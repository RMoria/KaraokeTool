"""Timing arbitration: ordered, weighted anchors with block barriers (B251).

The automatic timing comes from several sources (coupling/forced alignment,
vocal onset, sustained notes, stress, energy windows, phonetics). Previously
each step overwrote the previous one (*last-wins*), so that a late, weak step
could spoil a good early estimate and the error in repeated choruses leaked
into the next verse.

This module replaces that with **candidates + arbitration**:

* Every source delivers :class:`Candidate` objects with an *effective weight*
  (base weight × confidence).
* ``kind="anker"`` may fix a position (onset); ``kind="verfijning"``
  may only shift within an already fixed span.
* **Block barrier** (the core of the "Formidable" fix): an anchor from an
  earlier block is never pushed away by a later anchor from another block.
  This way the offset of a repeated chorus no longer leaks into the next
  verse; every block is anchored independently on its own strong onset.

The functions are pure (no Qt/IO) and testable on their own.
``timing.sanitize_timing`` uses :func:`arbitrate_anchors` for the anchor
series.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

_EPS = 1e-6

# Candidate kinds.
KIND_ANCHOR = "anker"
KIND_DURATION = "duur"
KIND_REFINE = "verfijning"


@dataclass(frozen=True)
class Candidate:
    """One timing candidate from a source (B251).

    Attributes:
        scope: ``"line"``, ``"word"`` or ``"syllable"``.
        ref: index of the line/the word/the syllable that the candidate
            refers to.
        start: proposed start time (s).
        end: proposed end time (s).
        weight: base weight of the source (from the config).
        confidence: 0..1, determined by the source itself for this candidate.
        kind: ``"anker"`` (may fix a position), ``"duur"`` or
            ``"verfijning"`` (may only redistribute within a span).
        blok: block number of the line; determines the block barrier.
    """

    scope: str
    ref: int
    start: float
    end: float
    weight: float
    confidence: float
    kind: str
    block: int = 0

    @property
    def effect(self) -> float:
        """Effective weight = base weight × confidence (B251)."""
        return float(self.weight) * float(self.confidence)


def best_per_ref(candidates: Sequence[Candidate],
                 kind: str = KIND_ANCHOR) -> dict[int, Candidate]:
    """Keep per ``ref`` the candidate with the highest effective weight.

    Filters on ``kind`` (anchors by default). On equal weight the first wins.
    """
    best: dict[int, Candidate] = {}
    for cand in candidates:
        if cand.kind != kind:
            continue
        current = best.get(cand.ref)
        if current is None or cand.effect > current.effect + _EPS:
            best[cand.ref] = cand
    return best


def arbitrate_anchors(candidates: Sequence[Candidate]) -> dict[int, float]:
    """Choose a monotone anchor series with weight and block barriers (B251).

    Takes the anchor candidates (``kind="anker"``), keeps the strongest per
    line, and builds an ascending series of start times. On a conflict (a
    later candidate would fall before the previous anchor) the following
    applies:

    * **within the same block** the heaviest anchor wins (B250): a stronger
      later anchor may displace a weaker earlier anchor;
    * **across a block boundary** an earlier-block anchor is never displaced;
      the later, non-monotone candidate is skipped. This way a repeated
      chorus (earlier block) cannot drag the next verse along, and every
      block anchors itself on its own onset.

    Returns:
        ``{ref: chosen start time}``, ascending in time.
    """
    best = best_per_ref(candidates, KIND_ANCHOR)
    order = sorted(best)                       # line index ascending
    kept: list[int] = []
    time: dict[int, float] = {}
    for i in order:
        cand = best[i]
        t_i = float(cand.start)
        while kept:
            j = kept[-1]
            if t_i > time[j] + _EPS:
                break                            # monotone: no conflict
            previous = best[j]
            same_block = previous.block == cand.block
            if same_block and cand.effect > previous.effect + _EPS:
                kept.pop()                       # B250: heavier wins (block)
                del time[j]
                continue
            # Block barrier or not heavier: do not place this anchor.
            break
        else:
            kept.append(i)
            time[i] = t_i
            continue
        if not kept or t_i > time[kept[-1]] + _EPS:
            kept.append(i)
            time[i] = t_i
    return {i: time[i] for i in kept}


def clamp_refinement(start: float, end: float,
                     lower: float, upper: float) -> tuple[float, float]:
    """Clamp a refinement within a fixed anchor span (B251).

    A refinement (phonetics, energy windows) may adjust the internal
    distribution but may not step outside the span ``[lower, upper]`` and may
    not put the start after the end.
    """
    lo, hi = (lower, upper) if upper >= lower else (upper, lower)
    s = min(max(float(start), lo), hi)
    e = min(max(float(end), s), hi)
    return s, e
