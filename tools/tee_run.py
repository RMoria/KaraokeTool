"""Run one command of the setup (KaraokeToolGUI.bat, install_hulp.bat), on screen and in the install log.

The setup is a batch file, and its output lived only in the window: a
message that scrolled past was gone, and the owner could not hand it
over (v1.0.15). This runs a command, shows what it says as it says it,
and appends the same text to the log - with the command above it and
its exit code below it - then exits with the command's own code, so
``|| echo ...`` and ``if errorlevel`` in the batch file keep working.

Standard library only: it runs on the Python the setup found, before
any environment exists.

Usage::

    python tools/tee_run.py <log file> -- <command> [arguments...]
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys


def _clean(text: str) -> str:
    """What the log keeps of a line: what is left after the last carriage
    return, so a progress bar leaves only its final state."""
    return text.rsplit("\r", 1)[-1]


def run(log_path: str, command: list[str]) -> int:
    """Run ``command``; screen and log get its output. Returns its code."""
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    # Unbuffered, so the screen follows as it happens; UTF-8, so the log
    # of a Python program reads the same whatever the console's code page.
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    with open(log_path, "a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n[{stamp}] > {subprocess.list2cmdline(command)}\n")
        log.flush()
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, env=env)
        except OSError as exc:
            message = f"could not start: {exc}"
            print(message, flush=True)
            log.write(message + "\n[exit 127]\n")
            return 127
        pending = ""
        out = sys.stdout.buffer
        while True:
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                break
            out.write(chunk)
            out.flush()
            text = pending + chunk.decode("utf-8", errors="replace")
            *lines, pending = text.split("\n")
            for line in lines:
                log.write(_clean(line.rstrip("\r")) + "\n")
            log.flush()
        if pending:
            log.write(_clean(pending) + "\n")
        code = process.wait()
        log.write(f"[exit {code}]\n")
    return code


def main(argv: list[str]) -> int:
    usage = "usage: tee_run.py <log file> -- <command> [arguments...]"
    if argv[:1] in (["-h"], ["--help"]):
        print(usage + "\n\n" + __doc__)
        return 0
    if len(argv) < 3 or argv[1] != "--":
        print(usage)
        return 2
    return run(argv[0], argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
