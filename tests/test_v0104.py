"""Tests voor v0.104.0: B334 tot en met B338.

B334 - een reeks woorden zonder tijdsduur op hetzelfde moment is
       Whispers herhaallus en gaat eruit.
B335 - een karaoke die uit het origineel is gemaakt heet ook zo.
B336 - de staart wordt over de zangvensters verdeeld, op hele frases.
B337 - hallucinatie- en vulwoordenlijsten horen bij de TAAL, worden op
       de PLEK in de songtekst getoetst, en zijn met de hand aan te
       vullen vanuit de koppel-editor.
B338 - de meetlat draait de echte pijplijn en laat de handmatige
       correcties van de gebruiker uit de invoer.
"""
from __future__ import annotations

import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import phonetics  # noqa: E402
from modules import pipeline  # noqa: E402
from modules import timing as T  # noqa: E402
from modules.whisper import Segment, Word  # noqa: E402


# --------------------------------------------------------------------------
# B334: de herhaallus
# --------------------------------------------------------------------------

def _segment(*woorden: tuple[str, float, float]) -> Segment:
    ws = tuple(Word(t, s, e, 0.9) for t, s, e in woorden)
    return Segment(0, " ".join(w[0] for w in woorden),
                   ws[0].start, ws[-1].end, ws)


def test_lus_van_vier_gaat_eruit() -> None:
    """Het gemeten geval: 34x "now," allemaal op exact 193.500 s, met een
    betrouwbaarheid van 0,98 - onzichtbaar voor elke inhoudelijke toets,
    maar een woord zonder tijdsduur kan nooit een timing opleveren."""
    seg = _segment(("echt", 10.0, 10.5), *[("now", 11.0, 11.0)] * 6)
    uit = pipeline._drop_repetition_loop((seg,))
    assert [w.text for w in uit[0].words] == ["echt"]


def test_korte_reeks_blijft_staan() -> None:
    """Acht van de elf projecten hebben geen enkel woord zonder duur,
    twee hebben er één en één heeft een reeks van drie. De drempel ligt
    daarboven, want dat drietal weghalen maakte dat lied meetbaar (zij
    het licht) slechter."""
    seg = _segment(("a", 1.0, 1.4), *[("oe", 2.0, 2.0)] * 3, ("b", 3.0, 3.4))
    uit = pipeline._drop_repetition_loop((seg,))
    assert len(uit[0].words) == 5


def test_zonder_lus_verandert_er_niets() -> None:
    seg = _segment(("een", 1.0, 1.4), ("twee", 1.4, 1.9), ("drie", 1.9, 2.5))
    assert pipeline._drop_repetition_loop((seg,)) == (seg,)


def test_losse_nulwoorden_op_andere_momenten_tellen_niet() -> None:
    """Alleen een reeks op HETZELFDE moment is de lus; losse nul-woorden
    verspreid door het lied zijn iets anders."""
    seg = _segment(("a", 1.0, 1.0), ("b", 2.0, 2.0), ("c", 3.0, 3.0),
                   ("d", 4.0, 4.0))
    assert len(pipeline._drop_repetition_loop((seg,))[0].words) == 4


def test_segment_dat_helemaal_lus_is_verdwijnt() -> None:
    seg = _segment(*[("now", 5.0, 5.0)] * 8)
    assert pipeline._drop_repetition_loop((seg,)) == ()


# --------------------------------------------------------------------------
# B336: de staart over de zangvensters
# --------------------------------------------------------------------------

def test_hele_frases_krijgen_regels() -> None:
    """Het gemeten geval: 14,56 s = 3,90 frases -> 4 regels, 29,88 s =
    8,01 -> 8 regels, terwijl een piekje van 0,88 s en een uithaal van
    4,78 s er geen krijgen."""
    vensters = [(133.07, 147.63), (160.43, 161.31), (172.06, 176.84),
                (177.75, 207.63)]
    uit = T.tail_over_windows(12, vensters, 3.73, 131.98)
    assert uit is not None and len(uit) == 12
    assert math.isclose(uit[0], 133.07, abs_tol=0.01)
    assert math.isclose(uit[4], 177.75, abs_tol=0.01)


def test_klopt_het_aantal_niet_dan_niets_doen() -> None:
    """Liever niets dan een zelfverzekerde vergissing: als de vensters
    de staart niet precies verklaren houdt de aanroeper zijn eigen
    verdeling."""
    vensters = [(133.07, 147.63), (177.75, 207.63)]
    assert T.tail_over_windows(11, vensters, 3.73, 131.98) is None


def test_uithaal_van_anderhalve_frase_draagt_geen_regels() -> None:
    assert T.tail_over_windows(1, [(10.0, 14.78)], 3.73, 0.0) is None


def test_venster_voor_het_anker_telt_niet_mee() -> None:
    """Een venster dat nog bij het gekoppelde deel hoort wordt afgekapt
    op het laatste anker."""
    assert T.tail_over_windows(4, [(100.0, 132.12), (133.07, 147.63)],
                               3.73, 131.98) is not None


def test_zonder_vensters_of_periode_geen_uitspraak() -> None:
    assert T.tail_over_windows(4, [], 3.73, 0.0) is None
    assert T.tail_over_windows(4, [(0.0, 15.0)], 0.0, 0.0) is None


# --------------------------------------------------------------------------
# B337: de lijsten horen bij de taal
# --------------------------------------------------------------------------

@pytest.mark.parametrize("code", sorted(phonetics.LANGUAGES))
@pytest.mark.parametrize("kind", phonetics.WORD_LISTS)
def test_elke_ingebouwde_taal_heeft_beide_lijsten(code: str,
                                                  kind: str) -> None:
    """De bewaking die de gebruiker vroeg: er kan geen taal bijkomen
    zonder dat iemand een besluit neemt over zijn artefacten. Leeg mag,
    ontbreken niet."""
    assert kind in phonetics.LANGUAGES[code], f"{code} mist {kind}"


def test_onbekende_taal_begint_leeg() -> None:
    """Een Deens liedje maakt zijn eigen da.json met lege lijsten; er
    komt niets in de meegeleverde set terecht."""
    seed = phonetics.generate_language("da")
    assert seed["hallucinations"] == []
    assert seed["fillers"] == []


def test_lijst_is_meegeleverd_plus_verzameld() -> None:
    """Bewust een vereniging en niet 'de eerste wint' zoals bij de
    fonetiek: anders wordt een verzameld en.json voor een ingebouwde
    taal stilletjes genegeerd en gebeurt er niets als je een woord
    markeert."""
    try:
        assert phonetics.add_word("en", "hallucinations", "bye") is True
        woorden = phonetics.word_list("en", "hallucinations")
        assert "bye" in woorden and "thank" in woorden
        assert phonetics.add_word("en", "hallucinations", "bye") is False
    finally:
        phonetics.remove_word("en", "hallucinations", "bye")
    assert "bye" not in phonetics.word_list("en", "hallucinations")


def test_meegeleverd_woord_is_niet_met_de_hand_te_wissen() -> None:
    assert phonetics.remove_word("en", "hallucinations", "thank") is False
    assert "thank" in phonetics.word_list("en", "hallucinations")


def test_taalbestand_draagt_de_lijsten_mee() -> None:
    payload = phonetics.language_payload("en", "0.104.0")
    assert "hallucinations" in payload and "fillers" in payload
    assert "thank" in payload["hallucinations"]


def test_engelse_vulwoorden_dekken_thank_you() -> None:
    """"Thank you." is pas te filteren als "you" niet als kernwoord
    telt. Dat lost het vulwoordenlijstje op - veiliger dan "you" op de
    hallucinatielijst zetten, want dat woord staat in half Engeland."""
    assert "you" in phonetics.word_list("en", "fillers")
    assert "you" not in phonetics.word_list("en", "hallucinations")


def test_pijplijn_valt_terug_op_de_basislijst() -> None:
    """Zonder taalgegevens blijft het oude, kleine setje over."""
    assert "zang" in pipeline._language_words("xx", "hallucinations")
    assert pipeline._language_words("xx", "fillers")


# --------------------------------------------------------------------------
# B337: markeren vanuit de koppel-editor
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_alleen_een_oordeel_is_markeerbaar() -> None:
    """Van de vijf markeringen zijn er drie een meting - "Whisper hoorde
    hier niets", "getimed op de zangstem", "geen match". Die met de hand
    kunnen zetten zou iets beweren dat niet waar is."""
    from modules.coupling_editor import MARKABLE, _STATUS_STYLE

    assert set(MARKABLE) == {"hallucination_filtered", "filler_skipped"}
    assert set(MARKABLE) < set(_STATUS_STYLE)


def test_legenda_wordt_alleen_klikbaar_als_het_mag() -> None:
    from modules.coupling_editor import legend_html

    assert legend_html(clickable=True).count("<a href=") == 2
    assert legend_html().count("<a href=") == 0


def test_markeren_pakt_de_juiste_rij(qapp) -> None:
    """Hallucinatie gaat over wat Whisper vond (bovenste rij), vulwoord
    over de songtekst (onderste rij)."""
    from modules.coupling_editor import CouplingEditorDialog

    transcript = [("Thank", 1.0, 1.5), ("you", 1.5, 2.0)]
    woorden = [{"index": i, "text": f"L{i}", "transcript_indices": [],
                "pinned": False, "sim": 0.0, "line": 0} for i in range(2)]
    gezien: list[tuple[str, str]] = []
    dialoog = CouplingEditorDialog(
        transcript, woorden, lambda pins: None,
        on_mark=lambda kind, word: (gezien.append((kind, word)) or True))

    dialoog._canvas._sel_top = 0
    dialoog._mark_selected("hallucination_filtered")
    assert gezien == [("hallucinations", "Thank")]
    assert 0 in dialoog._canvas._filtered

    dialoog._canvas._sel_top = None
    dialoog._canvas._sel_bot = 1
    dialoog._mark_selected("filler_skipped")
    assert gezien[-1] == ("fillers", "L1")
    assert woorden[1]["status"] == "filler_skipped"


def test_nog_eens_klikken_haalt_de_markering_weg(qapp) -> None:
    from modules.coupling_editor import CouplingEditorDialog

    dialoog = CouplingEditorDialog(
        [("Thank", 1.0, 1.5)], [], lambda pins: None,
        on_mark=lambda kind, word: True)
    dialoog._canvas._sel_top = 0
    dialoog._mark_selected("hallucination_filtered")
    dialoog._mark_selected("hallucination_filtered")
    assert not dialoog._canvas._filtered


def test_een_meting_is_niet_te_zetten(qapp) -> None:
    from modules.coupling_editor import CouplingEditorDialog

    gezien = []
    dialoog = CouplingEditorDialog(
        [("iets", 1.0, 1.5)], [], lambda pins: None,
        on_mark=lambda kind, word: (gezien.append(kind) or True))
    dialoog._canvas._sel_top = 0
    for status in ("transcription_gap", "energy_placed", "no_match"):
        dialoog._mark_selected(status)
    assert gezien == []


# --------------------------------------------------------------------------
# B335: het label bij een karaoke uit het origineel
# --------------------------------------------------------------------------

def test_label_bestaat_in_beide_talen() -> None:
    from modules.translations import TRANSLATIONS

    for taal in ("nl", "en"):
        assert TRANSLATIONS[taal]["karaoke_from_original_label"].strip()


def test_uit_origineel_wint_van_de_bestandsnaam(qapp, tmp_path) -> None:
    """De vlag hangt in de afleidingsketen aan input:karaoke, dus zodra
    er alsnog een echte karaoke wordt gekozen komt de naam vanzelf
    terug."""
    from modules import gui
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)
    from modules.translations import t

    paths = ProjectPaths(root=tmp_path, song="Label")
    ensure_directories(paths)
    (paths.input_dir / "karaoke.wav").write_bytes(b"x")
    store = ProjectStore(paths.project_file)
    store.set_meta("karaoke_from_original", True)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=store)
    window = gui.MainWindow(context)
    window._refresh_inputs()
    assert window._input_labels[pipeline.TRACK_KARAOKE].text() == \
        t("karaoke_from_original_label")

    # Een echt gekozen bestand wint weer.
    pipeline.set_input_origin(context, pipeline.TRACK_KARAOKE,
                              tmp_path / "mijn karaoke.wav")
    window._refresh_inputs()
    assert window._input_labels[pipeline.TRACK_KARAOKE].text() == \
        "mijn karaoke.wav"


# --------------------------------------------------------------------------
# B338: de meetlat meet de tool, niet het handwerk
# --------------------------------------------------------------------------

def test_meetlat_laat_de_handmatige_stappen_weg() -> None:
    """De opgeslagen koppeling bevat de correcties van de gebruiker op de
    originele baan - in één project 58 van de 64 zinnen. Daartegen meten
    is jezelf nakijken."""
    import importlib.util
    from pathlib import Path

    pad = Path(__file__).resolve().parents[1] / "tools" / \
        "timing_regression.py"
    spec = importlib.util.spec_from_file_location("timing_regression", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for stap in ("original_overrides", "word_coupling", "lyrics_override",
                 "coupling"):
        assert stap in module.MANUAL_STEPS
