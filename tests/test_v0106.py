"""Tests voor v0.106.0: B341, B342, B345, B346 en B347.

B341 - de bezig-kleur komt op de knop die de taak start; sinds B323 nam
       elke stapknop opzij voor zijn eigen taak, want die draait al op
       het moment dat de haak aan de beurt is.
B342 - een woord dat op een segmentgrens is doorgeknipt komt twee keer
       uit Whisper en wordt weer samengevoegd; "amen" erbij in de
       Engelse hallucinatielijst.
B345 - in de timing-editor kan niets meer voorbij het eind van het
       nummer worden gesleept of gerekt.
B346 - regels, blokken en originele zinnen kunnen elkaar niet meer
       passeren (crowd mag nog wel overlappen).
B347 - bij een pauze binnen een regel verloren de laatste woorden hun
       hele duur, doordat de brokjes met een andere telling werden
       doorlopen dan waarmee ze zijn opgeslagen.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline  # noqa: E402
from modules.timing import (  # noqa: E402
    Syllable, TimedLine, distribute_over_windows, piece_groups, word_spans,
)
from modules.whisper import Segment, Word  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _context(tmp_path: Path, naam: str = "Proef"):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=naam)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B347: de woordtiming bij een pauze binnen de regel
# --------------------------------------------------------------------------

#: Precies zoals het in timing.json staat: fijnere brokjes dan de
#: lettergrepen die split_line uit de woordtekst haalt (25 om 10).
_BROKJES = ["I", "k", " g", "i", "ng", " a", "l", " j", "a", "r", "e", "n",
            " m", "e", "t", " d", "e", " R", "ei", "g", "e", "r", "s",
            " m", "ee"]


def _regel_met_pauze() -> TimedLine:
    stap = (86.351 - 81.031) / len(_BROKJES)
    syllables = tuple(
        Syllable(text=stuk, start=round(81.031 + i * stap, 3),
                 end=round(81.031 + (i + 1) * stap, 3))
        for i, stuk in enumerate(_BROKJES))
    return TimedLine(index=20, text="Ik ging al jaren met de Zangers mee",
                     crowd=False, syllables=syllables)


def test_piece_groups_telt_de_opgeslagen_brokjes() -> None:
    """B347: de groepering volgt de spatie, niet de woordtekst."""
    groepen = piece_groups(_regel_met_pauze().syllables)
    assert [len(g) for g in groepen] == [2, 3, 2, 5, 3, 2, 6, 2]
    assert sum(len(g) for g in groepen) == len(_BROKJES)


def test_geen_woord_verliest_zijn_duur_bij_een_pauze() -> None:
    """B347: vier van de acht woorden stonden op begin == eind."""
    vensters = [(81.031, 82.582), (84.686, 86.351)]
    uit = distribute_over_windows(_regel_met_pauze(), vensters)
    assert len(uit.syllables) == len(_BROKJES)
    for tekst, begin, eind in word_spans(uit.syllables):
        assert eind - begin > 0.001, f"{tekst} heeft geen duur"
        assert eind >= begin, f"{tekst} loopt achteruit"


def test_de_woorden_komen_in_de_gezongen_helften() -> None:
    """B347: de pauze hoort tussen de woorden te vallen, niet erin."""
    pauze = (82.582, 84.686)
    uit = distribute_over_windows(_regel_met_pauze(),
                                  [(81.031, 82.582), (84.686, 86.351)])
    woorden = word_spans(uit.syllables)
    assert len(woorden) == 8
    for _tekst, begin, eind in woorden:
        assert not (pauze[0] < begin < pauze[1]), "woord begint in de pauze"
        assert not (pauze[0] < eind < pauze[1]), "woord eindigt in de pauze"
    assert woorden[0][1] == pytest.approx(81.031, abs=0.01)
    assert woorden[-1][2] == pytest.approx(86.351, abs=0.01)


# --------------------------------------------------------------------------
# B345/B346: begrenzing en volgorde in de timing-editor
# --------------------------------------------------------------------------

_DUUR = 20.0


def _regels(aantal: int = 3) -> list[dict]:
    return [{"text": f"regel {i + 1}", "crowd": False, "block": 0,
             "disabled": False,
             "syllables": [{"text": "a", "start": 1.0 + 2 * i,
                            "end": 2.0 + 2 * i, "held": False,
                            "stress": False, "crowd": False}]}
            for i in range(aantal)]


def _span(regel: dict) -> tuple[float, float]:
    return (regel["syllables"][0]["start"], regel["syllables"][-1]["end"])


def _canvas(regels: list[dict], originals: list[dict] | None = None):
    import numpy as np
    from modules.timing_editor import TimingCanvas

    peaks = np.zeros(2000)
    canvas = TimingCanvas(peaks, peaks, _DUUR, regels, lambda *_: None,
                          originals=originals or [],
                          original_duration=_DUUR, vocal_peaks=peaks)
    canvas._cells = [{"text": r["text"], "start": _span(r)[0],
                      "end": _span(r)[1], "crowd": bool(r["crowd"]),
                      "rows": [i], "uit": False}
                     for i, r in enumerate(regels)]
    return canvas


def _sleep(canvas, cel: int, mode: str, vanaf: float, naar: float) -> None:
    """Eén sleepbeweging, zoals de muis hem aflevert."""
    from PySide6.QtCore import QPointF

    class _Gebeurtenis:
        def __init__(self, x: float) -> None:
            self._punt = QPointF(x, 0.0)

        def position(self):
            return self._punt

    canvas._drag = ("cel", cel, mode, vanaf)
    canvas.mouseMoveEvent(_Gebeurtenis(naar * canvas._pps))


def test_regel_kan_niet_voorbij_het_eind_worden_gerekt(qapp) -> None:
    """B345: rekken tot 80 s in een nummer van 20 s."""
    regels = _regels()
    _sleep(_canvas(regels), 2, "rechts", 6.0, 80.0)
    assert _span(regels[2])[1] == pytest.approx(_DUUR)


def test_regel_kan_niet_voorbij_het_eind_worden_gesleept(qapp) -> None:
    """B345: verplaatsen naar 200 s zette hem gewoon op 199,5."""
    regels = _regels()
    _sleep(_canvas(regels), 2, "verplaats", 5.5, 200.0)
    begin, eind = _span(regels[2])
    assert eind <= _DUUR + 1e-6
    assert eind - begin == pytest.approx(1.0)


def test_regel_kan_zijn_voorganger_niet_passeren(qapp) -> None:
    """B346: clamp_span liet hem in het vrije gat vóór regel 1 vallen."""
    regels = _regels()
    _sleep(_canvas(regels), 1, "verplaats", 3.5, 0.4)
    assert _span(regels[1])[0] >= _span(regels[0])[1] - 1e-6


def test_regel_kan_zijn_opvolger_niet_passeren(qapp) -> None:
    """B346: dezelfde regel, de andere kant op."""
    regels = _regels()
    _sleep(_canvas(regels), 0, "verplaats", 1.5, 9.0)
    assert _span(regels[0])[1] <= _span(regels[1])[0] + 1e-6


def test_blok_kan_zijn_buur_niet_passeren(qapp) -> None:
    """B346: in de blokweergave werd de overlapcontrole overgeslagen."""
    regels = _regels()
    canvas = _canvas(regels)
    canvas.set_view_mode("blocks")
    canvas._cells = [
        {"text": "blok 0", "start": 1.0, "end": 4.0, "crowd": False,
         "rows": [0, 1], "uit": False},
        {"text": "blok 1", "start": 5.0, "end": 6.0, "crowd": False,
         "rows": [2], "uit": False}]
    _sleep(canvas, 1, "verplaats", 5.5, 0.5)
    assert _span(regels[2])[0] >= _span(regels[1])[1] - 1e-6


def test_crowd_regel_mag_overlappen_maar_niet_passeren(qapp) -> None:
    """B346: 'nooit overlappen, crowd uitgezonderd' - passeren nooit."""
    regels = _regels()
    regels[2]["crowd"] = True
    _sleep(_canvas(regels), 2, "verplaats", 5.5, 0.5)
    begin, _eind = _span(regels[2])
    # Mag over regel 2 heen liggen ...
    assert begin < _span(regels[1])[1]
    # ... maar niet vóór het begin ervan uitkomen.
    assert begin >= _span(regels[1])[0] - 1e-6


def test_originele_zin_blijft_binnen_het_nummer_en_op_zijn_plek(qapp) -> None:
    """B345/B346 op de originele baan."""
    from PySide6.QtCore import QPointF

    regels = _regels()
    originals = [{"text": "o1", "start": 1.0, "end": 2.0, "rows": [0]},
                 {"text": "o2", "start": 3.0, "end": 4.0, "rows": [1]},
                 {"text": "o3", "start": 5.0, "end": 6.0, "rows": [2]}]
    canvas = _canvas(regels, originals)

    class _Gebeurtenis:
        def __init__(self, x: float) -> None:
            self._punt = QPointF(x, 0.0)

        def position(self):
            return self._punt

    canvas._drag = ("original", 2, "rechts", 6.0)
    canvas.mouseMoveEvent(_Gebeurtenis(90.0 * canvas._pps))
    assert originals[2]["end"] <= _DUUR + 1e-6

    canvas._drag = ("original", 1, "verplaats", 3.5)
    canvas.mouseMoveEvent(_Gebeurtenis(0.4 * canvas._pps))
    assert originals[1]["start"] >= originals[0]["end"] - 1e-6


# --------------------------------------------------------------------------
# B341: de bezig-kleur
# --------------------------------------------------------------------------

def test_knop_die_een_taak_start_wordt_geel(qapp, tmp_path) -> None:
    """B341: via een ECHTE klik, want daar zat het gat.

    De oude test riep ``_mark_busy_click`` rechtstreeks aan met een lege
    ``_worker`` en zag daarom niet dat de haak in werkelijkheid pas na de
    eigen handler aan de beurt komt - als de taak dus al draait.
    """
    import time

    from PySide6.QtWidgets import QPushButton

    from modules import gui

    window = gui.MainWindow(_context(tmp_path, "Bezig1"))
    knop = QPushButton("proef", window)
    knop.pressed.connect(window._remember_worker)
    knop.clicked.connect(
        lambda: window._run(lambda progress, message: time.sleep(0.2),
                            lambda _r: None))
    knop.clicked.connect(lambda _=False: window._mark_busy_click(knop))
    knop.click()
    try:
        assert window._worker.isRunning()
        assert knop in window._busy_buttons
        assert knop.styleSheet() != ""
    finally:
        window._worker.wait()


def test_knop_pakt_de_kleur_niet_af_van_een_lopende_taak(qapp,
                                                        tmp_path) -> None:
    """B323 blijft staan: andermans taak houdt de kleur."""
    from PySide6.QtWidgets import QPushButton

    from modules import gui

    window = gui.MainWindow(_context(tmp_path, "Bezig2"))
    bezig = window._step_buttons[0]

    class _Draait:
        def isRunning(self) -> bool:
            return True

    window._worker = _Draait()
    window._busy_buttons.add(bezig)
    window._apply_busy_style(bezig, True)

    andere = QPushButton("andere", window)
    window._remember_worker()          # de druk vóór de klik
    window._mark_busy_click(andere)
    assert andere not in window._busy_buttons
    assert bezig in window._busy_buttons


# --------------------------------------------------------------------------
# B342: het doorgeknipte woord op de segmentgrens
# --------------------------------------------------------------------------

def _segment(index: int, woorden: list[Word]) -> Segment:
    return Segment(index=index, text=" ".join(w.text for w in woorden),
                   start=woorden[0].start, end=woorden[-1].end,
                   words=tuple(woorden))


def test_doorgeknipt_woord_wordt_samengevoegd() -> None:
    """B342: de gemeten "reflections"/"Collections," van Lied D."""
    links = _segment(12, [Word("Golden", 81.031, 81.335, 0.516),
                          Word("reflections", 81.355, 81.740, 0.220)])
    rechts = _segment(13, [Word("Collections,", 81.760, 82.582, 0.622),
                           Word("given", 84.686, 85.127, 0.794)])
    uit = pipeline._merge_boundary_duplicates((links, rechts))
    assert [w.text for w in uit[0].words] == ["Golden"]
    assert uit[0].end == pytest.approx(81.335)
    eerste = uit[1].words[0]
    assert eerste.text == "Collections,"
    assert eerste.start == pytest.approx(81.355)   # de echte inzet
    assert eerste.end == pytest.approx(82.582)


def test_samengevoegd_woord_duurt_wat_het_elders_duurt() -> None:
    """B342: het bewijs dat het één woord is - 1,29 s tegen 1,31/1,36."""
    links = _segment(24, [Word("up,", 135.232, 135.695, 0.803),
                          Word("dreaming", 136.178, 136.420, 0.253)])
    rechts = _segment(25, [Word("Dreaming", 136.621, 137.466, 0.686),
                           Word("of", 137.869, 137.909, 0.000)])
    uit = pipeline._merge_boundary_duplicates((links, rechts))
    samen = uit[1].words[0]
    assert samen.end - samen.start == pytest.approx(1.288, abs=0.005)


def test_echte_herhaling_blijft_staan() -> None:
    """B342: "Tickle, tickle" staat binnen één segment en blijft heel."""
    segment = _segment(8, [Word("Tickle,", 56.680, 57.560, 0.640),
                           Word("tickle,", 57.621, 57.981, 0.490)])
    uit = pipeline._merge_boundary_duplicates((segment,))
    assert len(uit[0].words) == 2


def test_groot_gat_wordt_niet_samengevoegd() -> None:
    """B342: 0,70 s stilte binnen een woord proppen is geen winst."""
    links = _segment(1, [Word("I'm", 40.0, 40.2, 0.700),
                         Word("sure", 40.30, 40.38, 0.010)])
    rechts = _segment(2, [Word("sure.", 41.082, 41.802, 0.620)])
    uit = pipeline._merge_boundary_duplicates((links, rechts))
    assert [w.text for w in uit[0].words] == ["I'm", "sure"]
    assert uit[1].words[0].start == pytest.approx(41.082)


def test_zeker_woord_wordt_niet_als_stompje_gezien() -> None:
    """B342: alleen een korter EN onzekerder woord telt als stompje."""
    links = _segment(1, [Word("oh", 10.0, 10.4, 0.900),
                         Word("no", 10.5, 11.2, 0.880)])
    rechts = _segment(2, [Word("No", 11.30, 11.60, 0.910)])
    uit = pipeline._merge_boundary_duplicates((links, rechts))
    assert len(uit[0].words) == 2


def test_amen_staat_in_de_engelse_hallucinatielijst() -> None:
    """B342: 0,11 s, betrouwbaarheid 0,032, twee tellen na de zang."""
    from modules import phonetics

    assert "amen" in phonetics.word_list("en", "hallucinations")
    assert "amen" not in phonetics.word_list("nl", "hallucinations")
