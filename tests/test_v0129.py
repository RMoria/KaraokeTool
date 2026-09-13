"""Tests for v0.129.0: B397 - which of the four is running?

1.5.11 is four investigations under one number, and on screen it said
only "1.5.11" plus a Dutch title. The user could not tell whether he was
looking at a, b, c or d - and therefore could not say which one to talk
about, which is exactly what those letters are for. The report had the
same problem: four headings, no codes.

This release also carries the reading of the first COMPLETE heavy run,
and that reading contains a correction. On the aborted run I reported a
combination worth 1.02 s - a third off the error. Over all 128
combinations that same combination comes out at +0.21, so it makes
things worse. The partial table was wrong and I passed it on as a lead;
the full one says no combination in this cluster beats the current state
by more than 0.04 s.

The search trial is the one that earned its keep. It found a combination
worth 0.32 s on the search set and 7.21 s WORSE on the three held-back
songs, and said so itself. That is precisely why those songs are held
back, and it fired on its first real run.
"""
from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import test_panel  # noqa: E402


def test_every_heavy_trial_has_a_letter() -> None:
    for trial in test_panel.HEAVY_TRIALS:
        assert trial.code.startswith("1.5.11")
        assert trial.code[-1] in "abcdefgh", trial.code


def test_the_running_trial_can_be_asked_for_its_code() -> None:
    assert test_panel.running_code().startswith("1.5.11")


def test_the_runner_sets_the_code_before_it_starts() -> None:
    source = inspect.getsource(test_panel.heavy_trial)
    assert "_RUNNING_CODE = trial.code" in source
    assert source.index("_RUNNING_CODE = trial.code") < \
        source.index("trial.function(")


def test_the_bar_shows_the_letter() -> None:
    """B409: on the ACTION row, not on a work slot.

    The letter used to go to slot 0, and the first project name
    overwrote it a moment later - so the top row read "1.5.11  2/4" and
    never said which of the four was running.
    """
    source = inspect.getsource(test_panel.heavy_trial)
    assert "steps.name(trial.code)" in source
    assert 'report(0, f"{trial.code} ' not in source


def test_the_report_headings_carry_the_letter() -> None:
    source = inspect.getsource(test_panel.heavy_trial)
    # B452: de kop wordt nu één keer gebouwd (``head``) en door beide
    # wegen gebruikt - overgeslagen én gedraaid. Dat legt deze test vast,
    # alleen niet meer als twee keer dezelfde f-string.
    assert source.count('f"## {trial.code} ') == 1
    assert source.count("lines += head") >= 2, \
        "zowel de overgeslagen als de gedraaide kop"


def test_no_trial_still_writes_a_bare_number() -> None:
    """The whole point: not one label may say just "1.5.11"."""
    for name in ("cluster_trial", "search_trial", "chunk_trial"):
        source = inspect.getsource(getattr(test_panel, name))
        assert 'f"1.5.11 ' not in source, name


def test_the_panel_lists_what_hides_under_the_number() -> None:
    """B453: the letters were a grey line of prose; they are ticks now,
    so the number no longer hides anything AND you can run one of them."""
    source = inspect.getsource(test_panel.TestPanel.__init__)
    assert "HEAVY_TRIALS" in source
    assert "trial.code" in source and "QCheckBox(label)" in source


# --------------------------------------------------------------------------
# The probe names its own winner
# --------------------------------------------------------------------------

