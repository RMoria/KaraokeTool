"""Tests for the v0.91.0 fixes.

B274: lyric words made up purely of digits (e.g. "500", "1000") got an
empty phonetic key and could therefore never match Whisper's
transcription, not even when Whisper wrote the number out in full (in
Dutch or in English). Such a word is now compared through its
spelled-out form in both languages, and the form with the best
similarity wins. Supports 0 up to 999,999,999.

B275: the title fields (karaoke title/artist/title) only saved on
``editingFinished``, which did not always fire reliably before a step
button (Detect/Couple/...) had already read the context. Every step
handler now first forces the focus away from an active input field.

B276: filler words (oh, da-da-da) were always skipped in the lyric
alignment, even when Whisper had transcribed them after all. They now
first get a match attempt inside the anchor window of their
neighbours; only without a good match do they fall back to the old
behaviour.

B277 (first version, see tests/test_v092.py for the revision):
``held_note_end``/``active_end`` sampled the vocal energy at a single
point; a first attempt used a ~0.1s moving average.

B278: the karaoke video tab had no progress bar of its own; it has one
now, and it mirrors the same progress as the Audio tab.

B279: karaoke syllables were resampled in one flat pass over the whole
original-word timeline, purely on relative position - a short karaoke
word could thus inherit the duration of a long held original word by
accident. Karaoke WORDS are now projected onto original words first,
and only then are the syllables divided within that word pair.
"""
from __future__ import annotations

from modules.cluster import (is_pure_number, number_key_best_match,
                             number_word_forms, phonetic_key, similarity)
from modules.song_text import LyricWord, align_lyrics, is_filler_word
from modules.whisper import Segment, Word


# -- B274 --------------------------------------------------------------

def test_number_word_forms_basics() -> None:
    assert number_word_forms(500) == ("vijfhonderd", "five hundred")
    assert number_word_forms(0) == ("nul", "zero")
    assert number_word_forms(1000) == ("duizend", "one thousand")


def test_number_word_forms_limit_999_999_999() -> None:
    assert number_word_forms(999_999_999) != ()
    assert number_word_forms(1_000_000_000) == ()
    assert number_word_forms(-1) == ()


def test_is_pure_number() -> None:
    assert is_pure_number("500")
    assert is_pure_number("5.000")   # thousand separators allowed
    assert not is_pure_number("500km")
    assert not is_pure_number("vijfhonderd")


def test_phonetic_key_digit_word_uses_the_spelled_out_form() -> None:
    # Without B274 "500" gets an empty key (only letters survive); now
    # the Dutch spelled-out form is used.
    assert phonetic_key("500") != ""
    assert phonetic_key("500") == phonetic_key("vijfhonderd")


def test_number_key_best_match_picks_the_best_language() -> None:
    english = phonetic_key("five hundred")
    best = number_key_best_match("500", english)
    assert similarity(best, english) == 1.0


def test_align_lyrics_couples_a_digit_word_to_spelled_out_english() -> None:
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

def test_is_filler_word_recognises_interjection_and_block() -> None:
    assert is_filler_word("oh")
    assert is_filler_word("da")
    assert is_filler_word("dadada")   # repeat of a filler-sound base
    assert not is_filler_word("banana")
    assert not is_filler_word("mama")


def test_align_lyrics_couples_interjection_in_anchor_window() -> None:
    """B276: 'oh' between two anchors, transcribed by Whisper."""
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


def test_align_lyrics_filler_word_falls_back_without_a_match() -> None:
    """B276: no good match inside the window -> stays uncoupled (the old
    behaviour, with the energy-timing fallback elsewhere)."""
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


def test_align_lyrics_couples_every_word_of_a_block_separately() -> None:
    """B276: a block of 'da da da' that is really sung gets every word
    coupled on its own, not all of them to the same transcript word."""
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
    assert len(times) == 3   # every 'da' its own transcript word


# -- B278 --------------------------------------------------------------

def test_video_tab_has_its_own_progress_bar(tmp_path) -> None:
    """B278: the Video tab holds its own QProgressBar and status label."""
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

def test_spans_over_words_couples_on_word_boundaries() -> None:
    """B279: a short karaoke word ('Ik') must not inherit the duration of
    a long held original word that does not correspond to it in position."""
    from modules.timing import _spans_over_words, split_line

    pieces = split_line("Ik zeg miauw.")
    original_words = [
        ("hoe", 44.88, 45.16),
        ("is", 45.16, 45.86),
        ("het", 45.86, 46.20),
        ("nou?", 46.20, 49.62),   # stretched by held_note_end, 3.42s
    ]
    spans = _spans_over_words(pieces, 44.88, 49.62, original_words)
    assert spans is not None
    # 'Ik' (karaoke word 1 of 4) belongs to the first original word
    # ('hoe', short) and must not inherit the stretched last-word length.
    ik_start, ik_end = spans[0]
    assert ik_end - ik_start < 1.0
    # The syllables of 'miauw' (the last karaoke word) belong to the
    # stretched last original word and share its long duration.
    mi_start, _ = spans[2]
    _, auw_end = spans[3]
    assert auw_end - mi_start > 3.0


def test_spans_over_words_without_usable_words_returns_none() -> None:
    from modules.timing import _spans_over_words, split_line

    pieces = split_line("Hallo daar")
    assert _spans_over_words(pieces, 0.0, 1.0, []) is None
    assert _spans_over_words(pieces, 0.0, 1.0, [("x", 5.0, 5.0)]) is None


def test_karaoke_word_groups_groups_on_the_leading_space() -> None:
    from modules.timing import _karaoke_word_groups, split_line

    pieces = split_line("Ik zeg miauw.")
    groups = _karaoke_word_groups(pieces)
    assert groups == [[0], [1], [2, 3]]
