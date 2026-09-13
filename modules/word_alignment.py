"""Forced alignment of words with WhisperX (optional).

Refines the word/time data of the Whisper transcription into much more
precise start/end times per word, with a wav2vec2 alignment model.
Only works if WhisperX is installed and a language is known; otherwise
the ordinary Whisper timing remains in place (a clean fallback).
"""

from __future__ import annotations

import importlib.util
import logging

from .whisper import Segment, Word
from .translations import t

logger = logging.getLogger(__name__)

#: WhisperX works internally at 16 kHz mono.
_WHISPERX_SR = 16_000


def is_available() -> bool:
    """Is WhisperX installed?"""
    return importlib.util.find_spec("whisperx") is not None


def _resample_to(data, sr: int, target_sr: int):
    """Resample ``data`` (1-D float32) from ``sr`` to ``target_sr``.

    Tries librosa first (qualitatively the best), but librosa's resample
    path runs via numba JIT compilation; a broken/incompatible numba
    installation on the user's pc breaks that with an ``AttributeError``
    that has nothing to do with the audio itself (B254). Falls back to
    ``scipy.signal.resample_poly`` (no numba needed; scipy is already a
    core dependency) so that the in-process approach - and thus no
    flashing WhisperX/ffmpeg window - keeps working then too.
    """
    import numpy as np
    try:
        import librosa
        return librosa.resample(data, orig_sr=sr, target_sr=target_sr)
    except Exception:  # noqa: BLE001 - numba/librosa may be broken (B254)
        logger.debug(t("log_librosa_resample_missing"),
                     exc_info=True)
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(int(sr), int(target_sr))
        up, down = int(target_sr) // g, int(sr) // g
        return np.asarray(resample_poly(data, up, down), dtype=np.float32)


def _load_mono_16k(audio_path):
    """Load audio in-process as a mono 16 kHz float32 array.

    This way WhisperX does not have to load the audio itself via an
    ffmpeg subprocess - on Windows that gave a flashing cmd window (B97).
    On an error this returns ``None`` and :func:`refine` falls back to
    the path.
    """
    try:
        import numpy as np
        import soundfile as sf
        data, sr = sf.read(str(audio_path), dtype="float32",
                           always_2d=False)
        if getattr(data, "ndim", 1) > 1:
            data = data.mean(axis=1)
        if sr != _WHISPERX_SR:
            data = _resample_to(data, sr, _WHISPERX_SR)
        return np.ascontiguousarray(data, dtype=np.float32)
    except Exception:  # noqa: BLE001 - fall back to the path
        logger.debug(t("log_preload_failed"))
        return None


def refine(audio_path, segments: tuple[Segment, ...], language: str,
           device: str = "cpu") -> tuple[Segment, ...]:
    """Return segments with refined word times.

    On every error or missing language the original timing is returned
    unchanged.
    """
    if not is_available() or not language or language == "auto":
        return segments
    try:
        import whisperx  # type: ignore

        model_a, metadata = whisperx.load_align_model(
            language_code=language, device=device)
        raw = [{"start": s.start, "end": s.end, "text": s.text}
               for s in segments]
        # Pass the audio in-process (mono 16k ndarray) instead of a path,
        # so that WhisperX starts no ffmpeg subprocess/window (B97).
        audio_input = _load_mono_16k(audio_path)
        if audio_input is None:
            audio_input = str(audio_path)
        result = whisperx.align(raw, model_a, metadata, audio_input,
                                device, return_char_alignments=False)
    except Exception:  # noqa: BLE001 - forced alignment may never break
        logger.exception(t("log_forced_alignment_failed"))
        return segments

    refined: list[Segment] = []
    for index, item in enumerate(result.get("segments", [])):
        base = segments[index] if index < len(segments) else None
        words = tuple(
            Word(text=str(w.get("word", "")).strip(),
                 start=float(w.get("start", base.start if base else 0.0)),
                 end=float(w.get("end", base.end if base else 0.0)),
                 confidence=float(w.get("score", 0.0)))
            for w in item.get("words", []) if "start" in w and "end" in w)
        if not words and base is not None:
            words = base.words
        start = words[0].start if words else (base.start if base else 0.0)
        end = words[-1].end if words else (base.end if base else 0.0)
        refined.append(Segment(index=index,
                               text=str(item.get("text", "")).strip(),
                               start=start, end=end, words=words))
    logger.info(t("log_forced_alignment_applied"), len(refined))
    return tuple(refined) if refined else segments


def warmup(language: str, device: str = "cpu") -> None:
    """Load the alignment model for a language (forces the download)."""
    if not is_available() or not language or language == "auto":
        return
    try:
        import whisperx  # type: ignore
        whisperx.load_align_model(language_code=language, device=device)
    except Exception:  # noqa: BLE001
        logger.exception(t("log_align_model_failed"))
