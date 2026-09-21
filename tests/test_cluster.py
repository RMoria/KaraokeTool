"""Tests for modules.cluster (phonetic clustering)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.cluster import (
    Cluster,
    _fold_repeats,
    _levenshtein,
    build_clusters,
    build_tokens,
    clusters_from_dicts,
    clusters_to_dicts,
    format_overview,
    phonetic_key,
    similarity,
    suggest_clusters,
    write_outputs,
)
from modules.config import ClusterSettings
from modules.whisper import Segment, Word


def test_phonetic_key_basics() -> None:
    assert phonetic_key("kedeng") == "ketenk"
    assert phonetic_key("GEDENGEDENG") == "ketenketenk"
    # oe/oeh/ooh/oh all sound the same
    assert phonetic_key("oe") == phonetic_key("oeh") == \
        phonetic_key("ooh") == phonetic_key("oh") == "o"
    assert phonetic_key("koffie") == "kofi"
    assert phonetic_key("koffie thee") == phonetic_key("koffiethee")


def test_levenshtein() -> None:
    assert _levenshtein("", "abc") == 3
    assert _levenshtein("kat", "kat") == 0
    assert _levenshtein("kat", "krat") == 1


def test_fold_repeats() -> None:
    assert _fold_repeats("ketenketen") == "keten"
    assert _fold_repeats("ketenk") == "ketenk"


def test_similarity_rules() -> None:
    assert similarity("ketenk", "ketenk") == 1.0
    # Containment: GEDENGEDENG belongs with kedeng.
    assert similarity(phonetic_key("kedeng"),
                      phonetic_key("gedengedeng")) >= 0.75
    # KREEG ER EEN belongs (phonetically) with kedeng.
    assert similarity(phonetic_key("kedeng"),
                      phonetic_key("kreeg er een")) >= 0.65
    # Unrelated words are not alike.
    assert similarity(phonetic_key("koffie"), phonetic_key("kedeng")) < 0.65


def _word(text: str, start: float, duration: float = 0.4,
          confidence: float = 0.9) -> Word:
    return Word(text=text, start=start, end=start + duration,
                confidence=confidence)


def _per_track_segments() -> tuple[Segment, ...]:
    """Mock Whisper output with inconsistent spelling."""
    seg0 = (_word("GEDENGEDENG", 1.0, 0.8), _word("GEDENGEDENG", 3.0, 0.8))
    seg1 = (_word("Kreeg", 5.0, 0.25), _word("er", 5.28, 0.15),
            _word("een", 5.46, 0.2))
    seg2 = (_word("Kregering", 7.0, 0.7),)
    seg3 = (_word("oeh", 9.0, 0.3), _word("oe", 9.5, 0.3))
    seg4 = (_word("koffiethee", 11.0, 0.8),)
    make = lambda i, words: Segment(  # noqa: E731
        index=i, text=" ".join(w.text for w in words),
        start=words[0].start, end=words[-1].end, words=words)
    return tuple(make(i, words) for i, words in
                 enumerate((seg0, seg1, seg2, seg3, seg4)))


def test_build_tokens_merges_within_gap() -> None:
    segments = _per_track_segments()
    settings = ClusterSettings(merge_gap_ms=100, max_ngram=3)
    tokens = build_tokens(segments, settings)
    texts = {token.text for token in tokens}
    # The 'Kreeg er een' words lie < 100 ms apart, so n-grams exist.
    assert "Kreeg er een" in texts
    # The two GEDENGEDENGs lie far apart: no bigram.
    assert "GEDENGEDENG GEDENGEDENG" not in texts


def test_build_clusters_per_track() -> None:
    """The core: different spellings of 'kedeng' in one cluster."""
    found = build_clusters(_per_track_segments(), ClusterSettings())

    def cluster_with(spelling: str) -> Cluster:
        for cluster in found:
            if any(spelling in member for member, _ in cluster.members):
                return cluster
        raise AssertionError(f"no cluster with {spelling}")

    kedeng = cluster_with("GEDENGEDENG")
    spellings = {member for member, _ in kedeng.members}
    assert "KREEG ER EEN" in spellings
    assert "KREGERING" in spellings
    assert kedeng.frequency == 4  # 2x GEDENGEDENG + kreeg-er-een + kregering

    oe = cluster_with("OEH")
    assert {member for member, _ in oe.members} == {"OEH", "OE"}
    assert oe.frequency == 2  # deduplicated: not the bigram 'oeh oe' as well


def test_cluster_stats() -> None:
    found = build_clusters(_per_track_segments(), ClusterSettings())
    kedeng = found[0]  # largest cluster first
    assert kedeng.frequency == 4
    assert kedeng.avg_duration_s == pytest.approx(0.74, abs=0.05)
    assert kedeng.avg_pause_s > 1.0  # repeats with gaps (chorus)
    assert 0.0 < kedeng.avg_confidence <= 1.0


def test_suggest_clusters() -> None:
    found = build_clusters(_per_track_segments(), ClusterSettings())
    suggested = suggest_clusters(found, ("oe", "kedeng"), 0.65)
    labels = {cluster.label for cluster in found if cluster.id in suggested}
    assert "GEDENGEDENG" in labels
    assert any(label in {"OEH", "OE"} for label in labels)


def test_write_outputs_and_roundtrip(tmp_path: Path) -> None:
    segments = _per_track_segments()
    found = build_clusters(segments, ClusterSettings())
    json_path, html_path = write_outputs(found, segments, tmp_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert clusters_from_dicts(data) == found
    assert clusters_to_dicts(found) == data
    assert html_path.exists()
    assert not (tmp_path / "clusters.csv").exists()  # no CSV any more


def test_html_report_content(tmp_path: Path) -> None:
    segments = _per_track_segments()
    found = build_clusters(segments, ClusterSettings())
    _, html_path = write_outputs(found, segments, tmp_path)
    report = html_path.read_text(encoding="utf-8")
    assert "Cluster 1" in report
    assert "GEDENGEDENG" in report
    assert "KREEG ER EEN" in report          # variants
    assert "Voorbeeldtekst" in report
    assert "Segmenten" in report
    assert 'type=checkbox' in report          # selection for menu step 2
    assert "0:01.0" in report                 # time of first occurrence


def test_occurrences_carry_segment_numbers() -> None:
    segments = _per_track_segments()
    found = build_clusters(segments, ClusterSettings())
    kedeng = found[0]
    # GEDENGEDENG, kreeg-er-een, kregering
    assert kedeng.segments == (0, 1, 2)
    assert all(occ.segment in kedeng.segments for occ in kedeng.occurrences)


def test_format_overview_mentions_counts() -> None:
    found = build_clusters(_per_track_segments(), ClusterSettings())
    overview = format_overview(found)
    assert "Cluster 1" in overview
    assert "gevonden: 4 keer" in overview


def test_subtoken_clusters_are_suppressed() -> None:
    """Sub-tokens such as 'ER' (inside 'KREEG ER EEN') do not
    become a cluster of their own."""
    found = build_clusters(_per_track_segments(), ClusterSettings())
    assert len(found) == 3  # kedeng variants, oe variants, koffiethee
    labels = {cluster.label.lower() for cluster in found}
    assert "er" not in labels and "er een" not in labels


def test_hallucinations_are_filtered() -> None:
    """Whisper hallucinations such as 'Muziek' stay out of the
    clusters."""
    words = (Word("Muziek", 1.0, 1.5, 0.5), Word("Muziek", 3.0, 3.5, 0.5),
             Word("oe", 5.0, 5.4, 0.9), Word("oe", 6.0, 6.4, 0.9),
             Word("Ondertiteld", 8.0, 8.8, 0.4))
    segments = (Segment(0, " ".join(w.text for w in words), 1.0, 8.8,
                        words),)
    found = build_clusters(segments, ClusterSettings())
    labels = {cluster.label for cluster in found}
    assert "MUZIEK" not in labels and "ONDERTITELD" not in labels
    assert any("OE" == label for label in labels)  # real sounds remain
