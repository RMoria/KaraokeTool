"""Keep track of which versions this installation runs on (B443/B444).

The user's reasoning, and it is the right one: things get developed, and
when something suddenly behaves oddly you want to be able to point at an
update - or rule one out. That only works if you wrote down what was
installed BEFORE the odd thing happened, so this runs at every start and
costs nothing: reading version numbers is a dictionary lookup, no network
and no imports of the heavy packages themselves.

Two separate things live here, deliberately not mixed up:

* the STAMP - what is installed right now, appended to a history file
  the moment it differs from the previous entry. No network, always on.
* the UPDATE CHECK - what COULD be newer. That one does need the network
  and pip, so it does not run in the program at all: the launcher starts
  it in the background and it writes its answer to a file. The program
  only reads that file, and therefore never waits for it.

The history is the part that matters. A list of "on 3 August torch went
from 2.3.0 to 2.4.0" turns "it suddenly sounds different" from a hunch
into something you can look up.
"""
from __future__ import annotations

import json
import logging
import platform
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

#: The packages worth following. Everything the audio path leans on plus
#: the toolkit that draws the window. A package that is not installed is
#: recorded as absent rather than skipped: "demucs disappeared" is
#: exactly the kind of thing this file has to be able to show.
PACKAGES = (
    "faster-whisper", "ctranslate2", "torch", "torchaudio", "demucs",
    "whisperx", "librosa", "numpy", "scipy", "soundfile", "rapidfuzz",
    "PySide6", "pillow", "langdetect", "av",
)

#: Where the history goes. A constant so a test can move it aside.
VERSION_LOG = Path(__file__).resolve().parents[1] / "docs" / "pakketversies.json"

#: Where the launcher leaves the outcome of its update check.
UPDATE_FILE = Path(__file__).resolve().parents[1] / "docs" / "updates.json"

#: An update report older than this says nothing about today.
UPDATE_MAX_AGE_DAYS = 14


def _version_of(name: str) -> str:
    """The installed version, or an empty string when it is not there."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return str(version(name))
    except PackageNotFoundError:
        return ""
    except Exception:                # noqa: BLE001 - a stamp may never break the start
        from .translations import t

        logger.exception(t("log_version_lookup_failed"))
        return ""


def collected(app_version: str) -> dict:
    """What this installation runs on right now."""
    return {
        "app": str(app_version),
        "python": platform.python_version(),
        "packages": {name: _version_of(name) for name in PACKAGES},
    }


def differences(previous: dict | None, current: dict) -> list[str]:
    """What changed between two stamps, in readable lines.

    An absent package is written as "-", so appearing and disappearing
    read the same way as an upgrade does.
    """
    if not previous:
        return []
    out = []
    for key in ("app", "python"):
        was, now = str(previous.get(key, "")), str(current.get(key, ""))
        if was and was != now:
            out.append(f"{key} {was} -> {now}")
    old_packages = dict(previous.get("packages") or {})
    for name, now in (current.get("packages") or {}).items():
        was = str(old_packages.get(name, ""))
        if name not in old_packages or was == now:
            continue
        out.append(f"{name} {was or '-'} -> {now or '-'}")
    return out


def history(path: Path | None = None) -> list[dict]:
    """Everything written down so far, oldest first."""
    path = path or VERSION_LOG
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        from .translations import t

        logger.exception(t("log_version_history_failed"))
        return []
    return [item for item in data if isinstance(item, dict)] \
        if isinstance(data, list) else []


def remember(current: dict, path: Path | None = None,
             when: str = "") -> list[str]:
    """Append this stamp if it differs from the last, and say what moved.

    Only on a change, on purpose: an entry per start would be a file of
    thousands of identical lines within a month, and then nobody looks
    in it any more.
    """
    path = path or VERSION_LOG
    entries = history(path)
    previous = entries[-1] if entries else None
    if previous and {k: previous.get(k) for k in ("app", "python", "packages")} \
            == {k: current.get(k) for k in ("app", "python", "packages")}:
        return []
    changes = differences(previous, current)
    entry = dict(current)
    entry["when"] = when or datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    if changes:
        entry["changed"] = changes
    entries.append(entry)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, indent=2, ensure_ascii=False)
                        + "\n", encoding="utf-8")
    except OSError:
        from .translations import t

        logger.exception(t("log_version_history_failed"))
    return changes


def stamp(app_version: str, path: Path | None = None) -> list[str]:
    """Record the versions and log what changed since the last start."""
    from .translations import t

    changes = remember(collected(app_version), path)
    if changes:
        logger.info(t("log_versions_changed"), "; ".join(changes))
    return changes


# -- the update check, which the launcher runs and the program reads -----

def outdated_from_pip(payload: str) -> list[dict]:
    """The packages we follow, out of ``pip list --outdated --format=json``.

    Kept apart from the running of pip so this half can be tested
    without a network, and so the parsing is not repeated in the tool.
    """
    try:
        data = json.loads(payload or "[]")
    except json.JSONDecodeError:
        return []
    wanted = {name.lower() for name in PACKAGES}
    return sorted(
        ({"name": str(item.get("name", "")),
          "current": str(item.get("version", "")),
          "latest": str(item.get("latest_version", ""))}
         for item in data if isinstance(item, dict)
         and str(item.get("name", "")).lower() in wanted),
        key=lambda item: item["name"].lower())


def write_update_report(found: list[dict], path: Path | None = None,
                        when: str = "") -> Path:
    """Leave the outcome where the program can read it."""
    path = path or UPDATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"when": when or datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
         "outdated": list(found)}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return path


def pending_updates(path: Path | None = None, now: datetime | None = None,
                    max_age_days: int = UPDATE_MAX_AGE_DAYS) -> list[dict]:
    """Updates the launcher found, if the report is still recent.

    An old report is silently treated as no report. Saying "there is an
    update" on the strength of a file from six weeks ago is worse than
    saying nothing: it is advice that has already been followed or has
    long since been overtaken.
    """
    path = path or UPDATE_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    try:
        written = datetime.fromisoformat(str(data.get("when", "")))
    except ValueError:
        return []
    moment = now or datetime.now(timezone.utc)
    if written.tzinfo is None:
        written = written.replace(tzinfo=timezone.utc)
    if (moment - written).days > max_age_days:
        return []
    return [item for item in (data.get("outdated") or ())
            if isinstance(item, dict)]


def report_pending(path: Path | None = None) -> list[dict]:
    """Log the updates the launcher found, so they land in the log window."""
    from .translations import t

    found = pending_updates(path)
    if found:
        logger.info(t("log_updates_available"), ", ".join(
            f"{item['name']} {item['current']} -> {item['latest']}"
            for item in found))
    return found
