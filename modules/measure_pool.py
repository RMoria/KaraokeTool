"""Measure over PROCESSES instead of threads (B396).

The user asked for this more than once, and got an explanation instead of
a repair more than once. This is the repair.

Two work slots have existed since B357, and they are real threads - but
the work they do is pure Python, so the GIL lets only one of them run at
a time. The task manager said it plainly: 15% of a machine with twelve
logical processors, which is one core. Threads cannot fix that. Only
separate interpreters can.

There is a second reason processes are the only option here, and it is
the harder one. A model variant is applied with ``setattr`` on module
globals, so two variants in one interpreter would read each other's
models. That is why 1.5.10 walks its 256 rounds strictly one after
another. Give every worker its own interpreter and that objection
disappears: each one sets its own model state and cannot disturb anybody.

The work item is therefore deliberately small and picklable: a project
name plus the FULL desired model state. No callables, no context, no
closures - those were exactly what made the existing spreader
thread-only.

Falls back to the thread path without complaining when processes cannot
be started (a frozen build, a locked-down machine). Better a slow answer
than no answer.
"""
from __future__ import annotations

import atexit
import logging
import os

logger = logging.getLogger(__name__)


def _t(key: str) -> str:
    """The log texts go through translations (B315): they land in
    the log window, so the user reads them."""
    from .translations import t

    return t(key)

#: Logical processors left alone for pure-Python work, so the machine
#: stays usable while a night job runs. The user's rule, and a sound one:
#: a program that claims everything is a program you switch off.
SPARE_CORES = 3

#: Threads one Whisper run takes for itself. ctranslate2 is C++ and does
#: its own threading, so a second run only helps if there are cores left
#: over - counting work slots as if they were free is how you end up
#: with two runs fighting over the same four cores.
WHISPER_THREADS = 4

#: Of the Whisper slots that would fit, take this share. Leaves room for
#: the loading of a second model and for the machine itself.
WHISPER_SHARE = 2 / 3

#: Below this there is nothing to spread: the overhead of starting an
#: interpreter (on Windows a full re-import) is larger than the gain.
MIN_ITEMS = 2


def core_count() -> int:
    """Logical processors on this machine."""
    try:
        return len(os.sched_getaffinity(0))      # type: ignore[attr-defined]
    except AttributeError:                        # Windows
        return os.cpu_count() or 1


def worker_count(items: int, spare: int = SPARE_CORES) -> int:
    """Processes for PURE PYTHON work: cores minus a few.

    Every worker holds one core busy for the whole run, so the count is
    simply what is left after keeping the machine usable. On the user's
    twelve logical processors that is nine.
    """
    if items < MIN_ITEMS:
        return 1
    return max(1, min(items, core_count() - spare))


def whisper_lanes() -> int:
    """How many Whisper runs may sound at once (B422).

    The same sum as :func:`whisper_workers`, but without an item count -
    the model has to be built before anybody knows how much work there
    is, and it must be told how many threads will call it. Kept as one
    function so the number the model is given and the number of slots
    that are handed out can never drift apart.
    """
    fits = core_count() / WHISPER_THREADS
    return max(1, round(fits * WHISPER_SHARE))


def threads_per_lane() -> int:
    """Cores one Whisper run may use for itself (B422).

    Was never passed on: the library quietly defaults to four and this
    module assumed four, and those two agreeing was luck. On a machine
    where cores/lanes gives something else, this now follows.
    """
    return max(1, min(WHISPER_THREADS,
                      core_count() // max(1, whisper_lanes())))


def whisper_workers(items: int) -> int:
    """Work slots for WHISPER work: cores / 4, and two thirds of that.

    A different sum, for a different reason. A Whisper run is not one
    core: ctranslate2 takes about four for itself. So the number that
    fits is cores over four - three on this machine - and of those we
    take two thirds, which leaves room for a second model in memory and
    for the machine itself. Twelve logical processors therefore give two
    slots, and that matches what the task manager showed: one run sat at
    33%, so two of them fill about two thirds of the machine.
    """
    if items < MIN_ITEMS:
        return 1
    return max(1, min(items, whisper_lanes()))


def _measure_one(item):
    """Measure one project with one model state. Runs in a CHILD.

    Must stay importable at module level and take only picklable
    arguments - that is the whole contract with ``ProcessPoolExecutor``.
    """
    root, song, output_base, states, order = item
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "regression_child", here / "tools" / "timing_regression.py")
    regression = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regression)

    from modules import model_register

    model_register.apply_settings(dict(states))
    model_register.apply_disabled()

    # B439: an order is not a model - it swaps whole functions, and a
    # function object does not travel. The NAME travels, and the child
    # builds the replacements itself.
    #
    # And it puts them back afterwards. The first version did not,
    # reasoning that a child is thrown away - which is wrong here: B399
    # keeps ONE pool alive for the whole action on purpose, so a worker
    # measures round after round. An order left standing would stack on
    # the next one (the second order would capture the first as "the
    # real function"), and every later round without an order would
    # quietly keep running with it. That is the same defect this whole
    # release is about, one process further along.
    put_back = ()
    if order:
        from modules import model_orders

        targets = model_orders.targets(order)
        put_back = tuple((module, attribute, getattr(module, attribute))
                         for module, attribute, _new in targets)
        for module, attribute, replacement in targets:
            setattr(module, attribute, replacement)

    from modules.filesystem import ProjectPaths

    paths = ProjectPaths(root=Path(root), song=song,
                         output_base=output_base)
    try:
        return regression.measure(paths.output_dir)
    except Exception:                    # noqa: BLE001 - one project does not stop the rest
        logger.exception(_t("log_measure_failed"))
        return None
    finally:
        for module, attribute, real in put_back:
            setattr(module, attribute, real)


def measure_rows(root, songs, output_base, states, report=None,
                 cancelled=None, spare: int = SPARE_CORES,
                 order: str = ""):
    """Measure these projects with this model state, over processes.

    ``states`` is the complete ``{model code: on}`` map the children have
    to apply - explicit rather than "the current state", because a child
    has no way of knowing what the parent switched.

    ``order`` is the name of an order from :mod:`modules.model_orders`,
    empty for the normal one (B439). Same reasoning as the state map: the
    child is told what to be, it does not inherit it.

    Returns the rows in project order; a project that fails is left out,
    exactly as the thread path does.
    """
    songs = list(songs)
    if not songs:
        return []
    items = [(str(root), song, output_base, tuple(sorted(states.items())),
              order)
             for song in songs]
    workers = worker_count(len(items), spare)
    if workers <= 1:
        return _serial(items, report, cancelled)

    pool = _shared_pool(workers)
    if pool is None:
        return _serial(items, report, cancelled)

    rows: list = []
    done = 0
    try:
        futures = {pool.submit(_measure_one, item): item[1]
                   for item in items}
        for future in futures:
            if cancelled is not None and cancelled():
                break
            song = futures[future]
            if report is not None:
                # B398: the real slot number - the panel folds however
                # many there are onto its two rows itself.
                report(done % workers, song, done, len(items))
            try:
                row = future.result()
            except Exception:            # noqa: BLE001
                logger.exception(_t("log_measure_failed"))
                row = None
            done += 1
            if isinstance(row, dict):
                rows.append(row)
    finally:
        # B399: NOT shut down here. The pool lives on for the next round.
        pass
    return sorted(rows, key=lambda r: r.get("project", ""))


#: B399: one pool for the whole action, not one per round.
#:
#: The first version made a fresh ``ProcessPoolExecutor`` for every
#: measurement round and shut it down again. That looks tidy and is
#: ruinous: 1.5.10 walks 256 rounds, so that is 256 x 9 = over two
#: thousand process starts - and on Windows a start is a full re-import
#: of the modules, not a cheap fork. The work per round is seconds; the
#: starting would have cost more than the measuring.
#:
#: Reuse is safe precisely because of how the work item was designed: a
#: child is told the COMPLETE model state with every item, so it never
#: carries anything over from the previous round.
_POOL = None
_POOL_SIZE = 0


def _shared_pool(workers: int):
    """The pool, made once and kept (B399). ``None`` if it will not start."""
    global _POOL, _POOL_SIZE
    if _POOL is not None and _POOL_SIZE == workers:
        return _POOL
    close_pool()
    from concurrent.futures import ProcessPoolExecutor
    try:
        _POOL = ProcessPoolExecutor(max_workers=workers)
    except (OSError, ValueError, ImportError):  # noqa: BLE001
        logger.exception(_t("log_pool_unavailable"))
        _POOL, _POOL_SIZE = None, 0
        return None
    _POOL_SIZE = workers
    return _POOL


def _close_at_exit() -> None:
    """B401: let the workers go when the program stops, whatever happens.

    ``close_pool`` is called when an action finishes, but that is the
    tidy path. Stop being pressed halfway, the window being closed, an
    exception in the runner - in all of those the pool would keep nine
    interpreters standing, and after closing the app they would be
    orphans nobody can see any more except in the task manager.

    ``ProcessPoolExecutor`` does register its own atexit hook, but it
    WAITS for running work there. A yardstick round is seconds, so that
    is survivable, but it means closing the window can hang - and a
    program that does not close is a program you kill, which leaves the
    orphans after all. Hence cancel first, then let go.
    """
    close_pool()


def close_pool() -> None:
    """Let the worker processes go (B399).

    Called when an action is done. Without this the nine interpreters
    keep standing for as long as the program runs - which is not fatal
    at about 110 MB each, but it is not tidy either.
    """
    global _POOL, _POOL_SIZE
    if _POOL is not None:
        try:
            _POOL.shutdown(wait=False, cancel_futures=True)
        except Exception:            # noqa: BLE001 - opruimen mag nooit klappen
            logger.exception(_t("log_pool_unavailable"))
    _POOL, _POOL_SIZE = None, 0


def _serial(items, report, cancelled):
    """One process after all: too few items, or no pool available.

    B439: this path runs ``_measure_one`` in the PARENT, and that
    function is written for a child - it applies the model state and the
    order and never puts anything back, because a child is thrown away.
    In the parent that means the program keeps running on the last
    variant it measured: a fallback that only happens on a locked-down
    machine, and would have been very hard to recognise there. So the
    state is saved and restored around it here.
    """
    from . import model_register

    rows = []
    saved_models = model_register.current_settings()
    saved_orders = [(module, attribute, getattr(module, attribute))
                    for item in items if item[4]
                    for module, attribute, _new in _order_targets(item[4])]
    try:
        for number, item in enumerate(items):
            if cancelled is not None and cancelled():
                break
            if report is not None:
                report(0, item[1], number, len(items))
            row = _measure_one(item)
            if isinstance(row, dict):
                rows.append(row)
    finally:
        for module, attribute, real in saved_orders:
            setattr(module, attribute, real)
        model_register.apply_settings(saved_models)
        model_register.apply_disabled()
    return sorted(rows, key=lambda r: r.get("project", ""))


def _order_targets(name):
    """The targets of an order, without dragging the panel along."""
    from . import model_orders

    return model_orders.targets(name)


atexit.register(_close_at_exit)
