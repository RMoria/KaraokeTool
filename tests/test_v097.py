"""Tests for v0.97.0: B307, B308, B309 and B310.

B307 - the hallucination check also looks at the POSITION of a segment.
B308 - a hole in the transcription gets its own status.
B309 - the filtered out found words stay visible and can be coupled.
B310 - a la-la/na-na series is timed on where the singing really is.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from modules import pipeline, song_text
from modules import timing as timing_module
from modules.song_text import LyricWord
from modules.whisper import Segment, Word


# --------------------------------------------------------------------------
# B307: position-aware hallucination check
# --------------------------------------------------------------------------

def _lyrics(text: str) -> tuple[LyricWord, ...]:
    return tuple(LyricWord(index=i, text=w, line=0)
                 for i, w in enumerate(text.split()))


def _aligned(lyrics, coupling: dict[int, float]):
    """Minimal alignment: lyrics index -> start time (sim 0.95)."""
    from modules.song_text import AlignedWord
    return tuple(
        AlignedWord(lyrics[i],
                    coupling.get(i), None if i not in coupling
                    else coupling[i] + 0.4,
                    lyrics[i].text if i in coupling else None,
                    0.95 if i in coupling else 0.0)
        for i in range(len(lyrics)))


def test_position_window_lies_between_the_nearest_anchors() -> None:
    """The window runs from the last anchor before the segment to the
    first anchor after it - which is exactly what the lyrics do know:
    not the time, but the order."""
    lyrics = _lyrics(" ".join(f"w{i}" for i in range(40)))
    anchors = [(1.0, 5), (2.0, 10), (30.0, 35)]
    seg = Segment(0, "iets", 3.0, 4.0, ())
    lo, hi = pipeline._position_window(seg, anchors, len(lyrics))
    assert lo == 10 and hi == 35


def test_position_window_is_widened_to_a_minimum() -> None:
    """Two anchors close together give a window of one or two words;
    almost nothing matches that, and the check would then accuse every
    segment. So the window is widened."""
    lyrics = _lyrics(" ".join(f"w{i}" for i in range(40)))
    anchors = [(1.0, 20), (2.0, 21)]
    seg = Segment(0, "iets", 1.4, 1.6, ())
    lo, hi = pipeline._position_window(seg, anchors, len(lyrics))
    assert hi - lo + 1 >= pipeline._POSITION_WINDOW_MIN_WORDS


def test_position_window_stays_inside_the_lyrics() -> None:
    """Widening may never point outside the lyrics."""
    lyrics = _lyrics("een twee drie")
    seg = Segment(0, "iets", 9.0, 9.5, ())
    lo, hi = pipeline._position_window(seg, [(1.0, 1)], len(lyrics))
    assert lo == 0 and hi == len(lyrics) - 1


def test_hallucination_that_matches_song_wide_but_not_in_this_place() -> None:
    """The heart of B307: "SPANNENDE MUZIEK" in the outro scores a
    perfect match song-wide, because "muziek" really is sung halfway
    through the first verse. At the place where the segment sits that
    word occurs nowhere, and then it is a hallucination."""
    lyrics = _lyrics(
        "ik hou van dansen en muziek e viva espagna van oude trots en "
        "romantiek geef mij maar alle dagen zon espagna por favor ole "
        "lalaala lalalalalaa e viva espagna lalaala lalalalalaa")
    zon = next(i for i, w in enumerate(lyrics) if w.text == "zon")
    segments = (
        Segment(0, "geef mij maar alle dagen zon", 10.0, 12.0,
                (Word("zon", 11.5, 12.0, 0.95),)),
        Segment(1, "SPANNENDE MUZIEK", 40.0, 41.0,
                (Word("SPANNENDE", 40.0, 40.5, 0.31),
                 Word("MUZIEK", 40.5, 41.0, 0.42))),
    )
    aligned = _aligned(lyrics, {zon: 11.5})
    dropped: list = []
    kept = pipeline._filter_hallucinations_in_position(
        segments, lyrics, aligned, dropped_out=dropped)

    assert [s.index for s in kept] == [0]
    assert [s.text for s in dropped] == ["SPANNENDE MUZIEK"]
    # Song-wide the same segment would survive: "muziek" does occur in
    # the lyrics. That is precisely why the position is needed.
    assert pipeline._filter_hallucinations(segments, lyrics) == segments


def test_segment_with_a_coupling_is_never_thrown_away() -> None:
    """If the alignment coupled anything inside a segment, it is by
    definition not a hallucination - however badly the rest matches."""
    lyrics = _lyrics("geef mij maar alle dagen zon espagna por favor ole "
                     "lalaala lalalalalaa e viva espagna")
    segments = (Segment(0, "zon xyzzy plugh", 11.0, 12.0,
                        (Word("zon", 11.0, 11.3, 0.9),
                         Word("xyzzy", 11.3, 11.6, 0.1),
                         Word("plugh", 11.6, 12.0, 0.1))),)
    aligned = _aligned(lyrics, {5: 11.0})
    assert pipeline._filter_hallucinations_in_position(
        segments, lyrics, aligned) == segments


def test_high_confidence_protects_against_the_position_check() -> None:
    """The same safety net as in B285: if Whisper itself was sure of
    every word, we leave it standing - it may be an ad lib."""
    lyrics = _lyrics("geef mij maar alle dagen zon espagna por favor ole "
                     "lalaala lalalalalaa e viva espagna")
    segments = (Segment(0, "compleet andere tekst", 40.0, 41.0,
                        (Word("compleet", 40.0, 40.3, 0.99),
                         Word("andere", 40.3, 40.6, 0.98),
                         Word("tekst", 40.6, 41.0, 0.97))),)
    aligned = _aligned(lyrics, {5: 11.0})
    assert pipeline._filter_hallucinations_in_position(
        segments, lyrics, aligned) == segments


def test_without_anchors_the_position_check_does_nothing() -> None:
    """Without a single coupled word there is no position to determine,
    and then the check must not guess."""
    lyrics = _lyrics("geef mij maar alle dagen zon espagna por favor")
    segments = (Segment(0, "compleet anders", 40.0, 41.0,
                        (Word("compleet", 40.0, 40.5, 0.1),
                         Word("anders", 40.5, 41.0, 0.1))),)
    aligned = _aligned(lyrics, {})
    assert pipeline._filter_hallucinations_in_position(
        segments, lyrics, aligned) == segments


# --------------------------------------------------------------------------
# B308: a hole in the transcription is its own cause
# --------------------------------------------------------------------------

def test_transcription_gap_is_recognised() -> None:
    """Not one kept segment inside the anchor window and the window is
    long: then Whisper simply produced nothing here."""
    lyrics = _lyrics("een twee drie vier")
    aligned = _aligned(lyrics, {0: 1.0, 3: 30.0})
    segments = (Segment(0, "een", 1.0, 1.4, ()),
                Segment(1, "vier", 30.0, 30.4, ()))
    assert pipeline._word_in_transcription_gap(aligned, 1, segments) is True
    assert pipeline._word_in_transcription_gap(aligned, 2, segments) is True


def test_no_transcription_gap_when_there_is_text_after_all() -> None:
    """If the window does hold a kept segment, the gap is not the cause
    - the word simply matched nothing."""
    lyrics = _lyrics("een twee drie vier")
    aligned = _aligned(lyrics, {0: 1.0, 3: 30.0})
    segments = (Segment(0, "een", 1.0, 1.4, ()),
                Segment(1, "iets anders", 12.0, 14.0, ()),
                Segment(2, "vier", 30.0, 30.4, ()))
    assert pipeline._word_in_transcription_gap(aligned, 1, segments) is False


def test_a_short_hole_does_not_count_as_a_transcription_gap() -> None:
    """A normal pause between two lines is not a gap."""
    lyrics = _lyrics("een twee drie")
    aligned = _aligned(lyrics, {0: 1.0, 2: 2.0})
    segments = (Segment(0, "een", 1.0, 1.4, ()),
                Segment(1, "drie", 2.0, 2.4, ()))
    assert pipeline._word_in_transcription_gap(aligned, 1, segments) is False


def test_transcription_gap_outranks_hallucination(tmp_path: Path) -> None:
    """The real Viva case: after the last coupled word nothing comes out
    of Whisper for 27 seconds, with one filtered-out hallucination in
    between. The cause is the gap, not the hallucination - otherwise the
    editor points the user in the wrong direction."""
    lyrics = _lyrics("een twee drie vier vijf")
    aligned = _aligned(lyrics, {0: 1.0})
    clean = (Segment(0, "een", 1.0, 1.4, ()),)
    dropped = [Segment(1, "Heerlijke Heer", 20.0, 22.0, ())]
    assert pipeline._word_in_transcription_gap(aligned, 3, clean) is True
    assert pipeline._word_overlaps_dropped_segment(aligned, 3, dropped) is True


# --------------------------------------------------------------------------
# B309: filtered found words stay visible and can be coupled
# --------------------------------------------------------------------------

def test_full_transcript_contains_the_filtered_words() -> None:
    """The top row shows everything Whisper produced, with the positions
    of the filtered-out words alongside."""
    segments = (
        Segment(0, "een", 1.0, 1.5, (Word("een", 1.0, 1.5, 0.9),)),
        Segment(1, "MUZIEK", 2.0, 2.5, (Word("MUZIEK", 2.0, 2.5, 0.3),)),
        Segment(2, "twee", 3.0, 3.5, (Word("twee", 3.0, 3.5, 0.9),)),
    )
    clean = (segments[0], segments[2])
    transcript, filtered = pipeline._full_transcript(segments, clean)
    assert [w for w, _s, _e in transcript] == ["een", "MUZIEK", "twee"]
    assert filtered == [1]


def test_transcript_index_no_longer_shifts_through_the_filter() -> None:
    """The gain of B309: the number of a found word no longer depends on
    what the filter decides. "twee" sits at index 2, whether "MUZIEK" is
    thrown away or not."""
    segments = (
        Segment(0, "een", 1.0, 1.5, (Word("een", 1.0, 1.5, 0.9),)),
        Segment(1, "MUZIEK", 2.0, 2.5, (Word("MUZIEK", 2.0, 2.5, 0.3),)),
        Segment(2, "twee", 3.0, 3.5, (Word("twee", 3.0, 3.5, 0.9),)),
    )
    kept_all, _f = pipeline._full_transcript(segments, segments)
    kept_some, _f2 = pipeline._full_transcript(segments,
                                               (segments[0], segments[2]))
    assert kept_all == kept_some


@pytest.mark.parametrize("old,filtered,new", [
    (0, [1], 0),
    (1, [1], 2),
    (5, [1, 3], 7),
    (0, [], 0),
    (4, [0], 5),
])
def test_pin_index_conversion(old: int, filtered: list[int],
                              new: int) -> None:
    """Old pins counted the kept words only; every filtered position at
    or before the word shifts it one place along."""
    assert pipeline._shift_pin_index(old, filtered) == new


def test_creative_coupling_never_takes_a_filtered_word() -> None:
    """The automatic coupling must not pull in a filtered-out word after
    all; by hand the user may."""
    transcript = [("formidable", 0.0, 0.5), ("MUZIEK", 0.6, 1.0),
                  ("nous", 1.1, 1.5)]
    lyric_texts = ["fort", "minable", "nous"]
    targets = [[], [0], [2]]
    without_block = song_text.creative_couplings(lyric_texts, transcript,
                                                targets)
    with_block = song_text.creative_couplings(lyric_texts, transcript,
                                              targets, blocked={0})
    assert without_block[0] == [0]   # coupled when nothing is blocked
    assert with_block[0] == []       # not when it is

# --------------------------------------------------------------------------
# B310: timing a la-la/na-na series
# --------------------------------------------------------------------------

def test_spreading_over_sung_time_skips_the_silence() -> None:
    """Four lines over two singing windows of equal length with a silence
    in between: two lines per window, no line across the silence."""
    slots = timing_module.spread_over_active(4, [(0.0, 4.0), (10.0, 14.0)])
    assert slots == [(0.0, 2.0), (2.0, 4.0), (10.0, 12.0), (12.0, 14.0)]


def test_spreading_is_proportional_to_the_sung_duration() -> None:
    """A window that is three times as long also gets roughly three times
    as many lines."""
    slots = timing_module.spread_over_active(4, [(0.0, 9.0), (20.0, 23.0)])
    in_first = sum(1 for s, _e in slots if s < 10.0)
    assert len(slots) == 4 and in_first == 3


def test_spreading_ignores_a_sliver_of_a_window() -> None:
    """Cutting on the gap boundary often leaves a sliver of a window of a
    few hundredths. That must not swallow a whole line (which produced
    lines of 0.07 s)."""
    slots = timing_module.spread_over_active(2, [(0.0, 10.0), (10.0, 10.07)])
    assert len(slots) == 2
    assert all(e - s > 1.0 for s, e in slots)


def test_spreading_merges_windows_when_there_are_more_than_lines() -> None:
    """More singing windows than lines: the windows with the smallest
    pause between them are merged, so that precisely the clearest pauses
    survive."""
    slots = timing_module.spread_over_active(
        2, [(0.0, 2.0), (2.5, 4.0), (30.0, 34.0)])
    assert len(slots) == 2
    assert slots[0][0] == 0.0 and slots[1][0] == 30.0


def test_spreading_without_windows_yields_nothing() -> None:
    """Without usable windows the caller keeps its own interpolation;
    this function invents nothing."""
    assert timing_module.spread_over_active(3, []) == []
    assert timing_module.spread_over_active(0, [(0.0, 4.0)]) == []


def _pulse_stem(path: Path, pulses: list[float], duration: float,
               sample_rate: int = 22_050, length_s: float = 0.6) -> Path:
    """A vocal stem: short bursts of noise at the given moments."""
    from modules.audio import save_wav

    samples = np.zeros(int(duration * sample_rate), dtype=np.float32)
    rng = np.random.default_rng(7)
    for moment in pulses:
        start = int(moment * sample_rate)
        length = int(length_s * sample_rate)
        piece = rng.normal(0.0, 0.3, length).astype(np.float32)
        piece *= np.hanning(length).astype(np.float32)
        samples[start:start + length] += piece[:len(samples) - start]
    save_wav(path, samples[:, None], sample_rate)
    return path


def test_onsets_do_not_sit_on_top_of_each_other() -> None:
    """B310: when picking the strongest ``expected`` onsets they have to
    lie at least a fraction of the average distance apart. Without that
    demand two onsets of one and the same sung note (the attack and the
    body) ended up a few hundredths after each other, and one line got a
    slot of a fraction of a second. Really measured case: 180.14 s and
    180.21 s in "Lied I"."""
    from modules import rhythm

    # The two strongest onsets lie 0.07 s apart (the same note).
    onsets = [(180.14, 9.0), (180.21, 8.9), (184.07, 3.0), (188.46, 2.5)]
    picked = rhythm.pick_spread_onsets(onsets, 3, minimum_gap=2.0)
    assert [t for t, _s in picked] == [180.14, 184.07, 188.46]

    # Without a minimum distance the double attack beats a real pulse.
    without_gap = rhythm.pick_spread_onsets(onsets, 3, minimum_gap=0.0)
    assert [t for t, _s in without_gap] == [180.14, 180.21, 184.07]


def test_picking_onsets_never_yields_more_than_asked_for() -> None:
    """Even with a minimum distance of zero the count stays bounded."""
    from modules import rhythm

    onsets = [(float(i), float(10 - i)) for i in range(10)]
    assert len(rhythm.pick_spread_onsets(onsets, 4, 0.0)) == 4


def test_onset_separation_is_really_applied(tmp_path: Path) -> None:
    """End to end: on a real vocal stem the picked onsets lie at least
    the minimum distance apart."""
    from modules import rhythm

    pytest.importorskip("librosa")
    stem = _pulse_stem(tmp_path / "vocals.wav",
                      [0.5, 2.5, 4.5, 6.5, 8.5], 11.0)
    onsets = rhythm.energy_onsets(stem, 0.0, 11.0, expected=5)
    assert len(onsets) == 5
    distances = [b - a for a, b in zip(onsets, onsets[1:])]
    minimum = 11.0 / 5 * rhythm._ONSET_MIN_SEPARATION_RATIO
    assert min(distances) >= minimum


def _refine(stem: Path, lines, filled, reliable) -> None:
    """``_refine_with_vocals`` on a stand-in context with ``stem``."""
    import types

    context = types.SimpleNamespace(config=types.SimpleNamespace(
        advanced=types.SimpleNamespace(vocal_analysis=True)))
    original = pipeline.ensure_original_vocals
    pipeline.ensure_original_vocals = lambda _c: stem
    try:
        pipeline._refine_with_vocals(context, lines, filled, reliable, {})
    finally:
        pipeline.ensure_original_vocals = original


def test_tail_run_is_bounded_by_where_the_singing_stops(
        tmp_path: Path) -> None:
    """B310: a run of filler lines at the END of a song has no anchor
    behind it. Up to and including v0.96 the interpolation marched on
    with the median line duration, and with short coupled lines that is
    far too short: the whole la-la outro was then squeezed into the
    first seconds and the rest of the sung time stayed empty. Now the
    vocal stem decides where the last line ends.

    Exactly the Viva case: sung well past the point where the extended
    interpolation stopped.
    """
    from modules import rhythm

    pytest.importorskip("librosa")
    # Sung: pulses from 1 to just over 7 s, then silence until 20 s.
    stem = _pulse_stem(tmp_path / "vocals.wav", [1.0, 3.0, 5.0, 7.0], 20.0)
    lines = [0, 1, 2, 3, 4]
    # The coupled line lasts 0.7 s, so the interpolation runs on in
    # steps of 0.7 s up to 3.7 s - while there is singing until 7.6 s.
    filled = [(0.2, 0.9), (0.9, 1.6), (1.6, 2.3), (2.3, 3.0), (3.0, 3.7)]
    reliable = [True, False, False, False, False]
    _refine(stem, lines, filled, reliable)

    assert rhythm.is_available()
    assert filled[-1][1] > 6.0, filled          # the outro is covered
    assert all(e - s >= pipeline._FILLER_LINE_MIN_S for s, e in filled[1:]), \
        filled
    assert all(filled[i][0] <= filled[i + 1][0]
               for i in range(len(filled) - 1)), filled


def test_filler_lines_never_land_in_a_fraction_of_a_second(
        tmp_path: Path) -> None:
    """B310: when the onset detection finds pulses in a largely silent
    passage, that produced lines of a tenth of a second while the rest
    of the passage stayed empty. Such a placement is rejected and the
    lines are spread over the sung time instead."""
    from modules import rhythm

    pytest.importorskip("librosa")
    # Sung: 1-2.6 s. Just before the next anchor (4.0 s) there is a short
    # run-out, in which the onset detection sees a pulse. Three filler
    # lines on those three onsets give 3.94-4.0 s as the last line: a
    # slot of six hundredths.
    stem = _pulse_stem(tmp_path / "vocals.wav", [1.0, 2.0, 3.9], 5.0,
                      length_s=0.5)
    lines = [0, 1, 2, 3, 4]
    filled = [(0.2, 0.9), (0.9, 1.93), (1.93, 2.96), (2.96, 4.0),
              (4.0, 4.7)]
    reliable = [True, False, False, False, True]
    _refine(stem, lines, filled, reliable)

    assert rhythm.is_available()
    assert all(e - s >= pipeline._FILLER_LINE_MIN_S
               for s, e in filled[1:4]), filled
