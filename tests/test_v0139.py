"""Tests for v0.139.0: B447 to B457.

Three things the user could see and did not like, and three he asked
for. The colouring jumped per piece; the underline under a held piece
was one sign too many in the video; the twenty-version brake held back
exactly the trial that had to run. And underneath: the stress editor
rebuilt around the recording instead of around a spelling rule, the
la-la-la that was being deleted as a hallucination, and one level for
every video.
"""
from __future__ import annotations

import inspect

import pytest

from modules import pipeline, timing, video


# --------------------------------------------------------------------------
# B447 - the colour sweeps instead of flipping
# --------------------------------------------------------------------------

def test_a_piece_is_part_sung_while_it_runs() -> None:
    from modules.timing import Syllable

    piece = Syllable("aa", 2.0, 4.0)
    assert video._sung_share(piece, 1.0) == 0.0
    assert video._sung_share(piece, 3.0) == pytest.approx(0.5)
    assert video._sung_share(piece, 9.0) == 1.0


def test_a_piece_without_length_is_simply_done() -> None:
    """Never divide by zero in a render loop."""
    from modules.timing import Syllable

    assert video._sung_share(Syllable("a", 2.0, 2.0), 2.5) == 1.0


def test_the_colour_no_longer_flips_per_piece() -> None:
    """The regression the user reported: a held vowel stood still for two
    seconds and then jumped over in one frame."""
    source = inspect.getsource(video._draw_line)
    assert "_sung_share(syllable, moment)" in source
    assert "_draw_swept(" in source


def test_only_the_piece_on_the_boundary_costs_extra(tmp_path) -> None:
    """A whole share of 0 or 1 - so every other piece on screen - takes
    the plain single draw."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default()
    drawn = []

    class Counting(ImageDraw.ImageDraw):
        def text(self, *args, **kw):
            drawn.append(1)
            return super().text(*args, **kw)

    image = Image.new("RGB", (200, 60))
    video._draw_swept(image, Counting(image), 5, 5, "aa", font,
                      (0, 255, 0), (255, 255, 255), 0.0)
    assert len(drawn) == 1
    drawn.clear()
    video._draw_swept(image, Counting(image), 5, 5, "aa", font,
                      (0, 255, 0), (255, 255, 255), 0.5)
    assert len(drawn) == 2


def test_the_sweep_really_gives_two_colours() -> None:
    """Left of the sweep green, right of it white - on one and the same
    piece, so a wide letter fills gradually."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default()
    image = Image.new("RGB", (300, 60), (0, 0, 0))
    video._draw_swept(image, ImageDraw.Draw(image), 5, 5, "mmmmmmmm", font,
                      (0, 255, 0), (255, 255, 255), 0.5)
    greenish = whitish = 0
    for count, (red, green, blue) in image.getcolors(100000):
        if green > 120 and green > red + 60:
            greenish += count
        elif red > 120 and green > 120 and blue > 120:
            whitish += count
    assert greenish > 0 and whitish > 0


def test_the_whole_line_walks_from_white_to_sung() -> None:
    from dataclasses import replace

    from PIL import Image, ImageDraw, ImageFont

    line = timing.timedline_from_text(0, "zing maar mee", 0.0, 3.0)
    spans = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]
    line = replace(line, syllables=tuple(
        replace(s, start=a, end=b)
        for s, (a, b) in zip(line.syllables, spans)))
    font = ImageFont.load_default()
    green = []
    for moment in (0.0, 1.5, 2.9):
        image = Image.new("RGB", (600, 80), (0, 0, 0))
        video._draw_line(image, ImageDraw.Draw(image), line, moment, 600, 20,
                         font, active_slot=True)
        green.append(sum(count for count, rgb in image.getcolors(100000)
                         if rgb[1] > rgb[0] and rgb[1] > 100))
    assert green[0] < green[1] < green[2], green


# --------------------------------------------------------------------------
# B448 - fifty frames, and a shift that starts as quietly as it ends
# --------------------------------------------------------------------------

def test_the_frame_rate_is_fifty() -> None:
    from modules.config import VideoSettings

    assert VideoSettings.fps == 50
    assert inspect.signature(video.render_video).parameters["fps"].default \
        == 50


def test_an_existing_config_is_lifted_once(tmp_path) -> None:
    """A default that is never read again is no default: the config on
    disk holds the old 25."""
    import json

    from modules.config import load_config

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"video": {"fps": 25}}), encoding="utf-8")
    assert load_config(path).video.fps == 50


def test_a_deliberate_other_rate_is_left_alone(tmp_path) -> None:
    import json

    from modules.config import load_config

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"video": {"fps": 30}}), encoding="utf-8")
    assert load_config(path).video.fps == 30


def test_the_shift_brakes_at_both_ends() -> None:
    """Was ``(1 - t) ** 2``: lands softly but STARTS at full speed, so
    the first frame of a shift was a jolt however high the frame rate."""
    assert video._eased_out(0.0) == 1.0
    assert video._eased_out(1.0) == 0.0
    assert video._eased_out(0.5) == pytest.approx(0.5)
    # Symmetrical, and therefore just as quiet at the start as at the end.
    assert video._eased_out(0.1) + video._eased_out(0.9) \
        == pytest.approx(1.0)
    begin = video._eased_out(0.0) - video._eased_out(0.05)
    middle = video._eased_out(0.475) - video._eased_out(0.525)
    assert begin < middle


def test_the_audio_is_encoded_at_256() -> None:
    from pathlib import Path

    import modules

    source = (Path(modules.__file__).resolve().parent
              / "video.py").read_text(encoding="utf-8")
    assert '"-b:a", "256k"' in source


# --------------------------------------------------------------------------
# B450 - the stress editor rebuilt around the recording
# --------------------------------------------------------------------------

def test_an_anchor_keeps_its_time_and_the_rest_gives_way() -> None:
    spans = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)]
    fitted, shortfall = timing.fit_between_anchors(spans, {2: (2.5, 3.5)})
    assert fitted[2] == (2.5, 3.5)
    assert shortfall == 0.0
    assert fitted[0][0] == 0.0 and fitted[-1][1] == 4.0


def test_the_sentence_keeps_its_own_beginning_and_end() -> None:
    """A redistribution, never a shift of the line."""
    spans = [(5.0, 6.0), (6.0, 7.0), (7.0, 9.0)]
    for anchors in ({}, {1: (5.2, 5.4)}, {0: (5.0, 8.5)}):
        fitted, _short = timing.fit_between_anchors(spans, anchors)
        assert fitted[0][0] == 5.0
        assert fitted[-1][1] == 9.0


def test_the_pieces_stay_in_order_even_when_it_does_not_fit() -> None:
    """Squeezing is bad; running past the end of the sentence or laying
    pieces back to front is worse."""
    spans = [(0.0, 1.0)] + [(n, n + 1.0) for n in range(1, 6)]
    fitted, shortfall = timing.fit_between_anchors(spans, {0: (0.0, 5.95)})
    assert shortfall > 0
    assert all(a <= b for a, b in fitted)
    assert all(fitted[i][1] <= fitted[i + 1][0] + 1e-6
               for i in range(len(fitted) - 1))
    assert fitted[-1][1] == pytest.approx(6.0)


def test_the_rhythm_within_a_run_survives() -> None:
    """A long piece stays longer than a short one next to it."""
    spans = [(0.0, 0.2), (0.2, 1.0), (1.0, 2.0)]
    fitted, _short = timing.fit_between_anchors(spans, {2: (1.5, 2.0)})
    first = fitted[0][1] - fitted[0][0]
    second = fitted[1][1] - fitted[1][0]
    assert second > first * 3


def test_applying_spans_leaves_the_text_alone() -> None:
    line = timing.timedline_from_text(0, "zing maar mee", 0.0, 3.0)
    spans = [(n * 0.5, n * 0.5 + 0.5) for n in range(len(line.syllables))]
    out = timing.apply_spans(line, spans)
    assert [s.text for s in out.syllables] == [s.text for s in line.syllables]
    assert [(s.start, s.end) for s in out.syllables] == spans


def test_the_original_row_is_measured_where_it_can_be() -> None:
    """Word boundaries from the forced alignment, and inside a word the
    same phonetic rule the karaoke side uses."""
    pieces = pipeline.original_pieces(
        "ik zing", [("ik", 1.0, 1.4), ("zing", 2.0, 3.0)])
    assert pieces
    assert pieces[0].start == pytest.approx(1.0)
    assert pieces[-1].end == pytest.approx(3.0)
    # The gap between the two words is not filled in: it was not sung.
    joined = "".join(p.text for p in pieces).strip()
    assert joined.replace(" ", "") == "ikzing"


def test_the_original_row_survives_a_word_count_that_does_not_match() -> None:
    pieces = pipeline.original_pieces("ik zing hard", [("ik", 1.0, 2.0)])
    assert pieces
    assert all(p.end >= p.start for p in pieces)


def test_the_original_row_says_which_pieces_are_held() -> None:
    pieces = pipeline.original_pieces(
        "ik zing maar door", [("ik", 0.0, 0.2), ("zing", 0.2, 0.4),
                              ("maar", 0.4, 0.6), ("door", 0.6, 3.0)])
    assert any(p.held for p in pieces)


def test_the_anchors_are_kept_as_the_users_own_judgement(tmp_path) -> None:
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    pipeline.set_stress_anchors(context, {0: {3: 5}, 2: {1: 1}})
    assert pipeline.stress_anchors(context) == {0: {3: 5}, 2: {1: 1}}


def test_the_anchors_hang_in_the_dependency_chain() -> None:
    """They point at pieces of both texts, so a changed text has to be
    able to take them with it."""
    from modules import dependencies

    steps, _metas, _files = dependencies.invalidation_plan(
        ["input:karaoke_text"], ())
    assert "stress_anchors" in steps


def test_the_stress_is_still_settable_by_hand() -> None:
    """Taking it away would have removed something that was in use."""
    from modules import stress_editor

    source = inspect.getsource(stress_editor.SentenceCanvas.mousePressEvent)
    assert "right_button" in source
    assert "set_stress" in source


# --------------------------------------------------------------------------
# B451 - a rescued timing keeps its counterpart
# --------------------------------------------------------------------------

def test_the_rescue_writes_both_files() -> None:
    """The yardstick needs the PAIR - it measures how far the hand moved
    the automatic timing - and silently skips a project that is missing
    one of the two. Lied_Q and Lied_O had disappeared from
    every measurement that way."""
    source = inspect.getsource(pipeline._write_rescued_timing)
    assert "timing_auto_file" in source
    caller = inspect.getsource(pipeline.sync_input_changes)
    assert "_read_auto_timing(context, rescue[0])" in caller
    assert caller.index("_read_auto_timing") < caller.index("invalidate(")


def test_the_pair_is_kept_matched_or_not_written_at_all() -> None:
    """The yardstick compares the two line by line and gives up on a
    pair that does not match, so a mismatched pair is worse than a
    missing one - a missing one is at least visible."""
    source = inspect.getsource(pipeline._read_auto_timing)
    assert "carry_over(" in source
    assert "len(carried) == len(like)" in source


def test_the_yardstick_needs_both_files() -> None:
    """The reason the missing file was invisible: no complaint, just a
    project that is not in the table."""
    from pathlib import Path

    import modules

    source = (Path(modules.__file__).resolve().parents[1] / "tools"
              / "timing_regression.py").read_text(encoding="utf-8")
    assert "hand_path.exists() and auto_path.exists()" in source


# --------------------------------------------------------------------------
# B452/B453/B454 - the brake, the letters, and what is switched off
# --------------------------------------------------------------------------

def test_the_twenty_version_brake_is_gone() -> None:
    from modules import test_panel

    for trial in test_panel.HEAVY_TRIALS:
        assert not hasattr(trial, "threshold")
    assert "versions_ago" not in inspect.getsource(test_panel.heavy_trial)


def test_a_trial_runs_once_per_version_and_state(tmp_path) -> None:
    from modules import test_panel
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    assert test_panel._heavy_done(context, "1.5.11a") is None
    test_panel._remember_heavy(context, "1.5.11a", 1.0)
    assert test_panel._heavy_done(context, "1.5.11a") is not None
    assert test_panel._heavy_done(context, "1.5.11b") is None


def test_the_letters_can_be_picked_one_by_one() -> None:
    from modules import test_panel

    test_panel.limit_heavy_to(["1.5.11a"])
    try:
        assert test_panel._wanted("1.5.11a")
        assert not test_panel._wanted("1.5.11b")
    finally:
        test_panel.limit_heavy_to([])
    assert test_panel._wanted("1.5.11b"), "empty = everything, as before"


def test_the_answered_trials_are_switched_off_not_deleted() -> None:
    """The same way a model is switched off: the idea stays readable."""
    from modules import test_panel

    codes = {trial.code: trial for trial in test_panel.HEAVY_TRIALS}
    assert codes["1.5.11d"].off
    assert codes["1.5.11d"].function is test_panel.chunk_trial
    assert not codes["1.5.11a"].off and not codes["1.5.11b"].off


def test_the_new_gain_trial_is_on_and_can_go_off_again() -> None:
    from modules import test_panel

    codes = {trial.code: trial for trial in test_panel.HEAVY_TRIALS}
    # B491: the question has been answered, so it is off now - and that
    # is exactly what this test set out to pin down: being able to go
    # off, not being gone.
    assert "1.5.11e" in codes and codes["1.5.11e"].off
    assert codes["1.5.11e"].reason == "gain_answered"
    assert "GAIN_LEVELS" in dir(test_panel)
    first, target = test_panel.GAIN_LEVELS[0]
    assert target is None, "the first level is the untouched stem"
    from modules import translations

    for language, label in (("nl", "zoals nu"), ("en", "as it is")):
        translations.set_language(language)
        try:
            assert test_panel._gain_label(first) == label
        finally:
            translations.set_language("nl")


# --------------------------------------------------------------------------
# B455 - the la-la-la that was being deleted
# --------------------------------------------------------------------------

def test_a_row_of_the_same_short_syllable_is_a_chant() -> None:
    """Whisper's hallucinations are plausible SENTENCES; a row of the
    same short syllable is the opposite of that shape."""
    assert pipeline._is_chant(["la", "la", "la"])
    assert pipeline._is_chant(["na", "na", "na", "na"])
    assert not pipeline._is_chant(["la", "la"])
    assert not pipeline._is_chant(["heerlijke", "heer", "heerlijke"])
    assert not pipeline._is_chant(["polonaise"] * 3)


def test_the_filter_knows_what_the_texts_chant() -> None:
    """B464: not "every word of both texts" - that widened the match
    floor and cost half a second of timing - but only the syllables the
    texts REPEAT back to back, which is the one thing that tells a
    carnival chant apart from a Whisper loop."""
    source = inspect.getsource(pipeline._clean_segments_and_alignment)
    assert "chanted_keys(context)" in source
    assert "extra_keys=chanted" in source


def test_a_chant_survives_both_rounds() -> None:
    for name in ("_filter_hallucinations",
                 "_filter_hallucinations_in_position"):
        assert "_is_chant" in inspect.getsource(getattr(pipeline, name)), name


def test_the_measured_reason_it_went_wrong() -> None:
    """0.50 was not Whisper's confidence but the best lyrics match: "la"
    against "lang", just under the floor of 0.65."""
    from modules import cluster

    similarity = cluster.similarity(cluster.phonetic_key("la"),
                                    cluster.phonetic_key("lang"))
    assert similarity < pipeline._SEGMENT_HALLUCINATION_MATCH_FLOOR


# --------------------------------------------------------------------------
# B456 - one level for every video
# --------------------------------------------------------------------------

def test_the_target_is_a_setting_and_can_be_switched_off() -> None:
    from dataclasses import replace

    from modules.config import default_config

    config = default_config()
    assert config.advanced.video_loudness_lufs == -16.0
    assert config.advanced.video_true_peak_db == -1.0
    off = replace(config.advanced, video_loudness_lufs=None)
    assert off.video_loudness_lufs is None


def test_the_filter_uses_the_measurement_and_stays_linear() -> None:
    """``linear`` is the whole point: a straight gain where it fits, and
    dynamic only for a track that cannot reach the target otherwise."""
    from modules.ffmpeg import Loudness, loudnorm_filter

    measured = Loudness(integrated=-23.4, true_peak=-7.1, lra=14.5,
                        threshold=-33.0)
    text = loudnorm_filter(measured, -16.0, -1.0)
    assert "linear=true" in text
    assert "measured_I=-23.4" in text and "measured_TP=-7.1" in text
    assert "I=-16.0" in text and "TP=-1.0" in text


def test_what_a_track_reaches_on_a_straight_gain() -> None:
    """Reported next to the target, so it is visible WHICH song had to
    give something up instead of quietly sounding flatter."""
    from modules.ffmpeg import Loudness, reachable_loudness

    # Lied_I, measured: -23.42 LUFS with peaks at -7.09.
    quiet = Loudness(integrated=-23.42, true_peak=-7.09, lra=14.5,
                     threshold=-33.0)
    assert reachable_loudness(quiet, -1.0) == pytest.approx(-17.33, abs=0.01)
    # Biertje hier: already peaking, so it can only go down.
    loud = Loudness(integrated=-12.61, true_peak=-0.08, lra=2.2,
                    threshold=-22.0)
    assert reachable_loudness(loud, -1.0) < -12.61


def test_the_render_measures_before_it_normalises() -> None:
    """A single pass has to guess as it goes and gets the start of a song
    wrong."""
    source = inspect.getsource(video.render_video)
    assert "measure_loudness(" in source
    assert source.index("measure_loudness(") < source.index("loudnorm_filter(")


def test_a_failed_measurement_does_not_drop_the_render() -> None:
    """A level is a nicety, not a reason to lose a video."""
    source = inspect.getsource(video.render_video)
    assert "if measured is not None:" in source


# --------------------------------------------------------------------------
# What a critical rereading of this release turned up, all fixed before
# anything was delivered. Each of these is the test that was missing.
# --------------------------------------------------------------------------

def test_the_mapping_is_read_the_way_it_is_written() -> None:
    """``couple_timing`` builds {karaoke line: original line} and the two
    other readers in gui.py use it that way. Reading it backwards is
    invisible while the coupling is one-to-one and wrong the moment it is
    not - which is the case the editor exists for."""
    from modules import gui

    block = inspect.getsource(gui.MainWindow._open_stress_editor)
    assert "by_karaoke = {int(k): int(v)" in block
    assert "for original_index, karaoke_index in" not in block


def test_anchors_in_any_order_never_break_the_sentence() -> None:
    """The editor lets you couple in any order and point two karaoke
    pieces at the same original. Neither is a mistake to refuse, and both
    used to produce times running backwards."""
    import random

    random.seed(11)
    for _ in range(500):
        count = random.randint(1, 8)
        spans = [(float(n), float(n + 1)) for n in range(count)]
        anchors = {}
        for index in random.sample(range(count), random.randint(0, count)):
            low = round(random.uniform(-1, count + 1), 2)
            anchors[index] = (low, round(low + random.uniform(-1, 3), 2))
        fitted, _short = timing.fit_between_anchors(spans, anchors)
        assert len(fitted) == count
        assert all(a <= b for a, b in fitted), (spans, anchors, fitted)
        assert all(fitted[n][1] <= fitted[n + 1][0] + 1e-6
                   for n in range(count - 1)), (anchors, fitted)
        assert fitted[0][0] == spans[0][0]
        assert fitted[-1][1] == spans[-1][1]


def test_an_anchor_on_the_last_piece_does_not_shorten_the_sentence() -> None:
    spans = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]
    fitted, _short = timing.fit_between_anchors(spans, {2: (2.1, 2.4)})
    assert fitted[-1][1] == 3.0


def test_releasing_a_coupling_puts_the_times_back(qapp=None) -> None:
    """Refitting from the ALREADY refitted spans made releasing a no-op,
    and one experimental click permanent."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from modules.stress_editor import StressEditorDialog

    lines = [timing.timedline_from_text(0, "zing maar mee", 0.0, 3.0)]
    original = [timing.timedline_from_text(0, "sing along now", 0.0, 3.0)]
    dialog = StressEditorDialog(lines, lambda *a: None,
                                  original_lines=original)
    before = [(s.start, s.end) for s in dialog._karaoke[0].syllables]
    dialog._canvas._anchors[1] = 0
    dialog._changed()
    assert [(s.start, s.end) for s in dialog._karaoke[0].syllables] != before
    dialog._canvas._anchors.pop(1)
    dialog._changed()
    assert [(s.start, s.end) for s in dialog._karaoke[0].syllables] == before


def test_closing_without_saving_changes_nothing() -> None:
    """The editor MOVES times now, so writing on every way out would
    have made an experiment permanent - on hand-made timing, unasked."""
    from modules import stress_editor

    source = inspect.getsource(
        stress_editor.StressEditorDialog.done)
    assert "DialogCode.Accepted" in source


def test_silence_gives_no_measurement_instead_of_minus_infinity() -> None:
    """loudnorm refuses its own -inf back ("out of range [-99 - 0]") and
    the render then dies on a filter string - while it promises to fail
    silently."""
    import tempfile
    from pathlib import Path

    import numpy
    import soundfile

    from modules import ffmpeg

    folder = Path(tempfile.mkdtemp())
    path = folder / "stil.wav"
    soundfile.write(path, numpy.zeros(44100 * 2, dtype="float32"), 44100)
    assert ffmpeg.measure_loudness(path) is None


def test_the_audio_keeps_a_sane_sample_rate() -> None:
    """loudnorm works internally at 192 kHz and passes that on, so
    without this every video shipped 96 kHz AAC - twice the size for
    audio nobody can hear the difference of."""
    from modules.ffmpeg import Loudness, OUTPUT_RATE, loudnorm_filter

    measured = Loudness(integrated=-20.0, true_peak=-3.0, lra=5.0,
                        threshold=-30.0)
    assert f"aresample={OUTPUT_RATE}" in loudnorm_filter(measured)
    assert OUTPUT_RATE in (44100, 48000)


def test_the_frame_rate_lift_happens_once(tmp_path) -> None:
    """Without the marker 25 would be the one value the user could never
    keep, which is the opposite of a setting."""
    import json

    from modules.config import load_config, save_config

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"video": {"fps": 25}}), encoding="utf-8")
    assert load_config(path).video.fps == 50
    save_config(load_config(path), path)
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["video"]["fps"] = 25
    path.write_text(json.dumps(stored), encoding="utf-8")
    assert load_config(path).video.fps == 25, "a deliberate 25 stays"
