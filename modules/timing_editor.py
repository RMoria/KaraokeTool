"""Graphical timing editor: waveforms, playback and draggable lines.

Stacked on top of each other: the waveform of the ORIGINAL (placed on
the karaoke timeline via the alignment offset), the waveform of the
karaoke, a time bar and the text lines as blocks. A red playhead runs
across all lanes and moves along with the zoom. Clicking in a waveform
puts the playhead there and starts playback (original or karaoke,
selectable in the toolbar). Dragging the middle of a block shifts a
line; dragging an edge stretches or shrinks it; the start of the line
snaps to the playhead when it is close by. Saving writes
``timing.json``.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from . import waveform
from .translations import t
from .timing import (Syllable, TimedLine, mark_held, snap_time,
                     spread_flattened)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    _MULTIMEDIA = True
except ImportError:  # pragma: no cover
    _MULTIMEDIA = False

logger = logging.getLogger(__name__)

_EDGE_PX = 7
_MIN_LINE_S = 0.2
_WAVE_HEIGHT = 105
_ORIG_LANE_TOP = _WAVE_HEIGHT + 2      # lane with original sentences (2 rows)
_ORIG_ROW_H = 30
_ORIG_LANE_H = 2 * _ORIG_ROW_H
_KARAOKE_WAVE_TOP = _ORIG_LANE_TOP + _ORIG_LANE_H + 4
_VOCAL_HEIGHT = 80                     # vocal stem lane (B196), a bit lower
_AXIS_TOP = _KARAOKE_WAVE_TOP + _WAVE_HEIGHT + 8
_LANES_TOP = _AXIS_TOP + 36
# Vocal stem lane below the karaoke lines (B223) instead of above the
# time bar.
_VOCAL_WAVE_TOP = _LANES_TOP + 3 * 34 + 8
_CANVAS_HEIGHT = _VOCAL_WAVE_TOP + _VOCAL_HEIGHT + 10
#: Fixed (non-scrolling) labels at the top left per lane (B196/B223).
#: The names are the ``lane_*`` translation keys without their prefix
#: (B327: three of them were left behind in Dutch at the B299 rename and
#: therefore ended up on screen as a raw key).
_LANE_LABELS = (
    ("original", 2),
    ("original_text", _ORIG_LANE_TOP),
    ("karaoke", _KARAOKE_WAVE_TOP),
    ("karaoke_lines", _LANES_TOP),
    ("vocals", _VOCAL_WAVE_TOP),
)
_ORIG_BLOCK = QColor(140, 120, 90, 140)
# Mirrored standalone crowd line in the original lane (B193/B257): not
# real original text, so its own (red) colour instead of the normal
# beige, so that it is not mistaken for original text.
_ORIG_CROWD = QColor(200, 90, 85, 140)
#: B499: an original sentence that is fetched back from the original
#: recording, and the border colour that goes with it. Dotted means:
#: the piece was moved in 1.4 and no longer lies on this sentence.
_ORIG_RESTORE = QColor(60, 120, 210, 130)
_RESTORE_BORDER = QColor(30, 70, 150)
_GREEN = QColor(60, 176, 67, 150)
_RED = QColor(229, 57, 53, 150)
#: B507: an inline [bg] piece as a block of its own, on its own time.
#: Lighter than the sentence it belongs to and with a dotted border, so
#: that it is visibly not a sentence - it may lie over its neighbours
#: and it never reaches the render.
_BG_BLOCK = QColor(60, 176, 67, 60)
_BG_BORDER = QColor(70, 130, 75)
#: B508: a sentence that lies over its neighbour, is empty or stands out
#: of order. The pipeline has checked this since B500, but only while
#: generating - and the editor is precisely where such a thing is made.
_PROBLEM_BORDER = QColor(220, 120, 20)
_PLAYHEAD = QColor(200, 30, 30)
_MARKER = QColor(120, 120, 120)


class TimingCanvas(QWidget):
    """Draws waveforms, time bar, playhead and line blocks."""

    def __init__(self, karaoke_peaks: np.ndarray,
                 original_peaks: np.ndarray | None, duration: float,
                 lines: list[dict],
                 on_seek: Callable[[float], None],
                 originals: list[dict] | None = None,
                 original_duration: float = 0.0,
                 project: Callable[[float], float] | None = None,
                 vocal_peaks: np.ndarray | None = None,
                 moved_restores: Sequence[int] = ()) -> None:
        """``originals``: original sentences as ``{"text", "start",
        "end", "rows": [line indices]}``; shifting/stretching these moves
        the coupled karaoke lines along. ``vocal_peaks``: waveform of the
        vocal stem of the original (B196), on the original timeline."""
        super().__init__()
        self._karaoke_peaks = karaoke_peaks
        self._original_peaks = original_peaks
        self._vocal_peaks = vocal_peaks
        # B499: line numbers whose piece of original was moved in 1.4.
        self._moved_restores = {int(number) for number in moved_restores}
        #: B499: what the user asked to put back, handed on when saving.
        self._reset_moves: set[int] = set()
        self._original_duration = max(original_duration, 0.001)
        self._project = project or (lambda t: t)
        self._duration = max(duration, 1.0)
        self._lines = lines
        self._originals = originals or []
        self._on_seek = on_seek
        self._pps = 60.0
        self._view_mode = "sentences"        # B127: blocks/sentences/words
        self._cells: list[dict] = []      # last drawn cells (B162)
        self._orig_cells: list[dict] = []  # last drawn original cells
        self._sel_cell: int | None = None  # selected karaoke cell (B180)
        self._sel_orig: int | None = None  # selected original cell (B198)
        self._playhead: float | None = None
        self._marker: float | None = None
        self._drag: tuple[str, int, str, float] | None = None
        self._col_cache = None            # cached karaoke columns
        self._col_cache_key = None        # (id(peaks), width) of the cache
        # coupling karaoke line -> original index (for both directions)
        self._line_to_orig: dict[int, int] = {}
        for oi, original in enumerate(self._originals):
            for row in original.get("rows", ()):
                self._line_to_orig[row] = oi
        #: B508: line numbers with a problem between the sentences.
        self._problem_rows: set[int] = set()
        self._recheck()
        self.setMouseTracking(True)
        self.setFixedSize(int(self._duration * self._pps), _CANVAS_HEIGHT)

    @property
    def pixels_per_second(self) -> float:
        return self._pps

    @property
    def playhead(self) -> float | None:
        return self._playhead

    @property
    def marker(self) -> float | None:
        return self._marker

    def set_zoom(self, pixels_per_second: float) -> None:
        self._pps = float(np.clip(pixels_per_second, 8.0, 600.0))
        self.setFixedWidth(int(self._duration * self._pps))
        self.update()

    def set_playhead(self, moment: float | None) -> None:
        self._playhead = moment
        self.update()

    def set_originals(self, originals: list[dict]) -> None:
        """Replace the original sentences (after a reset) and redraw."""
        self._originals = originals
        self._line_to_orig = {}
        for oi, original in enumerate(self._originals):
            for row in original.get("rows", ()):
                self._line_to_orig[row] = oi
        self.update()

    def set_lines(self, lines: list[dict]) -> None:
        """Replace the karaoke lines (after a reset) and redraw (B100)."""
        self._lines = lines
        self._drag = None
        self._recheck()
        self.update()

    def _recheck(self) -> None:
        """Which sentences have a problem between them (B508)?

        The same check the pipeline runs at the end of the automatic
        timing (B500), but here - because this is where an overlap is
        made by hand, and pointing at it three steps later is pointing
        at it too late. Cheap enough to run after every drag: it walks
        the lines once and touches no audio.
        """
        from . import timing_checks

        try:
            lines = [_from_dict(line) for line in self._lines]
            found = timing_checks.line_checks(lines)
        except Exception:  # noqa: BLE001 - a check never breaks the editor
            logger.exception(t("log_timing_paint_error"))
            self._problem_rows = set()
            return
        by_index = {line.index: pos for pos, line in enumerate(lines)}
        numbers: set[int] = set(found.get("empty_lines") or ())
        for entry in (found.get("overlapping_lines") or ()):
            numbers.update(entry[:2])
        for entry in (found.get("lines_out_of_order") or ()):
            numbers.update(entry[:2])
        self._problem_rows = {by_index[number] for number in numbers
                              if number in by_index}

    def set_view_mode(self, mode: str) -> None:
        """Switch the lane view: blocks, sentences or words (B127).

        Dragging/stretching stays at sentence level; the other views are
        only there for orientation (reading).
        """
        from . import timing as timing_module
        if mode in timing_module.VIEW_MODES:
            self._view_mode = mode
            self._drag = None
            self.update()

    def toggle_selected_restore(self) -> bool:
        """Mark/unmark the selected sentence as "back from the original"
        (B496).

        Works on the karaoke cell or on the cell in the original lane -
        the two are the same sentence, so it does not matter which one is
        selected. What is marked here is handed to step 1.4, which does
        the actual fetching back.
        """
        if self._sel_cell is not None and self._sel_cell < len(self._cells):
            rows = self._cells[self._sel_cell].get("rows", [])
        elif self._sel_orig is not None \
                and self._sel_orig < len(self._orig_cells):
            rows = self._orig_cells[self._sel_orig].get("rows", [])
        else:
            return False
        own = [r for r in rows if 0 <= r < len(self._lines)]
        if not own:
            return False
        # B499: is the piece of this sentence moved in 1.4, then one more
        # click does not switch the marking off but puts the piece back
        # on the sentence - that is what the dotted border is asking for.
        # Switching off then takes one more click, and that is the right
        # order: undoing a move is the smaller step.
        moved = [int(self._lines[r]["index"]) for r in own
                 if int(self._lines[r]["index"]) in self._moved_restores]
        if moved:
            for number in moved:
                self._moved_restores.discard(number)
                self._reset_moves.add(number)
            self.update()
            return True
        new = not all(self._lines[r].get("restore") for r in own)
        for r in own:
            self._lines[r]["restore"] = new
        self.update()
        return True

    def reset_moves(self) -> list[int]:
        """Sentences whose piece has to go back onto the sentence (B499)."""
        return sorted(self._reset_moves)

    def restore_rows(self) -> list[int]:
        """The line numbers marked as "back from the original" (B496)."""
        return [int(line["index"]) for line in self._lines
                if line.get("restore")]

    def toggle_selected_disabled(self) -> bool:
        """Disable/enable the selected cell (and its lines) (B180/B198).

        Works on the selected karaoke cell or, if there is none, on the
        selected cell in the original lane (B198): the grey then applies
        to both lanes, because it is the same line."""
        if self._sel_cell is not None and self._sel_cell < len(self._cells):
            rows = self._cells[self._sel_cell].get("rows", [])
        elif self._sel_orig is not None \
                and self._sel_orig < len(self._orig_cells):
            rows = self._orig_cells[self._sel_orig].get("rows", [])
        else:
            return False
        if not rows:
            return False
        # New status = inverse of the current one (all lines involved
        # get the same value).
        new = not all(self._lines[r].get("disabled") for r in rows)
        for r in rows:
            if 0 <= r < len(self._lines):
                self._lines[r]["disabled"] = new
        if not new:
            # Enabled again: absorb any overlap that arose with
            # neighbours that have been stretched over it in the
            # meantime (B199b).
            for r in rows:
                if 0 <= r < len(self._lines) \
                        and not self._lines[r]["crowd"]:
                    self._reenable_fit(r)
        # B509: switching off works on the PAIR - the rows above carry
        # both lanes, so the original block follows its sentences either
        # way round. Re-enabling moves times, and not only of these rows:
        # ``_reenable_fit`` shortens the NEIGHBOURS to make room. Only
        # mirroring ``rows`` left those neighbours' blocks behind, which
        # is the very drift this was meant to end - so every block goes
        # back onto its rows.
        self._sync_all_originals()
        self._recheck()
        self.update()
        return True

    def _reenable_fit(self, r: int) -> None:
        """Clamp a re-enabled line between its neighbours; if there is no
        room, make it 2x the minimum and shrink each neighbour by 1x the
        minimum (B199b)."""
        start, end = _line_span(self._lines[r])
        span = self._without_overlap([r], start, end)
        if span[1] - span[0] >= 2 * _MIN_LINE_S:
            if span != (start, end):
                _remap_line(self._lines[r], *span)
            return
        # No room: force 2x the minimum and push the neighbours away by 1x
        # the minimum. Only the direct neighbours in the ordering (index),
        # so that the order does not change and the line stays in its own
        # place (B199b).
        def neighbour(before: bool):
            search_range = range(r - 1, -1, -1) if before else range(r + 1,
                                                              len(self._lines))
            for i in search_range:
                o = self._lines[i]
                if not o["crowd"] and not self._skippable(i):   # B510
                    return i
            return None
        previous, next = neighbour(True), neighbour(False)
        if previous is not None:
            vs, ve = _line_span(self._lines[previous])
            _remap_line(self._lines[previous], vs,
                        max(vs + _MIN_LINE_S, ve - _MIN_LINE_S))
        if next is not None:
            ns, ne = _line_span(self._lines[next])
            _remap_line(self._lines[next],
                        min(ne - _MIN_LINE_S, ns + _MIN_LINE_S), ne)
        lo = _line_span(self._lines[previous])[1] if previous is not None else start
        _remap_line(self._lines[r], lo, lo + 2 * _MIN_LINE_S)

    # -- Drawing -------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt interface
        painter = QPainter(self)
        try:
            self._paint(painter, event)
        except Exception:  # noqa: BLE001 - a paint error never closes the app
            logger.exception(t("log_timing_paint_error"))
        finally:
            painter.end()

    def _columns_for(self, peaks, width: int):
        """Resample the waveform peaks to ``width`` and cache the result
        per zoom level (avoids recomputing on every repaint)."""
        key = (id(peaks), width)
        if self._col_cache_key != key or self._col_cache is None:
            self._col_cache = waveform.resample_peaks(peaks, max(width, 1))
            self._col_cache_key = key
        return self._col_cache

    def _paint(self, painter, event) -> None:
        width, height = self.width(), self.height()
        rect = event.rect()
        # Visible drawing area (stays integer; do not reuse as a loop
        # variable - that broke the karaoke waveform before, B92).
        vis_x0 = max(0, rect.left())
        vis_x1 = min(width, rect.right() + 1)
        painter.fillRect(rect, QColor(250, 250, 252))

        self._draw_original_wave(painter, self._original_peaks, 0,
                                 QColor(180, 120, 60), "original",
                                 vis_x0, vis_x1)
        # The original-text lane follows the same view as the karaoke
        # (B161).
        from . import timing as timing_module
        line_block = {row: line.get("block", 0)
                     for row, line in enumerate(self._lines)}
        orig_cells = timing_module.original_view_cells(
            self._originals, self._view_mode, line_block)
        self._orig_cells = orig_cells
        for oi, cel in enumerate(orig_cells):
            ox1 = cel["start"] * self._pps
            ox2 = cel["end"] * self._pps
            y = _ORIG_LANE_TOP + (oi % 2) * _ORIG_ROW_H
            rows = cel.get("rows") or []
            uit = bool(rows) and all(
                self._lines[r].get("disabled")
                for r in rows if 0 <= r < len(self._lines))
            # Mirrored standalone crowd line (B193): exists only in the
            # karaoke, not real original text. Red/dotted instead of the
            # usual beige, so that it is not mistaken for original text
            # among the real original sentences (B257).
            is_crowd = bool(cel.get("crowd"))
            # B499: this sentence is fetched back from the original, so
            # THIS block is blue - the text stays readable.
            own = [r for r in rows if 0 <= r < len(self._lines)]
            fetched = bool(own) and all(
                self._lines[r].get("restore") for r in own)
            moved = fetched and any(int(self._lines[r]["index"])
                                    in self._moved_restores for r in own)
            if uit:
                fill_color = QColor(200, 200, 200, 120)
            elif fetched:
                fill_color = _ORIG_RESTORE
            elif is_crowd:
                fill_color = _ORIG_CROWD
            else:
                fill_color = _ORIG_BLOCK
            painter.fillRect(int(ox1), y, max(3, int(ox2 - ox1)),
                             _ORIG_ROW_H - 4, fill_color)
            selected = (oi == self._sel_orig)
            border_color = (_RESTORE_BORDER if fetched
                         else QColor(150, 30, 30) if selected
                         else QColor(150, 30, 30) if is_crowd
                         else QColor(60, 50, 30))
            # B499: a dotted blue border says the piece of original no
            # longer lies on this sentence - it was moved in 1.4.
            # A crowd line is dashed (B257); a MOVED piece is dotted, so
            # the two stay apart.
            style = (Qt.DotLine if moved
                     else Qt.DashLine if is_crowd else Qt.SolidLine)
            painter.setPen(QPen(border_color, 2 if (selected or moved) else 1,
                                style))
            painter.drawRect(int(ox1), y, max(3, int(ox2 - ox1)),
                             _ORIG_ROW_H - 4)
            painter.setPen(QPen(QColor(120, 120, 120) if uit
                                else QColor(90, 30, 30) if is_crowd
                                else QColor(60, 50, 30)))
            prefix = "[uit] " if uit else ("[crowd] " if is_crowd else "")
            # B485: the background piece belongs to this sentence and is
            # shown with it, between brackets so that it is clear it is
            # not sung along with.
            background = str(cel.get("bg") or "")
            text_value = prefix + cel["text"] + (
                f"  [{background}]" if background else "")
            painter.drawText(int(ox1) + 4, y + 18,
                             text_value[:int((ox2 - ox1) / 7) or 1])
        self._draw_wave(painter, self._karaoke_peaks, _KARAOKE_WAVE_TOP,
                        QColor(90, 110, 150), "karaoke", vis_x0, vis_x1)
        # Vocal stem of the original on the karaoke timeline (B196).
        self._draw_original_wave(painter, self._vocal_peaks, _VOCAL_WAVE_TOP,
                                 QColor(150, 80, 160), "vocals",
                                 vis_x0, vis_x1, wave_h=_VOCAL_HEIGHT)

        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawLine(0, _AXIS_TOP + 14, width, _AXIS_TOP + 14)
        tick_step = 10 if self._pps < 40 else (5 if self._pps < 120 else 1)
        second = 0
        while second <= self._duration:
            x = int(second * self._pps)
            painter.drawLine(x, _AXIS_TOP + 8, x, _AXIS_TOP + 20)
            painter.drawText(x + 3, _AXIS_TOP + 30,
                             f"{second // 60}:{second % 60:02d}")
            second += tick_step

        from . import timing as timing_module
        self._cells = timing_module.editor_view_cells(self._lines,
                                                      self._view_mode)
        for row, cel in enumerate(self._cells):
            x1, x2 = cel["start"] * self._pps, cel["end"] * self._pps
            y = _LANES_TOP + (row % 3) * 34
            uit = cel.get("uit", False)
            rows = cel.get("rows") or []
            # B499: the karaoke text stays as it is. The marking belongs
            # to the ORIGINAL that is fetched back, so it is shown there;
            # colouring the karaoke sentence blue as well hid the very
            # text the user is working on.
            background = bool(cel.get("bg"))       # B507
            if uit:
                fill = QColor(200, 200, 200, 120)   # disabled = grey
            elif background:
                fill = _BG_BLOCK
            else:
                fill = _RED if cel["crowd"] else _GREEN
            painter.fillRect(int(x1), y, max(3, int(x2 - x1)), 28, fill)
            # B499: the sentence keeps its text and its colour, but a
            # blue border says that it is fetched back from the original
            # - otherwise a line that has no block in the original lane
            # (a whole [bg] line) can be marked without anything at all
            # showing for it.
            restores = bool(rows) and all(
                self._lines[r].get("restore")
                for r in rows if 0 <= r < len(self._lines))
            # B508: a sentence with a problem between the lines gets an
            # orange border, so it is visible here and not only in the
            # report three steps later.
            error = bool(set(rows) & self._problem_rows)
            border = QColor(150, 30, 30) if row == self._sel_cell \
                else _PROBLEM_BORDER if error \
                else _RESTORE_BORDER if restores \
                else _BG_BORDER if background else QColor(40, 40, 40)
            painter.setPen(QPen(border,
                                2 if (row == self._sel_cell
                                      or restores or error)
                                else 1,
                                Qt.DotLine if background else Qt.SolidLine))
            painter.drawRect(int(x1), y, max(3, int(x2 - x1)), 28)
            painter.setPen(QPen(QColor(120, 120, 120) if uit
                                else QColor(70, 110, 75) if background
                                else QColor(40, 40, 40)))
            label = ("[uit] " + cel["text"]) if uit else cel["text"]
            painter.drawText(int(x1) + 4, y + 19,
                             label[:int((x2 - x1) / 7) or 1])

        if self._marker is not None:
            xm = int(self._marker * self._pps)
            painter.setPen(QPen(_MARKER, 1))
            painter.drawLine(xm, 0, xm, height)  # persistent marker
        if self._playhead is not None:
            x = int(self._playhead * self._pps)
            painter.setPen(QPen(_PLAYHEAD, 2))
            painter.drawLine(x, 0, x, height)  # continuous across all lanes

    def _draw_wave(self, painter, peaks, top, color, label,
                   x0: int, x1: int, wave_h: int = _WAVE_HEIGHT) -> None:
        if peaks is None:
            painter.setPen(QPen(QColor(150, 150, 150)))
            painter.drawText(60, top + wave_h // 2,
                             t("wave_unavailable").format(
                                 name=t(f"lane_{label}")))
            return
        mid = top + wave_h / 2
        columns = self._columns_for(peaks, max(self.width(), 1))
        painter.setPen(QPen(color))
        for x in range(int(x0), int(min(x1, len(columns)))):
            value = float(columns[x])
            if not math.isfinite(value):
                continue
            extent = value * (wave_h / 2 - 8)
            painter.drawLine(x, int(mid - extent), x, int(mid + extent))

    def _draw_original_wave(self, painter, peaks, top, color, label,
                            x0: int, x1: int,
                            wave_h: int = _WAVE_HEIGHT) -> None:
        """Draw a waveform of the ORIGINAL on the KARAOKE timeline.

        Every original time is projected via the alignment (offset
        regions), so that the peaks end up straight above the karaoke -
        also with drift/tempo changes (piecewise per region). Only the
        visible range ``[x0, x1)`` is drawn. Used for both the original
        mix and the vocal stem (B196).
        """
        if peaks is None:
            painter.setPen(QPen(QColor(150, 150, 150)))
            painter.drawText(60, top + wave_h // 2,
                             t("wave_unavailable").format(
                                 name=t(f"lane_{label}")))
            return
        mid = top + wave_h / 2
        n = len(peaks)
        painter.setPen(QPen(color))
        for i in range(n):
            original_time = (i + 0.5) / n * self._original_duration
            x = int(self._project(original_time) * self._pps)
            if x0 <= x < x1:
                value = float(peaks[i])
                if not math.isfinite(value):
                    continue
                extent = value * (wave_h / 2 - 8)
                painter.drawLine(x, int(mid - extent), x, int(mid + extent))

    # -- Mouse interaction -----------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        position = event.position()
        moment = position.x() / self._pps
        # Clicking a cell selects it (for disabling/enabling, B180) - in
        # every view, including 'woorden'.
        op_een_cel = False                      # B414
        for ci, cel in enumerate(getattr(self, "_cells", [])):
            y = _LANES_TOP + (ci % 3) * 34
            if (y <= position.y() <= y + 28
                    and cel["start"] * self._pps <= position.x()
                    <= cel["end"] * self._pps):
                # B507: a background block selects nothing - but the
                # click DID land on a block, so it must not fall through
                # to a later cell (three positions on is the same row)
                # and it must not move the playhead either.
                if not cel.get("rows"):
                    op_een_cel = True
                    break
                self._sel_cell = ci
                self._sel_orig = None          # karaoke selection wins (B198)
                self.update()
                op_een_cel = True
                break
        # Clicking a cell in the original lane selects it, so that a line
        # can be disabled/enabled there as well (B198).
        for oi, cel in enumerate(getattr(self, "_orig_cells", [])):
            y = _ORIG_LANE_TOP + (oi % 2) * _ORIG_ROW_H
            if (y <= position.y() <= y + _ORIG_ROW_H - 4
                    and cel["start"] * self._pps <= position.x()
                    <= cel["end"] * self._pps):
                self._sel_orig = oi
                self._sel_cell = None
                self.update()
                break
        # Dragging/stretching on cells: in 'zinnen' per line, in 'blokken'
        # per block (B162). In the 'words' view only for orientation.
        if self._view_mode in ("sentences", "blocks"):
            for ci, cel in enumerate(getattr(self, "_cells", [])):
                y = _LANES_TOP + (ci % 3) * 34
                if not (y <= position.y() <= y + 28):
                    continue
                # B507: a background block is drawn, not dragged. It
                # moves with the sentence it belongs to; grabbing it
                # separately would let the user pull it loose from its
                # own line, and it has no rows to move anyway.
                if not cel.get("rows"):
                    continue
                mode = self._hit_mode(position.x(),
                                      (cel["start"], cel["end"]))
                if mode is not None:
                    self._drag = ("cel", ci, mode, moment)
                    return
        if self._view_mode == "sentences":
            for index, original in enumerate(self._originals):
                y = _ORIG_LANE_TOP + (index % 2) * _ORIG_ROW_H
                if not (y <= position.y() <= y + _ORIG_ROW_H - 4):
                    continue
                mode = self._hit_mode(position.x(),
                                      (original["start"], original["end"]))
                if mode is not None:
                    self._drag = ("original", index, mode, moment)
                    return
        in_vocal_lane = (_VOCAL_WAVE_TOP <= position.y()
                       <= _VOCAL_WAVE_TOP + _VOCAL_HEIGHT)
        # B414: an empty spot in the text lane counts too. Clicking
        # beside a block did literally nothing there - no selection, no
        # playhead - while the lanes are the widest surface on the
        # screen and the place you are looking anyway when you are
        # timing a line. Only the empty spots: hitting a block still
        # means grabbing that block, and that is caught above.
        in_text_lane = position.y() >= _LANES_TOP and not op_een_cel
        if position.y() <= _AXIS_TOP + 20 or in_vocal_lane or in_text_lane:
            # Click (on the waveforms/time bar, the vocal stem lane
            # (B230) or an empty spot in the text lane): playhead +
            # persistent marker move there (paused; playback starts with
            # the play button, from the marker).
            self._playhead = max(0.0, min(moment, self._duration))
            self._marker = self._playhead
            self.update()
            self._on_seek(self._playhead)

    def _hit_mode(self, x: float,
                  span: tuple[float, float]) -> str | None:
        x1, x2 = span[0] * self._pps, span[1] * self._pps
        if abs(x - x1) <= _EDGE_PX:
            return "links"
        if abs(x - x2) <= _EDGE_PX:
            return "rechts"
        if x1 <= x <= x2:
            return "verplaats"
        return None

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is None:
            self._update_cursor(event.position().x(), event.position().y())
            return
        kind, row, mode, grabbed = self._drag
        moment = event.position().x() / self._pps
        delta = moment - grabbed
        if abs(delta) < 0.01:
            return
        if kind == "original":
            self._move_original(row, mode, delta)
            self._drag = (kind, row, mode, moment)
            self.update()
            return
        # kind == "cel": one sentence (zinnen) or a whole block (blokken).
        cel = self._cells[row] if row < len(self._cells) else None
        if cel is None:
            return
        rows = cel.get("rows", [])
        start, end = cel["start"], cel["end"]
        limit = self._duration                    # B345
        if mode == "verplaats":
            width = end - start
            new_start = max(0.0, min(start + delta, limit - width))
            new_start = min(snap_time(new_start, self._playhead, self._pps),
                            max(0.0, limit - width))
            span = (new_start, new_start + width)
        elif mode == "links":
            new_start = min(max(0.0, start + delta), end - _MIN_LINE_S)
            new_start = min(snap_time(new_start, self._playhead, self._pps),
                            end - _MIN_LINE_S)
            span = (new_start, end)
        else:
            span = (start, min(max(end + delta, start + _MIN_LINE_S), limit))
        # B405: the grabbed edge goes along, so that stretching only
        # moves the edge under the mouse.
        span = self._keep_in_order(rows, *span, anchor=mode)      # B346
        span = self._without_overlap(rows, *span, anchor=mode)
        self._remap_rows(rows, (start, end), span)
        # B508: always, and for every original involved. It used to run
        # only for a single line, so in the block view the original lane
        # simply stayed behind.
        self._mirror_to_original(rows)
        self._drag = (kind, row, mode, moment)
        self.update()

    def _remap_rows(self, rows: list[int], old_span: tuple[float, float],
                    new_span: tuple[float, float]) -> None:
        """Scale all lines in ``rows`` linearly from ``old_span`` to
        ``new_span`` (shifting/stretching a block, B162)."""
        old_width = max(old_span[1] - old_span[0], 1e-6)
        factor = (new_span[1] - new_span[0]) / old_width
        for row in rows:
            if not (0 <= row < len(self._lines)):
                continue
            for syl in self._lines[row]["syllables"]:
                syl["start"] = round(
                    new_span[0] + (syl["start"] - old_span[0]) * factor, 3)
                syl["end"] = round(
                    new_span[0] + (syl["end"] - old_span[0]) * factor, 3)

    def _sync_original(self, index: int) -> None:
        """Put a coupled original block back on its own rows (B508).

        The same min/max rule the editor is built with, so the block and
        the sentence(s) under it are the same length by construction
        instead of by two mirroring routes that each had their holes:
        one only worked for a 1-to-1 coupling, and in the block view
        neither of them ran at all.
        """
        if not (0 <= index < len(self._originals)):
            return
        original = self._originals[index]
        rows = [row for row in original.get("rows", ())
                if 0 <= row < len(self._lines)]
        if not rows:
            return
        spans = [_line_span(self._lines[row]) for row in rows]
        original["start"] = min(start for start, _end in spans)
        original["end"] = max(end for _start, end in spans)

    def _mirror_to_original(self, rows: Sequence[int]) -> None:
        """Mirror moved karaoke lines onto their original blocks (B508)."""
        for index in {self._line_to_orig.get(row) for row in rows}:
            if index is not None:
                self._sync_original(index)

    def _sync_all_originals(self) -> None:
        """Every coupled block back onto its rows (B508)."""
        for index in range(len(self._originals)):
            self._sync_original(index)

    def _update_cursor(self, x: float, y: float) -> None:
        """Show a <-> cursor when the mouse is on a stretchable edge."""
        on_edge = False
        if self._view_mode in ("sentences", "blocks"):
            for ci, cel in enumerate(self._cells):
                top = _LANES_TOP + (ci % 3) * 34
                if not cel.get("rows"):        # B507: background block
                    continue
                if top <= y <= top + 28 and self._hit_mode(
                        x, (cel["start"], cel["end"])) in ("links", "rechts"):
                    on_edge = True
                    break
        if not on_edge:
            for index, original in enumerate(self._originals):
                top = _ORIG_LANE_TOP + (index % 2) * _ORIG_ROW_H
                if top <= y <= top + _ORIG_ROW_H - 4 and self._hit_mode(
                        x, (original["start"], original["end"])) in (
                        "links", "rechts"):
                    on_edge = True
                    break
        self.setCursor(Qt.CursorShape.SizeHorCursor if on_edge
                       else Qt.CursorShape.ArrowCursor)

    def _move_original(self, index: int, mode: str, delta: float) -> None:
        """Shift/stretch an original sentence; coupled karaoke lines move
        along relatively."""
        from .timing import remap_relative

        original = self._originals[index]
        old_span = (original["start"], original["end"])
        rows = [row for row in original.get("rows", ())
                if 0 <= row < len(self._lines)]
        # B508: this lane runs on the KARAOKE clock since B489 (an
        # uncoupled sentence is placed between its coupled neighbours),
        # so the karaoke duration is the ceiling. Bounding on the
        # original's own duration was left over from before that.
        limit = self._duration
        if mode == "verplaats":
            width = old_span[1] - old_span[0]
            shift = max(min(delta, limit - old_span[1]), -old_span[0])
            new_span = (old_span[0] + shift, old_span[0] + shift + width)
        elif mode == "links":
            new_start = min(max(0.0, old_span[0] + delta),
                            old_span[1] - _MIN_LINE_S)
            new_start = snap_time(new_start, self._playhead, self._pps)
            new_span = (min(new_start, old_span[1] - _MIN_LINE_S),
                        old_span[1])
        else:
            new_span = (old_span[0],
                        min(max(old_span[1] + delta,
                                old_span[0] + _MIN_LINE_S), limit))
        # No overlap with other original sentences, and never past them
        # either: the original text runs in the order of the lyrics
        # (B346). Bounding on the END of the predecessor and the START of
        # the successor covers both at once, and squeezing in against a
        # neighbour keeps working. Deliberately no longer via
        # ``clamp_span``: that one looks for the nearest FREE gap, and a
        # gap before the predecessor is just as free - which is exactly
        # how a sentence could jump over its neighbour.
        # B508: skip the neighbours that bound nothing - a mirrored
        # crowd block and a switched-off block. This bound comes FIRST
        # and ``_inside`` slides on a move, so without the exemption a
        # drag to the right jumped left against a crowd block and then
        # sat stuck, while the karaoke lane would happily have allowed
        # the move.
        low = self._bound_original(index, before=True)
        high = self._bound_original(index, before=False, fallback=limit)
        new_span = _inside(new_span, low, high, mode)          # B405
        # B508: the karaoke lane has its own rules - no swapping places,
        # no overlap - and up to v0.145.0 they were not applied here.
        # That made the original lane a back door around every one of
        # them: dragging or stretching a sentence up here pushed its
        # karaoke line straight over its neighbour, and with a [bg]
        # piece scaling along past the end it did so every time.
        if rows:
            new_span = self._keep_in_order(rows, *new_span, anchor=mode)
            new_span = self._without_overlap(rows, *new_span, anchor=mode)
        original["start"], original["end"] = new_span
        for row in rows:
            line = self._lines[row]
            start, end = _line_span(line)
            _remap_line(line, *remap_relative(start, end, old_span,
                                              new_span))
        # And the block goes back onto its rows, so the pair cannot
        # drift apart on a rounding or a clamp.
        self._sync_original(index)

    def _bound_original(self, index: int, before: bool,
                        fallback: float = 0.0) -> float:
        """The nearest original block that really bounds this one (B508)."""
        span = (range(index - 1, -1, -1) if before
                else range(index + 1, len(self._originals)))
        for other in span:
            block = self._originals[other]
            rows = [row for row in block.get("rows", ())
                    if 0 <= row < len(self._lines)]
            if block.get("crowd"):
                continue
            if rows and all(self._lines[row].get("disabled")
                            for row in rows):
                continue
            return float(block["end"] if before else block["start"])
        return 0.0 if before else fallback

    def _keep_in_order(self, rows: Sequence[int], start: float,
                       end: float,
                       anchor: str = "verplaats") -> tuple[float, float]:
        """Keep a selection between its neighbours (B346).

        Overlapping is a separate question (crowd lines may, the rest may
        not); passing is never allowed, not even for crowd and not even
        in the block view. The bound is therefore loose - the START of
        the line before and the END of the line after - so that an
        allowed overlap stays possible while swapping places does not.
        Disabled lines do not count, in the same spirit as B199.
        """
        if not rows:
            return start, end
        low, high = 0.0, self._duration
        for index in range(min(rows) - 1, -1, -1):
            if index in rows or self._skippable(index):
                continue
            low = _line_span(self._lines[index])[0]
            break
        for index in range(max(rows) + 1, len(self._lines)):
            if index in rows or self._skippable(index):
                continue
            high = _line_span(self._lines[index])[1]
            break
        return _inside((start, end), low, high, anchor)

    def _skippable(self, index: int) -> bool:
        """A neighbour that does not bound anything (B510).

        A switched-off line may be stretched over (B199), and a whole
        ``[bg]`` line may be lain over - background vocals sound WITH a
        sentence. Without this a background line became a wall in the
        lane: the editor refused a move that ``line_checks`` calls
        perfectly correct, and it did so exactly where the user can see
        that background line lying for the first time.
        """
        line = self._lines[index]
        return bool(line.get("disabled") or line.get("bg"))

    def _without_overlap(self, rows: Sequence[int], start: float,
                         end: float,
                         anchor: str = "verplaats") -> tuple[float, float]:
        """Prevent overlap with other blocks (crowd may overlap).

        B346: also for a whole block. That check used to run only for a
        single line, so in the block view a block could be dragged
        straight over its neighbour.
        """
        own = set(rows)
        if not own or all(self._lines[row]["crowd"] for row in own):
            return start, end
        # Bounded by the END of the nearest line before it and the START
        # of the nearest line after it: that forbids overlapping AND
        # passing in one go, and squeezing in against a neighbour keeps
        # working. Disabled lines do not count: stretching over them is
        # allowed (B199), and crowd lines may be overlapped.
        low, high = 0.0, self._duration
        for index in range(min(own) - 1, -1, -1):
            other = self._lines[index]
            if index in own or other["crowd"] or self._skippable(index):
                continue
            low = _line_span(other)[1]
            break
        for index in range(max(own) + 1, len(self._lines)):
            other = self._lines[index]
            if index in own or other["crowd"] or self._skippable(index):
                continue
            high = _line_span(other)[0]
            break
        return _inside((start, end), low, high, anchor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None:
            self._recheck()                                    # B508
            self.update()
        self._drag = None


def _inside(span: tuple[float, float], low: float,
            high: float, anchor: str = "verplaats") -> tuple[float, float]:
    """Push a time slot inside ``low``..``high`` (B345/B346/B405).

    ``anchor`` says which edge the user has hold of, and that decides
    what may give way:

    * ``"verplaats"`` - the slot moves as a whole. Sticks it out on one
      side, then it slides back inside with its width intact, so
      squeezing in against a neighbour keeps working.
    * ``"rechts"`` - the user is stretching the END. The start stays
      exactly where it is and only the end is capped at ``high``.
    * ``"links"`` - mirror image: the end stays put, the start is
      capped at ``low``.

    B405: before this, every case behaved like ``"verplaats"``. Stretch
    a line to the right against its neighbour and the slot kept its new
    width and slid LEFT to fit - so the word grew on the side the user
    was not touching. Sliding is right for moving and wrong for
    stretching; that difference is what ``anchor`` carries.

    When there really is no room, a stretch returns the slot unchanged:
    refusing to move is the honest answer there, jumping is not.
    """
    start, end = span
    if anchor == "rechts":
        if high < start + _MIN_LINE_S:
            return span
        return start, min(max(end, start + _MIN_LINE_S), high)
    if anchor == "links":
        if low > end - _MIN_LINE_S:
            return span
        return max(min(start, end - _MIN_LINE_S), low), end
    if high - low < _MIN_LINE_S:
        return low, low + _MIN_LINE_S
    width = min(end - start, high - low)
    start = min(max(start, low), high - width)
    return start, max(start + width, start + _MIN_LINE_S)


def _line_span(line: dict) -> tuple[float, float]:
    syllables = _sung_pieces(line)
    if not syllables:  # defensive: never crash on an empty line
        return 0.0, _MIN_LINE_S
    return syllables[0]["start"], syllables[-1]["end"]


def _sung_pieces(line: dict) -> list:
    """The pieces that make up the sentence itself (B485).

    An inline ``[bg]`` piece belongs to the line but is allowed to lie
    over its neighbours, so it must not decide where the sentence begins
    or ends - otherwise dragging the background vocals would drag the
    whole sentence with it.
    """
    pieces = list(line.get("syllables") or ())
    sung = [item for item in pieces if not item.get("bg")]
    return sung or pieces


def _remap_line(line: dict, new_start: float, new_end: float) -> None:
    """Scale all syllable times linearly to the new range."""
    old_start, old_end = _line_span(line)
    old_width = max(old_end - old_start, 1e-6)
    factor = (new_end - new_start) / old_width
    for syllable in line["syllables"]:
        syllable["start"] = round(
            new_start + (syllable["start"] - old_start) * factor, 3)
        syllable["end"] = round(
            new_start + (syllable["end"] - old_start) * factor, 3)


class TimingEditorDialog(QDialog):
    """Dialog with waveforms, playback, zoom and saving."""

    def __init__(self, karaoke_peaks: np.ndarray,
                 original_peaks: np.ndarray | None, duration: float,
                 lines: Sequence[TimedLine],
                 on_save: Callable[..., None],
                 audio_paths: dict[str, Path | None],
                 offset: float = 0.0,
                 originals: list[dict] | None = None,
                 on_reset: Callable[[], list[dict]] | None = None,
                 original_duration: float = 0.0,
                 regions=None,
                 vocal_peaks: np.ndarray | None = None,
                 restore_rows: Sequence[int] = (),
                 moved_restores: Sequence[int] = (),
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("editor_timing_title"))
        self.setWindowFlags(Qt.WindowType.Window
                            | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowCloseButtonHint)
        self.resize(1150, 560)
        self._on_save = on_save
        self._on_reset = on_reset
        self._audio_paths = audio_paths
        self._offset = offset  # karaoke time - original time
        self._lines = [_to_dict(line) for line in lines]
        # B496: which sentences are fetched back from the original is
        # stored by line number, not in timing.json - the marking is a
        # choice about the AUDIO and does not belong in the timing.
        marked = {int(number) for number in restore_rows}
        for line in self._lines:
            line["restore"] = int(line["index"]) in marked
        # B406: a line that was saved flat cannot be repaired by hand -
        # stretching scales linearly and zero stays zero. So it is put
        # right on the way in; it only lands on disk when the user saves.
        repaired = spread_flattened(self._lines)
        if repaired:
            logger.info(t("log_timing_flat_repaired"), repaired)
        self._originals = originals or []
        self._initial_original = {
            o["line_no"]: (round(o["start"], 3), round(o["end"], 3))
            for o in self._originals if "line_no" in o}

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        zoom_in = QPushButton(t("zoom_in"))
        zoom_out = QPushButton(t("zoom_out"))
        toolbar.addWidget(zoom_in)
        toolbar.addWidget(zoom_out)
        self._source = QComboBox()
        for name in ("original", "karaoke", "vocals"):   # B196
            if audio_paths.get(name) is not None:
                self._source.addItem(t(f"lane_{name}"), name)
        self._play_button = QPushButton(t("play"))
        if _MULTIMEDIA and self._source.count():
            toolbar.addWidget(QLabel(t("source_label")))
            toolbar.addWidget(self._source)
            toolbar.addWidget(self._play_button)
        # View choice blocks/sentences/words (B127).
        self._view_combo = QComboBox()
        for mode in ("blocks", "sentences", "words"):    # B160: order
            self._view_combo.addItem(t(f"view_{mode}"), mode)
        idx = self._view_combo.findData("sentences")         # default: zinnen
        self._view_combo.setCurrentIndex(idx if idx >= 0 else 0)
        toolbar.addWidget(QLabel(t("view_label")))
        toolbar.addWidget(self._view_combo)
        disable_button = QPushButton(t("line_toggle"))
        disable_button.setToolTip(t("line_toggle_tip"))
        disable_button.clicked.connect(
            lambda: self._canvas.toggle_selected_disabled())
        toolbar.addWidget(disable_button)
        restore_button = QPushButton(t("line_restore"))       # B496
        restore_button.setToolTip(t("line_restore_tip"))
        restore_button.clicked.connect(
            lambda: self._canvas.toggle_selected_restore())
        toolbar.addWidget(restore_button)
        # B481: the hint about clicking in the waveform is out - after a
        # hundred sessions in this editor it only took up room.
        toolbar.addStretch(1)
        # B504: the "adjust syllables" button of B497 is gone. Measured
        # over eighteen projects it won nothing anywhere and lost 14 ms
        # on the one song where the user really had moved syllables by
        # hand; a button that promises something it does not deliver is
        # worse than no button.
        reset_button = QPushButton(t("reset_original"))
        save_button = QPushButton(t("save_timing"))
        close_button = QPushButton(t("close"))
        if on_reset is not None:
            toolbar.addWidget(reset_button)
        toolbar.addWidget(save_button)
        toolbar.addWidget(close_button)
        layout.addLayout(toolbar)

        from . import align as _align
        regions = regions or ()
        project = (lambda t: _align.project_time(t, regions)) if regions \
            else (lambda t: t)
        self._canvas = TimingCanvas(karaoke_peaks, original_peaks, duration,
                                    self._lines, on_seek=self._seek,
                                    originals=self._originals,
                                    original_duration=original_duration,
                                    project=project, vocal_peaks=vocal_peaks,
                                    moved_restores=moved_restores)
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._canvas)
        self._scroll.setWidgetResizable(False)
        layout.addWidget(self._scroll, stretch=1)
        self._build_lane_labels()   # fixed (non-scrolling) labels (B196)

        self._view_combo.currentIndexChanged.connect(
            lambda: self._canvas.set_view_mode(
                self._view_combo.currentData()))
        zoom_in.clicked.connect(lambda: self._zoom(1.5))
        zoom_out.clicked.connect(lambda: self._zoom(1 / 1.5))
        reset_button.clicked.connect(self._reset)
        save_button.clicked.connect(self._save)
        close_button.clicked.connect(self.accept)

        self._player = None
        if _MULTIMEDIA and self._source.count():
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_output)
            self._play_button.clicked.connect(self._toggle_play)
            self._source.currentIndexChanged.connect(
                lambda _: self._stop_playback())
            self._timer = QTimer(self)
            self._timer.setInterval(50)
            self._timer.timeout.connect(self._tick)
            self._timer.start()

    # -- Fixed lane labels (B196) ----------------------------------------

    def _build_lane_labels(self) -> None:
        """Create fixed labels at the top left per lane that do not scroll
        along (B196).

        The labels are children of the scroll viewport (not of the
        canvas), so that they stay in place while the waveforms scroll
        horizontally."""
        self._lane_labels: list[QLabel] = []
        for key, top in _LANE_LABELS:
            label = QLabel(t(f"lane_{key}"), self._scroll.viewport())
            label.setStyleSheet(
                "color:#333; background: rgba(250,250,252,200);"
                " padding:0 3px; font-size:10px;")
            label.move(3, top + 1)
            label.show()
            self._lane_labels.append(label)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt interface
        super().resizeEvent(event)
        for (key, top), label in zip(_LANE_LABELS,
                                     getattr(self, "_lane_labels", [])):
            label.move(3, top + 1)

    # -- Playback ---------------------------------------------------------

    def _zoom(self, factor: float) -> None:
        """Zoom around the playhead (or the middle of the view).

        This keeps the spot you are working on in view, so you do not
        have to scroll back all the time.
        """
        canvas = self._canvas
        bar = self._scroll.horizontalScrollBar()
        viewport = self._scroll.viewport().width()
        if canvas.playhead is not None:
            anchor = canvas.playhead
        else:
            anchor = (bar.value() + viewport / 2) / canvas.pixels_per_second
        canvas.set_zoom(canvas.pixels_per_second * factor)
        bar.setValue(int(anchor * canvas.pixels_per_second - viewport / 2))

    def _media_offset(self) -> float:
        """Difference between the display timeline (karaoke) and the source.

        The vocal stem is on the original timeline and therefore uses the
        same offset as the original (B196)."""
        return self._offset \
            if self._source.currentData() in ("original", "vocals") \
            else 0.0

    def _seek(self, display_time: float, autoplay: bool = False) -> None:
        """Set the playback position to the playhead.

        Paused by default: that way the playhead stays where you put it
        and you can align a word against it; with the play button the
        sound starts from that spot.
        """
        if self._player is None:
            return
        source = self._audio_paths.get(self._source.currentData())
        if source is None:
            return
        self._player.setSource(QUrl.fromLocalFile(str(source)))
        self._player.setPosition(
            int(max(0.0, display_time - self._media_offset()) * 1000))
        if autoplay:
            self._player.play()
            self._play_button.setText(t("pause"))
        else:
            self._player.pause()
            self._play_button.setText(t("play"))

    def _toggle_play(self) -> None:
        if self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._play_button.setText(t("play"))
        else:
            start = self._canvas.marker
            if start is None:
                start = self._canvas.playhead or 0.0
            self._seek(start, autoplay=True)

    def _stop_playback(self) -> None:
        if self._player is not None:
            self._player.stop()
            self._play_button.setText(t("play"))

    def _tick(self) -> None:
        """Let the playhead run along (and keep it in view)."""
        if (self._player is None or self._player.playbackState()
                != QMediaPlayer.PlaybackState.PlayingState):
            return
        display = self._player.position() / 1000.0 + self._media_offset()
        self._canvas.set_playhead(display)
        x = int(display * self._canvas.pixels_per_second)
        self._scroll.ensureVisible(x, 0, 80, 0)

    def _shutdown_playback(self) -> None:
        """Stop player and timer (on every close path, B93).

        Also clears the source so that Windows releases the audio file
        (e.g. cache/origineel.wav); otherwise it stays locked and the
        cache cannot be emptied on exit (B205).
        """
        if getattr(self, "_player", None) is not None:
            self._player.stop()
            try:
                self._player.setSource(QUrl())
            except Exception:  # noqa: BLE001 - releasing must never crash
                pass
        timer = getattr(self, "_timer", None)
        if timer is not None:
            timer.stop()

    def done(self, result: int) -> None:  # noqa: N802 - Qt interface
        """Closing via button/Esc (accept/reject) also stops playback.

        ``accept()``/``reject()`` call ``done()`` but not
        ``closeEvent``; without this override the music kept playing
        when closing via the button (B93).
        """
        self._shutdown_playback()
        super().done(result)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt interface
        """Stop playback as soon as the editor closes (window cross)."""
        self._shutdown_playback()
        super().closeEvent(event)

    def _save(self) -> None:
        overrides: dict[str, list[float]] = {}
        for original in self._originals:
            line_no = original.get("line_no")
            if line_no is None:
                continue
            span = (round(original["start"], 3), round(original["end"], 3))
            if span != self._initial_original.get(line_no):
                overrides[str(line_no)] = [span[0], span[1]]
        # B441: recompute the held marks over the spans as they are NOW.
        # Stretching a syllable is exactly how a held note comes into
        # being, so the one place it may not go stale is here.
        self._on_save(mark_held(tuple(_from_dict(line)
                                for line in self._lines)), overrides,
                      self._canvas.restore_rows(),          # B496
                      self._canvas.reset_moves())           # B499

    def _reset(self) -> None:
        """Restore original: set both the original lane and the karaoke
        text timing back to the fresh coupling (B100)."""
        if self._on_reset is None:
            return
        fresh = self._on_reset()
        # Backwards compatible: the old behaviour returned only a list of
        # originals.
        if isinstance(fresh, dict):
            originals = fresh.get("originals", [])
            fresh_lines = fresh.get("lines", [])
        else:
            originals, fresh_lines = fresh, []
        self._originals = originals
        self._initial_original = {
            o["line_no"]: (round(o["start"], 3), round(o["end"], 3))
            for o in originals if "line_no" in o}
        if fresh_lines:
            # Replace in place so that the canvas (which shares the same
            # list) shows the new karaoke lines.
            # B498: the marking "back from the original" is a choice
            # about the AUDIO and has nothing to do with the timing, so
            # it survives a reset - without this it disappeared from the
            # screen and the next save wiped it for good.
            marked = {int(line["index"]) for line in self._lines
                      if line.get("restore")}
            self._lines[:] = [_to_dict(line) for line in fresh_lines]
            for line in self._lines:
                line["restore"] = int(line["index"]) in marked
            self._canvas.set_lines(self._lines)
        self._canvas.set_originals(originals)


def _to_dict(line: TimedLine) -> dict:
    return {"index": line.index, "text": line.text, "crowd": line.crowd,
            "crowd_section": line.crowd_section,
            "quality": line.quality, "block": line.block,
            "disabled": line.disabled,
            # B510: the same trap as the syllable mark below - without
            # this, one save turned a whole [bg] line into an ordinary
            # one and it stood in the video.
            "bg": line.bg,
            "syllables": [{"text": syllable.text, "start": syllable.start,
                           "end": syllable.end, "held": syllable.held,
                           "stress": syllable.stress,
                           "crowd": syllable.crowd,
                           # B485: without this, saving once wiped the
                           # mark, and the bg piece then simply stood in
                           # the video.
                           "bg": syllable.bg}
                          for syllable in line.syllables]}


def _from_dict(line: dict) -> TimedLine:
    return TimedLine(
        index=line["index"], text=line["text"], crowd=line["crowd"],
        crowd_section=line.get("crowd_section", False),
        quality=line.get("quality", "sentence"), block=line.get("block", 0),
        disabled=line.get("disabled", False),
        bg=line.get("bg", False),                             # B510
        syllables=tuple(Syllable(text=syl["text"], start=syl["start"],
                                 end=syl["end"], held=syl["held"],
                                 stress=syl.get("stress", False),
                                 crowd=syl.get("crowd", False),
                                 bg=syl.get("bg", False))
                        for syl in line["syllables"]))
