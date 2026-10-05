"""v1.0.14: what the 1.5.13 night taught, and the editor wishes.

B593 - a hand timing with split lines is measured after all.
B594 - the night judges on a capped error and on songs, not on a mean.
B595 - anchors that cram their lines lose their anchor (model, off).
"""
from __future__ import annotations

import subprocess

from pathlib import Path

import pytest

from modules import front_to_back as ftb
from modules import model_register, test_panel
from modules import timing as tim
from modules.timing import Syllable, TimedLine


# --------------------------------------------------------------------------
# B593 - pairing lines on the word they begin on
# --------------------------------------------------------------------------

def _pairing():
    return test_panel._regression_module().paired_lines


def test_equal_counts_pair_one_to_one_as_before() -> None:
    pair = _pairing()
    assert pair(["a b", "c d"], ["x", "y"]) == [(0, 0), (1, 1)]


def test_a_split_line_pairs_on_its_first_word() -> None:
    """The owner split every long line into the line and its last word;
    the first piece pairs with the whole line, the split-off word has
    nothing to pair with."""
    pair = _pairing()
    hand = ["een twee drie", "vier", "vijf zes", "zeven acht", "negen"]
    auto = ["een twee drie vier", "vijf zes", "zeven acht negen"]
    assert pair(hand, auto) == [(0, 0), (2, 1), (3, 2)]
    # And the other way round.
    assert pair(auto, hand) == [(0, 0), (1, 2), (2, 3)]


def test_pairing_survives_a_changed_word_and_punctuation() -> None:
    pair = _pairing()
    hand = ["Een, twee!", "drie", "vier vijf"]
    auto = ["een twee drie", "vier VIJF"]
    assert pair(hand, auto) == [(0, 0), (2, 1)]


def test_the_night_measures_the_paired_lines_and_keeps_their_index(
        monkeypatch, tmp_path) -> None:
    hand = [{"text": "een twee", "syllables": [{"start": 1.0, "end": 2}]},
            {"text": "drie", "syllables": [{"start": 2.5, "end": 3}]},
            {"text": "vier", "syllables": [{"start": 5.0, "end": 6}]}]
    fresh = (TimedLine(0, "een twee drie", False,
                       (Syllable("een", 1.2, 3.0),)),
             TimedLine(1, "vier", False, (Syllable("vier", 5.5, 6.0),)))

    class _Timing:
        paired_lines = staticmethod(_pairing())

        @staticmethod
        def timing_for(copy, hand_lines):
            return fresh, 2

    monkeypatch.setattr(test_panel, "_regression_module", lambda: _Timing)
    monkeypatch.setattr(ftb, "_hand_lines", lambda folder: hand)
    monkeypatch.setattr(ftb, "copy_project", lambda *a, **k: None)
    monkeypatch.setattr(ftb.pipeline, "context_for_project",
                        lambda *a, **k: type("C", (), {"paths": type(
                            "P", (), {"output_dir": tmp_path})()})())
    monkeypatch.setattr(ftb.pipeline, "read_only", lambda c: c)
    monkeypatch.setattr(ftb.pipeline, "detect_track", lambda *a, **k: None)
    monkeypatch.setattr(ftb.pipeline, "load_segments", lambda *a, **k: ())
    monkeypatch.setattr(ftb.pipeline, "_original_vocal_windows",
                        lambda c: [])
    monkeypatch.setattr(ftb.pipeline, "lyric_keys", lambda c: set())
    try:
        found = ftb.measure_one(None, "S", ftb.BASELINE, tmp_path,
                                ftb.HeardOnce(tmp_path, "S"),
                                lambda: False)
    finally:
        model_register.restore_all()
    assert found["index"] == [0, 2]
    assert found["starts"] == [1.2, 5.5] and found["hand"] == [1.0, 5.0]


# --------------------------------------------------------------------------
# B594 - a capped error, and songs better or worse
# --------------------------------------------------------------------------

def _run(starts, hand, index=None):
    out = {"starts": starts, "hand": hand, "unheard": 0.0, "in_text": 90.0}
    if index is not None:
        out["index"] = index
    return out


def test_one_runaway_song_weighs_like_any_other() -> None:
    hand = [1.0, 5.0, 9.0, 13.0]
    results = {
        "calm": {"baseline": _run([1.5, 5.5, 9.5, 13.5], hand),
                 "way": _run([1.0, 5.0, 9.0, 13.0], hand)},
        "wild": {"baseline": _run([1.0, 5.0, 9.0, 13.0], hand),
                 "way": _run([1.0, 5.0, 29.0, 33.0], hand)},
    }
    way = ftb.tally(results, "way", ["calm", "wild"])
    zero = ftb.tally(results, "baseline", ["calm", "wild"])
    # Plain mean: 40 s of error against 2 s - the runaway decides.
    # Capped: 2 x 2 s against 4 x 0.5 s, level.
    assert way.mean == pytest.approx(4.0 / 8)
    assert zero.mean == pytest.approx(2.0 / 8)
    assert way.runaway == 2 and way.good == 6
    assert way.share_good == pytest.approx(75.0)
    assert way.songs_better == 1 and way.songs_worse == 1


def test_a_song_moving_less_than_the_margin_is_neither() -> None:
    hand = [1.0, 5.0]
    results = {"S": {"baseline": _run([1.0, 5.0], hand),
                     "way": _run([1.02, 5.02], hand)}}
    way = ftb.tally(results, "way", ["S"])
    assert way.songs_better == 0 and way.songs_worse == 0


def test_the_sums_pair_runs_on_the_hand_line_not_the_position() -> None:
    """A run that paired fewer lines is compared line by line on the
    hand line it belongs to, not shifted by one."""
    results = {"S": {"baseline": _run([1.0, 2.0, 3.0], [1.0, 2.0, 3.0],
                                      [0, 1, 2]),
                     "way": _run([1.0, 3.0], [1.0, 3.0], [0, 2])}}
    way = ftb.tally(results, "way", ["S"])
    assert way.lines == 2 and way.mean == 0.0 and way.broken == 0


def test_a_line_only_one_run_paired_is_left_out() -> None:
    results = {"S": {"baseline": _run([1.0, 2.0, 3.0], [1.0, 2.0, 3.0],
                                      [0, 1, 2]),
                     "way": _run([1.0, 3.0, 4.0], [1.0, 3.0, 4.0],
                                 [0, 2, 3])}}
    way = ftb.tally(results, "way", ["S"])
    assert way.lines == 2


def test_helping_means_a_lower_capped_mean_and_no_more_songs_worse() -> None:
    better = ftb.Tally(lines=10, capped=1.0, songs_better=3, songs_worse=2)
    zero = ftb.Tally(lines=10, capped=2.0)
    assert ftb.helps(better, zero)
    lucky = ftb.Tally(lines=10, capped=1.0, songs_better=1, songs_worse=4)
    assert not ftb.helps(lucky, zero), "one big win, four songs worse"
    assert not ftb.helps(ftb.Tally(lines=10, capped=2.5), zero)


def test_the_report_has_a_cell_for_every_column() -> None:
    columns = ftb.t("front_to_back_cols").count("|")
    row = ftb._row("x", ftb.Tally(lines=1, capped=0.1, good=1),
                   ftb.Tally(lines=1, capped=0.2))
    assert row.count("|") == columns == ftb._RULE.count("|")


# --------------------------------------------------------------------------
# B595 - stacked lines lose their anchor
# --------------------------------------------------------------------------

def test_a_crammed_anchor_is_dropped_the_right_one() -> None:
    """Five lines between 42.0 and 57.1, four anchors on top of each
    other just after 42: the early one is right (its left neighbour has
    room), the stacked ones go and the run fits again."""
    kept = {10: 40.5, 11: 42.0, 12: 42.1, 13: 42.2, 14: 42.3, 15: 42.4,
            16: 57.1}
    floors = [1.0] * 20
    weights = {i: 2.0 for i in kept}
    left = tim.unstack_anchors(kept, floors, weights)
    assert sorted(left) == [10, 11, 16]


def test_room_for_the_lines_leaves_every_anchor() -> None:
    kept = {0: 0.0, 1: 3.0, 2: 6.0, 3: 6.8}
    assert tim.unstack_anchors(kept, [1.0] * 4, {}) == kept


def test_a_fixed_anchor_always_stays() -> None:
    kept = {0: 5.0, 1: 5.1, 2: 20.0}
    left = tim.unstack_anchors(kept, [1.0] * 3, {0: 10.0, 1: 2.0},
                               fixed=frozenset({0}))
    assert 0 in left and 1 not in left
    # Where the fixed one would be the one to go, its neighbour goes.
    kept = {0: 0.0, 1: 10.0, 2: 10.1, 3: 30.0}
    assert sorted(tim.unstack_anchors(kept, [1.0] * 4, {})) == [0, 1, 3]
    assert sorted(tim.unstack_anchors(kept, [1.0] * 4, {},
                                      fixed=frozenset({2}))) == [0, 2, 3]


def _line(index, start, quality="high", words=4):
    width = 0.3
    return TimedLine(index, "la " * words, False, tuple(
        Syllable(("" if k == 0 else " ") + "la", start + k * width,
                 start + (k + 1) * width) for k in range(words)),
        quality=quality)


def test_stacked_lines_spread_over_the_room_when_switched_on() -> None:
    starts = [0.0, 3.3, 6.6, 6.7, 6.8, 6.9, 19.8, 23.1]
    lines = [_line(i, s) for i, s in enumerate(starts)]
    model_register.apply_settings({"B595": True})
    model_register.apply_disabled()
    try:
        spread = tim.sanitize_timing(lines)
    finally:
        model_register.restore_all()
    model_register.apply_settings({"B595": False})
    model_register.apply_disabled()
    try:
        stacked = tim.sanitize_timing(lines)
    finally:
        model_register.restore_all()
    gaps_on = [b.start - a.start for a, b in zip(spread[2:6], spread[3:7])]
    gaps_off = [b.start - a.start for a, b in zip(stacked[2:6],
                                                  stacked[3:7])]
    assert max(gaps_off) > 9.0, "switched off the run sits on the floor"
    assert min(gaps_on) > 2.0, "switched on the lines share the room"
    # The good anchors stay where they were.
    assert spread[1].start == pytest.approx(3.3)
    assert spread[6].start == pytest.approx(19.8)


def test_the_stacking_idea_ships_on_since_v1015() -> None:
    """Off in v1.0.14 until 1.5.13 had measured it; on since v1.0.15."""
    model = model_register.by_code("B595")
    assert model is not None and model.default_on


# --------------------------------------------------------------------------
# B585/B586 - the word and syllable views
# --------------------------------------------------------------------------

def _pieces(words, crowd_words=()):
    """Letter pieces for ``words`` = [(text, start, end)]."""
    out = []
    for n, (text, start, end) in enumerate(words):
        step = (end - start) / len(text)
        for k, ch in enumerate(text):
            out.append({"text": (" " if n and not k else "") + ch,
                        "start": round(start + k * step, 3),
                        "end": round(start + (k + 1) * step, 3),
                        "crowd": text in crowd_words})
    return out


def _edit_line(index, words, crowd=False, crowd_words=()):
    return {"index": index, "text": " ".join(w[0] for w in words),
            "crowd": crowd, "syllables": _pieces(words, crowd_words)}


def test_the_word_view_underlines_each_sentence() -> None:
    lines = [_edit_line(0, [("ik", 0.0, 1.0), ("zie", 1.0, 2.0)]),
             _edit_line(1, [("jou", 3.0, 4.0)])]
    cells = tim.editor_view_cells(lines, "words")
    assert tim.underline_spans(cells) == [(0.0, 2.0), (3.0, 4.0)]
    assert tim.underline_spans(tim.editor_view_cells(lines,
                                                     "sentences")) == []


def test_the_syllable_view_underlines_each_word() -> None:
    lines = [_edit_line(0, [("jalala", 0.0, 1.2), ("hey", 1.5, 2.0)])]
    cells = tim.editor_view_cells(lines, "syllables")
    assert [c["text"] for c in cells] == ["ja", "la", "la", "hey"]
    assert tim.underline_spans(cells) == [(0.0, 1.2), (1.5, 2.0)]
    assert [c["word"] for c in cells] == [0, 0, 0, 1]


def test_the_original_lane_underlines_the_same_way() -> None:
    originals = [{"text": "jalala hey", "start": 0.0, "end": 2.0,
                  "rows": [0]}]
    words = tim.original_view_cells(originals, "words")
    assert tim.underline_spans(words) == [(0.0, 2.0)]
    syllables = tim.original_view_cells(originals, "syllables")
    assert [c["text"] for c in syllables] == ["ja", "la", "la", "hey"]
    assert tim.underline_spans(syllables) == [(0.0, 1.0), (1.0, 2.0)]


def test_a_crowd_word_is_red_in_the_word_and_syllable_view() -> None:
    lines = [_edit_line(0, [("owheoo", 0.0, 1.0), ("ja", 1.0, 2.0)],
                        crowd_words=("owheoo",))]
    for mode in ("words", "syllables"):
        cells = tim.editor_view_cells(lines, mode)
        assert all(c["crowd"] for c in cells if c["word"] == 0), mode
        assert not any(c["crowd"] for c in cells if c["word"] == 1), mode
    whole = [_edit_line(0, [("ja", 0.0, 1.0)], crowd=True)]
    assert tim.editor_view_cells(whole, "words")[0]["crowd"]


# --------------------------------------------------------------------------
# B587 - one word back from the original
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _canvas(lines, mode, originals=None, moved_words=()):
    import numpy as np

    from modules.timing_editor import TimingCanvas

    canvas = TimingCanvas(np.zeros(100, dtype=np.float32), None, 30.0,
                          lines, on_seek=lambda *_: None,
                          originals=originals,
                          moved_word_restores=moved_words)
    canvas.set_view_mode(mode)
    canvas._cells = tim.editor_view_cells(lines, mode)
    canvas._orig_cells = tim.original_view_cells(originals or [], mode)
    return canvas


def test_the_word_view_marks_one_word_not_the_sentence(qapp) -> None:
    lines = [_edit_line(7, [("ik", 0.0, 1.0), ("zie", 1.0, 2.0)])]
    canvas = _canvas(lines, "words")
    canvas._sel_cell = 1
    assert canvas.toggle_selected_restore()
    assert canvas.restore_words() == [(7, 1)] and canvas.restore_rows() == []
    canvas.toggle_selected_restore()
    assert canvas.restore_words() == []


def test_the_syllable_view_marks_the_whole_word(qapp) -> None:
    lines = [_edit_line(3, [("jalala", 0.0, 1.2), ("hey", 1.5, 2.0)])]
    canvas = _canvas(lines, "syllables")
    canvas._sel_cell = 2                                  # the last "la"
    canvas.toggle_selected_restore()
    assert canvas.restore_words() == [(3, 0)]


def test_the_sentence_view_still_marks_the_sentence(qapp) -> None:
    lines = [_edit_line(2, [("ik", 0.0, 1.0), ("zie", 1.0, 2.0)])]
    canvas = _canvas(lines, "sentences")
    canvas._sel_cell = 0
    canvas.toggle_selected_restore()
    assert canvas.restore_rows() == [2] and canvas.restore_words() == []


def test_the_original_lane_marks_the_word_under_it(qapp) -> None:
    lines = [_edit_line(0, [("ik", 0.0, 1.0), ("zie", 1.0, 2.0)])]
    originals = [{"text": "I see", "start": 0.0, "end": 2.0, "rows": [0]}]
    canvas = _canvas(lines, "words", originals)
    canvas._sel_orig = 1                                 # "see", 1.0-2.0
    canvas.toggle_selected_restore()
    assert canvas.restore_words() == [(0, 1)]


def test_a_moved_word_is_put_back_first(qapp) -> None:
    lines = [_edit_line(4, [("ik", 0.0, 1.0), ("zie", 1.0, 2.0)])]
    lines[0]["restore_words"] = [0]
    canvas = _canvas(lines, "words", moved_words=[(4, 0)])
    canvas._sel_cell = 0
    canvas.toggle_selected_restore()
    assert canvas.reset_word_moves() == [(4, 0)]
    assert canvas.restore_words() == [(4, 0)], "still marked"
    canvas.toggle_selected_restore()
    assert canvas.restore_words() == []


def _project(tmp_path):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)
    from modules import pipeline

    paths = ProjectPaths(root=tmp_path, song="Lied")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    lines = [TimedLine(index=i, text="ik zie", crowd=False, syllables=(
        Syllable("ik", i * 4.0, i * 4.0 + 1.0),
        Syllable(" zie", i * 4.0 + 1.0, i * 4.0 + 2.0))) for i in range(3)]
    tim.save_timing(lines, paths.timing_file)
    return context


def test_a_marked_word_becomes_a_fragment_that_follows_it(tmp_path) -> None:
    from modules import pipeline

    context = _project(tmp_path)
    pipeline.set_restore_words(context, [(1, 1)])
    fragments = pipeline.restore_fragments(context)
    assert [(f.start, f.end) for f in fragments] == [(5.0, 6.0)]
    assert pipeline.word_of_restore_label(fragments[0].label) == (1, 1)
    assert fragments[0].label.endswith(": zie")
    assert pipeline.line_of_restore_label(fragments[0].label) is None
    # The sentence wins over its words.
    pipeline.set_restore_lines(context, [1])
    assert [(f.start, f.end) for f in pipeline.restore_fragments(
        context)] == [(4.0, 6.0)]


def _no_audio(monkeypatch, pipeline):
    monkeypatch.setattr(pipeline, "stored_wav", lambda c, track: "k.wav")
    monkeypatch.setattr(pipeline.ffmpeg, "probe", lambda path: type(
        "P", (), {"sample_rate": 44100})())
    monkeypatch.setattr(pipeline.karaoke, "apply_damping",
                        lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "_prepared_restore_intervals",
                        lambda *a, **k: [])


def test_deleting_or_moving_a_word_block_in_1_4_reaches_the_mark(
        tmp_path, monkeypatch) -> None:
    from modules import pipeline

    _no_audio(monkeypatch, pipeline)
    context = _project(tmp_path)
    pipeline.set_restore_words(context, [(0, 0), (2, 1)])
    blocks = [(f.start, f.end, f.label)
              for f in pipeline.restore_fragments(context)]
    # The first is moved half a second, the second deleted.
    moved = [(blocks[0][0] + 0.5, blocks[0][1] + 0.5, blocks[0][2])]
    pipeline.apply_manual_damping(context, [], restore_spans=moved)
    assert pipeline.restore_words(context) == ((0, 0),)
    assert pipeline.moved_word_restores(context) == {(0, 0): (0.5, 1.5)}
    assert [(f.start, f.end) for f in pipeline.restore_fragments(
        context)] == [(0.5, 1.5)]
    pipeline.reset_moved_word_restore(context, 0, 0)
    assert [(f.start, f.end) for f in pipeline.restore_fragments(
        context)] == [(0.0, 1.0)]
    # Drawn blocks never store a derived word block as drawn.
    step = context.store.get_step("restore_fragments")
    assert step["list"] == []


# --------------------------------------------------------------------------
# B588/B590 - the damping editor
# --------------------------------------------------------------------------

def test_a_new_block_goes_into_the_next_free_gap() -> None:
    from modules import damping_editor as de

    blocks = [[1.0, 2.0, "demping", ""], [2.5, 4.0, "herstel", "x"]]
    assert de.free_gap(blocks, 0.0, 10.0) == (0.0, 1.0)
    assert de.free_gap(blocks, 1.5, 10.0) == (2.0, 2.5), "shorter gap"
    assert de.free_gap(blocks, 3.0, 10.0) == (4.0, 5.0)
    assert de.free_gap(blocks, 9.5, 10.0) == (9.5, 10.0)
    assert de.free_gap([[0.0, 10.0, "demping", ""]], 0.0, 10.0) is None
    tight = [[1.0, 2.0, "demping", ""], [2.05, 3.0, "demping", ""]]
    assert de.free_gap(tight, 1.5, 10.0) == (3.0, 4.0), "too small skipped"


def test_a_block_is_bound_by_its_neighbours_of_any_kind() -> None:
    from modules import damping_editor as de

    blocks = [[1.0, 2.0, "demping", ""], [3.0, 4.0, "herstel", "zin 1: x"],
              [6.0, 7.0, "herstel", "y"]]
    assert de.block_bounds(blocks, 1, 20.0) == (2.0, 6.0)
    assert de.block_bounds(blocks, 0, 20.0) == (0.0, 3.0)
    assert de.block_bounds(blocks, 2, 20.0) == (4.0, 20.0)


def test_dragging_a_block_stops_at_the_neighbour(qapp) -> None:
    import numpy as np

    from modules import damping_editor as de

    blocks = [[1.0, 2.0, "demping", ""], [3.0, 4.0, "herstel", "x"]]
    canvas = de.DampingCanvas(np.zeros(100, dtype=np.float32), 10.0,
                              blocks, on_seek=lambda *_: None)

    class _Event:
        def __init__(self, x):
            self._x = x

        def position(self):
            from PySide6.QtCore import QPointF
            return QPointF(self._x, de._BLOCK_TOP + 5)

    pps = canvas.pixels_per_second
    canvas._drag = (0, "verplaats", 1.5)
    canvas.mouseMoveEvent(_Event(3.5 * pps))          # two seconds right
    assert blocks[0][:2] == [2.0, 3.0], "slides up against the neighbour"
    canvas._drag = (0, "rechts", 3.0)
    canvas.mouseMoveEvent(_Event(4.0 * pps))
    assert blocks[0][:2] == [2.0, 3.0], "no room to stretch"
    canvas._drag = (1, "rechts", 4.0)
    canvas.mouseMoveEvent(_Event(30.0 * pps))
    assert blocks[1][1] == pytest.approx(10.0), "not past the song"
    # An old block squeezed in a gap too small to move in stays put.
    tight = [[1.0, 2.0, "demping", ""], [2.02, 2.06, "demping", ""],
             [2.08, 3.0, "herstel", "x"]]
    canvas = de.DampingCanvas(np.zeros(100, dtype=np.float32), 10.0,
                              tight, on_seek=lambda *_: None)
    canvas._drag = (1, "verplaats", 2.04)
    canvas.mouseMoveEvent(_Event(2.2 * canvas.pixels_per_second))
    assert tight[1][:2] == [2.02, 2.06]


def test_playback_follows_the_blocks_as_they_stand() -> None:
    from modules import damping_editor as de

    blocks = [[1.0, 2.0, "demping", ""], [1.5, 3.0, "herstel", "x"]]
    assert de.preview_kind(blocks, 0.5) is None
    assert de.preview_kind(blocks, 1.2) == "demping"
    assert de.preview_kind(blocks, 1.7) == "herstel", "restore wins"
    assert de.preview_kind(blocks, 3.0) is None
    assert de.preview_kind(list(reversed(blocks)), 1.7) == "herstel"


def test_the_live_preview_switches_to_the_original(qapp) -> None:
    from modules import damping_editor as de

    class _Output:
        def __init__(self):
            self.volume = 1.0

        def setVolume(self, value):
            self.volume = value

    class _Player:
        def __init__(self, at):
            self.at = at

        def position(self):
            return int(self.at * 1000)

        def setPosition(self, ms):
            self.at = ms / 1000.0

    editor = de.DampingEditorDialog.__new__(de.DampingEditorDialog)
    editor._canvas = type("C", (), {"blocks": [
        [1.0, 2.0, "demping", ""], [4.0, 5.0, "herstel", "zin 2: x"]]})()
    editor._audio_output, editor._original_output = _Output(), _Output()
    editor._original_player = _Player(0.0)
    editor._to_original = lambda moment: moment + 10.0
    editor._damped_volume = 0.05
    editor._follow(1.5)
    assert editor._audio_output.volume == 0.05
    assert editor._original_output.volume == 0.0
    editor._follow(4.5)
    assert editor._audio_output.volume == 0.0
    assert editor._original_output.volume == 1.0
    assert editor._original_player.at == pytest.approx(14.5)
    editor._follow(6.0)
    assert editor._audio_output.volume == 1.0
    assert editor._original_output.volume == 0.0


# --------------------------------------------------------------------------
# B591 - the separation, a setting, and existing projects untouched
# --------------------------------------------------------------------------

def test_the_standard_way_keeps_its_folder_and_marker() -> None:
    from modules import separation

    standard = separation.way_for("standard")
    assert standard.is_standard and standard.tag == "htdemucs"
    assert standard.folder("original") == "demucs_stems_original"
    careful = separation.way_for("careful")
    assert (careful.model, careful.shifts) == ("htdemucs_ft", 2)
    assert careful.folder("original") != standard.folder("original")
    roformer = separation.way_for("roformer")
    assert roformer.backend == "roformer"
    assert roformer.folder("original").startswith("stems_original_")
    assert separation.way_for("nonsense") == standard


def test_careful_demucs_asks_for_two_shifts(tmp_path, monkeypatch) -> None:
    from modules import proc, separation

    seen = []

    def run(command, **k):
        seen.append(list(command))
        out = tmp_path / "w" / "htdemucs_ft" / "song"
        out.mkdir(parents=True, exist_ok=True)
        (out / "vocals.wav").write_bytes(b"v")
        (out / "no_vocals.wav").write_bytes(b"m")

    monkeypatch.setattr(separation, "is_available", lambda way=None: True)
    monkeypatch.setattr(proc, "run", run)
    separation.separate_way(tmp_path / "a.wav", tmp_path / "w",
                            separation.way_for("careful"))
    command = seen[0]
    assert command[command.index("--shifts") + 1] == "2"
    assert command[command.index("-n") + 1] == "htdemucs_ft"
    separation.separate_way(tmp_path / "a.wav", tmp_path / "w",
                            separation.way_for("standard"))
    assert "--shifts" not in seen[1]


def test_roformer_runs_in_its_own_environment(tmp_path, monkeypatch) -> None:
    from modules import proc, separation

    python = tmp_path / "venv_separator" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    monkeypatch.setattr(separation, "roformer_env_dirs",
                        lambda: [tmp_path / "venv_separator"])
    seen = []
    monkeypatch.setattr(separation, "_ROFORMER_CHECKED", {})

    def run(command, **k):
        if "-c" in command:          # v1.0.15: the import check
            return subprocess.CompletedProcess(command, 0, "", "")
        seen.append(list(command))
        # v1.0.15 (B597): the script names the stems itself.
        out = Path(command[3])
        (out / "vocals.wav").write_bytes(b"v")
        (out / "instrumental.wav").write_bytes(b"m")

    monkeypatch.setattr(proc, "run", run)
    stems = separation.separate_way(tmp_path / "a.wav", tmp_path / "w",
                                    separation.way_for("roformer"))
    assert seen[0][0] == str(python)
    assert seen[0][1] == str(separation.ROFORMER_SCRIPT)
    assert seen[0][4] == str(tmp_path / "models" / "audio_separator")
    assert seen[0][5] == separation.ROFORMER_MODELS["vocals"]
    assert stems["vocals"].name == "vocals.wav"
    assert stems["instrumental"].name == "instrumental.wav"
    assert separation.is_available(separation.way_for("roformer"))


def test_without_its_environment_roformer_is_not_available(
        tmp_path, monkeypatch) -> None:
    from modules import separation

    monkeypatch.setattr(separation, "roformer_env_dirs",
                        lambda: [tmp_path / "nothing"])
    assert not separation.is_available(separation.way_for("roformer"))
    with pytest.raises(separation.SeparationError):
        separation.separate_roformer(tmp_path / "a.wav", tmp_path / "w",
                                     "m.ckpt")


def _separation_project(tmp_path, method, monkeypatch, steps=()):
    from dataclasses import replace

    from modules import pipeline, profiles
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Nieuw")
    ensure_directories(paths)
    # v1.0.15 (B606): the way comes from the stand a project is made
    # with; the settings tab here chooses a stand that separates
    # ``method``.
    monkeypatch.setitem(profiles.PROFILES, "trial", dict(
        profiles.PROFILES["normal"], separation=method))
    config = default_config()
    config = replace(config, advanced=replace(config.advanced,
                                              profile="trial"))
    context = pipeline.AppContext(paths=paths, config=config,
                                  store=ProjectStore(paths.project_file))
    for name in steps:
        context.store.set_step(name, {"x": 1})
    return context


def test_a_new_project_takes_the_setting_and_keeps_it(
        tmp_path, monkeypatch) -> None:
    from dataclasses import replace

    from modules import pipeline, separation

    monkeypatch.setattr(separation, "is_available", lambda way=None: True)

    context = _separation_project(tmp_path, "careful", monkeypatch,
                                  steps=("source_original",))
    assert pipeline.separation_method(context) == "careful"
    later = replace(context, config=replace(
        context.config, advanced=replace(context.config.advanced,
                                         profile="quick")))
    context.store.set_meta("profile", dict(
        context.store.get_meta("profile"), separation="standard"))
    assert pipeline.separation_method(later) == "careful", "remembered"


def test_an_existing_project_stays_standard(tmp_path, monkeypatch) -> None:
    from modules import pipeline, separation

    monkeypatch.setattr(separation, "is_available", lambda way=None: True)

    context = _separation_project(tmp_path, "careful", monkeypatch,
                                  steps=("whisper_original",))
    assert pipeline.separation_method(context) == "standard"
    stems = _separation_project(tmp_path / "b", "careful", monkeypatch)
    (stems.paths.cache_dir / "demucs_stems_original").mkdir(parents=True)
    assert pipeline.separation_method(stems) == "standard"


def test_roformer_not_installed_falls_back_without_remembering(
        tmp_path, monkeypatch) -> None:
    from modules import pipeline, separation

    monkeypatch.setattr(separation, "roformer_python", lambda: None)
    context = _separation_project(tmp_path, "roformer", monkeypatch)
    assert pipeline.separation_method(context) == "standard"
    assert context.store.get_meta("separation") is None
    monkeypatch.setattr(separation, "roformer_python",
                        lambda: Path("python"))
    monkeypatch.setattr(separation, "roformer_problem", lambda: None)
    assert pipeline.separation_method(context) == "roformer"


def test_the_version_of_the_separator_is_read_from_its_environment(
        tmp_path, monkeypatch) -> None:
    from modules import separation, versions

    info = (tmp_path / "venv_separator" / "Lib" / "site-packages"
            / "audio_separator-0.47.0.dist-info")
    info.mkdir(parents=True)
    monkeypatch.setattr(separation, "roformer_env_dirs",
                        lambda: [tmp_path / "venv_separator"])
    assert "audio-separator" in versions.PACKAGES
    assert versions._version_of("audio-separator") == "0.47.0"
    monkeypatch.setattr(separation, "roformer_env_dirs", lambda: [])
    assert versions._version_of("audio-separator") == ""


def test_install_offers_the_roformer_environment() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "KaraokeToolGUI.bat").read_text(encoding="utf-8")
    # v1.0.20: the kind follows the card (cpu without one).
    assert "audio-separator[%SEPKIND%]" in text
    assert 'set "SEPKIND=cpu"' in text
    assert "%VENV%_separator" in text
    assert "tools\\roformer_separate.py --download" in text
    from modules import separation
    for model in separation.ROFORMER_MODELS.values():
        assert model in text


# --------------------------------------------------------------------------
# B592 - 1.5.14, which separation
# --------------------------------------------------------------------------

def test_a_dip_is_music_gone_where_the_original_plays_on() -> None:
    import numpy as np

    from modules import separation_trial as st

    rate = 1000
    mix = np.full((20 * rate, 1), 0.5, dtype=np.float32)
    mix[15 * rate:17 * rate] = 0.001          # a real band break
    music = np.full((20 * rate, 1), 0.3, dtype=np.float32)
    music[15 * rate:17 * rate] = 0.001        # quiet in the break: fine
    music[5 * rate:8 * rate] = 0.003          # gone while the band plays
    assert st.dip_seconds(music, rate, mix, rate) == pytest.approx(3.0)
    # Two rates frame alike.
    mix_fast = np.repeat(mix, 2, axis=0)
    assert st.dip_seconds(music, rate, mix_fast, 2 * rate) == \
        pytest.approx(3.0)


def test_the_voice_measures() -> None:
    from modules import separation_trial as st

    words = [{"start": 1.0, "end": 1.4, "confidence": 0.9},
             {"start": 5.1, "end": 5.5, "confidence": 0.5}]
    assert st.residue_words(words, [(0.5, 2.0)]) == 1
    assert st.line_hits(words, [1.1, 3.0, 5.0, 9.0]) == 50.0
    assert st.mean_certainty(words) == pytest.approx(0.7)


def test_1_5_14_measures_every_way_and_touches_no_project(
        tmp_path, monkeypatch) -> None:
    import hashlib
    import json

    from modules import ffmpeg, pipeline, separation, whisper
    from modules import separation_trial as st
    from tests.test_front_to_back import _install

    root, context = _install(tmp_path)

    def fingerprint():
        # v1.0.23 (B650): the work queue is in helper/kt_work, and rounds
        # going through it are work, not a project being written.
        return {str(p.relative_to(root)): hashlib.sha1(
            p.read_bytes()).hexdigest()
                for p in sorted(root.rglob("*")) if p.is_file()
                and p.relative_to(root).parts[:2] != ("helper", "kt_work")}

    before = fingerprint()
    monkeypatch.setattr(separation, "roformer_python", lambda: None)
    monkeypatch.setattr(separation, "is_available",
                        lambda way=None: way is None
                        or way.backend == "demucs")

    def convert(source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"wav")
        return target

    made = []

    def separate(audio, work, way, store=None):
        made.append(way.tag)
        work.mkdir(parents=True, exist_ok=True)
        for name in ("vocals", "no_vocals"):
            (work / f"{name}.wav").write_bytes(b"x")
        return {"vocals": work / "vocals.wav",
                "instrumental": work / "no_vocals.wav"}

    import numpy as np
    monkeypatch.setattr(ffmpeg, "convert_to_wav", convert)
    monkeypatch.setattr(ffmpeg, "encode_mp3", lambda s, t, *a, **k: (
        t.parent.mkdir(parents=True, exist_ok=True), t.write_bytes(b"mp3")))
    monkeypatch.setattr(separation, "separate_way", separate)
    from modules import audio
    monkeypatch.setattr(audio, "load_audio", lambda p: (
        np.full((1000, 1), 0.2, dtype=np.float32), 1000))
    monkeypatch.setattr(whisper, "transcribe", lambda *a, **k: (
        whisper.Segment(0, "ik zie", 1.0, 2.0,
                        (whisper.Word("ik", 1.0, 1.4, 0.9),
                         whisper.Word("zie", 1.4, 2.0, 0.8))),))
    monkeypatch.setattr(pipeline, "_language_for", lambda c, track: "nl")
    text = st.run(context, lambda *a: None, lambda: False)

    assert fingerprint() == before, "the projects are only read"
    assert sorted(set(made)) == ["htdemucs", "htdemucs_ft shifts=2"]
    assert st.t("sep_demucs_careful") in text
    assert st.t("separation_trial_install_hint") in text
    scrap = st.scratch_root(context)
    stored = json.loads((scrap / "results.json").read_text("utf-8"))
    assert not any("failed" in run for run in stored["runs"].values())
    assert (scrap / "listen" / "Song_A" / "demucs_careful_music.mp3").exists()
    assert not (scrap / "songs").exists() or not any(
        (scrap / "songs").rglob("*.wav")), "the converted originals go"
    # A second night measures nothing again.
    made.clear()
    st.run(context, lambda *a: None, lambda: False)
    assert made == []


def test_1_5_14_is_a_deliberate_choice() -> None:
    action = next(a for a in test_panel.ACTIONS if a.code == "1.5.14")
    # v1.0.25: done (all ten ways on all 22 songs), still on request.
    # v1.0.28: on again for the one new way.
    assert action.on_request and not action.heavy and not action.done


# --------------------------------------------------------------------------
# Found in review
# --------------------------------------------------------------------------

def test_the_first_anchor_stays_without_a_vocal_onset() -> None:
    """Without the onset as a fixed anchor, the first anchor may not go:
    the lines before the next one would fall back to 0:00."""
    left = tim.unstack_anchors({0: 10.0, 5: 11.0}, [1.0] * 6,
                               {0: 2.0, 5: 3.0})
    assert 0 in left


def test_a_word_of_a_marked_sentence_goes_to_the_sentence(qapp) -> None:
    lines = [_edit_line(7, [("ik", 0.0, 1.0), ("zie", 1.0, 2.0)])]
    lines[0]["restore"] = True
    canvas = _canvas(lines, "words")
    canvas._sel_cell = 1
    assert canvas.toggle_selected_restore()
    assert canvas.restore_rows() == [] and canvas.restore_words() == []


def test_the_original_stops_with_the_karaoke(qapp) -> None:
    pytest.importorskip("PySide6.QtMultimedia", exc_type=ImportError)
    from modules import damping_editor as de

    class _Player:
        def __init__(self, state):
            self.state = state

        def playbackState(self):
            return self.state

        def pause(self):
            self.state = de.QMediaPlayer.PlaybackState.PausedState

    class _Output:
        volume = 1.0

        def setVolume(self, value):
            self.volume = value

    class _Button:
        text = ""

        def setText(self, value):
            self.text = value

    editor = de.DampingEditorDialog.__new__(de.DampingEditorDialog)
    editor._player = _Player(de.QMediaPlayer.PlaybackState.StoppedState)
    editor._original_player = _Player(
        de.QMediaPlayer.PlaybackState.PlayingState)
    editor._original_output = _Output()
    editor._play_button = _Button()
    editor._tick()
    assert editor._original_player.state == \
        de.QMediaPlayer.PlaybackState.PausedState
    assert editor._original_output.volume == 0.0
