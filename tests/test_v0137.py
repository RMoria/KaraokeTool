"""Tests for v0.137.0: B435 to B438.

The user's own words: run the logic checks between the models, so that a
model that goes off the rails gets reported. The weighted error only
weighs line STARTS - a model can leave those alone and still wreck
everything inside the line, and that stays invisible in an average.
"""
from __future__ import annotations

import inspect

from modules import test_panel, timing, timing_checks


def _line(text: str, start: float, end: float):
    return timing.timedline_from_text(0, text, start, end)


def _flat(text: str, moment: float):
    """A line whose syllables all sit on one instant."""
    line = _line(text, moment, moment + 1.0)
    return timing.TimedLine(
        index=line.index, text=line.text, crowd=line.crowd,
        syllables=tuple(timing.Syllable(text=s.text, start=moment,
                                        end=moment)
                        for s in line.syllables))


# --------------------------------------------------------------------------
# B435 - the cheap checks, and what they catch
# --------------------------------------------------------------------------

def test_a_healthy_line_gives_no_complaints() -> None:
    counts = timing_checks.sanity([_line("zing maar mee", 10.0, 13.0)])
    assert counts["flat"] == 0
    assert counts["stacked"] == 0
    assert not timing_checks.broken(counts)


def test_syllables_without_a_moment_are_counted() -> None:
    counts = timing_checks.sanity([_flat("zing maar mee", 10.0)])
    assert counts["flat"] > 0
    assert timing_checks.broken(counts)


def test_stacked_syllables_are_counted() -> None:
    counts = timing_checks.sanity([_flat("zing maar mee", 10.0)])
    assert counts["stacked"] > 0


def test_a_reversed_line_is_broken() -> None:
    good = _line("zing maar mee", 10.0, 13.0)
    reversed_line = timing.TimedLine(
        index=0, text=good.text, crowd=False,
        syllables=tuple(timing.Syllable(text=s.text, start=s.end, end=s.start)
                        for s in good.syllables))
    assert timing_checks.broken(timing_checks.sanity([reversed_line]))


def test_the_cheap_check_needs_no_audio() -> None:
    """It has to be able to run a few hundred times in a row."""
    source = inspect.getsource(timing_checks.sanity)
    assert "audio_checks" not in source
    assert "shape_checks" in source


def test_the_measurement_carries_the_checks_along() -> None:
    from pathlib import Path

    import modules

    source = (Path(modules.__file__).resolve().parents[1] / "tools"
              / "timing_regression.py").read_text(encoding="utf-8")
    assert '"sanity": timing_checks.sanity(fresh)' in source


def test_an_alarm_names_the_model_and_the_project() -> None:
    test_panel.reset_alarms()
    test_panel.note_alarms(
        [{"project": "Proef", "sanity": {"flat": 3, "stacked": 2,
                                         "out_of_order": 0}}],
        chosen=["B380"])
    lines = test_panel.alarm_lines()
    text = "\n".join(lines)
    assert "Proef" in text
    assert "B380" in text
    assert "flat 3" in text


def test_a_clean_measurement_gives_a_reassuring_line() -> None:
    test_panel.reset_alarms()
    test_panel.note_alarms([{"project": "Proef",
                             "sanity": {"flat": 0, "stacked": 0}}])
    assert len(test_panel.alarm_lines()) == 2      # empty line + message


def test_the_same_alarm_is_reported_once() -> None:
    test_panel.reset_alarms()
    for _ in range(5):
        test_panel.note_alarms(
            [{"project": "Proef", "sanity": {"flat": 1}}], chosen=["B380"])
    rows = [line for line in test_panel.alarm_lines()
            if line.startswith("| Proef")]
    assert len(rows) == 1


def test_every_action_starts_with_a_clean_slate() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "reset_alarms()" in source


# --------------------------------------------------------------------------
# B436 - wall clock beside compute time
# --------------------------------------------------------------------------

def test_the_run_time_is_weighed_against_the_compute_time() -> None:
    """The user had other work running and the numbers were not
    comparable; the trial should say so itself."""
    from modules import gui

    source = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "process_time()" in source
    assert "log_test_busy_machine" in source


# --------------------------------------------------------------------------
# B437 - three countings, and the retired variants
# --------------------------------------------------------------------------

def test_the_countings_hang_under_the_syllable_checks() -> None:
    """The panel has a ceiling of ten actions on purpose."""
    assert len([a for a in test_panel.ACTIONS
                if not a.heavy]) <= test_panel.MAX_ACTIONS == 10
    source = inspect.getsource(test_panel.syllable_checks)
    assert "inventory_lines(context, cancelled)" in source


def test_the_inventory_asks_three_questions() -> None:
    source = inspect.getsource(test_panel.inventory_lines)
    for name in ("_uncoupled_words", "_held_syllables", "_block_drift"):
        assert name in source, name


def test_a_held_syllable_needs_both_conditions() -> None:
    """A slow song has long syllables everywhere, and then none of them
    is special."""
    assert test_panel.HELD_S > 0
    assert test_panel.HELD_FACTOR > 1
    source = inspect.getsource(test_panel._held_syllables)
    assert "HELD_S" in source and "HELD_FACTOR" in source


def test_the_exhausted_variants_are_switched_off_not_deleted() -> None:
    """The same way a model is switched off: the idea stays readable."""
    from pathlib import Path
    import importlib.util

    import modules

    path = (Path(modules.__file__).resolve().parents[1] / "tools"
            / "whisper_probe.py")
    spec = importlib.util.spec_from_file_location("probe_retired", path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    assert set(probe.VARIANTS) == {"current", "vad"}
    assert "wider" in probe.RETIRED
    assert "fallback_on" in probe.RETIRED
    assert probe.PROMPT_LENGTHS == (400,)


# --------------------------------------------------------------------------
# B438 - the language debt of my own making
# --------------------------------------------------------------------------

def test_the_files_i_kept_touching_have_english_comments() -> None:
    """The rule says a file that is substantially changed goes over in
    the same turn. Four files were edited release after release and the
    Dutch comments stayed; the guard only watched names, so nothing went
    red."""
    import re
    from pathlib import Path

    import modules

    root = Path(modules.__file__).resolve().parent
    dutch = re.compile(
        r"\b(de|het|een|niet|geen|voor|naar|wordt|zijn|dus|maar|dat|die|"
        r"deze|eerst|nog|weer|zodat|omdat|bij|van|met|aan|uit|per|alleen|"
        r"altijd|nooit|welke|hoe|regel|regels|woord|woorden|gebruiker|knop|"
        r"draai|plek|sleutel|tekst|stap|bestand|map|venster|balk)\b",
        re.IGNORECASE)
    for name in ("pipeline.py", "gui.py", "dependencies.py",
                 "model_register.py", "timing_checks.py",
                 # B446: the files v0.138.0 went over. Every release adds
                 # the ones it substantially touched, so the debt can
                 # only shrink.
                 "config.py", "timing.py", "timing_editor.py",
                 "whisper.py", "whisper_chunks.py", "measure_pool.py",
                 "test_panel.py", "coupling_editor.py", "filesystem.py",
                 "model_orders.py", "versions.py"):
        found = [line.strip()
                 for line in (root / name).read_text(
                     encoding="utf-8").splitlines()
                 if line.strip().startswith("#")
                 and len(dutch.findall(line)) >= 2]
        assert not found, (name, found[:2])
    start = (root.parent / "KaraokeTool.py").read_text(encoding="utf-8")
    assert not [line.strip() for line in start.splitlines()
                if line.strip().startswith("#")
                and len(dutch.findall(line)) >= 2]
