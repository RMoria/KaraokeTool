"""The helper's own small window (v1.0.23, B640).

The owner's wish: start the helpers with a minimal window instead of a
console, with the program's icon - and a way to stop one after the round
it is on, so a computer can be switched off without throwing an hour of
work away.

The window shows, per lane, what it is doing (waiting, working on which
round and how long that still takes, cooling down), and under that the
lines the lanes write - what the console showed before. Two buttons:

* **Stoppen na huidige taak** - every lane finishes the round it is on
  and takes no new one; then the helper ends. Clicked again before that
  it is taken back.
* **Nu stoppen** - the rounds that run go back into the queue at once,
  for another computer, and the helper ends.

Closing the window asks which of the two. The lanes read the choice from
a file in the helper's folder (``tools/helper.py``), so it reaches them
whatever they are busy with.

v1.0.24: the window is there from the start (B653) - while the helper
still looks for the laptop, its lanes come in when they start - and a
third button, **Helper verwijderen**, stops the helper and takes it off
this computer (B655).
"""
from __future__ import annotations

import queue as queue_module
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .translations import t

_ROOT = Path(__file__).resolve().parents[1]
#: How many lines the window keeps.
MAX_LINES = 3000


def icon() -> QIcon:
    for name in ("karaoketool.ico", "karaoketool.png"):
        candidate = _ROOT / "assets" / "icons" / name
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


def _own_taskbar_icon() -> None:
    """Windows shows pythonw's icon on the taskbar unless the process has
    an id of its own; then it takes the window's icon."""
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "RoodWitteZangers.KaraokeTool.Helper")
        except Exception:  # noqa: BLE001 - nice-to-have
            pass


def _left(seconds) -> str:
    if seconds is None:
        return ""
    minutes = int(round(float(seconds) / 60.0))
    if minutes < 1:
        return t("duration_under_minute")
    hours, minutes = divmod(minutes, 60)
    return t("duration_hours").format(hours=hours, minutes=minutes) \
        if hours else t("duration_minutes").format(minutes=minutes)


class HelperWindow(QWidget):
    """What the helper does, and the two ways to stop it."""

    def __init__(self, title: str, lanes, status_of:
                 Callable[[str], dict | None], lines: "queue_module.Queue",
                 finish: Callable[[bool], None], stop_now: Callable[[], None],
                 finished: Callable[[], bool],
                 remove: Callable[[], None] | None = None,
                 ended: Callable[[], bool] | None = None) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.setWindowIcon(icon())
        # v1.0.24: the lanes may come in later (a list, or what gives it).
        self._lanes_of = lanes if callable(lanes) else (lambda: lanes)
        self._lanes: list[str] = []
        self._status_of = status_of
        self._lines = lines
        self._finish = finish
        self._stop_now = stop_now
        self._finished = finished
        self._remove = remove
        self._ended = ended or (lambda: False)
        self._ended_said = False
        self._finishing = False
        self._stopping = False
        outer = QVBoxLayout(self)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(
            [t("helper_col_lane"), t("helper_col_state"),
             t("helper_col_job")])
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        outer.addWidget(self._table)
        self._lanes_changed()
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(MAX_LINES)
        outer.addWidget(self._log, stretch=1)
        row = QHBoxLayout()
        self._note = QLabel("")
        row.addWidget(self._note, stretch=1)
        self._finish_button = QPushButton(t("helper_finish"))
        self._finish_button.clicked.connect(self._toggle_finish)
        row.addWidget(self._finish_button)
        self._stop_button = QPushButton(t("helper_stop_now"))
        self._stop_button.clicked.connect(self._ask_stop_now)
        row.addWidget(self._stop_button)
        self._remove_button = QPushButton(t("helper_remove"))
        self._remove_button.clicked.connect(self._ask_remove)
        self._remove_button.setVisible(remove is not None)
        row.addWidget(self._remove_button)
        outer.addLayout(row)
        self.resize(760, 460)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)
        self._status_every = 0

    # -- what happens --------------------------------------------------------

    def add_line(self, text: str) -> None:
        self._log.appendPlainText(str(text).rstrip())

    def _lanes_changed(self) -> None:
        lanes = list(self._lanes_of() or ())
        if lanes == self._lanes:
            return
        self._lanes = lanes
        self._table.setRowCount(len(lanes))
        for row, lane in enumerate(lanes):
            self._table.setItem(row, 0, QTableWidgetItem(
                t(f"helper_lane_{lane}")))
        self._table.setMaximumHeight(40 + 30 * max(1, len(lanes)))

    def _tick(self) -> None:
        for _n in range(500):
            try:
                self.add_line(self._lines.get_nowait())
            except queue_module.Empty:
                break
        self._status_every -= 1
        if self._status_every <= 0:
            self._status_every = 4            # every two seconds
            self._lanes_changed()
            self.show_status()
        if self._ended() and not self._ended_said:
            # The helper stopped by itself: the window stays, to be read,
            # and closes without a question.
            self._ended_said = True
            self._stopping = True
            self._note.setText(t("helper_ended_note"))
            for button in (self._finish_button, self._stop_button):
                button.setEnabled(False)
        if self._finished():
            self._timer.stop()
            self.close_quietly()

    def show_status(self) -> None:
        for row, lane in enumerate(self._lanes):
            try:
                status = self._status_of(lane) or {}
            except (OSError, ValueError):
                status = {}
            state = str(status.get("state") or "-")
            left = _left(status.get("left_s")) if state == "working" else ""
            self._table.setItem(row, 1, QTableWidgetItem(
                t(f"helper_state_{state}") if state != "-" else "-"))
            label = str(status.get("job") or "")
            if left:
                label += f"  ({t('helper_left').format(left=left)})"
            self._table.setItem(row, 2, QTableWidgetItem(label))

    # -- stopping ------------------------------------------------------------

    def _toggle_finish(self) -> None:
        self._finishing = not self._finishing
        self._finish(self._finishing)
        self._finish_button.setText(t("helper_finish_undo") if self._finishing
                                    else t("helper_finish"))
        self._note.setText(t("helper_finish_note") if self._finishing
                           else "")

    def _ask_stop_now(self) -> None:
        answer = QMessageBox.question(self, t("helper_stop_now"),
                                      t("helper_stop_now_ask"))
        if answer == QMessageBox.StandardButton.Yes:
            self._now()

    def _ask_remove(self) -> None:
        answer = QMessageBox.question(self, t("helper_remove"),
                                      t("helper_remove_ask"))
        if answer != QMessageBox.StandardButton.Yes or self._remove is None:
            return
        self._remove()
        self._stopping = True
        self._note.setText(t("helper_removing_note"))
        for button in (self._finish_button, self._stop_button,
                       self._remove_button):
            button.setEnabled(False)

    def _now(self) -> None:
        self._stopping = True
        self._stop_now()
        self._note.setText(t("helper_stopping_note"))
        self._finish_button.setEnabled(False)
        self._stop_button.setEnabled(False)

    def close_quietly(self) -> None:
        self._stopping = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt's name
        if self._stopping or self._finished():
            event.accept()
            return
        app = QApplication.instance()
        if app is not None and app.isSavingSession():
            # Windows shuts down: no question that would hold it up; the
            # rounds go back into the queue.
            self._now()
            event.accept()
            return
        box = QMessageBox(self)
        box.setWindowTitle(t("helper_close_title"))
        box.setText(t("helper_close_ask"))
        after = box.addButton(t("helper_finish"),
                              QMessageBox.ButtonRole.AcceptRole)
        now = box.addButton(t("helper_stop_now"),
                            QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is after:
            if not self._finishing:
                self._toggle_finish()
        elif clicked is now:
            self._now()
        event.ignore()          # the window goes when the lanes are done


def run(title: str, lanes, status_of, lines, finish, stop_now,
        finished, remove=None, ended=None) -> None:
    """Show the window until the lanes are done."""
    _own_taskbar_icon()
    app = QApplication.instance() or QApplication([])
    app.setWindowIcon(icon())
    window = HelperWindow(title, lanes, status_of, lines, finish, stop_now,
                          finished, remove, ended)
    window.show()
    # The start file runs minimized, and Windows gives its way of showing
    # to the first window it opens; the second time counts.
    window.showNormal()
    window.raise_()
    window.activateWindow()
    app.exec()
