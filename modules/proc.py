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
import os
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
#: How often :func:`terminate_all` was called: work that does not run as
#: a process of its own (a round a helper does, v1.0.20) looks at this to
#: see that Stop was pressed.
_STOPS = 0

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


def hidden_console_python() -> str:
    """v1.0.28 (B658): ``python.exe`` also when this process runs under
    ``pythonw.exe`` - for a child that starts programs of its own.

    A child started with ``CREATE_NO_WINDOW`` gets a console without a
    window, and every console program IT starts (ffmpeg under Demucs or
    the Roformer library, torch's worker processes) shares that hidden
    console. Under ``pythonw.exe`` the child has no console at all, and
    each of those grandchildren opens a window of its own: the flash the
    owner saw whenever a helper began a round.
    """
    executable = sys.executable
    if is_windows() and executable:
        candidate = Path(executable)
        if candidate.name.lower() == "pythonw.exe":
            console = candidate.with_name("python.exe")
            if console.exists():
                return str(console)
    return executable


def child_env(env: dict | None = None) -> dict:
    """v1.0.28 (B657): what a child gets on top of its environment: its
    output as UTF-8 (a cp1252 decode of tqdm's bars crashed a helper)
    and no progress bars (nobody sees them; they only fill the pipe)."""
    out = dict(os.environ if env is None else env)
    out.setdefault("PYTHONIOENCODING", "utf-8")
    out.setdefault("TQDM_DISABLE", "1")
    return out


def run(command: Sequence[str], *, timeout: float | None = None,
        check: bool = True, capture: bool = True,
        text: bool = True, env: dict | None = None,
        cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run an external program, windowless and killable (B356).

    The one door for every external program in this project. Registers
    the process while it runs, so that :func:`terminate_all` can really
    stop it - ``subprocess.run`` on its own waits until the program is
    finished, however hard the user presses Stop.
    """
    # v1.0.28 (B657): read as UTF-8, and a byte that is not is replaced
    # - never a crash on what a program prints.
    extra = {"encoding": "utf-8", "errors": "replace"} if text else {}
    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=text, env=child_env(env), cwd=cwd, **extra,
        **no_window_kwargs())
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
    global _STOPS
    with _RUNNING_LOCK:
        processes = list(_RUNNING)
        _STOPS += 1
    for process in processes:
        try:
            process.kill()
        except OSError:          # already gone between looking and killing
            continue
    if processes:
        logger.info(t_or_plain("log_processes_killed"), len(processes))
    return len(processes)


def stops() -> int:
    return _STOPS


def stopped_since(count: int):
    """A ``cancelled()`` for work that started when :func:`stops` was
    ``count``."""
    return lambda: _STOPS != count


def t_or_plain(key: str) -> str:
    """Translation if available; this module must stay importable on its
    own (the translation table imports nothing from here, but a circular
    import in the future would be nasty)."""
    try:
        from .translations import t
        return t(key)
    except Exception:  # noqa: BLE001 - logging may never be the cause
        return "%d process(es) stopped"
