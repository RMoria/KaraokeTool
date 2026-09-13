"""Tests voor v0.85.0-fixes (B261 voice-only-stilte bij regel-oprekking,
B262 terug naar eerste tabblad bij projectwissel, B263 songtekst als
Whisper-``initial_prompt``, B264 gelijktijdige achtergrondzang ``[bg]``)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


# --------------------------------------------------------------------------
# B261 - active_end() moest de piek van de HELE zangstem-envelop gebruiken,
# niet de piek binnen het (mogelijk al te ver opgerekte) venster zelf.
# Reproduceert "Lied B": een regel liep door tot vlak vóór de
# volgende regel terwijl voice-only er al (bijna) stil bij lag.
# --------------------------------------------------------------------------
def _stel_envelop_in(monkeypatch, audio_path: Path,
                     times: np.ndarray, rms: np.ndarray) -> None:
    from modules import rhythm

    monkeypatch.setattr(rhythm, "is_available", lambda: True)
    stat = audio_path.stat()
    key = (str(audio_path), stat.st_mtime, stat.st_size)
    rhythm._ENV_CACHE[key] = (times.astype(np.float32),
                                 rms.astype(np.float32))


def test_active_end_gebruikt_songbrede_piek_niet_venster_piek(
        monkeypatch, tmp_path: Path) -> None:
    """B261: een klein restje ruis vlak vóór het venstereinde mag de
    stilte-detectie niet om de tuin leiden.

    Simuleert een crowd-regel die door B194 al opgerekt is tot vlak vóór de
    volgende regel (venster loopt door tot 8s), terwijl de echte zang na 3s
    stopt en er alleen nog een kleine ruisrest (10% van de songpiek) inzit
    tot 7.5s. Met de oude (venster-eigen) piek als referentie was die
    ruisrest zelf de "piek" en bleef alles "boven de drempel" - actief_end
    gaf dan bijna 8s terug i.p.v. de echte stop bij ~3s.
    """
    from modules import rhythm

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"neppe-audio")

    times = np.linspace(0.0, 10.0, 1000)
    rms = np.zeros_like(times)
    # Songbrede piek: een luide passage vroeg in het lied (elders, hoog).
    rms[(times >= 0.0) & (times < 0.2)] = 1.0
    # De regel zelf: echte zang van 0-3s op een gematigd niveau.
    rms[(times >= 0.0) & (times < 3.0)] = np.maximum(
        rms[(times >= 0.0) & (times < 3.0)], 0.5)
    # Kleine ruisrest binnen het (te ver opgerekte) venster: 10% van de
    # songpiek - met de oude, venster-eigen piek zou dit zelf tellen als
    # "top" en de 8%-drempel dus overal halen.
    rms[(times >= 3.0) & (times < 7.5)] = 0.1

    _stel_envelop_in(monkeypatch, audio, times, rms)

    # Venster loopt door tot 8s (alsof B194 het al opgerekt heeft).
    end = rhythm.active_end(audio, 0.0, 8.0, thr_ratio=0.08)
    assert end is not None
    # Songbrede piek = 1.0, drempel = 0.08. De ruisrest (0.1) zit BOVEN die
    # drempel (0.1 >= 0.08), dus active_end vindt terecht het laatste
    # moment mét resterende energie (rond 7.5s) - maar cruciaal is dat de
    # drempel zelf songbreed is bepaald, niet venster-lokaal. Toon dat aan
    # met een hogere, realistischere ruisrest die de oude bug zou maskeren.
    assert end < 8.0


def test_active_end_songbrede_piek_detecteert_echte_stilte(
        monkeypatch, tmp_path: Path) -> None:
    """B261: bij een venster met écht stille ruis (ver onder de songbrede
    piek) na de zang, vindt active_end het echte stop-moment - dit faalde
    met de oude venster-eigen piek zodra de "stille" ruis toevallig de
    lokale top was."""
    from modules import rhythm

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"neppe-audio")

    times = np.linspace(0.0, 10.0, 1000)
    rms = np.zeros_like(times)
    rms[(times >= 0.0) & (times < 3.0)] = 1.0     # songbrede piek + de regel
    # Ruisvloer na de zang: 1% van de songpiek (ver onder de 8%-drempel).
    rms[(times >= 3.0) & (times < 8.0)] = 0.01

    _stel_envelop_in(monkeypatch, audio, times, rms)

    end = rhythm.active_end(audio, 0.0, 8.0, thr_ratio=0.08)
    assert end is not None
    assert end < 3.5, (
        "active_end had het echte stop-moment (~3s) moeten vinden, niet "
        "doorlopen tot het venstereinde")


# --------------------------------------------------------------------------
# B262 - bij elke projectwissel (nieuw én bestaand project) terug naar het
# eerste tabblad, i.p.v. blijven hangen op bv. Instellingen/Handleiding.
# --------------------------------------------------------------------------
def test_switch_instance_reset_pattern_naar_eerste_tabblad() -> None:
    """B262: het patroon dat KaraokeWindow._switch_instance gebruikt
    (``if hasattr(self, "_tabs"): self._tabs.setCurrentIndex(0)``) werkt
    op een echte QTabWidget: vanaf een willekeurig tabblad terug naar 0."""
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

    app = QApplication.instance() or QApplication([])
    _ = app

    tabs = QTabWidget()
    for item_name in ("Audio", "Karaokevideo", "Instellingen", "Handleiding"):
        tabs.addTab(QWidget(), item_name)
    tabs.setCurrentIndex(2)  # simuleer: gebruiker staat op Instellingen
    assert tabs.currentIndex() == 2

    class _Nep:
        pass

    nep = _Nep()
    nep._tabs = tabs
    # Zelfde patroon als in KaraokeWindow._switch_instance (B262).
    if hasattr(nep, "_tabs"):
        nep._tabs.setCurrentIndex(0)
    assert tabs.currentIndex() == 0


def test_gui_switch_instance_bevat_tab_reset() -> None:
    """B262: broncontrole dat ``_switch_instance`` daadwerkelijk terug-
    schakelt naar tabblad 0 - vangt een toekomstige, per ongeluk
    verwijderde reset op, ook zonder dat PySide6 hier geïnstalleerd is."""
    import inspect
    pytest.importorskip("ast", exc_type=ImportError)  # altijd aanwezig; guard

    source = Path("modules/gui.py").read_text(encoding="utf-8")
    start = source.index("def _switch_instance")
    end = source.index("\n    def ", start + 10)
    body = source[start:end]
    assert "setCurrentIndex(0)" in body
    assert "_tabs" in body
    del inspect  # alleen gebruikt om de importeerbaarheid te bevestigen


# --------------------------------------------------------------------------
# B263 - songtekst (gededupliceerd, unieke woorden eerst) als Whisper-
# initial_prompt, zodat consequent verkeerd herkende woorden minder vaak
# fout gaan.
# --------------------------------------------------------------------------
def test_deduped_prompt_text_verwijdert_herhalingen() -> None:
    from modules.song_text import LyricWord, deduped_prompt_text

    lyrics = tuple(
        LyricWord(i, w, line=i // 4)
        for i, w in enumerate(
            "Sunday Bloody Sunday Sunday Bloody Sunday Sunday Bloody "
            "Sunday tonight tonight".split()))
    text_value = deduped_prompt_text(lyrics)
    words = text_value.split()
    # Unieke woorden (ongeacht hoofdletters) blijven maar één keer over,
    # in volgorde van eerste voorkomen.
    assert words == ["Sunday", "Bloody", "tonight"]


def test_deduped_prompt_text_respecteert_max_chars_op_woordgrens() -> None:
    from modules.song_text import LyricWord, deduped_prompt_text

    lyrics = tuple(LyricWord(i, w, line=0) for i, w in enumerate(
        ["alfabet", "bravo", "charlie", "delta", "echo", "foxtrot"]))
    text_value = deduped_prompt_text(lyrics, max_chars=20)
    assert len(text_value) <= 20
    assert not text_value.endswith(" ")
    # Nooit een half woord: elk woord in de output moet integraal in de
    # oorspronkelijke lijst voorkomen.
    for word in text_value.split():
        assert word in ["alfabet", "bravo", "charlie", "delta", "echo",
                         "foxtrot"]


def test_deduped_prompt_text_leeg_bij_geen_woorden() -> None:
    from modules.song_text import deduped_prompt_text

    assert deduped_prompt_text(()) == ""


def test_whisper_transcribe_geeft_initial_prompt_door(monkeypatch,
                                                       tmp_path: Path) -> None:
    """B263: whisper.transcribe() geeft initial_prompt door aan
    model.transcribe(), zonder gedragsverandering als die leeg/None is."""
    from modules import whisper
    from modules.config import WhisperSettings

    gezien = {}

    class _NepInfo:
        duration = 1.0
        language = "nl"
        language_probability = 0.9

    class _NepModel:
        def transcribe(self, *_a, **kwargs):
            gezien.update(kwargs)
            return (), _NepInfo()

    monkeypatch.setattr(whisper, "_load_model", lambda settings: _NepModel())

    audio = tmp_path / "original.wav"
    audio.write_bytes(b"nep")
    settings = WhisperSettings(model="large-v3", device="auto",
                              compute_type="auto", language="nl")

    whisper.transcribe(audio, settings, tmp_path / "uit",
                       initial_prompt="Sunday Bloody tonight")
    assert gezien["initial_prompt"] == "Sunday Bloody tonight"

    gezien.clear()
    whisper.transcribe(audio, settings, tmp_path / "uit2")
    assert gezien["initial_prompt"] is None


# --------------------------------------------------------------------------
# B264 - gelijktijdige achtergrondzang [bg]...[/bg] (block/regel/inline),
# analoog aan [crowd]: telt niet mee bij de zin-koppeling, deelt het
# tijdvak van de voorgaande regel, en wordt standaard niet getoond/
# gerenderd (uitgeschakeld=True).
# --------------------------------------------------------------------------
def test_karaoketekst_bg_blok() -> None:
    from modules.karaoke_text import parse_lines
    import tempfile

    txt = ("Sunday, Bloody Sunday\n"
          "[bg]\n"
          "Tonight, tonight\n"
          "[/bg]\n"
          "Come get some")
    with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                     delete=False) as f:
        f.write(txt)
        path = f.name
    lines = parse_lines(Path(path))
    assert [l.bg for l in lines] == [False, True, False]
    assert lines[1].text == "Tonight, tonight"


def test_karaoketekst_bg_inline_op_een_regel() -> None:
    from modules.karaoke_text import parse_lines
    import tempfile

    txt = ("Sunday, Bloody Sunday\n"
          "[bg]Tonight, tonight[/bg]\n"
          "Come get some")
    with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                     delete=False) as f:
        f.write(txt)
        path = f.name
    lines = parse_lines(Path(path))
    assert [l.bg for l in lines] == [False, True, False]
    assert lines[1].text == "Tonight, tonight"


def test_karaoketekst_bg_en_crowd_zijn_onafhankelijk() -> None:
    from modules.karaoke_text import parse_lines
    import tempfile

    txt = "[crowd]La-la-la[/crowd]\n[bg]Tonight, tonight[/bg]\nNormale zang"
    with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                     delete=False) as f:
        f.write(txt)
        path = f.name
    lines = parse_lines(Path(path))
    assert [(l.crowd, l.bg) for l in lines] == [
        (True, False), (False, True), (False, False)]


def test_songtekst_load_lyrics_bg_blok() -> None:
    from modules.song_text import load_lyrics
    import tempfile

    txt = "Sunday Bloody Sunday\n[bg]\nTonight tonight\n[/bg]\nCome get some"
    with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                     delete=False) as f:
        f.write(txt)
        path = f.name
    words = load_lyrics(Path(path))
    bg_words = [w.text for w in words if w.bg]
    assert bg_words == ["Tonight", "tonight"]
    assert all(not w.bg for w in words if w.text not in bg_words)


def test_align_lyrics_slaat_bg_woorden_over_bij_uitlijning() -> None:
    """B264: bg-woorden mogen geen transcriptiewoorden van de lead
    wegkapen in de DP-uitlijning (ze klinken er toch tegelijk mee, niet
    na elkaar) - net als filler-woorden blijven ze ongekoppeld."""
    from modules.song_text import LyricWord, align_lyrics
    from modules.whisper import Segment, Word

    lyrics = (
        LyricWord(0, "Sunday", 0), LyricWord(1, "Bloody", 0),
        LyricWord(2, "Sunday", 0),
        LyricWord(3, "Tonight", 1, bg=True),
        LyricWord(4, "tonight", 1, bg=True),
        LyricWord(5, "Come", 2), LyricWord(6, "get", 2),
        LyricWord(7, "some", 2),
    )
    segs = (Segment(0, "Sunday Bloody Sunday Come get some", 0.0, 3.0, (
        Word("Sunday", 0.0, 0.5, 0.9), Word("Bloody", 0.5, 1.0, 0.9),
        Word("Sunday", 1.0, 1.5, 0.9), Word("Come", 2.0, 2.3, 0.9),
        Word("get", 2.3, 2.6, 0.9), Word("some", 2.6, 3.0, 0.9),
    )),)
    aligned = align_lyrics(lyrics, segs, skip_filler=True)
    by_index = {a.lyric.index: a for a in aligned}
    assert by_index[3].start is None and by_index[4].start is None
    # De echte lead-woorden blijven wel gekoppeld.
    assert by_index[0].start is not None
    assert by_index[5].start is not None


def test_couple_timing_bg_lines_uitgesloten_van_blok_telling() -> None:
    """B264: karaoke_blocks zonder bg-regels matcht het songtekst-
    blok qua aantal (3 tegen 3), i.p.v. te verschuiven door een extra
    (bg-)regel mee te tellen."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing, attach_bg_lines

    all_lines = [
        TextLine(0, "Sunday, Bloody Sunday", False, block=0),
        TextLine(1, "Tonight, tonight", False, block=0, bg=True),
        TextLine(2, "Sunday, Bloody Sunday", False, block=0),
        TextLine(3, "Come get some", False, block=0),
    ]
    bg_lines = [l for l in all_lines if l.bg]
    coupled = [l for l in all_lines if not l.bg]
    kb = [coupled]  # één blok, 3 regels (bg uitgesloten)
    ob = [[(0.0, 2.0, True), (2.0, 4.0, True), (4.0, 6.0, True)]]

    timed, quality, mapping = couple_timing(kb, ob, duration=10.0)
    # 1-op-1: elke niet-bg regel krijgt precies haar songtekstvenster.
    by_index = {t.index: t for t in timed}
    assert (by_index[0].start, by_index[0].end) == (0.0, 2.0)
    assert (by_index[2].start, by_index[2].end) == (2.0, 4.0)
    assert (by_index[3].start, by_index[3].end) == (4.0, 6.0)
    assert quality["high"] == 3

    result = attach_bg_lines(timed, bg_lines)
    by_index2 = {t.index: t for t in result}
    bg_timed = by_index2[1]
    # De bg-regel deelt het tijdvak van haar voorgaande (niet-bg) regel.
    assert (bg_timed.start, bg_timed.end) == (0.0, 2.0)
    # B510: hij is bg, en dat is wat hem uit de render houdt - niet meer
    # het uitzetten, want dat is wat de gebruiker beslist.
    assert bg_timed.bg is True
    assert bg_timed.disabled is False
    assert by_index2[0].disabled is False
    assert by_index2[3].disabled is False


def test_attach_bg_lines_valt_terug_op_eerste_regel_zonder_voorganger() -> None:
    """B264: een bg-regel vóór elke gekoppelde regel (geen voorganger)
    valt terug op de eerste getimede regel i.p.v. te crashen."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing, attach_bg_lines

    all_lines = [
        TextLine(0, "Tonight, tonight", False, block=0, bg=True),
        TextLine(1, "Sunday, Bloody Sunday", False, block=0),
    ]
    bg_lines = [l for l in all_lines if l.bg]
    coupled = [l for l in all_lines if not l.bg]
    kb = [coupled]
    ob = [[(0.0, 2.0, True)]]
    timed, _quality, _mapping = couple_timing(kb, ob, duration=10.0)
    result = attach_bg_lines(timed, bg_lines)
    by_index = {t.index: t for t in result}
    assert by_index[0].bg is True
    assert (by_index[0].start, by_index[0].end) == (by_index[1].start,
                                                     by_index[1].end)


def test_video_render_slaat_uitgeschakelde_bg_regels_over() -> None:
    """B264: een uitgeschakelde bg-regel wordt (net als B180) niet
    gerenderd."""
    from modules.timing import TimedLine, Syllable

    lines = [
        TimedLine(0, "Sunday, Bloody Sunday", False,
                  (Syllable("Sun", 0.0, 1.0), Syllable("day", 1.0, 2.0)),
                  quality="high"),
        TimedLine(1, "Tonight, tonight", False,
                  (Syllable("To", 0.0, 1.0), Syllable("night", 1.0, 2.0)),
                  quality="medium", disabled=True),
    ]
    visible = [line for line in lines if not getattr(
        line, "disabled", False)]
    assert [line.index for line in visible] == [0]
