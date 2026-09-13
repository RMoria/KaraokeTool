"""Analysis of the Whisper results.

Creates, on the basis of the transcription: word frequencies
(``frequentie.csv``), short words (``korte_woorden.csv``), a
confidence report (``lage_confidence.csv``) and general statistics
(``statistieken.json``). Works purely on the dataclasses from
``whisper.py`` and is therefore testable on its own.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import AnalysisSettings
from .whisper import CSV_DELIMITER, Segment, Word
from .translations import t

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisStats:
    """Summarising statistics of an analysis."""

    segments: int
    words: int
    unique_words: int
    short_words: int
    lage_confidence: int
    average_confidence: float
    total_word_duration_s: float


def normalize_word(text: str) -> str:
    """Normalise a word for comparison: lower case, without
    punctuation (accents and apostrophe are preserved)."""
    cleaned = "".join(ch for ch in text.strip().lower()
                      if ch.isalnum() or ch in "'’-")
    return cleaned.strip("'’-")


def run_analysis(
    segments: tuple[Segment, ...],
    settings: AnalysisSettings,
    output_dir: Path,
) -> AnalysisStats:
    """Analyse the transcription and write the report files.

    Args:
        segments: The Whisper segments of the original.
        settings: Analysis settings (confidence limit, word length).
        output_dir: Folder in which the reports are placed.

    Returns:
        Summarising statistics (also stored as
        ``statistieken.json``).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    words = [word for segment in segments for word in segment.words]

    frequencies = _word_frequencies(words)
    short_words = Counter({word: count for word, count in frequencies.items()
                           if len(word) <= settings.short_word_max_letters})
    low_confidence = sorted(
        (word for word in words if word.confidence < settings.min_confidence),
        key=lambda word: word.confidence,
    )

    _write_frequency_csv(frequencies, output_dir / "frequency.csv")
    _write_frequency_csv(short_words, output_dir / "short_words.csv")
    _write_low_confidence_csv(low_confidence, output_dir / "low_confidence.csv")

    stats = AnalysisStats(
        segments=len(segments),
        words=len(words),
        unique_words=len(frequencies),
        short_words=len(short_words),
        lage_confidence=len(low_confidence),
        average_confidence=round(
            sum(word.confidence for word in words) / len(words), 4
        ) if words else 0.0,
        total_word_duration_s=round(
            sum(word.end - word.start for word in words), 2
        ),
    )
    stats_path = output_dir / "statistics.json"
    stats_path.write_text(
        json.dumps(asdict(stats), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info(t("log_analysis_done"), stats)
    return stats


def _word_frequencies(words: list[Word]) -> Counter[str]:
    """Count normalised words (empty results are skipped)."""
    counter: Counter[str] = Counter()
    for word in words:
        normalized = normalize_word(word.text)
        if normalized:
            counter[normalized] += 1
    return counter


def _write_frequency_csv(frequencies: Counter[str], path: Path) -> None:
    """Write word/count pairs, sorted by descending frequency."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=CSV_DELIMITER)
        writer.writerow(["word", "count"])
        for word, count in frequencies.most_common():
            writer.writerow([word, count])
    logger.debug(t("log_written_words"), path.name, len(frequencies))


def _write_low_confidence_csv(words: list[Word], path: Path) -> None:
    """Write words with low confidence, lowest first."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=CSV_DELIMITER)
        writer.writerow(["word", "start", "end", "confidence"])
        for word in words:
            writer.writerow([word.text, f"{word.start:.3f}",
                             f"{word.end:.3f}", f"{word.confidence:.4f}"])
    logger.debug(t("log_written_words"), path.name, len(words))
