"""Tests voor modules.audio."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from modules.audio import (
    AudioError,
    db_to_amplitude,
    duration_seconds,
    load_audio,
    save_wav,
    seconds_to_samples,
)


def test_db_to_amplitude() -> None:
    assert db_to_amplitude(0) == pytest.approx(1.0)
    assert db_to_amplitude(-20) == pytest.approx(0.1)
    assert db_to_amplitude(-25) == pytest.approx(0.0562, abs=1e-4)


def test_duration_and_samples() -> None:
    data = np.zeros((44100, 2), dtype=np.float32)
    assert duration_seconds(data, 44100) == pytest.approx(1.0)
    assert seconds_to_samples(1.5, 44100) == 66150


def test_duration_invalid_rate() -> None:
    with pytest.raises(AudioError):
        duration_seconds(np.zeros((10, 1), dtype=np.float32), 0)


def test_wav_roundtrip(tmp_path: Path) -> None:
    sample_rate = 22050
    time = np.linspace(0, 1, sample_rate, dtype=np.float32)
    signal = 0.5 * np.sin(2 * np.pi * 440 * time)
    data = np.stack([signal, signal], axis=1)

    path = tmp_path / "toon.wav"
    save_wav(path, data, sample_rate)
    loaded, loaded_rate = load_audio(path)

    assert loaded_rate == sample_rate
    assert loaded.shape == data.shape
    # 16-bit kwantisatie geeft een kleine afwijking.
    assert np.max(np.abs(loaded - data)) < 1e-3


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises((AudioError, Exception)):
        load_audio(tmp_path / "bestaat_niet.wav")
