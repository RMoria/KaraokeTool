"""Tests for v0.102.0: B329 up to and including B333.

From large to small. The sentence structure is put right first, and only
then refined at word and syllable level.

B329 - a repeated sentence is about equally long everywhere; a copy that
       sits far away from that is not a held sentence but a mistake.
B330 - an estimated line start moves to the vocal onset it belongs to.
B331 - two separate shouts close after each other are two onsets, not
       one merged window.
B332 - the phrase period is the unit of the sentence level: as an anchor
       check, and as the division between two anchors.
B333 - a measured line start wins from the minimum duration of the line
       before it; otherwise those nudges stack up over the whole song.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import timing as T  # noqa: E402
from modules.timing import Syllable, TimedLine  # noqa: E402

PERIOD = 3.6


def line(index: int, text: str, start: float, end: float,
         quality: str = "high", syllable_count: int = 6,
         crowd: bool = False) -> TimedLine:
    step = (end - start) / max(1, syllable_count)
    return TimedLine(
        index=index, text=text, crowd=crowd,
        syllables=tuple(Syllable(text=f"s{i}", start=start + i * step,
                                 end=start + (i + 1) * step)
                        for i in range(syllable_count)),
        quality=quality, block=0)


def steady_song(n: int = 12, period: float = PERIOD) -> list[TimedLine]:
    """A song that neatly starts a new line every ``period``."""
    return [line(i, f"Regel {i % 3}", 10.0 + i * period,
                 10.0 + i * period + period * 0.9)
            for i in range(n)]


# --------------------------------------------------------------------------
# B332: measuring the phrase period
# --------------------------------------------------------------------------

def test_the_period_of_a_steady_song() -> None:
    measured = T.phrase_period(steady_song())
    assert measured is not None
    assert math.isclose(measured, PERIOD, abs_tol=0.05)


def test_an_erratic_song_yields_no_period() -> None:
    """In a song with interjections between the full lines the spacing
    cannot be measured (measured: Lied N 50%). The whole mechanism
    then switches itself off and everything stays as it was."""
    lines = []
    t = 10.0
    for i, gap in enumerate([3.6, 0.9, 4.8, 1.1, 3.4, 0.8, 5.2, 1.3, 3.9]):
        lines.append(line(i, f"Regel {i}", t, t + gap * 0.8))
        t += gap
    assert T.phrase_period(lines) is None


def test_too_few_reliable_lines_yield_no_period() -> None:
    lines = steady_song(4)
    for i in (1, 2):
        lines[i] = line(i, lines[i].text, lines[i].start, lines[i].end,
                        quality="sentence")
    assert T.phrase_period(lines) is None


def test_crowd_lines_count_along_in_the_measurement() -> None:
    """In a parody a crowd line is often a full phrase in its own right.
    Filtering them out made the measurement worse (measured: MAD 6% ->
    50%)."""
    lines = steady_song()
    lines = [line(ln.index, ln.text, ln.start, ln.end,
                  crowd=(ln.index % 2 == 0))
             for ln in lines]
    assert T.phrase_period(lines) is not None


# --------------------------------------------------------------------------
# B329: the duration of identical sentences
# --------------------------------------------------------------------------

def test_the_reference_comes_from_measured_copies_only() -> None:
    """An estimate used as a reference confirms its own mistake."""
    lines = [line(0, "Refrein", 10.0, 13.6),
             line(1, "Refrein", 20.0, 23.6),
             line(2, "Refrein", 30.0, 33.6),
             line(3, "Refrein", 40.0, 49.0, quality="sentence")]
    ref = T.reference_durations(lines)
    median, _spread = ref["refrein"]
    assert math.isclose(median, 3.6, abs_tol=0.05)


def test_a_too_erratic_text_yields_no_reference() -> None:
    """A hook that is sometimes held and sometimes shouted ("Sunday
    Bloody Sunday": 0.10 up to 8.50 s) gives no usable median."""
    durations = [0.6, 4.1, 1.2, 5.3, 0.9]
    lines = [line(i, "Haak", 10.0 + i * 12, 10.0 + i * 12 + d)
             for i, d in enumerate(durations)]
    assert "haak" not in T.reference_durations(lines)


def test_fewer_than_three_times_does_not_count() -> None:
    lines = [line(0, "Eenmalig", 10.0, 13.6),
             line(1, "Eenmalig", 20.0, 23.6)]
    assert T.reference_durations(lines) == {}


# --------------------------------------------------------------------------
# B329/B332: which anchors are impossible?
# --------------------------------------------------------------------------

def test_a_double_length_is_pointed_out() -> None:
    """The measured case: "E viva Espagna" at 7.66 s against a median of
    3.60 - 2.13x. That single sentence accounted for 8.8 s of the 9.4 s
    of drift that sat in the whole tail after it."""
    lines = steady_song()
    lines[6] = line(6, lines[6].text, lines[6].start,
                    lines[6].start + 7.66)
    period = T.phrase_period(lines)
    suspect = T.implausible_and_overlong(lines, period,
                                     T.reference_durations(lines))[0]
    assert 6 in suspect


def test_a_flattened_sentence_is_pointed_out() -> None:
    """The other side: sentences of 0.02 and 0.90 s at the end, because
    everything before them stood too late."""
    lines = steady_song()
    lines[9] = line(9, lines[9].text, lines[9].start,
                    lines[9].start + 0.02)
    suspect = T.implausible_and_overlong(lines, T.phrase_period(lines),
                                     T.reference_durations(lines))[0]
    assert 9 in suspect


def test_a_short_but_real_line_is_left_standing() -> None:
    """A song also has lines that last half a phrase ("Rood Witte
    Zangers", 1.42 s at a period of 3.72). Those must not fall: cutting
    them loose cost 2.27 s of drift there."""
    lines = steady_song(period=3.72)
    lines[5] = line(5, "Korte tag", lines[5].start,
                    lines[5].start + 1.42)
    suspect = T.implausible_and_overlong(lines, T.phrase_period(lines),
                                     T.reference_durations(lines))[0]
    assert 5 not in suspect


def test_more_than_half_suspect_means_doing_nothing() -> None:
    """If nearly everything is suspect, then the reference is wrong and
    not the song. The timing then stays as it was."""
    lines = [line(i, "Regel", 10.0 + i * 3.6,
                  10.0 + i * 3.6 + (3.4 if i in (0, 1, 2, 3) else 0.1))
             for i in range(10)]
    suspect = T.implausible_and_overlong(lines, 3.6,
                                     T.reference_durations(lines))[0]
    assert suspect == set(), "six out of ten is too many to trust"


def test_without_a_period_the_duration_check_still_works() -> None:
    """The two checks catch different things. Without a measurable
    period the reference duration is what is left."""
    lines = [line(0, "Refrein", 10.0, 13.6),
             line(1, "Refrein", 25.0, 28.6),
             line(2, "Refrein", 44.0, 47.6),
             line(3, "Refrein", 60.0, 69.0)]
    suspect = T.implausible_and_overlong(lines, None,
                                     T.reference_durations(lines))[0]
    assert suspect == {3}


# --------------------------------------------------------------------------
# B332: the division between two anchors
# --------------------------------------------------------------------------

def test_the_division_is_per_phrase_and_not_per_syllable() -> None:
    """Between two anchors every line gets a phrase of its own. A line
    of four syllables therefore does not get a quarter of the time of a
    line of sixteen."""
    lines = steady_song(10)
    # lines 4..6 are estimated and differ strongly in length
    for i, n in ((4, 3), (5, 18), (6, 4)):
        lines[i] = line(i, f"Geschat {i}", lines[i].start, lines[i].end,
                        quality="sentence", syllable_count=n)
    out = T.sanitize_timing(lines, song_duration=80.0)
    spacings = [out[i + 1].start - out[i].start for i in range(3, 7)]
    assert max(spacings) - min(spacings) < 0.2, spacings


def test_one_wrong_anchor_no_longer_drags_the_rest_along() -> None:
    """The pattern of Lied S: an anchor that is too long halfway, then
    a run of estimated lines. The drift that followed from it grew to
    well over nine seconds."""
    lines = steady_song(14)
    lines[5] = line(5, lines[5].text, lines[5].start,
                    lines[5].start + 2 * PERIOD)
    for i in range(6, 12):
        lines[i] = line(i, lines[i].text, lines[i].start, lines[i].end,
                        quality="sentence")
    out = T.sanitize_timing(lines, song_duration=90.0)
    for i in range(6, 12):
        assert abs(out[i].start - lines[i].start) < 1.0, i


# --------------------------------------------------------------------------
# B330: putting a line on the vocal onset
# --------------------------------------------------------------------------

def test_an_estimated_line_moves_to_the_onset() -> None:
    lines = steady_song(6)
    lines[3] = line(3, "Geschat", lines[3].start, lines[3].end,
                    quality="sentence")
    target = lines[3].start + 0.7
    out = T.snap_to_onsets(lines, [target], PERIOD)
    assert math.isclose(out[3].start, target, abs_tol=0.01)


def test_a_measured_line_is_never_moved() -> None:
    lines = steady_song(6)
    out = T.snap_to_onsets(lines, [ln.start + 0.6 for ln in lines], PERIOD)
    assert [ln.start for ln in out] == [ln.start for ln in lines]


def test_a_moved_line_does_not_push_a_measured_line_forward() -> None:
    """The leak in the first version: the START was bounded, but the END
    of the moved line pushed the measured line after it away all the
    same - five lines that stood right went wrong that way."""
    lines = steady_song(6)
    lines[2] = line(2, "Geschat", lines[2].start, lines[2].end,
                    quality="sentence")
    fixed = lines[3].start
    out = T.snap_to_onsets(lines, [lines[3].start - 0.2], PERIOD)
    assert math.isclose(out[3].start, fixed, abs_tol=1e-6)
    assert out[2].end <= fixed + 1e-6


def test_an_onset_too_far_away_is_left_alone() -> None:
    """The reach stays well under half a phrase; any further and it
    would take the onset of its neighbouring line."""
    lines = steady_song(6)
    lines[3] = line(3, "Geschat", lines[3].start, lines[3].end,
                    quality="sentence")
    far = lines[3].start + 0.9 * PERIOD
    out = T.snap_to_onsets(lines, [far], PERIOD)
    assert math.isclose(out[3].start, lines[3].start, abs_tol=0.01)


def test_without_onsets_nothing_changes() -> None:
    lines = steady_song(6)
    assert T.snap_to_onsets(lines, [], PERIOD) == tuple(lines)


def test_the_order_is_kept() -> None:
    lines = steady_song(8)
    for i in (3, 4, 5):
        lines[i] = line(i, f"Geschat {i}", lines[i].start, lines[i].end,
                        quality="sentence")
    out = T.snap_to_onsets(lines, [lines[5].start - 0.5,
                                   lines[3].start + 0.4], PERIOD)
    starts = [ln.start for ln in out]
    assert starts == sorted(starts)


# --------------------------------------------------------------------------
# B331: two shouts are two onsets
# --------------------------------------------------------------------------

@pytest.fixture
def two_shouts(tmp_path: Path) -> Path:
    """Two bursts of 2.5 s with a short dip between them - the pattern
    of the two "Ole!" shouts in the intro."""
    numpy = pytest.importorskip("numpy")
    soundfile = pytest.importorskip("soundfile")
    sr = 22050
    duration = 8.0
    t = numpy.arange(int(duration * sr)) / sr
    tone = numpy.sin(2 * numpy.pi * 220 * t).astype("float32")
    envelope = numpy.zeros_like(tone)
    for start, end in ((1.6, 4.2), (4.4, 6.8)):
        mask = (t >= start) & (t <= end)
        envelope[mask] = 1.0
    path = tmp_path / "shouts.wav"
    soundfile.write(path, tone * envelope, sr)
    return path


def test_the_onsets_find_both_shouts(two_shouts: Path) -> None:
    from modules import rhythm

    if not rhythm.is_available():
        pytest.skip("librosa not available")
    found = rhythm.onsets(two_shouts)
    assert len(found) == 2, found
    assert abs(found[0] - 1.6) < 0.4
    assert abs(found[1] - 4.4) < 0.4


def test_the_active_windows_do_merge_them_together(two_shouts: Path) -> None:
    """Why the onsets were needed: the existing window bridges the dip
    and delivers one block of well over five seconds, over which the two
    lines were then spread evenly."""
    from modules import rhythm

    if not rhythm.is_available():
        pytest.skip("librosa not available")
    windows = rhythm.active_windows(two_shouts)
    assert len(windows) == 1
    assert windows[0][1] - windows[0][0] > 4.5


# --------------------------------------------------------------------------
# Coherence: the order of the steps
# --------------------------------------------------------------------------

def test_structure_first_and_only_then_refining() -> None:
    """Snapping before the structure takes the onset of the neighbouring
    line. On a crooked structure it made the outcome worse; on a
    straight structure it brings the line to within a fraction."""
    lines = steady_song(8)
    for i in (4, 5):
        lines[i] = line(i, f"Geschat {i}", lines[i].start + 2.4,
                        lines[i].end + 2.4, quality="sentence")
    onsets = [10.0 + i * PERIOD for i in range(8)]

    crooked = T.snap_to_onsets(lines, onsets, PERIOD)
    straight = T.snap_to_onsets(
        T.sanitize_timing(lines, song_duration=60.0), onsets, PERIOD)

    truth = [10.0 + i * PERIOD for i in range(8)]
    error_crooked = sum(abs(ln.start - w)
                        for ln, w in zip(crooked, truth))
    error_straight = sum(abs(ln.start - w)
                         for ln, w in zip(straight, truth))
    assert error_straight < error_crooked


# --------------------------------------------------------------------------
# B333: a measured start wins from the minimum duration before it
# --------------------------------------------------------------------------

def test_a_too_short_sentence_does_not_push_the_next_one_forward() -> None:
    """The sentence before it has to last at least ~1 s, but that may
    not come at the cost of the MEASURED start of the sentence after."""
    lines = steady_song(6)
    short = line(2, "Kort", lines[2].start, lines[2].start + 0.2)
    lines[2] = short
    out = T.sanitize_timing(lines, song_duration=60.0)
    assert math.isclose(out[3].start, lines[3].start, abs_tol=0.01)


def test_the_nudges_do_not_stack_up_over_the_song() -> None:
    """The measured case: six short sentences spread over a song let the
    rest run up to 8.6 s late, while the coupling itself was right to
    within 0.34 s."""
    lines = steady_song(24)
    for i in (2, 5, 9, 13, 17, 21):
        lines[i] = line(i, "Kort", lines[i].start, lines[i].start + 0.25)
    out = T.sanitize_timing(lines, song_duration=150.0)
    deviations = [abs(out[i].start - lines[i].start) for i in range(24)]
    assert max(deviations) < 0.6, max(deviations)


def test_an_estimated_line_may_still_shift() -> None:
    """Only a MEASURED start is untouchable; an estimate may still give
    way to the line before it."""
    lines = steady_song(6)
    lines[2] = line(2, "Lang", lines[2].start, lines[2].start + 6.0)
    lines[3] = line(3, "Geschat", lines[3].start, lines[3].end,
                    quality="sentence")
    out = T.sanitize_timing(lines, song_duration=60.0)
    assert out[3].start >= out[2].end - 1e-6
