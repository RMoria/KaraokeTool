"""Tests voor modules.waveform."""

from __future__ import annotations

import numpy as np
import pytest

from modules.waveform import compute_peaks, resample_peaks


def test_compute_peaks_basic() -> None:
    samples = np.zeros(1000, dtype=np.float32)
    samples[250] = 0.5   # piek in het tweede kwart
    samples[750] = -1.0  # negatieve piek in het laatste kwart
    peaks = compute_peaks(samples, 4)
    assert peaks.shape == (4,)
    assert peaks[0] == 0.0
    assert peaks[1] == pytest.approx(0.5)
    assert peaks[3] == pytest.approx(1.0)  # genormaliseerd


def test_compute_peaks_stereo_and_empty() -> None:
    stereo = np.stack([np.linspace(0, 1, 100, dtype=np.float32),
                       np.zeros(100, dtype=np.float32)], axis=1)
    peaks = compute_peaks(stereo, 10)
    assert peaks[-1] == pytest.approx(1.0)
    assert compute_peaks(np.zeros((0, 2), dtype=np.float32), 5).tolist() == \
        [0.0] * 5


def test_compute_peaks_invalid_columns() -> None:
    with pytest.raises(ValueError):
        compute_peaks(np.zeros(10, dtype=np.float32), 0)


def test_resample_peaks() -> None:
    peaks = np.array([0.0, 1.0, 0.2, 0.4], dtype=np.float32)
    assert resample_peaks(peaks, 4) is peaks
    halved = resample_peaks(peaks, 2)
    assert halved.tolist() == pytest.approx([1.0, 0.4])
    doubled = resample_peaks(peaks, 8)
    assert len(doubled) == 8 and doubled.max() == pytest.approx(1.0)
