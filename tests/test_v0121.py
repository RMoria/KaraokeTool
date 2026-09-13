"""Tests for v0.121.0: B380 (template timing) - built and switched off.

The idea is the user's and it is sound: what is sung in an outro is
almost always a repetition of something sung earlier, and *that* copy was
heard well - so do not guess, reuse the measurement. On one project the
same line is transcribed cleanly four times and the two eleven-word
instances run 5.38 and 5.40 seconds: two independent measurements two
hundredths apart.

The machinery below does exactly that and is correct in isolation. What
it does NOT do yet is source those templates from the right place. It
builds them from the output of the sentence coupling, and in an outro
that is precisely the step that is broken: on "Lied K"
four "instances" came out at exactly 1.00 s - not a measurement but the
lower bound from ``sanitize_timing`` - and nine others had a spread of
1.48. Repairing on that is worse than doing nothing.

So the model ships switched OFF, with the reason recorded in the
register, per the working agreement: an idea that turns out not to be
worth anything is switched off and not removed, and the big trial keeps
measuring it every run. The templates have to come from the transcription
times via the coupling map, and that is the next round.

These tests therefore pin two things: the machinery is right, and the
model is off for a stated reason.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import model_register, timing_checks  # noqa: E402
from modules import timing_template as template  # noqa: E402


@dataclass(frozen=True)
class FakeSyllable:
    text: str
    start: float
    end: float
    held: bool = False


@dataclass(frozen=True)
class FakeLine:
    text: str
    syllables: tuple
    quality: str = "high"


def _line(text: str, start: float, parts, quality: str = "high"):
    syllables, moment = [], start
    for word, duration in parts:
        syllables.append(FakeSyllable(word, round(moment, 3),
                                      round(moment + duration, 3)))
        moment += duration
    return FakeLine(text=text, syllables=tuple(syllables), quality=quality)


CHORUS = [(" don't", 0.6), ("stand", 0.5), ("so", 0.4), ("close", 0.5)]


# --------------------------------------------------------------------------
# The machinery itself
# --------------------------------------------------------------------------

def test_two_instances_of_a_line_become_one_template() -> None:
    lines = [_line("Don't stand so close", 10.0, CHORUS),
             _line("Don't stand so close", 30.0, CHORUS)]
    templates = template.collect(lines)
    assert len(templates) == 1
    made = next(iter(templates.values()))
    assert made.instances == 2
    assert made.duration == pytest.approx(2.0)
    assert made.spread == pytest.approx(0.0)
    assert made.reliable


def test_the_profile_keeps_the_rhythm_of_the_line() -> None:
    """Spreading syllables evenly is what makes the fallback mechanical."""
    made = next(iter(template.collect(
        [_line("A line", 0.0, [(" long", 3.0), ("short", 1.0)])]).values()))
    assert made.profile == pytest.approx((0.75, 0.25))
    assert sum(made.profile) == pytest.approx(1.0)


def test_a_line_stretched_across_silence_is_no_template() -> None:
    """The lines we want to repair must not end up in their own
    template - that is the trap this model fell into."""
    windows = ((10.0, 12.0),)
    good = _line("Chorus", 10.0, CHORUS)
    stretched = _line("Chorus", 40.0, [(" don't", 5.0), ("stand", 5.0),
                                       ("so", 5.0), ("close", 5.0)])
    templates = template.collect([good, stretched], windows)
    made = next(iter(templates.values()))
    assert made.instances == 1, "the stretched instance must be left out"
    assert made.duration == pytest.approx(2.0)


def test_instances_that_disagree_are_not_used() -> None:
    """Twelve instances with a spread of 1.48 describe nothing."""
    lines = [_line("Chorus", 10.0, CHORUS),
             _line("Chorus", 30.0, [(w, d * 4) for w, d in CHORUS])]
    made = next(iter(template.collect(lines).values()))
    assert made.spread > template.MAX_SPREAD
    repaired = template.repair(lines, (), template.collect(lines))
    assert [r.syllables for r in repaired] == [r.syllables for r in lines]


def test_an_impossible_duration_is_recognised() -> None:
    """The reason ends up in the log window, so it comes from
    ``translations`` - no literal here, per the working agreement."""
    from modules.translations import TRANSLATIONS

    made = template.Template("k", 2.0, (0.25, 0.25, 0.25, 0.25), 2, 0.0)
    far_too_long = _line("Chorus", 0.0, [(w, d * 8) for w, d in CHORUS])
    far_too_short = _line("Chorus", 0.0, [(w, 0.02) for w, _d in CHORUS])
    fine = _line("Chorus", 0.0, CHORUS)
    assert template.implausible(far_too_long, made) == \
        TRANSLATIONS["nl"]["template_longer"] % 8.0
    assert template.implausible(far_too_short, made) == \
        TRANSLATIONS["nl"]["template_too_fast"]
    assert template.implausible(fine, made) == ""


def test_a_repaired_line_gets_the_template_duration_and_rhythm() -> None:
    made = template.Template("k", 2.0, (0.5, 0.2, 0.2, 0.1), 2, 0.0)
    broken = _line("Chorus", 100.0, [(w, 5.0) for w, _d in CHORUS])
    fixed = template.fit(broken, made, 100.0, 102.0)
    spans = [round(s.end - s.start, 3) for s in fixed.syllables]
    assert spans == pytest.approx([1.0, 0.4, 0.4, 0.2])
    assert fixed.syllables[0].start == pytest.approx(100.0)
    assert fixed.syllables[-1].end == pytest.approx(102.0)


def test_a_repair_lands_inside_the_measured_singing() -> None:
    lines = [_line("Chorus", 10.0, CHORUS), _line("Chorus", 30.0, CHORUS),
             _line("Chorus", 50.0, [(w, 6.0) for w, _d in CHORUS])]
    windows = ((10.0, 12.0), (30.0, 32.0), (50.0, 53.0))
    repaired = template.repair(lines, windows)
    last = repaired[-1]
    span = last.syllables[-1].end - last.syllables[0].start
    assert span == pytest.approx(2.0, abs=0.05)
    assert last.syllables[0].start >= 50.0
    assert last.syllables[-1].end <= 53.0


def test_without_a_template_nothing_happens() -> None:
    lines = [_line("Only once", 0.0, CHORUS)]
    assert template.repair(lines, ()) == tuple(lines)


# --------------------------------------------------------------------------
# The model is off, and says why
# --------------------------------------------------------------------------

def test_the_model_is_switched_off_with_a_reason() -> None:
    model = model_register.by_code("B380")
    assert model is not None
    assert model.default_on is False
    assert "1.00" in model.reason, \
        "the reason has to name the measurement, not just an opinion"


def test_a_switched_off_model_keeps_taking_part_in_the_trial() -> None:
    """The whole point of switching off instead of removing."""
    from modules import test_panel

    model_register.apply_settings({})
    model_register.apply_disabled()
    try:
        codes = {m.code for _level, m, _targets, _on
                 in test_panel._variants_from_register()}
        assert "B380" in codes
    finally:
        model_register.restore_all()


# --------------------------------------------------------------------------
# The duration check that came out of it
# --------------------------------------------------------------------------

def test_a_line_far_longer_than_the_same_line_elsewhere_is_flagged() -> None:
    """"High quality" only says the coupling was one-to-one; one project
    had a line of 19.42 s labelled high while the same text runs 5.4 s."""
    found = timing_checks.Findings()
    lines = [
        {"text": "Chorus", "syllables": [{"text": "a", "start": 0.0,
                                          "end": 5.0, "held": False}]},
        {"text": "Chorus", "syllables": [{"text": "a", "start": 10.0,
                                          "end": 15.0, "held": False}]},
        {"text": "Chorus", "syllables": [{"text": "a", "start": 20.0,
                                          "end": 39.4, "held": False}]},
    ]
    timing_checks.duration_outliers(lines, found)
    assert found.odd_duration == 1


def test_a_normal_spread_is_not_flagged() -> None:
    found = timing_checks.Findings()
    lines = [{"text": "Chorus",
              "syllables": [{"text": "a", "start": s, "end": s + d,
                             "held": False}]}
             for s, d in ((0.0, 5.0), (10.0, 5.4), (20.0, 4.6))]
    timing_checks.duration_outliers(lines, found)
    assert found.odd_duration == 0


def test_the_check_reports_its_number() -> None:
    assert "odd_duration" in timing_checks.Findings().as_dict()
