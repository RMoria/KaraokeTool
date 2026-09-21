"""Stress editor: one sentence, two rows, one time axis (B450).

What this was: a grid of syllable boxes where a click set the stress, and
the stress was a guess from spelling ("the first syllable of a
polysyllabic word"). That guess is wrong often enough to be annoying -
po-lo-NAI-se is stressed on the third - and there is no stress lexicon
in this project to do better.

What it is now rests on the user's own observation: in a song a stress
and a held syllable are nearly always the same place, and the ORIGINAL
already shows where that place is. So the sentence is drawn twice on ONE
time axis - the original above, the karaoke below - and you say which
piece of the karaoke belongs to which piece of the original. A coupled
piece takes the time of its counterpart and the rest of the sentence
gives way in proportion (``timing.fit_between_anchors``). The spelling
guess is only the starting position; the recording has the last word.

Per sentence on purpose, and no waveform. A whole song of phonetic
pieces on one axis is unreadable, and the timing editor is already the
place for the waveform.
"""

from __future__ import annotations

import logging
from typing import Callable, Sequence

from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from . import timing as timing_module
from .translations import t

logger = logging.getLogger(__name__)

_ROW_H = 34
_ORIG_Y = 26
_KAR_Y = 130
_MARGIN = 14
_MIN_BOX = 16

#: Fill of a piece that is coupled to the original: it leads, the rest
#: gives way to it.
_ANCHOR_FILL = QColor(60, 120, 220)
_ANCHOR_TEXT = QColor(255, 255, 255)
#: A piece the original holds long. Same orange as the coupling line, so
#: "long" reads the same in both rows.
_HELD_FILL = QColor(250, 210, 160)
_HELD_EDGE = QColor(210, 120, 20)
_PLAIN_FILL = QColor(234, 238, 244)
_ORIG_FILL = QColor(226, 234, 226)
_EDGE = QColor(120, 128, 136)
_LINK = QColor(210, 120, 20)


class SentenceCanvas(QWidget):
    """One sentence: original above, karaoke below, on one time axis."""

    def __init__(self, on_change: Callable[[], None],
                 on_stress: Callable[[list], None] | None = None) -> None:
        super().__init__()
        self._on_stress = on_stress or (lambda _pieces: None)
        self._original: list = []
        self._karaoke: list = []
        self._anchors: dict[int, int] = {}      # karaoke piece -> original
        self._selected_original: int | None = None
        self._on_change = on_change
        self._boxes: list[tuple] = []           # (x, y, w, h, row, index)
        self.setMinimumSize(600, 200)

    def set_sentence(self, original, karaoke, anchors) -> None:
        self._original = list(original or [])
        self._karaoke = list(karaoke or [])
        self._anchors = dict(anchors or {})
        self._selected_original = None
        self.update()

    def anchors(self) -> dict[int, int]:
        return dict(self._anchors)

    def set_stress(self, index: int) -> None:
        """Move the stress within its word to this piece (B151/B450)."""
        if not (0 <= index < len(self._karaoke)):
            return
        self._karaoke = list(timing_module.set_word_stress(
            tuple(self._karaoke), index))
        self._on_stress(list(self._karaoke))
        self.update()

    # -- geometry ---------------------------------------------------------
    def _window(self) -> tuple[float, float]:
        """The time window both rows are drawn in."""
        moments = [s.start for s in self._original + self._karaoke]
        moments += [s.end for s in self._original + self._karaoke]
        if not moments:
            return 0.0, 1.0
        low, high = min(moments), max(moments)
        return (low, high if high > low else low + 1.0)

    def _x_of(self, moment: float) -> float:
        low, high = self._window()
        usable = max(1, self.width() - 2 * _MARGIN)
        return _MARGIN + (moment - low) / (high - low) * usable

    # -- drawing ----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt interface
        painter = QPainter(self)
        try:
            self._paint(painter)
        except Exception:  # noqa: BLE001 - drawing must never crash
            logger.exception(t("log_stress_paint_error"))
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor(250, 250, 252))
        self._boxes = []
        painter.setPen(QPen(QColor(90, 90, 90)))
        painter.drawText(_MARGIN, _ORIG_Y - 6, t("stress_group_original"))
        painter.drawText(_MARGIN, _KAR_Y - 6, t("stress_group_karaoke"))
        self._paint_row(painter, self._original, _ORIG_Y, "original")
        self._paint_row(painter, self._karaoke, _KAR_Y, "karaoke")
        self._paint_links(painter)

    def _paint_row(self, painter: QPainter, pieces, y: int, row: str) -> None:
        for index, piece in enumerate(pieces):
            left = self._x_of(piece.start)
            width = max(_MIN_BOX, self._x_of(piece.end) - left)
            anchored = (row == "karaoke" and index in self._anchors) or \
                (row == "original" and index in self._anchors.values())
            if anchored:
                fill, ink = _ANCHOR_FILL, _ANCHOR_TEXT
            elif getattr(piece, "held", False):
                fill, ink = _HELD_FILL, QColor(30, 30, 30)
            else:
                fill = _ORIG_FILL if row == "original" else _PLAIN_FILL
                ink = QColor(30, 30, 30)
            painter.fillRect(int(left), y, int(width), _ROW_H, fill)
            edge = _HELD_EDGE if getattr(piece, "held", False) else _EDGE
            selected = (row == "original"
                        and index == self._selected_original)
            painter.setPen(QPen(QColor(30, 90, 200) if selected else edge,
                                2 if selected else 1))
            painter.drawRect(int(left), y, int(width), _ROW_H)
            painter.setPen(QPen(ink))
            painter.drawText(int(left) + 3, y + 21,
                             piece.text.strip() or "·")
            self._boxes.append((left, y, width, _ROW_H, row, index))

    def _paint_links(self, painter: QPainter) -> None:
        painter.setPen(QPen(_LINK, 2))
        for karaoke_index, original_index in self._anchors.items():
            if not (0 <= karaoke_index < len(self._karaoke)
                    and 0 <= original_index < len(self._original)):
                continue
            top = self._original[original_index]
            bottom = self._karaoke[karaoke_index]
            x1 = (self._x_of(top.start) + self._x_of(top.end)) / 2
            x2 = (self._x_of(bottom.start) + self._x_of(bottom.end)) / 2
            painter.drawLine(int(x1), _ORIG_Y + _ROW_H, int(x2), _KAR_Y)

    # -- interaction ------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt interface
        position = event.position().toPoint() if hasattr(event, "position") \
            else event.pos()
        right_button = False
        try:
            from PySide6.QtCore import Qt

            right_button = event.button() == Qt.MouseButton.RightButton
        except Exception:  # noqa: BLE001 - a test may send a bare event
            right_button = False
        for left, y, width, height, row, index in self._boxes:
            if not (left <= position.x() <= left + width
                    and y <= position.y() <= y + height):
                continue
            if right_button and row == "karaoke":
                # The stress stays settable by hand (B151). It moved to
                # the right mouse button because the left one now does
                # the coupling, and taking the stress away entirely would
                # have removed something that was being used.
                self.set_stress(index)
                return
            if row == "original":
                # Select above, then click below: that is the coupling.
                self._selected_original = (
                    None if self._selected_original == index else index)
            elif self._selected_original is not None:
                self._anchors[index] = self._selected_original
                self._selected_original = None
                self._on_change()
            elif index in self._anchors:
                # A click on a coupled karaoke piece releases it, so
                # undoing needs no separate button.
                self._anchors.pop(index)
                self._on_change()
            self.update()
            return


class StressEditorDialog(QDialog):
    """The stress editor: pick a sentence, couple, and the rest fits."""

    def __init__(self, karaoke_lines: Sequence,
                 on_save: Callable[..., None],
                 original_lines: Sequence | None = None,
                 anchors: dict | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("stress_title"))
        self.resize(1000, 460)
        self._on_save = on_save
        # B450: the sentences as they were when the editor opened. Every
        # refit starts from THESE, never from the result of the previous
        # one - otherwise releasing a coupling does nothing, because the
        # times it was supposed to undo have already become the new
        # starting point, and one experimental click is permanent.
        self._original_spans = [
            [(s.start, s.end) for s in line.syllables]
            for line in karaoke_lines]
        self._karaoke = list(karaoke_lines)
        self._original = list(original_lines or [])
        self._anchors = {int(k): dict(v) for k, v in (anchors or {}).items()}

        layout = QVBoxLayout(self)
        hint = QLabel(t("stress_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        picker = QHBoxLayout()
        picker.addWidget(QLabel(t("stress_sentence")))
        self._picker = QComboBox()
        for index, line in enumerate(self._karaoke):
            self._picker.addItem(f"{index + 1}. {line.text[:60]}")
        self._picker.currentIndexChanged.connect(self._show_sentence)
        picker.addWidget(self._picker, stretch=1)
        layout.addLayout(picker)

        self._canvas = SentenceCanvas(self._changed, self._stress_changed)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._canvas)
        layout.addWidget(scroll, stretch=1)

        self._note = QLabel("")
        self._note.setWordWrap(True)
        self._note.setStyleSheet("color: #a33;")
        layout.addWidget(self._note)

        row = QHBoxLayout()
        row.addStretch()
        save = QPushButton(t("couple_save"))
        save.clicked.connect(self.accept)
        close = QPushButton(t("close"))
        close.clicked.connect(self.reject)
        row.addWidget(save)
        row.addWidget(close)
        layout.addLayout(row)
        self._show_sentence(0)

    # -- the sentence on screen ------------------------------------------
    def _show_sentence(self, index: int) -> None:
        if not (0 <= index < len(self._karaoke)):
            return
        original = (list(self._original[index].syllables)
                    if index < len(self._original)
                    and self._original[index] is not None else [])
        self._canvas.set_sentence(original,
                                  list(self._karaoke[index].syllables),
                                  self._anchors.get(index, {}))
        self._note.setText("")

    def _changed(self) -> None:
        """Fit the sentence to the couplings as they now stand."""
        index = self._picker.currentIndex()
        if not (0 <= index < len(self._karaoke)):
            return
        anchors = self._canvas.anchors()
        self._anchors[index] = anchors
        line = self._karaoke[index]
        original = (self._original[index]
                    if index < len(self._original) else None)
        spans = list(self._original_spans[index])
        forced = {}
        if original is not None:
            pieces = list(original.syllables)
            for karaoke_index, original_index in anchors.items():
                if 0 <= original_index < len(pieces):
                    piece = pieces[original_index]
                    forced[karaoke_index] = (piece.start, piece.end)
        fitted, shortfall = timing_module.fit_between_anchors(spans, forced)
        self._karaoke[index] = timing_module.apply_spans(line, fitted)
        self._note.setText(t("stress_no_room").format(seconds=shortfall)
                           if shortfall > 0 else "")
        self._canvas.set_sentence(
            list(original.syllables) if original is not None else [],
            list(self._karaoke[index].syllables), anchors)

    def _stress_changed(self, pieces: list) -> None:
        """Keep the moved stress on the sentence itself."""
        index = self._picker.currentIndex()
        if 0 <= index < len(self._karaoke):
            self._karaoke[index] = timing_module.replace(
                self._karaoke[index], syllables=tuple(pieces))

    def lines(self) -> list:
        """The karaoke sentences as they now stand."""
        return list(self._karaoke)

    def done(self, result: int) -> None:  # noqa: N802 - Qt interface
        """Only save on Save (B450).

        This used to write on every way out, Escape included. That is
        wrong here in a way it was not before: the editor now MOVES
        times, so closing after an experiment would have made the
        experiment permanent - on hand-made timing, without asking.
        """
        if result == QDialog.DialogCode.Accepted:
            try:
                self._on_save(list(self._karaoke), list(self._original),
                              dict(self._anchors))
            except Exception:  # noqa: BLE001 - saving must not crash
                logger.exception(t("log_stress_save_failed"))
        super().done(result)
