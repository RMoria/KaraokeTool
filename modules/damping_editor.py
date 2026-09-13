"""Graphical damping editor for the karaoke audio.

Same idea as the timing editor: the waveform of the karaoke with a time
bar and a playhead (click = playhead moves there, paused; the play
button starts from the playhead). The red blocks are the fragments to
damp; they can be dragged and stretched at their edges (the cursor
becomes <->). Adding fragments ("Demping toevoegen" at the playhead) and
removing them (select + "Verwijderen") is possible too. Saving applies
the damping and exports again.

B282: besides the red damping blocks there is now a second, green block
type ("restore from original"): instead of attenuating the karaoke
audio, the matching piece of the ORIGINAL is laid over it there. Meant
for sound that Demucs (or a manual edit) removed from the karaoke but
that does belong there (e.g. an interjection or a sound effect) -
"Karaoke aanpassen" (step 4) can only damp, never put back something
that is no longer there.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from . import waveform
from .translations import t

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    _MULTIMEDIA = True
except ImportError:  # pragma: no cover
    _MULTIMEDIA = False

logger = logging.getLogger(__name__)

_EDGE_PX = 7
_MIN_S = 0.1
_WAVE_TOP = 4
_WAVE_H = 150
_AXIS_TOP = _WAVE_TOP + _WAVE_H + 6
_BLOCK_TOP = _AXIS_TOP + 30
_BLOCK_H = 34
_CANVAS_H = _BLOCK_TOP + _BLOCK_H + 12
_BLOCK = QColor(220, 60, 50, 110)
_BLOCK_SEL = QColor(220, 60, 50, 190)
_RESTORE_BLOCK = QColor(50, 170, 70, 110)
_RESTORE_BLOCK_SEL = QColor(50, 170, 70, 190)
#: B496: a restore fragment that came from a sentence marked in the
#: timing editor gets its own colour, so it is clear at a glance that
#: this one was not drawn here but chosen there.
_LINE_BLOCK = QColor(60, 120, 210, 110)
_LINE_BLOCK_SEL = QColor(60, 120, 210, 190)
_PLAYHEAD = QColor(200, 30, 30)

#: Block types (B282): "demping" = red blocks (attenuate), "herstel" =
#: green blocks ("restore from original", replaces with original audio).
_KIND_DAMPING = "demping"
_KIND_RESTORE = "herstel"
#: Label prefix of a restore fragment that comes from the timing editor
#: (B496); kept equal to ``pipeline.LINE_RESTORE_PREFIX``.
_LINE_PREFIX = "zin "


class DampingCanvas(QWidget):
    """Waveform + time bar + draggable/stretchable damping/restore blocks."""

    def __init__(self, peaks: np.ndarray, duration: float,
                 blocks: list[list],
                 on_seek: Callable[[float], None]) -> None:
        super().__init__()
        self._peaks = peaks
        self._duration = max(duration, 1.0)
        # Each block = [start, end, kind, label]. ``kind`` is _KIND_DAMPING
        # or _KIND_RESTORE; ``label`` is only used for restore blocks.
        self._blocks = blocks
        self._on_seek = on_seek
        self._pps = 60.0
        self._playhead: float | None = None
        self._selected: int | None = None
        self._drag: tuple[int, str, float] | None = None
        self.setMouseTracking(True)
        self.setFixedSize(int(self._duration * self._pps), _CANVAS_H)

    @property
    def pixels_per_second(self) -> float:
        return self._pps

    @property
    def playhead(self) -> float | None:
        return self._playhead

    @property
    def selected(self) -> int | None:
        return self._selected

    def set_zoom(self, pps: float) -> None:
        self._pps = float(np.clip(pps, 8.0, 600.0))
        self.setFixedWidth(int(self._duration * self._pps))
        self.update()

    def set_playhead(self, moment: float | None) -> None:
        self._playhead = moment
        self.update()

    def set_peaks(self, peaks) -> None:
        """Replace the shown waveform (after a new damping pass)."""
        self._peaks = peaks
        self.update()

    def add_block_at_playhead(
            self, kind: str = _KIND_DAMPING,
            label: str = "", length: float = 1.0) -> None:
        start = self._playhead if self._playhead is not None else 0.0
        self._blocks.append(
            [start, min(self._duration, start + length), kind, label])
        self._selected = len(self._blocks) - 1
        self.update()

    def remove_selected(self) -> None:
        if self._selected is not None:
            self._blocks.pop(self._selected)
            self._selected = None
            self.update()

    # -- Drawing -------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        width, height = self.width(), self.height()
        painter.fillRect(0, 0, width, height, QColor(250, 250, 252))

        mid = _WAVE_TOP + _WAVE_H / 2
        columns = waveform.resample_peaks(self._peaks, max(width, 1))
        painter.setPen(QPen(QColor(90, 110, 150)))
        for x in range(width):
            extent = float(columns[x]) * (_WAVE_H / 2 - 6)
            painter.drawLine(x, int(mid - extent), x, int(mid + extent))

        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawLine(0, _AXIS_TOP + 12, width, _AXIS_TOP + 12)
        tick = 10 if self._pps < 40 else (5 if self._pps < 120 else 1)
        second = 0
        while second <= self._duration:
            x = int(second * self._pps)
            painter.drawLine(x, _AXIS_TOP + 6, x, _AXIS_TOP + 18)
            painter.drawText(x + 3, _AXIS_TOP + 28,
                             f"{second // 60}:{second % 60:02d}")
            second += tick

        for index, block in enumerate(self._blocks):
            start, end, kind = block[0], block[1], block[2]
            label = block[3] if len(block) > 3 else ""
            x1, x2 = start * self._pps, end * self._pps
            selected = index == self._selected
            if kind == _KIND_RESTORE and str(label).startswith(
                    _LINE_PREFIX):
                colour = _LINE_BLOCK_SEL if selected else _LINE_BLOCK
                border = QColor(30, 70, 150)
            elif kind == _KIND_RESTORE:
                colour = _RESTORE_BLOCK_SEL if selected else _RESTORE_BLOCK
                border = QColor(20, 120, 40)
            else:
                colour = _BLOCK_SEL if selected else _BLOCK
                border = QColor(150, 30, 20)
            painter.fillRect(int(x1), _BLOCK_TOP, max(3, int(x2 - x1)),
                             _BLOCK_H, colour)
            painter.setPen(QPen(border))
            painter.drawRect(int(x1), _BLOCK_TOP, max(3, int(x2 - x1)),
                             _BLOCK_H)

        if self._playhead is not None:
            x = int(self._playhead * self._pps)
            painter.setPen(QPen(_PLAYHEAD, 2))
            painter.drawLine(x, 0, x, height)
        painter.end()

    # -- Mouse ----------------------------------------------------------

    def _edge_hit(self, x: float, block: list[float]) -> str | None:
        x1, x2 = block[0] * self._pps, block[1] * self._pps
        if abs(x - x1) <= _EDGE_PX:
            return "links"
        if abs(x - x2) <= _EDGE_PX:
            return "rechts"
        if x1 <= x <= x2:
            return "verplaats"
        return None

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        x = event.position().x()
        y = event.position().y()
        if self._drag is None:
            # Cursor feedback: <-> on a stretchable edge.
            on_edge = False
            if _BLOCK_TOP <= y <= _BLOCK_TOP + _BLOCK_H:
                for block in self._blocks:
                    hit = self._edge_hit(x, block)
                    if hit in ("links", "rechts"):
                        on_edge = True
                        break
            self.setCursor(Qt.CursorShape.SizeHorCursor if on_edge
                           else Qt.CursorShape.ArrowCursor)
            return
        index, mode, grabbed = self._drag
        moment = x / self._pps
        delta = moment - grabbed
        if abs(delta) < 0.005:
            return
        block = self._blocks[index]
        if mode == "verplaats":
            width = block[1] - block[0]
            block[0] = max(0.0, block[0] + delta)
            block[1] = block[0] + width
        elif mode == "links":
            block[0] = min(max(0.0, block[0] + delta), block[1] - _MIN_S)
        else:
            block[1] = max(block[1] + delta, block[0] + _MIN_S)
        self._drag = (index, mode, moment)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        x = event.position().x()
        y = event.position().y()
        if _BLOCK_TOP <= y <= _BLOCK_TOP + _BLOCK_H:
            for index, block in enumerate(self._blocks):
                hit = self._edge_hit(x, block)
                if hit is not None:
                    self._selected = index
                    self._drag = (index, hit, x / self._pps)
                    self.update()
                    return
            self._selected = None
            self.update()
            return
        if y <= _AXIS_TOP + 18:
            self._playhead = max(0.0, min(x / self._pps, self._duration))
            self.update()
            self._on_seek(self._playhead)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag = None


class DampingEditorDialog(QDialog):
    """Pop-out window to edit the damping on the waveform."""

    def __init__(self, peaks: np.ndarray, duration: float,
                 intervals: Sequence[tuple[float, float, str]],
                 audio_path: Path | None,
                 on_save: Callable[
                     [list[tuple[float, float]],
                      list[tuple[float, float, str]]], None],
                 restore_intervals: Sequence[tuple[float, float, str]] = (),
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("editor_damping_title"))
        self.setWindowFlags(Qt.WindowType.Window
                            | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowCloseButtonHint)
        self.resize(1150, 380)
        self._on_save = on_save
        self._audio_path = audio_path
        self._restore_counter = 0
        self._blocks: list[list] = [
            [start, end, _KIND_DAMPING, ""] for start, end, _ in intervals]
        self._blocks += [
            [start, end, _KIND_RESTORE, label]
            for start, end, label in restore_intervals]

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        for text, handler in (
                (t("zoom_in"), lambda: self._zoom(1.5)),
                (t("zoom_out"), lambda: self._zoom(1 / 1.5)),
                (t("add_damping"), self._add_block),
                (t("add_restore"), self._add_restore_block),
                (t("remove"), self._remove_block)):
            button = QPushButton(text)
            button.clicked.connect(handler)
            toolbar.addWidget(button)
        self._play_button = QPushButton(t("play"))
        if _MULTIMEDIA and audio_path is not None:
            toolbar.addWidget(self._play_button)
        hint = QLabel(t("editor_damping_hint"))
        hint.setStyleSheet("color: #666;")
        toolbar.addWidget(hint, stretch=1)
        save_button = QPushButton(t("save_apply"))
        close_button = QPushButton(t("close"))
        toolbar.addWidget(save_button)
        toolbar.addWidget(close_button)
        layout.addLayout(toolbar)

        self._canvas = DampingCanvas(peaks, duration, self._blocks,
                                     on_seek=self._seek)
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._canvas)
        self._scroll.setWidgetResizable(False)
        layout.addWidget(self._scroll, stretch=1)

        save_button.clicked.connect(self._save)
        close_button.clicked.connect(self.accept)

        self._player = None
        if _MULTIMEDIA and audio_path is not None:
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_output)
            self._player.setSource(QUrl.fromLocalFile(str(audio_path)))
            self._play_button.clicked.connect(self._toggle_play)
            self._timer = QTimer(self)
            self._timer.setInterval(50)
            self._timer.timeout.connect(self._tick)
            self._timer.start()

    def _zoom(self, factor: float) -> None:
        """Zoom around the playhead (or the middle of the view)."""
        canvas = self._canvas
        bar = self._scroll.horizontalScrollBar()
        viewport = self._scroll.viewport().width()
        if canvas.playhead is not None:
            anchor = canvas.playhead
        else:
            anchor = (bar.value() + viewport / 2) / canvas.pixels_per_second
        canvas.set_zoom(canvas.pixels_per_second * factor)
        bar.setValue(int(anchor * canvas.pixels_per_second - viewport / 2))

    def _add_block(self) -> None:
        self._canvas.add_block_at_playhead(kind=_KIND_DAMPING)

    def _add_restore_block(self) -> None:
        self._restore_counter += 1
        label = f"{t('add_restore')} {self._restore_counter}"
        self._canvas.add_block_at_playhead(kind=_KIND_RESTORE, label=label)

    def _remove_block(self) -> None:
        self._canvas.remove_selected()

    def _seek(self, moment: float, autoplay: bool = False) -> None:
        if self._player is None:
            return
        self._player.setPosition(int(moment * 1000))
        if autoplay:
            self._player.play()
            self._play_button.setText(t("pause"))
        else:
            self._player.pause()
            self._play_button.setText(t("play"))

    def _toggle_play(self) -> None:
        if self._player is None:
            return
        if self._player.playbackState() == \
                QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._play_button.setText(t("play"))
        else:
            self._seek(self._canvas.playhead or 0.0, autoplay=True)

    def _tick(self) -> None:
        if (self._player is None or self._player.playbackState()
                != QMediaPlayer.PlaybackState.PlayingState):
            return
        moment = self._player.position() / 1000.0
        self._canvas.set_playhead(moment)
        self._scroll.ensureVisible(
            int(moment * self._canvas.pixels_per_second), 0, 80, 0)

    def _shutdown_playback(self) -> None:
        """Stop player and timer (on every close path, B93); also release
        the audio file so the cache can be emptied on exit (B205)."""
        if getattr(self, "_player", None) is not None:
            self._player.stop()
            try:
                self._player.setSource(QUrl())
            except Exception:  # noqa: BLE001
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
        spans = [(min(b[0], b[1]), max(b[0], b[1])) for b in self._blocks
                 if b[2] == _KIND_DAMPING and abs(b[1] - b[0]) > _MIN_S / 2]
        restore_spans = [
            (min(b[0], b[1]), max(b[0], b[1]), b[3]) for b in self._blocks
            if b[2] == _KIND_RESTORE and abs(b[1] - b[0]) > _MIN_S / 2]
        result = self._on_save(spans, restore_spans)
        # The callback applies the damping/restore and returns the new
        # waveform.
        if isinstance(result, dict) and result.get("peaks") is not None:
            self._canvas.set_peaks(result["peaks"])
            new_audio = result.get("audio")
            if new_audio is not None and self._player is not None:
                self._audio_path = Path(new_audio)
                self._player.setSource(QUrl.fromLocalFile(str(new_audio)))
