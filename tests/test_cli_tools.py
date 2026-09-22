"""The command-line tools are RUN here, not read (B565).

Twice this month a tool turned out to have been dead for a hundred
builds. B550: ``tools/timing_eval.py`` called
``timing_eval.vergelijk_paden``, a name that was renamed at B379.
B562: ``modules/timing_eval.format_report`` asked for a dict key
``gem`` that had become ``avg`` at B299. Both raise on the first line
that does any work, so the tool could not print a single row - and the
suite stayed green through all of it.

It stayed green because about ninety of the tests that touch this
machinery assert on SOURCE TEXT (``assert "x" in
inspect.getsource(...)``), and a text assertion passes on code that
crashes: the name is in the file whether or not calling it raises. It
was proven this week that putting the B550 bug back verbatim leaves the
whole suite green, which is the same as saying the suite did not cover
these tools at all.

So this file executes them, in two layers:

1. every tool answers ``--help`` with exit code 0 and a usage line, and
   does no work while doing so. That second half is not decoration:
   before B564 ``github_export.py --help`` built a complete export into
   a folder beside the project, and ``write_dependency_doc.py --help``
   rewrote the document. Both are checked by snapshotting the tree
   before and after and requiring it unchanged.
2. the tools that need neither Whisper, nor Demucs, nor the owner's own
   projects are really run, on data made in ``tmp_path``, and their
   output is read.

``tools/whisper_probe.py`` stays in layer 1 on purpose: it loads a
Whisper model before it can report anything at all, so running it here
would mean a suite that only passes on the owner's machine - worse than
a gap that is written down. Its ``--help`` is the part that can be
checked cheaply, and it is checked.

``tools/timing_regression.py`` is not in layer 2 here because it is
already run for real in ``tests/test_project_safety.py``, over two
projects built in a temporary folder: that test is about where it
writes, and running it twice would only make the suite slower.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
DOC = ROOT / "docs" / "dependencies.md"

#: Seconds per subprocess. Generous for a slow machine, small enough
#: that a tool which hangs fails the file instead of the run.
TIMEOUT = 30

#: Folders whose contents are written by the interpreter and by pytest
#: itself, so they say nothing about what a tool did.
IGNORED = {"__pycache__", ".pytest_cache", ".git"}

#: Files in ``tools/`` that are data and not a program: no ``main()``,
#: so no usage line, and that is asserted rather than skipped - if such
#: a file ever grows a command line, the test says so instead of
#: quietly passing. Empty since B571 took ``b299_dictionary.py`` out.
DATA_MODULES: set[str] = set()


def _tool_names() -> list[str]:
    """Every tool as a file name, so the ids read as the tool."""
    if not TOOLS.is_dir():  # pragma: no cover - published copies keep it
        return []
    return sorted(path.name for path in TOOLS.glob("*.py")
                  if path.name != "__init__.py")


def _run(*arguments: object) -> subprocess.CompletedProcess:
    """Run a tool as a separate process, from the project root."""
    command = [sys.executable] + [str(item) for item in arguments]
    return subprocess.run(command, cwd=str(ROOT), capture_output=True,
                          text=True, timeout=TIMEOUT)


def _snapshot(folder: Path) -> dict[str, tuple[int, str]]:
    """``relative path -> (size, sha1)`` for everything under *folder*.

    Content and not modification time. The owner runs this suite on a
    Windows machine where the project may sit in a synced folder, and
    an indexer or an editor that touches a file during the thirty walks
    below would otherwise fail a tool for something it did not do. A
    file that a tool writes, adds or removes shows up either way, and a
    rewrite with the same bytes is not damage.

    Folders are recorded by presence only: a folder's own mtime changes
    as soon as the interpreter drops a ``__pycache__`` beside a module.
    """
    state: dict[str, tuple[int, str]] = {}
    for path in folder.rglob("*"):
        relative = path.relative_to(folder)
        if set(relative.parts) & IGNORED:
            continue
        if path.is_dir():
            state[str(relative)] = (-1, "")
            continue
        data = path.read_bytes()
        state[str(relative)] = (len(data), hashlib.sha1(data).hexdigest())
    return state


def _neighbours() -> list[str]:
    """What sits beside the project, by folder name.

    ``github_export.py`` writes into ``<project>_git`` NEXT to the
    project when it is given no target, so a snapshot of the project
    itself would have missed exactly the accident of B564.

    Folders only: the accident makes a folder, and the folder the
    project sits in is the owner's own, where a download or a sync
    client may drop a file while the suite runs.
    """
    return sorted(path.name for path in ROOT.parent.iterdir()
                  if path.is_dir())


def _timing_file(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps({"lines": rows}), encoding="utf-8")


def _installation(root: Path) -> Path:
    """A small fake KaraokeTool installation for the migrations."""
    song = root / "input" / "Song_A"
    song.mkdir(parents=True)
    (song / "songtekst.txt").write_text("line one\n", encoding="utf-8")
    (song / "karaoketekst.txt").write_text("regel een\n", encoding="utf-8")
    settings = root / "output" / "Song_A" / "settings"
    settings.mkdir(parents=True)
    (settings / "project.json").write_text(
        json.dumps({"songtekst": "input/Song_A/songtekst.txt",
                    "taal": "nl"}), encoding="utf-8")
    config = root / "config"
    config.mkdir()
    (config / "config.json").write_text(
        json.dumps({"taal": "nl"}), encoding="utf-8")
    return root


# --------------------------------------------------------------- layer 1

@pytest.mark.parametrize("name", _tool_names())
def test_help_answers_and_does_no_work(name: str) -> None:
    """Prevents a tool that cannot even start, and one that works on
    ``--help``: exit 0, a usage line, and a tree that did not move."""
    before = _snapshot(ROOT)
    neighbours = _neighbours()
    result = _run(TOOLS / name, "--help")
    assert result.returncode == 0, result.stderr
    if name in DATA_MODULES:
        source = (TOOLS / name).read_text(encoding="utf-8")
        assert "\ndef main(" not in source, (
            f"{name} has grown a main(); it is listed as a data module")
        assert not result.stdout.startswith("usage:"), result.stdout[:200]
    else:
        assert result.stdout.startswith("usage:"), (
            f"{name} --help printed: {result.stdout[:200]!r}")
    assert _snapshot(ROOT) == before, f"{name} --help changed the project"
    assert _neighbours() == neighbours, f"{name} --help wrote beside it"


# --------------------------------------------------------------- layer 2

def test_timing_eval_prints_the_per_block_table(tmp_path: Path) -> None:
    """Prevents B550 and B562 coming back: the tool must reach the end
    of the table, not raise halfway down it."""
    auto = tmp_path / "timing_auto.json"
    reference = tmp_path / "timing.json"
    _timing_file(auto, [
        {"text": "first line", "block": 1,
         "syllables": [{"start": 1.0, "end": 1.5},
                       {"start": 1.5, "end": 2.0}]},
        {"text": "second line", "block": 1,
         "syllables": [{"start": 3.0, "end": 3.4}]},
        {"text": "third line", "block": 2,
         "syllables": [{"start": 5.2, "end": 5.9}]},
    ])
    _timing_file(reference, [
        {"text": "first line", "block": 1,
         "syllables": [{"start": 1.1, "end": 1.6},
                       {"start": 1.6, "end": 2.1}]},
        {"text": "second line", "block": 1,
         "syllables": [{"start": 3.05, "end": 3.5}]},
        {"text": "third line", "block": 2,
         "syllables": [{"start": 5.0, "end": 5.8}]},
    ])

    result = _run(TOOLS / "timing_eval.py", auto, reference)

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert str(auto) in output and str(reference) in output
    # The header and the totals line are translated, the rows are not:
    # "<block> | <n> | ...ms | ...ms | ...ms".
    rows = [line for line in output.splitlines()
            if re.match(r"^\s*\d+ \|", line)]
    assert len(rows) == 2, output
    assert re.match(r"^\s*1 \|\s+2 \|", rows[0]), rows[0]
    assert re.match(r"^\s*2 \|\s+1 \|", rows[1]), rows[1]
    assert rows[0].count("ms") == 3 and rows[1].count("ms") == 3
    assert "-----+----+" in output
    assert "(n=3)" in output          # the three pairs, in the totals


def test_timing_eval_says_so_when_a_file_is_missing(tmp_path: Path) -> None:
    """Prevents the missing-file branch dying unseen: it must report,
    not raise, because that is the branch a mistyped path hits."""
    present = tmp_path / "timing.json"
    _timing_file(present, [])
    result = _run(TOOLS / "timing_eval.py", present, tmp_path / "gone.json")
    assert result.returncode == 1
    assert "gone.json" in result.stderr


def test_dependency_doc_check_passes_and_writes_nothing() -> None:
    """Prevents the generated document drifting from the chain, and
    prevents ``--check`` writing the thing it is checking."""
    before = _snapshot(ROOT)
    result = _run(TOOLS / "write_dependency_doc.py", "--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "up to date" in result.stdout
    assert _snapshot(ROOT) == before, "--check touched the tree"
    assert str(DOC.relative_to(ROOT)) in before, "the document is gone"


def test_github_export_check_reads_an_empty_folder(tmp_path: Path) -> None:
    """Prevents the publication check raising on the two folders it
    meets most: one that is empty, and one that is not there."""
    empty = tmp_path / "copy"
    empty.mkdir()

    result = _run(TOOLS / "github_export.py", "--check", empty)
    # Nothing to find and no history to read, so: clean.
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no names or paths of the owner left" in result.stdout
    assert "not a git working copy" in result.stdout
    assert list(empty.iterdir()) == [], "--check wrote into the folder"

    missing = _run(TOOLS / "github_export.py", "--check", tmp_path / "no")
    # A folder that is not there is not clean, it is unanswered.
    assert missing.returncode == 1
    assert "does not exist" in missing.stdout


def test_migrate_texts_dry_run_writes_nothing(tmp_path: Path) -> None:
    """Prevents the rename migration raising on a normal installation,
    and prevents a dry run touching a single file."""
    root = _installation(tmp_path / "install")
    before = _snapshot(root)

    result = _run(TOOLS / "migrate_texts.py", root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "dry run" in result.stdout
    assert "songtekst.txt -> lyrics.txt" in result.stdout
    assert "karaoketekst.txt -> karaoke_text.txt" in result.stdout
    assert _snapshot(root) == before, "the dry run wrote"


def test_migrate_texts_refuses_a_folder_that_is_not_one(
        tmp_path: Path) -> None:
    """Prevents the guard going missing: pointed at anything without an
    ``input`` folder the tool must stop, not start renaming."""
    stray = tmp_path / "elsewhere"
    stray.mkdir()
    result = _run(TOOLS / "migrate_texts.py", stray)
    assert result.returncode == 1
    assert "is that the installation" in result.stdout


def test_migrate_b299_dry_run_writes_nothing(tmp_path: Path) -> None:
    """Prevents the B299 key migration raising, and prevents a dry run
    converting anything on disk."""
    root = _installation(tmp_path / "install")
    before = _snapshot(root)

    result = _run(TOOLS / "migrate_b299.py", root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "DRY RUN" in result.stdout
    assert "config.json: converted" in result.stdout
    assert "project.json: converted" in result.stdout
    assert _snapshot(root) == before, "the dry run wrote"


def test_migrate_b299_refuses_a_path_that_is_no_folder(
        tmp_path: Path) -> None:
    """Prevents the tool walking a path that does not exist: it reports
    and returns 2."""
    result = _run(TOOLS / "migrate_b299.py", tmp_path / "nothing_here")
    assert result.returncode == 2
    assert "not a folder" in result.stdout
