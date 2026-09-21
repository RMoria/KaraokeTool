"""Tests for v0.78.0 features (B221, B224, B225, B226)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from modules import filesystem, pipeline, rhythm
from modules.config import default_config
from modules.filesystem import ProjectPaths, ProjectStore, ensure_directories
from modules.pipeline import AppContext, PipelineError


def _context(tmp_path: Path, title: str = "Song"):
    paths = ProjectPaths(root=tmp_path, song=title)
    ensure_directories(paths)
    cfg = replace(default_config(),
                  song=replace(default_config().song, title=title))
    return AppContext(config=cfg, paths=paths,
                      store=ProjectStore(paths.project_file))


# -- B221: data root -------------------------------------------------------

def test_is_writable(tmp_path):
    assert filesystem.is_writable(tmp_path)


def test_resolve_data_root_env(tmp_path, monkeypatch):
    target = tmp_path / "elders"
    monkeypatch.setenv("KARAOKETOOL_DATA", str(target))
    assert filesystem.resolve_data_root(tmp_path / "app") == target


def test_resolve_data_root_writable(tmp_path, monkeypatch):
    monkeypatch.delenv("KARAOKETOOL_DATA", raising=False)
    app = tmp_path / "app"
    app.mkdir()
    assert filesystem.resolve_data_root(app) == app


def test_resolve_data_root_readonly_falls_back(tmp_path, monkeypatch):
    monkeypatch.delenv("KARAOKETOOL_DATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    # simulating a path that does not exist and cannot be created via
    # monkeypatch is awkward; use a file as the 'folder' so that
    # mkdir/among fails.
    fake = tmp_path / "readonly_file"
    fake.write_text("x", encoding="utf-8")
    # fake is a file -> not writable
    root = filesystem.resolve_data_root(fake)
    assert root == (tmp_path / "LocalAppData" / "KaraokeTool")


# -- B224/B225: vocal energy -----------------------------------------------

def _write_wav(path, signal, sr=22050):
    import soundfile as sf
    sf.write(str(path), signal.astype(np.float32), sr)


def test_active_windows_and_end(tmp_path):
    pytest.importorskip("librosa")
    sr = 22050
    tone = 0.5 * np.sin(2 * np.pi * 220 * np.arange(2 * sr) / sr)
    silent = np.zeros(int(1.5 * sr))
    # 0-2 active, 2-3.5 empty, 3.5-5.5 active
    signal = np.concatenate([tone, silent, tone])
    wav = tmp_path / "v.wav"
    _write_wav(wav, signal, sr)
    usable_windows = rhythm.active_windows(wav)
    assert len(usable_windows) >= 2
    # first window ~0-2s
    assert usable_windows[0][0] < 0.5 and usable_windows[0][1] < 2.6
    # active_end within [0, 3.5] lies around the end of the first tone (~2s)
    ae = rhythm.active_end(wav, 0.0, 3.4)
    assert ae is not None and 1.7 <= ae <= 2.4


def test_count_repetitions(tmp_path):
    pytest.importorskip("librosa")
    sr = 22050
    signal = np.zeros(4 * sr, dtype=np.float32)
    for k in range(4):
        b = int((0.2 + k) * sr)
        pulse = 0.6 * np.sin(2 * np.pi * 300 * np.arange(int(0.3 * sr)) / sr)
        signal[b:b + pulse.size] += pulse
    wav = tmp_path / "chant.wav"
    _write_wav(wav, signal, sr)
    assert rhythm.count_repetitions(wav, 0.0, 4.0) >= 3


# -- B226: render sources --------------------------------------------------

def test_render_audio_picks_stems(tmp_path):
    ctx = _context(tmp_path)
    ctx.paths.output_dir.mkdir(parents=True, exist_ok=True)
    (ctx.paths.output_dir / "karaoke_demucs.mp3").write_text("x")
    (ctx.paths.output_dir / "vocal_demucs.mp3").write_text("x")
    assert pipeline._render_audio(ctx, "demucs").name == "karaoke_demucs.mp3"
    assert pipeline._render_audio(ctx, "vocals").name == "vocal_demucs.mp3"


def test_render_audio_missing_gives_an_error(tmp_path):
    ctx = _context(tmp_path)
    with pytest.raises(PipelineError):
        pipeline._render_audio(ctx, "demucs")
    with pytest.raises(PipelineError):
        pipeline._render_audio(ctx, "original")


def test_render_timed_lines_original_without_data(tmp_path):
    ctx = _context(tmp_path)
    with pytest.raises(PipelineError):
        pipeline._render_timed_lines(ctx, "original")


def test_render_source_constants():
    assert pipeline.TEXT_SOURCES == ("karaoke", "original")
    assert set(pipeline.AUDIO_SOURCES) == {"karaoke", "original",
                                           "demucs", "vocals"}
