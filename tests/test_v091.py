"""Tests voor v0.91.0-fixes.

B274: songtekstwoorden die puur uit cijfers bestaan (bv. "500", "1000")
kregen een lege fonetische sleutel en konden daardoor nooit koppelen aan
Whisper's transcriptie, ook niet als Whisper het getal (in het Nederlands
of Engels) voluit schreef. Nu wordt zo'n woord vergeleken via zijn
voluit-vorm in beide talen, en wint de vorm met de beste gelijkenis.
Ondersteunt 0 t/m 999.999.999.

B275: de titelvelden (Karaoketitel/artiest/titel) bewaarden pas bij
``editingFinished``, dat niet altijd betrouwbaar afvuurde vóórdat een
stap-knop (Detecteren/Koppelen/...) de context alweer las. Elke
stap-handler dwingt nu eerst de focus van een actief invoerveld af.

B276: vulwoorden (oh, da-da-da) werden altijd overgeslagen in de
songtekst-uitlijning, ook als Whisper ze wél had getranscribeerd. Nu
krijgen ze eerst een matchpoging binnen het ankervenster van hun
buren; alleen zonder goede match vallen ze terug op het oude gedrag.

B277 (eerste versie, zie tests/test_v092.py voor de herziening):
``held_note_end``/``active_end`` toetsten de zangenergie op een enkel
steekpunt; een eerste poging gebruikte een ~0.1s glijdend gemiddelde.

B278: de Karaokevideo-tab had geen eigen voortgangsbalk; die is er nu
en spiegelt dezelfde voortgang als het Audio-tabblad.

B279: karaoke-lettergrepen werden in één platte pas over de totale
originele-woorden-tijdlijn geresampled, puur op relatieve positie -
een kort karaoke-woord kon zo toevallig de duur van een lang
aangehouden origineel woord overerven. Nu worden eerst karaoke-WOORDEN
op originele woorden geprojecteerd, en pas daarna de lettergrepen
binnen dat woordpaar verdeeld.
"""
from __future__ import annotations

from modules.cluster import (is_pure_number, number_key_best_match,
                             number_word_forms, phonetic_key, similarity)
from modules.song_text import LyricWord, align_lyrics, is_filler_word
from modules.whisper import Segment, Word


# -- B274 --------------------------------------------------------------

def test_number_word_forms_basis() -> None:
    assert number_word_forms(500) == ("vijfhonderd", "five hundred")
    assert number_word_forms(0) == ("nul", "zero")
    assert number_word_forms(1000) == ("duizend", "one thousand")


def test_number_word_forms_grens_999_999_999() -> None:
    assert number_word_forms(999_999_999) != ()
    assert number_word_forms(1_000_000_000) == ()
    assert number_word_forms(-1) == ()


def test_is_pure_number() -> None:
    assert is_pure_number("500")
    assert is_pure_number("5.000")   # duizendtal-punten toegestaan
    assert not is_pure_number("500km")
    assert not is_pure_number("vijfhonderd")


def test_phonetic_key_cijferwoord_gebruikt_voluit_vorm() -> None:
    # "500" krijgt zonder B274 een lege sleutel (alleen letters blijven
    # over); nu wordt de NL-voluit-vorm gebruikt.
    assert phonetic_key("500") != ""
    assert phonetic_key("500") == phonetic_key("vijfhonderd")


def test_number_key_best_match_kiest_beste_taal() -> None:
    engels = phonetic_key("five hundred")
    best = number_key_best_match("500", engels)
    assert similarity(best, engels) == 1.0


def test_align_lyrics_koppelt_cijferwoord_aan_voluit_engels() -> None:
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        ["But", "I", "would", "walk", "500", "miles"]))
    words = [
        Word("But", 0.0, 0.3, 0.9), Word("I", 0.3, 0.5, 0.9),
        Word("would", 0.5, 0.8, 0.9), Word("walk", 0.8, 1.1, 0.9),
        Word("five", 1.1, 1.4, 0.9), Word("hundred", 1.4, 1.8, 0.9),
        Word("miles", 1.8, 2.2, 0.9),
    ]
    segments = (Segment(index=0, text=" ".join(w.text for w in words),
                        start=0.0, end=2.2, words=tuple(words)),)
    aligned = align_lyrics(lyrics, segments, skip_filler=True)
    number = next(a for a in aligned if a.lyric.text == "500")
    assert number.matched_text == "five hundred"
    assert number.sim == 1.0


# -- B276 ----------------------------------------------------------------

def test_is_filler_word_herkent_interjectie_en_blok() -> None:
    assert is_filler_word("oh")
    assert is_filler_word("da")
    assert is_filler_word("dadada")   # herhaling van een vulklank-basis
    assert not is_filler_word("banana")
    assert not is_filler_word("mama")


def test_align_lyrics_koppelt_interjectie_binnen_ankervenster() -> None:
    """B276: 'oh' tussen twee ankers, door Whisper wel getranscribeerd."""
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        ["niets", "veranderd", "oh", "het", "voelt"]))
    words = [
        Word("niets", 0.0, 0.5, 0.9), Word("veranderd", 0.5, 1.5, 0.9),
        Word("oh", 1.5, 1.8, 0.9), Word("het", 1.8, 2.1, 0.9),
        Word("voelt", 2.1, 2.6, 0.9),
    ]
    segments = (Segment(index=0, text=" ".join(w.text for w in words),
                        start=0.0, end=2.6, words=tuple(words)),)
    aligned = align_lyrics(lyrics, segments, skip_filler=True)
    oh = next(a for a in aligned if a.lyric.text == "oh")
    assert oh.matched_text == "oh"
    assert oh.start == 1.5 and oh.end == 1.8


def test_align_lyrics_vulwoord_valt_terug_zonder_match() -> None:
    """B276: geen goede match in het venster -> blijft ongekoppeld (oud
    gedrag, energie-timing-terugval elders)."""
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        ["hallo", "da", "da", "da", "wereld"]))
    words = [
        Word("hallo", 10.0, 10.5, 0.9),
        Word("muziek", 10.5, 12.5, 0.3),
        Word("wereld", 12.5, 13.0, 0.9),
    ]
    segments = (Segment(index=0, text=" ".join(w.text for w in words),
                        start=10.0, end=13.0, words=tuple(words)),)
    aligned = align_lyrics(lyrics, segments, skip_filler=True)
    das = [a for a in aligned if a.lyric.text == "da"]
    assert all(a.start is None for a in das)


def test_align_lyrics_koppelt_elk_woord_van_een_blok_apart() -> None:
    """B276: een echt gezongen 'da da da'-blok krijgt elk woord los
    gekoppeld, niet allemaal aan hetzelfde transcript-woord."""
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        ["hallo", "da", "da", "da", "wereld"]))
    words = [
        Word("hallo", 10.0, 10.5, 0.9),
        Word("da", 10.5, 11.0, 0.9), Word("da", 11.0, 11.5, 0.9),
        Word("da", 11.5, 12.0, 0.9),
        Word("wereld", 12.5, 13.0, 0.9),
    ]
    segments = (Segment(index=0, text=" ".join(w.text for w in words),
                        start=10.0, end=13.0, words=tuple(words)),)
    aligned = align_lyrics(lyrics, segments, skip_filler=True)
    das = [a for a in aligned if a.lyric.text == "da"]
    times = {(a.start, a.end) for a in das}
    assert len(times) == 3   # elk 'da' zijn eigen transcript-woord


# -- B278 --------------------------------------------------------------

def test_video_tab_heeft_eigen_voortgangsbalk(tmp_path) -> None:
    """B278: het Video-tabblad bevat een eigen QProgressBar + statuslabel."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import pytest
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from modules import gui
    from modules.config import default_config
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories
    from modules.pipeline import AppContext

    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    context = AppContext(config=default_config(), paths=paths,
                         store=ProjectStore(paths.project_file))

    QApplication.instance() or QApplication([])
    window = gui.MainWindow(context)
    try:
        assert hasattr(window, "_video_progress")
        assert hasattr(window, "_video_status")
        assert window._video_progress is not None
        assert window._video_status is not None
    finally:
        window.close()


# -- B279 ----------------------------------------------------------------

def test_spans_over_words_koppelt_op_woordgrenzen() -> None:
    """B279: een kort karaoke-woord ('Ik') mag niet de duur erven van een
    lang aangehouden, positioneel niet-corresponderend origineel woord."""
    from modules.timing import _spans_over_words, split_line

    pieces = split_line("Ik zeg miauw.")
    original_words = [
        ("hoe", 44.88, 45.16),
        ("is", 45.16, 45.86),
        ("het", 45.86, 46.20),
        ("nou?", 46.20, 49.62),   # held_note_end-opgerekt, 3.42s
    ]
    spans = _spans_over_words(pieces, 44.88, 49.62, original_words)
    assert spans is not None
    # 'Ik' (karaoke-woord 1 van 4) hoort bij het 1e originele woord ('hoe',
    # kort) en mag dus niet de opgerekte laatste-woord-duur erven.
    ik_start, ik_end = spans[0]
    assert ik_end - ik_start < 1.0
    # De lettergrepen van 'miauw' (laatste karaoke-woord) horen bij het
    # opgerekte laatste originele woord en delen diens grote duur samen.
    mi_start, _ = spans[2]
    _, auw_end = spans[3]
    assert auw_end - mi_start > 3.0


def test_spans_over_words_zonder_bruikbare_woorden_geeft_none() -> None:
    from modules.timing import _spans_over_words, split_line

    pieces = split_line("Hallo daar")
    assert _spans_over_words(pieces, 0.0, 1.0, []) is None
    assert _spans_over_words(pieces, 0.0, 1.0, [("x", 5.0, 5.0)]) is None


def test_karaoke_word_groups_groepeert_op_voorloopspatie() -> None:
    from modules.timing import _karaoke_word_groups, split_line

    pieces = split_line("Ik zeg miauw.")
    groups = _karaoke_word_groups(pieces)
    assert groups == [[0], [1], [2, 3]]
