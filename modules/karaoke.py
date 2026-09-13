"""Karaoke editing: damping selected sound clusters.

The occurrences of the chosen clusters (moments in the original)
are projected onto the karaoke timeline via the alignment.
Only those fragments are lowered by ``gain_db`` (default
-25 dB) - there is no muting. Around each fragment there is a
crossfade: ``fade_in_ms`` down before the fragment, ``fade_out_ms``
back up after it. Overlapping fragments are merged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from . import audio
from .align import OffsetRegion, project_time
from .cluster import Cluster
from .config import KaraokeSettings
from .translations import t

logger = logging.getLogger(__name__)

#: Fragments that lie less than this many seconds apart are
#: merged (prevents up-and-down pumping damping).
_MERGE_GAP_S = 0.05


@dataclass(frozen=True)
class DampingInterval:
    """One fragment to be damped on the karaoke timeline."""

    label: str
    start: float
    end: float
    gain_db: float


@dataclass(frozen=True)
class RestoreInterval:
    """One fragment that is mixed with the ORIGINAL (B282).

    Unlike ``DampingInterval`` (which lowers the karaoke audio
    itself), a piece of the original source is laid over the karaoke
    audio here - intended for sound that Demucs (or a manual
    edit) has removed from the karaoke but that does belong there
    (e.g. a yee-haw shout or a sound effect). ``start``/``end``
    lie on the KARAOKE timeline (the window that the user marks in the
    damping editor); the corresponding time in the original is
    determined separately via :func:`modules.align.project_time_reverse`.
    """

    label: str
    start: float
    end: float


def find_intervals(
    selected: Sequence[Cluster],
    regions: Sequence[OffsetRegion],
    settings: KaraokeSettings,
) -> tuple[DampingInterval, ...]:
    """Project cluster occurrences onto the karaoke and merge overlap.

    Args:
        selected: The clusters chosen by the user.
        regions: Offset regions from the alignment step.
        settings: Karaoke settings (damping).

    Returns:
        Sorted, merged damping fragments.
    """
    margin = settings.margin_ms / 1000.0
    raw: list[DampingInterval] = []
    for cluster in selected:
        for occurrence in cluster.occurrences:
            start = max(0.0, project_time(occurrence.start, regions) - margin)
            end = project_time(occurrence.end, regions) + margin
            if end > start:
                raw.append(DampingInterval(label=cluster.label, start=start,
                                           end=end, gain_db=settings.gain_db))
    merged = merge_intervals(raw)
    logger.info(t("log_damping_fragments"),
                len(merged), len(raw))
    return merged


def merge_intervals(
    intervals: Sequence[DampingInterval],
) -> tuple[DampingInterval, ...]:
    """Sort fragments and merge overlapping/adjacent ones.

    The label of a merged fragment names all sounds that are in it
    ("oe+woo"), not only that of the first one (B301): in the
    damping editor and the fragment list that label otherwise pointed to
    one cluster while the box in reality damped several clusters, which
    made ticking it on and off misleading. The damping itself
    (``gain_db``) becomes the STRONGEST of the merged fragments: if two
    overlapping fragments ask for different damping, the heaviest is the
    safe choice - otherwise a softer fragment would silently weaken a
    damping that was meant to be harder.
    """
    ordered = sorted(intervals, key=lambda interval: interval.start)
    merged: list[DampingInterval] = []
    for interval in ordered:
        if merged and interval.start <= merged[-1].end + _MERGE_GAP_S:
            previous = merged[-1]
            labels = previous.label.split("+")
            if interval.label not in labels:
                labels.append(interval.label)
            merged[-1] = DampingInterval(
                label="+".join(labels),
                start=previous.start,
                end=max(previous.end, interval.end),
                gain_db=min(previous.gain_db, interval.gain_db),
            )
        else:
            merged.append(interval)
    return tuple(merged)


def apply_damping(
    karaoke_wav: Path,
    intervals: Sequence[DampingInterval],
    settings: KaraokeSettings,
    output_wav: Path,
    restore_intervals: Sequence[tuple[RestoreInterval, np.ndarray, int]]
        = (),
) -> Path:
    """Apply the damping with crossfades and write the result.

    Args:
        karaoke_wav: The (unprocessed) karaoke wav file.
        intervals: The fragments to be damped (karaoke timeline).
        settings: Karaoke settings (fades).
        output_wav: Target path for the processed wav file.
        restore_intervals: (B282) "restore from original" fragments, each
            as ``(RestoreInterval, origineel_samples, origineel_sample_rate)``
            - the original samples have already been preprocessed (cut
            out and resampled to the sample rate of ``karaoke_wav``) by
            the caller. These fragments are mixed over the karaoke audio
            AFTER the damping, so that they are not damped themselves.

    Returns:
        The path of the processed file.
    """
    data, sample_rate = audio.load_audio(karaoke_wav)
    envelope = build_envelope(data.shape[0], sample_rate, intervals, settings)
    result = data * envelope[:, None]
    if restore_intervals:
        result = apply_restore(result, sample_rate, restore_intervals,
                               settings)
    audio.save_wav(output_wav, result, sample_rate)
    total = sum(interval.end - interval.start for interval in intervals)
    logger.info(t("log_damping_applied"),
                len(intervals), total, settings.gain_db)
    if restore_intervals:
        restore_total = sum(iv.end - iv.start
                            for iv, _, _ in restore_intervals)
        logger.info(t("log_restore_applied"),
                    len(restore_intervals), restore_total)
    return output_wav


def apply_restore(
    data: np.ndarray,
    sample_rate: int,
    restore_intervals: Sequence[tuple[RestoreInterval, np.ndarray, int]],
    settings: KaraokeSettings,
) -> np.ndarray:
    """Mix original audio over the karaoke samples (B282).

    For each fragment the (already cut out and to ``sample_rate``
    resampled) original samples are laid over ``data``, with
    the same crossfade build-up as the damping (``fade_in_ms``/
    ``fade_out_ms``): a gradual transition from the karaoke audio to
    the original fragment and back again, so that no audible cut
    occurs. Within the fragment itself (after the fade-in, before the
    fade-out) only the original fragment sounds - this REPLACES the
    karaoke audio there, instead of mixing the two (otherwise any
    residual karaoke would keep sounding through the restored sound).

    Args:
        data: The karaoke samples (after damping), shape ``(n, kanalen)``.
        sample_rate: Sample rate of ``data``.
        restore_intervals: Fragments with their preprocessed original
            audio.
        settings: Karaoke settings (fades).

    Returns:
        The samples with the fragments replaced by the original.
    """
    if not restore_intervals:
        return data
    result = data.copy()
    n_samples = result.shape[0]
    fade_in = max(1, audio.seconds_to_samples(settings.fade_in_ms / 1000.0,
                                              sample_rate))
    fade_out = max(1, audio.seconds_to_samples(settings.fade_out_ms / 1000.0,
                                               sample_rate))
    for interval, orig_samples, orig_sr in restore_intervals:
        if orig_sr != sample_rate:
            logger.warning(
                t("log_restore_rate_mismatch"),
                orig_sr, sample_rate, interval.label)
            continue
        start = np.clip(audio.seconds_to_samples(interval.start, sample_rate),
                        0, n_samples)
        end = np.clip(audio.seconds_to_samples(interval.end, sample_rate),
                     0, n_samples)
        if end <= start:
            continue
        span = end - start
        source = orig_samples
        if source.ndim == 1:
            source = source[:, None]
        if source.shape[1] != result.shape[1]:
            # Match channels (mono<->stereo) by repeating/averaging.
            if source.shape[1] == 1:
                source = np.repeat(source, result.shape[1], axis=1)
            else:
                source = source.mean(axis=1, keepdims=True)
                source = np.repeat(source, result.shape[1], axis=1)
        usable = min(span, source.shape[0])
        if usable <= 0:
            continue
        segment = source[:usable].astype(np.float32)

        # Within the fragment: replace entirely by the original.
        result[start:start + usable] = segment
        if usable < span:
            # Original fragment shorter than the marked window: the
            # rest stays the (damped) karaoke audio.
            logger.warning(
                t("log_restore_too_short"),
                interval.label, (span - usable) / sample_rate)

        # Crossfade at the edges: gradual transition instead of a cut.
        ramp_start = max(0, start - fade_in)
        if start > ramp_start:
            ramp = np.linspace(0.0, 1.0, start - ramp_start,
                               endpoint=False, dtype=np.float32)[:, None]
            result[ramp_start:start] = (
                data[ramp_start:start] * (1.0 - ramp)
                + segment[0] * ramp if usable > 0
                else data[ramp_start:start])
        fade_end = start + usable
        ramp_end = min(n_samples, fade_end + fade_out)
        if ramp_end > fade_end:
            ramp = np.linspace(1.0, 0.0, ramp_end - fade_end,
                               dtype=np.float32)[:, None]
            tail = segment[-1] if usable > 0 else 0.0
            result[fade_end:ramp_end] = (
                tail * ramp + data[fade_end:ramp_end] * (1.0 - ramp))
    return result


def build_envelope(
    n_samples: int,
    sample_rate: int,
    intervals: Sequence[DampingInterval],
    settings: KaraokeSettings,
) -> np.ndarray:
    """Build the gain envelope (1.0 = unchanged).

    Per fragment: linear fade from 1.0 to the damping factor in the
    ``fade_in_ms`` before the start, hold until the end, and back
    to 1.0 in the ``fade_out_ms`` after it. Overlapping envelopes are
    combined with the minimum.
    """
    envelope = np.ones(n_samples, dtype=np.float32)
    fade_in = max(1, audio.seconds_to_samples(settings.fade_in_ms / 1000.0,
                                              sample_rate))
    fade_out = max(1, audio.seconds_to_samples(settings.fade_out_ms / 1000.0,
                                               sample_rate))
    for interval in intervals:
        gain = audio.db_to_amplitude(interval.gain_db)
        start = np.clip(audio.seconds_to_samples(interval.start, sample_rate),
                        0, n_samples)
        end = np.clip(audio.seconds_to_samples(interval.end, sample_rate),
                      0, n_samples)
        if end <= start:
            continue
        ramp_start = max(0, start - fade_in)
        if start > ramp_start:
            ramp = np.linspace(1.0, gain, start - ramp_start,
                               endpoint=False, dtype=np.float32)
            envelope[ramp_start:start] = np.minimum(
                envelope[ramp_start:start], ramp)
        envelope[start:end] = np.minimum(envelope[start:end],
                                         np.float32(gain))
        ramp_end = min(n_samples, end + fade_out)
        if ramp_end > end:
            ramp = np.linspace(gain, 1.0, ramp_end - end, dtype=np.float32)
            envelope[end:ramp_end] = np.minimum(envelope[end:ramp_end], ramp)
    return envelope


def intervals_to_dicts(
    intervals: Sequence[DampingInterval],
) -> list[dict[str, Any]]:
    """Convert damping fragments into JSON-serializable dicts."""
    return [{"label": interval.label, "start": interval.start,
             "end": interval.end, "gain_db": interval.gain_db}
            for interval in intervals]


def intervals_from_dicts(
    data: list[dict[str, Any]],
) -> tuple[DampingInterval, ...]:
    """Rebuild damping fragments from dicts."""
    return tuple(DampingInterval(label=str(item["label"]),
                                 start=float(item["start"]),
                                 end=float(item["end"]),
                                 gain_db=float(item["gain_db"]))
                 for item in data)


# B292: ``restore_intervals_to_dicts``/``_from_dicts`` (B282) used to be
# here. They have been removed: nobody called them, and moreover they
# described a different format than what is actually stored -
# ``restore_fragmenten`` keeps (start, end, label) triples, not dicts
# (see ``pipeline.restore_intervals``). Two functions that did not match
# reality are worse than no functions.
