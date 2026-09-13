"""Self-checks on word and syllable timing (B363).

At sentence level there is a hand-corrected truth: ``timing.json`` holds
line starts the user set himself, and the ruler measures against those.
Below the line that truth stops. Dragging a line scales its syllables
along linearly, so the syllable times in ``timing.json`` are a
CONSEQUENCE of the model and not a judgement about it. Measuring the
model against them would be measuring the model against itself.

That does not mean nothing can be measured. Four kinds of check here,
none of which needs a hand-set syllable:

1. **Against the measured word boundaries.** The forced alignment
   (WhisperX on the vocal stem) puts a start and an end on every word,
   independent of the syllable model, and those times are already in the
   transcription cache. A syllable that crosses a measured word boundary
   is demonstrably wrong. This is the closest thing to a truth we have,
   and it was lying there unused.
2. **Against the shape.** Some things are wrong regardless of the audio:
   syllables out of order, overlapping, gaps within a word, a syllable
   of eight milliseconds, more than nine syllables per second (nobody
   sings that), a held syllable that is not the last of its word.
3. **Against the audio.** The energy of the vocal stem shows where the
   singing is. A word in a measured silence is wrong, and the distance
   from each start to the nearest onset says something about how well
   the timing follows the singing.
4. **Against itself.** A line that is sung twice should have roughly the
   same internal rhythm both times. That says nothing about what is
   right, but it does distinguish a stable model from a wobbly one - and
   it needs no truth at all.

What these four have in common: they measure agreement, not
correctness. A model can agree beautifully with the audio and still put
the syllables in the wrong place. To calibrate them a small hand-set
sample is needed, and the timing editor cannot do that yet (it drags
lines, not syllables). Until then these are indicators, and they are
reported as such.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: Shorter than this nobody sings a syllable; below it, it is an
#: artefact of dividing up rather than a measurement.
MIN_SYLLABLE_S = 0.05
#: Syllables per second above which a line is not humanly sung. Speech
#: sits around 4 to 7 per second, singing lower; nine leaves room.
MAX_SYLLABLE_RATE = 9.0
#: A word start counts as "on an onset" within this distance.
ONSET_NEAR_S = 0.15


@dataclass
class Findings:
    """Countings over one project; all "lower is better"."""

    lines: int = 0
    words: int = 0
    syllables: int = 0
    #: Shape (2)
    out_of_order: int = 0
    overlapping: int = 0
    gaps_in_word: int = 0
    too_short: int = 0
    too_fast_lines: int = 0
    held_not_last: int = 0
    #: Audio (3)
    without_duration: int = 0
    in_silence: int = 0
    onset_distances: list = field(default_factory=list)
    #: Consistency over repetitions (4)
    repeat_pairs: int = 0
    repeat_divergence: list = field(default_factory=list)
    #: B435: syllables without a moment of their own, and words that are
    #: squeezed below what the code itself calls a minimum. Cheap to
    #: count and exactly the kind of nonsense a model can produce while
    #: the yardstick - which only looks at line STARTS - reports nothing.
    flat: int = 0
    stacked: int = 0
    cramped_words: int = 0
    #: B500: between the sentences. Everything above looks INSIDE one
    #: sentence; two sentences over each other or a sentence of zero
    #: length was measured by nothing, while that is exactly what you
    #: see in the editor and in the picture.
    empty_lines: int = 0
    overlapping_lines: int = 0
    lines_out_of_order: int = 0
    #: B380: lines whose duration is far from the same line elsewhere.
    #: "high quality" only says the coupling was one-to-one, never that
    #: the duration makes sense - one project had a line of 19.42 s
    #: labelled high while the same line runs 5.4 s elsewhere.
    odd_duration: int = 0

    def as_dict(self) -> dict:
        return {
            "lines": self.lines, "words": self.words,
            "syllables": self.syllables,
            "out_of_order": self.out_of_order,
            "flat": self.flat,
            "stacked": self.stacked,
            "cramped_words": self.cramped_words,
            "overlapping": self.overlapping,
            "gaps_in_word": self.gaps_in_word,
            "too_short": self.too_short,
            "too_fast_lines": self.too_fast_lines,
            "held_not_last": self.held_not_last,
            "without_duration": self.without_duration,
            "in_silence": self.in_silence,
            "onset_distance": (statistics.median(self.onset_distances)
                               if self.onset_distances else 0.0),
            "empty_lines": self.empty_lines,
            "overlapping_lines": self.overlapping_lines,
            "lines_out_of_order": self.lines_out_of_order,
            "odd_duration": self.odd_duration,
            "repeat_pairs": self.repeat_pairs,
            "repeat_divergence": (statistics.median(self.repeat_divergence)
                                  if self.repeat_divergence else 0.0),
        }


def _value(item, name):
    return item[name] if isinstance(item, dict) else getattr(item, name)


#: A syllable shorter than this has no moment of its own (B435).
FLAT_S = 0.001


def sanity(lines) -> dict:
    """The cheap checks only - no audio, no context (B435).

    Meant to run BETWEEN model measurements. The yardstick weighs line
    starts, and a model can leave those alone while wrecking everything
    inside the line: syllables of length zero, a whole word on one
    instant, sentences running backwards. That stays invisible in an
    average, and it is exactly what a user notices in the video.

    Deliberately free of the audio checks: this has to be cheap enough
    to run a few hundred times in a row.
    """
    found = Findings()
    shape_checks(lines, found)
    return {"lines": found.lines, "syllables": found.syllables,
            "flat": found.flat, "stacked": found.stacked,
            "cramped_words": found.cramped_words,
            "out_of_order": found.out_of_order,
            "overlapping": found.overlapping,
            "gaps_in_word": found.gaps_in_word}


def broken(counts: dict) -> bool:
    """Is this timing structurally wrong? (B435)"""
    return any(int(counts.get(name, 0)) > 0
               for name in ("flat", "stacked", "out_of_order",
                            "overlapping"))


def shape_checks(lines, found: Findings) -> None:
    """Everything that is wrong regardless of the audio (kind 2)."""
    from . import timing as timing_module

    for line in lines:
        syllables = list(_value(line, "syllables"))
        if not syllables:
            continue
        found.lines += 1
        found.syllables += len(syllables)
        previous_end = None
        previous_start = None
        for syllable in syllables:
            start = float(_value(syllable, "start"))
            end = float(_value(syllable, "end"))
            if end < start:
                found.out_of_order += 1
            elif end - start < MIN_SYLLABLE_S:
                found.too_short += 1
            if end - start < FLAT_S:                       # B435
                found.flat += 1
            if previous_start is not None \
                    and abs(start - previous_start) < FLAT_S:
                found.stacked += 1
            if previous_end is not None and start < previous_end - 1e-6:
                found.overlapping += 1
            previous_end = end
            previous_start = start
        span = (float(_value(syllables[-1], "end"))
                - float(_value(syllables[0], "start")))
        if span > 0 and len(syllables) / span > MAX_SYLLABLE_RATE:
            found.too_fast_lines += 1
        # Gaps INSIDE a word: between words a gap is allowed (a breath
        # pause), inside a word it is not - that is a word falling apart.
        index = 0
        for _text, _start, _end in timing_module.word_spans(syllables):
            eigen = []
            while index < len(syllables):
                eigen.append(syllables[index])
                index += 1
                if index < len(syllables) and \
                        str(_value(syllables[index], "text")).startswith(" "):
                    break
            for first, second in zip(eigen, eigen[1:]):
                if float(_value(second, "start")) \
                        - float(_value(first, "end")) > 0.02:
                    found.gaps_in_word += 1
            if eigen:
                breedte = (float(_value(eigen[-1], "end"))
                           - float(_value(eigen[0], "start")))
                if breedte < len(eigen) * MIN_SYLLABLE_S:   # B435
                    found.cramped_words += 1
            held = [n for n, s in enumerate(eigen)
                    if bool(_value(s, "held"))]
            if held and max(held) != len(eigen) - 1:
                found.held_not_last += 1


def line_checks(lines) -> dict[str, list]:
    """Checks BETWEEN the lines (B500).

    Everything in ``shape_checks`` looks inside one sentence; nothing
    looked at the sentences among themselves, while exactly that is what
    shows up in the editor and in the picture: two sentences over each
    other, a sentence of zero length, or two that have swapped places.

    Crowd lines are allowed to overlap - a shout sounds at the same time
    as the singing (B346) - and so is a line that is switched off.
    """
    empty: list = []
    overlapping: list = []
    out_of_order: list = []
    previous = None
    for line in lines:
        index = getattr(line, "index", None)
        start = float(getattr(line, "start", 0.0))
        end = float(getattr(line, "end", 0.0))
        if _may_overlap(line):
            # Such a line may lie over its neighbour, and it does not
            # count as "the previous one" either - otherwise it would
            # make every line after it look out of order.
            continue
        if end <= start:
            empty.append(index)
        if previous is not None:
            prev_index, prev_start, prev_end = previous
            if start < prev_start:
                out_of_order.append((prev_index, index))
            elif start < prev_end - 0.002:
                overlapping.append((prev_index, index,
                                    round(prev_end - start, 3)))
        previous = (index, start, end)
    return {"empty_lines": empty, "overlapping_lines": overlapping,
            "lines_out_of_order": out_of_order}


def _may_overlap(line) -> bool:
    """A crowd line, a switched-off line and a whole background line may
    lie over their neighbours (B346/B180/B510).

    Background vocals CAN sound at the same time as another sentence -
    they do not have to, but the moment they do, an overlap is the
    correct picture and not a finding. Up to v0.145.0 such a line was
    switched off by default and fell under ``disabled``; now that it is
    a line like any other in the editor it needs its own exemption.
    """
    return bool(getattr(line, "crowd", False)
                or getattr(line, "disabled", False)
                or getattr(line, "bg", False))


def audio_checks(context, lines, found: Findings) -> None:
    """Words without duration, in a silence, and their onset distance."""
    from . import pipeline, rhythm
    from . import timing as timing_module

    windows = pipeline._vocal_windows(context)
    stem = pipeline.ensure_original_vocals(context)
    onsets = sorted(rhythm.onsets(stem)) if stem is not None else []
    for line in lines:
        syllables = list(_value(line, "syllables"))
        if not syllables:
            continue
        line_start = float(_value(syllables[0], "start"))
        line_end = float(_value(syllables[-1], "end"))
        own = [(a, b) for a, b in windows if b > line_start and a < line_end]
        for _text, start, end in timing_module.word_spans(syllables):
            found.words += 1
            if end - start < 0.001:
                found.without_duration += 1
            if own and not any(a - 0.05 <= start <= b + 0.05
                               for a, b in own):
                found.in_silence += 1
            if onsets:
                found.onset_distances.append(
                    min(abs(start - moment) for moment in onsets))


def repetition_consistency(lines, found: Findings) -> None:
    """Does the same text get the same internal rhythm twice? (kind 4)

    Per line the syllable durations are normalised to a fraction of the
    line, so that a slower repetition does not count as a difference -
    only the DIVISION counts. The divergence is the mean absolute
    difference between two profiles of the same length.
    """
    by_text: dict[str, list[list[float]]] = {}
    for line in lines:
        syllables = list(_value(line, "syllables"))
        if len(syllables) < 2:
            continue
        text = " ".join(str(_value(s, "text")).strip().lower()
                        for s in syllables).strip()
        span = (float(_value(syllables[-1], "end"))
                - float(_value(syllables[0], "start")))
        if span <= 0:
            continue
        profile = [(float(_value(s, "end")) - float(_value(s, "start"))) / span
                   for s in syllables]
        by_text.setdefault(text, []).append(profile)
    for profiles in by_text.values():
        for first, second in zip(profiles, profiles[1:]):
            if len(first) != len(second):
                continue
            found.repeat_pairs += 1
            found.repeat_divergence.append(
                sum(abs(a - b) for a, b in zip(first, second)) / len(first))


def duration_outliers(lines, found: Findings) -> None:
    """Lines that take far longer or shorter than the same line elsewhere.

    Costs nothing - the comparison is with the song itself - and it
    catches what no quality label does: a line marked "high" (coupled
    one-to-one) that nevertheless spans nineteen seconds where the same
    text runs five somewhere else.
    """
    from . import timing_template

    by_key: dict[str, list[float]] = {}
    for line in lines:
        syllables = list(_value(line, "syllables"))
        if not syllables:
            continue
        span = (float(_value(syllables[-1], "end"))
                - float(_value(syllables[0], "start")))
        if span > 0:
            by_key.setdefault(timing_template.line_key(
                _value(line, "text")), []).append(span)
    for spans in by_key.values():
        if len(spans) < 2:
            continue
        middle = statistics.median(spans)
        if middle <= 0:
            continue
        found.odd_duration += sum(
            1 for s in spans
            if s / middle > timing_template.MAX_FACTOR
            or middle / s > timing_template.MAX_FACTOR)


def inspect(context, lines) -> dict:
    """Every check over one project's timed lines.

    B525: there were four kinds; the one against the measured word
    boundaries of the ORIGINAL is gone, because in a parody those are
    different words.
    """
    found = Findings()
    shape_checks(lines, found)
    try:
        audio_checks(context, lines, found)
    except Exception:  # noqa: BLE001 - aanwijzing mag falen, meting niet
        from .translations import t
        logger.exception(t("log_syllable_checks_failed"))
    repetition_consistency(lines, found)
    duration_outliers(lines, found)
    between = line_checks(lines)                              # B500
    found.empty_lines = len(between["empty_lines"])
    found.overlapping_lines = len(between["overlapping_lines"])
    found.lines_out_of_order = len(between["lines_out_of_order"])
    return found.as_dict()
