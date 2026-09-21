"""One-off migration of the two text files to their English names (B555).

Until v1.0.5 the lyrics and the karaoke text sat in every project as
``input/<song>/songtekst.txt`` and ``karaoketekst.txt`` - the last Dutch
names in the tree, and the only ones the user also sees in Explorer.
From v1.0.6 they are ``lyrics.txt`` and ``karaoke_text.txt``, the names
the program already used everywhere else (``input:lyrics``,
``source_lyrics``, the ``lyrics`` key in ``input_names``).

There is no fallback on the old names: two truths for one file is how a
rename stays half done for years. So a project has to be migrated before
it opens again, and that is what this does.

What it does NOT cost: the derivation chain compares the SHA1 of a
source, never its path (``pipeline.sync_input_changes``). Renaming a
file with unchanged content is therefore invisible to it - the word
coupling, ``timing.json`` and ``timing_auto.json`` stay exactly where
they are. The path recorded in ``project.json`` is rewritten anyway,
because a path that points at a name which no longer exists is a lie
waiting for the next reader.

Safety measures, in the order they matter:

1. **Dry run by default.** Without ``--apply`` nothing is written; the
   script only says what it would do.
2. **Backup first.** Every file that is touched is copied to
   ``<name>.pre_b555.bak`` before anything is written. Nothing is
   deleted, ever.
3. **Idempotent.** A project that is already migrated is recognised and
   skipped, so running it twice is harmless.
4. **Verified afterwards.** With ``--apply`` it checks per project that
   the new file exists, that its content is byte for byte what the old
   one held, and that no recorded path still names the old file.

There is deliberately no "is the app running" check. An earlier version
of this script had one, on a ``.write_test`` that nothing in the program
ever leaves behind - a promise in a docstring and nothing underneath it,
which is worse than no promise at all. The real protection sits in the
app: :func:`pipeline.unmigrated_texts` makes every step refuse on a
project that still carries the old names, so opening one before
migrating costs nothing. Close KaraokeTool anyway, or it writes the old
path back into ``project.json`` after this has run.

Usage::

    python3 tools/migrate_texts.py <installation-dir>          # dry run
    python3 tools/migrate_texts.py <installation-dir> --apply  # do it
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import karaoke_text, song_text            # noqa: E402

#: ``old name -> new name``. The new names come from the modules that
#: own them, so this mapping cannot drift away from the program.
RENAMES = {
    "songtekst.txt": song_text.LYRICS_FILENAME,
    "karaoketekst.txt": karaoke_text.FILENAME,
}

#: Suffix of the copy made before anything is written.
BACKUP_SUFFIX = ".pre_b555.bak"

def _file_name(path: str) -> str:
    """The last piece of a stored path, whatever slash wrote it.

    ``PurePath`` follows the platform it runs on, and the paths in
    ``project.json`` are Windows paths. On Windows that is the same
    thing; anywhere else ``PurePath("C:\\x\\songtekst.txt").name`` is
    the whole string and nothing ever matches. The dry run over the
    real installation is what showed it: 44 files to rename and 0
    paths to correct, where the answer is 44 and 44.
    """
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _projects(root: Path) -> list[Path]:
    """Every project folder under ``input/``."""
    inputs = root / "input"
    if not inputs.is_dir():
        return []
    return sorted(p for p in inputs.iterdir() if p.is_dir())


def rename_texts(root: Path, apply: bool, report: list[str]) -> int:
    """Rename the two text files in every project. Returns the count."""
    done = 0
    for project in _projects(root):
        for old_name, new_name in RENAMES.items():
            old = project / old_name
            new = project / new_name
            if not old.exists():
                if not new.exists():
                    report.append(f"  {project.name}: no {old_name} and no "
                                  f"{new_name} - nothing to do")
                continue
            if new.exists():
                report.append(f"  {project.name}: {new_name} already there "
                              f"AND {old_name} - left alone, look at it "
                              "yourself")
                continue
            report.append(f"  {project.name}: {old_name} -> {new_name}")
            if apply:
                shutil.copyfile(old, old.with_name(old.name + BACKUP_SUFFIX))
                old.rename(new)
            done += 1
    return done


def fix_stored_paths(root: Path, apply: bool, report: list[str]) -> int:
    """Rewrite the paths in ``project.json`` that name the old files."""
    changed = 0
    for store in sorted((root / "output").glob("*/settings/project.json")):
        try:
            data = json.loads(store.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            report.append(f"  {store}: unreadable ({exc}) - skipped")
            continue
        # ``ProjectStore`` tolerates a file of another shape, so this
        # has to as well: crashing here would leave the rename done and
        # the verification unrun.
        steps = data.get("steps") if isinstance(data, dict) else None
        if not isinstance(steps, dict):
            report.append(f"  {store.parts[-3]}: project.json has no "
                          "steps of the expected shape - left alone")
            continue
        hits = 0
        for step in steps.values():
            if not isinstance(step, dict):
                continue
            path = step.get("path")
            if not isinstance(path, str):
                continue
            # The NAME, not the tail of the path: ``my_songtekst.txt``
            # is somebody else's file and ``my_lyrics.txt`` is not where
            # it went.
            name = _file_name(path)
            if name in RENAMES:
                step["path"] = path[:-len(name)] + RENAMES[name]
                hits += 1
        if not hits:
            continue
        report.append(f"  {store.parts[-3]}: {hits} path(s) in project.json")
        changed += hits
        if apply:
            shutil.copyfile(store,
                            store.with_name(store.name + BACKUP_SUFFIX))
            store.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                             encoding="utf-8")
    return changed


def verify(root: Path, report: list[str]) -> int:
    """Check afterwards. Returns the number of complaints."""
    complaints = []
    for project in _projects(root):
        for old_name, new_name in RENAMES.items():
            old = project / old_name
            new = project / new_name
            backup = project / (old_name + BACKUP_SUFFIX)
            if old.exists():
                complaints.append(f"{project.name}: {old_name} is still here")
            if backup.exists() and not new.exists():
                complaints.append(f"{project.name}: {new_name} is missing "
                                  "while there is a backup")
            if backup.exists() and new.exists() \
                    and _sha1(backup) != _sha1(new):
                complaints.append(f"{project.name}: {new_name} does not hold "
                                  f"what {old_name} held")
    for store in sorted((root / "output").glob("*/settings/project.json")):
        # Only the paths this script rewrites. Searching the whole file
        # for the old words would also hit ``input_names``, which keeps
        # the name of the file the USER picked - and a text he called
        # "Kedeng songtekst.txt" is his business, not a leftover.
        try:
            data = json.loads(store.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        steps = data.get("steps") if isinstance(data, dict) else None
        if not isinstance(steps, dict):
            continue
        for step in steps.values():
            if not isinstance(step, dict):
                continue
            path = step.get("path")
            if isinstance(path, str) and _file_name(path) in RENAMES:
                complaints.append(f"{store.parts[-3]}: project.json still "
                                  f"names {_file_name(path)}")
    for line in complaints:
        report.append("  " + line)
    return len(complaints)


def main(argv: list[str] | None = None) -> int:
    """Run the migration, or say what it would do."""
    parser = argparse.ArgumentParser(
        description="Rename songtekst.txt/karaoketekst.txt to "
                    "lyrics.txt/karaoke_text.txt in every project (B555).")
    parser.add_argument("root", help="the KaraokeTool installation folder")
    parser.add_argument("--apply", action="store_true",
                        help="really write; without this it is a dry run")
    arguments = parser.parse_args(argv)
    root = Path(arguments.root).resolve()
    if not (root / "input").is_dir():
        print(f"no input folder in {root} - is that the installation?")
        return 1
    report = ["dry run - nothing is written" if not arguments.apply
              else "applying", "", "text files:"]
    renamed = rename_texts(root, arguments.apply, report)
    report.append("stored paths:")
    paths = fix_stored_paths(root, arguments.apply, report)
    report.append("")
    report.append(f"{renamed} file(s) and {paths} path(s)"
                  + (" changed" if arguments.apply else " would change"))
    problems = 0
    if arguments.apply:
        report.append("verification:")
        problems = verify(root, report)
        report.append("  nothing wrong" if not problems
                      else f"  {problems} thing(s) to look at")
        report.append("")
        report.append(f"The copies are called *{BACKUP_SUFFIX}. Delete them "
                      "yourself once you have seen the app open a project.")
    print("\n".join(report))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
