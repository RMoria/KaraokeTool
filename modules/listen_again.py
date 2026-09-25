"""Listen again where the first listen heard nothing (v1.0.12).

One of the owner's songs had 31.5 seconds of singing without a pause,
and Whisper heard nothing in 25 of them - apart from "ZANG EN MUZIEK", the
subtitle it invents when it has decided that nothing is being sung. The
chunked run of B442 did not help, because that stretch had no silence to
cut in, so its piece was a whole thirty-second window again. Three
answers, and this module holds the parts of them that can be reasoned
about and tested without starting a model:

* **cut shorter** where the singing does not pause - that is
  ``whisper_chunks.FORCED_S``;
* **lay the known text on the voice.** The lyrics say what is sung, the
  vocal stem says THAT it is sung; what is missing is only where each
  word goes, and a forced aligner answers exactly that question. In
  step 1.1 that happens automatically for every stretch of measured
  singing that is still unheard after the merge (:func:`gap_segments`);
* **listen again, aimed.** After 1.2 far more is known: which lyric
  words are coupled well, and therefore exactly which words are missing
  between which two anchors. The coupling editor asks for that
  (:func:`problem_areas`), gets candidates from a Whisper run on only
  that stretch and from the aligner, and has the vocal stem judge them
  (:func:`score`), because the vocal stem is the one witness that knows
  nothing of the lyrics.

What is found this way is marked with where it came from
(``whisper.ORIGIN_ALIGNED`` / ``whisper.ORIGIN_HEARD_AGAIN``), so it can
never pass for something Whisper heard in the normal run.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Sequence

from .whisper import ORIGIN_ALIGNED, Segment

#: Step 1.1: an unheard stretch of singing shorter than this is left
#: alone. A single missed word is the coupling's business, not a
#: forced aligner's; five seconds is a line.
GAP_MIN_S = 5.0

#: A heard word "covers" this much singing around itself, so the small
#: pause between two words is not counted as a hole.
WORD_REACH_S = 0.4

#: A coupling below this similarity is weak: it is coupled, but the
#: coupling itself may be the mistake.
WEAK_SIM = 0.5

#: An area shorter than this has no room for a word; one longer than
#: this is not a gap in a coupling but a coupling that failed wholesale,
#: and listening to a minute again will not fix that.
AREA_MIN_S = 0.8
AREA_MAX_S = 60.0

#: How much the Whisper slice sticks out on both sides of an area, so a
#: word on its edge is not cut off.
MARGIN_S = 1.0

#: Lyric words that do not fit their stretch at this many syllables per
#: second are not laid on it: too slow means the stretch is mostly
#: something else, too fast means the words belong partly elsewhere.
SYLLABLES_PER_S = (0.6, 8.0)

#: The statuses of ``pipeline.word_coupling_view`` that are NOT a
#: problem: coupled (judged on its similarity separately), backing
#: vocals, a word the user uncoupled himself, and a filler that the
#: coupling skipped on purpose.
_NOT_A_PROBLEM = ("background", "manually_uncoupled", "filler_skipped")

#: A Whisper answer that repeats the prompt word for word with a mean
#: confidence below this is suspected of reciting it (the prompt echo of
#: B390) and loses this share of its score.
ECHO_CONFIDENCE = 0.5
ECHO_PENALTY = 0.4


def syllables(words: Sequence[str]) -> int:
    """How many syllables these words have."""
    from .timing import split_syllables

    return sum(max(1, len(split_syllables(str(word)))) for word in words)


def plausible(words: Sequence[str], low: float, high: float) -> bool:
    """Can these words be sung in this stretch at a normal pace?"""
    span = high - low
    if span <= 0 or not words:
        return False
    rate = syllables(words) / span
    return SYLLABLES_PER_S[0] <= rate <= SYLLABLES_PER_S[1]


def unheard_stretches(windows, words, minimum: float = GAP_MIN_S
                      ) -> list[tuple[float, float]]:
    """Stretches of measured singing where no heard word lies.

    ``windows`` are the sung windows of the vocal stem, ``words`` the
    ``(start, end)`` of every word the transcription has. Each word
    covers :data:`WORD_REACH_S` around itself; what is left of a window
    after that, and is at least ``minimum`` long, is a hole.
    """
    covered = sorted((float(s) - WORD_REACH_S, float(e) + WORD_REACH_S)
                     for s, e in words)
    holes = []
    for low, high in windows:
        cursor = float(low)
        for start, end in covered:
            if end <= cursor or start >= high:
                continue
            if start - cursor >= minimum:
                holes.append((round(cursor, 3), round(start, 3)))
            cursor = max(cursor, end)
        if high - cursor >= minimum:
            holes.append((round(cursor, 3), round(float(high), 3)))
    return holes


def expected_between(aligned, low: float, high: float) -> list:
    """The lyric words that belong in ``low``-``high`` (step 1.1).

    ``aligned`` is the lyrics alignment on the transcription so far (a
    sequence of ``song_text.AlignedWord``). The last coupled word ending
    before the stretch and the first starting after it are the anchors;
    the uncoupled words in between, backing vocals left out, are what
    was sung there. A backing vocal sounds WITH a line and not after it,
    so laying it end to end with the rest would push every word behind
    it out of place.
    """
    before = None
    after = None
    for position, word in enumerate(aligned):
        if word.start is None:
            continue
        if word.end is not None and word.end <= low + WORD_REACH_S:
            before = position
        elif word.start >= high - WORD_REACH_S and after is None:
            after = position
    first = 0 if before is None else before + 1
    last = len(aligned) if after is None else after
    return [word.lyric for word in aligned[first:last]
            if word.start is None and not word.lyric.bg]


def gap_segments(holes, aligned) -> list[Segment]:
    """One segment of known text per hole, for the forced aligner.

    The segment has no words yet - the aligner gives them their times -
    and is marked :data:`whisper.ORIGIN_ALIGNED`. A hole whose words do
    not fit it is skipped, and so is a word that two holes would both
    claim: it goes to the first, the one it is closest to in the song.
    """
    out = []
    used: set[int] = set()
    for low, high in holes:
        lyrics = [w for w in expected_between(aligned, low, high)
                  if w.index not in used]
        texts = [w.text for w in lyrics]
        if not plausible(texts, low, high):
            continue
        used.update(w.index for w in lyrics)
        out.append(Segment(index=0, text=" ".join(texts), start=low,
                           end=high, words=(), origin=ORIGIN_ALIGNED))
    return out


# --------------------------------------------------------------------------
# After 1.2: the problem areas of a coupling
# --------------------------------------------------------------------------

@dataclass
class Area:
    """One place in the coupling where something is missing or weak."""

    low: float
    high: float
    #: Their text, in order - what the aligner lays on the voice.
    expected: list[str]
    #: The whole lines they stand in, as running text - what Whisper
    #: gets as a hint. A line gives the phrasing a word list does not.
    prompt: str
    #: Found-word indices inside the area that no good or pinned lyric
    #: word claims. Accepting a candidate replaces exactly these.
    replaceable: list[int] = field(default_factory=list)
    #: The ``(start, end)`` of the found words inside the area that an
    #: anchor DOES claim. A candidate word on one of them is left out: it
    #: would stand beside a word that is coupled well already.
    claimed_spans: list[tuple[float, float]] = field(default_factory=list)


def _good(word: dict) -> bool:
    """Is this lyric word an anchor that may not be touched?

    A backing vocal is never one: it sounds WITH a line, so its time
    says nothing about where the words around it in the lyrics are.
    """
    if word.get("bg") and not word.get("pinned"):
        return False
    if word.get("pinned"):
        return bool(word.get("transcript_indices"))
    return (word.get("status") == "coupled"
            and float(word.get("sim", 0.0)) >= WEAK_SIM
            and bool(word.get("transcript_indices")))


def _problem(word: dict) -> bool:
    if (word.get("pinned") or word.get("bg")
            or word.get("status") in _NOT_A_PROBLEM):
        return False
    if word.get("status") == "coupled":
        return float(word.get("sim", 0.0)) < WEAK_SIM
    return True


def problem_areas(view: dict, lyric_lines: dict[int, str],
                  song_end: float) -> list[Area]:
    """Every place the coupling of ``view`` is missing or weak.

    ``view`` is ``pipeline.word_coupling_view``: the found words
    (``transcript``) and per lyric word its coupling and status. A run
    of problem words in lyric order is one area; its time span runs from
    the end of the last good anchor before it to the start of the first
    one after it. Pinned words - the user's own work - and good
    couplings are anchors and are never part of an area; a word the user
    uncoupled on purpose, a backing vocal and a skipped filler are not
    problems either, and do not break a run.

    ``lyric_lines`` gives the text of each lyric line, for the prompt.
    """
    transcript = view.get("transcript") or []
    words = view.get("words") or []
    claimed: set[int] = set()
    for word in words:
        # A backing vocal that was heard is no anchor, but what it was
        # coupled to is no word to replace either: no candidate brings
        # it back, because the aligner is never given backing vocals.
        if _good(word) or (word.get("bg") and word.get("transcript_indices")):
            claimed.update(int(i) for i in word["transcript_indices"])

    def span(word: dict) -> tuple[float, float]:
        indices = [int(i) for i in word["transcript_indices"]
                   if 0 <= int(i) < len(transcript)]
        return (min(transcript[i][1] for i in indices),
                max(transcript[i][2] for i in indices))

    areas = []
    run: list[dict] = []
    last_good_end = 0.0

    def close(next_start: float) -> None:
        if not run:
            return
        low, high = last_good_end, next_start
        if AREA_MIN_S <= high - low <= AREA_MAX_S:
            lines = []
            for word in run:
                line = lyric_lines.get(int(word.get("line", -1)), "")
                if line and line not in lines:
                    lines.append(line)
            within = [i for i, (_t, s, e) in enumerate(transcript)
                      if s >= low - 1e-6 and e <= high + 1e-6]
            areas.append(Area(low=round(low, 3), high=round(high, 3),
                              expected=[str(w["text"]) for w in run],
                              prompt=" ".join(lines),
                              replaceable=[i for i in within
                                           if i not in claimed],
                              claimed_spans=[
                                  (float(transcript[i][1]),
                                   float(transcript[i][2]))
                                  for i in within if i in claimed]))
        run.clear()

    for word in words:
        if _good(word):
            start, end = span(word)
            close(start)
            last_good_end = max(last_good_end, end)
        elif _problem(word):
            run.append(word)
    close(float(song_end))
    return areas


# --------------------------------------------------------------------------
# The referee
# --------------------------------------------------------------------------

@dataclass
class Candidate:
    """One answer for an area, and how well the voice supports it."""

    kind: str                       # "whisper" or "aligned"
    words: list[tuple[str, float, float, float]]
    score: float = 0.0
    #: The parts of the score, shown with the candidate in the dialog.
    evidence: dict = field(default_factory=dict)


def _keys(words) -> list[str]:
    from .cluster import phonetic_key

    return [phonetic_key(str(word)) for word in words]


def _on_singing(start: float, end: float, windows) -> bool:
    middle = (float(start) + float(end)) / 2.0
    return any(float(a) <= middle <= float(b) for a, b in windows)


def score(candidate: Candidate, expected: Sequence[str],
          onsets: Sequence[float] | None, windows) -> Candidate:
    """Judge a candidate against what the voice itself shows.

    Three parts:

    * **evidence** - for a Whisper answer, how closely it matches the
      expected words, weighed by Whisper's own confidence; for the
      aligner, the aligner's own mean score, because its text IS the
      expected text and matching it against itself proves nothing;
    * **singing** - the share of its words that lie on measured singing;
    * **rhythm** - how close its number of syllables comes to the
      number of onsets the vocal stem shows in the area. Unknown
      (``None``) onsets count as neutral.

    A Whisper answer that is exactly the expected words at a low mean
    confidence is suspected of reciting its hint instead of hearing it
    (the hint holds those words), and loses :data:`ECHO_PENALTY` of its
    score. Exactly right AND sure of it is simply a good answer.
    """
    words = candidate.words
    if not words:
        candidate.score = 0.0
        candidate.evidence = {}
        return candidate
    texts = [w[0] for w in words]
    confidence = sum(float(w[3]) for w in words) / len(words)
    if candidate.kind == "aligned":
        evidence = confidence
    else:
        match = difflib.SequenceMatcher(
            a=_keys(texts), b=_keys(expected), autojunk=False).ratio()
        evidence = match * (0.5 + 0.5 * confidence)
    singing = (sum(1 for w in words if _on_singing(w[1], w[2], windows))
               / len(words)) if windows else 0.5
    if onsets:
        heard = syllables(texts)
        rhythm = 1.0 - abs(heard - len(onsets)) / max(heard, len(onsets))
    else:
        rhythm = 0.5
    total = 0.45 * evidence + 0.30 * singing + 0.25 * rhythm
    echo = (candidate.kind == "whisper"
            and _keys(texts) == _keys(expected)
            and confidence < ECHO_CONFIDENCE)
    if echo:
        total *= 1.0 - ECHO_PENALTY
    candidate.score = round(total, 3)
    candidate.evidence = {"evidence": round(evidence, 3),
                          "singing": round(singing, 3),
                          "rhythm": round(rhythm, 3),
                          "echo": echo}
    return candidate


def inside(words, low: float, high: float, claimed_spans=()):
    """The words whose middle lies in ``low``-``high`` and not on a word
    an anchor claims."""
    out = []
    for w in words:
        middle = (float(w[1]) + float(w[2])) / 2.0
        if low <= middle <= high and not any(
                float(a) <= middle <= float(b) for a, b in claimed_spans):
            out.append(w)
    return out
