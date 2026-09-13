"""Tests voor modules.karaoke."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from modules.align import OffsetRegion
from modules.audio import db_to_amplitude, load_audio, save_wav
from modules.cluster import Cluster, Occurrence
from modules.config import KaraokeSettings
from modules.karaoke import (
    DampingInterval,
    apply_damping,
    build_envelope,
    find_intervals,
    intervals_from_dicts,
    intervals_to_dicts,
)


def _cluster(times: list[tuple[float, float]]) -> Cluster:
    occurrences = tuple(Occurrence(text="oe", start=start, end=end,
                                   confidence=0.9, segment=0)
                        for start, end in times)
    return Cluster(id=1, label="OE", members=(("oe", len(times)),),
                   occurrences=occurrences, segments=(0,),
                   frequency=len(times), avg_confidence=0.9,
                   avg_duration_s=0.4, avg_pause_s=1.0)


def test_find_intervals_projects_via_alignment() -> None:
    regions = (OffsetRegion(0.0, 100.0, -0.5, 0.9),)
    intervals = find_intervals([_cluster([(10.0, 10.4)])], regions,
                               KaraokeSettings())
    assert len(intervals) == 1
    assert intervals[0].start == pytest.approx(9.5)
    assert intervals[0].end == pytest.approx(9.9)
    assert intervals[0].gain_db == -25.0


def test_find_intervals_merges_adjacent() -> None:
    regions = (OffsetRegion(0.0, 100.0, 0.0, 0.9),)
    intervals = find_intervals(
        [_cluster([(10.0, 10.4), (10.42, 10.8), (50.0, 50.5)])],
        regions, KaraokeSettings())
    assert len(intervals) == 2
    assert intervals[0].end == pytest.approx(10.8)
    assert intervals[1].start == pytest.approx(50.0)


def test_build_envelope_shape_and_fades() -> None:
    settings = KaraokeSettings(gain_db=-25.0, fade_in_ms=100, fade_out_ms=100)
    sample_rate = 10_000
    intervals = (DampingInterval("OE", 1.0, 1.5, -25.0),)
    envelope = build_envelope(3 * sample_rate, sample_rate, intervals, settings)
    gain = db_to_amplitude(-25.0)

    assert envelope[5_000] == pytest.approx(1.0)          # ver vóór fragment
    assert envelope[12_000] == pytest.approx(gain, abs=1e-4)  # in fragment
    assert envelope[25_000] == pytest.approx(1.0)         # ver erna
    # Halverwege de fade-in (50 ms vóór de start): tussen gain en 1.
    halfway = envelope[10_000 - 500]
    assert gain < halfway < 1.0


def test_apply_damping_reduces_level(tmp_path: Path) -> None:
    sample_rate = 22_050
    time = np.arange(3 * sample_rate) / sample_rate
    tone = (0.5 * np.sin(2 * np.pi * 440 * time)).astype(np.float32)
    data = np.stack([tone, tone], axis=1)
    source = tmp_path / "karaoke.wav"
    save_wav(source, data, sample_rate)

    settings = KaraokeSettings(gain_db=-25.0, fade_in_ms=70, fade_out_ms=60)
    output = tmp_path / "bewerkt.wav"
    apply_damping(source, (DampingInterval("OE", 1.0, 1.5, -25.0),),
                  settings, output)

    processed, _ = load_audio(output)

    def rms(signal: np.ndarray, start_s: float, end_s: float) -> float:
        segment = signal[int(start_s * sample_rate):int(end_s * sample_rate), 0]
        return float(np.sqrt(np.mean(segment ** 2)))

    original_rms = rms(data, 0.2, 0.8)
    untouched_rms = rms(processed, 0.2, 0.8)
    damped_rms = rms(processed, 1.1, 1.4)

    assert untouched_rms == pytest.approx(original_rms, rel=0.01)
    ratio_db = 20 * np.log10(damped_rms / original_rms)
    assert ratio_db == pytest.approx(-25.0, abs=1.0)


def test_intervals_roundtrip() -> None:
    intervals = (DampingInterval("OE", 1.0, 1.5, -25.0),)
    assert intervals_from_dicts(intervals_to_dicts(intervals)) == intervals


def test_find_intervals_applies_margin() -> None:
    regions = (OffsetRegion(0.0, 100.0, 0.0, 0.9),)
    settings = KaraokeSettings(margin_ms=150)
    intervals = find_intervals([_cluster([(10.0, 10.4)])], regions, settings)
    assert intervals[0].start == pytest.approx(9.85)
    assert intervals[0].end == pytest.approx(10.55)
