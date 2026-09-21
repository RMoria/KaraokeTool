"""Alignment of original and karaoke version.

Original and karaoke can differ slightly in timing. This module
automatically determines the offset(s) with a combination of
onset detection, chroma features and MFCCs, combined via
FFT cross-correlation - without assumptions about BPM or bar length.
The song is then re-measured in windows; if the offset deviates
locally, multiple offset regions arise (up to ``max_offsets``).

Convention: ``offset = karaoke time - original time``. Regions are on
the timeline of the ORIGINAL; :func:`project_time` projects a
moment from the original onto the karaoke.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .config import AlignSettings
from .translations import t

logger = logging.getLogger(__name__)

#: If the offset of a region deviates more than this (seconds) from the
#: median, it is almost certainly a wrong measurement (outlier)
#: and the region gets the median offset.
OUTLIER_OFFSET_S = 1.0

_SR = 22050
_HOP = 512
_FRAME_S = _HOP / _SR


class AlignError(Exception):
    """Error during alignment."""


@dataclass(frozen=True)
class OffsetRegion:
    """One time region (original timeline) with its own offset."""

    start: float
    end: float
    offset: float
    confidence: float


@dataclass(frozen=True)
class WindowOffset:
    """Measurement of the offset in one analysis window."""

    start: float
    end: float
    offset: float
    confidence: float


def determine_offsets(
    original_wav: Path,
    karaoke_wav: Path,
    settings: AlignSettings,
) -> tuple[OffsetRegion, ...]:
    """Determine the offset(s) between original and karaoke.

    Args:
        original_wav: Wav file of the original.
        karaoke_wav: Wav file of the karaoke version.
        settings: Alignment settings.

    Returns:
        One or more offset regions that together cover the whole
        original, sorted by start time.

    Raises:
        AlignError: If librosa is missing or the audio is unreadable.
    """
    features_original, duration = _features(original_wav)
    features_karaoke, _ = _features(karaoke_wav)

    global_lag, global_confidence = _correlate_offset(
        features_original, features_karaoke)
    global_offset = -global_lag * _FRAME_S
    logger.info(t("log_global_offset"),
                global_offset * 1000, global_confidence)

    windows = _window_offsets(features_original, features_karaoke,
                              global_lag, settings)
    regions = _build_regions(windows, duration, global_offset,
                             global_confidence, settings)
    regions = _smooth_regions(regions)
    for region in regions:
        logger.info(t("log_region_offset"),
                    region.start, region.end, region.offset * 1000,
                    region.confidence)
    return regions


def _smooth_regions(regions: tuple[OffsetRegion, ...]
                    ) -> tuple[OffsetRegion, ...]:
    """Make the offset regions robust and monotonic.

    1. **Outliers** (offset far from the median) get the median
       offset - a single wrong measurement can otherwise make the
       projection jump by seconds (empty stretches/reversed lines).
    2. **No backward jumps in the projected time**: the offset may
       decrease (the karaoke can gradually start running ahead of the
       original), as long as the *projected* time does not run backwards.

    The old approach pulled every region that lay > OUTLIER_OFFSET_S from
    the global median towards that median AND forced the offsets to be
    monotonically non-decreasing. With a song with gradual tempo drift
    (over its duration the karaoke drifts seconds out of sync) that
    flattened the real drift into one flat offset. Now we follow the
    drift: we estimate the local trend and only replace regions that
    deviate from THAT trend (isolated measurement errors), not the trend
    itself (B249).

    There used to be a ``fallback_offset`` parameter here that, since
    that switch to trend detection, was no longer used anywhere in the
    body - the median fallback it was meant for no longer exists.
    Removed (B293).
    """
    if len(regions) <= 1:
        return regions

    ordered = sorted(regions, key=lambda region: region.start)
    offsets = [r.offset for r in ordered]

    # --- Robust outlier detection via a median filter. ------------------
    # For every region we take the median of the neighbours (+-2, region
    # itself excluded). A region only counts as an outlier once it clearly
    # deviates from that: more than OUTLIER_OFFSET_S AND more than 3x the
    # mutual spread of the neighbours. This way a gradual drift slope
    # stays standing (the neighbours then lie close to the median, and so
    # does its own value), while an isolated jump stands out. A median is
    # robust against one outlier neighbour, unlike a least-squares line.
    def _neighbours(index: int) -> list[float]:
        return [offsets[j] for j in range(index - 2, index + 3)
                if 0 <= j < len(offsets) and j != index]

    def _median(values: list[float]) -> float:
        s = sorted(values)
        m = len(s) // 2
        return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2.0

    def _trend(index: int) -> float:
        neighbours = _neighbours(index)
        return _median(neighbours) if neighbours else offsets[index]

    def _is_outlier(index: int) -> bool:
        neighbours = _neighbours(index)
        if len(neighbours) < 2:
            return False
        med = _median(neighbours)
        spread = _median([abs(b - med) for b in neighbours])  # robust spread
        threshold = max(OUTLIER_OFFSET_S, 3.0 * spread)
        return abs(offsets[index] - med) > threshold

    cleaned: list[OffsetRegion] = []
    for i, region in enumerate(ordered):
        if _is_outlier(i):
            trend = _trend(i)
            logger.info(t("log_outlier_region"),
                        region.start, region.end, region.offset * 1000,
                        trend * 1000)
            cleaned.append(replace(region, offset=trend))
        else:
            cleaned.append(region)

    # --- No backward jump in the *projected* time. ----------------------
    # The offset itself may decrease; only if start+offset would run
    # backwards relative to the previous region do we adjust the offset.
    # This keeps drift (also downward) without the karaoke timeline
    # jumping back.
    result: list[OffsetRegion] = [cleaned[0]]
    for region in cleaned[1:]:
        previous = result[-1]
        if region.start + region.offset < previous.start + previous.offset:
            region = replace(region,
                             offset=previous.start + previous.offset - region.start)
        result.append(region)
    return tuple(result)


def project_time(seconds: float, regions: Sequence[OffsetRegion]) -> float:
    """Project a moment from the original onto the karaoke timeline.

    The offset is **linearly interpolated** between the centers of
    consecutive regions, so that gradual drift becomes a smooth slope
    instead of stepwise jumps at the region boundaries (B249). Before the
    first and after the last region center the offset of that edge
    region applies (no extrapolation). The result is never negative.
    """
    if not regions:
        return max(0.0, seconds)
    ordered = sorted(regions, key=lambda region: region.start)
    centers = [((r.start + r.end) / 2.0, r.offset) for r in ordered]
    if seconds <= centers[0][0]:
        return max(0.0, seconds + centers[0][1])
    if seconds >= centers[-1][0]:
        return max(0.0, seconds + centers[-1][1])
    for (t0, o0), (t1, o1) in zip(centers, centers[1:]):
        if t0 <= seconds <= t1:
            frac = 0.0 if t1 == t0 else (seconds - t0) / (t1 - t0)
            return max(0.0, seconds + o0 + frac * (o1 - o0))
    return max(0.0, seconds + centers[-1][1])


def project_time_reverse(
        seconds: float, regions: Sequence[OffsetRegion]) -> float:
    """Project a moment from the KARAOKE timeline back to the
    original (B282, the reverse direction of :func:`project_time`).

    Used by the "restore from original" damping: the user marks a time
    span on the karaoke waveform, and that has to be converted to the
    corresponding time span in the original file. The same linear
    interpolation between region centers as ``project_time``, but with
    the centers expressed on the KARAOKE timeline (``midden_origineel +
    offset``) instead of the original. The result is never
    negative.
    """
    if not regions:
        return max(0.0, seconds)
    ordered = sorted(regions, key=lambda region: region.start)
    # Centers, expressed on the karaoke timeline (on which 'seconds' lies).
    centers = [(((r.start + r.end) / 2.0) + r.offset, r.offset)
              for r in ordered]
    if seconds <= centers[0][0]:
        return max(0.0, seconds - centers[0][1])
    if seconds >= centers[-1][0]:
        return max(0.0, seconds - centers[-1][1])
    for (t0, o0), (t1, o1) in zip(centers, centers[1:]):
        if t0 <= seconds <= t1:
            frac = 0.0 if t1 == t0 else (seconds - t0) / (t1 - t0)
            offset = o0 + frac * (o1 - o0)
            return max(0.0, seconds - offset)
    return max(0.0, seconds - centers[-1][1])


def regions_to_dicts(regions: Sequence[OffsetRegion]) -> list[dict[str, Any]]:
    """Convert regions into JSON-serializable dicts."""
    return [{"start": region.start, "end": region.end,
             "offset": region.offset, "confidence": region.confidence}
            for region in regions]


def regions_from_dicts(data: list[dict[str, Any]]) -> tuple[OffsetRegion, ...]:
    """Rebuild regions from dicts."""
    return tuple(OffsetRegion(start=float(item["start"]),
                              end=float(item["end"]),
                              offset=float(item["offset"]),
                              confidence=float(item["confidence"]))
                 for item in data)


def _features(path: Path) -> tuple[np.ndarray, float]:
    """Compute the feature matrix (onsets, chroma, MFCC, beats) of a file.

    Every feature row is normalized (z-score); the onset row counts
    double because rhythm is the most reliable alignment signal. The
    beat anchor (librosa) is always added when it succeeds; otherwise
    the alignment quietly falls back to onset/chroma/MFCC.

    Returns:
        Tuple of (matrix with shape ``(rijen, frames)``, duration in s).
    """
    try:
        import librosa
    except ImportError as exc:
        raise AlignError(t("err_librosa_missing")) from exc
    try:
        samples, _ = librosa.load(str(path), sr=_SR, mono=True)
    except Exception as exc:  # noqa: BLE001 - librosa/audioread errors
        raise AlignError(
            t("err_align_audio_unreadable").format(path=path)) from exc
    if samples.size < _SR:
        raise AlignError(t("err_align_audio_too_short").format(path=path))

    onset = librosa.onset.onset_strength(y=samples, sr=_SR, hop_length=_HOP)
    chroma = librosa.feature.chroma_stft(y=samples, sr=_SR, hop_length=_HOP)
    mfcc = librosa.feature.mfcc(y=samples, sr=_SR, hop_length=_HOP, n_mfcc=13)

    frames = min(onset.shape[-1], chroma.shape[-1], mfcc.shape[-1])
    rows = [
        _normalize_rows(onset[None, :frames]) * 2.0,
        _normalize_rows(chroma[:, :frames]),
        _normalize_rows(mfcc[:, :frames]),
    ]
    from . import rhythm
    beats = rhythm.beat_activation(path, frames)
    if beats is not None:
        rows.insert(0, _normalize_rows(beats[None, :frames]) * 2.0)
    stacked = np.vstack(rows)
    return stacked.astype(np.float32), samples.size / _SR


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    """Z-score normalization per feature row (robust against silence)."""
    mean = matrix.mean(axis=1, keepdims=True)
    std = matrix.std(axis=1, keepdims=True)
    std[std < 1e-8] = 1.0
    return (matrix - mean) / std


def _correlate_offset(reference: np.ndarray,
                      query: np.ndarray) -> tuple[float, float]:
    """Find where ``query`` fits best within ``reference`` (FFT).

    Returns:
        Tuple of (lag in frames, possibly fractional: ``query[t] ~
        reference[t + lag]``, and a normalized confidence 0..1).
    """
    length = reference.shape[1] + query.shape[1] - 1
    nfft = 1 << (length - 1).bit_length()
    spectrum = (np.fft.rfft(reference, nfft, axis=1)
                * np.conj(np.fft.rfft(query, nfft, axis=1)))
    correlation = np.fft.irfft(spectrum, nfft, axis=1).sum(axis=0)

    max_positive = reference.shape[1] - 1
    max_negative = query.shape[1] - 1
    lags = np.concatenate([np.arange(0, max_positive + 1),
                           np.arange(-max_negative, 0)])
    values = np.concatenate([correlation[:max_positive + 1],
                             correlation[nfft - max_negative:nfft]])

    peak_index = int(np.argmax(values))
    lag = float(lags[peak_index])
    lag += _parabolic_refinement(values, peak_index)

    norm = float(np.linalg.norm(reference) * np.linalg.norm(query))
    scale = min(reference.shape[1], query.shape[1]) / max(
        reference.shape[1], query.shape[1])
    confidence = 0.0 if norm <= 0 else float(
        np.clip(values[peak_index] / (norm * np.sqrt(scale)), 0.0, 1.0))
    return lag, confidence


def _parabolic_refinement(values: np.ndarray, index: int) -> float:
    """Sub-frame refinement of a correlation peak (parabola fit)."""
    if index <= 0 or index >= len(values) - 1:
        return 0.0
    left, center, right = values[index - 1], values[index], values[index + 1]
    denominator = left - 2.0 * center + right
    if abs(denominator) < 1e-12:
        return 0.0
    return float(np.clip(0.5 * (left - right) / denominator, -0.5, 0.5))


def _window_offsets(
    features_original: np.ndarray,
    features_karaoke: np.ndarray,
    global_lag: float,
    settings: AlignSettings,
) -> list[WindowOffset]:
    """Measure the offset per window around the global estimate."""
    window = int(settings.window_s / _FRAME_S)
    step = int(settings.step_s / _FRAME_S)
    search = int(settings.search_s / _FRAME_S)
    frames_karaoke = features_karaoke.shape[1]
    frames_original = features_original.shape[1]

    results: list[WindowOffset] = []
    for start in range(0, max(frames_karaoke - window, 0) + 1, max(step, 1)):
        segment = features_karaoke[:, start:start + window]
        expected = start + int(round(global_lag))
        slice_start = max(0, expected - search)
        slice_end = min(frames_original, expected + window + search)
        if slice_end - slice_start < window // 2:
            continue
        reference = features_original[:, slice_start:slice_end]
        local_lag, confidence = _correlate_offset(reference, segment)
        total_lag = slice_start + local_lag - start
        offset = -total_lag * _FRAME_S
        original_start = (start + total_lag) * _FRAME_S
        results.append(WindowOffset(
            start=max(0.0, original_start),
            end=max(0.0, original_start) + settings.window_s,
            offset=offset,
            confidence=confidence,
        ))
    return results


def _build_regions(
    windows: Sequence[WindowOffset],
    duration: float,
    fallback_offset: float,
    fallback_confidence: float,
    settings: AlignSettings,
) -> tuple[OffsetRegion, ...]:
    """Group window measurements into contiguous offset regions.

    Windows with too low a confidence are dropped; consecutive windows
    with (virtually) the same offset form one region. More regions than
    ``max_offsets``? Then neighbouring regions with the smallest
    offset differences are merged. The regions are stretched so that
    together they cover 0..duration.
    """
    tolerance = settings.tolerance_ms / 1000.0
    usable = [w for w in windows if w.confidence >= settings.min_confidence]
    if not usable:
        logger.warning(t("log_no_reliable_windows"))
        return (OffsetRegion(0.0, duration, fallback_offset,
                             fallback_confidence),)

    groups: list[list[WindowOffset]] = [[usable[0]]]
    for window in usable[1:]:
        mean_offset = float(np.mean([w.offset for w in groups[-1]]))
        if abs(window.offset - mean_offset) <= tolerance:
            groups[-1].append(window)
        else:
            groups.append([window])

    while len(groups) > settings.max_offsets:
        differences = [
            abs(float(np.mean([w.offset for w in groups[i]]))
                - float(np.mean([w.offset for w in groups[i + 1]])))
            for i in range(len(groups) - 1)
        ]
        index = int(np.argmin(differences))
        groups[index] = groups[index] + groups.pop(index + 1)

    regions: list[OffsetRegion] = []
    for group in groups:
        weights = np.array([w.confidence for w in group])
        offsets = np.array([w.offset for w in group])
        # B301: ``np.average`` divides by the sum of the weights and gives
        # a ZeroDivisionError as soon as that is zero (all windows at
        # confidence 0.0). The configuration check now stops that up
        # front, but a group can end up looking like that by another route
        # too; in that case fall back on the unweighted mean instead of
        # letting the whole alignment crash.
        gewichtensom = float(weights.sum())
        average_offset = (float(np.average(offsets, weights=weights))
                            if gewichtensom > 0 else float(np.mean(offsets)))
        regions.append(OffsetRegion(
            start=group[0].start,
            end=group[-1].end,
            offset=average_offset,
            confidence=float(np.mean(weights)),
        ))

    stitched: list[OffsetRegion] = []
    for index, region in enumerate(regions):
        start = 0.0 if index == 0 else (regions[index - 1].end
                                        + region.start) / 2.0
        end = duration if index == len(regions) - 1 else (
            region.end + regions[index + 1].start) / 2.0
        stitched.append(OffsetRegion(start=start, end=max(start, end),
                                     offset=region.offset,
                                     confidence=region.confidence))
    return tuple(stitched)
