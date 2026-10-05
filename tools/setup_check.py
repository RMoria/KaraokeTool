"""Is the installation up to date? (v1.0.19, run by KaraokeToolGUI.bat).

The launcher starts the program and installs or brings up to date
what it needs, in one file: install.bat is gone. To start quickly it
does the setup only when something changed: the packages the program
asks for (``requirements.txt``), the steps of the setup itself
(:data:`SETUP_LEVEL`, raised when the launcher's setup part changes),
the owner's choice about Roformer, whether the computer has an NVIDIA
card, or the Python the environment was made with (v1.0.20: 3.13).
What was installed is noted in the virtual environment
(``karaoketool_setup.txt``).

    python tools/setup_check.py <venv> <roformer J|N|?> [--cuda]      exit 1: set up
    python tools/setup_check.py <venv> <roformer> [--cuda] --write    note it done
    python tools/setup_check.py --same-python <venv>     exit 1: made with another Python
    python tools/setup_check.py --python-of <venv>       print the venv's Python (3.13)
    python tools/setup_check.py --set-aside <path> <folder> [<folder> ...]
                                    move <path> into the first folder that works
    python tools/setup_check.py --vc-runtime       exit 1: Microsoft's Visual C++
                                    runtime is missing or too old for PyTorch

Run with the Python the launcher chose, not with the one in the
environment: the environment may be the one that has to go. Standard
library only.
"""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: Raised when the setup part of KaraokeToolGUI.bat does something new.
SETUP_LEVEL = 2
MARKER = "karaoketool_setup.txt"


def venv_python(venv: Path) -> str:
    """``3.13`` for an environment made with Python 3.13.x; empty when
    it cannot be told."""
    try:
        text = (venv / "pyvenv.cfg").read_text(encoding="utf-8",
                                               errors="replace")
    except OSError:
        return ""
    for row in text.splitlines():
        key, _sep, value = row.partition("=")
        if key.strip().lower() in ("version", "version_info"):
            parts = value.strip().split(".")
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[1]}"
    return ""


def running_python() -> str:
    return "%d.%d" % sys.version_info[:2]


def stamp(roformer: str, root: Path = ROOT, cuda: bool = False,
          python: str = "") -> str:
    digest = hashlib.sha1(f"level {SETUP_LEVEL} roformer {roformer} "
                          f"cuda {int(bool(cuda))} python {python}".encode())
    try:
        digest.update((root / "requirements.txt").read_bytes())
    except OSError:
        digest.update(b"-")
    return digest.hexdigest()


def needed(venv: Path, roformer: str, root: Path = ROOT,
           cuda: bool = False) -> bool:
    try:
        done = (venv / MARKER).read_text(encoding="utf-8").strip()
    except OSError:
        return True
    return done != stamp(roformer, root, cuda, venv_python(venv))


def set_aside(path: Path, folders) -> Path | None:
    """Move ``path`` (an environment, a Python) into the first of
    ``folders`` where that works, under a name that says what it was and
    when. Returns where it went, or ``None``."""
    python = venv_python(path)
    label = f"{path.name}_py{python.replace('.', '')}" if python \
        else path.name
    moment = time.strftime("%Y%m%d_%H%M%S")
    for folder in folders:
        folder = Path(folder)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{label}_{moment}"
            path.rename(target)
            return target
        except (OSError, ValueError):
            continue
    return None


#: The files of Microsoft's Visual C++ 2015-2022 runtime (x64) that
#: PyTorch 2.x loads (v1.0.23, B649). The last two came with the newer
#: releases of that runtime: Probook had an older one, and torch stopped
#: on ``c10.dll`` until winget brought it to 14.51.
VC_RUNTIME_FILES = ("vcruntime140.dll", "vcruntime140_1.dll",
                    "msvcp140.dll", "msvcp140_1.dll",
                    "vcruntime140_threads.dll", "msvcp140_atomic_wait.dll")


def vc_runtime_missing(system: Path | None = None) -> list[str]:
    """The runtime files that are not in System32 (none off Windows)."""
    import os

    if system is None:
        if os.name != "nt":
            return []
        system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / \
            "System32"
    return [name for name in VC_RUNTIME_FILES
            if not (Path(system) / name).exists()]


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: setup_check.py <venv> <roformer J|N|?> [--cuda] "
              "[--write]\n       setup_check.py --same-python|--python-of "
              "<venv>\n       setup_check.py --set-aside <path> <folder>...")
        print(__doc__)
        return 0 if argv[:1] in (["-h"], ["--help"]) else 2
    if argv[0] == "--same-python":
        made = venv_python(Path(argv[1]))
        return 0 if made == running_python() else 1
    if argv[0] == "--python-of":
        print(venv_python(Path(argv[1])))
        return 0
    if argv[0] == "--vc-runtime":
        missing = vc_runtime_missing()
        for name in missing:
            print(f"missing: {name}")
        return 1 if missing else 0
    if argv[0] == "--set-aside":
        target = set_aside(Path(argv[1]), argv[2:])
        if target is None:
            return 1
        print(target)
        return 0
    if len(argv) < 2:
        return 2
    venv, roformer = Path(argv[0]), argv[1].strip().upper()[:1] or "?"
    cuda = "--cuda" in argv[2:]
    if "--write" in argv[2:]:
        (venv / MARKER).write_text(
            stamp(roformer, cuda=cuda, python=venv_python(venv)),
            encoding="utf-8")
        return 0
    return 1 if needed(venv, roformer, cuda=cuda) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
