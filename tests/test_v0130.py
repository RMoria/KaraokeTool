"""Tests for v0.130.0: B398 - two rows, nine work slots.

Since B396 the measurement runs over nine processes, but the panel had
two progress bars and indexed them by slot number - so slots 2 to 8 fell
off the end of the list and were never shown. The user saw two queues
while nine were running, and said so.

Two rows was and is the right number; what changed is what they mean. The
first row is the run as a whole (which action, how far along), the second
is who is busy right now - one chip per slot, so nine slots stay legible
where one cut-off line was not (B409).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, tmp_path):
    from dataclasses import replace

    from modules import gui, pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    config = default_config()
    config = replace(config, song=replace(config.song, title="Proef"))
    context = pipeline.AppContext(paths=paths, config=config,
                                  store=ProjectStore(paths.project_file))
    return gui.MainWindow(context)


def test_a_high_slot_number_is_no_longer_dropped(window) -> None:
    """The regression: slot 8 used to fall off the end of the list."""
    window._on_test_progress(8, "1.5.10  Lied D", 5, 128)
    assert window._slot_chips[8].text() == "Lied D"


def test_the_first_row_is_the_run_as_a_whole(window) -> None:
    """B402: and it takes that from the ACTION channel, not from a work
    slot - a slot knows how far its round is, not how far the run is."""
    window._on_test_progress(window.ACTION_SLOT, "1.5.10", 12, 128)
    assert window._progress_labels[0].text() == "1.5.10  12/128"
    assert window._progress_bars[0].maximum() == 128
    assert window._progress_bars[0].value() == 12


def test_the_chips_name_the_slots(window) -> None:
    for slot, song in enumerate(("Lied D", "Lied_J", "Lied_S")):
        window._on_test_progress(slot, f"1.5.10  {song}", slot, 128)
    shown = [chip.text() for chip in window._slot_chips if not chip.isHidden()]
    assert shown == ["Lied D", "Lied_J", "Lied_S"]


def test_the_row_above_the_chips_stays_empty(window) -> None:
    """B409: the chips already say who is busy. A line above them that
    repeats the same names, cut off on width, is one line too many."""
    window._on_test_progress(0, "1.5.7  Lied D", 1, 11)
    assert not window._progress_labels[1].isVisible()


def test_nine_slots_give_nine_chips(window) -> None:
    """Without chips this fell off the end of two bars: nine running and
    two visible."""
    for slot in range(9):
        window._on_test_progress(
            slot, f"1.5.10  Een_behoorlijk_lange_projectnaam_{slot}",
            slot, 128)
    assert sum(1 for chip in window._slot_chips if not chip.isHidden()) == 9


def test_a_new_run_forgets_the_previous_slots(window) -> None:
    """Otherwise a chip still names a project from the action before it."""
    window._on_test_progress(4, "1.5.10  Lied D", 1, 128)
    window._show_test_bars(["1.5.7", "1.5.7"])
    window._on_test_progress(0, "1.5.7  Lied_J", 1, 11)
    shown = [chip.text() for chip in window._slot_chips if not chip.isHidden()]
    assert "Lied D" not in shown and "Lied_J" in shown


# --------------------------------------------------------------------------
# B399 - one pool, not one per round
# --------------------------------------------------------------------------

def test_the_pool_is_made_once_and_kept() -> None:
    """1.5.10 walks 256 rounds. A pool per round would be over two
    thousand process starts, and on Windows a start is a full
    re-import - the starting would cost more than the measuring."""
    from unittest.mock import patch

    from modules import measure_pool

    measure_pool.close_pool()
    made = []

    class FakePool:
        def __init__(self, max_workers=None):
            made.append(max_workers)

        def shutdown(self, **_kw):
            pass

    with patch("concurrent.futures.ProcessPoolExecutor", FakePool):
        first = measure_pool._shared_pool(9)
        second = measure_pool._shared_pool(9)
    assert first is second
    assert made == [9], "make once, reuse after that"
    measure_pool.close_pool()


def test_a_different_size_gets_a_new_pool() -> None:
    from unittest.mock import patch

    from modules import measure_pool

    measure_pool.close_pool()
    made = []

    class FakePool:
        def __init__(self, max_workers=None):
            made.append(max_workers)

        def shutdown(self, **_kw):
            pass

    with patch("concurrent.futures.ProcessPoolExecutor", FakePool):
        measure_pool._shared_pool(9)
        measure_pool._shared_pool(2)
    assert made == [9, 2]
    measure_pool.close_pool()


def test_closing_is_safe_when_there_is_nothing_to_close() -> None:
    from modules import measure_pool

    measure_pool.close_pool()
    measure_pool.close_pool()


def test_the_runner_lets_the_workers_go_when_an_action_is_done() -> None:
    import inspect

    from modules import gui

    source = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "close_pool()" in source
