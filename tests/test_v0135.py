"""Tests for v0.135.0: B417 to B420.

The hyphen turned out to be the same bug as the 45: a word that exists
in the lyrics AND in the transcription, in a form that can never match.
And repairing that shape shifts the manual word couplings, which count
positions - so the conversion comes first, otherwise this release makes
the problem it is meant to solve bigger.
"""
from __future__ import annotations

import inspect

from modules import song_text


# --------------------------------------------------------------------------
# B418 - a hyphen is a word boundary
# --------------------------------------------------------------------------

def test_a_cluster_of_las_becomes_separate_words() -> None:
    """The user writes them joined because the cluster belongs together
    rhythmically; Whisper writes five separate ``la``s."""
    assert song_text.split_word("La-la-la-la-la,") == ["La", "la", "la",
                                                       "la", "la"]


def test_the_apostrophe_stays_a_word() -> None:
    assert song_text.split_word("I've") == ["I've"]
    assert song_text.split_word("'cos") == ["'cos"]


def test_a_number_survives_the_split() -> None:
    assert song_text.split_word("45.") == ["45"]


def test_punctuation_still_yields_nothing() -> None:
    assert song_text.split_word("—") == []
    assert song_text.split_word("...") == []


def test_the_lyrics_count_the_pieces(tmp_path) -> None:
    path = tmp_path / song_text.LYRICS_FILENAME
    path.write_text("La-la-la, na-na\nwoah-oh\n", encoding="utf-8")
    assert [w.text for w in song_text.load_lyrics(path)] == [
        "La", "la", "la", "na", "na", "woah", "oh"]


def test_a_compound_falls_apart_but_can_still_be_coupled(tmp_path) -> None:
    """"e" + "mail" against "email" is exactly what ``_lyric_pair_sim``
    is for, so splitting does not cost the coupling anything."""
    from modules import song_text as st

    assert st.split_word("e-mail") == ["e", "mail"]
    source = inspect.getsource(st._align_core)
    assert "_lyric_pair_sim" in source


def test_the_old_shape_is_still_reproducible() -> None:
    """The conversion of the pins needs both shapes."""
    text = "La-la-la 45 e-mail"
    assert song_text.words_before_b418(text) == ["La-la-la", "e-mail"]
    assert [p for raw in text.split() for p in song_text.split_word(raw)] == [
        "La", "la", "la", "45", "e", "mail"]


# --------------------------------------------------------------------------
# B417 - the manual couplings move along
# --------------------------------------------------------------------------

def _context(tmp_path, lyrics: str):
    from modules import pipeline
    from modules.config import AppConfig
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    (paths.input_dir / song_text.LYRICS_FILENAME).write_text(
        lyrics, encoding="utf-8")
    return pipeline.AppContext(paths=paths, config=AppConfig(),
                               store=ProjectStore(paths.project_file))


def test_a_pin_after_a_number_moves_along(tmp_path) -> None:
    """The real case: 279 words instead of 268, so everything after the
    first number points one word further."""
    from modules import pipeline

    context = _context(tmp_path, "Another 45 miles to go\n")
    # oude lijst: Another miles to go -> pin 2 = "to"
    pipeline.set_word_pins(context, {2: [7]})
    context.store.set_step("word_coupling", {"pins": {"2": [7]},
                                             "layout": "full"})
    pins = pipeline.migrate_lyric_pins(context)
    words = [w.text for w in song_text.load_lyrics(
        context.paths.input_dir / song_text.LYRICS_FILENAME)]
    assert list(pins) == [3]
    assert words[3] == "to"
    assert pins[3] == [7]


def test_a_pin_before_the_first_number_stays_put(tmp_path) -> None:
    from modules import pipeline

    context = _context(tmp_path, "Another 45 miles to go\n")
    context.store.set_step("word_coupling", {"pins": {"0": [1]}})
    assert list(pipeline.migrate_lyric_pins(context)) == [0]


def test_the_conversion_happens_only_once(tmp_path) -> None:
    from modules import pipeline

    context = _context(tmp_path, "Another 45 miles to go\n")
    context.store.set_step("word_coupling", {"pins": {"2": [7]}})
    first = pipeline.migrate_lyric_pins(context)
    second = pipeline.migrate_lyric_pins(context)
    assert first == second == {3: [7]}


def test_the_transcript_marker_is_not_faked(tmp_path) -> None:
    """Writing the pins back may not claim that the B309 conversion has
    happened; that one is about the OTHER side of the pin."""
    from modules import pipeline

    context = _context(tmp_path, "Another 45 miles to go\n")
    context.store.set_step("word_coupling", {"pins": {"2": [7]}})
    pipeline.migrate_lyric_pins(context)
    step = context.store.get_step("word_coupling")
    assert step["lyrics_layout"] == pipeline._PIN_LYRICS_SPLIT
    assert "layout" not in step


def test_an_existing_transcript_marker_is_kept(tmp_path) -> None:
    from modules import pipeline

    context = _context(tmp_path, "Another 45 miles to go\n")
    context.store.set_step("word_coupling",
                           {"pins": {"2": [7]}, "layout": "full"})
    pipeline.migrate_lyric_pins(context)
    assert context.store.get_step("word_coupling")["layout"] == "full"


def test_a_pin_on_a_word_that_fell_apart_takes_the_first_piece(
        tmp_path) -> None:
    from modules import pipeline

    context = _context(tmp_path, "zing La-la-la mee\n")
    context.store.set_step("word_coupling", {"pins": {"1": [4], "2": [9]}})
    pins = pipeline.migrate_lyric_pins(context)
    words = [w.text for w in song_text.load_lyrics(
        context.paths.input_dir / song_text.LYRICS_FILENAME)]
    assert words == ["zing", "La", "la", "la", "mee"]
    assert pins[1] == [4]          # "La", het eerste stuk
    assert pins[4] == [9]          # "mee" schoof twee plaatsen op


def test_without_lyrics_nothing_falls_over(tmp_path) -> None:
    from modules import pipeline
    from modules.config import AppConfig
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paths = ProjectPaths(root=tmp_path, song="Leeg")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=AppConfig(),
                                  store=ProjectStore(paths.project_file))
    context.store.set_step("word_coupling", {"pins": {"2": [7]}})
    assert pipeline.migrate_lyric_pins(context) == {2: [7]}


# --------------------------------------------------------------------------
# B419 - the model is shared
# --------------------------------------------------------------------------

def test_the_probe_uses_the_model_cache_of_the_app() -> None:
    """Ten pieces meant ten times loading large-v3: 28.9 s fixed cost per
    piece, measured over 35 pieces."""
    from pathlib import Path

    import modules

    source = (Path(modules.__file__).resolve().parents[1] / "tools"
              / "whisper_probe.py").read_text(encoding="utf-8")
    assert "whisper._load_model(settings)" in source
    assert "WhisperModel(settings.model" not in source


# --------------------------------------------------------------------------
# B420 - what was heard has to be in the lyrics
# --------------------------------------------------------------------------

def _words(*texts):
    return [{"text": text, "start": 0.0, "end": 0.1} for text in texts]


def test_the_share_in_the_lyrics_is_counted() -> None:
    from modules import cluster, test_panel

    keys = frozenset(cluster.phonetic_key(w) for w in ("zing", "maar", "mee"))
    assert test_panel.in_the_text(_words("zing", "maar", "mee"), keys) == 100.0
    assert test_panel.in_the_text(_words("zing", "gregereng"), keys) == 50.0
    assert test_panel.in_the_text([], keys) == 0.0
    assert test_panel.in_the_text(_words("zing"), frozenset()) == 0.0


def test_a_spelling_variant_still_counts() -> None:
    """Compared on the sound, the same notion the coupling uses."""
    from modules import cluster, test_panel

    keys = frozenset([cluster.phonetic_key("la")])
    assert test_panel.in_the_text(_words("-la", "La,"), keys) == 100.0


def test_a_looping_run_may_not_become_the_merge_base() -> None:
    from modules import test_panel

    source = inspect.getsource(test_panel._chunk_one_song)
    assert "purity" in source and "_PURITY_SLACK" in source


def test_both_trials_report_the_share() -> None:
    from modules import test_panel

    for name in ("_chunk_one_song",):
        source = inspect.getsource(getattr(test_panel, name))
        assert "in_the_text(" in source, name
        assert "in tekst" in source, name


def test_the_slack_is_not_zero() -> None:
    """Cutting hears MORE; a couple of words outside the lyrics is
    normal, a loop is not a couple."""
    from modules import test_panel

    assert test_panel._PURITY_SLACK > 0
