"""Tests for v0.122.0: B382 - modules/ and tools/ are English.

The last two files on the language guard's TODO list are gone from it:
``modules/test_panel.py`` (twenty-three names plus its Dutch docstrings)
and the nested reporter in ``modules/gui.py``. With those done the guard
turned red on its own accord, which is exactly what it was built for -
the list may only shrink, so a file that comes out clean has to be struck
from it.

Two things are pinned here.

The first is the shape of the reporter, because it is the one contract in
this file that has already broken twice. B357 changed it from
``report(name)`` to four arguments, B360 was the fallout of a type hint
that still described the old shape, and this round renamed all four
arguments at once. A rename that changes a contract is the same class of
change as B357 was; it deserves the same test.

The second is that the conversion did not quietly change behaviour. The
internal dict keys of 1.5.8 and the coupling coverage went to English in
the same round - those are data, not names, and a token-level rename does
not touch strings. Getting one wrong would not raise anything: the table
would simply print a KeyError-free blank or the history would stop
matching. So the keys are named here explicitly.
"""
from __future__ import annotations

import ast
import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import test_panel  # noqa: E402

#: The reporter as every action in the panel must be able to call it.
REPORTER = ["slot", "name", "done", "total"]


# --------------------------------------------------------------------------
# The reporter contract survived the rename
# --------------------------------------------------------------------------

def test_the_runner_hands_out_the_reporter_shape() -> None:
    """B357/B360 twice over: this contract has broken before."""
    from modules import gui

    tree = ast.parse(inspect.getsource(
        gui.MainWindow._do_fill_cache).lstrip())
    inner = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "report"]
    assert len(inner) == 1, "where did the runner's reporter go?"
    assert [a.arg for a in inner[0].args.args][:4] == REPORTER


def test_the_panel_side_of_the_bar_speaks_the_same_shape() -> None:
    from modules import gui

    names = list(inspect.signature(
        gui.MainWindow._on_test_progress).parameters)
    assert names[1:] == REPORTER


def test_every_action_still_takes_context_reporter_cancelled() -> None:
    """A renamed argument must not shift a position."""
    for action in test_panel.ACTIONS:
        names = list(inspect.signature(action.function).parameters)
        assert names[:3] == ["context", "report", "cancelled"], action.code


# --------------------------------------------------------------------------
# The data keys went along, and a rename cannot see those
# --------------------------------------------------------------------------

def test_the_gap_measurement_carries_english_names() -> None:
    """B526: 1.5.8 has gone; the measurement itself stayed for 1.5.11."""
    dutch = {"gezongen", "gaten", "stilte", "venster", "vensters",
             "project_naam", "uit", "aantal"}
    for name in ("_gaps_in", "_projects_by_gap"):
        function = getattr(test_panel, name)
        locals_ = set(function.__code__.co_varnames)
        assert not (locals_ & dutch), f"{name}: {locals_ & dutch}"


def test_the_coupling_coverage_carries_english_keys() -> None:
    source = inspect.getsource(test_panel._coupling_features)
    for key in ("words", "coupled", "multiple", "weak", "weak_share",
                "lowest", "energy", "gap", "filtered", "filler", "no_match"):
        assert f'"{key}"' in source, key


def test_the_matrix_row_reads_the_keys_that_are_written() -> None:
    """The dict is built in one function and printed in another; nothing
    connects the two but the spelling."""
    written = inspect.getsource(test_panel._coupling_features)
    printed = inspect.getsource(test_panel.big_trial)
    for key in ("words", "coupled", "multiple", "weak", "weak_share",
                "lowest", "energy", "gap", "filtered", "filler", "no_match"):
        assert f'"{key}"' in written and f"k['{key}']" in printed, key


def test_the_syllable_totals_use_the_same_names_twice() -> None:
    """``dict(shape=...)`` and ``total["shape"]`` are a keyword and a
    string: the rename touched one of them and not the other."""
    source = inspect.getsource(test_panel.syllable_checks)
    for key in ("shape", "silence", "between", "duration"):
        assert f"{key}=0" in source and f'total["{key}"]' in source, key


# --------------------------------------------------------------------------
# The register is untouched by all of this
# --------------------------------------------------------------------------

def test_the_model_levels_are_still_the_register_levels() -> None:
    """These are values in the register and columns in a report the user
    reads, not identifiers - so they stay Dutch on purpose."""
    from modules import model_register

    levels = {m.level for m in model_register.register()}
    assert {"blok", "zin", "koppeling"} <= levels
    source = inspect.getsource(test_panel._variants_from_register)
    assert '("blok", "zin", "koppeling")' in source
