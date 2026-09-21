"""Tests for modules.song_text (alignment of the official lyrics)."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.cluster import build_clusters, phonetic_key
from modules.config import ClusterSettings
from modules.song_text import (
    align_lyrics,
    extra_intervals,
    load_lyrics,
    relabel_clusters,
    write_report,
)
from modules.whisper import Segment, Word


def _word(text: str, start: float, duration: float = 0.4) -> Word:
    return Word(text=text, start=start, end=start + duration, confidence=0.9)


def _segments() -> tuple[Segment, ...]:
    """Whisper heard: GEDENGEDENG (=kedeng kedeng), 'de trein' (=kedeng
    kedeng), and the ordinary line; the second kedeng line was missed."""
    words0 = (_word("GEDENGEDENG", 1.0, 0.9),)
    words1 = (_word("de", 3.0, 0.3), _word("trein", 3.35, 0.45))
    words2 = (_word("kilometers", 20.0, 0.8), _word("spoor", 20.9, 0.5))
    make = lambda i, ws: Segment(  # noqa: E731
        index=i, text=" ".join(w.text for w in ws),
        start=ws[0].start, end=ws[-1].end, words=ws)
    return tuple(make(i, ws) for i, ws in enumerate((words0, words1, words2)))


def _lyrics(tmp_path: Path) -> Path:
    """Eight kedengs; the transcription can account for only six of them."""
    path = tmp_path / "songtekst.txt"
    path.write_text(
        "Kedeng Kedeng, Kedeng Kedeng\n"
        "Kedeng Kedeng\n"
        "Kedeng Kedeng\n"
        "kilometers spoor\n",
        encoding="utf-8")
    return path


def test_load_lyrics(tmp_path: Path) -> None:
    lyrics = load_lyrics(_lyrics(tmp_path))
    assert len(lyrics) == 10
    assert lyrics[0].text == "Kedeng"
    assert lyrics[1].line == 0 and lyrics[8].line == 3


def test_align_matches_gedengedeng_and_de_trein(tmp_path: Path) -> None:
    aligned = align_lyrics(load_lyrics(_lyrics(tmp_path)), _segments())
    # First two kedengs -> GEDENGEDENG (2:1 coupling).
    assert aligned[0].matched_text == "GEDENGEDENG"
    assert aligned[1].matched_text == "GEDENGEDENG"
    assert aligned[0].start == pytest.approx(1.0)
    # 'kilometers spoor' simply coupled as an anchor.
    assert aligned[8].matched_text == "kilometers"


def test_extra_intervals_finds_new_and_estimates_gap(tmp_path: Path) -> None:
    aligned = align_lyrics(load_lyrics(_lyrics(tmp_path)), _segments())
    target_keys = {phonetic_key("kedeng")}
    known = [(1.0, 1.9)]  # the GEDENGEDENG occurrences are already known
    extras = extra_intervals(aligned, target_keys, known)
    labels = [label for _, _, label in extras]
    # 'de trein' is a newly found kedeng interval...
    assert any(3.0 <= start <= 3.4 for start, _, _ in extras)
    # ...and the missed kedeng line is estimated between the anchors.
    assert any("geschat" in label for label in labels)
    # Known intervals are not reported again.
    assert not any(abs(start - 1.0) < 0.05 for start, _, _ in extras)


def test_relabel_clusters_uses_official_text(tmp_path: Path) -> None:
    segments = _segments()
    aligned = align_lyrics(load_lyrics(_lyrics(tmp_path)), segments)
    clusters = build_clusters(segments, ClusterSettings())
    relabeled = relabel_clusters(clusters, aligned)
    gedeng = next(c for c in relabeled
                  if any("GEDENGEDENG" in m for m, _ in c.members))
    assert gedeng.label == "KEDENG"  # the official lyrics lead


def test_write_report(tmp_path: Path) -> None:
    aligned = align_lyrics(load_lyrics(_lyrics(tmp_path)), _segments())
    report = tmp_path / "verslag.txt"
    write_report(aligned, report)
    content = report.read_text(encoding="utf-8")
    assert "Kedeng" in content and "GEDENGEDENG" in content
