"""Tests for modules.export."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from modules import ffmpeg
from modules.audio import save_wav
from modules.export import (
    ExportError,
    export_result,
    nearest_cbr_bitrate,
    vbr_quality_for,
)
from modules.ffmpeg import AudioProperties


def test_nearest_cbr_bitrate() -> None:
    assert nearest_cbr_bitrate(320_000) == 320_000
    assert nearest_cbr_bitrate(267_808) == 256_000
    assert nearest_cbr_bitrate(96_500) == 96_000
    assert nearest_cbr_bitrate(None) == 192_000


def test_vbr_quality_for() -> None:
    assert vbr_quality_for(245_000) == 0
    assert vbr_quality_for(267_808) == 0
    assert vbr_quality_for(190_000) == 2
    assert vbr_quality_for(120_000) == 6
    assert vbr_quality_for(None) == 2


def _properties(**overrides: object) -> AudioProperties:
    values: dict = {"codec": "mp3", "sample_rate": 48_000, "channels": 2,
                    "bit_rate": 267_808, "duration": 3.0,
                    "container": "mp3", "is_vbr": True}
    values.update(overrides)
    return AudioProperties(**values)


def _make_wav(path: Path, sample_rate: int = 48_000) -> None:
    time = np.arange(2 * sample_rate) / sample_rate
    tone = (0.4 * np.sin(2 * np.pi * 330 * time)).astype(np.float32)
    save_wav(path, np.stack([tone, tone], axis=1), sample_rate)


def test_export_missing_input(tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        export_result(tmp_path / "weg.wav", _properties(), ".mp3", tmp_path)


def test_export_unknown_format(tmp_path: Path) -> None:
    # .flac/.m4a/.ogg/.aac have been supported INPUT formats since B280
    # (they export as mp3, just like mp3 itself) - a genuinely unknown
    # extension must still fail.
    source = tmp_path / "bewerkt.wav"
    _make_wav(source)
    with pytest.raises(ExportError):
        export_result(source, _properties(), ".xyz", tmp_path)


def test_export_m4a_source_yields_mp3(tmp_path: Path) -> None:
    """B280: an m4a/flac/ogg/aac source exports (just like mp3) to mp3;
    there is no separate "m4a output format" - the output stays mp3/wav."""
    source = tmp_path / "bewerkt.wav"
    _make_wav(source)
    for ext in (".m4a", ".flac", ".ogg", ".aac"):
        result = export_result(source, _properties(is_vbr=False), ext,
                               tmp_path / f"uit{ext}")
        assert result.name == "karaoke_edit.mp3"


def test_export_wav_copies(tmp_path: Path) -> None:
    source = tmp_path / "bewerkt.wav"
    _make_wav(source)
    result = export_result(source, _properties(codec="pcm_s16le"),
                           ".wav", tmp_path / "uit")
    assert result.name == "karaoke_edit.wav"
    assert result.read_bytes() == source.read_bytes()


def test_export_mp3_matches_source_properties(tmp_path: Path) -> None:
    """Integration test: mp3 export preserves sample rate and channels."""
    if not ffmpeg.is_available():
        pytest.skip("ffmpeg not available")
    source = tmp_path / "bewerkt.wav"
    _make_wav(source, sample_rate=48_000)
    result = export_result(source, _properties(), ".mp3", tmp_path / "uit")
    assert result.name == "karaoke_edit.mp3"
    probed = ffmpeg.probe(result)
    assert probed.sample_rate == 48_000
    assert probed.channels == 2
    assert probed.codec == "mp3"
