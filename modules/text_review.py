"""Check the text that was heard (v1.0.19, "Make full karaoke").

The one pause of the ordinary karaoke path: what Whisper heard is shown
as the song text, one line per sung line and an empty line between
blocks, for the owner to correct and complete. Buttons mark a selection
(or the line the cursor is in) as ``[bg]`` or ``[crowd]``, start a new
block, and play the line the cursor is in - its time comes from what
was heard, so a line the owner added has none and plays nothing.
"""
from __future__ import annotations

import re

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .translations import t

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    _MULTIMEDIA = True
except ImportError:  # pragma: no cover
    _MULTIMEDIA = False


def wrap(text: str, start: int, end: int, tag: str) -> tuple[str, int]:
    """``text`` with ``[tag]...[/tag]`` around ``start:end``; returns the
    new text and where the cursor goes (after the closing tag)."""
    opening, closing = f"[{tag}]", f"[/{tag}]"
    inner = text[start:end]
    new = text[:start] + opening + inner + closing + text[end:]
    return new, start + len(opening) + len(inner) + len(closing)


def line_span(text: str, position: int) -> tuple[int, int]:
    """The line ``position`` is in, without its line break."""
    begin = text.rfind("\n", 0, position) + 1
    finish = text.find("\n", position)
    return begin, len(text) if finish < 0 else finish


_ONLY_MARKS = re.compile(r"(?i)^(\s*\[/?(bg|crowd)\]\s*)+$")


def _sung(row: str) -> bool:
    """A row with words: not empty, no ``#`` comment, not only marks."""
    stripped = row.strip()
    return bool(stripped) and not stripped.startswith("#") \
        and not _ONLY_MARKS.match(stripped)


def heard_line(row: str, times: Sequence[Sequence], index: int | None
               ) -> tuple[float, float] | None:
    """The heard time of the line ``row``: the heard line most like it
    (the owner adds and moves lines, so counting alone goes wrong after
    the first one he adds), otherwise the one at its place."""
    from difflib import SequenceMatcher

    plain = re.sub(r"(?i)\[/?(bg|crowd)\]", "", row).strip().lower()
    best, score = None, 0.0
    for entry in times:
        if len(entry) < 3 or not plain:
            continue
        ratio = SequenceMatcher(None, plain, str(entry[2]).lower()).ratio()
        if ratio > score:
            best, score = entry, ratio
    if best is not None and score >= 0.5:
        return float(best[0]), float(best[1])
    if index is not None and index < len(times):
        return float(times[index][0]), float(times[index][1])
    return None


def sung_index(text: str, position: int) -> int | None:
    """Which sung line the cursor is in, counted from 0 - the index into
    the heard times."""
    count = -1
    offset = 0
    for row in text.split("\n"):
        if _sung(row):
            count += 1
        if offset <= position <= offset + len(row):
            return count if _sung(row) else None
        offset += len(row) + 1
    return None


class TextReviewDialog(QDialog):
    """The text to check, with its buttons. ``accepted`` means: save and
    go on; ``text()`` is then what to save."""

    def __init__(self, text: str, times: Sequence[Sequence[float]],
                 audio: Path | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("text_review_title"))
        self.resize(760, 640)
        self._times = [tuple(entry) for entry in times or ()]
        layout = QVBoxLayout(self)
        explain = QLabel(t("text_review_explain"))
        explain.setWordWrap(True)
        layout.addWidget(explain)
        self._edit = QPlainTextEdit(text)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._edit.setFont(font)
        layout.addWidget(self._edit, stretch=1)
        row = QHBoxLayout()
        for key, handler in (("text_review_bg", lambda: self._mark("bg")),
                             ("text_review_crowd",
                              lambda: self._mark("crowd")),
                             ("text_review_block", self._new_block)):
            button = QPushButton(t(key))
            button.clicked.connect(handler)
            row.addWidget(button)
        self._play = QPushButton(t("text_review_play"))
        self._play.clicked.connect(self._toggle_play)
        row.addWidget(self._play)
        row.addStretch(1)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addStretch(1)
        go_on = QPushButton(t("text_review_continue"))
        go_on.setDefault(True)
        go_on.clicked.connect(self.accept)
        close = QPushButton(t("text_review_close"))
        close.clicked.connect(self.reject)
        row.addWidget(go_on)
        row.addWidget(close)
        layout.addLayout(row)
        self._player = None
        self._until = None
        if _MULTIMEDIA and audio is not None and Path(audio).exists():
            self._player = QMediaPlayer(self)
            self._output = QAudioOutput(self)
            self._player.setAudioOutput(self._output)
            self._player.setSource(QUrl.fromLocalFile(str(audio)))
            self._timer = QTimer(self)
            self._timer.setInterval(50)
            self._timer.timeout.connect(self._tick)
            self._timer.start()
        else:
            self._play.setEnabled(False)

    def text(self) -> str:
        return self._edit.toPlainText()

    def _mark(self, tag: str) -> None:
        cursor = self._edit.textCursor()
        text = self._edit.toPlainText()
        if cursor.hasSelection():
            start, end = sorted((cursor.selectionStart(),
                                 cursor.selectionEnd()))
        else:
            start, end = line_span(text, cursor.position())
        new, position = wrap(text, start, end, tag)
        self._edit.setPlainText(new)
        cursor = self._edit.textCursor()
        cursor.setPosition(min(position, len(new)))
        self._edit.setTextCursor(cursor)

    def _new_block(self) -> None:
        cursor = self._edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.insertText("\n")
        self._edit.setTextCursor(cursor)

    def _toggle_play(self) -> None:
        if self._player is None:
            return
        if self._until is not None:
            self._stop()
            return
        text = self._edit.toPlainText()
        position = self._edit.textCursor().position()
        index = sung_index(text, position)
        if index is None:
            return
        begin, finish = line_span(text, position)
        found = heard_line(text[begin:finish], self._times, index)
        if found is None:
            return
        start, end = found
        self._player.setPosition(int(max(0.0, start - 0.2) * 1000))
        self._until = end + 0.3
        self._player.play()
        self._play.setText(t("text_review_stop"))

    def _tick(self) -> None:
        if self._until is not None and \
                self._player.position() / 1000.0 >= self._until:
            self._stop()

    def _stop(self) -> None:
        if self._player is not None:
            self._player.pause()
        self._until = None
        self._play.setText(t("text_review_play"))

    def done(self, result: int) -> None:  # noqa: D401 - Qt override
        self._stop()
        super().done(result)
