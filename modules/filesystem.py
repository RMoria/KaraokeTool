"""File system: folder structure, input files and ``project.json``.

The class :class:`ProjectStore` keeps all intermediate results in
``cache/project.json``, so that expensive steps (such as Whisper) do not
have to run again when only the karaoke processing changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .translations import t

logger = logging.getLogger(__name__)

#: B280: ``.m4a``/``.flac``/``.ogg``/``.aac`` added (e.g. audio
#: fragments merged via Clipchamp, which exports as ``.m4a``, or
#: lossless rips/Audacity exports in other formats) - ffmpeg/ffprobe
#: already process those just as generically as mp3/wav, so this was
#: purely a whitelist extension.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".wav", ".mp3", ".m4a", ".flac",
                                        ".ogg", ".aac")


def safe_name(text: str) -> str:
    """Make a safe folder/file name out of free text."""
    cleaned = "".join(ch if ch.isalnum() or ch in " -_" else "_"
                      for ch in text.strip())
    return "_".join(cleaned.split())[:60]


@dataclass(frozen=True)
class ProjectPaths:
    """All fixed paths within the project, derived from the project root.

    With a ``song`` (song title) ``input`` and ``output`` get a subfolder
    per song project; the main folders stay ready for the next use.
    """

    root: Path
    song: str = ""
    #: Optional own output main folder (Windows path or UNC) outside the
    #: project root (B214). ``None`` = the default ``root/output``.
    output_base: Path | None = None

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def backgrounds_dir(self) -> Path:
        """Central store for chosen background images (B480), next to the
        global settings: a picture is chosen once and then used for any
        project."""
        return self.config_dir / "backgrounds"

    @property
    def languages_dir(self) -> Path:
        """Collection folder for 'on-the-go' languages (B241), shared
        across projects."""
        return self.root / "languages"

    @property
    def input_root(self) -> Path:
        return self.root / "input"

    @property
    def input_dir(self) -> Path:
        return self.input_root / self.song if self.song else self.input_root

    @property
    def cache_root(self) -> Path:
        return self.root / "cache"

    @property
    def cache_dir(self) -> Path:
        return self.cache_root / self.song if self.song else self.cache_root

    @property
    def output_root(self) -> Path:
        return self.output_base if self.output_base is not None \
            else self.root / "output"

    @property
    def output_dir(self) -> Path:
        return (self.output_root / self.song if self.song
                else self.output_root)

    @property
    def settings_dir(self) -> Path:
        """Permanent folder with all choices/settings of this project."""
        return self.output_dir / "settings"

    @property
    def timing_file(self) -> Path:
        return self.settings_dir / "timing.json"

    @property
    def timing_auto_file(self) -> Path:
        """Automatically generated timing (for comparison with the
        manually edited ``timing.json``)."""
        return self.settings_dir / "timing_auto.json"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def project_file(self) -> Path:
        """Permanent project record (choices) in the settings folder."""
        return self.settings_dir / "project.json"


def is_writable(directory: Path) -> bool:
    """Can ``directory`` be written to? (B221)

    Tests with a temporary file; ``False`` on a read-only location
    (e.g. Program Files) or a permissions problem."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".karaoketool_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_data_root(app_root: Path) -> Path:
    """Where the writable data (input/output/cache/logs/config) goes (B221).

    Order: explicit ``KARAOKETOOL_DATA`` (set by the launcher) -> the app
    folder itself if it is writable -> otherwise ``%LOCALAPPDATA%\\
    KaraokeTool`` (e.g. when the app is in Program Files). This way the app
    also works from a read-only location, without hard-coded paths."""
    env = os.environ.get("KARAOKETOOL_DATA")
    if env:
        return Path(env)
    if is_writable(app_root):
        return app_root
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData"
                                                 / "Local")
    return Path(base) / "KaraokeTool"


def output_base_from(output_dir: str) -> Path | None:
    """Convert the configured output folder string into a ``Path`` (B214).

    Empty or only whitespace -> ``None`` (the default ``<root>/output``)."""
    schoon = (output_dir or "").strip()
    return Path(schoon) if schoon else None


def ensure_directories(paths: ProjectPaths) -> None:
    """Create all project folders if they do not exist yet."""
    for directory in (
        paths.config_dir,
        paths.input_dir,
        paths.cache_dir,
        paths.output_dir,
        paths.settings_dir,
        paths.logs_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def find_audio_file(directory: Path, stem: str) -> Path | None:
    """Look for ``<stem>`` with one of ``SUPPORTED_EXTENSIONS`` in a folder.

    Args:
        directory: Folder that is searched (usually ``input``).
        stem: File name without extension, e.g. ``"original"``.

    Returns:
        The path found, or ``None`` if no file exists. If several variants
        exist, then the first in ``SUPPORTED_EXTENSIONS`` wins (``.wav``
        first, no conversion needed).
    """
    found = [directory / f"{stem}{ext}" for ext in SUPPORTED_EXTENSIONS
             if (directory / f"{stem}{ext}").exists()]
    if not found:
        return None
    if len(found) > 1:
        logger.warning(t("log_several_variants"),
                       stem, found[0].name)
    return found[0]


def clean_cache(cache_dir: Path, keep: tuple[str, ...] = ()) -> int:
    """Empty the cache completely.

    Is called at start-up and shutdown: all intermediate results
    (conversions, project.json, transcriptie.json) are removed. Every
    session thus starts clean; Whisper runs again per session.

    Returns:
        The number of removed files.
    """
    if not cache_dir.exists():
        return 0
    import shutil
    import stat
    import sys

    def _force(func, path, *_):
        """Recovery function: remove read-only and retry ('del /F')."""
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            logger.warning(t("log_delete_failed"), path)

    def _rmtree(target: Path) -> None:
        # onexc (3.12+) replaces the deprecated onerror; support both.
        if sys.version_info >= (3, 12):
            shutil.rmtree(target, onexc=_force)
        else:
            shutil.rmtree(target, onerror=_force)

    removed = 0
    for entry in cache_dir.iterdir():
        if entry.name in keep:
            continue
        try:
            if entry.is_dir():
                _rmtree(entry)
            else:
                try:
                    entry.unlink()
                except PermissionError:
                    os.chmod(entry, stat.S_IWRITE)
                    entry.unlink()
            removed += 1
        except OSError:
            logger.warning(t("log_cache_item_failed"), entry)
    # Check whether something unexpectedly still remains (e.g. a locked
    # file) and report that explicitly instead of leaving it silent (B184).
    rest = [p for p in cache_dir.iterdir() if p.name not in keep]
    if rest:
        logger.warning(t("log_cache_not_empty"),
                       len(rest), ", ".join(p.name for p in rest[:5]))
    if removed:
        logger.info(t("log_cache_cleaned"),
                    removed)
    return removed


def warn_about_stray_store(paths: "ProjectPaths") -> Path | None:
    """Say so when a project record sits where no project lives (B445).

    ``output/settings/project.json`` belongs to nobody: the settings
    folder of a context WITHOUT a song. It came into being because that
    context could write, and it has been there on the user's machine
    since the end of July, holding the video titles of a song that was
    made later somewhere else. Every start it produced a warning that
    its structure was unexpected - true, and useless, because it named a
    path and not the problem.

    Deliberately only a warning. The file is not the program's to throw
    away: it may hold something the user still wants, and a program that
    quietly deletes files in a folder called "output" is a program you
    stop trusting. So it says what it is, and that it can go.
    """
    stray = paths.output_root / "settings" / "project.json"
    if not stray.exists():
        return None
    logger.warning(t("log_stray_project_store"), stray)
    return stray


def _safe_iterdir(directory: Path):
    """The contents of a folder, empty when it cannot be read."""
    try:
        return sorted(directory.iterdir())
    except OSError:
        return []


def prune_orphan_projects(root: Path,
                          output_root: Path | None = None) -> list[str]:
    """Clean up input folders of projects without an (existing) output
    folder (B112).

    A project 'exists' as long as its output folder is there (that
    contains the permanent settings and end products). If it has been
    removed manually, then the project is gone; a leftover input folder
    with the same name is then cleaned up. Loose files in the input root
    (without a title) are left untouched.

    Returns:
        The names of the cleaned-up (orphan) projects.
    """
    import shutil
    input_root = root / "input"
    # B469: this used to hardcode ``root/output``. With an own output
    # folder set (B214) that place is empty, so every project looked
    # orphaned and its input folder was deleted at every start. The
    # caller now passes the output root that is really in use.
    if output_root is None:
        output_root = root / "output"
    pruned: list[str] = []
    if not input_root.exists():
        return pruned
    # B469: an output folder without a single project in it means "we
    # cannot see it", not "they are all orphans". Without this brake the
    # first start after the output folder is moved - or a drive that
    # comes back empty - would still empty every input folder. Checking
    # that the folder EXISTS is not enough: the app creates it itself one
    # line before this runs.
    # ``settings`` does not count: the app creates that folder itself
    # (B445 even warns about it), so it is there in a brand new and
    # otherwise empty output folder too.
    projects = [entry for entry in _safe_iterdir(output_root)
                if entry.is_dir() and entry.name != "settings"]
    if not projects:
        logger.warning(t("log_orphans_skipped"), output_root)
        return pruned
    candidates = [entry for entry in _safe_iterdir(input_root)
                  if entry.is_dir()
                  and not (output_root / entry.name).exists()]
    # Second brake (B469): EVERYTHING being an orphan at once is not a
    # cleaning job but a sign that we are measuring against the wrong
    # folder. With one project it can genuinely be so; with more it
    # cannot.
    others = sum(1 for entry in _safe_iterdir(input_root) if entry.is_dir())
    if len(candidates) > 1 and len(candidates) == others:
        logger.warning(t("log_orphans_all"), len(candidates), output_root)
        return pruned
    for entry in candidates:
        try:
            shutil.rmtree(entry)
            pruned.append(entry.name)
        except OSError:
            logger.warning(t("log_orphan_input_failed"), entry)
    if pruned:
        logger.info(t("log_orphans_cleaned"),
                    pruned)
    return pruned


def remove_empty_tree(directory: Path) -> bool:
    """Remove a folder if it (recursively) contains no files.

    Empty subfolders are cleaned up from the inside out first; if the
    branch still contains a file somewhere, then everything stays. Is
    used to clean up the leftover empty folders (e.g. ``output/settings``
    and the empty ``cache``) after the root->project migration.

    Returns:
        ``True`` if the folder was removed in the end.
    """
    if not directory.exists() or not directory.is_dir():
        return False
    for child in list(directory.iterdir()):
        if child.is_dir():
            remove_empty_tree(child)
    try:
        directory.rmdir()  # only succeeds if the folder is really empty now
        logger.info(t("log_empty_dir_cleaned"), directory)
        return True
    except OSError:
        return False


def clean_logs(logs_dir: Path, keep: int = 5) -> int:
    """Keep the newest ``keep`` log files; remove the rest.

    Is called together with the cleaning of the cache. The daily log
    files are named ``YYYY-MM-DD.log``, so newest first when sorted by
    name; today's log file (in use) belongs to the newest and therefore
    stays.

    Returns:
        The number of removed log files.
    """
    if not logs_dir.exists():
        return 0
    log_files = sorted((f for f in logs_dir.glob("*.log") if f.is_file()),
                       reverse=True)
    removed = 0
    for old_log in log_files[keep:]:
        try:
            old_log.unlink()
            removed += 1
        except OSError:
            logger.warning(t("log_logfile_failed"), old_log)
    if removed:
        logger.info(t("log_logs_cleaned"),
                    removed, min(len(log_files), keep))
    return removed


def file_sha1(path: Path) -> str:
    """Calculate the SHA1 checksum of a file (read in blocks)."""
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _now_iso() -> str:
    """Current time as an ISO-8601 string in UTC."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProjectStore:
    """Management of ``project.json`` with results per pipeline step."""

    def __init__(self, path: Path, writable: bool = True) -> None:
        """Open (or initialise) the project record.

        Args:
            path: Path to ``project.json``.
            writable: False for the record of a context WITHOUT a song
                (B445). Such a context has no project to write about, so
                everything it collects is misfiled by definition - and
                it was: ``output/settings/project.json`` on the user's
                machine holds the video titles of a song that did not
                exist yet, and complained at every start that its
                structure was wrong. Reading stays allowed, so an
                existing file is not suddenly invisible.
        """
        self._path = path
        self._writable = bool(writable)
        # Reentrant lock: with parallel detection (B90) several threads
        # write steps to project.json at the same time.
        self._lock = threading.RLock()
        self._data: dict[str, Any] = self._load()

    @property
    def path(self) -> Path:
        """Path to the underlying JSON file."""
        return self._path

    def _load(self) -> dict[str, Any]:
        """Read the file; start with an empty record on errors."""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("steps"), dict):
                    return data
                # B445: without a song this is the loose record, and
                # ``warn_about_stray_store`` has just said so in words
                # that explain what to do. Repeating "unexpected
                # structure" here only names a path again.
                if self._writable:
                    logger.warning(t("log_unexpected_structure"), self._path)
            except json.JSONDecodeError:
                logger.warning(t("log_project_damaged"), self._path)
        return {"created": _now_iso(), "steps": {}}

    def save(self) -> None:
        """Write the record to disk (B445: unless there is no project)."""
        if not self._writable:
            logger.debug(t("log_project_not_saved"), self._path)
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.debug(t("log_project_saved"), self._path)

    def get_step(self, name: str) -> dict[str, Any] | None:
        """Give the stored data of a step, or ``None``."""
        with self._lock:
            step = self._data["steps"].get(name)
            return dict(step) if isinstance(step, dict) else None

    def get_meta(self, key: str, default: Any = None) -> Any:
        """Read a project-wide meta value (e.g. the display name)."""
        value = self._data.get(key, default)
        return value if value not in ("", None) else default

    def set_meta(self, key: str, value: Any) -> None:
        """Store a project-wide meta value and write it out at once."""
        with self._lock:
            self._data[key] = value
            self.save()
        logger.debug(t("log_meta_updated"), key)

    def clear_meta(self, key: str) -> None:
        """Remove a project-wide meta value (B311).

        Until v0.97 there was no counterpart to :meth:`set_meta`, and
        ``clear_step`` deliberately does not reach the top level of
        ``project.json``. The consequence was that the project-wide
        markers ("karaoke made from the original", the vocal onset, the
        fixed language) survived every invalidation - also when the audio
        or the lyrics they belonged to had long since been replaced.
        """
        with self._lock:
            removed = self._data.pop(key, None) is not None
            if removed:
                self.save()
        if removed:
            logger.debug(t("log_meta_removed"), key)

    def set_step(self, name: str, payload: dict[str, Any]) -> None:
        """Store the data of a step (with timestamp) and save at once."""
        entry = dict(payload)
        entry["updated"] = _now_iso()
        with self._lock:
            self._data["steps"][name] = entry
            self.save()
        logger.debug(t("log_step_updated"), name)

    def rewrite_prefix(self, old: Path, new: Path) -> int:
        """Replace path prefixes in all stored steps.

        Needed when the song title changes and files move to another
        (sub)folder; all references in ``project.json`` then stay
        correct.

        Returns:
            The number of adjusted values.
        """
        old_text, new_text = str(old), str(new)

        def walk(value):
            if isinstance(value, str) and value.startswith(old_text):
                return new_text + value[len(old_text):], 1
            if isinstance(value, dict):
                changed = 0
                for key in value:
                    value[key], hits = walk(value[key])
                    changed += hits
                return value, changed
            if isinstance(value, list):
                changed = 0
                for position in range(len(value)):
                    value[position], hits = walk(value[position])
                    changed += hits
                return value, changed
            return value, 0

        self._data, count = walk(self._data)
        if count:
            self.save()
            logger.info(t("log_paths_updated"), count, old_text, new_text)
        return count

    def clear_step(self, name: str) -> None:
        """Remove a step from the record (if present)."""
        with self._lock:
            removed = self._data["steps"].pop(name, None) is not None
            if removed:
                self.save()
        if removed:
            logger.debug(t("log_step_removed"), name)
