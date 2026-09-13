"""Rhythm analysis for better alignment anchors.

Delivers a beat activation function per frame that is added to the
alignment as an extra feature (especially useful with drift/tempo
changes). Uses librosa's built-in beat tracking - that is already
installed and requires no compiler or separate download. On an error
``None`` is returned and the alignment falls back to onset/chroma/MFCC.
"""

from __future__ import annotations

import importlib.util
import logging

import numpy as np
from .translations import t

logger = logging.getLogger(__name__)

_SR = 22050
_HOP = 512


def is_available() -> bool:
    """Available as long as librosa is present (core dependency)."""
    return importlib.util.find_spec("librosa") is not None


def beat_activation(audio_path, frames: int) -> np.ndarray | None:
    """Beat activation (0..1) per alignment frame, or ``None`` on failure.

    Detects the beats with librosa and turns them into a smooth pulse
    train on the same frame grid as the alignment (sr 22050, hop
    512), so that the cross-correlation can latch onto it rhythmically.
    """
    if not is_available() or frames < 1:
        return None
    try:
        import librosa
        samples, _ = librosa.load(str(audio_path), sr=_SR, mono=True)
        if samples.size < _SR:
            return None
        _, beat_frames = librosa.beat.beat_track(
            y=samples, sr=_SR, hop_length=_HOP, units="frames")
    except Exception:  # noqa: BLE001 - beat tracking must not break alignment
        logger.exception(t("log_beat_analysis_failed"))
        return None
    if len(beat_frames) == 0:
        return None

    total = 1 + samples.size // _HOP
    pulse = np.zeros(total, dtype=np.float32)
    pulse[np.clip(beat_frames, 0, total - 1)] = 1.0
    # Smooth triangular kernel so the peak spreads a bit (more robust).
    kernel = np.array([0.4, 0.7, 1.0, 0.7, 0.4], dtype=np.float32)
    pulse = np.convolve(pulse, kernel, mode="same")

    source = np.linspace(0.0, 1.0, pulse.size)
    target = np.linspace(0.0, 1.0, frames)
    resampled = np.interp(target, source, pulse).astype(np.float32)
    top = float(resampled.max())
    return resampled / top if top > 0 else resampled


def beat_times(audio_path) -> list[float]:
    """Detect the beat moments (in seconds) of an audio file.

    Used for placing rhythmic chant lines on the beat
    (e.g. ``G Z R``) in the karaoke video. On an error or with librosa
    missing an empty list is returned (clean fallback to an
    even distribution).
    """
    if not is_available():
        return []
    try:
        import librosa
        samples, _ = librosa.load(str(audio_path), sr=_SR, mono=True)
        if samples.size < _SR:
            return []
        _, beat_frames = librosa.beat.beat_track(
            y=samples, sr=_SR, hop_length=_HOP, units="frames")
        times = librosa.frames_to_time(beat_frames, sr=_SR, hop_length=_HOP)
    except Exception:  # noqa: BLE001 - beat detection must not break timing
        logger.exception(t("log_beat_times_failed"))
        return []
    return [float(t) for t in times]


_ENV_CACHE: dict[tuple[str, float, int],
                 tuple[np.ndarray, np.ndarray] | None] = {}
#: Keys for which loading already failed and was reported (B256): prevents
#: the same broken audio/environment (e.g. a defective numba installation)
#: from being retried and logged hundreds of times within one session.
_ENV_FAILED_LOGGED: set[tuple[str, float, int]] = set()


def _rms_envelope(audio_path) -> tuple[np.ndarray, np.ndarray] | None:
    """(times, RMS) of an audio file on the frame grid, or ``None``.

    Basis for the vocal stem energy analysis (B194/B209): a smooth
    energy envelope with which we can extend held notes and find back
    the pulses of 'na-na' filler lines. The result is cached per file
    (path + mtime + size), so that repeated requests do not reload the
    vocal stem every time. If loading fails (e.g. a broken
    librosa/numba installation), that result is cached too (B256):
    without this cache every line/sentence in the song retries the same
    expensive and broken import, with a full stack trace each time
    (hundreds of identical messages for one song).
    """
    if not is_available():
        return None
    from pathlib import Path
    try:
        stat = Path(audio_path).stat()
        key = (str(audio_path), stat.st_mtime, stat.st_size)
    except OSError:
        key = None
    if key is not None and key in _ENV_CACHE:
        return _ENV_CACHE[key]
    try:
        import librosa
        samples, _ = librosa.load(str(audio_path), sr=_SR, mono=True)
        if samples.size < _HOP:
            if key is not None:
                _ENV_CACHE[key] = None
            return None
        rms = librosa.feature.rms(y=samples, hop_length=_HOP)[0]
        times = librosa.frames_to_time(np.arange(rms.size), sr=_SR,
                                       hop_length=_HOP)
    except Exception:  # noqa: BLE001 - energy analysis must never break
        if key is None or key not in _ENV_FAILED_LOGGED:
            logger.exception(t("log_rms_failed"))
            if key is not None:
                _ENV_FAILED_LOGGED.add(key)
        if key is not None:
            _ENV_CACHE[key] = None
        return None
    result = (times.astype(np.float32), rms.astype(np.float32))
    if key is not None:
        _ENV_CACHE[key] = result
    return result


#: Minimum duration of a contiguous silent gap (B277) to count as
#: "the vocals really stopped here", even if AFTER that gap another short
#: outlier above the threshold still occurs (e.g. the BUILD-UP of the next
#: line/crowd passage that happens to fall within the same analysis
#: window, because ``ceil_end``/``end`` is often the START of that next
#: line). Without this step simply "the last RMS sample point above the
#: threshold" determines the end - and that is then the build-up of the
#: NEXT line, even if there is a long silent gap in between.
#:
#: At first a moving average (~0.1s) over the RMS was also tried, to
#: average away a stubborn low noise floor before the threshold test.
#: Concretely compared on real, manually corrected project data
#: ("Lied B": 31 lines with an auto/manual difference
#: >0.3s), the PURE gap approach (on the raw sample points, without
#: smoothing) turned out to perform best: mean deviation 1.63s -> 0.28s,
#: median 1.47s -> 0.25s. Smoothing for the gap detection itself
#: sometimes even made this worse (a short surge of e.g. 0.07-0.08
#: fraction could end up just above the threshold after averaging, so
#: that a REALLY long silent gap was "smeared shut" and no longer
#: recognized as such - on one line that gave a deviation of 4.3s instead
#: of 0.2s). Hence: gap detection on the raw RMS, no separate smoothing
#: step.
_SUSTAINED_SILENCE_S = 0.3


def _last_active_time(rms: np.ndarray, times: np.ndarray,
                      mask: np.ndarray, threshold: float) -> float | None:
    """Last moment within ``mask`` with genuine, contiguous vocal
    energy (B277).

    Shared core of ``held_note_end`` (stretches out) and ``active_end``
    (shortens). Searches from right to left for the first contiguous
    silent gap of at least ``_SUSTAINED_SILENCE_S`` (~0.3s) between two
    consecutive above-threshold moments: everything after that (so
    later/to the right) belongs to a new sound episode (e.g. the next
    line or a crowd passage) and no longer counts. The answer is the
    last above-threshold moment BEFORE that gap. If no long gap at all
    is found (the whole series is one contiguous active episode), then
    simply the very last above-threshold moment remains the answer (the
    old behaviour). Returns ``None`` if there is nowhere enough energy.
    """
    window = rms[mask]
    wtimes = times[mask]
    if window.size == 0:
        return None
    top = np.where(window >= threshold)[0]
    if top.size == 0:
        return None
    # Step size of the time grid (frames are evenly distributed).
    if wtimes.size >= 2:
        step = float(wtimes[1] - wtimes[0])
    else:
        step = _HOP / _SR
    min_gap_frames = max(1, int(round(_SUSTAINED_SILENCE_S / step))) \
        if step > 0 else 1
    last = top[-1]
    for k in range(len(top) - 1, 0, -1):
        if top[k] - top[k - 1] >= min_gap_frames:
            last = top[k - 1]
            break
    return float(wtimes[last])


def held_note_end(audio_path, start: float, floor_end: float,
                  ceil_end: float, ratio: float = 0.15) -> float | None:
    """Determine the actual end of a held note (B194/B277).

    WhisperX puts the word end at the end of the phoneme; a long
    held vowel ("BSAaaa") therefore stops too early. This function
    looks in the vocal stem for where the energy after ``start`` is last
    above ``ratio`` of the local peak before a prolonged silent gap
    (B277: ``_last_active_time``, prevents the build-up of the next
    line/onset - which often happens to fall within ``ceil_end`` - from
    wrongly pulling up the end) and holds the note until that point. The
    result never lies before ``floor_end`` (the original end) and never
    after ``ceil_end`` (e.g. the next onset). ``None`` with the analysis
    missing.
    """
    env = _rms_envelope(audio_path)
    if env is None or ceil_end <= start:
        return None
    times, rms = env
    mask = (times >= start) & (times <= ceil_end)
    if not mask.any():
        return None
    peak = float(rms[mask].max())
    if peak <= 0:
        return None
    end = _last_active_time(rms, times, mask, peak * ratio)
    if end is None:
        return None
    return max(float(floor_end), min(end, float(ceil_end)))


#: When ``expected`` onsets are asked for, two selected onsets have to
#: lie at least this fraction of the AVERAGE spacing apart (B310).
#: Purely picking the strongest ``expected`` onsets regularly delivered
#: two pulses 70 ms apart (the attack and the body of the same sung
#: note), after which one line got a time slot of 70 ms and the rest of
#: the passage stayed empty. With a minimum spacing the selection
#: follows the rhythm of the passage instead of the loudness peaks.
#: Measured on a real la-la outro (nine lines over 35 seconds) the
#: spacing between the chosen onsets became regular from about 0.5
#: onwards; 0.6 keeps a margin without forcing a rigid grid.
_ONSET_MIN_SEPARATION_RATIO = 0.6


def energy_onsets(audio_path, gap_start: float, gap_end: float,
                  expected: int | None = None) -> list[float]:
    """Detect energy onsets (pulses) in a time span (B209/B310).

    In a non-transcribed 'na-na-na' passage the vocals ARE present in the
    vocal stem. This function looks for the onsets of those pulses
    between ``gap_start`` and ``gap_end``. If ``expected`` is given and
    more onsets are found, the strongest ones are returned (sorted by
    time), where two chosen onsets have to lie at least
    ``_ONSET_MIN_SEPARATION_RATIO`` of the average spacing apart. Empty
    list on failure -> the caller falls back on an even distribution over
    the gap.
    """
    if not is_available() or gap_end <= gap_start:
        return []
    try:
        import librosa
        samples, _ = librosa.load(str(audio_path), sr=_SR, mono=True,
                                  offset=max(0.0, gap_start),
                                  duration=gap_end - gap_start)
        if samples.size < _HOP:
            return []
        env = librosa.onset.onset_strength(y=samples, sr=_SR,
                                           hop_length=_HOP)
        frames = librosa.onset.onset_detect(
            onset_envelope=env, sr=_SR, hop_length=_HOP,
            backtrack=False, units="frames")
    except Exception:  # noqa: BLE001 - onset detection must never break
        logger.exception(t("log_onsets_failed"))
        return []
    if len(frames) == 0:
        return []
    frames = np.clip(frames, 0, len(env) - 1)
    times = librosa.frames_to_time(frames, sr=_SR, hop_length=_HOP)
    onsets = [(float(gap_start + t), float(env[f]))
              for t, f in zip(times, frames)]
    if expected is not None and expected > 0 and len(onsets) > expected:
        onsets = pick_spread_onsets(onsets, expected,
                                    (gap_end - gap_start) / expected
                                    * _ONSET_MIN_SEPARATION_RATIO)
    return [t for t, _s in onsets]


def pick_spread_onsets(onsets: list[tuple[float, float]], expected: int,
                       minimum_gap: float) -> list[tuple[float, float]]:
    """Choose the ``expected`` strongest onsets, spread out (B310).

    Strongest first, but an onset is only accepted if it lies at least
    ``minimum_gap`` away from every onset already chosen. Purely taking
    the strongest ones regularly picked two pulses of the SAME sung note
    (the attack and its body, tens of milliseconds apart), after which
    one line got a time slot of a few hundredths of a second and the rest
    of the passage stayed empty.

    Args:
        onsets: ``(time, strength)`` pairs.
        expected: How many are wanted.
        minimum_gap: Minimum distance between two chosen onsets.

    Returns:
        At most ``expected`` pairs, sorted by time.
    """
    chosen: list[tuple[float, float]] = []
    for time, strength in sorted(onsets, key=lambda p: p[1], reverse=True):
        if all(abs(time - t) >= minimum_gap for t, _s in chosen):
            chosen.append((time, strength))
        if len(chosen) >= expected:
            break
    return sorted(chosen, key=lambda p: p[0])


def active_windows(audio_path, thr_ratio: float = 0.08,
                   min_active: float = 0.4, min_gap: float = 0.6
                   ) -> list[tuple[float, float]]:
    """Time spans where the vocals are really active (B224).

    Returns merged (start, end) windows where the RMS lies above
    ``thr_ratio`` of the peak. Short gaps (< ``min_gap``) are bridged and
    very short windows (< ``min_active``) are dropped. Empty list on
    failure -> the caller then leaves the timing untouched.
    """
    env = _rms_envelope(audio_path)
    if env is None:
        return []
    times, rms = env
    peak = float(rms.max())
    if peak <= 0:
        return []
    top = rms >= peak * thr_ratio
    usable_windows: list[list[float]] = []
    i = 0
    n = len(top)
    while i < n:
        if top[i]:
            j = i
            while j < n and top[j]:
                j += 1
            usable_windows.append([float(times[i]), float(times[min(j, n - 1)])])
            i = j
        else:
            i += 1
    # bridge small gaps
    merged: list[list[float]] = []
    for v in usable_windows:
        if merged and v[0] - merged[-1][1] < min_gap:
            merged[-1][1] = v[1]
        else:
            merged.append(v)
    return [(s, e) for s, e in merged if e - s >= min_active]


def onsets(audio_path, min_rise: float = 0.20, window_s: float = 0.20,
           min_level: float = 0.25, min_gap: float = 0.8) -> list[float]:
    """Moments where the singing visibly starts (B330).

    :func:`active_windows` only gives the OUTER edges of a sung passage;
    within such a window the individual line starts are invisible. Two
    shouts two and a half seconds apart merged into one window of five
    seconds, after which two lines were spread evenly over that window
    instead of landing on their own shout.

    An onset here is a rise of at least ``min_rise`` of the song peak
    within ``window_s``, at a level that is really singing
    (``min_level``). Only the steepest moment of a rise counts, and
    onsets closer together than ``min_gap`` are one.

    Measured against a hand-corrected timing: every line start in a
    fifty-second stretch without transcription lay within 0.6 s of such
    an onset (median 0.15 s).
    """
    env = _rms_envelope(audio_path)
    if env is None:
        return []
    times, rms = env
    peak = float(rms.max())
    if peak <= 0 or len(times) < 3:
        return []
    level = rms / peak
    step = float(times[1] - times[0]) or 0.01
    span = max(1, int(round(window_s / step)))
    if len(level) <= span + 1:
        return []
    rise = np.zeros_like(level)
    rise[span:] = level[span:] - level[:-span]
    found: list[float] = []
    for i in range(span, len(level) - 1):
        if (rise[i] > min_rise and level[i] > min_level
                and rise[i] >= rise[i - 1] and rise[i] > rise[i + 1]):
            moment = float(times[i - span])
            if not found or moment - found[-1] > min_gap:
                found.append(moment)
    return found


def active_end(audio_path, start: float, end: float,
               thr_ratio: float = 0.08) -> float | None:
    """Last moment in ``[start, end]`` with vocal energy (B224/B261/B277).

    Used to shorten a line that runs on into a vocal-empty region
    (e.g. after a B194 stretch that overshot onto a loud crowd
    passage). The threshold is tested against the peak of the WHOLE
    vocal stem envelope, not against the peak within ``[start, end]``
    itself: that window can (just) be the already too far stretched
    line, in which a residual noise level just before ``end`` happens to
    determine the local peak. Such a self-referential threshold then
    stays almost everywhere "above the threshold" and no longer
    recognizes real silence (B261: the line kept running on while the
    voice-only track already lay (almost) flat). A song-wide reference
    peak stays stable, no matter how far the window itself has already
    been stretched. The last active moment itself is (just as with
    ``held_note_end``) determined via ``_last_active_time`` (B277): the
    contiguous silent gap before the build-up of the next line/onset
    (which often happens to fall within ``end``) is recognized, so that
    this build-up does not wrongly pull up the end. ``None`` if the
    analysis is missing or there is no energy in the window.
    """
    env = _rms_envelope(audio_path)
    if env is None or end <= start:
        return None
    times, rms = env
    piek = float(rms.max())
    if piek <= 0:
        return None
    mask = (times >= start) & (times <= end)
    if not mask.any():
        return None
    return _last_active_time(rms, times, mask, piek * thr_ratio)


def last_energy(audio_path, start: float, end: float,
                thr_ratio: float = 0.08) -> float | None:
    """The last moment with vocal energy in ``[start, end]`` - gaps and
    all (B492).

    ``active_end`` stops at the contiguous silent gap before the last
    sound episode, and that is right when a line has been stretched onto
    the NEXT line. It is wrong for a sentence that has a pause of its own
    in the middle: from the right, the first gap it finds is that pause,
    so the answer is the end of the FIRST half and the second half falls
    off. This one answers the plain question - where does the singing
    within this window stop - so that trailing silence can be trimmed
    without cutting a sentence in two.
    """
    env = _rms_envelope(audio_path)
    if env is None or end <= start:
        return None
    times, rms = env
    peak = float(rms.max())
    if peak <= 0:
        return None
    mask = (times >= start) & (times <= end)
    if not mask.any():
        return None
    window, wtimes = rms[mask], times[mask]
    above = np.where(window >= peak * thr_ratio)[0]
    if above.size == 0:
        return None
    return float(wtimes[above[-1]])


def count_repetitions(audio_path, gap_start: float, gap_end: float) -> int:
    """Estimate the number of repeating vocal bursts in a time span (B225).

    Counts the energy onsets in ``[gap_start, gap_end]`` as a measure of
    how many times a chant (e.g. 'na-na') repeats. 0 on failure.
    """
    onsets = energy_onsets(audio_path, gap_start, gap_end)
    return len(onsets)


def warmup() -> None:
    """Nothing to download; librosa is built in."""
    return None
