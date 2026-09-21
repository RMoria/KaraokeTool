"""Tests for v0.107.0: B339, B340, B343 and B348.

B339 - line markers under the lyrics row of the coupling editor.
B340 - a run of anchors packed far tighter than the phrase cannot be
       right as a whole; only the outer two survive.
B343 - a word of twenty milliseconds with confidence 0.004 is not a
       word and certainly must not start a sentence.
B348 - the ruler fed the coupling the RAW transcript while the app
       itself runs on the aligned cache.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline  # noqa: E402
from modules.timing import Syllable, TimedLine, _packed_runs  # noqa: E402
from modules.whisper import Segment, Word  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _segment(index: int, words: list[Word]) -> Segment:
    return Segment(index=index, text=" ".join(w.text for w in words),
                   start=words[0].start, end=words[-1].end,
                   words=tuple(words))


# --------------------------------------------------------------------------
# B343: phantom words
# --------------------------------------------------------------------------

def test_a_phantom_word_is_dropped() -> None:
    """The measured 'I' of 0.020 s with confidence 0.004."""
    segment = _segment(2, [Word("I", 16.446, 16.466, 0.004),
                           Word("don't", 18.829, 18.989, 0.569),
                           Word("know", 19.029, 19.209, 0.910)])
    out = pipeline._drop_phantom_words((segment,))
    assert [w.text for w in out[0].words] == ["don't", "know"]
    # The segment now starts where it really starts - that is the gain.
    assert out[0].start == pytest.approx(18.829)


def test_a_short_but_certain_word_stays() -> None:
    """Duration alone says nothing: 'a' of 0.040 s scores 0.952."""
    segment = _segment(3, [Word("a", 143.174, 143.214, 0.952),
                           Word("fantasy", 143.3, 143.9, 0.7)])
    out = pipeline._drop_phantom_words((segment,))
    assert len(out[0].words) == 2


def test_an_uncertain_but_long_word_stays() -> None:
    """And confidence alone says nothing either - both conditions count."""
    segment = _segment(4, [Word("shoes", 139.418, 140.100, 0.055),
                           Word("now", 140.2, 140.6, 0.8)])
    out = pipeline._drop_phantom_words((segment,))
    assert len(out[0].words) == 2


def test_a_segment_of_only_a_phantom_disappears() -> None:
    segment = _segment(5, [Word("I", 60.082, 60.102, 0.006)])
    assert pipeline._drop_phantom_words((segment,)) == ()


def test_the_phantom_filter_sits_in_the_read_path() -> None:
    """Existing projects benefit without transcribing all over again."""
    source = (ROOT / "modules" / "pipeline.py").read_text(encoding="utf-8")
    head = source[source.index("def load_segments("):]
    body = head[:head.index("\n\n\ndef ")]
    for name in ("_drop_phantom_words", "_merge_boundary_duplicates",
                 "_drop_repetition_loop"):
        assert name in body, f"{name} is not hooked into load_segments"


# --------------------------------------------------------------------------
# B340: packed anchors
# --------------------------------------------------------------------------

def _line(index: int, start: float, end: float) -> TimedLine:
    return TimedLine(index=index, text=f"regel {index}", crowd=False,
                     syllables=(Syllable(text="la", start=start, end=end),),
                     quality="high")


def _inner(lines, anchors, period) -> set:
    """Which anchors of a packed run have to go (B340/B535)."""
    return {i for run in _packed_runs(lines, anchors, period)
            for i in run[1:-1]}


def test_a_packed_run_loses_its_inner_anchors() -> None:
    """Four anchors a third of a second apart on a 3.5 s phrase."""
    lines = [_line(i, 10.0 + 0.33 * i, 10.3 + 0.33 * i) for i in range(4)]
    suspect = _inner(lines, list(range(4)), 3.5)
    assert suspect == {1, 2}


def test_normal_spacing_is_left_alone() -> None:
    lines = [_line(i, 10.0 + 3.5 * i, 13.0 + 3.5 * i) for i in range(4)]
    assert _inner(lines, list(range(4)), 3.5) == set()


def test_two_close_together_is_not_a_run() -> None:
    """Two in quick succession can simply be an interjection."""
    lines = [_line(0, 10.0, 10.3), _line(1, 10.4, 10.7),
             _line(2, 20.0, 23.0)]
    assert _inner(lines, [0, 1, 2], 3.5) == set()


def test_without_a_period_nothing_happens() -> None:
    """Seven out of ten projects yield no reliable period."""
    lines = [_line(i, 10.0 + 0.33 * i, 10.3 + 0.33 * i) for i in range(4)]
    assert _inner(lines, list(range(4)), None) == set()


# --------------------------------------------------------------------------
# B339: line markers in the coupling editor
# --------------------------------------------------------------------------

def test_a_line_marker_sits_at_every_line_change(qapp=None) -> None:
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from modules.coupling_editor import CouplingCanvas

    words = [{"index": i, "text": text, "line": line, "sim": 0.9,
              "pinned": False, "transcript_indices": [i],
              "status": "coupled"}
             for i, (text, line) in enumerate(
                 [("nu", 0), ("nu", 0), ("nu", 1), ("nu", 1), ("nu", 2)])]
    transcript = [("nu", float(i), float(i) + 0.2) for i in range(5)]
    canvas = CouplingCanvas(transcript, words, on_change=lambda _d: None)
    assert [number for number, _col in canvas.line_marker_columns()] \
        == [0, 1, 2]


# --------------------------------------------------------------------------
# B348: the ruler takes the cache
# --------------------------------------------------------------------------

def test_the_ruler_prefers_the_cache_over_the_raw_copy(tmp_path) -> None:
    """The app couples on the cache (after forced alignment), so the
    measurement has to do the same."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "regression", ROOT / "tools" / "timing_regression.py")
    regression = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regression)

    song = "Proef"
    project = tmp_path / "output" / song
    (project / "settings").mkdir(parents=True)
    (project / "original").mkdir(parents=True)
    (tmp_path / "input" / song).mkdir(parents=True)
    (tmp_path / "input" / song / "songtekst.txt").write_text(
        "een twee\n", encoding="utf-8")
    (project / "settings" / "project.json").write_text(
        json.dumps({"steps": {}}), encoding="utf-8")

    def segments(start: float) -> str:
        return json.dumps([{"index": 0, "text": "een", "start": start,
                            "end": start + 1.0,
                            "words": [{"text": "een", "start": start,
                                       "end": start + 1.0, "conf": 0.9}]}])

    (project / "original" / "segmenten.json").write_text(
        segments(10.660), encoding="utf-8")

    # Without a cache it falls back on the raw copy ...
    context = regression._build_project(project, tmp_path / "work1")
    stored = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    assert json.loads(stored.read_text())[0]["start"] == pytest.approx(10.660)
    assert regression.SOURCE[song] == "ruw"

    # ... and with a cache it takes that, for that is what the app reads.
    cache = tmp_path / "cache" / song
    cache.mkdir(parents=True)
    (cache / "transcription_original.json").write_text(
        segments(11.201), encoding="utf-8")
    context = regression._build_project(project, tmp_path / "work2")
    stored = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    assert json.loads(stored.read_text())[0]["start"] == pytest.approx(11.201)
    assert regression.SOURCE[song] == "cache"
