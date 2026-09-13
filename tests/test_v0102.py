"""Tests voor v0.102.0: B329 tot en met B333.

Van groot naar klein. De zinsstructuur wordt eerst goed gezet, daarna
pas verfijnd op woord- en lettergreepniveau.

B329 - een herhaalde zin is overal ongeveer even lang; een exemplaar dat
       daar ver vanaf zit is geen aangehouden zin maar een fout.
B330 - een geschat regelbegin gaat naar de zanginzet waar hij bij hoort.
B331 - twee losse roepjes vlak na elkaar zijn twee inzetten, geen één
       samengesmolten venster.
B332 - de fraseperiode is de eenheid van het zinsniveau: als ankertoets
       en als verdeling tussen twee ankers.
B333 - een gemeten regelbegin wint van de minimumduur van de regel
       ervoor; anders stapelen die duwtjes op over het hele lied.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import timing as T  # noqa: E402
from modules.timing import Syllable, TimedLine  # noqa: E402

PERIODE = 3.6


def regel(index: int, tekst: str, start: float, eind: float,
          kwaliteit: str = "high", lettergrepen: int = 6,
          crowd: bool = False) -> TimedLine:
    stap = (eind - start) / max(1, lettergrepen)
    return TimedLine(
        index=index, text=tekst, crowd=crowd,
        syllables=tuple(Syllable(text=f"s{i}", start=start + i * stap,
                                 end=start + (i + 1) * stap)
                        for i in range(lettergrepen)),
        quality=kwaliteit, block=0)


def strak_lied(n: int = 12, periode: float = PERIODE) -> list[TimedLine]:
    """Een lied dat netjes elke ``periode`` een nieuwe regel begint."""
    return [regel(i, f"Regel {i % 3}", 10.0 + i * periode,
                  10.0 + i * periode + periode * 0.9)
            for i in range(n)]


# --------------------------------------------------------------------------
# B332: de fraseperiode meten
# --------------------------------------------------------------------------

def test_periode_van_een_strak_lied() -> None:
    gemeten = T.phrase_period(strak_lied())
    assert gemeten is not None
    assert math.isclose(gemeten, PERIODE, abs_tol=0.05)


def test_grillig_lied_levert_geen_periode() -> None:
    """Bij een lied met tussenwerpsels tussen de volle regels is de
    afstand niet meetbaar (gemeten: Lied N 50%). Dan zet het hele
    mechanisme zichzelf uit en blijft alles bij het oude."""
    regels = []
    t = 10.0
    for i, gat in enumerate([3.6, 0.9, 4.8, 1.1, 3.4, 0.8, 5.2, 1.3, 3.9]):
        regels.append(regel(i, f"Regel {i}", t, t + gat * 0.8))
        t += gat
    assert T.phrase_period(regels) is None


def test_te_weinig_betrouwbare_regels_levert_geen_periode() -> None:
    regels = strak_lied(4)
    for i in (1, 2):
        regels[i] = regel(i, regels[i].text, regels[i].start, regels[i].end,
                          kwaliteit="sentence")
    assert T.phrase_period(regels) is None


def test_crowdregels_tellen_mee_bij_het_meten() -> None:
    """In een parodie is een crowd-regel vaak een volwaardige frase. Ze
    eruit filteren maakte de meting slechter (gemeten: MAD 6% -> 50%)."""
    regels = strak_lied()
    regels = [regel(r.index, r.text, r.start, r.end, crowd=(r.index % 2 == 0))
              for r in regels]
    assert T.phrase_period(regels) is not None


# --------------------------------------------------------------------------
# B329: de duur van gelijke zinnen
# --------------------------------------------------------------------------

def test_referentie_alleen_uit_gemeten_exemplaren() -> None:
    """Een schatting als referentie bevestigt zijn eigen fout."""
    regels = [regel(0, "Refrein", 10.0, 13.6),
              regel(1, "Refrein", 20.0, 23.6),
              regel(2, "Refrein", 30.0, 33.6),
              regel(3, "Refrein", 40.0, 49.0, kwaliteit="sentence")]
    ref = T.reference_durations(regels)
    mediaan, _spreiding = ref["refrein"]
    assert math.isclose(mediaan, 3.6, abs_tol=0.05)


def test_te_grillige_tekst_levert_geen_referentie() -> None:
    """Een haak die soms wordt aangehouden en soms geroepen ("Sunday
    Bloody Sunday": 0,10 tot 8,50 s) geeft geen bruikbare mediaan."""
    duren = [0.6, 4.1, 1.2, 5.3, 0.9]
    regels = [regel(i, "Haak", 10.0 + i * 12, 10.0 + i * 12 + d)
              for i, d in enumerate(duren)]
    assert "haak" not in T.reference_durations(regels)


def test_minder_dan_drie_keer_telt_niet() -> None:
    regels = [regel(0, "Eenmalig", 10.0, 13.6),
              regel(1, "Eenmalig", 20.0, 23.6)]
    assert T.reference_durations(regels) == {}


# --------------------------------------------------------------------------
# B329/B332: welke ankers zijn onmogelijk?
# --------------------------------------------------------------------------

def test_dubbele_lengte_wordt_aangewezen() -> None:
    """Het gemeten geval: "E viva Espagna" van 7,66 s tegen een mediaan
    van 3,60 - 2,13x. Die ene zin verklaarde 8,8 s van de 9,4 s
    verschuiving die daarna in het hele staartstuk zat."""
    regels = strak_lied()
    regels[6] = regel(6, regels[6].text, regels[6].start,
                      regels[6].start + 7.66)
    periode = T.phrase_period(regels)
    verdacht = T.implausible_and_overlong(regels, periode,
                                     T.reference_durations(regels))[0]
    assert 6 in verdacht


def test_platgeslagen_zin_wordt_aangewezen() -> None:
    """De andere kant: zinnen van 0,02 en 0,90 s aan het eind, omdat
    alles ervoor te laat stond."""
    regels = strak_lied()
    regels[9] = regel(9, regels[9].text, regels[9].start,
                      regels[9].start + 0.02)
    verdacht = T.implausible_and_overlong(regels, T.phrase_period(regels),
                                     T.reference_durations(regels))[0]
    assert 9 in verdacht


def test_korte_maar_echte_regel_blijft_staan() -> None:
    """Een lied heeft ook regels die een halve frase duren ("Rood
    Witte Zangers", 1,42 s bij een periode van 3,72). Die mogen niet
    sneuvelen: het losmaken kostte daar 2,27 s verschuiving."""
    regels = strak_lied(periode=3.72)
    regels[5] = regel(5, "Korte tag", regels[5].start,
                      regels[5].start + 1.42)
    verdacht = T.implausible_and_overlong(regels, T.phrase_period(regels),
                                     T.reference_durations(regels))[0]
    assert 5 not in verdacht


def test_meer_dan_de_helft_verdacht_betekent_niets_doen() -> None:
    """Is bijna alles verdacht, dan klopt de referentie niet en niet het
    lied. Dan blijft de timing zoals hij was."""
    regels = [regel(i, "Regel", 10.0 + i * 3.6,
                    10.0 + i * 3.6 + (3.4 if i in (0, 1, 2, 3) else 0.1))
              for i in range(10)]
    verdacht = T.implausible_and_overlong(regels, 3.6,
                                     T.reference_durations(regels))[0]
    assert verdacht == set(), "zes van de tien is te veel om te vertrouwen"


def test_zonder_periode_werkt_de_duurtoets_nog() -> None:
    """De twee toetsen vangen verschillende dingen. Zonder meetbare
    periode blijft de referentieduur over."""
    regels = [regel(0, "Refrein", 10.0, 13.6),
              regel(1, "Refrein", 25.0, 28.6),
              regel(2, "Refrein", 44.0, 47.6),
              regel(3, "Refrein", 60.0, 69.0)]
    verdacht = T.implausible_and_overlong(regels, None,
                                     T.reference_durations(regels))[0]
    assert verdacht == {3}


# --------------------------------------------------------------------------
# B332: de verdeling tussen twee ankers
# --------------------------------------------------------------------------

def test_verdeling_per_frase_in_plaats_van_per_lettergreep() -> None:
    """Tussen twee ankers krijgt elke regel een eigen frase. Een regel
    van vier lettergrepen krijgt dus niet een kwart van de tijd van een
    regel van zestien."""
    regels = strak_lied(10)
    # regels 4..6 zijn geschat en verschillen sterk in lengte
    for i, n in ((4, 3), (5, 18), (6, 4)):
        regels[i] = regel(i, f"Geschat {i}", regels[i].start, regels[i].end,
                          kwaliteit="sentence", lettergrepen=n)
    uit = T.sanitize_timing(regels, song_duration=80.0)
    afstanden = [uit[i + 1].start - uit[i].start for i in range(3, 7)]
    assert max(afstanden) - min(afstanden) < 0.2, afstanden


def test_een_fout_anker_sleept_de_rest_niet_meer_mee() -> None:
    """Het patroon van Lied S: een te lang anker halverwege, gevolgd
    door een reeks geschatte regels. De verschuiving die daaruit volgde
    liep op tot ruim negen seconden."""
    regels = strak_lied(14)
    regels[5] = regel(5, regels[5].text, regels[5].start,
                      regels[5].start + 2 * PERIODE)
    for i in range(6, 12):
        regels[i] = regel(i, regels[i].text, regels[i].start, regels[i].end,
                          kwaliteit="sentence")
    uit = T.sanitize_timing(regels, song_duration=90.0)
    for i in range(6, 12):
        assert abs(uit[i].start - regels[i].start) < 1.0, i


# --------------------------------------------------------------------------
# B330: op de zanginzet zetten
# --------------------------------------------------------------------------

def test_geschatte_regel_gaat_naar_de_inzet() -> None:
    regels = strak_lied(6)
    regels[3] = regel(3, "Geschat", regels[3].start, regels[3].end,
                      kwaliteit="sentence")
    doel = regels[3].start + 0.7
    uit = T.snap_to_onsets(regels, [doel], PERIODE)
    assert math.isclose(uit[3].start, doel, abs_tol=0.01)


def test_gemeten_regel_wordt_nooit_verplaatst() -> None:
    regels = strak_lied(6)
    uit = T.snap_to_onsets(regels, [r.start + 0.6 for r in regels], PERIODE)
    assert [r.start for r in uit] == [r.start for r in regels]


def test_een_verschoven_regel_duwt_een_gemeten_regel_niet_vooruit() -> None:
    """De lek uit de eerste versie: het BEGIN was begrensd, maar het
    EINDE van de verschoven regel duwde de gemeten regel erna alsnog
    weg - vijf regels die goed stonden, gingen zo mis."""
    regels = strak_lied(6)
    regels[2] = regel(2, "Geschat", regels[2].start, regels[2].end,
                      kwaliteit="sentence")
    vast = regels[3].start
    uit = T.snap_to_onsets(regels, [regels[3].start - 0.2], PERIODE)
    assert math.isclose(uit[3].start, vast, abs_tol=1e-6)
    assert uit[2].end <= vast + 1e-6


def test_te_ver_weg_blijft_liggen() -> None:
    """De reikwijdte staat ruim onder de halve frase; verder zou hij de
    inzet van zijn buurregel pakken."""
    regels = strak_lied(6)
    regels[3] = regel(3, "Geschat", regels[3].start, regels[3].end,
                      kwaliteit="sentence")
    ver = regels[3].start + 0.9 * PERIODE
    uit = T.snap_to_onsets(regels, [ver], PERIODE)
    assert math.isclose(uit[3].start, regels[3].start, abs_tol=0.01)


def test_zonder_inzetten_verandert_er_niets() -> None:
    regels = strak_lied(6)
    assert T.snap_to_onsets(regels, [], PERIODE) == tuple(regels)


def test_volgorde_blijft_behouden() -> None:
    regels = strak_lied(8)
    for i in (3, 4, 5):
        regels[i] = regel(i, f"Geschat {i}", regels[i].start, regels[i].end,
                          kwaliteit="sentence")
    uit = T.snap_to_onsets(regels, [regels[5].start - 0.5,
                                    regels[3].start + 0.4], PERIODE)
    starts = [r.start for r in uit]
    assert starts == sorted(starts)


# --------------------------------------------------------------------------
# B331: twee roepjes zijn twee inzetten
# --------------------------------------------------------------------------

@pytest.fixture
def twee_roepjes(tmp_path: Path) -> Path:
    """Twee uitbarstingen van 2,5 s met een kort dal ertussen - het
    patroon van de twee "Ole!"-roepen in de intro."""
    numpy = pytest.importorskip("numpy")
    soundfile = pytest.importorskip("soundfile")
    sr = 22050
    duur = 8.0
    t = numpy.arange(int(duur * sr)) / sr
    toon = numpy.sin(2 * numpy.pi * 220 * t).astype("float32")
    omhullende = numpy.zeros_like(toon)
    for begin, eind in ((1.6, 4.2), (4.4, 6.8)):
        masker = (t >= begin) & (t <= eind)
        omhullende[masker] = 1.0
    pad = tmp_path / "roepjes.wav"
    soundfile.write(pad, toon * omhullende, sr)
    return pad


def test_inzetten_vinden_beide_roepjes(twee_roepjes: Path) -> None:
    from modules import rhythm

    if not rhythm.is_available():
        pytest.skip("librosa niet beschikbaar")
    gevonden = rhythm.onsets(twee_roepjes)
    assert len(gevonden) == 2, gevonden
    assert abs(gevonden[0] - 1.6) < 0.4
    assert abs(gevonden[1] - 4.4) < 0.4


def test_actieve_vensters_smelten_ze_juist_samen(twee_roepjes: Path) -> None:
    """Waarom de inzetten nodig waren: het bestaande venster overbrugt
    het dal en levert één blok van ruim vijf seconden op, waar de twee
    regels dan gelijkmatig over verdeeld werden."""
    from modules import rhythm

    if not rhythm.is_available():
        pytest.skip("librosa niet beschikbaar")
    vensters = rhythm.active_windows(twee_roepjes)
    assert len(vensters) == 1
    assert vensters[0][1] - vensters[0][0] > 4.5


# --------------------------------------------------------------------------
# Samenhang: de volgorde van de stappen
# --------------------------------------------------------------------------

def test_structuur_eerst_dan_pas_verfijnen() -> None:
    """Snappen vóór de structuur pakt de inzet van de buurregel. Op een
    scheve structuur maakte het de uitslag slechter, op een rechte
    structuur brengt het de regel tot binnen een fractie."""
    regels = strak_lied(8)
    for i in (4, 5):
        regels[i] = regel(i, f"Geschat {i}", regels[i].start + 2.4,
                          regels[i].end + 2.4, kwaliteit="sentence")
    inzetten = [10.0 + i * PERIODE for i in range(8)]

    scheef = T.snap_to_onsets(regels, inzetten, PERIODE)
    recht = T.snap_to_onsets(
        T.sanitize_timing(regels, song_duration=60.0), inzetten, PERIODE)

    waarheid = [10.0 + i * PERIODE for i in range(8)]
    fout_scheef = sum(abs(r.start - w) for r, w in zip(scheef, waarheid))
    fout_recht = sum(abs(r.start - w) for r, w in zip(recht, waarheid))
    assert fout_recht < fout_scheef


# --------------------------------------------------------------------------
# B333: een gemeten begin wint van de minimumduur ervoor
# --------------------------------------------------------------------------

def test_te_korte_zin_duwt_de_volgende_niet_vooruit() -> None:
    """De zin ervoor moet minstens ~1 s duren, maar dat mag niet ten koste
    gaan van het GEMETEN begin van de zin erna."""
    regels = strak_lied(6)
    kort = regel(2, "Kort", regels[2].start, regels[2].start + 0.2)
    regels[2] = kort
    uit = T.sanitize_timing(regels, song_duration=60.0)
    assert math.isclose(uit[3].start, regels[3].start, abs_tol=0.01)


def test_de_duwtjes_stapelen_niet_op_over_het_lied() -> None:
    """Het gemeten geval: zes korte zinnen verspreid over een lied lieten
    de rest oplopen tot 8,6 s te laat, terwijl de koppeling zelf tot op
    0,34 s klopte."""
    regels = strak_lied(24)
    for i in (2, 5, 9, 13, 17, 21):
        regels[i] = regel(i, "Kort", regels[i].start, regels[i].start + 0.25)
    uit = T.sanitize_timing(regels, song_duration=150.0)
    afwijkingen = [abs(uit[i].start - regels[i].start) for i in range(24)]
    assert max(afwijkingen) < 0.6, max(afwijkingen)


def test_een_geschatte_regel_mag_nog_wel_opschuiven() -> None:
    """Alleen een GEMETEN begin is onaantastbaar; een schatting mag nog
    steeds voor de vorige regel wijken."""
    regels = strak_lied(6)
    regels[2] = regel(2, "Lang", regels[2].start, regels[2].start + 6.0)
    regels[3] = regel(3, "Geschat", regels[3].start, regels[3].end,
                      kwaliteit="sentence")
    uit = T.sanitize_timing(regels, song_duration=60.0)
    assert uit[3].start >= uit[2].end - 1e-6
