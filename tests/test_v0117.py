"""Tests voor v0.117.0: B368 t/m B371.

B368 de secondeteller bleef steken op 361 s terwijl 1.5.10 nog liep.
B369 de uitslag van elke actie wordt meteen weggeschreven, niet pas aan
     het eind van de hele reeks - en de crashbestendige kant gaat
     rechtstreeks naar het logbestand.
B370 de duur per actie in de meethistorie, want de logbestanden gaan na
     vijf dagen weg.
B371 1.5.11 als zware bak: buiten de knop 'alle', onzichtbaar als er
     niets onder zit, met een versiedrempel per onderzoek.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import model_register, test_history, test_panel  # noqa: E402
from modules.translations import TRANSLATIONS  # noqa: E402

WORTEL = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _schoon(tmp_path, monkeypatch):
    monkeypatch.setattr(test_history, "HISTORY_FILE",
                        tmp_path / "testhistorie.json")
    monkeypatch.setattr(test_panel, "COMBINATION_REPORT",
                        tmp_path / "modelcombinaties.md")
    yield
    model_register.restore_all()
    model_register.apply_settings({})
    test_panel.REMEASURE = False


def _context(tmp_path: Path, naam: str = "Proef"):
    from dataclasses import replace

    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=naam)
    ensure_directories(paths)
    config = default_config()
    config = replace(config, song=replace(config.song, title=naam))
    return pipeline.AppContext(paths=paths, config=config,
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B368 - de bevroren secondeteller
# --------------------------------------------------------------------------

def test_de_hoofdbalk_is_dezelfde_als_de_eerste_testbalk(qapp,
                                                         tmp_path) -> None:
    """Dit is de val waar B368 in liep; hij bestaat nog steeds.

    De teller mag er daarom niet meer op leunen - vandaar deze test:
    verdwijnt die gedeelde balk ooit, dan mag deze test omvallen en kan
    de eigen toestand weer weg.
    """
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    assert window._progress is window._progress_bars[0]


def test_de_teller_leunt_niet_meer_op_een_balk() -> None:
    from modules import gui

    bron = inspect.getsource(gui.MainWindow._tick_elapsed)
    assert "_show_elapsed" in bron
    assert "maximum()" not in bron, \
        "de teller mag niet meer aan het maximum van een balk hangen"


def test_de_teller_blijft_lopen_als_het_testpaneel_meldt(qapp,
                                                         tmp_path) -> None:
    """Precies het geval van 361 s: de meetlat zet een projectteller op
    balk nul en de seconden stonden stil."""
    import time

    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    window._set_busy(True)
    window._phase_start = time.monotonic() - 42
    # B402: een werkplekmelding raakt balk nul niet meer; de val zit nu
    # in de ACTIEmelding, en die zet balk nul wel degelijk op een bereik.
    window._on_test_progress(window.ACTION_SLOT, "1.5.10", 3, 13)
    assert window._progress.maximum() == 13      # de val staat er nog
    window._tick_elapsed()
    assert "42" in window._status.text(), window._status.text()


def test_een_echt_percentage_zet_de_teller_wel_stil(qapp, tmp_path) -> None:
    """Met een percentage is de teller overbodig; die mag dan zwijgen."""
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    window._set_busy(True)
    window._on_progress(5.0, 10.0)
    assert window._show_elapsed is False


# --------------------------------------------------------------------------
# B369 - de uitslag meteen wegschrijven
# --------------------------------------------------------------------------

def test_de_loper_schrijft_per_actie_weg() -> None:
    from modules import gui

    bron = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "_test_result.emit" in bron
    # Het logbestand eerst: dat is het deel dat een crash overleeft.
    assert bron.index("logger.info(t(\"log_gui\")") < \
        bron.index("_test_result.emit")


def test_on_done_dumpt_de_stapel_niet_nog_een_keer() -> None:
    from modules import gui

    bron = inspect.getsource(gui.MainWindow._do_fill_cache)
    staart = bron[bron.index("def on_done"):]
    assert "splitlines()" not in staart, "dan staat alles dubbel"


def test_het_venster_logt_niet_nog_eens_naar_het_bestand() -> None:
    """De werkthread heeft de regels al weggeschreven."""
    from modules import gui

    bron = inspect.getsource(gui.MainWindow._on_test_result)
    assert "_log_view_only" in bron
    assert "logger" not in inspect.getsource(gui.MainWindow._log_view_only)


def test_de_uitslag_gaat_via_een_signaal() -> None:
    """Uit een werkthread mag geen Qt-widget worden aangeraakt."""
    from modules import gui

    assert hasattr(gui.MainWindow, "_test_result")


# --------------------------------------------------------------------------
# B370 - de duur in de historie
# --------------------------------------------------------------------------

def test_de_duur_van_een_actie_wordt_bewaard(tmp_path) -> None:
    test_history.remember_duration("1.5.10", "0.117.0", 1673.0)
    assert test_history.durations("1.5.10") == [("0.117.0", 1673.0)]


def test_de_duur_per_project_gaat_mee(tmp_path) -> None:
    test_history.remember("1.5.5", "Lied", "0.1.0", "abc", {"x": 1},
                          seconds=2.5)
    ingang = test_history.history("1.5.5", "Lied")[-1]
    assert ingang["seconds"] == 2.5


def test_de_verdeler_meet_de_duur_per_project(tmp_path) -> None:
    context = _context(tmp_path)
    test_panel.with_history(context, ["Proef"], lambda s: {"x": 1},
                            lambda *a, **k: None, lambda: False, "1.5.9")
    ingang = test_history.history("1.5.9", "Proef")[-1]
    assert "seconds" in ingang


def test_het_programma_zeurt_niet_over_de_duur() -> None:
    """De gebruiker vroeg het getal te bewaren, niet om een melding.

    De vraag "hoort dit in 1.5.11?" wordt gesteld bij de analyse op de
    data, niet door de app zelf.
    """
    bron = (WORTEL / "modules" / "test_panel.py").read_text(encoding="utf-8")
    assert "30 min" not in bron and "1800" not in bron


def test_de_versieafstand_telt_het_middelste_getal(tmp_path) -> None:
    """0.110.1 is een reparatie, geen eigen versie."""
    assert test_history.version_number("0.116.0") == 116
    assert test_history.version_number("0.110.1") == 110
    test_history.remember_duration("1.5.11a", "0.100.0", 1.0)
    assert test_history.versions_ago("1.5.11a", "0.120.0") == 20
    assert test_history.versions_ago("1.5.11a", "0.101.0") == 1


def test_nooit_gedraaid_betekent_gewoon_doen(tmp_path) -> None:
    assert test_history.versions_ago("1.5.11b", "0.117.0") is None


# --------------------------------------------------------------------------
# B371 - de zware bak
# --------------------------------------------------------------------------

def test_de_zware_actie_staat_buiten_het_plafond_van_tien() -> None:
    meetacties = [a for a in test_panel.ACTIONS
                  if not a.heavy and not a.on_request]
    heavy = [a for a in test_panel.ACTIONS if a.heavy]
    klussen = [a for a in test_panel.ACTIONS if a.on_request]
    # B526: negen sinds 1.5.8 weg is; het plafond blijft tien.
    # B531: 1.5.12 is een klus en telt niet mee voor dat plafond.
    assert len(meetacties) == 9 <= test_panel.MAX_ACTIONS
    assert [a.code for a in heavy] == ["1.5.11"]
    assert [a.code for a in klussen] == ["1.5.12"]


def test_alles_aanvinken_slaat_de_zware_over(qapp) -> None:
    """Uren rekenen hoort een bewuste keuze te zijn, ook bij 'alles'."""
    paneel = test_panel.TestPanel()
    paneel._toggle_all()
    assert all(not a.heavy for a in paneel.chosen())
    assert len(paneel.chosen()) == 9


def test_de_zware_actie_is_wel_los_aan_te_vinken(qapp) -> None:
    paneel = test_panel.TestPanel()
    heavy = [n for n, a in enumerate(paneel._actions) if a.heavy]
    assert heavy, "1.5.11 hoort zichtbaar te zijn nu er proeven onder staan"
    paneel._ticks[heavy[0]].setChecked(True)
    assert [a.code for a in paneel.chosen()] == ["1.5.11"]


def test_zonder_onderzoeken_verdwijnt_de_zware_actie(qapp,
                                                     monkeypatch) -> None:
    """Geen lege regel en geen uitgegrijsde knop."""
    monkeypatch.setattr(test_panel, "HEAVY_TRIALS", ())
    assert all(not a.heavy for a in test_panel.visible_actions())
    paneel = test_panel.TestPanel()
    gewoon = [a for a in test_panel.visible_actions()
              if not a.heavy and not a.on_request]
    assert len(gewoon) == 9
    # B531: 1.5.12 blijft wel staan - die hangt niet aan de onderzoeken.
    assert len(paneel._ticks) == 10
    assert "1.5.11" not in " ".join(v.text() for v in paneel._ticks)
    assert "1.5.12" in " ".join(v.text() for v in paneel._ticks)


def test_elk_zwaar_onderzoek_heeft_een_drempel() -> None:
    """B452: de drempel op versies is eruit - die hield precies de twee
    proeven tegen die moesten draaien. Wat blijft is de vorm."""
    for proef in test_panel.HEAVY_TRIALS:
        assert not hasattr(proef, "threshold")
        assert proef.code.startswith("1.5.11")
        for taal in ("nl", "en"):
            assert TRANSLATIONS[taal].get(proef.name_key, "").strip()


def test_een_al_gemeten_onderzoek_wordt_overgeslagen(tmp_path) -> None:
    """B452: één keer per versie per stand, zoals de rest van het paneel."""
    context = _context(tmp_path)
    for proef in test_panel.HEAVY_TRIALS:
        test_panel._remember_heavy(context, proef.code, 1.0)
    uitkomst = test_panel.heavy_trial(context, lambda *a, **k: None,
                                      lambda: False)
    tekst = test_panel.COMBINATION_REPORT.read_text(encoding="utf-8")
    assert isinstance(uitkomst, str)
    aan = [p for p in test_panel.HEAVY_TRIALS if not p.off]
    assert tekst.count("Al gemeten") == len(aan)
    assert tekst.count("Uitgezet") == len(test_panel.HEAVY_TRIALS) - len(aan)


def test_opnieuw_meten_dwingt_een_zwaar_onderzoek_af(tmp_path,
                                                     monkeypatch) -> None:
    from modules import __version__

    for proef in test_panel.HEAVY_TRIALS:
        test_history.remember_duration(proef.code, __version__, 1.0)
    monkeypatch.setattr(test_panel, "REMEASURE", True)
    test_panel.heavy_trial(_context(tmp_path), lambda *a, **k: None,
                           lambda: False)
    tekst = test_panel.COMBINATION_REPORT.read_text(encoding="utf-8")
    assert "Overgeslagen" not in tekst


def test_de_zware_proef_stopt_op_de_stopknop(tmp_path) -> None:
    uitkomst = test_panel.heavy_trial(_context(tmp_path),
                                      lambda *a, **k: None, lambda: True)
    assert isinstance(uitkomst, str)


# --------------------------------------------------------------------------
# De clusters
# --------------------------------------------------------------------------

def test_clusters_koppelen_alleen_echte_wisselwerkingen() -> None:
    paren = [("A", "B", 2.00), ("B", "C", 0.30), ("D", "E", 0.01),
             ("F", "G", -0.50)]
    groepen = test_panel.clusters_from_pairs(paren)
    assert {"A", "B", "C"} in groepen
    assert {"F", "G"} in groepen
    assert not any("D" in g or "E" in g for g in groepen), \
        "0.01 s is ruis, geen wisselwerking"


def test_een_cluster_van_zes_is_vierenzestig_metingen() -> None:
    """De hele reden dat dit betaalbaar is: 2^6 + 2^2 = 68 in plaats
    van 2^17 = 131.072."""
    paren = [(f"M{n}", f"M{n + 1}", 1.0) for n in range(5)]
    groep = test_panel.clusters_from_pairs(paren)[0]
    assert len(groep) == 6 and 2 ** len(groep) == 64


def test_zonder_modelmatrix_wordt_er_niet_gegokt(tmp_path,
                                                 monkeypatch) -> None:
    """Op de clusters gokken zou de hele proef waardeloos maken."""
    monkeypatch.setattr(test_panel, "MATRIX_REPORT",
                        tmp_path / "bestaat_niet.md")
    with pytest.raises(test_panel.TrialSkipped) as val:
        test_panel.cluster_trial(_context(tmp_path),
                                 lambda *a, **k: None, lambda: False)
    assert val.value.lines == [TRANSLATIONS["nl"]["heavy_needs_matrix"]]


def test_de_paren_komen_uit_het_verslag_van_1_5_10(tmp_path,
                                                   monkeypatch) -> None:
    """Opnieuw meten zou een half uur kosten; ze staan er al."""
    verslag = tmp_path / "modelmatrix.md"
    verslag.write_text(
        "## Twee tegelijk anders\n\n"
        "| model A | model B | samen | los opgeteld | verschil |\n"
        "| --- | --- | ---: | ---: | ---: |\n"
        "| B329 ankertoets | B313 energie | 5.66 s | 3.66 s | +2.00 |\n"
        "| B334 lus | B342 grens | 3.25 s | 3.25 s | +0.00 |\n",
        encoding="utf-8")
    monkeypatch.setattr(test_panel, "MATRIX_REPORT", verslag)
    paren = test_panel._pairs_from_report()
    assert len(paren) == 2
    groepen = test_panel.clusters_from_pairs(paren)
    assert groepen == [{"B329 ankertoets", "B313 energie"}]


# --------------------------------------------------------------------------
# De zoektocht houdt liedjes achter
# --------------------------------------------------------------------------

def test_de_zoektocht_houdt_liedjes_achter() -> None:
    """Met 131.072 standen en 188 regels vind je gegarandeerd ruis."""
    bron = inspect.getsource(test_panel.search_trial)
    assert "_HELD_BACK" in bron
    assert "heavy_search_overfit" in bron, \
        "een te mooie uitslag op de zoekset moet gemeld worden"


def test_te_weinig_projecten_geeft_geen_uitslag(tmp_path) -> None:
    with pytest.raises(test_panel.TrialSkipped) as val:
        test_panel.search_trial(_context(tmp_path), lambda *a, **k: None,
                                lambda: False)
    assert len(val.value.lines) == 1


def test_de_zoektocht_is_herhaalbaar() -> None:
    """Een vaste reeks, anders geeft dezelfde meting twee antwoorden."""
    bron = inspect.getsource(test_panel.search_trial)
    assert "random.Random(" in bron


def test_alle_nieuwe_teksten_staan_in_beide_talen() -> None:
    for sleutel in ("test_heavy", "test_heavy_hint", "heavy_intro",
                    "heavy_clusters", "heavy_search", "heavy_cluster_intro",
                    "heavy_cluster_too_big", "heavy_needs_matrix",
                    "heavy_no_clusters", "heavy_search_intro",
                    "heavy_search_split", "heavy_search_verdict",
                    "heavy_search_overfit", "heavy_too_few_songs",
                    "heavy_already", "heavy_not_chosen",
                    "heavy_switched_off", "heavy_done", "log_test_result"):
        for taal in ("nl", "en"):
            assert TRANSLATIONS[taal].get(sleutel, "").strip(), \
                f"{sleutel} ({taal})"
