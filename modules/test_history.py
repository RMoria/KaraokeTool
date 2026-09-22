"""Measurement history per action, project and version (B362, TEMPORARY).

Without bookkeeping every test run measures everything again, including
the eleven projects that have not changed at all since the previous
version. With it, three things become possible:

* **Skipping.** Has this action already run for this version AND this
  unchanged project, then the kept result is used again. That is what
  makes a full round cheap enough to simply run after every release.
* **Comparing.** A new version puts its numbers next to those of the
  previous versions, so a regression is visible in the report itself
  instead of only in someone's memory.
* **Tracing.** For every number it is recorded which version produced it
  and on which state of the project.

The key is deliberately more than the version. A version says something
about the CODE, not about the DATA: the user adjusts a lyrics file or
corrects the timing without a single line of code changing. Every entry
therefore also carries a fingerprint of the project files the
measurement depends on. Changes the data, then the fingerprint changes
and the measurement is done again - exactly what the user asked for when
he said that with new data or model additions it does have to be redone.

The switched-off models are part of that fingerprint too (B361): the
same code with B213 off is a different measurement.

TEMPORARY: this belongs to the test panel. See
``docs/development_log.md``, section "Decide before release".
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

#: How many versions are kept per (action, project). The user asked for
#: three; a fourth would only make the report wider without adding an
#: insight - with three you see a trend and still the direct predecessor.
KEEP_VERSIONS = 3

#: Where the history lives. Next to the reports, not in the projects: it
#: is bookkeeping about measurements, not about a song.
HISTORY_FILE = Path(__file__).resolve().parents[1] / "docs" / "testhistorie.json"

#: The project files a measurement leans on. Missing files simply do not
#: count; that keeps the fingerprint stable for projects without timing.
_FINGERPRINT_FILES = (
    ("timing", "settings/timing.json"),
    ("timing_auto", "settings/timing_auto.json"),
    ("project", "settings/project.json"),
)


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def project_fingerprint(context, song: str) -> str:
    """A short fingerprint of everything a measurement depends on.

    Deliberately based on size + modification time and not on the full
    content: a fingerprint over thirteen projects is calculated at every
    test run, and reading in every ``timing.json`` for that is a waste.
    A changed file always changes at least one of the two.
    """
    from . import filesystem, model_register

    paths = filesystem.ProjectPaths(root=context.paths.root, song=song,
                                    output_base=context.paths.output_base)
    parts: list[str] = []
    for name, relative in _FINGERPRINT_FILES:
        path = paths.output_dir / relative
        try:
            stat = path.stat()
            parts.append(f"{name}:{stat.st_size}:{int(stat.st_mtime)}")
        except OSError:
            parts.append(f"{name}:-")
    cache = paths.cache_dir / "transcription_original.json"
    try:
        stat = cache.stat()
        parts.append(f"cache:{stat.st_size}:{int(stat.st_mtime)}")
    except OSError:
        parts.append("cache:-")
    # B361: the same code with a different model off is a different
    # measurement.
    parts.append("uit:" + ",".join(model_register.disabled_now()))
    return _digest("|".join(parts))


#: B394: every write is a read-modify-write of the WHOLE file, and
#: ``across_projects`` runs two worker threads. Without this lock the
#: second writer loads its snapshot before the first has saved, and then
#: saves it back - throwing the first one's entry away.
#:
#: That is not theory. After a full run of 1.5.1 to 1.5.10 the history
#: held nine keys: the per-action totals (written from the main thread,
#: so never in the race) plus four of the fourteen projects measured then.
#: Everything from 1.5.5, 1.5.6 and 1.5.7 was gone. Which quietly
#: undermines the whole point of B362: comparing against previous
#: versions only works if the previous versions are still there.
#:
#: A thread lock is enough as long as one process writes. The moment the
#: measurement is spread over PROCESSES this has to become a file lock -
#: worth remembering, because that idea is on the list.
_WRITE_LOCK = threading.Lock()


def _load() -> dict:
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")


def _key(code: str, song: str) -> str:
    return f"{code}|{song}"


def lookup(code: str, song: str, version: str, fingerprint: str):
    """The kept result, or ``None`` if it has to be measured again."""
    entries = _load().get(_key(code, song), [])
    for entry in entries:
        if entry.get("version") == version and \
                entry.get("fingerprint") == fingerprint:
            return entry.get("result")
    return None


#: Under this "project name" stands the duration of the WHOLE action,
#: as against the duration per project at the ordinary entries (B370).
TOTAL = "*"


def remember(code: str, song: str, version: str, fingerprint: str,
             result, seconds: float | None = None) -> None:
    """Keep a result, and throw away everything but the last versions.

    B394: under the lock, because two work slots write here at the same
    time and the whole file is rewritten every time.
    """
    with _WRITE_LOCK:
        data = _load()
        entries = [e for e in data.get(_key(code, song), [])
                   if e.get("version") != version]
        ingang = {"version": version, "fingerprint": fingerprint,
                  "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                  "result": result}
        if seconds is not None:
            ingang["seconds"] = round(float(seconds), 1)
        entries.append(ingang)
        # Newest at the back; older than KEEP_VERSIONS drops out.
        data[_key(code, song)] = entries[-KEEP_VERSIONS:]
        _save(data)


def history(code: str, song: str) -> list[dict]:
    """All kept versions for this action and project, oldest first."""
    return list(_load().get(_key(code, song), []))


def earlier_versions(code: str, song: str, version: str) -> list[dict]:
    """The kept entries of OTHER versions, newest last."""
    return [e for e in history(code, song) if e.get("version") != version]


def comparison(code: str, songs, version: str, field: str) -> list[str]:
    """Table rows: this version next to the previous ones (B362).

    ``field`` is the key in the kept result that carries the number.
    Projects without history give a dash instead of a hole, so that the
    table stays readable.
    """
    from .translations import t

    versions: list[str] = []
    for song in songs:
        for entry in history(code, song):
            if entry["version"] not in versions:
                versions.append(entry["version"])
    versions = [v for v in versions if v != version][-KEEP_VERSIONS:]
    if not versions:
        return []
    rows = ["| project | " + " | ".join(versions) + f" | {version} |",
            "| --- |" + " ---: |" * (len(versions) + 1)]
    for song in songs:
        entries = {e["version"]: e for e in history(code, song)}
        cells = []
        for name in versions + [version]:
            entry = entries.get(name)
            value = (entry or {}).get("result", {})
            value = value.get(field) if isinstance(value, dict) else None
            cells.append("-" if value is None else f"{float(value):.2f}")
        rows.append(f"| {song} | " + " | ".join(cells) + " |")
    rows.append("")
    rows.append(t("test_history_note").format(count=len(versions)))
    return rows


def forget_all() -> None:
    """Throw the whole history away (for tests, and for a fresh start)."""
    try:
        HISTORY_FILE.unlink(missing_ok=True)
    except OSError:
        from .translations import t
        logger.warning(t("log_history_delete_failed"), HISTORY_FILE)


def remember_duration(code: str, version: str, seconds: float) -> None:
    """Keep how long a whole action took (B370).

    Deliberately no warning in the program itself - the user asked for
    the number to be kept, not for the app to nag about it. The question
    "does this belong in 1.5.11?" is asked when the data is looked at.
    The log files are pruned to five, so without this the duration of a
    run is gone within a week.
    """
    remember(code, TOTAL, version, "-", {"seconds": round(float(seconds), 1)},
             seconds=seconds)


def durations(code: str) -> list[tuple[str, float]]:
    """(version, seconds) of the kept runs, oldest first."""
    uit = []
    for entry in history(code, TOTAL):
        seconden = entry.get("seconds")
        if seconden is not None:
            uit.append((entry.get("version", "?"), float(seconden)))
    return uit


def version_number(version: str) -> int:
    """The middle number of "0.116.0".

    A repair release such as 0.110.1 therefore does not count as a
    version of its own (B371).
    """
    parts = str(version).split(".")
    try:
        return int(parts[1]) if len(parts) > 1 else int(parts[0])
    except ValueError:
        return 0


def versions_ago(code: str, version: str) -> int | None:
    """How many versions ago this action last ran.

    ``None`` if it has never run yet - then there is nothing to skip
    and it simply has to.
    """
    gedraaid = [version_number(v) for v, _s in durations(code)]
    gedraaid += [version_number(e.get("version", ""))
                 for e in history(code, TOTAL)]
    gedraaid = [n for n in gedraaid if n]
    if not gedraaid:
        return None
    return max(0, version_number(version) - max(gedraaid))
