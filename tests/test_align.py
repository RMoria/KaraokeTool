"""Tests for modules.align (without librosa: the pure numpy parts)."""

from __future__ import annotations

import numpy as np
import pytest

from modules.align import (
    OffsetRegion,
    WindowOffset,
    _build_regions,
    _correlate_offset,
    project_time,
    regions_from_dicts,
    regions_to_dicts,
)
from modules.config import AlignSettings


def test_correlate_offset_finds_shift() -> None:
    """A shifted copy is found back at the right lag."""
    rng = np.random.default_rng(42)
    reference = rng.normal(size=(5, 2000)).astype(np.float32)
    query = reference[:, 300:1300]
    lag, confidence = _correlate_offset(reference, query)
    assert lag == pytest.approx(300, abs=0.5)
    assert confidence > 0.5


def test_correlate_offset_negative_lag() -> None:
    """A negative shift works too: the karaoke starts earlier."""
    rng = np.random.default_rng(7)
    query = rng.normal(size=(3, 800)).astype(np.float32)
    reference = query[:, 200:700]
    lag, _ = _correlate_offset(reference, query)
    assert lag == pytest.approx(-200, abs=0.5)


def _window(start: float, offset: float, confidence: float = 0.8) -> WindowOffset:
    return WindowOffset(start=start, end=start + 20.0, offset=offset,
                        confidence=confidence)


def test_build_regions_single_offset() -> None:
    windows = [_window(t, -0.70) for t in (0.0, 10.0, 20.0, 30.0)]
    regions = _build_regions(windows, 60.0, -0.70, 0.9, AlignSettings())
    assert len(regions) == 1
    assert regions[0].start == 0.0 and regions[0].end == 60.0
    assert regions[0].offset == pytest.approx(-0.70)


def test_build_regions_two_offsets() -> None:
    windows = ([_window(t, -0.10) for t in (0.0, 10.0, 20.0)]
               + [_window(t, -0.90) for t in (30.0, 40.0, 50.0)])
    regions = _build_regions(windows, 80.0, -0.5, 0.5, AlignSettings())
    assert len(regions) == 2
    assert regions[0].offset == pytest.approx(-0.10)
    assert regions[1].offset == pytest.approx(-0.90)
    # The coverage is continuous, from 0 to the duration.
    assert regions[0].start == 0.0
    assert regions[0].end == pytest.approx(regions[1].start)
    assert regions[1].end == 80.0


def test_build_regions_respects_max_offsets() -> None:
    windows = ([_window(0.0, -0.10), _window(10.0, -0.15),
                _window(20.0, -0.90), _window(30.0, -0.95)])
    settings = AlignSettings(max_offsets=1, tolerance_ms=20)
    regions = _build_regions(windows, 60.0, -0.5, 0.5, settings)
    assert len(regions) == 1


def test_build_regions_fallback_without_confidence() -> None:
    windows = [_window(0.0, -0.3, confidence=0.01)]
    regions = _build_regions(windows, 60.0, -0.42, 0.4, AlignSettings())
    assert len(regions) == 1
    assert regions[0].offset == pytest.approx(-0.42)


def test_project_time() -> None:
    regions = (OffsetRegion(0.0, 100.0, -0.5, 0.9),
               OffsetRegion(100.0, 200.0, -1.0, 0.9))
    assert project_time(50.0, regions) == pytest.approx(49.5)
    assert project_time(150.0, regions) == pytest.approx(149.0)
    # Outside every region the nearest region applies.
    assert project_time(250.0, regions) == pytest.approx(249.0)
    assert project_time(10.0, ()) == pytest.approx(10.0)


def test_regions_roundtrip() -> None:
    regions = (OffsetRegion(0.0, 120.5, -0.7, 0.85),)
    assert regions_from_dicts(regions_to_dicts(regions)) == regions


def test_smooth_regions_rejects_local_outlier() -> None:
    """A LOOSE outlier between steady neighbours follows the local trend.

    (B249) The old approach pulled every deviation towards the global
    median and forced the offsets not to fall; that flattened real
    drift. Now only an outlier measured against its own neighbours is
    pulled in, while a gradual slope survives (see the drift test
    below).
    """
    from modules.align import OffsetRegion, _smooth_regions
    regions = (OffsetRegion(0, 10, 0.70, 0.72),
               OffsetRegion(10, 20, 4.40, 0.60),   # loose outlier
               OffsetRegion(20, 30, 0.65, 0.50),
               OffsetRegion(30, 40, 0.68, 0.52))
    out = _smooth_regions(regions)
    offsets = [r.offset for r in out]
    assert max(offsets) < 1.0                       # outlier flattened


def test_smooth_regions_keeps_gradual_drift() -> None:
    """Gradual drift, falling drift included, is kept (B249).

    Over its length the karaoke can start running ahead of the original
    (the offset drops); that must not be flattened. The projected time
    does stay monotonic - it never jumps back.
    """
    from modules.align import (OffsetRegion, _smooth_regions, project_time)
    regions = tuple(
        OffsetRegion(i * 10.0, i * 10.0 + 10.0, -i * 1.5, 0.7)
        for i in range(6))                          # 0, -1.5, -3, ... -7.5
    out = _smooth_regions(regions)
    offsets = [r.offset for r in out]
    assert min(offsets) < -5.0                      # drift NOT flattened
    # The projected time never runs backwards.
    times = [project_time(t, out) for t in range(0, 60, 2)]
    assert times == sorted(times)


def test_full_alignment_with_librosa(tmp_path) -> None:
    """Integration test on real audio; skipped without librosa."""
    pytest.importorskip("librosa")
    from pathlib import Path

    from modules.align import determine_offsets
    from modules.audio import save_wav

    rng = np.random.default_rng(3)
    sample_rate = 22050
    duration_s = 30
    # A rhythmic signal: noise bursts at irregular places.
    original = np.zeros(sample_rate * duration_s, dtype=np.float32)
    for position_s in (1.0, 2.2, 4.1, 5.0, 7.3, 9.9, 12.0, 14.8, 17.1,
                       19.5, 21.2, 24.4, 26.0, 28.3):
        index = int(position_s * sample_rate)
        original[index:index + 2000] = rng.normal(
            0, 0.4, 2000).astype(np.float32)
    shift = int(0.5 * sample_rate)  # the karaoke starts 0.5 s later
    karaoke = np.concatenate([np.zeros(shift, dtype=np.float32),
                              original])[:original.size]

    original_path = tmp_path / "original.wav"
    karaoke_path = tmp_path / "karaoke.wav"
    save_wav(original_path, original[:, None], sample_rate)
    save_wav(karaoke_path, karaoke[:, None], sample_rate)

    regions = determine_offsets(Path(original_path), Path(karaoke_path),
                                AlignSettings(window_s=8.0, step_s=4.0))
    assert regions
    # offset = karaoke - original = +0.5 s
    assert regions[0].offset == pytest.approx(0.5, abs=0.05)
