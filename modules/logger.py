"""Logging configuration for KaraokeTool.

Writes everything (DEBUG and higher) to a daily log file in the folder
``logs`` and shows INFO and higher on the console.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

_FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_CONSOLE_FORMAT = "%(levelname)-8s %(message)s"
#: Format for the "Activity" panel in the GUI (compact, like the cmd).
GUI_FORMAT = "%(levelname)-8s %(name)s | %(message)s"


def setup_logging(log_dir: Path, console_level: int = logging.INFO) -> logging.Logger:
    """Configure logging to the console and a daily log file.

    Args:
        log_dir: Folder in which log files are written,
            for example ``logs/2026-07-13.log``.
        console_level: Minimum log level for console output.

    Returns:
        The configured root logger.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{date.today():%Y-%m-%d}.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    root.addHandler(file_handler)

    # Without a console (started via pythonw.exe) there is no stderr; do
    # not add a console handler then (the GUI shows the activity and the
    # log file keeps being filled).
    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
        root.addHandler(console_handler)

    from .translations import t

    logging.getLogger(__name__).debug(t("log_logging_started"), log_file)
    return root
