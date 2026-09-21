"""Tests for v0.117.0: B368 through B371.

B368 the seconds counter stuck at 361 s while 1.5.10 was still running.
B369 the result of every action is written out at once, not only at the
     end of the whole series - and the crash-proof half goes straight to
     the log file.
B370 the duration per action in the measurement history, because log
     files are removed after five days.
B371 1.5.11 as the heavy bin: outside the 'all' button, invisible when
     there is nothing under it, with a version threshold per trial.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import model_register, test_history, test_panel  # noqa: E402
from modules.translations import TRANSLATIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setattr(test_history, "HISTORY_FILE",
                        tmp_path / "testhistorie.json")
    monkeypatch.setattr(test_panel, "COMBINATION_REPORT",
                        tmp_path / "modelcombinaties.md")
    yield
    model_register.restore_all()
    model_register.apply_settings({})
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
# B368 - the frozen seconds counter
# --------------------------------------------------------------------------

def test_the_main_bar_is_the_same_as_the_first_test_bar(qapp,
                                                        tmp_path) -> None:
    """This is the trap B368 fell into, and it is still there.

    The counter may therefore not lean on it any more - hence this test:
    if that shared bar ever disappears, this test may fall over and the
    separate state can go again.
    """
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    assert window._progress is window._progress_bars[0]


def test_the_counter_no_longer_leans_on_a_bar() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._tick_elapsed)
    assert "_show_elapsed" in source
    assert "maximum()" not in source, \
        "the counter may not hang on the maximum of a bar any more"


def test_the_counter_keeps_running_while_the_panel_reports(qapp,
                                                           tmp_path) -> None:
    """Exactly the 361 s case: the yardstick sets a project counter on
    bar zero and the seconds stood still."""
    import time

    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    window._set_busy(True)
    window._phase_start = time.monotonic() - 42
    # B402: a worker report no longer touches bar zero; the trap now sits
    # in the ACTION report, and that one does give bar zero a range.
    window._on_test_progress(window.ACTION_SLOT, "1.5.10", 3, 13)
    assert window._progress.maximum() == 13      # the trap is still there
    window._tick_elapsed()
    assert "42" in window._status.text(), window._status.text()


def test_a_real_percentage_does_silence_the_counter(qapp, tmp_path) -> None:
    """With a percentage the counter is redundant; it may keep quiet."""
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    window._set_busy(True)
    window._on_progress(5.0, 10.0)
    assert window._show_elapsed is False


# --------------------------------------------------------------------------
# B369 - write the result out at once
# --------------------------------------------------------------------------

def test_the_runner_writes_out_per_action() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "_test_result.emit" in source
    # The log file first: that is the part that survives a crash.
    assert source.index("logger.info(t(\"log_gui\")") < \
        source.index("_test_result.emit")


def test_on_done_does_not_dump_the_stack_a_second_time() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._do_fill_cache)
    tail = source[source.index("def on_done"):]
    assert "splitlines()" not in tail, "then everything stands twice"


def test_the_window_does_not_log_to_the_file_again() -> None:
    """The worker thread has already written the lines out."""
    from modules import gui

    source = inspect.getsource(gui.MainWindow._on_test_result)
    assert "_log_view_only" in source
    assert "logger" not in inspect.getsource(gui.MainWindow._log_view_only)


def test_the_result_travels_by_signal() -> None:
    """No Qt widget may be touched from a worker thread."""
    from modules import gui

    assert hasattr(gui.MainWindow, "_test_result")


# --------------------------------------------------------------------------
# B370 - the duration in the history
# --------------------------------------------------------------------------

def test_the_duration_of_an_action_is_kept(tmp_path) -> None:
    test_history.remember_duration("1.5.10", "0.117.0", 1673.0)
    assert test_history.durations("1.5.10") == [("0.117.0", 1673.0)]


def test_the_duration_per_project_is_carried_along(tmp_path) -> None:
    test_history.remember("1.5.5", "Lied", "0.1.0", "abc", {"x": 1},
                          seconds=2.5)
    entry = test_history.history("1.5.5", "Lied")[-1]
    assert entry["seconds"] == 2.5


def test_the_dispatcher_measures_the_duration_per_project(tmp_path) -> None:
    context = _context(tmp_path)
    test_panel.with_history(context, ["Proef"], lambda s: {"x": 1},
                            lambda *a, **k: None, lambda: False, "1.5.9")
    entry = test_history.history("1.5.9", "Proef")[-1]
    assert "seconds" in entry


def test_the_program_does_not_nag_about_the_duration() -> None:
    """The user asked for the number to be kept, not for a warning.

    The question "does this belong in 1.5.11?" is asked while analysing
    the data, not by the app itself.
    """
    source = (ROOT / "modules" / "test_panel.py").read_text(encoding="utf-8")
    assert "30 min" not in source and "1800" not in source


def test_the_version_distance_counts_the_middle_number(tmp_path) -> None:
    """0.110.1 is a repair, not a version of its own."""
    assert test_history.version_number("0.116.0") == 116
    assert test_history.version_number("0.110.1") == 110
    test_history.remember_duration("1.5.11a", "0.100.0", 1.0)
    assert test_history.versions_ago("1.5.11a", "0.120.0") == 20
    assert test_history.versions_ago("1.5.11a", "0.101.0") == 1


def test_never_run_simply_means_run_it(tmp_path) -> None:
    assert test_history.versions_ago("1.5.11b", "0.117.0") is None


# --------------------------------------------------------------------------
# B371 - the heavy bin
# --------------------------------------------------------------------------

def test_the_heavy_action_stands_outside_the_ceiling_of_ten() -> None:
    measuring = [a for a in test_panel.ACTIONS
                 if not a.heavy and not a.on_request]
    heavy = [a for a in test_panel.ACTIONS if a.heavy]
    chores = [a for a in test_panel.ACTIONS if a.on_request]
    # B526: nine since 1.5.8 went; the ceiling stays at ten.
    # B531: 1.5.12 is a chore and does not count towards that ceiling.
    assert len(measuring) == 9 <= test_panel.MAX_ACTIONS
    assert [a.code for a in heavy] == ["1.5.11"]
    assert [a.code for a in chores] == ["1.5.12"]


def test_ticking_everything_skips_the_heavy_one(qapp) -> None:
    """Hours of computing should be a deliberate choice, 'all' included."""
    panel = test_panel.TestPanel()
    panel._toggle_all()
    assert all(not a.heavy for a in panel.chosen())
    assert len(panel.chosen()) == 9


def test_the_heavy_action_can_still_be_ticked_on_its_own(qapp) -> None:
    panel = test_panel.TestPanel()
    heavy = [n for n, a in enumerate(panel._actions) if a.heavy]
    assert heavy, "1.5.11 should be visible now that it has trials under it"
    panel._ticks[heavy[0]].setChecked(True)
    assert [a.code for a in panel.chosen()] == ["1.5.11"]


def test_without_trials_the_heavy_action_disappears(qapp,
                                                    monkeypatch) -> None:
    """No empty row and no greyed-out button."""
    monkeypatch.setattr(test_panel, "HEAVY_TRIALS", ())
    assert all(not a.heavy for a in test_panel.visible_actions())
    panel = test_panel.TestPanel()
    ordinary = [a for a in test_panel.visible_actions()
                if not a.heavy and not a.on_request]
    assert len(ordinary) == 9
    # B531: 1.5.12 does stay - it does not hang on the trials.
    assert len(panel._ticks) == 10
    assert "1.5.11" not in " ".join(v.text() for v in panel._ticks)
    assert "1.5.12" in " ".join(v.text() for v in panel._ticks)


def test_every_heavy_trial_has_a_threshold() -> None:
    """B452: the threshold on versions is gone - it held back exactly the
    two trials that had to run. What remains is the shape."""
    for trial in test_panel.HEAVY_TRIALS:
        assert not hasattr(trial, "threshold")
        assert trial.code.startswith("1.5.11")
        for language in ("nl", "en"):
            assert TRANSLATIONS[language].get(trial.name_key, "").strip()


def test_an_already_measured_trial_is_skipped(tmp_path) -> None:
    """B452: once per version per state, like the rest of the panel."""
    context = _context(tmp_path)
    for trial in test_panel.HEAVY_TRIALS:
        test_panel._remember_heavy(context, trial.code, 1.0)
    outcome = test_panel.heavy_trial(context, lambda *a, **k: None,
                                     lambda: False)
    text = test_panel.COMBINATION_REPORT.read_text(encoding="utf-8")
    assert isinstance(outcome, str)
    on = [p for p in test_panel.HEAVY_TRIALS if not p.off]
    assert text.count("Al gemeten") == len(on)
    assert text.count("Uitgezet") == len(test_panel.HEAVY_TRIALS) - len(on)


def test_remeasuring_forces_a_heavy_trial(tmp_path, monkeypatch) -> None:
    from modules import __version__

    for trial in test_panel.HEAVY_TRIALS:
        test_history.remember_duration(trial.code, __version__, 1.0)
    monkeypatch.setattr(test_panel, "REMEASURE", True)
    test_panel.heavy_trial(_context(tmp_path), lambda *a, **k: None,
                           lambda: False)
    text = test_panel.COMBINATION_REPORT.read_text(encoding="utf-8")
    assert "Overgeslagen" not in text


def test_the_heavy_trial_stops_on_the_stop_button(tmp_path) -> None:
    outcome = test_panel.heavy_trial(_context(tmp_path),
                                     lambda *a, **k: None, lambda: True)
    assert isinstance(outcome, str)


# --------------------------------------------------------------------------
# The clusters
# --------------------------------------------------------------------------

def test_clusters_link_only_real_interactions() -> None:
    pairs = [("A", "B", 2.00), ("B", "C", 0.30), ("D", "E", 0.01),
             ("F", "G", -0.50)]
    groups = test_panel.clusters_from_pairs(pairs)
    assert {"A", "B", "C"} in groups
    assert {"F", "G"} in groups
    assert not any("D" in g or "E" in g for g in groups), \
        "0.01 s is noise, not an interaction"


def test_a_cluster_of_six_is_sixty_four_measurements() -> None:
    """The whole reason this is affordable: 2^6 + 2^2 = 68 instead of
    2^17 = 131,072."""
    pairs = [(f"M{n}", f"M{n + 1}", 1.0) for n in range(5)]
    group = test_panel.clusters_from_pairs(pairs)[0]
    assert len(group) == 6 and 2 ** len(group) == 64


def test_without_a_model_matrix_nothing_is_guessed(tmp_path,
                                                   monkeypatch) -> None:
    """Guessing at the clusters would make the whole trial worthless."""
    monkeypatch.setattr(test_panel, "MATRIX_REPORT",
                        tmp_path / "bestaat_niet.md")
    with pytest.raises(test_panel.TrialSkipped) as caught:
        test_panel.cluster_trial(_context(tmp_path),
                                 lambda *a, **k: None, lambda: False)
    assert caught.value.lines == [TRANSLATIONS["nl"]["heavy_needs_matrix"]]


def test_the_pairs_come_from_the_report_of_1_5_10(tmp_path,
                                                  monkeypatch) -> None:
    """Measuring them again would cost half an hour; they are there."""
    report = tmp_path / "modelmatrix.md"
    report.write_text(
        "## Twee tegelijk anders\n\n"
        "| model A | model B | samen | los opgeteld | verschil |\n"
        "| --- | --- | ---: | ---: | ---: |\n"
        "| B329 ankertoets | B313 energie | 5.66 s | 3.66 s | +2.00 |\n"
        "| B334 lus | B342 grens | 3.25 s | 3.25 s | +0.00 |\n",
        encoding="utf-8")
    monkeypatch.setattr(test_panel, "MATRIX_REPORT", report)
    pairs = test_panel._pairs_from_report()
    assert len(pairs) == 2
    groups = test_panel.clusters_from_pairs(pairs)
    assert groups == [{"B329 ankertoets", "B313 energie"}]


# --------------------------------------------------------------------------
# The search holds songs back
# --------------------------------------------------------------------------

def test_the_search_holds_songs_back() -> None:
    """With 131,072 states and 188 lines you are guaranteed to find
    noise."""
    source = inspect.getsource(test_panel.search_trial)
    assert "_HELD_BACK" in source
    assert "heavy_search_overfit" in source, \
        "a result that is too good on the search set has to be reported"


def test_too_few_projects_gives_no_result(tmp_path) -> None:
    with pytest.raises(test_panel.TrialSkipped) as caught:
        test_panel.search_trial(_context(tmp_path), lambda *a, **k: None,
                                lambda: False)
    assert len(caught.value.lines) == 1


def test_the_search_is_repeatable() -> None:
    """A fixed sequence, or the same measurement gives two answers."""
    source = inspect.getsource(test_panel.search_trial)
    assert "random.Random(" in source


def test_all_new_texts_exist_in_both_languages() -> None:
    for key in ("test_heavy", "test_heavy_hint", "heavy_intro",
                "heavy_clusters", "heavy_search", "heavy_cluster_intro",
                "heavy_cluster_too_big", "heavy_needs_matrix",
                "heavy_no_clusters", "heavy_search_intro",
                "heavy_search_split", "heavy_search_verdict",
                "heavy_search_overfit", "heavy_too_few_songs",
                "heavy_already", "heavy_not_chosen",
                "heavy_switched_off", "heavy_done", "log_test_result"):
        for language in ("nl", "en"):
            assert TRANSLATIONS[language].get(key, "").strip(), \
                f"{key} ({language})"
