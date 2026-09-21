"""Tests for v0.147.0.

B513 two lyrics words can no longer land on the same column, so a click
in the coupling editor never couples the neighbour, B514 a word of tens
of seconds is a runaway loop and not usable word times, B515 the trial
that offers a second language the weak spots of the first, B516 a
measuring stick that lays two runs on the same audio side by side.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline, test_panel  # noqa: E402
from modules.whisper import Segment, Word  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _source_of(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# B513 - every lyrics word its own column
# --------------------------------------------------------------------------

def _canvas(transcript, targets):
    from modules.coupling_editor import CouplingCanvas

    words = [{"index": i, "text": f"w{i}", "line": 0,
              "transcript_indices": list(t), "found": None, "sim": 0.0,
              "pinned": False, "status": "coupled"}
             for i, t in enumerate(targets)]
    return CouplingCanvas(list(transcript), words, lambda *_a: None)


def test_two_lyrics_words_never_share_a_column(qapp) -> None:
    """The measured case: two lyrics words on the same found word, with
    an uncoupled one behind them. They were drawn on exactly the same
    pixels and every click returned the leftmost."""
    canvas = _canvas([("een", 1.0, 1.4), ("twee", 1.4, 1.8)],
                     [[0], [0], []])
    assert len(set(canvas._bot_col)) == len(canvas._bot_col)


def test_clicking_a_word_gives_that_word(qapp) -> None:
    from PySide6.QtCore import QPoint

    canvas = _canvas([("een", 1.0, 1.4), ("twee", 1.4, 1.8)],
                     [[0], [0], []])
    for index in range(3):
        x, y, width = canvas._bot_rect(index)
        hit = canvas._hit_row(QPoint(int(x + width / 2), y + 5), top=False)
        assert hit == index, f"klik op {index} gaf {hit}"


def test_the_found_words_keep_their_own_column_too(qapp) -> None:
    canvas = _canvas([("een", 1.0, 1.4), ("twee", 1.4, 1.8),
                      ("drie", 1.8, 2.2)], [[1], [], [2]])
    assert len(set(canvas._top_col)) == len(canvas._top_col)


def test_a_lyrics_word_sits_under_its_own_group(qapp) -> None:
    """B220 still holds: coupled to found word 1, so under found word 1
    - and not on "whatever column happened to be free"."""
    canvas = _canvas([("een", 1.0, 1.4), ("twee", 1.4, 1.8)], [[1]])
    assert canvas._bot_col[0] == canvas._top_col[1]


def test_a_long_uncoupled_run_stays_side_by_side(qapp) -> None:
    """B320 must survive: rows that drift apart by a column per word are
    exactly what that fix was for."""
    canvas = _canvas([("a", 1.0, 1.2), ("b", 1.2, 1.4), ("c", 1.4, 1.6)],
                     [[], [], []])
    assert canvas._bot_col == canvas._top_col


# --------------------------------------------------------------------------
# B514 - a word of tens of seconds is not a word
# --------------------------------------------------------------------------

def _segment(index, text, start, end, words):
    return Segment(index, text, start, end,
                   tuple(Word(t, s, e, 0.8) for t, s, e in words))


def _normal(count=12):
    return [_segment(i, "woord", 10.0 + i, 10.4 + i,
                     [("woord", 10.0 + i, 10.4 + i)]) for i in range(count)]


def test_one_word_of_twenty_seven_seconds_is_a_loop() -> None:
    """The measured case at "Lied_R2": one word of 223 characters from
    116.8 to 143.8 s, over the whole second chorus."""
    loop = _segment(99, "D.O." * 55, 116.8, 143.8,
                    [("D.O." * 55, 116.8, 143.8)])
    segments = tuple(_normal() + [loop])
    middle = pipeline._median_word_seconds(segments)
    assert 0.0 < middle < 1.0
    assert pipeline.runaway_words(loop, middle)
    assert not pipeline.runaway_words(segments[0], middle)


def test_an_ordinary_held_note_is_not_a_loop() -> None:
    held = _segment(99, "jaaaa", 50.0, 53.0, [("jaaaa", 50.0, 53.0)])
    middle = pipeline._median_word_seconds(tuple(_normal() + [held]))
    assert not pipeline.runaway_words(held, middle)


def test_the_loop_is_dropped_even_without_a_second_core_word() -> None:
    """The broad check needs two core words, and that safety valve is
    what let the worst case through."""
    loop = _segment(99, "D.O." * 55, 116.8, 143.8,
                    [("D.O." * 55, 116.8, 143.8)])
    dropped: list = []
    kept = pipeline._filter_hallucinations(tuple(_normal() + [loop]),
                                           dropped_out=dropped)
    assert loop not in kept
    assert [s.text for s in dropped] == [loop.text]


def test_it_beats_the_chant_exemption() -> None:
    """A chant of twenty-seven seconds in one word is still one word of
    twenty-seven seconds."""
    source = inspect.getsource(pipeline._filter_hallucinations)
    assert source.index("if chant:") < source.index("runaway_words(seg")


def test_the_log_line_does_not_claim_there_was_silence() -> None:
    """The loop demonstrably starts on real singing; what it lacks is
    usable word times."""
    from modules.translations import TRANSLATIONS

    for language in ("nl", "en"):
        text = TRANSLATIONS[language]["log_runaway_filtered"]
        assert text.count("%") >= 4


# --------------------------------------------------------------------------
# B516 - two runs side by side
# --------------------------------------------------------------------------

def _word(text, start, end, confidence=0.9):
    return {"text": text, "start": start, "end": end,
            "confidence": confidence}


def test_it_says_where_two_runs_differ() -> None:
    """1.5.8 counts holes of five seconds and could therefore not see a
    difference of 21.5 s spread over twelve pieces."""
    a = [_word("een", 1.0, 2.0), _word("twee", 5.0, 6.0)]
    b = [_word("een", 1.0, 2.0)]
    windows = [(0.0, 10.0)]
    assert test_panel.only_in(a, b, windows) == [(5.0, 6.0)]
    assert test_panel.only_in(b, a, windows) == []


def test_a_hair_of_difference_is_not_a_finding() -> None:
    a = [_word("een", 1.0, 2.1)]
    b = [_word("een", 1.0, 2.0)]
    assert test_panel.only_in(a, b, [(0.0, 10.0)]) == []


def test_covered_is_the_singing_that_carries_a_word() -> None:
    words = [_word("een", 1.0, 2.0)]
    assert test_panel.covered_seconds(words, [(0.0, 10.0)]) == 1.0


def test_the_hand_timing_of_the_same_recording_is_a_reference() -> None:
    """"In text" cannot reward a correct Korean word when the lyrics
    write it in Latin letters; this figure knows nothing of spelling."""
    lines = [(1.0, 2.0), (5.0, 6.0)]
    assert test_panel.on_the_lines([_word("뛰어", 1.2, 1.6)], lines) == 100.0
    assert test_panel.on_the_lines([_word("iets", 3.0, 3.5)], lines) == 0.0
    assert test_panel.on_the_lines([], lines) == 0.0


def test_the_reference_only_counts_real_hand_work() -> None:
    source = inspect.getsource(test_panel.reference_timing)
    assert 'source.get("sha1") != fingerprint' in source
    assert "never touched by hand" in source


def test_the_table_carries_the_reference_column() -> None:
    # B527: ``ab_report`` grew into ``search_table``, which lays every
    # variant beside the hand work instead of two runs beside each other.
    rows = test_panel.search_table([("a", [_word("x", 1.0, 1.5)]),
                                    ("b", [])],
                                   [(0.0, 10.0)], frozenset(["x"]),
                                   [(1.0, 2.0)])
    head = next(i for i, row in enumerate(rows) if row.startswith("| "))
    assert rows[head].endswith("afstand tot regelbegin |")
    assert rows[head].count("|") == rows[head + 1].count("|")


# --------------------------------------------------------------------------
# B515/B538 - a song with two languages in it
#
# The weak-spot route is gone (B538): the second language over the weak
# spots of the first gave six words and 0% on a real sentence - too
# little run-up for Whisper. What won is in production now and is tested
# in test_v0151. What stays here is what did not go with it.
# --------------------------------------------------------------------------

def test_a_runaway_is_taken_out_before_counting() -> None:
    """Otherwise the loop covers the very hole it sits in, and this
    trial calls that spot healthy."""
    words = [_word("een", 1.0, 1.4)] * 0 + [
        _word(f"w{i}", 10.0 + i, 10.4 + i) for i in range(12)]
    words.append(_word("D.O." * 55, 116.8, 143.8))
    kept, dropped = test_panel.without_runaways(words)
    assert dropped == 1
    assert all(float(w["end"]) - float(w["start"]) < 8.0 for w in kept)


def test_the_trial_is_on_and_can_go_off_again() -> None:
    codes = {trial.code: trial for trial in test_panel.HEAVY_TRIALS}
    assert "1.5.11g" in codes and not codes["1.5.11g"].off
    assert codes["1.5.11g"].function is test_panel.two_language_trial


def test_it_only_runs_where_there_is_a_second_script() -> None:
    source = inspect.getsource(test_panel.two_language_trial)
    assert "pipeline.second_language_of(other)" in source
    assert "raise TrialSkipped" in source
    assert "songs = songs[:CHUNK_SONGS]" in source


def test_the_new_texts_are_in_both_languages() -> None:
    from modules.translations import TRANSLATIONS

    for key in ("ab_only", "ab_more", "heavy_two_languages",
                "heavy_two_languages_intro", "heavy_two_languages_pair",
                "heavy_two_languages_filled", "heavy_two_languages_note",
                "heavy_two_languages_runaway",
                "heavy_two_languages_reference"):
        for language in ("nl", "en"):
            assert TRANSLATIONS[language].get(key, "").strip(), \
                f"{key} ({language})"


# --------------------------------------------------------------------------
# The critical re-reading: what still came out before the delivery
# --------------------------------------------------------------------------

def test_a_whole_missed_line_is_one_stretch() -> None:
    """Whisper words are a third of a second, so a line the other run
    misses arrives as eight little pieces - and judged one by one they
    all fell under the minimum and the difference read as zero."""
    a = [_word(f"w{i}", 10.0 + i * 0.4, 10.4 + i * 0.4) for i in range(8)]
    stretches = test_panel.only_in(a, [], [(0.0, 20.0)])
    assert stretches == [(10.0, 13.2)]


def test_a_held_note_is_not_a_loop() -> None:
    """Nine seconds of "aaaaah" is singing. Dropping that would be the
    cure killing the patient."""
    note = _segment(99, "aaaaah", 50.0, 59.4, [("aaaaah", 50.0, 59.4)])
    segments = tuple(_normal() + [note])
    assert not pipeline.runaway_words(note,
                                      pipeline._median_word_seconds(segments))
    assert note in pipeline._filter_hallucinations(segments)


def test_one_long_word_does_not_take_nine_good_ones_with_it() -> None:
    words = [(t, 60.0 + i, 60.4 + i)
             for i, t in enumerate("ik hou van jou".split())]
    words.append(("aaaaah", 64.0, 73.4))
    words += [(t, 74.0 + i, 74.4 + i)
              for i, t in enumerate("en jij van mij".split())]
    line = _segment(98, "ik hou van jou aaaaah en jij van mij",
                    60.0, 78.4, words)
    assert line in pipeline._filter_hallucinations(tuple(_normal() + [line]))


def test_without_a_median_only_the_letters_count() -> None:
    """The same restraint held_transcript_words shows with too little to
    measure against."""
    loop = _segment(0, "x" * 80, 0.0, 30.0, [("x" * 80, 0.0, 30.0)])
    plain = _segment(1, "aaaaah", 40.0, 60.0, [("aaaaah", 40.0, 60.0)])
    assert pipeline._median_word_seconds((loop, plain)) == 0.0
    assert pipeline.runaway_words(loop, 0.0)
    assert not pipeline.runaway_words(plain, 0.0)


def test_the_reference_is_projected_onto_the_right_timeline() -> None:
    """timing.json lies on the karaoke timeline and a Whisper run on
    that of the original vocal stem."""
    source = inspect.getsource(test_panel.reference_timing)
    assert "align.project_time_reverse(line.start, regions)" in source


def test_the_difference_rows_are_a_real_table() -> None:
    rows = test_panel.differences("a", [_word("x", 1.0, 2.0)], "b", [],
                                  [(0.0, 10.0)])
    kop = [i for i, r in enumerate(rows) if r.startswith("| plek |")]
    assert kop, "de verschilregels horen een eigen kopregel te hebben"
    for index in kop:
        assert rows[index + 1].startswith("| --- |")


def test_a_click_in_an_empty_part_of_a_box_destroys_nothing(qapp) -> None:
    """A merged box may cover a column belonging to nobody, and the
    coupling line hangs on the optical middle of that box - so a click
    in the middle of a word box removed the whole group's coupling."""
    from PySide6.QtCore import QPoint

    from modules import coupling_editor as ce

    canvas = _canvas([(f"t{i}", i * 1.0, i * 1.0 + 0.5) for i in range(6)],
                     [[1, 2, 3], [3]])
    spans = canvas._merged_bottom_spans()
    first, last, _targets = list(spans.values())[0]
    x1 = canvas._bot_rect(first)[0]
    x2 = canvas._bot_rect(last)[0] + canvas._bot_rect(last)[2]
    middle = QPoint((x1 + x2) // 2, ce._BOT_Y + 5)
    assert canvas._hit_row(middle, top=False) is None
    assert canvas._hit_link(middle) is not None    # dit was de sloper
    assert canvas._in_a_box(middle) is True
    source = inspect.getsource(ce.CouplingCanvas.mousePressEvent)
    assert source.index("self._in_a_box(pos)") < source.index("_hit_link")
