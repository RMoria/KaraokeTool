"""Tests for v0.132.0: B402 (the display) and B403/B404 (one language).

B402 - two things were wrong with the same display, and both came from
the rows having grown into a job they were never given. The top bar
showed the progress WITHIN one measurement round: on 1.5.10 it read
"2/17" and sat at 11% for eight minutes, so a run that was racing along
looked stuck. An action counts rounds and a work slot counts projects,
and those are different numbers - so the action got a channel of its
own. The second row named the busy slots on one line, and with nine
slots that line ran out of room; now every slot has its own chip.

B403/B404 - the user spotted Spanish going by in a Dutch song, and asked
whether Whisper gets the language once or per piece. Per piece, it turned
out, and worse: the test panel never asked ``pipeline._language_for`` at
all. That function has always done the right thing - one language, from
the COMPLETE lyrics - but the panel handed Whisper
``config.whisper.language``, which is "auto" by default. So every variant
detected its own language, and in the chunked run every one of ten pieces
did too.

That is not cosmetic. It pollutes the very comparison the trial exists
for: a variant can differ from its neighbour not because of the setting
under test but because that run decided the song was Spanish. Which means
the VAD result - 26.4 of 28 seconds against 0.9 for everything else - has
to be measured again before anybody believes it.
"""
from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from modules import test_panel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _context(tmp_path, name="Proef"):
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


@pytest.fixture()
def window(qapp, tmp_path):
    from modules import gui
    return gui.MainWindow(_context(tmp_path))


# --------------------------------------------------------------------------
# B403/B404 - one language, from the whole text
# --------------------------------------------------------------------------

def test_a_manual_choice_wins(tmp_path) -> None:
    """What the user pinned on tab 1 beats any detection."""
    from modules import pipeline

    context = _context(tmp_path)
    pipeline.set_language_choice(context, "nl")
    assert test_panel.probe_language(context, "Proef") == "nl"


def test_without_a_choice_it_falls_back_to_the_whole_original(
        tmp_path) -> None:
    """``run_info.json`` holds what Whisper decided on the COMPLETE
    original - one answer for the whole song, which is exactly what a
    chunked run must not decide for itself ten times over."""
    import json

    from modules import pipeline

    context = _context(tmp_path)
    folder = context.paths.output_dir / pipeline.TRACK_ORIGINAL
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run_info.json").write_text(
        json.dumps({"language": "nl"}), encoding="utf-8")
    assert test_panel.probe_language(context, "Proef") == "nl"


def test_with_nothing_to_go_on_it_stays_auto(tmp_path) -> None:
    """And then the trial says so, because a measurement whose language
    wanders is worth knowing about."""
    assert test_panel.probe_language(_context(tmp_path), "Proef") == "auto"


def test_a_broken_run_info_does_not_break_the_trial(tmp_path) -> None:
    from modules import pipeline

    context = _context(tmp_path)
    folder = context.paths.output_dir / pipeline.TRACK_ORIGINAL
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run_info.json").write_text("{kapot", encoding="utf-8")
    assert test_panel.probe_language(context, "Proef") == "auto"


def test_no_whisper_trial_uses_the_raw_setting() -> None:
    """The regression itself: ``base.language`` is "auto" by default, so
    reaching for it means every run detects again."""
    # B416: since the night job chunk_trial only hands out the songs;
    # the measuring - and therefore the language - sits in
    # _chunk_one_song.
    for name in ("_chunk_one_song",):
        source = inspect.getsource(getattr(test_panel, name))
        assert "base.language" not in source, name
        assert "probe_language(" in source, name


def test_the_language_is_pinned_before_the_cutting(tmp_path) -> None:
    """Ten pieces would otherwise be ten independent detections."""
    source = (inspect.getsource(test_panel.chunk_trial)
              + inspect.getsource(test_panel._chunk_one_song))
    assert source.index("probe_language(") < source.index("run_chunked(")


def test_every_piece_gets_the_same_language() -> None:
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "probe_lang_once", root / "tools" / "whisper_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = inspect.getsource(module.run_chunked)
    assert "language," in source or "language)" in source


def test_the_report_says_which_language_was_used() -> None:
    """So a table can never be read without knowing what it was measured
    under."""
    from modules.translations import TRANSLATIONS

    for name in ("_chunk_one_song",):
        assert "heavy_language_used" in inspect.getsource(
            getattr(test_panel, name)), name
    for language in ("nl", "en"):
        assert "{code}" in TRANSLATIONS[language]["heavy_language_used"]
        assert TRANSLATIONS[language]["heavy_language_auto"].strip()


# --------------------------------------------------------------------------
# B402 - the action has a channel of its own
# --------------------------------------------------------------------------

def test_the_action_slot_is_not_a_work_slot() -> None:
    from modules import gui

    assert test_panel.ACTION_SLOT < 0
    assert gui.MainWindow.ACTION_SLOT == test_panel.ACTION_SLOT


def test_the_counter_knows_its_total_up_front() -> None:
    seen = []
    steps = test_panel.Steps(lambda *a: seen.append(a), "1.5.10", 5)
    steps.tick()
    steps.tick()
    assert seen[0] == (test_panel.ACTION_SLOT, "1.5.10", 0, 5)
    assert seen[-1] == (test_panel.ACTION_SLOT, "1.5.10", 2, 5)


def test_the_counter_never_runs_past_its_total() -> None:
    seen = []
    steps = test_panel.Steps(lambda *a: seen.append(a), "1.5.10", 2)
    for _ in range(9):
        steps.tick()
    assert seen[-1][2] == 2


def test_the_action_progress_lands_on_the_top_row(window) -> None:
    window._on_test_progress(window.ACTION_SLOT, "1.5.10", 34, 258)
    assert window._progress_bars[0].maximum() == 258
    assert "34/258" in window._progress_labels[0].text()


def test_a_work_slot_leaves_the_top_row_alone(window) -> None:
    """The two used to fight over the same bar and the round always won
    - which is why 1.5.10 sat at 11%."""
    window._on_test_progress(window.ACTION_SLOT, "1.5.10", 34, 258)
    window._on_test_progress(3, "Lied D", 2, 17)
    assert window._progress_bars[0].maximum() == 258
    assert "34/258" in window._progress_labels[0].text()


def test_every_slot_gets_its_own_chip(window) -> None:
    for slot, song in enumerate(("Lied_A", "Lied D", "Lied_S")):
        window._on_test_progress(slot, song, slot, 17)
    assert [c.text() for c in window._slot_chips[:3]] == \
        ["Lied_A", "Lied D", "Lied_S"]


def test_a_ninth_slot_is_not_dropped(window) -> None:
    window._on_test_progress(8, "Lied_T", 8, 17)
    assert window._slot_chips[8].text() == "Lied_T"


def test_a_busy_chip_looks_different_from_an_idle_one(window) -> None:
    window._show_slot_chips(2)
    window._on_test_progress(0, "Lied D", 1, 17)
    assert window._slot_chips[0].styleSheet() == window._CHIP_BUSY
    assert window._slot_chips[1].styleSheet() == window._CHIP_IDLE


def test_a_new_run_empties_the_chips(window) -> None:
    window._on_test_progress(4, "Lied D", 1, 17)
    window._show_test_bars(["1.5.7", "1.5.7"])
    assert all(c.text() == "" for c in window._slot_chips)


def test_the_big_trial_counts_its_rounds() -> None:
    source = inspect.getsource(test_panel.big_trial)
    assert "Steps(report" in source and "pairs_count" in source
    assert 'report(0, f"1.5.10' not in source


def test_the_heavy_trial_counts_its_four() -> None:
    source = inspect.getsource(test_panel.heavy_trial)
    assert "Steps(report" in source and "len(HEAVY_TRIALS)" in source
