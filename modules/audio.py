"""Audio helper functions: loading, saving and simple operations.

All audio is processed internally as a float32 numpy array with shape
``(samples, channels)``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import soundfile as sf
from .translations import t

logger = logging.getLogger(__name__)


class AudioError(Exception):
    """Error while loading or saving audio."""


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    """Load an audio file as a float32 array.

    Args:
        path: Path to the file (wav is recommended).

    Returns:
        Tuple of (samples with shape ``(n, channels)``, sample rate).

    Raises:
        AudioError: If the file cannot be read.
    """
    try:
        data, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    except (RuntimeError, sf.LibsndfileError) as exc:
        raise AudioError(t("err_audio_load").format(path=path)) from exc
    logger.debug(t("log_audio_loaded"),
                 path.name, data.shape[0], sample_rate, data.shape[1])
    return data, int(sample_rate)


def save_wav(path: Path, data: np.ndarray, sample_rate: int) -> None:
    """Save audio as 16-bit PCM wav.

    Args:
        path: Target path.
        data: Samples with shape ``(n, channels)`` or ``(n,)``.
        sample_rate: Sample rate in Hz.

    Raises:
        AudioError: If the file cannot be written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        sf.write(path, data, sample_rate, subtype="PCM_16")
    except (RuntimeError, sf.LibsndfileError) as exc:
        raise AudioError(t("err_audio_save").format(path=path)) from exc
    logger.info(t("log_wav_saved"), path)


def db_to_amplitude(db: float) -> float:
    """Convert decibels into a linear amplitude factor.

    Example: ``db_to_amplitude(-20) == 0.1``.
    """
    return float(10.0 ** (db / 20.0))


def duration_seconds(data: np.ndarray, sample_rate: int) -> float:
    """Calculate the duration of an audio fragment in seconds."""
    if sample_rate <= 0:
        raise AudioError(t("err_audio_positive_rate"))
    return data.shape[0] / float(sample_rate)


def seconds_to_samples(seconds: float, sample_rate: int) -> int:
    """Convert a time in seconds into a sample index."""
    return int(round(seconds * sample_rate))
