"""The one-off migration of the two text files (B555).

This runs over the user's own projects and renames files there, so it
is tested the way the export tool is: every case that could cost him
something, made on disk and checked afterwards. Twenty-two projects
with a hand-made timing in each of them is not a place for a script
that was only read.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "migrate_texts.py"


def _tool():
    if not TOOL.exists():  # pragma: no cover - published copies keep it
        pytest.skip("migrate_texts.py is not here")
    spec = importlib.util.spec_from_file_location("migrate_texts", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _installation(tmp_path: Path, songs=("Song_A", "Song_B")) -> Path:
    """An installation with a couple of projects in the old shape."""
    root = tmp_path / "KaraokeTool"
    for song in songs:
        folder = root / "input" / song
        folder.mkdir(parents=True)
        (folder / "songtekst.txt").write_text(f"lyrics of {song}\n",
                                              encoding="utf-8")
        (folder / "karaoketekst.txt").write_text(f"parody of {song}\n",
                                                 encoding="utf-8")
        settings = root / "output" / song / "settings"
        settings.mkdir(parents=True)
        (settings / "project.json").write_text(json.dumps({"steps": {
            "source_lyrics": {
                "path": str(folder / "songtekst.txt"), "sha1": "aaa"},
            "source_karaoke_text": {
                "path": str(folder / "karaoketekst.txt"), "sha1": "bbb"},
            "source_original": {
                "path": str(folder / "original.mp3"), "sha1": "ccc"},
        }}), encoding="utf-8")
    return root


def test_a_dry_run_writes_nothing(tmp_path: Path, capsys) -> None:
    """The default. A migration you cannot look at first is a gamble."""
    tool = _tool()
    root = _installation(tmp_path)
    assert tool.main([str(root)]) == 0
    printed = capsys.readouterr().out
    assert "dry run" in printed
    assert "songtekst.txt -> lyrics.txt" in printed
    for song in ("Song_A", "Song_B"):
        assert (root / "input" / song / "songtekst.txt").exists()
        assert not (root / "input" / song / "lyrics.txt").exists()


def test_apply_renames_and_keeps_a_copy(tmp_path: Path) -> None:
    tool = _tool()
    root = _installation(tmp_path)
    assert tool.main([str(root), "--apply"]) == 0
    for song in ("Song_A", "Song_B"):
        folder = root / "input" / song
        assert not (folder / "songtekst.txt").exists()
        assert not (folder / "karaoketekst.txt").exists()
        assert (folder / "lyrics.txt").read_text(
            encoding="utf-8") == f"lyrics of {song}\n"
        assert (folder / "karaoke_text.txt").read_text(
            encoding="utf-8") == f"parody of {song}\n"
        # Nothing is deleted, ever.
        assert (folder / ("songtekst.txt" + tool.BACKUP_SUFFIX)).exists()
        assert (folder / ("karaoketekst.txt" + tool.BACKUP_SUFFIX)).exists()


def test_the_stored_paths_follow(tmp_path: Path) -> None:
    """A path that names a file which no longer exists is a lie waiting
    for the next reader. The sha1 beside it is untouched, because that
    is what the derivation chain actually compares."""
    tool = _tool()
    root = _installation(tmp_path)
    tool.main([str(root), "--apply"])
    store = json.loads((root / "output" / "Song_A" / "settings"
                        / "project.json").read_text(encoding="utf-8"))
    steps = store["steps"]
    assert steps["source_lyrics"]["path"].endswith("lyrics.txt")
    assert steps["source_karaoke_text"]["path"].endswith("karaoke_text.txt")
    assert steps["source_lyrics"]["sha1"] == "aaa"
    assert steps["source_original"]["path"].endswith("original.mp3")


def test_running_it_twice_is_harmless(tmp_path: Path) -> None:
    tool = _tool()
    root = _installation(tmp_path)
    assert tool.main([str(root), "--apply"]) == 0
    before = (root / "input" / "Song_A" / "lyrics.txt").read_text(
        encoding="utf-8")
    assert tool.main([str(root), "--apply"]) == 0
    assert (root / "input" / "Song_A" / "lyrics.txt").read_text(
        encoding="utf-8") == before


def test_both_names_present_is_left_alone(tmp_path: Path, capsys) -> None:
    """Two files, one of which would be overwritten: hands off.

    This is the only case where the user can lose something, so the
    script does nothing at all and says so instead of guessing which of
    the two he meant.
    """
    tool = _tool()
    root = _installation(tmp_path, songs=("Song_A",))
    folder = root / "input" / "Song_A"
    (folder / "lyrics.txt").write_text("a newer text\n", encoding="utf-8")
    assert tool.main([str(root), "--apply"]) == 1     # verify complains
    assert (folder / "songtekst.txt").exists()
    assert (folder / "lyrics.txt").read_text(
        encoding="utf-8") == "a newer text\n"
    assert "left alone" in capsys.readouterr().out


def test_a_project_json_of_another_shape_does_not_stop_it(
        tmp_path: Path, capsys) -> None:
    """The rename happens first, so a crash here is the worst place.

    ``ProjectStore`` tolerates a file whose ``steps`` are not a mapping,
    and an earlier version of this script did not: it raised halfway,
    after every file had been renamed, so the verification never ran and
    the user was left with a traceback where the check should have been.
    """
    tool = _tool()
    root = _installation(tmp_path, songs=("Song_A",))
    store = root / "output" / "Song_A" / "settings" / "project.json"
    store.write_text(json.dumps({"steps": ["not", "a", "mapping"]}),
                     encoding="utf-8")
    assert tool.main([str(root), "--apply"]) == 0
    assert (root / "input" / "Song_A" / "lyrics.txt").exists()
    assert "of the expected shape" in capsys.readouterr().out


def test_a_path_that_merely_ends_in_the_old_name_is_left(
        tmp_path: Path) -> None:
    """``my_songtekst.txt`` is somebody else's file."""
    tool = _tool()
    root = _installation(tmp_path, songs=("Song_A",))
    store = root / "output" / "Song_A" / "settings" / "project.json"
    data = json.loads(store.read_text(encoding="utf-8"))
    data["steps"]["source_logo"] = {"path": "C:\\x\\my_songtekst.txt"}
    store.write_text(json.dumps(data), encoding="utf-8")
    tool.main([str(root), "--apply"])
    after = json.loads(store.read_text(encoding="utf-8"))
    assert after["steps"]["source_logo"]["path"].endswith("my_songtekst.txt")
    assert after["steps"]["source_lyrics"]["path"].endswith("lyrics.txt")


def test_the_users_own_file_name_is_not_a_complaint(tmp_path: Path) -> None:
    """``input_names`` keeps the name of the file the user PICKED.

    A text he called "Kedeng songtekst.txt" is his business. Searching
    the whole project.json for the old words made the verification
    complain about a migration that was perfectly fine, and a check that
    cries wolf gets ignored on the one occasion it is right.
    """
    tool = _tool()
    root = _installation(tmp_path, songs=("Song_A",))
    store = root / "output" / "Song_A" / "settings" / "project.json"
    data = json.loads(store.read_text(encoding="utf-8"))
    data["input_names"] = {"lyrics": {"name": "Kedeng songtekst.txt",
                                      "dir": "C:\\Temp"}}
    store.write_text(json.dumps(data), encoding="utf-8")
    assert tool.main([str(root), "--apply"]) == 0


def test_a_folder_that_is_not_an_installation_is_refused(
        tmp_path: Path, capsys) -> None:
    tool = _tool()
    target = tmp_path / "holiday_pictures"
    target.mkdir()
    assert tool.main([str(target)]) == 1
    assert "is that the installation" in capsys.readouterr().out


def test_a_project_without_the_texts_is_no_problem(tmp_path: Path) -> None:
    tool = _tool()
    root = _installation(tmp_path, songs=("Song_A",))
    empty = root / "input" / "Song_Empty"
    empty.mkdir()
    assert tool.main([str(root), "--apply"]) == 0
    assert list(empty.iterdir()) == []


def test_the_new_names_come_from_the_program(tmp_path: Path) -> None:
    """Not typed out here: the mapping reads the constants, so this
    script cannot drift away from what the app opens."""
    tool = _tool()
    from modules import karaoke_text, song_text

    assert tool.RENAMES["songtekst.txt"] == song_text.LYRICS_FILENAME
    assert tool.RENAMES["karaoketekst.txt"] == karaoke_text.FILENAME


def test_an_unmigrated_project_refuses_to_run(tmp_path: Path) -> None:
    """B555: the gate that makes the hard cut safe.

    Without it, opening a project that has not been migrated is the
    expensive mistake: from `sync_input_changes` the old name looks
    like a DELETED source, and its answer to a deleted source is to
    throw away everything derived from it - the word coupling,
    `timing.json` and `timing_auto.json`. The rescue of B407/B429
    cannot step in, because that needs the karaoke text and that is
    missing under its new name too. One click on any step button, and
    no backup exists unless the migration has run.
    """
    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    context = pipeline.AppContext(config=default_config(), paths=paths,
                                  store=ProjectStore(paths.project_file))
    (paths.input_dir / "songtekst.txt").write_text("x", encoding="utf-8")

    assert pipeline.unmigrated_texts(context) == ("songtekst.txt",)
    with pytest.raises(pipeline.PipelineError, match="songtekst.txt"):
        pipeline.sync_input_changes(context)

    # Migrated: the gate opens and nothing is left to complain about.
    (paths.input_dir / "songtekst.txt").rename(
        paths.input_dir / "lyrics.txt")
    assert pipeline.unmigrated_texts(context) == ()
    pipeline.sync_input_changes(context)


def test_both_names_present_is_not_unmigrated(tmp_path: Path) -> None:
    """The migration leaves that case alone, so the app must not stop
    on it: it simply reads the new file."""
    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    context = pipeline.AppContext(config=default_config(), paths=paths,
                                  store=ProjectStore(paths.project_file))
    (paths.input_dir / "songtekst.txt").write_text("old", encoding="utf-8")
    (paths.input_dir / "lyrics.txt").write_text("new", encoding="utf-8")

    assert pipeline.unmigrated_texts(context) == ()
    pipeline.sync_input_changes(context)


def test_a_windows_path_is_read_on_any_platform(tmp_path: Path) -> None:
    """The paths in project.json are Windows paths.

    ``PurePath`` follows the platform it runs on, so on anything but
    Windows the whole backslashed string came back as the "name" and
    nothing matched. The dry run over the real installation is what
    showed it - 44 files to rename and 0 paths to correct, where the
    answer is 44 and 44 - and this test is so that it cannot come back.
    """
    tool = _tool()
    assert tool._file_name("C:/Muziek\\KT\\input\\A\\songtekst.txt") \
        == "songtekst.txt"
    assert tool._file_name("/home/x/input/A/songtekst.txt") \
        == "songtekst.txt"

    root = _installation(tmp_path, songs=("Song_A",))
    store = root / "output" / "Song_A" / "settings" / "project.json"
    data = json.loads(store.read_text(encoding="utf-8"))
    data["steps"]["source_lyrics"]["path"] = \
        "C:/Muziek/KaraokeTool\\input\\Song_A\\songtekst.txt"
    store.write_text(json.dumps(data), encoding="utf-8")

    assert tool.main([str(root), "--apply"]) == 0
    after = json.loads(store.read_text(encoding="utf-8"))
    assert after["steps"]["source_lyrics"]["path"] == \
        "C:/Muziek/KaraokeTool\\input\\Song_A\\lyrics.txt"
