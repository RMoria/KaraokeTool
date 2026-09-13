"""Tests voor v0.113.0: B358 (de grote proef, 1.5.11).

Eén test die alle modellen tegen elkaar afzet: per niveau (blok, zin,
KOPPELING, woord), apart, in paren, in omgekeerde volgorde en per
project. Het verslag komt in ``docs/modelmatrix.md`` en wordt na elke
variant weggeschreven, want een vastloper om drie uur 's nachts mag niet
de hele nacht weggooien.

De scherpste test hier is ``test_elke_vervanger_past_op_de_echte_aanroep``:
de proef zet functies opzij door ze te overschrijven, en dat gaat stil
mis zodra iemand een echte functie hernoemt of er een argument bij zet.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline, test_panel  # noqa: E402
from modules.translations import TRANSLATIONS  # noqa: E402

WORTEL = Path(__file__).resolve().parents[1]


def _context(tmp_path: Path, naam: str = "Proef"):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=naam)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


def _alle_varianten():
    """(naam, doelen) van élke lijst met vervangers in de proef.

    B361: de modellen komen nu uit ``model_register`` in plaats van uit
    een eigen kopie in het testpaneel. De bewakingen hieronder blijven
    precies hetzelfde werk doen - ze kijken alleen op de nieuwe plek.
    """
    from modules import model_register

    for model in model_register.register():
        yield model.label, list(model.targets)
    for naam, doelen in test_panel._orders():
        yield naam, doelen


# --------------------------------------------------------------------------
# De vervangers passen op de echte functies
# --------------------------------------------------------------------------

def test_elk_doel_bestaat_nog() -> None:
    """Een hernoemde functie moet hier omvallen, niet 's nachts."""
    for naam, doelen in _alle_varianten():
        for module, attribuut, _vervanger in doelen:
            assert hasattr(module, attribuut), \
                f"{naam}: {module.__name__}.{attribuut} bestaat niet meer"


def test_elke_vervanger_neemt_de_verplichte_argumenten():
    """Zoveel argumenten kunnen aannemen als de echte functie eist.

    Zonder deze test valt een vervanger pas om als de proef er al een
    uur in zit - en dan is de nacht weg.
    """
    for naam, doelen in _alle_varianten():
        for module, attribuut, vervanger in doelen:
            echt = inspect.signature(getattr(module, attribuut))
            verplicht = [p for p in echt.parameters.values()
                         if p.default is p.empty
                         and p.kind in (p.POSITIONAL_ONLY,
                                        p.POSITIONAL_OR_KEYWORD)]
            try:
                inspect.signature(vervanger).bind_partial(
                    *[None] * len(verplicht))
            except TypeError:
                pytest.fail(f"{naam}: {attribuut} krijgt {len(verplicht)} "
                            f"argument(en), de vervanger neemt er minder")


def test_elke_vervanger_slikt_ook_de_keuze_argumenten() -> None:
    """De aanroepers geven ``skip_filler=``, ``dropped_out=`` en zo mee."""
    for naam, doelen in _alle_varianten():
        for module, attribuut, vervanger in doelen:
            echt = inspect.signature(getattr(module, attribuut))
            nep = inspect.signature(vervanger)
            if any(p.kind is p.VAR_KEYWORD for p in nep.parameters.values()):
                continue
            for parameter in echt.parameters.values():
                if parameter.default is parameter.empty:
                    continue
                try:
                    nep.bind_partial(**{parameter.name: None})
                except TypeError:
                    pytest.fail(f"{naam}: {attribuut} kan met "
                                f"'{parameter.name}=' worden aangeroepen, "
                                f"de vervanger kent die niet")


def test_een_vervanger_geeft_hetzelfde_soort_antwoord() -> None:
    """De neutrale vorm moet de invoer teruggeven, niet None."""
    from modules import model_register, song_text

    _m, _a, uitbreiden = model_register.by_code("B191").targets[0]
    assert uitbreiden("tekst", [("tekst", 0.0, 1.0)], 0, set()) == [0]
    _m, _a, creatief = model_register.by_code("B228").targets[0]
    assert creatief(["a", "b"], [], [[3], []]) == [[3], []]
    assert song_text.extend_coupling  # de echte staat er nog


# --------------------------------------------------------------------------
# De koppeling zit er echt in
# --------------------------------------------------------------------------

def test_de_koppeling_is_een_eigen_niveau() -> None:
    """B148 zit in de koppeling, dus die moet in de matrix staan."""
    from modules import model_register

    niveaus = {m.level for m in model_register.register()}
    assert niveaus == {"blok", "zin", "koppeling", "woord", "venster"}


def test_de_koppelmodellen_die_ertoe_doen_staan_erin() -> None:
    from modules import model_register

    codes = {m.code for m in model_register.register()
             if m.level == "koppeling"}
    for nummer in ("B258/B285", "B307/B337", "B213", "B276", "B159",
                   "B121", "B313"):
        assert nummer in codes, nummer


def test_b313_staat_maar_op_een_plek() -> None:
    """Stond eerst onder 'zin'; twee keer meten geeft twee waarheden."""
    from modules import model_register

    plekken = [m.level for m in model_register.register()
               if m.code == "B313"]
    assert plekken == ["koppeling"]


def test_de_venstermodellen_zitten_niet_in_de_meetlat() -> None:
    """B191/B228 draaien alleen in ``word_coupling_view``.

    Ze in de meetlat zetten zou een tabel vol nullen geven en een nacht
    kosten; ze horen in de dekkingstabel.
    """
    bron = inspect.getsource(pipeline._lyrics_alignment)
    assert "extend_coupling" not in bron
    assert "creative_couplings" not in bron
    from modules import model_register

    for code in ("B191", "B228"):
        model = model_register.by_code(code)
        assert model is not None and model.level == "venster", code
    meetbaar = {m.code for m in model_register.register()
                if m.level in ("blok", "zin", "koppeling")}
    assert "B191" not in meetbaar and "B228" not in meetbaar


def test_koppelkenmerken_zwijgt_over_een_leeg_project(tmp_path) -> None:
    assert test_panel._coupling_features(_context(tmp_path), "Proef") == {}


# --------------------------------------------------------------------------
# Volgorde
# --------------------------------------------------------------------------

def test_er_worden_echt_volgordes_omgedraaid() -> None:
    namen = [naam for naam, _d in test_panel._orders()]
    assert namen and all("vóór" in naam for naam in namen)


def test_een_volgordevariant_zet_meer_dan_een_functie_uit() -> None:
    """'B313 vóór B121' moet B313 verplaatsen, niet uitzetten.

    Alleen de energieplaatsing leegmaken zou hetzelfde meten als het
    losse model en stil een verkeerde conclusie opleveren.
    """
    doelen = dict(test_panel._orders())["B313 vóór B121"]
    attributen = {a for _m, a, _v in doelen}
    assert attributen == {"_clean_segments_and_alignment",
                          "_place_skipped_on_energy"}


# --------------------------------------------------------------------------
# De nacht moet af komen
# --------------------------------------------------------------------------

def test_er_wordt_niet_meer_gesnoeid_op_de_paren() -> None:
    """B366: de snoeidrempel is eruit, en dat moet zo blijven.

    In v0.115.0 gingen alleen modellen met >=0.02 s eigen effect mee.
    Diezelfde tabel liet zien waarom dat fout was: de ankertoets en de
    energieplaatsing samen uit gaven 5.66 s waar 3.66 verwacht werd. Een
    model dat in zijn eentje niets doet, kan een vangnet zijn.
    """
    assert not hasattr(test_panel, "_PAAR_DREMPEL")
    bron = inspect.getsource(test_panel.big_trial)
    assert "combinations(singles, 2)" in bron
    assert "test_matrix_pairs_all" in bron


def test_er_wordt_na_elke_variant_weggeschreven() -> None:
    """Een vastloper om drie uur mag niet de hele nacht weggooien."""
    bron = inspect.getsource(test_panel.big_trial)
    assert bron.count("write_report()") >= 8


def test_elke_lus_kijkt_naar_de_stopknop() -> None:
    bron = inspect.getsource(test_panel.big_trial)
    assert bron.count("cancelled()") >= 5


def test_de_modellen_worden_altijd_teruggezet(tmp_path) -> None:
    """Ook als een variant onderweg klapt.

    Blijft er een vervanger staan, dan draait de volgende meting - en
    daarna het programma - op nep.
    """
    from modules import model_register

    context = _context(tmp_path)
    # B361: eerst de stand van het register toepassen, want dat doet de
    # proef zelf ook. Wat hier gemeten wordt is of een VARIANT blijft
    # hangen, niet of een uitgezet model is toegepast.
    model_register.apply_disabled()
    voor = {(m.__name__, a): getattr(m, a)
            for _naam, doelen in _alle_varianten()
            for m, a, _v in doelen}
    kapot = test_panel._yardstick_rows

    def klap(*_a, **_k):
        raise RuntimeError("kapot")

    test_panel._yardstick_rows = klap
    try:
        with pytest.raises(RuntimeError):
            test_panel.big_trial(context, lambda *a, **k: None,
                                   lambda: False)
    finally:
        test_panel._yardstick_rows = kapot
    na = {(m.__name__, a): getattr(m, a)
          for _naam, doelen in _alle_varianten()
          for m, a, _v in doelen}
    assert voor == na
    model_register.restore_all()


# --------------------------------------------------------------------------
# Het paneel en het verslag
# --------------------------------------------------------------------------

def test_de_grote_proef_is_de_laatste_meetactie() -> None:
    """B531: 1.5.12 staat er achter, maar dat is een klus en geen
    meting - vandaar dat die er hier buiten valt."""
    meetacties = [a for a in test_panel.ACTIONS
                  if not a.heavy and not a.on_request]
    actie = meetacties[-1]
    assert actie.code == "1.5.10"
    assert actie.function is test_panel.big_trial
    assert actie.all_projects


def test_het_verslag_is_om_te_leggen() -> None:
    """Anders overschrijft een test het echte verslag."""
    assert test_panel.MATRIX_REPORT.name == "modelmatrix.md"
    assert "MATRIX_REPORT" in inspect.getsource(test_panel.big_trial)


def test_de_proef_draait_op_een_lege_ijkset(tmp_path, monkeypatch) -> None:
    verslag = tmp_path / "modelmatrix.md"
    monkeypatch.setattr(test_panel, "MATRIX_REPORT", verslag)
    uitkomst = test_panel.big_trial(_context(tmp_path),
                                      lambda *a, **k: None, lambda: False)
    assert isinstance(uitkomst, str)
    tekst = verslag.read_text(encoding="utf-8")
    for kop in ("## Uitgangspunt", "## Elk model apart anders",
                "## Twee tegelijk anders", "## Volgorde",
                "## Woordkoppeling (dekking)", "## Woord en lettergreep"):
        assert kop in tekst, kop


def test_een_afgebroken_proef_stopt_meteen(tmp_path, monkeypatch) -> None:
    verslag = tmp_path / "modelmatrix.md"
    monkeypatch.setattr(test_panel, "MATRIX_REPORT", verslag)
    gemeten: list[int] = []
    echt = test_panel._yardstick_rows
    monkeypatch.setattr(test_panel, "_yardstick_rows",
                        lambda *a, **k: gemeten.append(1) or echt(*a, **k))
    test_panel.big_trial(_context(tmp_path), lambda *a, **k: None,
                           lambda: True)
    assert len(gemeten) == 1          # alleen het uitgangspunt


def test_alle_nieuwe_teksten_staan_in_beide_talen() -> None:
    for sleutel in ("test_matrix", "test_matrix_hint", "test_matrix_intro",
                    "test_matrix_where", "test_matrix_pairs",
                    "test_matrix_order",
                    "test_matrix_coupling", "test_matrix_words",
                    "test_matrix_done"):
        for taal in ("nl", "en"):
            assert TRANSLATIONS[taal].get(sleutel, "").strip(), \
                f"{sleutel} ({taal})"
