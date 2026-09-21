"""Tests for v0.100.0: B316 up to and including B322.

B316 - the initial prompt is a hint, not a source: a lyrics override
       must not throw the transcription away.
B317 - the markings belong in a legend, not in front of the word.
B318 - the sung time is divided weighted by syllables.
B319 - the end of the singing is an anchor: nothing runs past it, and
       the tail is fitted from the back forwards.
B320 - uncoupled words stay above each other.
B321 - a click yields the word it points at.
B322 - the window starts big enough for its own content.
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
# B316: what a source change must precisely NOT cost
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source,spared", [
    # The lyrics travel to Whisper as the initial prompt, but a
    # correction to the word list in the coupling editor is no reason to
    # throw away a transcription that took two and a half minutes of
    # computing.
    ("lyrics_override", "whisper_original"),
    ("lyrics_override", "cache:transcription_original"),
    ("lyrics_override", "analysis_original"),
    ("transcript_override", "whisper_original"),
    ("word_coupling", "whisper_original"),
])
def test_a_source_change_spares_the_transcription(source: str,
                                                  spared: str) -> None:
    assert spared not in deps.dependents([source])


def test_replacing_the_lyrics_file_does_hit_the_transcription() -> None:
    """The other side: replacing the FILE is a real text change, and
    then a new transcription is in order."""
    assert "whisper_original" in deps.dependents(["input:lyrics"])


def test_an_override_hits_everything_counting_on_the_word_list() -> None:
    """Splitting or merging renumbers the lyric words, so everything
    that counts on those positions does lapse."""
    affected = deps.dependents(["lyrics_override"])
    for name in ("word_coupling", "original_overrides", "stress_anchors",
                 "coupling", "timing"):
        assert name in affected, name


# --------------------------------------------------------------------------
# B318: weighing by syllables
# --------------------------------------------------------------------------

def test_the_split_weighs_syllables() -> None:
    """"Espagna" (three syllables) should get more time than "e"."""
    even = timing_module.spread_over_active(3, [(0.0, 6.0)])
    weighted = timing_module.spread_over_active(3, [(0.0, 6.0)],
                                                weights=[1, 3, 2])
    assert [round(e - s, 2) for s, e in even] == [2.0, 2.0, 2.0]
    assert [round(e - s, 2) for s, e in weighted] == [1.0, 3.0, 2.0]


def test_the_split_without_weights_stays_the_same() -> None:
    """Without weights (or with the wrong number of them) nothing about
    the old behaviour changes."""
    without = timing_module.spread_over_active(4, [(0.0, 8.0)])
    wrong_count = timing_module.spread_over_active(4, [(0.0, 8.0)],
                                                   weights=[1, 2])
    assert without == wrong_count


def test_the_split_fills_the_window_exactly() -> None:
    """Weighted or not: together the slots cover the whole window, with
    no gap and no overlap."""
    slots = timing_module.spread_over_active(5, [(10.0, 20.0)],
                                             weights=[1, 4, 2, 1, 2])
    assert round(slots[0][0], 3) == 10.0
    assert round(slots[-1][1], 3) == 20.0
    for left, right in zip(slots, slots[1:]):
        assert round(left[1], 3) == round(right[0], 3)


# --------------------------------------------------------------------------
# B319: the end of the singing as an anchor
# --------------------------------------------------------------------------

def _words(spec):
    out = []
    for index, (text, start, sim) in enumerate(spec):
        out.append(AlignedWord(
            LyricWord(index=index, text=text, line=index // 4),
            start, None if start is None else start + 0.3,
            text if start is not None else None, sim))
    return tuple(out)


def test_a_coupling_after_the_end_of_the_singing_is_dropped() -> None:
    """After the last singing Whisper sometimes still writes something
    down (applause, a fade-out, a hallucination). A lyric word hanging
    on that sits past the end of the song and skews everything before
    it."""
    aligned = _words([("een", 1.0, 1.0), ("twee", 2.0, 1.0),
                      ("drie", 40.0, 1.0)])
    out = pipeline._drop_couplings_after(aligned, song_end=30.0)
    assert out[0].start == 1.0 and out[1].start == 2.0
    assert out[2].start is None and out[2].matched_text is None


def test_a_coupling_just_before_the_end_stays() -> None:
    aligned = _words([("een", 29.9, 1.0)])
    assert pipeline._drop_couplings_after(aligned, 30.0)[0].start == 29.9


def test_the_tail_is_fitted_from_the_back_forwards() -> None:
    """A run at the end has no anchor behind it, so the window reaches
    to wherever the singing stops. If that offers far more time than the
    words need, counting back from the end is the better fit - that is
    where the certainty lies."""
    windows = [(0.0, 10.0), (20.0, 30.0)]
    fitted = pipeline._fit_from_the_back(windows, needed=4.0)
    assert fitted == [(26.0, 30.0)]


def test_fitting_from_the_back_takes_more_windows_if_it_must() -> None:
    windows = [(0.0, 10.0), (20.0, 24.0)]
    fitted = pipeline._fit_from_the_back(windows, needed=6.0)
    assert fitted == [(8.0, 10.0), (20.0, 24.0)]


def test_fitting_from_the_back_leaves_a_tight_fit_alone() -> None:
    """If it only just fits, or does not fit at all, nothing changes."""
    windows = [(0.0, 4.0)]
    assert pipeline._fit_from_the_back(windows, needed=10.0) == windows


def test_syllable_duration_is_measured_on_the_song_itself() -> None:
    """The duration of a syllable follows the tempo of this song,
    measured on the well-coupled words."""
    aligned = tuple(
        AlignedWord(LyricWord(i, "la", 0), float(i), float(i) + 0.5,
                    "la", 1.0)
        for i in range(6))
    assert 0.4 <= pipeline._seconds_per_syllable(aligned) <= 0.6


def test_syllable_duration_falls_back_without_measurements() -> None:
    aligned = _words([("een", None, 0.0)])
    assert pipeline._seconds_per_syllable(aligned) == \
        pipeline._DEFAULT_SECONDS_PER_SYLLABLE


def test_the_end_of_the_singing_is_in_the_chain() -> None:
    """The end derives from the vocal track just as much as the start
    does; without a place in the chain it would survive a new source
    change."""
    assert "vocal_end_s" in deps.ARTEFACTS
    assert deps.ARTEFACTS["vocal_end_s"].sources == ("cache:demucs_original",)
    assert "vocal_end_s" in deps.dependents(["input:original"])


# --------------------------------------------------------------------------
# B320/B321: the coupling editor
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _canvas(trans, couplings):
    """Canvas with ``couplings`` = the transcript indices per lyric word."""
    from modules.coupling_editor import CouplingCanvas

    words = [{"index": i, "text": f"L{i}", "transcript_indices": list(t),
              "pinned": False, "sim": 1.0 if t else 0.0, "line": 0}
             for i, t in enumerate(couplings)]
    return CouplingCanvas([(w, i * 1.0, i * 1.0 + 0.5)
                         for i, w in enumerate(trans)],
                        words, lambda *_a: None)


def test_uncoupled_words_stay_above_each_other(qapp) -> None:
    """Over a long uncoupled stretch the two rows drifted a column apart
    per word: eight words was a shift of 720 pixels."""
    trans = [f"T{i}" for i in range(10)]
    couplings = [[0]] + [[] for _ in range(8)] + [[9]]
    canvas = _canvas(trans, couplings)
    assert canvas._top_col == canvas._bot_col
    assert canvas._cols == 10


def test_coupled_pairs_stay_above_each_other(qapp) -> None:
    """What was already right (B220) has to stay that way."""
    canvas = _canvas(["T0", "T1", "T2"], [[0], [1], [2]])
    assert canvas._top_col == canvas._bot_col == [0, 1, 2]


def test_a_click_lands_on_the_word_it_points_at(qapp) -> None:
    """A coupling is stretched automatically onto adjacent found words
    (B191), and that group was drawn as one wide box. Every click inside
    it returned the FIRST word of the group, so a coupling landed on the
    word to the left of your pointer."""
    from PySide6.QtCore import QPoint

    from modules.coupling_editor import _PATH, _PPW, _TOP_Y

    canvas = _canvas(["formi", "dable", "nous"], [[0, 1], []])
    for index in range(3):
        x = _PATH + canvas._top_col[index] * _PPW + 20
        assert canvas._hit_row(QPoint(x, _TOP_Y + 5), top=True) == index


def test_the_legend_describes_every_marking(qapp) -> None:
    """The legend is built from the same table that is drawn from, so a
    new marking cannot appear on screen without an explanation."""
    from modules import translations
    from modules.coupling_editor import _STATUS_STYLE, legend_html

    html = legend_html()
    for fill, _border, key in _STATUS_STYLE.values():
        assert fill.name() in html
        assert translations.t(key) in html


def test_no_marking_in_front_of_the_word_any_more(qapp) -> None:
    """The codes ``[vul]``/``[hal]``/``[zang]`` sat in front of the word
    and made it harder to read; they belong in the legend.

    Checked structurally rather than on text: the third field of the
    style table is now a translation key, not a label that gets glued in
    front of the word."""
    from modules import translations
    from modules.coupling_editor import _STATUS_STYLE

    for _fill, _border, third in _STATUS_STYLE.values():
        assert third.startswith("legend_"), third
        assert not third.strip().startswith("["), third
        assert third in translations.TRANSLATIONS["nl"]


# --------------------------------------------------------------------------
# B322: the startup height
# --------------------------------------------------------------------------

def test_the_window_starts_big_enough_for_its_content(qapp, tmp_path) -> None:
    """The window minimum sits deliberately below what the layout needs,
    so that shrinking is allowed. That let the window start at a size
    where the group boxes drew their text on top of each other."""
    from modules import gui
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    window = gui.MainWindow(context)
    needed = window.centralWidget().layout().minimumSize()
    screen = window.screen()
    room = screen.availableGeometry() if screen is not None else None

    # Big enough, or else bounded by what the screen offers.
    if room is None or room.height() >= needed.height():
        assert window.height() >= needed.height()
    else:
        assert window.height() >= room.height() - 1
    assert window.width() >= min(needed.width(),
                                 room.width() if room else needed.width())


def test_shrinking_stays_allowed(qapp, tmp_path) -> None:
    """Afterwards the user may make the window as small as he likes."""
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
# Coherence: the placement keeps doing what B313 promised
# --------------------------------------------------------------------------

def test_placement_stays_orderly_with_weights_and_the_end(
        monkeypatch) -> None:
    """With weighing and the end anchor added it still holds: the order
    is intact, good couplings are untouched, nothing past the end."""
    from modules import rhythm

    aligned = _words([("start", 1.0, 1.0)]
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
    out = pipeline._place_skipped_on_energy(context, aligned)
    times = [w.start for w in out if w.start is not None]
    assert times == sorted(times)
    assert out[0].start == 1.0 and not out[0].estimated
    assert out[-1].start == 20.0 and not out[-1].estimated
    assert all(w.end <= 25.1 for w in out if w.end is not None)
