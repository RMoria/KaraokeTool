"""Timing from the other stems: drums, breaths and the choir (v1.0.22).

Demucs keeps its four stems since v1.0.22 (B632) and a karaoke model
splits the lead voice from the choir. Three ideas use them, each a model
in the register and off until a test on the test set has measured it
against the hand timings (1.5.19):

* **B633 - the drums as the anchor.** A sung line starts on the beat of
  the band far more often than between two beats. The beats and the
  half beats of the drum stem are a grid, and a line start near a grid
  point is pulled onto it - a little way only, and never across its
  neighbours. Whisper's word starts are a tenth of a second off as a
  rule; the drums are not.
* **B634 - breaths and pauses.** Between two lines the singer breathes:
  the lead voice falls silent for a moment. A line start that lies in
  the middle of singing, with a pause close by, is moved to where the
  singing starts again after that pause, and the line before it ends
  where the pause begins.
* **B635 - [bg] from the choir.** Lines and pieces marked ``[bg]`` are
  sung by the choir, not by the lead; Whisper listens to all the voices
  and cannot tell them apart. The choir stem can: a ``[bg]`` line starts
  where the choir starts singing nearby, and ends where it stops; an
  inline ``[bg]`` piece moves as a whole to the choir's start.

The functions here work on plain times and timed lines; where the stems
come from and how their times reach the karaoke's timeline is the
pipeline's business (``pipeline._stem_models``).
"""
from __future__ import annotations

import bisect
import logging
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .timing import _MIN_ANY_S
from .translations import t

logger = logging.getLogger(__name__)

#: B633: how far a line start may be pulled onto the drums' grid.
DRUM_REACH_S = 0.12
#: B634: how far a pause may be from a line start to count for it.
PAUSE_REACH_S = 0.5
#: B634: silence of the lead voice at least this long is a breath.
PAUSE_MIN_S = 0.15
#: B634: below this share of the voice's peak the voice is silent.
PAUSE_LEVEL = 0.06
#: B635: how far the choir's start may be from a [bg] line's start.
CHOIR_REACH_S = 1.0
#: B635: how far an inline [bg] piece may move.
PIECE_REACH_S = 0.6
#: Nothing gets shorter than this: the least length a line is put on by
#: ``timing._reflow_line``, so moving a start never pushes an end out.
_LEAST_S = _MIN_ANY_S


# -- what the stems say ----------------------------------------------------------

def drum_grid(audio_path: Path) -> list[float]:
    """The beats of the drum stem and the moments halfway between them,
    in seconds; empty when there is no beat to be found."""
    try:
        import librosa

        samples, rate = librosa.load(str(audio_path), sr=22050, mono=True)
        if samples.size < rate:
            return []
        _tempo, frames = librosa.beat.beat_track(y=samples, sr=rate,
                                                 hop_length=512,
                                                 units="frames")
        beats = [float(x) for x in librosa.frames_to_time(
            frames, sr=rate, hop_length=512)]
    except Exception:  # noqa: BLE001 - a model may never break the timing
        logger.exception(t("log_stem_model_read_failed"), audio_path)
        return []
    grid = []
    for first, second in zip(beats, beats[1:]):
        grid += [first, (first + second) / 2.0]
    if beats:
        grid.append(beats[-1])
    return grid


def pauses(audio_path: Path, level: float = PAUSE_LEVEL,
           least: float = PAUSE_MIN_S) -> list[tuple[float, float]]:
    """Where the voice is silent for at least ``least`` seconds:
    ``(start, end)`` pairs, the end being where it sings again."""
    from . import rhythm

    envelope = rhythm._rms_envelope(audio_path)
    if envelope is None:
        return []
    times, rms = envelope
    peak = float(rms.max()) if rms.size else 0.0
    if peak <= 0:
        return []
    quiet = rms < peak * level
    found = []
    start = None
    for index, silent in enumerate(quiet):
        if silent and start is None:
            start = index
        elif not silent and start is not None:
            begin, end = float(times[start]), float(times[index])
            if end - begin >= least:
                found.append((begin, end))
            start = None
    return found


def choir_starts(audio_path: Path) -> list[float]:
    """Where the choir starts singing (the onsets of its stem, at a lower
    level than a lead voice: a choir is quieter and wider)."""
    from . import rhythm

    return rhythm.onsets(audio_path, min_level=0.15, min_gap=0.5)


def choir_windows(audio_path: Path) -> list[tuple[float, float]]:
    from . import rhythm

    return rhythm.active_windows(audio_path, thr_ratio=0.1, min_active=0.2,
                                 min_gap=0.3)


# -- the models ---------------------------------------------------------------

def _sung(line) -> bool:
    return not line.bg and not line.disabled and bool(line.syllables) \
        and line.end > line.start


def _reflow(line, start: float, end: float):
    from .timing import _reflow_line

    return _reflow_line(line, start, end)


def _nearest(ordered: Sequence[float], moment: float, reach: float,
             low: float, high: float) -> float | None:
    """The time in ``ordered`` nearest to ``moment`` within ``reach`` and
    inside ``[low, high)``."""
    n = bisect.bisect_left(ordered, moment)
    best = None
    for k in range(max(0, n - 3), min(len(ordered), n + 3)):
        value = ordered[k]
        if abs(value - moment) > reach or value < low or value >= high:
            continue
        if best is None or abs(value - moment) < abs(best - moment):
            best = value
    return best


def on_the_drums(lines: Sequence, grid: Sequence[float],
                 reach: float = DRUM_REACH_S) -> tuple:
    """B633: every sung line start pulled onto the nearest point of the
    drums' grid within ``reach`` - after the line before it, and leaving
    the line at least a moment long."""
    ordered = sorted(float(x) for x in grid)
    if not ordered:
        return tuple(lines)
    out = []
    previous_end = 0.0
    for index, line in enumerate(lines):
        if not _sung(line):
            out.append(line)
            continue
        high = min(line.end - _LEAST_S, _next_start(lines, index))
        found = _nearest(ordered, line.start, reach, previous_end - 1e-9,
                         high)
        if found is not None and abs(found - line.start) > 0.005:
            line = _reflow(line, found, line.end)
        out.append(line)
        previous_end = line.end
    return tuple(out)


def _next_start(lines: Sequence, index: int) -> float:
    """Where the next sung line starts (a moved start stays before it)."""
    return next((line.start for line in lines[index + 1:] if _sung(line)),
                float("inf"))


def at_the_breaths(lines: Sequence, silent: Sequence[tuple[float, float]],
                   reach: float = PAUSE_REACH_S) -> tuple:
    """B634: a line start in the middle of singing moves to the end of the
    nearest pause within ``reach``; the line before it then ends at the
    start of that pause, where it overlaps it."""
    ends = sorted(end for _start, end in silent)
    begin_of = {end: start for start, end in silent}
    out = list(lines)
    previous = None
    for index, line in enumerate(out):
        if not _sung(line):
            continue
        if previous is None:
            previous = index
            continue
        before = out[previous]
        # Already at the end of a pause: that is where it belongs.
        if _nearest(ends, line.start, 0.04, 0.0, float("inf")) is not None:
            previous = index
            continue
        found = _nearest(ends, line.start, reach,
                         before.start + _LEAST_S,
                         min(line.end - _LEAST_S, _next_start(out, index)))
        if found is not None:
            breath = begin_of[found]
            if before.end > breath:
                if breath - before.start < _LEAST_S:
                    previous = index
                    continue
                out[previous] = _reflow(before, before.start, breath)
            out[index] = _reflow(line, found, line.end)
        previous = index
    return tuple(out)


def _bg_runs(line) -> list[tuple[int, int]]:
    """The inline [bg] pieces of a line: ``(first, last + 1)`` syllable
    indices."""
    runs = []
    start = None
    for index, piece in enumerate(line.syllables):
        if piece.bg and start is None:
            start = index
        elif not piece.bg and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(line.syllables)))
    return runs


def from_the_choir(lines: Sequence, starts: Sequence[float],
                   windows: Sequence[tuple[float, float]],
                   reach: float = CHOIR_REACH_S,
                   piece_reach: float = PIECE_REACH_S) -> tuple:
    """B635: [bg] lines and pieces on the choir. A whole [bg] line starts
    at the nearest start of the choir within ``reach`` and ends where
    that stretch of choir ends (at least a moment, at most twice its old
    length); an inline piece keeps its length and moves to the choir's
    start within ``piece_reach``. A [bg] part may overlap its neighbours
    - it is sung at the same time - so only the choir bounds it."""
    ordered = sorted(float(x) for x in starts)
    if not ordered:
        return tuple(lines)
    spans = sorted((float(a), float(b)) for a, b in windows)
    out = []
    for line in lines:
        if line.disabled or not line.syllables:
            out.append(line)
            continue
        if line.bg:
            found = _nearest(ordered, line.start, reach, 0.0, float("inf"))
            if found is None:
                out.append(line)
                continue
            length = max(_LEAST_S, line.end - line.start)
            end = next((b for a, b in spans if a - 0.05 <= found < b),
                       found + length)
            end = min(max(end, found + _LEAST_S), found + 2.0 * length)
            out.append(_reflow(line, found, end))
            continue
        runs = _bg_runs(line)
        if not runs:
            out.append(line)
            continue
        pieces = list(line.syllables)
        for first, last in runs:
            begin = pieces[first].start
            found = _nearest(ordered, begin, piece_reach, 0.0, float("inf"))
            if found is None or abs(found - begin) <= 0.005:
                continue
            delta = found - begin
            for k in range(first, last):
                pieces[k] = replace(pieces[k],
                                    start=round(pieces[k].start + delta, 3),
                                    end=round(pieces[k].end + delta, 3))
        out.append(replace(line, syllables=tuple(pieces)))
    return tuple(out)

