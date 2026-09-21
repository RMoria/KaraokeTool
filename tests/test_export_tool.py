"""The safety catch on the folder the publication tool empties (B544).

``tools/github_export.py`` does not travel to the public repository - it
lists exactly the names it is there to hide - so this file skips itself
when the tool is absent rather than turning a clone red.

What is tested is the one thing that can cost something: ``_clear``
deletes a folder before writing the export into it. Guarding that with
"only a folder this tool made itself" was too narrow, and the very first
real push proved it: the normal way to publish is to clone the
repository and export over the clone, so that renamed and deleted files
end up in the commit, and a fresh clone carries neither the marker nor
emptiness.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "github_export.py"


def _tool():
    if not TOOL.exists():
        pytest.skip("github_export.py is not part of a published copy")
    spec = importlib.util.spec_from_file_location("export_tool", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_an_empty_folder_may_be_emptied(tmp_path: Path) -> None:
    target = tmp_path / "out"
    target.mkdir()
    _tool()._clear(target)
    assert list(target.iterdir()) == []


def test_a_folder_this_tool_made_may_be_emptied(tmp_path: Path) -> None:
    tool = _tool()
    target = tmp_path / "out"
    target.mkdir()
    (target / tool.MARKER).write_text("x", encoding="utf-8")
    (target / "old.py").write_text("x", encoding="utf-8")
    tool._clear(target)
    assert list(target.iterdir()) == []


def test_a_git_working_copy_may_be_emptied(tmp_path: Path) -> None:
    """The case that broke the first push.

    A clone holds no marker, so the old rule refused it and nothing
    could be published. Emptying it is harmless: everything in it also
    lives in the repository, and ``git status`` shows afterwards exactly
    what the export changed - including the files it no longer writes,
    which is the whole reason for cloning first.
    """
    tool = _tool()
    target = tmp_path / "clone"
    (target / ".git").mkdir(parents=True)
    (target / "README.md").write_text("x", encoding="utf-8")
    (target / "modules").mkdir()
    tool._clear(target)
    assert [p.name for p in target.iterdir()] == [".git"]


def test_a_folder_of_someone_else_is_refused(tmp_path: Path) -> None:
    """A typo in the path may not cost a stranger's folder."""
    tool = _tool()
    target = tmp_path / "holiday_pictures"
    target.mkdir()
    (target / "beach.jpg").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        tool._clear(target)
    assert (target / "beach.jpg").exists()


def test_the_project_itself_is_refused(tmp_path: Path) -> None:
    """Exporting onto the source would delete the source."""
    tool = _tool()
    with pytest.raises(ValueError):
        tool._clear(ROOT)
    with pytest.raises(ValueError):
        tool._clear(ROOT / "modules")


def test_the_check_does_not_read_git_its_own_storage(tmp_path: Path) -> None:
    """B546: a packfile is compressed, so reading it as text is noise.

    The first push of v1.0.2 stopped on "TVX" found inside a zlib
    stream of `.git/objects/pack/*.pack` - three letters that occur by
    themselves in three megabytes of compressed bytes, while the
    literal name is in no revision and in no file. Nothing the export
    writes lives under `.git`, so nothing under `.git` is its business.
    """
    tool = _tool()
    target = tmp_path / "clone"
    (target / ".git" / "objects" / "pack").mkdir(parents=True)
    (target / ".git" / "objects" / "pack" / "p.pack").write_bytes(
        b"\x00\x01GZR\x02Groen Zwarte Zangers\x00")
    (target / "README.md").write_text("clean\n", encoding="utf-8")
    assert tool.leftovers(target) == 0


def test_the_check_still_reads_the_working_copy(tmp_path: Path) -> None:
    """The other half of the one above: skipping `.git` may not make
    the check blind to a real file beside it."""
    tool = _tool()
    target = tmp_path / "clone"
    (target / ".git").mkdir(parents=True)
    (target / "README.md").write_text("Rood Witte Zangers\n",
                                      encoding="utf-8")
    assert tool.leftovers(target) == 1


def _git(target: Path, *arguments: str) -> None:
    import subprocess

    subprocess.run(["git", "-C", str(target), *arguments], check=True,
                   capture_output=True)


def _repository(tmp_path: Path, content: str) -> Path:
    import shutil
    import subprocess

    if shutil.which("git") is None:  # pragma: no cover - machine bound
        pytest.skip("git is not installed")
    target = tmp_path / "repo"
    target.mkdir()
    try:
        _git(target, "init", "-q")
        _git(target, "config", "user.email", "t@example.com")
        _git(target, "config", "user.name", "Test")
    except subprocess.CalledProcessError:  # pragma: no cover
        pytest.skip("git cannot make a repository here")
    (target / "README.md").write_text(content, encoding="utf-8")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "first")
    return target


def test_a_name_in_the_history_is_found(tmp_path: Path) -> None:
    """B546: the question the packfile scan was pretending to ask.

    A name that was pushed once stays readable in the history after the
    working copy has been cleaned, and no export takes it back out.
    """
    tool = _tool()
    target = _repository(tmp_path, "Rood Witte Zangers\n")
    (target / "README.md").write_text("clean\n", encoding="utf-8")
    assert tool.leftovers(target) == 1  # clean folder, dirty history
    assert tool.history_leftovers(target) == 1


def test_a_clean_history_is_clean(tmp_path: Path) -> None:
    tool = _tool()
    target = _repository(tmp_path, "nothing to see\n")
    assert tool.history_leftovers(target) == 0
    assert tool.leftovers(target) == 0


def test_a_folder_without_git_has_no_history(tmp_path: Path) -> None:
    """No repository is not a failure: the export also writes into an
    empty folder, and then there is nothing to have leaked."""
    tool = _tool()
    target = tmp_path / "plain"
    target.mkdir()
    assert tool.history_leftovers(target) == 0


def test_a_word_that_merely_contains_a_name_is_not_a_hit(
        tmp_path: Path) -> None:
    """B546: the history check uses the same patterns as the walk.

    A first version searched plain substrings, case-insensitively, and
    then reported five files of the project itself - "Lied R" inside
    "springen", and the copyright line of LICENSE, which the walk has
    exempted on purpose. A check that cries wolf gets switched off by
    whoever has to read it. The capital in "Springen" is the point:
    with a plain escaped name instead of the pattern that is a hit
    whatever the case rule says. An underscore after the name is NOT
    in here on purpose - "Lied R_board" really is a hit, the same as
    in the walk, because ``_loose`` deliberately does not treat an
    underscore as part of a word (that is how "Lied A_2.mp4"
    was caught).
    """
    tool = _tool()
    target = _repository(
        tmp_path, "Springen en gesprongen, springerig, Springtijd\n")
    assert tool.history_leftovers(target) == 0


def test_the_exempt_files_stay_exempt_in_the_history(
        tmp_path: Path) -> None:
    """LICENSE carries the owner's name on purpose - in the working
    copy and therefore in every revision as well.

    The name here is the association and not the owner's own, because
    a hunted name written out in a file of this project is exactly
    what the export is there to prevent: the association is replaced
    on the way out, the owner's name would stand there.
    """
    tool = _tool()
    target = _repository(tmp_path, "clean\n")
    (target / "LICENSE").write_text("Copyright (c) Rood Witte Zangers\n",
                                    encoding="utf-8")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "licence")
    assert tool.history_leftovers(target) == 0


def test_a_name_in_a_commit_message_is_found(tmp_path: Path) -> None:
    """B546: a message is as public as a file, and no git grep over
    the trees reads one."""
    tool = _tool()
    target = _repository(tmp_path, "clean\n")
    (target / "notes.txt").write_text("nothing\n", encoding="utf-8")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "fix for Rood Witte Zangers")
    assert tool.history_leftovers(target) == 1


def test_a_deleted_file_keeps_its_name_in_the_history(
        tmp_path: Path) -> None:
    """B546: git grep matches content, not paths - and a file that was
    removed still stands in the history under the name it had."""
    tool = _tool()
    target = _repository(tmp_path, "clean\n")
    (target / "Lied J.txt").write_text("nothing\n", encoding="utf-8")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "add")
    _git(target, "rm", "-q", "Lied J.txt")
    _git(target, "commit", "-q", "-m", "remove")
    assert not (target / "Lied J.txt").exists()
    assert tool.leftovers(target) == 1  # clean folder, dirty history
    assert tool.history_leftovers(target) == 1


def test_a_name_in_gitignore_is_still_found(tmp_path: Path) -> None:
    """B546: only `.git` is skipped, not everything starting with a dot.

    `.gitignore` and `.gitattributes` are files this tool writes
    itself; widening the skip to every dotted name would stop reading
    them and nothing would notice.
    """
    tool = _tool()
    target = tmp_path / "clone"
    (target / ".git").mkdir(parents=True)
    (target / ".gitignore").write_text("Rood Witte Zangers\n",
                                       encoding="utf-8")
    assert tool.leftovers(target) == 1
