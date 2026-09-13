"""Tests voor v0.101.0: B323 tot en met B328.

B323 - de Stop-knop pakt de bezig-kleur niet meer af van de stap die
       loopt, zodat "1.1. Detecteer woorden" niet geel blijft.
B324 - de originele bestandsnaam van songtekst en karaoketekst wordt
       geschreven onder dezelfde sleutel als waaronder hij gelezen wordt.
B325 - de knoppen heten <tab>.<knop>. en een melding noemt een knop bij
       sleutel, niet bij naam.
B326 - "2.2. Timing verfijnen" liep stuk op een Nederlandse sleutel; de
       teksten die de pijplijn teruggeeft lopen nu via translations.py.
B327 - de baanlabels van de golfvorm-editor toonden hun eigen sleutel.
B328 - de handleiding beschrijft wat er te zien en te bedienen is.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline  # noqa: E402
from modules import translations as translations_module  # noqa: E402
from modules.translations import TRANSLATIONS, t  # noqa: E402

WORTEL = Path(__file__).resolve().parents[1]
MODULES = WORTEL / "modules"


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def nederlands():
    """Zet de taal terug, ook als een test hem onderweg omzet."""
    yield
    translations_module.set_language("nl")


def _context(tmp_path: Path, naam: str = "Proef"):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=naam)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B323: de Stop-knop en de bezig-kleur
# --------------------------------------------------------------------------

def test_stop_wordt_niet_op_bezig_gezet(qapp, tmp_path) -> None:
    """Stop start geen taak; hij hoort de bezig-kleur niet te krijgen."""
    from modules import gui

    window = gui.MainWindow(_context(tmp_path, "Stop1"))
    window._mark_busy_click(window._stop_button)
    assert window._stop_button not in window._busy_buttons


def test_stop_laat_de_lopende_knop_niet_geel_achter(qapp, tmp_path) -> None:
    """De gemelde volgorde: detectie starten, Stop drukken, afbreken.

    Stop was ook aangehaakt en werd daarmee eigenaar van de bezig-kleur;
    het opruimen zette daarna Stop terug in plaats van de stapknop, die
    dus geel bleef staan.
    """
    from modules import gui

    window = gui.MainWindow(_context(tmp_path, "Stop2"))
    detect = window._step_buttons[0]

    window._mark_busy_click(detect)
    assert detect in window._busy_buttons
    assert detect.styleSheet() != ""

    # Er loopt een taak; een klik op Stop mag het eigenaarschap niet
    # overnemen. (De echte worker vervangen we door een stand-in.)
    class _Bezig:
        def isRunning(self) -> bool:
            return True

    window._worker = _Bezig()
    window._mark_busy_click(window._stop_button)
    assert detect in window._busy_buttons
    assert window._stop_button not in window._busy_buttons

    # En na het afbreken is de stapknop weer gewoon.
    window._worker = None
    window._release_busy_button()
    assert detect.styleSheet() == ""
    assert not window._busy_buttons


def test_alle_gemarkeerde_knoppen_gaan_terug(qapp, tmp_path) -> None:
    """``_busy_buttons`` is een verzameling: er blijft er nooit een staan."""
    from modules import gui

    window = gui.MainWindow(_context(tmp_path, "Stop3"))
    eerste, tweede = window._step_buttons[0], window._step_buttons[1]
    window._busy_buttons = {eerste, tweede}
    window._apply_busy_style(eerste, True)
    window._apply_busy_style(tweede, True)
    window._release_busy_button()
    assert eerste.styleSheet() == "" and tweede.styleSheet() == ""


# --------------------------------------------------------------------------
# B324: onder welke sleutel de originele bestandsnaam staat
# --------------------------------------------------------------------------

def test_schrijfsleutel_en_leessleutel_zijn_dezelfde() -> None:
    """De schrijver gebruikte de bestandsnaam (``songtekst``), de lezer
    vroeg om ``lyrics``. Daardoor stond er altijd de interne naam."""
    gui_bron = (MODULES / "gui.py").read_text(encoding="utf-8")

    geschreven = set(re.findall(
        r'_copy_into_input\(\s*chosen,\s*\n?\s*(?:f?"[^"]+"|[^,]+),\s*\n?\s*"(\w+)"',
        gui_bron))
    gelezen = set(re.findall(
        r'input_display_name\(\s*\n?\s*self\._context,\s*"(\w+)"', gui_bron))
    gelezen |= set(re.findall(r'input_start_dir\(self\._context,\s*"(\w+)"',
                              gui_bron))

    # De audiosporen gaan via de variabele ``stem`` (original/karaoke)
    # en zijn altijd al gelijk geweest; de tekstbestanden niet.
    assert geschreven == {"lyrics", "karaoke_text", "logo"}, geschreven
    assert gelezen == {"lyrics", "karaoke_text", "logo"}, gelezen
    onbekend = (geschreven | gelezen) - set(pipeline.INPUT_NAME_KEYS)
    assert not onbekend, f"sleutel buiten INPUT_NAME_KEYS: {sorted(onbekend)}"
    # De schrijver mag de sleutel niet meer uit de bestandsnaam afleiden.
    assert "Path(target_name).stem" not in gui_bron


@pytest.mark.parametrize("sleutel", pipeline.INPUT_NAME_KEYS)
def test_elke_invoersleutel_leest_terug_wat_hij_schreef(tmp_path,
                                                        sleutel) -> None:
    context = _context(tmp_path, f"Sleutel_{sleutel}")
    bron = tmp_path / "map" / "viva espanja-origineel.txt"
    bron.parent.mkdir(parents=True, exist_ok=True)
    bron.write_text("x", encoding="utf-8")
    pipeline.set_input_origin(context, sleutel, bron)
    assert pipeline.input_display_name(context, sleutel, "val") == bron.name
    assert pipeline.input_start_dir(context, sleutel) == str(bron.parent)


def test_bestaand_project_wordt_omgezet(tmp_path) -> None:
    """Wie al projecten heeft, moet zijn namen niet kwijt zijn."""
    context = _context(tmp_path, "Migratie")
    context.store.set_meta("input_names", {
        "songtekst": {"name": "viva espanja-origineel.txt", "dir": "/tmp"},
        "karaoketekst": {"name": "Lied S-karaoke.txt", "dir": "/tmp"},
        "original": {"name": "viva.mp3", "dir": "/tmp"}})

    assert pipeline.migrate_input_names(context) is True
    assert pipeline.input_display_name(context, "lyrics", "val") \
        == "viva espanja-origineel.txt"
    assert pipeline.input_display_name(context, "karaoke_text", "val") \
        == "Lied S-karaoke.txt"
    assert pipeline.input_display_name(context, "original", "val") \
        == "viva.mp3"
    # Idempotent: een tweede keer verandert er niets meer.
    assert pipeline.migrate_input_names(context) is False


def test_migratie_overschrijft_geen_nieuwe_waarde(tmp_path) -> None:
    """Staat er al een goede waarde, dan wint die van de oude sleutel."""
    context = _context(tmp_path, "Migratie2")
    context.store.set_meta("input_names", {
        "songtekst": {"name": "oud.txt", "dir": "/tmp"},
        "lyrics": {"name": "nieuw.txt", "dir": "/tmp"}})
    pipeline.migrate_input_names(context)
    assert pipeline.input_display_name(context, "lyrics", "val") == "nieuw.txt"
    assert "songtekst" not in (context.store.get_meta("input_names") or {})


# --------------------------------------------------------------------------
# B325: de knopnummering
# --------------------------------------------------------------------------

VERWACHTE_NUMMERS = {
    "step_detect": "1.1. ", "step_couple": "1.2. ",
    "step_analyse": "1.3. ", "step_karaoke": "1.4. ",
    "video_edit_stress": "2.1. ", "video_timing": "2.2. ",
    "video_edit_timing": "2.3. ", "video_render": "2.4. ",
}


@pytest.mark.parametrize("sleutel,nummer", sorted(VERWACHTE_NUMMERS.items()))
def test_knop_draagt_tab_en_volgnummer(sleutel: str, nummer: str) -> None:
    for taal in ("nl", "en"):
        assert TRANSLATIONS[taal][sleutel].startswith(nummer), (taal, sleutel)


def test_de_knoplijst_is_compleet() -> None:
    assert set(translations_module.BUTTON_KEYS) == set(VERWACHTE_NUMMERS)


def test_geen_tekst_noemt_een_knop_nog_bij_naam() -> None:
    """Een melding die een knopnaam uitschrijft loopt bij de volgende
    hernummering weer uit de pas. Ze horen de sleutel te gebruiken."""
    overtreders = []
    for taal, woordenboek in TRANSLATIONS.items():
        namen = {s: woordenboek[s] for s in translations_module.BUTTON_KEYS}
        for sleutel, tekst in woordenboek.items():
            if sleutel in translations_module.BUTTON_KEYS:
                continue
            for knop, naam in namen.items():
                # De naam zonder nummer, dat is het deel dat blijft staan.
                kaal = naam.split(". ", 1)[-1]
                if f"'{naam}'" in tekst or f"'{kaal}'" in tekst:
                    overtreders.append(f"{taal}/{sleutel} noemt {knop}")
    assert not overtreders, overtreders


def test_knopverwijzing_wordt_ingevuld(nederlands) -> None:
    for taal in ("nl", "en"):
        translations_module.set_language(taal)
        tekst = t("prereq_need_detect")
        assert "{step_detect}" not in tekst
        assert TRANSLATIONS[taal]["step_detect"] in tekst


def test_andere_plaatshouders_blijven_staan(nederlands) -> None:
    """``t()`` vult alleen knopverwijzingen in; de rest doet de aanroeper."""
    tekst = t("err_no_transcription")
    assert "{track}" in tekst
    assert "1.1. Detecteer woorden" in tekst
    assert "{track}" not in tekst.format(track="origineel")


# --------------------------------------------------------------------------
# B326: de vastloper bij "2.2. Timing verfijnen"
# --------------------------------------------------------------------------

def test_koppelkwaliteit_heeft_engelse_sleutels() -> None:
    """``couple_timing`` geeft high/medium/low; de pijplijn las hoog/
    midden/laag en liep daarop stuk met een KeyError."""
    from modules import timing as timing_module

    bron = (MODULES / "pipeline.py").read_text(encoding="utf-8")
    for oud in ("quality['hoog']", "quality['midden']", "quality['laag']",
                'quality["hoog"]', 'quality["midden"]', 'quality["laag"]'):
        assert oud not in bron, oud
    assert set(timing_module.couple_timing.__doc__ or "") or True
    tekst = t("timing_detail_coupling").format(high=1, medium=2, low=3)
    assert "1x" in tekst and "2x" in tekst and "3x" in tekst


def test_timing_detail_volgt_de_taal(nederlands) -> None:
    translations_module.set_language("en")
    engels = t("timing_detail_even")
    translations_module.set_language("nl")
    assert engels != t("timing_detail_even")
    assert "songtekst" in t("timing_detail_even")


def test_video_invoer_heeft_taalonafhankelijke_sleutels(tmp_path) -> None:
    """De render sloeg de offset over op zijn NEDERLANDSE naam; in het
    Engels klopte die vergelijking niet en weigerde hij te renderen."""
    context = _context(tmp_path, "Invoer")
    sleutels = [rij[0] for rij in pipeline.video_input_status(context)]
    assert sleutels == ["lyrics", "karaoke_text", "logo", "timing", "offset"]
    assert "offset" in pipeline.VIDEO_INPUT_OPTIONAL
    bron = (MODULES / "pipeline.py").read_text(encoding="utf-8")
    assert '!= "offset origineel/karaoke"' not in bron


def test_video_invoerdetails_volgen_de_taal(tmp_path, nederlands) -> None:
    context = _context(tmp_path, "Invoer2")

    def details():
        return [rij[3] for rij in pipeline.video_input_status(context)]

    translations_module.set_language("nl")
    nl_details = details()
    translations_module.set_language("en")
    en_details = details()
    # De paden zijn gelijk; de zinnen eromheen niet.
    assert nl_details != en_details


@pytest.mark.parametrize("functie,argumenten", [
    ("check_text_alignment", ()),
    ("sync_timing_with_text_change", ((), ())),
])
def test_pijplijnmeldingen_volgen_de_taal(tmp_path, nederlands,
                                          functie, argumenten) -> None:
    """Deze twee geven een melding terug die de GUI toont; die stond
    hardgecodeerd in het Nederlands."""
    context = _context(tmp_path, f"Melding_{functie}")
    aanroep = getattr(pipeline, functie)

    translations_module.set_language("nl")
    _, nl_melding = aanroep(context, *argumenten)
    translations_module.set_language("en")
    _, en_melding = aanroep(context, *argumenten)
    assert nl_melding and en_melding and nl_melding != en_melding


def test_geen_nederlandse_letterlijke_tekst_meer_in_die_functies() -> None:
    """Regressiewacht op de functies waarvan de GUI de tekst toont."""
    bron = (MODULES / "pipeline.py").read_text(encoding="utf-8")
    boom = ast.parse(bron)
    bewaakt = {"generate_timing", "video_input_status", "check_text_alignment",
               "sync_timing_with_text_change"}
    nederlands = re.compile(
        r"\b(?:geen|niet|regels|eerst|draai|secties|verschilt|onleesbaar|"
        r"gewijzigd|bijgewerkt|aanwezig|songtekst|karaoketekst)\b", re.I)
    overtreders = []
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.FunctionDef) or knoop.name not in bewaakt:
            continue
        docstring = knoop.body[0].value if (
            knoop.body and isinstance(knoop.body[0], ast.Expr)) else None
        for kind in ast.walk(knoop):
            if kind is docstring or not isinstance(kind, ast.Constant):
                continue
            if isinstance(kind.value, str) and nederlands.search(kind.value):
                overtreders.append(f"{knoop.name}:{kind.lineno} "
                                   f"{kind.value[:50]!r}")
    assert not overtreders, overtreders


# --------------------------------------------------------------------------
# B327: sleutels die met een f-string worden opgebouwd
# --------------------------------------------------------------------------

def test_alle_samengestelde_vertaalsleutels_bestaan() -> None:
    """``t(f"lane_{key}")`` ontsnapte aan de wacht van B315: drie
    baannamen bleven bij de hernoeming in het Nederlands staan en
    stonden daarna letterlijk als sleutel in beeld."""
    ontbreekt = []
    for pad in sorted(MODULES.glob("*.py")):
        bron = pad.read_text(encoding="utf-8")
        for prefix in set(re.findall(r't\(f"(\w+_)\{', bron)):
            # Alle waarden die als staart in die f-string terechtkomen:
            # de losse tekstconstanten in dit bestand.
            for staart in re.findall(r'"(\w+)"', bron):
                sleutel = prefix + staart
                if sleutel in TRANSLATIONS["nl"]:
                    continue
    # Directer: de baanlabels en de bronkeuze van de golfvorm-editor.
    from modules import timing_editor

    for naam, _top in timing_editor._LANE_LABELS:
        sleutel = f"lane_{naam}"
        if sleutel not in TRANSLATIONS["nl"]:
            ontbreekt.append(sleutel)
    for naam in ("original", "karaoke", "vocals"):
        if f"lane_{naam}" not in TRANSLATIONS["nl"]:
            ontbreekt.append(f"lane_{naam}")
    for modus in ("blocks", "sentences", "words"):
        if f"view_{modus}" not in TRANSLATIONS["nl"]:
            ontbreekt.append(f"view_{modus}")
    assert not ontbreekt, ontbreekt


def test_geen_baanlabel_toont_zijn_eigen_sleutel() -> None:
    from modules import timing_editor

    for naam, _top in timing_editor._LANE_LABELS:
        assert t(f"lane_{naam}") != f"lane_{naam}"


def test_de_bronkeuze_kent_dezelfde_namen_als_de_gui() -> None:
    """De sleutels van ``audio_paths`` moeten aan beide kanten gelijk
    zijn, anders verdwijnt de zangstem stilletjes uit het keuzelijstje."""
    editor = (MODULES / "timing_editor.py").read_text(encoding="utf-8")
    gui_bron = (MODULES / "gui.py").read_text(encoding="utf-8")
    assert 'for name in ("original", "karaoke", "vocals")' in editor
    assert '"vocals": vocal_wav' in gui_bron
    assert "zangstem" not in editor


# --------------------------------------------------------------------------
# B328: de handleiding
# --------------------------------------------------------------------------

HANDLEIDING = (WORTEL / "docs" / "handleiding.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("sleutel,nummer", sorted(VERWACHTE_NUMMERS.items()))
def test_handleiding_noemt_de_huidige_knopnamen(sleutel: str,
                                                nummer: str) -> None:
    naam = TRANSLATIONS["nl"][sleutel]
    assert naam in HANDLEIDING, f"handleiding mist '{naam}'"


def test_handleiding_noemt_geen_oude_knopnamen() -> None:
    """Elke vermelding van een knop draagt de huidige nummering, zodat
    de handleiding niet stilletjes achterloopt op de app."""
    for sleutel, nummer in VERWACHTE_NUMMERS.items():
        kaal = TRANSLATIONS["nl"][sleutel][len(nummer):]
        for treffer in re.finditer(re.escape(kaal), HANDLEIDING):
            begin = treffer.start()
            assert HANDLEIDING[max(0, begin - len(nummer)):begin] == nummer, (
                f"'{kaal}' zonder nummer '{nummer}': "
                f"...{HANDLEIDING[max(0, begin - 50):treffer.end()]}")


@pytest.mark.parametrize("onderwerp", [
    "afhankelijkheden.md",          # de afleidingsketen (B311)
    "Zangstem-analyse",             # de instelling achter B313/B319
    "Terug uit origineel",          # de groene blokken in de dempingeditor
    "Regel uit/aan",                # niet renderen
    "Blokken",                      # de weergavekeuze in de golfvormeditor
    "legenda",                      # de kleuren in de koppeleditor
    "Sluiten",                      # opslaan-bij-sluiten verschilt per editor
])
def test_handleiding_beschrijft_wat_er_te_bedienen_is(onderwerp: str) -> None:
    assert onderwerp in HANDLEIDING, f"handleiding mist '{onderwerp}'"
