"""Tests for v0.77.0 features (B214, B215, B220)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from modules import pipeline
from modules.config import default_config
from modules.filesystem import (ProjectPaths, ProjectStore, ensure_directories,
                                output_base_from)
from modules.pipeline import AppContext


def _context(tmp_path: Path, title: str = "Song", output_base=None):
    paths = ProjectPaths(root=tmp_path, song=title, output_base=output_base)
    ensure_directories(paths)
    cfg = replace(default_config(),
                  song=replace(default_config().song, title=title))
    return AppContext(config=cfg, paths=paths,
                      store=ProjectStore(paths.project_file))


# -- B214: output folder ---------------------------------------------------

def test_output_base_from():
    assert output_base_from("") is None
    assert output_base_from("   ") is None
    assert output_base_from("D:/karaoke") == Path("D:/karaoke")


def test_projectpaths_output_base(tmp_path):
    base = tmp_path / "elders"
    paths = ProjectPaths(root=tmp_path, song="X", output_base=base)
    assert paths.output_root == base
    assert paths.output_dir == base / "X"
    # input and cache stay with the root
    assert paths.input_dir == tmp_path / "input" / "X"
    assert paths.cache_dir == tmp_path / "cache" / "X"


def test_output_writable(tmp_path):
    ok, _ = pipeline.output_writable(tmp_path / "nieuw")
    assert ok
    assert (tmp_path / "nieuw").exists()


def test_relocate_output_base_moves_and_rewrites(tmp_path):
    ctx = _context(tmp_path, "Lied")
    # create some content in the old output folder + a reference in
    # project.json
    (ctx.paths.output_dir).mkdir(parents=True, exist_ok=True)
    (ctx.paths.output_dir / "resultaat.txt").write_text("hoi",
                                                        encoding="utf-8")
    old_output = str(ctx.paths.output_dir)
    ctx.store.set_step("video", {"file": old_output + "/video.mp4"})

    target = tmp_path / "extern"
    ok, message, new = pipeline.relocate_output_base(ctx, target)
    assert ok, message
    # the file has been moved
    assert (target / "Lied" / "resultaat.txt").exists()
    assert not (tmp_path / "output" / "Lied").exists()
    # config updated
    assert new.config.advanced.output_dir == str(target)
    assert new.paths.output_dir == target / "Lied"
    # reference in project.json rewritten
    step = new.store.get_step("video")
    assert step["file"].startswith(str(target))


def test_relocate_back_to_default(tmp_path):
    base = tmp_path / "extern"
    ctx = _context(tmp_path, "Lied", output_base=base)
    ctx.paths.output_dir.mkdir(parents=True, exist_ok=True)
    ok, message, new = pipeline.relocate_output_base(
        ctx, tmp_path / "output")
    assert ok, message
    # back to the default -> no base of its own any more
    assert new.paths.output_base is None
    assert new.config.advanced.output_dir == ""


# -- B215: stems gone on a new original ------------------------------------

def test_remove_demucs_stems(tmp_path):
    ctx = _context(tmp_path, "Lied")
    ctx.paths.output_dir.mkdir(parents=True, exist_ok=True)
    for item_name in ("karaoke_demucs.mp3", "vocal_demucs.mp3", "video.mp4"):
        (ctx.paths.output_dir / item_name).write_text("x", encoding="utf-8")
    pipeline.remove_demucs_stems(ctx)
    assert not (ctx.paths.output_dir / "karaoke_demucs.mp3").exists()
    assert not (ctx.paths.output_dir / "vocal_demucs.mp3").exists()
    # other output stays put
    assert (ctx.paths.output_dir / "video.mp4").exists()


# -- B220: coupling editor aligns coupled pairs vertically -----------------

def test_coupling_layout_aligns_pairs():
    import os
    import pytest
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from modules.coupling_editor import CouplingCanvas
    # 3 words found; lyrics: A (na-na, uncoupled) B(->2)
    transcript = [("aa", 0.0, 0.5), ("bb", 0.5, 1.0), ("cc", 1.0, 1.5)]
    words = [
        {"index": 0, "text": "aa", "line": 0, "transcript_indices": [0],
         "found": "aa", "sim": 1.0, "pinned": False},
        {"index": 1, "text": "na-na", "line": 0, "transcript_indices": [],
         "found": None, "sim": 0.0, "pinned": False},
        {"index": 2, "text": "bb", "line": 0, "transcript_indices": [1],
         "found": "bb", "sim": 1.0, "pinned": False},
    ]
    canvas = CouplingCanvas(transcript, words, lambda _p: None)
    canvas._relayout()
    # coupled pair 'aa' sits straight above the other (same column)
    assert canvas._top_col[0] == canvas._bot_col[0]
    # 'bb' too, despite the uncoupled na-na in between on the bottom row
    assert canvas._top_col[1] == canvas._bot_col[2]
    # the na-na gets a column of its own (not equal to a top-column pair)
    assert canvas._bot_col[1] != canvas._bot_col[0]
