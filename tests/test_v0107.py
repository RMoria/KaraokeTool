"""Tests voor v0.107.0: B339, B340, B343 en B348.

B339 - regelmarkering onder de songtekstrij van de koppel-editor.
B340 - een reeks ankers die veel dichter op elkaar staat dan de frase
       kan niet in zijn geheel kloppen; alleen de buitenste twee blijven.
B343 - een woord van twintig milliseconden met betrouwbaarheid 0,004 is
       geen woord en mag zeker geen zinsbegin worden.
B348 - de meetlat voerde de koppeling de RUWE transcriptie terwijl de
       app op de uitgelijnde cache draait.
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

WORTEL = Path(__file__).resolve().parents[1]


def _segment(index: int, woorden: list[Word]) -> Segment:
    return Segment(index=index, text=" ".join(w.text for w in woorden),
                   start=woorden[0].start, end=woorden[-1].end,
                   words=tuple(woorden))


# --------------------------------------------------------------------------
# B343: spookwoorden
# --------------------------------------------------------------------------

def test_spookwoord_gaat_eruit() -> None:
    """De gemeten 'I' van 0,020 s met betrouwbaarheid 0,004."""
    segment = _segment(2, [Word("I", 16.446, 16.466, 0.004),
                           Word("don't", 18.829, 18.989, 0.569),
                           Word("know", 19.029, 19.209, 0.910)])
    uit = pipeline._drop_phantom_words((segment,))
    assert [w.text for w in uit[0].words] == ["don't", "know"]
    # Het segment begint nu waar het echt begint - dat is de winst.
    assert uit[0].start == pytest.approx(18.829)


def test_kort_maar_zeker_woord_blijft() -> None:
    """Duur alleen zegt niets: 'a' van 0,040 s scoort 0,952."""
    segment = _segment(3, [Word("a", 143.174, 143.214, 0.952),
                           Word("fantasy", 143.3, 143.9, 0.7)])
    uit = pipeline._drop_phantom_words((segment,))
    assert len(uit[0].words) == 2


def test_onzeker_maar_lang_woord_blijft() -> None:
    """En betrouwbaarheid alleen ook niet - beide voorwaarden tellen."""
    segment = _segment(4, [Word("shoes", 139.418, 140.100, 0.055),
                           Word("now", 140.2, 140.6, 0.8)])
    uit = pipeline._drop_phantom_words((segment,))
    assert len(uit[0].words) == 2


def test_segment_dat_alleen_spook_bevat_verdwijnt() -> None:
    segment = _segment(5, [Word("I", 60.082, 60.102, 0.006)])
    assert pipeline._drop_phantom_words((segment,)) == ()


def test_spookfilter_zit_in_het_leespad() -> None:
    """Bestaande projecten profiteren zonder opnieuw te transcriberen."""
    bron = (WORTEL / "modules" / "pipeline.py").read_text(encoding="utf-8")
    kop = bron[bron.index("def load_segments("):]
    lijf = kop[:kop.index("\n\n\ndef ")]
    for naam in ("_drop_phantom_words", "_merge_boundary_duplicates",
                 "_drop_repetition_loop"):
        assert naam in lijf, f"{naam} hangt niet in load_segments"


# --------------------------------------------------------------------------
# B340: opgepropte ankers
# --------------------------------------------------------------------------

def _regel(index: int, start: float, eind: float) -> TimedLine:
    return TimedLine(index=index, text=f"regel {index}", crowd=False,
                     syllables=(Syllable(text="la", start=start, end=eind),),
                     quality="high")


def _binnenkant(regels, ankers, periode) -> set:
    """Wie er van een opgepropte reeks af moet (B340/B535)."""
    return {i for reeks in _packed_runs(regels, ankers, periode)
            for i in reeks[1:-1]}


def test_opgepropte_reeks_verliest_zijn_binnenste_ankers() -> None:
    """Vier ankers op een derde seconde bij een frase van 3,5 s."""
    regels = [_regel(i, 10.0 + 0.33 * i, 10.3 + 0.33 * i) for i in range(4)]
    verdacht = _binnenkant(regels, list(range(4)), 3.5)
    assert verdacht == {1, 2}


def test_normale_afstand_blijft_ongemoeid() -> None:
    regels = [_regel(i, 10.0 + 3.5 * i, 13.0 + 3.5 * i) for i in range(4)]
    assert _binnenkant(regels, list(range(4)), 3.5) == set()


def test_twee_dicht_op_elkaar_is_geen_reeks() -> None:
    """Twee kort achter elkaar kan gewoon een tussenroepsel zijn."""
    regels = [_regel(0, 10.0, 10.3), _regel(1, 10.4, 10.7),
              _regel(2, 20.0, 23.0)]
    assert _binnenkant(regels, [0, 1, 2], 3.5) == set()


def test_zonder_periode_gebeurt_er_niets() -> None:
    """Zeven van de tien projecten leveren geen betrouwbare periode."""
    regels = [_regel(i, 10.0 + 0.33 * i, 10.3 + 0.33 * i) for i in range(4)]
    assert _binnenkant(regels, list(range(4)), None) == set()


# --------------------------------------------------------------------------
# B339: regelmarkering in de koppel-editor
# --------------------------------------------------------------------------

def test_regelmarkering_staat_op_elke_regelovergang(qapp=None) -> None:
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from modules.coupling_editor import CouplingCanvas

    woorden = [{"index": i, "text": tekst, "line": regel, "sim": 0.9,
                "pinned": False, "transcript_indices": [i],
                "status": "coupled"}
               for i, (tekst, regel) in enumerate(
                   [("nu", 0), ("nu", 0), ("nu", 1), ("nu", 1), ("nu", 2)])]
    transcript = [("nu", float(i), float(i) + 0.2) for i in range(5)]
    canvas = CouplingCanvas(transcript, woorden, on_change=lambda _d: None)
    assert [nummer for nummer, _col in canvas.line_marker_columns()] \
        == [0, 1, 2]


# --------------------------------------------------------------------------
# B348: de meetlat neemt de cache
# --------------------------------------------------------------------------

def test_meetlat_neemt_de_cache_boven_de_ruwe_kopie(tmp_path) -> None:
    """De app koppelt op de cache (na forced alignment), dus de meting ook."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "regressie", WORTEL / "tools" / "timing_regression.py")
    regressie = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regressie)

    lied = "Proef"
    project = tmp_path / "output" / lied
    (project / "settings").mkdir(parents=True)
    (project / "original").mkdir(parents=True)
    (tmp_path / "input" / lied).mkdir(parents=True)
    (tmp_path / "input" / lied / "songtekst.txt").write_text(
        "een twee\n", encoding="utf-8")
    (project / "settings" / "project.json").write_text(
        json.dumps({"steps": {}}), encoding="utf-8")

    def segmenten(start: float) -> str:
        return json.dumps([{"index": 0, "text": "een", "start": start,
                            "end": start + 1.0,
                            "words": [{"text": "een", "start": start,
                                       "end": start + 1.0, "conf": 0.9}]}])

    (project / "original" / "segmenten.json").write_text(
        segmenten(10.660), encoding="utf-8")

    # Zonder cache valt hij terug op de ruwe kopie ...
    context = regressie._build_project(project, tmp_path / "werk1")
    bewaard = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    assert json.loads(bewaard.read_text())[0]["start"] == pytest.approx(10.660)
    assert regressie.SOURCE[lied] == "ruw"

    # ... en met cache neemt hij die, want dat is wat de app leest.
    cache = tmp_path / "cache" / lied
    cache.mkdir(parents=True)
    (cache / "transcription_original.json").write_text(
        segmenten(11.201), encoding="utf-8")
    context = regressie._build_project(project, tmp_path / "werk2")
    bewaard = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    assert json.loads(bewaard.read_text())[0]["start"] == pytest.approx(11.201)
    assert regressie.SOURCE[lied] == "cache"
