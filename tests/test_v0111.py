"""Tests for v0.111.0: the test panel behind 1.5 and the publication list.

Button 1.5 is called "Test" now and opens a tick list with ten numbered
actions. Further: "Lied-project" without the explanation in brackets, and
a guard that demands temporary code be on the publication list.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import test_panel  # noqa: E402
from modules.translations import TRANSLATIONS, t  # noqa: E402

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
# The numbering
# --------------------------------------------------------------------------

def test_the_actions_are_numbered_upwards() -> None:
    """"Run 1.5.3" has to mean one thing.

    B526: 1.5.8 has been taken out and its number stays empty. Shifting
    the rest up would give every number in the log, in the test history
    and in conversation a different meaning - and that is exactly what a
    number must never do. A gap is more honest than a renumbering; the
    next investigation that comes along takes 1.5.8 again.
    """
    numbers = [int(action.code.rsplit(".", 1)[1])
               for action in test_panel.ACTIONS]
    assert numbers == sorted(numbers)
    assert len(numbers) == len(set(numbers))
    assert numbers[0] == 1


def test_every_action_has_a_name_and_explanation_in_both_languages() -> None:
    for action in test_panel.ACTIONS:
        for key in (action.name_key, action.explanation_key):
            for language in ("nl", "en"):
                assert key in TRANSLATIONS[language], f"{key} ({language})"
                assert TRANSLATIONS[language][key].strip()


def test_filling_the_cache_is_action_one() -> None:
    """That one existed as a button of its own; it keeps its place at the
    front."""
    assert test_panel.ACTIONS[0].code == "1.5.1"
    assert test_panel.ACTIONS[0].function is test_panel.fill_cache


# --------------------------------------------------------------------------
# The window
# --------------------------------------------------------------------------

def test_the_ticks_are_always_off_when_it_opens(qapp) -> None:
    """A forgotten tick on 1.5.10 costs half an hour."""
    panel = test_panel.TestPanel()
    assert not any(v.isChecked() for v in panel._ticks)
    assert panel.chosen() == []


def test_ticking_gives_the_actions_in_number_order(qapp,
                                                   monkeypatch) -> None:
    """What comes out follows the list, not the order of clicking.

    B563: the panel shows three lines now, so ticks 4 and 1 pointed at
    nothing. The rule is about the ORDER that comes out and not about
    how long the list is, so the test lays out its own list of three
    real actions instead of hoping to find five in the panel.
    """
    from dataclasses import replace

    monkeypatch.setattr(
        test_panel, "ACTIONS",
        tuple(replace(a, done=False) for a in test_panel.ACTIONS
              if a.code in ("1.5.2", "1.5.4", "1.5.5")))
    panel = test_panel.TestPanel()
    panel._ticks[2].setChecked(True)
    panel._ticks[0].setChecked(True)
    assert [a.code for a in panel.chosen()] == ["1.5.2", "1.5.5"]


def test_button_15_is_called_test(qapp, tmp_path) -> None:
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    names = [b.text() for b in window._step_buttons]
    assert names[-1] == t("step_fill_cache") == "1.5. Test"


# --------------------------------------------------------------------------
# The actions themselves
# --------------------------------------------------------------------------

def test_every_action_watches_the_stop_button() -> None:
    """Stop has to work during a test as well."""
    import inspect

    for action in test_panel.ACTIONS:
        source = inspect.getsource(action.function)
        assert "cancelled" in source, action.code


def test_the_reports_run_on_an_empty_project(tmp_path) -> None:
    """They must not break when there is nothing to report.

    B360: the reporter here was ``lambda _t: None`` - the shape from
    before B357. With that, this test recorded the OLD contract and
    could never catch an action that did not keep to the new one. It
    comes from ``test_v0115`` now, where it is pinned to the runner; the
    full round over all eleven actions is there too.
    """
    from test_v0115 import reporter

    context = _context(tmp_path)
    for code in ("1.5.2", "1.5.3", "1.5.4", "1.5.5"):
        action = next(a for a in test_panel.ACTIONS if a.code == code)
        outcome = action.function(context, reporter(), lambda: False)
        assert isinstance(outcome, str)


def test_a_cancelled_test_stops_at_once(tmp_path) -> None:
    from test_v0115 import reporter

    context = _context(tmp_path)
    action = next(a for a in test_panel.ACTIONS if a.code == "1.5.2")
    assert isinstance(action.function(context, reporter(), lambda: True), str)


# --------------------------------------------------------------------------
# "Lied-project" without the brackets
# --------------------------------------------------------------------------

def test_the_song_project_has_no_explanation_in_its_heading() -> None:
    assert TRANSLATIONS["nl"]["song_group"] == "Lied-project"
    assert TRANSLATIONS["en"]["song_group"] == "Song project"


# --------------------------------------------------------------------------
# Temporary code is on the publication list
# --------------------------------------------------------------------------

def test_temporary_code_is_on_the_publication_list() -> None:
    """A TEMPORARY mark that is named nowhere gets forgotten.

    B136 was such a temporary button too; that it went out again was
    more luck than judgement.
    """
    document = (ROOT / "docs" / "development_log.md").read_text(
        encoding="utf-8")
    heading = document.index("## Decide before release")
    section = document[heading:document.index("\n## ", heading + 10)]
    marked = {
        path.relative_to(ROOT).as_posix()
        for folder in ("modules", "tools")
        for path in (ROOT / folder).glob("*.py")
        # B465: the English word counts as well. The code was converted
        # at B438/B446, so a new temporary note goes in in English - and
        # then this guard looked straight past it.
        if re.search(r"\b(TIJDELIJK|TEMPORARY)\b",
                     path.read_text(encoding="utf-8"))
    }
    assert marked, "no temporary code found - is the search still right?"
    for path in sorted(marked):
        assert path in section, f"{path} is temporary but not on the list"
