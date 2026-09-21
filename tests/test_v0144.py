"""Tests for v0.144.0.

B487 the outline is on every line, B488 an empty block still counts as a
block, B489 an uncoupled original sentence goes between its neighbours,
B490 "overwrite" takes the last video, B491 1.5.11e is off, B492/B493/
B494 the pause inside a sentence, B495 a second script asks which
language, B496 sentences fetched back from the original, B497 refitting
the syllables within the sentences.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np

from modules import pipeline, timing, video


def _source_of(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# B487 - the outline on every line
# --------------------------------------------------------------------------

def test_a_line_that_is_not_active_gets_an_outline_too() -> None:
    """At B477 I read "a sentence that is done need not stand out any
    more" as "no outline", and those are exactly the lines that vanish
    against a background photo."""
    source = inspect.getsource(video._draw_line)
    assert "before_edge = after_edge = None" not in source
    assert 'before_edge = after_edge = palette.get("outline_" + past_key)' \
        in source


def test_the_pause_dots_and_the_titles_get_one_as_well() -> None:
    source = _source_of(video)
    assert "stroke_width=(stroke if edge is not None else 0)" in source
    assert 'outline=palette.get("outline_" + title_key)' in source
    assert 'outline=palette.get("outline_na")' in source


def test_the_rows_of_a_broken_sentence_keep_room_for_the_outline() -> None:
    """The rows of a broken sentence sit tight on purpose; an outline
    grows on both sides and would push them together."""
    from PIL import ImageFont

    for name in ("Anton-Regular.ttf", "DejaVuSans-Bold.ttf"):
        path = Path(video.__file__).resolve().parents[1] / "assets" / \
            "fonts" / name
        if not path.exists():
            continue
        font = ImageFont.truetype(str(path), size=72)
        assert video._row_air(font) >= 2 * video._stroke_width(font) + 2
        assert video._line_gap(font) >= 2 * video._stroke_width(font) + 2


def test_every_line_really_has_a_border_in_the_picture() -> None:
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from PIL import Image

    lines = [TextLine(0, "al gezongen", False), TextLine(1, "nu bezig", False),
             TextLine(2, "komt nog", False)]
    spans = {0: (2.0, 4.0), 1: (5.0, 7.0), 2: (8.0, 10.0)}
    timed = sorted(generate_skeleton(lines, spans), key=lambda l: l.index)
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    background = Image.new("RGB", (1280, 720), (60, 130, 70))
    font = video._fit_body_font("", timed, 1280, int(720 * 0.06))
    frame = video._compose_frame(6.0, timed, 1.0, 600.0, 1280, 720, font,
                                 font, logo, "T", video._DEFAULT_COLORS,
                                 "", None, background)
    array = np.asarray(frame).astype(int)
    # The counter colour of white and of grey is black; without an
    # outline no black shows up at all (the background is green).
    black = (np.abs(array - np.array([0, 0, 0])).sum(axis=2) < 40)
    rows = np.nonzero(black.any(axis=1))[0]
    assert len(rows) > 0, "not a single outline in the picture"
    assert rows.max() - rows.min() > 200, "outline on one line only"


# --------------------------------------------------------------------------
# B488/B489 - the coupling and the lane
# --------------------------------------------------------------------------

def test_an_empty_block_still_counts_as_a_block() -> None:
    """A block made up of nothing but whole [bg] lines dropped out, and
    then every block after it shifted."""
    source = _source_of(pipeline)
    assert "blocks_in_text = (max((line.block for line in karaoke_lines)" \
        in source
    assert "karaoke_blocks = [b for b in karaoke_blocks if b]" not in source


def test_the_coupling_stays_one_on_one_with_an_empty_last_block() -> None:
    from modules.karaoke_text import TextLine

    original = [[(float(i), float(i) + 1.0, True) for i in range(4)],
                [(10.0, 11.0, True), (11.0, 12.0, True)]]
    karaoke = [[TextLine(i, f"regel {i}", False, block=0) for i in range(4)],
               []]
    _timed, _q, mapping = timing.couple_timing(karaoke, original,
                                               duration=20.0)
    assert mapping == {0: 0, 1: 1, 2: 2, 3: 3}


def test_an_uncoupled_sentence_goes_between_its_neighbours() -> None:
    items = [{"start": 10.0, "end": 12.0, "rows": [0]},
             {"start": 2.0, "end": 3.0, "rows": []},
             {"start": 16.0, "end": 18.0, "rows": [2]}]
    pipeline.place_between_neighbours(items)
    assert 12.0 <= items[1]["start"] < items[1]["end"] <= 16.0


def test_it_leaves_a_lane_that_is_wholly_coupled_alone() -> None:
    items = [{"start": 1.0, "end": 2.0, "rows": [0]},
             {"start": 3.0, "end": 4.0, "rows": [1]}]
    before = [dict(item) for item in items]
    pipeline.place_between_neighbours(items)
    assert items == before


def test_a_sentence_at_the_head_or_tail_still_gets_a_place() -> None:
    items = [{"start": 99.0, "end": 100.0, "rows": []},
             {"start": 10.0, "end": 12.0, "rows": [1]},
             {"start": 0.0, "end": 1.0, "rows": []}]
    pipeline.place_between_neighbours(items)
    assert items[0]["end"] <= 10.0
    assert items[2]["start"] >= 12.0


# --------------------------------------------------------------------------
# B490/B491
# --------------------------------------------------------------------------

def test_overwrite_takes_the_last_video_not_the_first() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._ask_video_exists)
    assert "existing_videos(self._context, like=target)" in source
    assert "newest = existing[-1] if existing else target" in source
    assert "return newest" in source


def test_overwrite_stays_within_its_own_family(tmp_path) -> None:
    """``Titel_voc_ori.mp4`` is a different render (B271); it must not
    count as the "newest" of ``Titel.mp4``."""
    context = _context(tmp_path)
    for name in ("Titel.mp4", "Titel_2.mp4", "Titel_3.mp4",
                 "Titel_voc_ori.mp4", "Ander Lied.mp4"):
        (context.paths.output_dir / name).write_bytes(b"x")
    family = pipeline.existing_videos(
        context, like=context.paths.output_dir / "Titel.mp4")
    assert [p.name for p in family] == ["Titel.mp4", "Titel_2.mp4",
                                        "Titel_3.mp4"]
    # Without a filter it stays the whole folder, because that is what
    # "Open video" has to offer.
    assert len(pipeline.existing_videos(context)) == 5


def test_the_gain_trial_is_off() -> None:
    from modules import test_panel

    codes = {trial.code: trial for trial in test_panel.HEAVY_TRIALS}
    assert codes["1.5.11e"].off and codes["1.5.11e"].reason == "gain_answered"


# --------------------------------------------------------------------------
# B492/B493/B494 - the pause inside a sentence
# --------------------------------------------------------------------------

def test_the_trim_measures_the_last_singing_not_the_first() -> None:
    """``active_end`` stops at the silent gap before the last singing
    episode, and that cuts a sentence with a pause of its own in two."""
    source = _source_of(pipeline)
    assert "ae = rhythm.last_energy(vocals, start, end)" in source
    assert "def last_energy(" in _source_of(
        __import__("modules.rhythm", fromlist=["x"]))


def test_the_pause_decides_where_the_sentence_splits() -> None:
    line = timing.TimedLine(
        index=0, text="Lied Q … kom maar", crowd=False,
        syllables=(timing.Syllable("rei", 0.0, 0.5),
                   timing.Syllable("ger", 0.5, 1.0),
                   timing.Syllable(" rock", 1.0, 1.5),
                   timing.Syllable(" …", 1.5, 2.0),
                   timing.Syllable(" kom", 2.0, 2.5),
                   timing.Syllable(" maar", 2.5, 3.0)))
    out = timing.distribute_over_windows(line, [(0.0, 1.2), (2.4, 3.0)])
    words = timing.word_spans(out.syllables)
    # "zanger" and "rock" in the first window, "kom" and "maar" in the
    # second; the pause lies between them.
    assert words[0][1] >= 0.0 and words[1][2] <= 1.2 + 1e-6
    assert words[4][1] >= 2.4 - 1e-6


def test_stretching_a_line_keeps_the_proportions() -> None:
    """Making every syllable the same width throws away the measured
    pause - exactly the complaint that a stretched line no longer has
    good phonetic timing."""
    line = timing.TimedLine(
        index=0, text="a b", crowd=False,
        syllables=(timing.Syllable("a", 0.0, 0.2),
                   timing.Syllable(" b", 1.8, 2.0)))
    out = timing._reflow_line(line, 0.0, 4.0)
    widths = [round(s.end - s.start, 3) for s in out.syllables]
    assert widths[0] == widths[1] == 0.4, widths
    assert out.syllables[1].start > 3.0, "the gap stays a gap"


# --------------------------------------------------------------------------
# B495 - a second script
# --------------------------------------------------------------------------

def test_a_passage_in_another_script_is_recognised() -> None:
    assert pipeline.second_language("착각 하지 마\n누가 누군지\n") == ("ko", 5)
    assert pipeline.second_language("착각 하지 마\nNoo-ga noo-goon-ji\n") \
        == ("ko", 3)


def test_one_foreign_word_is_not_a_second_language() -> None:
    assert pipeline.second_language("Een liedje met 착각 erin\nnormaal\n") \
        is None


def test_a_phonetic_transliteration_is_not_recognised() -> None:
    """In "Lied R" the Korean is written in Latin letters; there is
    nothing to see there, and that is as it should be."""
    assert pipeline.second_language(
        "Chak-kak ha-ji ma\nNoo-ga noo-goon-ji\n") is None


def test_the_question_comes_before_the_transcription() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._ensure_language_choice)
    assert "second = pipeline.second_language_of(context)" in source
    assert "_ask_second_language" in source


# --------------------------------------------------------------------------
# B496 - sentences fetched back from the original
# --------------------------------------------------------------------------

def _context(tmp_path, song="Lied"):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=song)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


def test_the_marking_survives_and_becomes_a_fragment(tmp_path) -> None:
    context = _context(tmp_path)
    lines = [timing.TimedLine(
        index=i, text=f"zin {i}", crowd=False,
        syllables=(timing.Syllable(" zin", i * 2.0, i * 2.0 + 1.0),
                   timing.Syllable(f" {i}", i * 2.0 + 1.0, i * 2.0 + 2.0)))
        for i in range(3)]
    timing.save_timing(lines, context.paths.timing_file)
    pipeline.set_restore_lines(context, [1])
    assert pipeline.restore_lines(context) == (1,)
    fragments = pipeline.restore_fragments(context)
    assert len(fragments) == 1
    assert fragments[0].start == 2.0 and fragments[0].end == 4.0
    assert pipeline.line_of_restore_label(fragments[0].label) == 1


def test_the_window_follows_the_sentence(tmp_path) -> None:
    """Derived on purpose and not pinned down: move the sentence and
    the piece of the original moves with it."""
    context = _context(tmp_path)
    line = timing.TimedLine(
        index=0, text="zin", crowd=False,
        syllables=(timing.Syllable("zin", 5.0, 6.0),))
    timing.save_timing([line], context.paths.timing_file)
    pipeline.set_restore_lines(context, [0])
    assert pipeline.restore_fragments(context)[0].start == 5.0
    moved = timing.TimedLine(
        index=0, text="zin", crowd=False,
        syllables=(timing.Syllable("zin", 9.0, 10.0),))
    timing.save_timing([moved], context.paths.timing_file)
    assert pipeline.restore_fragments(context)[0].start == 9.0


def test_a_hand_drawn_block_is_not_thrown_away(tmp_path) -> None:
    context = _context(tmp_path)
    pipeline.set_restore_fragments(context, [(1.0, 2.0, "met de hand")])
    assert [f.label for f in pipeline.restore_fragments(context)] == \
        ["met de hand"]


def test_it_replaces_the_karaoke_there_and_does_not_mix() -> None:
    """The user was clear about it: replace one to one, no mixing."""
    from modules import karaoke

    doc = inspect.getdoc(karaoke.apply_restore) or ""
    assert "REPLACES" in doc


def test_the_marked_sentence_has_its_own_colour_in_both_editors() -> None:
    from modules import damping_editor, timing_editor

    assert "_LINE_BLOCK" in _source_of(damping_editor)
    assert damping_editor._LINE_PREFIX == pipeline.LINE_RESTORE_PREFIX
    editor = _source_of(timing_editor)
    # B499: the marking belongs to the ORIGINAL that is fetched back,
    # so that lane turns blue; the karaoke text stays as it is.
    assert "_ORIG_RESTORE" in editor
    assert 'self._lines[r].get("restore")' in editor
    assert "def toggle_selected_restore" in editor


def test_the_chain_knows_about_it() -> None:
    from modules import dependencies

    assert "restore_lines" in dependencies.ARTEFACTS
    assert "restore_lines" in dependencies.ARTEFACTS["karaoke"].sources
    # Deliberately not hung on the timing: every timing change would
    # then invalidate the edited karaoke, and that is on purpose not so.
    assert "output:timing" not in dependencies.ARTEFACTS[
        "restore_lines"].sources


def test_the_marking_survives_a_reset() -> None:
    from modules import timing_editor

    source = inspect.getsource(timing_editor.TimingEditorDialog._reset)
    assert 'line.get("restore")' in source
    assert 'line["restore"] = int(line["index"]) in marked' in source


def test_deleting_a_blue_block_in_step_four_unmarks_the_sentence() -> None:
    source = inspect.getsource(pipeline.apply_manual_damping)
    assert "kept_lines = {line_of_restore_label(label)" in source
    assert "set_restore_lines(context," in source


def test_the_label_carries_the_line_number() -> None:
    assert pipeline.line_of_restore_label("zin 12: hallo") == 12
    assert pipeline.line_of_restore_label("Terug uit origineel 1") is None

