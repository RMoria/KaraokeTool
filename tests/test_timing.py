"""Tests for modules.timing (syllables and timing.json)."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.karaoke_text import TextLine
from modules.timing import (
    editor_view_cells,
    generate_skeleton,
    load_timing,
    save_timing,
    split_line,
    split_syllables,
    word_spans,
)


def test_block_survives_timing_json(tmp_path: Path) -> None:
    """B127: the block number survives writing/reading timing.json."""
    lines = generate_skeleton(
        (TextLine(index=0, text="een twee", crowd=False, block=0),
         TextLine(index=1, text="la la", crowd=True, block=2)),
        {0: (0.0, 2.0), 1: (3.0, 4.0)})
    assert [line.block for line in lines] == [0, 2]
    path = tmp_path / "timing.json"
    save_timing(lines, path)
    assert [line.block for line in load_timing(path)] == [0, 2]


def test_editor_view_cells_modes() -> None:
    """B127: blocks/sentences/words yield the right cells."""
    lines = [
        {"text": "een twee", "crowd": False, "block": 0,
         "syllables": [{"text": "een", "start": 0.0, "end": 1.0},
                       {"text": " twee", "start": 1.0, "end": 2.0}]},
        {"text": "drie", "crowd": False, "block": 0,
         "syllables": [{"text": "drie", "start": 2.0, "end": 3.0}]},
        {"text": "la", "crowd": True, "block": 1,
         "syllables": [{"text": "la", "start": 5.0, "end": 6.0}]},
    ]
    assert len(editor_view_cells(lines, "sentences")) == 3
    blocks = editor_view_cells(lines, "blocks")
    assert len(blocks) == 2
    assert blocks[0]["start"] == 0.0 and blocks[0]["end"] == 3.0
    words = editor_view_cells(lines, "words")
    assert [c["text"] for c in words] == ["een", "twee", "drie", "la"]


def test_editor_view_cells_rows() -> None:
    """B162: cells carry their source rows, for dragging/stretching."""
    from modules.timing import editor_view_cells
    lines = [
        {"text": "a b", "crowd": False, "block": 0,
         "syllables": [{"text": "a", "start": 0.0, "end": 1.0},
                       {"text": " b", "start": 1.0, "end": 2.0}]},
        {"text": "c", "crowd": False, "block": 0,
         "syllables": [{"text": "c", "start": 2.0, "end": 3.0}]},
    ]
    assert editor_view_cells(lines, "sentences")[0]["rows"] == [0]
    block = editor_view_cells(lines, "blocks")
    assert block[0]["rows"] == [0, 1]          # whole block = both lines
    assert block[0]["text"] == "a b c"          # B163: full block text


def test_original_view_cells_modes() -> None:
    """B161: the original track follows blocks/sentences/words."""
    from modules.timing import original_view_cells
    originals = [
        {"text": "een twee", "start": 0.0, "end": 2.0, "rows": [0]},
        {"text": "drie", "start": 2.0, "end": 3.0, "rows": [1]},
    ]
    line_block = {0: 0, 1: 0}
    assert len(original_view_cells(originals, "sentences", line_block)) == 2
    assert [c["text"] for c in
            original_view_cells(originals, "words", line_block)] == [
        "een", "twee", "drie"]
    block = original_view_cells(originals, "blocks", line_block)
    assert len(block) == 1 and block[0]["text"] == "een twee drie"


def test_fade_out_repeat_gets_the_same_length() -> None:
    """B166: an unanchored tail repeat takes the length of the earlier
    sentence with the same text (rather than being spread or squashed)."""
    from modules.timing import Syllable, TimedLine, sanitize_timing

    def line(i, text, start, end, quality):
        return TimedLine(index=i, text=text, crowd=False,
                         syllables=(Syllable(text, start, end),),
                         quality=quality)
    # Two anchored 'oeh' lines of 2 s, then an unanchored repeat.
    lines = (
        line(0, "oeh", 0.0, 2.0, "high"),
        line(1, "tussen", 2.0, 4.0, "high"),
        line(2, "oeh", 6.0, 6.2, "sentence"),      # unreliable, must go to ~2 s
    )
    out = sanitize_timing(lines, song_duration=30.0)
    duration = out[2].end - out[2].start
    assert duration == pytest.approx(2.0, abs=0.3)


def test_stress_default_and_toggle() -> None:
    """B151: default stress + moving/clearing it per word."""
    from modules.timing import (Syllable, TimedLine, apply_default_stress,
                                set_word_stress)
    line = TimedLine(0, "komen de", False,
                     (Syllable("ko", 0, 1), Syllable("men", 1, 2),
                      Syllable(" de", 2, 3)))
    out = apply_default_stress([line])[0]
    # Multi-syllable 'komen' -> first syllable; 'de' (1 syl) gets none.
    assert [s.stress for s in out.syllables] == [True, False, False]
    on_men = set_word_stress(out.syllables, 1)
    assert [s.stress for s in on_men] == [False, True, False]
    # Toggle: clicking again takes the stress away.
    cleared = set_word_stress(on_men, 1)
    assert [s.stress for s in cleared] == [False, False, False]


def test_redistribute_by_stress() -> None:
    """B151: stress weighs heavier in the best-effort split of durations;
    the line span stays the same and reliable lines are left alone."""
    from modules.timing import (Syllable, TimedLine, redistribute_by_stress)
    sentence = TimedLine(0, "ko men nu", False,
                    (Syllable("ko", 0.0, 1.0, stress=True),
                     Syllable(" men", 1.0, 2.0),
                     Syllable(" nu", 2.0, 3.0)), quality="sentence")
    out = redistribute_by_stress([sentence], weight=1.6)[0]
    durations = [round(s.end - s.start, 2) for s in out.syllables]
    assert durations[0] > durations[1]              # stress lasts longer
    assert out.start == 0.0 and out.end == pytest.approx(3.0)  # same span
    # A reliable (forced-alignment) line is not touched.
    high = TimedLine(1, "a b", False,
                     (Syllable("a", 0.0, 1.0, stress=True),
                      Syllable(" b", 1.0, 2.0)), quality="high")
    assert redistribute_by_stress([high])[0].syllables == high.syllables


def test_inline_crowd_marking(tmp_path: Path) -> None:
    """B179a: inline crowd words get crowd=True at syllable level, and
    that survives timing.json."""
    from modules.karaoke_text import TextLine
    from modules.timing import (apply_inline_crowd, generate_skeleton,
                                load_timing, save_timing)
    tl = TextLine(index=0, text="G Z R Waertje", crowd=False,
                  crowd_words=frozenset({3}))
    timed = generate_skeleton((tl,), {0: (0.0, 4.0)})
    timed = apply_inline_crowd(timed, (tl,))
    syls = timed[0].syllables
    # Words G/Z/R are not crowd; 'Waertje' (2 syllables) is.
    assert [s.crowd for s in syls][:3] == [False, False, False]
    assert any(s.crowd for s in syls)
    path = tmp_path / "timing.json"
    save_timing(timed, path)
    assert any(s.crowd for s in load_timing(path)[0].syllables)


def test_metadata_and_disabled_in_timing_json(tmp_path: Path) -> None:
    """B183/B180: header (project/version) + disabled flag in timing.json."""
    from modules.timing import (Syllable, TimedLine, load_timing,
                                save_timing, timing_project)
    line = TimedLine(0, "hoi", False, (Syllable("hoi", 0.0, 1.0),),
                     disabled=True)
    path = tmp_path / "timing.json"
    save_timing((line,), path, offset=0.0, project="Lied_N",
                versie="0.72.0")
    assert timing_project(path) == "Lied_N"
    back = load_timing(path)
    assert back[0].disabled is True


def test_stress_survives_timing_json(tmp_path: Path) -> None:
    """B151: stress is written to and read back from timing.json."""
    from modules.timing import Syllable, TimedLine, load_timing, save_timing
    line = TimedLine(0, "ko men", False,
                     (Syllable("ko", 0.0, 1.0, stress=True),
                      Syllable(" men", 1.0, 2.0)))
    path = tmp_path / "timing.json"
    save_timing((line,), path)
    back = load_timing(path)
    assert [s.stress for s in back[0].syllables] == [True, False]


def test_word_spans_split_on_the_space() -> None:
    """B127: syllables are grouped into words on the leading space."""
    syls = [{"text": "hos", "start": 0.0, "end": 0.5},
            {"text": "sen", "start": 0.5, "end": 1.0},
            {"text": " weer", "start": 1.0, "end": 1.5}]
    assert word_spans(syls) == [("hossen", 0.0, 1.0), ("weer", 1.0, 1.5)]


def test_syllabify_model_when_available() -> None:
    """B150: with pyphen words split finer; reconstruction stays exact."""
    import pytest as _pytest
    _pytest.importorskip("pyphen")
    # pyphen (nl) splits 'iederien' into three syllables; the heuristic
    # does not.
    pieces = split_syllables("iederien")
    assert "".join(pieces) == "iederien"
    assert len(pieces) == 3


def test_split_syllables_dutch() -> None:
    assert split_syllables("Groen") == ["Groen"]
    assert split_syllables("Zwarte") == ["Zwar", "te"]
    assert split_syllables("Zangers") == ["Zan", "gers"]
    assert split_syllables("polonaise") == ["po", "lo", "nai", "se"]
    assert split_syllables("kedeng") == ["ke", "deng"]
    assert split_syllables("TVX") == ["T", "V", "X"]  # spelled-out letters
    assert split_syllables("OE") == ["OE"]  # vowels -> vocable, 1


def test_split_line_reconstructs_exactly() -> None:
    line = "Rood Witte Zangers, vooraan in de polonaise"
    pieces = split_line(line)
    assert "".join(pieces) == line
    assert pieces[0] == "Rood"
    assert pieces[1] == " Wit"  # new word: leading space


def test_generate_skeleton_with_spans() -> None:
    lines = (TextLine(0, "Kedeng Kedeng", False),
             TextLine(1, "La-la-la", True))
    timed = generate_skeleton(lines, {0: (10.0, 12.0)})
    assert timed[0].start == pytest.approx(10.0)
    assert timed[0].end == pytest.approx(12.0)
    # Spread evenly over 4 syllables (ke/deng ke/deng).
    assert len(timed[0].syllables) == 4
    assert timed[0].syllables[1].start == pytest.approx(10.5)
    # Without times: everything at 0; crowd is kept.
    assert timed[1].end == 0.0
    assert timed[1].crowd is True


def test_timing_roundtrip(tmp_path: Path) -> None:
    lines = (TextLine(0, "Kedeng Kedeng", False),)
    timed = generate_skeleton(lines, {0: (1.0, 2.0)})
    path = tmp_path / "timing.json"
    save_timing(timed, path)
    assert load_timing(path) == timed


def test_timing_offset_roundtrip_and_old_format(tmp_path: Path) -> None:
    """B98: the offset is kept; the old bare-list format stays readable."""
    import json

    from modules.timing import load_offset
    lines = (TextLine(0, "Kedeng Kedeng", False),)
    timed = generate_skeleton(lines, {0: (1.0, 2.0)})
    path = tmp_path / "timing.json"
    save_timing(timed, path, offset=-0.192)
    assert load_offset(path) == -0.192
    assert load_timing(path) == timed
    # Old format (bare list) -> offset unknown, lines still readable.
    old = [{"line": 0, "text": "a", "crowd": False, "crowd_section": False,
            "quality": "sentence",
            "syllables": [{"text": "a", "start": 1.0, "end": 2.0,
                              "held": False}]}]
    path.write_text(json.dumps(old), encoding="utf-8")
    assert load_offset(path) is None
    assert len(load_timing(path)) == 1


def _tl(index, text, start, end, quality="sentence"):
    from modules.timing import Syllable, TimedLine
    pieces = split_line(text)
    n = len(pieces)
    width = (end - start) / n if n else 0.0
    syl = tuple(Syllable(p, round(start + i * width, 3),
                         round(start + (i + 1) * width, 3))
                for i, p in enumerate(pieces))
    return TimedLine(index=index, text=text, crowd=False, syllables=syl,
                     quality=quality)


def test_sanitize_timing_bounds_and_stays_monotonic() -> None:
    """B106: extreme durations are bounded, the order stays monotonic."""
    from modules.timing import sanitize_timing
    lines = (
        _tl(0, "Rood Witte Zangers vooraan", 10.0, 12.5, "high"),  # ref
        _tl(1, "Frikandel met mayonaise samen", 12.5, 42.5),  # 30s -> too long
        _tl(2, "Waar ik altijd verder ga door", 42.6, 42.65),  # ~0 -> too short
    )
    out = sanitize_timing(lines)
    spans = [ln.end - ln.start for ln in out]
    assert all(sp > 0 for sp in spans)
    assert spans[1] < 12.0          # no longer 30 s
    assert spans[2] >= 1.0          # a real sentence lasts at least ~1 s
    # monotonic, no overlap
    assert out[1].start >= out[0].end - 1e-6
    assert out[2].start >= out[1].end - 1e-6


def test_sanitize_timing_redistributes_between_anchors() -> None:
    """B106: piled-up lines are spread between anchors, not crammed."""
    from modules.timing import sanitize_timing
    lines = (
        _tl(0, "Rood Witte Zangers vooraan", 0.0, 2.0, "high"),  # anchor
        _tl(1, "Frikandel met mayonaise erbij", 2.0, 2.05),  # crammed (low)
        _tl(2, "Waar ik altijd verder ga door", 10.0, 12.0, "high"),  # anchor
    )
    out = sanitize_timing(lines)
    # The middle line now sits somewhere between the anchors, no longer
    # right behind line 0 at ~2.05 s.
    assert out[1].start > 3.5
    assert out[1].start < out[2].start
    assert out[0].end <= out[1].start + 1e-6      # monotonic


def test_sanitize_timing_keeps_the_pause() -> None:
    """B147: a reliable sentence keeps its real end; the pause stays."""
    from modules.timing import sanitize_timing
    lines = (
        _tl(0, "Want ze hadden van de motorcross", 4.0, 6.0, "high"),
        _tl(1, "Oehoe oehoerend hard vooraan", 10.0, 12.0, "high"),
    )
    out = sanitize_timing(lines)
    # Line 0 ends near its real end (~6 s), not glued shut up to 10.
    assert out[0].end < 8.0
    assert out[1].start - out[0].end > 0.4        # a visible pause


def test_sanitize_timing_closes_a_small_gap() -> None:
    """B147: a small gap (<0.4 s) is wiped away (the lines join up)."""
    from modules.timing import sanitize_timing
    lines = (
        _tl(0, "Rood Witte Zangers samen", 4.0, 7.8, "high"),
        _tl(1, "Frikandel met mayonaise erbij", 8.0, 11.0, "high"),
    )
    out = sanitize_timing(lines)
    assert abs(out[0].end - out[1].start) < 1e-6   # contiguous


def test_sanitize_timing_spreads_a_crammed_tail() -> None:
    """B139/B148: tightly packed repeat/crowd lines are spread out, not
    squashed to ~0 s."""
    from modules.timing import sanitize_timing
    # Four multi-syllable lines that the coupling put ~0.35 s apart.
    lines = tuple(
        _tl(i, "la la la la la", 100.0 + i * 0.35, 100.0 + i * 0.35 + 0.3,
            "high")
        for i in range(4)
    )
    out = sanitize_timing(lines, song_duration=240.0)
    spans = [ln.end - ln.start for ln in out]
    assert all(sp >= 0.99 for sp in spans)         # no longer 0.35 s
    # Monotonically rising and spread out (every start after the last).
    for a, b in zip(out, out[1:]):
        assert b.start >= a.end - 1e-6


def test_sanitize_timing_fade_out_fills_to_the_end() -> None:
    """B148: many unanchored tail lines fill the remaining time up to the
    end, instead of being crammed right after the last anchor."""
    from modules.timing import sanitize_timing
    # 1 anchor around 180 s, then 12 repeated fade-out lines (low),
    # song 222 s.
    lines = [_tl(0, "Nooit meer oerend hard samen", 178.0, 181.0, "high")]
    for i in range(1, 13):
        lines.append(_tl(i, "Want de Zangers oehoe oehoe", 181.0, 181.3,
                         "low"))
    out = sanitize_timing(tuple(lines), song_duration=222.0)
    # The last fade-out line ends near the end of the song, not already
    # around 193 s (crammed).
    assert out[-1].end > 205.0
    # Monotonic and no zero-length lines.
    for a, b in zip(out, out[1:]):
        assert b.start >= a.end - 1e-6
        assert b.end > b.start


def test_sanitize_timing_first_start_anchor() -> None:
    """B130: the first sentence is anchored on the onset."""
    from modules.timing import sanitize_timing
    lines = (_tl(0, "K zeg oeh vooraan samen", 28.0, 40.0),)
    out = sanitize_timing(lines, first_start=3.5)
    assert abs(out[0].start - 3.5) < 1e-6


def test_enforce_monotonic_no_zero_and_no_reorder() -> None:
    """B108: start<end, no zero-length line, no reordering."""
    from modules.timing import enforce_monotonic
    lines = (
        _tl(0, "een twee drie", 5.0, 7.0),
        _tl(1, "vier vijf zes", 3.0, 3.0),   # 0 span and before line 0
    )
    out = enforce_monotonic(lines)
    assert out[0].end > out[0].start
    assert out[1].start >= out[0].end        # not reordered
    assert out[1].end > out[1].start          # no zero-length line


def test_timing_report_flags() -> None:
    """B129: the report flags short lines and overlap."""
    from modules.timing import timing_report
    lines = (
        _tl(0, "een twee drie vier", 5.0, 8.0),
        _tl(1, "vijf zes", 6.0, 6.1),  # overlap + short
    )
    report = timing_report(lines, offset=-0.192, source_karaoke="demucs")
    assert "bron-karaoke=demucs" in report
    assert "KORT" in report
    assert "OVERLAP" in report


def test_reanchor_shifts_every_time(tmp_path: Path) -> None:
    """B98: reanchor shifts all syllable times by the difference."""
    from modules.timing import reanchor
    lines = (TextLine(0, "Kedeng Kedeng", False),)
    timed = generate_skeleton(lines, {0: (1.0, 2.0)})
    shifted = reanchor(timed, 0.192)
    assert shifted[0].syllables[0].start == round(
        timed[0].syllables[0].start + 0.192, 3)
    # A zero shift leaves everything alone.
    assert reanchor(timed, 0.0) == timed


def test_best_effort_syllable_level() -> None:
    """Equal syllable count: exact syllable times."""
    from modules.timing import best_effort_skeleton

    lines = (TextLine(0, "Zangers vooraan", False),)  # Zan-gers voor-aan
    original = [[("kedeng", 10.0, 11.0), ("kedeng", 11.0, 12.0)]]  # 4 syl
    timed, quality = best_effort_skeleton(lines, original)
    assert quality == {"syllable": 1, "word": 0, "sentence": 0}
    assert timed[0].syllables[0].start == pytest.approx(10.0)
    assert timed[0].syllables[1].start == pytest.approx(10.5)
    assert timed[0].end == pytest.approx(12.0)


def test_best_effort_word_level() -> None:
    """Equal word count: word times, syllables split inside them."""
    from modules.timing import best_effort_skeleton

    lines = (TextLine(0, "Zangers hey", False),)  # 3 syllables, 2 words
    original = [[("kedeng", 10.0, 11.0), ("oe", 11.5, 12.0)]]  # 3 syl? 2+1=3
    # 3 original syllables == 3 pieces: that would be syllable level;
    # force word level with a differing syllable count.
    original = [[("trein", 10.0, 11.0), ("oe", 11.5, 12.0)]]  # 1+1=2 syl
    timed, quality = best_effort_skeleton(lines, original)
    assert quality["word"] == 1
    # 'Zangers' (2 syllables) inside word 1: 10.0-10.5-11.0.
    assert timed[0].syllables[1].start == pytest.approx(10.5)
    assert timed[0].syllables[2].start == pytest.approx(11.5)  # 'hey'


def test_best_effort_sentence_level_and_projection() -> None:
    from modules.timing import best_effort_skeleton

    lines = (TextLine(0, "Heel veel meer woorden dan origineel", False),)
    original = [[("kort", 10.0, 12.0)]]
    timed, quality = best_effort_skeleton(
        lines, original, project=lambda t: t - 0.5)
    assert quality["sentence"] == 1
    assert timed[0].start == pytest.approx(9.5)  # projection applied
    assert timed[0].end == pytest.approx(11.5)


def test_best_effort_proportional_line_mapping() -> None:
    """More karaoke lines than lyric lines: split proportionally."""
    from modules.timing import best_effort_skeleton

    lines = tuple(TextLine(i, f"regel {i}", False) for i in range(4))
    original = [[("een", 10.0, 11.0)], [("twee", 50.0, 51.0)]]
    timed, _ = best_effort_skeleton(lines, original)
    assert timed[0].start < 12 and timed[1].start < 12   # first half
    assert timed[2].start >= 50 and timed[3].start >= 50  # second half


def test_fallback_even_never_zero() -> None:
    from modules.timing import fallback_even

    lines = tuple(TextLine(i, "la la", i % 2 == 0) for i in range(5))
    timed = fallback_even(lines, 120.0)
    assert all(line.end > line.start >= 8.0 for line in timed)
    starts = [line.start for line in timed]
    assert starts == sorted(starts)


def test_best_effort_splits_shared_lines_in_order() -> None:
    """Lines that share the same original line get consecutive slots of
    their own; order and completeness are guaranteed."""
    from modules.timing import best_effort_skeleton

    lines = tuple(TextLine(i, f"regel {i}", False) for i in range(4))
    original = [[("een", 10.0, 12.0)], [("twee", 50.0, 52.0)]]
    timed, _ = best_effort_skeleton(lines, original)
    assert [line.index for line in timed] == [0, 1, 2, 3]
    # Pair 0/1 shares 10-12, pair 2/3 shares 50-52 - split in sequence.
    assert timed[0].end == pytest.approx(timed[1].start)
    assert timed[0].start == pytest.approx(10.0)
    assert timed[1].end == pytest.approx(12.0)
    assert timed[2].start == pytest.approx(50.0)
    # Every line has a slot of its own (no duplicates).
    spans = [(line.start, line.end) for line in timed]
    assert len(set(spans)) == 4


def test_quality_is_saved_and_loaded(tmp_path: Path) -> None:
    from modules.timing import best_effort_skeleton, load_timing, save_timing

    lines = (TextLine(0, "Zangers vooraan", False),)
    original = [[("kedeng", 10.0, 11.0), ("kedeng", 11.0, 12.0)]]
    timed, _ = best_effort_skeleton(lines, original)
    assert timed[0].quality == "syllable"
    path = tmp_path / "timing.json"
    save_timing(timed, path)
    assert load_timing(path)[0].quality == "syllable"


def test_fallback_marks_even() -> None:
    from modules.timing import fallback_even

    timed = fallback_even((TextLine(0, "la", False),), 60.0)
    assert timed[0].quality == "even"


def test_snap_time() -> None:
    from modules.timing import snap_time

    # Within 10 px at 60 px/s (= 0.167 s): snap.
    assert snap_time(10.1, 10.0, 60.0) == 10.0
    # Outside that: no snap.
    assert snap_time(10.5, 10.0, 60.0) == 10.5
    # Zoomed in further (200 px/s): 0.1 s is 20 px then - no snap.
    assert snap_time(10.1, 10.0, 200.0) == 10.1
    # No playhead: the value is left alone.
    assert snap_time(10.1, None, 60.0) == 10.1


def test_clamp_span_prevents_overlap() -> None:
    from modules.timing import clamp_span

    blocked = [(10.0, 12.0), (15.0, 17.0)]
    # Moved up against the next block: trimmed back to the border.
    assert clamp_span(13.0, 16.0, blocked) == (13.0, 15.0)
    # Up against the previous block: the start moves along.
    assert clamp_span(11.0, 14.0, blocked) == (12.0, 14.0)
    # Free window: unchanged.
    assert clamp_span(12.5, 14.5, blocked) == (12.5, 14.5)
    # Right inside a block: jump to the nearest free gap.
    tight = [(10.0, 12.0), (12.1, 14.0)]
    jumped = clamp_span(11.9, 12.6, tight, min_length=0.2)
    assert jumped[0] >= 14.0  # behind the blocking block
    # Nothing blocking: unchanged.
    assert clamp_span(1.0, 2.0, []) == (1.0, 2.0)


def test_line_assignments() -> None:
    from modules.timing import line_assignments

    assert line_assignments(4, 4) == [0, 1, 2, 3]      # 1-to-1
    assert line_assignments(4, 2) == [0, 0, 1, 1]      # sharing
    assert line_assignments(2, 4) == [0, 2]            # skipping
    assert line_assignments(3, 1) == [0, 0, 0]


def test_remap_relative_follows_reference() -> None:
    from modules.timing import remap_relative

    # The reference moves 2 s: the karaoke sentence moves with it.
    assert remap_relative(11.0, 12.0, (10.0, 14.0), (12.0, 16.0)) == \
        pytest.approx((13.0, 14.0))
    # The reference doubles in length: the karaoke sentence stretches
    # along with it.
    start, end = remap_relative(11.0, 12.0, (10.0, 14.0), (10.0, 18.0))
    assert (start, end) == pytest.approx((12.0, 14.0))


def test_interpolate_spans_fills_gaps() -> None:
    from modules.timing import interpolate_spans

    # Lines 1 and 3 are coupled; 2 in between is interpolated.
    spans = [(10.0, 12.0), (None, None), (20.0, 22.0)]
    out = interpolate_spans(spans)
    assert out[0] == (10.0, 12.0)
    assert out[2] == (20.0, 22.0)
    assert 12.0 <= out[1][0] < out[1][1] <= 20.0  # neatly inside the gap
    # Two gaps in a row: divided evenly.
    spans2 = [(0.0, 2.0), (None, None), (None, None), (12.0, 14.0)]
    out2 = interpolate_spans(spans2)
    assert out2[1][0] == pytest.approx(2.0)
    assert out2[2][1] == pytest.approx(12.0)


def test_interpolate_spans_no_anchor() -> None:
    from modules.timing import interpolate_spans
    assert interpolate_spans([(None, None), (None, None)]) == []


def test_couple_timing_block_level() -> None:
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    # Block 0 = chorus (1 original line, reliable), 1 sung line.
    # Block 1 = verse: 1 original line but 2 karaoke lines -> spread.
    karaoke_blocks = [
        [TextLine(0, "G Z R", False, block=0),
         TextLine(1, "Waertje", True, block=0)],
        [TextLine(2, "Van alle kanten", False, block=1),
         TextLine(3, "komt men an", False, block=1)],
    ]
    original_blocks = [
        [(13.0, 15.0, True)],
        [(30.0, 34.0, True)],
    ]
    timed, quality, _ = couple_timing(karaoke_blocks, original_blocks)
    by_index = {t.index: t for t in timed}
    # Chorus 1-to-1 -> high, exactly on the original time.
    assert by_index[0].start == pytest.approx(13.0)
    assert by_index[0].end == pytest.approx(15.0)
    assert by_index[0].quality == "high"
    # Crowd 'Waertje' gets a short slot of its own and does not count.
    assert by_index[1].crowd is True
    # The verse is spread over 30-34 -> medium.
    assert by_index[2].start == pytest.approx(30.0)
    assert by_index[3].end == pytest.approx(34.0)
    assert by_index[2].quality == "medium"
    assert quality["high"] == 1 and quality["medium"] == 2


def test_couple_timing_interpolated_is_low() -> None:
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    karaoke_blocks = [[TextLine(0, "G Z R", False, block=0)]]
    original_blocks = [[(13.0, 28.0, False)]]  # interpolated chorus
    timed, quality, _ = couple_timing(karaoke_blocks, original_blocks)
    assert timed[0].quality == "low"
    assert quality["low"] == 1


def test_couple_1to1_equal_structure() -> None:
    """Equal number of blocks and lines -> pure 1-to-1, all high."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "aa", False, block=0), TextLine(1, "bb", False, block=0)],
          [TextLine(2, "cc", False, block=1)]]
    ob = [[(10.0, 11.0, True), (11.0, 12.0, True)], [(20.0, 21.0, True)]]
    timed, quality, mapping = couple_timing(kb, ob)
    assert quality == {"high": 3, "medium": 0, "low": 0}
    assert mapping == {0: 0, 1: 1, 2: 2}  # 1-to-1 over the flat list
    by = {t.index: t for t in timed}
    assert by[1].start == pytest.approx(11.0)
    assert by[2].start == pytest.approx(20.0)


def test_couple_unequal_blocks_fallback() -> None:
    """Unequal number of blocks -> proportional safety net, no crash."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "a", False, block=0)],
          [TextLine(1, "b", False, block=1)],
          [TextLine(2, "c", False, block=2)]]
    ob = [[(0.0, 10.0, True)], [(10.0, 20.0, True)]]  # 2 blocks
    timed, quality, mapping = couple_timing(kb, ob)
    assert len(timed) == 3
    assert set(mapping) == {0, 1, 2}
    assert all(0.0 <= t.start <= t.end for t in timed)


def test_couple_clamps_negative_and_duration() -> None:
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "a", False, block=0), TextLine(1, "b", False, block=0)]]
    ob = [[(0.0, 5.0, True), (5.0, 500.0, True)]]
    # A projection of -10 s would go negative; the duration bounds the end.
    timed, _, _ = couple_timing(kb, ob, duration=30.0,
                                project=lambda s: s - 10.0)
    assert all(t.start >= 0.0 for t in timed)
    assert all(t.end <= 30.0 for t in timed)


def test_interpolate_leading_not_stretched_to_zero() -> None:
    from modules.timing import interpolate_spans
    # One uncoupled line before the first anchor (duration ~1 s).
    out = interpolate_spans([(None, None), (10.0, 11.0)])
    assert out[0][1] == pytest.approx(10.0)      # ends on the anchor
    assert out[0][0] == pytest.approx(9.0)       # not 0, but ~its duration
    # A closing run: from the last anchor on, not up to the very end.
    out2 = interpolate_spans([(10.0, 12.0), (None, None)])
    assert out2[1][0] == pytest.approx(12.0)
    assert out2[1][1] == pytest.approx(14.0)     # +median duration (2 s)


def test_couple_over_original_words_preserves_rhythm() -> None:
    """B66: syllables follow the rhythm of the original words instead of
    being even; a long held word yields a longer syllable."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "aa bb", False, block=0)]]
    ob = [[(0.0, 3.0, True)]]
    # 'langlang' is held long (0-2.5), 'kort' is short (2.5-3.0).
    original_words = {0: [("langlang", 0.0, 2.5), ("kort", 2.5, 3.0)]}
    timed, _, _ = couple_timing(kb, ob, original_words=original_words)
    syl = timed[0].syllables
    first = syl[0].end - syl[0].start
    last = syl[-1].end - syl[-1].start
    assert first > last          # not even (then first would equal last)
    assert timed[0].start == pytest.approx(0.0, abs=0.05)


def test_couple_chant_snaps_to_beats() -> None:
    """B67: chant lines (low confidence) land on the (irregular) beats
    instead of being spread evenly."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "G Z R", False, block=0)]]
    ob = [[(0.0, 4.0, False)]]              # unreliable -> low
    beats = [0.0, 0.5, 2.5, 3.0, 4.0]       # deliberately irregular
    timed, quality, _ = couple_timing(kb, ob, beats=beats)
    assert quality["low"] == 1
    starts = [s.start for s in timed[0].syllables]
    # The beats pull the middle onset forward (even spacing would put it
    # around 1.33).
    assert starts[1] == pytest.approx(1.167, abs=0.1)


def test_crowd_section_block_is_coupled() -> None:
    """B75: a block that is entirely crowd couples to the original block
    (real timing, crowd_section=True) instead of getting short slots."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [
        [TextLine(0, "Rood Witte Zangers", False, block=0)],
        [TextLine(1, "La-la 1", True, block=1),
         TextLine(2, "La-la 2", True, block=1)],
    ]
    ob = [[(0.0, 3.0, True)], [(10.0, 14.0, True)]]
    timed, _, mapping = couple_timing(kb, ob)
    by = {t.index: t for t in timed}
    # The crowd chorus lines couple to the second original block...
    assert by[1].crowd is True and by[1].crowd_section is True
    assert by[1].start == pytest.approx(10.0)
    assert by[2].end == pytest.approx(14.0)
    # ... and they are in the mapping, so they really are coupled.
    assert 1 in mapping and 2 in mapping


def test_crowd_interjection_stays_short() -> None:
    """A crowd line in a mixed block stays a short interjection (no
    crowd_section)."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "G Z R", False, block=0),
           TextLine(1, "Waertje!", True, block=0)]]
    ob = [[(5.0, 7.0, True)]]
    timed, _, _ = couple_timing(kb, ob)
    by = {t.index: t for t in timed}
    assert by[1].crowd is True and by[1].crowd_section is False


def test_timing_save_load_preserves_crowd_section(tmp_path) -> None:
    """B80: crowd_section survives save/load (editor regression fix)."""
    from modules.timing import (Syllable, TimedLine, load_timing,
                                save_timing)
    line = TimedLine(0, "La la", True, (Syllable("La", 1.0, 1.5),
                                        Syllable(" la", 1.5, 2.0)),
                     quality="high", crowd_section=True)
    path = tmp_path / "timing.json"
    save_timing((line,), path)
    got = load_timing(path)[0]
    assert got.crowd is True and got.crowd_section is True


def test_couple_even_fallback_without_hints() -> None:
    """Without word or beat hints the even split still applies."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "aa bb", False, block=0)]]
    ob = [[(0.0, 4.0, True)]]
    timed, _, _ = couple_timing(kb, ob)
    syl = timed[0].syllables
    assert (syl[0].end - syl[0].start) == pytest.approx(
        syl[-1].end - syl[-1].start, abs=0.01)
