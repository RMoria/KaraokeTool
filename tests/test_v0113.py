"""Tests for v0.113.0: B358 (the big trial, 1.5.11).

One test that sets all the models against each other: per level (block,
sentence, COUPLING, word), on their own, in pairs, in reversed order and
per project. The report goes into ``docs/modelmatrix.md`` and is written
out after every variant, because a hang at three in the morning must not
throw the whole night away.

The sharpest tests here are the ones that check whether the replacements
still fit the real call: the trial sets functions aside by overwriting
them, and that goes wrong silently the moment somebody renames a real
function or adds an argument to it.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline, test_panel  # noqa: E402
from modules.translations import TRANSLATIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _context(tmp_path: Path, name: str = "Proef"):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=name)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


def _all_variants():
    """(name, targets) of EVERY list of replacements in the trial.

    B361: the models now come from ``model_register`` instead of from a
    copy of their own in the test panel. The guards below keep doing
    exactly the same work - they only look in the new place.
    """
    from modules import model_register

    for model in model_register.register():
        yield model.label, list(model.targets)
    for name, targets in test_panel._orders():
        yield name, targets


# --------------------------------------------------------------------------
# The replacements fit the real functions
# --------------------------------------------------------------------------

def test_every_target_still_exists() -> None:
    """A renamed function has to fall over here, not in the night."""
    for name, targets in _all_variants():
        for module, attribute, _replacement in targets:
            assert hasattr(module, attribute), \
                f"{name}: {module.__name__}.{attribute} no longer exists"


def test_every_replacement_takes_the_required_arguments():
    """Able to take as many arguments as the real function demands.

    Without this test a replacement only falls over when the trial is an
    hour in - and by then the night is gone.
    """
    for name, targets in _all_variants():
        for module, attribute, replacement in targets:
            real = inspect.signature(getattr(module, attribute))
            required = [p for p in real.parameters.values()
                        if p.default is p.empty
                        and p.kind in (p.POSITIONAL_ONLY,
                                       p.POSITIONAL_OR_KEYWORD)]
            try:
                inspect.signature(replacement).bind_partial(
                    *[None] * len(required))
            except TypeError:
                pytest.fail(f"{name}: {attribute} takes {len(required)} "
                            f"argument(s), the replacement takes fewer")


def test_every_replacement_swallows_the_keyword_arguments_too() -> None:
    """The callers pass ``skip_filler=``, ``dropped_out=`` and so on."""
    for name, targets in _all_variants():
        for module, attribute, replacement in targets:
            real = inspect.signature(getattr(module, attribute))
            fake = inspect.signature(replacement)
            if any(p.kind is p.VAR_KEYWORD for p in fake.parameters.values()):
                continue
            for parameter in real.parameters.values():
                if parameter.default is parameter.empty:
                    continue
                try:
                    fake.bind_partial(**{parameter.name: None})
                except TypeError:
                    pytest.fail(f"{name}: {attribute} can be called with "
                                f"'{parameter.name}=', "
                                f"the replacement does not know it")


def test_a_replacement_gives_the_same_kind_of_answer() -> None:
    """The neutral shape has to hand the input back, not None."""
    from modules import model_register, song_text

    _m, _a, extend = model_register.by_code("B191").targets[0]
    assert extend("tekst", [("tekst", 0.0, 1.0)], 0, set()) == [0]
    _m, _a, creative = model_register.by_code("B228").targets[0]
    assert creative(["a", "b"], [], [[3], []]) == [[3], []]
    assert song_text.extend_coupling  # the real one is still there


# --------------------------------------------------------------------------
# The coupling really is in it
# --------------------------------------------------------------------------

def test_the_coupling_is_a_level_of_its_own() -> None:
    """B148 sits in the coupling, so that has to be in the matrix."""
    from modules import model_register

    levels = {m.level for m in model_register.register()}
    assert levels == {"blok", "zin", "koppeling", "woord", "venster"}


def test_the_coupling_models_that_matter_are_in_it() -> None:
    from modules import model_register

    codes = {m.code for m in model_register.register()
             if m.level == "koppeling"}
    for number in ("B258/B285", "B307/B337", "B213", "B276", "B159",
                   "B121", "B313"):
        assert number in codes, number


def test_b313_stands_in_only_one_place() -> None:
    """It was under 'zin' first; measuring twice gives two truths."""
    from modules import model_register

    places = [m.level for m in model_register.register()
              if m.code == "B313"]
    assert places == ["koppeling"]


def test_the_window_models_are_not_in_the_yardstick() -> None:
    """B191/B228 only run in ``word_coupling_view``.

    Putting them in the yardstick would give a table full of zeroes and
    cost a night; they belong in the coverage table.
    """
    source = inspect.getsource(pipeline._lyrics_alignment)
    assert "extend_coupling" not in source
    assert "creative_couplings" not in source
    from modules import model_register

    for code in ("B191", "B228"):
        model = model_register.by_code(code)
        assert model is not None and model.level == "venster", code
    measurable = {m.code for m in model_register.register()
                  if m.level in ("blok", "zin", "koppeling")}
    assert "B191" not in measurable and "B228" not in measurable


def test_the_coupling_features_stay_silent_on_an_empty_project(
        tmp_path) -> None:
    assert test_panel._coupling_features(_context(tmp_path), "Proef") == {}


# --------------------------------------------------------------------------
# Order
# --------------------------------------------------------------------------

def test_orders_really_are_reversed() -> None:
    names = [name for name, _t in test_panel._orders()]
    assert names and all("vóór" in name for name in names)


def test_an_order_variant_switches_off_more_than_one_function() -> None:
    """'B313 vóór B121' has to MOVE B313, not switch it off.

    Emptying only the energy placement would measure the same thing as
    the single model and quietly give the wrong conclusion.
    """
    targets = dict(test_panel._orders())["B313 vóór B121"]
    attributes = {a for _m, a, _v in targets}
    assert attributes == {"_clean_segments_and_alignment",
                          "_place_skipped_on_energy"}


# --------------------------------------------------------------------------
# The night has to finish
# --------------------------------------------------------------------------

def test_the_pairs_are_no_longer_pruned() -> None:
    """B366: the pruning threshold is gone, and it has to stay gone.

    In v0.115.0 only models with an own effect of >=0.02 s went along.
    That same table showed why that was wrong: the anchor test and the
    energy placement switched off together gave 5.66 s where 3.66 was
    expected. A model that does nothing on its own can be a safety net.
    """
    assert not hasattr(test_panel, "_PAAR_DREMPEL")
    source = inspect.getsource(test_panel.big_trial)
    assert "combinations(singles, 2)" in source
    assert "test_matrix_pairs_all" in source


def test_it_writes_out_after_every_variant() -> None:
    """A hang at three in the morning must not throw the night away."""
    source = inspect.getsource(test_panel.big_trial)
    assert source.count("write_report()") >= 8


def test_every_loop_watches_the_stop_button() -> None:
    source = inspect.getsource(test_panel.big_trial)
    assert source.count("cancelled()") >= 5


def test_the_models_are_always_put_back(tmp_path) -> None:
    """Even when a variant blows up halfway.

    If a replacement stays behind, the next measurement - and after that
    the program itself - runs on a fake.
    """
    from modules import model_register

    context = _context(tmp_path)
    # B361: apply the state of the register first, because that is what
    # the trial does too. What is measured here is whether a VARIANT
    # stays behind, not whether a disabled model has been applied.
    model_register.apply_disabled()
    before = {(m.__name__, a): getattr(m, a)
              for _name, targets in _all_variants()
              for m, a, _v in targets}
    real_rows = test_panel._yardstick_rows

    def crash(*_a, **_k):
        raise RuntimeError("broken")

    test_panel._yardstick_rows = crash
    try:
        with pytest.raises(RuntimeError):
            test_panel.big_trial(context, lambda *a, **k: None,
                                   lambda: False)
    finally:
        test_panel._yardstick_rows = real_rows
    after = {(m.__name__, a): getattr(m, a)
             for _name, targets in _all_variants()
             for m, a, _v in targets}
    assert before == after
    model_register.restore_all()


# --------------------------------------------------------------------------
# The panel and the report
# --------------------------------------------------------------------------

def test_the_big_trial_is_the_last_measuring_action() -> None:
    """B531: 1.5.12 stands behind it, but that is a job and not a
    measurement - which is why it falls outside this."""
    measuring = [a for a in test_panel.ACTIONS
                 if not a.heavy and not a.on_request]
    action = measuring[-1]
    assert action.code == "1.5.10"
    assert action.function is test_panel.big_trial
    assert action.all_projects


def test_the_report_can_be_redirected() -> None:
    """Otherwise a test overwrites the real report."""
    assert test_panel.MATRIX_REPORT.name == "modelmatrix.md"
    assert "MATRIX_REPORT" in inspect.getsource(test_panel.big_trial)


def test_the_trial_runs_on_an_empty_reference_set(tmp_path,
                                                  monkeypatch) -> None:
    report = tmp_path / "modelmatrix.md"
    monkeypatch.setattr(test_panel, "MATRIX_REPORT", report)
    outcome = test_panel.big_trial(_context(tmp_path),
                                      lambda *a, **k: None, lambda: False)
    assert isinstance(outcome, str)
    text = report.read_text(encoding="utf-8")
    for heading in ("## Uitgangspunt", "## Elk model apart anders",
                    "## Twee tegelijk anders", "## Volgorde",
                    "## Woordkoppeling (dekking)", "## Woord en lettergreep"):
        assert heading in text, heading


def test_a_cancelled_trial_stops_at_once(tmp_path, monkeypatch) -> None:
    report = tmp_path / "modelmatrix.md"
    monkeypatch.setattr(test_panel, "MATRIX_REPORT", report)
    measured: list[int] = []
    real = test_panel._yardstick_rows
    monkeypatch.setattr(test_panel, "_yardstick_rows",
                        lambda *a, **k: measured.append(1) or real(*a, **k))
    test_panel.big_trial(_context(tmp_path), lambda *a, **k: None,
                           lambda: True)
    assert len(measured) == 1          # only the baseline


def test_all_the_new_texts_are_in_both_languages() -> None:
    for key in ("test_matrix", "test_matrix_hint", "test_matrix_intro",
                "test_matrix_where", "test_matrix_pairs",
                "test_matrix_order",
                "test_matrix_coupling", "test_matrix_words",
                "test_matrix_done"):
        for language in ("nl", "en"):
            assert TRANSLATIONS[language].get(key, "").strip(), \
                f"{key} ({language})"
