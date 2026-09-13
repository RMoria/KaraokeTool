"""Tests for v0.97.0: B307, B308, B309 and B310.

B307 - the hallucination check also looks at the POSITION of a segment.
B308 - a hole in the transcription gets its own status.
B309 - the filtered out found words stay visible and can be coupled.
B310 - a la-la/na-na series is timed on where the singing really is.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from modules import pipeline, song_text
from modules import timing as timing_module
from modules.song_text import LyricWord
from modules.whisper import Segment, Word


# --------------------------------------------------------------------------
# B307: position-aware hallucination check
# --------------------------------------------------------------------------

def _lyrics(text: str) -> tuple[LyricWord, ...]:
    return tuple(LyricWord(index=i, text=w, line=0)
                 for i, w in enumerate(text.split()))


def _aligned(lyrics, coupling: dict[int, float]):
    """Minimal alignment: lyrics index -> start time (sim 0.95)."""
    from modules.song_text import AlignedWord
    return tuple(
        AlignedWord(lyrics[i],
                    coupling.get(i), None if i not in coupling
                    else coupling[i] + 0.4,
                    lyrics[i].text if i in coupling else None,
                    0.95 if i in coupling else 0.0)
        for i in range(len(lyrics)))


def test_positie_venster_ligt_tussen_de_dichtstbijzijnde_ankers() -> None:
    """Het venster loopt van het laatste anker vóór het segment tot het
    eerste anker erna - dat is precies wat de songtekst wél weet: niet de
    tijd, maar de volgorde."""
    lyrics = _lyrics(" ".join(f"w{i}" for i in range(40)))
    anchors = [(1.0, 5), (2.0, 10), (30.0, 35)]
    seg = Segment(0, "iets", 3.0, 4.0, ())
    lo, hi = pipeline._position_window(seg, anchors, len(lyrics))
    assert lo == 10 and hi == 35


def test_positie_venster_wordt_verbreed_tot_een_minimum() -> None:
    """Twee ankers vlak na elkaar leveren een venster van één of twee
    woorden op; daar matcht bijna niets mee en dan zou de check elk
    segment beschuldigen. Het venster wordt daarom verbreed."""
    lyrics = _lyrics(" ".join(f"w{i}" for i in range(40)))
    anchors = [(1.0, 20), (2.0, 21)]
    seg = Segment(0, "iets", 1.4, 1.6, ())
    lo, hi = pipeline._position_window(seg, anchors, len(lyrics))
    assert hi - lo + 1 >= pipeline._POSITION_WINDOW_MIN_WORDS


def test_positie_venster_blijft_binnen_de_songtekst() -> None:
    """Verbreden mag nooit buiten de songtekst wijzen."""
    lyrics = _lyrics("een twee drie")
    seg = Segment(0, "iets", 9.0, 9.5, ())
    lo, hi = pipeline._position_window(seg, [(1.0, 1)], len(lyrics))
    assert lo == 0 and hi == len(lyrics) - 1


def test_hallucinatie_die_liedbreed_matcht_maar_niet_op_die_plek() -> None:
    """De kern van B307: "SPANNENDE MUZIEK" in de outro scoort liedbreed
    een perfecte match, want "muziek" wordt halverwege het eerste couplet
    echt gezongen. Op de plek waar het segment staat komt dat woord
    nergens voor, en dan is het een hallucinatie."""
    lyrics = _lyrics(
        "ik hou van dansen en muziek e viva espagna van oude trots en "
        "romantiek geef mij maar alle dagen zon espagna por favor ole "
        "lalaala lalalalalaa e viva espagna lalaala lalalalalaa")
    zon = next(i for i, w in enumerate(lyrics) if w.text == "zon")
    segments = (
        Segment(0, "geef mij maar alle dagen zon", 10.0, 12.0,
                (Word("zon", 11.5, 12.0, 0.95),)),
        Segment(1, "SPANNENDE MUZIEK", 40.0, 41.0,
                (Word("SPANNENDE", 40.0, 40.5, 0.31),
                 Word("MUZIEK", 40.5, 41.0, 0.42))),
    )
    aligned = _aligned(lyrics, {zon: 11.5})
    weg: list = []
    kept = pipeline._filter_hallucinations_in_position(
        segments, lyrics, aligned, dropped_out=weg)

    assert [s.index for s in kept] == [0]
    assert [s.text for s in weg] == ["SPANNENDE MUZIEK"]
    # Liedbreed zou hetzelfde segment blijven staan: "muziek" komt echt
    # in de songtekst voor. Dat is precies waarom de positie nodig is.
    assert pipeline._filter_hallucinations(segments, lyrics) == segments


def test_segment_met_een_koppeling_wordt_nooit_weggegooid() -> None:
    """Als de uitlijning binnen een segment iets heeft gekoppeld, is het
    per definitie geen hallucinatie - hoe slecht de rest ook matcht."""
    lyrics = _lyrics("geef mij maar alle dagen zon espagna por favor ole "
                     "lalaala lalalalalaa e viva espagna")
    segments = (Segment(0, "zon xyzzy plugh", 11.0, 12.0,
                        (Word("zon", 11.0, 11.3, 0.9),
                         Word("xyzzy", 11.3, 11.6, 0.1),
                         Word("plugh", 11.6, 12.0, 0.1))),)
    aligned = _aligned(lyrics, {5: 11.0})
    assert pipeline._filter_hallucinations_in_position(
        segments, lyrics, aligned) == segments


def test_hoge_zekerheid_beschermt_tegen_de_positiecheck() -> None:
    """Hetzelfde vangnet als in B285: als Whisper zelf van elk woord
    zeker was, laten we het staan - dat kan een ad lib zijn."""
    lyrics = _lyrics("geef mij maar alle dagen zon espagna por favor ole "
                     "lalaala lalalalalaa e viva espagna")
    segments = (Segment(0, "compleet andere tekst", 40.0, 41.0,
                        (Word("compleet", 40.0, 40.3, 0.99),
                         Word("andere", 40.3, 40.6, 0.98),
                         Word("tekst", 40.6, 41.0, 0.97))),)
    aligned = _aligned(lyrics, {5: 11.0})
    assert pipeline._filter_hallucinations_in_position(
        segments, lyrics, aligned) == segments


def test_zonder_ankers_doet_de_positiecheck_niets() -> None:
    """Zonder één enkel gekoppeld woord is er geen positie te bepalen;
    dan mag de check niet gokken."""
    lyrics = _lyrics("geef mij maar alle dagen zon espagna por favor")
    segments = (Segment(0, "compleet anders", 40.0, 41.0,
                        (Word("compleet", 40.0, 40.5, 0.1),
                         Word("anders", 40.5, 41.0, 0.1))),)
    aligned = _aligned(lyrics, {})
    assert pipeline._filter_hallucinations_in_position(
        segments, lyrics, aligned) == segments


# --------------------------------------------------------------------------
# B308: a hole in the transcription is its own cause
# --------------------------------------------------------------------------

def test_transcriptie_gat_wordt_herkend() -> None:
    """Geen enkel bewaard segment in het ankervenster en het venster is
    lang: dan heeft Whisper hier simpelweg niets geproduceerd."""
    lyrics = _lyrics("een twee drie vier")
    aligned = _aligned(lyrics, {0: 1.0, 3: 30.0})
    segments = (Segment(0, "een", 1.0, 1.4, ()),
                Segment(1, "vier", 30.0, 30.4, ()))
    assert pipeline._word_in_transcription_gap(aligned, 1, segments) is True
    assert pipeline._word_in_transcription_gap(aligned, 2, segments) is True


def test_transcriptie_gat_niet_als_er_wel_tekst_staat() -> None:
    """Staat er in het venster wél een bewaard segment, dan is het gat
    niet de oorzaak - het woord matchte gewoon nergens op."""
    lyrics = _lyrics("een twee drie vier")
    aligned = _aligned(lyrics, {0: 1.0, 3: 30.0})
    segments = (Segment(0, "een", 1.0, 1.4, ()),
                Segment(1, "iets anders", 12.0, 14.0, ()),
                Segment(2, "vier", 30.0, 30.4, ()))
    assert pipeline._word_in_transcription_gap(aligned, 1, segments) is False


def test_kort_gaatje_telt_niet_als_transcriptie_gat() -> None:
    """Een normale pauze tussen twee regels is geen gat."""
    lyrics = _lyrics("een twee drie")
    aligned = _aligned(lyrics, {0: 1.0, 2: 2.0})
    segments = (Segment(0, "een", 1.0, 1.4, ()),
                Segment(1, "drie", 2.0, 2.4, ()))
    assert pipeline._word_in_transcription_gap(aligned, 1, segments) is False


def test_transcriptie_gat_gaat_voor_op_hallucinatie(tmp_path: Path) -> None:
    """De echte Viva-situatie: na het laatste gekoppelde woord komt er
    27 seconden lang niets meer uit Whisper, met daarin één weggefilterde
    hallucinatie. De oorzaak is het gat, niet de hallucinatie - anders
    wijst de editor de gebruiker de verkeerde kant op."""
    lyrics = _lyrics("een twee drie vier vijf")
    aligned = _aligned(lyrics, {0: 1.0})
    clean = (Segment(0, "een", 1.0, 1.4, ()),)
    dropped = [Segment(1, "Heerlijke Heer", 20.0, 22.0, ())]
    assert pipeline._word_in_transcription_gap(aligned, 3, clean) is True
    assert pipeline._word_overlaps_dropped_segment(aligned, 3, dropped) is True


# --------------------------------------------------------------------------
# B309: filtered found words stay visible and can be coupled
# --------------------------------------------------------------------------

def test_volledige_transcriptie_bevat_de_gefilterde_woorden() -> None:
    """De bovenste rij toont alles wat Whisper heeft geproduceerd, met de
    posities van de weggefilterde woorden erbij."""
    segments = (
        Segment(0, "een", 1.0, 1.5, (Word("een", 1.0, 1.5, 0.9),)),
        Segment(1, "MUZIEK", 2.0, 2.5, (Word("MUZIEK", 2.0, 2.5, 0.3),)),
        Segment(2, "twee", 3.0, 3.5, (Word("twee", 3.0, 3.5, 0.9),)),
    )
    clean = (segments[0], segments[2])
    transcript, filtered = pipeline._full_transcript(segments, clean)
    assert [w for w, _s, _e in transcript] == ["een", "MUZIEK", "twee"]
    assert filtered == [1]


def test_transcript_index_verschuift_niet_meer_door_het_filter() -> None:
    """De winst van B309: het nummer van een gevonden woord hangt niet
    meer af van wat het filter besluit. "twee" staat op index 2, of
    "MUZIEK" nu wel of niet wordt weggegooid."""
    segments = (
        Segment(0, "een", 1.0, 1.5, (Word("een", 1.0, 1.5, 0.9),)),
        Segment(1, "MUZIEK", 2.0, 2.5, (Word("MUZIEK", 2.0, 2.5, 0.3),)),
        Segment(2, "twee", 3.0, 3.5, (Word("twee", 3.0, 3.5, 0.9),)),
    )
    alles, _f = pipeline._full_transcript(segments, segments)
    zonder, _f2 = pipeline._full_transcript(segments,
                                            (segments[0], segments[2]))
    assert alles == zonder


@pytest.mark.parametrize("oud,gefilterd,nieuw", [
    (0, [1], 0),
    (1, [1], 2),
    (5, [1, 3], 7),
    (0, [], 0),
    (4, [0], 5),
])
def test_pin_index_omrekenen(oud: int, gefilterd: list[int],
                             nieuw: int) -> None:
    """Oude pins telden alleen de bewaarde woorden; elke gefilterde
    positie op of vóór het woord schuift het één plaats op."""
    assert pipeline._shift_pin_index(oud, gefilterd) == nieuw


def test_creatieve_koppeling_pakt_nooit_een_gefilterd_woord() -> None:
    """De automatische koppeling mag een weggefilterd woord niet alsnog
    binnenhalen; de gebruiker mag dat wel met de hand doen."""
    transcript = [("formidable", 0.0, 0.5), ("MUZIEK", 0.6, 1.0),
                  ("nous", 1.1, 1.5)]
    lyric_texts = ["fort", "minable", "nous"]
    targets = [[], [0], [2]]
    zonder = song_text.creative_couplings(lyric_texts, transcript, targets)
    met = song_text.creative_couplings(lyric_texts, transcript, targets,
                                       blocked={0})
    assert zonder[0] == [0]          # zonder blokkade wél gekoppeld
    assert met[0] == []              # met blokkade niet


# --------------------------------------------------------------------------
# B310: timing a la-la/na-na series
# --------------------------------------------------------------------------

def test_verdelen_over_gezongen_tijd_slaat_de_stilte_over() -> None:
    """Vier regels over twee even lange zangvensters met een stilte
    ertussen: twee regels per venster, geen regel over de stilte heen."""
    slots = timing_module.spread_over_active(4, [(0.0, 4.0), (10.0, 14.0)])
    assert slots == [(0.0, 2.0), (2.0, 4.0), (10.0, 12.0), (12.0, 14.0)]


def test_verdelen_naar_rato_van_de_zangduur() -> None:
    """Een venster dat drie keer zo lang is, krijgt ook ongeveer drie keer
    zoveel regels."""
    slots = timing_module.spread_over_active(4, [(0.0, 9.0), (20.0, 23.0)])
    in_eerste = sum(1 for s, _e in slots if s < 10.0)
    assert len(slots) == 4 and in_eerste == 3


def test_verdelen_negeert_een_flintertje_venster() -> None:
    """Het knippen op de gap-grens laat vaak een venstertje van enkele
    honderdsten over. Dat mag geen hele regel opslokken (dat leverde
    regels van 0,07 s op)."""
    slots = timing_module.spread_over_active(2, [(0.0, 10.0), (10.0, 10.07)])
    assert len(slots) == 2
    assert all(e - s > 1.0 for s, e in slots)


def test_verdelen_voegt_vensters_samen_bij_meer_vensters_dan_regels() -> None:
    """Meer zangvensters dan regels: de vensters met de kleinste pauze
    ertussen worden samengevoegd, zodat juist de duidelijkste pauzes
    overblijven."""
    slots = timing_module.spread_over_active(
        2, [(0.0, 2.0), (2.5, 4.0), (30.0, 34.0)])
    assert len(slots) == 2
    assert slots[0][0] == 0.0 and slots[1][0] == 30.0


def test_verdelen_zonder_vensters_geeft_niets() -> None:
    """Zonder bruikbare vensters houdt de aanroeper zijn eigen
    interpolatie; deze functie verzint niets."""
    assert timing_module.spread_over_active(3, []) == []
    assert timing_module.spread_over_active(0, [(0.0, 4.0)]) == []


def _puls_stem(path: Path, pulses: list[float], duration: float,
               sample_rate: int = 22_050, length_s: float = 0.6) -> Path:
    """A vocal stem: short bursts of noise at the given moments."""
    from modules.audio import save_wav

    samples = np.zeros(int(duration * sample_rate), dtype=np.float32)
    rng = np.random.default_rng(7)
    for moment in pulses:
        start = int(moment * sample_rate)
        length = int(length_s * sample_rate)
        piece = rng.normal(0.0, 0.3, length).astype(np.float32)
        piece *= np.hanning(length).astype(np.float32)
        samples[start:start + length] += piece[:len(samples) - start]
    save_wav(path, samples[:, None], sample_rate)
    return path


def test_inzetten_liggen_niet_bovenop_elkaar() -> None:
    """B310: bij het kiezen van de sterkste ``expected`` inzetten moeten
    ze minstens een deel van de gemiddelde afstand uit elkaar liggen.
    Zonder die eis kwamen twee inzetten van dezelfde gezongen noot (de
    aanzet en het lijf) enkele honderdsten na elkaar terecht, en kreeg
    één regel een tijdvak van een fractie van een seconde. Echt gemeten
    geval: 180,14 s en 180,21 s in "Lied I"."""
    from modules import rhythm

    # De twee sterkste inzetten liggen 0,07 s uit elkaar (dezelfde noot).
    onsets = [(180.14, 9.0), (180.21, 8.9), (184.07, 3.0), (188.46, 2.5)]
    gekozen = rhythm.pick_spread_onsets(onsets, 3, minimum_gap=2.0)
    assert [t for t, _s in gekozen] == [180.14, 184.07, 188.46]

    # Zonder minimumafstand wint de dubbele aanzet het van een echte puls.
    zonder = rhythm.pick_spread_onsets(onsets, 3, minimum_gap=0.0)
    assert [t for t, _s in zonder] == [180.14, 180.21, 184.07]


def test_inzetten_kiezen_levert_nooit_meer_dan_gevraagd() -> None:
    """Ook met een minimumafstand van nul blijft het aantal begrensd."""
    from modules import rhythm

    onsets = [(float(i), float(10 - i)) for i in range(10)]
    assert len(rhythm.pick_spread_onsets(onsets, 4, 0.0)) == 4


def test_inzetafstand_wordt_echt_toegepast(tmp_path: Path) -> None:
    """Einde-tot-einde: op een echte zangstem liggen de gekozen inzetten
    minstens de minimumafstand uit elkaar."""
    from modules import rhythm

    pytest.importorskip("librosa")
    stem = _puls_stem(tmp_path / "vocals.wav",
                      [0.5, 2.5, 4.5, 6.5, 8.5], 11.0)
    onsets = rhythm.energy_onsets(stem, 0.0, 11.0, expected=5)
    assert len(onsets) == 5
    afstanden = [b - a for a, b in zip(onsets, onsets[1:])]
    minimum = 11.0 / 5 * rhythm._ONSET_MIN_SEPARATION_RATIO
    assert min(afstanden) >= minimum


def _verfijn(stem: Path, lines, filled, reliable) -> None:
    """``_refine_with_vocals`` on a stand-in context with ``stem``."""
    import types

    context = types.SimpleNamespace(config=types.SimpleNamespace(
        advanced=types.SimpleNamespace(vocal_analysis=True)))
    origineel = pipeline.ensure_original_vocals
    pipeline.ensure_original_vocals = lambda _c: stem
    try:
        pipeline._refine_with_vocals(context, lines, filled, reliable, {})
    finally:
        pipeline.ensure_original_vocals = origineel


def test_staartreeks_wordt_begrensd_door_waar_de_zang_stopt(
        tmp_path: Path) -> None:
    """B310: een reeks vulregels aan het EIND van een nummer heeft geen
    anker erachter. Tot en met v0.96 marcheerde de interpolatie door met
    de mediane regelduur, en die is bij korte gekoppelde regels veel te
    kort: de hele la-la-outro werd dan in de eerste seconden geperst en
    de rest van de gezongen tijd bleef leeg. Nu bepaalt de zangstem waar
    de laatste regel eindigt.

    Precies de Viva-situatie: gezongen tot ver na het punt waar de
    doorgetrokken interpolatie ophield.
    """
    from modules import rhythm

    pytest.importorskip("librosa")
    # Gezongen: pulsen van 1 tot ruim 7 s, daarna stilte tot 20 s.
    stem = _puls_stem(tmp_path / "vocals.wav", [1.0, 3.0, 5.0, 7.0], 20.0)
    lines = [0, 1, 2, 3, 4]
    # De gekoppelde regel duurt 0,7 s, dus de interpolatie loopt met
    # stapjes van 0,7 s door tot 3,7 s - terwijl er tot 7,6 s gezongen
    # wordt.
    filled = [(0.2, 0.9), (0.9, 1.6), (1.6, 2.3), (2.3, 3.0), (3.0, 3.7)]
    reliable = [True, False, False, False, False]
    _verfijn(stem, lines, filled, reliable)

    assert rhythm.is_available()
    assert filled[-1][1] > 6.0, filled          # de outro wordt gedekt
    assert all(e - s >= pipeline._FILLER_LINE_MIN_S for s, e in filled[1:]), \
        filled
    assert all(filled[i][0] <= filled[i + 1][0]
               for i in range(len(filled) - 1)), filled


def test_vulregels_komen_nooit_in_een_fractie_van_een_seconde(
        tmp_path: Path) -> None:
    """B310: als de inzetdetectie in een grotendeels stille passage
    pulsen vindt, leverde dat regels van een tiende seconde op terwijl de
    rest van de passage leeg bleef. Zo'n plaatsing wordt verworpen en de
    regels worden over de gezongen tijd verdeeld."""
    from modules import rhythm

    pytest.importorskip("librosa")
    # Gezongen: 1-2,6 s. Vlak voor het volgende anker (4,0 s) nog een korte
    # uitloop, waar de inzetdetectie een puls in ziet. Drie vulregels op
    # die drie inzetten leveren als laatste regel 3,94-4,0 s op: een
    # tijdvak van zes honderdsten.
    stem = _puls_stem(tmp_path / "vocals.wav", [1.0, 2.0, 3.9], 5.0,
                      length_s=0.5)
    lines = [0, 1, 2, 3, 4]
    filled = [(0.2, 0.9), (0.9, 1.93), (1.93, 2.96), (2.96, 4.0),
              (4.0, 4.7)]
    reliable = [True, False, False, False, True]
    _verfijn(stem, lines, filled, reliable)

    assert rhythm.is_available()
    assert all(e - s >= pipeline._FILLER_LINE_MIN_S
               for s, e in filled[1:4]), filled
