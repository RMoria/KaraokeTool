"""Tests voor modules.whisper (serialisatie en uitvoer, zonder model)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from modules.whisper import (
    CSV_DELIMITER,
    Segment,
    Word,
    WhisperError,
    load_segments,
    save_segments,
    segments_from_dicts,
    segments_to_dicts,
    write_outputs,
)


def _example_segments() -> tuple[Segment, ...]:
    return (
        Segment(index=0, text="Kedeng kedeng", start=1.0, end=2.5, words=(
            Word(text="Kedeng", start=1.0, end=1.7, confidence=0.95),
            Word(text="kedeng", start=1.8, end=2.5, confidence=0.91),
        )),
        Segment(index=1, text="oe oe", start=3.0, end=4.0, words=(
            Word(text="oe", start=3.0, end=3.4, confidence=0.42),
            Word(text="oe", start=3.6, end=4.0, confidence=0.88),
        )),
    )


def test_serialisation_roundtrip() -> None:
    segments = _example_segments()
    assert segments_from_dicts(segments_to_dicts(segments)) == segments


def test_save_and_load_segments(tmp_path: Path) -> None:
    segments = _example_segments()
    cache = tmp_path / "transcriptie.json"
    save_segments(segments, cache)
    assert load_segments(cache) == segments


def test_load_segments_corrupt(tmp_path: Path) -> None:
    cache = tmp_path / "transcriptie.json"
    cache.write_text("{kapot", encoding="utf-8")
    with pytest.raises(WhisperError):
        load_segments(cache)


def test_write_outputs_creates_all_files(tmp_path: Path) -> None:
    write_outputs(_example_segments(), {"model": "large-v3"}, tmp_path)
    for name in ("transcript.txt", "words.csv", "woorden.json",
                 "segmenten.json", "run_info.json"):
        assert (tmp_path / name).exists(), name


def test_transcript_content(tmp_path: Path) -> None:
    write_outputs(_example_segments(), {}, tmp_path)
    lines = (tmp_path / "transcript.txt").read_text(encoding="utf-8").splitlines()
    assert lines == ["Kedeng kedeng", "oe oe"]


def test_words_csv_content(tmp_path: Path) -> None:
    write_outputs(_example_segments(), {}, tmp_path)
    with (tmp_path / "words.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=CSV_DELIMITER))
    assert rows[0] == ["word", "start", "end", "confidence", "segment"]
    assert len(rows) == 5  # header + 4 woorden
    assert rows[1][0] == "Kedeng"
    assert rows[3][4] == "1"  # segmentindex van 'oe'


def test_words_json_content(tmp_path: Path) -> None:
    write_outputs(_example_segments(), {}, tmp_path)
    words = json.loads((tmp_path / "woorden.json").read_text(encoding="utf-8"))
    assert len(words) == 4
    assert words[2] == {"text": "oe", "start": 3.0, "end": 3.4,
                        "confidence": 0.42, "segment": 1}


def test_model_cached(tmp_path, monkeypatch) -> None:
    from modules.config import WhisperSettings
    from modules.whisper import model_cached

    monkeypatch.setenv("HF_HOME", str(tmp_path))
    settings = WhisperSettings(model="large-v3")
    assert model_cached(settings) is False
    hub = tmp_path / "hub" / "models--Systran--faster-whisper-large-v3"
    hub.mkdir(parents=True)
    assert model_cached(settings) is True


def test_collect_segments_cancels() -> None:
    """B86: _collect_segments stopt met CancelledError zodra cancelled()."""
    import pytest
    from modules.whisper import CancelledError, _collect_segments

    class _Raw:
        def __init__(self, end: float) -> None:
            self.start, self.end, self.text, self.words = 0.0, end, "a", ()

    with pytest.raises(CancelledError):
        _collect_segments(iter([_Raw(1.0), _Raw(2.0)]), 10.0, None,
                          lambda: True)
