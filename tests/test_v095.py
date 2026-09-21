"""Tests for v0.95 (B288 up to and including B302).

A clean-up and correctness round, born out of a full review of the code
base on logic, dead code and translatability. Not one of the bugs below
was reported by the user: they came out of the review and every one of
them was reproduced with a concrete failing scenario before it was
fixed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import align, config, karaoke, pipeline, timing  # noqa: E402
from modules.config import default_config  # noqa: E402
from modules.filesystem import (ProjectPaths, ProjectStore,  # noqa: E402
                                ensure_directories)
from modules.pipeline import AppContext  # noqa: E402
from modules.song_text import LyricWord, align_lyrics  # noqa: E402
from modules.whisper import Segment, Word  # noqa: E402


def _context(tmp_path: Path) -> AppContext:
    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    return AppContext(config=default_config(), paths=paths,
                      store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B288 - priority_lines compared a word index with a line number
# --------------------------------------------------------------------------

def _viva_segments() -> tuple:
    """Transcription in which the filler word "oh" was heard as "hoa".

    similarity("oh", "hoa") = 0.5: under the normal filler threshold
    (0.6), but above the priority threshold (0.5). That way the
    coupling shows whether the priority was applied or not.
    """
    return (
        Segment(0, "niets veranderd hoa het voelt", 0.0, 5.0, (
            Word("niets", 0.0, 0.5, 0.9),
            Word("veranderd", 0.6, 1.2, 0.9),
            Word("hoa", 1.5, 1.8, 0.9),
            Word("het", 2.0, 2.4, 0.9),
            Word("voelt", 2.5, 3.0, 0.9),
        )),
    )


def test_priority_lines_works_on_the_line_number_not_the_word_index(
) -> None:
    """B288: every word sits on line 5. Give line 5 as a priority line
    and the gentler threshold MUST apply, so that "oh" is coupled after
    all. Before the fix ``i in priority`` was tested - with ``i`` the
    word index - and nothing happened."""
    lyrics = tuple(LyricWord(i, t, 5) for i, t in enumerate(
        ["niets", "veranderd", "oh", "het", "voelt"]))
    aligned = align_lyrics(lyrics, _viva_segments(), skip_filler=True,
                           priority_lines=frozenset({5}))
    oh = aligned[2]
    assert oh.matched_text == "hoa", \
        "the priority line did not lower the threshold"


def test_priority_lines_does_not_touch_the_wrong_words() -> None:
    """B288, the other way round: line number 2 is NOT a line of these
    words (they all sit on line 5). Before the fix that coupled the
    third word (index 2) by coincidence, purely because the number
    matched."""
    lyrics = tuple(LyricWord(i, t, 5) for i, t in enumerate(
        ["niets", "veranderd", "oh", "het", "voelt"]))
    aligned = align_lyrics(lyrics, _viva_segments(), skip_filler=True,
                           priority_lines=frozenset({2}))
    assert aligned[2].matched_text is None, \
        "the word index was still used as a line number"


# --------------------------------------------------------------------------
# B289 - lang="nl" in a boolean field
# --------------------------------------------------------------------------

def test_timedline_from_text_does_not_set_lang_to_a_string() -> None:
    """B289: ``Syllable.lang`` means "long held note" and drives the
    underlining in the render. It read ``lang="nl"`` (confusion with the
    language parameter); a non-empty string is truthy, so EVERY syllable
    was underlined."""
    line = timing.timedline_from_text(0, "hallo wereld", 0.0, 2.0)
    assert [s.held for s in line.syllables] == [False, False, False, False]
    assert not any(s.held for s in line.syllables)


# --------------------------------------------------------------------------
# B290 - distribute_over_windows crashed on more windows than words
# --------------------------------------------------------------------------

@pytest.mark.parametrize("n_words,n_windows",
                         [(2, 4), (2, 9), (3, 5), (4, 6), (2, 12)])
def test_distribute_over_windows_does_not_crash_on_many_windows(
    n_words: int, n_windows: int,
) -> None:
    """B290: as soon as a line held ``n_words + 2`` or more sung
    windows, the clamp ran past the last word and ``word_spans[wi]``
    raised an IndexError. That was swallowed by the safety net in
    ``pipeline._apply_energy_word_timing``, which silently dropped the
    energy word timing of the WHOLE song."""
    text_value = " ".join(f"woord{i}" for i in range(n_words))
    line = timing.timedline_from_text(0, text_value, 0.0, 20.0)
    usable_windows = [(i * 1.5, i * 1.5 + 1.0) for i in range(n_windows)]
    out = timing.distribute_over_windows(line, usable_windows)
    assert len(out.syllables) == len(line.syllables)


def test_distribute_over_windows_keeps_the_order_and_the_syllables(
) -> None:
    """B290: after merging the surplus windows the syllables still have
    to be complete, ascending and non-overlapping."""
    line = timing.timedline_from_text(0, "een twee drie", 0.0, 20.0)
    usable_windows = [(i * 2.0, i * 2.0 + 1.0) for i in range(8)]
    out = timing.distribute_over_windows(line, usable_windows)
    assert len(out.syllables) == len(line.syllables)
    times = [(s.start, s.end) for s in out.syllables]
    assert all(a <= b for a, b in times)
    assert all(times[i][1] <= times[i + 1][0] + 1e-6
               for i in range(len(times) - 1))


def test_distribute_over_windows_keeps_the_biggest_pauses() -> None:
    """B290: surplus windows are merged on the SMALLEST pause between
    them, so that exactly the clear pauses (what B234 is about) stay
    standing and the outer span of the line stays intact."""
    line = timing.timedline_from_text(0, "een twee", 0.0, 20.0)
    # Two windows close together, then a wide gap, then one more.
    usable_windows = [(0.0, 1.0), (1.1, 2.0), (10.0, 11.0)]
    out = timing.distribute_over_windows(line, usable_windows)
    assert out.syllables[0].start == pytest.approx(0.0, abs=0.05)
    assert out.syllables[-1].end == pytest.approx(11.0, abs=0.05)


# --------------------------------------------------------------------------
# B291 - block and disabled were lost on a text change
# --------------------------------------------------------------------------

def test_sync_timing_keeps_block_and_disabled(tmp_path: Path) -> None:
    """B291: when a corrected karaoke text was carried through,
    ``block`` and ``disabled`` were not passed to the new
    ``TimedLine``, so they fell back to 0/False. A line the user had
    switched off (B180) was therefore simply back in the video after a
    typo correction."""
    from modules.karaoke_text import TextLine

    context = _context(tmp_path)
    timed = (
        timing.TimedLine(
            index=0, text="eerste regel", crowd=False, block=0,
            syllables=(timing.Syllable("eerste", 0.0, 1.0),
                       timing.Syllable(" regel", 1.0, 2.0))),
        timing.TimedLine(
            index=1, text="tweede regel", crowd=False, block=1,
            disabled=True, quality="word",
            syllables=(timing.Syllable("tweede", 2.0, 3.0),
                       timing.Syllable(" regel", 3.0, 4.0))),
    )
    timing.save_timing(timed, context.paths.timing_file)

    old = (TextLine(index=0, text="eerste regel", crowd=False, block=0),
           TextLine(index=1, text="tweede regel", crowd=False, block=1))
    new = (TextLine(index=0, text="eerste regel", crowd=False, block=0),
             TextLine(index=1, text="tweede regels", crowd=False, block=1))

    updated, _message = pipeline.sync_timing_with_text_change(
        context, old, new)
    assert updated is True

    after = timing.load_timing(context.paths.timing_file)
    assert after[1].text == "tweede regels"        # the change came through
    assert after[1].disabled is True, "disabled was lost"
    assert after[1].block == 1, "block was lost"
    assert after[1].quality == "word"          # existed already, stays
    assert after[0].block == 0                     # untouched line intact


# --------------------------------------------------------------------------
# B292 - loose ends from v0.93/v0.94
# --------------------------------------------------------------------------

def test_word_in_lyrics_has_no_dead_floor_parameter() -> None:
    """B292: ``_word_in_lyrics`` had a ``floor`` parameter that was
    never called with anything but the default, while the docstring
    suggested the wide B285 check used it. That check goes through
    ``_best_lyrics_match``; whoever went by the docstring tuned the
    wrong thing."""
    import inspect

    params = inspect.signature(pipeline._word_in_lyrics).parameters
    assert "floor" not in params
    assert list(params) == ["word", "lyric_keys"]


def test_the_dead_restore_interval_helpers_are_gone() -> None:
    """B292: ``restore_intervals_to_dicts``/``_from_dicts`` (B282) were
    called nowhere AND described a different format from what is really
    stored (``restore_fragments`` keeps triples)."""
    assert not hasattr(karaoke, "restore_intervals_to_dicts")
    assert not hasattr(karaoke, "restore_intervals_from_dicts")


# --------------------------------------------------------------------------
# B301 - unchecked threshold and a misleading merged label
# --------------------------------------------------------------------------

def test_align_min_confidence_is_checked(tmp_path: Path) -> None:
    """B301: ``align.min_confidence`` was the only threshold without a
    check, while 0.0 makes the weighted averaging in
    ``align._build_regions`` divide by zero."""
    import json
    from dataclasses import replace

    cfg = default_config()
    broken = replace(cfg, align=replace(cfg.align, min_confidence=0.0))
    with pytest.raises(config.ConfigError, match="align.min_confidence"):
        config._validate(broken)

    # And through the real loading path (config.json on disk).
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"align": {"min_confidence": 0.0}}),
                   encoding="utf-8")
    with pytest.raises(config.ConfigError, match="align.min_confidence"):
        config.load_config(path)


def test_build_regions_survives_zero_weights() -> None:
    """B301: this is exactly the path the config check above now closes
    off, but ``_build_regions`` can also be called on its own. With
    ``min_confidence=0.0`` windows with confidence 0.0 slip through the
    filter and ended up at ``np.average(..., weights=...)`` - which
    divides by the sum of the weights and raised a ZeroDivisionError.
    It now falls back on the unweighted mean."""
    from dataclasses import replace

    settings = replace(default_config().align, min_confidence=0.0)
    # Both offsets within the tolerance (40 ms), so that they form one
    # group and therefore go through the weighted averaging together.
    usable_windows = [align.WindowOffset(start=0.0, end=1.0, offset=0.10,
                                   confidence=0.0),
                align.WindowOffset(start=1.0, end=2.0, offset=0.12,
                                   confidence=0.0)]
    regions = align._build_regions(usable_windows, duration=2.0, fallback_offset=0.0,
                                  fallback_confidence=0.0,
                                  settings=settings)
    assert regions, "no regions produced"
    # Unweighted mean of 0.10 and 0.12; before the fix a
    # ZeroDivisionError.
    assert regions[0].offset == pytest.approx(0.11)


def test_merge_intervals_names_every_sound_it_merged() -> None:
    """B301: a merged damping span kept only the label of the first
    fragment, while in reality it damped several clusters - misleading
    when ticking them on and off in the damping editor. The damping
    itself becomes the stronger of the two."""
    merged = karaoke.merge_intervals((
        karaoke.DampingInterval(label="oe", start=0.0, end=1.0,
                                gain_db=-20.0),
        karaoke.DampingInterval(label="woo", start=1.0, end=2.0,
                                gain_db=-30.0),
    ))
    assert len(merged) == 1
    assert merged[0].label == "oe+woo"
    assert merged[0].gain_db == -30.0          # strongest damping wins
    assert merged[0].start == 0.0 and merged[0].end == 2.0


def test_merge_intervals_does_not_repeat_the_same_label() -> None:
    """B301: three adjacent fragments of the same sound give "oe", not
    "oe+oe+oe"."""
    merged = karaoke.merge_intervals(tuple(
        karaoke.DampingInterval(label="oe", start=float(i), end=float(i) + 1,
                                gain_db=-25.0)
        for i in range(3)))
    assert len(merged) == 1
    assert merged[0].label == "oe"


def test_merge_intervals_leaves_separate_fragments_alone() -> None:
    """B301: fragments that do not overlap stay unchanged - the label
    and the damping of each on its own."""
    merged = karaoke.merge_intervals((
        karaoke.DampingInterval(label="oe", start=0.0, end=1.0,
                                gain_db=-20.0),
        karaoke.DampingInterval(label="woo", start=50.0, end=51.0,
                                gain_db=-30.0),
    ))
    assert [iv.label for iv in merged] == ["oe", "woo"]
    assert [iv.gain_db for iv in merged] == [-20.0, -30.0]


# --------------------------------------------------------------------------
# B293/B295 - dead code and dead translation keys
# --------------------------------------------------------------------------

def test_the_dead_functions_and_constants_are_gone() -> None:
    """B293: cleared out because nothing called them. ``detect_words``
    did exactly the same as ``detect_tracks(parallel=False)`` on top of
    that - two doors into the same step 1 means a change to one of them
    silently passes the other by."""
    from modules import phonetics

    assert not hasattr(phonetics, "_lang_dir_name")
    assert not hasattr(pipeline, "TrackProgressCallback")
    assert not hasattr(pipeline, "detect_words")
    assert hasattr(pipeline, "detect_tracks")       # the door that is left


def test_smooth_regions_has_no_dead_parameter() -> None:
    """B293: ``fallback_offset`` was used nowhere in the body since the
    move to trend detection (B249)."""
    import inspect

    params = inspect.signature(align._smooth_regions).parameters
    assert list(params) == ["regions"]


def test_format_time_stands_in_only_one_place() -> None:
    """B293: ``gui.py`` had a literally identical private copy of
    ``cluster._format_time``. Now there is one public source."""
    from modules import cluster, gui

    assert cluster.format_time(75.25) == "1:15.2"
    assert gui._format_time is cluster.format_time


def test_no_dead_translation_keys_left() -> None:
    """B295: 14 keys were still in both dictionaries but were called
    nowhere any more (among them the orphans of a dialogue that an error
    message replaced)."""
    from modules.translations import TRANSLATIONS

    for gone in ("options_group", "analyse_on", "analyse_hint",
                 "render_audio_demucs", "analyse_toggle_log",
                 "track_required_body", "alignment_remade", "mark_ok",
                 "mark_missing", "video_input_incomplete_title",
                 "video_input_incomplete_body", "video_input_complete_title",
                 "video_input_complete_body", "open"):
        assert gone not in TRANSLATIONS["nl"], f"{gone} still in nl"
        assert gone not in TRANSLATIONS["en"], f"{gone} still in en"


# --------------------------------------------------------------------------
# B296/B297/B298 - translatability and correct step references
# --------------------------------------------------------------------------

def test_the_pipeline_error_messages_are_translatable(tmp_path: Path) -> None:
    """B296: the error messages out of the pipeline end up in a
    QMessageBox through ``_on_failed``; they were all hard-coded in
    Dutch. They now follow the language that is set."""
    from modules import translations
    from modules.pipeline import PipelineError

    context = _context(tmp_path)
    try:
        translations.set_language("en")
        with pytest.raises(PipelineError) as error:
            pipeline.load_segments(context, "original")
        assert "No transcription" in str(error.value)
        # B325: the button name comes from the same translation key as
        # the button itself.
        assert translations.TRANSLATIONS["en"]["step_detect"] \
            in str(error.value)

        translations.set_language("nl")
        with pytest.raises(PipelineError) as error:
            pipeline.load_segments(context, "original")
        assert "Geen transcriptie" in str(error.value)
    finally:
        translations.set_language("nl")


def test_no_hard_coded_pipeline_errors_left() -> None:
    """B296: a regression guard - every ``raise PipelineError`` goes
    through ``t()`` or passes an existing exception on, not a literal
    text."""
    import re

    source = (Path(__file__).parent.parent / "modules" / "pipeline.py").read_text(
        encoding="utf-8")
    literal = re.findall(r'raise PipelineError\("', source)
    assert not literal, f"{len(literal)} hard-coded error message(s)"


def test_the_html_report_follows_the_language() -> None:
    """B296: the HTML cluster report was hard-coded Dutch from top to
    bottom, the title and the headings included."""
    from modules import cluster, translations
    from modules.whisper import Segment, Word

    c = cluster.Cluster(id=1, label="oeh", members=(("oeh", 3),),
                        occurrences=(cluster.Occurrence("oeh", 1.5, 1.9, 0.9,
                                                       0),),
                        segments=(0,), frequency=5, avg_confidence=0.88,
                        avg_duration_s=0.4, avg_pause_s=2.1)
    segs = (Segment(0, "oeh oe", 0.5, 1.5, (Word("oeh", 0.5, 0.9, 0.9),)),)
    try:
        translations.set_language("en")
        html = cluster._render_html((c,), segs)
        assert "<html lang=en>" in html
        assert "Sound clusters" in html
        assert "Avg. duration" in html

        translations.set_language("nl")
        html = cluster._render_html((c,), segs)
        assert "<html lang=nl>" in html
        assert "Klankclusters" in html
    finally:
        translations.set_language("nl")


def test_the_step_numbers_in_texts_match_the_buttons() -> None:
    """B297: texts pointed at "step 2 (Analyse)" and "step 3 (Align)",
    while the buttons are called something else - and a separate Align
    step does not exist any more (it runs by itself).

    B325: the numbering has become <tab>.<button>. and a text no longer
    names the button but its key, so that it cannot fall out of step
    again.
    """
    from modules import translations as translations_module
    from modules.translations import TRANSLATIONS

    for code in ("nl", "en"):
        translations = TRANSLATIONS[code]
        assert translations["step_analyse"].startswith("1.3. ")
        assert "{step_analyse}" in translations["prereq_need_analyse"]
        # Nowhere a reference left to an Align step that does not exist.
        for key, text_value in translations.items():
            assert "Uitlijnen'" not in text_value, key
            assert "stap 2 (Analyse)" not in text_value, key

    # The filled-in text carries the current button name.
    try:
        translations_module.set_language("nl")
        assert "1.3. Analyse" in translations_module.t("prereq_need_analyse")
        translations_module.set_language("en")
        assert "1.3. Analyse" in translations_module.t("prereq_need_analyse")
    finally:
        translations_module.set_language("nl")


def test_no_internal_bug_references_in_visible_texts() -> None:
    """B298: the tooltip of the line switch ended on "(B180)" - an
    internal finding number that says nothing to the user."""
    import re

    from modules.translations import TRANSLATIONS

    for code, translations in TRANSLATIONS.items():
        for key, text_value in translations.items():
            assert not re.search(r"\bB\d{2,3}\b", text_value), \
                f"{code}/{key} holds an internal bug reference: {text_value}"


def test_the_language_keys_stay_in_balance() -> None:
    """The nl and en dictionaries have to keep exactly the same keys,
    also after adding ~45 new ones and striking 14."""
    from modules.translations import TRANSLATIONS

    assert set(TRANSLATIONS["nl"]) == set(TRANSLATIONS["en"])
