"""Separations blended into one (v1.0.22, B631).

The owner's wish: blend Demucs with the careful Demucs now, and keep in
mind that it may become a blend of Roformer models later - or of both
Demucs ways with one or more Roformer models, for High performance. So
nothing here knows what it blends: a blend is a list of separations
(:class:`modules.separation.Way`, each a stem set of its own) and a way
to join them, and the stems that every part has are joined one by one.

The ways of joining, the ones the Roformer ensembles of
python-audio-separator use too:

* ``avg_wave`` - the mean of the waveforms, with weights when given.
  The errors of two models that go wrong in different places are
  halved where only one of them goes wrong;
* ``median_wave`` - the median, sample by sample: one model that goes
  badly wrong in a place is outvoted (three parts or more);
* ``max_spec`` - per frequency and moment the part that is loudest
  there: fuller, keeps what one part lost (for a voice);
* ``min_spec`` - the quietest: cleaner, drops what one part let bleed in
  (for a music track).

Every part is brought to the rate, the channels and the length of the
first before joining, so a Roformer stem at another rate can be joined
with a Demucs one. The result is written as 32-bit float, so it keeps
the level of its parts (B597): nothing is scaled, nothing clips.
"""
from __future__ import annotations

import logging
from math import gcd
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .translations import t

logger = logging.getLogger(__name__)

#: How parts can be joined; the first is the default.
ALGORITHMS = ("avg_wave", "median_wave", "max_spec", "min_spec")

#: The frame of the spectral ways: 2048 samples with half of it as the
#: step - a Hann window then adds up to one, so what is not changed
#: comes back as it went in.
_FRAME = 2048
_STEP = 1024


class BlendError(Exception):
    """The parts could not be joined."""


def _load(path: Path) -> tuple[np.ndarray, int]:
    import soundfile

    data, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
    return data, int(rate)


def _resampled(data: np.ndarray, rate: int, target: int) -> np.ndarray:
    """``data`` at ``target`` Hz (polyphase: exact for 48 -> 44.1 kHz)."""
    if rate == target or data.size == 0:
        return data
    from scipy.signal import resample_poly

    common = gcd(int(rate), int(target))
    return resample_poly(data, target // common, rate // common,
                         axis=0).astype(np.float32)


def _shaped(data: np.ndarray, channels: int, length: int) -> np.ndarray:
    """``data`` with ``channels`` channels and ``length`` samples: a mono
    part is laid on every channel, a longer one is cut, a shorter one
    padded with silence."""
    if data.shape[1] != channels:
        if data.shape[1] == 1:
            data = np.repeat(data, channels, axis=1)
        else:
            mono = data.mean(axis=1, keepdims=True)
            data = np.repeat(mono, channels, axis=1)
    if len(data) > length:
        return data[:length]
    if len(data) < length:
        pad = np.zeros((length - len(data), channels), dtype=np.float32)
        return np.concatenate([data, pad])
    return data


def _weights(count: int, weights: Sequence[float] | None) -> np.ndarray:
    if not weights:
        return np.full(count, 1.0 / count)
    values = np.asarray([max(0.0, float(w)) for w in weights][:count])
    if len(values) < count or values.sum() <= 0:
        raise BlendError(t("err_blend_weights").format(count=count))
    return values / values.sum()


def _spectral(parts: Sequence[np.ndarray], loudest: bool) -> np.ndarray:
    """Per frequency and moment the loudest (or quietest) part, one
    channel and one part at a time, so a long song does not hold every
    spectrum at once."""
    from scipy.signal import istft, stft

    length, channels = parts[0].shape
    out = np.zeros((length, channels), dtype=np.float32)
    for channel in range(channels):
        best = None
        best_size = None
        for part in parts:
            _f, _t, spectrum = stft(part[:, channel], nperseg=_FRAME,
                                    noverlap=_FRAME - _STEP,
                                    boundary="even", padded=True)
            spectrum = spectrum.astype(np.complex64)
            size = np.abs(spectrum)
            if best is None:
                best, best_size = spectrum, size
                continue
            better = size > best_size if loudest else size < best_size
            best = np.where(better, spectrum, best)
            best_size = np.where(better, size, best_size)
            del spectrum, size, better
        _t, wave = istft(best, nperseg=_FRAME, noverlap=_FRAME - _STEP,
                         boundary=True)
        wave = np.asarray(wave, dtype=np.float32)[:length]
        out[:len(wave), channel] = wave
    return out


def join(parts: Sequence[np.ndarray], algorithm: str = "avg_wave",
         weights: Sequence[float] | None = None) -> np.ndarray:
    """Join stems of the same shape ``(samples, channels)`` into one."""
    if not parts:
        raise BlendError(t("err_blend_no_parts"))
    algorithm = algorithm or ALGORITHMS[0]
    if algorithm not in ALGORITHMS:
        raise BlendError(t("err_blend_algorithm").format(name=algorithm))
    if len(parts) == 1:
        return np.asarray(parts[0], dtype=np.float32)
    if algorithm == "avg_wave":
        share = _weights(len(parts), weights)
        out = np.zeros_like(parts[0], dtype=np.float32)
        for weight, part in zip(share, parts):
            out += np.float32(weight) * part
        return out
    if algorithm == "median_wave":
        return np.median(np.stack(parts), axis=0).astype(np.float32)
    return _spectral(parts, loudest=algorithm == "max_spec")


#: v1.0.28 (B667): ``<algorithm>+repair`` - and then where the joined
#: music falls this far below the loudest part while that part plays,
#: the music is taken from that part there, at its own (the original's)
#: level: an average halves what one model kept and another dropped.
REPAIR = "+repair"
REPAIR_DB = 6.0
_REPAIR_FRAME_S = 0.25
_REPAIR_FADE_S = 0.05
#: A part counts as playing within this of its own median level.
_REPAIR_PLAYING_DB = 15.0


def _frame_db(data: np.ndarray, size: int) -> np.ndarray:
    mono = data.mean(axis=1) if data.ndim == 2 else data
    count = len(mono) // size
    if count == 0:
        return np.zeros(0)
    frames = mono[:count * size].reshape(count, size).astype(np.float64)
    return 20.0 * np.log10(np.maximum(np.sqrt(np.mean(frames ** 2, axis=1)),
                                      1e-7))


def repair_dips(joined: np.ndarray, parts: Sequence[np.ndarray],
                rate: int) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """B667: the joined music with its dips filled from the part that
    kept the music there. Returns the music and the spans repaired, in
    seconds."""
    if len(parts) < 2 or not len(joined):
        return joined, []
    size = max(1, int(rate * _REPAIR_FRAME_S))
    own = _frame_db(joined, size)
    levels = np.stack([_frame_db(part, size) for part in parts])
    if not own.size:
        return joined, []
    best = levels.argmax(axis=0)
    loudest = levels.max(axis=0)
    playing = loudest > float(np.median(loudest)) - _REPAIR_PLAYING_DB
    dip = playing & (own < loudest - REPAIR_DB)
    spans: list[tuple[int, int]] = []
    frame = 0
    while frame < len(dip):
        if not dip[frame]:
            frame += 1
            continue
        start = frame
        while frame < len(dip) and dip[frame]:
            frame += 1
        spans.append((start, frame))
    if not spans:
        return joined, []
    out = np.array(joined, dtype=np.float32, copy=True)
    fade = max(1, int(rate * _REPAIR_FADE_S))
    found = []
    for start, end in spans:
        source = parts[int(np.bincount(best[start:end]).argmax())]
        low, high = start * size, min(len(out), end * size)
        ramp_low, ramp_high = max(0, low - fade), min(len(out), high + fade)
        weight = np.zeros(ramp_high - ramp_low, dtype=np.float32)
        weight[low - ramp_low:high - ramp_low] = 1.0
        if low > ramp_low:
            weight[:low - ramp_low] = np.linspace(0.0, 1.0, low - ramp_low,
                                                  endpoint=False)
        if ramp_high > high:
            weight[high - ramp_low:] = np.linspace(1.0, 0.0,
                                                   ramp_high - high)
        if out.ndim == 2:
            weight = weight[:, None]
        piece = out[ramp_low:ramp_high]
        out[ramp_low:ramp_high] = piece * (1.0 - weight) + \
            source[ramp_low:ramp_high] * weight
        found.append((round(low / rate, 2), round(high / rate, 2)))
    return out, found


def common_stems(stem_sets: Sequence[Mapping[str, Path]]) -> list[str]:
    """The stems every part has, voice and music first."""
    names = set(stem_sets[0]) if stem_sets else set()
    for stems in stem_sets[1:]:
        names &= set(stems)
    first = [name for name in ("vocals", "instrumental") if name in names]
    return first + sorted(names - set(first))


def blend_files(stem_sets: Sequence[Mapping[str, Path]], out_dir: Path,
                algorithm: str = "avg_wave",
                weights: Sequence[float] | None = None) -> dict[str, Path]:
    """Join the stems of several separations; every stem all of them
    have becomes one file in ``out_dir``. Returns ``{name: path}``.

    Raises:
        BlendError: With no parts, or without a voice and a music track
            in every part.
    """
    import soundfile

    if not stem_sets:
        raise BlendError(t("err_blend_no_parts"))
    algorithm = algorithm or ALGORITHMS[0]
    repair = algorithm.endswith(REPAIR)
    if repair:
        algorithm = algorithm[:-len(REPAIR)]
    names = common_stems(stem_sets)
    if "vocals" not in names or "instrumental" not in names:
        raise BlendError(t("err_blend_no_stems"))
    out_dir.mkdir(parents=True, exist_ok=True)
    made: dict[str, Path] = {}
    for name in names:
        first, rate = _load(Path(stem_sets[0][name]))
        channels, length = first.shape[1], len(first)
        parts = [first]
        for stems in stem_sets[1:]:
            data, own_rate = _load(Path(stems[name]))
            data = _resampled(data, own_rate, rate)
            parts.append(_shaped(data, channels, length))
        joined = join(parts, algorithm, weights)
        if repair and name == "instrumental":
            joined, spans = repair_dips(joined, parts, rate)
            if spans:
                logger.info(t("log_blend_repaired"), len(spans),
                            sum(high - low for low, high in spans))
        del parts
        target = out_dir / f"{name}.wav"
        soundfile.write(str(target), joined, rate, subtype="FLOAT")
        made[name] = target
    logger.info(t("log_blend_done"), len(stem_sets), algorithm, len(made))
    return made
