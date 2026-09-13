"""Tests voor v0.116.0: B361 t/m B367.

Zes stukken in één release:

B361 het modellenregister - elk idee staat op naam met een stand, en een
     model dat niets waard blijkt gaat UIT en niet weg.
B362 de meethistorie - per actie, project en versie, zodat een
     onveranderd project overgeslagen wordt en een nieuwe versie naast
     de vorige drie te leggen is.
B363 woord- en lettergreeptoetsen - vier soorten controle zonder één
     handmatig gezette lettergreep.
B364 sneller - de zangstem één keer per project omzetten in plaats van
     per variant, en de laatste twee seriële secties over beide lijnen.
B365 maximaal tien acties onder 1.5, dus kleine tests samengevoegd.
B366 alle paren meten, zonder snoeidrempel.
B367 de knop 'alle' bovenaan.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import model_register, test_history, test_panel  # noqa: E402
from modules import timing_checks  # noqa: E402
from modules.translations import TRANSLATIONS  # noqa: E402

WORTEL = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _schoon(tmp_path, monkeypatch):
    """Register en historie nooit laten uitlekken naar een andere test."""
    monkeypatch.setattr(test_history, "HISTORY_FILE",
                        tmp_path / "testhistorie.json")
    yield
    model_register.restore_all()
    model_register.apply_settings({})
    test_panel.limit_to_current(False)
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
# B361 - het register
# --------------------------------------------------------------------------

def test_elk_model_heeft_een_code_een_naam_en_een_niveau() -> None:
    codes = [m.code for m in model_register.register()]
    assert len(codes) == len(set(codes)), "dubbele B-nummers"
    for model in model_register.register():
        assert model.code.startswith("B"), model.code
        assert model.name.strip()
        assert model.level in model_register.LEVELS, model.level
        assert model.targets, f"{model.code} kan niet uitgezet worden"


def test_een_uitgezet_model_zegt_waarom() -> None:
    """Een stand zonder reden is een stand die niemand meer durft terug
    te draaien."""
    for model in model_register.register():
        if not model.default_on:
            assert model.reason.strip(), model.code


def test_b213_staat_weer_aan_want_de_ijkset_is_meegegroeid() -> None:
    """B536: het oordeel uit v0.115.0 (-0,13 s) is achterhaald.

    De uitlaatproef mat het op 26 en 31 augustus twee keer andersom:
    met B213 AAN is de fout 0,18 s lager. Een uitgezet model blijft
    daarom meelopen - anders blijft zo'n oordeel dertig versies staan.
    """
    model = model_register.by_code("B213")
    assert model is not None and model.default_on is True
    assert not model.reason                  # aan, dus geen reden nodig


def test_uitzetten_vervangt_en_aanzetten_zet_terug() -> None:
    from modules import song_text

    echt = song_text.align_lyrics
    model_register.apply_settings({"B213": False})
    assert "B213" in model_register.apply_disabled()
    assert song_text.align_lyrics is not echt
    model_register.apply_settings({"B213": True})
    model_register.apply_disabled()
    assert song_text.align_lyrics is echt


def test_twee_keer_uitzetten_verandert_niets_extra() -> None:
    """Anders bewaart de tweede ronde de VERVANGER als origineel."""
    from modules import song_text

    echt = song_text.align_lyrics
    model_register.apply_settings({"B213": False})
    model_register.apply_disabled()
    model_register.apply_disabled()
    model_register.apply_settings({"B213": True})
    model_register.apply_disabled()
    assert song_text.align_lyrics is echt


def test_een_onbekend_model_in_de_instellingen_wordt_genegeerd() -> None:
    model_register.apply_settings({"B999": False})
    assert model_register.disabled_now() == ()
    assert model_register.enabled("B999") is True


def test_de_stand_gaat_mee_in_de_afleidingsketen() -> None:
    """B311: een uitgezet model verandert de timing, dus de afgeleiden
    moeten net zo goed vervallen als bij een gewijzigde instelling."""
    from dataclasses import replace

    from modules import pipeline
    from modules.config import default_config

    basis = default_config()
    anders = replace(basis, models={"B343": False})
    assert (pipeline._config_signature(basis)["config:models"]
            != pipeline._config_signature(anders)["config:models"])


def test_de_instellingen_bewaren_de_stand(tmp_path) -> None:
    from dataclasses import replace

    from modules import config as config_module

    pad = tmp_path / "config.json"
    config_module.save_config(
        replace(config_module.default_config(), models={"B213": False}), pad)
    assert config_module.load_config(pad).models == {"B213": False}


def test_de_matrix_meet_een_uitgezet_model_andersom() -> None:
    """Precies waarom het register er is: een uitgezet idee blijft
    meelopen en meldt zichzelf zodra het wél wat waard is.

    B536: het voorbeeld is nu de hallucinatiefilter, want B213 staat na
    diezelfde meting weer aan - wat het punt van deze toets alleen maar
    onderstreept.
    """
    varianten = {m.code: (doelen, aan) for _n, m, doelen, aan
                 in test_panel._variants_from_register()}
    assert "B258/B285" in varianten, "een uitgezet model mag niet wegvallen"
    doelen, aan = varianten["B258/B285"]
    assert aan is False
    assert [a for _m, a, _v in doelen] == ["_filter_hallucinations"]
    # De "andere kant" van uit is de ECHTE functie. Die staat op dit
    # moment NIET op de module (daar staat de vervanger), dus de variant
    # zou hem terugzetten - precies wat "wat zou aanzetten opleveren"
    # betekent.
    from modules import pipeline
    _module, _attribuut, terug = doelen[0]
    assert terug is not pipeline._filter_hallucinations
    assert "segments" in inspect.signature(terug).parameters


# --------------------------------------------------------------------------
# B362 - de meethistorie
# --------------------------------------------------------------------------

def test_een_bewaarde_uitslag_komt_terug(tmp_path) -> None:
    test_history.remember("1.5.5", "Lied", "0.1.0", "abc", {"new_moved": 1.5})
    assert test_history.lookup("1.5.5", "Lied", "0.1.0", "abc") == \
        {"new_moved": 1.5}


def test_een_andere_versie_telt_niet(tmp_path) -> None:
    test_history.remember("1.5.5", "Lied", "0.1.0", "abc", {"x": 1})
    assert test_history.lookup("1.5.5", "Lied", "0.2.0", "abc") is None


def test_gewijzigde_gegevens_tellen_niet(tmp_path) -> None:
    """De kern van "bij nieuwe data moet het wel overnieuw"."""
    test_history.remember("1.5.5", "Lied", "0.1.0", "abc", {"x": 1})
    assert test_history.lookup("1.5.5", "Lied", "0.1.0", "gewijzigd") is None


def test_er_worden_maar_drie_versies_bewaard(tmp_path) -> None:
    for n in range(6):
        test_history.remember("1.5.5", "Lied", f"0.{n}.0", "abc", {"x": n})
    bewaard = [e["version"] for e in test_history.history("1.5.5", "Lied")]
    assert bewaard == ["0.3.0", "0.4.0", "0.5.0"]
    assert test_history.KEEP_VERSIONS == 3


def test_de_vingerafdruk_verandert_met_een_uitgezet_model(tmp_path) -> None:
    context = _context(tmp_path)
    model_register.restore_all()
    voor = test_history.project_fingerprint(context, "Proef")
    model_register.apply_settings({"B343": False})
    model_register.apply_disabled()
    assert test_history.project_fingerprint(context, "Proef") != voor


def test_de_vergelijkingstabel_zet_de_versies_naast_elkaar(tmp_path) -> None:
    test_history.remember("1.5.5", "Lied", "0.1.0", "a", {"new_moved": 3.4})
    test_history.remember("1.5.5", "Lied", "0.2.0", "b", {"new_moved": 3.1})
    rijen = test_history.comparison("1.5.5", ["Lied"], "0.2.0", "new_moved")
    assert any("0.1.0" in r for r in rijen)
    assert any("3.40" in r and "3.10" in r for r in rijen)


def test_een_project_zonder_historie_geeft_een_streepje(tmp_path) -> None:
    test_history.remember("1.5.5", "Een", "0.1.0", "a", {"new_moved": 1.0})
    rijen = test_history.comparison("1.5.5", ["Een", "Twee"], "0.2.0",
                                    "new_moved")
    assert any(r.startswith("| Twee |") and "-" in r for r in rijen)


def test_de_verdeler_slaat_een_bekend_project_over(tmp_path) -> None:
    context = _context(tmp_path)
    gedaan: list[str] = []

    def werk(song: str):
        gedaan.append(song)
        return {"waarde": 1}

    for _ronde in range(2):
        test_panel.with_history(context, ["Proef"], werk,
                                lambda *a, **k: None, lambda: False, "1.5.9")
    assert gedaan == ["Proef"], "de tweede ronde moest hergebruiken"
    assert test_panel.SKIPPED["1.5.9"] == 1


def test_opnieuw_meten_negeert_het_geheugen(tmp_path) -> None:
    context = _context(tmp_path)
    gedaan: list[str] = []
    for opnieuw in (False, True):
        test_panel.with_history(context, ["Proef"],
                                lambda s: gedaan.append(s) or {"x": 1},
                                lambda *a, **k: None, lambda: False,
                                "1.5.9", opnieuw)
    assert gedaan == ["Proef", "Proef"]


def test_de_verdeler_verwart_een_dict_niet_met_regels(tmp_path) -> None:
    """B362: de lus liep eerst over de SLEUTELS van zo'n antwoord."""
    context = _context(tmp_path)
    uit = test_panel.across_projects(context, ["a"], lambda s: {"project": s},
                                    lambda *a, **k: None, lambda: False)
    assert uit == [{"project": "a"}]


# --------------------------------------------------------------------------
# B363 - woord- en lettergreeptoetsen
# --------------------------------------------------------------------------

class _Lettergreep(dict):
    def __init__(self, text, start, end, held=False):
        super().__init__(text=text, start=start, end=end, held=held)


def _regel(*lettergrepen):
    return {"syllables": list(lettergrepen)}


def test_een_nette_regel_levert_geen_klachten() -> None:
    found = timing_checks.Findings()
    timing_checks.shape_checks(
        [_regel(_Lettergreep(" ka", 0.0, 0.3), _Lettergreep("ra", 0.3, 0.6),
                _Lettergreep("o", 0.6, 0.9), _Lettergreep("ke", 0.9, 1.2))],
        found)
    uit = found.as_dict()
    assert uit["out_of_order"] == 0 and uit["overlapping"] == 0
    assert uit["too_short"] == 0 and uit["gaps_in_word"] == 0
    assert uit["syllables"] == 4


def test_een_lettergreep_van_acht_milliseconden_valt_op() -> None:
    found = timing_checks.Findings()
    timing_checks.shape_checks(
        [_regel(_Lettergreep(" a", 0.0, 0.008),
                _Lettergreep("b", 0.008, 0.9))], found)
    assert found.too_short == 1


def test_overlappende_lettergrepen_vallen_op() -> None:
    found = timing_checks.Findings()
    timing_checks.shape_checks(
        [_regel(_Lettergreep(" a", 0.0, 0.5), _Lettergreep("b", 0.3, 0.9))],
        found)
    assert found.overlapping == 1


def test_negen_lettergrepen_per_seconde_is_geen_zang() -> None:
    found = timing_checks.Findings()
    veel = [_Lettergreep(f" w{n}", n * 0.05, n * 0.05 + 0.05)
            for n in range(20)]
    timing_checks.shape_checks([_regel(*veel)], found)
    assert found.too_fast_lines == 1


def test_dezelfde_regel_twee_keer_hetzelfde_geeft_nul_verschil() -> None:
    found = timing_checks.Findings()
    regel = _regel(_Lettergreep(" la", 0.0, 0.5), _Lettergreep("la", 0.5, 1.0))
    tweede = _regel(_Lettergreep(" la", 10.0, 11.0),
                    _Lettergreep("la", 11.0, 12.0))
    timing_checks.repetition_consistency([regel, tweede], found)
    assert found.repeat_pairs == 1
    assert found.as_dict()["repeat_divergence"] == pytest.approx(0.0)


def test_een_scheve_herhaling_geeft_wel_verschil() -> None:
    found = timing_checks.Findings()
    eerste = _regel(_Lettergreep(" la", 0.0, 0.5), _Lettergreep("la", 0.5, 1.0))
    tweede = _regel(_Lettergreep(" la", 0.0, 0.9), _Lettergreep("la", 0.9, 1.0))
    timing_checks.repetition_consistency([eerste, tweede], found)
    assert found.as_dict()["repeat_divergence"] > 0.3


def test_de_toetsen_draaien_op_een_leeg_project(tmp_path) -> None:
    uit = timing_checks.inspect(_context(tmp_path), [])
    assert uit["lines"] == 0 and uit["in_silence"] == 0
    # B525: de grensovergang is weg; hij vergeleek de woorden van de
    # parodie met de gemeten grenzen van het origineel.
    assert "boundary_crossings" not in uit


# --------------------------------------------------------------------------
# B364 - sneller
# --------------------------------------------------------------------------

def test_de_zangstem_wordt_maar_een_keer_omgezet() -> None:
    bron = (WORTEL / "tools" / "timing_regression.py").read_text(
        encoding="utf-8")
    assert "_VOCALS_READY" in bron
    assert "def _stable_vocals" in bron
    assert "shutil.copy2" in bron, "copy2 houdt de wijzigingstijd aan"


def test_de_meetlat_wordt_maar_een_keer_ingeladen() -> None:
    bron = inspect.getsource(test_panel._regression_module)
    assert "_REGRESSION" in bron
    assert "exec_module" not in inspect.getsource(test_panel._yardstick_rows)


def test_de_laatste_twee_secties_gebruiken_beide_werkplekken() -> None:
    """Ze liepen met een gewone lus en dus op één kern."""
    bron = inspect.getsource(test_panel.big_trial)
    kop = bron.index("## Woordkoppeling")
    staart = bron[kop:]
    assert staart.count("across_projects(") == 2
    assert "for song in _projects(context)" not in staart


# --------------------------------------------------------------------------
# B365 / B366 / B367 - het paneel
# --------------------------------------------------------------------------

def test_er_zijn_hoogstens_tien_lichte_acties() -> None:
    """B371: het plafond geldt voor het gewone werk; 1.5.11 staat
    daarbuiten als zware bak."""
    licht = [a for a in test_panel.ACTIONS
             if not a.heavy]
    assert len(licht) <= test_panel.MAX_ACTIONS == 10
    # B526: oplopend en uniek; 1.5.8 staat leeg sinds die actie weg is.
    nummers = [int(a.code.rsplit(".", 1)[1]) for a in test_panel.ACTIONS]
    assert nummers == sorted(nummers) and len(nummers) == len(set(nummers))


def test_de_drie_goedkope_rapporten_zitten_in_een_actie(tmp_path) -> None:
    actie = next(a for a in test_panel.ACTIONS if a.code == "1.5.3")
    assert actie.function is test_panel.project_report
    bron = inspect.getsource(test_panel.project_report)
    for deel in ("_text_rows", "_filter_rows", "_structure_rows"):
        assert deel in bron, deel


def test_de_lettergreeptoetsen_hebben_een_eigen_actie() -> None:
    actie = next(a for a in test_panel.ACTIONS if a.code == "1.5.7")
    assert actie.function is test_panel.syllable_checks


def test_alle_paren_worden_gemeten() -> None:
    bron = inspect.getsource(test_panel.big_trial)
    assert "itertools.combinations(singles, 2)" in bron
    assert "DREMPEL" not in bron


def test_de_knop_alle_vinkt_alles_aan_en_weer_uit(qapp) -> None:
    paneel = test_panel.TestPanel()
    assert paneel.chosen() == [], "bij openen staat alles uit"
    paneel._toggle_all()
    licht = [a for a in test_panel.visible_actions()
             if not a.heavy and not a.on_request]
    assert len(paneel.chosen()) == len(licht)
    assert all(not a.heavy for a in paneel.chosen()), \
        "een zware proef mag nooit meeliften op 'alle'"
    assert all(not a.on_request for a in paneel.chosen()), \
        "alle video's opnieuw maken mag nooit meeliften op 'alle' (B531)"
    assert paneel._all_button.text() == TRANSLATIONS["nl"]["test_select_none"]
    paneel._toggle_all()
    assert paneel.chosen() == []
    assert paneel._all_button.text() == TRANSLATIONS["nl"]["test_select_all"]


def test_de_knop_alle_vult_aan_bij_een_halve_selectie(qapp) -> None:
    paneel = test_panel.TestPanel()
    paneel._ticks[0].setChecked(True)
    paneel._toggle_all()
    licht = [a for a in test_panel.visible_actions()
             if not a.heavy and not a.on_request]
    assert len(paneel.chosen()) == len(licht)


def test_opnieuw_meten_staat_uit_bij_openen(qapp) -> None:
    assert test_panel.TestPanel().remeasure() is False


def test_de_loper_geeft_opnieuw_meten_door() -> None:
    from modules import gui

    bron = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "remeasure()" in bron
    assert bron.index("REMEASURE") < bron.index("def task")


def test_alle_nieuwe_teksten_staan_in_beide_talen() -> None:
    sleutels = [a.name_key for a in test_panel.ACTIONS]
    sleutels += [a.explanation_key for a in test_panel.ACTIONS]
    sleutels += ["test_select_all", "test_select_none", "test_force_again",
                 "test_skipped_note", "test_history_head", "test_history_note",
                 "test_syllable_intro", "test_syllable_total", "test_on",
                 "test_off", "test_with", "test_without", "test_all_on",
                 "test_matrix_state", "test_matrix_symmetry",
                 "test_matrix_pairs_all", "test_model_state",
                 "log_model_disabled", "log_model_unknown"]
    for sleutel in sleutels:
        for taal in ("nl", "en"):
            assert TRANSLATIONS[taal].get(sleutel, "").strip(), \
                f"{sleutel} ({taal})"
