"""Tests for v0.116.0: B361 through B367.

Six pieces in one release:

B361 the model register - every idea is on record with a state, and a
     model that turns out to be worth nothing goes OFF, not away.
B362 the measurement history - per action, project and version, so that
     an unchanged project is skipped and a new version can be laid
     beside the previous three.
B363 word and syllable checks - four kinds of check without a single
     hand-placed syllable.
B364 faster - convert the vocal stem once per project instead of once
     per variant, and spread the last two serial sections over both
     lanes.
B365 at most ten actions under 1.5, so small tests were merged.
B366 measure every pair, with no pruning threshold.
B367 the 'all' button at the top.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import model_register, test_history, test_panel  # noqa: E402
from modules import timing_checks  # noqa: E402
from modules.translations import TRANSLATIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    """Never let the register or the history leak into another test."""
    monkeypatch.setattr(test_history, "HISTORY_FILE",
                        tmp_path / "testhistorie.json")
    yield
    model_register.restore_all()
    model_register.apply_settings({})
    test_panel.limit_to_current(False)
    test_panel.REMEASURE = False


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
# B361 - the register
# --------------------------------------------------------------------------

def test_every_model_has_a_code_a_name_and_a_level() -> None:
    codes = [m.code for m in model_register.register()]
    assert len(codes) == len(set(codes)), "duplicate B numbers"
    for model in model_register.register():
        assert model.code.startswith("B"), model.code
        assert model.name.strip()
        assert model.level in model_register.LEVELS, model.level
        assert model.targets, f"{model.code} cannot be switched off"


def test_a_switched_off_model_says_why() -> None:
    """A state without a reason is a state nobody dares to reverse
    later on."""
    for model in model_register.register():
        if not model.default_on:
            assert model.reason.strip(), model.code


def test_b213_is_on_again_because_the_reference_set_grew() -> None:
    """B536: the verdict from v0.115.0 (-0.13 s) is out of date.

    The exhaust trial measured it the other way round twice, on 26 and
    31 August: with B213 ON the error is 0.18 s lower. A switched-off
    model therefore keeps running along - otherwise such a verdict
    stands for thirty versions.
    """
    model = model_register.by_code("B213")
    assert model is not None and model.default_on is True
    assert not model.reason                  # on, so no reason needed


def test_switching_off_replaces_and_switching_on_restores() -> None:
    from modules import song_text

    real = song_text.align_lyrics
    model_register.apply_settings({"B213": False})
    assert "B213" in model_register.apply_disabled()
    assert song_text.align_lyrics is not real
    model_register.apply_settings({"B213": True})
    model_register.apply_disabled()
    assert song_text.align_lyrics is real


def test_switching_off_twice_changes_nothing_extra() -> None:
    """Otherwise the second round stores the REPLACEMENT as the original."""
    from modules import song_text

    real = song_text.align_lyrics
    model_register.apply_settings({"B213": False})
    model_register.apply_disabled()
    model_register.apply_disabled()
    model_register.apply_settings({"B213": True})
    model_register.apply_disabled()
    assert song_text.align_lyrics is real


def test_an_unknown_model_in_the_settings_is_ignored() -> None:
    model_register.apply_settings({"B999": False})
    assert model_register.disabled_now() == ()
    assert model_register.enabled("B999") is True


def test_the_state_counts_in_the_dependency_chain() -> None:
    """B311: a switched-off model changes the timing, so the derived
    artefacts have to lapse just as they do for a changed setting."""
    from dataclasses import replace

    from modules import pipeline
    from modules.config import default_config

    base = default_config()
    other = replace(base, models={"B343": False})
    assert (pipeline._config_signature(base)["config:models"]
            != pipeline._config_signature(other)["config:models"])


def test_the_settings_keep_the_state(tmp_path) -> None:
    from dataclasses import replace

    from modules import config as config_module

    path = tmp_path / "config.json"
    config_module.save_config(
        replace(config_module.default_config(), models={"B213": False}), path)
    assert config_module.load_config(path).models == {"B213": False}


def test_the_matrix_measures_a_switched_off_model_the_other_way() -> None:
    """Exactly why the register exists: a switched-off idea keeps
    running along and reports itself the moment it IS worth something.

    B536: the example is now the hallucination filter, because B213 went
    back on after that same measurement - which only underlines what
    this check is about.
    """
    variants = {m.code: (targets, on) for _n, m, targets, on
                in test_panel._variants_from_register()}
    assert "B258/B285" in variants, "a switched-off model may not drop out"
    targets, on = variants["B258/B285"]
    assert on is False
    assert [a for _m, a, _v in targets] == ["_filter_hallucinations"]
    # The "other side" of off is the REAL function. Right now that one is
    # NOT on the module (the replacement is), so the variant would put it
    # back - which is precisely what "what would switching it on give us"
    # means.
    from modules import pipeline
    _module, _attribute, back = targets[0]
    assert back is not pipeline._filter_hallucinations
    assert "segments" in inspect.signature(back).parameters


# --------------------------------------------------------------------------
# B362 - the measurement history
# --------------------------------------------------------------------------

def test_a_stored_result_comes_back(tmp_path) -> None:
    test_history.remember("1.5.5", "Lied", "0.1.0", "abc", {"new_moved": 1.5})
    assert test_history.lookup("1.5.5", "Lied", "0.1.0", "abc") == \
        {"new_moved": 1.5}


def test_another_version_does_not_count(tmp_path) -> None:
    test_history.remember("1.5.5", "Lied", "0.1.0", "abc", {"x": 1})
    assert test_history.lookup("1.5.5", "Lied", "0.2.0", "abc") is None


def test_changed_data_does_not_count(tmp_path) -> None:
    """The heart of "with new data it does have to be redone"."""
    test_history.remember("1.5.5", "Lied", "0.1.0", "abc", {"x": 1})
    assert test_history.lookup("1.5.5", "Lied", "0.1.0", "gewijzigd") is None


def test_only_three_versions_are_kept(tmp_path) -> None:
    for n in range(6):
        test_history.remember("1.5.5", "Lied", f"0.{n}.0", "abc", {"x": n})
    kept = [e["version"] for e in test_history.history("1.5.5", "Lied")]
    assert kept == ["0.3.0", "0.4.0", "0.5.0"]
    assert test_history.KEEP_VERSIONS == 3


def test_the_fingerprint_changes_with_a_switched_off_model(tmp_path) -> None:
    context = _context(tmp_path)
    model_register.restore_all()
    before = test_history.project_fingerprint(context, "Proef")
    model_register.apply_settings({"B343": False})
    model_register.apply_disabled()
    assert test_history.project_fingerprint(context, "Proef") != before


def test_the_comparison_table_puts_the_versions_side_by_side(tmp_path) -> None:
    test_history.remember("1.5.5", "Lied", "0.1.0", "a", {"new_moved": 3.4})
    test_history.remember("1.5.5", "Lied", "0.2.0", "b", {"new_moved": 3.1})
    rows = test_history.comparison("1.5.5", ["Lied"], "0.2.0", "new_moved")
    assert any("0.1.0" in r for r in rows)
    assert any("3.40" in r and "3.10" in r for r in rows)


def test_a_project_without_history_gets_a_dash(tmp_path) -> None:
    test_history.remember("1.5.5", "Een", "0.1.0", "a", {"new_moved": 1.0})
    rows = test_history.comparison("1.5.5", ["Een", "Twee"], "0.2.0",
                                   "new_moved")
    assert any(r.startswith("| Twee |") and "-" in r for r in rows)


def test_the_dispatcher_skips_a_known_project(tmp_path) -> None:
    context = _context(tmp_path)
    seen: list[str] = []

    def work(song: str):
        seen.append(song)
        return {"value": 1}

    for _round in range(2):
        test_panel.with_history(context, ["Proef"], work,
                                lambda *a, **k: None, lambda: False, "1.5.9")
    assert seen == ["Proef"], "the second round had to reuse the result"
    assert test_panel.SKIPPED["1.5.9"] == 1


def test_remeasuring_ignores_the_memory(tmp_path) -> None:
    context = _context(tmp_path)
    seen: list[str] = []
    for again in (False, True):
        test_panel.with_history(context, ["Proef"],
                                lambda s: seen.append(s) or {"x": 1},
                                lambda *a, **k: None, lambda: False,
                                "1.5.9", again)
    assert seen == ["Proef", "Proef"]


def test_the_dispatcher_does_not_mistake_a_dict_for_lines(tmp_path) -> None:
    """B362: the loop first ran over the KEYS of such an answer."""
    context = _context(tmp_path)
    out = test_panel.across_projects(context, ["a"], lambda s: {"project": s},
                                     lambda *a, **k: None, lambda: False)
    assert out == [{"project": "a"}]


# --------------------------------------------------------------------------
# B363 - word and syllable checks
# --------------------------------------------------------------------------

class _Syllable(dict):
    def __init__(self, text, start, end, held=False):
        super().__init__(text=text, start=start, end=end, held=held)


def _line(*syllables):
    return {"syllables": list(syllables)}


def test_a_tidy_line_draws_no_complaints() -> None:
    found = timing_checks.Findings()
    timing_checks.shape_checks(
        [_line(_Syllable(" ka", 0.0, 0.3), _Syllable("ra", 0.3, 0.6),
               _Syllable("o", 0.6, 0.9), _Syllable("ke", 0.9, 1.2))],
        found)
    out = found.as_dict()
    assert out["out_of_order"] == 0 and out["overlapping"] == 0
    assert out["too_short"] == 0 and out["gaps_in_word"] == 0
    assert out["syllables"] == 4


def test_a_syllable_of_eight_milliseconds_stands_out() -> None:
    found = timing_checks.Findings()
    timing_checks.shape_checks(
        [_line(_Syllable(" a", 0.0, 0.008),
               _Syllable("b", 0.008, 0.9))], found)
    assert found.too_short == 1


def test_overlapping_syllables_stand_out() -> None:
    found = timing_checks.Findings()
    timing_checks.shape_checks(
        [_line(_Syllable(" a", 0.0, 0.5), _Syllable("b", 0.3, 0.9))],
        found)
    assert found.overlapping == 1


def test_nine_syllables_a_second_is_not_singing() -> None:
    found = timing_checks.Findings()
    many = [_Syllable(f" w{n}", n * 0.05, n * 0.05 + 0.05)
            for n in range(20)]
    timing_checks.shape_checks([_line(*many)], found)
    assert found.too_fast_lines == 1


def test_the_same_line_twice_over_gives_zero_divergence() -> None:
    found = timing_checks.Findings()
    first = _line(_Syllable(" la", 0.0, 0.5), _Syllable("la", 0.5, 1.0))
    second = _line(_Syllable(" la", 10.0, 11.0),
                   _Syllable("la", 11.0, 12.0))
    timing_checks.repetition_consistency([first, second], found)
    assert found.repeat_pairs == 1
    assert found.as_dict()["repeat_divergence"] == pytest.approx(0.0)


def test_a_skewed_repeat_does_give_divergence() -> None:
    found = timing_checks.Findings()
    first = _line(_Syllable(" la", 0.0, 0.5), _Syllable("la", 0.5, 1.0))
    second = _line(_Syllable(" la", 0.0, 0.9), _Syllable("la", 0.9, 1.0))
    timing_checks.repetition_consistency([first, second], found)
    assert found.as_dict()["repeat_divergence"] > 0.3


def test_the_checks_run_on_an_empty_project(tmp_path) -> None:
    out = timing_checks.inspect(_context(tmp_path), [])
    assert out["lines"] == 0 and out["in_silence"] == 0
    # B525: the boundary crossing is gone; it compared the words of the
    # parody with the measured boundaries of the original.
    assert "boundary_crossings" not in out


# --------------------------------------------------------------------------
# B364 - faster
# --------------------------------------------------------------------------

def test_the_vocal_stem_is_converted_only_once() -> None:
    source = (ROOT / "tools" / "timing_regression.py").read_text(
        encoding="utf-8")
    assert "_VOCALS_READY" in source
    assert "def _stable_vocals" in source
    assert "shutil.copy2" in source, "copy2 keeps the modification time"


def test_the_yardstick_is_loaded_only_once() -> None:
    source = inspect.getsource(test_panel._regression_module)
    assert "_REGRESSION" in source
    assert "exec_module" not in inspect.getsource(test_panel._yardstick_rows)


def test_the_last_two_sections_use_both_workers() -> None:
    """They ran in a plain loop and therefore on a single core."""
    source = inspect.getsource(test_panel.big_trial)
    head = source.index("## Woordkoppeling")
    tail = source[head:]
    assert tail.count("across_projects(") == 2
    assert "for song in _projects(context)" not in tail


# --------------------------------------------------------------------------
# B365 / B366 / B367 - the panel
# --------------------------------------------------------------------------

def test_there_are_at_most_ten_light_actions() -> None:
    """B371: the ceiling applies to the ordinary work; 1.5.11 stands
    outside it as the heavy bin."""
    light = [a for a in test_panel.ACTIONS
             if not a.heavy]
    assert len(light) <= test_panel.MAX_ACTIONS == 10
    # B526: ascending and unique; 1.5.8 is vacant since that action went.
    numbers = [int(a.code.rsplit(".", 1)[1]) for a in test_panel.ACTIONS]
    assert numbers == sorted(numbers) and len(numbers) == len(set(numbers))


def test_the_three_cheap_reports_sit_in_one_action(tmp_path) -> None:
    action = next(a for a in test_panel.ACTIONS if a.code == "1.5.3")
    assert action.function is test_panel.project_report
    source = inspect.getsource(test_panel.project_report)
    for part in ("_text_rows", "_filter_rows", "_structure_rows"):
        assert part in source, part


def test_the_syllable_checks_have_an_action_of_their_own() -> None:
    action = next(a for a in test_panel.ACTIONS if a.code == "1.5.7")
    assert action.function is test_panel.syllable_checks


def test_every_pair_is_measured() -> None:
    source = inspect.getsource(test_panel.big_trial)
    assert "itertools.combinations(singles, 2)" in source
    assert "DREMPEL" not in source


def test_the_all_button_ticks_everything_on_and_off_again(qapp) -> None:
    panel = test_panel.TestPanel()
    assert panel.chosen() == [], "everything is off when it opens"
    panel._toggle_all()
    light = [a for a in test_panel.visible_actions()
             if not a.heavy and not a.on_request]
    assert len(panel.chosen()) == len(light)
    assert all(not a.heavy for a in panel.chosen()), \
        "a heavy trial may never ride along on 'all'"
    assert all(not a.on_request for a in panel.chosen()), \
        "remaking every video may never ride along on 'all' (B531)"
    assert panel._all_button.text() == TRANSLATIONS["nl"]["test_select_none"]
    panel._toggle_all()
    assert panel.chosen() == []
    assert panel._all_button.text() == TRANSLATIONS["nl"]["test_select_all"]


def test_the_all_button_completes_a_half_selection(qapp) -> None:
    panel = test_panel.TestPanel()
    panel._ticks[0].setChecked(True)
    panel._toggle_all()
    light = [a for a in test_panel.visible_actions()
             if not a.heavy and not a.on_request]
    assert len(panel.chosen()) == len(light)


def test_remeasure_is_off_when_the_panel_opens(qapp) -> None:
    assert test_panel.TestPanel().remeasure() is False


def test_the_runner_passes_remeasure_along() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "remeasure()" in source
    assert source.index("REMEASURE") < source.index("def task")


def test_all_new_texts_exist_in_both_languages() -> None:
    keys = [a.name_key for a in test_panel.ACTIONS]
    keys += [a.explanation_key for a in test_panel.ACTIONS]
    keys += ["test_select_all", "test_select_none", "test_force_again",
             "test_skipped_note", "test_history_head", "test_history_note",
             "test_syllable_intro", "test_syllable_total", "test_on",
             "test_off", "test_with", "test_without", "test_all_on",
             "test_matrix_state", "test_matrix_symmetry",
             "test_matrix_pairs_all", "test_model_state",
             "log_model_disabled", "log_model_unknown"]
    for key in keys:
        for language in ("nl", "en"):
            assert TRANSLATIONS[language].get(key, "").strip(), \
                f"{key} ({language})"
