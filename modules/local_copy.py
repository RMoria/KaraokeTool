"""A round's input fetched once, not read over the network all the time
(v1.0.23, B647).

The owner: when work is handed out, put a copy of the data on the helper
first, so there is no network traffic all the time - rather twice a lot
(fetching and handing in) than the network the whole time. And clean it
up afterwards, in a folder of its own under %TEMP% for safety.

So a round that runs on a helper copies what it reads - the song, a
render's audio, logo, background and font - from the work folder on the
share into ``%TEMP%\\KaraokeToolHelper\\<round>``, works there, hands its
result in once, and the folder goes when the round is done, whatever
happened. What a crash left behind goes at the next start of a lane.

On the laptop itself the work folder is on its own disk: there nothing
is copied.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

#: The helper's own folder in %TEMP%.
FOLDER_NAME = "KaraokeToolHelper"
#: A folder left behind longer ago than this is a crash's: it goes.
STALE_S = 24 * 3600.0


def base() -> Path:
    return Path(tempfile.gettempdir()) / FOLDER_NAME


def is_remote(path: Path) -> bool:
    """Is this on a share (``\\\\server\\...``) rather than a local disk?"""
    text = str(path).replace("/", "\\")
    return text.startswith("\\\\")


def _safe(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(text))[:40]


@contextmanager
def fetched(root: Path, job_id: str, relative: Sequence[str],
            copy: bool | None = None) -> Iterator[list[Path]]:
    """The files or folders ``relative`` (to ``root``, the work folder) as
    local paths for as long as the ``with`` lasts. Copied into
    ``%TEMP%\\KaraokeToolHelper\\<round>`` when the work folder is on a
    share (or ``copy`` says so), else the paths themselves."""
    root = Path(root)
    wanted = [root / item for item in relative]
    if copy is None:
        copy = is_remote(root)
    if not copy:
        yield wanted
        return
    folder = base() / f"{_safe(job_id)}_{os.getpid()}_{time.time_ns()}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        local = []
        for number, source in enumerate(wanted):
            target = folder / f"{number}_{source.name}"
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
            local.append(target)
        yield local
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def tidy(now: float | None = None) -> int:
    """What rounds that crashed left in the helper's folder: away.
    Returns how many folders went."""
    now = time.time() if now is None else now
    gone = 0
    try:
        folders = [path for path in base().iterdir() if path.is_dir()]
    except OSError:
        return 0
    for path in folders:
        try:
            if now - path.stat().st_mtime > STALE_S:
                shutil.rmtree(path, ignore_errors=True)
                gone += 1
        except OSError:
            continue
    return gone
