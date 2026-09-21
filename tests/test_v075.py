"""Tests for the v0.75.0 features (B189, B191, B194, B201, B202, B207,
B208, B209)."""

from __future__ import annotations

import numpy as np
import pytest

from modules import pipeline, rhythm, song_text, timing
from modules.timing import Syllable, TimedLine


# -- B207: filler-line filter for language detection ------------------------

def test_is_filler_line_detects_nanana():
    assert pipeline._is_filler_line("Na na na na")
    assert pipeline._is_filler_line("la-la-la")
    assert pipeline._is_filler_line("Oh oh oh")
    assert pipeline._is_filler_line("nanana")
    assert pipeline._is_filler_line("[crowd]hey hey[/crowd]")


def test_is_filler_line_leaves_real_text_alone():
    assert not pipeline._is_filler_line("Freed from desire")
    assert not pipeline._is_filler_line("Kwamen zie doar op de fiets")


def test_strip_filler_removes_only_filler_lines():
    text_value = "Freed from desire\nNa na na na\nMind and senses purified\nla la la"
    clean = pipeline._strip_filler_for_language(text_value)
    assert "Freed from desire" in clean
    assert "purified" in clean
    assert "Na na" not in clean
    assert "la la" not in clean


def test_strip_filler_falls_back_when_all_is_filler():
    text_value = "na na na\nla la la"
    # Nothing meaningful left -> hand back the original text.
    assert pipeline._strip_filler_for_language(text_value) == text_value


# -- B208: language choice with near-equal candidates -----------------------

def test_language_ambiguous_within_the_margin():
    assert pipeline.language_ambiguous([("nl", 0.52), ("en", 0.50)])
    assert not pipeline.language_ambiguous([("en", 0.90), ("nl", 0.05)])
    assert not pipeline.language_ambiguous([("en", 0.99)])


# -- B191: smarter auto-coupling --------------------------------------------

def test_extend_coupling_hooks_on_the_neighbour():
    # "Tinus" is phonetically better covered by "Tien" + "Is" together.
    transcript = [("tien", 0.0, 0.4), ("is", 0.4, 0.8), ("weg", 0.8, 1.2)]
    targets = song_text.extend_coupling("Tinus", transcript, 0, claimed=set())
    assert targets == [0, 1]


def test_extend_coupling_stops_at_a_claimed_word():
    transcript = [("tien", 0.0, 0.4), ("is", 0.4, 0.8)]
    # neighbour index 1 is already claimed by another word -> no extension.
    targets = song_text.extend_coupling("Tinus", transcript, 0, claimed={1})
    assert targets == [0]


def test_extend_coupling_no_extension_without_gain():
    transcript = [("hallo", 0.0, 0.5), ("wereld", 0.5, 1.0)]
    targets = song_text.extend_coupling("hallo", transcript, 0, claimed=set())
    assert targets == [0]


# -- B194/B209: vocal-stem energy -------------------------------------------

def _write_wav(path, signal, sr=22050):
    import soundfile as sf
    sf.write(str(path), signal.astype(np.float32), sr)


def test_held_note_end_extends_to_the_silence(tmp_path):
    pytest.importorskip("librosa")
    sr = 22050
    # 2 s of tone, then 1 s of silence.
    tone = 0.5 * np.sin(2 * np.pi * 220 * np.arange(2 * sr) / sr)
    silent = np.zeros(sr)
    signal = np.concatenate([tone, silent])
    wav = tmp_path / "vocal.wav"
    _write_wav(wav, signal, sr)
    # Original end too early (0.5 s), ceiling generous (2.8 s).
    end = rhythm.held_note_end(wav, start=0.0, floor_end=0.5, ceil_end=2.8)
    assert end is not None
    assert 1.7 <= end <= 2.4     # around the end of the tone


def test_held_note_end_within_the_bounds(tmp_path):
    pytest.importorskip("librosa")
    sr = 22050
    signal = 0.5 * np.sin(2 * np.pi * 220 * np.arange(3 * sr) / sr)
    wav = tmp_path / "vocal.wav"
    _write_wav(wav, signal, sr)
    end = rhythm.held_note_end(wav, start=0.0, floor_end=0.5, ceil_end=1.5)
    assert end is not None
    assert end <= 1.5 + 1e-6      # never past the ceiling


def test_energy_onsets_finds_the_pulses(tmp_path):
    pytest.importorskip("librosa")
    sr = 22050
    # Four short pulses (na-na-na-na) with silences between, over 4 s.
    signal = np.zeros(4 * sr, dtype=np.float32)
    for k in range(4):
        start = int((0.2 + k) * sr)
        pulse = 0.6 * np.sin(2 * np.pi * 300 *
                             np.arange(int(0.3 * sr)) / sr)
        signal[start:start + pulse.size] += pulse
    wav = tmp_path / "nanana.wav"
    _write_wav(wav, signal, sr)
    onsets = rhythm.energy_onsets(wav, 0.0, 4.0, expected=4)
    assert len(onsets) >= 3        # at least most of the pulses back
    assert all(0.0 <= o <= 4.0 for o in onsets)


# -- B201: the original line out of the text --------------------------------

def test_timedline_from_text_divides_evenly():
    line = timing.timedline_from_text(0, "hallo wereld", 0.0, 2.0)
    assert line.text == "hallo wereld"
    assert line.syllables[0].start == 0.0
    assert abs(line.syllables[-1].end - 2.0) < 1e-6
    # ascending
    times = [s.start for s in line.syllables]
    assert times == sorted(times)


# -- B202: aligning the stress timing ---------------------------------------

def _line(sylspec):
    syls = tuple(Syllable(text=t, start=s, end=e, held="nl", stress=n)
                 for t, s, e, n in sylspec)
    return TimedLine(index=0, text="".join(s[0] for s in sylspec),
                     crowd=False, syllables=syls)


def test_stress_fraction():
    line = _line([("a", 0.0, 1.0, False), ("b", 1.0, 2.0, True)])
    frac = timing.stress_fraction(line.syllables)
    assert abs(frac - 0.75) < 1e-6


def test_shift_stress_to_shifts_and_keeps_the_bounds():
    line = _line([("a", 0.0, 1.0, False), ("b", 1.0, 2.0, True),
                  ("c", 2.0, 3.0, False)])
    shifted = timing.shift_stress_to(line, target_rel=0.3)
    # line start/end and the count stay the same
    assert shifted.syllables[0].start == 0.0
    assert abs(shifted.syllables[-1].end - 3.0) < 1e-6
    assert len(shifted.syllables) == 3
    # the stressed syllable has moved forward
    frac_after = timing.stress_fraction(shifted.syllables)
    assert frac_after < 0.5


def test_align_karaoke_stress_uses_the_mapping():
    karaoke = [_line([("ka", 0.0, 1.0, False), ("ra", 1.0, 2.0, True),
                      ("o", 2.0, 3.0, False)])]
    original = [_line([("o", 0.0, 1.0, True), ("ri", 1.0, 2.0, False)])]
    out = timing.align_karaoke_stress(karaoke, original, {0: 0})
    # the original stress sits up front -> karaoke moves forward
    assert timing.stress_fraction(out[0].syllables) < \
        timing.stress_fraction(karaoke[0].syllables)


def test_align_karaoke_stress_leaves_uncoupled_alone():
    karaoke = [_line([("a", 0.0, 1.0, False), ("b", 1.0, 2.0, True)])]
    out = timing.align_karaoke_stress(karaoke, [], {})
    assert out[0].syllables == karaoke[0].syllables


# -- B198: the original cells carry rows ------------------------------------

def test_original_view_cells_carries_rows():
    originals = [{"text": "een twee", "start": 0.0, "end": 2.0, "rows": [3]}]
    cells = timing.original_view_cells(originals, "sentences")
    assert cells[0]["rows"] == [3]
    words = timing.original_view_cells(originals, "words")
    assert all(c["rows"] == [3] for c in words)


# -- B189: a double coupling as one box (Qt) --------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_coupling_merged_spans(qapp):
    from modules.coupling_editor import CouplingCanvas
    transcript = [("tien", 0.0, 0.4), ("is", 0.4, 0.8), ("weg", 0.8, 1.2)]
    words = [{"index": 0, "text": "Tinus", "line": 0,
                "transcript_indices": [0, 1], "found": "tien is",
                "sim": 0.8, "pinned": True},
               {"index": 1, "text": "weg", "line": 0,
                "transcript_indices": [2], "found": "weg",
                "sim": 0.9, "pinned": False}]
    canvas = CouplingCanvas(transcript, words, lambda _p: None)
    spans = canvas._merged_spans()
    # 0 and 1 together form one box; 2 does not.
    assert spans.get(0) == (0, 1)
    assert spans.get(1) == (0, 1)
    assert 2 not in spans


def test_timing_canvas_disable_from_the_original(qapp):
    from modules.timing_editor import TimingCanvas
    lines = [{"text": "een", "crowd": False, "index": 0,
              "crowd_section": False, "quality": "sentence", "block": 0,
              "disabled": False,
              "syllables": [{"text": "een", "start": 0.0, "end": 1.0,
                             "held": "nl", "stress": False, "crowd": False}]}]
    originals = [{"text": "one", "start": 0.0, "end": 1.0, "rows": [0]}]
    peaks = _peaks_arr()
    canvas = TimingCanvas(peaks, peaks, 2.0, lines, on_seek=lambda _t: None,
                          originals=originals, original_duration=2.0)
    canvas._orig_cells = timing.original_view_cells(originals, "sentences")
    canvas._sel_orig = 0
    assert canvas.toggle_selected_disabled()
    assert lines[0]["disabled"]


def _peaks_arr():
    return np.abs(np.sin(np.linspace(0, 20, 200))).astype(np.float32)
