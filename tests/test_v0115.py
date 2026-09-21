"""Tests for v0.115.0: B360 (1.5.10 tripped over the reporter).

B357 gave the reporter a different shape - from one argument to
``(slot, name, done, total)``, because every workplace got a bar of its
own. Every action went along, except ``omission_trial``, which still
used the old shape in one place. That is why 1.5.10 fell over with a
``TypeError`` after twenty-eight milliseconds.

The sting is not in that one line but in why 827 tests did not see it.
Two things still pointed at the old contract: the type hint ``Reporter``
at the top of ``test_panel.py`` still read ``Callable[[str], None]``, and
the tests called the actions with ``lambda _t: None`` - a reporter with
one argument. So the test confirmed the old contract instead of the real
one, and could not possibly find this fault.

Hence one reporter below with exactly the shape the runner has, plus a
guard that pins those two shapes to each other.
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

#: The names the runner gives its reporter, in this order.
REPORTER_SHAPE = ["slot", "name", "done", "total"]


def reporter(seen: list | None = None):
    """Exactly the reporter the runner hands over (B357/B360).

    No ``*args``: a reporter that swallows everything would hide this
    very bug, and that is exactly what happened.
    """
    def report(slot: int, name: str, done: int = 0,
               total: int = 0) -> None:
        if seen is not None:
            seen.append((slot, name, done, total))
    return report


def _context(tmp_path: Path, name: str = "Proef"):
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


# --------------------------------------------------------------------------
# The repair itself
# --------------------------------------------------------------------------

def test_the_omission_trial_reports_in_the_new_shape(tmp_path) -> None:
    """This is the line that fell over; it simply has to run now."""
    seen: list = []
    outcome = test_panel.omission_trial(_context(tmp_path), reporter(seen),
                                       lambda: False)
    assert isinstance(outcome, str)
    assert seen, "1.5.9 has to report its variants"
    for slot, name, done, total in seen:
        assert slot == 0, "the variant name belongs on the first bar"
        assert isinstance(name, str) and name.strip()
        assert (done, total) == (0, 0)


def test_the_omission_trial_names_its_variants(tmp_path) -> None:
    """B361: the variants come from the register, with their B number."""
    from modules import model_register

    seen: list = []
    test_panel.omission_trial(_context(tmp_path), reporter(seen),
                            lambda: False)
    names = [name for _slot, name, _d, _t in seen]
    assert len(names) == len(set(names)), "every variant only once"
    measurable = [m.label for m in model_register.register()
                  if m.level in ("blok", "zin", "koppeling")]
    for label in measurable:
        assert label in names, label


# --------------------------------------------------------------------------
# Pinning the contract down, so this cannot happen twice
# --------------------------------------------------------------------------

def test_the_runner_hands_over_the_reporter_we_use_here() -> None:
    """Pins the shape in the runner to the shape in these tests.

    If the reporter changes once more, this test falls over instead of
    one forgotten action showing up on screen.
    """
    from modules import gui

    tree = ast.parse(inspect.getsource(gui.MainWindow._do_fill_cache).lstrip())
    inside = [k for k in ast.walk(tree)
              if isinstance(k, ast.FunctionDef) and k.name == "report"]
    assert len(inside) == 1, "where has the runner's reporter gone?"
    names = [a.arg for a in inside[0].args.args]
    assert names[:len(REPORTER_SHAPE)] == REPORTER_SHAPE
    assert list(inspect.signature(reporter()).parameters) == REPORTER_SHAPE


def test_no_action_calls_the_reporter_with_one_argument() -> None:
    """The structural guard: a one-argument call may not stand anywhere.

    Cheaper and sharper than waiting for a heavy action to fall over.
    """
    wrong = []
    for path in (ROOT / "modules" / "test_panel.py",
                 ROOT / "modules" / "gui.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name)
                    and node.func.id == "melden"):
                continue
            if len(node.args) < 2:
                wrong.append(f"{path.name}:{node.lineno}")
    assert wrong == [], ("melden() with too few arguments: "
                         + ", ".join(wrong))


def test_the_type_hint_no_longer_points_the_wrong_way() -> None:
    """``Callable[[str], None]`` described the reporter from before B357."""
    source = (ROOT / "modules" / "test_panel.py").read_text(encoding="utf-8")
    assert "Reporter = Callable[[str], None]" not in source
    assert "Reporter = Callable[..., None]" in source


# --------------------------------------------------------------------------
# All eleven, with the real reporter
# --------------------------------------------------------------------------

def test_every_action_copes_with_the_real_reporter(tmp_path,
                                                   monkeypatch) -> None:
    """All eleven, not the four that happen never to report anything.

    ``test_the_reports_run_on_an_empty_project`` only walked 1.5.2 up to
    1.5.5, and those four are precisely the ones that never call the
    reporter. That is how 1.5.10 could stand green while it fell over on
    screen straight away.
    """
    monkeypatch.setattr(test_panel, "MATRIX_REPORT",
                        tmp_path / "modelmatrix.md")
    context = _context(tmp_path)
    for action in test_panel.ACTIONS:
        outcome = action.function(context, reporter(), lambda: False)
        assert isinstance(outcome, str), action.code


def test_every_action_stops_cleanly_on_the_stop_button(tmp_path,
                                                       monkeypatch) -> None:
    monkeypatch.setattr(test_panel, "MATRIX_REPORT",
                        tmp_path / "modelmatrix.md")
    context = _context(tmp_path)
    for action in test_panel.ACTIONS:
        assert isinstance(action.function(context, reporter(), lambda: True),
                          str), action.code


# --------------------------------------------------------------------------
# "Hung" had come to mean something else
# --------------------------------------------------------------------------

def test_a_tripped_action_is_no_longer_called_hung() -> None:
    """Since B359 "hanging" is a different failure: a dead window.

    1.5.10 did not hang, it fell over after twenty-eight milliseconds -
    and the message sent the search in exactly the wrong direction.
    """
    for key in ("log_test_failed", "test_failed", "test_project_failed"):
        text = TRANSLATIONS["nl"][key]
        assert "vast" not in text, f"{key}: {text!r}"
        assert "struikel" in text, f"{key}: {text!r}"
    assert set(TRANSLATIONS["nl"]) == set(TRANSLATIONS["en"])


@pytest.mark.parametrize("key", ["test_failed", "test_project_failed"])
def test_the_messages_keep_their_placeholder(key) -> None:
    for language in ("nl", "en"):
        text = TRANSLATIONS[language][key]
        assert "{code}" in text or "{name}" in text, f"{key} ({language})"
