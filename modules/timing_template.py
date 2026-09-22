"""Time a line from the same line elsewhere in the song (B380).

The outro of a song is where the timing falls apart, and the measurement
says so plainly: over eleven projects with hand-corrected timing, unique
lines carry 0.48 s of error and repeated lines 1.89 s. The end of a song
is where repetitions pile up.

The cause is not a bad model but missing input. On one project the vocal
stem shows 36 seconds of singing after the last verse while Whisper
produces two mangled fragments; twelve lyrics lines then have to be
placed with essentially no anchor, and the coupling stretches one line
over nineteen seconds and crushes nine others below half a second.

The user's idea, and it is a good one: whatever is sung there is almost
always a repetition of something sung earlier - a chorus line, a refrain.
And *that* copy was heard well. So do not guess: take the measurement
from the place where it worked.

How well that works is itself measured. On "Lied K" the
line "Don't stand, don't stand so, don't stand so close to me" is
transcribed cleanly four times; the two eleven-word instances run 5.38
and 5.40 seconds. Two independent measurements of the same line, two
hundredths apart. That is not an estimate, it is a template with a known
spread - and 36.3 seconds of measured singing divided by 5.39 gives
almost exactly the six repetitions the lyrics say are there.

Three sources, in order of preference:

1. the same line elsewhere, well timed - duration AND internal profile;
2. the same words individually, well timed elsewhere;
3. the median syllable duration of this song, over well-timed lines.

The internal profile matters as much as the duration. A line is not sung
at an even pace, and spreading syllables evenly over a window is exactly
what makes the current fallback sound mechanical. Reusing the profile
keeps the rhythm of the line the singer actually used.

The check on this model already existed before the model did:
``timing_checks.repetition_consistency`` measures how differently the
same line is divided across two occurrences. This model makes those
divisions equal on purpose, so that number is the direct verification
that it has not overshot.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, replace

logger = logging.getLogger(__name__)

#: A line is suspect when its duration deviates from the template by more
#: than this factor. Deliberately wide: singing genuinely varies, and a
#: line that runs 30% longer in a fade-out is not broken. What we are
#: after are the outliers - nineteen seconds where five is normal, or
#: three tenths where five is normal.
MAX_FACTOR = 2.0

#: Below this a line is too short to be sung at all, whatever the
#: template says. A line of nine syllables in 0.3 s is not a measurement.
MIN_SYLLABLE_S = 0.12

#: How many well-timed instances a template needs. One is allowed - one
#: measurement beats no measurement - but two agreeing instances are
#: reported as far more reliable.
MIN_INSTANCES = 1

#: Above this relative spread the instances disagree too much to be
#: called a measurement, and the template is not used. This is the guard
#: that had to be learned the hard way: without it the broken lines end
#: up in their own template. On one project twelve instances of the same
#: line gave a spread of 1.38 - six well-timed choruses and six crushed
#: outro lines, averaged into a number that described neither.
MAX_SPREAD = 0.35

#: Share of a line that has to fall inside measured singing before it may
#: serve as a template. A line stretched across silence is a symptom, not
#: a measurement - and it is exactly those we want to repair.
MIN_ON_SINGING = 0.8

#: Qualities that count as "well timed" and may serve as a template.
#: Two vocabularies meet here: ``couple_timing`` labels a line
#: high/medium/low (how sure the sentence coupling is) and the syllable
#: timing labels it syllable/word/sentence/even. A template may come
#: from either, as long as it is the good end of that scale.
GOOD_QUALITY = ("syllable", "word", "high")


@dataclass(frozen=True)
class Template:
    """A measured line: how long it takes and how it divides."""

    key: str
    duration: float
    #: Relative duration per syllable, summing to 1.0.
    profile: tuple[float, ...]
    instances: int
    #: Spread between the instances (0.0 with a single one). Small spread
    #: means two independent measurements agreed.
    spread: float

    @property
    def reliable(self) -> bool:
        return self.instances >= 2 and self.spread <= 0.25


def line_key(text: str) -> str:
    """The text of a line, normalised, as the template key."""
    from . import cluster as cluster_module

    return cluster_module.phonetic_key(" ".join(str(text).split()))


def _span(line) -> float:
    syllables = line.syllables
    if not syllables:
        return 0.0
    return float(syllables[-1].end) - float(syllables[0].start)


def _profile(line) -> tuple[float, ...]:
    """The relative duration per syllable, normalised to 1.0."""
    syllables = line.syllables
    total = _span(line)
    if total <= 0 or not syllables:
        return ()
    parts = [max(0.0, float(s.end) - float(s.start)) / total
             for s in syllables]
    total = sum(parts)
    if total <= 0:
        return tuple(1.0 / len(syllables) for _ in syllables)
    return tuple(p / total for p in parts)


def _on_singing_share(line, windows) -> float:
    """Which share of this line falls inside measured singing."""
    if not windows:
        return 1.0                       # no measurement, no opinion
    start = float(line.syllables[0].start)
    end = float(line.syllables[-1].end)
    if end <= start:
        return 0.0
    inside = sum(max(0.0, min(end, high) - max(start, low))
                 for low, high in windows)
    return inside / (end - start)


def collect(lines, windows=()) -> dict[str, Template]:
    """Build a template per line text, from the well-timed instances.

    Only instances that are themselves credible take part: good quality,
    a real duration, and standing on measured singing. That last one is
    the important filter - the lines we want to repair are precisely the
    ones stretched across silence, and without it they end up in their
    own template.
    """
    per_key: dict[str, list] = {}
    for line in lines:
        if line.quality not in GOOD_QUALITY or not line.syllables:
            continue
        duration = _span(line)
        if duration <= 0:
            continue
        if duration / len(line.syllables) < MIN_SYLLABLE_S:
            continue
        if _on_singing_share(line, windows) < MIN_ON_SINGING:
            continue
        per_key.setdefault(line_key(line.text), []).append(line)

    templates: dict[str, Template] = {}
    for key, instances in per_key.items():
        if not key or len(instances) < MIN_INSTANCES:
            continue
        # Only instances with the same number of syllables can share a
        # profile; take the most common count.
        counts = [len(i.syllables) for i in instances]
        usual = max(set(counts), key=counts.count)
        matching = [i for i in instances if len(i.syllables) == usual]
        durations = [_span(i) for i in matching]
        middle = statistics.median(durations)
        spread = ((max(durations) - min(durations)) / middle
                  if len(durations) > 1 and middle > 0 else 0.0)
        profiles = [_profile(i) for i in matching]
        averaged = tuple(statistics.mean(p[n] for p in profiles)
                          for n in range(usual)) if profiles else ()
        templates[key] = Template(key=key, duration=middle,
                                  profile=averaged, instances=len(matching),
                                  spread=spread)
    return templates


def implausible(line, template: Template | None) -> str:
    """Why this line's timing cannot be right - or an empty string.

    Separate from the repair so that the reason can be reported and
    tested; a line that is only "a bit off" is deliberately left alone.

    The reason travels into the log window as the ``%s`` of
    ``log_template_retimed``, so the user reads it - which is why it goes
    through ``translations`` and is not a literal here.
    """
    from .translations import t

    syllables = line.syllables
    if not syllables:
        return ""
    duration = _span(line)
    if duration <= 0:
        return t("template_no_duration")
    if duration / len(syllables) < MIN_SYLLABLE_S:
        return t("template_too_fast")
    if template is None or template.duration <= 0:
        return ""
    factor = duration / template.duration
    if factor > MAX_FACTOR:
        return t("template_longer") % factor
    if factor < 1.0 / MAX_FACTOR:
        return t("template_shorter") % (1 / factor)
    return ""


def fit(line, template: Template, start: float, end: float):
    """Put the template profile between ``start`` and ``end``."""
    syllables = list(line.syllables)
    profile = template.profile
    if not syllables or len(profile) != len(syllables) or end <= start:
        return line
    total = end - start
    moment = start
    fitted = []
    for syllable, share in zip(syllables, profile):
        duration = total * share
        fitted.append(replace(syllable, start=round(moment, 3),
                             end=round(moment + duration, 3)))
        moment += duration
    return replace(line, syllables=tuple(fitted))


def repair(lines, windows, templates: dict[str, Template] | None = None):
    """Re-time lines whose timing cannot be right, from a template.

    ``windows`` are the measured sung stretches; a repaired line is
    placed inside the window it overlaps most, so the result stays on
    the singing instead of on the coupling's guess.
    """
    from .translations import t

    lines = list(lines)
    if templates is None:
        templates = collect(lines, windows)
    if not templates:
        return tuple(lines)

    repaired = 0
    for index, line in enumerate(lines):
        template = templates.get(line_key(line.text))
        if template is not None and template.spread > MAX_SPREAD:
            continue                     # the instances disagree
        reason = implausible(line, template)
        if not reason or template is None or not template.profile:
            continue
        if len(template.profile) != len(line.syllables):
            continue
        start = float(line.syllables[0].start)
        line_end = float(line.syllables[-1].end)
        window = _best_window(windows, start, line_end)
        if window is None:
            new_end = start + template.duration
        else:
            low, high = window
            new_start = max(low, min(start, high - template.duration))
            start = new_start if new_start >= low else low
            new_end = min(high, start + template.duration)
            if new_end - start < template.duration * 0.5:
                new_end = start + template.duration
        lines[index] = fit(line, template, start, new_end)
        repaired += 1
        logger.info(t("log_template_retimed"), line.text[:40], reason,
                    template.duration)
    if repaired:
        logger.info(t("log_template_total"), repaired)
    return tuple(lines)


def _best_window(windows, start: float, end: float):
    """The measured window this line overlaps most, or ``None``."""
    best, most = None, 0.0
    for low, high in windows or ():
        overlap = min(end, high) - max(start, low)
        if overlap > most:
            best, most = (low, high), overlap
    return best
