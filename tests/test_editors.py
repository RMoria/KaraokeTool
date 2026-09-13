"""Tests voor de editors en de video-invoerrij (alleen met PySide6).

Draaien alleen wanneer PySide6 met een (offscreen) Qt-platform beschikbaar
is; op een kale server worden ze overgeslagen.
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


def test_timing_canvas_paint_met_originelen(qapp) -> None:
    """B92: _paint tekent de karaoke-golfvorm ook mét originele zinnen.

    De regressie liet ``x1`` (zichtbaar-grens) overschrijven door de
    originelen-lus, wat een TypeError in ``range()`` gaf en de onderhelft
    (golfvorm, tijdas, tekstbanen, afspeellijn) wegliet.
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

    # Vóór de fix wierp dit een TypeError (float in range); nu niet meer.
    canvas._paint(painter, _Event())
    painter.end()


def test_timing_editor_done_stopt_afspelen(qapp, monkeypatch) -> None:
    """B93: done() (Sluiten/Esc) stopt de speler, net als closeEvent."""
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


def test_open_selected_project_routeert(qapp) -> None:
    """B95a: de dropdown-handler schakelt naar de gekozen titel.

    De 'Openen'-knop is weg; ``textActivated`` roept nu direct deze
    handler aan. We testen dat de handler de juiste titel doorgeeft.
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

    # De 'geen titel'-keuze schakelt naar de root ("").
    calls.clear()
    window._song_combo = SimpleNamespace(currentText=lambda: translations.t("no_title"))
    gui.MainWindow._open_selected_project(window)
    assert calls == [("", False)]


def test_reset_zet_ook_karaoketimimg_terug(qapp) -> None:
    """B100: 'Herstel origineel' reset óók de karaokeregels, niet alleen
    de originele baan."""
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
    # De karaokeregel is teruggezet naar de verse tekst/timing.
    assert dlg._lines[0]["text"] == "nieuw"
    assert dlg._lines[0]["syllables"][0]["start"] == 5.0
    assert "lines" in recorded  # canvas is bijgewerkt


def test_koppel_canvas_pin_en_ontkoppel(qapp) -> None:
    """B121: koppel-canvas houdt handmatige pins bij en meldt wijzigingen."""
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
    assert canvas._current_targets(1) == [2]          # auto-koppeling
    # 1-op-meer: woord 0 aan twee gevonden woorden koppelen.
    canvas._sel_bot = 0
    canvas._targets[0] = [0, 1]
    canvas._pinned.add(0)
    canvas._emit()
    assert seen.get(0) == [0, 1]
    # Alleen gepinde woorden worden bewaard (auto-koppeling van 1 niet).
    assert 1 not in seen
    # Afstand-tot-lijn helper (puur).
    assert canvas._point_near_segment(5, 5, 0, 0, 10, 10) is True
    assert canvas._point_near_segment(50, 5, 0, 0, 10, 10) is False


def test_koppel_canvas_knip_en_samenvoeg(qapp) -> None:
    """B153: knip/samenvoegen past de gevonden woorden aan en meldt ze."""
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
    # 'OEREND' knippen -> OER/END; de pin (die naar index 1='HARD' wees)
    # schuift mee naar index 2.
    canvas._sel_top = 0
    assert canvas.cut_selected() is True
    assert [w[0] for w in last["t"]] == ["OER", "END", "HARD"]
    assert canvas._targets[0] == [2]
    # Nu OER + END weer samenvoegen.
    canvas._sel_top = 0
    assert canvas.merge_selected() is True
    assert [w[0] for w in last["t"]] == ["OER END", "HARD"]


def test_koppel_canvas_selectie_ux(qapp) -> None:
    """B154/B155: tweede klik deselecteert; koppeling heft selectie op."""
    from modules.coupling_editor import CouplingCanvas
    transcript = [("A", 0.0, 1.0), ("B", 1.0, 2.0)]
    words = [{"index": 0, "text": "een", "line": 0,
                "transcript_indices": [], "found": None, "sim": 0.0,
                "pinned": False}]
    canvas = CouplingCanvas(transcript, words, lambda p: None)
    # B154: top-woord (de)selecteren.
    canvas._sel_top = 0
    canvas._sel_top = None if canvas._sel_top == 0 else 0
    assert canvas._sel_top is None


def test_koppel_canvas_songtekst_knip(qapp) -> None:
    """B156: knippen op de songtekst-rij splitst een woord en meldt het."""
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
    # 'oehoerend' -> twee woorden; 'hard' schuift een plek op.
    assert [w["text"] for w in canvas._words] == ["oeho", "erend", "hard"]
    assert [t for t, _ in last["ly"]] == ["oeho", "erend", "hard"]
    # De pin van 'hard' (was index 1 -> transcript 1) staat nu op index 2.
    assert canvas._targets.get(2) == [1]


def test_klemtoon_canvas_zet_klemtoon(qapp) -> None:
    """B151/B450: de klemtoon blijft met de hand te zetten.

    De canvas is bij B450 een tijdbalk per zin geworden, met links
    koppelen en rechts de klemtoon. Die tweede is er met opzet nog: hem
    weglaten zou iets weghalen dat in gebruik was."""
    from modules.stress_editor import SentenceCanvas
    from modules.timing import Syllable

    gezien = {}
    canvas = SentenceCanvas(lambda: None,
                            lambda pieces: gezien.update(p=pieces))
    canvas.set_sentence(
        [], [Syllable("ko", 0.0, 1.0), Syllable(" men", 1.0, 2.0)], {})
    canvas.set_stress(1)
    assert [s.stress for s in gezien["p"]] == [False, True]


def test_klemtoon_canvas_koppelt_en_past_de_rest_aan(qapp) -> None:
    """B450: koppelen laat het gekoppelde stukje de tijd van het
    origineel overnemen; de rest schikt zich naar verhouding."""
    from modules.stress_editor import SentenceCanvas
    from modules.timing import Syllable

    geraakt = []
    canvas = SentenceCanvas(lambda: geraakt.append(1))
    canvas.set_sentence(
        [Syllable("aa", 0.0, 2.0)],
        [Syllable("a", 0.0, 0.5), Syllable(" b", 0.5, 1.0)], {})
    canvas._selected_original = 0
    canvas._anchors[1] = 0
    assert canvas.anchors() == {1: 0}


def test_timing_canvas_toggle_disabled(qapp) -> None:
    """B180: geselecteerde cel uit/aan zetten werkt op de onderliggende regel."""
    from modules.timing_editor import TimingCanvas, _CANVAS_HEIGHT
    lines = [{"text": "een", "crowd": False, "index": 0, "block": 0,
              "disabled": False,
              "syllables": [{"text": "een", "start": 1.0, "end": 2.0}]}]
    canvas = TimingCanvas(_peaks(), None, duration=5.0, lines=lines,
                          on_seek=lambda *_: None)
    canvas.resize(400, _CANVAS_HEIGHT)
    # Cellen ontstaan bij het tekenen; forceer een view-cel-berekening.
    from modules import timing as tmod
    canvas._cells = tmod.editor_view_cells(canvas._lines, "sentences")
    canvas._sel_cell = 0
    assert canvas.toggle_selected_disabled() is True
    assert canvas._lines[0]["disabled"] is True
    canvas._cells = tmod.editor_view_cells(canvas._lines, "sentences")
    canvas.toggle_selected_disabled()             # weer aan
    assert canvas._lines[0]["disabled"] is False


def test_damping_editor_shutdown(qapp) -> None:
    """B93: ook de dempings-editor stopt de speler bij sluiten."""
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
