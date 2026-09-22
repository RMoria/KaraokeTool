"""Keeps the last ten versions of the files that hold hand work (B568).

Three files in ``output/<song>/settings/`` cannot be made again by
running the program:

* ``timing.json`` - every syllable the user has dragged into place;
* ``project.json`` - the pins, the coupling and the chosen settings;
* ``timing_auto.json`` - can be made again in principle, but only by
  the same models on the same machine, and it is the reference the
  hand work is measured against.

All three are overwritten in place, and until now that was the end of
the previous version. A pipeline step that ran on the wrong project, a
report that saves something it only meant to read (the ``1.5.2`` case
in ``tests/test_project_safety.py``), a crash halfway through a
write - each of them costs an evening of dragging, and the only copy
was the one being written over. Invalidation deletes the timing
outright, which is cheaper still.

So the version that is ABOUT to disappear is copied first, into
``settings/history/``, named after the moment it was replaced. Ten per
file; the eleventh pushes the oldest out. It is a safety net, not a
version control system: there is no interface to it on purpose,
because the files are plain JSON with their own date and putting one
back is copying it over the original in Explorer.

Two things keep the folder from filling with noise:

* a copy is only made when the file on disk really differs from the
  newest copy already there, so running the same step twice does not
  push nine useful versions out with an identical tenth;
* ``project.json`` is written by every pipeline step, so a copy of it
  is made at most once every :data:`SETTLE_S`. The first write of a
  run therefore keeps the state the user left, and an afternoon of
  pinning is kept at intervals instead of a hundred times or not at
  all.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from .translations import t

logger = logging.getLogger(__name__)

#: Folder next to the files it protects, so a project stays one folder
#: and a copied project brings its history along.
FOLDER_NAME = "history"

#: How many versions of one file are kept. Ten covers a session of
#: work; a hundred would be a version control system nobody asked for.
KEEP = 10

#: Seconds between two copies of a file that is written continuously.
#: Ten of these span an hour and a half of work.
SETTLE_S = 600.0

#: The files this is for. Used by the deletion route, which sees every
#: derived artefact go by and may only keep these.
HAND_WORK = ("timing.json", "timing_auto.json", "project.json")

_STAMP = "%Y%m%d-%H%M%S"

#: ``<stem>_<date>-<time>`` with an optional counter. Anchored on both
#: ends, so ``timing_auto_...`` is NOT a copy of ``timing.json`` - they
#: share one folder, and a loose ``timing_*`` glob let the automatic
#: file push the hand work out of its own ring.
_COPY = re.compile(r"^(?P<stem>.+)_(?P<stamp>\d{8}-\d{6})"
                   r"(?:_(?P<counter>\d+))?$")


def history_dir(path: Path) -> Path:
    """The history folder belonging to *path*."""
    return Path(path).parent / FOLDER_NAME


def _age_key(path: Path) -> tuple[str, int]:
    """``(stamp, counter)``: the order in which the copies were made.

    Read out of the name and not off the name's sort order, because
    those two are not the same thing. ``_10`` sorts before ``_2``, and
    a counter can be re-used once the copy that held the bare name has
    been pushed out of the ring - both of which put the youngest copy
    at the front of the list and make the ring throw away the wrong
    one.
    """
    found = _COPY.match(path.stem)
    if found is None:                    # pragma: no cover - filtered out
        return ("", 0)
    return (found.group("stamp"), int(found.group("counter") or 1))


def copies_of(path: Path) -> list[Path]:
    """Every kept copy of *path*, oldest first."""
    path = Path(path)
    folder = history_dir(path)
    if not folder.is_dir():
        return []
    mine = []
    for item in folder.iterdir():
        found = _COPY.match(item.stem)
        if (found is not None and found.group("stem") == path.stem
                and item.suffix == path.suffix):
            mine.append(item)
    return sorted(mine, key=_age_key)


def _digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _free_name(folder: Path, stem: str, suffix: str, when: datetime,
               earlier: list[Path]) -> Path:
    """The name for a new copy, one after the youngest of this second.

    Two writes within one second happen, and the second one may not
    overwrite the first - nor take a lower counter than a copy that is
    already there, because the counter is what says which of the two is
    younger.
    """
    stamp = when.strftime(_STAMP)
    used = [_age_key(item)[1] for item in earlier
            if _age_key(item)[0] == stamp]
    if not used:
        return folder / f"{stem}_{stamp}{suffix}"
    return folder / f"{stem}_{stamp}_{max(used) + 1}{suffix}"


def _too_soon(earlier: list[Path], now: datetime, settle: float) -> bool:
    """Was the youngest copy made less than *settle* seconds ago?"""
    if not settle or not earlier:
        return False
    try:
        made = datetime.strptime(_age_key(earlier[-1])[0], _STAMP)
    except ValueError:                   # pragma: no cover - filtered out
        return False
    return (now - made).total_seconds() < settle


def keep_a_copy(path: Path, settle: float = 0.0) -> Path | None:
    """Copy the version of *path* that is about to disappear.

    Call this BEFORE writing or deleting, not after: what is worth
    keeping is the version the user still has, not the one that is
    being written.

    Args:
        path: The file that is about to go. A path that does not exist
            yet is the first write and has nothing to keep.
        settle: Seconds that have to have passed since the youngest
            copy, for a file that is written continuously
            (``project.json``). Zero keeps every changed version.

    Returns:
        The copy that was made, or ``None`` if there was nothing to
        keep, if the content is identical to the youngest copy, or if
        that copy is younger than *settle*.

    Never raises: a backup that fails may not stop the write it is
    protecting. It is reported in the log and that is all.
    """
    path = Path(path)
    try:
        if not path.is_file():
            return None
        earlier = copies_of(path)
        now = datetime.now()
        if _too_soon(earlier, now, settle):
            return None
        if earlier and _digest(earlier[-1]) == _digest(path):
            return None

        folder = history_dir(path)
        folder.mkdir(parents=True, exist_ok=True)
        target = _free_name(folder, path.stem, path.suffix, now, earlier)
        shutil.copy2(path, target)

        kept = earlier + [target]
        for old in kept[:max(0, len(kept) - KEEP)]:
            old.unlink()
        logger.debug(t("log_previous_kept"), target.name)
        return target
    except OSError as error:
        logger.warning(t("log_previous_keep_failed"), path, error)
        return None
