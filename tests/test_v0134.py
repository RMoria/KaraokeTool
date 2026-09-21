"""Tests for v0.134.0: B411 to B416.

Five things the user found in one sitting, and one of them is a lesson
about measuring: on "Lied M" there is more sung than the
lyrics hold, because the last chorus was deliberately left out. A
measurement that calls those seconds "not heard" blames Whisper for a
hole in the text.
"""
from __future__ import annotations

import inspect

import pytest

from modules import cluster, song_text, timing


class _New:
    """A text line as ``karaoke_text.parse_lines`` yields it."""

    def __init__(self, index: int, text: str, crowd: bool = False,
                 block: int = 0) -> None:
        self.index, self.text, self.crowd, self.block = (index, text,
                                                         crowd, block)


def _timed(texts, start: float = 10.0, step: float = 4.0):
    return [timing.timedline_from_text(i, text, start + i * step,
                                       start + i * step + 3.0)
            for i, text in enumerate(texts)]


# --------------------------------------------------------------------------
# B411 - a changed number of lines no longer costs the whole timing
# --------------------------------------------------------------------------

def test_a_chorus_added_at_the_end_costs_only_the_new_lines() -> None:
    old = _timed(["eerste regel", "tweede regel", "derde regel"])
    new = [_New(i, text) for i, text in enumerate(
        ["eerste regel", "tweede regel", "derde regel",
         "eerste regel", "tweede regel"])]
    out = timing.carry_over(old, new)
    assert [line.text for line in out] == [line.text for line in new]
    for before, after in zip(old, out):
        assert after.syllables == before.syllables
    assert out[3].end > out[3].start
    assert out[4].start >= out[3].start


def test_a_line_inserted_in_the_middle_gets_the_room_between_its_neighbours(
) -> None:
    old = _timed(["een", "twee"])
    new = [_New(0, "een"), _New(1, "tussen"), _New(2, "twee")]
    out = timing.carry_over(old, new)
    assert out[0].syllables == old[0].syllables
    assert out[2].syllables == old[1].syllables
    assert out[0].end <= out[1].start
    assert out[1].end <= out[2].start


def test_a_deleted_line_simply_disappears() -> None:
    old = _timed(["een", "twee", "drie"])
    new = [_New(0, "een"), _New(1, "drie")]
    out = timing.carry_over(old, new)
    assert [line.text for line in out] == ["een", "drie"]
    assert out[1].syllables == old[2].syllables


def test_a_rewritten_line_keeps_its_own_place() -> None:
    """The B99/B407 case: same count, other words, same span."""
    old = _timed(["la la la", "tweede regel"])
    new = [_New(0, "la la la la"), _New(1, "tweede regel")]
    out = timing.carry_over(old, new)
    assert out[0].start == pytest.approx(old[0].start)
    assert out[0].end == pytest.approx(old[0].end)
    assert len(out[0].syllables) > len(old[0].syllables)
    assert all(s.end > s.start for s in out[0].syllables)


def test_carrying_over_always_yields_as_many_lines_as_the_new_text() -> None:
    old = _timed(["een", "twee", "drie"])
    for texts in ([], ["een"], ["nieuw"], ["een", "nieuw", "twee", "drie"],
                  ["drie", "twee", "een"]):
        new = [_New(i, text) for i, text in enumerate(texts)]
        assert len(timing.carry_over(old, new)) == len(new)


# --------------------------------------------------------------------------
# B412 - numbers in the lyrics
# --------------------------------------------------------------------------

def test_a_number_stays_in_the_lyrics(tmp_path) -> None:
    """"Another 45 miles" became "Another miles": eleven words missing
    from one song, invisible in every display."""
    path = tmp_path / song_text.LYRICS_FILENAME
    path.write_text("Another 45 miles to go\nBut I would walk 500 miles\n",
                    encoding="utf-8")
    words = [w.text for w in song_text.load_lyrics(path)]
    assert "45" in words and "500" in words
    assert len(words) == 11


def test_dutch_says_the_units_first() -> None:
    """"veertigvijf" is not Dutch, and its phonetic key can therefore
    never match the sung "vijfenveertig"."""
    assert cluster.number_word_forms(45)[0] == "vijfenveertig"
    assert cluster.number_word_forms(21)[0] == "eenentwintig"
    assert cluster.number_word_forms(30)[0] == "dertig"
    assert cluster.number_word_forms(500)[0] == "vijfhonderd"


def test_the_key_of_the_digits_matches_the_key_of_the_words() -> None:
    assert cluster.phonetic_key("45") == cluster.phonetic_key("vijfenveertig")


def test_punctuation_still_goes(tmp_path) -> None:
    path = tmp_path / song_text.LYRICS_FILENAME
    path.write_text("Hello, world! 45.\n", encoding="utf-8")
    assert [w.text for w in song_text.load_lyrics(path)] == [
        "Hello", "world", "45"]


# --------------------------------------------------------------------------
# B413 - one folder per project
# --------------------------------------------------------------------------

def _context(tmp_path):
    from modules import pipeline
    from modules.config import AppConfig
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=AppConfig(),
                               store=ProjectStore(paths.project_file))


def test_the_next_chooser_opens_where_the_last_file_came_from(
        tmp_path) -> None:
    """The user puts everything for a song in one folder first."""
    from modules import pipeline

    context = _context(tmp_path)
    folder = tmp_path / "Lied M"
    folder.mkdir()
    pipeline.set_input_origin(context, "original", folder / "origineel.mp3")
    assert pipeline.input_start_dir(context, "lyrics") == str(folder)


def test_a_kind_that_has_its_own_folder_keeps_it(tmp_path) -> None:
    from modules import pipeline

    context = _context(tmp_path)
    music = tmp_path / "muziek"
    text = tmp_path / "teksten"
    music.mkdir()
    text.mkdir()
    pipeline.set_input_origin(context, "lyrics",
                              text / song_text.LYRICS_FILENAME)
    pipeline.set_input_origin(context, "original", music / "origineel.mp3")
    assert pipeline.input_start_dir(context, "lyrics") == str(text)


def test_a_fresh_project_still_lands_neutrally(tmp_path) -> None:
    """B388: an empty string is not neutral - Qt fills in the last folder
    used anywhere in this run."""
    from pathlib import Path

    from modules import pipeline

    assert pipeline.input_start_dir(_context(tmp_path), "lyrics") == str(
        Path.home())


# --------------------------------------------------------------------------
# B414/B415/B416
# --------------------------------------------------------------------------

def test_an_empty_spot_in_the_text_lane_moves_the_playhead() -> None:
    from modules import timing_editor

    source = inspect.getsource(timing_editor.TimingCanvas.mousePressEvent)
    assert "in_text_lane" in source
    assert "on_a_cell" in source


def test_the_sentence_step_and_the_onset_step_have_their_own_column() -> None:
    lines = _timed(["een zin met woorden"])
    report = timing.timing_report(
        lines, stages={"koppeling": [(10.0, 20.0)], "zinnen": [(10.0, 16.0)],
                       "inzet": [(10.0, 14.0)], "woorden": [(10.0, 13.0)]})
    assert "zinnen|inzet" in report.splitlines()[1]
    assert "|10.00|6.00|4.00|3.00|" in report


def test_the_night_job_takes_more_than_one_song() -> None:
    from modules import test_panel

    assert test_panel.CHUNK_SONGS > 1
    source = inspect.getsource(test_panel.chunk_trial)
    assert "_projects_by_gap" in source
    assert "CHUNK_SONGS" in source


def test_singing_after_the_last_line_is_reported_separately() -> None:
    """Missing lyrics is not missed singing."""
    from modules import test_panel

    source = inspect.getsource(test_panel._chunk_one_song)
    assert "_sung_after_the_text" in source
    assert "heavy_chunk_tail" in source


def test_the_tail_counts_only_what_comes_after_the_last_line() -> None:
    from modules import test_panel
    from unittest.mock import patch

    windows = ((10.0, 20.0), (30.0, 40.0), (50.0, 60.0))
    placed = [{"start": 10.0, "text": "een"}, {"start": 35.0, "text": "twee"}]
    with patch.object(test_panel, "_placed_lines", return_value=placed):
        assert test_panel._sung_after_the_text(None, windows) == \
            pytest.approx(15.0)


def test_without_placed_lines_the_tail_is_zero() -> None:
    from modules import test_panel
    from unittest.mock import patch

    with patch.object(test_panel, "_placed_lines", return_value=()):
        assert test_panel._sung_after_the_text(None, ((0.0, 10.0),)) == 0.0
