"""Tests for v0.106.0: B341, B342, B345, B346 and B347.

B341 - the busy colour lands on the button that starts the task; since
       B323 every step button stepped aside for its own task, because
       that one is already running by the time the hook has its turn.
B342 - a word cut in two on a segment boundary comes out of Whisper
       twice and is joined back together; "amen" added to the English
       hallucination list.
B345 - in the timing editor nothing can be dragged or stretched past
       the end of the song any more.
B346 - lines, blocks and original sentences can no longer pass each
       other (crowd may still overlap).
B347 - with a pause inside a line the last words lost their whole
       duration, because the pieces were walked with a different count
       than the one they were stored with.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline  # noqa: E402
from modules.timing import (  # noqa: E402
    Syllable, TimedLine, distribute_over_windows, piece_groups, word_spans,
)
from modules.whisper import Segment, Word  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _context(tmp_path: Path, name: str = "Proef"):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=name)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B347: the word timing around a pause inside the line
# --------------------------------------------------------------------------

#: Exactly as it stands in timing.json: finer pieces than the syllables
#: split_line takes from the word text (25 against 10).
_PIECES = ["I", "k", " g", "i", "ng", " a", "l", " j", "a", "r", "e", "n",
           " m", "e", "t", " d", "e", " R", "ei", "g", "e", "r", "s",
           " m", "ee"]


def _line_with_a_pause() -> TimedLine:
    step = (86.351 - 81.031) / len(_PIECES)
    syllables = tuple(
        Syllable(text=piece, start=round(81.031 + i * step, 3),
                 end=round(81.031 + (i + 1) * step, 3))
        for i, piece in enumerate(_PIECES))
    return TimedLine(index=20, text="Ik ging al jaren met de Zangers mee",
                     crowd=False, syllables=syllables)


def test_piece_groups_counts_the_stored_pieces() -> None:
    """B347: the grouping follows the space, not the word text."""
    groups = piece_groups(_line_with_a_pause().syllables)
    assert [len(g) for g in groups] == [2, 3, 2, 5, 3, 2, 6, 2]
    assert sum(len(g) for g in groups) == len(_PIECES)


def test_no_word_loses_its_duration_at_a_pause() -> None:
    """B347: four of the eight words sat on start == end."""
    windows = [(81.031, 82.582), (84.686, 86.351)]
    out = distribute_over_windows(_line_with_a_pause(), windows)
    assert len(out.syllables) == len(_PIECES)
    for text, start, end in word_spans(out.syllables):
        assert end - start > 0.001, f"{text} has no duration"
        assert end >= start, f"{text} runs backwards"


def test_the_words_land_in_the_sung_halves() -> None:
    """B347: the pause belongs between the words, not inside one."""
    pause = (82.582, 84.686)
    out = distribute_over_windows(_line_with_a_pause(),
                                  [(81.031, 82.582), (84.686, 86.351)])
    words = word_spans(out.syllables)
    assert len(words) == 8
    for _text, start, end in words:
        assert not (pause[0] < start < pause[1]), "word starts in the pause"
        assert not (pause[0] < end < pause[1]), "word ends in the pause"
    assert words[0][1] == pytest.approx(81.031, abs=0.01)
    assert words[-1][2] == pytest.approx(86.351, abs=0.01)


# --------------------------------------------------------------------------
# B345/B346: bounds and order in the timing editor
# --------------------------------------------------------------------------

_DURATION = 20.0


def _lines(count: int = 3) -> list[dict]:
    return [{"text": f"regel {i + 1}", "crowd": False, "block": 0,
             "disabled": False,
             "syllables": [{"text": "a", "start": 1.0 + 2 * i,
                            "end": 2.0 + 2 * i, "held": False,
                            "stress": False, "crowd": False}]}
            for i in range(count)]


def _span(line: dict) -> tuple[float, float]:
    return (line["syllables"][0]["start"], line["syllables"][-1]["end"])


def _canvas(lines: list[dict], originals: list[dict] | None = None):
    import numpy as np
    from modules.timing_editor import TimingCanvas

    peaks = np.zeros(2000)
    canvas = TimingCanvas(peaks, peaks, _DURATION, lines, lambda *_: None,
                          originals=originals or [],
                          original_duration=_DURATION, vocal_peaks=peaks)
    canvas._cells = [{"text": r["text"], "start": _span(r)[0],
                      "end": _span(r)[1], "crowd": bool(r["crowd"]),
                      "rows": [i], "uit": False}
                     for i, r in enumerate(lines)]
    return canvas


def _drag(canvas, cell: int, mode: str, start: float, to: float) -> None:
    """One drag movement, the way the mouse delivers it."""
    from PySide6.QtCore import QPointF

    class _Event:
        def __init__(self, x: float) -> None:
            self._point = QPointF(x, 0.0)

        def position(self):
            return self._point

    canvas._drag = ("cel", cell, mode, start)
    canvas.mouseMoveEvent(_Event(to * canvas._pps))


def test_a_line_cannot_be_stretched_past_the_end(qapp) -> None:
    """B345: stretching to 80 s in a song of 20 s."""
    lines = _lines()
    _drag(_canvas(lines), 2, "rechts", 6.0, 80.0)
    assert _span(lines[2])[1] == pytest.approx(_DURATION)


def test_a_line_cannot_be_dragged_past_the_end(qapp) -> None:
    """B345: moving it to 200 s simply put it down on 199.5."""
    lines = _lines()
    _drag(_canvas(lines), 2, "verplaats", 5.5, 200.0)
    start, end = _span(lines[2])
    assert end <= _DURATION + 1e-6
    assert end - start == pytest.approx(1.0)


def test_a_line_cannot_pass_its_predecessor(qapp) -> None:
    """B346: clamp_span let it drop into the free gap before line 1."""
    lines = _lines()
    _drag(_canvas(lines), 1, "verplaats", 3.5, 0.4)
    assert _span(lines[1])[0] >= _span(lines[0])[1] - 1e-6


def test_a_line_cannot_pass_its_successor(qapp) -> None:
    """B346: the same rule, the other way round."""
    lines = _lines()
    _drag(_canvas(lines), 0, "verplaats", 1.5, 9.0)
    assert _span(lines[0])[1] <= _span(lines[1])[0] + 1e-6


def test_a_block_cannot_pass_its_neighbour(qapp) -> None:
    """B346: in the block view the overlap check was skipped."""
    lines = _lines()
    canvas = _canvas(lines)
    canvas.set_view_mode("blocks")
    canvas._cells = [
        {"text": "blok 0", "start": 1.0, "end": 4.0, "crowd": False,
         "rows": [0, 1], "uit": False},
        {"text": "blok 1", "start": 5.0, "end": 6.0, "crowd": False,
         "rows": [2], "uit": False}]
    _drag(canvas, 1, "verplaats", 5.5, 0.5)
    assert _span(lines[2])[0] >= _span(lines[1])[1] - 1e-6


def test_a_crowd_line_may_overlap_but_not_pass(qapp) -> None:
    """B346: 'never overlap, crowd excepted' - passing never."""
    lines = _lines()
    lines[2]["crowd"] = True
    _drag(_canvas(lines), 2, "verplaats", 5.5, 0.5)
    start, _end = _span(lines[2])
    # May lie over the line before it ...
    assert start < _span(lines[1])[1]
    # ... but may not come out in front of where that one begins.
    assert start >= _span(lines[1])[0] - 1e-6


def test_an_original_sentence_stays_in_the_song_and_in_place(qapp) -> None:
    """B345/B346 on the original track."""
    from PySide6.QtCore import QPointF

    lines = _lines()
    originals = [{"text": "o1", "start": 1.0, "end": 2.0, "rows": [0]},
                 {"text": "o2", "start": 3.0, "end": 4.0, "rows": [1]},
                 {"text": "o3", "start": 5.0, "end": 6.0, "rows": [2]}]
    canvas = _canvas(lines, originals)

    class _Event:
        def __init__(self, x: float) -> None:
            self._point = QPointF(x, 0.0)

        def position(self):
            return self._point

    canvas._drag = ("original", 2, "rechts", 6.0)
    canvas.mouseMoveEvent(_Event(90.0 * canvas._pps))
    assert originals[2]["end"] <= _DURATION + 1e-6

    canvas._drag = ("original", 1, "verplaats", 3.5)
    canvas.mouseMoveEvent(_Event(0.4 * canvas._pps))
    assert originals[1]["start"] >= originals[0]["end"] - 1e-6


# --------------------------------------------------------------------------
# B341: the busy colour
# --------------------------------------------------------------------------

def test_the_button_that_starts_a_task_turns_yellow(qapp, tmp_path) -> None:
    """B341: through a REAL click, because that is where the hole was.

    The old test called ``_mark_busy_click`` straight out with an empty
    ``_worker`` and so did not see that in reality the hook only has
    its turn after the handler of the button itself - that is, when the
    task is already running.
    """
    import time

    from PySide6.QtWidgets import QPushButton

    from modules import gui

    window = gui.MainWindow(_context(tmp_path, "Bezig1"))
    button = QPushButton("proef", window)
    button.pressed.connect(window._remember_worker)
    button.clicked.connect(
        lambda: window._run(lambda progress, message: time.sleep(0.2),
                            lambda _r: None))
    button.clicked.connect(lambda _=False: window._mark_busy_click(button))
    button.click()
    try:
        assert window._worker.isRunning()
        assert button in window._busy_buttons
        assert button.styleSheet() != ""
    finally:
        window._worker.wait()


def test_a_button_does_not_take_the_colour_from_a_running_task(qapp,
                                                               tmp_path
                                                               ) -> None:
    """B323 still stands: someone else's task keeps the colour."""
    from PySide6.QtWidgets import QPushButton

    from modules import gui

    window = gui.MainWindow(_context(tmp_path, "Bezig2"))
    busy = window._step_buttons[0]

    class _Running:
        def isRunning(self) -> bool:
            return True

    window._worker = _Running()
    window._busy_buttons.add(busy)
    window._apply_busy_style(busy, True)

    other = QPushButton("andere", window)
    window._remember_worker()          # the press before the click
    window._mark_busy_click(other)
    assert other not in window._busy_buttons
    assert busy in window._busy_buttons


# --------------------------------------------------------------------------
# B342: the word cut in two on the segment boundary
# --------------------------------------------------------------------------

def _segment(index: int, words: list[Word]) -> Segment:
    return Segment(index=index, text=" ".join(w.text for w in words),
                   start=words[0].start, end=words[-1].end,
                   words=tuple(words))


def test_a_word_cut_in_two_is_joined_back_together() -> None:
    """B342: the measured "reflections"/"Collections," of Lied D."""
    left = _segment(12, [Word("Golden", 81.031, 81.335, 0.516),
                         Word("reflections", 81.355, 81.740, 0.220)])
    right = _segment(13, [Word("Collections,", 81.760, 82.582, 0.622),
                          Word("given", 84.686, 85.127, 0.794)])
    out = pipeline._merge_boundary_duplicates((left, right))
    assert [w.text for w in out[0].words] == ["Golden"]
    assert out[0].end == pytest.approx(81.335)
    first = out[1].words[0]
    assert first.text == "Collections,"
    assert first.start == pytest.approx(81.355)   # the real onset
    assert first.end == pytest.approx(82.582)


def test_a_joined_word_lasts_what_it_lasts_elsewhere() -> None:
    """B342: the proof that it is one word - 1.29 s against 1.31/1.36."""
    left = _segment(24, [Word("up,", 135.232, 135.695, 0.803),
                         Word("dreaming", 136.178, 136.420, 0.253)])
    right = _segment(25, [Word("Dreaming", 136.621, 137.466, 0.686),
                          Word("of", 137.869, 137.909, 0.000)])
    out = pipeline._merge_boundary_duplicates((left, right))
    merged = out[1].words[0]
    assert merged.end - merged.start == pytest.approx(1.288, abs=0.005)


def test_a_real_repetition_stays_standing() -> None:
    """B342: "Tickle, tickle" sits inside one segment and stays whole."""
    segment = _segment(8, [Word("Tickle,", 56.680, 57.560, 0.640),
                           Word("tickle,", 57.621, 57.981, 0.490)])
    out = pipeline._merge_boundary_duplicates((segment,))
    assert len(out[0].words) == 2


def test_a_wide_gap_is_not_joined_together() -> None:
    """B342: stuffing 0.70 s of silence inside a word is no gain."""
    left = _segment(1, [Word("I'm", 40.0, 40.2, 0.700),
                        Word("sure", 40.30, 40.38, 0.010)])
    right = _segment(2, [Word("sure.", 41.082, 41.802, 0.620)])
    out = pipeline._merge_boundary_duplicates((left, right))
    assert [w.text for w in out[0].words] == ["I'm", "sure"]
    assert out[1].words[0].start == pytest.approx(41.082)


def test_a_confident_word_is_not_taken_for_a_stub() -> None:
    """B342: only a word that is shorter AND less sure counts as a
    stub."""
    left = _segment(1, [Word("oh", 10.0, 10.4, 0.900),
                        Word("no", 10.5, 11.2, 0.880)])
    right = _segment(2, [Word("No", 11.30, 11.60, 0.910)])
    out = pipeline._merge_boundary_duplicates((left, right))
    assert len(out[0].words) == 2


def test_amen_stands_in_the_english_hallucination_list() -> None:
    """B342: 0.11 s, confidence 0.032, two beats after the singing."""
    from modules import phonetics

    assert "amen" in phonetics.word_list("en", "hallucinations")
    assert "amen" not in phonetics.word_list("nl", "hallucinations")
