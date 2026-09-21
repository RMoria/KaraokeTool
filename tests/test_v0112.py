"""Tests for v0.112.0: B356 (stopping harder) and B357 (two lanes).

B356 - an outside program did not listen to Stop. Everything runs
       through ``proc.run`` now, which registers the process, and five
       seconds after Stop they really are shot down. That also got rid
       of the cmd windows the benchmark opened.
B357 - the bars in the test panel stayed on the first action number,
       and only 1.5.1 used both slots.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import proc, test_panel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _context(tmp_path: Path, name: str = "Proef"):
    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=name)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B356: stopping harder
# --------------------------------------------------------------------------

def test_the_benchmark_no_longer_calls_bare_ffmpeg() -> None:
    """This is what made the cmd windows: eleven at 1.5.7, eighty-eight
    at 1.5.10."""
    source = (ROOT / "tools" / "timing_regression.py").read_text(
        encoding="utf-8")
    assert "subprocess.run(" not in source
    assert "ffmpeg_module.resample_to_match" in source


def test_stop_schedules_a_hard_stop(qapp, tmp_path) -> None:
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    scheduled: list[int] = []
    window._active_cancel = threading.Event()

    from PySide6.QtCore import QTimer
    real = QTimer.singleShot
    try:
        QTimer.singleShot = staticmethod(  # type: ignore[assignment]
            lambda ms, fn: scheduled.append(ms))
        window._stop_current()
    finally:
        QTimer.singleShot = real  # type: ignore[assignment]
    assert window._active_cancel.is_set()
    assert scheduled == [gui.MainWindow.HARD_STOP_MS]
    assert gui.MainWindow.HARD_STOP_MS == 5000


def test_the_hard_stop_does_nothing_once_the_job_is_done(qapp,
                                                         tmp_path) -> None:
    """Otherwise it shoots down the programs of a NEXT run."""
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    window._worker = None
    killed = []
    real_terminate = proc.terminate_all
    try:
        proc.terminate_all = lambda: killed.append(1)  # type: ignore
        window._stop_hard()
    finally:
        proc.terminate_all = real_terminate  # type: ignore
    assert killed == []


def test_terminate_all_clears_its_own_bookkeeping(monkeypatch) -> None:
    class _Process:
        def __init__(self) -> None:
            self.killed = False

        def kill(self) -> None:
            self.killed = True

    first, second = _Process(), _Process()
    proc._RUNNING.update({first, second})
    try:
        assert proc.terminate_all() == 2
        assert first.killed and second.killed
    finally:
        proc._RUNNING.clear()


# --------------------------------------------------------------------------
# B357: two slots and bars that keep up
# --------------------------------------------------------------------------

def test_the_spreader_uses_two_slots(tmp_path) -> None:
    """Really at the same time, not one after the other by accident.

    The gate only lets through once TWO workers stand in front of it; if
    only one runs, the test falls over on the time limit instead of
    passing by accident.
    """
    context = _context(tmp_path)
    slots: set[int] = set()
    gate = threading.Barrier(2, timeout=5)

    def work(song: str) -> list[str]:
        gate.wait()
        return [song]

    def report(slot: int, name: str, done: int = 0, total: int = 0) -> None:
        slots.add(slot)

    rows = test_panel.across_projects(
        context, ["een", "twee"], work, report, lambda: False)
    assert sorted(rows) == ["een", "twee"]
    assert slots == {0, 1}


def test_the_spreader_reports_how_many_are_done(tmp_path) -> None:
    """The bar has to climb; at first it animated forever."""
    context = _context(tmp_path)
    readings: list[tuple[int, int]] = []

    def report(slot: int, name: str, done: int = 0, total: int = 0) -> None:
        readings.append((done, total))

    test_panel.across_projects(context, ["a", "b", "c"], lambda s: [s],
                               report, lambda: False)
    assert {total for _done, total in readings} == {3}
    assert max(done for done, _total in readings) == 3


def test_one_stumbling_project_does_not_stop_the_rest(tmp_path) -> None:
    context = _context(tmp_path)

    def work(song: str) -> list[str]:
        if song == "stuk":
            raise RuntimeError("kapot")
        return [song]

    rows = test_panel.across_projects(
        context, ["een", "stuk", "twee"], work, lambda *a: None,
        lambda: False)
    assert any("een" == r for r in rows)
    assert any("twee" == r for r in rows)
    assert any("stuk" in r for r in rows)        # as a report, not a crash


def test_the_spreader_stops_on_the_stop_button(tmp_path) -> None:
    context = _context(tmp_path)
    handled: list[str] = []
    rows = test_panel.across_projects(
        context, [f"lied{n}" for n in range(20)],
        lambda s: handled.append(s) or [s], lambda *a: None, lambda: True)
    assert rows == []
    assert handled == []


def test_the_bar_gets_a_range_and_a_value(qapp, tmp_path) -> None:
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    window._on_test_progress(1, "1.5.7  Lied D", 3, 11)
    bar = window._progress_bars[1]
    assert bar.maximum() == 11
    assert bar.value() == 3
    # B398/B409: the second line carries the progress within the round;
    # who is busy stands on the chips below it, no longer in a label.
    assert window._slot_chips[1].text() == "Lied D"
    assert not window._progress_labels[1].isVisible()
    # B402: the top line has become the action channel; a slot message
    # no longer fills it.
    window._on_test_progress(window.ACTION_SLOT, "1.5.7", 3, 11)
    assert window._progress_labels[0].text() == "1.5.7  3/11"


def test_the_progress_travels_by_signal() -> None:
    """The message comes from a worker thread; Qt widgets may only be
    touched from the GUI thread."""
    from modules import gui

    assert hasattr(gui.MainWindow, "_test_progress")
    source = __import__("inspect").getsource(gui.MainWindow._do_fill_cache)
    assert "_test_progress.emit" in source
