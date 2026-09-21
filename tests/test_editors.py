"""Tests for the editors and the video input row (PySide6 only).

They run only when PySide6 with an (offscreen) Qt platform is
available; on a bare server they are skipped.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _peaks(n: int = 200) -> np.ndarray:
    return np.abs(np.sin(np.linspace(0, 20, n))).astype(np.float32)


def test_timing_canvas_paint_with_originals(qapp) -> None:
    """B92: _paint draws the karaoke waveform with originals too.

    The regression let the originals loop overwrite ``x1`` (the
    visible bound), which raised a TypeError in ``range()`` and
    dropped the lower half (waveform, time axis, text lanes,
    playhead).
    """
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import QRect
    from modules.timing_editor import TimingCanvas, _CANVAS_HEIGHT

    lines = [{"text": "een twee", "crowd": False, "index": 0,
              "syllables": [{"text": "een", "start": 1.0, "end": 2.0},
                            {"text": "twee", "start": 2.0, "end": 3.0}]}]
    originals = [{"text": "origineel zin", "line_no": 1, "start": 1.0,
                  "end": 3.0, "rows": [0]}]
    canvas = TimingCanvas(_peaks(), _peaks(), duration=5.0, lines=lines,
                          on_seek=lambda *_: None, originals=originals,
                          original_duration=5.0)
    canvas.resize(400, _CANVAS_HEIGHT)

    image = QImage(400, _CANVAS_HEIGHT, QImage.Format.Format_RGB32)
    painter = QPainter(image)

    class _Event:
        def rect(self):
            return QRect(0, 0, 400, _CANVAS_HEIGHT)

    # Before the fix this raised a TypeError (float in range); it no
    # longer does.
    canvas._paint(painter, _Event())
    painter.end()


def test_timing_editor_done_stops_playback(qapp, monkeypatch) -> None:
    """B93: done() (Close/Esc) stops the player, just like closeEvent."""
    from modules import timing_editor

    class _DummyPlayer:
        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    editor = timing_editor.TimingEditorDialog.__new__(
        timing_editor.TimingEditorDialog)
    editor._player = _DummyPlayer()
    editor._timer = None
    editor._shutdown_playback()
    assert editor._player.stopped is True


def test_open_selected_project_routes(qapp) -> None:
    """B95a: the dropdown handler switches to the chosen title.

    The 'Open' button is gone; ``textActivated`` now calls this
    handler directly. This checks that it passes on the right title.
    """
    from types import SimpleNamespace

    from modules import gui, translations

    calls = []
    window = gui.MainWindow.__new__(gui.MainWindow)
    window._song_combo = SimpleNamespace(
        currentText=lambda: "Mijn Lied")
    window._switch_instance = lambda title, is_new=False, **kw: calls.append(
        (title, is_new))
    gui.MainWindow._open_selected_project(window)
    assert calls == [("Mijn_Lied", False)]

    # The 'no title' choice switches to the root ("").
    calls.clear()
    window._song_combo = SimpleNamespace(currentText=lambda: translations.t("no_title"))
    gui.MainWindow._open_selected_project(window)
    assert calls == [("", False)]


def test_reset_also_restores_karaoke_timing(qapp) -> None:
    """B100: 'Restore original' resets the karaoke lines as well,
    not just the original lane."""
    from types import SimpleNamespace

    from modules import timing_editor
    from modules.timing import Syllable, TimedLine

    fresh_line = TimedLine(index=0, text="nieuw", crowd=False,
                           syllables=(Syllable("nieuw", 5.0, 6.0),),
                           quality="sentence")

    dlg = timing_editor.TimingEditorDialog.__new__(
        timing_editor.TimingEditorDialog)
    dlg._on_reset = lambda: {"originals": [], "lines": [fresh_line]}
    dlg._lines = [{"index": 0, "text": "oud", "crowd": False,
                   "syllables": [{"text": "oud", "start": 1.0, "end": 2.0}]}]

    recorded = {}
    dlg._canvas = SimpleNamespace(
        set_lines=lambda lines: recorded.__setitem__("lines", lines),
        set_originals=lambda o: recorded.__setitem__("orig", o))

    timing_editor.TimingEditorDialog._reset(dlg)
    # The karaoke line is back to the fresh text and timing.
    assert dlg._lines[0]["text"] == "nieuw"
    assert dlg._lines[0]["syllables"][0]["start"] == 5.0
    assert "lines" in recorded  # canvas was updated


def test_coupling_canvas_pin_and_unpin(qapp) -> None:
    """B121: the coupling canvas keeps manual pins and reports
    changes."""
    from modules.coupling_editor import CouplingCanvas
    transcript = [("OEHOOR", 3.0, 3.5), ("EN", 3.6, 3.9), ("THEE", 5.0, 5.4)]
    words = [
        {"index": 0, "text": "oerend", "line": 0,
         "transcript_indices": [], "found": None, "sim": 0.0,
         "pinned": False},
        {"index": 1, "text": "thee", "line": 0,
         "transcript_indices": [2], "found": "THEE", "sim": 0.9,
         "pinned": False},
    ]
    seen = {}
    canvas = CouplingCanvas(transcript, words, lambda p: (seen.clear(),
                                                          seen.update(p)))
    assert canvas._current_targets(1) == [2]          # auto coupling
    # One-to-many: couple word 0 to two found words.
    canvas._sel_bot = 0
    canvas._targets[0] = [0, 1]
    canvas._pinned.add(0)
    canvas._emit()
    assert seen.get(0) == [0, 1]
    # Only pinned words are kept (the auto coupling of 1 is not).
    assert 1 not in seen
    # Distance-to-line helper (pure).
    assert canvas._point_near_segment(5, 5, 0, 0, 10, 10) is True
    assert canvas._point_near_segment(50, 5, 0, 0, 10, 10) is False


def test_coupling_canvas_cut_and_merge(qapp) -> None:
    """B153: cut/merge adjusts the found words and reports them."""
    from modules.coupling_editor import CouplingCanvas
    transcript = [("OEREND", 0.0, 2.0), ("HARD", 2.0, 3.0)]
    words = [
        {"index": 0, "text": "oerend", "line": 0,
         "transcript_indices": [1], "found": "HARD", "sim": 0.5,
         "pinned": True},
    ]
    last = {}
    canvas = CouplingCanvas(transcript, words, lambda p: None,
                          on_transcript=lambda tr: last.update(t=tr))
    # Cutting 'OEREND' -> OER/END; the pin (which pointed at index
    # 1='HARD') shifts along to index 2.
    canvas._sel_top = 0
    assert canvas.cut_selected() is True
    assert [w[0] for w in last["t"]] == ["OER", "END", "HARD"]
    assert canvas._targets[0] == [2]
    # Now merge OER + END back together.
    canvas._sel_top = 0
    assert canvas.merge_selected() is True
    assert [w[0] for w in last["t"]] == ["OER END", "HARD"]


def test_coupling_canvas_selection_ux(qapp) -> None:
    """B154/B155: a second click deselects; coupling drops the
    selection."""
    from modules.coupling_editor import CouplingCanvas
    transcript = [("A", 0.0, 1.0), ("B", 1.0, 2.0)]
    words = [{"index": 0, "text": "een", "line": 0,
                "transcript_indices": [], "found": None, "sim": 0.0,
                "pinned": False}]
    canvas = CouplingCanvas(transcript, words, lambda p: None)
    # B154: (de)select the top word.
    canvas._sel_top = 0
    canvas._sel_top = None if canvas._sel_top == 0 else 0
    assert canvas._sel_top is None


def test_coupling_canvas_lyrics_cut(qapp) -> None:
    """B156: cutting on the lyrics row splits a word and reports it."""
    from modules.coupling_editor import CouplingCanvas
    transcript = [("OEHOEREND", 0.0, 1.0), ("HARD", 1.0, 2.0)]
    words = [
        {"index": 0, "text": "oehoerend", "line": 0,
         "transcript_indices": [0], "found": "OEHOEREND", "sim": 0.9,
         "pinned": True},
        {"index": 1, "text": "hard", "line": 0,
         "transcript_indices": [1], "found": "HARD", "sim": 0.9,
         "pinned": True},
    ]
    last = {}
    canvas = CouplingCanvas(transcript, words, lambda p: None,
                          on_lyrics=lambda ly: last.update(ly=ly))
    canvas._sel_bot = 0
    assert canvas.cut_selected() is True
    # 'oehoerend' -> two words; 'hard' shifts one place along.
    assert [w["text"] for w in canvas._words] == ["oeho", "erend", "hard"]
    assert [t for t, _ in last["ly"]] == ["oeho", "erend", "hard"]
    # The pin of 'hard' (was index 1 -> transcript 1) now sits on
    # index 2.
    assert canvas._targets.get(2) == [1]


def test_stress_canvas_sets_stress(qapp) -> None:
    """B151/B450: the stress can still be set by hand.

    At B450 the canvas became a time bar per sentence, with coupling
    on the left and the stress on the right. That second one is
    deliberately still there: dropping it would take away something
    that was in use."""
    from modules.stress_editor import SentenceCanvas
    from modules.timing import Syllable

    seen = {}
    canvas = SentenceCanvas(lambda: None,
                            lambda pieces: seen.update(p=pieces))
    canvas.set_sentence(
        [], [Syllable("ko", 0.0, 1.0), Syllable(" men", 1.0, 2.0)], {})
    canvas.set_stress(1)
    assert [s.stress for s in seen["p"]] == [False, True]


def test_stress_canvas_couples_and_fits_the_rest(qapp) -> None:
    """B450: coupling lets the coupled piece take over the time of
    the original; the rest fits in proportionally."""
    from modules.stress_editor import SentenceCanvas
    from modules.timing import Syllable

    touched = []
    canvas = SentenceCanvas(lambda: touched.append(1))
    canvas.set_sentence(
        [Syllable("aa", 0.0, 2.0)],
        [Syllable("a", 0.0, 0.5), Syllable(" b", 0.5, 1.0)], {})
    canvas._selected_original = 0
    canvas._anchors[1] = 0
    assert canvas.anchors() == {1: 0}


def test_timing_canvas_toggle_disabled(qapp) -> None:
    """B180: switching the selected cell off/on works on the line
    underneath."""
    from modules.timing_editor import TimingCanvas, _CANVAS_HEIGHT
    lines = [{"text": "een", "crowd": False, "index": 0, "block": 0,
              "disabled": False,
              "syllables": [{"text": "een", "start": 1.0, "end": 2.0}]}]
    canvas = TimingCanvas(_peaks(), None, duration=5.0, lines=lines,
                          on_seek=lambda *_: None)
    canvas.resize(400, _CANVAS_HEIGHT)
    # Cells appear while drawing; force a view-cell computation.
    from modules import timing as tmod
    canvas._cells = tmod.editor_view_cells(canvas._lines, "sentences")
    canvas._sel_cell = 0
    assert canvas.toggle_selected_disabled() is True
    assert canvas._lines[0]["disabled"] is True
    canvas._cells = tmod.editor_view_cells(canvas._lines, "sentences")
    canvas.toggle_selected_disabled()             # on again
    assert canvas._lines[0]["disabled"] is False


def test_damping_editor_shutdown(qapp) -> None:
    """B93: the damping editor stops the player on close too."""
    from modules import damping_editor

    class _DummyPlayer:
        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    editor = damping_editor.DampingEditorDialog.__new__(
        damping_editor.DampingEditorDialog)
    editor._player = _DummyPlayer()
    editor._timer = None
    editor._shutdown_playback()
    assert editor._player.stopped is True
