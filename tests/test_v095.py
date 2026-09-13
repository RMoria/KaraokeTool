"""Tests voor v0.95 (B288 t/m B302).

Een opruim- en correctheidsronde, voortgekomen uit een volledige review van
de codebase op logica, dode code en vertaalbaarheid. De bugs hieronder
waren geen van alle door de gebruiker gemeld: ze kwamen uit de review en
zijn stuk voor stuk met een concreet faalscenario gereproduceerd voordat ze
zijn gefixt.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import align, config, karaoke, pipeline, timing  # noqa: E402
from modules.config import default_config  # noqa: E402
from modules.filesystem import (ProjectPaths, ProjectStore,  # noqa: E402
                                ensure_directories)
from modules.pipeline import AppContext  # noqa: E402
from modules.song_text import LyricWord, align_lyrics  # noqa: E402
from modules.whisper import Segment, Word  # noqa: E402


def _context(tmp_path: Path) -> AppContext:
    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    return AppContext(config=default_config(), paths=paths,
                      store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B288 - priority_lines vergeleek een woordindex met een regelnummer
# --------------------------------------------------------------------------

def _viva_segments() -> tuple:
    """Transcriptie waarin het vulwoord "oh" als "hoa" gehoord is.

    similarity("oh", "hoa") = 0.5: onder de normale vulwoorddrempel (0.6),
    maar boven de voorrangsdrempel (0.5). Zo is aan de koppeling af te lezen
    of de voorrang wel of niet is toegepast.
    """
    return (
        Segment(0, "niets veranderd hoa het voelt", 0.0, 5.0, (
            Word("niets", 0.0, 0.5, 0.9),
            Word("veranderd", 0.6, 1.2, 0.9),
            Word("hoa", 1.5, 1.8, 0.9),
            Word("het", 2.0, 2.4, 0.9),
            Word("voelt", 2.5, 3.0, 0.9),
        )),
    )


def test_priority_lines_werkt_op_regelnummer_niet_op_woordindex() -> None:
    """B288: alle woorden staan op regel 5. Geef je regel 5 als
    voorrangsregel, dan MOET de soepelere drempel gelden en wordt "oh"
    alsnog gekoppeld. Vóór de fix werd ``i in priority`` getoetst - met
    ``i`` de woordindex - en gebeurde er niets."""
    lyrics = tuple(LyricWord(i, t, 5) for i, t in enumerate(
        ["niets", "veranderd", "oh", "het", "voelt"]))
    aligned = align_lyrics(lyrics, _viva_segments(), skip_filler=True,
                           priority_lines=frozenset({5}))
    oh = aligned[2]
    assert oh.matched_text == "hoa", "voorrangsregel verlaagde de drempel niet"


def test_priority_lines_raakt_niet_de_verkeerde_woorden() -> None:
    """B288, andere kant: regelnummer 2 is hier GEEN regel van deze woorden
    (die staan allemaal op regel 5). Vóór de fix koppelde dat toevallig het
    derde woord (index 2), puur omdat het nummer samenviel."""
    lyrics = tuple(LyricWord(i, t, 5) for i, t in enumerate(
        ["niets", "veranderd", "oh", "het", "voelt"]))
    aligned = align_lyrics(lyrics, _viva_segments(), skip_filler=True,
                           priority_lines=frozenset({2}))
    assert aligned[2].matched_text is None, \
        "woordindex werd nog steeds als regelnummer gebruikt"


# --------------------------------------------------------------------------
# B289 - lang="nl" in een booleaans veld
# --------------------------------------------------------------------------

def test_timedline_from_text_zet_lang_niet_op_een_string() -> None:
    """B289: ``Syllable.lang`` betekent "lang aangehouden noot" en stuurt de
    onderstreping in de render aan. Er stond ``lang="nl"`` (verwarring met
    de taalparameter); een niet-lege string is truthy, dus élke lettergreep
    werd onderstreept."""
    line = timing.timedline_from_text(0, "hallo wereld", 0.0, 2.0)
    assert [s.held for s in line.syllables] == [False, False, False, False]
    assert not any(s.held for s in line.syllables)


# --------------------------------------------------------------------------
# B290 - distribute_over_windows crashte bij meer vensters dan woorden
# --------------------------------------------------------------------------

@pytest.mark.parametrize("n_words,n_windows",
                         [(2, 4), (2, 9), (3, 5), (4, 6), (2, 12)])
def test_distribute_over_windows_crasht_niet_bij_veel_vensters(
    n_words: int, n_windows: int,
) -> None:
    """B290: zodra een regel ``n_woorden + 2`` of meer zangvensters bevatte,
    liep de klem voorbij het laatste woord en gaf ``woord_spans[wi]`` een
    IndexError. Die werd door het vangnet in
    ``pipeline._apply_energy_word_timing`` opgeslokt, waardoor de
    energie-woordtiming van het HELE lied stilzwijgend uitviel."""
    text_value = " ".join(f"woord{i}" for i in range(n_words))
    line = timing.timedline_from_text(0, text_value, 0.0, 20.0)
    usable_windows = [(i * 1.5, i * 1.5 + 1.0) for i in range(n_windows)]
    uit = timing.distribute_over_windows(line, usable_windows)
    assert len(uit.syllables) == len(line.syllables)


def test_distribute_over_windows_behoudt_volgorde_en_lettergrepen() -> None:
    """B290: na het samenvoegen van overtollige vensters moeten de
    lettergrepen nog steeds compleet, oplopend en niet-overlappend zijn."""
    line = timing.timedline_from_text(0, "een twee drie", 0.0, 20.0)
    usable_windows = [(i * 2.0, i * 2.0 + 1.0) for i in range(8)]
    uit = timing.distribute_over_windows(line, usable_windows)
    assert len(uit.syllables) == len(line.syllables)
    times = [(s.start, s.end) for s in uit.syllables]
    assert all(a <= b for a, b in times)
    assert all(times[i][1] <= times[i + 1][0] + 1e-6
               for i in range(len(times) - 1))


def test_distribute_over_windows_houdt_de_grootste_pauzes() -> None:
    """B290: overtollige vensters worden samengevoegd op de KLEINSTE
    tussenpauze, zodat juist de duidelijke pauzes (waar B234 om draait)
    blijven staan en de buitenspan van de regel intact blijft."""
    line = timing.timedline_from_text(0, "een twee", 0.0, 20.0)
    # Twee vensters dicht bij elkaar, dan een groot gat, dan nog een.
    usable_windows = [(0.0, 1.0), (1.1, 2.0), (10.0, 11.0)]
    uit = timing.distribute_over_windows(line, usable_windows)
    assert uit.syllables[0].start == pytest.approx(0.0, abs=0.05)
    assert uit.syllables[-1].end == pytest.approx(11.0, abs=0.05)


# --------------------------------------------------------------------------
# B291 - blok en uitgeschakeld gingen verloren bij een tekstwijziging
# --------------------------------------------------------------------------

def test_sync_timing_behoudt_blok_en_uitgeschakeld(tmp_path: Path) -> None:
    """B291: bij het doorvoeren van een gecorrigeerde karaoketekst werden
    ``blok`` en ``uitgeschakeld`` niet meegegeven aan de nieuwe
    ``TimedLine``, waardoor ze terugvielen op 0/False. Een regel die de
    gebruiker had uitgeschakeld (B180) stond na een typefoutcorrectie dus
    weer gewoon in de video."""
    from modules.karaoke_text import TextLine

    context = _context(tmp_path)
    timed = (
        timing.TimedLine(
            index=0, text="eerste regel", crowd=False, block=0,
            syllables=(timing.Syllable("eerste", 0.0, 1.0),
                       timing.Syllable(" regel", 1.0, 2.0))),
        timing.TimedLine(
            index=1, text="tweede regel", crowd=False, block=1,
            disabled=True, quality="word",
            syllables=(timing.Syllable("tweede", 2.0, 3.0),
                       timing.Syllable(" regel", 3.0, 4.0))),
    )
    timing.save_timing(timed, context.paths.timing_file)

    old = (TextLine(index=0, text="eerste regel", crowd=False, block=0),
           TextLine(index=1, text="tweede regel", crowd=False, block=1))
    new = (TextLine(index=0, text="eerste regel", crowd=False, block=0),
             TextLine(index=1, text="tweede regels", crowd=False, block=1))

    updated, _message = pipeline.sync_timing_with_text_change(
        context, old, new)
    assert updated is True

    na = timing.load_timing(context.paths.timing_file)
    assert na[1].text == "tweede regels"          # de wijziging is door
    assert na[1].disabled is True, "uitgeschakeld ging verloren"
    assert na[1].block == 1, "blok ging verloren"
    assert na[1].quality == "word"             # bestond al, blijft
    assert na[0].block == 0                        # ongewijzigde regel intact


# --------------------------------------------------------------------------
# B292 - losse eindjes uit v0.93/v0.94
# --------------------------------------------------------------------------

def test_word_in_lyrics_heeft_geen_dode_floor_parameter() -> None:
    """B292: ``_word_in_lyrics`` had een ``floor``-parameter die nooit
    anders dan met de default werd aangeroepen, terwijl de docstring
    suggereerde dat de brede B285-check hem gebruikte. Die check gaat via
    ``_best_lyrics_match``; wie op de docstring afging, stelde het verkeerde
    bij."""
    import inspect

    params = inspect.signature(pipeline._word_in_lyrics).parameters
    assert "floor" not in params
    assert list(params) == ["word", "lyric_keys"]


def test_dode_restore_interval_helpers_zijn_weg() -> None:
    """B292: ``restore_intervals_to_dicts``/``_from_dicts`` (B282) werden
    nergens aangeroepen én beschreven een ander formaat dan er werkelijk
    wordt opgeslagen (``restore_fragmenten`` bewaart drietallen)."""
    assert not hasattr(karaoke, "restore_intervals_to_dicts")
    assert not hasattr(karaoke, "restore_intervals_from_dicts")


# --------------------------------------------------------------------------
# B301 - ongecontroleerde drempel en misleidend samengevoegd label
# --------------------------------------------------------------------------

def test_align_min_confidence_wordt_gecontroleerd(tmp_path: Path) -> None:
    """B301: ``align.min_confidence`` was de enige drempel zonder controle,
    terwijl 0.0 de gewogen middeling in ``align._build_regions`` door nul
    laat delen."""
    import json
    from dataclasses import replace

    cfg = default_config()
    kapot = replace(cfg, align=replace(cfg.align, min_confidence=0.0))
    with pytest.raises(config.ConfigError, match="align.min_confidence"):
        config._validate(kapot)

    # En via het echte laadpad (config.json op schijf).
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"align": {"min_confidence": 0.0}}),
                   encoding="utf-8")
    with pytest.raises(config.ConfigError, match="align.min_confidence"):
        config.load_config(path)


def test_build_regions_overleeft_nulgewichten() -> None:
    """B301: dit is precies het pad dat de configcontrole hierboven nu
    afsluit, maar ``_build_regions`` is ook los aanroepbaar. Met
    ``min_confidence=0.0`` glippen vensters met confidence 0.0 door de
    filter heen en kwamen ze bij ``np.average(..., weights=...)`` terecht -
    dat deelt door de gewichtensom en gaf een ZeroDivisionError. Nu valt hij
    terug op het ongewogen gemiddelde."""
    from dataclasses import replace

    settings = replace(default_config().align, min_confidence=0.0)
    # Beide offsets binnen de tolerantie (40 ms), zodat ze één groep vormen
    # en dus samen door de gewogen middeling gaan.
    usable_windows = [align.WindowOffset(start=0.0, end=1.0, offset=0.10,
                                   confidence=0.0),
                align.WindowOffset(start=1.0, end=2.0, offset=0.12,
                                   confidence=0.0)]
    regios = align._build_regions(usable_windows, duration=2.0, fallback_offset=0.0,
                                  fallback_confidence=0.0,
                                  settings=settings)
    assert regios, "geen regio's opgeleverd"
    # Ongewogen gemiddelde van 0.10 en 0.12; vóór de fix een ZeroDivisionError.
    assert regios[0].offset == pytest.approx(0.11)


def test_merge_intervals_noemt_alle_samengevoegde_klanken() -> None:
    """B301: een samengevoegd dempingsvak hield alleen het label van het
    eerste fragment, terwijl het in werkelijkheid meerdere clusters dempte -
    misleidend bij het aan-/uitvinken in de dempingseditor. De demping zelf
    wordt de sterkste van de twee."""
    merged = karaoke.merge_intervals((
        karaoke.DampingInterval(label="oe", start=0.0, end=1.0,
                                gain_db=-20.0),
        karaoke.DampingInterval(label="woo", start=1.0, end=2.0,
                                gain_db=-30.0),
    ))
    assert len(merged) == 1
    assert merged[0].label == "oe+woo"
    assert merged[0].gain_db == -30.0          # sterkste demping wint
    assert merged[0].start == 0.0 and merged[0].end == 2.0


def test_merge_intervals_herhaalt_hetzelfde_label_niet() -> None:
    """B301: drie aaneengesloten fragmenten van dezelfde klank leveren
    "oe", niet "oe+oe+oe"."""
    merged = karaoke.merge_intervals(tuple(
        karaoke.DampingInterval(label="oe", start=float(i), end=float(i) + 1,
                                gain_db=-25.0)
        for i in range(3)))
    assert len(merged) == 1
    assert merged[0].label == "oe"


def test_merge_intervals_laat_losse_fragmenten_met_rust() -> None:
    """B301: fragmenten die niet overlappen blijven onveranderd - label en
    demping van elk apart."""
    merged = karaoke.merge_intervals((
        karaoke.DampingInterval(label="oe", start=0.0, end=1.0,
                                gain_db=-20.0),
        karaoke.DampingInterval(label="woo", start=50.0, end=51.0,
                                gain_db=-30.0),
    ))
    assert [iv.label for iv in merged] == ["oe", "woo"]
    assert [iv.gain_db for iv in merged] == [-20.0, -30.0]


# --------------------------------------------------------------------------
# B293/B295 - dode code en dode vertaalsleutels
# --------------------------------------------------------------------------

def test_dode_functies_en_constanten_zijn_weg() -> None:
    """B293: opgeruimd omdat niets ze aanriep. ``detect_words`` deed
    bovendien exact hetzelfde als ``detect_tracks(parallel=False)`` - twee
    ingangen naar dezelfde stap 1 betekent dat een wijziging in de ene
    stilzwijgend langs de andere gaat."""
    from modules import phonetics

    assert not hasattr(phonetics, "_lang_dir_name")
    assert not hasattr(pipeline, "TrackProgressCallback")
    assert not hasattr(pipeline, "detect_words")
    assert hasattr(pipeline, "detect_tracks")       # de overgebleven ingang


def test_smooth_regions_heeft_geen_dode_parameter() -> None:
    """B293: ``fallback_offset`` werd nergens in de body gebruikt sinds de
    overstap op trend-detectie (B249)."""
    import inspect

    params = inspect.signature(align._smooth_regions).parameters
    assert list(params) == ["regions"]


def test_format_time_staat_maar_op_een_plek() -> None:
    """B293: ``gui.py`` had een letterlijk identieke privékopie van
    ``cluster._format_time``. Nu is er één publieke bron."""
    from modules import cluster, gui

    assert cluster.format_time(75.25) == "1:15.2"
    assert gui._format_time is cluster.format_time


def test_geen_dode_vertaalsleutels_meer() -> None:
    """B295: 14 sleutels stonden nog in beide woordenboeken maar werden
    nergens meer aangeroepen (o.a. de wezen van een dialoog die door een
    foutmelding is vervangen)."""
    from modules.translations import TRANSLATIONS

    for weg in ("options_group", "analyse_on", "analyse_hint",
                "render_audio_demucs", "analyse_toggle_log",
                "track_required_body", "alignment_remade", "mark_ok",
                "mark_missing", "video_input_incomplete_title",
                "video_input_incomplete_body", "video_input_complete_title",
                "video_input_complete_body", "open"):
        assert weg not in TRANSLATIONS["nl"], f"{weg} nog in nl"
        assert weg not in TRANSLATIONS["en"], f"{weg} nog in en"


# --------------------------------------------------------------------------
# B296/B297/B298 - vertaalbaarheid en juiste stapverwijzingen
# --------------------------------------------------------------------------

def test_pipeline_foutmeldingen_zijn_vertaalbaar(tmp_path: Path) -> None:
    """B296: de foutmeldingen uit de pijplijn komen via ``_on_failed`` in een
    QMessageBox terecht; ze stonden allemaal hardgecodeerd in het
    Nederlands. Nu volgen ze de ingestelde taal."""
    from modules import translations
    from modules.pipeline import PipelineError

    context = _context(tmp_path)
    try:
        translations.set_language("en")
        with pytest.raises(PipelineError) as error:
            pipeline.load_segments(context, "original")
        assert "No transcription" in str(error.value)
        # B325: de knopnaam komt uit dezelfde vertaalsleutel als de knop.
        assert translations.TRANSLATIONS["en"]["step_detect"] \
            in str(error.value)

        translations.set_language("nl")
        with pytest.raises(PipelineError) as error:
            pipeline.load_segments(context, "original")
        assert "Geen transcriptie" in str(error.value)
    finally:
        translations.set_language("nl")


def test_geen_hardgecodeerde_pipelinefouten_meer() -> None:
    """B296: regressiewacht - elke ``raise PipelineError`` gaat via ``t()``
    of geeft een bestaande uitzondering door, niet een letterlijke tekst."""
    import re

    source = (Path(__file__).parent.parent / "modules" / "pipeline.py").read_text(
        encoding="utf-8")
    letterlijk = re.findall(r'raise PipelineError\("', source)
    assert not letterlijk, f"{len(letterlijk)} hardgecodeerde foutmelding(en)"


def test_html_rapport_volgt_de_taal() -> None:
    """B296: het HTML-clusterrapport was volledig hardgecodeerd Nederlands,
    inclusief de titel en de kopjes."""
    from modules import cluster, translations
    from modules.whisper import Segment, Word

    c = cluster.Cluster(id=1, label="oeh", members=(("oeh", 3),),
                        occurrences=(cluster.Occurrence("oeh", 1.5, 1.9, 0.9,
                                                       0),),
                        segments=(0,), frequency=5, avg_confidence=0.88,
                        avg_duration_s=0.4, avg_pause_s=2.1)
    segs = (Segment(0, "oeh oe", 0.5, 1.5, (Word("oeh", 0.5, 0.9, 0.9),)),)
    try:
        translations.set_language("en")
        html = cluster._render_html((c,), segs)
        assert "<html lang=en>" in html
        assert "Sound clusters" in html
        assert "Avg. duration" in html

        translations.set_language("nl")
        html = cluster._render_html((c,), segs)
        assert "<html lang=nl>" in html
        assert "Klankclusters" in html
    finally:
        translations.set_language("nl")


def test_stapnummers_in_teksten_kloppen_met_de_knoppen() -> None:
    """B297: teksten verwezen naar "stap 2 (Analyse)" en "stap 3
    (Uitlijnen)", terwijl de knoppen anders heten - en een aparte
    Uitlijnen-stap bestaat niet meer (die loopt automatisch).

    B325: de nummering is <tab>.<knop>. geworden en een tekst noemt de
    knop niet meer bij naam maar bij sleutel, zodat hij niet opnieuw uit
    de pas kan lopen.
    """
    from modules import translations as translations_module
    from modules.translations import TRANSLATIONS

    for taalcode in ("nl", "en"):
        translations = TRANSLATIONS[taalcode]
        assert translations["step_analyse"].startswith("1.3. ")
        assert "{step_analyse}" in translations["prereq_need_analyse"]
        # Nergens meer een verwijzing naar een niet-bestaande Uitlijnen-stap.
        for key, text_value in translations.items():
            assert "Uitlijnen'" not in text_value, key
            assert "stap 2 (Analyse)" not in text_value, key

    # De ingevulde tekst bevat de actuele knopnaam.
    try:
        translations_module.set_language("nl")
        assert "1.3. Analyse" in translations_module.t("prereq_need_analyse")
        translations_module.set_language("en")
        assert "1.3. Analyse" in translations_module.t("prereq_need_analyse")
    finally:
        translations_module.set_language("nl")


def test_geen_interne_bugreferenties_in_zichtbare_teksten() -> None:
    """B298: de tooltip van de regel-schakelaar eindigde op "(B180)" - een
    interne bevindingsnummering die de gebruiker niets zegt."""
    import re

    from modules.translations import TRANSLATIONS

    for taalcode, translations in TRANSLATIONS.items():
        for key, text_value in translations.items():
            assert not re.search(r"\bB\d{2,3}\b", text_value), \
                f"{taalcode}/{key} bevat een interne bugreferentie: {text_value}"


def test_taalsleutels_blijven_in_balans() -> None:
    """De nl- en en-woordenboeken moeten exact dezelfde sleutels houden,
    ook na het toevoegen van ~45 nieuwe en het schrappen van 14."""
    from modules.translations import TRANSLATIONS

    assert set(TRANSLATIONS["nl"]) == set(TRANSLATIONS["en"])
