"""Tests for v0.141.0: B464 to B467.

B464 is the one worth reading. I built a rule on a premise I had not
checked - "Whisper invents plausible sentences, not singing" - and the
measurement said the opposite: a repetition loop is one of the most
common hallucinations there is. The rule exempted exactly that, and half
a second of timing walked out. It is not the reasoning that decides
here, it is the yardstick.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

from modules import cluster, pipeline


def _project(tmp_path, lyrics: str = "", karaoke: str = ""):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    if lyrics:
        (paths.input_dir / "lyrics.txt").write_text(lyrics,
                                                    encoding="utf-8")
    if karaoke:
        (paths.input_dir / "karaoke_text.txt").write_text(karaoke,
                                                          encoding="utf-8")
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B464 - only what the text really chants
# --------------------------------------------------------------------------

def test_the_text_decides_what_counts_as_a_chant(tmp_path) -> None:
    context = _project(
        tmp_path,
        lyrics="ik wil dit wel\nna na na en verder",
        karaoke="la-la-la-la wat een feest\nik wil dit ook")
    keys = pipeline.chanted_keys(context)
    assert cluster.phonetic_key("la") in keys
    assert cluster.phonetic_key("na") in keys
    # "wil" is sung once and stands in the text once.
    assert cluster.phonetic_key("wil") not in keys
    assert cluster.phonetic_key("feest") not in keys


def test_two_in_a_row_is_not_a_chant_yet(tmp_path) -> None:
    """Three, like the shape check itself - two of the same word is an
    ordinary repetition ("heel heel mooi")."""
    context = _project(tmp_path, lyrics="la la wat een feest")
    assert cluster.phonetic_key("la") not in pipeline.chanted_keys(context)


def test_a_chant_only_counts_where_it_stands_next_to_itself(
        tmp_path) -> None:
    """Three "la"s scattered through the song is not a chant."""
    context = _project(tmp_path,
                       lyrics="la een keer\nen dan la\nnog eens la")
    assert cluster.phonetic_key("la") not in pipeline.chanted_keys(context)


def test_either_of_the_two_texts_may_have_it(tmp_path) -> None:
    """The original may sing "na-na-na" where the karaoke text writes
    "la-la-la"; one of the two having it is enough."""
    only_karaoke = _project(tmp_path / "a", karaoke="la-la-la mooi")
    assert cluster.phonetic_key("la") in pipeline.chanted_keys(only_karaoke)
    only_lyrics = _project(tmp_path / "b", lyrics="oe oe oe daar")
    assert cluster.phonetic_key("oe") in pipeline.chanted_keys(only_lyrics)


def test_no_text_no_exemption(tmp_path) -> None:
    """Without a text there is nothing to lean on, and then a repetition
    loop is just a repetition loop."""
    assert pipeline.chanted_keys(_project(tmp_path)) == frozenset()


def test_the_exemption_needs_the_text_and_not_just_the_shape() -> None:
    """That is the whole correction: the shape alone exempted the most
    common hallucination Whisper produces."""
    source = inspect.getsource(pipeline._filter_hallucinations)
    assert "chant = _is_chant(core_words) and any(" in source
    assert "_word_in_lyrics(w, chant_keys) for w in core_words" in source
    # And no "or not chant_keys" escape any more.
    assert "not chant_keys" not in source


def test_both_rounds_use_the_same_condition() -> None:
    for name in ("_filter_hallucinations",
                 "_filter_hallucinations_in_position"):
        source = inspect.getsource(getattr(pipeline, name))
        assert "_is_chant(core_words) and any(" in source, name


def test_the_filter_is_handed_the_chanted_keys() -> None:
    source = inspect.getsource(pipeline._clean_segments_and_alignment)
    assert "chanted = chanted_keys(context)" in source
    assert source.count("extra_keys=chanted") == 2


def test_the_guard_now_knows_the_english_marker() -> None:
    """The code was translated and the guard only looked for the Dutch
    word, so it walked straight past a temporary function that had been
    sitting in pipeline.py for months."""
    import modules

    source = (pathlib.Path(modules.__file__).resolve().parents[1] / "tests"
              / "test_v0111.py").read_text(encoding="utf-8")
    assert "TIJDELIJK|TEMPORARY" in source


# --------------------------------------------------------------------------
# B466 - say what is wrong instead of that something is wrong
# --------------------------------------------------------------------------

def test_a_refusal_names_both_line_counts() -> None:
    """"A different number of lines" says nothing about what to do.
    Lied_O has 55 hand-timed lines against a karaoke text that now
    yields 41: the handwork is older than the text."""
    from modules.translations import TRANSLATIONS

    for language in ("nl", "en"):
        text = TRANSLATIONS[language]["log_auto_rebuild_mismatch"]
        assert text.count("%d") == 2
    source = inspect.getsource(pipeline.rebuild_auto_timing)
    assert "len(hand)," in source


# --------------------------------------------------------------------------
# B467 - one clock
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["_gaps_in", "_chunk_one_song",
                                  "_gain_trial"])
def test_every_stem_measurement_uses_the_originals_own_clock(name) -> None:
    """The word times come from the transcription of the original and
    ``_vocal_windows`` projects onto the karaoke - so this was comparing
    two different clocks. That is how the same run gave 49.2 s in one
    trial and 68.8 s in another."""
    from modules import test_panel

    source = inspect.getsource(getattr(test_panel, name))
    assert "_original_vocal_windows(other)" in source, name
    assert "= pipeline._vocal_windows(other)" not in source, name


def test_the_two_windows_are_still_different_functions() -> None:
    """The karaoke timeline is right for everything that works on the
    karaoke text; this is not a reason to merge them."""
    karaoke = inspect.getsource(pipeline._vocal_windows)
    original = inspect.getsource(pipeline._original_vocal_windows)
    assert "project_time" in karaoke
    assert "project_time" not in original
