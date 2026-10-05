"""The timing editor edits words and syllables (v1.0.13).

The word view was for reading only (B127), and stretching a sentence
scales all its pieces by the same factor - so the division INSIDE a
sentence was whatever the automatic timing made of it, and a pause
between two sung words could not be made by hand. Now a word, or a
syllable, is dragged and stretched on its own, under exactly the rules
the sentence view has towards the neighbours.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import timing  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _piece(text, start, end, **extra):
    return dict({"text": text, "start": start, "end": end}, **extra)


def _word(text, start, end, lead=True):
    """One word as letter pieces, the way the timing stores them."""
    step = (end - start) / len(text)
    return [_piece((" " if lead and n == 0 else "") + ch,
                   round(start + n * step, 3),
                   round(start + (n + 1) * step, 3))
            for n, ch in enumerate(text)]


def _line(index, words, crowd=False, **extra):
    pieces = []
    for n, (text, start, end) in enumerate(words):
        pieces += _word(text, start, end, lead=n > 0)
    return dict({"index": index, "text": " ".join(w[0] for w in words),
                 "crowd": crowd, "syllables": pieces}, **extra)


def _canvas(lines, mode="words"):
    from modules.timing_editor import TimingCanvas

    canvas = TimingCanvas(np.zeros(100, dtype=np.float32), None, 30.0,
                          lines, on_seek=lambda *_: None)
    canvas.set_view_mode(mode)
    canvas._cells = timing.editor_view_cells(lines, mode)
    return canvas


def _cell(canvas, text):
    return next(c for c in canvas._cells if c["text"] == text)


def _span(line, cell):
    group = cell["pieces"]
    return (line["syllables"][group[0]]["start"],
            line["syllables"][group[-1]]["end"])


def _drag(canvas, cell, mode, delta):
    canvas._move_pieces(cell["rows"][0], cell["pieces"], mode, delta)


def test_the_syllables_of_a_word_are_found_in_its_letters() -> None:
    pieces = _word("jalala", 0.0, 1.2, lead=False)
    assert timing.syllable_groups(pieces) == [[0, 1], [2, 3], [4, 5]]
    cells = timing.editor_view_cells([_line(0, [("jalala", 0.0, 1.2)])],
                                     "syllables")
    assert [c["text"] for c in cells] == ["ja", "la", "la"]
    assert [c["pieces"] for c in cells] == [[0, 1], [2, 3], [4, 5]]


def test_stretching_a_word_moves_only_that_word(qapp) -> None:
    line = _line(0, [("ja", 1.0, 2.0), ("la", 2.0, 3.0), ("hey", 3.0, 4.0)])
    canvas = _canvas([line])
    others = [dict(p) for p in line["syllables"]]

    _drag(canvas, _cell(canvas, "ja"), "rechts", -0.5)

    first = _cell(canvas, "ja")
    assert _span(line, first) == pytest.approx((1.0, 1.5))
    # Its own letters scale along, evenly as they were.
    assert line["syllables"][0]["end"] == pytest.approx(1.25)
    # Nothing else moved: a pause of half a second now lies before "la".
    assert line["syllables"][2:] == others[2:]


def test_a_word_stops_against_its_neighbour(qapp) -> None:
    line = _line(0, [("ja", 1.0, 2.0), ("la", 2.5, 3.0), ("hey", 3.0, 4.0)])
    canvas = _canvas([line])

    _drag(canvas, _cell(canvas, "la"), "verplaats", -2.0)
    assert _span(line, _cell(canvas, "la")) == pytest.approx((2.0, 2.5))

    _drag(canvas, _cell(canvas, "la"), "rechts", 5.0)
    assert _span(line, _cell(canvas, "la")) == pytest.approx((2.0, 3.0))


def test_the_first_word_follows_the_sentence_rules(qapp) -> None:
    before = _line(0, [("oh", 1.0, 2.0)])
    line = _line(1, [("ja", 3.0, 4.0), ("la", 4.0, 5.0)])
    canvas = _canvas([before, line])

    # Stretched left, it stops at the end of the sentence before it -
    # exactly where the sentence view stops the whole sentence.
    _drag(canvas, _cell(canvas, "ja"), "links", -5.0)
    assert _span(line, _cell(canvas, "ja"))[0] == pytest.approx(2.0)
    assert canvas._without_overlap([1], 0.0, 5.0, "links")[0] == \
        pytest.approx(2.0)


def test_a_crowd_line_may_overlap_but_not_pass(qapp) -> None:
    before = _line(0, [("oh", 1.0, 2.0)])
    line = _line(1, [("ja", 3.0, 4.0), ("la", 4.0, 5.0)], crowd=True)
    canvas = _canvas([before, line])

    _drag(canvas, _cell(canvas, "ja"), "links", -5.0)
    # Over the end of "oh", but not before its start.
    assert _span(line, _cell(canvas, "ja"))[0] == pytest.approx(1.0)


def test_a_disabled_neighbour_may_be_stretched_over(qapp) -> None:
    before = _line(0, [("oh", 1.0, 2.0)], disabled=True)
    line = _line(1, [("ja", 3.0, 4.0), ("la", 4.0, 5.0)])
    canvas = _canvas([before, line])

    _drag(canvas, _cell(canvas, "ja"), "links", -2.5)
    assert _span(line, _cell(canvas, "ja"))[0] == pytest.approx(0.5)


def test_a_syllable_is_dragged_inside_its_word(qapp) -> None:
    line = _line(0, [("jalala", 1.0, 2.2)])
    canvas = _canvas([line], "syllables")
    middle = canvas._cells[1]
    assert middle["text"] == "la"

    _drag(canvas, middle, "rechts", -0.2)
    assert _span(line, middle) == pytest.approx((1.4, 1.6))
    _drag(canvas, middle, "verplaats", 0.5)

    # It moves, but not into the syllable after it, and the first one
    # does not move at all.
    assert _span(line, middle) == pytest.approx((1.6, 1.8))
    assert _span(line, canvas._cells[0]) == pytest.approx((1.0, 1.4))


def test_a_background_piece_is_not_a_wall_and_not_draggable(qapp) -> None:
    line = _line(0, [("ja", 1.0, 2.0), ("la", 2.0, 3.0)])
    line["syllables"] += [_piece(" oeh", 2.2, 2.6, bg=True)]
    canvas = _canvas([line])
    bg = next(c for c in canvas._cells if c.get("bg"))
    assert bg["rows"] == []

    _drag(canvas, _cell(canvas, "ja"), "rechts", 0.5)
    assert _span(line, _cell(canvas, "ja"))[1] == pytest.approx(2.0)
    _drag(canvas, _cell(canvas, "la"), "links", -0.5)
    assert _span(line, _cell(canvas, "la"))[0] == pytest.approx(2.0)


def test_the_original_lane_follows_a_moved_first_word(qapp) -> None:
    from modules.timing_editor import TimingCanvas

    line = _line(0, [("ja", 3.0, 4.0), ("la", 4.0, 5.0)])
    originals = [{"text": "ja la", "start": 3.0, "end": 5.0, "rows": [0]}]
    canvas = TimingCanvas(np.zeros(100, dtype=np.float32), None, 30.0,
                          [line], on_seek=lambda *_: None,
                          originals=originals)
    canvas.set_view_mode("words")
    canvas._cells = timing.editor_view_cells([line], "words")

    _drag(canvas, _cell(canvas, "ja"), "links", -1.0)
    assert originals[0]["start"] == pytest.approx(2.0)


def test_the_mouse_grabs_a_word_in_the_word_view(qapp) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent
    from modules.timing_editor import _LANES_TOP

    line = _line(0, [("ja", 1.0, 2.0), ("la", 2.0, 3.0)])
    canvas = _canvas([line])
    pps = canvas.pixels_per_second
    y = _LANES_TOP + 10

    def event(kind, x):
        return QMouseEvent(kind, QPointF(x, y), QPointF(x, y),
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)

    canvas.mousePressEvent(event(QEvent.Type.MouseButtonPress, 1.5 * pps))
    assert canvas._drag is not None and canvas._drag[0] == "piece"
    canvas.mouseMoveEvent(event(QEvent.Type.MouseMove, 1.3 * pps))
    canvas.mouseReleaseEvent(event(QEvent.Type.MouseButtonRelease,
                                   1.3 * pps))
    assert _span(line, _cell(canvas, "ja")) == pytest.approx((0.8, 1.8))
    assert canvas._drag is None and canvas._drag_pieces is None


def test_the_block_view_keeps_the_same_rules(qapp) -> None:
    """Asked for with this round: blocks may not overlap or pass their
    neighbours either - checked here for a block against a sentence."""
    first = _line(0, [("oh", 1.0, 2.0)], block=0)
    second = _line(1, [("ja", 3.0, 4.0)], block=1)
    third = _line(2, [("la", 4.0, 5.0)], block=1)
    canvas = _canvas([first, second, third], "blocks")
    start, _end = canvas._without_overlap([1, 2], 0.5, 3.5, "verplaats")
    assert start >= 2.0 - 1e-9
    assert canvas._keep_in_order([1, 2], -3.0, -1.0, "verplaats")[0] >= 1.0


def test_a_piece_with_no_room_is_not_pushed_over_its_neighbour(qapp) -> None:
    line = _line(0, [("ja", 1.0, 1.02), ("la", 1.02, 2.0)])
    canvas = _canvas([line], "syllables")
    first = canvas._cells[0]
    for _n in range(5):
        _drag(canvas, first, "rechts", 0.1)
    assert _span(line, first)[1] <= line["syllables"][2]["start"] + 1e-9
    _drag(canvas, canvas._cells[1], "links", -0.5)
    assert _span(line, canvas._cells[1])[0] >= _span(line, first)[1] - 1e-9


def test_a_word_of_no_length_can_be_stretched(qapp) -> None:
    line = _line(0, [("ja", 1.0, 1.0), ("la", 2.0, 3.0)])
    canvas = _canvas([line])
    _drag(canvas, _cell(canvas, "ja"), "rechts", 0.5)
    assert _span(line, _cell(canvas, "ja")) == pytest.approx((1.0, 1.5))
    assert line["syllables"][0]["end"] == pytest.approx(1.25)


def test_a_sentence_does_not_get_shorter_than_in_the_sentence_view(
        qapp) -> None:
    from modules.timing_editor import _MIN_LINE_S

    line = _line(0, [("oh", 1.0, 1.5)])
    canvas = _canvas([line])
    _drag(canvas, _cell(canvas, "oh"), "rechts", -0.45)
    start, end = _span(line, _cell(canvas, "oh"))
    assert end - start >= _MIN_LINE_S - 1e-9
