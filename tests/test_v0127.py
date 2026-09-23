"""Tests for v0.127.0: B390 - the chunk/merge experiment.

The parts that can be reasoned about without starting Whisper: where to
cut, what prompt a piece gets, and how the results go back together. The
transcribing itself is measured by 1.5.11d on real audio; these tests pin
the rules that trial leans on.

The rule that matters most is a refusal. Two Whisper runs share their
initial prompt (B263), so if both say the same thing that can mean they
both heard it - or that both are reciting the prompt, which is exactly
the prompt echo we are trying to catch. Agreement is therefore not
evidence, and ``merge_runs`` is deliberately not a vote: the first run
stays the truth and another run may only speak where the first says
nothing at all. The vocal stem is the only witness that knows nothing of
the lyrics, so it holds the veto.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import whisper_chunks as chunks  # noqa: E402


def _word(text, start, end, confidence=0.9):
    return {"text": text, "start": start, "end": end,
            "confidence": confidence}


# --------------------------------------------------------------------------
# Where to cut
# --------------------------------------------------------------------------

def test_the_cut_lands_in_the_silence() -> None:
    """A cut in silence costs nothing; a cut through singing costs a
    word. The vocal stem already says where the silences are."""
    windows = ((0.0, 10.0), (14.0, 24.0), (28.0, 40.0))
    cut = chunks.cut_points(windows, total=40.0)
    assert cut[0].start == 0.0
    assert cut[0].end == pytest.approx(26.0)   # the middle of 24-28
    assert not cut[0].forced


def test_no_piece_is_longer_than_whispers_window() -> None:
    windows = tuple((float(n), float(n) + 3.0) for n in range(0, 300, 5))
    for chunk in chunks.cut_points(windows, total=300.0):
        assert chunk.duration <= chunks.WINDOW_S + 1e-6


def test_singing_that_never_pauses_is_cut_with_overlap() -> None:
    """Then there is no free cut, so the border area has to occur in two
    pieces and the merge can pick the one where the word is furthest
    from an edge."""
    cut = chunks.cut_points(((0.0, 90.0),), total=90.0)
    assert any(c.forced for c in cut)
    forced = [c for c in cut if c.forced][0]
    following = cut[cut.index(forced) + 1]
    assert following.start < forced.end, "the pieces should overlap"


def test_the_offset_moves_every_edge() -> None:
    """The offset idea in its simplest form: start a few seconds in and
    every window edge lands somewhere else than in the first run."""
    windows = ((0.0, 10.0), (14.0, 24.0), (28.0, 40.0))
    plain = chunks.cut_points(windows, total=40.0)
    shifted = chunks.cut_points(windows, total=40.0, first_sound=5.0)
    assert shifted[0].start == 5.0
    assert plain[0].start != shifted[0].start


def test_without_windows_it_is_one_piece() -> None:
    """No vocal stem, no opinion - the same fallback as everywhere."""
    assert chunks.cut_points((), total=30.0) == (chunks.Chunk(0.0, 30.0),)


def test_an_empty_song_yields_nothing() -> None:
    assert chunks.cut_points(((0.0, 5.0),), total=0.0) == ()


# --------------------------------------------------------------------------
# The prompt per piece
# --------------------------------------------------------------------------

def test_a_piece_gets_the_lines_that_belong_to_it() -> None:
    lines = [(2.0, "Eerste regel"), (30.0, "Middenregel"),
             (120.0, "Veel later")]
    prompt = chunks.chunk_prompt(lines, chunks.Chunk(25.0, 40.0))
    assert "Middenregel" in prompt
    assert "Veel later" not in prompt


def test_the_slice_is_generous_on_purpose() -> None:
    """It leans on the first run's placement, and that is worst exactly
    where we are looking again."""
    lines = [(20.0, "Net ervoor"), (46.0, "Net erna")]
    prompt = chunks.chunk_prompt(lines, chunks.Chunk(25.0, 40.0))
    assert "Net ervoor" in prompt and "Net erna" in prompt


def test_the_piece_prompt_is_running_text_not_a_word_list() -> None:
    """The whole gain: locally there is room for real phrasing, where
    the global prompt (B263) has to deduplicate to fit 400 characters."""
    lines = [(1.0, "Don't stand so close to me"),
             (5.0, "Don't stand so close to me")]
    prompt = chunks.chunk_prompt(lines, chunks.Chunk(0.0, 10.0))
    assert prompt.count("Don't stand so close to me") == 2


def test_the_prompt_stays_within_its_budget() -> None:
    lines = [(float(n), "een hele lange regel vol woorden en nog wat")
             for n in range(40)]
    assert len(chunks.chunk_prompt(lines, chunks.Chunk(0.0, 40.0))) <= 400


def test_no_lines_means_no_prompt() -> None:
    assert chunks.chunk_prompt([], chunks.Chunk(0.0, 10.0)) == ""


# --------------------------------------------------------------------------
# Merging - and the refusal it is built on
# --------------------------------------------------------------------------

def test_a_hole_is_filled_from_the_other_run() -> None:
    windows = ((0.0, 30.0),)
    base = [_word("een", 1.0, 2.0)]
    extra = [_word("twee", 10.0, 11.0)]
    merged, filled = chunks.merge_runs(base, extra, windows)
    assert filled == 1
    assert [w["text"] for w in merged] == ["een", "twee"]


def test_a_word_that_was_heard_is_never_overruled() -> None:
    """Not a vote: the first run stays the truth. A second run with the
    same prompt is not an independent witness, so it may not outvote."""
    windows = ((0.0, 30.0),)
    base = [_word("gehoord", 5.0, 6.0, confidence=0.3)]
    extra = [_word("anders", 5.2, 5.9, confidence=0.99)]
    merged, filled = chunks.merge_runs(base, extra, windows)
    assert filled == 0
    assert [w["text"] for w in merged] == ["gehoord"]


def test_a_word_beside_the_singing_may_not_fill_anything() -> None:
    """The vocal stem holds the veto - the same rule B377 applies to
    whole segments, here per word."""
    windows = ((0.0, 10.0),)
    merged, filled = chunks.merge_runs(
        [], [_word("Thank you", 20.0, 21.0, confidence=1.0)], windows)
    assert filled == 0 and merged == ()


def test_an_unsure_word_does_not_get_in_either() -> None:
    windows = ((0.0, 30.0),)
    merged, filled = chunks.merge_runs(
        [], [_word("misschien", 5.0, 6.0, confidence=0.1)], windows)
    assert filled == 0 and merged == ()


def test_a_word_from_the_lyrics_counts_heavier() -> None:
    from modules import cluster

    windows = ((0.0, 30.0),)
    word = _word("close", 5.0, 6.0, confidence=0.5)
    keys = frozenset({cluster.phonetic_key("close")})
    assert chunks.word_score(word, windows, keys) > \
        chunks.word_score(word, windows, frozenset({"iets_anders"}))


# --------------------------------------------------------------------------
# The number the whole exercise aims at
# --------------------------------------------------------------------------

def test_unheard_seconds_counts_singing_without_text() -> None:
    """The same measure 1.5.8 reports: singing with no word on it."""
    windows = ((0.0, 10.0), (20.0, 30.0))
    words = [_word("a", 0.0, 5.0), _word("b", 20.0, 30.0)]
    assert chunks.unheard_seconds(words, windows) == pytest.approx(5.0)


def test_full_coverage_leaves_nothing_unheard() -> None:
    windows = ((0.0, 10.0),)
    assert chunks.unheard_seconds([_word("a", 0.0, 10.0)], windows) == 0.0


def test_without_any_word_everything_is_unheard() -> None:
    assert chunks.unheard_seconds([], ((0.0, 10.0),)) == pytest.approx(10.0)


# --------------------------------------------------------------------------
# The trial that measures it on real audio
# --------------------------------------------------------------------------

def test_the_chunk_trial_is_in_the_heavy_bin() -> None:
    from modules import test_panel

    codes = {h.code: h for h in test_panel.HEAVY_TRIALS}
    assert "1.5.11d" in codes
    assert codes["1.5.11d"].off, \
        "B454: the chunking runs in production, the trial is off"
    assert codes["1.5.11d"].function is test_panel.chunk_trial


def test_it_picks_the_project_with_the_most_unheard_singing() -> None:
    import inspect

    from modules import test_panel

    source = (inspect.getsource(test_panel.chunk_trial)
              + inspect.getsource(test_panel._chunk_one_song))
    # B416: since the overnight trial these are the four biggest gaps,
    # and the ranking is the same as that of the separate choice.
    assert "_projects_by_gap" in source


def test_it_reports_seconds_unheard_and_not_a_word_count() -> None:
    """The number the whole experiment is aimed at: singing with no text
    on it. A word count says nothing - a run can produce more words and
    still leave the same hole."""
    import inspect

    from modules import test_panel

    source = (inspect.getsource(test_panel.chunk_trial)
              + inspect.getsource(test_panel._chunk_one_song))
    assert "unheard_seconds" in source


def test_the_merge_is_reported_beside_the_variants_not_instead() -> None:
    """Each variant on its own AND the merge, so a win is traceable to
    where it came from."""
    import inspect

    from modules import test_panel

    source = (inspect.getsource(test_panel.chunk_trial)
              + inspect.getsource(test_panel._chunk_one_song))
    # The calls, not the docstring that also mentions merge_runs.
    assert source.index("wc.merge_runs(") > source.index("probe.run_chunked(")


def test_the_probe_can_transcribe_a_slice() -> None:
    """The offset and the chunk both lean on this: cut the audio, and
    shift the times back onto the song's own timeline."""
    import importlib.util
    import inspect
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "probe_slice", root / "tools" / "whisper_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = list(inspect.signature(module.run_once).parameters)
    assert "start" in names and "end" in names
    assert hasattr(module, "run_chunked")
    source = inspect.getsource(module.run_once)
    assert "shift" in source, "the times have to go back onto the song timeline"
