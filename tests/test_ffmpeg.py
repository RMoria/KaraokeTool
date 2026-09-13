"""Tests voor modules.ffmpeg (pure parsing, geen echte ffmpeg nodig)."""

from __future__ import annotations

import pytest

from modules.ffmpeg import FfmpegError, _detect_vbr, _parse_probe_output


def _probe_data(**overrides: object) -> dict:
    data = {
        "streams": [{
            "codec_type": "audio",
            "codec_name": "mp3",
            "sample_rate": "44100",
            "channels": 2,
            "bit_rate": "192000",
        }],
        "format": {
            "format_name": "mp3",
            "duration": "215.5",
            "bit_rate": "192000",
        },
    }
    data.update(overrides)
    return data


def test_parse_probe_output() -> None:
    properties = _parse_probe_output(_probe_data())
    assert properties.codec == "mp3"
    assert properties.sample_rate == 44100
    assert properties.channels == 2
    assert properties.bit_rate == 192000
    assert properties.duration == pytest.approx(215.5)
    assert properties.is_vbr is None


def test_parse_probe_output_without_stream_bitrate() -> None:
    data = _probe_data()
    del data["streams"][0]["bit_rate"]
    properties = _parse_probe_output(data)
    assert properties.bit_rate == 192000  # valt terug op format


def test_parse_probe_output_no_audio_stream() -> None:
    with pytest.raises(FfmpegError):
        _parse_probe_output({"streams": [], "format": {}})


def test_detect_vbr_constant_sizes_is_cbr() -> None:
    assert _detect_vbr([417] * 100) is False


def test_detect_vbr_varied_sizes_is_vbr() -> None:
    sizes = [417, 522, 313, 417, 626, 522, 313, 417] * 15
    assert _detect_vbr(sizes) is True


def test_detect_vbr_too_few_packets() -> None:
    assert _detect_vbr([417, 417]) is None
