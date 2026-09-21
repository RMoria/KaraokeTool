"""Tests for modules.filesystem."""

from __future__ import annotations

from pathlib import Path

from modules.filesystem import (
    ProjectPaths,
    ProjectStore,
    clean_cache,
    ensure_directories,
    file_sha1,
    find_audio_file,
    remove_empty_tree,
)


def test_clean_cache_wipes_everything_incl_readonly(tmp_path: Path) -> None:
    """B184: empty the cache completely, nested folders and read-only
    files included."""
    import os
    import stat
    cache = tmp_path / "cache"
    (cache / "sub" / "diep").mkdir(parents=True)
    (cache / "sub" / "diep" / "a.bin").write_bytes(b"x")
    ro = cache / "sub" / "readonly.bin"
    ro.write_bytes(b"y")
    os.chmod(ro, stat.S_IREAD)                 # read-only file
    (cache / "los.txt").write_text("z", encoding="utf-8")
    clean_cache(cache)
    # The folder is still there, but completely empty.
    assert cache.exists()
    assert list(cache.iterdir()) == []


def test_timing_auto_file(tmp_path: Path) -> None:
    paths = ProjectPaths(root=tmp_path, song="Lied_O")
    assert paths.timing_auto_file == (paths.settings_dir / "timing_auto.json")


def test_prune_orphan_projects(tmp_path: Path) -> None:
    """B112: an input folder without an output folder (a deleted
    project) is cleaned up."""
    from modules.filesystem import prune_orphan_projects
    (tmp_path / "input" / "Blijft").mkdir(parents=True)
    (tmp_path / "output" / "Blijft").mkdir(parents=True)
    (tmp_path / "input" / "Weg").mkdir(parents=True)  # no output -> orphan
    (tmp_path / "input" / "los.wav").write_bytes(b"x")  # loose file stays
    pruned = prune_orphan_projects(tmp_path)
    assert pruned == ["Weg"]
    assert (tmp_path / "input" / "Blijft").exists()
    assert not (tmp_path / "input" / "Weg").exists()
    assert (tmp_path / "input" / "los.wav").exists()


def test_project_store_thread_safe_set_step(tmp_path: Path) -> None:
    """B90: parallel set_step calls neither get lost nor collide."""
    import threading

    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    store = ProjectStore(paths.project_file)

    def writer(index: int) -> None:
        for i in range(20):
            store.set_step(f"stap_{index}", {"i": i})

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Every writer has its own last value; nothing was lost.
    for n in range(6):
        step = store.get_step(f"stap_{n}")
        assert step is not None and step["i"] == 19
    # The file on disk is still valid JSON (it reloads).
    reloaded = ProjectStore(paths.project_file)
    assert reloaded.get_step("stap_0") is not None


def test_project_store_meta(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "project.json")
    assert store.get_meta("display_name") is None
    store.set_meta("display_name", "Lied O")
    # Load it again: the value is still there.
    again = ProjectStore(tmp_path / "project.json")
    assert again.get_meta("display_name") == "Lied O"
    assert again.get_meta("ontbreekt", "x") == "x"


def test_remove_empty_tree(tmp_path: Path) -> None:
    # An empty tree (only empty subfolders) goes completely.
    empty = tmp_path / "output"
    (empty / "settings").mkdir(parents=True)
    assert remove_empty_tree(empty) is True
    assert not empty.exists()
    # A tree with a file in it stays.
    filled = tmp_path / "input"
    filled.mkdir()
    (filled / "LEESMIJ.txt").write_text("hoi", encoding="utf-8")
    assert remove_empty_tree(filled) is False
    assert filled.exists()


def test_project_paths(tmp_path: Path) -> None:
    paths = ProjectPaths(root=tmp_path)
    assert paths.config_file == tmp_path / "config" / "config.json"
    assert paths.project_file == (tmp_path / "output" / "settings"
                                  / "project.json")
    assert paths.timing_file == (tmp_path / "output" / "settings"
                                 / "timing.json")


def test_ensure_directories(tmp_path: Path) -> None:
    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    for directory in (paths.config_dir, paths.input_dir, paths.cache_dir,
                      paths.output_dir, paths.logs_dir):
        assert directory.is_dir()


def test_find_audio_file_prefers_wav(tmp_path: Path) -> None:
    (tmp_path / "original.mp3").write_bytes(b"mp3")
    (tmp_path / "original.wav").write_bytes(b"wav")
    found = find_audio_file(tmp_path, "original")
    assert found is not None and found.suffix == ".wav"


def test_find_audio_file_missing(tmp_path: Path) -> None:
    assert find_audio_file(tmp_path, "original") is None


def test_file_sha1(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(b"carnaval")
    # Known SHA1 of b"carnaval".
    import hashlib
    assert file_sha1(path) == hashlib.sha1(b"carnaval").hexdigest()


def test_project_store_roundtrip(tmp_path: Path) -> None:
    store_path = tmp_path / "project.json"
    store = ProjectStore(store_path)
    store.set_step("source_original", {"sha1": "abc"})

    reloaded = ProjectStore(store_path)
    step = reloaded.get_step("source_original")
    assert step is not None
    assert step["sha1"] == "abc"
    assert "updated" in step


def test_project_store_clear(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "project.json")
    store.set_step("x", {"a": 1})
    store.clear_step("x")
    assert store.get_step("x") is None


def test_project_store_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    path.write_text("{kapot", encoding="utf-8")
    store = ProjectStore(path)
    assert store.get_step("iets") is None


def test_clean_cache_removes_everything(tmp_path: Path) -> None:
    (tmp_path / "project.json").write_text("{}", encoding="utf-8")
    (tmp_path / "transcriptie.json").write_text("[]", encoding="utf-8")
    (tmp_path / "original.wav").write_bytes(b"wav")

    removed = clean_cache(tmp_path)

    assert removed == 3
    assert list(tmp_path.iterdir()) == []


def test_clean_cache_missing_dir(tmp_path: Path) -> None:
    assert clean_cache(tmp_path / "bestaat_niet") == 0


def test_safe_name() -> None:
    from modules.filesystem import safe_name

    assert safe_name("Per Spoor") == "Per_Spoor"
    assert safe_name('Kedeng: "live"?/\\') == "Kedeng___live____"
    assert "/" not in safe_name("a/b\\c") and "\\" not in safe_name("a/b\\c")
    assert len(safe_name("x" * 100)) == 60


def test_project_paths_with_song(tmp_path: Path) -> None:
    paths = ProjectPaths(root=tmp_path, song="Per_Spoor")
    assert paths.input_dir == tmp_path / "input" / "Per_Spoor"
    assert paths.output_dir == tmp_path / "output" / "Per_Spoor"
    assert paths.input_root == tmp_path / "input"
    assert paths.cache_dir == tmp_path / "cache" / "Per_Spoor"  # per project
    assert ProjectPaths(root=tmp_path).cache_dir == tmp_path / "cache"


def test_project_store_rewrite_prefix(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "project.json")
    store.set_step("source_karaoke", {
        "path": str(tmp_path / "input" / "karaoke.mp3"),
        "geneste": {"wav": str(tmp_path / "input" / "karaoke.wav")},
        "list": [str(tmp_path / "input" / "x.txt"), 42],
        "sha1": "geen pad"})
    count = store.rewrite_prefix(tmp_path / "input",
                                 tmp_path / "input" / "Per_Spoor")
    assert count == 3
    reloaded = ProjectStore(tmp_path / "project.json")
    step = reloaded.get_step("source_karaoke")
    assert step["path"] == str(tmp_path / "input" / "Per_Spoor"
                              / "karaoke.mp3")
    assert step["geneste"]["wav"].endswith("karaoke.wav")
    assert "Per_Spoor" in step["geneste"]["wav"]
    assert step["sha1"] == "geen pad"


def test_clean_logs_keeps_newest_five(tmp_path: Path) -> None:
    from modules.filesystem import clean_logs

    logs = tmp_path / "logs"
    logs.mkdir()
    for day in range(1, 9):  # 8 days of logs
        (logs / f"2026-07-{day:02d}.log").write_text("x", encoding="utf-8")
    removed = clean_logs(logs, keep=5)
    assert removed == 3
    remaining = sorted(f.name for f in logs.glob("*.log"))
    # The 5 newest stay (04 through 08).
    assert remaining == ["2026-07-04.log", "2026-07-05.log",
                         "2026-07-06.log", "2026-07-07.log",
                         "2026-07-08.log"]


def test_clean_logs_fewer_than_keep(tmp_path: Path) -> None:
    from modules.filesystem import clean_logs

    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "2026-07-01.log").write_text("x", encoding="utf-8")
    assert clean_logs(logs, keep=5) == 0
    assert clean_logs(tmp_path / "weg", keep=5) == 0  # folder is absent
