"""KaraokeTool - the entry point of the application.

The only file that is started directly. All the logic lives in the
``modules`` package; start it through ``KaraokeToolGUI.bat``::

    python KaraokeTool.py    # start the graphical interface
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# On Windows Hugging Face otherwise logs a (harmless) warning about
# symlinks in the model cache. Switching it off BEFORE any model is
# loaded keeps the console clean.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Under pythonw.exe (the windowless start, B50) sys.stdout and
# sys.stderr are None. Some libraries write to them anyway - torch.hub
# during the model download for the forced alignment, for one - and then
# crash with "NoneType has no attribute 'write'" (B119). Replace them
# with a writable sink so that such prints do no harm.
if sys.stdout is None or sys.stderr is None:
    _devnull = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _devnull
    if sys.stderr is None:
        sys.stderr = _devnull

from modules import __version__

# v1.0.28: numba (librosa's onset search) keeps compiled code. Next to
# librosa in the venv that cache went bad on the laptop: every process
# that searched onsets died with an access violation (logs/crash.log,
# 5 October). A folder of the program's own in TEMP (the cache folder
# is emptied at every start), fresh per version - the processes of a
# pool inherit it.
import tempfile  # noqa: E402

os.environ.setdefault("NUMBA_CACHE_DIR", str(
    Path(tempfile.gettempdir()) / "KaraokeTool_numba" / __version__))
from modules import config as config_module
from modules import ffmpeg
from modules.filesystem import (ProjectPaths, ProjectStore, clean_cache,
                                clean_logs, ensure_directories)
from modules import translations
from modules.logger import setup_logging
from modules.pipeline import AppContext
from modules.translations import t


#: v1.0.26 (B674): kept open for the whole run - faulthandler writes into it
#: when the process dies natively, where logging can no longer.
_CRASH_FILE = None


def _install_crash_log(logs_dir: Path) -> None:
    """A native crash (a DLL, memory running out) ended the program twice
    without a line in the log: the Python stacks then go to
    ``logs/crash.log``."""
    global _CRASH_FILE
    import faulthandler
    import time

    try:
        Path(logs_dir).mkdir(parents=True, exist_ok=True)
        _CRASH_FILE = open(Path(logs_dir) / "crash.log", "a",
                           encoding="utf-8")
        _CRASH_FILE.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} "
                          f"v{__version__} pid {os.getpid()}\n")
        _CRASH_FILE.flush()
        faulthandler.enable(file=_CRASH_FILE, all_threads=True)
        # v1.0.27: the processes of a pool write there too.
        os.environ["KT_CRASH_LOG"] = str(Path(logs_dir) / "crash.log")
    except (OSError, RuntimeError, ValueError):
        pass


def _install_excepthook() -> None:
    """Log every uncaught error in full to the log file.

    Without this a crash in a Qt callback (the drawing of the editor,
    say) disappears without a trace; with this hook the traceback is
    always in ``logs/``, so a crash can be traced back.
    """
    crash_logger = logging.getLogger("crash")

    def hook(exc_type, exc, tb) -> None:
        crash_logger.critical(t("log_uncaught_crash"),
                              exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


def main() -> int:
    """Initialise the project and start the interface.

    Returns:
        Exit code for the operating system (0 = success).
    """
    from modules import filesystem as _fs
    app_root = Path(__file__).resolve().parent
    # Data (input/output/cache/logs/config) to a writable folder; with a
    # read-only app location (Program Files, say) to %LOCALAPPDATA%
    # (B221).
    root = _fs.resolve_data_root(app_root)
    paths = ProjectPaths(root=root)
    ensure_directories(paths)
    # v1.0.20: what the launcher's card test found - the card only for
    # what really worked on it (see modules/cuda.py).
    from modules import cuda as _cuda
    _cuda.use_card_file(paths.config_dir / "cuda.json")
    # v1.0.20: how long the long steps took before, to say how long
    # they still take.
    from modules import step_times as _step_times
    _step_times.use_file(paths.config_dir / "step_times.json")
    # v1.0.11: the language BEFORE the first log line. The settings are
    # loaded properly further down, but by then the start of the log has
    # been written, and it would always have been Dutch. Only the one
    # field is read here, raw - loading is what may fail, and a failure
    # has to be logged in the right language too.
    translations.set_language(
        config_module.read_interface_language(paths.config_file) or "nl")
    setup_logging(paths.logs_dir)
    _install_crash_log(paths.logs_dir)
    logger = logging.getLogger(__name__)
    _install_excepthook()
    logger.info(t("log_app_started"), __version__)

    if not paths.config_file.exists():
        config_module.save_config(config_module.default_config(), paths.config_file)
        logger.info(t("log_default_config_created"), paths.config_file)

    try:
        app_config = config_module.load_config(paths.config_file)
    except config_module.ConfigError:
        logger.exception(t("log_config_unreadable"))
        print(t("console_config_error").format(path=paths.config_file))
        return 1

    from dataclasses import replace

    from modules import filesystem, model_register
    translations.set_language(app_config.interface.language)

    # B361: neutralise every switched-off model at once, before anything
    # is computed. Each one logs itself with its name and its reason, so
    # nothing is ever quietly off.
    model_register.apply_settings(app_config.models)
    switched_off = model_register.apply_disabled()

    # B443/B444: record what this installation runs on, and report what
    # the launcher found in the way of updates last time. Both without a
    # network and without waiting: the stamp is a dictionary lookup, and
    # the update check itself runs in the background from the bat.
    from modules import versions
    versions.stamp(__version__)
    versions.report_pending()
    logger.info(t("log_models_state"), model_register.state_line())
    if switched_off:
        print(t("console_models_off").format(
            count=len(switched_off), names=", ".join(switched_off)))

    # The GUI always starts on an EMPTY project, not on the last one used
    # (B111), so the stored title is cleared.
    if app_config.song.title:
        app_config = replace(app_config,
                             song=replace(app_config.song, title=""))
        config_module.save_config(app_config, paths.config_file)

    # Empty the whole cache root hard and recursively (all projects), so
    # that no empty folders or old wavs of other projects stay behind
    # (B110).
    if app_config.cache.clear:
        clean_cache(paths.cache_root)
    clean_logs(paths.logs_dir)

    if not ffmpeg.is_available():
        logger.warning(t("log_ffmpeg_not_on_path"))
        print(t("console_ffmpeg_missing"))

    # Apply an own output folder (B214) as soon as the config is loaded;
    # input and cache stay relative to the project root.
    paths = ProjectPaths(root=root,
                         output_base=filesystem.output_base_from(
                             app_config.advanced.output_dir))
    ensure_directories(paths)
    # Clear up orphan projects: an input folder without an output folder
    # belongs to a project that was removed (B112). B469: this has to
    # happen AFTER the configured output folder is known, otherwise it
    # measures against an empty default folder and deletes everything.
    filesystem.prune_orphan_projects(root, paths.output_root)
    # B445: this is the state BEFORE a song has been chosen, so nothing
    # should reach the disk yet. It did: output\settings\project.json is
    # a real file on the user's machine, holding the video titles of a
    # song that did not exist then, and producing a warning about its
    # structure at every single start.
    filesystem.warn_about_stray_store(paths)
    store = ProjectStore(paths.project_file, writable=False)
    context = AppContext(config=app_config, paths=paths, store=store)
    # v1.0.20: helpers may take a separation when they are sooner done.
    from modules import shared_work, work_queue
    shared_work.use_queue(work_queue.queue_for(context).root)
    shared_work.tidy_at_start()
    # And the helpers of v1.0.18 in the old work folder hear of it.
    work_queue.announce(work_queue.queue_for(context), __version__)

    try:
        from modules.gui import run_gui
    except ImportError:
        logger.exception(t("log_pyside_missing"))
        print(t("console_pyside_missing"))
        return 1
    exit_code = run_gui(context)

    # On closing, clear the cache of the project that is active NOW (the
    # GUI may have switched to another song during the session).
    try:
        final_config = config_module.load_config(paths.config_file)
    except config_module.ConfigError:
        final_config = app_config
    final_paths = ProjectPaths(root=root, song=final_config.song.title)
    if final_config.cache.clear:
        clean_cache(final_paths.cache_root)  # the whole cache root (B110)
    clean_logs(final_paths.logs_dir)
    logger.info(t("log_app_closed"))
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n" + t("console_interrupted"))
        sys.exit(130)
    except Exception:  # noqa: BLE001 - the last net, with logging
        logging.getLogger(__name__).exception(t("log_unexpected_error"))
        print(t("console_unexpected_error"))
        sys.exit(1)
