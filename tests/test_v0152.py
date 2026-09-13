"""Tests for v0.152.0.

B541 - hetzelfde beeld wordt niet twee keer getekend. De renderlus
bouwt elk beeld eerst DROOG op (een grootboek van tekenopdrachten in
plaats van pixels) en hergebruikt de vorige bytes als die opdrachten
gelijk zijn. Daarnaast wordt de opmaak van een zin - hoe hij over rijen
breekt en hoe hoog hij is - nog maar één keer per render uitgerekend in
plaats van vijftig keer per seconde.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image                                 # noqa: E402

from modules import video                             # noqa: E402
from modules.timing import Syllable, TimedLine        # noqa: E402


def _regel(index, tekst, start, eind, crowd=False):
    woorden = tekst.split()
    stap = (eind - start) / len(woorden)
    return TimedLine(
        index=index, text=tekst, crowd=crowd, block=0, quality="high",
        syllables=tuple(
            Syllable(("" if k == 0 else " ") + w,
                     start + k * stap, start + (k + 1) * stap)
            for k, w in enumerate(woorden)))


@pytest.fixture
def lied():
    """Een lied met alles erin: intro, een lange zin over twee rijen,
    een meezingregel, een instrumentaal gat met aftelling, en een
    outro - dus ook allebei de overvloeiingen."""
    regels = [
        _regel(0, "een twee drie vier vijf zes zeven acht negen tien elf",
               12.0, 15.5),
        _regel(1, "vijf zes zeven acht", 16.0, 19.0),
        _regel(2, "roep maar mee", 19.5, 21.0, crowd=True),
        _regel(3, "negen tien elf twaalf", 30.0, 33.0),
        _regel(4, "dertien veertien", 34.0, 36.0),
    ]
    font = video._load_font("", 26)
    titel = video._load_font("", 34)
    logo = Image.new("RGBA", (60, 60), (0, 200, 0, 255))
    return regels, (regels, 7.0, 40.0, 240, 135, font, titel, logo,
                    "Titel", video._DEFAULT_COLORS, "naar: X", font, None)


def _momenten(fps=25, tot=44.0):
    return [i / fps for i in range(int(tot * fps))]


# --------------------------------------------------------------------------
# De belofte: gelijke sleutel betekent gelijk beeld
# --------------------------------------------------------------------------

def test_een_gelijke_sleutel_betekent_een_gelijk_beeld(lied) -> None:
    """Dit is de hele afspraak waar het hergebruik op rust, en de reden
    dat de sleutel wordt OPGENOMEN en niet nagebouwd: verandert er ooit
    iets aan het tekenen, dan valt deze toets om."""
    _regels, args = lied
    video._LAYOUT_CACHE.clear()
    vorige_sleutel = None
    vorige_bytes = None
    gecontroleerd = 0
    for moment in _momenten():
        sleutel = video._frame_key(moment, *args)
        beeld = video._compose_frame(moment, *args).tobytes()
        if sleutel == vorige_sleutel:
            assert beeld == vorige_bytes, f"moment {moment}"
            gecontroleerd += 1
        vorige_sleutel, vorige_bytes = sleutel, beeld
    assert gecontroleerd > 100, "te weinig gelijke beelden om iets te zeggen"


def test_de_hele_render_komt_er_hetzelfde_uit(lied) -> None:
    """Met en zonder hergebruik byte voor byte hetzelfde, inclusief de
    terugvalregel die niet elk beeld meer opneemt."""
    _regels, args = lied
    video._LAYOUT_CACHE.clear()
    zonder = [video._compose_frame(m, *args).tobytes() for m in _momenten()]
    video._LAYOUT_CACHE.clear()
    met = []
    sleutel = None
    laatste = b""
    mis = 0
    for nummer, moment in enumerate(_momenten()):
        kijk = (mis < video._CACHE_PATIENCE
                or nummer % video._CACHE_PROBE in (0, 1))
        nu = video._frame_key(moment, *args) if kijk else None
        if nu is not None and nu == sleutel:
            mis = 0
        else:
            laatste = video._compose_frame(moment, *args).tobytes()
            sleutel = nu
            mis += 1
        met.append(laatste)
    assert met == zonder


def test_er_valt_echt_iets_te_hergebruiken(lied) -> None:
    """Anders bewijst de toets hierboven niets."""
    _regels, args = lied
    video._LAYOUT_CACHE.clear()
    sleutels = [video._frame_key(m, *args) for m in _momenten()]
    gelijk = sum(1 for a, b in zip(sleutels, sleutels[1:]) if a == b)
    assert gelijk > 0.4 * len(sleutels)


# --------------------------------------------------------------------------
# Het grootboek
# --------------------------------------------------------------------------

def test_de_intro_is_een_stilstaand_beeld(lied) -> None:
    _regels, args = lied
    assert video._frame_key(1.0, *args) == video._frame_key(4.0, *args)


def test_tijdens_de_zang_beweegt_er_wel_iets(lied) -> None:
    _regels, args = lied
    assert video._frame_key(13.0, *args) != video._frame_key(13.04, *args)


def test_de_overvloeiing_is_nooit_twee_keer_hetzelfde(lied) -> None:
    """Bij een overvloeiing verandert het aandeel elk beeld; zonder dat
    aandeel in de sleutel zou een halve overgang blijven staan."""
    _regels, args = lied
    # de intro-overvloeiing loopt van 6,5 tot 7,0 s
    binnen = [video._frame_key(6.55 + k * 0.02, *args) for k in range(8)]
    assert len(set(binnen)) == len(binnen)


def test_het_grootboek_tekent_niets() -> None:
    """Anders is de sleutel even duur als het beeld zelf."""
    grootboek = video._Ledger(320, 180)
    font = video._load_font("", 20)
    grootboek.text((1.0, 2.0), "hallo", font=font, fill=(1, 2, 3))
    assert grootboek.width == 320 and grootboek.key()[0][0] == "text"
    assert grootboek.textlength("hallo", font=font) > 0


def test_twee_verschillende_kleuren_geven_twee_sleutels() -> None:
    grootboek = video._Ledger(10, 10)
    font = video._load_font("", 20)
    grootboek.text((0, 0), "x", font=font, fill=(255, 0, 0))
    eerste = grootboek.key()
    tweede = video._Ledger(10, 10)
    tweede.text((0, 0), "x", font=font, fill=(0, 255, 0))
    assert eerste != tweede.key()


# --------------------------------------------------------------------------
# De opmaak van een zin, één keer per render
# --------------------------------------------------------------------------

def test_de_opmaak_van_een_zin_wordt_onthouden(lied) -> None:
    regels, args = lied
    video._LAYOUT_CACHE.clear()
    font = args[5]
    eerst = video._line_text_height(regels[0], font, 240)
    assert video._LAYOUT_CACHE
    nogmaals = video._line_text_height(regels[0], font, 240)
    assert eerst == nogmaals


def test_een_andere_breedte_krijgt_zijn_eigen_opmaak(lied) -> None:
    regels, args = lied
    video._LAYOUT_CACHE.clear()
    font = args[5]
    smal = video._line_text_height(regels[0], font, 200)
    breed = video._line_text_height(regels[0], font, 2000)
    assert smal >= breed          # smal breekt over twee rijen
    assert len(video._LAYOUT_CACHE) == 2


def test_de_opmaak_gaat_niet_mee_naar_de_volgende_render() -> None:
    """De cache staat op regelobjecten van DEZE render; blijven staan
    zou betekenen dat een volgend lied de rijen van het vorige krijgt."""
    import inspect
    bron = inspect.getsource(video.render_video)
    assert "_LAYOUT_CACHE.clear()" in bron


# --------------------------------------------------------------------------
# De terugvalregel
# --------------------------------------------------------------------------

def test_een_echte_render_is_gelijk_met_en_zonder_hergebruik(
        tmp_path, monkeypatch) -> None:
    """De toets die het risico van deze ronde echt vasthoudt: twee keer
    dezelfde video renderen, één keer met elk beeld getekend, en de
    beeldstroom vergelijken. Een broncontrole met ``inspect`` blijft
    groen bij een echte fout; dit niet."""
    import subprocess

    import numpy as np

    from modules import ffmpeg
    if not ffmpeg.is_available():
        pytest.skip("ffmpeg niet beschikbaar")
    from modules.audio import save_wav
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    tempo = 22_050
    toon = (0.3 * np.sin(2 * np.pi * 220
                         * np.arange(12 * tempo) / tempo)).astype("float32")
    audio = tmp_path / "karaoke.wav"
    save_wav(audio, np.stack([toon, toon], axis=1), tempo)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (120, 60), (60, 176, 67, 255)).save(logo)
    regels = generate_skeleton(
        (TextLine(0, "Kedeng Kedeng", False), TextLine(1, "La-la-la", True)),
        {0: (6.0, 8.0), 1: (9.0, 11.0)})

    def rauw(pad):
        klaar = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(pad), "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
        return klaar.stdout

    met = video.render_video(regels, audio, logo, "Testlied",
                             tmp_path / "met.mp4", width=160, height=90,
                             fps=10)
    # Geen sleutel betekent geen hergebruik: elk beeld wordt getekend.
    monkeypatch.setattr(video, "_frame_key", lambda *a, **k: None)
    zonder = video.render_video(regels, audio, logo, "Testlied",
                                tmp_path / "zonder.mp4", width=160,
                                height=90, fps=10)
    assert rauw(met) == rauw(zonder)


def test_twee_renders_achter_elkaar_delen_geen_opmaak(tmp_path) -> None:
    """1.5.12 rendert eenentwintig video's achter elkaar in hetzelfde
    proces; de opmaakcache staat op regelobjecten van één render."""
    import numpy as np

    from modules import ffmpeg
    if not ffmpeg.is_available():
        pytest.skip("ffmpeg niet beschikbaar")
    from modules.audio import save_wav
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    tempo = 22_050
    toon = (0.3 * np.sin(2 * np.pi * 220
                         * np.arange(12 * tempo) / tempo)).astype("float32")
    audio = tmp_path / "karaoke.wav"
    save_wav(audio, np.stack([toon, toon], axis=1), tempo)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (120, 60), (60, 176, 67, 255)).save(logo)
    eerste = generate_skeleton(
        (TextLine(0, "Kedeng Kedeng", False),), {0: (6.0, 8.0)})
    tweede = generate_skeleton(
        (TextLine(0, "Een veel langere zin die over twee rijen breekt",
                  False),), {0: (6.0, 8.0)})
    video.render_video(eerste, audio, logo, "Een", tmp_path / "een.mp4",
                       width=160, height=90, fps=10)
    hoogtes_na_een = dict(video._LAYOUT_CACHE)
    video.render_video(tweede, audio, logo, "Twee", tmp_path / "twee.mp4",
                       width=160, height=90, fps=10)
    # Niets van de eerste render staat nog in de cache van de tweede.
    assert not (set(hoogtes_na_een) & set(video._LAYOUT_CACHE))


def test_zonder_sleutel_wordt_er_niets_hergebruikt() -> None:
    """Een beeld dat niet is opgenomen heeft geen sleutel, en dan mag er
    niets mee vergeleken worden - dat is precies hoe een oud beeld in
    een video terechtkomt."""
    import inspect
    bron = inspect.getsource(video.render_video)
    # De bytes en de sleutel worden op één plek samen gezet; staat er
    # ooit een pad waar alleen de bytes veranderen, dan hoort een oude
    # sleutel bij een nieuw beeld.
    assert bron.count("last_bytes = frame.tobytes()") == 1
    assert bron.count("last_key = key") == 1
    assert "if key is not None and key == last_key:" in bron


def test_de_terugval_kijkt_in_paren() -> None:
    """Zien dat er niets beweegt kost twee beelden naast elkaar; één
    beeld per tien vindt nooit een tweede om mee te vergelijken."""
    import inspect
    bron = inspect.getsource(video.render_video)
    assert "frame_index % _CACHE_PROBE in (0, 1)" in bron
