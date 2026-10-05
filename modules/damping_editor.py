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

v1.0.14: blocks no longer slide over one another (B588), the colours
have a legend of their own (B589), and playing lets you hear what the
blocks do before anything is saved (B590): the bare karaoke plays, a
red block turns its volume down, and over a green or blue block the
original takes over, on its own clock through the alignment.
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
#: The same for one word (B587); kept equal to
#: ``pipeline.WORD_RESTORE_PREFIX``.
_WORD_PREFIX = "woord "
#: B590: how often playback looks where it is, and how far the original
#: may drift from where it should be before it is put right.
_TICK_MS = 50
_DRIFT_S = 0.12


def _marked(label: str) -> bool:
    """Was this restore block marked in the timing editor (B496/B587)?"""
    return str(label).startswith((_LINE_PREFIX, _WORD_PREFIX))


def free_gap(blocks: Sequence[Sequence], moment: float, duration: float,
             length: float = 1.0, minimum: float = _MIN_S
             ) -> tuple[float, float] | None:
    """Where a new block goes (B588): the first free stretch from
    ``moment`` on, ``length`` long or shorter when the gap is shorter;
    ``None`` when no gap of at least ``minimum`` is left."""
    taken = sorted((float(b[0]), float(b[1])) for b in blocks)
    cursor = max(0.0, float(moment))
    for start, end in taken:
        if end <= cursor:
            continue
        if start - cursor >= minimum:
            return cursor, min(cursor + length, start)
        cursor = max(cursor, end)
    if duration - cursor >= minimum:
        return cursor, min(cursor + length, duration)
    return None


def block_bounds(blocks: Sequence[Sequence], index: int,
                 duration: float) -> tuple[float, float]:
    """How far block ``index`` may go (B588): from the END of the block
    before it to the START of the block after it, whatever their kind -
    so no block lies over another or passes it - and within the song.
    Before and after go by start time, and by list order on a tie."""
    own = float(blocks[index][0])
    low, high = 0.0, float(duration)
    for other, block in enumerate(blocks):
        if other == index:
            continue
        start, end = float(block[0]), float(block[1])
        if start < own or (start == own and other < index):
            low = max(low, end)
        else:
            high = min(high, start)
    return low, high


def preview_kind(blocks: Sequence[Sequence], moment: float) -> str | None:
    """What playback does at ``moment`` (B590): ``"herstel"`` over a
    restore block (it wins where old blocks still overlap), otherwise
    ``"demping"`` over a damping block, otherwise ``None``."""
    found = None
    for block in blocks:
        if float(block[0]) <= moment < float(block[1]):
            if block[2] == _KIND_RESTORE:
                return _KIND_RESTORE
            found = _KIND_DAMPING
    return found


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

    @property
    def blocks(self) -> list[list]:
        return self._blocks

    def add_block_at_playhead(
            self, kind: str = _KIND_DAMPING,
            label: str = "", length: float = 1.0) -> bool:
        """A new block in the first free gap from the playhead (B588);
        False when there is none."""
        start = self._playhead if self._playhead is not None else 0.0
        gap = free_gap(self._blocks, start, self._duration, length)
        if gap is None:
            return False
        self._blocks.append([gap[0], gap[1], kind, label])
        self._selected = len(self._blocks) - 1
        self.update()
        return True

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
            if kind == _KIND_RESTORE and _marked(label):
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
            # B587: a block marked in the timing editor says what it is
            # - the sentence or the word - so a word block can be found.
            if kind == _KIND_RESTORE and _marked(label):
                text = str(label).split(": ", 1)[-1]
                room = int((x2 - x1) / 7)
                if room > 0:
                    painter.setPen(QPen(QColor(20, 40, 90)))
                    painter.drawText(int(x1) + 3, _BLOCK_TOP + 21,
                                     text[:room])

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
        from .timing_editor import _inside

        block = self._blocks[index]
        if mode == "verplaats":
            span = (block[0] + delta, block[1] + delta)
        elif mode == "links":
            span = (block[0] + delta, block[1])
        else:
            span = (block[0], block[1] + delta)
        # B588: against the neighbours and the end of the song, by the
        # timing editor's own rules: a move slides up against a
        # neighbour, a stretch stops there, and with no room nothing
        # happens.
        low, high = block_bounds(self._blocks, index, self._duration)
        span = _inside(span, low, high, mode, minimum=_MIN_S)
        if span[0] >= low - 1e-9 and span[1] <= high + 1e-9:
            block[0], block[1] = span
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
                 original_path: Path | None = None,
                 to_original: Callable[[float], float] | None = None,
                 damped_volume: float = 0.06,
                 parent=None) -> None:
        """``audio_path`` is the bare karaoke: playback makes the blocks
        audible itself (B590). ``original_path`` and ``to_original`` (a
        karaoke time to its time in the original) let the original take
        over under a restore block; without them only the damping is
        heard. ``damped_volume`` is the volume under a damping block."""
        super().__init__(parent)
        self.setWindowTitle(t("editor_damping_title"))
        self.setWindowFlags(Qt.WindowType.Window
                            | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowCloseButtonHint)
        self.resize(1150, 420)
        self._on_save = on_save
        self._to_original = to_original or (lambda moment: moment)
        self._damped_volume = float(min(max(damped_volume, 0.0), 1.0))
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
        toolbar.addStretch(1)
        save_button = QPushButton(t("save_apply"))
        close_button = QPushButton(t("close"))
        toolbar.addWidget(save_button)
        toolbar.addWidget(close_button)
        layout.addLayout(toolbar)
        # B589: the explanation on a line of its own that wraps, and the
        # colours as a legend in their own colours - in the toolbar it
        # ran out of the window, and it named two colours of three.
        hint = QLabel(t("editor_damping_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)
        legend = QHBoxLayout()
        for key, colour in (("damping_legend_damping", _BLOCK_SEL),
                            ("damping_legend_restore", _RESTORE_BLOCK_SEL),
                            ("damping_legend_marked", _LINE_BLOCK_SEL)):
            swatch = QLabel(t(key))
            swatch.setWordWrap(True)
            swatch.setStyleSheet(
                f"background: rgba({colour.red()},{colour.green()},"
                f"{colour.blue()},90); padding: 2px 6px;"
                " border-radius: 3px;")
            legend.addWidget(swatch)
        legend.addStretch(1)
        layout.addLayout(legend)
        self._message = QLabel("")
        self._message.setStyleSheet("color: #a33;")
        layout.addWidget(self._message)

        self._canvas = DampingCanvas(peaks, duration, self._blocks,
                                     on_seek=self._seek)
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._canvas)
        self._scroll.setWidgetResizable(False)
        layout.addWidget(self._scroll, stretch=1)

        save_button.clicked.connect(self._save)
        close_button.clicked.connect(self.accept)

        self._player = None
        self._original_player = None
        if _MULTIMEDIA and audio_path is not None:
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_output)
            self._player.setSource(QUrl.fromLocalFile(str(audio_path)))
            if original_path is not None and Path(original_path).exists():
                self._original_player = QMediaPlayer(self)
                self._original_output = QAudioOutput(self)
                self._original_output.setVolume(0.0)
                self._original_player.setAudioOutput(self._original_output)
                self._original_player.setSource(
                    QUrl.fromLocalFile(str(original_path)))
            self._play_button.clicked.connect(self._toggle_play)
            self._timer = QTimer(self)
            self._timer.setInterval(_TICK_MS)
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

    def _add(self, kind: str, label: str = "") -> None:
        if self._canvas.add_block_at_playhead(kind=kind, label=label):
            self._message.setText("")
        else:
            self._message.setText(t("damping_no_room"))

    def _add_block(self) -> None:
        self._add(_KIND_DAMPING)

    def _add_restore_block(self) -> None:
        self._restore_counter += 1
        self._add(_KIND_RESTORE,
                  f"{t('add_restore')} {self._restore_counter}")

    def _remove_block(self) -> None:
        self._canvas.remove_selected()

    def _playing(self) -> bool:
        return self._player is not None and self._player.playbackState() \
            == QMediaPlayer.PlaybackState.PlayingState

    def _seek(self, moment: float, autoplay: bool = False) -> None:
        if self._player is None:
            return
        self._player.setPosition(int(moment * 1000))
        if self._original_player is not None:
            self._original_player.setPosition(
                int(max(0.0, self._to_original(moment)) * 1000))
        if autoplay:
            self._player.play()
            if self._original_player is not None:
                self._original_player.play()
            self._play_button.setText(t("pause"))
            self._follow(moment)
        else:
            self._player.pause()
            if self._original_player is not None:
                self._original_player.pause()
            self._play_button.setText(t("play"))

    def _toggle_play(self) -> None:
        if self._player is None:
            return
        if self._playing():
            self._player.pause()
            if self._original_player is not None:
                self._original_player.pause()
            self._play_button.setText(t("play"))
        else:
            self._seek(self._canvas.playhead or 0.0, autoplay=True)

    def _follow(self, moment: float) -> None:
        """B590: make audible what the blocks do at ``moment`` - the
        blocks as they stand now, saved or not."""
        kind = preview_kind(self._canvas.blocks, moment)
        original = self._original_player
        if kind == _KIND_RESTORE and original is not None:
            expected = max(0.0, self._to_original(moment))
            if abs(original.position() / 1000.0 - expected) > _DRIFT_S:
                original.setPosition(int(expected * 1000))
            self._original_output.setVolume(1.0)
            self._audio_output.setVolume(0.0)
            return
        if original is not None:
            self._original_output.setVolume(0.0)
        self._audio_output.setVolume(
            self._damped_volume if kind == _KIND_DAMPING else 1.0)

    def _tick(self) -> None:
        if not self._playing():
            # The karaoke ended (or was paused elsewhere): the original
            # may not play on over a restore block (found in review).
            original = self._original_player
            if original is not None and original.playbackState() == \
                    QMediaPlayer.PlaybackState.PlayingState:
                original.pause()
                self._original_output.setVolume(0.0)
                self._play_button.setText(t("play"))
            return
        moment = self._player.position() / 1000.0
        self._follow(moment)
        self._canvas.set_playhead(moment)
        self._scroll.ensureVisible(
            int(moment * self._canvas.pixels_per_second), 0, 80, 0)

    def _shutdown_playback(self) -> None:
        """Stop player and timer (on every close path, B93); also release
        the audio file so the cache can be emptied on exit (B205)."""
        for player in (getattr(self, "_player", None),
                       getattr(self, "_original_player", None)):
            if player is None:
                continue
            player.stop()
            try:
                player.setSource(QUrl())
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
        # waveform. The player keeps the bare karaoke (B590): the edited
        # one would be damped twice under the live preview.
        if isinstance(result, dict) and result.get("peaks") is not None:
            self._canvas.set_peaks(result["peaks"])
