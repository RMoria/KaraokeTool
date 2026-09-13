"""Waveform data for display in the GUI.

Pure numpy calculations (no Qt), so this is testable on its own. The
GUI draws the peaks and marks the damped fragments.
"""

from __future__ import annotations

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)


def compute_peaks(samples: np.ndarray, columns: int) -> np.ndarray:
    """Convert audio samples into peak values per column (0..1).

    Args:
        samples: Array with shape ``(n,)`` or ``(n, channels)``.
        columns: The number of columns (e.g. the width of the display).

    Returns:
        Array with shape ``(columns,)``: the maximum absolute amplitude
        per time slot, normalised to 0..1.
    """
    if columns < 1:
        raise ValueError("columns moet minimaal 1 zijn")
    mono = np.abs(samples)
    if mono.ndim > 1:
        mono = mono.max(axis=1)
    if mono.size == 0:
        return np.zeros(columns, dtype=np.float32)

    per_column = max(1, math.ceil(mono.size / columns))
    padded_length = per_column * columns
    padded = np.zeros(padded_length, dtype=np.float32)
    padded[:mono.size] = mono
    peaks = padded.reshape(columns, per_column).max(axis=1)

    top = float(peaks.max())
    if top > 0:
        peaks = peaks / top
    return peaks.astype(np.float32)


def resample_peaks(peaks: np.ndarray, width: int) -> np.ndarray:
    """Scale a peak series to another width (max per range)."""
    if width < 1:
        raise ValueError("width moet minimaal 1 zijn")
    if len(peaks) == width:
        return peaks
    edges = np.linspace(0, len(peaks), width + 1).astype(int)
    return np.array([peaks[start:max(start + 1, end)].max()
                     for start, end in zip(edges[:-1], edges[1:])],
                    dtype=np.float32)
