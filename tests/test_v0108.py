"""Tests voor v0.108.0 en v0.109.0: B349, B350, B351 en B352.

B349 - de voortgang toonde het percentage twee keer: één keer in de balk
       zelf en één keer in de tekst ernaast.
B350 - melding als er met hoge zekerheid iets is gehoord dat niet in de
       songtekst staat, met onderscheid tussen een ontbrekende herhaling
       en onbekende tekst.
B351 - een regel die achter een pauze begint, begint te laat: het anker
       komt uit de uitlijning en die zet het woordbegin ná de inzet van
       de zang.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline  # noqa: E402
from modules.timing import (  # noqa: E402
    Syllable, TimedLine, _onset_before_start, snap_to_onsets,
)
from modules.translations import TRANSLATIONS  # noqa: E402

WORTEL = Path(__file__).resolve().parents[1]


def _regel(index: int, start: float, eind: float,
           kwaliteit: str = "high") -> TimedLine:
    return TimedLine(index=index, text=f"regel {index}", crowd=False,
                     syllables=(Syllable(text="la", start=start, end=eind),),
                     quality=kwaliteit)


# --------------------------------------------------------------------------
# B349: het percentage stond er twee keer
# --------------------------------------------------------------------------

def test_voortgangstekst_heeft_geen_percentage_meer() -> None:
    """De balk toont zelf al '20%'; de tekst ernaast houdt de seconden."""
    for taal in ("nl", "en"):
        tekst = TRANSLATIONS[taal]["progress_pct"]
        assert "%" not in tekst, f"{taal} toont het percentage nog een keer"
        assert "{done" in tekst and "{total" in tekst


def test_voortgangstekst_verdraagt_de_oude_aanroep() -> None:
    """``pct`` wordt nog meegegeven; een ongebruikte sleutel mag."""
    tekst = TRANSLATIONS["nl"]["progress_pct"].format(
        pct=20, done=12.0, total=60.0)
    assert tekst == "Voortgang: 12 / 60 s"


# --------------------------------------------------------------------------
# B351: het begin achter een pauze
# --------------------------------------------------------------------------

def test_anker_achter_een_pauze_gaat_naar_de_inzet() -> None:
    """Gemeten geval: begin op 151,46 terwijl de zang op 150,98 inzet."""
    regel = _regel(1, 151.46, 154.0)
    inzet = _onset_before_start(regel, previous_end=149.0,
                                ordered=[145.0, 150.98, 151.60])
    assert inzet == pytest.approx(150.98)


def test_zonder_pauze_blijft_het_anker_staan() -> None:
    """Aansluitende regels zijn juist goed - daar valt niets te winnen."""
    regel = _regel(1, 151.46, 154.0)
    assert _onset_before_start(regel, previous_end=151.20,
                               ordered=[150.98, 151.60]) is None


def test_klein_verschil_blijft_ongemoeid() -> None:
    """Regels die de gebruiker liet staan zitten 0,10-0,23 s achter hun
    inzet; die drempel houdt ze met rust."""
    regel = _regel(1, 151.46, 154.0)
    assert _onset_before_start(regel, previous_end=149.0,
                               ordered=[151.30]) is None


def test_nooit_verder_terug_dan_de_vorige_regel() -> None:
    regel = _regel(1, 151.46, 154.0)
    assert _onset_before_start(regel, previous_end=151.0,
                               ordered=[150.50]) is None


def test_snap_verzet_een_gemeten_regel_achter_een_pauze() -> None:
    """Het hele pad: B330 laat gemeten regels staan, B351 maakt hierop
    één uitzondering."""
    lijnen = (_regel(0, 140.0, 149.0), _regel(1, 151.46, 154.0))
    uit = snap_to_onsets(lijnen, [150.98], period=None)
    assert uit[0].start == pytest.approx(140.0)      # ongemoeid
    assert uit[1].start == pytest.approx(150.98)
    assert uit[1].end == pytest.approx(154.0)        # eind blijft staan


def test_snap_laat_een_aansluitende_gemeten_regel_met_rust() -> None:
    lijnen = (_regel(0, 140.0, 151.20), _regel(1, 151.46, 154.0))
    uit = snap_to_onsets(lijnen, [150.98], period=None)
    assert uit[1].start == pytest.approx(151.46)


# --------------------------------------------------------------------------
# B350: melding over wat er is gehoord maar niet in de songtekst staat
# --------------------------------------------------------------------------

def _project(tmp_path: Path, songtekst: str, karaoketekst: str,
             segmenten: list[dict]):
    import json

    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    (paths.input_dir / "songtekst.txt").write_text(songtekst,
                                                   encoding="utf-8")
    (paths.input_dir / "karaoketekst.txt").write_text(karaoketekst,
                                                      encoding="utf-8")
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    cache = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(segmenten), encoding="utf-8")
    context.store.set_step("whisper_original", {"segments": len(segmenten)})
    return context


def _segment(index: int, woorden: list[tuple[str, float, float, float]]
             ) -> dict:
    return {"index": index, "text": " ".join(w[0] for w in woorden),
            "start": woorden[0][1], "end": woorden[-1][2],
            "words": [{"text": t, "start": s, "end": e, "confidence": c}
                      for t, s, e, c in woorden]}


def test_ontbrekende_herhaling_wordt_gemeld(tmp_path) -> None:
    """Het gemeten geval: de zang doet het paar twee keer, de tekst één."""
    context = _project(
        tmp_path,
        "shalalie shalala\nja ik weet het alweer\n",
        "biertje hier\nen morgen nog een keer\n",
        [_segment(0, [("shalalie", 10.0, 10.7, 0.7),
                      ("shalala", 10.7, 11.4, 0.7),
                      ("shalalie", 11.4, 12.1, 0.7),
                      ("shalala", 12.1, 12.9, 0.7),
                      ("ja", 13.0, 13.2, 0.9),
                      ("ik", 13.2, 13.4, 0.9),
                      ("weet", 13.4, 13.7, 0.9),
                      ("het", 13.7, 13.9, 0.9),
                      ("alweer", 13.9, 14.4, 0.9)])])
    gemeld = pipeline.missing_repetitions(context)
    assert [m["repetition"] for m in gemeld] == [True]
    assert gemeld[0]["text"].lower().startswith("shalalie")
    assert gemeld[0]["similarity"] >= 0.9


def test_kloppende_tekst_geeft_geen_melding(tmp_path) -> None:
    context = _project(
        tmp_path,
        "shalalie shalala shalalie shalala\nja ik weet het alweer\n",
        "Lied C\nen morgen nog een keer\n",
        [_segment(0, [("shalalie", 10.0, 10.7, 0.7),
                      ("shalala", 10.7, 11.4, 0.7),
                      ("shalalie", 11.4, 12.1, 0.7),
                      ("shalala", 12.1, 12.9, 0.7),
                      ("ja", 13.0, 13.2, 0.9),
                      ("ik", 13.2, 13.4, 0.9),
                      ("weet", 13.4, 13.7, 0.9),
                      ("het", 13.7, 13.9, 0.9),
                      ("alweer", 13.9, 14.4, 0.9)])])
    assert [m for m in pipeline.missing_repetitions(context)
            if m["repetition"]] == []


def test_onzeker_woord_levert_geen_melding(tmp_path) -> None:
    """Onder de drempel is het gemompel aan het eind van een regel."""
    context = _project(
        tmp_path,
        "shalalie shalala\nja ik weet het alweer\n",
        "biertje hier\nen morgen nog een keer\n",
        [_segment(0, [("shalalie", 10.0, 10.7, 0.7),
                      ("shalala", 10.7, 11.4, 0.7),
                      ("shalalie", 11.4, 12.1, 0.900),
                      ("shalala", 12.1, 12.9, 0.05),
                      ("ja", 13.0, 13.2, 0.9),
                      ("ik", 13.2, 13.4, 0.9),
                      ("weet", 13.4, 13.7, 0.9),
                      ("het", 13.7, 13.9, 0.9),
                      ("alweer", 13.9, 14.4, 0.9)])])
    gemeld = pipeline.missing_repetitions(context)
    assert all(m["similarity"] >= 0.9 or not m["repetition"] for m in gemeld)


def test_melding_hangt_achter_de_koppel_editor(tmp_path) -> None:
    """De controle draait na 1.2, want daar wordt de koppeling gemaakt."""
    bron = (WORTEL / "modules" / "gui.py").read_text(encoding="utf-8")
    kop = bron[bron.index("def _open_word_couple("):]
    lijf = kop[:kop.index("\n    def _report_missing(")]
    assert "_report_missing" in lijf
    assert "missing_repetitions" in bron


# --------------------------------------------------------------------------
# B352: de meetlat gaf de zangvensters niet door
# --------------------------------------------------------------------------

def test_meetlat_geeft_de_zangvensters_mee() -> None:
    """De app doet dat wel, dus alles wat erop leunt werd nooit gemeten."""
    bron = (WORTEL / "tools" / "timing_regression.py").read_text(
        encoding="utf-8")
    aanroep = bron[bron.index("sanitize_timing("):]
    aanroep = aanroep[:aanroep.index(")\n")]
    assert "active_windows" in aanroep
    app = (WORTEL / "modules" / "pipeline.py").read_text(encoding="utf-8")
    assert "active_windows=_vocal_windows(context)" in app
