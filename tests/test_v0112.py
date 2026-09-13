"""Tests voor v0.112.0: B356 (harder stoppen) en B357 (twee lijnen).

B356 - een extern programma luisterde niet naar Stop. Alles loopt nu
       door ``proc.run``, dat het proces registreert, en vijf seconden na
       Stop worden ze echt afgeschoten. Meteen ook de cmd-vensters weg
       die de meetlat maakte.
B357 - de balken in het testpaneel bleven op het eerste actienummer
       staan, en alleen 1.5.1 gebruikte beide werkplekken.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import proc, test_panel  # noqa: E402

WORTEL = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _context(tmp_path: Path, naam: str = "Proef"):
    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=naam)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B356: harder stoppen
# --------------------------------------------------------------------------

def test_de_meetlat_roept_geen_kale_ffmpeg_meer_aan() -> None:
    """Dit maakte de cmd-vensters: elf bij 1.5.7, achtentachtig bij 1.5.10."""
    bron = (WORTEL / "tools" / "timing_regression.py").read_text(
        encoding="utf-8")
    assert "subprocess.run(" not in bron
    assert "ffmpeg_module.resample_to_match" in bron


def test_stop_plant_een_harde_stop(qapp, tmp_path) -> None:
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    gepland: list[int] = []
    window._active_cancel = threading.Event()

    from PySide6.QtCore import QTimer
    echt = QTimer.singleShot
    try:
        QTimer.singleShot = staticmethod(  # type: ignore[assignment]
            lambda ms, fn: gepland.append(ms))
        window._stop_current()
    finally:
        QTimer.singleShot = echt  # type: ignore[assignment]
    assert window._active_cancel.is_set()
    assert gepland == [gui.MainWindow.HARD_STOP_MS]
    assert gui.MainWindow.HARD_STOP_MS == 5000


def test_harde_stop_doet_niets_als_de_taak_al_klaar_is(qapp,
                                                       tmp_path) -> None:
    """Anders schiet hij de programma's van een VOLGENDE draai af."""
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    window._worker = None
    gedood = []
    proc_echt = proc.terminate_all
    try:
        proc.terminate_all = lambda: gedood.append(1)  # type: ignore
        window._stop_hard()
    finally:
        proc.terminate_all = proc_echt  # type: ignore
    assert gedood == []


def test_terminate_all_ruimt_zijn_administratie_op(monkeypatch) -> None:
    class _Proces:
        def __init__(self) -> None:
            self.gedood = False

        def kill(self) -> None:
            self.gedood = True

    eerste, tweede = _Proces(), _Proces()
    proc._RUNNING.update({eerste, tweede})
    try:
        assert proc.terminate_all() == 2
        assert eerste.gedood and tweede.gedood
    finally:
        proc._RUNNING.clear()


# --------------------------------------------------------------------------
# B357: twee werkplekken en meelopende balken
# --------------------------------------------------------------------------

def test_verdeler_gebruikt_twee_werkplekken(tmp_path) -> None:
    """Echt tegelijk, niet toevallig na elkaar.

    De poort laat pas door als er TWEE werkers voor staan; loopt er maar
    een, dan valt de test om op de tijdslimiet in plaats van hem per
    ongeluk te halen.
    """
    context = _context(tmp_path)
    plekken: set[int] = set()
    poort = threading.Barrier(2, timeout=5)

    def werk(song: str) -> list[str]:
        poort.wait()
        return [song]

    def report(slot: int, name: str, done: int = 0, total: int = 0) -> None:
        plekken.add(slot)

    regels = test_panel.across_projects(
        context, ["een", "twee"], werk, report, lambda: False)
    assert sorted(regels) == ["een", "twee"]
    assert plekken == {0, 1}


def test_verdeler_meldt_hoeveel_er_klaar_zijn(tmp_path) -> None:
    """De balk moet oplopen; hij bleef eerst eeuwig animeren."""
    context = _context(tmp_path)
    standen: list[tuple[int, int]] = []

    def report(slot: int, name: str, done: int = 0, total: int = 0) -> None:
        standen.append((done, total))

    test_panel.across_projects(context, ["a", "b", "c"], lambda s: [s],
                               report, lambda: False)
    assert {t for _k, t in standen} == {3}
    assert max(k for k, _t in standen) == 3


def test_een_struikelend_project_stopt_de_rest_niet(tmp_path) -> None:
    context = _context(tmp_path)

    def werk(song: str) -> list[str]:
        if song == "stuk":
            raise RuntimeError("kapot")
        return [song]

    regels = test_panel.across_projects(
        context, ["een", "stuk", "twee"], werk, lambda *a: None,
        lambda: False)
    assert any("een" == r for r in regels)
    assert any("twee" == r for r in regels)
    assert any("stuk" in r for r in regels)      # als melding, niet als crash


def test_verdeler_stopt_op_de_stopknop(tmp_path) -> None:
    context = _context(tmp_path)
    gedaan: list[str] = []
    regels = test_panel.across_projects(
        context, [f"lied{n}" for n in range(20)],
        lambda s: gedaan.append(s) or [s], lambda *a: None, lambda: True)
    assert regels == []
    assert gedaan == []


def test_balk_krijgt_bereik_en_waarde(qapp, tmp_path) -> None:
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    window._on_test_progress(1, "1.5.7  Lied D", 3, 11)
    balk = window._progress_bars[1]
    assert balk.maximum() == 11
    assert balk.value() == 3
    # B398/B409: de tweede regel draagt de voortgang binnen de ronde; wie
    # er bezig is staat op de knopjes eronder, niet meer in een etiket.
    assert window._slot_chips[1].text() == "Lied D"
    assert not window._progress_labels[1].isVisible()
    # B402: de bovenste regel is het actiekanaal geworden; een
    # werkplekmelding vult die niet meer.
    window._on_test_progress(window.ACTION_SLOT, "1.5.7", 3, 11)
    assert window._progress_labels[0].text() == "1.5.7  3/11"


def test_voortgang_gaat_via_een_signaal() -> None:
    """De melding komt uit een werkthread; Qt-widgets mogen alleen vanuit
    de GUI-thread worden aangeraakt."""
    from modules import gui

    assert hasattr(gui.MainWindow, "_test_progress")
    bron = __import__("inspect").getsource(gui.MainWindow._do_fill_cache)
    assert "_test_progress.emit" in bron
