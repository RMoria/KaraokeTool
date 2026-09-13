"""Tests for v0.140.0: B458 to B463.

Two of these are my own mistakes from v0.139.0, and both were invisible
in exactly the same way: a guard that was too wide, and a test that used
material which could not expose it. The hallucination filter let the
karaoke text count towards the general match floor and 0.56 s of timing
walked out; the loudness check demanded a negative loudness range, which
does not exist, so the normalisation quietly did nothing at all.
"""
from __future__ import annotations

import inspect
import pathlib
import tempfile

import numpy
import pytest
import soundfile

from modules import ffmpeg, pipeline


def _wav(signal, rate: int = 44100) -> pathlib.Path:
    folder = pathlib.Path(tempfile.mkdtemp())
    path = folder / "proef.wav"
    soundfile.write(path, numpy.asarray(signal, dtype="float32"), rate)
    return path


# --------------------------------------------------------------------------
# B458 - the chant loose from the match floor
# --------------------------------------------------------------------------

def test_the_karaoke_text_no_longer_widens_the_match_floor() -> None:
    """That is what cost the 0.56 s: the parody has other words, so
    almost any invented segment found something above 0.65 somewhere and
    stayed. Measured, switching this filter off went from costing 0.07 s
    to being worth 0.49 s."""
    source = inspect.getsource(pipeline._filter_hallucinations)
    assert "chant_keys = frozenset(extra_keys or ())" in source
    # The general match runs against the lyrics alone.
    assert "_best_lyrics_match(w, lyric_keys)" in source
    assert "_best_lyrics_match(w, chant_keys)" not in source


def test_the_second_text_still_serves_the_chant() -> None:
    """The original may sing "na-na-na" where the karaoke text writes
    "la-la-la"; either spelling makes it a chant."""
    for name in ("_filter_hallucinations",
                 "_filter_hallucinations_in_position"):
        source = inspect.getsource(getattr(pipeline, name))
        assert "chant_keys" in source, name
        assert "_is_chant(core_words)" in source, name


def test_a_chant_of_something_sung_nowhere_stays_suspect() -> None:
    """Too mild beats too strict for a guard, but not without limit."""
    source = inspect.getsource(pipeline._filter_hallucinations)
    assert "_word_in_lyrics(w, chant_keys) for w in core_words" in source


# --------------------------------------------------------------------------
# B459 - the loudness check, with the ranges that really exist
# --------------------------------------------------------------------------

def test_music_with_dynamics_gives_a_measurement() -> None:
    """THE test that was missing. The old check demanded -99..0 for the
    loudness range, and that one is positive by definition - so every
    piece of music with any dynamic at all was rejected, and both the
    normalisation and the whole of 1.5.11e silently did nothing."""
    moment = numpy.linspace(0, 8, 44100 * 8, endpoint=False)
    quiet_and_loud = (numpy.where((moment % 4) < 2, 0.05, 0.4)
                      * numpy.sin(2 * numpy.pi * 300 * moment))
    measured = ffmpeg.measure_loudness(_wav(quiet_and_loud))
    assert measured is not None
    assert measured.lra > 0, "juist dit getal is positief"
    assert -99.0 <= measured.integrated <= 0.0


def test_a_pure_sine_was_the_one_signal_that_slipped_through() -> None:
    """Recorded so nobody tests with it again: a sine has a loudness
    range of exactly 0.0, and that is the only value the old check let
    pass."""
    moment = numpy.linspace(0, 5, 44100 * 5, endpoint=False)
    measured = ffmpeg.measure_loudness(
        _wav(0.2 * numpy.sin(2 * numpy.pi * 300 * moment)))
    assert measured is not None
    assert measured.lra == 0.0


def test_silence_still_gives_nothing() -> None:
    assert ffmpeg.measure_loudness(_wav(numpy.zeros(44100 * 2))) is None


def test_a_true_peak_just_above_zero_is_allowed() -> None:
    """Measured on the user's own material: "Lied M" peaks at
    +0.12 dBTP, and that is a perfectly ordinary track."""
    assert ffmpeg._TP_RANGE[1] > 0
    assert ffmpeg._LRA_RANGE[1] > 0
    assert ffmpeg._I_RANGE == (-99.0, 0.0)


def test_the_video_really_comes_out_at_the_target() -> None:
    """End to end, on material with dynamics - the shape that was broken."""
    import subprocess

    from PIL import Image

    from modules import timing, video

    folder = pathlib.Path(tempfile.mkdtemp())
    rate = 44100
    moment = numpy.linspace(0, 8, rate * 8, endpoint=False)
    signal = (numpy.where((moment % 3) < 1.5, 0.03, 0.25)
              * numpy.sin(2 * numpy.pi * 300 * moment)).astype("float32")
    audio = folder / "karaoke.wav"
    soundfile.write(audio, signal, rate)
    logo = folder / "logo.png"
    Image.new("RGB", (120, 80)).save(logo)
    target = folder / "proef.mp4"
    lines = timing.mark_held(
        [timing.timedline_from_text(0, "zing mee", 1.0, 5.0)])
    video.render_video(lines, audio, logo, "Proef", target,
                       width=320, height=180, fps=50, loudness_lufs=-16.0)
    report = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(target),
         "-af", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    measured = [line for line in report.splitlines()
                if line.strip().startswith("I:")]
    value = float(measured[-1].split()[1])
    assert -17.0 < value < -15.0, measured[-1]


# --------------------------------------------------------------------------
# B460 - 1.5.11e over the lanes instead of on one
# --------------------------------------------------------------------------

def test_the_gain_trial_uses_the_whisper_lanes() -> None:
    """The user saw one Whisper process where the rule has said two
    since B396 - half the machine standing still for an hour."""
    from modules import test_panel

    source = inspect.getsource(test_panel._gain_trial)
    assert "measure_pool.whisper_lanes()" in source
    assert "threading.Thread(target=worker" in source


def test_every_run_goes_into_one_queue_longest_first() -> None:
    from modules import test_panel

    source = inspect.getsource(test_panel._gain_trial)
    assert 'sorted(prepared, key=lambda job: -job["seconds"])' in source


def test_the_conversions_happen_before_the_lanes_start() -> None:
    """ffmpeg work up front keeps the lanes busy with nothing but
    transcribing."""
    from modules import test_panel

    source = inspect.getsource(test_panel._gain_trial)
    assert source.index("_at_level(") < source.index("def worker")


# --------------------------------------------------------------------------
# B461 - the letters and the number agree
# --------------------------------------------------------------------------

@pytest.fixture()
def panel(qapp_offscreen):
    from modules import test_panel

    return test_panel.TestPanel(None)


@pytest.fixture(scope="module")
def qapp_offscreen():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _heavy_tick(panel):
    return next(tick for tick, action in zip(panel._ticks, panel._actions)
                if action.heavy)


def test_the_letters_open_the_way_the_number_opens(panel) -> None:
    """They used to open TICKED while 1.5.11 was not, so the panel showed
    "a, b, e chosen" and meant "nothing chosen"."""
    assert not _heavy_tick(panel).isChecked()
    assert not any(box.isChecked() for box, _trial in panel._letters)


def test_ticking_a_letter_starts_the_number(panel) -> None:
    """The exact case the user reported: a and e ticked, b not, and
    pressing start did nothing at all."""
    # B491: 1.5.11e staat inmiddels uit, dus die staat niet meer in de
    # lijst met letters; het gedrag dat deze test vastlegt is dat een
    # aangevinkte letter het nummer meeneemt.
    aan = [trial.code for box, trial in panel._letters
           if trial.code in ("1.5.11a", "1.5.11b")]
    for box, trial in panel._letters:
        if trial.code in aan:
            box.setChecked(True)
    assert _heavy_tick(panel).isChecked()
    assert panel.heavy_choice() == aan
    assert [action.code for action in panel.chosen()] == ["1.5.11"]


def test_the_number_still_pulls_all_its_letters_along(panel) -> None:
    _heavy_tick(panel).setChecked(True)
    on = {trial.code for box, trial in panel._letters if box.isChecked()}
    assert on == {trial.code for _b, trial in panel._letters
                  if not trial.off}


def test_the_last_letter_off_switches_the_number_off(panel) -> None:
    _heavy_tick(panel).setChecked(True)
    for box, trial in panel._letters:
        if not trial.off:
            box.setChecked(False)
    assert not _heavy_tick(panel).isChecked()
    assert [action.code for action in panel.chosen()] == []


def test_the_two_ticks_do_not_wake_each_other_up(panel) -> None:
    """Without the lock the number sets the letters and the letters set
    the number, round and round."""
    for _ in range(20):
        _heavy_tick(panel).setChecked(True)
        _heavy_tick(panel).setChecked(False)
    assert not _heavy_tick(panel).isChecked()


# --------------------------------------------------------------------------
# B462/B463 - what falls outside the measurement, and putting it back
# --------------------------------------------------------------------------

def _project(tmp_path, song: str, hand: bool, auto: bool):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=song)
    ensure_directories(paths)
    store = ProjectStore(paths.project_file)
    store.set_step("whisper_original", {"segments": 1})
    store.save()
    if hand:
        paths.timing_file.write_text("[]", encoding="utf-8")
    if auto:
        paths.timing_auto_file.write_text("[]", encoding="utf-8")
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=store)


def test_a_project_without_an_auto_file_is_named_not_counted(
        tmp_path) -> None:
    """It counted towards "measured on 16 projects" while contributing
    nothing - the quiet miscounting this function claims to have solved
    for the search, one level down."""
    from modules import test_panel

    context = _project(tmp_path, "MetBeide", hand=True, auto=True)
    _project(tmp_path, "ZonderAuto", hand=True, auto=False)
    _project(tmp_path, "ZonderAlles", hand=False, auto=False)
    measurable, skipped = test_panel._measurable_split(context)
    assert [song for song, _why in measurable] == ["MetBeide"]
    assert [song for song, _why in skipped] == ["ZonderAuto"]
    note = "\n".join(test_panel._skipped_projects_note(context))
    assert "ZonderAuto" in note
    assert "ZonderAlles" not in note, "niets getimed is geen probleem"


def test_no_missing_file_no_note(tmp_path) -> None:
    from modules import test_panel

    context = _project(tmp_path, "MetBeide", hand=True, auto=True)
    assert test_panel._skipped_projects_note(context) == []


def test_rebuilding_never_touches_the_hand_timing() -> None:
    """That file IS handwork; the automatic one is only what the
    coupling produces."""
    source = inspect.getsource(pipeline.rebuild_auto_timing)
    assert "timing_file" in source          # only read, for the line count
    assert "save_timing(" in source
    assert source.count("timing_auto_file") >= 1
    saving = source[source.index("save_timing("):]
    assert "timing_auto_file" not in saving or "target" in saving


def test_an_existing_auto_file_is_left_alone(tmp_path) -> None:
    context = _project(tmp_path, "Proef", hand=True, auto=True)
    before = context.paths.timing_auto_file.read_text(encoding="utf-8")
    assert pipeline.rebuild_auto_timing(context) is None
    assert context.paths.timing_auto_file.read_text(encoding="utf-8") \
        == before


def test_without_hand_timing_there_is_nothing_to_rebuild(tmp_path) -> None:
    context = _project(tmp_path, "Proef", hand=False, auto=False)
    assert pipeline.rebuild_auto_timing(context) is None


def test_the_preparation_action_does_the_rebuilding() -> None:
    """1.5.1 is the step that makes what the measurement needs but does
    not have, so this is where it belongs."""
    from modules import test_panel

    source = inspect.getsource(test_panel.fill_cache)
    assert "rebuild_auto_timing(other)" in source
    assert "_measurable_split(context)" in source
