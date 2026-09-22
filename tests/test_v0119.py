"""Tests for v0.119.0: B375, B376, B377.

Written in English on purpose. The working agreement says the internal
language is English - including test names and docstrings - and this
file is the start of honouring it again instead of adding to the pile.

B375 a ``[bg]`` line split the block it stood in. Block boundaries were
     derived from a GAP in the line numbers, and a bg line is left out
     of that list, so it produced exactly the same gap as a blank line.
     Measured on a real project: the lyrics went from 8 blocks to 13
     while the karaoke kept 8, and the sentence coupling collapsed from
     47 lines of high quality to zero.
B376 the structure warning counted raw lines on the lyrics side and
     parsed lines on the karaoke side, so it reported 18 against 12
     where the coupling itself saw 12 against 12.
B377 the vocal stem decides. A segment that sits on no measured singing
     is not singing - whatever the text claims. That also catches the
     prompt echo, where Whisper speaks the lyrics we handed it as an
     initial prompt during an instrumental intro; no text-based rule can
     see that one, because the text is genuine lyrics.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import model_register, pipeline, song_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean_register():
    yield
    model_register.restore_all()
    model_register.apply_settings({})


def _context(tmp_path: Path, lyrics: str, karaoke: str | None = None,
             name: str = "Test"):
    from dataclasses import replace

    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=name)
    ensure_directories(paths)
    (paths.input_dir / song_text.LYRICS_FILENAME).write_text(
        lyrics, encoding="utf-8")
    if karaoke is not None:
        from modules import karaoke_text
        (paths.input_dir / karaoke_text.FILENAME).write_text(
            karaoke, encoding="utf-8")
    config = default_config()
    config = replace(config, song=replace(config.song, title=name))
    return pipeline.AppContext(paths=paths, config=config,
                               store=ProjectStore(paths.project_file))


def _word(text, start, end, confidence=0.8):
    from modules.whisper import Word
    return Word(text=text, start=start, end=end, confidence=confidence)


def _segment(words):
    from modules.whisper import Segment
    return Segment(index=0, text=" ".join(w.text for w in words),
                   start=words[0].start, end=words[-1].end,
                   words=tuple(words))


# --------------------------------------------------------------------------
# B375 - a [bg] line must not split its block
# --------------------------------------------------------------------------

LYRICS_WITH_BG = (
    "First line here\n"
    "Second line here\n"
    "\n"
    "Chorus line one\n"
    "Chorus line two\n"
    "[bg]Softly in the back[/bg]\n"
    "Chorus line three\n"
    "Chorus line four\n"
)


def test_a_bg_line_is_recognised_as_bg_only(tmp_path) -> None:
    context = _context(tmp_path, LYRICS_WITH_BG)
    assert pipeline._bg_only_lines(context), \
        "the bg line has to be found, otherwise the fix does nothing"


def test_bg_lines_do_not_count_as_a_gap() -> None:
    """The heart of B375: the block counter must look past the hole.

    B523 moved the counting into ``_line_blocks``, because the blocks
    have to be known BEFORE the placement. The exemption travelled along
    and is checked here where it lives.
    """
    source = inspect.getsource(pipeline._original_lines_detailed)
    assert "_bg_only_lines" in source and "_line_blocks" in source
    counter = inspect.getsource(pipeline._line_blocks)
    assert "bg_only" in counter and "skipped" in counter
    # And it really counts: three lines with number 0, 1 and 3 are one
    # block when line 2 is a whole-[bg] line and two blocks when it is
    # a blank line.
    assert pipeline._line_blocks([0, 1, 3], frozenset({2})) == [0, 0, 0]
    assert pipeline._line_blocks([0, 1, 3], frozenset()) == [0, 0, 1]


def test_only_a_blank_line_starts_a_new_block(tmp_path) -> None:
    """A blank line yields a gap of 2 and a bg line yields one as well;
    only the first may count."""
    context = _context(tmp_path, LYRICS_WITH_BG)
    bg = pipeline._bg_only_lines(context)
    assert len(bg) == 1
    line = next(iter(bg))
    # The lines around it belong to the same block.
    assert line - 1 not in bg and line + 1 not in bg


def test_a_lyrics_line_without_bg_keeps_its_blocks(tmp_path) -> None:
    context = _context(tmp_path, "One\nTwo\n\nThree\nFour\n")
    assert pipeline._bg_only_lines(context) == frozenset()


# --------------------------------------------------------------------------
# B376 - the structure warning has to speak the same language
# --------------------------------------------------------------------------

def test_a_bg_only_line_is_detected_in_raw_text() -> None:
    assert song_text.is_bg_only_line("[bg]Softly in the back[/bg]")
    assert song_text.is_bg_only_line("[bg]No closing marker")
    assert not song_text.is_bg_only_line("Don't stand so close to me")
    assert not song_text.is_bg_only_line("[crowd]La la la[/crowd]")


def test_the_structure_check_skips_bg_lines(tmp_path) -> None:
    """Both sides now count the same thing: 2 against 2, not 3 against 2."""
    context = _context(
        tmp_path,
        "Chorus line one\nChorus line two\n[bg]Softly in the back[/bg]\n",
        karaoke="Chorus line one\nChorus line two\n")
    ok, report = pipeline.check_text_alignment(context)
    assert ok, report
    assert "2 / " in report


def test_a_real_difference_is_still_reported(tmp_path) -> None:
    """The warning must not become blind - only bg-aware."""
    context = _context(tmp_path, "One\nTwo\nThree\n", karaoke="One\nTwo\n")
    ok, _report = pipeline.check_text_alignment(context)
    assert not ok


# --------------------------------------------------------------------------
# B377 - the vocal stem decides
# --------------------------------------------------------------------------

def test_a_segment_without_measured_singing_is_dropped(tmp_path,
                                                       monkeypatch) -> None:
    context = _context(tmp_path, "Anything\n")
    monkeypatch.setattr(pipeline, "_vocal_windows",
                        lambda ctx: ((30.0, 60.0),))
    sung = _segment([_word("real", 35.0, 36.0), _word("words", 36.0, 37.0)])
    echo = _segment([_word("Loose", 7.4, 8.0), _word("talk", 8.0, 9.0)])
    dropped: list = []
    kept = pipeline._drop_unsung_segments(context, (echo, sung),
                                          dropped_out=dropped)
    assert [s.text for s in kept] == ["real words"]
    assert [s.text for s in dropped] == ["Loose talk"]


def test_a_stretched_segment_end_does_not_cost_a_real_segment(
        tmp_path, monkeypatch) -> None:
    """Whisper regularly stretches the end of a segment well past the
    last note. Judging per segment would drop a real one; per word it
    survives."""
    context = _context(tmp_path, "Anything\n")
    monkeypatch.setattr(pipeline, "_vocal_windows",
                        lambda ctx: ((30.0, 33.0),))
    stretched = _segment([_word("sung", 30.5, 31.0), _word("here", 31.0, 32.0),
                          _word("tail", 40.0, 41.0)])
    kept = pipeline._drop_unsung_segments(context, (stretched,))
    assert len(kept) == 1


def test_without_a_measurement_nothing_is_judged(tmp_path,
                                                 monkeypatch) -> None:
    """No vocal stem, no opinion - the read path may never depend on it."""
    context = _context(tmp_path, "Anything\n")
    monkeypatch.setattr(pipeline, "_vocal_windows", lambda ctx: ())
    segment = _segment([_word("whatever", 1.0, 2.0)])
    assert pipeline._drop_unsung_segments(context, (segment,)) == (segment,)


def test_the_filter_runs_before_the_text_based_rounds() -> None:
    """Cheapest and most decisive first; the text rounds only get what
    is left."""
    source = inspect.getsource(pipeline._clean_segments_and_alignment)
    assert source.index("_drop_unsung_segments") < \
        source.index("_filter_hallucinations(")


def test_the_referee_is_a_switchable_model() -> None:
    model = model_register.by_code("B377")
    assert model is not None
    assert model.level == "koppeling"
    assert model.default_on


def test_a_prompt_echo_cannot_be_caught_by_text(tmp_path) -> None:
    """Why B377 exists at all: the prompt echo is literally the lyrics.

    Whisper gets the lyrics as an initial prompt (B263) and during an
    instrumental intro it simply speaks them. Every check of the form
    "does this resemble the lyrics?" says yes with full conviction.
    """
    lyrics = song_text.load_lyrics.__doc__ is not None  # module is usable
    assert lyrics
    context = _context(tmp_path, "Loose talk in the classroom\n")
    words = song_text.load_lyrics(
        context.paths.input_dir / song_text.LYRICS_FILENAME)
    keys = frozenset(pipeline.cluster_module.phonetic_key(w.text)
                     for w in words)
    for word in ("Loose", "talk", "classroom"):
        assert pipeline._best_lyrics_match(word, keys) >= 0.9, \
            "the echo matches the lyrics perfectly - that is the problem"
