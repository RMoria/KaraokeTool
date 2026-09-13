"""Tests voor v0.114.0: B359 (de GUI liep vast op een SystemExit).

De gebruiker startte 1.5.9, er gebeurde niets meer, en er was geen CPU-
activiteit. Het logboek eindigde met "1.5.9 draait" en daarna niets: geen
fout, geen volgende actie, niets. De werkthread was stil doodgegaan.

``SystemExit`` erft van ``BaseException`` en niet van ``Exception``, dus
hij glipte door alle drie de vangnetten (de actie zelf, de lus over de
acties, en ``_Worker.run``). Omdat ``run()`` klapte werd géén van de
signalen ``done``/``failed``/``cancelled`` verstuurd, bleef
``_set_busy(False)`` achterwege en hing het venster voorgoed op "bezig".

Drie reparaties plus een die er los van staat maar dezelfde oorzaak had
(de keuzerondjes deden niets).
"""
from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import test_panel  # noqa: E402
from modules.translations import TRANSLATIONS  # noqa: E402

WORTEL = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _context(tmp_path: Path, naam: str = "Proef"):
    """Een context waarin ``naam`` ook echt het GEKOZEN project is.

    De titel in de instellingen is wat de app "het huidige project"
    noemt; hij staat los van de paden. Precies dat verschil ging mis.
    """
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


@pytest.fixture(autouse=True)
def _reikwijdte_terug():
    """De reikwijdte is een moduleschakelaar; niet laten hangen."""
    yield
    test_panel.limit_to_current(False)


# --------------------------------------------------------------------------
# De kern: een dode thread mag niet meer voorkomen
# --------------------------------------------------------------------------

def test_systemexit_is_geen_exception() -> None:
    """De hele bug in één regel - hier stond ieders aanname verkeerd."""
    assert not issubclass(SystemExit, Exception)
    assert issubclass(SystemExit, BaseException)


@pytest.mark.parametrize("ontploffing", [
    SystemExit("gereedschap stopte"),
    KeyboardInterrupt(),
])
def test_de_werker_meldt_ook_een_baseexception(qapp, ontploffing) -> None:
    """Anders: geen signaal, geen melding, en een venster dat hangt."""
    from modules import gui

    def taak(_progress, _message):
        raise ontploffing

    werker = gui._Worker(taak)
    gemeld: list[str] = []
    klaar: list[object] = []
    werker.failed.connect(gemeld.append)
    werker.done.connect(klaar.append)
    werker.run()                     # rechtstreeks, geen echte thread
    assert klaar == []
    assert len(gemeld) == 1, "er moet PRECIES één melding komen"
    assert gemeld[0].strip()


def test_de_werker_vangt_alles_af() -> None:
    """Een `except Exception` als laatste vangnet is hier niet genoeg."""
    from modules import gui

    bron = inspect.getsource(gui._Worker.run)
    assert "except BaseException" in bron
    laatste = [regel.strip() for regel in bron.splitlines()
               if regel.strip().startswith("except ")][-1]
    assert "BaseException" in laatste, \
        f"het laatste vangnet is {laatste!r} en laat SystemExit langs"


def test_een_gewone_taak_meldt_nog_steeds_klaar(qapp) -> None:
    """Het bredere vangnet mag de goede afloop niet opeten."""
    from modules import gui

    werker = gui._Worker(lambda _p, _m: "uitkomst")
    klaar: list[object] = []
    mislukt: list[str] = []
    werker.done.connect(klaar.append)
    werker.failed.connect(mislukt.append)
    werker.run()
    assert klaar == ["uitkomst"]
    assert mislukt == []


# --------------------------------------------------------------------------
# Het gereedschap gooit geen SystemExit meer
# --------------------------------------------------------------------------

def _probe():
    import importlib.util

    pad = WORTEL / "tools" / "whisper_probe.py"
    spec = importlib.util.spec_from_file_location("probe_test", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vocal_stem_raises_an_ordinary_error(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        _probe().vocal_stem(tmp_path, "DoesNotExist")


def test_vocal_stem_still_finds_the_loose_wav(tmp_path) -> None:
    from modules.filesystem import ProjectPaths

    paden = ProjectPaths(root=tmp_path, song="Proef")
    paden.cache_dir.mkdir(parents=True, exist_ok=True)
    (paden.cache_dir / "original.wav").write_bytes(b"")
    assert _probe().vocal_stem(tmp_path, "Proef").name == "original.wav"


def test_alleen_main_mag_met_systemexit_stoppen() -> None:
    """Een functie die de app ook aanroept, mag dat nooit doen.

    Precies dit onderscheid ging mis: ``zangstem`` was geschreven als
    opdrachtregelcode maar werd door 1.5.9 aangeroepen.
    """
    fout = []
    for map_ in ("modules", "tools"):
        for pad in sorted((WORTEL / map_).glob("*.py")):
            boom = ast.parse(pad.read_text(encoding="utf-8"))
            for knoop in ast.walk(boom):
                if not isinstance(knoop, ast.FunctionDef):
                    continue
                if knoop.name == "main":
                    continue
                for binnen in ast.walk(knoop):
                    if isinstance(binnen, ast.Raise) and \
                            "SystemExit" in ast.dump(binnen):
                        fout.append(f"{pad.name}:{binnen.lineno} "
                                    f"({knoop.name})")
    assert fout == [], "SystemExit buiten main(): " + ", ".join(fout)


# --------------------------------------------------------------------------
# 1.5.9 struikelt niet meer over een leeg project
# --------------------------------------------------------------------------

def test_zonder_gekozen_project_komt_er_een_nette_melding(tmp_path) -> None:
    """Dit was de aanleiding: het project stond leeg na de herstart.

    B374: de venstertest is verhuisd naar de zware bak (1.5.11c); de
    controle op "is er wel een project gekozen" is meeverhuisd en moet
    daar net zo goed staan.
    """
    from dataclasses import replace

    context = _context(tmp_path)
    context = replace(context,
                      config=replace(context.config,
                                     song=replace(context.config.song,
                                                  title="")))
    # B386: zonder gekozen project zoekt de proef zelf het grootste gat
    # op. Is er nergens een gat, dan slaat hij zichzelf over - en dat is
    # sinds B385 een TrialSkipped en geen gewone uitslag, zodat hij geen
    # twintig versies vrijaf boekt voor een meting die niet plaatsvond.
    with pytest.raises(test_panel.TrialSkipped) as val:
        test_panel.chunk_trial(context, lambda *a, **k: None,
                               lambda: False)
    assert val.value.lines == [TRANSLATIONS["nl"]["heavy_probe_nowhere"]]


def test_zonder_transcriptie_is_het_een_melding_en_geen_klap(tmp_path) -> None:
    with pytest.raises(test_panel.TrialSkipped) as val:
        test_panel.chunk_trial(_context(tmp_path),
                               lambda *a, **k: None, lambda: False)
    assert len(val.value.lines) == 1


# --------------------------------------------------------------------------
# De keuzerondjes doen eindelijk iets
# --------------------------------------------------------------------------

def _project_maken(context, naam: str) -> None:
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paden = ProjectPaths(root=context.paths.root, song=naam,
                         output_base=context.paths.output_base)
    ensure_directories(paden)
    ProjectStore(paden.project_file).set_meta("proef", 1)


def test_alle_projecten_levert_alles(tmp_path) -> None:
    context = _context(tmp_path, "Twee")
    for naam in ("Een", "Twee", "Drie"):
        _project_maken(context, naam)
    test_panel.limit_to_current(False)
    assert test_panel._projects(context) == ["Drie", "Een", "Twee"]


def test_alleen_dit_project_levert_er_een(tmp_path) -> None:
    context = _context(tmp_path, "Twee")
    for naam in ("Een", "Twee", "Drie"):
        _project_maken(context, naam)
    test_panel.limit_to_current(True)
    assert test_panel._projects(context) == ["Twee"]


def test_alleen_dit_project_zonder_project_levert_niets(tmp_path) -> None:
    from dataclasses import replace

    context = _context(tmp_path, "Twee")
    _project_maken(context, "Twee")
    context = replace(context,
                      config=replace(context.config,
                                     song=replace(context.config.song,
                                                  title="")))
    test_panel.limit_to_current(True)
    assert test_panel._projects(context) == []


def test_de_loper_leest_de_keuzerondjes() -> None:
    """Ze stonden er wel, maar niemand keek ernaar."""
    from modules import gui

    bron = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "only_this_project()" in bron
    assert "limit_to_current" in bron


def test_de_reikwijdte_wordt_elke_draai_opnieuw_gezet() -> None:
    """Anders blijft de keuze van vorige keer hangen."""
    from modules import gui

    bron = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert bron.index("limit_to_current") < bron.index("def task")


def test_de_balk_verspringt_ook_bij_een_actie_die_niets_meldt() -> None:
    """1.5.9 heeft geen rij projecten en meldde dus nooit iets; het
    etiket van de vorige actie bleef staan en dat leest als vastlopen."""
    from modules import gui

    bron = inspect.getsource(gui.MainWindow._do_fill_cache)
    kop = bron.index("def report")
    staart = bron[kop:]
    assert "for slot in range(len(self._progress_bars))" in staart
    assert staart.index("report(slot") < staart.index("action.function(")


def test_de_nieuwe_teksten_staan_in_beide_talen() -> None:
    """B400: ``test_no_project`` en ``test_cancelled`` zijn opgeruimd.

    Ze hoorden bij de venstertest die in B374 naar de zware bak is
    verhuisd en in B386 zichzelf een project ging kiezen; sindsdien riep
    niemand ze meer aan. De sleutels die er WEL nog toe doen staan
    hieronder.
    """
    for sleutel in ("test_running", "test_failed", "test_done"):
        for taal in ("nl", "en"):
            assert TRANSLATIONS[taal].get(sleutel, "").strip(), \
                f"{sleutel} ({taal})"
