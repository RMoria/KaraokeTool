"""Tests for v0.142.0.

B468 the render no longer writes over the video that is already there,
B469 an own output folder no longer costs the input folders, B470 artist
and original title reach every render route, B471/B472 the editor keeps
showing the original text and every karaoke line keeps a coupling,
B473-B477 the picture (stacking, countdown, crowd, row spacing,
outline), B478 "Open video" reads the output folder, B479 the temporary
action 1.5.12 is gone, B480 background images are kept centrally, B481
the hint is out of the editor, B482 the trial cleans up after itself.
"""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import numpy as np
import pytest

from modules import pipeline, video


# --------------------------------------------------------------------------
# B468 - a failed render never costs the video that was already there
# --------------------------------------------------------------------------

def test_the_render_writes_next_to_the_target_and_moves_it_afterwards() -> None:
    source = inspect.getsource(video.render_video)
    assert 'scratch = target.with_name(' in source
    assert '        str(scratch),\n' in source
    assert "os.replace(scratch, target)" in source
    # Every way out clears up the half-finished file: beforehand, a
    # broken pipe, any other error, and an ffmpeg that fails.
    assert source.count("_discard(scratch)") == 4


def _tone(path: Path, seconds: float = 12.0) -> None:
    from modules.audio import save_wav

    rate = 22_050
    samples = (0.3 * np.sin(2 * np.pi * 220
                            * np.arange(int(seconds * rate)) / rate)
               ).astype(np.float32)
    save_wav(path, np.stack([samples, samples], axis=1), rate)


def _lines():
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    lines = [TextLine(0, "een regel", False), TextLine(1, "en nog een", False)]
    return generate_skeleton(lines, {0: (6.0, 8.0), 1: (9.0, 11.0)})


def test_a_failed_render_leaves_the_old_video_untouched(tmp_path,
                                                        monkeypatch) -> None:
    """Two of the user's videos were gone. ffmpeg wrote straight onto the
    target with ``-y`` and truncates that file the moment it starts, so a
    render that was broken off destroyed what was there."""
    from modules import ffmpeg

    if not ffmpeg.is_available():
        pytest.skip("ffmpeg not available")
    from PIL import Image

    audio = tmp_path / "karaoke.wav"
    _tone(audio)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (60, 30), (60, 176, 67, 255)).save(logo)
    target = tmp_path / "video.mp4"
    target.write_bytes(b"yesterday's video")

    real_popen = subprocess.Popen

    def broken_popen(command, **kwargs):
        # Divert only the render itself; measuring the audio (ffprobe) has
        # to keep working. This is an ffmpeg that stops at once - which is
        # what Stop does too.
        if "rawvideo" not in list(command):
            return real_popen(command, **kwargs)
        return real_popen(["ffmpeg", "-v", "error", "-x-does-not-exist"],
                          **kwargs)

    monkeypatch.setattr(subprocess, "Popen", broken_popen)
    with pytest.raises(video.VideoError):
        video.render_video(_lines(), audio, logo, "Test", target,
                           width=320, height=180, fps=5)
    assert target.read_bytes() == b"yesterday's video"
    assert not list(tmp_path.glob("*.part.mp4"))


# --------------------------------------------------------------------------
# B469 - an own output folder no longer costs every input folder
# --------------------------------------------------------------------------

def test_the_orphan_cleanup_measures_against_the_output_folder_in_use(
        tmp_path) -> None:
    from modules import filesystem

    (tmp_path / "input" / "Een Lied").mkdir(parents=True)
    elsewhere = tmp_path / "elders"
    (elsewhere / "Een Lied").mkdir(parents=True)
    # With the real output folder in hand the project is not an orphan.
    assert filesystem.prune_orphan_projects(tmp_path, elsewhere) == []
    assert (tmp_path / "input" / "Een Lied").exists()
    # Pointed at a folder the project is not in, it IS an orphan - that
    # is the existing behaviour of B112.
    (tmp_path / "output" / "Ander Lied").mkdir(parents=True)
    assert filesystem.prune_orphan_projects(tmp_path) == ["Een Lied"]


def test_an_empty_output_folder_never_means_everything_is_an_orphan(
        tmp_path) -> None:
    """Without this brake the first start after moving the output
    folder still wiped every input folder. The folder does exist by then
    - the app makes it itself one line earlier - but it is empty."""
    from modules import filesystem

    (tmp_path / "input" / "Een Lied").mkdir(parents=True)
    empty = tmp_path / "verzet"
    empty.mkdir()
    assert filesystem.prune_orphan_projects(tmp_path, empty) == []
    assert (tmp_path / "input" / "Een Lied").exists()
    assert filesystem.prune_orphan_projects(tmp_path, tmp_path / "weg") == []
    assert (tmp_path / "input" / "Een Lied").exists()


def test_the_cleanup_runs_after_the_output_folder_is_known() -> None:
    import modules

    source = (Path(modules.__file__).resolve().parents[1]
              / "KaraokeTool.py").read_text(encoding="utf-8")
    assert "prune_orphan_projects(root, paths.output_root)" in source
    assert source.index("output_base=filesystem.output_base_from(") \
        < source.index("prune_orphan_projects(")


# --------------------------------------------------------------------------
# B470 - artist and original title in every render
# --------------------------------------------------------------------------

def test_every_render_route_loads_the_titles_of_its_own_project() -> None:
    source = inspect.getsource(pipeline.run_video)
    assert "context = apply_project_titles(context)" in source
    assert (source.index("apply_project_titles")
            < source.index("sync_input_changes"))


def test_a_title_this_project_does_not_have_is_empty(tmp_path) -> None:
    """Missing keys were skipped, so the value of the previous project
    stayed put and ended up in someone else's video."""
    from dataclasses import replace

    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Twee")
    ensure_directories(paths)
    config = default_config()
    config = replace(config, video=replace(config.video,
                                           orig_artist="Van Het Vorige",
                                           orig_title="Ook Van Het Vorige"))
    context = pipeline.AppContext(paths=paths, config=config,
                                  store=ProjectStore(paths.project_file))
    context.store.set_meta("video_titles", {"karaoke_title": "Twee"})
    updated = pipeline.apply_project_titles(context)
    assert updated.config.video.karaoke_title == "Twee"
    assert updated.config.video.orig_artist == ""
    assert updated.config.video.orig_title == ""


# --------------------------------------------------------------------------
# B471/B472 - the original text stays visible, every line stays coupled
# --------------------------------------------------------------------------

def test_a_line_with_only_estimated_times_keeps_its_words() -> None:
    source = inspect.getsource(pipeline._original_lines_detailed)
    assert "del per_line_word_spans" not in source
    assert "estimated_only" in source
    assert '"words_estimated": ln in estimated_only' in source


def test_the_coupling_still_ignores_those_estimated_words() -> None:
    """B313 stands: the timing does not hang on an estimate."""
    source = inspect.getsource(pipeline.build_coupling)
    assert 'not line.get("words_estimated")' in source


def test_without_any_coupling_the_editor_still_gets_the_text(
        tmp_path) -> None:
    """An empty lane is no answer: he can then put nothing in the right
    place, which is precisely what he needs the editor for."""
    context = _context(tmp_path)
    (context.paths.input_dir / "songtekst.txt").write_text(
        "een regel\ntwee regel\ndrie regel\n", encoding="utf-8")
    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "aap noot\nmies wim\n", encoding="utf-8")
    items, mapping = pipeline.editor_originals(context)
    assert [item["text"] for item in items] == \
        ["een regel", "twee regel", "drie regel"]
    assert all(item["end"] > item["start"] for item in items)
    # Every karaoke sentence has something to hang on.
    assert set(mapping) == {0, 1}


def test_the_render_timing_keeps_its_own_road() -> None:
    """The fallback is for the editor; the timing already has one
    (``fallback_even``) and must not go trailing after a guess."""
    source = inspect.getsource(pipeline._original_lines_detailed)
    assert "log_original_times_guessed" not in source
    assert "log_original_times_guessed" in inspect.getsource(
        pipeline._originals_without_coupling)


def test_every_karaoke_line_gets_a_coupling() -> None:
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    blocks = [[TextLine(0, "een zin", False, block=0),
               TextLine(1, "Hoi!", True, block=0),
               TextLine(2, "nog een zin", False, block=0)]]
    original = [[(5.0, 7.0, True)]]
    _timed, _quality, mapping = couple_timing(blocks, original)
    assert set(mapping) == {0, 1, 2}


def test_a_line_without_a_coupling_takes_the_one_before_it() -> None:
    source = inspect.getsource(
        __import__("modules.timing", fromlist=["x"]).couple_timing)
    assert "before if before is not None else" in source


# --------------------------------------------------------------------------
# B473/B474/B475/B476 - the picture
# --------------------------------------------------------------------------

def _frame(moment, timed, height=720, width=1280):
    from PIL import Image, ImageFont

    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    return video._compose_frame(moment, timed, 1.0, 600.0, width, height,
                                font, font, logo, "T",
                                video._DEFAULT_COLORS)


def _rows_with(frame, colour, tol=40):
    array = np.asarray(frame).astype(int)
    mask = np.abs(array - np.array(colour)).sum(axis=2) < tol
    return [int(row) for row in np.nonzero(mask.any(axis=1))[0]]


def _gaps(rows: list[int]) -> list[int]:
    """The empty stretches between the blocks of text rows on screen."""
    return [current - previous
            for previous, current in zip(rows, rows[1:])
            if current - previous > 1]


def test_two_sentences_over_two_rows_do_not_draw_through_each_other() -> None:
    """The height of a broken sentence did not count when working out the
    place of the next one, and then they draw through each other."""
    from PIL import Image

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    height, width = 720, 1280
    long_line = "een tamelijk lange zin die niet op de breedte past nummer"
    lines = [TextLine(index, f"{long_line} {index}", False)
             for index in range(4)]
    spans = {0: (2.0, 4.0), 1: (4.0, 6.0), 2: (8.0, 10.0), 3: (10.0, 12.0)}
    timed = sorted(generate_skeleton(lines, spans), key=lambda l: l.index)
    font = video._fit_body_font("", timed, width, int(height * 0.06))
    assert len(video._wrap_syllables(timed[1].syllables, font,
                                     width * video._TEXT_WIDTH_FRAC)) == 2, \
        "this only says something if the sentences run over two rows"
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    # A moment between line 1 and 2, shorter than an instrumental gap:
    # slots -1, 1 and 2 are then all three in white.
    frame = video._compose_frame(7.0, timed, 1.0, 600.0, width, height,
                                 font, font, logo, "T",
                                 video._DEFAULT_COLORS)
    rows = sorted(set(_rows_with(frame, video._DEFAULT_COLORS["voor"], tol=30))
                  | set(_rows_with(frame, video._DEFAULT_COLORS["na"], tol=30)))
    # Four sentences of two rows: eight blocks, and the space within a
    # sentence should be smaller than the space between two sentences
    # (B476).
    gaps = sorted(_gaps(rows))
    assert len(gaps) == 7, f"eight blocks expected, gaps: {gaps}"
    assert max(gaps[:4]) < min(gaps[4:]), gaps


def test_the_countdown_takes_the_place_of_the_line_just_sung() -> None:
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    gap = video.GAP_MIN_S + 3.0
    lines = [TextLine(0, "gezongen", False), TextLine(1, "komt eraan", False)]
    spans = {0: (2.0, 4.0), 1: (4.0 + gap, 6.0 + gap)}
    timed = sorted(generate_skeleton(lines, spans), key=lambda l: l.index)
    frame = _frame(4.0 + gap - 0.5, timed)
    green = _rows_with(frame, video._DEFAULT_COLORS["zang"])
    assert green, "the countdown belongs on screen"
    assert abs(min(green) - int(720 * 0.34)) <= 12
    # The line just sung is no longer drawn during the gap.
    source = inspect.getsource(video._text_frame)
    assert "first_slot = ((1 if counting_down else 0) if gap_active" in source


def test_the_line_that_made_way_does_not_come_back_after_the_gap() -> None:
    """It would jump back to exactly the place where the digit stood."""
    source = inspect.getsource(video._text_frame)
    assert "after_gap = (active_index > 0" in source
    assert "else (0 if after_gap else -1))" in source


def test_the_first_countdown_of_the_song_keeps_its_own_place() -> None:
    """Before the very first text there is no sung line whose place the
    countdown could take."""
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    lines = [TextLine(0, "de eerste zin", False)]
    timed = generate_skeleton(lines, {0: (10.0, 12.0)})
    frame = _frame(9.0, timed)
    green = _rows_with(frame, video._DEFAULT_COLORS["zang"])
    assert green and abs(min(green) - int(720 * 0.18)) <= 12


def test_a_crowd_line_runs_along_in_the_flow() -> None:
    """It stayed put where every other sentence moves up; only the colour
    should differ, not the behaviour."""
    source = inspect.getsource(video.render_video)
    assert "_is_interjection" not in source
    assert "crowd_by_parent" not in source
    assert "crowd_by_parent" not in inspect.getsource(video._text_frame)


def test_the_rows_of_one_sentence_sit_closer_than_two_sentences() -> None:
    from PIL import ImageFont

    font = ImageFont.load_default()
    ascent, descent = font.getmetrics()
    class _Piece:
        def __init__(self, text): self.text = text

    rows = [[_Piece("zonder staarten")], [_Piece("ook geen staarten")]]
    # Without descenders and without accents the rows may sit closer
    # together than the full font box.
    assert video._row_tops(rows, font)[1] < ascent + descent
    assert video._line_gap(font) > 0


def test_the_two_places_that_measure_a_row_use_the_same_number() -> None:
    """Measurement and drawing could drift apart because ``+ 2`` stood in
    the code twice, separately."""
    # B541: the drawing now takes its rows and their heights from
    # ``_rows_of``, which still uses ``_row_tops`` for it - one place,
    # and it is worked out only once per render.
    assert "_row_tops(rows, font)" in inspect.getsource(video._rows_of)
    assert "_rows_of(line, font, width)" in inspect.getsource(video._draw_line)
    assert "_row_tops(rows, font)" in inspect.getsource(
        video._measure_line_height)


def test_a_sentence_that_has_been_sung_stays_grey_on_the_top_slot() -> None:
    """White means "still to come"; what lies behind us is grey. The
    line just sung turned white again as soon as it moved up."""
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    lines = [TextLine(0, "al gezongen", False),
             TextLine(1, "nu bezig", False),
             TextLine(2, "komt nog", False)]
    spans = {0: (2.0, 4.0), 1: (5.0, 7.0), 2: (8.0, 10.0)}
    timed = sorted(generate_skeleton(lines, spans), key=lambda l: l.index)
    frame = _frame(6.0, timed)
    grey = _rows_with(frame, video._DEFAULT_COLORS["na"], tol=25)
    white = _rows_with(frame, video._DEFAULT_COLORS["voor"], tol=25)
    assert grey, "the line already sung belongs in grey"
    # The grey line stands at the top, the waiting one below it.
    assert min(grey) < min(white)


# --------------------------------------------------------------------------
# B477 - the outline
# --------------------------------------------------------------------------

def test_a_light_letter_gets_a_dark_outline_and_the_other_way_round() -> None:
    """B511 took the four standard colours out of this rule; what is
    left here is the fallback for a colour the user picks himself."""
    assert video.contra_colour((10, 10, 10)) == (255, 255, 255)
    assert video.contra_colour((250, 250, 200)) == (0, 0, 0)
    assert video.contra_colour((30, 60, 200)) == (255, 255, 255)


def test_every_text_colour_has_its_own_outline() -> None:
    from modules.config import VideoSettings

    palette = video.colors_from_settings(VideoSettings())
    for key in ("voor", "zang", "na", "crowd"):
        assert palette["outline_" + key] == video.contra_colour(palette[key])
    assert "outline_background" not in palette


def test_a_filled_in_outline_wins_from_the_contra_colour() -> None:
    from dataclasses import replace

    from modules.config import VideoSettings

    settings = replace(VideoSettings(), outline_vocal="#123456")
    palette = video.colors_from_settings(settings)
    assert palette["outline_zang"] == (0x12, 0x34, 0x56)
    assert palette["outline_voor"] == video.contra_colour(palette["voor"])


def test_the_outline_is_swept_along_with_the_fill() -> None:
    source = inspect.getsource(video._draw_line)
    assert 'before_edge = palette.get("outline_" + sung_key)' in source
    assert 'after_edge = palette.get("outline_voor")' in source
    # B487 withdrew the exception for the inactive line again: every
    # line gets one.
    assert "before_edge = after_edge = None" not in source


def test_the_strip_that_is_put_back_covers_the_outline() -> None:
    source = inspect.getsource(video._draw_swept)
    assert "margin = stroke + 3" in source


def test_the_outline_stays_thin() -> None:
    from PIL import ImageFont

    for size in (20, 43, 80):
        font = video._load_font("", size=size)
        ascent, descent = font.getmetrics()
        assert 1 <= video._stroke_width(font) <= max(1, (ascent + descent) // 20)
    assert video._stroke_width(ImageFont.load_default()) >= 1


# --------------------------------------------------------------------------
# B478 - "Open video" reads the output folder of this project
# --------------------------------------------------------------------------

def test_the_number_is_read_as_a_number() -> None:
    assert pipeline.video_version(Path("Lied.mp4")) == 1
    assert pipeline.video_version(Path("Lied_3.mp4")) == 3
    assert pipeline.video_version(Path("Lied_10.mp4")) == 10


def test_the_versions_are_sorted_on_that_number(tmp_path) -> None:
    """Sorted as text, _10 comes before _3, and then the wrong one stands
    preselected."""
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Lied")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    for name in ("Lied_10.mp4", "Lied.mp4", "Lied_3.mp4"):
        (paths.output_dir / name).write_bytes(b"x")
    assert [path.name for path in pipeline.existing_videos(context)] == \
        ["Lied.mp4", "Lied_3.mp4", "Lied_10.mp4"]


def test_the_button_follows_the_project_and_carries_no_number() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._refresh_video_button)
    assert 'button.setText(t("open_video"))' in source
    assert "pipeline.existing_videos(self._context)" in source
    # On a project change it is set again.
    assert "self._refresh_video_button()" in inspect.getsource(
        gui.MainWindow._reset_project_view)


def test_the_highest_number_is_preselected() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._choose_video)
    assert "len(names) - 1" in source


# --------------------------------------------------------------------------
# B479 - the temporary action 1.5.12 is gone
# --------------------------------------------------------------------------

def test_the_rerender_action_is_gone() -> None:
    """B479 threw the temporary re-render out; B531 built it back.

    Not the same thing, and that is the point. The old one was a
    stopgap with its own numbering machinery and a ``slow`` field; it
    was removed because it had done its work. It turned out the work
    comes back - after the outlining (v0.146.0) and again after the
    silence in front of the sound (B530) - so 1.5.12 now exists as a
    proper job with a proper name, and the stopgap stays gone.
    """
    from modules import test_panel

    assert not hasattr(test_panel, "rerender_videos")
    assert not hasattr(test_panel, "RERENDER_NUMBER")
    assert not hasattr(test_panel, "_numbered_target")
    assert not hasattr(test_panel.TestAction("x", "y", "z", True, print),
                       "slow")
    action = next(a for a in test_panel.ACTIONS if a.code == "1.5.12")
    assert action.function is test_panel.rebuild_videos
    assert action.on_request


def test_its_texts_are_gone_too() -> None:
    from modules import translations

    for language in ("nl", "en"):
        keys = translations.TRANSLATIONS[language]
        for key in ("test_rerender", "rerender_none", "rerender_done",
                    "rerender_skipped", "log_rerender_failed"):
            assert key not in keys
        # B531: the new job has texts of its own, not reused ones.
        assert keys["test_rebuild"].strip()


# --------------------------------------------------------------------------
# B480 - background images kept centrally
# --------------------------------------------------------------------------

def _context(tmp_path, song="Lied"):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=song)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


def _picture(path: Path, colour=(10, 20, 30)) -> Path:
    from PIL import Image

    Image.new("RGB", (32, 18), colour).save(path)
    return path


def test_the_first_one_is_numbered_001_and_it_counts_on(tmp_path) -> None:
    context = _context(tmp_path)
    first = pipeline.store_background(
        context, _picture(tmp_path / "een.png"))
    second = pipeline.store_background(
        context, _picture(tmp_path / "twee.png", (200, 30, 40)))
    assert first.name == "background_001.png"
    assert second.name == "background_002.png"


def test_the_same_picture_does_not_land_in_the_list_twice(tmp_path) -> None:
    context = _context(tmp_path)
    source = _picture(tmp_path / "een.png")
    first = pipeline.store_background(context, source)
    assert pipeline.store_background(context, source) == first
    assert len(pipeline.stored_backgrounds(context)) == 1


def test_a_gap_in_the_numbers_is_not_filled_up_again(tmp_path) -> None:
    """Otherwise a new background takes the name of a deleted one."""
    context = _context(tmp_path)
    first = pipeline.store_background(context, _picture(tmp_path / "a.png"))
    pipeline.store_background(context, _picture(tmp_path / "b.png",
                                                (90, 90, 90)))
    pipeline.remove_stored_background(first)
    third = pipeline.store_background(context, _picture(tmp_path / "c.png",
                                                        (7, 8, 9)))
    assert third.name == "background_003.png"


def test_the_project_gets_a_copy_without_a_number(tmp_path) -> None:
    context = _context(tmp_path)
    stored = pipeline.store_background(context, _picture(tmp_path / "a.png"))
    used = pipeline.apply_background(context, stored)
    assert used.name == "background.png"
    assert pipeline.project_background(context) == used


def test_another_extension_does_not_leave_the_old_one_behind(
        tmp_path) -> None:
    """Otherwise there are two and the render cannot tell which to take."""
    from PIL import Image

    context = _context(tmp_path)
    png = pipeline.store_background(context, _picture(tmp_path / "a.png"))
    pipeline.apply_background(context, png)
    jpg_source = tmp_path / "b.jpg"
    Image.new("RGB", (32, 18), (200, 10, 10)).save(jpg_source)
    jpg = pipeline.store_background(context, jpg_source)
    pipeline.apply_background(context, jpg)
    assert [path.name for path
            in sorted(context.paths.input_dir.glob("background.*"))] == \
        ["background.jpg"]


def test_deleting_a_stored_picture_leaves_the_project_alone(
        tmp_path) -> None:
    context = _context(tmp_path)
    stored = pipeline.store_background(context, _picture(tmp_path / "a.png"))
    pipeline.apply_background(context, stored)
    pipeline.remove_stored_background(stored)
    assert pipeline.project_background(context) is not None
    assert pipeline.stored_backgrounds(context) == []


def test_the_render_takes_the_copy_of_the_project() -> None:
    source = inspect.getsource(pipeline.run_video)
    assert "background = project_background(context)" in source
    assert "background_path=str(background or \"\")" in source


def test_removing_it_from_the_project_clears_the_input_folder(
        tmp_path) -> None:
    context = _context(tmp_path)
    stored = pipeline.store_background(context, _picture(tmp_path / "a.png"))
    pipeline.apply_background(context, stored)
    pipeline.clear_background(context)
    assert pipeline.project_background(context) is None
    assert len(pipeline.stored_backgrounds(context)) == 1


def test_a_background_does_not_disturb_the_chain(tmp_path) -> None:
    """An extra file in input must not invalidate any derivative; the
    video deliberately hangs on nothing (B353)."""
    assert "input:background" not in pipeline._FINGERPRINTED
    from modules import dependencies

    assert "input:background" not in dependencies.ARTEFACTS
    assert not dependencies.ARTEFACTS["video"].sources


def test_the_button_says_what_it_does_and_is_off_without_a_picture() -> None:
    from modules import gui, translations

    source = inspect.getsource(gui.MainWindow._refresh_background_view)
    assert 't("background_none")' in source
    assert "self._bg_clear_button.setEnabled(current is not None)" in source
    assert translations.TRANSLATIONS["nl"]["background_none"] == "Geen"
    assert translations.TRANSLATIONS["nl"]["background_remove"] == \
        "Afbeelding verwijderen"


def test_the_background_stands_under_the_video_background_colour() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._build_video_colors_group)
    assert 'if key == "color_background":' in source
    assert "self._build_background_group()" in source
    tab = inspect.getsource(gui.MainWindow._build_settings_tab)
    assert "_build_background_group" not in tab


# --------------------------------------------------------------------------
# B481/B482 - the hint out of the editor, the trial cleans up
# --------------------------------------------------------------------------

def test_the_waveform_hint_is_gone() -> None:
    from modules import timing_editor, translations

    assert "editor_timing_hint" not in inspect.getsource(timing_editor)
    for language in ("nl", "en"):
        assert "editor_timing_hint" not in translations.TRANSLATIONS[language]


def test_the_trial_no_longer_leaves_folders_in_temp() -> None:
    from modules import test_panel

    source = inspect.getsource(test_panel.gain_trial)
    assert "tempfile.TemporaryDirectory(prefix=" in source
    assert "mkdtemp(" not in inspect.getsource(test_panel)


def test_every_song_writes_its_own_converted_file() -> None:
    """The voice is called ``vocals.wav`` in every project; in one
    shared scratch folder they would write over each other."""
    from modules import test_panel

    source = inspect.getsource(test_panel._at_level)
    assert 'f"{song}_{stem.stem}_' in source


def test_nothing_in_the_app_itself_makes_a_temporary_folder() -> None:
    """An ordinary function belongs in the app's own cache folder, so
    that "empty the cache" can clear it up."""
    from modules import gui, pipeline as pipeline_module, video as video_module

    for module in (gui, video_module):
        assert "tempfile" not in inspect.getsource(module)
    # In pipeline.py it is allowed only in the measuring function of 1.5.
    source = inspect.getsource(pipeline_module)
    assert source.count("tempfile") == 2
    assert "tempfile" in inspect.getsource(
        pipeline_module.fill_transcription_cache)
