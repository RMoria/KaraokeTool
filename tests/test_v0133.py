"""Tests for v0.133.0: B405 to B410.

The theme of this release is one the user found by hand: the timing
threw away answers it had already computed. On one song the sentence
coupling had seven lines right to within a hundredth of a second, the
timing that came out of it was more than a second short on every one of
those seven, and the words that no longer fitted were stacked on top of
each other at the end of the line with length zero. Stretching such a
line in the editor did not help - and stretching moved the wrong edge
too.
"""
from __future__ import annotations

import json

import pytest

from modules import timing


# --------------------------------------------------------------------------
# B405 - stretching moves the edge under the mouse, and only that one
# --------------------------------------------------------------------------

def test_stretching_right_keeps_the_start_where_it_is() -> None:
    """The report: 'I stretch a word to the right, there is a word, and
    then it grows on the LEFT.'"""
    from modules.timing_editor import _inside

    start, end = _inside((10.0, 14.0), low=0.0, high=12.0, anchor="rechts")
    assert start == 10.0
    assert end == 12.0


def test_stretching_left_keeps_the_end_where_it_is() -> None:
    from modules.timing_editor import _inside

    start, end = _inside((6.0, 14.0), low=8.0, high=100.0, anchor="links")
    assert start == 8.0
    assert end == 14.0


def test_moving_still_slides_against_the_neighbour() -> None:
    """Sliding is right for moving; that is what the anchor separates."""
    from modules.timing_editor import _inside

    start, end = _inside((10.0, 14.0), low=0.0, high=12.0,
                         anchor="verplaats")
    assert (start, end) == (8.0, 12.0)


def test_a_stretch_without_room_does_not_move_at_all() -> None:
    """Refusing beats jumping: the old code put the slot at ``low``."""
    from modules.timing_editor import _inside

    span = (10.0, 11.0)
    assert _inside(span, low=9.9, high=10.05, anchor="rechts") == span


# --------------------------------------------------------------------------
# B406 - no syllable without a moment
# --------------------------------------------------------------------------

def test_syllables_that_do_not_fit_are_compressed_not_flattened() -> None:
    raw = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)]
    spans = timing._sanitize_spans(raw, 10.0, 11.0)
    assert len(spans) == 4
    assert all(e - s > 0.0 for s, e in spans)
    assert spans[0][0] == pytest.approx(10.0)
    assert spans[-1][1] == pytest.approx(11.0)


def test_the_end_of_a_line_no_longer_becomes_a_heap() -> None:
    """The measured case: everything past the ceiling became (high, high)."""
    raw = [(50.0, 51.0), (51.0, 52.0), (52.0, 60.0), (60.0, 61.0),
           (61.0, 62.0)]
    spans = timing._sanitize_spans(raw, 50.0, 54.0)
    assert all(e - s >= 0.02 for s, e in spans)
    assert len({round(s, 3) for s, _ in spans}) == len(spans)


def test_with_almost_no_room_everyone_still_gets_a_turn() -> None:
    spans = timing._sanitize_spans([(0.0, 1.0)] * 5, 0.0, 0.01)
    assert len(spans) == 5
    assert all(e >= s for s, e in spans)


def test_a_flattened_line_is_repaired_on_the_way_in() -> None:
    """B406: stretching cannot repair it - zero times any factor is zero."""
    line = {"syllables": [
        {"text": "a", "start": 1.0, "end": 2.0},
        {"text": "b", "start": 2.0, "end": 2.0},
        {"text": "c", "start": 2.0, "end": 2.0},
        {"text": "d", "start": 2.0, "end": 2.0}]}
    assert timing.spread_flattened([line]) == 1
    syllables = line["syllables"]
    assert syllables[0]["start"] == 1.0
    assert syllables[-1]["end"] == 2.0
    assert all(s["end"] > s["start"] for s in syllables)


def test_a_healthy_line_is_left_alone() -> None:
    line = {"syllables": [{"text": "a", "start": 1.0, "end": 1.5},
                          {"text": "b", "start": 1.5, "end": 2.0}]}
    before = json.dumps(line)
    assert timing.spread_flattened([line]) == 0
    assert json.dumps(line) == before


# --------------------------------------------------------------------------
# B408 - which step shortens the line
# --------------------------------------------------------------------------

def _line(text: str, start: float, end: float):
    return timing.timedline_from_text(0, text, start, end)


def test_the_report_puts_the_stages_beside_each_other() -> None:
    lines = [_line("een zin met woorden", 10.0, 11.0)]
    report = timing.timing_report(
        lines, stages={"koppeling": [(10.0, 14.0)],
                       "zinnen": [(10.0, 13.5)],
                       "inzet": [(10.0, 13.0)],
                       "woorden": [(10.0, 11.0)]})
    header = report.splitlines()[1]
    assert header == ("idx|start|end|span|koppeling|zinnen|inzet|woorden"
                      "|nsyl|kwal|flags")
    assert "|4.00|3.50|3.00|1.00|" in report


def test_a_line_that_loses_a_second_is_flagged() -> None:
    lines = [_line("een zin met woorden", 10.0, 11.0)]
    report = timing.timing_report(lines, stages={"koppeling": [(10.0, 14.0)]})
    assert "KRIMP" in report


def test_without_stages_the_old_columns_stay() -> None:
    """The diagnostics are read by hand; do not move a column for nothing."""
    lines = [_line("een zin met woorden", 10.0, 11.0)]
    report = timing.timing_report(lines)
    assert report.splitlines()[1] == "idx|start|end|span|nsyl|kwal|flags"
    assert "KRIMP" not in report


# --------------------------------------------------------------------------
# B407 - the karaoke text edited in Notepad no longer wipes the timing
# --------------------------------------------------------------------------

def _context(tmp_path):
    from modules import pipeline
    from modules.config import AppConfig
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    paths.cache_dir.mkdir(parents=True, exist_ok=True)
    return pipeline.AppContext(paths=paths, config=AppConfig(),
                               store=ProjectStore(paths.project_file))


def _timing_project(tmp_path, text: str):
    """A project with a karaoke text and a hand-made timing beside it."""
    from modules import pipeline

    context = _context(tmp_path)
    karaoke = context.paths.input_dir / "karaoketekst.txt"
    karaoke.write_text(text, encoding="utf-8")
    pipeline.remember_sources(context)

    lines = [timing.timedline_from_text(i, line, 10.0 + i * 4, 13.0 + i * 4)
             for i, line in enumerate(text.strip().splitlines())]
    timing.save_timing(lines, context.paths.timing_file, offset=0.0,
                       project="Proef", versie="0.133.0")
    context.store.set_step("timing", {"lines": len(lines)})
    return context, karaoke


def test_a_text_change_keeps_the_hand_made_timing(tmp_path) -> None:
    """The afternoon that was lost: editing karaoketekst.txt in Notepad
    removed timing.json without a question being asked, while choosing
    the same file through the dialog has kept it since B99."""
    from modules import pipeline

    context, karaoke = _timing_project(tmp_path, "la la la\ntweede regel\n")
    karaoke.write_text("la la la la\ntweede regel\n", encoding="utf-8")

    assert pipeline.sync_input_changes(context) == ("input:karaoke_text",)
    assert context.paths.timing_file.exists()
    kept = list(timing.load_timing(context.paths.timing_file))
    assert [line.text for line in kept] == ["la la la la", "tweede regel"]


def test_the_span_of_a_changed_line_stays_put(tmp_path) -> None:
    """Only the division within the line changes; where the sentence lies
    is exactly the handwork that must not be thrown away."""
    from modules import pipeline

    context, karaoke = _timing_project(tmp_path, "la la la\ntweede regel\n")
    before = list(timing.load_timing(context.paths.timing_file))
    karaoke.write_text("la la la la\ntweede regel\n", encoding="utf-8")
    pipeline.sync_input_changes(context)
    after = list(timing.load_timing(context.paths.timing_file))

    for old, new in zip(before, after):
        assert new.start == pytest.approx(old.start)
        assert new.end == pytest.approx(old.end)
    assert len(after[0].syllables) > len(before[0].syllables)
    assert all(s.end > s.start for s in after[0].syllables)


def test_an_untouched_line_is_not_touched(tmp_path) -> None:
    from modules import pipeline

    context, karaoke = _timing_project(tmp_path, "la la la\ntweede regel\n")
    before = list(timing.load_timing(context.paths.timing_file))
    karaoke.write_text("la la la la\ntweede regel\n", encoding="utf-8")
    pipeline.sync_input_changes(context)
    after = list(timing.load_timing(context.paths.timing_file))
    assert after[1].syllables == before[1].syllables


def test_another_number_of_lines_keeps_what_did_not_change(tmp_path) -> None:
    """B411: adding a chorus costs the new lines and nothing more."""
    from modules import pipeline

    context, karaoke = _timing_project(tmp_path, "la la la\ntweede regel\n")
    before = list(timing.load_timing(context.paths.timing_file))
    karaoke.write_text("la la la\ntweede regel\nderde regel\n",
                       encoding="utf-8")
    pipeline.sync_input_changes(context)

    after = list(timing.load_timing(context.paths.timing_file))
    assert [line.text for line in after] == ["la la la", "tweede regel",
                                             "derde regel"]
    for old, new in zip(before, after):
        assert new.syllables == old.syllables
    assert after[2].end > after[2].start


def test_the_derived_steps_do_go(tmp_path) -> None:
    """Rescuing the handwork is not the same as pretending nothing
    happened: the coupling is based on the old text and has to go."""
    from modules import pipeline

    context, karaoke = _timing_project(tmp_path, "la la la\ntweede regel\n")
    context.store.set_step("coupling", {"mapping": {}})
    karaoke.write_text("la la la la\ntweede regel\n", encoding="utf-8")
    pipeline.sync_input_changes(context)
    assert context.store.get_step("coupling") is None


# --------------------------------------------------------------------------
# B409/B410 - the panel: what you see and how hard the machine works
# --------------------------------------------------------------------------

def test_the_measurement_no_longer_runs_over_two_threads() -> None:
    """1.5.11b walks 240 rounds. Over threads that is one core of the
    twelve, and the user asked about that more than once."""
    import inspect

    from modules import test_panel

    source = inspect.getsource(test_panel._measure)
    assert "measure_pool.measure_rows" in source
    assert "across_projects" not in source


def test_a_chosen_model_is_flipped_and_not_set_to_off() -> None:
    """A model that is OFF takes part by being switched ON; the state map
    must therefore flip and not force a value.

    B439: the flipping moved to ``_states_with``, so the trial and the
    search cannot disagree about what "this variant" means. ``_measure``
    goes through it, and so does the big trial.
    """
    import inspect

    from modules import test_panel

    source = inspect.getsource(test_panel._states_with)
    assert "not states[code]" in source
    assert "_states_with(chosen)" in inspect.getsource(test_panel._measure)


def test_the_held_back_songs_can_actually_be_measured() -> None:
    import inspect

    from modules import test_panel

    source = inspect.getsource(test_panel.search_trial)
    assert "_measurable_projects(context)" in source
    assert "all_songs[-_HELD_BACK:]" not in source


def test_the_chunk_trial_spreads_its_runs() -> None:
    import inspect

    from modules import test_panel

    source = (inspect.getsource(test_panel.chunk_trial)
              + inspect.getsource(test_panel._chunk_one_song))
    assert "whisper_workers" in source
    assert "across_projects" in source


def test_the_merge_starts_from_the_best_run() -> None:
    """Merging into the worst run threw away seven seconds of coverage."""
    import inspect

    from modules import test_panel

    source = (inspect.getsource(test_panel.chunk_trial)
              + inspect.getsource(test_panel._chunk_one_song))
    # B420: still the best run, but since that bug report "best" also
    # weighs whether what was heard occurs in the lyrics.
    assert "min(clean, key=unheard)" in source
    assert "purity(" in source


def test_coverage_counts_words_and_not_segment_edges() -> None:
    """A long VAD segment lies across the gap without a word in it."""
    import importlib.util
    from pathlib import Path

    import modules

    root = Path(modules.__file__).resolve().parents[1]
    path = root / "tools" / "whisper_probe.py"
    spec = importlib.util.spec_from_file_location("probe_test", path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    bracket = [{"start": 130.0, "end": 165.0, "text": "ver weg",
                "words": [{"text": "ver", "start": 130.0, "end": 130.4},
                          {"text": "weg", "start": 164.0, "end": 164.5}]}]
    assert probe.coverage(bracket, (134.0, 163.0)) == pytest.approx(0.0)
    assert probe.words_within(bracket, (134.0, 163.0)) == 0

    real = [{"start": 134.0, "end": 140.0, "text": "wel gezongen",
             "words": [{"text": "wel", "start": 135.0, "end": 136.0},
                       {"text": "gezongen", "start": 136.0, "end": 138.0}]}]
    assert probe.coverage(real, (134.0, 163.0)) == pytest.approx(3.0)
    assert probe.words_within(real, (134.0, 163.0)) == 2


