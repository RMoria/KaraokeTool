"""Tests for v0.151.0.

B538 - een lied met een tweede taal erin wordt ook in die taal gelezen,
en die tweede lezing mag alleen stiltes vullen. Wat 1.5.11g op 31
augustus mat op "Lied_R2", nu in productie; de zwakke-plekken-route uit
diezelfde proef is eruit, met zijn antwoord in het logboek.
"""

from __future__ import annotations

import inspect
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline                          # noqa: E402
from modules import whisper                           # noqa: E402
from modules import whisper_chunks as wc              # noqa: E402
from modules.config import default_config             # noqa: E402
from modules.filesystem import (ProjectPaths, ProjectStore,  # noqa: E402
                                ensure_directories)


# --------------------------------------------------------------------------
# De werklijst
# --------------------------------------------------------------------------

def test_de_tweede_taal_staat_vooraan_in_de_rij() -> None:
    """Hij is even zwaar als de eerste hele draai, en de rij begint met
    het zwaarste werk - de regel van de gebruiker."""
    stukken = (wc.Chunk(0.0, 20.0), wc.Chunk(20.0, 30.0))
    banen = wc.jobs_heaviest_first(stukken, 30.0, "ko")
    assert banen[0] == wc.WHOLE_SONG
    assert banen[1] == (0.0, None, "ko")
    assert len(banen) == 4


def test_zonder_tweede_taal_verandert_er_niets() -> None:
    stukken = (wc.Chunk(0.0, 20.0), wc.Chunk(20.0, 30.0))
    assert wc.jobs_heaviest_first(stukken, 30.0) == [
        wc.WHOLE_SONG, (0.0, 20.0), (20.0, 30.0)]


def test_de_tweede_taal_botst_niet_met_de_eerste_hele_draai() -> None:
    """Dezelfde seconden, andere lezing: als de sleutel gelijk was zou
    de een de ander uit de uitslag drukken."""
    banen = wc.jobs_heaviest_first((), 0.0, "ko")
    assert banen[1] != wc.WHOLE_SONG and len(set(banen)) == len(banen)


# --------------------------------------------------------------------------
# De banen: elke baan zijn eigen taal
# --------------------------------------------------------------------------

def test_elke_baan_krijgt_zijn_eigen_taal(monkeypatch) -> None:
    gevraagd = []

    def fake(audio_path, settings, start=0.0, end=None, initial_prompt="",
             language_override=None, cancelled=None):
        gevraagd.append((start, end, language_override))
        return ()

    monkeypatch.setattr(whisper, "transcribe_slice", fake)
    wc.run_over_lanes("a.wav", None,
                      [wc.WHOLE_SONG, (0.0, None, "ko"), (10.0, 20.0)],
                      "", "en", lanes=1)
    assert sorted(gevraagd, key=str) == sorted(
        [(0.0, None, "en"), (0.0, None, "ko"), (10.0, 20.0, "en")], key=str)


def test_de_tweede_taal_telt_mee_als_invuller() -> None:
    """Voor het samenvoegen is de tweede taal hetzelfde soort ding als
    een stuk: een lezing die een stilte mag vullen."""
    tweede = whisper.segments_from_dicts([{
        "index": 0, "text": "뛰어", "start": 50.4, "end": 50.9,
        "words": [{"text": "뛰어", "start": 50.4, "end": 50.9,
                   "confidence": 0.8}]}])
    gevonden = {wc.WHOLE_SONG: (), (0.0, None, "ko"): tweede}
    assert [w["text"] for w in wc.extra_words_from(gevonden)] == ["뛰어"]


# --------------------------------------------------------------------------
# Wanneer er een tweede taal is
# --------------------------------------------------------------------------

def _context(tmp_path, tekst: str):
    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    (paths.input_dir / "songtekst.txt").write_text(tekst, encoding="utf-8")
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


def test_een_echte_passage_in_een_ander_schrift_telt(tmp_path) -> None:
    context = _context(tmp_path, "we run and we jump\n뛰어 뛰어 뛰어\n")
    assert pipeline._second_language_code(context, "en") == "ko"


def test_de_taal_van_de_draai_zelf_telt_niet(tmp_path) -> None:
    """Hetzelfde lied twee keer in dezelfde taal lezen kost een draai en
    levert niets."""
    context = _context(tmp_path, "we run and we jump\n뛰어 뛰어 뛰어\n")
    assert pipeline._second_language_code(context, "ko") == ""


def test_een_los_leenwoord_is_geen_tweede_taal(tmp_path) -> None:
    context = _context(tmp_path, "we run and we jump\nnaar 뛰어 toe\n")
    assert pipeline._second_language_code(context, "en") == ""


# --------------------------------------------------------------------------
# Productie: de tweede taal vult alleen stiltes
# --------------------------------------------------------------------------

def _woord(text, start, end, conf=0.9):
    return {"text": text, "start": start, "end": end, "confidence": conf}


def _segment(text, start, end, words):
    return {"index": 0, "text": text, "start": start, "end": end,
            "words": [_woord(*w) for w in words]}


@pytest.fixture
def _tweetalig(tmp_path, monkeypatch):
    """Een project met Koreaans in de tekst en twee nep-lezingen."""
    def fake_slice(audio_path, settings, start=0.0, end=None,
                   initial_prompt="", language_override=None,
                   cancelled=None):
        if end is None and language_override == "ko":
            return whisper.segments_from_dicts([
                # eentje in de stilte - die mag erbij
                _segment("뛰어", 25.0, 25.6, [("뛰어", 25.0, 25.6)]),
                # en eentje bovenop een woord dat de eerste taal hoorde
                _segment("점프", 1.0, 1.4, [("점프", 1.0, 1.4)])])
        if end is None:
            return whisper.segments_from_dicts([
                _segment("we jump", 1.0, 2.0,
                         [("we", 1.0, 1.4), ("jump", 1.5, 2.0)])])
        return ()

    context = _context(tmp_path, "we jump 뛰어\n뛰어 뛰어 뛰어\n")
    monkeypatch.setattr(whisper, "transcribe_slice", fake_slice)
    monkeypatch.setattr(pipeline, "_original_vocal_windows",
                        lambda c: [(0.0, 10.0), (20.0, 30.0)])
    monkeypatch.setattr(pipeline, "lyric_keys", lambda c: frozenset())
    return context


def test_de_tweede_taal_vult_de_stilte(tmp_path, _tweetalig) -> None:
    context = _tweetalig
    uitvoer = context.paths.output_dir / "original"
    segmenten, gevuld, _taal = pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "en", uitvoer)
    teksten = [s.text for s in segmenten]
    assert "뛰어" in teksten and gevuld == 1


def test_de_tweede_taal_overruled_geen_gehoord_woord(tmp_path,
                                                     _tweetalig) -> None:
    """De eerste draai blijft de waarheid; dat is de hele reden dat deze
    samenvoeging de voorzichtigste van de acht was."""
    context = _tweetalig
    segmenten, _gevuld, _taal = pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "en", context.paths.output_dir / "original")
    teksten = [s.text for s in segmenten]
    assert "we jump" in teksten and "점프" not in teksten


def test_het_verslag_van_de_draai_noemt_de_tweede_taal(tmp_path,
                                                       _tweetalig) -> None:
    import json
    context = _tweetalig
    uitvoer = context.paths.output_dir / "original"
    pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "en", uitvoer)
    info = json.loads((uitvoer / "run_info.json").read_text(encoding="utf-8"))
    assert info["second_language"] == "ko"


def test_zonder_stukken_maar_met_tweede_taal_gaan_de_banen_toch_aan(
        tmp_path, _tweetalig, monkeypatch) -> None:
    """Anders zou een lied dat niet te knippen valt zijn tweede taal
    kwijtraken."""
    context = _tweetalig
    monkeypatch.setattr(pipeline, "_original_vocal_windows",
                        lambda c: [(0.0, 30.0)])
    segmenten, gevuld, _taal = pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "en", context.paths.output_dir / "original")
    assert gevuld == 1 and "뛰어" in [s.text for s in segmenten]


# --------------------------------------------------------------------------
# De cache
# --------------------------------------------------------------------------

def test_de_tweede_taal_hoort_in_de_cachesleutel() -> None:
    """Zet er een Koreaans couplet bij en de bewaarde transcriptie is
    het antwoord op een andere vraag."""
    source = inspect.getsource(pipeline.detect_track)
    assert 'step.get("second_language", second_code)) == second_code' in source
    assert '"second_language": second_code' in source


# --------------------------------------------------------------------------
# Wat eruit ging
# --------------------------------------------------------------------------

def test_de_zwakke_plekken_route_is_weg() -> None:
    """B538: zes woorden en 0% op een echte zin - te weinig aanloop voor
    Whisper. Het antwoord staat in het logboek, de route niet meer in de
    code (zoals bij 1.5.8 en 1.5.11c)."""
    from modules import test_panel

    for naam in ("weak_by_ratio", "useful_spans", "combine_in_spots",
                 "_pad_and_cap"):
        assert not hasattr(test_panel, naam), naam
    source = inspect.getsource(test_panel.two_language_trial)
    assert "spot" not in source.lower().replace("search_col_spot", "")


def test_de_proef_meet_nog_wel_of_de_samenvoeging_wint() -> None:
    """Eén lied is geen regel; de proef blijft bestaan om dat op een
    nieuw lied na te gaan."""
    from modules import test_panel

    codes = {trial.code: trial for trial in test_panel.HEAVY_TRIALS}
    assert "1.5.11g" in codes and not codes["1.5.11g"].off
    source = inspect.getsource(test_panel.two_language_trial)
    assert "search_fill_silence" in source and "merge_runs" in source


# --------------------------------------------------------------------------
# B539 - een opgepropte staart wordt over de zang uitgelegd
# --------------------------------------------------------------------------

def _regel(index, text, start, end):
    from modules.timing import Syllable, TimedLine
    woorden = text.split()
    stap = (end - start) / len(woorden)
    return TimedLine(
        index=index, text=text, crowd=False, block=0, quality="high",
        syllables=tuple(
            Syllable(("" if i == 0 else " ") + w,
                     start + i * stap, start + (i + 1) * stap)
            for i, w in enumerate(woorden)))


def _opgepropte_staart():
    """Het beeld van "Lied N": zes regels op de bodem achter elkaar,
    terwijl de zang daarna nog doorloopt."""
    from modules import timing
    kop = [_regel(0, "een echte zin met tijd", 10.0, 13.0),
           _regel(1, "nog een echte zin", 14.0, 17.0)]
    staart = [_regel(2 + i, f"regel {i}", 20.0 + i * 1.0, 21.0 + i * 1.0)
              for i in range(6)]
    vensters = [(10.0, 17.0), (20.0, 23.0), (26.0, 29.0), (32.0, 35.0),
                (38.0, 41.0)]
    return timing, kop + staart, vensters


def test_de_staart_gaat_over_de_zang_die_nog_komt() -> None:
    timing, regels, vensters = _opgepropte_staart()
    uit = timing.stretch_tail_over_singing(regels, vensters)
    assert [round(r.start, 1) for r in uit[:2]] == [10.0, 14.0]  # kop blijft
    starts = [r.start for r in uit[2:]]
    assert starts != [r.start for r in regels[2:]]
    assert max(starts) > 35.0        # de laatste vensters worden gebruikt
    assert starts == sorted(starts)  # en de volgorde blijft


def test_zonder_zang_erna_blijft_alles_staan() -> None:
    timing, regels, _ = _opgepropte_staart()
    vensters = [(10.0, 17.0), (20.0, 26.5)]      # zang stopt vlak na de staart
    uit = timing.stretch_tail_over_singing(regels, vensters)
    assert [r.start for r in uit] == [r.start for r in regels]


def test_een_staart_met_eigen_tijden_blijft_staan() -> None:
    """De regel grijpt alleen in waar de plaatsing zelf zegt dat ze
    niets te melden had: regels op de bodem van de minimumduur."""
    timing, regels, vensters = _opgepropte_staart()
    ruim = list(regels[:2]) + [
        _regel(2 + i, f"regel {i}", 20.0 + i * 3.0, 22.5 + i * 3.0)
        for i in range(6)]
    # zang die ruim NA de staart doorloopt, anders slaagt deze toets op
    # de zangtoets in plaats van op de bodemtoets
    ruime_vensters = vensters + [(44.0, 50.0)]
    uit = timing.stretch_tail_over_singing(ruim, ruime_vensters)
    assert [r.start for r in uit] == [r.start for r in ruim]


def test_een_laatste_regel_met_lengte_verbergt_de_staart_niet() -> None:
    """De laatste zin wordt vaak opgevuld tot het eind van het lied; die
    ene mag de vijftien opgepropte regels ervoor niet afdekken."""
    timing, regels, vensters = _opgepropte_staart()
    met_staart = list(regels)
    met_staart[-1] = _regel(7, "laatste zin", 25.0, 28.0)
    uit = timing.stretch_tail_over_singing(met_staart, vensters)
    assert [r.start for r in uit[2:]] != [r.start for r in met_staart[2:]]


def test_zonder_vensters_gebeurt_er_niets() -> None:
    timing, regels, _ = _opgepropte_staart()
    assert timing.stretch_tail_over_singing(regels, []) == regels
    assert timing.stretch_tail_over_singing(regels, None) == regels


def test_de_regels_houden_hun_eigen_lengte() -> None:
    """Verschuiven, niet uitrekken: de lettergrepen binnen een regel
    houden hun onderlinge verhouding."""
    timing, regels, vensters = _opgepropte_staart()
    uit = timing.stretch_tail_over_singing(regels, vensters)
    for voor, na in zip(regels[2:], uit[2:]):
        assert round(na.end - na.start, 3) == round(voor.end - voor.start, 3)
        assert len(na.syllables) == len(voor.syllables)


def test_de_meetlat_hoort_dit_te_zien() -> None:
    """B539 zit in sanitize_timing en niet in een stap die alleen de app
    doet - anders meet de meetlat iets anders dan de gebruiker krijgt."""
    import inspect
    from modules import timing
    bron = inspect.getsource(timing.sanitize_timing)
    assert "stretch_tail_over_singing(result, active_windows" in bron


def test_een_lied_van_korte_kreten_is_geen_staart() -> None:
    """B539 na de herlezing: zonder de eis dat de regel VOOR de staart
    geen bodemregel is, was een carnavalsdreun van twintig korte kreten
    één staart vanaf regel nul - en dan verlegt een regel over het EIND
    van een lied het hele lied."""
    from modules import timing
    regels = [_regel(i, f"hop {i}", 20.0 + i * 1.0, 21.0 + i * 1.0)
              for i in range(20)]
    vensters = [(20.0, 40.0), (46.0, 60.0)]
    uit = timing.stretch_tail_over_singing(regels, vensters)
    assert [r.start for r in uit] == [r.start for r in regels]


def test_de_staart_begint_op_het_eerste_venster() -> None:
    """Vier regels over tien vensters legde de eerste zes vensters leeg
    en schoof alles naar het eind van het lied."""
    from modules import timing
    vensters = [(20.0 + i * 5.0, 23.0 + i * 5.0) for i in range(10)]
    plaatsen = timing._spread_over_windows(4, vensters, 20.0, 70.0)
    assert plaatsen[0] == 20.0
    assert plaatsen == sorted(plaatsen)
    assert plaatsen[-1] < 60.0            # niet alles achteraan


def test_geen_regel_komt_voorbij_het_eind_van_het_lied() -> None:
    from modules import timing
    kop = [_regel(0, "een echte zin met tijd", 10.0, 13.0),
           _regel(1, "nog een echte zin", 14.0, 17.0)]
    staart = [_regel(2 + i, f"regel {i}", 20.0 + i * 1.0, 21.0 + i * 1.0)
              for i in range(6)]
    vensters = [(10.0, 17.0), (20.0, 30.0), (36.0, 44.0)]
    uit = timing.stretch_tail_over_singing(kop + staart, vensters,
                                           song_duration=40.0)
    assert max(r.end for r in uit) <= 40.0 + 1e-6


def test_te_weinig_ruimte_laat_alles_staan() -> None:
    """Liever de opgepropte staart dan een staart die gemeten lijkt."""
    from modules import timing
    kop = [_regel(0, "een echte zin met tijd", 10.0, 13.0)]
    staart = [_regel(1 + i, f"regel {i}", 20.0 + i * 1.0, 21.0 + i * 1.0)
              for i in range(8)]
    # maar drie seconden zang voor acht regels
    vensters = [(10.0, 13.0), (20.0, 23.0), (40.0, 41.0)]
    uit = timing.stretch_tail_over_singing(kop + staart, vensters)
    assert [r.start for r in uit] == [r.start for r in kop + staart]


def test_een_uitgezette_regel_eet_geen_zang_op() -> None:
    """Een regel die niet op het scherm komt (B180) mag geen stuk zang
    claimen dat niemand ziet."""
    from dataclasses import replace
    from modules import timing
    kop = [_regel(0, "een echte zin met tijd", 10.0, 13.0)]
    staart = [_regel(1 + i, f"regel {i}", 20.0 + i * 1.0, 21.0 + i * 1.0)
              for i in range(6)]
    staart[2] = replace(staart[2], disabled=True)
    vensters = [(10.0, 13.0), (20.0, 30.0), (36.0, 46.0)]
    uit = timing.stretch_tail_over_singing(kop + staart, vensters)
    zichtbaar = [r.start for r in uit[1:] if not r.disabled]
    assert len(zichtbaar) == 5 and zichtbaar == sorted(zichtbaar)
    assert max(zichtbaar) > 36.0          # de laatste vensters zijn gebruikt


def test_een_regel_zonder_lettergrepen_laat_de_stap_niet_omvallen() -> None:
    from dataclasses import replace
    from modules import timing
    regel = _regel(0, "een zin", 10.0, 11.0)
    leeg = replace(regel, syllables=())
    assert timing._moved_to(leeg, 50.0) is leeg


def test_zonder_zangvensters_geen_tweede_draai(tmp_path, _tweetalig,
                                               monkeypatch) -> None:
    """B538 na de herlezing: zonder gemeten zang kan een tweede lezing
    per definitie niets invullen (een woord telt alleen als het op zang
    staat), dus dat zou een hele Whisper-draai voor zeker niets zijn -
    en de voortgangsbalk zou er ook nog bij stilvallen."""
    context = _tweetalig
    gevraagd = []
    echt = whisper.transcribe_slice

    def tel(*args, **kwargs):
        gevraagd.append(kwargs.get("language_override"))
        return echt(*args, **kwargs)

    monkeypatch.setattr(whisper, "transcribe_slice", tel)
    monkeypatch.setattr(pipeline, "_original_vocal_windows", lambda c: [])
    monkeypatch.setattr(
        whisper, "transcribe",
        lambda *a, **k: whisper.segments_from_dicts([
            _segment("we jump", 1.0, 2.0,
                     [("we", 1.0, 1.4), ("jump", 1.5, 2.0)])]))
    segmenten, gevuld, taal = pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "en", context.paths.output_dir / "original")
    assert gevraagd == [] and gevuld == 0 and taal == ""


def test_de_gelezen_taal_gaat_terug_naar_de_cachesleutel() -> None:
    """Anders staat er "ko" in de sleutel terwijl er geen Koreaanse
    draai geweest is, en draait de volgende keer alles opnieuw."""
    source = inspect.getsource(pipeline.detect_track)
    assert "segments, filled, second_code = _transcribe_in_pieces(" in source


def test_kanji_maken_van_een_japans_lied_geen_chinees(tmp_path) -> None:
    """Kanji tellen naar hun blok als Chinees (B495); een Japans lied
    staat er vol mee, en dat zou elke keer een hele Chinese draai
    kosten voor een schrift dat de eerste draai al kent."""
    context = _context(tmp_path, "hana no uta\n花 歌 花 歌 花 歌\n")
    assert pipeline._second_language_code(context, "ja") == ""
    assert pipeline._second_language_code(context, "nl") == "zh"


def test_herstellen_bouwt_dezelfde_timing_als_bouwen() -> None:
    """B539: "Originele timing herstellen" gaf een andere timing dan de
    bouwstap zelf, omdat het de zangvensters niet meegaf - en juist
    B336 en B539 hangen daaraan."""
    from pathlib import Path
    from modules import gui
    bron = Path(gui.__file__).read_text(encoding="utf-8")
    plek = bron[bron.index("def reset_original"):]
    plek = plek[:plek.index("mapping = fresh")]
    assert "active_windows=pipeline._vocal_windows(context)" in plek


def test_de_proef_meet_de_samenvoeging_die_productie_maakt() -> None:
    """De rij in de tabel moet dezelfde zijn als wat het programma doet:
    de eerste draai als waarheid, de stukken EN de tweede taal als
    invullers."""
    import inspect
    from modules import test_panel
    bron = inspect.getsource(test_panel.two_language_trial)
    assert "extra += list(chunked_first)" in bron
