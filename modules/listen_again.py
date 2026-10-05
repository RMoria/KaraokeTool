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
  singing that is still unheard after the merge (:func:`gap_texts`);
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


def gap_texts(holes, aligned) -> list[tuple[Segment, list[int]]]:
    """One segment of known text per hole, for the forced aligner, with
    the lyric line of each of its words.

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
        out.append((Segment(index=0, text=" ".join(texts), start=low,
                            end=high, words=(), origin=ORIGIN_ALIGNED),
                    [int(w.line) for w in lyrics]))
    return out


def heard_lines_of_alignment(aligned) -> list[tuple[str, list]]:
    """Per lyric line that was fully HEARD in the lyrics alignment of
    step 1.1: its text and the ``(text, start, end)`` of its words - the
    material for :func:`line_templates`. A line with a word that was not
    coupled, or only estimated, is not a measurement and stays out."""
    per_line: dict[int, list] = {}
    for word in aligned:
        if word.lyric.bg:
            continue
        per_line.setdefault(int(word.lyric.line), []).append(word)
    out = []
    for _line, words in sorted(per_line.items()):
        if all(w.start is not None and w.end is not None
               and not getattr(w, "estimated", False) for w in words):
            out.append((" ".join(w.lyric.text for w in words),
                        [(w.lyric.text, float(w.start), float(w.end))
                         for w in words]))
    return out


def heard_lines_of_view(view: dict, made_starts) -> list[tuple[str, list]]:
    """The same for the coupling of step 1.2: a line whose every word is
    coupled well - or pinned by the user - to found words none of which
    was laid on or heard again (``made_starts``: their start times)."""
    transcript = view.get("transcript") or []
    made = {round(float(start), 3) for start in made_starts}
    per_line: dict[int, list] = {}
    for word in view.get("words") or []:
        if word.get("bg"):
            continue
        per_line.setdefault(int(word.get("line", -1)), []).append(word)
    out = []
    for _line, words in sorted(per_line.items()):
        timed = []
        for word in words:
            rows = [transcript[int(i)] for i in word.get("transcript_indices")
                    or () if 0 <= int(i) < len(transcript)]
            if not rows or not (_good(word) or word.get("pinned")):
                break
            if any(round(float(r[1]), 3) in made for r in rows):
                break
            timed.append((str(word["text"]), min(float(r[1]) for r in rows),
                          max(float(r[2]) for r in rows)))
        else:
            out.append((" ".join(w[0] for w in timed), timed))
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
    #: The lyric line of each expected word (v1.0.13), so a candidate can
    #: be judged per line and not only as a whole.
    expected_lines: list[int] = field(default_factory=list)
    #: The anchor words on either side (v1.0.13), for the hint that
    #: tells Whisper where the stretch begins and ends.
    before: str = ""
    after: str = ""


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
    last_good_text = ""

    def close(next_start: float, next_text: str = "") -> None:
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
                              expected_lines=[int(w.get("line", -1))
                                              for w in run],
                              prompt=" ".join(lines),
                              before=last_good_text, after=next_text,
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
            close(start, str(word.get("text", "")))
            last_good_end = max(last_good_end, end)
            last_good_text = str(word.get("text", ""))
        elif _problem(word):
            run.append(word)
    close(float(song_end))
    return areas


#: What Whisper gets as its hint when it listens again (v1.0.13, B583):
#: ``"lines"`` - the whole lines the missing words stand in (the way it
#: shipped in v1.0.12); ``"expected"`` - only the missing words, sharper
#: but easier to recite; ``"anchored"`` - the lines with the anchor word
#: before and after, so Whisper knows where the stretch begins and ends.
#: A setting for 1.5.13 to measure, not for the user.
HINTS = ("lines", "expected", "anchored")
HINT = "lines"


def hint_for(area: Area, how: str | None = None) -> str:
    """The hint for one area, in the way ``how`` (default :data:`HINT`);
    an unknown way is the shipped one."""
    how = how or HINT
    if how not in HINTS:
        how = "lines"
    if how == "expected":
        return " ".join(area.expected)
    if how == "anchored":
        return " ".join(part for part in (area.before, area.prompt,
                                          area.after) if part)
    return area.prompt


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
          onsets: Sequence[float] | None, windows,
          area: "Area | None" = None) -> Candidate:
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
    if candidate.kind in ("aligned", "singing"):
        # For the candidate on the singing (B580) the "confidence" is the
        # way it was made, see ON_SINGING_CONFIDENCE.
        evidence = confidence
    else:
        match = difflib.SequenceMatcher(
            a=_keys(texts), b=_keys(expected), autojunk=False).ratio()
        evidence = match * (0.5 + 0.5 * confidence)
    singing = (sum(1 for w in words if _on_singing(w[1], w[2], windows))
               / len(words)) if windows else 0.5
    if candidate.kind == "singing":
        # B580: laid on the singing by construction, so "on singing" and
        # "covers the singing" say nothing about it - they count as
        # neutral, or it would outscore a real hearing for free.
        singing = 0.5
    if onsets:
        heard = syllables(texts)
        rhythm = 1.0 - abs(heard - len(onsets)) / max(heard, len(onsets))
    else:
        rhythm = 0.5
    covered = (coverage(words, area.low, area.high, windows)
               if area is not None else None)
    if covered is not None and candidate.kind == "singing":
        covered = 0.5
    if covered is None:
        total = 0.45 * evidence + 0.30 * singing + 0.25 * rhythm
    else:
        # v1.0.13 (B578): how much of the singing of the place the words
        # take up. Laid on seventeen seconds of singing in three, they
        # leave most of the voice unexplained.
        total = (0.40 * evidence + 0.25 * singing + 0.20 * rhythm
                 + 0.15 * covered)
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
    if covered is not None:
        candidate.evidence["coverage"] = round(covered, 3)
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


# --------------------------------------------------------------------------
# v1.0.13: squeezed lines, the same line elsewhere, and a third candidate
# --------------------------------------------------------------------------

#: B579: a line may last at most this factor longer or shorter than the
#: same line where Whisper heard it - the same margin the timing's own
#: templates allow (``timing_template.MAX_FACTOR``).
TEMPLATE_FACTOR = 2.0

#: B579, the last resort: with no heard copy of a line, it may not be
#: sung this many times faster than the song's own pace per syllable.
#: A bound, never a measure: an average says nothing about how ONE line
#: is sung, only that a line cannot be three times too fast.
PACE_FACTOR = 3.0

#: B578/B579: a line is only judged when it has this much in it. One
#: short word of a line - the aligner often gives a word a tenth of a
#: second - is no measure of how fast that line is sung.
JUDGED_MIN_WORDS = 2
JUDGED_MIN_SYLLABLES = 3

#: B580: a sung window shorter than this carries no line of its own.
WINDOW_MIN_S = 0.3

#: B580: how sure the candidate on the singing is, per way it was made -
#: as its evidence in the referee. A line laid on the profile of the same
#: line elsewhere beats one laid on the onsets, and spreading by
#: syllables is the last resort and scores as such.
ON_SINGING_CONFIDENCE = {"profile": 0.6, "onsets": 0.45, "even": 0.3}


@dataclass(frozen=True)
class LineTemplate:
    """How long a lyric line lasts where it was heard, and where its
    words begin within it (fractions of the line, first one 0.0)."""

    duration: float
    starts: tuple[float, ...]
    ends: tuple[float, ...]


def _line_key(text: str) -> str:
    from .timing_template import line_key

    return line_key(text)


def line_templates(lines) -> tuple[dict[str, LineTemplate], float]:
    """Templates per line text, and the song's pace per syllable.

    ``lines`` holds per lyric line ``(text, words)`` where ``words`` are
    the ``(text, start, end)`` of a line that was HEARD - every word
    coupled to a word Whisper heard in the normal run. What was laid on
    by the aligner or taken over in "Listen again" is left out by the
    caller: a squeezed line may not become the measure for its copies.
    The pace is the median seconds per syllable over those lines.
    """
    import statistics

    per_key: dict[str, list] = {}
    paces = []
    for text, words in lines:
        if not words:
            continue
        start = float(words[0][1])
        end = float(words[-1][2])
        span = end - start
        count = syllables([w[0] for w in words])
        if span <= 0 or not count:
            continue
        paces.append(span / count)
        per_key.setdefault(_line_key(text), []).append(
            (span, tuple((float(w[1]) - start) / span for w in words),
             tuple((float(w[2]) - start) / span for w in words)))
    templates = {}
    for key, found in per_key.items():
        size = max({len(f[1]) for f in found},
                   key=[len(f[1]) for f in found].count)
        same = [f for f in found if len(f[1]) == size]
        templates[key] = LineTemplate(
            duration=statistics.median(f[0] for f in same),
            starts=tuple(statistics.median(f[1][n] for f in same)
                         for n in range(size)),
            ends=tuple(statistics.median(f[2][n] for f in same)
                       for n in range(size)))
    pace = statistics.median(paces) if paces else 0.0
    return templates, pace


def lines_of(words, expected: Sequence[str],
             expected_lines: Sequence[int]) -> list[int]:
    """The lyric line of every candidate word.

    Matched to the expected words on their sound; a word that matches
    nothing belongs to the line of the word before it (or, at the very
    start, the first line).
    """
    if not expected_lines:
        return [-1 for _w in words]
    if len(words) == len(expected) and [w[0] for w in words] == \
            list(expected):
        return list(expected_lines)
    keys = _keys([w[0] for w in words])
    matcher = difflib.SequenceMatcher(a=keys, b=_keys(expected),
                                      autojunk=False)
    out: list[int | None] = [None] * len(words)
    for block in matcher.get_matching_blocks():
        for n in range(block.size):
            out[block.a + n] = expected_lines[block.b + n]
    last = expected_lines[0]
    for n, line in enumerate(out):
        if line is None:
            out[n] = last
        else:
            last = line
    return [int(x) for x in out]


def squeezed(words, lines: Sequence[int]) -> list[int]:
    """B578: the lines a candidate sings faster than anyone can.

    Per lyric line: its syllables over the time its own words take. The
    ceiling is the one the area itself already had to meet
    (:data:`SYLLABLES_PER_S`); the first version only held the AREA to
    it, and twelve syllables in six tenths of a second inside a
    seventeen-second area went straight through.
    """
    bad = []
    for line in sorted(set(lines)):
        own = [w for w, ln in zip(words, lines) if ln == line]
        span = float(own[-1][2]) - float(own[0][1])
        count = syllables([w[0] for w in own])
        if not _judged(own, count):
            continue
        if span <= 0 or count / span > SYLLABLES_PER_S[1]:
            bad.append(line)
    return bad


def _judged(own, count: int) -> bool:
    return len(own) >= JUDGED_MIN_WORDS or count >= JUDGED_MIN_SYLLABLES


def unlike_elsewhere(words, lines: Sequence[int], line_texts: dict,
                     templates: dict, pace: float) -> list[int]:
    """B579: the lines a candidate times unlike the same line elsewhere.

    Only a WHOLE line is held against its template - a stretch that has
    the second half of a line cannot be as long as all of it. Without a
    heard copy, the song's pace is the last resort, and only as a floor:
    a line three times faster than the song sings is squeezed.
    """
    bad = []
    for line in sorted(set(lines)):
        own = [w for w, ln in zip(words, lines) if ln == line]
        span = float(own[-1][2]) - float(own[0][1])
        count = syllables([w[0] for w in own])
        text = str(line_texts.get(line, ""))
        template = templates.get(_line_key(text)) if text else None
        whole = template is not None and len(own) == len(text.split())
        if not whole and not _judged(own, count):
            continue
        if whole:
            if not (template.duration / TEMPLATE_FACTOR <= span
                    <= template.duration * TEMPLATE_FACTOR):
                bad.append(line)
        elif pace > 0 and span < count * pace / PACE_FACTOR:
            bad.append(line)
    return bad


def coverage(words, low: float, high: float, windows) -> float | None:
    """B578: the share of the measured singing in ``low``-``high`` that
    the words take up (each reaching :data:`WORD_REACH_S` around it).
    ``None`` without measured singing there - then it says nothing."""
    sung = [(max(low, float(a)), min(high, float(b))) for a, b in windows
            if float(b) > low and float(a) < high]
    total = sum(b - a for a, b in sung)
    if total <= 0:
        return None
    reach = sorted((float(w[1]) - WORD_REACH_S, float(w[2]) + WORD_REACH_S)
                   for w in words)
    covered = 0.0
    for a, b in sung:
        cursor = a
        for start, end in reach:
            start, end = max(start, cursor), min(end, b)
            if end > start:
                covered += end - start
                cursor = end
    return min(1.0, covered / total)


def _sung_in(low: float, high: float, windows) -> list[tuple[float, float]]:
    """The sung windows inside ``low``-``high``; a blip too short to
    carry a line is left out, unless there is nothing else."""
    inside = [(max(low, float(a)), min(high, float(b))) for a, b in windows
              if float(b) > low and float(a) < high
              and min(high, float(b)) - max(low, float(a)) > 0.05]
    real = [w for w in inside if w[1] - w[0] >= WINDOW_MIN_S]
    return real or inside


def _slots_for(count: int, sung, weights) -> list[tuple[float, float]]:
    """``count`` time slots on the sung windows, one per line.

    The pauses are the line boundaries. With more windows than lines the
    smallest pauses are closed first. With fewer, every window gets lines
    in proportion to its length (at least one each), and a window with
    several lines is split in the ratio of their weights (syllables).
    """
    slots = [list(w) for w in sung]
    while len(slots) > count:
        gaps = [slots[n + 1][0] - slots[n][1] for n in range(len(slots) - 1)]
        n = gaps.index(min(gaps))
        slots[n:n + 2] = [[slots[n][0], slots[n + 1][1]]]
    if len(slots) == count:
        return [(a, b) for a, b in slots]
    lengths = [b - a for a, b in slots]
    total = sum(lengths) or 1.0
    shares = [count * length / total for length in lengths]
    counts = [max(1, int(share)) for share in shares]
    while sum(counts) < count:
        n = max(range(len(slots)), key=lambda k: shares[k] - counts[k])
        counts[n] += 1
    while sum(counts) > count:
        n = max((k for k in range(len(slots)) if counts[k] > 1),
                key=lambda k: counts[k] - shares[k])
        counts[n] -= 1
    out = []
    cursor = 0
    for (a, b), many in zip(slots, counts):
        own = weights[cursor:cursor + many]
        cursor += many
        whole = sum(own) or 1.0
        edge = a
        for weight in own:
            step = (b - a) * weight / whole
            out.append((edge, edge + step))
            edge += step
    return out


def on_singing(area: Area, windows, onsets, line_texts: dict,
               templates: dict) -> Candidate | None:
    """B580: the expected words laid out on the singing of the place.

    For sounds the aligner cannot follow - a long "jalala" has nothing
    for wav2vec2 to hold on to, and it squeezed four of them into the
    first second. The lines go on the sung windows, one per window with
    the pauses as line boundaries. Within a line, in this order:

    1. the profile of the same line where it was heard (its length and
       where each word begins);
    2. the onsets the vocal stem shows - each word begins on the onset
       nearest to where an even spread would put it;
    3. only when there is nothing else: spread by syllables.
    """
    sung = _sung_in(area.low, area.high, windows)
    if not sung or not area.expected:
        return None
    lines = list(dict.fromkeys(area.expected_lines)) or [-1]
    groups = [[w for w, ln in zip(area.expected, area.expected_lines or
                                  [-1] * len(area.expected)) if ln == line]
              for line in lines]
    weights = [max(1, syllables(g)) for g in groups]
    slots = _slots_for(len(groups), sung, weights)
    words = []
    ways = []
    for line, group, (low, high) in zip(lines, groups, slots):
        text = str(line_texts.get(line, ""))
        template = templates.get(_line_key(text)) if text else None
        if template is not None and len(template.starts) == len(group) \
                and len(group) == len(text.split()):
            span = min(template.duration, high - low)
            starts = [low + f * span for f in template.starts]
            ends = [low + f * span for f in template.ends]
            ways.append("profile")
        else:
            counts = [max(1, syllables([w])) for w in group]
            total = sum(counts)
            even = []
            cursor = 0
            for c in counts:
                even.append(low + (high - low) * cursor / total)
                cursor += c
            near = [o for o in (onsets or ()) if low <= o < high]
            if len(near) >= len(group):
                starts = []
                for target in even:
                    pick = min((o for o in near
                                if not starts or o > starts[-1]),
                               key=lambda o: abs(o - target),
                               default=target)
                    starts.append(pick)
                ways.append("onsets")
            else:
                starts = even
                ways.append("even")
            ends = [starts[n + 1] - 0.02 for n in range(len(starts) - 1)]
            ends.append(high)
        # In order, apart, and inside the slot - whichever way the starts
        # were found - and every word ends before the next one begins.
        count = len(group)
        placed = []
        for n, start in enumerate(starts):
            floor = placed[-1] + 0.05 if placed else low
            ceiling = high - 0.05 * (count - n)
            placed.append(round(max(floor, min(float(start), ceiling)), 3))
        for n, text_value in enumerate(group):
            start = placed[n]
            limit = placed[n + 1] - 0.02 if n + 1 < count else high
            end = max(start + 0.02, min(float(ends[n]), limit))
            words.append((str(text_value), start, round(end, 3)))
    worst = min(ways, key=lambda way: ON_SINGING_CONFIDENCE[way])
    confidence = ON_SINGING_CONFIDENCE[worst]
    return Candidate("singing", [(t, s, e, confidence) for t, s, e in words])
