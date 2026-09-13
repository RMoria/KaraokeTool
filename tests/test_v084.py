"""Tests voor v0.84.0-fixes (B254 forced-alignment-venster, B256
RMS-omhullende-cache, B257/B260 crowd-koppeling in een gemengd blok, B258
hallucinatie-varianten met een functiewoord)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


# --------------------------------------------------------------------------
# B256 - RMS-omhullende: faalresultaat wordt gecachet (geen herhaalde
# identieke dure/kapotte librosa-aanroepen + stacktraces per regel/zin).
# --------------------------------------------------------------------------
def test_rms_envelope_caches_failure(monkeypatch, tmp_path: Path) -> None:
    from modules import rhythm

    rhythm._ENV_CACHE.clear()
    rhythm._ENV_FAILED_LOGGED.clear()
    monkeypatch.setattr(rhythm, "is_available", lambda: True)

    audio = tmp_path / "kapot.wav"
    audio.write_bytes(b"niet echt audio")

    calls = {"n": 0}

    class _KapotteLibrosa:
        def load(self, *_a, **_kw):
            calls["n"] += 1
            raise AttributeError("module 'numba' has no attribute 'core'")

    import sys
    monkeypatch.setitem(sys.modules, "librosa", _KapotteLibrosa())

    first = rhythm._rms_envelope(audio)
    tweede = rhythm._rms_envelope(audio)
    derde = rhythm._rms_envelope(audio)

    assert first is None and tweede is None and derde is None
    # Zonder de fix zou elke aanroep librosa.load opnieuw proberen (n == 3).
    assert calls["n"] == 1
    # Het faalresultaat zit expliciet (als None) in de cache, niet alleen
    # "afwezig" - anders is er geen onderscheid met "nog niet geprobeerd".
    key = next(iter(rhythm._ENV_CACHE))
    assert rhythm._ENV_CACHE[key] is None


def test_rms_envelope_failure_logged_once(monkeypatch, tmp_path: Path,
                                          caplog) -> None:
    from modules import rhythm

    rhythm._ENV_CACHE.clear()
    rhythm._ENV_FAILED_LOGGED.clear()
    monkeypatch.setattr(rhythm, "is_available", lambda: True)
    audio = tmp_path / "kapot2.wav"
    audio.write_bytes(b"x")

    class _KapotteLibrosa:
        def load(self, *_a, **_kw):
            raise RuntimeError("kapot")

    import sys
    monkeypatch.setitem(sys.modules, "librosa", _KapotteLibrosa())

    with caplog.at_level("ERROR", logger="modules.rhythm"):
        rhythm._rms_envelope(audio)
        rhythm._rms_envelope(audio)
        rhythm._rms_envelope(audio)

    messages = [r for r in caplog.records
                if "RMS-omhullende bepalen mislukt" in r.message]
    assert len(messages) == 1


# --------------------------------------------------------------------------
# B254 - forced alignment: resample valt terug op scipy als librosa (numba)
# kapot is, zodat de audio toch in-process geladen wordt (geen WhisperX-
# ffmpeg-venster).
# --------------------------------------------------------------------------
def test_resample_valt_terug_op_scipy_bij_kapotte_librosa(monkeypatch) -> None:
    from modules import word_alignment

    class _KapotteLibrosa:
        def resample(self, *_a, **_kw):
            raise AttributeError("module 'numba' has no attribute 'core'")

    import sys
    monkeypatch.setitem(sys.modules, "librosa", _KapotteLibrosa())

    sr = 44_100
    target = 16_000
    tone = (0.3 * np.sin(2 * np.pi * 220 *
                         np.arange(sr) / sr)).astype(np.float32)
    out = word_alignment._resample_to(tone, sr, target)
    assert out is not None
    # ~1 s audio -> ~16000 samples na resampling.
    assert abs(len(out) - target) < 200


def test_load_mono_16k_werkt_ook_als_librosa_resample_kapot_is(
        monkeypatch, tmp_path: Path) -> None:
    pytest.importorskip("soundfile", exc_type=ImportError)
    from modules import word_alignment
    from modules.audio import save_wav

    sr = 44_100
    tone = (0.3 * np.sin(2 * np.pi * 220 *
                         np.arange(sr) / sr)).astype(np.float32)
    path = tmp_path / "audio.wav"
    save_wav(path, tone.reshape(-1, 1), sr)

    monkeypatch.setattr(word_alignment, "_resample_to",
                        lambda data, sr, target_sr: (_ for _ in ()).throw(
                            AttributeError("numba kapot")))

    # _load_mono_16k vangt de fout van _resample_to zelf op (nette terugval
    # op het pad); dit bevestigt dat een kapotte resample niet crasht maar
    # nette None teruggeeft in plaats van een uitzondering te propageren.
    data = word_alignment._load_mono_16k(path)
    assert data is None


# --------------------------------------------------------------------------
# B260 - crowd-regels in een gemengd blok koppelen 1-op-1 aan de songtekst
# zodra het aantal regels (crowd inbegrepen) precies overeenkomt, i.p.v.
# altijd als los "tussenroepje" te eindigen. Reproduceert "Lied B
# ": blok met 2 crowd- + 3 zangregels tegenover 5 songtekstregels.
# --------------------------------------------------------------------------
def test_couple_crowd_counts_when_block_sizes_match() -> None:
    """B260: 5 karaokeregels (2 crowd + 3 zang) tegen 5 songtekstregels
    koppelen 1-op-1 - ook de crowd-regels, i.p.v. als tussenroepje."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[
        TextLine(0, "De Rood Wit-te Zangers...", True, block=0),
        TextLine(1, "Ik zeg rot hier nu maar op.", False, block=0),
        TextLine(2, "De Rood Wit-te Zangers...", True, block=0),
        TextLine(3, "Ik zeg vrienden, ga maar,", False, block=0),
        TextLine(4, "Het bier is op.", False, block=0),
    ]]
    ob = [[
        (10.0, 12.0, True),   # "Met bloed, zweet en tranen"
        (12.0, 14.0, True),   # "zei ik rot hier nu maar op"
        (14.0, 16.0, True),   # "met bloed, zweet en tranen"
        (16.0, 18.0, True),   # "zei ik vrienden dag vrienden"
        (18.0, 20.0, True),   # "de koek is op"
    ]]
    timed, quality, mapping = couple_timing(kb, ob)
    by = {t.index: t for t in timed}

    # Alle 5 regels zitten in de mapping (dus echt 1-op-1 gekoppeld),
    # inclusief de twee crowd-regels (index 0 en 2).
    assert set(mapping) == {0, 1, 2, 3, 4}
    assert mapping[0] == 0 and mapping[2] == 2

    # De crowd-regel staat op de tijd van ZIJN songtekstregel, niet op een
    # kort tussenroep-slotje na de vorige regel.
    assert by[0].crowd is True
    assert by[0].start == pytest.approx(10.0)
    assert by[0].end == pytest.approx(12.0)
    assert by[2].crowd is True
    assert by[2].start == pytest.approx(14.0)
    assert by[2].end == pytest.approx(16.0)

    # Alles hoog vertrouwen (1-op-1, betrouwbare originele spans).
    assert quality == {"high": 5, "medium": 0, "low": 0}
    # Geen enkele regel liep via het tussenroepje-pad (dat zou "medium"
    # opleveren met een 0.8s-slotje i.p.v. de echte 2s-songtekstspan).
    assert all(round(by[i].end - by[i].start, 3) == 2.0 for i in range(5))


def test_couple_crowd_interjection_still_short_when_counts_differ() -> None:
    """Blijft bestaand gedrag: matchen de aantallen niet, dan blijft een
    losse crowd-regel een kort tussenroepje (bv. publieks-'Oeh!')."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "G Z R", False, block=0),
          TextLine(1, "Oeh!", True, block=0)]]
    ob = [[(5.0, 7.0, True)]]          # 1 songtekstregel, 2 karaokeregels
    timed, _, mapping = couple_timing(kb, ob)
    by = {t.index: t for t in timed}
    assert by[1].crowd is True and by[1].crowd_section is False
    # B472: de TIMING blijft een kort tussenroepje, maar de regel krijgt
    # wel een koppeling naar de originele zin waar hij achteraan komt -
    # zonder koppeling is hij in de editor niet te plaatsen.
    assert mapping[1] == 0


def test_couple_crowd_matches_original_view_cells_have_no_duplicate() -> None:
    """B257: zodra de crowd-regel via B260 netjes koppelt, hoort hij niet
    meer als losse/verdwaalde cel in de originele-baan te verschijnen -
    de kar_index zit dan gewoon in de normale koppeling."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[
        TextLine(0, "Crowd-regel", True, block=0),
        TextLine(1, "Zangregel", False, block=0),
    ]]
    ob = [[(0.0, 2.0, True), (2.0, 4.0, True)]]
    _, _, mapping = couple_timing(kb, ob)
    # Beide karaoke-indices zitten in de mapping (dus 'gekoppeld' in
    # gui.py's mirror-logica) - er is geen crowd-regel meer die als
    # "geen songtekst-equivalent" behandeld wordt.
    assert set(mapping) == {0, 1}


# --------------------------------------------------------------------------
# B257 - gespiegelde crowd-regel (voor het overblijvende, écht-ongekoppelde
# geval) is herkenbaar als zodanig; crowd-vlag reist mee door
# original_view_cells in alle drie de weergaven.
# --------------------------------------------------------------------------
def test_original_view_cells_marks_mirrored_crowd() -> None:
    from modules.timing import original_view_cells

    originals = [
        {"text": "Een echte originele zin", "start": 0.0, "end": 2.0,
         "rows": [0], "crowd": False},
        {"text": "Oeh!", "start": 2.0, "end": 2.8,
         "rows": [1], "crowd": True},
    ]
    cellen = original_view_cells(originals, "sentences")
    assert cellen[0]["crowd"] is False
    assert cellen[1]["crowd"] is True


def test_original_view_cells_woorden_mode_propagates_crowd() -> None:
    from modules.timing import original_view_cells

    originals = [
        {"text": "Oeh Oeh", "start": 0.0, "end": 2.0,
         "rows": [0], "crowd": True},
    ]
    cellen = original_view_cells(originals, "words")
    assert cellen and all(c["crowd"] for c in cellen)


def test_original_view_cells_blokken_mode_all_crowd_is_crowd() -> None:
    from modules.timing import original_view_cells

    originals = [
        {"text": "Regel een", "start": 0.0, "end": 1.0, "rows": [0],
         "crowd": True},
        {"text": "Regel twee", "start": 1.0, "end": 2.0, "rows": [1],
         "crowd": True},
    ]
    cellen = original_view_cells(originals, "blocks", {0: 0, 1: 0})
    assert len(cellen) == 1
    assert cellen[0]["crowd"] is True


def test_original_view_cells_missing_crowd_defaults_false() -> None:
    """Achterwaartse compatibiliteit: dicts zonder "crowd" -> False."""
    from modules.timing import original_view_cells

    originals = [{"text": "Oud formaat", "start": 0.0, "end": 1.0,
                 "rows": [0]}]
    cellen = original_view_cells(originals, "sentences")
    assert cellen[0]["crowd"] is False


# --------------------------------------------------------------------------
# B258 - "ZANG EN MUZIEK"-hallucinatie: een functiewoord ("en") plakt twee
# hallucinatiewoorden aan elkaar, waardoor het hele segment niet meer
# volledig uit bekende HALLUCINATIONS-woorden bestaat en overleefde
# (reproductie uit de diagnostiek van "Lied B"). "zang" telt
# alleen als hallucinatiesignaal als het ook niet ergens in de songtekst
# van dit lied voorkomt - anders zou een lied dat het woord "zang" echt
# bezingt dat woord kwijtraken.
# --------------------------------------------------------------------------
def test_filter_hallucinations_zang_en_muziek() -> None:
    """B258: 'ZANG EN MUZIEK' (functiewoord 'en' ertussen) wordt net als
    los 'MUZIEK' (B141) uit de koppeling gefilterd als "zang" nergens in
    de songtekst van dit lied voorkomt."""
    from modules import pipeline
    from modules.song_text import LyricWord
    from modules.whisper import Segment, Word

    segs = (
        Segment(0, "ZANG EN MUZIEK", 229.88, 241.04, (
            Word("ZANG", 229.88, 231.28, 0.42),
            Word("EN", 231.28, 232.68, 0.99),
            Word("MUZIEK", 232.68, 241.04, 0.98),
        )),
        Segment(1, "Bertus op zien Norton", 120.1, 123.4,
                (Word("Bertus", 120.1, 120.6, 0.9),
                 Word("op", 120.6, 120.8, 0.9))),
    )
    # Songtekst van "Lied B" bevat geen "zang"/"muziek".
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "Ik heb veel bier getapt maar ook veel bier gemorst".split()))
    kept = pipeline._filter_hallucinations(segs, lyrics)
    assert len(kept) == 1
    assert kept[0].text == "Bertus op zien Norton"


def test_filter_hallucinations_without_lyrics_still_filters() -> None:
    """Zonder songtekst (lyrics=None, bv. bij het oude call-pad) blijft
    'zang' meetellen als signaalwoord - geen songtekst betekent geen
    context om het woord te sparen."""
    from modules import pipeline
    from modules.whisper import Segment, Word

    segs = (
        Segment(0, "ZANG EN MUZIEK", 229.88, 241.04, (
            Word("ZANG", 229.88, 231.28, 0.42),
            Word("EN", 231.28, 232.68, 0.99),
            Word("MUZIEK", 232.68, 241.04, 0.98),
        )),
    )
    kept = pipeline._filter_hallucinations(segs)
    assert len(kept) == 0


def test_filter_hallucinations_spares_zang_when_in_lyrics() -> None:
    """Kern van B258: staat "zang" wél (fonetisch) in de songtekst van dit
    lied, dan mag het segment NIET als hallucinatie worden weggegooid -
    het kan een echt gezongen woord zijn op dat moment."""
    from modules import pipeline
    from modules.song_text import LyricWord
    from modules.whisper import Segment, Word

    segs = (
        Segment(0, "Zang en muziek", 50.0, 52.0, (
            Word("Zang", 50.0, 50.5, 0.9),
            Word("en", 50.5, 50.7, 0.9),
            Word("muziek", 50.7, 52.0, 0.9),
        )),
    )
    # Deze songtekst bezingt "zang" letterlijk.
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "Wat een mooie zang klinkt hier".split()))
    kept = pipeline._filter_hallucinations(segs, lyrics)
    assert len(kept) == 1
    assert kept[0].text == "Zang en muziek"


def test_filter_hallucinations_still_needs_real_hallucination_word() -> None:
    """Een segment met alleen functiewoorden + een niet-hallucinatiewoord
    ('zang' alleen telt niet als alleen 'zang' erin staat zonder
    'muziek'/'ondertiteling') overleeft niet zomaar minder streng: dit is
    de negatieve controle dat 'zang' alléén niets filtert dat het niet al
    filterde, alleen de combinatie met een echt HALLUCINATIONS-woord."""
    from modules import pipeline
    from modules.whisper import Segment, Word

    # "Zang en dans" - "dans" is geen hallucinatiewoord, dus dit segment
    # moet OVERLEVEN (dit is echte tekst, geen instrumentale hallucinatie).
    segs = (
        Segment(0, "Zang en dans", 10.0, 12.0, (
            Word("Zang", 10.0, 10.5, 0.9),
            Word("en", 10.5, 10.7, 0.9),
            Word("dans", 10.7, 12.0, 0.9),
        )),
    )
    kept = pipeline._filter_hallucinations(segs)
    assert len(kept) == 1
    assert kept[0].text == "Zang en dans"


def test_filter_hallucinations_pure_muziek_still_filtered() -> None:
    """B141 blijft werken: los 'MUZIEK' wordt nog steeds gefilterd, ook met
    een songtekst die het woord niet bevat - MUZIEK/ondertiteling-achtige
    generieke Whisper-artefacten blijven altijd hallucinatie, ongeacht de
    songtekst (alleen de aparte 'zang'-signaalwoordenlijst wordt tegen de
    songtekst getoetst)."""
    from modules import pipeline
    from modules.song_text import LyricWord
    from modules.whisper import Segment, Word

    segs = (Segment(0, "MUZIEK", 28.6, 29.0,
                    (Word("MUZIEK", 28.6, 29.0, 0.5),)),)
    lyrics = (LyricWord(0, "muziek", 0),)   # zelfs als songtekst 'muziek' bevat
    kept = pipeline._filter_hallucinations(segs, lyrics)
    assert len(kept) == 0
