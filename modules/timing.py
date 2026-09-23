"""Per-syllable timing for the karaoke video.

Per the working method, lyrics, timing, color rules and render are four
separate parts; this is the timing part. The timing lives in
``input/<lied>/timing.json`` and holds, per logical line and per
syllable, a start time, an end/hold time and a flag ``held`` (long held
note, underlined in the video). The color changes exactly on the onset
of every syllable.

Syllable splitting is a Dutch approximation (vowel groups; a single
intervocalic consonant goes to the right, multiple ones are split after
the first) - meant as a starting point that is then fine-tuned by
hand.
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

from . import history, timing_rules
from .karaoke_text import TextLine, is_pause
from .translations import t

logger = logging.getLogger(__name__)

FILENAME = "timing.json"

_VOWELS = set("aeiouyàáâäèéêëìíîïòóôöùúûü")


@dataclass(frozen=True)
class Syllable:
    """One syllable with its times.

    The first syllable of every following word starts with a space, so
    that the line can be reconstructed with ``"".join(...)``.
    """

    text: str
    start: float
    end: float
    held: bool = False
    #: True = stressed syllable (stress), gets a subtle accent in the
    #: render; adjustable via the stress editor (B151).
    stress: bool = False
    #: True = this syllable belongs to an inline crowd piece and gets the
    #: crowd color (red), even though the rest of the sentence is vocals
    #: (B179a).
    crowd: bool = False
    #: True = this syllable belongs to an inline ``[bg]`` piece (B485):
    #: simultaneous background vocals that are part of this sentence. It
    #: is shown in the editors and may overlap its neighbours in time,
    #: but it never appears in the render.
    bg: bool = False


@dataclass(frozen=True)
class TimedLine:
    """One logical line with timed syllables.

    ``quality`` expresses the confidence in the automatic timing:
    ``syllable`` (high, green), ``word`` (medium, yellow) or
    ``sentence``/``even`` (best-effort, red). B326: these names were
    still documented in Dutch after the B299 rename.
    """

    index: int
    text: str
    crowd: bool
    syllables: tuple[Syllable, ...]
    quality: str = "sentence"
    #: True if this crowd line fills a whole block/section (sing-along
    #: chorus): it gets coupled and shown in the main flow instead of as
    #: a short interjection below the previous vocal line.
    crowd_section: bool = False
    #: Block number from the karaoke text (empty line = new block); used
    #: for the block view in the timing editor (B127).
    block: int = 0
    #: Disabled: this line is not shown in the render (B180), handy to
    #: drop leftover sentences without changing the text.
    disabled: bool = False
    #: True = this whole line is background vocals (``[bg]`` around the
    #: entire line in the karaoke text) (B510). It belongs in every
    #: editor and never in the render. Up to v0.145.0 that second half
    #: was arranged by switching the line off, and those are two
    #: different things: ``disabled`` is what the USER decided, ``bg`` is
    #: what the TEXT says. Because they shared one field, switching such
    #: a line on in the editor - which is the only way to see where it
    #: really lies - put it straight into the render.
    bg: bool = False

    @property
    def start(self) -> float:
        return self._sung[0].start if self._sung else 0.0

    @property
    def end(self) -> float:
        return self._sung[-1].end if self._sung else 0.0

    @property
    def _sung(self) -> tuple[Syllable, ...]:
        """The syllables that count as THIS sentence (B485).

        An inline ``[bg]`` piece is allowed to lie over its neighbours -
        that is the whole point of background vocals - so it must not
        drag the start or the end of the sentence along with it.
        Everything that reasons about the order of sentences (coupling,
        interpolation, the editor) therefore looks at the sung part. A
        line that is background vocals from beginning to end has no sung
        part and keeps its own times.
        """
        sung = tuple(item for item in self.syllables if not item.bg)
        return sung or self.syllables

    @property
    def full_end(self) -> float:
        """The end including an inline bg piece (B485).

        Used where the whole sentence has to fit on screen in time - the
        background piece may lie over its neighbours, but the video does
        have to run long enough for it.
        """
        if not self.syllables:
            return 0.0
        # The piece may lie anywhere in the sentence, so the last one in
        # the text is not necessarily the last one in time.
        return max(item.end for item in self.syllables)


#: Lazy cache of the pyphen hyphenator (None = not tried yet, False =
#: unavailable). The syllable model (B150) uses pyphen's Dutch word
#: list; if that one is missing, everything falls back to the built-in
#: vowel-group heuristic.
_PYPHEN: Any = None


def _pyphen_split(word: str) -> list[str] | None:
    """Split with pyphen (nl) when that is available, otherwise ``None``.

    pyphen only inserts hyphens at syllable boundaries, so the
    reconstruction (``"".join(...)``) stays exactly equal to the word.
    """
    global _PYPHEN
    if _PYPHEN is None:
        try:
            import pyphen
            _PYPHEN = pyphen.Pyphen(lang="nl_NL")
        except Exception:  # noqa: BLE001 - optional; graceful fallback
            _PYPHEN = False
    if not _PYPHEN:
        return None
    pieces = _PYPHEN.inserted(word).split("-")
    pieces = [p for p in pieces if p]
    return pieces if "".join(pieces) == word else None


def split_syllables(word: str) -> list[str]:
    """Split a word into syllables.

    Uses the pyphen syllable model (Dutch, B150) when available;
    otherwise a built-in vowel-group heuristic. Spelled-out uppercase
    words (TVX) are always split letter by letter.
    """
    if "_" in word:
        # B252: an underscore joins words into a single syllable
        # (e.g. "'k_heb", sung as "kep"). The underscore stays in place
        # internally as a marker so that downstream sees it as one unit;
        # only in the video render (modules.video) does it become a space.
        return [word]
    letters_only = "".join(ch for ch in word if ch.isalpha())
    if (len(letters_only) >= 2 and letters_only.isupper()
            and not any(ch.lower() in _VOWELS for ch in letters_only)):
        # Abbreviation/spelled letters (TVX, TV): each letter a syllable.
        return list(word)
    via_model = _pyphen_split(word)
    if via_model is not None:
        return via_model
    lowered = word.lower()
    groups: list[tuple[int, int]] = []  # vowel groups (start, end)
    position = 0
    while position < len(word):
        if lowered[position] in _VOWELS:
            group_start = position
            while position < len(word) and lowered[position] in _VOWELS:
                position += 1
            groups.append((group_start, position))
        else:
            position += 1
    if len(groups) < 2:
        return [word]

    cuts: list[int] = []
    for (_, end_a), (start_b, _) in zip(groups, groups[1:]):
        consonants = start_b - end_a
        if consonants <= 1:
            cuts.append(start_b - consonants)  # V-CV: before the consonant
        else:
            cuts.append(end_a + 1)             # VC-CV: after the first
    pieces: list[str] = []
    previous = 0
    for cut in cuts:
        pieces.append(word[previous:cut])
        previous = cut
    pieces.append(word[previous:])
    return [piece for piece in pieces if piece]


def split_line(text: str) -> list[str]:
    """Split a line into syllables; new words get a leading space so
    that the line can be reconstructed exactly."""
    syllables: list[str] = []
    for word_index, word in enumerate(text.split()):
        for syllable_index, syllable in enumerate(split_syllables(word)):
            prefix = " " if word_index > 0 and syllable_index == 0 else ""
            syllables.append(prefix + syllable)
    return syllables


def distribute_over_windows(line: TimedLine,
                            windows: Sequence[tuple[float, float]]
                            ) -> TimedLine:
    """Redistribute a line's words over vocal-active sub-windows (B234).

    ``windows`` are the (start, end) slots where the vocals sound within
    the line (separated by pauses). The words are distributed over those
    windows in proportion to their syllable count, so that the pauses
    BETWEEN words appear in the timing; syllables within a word stay
    evenly spaced. Line start/end and ordering are preserved. Without
    usable windows the line is returned unchanged.
    """
    # B485: an inline [bg] piece keeps its own times. Redistributing it
    # would pull it back inside the window of the sentence - while it is
    # precisely allowed to lie over its neighbours - and it would shorten
    # the sentence itself, because the piece counts along for a share of
    # the time. The sung part is distributed; the piece stays where it is.
    if any(item.bg for item in line.syllables):
        sung = tuple(item for item in line.syllables if not item.bg)
        if len(sung) < 2:
            return line
        fitted = distribute_over_windows(replace(line, syllables=sung),
                                         windows)
        rest = iter(fitted.syllables)
        merged = tuple(item if item.bg else next(rest)
                       for item in line.syllables)
        return replace(line, syllables=merged)
    usable_windows = [(float(s), float(e)) for s, e in windows if e > s]
    if not usable_windows or len(line.syllables) < 2:
        return line
    span_list = word_spans(line.syllables)          # (text, start, end)
    n_words = len(span_list)
    if n_words < 2 or len(usable_windows) < 2:
        return line
    # B290: more windows than words is impossible - every window is
    # allotted at least one word below. In that case first merge the
    # windows with the SMALLEST pause between them until exactly
    # ``n_words`` remain: that way precisely the clearest pauses survive
    # (which is what B234 is all about) and the outer span of the line
    # stays intact. Without this step the clamp further down ran past the
    # last word and ``woord_spans[wi]`` raised an IndexError - which was
    # swallowed by the broad catch-all except in
    # ``pipeline._apply_energy_word_timing``, so that one such line
    # silently switched off the energy word timing of the WHOLE song.
    while len(usable_windows) > n_words:
        _, merged = min((usable_windows[i + 1][0] - usable_windows[i][1], i)
                       for i in range(len(usable_windows) - 1))
        usable_windows[merged] = (usable_windows[merged][0], usable_windows[merged + 1][1])
        del usable_windows[merged + 1]
    # B493: does the sentence say WHERE the pause is, then that decides
    # the split and not the duration of the windows. A [pause] in the
    # karaoke text ("Lied Q [pause] kom maar, Lied Q") is the
    # user telling us that the sentence falls apart in two halves right
    # there; working it out from the window durations put the boundary at
    # another word often enough, and then the halves land in the wrong
    # gaps. ``is_pause`` steered nothing outside the render up to now.
    pause_at = [index for index, (text_value, _s, _e) in enumerate(span_list)
                if is_pause(text_value)]
    if pause_at and len(pause_at) == len(usable_windows) - 1:
        bounds = [index + 1 for index in pause_at]
    else:
        # Distribute words over windows in proportion to window duration.
        total = sum(e - s for s, e in usable_windows)
        bounds = []
        summed = 0.0
        for s, e in usable_windows[:-1]:
            summed += (e - s)
            bounds.append(round(summed / total * n_words))
    # groups of word indexes per window
    groups: list[list[int]] = []
    previous = 0
    for g in bounds:
        g = max(previous + 1, min(n_words - (len(usable_windows) - len(groups) - 1),
                                g))
        groups.append(list(range(previous, g)))
        previous = g
    groups.append(list(range(previous, n_words)))
    # B347: the pieces that are STORED are finer than the syllables that
    # ``split_line`` derives from the word text - on a real line 25
    # pieces against 10 syllables. The old code walked the stored pieces
    # with the split_line count, thought it was done after ten of them
    # and dumped the other fifteen on ``line.end`` with start == end. On
    # the two measured lines that cost four of the eight words all their
    # time (and gave one word a NEGATIVE span). So: the share of a word
    # is still weighed by its syllable count - that is what B234 is for -
    # but the pieces are taken from what is actually there.
    syls = list(line.syllables)
    pieces = piece_groups(syls)
    new: list[Syllable] = list(syls)
    for (ws, we), words_in in zip(usable_windows, groups):
        if not words_in:
            continue
        weights = [len(split_line(span_list[wi][0])) or 1 for wi in words_in]
        per_syllable = (we - ws) / (sum(weights) or 1)
        pos = ws
        for wi, weight in zip(words_in, weights):
            share = per_syllable * weight
            own = pieces[wi] if wi < len(pieces) else []
            step = share / (len(own) or 1)
            for offset, index in enumerate(own):
                new[index] = replace(
                    syls[index], start=round(pos + offset * step, 3),
                    end=round(pos + (offset + 1) * step, 3))
            pos += share
    if not new:
        return line
    return replace(line, syllables=tuple(new))


def apply_phonetic_timing(lines: Sequence[TimedLine], language: str = "nl",
                          config=None) -> tuple[TimedLine, ...]:
    """Rebuild the syllable timing on phonetic segments (B241).

    Per word (on the leading-space boundary) the existing word span is
    redistributed over phonetic segments (vowel groups weigh heavier, a
    final vowel is lengthened), language-independently via
    ``modules.fonetiek``. The segments become the new drawing units
    (syllables). Crowd is preserved per word; the stress moves to the
    heaviest vowel group of the word. If the segmentation fails, the line
    is left untouched.
    """
    from . import phonetics
    out: list[TimedLine] = []
    for line in lines:
        syls = list(line.syllables)
        if not syls:
            out.append(line)
            continue
        # group into words (new word = leading space)
        words: list[list[Syllable]] = []
        for s in syls:
            if not words or s.text.startswith(" "):
                words.append([s])
            else:
                words[-1].append(s)
        new: list[Syllable] = []
        try:
            for group in words:
                text_value = "".join(s.text for s in group)
                leading = " " if text_value.startswith(" ") else ""
                bare = text_value.strip()
                ws, we = group[0].start, group[-1].end
                crowd = any(s.crowd for s in group)
                # B485: without this the mark was lost in the phonetic
                # step - and that runs on EVERY freshly generated timing,
                # so no file had it.
                background = any(s.bg for s in group)
                had_stress = any(s.stress for s in group)
                held = group[0].held
                if "_" in bare:
                    # B252: an underscore word ("'k_heb") is deliberately
                    # one syllable; do not split it phonetically.
                    new.append(Syllable(text=leading + bare, start=ws,
                                          end=we, held=held, stress=had_stress,
                                          crowd=crowd, bg=background))
                    continue
                segs = phonetics.distribute_word(bare, ws, we, language, config)
                # stress -> heaviest vowel segment
                cfg = config or phonetics.SegmentConfig()
                stress = None
                if had_stress:
                    best = -1.0
                    for k, (seg, _s, _e) in enumerate(segs):
                        if phonetics._is_vowel_segment(seg):
                            g = phonetics.segment_weight(seg, cfg)
                            if g > best:
                                best, stress = g, k
                for k, (seg, s0, e0) in enumerate(segs):
                    txt = (leading + seg) if k == 0 else seg
                    new.append(Syllable(text=txt, start=s0, end=e0,
                                          held=held, stress=(k == stress),
                                          crowd=crowd, bg=background))
            out.append(replace(line, syllables=tuple(new)))
        except Exception:  # noqa: BLE001 - segmentation must never break
            logger.exception(t("log_phonetic_segmentation_skipped"))
            out.append(line)
    return tuple(out)


def timedline_from_text(index: int, text: str, start: float, end: float,
                        crowd: bool = False) -> TimedLine:
    """Build a ``TimedLine`` from plain text with evenly spread syllable
    timing (B201). Used for the original lines in the stress editor, on
    which the user can set the stress.

    ``Syllable.lang`` stays ``False`` here: that field means "long held
    note" (which is underlined in the render), not a language code. It
    previously said ``lang="nl"`` - a confusion with the language
    parameter elsewhere in this module - and because a non-empty string
    is truthy, EVERY syllable counted as a held note and was therefore
    underlined as soon as the video of the original lyrics was rendered
    (B289).
    """
    pieces = split_line(text) or [text or " "]
    n = max(1, len(pieces))
    span = max(float(end) - float(start), 0.001)
    syls = []
    for i, piece in enumerate(pieces):
        s = start + span * i / n
        e = start + span * (i + 1) / n
        syls.append(Syllable(text=piece, start=round(s, 3), end=round(e, 3),
                             held=False))
    return TimedLine(index=index, text=text, crowd=crowd,
                     syllables=tuple(syls))


#: View modes for the timing editor (B127): whole blocks, individual
#: sentences or separate words.
VIEW_MODES = ("blocks", "sentences", "words")


def apply_inline_crowd(lines: Sequence[TimedLine],
                       text_lines: Sequence) -> tuple[TimedLine, ...]:
    """Mark syllables of inline crowd and bg words (B179a/B485).

    ``text_lines`` are the source ``TextLine``s with ``crowd_words`` and
    ``bg_words`` (word indexes of an inline piece). The matching
    syllables get ``crowd=True`` so that they turn red in the render, or
    ``bg=True`` so that they stay out of it. A whole crowd line runs via
    ``TimedLine.crowd``; a whole ``[bg]`` line gets ``TimedLine.bg`` here
    (B510), read from the text and not from what the timing file says,
    because the text is where that truth lives.
    """
    crowd_per_index = {tl.index: getattr(tl, "crowd_words", frozenset())
                       for tl in text_lines
                       if getattr(tl, "crowd_words", None)}
    bg_per_index = {tl.index: getattr(tl, "bg_words", frozenset())
                    for tl in text_lines
                    if getattr(tl, "bg_words", None)}
    # B510: also when there is no inline piece anywhere - a text of
    # nothing but whole [bg] lines has neither, and that is exactly the
    # case that must not be skipped.
    whole_bg = {tl.index for tl in text_lines if getattr(tl, "bg", False)}
    known = {tl.index for tl in text_lines}
    counts = {tl.index: len(str(tl.text).split()) for tl in text_lines}
    out: list[TimedLine] = []
    for line in lines:
        crowd_words = crowd_per_index.get(line.index) or frozenset()
        bg_words = bg_per_index.get(line.index) or frozenset()
        # A line the text no longer knows keeps what it had; for the
        # rest the text decides, so unmarking works as well as marking.
        line = (replace(line, bg=line.index in whole_bg)
                if line.index in known else line)
        if not crowd_words and not bg_words:
            out.append(line)
            continue
        # B485: word numbers from the text laid onto the timing only work
        # while the two still say the same thing. Does the line have a
        # different number of words, then the text is ahead of the timing
        # and marking would land on the wrong word - and a word wrongly
        # marked bg vanishes from the render altogether.
        own = sum(1 for pos, item in enumerate(line.syllables)
                  if pos == 0 or item.text.startswith(" "))
        if counts.get(line.index) not in (None, own):
            logger.warning(t("log_inline_mark_skipped"), line.index)
            out.append(line)
            continue
        new: list[Syllable] = []
        wi = -1
        for s in line.syllables:
            if wi == -1 or s.text.startswith(" "):
                wi += 1
            new.append(replace(s, crowd=(wi in crowd_words),
                               bg=(wi in bg_words)))
        out.append(replace(line, syllables=tuple(new)))
    return tuple(out)


#: A syllable has to last at least this long before "held" means
#: anything. In a fast song every syllable is short and the ratio below
#: fires on nothing special; this is the floor under it (B441).
HELD_MIN_S = 0.35

#: And it has to last this many times the median syllable of its OWN
#: line. Relative on purpose: a slow ballad has long syllables
#: everywhere, and then none of them is remarkable.
HELD_FACTOR = 4.0

#: Under this many syllables a line has no usable median - two
#: syllables and the median sits exactly between them, so one of the two
#: is always four times "the middle" or neither ever is.
HELD_MIN_SYLLABLES = 3


def mark_held(lines: Sequence[TimedLine],
              min_length: float = HELD_MIN_S,
              factor: float = HELD_FACTOR) -> tuple[TimedLine, ...]:
    """Mark syllables that are genuinely stretched out (B441).

    ``Syllable.held`` has existed for a long time and the render has
    drawn a line under a held syllable for just as long - but nothing
    ever set the field. Over fourteen thousand syllables in seventeen
    projects there was not one, so that piece of the render had never
    run.

    The rule is the one the 1.5.7 inventory measured, unchanged, because
    that is the rule the numbers came from: a syllable counts as held
    when it lasts at least ``min_length`` AND at least ``factor`` times
    the median syllable of its own line. Over all projects that marks
    7.0% of the syllables, and they were vowels top to bottom - which is
    what you would hope for, since a consonant cannot be held.

    A pause is skipped. It is long by its nature, it is drawn as
    lighting dots and not as text, and an underline under a pause would
    be a line under nothing.
    """
    result: list[TimedLine] = []
    for line in lines:
        # B485: an inline [bg] piece is not sung along with and is not in
        # the picture, so it must not sit in the median of this sentence
        # nor be marked itself.
        spans = [s.end - s.start for s in line.syllables if not s.bg]
        if len(spans) < HELD_MIN_SYLLABLES:
            result.append(replace(
                line, syllables=tuple(replace(s, held=False)
                                      for s in line.syllables)))
            continue
        middle = statistics.median(spans)
        new = []
        for syllable in line.syllables:
            span = syllable.end - syllable.start
            held = (not syllable.bg and middle > 0 and span >= min_length
                    and span >= factor * middle
                    and not is_pause(syllable.text))
            new.append(replace(syllable, held=bool(held)))
        result.append(replace(line, syllables=tuple(new)))
    return tuple(result)


#: No piece may be squeezed below this. Same floor the shape checks use
#: (``timing_checks.MIN_SYLLABLE_S``), so that fitting can never produce
#: something those checks would then flag as broken.
MIN_PIECE_S = 0.05


def fit_between_anchors(spans, anchors, floor: float = MIN_PIECE_S):
    """Pin the anchors, let the rest give way (B450).

    ``spans`` are the ``(start, end)`` pairs of one sentence, in order.
    ``anchors`` is ``{index: (start, end)}`` - the pieces that are
    coupled to the original and therefore keep exactly that time. Every
    run of pieces between two anchors is redistributed over what is left
    over, in proportion to the durations they already had, so the rhythm
    within such a run survives.

    The sentence keeps its own beginning and end: what happens here is a
    redistribution, never a shift of the line.

    Returns ``(new_spans, shortfall)``. ``shortfall`` is the number of
    seconds that could not be given away because the floor was reached -
    zero means everything fitted. The caller reports it rather than
    quietly breaking through the floor: too many anchors in one line is
    a thing the user has to see, not something to paper over.
    """
    spans = [(float(a), float(b)) for a, b in spans]
    if not spans:
        return [], 0.0
    low_edge, high_edge = spans[0][0], spans[-1][1]
    result = list(spans)

    # The anchors come from the editor, where the user couples in any
    # order he likes and may point two karaoke pieces at the same piece
    # of the original. Neither is a mistake to refuse - but both would
    # produce a sentence with times running backwards, and that is the
    # one thing this function promises never to do. So: walk them in
    # order, keep every anchor inside the sentence, and let a later one
    # give way to the one before it rather than crossing it.
    fixed: list[int] = []
    previous = low_edge
    for index in sorted(i for i in (anchors or {}) if 0 <= i < len(spans)):
        start, end = (float(v) for v in anchors[index])
        if end < start:
            start, end = end, start
        start = min(max(start, previous), high_edge)
        end = min(max(end, start), high_edge)
        if end <= start and index != len(spans) - 1:
            # No room left for this one; the sentence has been claimed
            # up to here. Dropping it is honest - it is reported through
            # the shortfall below.
            continue
        result[index] = (start, end)
        fixed.append(index)
        previous = end
    shortfall = sum(1 for i in (anchors or {})
                    if 0 <= i < len(spans) and i not in fixed) * floor
    # Walk the runs BETWEEN the anchors: from the end of the previous
    # anchor (or the start of the sentence) to the start of the next one
    # (or the end of the sentence).
    edges = [-1] + fixed + [len(spans)]
    for left, right in zip(edges, edges[1:]):
        piece_range = range(left + 1, right)
        count = len(piece_range)
        if count <= 0:
            continue
        low = result[left][1] if left >= 0 else low_edge
        high = result[right][0] if right < len(spans) else high_edge
        if high < low:
            high = low
        room = max(0.0, high - low)
        weights = [max(1e-6, spans[i][1] - spans[i][0]) for i in piece_range]
        total = sum(weights)
        if room < count * floor:
            # Not enough room to give everyone the floor. Then it is
            # divided evenly over what there IS, and the difference is
            # reported. Squeezing is bad; running past the end of the
            # sentence or laying pieces back to front is worse, and that
            # is what a hard floor would do here.
            shortfall += count * floor - room
            shares = [room / count] * count
        else:
            shares = [max(floor, room * w / total) for w in weights]
            # Rounding up to the floor may have made the run too long;
            # take that back off the widest pieces.
            excess = sum(shares) - room
            while excess > 1e-9:
                widest = max(range(count), key=lambda n: shares[n])
                give = min(excess, shares[widest] - floor)
                if give <= 1e-9:
                    break
                shares[widest] -= give
                excess -= give
        moment = low
        for n, i in enumerate(piece_range):
            end_of = high if n == count - 1 else moment + shares[n]
            result[i] = (round(moment, 3), round(min(end_of, high), 3))
            moment = min(end_of, high)

    # The contract, enforced rather than hoped for: the sentence keeps
    # its own beginning and end, and nothing runs backwards. An anchor on
    # the first or last piece may move the pieces INSIDE the sentence,
    # never the sentence itself - what hangs off the line span (the
    # render, the checks, the yardstick) would otherwise silently shift.
    return _inside_the_line(result, low_edge, high_edge), round(shortfall, 3)


def _inside_the_line(spans, low: float, high: float):
    """Every span in order and within ``low``..``high`` (B450)."""
    out = []
    moment = low
    for start, end in spans:
        start = min(max(float(start), moment), high)
        end = min(max(float(end), start), high)
        out.append((round(start, 3), round(end, 3)))
        moment = end
    if out:
        out[0] = (round(low, 3), max(round(low, 3), out[0][1]))
        out[-1] = (min(out[-1][0], round(high, 3)), round(high, 3))
    return out


def apply_spans(line: TimedLine, spans) -> TimedLine:
    """A line with these ``(start, end)`` pairs on its pieces (B450).

    B485: an inline ``[bg]`` piece keeps its own times. The refit works
    within the window of the sentence and would pull the background
    vocals back inside it, while they are precisely allowed to lie over
    the neighbours.
    """
    return replace(line, syllables=tuple(
        syllable if syllable.bg
        else replace(syllable, start=float(a), end=float(b))
        for syllable, (a, b) in zip(line.syllables, spans)))


def held_words(line: TimedLine) -> frozenset:
    """The word numbers in this line that contain a held syllable (B441).

    The word coupling works per word and the mark sits per syllable, so
    somebody has to translate. Same counting as everywhere else: a new
    word starts at a syllable whose text begins with a space.
    """
    found = set()
    number = -1
    for syllable in line.syllables:
        if number == -1 or syllable.text.startswith(" "):
            number += 1
        if syllable.held:
            found.add(number)
    return frozenset(found)


def apply_default_stress(lines: Sequence[TimedLine]) -> tuple[TimedLine, ...]:
    """Mark a default stress per word (B151).

    Dutch is predominantly trochaic: as a first approximation the first
    syllable of every polysyllabic word gets the stress. The user
    corrects the exceptions in the stress editor. Monosyllabic words get
    no accent.
    """
    result: list[TimedLine] = []
    for line in lines:
        syls = list(line.syllables)
        # Word boundaries: a syllable that starts with a space (or the
        # first one) starts a new word.
        starts = [i for i, s in enumerate(syls)
                  if i == 0 or s.text.startswith(" ")]
        marks: dict[int, bool] = {}
        for w, start in enumerate(starts):
            end = starts[w + 1] if w + 1 < len(starts) else len(syls)
            multi_syllable = (end - start) >= 2
            for j in range(start, end):
                marks[j] = (j == start and multi_syllable)
        new = tuple(replace(s, stress=marks.get(i, False))
                      for i, s in enumerate(syls))
        result.append(replace(line, syllables=new))
    return tuple(result)


def redistribute_by_stress(lines: Sequence[TimedLine],
                           weight: float = 1.6) -> tuple[TimedLine, ...]:
    """Weigh stressed syllables heavier in the duration split (B151).

    Only for best-effort lines (quality not ``high``/``syllable``):
    there the syllables are spread evenly and the stress helps to make
    the rhythm more natural (a stressed syllable lasts a bit longer). The
    line span (start/end) stays exactly the same, so that manually set
    times and the coupling do not shift; reliable (forced-alignment)
    lines are left untouched.
    """
    out: list[TimedLine] = []
    for line in lines:
        syls = line.syllables
        if (line.quality in ("high", "syllable") or len(syls) < 2
                or not any(s.stress for s in syls)):
            out.append(line)
            continue
        start, end = line.start, line.end
        span = max(end - start, 0.0)
        weight_map = [weight if s.stress else 1.0 for s in syls]
        total = sum(weight_map) or 1.0
        new: list[Syllable] = []
        cum = 0.0
        for s, g in zip(syls, weight_map):
            s_start = start + span * cum / total
            cum += g
            s_end = start + span * cum / total
            new.append(replace(s, start=round(s_start, 3),
                                 end=round(s_end, 3)))
        out.append(replace(line, syllables=tuple(new)))
    return tuple(out)


def _word_bounds(syllables: Sequence[Any], index: int) -> tuple[int, int]:
    """Start and end index (exclusive) of the word ``index`` falls in."""
    def leads_in(i: int) -> bool:
        s = syllables[i]
        text_value = s["text"] if isinstance(s, dict) else s.text
        return i == 0 or text_value.startswith(" ")
    start = index
    while start > 0 and not leads_in(start):
        start -= 1
    end = index + 1
    while end < len(syllables) and not leads_in(end):
        end += 1
    return start, end


def set_word_stress(syllables: Sequence[Syllable], index: int
                    ) -> tuple[Syllable, ...]:
    """Set the stress on syllable ``index`` within its word (B151).

    Exactly one syllable per word can carry the stress. Clicking the
    already stressed syllable removes the stress again (toggle).
    """
    syls = list(syllables)
    if not (0 <= index < len(syls)):
        return tuple(syls)
    start, end = _word_bounds(syls, index)
    switch_on = not syls[index].stress
    for j in range(start, end):
        syls[j] = replace(syls[j], stress=(j == index and switch_on))
    return tuple(syls)


def _syl_field(syl: Any, item_name: str) -> Any:
    return syl[item_name] if isinstance(syl, dict) else getattr(syl, item_name)


def stress_fraction(syllables: Sequence[Any]) -> float | None:
    """Relative position (0..1) of the middle of the stressed syllable
    within the line (B202). ``None`` if there is no stress or no
    duration."""
    if not syllables:
        return None
    start = float(_syl_field(syllables[0], "start"))
    end = float(_syl_field(syllables[-1], "end"))
    span = end - start
    if span <= 0:
        return None
    for syl in syllables:
        if _syl_field(syl, "stress"):
            mid = (float(_syl_field(syl, "start"))
                   + float(_syl_field(syl, "end"))) / 2.0
            return (mid - start) / span
    return None


def shift_stress_to(line: TimedLine, target_rel: float,
                    max_slots: int = 1) -> TimedLine:
    """Shift the TIMING of the stressed syllable towards ``target_rel``
    (B202).

    Shifts only the times - not the text or the ordering - and keeps the
    line start/end and the number of syllables equal. The shift is
    bounded to ``max_slots`` average syllable widths ('at most one
    slot'). This way the karaoke stress aligns better with that of the
    original when the karaoke has extra syllables.
    """
    syls = list(line.syllables)
    n = len(syls)
    if n < 2:
        return line
    stressed = next((i for i, s in enumerate(syls) if s.stress), None)
    if stressed is None:
        return line
    start, end = syls[0].start, syls[-1].end
    span = end - start
    if span <= 0:
        return line
    cur_rel = ((syls[stressed].start + syls[stressed].end) / 2.0 - start) / span
    avg = span / n
    stress_shift = (target_rel - cur_rel) * span
    bound = max_slots * avg
    stress_shift = max(-bound, min(bound, stress_shift))
    if abs(stress_shift) < 1e-3:
        return line
    minw = min(0.05, avg / 2.0)
    new_s = syls[stressed].start + stress_shift
    new_e = syls[stressed].end + stress_shift
    if stressed > 0:
        new_s = max(syls[stressed - 1].start + minw, new_s)
    else:
        new_s = max(start, new_s)
    if stressed < n - 1:
        new_e = min(syls[stressed + 1].end - minw, new_e)
    else:
        new_e = min(end, new_e)
    if new_e - new_s < minw:
        return line
    syls[stressed] = replace(syls[stressed], start=round(new_s, 3),
                             end=round(new_e, 3))
    if stressed > 0:
        syls[stressed - 1] = replace(syls[stressed - 1], end=round(new_s, 3))
    if stressed < n - 1:
        syls[stressed + 1] = replace(syls[stressed + 1], start=round(new_e, 3))
    return replace(line, syllables=tuple(syls))


def align_karaoke_stress(karaoke_lines: Sequence[TimedLine],
                         original_lines: Sequence[TimedLine],
                         mapping: dict[int, int],
                         max_slots: int = 1) -> tuple[TimedLine, ...]:
    """Align the karaoke stress with the original per coupled line (B202).

    ``mapping`` couples karaoke line index -> original line index. For
    every karaoke line with a coupled original line the karaoke stress is
    shifted (via :func:`shift_stress_to`) at most one slot towards the
    relative stress position of the original. Lines without a coupling or
    without a stress are left untouched.
    """
    original_frac = {i: stress_fraction(ln.syllables)
                      for i, ln in enumerate(original_lines)}
    shifted_lines: list[TimedLine] = []
    for ki, line in enumerate(karaoke_lines):
        oi = mapping.get(ki)
        target = original_frac.get(oi) if oi is not None else None
        if target is None:
            shifted_lines.append(line)
        else:
            shifted_lines.append(shift_stress_to(line, target, max_slots=max_slots))
    return tuple(shifted_lines)


def word_spans(syllables: Sequence[Any]
               ) -> list[tuple[str, float, float]]:
    """Group syllables into words (on the leading-space boundary).

    ``syllables`` may contain syllable objects (with ``text/start/end``)
    or dicts (with ``"text"/"start"/"end"``). ``split_line`` marks the
    start of a new word with a leading space.
    """
    def field(syl: Any, item_name: str) -> Any:
        return syl[item_name] if isinstance(syl, dict) else getattr(syl, item_name)

    words: list[tuple[str, float, float]] = []
    text_value = ""
    start: float | None = None
    end = 0.0
    for syl in syllables:
        piece = str(field(syl, "text"))
        if piece.startswith(" ") and start is not None:
            words.append((text_value.strip(), start, end))
            text_value, start = "", None
        if start is None:
            start = float(field(syl, "start"))
        text_value += piece
        end = float(field(syl, "end"))
    if start is not None:
        words.append((text_value.strip(), start, end))
    return words


def piece_groups(syllables: Sequence[Any]) -> list[list[int]]:
    """Indexes of the stored pieces per word, on the same boundary that
    ``word_spans`` uses (B347).

    Needed because the stored pieces are finer than the syllables that
    ``split_line`` derives from a word text ("Zangers" is six pieces and
    two syllables). Anyone who wants to redistribute the pieces has to
    count what is there, not what the text suggests.
    """
    def field(syl: Any, item_name: str) -> Any:
        return syl[item_name] if isinstance(syl, dict) else getattr(syl, item_name)

    groups: list[list[int]] = []
    for index, syl in enumerate(syllables):
        if not groups or (str(field(syl, "text")).startswith(" ") and groups[-1]):
            groups.append([])
        groups[-1].append(index)
    return groups


def _sung_of(line) -> list:
    """The syllables that make up the sentence itself (B507).

    An inline ``[bg]`` piece belongs to the line but is allowed to lie
    over its neighbours, so it must not decide where the sentence begins
    or ends. Mirror of ``timing_editor._sung_pieces`` and of
    ``TimedLine._sung``; those two already reasoned this way while the
    cells here did not, and that difference is what made a karaoke block
    longer than the original block it is coupled to.

    Takes dicts as well as syllable objects, like ``_dict_span`` around
    it: a helper that is stricter than its caller is a trap.
    """
    def bg_of(item) -> bool:
        return bool(item.get("bg") if isinstance(item, dict)
                    else getattr(item, "bg", False))

    pieces = list(line.get("syllables") if isinstance(line, dict)
                  else getattr(line, "syllables", ()) or ())
    sung = [item for item in pieces if not bg_of(item)]
    return sung or pieces


def _whole_bg(line: dict) -> bool:
    """Is this line background vocals from beginning to end? (B507)"""
    pieces = list(line.get("syllables") or ())
    return bool(line.get("bg")) or bool(
        pieces and all(item.get("bg") for item in pieces))


def _bg_cell(line: dict) -> dict | None:
    """The inline ``[bg]`` piece of one line as its own cell (B507).

    Shown in every view, because the user wants to see background vocals
    everywhere except in the render, and it may lie over its neighbours.
    ``rows`` is empty on purpose: it is drawn, not dragged - dragging a
    sentence still moves the whole line, background piece and all.
    """
    pieces = [item for item in (line.get("syllables") or ())
              if item.get("bg")]
    if not pieces or len(pieces) == len(line.get("syllables") or ()):
        return None
    return {"text": "".join(str(item["text"]) for item in pieces).strip(),
            "start": min(float(item["start"]) for item in pieces),
            "end": max(float(item["end"]) for item in pieces),
            "crowd": False, "rows": [], "off": bool(line.get("disabled")),
            "bg": True}


def editor_view_cells(lines: Sequence[dict],
                      mode: str = "sentences") -> list[dict]:
    """Build drawable cells for the timing editor in the chosen view.

    ``lines`` are the editor line dicts (``text``, ``crowd``,
    ``syllables`` and optionally ``blok``). Returns per cell a dict with
    ``text``, ``start``, ``end`` and ``crowd`` (B127). An inline ``[bg]``
    piece gets a cell of its own in every view (B507).
    """
    if mode == "words":
        cells: list[dict] = []
        for pos, line in enumerate(lines):
            groups = piece_groups(line["syllables"])
            spans = word_spans(line["syllables"])
            for (text_value, start, end), group in zip(spans, groups):
                background = all(
                    line["syllables"][i].get("bg") for i in group)
                cells.append({"text": text_value, "start": start, "end": end,
                               "crowd": bool(line["crowd"]),
                               "rows": [] if background else [pos],
                               "off": bool(line.get("disabled")),
                               "bg": background})
        return cells
    if mode == "blocks":
        cells = []
        current: list[tuple[int, dict]] = []
        block_id = None

        def close(group: list[tuple[int, dict]]) -> None:
            cells.append(_block_cell(group))
            for _pos, line in group:
                cell = _bg_cell(line)
                if cell is not None:
                    cells.append(cell)

        for pos, line in enumerate(lines):
            b = line.get("block", 0)
            if current and b != block_id:
                close(current)
                current = []
            block_id = b
            current.append((pos, line))
        if current:
            close(current)
        return cells
    # "sentences" (default): one cell per line, with the background
    # piece right behind it so the two stay next to each other.
    cells = []
    for pos, line in enumerate(lines):
        start, end = _dict_span(line)
        cells.append({"text": line["text"], "start": start, "end": end,
                       "crowd": bool(line["crowd"]),
                       "rows": [pos], "off": bool(line.get("disabled")),
                       # B507: a whole background line is drawn as
                       # background - it is one - but it keeps its rows,
                       # so it stays draggable like any other sentence.
                       "bg": _whole_bg(line),
                       "restore": bool(line.get("restore"))})   # B496
        cell = _bg_cell(line)
        if cell is not None:
            cells.append(cell)
    return cells


def original_view_cells(originals: Sequence[dict], mode: str,
                        line_block: dict[int, int] | None = None
                        ) -> list[dict]:
    """Cells for the original-text lane in the chosen view (B161).

    ``originals`` = ``[{"text","start","end","rows","crowd"}]``. In word
    mode every sentence is split evenly into words; in block mode
    consecutive sentences with the same block (via ``line_blok`` on the
    first coupled karaoke line) are merged. Purely for display. ``crowd``
    marks a cell that is really karaoke-only text (a stand-alone crowd
    line, mirrored from the karaoke because it has no lyrics coupling,
    B193) so that the editor can show it visibly differently from real
    original text (B257).
    """
    line_block = line_block or {}
    if mode == "words":
        cells: list[dict] = []
        for o in originals:
            words = str(o["text"]).split()
            n = max(1, len(words))
            width = (o["end"] - o["start"]) / n
            rows = list(o.get("rows") or [])
            crowd = bool(o.get("crowd"))
            for k, w in enumerate(words):
                cells.append({"text": w,
                               "start": o["start"] + k * width,
                               "end": o["start"] + (k + 1) * width,
                               "rows": rows, "crowd": crowd})
        return cells
    if mode == "blocks":
        cells = []
        group: list[dict] = []
        block = None
        for o in originals:
            rows = o.get("rows") or []
            b = line_block.get(rows[0], 0) if rows else 0
            if group and b != block:
                cells.append(_original_block(group))
                group = []
            block = b
            group.append(o)
        if group:
            cells.append(_original_block(group))
        return cells
    return [{"text": o["text"], "start": o["start"], "end": o["end"],
             "rows": list(o.get("rows") or []), "crowd": bool(o.get("crowd"))}
            for o in originals]


def _original_block(originals: list[dict]) -> dict:
    rows: list[int] = []
    for o in originals:
        rows.extend(o.get("rows") or [])
    return {"text": " ".join(o["text"] for o in originals),
            "start": min(o["start"] for o in originals),
            "end": max(o["end"] for o in originals),
            "rows": rows,
            "crowd": all(o.get("crowd") for o in originals)}


def _dict_span(line: dict) -> tuple[float, float]:
    # B507: the sentence is the SUNG part; the [bg] piece belongs to it
    # but does not decide its edges.
    syls = _sung_of(line)
    if not syls:
        return 0.0, 0.0
    first, last = syls[0], syls[-1]
    fs = first["start"] if isinstance(first, dict) else first.start
    le = last["end"] if isinstance(last, dict) else last.end
    return float(fs), float(le)


def _block_cell(items: list[tuple[int, dict]]) -> dict:
    lines = [line for _pos, line in items]
    # B507: a line that is background vocals from beginning to end does
    # not decide how wide the block is either. Since B509 such a line
    # can have its own place far away from its block, and then it
    # stretched the block over the gap - and dragging it scaled every
    # sentence in it over those seconds.
    sung = [line for line in lines if not _whole_bg(line)] or lines
    spans = [_dict_span(line) for line in sung]
    start = min(s for s, _ in spans)
    end = max(e for _, e in spans)
    # B163: full block text (all lines joined), not just the first one.
    text_value = " ".join(line["text"] for line in lines)
    return {"text": text_value, "start": start, "end": end,
            "crowd": all(line["crowd"] for line in lines),
            "rows": [pos for pos, _line in items],
            "off": all(line.get("disabled") for line in lines)}


def generate_skeleton(
    lines: Sequence[TextLine],
    line_spans: dict[int, tuple[float, float]] | None = None,
    quality: str = "sentence",
) -> tuple[TimedLine, ...]:
    """Build a timing skeleton from the karaoke text.

    Args:
        lines: The logical lines (with crowd marking).
        line_spans: Optionally a (start, end) per line index on the
            karaoke timeline; syllables are spread evenly over it.
            Without times all times are 0 (to be filled in by hand or
            shifted later).

    Returns:
        The timed lines (``lang`` is ``False`` everywhere).
    """
    result: list[TimedLine] = []
    for line in lines:
        pieces = split_line(line.text)
        span = (line_spans or {}).get(line.index)
        syllables: list[Syllable] = []
        for position, piece in enumerate(pieces):
            if span is not None and pieces:
                width = (span[1] - span[0]) / len(pieces)
                start = span[0] + position * width
                end = start + width
            else:
                start = end = 0.0
            syllables.append(Syllable(text=piece, start=round(start, 3),
                                      end=round(end, 3)))
        result.append(TimedLine(index=line.index, text=line.text,
                                crowd=line.crowd,
                                syllables=tuple(syllables),
                                quality=quality,
                                block=getattr(line, "block", 0)))
    return tuple(result)


def best_effort_skeleton(
    lines: Sequence[TextLine],
    original_lines: Sequence[Sequence[tuple[str, float, float]]],
    project=None,
) -> tuple[tuple[TimedLine, ...], dict[str, int]]:
    """Best-effort timing from the original lyrics alignment.

    Every karaoke line is guaranteed its own, consecutive time slot and
    the ordering is preserved exactly. The lines are coupled
    (proportionally, in order) to the timed lyrics lines; if several
    karaoke lines share the same original line, that time is divided
    consecutively. Cascade per line:

    1. **lettergreep** (high confidence): syllable counts equal;
    2. **woord** (medium): word counts equal;
    3. **zin** (best-effort): evenly over the line time.

    Returns:
        Tuple of (timed lines, quality tally per level).
    """
    if project is None:
        project = lambda seconds: seconds  # noqa: E731
    quality = {"syllable": 0, "word": 0, "sentence": 0}
    total_original = len(original_lines)
    assignments = line_assignments(len(lines), total_original)
    result: list[TimedLine] = []
    position = 0
    while position < len(lines):
        mapped = assignments[position]
        group = [position]
        while (position + len(group) < len(lines)
               and assignments[position + len(group)] == mapped):
            group.append(position + len(group))
        original = original_lines[mapped]
        line_start = original[0][1]
        line_end = max(original[-1][2], line_start + 0.5)

        if len(group) == 1:
            line = lines[position]
            pieces = split_line(line.text)
            spans, level = _cascade_spans(line.text, pieces, original,
                                          line_start, line_end)
            quality[level] += 1
            result.append(_build_line(line, pieces, spans, project, level))
        else:
            part = (line_end - line_start) / len(group)
            for offset, line_position in enumerate(group):
                line = lines[line_position]
                pieces = split_line(line.text)
                sub_start = line_start + offset * part
                spans = _even_spans(sub_start, sub_start + part,
                                    len(pieces))
                quality["sentence"] += 1
                result.append(_build_line(line, pieces, spans, project,
                                          "sentence"))
        position += len(group)
    logger.info(t("log_best_effort_timing"), quality)
    return tuple(result), quality


def line_assignments(total_lines: int, total_original: int) -> list[int]:
    """Couple karaoke lines proportionally (in order) to the original
    lyrics lines; the same coupling is used for the best-effort timing
    as well as for the display in the timing editor."""
    return [min(total_original - 1,
                position * total_original // max(1, total_lines))
            for position in range(total_lines)]


def remap_relative(start: float, end: float,
                   old_span: tuple[float, float],
                   new_span: tuple[float, float]) -> tuple[float, float]:
    """Map a time slot along linearly when its reference shifts.

    Used to let a karaoke sentence move along when the coupled original
    sentence is shifted or stretched.
    """
    old_start, old_end = old_span
    new_start, new_end = new_span
    scale = (new_end - new_start) / max(old_end - old_start, 1e-6)
    return (new_start + (start - old_start) * scale,
            new_start + (end - old_start) * scale)


def _cascade_spans(text: str, pieces: list[str], original,
                   line_start: float,
                   line_end: float) -> tuple[list, str]:
    """Determine syllable times following syllable -> word -> sentence."""
    original_syllables: list[tuple[float, float]] = []
    for word_text, word_start, word_end in original:
        count = max(1, len(split_syllables(word_text)))
        step = (word_end - word_start) / count
        original_syllables.extend(
            (word_start + i * step, word_start + (i + 1) * step)
            for i in range(count))
    if len(original_syllables) == len(pieces):
        return original_syllables, "syllable"

    karaoke_words = text.split()
    if len(karaoke_words) == len(original):
        spans: list[tuple[float, float]] = []
        for word_index, (_, word_start, word_end) in enumerate(original):
            count = max(1, len(split_syllables(karaoke_words[word_index])))
            step = (word_end - word_start) / count
            spans.extend((word_start + i * step,
                          word_start + (i + 1) * step)
                         for i in range(count))
        return spans, "word"
    return _even_spans(line_start, line_end, len(pieces)), "sentence"


def _even_spans(start: float, end: float,
                count: int) -> list[tuple[float, float]]:
    """Split a time slot evenly into ``count`` parts."""
    step = (end - start) / max(1, count)
    return [(start + i * step, start + (i + 1) * step)
            for i in range(count)]


def _build_line(line: TextLine, pieces: list[str], spans, project,
                level: str) -> TimedLine:
    syllables = tuple(
        Syllable(text=piece, start=round(project(span[0]), 3),
                 end=round(project(span[1]), 3))
        for piece, span in zip(pieces, spans))
    return TimedLine(index=line.index, text=line.text, crowd=line.crowd,
                     syllables=syllables, quality=level,
                     block=getattr(line, "block", 0))


def fallback_even(lines: Sequence[TextLine],
                  duration: float) -> tuple[TimedLine, ...]:
    """Emergency timing without alignment: lines evenly over the song.

    Never zeros; always a starting point that is refined with the timing
    editor. Without lyrics/transcription there is no ``couple_timing``
    coupling to hang a ``[bg]`` line (B264) on its preceding line; such a
    line therefore simply gets (for now) its own, evenly distributed time
    slot like every other line - to be corrected via the timing editor as
    soon as a coupling is available after all.
    """
    usable_start = 8.0
    usable_end = max(usable_start + 10.0, duration - 8.0)
    slot = (usable_end - usable_start) / max(1, len(lines))
    spans = {line.index: (usable_start + position * slot,
                          usable_start + position * slot + slot * 0.8)
             for position, line in enumerate(lines)}
    return generate_skeleton(lines, spans, quality="even")


def snap_time(value: float, target: float | None,
              pixels_per_second: float,
              threshold_px: float = 10.0) -> float:
    """Snap a time to a target (e.g. the playhead) when it is close
    enough on screen.

    Args:
        value: The proposed time (e.g. the new line start).
        target: The target time (playhead), or ``None``.
        pixels_per_second: Current zoom factor of the display.
        threshold_px: Snap distance in pixels.

    Returns:
        ``target`` if the difference falls within the threshold,
        otherwise ``value``.
    """
    if target is None:
        return value
    if abs(value - target) * pixels_per_second <= threshold_px:
        return target
    return value


#: Shortest vocal-active window that may still carry a line of its own
#: (B310). See ``spread_over_active``.
_MIN_ACTIVE_WINDOW_S = 0.3


def spread_over_active(count: int,
                       windows: Sequence[tuple[float, float]],
                       weights: Sequence[float] | None = None
                       ) -> list[tuple[float, float]]:
    """Divide ``count`` consecutive lines over vocal-active windows (B310).

    Used for a series of lines that Whisper transcribed nothing for
    (la-la-la, na-na-na, a shouting crowd). Distributing them evenly over
    the whole gap puts lines over instrumental silences as well; here
    only the time in which the vocals really sound counts.

    The lines are divided over the windows in proportion to their
    duration, and within a window spread evenly. Deliberately NO line
    straddles a pause: a boundary that falls just before the end of a
    window gives a line of a few tenths of a second, which the shortening
    step (B224) subsequently cuts back even further. Each window gets at
    least one line; if there are more windows than lines, the windows
    with the smallest pause between them are merged first, so that
    exactly the clearest pauses survive (the same approach as
    :func:`distribute_over_windows`).

    Args:
        count: Number of lines to be placed (at least 1).
        windows: The (start, end) spans where the vocals sound, in order.
        weights: Optional relative duration per slot (B318), e.g. the
            syllable count of a word. Without them every slot gets an
            equal share.

    Returns:
        ``count`` time slots, or an empty list if there is nothing to
        distribute (then the caller keeps its own interpolation).
    """
    usable = [(float(s), float(e)) for s, e in windows if e > s]
    if count < 1 or not usable:
        return []
    slot_shares = _slot_weights(count, weights)
    # A window shorter than a line may never claim a line of its own
    # (B310). Clipping to the gap regularly leaves a sliver of a few
    # hundredths of a second at the edge; with "every window at least one
    # line" that sliver would swallow a whole line. If everything is that
    # short, only the longest window remains.
    long_enough = [w for w in usable if w[1] - w[0] >= _MIN_ACTIVE_WINDOW_S]
    usable = long_enough or [max(usable, key=lambda w: w[1] - w[0])]
    while len(usable) > count and len(usable) > 1:
        _, merged = min((usable[i + 1][0] - usable[i][1], i)
                        for i in range(len(usable) - 1))
        usable[merged] = (usable[merged][0], usable[merged + 1][1])
        del usable[merged + 1]

    total = sum(e - s for s, e in usable)
    if total <= 0:
        return []
    shares = [(e - s) / total * count for s, e in usable]
    per_window = [max(1, int(round(share))) for share in shares]
    # Round-off correction: the total has to be exactly ``count``. Take
    # away from (or give to) the window whose allocation deviates most
    # from its proportional share, so the distribution stays as close as
    # possible to the sung duration.
    while sum(per_window) > count:
        index = max((n - shares[i], i) for i, n in enumerate(per_window)
                    if n > 1)[1]
        per_window[index] -= 1
    while sum(per_window) < count:
        index = max((shares[i] - n, i)
                    for i, n in enumerate(per_window))[1]
        per_window[index] += 1

    slots: list[tuple[float, float]] = []
    placed = 0
    for (start, end), number in zip(usable, per_window):
        # B318: within a window divide by WEIGHT instead of equally.
        # "Espagna" used to get exactly as much time as "e", while it has
        # three syllables against one. The weights are the syllable
        # counts; without them (or with only zeros) it falls back on an
        # equal division, which is what it used to be.
        shares = (slot_shares[placed:placed + number]
                  or [1.0] * number)
        total_share = sum(shares) or float(number)
        position = start
        for weight in shares:
            length = (end - start) * (weight / total_share)
            slots.append((position, max(position + 0.1, position + length)))
            position += length
        placed += number
    return slots


def _slot_weights(count: int, weights: Sequence[float] | None
                  ) -> list[float]:
    """Usable weights per slot (B318); equal shares if none are given."""
    if not weights or len(weights) != count:
        return [1.0] * count
    cleaned = [max(float(w), 0.1) for w in weights]
    return cleaned if any(w > 0 for w in cleaned) else [1.0] * count


def windows_between(count: int,
                    windows: Sequence[tuple[float, float]],
                    after: float, before: float) -> list[float] | None:
    """Start times for ``count`` lines over the singing in a hole (B392).

    The middle brother of :func:`tail_over_windows`. B336 already gave
    the TAIL its measured windows, but a hole halfway through the song
    still got a straight line drawn through it - ``interpolate_spans``
    spreads such a run evenly between the two surrounding anchors, and
    knows nothing about where anybody is actually singing.

    Measured over thirteen projects with hand-corrected timing that is
    where the damage sits. A quarter of all lines lands more than a
    second off, and those errors are not scattered: they come in runs of
    4.16 lines on average, one of 39 consecutive lines. Split by whether
    a line has its own anchor: 17% of anchored lines are more than a
    second off against 75% of the anchorless ones. So it is not the
    coupling that drifts, it is the filling-in between anchors.

    The measurement also says exactly where the answer is. On
    Lied_P four of the eight anchorless lines sit within 0.22 s
    of a measured vocal onset and two within 0.03 s - and those two were
    the worst drifters, fourteen and eleven seconds late.

    Deliberately the same shape as B336, including its refusal: one line
    per sung window, and ``None`` as soon as the windows do not explain
    the run exactly. Better to keep the old interpolation than to be
    confidently wrong - a wrong window is worse than a straight line,
    because it looks measured.
    """
    if count <= 0 or not windows:
        return None
    inside = []
    for start, end in windows:
        start, end = float(start), float(end)
        if start >= after and end <= before and end > start:
            inside.append((start, end))
    if len(inside) != count:
        return None
    return [start for start, _end in inside]


def interpolate_spans(
    spans: Sequence[tuple[float | None, float | None]],
    windows: Sequence[tuple[float, float]] = (),
) -> list[tuple[float, float]]:
    """Fill missing time slots (None) by interpolation.

    Lines that Whisper could not couple anything to (typically garbled
    choruses) still get a plausible time slot. Gaps BETWEEN two anchors
    are distributed linearly over the intervening space. A run at the
    START or END (no anchor on one side) is not stretched to 0 or to the
    end of the song, but gets an estimated duration (the median duration
    of lines that were coupled) and is placed against the nearest
    anchor.

    Returns:
        A list of the same length in which all time slots are filled in.
        Without any coupled line: an empty list.
    """
    reliable = [(i, s, e) for i, (s, e) in enumerate(spans)
                if s is not None and e is not None]
    if not reliable:
        return []
    durations = [e - s for _, s, e in reliable if e > s]
    typical = sorted(durations)[len(durations) // 2] if durations else 2.0
    typical = max(typical, 0.3)

    result: list[tuple[float, float]] = [(0.0, 0.0)] * len(spans)
    for i, s, e in reliable:
        result[i] = (float(s), float(e))

    i = 0
    while i < len(spans):
        if spans[i][0] is not None:
            i += 1
            continue
        run_start = i
        while i < len(spans) and spans[i][0] is None:
            i += 1
        run_end = i  # exclusive
        length = run_end - run_start
        prev = next((r for r in reversed(reliable) if r[0] < run_start),
                    None)
        nxt = next((r for r in reliable if r[0] >= run_end), None)
        if prev is not None and nxt is not None:
            left, right = prev[2], nxt[1]
            # B392: the singing beats the straight line, if and only if
            # the windows explain this run exactly.
            #
            # B540 tried to weaken that refusal: where the windows do
            # not explain the run one-to-one, divide it over them by
            # share instead (as B310 does) as soon as a quarter of the
            # hole is silence. Measured on the project it was built
            # for, Lied_T, and it made that project
            # WORSE (7.28 to 7.35 s, damage 0.69 to 0.74) while nothing
            # else moved. Worth keeping: the two anchors around
            # the hole are themselves in the wrong place, and no
            # division between two wrong ends can come out right. The
            # answer stays in the logbook; the code stays as it was.
            placed = windows_between(length, windows, left, right)
            if placed is not None:
                for k, start in enumerate(placed):
                    stop = (placed[k + 1] if k + 1 < length else right)
                    result[run_start + k] = (start, max(start + 0.1, stop))
                continue
            step = (right - left) / length
            for k in range(length):
                result[run_start + k] = (left + k * step,
                                         left + (k + 1) * step)
        elif nxt is not None:  # leading run: against the first anchor
            right = nxt[1]
            left = max(0.0, right - length * typical)
            step = (right - left) / length
            for k in range(length):
                result[run_start + k] = (left + k * step,
                                         left + (k + 1) * step)
        else:  # trailing run: from the last anchor onwards
            left = prev[2]
            for k in range(length):
                result[run_start + k] = (left + k * typical,
                                         left + (k + 1) * typical)
    return result


def _block_all_crowd(block: Sequence[TextLine]) -> bool:
    """Does this block consist wholly of crowd lines (sing-along chorus)?"""
    return bool(block) and all(line.crowd for line in block)


def couple_timing(
    karaoke_blocks: Sequence[Sequence[TextLine]],
    original_blocks: Sequence[Sequence[tuple[float, float, bool]]],
    duration: float | None = None,
    project=None,
    crowd_slot_s: float = 0.8,
    original_words: dict[int, Sequence[tuple[str, float, float]]] | None = None,
    beats: Sequence[float] | None = None,
) -> tuple[tuple[TimedLine, ...], dict[str, int], dict[int, int]]:
    """Couple karaoke lines to original lines; sentence-on-sentence where
    possible.

    Three cases, from precise to robust:

    1. **Equal number of blocks and equal number of lines per block**:
       pure 1-on-1 sentence coupling (high confidence).
    2. **Equal number of blocks** (line counts differ): per block 1-on-1
       where possible, otherwise the karaoke lines proportionally over
       the block time (medium).
    3. **Unequal number of blocks** (e.g. sections glued together in the
       lyrics): proportional coupling over all original lines (safety
       net, lower confidence).

    All times are projected and clamped to ``[0, duration]``.

    Crowd lines (block, stand-alone line or inline) simply count along in
    the line tally per block, just like vocal lines (B260): if the number
    of karaoke lines of a block (crowd included) exactly equals the
    number of original lines, every line couples 1-on-1 - including a
    stand-alone crowd line that content-wise replaces a lyrics line (e.g.
    a parody chorus in the place of "Met bloed, zweet en tranen"). If the
    count per block does not add up, a stand-alone crowd line falls back
    to a short time slot after the preceding line (the old "interjection"
    behaviour, for audience shouts like "Oeh!" that have no lyrics
    equivalent).

    Syllable distribution within a line (from fine to coarse):

    * ``original_words`` (the projected word times per flat original-line
      index): the karaoke syllables follow the rhythm of the original
      word onsets, so that held notes stay long instead of being smeared
      out evenly.
    * ``beats`` (projected beat times): rhythmic chant lines (low
      confidence, e.g. ``G Z R``) are placed on the beats.
    * otherwise: evenly over the line time (existing behaviour).

    Returns:
        Tuple of (timed lines by index, quality tally,
        mapping ``karaoke line index -> flat original line index``).
    """
    if project is None:
        project = lambda seconds: seconds  # noqa: E731
    quality = {"high": 0, "medium": 0, "low": 0}

    flat_orig = [span for block in original_blocks for span in block]
    orig_sizes = [len(block) for block in original_blocks]
    # Coupling lines per block (B260): crowd simply counts along as soon
    # as that yields an exact match with the original block (a parody
    # chorus in the place of a lyrics line, e.g. the karaoke block with 2
    # crowd lines + 3 vocal lines against a lyrics block of 5 lines). If
    # the count per block does not match (or there is no corresponding
    # original block), the old "vocal lines only" tally keeps applying
    # and a stand-alone crowd line falls back to a short interjection
    # slot (B75) - for audience shouts without a lyrics equivalent.
    karaoke_vocal = []
    for bi, block in enumerate(karaoke_blocks):
        osize = orig_sizes[bi] if bi < len(orig_sizes) else None
        if (osize is not None and len(block) == osize) or \
                _block_all_crowd(block):
            karaoke_vocal.append(list(block))
        else:
            karaoke_vocal.append([line for line in block if not line.crowd])
    kar_sizes = [len(block) for block in karaoke_vocal]

    equal_blocks = len(original_blocks) == len(karaoke_blocks)
    equal_lines = equal_blocks and orig_sizes == kar_sizes

    assign: dict[int, tuple[float, float, str]] = {}
    mapping: dict[int, int] = {}

    if equal_lines and flat_orig:
        for bi, block in enumerate(karaoke_vocal):
            base = sum(orig_sizes[:bi])
            for pos, line in enumerate(block):
                s, e, rel = flat_orig[base + pos]
                assign[line.index] = (s, e, "high" if rel else "low")
                mapping[line.index] = base + pos
    elif equal_blocks and flat_orig:
        for bi, block in enumerate(karaoke_vocal):
            oblock = original_blocks[bi]
            base = sum(orig_sizes[:bi])
            bstart, bend = oblock[0][0], oblock[-1][1]
            if len(block) == len(oblock):
                for pos, line in enumerate(block):
                    s, e, rel = oblock[pos]
                    assign[line.index] = (s, e, "high" if rel else "low")
                    mapping[line.index] = base + pos
            else:
                reliable = all(o[2] for o in oblock)
                width = (bend - bstart) / max(1, len(block))
                for pos, line in enumerate(block):
                    oi = min(len(oblock) - 1,
                             round(pos * len(oblock) / max(1, len(block))))
                    assign[line.index] = (bstart + pos * width,
                                          bstart + (pos + 1) * width,
                                          "medium" if reliable else "low")
                    mapping[line.index] = base + oi
    elif flat_orig:
        all_lines = [line for block in karaoke_vocal for line in block]
        n = len(flat_orig)
        for i, line in enumerate(all_lines):
            oi = min(n - 1, i * n // max(1, len(all_lines)))
            s, e, rel = flat_orig[oi]
            assign[line.index] = (s, e, "medium" if rel else "low")
            mapping[line.index] = oi

    # B472: a karaoke line that fell outside the coupling above had NO
    # entry at all - not even an empty one - and then the editor shows no
    # link to the original text for it. The user cannot put such a line
    # in the right place, and that is precisely what he needs the
    # original lane for. Every line therefore gets a coupling: to the
    # original line of the sentence before it (an interjection belongs
    # with the line it follows), otherwise to that of the line after it,
    # otherwise to the first one. The TIMING is not touched by this -
    # a short interjection keeps its own slot (B75); this is about
    # "which original sentence does this belong to".
    if flat_orig:
        order = [line.index for block in karaoke_blocks for line in block]
        for position, index in enumerate(order):
            if index in mapping:
                continue
            before = next((mapping[i] for i in reversed(order[:position])
                           if i in mapping), None)
            after = next((mapping[i] for i in order[position + 1:]
                          if i in mapping), None)
            mapping[index] = before if before is not None else (
                after if after is not None else 0)

    timed: list[TimedLine] = []
    last_end = 0.0
    for block in karaoke_blocks:
        for line in block:
            words = None
            # Short interjection: only if this line was not counted in
            # the block coupling above (B260) - so was not assigned a
            # lyrics equivalent. A crowd line that did couple neatly
            # 1-on-1 (``assign``) simply runs through that branch, just
            # like a vocal line or a whole crowd chorus.
            if line.crowd and line.index not in assign:
                start, end, line_quality = (last_end,
                                            last_end + crowd_slot_s,
                                         "medium")
                crowd_section = False
            else:
                start, end, level = assign.get(
                    line.index, (last_end, last_end + 1.0, "low"))
                last_end = end
                quality[level] += 1
                line_quality = level
                crowd_section = line.crowd
                if original_words is not None:
                    raw_words = original_words.get(mapping.get(line.index, -1))
                    if raw_words:
                        words = [(t, max(0.0, project(s)), max(0.0, project(e)))
                                 for t, s, e in raw_words]
            s2 = max(0.0, project(start))
            e2 = max(s2 + 0.05, project(end))
            if duration:
                e2 = min(e2, duration)
                s2 = min(s2, max(0.0, e2 - 0.05))
            timed.append(_timed_from_span(
                line, s2, e2, line_quality, original_words=words, beats=beats,
                crowd_section=crowd_section))
    timed.sort(key=lambda item: item.index)
    logger.info(t("log_sentence_coupling"), quality,
                t("value_one_to_one") if equal_lines else
                t("value_per_block") if equal_blocks
                else t("value_proportional"))
    return tuple(timed), quality, mapping


def attach_bg_lines(timed: Sequence[TimedLine],
                    bg_lines: Sequence[TextLine],
                    spans: dict[int, tuple[float, float]] | None = None
                    ) -> tuple[TimedLine, ...]:
    """Give the decoupled ``[bg]`` lines a time slot (B264/B509/B510).

    Simultaneous backing vocals do not count in ``couple_timing``: they
    would take a place of their own in the block and line counting, and
    a line that sounds OVER another one has no such place. But they do
    need a time slot, and up to v0.145.0 that slot was always the slot
    of the preceding line - which quietly assumed they always sound at
    the same time as their neighbour. They can, and they need not: at
    "Lied R" the two closing ``[bg]LIED_R[/bg]`` lines stand entirely on
    their own and have their own sentences in the lyrics.

    So: has this line been given a place of its own in ``spans`` (the
    sentence coupling found a counterpart for it, B509), then it takes
    that span. Only without one does it fall back on the line before it
    - and then it really is simultaneous. Without any preceding line (a
    bg line right at the start) it falls back on the first line.

    They are no longer switched off by default (B510). That was how they
    were kept out of the render, and it cost the user the only way to
    see where they lie: switching one on in the editor put it straight
    into the video. The render now looks at ``TimedLine.bg``, so
    ``disabled`` means again what the user means by it.

    ``timed`` contains the already coupled lines (without bg); the result
    is sorted by ``index`` again, so that ``TimedLine.index`` stays equal
    to the original ``TextLine.index`` everywhere.
    """
    ordered = sorted(timed, key=lambda item: item.index)
    result = list(timed)
    for bg_line in bg_lines:
        own = (spans or {}).get(bg_line.index)
        if own is not None:
            start, end = own
        else:
            host = None
            for candidate in reversed(ordered):
                if candidate.index < bg_line.index:
                    host = candidate
                    break
            if host is None and ordered:
                host = ordered[0]
            start, end = ((host.start, host.end) if host is not None
                          else (0.0, 1.0))
        bg_timed = _timed_from_span(bg_line, start, end, "medium")
        result.append(replace(bg_timed, bg=True))
    result.sort(key=lambda item: item.index)
    return tuple(result)


def _timed_from_span(line: TextLine, start: float, end: float,
                     quality: str,
                     original_words: Sequence[tuple[str, float, float]]
                     | None = None,
                     beats: Sequence[float] | None = None,
                     crowd_section: bool = False) -> TimedLine:
    pieces = split_line(line.text)
    spans = _syllable_spans(pieces, start, end, quality,
                            original_words, beats)
    syllables = tuple(
        Syllable(text=piece, start=round(span[0], 3), end=round(span[1], 3))
        for piece, span in zip(pieces, spans))
    return TimedLine(index=line.index, text=line.text, crowd=line.crowd,
                     syllables=syllables, quality=quality,
                     crowd_section=crowd_section,
                     block=getattr(line, "block", 0))


def _syllable_spans(pieces: Sequence[str], start: float, end: float,
                    quality: str,
                    original_words: Sequence[tuple[str, float, float]] | None,
                    beats: Sequence[float] | None
                    ) -> list[tuple[float, float]]:
    """Determine the time slots per syllable within ``[start, end]``.

    Order: word onsets (rhythm of the original) -> beats (chant) ->
    evenly (fallback). See :func:`couple_timing`.
    """
    count = len(pieces)
    if count == 0:
        return []
    if original_words:
        spans = _spans_over_words(pieces, start, end, original_words)
        if spans is not None:
            return spans
    if quality == "low" and beats:
        spans = _spans_on_beats(count, start, end, beats)
        if spans is not None:
            return spans
    return _even_spans(start, end, count)


def _karaoke_word_groups(pieces: Sequence[str]) -> list[list[int]]:
    """Group syllable indexes into karaoke words (B279).

    ``split_line`` marks the start of a new word with a leading space in
    the syllable text; that boundary is used here to split the flat
    syllable list back into words (without any times being known yet -
    hence separate from :func:`word_spans`, which expects timed
    syllables).
    """
    groups: list[list[int]] = []
    for i, piece in enumerate(pieces):
        if str(piece).startswith(" ") or not groups:
            groups.append([i])
        else:
            groups[-1].append(i)
    return groups


def _spans_over_words(pieces: Sequence[str], start: float, end: float,
                      original_words: Sequence[tuple[str, float, float]]
                      ) -> list[tuple[float, float]] | None:
    """Lay the syllables of ``pieces`` on the rhythm of the original
    words (B194/B279).

    Previously all karaoke syllables were resampled in one flat pass over
    the TOTAL original-word timeline, purely on relative position. As a
    result a short karaoke word could happen to land exactly on the
    position of an enormously stretched original word (e.g. a held final
    note) and inherit its entire duration, even though that karaoke word
    does not rhythmically belong there at all (B279).

    Now it happens in two steps: first the karaoke WORDS (``pieces``
    grouped on the leading-space boundary) are distributed proportionally
    over the original WORDS - the same kind of even distribution that is
    already used elsewhere in the codebase for lines/blocks. Only after
    that are the syllables of each karaoke word distributed over the
    matching (part of the) original word window. This way a long held
    original word stays coupled to the karaoke word that positionally
    really belongs to it, instead of a chance neighbouring syllable
    inheriting the stretched duration. With too few usable word times:
    ``None`` (fallback).
    """
    owords = [(w_start, w_end) for _text, w_start, w_end in original_words
             if w_end > w_start]
    if not owords:
        return None
    groups = _karaoke_word_groups(pieces)
    n_words = len(groups)
    n_owords = len(owords)
    total_o_start, total_o_end = owords[0][0], owords[-1][1]
    if total_o_end <= total_o_start:
        return None

    raw: list[tuple[float, float] | None] = [None] * len(pieces)
    for wi, syl_indices in enumerate(groups):
        # Proportional projection of karaoke word ``wi`` onto the series
        # of original words (same even-distribution principle as
        # elsewhere: word ``wi`` of ``n_words`` covers original words
        # ``[wi/n_words, (wi+1)/n_words) * n_owords``).
        lo_f = wi * n_owords / n_words
        hi_f = (wi + 1) * n_owords / n_words
        lo_idx = min(n_owords - 1, int(lo_f))
        hi_idx = min(n_owords - 1, max(lo_idx, int(hi_f - 1e-9)))
        word_start = owords[lo_idx][0] + (lo_f - lo_idx) * (
            owords[lo_idx][1] - owords[lo_idx][0])
        word_end = owords[hi_idx][0] + (hi_f - hi_idx) * (
            owords[hi_idx][1] - owords[hi_idx][0]) if hi_f - hi_idx < 1.0 \
            else owords[hi_idx][1]
        if word_end <= word_start:
            word_end = word_start + 0.05
        # Distribute the syllables within this karaoke word evenly over
        # [word_start, word_end).
        n_syl = len(syl_indices)
        step = (word_end - word_start) / n_syl
        for k, idx in enumerate(syl_indices):
            raw[idx] = (word_start + k * step, word_start + (k + 1) * step)

    if any(span is None for span in raw):
        return None
    return _sanitize_spans(raw, start, max(end, start + 0.05))


def _spans_on_beats(count: int, start: float, end: float,
                    beats: Sequence[float]
                    ) -> list[tuple[float, float]] | None:
    """Place ``count`` syllables on the beats within ``[start, end]``.

    Meant for rhythmic chant lines. The beat times within the line
    window are used as a grid; syllables are laid over it
    (proportionally, with interpolation). With fewer than two beats in
    the window: ``None`` (fallback to evenly).
    """
    inside = sorted(b for b in beats if start - 0.05 <= b <= end + 0.05)
    if len(inside) < 2:
        return None

    def beat_at(fraction: float) -> float:
        x = fraction * (len(inside) - 1)
        low = min(len(inside) - 1, int(x))
        high = min(len(inside) - 1, low + 1)
        return inside[low] + (x - low) * (inside[high] - inside[low])

    onsets = [beat_at(i / count) for i in range(count)]
    raw = [(onsets[i], onsets[i + 1] if i + 1 < count else end)
           for i in range(count)]
    return _sanitize_spans(raw, start, max(end, start + 0.05))


def _sanitize_spans(raw: Sequence[tuple[float, float]], low: float,
                    high: float,
                    min_length: float = 0.02) -> list[tuple[float, float]]:
    """Make time slots monotonically rising and within ``[low, high]``.

    B406: material that does not fit is COMPRESSED, no longer cut off.
    The loop below walks a cursor along and caps every slot at ``high``;
    the moment the cursor reaches that ceiling, every remaining slot
    became ``(high, high)`` - length zero, all on top of each other at
    the end of the line. On a measured song that hit fourteen words on
    three lines: five words of "en de stemming zit erin" all at exactly
    54.064 s, which reads as one flash and no karaoke at all. And it
    could not be repaired by hand either, because stretching the line
    scales the slots linearly and zero times any factor stays zero.

    So: does the material stick out of ``[low, high]``, then it is
    scaled onto that room first, and only then walked monotonically.
    Eight words in 1.18 s reads fast but it reads. As a last resort -
    so little room that not even ``min_length`` fits each - the room is
    divided evenly; that is unreadable too, but at least every syllable
    still has its own moment and the line stays repairable in the
    editor.
    """
    count = len(raw)
    if count == 0:
        return []
    room = high - low
    if room <= count * min_length:
        step = room / count
        return [(low + i * step, low + (i + 1) * step)
                for i in range(count)]

    lowest = min(s for s, _ in raw)
    highest = max(e for _, e in raw)
    if highest - lowest > 1e-9 and (lowest < low - 1e-9
                                    or highest > high + 1e-9):
        factor = room / (highest - lowest)
        raw = [(low + (s - lowest) * factor, low + (e - lowest) * factor)
               for s, e in raw]

    spans: list[tuple[float, float]] = []
    cursor = low
    for span_start, span_end in raw:
        s = min(max(span_start, cursor), high)
        e = min(max(span_end, s + min_length), high)
        cursor = e
        spans.append((s, e))
    if any(e - s < min_length - 1e-9 for s, e in spans):
        # Rounding or a heap of identical input can still squeeze a slot
        # flat. Then evenly, rather than a slot without a moment.
        step = room / count
        return [(low + i * step, low + (i + 1) * step)
                for i in range(count)]
    return spans


def _reworded(line: TimedLine, new_line, low: float,
              high: float) -> TimedLine:
    """One line with new text, evenly spread over ``[low, high]``."""
    pieces = split_line(new_line.text)
    width = (high - low) / len(pieces) if pieces else 0.0
    return TimedLine(
        index=getattr(new_line, "index", line.index), text=new_line.text,
        crowd=new_line.crowd, crowd_section=line.crowd_section,
        quality=line.quality, block=getattr(new_line, "block", line.block),
        disabled=line.disabled,
        # B510: the new TEXT says whether this is background vocals, and
        # dropping the flag here put the line back in the render.
        bg=bool(getattr(new_line, "bg", False)),
        syllables=tuple(
            Syllable(text=piece, start=round(low + position * width, 3),
                     end=round(low + (position + 1) * width, 3), held=False)
            for position, piece in enumerate(pieces)))


def carry_over(old_lines: Sequence[TimedLine], new_lines) -> list[TimedLine]:
    """Carry a hand-made timing over to a changed text (B411).

    Up to now a changed NUMBER of lines meant the timing went in the bin:
    the sentences no longer lined up one to one, so nothing could be said
    about them. That is true of the changed lines and untrue of all the
    others - and adding a chorus at the end is precisely the case where
    everything before it is still exactly right. An afternoon of
    hand-timing thrown away for four new lines is a bad trade.

    So the lines are matched on their TEXT (``difflib``): a line that
    reads the same keeps its own syllables, whatever moved around it. A
    new line gets the room between its neighbours, evenly divided - not
    right, but placed, and repairable in the editor without having to
    start over.

    Returns:
        Exactly as many lines as ``new_lines``.
    """
    import difflib

    old_text = [_norm_text(line.text) for line in old_lines]
    new_text = [_norm_text(line.text) for line in new_lines]
    result: list[TimedLine | None] = [None] * len(new_lines)

    matcher = difflib.SequenceMatcher(a=old_text, b=new_text, autojunk=False)
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(b2 - b1):
                old = old_lines[a1 + offset]
                new = new_lines[b1 + offset]
                result[b1 + offset] = TimedLine(
                    index=getattr(new, "index", old.index), text=old.text,
                    crowd=new.crowd, crowd_section=old.crowd_section,
                    quality=old.quality,
                    block=getattr(new, "block", old.block),
                    disabled=old.disabled,
                    bg=bool(getattr(new, "bg", False)),          # B510
                    syllables=old.syllables)
        elif tag == "replace" and (a2 - a1) == (b2 - b1):
            # Same number: a rewritten line keeps its own place - that is
            # the B99/B407 case and the most common one by far.
            for offset in range(b2 - b1):
                old = old_lines[a1 + offset]
                low, high = _line_span_of(old)
                result[b1 + offset] = _reworded(old, new_lines[b1 + offset],
                                                low, high)

    # What is left over is genuinely new: give it the room between the
    # lines around it, which are placed by now.
    placed = [(i, line) for i, line in enumerate(result) if line is not None]
    typical = _median([line.end - line.start for _i, line in placed
                       if line.end > line.start]) if placed else 2.0
    typical = max(typical or 2.0, _MIN_ANY_S)
    fallback = old_lines[0] if old_lines else None
    index = 0
    while index < len(result):
        if result[index] is not None:
            index += 1
            continue
        run_end = index
        while run_end < len(result) and result[run_end] is None:
            run_end += 1
        before = next((line for i, line in reversed(placed) if i < index),
                      None)
        after = next((line for i, line in placed if i >= run_end), None)
        low = before.end if before is not None else max(
            0.0, (after.start - (run_end - index) * typical)
            if after is not None else 0.0)
        high = after.start if after is not None else low + \
            (run_end - index) * typical
        step = (high - low) / max(1, run_end - index)
        for offset, position in enumerate(range(index, run_end)):
            model = before or after or fallback
            if model is None:
                model = TimedLine(index=position, text="", crowd=False,
                                  syllables=())
            result[position] = _reworded(model, new_lines[position],
                                         low + offset * step,
                                         low + (offset + 1) * step)
        index = run_end
    return [line for line in result if line is not None]


def _line_span_of(line: TimedLine) -> tuple[float, float]:
    if not line.syllables:
        return 0.0, 0.0
    return line.syllables[0].start, line.syllables[-1].end


def spread_flattened(lines: Sequence[dict],
                     min_length: float = 0.02) -> int:
    """Give syllables without a moment their share back (B406).

    Works on the dicts of the timing editor and changes them in place.
    A line in which one or more syllables have length zero is spread
    evenly over its OWN span: first start and last end stay exactly
    where they are, so the sentence keeps the place the user gave it
    and only the division within it is repaired.

    Deliberately here and not in :func:`load_timing`: a file that is
    read is not thereby also rewritten. The editor calls this on the
    way in, so the repair only lands on disk when the user saves.

    Returns:
        How many lines were repaired.
    """
    repaired = 0
    for line in lines:
        every = line.get("syllables") or []
        # B485: an inline [bg] piece has its own times and may lie
        # outside the sentence; it neither sets the window nor gets
        # redivided.
        syllables = [s for s in every if not s.get("bg")] or every
        if len(syllables) < 2:
            continue
        if not any(float(s["end"]) - float(s["start"]) < min_length
                   for s in syllables):
            continue
        low = float(syllables[0]["start"])
        high = float(syllables[-1]["end"])
        if high <= low:
            continue
        step = (high - low) / len(syllables)
        for position, syllable in enumerate(syllables):
            syllable["start"] = round(low + position * step, 3)
            syllable["end"] = round(low + (position + 1) * step, 3)
        repaired += 1
    return repaired


def clamp_span(start: float, end: float,
               blocked: Sequence[tuple[float, float]],
               min_length: float = 0.2) -> tuple[float, float]:
    """Clamp a time slot into the nearest free gap.

    Used by the timing editor to prevent overlap: if a block is pushed
    up against a neighbouring block, it is shortened ("squeezed in"); if
    its middle lies INSIDE another block, it jumps to the nearest free
    gap.

    Returns:
        The adjusted time slot; if there is no room anywhere, the time
        slot is left untouched.
    """
    if not blocked:
        return start, end
    infinity = float("inf")
    ordered = sorted(blocked)
    merged: list[list[float]] = [list(ordered[0])]
    for block_start, block_end in ordered[1:]:
        if block_start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], block_end)
        else:
            merged.append([block_start, block_end])

    gaps: list[tuple[float, float]] = []
    previous = 0.0
    for block_start, block_end in merged:
        if block_start - previous >= min_length:
            gaps.append((previous, block_start))
        previous = max(previous, block_end)
    gaps.append((previous, infinity))

    middle = (start + end) / 2.0

    def distance(gap: tuple[float, float]) -> float:
        if gap[0] <= middle <= gap[1]:
            return 0.0
        return min(abs(middle - gap[0]), abs(middle - gap[1]))

    left, right = min(gaps, key=distance)
    new_start = max(start, left)
    if right != infinity:
        new_start = min(new_start, right - min_length)
    new_start = max(new_start, left)
    new_end = end if right == infinity else min(end, right)
    new_end = max(new_end, new_start + min_length)
    if right != infinity:
        new_end = min(new_end, right)
    if new_end - new_start < min_length - 1e-9:
        return start, end
    return new_start, new_end


#: Lower bound for a real sentence (>=3 syllables); short shouts may be
#: shorter. Never put a sentence below ~1 s just like that (B106).
_MIN_PHRASE_S = 1.0
_MIN_ANY_S = 0.35
#: Minimum (visible, singable-along) duration for short crowd shouts (B139).
_MIN_CROWD_S = 0.8
#: Room after a reliable sentence that is kept as a real pause instead of
#: being closed up against the next sentence (B147).
_PAUSE_GAP_S = 0.4
#: In terms of tempo (s per syllable) a sentence may deviate from the
#: baseline by at most this factor (B106).
_RATE_FACTOR = 3.0


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _reflow_line(line: TimedLine, start: float, end: float) -> TimedLine:
    """Put a line on [start, end]. With (virtually) equal length only
    shift it (preserves fine timing); otherwise syllables evenly."""
    start = max(0.0, start)
    end = max(start + _MIN_ANY_S, end)
    old_start, old_end = line.start, line.end
    same_len = abs((end - start) - (old_end - old_start)) < 1e-3
    if same_len and line.syllables:
        delta = start - old_start
        syllables = tuple(
            replace(s, start=round(s.start + delta, 3),
                    end=round(s.end + delta, 3))
            for s in line.syllables)
    else:
        # B485: an inline [bg] piece keeps its own times; spreading it
        # over the window of the sung part would shorten that part by its
        # share and drag the piece back inside.
        spread = [s for s in line.syllables if not s.bg] or list(line.syllables)
        if not spread:                      # B498: a line without pieces
            return line
        # B494: SCALED, not spread evenly. Making every syllable the same
        # width throws away all the fine timing that was measured -
        # including the pause in the middle of a sentence, which is
        # exactly the complaint "a stretched line no longer has good
        # phonetic timing". Scaling keeps every proportion and still puts
        # the line precisely on [start, end].
        old_low = spread[0].start
        old_high = spread[-1].end
        old_width = old_high - old_low
        fresh: dict[int, Syllable] = {}
        if old_width > 1e-6:
            factor = (end - start) / old_width
            for item in spread:
                fresh[id(item)] = replace(
                    item,
                    start=round(start + (item.start - old_low) * factor, 3),
                    end=round(start + (item.end - old_low) * factor, 3))
        else:
            width = (end - start) / len(spread) if spread else 0.0
            for i, item in enumerate(spread):
                fresh[id(item)] = replace(
                    item, start=round(start + i * width, 3),
                    end=round(start + (i + 1) * width, 3))
        syllables = tuple(fresh.get(id(s), s) for s in line.syllables)
    return replace(line, syllables=syllables)


def _norm_text(text: str) -> str:
    """Normalized text for recognizing identical lines (B166)."""
    return " ".join(text.lower().split())


#: A sentence lasts about one musical phrase. Below this fraction of the
#: measured phrase period a sentence is too short to be a phrase, above
#: the upper bound too long (B332). Deliberately wide: the test has to
#: catch the wrecks (a "sentence" of 0.02 s, one of double length), not
#: police normal variation.
_PHRASE_MIN_FACTOR = 0.25
_PHRASE_MAX_FACTOR = 1.8
#: The period is only used when it is really measurable: at least this
#: many intervals and a median absolute deviation below this fraction.
#: Above it the song has no steady phrase (measured: Lied N 50%) and
#: the whole mechanism switches itself off.
_PERIOD_MIN_INTERVALS = 5
_PERIOD_MAX_MAD = 0.18
#: Bounds within which an interval counts as one phrase at all.
_PERIOD_MIN_S = 1.2
_PERIOD_MAX_S = 7.0
#: A repeated sentence is about equally long everywhere (B329). The
#: reference needs this many reliably measured occurrences and has to be
#: this tight before anything is tested against it.
_REFERENCE_MIN_COUNT = 3
_REFERENCE_MAX_MAD = 0.15
#: Deviation from the reference at which an occurrence becomes suspect.
_REFERENCE_TOLERANCE = 0.35
#: At most this fraction of the anchors may be dropped by the tests. Is
#: it more, then the measurement itself is untrustworthy and everything
#: stays as it was.
_MAX_ANCHORS_DROPPED = 0.5
#: B340: anchors that follow one another at less than this fraction of
#: the phrase period form a "packed" run.
_PACKED_FACTOR = 0.5
#: Only from this many anchors in a row - two close together can simply
#: be a short interjection.
_PACKED_MIN_RUN = 3


def _reliable(line: TimedLine) -> bool:
    """Has this line a real, measured time (and not an estimate)?"""
    return line.quality in ("high", "syllable") and line.end > line.start


def phrase_period(lines: Sequence[TimedLine]) -> float | None:
    """The phrase period of the song in seconds, or ``None`` (B332).

    A sung line is a musical phrase, and a phrase lasts a fixed number
    of bars: measured on "Lied S" a new line starts every 3.77 s,
    which at 129 BPM is exactly 8 beats. That period is the natural unit
    at sentence level - unlike seconds per syllable, which is a word
    notion that was being used a floor too high.

    Measured over the intervals between successive lines that both have
    a real time. Returns ``None`` when there are too few of them or when
    they are too erratic (median absolute deviation above
    :data:`_PERIOD_MAX_MAD`); the caller then keeps working the old way.
    Deliberately measured over ALL lines, crowd included: in a parody a
    crowd line is often a full phrase, and leaving them out made the
    measurement worse (measured: MAD from 6% to 50%).
    """
    intervals = [b.start - a.start
                 for a, b in zip(lines, lines[1:])
                 if _reliable(a) and _reliable(b)]
    usable = [d for d in intervals if _PERIOD_MIN_S < d < _PERIOD_MAX_S]
    if len(usable) < _PERIOD_MIN_INTERVALS:
        return None
    period = _median(usable)
    if period <= 0:
        return None
    spread = _median([abs(d - period) for d in usable]) / period
    if spread > _PERIOD_MAX_MAD:
        return None
    return period


def reference_durations(lines: Sequence[TimedLine]
                        ) -> dict[str, tuple[float, float]]:
    """Per repeated sentence its usual duration: ``{text: (median, mad)}``.

    "E viva Espagna" is about equally long everywhere in the song, so an
    occurrence of double length is not a long-drawn-out one but a
    mistake (B329). Only reliably measured occurrences count - an
    estimate as reference would confirm its own error - and a text whose
    occurrences are too erratic (a hook that is genuinely sometimes held
    and sometimes shouted) delivers no reference at all.

    This generalizes :func:`_reference_durations` (B166), which did the
    same but only for the tail after the last anchor.
    """
    per_text: dict[str, list[float]] = {}
    for line in lines:
        if _reliable(line):
            per_text.setdefault(_norm_text(line.text), []).append(
                line.end - line.start)
    result: dict[str, tuple[float, float]] = {}
    for text_value, values in per_text.items():
        if len(values) < _REFERENCE_MIN_COUNT:
            continue
        median = _median(values)
        if median <= 0.05:
            continue
        spread = _median([abs(v - median) for v in values])
        if spread / median > _REFERENCE_MAX_MAD:
            continue
        result[text_value] = (median, spread)
    return result


def _packed_runs(lines: Sequence[TimedLine], anchors: Sequence[int],
                 period: float | None) -> list[list[int]]:
    """Runs of anchors that stand far tighter than the phrase (B340).

    A sung line is a musical phrase (B332). A row of anchors that follow
    one another at a third of that period can therefore not ALL be
    right - it is the picture of a repeated line that the coupling has
    put in the wrong place several times over.

    Deliberately on a RUN and not per pair: a crude per-pair version was
    tried during the development of v0.102 and was worse, because it
    killed half the verse anchors. And without a reliably measured
    period nothing happens at all.

    The caller asks two different questions of the same picture and they
    need different answers, which is why this returns the runs and not a
    verdict (B535). Which anchor has to GO is only the interior,
    ``run[1:-1]``: the outer two keep the stretch pinned. Whether a
    start may be BELIEVED excludes the last member too, ``run[1:]`` - it
    stands just as tightly against its neighbour as the ones inside it.
    """
    if period is None or len(anchors) < _PACKED_MIN_RUN:
        return []
    limit = _PACKED_FACTOR * period
    runs: list[list[int]] = []
    run = [anchors[0]]
    for previous, index in zip(anchors, anchors[1:]):
        if lines[index].start - lines[previous].start < limit:
            run.append(index)
            continue
        if len(run) >= _PACKED_MIN_RUN:
            runs.append(run)
        run = [index]
    if len(run) >= _PACKED_MIN_RUN:
        runs.append(run)
    return runs


def implausible_and_overlong(lines: Sequence[TimedLine],
                             period: float | None,
                             reference: dict[str, tuple[float, float]]
                             ) -> tuple[set[int], set[int]]:
    """The suspect anchors, and which of them are only TOO LONG (B522).

    Two tests decide "suspect", and they catch different things
    (B329/B332/B340). The phrase period sees that a "sentence" of
    0.02 s or of double length is impossible, also for a filler line
    for which no reference exists. The reference duration sees a
    sentence that deviates from its own repetitions, also when the
    period is not measurable. Both only look at what the timing
    DEMANDS, not at the similarity of the coupling - a wrong anchor is
    usually a perfect match in the wrong place (the lesson of B313).
    Refuses to drop more than :data:`_MAX_ANCHORS_DROPPED` of the
    anchors: is it more, then the reference is apparently the exception
    and everything stays as it was.

    The second set is the one B522 added, and that difference matters. A sentence measured at fifteen seconds
    while the phrase of this song is three and a half cannot be right -
    but the reason is almost always that its LAST word bleeds into the
    instrumental that follows, and then its beginning is still exactly
    where the singing starts. Measured on the user's own project: "Where
    we'll plan our escape" came out of the forced alignment as
    134.97-150.23 while he had timed the line by hand at 134.60. Drop
    that anchor and the line is interpolated between its neighbours,
    which puts it at 141.9 - seven seconds into the music. Keep the
    start and cap the duration and it lands where he put it.
    """
    anchors = [i for i, line in enumerate(lines) if _reliable(line)]
    if not anchors:
        return set(), set()
    # B529: an anchor that is suspect because it stands in the wrong
    # PLACE (a repeated line coupled several times over) may never come
    # back as "only too long" - it is its start that is wrong, and that
    # is exactly what the caller would then keep.
    #
    # B535: and that goes for the interior AND the last member of a
    # packed run. B340 keeps the outer two of such a run as anchors on
    # purpose, so the stretch stays pinned - but keeping a line as an
    # anchor is not the same as believing its start well enough to hand
    # it back after B522. Measured on "Lied K": line 43
    # is the last of a packed run, its coupling runs 202.57-225.09 (22.5
    # s against a phrase of 3.44) and its start is 10.3 s before where
    # the user put it. Handing that start back dragged the whole outro
    # forward and cost 2.05 s on the yardstick - from 4.85 to 6.90.
    #
    # The FIRST member keeps its start, and that is deliberate. A packed
    # run is the picture of one line put down several times over, and of
    # those copies the first is where the singing plausibly began - the
    # rest drift away from it. It is also exactly the shape B522 was
    # built for: a start that is right with an end that bleeds into the
    # instrumental. There is no measurement that says otherwise, so it
    # stays as it was.
    runs = _packed_runs(lines, anchors, period)
    crowded: set[int] = {index for run in runs for index in run[1:]}
    packed: set[int] = {index for run in runs for index in run[1:-1]}
    suspect: set[int] = set(packed)
    overlong: set[int] = set()
    for index in anchors:
        line = lines[index]
        span = line.end - line.start
        if period is not None and not (
                _PHRASE_MIN_FACTOR * period <= span
                <= _PHRASE_MAX_FACTOR * period):
            suspect.add(index)
            if span > _PHRASE_MAX_FACTOR * period:
                overlong.add(index)
            continue
        entry = reference.get(_norm_text(line.text))
        if entry is None:
            continue
        median, spread = entry
        if abs(span - median) > max(3 * spread,
                                    _REFERENCE_TOLERANCE * median):
            suspect.add(index)
            if span > median:
                overlong.add(index)
    if len(suspect) > _MAX_ANCHORS_DROPPED * len(anchors):
        return set(), set()
    return suspect, (overlong & suspect) - crowded


def _reference_durations(lines, starts, kept, last, baseline, nsyl
                         ) -> dict[str, float]:
    """Median duration per (normalized) line in the already placed,
    anchored part (lines 0..last). Used to give fade-out repetitions the
    same length as their earlier occurrence (B166).
    """
    per_text: dict[str, list[float]] = {}
    for k in range(last + 1):
        end = starts[k + 1] if k + 1 <= last else (
            kept[last] + max(baseline * nsyl(lines[last]), _MIN_ANY_S))
        duration = max(end - starts[k], _MIN_ANY_S)
        per_text.setdefault(_norm_text(lines[k].text), []).append(duration)
    return {text_value: sorted(v)[len(v) // 2] for text_value, v in per_text.items()}


#: A vocal window only carries lines when its length is a whole number
#: of phrases (B336). Measured on the tail of one song: 14.56 s = 3.90
#: phrases -> 4 lines, 29.88 s = 8.01 -> 8 lines, while a stray peak of
#: 0.88 s (0.24) and a held ad lib of 4.78 s (1.28) carry none. That
#: whole-number test is exactly what separates a series of sung lines
#: from a single long note.
_WINDOW_FIT_TOLERANCE = 0.20


def tail_over_windows(count: int,
                      windows: Sequence[tuple[float, float]],
                      period: float, after: float) -> list[float] | None:
    """Start times for ``count`` tail lines over the sung windows (B336).

    Where the transcription stops - Whisper writes no vocalises, so a
    "na-na-na" tail delivers nothing - the lines used to be spread over
    the remaining playing time of the song. That goes wrong as soon as
    there is another instrumental part in the tail: measured, one song
    had a gap of thirty seconds halfway through and the lines ended up
    an average of nine seconds off.

    The vocal stem shows exactly where singing is going on. Every window
    after ``after`` gets as many lines as it is phrases long, and a
    window that is not a whole number of phrases (a stray peak, a held
    ad lib) gets none.

    Returns ``None`` when the windows do not add up to exactly ``count``
    lines. Then something is going on that this rule does not see, and
    the caller keeps its own division - better nothing than a confident
    mistake.
    """
    if count <= 0 or period <= 0 or not windows:
        return None
    usable: list[tuple[float, float, int]] = []
    total = 0
    for start, end in windows:
        start = max(float(start), after)
        end = float(end)
        if end - start <= 0:
            continue
        phrases = (end - start) / period
        whole = round(phrases)
        if whole >= 1 and abs(phrases - whole) <= _WINDOW_FIT_TOLERANCE:
            usable.append((start, end, whole))
            total += whole
    if total != count:
        return None
    result: list[float] = []
    for start, end, whole in usable:
        step = (end - start) / whole
        result.extend(start + k * step for k in range(whole))
    return result


def sanitize_timing(lines: Sequence[TimedLine],
                    first_start: float | None = None,
                    song_duration: float | None = None,
                    block_barrier: bool = True,
                    weight_map: dict[str, float] | None = None,
                    active_windows: Sequence[tuple[float, float]] | None = None
                    ) -> tuple[TimedLine, ...]:
    """Make the timing robust and sensible (B106).

    This is the sentence level: it decides WHERE lines lie and how long
    they last, before the word and syllable steps refine within a line.
    From coarse to fine, so it reasons in phrases (B332) and no longer
    in syllables - the latter is a word notion that was being applied a
    floor too high.

    - measures the phrase period and the usual duration of repeated
      sentences, and drops anchors that cannot be a sentence (B329/B332);
    - derives a base tempo (s per syllable) from the lines with high
      confidence (falling back to the median of all lines);
    - clamps every line duration to that tempo ×/÷ 3 and to at least ~1 s
      for real sentences (short shouts may be shorter);
    - keeps the ordering monotonic and without overlap (no going back in
      time, no piled-up 0-second lines);
    - anchors the first line on ``first_start`` if desired (e.g. the
      Demucs vocal onset, B130).
    """
    lines = list(lines)
    # B509/B510: a whole [bg] line keeps its own times. Background
    # vocals may lie over their neighbours - that is what they are - so
    # such a line must not take part in the ordering, and it must not
    # push anything forward through ``prev_end`` either. It is set aside
    # here and put back untouched at the end. Without this the coupled
    # sentence it was given in B509 was handed straight back: measured,
    # a bg line on 4.0-6.0 came out at 5.2-6.2, and two closing ones on
    # 30 and 33 s landed on 7.4 and 7.75.
    background = [line for line in lines if getattr(line, "bg", False)]
    if background:
        lines = [line for line in lines if not getattr(line, "bg", False)]

    def _with_background(done: Sequence[TimedLine]) -> tuple[TimedLine, ...]:
        if not background:
            return tuple(done)
        return tuple(sorted(list(done) + background,
                            key=lambda item: item.index))

    n = len(lines)
    if n == 0:
        return _with_background(lines)

    def nsyl(line: TimedLine) -> int:
        return max(1, len(line.syllables))

    # --- Sentence level first (B329/B332) --------------------------------
    # The phrase period is the unit of this level; it is ``None`` and the
    # reference empty when the song does not sing steadily enough for it,
    # and then everything below works exactly as before.
    period = phrase_period(lines)
    reference = reference_durations(lines)
    suspect, overlong = implausible_and_overlong(lines, period, reference)
    if suspect:
        logger.info(t("log_anchors_implausible"), len(suspect),
                    period if period is not None else 0.0)
    if overlong:
        logger.info(t("log_anchors_capped"), len(overlong))

    hi = [ln for i, ln in enumerate(lines)
          if ln.quality in ("high", "syllable") and ln.end > ln.start
          and i not in suspect]
    if not hi:
        hi = [ln for ln in lines if ln.quality in ("high", "syllable")
              and ln.end > ln.start]
    pool = hi or [ln for ln in lines if ln.end > ln.start] or lines
    rates = [(ln.end - ln.start) / nsyl(ln) for ln in pool
             if ln.end > ln.start and ln.syllables]
    baseline = _median(rates) if rates else 0.3
    baseline = min(max(baseline, 0.12), 0.8)

    # --- Anchors: reliable lines (high confidence) + the onset. ---------
    # Every anchor gets a WEIGHT according to reliability (B250): a real
    # sung onset and 'lettergreep' quality weigh the heaviest, then
    # 'hoog'. On a conflict (non-monotonic time) the heaviest anchor wins
    # instead of simply the first one; this way repeated chorus lines no
    # longer push the reliable anchors aside and 'lines do not get in
    # each other's way'.
    _gw = weight_map or {}
    _ANCHOR_WEIGHT = {"syllable": float(_gw.get("syllable", 3.0)),
                      "high": float(_gw.get("high", 2.0)),
                      "word": float(_gw.get("word", 1.0))}
    _ONSET_WEIGHT = float(_gw.get("onset", 10.0))

    def _anchor_weight(ln: TimedLine) -> float:
        return _ANCHOR_WEIGHT.get(ln.quality, 0.0)

    # B522: a line that was rejected only because it lasts too long
    # keeps its START as an anchor. It stays in ``suspect``, so its
    # measured DURATION is not copied over further down - the beginning
    # is measured, the end ran away.
    candidates: dict[int, tuple[float, float]] = {
        i: (ln.start, _anchor_weight(ln))
        for i, ln in enumerate(lines)
        if ln.quality in ("high", "syllable") and ln.end > ln.start
        and (i not in suspect or i in overlong)}          # B329/B332/B522
    if first_start is not None:
        # The vocal onset is the strongest anchor there is (B130/B133).
        candidates[0] = (max(0.0, float(first_start)), _ONSET_WEIGHT)
    elif 0 not in candidates:
        candidates[0] = (max(0.0, lines[0].start
                             if lines[0].end > lines[0].start else 0.0), 0.5)

    # Monotonic anchor series with weight and block barriers (B251,
    # arbitration in modules.timing_rules). Within a block the heaviest
    # anchor wins (B250); across a block boundary an earlier-block anchor
    # is never pushed aside, so that a repeated chorus does not drag the
    # next verse along and every block anchors on its own onset. The
    # block barrier is on by default; with
    # ``blok_anker_barriere=False`` everything falls into one (virtual)
    # block.
    cands = [
        timing_rules.Candidate(
            scope="line", ref=i, start=t, end=t, weight=w,
            confidence=1.0, kind=timing_rules.KIND_ANCHOR,
            block=(lines[i].block if block_barrier else 0))
        for i, (t, w) in candidates.items()]
    kept = timing_rules.arbitrate_anchors(cands)
    anchor_idx = sorted(kept)

    # --- Start points: between two anchors one phrase each (B332). -----
    # Only without a measurable period does it fall back to pro rata of
    # syllables - which reads as sensible but is a word notion: a line of
    # four syllables does not get a quarter of the time of a line of
    # sixteen, it gets its own phrase.
    def _slot(k: int) -> float:
        return 1.0 if period is not None else float(nsyl(lines[k]))

    starts = [0.0] * n
    for a, b in zip(anchor_idx, anchor_idx[1:]):
        ta, tb = kept[a], kept[b]
        weights = [_slot(k) for k in range(a, b)]
        total = sum(weights) or 1
        cum = 0.0
        for offset, k in enumerate(range(a, b)):
            starts[k] = ta + (cum / total) * (tb - ta)
            cum += weights[offset]
        starts[b] = tb
    # Place the remaining lines after the last anchor.
    last = anchor_idx[-1]
    starts[last] = kept[last]
    trailing = list(range(last + 1, n))
    #: Tail lines (fade-out) are usually repetitions of earlier lines
    #: that Whisper no longer transcribes. Give such a line the same
    #: duration as the earlier line with exactly the same text and place
    #: them sequentially (B166). Without a known reference it falls back
    #: to syllable tempo; if there is no reference at all in the tail,
    #: then the old spread up to the end of the song (B148).
    ref = _reference_durations(lines, starts, kept, last, baseline, nsyl)

    def _dur_for(line: TimedLine) -> float:
        key = _norm_text(line.text)
        entry = reference.get(key)      # B329: only measured occurrences
        if entry is not None:
            return entry[0]
        if key in ref:                  # B166: what was placed earlier
            return ref[key]
        if period is not None:          # B332: one line is one phrase
            return period
        return max(baseline * nsyl(line), _MIN_ANY_S)

    # B336: where the singing really is beats every calculation. Only
    # taken over when the windows explain the tail exactly.
    over_windows = (tail_over_windows(len(trailing), active_windows or (),
                                      period, kept[last] + _MIN_ANY_S)
                    if (trailing and period is not None) else None)
    has_ref = any(_norm_text(lines[k].text) in ref
                    or _norm_text(lines[k].text) in reference
                    for k in trailing)
    tempo_end = kept[last] + sum(_dur_for(lines[k]) for k in trailing)
    if over_windows is not None:
        logger.info(t("log_tail_on_windows"), len(trailing))
        for k, moment in zip(trailing, over_windows):
            starts[k] = moment
    elif (not has_ref and song_duration and len(trailing) >= 4
            and song_duration - tempo_end > 3.0):
        ta, tb = kept[last], song_duration
        weights = [nsyl(lines[k]) for k in [last] + trailing]
        total = sum(weights) or 1
        cum = weights[0]
        for offset, k in enumerate(trailing, start=1):
            starts[k] = ta + (cum / total) * (tb - ta)
            cum += weights[offset]
    else:
        running = kept[last]
        for k in trailing:
            running += _dur_for(lines[k - 1])
            starts[k] = running

    # --- End times + min duration + monotonic + within song length. -----
    anchored = set(anchor_idx)
    result: list[TimedLine] = []
    prev_end = 0.0
    prev_min = 0.0
    for k in range(n):
        line = lines[k]
        start = max(starts[k], prev_end)
        if k in anchored and result and result[-1].end > starts[k]:
            # A MEASURED start wins over the minimum duration of the line
            # before it (B333). It used to be ``max(starts[k], prev_end)``
            # without exception, so every sentence that had to be
            # lengthened pushed the next one forward - and those pushes
            # added up over the song. In one measured case the coupling
            # was right to within 0.34 s while the timing that came out
            # of it was 4.19 s off, running up to 8.6 s at the end.
            #
            # But only where there is room for it. Are the anchors
            # themselves crammed (four repeat lines a third of a second
            # apart), then they cannot all be right and shortening would
            # squash the line to a sliver; there the old spreading is
            # still better (B139/B148).
            earlier = result[-1]
            if starts[k] - earlier.start >= prev_min:
                result[-1] = _reflow_line(earlier, earlier.start, starts[k])
                prev_end = result[-1].end
                start = starts[k]
        next_start = starts[k + 1] if k + 1 < n else None
        n_syl = nsyl(line)
        lo = max(_MIN_ANY_S, baseline * n_syl / _RATE_FACTOR)
        if n_syl >= 3:
            lo = max(lo, _MIN_PHRASE_S)
        # Do not squash short crowd shouts ('Oeh!', 'Ah!') to a sliver:
        # give them a visible, singable-along minimum duration (B139).
        if line.crowd:
            lo = max(lo, _MIN_CROWD_S)
        hi_dur = max(_MIN_PHRASE_S + 0.2, baseline * n_syl * _RATE_FACTOR)
        if period is not None:
            # A sentence never lasts much longer than its phrase (B332).
            hi_dur = min(hi_dur, max(_MIN_PHRASE_S + 0.2,
                                     _PHRASE_MAX_FACTOR * period))
        # A suspect span is not a measured duration but a mistake, so it
        # is not copied over either (B329/B332).
        reliable = line.quality in ("high", "syllable") \
            and line.end > line.start and k not in suspect

        if next_start is None:
            # Last line: use the reference duration of the same text
            # (B166), otherwise syllable tempo.
            base_duration = ref.get(_norm_text(line.text),
                                max(baseline * n_syl, _MIN_PHRASE_S))
            end = start + max(base_duration, lo)
        elif reliable:
            # Real sung duration (clamped to [lo, hi]).
            real_end = start + min(max(line.end - line.start, lo), hi_dur)
            if real_end <= next_start:
                # Room: polish away a small gap, leave a real pause in
                # place (B147).
                end = (real_end if (next_start - real_end) > _PAUSE_GAP_S
                       else next_start)
            else:
                # Crammed (repeated/fade-out anchors close together): the
                # minimum duration wins, the overlap pushes the rest
                # forward -> the lines get spread out instead of being
                # squashed to ~0 s (B139/B148).
                end = real_end
        elif k in overlong:
            # B522: rejected on duration alone. The start is measured and
            # kept above; the end is the one thing we know is wrong, so
            # it gets the length this song usually gives a sentence
            # (its own repetitions first, otherwise the syllable tempo)
            # instead of being stretched to the next line. Filling up
            # would put fifteen seconds of sentence over the
            # instrumental that made it too long in the first place.
            # Its own repetitions first; without those the phrase of this
            # song, because a sentence IS a phrase (B332) - the syllable
            # tempo would give this line six seconds where the song sings
            # three and a half.
            base_duration = ref.get(_norm_text(line.text),
                                period if period is not None
                                else max(baseline * n_syl, _MIN_PHRASE_S))
            end = min(max(next_start, start + lo),
                      start + max(min(base_duration, hi_dur), lo))
        else:
            # Unreliable: fill up to the next one, but never shorter than
            # the minimum duration (which beats the no-overlap bound).
            end = max(next_start, start + lo)
        if end < start + lo:
            end = start + lo
        if song_duration and end > song_duration:
            end = max(start + _MIN_ANY_S, song_duration)
        fixed = _reflow_line(line, start, end)
        result.append(fixed)
        prev_end = fixed.end
        prev_min = lo          # B333: how short this line may become
    return _with_background(
        stretch_tail_over_singing(result, active_windows, song_duration))


#: Singing after the last line that counts as "the text ran out before
#: the song did" (B539). Below this it is a held note or an "ahh" that
#: no line describes, and nothing has to happen.
_TAIL_SINGING_S = 5.0
#: A line whose duration is at or just above the floor: the placement
#: had nothing to say about it and simply put it behind its neighbour.
_TAIL_FLOOR_S = _MIN_PHRASE_S + 0.10
#: How much of the tail has to sit on that floor before it is re-spread,
#: and how many lines it takes at least. Both deliberately strict: this
#: rule moves lines the coupling calls reliable, and it may only do that
#: where the picture leaves no room for another reading.
_TAIL_FLOOR_SHARE = 0.70
_TAIL_MIN_LINES = 4


def stretch_tail_over_singing(lines: Sequence[TimedLine], windows,
                              song_duration: float | None = None
                              ) -> list[TimedLine]:
    """Spread a crammed tail over the singing that follows it (B539).

    Measured on "Lied N", the worst project of the collection at
    7.58 s. The song ends with the chorus four times over, the coupling
    matched all four to the same early occurrence, and the last fifteen
    lines came out stacked at the minimum duration between 189 and 204
    s - while the vocal stem shows singing up to 220 s and the user had
    those lines at 189 to 222. Sixteen seconds of measured singing with
    no text on it at all, and a metre of lines standing shoulder to
    shoulder in front of it.

    Two things have to be true together, and neither on its own is
    enough. There is singing after the last line - so the text
    demonstrably ran out before the song did - AND the tail sits on the
    floor of :data:`_MIN_PHRASE_S`, which is the placement's own way of
    saying it had nothing to go on. Then those lines are laid over the
    sung windows from where the tail begins.

    B336 does the same thing for the tail AFTER the last anchor, but
    needs a phrase period and an exact fit. This case has neither: the
    lines ARE anchors (wrong ones) and the song has no measurable
    period - which is precisely why nothing caught it. Measured over all
    twenty projects: "Lied N" from 7.58 s to 3.40 s with the damage
    on untouched lines going down as well (0.66 to 0.58), and not one
    other project changing by a thousandth.

    It keeps the invariants the rest of ``sanitize_timing`` keeps, and
    the critical re-reading is the reason they are written out here: the
    lines stay in order, they do not overlap, they stay inside the song,
    and a line that is switched off keeps its place instead of eating a
    piece of singing nobody can see. Where that cannot be done - the
    singing does not have room for this many lines - nothing happens at
    all. Better the crammed tail than a tail that looks measured.
    """
    lines = list(lines)
    spans = [(float(a), float(b)) for a, b in (windows or [])
             if float(b) > float(a)]
    if len(lines) < _TAIL_MIN_LINES or not spans:
        return lines
    singing_ends = max(b for _a, b in spans)
    if singing_ends - max(line.end for line in lines) < _TAIL_SINGING_S:
        return lines
    start_index = _crammed_tail(lines)
    if start_index is None:
        return lines
    # B539: a line that is switched off (B180) is not on screen, so it
    # may not claim a piece of the singing either. It travels with its
    # neighbour instead.
    movable = [index for index in range(start_index, len(lines))
               if not getattr(lines[index], "disabled", False)]
    if len(movable) < _TAIL_MIN_LINES:
        return lines
    last = min(singing_ends, song_duration) if song_duration else singing_ends
    begins = _spread_over_windows(len(movable), spans,
                                  lines[movable[0]].start, last)
    if begins is None:
        return lines
    # No line may end after its neighbour begins, and none may run past
    # the end of the song. Refuse rather than repair: a tail squeezed
    # below the floor is the very thing this rule was built against.
    room = [(begins[k + 1] if k + 1 < len(begins) else last) - begins[k]
            for k in range(len(begins))]
    if min(room) < _MIN_PHRASE_S:
        return lines
    for index, begin in zip(movable, begins):
        lines[index] = _moved_to(lines[index], begin)
    return lines


def _crammed_tail(lines: Sequence[TimedLine]) -> int | None:
    """Where the run of floor-length lines at the end begins (B539).

    The LONGEST such run: a tail can end on one line that did get a
    length of its own (the last sentence is filled up to the end of the
    song), and that one line may not hide the fifteen behind it.

    A tail has something in front of it, and that something has to be a
    line the placement DID have information about - so the run begins on
    a floor line and the line before it is not one. Without that second
    half a song of short shouts is one long "tail" from the first line,
    and then a rule about the end of a song quietly relays the whole
    thing.
    """
    on_the_floor = [1 if (line.end - line.start) <= _TAIL_FLOOR_S else 0
                    for line in lines]
    found = None
    counted = 0
    for index in range(len(lines) - 1, 0, -1):
        counted += on_the_floor[index]
        length = len(lines) - index
        if (on_the_floor[index] and not on_the_floor[index - 1]
                and length >= _TAIL_MIN_LINES
                and counted / length >= _TAIL_FLOOR_SHARE):
            found = index
    return found


def _spread_over_windows(count: int, spans, first: float,
                         last: float) -> list[float] | None:
    """``count`` starts over the sung SECONDS between ``first`` and
    ``last`` (B539).

    Measured in sung time and not per window, because per window means
    rounding per window: the first version reserved one line for every
    window still to come, and with fewer lines than windows the early
    ones were skipped and the whole tail slid to the end of the song.
    Walking the singing as one continuous stretch has neither problem -
    the first line lands exactly on ``first`` and the spacing is even in
    the time somebody is actually singing.
    """
    usable = [(max(float(a), first), min(float(b), last))
              for a, b in sorted(spans)]
    usable = [(a, b) for a, b in usable if b > a]
    if count <= 0 or not usable:
        return None
    room = sum(b - a for a, b in usable)
    if room <= 0:
        return None
    begins: list[float] = []
    step = room / count
    for number in range(count):
        walked = number * step
        for a, b in usable:
            if walked <= (b - a) + 1e-9:
                begins.append(round(a + walked, 3))
                break
            walked -= (b - a)
        else:                            # rounding at the very end
            begins.append(round(usable[-1][1], 3))
    return begins if len(begins) == count else None


def _moved_to(line: TimedLine, start: float) -> TimedLine:
    """The same line, its whole span shifted to ``start`` (B539).

    On ``line.start`` and not on the first syllable: with an inline
    ``[bg]`` piece in front those two are different, and then the line
    would land exactly that piece too late.
    """
    if not line.syllables:
        return line
    shift = start - line.start
    if abs(shift) < 1e-6:
        return line
    return replace(line, syllables=tuple(
        replace(syllable, start=round(syllable.start + shift, 3),
                end=round(syllable.end + shift, 3))
        for syllable in line.syllables))


#: How far a line may be pulled towards an onset, as a fraction of the
#: phrase period (B330). Well under half a phrase: any further and it
#: would grab its neighbour's onset instead of its own.
_SNAP_FACTOR = 0.45
#: Ceiling on that, for a song without a measurable period.
_SNAP_MAX_S = 1.5

#: B351: a line that starts AFTER A PAUSE begins measurably too late.
#: Measured on "Lied C": of the 48 lines the user
#: moved seven by more than 0.3 s, all seven backwards and all seven
#: behind a pause, while of the 23 lines that follow on directly he
#: touched none. Average error 0.29 s behind a pause against 0.04 s for
#: a line that follows on - a factor of seven. The cause is that the
#: anchor is the word start from the alignment, and that sits a median
#: 0.19 s AFTER the onset of the singing, while the right place lies
#: just before it. B330 cannot repair this because these lines are
#: measured, and a measured line is deliberately never moved.
#: A pause in front of it of at least this long.
_PAUSE_MIN_S = 1.0
#: And only when the anchor sits at least this far behind the onset. Of
#: the 25 lines behind a pause, the ones the user left alone sit
#: 0.10-0.23 s behind their onset and the ones he corrected 0.29-2.36 s.
#: The bound lies in that gap; higher and the correction does less,
#: lower and lines that were already right get moved.
_LATE_MIN_S = 0.25
#: Never travel further back than this.
_PAUSE_MAX_BACK_S = 1.5


def _onset_before_start(line: TimedLine, previous_end: float,
                        ordered: Sequence[float]) -> float | None:
    """The onset this line should have started on (B351), or ``None``.

    Only for a line with a real pause in front of it: then there is room
    to move backwards without touching anything, and the singing that
    begins there is a better witness than the word boundary from the
    alignment.
    """
    if line.start - previous_end < _PAUSE_MIN_S:
        return None
    floor = max(previous_end, line.start - _PAUSE_MAX_BACK_S)
    candidates = [moment for moment in ordered
                  if floor <= moment <= line.start - _LATE_MIN_S]
    return max(candidates) if candidates else None


def snap_to_onsets(lines: Sequence[TimedLine],
                   onsets: Sequence[float],
                   period: float | None = None) -> tuple[TimedLine, ...]:
    """Pull estimated line starts to the nearest sung onset (B330).

    The structure comes first (:func:`sanitize_timing`); this is the
    fine-tuning on top of it. A line whose time was really measured is
    never moved - those are right and moving them can only do damage.
    An estimated line searches for the nearest onset within reach, must
    stay after its predecessor and may not pass the next measured line.

    Order matters: snapping before the structure is right picks the
    onset of the neighbouring line. Measured, with a structure that was
    still two seconds off, snapping made the result WORSE; on top of a
    correct structure it brings the line to within 0.15 s.

    Without onsets (no vocal stem, analysis off) the lines come back
    unchanged.
    """
    lines = list(lines)
    if not lines or not onsets:
        return tuple(lines)
    reach = min(_SNAP_FACTOR * period, _SNAP_MAX_S) if period else _SNAP_MAX_S
    ordered = sorted(float(t) for t in onsets)
    fixed = [i for i, line in enumerate(lines) if _reliable(line)]
    next_fixed = {}
    following = None
    for i in range(len(lines) - 1, -1, -1):
        next_fixed[i] = following
        if i in fixed:
            following = lines[i].start
    result: list[TimedLine] = []
    previous_end = 0.0
    for index, line in enumerate(lines):
        if index in fixed:
            # A measured line stays exactly where it is - and it is not
            # pushed forward by a snapped predecessor either, which was
            # the leak in the first version: the start was bounded but
            # the END of the line before it pushed anyway.
            # One exception (B351): behind a real pause the anchor itself
            # is late, and there the singing tells us better. Only
            # backwards, only into the silence in front of it, and only
            # when the anchor sits clearly behind the onset.
            moved = _onset_before_start(line, previous_end, ordered)
            if moved is not None:
                line = _reflow_line(line, moved, line.end)
            result.append(line)
            previous_end = line.end
            continue
        ceiling = next_fixed.get(index)
        start = line.start
        best = None
        for moment in ordered:
            if abs(moment - start) > reach:
                continue
            if moment < previous_end - 1e-9:
                continue
            if ceiling is not None and moment >= ceiling:
                continue
            if best is None or abs(moment - start) < abs(best - start):
                best = moment
        if best is not None:
            start = best
        start = max(start, previous_end)
        end = start + max(line.end - line.start, _MIN_ANY_S)
        if ceiling is not None:
            start = min(start, max(previous_end, ceiling - _MIN_ANY_S))
            end = max(min(end, ceiling), start + _MIN_ANY_S / 2)
        moved = _reflow_line(line, start, end)
        result.append(moved)
        previous_end = moved.end
    return tuple(result)


def enforce_monotonic(lines: Sequence[TimedLine],
                      min_span: float = 0.3) -> tuple[TimedLine, ...]:
    """Safeguard the integrity of (manually edited) timing (B108).

    Guarantees that every line has start < end (at least ``min_span``),
    that no line sits at 0 and that the ordering stays monotonic (a line
    may not start before the previous one -> no reordering by dragging).
    The text/syllable proportions are preserved; only invalid edge cases
    are pulled into line.

    B510: a whole ``[bg]`` line is left alone and does not count as "the
    previous one" either. Background vocals may lie over their
    neighbours, so pulling them into the row would drag them off the
    sentence they sing over - and shift everything after them as well.
    """
    result: list[TimedLine] = []
    prev_end = 0.0
    for line in lines:
        if getattr(line, "bg", False):
            result.append(line)
            continue
        start = max(line.start, prev_end)
        end = line.end
        if end < start + min_span:
            end = start + min_span
        result.append(_reflow_line(line, start, end))
        prev_end = end
    return tuple(result)


def repair_line_edges(lines: Sequence[TimedLine],
                      min_span: float = _MIN_ANY_S
                      ) -> tuple[tuple[TimedLine, ...], int]:
    """Repair only the genuine defects between the lines (B500).

    Two things may not reach the editor and the render: a line of zero
    length, and two lines over each other. Deliberately NOT via
    ``enforce_monotonic``: that pushes a line forward as soon as its
    predecessor runs on, and a line START is the one thing that is often
    measured - snapped onto the vocal onset (B333/B357). Pushing that
    forward moves the sentence off the singing and squeezes it as well.

    So: a start is never touched. An overlap is taken off the END of the
    line before it, which is the least reliable side of a sentence -
    that is what B224 already trims for. A crowd line and a switched-off
    line are skipped: those are allowed to lie over their neighbours
    (B346/B180), and since B510 a whole ``[bg]`` line as well - that is
    the same exemption ``timing_checks._may_overlap`` makes, and without
    it this repair undoes exactly the overlap that was just declared
    correct: measured, a sung line of 1.0-5.0 was cut back to 1.0-4.0
    for a background line lying over it.

    Returns the lines and how many were repaired.
    """
    out = list(lines)
    repaired = 0
    previous = None
    for position, line in enumerate(out):
        if line.crowd or line.disabled or getattr(line, "bg", False):
            continue
        if line.end <= line.start:
            room = min_span
            out[position] = _reflow_line(line, line.start,
                                         line.start + room)
            repaired += 1
            line = out[position]
        if previous is not None:
            before = out[previous]
            if line.start < before.end - 0.002:
                new_end = max(before.start + min_span, line.start)
                if new_end < before.end:
                    out[previous] = _reflow_line(before, before.start,
                                                 new_end)
                    repaired += 1
        previous = position
    return tuple(out), repaired


#: The stages that :func:`timing_report` can put side by side (B408),
#: in the order in which ``generate_timing`` runs them.
STAGES = ("koppeling", "zinnen", "inzet", "woorden")


def timing_report(lines: Sequence[TimedLine], offset: float | None = None,
                  source_karaoke: str = "", version: str = "",
                  stages: dict[str, Sequence[tuple[float, float]]]
                  | None = None) -> str:
    """Compact, token-frugal diagnostics per sentence (B129/B408).

    One line per sentence with start/end/duration/syllable-count/quality
    and automatically detected oddities (too short, overlap, back in
    time).

    B408: with ``stages`` the span the line had after each earlier step
    is put beside it - after the sentence coupling, after
    ``sanitize_timing`` and after the word timing on the vocal energy.
    Without those columns a shortened line is a fact without a culprit:
    on one measured song seven lines came out more than a second
    shorter than the coupling had them, and answering WHICH step did
    that took an afternoon of reading code. The ``KRIMP`` flag marks a
    line that lost more than a second along the way, so it can be found
    without doing the arithmetic yourself.
    """
    head_offset = "onbekend" if offset is None else f"{offset * 1000:+.0f}ms"
    present = [name for name in STAGES if stages and stages.get(name)]
    extra = "".join(f"|{name}" for name in present)
    header = (f"# versie={version or '?'} offset={head_offset} "
              f"bron-karaoke={source_karaoke or '-'} regels={len(lines)}\n"
              f"idx|start|end|span{extra}|nsyl|kwal|flags")
    rows = [header]
    prev_end = None
    for i, line in enumerate(lines):
        s, e = line.start, line.end
        span = e - s
        n = len(line.syllables)
        columns = ""
        shrunk = 0.0
        for name in present:
            spans = stages[name]
            if i < len(spans):
                low, high = spans[i]
                columns += f"|{high - low:.2f}"
                shrunk = max(shrunk, (high - low) - span)
            else:
                columns += "|-"
        flags = []
        if span < 0.6:
            flags.append("KORT")
        if shrunk > 1.0:
            flags.append("KRIMP")
        if prev_end is not None and s < prev_end - 0.05:
            flags.append("OVERLAP")
        if e < s:
            flags.append("OMGEKEERD")
        rows.append(f"{i}|{s:.2f}|{e:.2f}|{span:.2f}{columns}|{n}|"
                    f"{line.quality}|{','.join(flags)}")
        prev_end = e
    return "\n".join(rows) + "\n"


def _line_to_dict(line: TimedLine) -> dict[str, Any]:
    return {
        "line": line.index,
        "text": line.text,
        "crowd": line.crowd,
        "crowd_section": line.crowd_section,
        "quality": line.quality,
        "block": line.block,
        "disabled": line.disabled,
        "bg": line.bg,                                        # B510
        "syllables": [
            {"text": syllable.text, "start": syllable.start,
             "end": syllable.end, "held": syllable.held,
             "stress": syllable.stress, "crowd": syllable.crowd,
             "bg": syllable.bg}
            for syllable in line.syllables
        ],
    }


def save_timing(lines: Sequence[TimedLine], path: Path,
                offset: float | None = None, project: str = "",
                version: str = "") -> None:
    """Write the timing to JSON.

    Since v0.53 the format is an object ``{"offset": <s>, "lines":
    [...]}`` so that the original↔karaoke offset that was used is
    preserved (B98). Since v0.72 there is also a header with ``project``
    (title), ``version`` and ``created`` (timestamp), so that you can
    see which project/version a file belongs to and cross-contamination
    can be traced (B183). The old bare-list format stays readable.
    """
    import datetime as _dt
    data = {
        "project": project,
        "version": version,
        "created": _dt.datetime.now().isoformat(timespec="seconds"),
        "offset": offset,
        "lines": [_line_to_dict(line) for line in lines],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # B568: the version that is about to disappear first. Every write
    # of a timing file in the program comes through here, so this one
    # line covers timing.json (the hand work) and timing_auto.json (the
    # reference it is measured against) both.
    history.keep_a_copy(path)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    logger.info(t("log_timing_written"),
                path, len(lines), t("value_unknown") if offset is None
                else f"{offset * 1000:+.0f} ms", project or "?")


def timing_project(path: Path) -> str | None:
    """Read the project title from a timing file (``None`` = unknown/old).

    Used to check whether a timing belongs to the current project
    (B181/B183)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        p = data.get("project")
        return str(p) if p else None
    return None


def _rows_from_raw(data: Any) -> list[dict[str, Any]]:
    """Get the line list out of both formats (list or object)."""
    if isinstance(data, dict):
        return list(data.get("lines", []))
    return list(data)  # old bare-list format


def load_timing(path: Path) -> tuple[TimedLine, ...]:
    """Read the timing from JSON (accepts old list and new object format).

    B441: ``held`` is DERIVED and is recomputed here, whatever the file
    says. Two reasons. The stored value is false in every existing
    project - the field was written for years and never set, so reading
    it faithfully means reading nothing. And it is a judgement on the
    spans: stretch a syllable in the editor and the mark has to follow,
    which it cannot do if it is frozen in a file. Deriving it means every
    project the user already has gets its held notes at once, without a
    single timing.json being touched.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return mark_held(tuple(
        TimedLine(
            index=int(item["line"]),
            text=str(item["text"]),
            crowd=bool(item["crowd"]),
            crowd_section=bool(item.get("crowd_section", False)),
            quality=str(item.get("quality", "sentence")),
            block=int(item.get("block", 0)),
            disabled=bool(item.get("disabled", False)),
            # B510: an older file does not have it. It is not guessed
            # here either - ``pipeline.mark_inline_pieces`` puts it back
            # from the karaoke text, which is where the truth is.
            bg=bool(item.get("bg", False)),
            syllables=tuple(
                Syllable(text=str(syl["text"]), start=float(syl["start"]),
                         end=float(syl["end"]), held=bool(syl["held"]),
                         stress=bool(syl.get("stress", False)),
                         crowd=bool(syl.get("crowd", False)),
                         # B485: an older file does not have it; the
                         # sentence then simply has no bg piece.
                         bg=bool(syl.get("bg", False)))
                for syl in item["syllables"]
            ),
        )
        for item in _rows_from_raw(data)
    ))


def load_offset(path: Path) -> float | None:
    """Read the stored offset from ``timing.json`` (``None`` = unknown)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("offset") is not None:
        return float(data["offset"])
    return None


def reanchor(lines: Sequence[TimedLine], delta_s: float) -> tuple[TimedLine,
                                                                  ...]:
    """Shift all syllable times by ``delta_s`` seconds (B98).

    Times are clamped to ``>= 0``. Used to lay a timing that was made
    for a different offset back onto the current karaoke.
    """
    if not delta_s:
        return tuple(lines)
    shifted: list[TimedLine] = []
    for line in lines:
        syllables = tuple(
            replace(s, start=round(max(0.0, s.start + delta_s), 3),
                    end=round(max(0.0, s.end + delta_s), 3))
            for s in line.syllables
        )
        shifted.append(replace(line, syllables=syllables))
    return tuple(shifted)
