"""Tests voor modules.woorduitlijning (forced alignment, B97)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from modules import word_alignment
from modules.audio import save_wav


def test_load_mono_16k_converteert(tmp_path: Path) -> None:
    """B97: audio wordt in-process mono 16 kHz float32 (geen ffmpeg-venster)."""
    pytest.importorskip("librosa", exc_type=ImportError)
    sr = 44_100
    tone = (0.3 * np.sin(2 * np.pi * 220 *
                         np.arange(sr) / sr)).astype(np.float32)
    stereo = np.stack([tone, tone], axis=1)
    path = tmp_path / "audio.wav"
    save_wav(path, stereo, sr)

    data = word_alignment._load_mono_16k(path)
    assert data is not None
    assert data.ndim == 1                       # mono
    assert data.dtype == np.float32
    # ~1 seconde audio -> ~16000 samples na resampling naar 16 kHz.
    assert abs(len(data) - word_alignment._WHISPERX_SR) < 200


def test_load_mono_16k_terugval_bij_fout(tmp_path: Path) -> None:
    """B97: een onleesbaar bestand geeft None (refine valt terug op het pad)."""
    assert word_alignment._load_mono_16k(tmp_path / "bestaat_niet.wav") is None


def test_refine_zonder_whisperx_ongewijzigd() -> None:
    """Zonder WhisperX/taal blijft de timing ongewijzigd (nette terugval)."""
    from modules.whisper import Segment, Word
    segs = (Segment(0, "oe", 0.5, 1.0, (Word("oe", 0.5, 1.0, 0.9),)),)
    assert word_alignment.refine("x.wav", segs, "auto") == segs
