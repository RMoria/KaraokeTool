"""The build of a song, read from its text (v1.0.15, B600).

The owner's observation, and his hand timings bear it out: in most
songs a chorus, a bridge and often a verse come back with the same
timing. Measured over eighteen of his songs: the line starts inside a
block that comes back with the same text differ 0.01 to 0.17 s between
its occurrences (mostly under 0.07 s); verses with the same number of
lines, once stretched to the same length, 0.05 to 0.14 s; one song has
seven verses of 25.7 to 26.8 s. That build can be read from the text
before anything is heard.

Two kinds of kinship, because they may be used differently:

* **the same text** - the same number of lines and at least
  :data:`SAME_SHARE` of the same words, so one "hey" more or less does
  not matter. Such blocks are LINKED: an edit in one holds for the
  others, and what is heard in one may be combined with the others;
* **the same shape** - the same number of lines with about the same
  number of syllables per line, but other words (verses). Those share
  the length and the place of the block as a whole; their sentences,
  words and syllables are always listened to on their own.

The links are the owner's to change, on tab 1 (:mod:`block_dialog`):
filled in by the program, stored per project, and checked against the
text every time they are read - a block whose text changed falls back
to what the program would link.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Sequence

#: Blocks with this share of the same words count as the same text.
SAME_SHARE = 0.85

#: Two lines have the same shape when their syllable counts differ by at
#: most this many, or this share of the larger.
SHAPE_SYLLABLES = 2
SHAPE_SHARE = 0.25

#: The step in ``project.json`` that holds the links.
STEP = "block_links"


def _field(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) \
        else getattr(item, name, default)


def words_of(text: str) -> list[str]:
    """The words of a line, markup and punctuation left out."""
    return re.findall(r"\w+", re.sub(r"\[[^\]]*\]", " ", str(text).lower()))


def _syllables(text: str) -> int:
    from .timing import split_syllables

    return sum(max(1, len(split_syllables(word)))
               for word in words_of(text))


@dataclass(frozen=True)
class Block:
    """One block of the karaoke text: the lines between two empty ones."""

    number: int
    lines: tuple[int, ...]
    texts: tuple[str, ...]

    @property
    def key(self) -> str:
        return " / ".join(" ".join(words_of(text)) for text in self.texts)

    @property
    def words(self) -> list[str]:
        return [word for text in self.texts for word in words_of(text)]

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(_syllables(text) for text in self.texts)

    @property
    def title(self) -> str:
        return str(self.texts[0]) if self.texts else ""


def blocks_of(lines: Sequence[Any]) -> list[Block]:
    """The blocks of a song, from its lines (text lines, timed lines or
    the editor's dicts - anything with a ``text`` and a ``block``). A
    line whose ``bg`` is set belongs to its block but not to its text:
    background vocals do not make two choruses different."""
    order: list[int] = []
    members: dict[int, list[tuple[int, str]]] = {}
    for position, line in enumerate(lines):
        number = int(_field(line, "block", 0) or 0)
        if number not in members:
            members[number] = []
            order.append(number)
        index = _field(line, "index", position)
        if _field(line, "bg", False):
            continue
        members[number].append((int(index), str(_field(line, "text", ""))))
    return [Block(number, tuple(i for i, _t in members[number]),
                  tuple(text for _i, text in members[number]))
            for number in order if members[number]]


def same_text(first: Block, second: Block) -> bool:
    """The same lines, bar a word here and there."""
    if len(first.lines) != len(second.lines) or not first.lines:
        return False
    if first.key == second.key:
        return True
    ratio = difflib.SequenceMatcher(None, first.words, second.words,
                                    autojunk=False).ratio()
    return ratio >= SAME_SHARE


def same_shape(first: Block, second: Block) -> bool:
    """As many lines, each about as long in syllables."""
    if len(first.lines) != len(second.lines) or len(first.lines) < 2:
        return False
    return all(abs(a - b) <= max(SHAPE_SYLLABLES, SHAPE_SHARE * max(a, b))
               for a, b in zip(first.shape, second.shape))


def _groups(blocks: Sequence[Block], kin) -> list[list[int]]:
    """Block numbers that belong together, in groups of two or more."""
    parent = {block.number: block.number for block in blocks}

    def root(number: int) -> int:
        while parent[number] != number:
            parent[number] = parent[parent[number]]
            number = parent[number]
        return number

    for n, first in enumerate(blocks):
        for second in blocks[n + 1:]:
            if kin(first, second):
                parent[root(second.number)] = root(first.number)
    found: dict[int, list[int]] = {}
    for block in blocks:
        found.setdefault(root(block.number), []).append(block.number)
    return [sorted(group) for group in found.values() if len(group) > 1]


def auto_links(blocks: Sequence[Block]) -> list[list[int]]:
    """The links the program makes: blocks with the same text."""
    return _groups(blocks, same_text)


def shape_groups(blocks: Sequence[Block]) -> list[list[int]]:
    """Blocks of the same shape, the same text or not."""
    return _groups(blocks, lambda a, b: same_text(a, b) or same_shape(a, b))


def clean_links(groups: Sequence[Sequence[int]],
                blocks: Sequence[Block]) -> list[list[int]]:
    """Groups of existing blocks with as many lines each, two or more,
    none in two groups; the first group wins a block."""
    by_number = {block.number: block for block in blocks}
    seen: set[int] = set()
    out: list[list[int]] = []
    for group in groups:
        kept = []
        for number in group:
            number = int(number)
            if number in by_number and number not in seen:
                kept.append(number)
        if len(kept) < 2:
            continue
        size = len(by_number[kept[0]].lines)
        kept = [n for n in kept if len(by_number[n].lines) == size]
        if len(kept) >= 2:
            seen.update(kept)
            out.append(sorted(kept))
    return out


def stored_links(step: dict | None,
                 blocks: Sequence[Block]) -> list[list[int]] | None:
    """The owner's links, or ``None`` when there are none or the text
    they were made on is not the text of today."""
    if not step:
        return None
    keys = {int(k): str(v) for k, v in (step.get("keys") or {}).items()}
    by_number = {block.number: block for block in blocks}
    if any(number not in by_number or by_number[number].key != key
           for number, key in keys.items()):
        return None
    return clean_links(step.get("groups") or [], blocks)


def step_for(groups: Sequence[Sequence[int]],
             blocks: Sequence[Block]) -> dict:
    """What is stored: the groups, and the text of every block, so a
    changed text is noticed."""
    return {"groups": clean_links(groups, blocks),
            "keys": {str(block.number): block.key for block in blocks}}


def partners(groups: Sequence[Sequence[int]], number: int) -> list[int]:
    """The blocks linked to ``number``, without itself."""
    for group in groups:
        if number in group:
            return [other for other in group if other != number]
    return []
