"""Tests voor v0.115.0: B360 (1.5.10 struikelde over de melder).

B357 gaf de melder een andere vorm - van ``melden(naam)`` naar
``melden(plek, naam, klaar, totaal)``, omdat elke werkplek zijn eigen
balk kreeg. Alle acties gingen mee, behalve ``omission_trial``, die op één
plek nog de oude vorm gebruikte. 1.5.10 viel daardoor na achtentwintig
milliseconden om met een ``TypeError``.

Het venijn zit niet in die ene regel maar in waarom 827 tests hem niet
zagen. Twee dingen wezen nog naar het oude contract: de typeaanduiding
``Reporter`` bovenin ``test_panel.py`` stond nog op ``Callable[[str],
None]``, en de tests riepen de acties aan met ``lambda _t: None`` - een
melder met één argument. De test bevestigde dus het oude contract in
plaats van het echte, en kon deze fout per definitie nooit vinden.

Vandaar dat hieronder één melder staat die exact de vorm van de loper
heeft, plus een bewaking die die twee vormen aan elkaar vastlegt.
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

#: De namen die de loper aan zijn melder geeft, in deze volgorde.
MELDERVORM = ["slot", "name", "done", "total"]


def melder(gezien: list | None = None):
    """Precies de melder die de loper meegeeft (B357/B360).

    Géén ``*args``: een melder die alles slikt zou deze bug juist
    verbergen, en dat is exact wat er gebeurde.
    """
    def report(slot: int, name: str, done: int = 0,
               total: int = 0) -> None:
        if gezien is not None:
            gezien.append((slot, name, done, total))
    return report


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
# De reparatie zelf
# --------------------------------------------------------------------------

def test_de_weglaatproef_meldt_met_de_nieuwe_vorm(tmp_path) -> None:
    """Dit is de regel die omviel; hij moet nu gewoon lopen."""
    gezien: list = []
    uitkomst = test_panel.omission_trial(_context(tmp_path), melder(gezien),
                                       lambda: False)
    assert isinstance(uitkomst, str)
    assert gezien, "1.5.9 moet zijn varianten melden"
    for plek, naam, klaar, totaal in gezien:
        assert plek == 0, "de variantnaam hoort op de eerste balk"
        assert isinstance(naam, str) and naam.strip()
        assert (klaar, totaal) == (0, 0)


def test_de_weglaatproef_noemt_zijn_varianten(tmp_path) -> None:
    """B361: de varianten komen uit het register, met hun B-nummer."""
    from modules import model_register

    gezien: list = []
    test_panel.omission_trial(_context(tmp_path), melder(gezien),
                            lambda: False)
    namen = [naam for _plek, naam, _k, _t in gezien]
    assert len(namen) == len(set(namen)), "elke variant maar één keer"
    meetbaar = [m.label for m in model_register.register()
                if m.level in ("blok", "zin", "koppeling")]
    for label in meetbaar:
        assert label in namen, label


# --------------------------------------------------------------------------
# Het contract vastleggen, zodat dit niet nog eens kan
# --------------------------------------------------------------------------

def test_de_loper_geeft_de_melder_die_wij_hier_gebruiken() -> None:
    """Legt de vorm in de loper vast aan de vorm in deze tests.

    Verandert de melder nóg een keer, dan valt deze test om in plaats
    van één vergeten actie in beeld.
    """
    from modules import gui

    boom = ast.parse(inspect.getsource(gui.MainWindow._do_fill_cache).lstrip())
    binnenin = [k for k in ast.walk(boom)
                if isinstance(k, ast.FunctionDef) and k.name == "report"]
    assert len(binnenin) == 1, "waar is de melder van de loper gebleven?"
    namen = [a.arg for a in binnenin[0].args.args]
    assert namen[:len(MELDERVORM)] == MELDERVORM
    assert list(inspect.signature(melder()).parameters) == MELDERVORM


def test_geen_actie_roept_de_melder_nog_met_een_argument_aan() -> None:
    """De structurele bewaking: ``melden(naam)`` mag nergens meer staan.

    Goedkoper en scherper dan wachten tot een zware actie omvalt.
    """
    fout = []
    for pad in (WORTEL / "modules" / "test_panel.py",
                WORTEL / "modules" / "gui.py"):
        boom = ast.parse(pad.read_text(encoding="utf-8"))
        for knoop in ast.walk(boom):
            if not isinstance(knoop, ast.Call):
                continue
            if not (isinstance(knoop.func, ast.Name)
                    and knoop.func.id == "melden"):
                continue
            if len(knoop.args) < 2:
                fout.append(f"{pad.name}:{knoop.lineno}")
    assert fout == [], "melden() met te weinig argumenten: " + ", ".join(fout)


def test_de_typeaanduiding_wijst_niet_meer_de_verkeerde_kant_op() -> None:
    """``Callable[[str], None]`` beschreef de melder van vóór B357."""
    bron = (WORTEL / "modules" / "test_panel.py").read_text(encoding="utf-8")
    assert "Reporter = Callable[[str], None]" not in bron
    assert "Reporter = Callable[..., None]" in bron


# --------------------------------------------------------------------------
# Alle elf, met de echte melder
# --------------------------------------------------------------------------

def test_elke_actie_verdraagt_de_echte_melder(tmp_path, monkeypatch) -> None:
    """Alle elf, niet de vier die toevallig nooit iets melden.

    ``test_rapporten_draaien_op_een_leeg_project`` liep alleen 1.5.2 t/m
    1.5.5 af, en juist die vier roepen de melder nooit aan. Daardoor kon
    1.5.10 groen staan terwijl hij in beeld meteen omviel.
    """
    monkeypatch.setattr(test_panel, "MATRIX_REPORT",
                        tmp_path / "modelmatrix.md")
    context = _context(tmp_path)
    for actie in test_panel.ACTIONS:
        uitkomst = actie.function(context, melder(), lambda: False)
        assert isinstance(uitkomst, str), actie.code


def test_elke_actie_stopt_netjes_op_de_stopknop(tmp_path,
                                                monkeypatch) -> None:
    monkeypatch.setattr(test_panel, "MATRIX_REPORT",
                        tmp_path / "modelmatrix.md")
    context = _context(tmp_path)
    for actie in test_panel.ACTIONS:
        assert isinstance(actie.function(context, melder(), lambda: True),
                          str), actie.code


# --------------------------------------------------------------------------
# "Liep vast" betekende iets anders geworden
# --------------------------------------------------------------------------

def test_een_gestruikelde_actie_heet_niet_meer_vastgelopen() -> None:
    """Sinds B359 is "vastlopen" een andere storing: een dood venster.

    1.5.10 hing niet, hij viel om na achtentwintig milliseconden - en de
    melding stuurde precies de verkeerde kant op bij het zoeken.
    """
    for sleutel in ("log_test_failed", "test_failed", "test_project_failed"):
        tekst = TRANSLATIONS["nl"][sleutel]
        assert "vast" not in tekst, f"{sleutel}: {tekst!r}"
        assert "struikel" in tekst, f"{sleutel}: {tekst!r}"
    assert set(TRANSLATIONS["nl"]) == set(TRANSLATIONS["en"])


@pytest.mark.parametrize("sleutel", ["test_failed", "test_project_failed"])
def test_de_meldingen_houden_hun_invulplek(sleutel) -> None:
    for taal in ("nl", "en"):
        tekst = TRANSLATIONS[taal][sleutel]
        assert "{code}" in tekst or "{name}" in tekst, f"{sleutel} ({taal})"
