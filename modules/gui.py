"""Graphical interface (PySide6) on top of the same pipeline as the menu.

Features: file chooser for missing input files (the chosen file is
copied to ``input``; the original stays where it is), the pipeline steps
as buttons, a progress bar for Whisper and cluster selection directly in
the window. Long steps run in a background thread so that the window
does not freeze.
"""

from __future__ import annotations

import logging
import shutil
import sys
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import (
    QObject, QRectF, QSettings, QSize, QThread, QTimer, Signal,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFrame,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QStackedWidget,
    QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from . import __version__
from . import audio as audio_module
from . import cluster as cluster_module
from . import filesystem, models, pipeline, translations, waveform, whisper
from .translations import t
from . import config as config_module
from .pipeline import AppContext, AnalyseResult, PipelineError

logger = logging.getLogger(__name__)

#: B477: which outline setting belongs to which text colour. The video
#: background gets none - that is not a letter. "After the singing" does
#: have one: on the ACTIVE line that colour is still being read. A line
#: that is wholly behind us gets no outline at all; that is decided in
#: ``_draw_line``, not here.
_OUTLINE_OF = {"color_before": "outline_before",
               "color_vocal": "outline_vocal",
               "color_after": "outline_after",
               "color_crowd": "outline_crowd"}

#: Shared minimum height for Sound clusters/Damped fragments (B284): they
#: alternate in the same QStackedWidget slot and must therefore be equal
#: in size, otherwise the window jumps when switching.
_CLUSTER_FRAGMENT_MIN_H = 140


def _app_icon() -> QIcon:
    """The app icon (window title + Windows taskbar); empty if missing."""
    icons = Path(__file__).resolve().parent.parent / "assets" / "icons"
    for name in ("karaoketool.ico", "karaoketool.png"):
        candidate = icons / name
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


#: Task for the background thread: (progress, message) -> result.
Task = Callable[[Callable[[float, float], None], Callable[[str], None]], Any]


class _LogBridge(QObject):
    """Bridge that sends log lines (thread-safe) to the GUI."""

    message = Signal(str)


class _QtLogHandler(logging.Handler):
    """Logging handler that mirrors records to the GUI activity panel.

    The ``emit`` may come from a background thread; via a Qt signal the
    text is appended on the GUI thread (queued connection).
    """

    def __init__(self, bridge: "_LogBridge") -> None:
        super().__init__()
        self._bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._bridge.message.emit(self.format(record))
        except Exception:  # noqa: BLE001 - logging must never crash
            pass


class _Worker(QThread):
    """Runs one pipeline task in a background thread."""

    progress = Signal(float, float)
    message = Signal(str)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, task: Task) -> None:
        super().__init__()
        self._task = task

    def run(self) -> None:  # noqa: D102 - Qt interface
        try:
            self.done.emit(self._task(self.progress.emit,
                                      self.message.emit))
        except whisper.CancelledError:
            logger.info(t("log_task_cancelled"))
            self.cancelled.emit()
        except PipelineError as exc:
            self.failed.emit(str(exc))
        # B359: BaseException, not Exception. SystemExit and
        # KeyboardInterrupt do NOT inherit from Exception, so those
        # slipped past here - and then none of the three signals is sent,
        # _set_busy(False) never happens and the GUI hangs on "busy"
        # forever while nothing is running (no CPU, no error, no log
        # line). Better an ugly message than a dead window.
        except BaseException as exc:  # noqa: BLE001 - report everything
            logger.exception(t("log_task_error"))
            self.failed.emit(t("task_failed").format(exc=exc))


class _TrackProgressBridge(QObject):
    """Bridge for per-track progress from (parallel) background threads.

    The bridge lives on the GUI thread; parallel detection tasks call
    :pyattr:`progress` (``track, verwerkte_s, totaal_s``) and Qt delivers
    that safely on the GUI thread via a queued connection (B90).
    """

    progress = Signal(str, float, float)
    done = Signal(str)


class WaveformWidget(QWidget):
    """Draws the waveform of the edited karaoke with damped fragments.

    (Prepared for a later extension: clicking and adding extra
    regions.)
    """

    def __init__(self) -> None:
        super().__init__()
        self._peaks: np.ndarray | None = None
        self._duration = 0.0
        self._intervals: list[tuple[float, float]] = []
        self.setMinimumHeight(130)

    def set_data(self, peaks: np.ndarray, duration: float,
                 intervals: list[tuple[float, float]]) -> None:
        """Fill the view with peaks, duration and damped fragments."""
        self._peaks = peaks
        self._duration = max(duration, 0.001)
        self._intervals = intervals
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt interface
        painter = QPainter(self)
        width, height = self.width(), self.height()
        painter.fillRect(0, 0, width, height, QColor(250, 250, 252))
        if self._peaks is None or width < 10:
            painter.setPen(QPen(QColor(150, 150, 150)))
            painter.drawText(12, height // 2, t("waveform_after_step4"))
            painter.end()
            return

        # Damped fragments (red, behind the waveform)
        for start, end in self._intervals:
            x1 = start / self._duration * width
            x2 = end / self._duration * width
            painter.fillRect(QRectF(x1, 2, max(2.0, x2 - x1), height - 18),
                             QColor(220, 60, 50, 70))

        # Waveform
        mid = (height - 14) / 2.0
        columns = waveform.resample_peaks(self._peaks, width)
        painter.setPen(QPen(QColor(90, 110, 150)))
        for x in range(width):
            extent = float(columns[x]) * (mid - 4)
            painter.drawLine(x, int(mid - extent), x, int(mid + extent))

        # Time markers every 30 s
        painter.setPen(QPen(QColor(130, 130, 130)))
        seconds = 30
        while seconds < self._duration:
            x = int(seconds / self._duration * width)
            painter.drawLine(x, height - 14, x, height - 10)
            painter.drawText(x + 2, height - 2,
                             f"{seconds // 60}:{seconds % 60:02d}")
            seconds += 30
        painter.end()


class MainWindow(QMainWindow):
    """Main window of Karaoke Tool."""

    #: Progress of one work slot in the test panel (B357, TIJDELIJK).
    #: A signal and not a direct call: the message comes from a worker
    #: thread and Qt widgets may only be touched from the GUI thread.
    _test_progress = Signal(int, str, int, int)
    #: B369: result of one action (code, text), as soon as it is done.
    _test_result = Signal(str, str)

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self._test_progress.connect(self._on_test_progress)
        self._test_result.connect(self._on_test_result)
        # Load the active project's titles from project.json (B210) - but
        # only if a project is really active. The app starts on an empty
        # project (B111); then the title fields should be empty, not show
        # the last project (B237).
        if context.config.song.title:
            self._context = pipeline.apply_project_titles(context)
            pipeline.migrate_input_names(self._context)   # B324
        else:
            from dataclasses import replace as _replace
            self._context = _replace(context, config=_replace(
                context.config, video=_replace(
                    context.config.video,
                    **{k: "" for k in pipeline.VIDEO_TITLE_KEYS})))
        self._worker: _Worker | None = None
        self._phase_text = ""
        self._phase_start = 0.0
        # B368: whether the seconds counter may refresh. That used to
        # hang off ``self._progress.maximum() == 0``, but that widget IS
        # the first test bar - the moment the test panel put a project
        # counter on it (B357) the clock stood still, and that read as a
        # hang.
        self._show_elapsed = False
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._analyse_results: dict[str, AnalyseResult] = {}
        self._cluster_boxes: list[tuple[QCheckBox, str, int]] = []
        self._extra_labels: dict[str, QLabel] = {}

        self.setWindowTitle(f"{t('app_title')} v{__version__}")
        self.setWindowIcon(_app_icon())     # top left in the title bar
        # Remember the window size between sessions; the first time the
        # default size (B187).
        self._settings = QSettings("KaraokeTool", "KaraokeTool")
        geo = self._settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1100, 900)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self._build_song_group())

        # Audio editing and video are separate workflows; adjusting the
        # karaoke sound is not always needed.
        tabs = QTabWidget()
        audio_tab = QWidget()
        audio_layout = QVBoxLayout(audio_tab)
        # Titles left of the input files (B171); the Options block is gone
        # (analysis always runs on original + karaoke) (B174).
        top_row = QHBoxLayout()
        top_row.addWidget(self._build_titles_group())
        top_row.addWidget(self._build_input_group(), stretch=1)
        audio_layout.addLayout(top_row)
        audio_layout.addWidget(self._build_steps_group())
        audio_layout.addWidget(self._build_progress_group())
        audio_layout.addWidget(self._build_waveform_group())
        # Sound clusters and Damped fragments are NEVER both shown at the
        # same time (B283/B284): it is one phase (before step 4) or the
        # other (after step 4). They therefore sit in the same slot in a
        # QStackedWidget instead of as two separate widgets below each
        # other - this way the outside (size/stretch) does not change when
        # switching, only the inside, and the window no longer jumps.
        self._cluster_fragment_stack = QStackedWidget()
        self._cluster_fragment_stack.addWidget(self._build_cluster_group())
        self._cluster_fragment_stack.addWidget(self._build_fragment_group())
        audio_layout.addWidget(self._cluster_fragment_stack, stretch=1)
        tabs.addTab(audio_tab, t("tab_audio"))
        self._video_tab_index = tabs.addTab(self._build_video_tab(),
                                            t("tab_video"))
        # Settings can be long; now that the whole-window scroll is gone
        # (B216), this tab gets its own scroll bar.
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.setWidget(self._build_settings_tab())
        self._settings_tab_index = tabs.addTab(settings_scroll,
                                               t("tab_settings"))
        # Manual to the right of Settings (B165).
        self._help_tab_index = tabs.addTab(self._build_help_tab(),
                                           t("tab_help"))
        # When opening the settings, read the font list from assets/fonts
        # again, so that new fonts appear automatically (B102).
        tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs = tabs  # stored so that _switch_instance (B262) can
        # switch back to the first tab on every project change.
        layout.addWidget(tabs, stretch=1)

        self._log_group = self._build_log_group()
        layout.addWidget(self._log_group)
        # No whole-window scroll anymore: it used the preferred height of
        # the content, so the flexible sound cluster field never shrank
        # along (B216). Now the normal window layout sets the size: the
        # cluster field (the only stretch block) grows/shrinks with the
        # window. A modest window minimum keeps the rest readable on
        # small screens.
        self.setCentralWidget(central)
        # The window minimum stays deliberately BELOW what the layout
        # needs, so that shrinking afterwards is allowed (B216). The
        # starting size is set separately - see ``_apply_startup_size``.
        self.setMinimumSize(760, 520)
        self._apply_startup_size(restored=geo is not None)   # B322
        self._refresh_inputs()
        self._apply_theme()
        self._install_busy_indicator()   # buttons 'yellow' while busy (B229)

    # -- Construction ----------------------------------------------------

    def _apply_startup_size(self, restored: bool) -> None:
        """Start at least as large as the content needs (B322).

        The window remembers its size between sessions (B187) and the
        minimum stands at 520 high, so that shrinking stays possible. The
        layout itself needs 807. Between those two the window fits, but
        the group boxes do not: at 520 the input block gets 54 pixels for
        four rows of thirty, and then the labels are drawn over each
        other. Measured per window height, the input block gets 54 / 90 /
        140 / 175 pixels at 520 / 600 / 700 / 800 - from about 800
        everything fits.

        The starting size is therefore raised to what the layout asks
        for, capped to what fits on the screen (``availableGeometry``
        already leaves the Windows taskbar out). Deliberately only at
        startup: raising the MINIMUM would make it impossible to shrink,
        and that is allowed to stay possible.
        """
        needed = self.centralWidget().layout().minimumSize()
        wanted = self.centralWidget().layout().sizeHint()
        screen = self.screen() or QApplication.primaryScreen()
        room = screen.availableGeometry() if screen is not None else None
        current = self.size()
        width = max(current.width(), needed.width())
        height = max(current.height(), wanted.height())
        if room is not None:
            width = min(width, room.width())
            height = min(height, room.height())
        if width != current.width() or height != current.height():
            self.resize(width, height)
            logger.info(t("log_startup_size"),
                        current.width(), current.height(), width, height,
                        "hersteld" if restored else "standaard")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt interface
        """Store the window size on closing (B187), and let the workers
        go (B401).

        Nine measuring processes that outlive their window are orphans
        nobody sees any more except in the task manager. The atexit hook
        in ``measure_pool`` is the safety net; this is the ordinary way.
        """
        try:
            self._settings.setValue("geometry", self.saveGeometry())
        except Exception:  # noqa: BLE001 - saving must never break closing
            pass
        try:
            from . import measure_pool
            measure_pool.close_pool()
        except Exception:  # noqa: BLE001 - opruimen mag sluiten niet breken
            pass
        super().closeEvent(event)

    def _build_song_group(self) -> QGroupBox:
        group = QGroupBox(t("song_group"))
        layout = QHBoxLayout(group)
        layout.addWidget(QLabel(t("song_label")))
        self._song_combo = QComboBox()
        self._refresh_song_titles()
        # Apply immediately on a user selection; the programmatic
        # refilling in _refresh_song_titles happens under blockSignals, so
        # that does not trigger this (no loop). An "Open" button is
        # superfluous (B95a).
        self._song_combo.textActivated.connect(
            lambda _text: self._open_selected_project())
        layout.addWidget(self._song_combo, stretch=1)
        new_button = QPushButton(t("new_project"))
        new_button.clicked.connect(self._new_project)
        layout.addWidget(new_button)
        self._delete_button = QPushButton(t("delete_project"))
        self._delete_button.clicked.connect(self._delete_project)
        self._delete_button.setEnabled(bool(self._context.config.song.title))
        layout.addWidget(self._delete_button)
        return group

    def _ask_yes_no(self, title: str, text: str) -> bool:
        """Yes/No question with translated buttons (Qt would otherwise
        show Yes/No, B116)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        yes = box.addButton(t("yes"), QMessageBox.ButtonRole.YesRole)
        box.addButton(t("no"), QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(yes)
        box.exec()
        return box.clickedButton() is yes

    def _ask_video_done(self, title: str, text: str) -> str:
        """Video-done question with three buttons (B267): "Open video",
        "Open folder", "Close". Returns ``"video"``, ``"folder"`` or
        ``"close"``."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        video_btn = box.addButton(t("open_video_button"),
                                  QMessageBox.ButtonRole.AcceptRole)
        folder_btn = box.addButton(t("open_folder_button"),
                                   QMessageBox.ButtonRole.ActionRole)
        box.addButton(t("close"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(video_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is video_btn:
            return "video"
        if clicked is folder_btn:
            return "folder"
        return "close"

    def _ask_video_exists(self, target: Path):
        """There is already a render with this name (B354).

        Returns the path to write to, or ``None`` when the user
        cancels. "Keep side by side" numbers the NEW file, so the file
        already there is never touched.

        B490: "Overwrite" takes the LAST video of this project, not the
        one without a number. After a couple of renders side by side the
        newest one is ``_3``, and overwriting the very first render is
        never what is meant by "do it again".
        """
        following = pipeline.next_video_target(target)
        existing = pipeline.existing_videos(self._context, like=target)
        newest = existing[-1] if existing else target
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(t("video_exists_title"))
        box.setText(t("video_exists_body").format(name=newest.name,
                                                  next=following.name))
        beside = box.addButton(t("video_keep_both"),
                               QMessageBox.ButtonRole.AcceptRole)
        over = box.addButton(t("video_overwrite"),
                             QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(t("video_cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(beside)
        box.exec()
        clicked = box.clickedButton()
        if clicked is beside:
            return following
        if clicked is over:
            return newest
        return None

    def _delete_project(self) -> None:
        """Delete the active project after confirmation (B84)."""
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, t("app_title"),
                                    t("busy_step_body"))
            return
        title = self._context.config.song.title
        if not title:
            return
        if not self._ask_yes_no(
                t("delete_project_title"),
                t("delete_project_confirm").format(title=title)):
            return
        try:
            pipeline.delete_project(self._context)
        except PipelineError as exc:
            QMessageBox.warning(self, t("delete_project_title"), str(exc))
            return
        self._log(t("project_deleted_log").format(title=title))
        # Back to no-project (root).
        self._switch_instance("", is_new=False)

    def _change_language(self) -> None:
        """Store the chosen interface language (applied on restart)."""
        code = self._language_combo.currentData()
        config = self._context.config
        if code == config.interface.language:
            return
        self._update_config(
            replace(config, interface=replace(config.interface, language=code)))
        translations.set_language(code)
        QMessageBox.information(self, t("app_title"), t("lang_saved"))

    def _refresh_song_titles(self) -> None:
        """Fill the dropdown with existing song projects."""
        input_root = self._context.paths.input_root
        titles = sorted(entry.name for entry in input_root.iterdir()
                        if entry.is_dir()) if input_root.exists() else []
        current = self._context.config.song.title
        if current and current not in titles:
            titles.append(current)
        self._song_combo.blockSignals(True)
        self._song_combo.clear()
        self._song_combo.addItem(t("no_title"))
        self._song_combo.addItems(titles)
        self._song_combo.setCurrentText(current or t("no_title"))
        self._song_combo.blockSignals(False)
        if hasattr(self, "_delete_button"):
            self._delete_button.setEnabled(bool(current))

    def _open_selected_project(self) -> None:
        """Switch to the chosen existing project (or the root)."""
        choice = self._song_combo.currentText()
        title = "" if choice == t("no_title") else filesystem.safe_name(
            choice)
        self._switch_instance(title, is_new=False)

    def _new_project(self) -> None:
        """Create a new, empty song project and switch to it."""
        name, ok = QInputDialog.getText(self, t("new_project_title"),
                                        t("new_project_prompt"))
        if not ok or not name.strip():
            return
        title = filesystem.safe_name(name)
        if not title:
            QMessageBox.information(self, t("new_project_title"),
                                    t("new_project_invalid_title"))
            return
        # Store the typed name (with spaces) as display name for the
        # video title; the folder name stays the safe _-variant (B70).
        self._switch_instance(title, is_new=True, display_name=name.strip())

    def _switch_instance(self, title: str, is_new: bool,
                         display_name: str = "") -> None:
        """Switch to a project instance without moving files.

        Every song title is an independent project with its own input,
        output and cache folder. If the folder already exists, work
        continues with it; otherwise an empty project starts.
        """
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                self, t("busy_switch_title"), t("busy_switch_body"))
            return
        config = self._context.config
        if title == config.song.title:
            self._log(t("project_already_active").format(
                title=title or t("no_title")))
            return
        old_paths = self._context.paths
        old_title = config.song.title
        new_paths = filesystem.ProjectPaths(
            root=old_paths.root, song=title,
            output_base=old_paths.output_base)   # own output folder (B214)
        existed = new_paths.input_dir.exists() or new_paths.output_dir.exists()
        if is_new and existed and title:
            if not self._ask_yes_no(
                    t("project_exists_title"),
                    t("project_exists_body").format(title=title)):
                return
        filesystem.ensure_directories(new_paths)

        # Only when you started without a title and now create a NEW,
        # empty project: move the loose root files here.
        moved = 0
        if old_title == "" and title != "" and not existed:
            moved = self._migrate_root_into(old_paths, new_paths)

        # Titles belong to the project (B210): start empty so that nothing
        # of the previous project lingers; project.json refills them soon.
        leeg_titels = {k: "" for k in pipeline.VIDEO_TITLE_KEYS}
        new_config = replace(config, song=replace(config.song, title=title),
                             video=replace(config.video, **leeg_titels))
        config_module.save_config(new_config, old_paths.config_file)
        # B445: without a title this is the record of no project at all,
        # and it lands in output/settings/. Reading yes, writing no -
        # otherwise switching back to "no song" recreates exactly the
        # loose file the start warns about.
        new_store = filesystem.ProjectStore(new_paths.project_file,
                                            writable=bool(title))
        if display_name and title:
            new_store.set_meta("display_name", display_name)
        if moved:
            new_store.rewrite_prefix(old_paths.input_dir, new_paths.input_dir)
            new_store.rewrite_prefix(old_paths.output_dir,
                                     new_paths.output_dir)
            new_store.rewrite_prefix(old_paths.cache_dir, new_paths.cache_dir)
            # Clean up leftover empty folders of the title-less root
            # (B60): e.g. the empty output/settings and the empty cache.
            for leftover in (old_paths.settings_dir, old_paths.output_dir,
                             old_paths.cache_dir, old_paths.input_dir):
                filesystem.remove_empty_tree(leftover)
        self._context = replace(self._context, config=new_config,
                                paths=new_paths, store=new_store)
        # Load per-project titles (B210); then prefill the karaoke title
        # if it is still empty (also per project) (B185, one-way).
        self._context = pipeline.apply_project_titles(self._context)
        pipeline.migrate_input_names(self._context)      # B324
        if title and not self._context.config.video.karaoke_title.strip():
            voor = (display_name or title.replace("_", " ")).strip()
            self._context = replace(self._context, config=replace(
                self._context.config, video=replace(
                    self._context.config.video, karaoke_title=voor)))
            pipeline.set_project_title(self._context, "karaoke_title", voor)
        # Verify that all paths/project.json belong to the right subdir
        # (B95b); on a mismatch we warn instead of silently continuing.
        ok, message = pipeline.check_project_paths(self._context)
        if not ok:
            logger.warning(t("log_project_switch"), message)
            QMessageBox.warning(self, t("app_title"), message)
        self._reset_project_view()
        self._refresh_song_titles()
        self._refresh_inputs()
        self._show_timing_lines()
        # B262: on every project change (new and existing project) back
        # to the first tab ("Audio"), so that you do not stay on e.g.
        # Settings/Manual while the workflow of the new project starts
        # precisely at the input files.
        if hasattr(self, "_tabs"):
            self._tabs.setCurrentIndex(0)
        state = (t("project_state_opened") if existed
                 else t("project_state_new"))
        extra = (t("project_moved_extra").format(count=moved)
                 if moved else "")
        self._log(t("project_opened_log").format(
            title=title or t("no_title"), state=state, extra=extra))

    def _migrate_root_into(self, old_paths, new_paths) -> int:
        """Move loose files from the title-less root into the project.

        Only input/output/cache files (no subfolders, no LEESMIJ.txt).
        Happens exclusively from the root to a new project, never
        between existing projects.
        """
        moved = 0
        pairs = ((old_paths.input_dir, new_paths.input_dir),
                 (old_paths.output_dir, new_paths.output_dir),
                 (old_paths.cache_dir, new_paths.cache_dir))
        for source, target in pairs:
            if source == target or not source.exists():
                continue
            target.mkdir(parents=True, exist_ok=True)
            for item in sorted(source.iterdir()):
                if item.is_file() and item.name != "LEESMIJ.txt":
                    try:
                        shutil.move(str(item), str(target / item.name))
                        moved += 1
                    except OSError:
                        logger.exception(t("log_move_failed"), item)
        return moved

    def _reset_project_view(self) -> None:
        """Clear views that belonged to the previous project."""
        self._analyse_results = {}
        self._cluster_boxes = []
        while self._cluster_layout.count():
            item = self._cluster_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._cluster_layout.addStretch()
        self._open_report_button.setEnabled(False)
        # Sound clusters is on again by default when (re)opening a
        # project - it only disappears once "Damped fragments" becomes
        # active (step 4 has run), not already at the opening itself
        # (B283).
        self._show_cluster_group()
        self._waveform_group.setVisible(False)
        self._timing_list.clear()
        # B478/B480: the video button and the background belong to the
        # project, not to the session.
        self._refresh_video_button()
        if getattr(self, "_bg_label", None) is not None:
            self._refresh_background_view()

    def _show_cluster_group(self) -> None:
        """Show "Sound clusters" instead of "Damped fragments" (B284)."""
        self._cluster_fragment_stack.setCurrentWidget(self._cluster_group)

    def _show_fragment_group(self) -> None:
        """Show "Damped fragments" instead of "Sound clusters" (B284)."""
        self._cluster_fragment_stack.setCurrentWidget(self._fragment_group)

    def _build_video_tab(self) -> QWidget:
        """Tab for the karaoke video (separate from the audio editing)."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        actions = QGroupBox(t("video_prep_group"))
        actions_layout = QHBoxLayout(actions)
        # Order: first edit stress, then refine timing (which takes the
        # stress along), then edit timing (B200). 'Check video input' is
        # gone (B178); every button checks its own requirements itself.
        stress_button = QPushButton(t("video_edit_stress"))
        stress_button.clicked.connect(self._open_klemtoon_editor)
        actions_layout.addWidget(stress_button)
        timing_button = QPushButton(t("video_timing"))
        timing_button.clicked.connect(self._do_generate_timing)
        actions_layout.addWidget(timing_button)
        editor_button = QPushButton(t("video_edit_timing"))
        editor_button.clicked.connect(self._open_timing_editor)
        actions_layout.addWidget(editor_button)
        render_button = QPushButton(t("video_render"))
        render_button.clicked.connect(self._do_render_video)
        actions_layout.addWidget(render_button)
        self._open_video_button = QPushButton(t("open_video"))
        self._open_video_button.setEnabled(False)
        self._open_video_button.clicked.connect(self._open_last_video)
        actions_layout.addWidget(self._open_video_button)
        # B532: everything that is finished together in one folder, to
        # hand over. Only useful once there is something to collect, so
        # the button follows the output folder just like "Open video".
        self._collect_button = QPushButton(t("video_collect"))
        self._collect_button.setEnabled(False)
        self._collect_button.clicked.connect(self._do_collect_videos)
        actions_layout.addWidget(self._collect_button)
        actions_layout.addStretch()
        layout.addWidget(actions)

        # B278: own progress bar + status on this tab itself, so that the
        # progress of 'Make video' is also visible without having to
        # switch to the Audio tab. Fed by the same callback as the bar
        # there (_on_progress/_on_message/_set_busy keep them in sync);
        # no separate background-task wiring needed.
        video_progress_row = QHBoxLayout()
        video_progress_row.setContentsMargins(0, 0, 0, 0)
        self._video_progress = QProgressBar()
        self._video_progress.setRange(0, 100)
        self._video_progress.setValue(0)
        self._video_status = QLabel(t("ready"))
        video_progress_row.addWidget(self._video_progress, stretch=1)
        video_progress_row.addWidget(self._video_status, stretch=1)
        layout.addLayout(video_progress_row)

        timing_group = QGroupBox(t("video_timing_group"))
        timing_layout = QVBoxLayout(timing_group)
        self._timing_list = QPlainTextEdit()
        self._timing_list.setReadOnly(True)
        timing_layout.addWidget(self._timing_list)
        layout.addWidget(timing_group, stretch=1)
        return tab

    def _show_timing_lines(self) -> None:
        """Show the karaoke text coloured by timing confidence."""
        from . import timing as timing_module
        timing_path = self._context.paths.timing_file
        if not timing_path.exists():
            return
        try:
            timed = pipeline.mark_inline_pieces(
                self._context, timing_module.load_timing(timing_path))
        except (OSError, ValueError, KeyError):
            self._log(t("timing_unreadable"))
            return
        colors = {"high": "#1b7f3b", "syllable": "#1b7f3b",
                  "medium": "#b8860b", "word": "#b8860b"}
        rows = []
        for line in sorted(timed, key=lambda item: item.index):
            color = colors.get(line.quality, "#b3261e")
            crowd = " [crowd]" if line.crowd else ""
            rows.append(
                f'<span style="color:{color};">'
                f"{_format_time(line.start)} - {_format_time(line.end)}  "
                f"{_escape_html(line.text)}{crowd}</span>")
        self._timing_list.clear()
        self._timing_list.appendHtml("<br>".join(rows))
        self._timing_list.moveCursor(
            self._timing_list.textCursor().MoveOperation.Start)

    def _do_generate_timing(self) -> None:
        """Build the timing skeleton in the background."""
        self._commit_pending_field()
        context = self._context

        def task(progress: Any, message: Any) -> tuple:
            message(t("timing_making"))
            return pipeline.generate_timing(context)

        def on_done(result: tuple) -> None:
            target, count, detail = result
            self._log(t("timing_made").format(
                target=target, count=count, detail=detail))
            # B235: did the timing fall back to even spacing (no
            # transcription/coupling)? Then warn instead of silently
            # showing everything in red. B326: compare against the same
            # translated text, not against a Dutch fragment.
            if detail == t("timing_detail_even"):
                QMessageBox.warning(self, t("timing_fallback_title"),
                                    t("timing_fallback_body"))
            self._show_timing_lines()

        self._run(task, on_done)

    def _open_klemtoon_editor(self) -> None:
        """Open the stress editor on the stored timing (B151)."""
        self._commit_pending_field()
        from . import timing as timing_module
        from .stress_editor import KlemtoonEditorDialog
        context = self._context
        timing_path = context.paths.timing_file
        if not timing_path.exists():
            QMessageBox.information(self, t("prereq_title"),
                                    t("no_timing_error"))
            return
        # B485: the inline crowd/bg marking comes from the text; read it
        # back so the editor shows it even when the timing is older.
        lines = pipeline.mark_inline_pieces(
            context, timing_module.load_timing(timing_path))
        offset = timing_module.load_offset(timing_path)

        # B450: the original sentence as timed PHONETIC pieces, on the
        # same timeline as the karaoke. The word boundaries come from the
        # forced alignment, so those are measured; within a word the
        # division is the same phonetic rule the karaoke side uses. The
        # editor lays the two rows on one axis and you say which piece
        # belongs to which.
        coupling = pipeline.build_coupling(context) or {}
        original_items, mapping = pipeline.editor_originals(context)
        original_words = coupling.get("original_words") or {}
        language = pipeline.language_for_original(context)
        # ``mapping`` is {karaoke line: original line} - that is how
        # ``couple_timing`` builds it and how the two other readers in
        # this file use it. Reading it the other way round is invisible
        # while the coupling is one-to-one and wrong the moment it is
        # not, which is exactly the case the editor exists for.
        by_karaoke = {int(k): int(v) for k, v in (mapping or {}).items()}
        original_lines: list = []
        for karaoke_index in range(len(lines)):
            original_index = by_karaoke.get(karaoke_index)
            item = (original_items[original_index]
                    if original_index is not None
                    and 0 <= original_index < len(original_items) else None)
            if item is None:
                original_lines.append(None)
                continue
            pieces = pipeline.original_pieces(
                item["text"], original_words.get(original_index, []),
                language)
            original_lines.append(timing_module.TimedLine(
                index=karaoke_index, text=item["text"], crowd=False,
                syllables=tuple(pieces)))

        def on_save(karaoke: list, original: list, anchors: dict) -> None:
            timing_module.save_timing(karaoke, timing_path, offset=offset,
                                      project=context.config.song.title,
                                      versie=__version__)
            pipeline.set_stress_anchors(context, anchors)
            self._log(t("stress_saved"))
            self._show_timing_lines()

        dialog = KlemtoonEditorDialog(lines, on_save,
                                      original_lines=original_lines,
                                      anchors=pipeline.stress_anchors(context),
                                      parent=self)
        dialog.exec()

    def _open_timing_editor(self) -> None:
        """Load audio + timing in the background and open the editor."""
        self._commit_pending_field()
        from . import timing as timing_module
        context = self._context
        timing_path = context.paths.timing_file

        def task(progress: Any, message: Any) -> dict[str, Any]:
            if not timing_path.exists():
                raise PipelineError(t("no_timing_error"))
            message(t("editor_loading"))
            # Re-anchor if the offset changed since storing (B98).
            timed = pipeline.load_timing_reanchored(context)
            # Use the adjusted (damped) karaoke if it exists.
            step = context.store.get_step("karaoke")
            if step and Path(step["wav"]).exists():
                karaoke_wav = Path(step["wav"])
            else:
                karaoke_wav = pipeline.prepare_track(
                    context, pipeline.TRACK_KARAOKE)
            data, sample_rate = audio_module.load_audio(karaoke_wav)
            duration = data.shape[0] / sample_rate
            peaks = waveform.compute_peaks(data,
                                           max(1000, int(duration * 100)))

            # Original (optional): waveform + playback source + offset.
            original_wav = None
            original_peaks = None
            try:
                original_wav = pipeline.prepare_track(
                    context, pipeline.TRACK_ORIGINAL)
                original_data, original_rate = audio_module.load_audio(
                    original_wav)
                original_duration = len(original_data) / original_rate
                original_peaks = waveform.compute_peaks(
                    original_data, max(1000, int(original_duration * 100)))
            except PipelineError:
                message(t("no_original_editor"))

            # Vocal stem of the original (B196): waveform + playback
            # source. On the original timeline, so the same length basis
            # as the original.
            vocal_wav = None
            vocal_peaks = None
            try:
                vocal_wav = pipeline.ensure_original_vocals(context)
                if vocal_wav is not None:
                    vocal_data, vocal_rate = audio_module.load_audio(vocal_wav)
                    vocal_dur = len(vocal_data) / vocal_rate
                    vocal_peaks = waveform.compute_peaks(
                        vocal_data, max(1000, int(vocal_dur * 100)))
            except (PipelineError, OSError, ValueError):
                logger.debug(t("log_vocal_waveform_missing"))
            offset = 0.0
            regions = ()
            try:
                pipeline.ensure_alignment(context)
            except Exception:  # noqa: BLE001
                pass
            step = context.store.get_step("align")
            if step is not None and step.get("regions"):
                from . import align as align_module
                regions = align_module.regions_from_dicts(step["regions"])
                offset = float(step["regions"][0].get("offset", 0.0))

            # Original sentences via the same coupling as the timing. The
            # original lane is placed 1-to-1 above its coupled karaoke
            # sentence (span from the already cleaned karaoke timing), so
            # that the original text no longer squashes and sits straight
            # above the karaoke sentence (B137/B138).
            originals: list[dict] = []
            original_items, mapping = pipeline.editor_originals(context)
            # B485: a loose crowd interjection got a coupling of its own
            # in B472 (every karaoke line has one), but in this lane it
            # is mirrored on its own row (B193/B257) - counting it in
            # here as well would make it disappear from the lane and
            # stretch the bar of the original sentence over it.
            def _mirrored(row: int) -> bool:
                line = timed[row] if 0 <= row < len(timed) else None
                return bool(line is not None and line.crowd
                            and not line.crowd_section)

            for original_index, item in enumerate(original_items):
                rows = [karaoke_index for karaoke_index, orig_index
                        in mapping.items()
                        if orig_index == original_index
                        and not _mirrored(karaoke_index)]
                kar_rows = [timed[r] for r in rows if 0 <= r < len(timed)]
                if kar_rows:
                    start = min(r.start for r in kar_rows)
                    end = max(r.end for r in kar_rows)
                else:
                    start, end = item["start"], item["end"]
                originals.append({
                    "text": item["text"],
                    "line_no": item.get("line_no"),
                    "bg": item.get("bg", ""),          # B485
                    "start": start,
                    "end": end,
                    "rows": rows,
                    "crowd": False,
                })
            # Loose crowd lines exist only in the karaoke (not in the
            # lyrics) and were therefore part of no coupling at all.
            # Mirror them 1-to-1 in the original lane so that they are
            # visible and can be shifted along (B193/B179b).
            # ``crowd=True`` so that the editor visibly draws them
            # differently from real original text (B257): it is
            # karaoke-only text that runs along here only for
            # orientation.
            # B489: an uncoupled original sentence hangs on its own
            # clock; put it between its neighbours before the crowd rows
            # are added (those are not original sentences).
            pipeline.place_between_neighbours(originals)
            coupled = {r for o in originals for r in o["rows"]}
            for karaoke_index, line in enumerate(timed):
                if karaoke_index in coupled or not line.crowd:
                    continue
                originals.append({
                    "text": line.text, "line_no": None,
                    "start": line.start, "end": line.end,
                    "rows": [karaoke_index], "crowd": True})
            originals.sort(key=lambda o: o["start"])
            return {"timed": timed, "peaks": peaks, "duration": duration,
                    "original_peaks": original_peaks,
                    "vocal_peaks": vocal_peaks,
                    "original_duration": locals().get("original_duration",
                                                      0.0),
                    "audio_paths": {"karaoke": karaoke_wav,
                                    "original": original_wav,
                                    "vocals": vocal_wav},
                    "offset": offset, "regions": regions,
                    "originals": originals}

        def on_done(payload: dict[str, Any]) -> None:
            from .timing_editor import TimingEditorDialog

            def save(lines: tuple, original_overrides: dict,
                     restore_rows: list | None = None,
                     reset_moves: list | None = None) -> None:
                # Safeguard integrity: start < end, no 0 lines, no
                # reordering (B108).
                lines = timing_module.enforce_monotonic(lines)
                timing_module.save_timing(
                    lines, timing_path,
                    offset=pipeline.current_offset(context),
                    project=context.config.song.title, versie=__version__)
                existing = pipeline.original_overrides(context)
                existing.update(original_overrides)
                pipeline.set_original_overrides(context, existing)
                if restore_rows is not None:            # B496
                    pipeline.set_restore_lines(context, restore_rows)
                for number in (reset_moves or ()):      # B499
                    pipeline.reset_moved_restore(context, number)
                self._log(t("timing_saved_log").format(path=timing_path)
                          + (t("timing_saved_corrections").format(
                              count=len(original_overrides))
                             if original_overrides else "")
                          + (t("timing_saved_restore").format(
                              count=len(restore_rows))
                             if restore_rows else ""))
                self._show_timing_lines()

            def reset_original() -> dict:
                pipeline.clear_original_overrides(context)
                fresh = pipeline.build_coupling(context)
                self._log(t("orig_timing_restored"))
                if fresh is None:
                    return {"originals": [], "lines": []}
                # Same cleanup + onset anchor as with the skeleton, so
                # that "Restore original" gives the same neat result.
                # B539: including the sung windows. Without them this
                # button built a timing the build step itself would
                # never make - B336 and B539 both need them, and
                # "restore" that gives something else than "build" is
                # the kind of difference nobody can explain afterwards.
                clean = timing_module.sanitize_timing(
                    fresh["timed"],
                    first_start=pipeline.ensure_vocal_onset(context),
                    song_duration=pipeline._karaoke_duration(context),
                    active_windows=pipeline._vocal_windows(context))
                mapping = fresh["mapping"]
                items = []
                def _mirrored_row(row: int) -> bool:       # B485
                    line = clean[row] if 0 <= row < len(clean) else None
                    return bool(line is not None and line.crowd
                                and not line.crowd_section)

                for oidx, item in enumerate(fresh["original_items"]):
                    rows = [k for k, v in mapping.items()
                            if v == oidx and not _mirrored_row(k)]
                    kar_rows = [clean[r] for r in rows if 0 <= r < len(clean)]
                    if kar_rows:
                        start = min(r.start for r in kar_rows)
                        end = max(r.end for r in kar_rows)
                    else:
                        start, end = item["start"], item["end"]
                    items.append({"text": item["text"],
                                  "line_no": item["line_no"],
                                  "bg": item.get("bg", ""),      # B485
                                  "start": start, "end": end, "rows": rows,
                                  "crowd": False})
                # Mirror loose crowd lines (B193/B257), just as when
                # first building the editor - otherwise that marking
                # disappears again after "Restore original timing".
                pipeline.place_between_neighbours(items)      # B489
                coupled = {r for o in items for r in o["rows"]}
                for karaoke_index, line in enumerate(clean):
                    if karaoke_index in coupled or not line.crowd:
                        continue
                    items.append({
                        "text": line.text, "line_no": None,
                        "start": line.start, "end": line.end,
                        "rows": [karaoke_index], "crowd": True})
                items.sort(key=lambda o: o["start"])
                # Also return the fresh (cleaned) karaoke lines so that
                # "Restore original" resets those too (B100).
                return {"originals": items, "lines": list(clean)}

            dialog = TimingEditorDialog(payload["peaks"],
                                        payload["original_peaks"],
                                        payload["duration"],
                                        payload["timed"], save,
                                        audio_paths=payload["audio_paths"],
                                        offset=payload["offset"],
                                        originals=payload["originals"],
                                        on_reset=reset_original,
                                        original_duration=payload[
                                            "original_duration"],
                                        regions=payload["regions"],
                                        vocal_peaks=payload["vocal_peaks"],
                                        restore_rows=pipeline.restore_lines(
                                            context),           # B496
                                        moved_restores=sorted(
                                            pipeline.moved_restores(
                                                context)),      # B499
                                        parent=self)
            dialog.exec()

        self._run(task, on_done)

    def _ask_render_options(self) -> tuple[str, str] | None:
        """Small pop-up: choose one text type + one music type (B226).

        Default = karaoke music + timed karaoke text. Returns
        ``(text_source, audio_source)`` or ``None`` on cancel."""
        from PySide6.QtWidgets import (QButtonGroup, QDialog, QDialogButtonBox,
                                       QRadioButton)
        dlg = QDialog(self)
        dlg.setWindowTitle(t("render_opts_title"))
        lay = QVBoxLayout(dlg)

        text_group = QGroupBox(t("render_opts_text"))
        tl = QVBoxLayout(text_group)
        text_bg = QButtonGroup(dlg)
        text_choices = [("karaoke", t("render_text_karaoke")),
                        ("original", t("render_text_original"))]
        for i, (code, label) in enumerate(text_choices):
            rb = QRadioButton(label)
            rb.setProperty("code", code)
            if i == 0:
                rb.setChecked(True)
            text_bg.addButton(rb)
            tl.addWidget(rb)
        lay.addWidget(text_group)

        muziek_grp = QGroupBox(t("render_opts_audio"))
        ml = QVBoxLayout(muziek_grp)
        muziek_bg = QButtonGroup(dlg)
        # 'Karaoke from original' (demucs) is deliberately gone from this
        # pop-up (B247): the karaoke music is the audio against which the
        # alignment and timing were made, regardless of whether it comes
        # from the original. The 'demucs' code path in _render_audio
        # remains in place for reuse.
        music_choices = [("karaoke", t("render_audio_karaoke")),
                         ("original", t("render_audio_original")),
                         ("vocals", t("render_audio_vocals"))]
        for i, (code, label) in enumerate(music_choices):
            rb = QRadioButton(label)
            rb.setProperty("code", code)
            if i == 0:
                rb.setChecked(True)
            muziek_bg.addButton(rb)
            ml.addWidget(rb)
        lay.addWidget(muziek_grp)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return (text_bg.checkedButton().property("code"),
                muziek_bg.checkedButton().property("code"))

    def _do_render_video(self) -> None:
        """Render the karaoke video in the background."""
        self._commit_pending_field()
        context = self._context
        choice = self._ask_render_options()
        if choice is None:
            return
        text_source, audio_source = choice
        # B354: an existing render used to be silently overwritten. Ask
        # first; "keep side by side" gives the NEW file a sequence
        # number, so nothing ever happens to the file already there.
        target = pipeline.video_target(context, text_source, audio_source)
        if target.exists():
            answer = self._ask_video_exists(target)
            if answer is None:
                return
            target = answer

        def task(progress: Any, message: Any) -> Path:
            message(t("video_rendering"))
            return pipeline.run_video(context, progress=progress,
                                      text_source=text_source,
                                      audio_source=audio_source,
                                      target=target)

        def on_done(target: Path) -> None:
            # B478: the name (with its sequence number) no longer goes on
            # the button; the number belongs in the choice dialog.
            self._refresh_video_button()
            self._progress.setRange(0, 100)
            self._progress.setValue(100)
            self._status.setText(t("video_done_status"))
            self._video_progress.setRange(0, 100)  # B278
            self._video_progress.setValue(100)
            self._video_status.setText(t("video_done_status"))
            self._log(t("video_done_log").format(target=target))
            choice = self._ask_video_done(
                t("video_done_title"),
                t("video_done_prompt").format(
                    title=t("video_done_title"), target=target))
            if choice == "video":
                pipeline.open_file(target)
            elif choice == "folder":
                pipeline.open_folder(target)

        self._run(task, on_done)

    def _refresh_video_button(self) -> None:
        """Switch "Open video" on or off by what is in the output folder
        of THIS project (B478).

        Called on every project change as well, because the button used
        to keep pointing at the video of the previous project.
        """
        button = getattr(self, "_open_video_button", None)
        if button is None:
            return
        button.setText(t("open_video"))
        button.setEnabled(bool(pipeline.existing_videos(self._context)))
        # B532: collecting looks across ALL projects, so this one is on
        # as soon as a single video exists anywhere.
        collect = getattr(self, "_collect_button", None)
        if collect is not None:
            collect.setEnabled(bool(pipeline.projects_with_video(
                self._context)))

    def _choose_video(self) -> Path | None:
        """Which video to open (B478).

        One video opens straight away. Several: a choice, with the
        highest sequence number selected - that is the most recent
        render, and ``existing_videos`` sorts by number and not by name.
        """
        videos = pipeline.existing_videos(self._context)
        if not videos:
            return None
        if len(videos) == 1:
            return videos[0]
        names = [path.name for path in videos]
        name, ok = QInputDialog.getItem(self, t("video_pick_title"),
                                        t("video_pick_body"), names,
                                        len(names) - 1, False)
        if not ok or not name:
            return None
        return videos[names.index(name)]

    def _do_collect_videos(self) -> None:
        """Copy the finished work to a folder of the user's choice (B532).

        Two questions and then it runs: what goes along, and where to.
        The copying itself is a background task, because twenty videos
        of fifteen megabytes is not instant and the window should not
        freeze on it.
        """
        songs = pipeline.projects_with_video(self._context)
        if not songs:
            QMessageBox.information(self, t("video_collect"),
                                    t("collect_none"))
            return
        choices = [t("collect_only_video"), t("collect_with_sources")]
        choice, ok = QInputDialog.getItem(
            self, t("video_collect"),
            t("collect_what").format(count=len(songs)), choices, 0, False)
        if not ok or not choice:
            return
        with_sources = choice == choices[1]
        folder = QFileDialog.getExistingDirectory(self, t("collect_where"))
        if not folder:
            return
        destination = Path(folder)
        cancel = threading.Event()

        def task(progress: Any, message: Any) -> tuple[int, int]:
            def report(done: int, total: int, song: str) -> None:
                message(t("collect_busy").format(song=song, done=done,
                                                 total=total))
                # The progress signal carries two numbers, like every
                # other task; one argument would raise on the first call
                # and the whole copy would never start.
                progress(float(done), float(total))

            return pipeline.collect_videos(self._context, destination,
                                           with_sources, progress=report,
                                           cancelled=cancel.is_set)

        # Ask before the work starts, not from the worker thread.
        try:
            pipeline.collect_destination_ok(self._context, destination)
        except pipeline.PipelineError as exc:
            QMessageBox.warning(self, t("video_collect"), str(exc))
            return

        def on_done(result: tuple[int, int]) -> None:
            projects, files = result
            message_text = t("collect_done").format(
                projects=projects, files=files, folder=destination)
            self._status.setText(message_text)
            self._video_status.setText(message_text)

        self._run(task, on_done, cancel_event=cancel)

    def _open_last_video(self) -> None:
        """Open a rendered video of this project with the default
        player."""
        chosen = self._choose_video()
        if chosen is not None:
            pipeline.open_file(chosen)

    def _open_last_video_folder(self) -> None:
        """Open the folder of the rendered video in the file
        manager (B267)."""
        chosen = self._choose_video()
        if chosen is not None:
            pipeline.open_folder(chosen)

    def _build_input_group(self) -> QGroupBox:
        group = QGroupBox(t("inputs_group"))
        layout = QVBoxLayout(group)
        self._input_labels: dict[str, QLabel] = {}
        for stem in (pipeline.TRACK_ORIGINAL, pipeline.TRACK_KARAOKE):
            row = QHBoxLayout()
            label = QLabel()
            self._input_labels[stem] = label
            row.addWidget(QLabel(f"{t(stem)}:"))
            row.addWidget(label, stretch=1)
            # On the karaoke row: "Karaoke from original" before "Choose
            # file..." (no separate row below it anymore, B88).
            if stem == pipeline.TRACK_KARAOKE:
                make_button = QPushButton(t("make_karaoke"))
                make_button.setToolTip(t("make_karaoke_tip"))
                make_button.clicked.connect(
                    self._make_karaoke_from_original)
                row.addWidget(make_button)
            button = QPushButton(t("choose_file"))
            button.clicked.connect(
                lambda _=False, s=stem: self._choose_file(s))
            row.addWidget(button)
            layout.addLayout(row)

        for name, tkey, handler in (
                ("Songtekst", "lyrics", self._choose_lyrics),
                ("Karaoketekst", "karaoke_text", self._choose_karaoke_text),
                ("Logo", "logo", self._choose_logo)):
            row = QHBoxLayout()
            label = QLabel()
            self._extra_labels[name] = label
            button = QPushButton(t("choose_file"))
            button.clicked.connect(handler)
            row.addWidget(QLabel(f"{t(tkey)}:"))
            row.addWidget(label, stretch=1)
            row.addWidget(button)
            layout.addLayout(row)
        return group

    def _copy_into_input(self, chosen: str, target_name: str, key: str,
                         note: str = "") -> None:
        """Copy a chosen file into the input folder of the project.

        ``key`` is the key under which the original name and folder are
        kept. It is passed explicitly (B324): deriving it from the file
        name gave ``songtekst``/``karaoketekst``, while everything that
        reads it asks for ``lyrics``/``karaoke_text``.
        """
        source = Path(chosen)
        target = self._context.paths.input_dir / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            QMessageBox.warning(self, t("copy_failed"), str(exc))
            return
        # Remember original name + location for display and reuse (B206).
        pipeline.set_input_origin(self._context, key, source)
        self._log(t("copied_to_log").format(
            name=source.name, target=target, note=note).strip())
        self._refresh_inputs()

    def _choose_karaoke_text(self) -> None:
        from . import karaoke_text
        chosen, _ = QFileDialog.getOpenFileName(
            self, t("choose_karaoke_text_title"),
            pipeline.input_start_dir(self._context, "karaoke_text"),
            t("filter_text"))
        if not chosen:
            return
        # Read the old text before overwriting, to be able to update an
        # existing timing.json along with it (B99).
        old_path = self._context.paths.input_dir / karaoke_text.FILENAME
        old_lines = (karaoke_text.parse_lines(old_path)
                     if old_path.exists() else ())
        self._copy_into_input(chosen, "karaoketekst.txt", "karaoke_text",
                              t("karaoke_text_note"))
        if old_lines:
            try:
                new_lines = karaoke_text.parse_lines(old_path)
                updated, message = pipeline.sync_timing_with_text_change(
                    self._context, old_lines, new_lines)
                if message:
                    self._log(message)
                if updated:
                    self._show_timing_lines()
            except Exception:  # noqa: BLE001 - sync must not break choosing
                logger.exception(t("log_timing_sync_failed"))
        # B311: through the filler-word priority the karaoke text also
        # steers the WORD COUPLING of the lyrics, and thereby the line
        # times. With an equal block structure that coupling stayed put
        # while it referred to the old text. What hangs off it now lapses;
        # the manual word couplings stay (those are about the lyrics and
        # the transcription, not about the parody).
        pipeline.invalidate(self._context, ["input:karaoke_text"])
        pipeline.remember_sources(self._context)
        self._check_text_alignment()

    def _check_text_alignment(self) -> None:
        """Check section structure and whether lines fit on screen."""
        # Quick sanity check: are the lyrics and karaoke text not by
        # accident both set to the same (wrong) text? (B115)
        if pipeline.texts_identical(self._context):
            self._log(t("lyrics_duplicate_warn"))
            QMessageBox.warning(self, t("text_structure_title"),
                                t("lyrics_duplicate_warn"))
        ok, message = pipeline.check_text_alignment(self._context)
        self._log(message)
        if not ok:
            QMessageBox.warning(self, t("text_structure_title"), message)
        self._check_line_overflow()

    def _check_line_overflow(self) -> None:
        """Warn about karaoke lines that do not fit in the video frame."""
        from . import karaoke_text
        from . import timing as timing_module
        from . import video
        kt = self._context.paths.input_dir / karaoke_text.FILENAME
        if not kt.exists():
            return
        try:
            lines = karaoke_text.parse_lines(kt)
            timed = timing_module.generate_skeleton(lines)
        except (OSError, ValueError):
            return
        vs = self._context.config.video
        te_lang = video.overflowing_lines(timed, vs.width, vs.height,
                                          vs.font)
        if te_lang:
            preview = "\n  - ".join(line_number[:60] for line_number in te_lang[:8])
            QMessageBox.warning(
                self, t("lines_overflow_title"),
                t("lines_overflow_body").format(count=len(te_lang),
                                                preview=preview))

    def _choose_logo(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, t("choose_logo_title"),
            pipeline.input_start_dir(self._context, "logo"),
            t("filter_images"))
        if chosen:
            for old_logo in self._context.paths.input_dir.glob("logo.*"):
                try:
                    old_logo.unlink()
                except OSError:
                    pass
            self._copy_into_input(chosen,
                                  f"logo{Path(chosen).suffix.lower()}",
                                  "logo")

    def _choose_lyrics(self) -> None:
        """Choose the official lyrics (txt) and copy them to input."""
        chosen, _ = QFileDialog.getOpenFileName(
            self, t("choose_lyrics_title"),
            pipeline.input_start_dir(self._context, "lyrics"),
            t("filter_text"))
        if chosen:
            self._copy_into_input(chosen, "songtekst.txt", "lyrics",
                                  t("lyrics_note"))
            # New lyrics -> everything derived from them lapses (B113/B311).
            pipeline.invalidate(self._context, ["input:lyrics"])
            pipeline.remember_sources(self._context)
            self._log(t("derived_invalidated"))
            self._show_timing_lines()
            self._check_text_alignment()

    def _toggle_cache(self, checked: bool) -> None:
        """Turn clearing of the cache on or off."""
        config = self._context.config
        self._update_config(replace(
            config, cache=replace(config.cache, clear=checked)))
        self._log(t("cache_clear_log").format(
            state=t("on") if checked else t("off")))

    def _clear_cache_now(self) -> None:
        """Empty the cache once, independent of the setting (B236)."""
        from .filesystem import clean_cache
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, t("busy_title"),
                                    t("busy_running_body"))
            return
        clean_cache(self._context.paths.cache_root)
        self._log(t("cache_cleared_now_log"))

    def _toggle_parallel(self, checked: bool) -> None:
        """Turn parallel detection (original+karaoke at once) on or off."""
        config = self._context.config
        self._update_config(replace(
            config, advanced=replace(
                config.advanced, parallel_detection=checked)))
        self._log(t("parallel_detect_log").format(
            state=t("on") if checked else t("off")))

    def _toggle_diagnostiek(self, checked: bool) -> None:
        """Turn writing of local diagnostic files on or off (B143)."""
        config = self._context.config
        self._update_config(replace(
            config, advanced=replace(
                config.advanced, diagnostics=checked)))
        self._log(t("diagnostics_log").format(
            state=t("on") if checked else t("off")))

    def _toggle_vocal_analyse(self, checked: bool) -> None:
        """Turn the vocal stem energy analysis on or off (B194/B209)."""
        config = self._context.config
        self._update_config(replace(
            config, advanced=replace(
                config.advanced, vocal_analysis=checked)))
        self._log(t("vocal_analyse_log").format(
            state=t("on") if checked else t("off")))

    def _change_model(self) -> None:
        """Choose the Whisper model (accurate/medium/fast)."""
        code = self._model_combo.currentData()
        config = self._context.config
        if code == config.whisper.model:
            return
        self._update_config(replace(
            config, whisper=replace(config.whisper, model=code)))
        self._log(t("whisper_model_log").format(code=code))

    def _update_config(self, new_config: Any) -> None:
        """Store a changed configuration and update the context."""
        config_module.save_config(new_config,
                                  self._context.paths.config_file)
        self._context = replace(self._context, config=new_config)

    def _build_titles_group(self) -> QWidget:
        """Karaoke title + original artist/title (leading for the render).

        Sits on the first tab, left of the input files (B171).
        """
        video = self._context.config.video
        group = QGroupBox(t("video_meta_group"))
        outer = QVBoxLayout(group)
        self._meta_fields: dict[str, QLineEdit] = {}
        for key, label in (("karaoke_title", t("meta_karaoke_title")),
                           ("orig_artist", t("meta_orig_artist")),
                           ("orig_title", t("meta_orig_title"))):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            field = QLineEdit(getattr(video, key))
            field.editingFinished.connect(
                lambda k=key: self._save_meta_field(k))
            self._meta_fields[key] = field
            row.addWidget(field, stretch=1)
            outer.addLayout(row)
        outer.addStretch()
        return group

    def _build_output_dir_group(self) -> QWidget:
        """Configurable output folder (Windows path or UNC), global (B214)."""
        group = QGroupBox(t("output_dir_group"))
        outer = QVBoxLayout(group)
        row = QHBoxLayout()
        current = (self._context.config.advanced.output_dir
                  or str(self._context.paths.output_root))
        self._output_dir_label = QLabel(current)
        self._output_dir_label.setStyleSheet("color: #333;")
        row.addWidget(self._output_dir_label, stretch=1)
        pick = QPushButton(t("choose_folder"))
        pick.clicked.connect(self._pick_output_dir)
        reset = QPushButton(t("reset"))
        reset.clicked.connect(self._reset_output_dir)
        row.addWidget(pick)
        row.addWidget(reset)
        outer.addLayout(row)
        hint = QLabel(t("output_dir_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        outer.addWidget(hint)
        return group

    def _pick_output_dir(self) -> None:
        start = (self._context.config.advanced.output_dir
                 or str(self._context.paths.output_root))
        chosen = QFileDialog.getExistingDirectory(
            self, t("output_dir_group"), start)
        if chosen:
            self._apply_output_dir(Path(chosen))

    def _reset_output_dir(self) -> None:
        self._apply_output_dir(self._context.paths.root / "output")

    def _apply_output_dir(self, new_base: Path) -> None:
        ok, message, new = pipeline.relocate_output_base(
            self._context, new_base)
        if ok:
            self._context = new
            self._output_dir_label.setText(
                self._context.config.advanced.output_dir
                or str(self._context.paths.output_root))
            self._log(message)
            self._refresh_inputs()
        else:
            QMessageBox.warning(self, t("output_dir_group"), message)
            self._log(message)

    def _build_background_group(self) -> QWidget:
        """Background image for the video (B126).

        B480: on Settings this no longer stands as a group of its own but
        under "Video background", with the colour it replaces. Chosen
        pictures are kept centrally, so one chosen once can be picked
        again for the next song.
        """
        group = QWidget()
        outer = QVBoxLayout(group)
        outer.setContentsMargins(0, 0, 0, 0)
        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel(t("meta_background")))
        self._bg_label = QLabel("")
        bg_row.addWidget(self._bg_label, stretch=1)
        pick = QPushButton(t("choose_file"))
        pick.clicked.connect(self._pick_background)
        bg_row.addWidget(pick)
        # B480: was "Back to default", and after pressing it the picture
        # said 'default' - while there simply was no picture any more.
        self._bg_clear_button = QPushButton(t("background_remove"))
        self._bg_clear_button.clicked.connect(self._clear_background)
        bg_row.addWidget(self._bg_clear_button)
        outer.addLayout(bg_row)

        # The stored pictures as thumbnails; only there once there is
        # something stored (B480).
        self._bg_list = QListWidget()
        self._bg_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._bg_list.setIconSize(QSize(120, 68))
        self._bg_list.setMaximumHeight(120)
        self._bg_list.setMovement(QListWidget.Movement.Static)
        self._bg_list.itemSelectionChanged.connect(self._stored_selection)
        # A double click picks it straight away; the button below does
        # the same for anyone who would rather click once.
        self._bg_list.itemDoubleClicked.connect(
            lambda _item: self._use_selected_background())
        outer.addWidget(self._bg_list)
        stored_row = QHBoxLayout()
        self._bg_use_button = QPushButton(t("background_use_stored"))
        self._bg_use_button.clicked.connect(self._use_selected_background)
        stored_row.addWidget(self._bg_use_button)
        self._bg_delete_button = QPushButton(t("background_delete_stored"))
        self._bg_delete_button.setToolTip(t("background_delete_stored_tip"))
        self._bg_delete_button.clicked.connect(self._delete_stored_background)
        stored_row.addWidget(self._bg_delete_button)
        stored_row.addStretch()
        self._bg_stored_row = QWidget()
        self._bg_stored_row.setLayout(stored_row)
        outer.addWidget(self._bg_stored_row)
        self._refresh_background_view()
        return group

    def _refresh_background_view(self) -> None:
        """Label, buttons and thumbnails after every change (B480).

        The picture in use is selected in the list, so it can be seen at
        a glance which one is on - and only then can it be deleted from
        the store.
        """
        current = pipeline.project_background(self._context)
        in_use = pipeline.stored_match(self._context, current)
        self._bg_label.setText(in_use.stem if in_use is not None else (
            current.name if current is not None else t("background_none")))
        self._bg_clear_button.setEnabled(current is not None)
        stored = pipeline.stored_backgrounds(self._context)
        self._bg_list.blockSignals(True)
        self._bg_list.clear()
        for path in stored:
            item = QListWidgetItem(QIcon(self._thumbnail(path)), path.stem)
            item.setData(0x0100, str(path))       # Qt.ItemDataRole.UserRole
            self._bg_list.addItem(item)
            if in_use is not None and path == in_use:
                item.setSelected(True)
        self._bg_list.blockSignals(False)
        self._bg_list.setVisible(bool(stored))
        self._bg_stored_row.setVisible(bool(stored))
        self._stored_selection()

    @staticmethod
    def _thumbnail(path: Path) -> QPixmap:
        """Small preview of a stored background (B480). Made when the
        list is built; a picture that cannot be read gives an empty
        square instead of an error."""
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            empty = QPixmap(120, 68)
            empty.fill(QColor("#444444"))    # else uninitialised memory
            return empty
        from PySide6.QtCore import Qt
        return pixmap.scaled(120, 68,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)

    def _selected_background(self) -> Path | None:
        items = self._bg_list.selectedItems()
        if not items:
            return None
        return Path(str(items[0].data(0x0100)))

    def _use_background(self, stored: Path) -> None:
        """Store the choice and put a copy in the project (B480)."""
        from dataclasses import replace as _replace
        try:
            pipeline.apply_background(self._context, stored)
        except pipeline.PipelineError as exc:
            QMessageBox.warning(self, t("meta_background"), str(exc))
            return
        except OSError:
            QMessageBox.warning(self, t("meta_background"), t("copy_failed"))
            return
        config = self._context.config
        self._update_config(_replace(
            config, video=_replace(config.video,
                                   background_image=str(stored))))
        self._refresh_background_view()

    def _pick_background(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, t("meta_background"),
            pipeline.picture_start_dir(self._context),
            t("filter_image"))
        if not chosen:
            return
        try:
            stored = pipeline.store_background(self._context, Path(chosen))
        except OSError:
            QMessageBox.warning(self, t("meta_background"), t("copy_failed"))
            return
        self._use_background(stored)

    def _stored_selection(self) -> None:
        """B480: selecting says WHICH picture the buttons work on; it
        does not switch the background by itself. Otherwise a stored
        picture could not be deleted without first putting it on this
        project."""
        chosen = bool(self._bg_list.selectedItems())
        self._bg_use_button.setEnabled(chosen)
        self._bg_delete_button.setEnabled(chosen)

    def _use_selected_background(self) -> None:
        stored = self._selected_background()
        if stored is not None:
            self._use_background(stored)

    def _delete_stored_background(self) -> None:
        """Remove a picture from the central store (B480). Projects that
        use it keep their own copy in ``input``."""
        stored = self._selected_background()
        if stored is None:
            return
        answer = QMessageBox.question(
            self, t("meta_background"),
            t("background_delete_ask").format(name=stored.name))
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not pipeline.remove_stored_background(stored):
            QMessageBox.warning(self, t("meta_background"),
                                t("background_delete_failed"))
        self._refresh_background_view()

    def _clear_background(self) -> None:
        """Remove the picture from THIS project (B480); the central store
        keeps it."""
        from dataclasses import replace as _replace
        pipeline.clear_background(self._context)
        config = self._context.config
        self._update_config(_replace(
            config, video=_replace(config.video, background_image="")))
        self._refresh_background_view()

    def _save_meta_field(self, key: str) -> None:
        from dataclasses import replace as _replace
        field_value = self._meta_fields[key].text().strip()
        config = self._context.config
        if getattr(config.video, key) == field_value:
            return
        self._update_config(_replace(
            config, video=_replace(config.video, **{key: field_value})))
        # Titles belong to the project: store them per project too (B210).
        pipeline.set_project_title(self._context, key, field_value)

    def _build_help_tab(self) -> QWidget:
        """Tab with the manual (renders docs/handleiding.md) (B165)."""
        from pathlib import Path as _Path
        tab = QWidget()
        outer = QVBoxLayout(tab)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        path = _Path(__file__).resolve().parents[1] / "docs" / "handleiding.md"
        try:
            text_value = path.read_text(encoding="utf-8")
            browser.setMarkdown(text_value)
        except Exception:  # noqa: BLE001 - manual must never break the GUI
            browser.setPlainText(t("help_missing"))
        outer.addWidget(browser)
        return tab

    def _build_settings_tab(self) -> QWidget:
        """Tab with all global (cross-project) settings."""
        tab = QWidget()
        outer = QVBoxLayout(tab)
        config = self._context.config

        language_group = QGroupBox(t("language_label"))
        language_layout = QHBoxLayout(language_group)
        self._language_combo = QComboBox()
        for code, label in translations.LANGUAGES.items():
            self._language_combo.addItem(label, code)
        idx = self._language_combo.findData(config.interface.language)
        if idx >= 0:
            self._language_combo.setCurrentIndex(idx)
        self._language_combo.currentIndexChanged.connect(
            self._change_language)
        language_layout.addWidget(self._language_combo)
        language_layout.addStretch()
        outer.addWidget(language_group)

        model_group = QGroupBox(t("model_label"))
        model_layout = QHBoxLayout(model_group)
        self._model_combo = QComboBox()
        for label, code in ((t("model_accurate"), "large-v3"),
                            (t("model_medium"), "distil-large-v3"),
                            (t("model_fast"), "small")):
            self._model_combo.addItem(label, code)
        midx = self._model_combo.findData(config.whisper.model)
        self._model_combo.setCurrentIndex(midx if midx >= 0 else 0)
        self._model_combo.currentIndexChanged.connect(self._change_model)
        model_layout.addWidget(self._model_combo)
        model_layout.addStretch()
        outer.addWidget(model_group)

        adv = QGroupBox(t("advanced_group"))
        adv_layout = QVBoxLayout(adv)
        self._advanced_boxes: dict[str, QCheckBox] = {}
        for key in ("demucs", "forced_alignment"):
            row = QHBoxLayout()
            box = QCheckBox(t(f"model_{key}_desc"))
            box.setChecked(getattr(config.advanced, key))
            box.toggled.connect(
                lambda checked, k=key: self._toggle_advanced(k, checked))
            self._advanced_boxes[key] = box
            row.addWidget(box)
            info = QLabel(t(f"model_{key}_info")
                          + ("" if models.is_available(key)
                             else t("model_not_installed_suffix")))
            info.setStyleSheet("color: #666;")
            row.addWidget(info, stretch=1)
            adv_layout.addLayout(row)
        outer.addWidget(adv)

        self._parallel_box = QCheckBox(t("parallel_detect"))
        self._parallel_box.setToolTip(t("parallel_detect_tip"))
        self._parallel_box.setChecked(config.advanced.parallel_detection)
        self._parallel_box.toggled.connect(self._toggle_parallel)
        outer.addWidget(self._parallel_box)

        self._vocal_box = QCheckBox(t("vocal_analyse_option"))
        self._vocal_box.setToolTip(t("vocal_analyse_tip"))
        self._vocal_box.setChecked(config.advanced.vocal_analysis)
        self._vocal_box.toggled.connect(self._toggle_vocal_analyse)
        outer.addWidget(self._vocal_box)

        self._diagnostics_box = QCheckBox(t("diagnostics_option"))
        self._diagnostics_box.setToolTip(t("diagnostics_tip"))
        self._diagnostics_box.setChecked(config.advanced.diagnostics)
        self._diagnostics_box.toggled.connect(self._toggle_diagnostiek)
        outer.addWidget(self._diagnostics_box)

        cache_row = QHBoxLayout()
        self._cache_box = QCheckBox(t("cache_clear"))
        self._cache_box.setChecked(config.cache.clear)
        self._cache_box.toggled.connect(self._toggle_cache)
        cache_row.addWidget(self._cache_box)
        cache_now = QPushButton(t("cache_clear_now"))       # B236
        cache_now.setToolTip(t("cache_clear_now_tip"))
        cache_now.clicked.connect(self._clear_cache_now)
        cache_row.addWidget(cache_now)
        cache_row.addStretch()
        outer.addLayout(cache_row)

        outer.addWidget(self._build_output_dir_group())   # B214

        outer.addWidget(self._build_video_colors_group())
        outer.addWidget(self._build_theme_group())
        outer.addStretch()
        return tab

    def _color_button(self, hex_value: str,
                      handler) -> QPushButton:
        """Button showing its colour that opens a colour picker on click."""
        button = QPushButton(hex_value or t("default_value"))
        if hex_value:
            button.setStyleSheet(f"background-color: {hex_value};")
        button.clicked.connect(handler)
        return button

    def _pick_color(self, current: str) -> str | None:
        from PySide6.QtGui import QColor
        colour = QColorDialog.getColor(QColor(current or "#ffffff"), self)
        return colour.name() if colour.isValid() else None

    def _build_video_colors_group(self) -> QGroupBox:
        group = QGroupBox(t("video_colors_group"))
        layout = QVBoxLayout(group)
        video = self._context.config.video
        self._color_buttons: dict[str, QPushButton] = {}
        rows = (("color_before", t("color_before")),
                ("color_vocal", t("color_during")),
                ("color_after", t("color_after")),
                ("color_crowd", t("color_crowd")),
                ("color_background", t("color_background")))
        for key, label in rows:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            btn = self._color_button(getattr(video, key),
                                     lambda _=False, k=key: self._pick_video_color(k))
            self._color_buttons[key] = btn
            row.addWidget(btn)
            # B477: every text colour of the active line has its own
            # outline colour right next to it; empty = the contra colour
            # of that letter colour.
            edge = _OUTLINE_OF.get(key)
            if edge is not None:
                row.addWidget(QLabel(t("outline_label")))
                edge_btn = self._color_button(
                    getattr(video, edge),
                    lambda _=False, k=edge: self._pick_video_color(k))
                self._color_buttons[edge] = edge_btn
                row.addWidget(edge_btn)
            layout.addLayout(row)
            # B480: the background image belongs with the background
            # colour, not in a group of its own.
            if key == "color_background":
                layout.addWidget(self._build_background_group())
        font_row = QHBoxLayout()
        font_row.addWidget(QLabel(t("font_ttf")))
        # Dropdown with the bundled fonts from assets/fonts (B102); is
        # refilled when the settings tab is opened.
        self._font_combo = QComboBox()
        self._font_combo.currentIndexChanged.connect(self._change_video_font)
        font_row.addWidget(self._font_combo, stretch=1)
        font_btn = QPushButton(t("choose_file"))
        font_btn.clicked.connect(self._pick_video_font)
        font_row.addWidget(font_btn)
        layout.addLayout(font_row)
        # Live preview of the chosen font (B102).
        self._font_preview = QLabel(t("font_preview_text"))
        self._font_preview.setMinimumHeight(48)
        layout.addWidget(self._font_preview)
        self._populate_font_combo()
        self._update_font_preview()
        reset = QPushButton(t("reset"))
        reset.clicked.connect(self._reset_video_colors)
        layout.addWidget(reset)
        return group

    def _pick_video_color(self, key: str) -> None:
        from dataclasses import replace as _replace
        current = getattr(self._context.config.video, key)
        chosen = self._pick_color(current)
        if chosen is None:
            return
        config = self._context.config
        self._update_config(_replace(
            config, video=_replace(config.video, **{key: chosen})))
        self._color_buttons[key].setText(chosen)
        self._color_buttons[key].setStyleSheet(
            f"background-color: {chosen};")

    def _on_tab_changed(self, index: int) -> None:
        """Refresh the font list when opening the settings tab (B102);
        hide the messages/activity panel on Settings and Manual (no
        added value there, B173)."""
        if index == getattr(self, "_settings_tab_index", -1):
            self._populate_font_combo()
        if index == getattr(self, "_video_tab_index", -1):
            self._show_timing_lines()          # always the latest state (B240)
        log_group = getattr(self, "_log_group", None)
        if log_group is not None:
            verbergen = index in (getattr(self, "_settings_tab_index", -1),
                                  getattr(self, "_help_tab_index", -1))
            log_group.setVisible(not verbergen)

    def _populate_font_combo(self) -> None:
        """Fill the font menu from assets/fonts; select the current choice."""
        from . import fonts as fonts_module
        combo = getattr(self, "_font_combo", None)
        if combo is None:
            return
        # The config stores a portable value (file name for fonts from
        # assets/fonts); resolve that to the absolute path that sits as
        # item data in the combo, so that the selection matches again
        # after a folder move or on another computer (B245).
        current = fonts_module.resolve_font(self._context.config.video.font)
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(t("font_default"), "")           # empty choice = default
        for item_name, path in fonts_module.available_fonts():
            combo.addItem(item_name, path)
        # Still show a manually chosen file outside assets/fonts.
        if current and combo.findData(current) < 0:
            combo.addItem(Path(current).name, current)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
        self._update_font_preview()

    def _change_video_font(self) -> None:
        """Store the font chosen from the dropdown menu."""
        from dataclasses import replace as _replace
        from . import fonts as _fonts
        combo = self._font_combo
        path = combo.currentData() or ""
        key = _fonts.store_key(path)           # store portably (B245)
        config = self._context.config
        self._update_font_preview()
        if key == config.video.font:
            return
        self._update_config(_replace(
            config, video=_replace(config.video, font=key)))

    def _update_font_preview(self) -> None:
        """Show a sample line in the chosen font (B102)."""
        label = getattr(self, "_font_preview", None)
        if label is None:
            return
        from PySide6.QtGui import QFont, QFontDatabase
        path = self._font_combo.currentData() or ""
        familie = ""
        if path:
            font_id = QFontDatabase.addApplicationFont(path)
            families = QFontDatabase.applicationFontFamilies(font_id) \
                if font_id != -1 else []
            familie = families[0] if families else ""
        label.setFont(QFont(familie, 22) if familie else QFont("", 22))

    def _pick_video_font(self) -> None:
        from dataclasses import replace as _replace
        chosen, _ = QFileDialog.getOpenFileName(
            self, t("choose_font_title"), "", t("filter_font"))
        if not chosen:
            return
        from . import fonts as _fonts
        config = self._context.config
        self._update_config(_replace(
            config, video=_replace(config.video,
                                   font=_fonts.store_key(chosen))))  # B245
        self._populate_font_combo()

    def _reset_video_colors(self) -> None:
        from dataclasses import replace as _replace
        from .config import VideoSettings
        d = VideoSettings()
        config = self._context.config
        self._update_config(_replace(config, video=_replace(
            config.video, font="", color_before=d.color_before,
            color_vocal=d.color_vocal, color_after=d.color_after,
            color_crowd=d.color_crowd,
            color_background=d.color_background,
            outline_before=d.outline_before, outline_vocal=d.outline_vocal,
            outline_after=d.outline_after, outline_crowd=d.outline_crowd)))
        for key, btn in self._color_buttons.items():
            value = getattr(d, key)
            btn.setText(value or t("default_value"))
            btn.setStyleSheet(f"background-color: {value};" if value else "")
        self._populate_font_combo()
        self._log(t("video_colors_reset_log"))

    def _build_theme_group(self) -> QGroupBox:
        group = QGroupBox(t("theme_group"))
        layout = QVBoxLayout(group)
        theme = self._context.config.theme
        self._theme_buttons: dict[str, QPushButton] = {}
        for key, label in (("background", t("theme_background")),
                           ("button", t("theme_buttons")),
                           ("button_active", t("theme_button_active"))):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            btn = self._color_button(getattr(theme, key),
                                     lambda _=False, k=key: self._pick_theme_color(k))
            self._theme_buttons[key] = btn
            row.addWidget(btn)
            layout.addLayout(row)
        reset = QPushButton(t("reset"))
        reset.clicked.connect(self._reset_theme)
        layout.addWidget(reset)
        return group

    def _pick_theme_color(self, key: str) -> None:
        from dataclasses import replace as _replace
        chosen = self._pick_color(getattr(self._context.config.theme, key))
        if chosen is None:
            return
        config = self._context.config
        self._update_config(_replace(
            config, theme=_replace(config.theme, **{key: chosen})))
        self._theme_buttons[key].setText(chosen)
        self._theme_buttons[key].setStyleSheet(
            f"background-color: {chosen};")
        self._apply_theme()

    def _reset_theme(self) -> None:
        from dataclasses import replace as _replace
        config = self._context.config
        # knop_actief back to the default yellow, not empty (B229).
        self._update_config(_replace(config, theme=_replace(
            config.theme, background="", button="", button_active="#f2c200")))
        for key, btn in self._theme_buttons.items():
            field_value = getattr(self._context.config.theme, key)
            btn.setText(field_value or t("default_value"))
            btn.setStyleSheet(f"background-color: {field_value};" if field_value else "")
        self._apply_theme()
        self._log(t("gui_colors_reset_log"))

    def _apply_theme(self) -> None:
        """Apply the GUI colours via a Qt stylesheet (empty = default)."""
        theme = self._context.config.theme
        parts = []
        if theme.background:
            parts.append(f"QWidget {{ background-color: "
                         f"{theme.background}; }}")
        if theme.button:
            parts.append(f"QPushButton {{ background-color: "
                         f"{theme.button}; }}")
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet("\n".join(parts))

    def _toggle_advanced(self, key: str, checked: bool) -> None:
        from dataclasses import replace as _replace
        config = self._context.config
        new_adv = _replace(config.advanced, **{key: checked})
        self._update_config(_replace(config, advanced=new_adv))
        self._log(t("model_toggle_log").format(
            model=t(f"model_{key}_desc"),
            state=t("on") if checked else t("off")))
        if checked:
            self._warmup_model(key)

    def _warmup_model(self, key: str) -> None:
        """Download/load the model directly after ticking (seconds counter)."""
        if not models.is_available(key):
            QMessageBox.information(
                self, t("package_missing_title"),
                t("package_missing_body").format(
                    model=t(f"model_{key}_desc")))
            return
        context = self._context

        def task(progress: Any, message: Any) -> str:
            message(t("model_downloading").format(
                model=t(f"model_{key}_desc")))
            from . import separation, word_alignment
            if key == "demucs":
                separation.warmup()
            elif key == "forced_alignment":
                held = pipeline._language_for(context,
                                              pipeline.TRACK_ORIGINAL)
                word_alignment.warmup(held)
            return key

        self._run(task, lambda k: self._log(
            t("model_ready_log").format(model=t(f"model_{k}_desc"))))

    def _build_steps_group(self) -> QGroupBox:
        group = QGroupBox(t("steps_group"))
        layout = QHBoxLayout(group)
        self._step_buttons: list[QPushButton] = []
        steps = (
            (t("step_detect"), self._do_detect),
            (t("step_couple"), self._open_word_couple),
            (t("step_analyse"), self._do_analyse),
            (t("step_karaoke"), self._do_karaoke),
            # TIJDELIJK (1.5): fills the transcription cache file of
            # projects whose copy is gone, without throwing anything
            # away. May go once the benchmark set is complete again.
            (t("step_fill_cache"), self._do_fill_cache),
        )
        for text, handler in steps:
            button = QPushButton(text)
            button.clicked.connect(handler)
            layout.addWidget(button)
            self._step_buttons.append(button)
        return group

    def _do_fill_cache(self) -> None:
        """Het testpaneel achter 1.5 (TIJDELIJK).

        Heette eerst "Cache vullen"; dat is nu actie 1.5.1 in een lijst.
        De naam van deze methode blijft zoals hij is - de knop verwijst
        ernaar en het hele paneel gaat er ooit weer uit.
        """
        self._commit_pending_field()
        context = self._context
        from PySide6.QtWidgets import QDialog

        from . import test_panel
        from .test_panel import TestPanel

        panel = TestPanel(self)
        if panel.exec() != QDialog.DialogCode.Accepted:
            return
        actions = panel.chosen()
        if not actions:
            return
        # B359: the radio buttons at the bottom of the panel did
        # nothing. The choice applies to this run and is set afresh every
        # time, so a previous choice never lingers.
        test_panel.limit_to_current(panel.only_this_project())
        # B362: "measure again" ignores the kept results of this
        # version. This too is set afresh every run.
        test_panel.REMEASURE = panel.remeasure()
        # B453: which letters of 1.5.11 to run. Set afresh per run, like
        # the two above, so a previous choice never lingers.
        test_panel.limit_heavy_to(panel.heavy_choice())
        # B524: every action also writes its lines to a file (the log
        # window keeps them, but that text cannot leave the machine).
        test_panel.start_trial_report(
            [action.code for action in actions],
            t("report_scope_current") if panel.only_this_project()
            else t("report_scope_all"),
            __version__)
        cancel = threading.Event()
        self._show_test_bars([actions[0].code, actions[0].code])

        def task(progress: Any, message: Any) -> list[tuple[str, str]]:
            results: list[tuple[str, str]] = []
            for action in actions:
                if cancel.is_set():
                    break
                message(t("test_running").format(code=action.code,
                                                 name=t(action.name_key)))

                def report(slot: int, name: str, done: int = 0,
                           total: int = 0, code=action.code) -> None:
                    # B357: every work slot has its own bar and puts the
                    # project it is busy with on it. The labels used to
                    # stay on the first action number and the bars on
                    # their busy animation.
                    #
                    # B409: the code is only prefixed when the name does
                    # not already start with it. An action that names
                    # itself - 1.5.11 reports "1.5.11b" to show the
                    # letter of the trial - otherwise read
                    # "1.5.11  1.5.11b  2/4".
                    label = (str(name) if str(name).startswith(code)
                             else f"{code}  {name}")
                    self._test_progress.emit(slot, label, done, total)

                # B359: an action that reports nothing itself (1.5.9
                # works on the current project and has no queue to walk)
                # must move the label too. Otherwise the previous action
                # still stands above the bar and it looks like a hang.
                for slot in range(len(self._progress_bars)):
                    report(slot, t(action.name_key), 0, 0)

                import time as _time
                # B435: every action starts with a clean slate, otherwise
                # an alarm from the previous action turns up in this
                # report. B436: the CPU time beside the wall clock - runs
                # far apart mean the machine was doing something else and
                # the number cannot be compared with an earlier one.
                test_panel.reset_alarms()
                self._clear_slot_chips()
                started = _time.monotonic()
                started_cpu = _time.process_time()
                try:
                    text = action.function(context, report, cancel.is_set)
                except Exception:  # noqa: BLE001 - een test mag de rest niet stoppen
                    logger.exception(t("log_test_failed"), action.code)
                    text = t("test_failed").format(code=action.code)
                seconds = _time.monotonic() - started
                cpu = _time.process_time() - started_cpu
                # B369: write it down NOW, not at the end. To the log
                # file first - that happens from this worker thread and is
                # therefore the only thing that survives a crash; the
                # signal to the window is still in the GUI thread's queue
                # afterwards and is the first thing lost in a fall.
                logger.info(t("log_test_result"), action.code, seconds)
                if seconds > 5.0 and cpu < seconds * 0.35:
                    logger.warning(t("log_test_busy_machine"),
                                   action.code, seconds, cpu)
                for line in str(text).splitlines():
                    logger.info(t("log_gui"), line)
                # B524: to the file from this worker thread, for the same
                # reason as the log line above - it survives a crash.
                test_panel.add_trial_result(
                    action.code, t(action.name_key), text, seconds, cpu,
                    # B537: only when there IS an alarm; the report
                    # writes a line above the block.
                    test_panel.alarm_rows())
                # B399: the worker processes may go once an action is done.
                from . import measure_pool as _pool
                _pool.close_pool()
                test_panel.remember_duration(action.code, seconds)
                self._test_result.emit(action.code, text)
                results.append((action.code, text))
            return results

        def on_done(results: list[tuple[str, str]]) -> None:
            # B369: the results are already there; only the closer here.
            self._status.setText(t("test_done").format(
                code=", ".join(code for code, _ in results)))

        self._run(task, on_done, cancel_event=cancel)

    def _show_test_bars(self, labels: list[str]) -> None:
        # B398: fresh run, fresh slots - otherwise the second line still
        # names projects from the previous action.
        self._slot_names = {}
        for chip in getattr(self, "_slot_chips", ()):
            chip.setText("")
            chip.setStyleSheet(self._CHIP_IDLE)
        """Twee balken tijdens het testen (TIJDELIJK).

        Dezelfde machinerie als de parallelle detectie van B90; alleen
        staat er nu een actienummer plus projectnaam boven in plaats van
        een spoornaam.
        """
        for index, bar in enumerate(self._progress_bars):
            actief = index < max(1, len(labels))
            self._progress_rows[index].setVisible(actief)
            self._progress_labels[index].setVisible(actief)
            if actief:
                self._progress_labels[index].setText(
                    labels[index] if index < len(labels) else "")
                bar.setRange(0, 0)

    #: B398: how wide the second line may get before the song titles are
    #: dropped. The line has to stay ONE line - the user asked for two
    #: rows and two rows only - so past this the names give way to a
    #: count. Better an honest "9 werkplekken" than a title cut in half.

    #: B402: the slot number meaning "the action as a whole" instead of
    #: one work slot. A channel of its own, so the top row can show how
    #: far 1.5.10 is while the slots show what they are chewing on. The
    #: two used to fight over the same bar and the round always won -
    #: which is why an eight-minute run sat at 11%.
    ACTION_SLOT = -1

    #: B402: how a chip looks. Busy is filled, idle is faint, so the row
    #: shows at a glance how many slots are really working - which is
    #: what the user went to the task manager for.
    _CHIP_BUSY = ("background:#e8f0d8; border:1px solid #b5c99a;"
                  " border-radius:8px; padding:1px 6px;")
    _CHIP_IDLE = ("background:#f4f4f4; border:1px solid #dcdcdc;"
                  " border-radius:8px; padding:1px 6px; color:#999;")

    def _on_test_progress(self, slot: int, name: str, done: int,
                          total: int) -> None:
        """A work slot reports what it is busy with (B357, B398).

        There are two rows and there will stay two rows, but since B396
        there can be nine work slots. So the rows changed meaning: the
        first is the run as a whole, the second is who is busy right now.
        Before this, slot 3 to 9 simply fell off the end of
        ``_progress_bars`` and the user saw two queues while nine were
        running.
        """
        self._progress_rows[0].setVisible(True)
        self._progress_labels[0].setVisible(True)

        if slot == self.ACTION_SLOT:
            # B402: the action as a whole. THIS is the row to read "how
            # far is 1.5.10" from - not how far one round is.
            bar = self._progress_bars[0]
            if total > 0:
                bar.setRange(0, total)
                bar.setValue(min(done, total))
            else:
                bar.setRange(0, 0)
            self._progress_labels[0].setText(
                f"{name}  {done}/{total}" if total > 0 else name)
            return
        if slot < 0:
            return

        self._slot_names[slot] = name
        self._show_slot_chips(max(len(self._slot_names),
                                  max(self._slot_names) + 1))
        chip = self._slot_chips[slot]
        chip.setText(name.split("  ")[-1])
        chip.setStyleSheet(self._CHIP_BUSY)
        chip.setToolTip(name)

        # The second bar keeps the progress WITHIN the current round.
        # B409: without a label. It named the same projects that are on
        # the chips just below it, only cut off on line width - a line
        # that only repeated what was already legible.
        self._progress_rows[1].setVisible(True)
        self._progress_labels[1].setVisible(False)
        second = self._progress_bars[1]
        if total > 0:
            second.setRange(0, total)
            second.setValue(min(done, total))
        else:
            second.setRange(0, 0)

    def _show_slot_chips(self, count: int) -> None:
        """Make sure there are exactly ``count`` chips (B402)."""
        while len(self._slot_chips) < count:
            chip = QLabel("")
            chip.setStyleSheet(self._CHIP_IDLE)
            self._slot_layout.addWidget(chip)
            self._slot_chips.append(chip)
        for number, chip in enumerate(self._slot_chips):
            chip.setVisible(number < count)
        self._slot_row.setVisible(count > 0)

    def _build_progress_group(self) -> QWidget:
        # B398: which work slot is busy with what. A dict and not a list,
        # because the number of slots is decided per action now (two for
        # Python work, nine for the measurement, see ``measure_pool``).
        # Deliberately created HERE and not as a class attribute: a
        # mutable class attribute is shared by every window, and then a
        # second window would inherit the first one's work slots.
        self._slot_names: dict = {}
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        # Two labelled bars; the second is only visible with parallel
        # detection (original + karaoke at once, B90).
        self._progress_rows: list[QWidget] = []
        self._progress_labels: list[QLabel] = []
        self._progress_bars: list[QProgressBar] = []
        for _ in range(2):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            label = QLabel("")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            row.addWidget(label)
            row.addWidget(bar, stretch=1)
            widget = QWidget()
            widget.setLayout(row)
            outer.addWidget(widget)
            self._progress_rows.append(widget)
            self._progress_labels.append(label)
            self._progress_bars.append(bar)
        self._progress = self._progress_bars[0]   # generic (single) bar
        self._progress2 = self._progress_bars[1]
        self._progress_rows[1].setVisible(False)
        self._progress_labels[0].setVisible(False)

        # B402: one chip per work slot. The second bar showed a list of
        # names on one line, and with nine slots that line ran out of
        # room while the top bar showed the progress WITHIN a round - so
        # the user could not read how far 1.5.10 was as a whole. Now the
        # top row is the action and every slot has its own chip saying
        # what it is chewing on.
        self._slot_row = QWidget()
        self._slot_layout = QHBoxLayout(self._slot_row)
        self._slot_layout.setContentsMargins(0, 0, 0, 0)
        self._slot_layout.setSpacing(4)
        self._slot_chips: list[QLabel] = []
        self._slot_row.setVisible(False)
        outer.addWidget(self._slot_row)

        #: Coupling track -> bar during (parallel) detection.
        self._track_bars: dict[str, QProgressBar] = {}

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        self._stop_button = QPushButton(t("stop"))
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._stop_current)
        self._status = QLabel(t("ready"))
        bottom.addWidget(self._stop_button)
        bottom.addWidget(self._status, stretch=2)
        outer.addLayout(bottom)
        return container

    def _start_track_progress(self, tracks: list[str]) -> None:
        """One bar per track (with track name) before (parallel) detection."""
        self._track_bars = {}
        for index, bar in enumerate(self._progress_bars):
            active = index < len(tracks)
            self._progress_rows[index].setVisible(active)
            if active:
                track = tracks[index]
                self._progress_labels[index].setVisible(True)
                self._progress_labels[index].setText(f"{t(track)}:")
                bar.setRange(0, 0)  # 'busy' until the first progress
                self._track_bars[track] = bar

    def _clear_slot_chips(self) -> None:
        """Empty the work-slot chips (B430/B435).

        Also BETWEEN rounds: 1.5.11 is four investigations under one
        button, and the chips of the previous one stayed on screen while
        the next was already running.
        """
        self._slot_names = {}
        for chip in getattr(self, "_slot_chips", ()):
            chip.setText("")
            chip.setStyleSheet(self._CHIP_IDLE)
            chip.setToolTip("")
        if getattr(self, "_slot_row", None) is not None:
            self._slot_row.setVisible(False)

    def _reset_track_progress(self) -> None:
        """Hide the second bar and restore the labels afterwards.

        B430: the work-slot chips go too. This routine has cleaned up
        after every action since B90, but the chips arrived later (B402)
        and were never added - they were only emptied at the START of a
        next test run. So after a finished run they stayed on screen with
        the names of the last projects, next to bars that had already been
        reset.
        """
        self._track_bars = {}
        self._progress_rows[1].setVisible(False)
        self._progress_labels[0].setVisible(False)
        for label in self._progress_labels:
            label.setText("")
        self._clear_slot_chips()

    #: B356: seconds a polite abort gets before the external programs
    #: are killed. Whisper looks at the cancel event per segment and
    #: stops within a second; ffmpeg and Demucs look at nothing at all
    #: and would otherwise finish their three minutes.
    HARD_STOP_MS = 5000

    def _stop_current(self) -> None:
        """Cancel the running (cancellable) task."""
        cancel = getattr(self, "_active_cancel", None)
        if cancel is not None:
            cancel.set()
            self._status.setText(t("cancelling"))
            self._stop_button.setEnabled(False)
            self._log(t("cancelling"))
            QTimer.singleShot(self.HARD_STOP_MS, self._stop_hard)

    def _stop_hard(self) -> None:
        """Really kill what is still running (B356).

        Only when the task is still going: a neatly finished abort must
        not shoot down the programs of a NEXT run.
        """
        if self._worker is None or not self._worker.isRunning():
            return
        from . import proc
        if proc.terminate_all():
            self._status.setText(t("cancel_hard"))
            self._log(t("cancel_hard"))

    def _build_waveform_group(self) -> QGroupBox:
        self._waveform_group = QGroupBox(t("waveform_group"))
        layout = QVBoxLayout(self._waveform_group)
        self._waveform = WaveformWidget()
        layout.addWidget(self._waveform)
        self._waveform_group.setVisible(False)
        return self._waveform_group

    def _build_fragment_group(self) -> QGroupBox:
        self._fragment_group = QGroupBox(t("fragments_group"))
        layout = QVBoxLayout(self._fragment_group)
        self._fragment_container = QWidget()
        self._fragment_layout = QVBoxLayout(self._fragment_container)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._fragment_container)
        # Same minimum height as the sound cluster group (B284): both sit
        # in the same slot in a QStackedWidget, so they must be equal in
        # size - otherwise the window jumps when switching.
        scroll.setMinimumHeight(_CLUSTER_FRAGMENT_MIN_H)
        layout.addWidget(scroll, stretch=1)
        edit_row = QHBoxLayout()
        editor_button = QPushButton(t("damping_editor_button"))
        editor_button.clicked.connect(self._open_damping_editor)
        edit_row.addWidget(editor_button)
        reset_button = QPushButton(t("damping_reset"))
        reset_button.clicked.connect(self._reset_damping)
        edit_row.addWidget(reset_button)
        edit_row.addStretch()
        layout.addLayout(edit_row)
        self._fragment_rows: list[tuple[QCheckBox, Any]] = []
        return self._fragment_group

    def _refresh_fragments(self, result: pipeline.KaraokeResult) -> None:
        """(Re)fill the fragment list; ticks show the active damping."""
        while self._fragment_layout.count():
            item = self._fragment_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._fragment_rows = []
        active = {(round(iv.start, 2), round(iv.end, 2))
                  for iv in result.intervals}
        for interval in result.all_intervals:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 0, 2, 0)
            checkbox = QCheckBox(
                f"{_format_time(interval.start)} - "
                f"{_format_time(interval.end)}  "
                f"({interval.end - interval.start:.2f} s)  "
                f"{interval.label}")
            checkbox.setChecked(
                (round(interval.start, 2), round(interval.end, 2)) in active)
            checkbox.toggled.connect(
                lambda _=False: self._apply_fragment_changes())
            row_layout.addWidget(checkbox, stretch=1)
            self._fragment_layout.addWidget(row)
            self._fragment_rows.append((checkbox, interval))
        self._fragment_layout.addStretch()
        # "Damped fragments" is now active; the sound cluster group
        # disappears entirely (empty or not) - what was ticked there is
        # here (B283/B284: both in the same stack slot, so this switches
        # instead of hiding).
        self._show_fragment_group()

    def _apply_fragment_changes(self) -> None:
        """Process ticking/unticking: store, damp again and export."""
        if self._worker is not None and self._worker.isRunning():
            return  # is rebuilt as soon as the running task is finished
        exclusions = [(interval.start, interval.end)
                      for checkbox, interval in self._fragment_rows
                      if not checkbox.isChecked()]
        pipeline.set_fragment_exclusions(self._context, exclusions)
        context = self._context

        def task(progress: Any, message: Any) -> dict[str, Any]:
            message(t("damping_reapply"))
            result = pipeline.run_karaoke(context)
            message(t("reexporting"))
            exported = pipeline.run_export(context)
            return {"karaoke": result, "export": exported,
                    **_waveform_payload(result.output_wav)}

        def on_done(payload: dict[str, Any]) -> None:
            self._show_waveform(payload)
            self._refresh_fragments(payload["karaoke"])
            self._log(t("fragments_applied_log").format(
                export=payload['export']))

        self._run(task, on_done)

    def _open_damping_editor(self) -> None:
        """Open the waveform editor to edit the damping manually.

        Only requires that step 1 (prepare source tracks) has run - no
        longer step 4 (cluster selection), so that "back from original"
        is also reachable without a cluster selection (B282).
        """
        context = self._context
        try:
            pipeline.stored_wav(context, pipeline.TRACK_KARAOKE)
        except PipelineError:
            QMessageBox.information(
                self, t("editor_damping_title"), t("damping_need_step_body"))
            return

        def task(progress: Any, message: Any) -> dict[str, Any]:
            message(t("karaoke_wave_loading"))
            step = context.store.get_step("karaoke")
            damped = Path(step["wav"]) if step and Path(step["wav"]).exists() \
                else None
            audio_path = damped or pipeline.stored_wav(
                context, pipeline.TRACK_KARAOKE)
            data, sample_rate = audio_module.load_audio(audio_path)
            duration = data.shape[0] / sample_rate
            peaks = waveform.compute_peaks(data,
                                           max(1000, int(duration * 100)))
            return {"peaks": peaks, "duration": duration,
                    "audio": audio_path,
                    "intervals": pipeline.current_damping_intervals(context),
                    "restore_intervals": [
                        (iv.start, iv.end, iv.label)
                        for iv in pipeline.restore_fragments(context)]}

        def on_done(payload: dict[str, Any]) -> None:
            from .damping_editor import DampingEditorDialog

            def apply_and_reload(spans: list, restore_spans: list) -> dict:
                # Synchronous: apply damping/restore, export and return
                # the new waveform so that the editor shows it.
                result = pipeline.apply_manual_damping(
                    context, spans, restore_spans=restore_spans)
                exported = pipeline.run_export(context)
                data, sample_rate = audio_module.load_audio(
                    result.output_wav)
                duration = data.shape[0] / sample_rate
                peaks = waveform.compute_peaks(
                    data, max(1000, int(duration * 100)))
                self._show_waveform({"karaoke": result, "peaks": peaks,
                                     "duration": duration})
                self._refresh_fragments(result)
                self._log(t("damping_applied_log").format(export=exported))
                return {"peaks": peaks, "duration": duration,
                        "audio": result.output_wav}

            dialog = DampingEditorDialog(
                payload["peaks"], payload["duration"], payload["intervals"],
                payload["audio"], apply_and_reload,
                restore_intervals=payload["restore_intervals"], parent=self)
            dialog.exec()

        self._run(task, on_done)

    def _reset_damping(self) -> None:
        """Reset the karaoke back to the original sound."""
        if self._worker is not None and self._worker.isRunning():
            return
        pipeline.reset_damping(self._context)
        self._waveform_group.setVisible(False)
        self._show_cluster_group()
        self._log(t("damping_reset_log"))

    def _build_cluster_group(self) -> QGroupBox:
        group = QGroupBox(t("clusters_group"))
        self._cluster_group = group
        layout = QVBoxLayout(group)
        self._cluster_container = QWidget()
        self._cluster_layout = QVBoxLayout(self._cluster_container)
        self._cluster_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._cluster_container)
        # Same minimum height as the fragment group (B284, see
        # _CLUSTER_FRAGMENT_MIN_H); the field may grow with the window
        # and fills its group (stretch), so that no empty frame appears
        # around it (B216/B211).
        scroll.setMinimumHeight(_CLUSTER_FRAGMENT_MIN_H)
        layout.addWidget(scroll, stretch=1)
        row = QHBoxLayout()
        hint = QLabel(t("clusters_hint"))
        hint.setStyleSheet("color: #666;")
        self._open_report_button = QPushButton(t("open_report"))
        self._open_report_button.clicked.connect(self._open_report)
        self._open_report_button.setEnabled(False)
        row.addWidget(hint)
        row.addStretch()
        row.addWidget(self._open_report_button)
        layout.addLayout(row)
        return group

    def _build_log_group(self) -> QWidget:
        """Messages (left) and live Activity (right), split 50/50."""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)

        # Modest minimum height so that the window can also get smaller
        # vertically (B187); growing is allowed via the stretch above.
        panel_min_h = 110
        messages = QGroupBox(t("log_group"))
        m_layout = QVBoxLayout(messages)
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMinimumHeight(panel_min_h)
        m_layout.addWidget(self._log_view)

        activiteit = QGroupBox(t("activity_group"))
        a_layout = QVBoxLayout(activiteit)
        self._activity_view = QPlainTextEdit()
        self._activity_view.setReadOnly(True)
        self._activity_view.setMaximumBlockCount(1000)  # do not let it fill
        self._activity_view.setMinimumHeight(panel_min_h)
        a_layout.addWidget(self._activity_view)

        row.addWidget(messages, stretch=1)
        row.addWidget(activiteit, stretch=1)

        # Mirror the root log lines (INFO+, as previously in the cmd) to
        # the activity panel; thread-safe via a Qt signal.
        from .logger import GUI_FORMAT
        self._log_bridge = _LogBridge()
        self._log_bridge.message.connect(self._activity_view.appendPlainText)
        handler = _QtLogHandler(self._log_bridge)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(GUI_FORMAT))
        logging.getLogger().addHandler(handler)
        self._log_handler = handler
        return container

    # -- Input files -------------------------------------------------------

    def _refresh_inputs(self) -> None:
        """Update the status lines of the input files."""
        for stem, label in self._input_labels.items():
            found = filesystem.find_audio_file(self._context.paths.input_dir,
                                               stem)
            if found is None:
                # Karaoke can also come via 'Karaoke from original' (B186).
                label.setText(t("missing_choose_karaoke")
                              if stem == pipeline.TRACK_KARAOKE
                              else t("missing_choose"))
                label.setStyleSheet("color: #b3261e;")
            elif (stem == pipeline.TRACK_KARAOKE
                    and pipeline.input_origin(self._context, stem) is None
                    and self._context.store.get_meta("karaoke_from_original")):
                # B335: this karaoke was not chosen but made from the
                # original with Demucs. Then "karaoke.wav" says nothing
                # and where it comes from says everything. The marker
                # lapses along with input:karaoke, so as soon as a real
                # karaoke is chosen the name appears again by itself.
                label.setText(t("karaoke_from_original_label"))
                label.setStyleSheet("color: #1b7f3b;")
            else:
                # Show the original name the user chose (B206), with
                # fallback to the under-the-hood name.
                label.setText(pipeline.input_display_name(
                    self._context, stem, found.name))
                label.setStyleSheet("color: #1b7f3b;")
        input_dir = self._context.paths.input_dir
        logos = sorted(input_dir.glob("logo.*"))
        statuses = {
            "Songtekst": (input_dir / "songtekst.txt").exists()
            and pipeline.input_display_name(
                self._context, "lyrics", "songtekst.txt"),
            "Karaoketekst": (input_dir / "karaoketekst.txt").exists()
            and pipeline.input_display_name(
                self._context, "karaoke_text", "karaoketekst.txt"),
            "Logo": bool(logos) and pipeline.input_display_name(
                self._context, "logo", logos[0].name if logos else ""),
        }
        required = {"Songtekst", "Karaoketekst"}
        for name, value in statuses.items():
            label = self._extra_labels[name]
            if value:
                label.setText(str(value))
                label.setStyleSheet("color: #1b7f3b;")
            elif name in required:
                label.setText(t("missing_required"))
                label.setStyleSheet("color: #b3261e;")
            else:
                label.setText(t("missing_video"))
                label.setStyleSheet("color: #666;")
        # Synchronise the title fields with the (possibly prefilled)
        # config on a project change (B185).
        video = self._context.config.video
        for key, field in getattr(self, "_meta_fields", {}).items():
            field_value = getattr(video, key, "")
            if field.text() != field_value:
                field.blockSignals(True)
                field.setText(field_value)
                field.blockSignals(False)

    def _choose_file(self, stem: str) -> None:
        """Choose a supported audio file and copy it to the input folder."""
        patronen = " ".join(f"*{ext}"
                            for ext in filesystem.SUPPORTED_EXTENSIONS)
        chosen, _ = QFileDialog.getOpenFileName(
            self, t("choose_file_for").format(stem=t(stem)),
            pipeline.input_start_dir(self._context, stem),   # B206
            t("filter_audio").format(patterns=patronen))
        if not chosen:
            return
        source = Path(chosen)
        input_dir = self._context.paths.input_dir
        input_dir.mkdir(parents=True, exist_ok=True)
        for extension in filesystem.SUPPORTED_EXTENSIONS:
            existing = input_dir / f"{stem}{extension}"
            if existing.exists():
                existing.unlink()
        target = input_dir / f"{stem}{source.suffix.lower()}"
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            QMessageBox.warning(self, t("copy_failed"), str(exc))
            return
        pipeline.set_input_origin(self._context, stem, source)   # B206
        if stem == pipeline.TRACK_ORIGINAL:
            # New original -> the derived Demucs mp3s are outdated (B215).
            pipeline.remove_demucs_stems(self._context)
        self._log(t("copied_untouched_log").format(
            name=source.name, target=target))
        # New audio -> everything derived from it lapses (B113/B311).
        # Also the project-wide marker "karaoke made from the original":
        # that survived a new ORIGINAL, after which the alignment was
        # skipped with offset 0 while the karaoke belonged to the
        # previous original.
        changed = ("input:original" if stem == pipeline.TRACK_ORIGINAL
                   else "input:karaoke")
        pipeline.invalidate(self._context, [changed])
        pipeline.remember_sources(self._context)
        self._log(t("derived_invalidated"))
        self._show_timing_lines()
        self._refresh_inputs()

    def _make_karaoke_from_original(self) -> None:
        """Make (on request) an instrumental from the original (Demucs)."""
        if not models.is_available("demucs"):
            QMessageBox.information(self, t("app_title"), t("demucs_missing"))
            return
        context = self._context

        def task(progress: Any, message: Any) -> Path:
            message(t("making_karaoke"))
            return pipeline.make_karaoke_from_original(context)

        def on_done(target: Path) -> None:
            self._log(t("karaoke_made"))
            self._refresh_inputs()

        self._run(task, on_done)

    # -- Steps -------------------------------------------------------------

    def _ensure_language_choice(self) -> bool:
        """Ask for a manual language choice if needed (B64).

        Only when there are lyrics and the detection is uncertain (top
        below the threshold) and no choice is stored yet. Returns
        ``False`` if the user cancels the dialog (detection is aborted).
        """
        context = self._context
        if pipeline.language_choice(context):
            return True
        candidates = pipeline.language_candidates(context)
        # B495: a passage in another SCRIPT is not a probability but a
        # fact, and the language detection cannot see it - it works on
        # Latin words. Ask which language Whisper should run in before
        # the transcription starts, because afterwards it costs a whole
        # run again.
        second = pipeline.second_language_of(context)
        if second is not None:
            code, number = second
            first = candidates[0][0] if candidates else "auto"
            chosen = self._ask_second_language(first, code, number)
            if chosen is None:
                self._log(t("lang_cancelled"))
                return False
            pipeline.set_language_choice(context, chosen)
            self._log(t("lang_chosen").format(code=chosen))
            return True
        if not candidates:
            return True  # no lyrics -> Whisper chooses by itself
        # Certain enough and not too close to number two (B208) -> auto.
        if candidates[0][1] >= pipeline.LANGUAGE_MIN_PROB \
                and not pipeline.language_ambiguous(candidates):
            return True
        code = self._ask_language(candidates)
        if code is None:
            self._log(t("lang_cancelled"))
            return False
        pipeline.set_language_choice(context, code)
        self._log(t("lang_chosen").format(code=code))
        return True

    def _ask_second_language(self, first: str, second: str,
                             number: int) -> str | None:
        """There is a passage in another script; in which language should
        Whisper run (B495)?"""
        keuzes = [t("lang_second_first").format(code=first),
                  t("lang_second_other").format(code=second),
                  t("lang_auto")]
        choice, ok = QInputDialog.getItem(
            self, t("lang_second_title"),
            t("lang_second_prompt").format(code=second, count=number),
            keuzes, 0, False)
        if not ok:
            return None
        if choice == keuzes[1]:
            return second
        if choice == keuzes[2]:
            return "auto"
        return first

    def _ask_language(self, candidates: list) -> str | None:
        """Show the top 3 language candidates with 'Other...' paging;
        return the chosen language code ('auto' = Whisper chooses by
        itself), or ``None``."""
        page = 0
        while True:
            chunk = candidates[page * 3:page * 3 + 3]
            if not chunk:
                page = 0
                chunk = candidates[:3]
            items = [f"{code}  ({prob:.0%})" for code, prob in chunk]
            items.append(t("lang_auto"))
            more = len(candidates) > (page + 1) * 3
            if more:
                items.append(t("lang_other"))
            choice, ok = QInputDialog.getItem(
                self, t("lang_uncertain_title"), t("lang_uncertain_prompt"),
                items, 0, False)
            if not ok:
                return None
            if more and choice == t("lang_other"):
                page += 1
                continue
            if choice == t("lang_auto"):
                return "auto"
            return choice.split(" ")[0]

    def _commit_pending_field(self) -> None:
        """Force storing a still-active input field before a step (B275).

        The title fields (karaoke title/artist/title) only store via
        ``editingFinished``, which normally fires as soon as the field
        loses focus. A mouse click on a button, however, does not always
        reliably take over that focus (depending on platform/style) - the
        step buttons (Detect/Couple/Analyse/Karaoke video) therefore
        sometimes still read the OLD value from ``self._context``, while
        the field itself already showed the new text. By explicitly
        releasing the focus of any active input field here,
        ``editingFinished`` always fires first - regardless of whether
        the button itself takes over the focus.
        """
        app = QApplication.instance()
        if app is None:
            return
        widget = app.focusWidget()
        if isinstance(widget, QLineEdit):
            widget.clearFocus()

    def _do_detect(self) -> None:
        self._commit_pending_field()
        if not self._ensure_language_choice():
            return
        context = self._context
        cancel = threading.Event()
        tracks = list(pipeline.enabled_tracks(context))
        parallel = (context.config.advanced.parallel_detection
                    and len(tracks) > 1)

        # Per-track progress bars (two when parallel, one otherwise, B90).
        self._start_track_progress(tracks)
        bridge = _TrackProgressBridge(self)
        bridge.progress.connect(self._on_track_progress)
        bridge.done.connect(self._on_track_done)

        def task(progress: Any,
                 message: Any) -> dict[str, pipeline.DetectResult]:
            message(t("detect_preparing"))
            pipeline.prepare_track(context, pipeline.TRACK_ORIGINAL)
            pipeline.prepare_track(context, pipeline.TRACK_KARAOKE)
            if not whisper.model_cached(context.config.whisper):
                message(t("detect_downloading"))
            message(t("detect_transcribing_parallel") if parallel
                    else t("detect_transcribing"))
            results = pipeline.detect_tracks(
                context, progress=bridge.progress.emit,
                cancelled=cancel.is_set, parallel=parallel,
                track_done=bridge.done.emit)
            if cancel.is_set():
                raise whisper.CancelledError()
            message(t("detect_aligning"))
            regions = None
            align_error = None
            try:
                regions = pipeline.run_alignment(context)
            except Exception as exc:  # noqa: BLE001
                align_error = str(exc)
            return {"results": results, "regions": regions,
                    "align_error": align_error}

        def on_done(payload: dict[str, Any]) -> None:
            for track, result in payload["results"].items():
                if result.from_cache:
                    self._log(t("detect_from_cache").format(
                        track=t(track), segments=len(result.segments)))
                else:
                    self._log(t("detect_ready").format(
                        track=t(track), segments=len(result.segments),
                        words=result.word_count))
            self._report_alignment(payload["regions"],
                                   payload["align_error"])

        self._run(task, on_done, cancel_event=cancel)

    def _report_alignment(self, regions, align_error) -> None:
        """Report the (automatic) alignment; warn on low confidence."""
        if align_error is not None or not regions:
            error = align_error or t("no_result")
            self._log(t("alignment_failed_log").format(error=error))
            QMessageBox.warning(
                self, t("alignment_failed_title"),
                t("alignment_failed_body").format(error=error))
            return
        best = max(region.confidence for region in regions)
        for region in regions:
            self._log(t("alignment_region_log").format(
                start=region.start, end=region.end,
                offset=region.offset * 1000, conf=region.confidence))
        if best < pipeline.ALIGN_MIN_CONFIDENCE:
            QMessageBox.warning(
                self, t("alignment_weak_title"),
                t("alignment_weak_body").format(conf=best))
        drift = pipeline.drift_ms(regions)
        if drift > pipeline.DRIFT_WARN_MS:
            if not self._ask_yes_no(
                    t("drift_title"), t("drift_body").format(drift=drift)):
                pipeline.collapse_alignment(self._context)
                self._log(t("drift_off_log"))
            else:
                self._log(t("drift_corrected_log").format(
                    drift=drift, count=len(regions)))

    def _require(self, ok: bool, message_key: str) -> bool:
        """Guard a step dependency; report which step is missing (B134)."""
        if not ok:
            QMessageBox.warning(self, t("prereq_title"), t(message_key))
        return ok

    def _open_word_couple(self) -> None:
        """Word coupling editor between step 1 and 2 (B121)."""
        self._commit_pending_field()
        context = self._context
        if not self._require(pipeline.has_transcription(context),
                             "prereq_need_detect"):
            return
        view = pipeline.word_coupling_view(context)
        if not view or not view.get("words"):
            QMessageBox.information(self, t("prereq_title"),
                                    t("couple_no_data"))
            return
        from .coupling_editor import CouplingEditorDialog

        def on_save(pins: dict) -> None:
            pipeline.set_word_pins(context, pins)
            # Everything built on the coupling has to be made again
            # (zinkoppeling, timing, video) - B311.
            pipeline.invalidate(context, ["word_coupling"])
            self._log(t("couple_saved").format(count=len(pins)))

        def on_save_transcript(transcript: list) -> None:
            # Store split/merged detected words (B153).
            pipeline.set_transcript_override(context, transcript)
            pipeline.invalidate(context, ["transcript_override"])  # B311

        def on_save_lyrics(lyrics: list) -> None:
            # Store split/merged lyrics words (B156). Cutting or merging
            # renumbers the lyrics words, so everything counting on those
            # positions (klemtonen, handmatige regeltijden) lapses - B311.
            pipeline.set_lyrics_override(context, lyrics)
            pipeline.invalidate(context, ["lyrics_override"])

        def on_mark(kind: str, word: str) -> bool:
            # B337: put the word in the list of the AUDIO language, so
            # every following project in that language benefits.
            changed, language = pipeline.mark_language_word(
                context, kind, word)
            if changed:
                self._log(t("mark_word_added").format(
                    word=word, language=language))
            else:
                self._log(t("mark_word_removed").format(
                    word=word, language=language))
            return True

        dialog = CouplingEditorDialog(view["transcript"], view["words"],
                                    on_save,
                                    on_save_transcript=on_save_transcript,
                                    on_save_lyrics=on_save_lyrics,
                                    parent=self,
                                    filtered=view.get("filtered", ()),  # B309
                                    on_mark=on_mark,                    # B337
                                    found_status=view.get(
                                        "found_status"),               # B502
                                    in_lyrics=view.get(
                                        "in_lyrics", ()))              # B521
        dialog.exec()
        self._report_missing(context)                                   # B350

    def _report_missing(self, context) -> None:
        """Report what was heard but is not in the lyrics (B350).

        Deliberately no pop-up: it is a hint, not an error, and with a
        repetitive outro there can be a few of them. One line in the
        status area and the details in the log.
        """
        try:
            missing = pipeline.missing_repetitions(context)
        except Exception:  # noqa: BLE001 - a hint must never break a step
            logger.exception(t("log_missing_failed"))
            return
        repeats = [m for m in missing if m["repetition"]]
        unknown = [m for m in missing if not m["repetition"]]
        for item in missing:
            self._log((t("missing_repeat_log") if item["repetition"]
                       else t("missing_unknown_log")).format(
                          start=item["start"], line=item["line"] + 1,
                          text=item["text"]))
        if not repeats and not unknown:
            return
        parts = []
        if repeats:
            spots = ", ".join(t("missing_spot").format(
                start=m["start"], line=m["line"] + 1) for m in repeats[:3])
            more = (t("missing_more").format(count=len(repeats) - 3)
                    if len(repeats) > 3 else "")
            parts.append(t("missing_repeat_summary").format(
                count=len(repeats), spots=spots, more=more))
        if unknown:
            parts.append(t("missing_unknown_summary").format(
                count=len(unknown)))
        self._status.setText(" ".join(parts))

    def _do_analyse(self) -> None:
        self._commit_pending_field()
        context = self._context
        if not self._require(pipeline.has_transcription(context),
                             "prereq_need_detect"):
            return

        def task(progress: Any, message: Any) -> dict[str, AnalyseResult]:
            message(t("analysing"))
            return pipeline.run_analyses(context)

        self._run(task, self._show_analyse_results)

    def _do_karaoke(self) -> None:
        self._commit_pending_field()
        context = self._context
        if not self._require(pipeline.has_transcription(context),
                             "prereq_need_detect"):
            return
        # B428: the analysis is only needed for DAMPING. Someone who just
        # wants to put a fragment back from the original has nothing to
        # select, and used to be sent through step 3 for a selection that
        # was then thrown away.
        if not pipeline.restore_fragments(context) and \
                not self._require(pipeline.has_analysis(context),
                                  "prereq_need_analyse"):
            return

        def task(progress: Any, message: Any) -> dict[str, Any]:
            message(t("karaoke_adjusting"))
            result = pipeline.run_karaoke(context)
            message(t("exporting"))
            exported = pipeline.run_export(context)
            message(t("computing_wave"))
            return {"karaoke": result, "export": exported,
                    **_waveform_payload(result.output_wav)}

        def on_done(payload: dict[str, Any]) -> None:
            result: pipeline.KaraokeResult = payload["karaoke"]
            settings = self._context.config.karaoke
            self._log(t("karaoke_adjusted_log").format(
                count=len(result.intervals),
                seconds=result.total_damped_s,
                gain=settings.gain_db, export=payload['export']))
            self._show_waveform(payload)
            self._refresh_fragments(result)

        self._run(task, on_done)

    def _show_analyse_results(self,
                              results: dict[str, AnalyseResult]) -> None:
        """Show the found clusters per track with check boxes."""
        self._analyse_results = results
        # New step 3 results: the sound cluster group is relevant again
        # (B283); "Damped fragments" only returns after a new step 4.
        self._show_cluster_group()
        while self._cluster_layout.count():
            item = self._cluster_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._cluster_boxes = []
        for track, result in results.items():
            self._log(t("analyse_done_log").format(
                track=t(track), words=result.stats.words,
                clusters=len(result.clusters), report=result.html_path))
            header = QLabel(f"—  {t(track).upper()}  —")
            header.setStyleSheet("font-weight: 600; margin-top: 6px;")
            self._cluster_layout.addWidget(header)
            suggested = set(result.suggested)
            for cluster in result.clusters:
                frame = QFrame()
                frame.setFrameShape(QFrame.Shape.StyledPanel)
                box_layout = QVBoxLayout(frame)
                tip = (t("cluster_suggestion_tag")
                       if cluster.id in suggested else "")
                checkbox = QCheckBox(t("cluster_checkbox").format(
                    id=cluster.id, label=cluster.label.upper(),
                    freq=cluster.frequency,
                    conf=cluster.avg_confidence, tip=tip))
                checkbox.setChecked(False)  # unticked by default
                checkbox.toggled.connect(
                    lambda _=False, tr=track: self._persist_selection(tr))
                variants = ", ".join(f"{member.upper()} ({count}x)"
                                     for member, count in cluster.members[:6])
                detail = QLabel(t("variants_label").format(variants=variants))
                detail.setWordWrap(True)
                box_layout.addWidget(checkbox)
                box_layout.addWidget(detail)
                self._cluster_layout.addWidget(frame)
                self._cluster_boxes.append((checkbox, track, cluster.id))
            # Nothing selected by default; store empty selection at once.
            self._persist_selection(track, log=False)
            if suggested:
                self._log(t("suggestion_log").format(
                    track=t(track),
                    clusters=', '.join(map(str, sorted(suggested)))))
        self._cluster_layout.addStretch()
        self._open_report_button.setEnabled(True)

    def _persist_selection(self, track: str, log: bool = True) -> None:
        """Store the current selection of one track (on every change)."""
        result = self._analyse_results.get(track)
        if result is None:
            return
        selection = [cluster_id for checkbox, box_track, cluster_id
                     in self._cluster_boxes
                     if box_track == track and checkbox.isChecked()]
        pipeline.save_cluster_selection(self._context, track, selection,
                                        result.json_path,
                                        len(result.clusters))
        if log:
            labels = [cluster.label for cluster in result.clusters
                      if cluster.id in set(selection)]
            self._log(t("selection_saved_log").format(
                track=t(track),
                labels=', '.join(labels) if labels else t("none_word")))

    def _show_waveform(self, payload: dict[str, Any]) -> None:
        """Show the waveform with the damped fragments."""
        result: pipeline.KaraokeResult = payload["karaoke"]
        self._waveform.set_data(
            payload["peaks"], payload["duration"],
            [(interval.start, interval.end)
             for interval in result.intervals])
        self._waveform_group.setVisible(True)

    def _open_report(self) -> None:
        for result in self._analyse_results.values():
            pipeline.open_in_browser(result.html_path)

    # -- Background tasks ----------------------------------------------------

    def _run(self, task: Task, on_done: Callable[[Any], None],
             cancel_event: "threading.Event | None" = None) -> None:
        """Start a task in the background and connect the signals.

        ``cancel_event`` (if supplied) activates the Stop button; the
        task checks that event itself and stops neatly.
        """
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, t("busy_title"),
                                    t("busy_running_body"))
            return
        self._active_cancel = cancel_event
        self._set_busy(True)
        self._stop_button.setEnabled(cancel_event is not None)
        import time as _time
        self._phase_text = t("busy_phase")
        self._phase_start = _time.monotonic()
        self._elapsed_timer.start()
        worker = _Worker(task)
        worker.progress.connect(self._on_progress)
        worker.message.connect(self._on_message)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)

        def finish(result: Any) -> None:
            self._set_busy(False)
            on_done(result)

        worker.done.connect(finish)
        self._worker = worker
        worker.start()

    def _on_cancelled(self) -> None:
        """Handling after the user has cancelled a task."""
        self._set_busy(False)
        try:
            pipeline.cleanup_after_cancel(self._context)
        except Exception:  # noqa: BLE001 - cleanup must not crash
            logger.exception(t("log_cleanup_failed"))
        self._log(t("cancelled_done"))

    def _set_busy(self, busy: bool) -> None:
        for button in self._step_buttons:
            button.setEnabled(not busy)
        for checkbox, _ in self._fragment_rows:
            checkbox.setEnabled(not busy)
        if busy:
            self._progress.setRange(0, 0)  # 'busy' animation
            self._video_progress.setRange(0, 0)  # B278
            self._show_elapsed = True
        else:
            self._elapsed_timer.stop()
            self._show_elapsed = False
            for bar in self._progress_bars:
                bar.setRange(0, 100)
                bar.setValue(0)
            self._reset_track_progress()
            self._status.setText(t("ready"))
            self._video_progress.setRange(0, 100)  # B278
            self._video_progress.setValue(0)
            self._video_status.setText(t("ready"))
            self._stop_button.setEnabled(False)
            self._active_cancel = None
            self._release_busy_button()      # busy button normal again (B229)

    # -- Busy colour per button (B229) -----------------------------------

    def _install_busy_indicator(self) -> None:
        """Make every button 'yellow' (busy) while its action runs (B229).

        We hook afterwards onto the click of all buttons: the own handler
        runs first, then we colour the button. If the handler starts a
        background task, it stays yellow until that is finished;
        otherwise we set it back immediately (a short flash).
        Double-clicking is still caught with the message.

        Stop is deliberately left out (B323): it starts no task of its
        own but ends the running one. Colouring it in made it the owner
        of the busy colour, after which the step button that was really
        running stayed yellow for good.
        """
        self._busy_buttons: set = set()
        self._worker_before_click = None
        for button in self.findChildren(QPushButton):
            if button is self._stop_button:
                continue
            # ``pressed`` fires BEFORE ``clicked``, and therefore before
            # the button's own handler; that is the only moment at which
            # we can still see whether a task was already running (B341).
            button.pressed.connect(self._remember_worker)
            button.clicked.connect(
                lambda _=False, b=button: self._mark_busy_click(b))

    def _remember_worker(self) -> None:
        """Note which task was running before this click (B341)."""
        self._worker_before_click = self._worker

    def _mark_busy_click(self, button) -> None:
        # B323: Stop never gets the busy colour (it ends a task, it does
        # not start one), and a click while a task is running does not
        # take the colour over - the running button keeps it until it is
        # really done.
        if button is self._stop_button:
            return
        # B341: that test used to read "is a task running", but we only
        # get here AFTER the button's own handler, and that handler has
        # already set and started its worker - ``isRunning()`` is true
        # the moment ``start()`` has been called. Every step button thus
        # stepped aside for its own task, so the busy colour had been
        # dead since B323. The question is not whether something is
        # running but whether something was ADDED: a worker other than
        # the one from before the click belongs to this click.
        worker = self._worker
        if (worker is not None and worker.isRunning()
                and worker is self._worker_before_click):
            return
        self._busy_buttons.add(button)
        self._apply_busy_style(button, True)
        QTimer.singleShot(0, self._busy_settle)

    def _busy_settle(self) -> None:
        if self._worker is None or not self._worker.isRunning():
            self._release_busy_button()

    def _release_busy_button(self) -> None:
        """Take the busy colour off every button that is still marked.

        A set, not one button (B323): if more than one button ever ends
        up marked, they all go back to normal instead of leaving one
        yellow behind.
        """
        for button in list(getattr(self, "_busy_buttons", ())):
            self._apply_busy_style(button, False)
        self._busy_buttons = set()

    def _apply_busy_style(self, button, busy: bool) -> None:
        if busy:
            color = (self._context.config.theme.button_active or "#f2c200")
            button.setStyleSheet(f"background-color: {color};")
        else:
            button.setStyleSheet("")   # back to theme/default

    def _on_progress(self, done_s: float, total_s: float) -> None:
        if total_s > 0:
            # There is a real percentage; then the seconds counter can go.
            self._show_elapsed = False
            percent = int(min(100.0, done_s / total_s * 100))
            self._progress.setRange(0, 100)
            self._progress.setValue(percent)
            text_value = t("progress_pct").format(
                pct=percent, done=done_s, total=total_s)
            self._status.setText(text_value)
            # B278: Video tab mirrors the same progress.
            self._video_progress.setRange(0, 100)
            self._video_progress.setValue(percent)
            self._video_status.setText(text_value)

    def _on_track_progress(self, track: str, done_s: float,
                           total_s: float) -> None:
        """Update the bar of one track (parallel detection, B90)."""
        bar = self._track_bars.get(track)
        if bar is None or total_s <= 0:
            return
        percent = int(min(100.0, done_s / total_s * 100))
        bar.setRange(0, 100)
        bar.setValue(percent)

    def _on_track_done(self, track: str) -> None:
        """Freeze the bar of a finished track at 100% + 'done' (B96)."""
        bar = self._track_bars.get(track)
        if bar is not None:
            bar.setRange(0, 100)
            bar.setValue(100)
        index = {b: i for i, b in enumerate(self._progress_bars)}.get(bar)
        if index is not None:
            self._progress_labels[index].setText(
                t("track_done").format(track=t(track)))

    def _on_message(self, text: str) -> None:
        import time as _time
        self._phase_text = text
        self._phase_start = _time.monotonic()
        self._status.setText(text)
        self._video_status.setText(text)  # B278
        self._log(text)

    def _tick_elapsed(self) -> None:
        """Show rising seconds for the current phase (e.g. model
        download), so that it is visible that the program still works."""
        import time as _time
        # B368: own state, not the maximum of a bar that the test panel
        # now writes to as well.
        if self._show_elapsed:
            elapsed = int(_time.monotonic() - self._phase_start)
            self._status.setText(t("phase_elapsed").format(
                phase=self._phase_text, elapsed=elapsed))

    def _on_failed(self, text: str) -> None:
        self._set_busy(False)
        self._log(text)
        QMessageBox.warning(self, t("app_title"), text)

    def _log(self, text: str) -> None:
        self._log_view.appendPlainText(text)
        logger.info(t("log_gui"), text)

    def _log_view_only(self, text: str) -> None:
        """Only in the window (B369).

        The worker thread already wrote the line straight to the log
        file - that is the part that survives a crash. Logging it again
        would put every line in the file twice.
        """
        self._log_view.appendPlainText(text)

    def _on_test_result(self, code: str, text: str) -> None:
        """Result of one test action, as soon as it is done (B369)."""
        self._log_view_only(f"--- {code} ---")
        for line in str(text).splitlines():
            self._log_view_only(line)


def _escape_html(text: str) -> str:
    """Make text safe for the HTML display in the list."""
    import html as html_module
    return html_module.escape(text)


# B293: a literally identical copy of this function used to be here. The
# time display now lives in one place (``cluster.format_time``), so that
# the cluster report and the windows in the interface cannot drift apart.
_format_time = cluster_module.format_time


def _waveform_payload(wav_path: Path) -> dict[str, Any]:
    """Compute waveform data of a wav file (in the worker thread)."""
    data, sample_rate = audio_module.load_audio(wav_path)
    return {"peaks": waveform.compute_peaks(data, 2400),
            "duration": data.shape[0] / sample_rate}


def run_gui(context: AppContext) -> int:
    """Start the graphical interface.

    Returns:
        The exit code of the Qt application.
    """
    # On Windows the taskbar otherwise shows the (pythonw) default icon;
    # with an own AppUserModelID it picks the window icon of the app.
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "RoodWitteZangers.KaraokeTool")
        except Exception:  # noqa: BLE001 - nice-to-have
            logger.debug(t("log_appusermodelid_failed"))
    app = QApplication.instance() or QApplication([])
    app.setWindowIcon(_app_icon())          # also on the Windows taskbar
    window = MainWindow(context)
    window.show()
    return app.exec()
