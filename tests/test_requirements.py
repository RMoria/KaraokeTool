"""Everything requirements.txt calls for is really installed (B552).

This is the test that would have prevented the whole of B545. Three
tests were green on the machine they were written on and red on the
machine they had to be green on, and the reason underneath was not
those three tests: the two machines did not have the same packages,
while ``requirements.txt`` says plainly which ones are needed. A suite
that runs with half of them missing is not testing the program, it is
testing a program that happens to be there.

The optional models (Demucs, WhisperX) are deliberately NOT in here.
``requirements.txt`` puts them under a heading of their own with a
`pip install` line beside them, the code asks
``models.is_available(...)`` before it uses them, and it falls back
when they are absent. That is a different promise from a requirement
and this test keeps the difference visible.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"

#: The import name, where it is not the name on the line. The rest is
#: the name with its dashes turned into underscores.
IMPORT_NAMES = {
    "faster-whisper": "faster_whisper",
    "pillow": "PIL",
}


def _required() -> list[tuple[str, str]]:
    """``(name on the line, name to import)`` for every requirement."""
    wanted = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[;]", line, maxsplit=1)[0].strip()
        if not name:
            continue
        wanted.append((name, IMPORT_NAMES.get(name, name.replace("-", "_"))))
    return wanted


def test_the_file_lists_what_this_project_needs() -> None:
    """A guard on the guard: an empty list would pass everything."""
    names = [name for name, _ in _required()]
    assert len(names) >= 8, names
    for expected in ("numpy", "faster-whisper", "librosa", "PySide6"):
        assert expected in names, names


def test_every_requirement_is_installed() -> None:
    """The machine the suite runs on meets requirements.txt.

    Red here means the environment is wrong, not the code. Fix it with
    the line the failure prints; do not put the package on a list of
    exceptions, because then the next difference between two machines
    is invisible again.
    """
    missing = [name for name, module in _required()
               if importlib.util.find_spec(module) is None]
    assert not missing, (
        "requirements.txt asks for packages that are not installed: "
        + ", ".join(missing) + " - install them with:  pip install "
        + " ".join(missing))


def test_the_optional_models_are_not_in_the_file() -> None:
    """Demucs and WhisperX are a suggestion, not a requirement.

    They sit in requirements.txt as a comment with a `pip install` line
    beside them, and the code checks for them before it uses them. If
    one of them ever moves into the list proper, this test says so -
    because from that moment on a machine without it is broken rather
    than merely limited.
    """
    names = [name.lower() for name, _ in _required()]
    for optional in ("demucs", "whisperx"):
        assert optional not in names, names
    text = REQUIREMENTS.read_text(encoding="utf-8")
    assert "pip install demucs" in text
    assert "pip install whisperx" in text
