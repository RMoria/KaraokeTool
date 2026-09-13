"""Tests for v0.138.0: B439 to B445.

B439 is the one that matters. The big trial measured nothing at all for
ten versions and said so in a way that read like a result: twenty models,
a hundred and ninety pairs and two orders, every single one of them
exactly +0.00. Nothing went red, because no test ever asked whether two
variants actually differ from each other.

These do.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path as pathlib_Path

import pytest

from modules import measure_pool, model_orders, model_register, pipeline


def _context(tmp_path, name: str = "Proef"):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=name)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


@pytest.fixture()
def recorded(monkeypatch):
    """Every measuring request the panel sends to a child."""
    seen: list[tuple] = []

    def fake_measure_rows(root, songs, output_base, states, **kw):
        seen.append((tuple(sorted(dict(states).items())),
                     kw.get("order", "")))
        return []

    monkeypatch.setattr(measure_pool, "measure_rows", fake_measure_rows)
    return seen


# --------------------------------------------------------------------------
# B439 - the regression itself
# --------------------------------------------------------------------------

def test_the_big_trial_does_not_measure_the_same_thing_every_round(
        tmp_path, monkeypatch, recorded) -> None:
    """THE test. It is the one that was missing.

    Since B396 the measuring happens in a child interpreter, and a child
    builds its world from the state map it is handed. The trial kept
    setting its variant with setattr in the parent, so every round asked
    for the identical state - and a table full of +0.00 looks like an
    answer, not like a defect.
    """
    from modules import test_panel

    monkeypatch.setattr(test_panel, "MATRIX_REPORT",
                        tmp_path / "modelmatrix.md")
    test_panel.big_trial(_context(tmp_path), lambda *a, **k: None,
                         lambda: False)
    states = {state for state, _order in recorded}
    assert len(states) > 1, "elke ronde vroeg dezelfde stand op"


def test_every_model_is_measured_with_its_own_code_flipped(
        tmp_path, monkeypatch, recorded) -> None:
    """Not just "different", but different in the right place."""
    from modules import test_panel

    monkeypatch.setattr(test_panel, "MATRIX_REPORT",
                        tmp_path / "modelmatrix.md")
    test_panel.big_trial(_context(tmp_path), lambda *a, **k: None,
                         lambda: False)
    base = dict(recorded[0][0])
    models = [m for _l, m, _t, _o in test_panel._variants_from_register()]
    flipped_once = {
        next(iter({code for code, on in state
                   if base.get(code) is not on}))
        for state, order in recorded
        if not order and len({code for code, on in state
                              if base.get(code) is not on}) == 1}
    for model in models:
        assert model.code in flipped_once, model.code


def test_the_pairs_flip_two_codes_at_once(
        tmp_path, monkeypatch, recorded) -> None:
    from modules import test_panel

    monkeypatch.setattr(test_panel, "MATRIX_REPORT",
                        tmp_path / "modelmatrix.md")
    test_panel.big_trial(_context(tmp_path), lambda *a, **k: None,
                         lambda: False)
    base = dict(recorded[0][0])
    two = [state for state, _o in recorded
           if len({code for code, on in state
                   if base.get(code) is not on}) == 2]
    models = test_panel._variants_from_register()
    assert len(two) == len(models) * (len(models) - 1) // 2


def test_an_order_travels_as_a_name(
        tmp_path, monkeypatch, recorded) -> None:
    """An order swaps whole functions, and a function object does not
    survive pickling - so the NAME goes and the child builds it.

    B536: an order that rearranges a step which is switched off is not
    measured at all, so only the measurable ones travel.
    """
    from modules import test_panel

    verslag = tmp_path / "modelmatrix.md"
    monkeypatch.setattr(test_panel, "MATRIX_REPORT", verslag)
    test_panel.big_trial(_context(tmp_path), lambda *a, **k: None,
                         lambda: False)
    asked = {order for _state, order in recorded if order}
    meetbaar = {name for name in model_orders.names()
                if not model_orders.measurable(name)}
    assert asked == meetbaar
    # En wat niet gemeten is staat er als overgeslagen, niet als 0,00.
    tekst = verslag.read_text(encoding="utf-8")
    for name in model_orders.names():
        uit = model_orders.measurable(name)
        if uit:
            regel = next(r for r in tekst.splitlines()
                         if r.startswith(f"| {name} |"))
            assert "0.00" not in regel and uit[0] in regel


def test_the_omission_trial_went_the_same_way(
        tmp_path, recorded) -> None:
    from modules import test_panel

    test_panel.omission_trial(_context(tmp_path), lambda *a, **k: None,
                              lambda: False)
    assert len({state for state, _o in recorded}) > 1


def _real_calls(function, name: str) -> int:
    """How often the CODE calls this - prose in a docstring does not
    count, and a comment explaining what went wrong certainly must not."""
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    return sum(1 for node in ast.walk(tree)
               if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Name)
               and node.func.id == name)


def test_no_trial_sets_a_model_with_setattr_any_more() -> None:
    """The two later sections of 1.5.10 (coverage, word/syllable) still
    use setattr, and rightly so - those run over threads in this same
    interpreter. The measuring sections must not, and those are exactly
    the four that lay flat on nought."""
    from modules import test_panel

    assert _real_calls(test_panel.omission_trial, "setattr") == 0
    # Four sets in the coverage and word sections, two each.
    assert _real_calls(test_panel.big_trial, "setattr") == 4


def test_the_flipping_happens_in_one_place() -> None:
    from modules import test_panel

    for name in ("_measure", "_rows_over_processes"):
        source = inspect.getsource(getattr(test_panel, name))
        assert "_states_with(" in source, name


# --------------------------------------------------------------------------
# B439 - the order, from the panel to the child
# --------------------------------------------------------------------------

def test_the_orders_no_longer_live_next_to_a_widget_toolkit() -> None:
    """A measuring process imports this module. It must not drag Qt in.

    On the imports, not on the text: the module explains in so many
    words WHY it does not import PySide6, and a test that reads prose
    would trip over its own explanation.
    """
    import ast

    tree = ast.parse(inspect.getsource(model_orders))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
            imported.update(a.name for a in node.names)
    assert "PySide6" not in imported
    assert "test_panel" not in imported


def test_the_panel_still_offers_the_orders() -> None:
    from modules import test_panel

    assert [name for name, _t in test_panel._orders()] \
        == list(model_orders.names())


def test_an_order_is_built_fresh_every_time() -> None:
    """A builder closes over what is real RIGHT NOW; building once at
    import time would freeze whatever happened to be installed then."""
    first = model_orders.targets("B313 vóór B121")
    second = model_orders.targets("B313 vóór B121")
    assert [(m, a) for m, a, _v in first] == [(m, a) for m, a, _v in second]
    assert first[0][2] is not second[0][2]


def test_an_unknown_order_gives_nothing_rather_than_an_error() -> None:
    assert model_orders.targets("bestaat niet") == []
    model_orders.apply("")


def test_the_child_applies_the_order_it_is_handed() -> None:
    source = inspect.getsource(measure_pool._measure_one)
    assert "model_orders.targets(order)" in source
    assert "apply_settings(dict(states))" in source


def test_the_child_puts_the_order_back_again() -> None:
    """The pool keeps ONE set of workers alive for a whole action, so a
    worker measures round after round. An order left standing stacks on
    the next one and keeps running in every round that has none."""
    source = inspect.getsource(measure_pool._measure_one)
    assert "put_back" in source
    assert "finally:" in source
    assert source.index("finally:") > source.index("regression.measure")


def test_an_order_does_not_stack_on_the_previous_one(monkeypatch) -> None:
    """Measured, not asserted from the source: build the world the pool
    builds and check the second order sees the REAL function."""
    real = pipeline._clean_segments_and_alignment
    first = model_orders.targets("B307 vóór B285")
    saved = [(m, a, getattr(m, a)) for m, a, _v in first]
    try:
        for module, attribute, replacement in first:
            setattr(module, attribute, replacement)
        assert pipeline._clean_segments_and_alignment is not real
    finally:
        for module, attribute, was in saved:
            setattr(module, attribute, was)
    assert pipeline._clean_segments_and_alignment is real


def test_the_work_item_carries_the_order() -> None:
    source = inspect.getsource(measure_pool.measure_rows)
    assert "order)" in source
    assert inspect.signature(measure_pool._measure_one)


# --------------------------------------------------------------------------
# B439 - the serial fallback used to leave the variant standing
# --------------------------------------------------------------------------

def test_the_serial_path_puts_the_register_back(monkeypatch) -> None:
    """``_measure_one`` is written for a child, which is thrown away.
    Run it in the parent and the program keeps going on the last variant
    it measured."""
    model_register.apply_settings({})
    before = model_register.current_settings()
    items = [("root", "Proef", "output",
              (("B380", True), ("B213", True)), "")]
    monkeypatch.setattr(measure_pool, "_measure_one", lambda item: None)
    measure_pool._serial(items, None, None)
    assert model_register.current_settings() == before


def test_the_serial_path_puts_the_order_back(monkeypatch) -> None:
    real = pipeline._clean_segments_and_alignment
    items = [("root", "Proef", "output", (), "B313 vóór B121")]

    def apply_and_die(item):
        model_orders.apply(item[4])
        return None

    monkeypatch.setattr(measure_pool, "_measure_one", apply_and_die)
    measure_pool._serial(items, None, None)
    assert pipeline._clean_segments_and_alignment is real


def test_the_register_can_say_what_it_is_set_to() -> None:
    """Deliberately the overrides and not the full map: handing back a
    complete map turns every default into an explicit setting."""
    model_register.apply_settings({"B380": False})
    assert model_register.current_settings() == {"B380": False}
    model_register.apply_settings({})
    assert model_register.current_settings() == {}


# --------------------------------------------------------------------------
# B440 - a broken report must not read like a result
# --------------------------------------------------------------------------

def test_a_matrix_of_pure_noughts_is_refused() -> None:
    """The cluster trial read ten versions of nothing as "no model
    touches any other" and wrote that down as a finding."""
    from modules import test_panel

    dead = [("A", "B", 0.0), ("A", "C", 0.0), ("B", "C", 0.0)]
    assert test_panel.flat_report(dead)
    assert not test_panel.flat_report(dead[:2] + [("B", "C", 0.02)])
    assert not test_panel.flat_report([])


def test_the_cluster_trial_stops_on_a_dead_matrix(tmp_path,
                                                  monkeypatch) -> None:
    from modules import test_panel

    monkeypatch.setattr(test_panel, "_pairs_from_report",
                        lambda: [("A", "B", 0.0), ("A", "C", 0.0)])
    with pytest.raises(test_panel.TrialSkipped):
        test_panel.cluster_trial(_context(tmp_path), lambda *a, **k: None,
                                 lambda: False)


def test_the_matrix_says_which_version_made_it(tmp_path,
                                               monkeypatch) -> None:
    """Ten reports of nought were indistinguishable from a real one."""
    from modules import __version__, test_panel

    report = tmp_path / "modelmatrix.md"
    monkeypatch.setattr(test_panel, "MATRIX_REPORT", report)
    test_panel.big_trial(_context(tmp_path), lambda *a, **k: None,
                         lambda: False)
    assert __version__ in report.read_text(encoding="utf-8")


def test_a_report_says_which_version_measured_it() -> None:
    """The banner that marked the broken reports has served its purpose -
    1.5.10 has since produced real numbers and overwrote it, which is
    exactly what should happen. What has to stay is the mechanism: every
    report names its version, so this can never again be invisible."""
    from modules.translations import TRANSLATIONS

    for language in ("nl", "en"):
        text = TRANSLATIONS[language]["test_matrix_made_with"]
        assert "{version}" in text
        assert "0.128.0" in text and "0.137.0" in text


def test_the_test_run_leaves_the_real_reports_alone() -> None:
    """Running the suite overwrote docs/modelcombinaties.md - an hour of
    the user's laptop, replaced by the output of an empty test project,
    and nothing said so. Redirecting per test is what you forget the
    fifteenth time, so it happens for every test now."""
    from pathlib import Path

    from modules import test_history, test_panel

    root = Path(test_panel.__file__).resolve().parents[1]
    for path in (test_panel.MATRIX_REPORT, test_panel.COMBINATION_REPORT,
                 test_panel.CHUNK_WORDS, test_history.HISTORY_FILE):
        assert not str(path).startswith(str(root / "docs")), path


# --------------------------------------------------------------------------
# B441 - the held syllable, at last
# --------------------------------------------------------------------------

def _line(text: str, spans):
    from dataclasses import replace

    from modules import timing

    line = timing.timedline_from_text(0, text, spans[0][0], spans[-1][1])
    return replace(line, syllables=tuple(
        replace(s, start=a, end=b)
        for s, (a, b) in zip(line.syllables, spans)))


def test_a_stretched_syllable_is_marked() -> None:
    from modules import timing

    spans = [(0.0, .3), (.3, .6), (.6, .9), (.9, 1.2), (1.2, 1.5),
             (1.5, 1.8), (1.8, 5.0), (5.0, 5.3)]
    line = timing.mark_held([_line("ik zal altijd van je houden", spans)])[0]
    assert [s.text for s in line.syllables if s.held] == [" hou"]


def test_an_evenly_sung_line_has_nothing_held() -> None:
    from modules import timing

    spans = [(n * 0.4, n * 0.4 + 0.4) for n in range(8)]
    line = timing.mark_held([_line("ik zal altijd van je houden", spans)])[0]
    assert not any(s.held for s in line.syllables)


def test_a_slow_song_is_not_one_long_held_note() -> None:
    """Relative on purpose: a ballad has long syllables everywhere, and
    then none of them is remarkable."""
    from modules import timing

    spans = [(n * 1.2, n * 1.2 + 1.2) for n in range(8)]
    line = timing.mark_held([_line("ik zal altijd van je houden", spans)])[0]
    assert not any(s.held for s in line.syllables)


def test_a_short_syllable_never_counts_however_lopsided() -> None:
    from modules import timing

    spans = [(0.0, .01), (.01, .02), (.02, .03), (.03, .04), (.04, .05),
             (.05, .06), (.06, .30), (.30, .31)]
    line = timing.mark_held([_line("ik zal altijd van je houden", spans)])[0]
    assert not any(s.held for s in line.syllables)


def test_a_line_of_two_syllables_is_left_alone() -> None:
    """With two syllables the median sits exactly between them, so one of
    the two is always four times "the middle"."""
    from modules import timing

    line = timing.mark_held([_line("hallo", [(0.0, 0.2), (0.2, 4.0)])])[0]
    assert not any(s.held for s in line.syllables)


def test_a_pause_is_not_a_held_note() -> None:
    """It is long by its nature and it is drawn as lighting dots - a rule
    under a pause is a rule under nothing."""
    from modules import karaoke_text, timing

    spans = [(0.0, .2), (.2, .4), (.4, 3.0), (3.0, 3.2)]
    line = _line(f"een twee {karaoke_text.PAUSE_TOKEN} drie", spans)
    long_one = [s for s in line.syllables
                if karaoke_text.is_pause(s.text)]
    assert long_one and long_one[0].end - long_one[0].start > 2, \
        "de opzet klopt niet: de pauze moet juist het lange stuk zijn"
    assert not any(s.held for s in timing.mark_held([line])[0].syllables)


def test_the_mark_is_set_where_the_timing_is_made() -> None:
    """It has existed since B92 and the render has drawn it just as long;
    nothing ever set it, so over fourteen thousand syllables there was
    not one."""
    from modules import pipeline

    source = inspect.getsource(pipeline.generate_timing)
    assert "timing_module.mark_held(timed)" in source
    # After the phonetic timing: everything above still moves syllable
    # boundaries and the mark judges the final spans.
    assert source.index("mark_held") > source.index("apply_phonetic_timing")


def test_the_render_does_not_draw_it() -> None:
    """B449: the underline is gone from the video. The colouring is what
    marks a held piece there - a rule under it as well was one sign too
    many, and it was the user's own call. On the code, not on the prose:
    the sweep explains itself with the word "held" in a comment."""
    import ast
    import textwrap

    from modules import video

    tree = ast.parse(textwrap.dedent(inspect.getsource(video._draw_line)))
    names = {node.attr for node in ast.walk(tree)
             if isinstance(node, ast.Attribute)}
    names |= {node.id for node in ast.walk(tree)
              if isinstance(node, ast.Name)}
    assert "held" not in names


def test_the_word_numbers_of_a_line_can_be_asked_for() -> None:
    from modules import timing

    spans = [(0.0, .3), (.3, .6), (.6, .9), (.9, 1.2), (1.2, 1.5),
             (1.5, 1.8), (1.8, 5.0), (5.0, 5.3)]
    line = timing.mark_held([_line("ik zal altijd van je houden", spans)])[0]
    assert timing.held_words(line) == frozenset({5})


# --------------------------------------------------------------------------
# B441 - and the same mark in the word coupling
# --------------------------------------------------------------------------

def test_a_long_found_word_is_marked_in_the_coupling() -> None:
    """The user is deciding there how to spread the stresses over the
    karaoke text, and "this word is sung for three seconds" is exactly
    what he cannot hear from the text."""
    transcript = [("ik", 0.0, 0.3), ("zal", 0.3, 0.6), ("altijd", 0.6, 1.2),
                  ("van", 1.2, 1.5), ("je", 1.5, 1.8), ("houden", 1.8, 5.0)]
    assert pipeline.held_transcript_words(transcript) == frozenset({5})


def test_an_even_transcription_marks_nothing() -> None:
    transcript = [(f"w{n}", n * 0.4, n * 0.4 + 0.4) for n in range(10)]
    assert pipeline.held_transcript_words(transcript) == frozenset()


def test_too_short_a_transcription_says_nothing_rather_than_something() -> None:
    assert pipeline.held_transcript_words([("ha", 0.0, 4.0)]) == frozenset()
    assert pipeline.held_transcript_words([]) == frozenset()


def test_the_coupling_view_hands_the_mark_on() -> None:
    source = inspect.getsource(pipeline.word_coupling_view)
    assert 'w["held"] = any(' in source
    assert "held_transcript_words(transcript)" in source


def test_the_word_coupling_is_plain_again() -> None:
    """B449: and out of the word coupling too. "Only visible in the
    timing editor" was the instruction, and it is the stress editor that
    shows it now - there it means something, because that is where the
    original and the karaoke lie next to each other."""
    from modules import coupling_editor

    source = inspect.getsource(coupling_editor.CouplingCanvas._draw_box)
    assert "held" not in source
    assert not hasattr(coupling_editor, "_HELD_MARK")


def test_the_two_thresholds_are_the_ones_that_were_measured() -> None:
    """Unchanged from the 1.5.7 inventory on purpose: that is the rule
    the 7.0% and the "all of them vowels" came out of."""
    from modules import test_panel, timing

    assert timing.HELD_MIN_S == test_panel.HELD_S
    assert timing.HELD_FACTOR == test_panel.HELD_FACTOR


# --------------------------------------------------------------------------
# B442 - the chunked run, from the night job into production
# --------------------------------------------------------------------------

def test_a_new_setting_does_not_wipe_the_existing_projects() -> None:
    """The one that could really hurt. Seventeen projects carry hand-made
    timing; if a signature group that was not there before counts as
    "changed", every one of them loses its derived work the first time
    the program starts."""
    from modules.config import default_config

    signature = pipeline._config_signature(default_config())
    assert "config:chunked" in signature
    kept = {group: value for group, value in signature.items()
            if group != "config:chunked"}
    changed = [group for group, value in signature.items()
               if group in kept and kept[group] != value]
    assert changed == []


def test_the_chunking_hangs_in_the_dependency_chain() -> None:
    """Switching it off has to remove the transcription, the same way
    the forced alignment does."""
    from modules import dependencies

    steps, _metas, _files = dependencies.invalidation_plan(
        ["config:chunked"], ())
    assert "whisper_original" in steps


def test_the_cache_key_knows_about_the_chunking() -> None:
    source = inspect.getsource(pipeline.detect_track)
    assert 'step.get("chunked", in_pieces)' in source
    assert '"chunked": in_pieces' in source


def test_only_the_original_is_cut() -> None:
    """The karaoke side is the residual singing and is usually empty;
    cutting an empty stem into ten pieces is ten times nothing."""
    source = inspect.getsource(pipeline.detect_track)
    assert "track == TRACK_ORIGINAL" in source.split("in_pieces =")[1][:80]


def test_the_heaviest_job_starts_first() -> None:
    """The user's rule: as much as possible in one queue, heaviest task
    first. The whole song is the heaviest single item by definition."""
    from modules import whisper_chunks as wc

    pieces = (wc.Chunk(0.0, 10.0), wc.Chunk(10.0, 40.0),
              wc.Chunk(40.0, 55.0))
    jobs = wc.jobs_heaviest_first(pieces, 55.0)
    assert jobs[0] == (0.0, None)
    lengths = [end - start for start, end in jobs[1:]]
    assert lengths == sorted(lengths, reverse=True)


def test_the_whole_song_is_recognisable_by_an_open_end() -> None:
    """That is also what tells the runner it may hand the file straight
    to Whisper instead of cutting samples out of it."""
    from modules import whisper_chunks as wc

    jobs = wc.jobs_heaviest_first((wc.Chunk(0.0, 10.0),), 10.0)
    assert jobs[0][1] is None
    assert all(end is not None for _s, end in jobs[1:])


def test_loose_words_become_segments_again() -> None:
    """The merge works on words - that is the level at which a hole can
    be filled - but the rest of the program reads segments."""
    from modules import whisper_chunks as wc

    words = [{"text": "een", "start": 1.0, "end": 1.2, "confidence": 0.9},
             {"text": "twee", "start": 1.3, "end": 1.5, "confidence": 0.9},
             {"text": "ver", "start": 9.0, "end": 9.4, "confidence": 0.9}]
    segments = wc.segments_from_words(words, first_index=7)
    assert [s["text"] for s in segments] == ["een twee", "ver"]
    assert [s["index"] for s in segments] == [7, 8]
    assert segments[0]["start"] == 1.0 and segments[0]["end"] == 1.5


def test_a_piece_may_only_fill_never_overrule() -> None:
    """The first run stays the truth. A second run cannot push a word
    that WAS heard out of the way; it can only fill a silence."""
    from modules import whisper_chunks as wc

    windows = [(0.0, 20.0)]
    base = [{"text": "hallo", "start": 1.0, "end": 1.4, "confidence": 0.9}]
    extra = [{"text": "fout", "start": 1.1, "end": 1.3, "confidence": 0.99},
             {"text": "gat", "start": 8.0, "end": 8.4, "confidence": 0.99}]
    added = wc.words_to_add(base, extra, windows)
    assert [w["text"] for w in added] == ["gat"]


def test_a_word_off_the_singing_is_never_added() -> None:
    from modules import whisper_chunks as wc

    added = wc.words_to_add(
        [], [{"text": "ruis", "start": 30.0, "end": 30.5,
              "confidence": 1.0}], [(0.0, 20.0)])
    assert added == []


def test_the_merge_and_the_addition_share_one_rule() -> None:
    """Two implementations of "may this word come in" would drift."""
    from modules import whisper_chunks as wc

    assert "words_to_add(" in inspect.getsource(wc.merge_runs)


def test_a_failed_piece_does_not_take_the_run_with_it(monkeypatch) -> None:
    from modules import whisper, whisper_chunks as wc

    def fake(audio_path, settings, start=0.0, end=None, **kw):
        if start:
            raise RuntimeError("dit stuk niet")
        return ()

    monkeypatch.setattr(whisper, "transcribe_slice", fake)
    found = wc.run_over_lanes("a.wav", None,
                              [(0.0, None), (10.0, 20.0)], "", "nl", lanes=2)
    assert (0.0, None) in found
    assert (10.0, 20.0) not in found


def test_a_failed_WHOLE_run_is_not_swallowed(monkeypatch) -> None:
    """Without the whole run there is nothing to fill in, and quietly
    returning the pieces would be the worst of both."""
    from modules import whisper, whisper_chunks as wc

    def fake(audio_path, settings, start=0.0, end=None, **kw):
        if not start:
            raise RuntimeError("de hele draai")
        return ()

    monkeypatch.setattr(whisper, "transcribe_slice", fake)
    with pytest.raises(RuntimeError):
        wc.run_over_lanes("a.wav", None, [(0.0, None), (10.0, 20.0)],
                          "", "nl", lanes=2)


def test_nothing_to_cut_on_falls_back_to_one_honest_run() -> None:
    """B538: en die terugval geldt nu alleen als er ook geen tweede taal
    is - anders is er wél iets te doen in de banen."""
    source = inspect.getsource(pipeline._transcribe_in_pieces)
    assert "if len(pieces) < 2 and not second:" in source
    assert "whisper.transcribe(" in source


def test_the_pieces_get_the_global_prompt() -> None:
    """B424: the gain comes from the CUTTING, not from a prompt per
    piece - and that is exactly what lets everything go in one queue
    instead of waiting for a first transcription."""
    source = inspect.getsource(pipeline._transcribe_in_pieces)
    assert "chunk_prompt" not in source
    assert "run_over_lanes(wav_path, settings, jobs, prompt" in source


def test_the_pieces_are_cut_on_the_originals_own_timeline() -> None:
    """``_vocal_windows`` projects onto the KARAOKE timeline, which is
    right for the karaoke text and wrong here: this cuts the original
    vocal stem and weighs word times measured in that same file. With an
    alignment in place a projection puts the cuts beside the real
    silences and scores correctly heard words as "not on singing"."""
    source = inspect.getsource(pipeline._transcribe_in_pieces)
    assert "_original_vocal_windows(context)" in source
    assert "= _vocal_windows(" not in source
    assert "project_time" not in inspect.getsource(
        pipeline._original_vocal_windows)


def test_the_karaoke_windows_still_go_through_the_projection() -> None:
    """The other users must not lose their projection over this."""
    source = inspect.getsource(pipeline._vocal_windows)
    assert "project_time" in source
    assert "_original_vocal_windows(context)" in source


def test_stopping_is_never_mistaken_for_a_finished_run() -> None:
    """The caller caches what it gets and marks the step done, and
    everything derived from the transcription - a hand-timed timing.json
    included - is thrown away on the strength of that."""
    from modules import whisper, whisper_chunks as wc

    def fake(audio_path, settings, start=0.0, end=None, **kw):
        if not start:
            raise whisper.CancelledError()
        return ()

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(whisper, "transcribe_slice", fake)
        with pytest.raises(whisper.CancelledError):
            wc.run_over_lanes("a.wav", None, [wc.WHOLE_SONG, (10.0, 20.0)],
                              "", "nl", lanes=2)


def test_a_cancelled_piece_stops_the_whole_run_too() -> None:
    """A partial merge cached as complete is the worst of both."""
    from modules import whisper, whisper_chunks as wc

    def fake(audio_path, settings, start=0.0, end=None, **kw):
        if start:
            raise whisper.CancelledError()
        return ()

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(whisper, "transcribe_slice", fake)
        with pytest.raises(whisper.CancelledError):
            wc.run_over_lanes("a.wav", None, [wc.WHOLE_SONG, (10.0, 20.0)],
                              "", "nl", lanes=1)


def test_a_failed_piece_still_counts_towards_the_progress() -> None:
    """Otherwise one failure means the bar never reaches the end."""
    from modules import whisper, whisper_chunks as wc

    seen = []

    def fake(audio_path, settings, start=0.0, end=None, **kw):
        if start:
            raise RuntimeError("dit stuk niet")
        return ()

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(whisper, "transcribe_slice", fake)
        wc.run_over_lanes("a.wav", None, [wc.WHOLE_SONG, (10.0, 20.0)],
                          "", "nl", lanes=1,
                          on_done=lambda ready, count: seen.append(
                              (ready, count)))
    assert seen[-1] == (2, 2)


def test_no_vad_on_the_pieces() -> None:
    """B425: cutting plus VAD was worse on all four songs, so the pieces
    are decoded with exactly the settings the whole song gets."""
    source = inspect.getsource(pipeline._transcribe_in_pieces)
    assert "vad_filter" not in source
    assert "settings" in source and "replace(" not in source


def test_the_slice_transcription_lives_in_the_app() -> None:
    """It was in tools/whisper_probe.py, which was fine while only the
    trial cut anything."""
    from modules import whisper

    assert hasattr(whisper, "transcribe_slice")
    assert hasattr(whisper, "audio_slice")
    assert "decode_options(settings)" in inspect.getsource(
        whisper.transcribe_slice)


def test_a_slice_puts_its_times_back_on_the_song() -> None:
    from modules import whisper

    source = inspect.getsource(whisper.transcribe_slice)
    assert "shift = float(start)" in source


def test_the_lyric_keys_live_where_production_can_reach_them() -> None:
    from modules import test_panel

    assert hasattr(pipeline, "lyric_keys")
    assert "pipeline.lyric_keys(context)" in inspect.getsource(
        test_panel._lyric_keys)


def test_the_setting_can_be_switched_off() -> None:
    """A model that turns out worthless is switched off, not removed -
    the same goes for a method."""
    from dataclasses import replace

    import json

    from modules.config import default_config, load_config, save_config

    config = default_config()
    assert config.advanced.chunked_transcription is True
    off = replace(config, advanced=replace(config.advanced,
                                           chunked_transcription=False))
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = pathlib_Path(folder) / "config.json"
        save_config(off, path)
        assert json.loads(path.read_text(encoding="utf-8"))["advanced"][
            "chunked_transcription"] is False
        assert load_config(path).advanced.chunked_transcription is False


# --------------------------------------------------------------------------
# B443 - what is this installation running on
# --------------------------------------------------------------------------

def test_the_stamp_needs_no_network_and_no_heavy_imports() -> None:
    """It runs at every start, so it may not cost anything. Reading a
    version number is a dictionary lookup; importing torch to ask is
    seconds."""
    from modules import versions

    source = inspect.getsource(versions)
    assert "import torch" not in source
    assert "subprocess" not in source
    assert "urlopen" not in source and "requests" not in source


def test_the_versions_of_the_packages_that_matter_are_taken() -> None:
    from modules import versions

    taken = versions.collected("0.138.0")
    assert taken["app"] == "0.138.0"
    assert taken["python"]
    for name in ("faster-whisper", "torch", "demucs", "PySide6"):
        assert name in taken["packages"], name


def test_a_package_that_is_gone_is_recorded_and_not_skipped() -> None:
    """"demucs has disappeared" is exactly what this file has to be able
    to show."""
    from modules import versions

    taken = versions.collected("0.138.0")
    assert set(taken["packages"]) == set(versions.PACKAGES)


def test_only_a_change_is_written_down(tmp_path) -> None:
    """An entry per start is thousands of identical lines within a
    month, and then nobody looks in it any more."""
    from modules import versions

    path = tmp_path / "pakketversies.json"
    taken = {"app": "0.138.0", "python": "3.12.1",
             "packages": {"torch": "2.3.0"}}
    assert versions.remember(taken, path) == []
    assert versions.remember(taken, path) == []
    assert len(versions.history(path)) == 1


def test_an_upgrade_is_written_down_in_words(tmp_path) -> None:
    from modules import versions

    path = tmp_path / "pakketversies.json"
    versions.remember({"app": "0.137.0", "python": "3.12.1",
                       "packages": {"torch": "2.3.0"}}, path)
    changes = versions.remember({"app": "0.138.0", "python": "3.12.1",
                                 "packages": {"torch": "2.4.0"}}, path)
    assert "torch 2.3.0 -> 2.4.0" in changes
    assert "app 0.137.0 -> 0.138.0" in changes
    entries = versions.history(path)
    assert len(entries) == 2 and entries[-1]["changed"] == changes
    assert entries[-1]["when"]


def test_a_package_appearing_and_disappearing_reads_the_same() -> None:
    from modules import versions

    gone = versions.differences({"packages": {"demucs": "4.1.0"}},
                                {"packages": {"demucs": ""}})
    assert gone == ["demucs 4.1.0 -> -"]
    back = versions.differences({"packages": {"demucs": ""}},
                                {"packages": {"demucs": "4.1.0"}})
    assert back == ["demucs - -> 4.1.0"]


def test_a_damaged_history_is_not_fatal(tmp_path) -> None:
    """This runs before anything else does. It may never stop a start."""
    from modules import versions

    path = tmp_path / "pakketversies.json"
    path.write_text("{dit is geen json", encoding="utf-8")
    assert versions.history(path) == []
    assert isinstance(versions.remember(
        {"app": "1", "python": "3", "packages": {}}, path), list)


def test_the_start_writes_the_stamp() -> None:
    from pathlib import Path

    import modules

    source = (Path(modules.__file__).resolve().parents[1]
              / "KaraokeTool.py").read_text(encoding="utf-8")
    assert "versions.stamp(__version__)" in source
    assert "versions.report_pending()" in source


# --------------------------------------------------------------------------
# B444 - the update check, which never keeps the start waiting
# --------------------------------------------------------------------------

def test_the_program_never_asks_pip_itself() -> None:
    """pip means the network and a subprocess, and the user should not
    be waiting for either at start-up."""
    from modules import versions

    assert "pip" not in inspect.getsource(versions.report_pending)
    assert "pip" not in inspect.getsource(versions.pending_updates)


def test_only_the_packages_we_follow_are_reported() -> None:
    from modules import versions

    payload = json.dumps([
        {"name": "torch", "version": "2.3.0", "latest_version": "2.4.0"},
        {"name": "een-of-ander", "version": "1.0", "latest_version": "2.0"}])
    found = versions.outdated_from_pip(payload)
    assert [item["name"] for item in found] == ["torch"]
    assert found[0]["current"] == "2.3.0" and found[0]["latest"] == "2.4.0"


def test_rubbish_from_pip_gives_nothing_rather_than_an_error() -> None:
    from modules import versions

    assert versions.outdated_from_pip("") == []
    assert versions.outdated_from_pip("niet eens json") == []


def test_an_old_report_says_nothing(tmp_path) -> None:
    """"There is an update" on the strength of a file from six weeks ago
    is advice that has already been followed or long since overtaken."""
    from datetime import datetime, timedelta, timezone

    from modules import versions

    path = tmp_path / "updates.json"
    long_ago = datetime.now(timezone.utc) - timedelta(days=60)
    versions.write_update_report(
        [{"name": "torch", "current": "2.3.0", "latest": "2.4.0"}], path,
        when=long_ago.isoformat(timespec="seconds"))
    assert versions.pending_updates(path) == []


def test_a_fresh_report_is_passed_on(tmp_path) -> None:
    from modules import versions

    path = tmp_path / "updates.json"
    versions.write_update_report(
        [{"name": "torch", "current": "2.3.0", "latest": "2.4.0"}], path)
    assert [item["name"] for item in versions.pending_updates(path)] \
        == ["torch"]


def test_a_missing_report_is_simply_no_news(tmp_path) -> None:
    from modules import versions

    assert versions.pending_updates(tmp_path / "er-is-niets.json") == []


def test_the_check_throttles_itself(tmp_path) -> None:
    """A batch file that has to work out how old a file is, is a batch
    file nobody dares touch again."""
    import importlib.util
    from pathlib import Path

    import modules
    from modules import versions

    path = (Path(modules.__file__).resolve().parents[1] / "tools"
            / "check_updates.py")
    spec = importlib.util.spec_from_file_location("check_updates", path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    report = tmp_path / "updates.json"
    assert not tool.checked_recently(report)
    versions.write_update_report([], report)
    assert tool.checked_recently(report)


def test_the_launcher_starts_the_check_in_the_background() -> None:
    from pathlib import Path

    import modules

    bat = (Path(modules.__file__).resolve().parents[1]
           / "KaraokeToolGUI.bat").read_text(encoding="utf-8")
    line = [n for n in bat.splitlines() if "check_updates.py" in n]
    assert line, "de bat draait de updatecheck niet"
    assert "/b" in line[0], "de check moet op de achtergrond"
    assert "pythonw" in line[0], "en zonder venster"


# --------------------------------------------------------------------------
# B445 - the record that belonged to nobody
# --------------------------------------------------------------------------

def test_without_a_song_nothing_is_written(tmp_path) -> None:
    """This is how output/settings/project.json came into being: a
    context without a song that could write, holding the video titles of
    a song that did not exist yet."""
    from modules.filesystem import ProjectStore

    path = tmp_path / "settings" / "project.json"
    store = ProjectStore(path, writable=False)
    store.set_step("whisper_original", {"segments": 3})
    store.save()
    assert not path.exists()


def test_reading_stays_allowed_without_a_song(tmp_path) -> None:
    """Otherwise an existing file is suddenly invisible."""
    import json as _json

    from modules.filesystem import ProjectStore

    path = tmp_path / "settings" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text(_json.dumps({"created": "toen", "steps":
                                 {"whisper_original": {"segments": 7}}}),
                    encoding="utf-8")
    store = ProjectStore(path, writable=False)
    assert store.get_step("whisper_original") == {"segments": 7}


def test_a_project_with_a_song_writes_as_before(tmp_path) -> None:
    from modules.filesystem import ProjectStore

    path = tmp_path / "settings" / "project.json"
    store = ProjectStore(path)
    store.set_step("whisper_original", {"segments": 3})
    store.save()
    assert path.exists()


def test_a_loose_record_is_named_not_removed(tmp_path) -> None:
    """A program that quietly deletes files in a folder called "output"
    is a program you stop trusting."""
    from modules.filesystem import ProjectPaths, warn_about_stray_store

    paths = ProjectPaths(root=tmp_path)
    stray = paths.output_root / "settings" / "project.json"
    stray.parent.mkdir(parents=True)
    stray.write_text("{}", encoding="utf-8")
    assert warn_about_stray_store(paths) == stray
    assert stray.exists()


def test_no_loose_record_no_warning(tmp_path) -> None:
    from modules.filesystem import ProjectPaths, warn_about_stray_store

    assert warn_about_stray_store(ProjectPaths(root=tmp_path)) is None


def test_the_start_looks_for_it() -> None:
    from pathlib import Path

    import modules

    source = (Path(modules.__file__).resolve().parents[1]
              / "KaraokeTool.py").read_text(encoding="utf-8")
    assert "warn_about_stray_store(paths)" in source
    assert "ProjectStore(paths.project_file, writable=False)" in source


def test_the_chunked_run_end_to_end(tmp_path, monkeypatch) -> None:
    """The whole path once, with Whisper faked out: the whole run keeps
    what it heard, a piece fills the hole, the segments are renumbered in
    time order and the output files are written.

    Worth its length. This runs inside step 1 for every song from now on,
    and an exception here would take the user's whole run with it."""
    from modules import whisper
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    def fake_slice(audio_path, settings, start=0.0, end=None,
                   initial_prompt="", language_override=None,
                   cancelled=None):
        if end is None:                       # the whole song
            return whisper.segments_from_dicts([{
                "index": 0, "text": "een twee", "start": 1.0, "end": 2.0,
                "words": [
                    {"text": "een", "start": 1.0, "end": 1.4,
                     "confidence": 0.9},
                    {"text": "twee", "start": 1.5, "end": 2.0,
                     "confidence": 0.9}]}])
        if start <= 40.0 <= (end or 0.0):     # the piece over the hole
            return whisper.segments_from_dicts([{
                "index": 0, "text": "drie", "start": 40.0, "end": 40.5,
                "words": [{"text": "drie", "start": 40.0, "end": 40.5,
                           "confidence": 0.95}]}])
        return ()

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    windows = [(0.0, 10.0), (20.0, 30.0), (38.0, 45.0)]
    monkeypatch.setattr(whisper, "transcribe_slice", fake_slice)
    monkeypatch.setattr(pipeline, "_original_vocal_windows",
                        lambda c: windows)
    monkeypatch.setattr(pipeline, "lyric_keys", lambda c: frozenset())

    output = paths.output_dir / "original"
    segments, filled, _second = pipeline._transcribe_in_pieces(
        context, tmp_path / "nep.wav", context.config.whisper, "prompt",
        "nl", output)

    assert filled == 1
    assert [s.text for s in segments] == ["een twee", "drie"]
    assert [s.index for s in segments] == [0, 1]
    assert [s.start for s in segments] == sorted(s.start for s in segments)
    assert (output / "segmenten.json").exists()
    assert (output / "run_info.json").exists()


def test_the_song_is_decoded_once_and_not_once_per_piece(tmp_path) -> None:
    """A trial cuts one song and takes as long as it takes. In
    production this is called ten to fifteen times per song, and
    decoding plus resampling the whole song every time is tens of
    seconds of waste per run."""
    import numpy
    import soundfile

    from modules import whisper

    path = tmp_path / "toon.wav"
    rate = 22050
    moment = numpy.linspace(0, 20, rate * 20, endpoint=False)
    soundfile.write(path, (0.2 * numpy.sin(2 * numpy.pi * 440 * moment)
                           ).astype("float32"), rate)

    calls = []
    real_load = None
    import librosa

    real_load = librosa.load

    def counted(*args, **kw):
        calls.append(1)
        return real_load(*args, **kw)

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(librosa, "load", counted)
        whisper._DECODED.clear()
        first = whisper.audio_slice(path, 0.0, 5.0)
        second = whisper.audio_slice(path, 5.0, 10.0)
        third = whisper.audio_slice(path, 10.0, 15.0)
    assert len(calls) == 1, "elk stuk decodeerde het hele liedje opnieuw"
    assert len(first) == len(second) == len(third) == 5 * whisper.SLICE_RATE


def test_a_replaced_audio_file_is_decoded_again(tmp_path) -> None:
    """Otherwise the cache quietly serves the previous song."""
    import numpy
    import soundfile

    from modules import whisper

    path = tmp_path / "toon.wav"
    rate = whisper.SLICE_RATE
    soundfile.write(path, numpy.zeros(rate * 4, dtype="float32"), rate)
    whisper._DECODED.clear()
    assert len(whisper.audio_slice(path)) == rate * 4
    soundfile.write(path, numpy.zeros(rate * 8, dtype="float32"), rate)
    assert len(whisper.audio_slice(path)) == rate * 8


def test_the_whole_song_goes_to_whisper_as_a_path() -> None:
    """No point cutting samples for a slice that is the entire file -
    faster-whisper decodes it perfectly well itself."""
    from modules import whisper

    source = inspect.getsource(whisper.transcribe_slice)
    assert "str(audio_path) if (start <= 0.0 and end is None)" in source


def test_the_version_files_are_redirected_in_tests_too() -> None:
    """The fifteenth-time-you-forget case the fixture exists for."""
    from pathlib import Path

    from modules import versions

    root = Path(versions.__file__).resolve().parents[1] / "docs"
    assert not str(versions.VERSION_LOG).startswith(str(root))
    assert not str(versions.UPDATE_FILE).startswith(str(root))


def test_switching_back_to_no_song_does_not_recreate_the_loose_file() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._switch_instance)
    assert "writable=bool(title)" in source
