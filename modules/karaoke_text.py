"""Karaoke text for the video: logical lines with vocals/crowd/bg marking.

The karaoke text (the new text to be sung) is an ordinary text file
with one logical sentence per line. Parts that are sung by the
audience (crowd) are marked with blocks:

    [crowd]
    La-la-la...
    Hey...
    [/crowd]

Lines within such a block colour white -> red -> grey in the video
instead of white -> green -> grey. Inline is possible too: a part
``[crowd]Waertje![/crowd]`` in the middle of a line is split off as its
own crowd line. Empty lines separate sections and are skipped; lines
that begin with ``#`` are comments (e.g. headings such as ``# Intro``)
and are not sung or shown.

Simultaneous background vocals (e.g. a second voice singing "Tonight,
tonight" while the lead vocals continue) are marked with
``[bg]...[/bg]`` (B264), analogous to ``[crowd]``: block notation,
separate line or inline. An INLINE piece stays part of its sentence and
only marks its own words (B484); it may overlap its neighbours in time
and never reaches the render. A whole ``[bg]`` line does not sound after the
previous line but at the same time as it: it does not count in the
sentence coupling (just like crowd, which does not count unless the
number matches exactly, B260) and gets the same time slot in the timing
as the preceding line. Such a line is by default not shown in "Refine
timing" and not rendered (``uitgeschakeld``), but the text does count
for Whisper's ``initial_prompt`` (B263) and the hallucination detection
(B258).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from .translations import t

logger = logging.getLogger(__name__)

#: B555: ``karaoketekst.txt`` until v1.0.5. See
#: ``song_text.LYRICS_FILENAME`` for the reasoning.
FILENAME = "karaoke_text.txt"

_CROWD_START = ("[crowd]",)
_CROWD_END = ("[/crowd]", "[einde crowd]")
_BG_START = ("[bg]",)
_BG_END = ("[/bg]", "[einde bg]")

#: Sentinel syllable for an inline pause (B107). Stays within the same
#: logical sentence, but splits it into two parts for placement/timing and
#: gets dots on the average beat in the render. ``[pause]``/``[pauze]``
#: in the karaoke text are converted into this.
PAUSE_TOKEN = "…"          # horizontal ellipsis
_PAUSE_RE = re.compile(r"(?i)\s*\[pau[sz]e\]\s*")


def apply_pause(text: str) -> str:
    """Convert inline ``[pause]``/``[pauze]`` into a separate pause sign.

    The sign becomes a 'word' of its own so that it falls in the timing as
    a separate syllable (two parts around the pause) and can be drawn as
    dots in the render.
    """
    replaced = _PAUSE_RE.sub(f" {PAUSE_TOKEN} ", text)
    return re.sub(r"\s+", " ", replaced).strip()


def is_pause(text: str) -> bool:
    """True if a syllable is the pause sign (B107)."""
    return text.strip() == PAUSE_TOKEN


@dataclass(frozen=True)
class TextLine:
    """One logical text line for the karaoke video."""

    index: int
    text: str
    crowd: bool
    block: int = 0
    #: Word indexes (in ``text``) that belong to an inline ``[crowd]`` part
    #: and get the crowd colour (red) in the render, while the rest of the
    #: sentence stays vocals (B179a). Empty for a whole vocals or whole
    #: crowd line.
    crowd_words: frozenset[int] = frozenset()
    #: True = the WHOLE line is simultaneous background vocals (B264):
    #: sounds at the same time as the preceding line instead of after it.
    #: Does not count in the sentence coupling and is by default not
    #: shown/rendered (see ``build_coupling``).
    bg: bool = False
    #: B484: word indexes (in ``text``) of an INLINE ``[bg]`` piece, the
    #: same shape as ``crowd_words``. Such a piece is background vocals
    #: while the rest of the sentence is not: it stays part of its line
    #: (so no line numbers shift), it may overlap its neighbours in time,
    #: and it never reaches the render. This used to mark the whole line
    #: as bg, which made the sentence disappear from the coupling and
    #: from the original lane of the editor.
    bg_words: frozenset[int] = frozenset()


def _parse_inline(text: str, block_crowd: bool, block_bg: bool = False
                  ) -> tuple[str, bool, frozenset[int], bool, frozenset[int]]:
    """Process inline ``[crowd]`` and ``[bg]`` within one sentence.

    Both stay IN the sentence (with spaces) instead of being split off;
    the words involved are marked, so crowd colours red in the render
    (B179a) and bg is left out of it altogether (B484/B485). Word indexes
    are counted on the final word list, so the two markers can be used in
    the same line without their numbering running apart.

    Returns ``(text, whole_line_crowd, crowd_word_indexes, whole_line_bg,
    bg_word_indexes)``. Is the whole line inside a marker, then the
    corresponding flag is True and its word set empty - the line is then
    crowd (B179b) or bg (B264) at line level.
    """
    parts = re.split(r"(?i)(\[crowd\]|\[/crowd\]|\[bg\]|\[/bg\])", text)
    if len(parts) == 1:
        return (text.strip(), block_crowd, frozenset(), block_bg,
                frozenset(), block_bg)
    words: list[str] = []
    crowd_idx: set[int] = set()
    bg_idx: set[int] = set()
    in_crowd, in_bg = block_crowd, block_bg
    for part in parts:
        lowered = part.lower()
        if lowered == "[crowd]":
            in_crowd = True
        elif lowered == "[/crowd]":
            in_crowd = block_crowd
        elif lowered == "[bg]":
            in_bg = True
        elif lowered == "[/bg]":
            in_bg = False
        else:
            for word in part.split():
                if in_crowd:
                    crowd_idx.add(len(words))
                if in_bg:
                    bg_idx.add(len(words))
                words.append(word)
    text_value = " ".join(words)
    whole_crowd = block_crowd or (bool(words)
                                  and len(crowd_idx) == len(words))
    whole_bg = bool(words) and len(bg_idx) == len(words)
    return (text_value,
            whole_crowd, frozenset() if whole_crowd else frozenset(crowd_idx),
            whole_bg, frozenset() if whole_bg else frozenset(bg_idx), in_bg)


def parse_lines(path: Path) -> tuple[TextLine, ...]:
    """Read the karaoke text and mark crowd/bg blocks.

    Args:
        path: Path to the text file.

    Returns:
        The logical lines, in order, with crowd/bg marking.
    """
    lines: list[TextLine] = []
    crowd = False
    bg = False
    block = 0
    saw_line = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        lowered = stripped.lower()
        if lowered in _CROWD_START:
            crowd = True
            continue
        if lowered in _CROWD_END:
            crowd = False
            continue
        if lowered in _BG_START:
            bg = True
            continue
        if lowered in _BG_END:
            bg = False
            continue
        if not stripped:
            if saw_line:  # empty line = block separation
                block += 1
                saw_line = False
            continue
        if stripped.startswith("#"):
            continue

        # B74: crowd markers stuck to the text also open/close the block
        # (e.g. '[crowd]La-la...' or '...La-la[/crowd]'), as long as they
        # are not both on the same line - then the inline splitting of
        # ``_parse_inline`` does the work.
        close_crowd_after = False
        has_open_c = "[crowd]" in lowered
        has_close_c = "[/crowd]" in lowered
        if has_open_c and not has_close_c:
            crowd = True
            stripped = re.sub(r"(?i)\[crowd\]\s*", "", stripped).strip()
        elif has_close_c and not has_open_c:
            close_crowd_after = True
            stripped = re.sub(r"(?i)\s*\[/crowd\]", "", stripped).strip()
        lowered = stripped.lower()

        # B484: a [bg] marker stuck to the START or END of the line opens
        # or closes a bg section, exactly as with crowd. Are BOTH markers
        # on the same line, then the marking belongs to this line only
        # and ``_parse_inline`` works out which words it covers - it used
        # to make the whole line bg, and a sentence with a background
        # tail then disappeared from the coupling and from the editor.
        if not stripped:
            if close_crowd_after:
                crowd = False
            continue

        saw_line = True
        # Inline [pause] stays within this sentence, as a separate pause
        # sign (B107); we leave [crowd]/[bg] markers in place so that
        # _parse_inline can mark the words.
        with_pause = apply_pause(stripped)
        text_value, is_crowd, crowd_words, is_bg_line, bg_words, bg = \
            _parse_inline(with_pause, crowd, bg)
        if text_value:
            lines.append(TextLine(index=len(lines), text=text_value,
                                  crowd=is_crowd, block=block,
                                  crowd_words=crowd_words, bg=is_bg_line,
                                  bg_words=bg_words))
        if close_crowd_after:
            crowd = False
    if crowd:
        logger.warning(t("log_karaoke_text_open_crowd"))
    if bg:
        logger.warning(t("log_karaoke_text_open_bg"))
    logger.info(t("log_karaoke_text_loaded"),
                len(lines), sum(1 for line in lines if line.crowd),
                sum(1 for line in lines if line.bg))
    return tuple(lines)
