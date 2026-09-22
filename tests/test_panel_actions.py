"""What the test panel still offers, and what it no longer does (B563).

Nine of the ten numbered measurements were experiments about the
PROGRAM - what is a model worth, does cutting help, is the loudest
level better. Those questions have been answered, the answers are in
production, and running them again stopped changing a decision: the
model register has not moved since v0.148.0 while 1.5.10 costs a
hundred and forty-four seconds and 1.5.11 costs hours. Measuring for
the sake of measuring is not a reason to keep a button.

What is left is what says something about the SONGS, and that is worth
a look at every new one. Those five became one action.
"""
from __future__ import annotations

import pytest

from modules import test_panel


def test_the_panel_shows_what_is_still_worth_clicking() -> None:
    """Three lines: fill the cache, check the projects, make the videos
    again. Everything else is switched off, not deleted."""
    assert [a.code for a in test_panel.visible_actions()] == [
        "1.5.1", "1.5.2", "1.5.12"]


def test_a_retired_action_keeps_its_code_and_its_function() -> None:
    """Switched off the way a heavy trial is (B454): the idea stays
    readable and is one word away from measuring again, and its code
    keeps meaning the same thing in ``docs/testhistorie.json``.
    """
    retired = {a.code: a for a in test_panel.ACTIONS if a.done}
    assert set(retired) == {"1.5.3", "1.5.4", "1.5.5", "1.5.6", "1.5.7",
                            "1.5.9", "1.5.10", "1.5.11"}
    for action in retired.values():
        assert callable(action.function), action.code
        assert action.name_key and action.explanation_key, action.code


def test_filling_the_cache_never_joins_the_all_tick() -> None:
    """It is the only light-looking action that starts Demucs and
    Whisper. On twenty-two projects with a cleared cache that is hours,
    and until B563 it joined "tick all" - which put a run of many hours
    one click away from a run of one minute.
    """
    fill = next(a for a in test_panel.ACTIONS if a.code == "1.5.1")
    assert fill.on_request is True
    in_the_tick = [a.code for a in test_panel.visible_actions()
                   if not a.heavy and not a.on_request]
    assert in_the_tick == ["1.5.2"]


def test_the_one_action_runs_every_part_and_says_what_each_is(
        monkeypatch) -> None:
    """The five were five ticks that were always ticked together.

    Merged into one button their explanations have nowhere else to go,
    so each part prints its own above its table - a report of five
    tables without a word about what they mean is a report nobody reads
    twice.
    """
    from modules.translations import t

    order = []

    def marker(name):
        def run(context, report, cancelled):
            order.append(name)
            return f"<{name}>"
        return run

    for name in ("benchmark_status", "project_report", "missing_repetitions",
                 "yardstick", "syllable_checks"):
        monkeypatch.setattr(test_panel, name, marker(name))

    text = test_panel.check_all_projects(None, lambda *a: None, lambda: False)

    assert order == ["benchmark_status", "project_report",
                     "missing_repetitions", "yardstick", "syllable_checks"]
    for name in order:
        assert f"<{name}>" in text
    for key in ("test_status_hint", "test_reports_hint", "test_missing_hint",
                "test_ruler_hint", "test_syllables_hint"):
        assert t(key) in text, key


def test_stop_cuts_the_one_action_short(monkeypatch) -> None:
    """Every action looks at ``cancelled()`` inside its loop, and this
    one is now a loop over five. Without this check Stop would still
    have to sit out the four parts that come after it."""
    ran = []

    def marker(context, report, cancelled):
        ran.append(1)
        return "x"

    for name in ("benchmark_status", "project_report", "missing_repetitions",
                 "yardstick", "syllable_checks"):
        monkeypatch.setattr(test_panel, name, marker)

    test_panel.check_all_projects(None, lambda *a: None, lambda: True)
    assert ran == []


@pytest.mark.parametrize("code", ["1.5.1", "1.5.2", "1.5.12"])
def test_every_visible_action_has_both_its_texts(code) -> None:
    """A line in the panel with a missing name or explanation is a line
    that says ``test_check_all`` to the user."""
    from modules.translations import TRANSLATIONS

    action = next(a for a in test_panel.ACTIONS if a.code == code)
    for language in ("nl", "en"):
        assert action.name_key in TRANSLATIONS[language], (code, language)
        assert action.explanation_key in TRANSLATIONS[language], (
            code, language)


def test_one_bad_part_does_not_cost_the_other_four(monkeypatch) -> None:
    """Before the merge each part was an action of its own and the
    runner caught per action, so a part that fell over cost one report
    of five. Merged into one button, an uncaught error would throw away
    the four that DID work - including the yardstick, which is the
    expensive one.
    """
    def good(name):
        def run(context, report, cancelled):
            return f"<{name}>"
        return run

    def bad(context, report, cancelled):
        raise RuntimeError("this part is broken")

    for name in ("benchmark_status", "project_report",
                 "yardstick", "syllable_checks"):
        monkeypatch.setattr(test_panel, name, good(name))
    monkeypatch.setattr(test_panel, "missing_repetitions", bad)

    text = test_panel.check_all_projects(None, lambda *a: None,
                                          lambda: False)

    for name in ("benchmark_status", "project_report", "yardstick",
                 "syllable_checks"):
        assert f"<{name}>" in text, name
    assert "this part is broken" not in text
    assert text.count("---") >= 5          # all five headings are there


def test_the_top_bar_follows_the_five_parts(monkeypatch) -> None:
    """B409, once more. The parts reported to work slot 0 at first, and
    the first project name of a part overwrites that a moment later -
    so the top row never moved and the user could see that something
    was running but not which of the five."""
    seen = []

    def report(slot, label, done, total):
        seen.append((slot, label, done, total))

    for name in ("benchmark_status", "project_report", "missing_repetitions",
                 "yardstick", "syllable_checks"):
        monkeypatch.setattr(test_panel, name,
                            lambda context, r, c: "x")

    test_panel.check_all_projects(None, report, lambda: False)

    action_rows = [row for row in seen if row[0] == test_panel.ACTION_SLOT]
    assert action_rows, seen
    assert all(row[3] == 5 for row in action_rows)
    assert action_rows[-1][2] == 5          # and it reaches the end
