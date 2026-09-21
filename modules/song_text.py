"""Lyrics alignment: coupling the official lyrics to the transcription.

The original lyrics are leading. Every text line is aligned word for
word phonetically onto the Whisper words (dynamic programming with
1:1, 2:1 and 1:2 couplings, so that ``Kedeng Kedeng`` is coupled to
``GEDENGEDENG`` or ``DE TREIN`` as well). With that it is possible to:

* replace cluster labels with the official spelling;
* find target words that Whisper wrote down differently;
* estimate missed choruses from the anchors around them.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Collection, Sequence

from .cluster import (Cluster, is_pure_number, number_key_best_match,
                      phonetic_key, similarity)
from .whisper import Segment
from .translations import t

logger = logging.getLogger(__name__)

#: B555: ``songtekst.txt`` until v1.0.5. The name is what the program
#: calls this input everywhere else - ``input:lyrics``,
#: ``source_lyrics``, the ``lyrics`` key in ``input_names`` - so it is
#: the last Dutch name in the tree that the user also sees in Explorer.
#: There is deliberately no fallback on the old name: two truths for one
#: file is how a rename stays half done for years.
LYRICS_FILENAME = "lyrics.txt"

_MATCH_BASE = 0.45      # similarity level that scores neutrally
_GAP_PENALTY = 0.15     # penalty for an unexplained word
_MULTI_PENALTY = 0.05   # small penalty for 2:1/1:2 couplings
_MIN_ESTIMATED_GAP_S = 0.3
_MAX_ESTIMATED_GAP_S = 30.0
_TARGET_SIM = 0.65

#: Lower bound for the BEST of the two separate half-similarities in a
#: MULTIPLE coupling (m21: two lyrics words against one transcription
#: word - each lyrics word separately against that single word; m12: one
#: lyrics word against two transcription words - that single word
#: separately against each transcription word), B281. Without this bound
#: the DP alignment can stick a lyrics word onto an interjection (e.g. the
#: lyrics word "allow" onto the transcription "land Whoo!") as soon as
#: that happens to score more cheaply than leaving the words as
#: unexplained gaps - even though "allow" has no noteworthy similarity
#: with EITHER of the two transcription words separately ("land" 0.0,
#: "Whoo!" 0.25). Such a coupling wrongly drags the (RMS-refined) line
#: end through to the end of the interjection.
#:
#: A bound on the COMBINED similarity (instead of the best half) turned
#: out not to work: "Kedeng Kedeng" <-> "de trein" (an existing, intended
#: 1:2 coupling, see the module docstring) scores 0.333 combined, just
#: like the faulty Lied J couplings, so no fixed combined threshold
#: can tell them apart. Per-HALF similarity does work: "Kedeng" sits at
#: 0.333 against both "de" and "trein" individually (both a reasonable
#: match), while "will"<->"of"/"the" and "allow"<->"land"/"Whoo!" get
#: stuck at 0.0-0.25 for at least one of the two halves. Tested on three
#: songs: every known legitimate multiple coupling has a best half of
#: >= 0.333 (Kedeng/de-trein 0.333, "mijn"<->"m 'n" 0.333, "is"<->"ik zo"
#: 0.5, "a-showin'"<->"show in" 0.5); both faulty Lied J couplings
#: get stuck with their best half at <= 0.25. Single (m11) couplings are
#: left UNTOUCHED: with an ordinary Whisper mishearing those legitimately
#: score just as low (e.g. "nu"<->"niet" 0.333) and would be wrongly
#: killed off by the same bound.
_MIN_MULTI_HALF_SIM = 0.3


@dataclass(frozen=True)
class LyricWord:
    """One word from the official lyrics."""

    index: int
    text: str
    line: int
    #: True = simultaneous background vocals (B264, ``[bg]...[/bg]`` in
    #: lyrics.txt): sounds at the same time as the surrounding line
    #: instead of after it. Such words are not counted in the sentence
    #: coupling (just like crowd in B260) but do count for Whisper's
    #: initial_prompt (B263) and the hallucination detection (B258).
    bg: bool = False


@dataclass(frozen=True)
class AlignedWord:
    """A lyrics word with (optionally) the coupled transcription time."""

    lyric: LyricWord
    start: float | None
    end: float | None
    matched_text: str | None
    sim: float
    #: Is this time an ESTIMATE instead of a coupling? (B313)
    #:
    #: A word that Whisper never produced can still be given a plausible
    #: time by measuring where the singing is in the vocal stem. That is
    #: worth a lot for the video - the line does move along - but it is
    #: not the same as a word that was really recognised. Everything that
    #: judges the quality of the timing (which lines count as reliable,
    #: which anchors may be stretched, what the editor colours) has to be
    #: able to see the difference, otherwise a guess silently gains the
    #: weight of a measurement.
    estimated: bool = False


_BG_START = ("[bg]",)
_BG_END = ("[/bg]", "[einde bg]")


def is_bg_only_line(line: str) -> bool:
    """Does this line consist entirely of background singing? (B376)

    For counts that look at the RAW text - such as the structure warning
    - because those otherwise see a line that does not exist as far as
    the coupling is concerned.
    """
    text = line.strip()
    for start in _BG_START:
        if text.lower().startswith(start):
            rest = text[len(start):].strip()
            for end in _BG_END:
                if rest.lower().endswith(end):
                    return True
            return not any(m in rest.lower() for m in _BG_END)
    return False


#: Practical upper bound for Whisper's ``initial_prompt`` (B263): Whisper
#: internally cuts the prompt off at ~224 tokens; stay well below that so
#: that the translation into tokens (not 1-to-1 with words) does not cut
#: off in the middle of a word after all.
INITIAL_PROMPT_MAX_CHARS = 400


def deduped_prompt_text(lyrics: Sequence[LyricWord],
                        max_chars: int = INITIAL_PROMPT_MAX_CHARS) -> str:
    """Build a Whisper ``initial_prompt`` from the lyrics words (B263).

    Whisper sometimes hears certain words consistently wrong (the same
    mistake at every repetition of the same phrase). By passing the lyrics
    along beforehand as context, Whisper recognises the real vocabulary
    better instead of guessing again and again.

    Repetitions (choruses, "Sunday, Bloody Sunday" x4, ...) are removed
    first - otherwise the available space is used up by the same words
    instead of the full unique vocabulary of the song. Only after that is
    it shortened if needed to ``max_chars``, on a word boundary.
    Simultaneous background vocals (``LyricWord.bg``, B264) simply count
    along: even though such a line is not rendered separately, the words
    still help Whisper recognise what can be heard in the recording.
    """
    gezien: set[str] = set()
    uniek: list[str] = []
    for word in lyrics:
        key = word.text.lower()
        if key in gezien:
            continue
        gezien.add(key)
        uniek.append(word.text)
    text_value = " ".join(uniek)
    if len(text_value) <= max_chars:
        return text_value
    ingekort = text_value[:max_chars].rsplit(" ", 1)[0]
    return ingekort


def split_word(raw: str) -> list[str]:
    """One piece of text into lyric WORDS (B412/B418).

    Two things that a reader takes for granted and the code did not.

    B412: digits stay. They used to be filtered out, so "Another 45
    miles" became "Another miles" and the number never reached the
    lyrics at all - not uncoupled but ABSENT, invisible in every
    display. On the measured song that cost eleven words: 279 in the
    file against 268 in the coupling, and a hole of 0.89 s in the middle
    of every chorus line, exactly where the 45 is sung. Bitter, because
    ``cluster.phonetic_key`` has handled numbers since B274 ("500"
    becomes "vijfhonderd") - that machinery simply never got to see one.

    B418: a hyphen is a word BOUNDARY. Inside a word it was already
    ignored (``e-mail`` and ``email`` both give the key ``email``), but
    "La-la-la-la-la," stayed one word with the key ``lalalalala`` while
    Whisper writes five separate ``la``s - so that could never match. In
    sung text a hyphen groups a rhythmic cluster, which is exactly a
    row of separate sounds; the user writes it that way to make counting
    easier. Over all seventeen songs there are 186 hyphenated words, of
    which 132 are pure repeats (``na-na-na``) and the rest are things
    like ``woah-oh`` and ``diggi-loo`` - sung syllables too, not one
    real compound. And where one does turn up, the coupling can already
    cope: ``_lyric_pair_sim`` lays two lyric words against one
    transcript word, which is precisely the "e" + "mail" against
    "email" case.
    """
    parts = []
    for piece in str(raw).split("-"):
        cleaned = "".join(ch for ch in piece if ch.isalnum() or ch in "'’")
        if cleaned:
            parts.append(cleaned)
    return parts


def words_before_b418(text: str) -> list[str]:
    """The lyric word list as it was up to and including v0.134.0.

    Kept deliberately: the manual word couplings count POSITIONS in this
    list, so converting them (B417) needs the old shape as well as the
    new one. Not a copy of dead code but the definition of a layout -
    the same reason ``_PIN_LAYOUT_FULL`` exists.
    """
    out = []
    for raw in text.split():
        cleaned = "".join(ch for ch in raw
                          if ch.isalpha() or ch in "'’-")
        if cleaned:
            out.append(cleaned)
    return out


def load_lyrics(path: Path) -> tuple[LyricWord, ...]:
    """Read the lyrics and split them into normalised words.

    ``[bg]...[/bg]`` marks simultaneous background vocals (B264), as
    separate lines (block notation) or stuck onto a line (e.g.
    '[bg]Tonight, tonight[/bg]' or '...(Tonight, tonight)' written as
    '[bg]Tonight, tonight[/bg]' in the place of the brackets). The markers
    themselves yield no word; the enclosed words get ``bg=True`` - only
    those, so a sentence with a background tail keeps its own words
    (B484).
    """
    words: list[LyricWord] = []
    bg = False
    for line_no, line in enumerate(
            path.read_text(encoding="utf-8").splitlines()):
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered in _BG_START:
            bg = True
            continue
        if lowered in _BG_END:
            bg = False
            continue
        # B484: both markers on one line used to make the WHOLE line
        # background vocals, so a sentence with a background tail
        # ("Noon gam-go, ha-na, dool, set [bg]Twee-uh[/bg]") vanished
        # from the original lane of the editor and from the coupling. The
        # marking belongs to the words between the markers; the rest of
        # the sentence is ordinary lead vocals.
        # Every marker runs through the same loop, so a marker anywhere
        # in the line does what it says: [bg] opens, [/bg] closes, and
        # what stands at the end of the line is the state the next line
        # starts in. Handling an attached marker separately beforehand
        # made "Tonight[/bg] my dear" background vocals from beginning to
        # end.
        inside = bg
        for raw in re.split(r"(?i)(\[bg\]|\[/bg\])", stripped):
            marker = raw.strip().lower()
            if marker == "[bg]":
                inside = True
                continue
            if marker == "[/bg]":
                inside = False
                continue
            for word in raw.split():
                for cleaned in split_word(word):
                    words.append(LyricWord(len(words), cleaned, line_no,
                                           bg=inside))
        bg = inside
    if bg:
        logger.warning(t("log_lyrics_open_bg"))
    logger.info(t("log_lyrics_loaded"), len(words),
                sum(1 for w in words if w.bg))
    return tuple(words)


def is_symbol_token(text: str) -> bool:
    """Does this found word contain no letter/digit at all? (B239)

    WhisperX sometimes gives loose punctuation/symbols ('?', ',', '…',
    '>>', '«', '»') their own word with a timestamp. Such tokens are
    meaningless for the coupling and are filtered out."""
    return not any(ch.isalnum() for ch in str(text))


def _meaningful_words(segments: Sequence[Segment]):
    """All words from the segments, without loose punctuation tokens (B239)."""
    return [word for segment in segments for word in segment.words
            if not is_symbol_token(word.text)]


def flat_transcript(segments: Sequence[Segment]
                    ) -> list[tuple[str, float, float]]:
    """The transcription as a flat list (text, start, end) in order.

    Same order as :func:`align_lyrics` uses internally; the index in this
    list is the 'transcript index' for manual couplings (B121). Loose
    punctuation tokens are skipped (B239).
    """
    return [(word.text, float(word.start), float(word.end))
            for word in _meaningful_words(segments)]


def apply_pins(aligned: Sequence[AlignedWord],
               transcript: Sequence[tuple[str, float, float]],
               pins: dict[int, list[int]]) -> tuple[AlignedWord, ...]:
    """Apply manual word couplings to the alignment (B121).

    ``pins`` couples a lyrics word index to a **list** of transcript
    indices: empty = uncoupled, one = 1-to-1, several = 1-to-many (e.g.
    one sung word that Whisper heard in two pieces). A pinned word gets
    the time span covering all coupled transcription words and confidence
    1.0. The remaining words keep their automatic coupling.
    """
    out = list(aligned)
    for li, targets in pins.items():
        if not (0 <= li < len(out)):
            continue
        base = out[li]
        valid = [transcript[t] for t in (targets or [])
                 if 0 <= t < len(transcript)]
        if not valid:
            out[li] = AlignedWord(base.lyric, None, None, None, 0.0)
        else:
            start = min(v[1] for v in valid)
            end = max(v[2] for v in valid)
            text = " ".join(v[0] for v in valid)
            out[li] = AlignedWord(base.lyric, start, end, text, 1.0)
    return tuple(out)


def cut_word(transcript: Sequence[tuple[str, float, float]], index: int,
             char_offset: int | None = None
             ) -> tuple[list[tuple[str, float, float]], dict[int, list[int]]]:
    """Cut a found word in two (B153).

    Splits ``transcript[index]`` at ``char_offset`` (the middle by
    default) into two words; the time span is divided in proportion to the
    text length. Returns the new transcription list and an index mapping
    ``old -> [new, ...]`` to remap couplings (pins) with.
    """
    out = list(transcript)
    if not (0 <= index < len(out)):
        return out, {i: [i] for i in range(len(out))}
    text, start, end = out[index]
    snijpunt = len(text) // 2 if char_offset is None else char_offset
    snijpunt = max(1, min(len(text) - 1, snijpunt)) if len(text) >= 2 else 0
    if snijpunt <= 0:                       # nothing to cut
        return out, {i: [i] for i in range(len(out))}
    left, right = text[:snijpunt].strip(), text[snijpunt:].strip()
    fraction = snijpunt / len(text)
    middle = round(start + (end - start) * fraction, 3)
    new = out[:index] + [(left, start, middle), (right, middle, end)] \
        + out[index + 1:]
    mapping: dict[int, list[int]] = {}
    for i in range(len(out)):
        if i < index:
            mapping[i] = [i]
        elif i == index:
            mapping[i] = [index, index + 1]
        else:
            mapping[i] = [i + 1]
    return new, mapping


def merge_words(transcript: Sequence[tuple[str, float, float]], index: int
                ) -> tuple[list[tuple[str, float, float]],
                           dict[int, list[int]]]:
    """Merge two adjacent found words into one (B153).

    Merges ``transcript[index]`` and ``transcript[index + 1]`` (text
    joined, time span from the start of the first to the end of the
    second). Returns the new list and an index mapping
    ``old -> [new, ...]``.
    """
    out = list(transcript)
    if not (0 <= index < len(out) - 1):
        return out, {i: [i] for i in range(len(out))}
    (ta, sa, _), (tb, _, eb) = out[index], out[index + 1]
    merged = (f"{ta} {tb}".strip(), sa, eb)
    new = out[:index] + [merged] + out[index + 2:]
    mapping: dict[int, list[int]] = {}
    for i in range(len(out)):
        if i <= index:
            mapping[i] = [i]
        elif i == index + 1:
            mapping[i] = [index]
        else:
            mapping[i] = [i - 1]
    return new, mapping


def remap_pins(pins: dict[int, list[int]],
               mapping: dict[int, list[int]]) -> dict[int, list[int]]:
    """Apply a transcript index mapping to the couplings (B153)."""
    result: dict[int, list[int]] = {}
    for li, targets in pins.items():
        new: list[int] = []
        for target in targets:
            new.extend(mapping.get(target, [target]))
        # clean up duplicates/order
        gezien: list[int] = []
        for target in new:
            if target not in gezien:
                gezien.append(target)
        result[li] = gezien
    return result


def cut_lyric(lyrics: Sequence[tuple[str, int]], index: int,
              char_offset: int | None = None
              ) -> tuple[list[tuple[str, int]], dict[int, list[int]]]:
    """Cut a lyrics word in two (B156).

    ``lyrics`` is a list of ``(text, line number)``. Returns the new list
    and a key mapping ``old index -> [new, ...]`` to remap the couplings
    (which are keyed on the lyrics index) with.
    """
    out = list(lyrics)
    if not (0 <= index < len(out)):
        return out, {i: [i] for i in range(len(out))}
    text_value, line_number = out[index]
    snijpunt = len(text_value) // 2 if char_offset is None else char_offset
    snijpunt = max(1, min(len(text_value) - 1, snijpunt)) if len(text_value) >= 2 else 0
    if snijpunt <= 0:
        return out, {i: [i] for i in range(len(out))}
    left, right = text_value[:snijpunt].strip(), text_value[snijpunt:].strip()
    new = out[:index] + [(left, line_number), (right, line_number)] + out[index + 1:]
    mapping: dict[int, list[int]] = {}
    for i in range(len(out)):
        if i < index:
            mapping[i] = [i]
        elif i == index:
            mapping[i] = [index, index + 1]
        else:
            mapping[i] = [i + 1]
    return new, mapping


def merge_lyrics(lyrics: Sequence[tuple[str, int]], index: int
                 ) -> tuple[list[tuple[str, int]], dict[int, list[int]]]:
    """Merge two adjacent lyrics words into one (B156)."""
    out = list(lyrics)
    if not (0 <= index < len(out) - 1):
        return out, {i: [i] for i in range(len(out))}
    (ta, ra), (tb, _) = out[index], out[index + 1]
    new = out[:index] + [(f"{ta} {tb}".strip(), ra)] + out[index + 2:]
    mapping: dict[int, list[int]] = {}
    for i in range(len(out)):
        if i <= index:
            mapping[i] = [i]
        elif i == index + 1:
            mapping[i] = [index]
        else:
            mapping[i] = [i - 1]
    return new, mapping


def remap_pin_keys(pins: dict[int, list[int]],
                   mapping: dict[int, list[int]]) -> dict[int, list[int]]:
    """Remap the KEYS (lyrics index) of the couplings (B156).

    With a split (``li -> [a, b]``) the first part keeps the existing
    coupling; with a merge (``a, b -> c``) the couplings of both words
    are merged.
    """
    result: dict[int, list[int]] = {}
    for li, targets in pins.items():
        target_list = mapping.get(li, [li])
        first = target_list[0]
        bestaand = result.get(first, [])
        for target in targets:
            if target not in bestaand:
                bestaand.append(target)
        result[first] = bestaand
    return result


def trim_tail_matches(aligned: Sequence[AlignedWord],
                      min_sim: float = 0.45) -> tuple[AlignedWord, ...]:
    """Uncouple a tail of weak matches (B159).

    On a fade-out Whisper no longer transcribes the repeated closing lines
    reliably; the alignment then carries the last well-heard word through
    to all those repetitions. This function walks back from the end and
    releases coupled words with a low similarity, until the first reliable
    match (``sim >= min_sim``). That way the reliable core remains and the
    'fan' in the tail disappears.
    """
    out = list(aligned)
    for i in range(len(out) - 1, -1, -1):
        word = out[i]
        if word.start is None:
            continue                     # already loose; on to the left
        if word.sim < min_sim:
            out[i] = AlignedWord(word.lyric, None, None, None, 0.0)
        else:
            break                        # first reliable match: stop
    return tuple(out)


def extend_coupling(lyric_text: str,
                    transcript: Sequence[tuple[str, float, float]],
                    base_index: int, claimed: set[int],
                    max_span: int = 3, min_gain: float = 0.05) -> list[int]:
    """Extend a 1-to-1 coupling with adjacent found words (B191).

    Whisper sometimes chops a sung word into pieces ("Tinus" -> "Tien" +
    "Is"): the alignment then only couples to the first piece. This
    function checks whether attaching the next found word - one not yet
    claimed by another lyrics word - noticeably (``min_gain``) improves
    the phonetic similarity and if so, extends the coupling to at most
    ``max_span`` words. Returns the list of transcript indices.
    """
    if not (0 <= base_index < len(transcript)):
        return [base_index]
    base_key = phonetic_key(lyric_text)
    keys = [phonetic_key(transcript[base_index][0])]
    best_indices = [base_index]
    best_sim = similarity(base_key, keys[0])
    idx = base_index
    for _ in range(max_span - 1):
        idx += 1
        if idx >= len(transcript) or idx in claimed:
            break
        keys.append(phonetic_key(transcript[idx][0]))
        sim = similarity(base_key, "".join(keys))
        if sim >= best_sim + min_gain:
            best_indices = list(range(base_index, idx + 1))
            best_sim = sim
    return best_indices


#: Non-lexical vocalises that must not disturb the alignment (B213).
_VOCALISE = {"na", "la", "oh", "ah", "ho", "da", "ba", "hey", "ya",
             "woah", "wo", "uh", "doo", "ooh", "yeah"}


def is_filler_word(text: str) -> bool:
    """Is this lyrics word a non-lexical vocalise (na, la-la, na-na-na)?

    Purely on the form: a short vocalise or a repetition of one. Words like
    'banana' or 'mama' are deliberately left out (only known vocalise bases
    count), so that real text is not skipped by accident (B213).
    """
    import re as _re
    core = _re.sub(r"[^a-z]", "", text.lower())
    if not core:
        return False
    if core in _VOCALISE:
        return True
    for base in _VOCALISE:
        if len(core) >= 2 * len(base) and len(core) % len(base) == 0 \
                and core == base * (len(core) // len(base)):
            return True
    return False


def is_repeated_filler_line(words: Sequence[str], min_repeats: int = 3
                            ) -> bool:
    """Is this a lyrics line that deliberately consists of repeated
    vocalises (e.g. "La la la la", B286)?

    If EVERY word on the line is a vocalise (``is_filler_word``) AND the
    line has at least ``min_repeats`` words, this is not incidental
    filling but the intended lyrics themselves - think of a chorus that
    literally consists of "la la la". ``align_lyrics`` (with
    ``skip_filler=True``) must not skip such lines: the repetition is not
    there by accident, so it should simply take part in the normal
    alignment. A short line (fewer than ``min_repeats`` words) does not
    count, even if all words are vocalises - that is too little to tell
    "deliberately repeated" from "a chance filler word".
    """
    if len(words) < min_repeats:
        return False
    return all(is_filler_word(w) for w in words)


def repeated_filler_lines(lyrics: Sequence[LyricWord], min_repeats: int = 3
                          ) -> frozenset[int]:
    """Lyrics line numbers that are deliberately repeated vocalises (B286).

    Groups the lyrics words per line (``LyricWord.line``) and returns the
    line numbers for which ``is_repeated_filler_line`` holds. Used by
    ``align_lyrics`` to exempt such lines from the normal filler word
    skipping (``skip_filler``).
    """
    per_line: dict[int, list[str]] = {}
    for w in lyrics:
        per_line.setdefault(w.line, []).append(w.text)
    return frozenset(line_number for line_number, words in per_line.items()
                     if is_repeated_filler_line(words, min_repeats))


def creative_couplings(lyric_texts: Sequence[str],
                       transcript: Sequence[tuple[str, float, float]],
                       targets: Sequence[Sequence[int]],
                       min_gain: float = -0.05, floor: float = 0.5,
                       blocked: Collection[int] = (),
                       ) -> list[list[int]]:
    """Supplement the automatic coupling 'creatively' (B228).

    ``targets`` = per lyrics word the current transcript indices.
    Two improvements, both safe within the local anchor window:

    (a) If an uncoupled word stands next to a 1-to-1 coupled word and the
        two words TOGETHER fit that same found word phonetically at least
        as well, couple the uncoupled word to it as well (2-to-1, e.g.
        ``fort`` + ``minable`` -> ``formidable``).
    (b) An uncoupled word between two anchors that matches strongly
        (>=0.7) with a still free found word WITHIN that anchor window is
        coupled 1-to-1 after all (this keeps distant duplicates such as
        'et'/'mais' out of range).

    ``blocked`` holds transcript indices that may never be coupled
    automatically (B309): the words that the hallucination filter threw
    out are shown in the editor but are deliberately not offered to the
    automatic coupling - the user can still couple them by hand.
    """
    out = [list(t) for t in targets]
    n = len(lyric_texts)
    keys = [phonetic_key(t) for t in lyric_texts]
    tkeys = [phonetic_key(w[0]) for w in transcript]
    forbidden = set(blocked)
    # (a) reverse merge
    for i in range(n):
        if out[i]:
            continue
        for nb in (i - 1, i + 1):
            if not (0 <= nb < n) or len(out[nb]) != 1:
                continue
            tj = out[nb][0]
            if not (0 <= tj < len(transcript)) or tj in forbidden:
                continue
            base = similarity(keys[nb], tkeys[tj])
            left, right = (i, nb) if i < nb else (nb, i)
            comb = similarity(keys[left] + keys[right], tkeys[tj])
            if comb >= base + min_gain and comb >= floor:
                out[i] = [tj]
                break
    # (b) real 1-to-1 gaps within the anchor window
    claimed = {tj for ts in out for tj in ts}
    for i in range(n):
        if out[i]:
            continue
        prev_a = next((j for j in range(i - 1, -1, -1) if out[j]), None)
        next_a = next((j for j in range(i + 1, n) if out[j]), None)
        if prev_a is None or next_a is None:
            continue
        lo, hi = max(out[prev_a]) + 1, min(out[next_a])
        best = (0.0, None)
        for tj in range(lo, hi):
            if tj in claimed or tj in forbidden \
                    or not (0 <= tj < len(transcript)):
                continue
            s = similarity(keys[i], tkeys[tj])
            if s > best[0]:
                best = (s, tj)
        if best[1] is not None and best[0] >= 0.7:
            out[i] = [best[1]]
            claimed.add(best[1])
    return out


#: Threshold for a successful anchor-window match of a filler word (B276).
#: Slightly lower than ``_TARGET_SIM`` because filler words are often short
#: (e.g. "oh", "da"), which makes small transcription differences weigh
#: more heavily; a real phonetic hit scores well above this.
_FILLER_MATCH_FLOOR = 0.6
#: Slightly more lenient threshold if the karaoke text on the same line
#: contains real (non-filler-word) text (B276): then it is extra important
#: to find the match, because that time determines where karaoke content
#: ends up.
_FILLER_MATCH_FLOOR_PRIORITY = 0.5


def align_lyrics(lyrics: Sequence[LyricWord],
                 segments: Sequence[Segment],
                 skip_filler: bool = False,
                 priority_lines: frozenset[int] | None = None
                 ) -> tuple[AlignedWord, ...]:
    """Align the lyrics onto the transcription (phonetic, in order).

    With ``skip_filler`` (B213) filler words (na-na, la-la) are not taken
    into the main alignment (DP): they would pull the lines of the real
    words askew if they happened to couple wrongly there. Instead every
    filler word first gets its own match attempt after the DP, within the
    anchor window of the nearest words before and after it that WERE
    coupled (B276): if Whisper really does sing the filler word out (e.g.
    "oh" between two coupled words), it is coupled after all; otherwise it
    stays uncoupled and its timing comes via the vocal energy (B209).
    ``priority_lines`` (lyrics line numbers, B276) lowers the match
    threshold for filler words on lines whose karaoke-text counterpart
    contains real (non-filler-word) content - there the timing is extra
    important. Simultaneous background vocals (``LyricWord.bg``, B264)
    stay out of the DP - they sound at the same time as the lead and
    would snatch away its transcription words in a matcher that runs in
    order - but they do get their own attempt afterwards, within the
    anchor window and only on transcription words that no coupled word
    has claimed (B486). A line that deliberately consists of repeated vocalises
    (e.g. "La la la la", ``repeated_filler_lines``, B286) is NEVER
    skipped: those words are not there by accident, so they should simply
    take part in the main alignment. The returned tuple keeps the original
    word order/indices.
    """
    priority = priority_lines or frozenset()
    repeated = repeated_filler_lines(lyrics)  # B286
    skip = frozenset(i for i, w in enumerate(lyrics)
                     if w.bg or (skip_filler and is_filler_word(w.text)
                                and w.line not in repeated))
    if not skip:
        return _align_core(lyrics, segments)

    real_positions = [i for i in range(len(lyrics)) if i not in skip]
    real = [lyrics[i] for i in real_positions]
    part = _align_core(real, segments)
    result = [AlignedWord(w, None, None, None, 0.0) for w in lyrics]
    for pos, aw in zip(real_positions, part):
        result[pos] = aw

    # B276/B486: try to match skipped words after all within the anchor
    # window of their neighbours. Background vocals used to be excluded
    # here too, and that was one step too careful: keeping them out of
    # the DP is what matters (they sound at the same time as the lead and
    # would snatch its words in a matcher that runs in order), but a
    # separate attempt afterwards costs the lead nothing - the words it
    # already has are claimed - and every hit is an extra anchor in a
    # stretch where there was none.
    fillable = [i for i in range(len(lyrics)) if i in skip]
    restored = 0
    if fillable:
        transcript = [(word.text, float(word.start), float(word.end))
                     for word in _meaningful_words(segments)]  # B239
        # transcript index -> claimed? (already used by a coupled word)
        claimed: set[int] = set()
        for aw in result:
            if aw.start is None or aw.matched_text is None:
                continue
            # 2:1/1:2 couplings share a transcript word with a neighbour;
            # the exact (start,end) then does not occur 1-to-1. Best-effort
            # claim based on time overlap instead of an exact match.
            for tj, (_txt, t_start, t_end) in enumerate(transcript):
                if t_start < aw.end and t_end > aw.start:
                    claimed.add(tj)

        for i in fillable:
            prev_a = next((p for p in range(i - 1, -1, -1)
                          if result[p].start is not None), None)
            next_a = next((p for p in range(i + 1, len(lyrics))
                          if result[p].start is not None), None)
            lo = 0.0 if prev_a is None else result[prev_a].end
            hi = (transcript[-1][2] if transcript else 0.0) \
                if next_a is None else result[next_a].start
            # B288: test the LINE NUMBER of this word against the
            # priority lines, not the word index ``i``.
            # ``priority_lines`` contains line numbers; ``i`` is the
            # position in the word list. Those two were being mixed up,
            # so the more lenient threshold never kicked in where it was
            # meant to (a song has many more words than lines) and
            # instead kicked in at random for the word whose index
            # happened to coincide with a priority line number.
            floor = (_FILLER_MATCH_FLOOR_PRIORITY
                    if lyrics[i].line in priority
                    else _FILLER_MATCH_FLOOR)
            key_i = phonetic_key(lyrics[i].text)
            best: tuple[float, int | None] = (0.0, None)
            for tj, (text, t_start, t_end) in enumerate(transcript):
                if tj in claimed or not (0 <= tj < len(transcript)):
                    continue
                if t_start < lo or t_end > hi:
                    continue
                sim = similarity(key_i, phonetic_key(text))
                if sim > best[0]:
                    best = (sim, tj)
            if best[1] is not None and best[0] >= floor:
                text, t_start, t_end = transcript[best[1]]
                result[i] = AlignedWord(lyrics[i], t_start, t_end, text,
                                          best[0])
                claimed.add(best[1])
                restored += 1

    logger.info(t("log_alignment_skipped_words"), len(skip), restored)
    return tuple(result)


def _align_core(lyrics: Sequence[LyricWord],
                segments: Sequence[Segment]) -> tuple[AlignedWord, ...]:
    """The actual phonetic alignment (Needleman-Wunsch)."""
    transcript = [(word.text, float(word.start), float(word.end))
                  for word in _meaningful_words(segments)]  # B239
    lyric_keys = [phonetic_key(word.text) for word in lyrics]
    trans_keys = [phonetic_key(text) for text, _, _ in transcript]
    # B274: a lyrics word consisting purely of digits (e.g. "500") cannot
    # be given one fixed key, because Whisper sometimes writes such a
    # number as digits and sometimes written out (in NL or EN) - which
    # form matches best phonetically therefore depends on what it is laid
    # against. ``_lyric_sim`` therefore picks the best form dynamically
    # per comparison instead of using the fixed (Dutch) ``lyric_keys[i]``;
    # for an ordinary lyrics word this is identical to the fixed key.
    number_words = [is_pure_number(word.text) for word in lyrics]

    def _lyric_key_for(i: int, other_key: str) -> str:
        if number_words[i]:
            return number_key_best_match(lyrics[i].text, other_key)
        return lyric_keys[i]

    def _lyric_sim(i: int, other_key: str) -> float:
        return similarity(_lyric_key_for(i, other_key), other_key)

    def _lyric_pair_sim(i: int, other_key: str) -> float:
        # m21: two lyrics words (i and i+1) together against one
        # transcript key. If one of the two is a digit word, its best
        # form is chosen against the FULL combination
        # (e.g. "500" + "meter" against "vijfhonderd meter").
        key_a = (number_key_best_match(lyrics[i].text, other_key)
                if number_words[i] else lyric_keys[i])
        key_b = (number_key_best_match(lyrics[i + 1].text, other_key)
                if number_words[i + 1] else lyric_keys[i + 1])
        return similarity(key_a + key_b, other_key)

    def _m21_best_half_sim(i: int, other_key: str) -> float:
        # B281: each lyrics word of the pair SEPARATELY against the one
        # transcript key - the best of the two must be reasonable,
        # otherwise this is presumably a lyrics word being stuck onto an
        # unrelated piece of transcription.
        key_a = (number_key_best_match(lyrics[i].text, other_key)
                if number_words[i] else lyric_keys[i])
        key_b = (number_key_best_match(lyrics[i + 1].text, other_key)
                if number_words[i + 1] else lyric_keys[i + 1])
        return max(similarity(key_a, other_key), similarity(key_b, other_key))

    def _m12_best_half_sim(i: int, key_a: str, key_b: str) -> float:
        # B281: the one lyrics word SEPARATELY against each of the two
        # transcript keys.
        lyric_key = _lyric_key_for(i, key_a + key_b)
        return max(similarity(lyric_key, key_a), similarity(lyric_key, key_b))

    n, m = len(lyrics), len(transcript)

    negative = float("-inf")
    score = [[negative] * (m + 1) for _ in range(n + 1)]
    move: list[list[tuple[str, int, int] | None]] = [
        [None] * (m + 1) for _ in range(n + 1)]
    score[0][0] = 0.0

    for i in range(n + 1):
        for j in range(m + 1):
            current = score[i][j]
            if current == negative:
                continue
            if i < n and current - _GAP_PENALTY > score[i + 1][j]:
                score[i + 1][j] = current - _GAP_PENALTY
                move[i + 1][j] = ("gl", i, j)
            if j < m and current - _GAP_PENALTY > score[i][j + 1]:
                score[i][j + 1] = current - _GAP_PENALTY
                move[i][j + 1] = ("gt", i, j)
            if i < n and j < m:
                value = current + (_lyric_sim(i, trans_keys[j])
                                   - _MATCH_BASE)
                if value > score[i + 1][j + 1]:
                    score[i + 1][j + 1] = value
                    move[i + 1][j + 1] = ("m11", i, j)
            if i + 1 < n and j < m:
                # B281: a weak multiple coupling (e.g. an interjection
                # that happens to score more cheaply than an unexplained
                # gap) may never be chosen, regardless of the DP cost -
                # hence this bound BEFORE the score comparison, on the
                # BEST of the two separate half-similarities (a bound on
                # the combined score turned out to break existing,
                # intended couplings like "Kedeng Kedeng"<->"de trein").
                if _m21_best_half_sim(i, trans_keys[j]) >= _MIN_MULTI_HALF_SIM:
                    sim = _lyric_pair_sim(i, trans_keys[j])
                    value = current + (sim - _MATCH_BASE) - _MULTI_PENALTY
                    if value > score[i + 2][j + 1]:
                        score[i + 2][j + 1] = value
                        move[i + 2][j + 1] = ("m21", i, j)
            if i < n and j + 1 < m:
                if _m12_best_half_sim(
                        i, trans_keys[j], trans_keys[j + 1]) \
                        >= _MIN_MULTI_HALF_SIM:  # B281
                    combo_key = trans_keys[j] + trans_keys[j + 1]
                    sim = _lyric_sim(i, combo_key)
                    value = current + (sim - _MATCH_BASE) - _MULTI_PENALTY
                    if value > score[i + 1][j + 2]:
                        score[i + 1][j + 2] = value
                        move[i + 1][j + 2] = ("m12", i, j)

    matched: dict[int, AlignedWord] = {}
    i, j = n, m
    while (i > 0 or j > 0) and move[i][j] is not None:
        kind, previous_i, previous_j = move[i][j]  # type: ignore[misc]
        if kind == "m11":
            text, start, end = transcript[previous_j]
            sim = _lyric_sim(previous_i, trans_keys[previous_j])
            matched[previous_i] = AlignedWord(lyrics[previous_i], start, end,
                                              text, sim)
        elif kind == "m21":
            text, start, end = transcript[previous_j]
            sim = _lyric_pair_sim(previous_i, trans_keys[previous_j])
            middle = (start + end) / 2.0
            matched[previous_i] = AlignedWord(lyrics[previous_i], start,
                                              middle, text, sim)
            matched[previous_i + 1] = AlignedWord(lyrics[previous_i + 1],
                                                  middle, end, text, sim)
        elif kind == "m12":
            text_a, start_a, _ = transcript[previous_j]
            text_b, _, end_b = transcript[previous_j + 1]
            combo_key = trans_keys[previous_j] + trans_keys[previous_j + 1]
            sim = _lyric_sim(previous_i, combo_key)
            matched[previous_i] = AlignedWord(lyrics[previous_i], start_a,
                                              end_b, f"{text_a} {text_b}",
                                              sim)
        i, j = previous_i, previous_j

    aligned = tuple(
        matched.get(index, AlignedWord(lyrics[index], None, None, None, 0.0))
        for index in range(n))
    logger.info(t("log_lyrics_aligned"),
                sum(1 for word in aligned if word.start is not None), n)
    return aligned


def extra_intervals(
    aligned: Sequence[AlignedWord],
    target_keys: set[str],
    known_spans: Sequence[tuple[float, float]],
) -> list[tuple[float, float, str]]:
    """Find extra time slots to damp, based on the lyrics.

    1. Target words that are coupled to a transcription word but fall
       outside the known cluster occurrences (e.g. a kedeng that
       Whisper wrote down as something else).
    2. Gaps: a contiguous series of uncoupled target words between two
       anchors is estimated at the time slot between those anchors.

    Times are on the timeline of the ORIGINAL.
    """
    def is_target(text: str) -> bool:
        key = phonetic_key(text)
        return any(similarity(key, target) >= _TARGET_SIM
                   for target in target_keys)

    def known(start: float, end: float) -> bool:
        return any(start < k_end - 0.1 and end > k_start + 0.1
                   for k_start, k_end in known_spans)

    extras: list[tuple[float, float, str]] = []
    targets = [is_target(word.lyric.text) for word in aligned]

    for word, target in zip(aligned, targets):
        if target and word.start is not None and not known(word.start,
                                                           word.end):
            extras.append((word.start, word.end,
                           f"TEKST {word.lyric.text.upper()}"))

    index = 0
    while index < len(aligned):
        if aligned[index].start is None:
            run_start = index
            while index < len(aligned) and aligned[index].start is None:
                index += 1
            run_end = index  # exclusive
            if not all(targets[run_start:run_end]):
                continue
            previous = next((aligned[k] for k in range(run_start - 1, -1, -1)
                             if aligned[k].end is not None), None)
            following = next((aligned[k] for k in range(run_end,
                                                        len(aligned))
                              if aligned[k].start is not None), None)
            if previous is None or following is None:
                continue
            gap_start, gap_end = previous.end, following.start
            if (_MIN_ESTIMATED_GAP_S <= gap_end - gap_start
                    <= _MAX_ESTIMATED_GAP_S and not known(gap_start,
                                                          gap_end)):
                extras.append((gap_start, gap_end, "TEKST (geschat)"))
        else:
            index += 1
    logger.info(t("log_lyrics_extras"), len(extras))
    return extras


def relabel_clusters(clusters: Sequence[Cluster],
                     aligned: Sequence[AlignedWord]) -> tuple[Cluster, ...]:
    """Replace cluster labels with the official lyrics (leading)."""
    timed = [word for word in aligned if word.start is not None]
    result: list[Cluster] = []
    for cluster in clusters:
        counts: Counter[str] = Counter()
        for occurrence in cluster.occurrences:
            for word in timed:
                if (word.start < occurrence.end
                        and word.end > occurrence.start):
                    counts[word.lyric.text.upper()] += 1
        if counts:
            result.append(replace(cluster,
                                  label=counts.most_common(1)[0][0]))
        else:
            result.append(cluster)
    return tuple(result)


def write_report(aligned: Sequence[AlignedWord], path: Path) -> None:
    """Write a readable alignment report (the lyrics are leading)."""
    lines: list[str] = []
    current_line = -1
    for word in aligned:
        if word.lyric.line != current_line:
            current_line = word.lyric.line
            lines.append("")
        if word.start is None:
            lines.append(f"  {word.lyric.text:<20} -> (niet gekoppeld)")
        else:
            lines.append(f"  {word.lyric.text:<20} -> "
                         f"{word.matched_text or '':<24} "
                         f"{word.start:7.2f}-{word.end:7.2f}  "
                         f"sim {word.sim:.2f}")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    logger.info(t("log_alignment_report"), path)
