"""Tests voor v0.111.0: het testpaneel achter 1.5 en de publicatielijst.

De knop 1.5 heet nu "Test" en opent een aanvinklijst met tien genummerde
acties. Verder: "Lied-project" zonder de uitleg tussen haakjes, en een
bewaking die eist dat tijdelijke code op de publicatielijst staat.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import test_panel  # noqa: E402
from modules.translations import TRANSLATIONS, t  # noqa: E402

WORTEL = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _context(tmp_path: Path, naam: str = "Proef"):
    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=naam)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# De nummering
# --------------------------------------------------------------------------

def test_de_acties_zijn_oplopend_genummerd() -> None:
    """"Draai 1.5.3" moet eenduidig zijn.

    B526: 1.5.8 is weggehaald en het nummer blijft leeg. Doorschuiven zou
    elk nummer in het logboek, in de testhistorie en in het gesprek een
    andere betekenis geven - en juist dat moet een nummer nooit doen. Een
    gat is eerlijker dan een hernummering; het volgende onderzoek dat
    erbij komt neemt 1.5.8 weer in.
    """
    nummers = [int(actie.code.rsplit(".", 1)[1])
               for actie in test_panel.ACTIONS]
    assert nummers == sorted(nummers)
    assert len(nummers) == len(set(nummers))
    assert nummers[0] == 1


def test_elke_actie_heeft_een_naam_en_uitleg_in_beide_talen() -> None:
    for actie in test_panel.ACTIONS:
        for sleutel in (actie.name_key, actie.explanation_key):
            for taal in ("nl", "en"):
                assert sleutel in TRANSLATIONS[taal], f"{sleutel} ({taal})"
                assert TRANSLATIONS[taal][sleutel].strip()


def test_cache_vullen_is_actie_een() -> None:
    """Die bestond eerst als losse knop; hij houdt zijn plek vooraan."""
    assert test_panel.ACTIONS[0].code == "1.5.1"
    assert test_panel.ACTIONS[0].function is test_panel.fill_cache


# --------------------------------------------------------------------------
# Het venster
# --------------------------------------------------------------------------

def test_vinkjes_staan_altijd_uit_bij_openen(qapp) -> None:
    """Een vergeten vinkje op 1.5.10 kost een half uur."""
    paneel = test_panel.TestPanel()
    assert not any(v.isChecked() for v in paneel._ticks)
    assert paneel.chosen() == []


def test_aanvinken_levert_de_acties_in_nummervolgorde(qapp) -> None:
    paneel = test_panel.TestPanel()
    paneel._ticks[4].setChecked(True)
    paneel._ticks[1].setChecked(True)
    assert [a.code for a in paneel.chosen()] == ["1.5.2", "1.5.5"]


def test_knop_15_heet_test(qapp, tmp_path) -> None:
    from modules import gui

    window = gui.MainWindow(_context(tmp_path))
    namen = [b.text() for b in window._step_buttons]
    assert namen[-1] == t("step_fill_cache") == "1.5. Test"


# --------------------------------------------------------------------------
# De acties zelf
# --------------------------------------------------------------------------

def test_elke_actie_kijkt_naar_de_stopknop() -> None:
    """Stop moet ook tijdens een test werken."""
    import inspect

    for actie in test_panel.ACTIONS:
        bron = inspect.getsource(actie.function)
        assert "cancelled" in bron, actie.code


def test_rapporten_draaien_op_een_leeg_project(tmp_path) -> None:
    """Ze mogen niet stuklopen als er niets te melden valt.

    B360: de melder hier was ``lambda _t: None`` - de vorm van vóór
    B357. Daarmee legde deze test het OUDE contract vast en kon hij een
    actie die zich niet aan het nieuwe hield nooit betrappen. Hij komt
    nu uit ``test_v0115``, waar hij aan de loper is vastgelegd; de volle
    ronde over alle elf acties staat daar ook.
    """
    from test_v0115 import melder

    context = _context(tmp_path)
    for code in ("1.5.2", "1.5.3", "1.5.4", "1.5.5"):
        actie = next(a for a in test_panel.ACTIONS if a.code == code)
        uitkomst = actie.function(context, melder(), lambda: False)
        assert isinstance(uitkomst, str)


def test_een_afgebroken_test_stopt_meteen(tmp_path) -> None:
    from test_v0115 import melder

    context = _context(tmp_path)
    actie = next(a for a in test_panel.ACTIONS if a.code == "1.5.2")
    assert isinstance(actie.function(context, melder(), lambda: True), str)


# --------------------------------------------------------------------------
# "Lied-project" zonder de haakjes
# --------------------------------------------------------------------------

def test_liedproject_heeft_geen_uitleg_meer_in_de_kop() -> None:
    assert TRANSLATIONS["nl"]["song_group"] == "Lied-project"
    assert TRANSLATIONS["en"]["song_group"] == "Song project"


# --------------------------------------------------------------------------
# Tijdelijke code staat op de publicatielijst
# --------------------------------------------------------------------------

def test_tijdelijke_code_staat_op_de_publicatielijst() -> None:
    """Een TIJDELIJK-markering die nergens genoemd wordt, wordt vergeten.

    B136 was ook zo'n tijdelijke knop; dat die er weer uit ging was meer
    geluk dan wijsheid.
    """
    document = (WORTEL / "docs" / "doorontwikkeling.md").read_text(
        encoding="utf-8")
    kop = document.index("## Voor publicatie beslissen")
    sectie = document[kop:document.index("\n## ", kop + 10)]
    gemarkeerd = {
        pad.relative_to(WORTEL).as_posix()
        for map_ in ("modules", "tools")
        for pad in (WORTEL / map_).glob("*.py")
        # B465: het Engelse woord telt ook. De code is bij B438/B446
        # omgezet, dus een nieuwe tijdelijke aantekening staat er in
        # het Engels in - en dan keek deze bewaker er straal langs.
        if re.search(r"\b(TIJDELIJK|TEMPORARY)\b",
                     pad.read_text(encoding="utf-8"))
    }
    assert gemarkeerd, "geen tijdelijke code gevonden - klopt de zoektocht nog?"
    for pad in sorted(gemarkeerd):
        assert pad in sectie, f"{pad} is tijdelijk maar staat niet op de lijst"
