"""Tests voor v0.75.0-functies (B189, B191, B194, B201, B202, B207, B208,
B209)."""

from __future__ import annotations

import numpy as np
import pytest

from modules import pipeline, rhythm, song_text, timing
from modules.timing import Syllable, TimedLine


# -- B207: vulregelfilter voor taaldetectie --------------------------------

def test_is_filler_line_detecteert_nanana():
    assert pipeline._is_filler_line("Na na na na")
    assert pipeline._is_filler_line("la-la-la")
    assert pipeline._is_filler_line("Oh oh oh")
    assert pipeline._is_filler_line("nanana")
    assert pipeline._is_filler_line("[crowd]hey hey[/crowd]")


def test_is_filler_line_laat_echte_tekst_staan():
    assert not pipeline._is_filler_line("Freed from desire")
    assert not pipeline._is_filler_line("Kwamen zie doar op de fiets")


def test_strip_filler_verwijdert_alleen_vulregels():
    text_value = "Freed from desire\nNa na na na\nMind and senses purified\nla la la"
    schoon = pipeline._strip_filler_for_language(text_value)
    assert "Freed from desire" in schoon
    assert "purified" in schoon
    assert "Na na" not in schoon
    assert "la la" not in schoon


def test_strip_filler_valt_terug_als_alles_vulling_is():
    text_value = "na na na\nla la la"
    # Niets zinnigs over -> geef de oorspronkelijke tekst terug.
    assert pipeline._strip_filler_for_language(text_value) == text_value


# -- B208: taalkeuze bij bijna gelijke kandidaten --------------------------

def test_language_ambiguous_binnen_marge():
    assert pipeline.language_ambiguous([("nl", 0.52), ("en", 0.50)])
    assert not pipeline.language_ambiguous([("en", 0.90), ("nl", 0.05)])
    assert not pipeline.language_ambiguous([("en", 0.99)])


# -- B191: slimmere auto-koppeling -----------------------------------------

def test_extend_coupling_haakt_buurwoord_aan():
    # "Tinus" fonetisch beter gedekt door "Tien" + "Is" samen.
    transcript = [("tien", 0.0, 0.4), ("is", 0.4, 0.8), ("weg", 0.8, 1.2)]
    targets = song_text.extend_coupling("Tinus", transcript, 0, claimed=set())
    assert targets == [0, 1]


def test_extend_coupling_stopt_bij_geclaimd():
    transcript = [("tien", 0.0, 0.4), ("is", 0.4, 0.8)]
    # buur index 1 al door een ander woord geclaimd -> niet uitbreiden.
    targets = song_text.extend_coupling("Tinus", transcript, 0, claimed={1})
    assert targets == [0]


def test_extend_coupling_geen_uitbreiding_zonder_winst():
    transcript = [("hallo", 0.0, 0.5), ("wereld", 0.5, 1.0)]
    targets = song_text.extend_coupling("hallo", transcript, 0, claimed=set())
    assert targets == [0]


# -- B194/B209: zangstem-energie -------------------------------------------

def _write_wav(path, signal, sr=22050):
    import soundfile as sf
    sf.write(str(path), signal.astype(np.float32), sr)


def test_held_note_end_verlengt_tot_stilte(tmp_path):
    pytest.importorskip("librosa")
    sr = 22050
    # 2 s toon, dan 1 s stilte.
    show = 0.5 * np.sin(2 * np.pi * 220 * np.arange(2 * sr) / sr)
    silent = np.zeros(sr)
    signal = np.concatenate([show, silent])
    wav = tmp_path / "vocal.wav"
    _write_wav(wav, signal, sr)
    # Oorspronkelijk einde te vroeg (0.5 s), plafond ruim (2.8 s).
    end = rhythm.held_note_end(wav, start=0.0, floor_end=0.5, ceil_end=2.8)
    assert end is not None
    assert 1.7 <= end <= 2.4     # rond het einde van de toon


def test_held_note_end_binnen_grenzen(tmp_path):
    pytest.importorskip("librosa")
    sr = 22050
    signal = 0.5 * np.sin(2 * np.pi * 220 * np.arange(3 * sr) / sr)
    wav = tmp_path / "vocal.wav"
    _write_wav(wav, signal, sr)
    end = rhythm.held_note_end(wav, start=0.0, floor_end=0.5, ceil_end=1.5)
    assert end is not None
    assert end <= 1.5 + 1e-6      # nooit voorbij het plafond


def test_energy_onsets_vindt_pulsen(tmp_path):
    pytest.importorskip("librosa")
    sr = 22050
    # Vier korte pulsen (na-na-na-na) met stiltes ertussen, over 4 s.
    signal = np.zeros(4 * sr, dtype=np.float32)
    for k in range(4):
        start = int((0.2 + k) * sr)
        puls = 0.6 * np.sin(2 * np.pi * 300 *
                            np.arange(int(0.3 * sr)) / sr)
        signal[start:start + puls.size] += puls
    wav = tmp_path / "nanana.wav"
    _write_wav(wav, signal, sr)
    onsets = rhythm.energy_onsets(wav, 0.0, 4.0, expected=4)
    assert len(onsets) >= 3        # ten minste de meeste pulsen terug
    assert all(0.0 <= o <= 4.0 for o in onsets)


# -- B201: originele regel uit tekst ---------------------------------------

def test_timedline_from_text_verdeelt_gelijk():
    line = timing.timedline_from_text(0, "hallo wereld", 0.0, 2.0)
    assert line.text == "hallo wereld"
    assert line.syllables[0].start == 0.0
    assert abs(line.syllables[-1].end - 2.0) < 1e-6
    # oplopend
    times = [s.start for s in line.syllables]
    assert times == sorted(times)


# -- B202: klemtoon-timing uitlijnen ---------------------------------------

def _line(sylspec):
    syls = tuple(Syllable(text=t, start=s, end=e, held="nl", stress=n)
                 for t, s, e, n in sylspec)
    return TimedLine(index=0, text="".join(s[0] for s in sylspec),
                     crowd=False, syllables=syls)


def test_stress_fraction():
    line = _line([("a", 0.0, 1.0, False), ("b", 1.0, 2.0, True)])
    frac = timing.stress_fraction(line.syllables)
    assert abs(frac - 0.75) < 1e-6


def test_shift_stress_to_verschuift_en_behoudt_grenzen():
    line = _line([("a", 0.0, 1.0, False), ("b", 1.0, 2.0, True),
                  ("c", 2.0, 3.0, False)])
    verschoven = timing.shift_stress_to(line, target_rel=0.3)
    # regelbegin/eind en aantal blijven gelijk
    assert verschoven.syllables[0].start == 0.0
    assert abs(verschoven.syllables[-1].end - 3.0) < 1e-6
    assert len(verschoven.syllables) == 3
    # de beklemtoonde lettergreep is naar voren geschoven
    frac_na = timing.stress_fraction(verschoven.syllables)
    assert frac_na < 0.5


def test_align_karaoke_stress_gebruikt_mapping():
    karaoke = [_line([("ka", 0.0, 1.0, False), ("ra", 1.0, 2.0, True),
                      ("o", 2.0, 3.0, False)])]
    original = [_line([("o", 0.0, 1.0, True), ("ri", 1.0, 2.0, False)])]
    uit = timing.align_karaoke_stress(karaoke, original, {0: 0})
    # origineel-klemtoon ligt vooraan -> karaoke schuift naar voren
    assert timing.stress_fraction(uit[0].syllables) < \
        timing.stress_fraction(karaoke[0].syllables)


def test_align_karaoke_stress_laat_ongekoppeld_ongemoeid():
    karaoke = [_line([("a", 0.0, 1.0, False), ("b", 1.0, 2.0, True)])]
    uit = timing.align_karaoke_stress(karaoke, [], {})
    assert uit[0].syllables == karaoke[0].syllables


# -- B198: originele cellen dragen rows ------------------------------------

def test_original_view_cells_bevat_rows():
    originals = [{"text": "een twee", "start": 0.0, "end": 2.0, "rows": [3]}]
    cells = timing.original_view_cells(originals, "sentences")
    assert cells[0]["rows"] == [3]
    words = timing.original_view_cells(originals, "words")
    assert all(c["rows"] == [3] for c in words)


# -- B189: dubbele koppeling als één vak (Qt) ------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_koppel_merged_spans(qapp):
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
    # 0 en 1 vormen samen één vak; 2 niet.
    assert spans.get(0) == (0, 1)
    assert spans.get(1) == (0, 1)
    assert 2 not in spans


def test_timing_canvas_disable_vanuit_origineel(qapp):
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
