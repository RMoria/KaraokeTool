"""Tests for v0.146.0.

B506 the manual couplings are written down by what they MEAN, an empty
pin is visible and can be given back to the automatic coupling, B507 an
inline ``[bg]`` piece no longer decides how long its sentence is and
gets a block of its own in every view, B508 the original lane runs the
same checks and the same clock as the karaoke lane, B509 a whole
``[bg]`` line gets its own counterpart in the lyrics, B510 background
vocals stay out of the render on their own flag instead of on
"switched off", B511 the outline colours of the four standard colours,
B512 the answered trials are gone with their subject.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import (pipeline, song_text, timing, timing_checks,  # noqa: E402
                     video)
from modules.config import default_config  # noqa: E402
from modules.filesystem import (ProjectPaths, ProjectStore,  # noqa: E402
                                ensure_directories)


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _source_of(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


def _context(tmp_path):
    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    return pipeline.AppContext(config=default_config(), paths=paths,
                               store=ProjectStore(paths.project_file))


def _lyrics(*words):
    """``("line/text", ...)`` into LyricWords."""
    out = []
    for index, item in enumerate(words):
        line, _, text = item.partition("/")
        out.append(song_text.LyricWord(index, text, int(line)))
    return tuple(out)


# --------------------------------------------------------------------------
# B506 - a pin says what it means
# --------------------------------------------------------------------------

_OLD = _lyrics("0/So", "0/come", "0/up", "1/That", "1/Prima", "1/donna")
_TRANS = [("come", 10.0, 10.4), ("up", 10.4, 10.8), ("prima", 12.0, 12.5)]


def test_the_first_time_nothing_is_relocated(tmp_path) -> None:
    """There is no description yet of what the pins meant, so what
    stands there now IS the truth. Guessing would freeze a guess."""
    context = _context(tmp_path)
    pins = {1: [0], 2: [1], 4: []}
    out = pipeline.anchor_pins(context, pins, _OLD, _TRANS)
    assert out == pins
    step = context.store.get_step("word_coupling")
    assert len(step["marks"]) == 3
    assert step["lists"]["lyrics"] and step["lists"]["transcript"]


def test_an_unchanged_list_leaves_the_numbers_alone(tmp_path) -> None:
    context = _context(tmp_path)
    pipeline.anchor_pins(context, {1: [0]}, _OLD, _TRANS)
    before = context.store.get_step("word_coupling")
    assert pipeline.anchor_pins(context, {1: [0]}, _OLD, _TRANS) == {1: [0]}
    assert context.store.get_step("word_coupling")["marks"] == before["marks"]


def test_a_pin_survives_a_shifted_word_list(tmp_path) -> None:
    """The heart of B506. At "Lied R" ``[bg]Twee-uh[/bg]`` became two
    tokens in twelve places and every pin after it shifted - silently,
    because a pin keeps working, it just means another word."""
    context = _context(tmp_path)
    pipeline.anchor_pins(context, {1: [0], 2: [1]}, _OLD, _TRANS)
    # Two words appear in front; every number shifts by two.
    shifted = _lyrics("0/Twee", "0/uh", "0/So", "0/come", "0/up",
                      "1/That", "1/Prima", "1/donna")
    out = pipeline.anchor_pins(context, {1: [0], 2: [1]}, shifted, _TRANS)
    assert out == {3: [0], 4: [1]}


def test_an_empty_pin_survives_on_its_own(tmp_path) -> None:
    """"I uncoupled this word" is a decision about the lyrics word and
    needs no found word to be relocated."""
    context = _context(tmp_path)
    pipeline.anchor_pins(context, {4: []}, _OLD, _TRANS)
    shifted = _lyrics("0/Twee", "0/So", "0/come", "0/up", "1/That",
                      "1/Prima", "1/donna")
    assert pipeline.anchor_pins(context, {4: []}, shifted, _TRANS) == {5: []}


def test_a_word_that_is_gone_is_let_go(tmp_path, caplog) -> None:
    """Letting go with a log line beats landing on another word."""
    import logging

    context = _context(tmp_path)
    pipeline.anchor_pins(context, {4: []}, _OLD, _TRANS)
    without = _lyrics("0/So", "0/come", "0/up", "1/That", "1/donna")
    with caplog.at_level(logging.INFO):
        assert pipeline.anchor_pins(context, {4: []}, without, _TRANS) == {}
    assert any("losgelaten" in record.getMessage()
               or "let go" in record.getMessage()
               for record in caplog.records)


def test_the_same_word_twice_on_a_line_keeps_them_apart(tmp_path) -> None:
    context = _context(tmp_path)
    twice = _lyrics("0/na", "0/na", "0/na")
    pipeline.anchor_pins(context, {2: []}, twice, _TRANS)
    langer = _lyrics("0/hey", "0/na", "0/na", "0/na")
    assert pipeline.anchor_pins(context, {2: []}, langer, _TRANS) == {3: []}


def test_a_target_that_moved_a_little_is_found_back(tmp_path) -> None:
    context = _context(tmp_path)
    pipeline.anchor_pins(context, {1: [0]}, _OLD, _TRANS)
    moved = [("come", 10.1, 10.5), ("up", 10.5, 10.9), ("prima", 12.0, 12.5)]
    assert pipeline.anchor_pins(context, {1: [0]}, _OLD, moved) == {1: [0]}


def test_a_target_that_is_really_gone_lets_the_pin_go(tmp_path) -> None:
    context = _context(tmp_path)
    pipeline.anchor_pins(context, {1: [0]}, _OLD, _TRANS)
    other = [("iets", 40.0, 40.4), ("anders", 40.4, 40.8)]
    assert pipeline.anchor_pins(context, {1: [0]}, _OLD, other) == {}


def test_saving_by_hand_clears_the_description(tmp_path) -> None:
    """After a manual save the pins mean what they point at right now,
    so the next read adopts that instead of relocating onto it."""
    context = _context(tmp_path)
    pipeline.anchor_pins(context, {1: [0]}, _OLD, _TRANS)
    pipeline.set_word_pins(context, {2: [1]})
    step = context.store.get_step("word_coupling")
    assert "marks" not in step and "lists" not in step
    assert pipeline.anchor_pins(context, {2: [1]}, _OLD, _TRANS) == {2: [1]}


def test_an_empty_pin_is_visible_in_the_editor() -> None:
    """Up to v0.145.0 it counted as "coupled", so nothing on screen said
    why an obviously matching word stayed loose."""
    source = inspect.getsource(pipeline.word_coupling_view)
    assert 'w["status"] = "manually_uncoupled"' in source
    assert 'w["status"] = "background"' in source
    from modules.coupling_editor import _STATUS_STYLE
    assert "manually_uncoupled" in _STATUS_STYLE
    assert "background" in _STATUS_STYLE


def test_a_word_can_be_given_back_to_the_automatic_coupling(qapp) -> None:
    from modules.coupling_editor import CouplingCanvas

    words = [{"index": 0, "text": "up", "line": 0, "transcript_indices": [],
              "found": None, "sim": 0.0, "pinned": True,
              "status": "manually_uncoupled"}]
    saved: list = []
    canvas = CouplingCanvas([("up", 1.0, 1.4)], words, saved.append)
    canvas._sel_bot = 0
    assert canvas.release_selected() is True
    assert saved and saved[-1] == {}
    assert words[0]["status"] == ""
    # Nothing selected, nothing to release.
    canvas._sel_bot = None
    assert canvas.release_selected() is False


# --------------------------------------------------------------------------
# B507 - the [bg] piece does not decide how long a sentence is
# --------------------------------------------------------------------------

def _line_dict(index, pieces):
    return {"index": index, "text": "een zin", "crowd": False, "block": 0,
            "syllables": [{"text": text, "start": start, "end": end,
                           "held": False, "stress": False, "crowd": False,
                           "bg": bg}
                          for text, start, end, bg in pieces]}


_WITH_BG = _line_dict(0, [("een", 1.0, 1.5, False), (" zin", 1.5, 2.0, False),
                          (" Nee", 2.0, 2.6, True)])


def test_the_sentence_ends_where_the_singing_ends() -> None:
    """This is what made the karaoke block longer than the original
    block it is coupled to: everything else already reasoned this way."""
    assert timing._dict_span(_WITH_BG) == (1.0, 2.0)


def test_the_background_piece_gets_a_block_of_its_own() -> None:
    cells = timing.editor_view_cells([_WITH_BG], "sentences")
    assert len(cells) == 2
    assert (cells[0]["start"], cells[0]["end"]) == (1.0, 2.0)
    assert cells[1]["bg"] is True and cells[1]["text"] == "Nee"
    assert (cells[1]["start"], cells[1]["end"]) == (2.0, 2.6)
    # Drawn, not dragged: it moves with the sentence it belongs to.
    assert cells[1]["rows"] == []


def test_the_block_view_shows_it_too() -> None:
    cells = timing.editor_view_cells([_WITH_BG], "blocks")
    assert [cell.get("bg", False) for cell in cells] == [False, True]
    assert (cells[0]["start"], cells[0]["end"]) == (1.0, 2.0)


def test_the_word_view_marks_it() -> None:
    cells = timing.editor_view_cells([_WITH_BG], "words")
    assert [cell["bg"] for cell in cells] == [False, False, True]
    assert cells[-1]["text"] == "Nee"


def test_a_line_that_is_all_background_keeps_its_own_span() -> None:
    """Then there is no sung part to fall back on."""
    whole = _line_dict(1, [("SPR", 5.0, 5.3, True), ("ING", 5.3, 5.6, True)])
    assert timing._dict_span(whole) == (5.0, 5.6)
    assert timing._bg_cell(whole) is None


def test_the_editor_does_not_grab_a_background_block() -> None:
    from modules import timing_editor

    source = _source_of(timing_editor)
    assert source.count('if not cel.get("rows"):') >= 2


# --------------------------------------------------------------------------
# B508 - the original lane is no back door
# --------------------------------------------------------------------------

def test_the_original_lane_runs_the_karaoke_checks() -> None:
    from modules import timing_editor

    source = inspect.getsource(timing_editor.TimingCanvas._move_original)
    assert "self._keep_in_order(rows, *new_span, anchor=mode)" in source
    assert "self._without_overlap(rows, *new_span, anchor=mode)" in source
    # And on the karaoke clock, not on the original's own duration.
    assert "limit = self._duration" in source
    assert "self._original_duration" not in source


def test_the_block_goes_back_onto_its_rows_after_every_drag() -> None:
    from modules import timing_editor

    source = _source_of(timing_editor)
    assert "def _sync_original" in source
    move = inspect.getsource(timing_editor.TimingCanvas.mouseMoveEvent)
    assert "self._mirror_to_original(rows)" in move
    assert "if single:" not in move


def test_the_editor_checks_between_the_lines_itself() -> None:
    from modules import timing_editor

    source = inspect.getsource(timing_editor.TimingCanvas._recheck)
    assert "timing_checks.line_checks(lines)" in source
    release = inspect.getsource(timing_editor.TimingCanvas.mouseReleaseEvent)
    assert "self._recheck()" in release


# --------------------------------------------------------------------------
# B509 - a whole [bg] line gets its counterpart back
# --------------------------------------------------------------------------

class _Bg:
    def __init__(self, index):
        self.index = index


def test_a_background_line_takes_the_leftover_sentence() -> None:
    detailed = [{"block": 0}, {"block": 0}, {"block": 1}, {"block": 1}]
    mapping = {0: 0, 1: 1}
    out = pipeline._couple_bg_lines(mapping, detailed, [_Bg(2), _Bg(3)])
    assert out == {0: 0, 1: 1, 2: 2, 3: 3}


def test_it_never_steps_over_a_coupled_neighbour() -> None:
    """Between the sentences of the lines before and after it - so the
    order stays intact whatever the block numbering says."""
    detailed = [{"block": 0}, {"block": 0}, {"block": 0}]
    out = pipeline._couple_bg_lines({0: 0, 2: 2}, detailed, [_Bg(1)])
    assert out[1] == 1


def test_without_a_counterpart_nothing_happens() -> None:
    out = pipeline._couple_bg_lines({0: 0}, [{"block": 0}], [_Bg(1)])
    assert out == {0: 0}


def test_a_coupled_background_line_gets_its_own_time() -> None:
    from modules.karaoke_text import TextLine

    base = timing.TimedLine(
        index=0, text="een zin", crowd=False,
        syllables=(timing.Syllable("een zin", 1.0, 2.0),))
    bg = TextLine(1, "LIED_R", False, block=0, bg=True)
    out = timing.attach_bg_lines([base], [bg], {1: (9.0, 9.5)})
    line = {item.index: item for item in out}[1]
    assert (line.start, line.end) == (9.0, 9.5)
    assert line.bg is True and line.disabled is False


def test_without_its_own_place_it_still_lies_on_its_neighbour() -> None:
    from modules.karaoke_text import TextLine

    base = timing.TimedLine(
        index=0, text="een zin", crowd=False,
        syllables=(timing.Syllable("een zin", 1.0, 2.0),))
    bg = TextLine(1, "LIED_R", False, block=0, bg=True)
    line = {item.index: item
            for item in timing.attach_bg_lines([base], [bg])}[1]
    assert (line.start, line.end) == (1.0, 2.0)


def test_background_may_lie_over_its_neighbour() -> None:
    """It CAN sound at the same time as another sentence; it need not,
    and when it does that is the right picture and not a finding."""
    one = timing.TimedLine(index=0, text="a", crowd=False,
                           syllables=(timing.Syllable("a", 1.0, 3.0),))
    two = timing.TimedLine(index=1, text="b", crowd=False, bg=True,
                           syllables=(timing.Syllable("b", 2.0, 4.0),))
    assert not timing_checks.line_checks([one, two])["overlapping_lines"]


def test_switching_off_works_on_the_pair() -> None:
    from modules import timing_editor

    source = inspect.getsource(
        timing_editor.TimingCanvas.toggle_selected_disabled)
    assert "self._sync_all_originals()" in source
    assert "self._recheck()" in source


# --------------------------------------------------------------------------
# B510 - bg is what the text says, disabled is what the user says
# --------------------------------------------------------------------------

def test_a_background_line_stays_out_of_the_render_when_switched_on() -> None:
    source = inspect.getsource(video.render_video)
    assert 'and not getattr(line, "bg", False)' in source


def test_the_flag_survives_saving_and_reading(tmp_path) -> None:
    line = timing.TimedLine(index=0, text="LIED_R", crowd=False, bg=True,
                            syllables=(timing.Syllable("LIED_R", 1.0, 2.0),))
    path = tmp_path / "timing.json"
    timing.save_timing([line], path)
    assert timing.load_timing(path)[0].bg is True


def test_the_editor_does_not_wipe_the_flag() -> None:
    from modules import timing_editor

    line = timing.TimedLine(index=0, text="LIED_R", crowd=False, bg=True,
                            syllables=(timing.Syllable("LIED_R", 1.0, 2.0),))
    assert timing_editor._from_dict(timing_editor._to_dict(line)).bg is True


def test_the_text_decides_and_can_also_unmark() -> None:
    from modules.karaoke_text import TextLine

    line = timing.TimedLine(index=0, text="LIED_R", crowd=False, bg=True,
                            syllables=(timing.Syllable("LIED_R", 1.0, 2.0),))
    plain = timing.apply_inline_crowd([line], [TextLine(0, "LIED_R", False)])
    assert plain[0].bg is False
    back = timing.apply_inline_crowd(
        plain, [TextLine(0, "LIED_R", False, bg=True)])
    assert back[0].bg is True


def test_marking_runs_without_a_single_inline_piece() -> None:
    """A text of nothing but whole [bg] lines has no inline piece at all,
    and that is exactly the case that must not be skipped."""
    source = inspect.getsource(timing.apply_inline_crowd)
    assert "if not crowd_per_index and not bg_per_index:" not in source


# --------------------------------------------------------------------------
# B511 - the outline colours
# --------------------------------------------------------------------------

def test_the_four_standard_colours_have_a_fixed_outline() -> None:
    assert video.contra_colour((255, 255, 255)) == (0, 0, 0)
    assert video.contra_colour((158, 158, 158)) == (0, 0, 0)
    assert video.contra_colour((229, 57, 53)) == (0, 0, 0)
    assert video.contra_colour((60, 176, 67)) == (255, 255, 255)


def test_a_colour_of_your_own_still_follows_the_brightness() -> None:
    assert video.contra_colour((10, 10, 10)) == (255, 255, 255)
    assert video.contra_colour((250, 250, 200)) == (0, 0, 0)


def test_the_palette_follows_the_table() -> None:
    from modules.config import VideoSettings

    palette = video.colors_from_settings(VideoSettings())
    assert palette["outline_zang"] == (255, 255, 255)
    assert palette["outline_crowd"] == (0, 0, 0)
    assert palette["outline_voor"] == (0, 0, 0)
    assert palette["outline_na"] == (0, 0, 0)


def test_a_stored_outline_is_emptied_once(tmp_path) -> None:
    """A filled-in value beats the table, so a stored one would keep the
    old picture alive."""
    import json

    from modules import config as config_module

    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "search_words": ["oeh"], "video": {"outline_before": "#000000",
                                      "outline_vocal": "#123456"}}),
        encoding="utf-8")
    loaded = config_module.load_config(path)
    assert loaded.video.outline_before == ""
    assert loaded.video.outline_vocal == ""
    # And only once: the marker is written on saving.
    config_module.save_config(loaded, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["outline_reset"] is True


def test_a_choice_made_after_the_wipe_is_kept(tmp_path) -> None:
    import json
    from dataclasses import replace

    from modules import config as config_module

    path = tmp_path / "config.json"
    config = default_config()
    config = replace(config, video=replace(config.video,
                                           outline_vocal="#FF00FF"))
    config_module.save_config(config, path)
    assert config_module.load_config(path).video.outline_vocal == "#FF00FF"
    assert json.loads(path.read_text(encoding="utf-8"))["outline_reset"]


# --------------------------------------------------------------------------
# B512 - what was answered is gone with its subject
# --------------------------------------------------------------------------

def test_the_adjust_button_and_its_measurement_are_gone() -> None:
    from modules import test_panel, timing_editor

    assert not hasattr(pipeline, "refit_syllables")
    assert not hasattr(test_panel, "refit_trial")
    assert "refit" not in _source_of(timing_editor)
    codes = [trial.code for trial in test_panel.HEAVY_TRIALS]
    assert "1.5.11f" not in codes and "1.5.11c" not in codes


# --------------------------------------------------------------------------
# The kritische herlezing: six holes that were found before delivery
# --------------------------------------------------------------------------

def test_saving_keeps_both_layout_markers(tmp_path) -> None:
    """The likeliest way "Lied R" drifted: ``set_word_pins`` wrote only
    the transcript marker, so the B417 conversion ran again at the next
    read on keys that were already converted - two words per save,
    compounding."""
    context = _context(tmp_path)
    (context.paths.input_dir / song_text.LYRICS_FILENAME).write_text(
        "Ik loop hier\nna-na-na hey\ntot het einde nu dan\n",
        encoding="utf-8")
    pins = {6: []}
    for _round in range(3):
        pipeline.set_word_pins(context, pins)
        pins = pipeline.migrate_lyric_pins(context)
    assert pins == {6: []}


def test_a_blank_line_costs_no_single_pin(tmp_path) -> None:
    """``LyricWord.line`` counts blank lines too, so one blank line
    renumbers the rest of the song while not a word moves."""
    context = _context(tmp_path)
    before = _lyrics("0/So", "0/come", "2/That", "2/Prima")
    pipeline.anchor_pins(context, {3: []}, before, _TRANS)
    after = _lyrics("0/So", "0/come", "4/That", "4/Prima")
    assert pipeline.anchor_pins(context, {3: []}, after, _TRANS) == {3: []}


def test_two_identical_words_do_not_land_on_the_same_one(tmp_path) -> None:
    """Three times "na" that all shifted a little used to collapse onto
    one found word: two lyrics words then get the same time span."""
    context = _context(tmp_path)
    words = _lyrics("0/na", "0/na", "0/na")
    trans = [("na", 1.0, 1.2), ("na", 1.3, 1.5), ("na", 1.6, 1.8)]
    pipeline.anchor_pins(context, {0: [0], 1: [1], 2: [2]}, words, trans)
    moved = [("na", 1.15, 1.35), ("na", 1.45, 1.65), ("na", 1.75, 1.95)]
    out = pipeline.anchor_pins(context, {0: [0], 1: [1], 2: [2]},
                               words, moved)
    assert out == {0: [0], 1: [1], 2: [2]}
    assert len({tuple(v) for v in out.values()}) == 3


def test_a_pin_that_cannot_be_described_is_counted(tmp_path, caplog) -> None:
    """It used to be kept in the numbers without a description, and then
    it vanished at the next relocation while the log said nothing."""
    import logging

    context = _context(tmp_path)
    with caplog.at_level(logging.INFO):
        out = pipeline.anchor_pins(context, {1: [0], 2: [99]}, _OLD, _TRANS)
    assert out == {1: [0]}
    assert any("losgelaten" in record.getMessage()
               or "let go" in record.getMessage()
               for record in caplog.records)


def test_a_background_line_keeps_its_own_time_through_the_cleanup() -> None:
    """``sanitize_timing`` pushed every line forward on ``prev_end``,
    which handed the coupled sentence of B509 straight back."""
    def line(index, start, end, bg=False):
        return timing.TimedLine(
            index=index, text=f"zin {index}", crowd=False, bg=bg,
            quality="high",
            syllables=(timing.Syllable("zin", start, end),))

    out = timing.sanitize_timing(
        [line(0, 1.0, 3.0), line(1, 4.0, 6.0, bg=True),
         line(2, 3.2, 5.0), line(3, 30.0, 31.5, bg=True)],
        song_duration=40.0)
    by_index = {item.index: item for item in out}
    assert (by_index[1].start, by_index[1].end) == (4.0, 6.0)
    assert (by_index[3].start, by_index[3].end) == (30.0, 31.5)
    # And they push nothing forward either.
    assert by_index[2].start < 4.0


def test_a_hand_correction_on_the_sentence_wins() -> None:
    """A lyrics sentence the user placed by hand keeps that place, also
    where a bg line now hangs on it."""
    source = inspect.getsource(pipeline.build_coupling)
    assert "def _original_span(index: int)" in source
    assert "own_spans[line.index] = _original_span(oi)" in source
    assert source.index("overrides = original_overrides(context)") \
        < source.index("_couple_bg_lines")


# --------------------------------------------------------------------------
# Tweede herlezing: nine more holes, closed before delivery
# --------------------------------------------------------------------------

def _tl(index, start, end, bg=False, crowd=False, disabled=False):
    return timing.TimedLine(
        index=index, text=f"zin {index}", crowd=crowd, bg=bg,
        disabled=disabled, quality="high",
        syllables=(timing.Syllable("zin", start, end),))


def test_the_repair_leaves_a_background_line_alone() -> None:
    """It cut a sung line back by a whole second to remove an overlap
    that B510 had just declared correct."""
    lines = (_tl(0, 1.0, 5.0), _tl(1, 4.0, 6.0, bg=True), _tl(2, 5.5, 7.0))
    fixed, count = timing.repair_line_edges(lines)
    assert count == 0
    assert [(round(x.start, 3), round(x.end, 3)) for x in fixed] == \
        [(1.0, 5.0), (4.0, 6.0), (5.5, 7.0)]


def test_the_monotonic_guard_leaves_it_alone_too() -> None:
    """One save through the timing editor was enough to pull the
    background line off the sentence it sings over."""
    out = timing.enforce_monotonic(
        (_tl(0, 1.0, 5.0), _tl(1, 4.0, 6.0, bg=True), _tl(2, 5.5, 7.0)))
    assert [(round(x.start, 3), round(x.end, 3)) for x in out] == \
        [(1.0, 5.0), (4.0, 6.0), (5.5, 7.0)]


def test_a_text_change_does_not_wipe_the_background_flag() -> None:
    from modules.karaoke_text import TextLine

    old = [_tl(0, 1.0, 2.0, bg=True)]
    new = [TextLine(0, "zin 0", False, bg=True)]
    assert timing.carry_over(old, new)[0].bg is True
    # And a line that is no longer bg in the text loses it.
    plain = timing.carry_over(old, [TextLine(0, "zin 0", False)])
    assert plain[0].bg is False


def test_a_rewritten_line_keeps_what_the_text_says() -> None:
    from modules.karaoke_text import TextLine

    line = timing._reworded(_tl(0, 1.0, 2.0), TextLine(0, "iets", False,
                                                       bg=True), 1.0, 2.0)
    assert line.bg is True


def test_a_background_line_is_no_wall_in_the_editor(qapp) -> None:
    """The editor refused a move that ``line_checks`` calls correct -
    and it did so exactly where that background line is visible."""
    import numpy as np

    from modules import timing_editor

    lines = [timing_editor._to_dict(_tl(0, 1.0, 2.0)),
             timing_editor._to_dict(_tl(1, 3.0, 4.0, bg=True)),
             timing_editor._to_dict(_tl(2, 6.0, 7.0))]
    canvas = timing_editor.TimingCanvas(
        np.zeros(10), None, 10.0, lines, lambda *_a: None)
    assert canvas._without_overlap([0], 1.0, 5.0, anchor="rechts") \
        == (1.0, 5.0)
    assert canvas._skippable(1) is True


def test_re_enabling_puts_every_block_back_on_its_rows() -> None:
    """``_reenable_fit`` shortens the NEIGHBOURS as well, and those
    blocks stayed behind."""
    from modules import timing_editor

    source = inspect.getsource(
        timing_editor.TimingCanvas.toggle_selected_disabled)
    assert "self._sync_all_originals()" in source
    assert "def _sync_all_originals" in _source_of(timing_editor)


def test_the_original_lane_skips_a_neighbour_that_bounds_nothing() -> None:
    from modules import timing_editor

    source = inspect.getsource(timing_editor.TimingCanvas._move_original)
    assert "self._bound_original(index, before=True)" in source
    assert "self._bound_original(index, before=False" in source


def test_clicking_a_background_block_selects_nothing_and_stops_there() -> None:
    """It used to fall through to the cell three positions on - the same
    row - and then "line on/off" switched off the wrong sentence."""
    from modules import timing_editor

    source = inspect.getsource(timing_editor.TimingCanvas.mousePressEvent)
    hit = source.index('if not cel.get("rows"):')
    assert "op_een_cel = True" in source[hit:hit + 200]
    assert "break" in source[hit:hit + 200]


def test_a_whole_background_line_does_not_stretch_its_block() -> None:
    sung = _line_dict(0, [("een", 5.0, 6.0, False)])
    whole = _line_dict(1, [("SPR", 30.0, 31.0, True)])
    cells = timing.editor_view_cells([sung, whole], "blocks")
    assert (cells[0]["start"], cells[0]["end"]) == (5.0, 6.0)


def test_the_span_helper_takes_objects_too() -> None:
    """A helper that is stricter than its caller is a trap."""
    line = _tl(0, 1.0, 2.0)
    assert timing._sung_of(line) == list(line.syllables)


def test_the_wipe_really_runs_only_once(tmp_path) -> None:
    """The marker only reaches the file through ``save_config``, and
    there are runs that never save - then the setting could never be
    used again."""
    import json

    from modules import config as config_module

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"search_words": ["oeh"],
                                "video": {"outline_vocal": "#123456"}}),
                    encoding="utf-8")
    assert config_module.load_config(path).video.outline_vocal == ""
    assert json.loads(path.read_text(encoding="utf-8"))["outline_reset"]
    # A choice made after the wipe survives a plain load.
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["video"]["outline_vocal"] = "#FF00FF"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert config_module.load_config(path).video.outline_vocal == "#FF00FF"


def test_a_whole_background_line_is_drawn_as_background_but_stays_draggable(
) -> None:
    whole = _line_dict(1, [("SPR", 30.0, 31.0, True)])
    cells = timing.editor_view_cells([whole], "sentences")
    assert len(cells) == 1
    assert cells[0]["bg"] is True
    assert cells[0]["rows"] == [0]
