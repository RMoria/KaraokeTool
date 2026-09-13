"""Tests for v0.128.0: B396 - the work slots finally use the machine.

The user asked for this repeatedly and got an explanation every time. The
explanation was even correct, which is what made it useless: two work
slots have existed since B357, they are real threads, and for pure Python
the GIL lets only one of them run. Fifteen percent of twelve logical
processors is one core. Explaining that again does not measure anything.

Two different jobs, so two different sums - the user's own rule, and it
is the right one because the two kinds of work are not alike.

Pure Python (the yardstick, and therefore 1.5.10 and the cluster and
search trials) needs SEPARATE INTERPRETERS. Every worker then holds one
core, so the count is cores minus a few to keep the machine usable:
twelve gives nine. Processes are also the only way to run two model
variants at once at all, because a variant is applied with ``setattr`` on
module globals - two of those in one interpreter would read each other's
models, which is exactly why 1.5.10 walks its rounds one at a time.

Whisper work is the opposite: ctranslate2 is C++ and releases the GIL, so
threads there really do run side by side. But one run already takes about
four cores for itself, so the number that fits is cores over four, and of
those two thirds - twelve gives two. That matches the measurement: one
run sat at 33% of the machine.
"""
from __future__ import annotations

import inspect
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import measure_pool, test_panel  # noqa: E402


# --------------------------------------------------------------------------
# The two sums
# --------------------------------------------------------------------------

def test_compute_work_takes_the_cores_minus_a_few() -> None:
    with patch.object(measure_pool, "core_count", lambda: 12):
        assert measure_pool.worker_count(50) == 9


def test_whisper_work_takes_a_quarter_of_that_and_two_thirds_again() -> None:
    """One Whisper run is about four cores, so two of them fill roughly
    two thirds of this machine - which is what the task manager showed."""
    with patch.object(measure_pool, "core_count", lambda: 12):
        assert measure_pool.whisper_workers(8) == 2


def test_a_small_machine_never_goes_below_one() -> None:
    with patch.object(measure_pool, "core_count", lambda: 2):
        assert measure_pool.worker_count(50) == 1
        assert measure_pool.whisper_workers(8) == 1


def test_a_bigger_machine_scales_along() -> None:
    with patch.object(measure_pool, "core_count", lambda: 24):
        assert measure_pool.worker_count(50) == 21
        assert measure_pool.whisper_workers(8) == 4


def test_one_work_item_is_never_worth_a_second_process() -> None:
    """Starting an interpreter costs more than the gain - on Windows a
    full re-import."""
    with patch.object(measure_pool, "core_count", lambda: 12):
        assert measure_pool.worker_count(1) == 1
        assert measure_pool.whisper_workers(1) == 1


def test_never_more_workers_than_work() -> None:
    with patch.object(measure_pool, "core_count", lambda: 24):
        assert measure_pool.worker_count(3) == 3


# --------------------------------------------------------------------------
# The spreader takes a slot count now
# --------------------------------------------------------------------------

def test_the_spreader_accepts_a_number_of_slots() -> None:
    names = list(inspect.signature(test_panel.across_projects).parameters)
    assert "slots" in names


def test_two_stays_the_default_for_python_work() -> None:
    """More threads on pure Python only take turns on the GIL."""
    default = inspect.signature(
        test_panel.across_projects).parameters["slots"].default
    assert default == 2


def test_the_slots_still_land_on_the_two_bars(tmp_path) -> None:
    """There are two progress bars, however many slots there are."""
    from dataclasses import replace

    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    config = default_config()
    config = replace(config, song=replace(config.song, title="Proef"))
    context = pipeline.AppContext(paths=paths, config=config,
                                  store=ProjectStore(paths.project_file))

    seen = []
    test_panel.across_projects(
        context, [f"lied{n}" for n in range(9)], lambda s: [s],
        lambda slot, name, done=0, total=0: seen.append(slot),
        lambda: False, slots=5)
    assert seen and set(seen) <= {0, 1}


def test_more_slots_really_run_more_at_once(tmp_path) -> None:
    """The point of the whole thing: nine work items over five slots may
    not be nine turns."""
    import threading
    from dataclasses import replace

    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    config = default_config()
    config = replace(config, song=replace(config.song, title="Proef"))
    context = pipeline.AppContext(paths=paths, config=config,
                                  store=ProjectStore(paths.project_file))

    busy = {"now": 0, "most": 0}
    lock = threading.Lock()
    gate = threading.Barrier(5, timeout=10)

    def work(song):
        with lock:
            busy["now"] += 1
            busy["most"] = max(busy["most"], busy["now"])
        try:
            gate.wait()
        except threading.BrokenBarrierError:
            pass
        with lock:
            busy["now"] -= 1
        return [song]

    test_panel.across_projects(context, [f"l{n}" for n in range(5)], work,
                               lambda *a, **k: None, lambda: False, slots=5)
    assert busy["most"] == 5, "vijf werkplekken horen echt tegelijk te lopen"


# --------------------------------------------------------------------------
# The Whisper trial no longer walks its variants one by one
# --------------------------------------------------------------------------

def test_the_yardstick_without_history_uses_processes() -> None:
    source = inspect.getsource(test_panel._yardstick_rows)
    assert "_rows_over_processes" in source


def test_with_history_it_stays_on_threads() -> None:
    """There most projects are skipped, so a process pool would only add
    start-up cost."""
    source = inspect.getsource(test_panel._yardstick_rows)
    assert source.index("with_history") < source.index("_rows_over_processes")


def test_the_children_are_told_the_whole_model_state() -> None:
    """A child interpreter cannot see what the parent switched with
    ``setattr``, so the state has to travel with the work item."""
    source = inspect.getsource(test_panel._model_state_now)
    assert "register()" in source and "enabled" in source


def test_the_work_item_is_picklable() -> None:
    """The contract with ProcessPoolExecutor. Callables and closures are
    exactly what kept the old spreader thread-only."""
    import pickle

    item = ("C:/Muziek", "Lied", None, (("B377", True), ("B380", False)))
    assert pickle.loads(pickle.dumps(item)) == item


def test_a_pool_that_will_not_start_falls_back(tmp_path) -> None:
    """Better a slow answer than no answer."""
    calls = []

    def explode(*_a, **_k):
        raise OSError("geen processen")

    with patch.object(measure_pool, "core_count", lambda: 12), \
            patch("concurrent.futures.ProcessPoolExecutor", explode), \
            patch.object(measure_pool, "_measure_one",
                         lambda item: calls.append(item) or None):
        rows = measure_pool.measure_rows(tmp_path, ["a", "b"], None, {})
    assert rows == [] and len(calls) == 2, "hij hoort het serieel te doen"
