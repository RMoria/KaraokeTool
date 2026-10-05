"""v1.0.29 (B678): the GitHub copy without the Roformer environment, its
models and the folder of things to throw away - and without walking the
skipped folders at all, which made a publication take so long."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "github_export.py"


def _tool():
    if not TOOL.exists():
        pytest.skip("github_export.py is not part of a published copy")
    spec = importlib.util.spec_from_file_location("export_v1029", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_the_program_goes_out(tmp_path: Path, monkeypatch) -> None:
    tool = _tool()
    for name in ("modules/a.py", "venv/Lib/x.py", "venv_separator/y.py",
                 "models/audio_separator/m.ckpt", "_to_delete/old.txt",
                 "helper/kt_work/jobs/j.json", "helper/install_helper.bat"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    monkeypatch.setattr(tool, "MAX_BYTES", 10)
    (tmp_path / "modules" / "big.dat").write_bytes(b"0" * 11)
    found = [p.relative_to(tmp_path).as_posix()
             for p in tool._sources(tmp_path)]
    assert found == ["helper/install_helper.bat", "modules/a.py"]


def test_skipped_folders_are_not_walked(tmp_path: Path, monkeypatch) -> None:
    import os

    tool = _tool()
    (tmp_path / "venv" / "deep").mkdir(parents=True)
    (tmp_path / "modules").mkdir()
    entered = []
    real = os.walk

    def walk(top, *args, **kwargs):
        for folder, folders, files in real(top, *args, **kwargs):
            entered.append(Path(folder).name)
            yield folder, folders, files

    monkeypatch.setattr(os, "walk", walk)
    tool._sources(tmp_path)
    assert "deep" not in entered and "venv" not in entered


def test_the_repository_ignores_them_too() -> None:
    tool = _tool()
    for name in ("venv_separator/", "models/", "_to_delete/"):
        assert name in tool.GITIGNORE_TEXT
    assert ".ckpt" in tool.BINARY_SUFFIXES
    assert tool.MAX_BYTES < 100 * 1024 * 1024
