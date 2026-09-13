"""Tests voor modules.analyse."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from modules.analysis import normalize_word, run_analysis
from modules.config import AnalysisSettings
from modules.whisper import CSV_DELIMITER, Segment, Word


def _segments() -> tuple[Segment, ...]:
    words_a = (
        Word(text="Kedeng", start=0.0, end=0.5, confidence=0.95),
        Word(text="kedeng,", start=0.6, end=1.1, confidence=0.90),
        Word(text="oe", start=1.2, end=1.5, confidence=0.40),
    )
    words_b = (
        Word(text="oe", start=2.0, end=2.3, confidence=0.85),
        Word(text="Koffie!", start=2.4, end=3.0, confidence=0.99),
    )
    return (
        Segment(index=0, text="Kedeng kedeng oe", start=0.0, end=1.5, words=words_a),
        Segment(index=1, text="oe Koffie!", start=2.0, end=3.0, words=words_b),
    )


def test_normalize_word() -> None:
    assert normalize_word("Koffie!") == "koffie"
    assert normalize_word(" Oe, ") == "oe"
    assert normalize_word("'s-nachts") == "s-nachts"
    assert normalize_word("...") == ""


def test_run_analysis_files_and_stats(tmp_path: Path) -> None:
    stats = run_analysis(_segments(), AnalysisSettings(), tmp_path)

    assert stats.segments == 2
    assert stats.words == 5
    assert stats.unique_words == 3  # kedeng, oe, koffie
    assert stats.short_words == 1   # alleen 'oe' (<= 4 letters)
    assert stats.lage_confidence == 1  # oe met 0.40
    assert stats.average_confidence == pytest.approx(0.818, abs=1e-3)

    for name in ("frequency.csv", "short_words.csv",
                 "low_confidence.csv", "statistics.json"):
        assert (tmp_path / name).exists(), name


def test_frequency_csv_sorted(tmp_path: Path) -> None:
    run_analysis(_segments(), AnalysisSettings(), tmp_path)
    with (tmp_path / "frequency.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=CSV_DELIMITER))
    assert rows[0] == ["word", "count"]
    # 'kedeng' en 'oe' komen beide 2x voor en staan bovenaan.
    assert {rows[1][0], rows[2][0]} == {"kedeng", "oe"}
    assert rows[3] == ["koffie", "1"]


def test_low_confidence_csv(tmp_path: Path) -> None:
    run_analysis(_segments(), AnalysisSettings(min_confidence=0.92), tmp_path)
    with (tmp_path / "low_confidence.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=CSV_DELIMITER))
    # Gesorteerd op oplopende confidence: oe (0.40), oe (0.85), kedeng (0.90)
    assert [row[0] for row in rows[1:]] == ["oe", "oe", "kedeng,"]


def test_run_analysis_empty(tmp_path: Path) -> None:
    stats = run_analysis((), AnalysisSettings(), tmp_path)
    assert stats.words == 0
    assert stats.average_confidence == 0.0
    stats_data = json.loads((tmp_path / "statistics.json").read_text(encoding="utf-8"))
    assert stats_data["segments"] == 0
