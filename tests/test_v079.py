"""Tests for v0.79.0 features (B222, B228, B234)."""

from __future__ import annotations

from modules import song_text, timing
from modules.timing import Syllable, TimedLine


# -- B228: creative auto-coupling ------------------------------------------

def _tr(words):
    return [(w, 0.0, 0.0) for w in words]


def test_creative_2_to_1():
    # 'fort' coupled to 'formidable'; 'minable' has to join it.
    lyr = ["fort", "minable", "weg"]
    tr = _tr(["formidable", "weg"])
    targets = [[0], [], [1]]
    out = song_text.creative_couplings(lyr, tr, targets)
    assert out[0] == [0]
    assert out[1] == [0]          # minable joins in (2-to-1)
    assert out[2] == [1]


def test_creative_gap_fill_within_window():
    # 'b' uncoupled between anchors a->0 and c->2; free word 1 matches 'b'.
    lyr = ["alpha", "bravo", "charlie"]
    tr = _tr(["alpha", "bravo", "charlie"])
    targets = [[0], [], [2]]
    out = song_text.creative_couplings(lyr, tr, targets)
    assert out[1] == [1]


def test_creative_no_distant_duplicates():
    # 'et' uncoupled; an identical 'et' exists but outside the anchor
    # window.
    lyr = ["hallo", "et", "wereld"]
    tr = _tr(["hallo", "wereld", "et"])  # 'et' at index 2, outside 0..1
    targets = [[0], [], [1]]
    out = song_text.creative_couplings(lyr, tr, targets)
    assert out[1] == []           # not coupled to the distant 'et'


# -- B234: distribute words over vocal-active windows ----------------------

def _line(words_syls):
    syls = []
    for wi, sylcount in enumerate(words_syls):
        for si in range(sylcount):
            txt = ("w%d" % wi) if si == 0 else "x"
            if wi > 0 and si == 0:
                txt = " " + txt
            syls.append(Syllable(text=txt, start=0.0, end=0.0, held="nl"))
    # evenly spread over 0..N
    n = len(syls)
    out = []
    for i, s in enumerate(syls):
        out.append(Syllable(text=s.text, start=round(i / n, 3),
                            end=round((i + 1) / n, 3), held="nl"))
    return TimedLine(index=0, text="".join(s.text for s in out),
                     crowd=False, syllables=tuple(out))


def test_distribute_over_windows_pause():
    # 4 words (1 syllable each), span 0..4, two windows with a gap.
    line = _line([1, 1, 1, 1])
    line = timing.replace(line, syllables=tuple(
        timing.replace(s, start=float(i), end=float(i + 1))
        for i, s in enumerate(line.syllables)))
    windows = [(0.0, 1.8), (2.6, 4.0)]     # gap 1.8-2.6
    out = timing.distribute_over_windows(line, windows)
    # start/end of the line are preserved
    assert out.syllables[0].start == 0.0
    assert abs(out.syllables[-1].end - 4.0) < 1e-6
    # there is a gap between two words now (somewhere around 1.8-2.6)
    gaps = [out.syllables[i + 1].start - out.syllables[i].end
            for i in range(len(out.syllables) - 1)]
    assert max(gaps) > 0.5


def test_distribute_over_windows_without_windows():
    line = _line([1, 1])
    assert timing.distribute_over_windows(line, []) is line


# -- B222: overlapping bottom-row group (graph) ----------------------------

def test_bottom_overlap_merge(qapp_or_skip=None):
    import os
    import pytest
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from modules.coupling_editor import CouplingCanvas
    transcript = [("Oh", 0.0, 0.3), ("bebe", 0.3, 0.6), ("x", 0.6, 0.9)]
    # Eh -> [0]; l'bebe -> [0,1] (overlap at 0) -> group {0,1}
    words = [
        {"index": 0, "text": "Eh", "line": 0, "transcript_indices": [0],
         "found": "Oh", "sim": 0.6, "pinned": True},
        {"index": 1, "text": "l'bebe", "line": 0,
         "transcript_indices": [0, 1], "found": "Oh bebe", "sim": 0.7,
         "pinned": False},
    ]
    canvas = CouplingCanvas(transcript, words, lambda _p: None)
    spans = canvas._merged_bottom_spans()
    assert spans.get(0)[:2] == (0, 1)
    assert spans.get(1)[:2] == (0, 1)
    assert set(spans[0][2]) == {0, 1}      # union of targets
