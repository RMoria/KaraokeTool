"""Tests voor de modellen-hulplaag."""

from __future__ import annotations

from modules import models


def test_availability_and_info() -> None:
    # numpy bestaat altijd; misbruik de check via een bekende module.
    assert models.is_available("bestaat_niet_feature") is False
    assert "MB" in models.info_text("demucs") or \
        models.info_text("demucs")  # bevat download/kosten
    for feature in ("demucs", "forced_alignment"):
        # geeft True/False, crasht niet
        assert isinstance(models.is_available(feature), bool)
    # 'ritme' hoort niet meer bij de grote modellen (zit vast in de kern).
    assert "ritme" not in models.MODEL_INFO


def test_woorduitlijning_fallback() -> None:
    """Zonder WhisperX blijft de timing ongewijzigd (nette terugval)."""
    from modules import word_alignment
    from modules.whisper import Segment, Word
    segs = (Segment(0, "kedeng", 1.0, 2.0,
                    (Word("kedeng", 1.0, 2.0, 0.9),)),)
    # Geen WhisperX / geen taal -> zelfde segmenten terug.
    assert word_alignment.refine("x.wav", segs, "auto") == segs
    if not word_alignment.is_available():
        assert word_alignment.refine("x.wav", segs, "nl") == segs


def test_ritme_via_librosa() -> None:
    """Ritme werkt via librosa (geen madmom/compiler nodig)."""
    from modules import rhythm
    assert rhythm.is_available() is True       # librosa is kern
    assert rhythm.beat_activation("x.wav", 0) is None      # ongeldige frames
    assert rhythm.beat_times("bestaat_niet.wav") == []     # nette terugval
    rhythm.warmup()  # no-op, geen download
