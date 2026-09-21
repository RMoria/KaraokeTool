"""Tests for v0.94 (B285/B286/B287).

Three connected improvements to the word coupling, prompted by a real
"Lied_S" alignment that fell apart towards the end:

1. **B285** - song-wide hallucination check in
   ``pipeline._filter_hallucinations``: even when a word is not on the
   fixed hallucination list, a segment is dropped when none of its core
   words matches the lyrics even roughly AND Whisper's own lowest word
   confidence is low (reproduces the "Heerlijke Heer, Heerlijke Heer."
   hallucination after a long silence in the transcription).
2. **B286** - ``song_text.is_repeated_filler_line``/``repeated_filler_lines``:
   a lyrics line that deliberately consists of repeated filler sounds
   (say "La la la la") is not skipped as an incidental filler word.
3. **B287** - status marks in the coupling editor
   (``pipeline.word_coupling_view`` and ``modules.coupling_editor``):
   every uncoupled lyrics word gets one of three visually distinct marks
   ("filler_skipped", "no_match", "hallucination_filtered"), so the user
   sees whether (and why) he has to couple it himself.
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
# B285 (1): song-wide hallucination check in _filter_hallucinations
# --------------------------------------------------------------------------

def test_filter_hallucinations_broad_check_drops_heerlijke_heer() -> None:
    """Reproduction of the Lied_S bug: after a long silence in the
    transcription Whisper hallucinates "Heerlijke Heer, Heerlijke Heer.",
    with an inconsistent word confidence (0.34/0.48/0.72/0.99, the real
    figures from the project) and not one lyrics match. The song-wide
    check now has to drop this segment as well, even though none of its
    words is on the fixed hallucination list."""
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
    """Without lyrics (``lyrics=None``) the song-wide check is skipped
    altogether - there is then nothing to hold "matches nothing" against,
    and the check would fire far too easily."""
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
    """A segment that Whisper transcribed with high confidence on every
    word stays, even when it happens not to match the lyrics - that can be
    an ad-lib rather than a hallucination."""
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
    """When at least one core word matches the lyrics reasonably, the whole
    segment stays - even with a low Whisper confidence on the rest. One
    real word between noise is enough to spare the segment."""
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


def test_filter_hallucinations_broad_check_needs_min_core_words() -> None:
    """Below ``_SEGMENT_HALLUCINATION_MIN_CORE_WORDS`` core words the
    song-wide check is skipped - too little phonetic material to establish
    "belongs nowhere" reliably."""
    segs = (Segment(0, "Xyzzy", 10.0, 10.5, (Word("Xyzzy", 10.0, 10.5, 0.2),)),)
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "Geef mij maar alle dagen zon".split()))
    kept = pipeline._filter_hallucinations(segs, lyrics)
    assert len(kept) == 1


def test_best_lyrics_match_ignores_degenerate_short_keys() -> None:
    """'heer' phonetises (h/r drop out, ``cluster._DROPPED``) down to the
    single character 'e' - by chance the same key as the small lyrics word
    'E' (from "E viva Espagna"). Without a lower bound such a one-character
    key would give a false match of 1.0 and make the whole song-wide check
    useless; ``_best_lyrics_match`` has to ignore keys that short."""
    from modules import cluster

    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "E viva Espagna".split()))
    lyric_keys = frozenset(cluster.phonetic_key(w.text) for w in lyrics)
    assert cluster.phonetic_key("heer") == "e"     # the test's premise
    assert pipeline._best_lyrics_match("heer", lyric_keys) == 0.0


def test_filter_hallucinations_dropped_out_stays_compatible() -> None:
    """The optional ``dropped_out`` argument collects the discarded
    segments without changing the return value - every existing call
    (without this argument) keeps working exactly as before."""
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
# B286 (2): repeated filler sounds as deliberate lyrics
# --------------------------------------------------------------------------

def test_is_repeated_filler_line_spots_a_repetition() -> None:
    assert song_text.is_repeated_filler_line(["la", "la", "la", "la"]) is True
    assert song_text.is_repeated_filler_line(["la", "la", "la"]) is True  # just enough


def test_is_repeated_filler_line_false_for_short_or_real() -> None:
    assert song_text.is_repeated_filler_line(["oh", "ja"]) is False   # too short
    assert song_text.is_repeated_filler_line(
        ["la", "la", "hallo"]) is False                              # no filler word


def test_repeated_filler_lines_groups_per_line() -> None:
    lyrics = (
        LyricWord(0, "Dit", 0), LyricWord(1, "is", 0), LyricWord(2, "text", 0),
        LyricWord(3, "la", 1), LyricWord(4, "la", 1),
        LyricWord(5, "la", 1), LyricWord(6, "la", 1),
    )
    assert song_text.repeated_filler_lines(lyrics) == frozenset({1})


def test_align_lyrics_repeated_filler_line_is_not_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A lyrics line that deliberately consists of repeated filler sounds
    ("la la la la" as one line) does not count as "filler to skip":
    ``align_lyrics`` then treats it exactly like ``skip_filler=False`` (no
    word reaches the skip set through ``repeated_filler_lines``, so the
    function goes straight to the ordinary DP alignment, without a
    skipped-words log line). Four SEPARATE filler lines (one word each, so
    no repetition within a line) are skipped, for comparison."""
    segments = (
        Segment(0, "la la la la", 10.0, 12.0, (
            Word("la", 10.0, 10.5, 0.9), Word("la", 10.5, 11.0, 0.9),
            Word("la", 11.0, 11.5, 0.9), Word("la", 11.5, 12.0, 0.9),
        )),
    )
    repeated = tuple(LyricWord(i, "la", 0) for i in range(4))    # 1 line
    separate = tuple(LyricWord(i, "la", i) for i in range(4))    # 4 lines

    with caplog.at_level(logging.INFO, logger="modules.song_text"):
        caplog.clear()
        with_skip = align_lyrics(repeated, segments, skip_filler=True)
        assert not any("overgeslagen" in r.message for r in caplog.records)
    without_skip = align_lyrics(repeated, segments, skip_filler=False)
    assert with_skip == without_skip

    with caplog.at_level(logging.INFO, logger="modules.song_text"):
        caplog.clear()
        align_lyrics(separate, segments, skip_filler=True)
        assert any("4 woord(en) overgeslagen" in r.message
                  for r in caplog.records)


# --------------------------------------------------------------------------
# B287 (3): status marks in the coupling editor
# --------------------------------------------------------------------------

def test_word_overlaps_dropped_segment_inside_anchor_window() -> None:
    """An uncoupled word between two coupled neighbours, with a
    filtered-out hallucination segment falling in between, counts as
    'overlapping'."""
    from modules.pipeline import _word_overlaps_dropped_segment
    from modules.song_text import AlignedWord

    aligned = (
        AlignedWord(LyricWord(0, "mij", 0), 1.0, 1.5, "mij", 0.9),
        AlignedWord(LyricWord(1, "Espagna", 0), None, None, None, 0.0),
        AlignedWord(LyricWord(2, "zon", 0), 5.0, 5.5, "zon", 0.9),
    )
    dropped = [Segment(9, "Heerlijke Heer", 2.0, 4.0, ())]
    assert _word_overlaps_dropped_segment(aligned, 1, dropped) is True


def test_word_overlaps_dropped_segment_outside_anchor_window() -> None:
    """No overlap when the filtered-out segment falls outside the anchor
    window of the uncoupled word."""
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


def test_word_coupling_view_status_all_categories(tmp_path: Path) -> None:
    """Full end-to-end check of the statuses in one set of lyrics:
    "Geef"/"mij"/"zon" plainly coupled, "la" a skipped filler word,
    "Espagna" lost in a filtered-out hallucination, and "Ole" a lyrics word
    with no transcription at all after the last coupled word.

    That last one was called "no_match" up to and including v0.96. Since
    B308 "Whisper produced nothing here" has a status of its own: it is a
    different problem with a different fix than a word that does sit in a
    transcribed stretch but matches nothing there."""
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


def test_word_coupling_view_status_is_never_missing(tmp_path: Path) -> None:
    """Every word always gets a status key (never missing), even when
    there is nothing special about it."""
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
# B287 (3, GUI): three visually distinct marks in the coupling editor
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_status_style_three_categories() -> None:
    """Every status has its own colour pair and its own legend text.

    "coupled" (or an unknown/missing status) is deliberately not in it -
    that uses the normal formatting, without a mark. Since B308
    "transcription_gap" has been added, and since B313 "energy_placed".
    Since B317 there is no label BEFORE the word any more: the third field
    is the key of the legend text, because a code in the box made the word
    harder to read and said nothing without an explanation."""
    from modules import translations
    from modules.coupling_editor import _STATUS_STYLE

    assert set(_STATUS_STYLE) == {
        "filler_skipped", "no_match", "hallucination_filtered",
        "transcription_gap", "energy_placed",
        "suspect_run",                          # B502
        "manually_uncoupled",                   # B506
        "background",                           # B507
        "repeat_missing"}                       # B521
    keys = [key for _f, _b, key in _STATUS_STYLE.values()]
    assert len(set(keys)) == len(keys)           # each status its own text
    colors = [(fill.name(), border.name())
              for fill, border, _k in _STATUS_STYLE.values()]
    assert len(set(colors)) == len(colors)       # each mark its own colour
    for fill, border, key in _STATUS_STYLE.values():
        assert fill != border
        # The legend text has to exist in both languages, or a key name
        # ends up on screen.
        for language in ("nl", "en"):
            assert key in translations.TRANSLATIONS[language], \
                f"{language}/{key}"


def test_coupling_canvas_paint_with_status_marks(qapp) -> None:
    """Regression: the three status marks (plus a word without a status)
    must not crash while being drawn."""
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


def test_coupling_canvas_without_status_falls_back_to_coupled(qapp) -> None:
    """Words without a ``status`` key (say after a split/merge edit, which
    rebuilds the dict without this field) do not crash and get the normal
    (unmarked) formatting."""
    from PySide6.QtGui import QImage, QPainter

    from modules.coupling_editor import CouplingCanvas

    transcript = [("HARD", 0.0, 1.0)]
    words = [
        {"index": 0, "text": "hard", "line": 0, "transcript_indices": [],
         "found": None, "sim": 0.0, "pinned": False},   # no "status"
    ]
    canvas = CouplingCanvas(transcript, words, lambda p: None)
    canvas.resize(300, 220)
    image = QImage(300, 220, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    canvas._paint(painter)
    painter.end()
