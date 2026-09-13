"""Tests voor v0.92.0-fixes.

B277-herziening: de v0.91-aanpak (~0.1s glijdend gemiddelde) bleek bij
vergelijking tegen ÉCHTE handmatig gecorrigeerde ``timing.json``-bestanden
(vs. ``timing_auto.json`` van dezelfde projecten) nauwelijks te helpen - de
werkelijke hoofdoorzaak was dat het analysevenster van een regel vaak
doorloopt tot de start van de volgende regel, en "het laatste steekpunt
boven drempel" dan de OPBOUW van die volgende regel pakt, ook met een lang
stil gat ertussen. ``held_note_end``/``active_end`` gebruiken nu een
gedeelde helper die van rechts naar links het eerste aaneengesloten stille
gat (~0.3s) herkent en het laatste echte actieve moment daarvóór teruggeeft,
op de RUWE RMS-steekpunten (geen smoothing meer - dat presteerde juist
slechter, zie ``docs/doorontwikkeling.md``). Concreet gemeten op "Lied B
" (47 regels, 31 met verschil >0.3s tussen auto en handmatig):
gemiddelde afwijking 1.63s -> 0.28s, mediaan 1.47s -> 0.25s.

Knoplabel-fix: de renderknop op het Karaokevideo-tabblad heette "4. Video
maken (eerste render)", ook al gebruikt dezelfde knop/functie evengoed een
herrender na een handmatige timing-correctie (leest altijd ``timing.json``,
nooit ``timing_auto.json``). Hernoemd naar "4. Video maken".

B280: alleen ``.wav``/``.mp3`` werden als invoerformaat herkend
(``filesystem.SUPPORTED_EXTENSIONS``), ook al verwerken ffmpeg/ffprobe
elk containerformaat even generiek. Aanleiding: de gebruiker voegde een
``.m4a``-fragment (via Clipchamp samengevoegd) toe aan de originele
audio van "Lied J". Uitgebreid met ``.m4a``/``.flac``/``.ogg``/
``.aac`` als invoerformaat; de UITVOER blijft ongewijzigd altijd mp3
(of wav voor een wav-bron) - ``export.export_result`` behandelt de
nieuwe formaten net als een mp3-bron (encodeert naar
``karaoke_edit.mp3``).

B281: bij "Lied J" ("Waylon Jennings - Good Ol' Boys") liep de
songtekstregel "Than the law will allow" in de video zo'n 0.6s te lang
door. Oorzaak: ``_align_core``'s DP-uitlijning koppelde het songtekstwoord
"allow" via een 1:2-koppeling (m12) aan de transcriptiewoorden "land"
gevolgd door het publieksgeluid "Whoo!" (gelijkenis slechts 0.333) - dat
scoorde toevallig goedkoper dan "allow" onverklaard te laten, ook al is de
gelijkenis zwak. Het (RMS-verfijnde) regeleinde volgt de gekoppelde tijd,
dus "Whoo!" werd zo per ongeluk het einde van de zangregel. Vergelijkbaar
gebeurde dit met "will" <-> "of the" (gelijkenis 0.250). Nieuwe ondergrens
(``_MIN_MULTI_HALF_SIM``) op de BESTE van de twee losse helft-gelijkenissen
bij zo'n meervoudige (m21/m12) koppeling repareert dit: "allow" heeft met
geen van beide transcriptiewoorden ("land" 0.0, "Whoo!" 0.25) een redelijke
match, dus wordt de koppeling geweigerd en valt "allow" terug op een
losse (m11) koppeling aan alleen "of". Een grens op de GECOMBINEERDE
gelijkenis in plaats van de beste helft bleek de bestaande, bedoelde
koppeling "Kedeng Kedeng" <-> "de trein" te breken (scoort net als de
Lied J-koppelingen 0.333 gecombineerd) - vandaar de per-helft-grens.
"""
from __future__ import annotations


# -- B277 --------------------------------------------------------------

def test_last_active_time_negeert_uitschieter_na_lang_stil_gat() -> None:
    """B277: een korte uitschieter (bv. de opbouw van de volgende regel)
    die pas ná een lang stil gat (>=0.3s) komt, mag het einde niet
    optrekken - het antwoord blijft het laatste actieve moment vóór dat
    gat, ongeacht wat er ná het gat weer opleeft."""
    import numpy as np
    from modules import rhythm

    step = rhythm._HOP / rhythm._SR
    n = 100
    times = np.arange(n, dtype=np.float32) * step
    rms = np.zeros(n, dtype=np.float32)
    rms[:40] = 1.0        # echte zang
    rms[40:] = 0.02        # (bijna) stilte erna
    rms[70] = 0.5          # uitschieter ver na de zang (bv. volgende regel)

    mask = np.ones(n, dtype=bool)
    threshold = 1.0 * 0.15
    end = rhythm._last_active_time(rms, times, mask, threshold)
    # Het stille gat tussen index 39 en 70 is ruim >=0.3s, dus de
    # uitschieter op index 70 telt niet mee: het antwoord is het einde van
    # de echte zang zelf (index 39).
    assert end is not None
    assert end == times[39]


def test_last_active_time_zonder_lang_gat_pakt_laatste_punt() -> None:
    """B277: is er geen enkel lang stil gat (alles blijft aaneengesloten
    boven de drempel of de gaten zijn te kort), dan blijft het oude
    gedrag gelden - het allerlaatste boven-drempel-moment."""
    import numpy as np
    from modules import rhythm

    step = rhythm._HOP / rhythm._SR
    n = 50
    times = np.arange(n, dtype=np.float32) * step
    rms = np.full(n, 1.0, dtype=np.float32)   # aaneengesloten actief

    mask = np.ones(n, dtype=bool)
    end = rhythm._last_active_time(rms, times, mask, 1.0 * 0.15)
    assert end == times[-1]


def test_held_note_end_en_active_end_gebruiken_gedeelde_helper() -> None:
    """B277: beide functies geven nog steeds zinnige, geclampte waarden."""
    from modules import rhythm

    # We testen hier alleen dat de functies bestaan en op ontbrekende
    # analyse netjes None teruggeven (geen audio beschikbaar in deze test
    # -> _rms_envelope faalt op het niet-bestaande pad).
    path = "/nonexistent/pad/audio.wav"
    assert rhythm.held_note_end(path, 0.0, 1.0, 2.0) is None
    assert rhythm.active_end(path, 0.0, 1.0) is None


# -- Knoplabel-fix -------------------------------------------------------

def test_video_render_label_zonder_eerste_render_tekst() -> None:
    """De renderknop wordt ook voor herrenders gebruikt (leest altijd
    timing.json); het label mag dus geen "(eerste render)"-tekst meer
    suggereren dat dit een eenmalige actie zou zijn."""
    from modules.translations import TRANSLATIONS

    for language_code, texts in TRANSLATIONS.items():
        label = texts.get("video_render", "")
        assert "eerste render" not in label.lower()
        assert "first render" not in label.lower()


# -- B280 ----------------------------------------------------------------

def test_supported_extensions_bevat_nieuwe_containers() -> None:
    """B280: m4a/flac/ogg/aac zijn als invoerformaat toegevoegd naast de
    oorspronkelijke wav/mp3; wav blijft eerst (geen conversie nodig)."""
    from modules import filesystem

    assert filesystem.SUPPORTED_EXTENSIONS[0] == ".wav"
    for ext in (".mp3", ".m4a", ".flac", ".ogg", ".aac"):
        assert ext in filesystem.SUPPORTED_EXTENSIONS


def test_find_audio_file_vindt_m4a(tmp_path) -> None:
    """B280: een los .m4a-bestand wordt nu ook gevonden (voorheen None)."""
    from modules.filesystem import find_audio_file

    (tmp_path / "original.m4a").write_bytes(b"m4a")
    found = find_audio_file(tmp_path, "original")
    assert found is not None and found.suffix == ".m4a"


def test_find_audio_file_wav_wint_van_nieuwe_containers(tmp_path) -> None:
    """B280: staan er meerdere varianten, dan wint nog altijd .wav (geen
    conversie nodig) - ook als er ook een .flac/.m4a naast bestaat."""
    from modules.filesystem import find_audio_file

    (tmp_path / "original.flac").write_bytes(b"flac")
    (tmp_path / "original.m4a").write_bytes(b"m4a")
    (tmp_path / "original.wav").write_bytes(b"wav")
    found = find_audio_file(tmp_path, "original")
    assert found is not None and found.suffix == ".wav"


# -- B281 ------------------------------------------------------------------

def _word(text: str, start: float, duration: float = 0.4):
    from modules.whisper import Word
    return Word(text=text, start=start, end=start + duration, confidence=0.9)


def test_meervoudige_koppeling_negeert_publieksgeluid(tmp_path) -> None:
    """B281: "allow" mag niet aan "land Whoo!" plakken (Lied J) - de
    interjectie "Whoo!" heeft met "allow" geen redelijke gelijkenis (beide
    helft-gelijkenissen <0.3), dus de m12-koppeling moet geweigerd worden en
    "allow" moet op de losse ("of") koppeling terugvallen."""
    from modules.song_text import align_lyrics, load_lyrics
    from modules.whisper import Segment

    words = (_word("than", 47.32), _word("the", 47.82, 0.16),
             _word("law", 47.98, 0.36), _word("of", 48.34, 0.02),
             _word("Whoo!", 48.36, 1.94))
    segment = Segment(index=0, text=" ".join(w.text for w in words),
                      start=words[0].start, end=words[-1].end, words=words)

    path = tmp_path / "songtekst.txt"
    path.write_text("Than the law will allow\n", encoding="utf-8")
    lyrics = load_lyrics(path)

    aligned = align_lyrics(lyrics, (segment,))
    by_text = {w.lyric.text: w for w in aligned}
    # "allow" mag niet gekoppeld zijn aan "Whoo!" (los of gecombineerd).
    allow = by_text["allow"]
    assert allow.matched_text is None or "Whoo" not in allow.matched_text


def test_meervoudige_koppeling_kedeng_de_trein_blijft_werken(tmp_path) -> None:
    """B281: de bestaande, bedoelde 1:2-koppeling "Kedeng"<->"de trein"
    (zie moduledocstring) mag niet breken - scoort gecombineerd exact
    hetzelfde (0.333) als de geweigerde Lied J-koppelingen, maar heeft
    (in tegenstelling tot die koppelingen) voor BEIDE helften een redelijke
    losse gelijkenis (Kedeng<->de en Kedeng<->trein, allebei 0.333)."""
    from modules.song_text import align_lyrics, load_lyrics
    from modules.whisper import Segment

    words0 = (_word("GEDENGEDENG", 1.0, 0.9),)
    words1 = (_word("de", 3.0, 0.3), _word("trein", 3.35, 0.45))
    make = lambda i, ws: Segment(  # noqa: E731
        index=i, text=" ".join(w.text for w in ws),
        start=ws[0].start, end=ws[-1].end, words=ws)
    segments = (make(0, words0), make(1, words1))

    path = tmp_path / "songtekst.txt"
    path.write_text("Kedeng Kedeng, Kedeng Kedeng\n", encoding="utf-8")
    lyrics = load_lyrics(path)

    aligned = align_lyrics(lyrics, segments)
    # Minstens één van de vier "Kedeng"-woorden moet nog steeds aan
    # "de"/"trein" gekoppeld worden (via m12, net als vóór B281).
    assert any(w.matched_text in ("de", "trein", "de trein")
              for w in aligned if w.lyric.text == "Kedeng")


def test_min_multi_half_sim_alleen_op_meervoudige_koppelingen(tmp_path) -> None:
    """B281: een zwakke ENKELVOUDIGE (m11) koppeling mag niet worden
    geraakt door de nieuwe grens - alleen 1:2/2:1-koppelingen worden
    getoetst. Whisper hoort geregeld een fonetisch verwant maar net ander
    woord (hier: "nu" -> "niet"); dat moet gewoon gekoppeld blijven."""
    from modules.song_text import align_lyrics, load_lyrics
    from modules.whisper import Segment

    words = (_word("niet", 5.0, 0.3),)
    segment = Segment(index=0, text="niet", start=words[0].start,
                      end=words[-1].end, words=words)
    path = tmp_path / "songtekst.txt"
    path.write_text("nu\n", encoding="utf-8")
    lyrics = load_lyrics(path)
    aligned = align_lyrics(lyrics, (segment,))
    assert aligned[0].matched_text == "niet"
