"""Tests for v0.125.0: B389 measured, B392 built, B388 repaired.

B389 is the one where measuring changed the answer. The user's
observation was that timing problems "shift along": when a line gets
pushed and its end runs into the start of the next, there should be a
fight on weight with the newer line getting a slight advantage. The
observation is right and the proposed mechanism is not, and it is worth
writing down which is which.

Collisions do not happen. Over thirteen projects with hand-corrected
timing there is exactly ONE line in 643 whose start falls before its
predecessor's end - ``sanitize_timing`` already prevents overlap. A fight
on weight at a collision boundary would therefore fire almost never.

But the errors DO cascade, and hard. 158 of those 643 lines (24.6%) land
more than a second off, and they arrive in runs: 38 runs, 4.16 lines on
average, the longest 39 consecutive lines out of a song of 64. Split by
whether a line has its own anchor the picture is unambiguous: 17% of
anchored lines are more than a second off against 75% of the anchorless
ones. So what shifts along is not a collision pushing its neighbour - it
is a whole stretch without anchors drifting together.

Which is exactly what B392 addresses, and B336 already did for the tail:
where the transcription is silent, the vocal stem is not. The hole in the
middle of the song was the one place still getting a straight line drawn
through it.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import model_register, pipeline  # noqa: E402
from modules import timing as timing_module  # noqa: E402


# --------------------------------------------------------------------------
# B392 - a hole in the middle gets the singing, not a straight line
# --------------------------------------------------------------------------

def test_a_run_that_matches_the_windows_is_placed_on_them() -> None:
    windows = ((10.0, 12.0), (14.0, 16.0), (18.0, 20.0))
    assert timing_module.windows_between(3, windows, 9.0, 21.0) == \
        [10.0, 14.0, 18.0]


def test_windows_outside_the_hole_do_not_count() -> None:
    """Only what lies BETWEEN the two anchors may fill the hole."""
    windows = ((2.0, 4.0), (10.0, 12.0), (14.0, 16.0), (30.0, 32.0))
    assert timing_module.windows_between(2, windows, 9.0, 21.0) == \
        [10.0, 14.0]


def test_a_run_the_windows_do_not_explain_is_refused() -> None:
    """The same refusal as B336, and for the same reason: a wrong window
    is worse than a straight line, because it looks measured."""
    windows = ((10.0, 12.0), (14.0, 16.0))
    assert timing_module.windows_between(3, windows, 9.0, 21.0) is None
    assert timing_module.windows_between(1, windows, 9.0, 21.0) is None


def test_without_windows_nothing_changes() -> None:
    assert timing_module.windows_between(2, (), 0.0, 30.0) is None
    assert timing_module.windows_between(0, ((1.0, 2.0),), 0.0, 3.0) is None


def test_the_interpolation_falls_back_to_the_straight_line() -> None:
    """No windows: exactly the old behaviour, evenly spread."""
    spans = [(0.0, 2.0), (None, None), (None, None), (12.0, 14.0)]
    filled = timing_module.interpolate_spans(spans)
    step = (12.0 - 2.0) / 2
    assert filled[1][0] == pytest.approx(2.0)
    assert filled[2][0] == pytest.approx(2.0 + step)


def test_the_interpolation_uses_the_windows_when_they_fit() -> None:
    """The whole point: the two orphan lines land on measured singing
    instead of at one third and two thirds of the hole."""
    spans = [(0.0, 2.0), (None, None), (None, None), (12.0, 14.0)]
    windows = ((0.0, 2.0), (4.5, 6.0), (9.0, 10.5), (12.0, 14.0))
    filled = timing_module.interpolate_spans(spans, windows)
    assert filled[1][0] == pytest.approx(4.5)
    assert filled[2][0] == pytest.approx(9.0)
    assert filled[0] == (0.0, 2.0) and filled[3] == (12.0, 14.0)


def test_the_pipeline_hands_the_windows_over() -> None:
    import inspect

    source = inspect.getsource(pipeline)
    where = source.index("interpolate_spans(raw")
    assert "_vocal_windows(context)" in source[where:where + 120]


def test_the_tail_keeps_its_own_rule() -> None:
    """B336 does the tail and does it differently - it divides a window
    into phrases. B392 must not quietly take that over."""
    assert timing_module.tail_over_windows is not None
    assert timing_module.windows_between is not timing_module.tail_over_windows


def test_it_is_a_switchable_model_and_it_is_on() -> None:
    """Measured on three projects: -0.37 s on Lied_P and
    unchanged on the other two, so weighted 0.17 s better and never
    worse. On with the measurement as the reason."""
    model = model_register.by_code("B392")
    assert model is not None
    assert model.default_on
    assert model.level == "zin"
    assert model.reason


# --------------------------------------------------------------------------
# B388 - a new project must not open in the previous one's folder
# --------------------------------------------------------------------------

def _context(tmp_path, name="Vers"):
    from dataclasses import replace

    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=name)
    ensure_directories(paths)
    config = default_config()
    config = replace(config, song=replace(config.song, title=name))
    return pipeline.AppContext(paths=paths, config=config,
                               store=ProjectStore(paths.project_file))


def test_a_fresh_project_never_yields_an_empty_start_folder(tmp_path) -> None:
    """An empty string is not neutral: handed one, Qt fills in the last
    folder used anywhere in this run - which is how a new project ended
    up opening in the previous project's music folder."""
    context = _context(tmp_path)
    assert pipeline.input_start_dir(context, "original") != ""


def test_a_remembered_folder_still_wins(tmp_path) -> None:
    context = _context(tmp_path)
    music = tmp_path / "Muziek"
    music.mkdir()
    pipeline.set_input_origin(context, "original", music / "lied.mp3")
    assert pipeline.input_start_dir(context, "original") == str(music)


def test_a_folder_that_is_gone_falls_back(tmp_path) -> None:
    context = _context(tmp_path)
    pipeline.set_input_origin(context, "original",
                              tmp_path / "weg" / "lied.mp3")
    start = pipeline.input_start_dir(context, "original")
    assert start != "" and "weg" not in start


def test_the_memory_is_per_project(tmp_path) -> None:
    """The heart of B388: what the previous project remembers may not
    leak into a new one."""
    first = _context(tmp_path, "Eerste")
    music = tmp_path / "Muziek"
    music.mkdir()
    pipeline.set_input_origin(first, "original", music / "lied.mp3")
    second = _context(tmp_path, "Tweede")
    assert pipeline.input_start_dir(second, "original") != str(music)
