"""Tests voor v0.100.0: B316 tot en met B322.

B316 - de beginprompt is een hint, geen bron: een songtekst-override mag
       de transcriptie niet wissen.
B317 - de markeringen staan in een legenda, niet vóór het woord.
B318 - de gezongen tijd wordt gewogen op lettergrepen verdeeld.
B319 - het einde van de zang is een anker: niets loopt erna door, en de
       staart wordt van achteren naar voren gepast.
B320 - ongekoppelde woorden staan boven elkaar.
B321 - een klik levert het aangewezen woord op.
B322 - het venster start groot genoeg voor zijn eigen inhoud.
"""
from __future__ import annotations

import os
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import dependencies as deps  # noqa: E402
from modules import pipeline  # noqa: E402
from modules import timing as timing_module  # noqa: E402
from modules.song_text import AlignedWord, LyricWord  # noqa: E402


# --------------------------------------------------------------------------
# B316: wat een bronwijziging juist NIET mag kosten
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bron,gespaard", [
    # De songtekst gaat als beginprompt mee naar Whisper, maar een
    # correctie op de woordenlijst in de koppeleditor is geen reden om
    # een transcriptie van tweeënhalve minuut rekenwerk weg te gooien.
    ("lyrics_override", "whisper_original"),
    ("lyrics_override", "cache:transcription_original"),
    ("lyrics_override", "analysis_original"),
    ("transcript_override", "whisper_original"),
    ("word_coupling", "whisper_original"),
])
def test_bronwijziging_spaart_de_transcriptie(bron: str,
                                              gespaard: str) -> None:
    assert gespaard not in deps.dependents([bron])


def test_songtekst_zelf_vervangen_raakt_de_transcriptie_wel() -> None:
    """De andere kant: het BESTAND vervangen is een echte tekstwijziging
    en dan is een nieuwe transcriptie op zijn plaats."""
    assert "whisper_original" in deps.dependents(["input:lyrics"])


def test_override_raakt_wel_alles_wat_op_de_woordenlijst_telt() -> None:
    """Knippen of samenvoegen hernummert de songtekstwoorden, dus alles
    wat op die posities telt vervalt wel degelijk."""
    gevolgen = deps.dependents(["lyrics_override"])
    for naam in ("word_coupling", "original_overrides", "stress_anchors",
                 "coupling", "timing"):
        assert naam in gevolgen, naam


# --------------------------------------------------------------------------
# B318: wegen op lettergrepen
# --------------------------------------------------------------------------

def test_verdeling_weegt_op_lettergrepen() -> None:
    """"Espagna" (drie lettergrepen) hoort meer tijd te krijgen dan "e"."""
    gelijk = timing_module.spread_over_active(3, [(0.0, 6.0)])
    gewogen = timing_module.spread_over_active(3, [(0.0, 6.0)],
                                               weights=[1, 3, 2])
    assert [round(e - s, 2) for s, e in gelijk] == [2.0, 2.0, 2.0]
    assert [round(e - s, 2) for s, e in gewogen] == [1.0, 3.0, 2.0]


def test_verdeling_zonder_gewichten_blijft_gelijk() -> None:
    """Zonder gewichten (of met een verkeerd aantal) verandert er niets
    aan het oude gedrag."""
    zonder = timing_module.spread_over_active(4, [(0.0, 8.0)])
    fout_aantal = timing_module.spread_over_active(4, [(0.0, 8.0)],
                                                   weights=[1, 2])
    assert zonder == fout_aantal


def test_verdeling_vult_het_venster_precies() -> None:
    """Gewogen of niet: de slots samen beslaan het hele venster, zonder
    gat en zonder overlap."""
    slots = timing_module.spread_over_active(5, [(10.0, 20.0)],
                                             weights=[1, 4, 2, 1, 2])
    assert round(slots[0][0], 3) == 10.0
    assert round(slots[-1][1], 3) == 20.0
    for links, rechts in zip(slots, slots[1:]):
        assert round(links[1], 3) == round(rechts[0], 3)


# --------------------------------------------------------------------------
# B319: het einde van de zang als anker
# --------------------------------------------------------------------------

def _woorden(spec):
    uit = []
    for index, (tekst, start, sim) in enumerate(spec):
        uit.append(AlignedWord(
            LyricWord(index=index, text=tekst, line=index // 4),
            start, None if start is None else start + 0.3,
            tekst if start is not None else None, sim))
    return tuple(uit)


def test_koppeling_na_het_einde_van_de_zang_wordt_losgemaakt() -> None:
    """Whisper schrijft na de laatste zang soms nog iets op (applaus, een
    uitfade, een hallucinatie). Een songtekstwoord dat daaraan hangt ligt
    voorbij het einde van het lied en trekt alles ervóór scheef."""
    aligned = _woorden([("een", 1.0, 1.0), ("twee", 2.0, 1.0),
                        ("drie", 40.0, 1.0)])
    uit = pipeline._drop_couplings_after(aligned, song_end=30.0)
    assert uit[0].start == 1.0 and uit[1].start == 2.0
    assert uit[2].start is None and uit[2].matched_text is None


def test_koppeling_vlak_voor_het_einde_blijft_staan() -> None:
    aligned = _woorden([("een", 29.9, 1.0)])
    assert pipeline._drop_couplings_after(aligned, 30.0)[0].start == 29.9


def test_staart_wordt_van_achteren_naar_voren_gepast() -> None:
    """Een reeks aan het eind heeft geen anker erachter, dus het venster
    loopt door tot waar de zang stopt. Biedt dat veel meer tijd dan de
    woorden nodig hebben, dan is terugtellen vanaf het einde de betere
    pasvorm - daar ligt immers de zekerheid."""
    vensters = [(0.0, 10.0), (20.0, 30.0)]
    gepast = pipeline._fit_from_the_back(vensters, needed=4.0)
    assert gepast == [(26.0, 30.0)]


def test_van_achteren_passen_pakt_meer_vensters_als_het_moet() -> None:
    vensters = [(0.0, 10.0), (20.0, 24.0)]
    gepast = pipeline._fit_from_the_back(vensters, needed=6.0)
    assert gepast == [(8.0, 10.0), (20.0, 24.0)]


def test_van_achteren_passen_laat_alles_staan_als_het_krap_is() -> None:
    """Past het net of is er te weinig, dan verandert er niets."""
    vensters = [(0.0, 4.0)]
    assert pipeline._fit_from_the_back(vensters, needed=10.0) == vensters


def test_lettergreepduur_wordt_op_het_lied_zelf_gemeten() -> None:
    """De duur van een lettergreep volgt het tempo van dit nummer,
    gemeten op de goed gekoppelde woorden."""
    aligned = tuple(
        AlignedWord(LyricWord(i, "la", 0), float(i), float(i) + 0.5,
                    "la", 1.0)
        for i in range(6))
    assert 0.4 <= pipeline._seconds_per_syllable(aligned) <= 0.6


def test_lettergreepduur_valt_terug_zonder_metingen() -> None:
    aligned = _woorden([("een", None, 0.0)])
    assert pipeline._seconds_per_syllable(aligned) == \
        pipeline._DEFAULT_SECONDS_PER_SYLLABLE


def test_einde_van_de_zang_staat_in_de_keten() -> None:
    """Het einde is net zo goed een afgeleide van de zangstem als het
    begin; zonder plek in de keten zou het een nieuwe bronwijziging
    overleven."""
    assert "vocal_end_s" in deps.ARTEFACTS
    assert deps.ARTEFACTS["vocal_end_s"].sources == ("cache:demucs_original",)
    assert "vocal_end_s" in deps.dependents(["input:original"])


# --------------------------------------------------------------------------
# B320/B321: de koppeleditor
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _canvas(trans, koppelingen):
    """Canvas met ``koppelingen`` = per songtekstwoord de transcriptindices."""
    from modules.coupling_editor import CouplingCanvas

    woorden = [{"index": i, "text": f"L{i}", "transcript_indices": list(t),
                "pinned": False, "sim": 1.0 if t else 0.0, "line": 0}
               for i, t in enumerate(koppelingen)]
    return CouplingCanvas([(w, i * 1.0, i * 1.0 + 0.5)
                         for i, w in enumerate(trans)],
                        woorden, lambda *_a: None)


def test_ongekoppelde_woorden_staan_boven_elkaar(qapp) -> None:
    """Bij een lang ongekoppeld stuk liepen de rijen per woord een kolom
    uit elkaar: acht woorden was een verschuiving van 720 pixels."""
    trans = [f"T{i}" for i in range(10)]
    koppelingen = [[0]] + [[] for _ in range(8)] + [[9]]
    canvas = _canvas(trans, koppelingen)
    assert canvas._top_col == canvas._bot_col
    assert canvas._cols == 10


def test_gekoppelde_paren_blijven_boven_elkaar(qapp) -> None:
    """Wat al goed stond (B220) moet zo blijven."""
    canvas = _canvas(["T0", "T1", "T2"], [[0], [1], [2]])
    assert canvas._top_col == canvas._bot_col == [0, 1, 2]


def test_klik_landt_op_het_aangewezen_woord(qapp) -> None:
    """Een koppeling wordt automatisch uitgerekt naar aangrenzende
    gevonden woorden (B191), en die groep werd als één breed vak getekend.
    Elke klik daarin gaf het EERSTE woord van de groep terug, zodat een
    koppeling op het woord links van je aanwijzer landde."""
    from PySide6.QtCore import QPoint

    from modules.coupling_editor import _PATH, _PPW, _TOP_Y

    canvas = _canvas(["formi", "dable", "nous"], [[0, 1], []])
    for index in range(3):
        x = _PATH + canvas._top_col[index] * _PPW + 20
        assert canvas._hit_row(QPoint(x, _TOP_Y + 5), top=True) == index


def test_legenda_beschrijft_elke_markering(qapp) -> None:
    """De legenda wordt uit dezelfde tabel gebouwd als waarmee getekend
    wordt, zodat een nieuwe markering niet in beeld kan komen zonder
    uitleg."""
    from modules import translations
    from modules.coupling_editor import _STATUS_STYLE, legend_html

    html = legend_html()
    for fill, _border, sleutel in _STATUS_STYLE.values():
        assert fill.name() in html
        assert translations.t(sleutel) in html


def test_geen_markering_meer_voor_het_woord(qapp) -> None:
    """De codes ``[vul]``/``[hal]``/``[zang]`` stonden vóór het woord en
    maakten het slechter leesbaar; ze horen in de legenda.

    Structureel getoetst in plaats van op tekst: het derde veld van de
    stijltabel is nu een vertaalsleutel, geen label dat voor het woord
    geplakt wordt."""
    from modules import translations
    from modules.coupling_editor import _STATUS_STYLE

    for _fill, _border, derde in _STATUS_STYLE.values():
        assert derde.startswith("legend_"), derde
        assert not derde.strip().startswith("["), derde
        assert derde in translations.TRANSLATIONS["nl"]


# --------------------------------------------------------------------------
# B322: de opstarthoogte
# --------------------------------------------------------------------------

def test_venster_start_groot_genoeg_voor_zijn_inhoud(qapp, tmp_path) -> None:
    """Het vensterminimum staat bewust onder wat de layout nodig heeft,
    zodat krimpen mag. Daardoor kon het venster starten op een maat
    waarop de groepsvakken hun tekst over elkaar heen tekenden."""
    from modules import gui
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    window = gui.MainWindow(context)
    nodig = window.centralWidget().layout().minimumSize()
    scherm = window.screen()
    ruimte = scherm.availableGeometry() if scherm is not None else None

    # Groot genoeg, of anders begrensd door wat het scherm biedt.
    if ruimte is None or ruimte.height() >= nodig.height():
        assert window.height() >= nodig.height()
    else:
        assert window.height() >= ruimte.height() - 1
    assert window.width() >= min(nodig.width(),
                                 ruimte.width() if ruimte else nodig.width())


def test_kleiner_maken_blijft_toegestaan(qapp, tmp_path) -> None:
    """De gebruiker mag het venster daarna zo klein maken als hij wil."""
    from modules import gui
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef2")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    window = gui.MainWindow(context)
    assert window.minimumHeight() < window.centralWidget().layout() \
        .minimumSize().height()
    window.resize(800, 560)
    assert window.height() == 560


# --------------------------------------------------------------------------
# Samenhang: de plaatsing blijft doen wat B313 beloofde
# --------------------------------------------------------------------------

def test_plaatsing_blijft_ordelijk_met_gewichten_en_einde(
        monkeypatch) -> None:
    """Met wegen en het einde-anker erbij blijft gelden: volgorde intact,
    goede koppelingen onaangeroerd, niets voorbij het einde."""
    from modules import rhythm

    aligned = _woorden([("start", 1.0, 1.0)]
                       + [(f"w{i}", None, 0.0) for i in range(6)]
                       + [("eind", 20.0, 1.0)])
    monkeypatch.setattr(rhythm, "active_windows",
                        lambda *_a, **_k: [(0.0, 25.0)])
    monkeypatch.setattr(pipeline, "ensure_original_vocals",
                        lambda _c: Path("nep.wav"))
    context = types.SimpleNamespace(
        config=types.SimpleNamespace(
            advanced=types.SimpleNamespace(vocal_analysis=True)),
        store=types.SimpleNamespace(get_step=lambda _n: None,
                                    set_meta=lambda *_a: None))
    uit = pipeline._place_skipped_on_energy(context, aligned)
    tijden = [w.start for w in uit if w.start is not None]
    assert tijden == sorted(tijden)
    assert uit[0].start == 1.0 and not uit[0].estimated
    assert uit[-1].start == 20.0 and not uit[-1].estimated
    assert all(w.end <= 25.1 for w in uit if w.end is not None)
