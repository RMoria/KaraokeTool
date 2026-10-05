"""How long the long steps usually take, to say how long they still will
(v1.0.20).

Ordinary work showed only how long a step had been busy. For a step
with a real progress bar (Whisper, the render) the window now works out
from the bar how long is left. A separation has no bar - Demucs and
Roformer run as programs of their own - so there the time comes from
the previous times: per kind of step (the way of separating), the
seconds it took per second of audio, kept in ``config/step_times.json``.
The first time nothing is known and nothing is said; every time after
that the estimate learns.

Only the program's own window reads :func:`current_left`; the file is
written after every step that took long enough to say something.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path

#: Steps shorter than this say nothing about the work (a cache hit).
QUICK_S = 2.0

_FILE: Path | None = None
_LOCK = threading.Lock()
#: The step running now: ``(started, expected seconds)``.
_CURRENT: tuple[float, float] | None = None


def use_file(path: Path | None) -> None:
    global _FILE
    _FILE = Path(path) if path else None


def _read() -> dict:
    if _FILE is None:
        return {}
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def expected(kind: str, audio_s: float) -> float | None:
    """What a step of this kind usually takes for this much audio."""
    entry = _read().get(kind)
    try:
        rate, count = float(entry[0]), int(entry[1])
    except (TypeError, ValueError, IndexError):
        return None
    if count <= 0 or audio_s <= 0:
        return None
    return rate * float(audio_s)


def note(kind: str, audio_s: float, seconds: float) -> None:
    """A step of this kind took ``seconds`` for ``audio_s`` of audio. The
    rate is a running mean over the last times (the newest counts most
    while there are few)."""
    if _FILE is None or audio_s <= 0 or seconds < QUICK_S:
        return
    with _LOCK:
        data = _read()
        rate = seconds / float(audio_s)
        entry = data.get(kind)
        try:
            old, count = float(entry[0]), int(entry[1])
        except (TypeError, ValueError, IndexError):
            old, count = rate, 0
        count = min(count + 1, 10)
        data[kind] = [round(old + (rate - old) / count, 5), count]
        try:
            _FILE.parent.mkdir(parents=True, exist_ok=True)
            _FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")
        except OSError:
            pass


@contextmanager
def timed(kind: str, audio_s: float):
    """Time a step; while it runs, :func:`current_left` knows about it."""
    global _CURRENT
    began = time.monotonic()
    guess = expected(kind, audio_s)
    previous = _CURRENT
    _CURRENT = (began, guess) if guess is not None else None
    try:
        yield
    finally:
        _CURRENT = previous
    note(kind, audio_s, time.monotonic() - began)


def current_left() -> float | None:
    """Seconds the running step will still take, or ``None``."""
    now = _CURRENT
    if now is None:
        return None
    return max(0.0, now[1] - (time.monotonic() - now[0]))


def left_from_progress(done: float, total: float,
                       busy_s: float) -> float | None:
    """From a progress bar: ``busy_s`` for ``done`` of ``total``. Nothing
    under 3 %, where the start-up cost still dominates."""
    if total <= 0 or done <= 0 or busy_s <= 0:
        return None
    share = min(1.0, done / total)
    if share < 0.03:
        return None
    return busy_s * (1.0 - share) / share


def audio_seconds(path: Path) -> float:
    """The length of an audio file, or 0 when it cannot be told."""
    try:
        import soundfile

        return float(soundfile.info(str(path)).duration)
    except Exception:  # noqa: BLE001 - an mp3 soundfile cannot read, say
        pass
    try:
        from . import ffmpeg

        return float(ffmpeg.probe(Path(path)).duration)
    except Exception:  # noqa: BLE001
        return 0.0
