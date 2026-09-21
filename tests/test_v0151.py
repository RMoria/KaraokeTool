"""Tests for v0.151.0.

B538 - a song with a second language in it is read in that language too,
and that second reading may only fill silences. What 1.5.11g measured on
"Lied_R2" on 31 August, now in production; the weak-spots route from
that same trial is gone, with its answer in the log.
"""

from __future__ import annotations

import inspect
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline                          # noqa: E402
from modules import whisper                           # noqa: E402
from modules import whisper_chunks as wc              # noqa: E402
from modules.config import default_config             # noqa: E402
from modules.filesystem import (ProjectPaths, ProjectStore,  # noqa: E402
                                ensure_directories)


# --------------------------------------------------------------------------
# The work list
# --------------------------------------------------------------------------

def test_the_second_language_leads_the_queue() -> None:
    """It is as heavy as the first whole-song run, and the queue starts
    with the heaviest work - the user's rule."""
    chunks = (wc.Chunk(0.0, 20.0), wc.Chunk(20.0, 30.0))
    jobs = wc.jobs_heaviest_first(chunks, 30.0, "ko")
    assert jobs[0] == wc.WHOLE_SONG
    assert jobs[1] == (0.0, None, "ko")
    assert len(jobs) == 4


def test_without_a_second_language_nothing_changes() -> None:
    chunks = (wc.Chunk(0.0, 20.0), wc.Chunk(20.0, 30.0))
    assert wc.jobs_heaviest_first(chunks, 30.0) == [
        wc.WHOLE_SONG, (0.0, 20.0), (20.0, 30.0)]


def test_the_second_language_does_not_clash_with_the_whole_song() -> None:
    """The same seconds, a different reading: if the key were equal, one
    would push the other out of the result."""
    jobs = wc.jobs_heaviest_first((), 0.0, "ko")
    assert jobs[1] != wc.WHOLE_SONG and len(set(jobs)) == len(jobs)


# --------------------------------------------------------------------------
# The lanes: every lane its own language
# --------------------------------------------------------------------------

def test_every_lane_gets_its_own_language(monkeypatch) -> None:
    asked = []

    def fake(audio_path, settings, start=0.0, end=None, initial_prompt="",
             language_override=None, cancelled=None):
        asked.append((start, end, language_override))
        return ()

    monkeypatch.setattr(whisper, "transcribe_slice", fake)
    wc.run_over_lanes("a.wav", None,
                      [wc.WHOLE_SONG, (0.0, None, "ko"), (10.0, 20.0)],
                      "", "en", lanes=1)
    assert sorted(asked, key=str) == sorted(
        [(0.0, None, "en"), (0.0, None, "ko"), (10.0, 20.0, "en")], key=str)


def test_the_second_language_counts_as_a_filler() -> None:
    """For the merge the second language is the same kind of thing as a
    chunk: a reading allowed to fill a silence."""
    second = whisper.segments_from_dicts([{
        "index": 0, "text": "뛰어", "start": 50.4, "end": 50.9,
        "words": [{"text": "뛰어", "start": 50.4, "end": 50.9,
                   "confidence": 0.8}]}])
    found = {wc.WHOLE_SONG: (), (0.0, None, "ko"): second}
    assert [w["text"] for w in wc.extra_words_from(found)] == ["뛰어"]


# --------------------------------------------------------------------------
# When there is a second language
# --------------------------------------------------------------------------

def _context(tmp_path, text: str):
    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    (paths.input_dir / "lyrics.txt").write_text(text, encoding="utf-8")
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


def test_a_real_passage_in_another_script_counts(tmp_path) -> None:
    context = _context(tmp_path, "we run and we jump\n뛰어 뛰어 뛰어\n")
    assert pipeline._second_language_code(context, "en") == "ko"


def test_the_language_of_the_run_itself_does_not_count(tmp_path) -> None:
    """Reading the same song twice in the same language costs a run and
    yields nothing."""
    context = _context(tmp_path, "we run and we jump\n뛰어 뛰어 뛰어\n")
    assert pipeline._second_language_code(context, "ko") == ""


def test_a_single_loanword_is_no_second_language(tmp_path) -> None:
    context = _context(tmp_path, "we run and we jump\nnaar 뛰어 toe\n")
    assert pipeline._second_language_code(context, "en") == ""


# --------------------------------------------------------------------------
# Production: the second language only fills silences
# --------------------------------------------------------------------------

def _word(text, start, end, conf=0.9):
    return {"text": text, "start": start, "end": end, "confidence": conf}


def _segment(text, start, end, words):
    return {"index": 0, "text": text, "start": start, "end": end,
            "words": [_word(*w) for w in words]}


@pytest.fixture
def _bilingual(tmp_path, monkeypatch):
    """A project with Korean in the lyrics and two fake readings."""
    def fake_slice(audio_path, settings, start=0.0, end=None,
                   initial_prompt="", language_override=None,
                   cancelled=None):
        if end is None and language_override == "ko":
            return whisper.segments_from_dicts([
                # one in the silence - that one may join
                _segment("뛰어", 25.0, 25.6, [("뛰어", 25.0, 25.6)]),
                # and one on top of a word the first language heard
                _segment("점프", 1.0, 1.4, [("점프", 1.0, 1.4)])])
        if end is None:
            return whisper.segments_from_dicts([
                _segment("we jump", 1.0, 2.0,
                         [("we", 1.0, 1.4), ("jump", 1.5, 2.0)])])
        return ()

    context = _context(tmp_path, "we jump 뛰어\n뛰어 뛰어 뛰어\n")
    monkeypatch.setattr(whisper, "transcribe_slice", fake_slice)
    monkeypatch.setattr(pipeline, "_original_vocal_windows",
                        lambda c: [(0.0, 10.0), (20.0, 30.0)])
    monkeypatch.setattr(pipeline, "lyric_keys", lambda c: frozenset())
    return context


def test_the_second_language_fills_the_silence(tmp_path, _bilingual) -> None:
    context = _bilingual
    out_dir = context.paths.output_dir / "original"
    segments, filled, _language = pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "en", out_dir)
    texts = [s.text for s in segments]
    assert "뛰어" in texts and filled == 1


def test_the_second_language_never_overrules_a_heard_word(tmp_path,
                                                          _bilingual) -> None:
    """The first run stays the truth; that is the whole reason this
    merge was the most cautious of the eight."""
    context = _bilingual
    segments, _filled, _language = pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "en", context.paths.output_dir / "original")
    texts = [s.text for s in segments]
    assert "we jump" in texts and "점프" not in texts


def test_the_run_report_names_the_second_language(tmp_path,
                                                  _bilingual) -> None:
    import json
    context = _bilingual
    out_dir = context.paths.output_dir / "original"
    pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "en", out_dir)
    info = json.loads((out_dir / "run_info.json").read_text(encoding="utf-8"))
    assert info["second_language"] == "ko"


def test_lanes_still_run_for_a_second_language_without_chunks(
        tmp_path, _bilingual, monkeypatch) -> None:
    """Otherwise a song that cannot be cut into chunks would lose its
    second language."""
    context = _bilingual
    monkeypatch.setattr(pipeline, "_original_vocal_windows",
                        lambda c: [(0.0, 30.0)])
    segments, filled, _language = pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "en", context.paths.output_dir / "original")
    assert filled == 1 and "뛰어" in [s.text for s in segments]


# --------------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------------

def test_the_second_language_belongs_in_the_cache_key() -> None:
    """Add a Korean verse and the stored transcription is the answer to
    a different question."""
    source = inspect.getsource(pipeline.detect_track)
    assert 'step.get("second_language", second_code)) == second_code' in source
    assert '"second_language": second_code' in source


# --------------------------------------------------------------------------
# What was taken out
# --------------------------------------------------------------------------

def test_the_weak_spots_route_is_gone() -> None:
    """B538: six words and 0% on a real line - too little run-up for
    Whisper. The answer is in the log, the route is no longer in the
    code (as with 1.5.8 and 1.5.11c)."""
    from modules import test_panel

    for name in ("weak_by_ratio", "useful_spans", "combine_in_spots",
                 "_pad_and_cap"):
        assert not hasattr(test_panel, name), name
    source = inspect.getsource(test_panel.two_language_trial)
    assert "spot" not in source.lower().replace("search_col_spot", "")


def test_the_trial_still_measures_whether_merging_wins() -> None:
    """One song is no rule; the trial stays around to check that on a
    new song."""
    from modules import test_panel

    codes = {trial.code: trial for trial in test_panel.HEAVY_TRIALS}
    assert "1.5.11g" in codes and not codes["1.5.11g"].off
    source = inspect.getsource(test_panel.two_language_trial)
    assert "search_fill_silence" in source and "merge_runs" in source


# --------------------------------------------------------------------------
# B539 - a bunched-up tail is spread over the singing
# --------------------------------------------------------------------------

def _line(index, text, start, end):
    from modules.timing import Syllable, TimedLine
    words = text.split()
    step = (end - start) / len(words)
    return TimedLine(
        index=index, text=text, crowd=False, block=0, quality="high",
        syllables=tuple(
            Syllable(("" if i == 0 else " ") + w,
                     start + i * step, start + (i + 1) * step)
            for i, w in enumerate(words)))


def _bunched_tail():
    """The picture from "Lied N": six lines at the floor duration one
    after another, while the singing runs on afterwards."""
    from modules import timing
    head = [_line(0, "een echte zin met tijd", 10.0, 13.0),
            _line(1, "nog een echte zin", 14.0, 17.0)]
    tail = [_line(2 + i, f"regel {i}", 20.0 + i * 1.0, 21.0 + i * 1.0)
            for i in range(6)]
    windows = [(10.0, 17.0), (20.0, 23.0), (26.0, 29.0), (32.0, 35.0),
               (38.0, 41.0)]
    return timing, head + tail, windows


def test_the_tail_spreads_over_the_singing_still_to_come() -> None:
    timing, lines, windows = _bunched_tail()
    out = timing.stretch_tail_over_singing(lines, windows)
    assert [round(r.start, 1) for r in out[:2]] == [10.0, 14.0]  # head stays
    starts = [r.start for r in out[2:]]
    assert starts != [r.start for r in lines[2:]]
    assert max(starts) > 35.0        # the last windows are used
    assert starts == sorted(starts)  # and the order holds


def test_without_singing_afterwards_nothing_moves() -> None:
    timing, lines, _ = _bunched_tail()
    windows = [(10.0, 17.0), (20.0, 26.5)]   # singing stops just after it
    out = timing.stretch_tail_over_singing(lines, windows)
    assert [r.start for r in out] == [r.start for r in lines]


def test_a_tail_with_timings_of_its_own_stays_put() -> None:
    """The rule only steps in where the placement itself says it had
    nothing to go on: lines sitting at the floor of the minimum
    duration."""
    timing, lines, windows = _bunched_tail()
    roomy = list(lines[:2]) + [
        _line(2 + i, f"regel {i}", 20.0 + i * 3.0, 22.5 + i * 3.0)
        for i in range(6)]
    # singing that runs on well AFTER the tail, or this test would pass
    # on the singing check instead of on the floor check
    roomy_windows = windows + [(44.0, 50.0)]
    out = timing.stretch_tail_over_singing(roomy, roomy_windows)
    assert [r.start for r in out] == [r.start for r in roomy]


def test_a_long_last_line_does_not_hide_the_tail() -> None:
    """The last line is often padded to the end of the song; that one
    may not mask the fifteen bunched-up lines before it."""
    timing, lines, windows = _bunched_tail()
    with_tail = list(lines)
    with_tail[-1] = _line(7, "laatste zin", 25.0, 28.0)
    out = timing.stretch_tail_over_singing(with_tail, windows)
    assert [r.start for r in out[2:]] != [r.start for r in with_tail[2:]]


def test_without_windows_nothing_happens() -> None:
    timing, lines, _ = _bunched_tail()
    assert timing.stretch_tail_over_singing(lines, []) == lines
    assert timing.stretch_tail_over_singing(lines, None) == lines


def test_the_lines_keep_their_own_length() -> None:
    """Shifting, not stretching: the syllables inside a line keep their
    relative spacing."""
    timing, lines, windows = _bunched_tail()
    out = timing.stretch_tail_over_singing(lines, windows)
    for before, after in zip(lines[2:], out[2:]):
        assert round(after.end - after.start, 3) == \
            round(before.end - before.start, 3)
        assert len(after.syllables) == len(before.syllables)


def test_the_yardstick_has_to_see_this() -> None:
    """B539 sits in sanitize_timing and not in a step only the app
    takes - otherwise the yardstick measures something other than what
    the user gets."""
    import inspect
    from modules import timing
    source = inspect.getsource(timing.sanitize_timing)
    assert "stretch_tail_over_singing(result, active_windows" in source


def test_a_song_of_short_shouts_is_not_a_tail() -> None:
    """B539 after the re-read: without the demand that the line BEFORE
    the tail is not a floor line, a carnival stomper of twenty short
    shouts was one tail from line zero on - and then a rule about the
    END of a song shifts the whole song."""
    from modules import timing
    lines = [_line(i, f"hop {i}", 20.0 + i * 1.0, 21.0 + i * 1.0)
             for i in range(20)]
    windows = [(20.0, 40.0), (46.0, 60.0)]
    out = timing.stretch_tail_over_singing(lines, windows)
    assert [r.start for r in out] == [r.start for r in lines]


def test_the_tail_starts_at_the_first_window() -> None:
    """Four lines over ten windows left the first six windows empty and
    pushed everything to the end of the song."""
    from modules import timing
    windows = [(20.0 + i * 5.0, 23.0 + i * 5.0) for i in range(10)]
    places = timing._spread_over_windows(4, windows, 20.0, 70.0)
    assert places[0] == 20.0
    assert places == sorted(places)
    assert places[-1] < 60.0              # not everything at the back


def test_no_line_runs_past_the_end_of_the_song() -> None:
    from modules import timing
    head = [_line(0, "een echte zin met tijd", 10.0, 13.0),
            _line(1, "nog een echte zin", 14.0, 17.0)]
    tail = [_line(2 + i, f"regel {i}", 20.0 + i * 1.0, 21.0 + i * 1.0)
            for i in range(6)]
    windows = [(10.0, 17.0), (20.0, 30.0), (36.0, 44.0)]
    out = timing.stretch_tail_over_singing(head + tail, windows,
                                           song_duration=40.0)
    assert max(r.end for r in out) <= 40.0 + 1e-6


def test_too_little_room_leaves_everything_where_it_is() -> None:
    """Better the bunched-up tail than a tail that only looks
    measured."""
    from modules import timing
    head = [_line(0, "een echte zin met tijd", 10.0, 13.0)]
    tail = [_line(1 + i, f"regel {i}", 20.0 + i * 1.0, 21.0 + i * 1.0)
            for i in range(8)]
    # only three seconds of singing for eight lines
    windows = [(10.0, 13.0), (20.0, 23.0), (40.0, 41.0)]
    out = timing.stretch_tail_over_singing(head + tail, windows)
    assert [r.start for r in out] == [r.start for r in head + tail]


def test_a_disabled_line_eats_no_singing() -> None:
    """A line that never reaches the screen (B180) may not claim a
    stretch of singing nobody sees."""
    from dataclasses import replace
    from modules import timing
    head = [_line(0, "een echte zin met tijd", 10.0, 13.0)]
    tail = [_line(1 + i, f"regel {i}", 20.0 + i * 1.0, 21.0 + i * 1.0)
            for i in range(6)]
    tail[2] = replace(tail[2], disabled=True)
    windows = [(10.0, 13.0), (20.0, 30.0), (36.0, 46.0)]
    out = timing.stretch_tail_over_singing(head + tail, windows)
    visible = [r.start for r in out[1:] if not r.disabled]
    assert len(visible) == 5 and visible == sorted(visible)
    assert max(visible) > 36.0            # the last windows were used


def test_a_line_without_syllables_does_not_topple_the_step() -> None:
    from dataclasses import replace
    from modules import timing
    line = _line(0, "een zin", 10.0, 11.0)
    empty = replace(line, syllables=())
    assert timing._moved_to(empty, 50.0) is empty


def test_without_vocal_windows_there_is_no_second_run(tmp_path, _bilingual,
                                                      monkeypatch) -> None:
    """B538 after the re-read: without measured singing a second reading
    can by definition fill nothing (a word only counts where it sits on
    singing), so that would be a whole Whisper run for certainly nothing
    - and the progress bar would stall on it as well."""
    context = _bilingual
    asked = []
    real = whisper.transcribe_slice

    def count(*args, **kwargs):
        asked.append(kwargs.get("language_override"))
        return real(*args, **kwargs)

    monkeypatch.setattr(whisper, "transcribe_slice", count)
    monkeypatch.setattr(pipeline, "_original_vocal_windows", lambda c: [])
    monkeypatch.setattr(
        whisper, "transcribe",
        lambda *a, **k: whisper.segments_from_dicts([
            _segment("we jump", 1.0, 2.0,
                     [("we", 1.0, 1.4), ("jump", 1.5, 2.0)])]))
    segments, filled, language = pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "en", context.paths.output_dir / "original")
    assert asked == [] and filled == 0 and language == ""


def test_the_language_read_goes_back_into_the_cache_key() -> None:
    """Otherwise the key says "ko" while no Korean run ever happened,
    and next time everything runs again."""
    source = inspect.getsource(pipeline.detect_track)
    assert "segments, filled, second_code = _transcribe_in_pieces(" in source


def test_kanji_do_not_make_a_japanese_song_chinese(tmp_path) -> None:
    """Kanji count as Chinese by their block (B495); a Japanese song is
    full of them, and that would cost a whole Chinese run every time for
    a script the first run already knows."""
    context = _context(tmp_path, "hana no uta\n花 歌 花 歌 花 歌\n")
    assert pipeline._second_language_code(context, "ja") == ""
    assert pipeline._second_language_code(context, "nl") == "zh"


def test_restoring_builds_the_same_timing_as_building() -> None:
    """B539: "Originele timing herstellen" produced a different timing
    than the build step itself, because it did not pass the vocal
    windows - and B336 and B539 are exactly what hangs on those."""
    from pathlib import Path
    from modules import gui
    source = Path(gui.__file__).read_text(encoding="utf-8")
    part = source[source.index("def reset_original"):]
    part = part[:part.index("mapping = fresh")]
    assert "active_windows=pipeline._vocal_windows(context)" in part


def test_the_trial_measures_the_merge_production_makes() -> None:
    """The row in the table has to be what the program does: the first
    run as truth, the chunks AND the second language as fillers."""
    import inspect
    from modules import test_panel
    source = inspect.getsource(test_panel.two_language_trial)
    assert "extra += list(chunked_first)" in source
