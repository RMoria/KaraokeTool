"""v1.0.15: blocks that come back, timed together, and what came with it.

The block models (B602-B605, :mod:`modules.block_timing`) are pure
functions on timed lines, so they are tested on made-up lines here: the
rule the owner set for each one, and for every rule a mutation that has
to make the test fail. Test 1.5.15 (:mod:`modules.block_trial`) and the
editor's linked blocks (B601) are tested the same way.
"""
from __future__ import annotations

import inspect
import os

import numpy as np
import pytest

from modules import block_timing as bt
from modules import block_trial, model_orders, model_register, pipeline
from modules.timing import Syllable, TimedLine
from modules.translations import TRANSLATIONS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _line(index, block, words, start, length=0.4, gap=0.1, quality="high"):
    pieces, moment = [], start
    for n, word in enumerate(words):
        pieces.append(Syllable(text=(" " if n else "") + word,
                               start=round(moment, 3),
                               end=round(moment + length, 3)))
        moment += length + gap
    return TimedLine(index=index, text=" ".join(words), crowd=False,
                     syllables=tuple(pieces), quality=quality, block=block)


def _starts(line):
    return [piece.start for piece in line.syllables]


CHORUS = ["ja", "la", "la"]


# -- B603: linked blocks heard together -------------------------------------

def _three_choruses():
    """Three linked choruses, 20 s apart. The second "la" was heard on
    the same spot in the first two (certainty 0.5 each) and a bit
    earlier, more surely, in the third (0.8)."""
    lines = [_line(0, 0, CHORUS, 10.0), _line(1, 1, CHORUS, 30.0),
             _line(2, 2, CHORUS, 50.0)]
    pieces = list(lines[2].syllables)
    pieces[1] = Syllable(text=" la", start=50.3, end=50.7)
    lines[2] = TimedLine(index=2, text="ja la la", crowd=False,
                         syllables=tuple(pieces), quality="high", block=2)
    certainty = {10.0: 0.9, 10.5: 0.5, 11.0: 0.9,
                 30.0: 0.9, 30.5: 0.5, 31.0: 0.9,
                 50.0: 0.9, 50.3: 0.8, 51.0: 0.9}
    return lines, lambda moment: certainty.get(round(moment, 3), 0.0)


def test_the_summed_certainty_wins_and_holds_for_every_block() -> None:
    """The owner's rule: the combination of the highest certainty over
    the blocks. Two blocks on one spot (0.5 + 0.5) beat one surer block
    elsewhere (0.8), and all three get it - no block keeps its own."""
    lines, certainty = _three_choruses()
    fused = bt.fuse(lines, [[0, 1, 2]], certainty)
    assert _starts(fused[0])[1] == pytest.approx(10.5, abs=0.01)
    assert _starts(fused[1])[1] == pytest.approx(30.5, abs=0.01)
    assert _starts(fused[2])[1] == pytest.approx(50.5, abs=0.01)


def test_without_the_sum_the_surer_single_block_would_win(monkeypatch) -> None:
    """Mutation check: pick the group by its best single certainty
    instead of the sum, and the third block's time wins - so the test
    above really tests the sum."""
    lines, certainty = _three_choruses()

    def by_best(seen, tolerance):
        best = max(seen, key=lambda item: item[2])
        return best[0], best[1]

    monkeypatch.setattr(bt, "_winner", by_best)
    fused = bt.fuse(lines, [[0, 1, 2]], certainty)
    assert _starts(fused[0])[1] == pytest.approx(10.3, abs=0.01)


def test_the_tolerance_decides_what_counts_as_one_spot() -> None:
    """0.3 s apart are two spots at 0.1 s, one spot at 0.5 s."""
    seen = [(10.0, 10.4, 0.5), (10.3, 10.7, 0.6)]
    assert bt._winner(seen, 0.1)[0] == pytest.approx(10.3)
    assert bt._winner(seen, 0.5)[0] == pytest.approx(
        (10.0 * 0.5 + 10.3 * 0.6) / 1.1)


def test_a_word_more_in_one_block_does_not_shift_the_rest() -> None:
    """Linked blocks may differ by a word. The words are paired by their
    letters: "hey" of the second block has no kin and keeps its time,
    and its "la" is fused with the first block's "la" - not with "hey",
    which stands where "la" stands in the first."""
    def made(index, block, spans, words):
        return TimedLine(index=index, text=" ".join(words), crowd=False,
                         syllables=tuple(
                             Syllable(text=(" " if n else "") + word,
                                      start=a, end=b)
                             for n, (word, (a, b)) in enumerate(
                                 zip(words, spans))),
                         quality="high", block=block)

    first = made(0, 0, [(10.0, 10.4), (11.1, 11.4), (11.5, 11.9)], CHORUS)
    second = made(1, 1, [(30.0, 30.4), (30.5, 30.9), (31.0, 31.4),
                         (31.5, 31.9)], ["ja", "hey", "la", "la"])
    heard = {10.0: 0.9, 11.1: 0.9, 11.5: 0.9,
             30.0: 0.9, 30.5: 0.7, 31.0: 0.2, 31.5: 0.9}
    fused = bt.fuse([first, second], [[0, 1]],
                    lambda moment: heard.get(round(moment, 3), 0.0))
    # 31.1 on the clock the blocks agree on (within a few hundredths).
    assert _starts(fused[1]) == pytest.approx([30.0, 30.5, 31.1, 31.5],
                                              abs=0.04)
    assert _starts(fused[0]) == pytest.approx([10.0, 11.1, 11.5], abs=0.04)


def test_the_offset_is_what_most_lines_agree_on() -> None:
    assert bt._agreed([0.05, 0.05, 0.06, 0.3], 0.1) == pytest.approx(0.0533,
                                                                abs=1e-3)


# -- B602: an unheard line like its linked kin ---------------------------

def test_an_unheard_line_takes_the_layout_of_its_kin() -> None:
    lines = [_line(0, 0, CHORUS, 10.0), _line(1, 0, ["hey", "ho"], 12.0),
             _line(2, 1, CHORUS, 30.1),
             _line(3, 1, ["hey", "ho"], 31.0, length=0.05, gap=0.0,
                   quality="even")]
    filled = bt.fill(lines, [[0, 1]])
    assert filled[3].quality == bt.FILLED
    assert filled[3].start == pytest.approx(32.1, abs=0.01)
    assert filled[3].end - filled[3].start == pytest.approx(0.9, abs=0.01)
    assert filled[:3] == tuple(lines[:3])


def test_a_block_heard_nowhere_is_left_to_the_placement() -> None:
    lines = [_line(0, 0, CHORUS, 10.0),
             _line(1, 1, CHORUS, 30.0, quality="even")]
    assert bt.fill(lines, [[0, 1]]) == tuple(lines)


# -- B604: a whole block to its spot --------------------------------------

def _chroma():
    rng = np.random.default_rng(3)
    matrix = rng.random((12, 700))
    matrix[:, 300:340] = matrix[:, 100:140]     # 10 s comes back at 30 s
    return 0.1, matrix


def test_the_chords_say_where_a_block_comes_back() -> None:
    step, matrix = _chroma()
    spots = bt.harmony_spots(step, matrix, 10.0, 14.0, 26.0)
    assert spots[0][0] == pytest.approx(30.0)
    assert all(abs(start - 10.0) >= 2.0 for start, _s in spots)


def test_a_block_on_top_of_another_moves_as_a_whole() -> None:
    step, matrix = _chroma()
    lines = [_line(0, 0, CHORUS, 10.0), _line(1, 0, ["hey", "ho"], 12.0),
             _line(2, 1, ["x", "y"], 20.0),
             _line(3, 2, CHORUS, 20.2), _line(4, 2, ["hey", "ho"], 22.2)]
    placed = bt.place(lines, [[0, 2]], lambda a, b, g: bt.harmony_spots(
        step, matrix, a, b, g), relay=[[0, 2]])
    assert placed[3].start == pytest.approx(30.0, abs=0.01)
    assert placed[4].start == pytest.approx(32.0, abs=0.01)
    assert placed[:3] == tuple(lines[:3])


def test_a_block_that_is_fine_stays() -> None:
    step, matrix = _chroma()
    lines = [_line(0, 0, CHORUS, 10.0), _line(1, 1, CHORUS, 30.0)]
    placed = bt.place(lines, [[0, 1]], lambda a, b, g: bt.harmony_spots(
        step, matrix, a, b, g))
    assert placed == tuple(lines)


def test_a_verse_is_moved_but_not_laid_out_again() -> None:
    """Same shape, other words: the block moves, its own layout stays."""
    step, matrix = _chroma()
    lines = [_line(0, 0, ["een", "twee", "drie"], 10.0),
             _line(1, 1, ["x", "y"], 20.0),
             _line(2, 2, ["vier", "vijf", "zes"], 20.2, length=0.3)]
    placed = bt.place(lines, [[0, 2]], lambda a, b, g: bt.harmony_spots(
        step, matrix, a, b, g), relay=[])
    moved = placed[2]
    assert moved.start == pytest.approx(30.0, abs=0.01)
    assert [p.end - p.start for p in moved.syllables] == pytest.approx(
        [0.3, 0.3, 0.3])


# -- B605: the words of the text laid on the voice ---------------------------

def test_found_words_are_matched_by_their_letters() -> None:
    line = _line(0, 0, ["hallo", "wereld", "daar"], 5.0)
    laid = bt.lay_words(line, [("Hallo,", 5.1, 5.4, 0.9),
                               ("daar", 6.5, 6.9, 0.8)], 0.3)
    assert _starts(laid) == pytest.approx([5.1, 5.5, 6.5])


def test_an_unsure_word_keeps_its_time() -> None:
    line = _line(0, 0, ["hallo", "wereld"], 5.0)
    laid = bt.lay_words(line, [("hallo", 5.2, 5.4, 0.1)], 0.3)
    assert laid == line


def test_words_that_no_longer_fit_are_spread_between_the_placed() -> None:
    line = _line(0, 0, ["een", "twee", "drie"], 5.0)
    laid = bt.lay_words(line, [("een", 5.0, 5.2, 0.9),
                               ("drie", 5.4, 5.6, 0.9)], 0.3)
    starts = _starts(laid)
    assert starts[0] < starts[1] < starts[2]
    assert laid.syllables[1].end <= laid.syllables[2].start + 1e-3


# -- The register and the pipeline ---------------------------------------------

@pytest.mark.parametrize("code, attribute", [
    ("B602", "_fill_linked_blocks"), ("B603", "_fuse_linked_blocks"),
    ("B604", "_place_blocks"), ("B605", "_lyrics_first")])
def test_every_block_model_is_registered_off_with_a_neutral(code,
                                                            attribute):
    model = model_register.by_code(code)
    assert model is not None and model.default_on is False
    module, name, neutral = model.targets[0]
    assert module is pipeline and name == attribute
    assert hasattr(pipeline, attribute)
    timed = (_line(0, 0, CHORUS, 1.0),)
    assert neutral(object(), timed, None, []) is timed
    for language in ("nl", "en"):
        assert TRANSLATIONS[language][f"model_name_{model.key}"]
        assert TRANSLATIONS[language][f"model_reason_{model.key}"]


def test_the_coupling_runs_the_block_models_in_their_order() -> None:
    source = inspect.getsource(pipeline.build_coupling)
    assert "_block_models(context, timed, project, karaoke_lines)" in source
    order = inspect.getsource(pipeline._block_models)
    assert order.index("_place_blocks") < order.index("_fuse_linked_blocks") \
        < order.index("_fill_linked_blocks") < order.index("_lyrics_first")


def test_a_failing_block_model_costs_only_itself(caplog) -> None:
    timed = (_line(0, 0, CHORUS, 1.0),)

    def broken():
        raise ValueError("boom")

    assert pipeline._block_model(None, "b603", timed, broken) is timed


def test_heard_certainty_leaves_laid_on_words_out(monkeypatch) -> None:
    from modules.whisper import ORIGIN_ALIGNED, Segment, Word

    heard = Segment(index=0, text="ja", start=1.0, end=1.5,
                    words=(Word("ja", 1.0, 1.5, 0.8),))
    laid = Segment(index=1, text="la", start=3.0, end=3.5,
                   words=(Word("la", 3.0, 3.5, 0.9),), origin=ORIGIN_ALIGNED)
    monkeypatch.setattr(pipeline, "load_segments",
                        lambda context, track: (heard, laid))
    certainty = pipeline._heard_certainty(None, lambda s: s + 2.0)
    assert certainty(3.0) == pytest.approx(0.8)
    assert certainty(3.02) == pytest.approx(0.8)
    assert certainty(5.0) == 0.0


# -- Test 1.5.15 ----------------------------------------------------------

def test_the_fusion_widths_travel_by_name_but_are_not_orders() -> None:
    assert "B603 0.05 s" not in model_orders.names()
    (module, attribute, value), = model_orders.targets("B603 0.05 s")
    assert module is bt and attribute == "FUSE_S" and value == 0.05
    assert model_orders.models_for("B603 0.2 s") == ("B603",)


def test_a_round_switches_exactly_its_block_models_on() -> None:
    variant = block_trial.Variant("x", ("B603",))
    states = block_trial.states_for(variant)
    assert states["B603"] is True
    assert states["B602"] is states["B604"] is states["B605"] is False
    assert states["B377"] == model_register.enabled("B377")
    assert block_trial.VARIANTS[0].on == ()
    # v1.0.27: B605 is measured and has no round of its own any more.
    assert {code for v in block_trial.VARIANTS for code in v.on} == \
        set(block_trial.CODES) - {"B605"}


def test_the_figures_split_lines_and_blocks() -> None:
    rows = [{"project": "S", "hand_index": [0, 1, 2, 3],
             "hand_starts": [10.0, 12.0, 30.0, 32.0],
             "new_starts": [10.1, 12.1, 33.0, 35.0]}]
    shapes = {"S": ([0, 0, 1, 1], {0: "linked", 1: "single"})}
    found = block_trial.figures(rows, shapes)
    assert found["lines"] == 4
    assert found["within"] == pytest.approx(50.0)
    assert found["blocks"] == pytest.approx(50.0)
    assert found["linked"] == pytest.approx(0.1)
    assert found["single"] == pytest.approx(3.0)
    assert found["shape"] is None
    text = block_trial.report_text([(block_trial.VARIANTS[0], found)])
    assert "1.5.15" in text and "| S |" in text


def test_the_trial_is_a_button_on_request() -> None:
    from modules import test_panel

    action = next(a for a in test_panel.ACTIONS if a.code == "1.5.15")
    assert action.on_request and action.done      # v1.0.28: done


# -- B601: an edit in a linked block that does not fit -----------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _row(index, block, start, end):
    return {"text": "ja", "crowd": False, "index": index, "block": block,
            "disabled": False,
            "syllables": [{"text": "ja", "start": start, "end": end,
                           "held": False}]}


def test_a_linked_block_that_cannot_follow_goes_back_whole(qapp) -> None:
    """The owner's rule: when following would overlap, that block is not
    changed - not half-followed. The first small step fits, the second
    does not, and the block goes back to where it was before the drag."""
    from modules.timing_editor import TimingCanvas

    notices = []
    lines = [_row(0, 0, 1.0, 2.0), _row(1, 1, 20.0, 21.0),
             _row(2, 2, 21.05, 22.0)]
    canvas = TimingCanvas(np.zeros(100, dtype=np.float32), None,
                          duration=30.0, lines=lines,
                          on_seek=lambda *_: None, block_links=[[0, 1]],
                          on_notice=notices.append)
    canvas._follow_sentence(0, "verplaats", (1.0, 2.0), (1.03, 2.03))
    assert lines[1]["syllables"][0]["start"] == pytest.approx(20.03)
    canvas._follow_sentence(0, "verplaats", (1.03, 2.03), (1.3, 2.3))
    assert lines[1]["syllables"][0]["start"] == pytest.approx(20.0)
    assert lines[1]["syllables"][0]["end"] == pytest.approx(21.0)
    canvas._report_not_followed()
    assert notices and "2" in notices[0]


def test_an_edited_line_never_runs_into_the_room_of_a_stuck_kin(
        qapp) -> None:
    """Review of v1.0.15: two linked one-line blocks right after each
    other, and an unlinked line after them. Dragging the first to the
    right in steps, its kin follows until it gets stuck and goes back to
    where it was - and the first line may not be lying there by then."""
    from modules.timing_editor import TimingCanvas, _line_span

    lines = [_row(0, 0, 1.0, 2.0), _row(1, 1, 2.2, 3.0),
             _row(2, 2, 3.3, 4.0)]
    canvas = TimingCanvas(np.zeros(100, dtype=np.float32), None,
                          duration=30.0, lines=lines,
                          on_seek=lambda *_: None, block_links=[[0, 1]],
                          on_notice=lambda text: None)
    for _step in range(5):
        start, end = _line_span(lines[0])
        span = canvas._keep_in_order([0], start + 0.1, end + 0.1)
        span = canvas._without_overlap([0], *span)
        canvas._remap_rows([0], (start, end), span)
        canvas._follow_sentence(0, "verplaats", (start, end), span)
        assert _line_span(lines[0])[1] <= _line_span(lines[1])[0] + 1e-6
    # The first stops against where its kin began; the kin moved just as
    # far, so the two stay one edit apart and nothing overlaps.
    moved = _line_span(lines[0])[0] - 1.0
    assert moved == pytest.approx(0.2)
    assert _line_span(lines[1])[0] - 2.2 == pytest.approx(moved)


# -- B597: the level of a karaoke made from the original ------------------

def test_the_music_level_is_measured_on_its_own(tmp_path) -> None:
    """A separation scales every stem on its own. Fitting the original on
    both stems apart gives the music's factor, also with a mono original
    at another rate than the stems."""
    import soundfile as sf

    rng = np.random.default_rng(5)
    rate = 44_100
    seconds = 3
    from scipy.signal import butter, sosfilt
    # Music-like signals: nothing near Nyquist, where resampling cuts.
    low = butter(6, 5000, fs=rate, output="sos")
    voice = sosfilt(low, rng.normal(0, 0.2, rate * seconds))
    music = sosfilt(low, rng.normal(0, 0.3, rate * seconds))
    stereo = lambda x: np.stack([x, x], axis=1)  # noqa: E731
    sf.write(tmp_path / "vocals.wav", stereo(0.9 * voice), rate,
             subtype="FLOAT")
    sf.write(tmp_path / "music.wav", stereo(0.85 * music), rate,
             subtype="FLOAT")
    from scipy.signal import resample_poly
    mix48 = resample_poly(voice + music, 160, 147)
    sf.write(tmp_path / "original.wav", mix48, 48_000, subtype="FLOAT")
    factor = pipeline._measured_level(tmp_path / "original.wav",
                                      tmp_path / "vocals.wav",
                                      tmp_path / "music.wav")
    assert factor == pytest.approx(0.85, abs=0.01)


def test_demucs_gets_clip_mode_none_only_where_it_knows_it(
        monkeypatch) -> None:
    import importlib.metadata as metadata

    from modules import separation

    monkeypatch.setattr(metadata, "version", lambda name: "4.1.0")
    assert separation._level_args() == ["--clip-mode", "none", "--float32"]
    monkeypatch.setattr(metadata, "version", lambda name: "4.0.1")
    assert separation._level_args() == ["--float32"]


def test_a_new_project_follows_the_profile_until_its_first_step(
        tmp_path) -> None:
    """Review of v1.0.15: choosing another profile after making a
    project but before its first step still counts; after it, not."""
    from dataclasses import replace

    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Nieuw")
    ensure_directories(paths)
    config = default_config()
    context = pipeline.AppContext(paths=paths, config=config,
                                  store=ProjectStore(paths.project_file))
    assert pipeline.project_settings(context)["profile"] == "high"
    quick = replace(context, config=replace(config, advanced=replace(
        config.advanced, profile="quick")))
    assert pipeline.project_settings(quick)["whisper_model"] == "small"
    context.store.set_step("whisper_original", {"x": 1})
    assert pipeline.project_settings(context)["profile"] == "quick"


def test_high_performance_is_the_full_stand_whatever_the_old_file_says(
        ) -> None:
    from modules import profiles

    high = profiles.settings_for("high")
    assert high["whisper_model"] == "large-v3"
    assert all(high[key] for key in ("chunked_transcription", "gap_text",
                                     "forced_alignment", "vocal_analysis"))
    assert profiles.settings_for("unknown")["profile"] == "high"


# -- The second 1.5.14 night: an environment that is there but broken --------

def test_a_broken_roformer_environment_is_not_available(
        tmp_path, monkeypatch) -> None:
    """Every Roformer separation of that night stopped on its first
    import (librosa 1.0 no longer brings audioread). The environment is
    now checked by importing the library in it, once, and the answer is
    the exception itself - the last line - not where the traceback
    began."""
    import subprocess

    from modules import proc, separation

    python = tmp_path / "venv_separator" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    monkeypatch.setattr(separation, "roformer_env_dirs",
                        lambda: [tmp_path / "venv_separator"])
    monkeypatch.setattr(separation, "_ROFORMER_CHECKED", {})
    asked = []
    error = ('Traceback (most recent call last):\n  File "x", line 1\n'
             "    import audioread\n"
             "ModuleNotFoundError: No module named 'audioread'\n")

    def run(command, **k):
        asked.append(command)
        return subprocess.CompletedProcess(command, 1, "", error)

    monkeypatch.setattr(proc, "run", run)
    way = separation.way_for("roformer")
    assert not separation.is_available(way)
    assert separation.roformer_problem() == \
        "ModuleNotFoundError: No module named 'audioread'"
    assert not pipeline._way_available(way)
    assert len(asked) == 1, "checked once per run"


def test_install_names_what_librosa_1_no_longer_brings() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "KaraokeToolGUI.bat").read_text(
        encoding="utf-8", errors="replace")
    line = next(row for row in text.splitlines()
                if "audio-separator[%SEPKIND%]" in row and "pip install" in row)
    assert "audioread" in line and "librosa>=0.10,<1" in line
    assert 'import audio_separator.separator' in text


def test_the_background_of_a_moved_block_goes_along() -> None:
    step, matrix = _chroma()
    bg = _line(5, 2, ["oh"], 20.5)
    bg = TimedLine(index=5, text="oh", crowd=False, syllables=bg.syllables,
                   quality="high", block=2, bg=True)
    lines = [_line(0, 0, CHORUS, 10.0), _line(1, 0, ["hey", "ho"], 12.0),
             _line(2, 1, ["x", "y"], 20.0),
             _line(3, 2, CHORUS, 20.2), _line(4, 2, ["hey", "ho"], 22.2), bg]
    placed = bt.place(lines, [[0, 2]], lambda a, b, g: bt.harmony_spots(
        step, matrix, a, b, g), relay=[[0, 2]])
    moved = placed[3].start - 20.2
    assert moved == pytest.approx(9.8, abs=0.01)
    assert placed[5].start == pytest.approx(20.5 + moved, abs=0.01)


def test_the_fusion_width_reaches_the_block_clock_too(monkeypatch) -> None:
    """Review of v1.0.15: the width for 'the same spot' was bound when the
    module was loaded, so the 0.05 and 0.2 s rounds of 1.5.15 changed
    only half of the fusion."""
    seen = []
    real = bt._agreed
    monkeypatch.setattr(bt, "_agreed",
                        lambda diffs, tolerance: seen.append(tolerance)
                        or real(diffs, tolerance))
    monkeypatch.setattr(bt, "FUSE_S", 0.2)
    lines, certainty = _three_choruses()
    bt.fuse(lines, [[0, 1, 2]], certainty, tolerance=bt.FUSE_S)
    assert seen and set(seen) == {0.2}


def test_an_export_that_would_clip_is_turned_down_as_a_whole(
        tmp_path) -> None:
    """Review of v1.0.15: the processed karaoke is float and may peak
    above full scale. The shared file is a copy turned down just far
    enough; the processed file keeps its level."""
    import soundfile as sf

    from modules import export

    rate = 44_100
    data = np.stack([np.linspace(-1.2, 1.2, rate)] * 2, axis=1)
    source = tmp_path / "karaoke_edited.wav"
    sf.write(source, data, rate, subtype="FLOAT")
    quieter = export._without_clipping(source)
    assert quieter != source and quieter.name == \
        "karaoke_edited_export.wav"
    peak = float(np.max(np.abs(sf.read(quieter)[0])))
    assert 0.99 <= peak <= 1.0
    assert float(np.max(np.abs(sf.read(source)[0]))) == pytest.approx(1.2)
    fine = tmp_path / "fine.wav"
    sf.write(fine, data / 2, rate, subtype="FLOAT")
    assert export._without_clipping(fine) == fine


def test_a_probe_that_did_not_finish_is_asked_again(tmp_path,
                                                    monkeypatch) -> None:
    import subprocess

    from modules import proc, separation

    python = tmp_path / "venv_separator" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    monkeypatch.setattr(separation, "roformer_env_dirs",
                        lambda: [tmp_path / "venv_separator"])
    monkeypatch.setattr(separation, "_ROFORMER_CHECKED", {})
    answers = [subprocess.TimeoutExpired("python", 300),
               subprocess.CompletedProcess("python", 0, "", "")]

    def run(command, **k):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(proc, "run", run)
    assert separation.roformer_problem() is not None
    assert separation.roformer_problem() is None


# -- install.bat keeps a log (v1.0.15) -------------------------------------

def test_a_command_goes_to_screen_and_log_with_its_exit_code(
        tmp_path, capfd) -> None:
    import subprocess
    import sys
    from pathlib import Path

    tool = Path(__file__).resolve().parents[1] / "tools" / "tee_run.py"
    log = tmp_path / "install.log"
    child = ("import sys; print('Collecting demucs'); "
             "sys.stdout.write('10%\\r50%\\r100%\\n'); "
             "print('ERROR: no matching distribution', file=sys.stderr); "
             "sys.exit(3)")
    done = subprocess.run([sys.executable, str(tool), str(log), "--",
                           sys.executable, "-c", child],
                          capture_output=True)
    assert done.returncode == 3
    assert b"Collecting demucs" in done.stdout
    text = log.read_text(encoding="utf-8")
    assert "Collecting demucs" in text
    assert "ERROR: no matching distribution" in text
    rows = text.splitlines()
    assert "100%" in rows and "10%" not in "".join(
        row for row in rows if not row.startswith("[")), \
        "only a bar's last state"
    assert "[exit 3]" in text and "> " in text


def test_every_install_step_that_can_fail_is_logged() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "KaraokeToolGUI.bat").read_text(
        encoding="utf-8", errors="replace")
    assert 'set "LOG=%LOGDIR%\\install.log"' in text
    for row in text.splitlines():
        stripped = row.strip()
        if " -m pip install" in stripped or "roformer_separate.py" in \
                stripped and "--download" in stripped:
            assert "%TEE%" in stripped, stripped
        if stripped.startswith("echo Let op"):
            raise AssertionError("a warning only on screen: " + stripped)
    assert ":say" in text and '>> "%LOG%" echo(%*' in text


# -- v1.0.16: what the install log showed -----------------------------------

def _roformer_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "tools" / \
        "roformer_separate.py"
    spec = importlib.util.spec_from_file_location("roformer_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_threshold_is_one_the_library_accepts() -> None:
    """audio-separator 0.47 refuses a normalisation threshold above 1.0;
    v1.0.15 handed it 1e6 and every Roformer separation stopped."""
    script = _roformer_script()
    assert 0 < script.NORMALISATION_THRESHOLD <= 1.0


def test_the_library_normalisation_leaves_the_level(monkeypatch) -> None:
    import sys
    import types

    calls = []

    def normalize(wave, max_peak=1.0, min_peak=None):
        calls.append(max_peak)
        return np.asarray(wave) * 0.5

    spec_utils = types.ModuleType("spec_utils")
    spec_utils.normalize = normalize
    package = types.ModuleType("uvr_lib_v5")
    package.spec_utils = spec_utils
    for name, module in (
            ("audio_separator", types.ModuleType("audio_separator")),
            ("audio_separator.separator",
             types.ModuleType("audio_separator.separator")),
            ("audio_separator.separator.uvr_lib_v5", package),
            ("audio_separator.separator.uvr_lib_v5.spec_utils",
             spec_utils)):
        monkeypatch.setitem(sys.modules, name, module)
    script = _roformer_script()
    assert script._keep_levels()
    wave = np.array([1.2, -1.1, 0.3])
    assert spec_utils.normalize(wave, max_peak=1.0) == pytest.approx(wave)
    assert calls == []
    # Broken data still goes to the library's own checks.
    spec_utils.normalize(np.array([]), max_peak=1.0)
    assert calls == [1.0]


def test_the_night_tries_one_real_separation_before_it_starts() -> None:
    """v1.0.16: an environment that imports but cannot separate (the
    refused threshold) is found out before the first song, and the
    Roformer ways are then skipped with the reason instead of failing
    song after song."""
    import inspect

    from modules import separation_trial

    source = inspect.getsource(separation_trial.run)
    assert "roformer_selftest()" in source
    assert source.index("roformer_selftest()") < source.index("Steps(")
    # v1.0.23: a blend with a Roformer part goes with them.
    assert '"roformer" not in separation.backends(way.way)' in source
