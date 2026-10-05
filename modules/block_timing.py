"""Blocks that come back, timed together (v1.0.15, B602-B605).

Four ideas on the lines of a coupling, before ``sanitize_timing`` puts
them in order (``pipeline._block_models`` runs them in this order). Each
is a model in the register and ships OFF, until test 1.5.15
(:mod:`block_trial`) has measured it against the owner's hand timings.

* :func:`place` (B604) - a block standing on the wrong spot as a whole.
  84% of the lines more than 2 s off in the 1.5.13 night sat in blocks
  shifted as a whole. A block whose lines are crammed, far from the
  layout of its kin, or on top of another block (two choruses coupled to
  one repetition) is looked for again on the harmony of the music -
  where the chords come back that its best-heard kin stands on - and
  moved as a whole, never onto another block. Blocks of the same shape
  with other words (verses) are only moved, never laid out again: their
  sentences, words and syllables are always listened to on their own.
* :func:`fuse` (B603) - the blocks linked on tab 1 (the same text) are
  heard together. Per word, every time Whisper heard it in one of the
  blocks is put on one clock (the offset between the blocks is measured
  on the words they share), times on (nearly) the same spot form one
  group, and their certainties add up: a word heard in two blocks on the
  same spot weighs more than one heard a bit more surely somewhere else.
  The group with the highest sum wins, its time the certainty-weighted
  mean, and every linked block gets it, on its own place - no exception.
  The owner's rule, in his words: the combination of the highest
  certainty over the blocks.
* :func:`fill` (B602) - a line of a linked block that is still unheard
  takes the layout of the same line where it was heard: its start and
  end from the block's clock, and the profile of its syllables.
* :func:`lay_words` (B605) - the second road: the words of the text laid
  on the voice by the forced aligner, line by line, in the room the
  coupling gave each line, instead of only what Whisper heard.
"""
from __future__ import annotations

import statistics
from dataclasses import replace
from typing import Callable, Sequence

from .timing import TimedLine, piece_groups

#: B603: times closer than this count as the same spot. 1.5.15 measures
#: 0.05 and 0.2 s besides.
FUSE_S = 0.10

#: A line shorter than this per word is crammed.
CRAMMED_S = 0.15

#: B605: a word the forced alignment placed with less certainty keeps
#: the time it had.
LYRICS_LEAST = 0.3

#: B604: a block is looked for again when its lines stand further than
#: this from the layout of its kin (median), or when one is crammed.
PLACE_OFF_S = 1.0
#: How far around its spot a block is looked for, and what a second of
#: distance costs in similarity - a chorus a bar further has the same
#: chords, and the nearer one is the likelier.
PLACE_WINDOW_S = 30.0
PLACE_PENALTY = 0.005
#: A block lying on top of another one for longer than this is in the
#: wrong spot, and may not be moved to such a spot either.
PLACE_OVERLAP_S = 0.3
#: A move smaller than this is no move.
PLACE_MIN_S = 0.5

#: The shortest a word is made when words have to be spread.
MIN_WORD_S = 0.03

#: The quality a line laid out like its kin gets: taken over, not heard.
FILLED = "word"

#: Qualities that count as heard.
HEARD = ("high", "syllable")


def _rows_of(lines: Sequence[TimedLine], number: int) -> list[int]:
    return [i for i, line in enumerate(lines)
            if int(getattr(line, "block", 0)) == number
            and not getattr(line, "bg", False)]


def _heard(line: TimedLine) -> bool:
    return line.quality in HEARD and line.end > line.start \
        and not getattr(line, "made", False)


def _words(line: TimedLine) -> list[list[int]]:
    """The sung words of a line, as groups of piece indexes; a word of
    inline background vocals is not part of it."""
    return [group for group in piece_groups(line.syllables)
            if not all(getattr(line.syllables[i], "bg", False)
                       for i in group)]


def _word_span(line: TimedLine, group: Sequence[int]) -> tuple[float, float]:
    return (float(line.syllables[group[0]].start),
            float(line.syllables[group[-1]].end))


def _place_pieces(line: TimedLine, group: Sequence[int],
                  span: tuple[float, float]) -> TimedLine:
    """Lay the pieces of one word on ``span``, their proportions kept."""
    start, end = _word_span(line, group)
    width = end - start
    new_width = max(MIN_WORD_S, span[1] - span[0])
    pieces = list(line.syllables)
    for n, index in enumerate(group):
        item = pieces[index]
        if width > 1e-6:
            a = span[0] + (float(item.start) - start) / width * new_width
            b = span[0] + (float(item.end) - start) / width * new_width
        else:
            a = span[0] + n * new_width / len(group)
            b = span[0] + (n + 1) * new_width / len(group)
        pieces[index] = replace(item, start=round(a, 3), end=round(b, 3))
    return replace(line, syllables=tuple(pieces))


def _in_order(line: TimedLine, fixed: set[int]) -> TimedLine:
    """Words not in ``fixed`` that no longer fit in order between the
    fixed ones are spread evenly over the room between them; words that
    still fit keep what was heard."""
    words = _words(line)
    if len(words) < 2:
        return line
    spans = [_word_span(line, group) for group in words]
    k = 0
    while k < len(words):
        if k in fixed:
            k += 1
            continue
        run = [k]
        while run[-1] + 1 < len(words) and run[-1] + 1 not in fixed:
            run.append(run[-1] + 1)
        low = spans[run[0] - 1][1] if run[0] > 0 else None
        high = spans[run[-1] + 1][0] if run[-1] + 1 < len(words) else None
        inner = [spans[i] for i in run]
        fits = all(a[1] <= b[0] + 1e-3 for a, b in zip(inner, inner[1:])) \
            and (low is None or inner[0][0] >= low - 1e-3) \
            and (high is None or inner[-1][1] <= high + 1e-3)
        if not fits:
            room = MIN_WORD_S * len(run)
            if low is None:
                low = max(0.0, min(inner[0][0], high - room))
            if high is None:
                high = max(inner[-1][1], low + room)
            high = max(high, low + room)
            step = (high - low) / len(run)
            for n, index in enumerate(run):
                line = _place_pieces(line, words[index],
                                     (low + n * step, low + (n + 1) * step))
                spans[index] = _word_span(line, words[index])
        k = run[-1] + 1
    return line


def _texts(line: TimedLine) -> list[str]:
    """The words of a line as letters only, to match them by."""
    return ["".join(ch for ch in "".join(
        line.syllables[i].text for i in group).lower() if ch.isalnum())
        for group in _words(line)]


def _matching(first: TimedLine, second: TimedLine) -> dict[int, int]:
    """Which word of ``second`` is which word of ``first``: by their
    letters, so a word more or less in a linked block (they may differ a
    little) does not shift the rest; by position when they are as many
    and the letters say nothing."""
    import difflib

    mine, theirs = _texts(first), _texts(second)
    matcher = difflib.SequenceMatcher(None, mine, theirs, autojunk=False)
    pairs = {block.a + n: block.b + n
             for block in matcher.get_matching_blocks()
             for n in range(block.size)}
    if not pairs and len(mine) == len(theirs):
        pairs = {k: k for k in range(len(mine))}
    return pairs


def _offsets(lines, occurrences, observe, tolerance: float | None = None,
             by_words: bool = True) -> dict[int, float]:
    """The clock of each occurrence against the best-heard one: the
    difference most of the times both heard agree on. ``observe(row,
    word)`` gives ``(start, end, weight)`` or ``None``; with ``by_words``
    the words are paired by :func:`_matching`, otherwise by position."""
    def weight_of(rows) -> float:
        total = 0.0
        for row in rows:
            for k in range(len(_words(lines[row]))):
                seen = observe(row, k)
                if seen is not None:
                    total += seen[2]
        return total

    base = max(occurrences, key=lambda rows: weight_of(rows))
    out = {id(base): 0.0}
    for rows in occurrences:
        if rows is base:
            continue
        diffs = []
        for row, base_row in zip(rows, base):
            if by_words:
                pairs = _matching(lines[base_row], lines[row]).items()
            else:
                count = min(len(_words(lines[row])),
                            len(_words(lines[base_row])))
                pairs = ((k, k) for k in range(count))
            for theirs_k, mine_k in pairs:
                mine, theirs = observe(row, mine_k), observe(base_row,
                                                             theirs_k)
                if mine is not None and theirs is not None:
                    diffs.append(mine[0] - theirs[0])
        if not diffs:
            # Nothing heard in both: the first lines' starts.
            diffs = [float(lines[rows[0]].start) - float(lines[base[0]].start)]
        out[id(rows)] = _agreed(diffs, FUSE_S if tolerance is None
                                else tolerance)
    return out


def _agreed(diffs: Sequence[float], tolerance: float) -> float:
    """The offset most differences agree on: the largest set within
    ``tolerance`` of one of them (nearest the median on a tie), averaged.
    Better than the median alone when one line of a block was sung a
    little differently."""
    middle = statistics.median(diffs)
    best = max(diffs, key=lambda d: (
        sum(1 for other in diffs if abs(other - d) <= tolerance),
        -abs(d - middle)))
    near = [d for d in diffs if abs(d - best) <= tolerance]
    return sum(near) / len(near)


def fuse(lines: Sequence[TimedLine], groups: Sequence[Sequence[int]],
         certainty: Callable[[float], float],
         tolerance: float = FUSE_S) -> tuple[TimedLine, ...]:
    """B603: the words of linked blocks, heard together.

    ``certainty(start)`` is Whisper's certainty for a word heard starting
    at ``start`` (0 when it was not heard there: laid on, spread, or
    moved by the coupling).
    """
    lines = list(lines)
    for group in groups:
        occurrences = [_rows_of(lines, number) for number in group]
        occurrences = [rows for rows in occurrences if rows]
        if len(occurrences) < 2:
            continue
        size = min(len(rows) for rows in occurrences)
        occurrences = [rows[:size] for rows in occurrences]

        def observe(row: int, k: int):
            line = lines[row]
            words = _words(line)
            if k >= len(words) or not line.end > line.start:
                return None
            start, end = _word_span(line, words[k])
            weight = float(certainty(start))
            return (start, end, weight) if weight > 0 else None

        offsets = _offsets(lines, occurrences, observe, tolerance)
        for p in range(size):
            # Every word of every occurrence is paired with a word of the
            # first; a word one of them has and the first has not is left
            # to what was heard of it.
            reference = lines[occurrences[0][p]]
            pairs = [_matching(reference, lines[rows[p]])
                     for rows in occurrences]
            fused: dict[int, tuple[float, float]] = {}
            for k in range(len(_words(reference))):
                seen = []
                for rows, pair in zip(occurrences, pairs):
                    if k not in pair:
                        continue
                    found = observe(rows[p], pair[k])
                    if found is not None:
                        shift = offsets[id(rows)]
                        seen.append((found[0] - shift, found[1] - shift,
                                     found[2]))
                if seen:
                    fused[k] = _winner(seen, tolerance)
            if not fused:
                continue
            for rows, pair in zip(occurrences, pairs):
                row = rows[p]
                line = lines[row]
                words = _words(line)
                shift = offsets[id(rows)]
                placed = set()
                for k, (start, end) in fused.items():
                    if k in pair:
                        line = _place_pieces(line, words[pair[k]],
                                             (start + shift, end + shift))
                        placed.add(pair[k])
                line = _in_order(line, placed)
                if len(placed) * 2 >= len(words):
                    line = replace(line, quality="high", made=False)
                lines[row] = line
    return tuple(lines)


def _winner(seen: Sequence[tuple[float, float, float]],
            tolerance: float) -> tuple[float, float]:
    """The group of times on (nearly) one spot with the highest summed
    certainty; its certainty-weighted mean."""
    ordered = sorted(seen)
    clusters: list[list[tuple[float, float, float]]] = []
    for item in ordered:
        if clusters:
            members = clusters[-1]
            total = sum(w for _s, _e, w in members)
            centre = sum(s * w for s, _e, w in members) / total
            if abs(item[0] - centre) <= tolerance:
                members.append(item)
                continue
        clusters.append([item])
    best = max(clusters, key=lambda members: sum(w for _s, _e, w in members))
    total = sum(w for _s, _e, w in best)
    return (sum(s * w for s, _e, w in best) / total,
            sum(e * w for _s, e, w in best) / total)


def _layout(lines, occurrences, reliable):
    """Per line position the relative start, end and syllable profile
    from the occurrences where that line is reliable, and the clock of
    every occurrence (from its reliable lines)."""
    def observe(row: int, k: int):
        line = lines[row]
        if k != 0 or not reliable(line):
            return None
        return (float(line.start), float(line.end), 1.0)

    offsets = _offsets(lines, occurrences, observe, by_words=False)
    known = {id(rows): any(reliable(lines[r]) for r in rows)
             for rows in occurrences}
    layout = {}
    for p in range(len(occurrences[0])):
        spans, profiles = [], []
        for rows in occurrences:
            line = lines[rows[p]]
            if reliable(line):
                shift = offsets[id(rows)]
                spans.append((float(line.start) - shift,
                              float(line.end) - shift))
                profiles.append(line)
        if spans:
            layout[p] = (statistics.median(s for s, _e in spans),
                         statistics.median(e for _s, e in spans),
                         profiles[0])
    return layout, offsets, known


def _laid(line: TimedLine, template: TimedLine,
          span: tuple[float, float]) -> TimedLine:
    """``line`` on ``span``, its syllables divided like ``template``'s
    when it has as many, otherwise scaled as they are."""
    start, end = span
    if end <= start:
        return line
    if len(template.syllables) == len(line.syllables) and \
            template.end > template.start:
        width = template.end - template.start
        pieces = tuple(replace(
            item, start=round(start + (t.start - template.start) / width
                              * (end - start), 3),
            end=round(start + (t.end - template.start) / width
                      * (end - start), 3))
            for item, t in zip(line.syllables, template.syllables))
    else:
        width = max(1e-6, line.end - line.start)
        pieces = tuple(replace(
            item, start=round(start + (item.start - line.start) / width
                              * (end - start), 3),
            end=round(start + (item.end - line.start) / width
                      * (end - start), 3))
            for item in line.syllables)
    return replace(line, syllables=pieces)


def fill(lines: Sequence[TimedLine],
         groups: Sequence[Sequence[int]]) -> tuple[TimedLine, ...]:
    """B602: an unheard line of a linked block from the same line where
    it was heard. A block with no heard line at all keeps its lines -
    where it stands is :func:`place`'s question."""
    lines = list(lines)
    for group in groups:
        occurrences = [_rows_of(lines, number) for number in group]
        occurrences = [rows for rows in occurrences if rows]
        if len(occurrences) < 2:
            continue
        size = min(len(rows) for rows in occurrences)
        occurrences = [rows[:size] for rows in occurrences]
        layout, offsets, known = _layout(lines, occurrences, _heard)
        for rows in occurrences:
            if not known[id(rows)]:
                continue
            shift = offsets[id(rows)]
            for p, row in enumerate(rows):
                if _heard(lines[row]) or p not in layout:
                    continue
                start, end, template = layout[p]
                lines[row] = replace(
                    _laid(lines[row], template, (start + shift, end + shift)),
                    quality=FILLED)
    return tuple(lines)


def _crammed(line: TimedLine) -> bool:
    return line.end - line.start < CRAMMED_S * max(1, len(_words(line)))


def _span(lines, rows) -> tuple[float, float]:
    return (min(float(lines[r].start) for r in rows),
            max(float(lines[r].end) for r in rows))


def _overlap(lines, rows, span: tuple[float, float]) -> float:
    """How many seconds ``span`` shares with the lines of other blocks."""
    mine = set(rows)
    number = int(getattr(lines[rows[0]], "block", 0))
    total = 0.0
    for index, line in enumerate(lines):
        if index in mine or getattr(line, "bg", False) \
                or int(getattr(line, "block", 0)) == number \
                or not line.end > line.start:
            continue
        total += max(0.0, min(span[1], line.end) - max(span[0], line.start))
    return total


def place(lines: Sequence[TimedLine], groups: Sequence[Sequence[int]],
          search: Callable[[float, float, float],
                           Sequence[tuple[float, float]]],
          relay: Sequence[Sequence[int]] = ()) -> tuple[TimedLine, ...]:
    """B604: a block on the wrong spot, moved as a whole.

    ``groups`` are blocks of one shape (the same text or not); ``relay``
    are the groups with the same text, whose lines are also laid out
    like their kin once moved. ``search(ref_start, ref_end, guess)``
    gives the spots where the music of ``ref_start..ref_end`` comes back,
    ``(start, score)`` best first, the distance to ``guess`` weighed in.

    A block is looked for again when one of its lines is crammed, when
    its lines stand far from the layout of its kin, or when it lies on
    top of another block - the usual sign of two choruses coupled to one
    and the same repetition. It goes to the best spot where it does not
    lie on top of another block.
    """
    lines = list(lines)
    same_text = [set(group) for group in relay]
    for group in groups:
        occurrences = [(number, _rows_of(lines, number)) for number in group]
        occurrences = [(n, rows) for n, rows in occurrences if rows]
        if len(occurrences) < 2:
            continue
        size = min(len(rows) for _n, rows in occurrences)
        occurrences = [(n, rows[:size]) for n, rows in occurrences]
        just_rows = [rows for _n, rows in occurrences]
        layout, offsets, _known = _layout(lines, just_rows, _heard)
        if not layout:
            continue
        # The reference: the occurrence with the most heard lines, and of
        # those the one that lies on top of nothing.
        ref_rows = max(just_rows, key=lambda rows: (
            sum(_heard(lines[r]) for r in rows),
            -_overlap(lines, rows, _span(lines, rows))))
        ref_start, ref_end = _span(lines, ref_rows)
        for number, rows in occurrences:
            if rows is ref_rows:
                continue
            shift = offsets[id(rows)]
            span = _span(lines, rows)
            off = [abs(float(lines[row].start) - (layout[p][0] + shift))
                   for p, row in enumerate(rows) if p in layout]
            symptom = any(_crammed(lines[row]) for row in rows) \
                or bool(off and statistics.median(off) > PLACE_OFF_S) \
                or _overlap(lines, rows, span) > PLACE_OVERLAP_S
            if not symptom:
                continue
            guess = span[0]
            length = max(span[1] - span[0], ref_end - ref_start)
            found = None
            for start, _score in search(ref_start, ref_end, guess):
                if _overlap(lines, rows, (start, start + length)) \
                        <= PLACE_OVERLAP_S:
                    found = start
                    break
            if found is None or abs(found - guess) < PLACE_MIN_S:
                continue
            delta = found - guess
            relaid = any(number in kin for kin in same_text)
            # The background lines of the block go along with it.
            for index, line in enumerate(lines):
                if getattr(line, "bg", False) and \
                        int(getattr(line, "block", 0)) == number:
                    lines[index] = replace(line, syllables=tuple(
                        replace(item, start=round(item.start + delta, 3),
                                end=round(item.end + delta, 3))
                        for item in line.syllables))
            for p, row in enumerate(rows):
                line = lines[row]
                moved = replace(line, syllables=tuple(
                    replace(item, start=round(item.start + delta, 3),
                            end=round(item.end + delta, 3))
                    for item in line.syllables))
                if relaid and p in layout:
                    start, end, template = layout[p]
                    moved = _laid(moved, template, (start + shift + delta,
                                                    end + shift + delta))
                lines[row] = moved
    return tuple(lines)


def harmony_spots(step: float, chroma, ref_start: float, ref_end: float,
                  guess: float, window: float = PLACE_WINDOW_S,
                  penalty: float = PLACE_PENALTY) -> list[tuple[float, float]]:
    """Where the chords of ``ref_start..ref_end`` come back near ``guess``.

    ``chroma`` is a 12 x frames matrix, ``step`` seconds per frame. Per
    candidate start the mean cosine between the reference columns and
    the columns there, minus ``penalty`` per second from ``guess``; the
    reference's own spot is left out. Best first.
    """
    import numpy as np

    matrix = np.asarray(chroma, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] < 2 or step <= 0:
        return []
    norms = np.linalg.norm(matrix, axis=0)
    norms[norms < 1e-9] = 1.0
    matrix = matrix / norms
    first = max(0, int(round(ref_start / step)))
    last = min(matrix.shape[1], int(round(ref_end / step)))
    length = last - first
    if length < 2:
        return []
    reference = matrix[:, first:last]
    low = max(0, int(round((guess - window) / step)))
    high = min(matrix.shape[1] - length, int(round((guess + window) / step)))
    if high < low:
        return []
    scores = np.zeros(high - low + 1)
    for row in range(matrix.shape[0]):
        scores += np.correlate(matrix[row, low:high + length],
                               reference[row], mode="valid")[:scores.size]
    scores /= length
    out = []
    for n, value in enumerate(scores):
        start = (low + n) * step
        if abs(start - ref_start) < 0.5 * length * step:
            continue
        out.append((round(start, 3),
                    float(value) - penalty * abs(start - guess)))
    out.sort(key=lambda item: -item[1])
    return out


def lay_words(line: TimedLine,
              found: Sequence[tuple[str, float, float, float]],
              least: float) -> TimedLine:
    """B605: the words of ``line`` on the times found for them.

    ``found`` holds ``(text, start, end, certainty)`` per word the
    forced alignment placed, in order; they are matched to the words of
    the line by their letters, so a word it skipped does not shift the
    rest. A word found with less certainty than ``least`` keeps its
    time, and words that no longer fit around the placed ones are
    spread between them.
    """
    import difflib

    words = _words(line)
    if not words or not found:
        return line
    mine = ["".join(ch for ch in "".join(
        line.syllables[i].text for i in group).lower() if ch.isalnum())
        for group in words]
    theirs = ["".join(ch for ch in str(text).lower() if ch.isalnum())
              for text, _s, _e, _c in found]
    matcher = difflib.SequenceMatcher(None, mine, theirs, autojunk=False)
    placed: set[int] = set()
    for block in matcher.get_matching_blocks():
        for n in range(block.size):
            k, j = block.a + n, block.b + n
            _text, start, end, certainty = found[j]
            if certainty < least or not end > start:
                continue
            line = _place_pieces(line, words[k], (float(start), float(end)))
            placed.add(k)
    return _in_order(line, placed) if placed else line
