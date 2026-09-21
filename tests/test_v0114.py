"""Tests for v0.114.0: B359 (the GUI hung on a SystemExit).

The user started 1.5.9, nothing happened any more, and there was no CPU
activity either. The log ended with the line saying 1.5.9 was running
and then stopped: no error, no next action, nothing. The worker thread
had died in silence.

``SystemExit`` inherits from ``BaseException`` and not from
``Exception``, so it slipped through all three safety nets (the action
itself, the loop over the actions, and ``_Worker.run``). Because
``run()`` blew up, none of the signals ``done``/``failed``/``cancelled``
was ever sent, ``_set_busy(False)`` never ran, and the window hung on
"busy" for good.

Three repairs plus one that stands apart but had the same cause (the
radio buttons did nothing).
"""
from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import test_panel  # noqa: E402
from modules.translations import TRANSLATIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _context(tmp_path: Path, name: str = "Proef"):
    """A context in which ``name`` really is the CHOSEN project.

    The title in the settings is what the app calls "the current
    project"; it is independent of the paths. That very difference is
    what went wrong.
    """
    from dataclasses import replace

    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=name)
    ensure_directories(paths)
    config = default_config()
    config = replace(config, song=replace(config.song, title=name))
    return pipeline.AppContext(paths=paths, config=config,
                               store=ProjectStore(paths.project_file))


@pytest.fixture(autouse=True)
def _restore_scope():
    """The scope is a module-wide switch; never leave it hanging."""
    yield
    test_panel.limit_to_current(False)


# --------------------------------------------------------------------------
# The heart of it: a dead thread may never happen again
# --------------------------------------------------------------------------

def test_systemexit_is_not_an_exception() -> None:
    """The whole bug in one line - everybody's assumption was wrong."""
    assert not issubclass(SystemExit, Exception)
    assert issubclass(SystemExit, BaseException)


@pytest.mark.parametrize("blast", [
    SystemExit("gereedschap stopte"),
    KeyboardInterrupt(),
])
def test_the_worker_reports_a_baseexception_too(qapp, blast) -> None:
    """Otherwise: no signal, no message, and a window that hangs."""
    from modules import gui

    def task(_progress, _message):
        raise blast

    worker = gui._Worker(task)
    reported: list[str] = []
    done: list[object] = []
    worker.failed.connect(reported.append)
    worker.done.connect(done.append)
    worker.run()                     # straight through, no real thread
    assert done == []
    assert len(reported) == 1, "there must be EXACTLY one message"
    assert reported[0].strip()


def test_the_worker_catches_everything() -> None:
    """An `except Exception` as the last safety net is not enough here."""
    from modules import gui

    source = inspect.getsource(gui._Worker.run)
    assert "except BaseException" in source
    last = [line.strip() for line in source.splitlines()
            if line.strip().startswith("except ")][-1]
    assert "BaseException" in last, \
        f"the last safety net is {last!r} and lets SystemExit past"


def test_an_ordinary_task_still_reports_done(qapp) -> None:
    """The wider safety net may not swallow the happy ending."""
    from modules import gui

    worker = gui._Worker(lambda _p, _m: "uitkomst")
    done: list[object] = []
    failed: list[str] = []
    worker.done.connect(done.append)
    worker.failed.connect(failed.append)
    worker.run()
    assert done == ["uitkomst"]
    assert failed == []


# --------------------------------------------------------------------------
# The tool does not raise SystemExit any more
# --------------------------------------------------------------------------

def _probe():
    import importlib.util

    path = ROOT / "tools" / "whisper_probe.py"
    spec = importlib.util.spec_from_file_location("probe_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vocal_stem_raises_an_ordinary_error(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        _probe().vocal_stem(tmp_path, "DoesNotExist")


def test_vocal_stem_still_finds_the_loose_wav(tmp_path) -> None:
    from modules.filesystem import ProjectPaths

    paths = ProjectPaths(root=tmp_path, song="Proef")
    paths.cache_dir.mkdir(parents=True, exist_ok=True)
    (paths.cache_dir / "original.wav").write_bytes(b"")
    assert _probe().vocal_stem(tmp_path, "Proef").name == "original.wav"


def test_only_main_may_stop_with_systemexit() -> None:
    """A function the app also calls may never do that.

    This is exactly the distinction that went wrong: ``vocal_stem`` was
    written as command-line code but was being called by 1.5.9.
    """
    offenders = []
    for folder in ("modules", "tools"):
        for path in sorted((ROOT / folder).glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if node.name == "main":
                    continue
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Raise) and \
                            "SystemExit" in ast.dump(inner):
                        offenders.append(f"{path.name}:{inner.lineno} "
                                         f"({node.name})")
    assert offenders == [], "SystemExit outside main(): " + \
        ", ".join(offenders)


# --------------------------------------------------------------------------
# 1.5.9 no longer trips over an empty project
# --------------------------------------------------------------------------

def test_without_a_chosen_project_the_message_is_polite(tmp_path) -> None:
    """This is what set it off: the project was empty after a restart.

    B374: the window trial moved to the heavy bin (1.5.11c); the check
    for "has a project been chosen at all" moved with it and has to hold
    just as well over there.
    """
    from dataclasses import replace

    context = _context(tmp_path)
    context = replace(context,
                      config=replace(context.config,
                                     song=replace(context.config.song,
                                                  title="")))
    # B386: without a chosen project the trial looks up the largest gap
    # itself. If there is no gap anywhere it skips itself - and since
    # B385 that is a TrialSkipped and not an ordinary result, so it does
    # not book twenty versions off for a measurement that never happened.
    with pytest.raises(test_panel.TrialSkipped) as caught:
        test_panel.chunk_trial(context, lambda *a, **k: None,
                               lambda: False)
    assert caught.value.lines == [TRANSLATIONS["nl"]["heavy_probe_nowhere"]]


def test_without_a_transcription_it_reports_rather_than_crashes(
        tmp_path) -> None:
    with pytest.raises(test_panel.TrialSkipped) as caught:
        test_panel.chunk_trial(_context(tmp_path),
                               lambda *a, **k: None, lambda: False)
    assert len(caught.value.lines) == 1


# --------------------------------------------------------------------------
# The radio buttons finally do something
# --------------------------------------------------------------------------

def _make_project(context, name: str) -> None:
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paths = ProjectPaths(root=context.paths.root, song=name,
                         output_base=context.paths.output_base)
    ensure_directories(paths)
    ProjectStore(paths.project_file).set_meta("proef", 1)


def test_all_projects_yields_them_all(tmp_path) -> None:
    context = _context(tmp_path, "Twee")
    for name in ("Een", "Twee", "Drie"):
        _make_project(context, name)
    test_panel.limit_to_current(False)
    assert test_panel._projects(context) == ["Drie", "Een", "Twee"]


def test_only_this_project_yields_one(tmp_path) -> None:
    context = _context(tmp_path, "Twee")
    for name in ("Een", "Twee", "Drie"):
        _make_project(context, name)
    test_panel.limit_to_current(True)
    assert test_panel._projects(context) == ["Twee"]


def test_only_this_project_without_a_project_yields_nothing(tmp_path) -> None:
    from dataclasses import replace

    context = _context(tmp_path, "Twee")
    _make_project(context, "Twee")
    context = replace(context,
                      config=replace(context.config,
                                     song=replace(context.config.song,
                                                  title="")))
    test_panel.limit_to_current(True)
    assert test_panel._projects(context) == []


def test_the_runner_reads_the_radio_buttons() -> None:
    """They were there all right, but nobody looked at them."""
    from modules import gui

    source = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "only_this_project()" in source
    assert "limit_to_current" in source


def test_the_scope_is_set_afresh_on_every_run() -> None:
    """Otherwise last time's choice stays behind."""
    from modules import gui

    source = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert source.index("limit_to_current") < source.index("def task")


def test_the_bar_moves_even_for_an_action_that_reports_nothing() -> None:
    """1.5.9 has no row of projects and so never reported anything; the
    label of the previous action stayed put, and that reads as a hang."""
    from modules import gui

    source = inspect.getsource(gui.MainWindow._do_fill_cache)
    head = source.index("def report")
    tail = source[head:]
    assert "for slot in range(len(self._progress_bars))" in tail
    assert tail.index("report(slot") < tail.index("action.function(")


def test_the_new_texts_exist_in_both_languages() -> None:
    """B400: ``test_no_project`` and ``test_cancelled`` have been swept up.

    They belonged to the window trial that moved to the heavy bin in
    B374 and started choosing a project of its own in B386; nobody has
    called them since. The keys that DO still matter are listed below.
    """
    for key in ("test_running", "test_failed", "test_done"):
        for language in ("nl", "en"):
            assert TRANSLATIONS[language].get(key, "").strip(), \
                f"{key} ({language})"
