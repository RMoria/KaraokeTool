"""Utilities to start external processes without a window, and to kill
them when the user aborts.

On Windows every console program started via :mod:`subprocess` opens
its own cmd window when the GUI runs windowless (``pythonw.exe``).
Those windows flash distractingly on screen during, among others,
"Detect words" (ffmpeg/ffprobe) and the vocal separation (Demucs).

**Standing policy:** every new ``subprocess`` call in this project runs
through :func:`run` (or at least passes the kwargs of
:func:`no_window_kwargs`), so that a window never flashes up. On other
operating systems nothing changes. A test guards this.

A second reason for that one door (B356): a subprocess does not listen
to the Stop button. ``subprocess.run`` waits until the program is done,
so an abort during a Demucs separation still took the full three
minutes. Everything that runs through :func:`run` is registered, and
:func:`terminate_all` really does kill it.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

#: Everything that is running right now, so that it can be killed on an
#: abort (B356). A set and not one process: two projects can be busy at
#: the same time (the test panel runs two at a time).
_RUNNING: set = set()
_RUNNING_LOCK = threading.Lock()

#: ``CREATE_NO_WINDOW`` (0x08000000). On non-Windows the flag is absent.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_windows() -> bool:
    """Is this running on Windows?"""
    return sys.platform.startswith("win")


def no_window_kwargs() -> dict[str, Any]:
    """Kwargs for :mod:`subprocess` that hide the window on Windows.

    Combines ``creationflags=CREATE_NO_WINDOW`` with a hidden
    ``STARTUPINFO`` (doubled up; some programs ignore the one or the
    other). On other platforms an empty dict, so that the call remains
    unchanged there.
    """
    if not is_windows():
        return {}
    startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
    startupinfo.wShowWindow = subprocess.SW_HIDE  # type: ignore[attr-defined]
    return {"creationflags": _CREATE_NO_WINDOW, "startupinfo": startupinfo}


def windowless_python() -> str:
    """Path to a windowless Python interpreter (for subprocesses).

    On Windows a subprocess that itself creates processes again (such
    as Demucs via ``torch``/multiprocessing) starts new windows when
    the interpreter is ``python.exe``. By using ``pythonw.exe`` those
    child processes inherit a windowless interpreter. If
    ``pythonw.exe`` does not exist, this falls back to
    ``sys.executable``.
    """
    executable = sys.executable
    if is_windows() and executable:
        candidate = Path(executable)
        if candidate.name.lower() == "python.exe":
            pythonw = candidate.with_name("pythonw.exe")
            if pythonw.exists():
                return str(pythonw)
    return executable


def run(command: Sequence[str], *, timeout: float | None = None,
        check: bool = True, capture: bool = True,
        text: bool = True) -> subprocess.CompletedProcess:
    """Run an external program, windowless and killable (B356).

    The one door for every external program in this project. Registers
    the process while it runs, so that :func:`terminate_all` can really
    stop it - ``subprocess.run`` on its own waits until the program is
    finished, however hard the user presses Stop.
    """
    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=text, **no_window_kwargs())
    with _RUNNING_LOCK:
        _RUNNING.add(process)
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        out, err = process.communicate()
        raise
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(process)
    result = subprocess.CompletedProcess(list(command), process.returncode,
                                         out, err)
    if check and process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, list(command),
                                            out, err)
    return result


def register(process) -> None:
    """Note a process that was started elsewhere (B356).

    For the one case that cannot go through :func:`run`: the video
    render pipes frames into ffmpeg's stdin and therefore keeps the
    process itself. Registering it means Stop can still kill it.
    """
    with _RUNNING_LOCK:
        _RUNNING.add(process)


def unregister(process) -> None:
    """Counterpart of :func:`register`."""
    with _RUNNING_LOCK:
        _RUNNING.discard(process)


def terminate_all() -> int:
    """Kill everything that is running right now (B356).

    Used by the Stop button when a polite abort takes too long: a
    running Demucs or ffmpeg does not look at the cancel event and
    would otherwise simply finish. Returns how many processes were
    killed.
    """
    with _RUNNING_LOCK:
        processen = list(_RUNNING)
    for process in processen:
        try:
            process.kill()
        except OSError:          # al klaar tussen kijken en doden
            continue
    if processen:
        logger.info(t_or_plain("log_processes_killed"), len(processen))
    return len(processen)


def t_or_plain(key: str) -> str:
    """Translation if available; this module must stay importable on its
    own (the translation table imports nothing from here, but a circular
    import in the future would be nasty)."""
    try:
        from .translations import t
        return t(key)
    except Exception:  # noqa: BLE001 - logging mag nooit de oorzaak zijn
        return "%d proces(sen) afgebroken"
