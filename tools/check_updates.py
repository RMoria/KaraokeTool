"""Ask pip what could be newer, and write the answer down (B444).

Deliberately NOT part of the program. Asking pip means the network and a
subprocess, and the user should never be waiting for either at start-up:
the launcher fires this off in the background, it writes
``docs/updates.json``, and the program reads that file the NEXT time it
starts. So the news is always one start late, and that is the right
trade: a start that hangs on a slow mirror is worse than knowing about
an update tomorrow.

It throttles itself rather than making the launcher do it: a batch file
that has to work out how old a file is, is a batch file nobody dares
touch again.

Usage::

    python tools/check_updates.py            # at most once a day
    python tools/check_updates.py --force    # now, whatever the age
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import proc, versions  # noqa: E402

#: Do not ask again within this many hours.
EVERY_HOURS = 24

#: pip has to be allowed to be slow, but not endlessly.
TIMEOUT_S = 180


def checked_recently(path: Path, hours: int = EVERY_HOURS,
                     now: datetime | None = None) -> bool:
    """Is the existing report younger than ``hours``?"""
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        written = datetime.fromisoformat(str(data.get("when", "")))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if written.tzinfo is None:
        written = written.replace(tzinfo=timezone.utc)
    moment = now or datetime.now(timezone.utc)
    return (moment - written).total_seconds() < hours * 3600


def ask_pip(python_exe: str = "") -> str:
    """The raw JSON of ``pip list --outdated``; empty on any failure.

    Every failure is the same failure here: there is no news. A machine
    without a network, a pip that has been renamed, a proxy that says no
    - none of that is worth an error message, because nothing depends on
    the answer.
    """
    try:
        # Through ``proc.run``: the one door for every external program
        # in this project, so a run of pip is windowless and can really
        # be stopped instead of holding the start hostage.
        done = proc.run(
            [python_exe or sys.executable, "-m", "pip", "list",
             "--outdated", "--format=json", "--disable-pip-version-check"],
            timeout=TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="even if it was already checked today")
    parser.add_argument("--python", default="",
                        help="the python of the venv (default: this one)")
    args = parser.parse_args(argv)

    target = versions.UPDATE_FILE
    if not args.force and checked_recently(target):
        return 0
    found = versions.outdated_from_pip(ask_pip(args.python))
    versions.write_update_report(found, target)
    for item in found:
        print(f"  {item['name']}: {item['current']} -> {item['latest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
