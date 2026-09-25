"""Word coupling editor (B121).

Couples the 'real' lyrics words to the words found by Whisper, so that
the analysis and clustering work with the right words instead of the
garbled transcription. Purely coupling (no timing/stretching).

Two rows: the found transcription words on top, the lyrics below.
Coupling lines are coloured by confidence (green = high, yellow =
medium, red = low/manually low). Click a word above and a word below to
couple them; click a coupling line to remove it. One lyrics word can be
coupled to several transcription words and vice versa.

The editor shares its basic layout (scroll, clickable boxes, connecting
lines) with later coupling editors such as the syllable/stress editor
(B151/B152).
"""

from __future__ import annotations

import logging
from typing import Callable, Sequence

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout,
                               QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .translations import t

logger = logging.getLogger(__name__)

_BOX_H = 26
_TOP_Y = 40
_BOT_Y = 150
_PATH = 8
_PPW = 90        # pixels per word (width unit)
#: Line marking under the lyrics row (B339): a thin rule plus the line
#: number where a new line of the lyrics starts.
_LINE_MARKER = QColor(170, 178, 186)
_LINE_MARKER_TEXT = QColor(120, 128, 136)

#: Fill colour, border colour and legend key per coupling status of a
#: lyrics word without a coupling (B287/B308/B313). Each status has its
#: own colour plus a dashed border.
#:
#: The word box used to carry a short label as well ("[vul] ", "[hal] ",
#: "[zang] "). That has gone (B317): a code in front of the word made the
#: text itself harder to read and explained nothing without a key
#: anyway. The colour does the marking; the legend above the editor says
#: what it means, once, for all of them. Words without a status (or
#: "coupled") use the normal styling and do not appear here.
_STATUS_STYLE: dict[str, tuple[QColor, QColor, str]] = {
    "filler_skipped": (QColor(250, 225, 180), QColor(200, 130, 20),
                       "legend_filler_skipped"),
    "no_match": (QColor(250, 205, 205), QColor(190, 40, 40),
                 "legend_no_match"),
    "hallucination_filtered": (QColor(225, 205, 240), QColor(120, 60, 170),
                               "legend_hallucination"),
    # B308: Whisper produced nothing at all at this spot (a la-la-la
    # outro, a shouting crowd, a heavily instrumental piece). That is a
    # different problem from a filtered out hallucination and therefore
    # gets its own, deliberately calm grey-blue marking: there is nothing
    # wrong here, there is simply nothing to couple to.
    "transcription_gap": (QColor(214, 222, 230), QColor(90, 115, 140),
                          "legend_transcription_gap"),
    # B313: not coupled, but timed on the vocal stem. Blue-green, because
    # something usable did happen here - it is only a measurement of the
    # singing and not a recognised word.
    "energy_placed": (QColor(200, 232, 226), QColor(30, 130, 120),
                      "legend_energy_placed"),
    # B502: a run of found words in a row that is coupled to nothing at
    # all. That is what a hallucination looks like on screen, and it is
    # the only marking that says something about the FOUND words instead
    # of about the lyrics. Orange-red, and deliberately not struck
    # through: in a song with a passage in another language this is real
    # singing, and then it has to be couplable by hand.
    "suspect_run": (QColor(255, 214, 190), QColor(200, 90, 30),
                    "legend_suspect_run"),
    # B506: the user uncoupled this word himself, and a pin - also an
    # empty one - beats the automatic coupling. Without a marking that
    # is invisible: the word simply stays uncoupled while identical
    # words sit right above it, and nothing on screen says why. At
    # "Lied R" fifty-four words stood like that. Blue, the colour that
    # already means "hand work" in this editor.
    "manually_uncoupled": (QColor(205, 220, 250), QColor(30, 90, 200),
                           "legend_manually_uncoupled"),
    # B521: a run without any coupling whose words DO occur in the
    # lyrics. Then the song sings a line twice while the text writes it
    # once, and the coupling has used those words up - a repetition the
    # text is missing, not an invention. Blue-grey, calm: there is
    # nothing wrong here either, the text is simply shorter than the
    # song.
    "repeat_missing": (QColor(214, 226, 234), QColor(90, 130, 155),
                       "legend_repeat_missing"),
    # B507: background vocals. They are shown everywhere except in the
    # render, so they belong in this lane too - but "not coupled" says
    # nothing about them, and up to v0.145.0 they were quietly counted
    # as coupled. Pale green, like the [bg] block in the timing editor.
    "background": (QColor(214, 238, 216), QColor(70, 130, 75),
                   "legend_background"),
    # v1.0.12: FOUND words that were not heard in the normal run. Heard
    # again from "Listen again" in lilac, laid on the singing by the
    # aligner in sand - both calm, because both are usable, and both
    # distinct, because neither is the same as a word Whisper heard.
    "heard_again": (QColor(232, 222, 245), QColor(125, 95, 170),
                    "legend_heard_again"),
    "aligned": (QColor(240, 232, 208), QColor(160, 130, 60),
                "legend_aligned"),
}


#: The two markings that are a JUDGEMENT and that the user can therefore
#: assign himself (B337). The other three are measurements - "Whisper
#: heard nothing here", "not coupled but timed on the vocal stem",
#: "skipped filler word" - and letting those be set by hand would claim
#: something that is not true.
#: hallucination works on a FOUND word (top row), filler on a lyrics word
#: (bottom row): each on the row where it means something.
MARKABLE = {"hallucination_filtered": "hallucinations",
            "filler_skipped": "fillers"}


def legend_html(clickable: bool = False) -> str:
    """The colour legend as rich text (B317).

    Built from the same table the editor paints with, so a new marking
    cannot end up in the drawing without appearing in the legend. With
    ``clickable`` the two assignable markings become links, so that
    selecting plus clicking assigns them (B337).
    """
    def swatch(fill: QColor, border: QColor, text: str,
               status: str = "") -> str:
        box = (f'<span style="background:{fill.name()};'
               f'border:1px solid {border.name()};">&nbsp;&nbsp;&nbsp;'
               f'</span>&nbsp;{text}')
        if clickable and status in MARKABLE:
            return f'<a href="{status}" style="text-decoration:none;">{box}</a>'
        return box

    parts = [swatch(fill, border, t(key), status)
             for status, (fill, border, key) in _STATUS_STYLE.items()]
    parts.append(swatch(_FILTERED_FILL, _FILTERED_BORDER,
                        t("legend_filtered_word")))
    return " &nbsp;&nbsp;·&nbsp;&nbsp; ".join(parts)

#: Fill and border of a found word that the hallucination filter threw
#: out (B309). Same purple as the "[hal]" marking in the bottom row, so
#: that the two rows tell the same story: this word was there, it is
#: deliberately not being used, and if that is wrong you can still couple
#: it by hand.
_FILTERED_FILL = QColor(238, 230, 246)
_FILTERED_BORDER = QColor(120, 60, 170)



def _sim_color(sim: float, pinned: bool) -> QColor:
    """Colour by coupling probability (green/yellow/red)."""
    if pinned:
        return QColor(60, 120, 220)      # blue = manual
    if sim >= 0.75:
        return QColor(60, 176, 67)
    if sim >= 0.45:
        return QColor(200, 160, 30)
    return QColor(220, 60, 50)


class CouplingCanvas(QWidget):
    """Draws two rows of words and the coupling lines between (B121)."""

    def __init__(self, transcript: list, words: list,
                 on_change: Callable[[dict], None],
                 on_transcript: Callable[[list], None] | None = None,
                 on_lyrics: Callable[[list], None] | None = None,
                 filtered: Sequence[int] = (),
                 found_status: dict | None = None,
                 in_lyrics: Sequence[int] = (),
                 origins: Sequence = ()) -> None:
        super().__init__()
        self._trans = list(transcript)    # [(text,start,end), ...]
        # v1.0.12: where a found word came from when it was not simply
        # heard, by its start time - an index would go stale the moment
        # a word is cut or merged.
        self._origins = {round(float(start), 3): str(origin)
                         for start, origin in origins}
        self._words = list(words)       # editor view words (dicts)
        self._filtered = set(filtered)  # B309: filtered found words
        # B521: which found words occur in the lyrics, so that a run of
        # them can be recognised as a repetition instead of an invention
        # after an edit as well.
        self._in_lyrics = set(in_lyrics)
        #: Lyrics words the user marked as a filler by hand (B528).
        self._marked: set[int] = {
            int(w["index"]) for w in self._words
            if w.get("status") == "filler_skipped"}
        # B502: status per FOUND word, so that this lane carries the
        # same colour codes as the lyrics lane.
        self._found_status = {int(k): str(v)
                              for k, v in (found_status or {}).items()}
        self._on_change = on_change
        self._on_transcript = on_transcript   # B153: edited transcription
        self._on_lyrics = on_lyrics           # B156: edited lyrics
        # Current couplings per lyrics index -> list of transcript indices
        # (1-to-many possible). Manually touched words are in ``_pinned``
        # (those are kept; automatic couplings are not).
        self._targets: dict[int, list[int]] = {
            w["index"]: list(w["transcript_indices"]) for w in words}
        self._pinned: set[int] = {w["index"] for w in words if w["pinned"]}
        self._sel_bot: int | None = None
        self._sel_top: int | None = None    # selected found word (B153)
        # Column layout: coupled pairs exactly above each other (B220).
        self._top_col: list[int] = []
        self._bot_col: list[int] = []
        self._cols = 0
        self._relayout()

    # -- column layout (B220) --------------------------------------------
    def _relayout(self) -> None:
        """Assign each word a column so that a coupled top/bottom pair
        sits exactly above each other; uncoupled words get their own
        column. This keeps the coupling lines straight, even when a row
        contains extra (uncoupled) words such as na-na (B220)."""
        n_top, n_bot = len(self._trans), len(self._words)
        self._top_col = [-1] * n_top
        self._bot_col = [-1] * n_bot
        col = 0
        i = 0  # next top word that has not been placed yet
        # B513: the column of the lyrics word before this one. Every
        # lyrics word must land strictly to the right of it. Without
        # that guard two of them could share a column - and a column IS
        # the position, so they were drawn on exactly the same pixels
        # and ``_hit_row`` gave the leftmost of them at every click. You
        # then click the box you see and the editor couples its
        # neighbour. Measured at "Lied R": 25 unreachable words, and of
        # the 82 manual couplings in that project not one matched what
        # the automatic coupling said - 65 of them pointed one or two
        # found words too far left. The user repaired that list three
        # times and it came back three times.
        last_bot = -1
        for j in range(n_bot):
            target_list = sorted(t for t in self._current_targets(j)
                            if 0 <= t < n_top)
            if not target_list:
                # B320: an uncoupled lyrics word takes the next free
                # column, and the next uncoupled FOUND word joins it in
                # that same column. Previously the two rows were laid out
                # one after the other: the bottom row claimed a column
                # immediately, while the top words only got theirs when a
                # coupled pair came along - and then they all shuffled in
                # behind each other. Over a long uncoupled stretch the
                # rows drifted apart by a column per word (measured: eight
                # words was a shift of 720 pixels), so you could no longer
                # see which found word belonged above which lyrics word.
                own = max(col, last_bot + 1)
                self._bot_col[j] = own
                last_bot = own
                while i < n_top and self._top_col[i] != -1:
                    i += 1
                if i < n_top and not self._is_coupled_top(i):
                    self._top_col[i] = own
                    i += 1
                col = own + 1
                continue
            first = target_list[0]
            while i < first:                       # uncoupled tops before
                if self._top_col[i] == -1:
                    self._top_col[i] = col
                    col += 1
                i += 1
            for tj in target_list:                       # coupled tops (group)
                if self._top_col[tj] == -1:
                    self._top_col[tj] = col
                    col += 1
                i = max(i, tj + 1)
            # Under the FIRST found word of its group (B220). That used
            # to be "the column that was free at this moment", which is
            # something else entirely once the group already had its
            # columns: then the lyrics word landed on a column that its
            # predecessor might already own.
            pair_col = min(self._top_col[tj] for tj in target_list)
            if pair_col <= last_bot:
                # No room under its own group: one place to the right.
                # The coupling line then runs at a slight angle, and
                # that is the smaller evil - a straight line to a word
                # that cannot be seen or clicked is no line at all.
                pair_col = last_bot + 1
            col = max(col, pair_col + 1)
            self._bot_col[j] = pair_col
            last_bot = pair_col
        while i < n_top:                            # remaining tops
            if self._top_col[i] == -1:
                self._top_col[i] = col
                col += 1
            i += 1
        for tj in range(n_top):                     # safety net: all a column
            if self._top_col[tj] == -1:
                self._top_col[tj] = col
                col += 1
        self._cols = max(col, 1)
        width = self._cols * _PPW + 2 * _PATH
        self.setMinimumSize(max(width, 400), _BOT_Y + _BOX_H + 30)

    # -- positions --------------------------------------------------------
    def _top_rect(self, i: int) -> tuple[int, int, int]:
        col = self._top_col[i] if 0 <= i < len(self._top_col) else i
        return _PATH + col * _PPW, _TOP_Y, _PPW - 6

    def _bot_rect(self, i: int) -> tuple[int, int, int]:
        col = self._bot_col[i] if 0 <= i < len(self._bot_col) else i
        return _PATH + col * _PPW, _BOT_Y, _PPW - 6

    def _current_targets(self, li: int) -> list[int]:
        return self._targets.get(li, [])

    def _is_coupled_top(self, tj: int) -> bool:
        """Is this found word coupled to any lyrics word? (B320)

        An uncoupled found word may share a column with an uncoupled
        lyrics word; a coupled one has to wait for its own pair, else it
        would end up above the wrong word.
        """
        return any(tj in targets for targets in self._targets.values())

    def _merged_spans(self) -> dict[int, tuple[int, int]]:
        """Contiguous found words that are shown as one (doubly coupled)
        box (B189). Key = every top index in the group, value = (start,
        end) of the group. When the coupling is undone the group
        disappears by itself, so the boxes split again."""
        spans: dict[int, tuple[int, int]] = {}
        for _li, targets in self._targets.items():
            ts = sorted(t for t in targets if 0 <= t < len(self._trans))
            if len(ts) >= 2 and ts == list(range(ts[0], ts[-1] + 1)):
                for k in ts:
                    spans.setdefault(k, (ts[0], ts[-1]))
        return spans

    def _merged_bottom_spans(self) -> dict[int, tuple[int, int, list]]:
        """Contiguous lyrics words that point (partly) to the same found
        words -> as one merged box on the bottom row (B222).

        Groups consecutive words as long as their target sets overlap
        (transitively). That covers both several lyrics words on one
        found word ("fort minable" -> "formidable") and the overlapping
        case ("Eh l'bébé" -> "Oh bébé,"). Key = every lyrics index in the
        group; value = (start, end, [target indices])."""
        spans: dict[int, tuple[int, int, list]] = {}
        n = len(self._words)
        li = 0
        while li < n:
            cur = {t for t in self._current_targets(li)
                   if 0 <= t < len(self._trans)}
            if cur:
                j = li
                union = set(cur)
                while j + 1 < n:
                    nxt = {t for t in self._current_targets(j + 1)
                           if 0 <= t < len(self._trans)}
                    if nxt and (nxt & union):
                        union |= nxt
                        j += 1
                    else:
                        break
                if j > li:
                    target_list = sorted(union)
                    for k in range(li, j + 1):
                        spans[k] = (li, j, target_list)
                    li = j + 1
                    continue
            li += 1
        return spans

    def _bot_link_point(self, li: int,
                        bot_spans: dict[int, tuple[int, int, int]]
                        ) -> tuple[int, int]:
        """Attachment point (x, y) of a coupling line on the (possibly
        merged) bottom box."""
        if li in bot_spans:
            a, b, _tj = bot_spans[li]
            ca, cb = self._bot_col[a], self._bot_col[b]
            x = _PATH + ca * _PPW
            w = (cb - ca + 1) * _PPW - 6
        else:
            x, _y, w = self._bot_rect(li)
        return x + w // 2, _BOT_Y

    def _top_link_point(self, i: int,
                        spans: dict[int, tuple[int, int]]) -> tuple[int, int]:
        """Attachment point (x, y) of a coupling line on the (possibly
        merged) top box."""
        if i in spans:
            a, b = spans[i]
            ca, cb = self._top_col[a], self._top_col[b]
            x = _PATH + ca * _PPW
            w = (cb - ca + 1) * _PPW - 6
        else:
            x, _y, w = self._top_rect(i)
        return x + w // 2, _TOP_Y + _BOX_H

    # -- drawing ----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt interface
        painter = QPainter(self)
        try:
            self._paint(painter)
        except Exception:  # noqa: BLE001 - drawing must never crash
            logger.exception(t("log_couple_paint_error"))
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        self._relayout()          # keep the columns up to date (B220)
        painter.fillRect(self.rect(), QColor(250, 250, 252))
        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawText(_PATH, _TOP_Y - 8, t("couple_found"))
        painter.drawText(_PATH, _BOT_Y - 8, t("couple_lyrics"))

        # Coupling lines. To keep the tangle readable (B157/B158) we show
        # the lines of the selected/pinned word solid and the rest very
        # faint. That way, after cutting/splitting, it stays possible to
        # follow what goes where.
        has_selection = self._sel_bot is not None or self._sel_top is not None
        spans = self._merged_spans()
        bot_spans = self._merged_bottom_spans()
        # First the 'background' (non-emphasised) lines, then the emphasis
        # on top of them.
        for stress in (False, True):
            for li, w in enumerate(self._words):
                # Bottom-row merge: only the head draws one line (B222).
                if li in bot_spans and li != bot_spans[li][0]:
                    continue
                for tj in self._current_targets(li):
                    if not (0 <= tj < len(self._trans)):
                        continue
                    # Top-row merge: only the head draws one line (B189).
                    if tj in spans and tj != spans[tj][0]:
                        continue
                    involved = (li == self._sel_bot or tj == self._sel_top)
                    # Without a selection everything is 'active' (in
                    # colour). With a selection only the lines involved
                    # are active; the rest dims.
                    active = involved or not has_selection
                    if active != stress:
                        continue
                    tcx, tcy = self._top_link_point(tj, spans)
                    bcx, bcy = self._bot_link_point(li, bot_spans)
                    if active:
                        # B167: always show the probability colour
                        # (blue = manually pinned); thicker when
                        # emphasised. For a merged bottom-row group the
                        # line is blue as soon as one member has been
                        # coupled manually (B222).
                        pinned = li in self._pinned
                        if li in bot_spans:
                            a, b, _d = bot_spans[li]
                            pinned = any(k in self._pinned
                                         for k in range(a, b + 1))
                        color = _sim_color(w["sim"], pinned)
                        pen = QPen(color, 3 if involved else 2)
                    else:
                        pen = QPen(QColor(205, 210, 216), 1)   # dimmed
                    painter.setPen(pen)
                    painter.drawLine(bcx, bcy, tcx, tcy)

        # Transcription words (top); the selected one gets a border (B153).
        # Doubly coupled, contiguous words are shown as one box (B189).
        for i, (text_value, _s, _e) in enumerate(self._trans):
            if i in spans:
                a, b = spans[i]
                if i != a:
                    continue                 # covered by the group's head
                ca, cb = self._top_col[a], self._top_col[b]
                x = _PATH + ca * _PPW
                rect = (x, _TOP_Y, (cb - ca + 1) * _PPW - 6)
                text_value = " ".join(self._trans[k][0] for k in range(a, b + 1))
                selected = any(k == self._sel_top for k in range(a, b + 1))
                self._draw_box(painter, rect, text_value, selected=selected,
                               fill=QColor(225, 228, 235),
                               dividers=[self._top_col[k] - ca
                                         for k in range(a + 1, b + 1)])
            elif i in self._filtered:
                # B309: filtered out by the hallucination check. Visible
                # and selectable, so that you can still couple it by hand
                # if the filter was wrong, but struck through so that it
                # is clear the automatic coupling leaves it alone.
                self._draw_box(painter, self._top_rect(i), text_value,
                               selected=(i == self._sel_top),
                               fill=_FILTERED_FILL, border=_FILTERED_BORDER,
                               dashed=True, struck=True)
            else:
                # B502: the same colour codes as the lyrics lane, so that
                # a found word which is coupled to nothing is visible
                # here too - and a whole run of them stands out.
                style = _STATUS_STYLE.get(self._found_style(i))
                self._draw_box(painter, self._top_rect(i), text_value,
                               selected=(i == self._sel_top),
                               fill=style[0] if style else QColor(225, 228,
                                                                  235),
                               border=style[1] if style else None)
        # Lyrics words (bottom); several -> one found word are merged into
        # one box (B222). The selected one gets a border.
        for i, w in enumerate(self._words):
            if i in bot_spans:
                a, b, _tj = bot_spans[i]
                if i != a:
                    continue                 # covered by the group's head
                ca, cb = self._bot_col[a], self._bot_col[b]
                x = _PATH + ca * _PPW
                rect = (x, _BOT_Y, (cb - ca + 1) * _PPW - 6)
                text_value = " ".join(self._words[k]["text"] for k in range(a, b + 1))
                selected = any(k == self._sel_bot for k in range(a, b + 1))
                self._draw_box(painter, rect, text_value, selected=selected,
                               fill=QColor(230, 240, 230),
                               dividers=[self._bot_col[k] - ca
                                         for k in range(a + 1, b + 1)])
            else:
                fill = QColor(230, 240, 230)
                border = None
                dashed = False
                text_value = w["text"]
                status_style = _STATUS_STYLE.get(w.get("status", "coupled"))
                if status_style is not None:
                    fill, border, _legend_key = status_style   # B317: no prefix
                    dashed = True
                self._draw_box(painter, self._bot_rect(i), text_value,
                               selected=(i == self._sel_bot),
                               fill=fill, border=border, dashed=dashed)
        self._draw_line_markers(painter)

    def _draw_line_markers(self, painter: QPainter) -> None:
        """Mark where a new lyrics line starts (B339).

        Every word already carries its line number in the view data, but
        it was never drawn - and without it a repeating outro reads as a
        wall of the same words, "a long-player with a scratch" in the
        words of the user. A thin rule plus the line number at every
        change is enough to find your place again.
        """
        y_top = _BOT_Y - 4
        y_bottom = _BOT_Y + _BOX_H + 16
        previous = None
        for i, w in enumerate(self._words):
            number = int(w.get("line", 0))
            if number == previous:
                continue
            previous = number
            col = self._bot_col[i] if i < len(self._bot_col) else i
            if col < 0:
                continue
            x = _PATH + col * _PPW - 4
            painter.setPen(QPen(_LINE_MARKER, 1))
            painter.drawLine(x, y_top, x, y_bottom)
            painter.setPen(QPen(_LINE_MARKER_TEXT))
            painter.drawText(x + 3, y_bottom - 2, str(number + 1))

    def line_marker_columns(self) -> list[tuple[int, int]]:
        """(line number, column) of every line start (B339, for the test)."""
        marks: list[tuple[int, int]] = []
        previous = None
        for i, w in enumerate(self._words):
            number = int(w.get("line", 0))
            if number == previous:
                continue
            previous = number
            col = self._bot_col[i] if i < len(self._bot_col) else i
            if col >= 0:
                marks.append((number, col))
        return marks

    def _draw_box(self, painter, rect, text, selected, fill,
                 border: QColor | None = None, dashed: bool = False,
                 struck: bool = False,
                 dividers: Sequence[int] = ()) -> None:
        """Draw one word box.

        ``dividers`` holds the column offsets within a merged group where
        a thin separating line goes (B321). Contiguous words that belong
        to the same coupling are shown as one wide box; without those
        lines you cannot see where one word ends and the next begins, and
        then you cannot aim at them either - while since B321 a click
        does land on the individual word.
        """
        x, y, w = rect
        painter.fillRect(x, y, w, _BOX_H, fill)
        for offset in dividers:
            boundary = x + offset * _PPW - 3
            if x < boundary < x + w:
                painter.setPen(QPen(QColor(150, 150, 150), 1, Qt.DotLine))
                painter.drawLine(boundary, y + 3,
                                 boundary, y + _BOX_H - 3)
        # The selection (blue, thick, solid) always takes precedence over
        # the status border (B287): that way it stays clear at a glance
        # what is selected, even on a word with a status marking.
        if selected:
            border_color, border_thickness = QColor(30, 90, 200), 2
        elif border is not None:
            border_color, border_thickness = border, 2
        else:
            border_color, border_thickness = QColor(90, 90, 90), 1
        painter.setPen(QPen(border_color, border_thickness,
                            Qt.DashLine if (dashed and not selected)
                            else Qt.SolidLine))
        painter.drawRect(x, y, w, _BOX_H)
        painter.setPen(QPen(QColor(120, 120, 120) if struck
                            else QColor(30, 30, 30)))
        shown = str(text)[:max(1, int((w - 8) / 7))]
        painter.drawText(x + 4, y + 18, shown)
        if struck:
            width = painter.fontMetrics().horizontalAdvance(shown)
            painter.drawLine(x + 4, y + 14, x + 4 + width, y + 14)

    def _toggle_coupling(self, li: int, tj: int) -> None:
        """(Un)couple lyrics word ``li`` to found word ``tj``."""
        targets = self._targets.setdefault(li, [])
        if tj in targets:
            targets.remove(tj)
        else:
            targets.append(tj)
        self._pinned.add(li)
        self._emit()

    # -- interaction ------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt interface
        pos = event.position().toPoint() if hasattr(event, "position") \
            else event.pos()
        # A box click takes precedence over a line click: a click on a word
        # box selects or (un)couples, and so does not remove a line by
        # accident (B121).
        bot = self._hit_row(pos, top=False)
        if bot is not None:
            if self._sel_top is not None:
                # Couple from top (found) to bottom (lyrics) (B190).
                self._toggle_coupling(bot, self._sel_top)
                self._sel_bot = None
                self._sel_top = None
            else:
                # A second click on the same word clears the selection
                # (B154).
                self._sel_bot = None if self._sel_bot == bot else bot
            self.update()
            return
        top = self._hit_row(pos, top=True)
        if top is not None:
            if self._sel_bot is not None:
                # Couple from bottom (lyrics) to top (found).
                self._toggle_coupling(self._sel_bot, top)
                # Clear the selection after a coupling (B155).
                self._sel_bot = None
                self._sel_top = None
            else:
                # No lyrics word active: (de)select the top word for
                # cutting/merging (B153/B154).
                self._sel_top = None if self._sel_top == top else top
            self.update()
            return
        # B513: inside a drawn box but on no word - a merged box may
        # cover a column that belongs to nobody, and the coupling line
        # is hung on the optical middle of that box. A click there fell
        # through to the line and REMOVED the coupling of the whole
        # group, while the user was clicking in the middle of a word
        # box. Doing nothing is the only right answer there.
        if self._in_a_box(pos):
            return
        # Outside the boxes: a click on a coupling line removes that link.
        hit = self._hit_link(pos)
        if hit is not None:
            li, tj = hit
            spans = self._merged_spans()
            # Undo a merged (double) coupling as a whole, so that the boxes
            # split again (B189).
            bot_spans = self._merged_bottom_spans()
            if li in bot_spans:
                # Bottom-row merge: detach the whole group (B222).
                a, b, target_list = bot_spans[li]
                target_set = set(target_list)
                for k in range(a, b + 1):
                    self._targets[k] = [t for t in self._targets.get(k, [])
                                        if t not in target_set]
                    self._pinned.add(k)
                self._emit()
            elif tj in spans:
                a, b = spans[tj]
                self._targets[li] = [t for t in self._targets.get(li, [])
                                     if not (a <= t <= b)]
                self._pinned.add(li)
                self._emit()
            elif tj in self._targets.get(li, []):
                self._targets[li].remove(tj)
                self._pinned.add(li)
                self._emit()
        self.update()

    def _in_a_box(self, pos: QPoint) -> bool:
        """Is this click inside a drawn word box? (B513)"""
        for y0, spans, rect in ((_TOP_Y, self._merged_spans(),
                                 self._top_rect),
                                (_BOT_Y, self._merged_bottom_spans(),
                                 self._bot_rect)):
            if not (y0 <= pos.y() <= y0 + _BOX_H):
                continue
            for key, value in spans.items():
                first, last = value[0], value[1]
                x1 = rect(first)[0]
                x2 = rect(last)[0] + rect(last)[2]
                if x1 <= pos.x() <= x2:
                    return True
        return False

    def _hit_row(self, pos: QPoint, top: bool) -> int | None:
        y0 = _TOP_Y if top else _BOT_Y
        if not (y0 <= pos.y() <= y0 + _BOX_H):
            return None
        col = int((pos.x() - _PATH) // _PPW)
        if col < 0:
            return None
        # Column -> word index (B220: columns != word order).
        cols = self._top_col if top else self._bot_col
        idx = next((k for k, c in enumerate(cols) if c == col), None)
        if idx is None:
            return None
        # B321: the word you point at, not the head of its group. The
        # grouping (B189/B222) is a DRAWING choice - contiguous words that
        # belong to the same coupling are shown as one wide box - and it
        # used to determine what you could address as well: every click
        # inside such a box returned the first word of the group. Since a
        # coupling is automatically extended to adjacent found words
        # (B191, up to three), that box regularly lies over the column of
        # its right-hand neighbour, and then a coupling landed on the word
        # to the LEFT of the one you clicked. Measured: clicking "dable"
        # in the group "formi|dable" returned "formi".
        return idx

    def _hit_link(self, pos: QPoint) -> tuple[int, int] | None:
        """(lyrics index, transcript index) of the line close to ``pos``."""
        spans = self._merged_spans()
        bot_spans = self._merged_bottom_spans()
        for li in range(len(self._words)):
            if li in bot_spans and li != bot_spans[li][0]:
                continue                     # bottom-row group: head only
            for tj in self._current_targets(li):
                if not (0 <= tj < len(self._trans)):
                    continue
                if tj in spans and tj != spans[tj][0]:
                    continue                 # top-row group: head line only
                tcx, tcy = self._top_link_point(tj, spans)
                bcx, bcy = self._bot_link_point(li, bot_spans)
                if self._point_near_segment(pos.x(), pos.y(),
                                            bcx, bcy, tcx, tcy):
                    return li, tj
        return None

    @staticmethod
    def _point_near_segment(px, py, x1, y1, x2, y2, tol=6.0) -> bool:
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        if length2 == 0:
            return (px - x1) ** 2 + (py - y1) ** 2 <= tol * tol
        u = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length2))
        cx, cy = x1 + u * dx, y1 + u * dy
        return (px - cx) ** 2 + (py - cy) ** 2 <= tol * tol

    def _emit(self) -> None:
        # B502: coupling or uncoupling by hand changes what the colour
        # code of a found word should say, so refresh it here - this is
        # the one place every change passes through.
        self._refresh_found_status()
        # Keep only manually touched words (not the automatic couplings).
        self._on_change({li: list(self._targets.get(li, []))
                         for li in self._pinned})

    # -- Cutting / merging of found words (B153) -------------------------
    def _remap(self, mapping: dict[int, list[int]]) -> None:
        """Reindex the couplings after a cut/merge operation."""
        from . import song_text
        self._targets = song_text.remap_pins(self._targets, mapping)
        # B528: ``_filtered`` and ``_in_lyrics`` are transcript indexes
        # too, and they stayed behind. Everything after the cut then
        # pointed one place too far left: the wrong word was drawn
        # struck through and the run rule of B520/B521 judged the wrong
        # words. Same mapping, same moment.
        self._filtered = self._remap_indices(self._filtered, mapping)
        self._in_lyrics = self._remap_indices(self._in_lyrics, mapping)
        # B519: the found words moved, so the text and the similarity
        # shown next to every lyrics word are about the old list. Same
        # repair as on the lyrics side: recompute instead of leaving a
        # stale answer standing.
        self._words = [self._word_entry(w["index"], w["text"],
                                        int(w.get("line", 0)))
                       for w in self._words]
        if self._on_transcript is not None:
            self._on_transcript(list(self._trans))
        self._emit()
        self._sel_top = None
        self.update()

    @staticmethod
    def _remap_indices(indices, mapping: dict[int, list[int]]) -> set:
        """Move a set of transcript indexes along with a cut/merge (B528)."""
        moved: set[int] = set()
        for index in indices:
            moved.update(mapping.get(index, [index]))
        return moved

    def cut_selected(self) -> bool:
        """Cut the selected word in two (found word or lyrics word).

        Top (found word) = B153; bottom (lyrics word) = B156.
        """
        from . import song_text
        if self._sel_top is not None:
            self._trans, mapping = song_text.cut_word(self._trans,
                                                      self._sel_top)
            self._remap(mapping)
            return True
        if self._sel_bot is not None:
            lyrics = self._lyrics_list()
            new, mapping = song_text.cut_lyric(lyrics, self._sel_bot)
            self._remap_lyrics(new, mapping)
            return True
        return False

    def merge_selected(self) -> bool:
        """Merge the selected word with its right-hand neighbour word.

        Top (found word) = B153; bottom (lyrics word) = B156.
        """
        from . import song_text
        if self._sel_top is not None and self._sel_top < len(self._trans) - 1:
            self._trans, mapping = song_text.merge_words(self._trans,
                                                         self._sel_top)
            self._remap(mapping)
            return True
        if self._sel_bot is not None and self._sel_bot < len(self._words) - 1:
            lyrics = self._lyrics_list()
            new, mapping = song_text.merge_lyrics(lyrics, self._sel_bot)
            self._remap_lyrics(new, mapping)
            return True
        return False

    def release_selected(self) -> bool:
        """Give the selected lyrics word back to the automatic coupling
        (B506).

        The third state next to coupling and uncoupling, and the one
        that was missing: a pin - also an empty one - always beats the
        automatic coupling, so a word you once uncoupled could never be
        given back to it. At "Lied R" that was fifty-four words, and the
        automatic coupling could not repair a single one of them however
        obvious the match was.
        """
        if self._sel_bot is None:
            return False
        if self._sel_bot not in self._pinned:
            return False
        self._pinned.discard(self._sel_bot)
        # The targets stay as they are drawn; what goes is the DECISION,
        # so the next time round the automatic coupling has this word
        # back. Its marking goes with it - it no longer says anything.
        word = self._words[self._sel_bot]
        if word.get("status") == "manually_uncoupled":
            word["status"] = ""
        self._emit()
        self.update()
        return True

    def _lyrics_list(self) -> list[tuple[str, int]]:
        return [(w["text"], int(w.get("line", 0))) for w in self._words]

    def selected_found_text(self) -> str:
        """The text of the selected FOUND word, or empty (B337)."""
        if self._sel_top is None or self._sel_top >= len(self._trans):
            return ""
        return str(self._trans[self._sel_top][0])

    def selected_lyric_text(self) -> str:
        """The text of the selected LYRICS word, or empty (B337)."""
        if self._sel_bot is None or self._sel_bot >= len(self._words):
            return ""
        return str(self._words[self._sel_bot].get("text") or "")

    def _found_style(self, index: int) -> str:
        """The colour code of a found word.

        v1.0.12: a word that was heard again or laid by the aligner shows
        where it came from as long as nothing is wrong with it - coupled,
        or no status at all. A problem status (no match, filtered,
        suspected) still wins: that is what the user has to act on.
        """
        status = self._found_status.get(index, "")
        if status in ("", "coupled"):
            return self._origin_at(index) or status
        return status

    def _origin_at(self, index: int) -> str:
        """``heard_again``/``aligned`` for a found word, or ""."""
        if not 0 <= index < len(self._trans):
            return ""
        return self._origins.get(round(float(self._trans[index][1]), 3), "")

    def _refresh_found_status(self, index: int | None = None) -> None:
        """The colour codes of the found lane after a change (B502/B520).

        Take a word out of the filter, or couple it by hand, and it must
        not keep standing there as filtered or as a suspected
        hallucination.

        B520: through the SAME function the pipeline uses, so an edit
        cannot make this lane cruder than it was. The old version knew
        only three states, so after one click a run marked as suspect
        (orange) silently became plain "no match" (red) - two different
        things in one colour. ``index`` is ignored; the whole lane is
        recomputed, which for a few hundred words costs nothing.
        """
        from . import pipeline

        used = {i for target in self._targets.values() for i in target}
        self._found_status = pipeline.found_word_status(
            len(self._trans), used, self._filtered, self._in_lyrics)

    def mark_selected(self, status: str) -> None:
        """Give the selected word the marking that goes with ``status``.

        A found word gets the styling of a filtered word (struck
        through), a lyrics word its status colour - both already exist,
        so the legend keeps saying exactly what you see.
        """
        if status == "hallucination_filtered" and self._sel_top is not None:
            if self._sel_top in self._filtered:
                self._filtered.discard(self._sel_top)
            else:
                self._filtered.add(self._sel_top)
            self._refresh_found_status(self._sel_top)          # B502
        elif status == "filler_skipped" and self._sel_bot is not None:
            word = self._words[self._sel_bot]
            index = int(word["index"])
            # B528: remember it, do not only write it into the view. A
            # cut or a merge rebuilds every entry from the couplings,
            # and a marking that lives nowhere else was silently gone.
            if word.get("status") == status:
                word["status"] = ""
                self._marked.discard(index)
            else:
                word["status"] = status
                self._marked.add(index)
        self.update()

    def _remap_lyrics(self, new: list[tuple[str, int]],
                      mapping: dict[int, list[int]]) -> None:
        """Rebuild the lyrics words and remap the coupling keys (B156)."""
        from . import song_text
        self._targets = song_text.remap_pin_keys(self._targets, mapping)
        self._pinned = {mapping.get(li, [li])[0] for li in self._pinned}
        # B528: a hand-set marking is keyed on the lyrics index, so it
        # has to travel with the same mapping as the couplings.
        self._marked = self._remap_indices(self._marked, mapping)
        self._words = [
            self._word_entry(i, text_value, line_number)
            for i, (text_value, line_number) in enumerate(new)]
        if self._on_lyrics is not None:
            self._on_lyrics(list(new))
        self._emit()
        self._sel_bot = None
        self.update()

    def _word_entry(self, index: int, text_value: str,
                    line_number: int) -> dict:
        """One lyrics word for the view, WITH what is known about it
        (B519).

        Up to v0.147.0 this set ``sim`` to 0.0, ``found`` to None and
        left out ``status`` altogether. The couplings themselves
        survived a cut or a merge - measured, 362 of 363 - but
        everything you SEE of them was wiped: the line colour comes from
        ``sim`` and 0.0 is red, so one merge turned 346 green lines into
        362 red ones, the found word disappeared from the box and every
        marking was gone. Nothing was broken; you just could no longer
        tell what was right.

        So it is recomputed here from the couplings as they stand at
        this moment - the same phonetic comparison the view itself uses.
        """
        from . import song_text
        from .cluster import phonetic_key, similarity

        targets = [t for t in self._targets.get(index, [])
                   if 0 <= t < len(self._trans)]
        found = " ".join(str(self._trans[t][0]) for t in targets)
        sim = (float(similarity(phonetic_key(text_value),
                                phonetic_key(found))) if found else 0.0)
        entry = {"index": index, "text": text_value, "line": line_number,
                 "transcript_indices": self._targets.get(index, []),
                 "found": found or None, "sim": round(sim, 3),
                 "pinned": index in self._pinned}
        # The same order of precedence as ``word_coupling_view``, minus
        # the parts that need the whole pipeline (a hole in the
        # transcription, a filtered segment). Those cannot be recomputed
        # here, and guessing at them would be worse than leaving them
        # out.
        if index in self._marked and not targets:
            entry["status"] = "filler_skipped"     # B528: by hand
        elif targets:
            entry["status"] = "coupled"
        elif index in self._pinned:
            entry["status"] = "manually_uncoupled"
        elif song_text.is_filler_word(text_value):
            entry["status"] = "filler_skipped"
        else:
            entry["status"] = "no_match"
        return entry


class CouplingEditorDialog(QDialog):
    """Dialog around :class:`CouplingCanvas` with save/close (B121)."""

    def __init__(self, transcript: list, words: list,
                 on_save: Callable[[dict], None],
                 on_save_transcript: Callable[[list], None] | None = None,
                 on_save_lyrics: Callable[[list], None] | None = None,
                 parent=None, filtered: Sequence[int] = (),
                 on_mark: Callable[[str, str], bool] | None = None,
                 found_status: dict | None = None,
                 in_lyrics: Sequence[int] = (),
                 origins: Sequence = (),
                 can_listen_again: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("couple_title"))
        #: v1.0.12: set when the user asks to listen again. The dialog
        #: then saves and closes, so the long run happens with nothing
        #: half-edited open, and the caller opens it again afterwards.
        self.listen_again_requested = False
        self.resize(1000, 320)
        self._on_save = on_save
        self._on_save_transcript = on_save_transcript
        self._on_save_lyrics = on_save_lyrics
        self._on_mark = on_mark
        self._pins: dict[int, list[int]] = {}
        self._transcript: list | None = None      # B153: edited transcription
        self._lyrics: list | None = None           # B156: edited lyrics

        layout = QVBoxLayout(self)
        hint = QLabel(t("couple_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)
        # B287/B308/B309: what the markings mean. Without a legend the
        # user has to guess what "[hal]" or a struck-through word means.
        legend = QLabel(f'{t("couple_legend")} '
                        f'{legend_html(clickable=on_mark is not None)}')
        legend.setTextFormat(Qt.RichText)
        legend.setWordWrap(True)
        legend.setStyleSheet("color: #666;")
        if on_mark is not None:
            legend.setToolTip(t("legend_mark_tip"))
            legend.linkActivated.connect(self._mark_selected)
        layout.addWidget(legend)

        self._canvas = CouplingCanvas(transcript, words, self._changed,
                                    on_transcript=self._transcript_changed,
                                    on_lyrics=self._lyrics_changed,
                                    filtered=filtered,
                                    found_status=found_status,
                                    in_lyrics=in_lyrics,      # B521
                                    origins=origins)          # v1.0.12
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setWidget(self._canvas)
        layout.addWidget(scroll, stretch=1)

        row = QHBoxLayout()
        # Cutting/merging on the found words (B153).
        cut = QPushButton(t("couple_cut"))
        cut.setToolTip(t("couple_cut_tip"))
        cut.clicked.connect(self._canvas.cut_selected)
        merge = QPushButton(t("couple_merge"))
        merge.setToolTip(t("couple_merge_tip"))
        merge.clicked.connect(self._canvas.merge_selected)
        release = QPushButton(t("couple_release"))          # B506
        release.setToolTip(t("couple_release_tip"))
        release.clicked.connect(self._release_selected)
        row.addWidget(cut)
        row.addWidget(merge)
        row.addWidget(release)
        if can_listen_again:
            again = QPushButton(t("couple_listen_again"))
            again.setToolTip(t("couple_listen_again_tip"))
            again.clicked.connect(self._ask_listen_again)
            row.addWidget(again)
        row.addStretch()
        save = QPushButton(t("couple_save"))
        save.clicked.connect(self.accept)
        close = QPushButton(t("close"))
        close.clicked.connect(self.reject)
        row.addWidget(save)
        row.addWidget(close)
        layout.addLayout(row)

    def _changed(self, pins: dict) -> None:
        self._pins = pins

    def _ask_listen_again(self) -> None:
        self.listen_again_requested = True
        self.accept()

    def _mark_selected(self, status: str) -> None:
        """Mark the selected word as hallucination or filler (B337).

        The word lands in the list of the audio language, so every
        following project in that language benefits. Clicking again
        removes it. Which row counts follows from the marking:
        hallucination is about what Whisper found, a filler word about
        the lyrics.
        """
        if self._on_mark is None or status not in MARKABLE:
            return
        kind = MARKABLE[status]
        word = (self._canvas.selected_found_text()
                if kind == "hallucinations"
                else self._canvas.selected_lyric_text())
        if not word:
            QMessageBox.information(self, t("couple_title"),
                                    t("mark_select_first"))
            return
        if self._on_mark(kind, word):
            self._canvas.mark_selected(status)

    def _release_selected(self) -> None:
        """Give the selected lyrics word back to the automatic coupling
        (B506)."""
        if not self._canvas.release_selected():
            QMessageBox.information(self, t("couple_title"),
                                    t("couple_release_first"))

    def _transcript_changed(self, transcript: list) -> None:
        self._transcript = transcript

    def _lyrics_changed(self, lyrics: list) -> None:
        self._lyrics = lyrics

    def done(self, result: int) -> None:  # noqa: N802 - Qt interface
        # Apply the coupling both on accept (save) and on close (B121:
        # the logic also runs when closing).
        try:
            if self._transcript is not None and \
                    self._on_save_transcript is not None:
                self._on_save_transcript(self._transcript)   # B153
            if self._lyrics is not None and \
                    self._on_save_lyrics is not None:
                self._on_save_lyrics(self._lyrics)           # B156
            self._on_save(self._pins)
        except Exception:  # noqa: BLE001 - saving must not crash
            logger.exception(t("log_couple_save_failed"))
        super().done(result)


class ListenAgainDialog(QDialog):
    """The candidates of "Listen again", one row per place (v1.0.12).

    Per place the best candidate is chosen and ticked; the user unticks
    what he does not want, or picks another candidate. What he does not
    take stays as it is and comes up again the next time.
    """

    def __init__(self, areas: list[dict], has_earlier: bool = False,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("listen_again_title"))
        self.resize(900, 420)
        self._areas = areas
        #: Set when the user asks to clear what was taken over before.
        self.clear_requested = False
        self._rows: list[tuple[QCheckBox, QComboBox]] = []

        layout = QVBoxLayout(self)
        # Nothing new to hear, but something taken over earlier: the
        # dialog still opens, so that can be cleared.
        intro = QLabel(t("listen_again_intro") if areas
                       else t("listen_again_nothing"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        for column, key in enumerate(("listen_again_col_take",
                                      "listen_again_col_where",
                                      "listen_again_col_expected",
                                      "listen_again_col_candidate")):
            header = QLabel(f"<b>{t(key)}</b>")
            header.setTextFormat(Qt.RichText)
            grid.addWidget(header, 0, column)
        for row, area in enumerate(areas, start=1):
            take = QCheckBox()
            choice = QComboBox()
            for candidate in area.get("candidates", ()):
                text = " ".join(str(w[0]) for w in candidate["words"])
                choice.addItem(t("listen_again_candidate").format(
                    kind=t(f"listen_again_kind_{candidate['kind']}"),
                    score=float(candidate["score"]), text=text[:80]))
                # Why it scored what it scored, on hovering over it.
                parts = candidate.get("evidence") or {}
                if parts:
                    choice.setItemData(
                        choice.count() - 1,
                        t("listen_again_evidence").format(
                            evidence=float(parts.get("evidence", 0.0)),
                            singing=float(parts.get("singing", 0.0)),
                            rhythm=float(parts.get("rhythm", 0.0)),
                            echo=(t("listen_again_echo")
                                  if parts.get("echo") else "")),
                        Qt.ToolTipRole)
            if choice.count() == 0:
                choice.addItem(t("listen_again_none"))
                take.setEnabled(False)
            else:
                take.setChecked(True)
            where = QLabel(t("listen_again_where").format(
                low=float(area["low"]), high=float(area["high"])))
            expected = QLabel(" ".join(area.get("expected", ()))[:90])
            expected.setWordWrap(True)
            grid.addWidget(take, row, 0)
            grid.addWidget(where, row, 1)
            grid.addWidget(expected, row, 2)
            grid.addWidget(choice, row, 3)
            self._rows.append((take, choice))
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_host)
        layout.addWidget(scroll, stretch=1)

        buttons = QHBoxLayout()
        if has_earlier:
            clear = QPushButton(t("listen_again_clear"))
            clear.clicked.connect(self._clear)
            buttons.addWidget(clear)
        buttons.addStretch()
        if areas:
            apply = QPushButton(t("listen_again_apply"))
            apply.clicked.connect(self.accept)
            buttons.addWidget(apply)
        cancel = QPushButton(t("close"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _clear(self) -> None:
        self.clear_requested = True
        self.accept()

    def chosen(self) -> list[dict]:
        """The areas the user takes over, each with its chosen words."""
        out = []
        for area, (take, choice) in zip(self._areas, self._rows):
            candidates = area.get("candidates") or []
            if not take.isChecked() or not candidates:
                continue
            candidate = candidates[max(0, choice.currentIndex())]
            out.append({"low": area["low"], "high": area["high"],
                        "kind": candidate["kind"],
                        "words": candidate["words"],
                        "replaced": area.get("replaced", [])})
        return out
