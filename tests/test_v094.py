"""Tests voor v0.94 (B285/B286/B287).

Drie samenhangende verbeteringen aan de woord-koppeling, naar aanleiding
van een echte "Lied_S"-uitlijning die aan het einde in de soep liep:

1. **B285** - Liedbrede hallucinatiecheck in
   ``pipeline._filter_hallucinations``: ook zónder dat een woord op de
   vaste hallucinatielijst staat, wordt een segment gedropt als geen van
   de kernwoorden ook maar redelijk op de songtekst matcht én Whisper's
   eigen laagste woord-confidence laag is (reproduceert de "Heerlijke
   Heer, Heerlijke Heer."-hallucinatie na een lange transcriptie-stilte).
2. **B286** - ``songtekst.is_repeated_filler_line``/``repeated_filler_lines``:
   een songtekstregel die bewust uit herhaalde vulklanken bestaat (bv.
   "La la la la") wordt niet als incidenteel vulwoord overgeslagen.
3. **B287** - Statusmarkering in de koppel-editor
   (``pipeline.word_coupling_view`` en ``modules.koppeleditor``): elk
   niet-gekoppeld songtekstwoord krijgt een van drie visueel verschillende
   markeringen ("filler_skipped", "no_match",
   "hallucination_filtered"), zodat de gebruiker ziet of (en waarom) hij
   zelf moet koppelen.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline, song_text  # noqa: E402
from modules.config import default_config  # noqa: E402
from modules.filesystem import ProjectPaths, ProjectStore, ensure_directories  # noqa: E402
from modules.pipeline import AppContext  # noqa: E402
from modules.song_text import LyricWord, align_lyrics  # noqa: E402
from modules.whisper import Segment, Word, save_segments  # noqa: E402


def _context(tmp_path: Path) -> AppContext:
    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    return AppContext(config=default_config(), paths=paths,
                      store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B285 (1): liedbrede hallucinatiecheck in _filter_hallucinations
# --------------------------------------------------------------------------

def test_filter_hallucinations_broad_check_drops_heerlijke_heer() -> None:
    """Reproductie van de Lied_S-bug: na een lange transcriptie-stilte
    hallucineert Whisper "Heerlijke Heer, Heerlijke Heer.", met een
    inconsistente woord-confidence (0.34/0.48/0.72/0.99, echte cijfers uit
    het project) en geen enkele songtekst-match. De liedbrede check moet
    dit segment nu ook droppen, ook al staat geen van de woorden op de
    vaste hallucinatielijst."""
    segs = (
        Segment(0, "Heerlijke Heer, Heerlijke Heer.", 199.44, 202.84, (
            Word("Heerlijke", 199.440, 200.480, 0.3403),
            Word("Heer,", 200.480, 201.140, 0.4825),
            Word("Heerlijke", 201.140, 202.020, 0.7155),
            Word("Heer.", 202.020, 202.840, 0.9926),
        )),
        Segment(1, "Geef mij maar alle dagen zon", 166.32, 169.44, (
            Word("Geef", 166.320, 166.940, 0.9766),
            Word("mij", 166.940, 167.140, 0.9990),
            Word("maar", 167.140, 167.720, 0.9959),
        )),
    )
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "Geef mij maar alle dagen zon Espagna por favor".split()))
    dropped: list = []
    kept = pipeline._filter_hallucinations(segs, lyrics, dropped_out=dropped)
    assert [s.text for s in kept] == ["Geef mij maar alle dagen zon"]
    assert [s.text for s in dropped] == ["Heerlijke Heer, Heerlijke Heer."]


def test_filter_hallucinations_broad_check_skipped_without_lyrics() -> None:
    """Zonder songtekst (``lyrics=None``) slaat de liedbrede check helemaal
    over - er is dan niets om "matcht nergens mee" tegen af te zetten en de
    check zou te makkelijk raak schieten."""
    segs = (
        Segment(0, "Heerlijke Heer, Heerlijke Heer.", 199.44, 202.84, (
            Word("Heerlijke", 199.440, 200.480, 0.3403),
            Word("Heer,", 200.480, 201.140, 0.4825),
            Word("Heerlijke", 201.140, 202.020, 0.7155),
            Word("Heer.", 202.020, 202.840, 0.9926),
        )),
    )
    kept = pipeline._filter_hallucinations(segs)
    assert len(kept) == 1


def test_filter_hallucinations_broad_check_spares_high_confidence() -> None:
    """Een segment waarvan Whisper élk woord met hoge confidence
    transcribeerde blijft staan, ook als het toevallig niet matcht met de
    songtekst - dat kan een ad-lib zijn, geen hallucinatie."""
    segs = (
        Segment(0, "Kom op mensen allemaal", 50.0, 52.0, (
            Word("Kom", 50.0, 50.4, 0.95),
            Word("op", 50.4, 50.6, 0.93),
            Word("mensen", 50.6, 51.2, 0.97),
            Word("allemaal", 51.2, 52.0, 0.91),
        )),
    )
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "Ik hou van dansen en muziek".split()))
    kept = pipeline._filter_hallucinations(segs, lyrics)
    assert len(kept) == 1


def test_filter_hallucinations_broad_check_spares_partial_match() -> None:
    """Als minstens één kernwoord redelijk matcht met de songtekst, blijft
    het hele segment staan - ook al is Whisper's confidence op de rest laag.
    Eén echt woord tussen ruis is genoeg om het segment te sparen."""
    segs = (
        Segment(0, "Blkjh Espagna Xyzzy", 10.0, 12.0, (
            Word("Blkjh", 10.0, 10.5, 0.2),
            Word("Espagna", 10.5, 11.2, 0.3),
            Word("Xyzzy", 11.2, 12.0, 0.2),
        )),
    )
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "E viva Espagna".split()))
    kept = pipeline._filter_hallucinations(segs, lyrics)
    assert len(kept) == 1


def test_filter_hallucinations_broad_check_needs_min_kernwoorden() -> None:
    """Bij minder dan ``_SEGMENT_HALLUCINATION_MIN_KERNWOORDEN`` kernwoorden
    slaat de liedbrede check over - te weinig fonetisch materiaal om
    betrouwbaar "hoort nergens bij" vast te stellen."""
    segs = (Segment(0, "Xyzzy", 10.0, 10.5, (Word("Xyzzy", 10.0, 10.5, 0.2),)),)
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "Geef mij maar alle dagen zon".split()))
    kept = pipeline._filter_hallucinations(segs, lyrics)
    assert len(kept) == 1


def test_best_lyrics_match_ignores_degenerate_short_keys() -> None:
    """'heer' fonetiseert (h/r vallen weg, ``cluster._DROPPED``) tot het ene
    teken 'e' - toevallig gelijk aan de sleutel van het songtekstwoordje 'E'
    (uit "E viva Espagna"). Zonder ondergrens zou zo'n eenmalig teken een
    valse match van 1.0 geven en de hele liedbrede check onbruikbaar maken;
    ``_best_lyrics_match`` moet zulke te-korte sleutels negeren."""
    from modules import cluster

    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "E viva Espagna".split()))
    lyric_keys = frozenset(cluster.phonetic_key(w.text) for w in lyrics)
    assert cluster.phonetic_key("heer") == "e"     # vooronderstelling van de test
    assert pipeline._best_lyrics_match("heer", lyric_keys) == 0.0


def test_filter_hallucinations_dropped_out_achterwaarts_compatibel() -> None:
    """Het optionele ``dropped_out``-argument verzamelt de weggegooide
    segmenten zonder de return-waarde te wijzigen - alle bestaande
    aanroepen (zonder dit argument) blijven precies hetzelfde werken."""
    segs = (Segment(0, "MUZIEK", 28.6, 29.0,
                    (Word("MUZIEK", 28.6, 29.0, 0.5),)),
            Segment(1, "Bertus", 30.0, 30.5,
                    (Word("Bertus", 30.0, 30.5, 0.9),)))
    dropped: list = []
    kept = pipeline._filter_hallucinations(segs, dropped_out=dropped)
    kept_old = pipeline._filter_hallucinations(segs)
    assert kept == kept_old
    assert [s.text for s in kept] == ["Bertus"]
    assert [s.text for s in dropped] == ["MUZIEK"]


# --------------------------------------------------------------------------
# B286 (2): herhaalde vulklanken als bewuste songtekst
# --------------------------------------------------------------------------

def test_is_repeated_filler_line_herkent_herhaling() -> None:
    assert song_text.is_repeated_filler_line(["la", "la", "la", "la"]) is True
    assert song_text.is_repeated_filler_line(["la", "la", "la"]) is True  # net genoeg


def test_is_repeated_filler_line_false_voor_kort_of_echt() -> None:
    assert song_text.is_repeated_filler_line(["oh", "ja"]) is False   # te kort
    assert song_text.is_repeated_filler_line(
        ["la", "la", "hallo"]) is False                              # geen vulwoord


def test_repeated_filler_lines_groepeert_per_regel() -> None:
    lyrics = (
        LyricWord(0, "Dit", 0), LyricWord(1, "is", 0), LyricWord(2, "text", 0),
        LyricWord(3, "la", 1), LyricWord(4, "la", 1),
        LyricWord(5, "la", 1), LyricWord(6, "la", 1),
    )
    assert song_text.repeated_filler_lines(lyrics) == frozenset({1})


def test_align_lyrics_repeated_filler_line_wordt_niet_overgeslagen(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Een songtekstregel die bewust uit herhaalde vulklanken bestaat ("la
    la la la" als één regel) telt niet mee als "vulwoord om over te slaan":
    ``align_lyrics`` behandelt hem dan identiek aan ``skip_filler=False``
    (er komt geen woord via ``repeated_filler_lines`` in de skip-set
    terecht, dus de functie neemt meteen de gewone DP-uitlijning, zonder
    "overgeslagen"-logregel). Vier LOSSE vulwoord-regels (elk maar 1 woord,
    dus geen herhaling binnen één regel) worden ter vergelijking wél
    overgeslagen."""
    segments = (
        Segment(0, "la la la la", 10.0, 12.0, (
            Word("la", 10.0, 10.5, 0.9), Word("la", 10.5, 11.0, 0.9),
            Word("la", 11.0, 11.5, 0.9), Word("la", 11.5, 12.0, 0.9),
        )),
    )
    repeated = tuple(LyricWord(i, "la", 0) for i in range(4))    # 1 regel
    los = tuple(LyricWord(i, "la", i) for i in range(4))         # 4 regels

    with caplog.at_level(logging.INFO, logger="modules.song_text"):
        caplog.clear()
        met_skip = align_lyrics(repeated, segments, skip_filler=True)
        assert not any("overgeslagen" in r.message for r in caplog.records)
    zonder_skip = align_lyrics(repeated, segments, skip_filler=False)
    assert met_skip == zonder_skip

    with caplog.at_level(logging.INFO, logger="modules.song_text"):
        caplog.clear()
        align_lyrics(los, segments, skip_filler=True)
        assert any("4 woord(en) overgeslagen" in r.message
                  for r in caplog.records)


# --------------------------------------------------------------------------
# B287 (3): statusmarkering in de koppel-editor
# --------------------------------------------------------------------------

def test_word_overlaps_dropped_segment_binnen_ankervenster() -> None:
    """Een ongekoppeld woord tussen twee gekoppelde buren waarbinnen een
    weggefilterd hallucinatie-segment valt, telt als 'overlapt'."""
    from modules.pipeline import _word_overlaps_dropped_segment
    from modules.song_text import AlignedWord

    aligned = (
        AlignedWord(LyricWord(0, "mij", 0), 1.0, 1.5, "mij", 0.9),
        AlignedWord(LyricWord(1, "Espagna", 0), None, None, None, 0.0),
        AlignedWord(LyricWord(2, "zon", 0), 5.0, 5.5, "zon", 0.9),
    )
    dropped = [Segment(9, "Heerlijke Heer", 2.0, 4.0, ())]
    assert _word_overlaps_dropped_segment(aligned, 1, dropped) is True


def test_word_overlaps_dropped_segment_buiten_ankervenster() -> None:
    """Geen overlap als het weggefilterde segment buiten het ankervenster
    van het ongekoppelde woord valt."""
    from modules.pipeline import _word_overlaps_dropped_segment
    from modules.song_text import AlignedWord

    aligned = (
        AlignedWord(LyricWord(0, "mij", 0), 1.0, 1.5, "mij", 0.9),
        AlignedWord(LyricWord(1, "Espagna", 0), None, None, None, 0.0),
        AlignedWord(LyricWord(2, "zon", 0), 5.0, 5.5, "zon", 0.9),
    )
    dropped = [Segment(9, "Ver weg", 20.0, 21.0, ())]
    assert _word_overlaps_dropped_segment(aligned, 1, dropped) is False
    assert _word_overlaps_dropped_segment(aligned, 1, []) is False


def test_word_coupling_view_status_alle_categorieen(tmp_path: Path) -> None:
    """Volledige end-to-end-check van de statussen in één songtekst:
    "Geef"/"mij"/"zon" gewoon gekoppeld, "la" een overgeslagen vulwoord,
    "Espagna" verdwenen in een weggefilterde hallucinatie, en "Ole" een
    songtekstwoord waar na het laatste gekoppelde woord helemaal geen
    transcriptie meer staat.

    Dat laatste heette tot en met v0.96 "no_match". Sinds B308 heeft
    "Whisper heeft hier niets geproduceerd" een eigen status: het is een
    ander probleem met een andere oplossing dan een woord dat wél in een
    getranscribeerd stuk staat maar nergens op matcht."""
    context = _context(tmp_path)
    (context.paths.input_dir / song_text.LYRICS_FILENAME).write_text(
        "Geef la mij Espagna zon Ole\n", encoding="utf-8")

    segments = (
        Segment(0, "Geef", 0.0, 0.5, (Word("Geef", 0.0, 0.5, 0.95),)),
        Segment(1, "mij", 1.0, 1.5, (Word("mij", 1.0, 1.5, 0.95),)),
        Segment(2, "Heerlijke Heer, Heerlijke Heer.", 2.0, 4.0, (
            Word("Heerlijke", 2.00, 2.25, 0.3403),
            Word("Heer,", 2.25, 2.50, 0.4825),
            Word("Heerlijke", 2.50, 2.75, 0.7155),
            Word("Heer.", 2.75, 4.00, 0.9926),
        )),
        Segment(3, "zon", 5.0, 5.5, (Word("zon", 5.0, 5.5, 0.95),)),
    )
    save_segments(segments, pipeline.transcript_cache(context, "original"))
    context.store.set_step("whisper_original", {
        "wav_sha1": "x", "model": "large-v3", "language": "nl"})

    view = pipeline.word_coupling_view(context)
    assert view is not None
    status = {w["text"]: w["status"] for w in view["words"]}
    assert status["Geef"] == "coupled"
    assert status["mij"] == "coupled"
    assert status["zon"] == "coupled"
    assert status["la"] == "filler_skipped"
    assert status["Espagna"] == "hallucination_filtered"
    assert status["Ole"] == "transcription_gap"          # B308


def test_word_coupling_view_status_ontbreekt_niet(tmp_path: Path) -> None:
    """Elk woord krijgt altijd een status-sleutel (nooit ontbrekend), ook al
    is er verder niets bijzonders aan de hand."""
    context = _context(tmp_path)
    (context.paths.input_dir / song_text.LYRICS_FILENAME).write_text(
        "Bertus op zijn Norton\n", encoding="utf-8")
    segments = (
        Segment(0, "Bertus op zijn Norton", 0.0, 2.0, (
            Word("Bertus", 0.0, 0.5, 0.9), Word("op", 0.5, 1.0, 0.9),
            Word("zijn", 1.0, 1.5, 0.9), Word("Norton", 1.5, 2.0, 0.9),
        )),
    )
    save_segments(segments, pipeline.transcript_cache(context, "original"))
    context.store.set_step("whisper_original", {
        "wav_sha1": "x", "model": "large-v3", "language": "nl"})

    view = pipeline.word_coupling_view(context)
    assert view is not None
    assert all("status" in w for w in view["words"])
    assert all(w["status"] == "coupled" for w in view["words"])


# --------------------------------------------------------------------------
# B287 (3, GUI): drie visueel verschillende markeringen in de koppel-editor
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_status_style_drie_categorieen() -> None:
    """Elke status heeft een eigen kleurenpaar en een eigen legenda-tekst.

    "coupled" (of een onbekende/ontbrekende status) staat er bewust niet
    in - dat gebruikt de normale opmaak zonder markering. Sinds B308 is
    "transcription_gap" erbij gekomen en sinds B313 "energy_placed".
    Sinds B317 staat er geen label meer VOOR het woord: het derde veld is
    de sleutel van de legenda-tekst, want een code in het vakje maakte
    het woord slechter leesbaar en zei zonder uitleg niets."""
    from modules import translations
    from modules.coupling_editor import _STATUS_STYLE

    assert set(_STATUS_STYLE) == {
        "filler_skipped", "no_match", "hallucination_filtered",
        "transcription_gap", "energy_placed",
        "suspect_run",                          # B502
        "manually_uncoupled",                   # B506
        "background",                           # B507
        "repeat_missing"}                       # B521
    sleutels = [key for _f, _b, key in _STATUS_STYLE.values()]
    assert len(set(sleutels)) == len(sleutels)   # elke status eigen tekst
    kleuren = [(fill.name(), border.name())
               for fill, border, _k in _STATUS_STYLE.values()]
    assert len(set(kleuren)) == len(kleuren)     # elke markering eigen kleur
    for fill, border, key in _STATUS_STYLE.values():
        assert fill != border
        # De legenda-tekst moet in beide talen bestaan, anders staat er
        # straks een sleutelnaam in beeld.
        for taal in ("nl", "en"):
            assert key in translations.TRANSLATIONS[taal], f"{taal}/{key}"


def test_koppel_canvas_paint_met_statusmarkeringen(qapp) -> None:
    """Regressie: de drie statusmarkeringen (plus een woord zonder status)
    mogen niet crashen tijdens het tekenen."""
    from PySide6.QtGui import QImage, QPainter

    from modules.coupling_editor import CouplingCanvas

    transcript = [("GEEF", 0.0, 0.5), ("MIJ", 1.0, 1.5)]
    words = [
        {"index": 0, "text": "Geef", "line": 0, "transcript_indices": [0],
         "found": "GEEF", "sim": 0.9, "pinned": False,
         "status": "coupled"},
        {"index": 1, "text": "la", "line": 0, "transcript_indices": [],
         "found": None, "sim": 0.0, "pinned": False,
         "status": "filler_skipped"},
        {"index": 2, "text": "Espagna", "line": 0, "transcript_indices": [],
         "found": None, "sim": 0.0, "pinned": False,
         "status": "hallucination_filtered"},
        {"index": 3, "text": "Ole", "line": 0, "transcript_indices": [],
         "found": None, "sim": 0.0, "pinned": False,
         "status": "no_match"},
    ]
    canvas = CouplingCanvas(transcript, words, lambda p: None)
    canvas.resize(600, 220)

    image = QImage(600, 220, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    canvas._paint(painter)
    painter.end()


def test_koppel_canvas_zonder_status_valt_terug_op_gekoppeld(qapp) -> None:
    """Woorden zonder ``status``-sleutel (bv. na een knip/samenvoeg-
    bewerking, die de dict opnieuw opbouwt zonder dit veld) crashen niet en
    krijgen gewoon de normale (ongemarkeerde) opmaak."""
    from PySide6.QtGui import QImage, QPainter

    from modules.coupling_editor import CouplingCanvas

    transcript = [("HARD", 0.0, 1.0)]
    words = [
        {"index": 0, "text": "hard", "line": 0, "transcript_indices": [],
         "found": None, "sim": 0.0, "pinned": False},   # geen "status"
    ]
    canvas = CouplingCanvas(transcript, words, lambda p: None)
    canvas.resize(300, 220)
    image = QImage(300, 220, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    canvas._paint(painter)
    painter.end()
