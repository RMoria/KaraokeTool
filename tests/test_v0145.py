"""Tests for v0.145.0.

B499 the marking of "back from the original" moved to the original lane
and a piece moved in 1.4 is kept, B500 the logic runs once more at the
end of the automatic timing and there are checks BETWEEN the lines,
B501 the intro and outro cross-fade, B502/B503 a run of found words
without any coupling is marked and the found lane carries the same
colour codes, B504 a measurement for "adjust syllables".
"""

from __future__ import annotations

import inspect
from pathlib import Path

from modules import pipeline, timing, timing_checks, video


def _source_of(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# B499 - the marking sits on the original, and a move survives
# --------------------------------------------------------------------------

def test_the_karaoke_sentence_keeps_its_own_colour_and_text() -> None:
    """De karaoketekst blauw maken en er [origineel] voor zetten verborg
    juist de tekst waar hij mee bezig is."""
    editor = _source_of(__import__("modules.timing_editor",
                                   fromlist=["x"]))
    assert "[origineel] " not in editor
    assert "_ORIG_RESTORE" in editor


def test_the_original_block_turns_blue() -> None:
    from modules import timing_editor

    source = _source_of(timing_editor)
    assert "fill_color = _ORIG_RESTORE" in source
    assert "border_color = (_RESTORE_BORDER if fetched" in source
    # En de karaokezin houdt tekst en kleur, maar krijgt wel een rand -
    # anders is een regel zonder blok in de originele baan (een hele
    # [bg]-regel) te markeren zonder dat er iets van te zien is.
    assert "else _RESTORE_BORDER if haalt \\\n" in source
    assert "else _BG_BORDER if achtergrond else QColor(40, 40, 40)" in source


def test_a_moved_piece_gets_a_dotted_border() -> None:
    from modules import timing_editor

    source = _source_of(timing_editor)
    assert "Qt.DotLine if moved" in source
    # Een crowdregel is gestreept; verplaatst is gestippeld, zodat de
    # twee uit elkaar te houden zijn.
    assert "else Qt.DashLine if is_crowd else Qt.SolidLine" in source


def test_a_move_in_step_one_four_is_kept(tmp_path) -> None:
    context = _context(tmp_path)
    pipeline.set_moved_restores(context, {3: [12.0, 14.5]})
    assert pipeline.moved_restores(context) == {3: (12.0, 14.5)}
    pipeline.reset_moved_restore(context, 3)
    assert pipeline.moved_restores(context) == {}


def test_a_broken_span_is_ignored(tmp_path) -> None:
    context = _context(tmp_path)
    context.store.set_step("restore_moved", {"list": {"1": [5.0, 5.0],
                                                      "2": ["x", 3],
                                                      "3": [1.0, 2.0]}})
    assert set(pipeline.moved_restores(context)) == {3}


def test_the_detection_compares_against_the_bare_derivation() -> None:
    """Anders zegt hij na één keer opslaan dat er niets verplaatst is."""
    source = _source_of(pipeline)
    assert "_restore_from_lines(context,\n                                                   apply_moves=False)" \
        in source
    assert "def _restore_from_lines(context: AppContext, apply_moves: bool = True" \
        in source


def test_clicking_again_puts_the_piece_back() -> None:
    from modules import timing_editor

    source = inspect.getsource(timing_editor.TimingCanvas.toggle_selected_restore)
    assert "self._reset_moves.add(number)" in source
    assert "if moved:" in source


def test_the_chain_knows_the_move() -> None:
    from modules import dependencies

    assert "restore_moved" in dependencies.ARTEFACTS
    assert "restore_moved" in dependencies.ARTEFACTS["karaoke"].sources


# --------------------------------------------------------------------------
# B500 - the logic once more, and checks between the lines
# --------------------------------------------------------------------------

def _line(index, start, end, text="een zin", crowd=False, disabled=False):
    return timing.TimedLine(
        index=index, text=text, crowd=crowd, disabled=disabled,
        syllables=(timing.Syllable("een", start, (start + end) / 2),
                   timing.Syllable(" zin", (start + end) / 2, end)))


def test_two_sentences_over_each_other_are_found() -> None:
    found = timing_checks.line_checks([_line(0, 1.0, 3.0),
                                       _line(1, 2.0, 4.0)])
    assert found["overlapping_lines"] == [(0, 1, 1.0)]
    assert not found["empty_lines"]


def test_a_crowd_line_may_lie_over_its_neighbour() -> None:
    """Een kreet klinkt tegelijk met de zang (B346)."""
    found = timing_checks.line_checks([_line(0, 1.0, 3.0, crowd=True),
                                       _line(1, 2.0, 4.0)])
    assert not found["overlapping_lines"]


def test_a_crowd_line_in_between_does_not_hide_an_overlap() -> None:
    """Hij werd wél onthouden als "de vorige", en dan was de laatste
    gewone zin vergeten."""
    found = timing_checks.line_checks([_line(0, 0.0, 2.0),
                                       _line(1, 0.5, 1.0, crowd=True),
                                       _line(2, 0.6, 3.0)])
    assert found["overlapping_lines"] == [(0, 2, 1.4)]


def test_a_switched_off_line_does_not_make_a_false_order() -> None:
    found = timing_checks.line_checks([_line(0, 0.0, 1.0),
                                       _line(1, 50.0, 51.0, disabled=True),
                                       _line(2, 1.0, 2.0)])
    assert not found["lines_out_of_order"]


def test_a_switched_off_line_does_not_count_either() -> None:
    found = timing_checks.line_checks([_line(0, 1.0, 3.0, disabled=True),
                                       _line(1, 2.0, 4.0)])
    assert not found["overlapping_lines"]


def test_a_line_of_zero_length_is_found() -> None:
    found = timing_checks.line_checks([_line(0, 1.0, 1.0)])
    assert found["empty_lines"] == [0]


def test_lines_that_swapped_places_are_found() -> None:
    found = timing_checks.line_checks([_line(0, 5.0, 6.0),
                                       _line(1, 1.0, 2.0)])
    assert found["lines_out_of_order"] == [(0, 1)]


def test_the_checks_are_part_of_the_report() -> None:
    source = inspect.getsource(timing_checks.inspect)
    assert "between = line_checks(lines)" in source
    for name in ("empty_lines", "overlapping_lines", "lines_out_of_order"):
        assert name in timing_checks.Findings().as_dict()


def test_the_automatic_timing_ends_with_the_logic() -> None:
    """Halverwege wordt er opgeschoond, maar daarna verschuift er nog van
    alles - en dat ging ongecontroleerd de editor en de render in."""
    source = inspect.getsource(pipeline.generate_timing)
    assert "timed, corrected = timing_module.repair_line_edges(timed)" in source
    assert "log_timing_corrected" in source
    # Vóór de diagnose, anders beschrijft dat rapport iets anders dan wat
    # er wordt opgeslagen.
    assert source.index("repair_line_edges(timed)") < source.index(
        "Token-thrifty diagnostics")
    # En de aangehouden noten worden erna opnieuw gewogen.
    na = source[source.index("repair_line_edges(timed)"):]
    assert "timed = timing_module.mark_held(timed)" in na


def test_a_measured_start_is_never_pushed_forward() -> None:
    """Een regelbegin is vaak gemeten (op de zanginzet gezet); dat
    vooruit duwen zet de zin naast de zang én perst hem samen."""
    lines = (_line(0, 10.0, 14.0), _line(1, 13.0, 15.0))
    fixed, count = timing.repair_line_edges(lines)
    assert count == 1
    assert fixed[1].start == 13.0 and fixed[1].end == 15.0
    assert abs(fixed[0].end - 13.0) < 0.01     # de vorige wordt ingekort
    assert fixed[0].start == 10.0


def test_a_line_of_zero_length_gets_room() -> None:
    fixed, count = timing.repair_line_edges((_line(0, 5.0, 5.0),))
    assert count == 1 and fixed[0].end > fixed[0].start


def test_the_repair_leaves_crowd_and_switched_off_alone() -> None:
    lines = (_line(0, 1.0, 3.0), _line(1, 2.0, 4.0, crowd=True))
    fixed, count = timing.repair_line_edges(lines)
    assert count == 0 and fixed[0].end == 3.0


# --------------------------------------------------------------------------
# B501 - the cross-fade
# --------------------------------------------------------------------------

def test_the_two_pictures_are_built_separately() -> None:
    assert callable(video._title_frame)
    assert callable(video._text_frame)
    source = inspect.getsource(video._compose_frame)
    assert "_blend(" in source


def test_the_fade_runs_from_nothing_to_everything() -> None:
    assert video._eased_in(0.0) == 0.0
    assert video._eased_in(1.0) == 1.0
    assert 0.0 < video._eased_in(0.5) < 1.0
    # Buiten bereik blijft binnen bereik.
    assert video._eased_in(-1.0) == 0.0 and video._eased_in(2.0) == 1.0


def test_the_intro_fades_into_the_text() -> None:
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 200, 0, 255))
    lines = [TextLine(0, "de eerste zin", False)]
    timed = generate_skeleton(lines, {0: (10.0, 12.0)})
    args = (320, 180, font, font, logo, "Titel", video._DEFAULT_COLORS)
    logo_only = video._compose_frame(1.0, timed, 5.0, 60.0, *args)
    halfway = video._compose_frame(5.0 - video._INTRO_FADE_S / 2, timed,
                                   5.0, 60.0, *args)
    text_only = video._compose_frame(6.0, timed, 5.0, 60.0, *args)
    assert halfway.tobytes() not in (logo_only.tobytes(),
                                     text_only.tobytes())


def test_the_outro_fades_in_from_the_text() -> None:
    source = inspect.getsource(video._compose_frame)
    assert "outro_start <= moment < outro_start + _OUTRO_FADE_S" in source
    assert video._OUTRO_FADE_S >= video._INTRO_FADE_S


# --------------------------------------------------------------------------
# B502/B503 - a run without any coupling
# --------------------------------------------------------------------------

def test_a_run_without_any_coupling_is_marked() -> None:
    transcript = [(f"w{i}", float(i), i + 0.5) for i in range(8)]
    words = [{"index": 0, "transcript_indices": [0]},
             {"index": 1, "transcript_indices": [7]}]
    status = pipeline._transcript_status(transcript, words, [])
    assert status[0] == "coupled" and status[7] == "coupled"
    assert all(status[i] == "suspect_run" for i in range(1, 7))


def test_a_single_missed_word_is_not_a_hallucination() -> None:
    transcript = [(f"w{i}", float(i), i + 0.5) for i in range(4)]
    words = [{"index": 0, "transcript_indices": [0]},
             {"index": 1, "transcript_indices": [2]},
             {"index": 2, "transcript_indices": [3]}]
    status = pipeline._transcript_status(transcript, words, [])
    assert status[1] == "no_match"
    assert "suspect_run" not in status.values()


def test_the_run_needs_a_length() -> None:
    assert pipeline.SUSPECT_RUN >= 3


def test_the_found_lane_carries_the_same_colour_codes() -> None:
    from modules import coupling_editor

    assert "suspect_run" in coupling_editor._STATUS_STYLE
    source = _source_of(coupling_editor)
    assert 'style = _STATUS_STYLE.get(self._found_status.get(i, ""))' in source
    assert "found_status" in inspect.signature(
        coupling_editor.CouplingCanvas.__init__).parameters


def test_the_view_hands_the_status_along() -> None:
    source = inspect.getsource(pipeline.word_coupling_view)
    assert '"found_status": _transcript_status(' in source


# --------------------------------------------------------------------------
# B505 - the shift runs between two stacks
# --------------------------------------------------------------------------

def test_the_shift_starts_where_the_line_really_stood() -> None:
    source = inspect.getsource(video._text_frame)
    assert "previous_tops = _stack(active_index - 1)" in source
    assert "was = _place(previous_tops, slot + 1)" in source


def _context(tmp_path):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Lied")
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# What the critical re-read found
# --------------------------------------------------------------------------

def test_a_filtered_word_keeps_its_own_marking() -> None:
    """Drie al gefilterde woorden plus één gemist woord maakten er een
    'verdachte reeks' van; dan zakt de drempel tot één woord."""
    transcript = [(f"w{i}", float(i), i + 0.5) for i in range(5)]
    words = [{"index": 0, "transcript_indices": [4]}]
    status = pipeline._transcript_status(transcript, words, [0, 1, 2])
    assert status[0] == "hallucination_filtered"
    assert status[3] == "no_match"
    assert "suspect_run" not in status.values()


def test_unfiltering_a_word_makes_it_look_ordinary_again() -> None:
    from modules import coupling_editor

    source = _source_of(coupling_editor)
    # B520: dezelfde functie als de pijplijn gebruikt, en de hele baan
    # in één keer - anders wordt hij na een bewerking grover dan hij was.
    assert "def _refresh_found_status(self, index: int | None = None)" in source
    assert "self._refresh_found_status(self._sel_top)" in source
    assert "pipeline.found_word_status(" in source
    # En koppelen met de hand loopt via _emit.
    assert "self._refresh_found_status()" in source


def test_a_read_error_does_not_wipe_the_markings() -> None:
    source = inspect.getsource(pipeline.apply_manual_damping)
    assert "readable = bool(_restore_from_lines(context, apply_moves=False))" \
        in source
    assert "if readable:" in source


def test_the_karaoke_sentence_shows_that_it_is_marked() -> None:
    """Een hele [bg]-regel heeft geen blok in de originele baan, dus
    zonder dit is hij te markeren zonder dat er iets van te zien is."""
    from modules import timing_editor

    source = _source_of(timing_editor)
    assert "haalt = bool(rows) and all(" in source
