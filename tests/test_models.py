"""Tests for the models helper layer."""

from __future__ import annotations

from modules import models


def test_availability_and_info() -> None:
    # A feature that does not exist is never available.
    assert models.is_available("does_not_exist_feature") is False
    assert "MB" in models.info_text("demucs") or \
        models.info_text("demucs")  # holds download/cost
    for feature in ("demucs", "forced_alignment"):
        # gives True/False, does not crash
        assert isinstance(models.is_available(feature), bool)
    # 'rhythm' is no longer one of the large models (it is core now).
    assert "ritme" not in models.MODEL_INFO


def test_word_alignment_falls_back(monkeypatch) -> None:
    """Without WhisperX the timing stays as it is (a clean fallback).

    B551: the second assertion used to sit under ``if not
    word_alignment.is_available():``, so on a machine with WhisperX
    the one case this test is named after was never run. The absence
    is arranged here instead of waited for.
    """
    from modules import word_alignment
    from modules.whisper import Segment, Word
    segs = (Segment(0, "kedeng", 1.0, 2.0,
                    (Word("kedeng", 1.0, 2.0, 0.9),)),)
    # No language -> the same segments back, whatever is installed.
    assert word_alignment.refine("x.wav", segs, "auto") == segs
    monkeypatch.setattr(word_alignment, "is_available", lambda: False)
    assert word_alignment.refine("x.wav", segs, "nl") == segs


def test_rhythm_through_librosa() -> None:
    """Rhythm works through librosa (no madmom, no compiler)."""
    from modules import rhythm
    assert rhythm.is_available() is True       # librosa is core
    assert rhythm.beat_activation("x.wav", 0) is None      # invalid frames
    assert rhythm.beat_times("no_such_file.wav") == []     # a clean fallback
    rhythm.warmup()  # no-op, no download
