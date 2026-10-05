"""1.5.13: every song from the start, every way (v1.0.13, B584).

What is tested is what the trial DOES around Whisper and the timing -
the copies, the reuse of what was heard, the sums and the report - and
above all that the user's own projects and hand timings stay exactly as
they were. Whisper and the timing are stand-ins.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from modules import front_to_back as ftb
from modules import model_register, pipeline, whisper
from modules import whisper_chunks as wc
from modules.config import default_config
from modules.filesystem import ProjectPaths, ProjectStore, ensure_directories
from modules.whisper import Segment, Word

LYRICS = "ik zie de zon\nwij lopen door de stad\n"


def _hand(starts):
    return {"lines": [{"index": n, "text": "x", "crowd": False,
                       "syllables": [{"text": "x", "start": s,
                                      "end": s + 1.0}]}
                      for n, s in enumerate(starts)]}


def _install(tmp_path, songs=("Song_A", "Song_B")):
    root = tmp_path / "Tools" / "KaraokeTool"
    for song in songs:
        paths = ProjectPaths(root=root, song=song)
        ensure_directories(paths)
        (paths.input_dir / "lyrics.txt").write_text(LYRICS, encoding="utf-8")
        (paths.input_dir / "original.mp3").write_bytes(b"mp3")
        (paths.cache_dir / "original_vocals.wav").write_bytes(b"wav" * 10)
        (paths.cache_dir / "transcription_original.json").write_text(
            "[]", encoding="utf-8")
        paths.project_file.write_text(json.dumps({"steps": {
            "source_original": {"sha1": "x"},
            "word_coupling": {"pins": {"1": [2]}},
            "whisper_original": {"segments": 3, "listening": 2},
            "heard_again": {"areas": []}}}), encoding="utf-8")
        (paths.settings_dir / "timing.json").write_text(
            json.dumps(_hand([1.0, 5.0])), encoding="utf-8")
    ProjectPaths(root=root).languages_dir.mkdir(parents=True, exist_ok=True)
    (ProjectPaths(root=root).languages_dir / "nl.json").write_text(
        "{}", encoding="utf-8")
    context = pipeline.AppContext(
        paths=ProjectPaths(root=root), config=default_config(),
        store=ProjectStore(root / "output" / "none.json"))
    return root, context


def _fingerprint(folder: Path) -> dict:
    return {str(p.relative_to(folder)): hashlib.sha1(
        p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()
            and "_to_delete" not in p.parts}


def test_the_zero_measurement_is_the_program_as_shipped() -> None:
    """v1.0.14 (B594): the short night starts from v1.0.13 as shipped."""
    assert ftb.BASELINE.listening == "v1012" and ftb.BASELINE.gap_text
    assert ftb.BASELINE.again == "none"
    assert set(ftb.BASELINE.models) == {"B578", "B579", "B580", "B581"}
    keys = [change.key for change in ftb.CHANGES]
    assert keys == ["piece_hint", "stacked"]
    for change in ftb.CHANGES:
        assert len(set(change.models) - set(ftb.BASELINE.models)) == 1
    assert set(ftb.BOTH.models) == set(ftb.BASELINE.models) | {"B583",
                                                                "B595"}
    assert ftb.BOTH.parts == ("piece_hint", "stacked")


def test_the_scrap_folder_is_next_to_the_program(tmp_path) -> None:
    root, context = _install(tmp_path)
    assert ftb.scratch_root(context) == \
        root.parent / "_to_delete" / ftb.SCRATCH_NAME


def test_the_copy_leaves_the_users_work_behind(tmp_path) -> None:
    root, context = _install(tmp_path)
    copy = ftb.copy_project(context, "Song_A", tmp_path / "w", "v1012")
    steps = json.loads(copy.paths.project_file.read_text("utf-8"))["steps"]
    assert "word_coupling" not in steps and "heard_again" not in steps
    assert "whisper_original" not in steps and "source_original" in steps
    assert not (copy.paths.cache_dir
                / "transcription_original.json").exists()
    assert (copy.paths.cache_dir / "original_vocals.wav").exists()
    assert (copy.paths.input_dir / "lyrics.txt").exists()
    assert (tmp_path / "w" / "languages" / "nl.json").exists()
    old = ftb.copy_project(context, "Song_A", tmp_path / "o", "v1011")
    step = old.store.get_step("whisper_original")
    assert step is not None and not pipeline._listens_anew(step)


def test_the_copy_is_a_copy_not_a_link(tmp_path) -> None:
    """The pipeline writes into its cache; through a hard link that
    would be the user's own file."""
    root, context = _install(tmp_path)
    copy = ftb.copy_project(context, "Song_A", tmp_path / "w", "v1012")
    (copy.paths.cache_dir / "original_vocals.wav").write_bytes(b"changed")
    mine = ProjectPaths(root=root, song="Song_A").cache_dir
    assert (mine / "original_vocals.wav").read_bytes() == b"wav" * 10


def test_a_question_is_heard_once(tmp_path) -> None:
    asked = []

    def real(audio, settings, start=0.0, end=None, initial_prompt="",
             language_override=None, cancelled=None):
        asked.append((start, end))
        return (Segment(0, "ja", 1.0, 1.5, (Word("ja", 1.0, 1.5, 0.9),)),)

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"x" * 100)
    heard = ftb.HeardOnce(tmp_path / "whisper", "Song_A")
    ask = heard.wrap(real)
    settings = default_config().whisper
    first = ask(audio, settings, start=0.0, end=12.0, initial_prompt="h")
    again = ask(audio, settings, start=0.0, end=12.0, initial_prompt="h")
    other = ask(audio, settings, start=0.0, end=12.0, initial_prompt="k")
    assert len(asked) == 2 and first == again and other
    # And across a broken-off night: read back from disk.
    later = ftb.HeardOnce(tmp_path / "whisper", "Song_A").wrap(real)
    later(audio, settings, start=0.0, end=12.0, initial_prompt="h")
    assert len(asked) == 2


def test_the_aligner_is_asked_once_as_well(tmp_path) -> None:
    calls = []

    timed = (Segment(0, "ja", 1.1, 1.4, (Word("ja", 1.1, 1.4, 0.9),)),)

    def real(audio, segments, language, device="cpu"):
        calls.append(len(segments))
        return timed

    audio = tmp_path / "v.wav"
    audio.write_bytes(b"x")
    refine = ftb.HeardOnce(tmp_path, "S").wrap_aligner(real)
    segments = (Segment(0, "ja", 1.0, 1.5, (Word("ja", 1.0, 1.5, 0.9),)),)
    assert refine(audio, segments, "nl") == timed
    assert refine(audio, segments, "nl") == timed
    refine(audio, segments, "en")
    assert calls == [1, 1]


def test_cutting_everywhere_covers_the_song_with_overlap() -> None:
    pieces = ftb._everywhere([], 30.0)
    assert pieces[0].start == 0.0 and pieces[-1].end == pytest.approx(30.0)
    for a, b in zip(pieces, pieces[1:]):
        assert b.start == pytest.approx(a.end - wc.OVERLAP_S)
        assert a.duration <= wc.FORCED_S + 1e-6


def test_the_ways_of_a_variant_are_undone_afterwards(tmp_path) -> None:
    from modules import listen_again

    from modules import word_alignment

    before = (word_alignment.refine, whisper.transcribe_slice,
              whisper.transcribe, wc.cut_points,
              pipeline._with_gap_text, listen_again.HINT,
              model_register.current_settings())
    variant = ftb.Variant("x", listening="everywhere", gap_text=False,
                          hint="expected", models=("B578",))
    heard = ftb.HeardOnce(tmp_path, "S")
    try:
        with ftb.ways(variant, heard):
            assert wc.cut_points is ftb._everywhere
            assert listen_again.HINT == "expected"
            assert pipeline._with_gap_text(None, ["s"]) == ("s",)
            assert model_register.enabled("B578")
            assert not model_register.enabled("B579")
    finally:
        model_register.restore_all()
    after = (word_alignment.refine, whisper.transcribe_slice,
             whisper.transcribe, wc.cut_points,
             pipeline._with_gap_text, listen_again.HINT,
             model_register.current_settings())
    assert after == before


def _result(starts, hand, unheard=1.0, in_text=90.0):
    return {"starts": starts, "hand": hand, "unheard": unheard,
            "in_text": in_text, "words": 3, "taken": 0}


def test_the_sums_hold_every_way_against_the_zero_measurement() -> None:
    hand = [1.0, 5.0, 9.0]
    results = {"S": {"baseline": _result([1.0, 6.0, 9.0], hand),
                     "better": _result([1.0, 5.0, 9.0], hand),
                     "worse": _result([2.0, 6.0, 9.0], hand)}}
    zero = ftb.tally(results, "baseline", ["S"])
    better = ftb.tally(results, "better", ["S"])
    worse = ftb.tally(results, "worse", ["S"])
    assert zero.mean == pytest.approx(1.0 / 3)
    assert better.mean == 0.0 and better.fixed == 1 and better.broken == 0
    assert worse.broken == 1 and worse.fixed == 0
    closer = ftb.tally({"S": {"baseline": results["S"]["baseline"],
                              "closer": _result([1.0, 5.5, 9.0], hand)}},
                       "closer", ["S"])
    assert closer.fixed == 0, "closer but still wrong is not put right"
    missing = ftb.tally(results, "absent", ["S"])
    assert missing.failed == 1 and missing.lines == 0


def test_a_third_of_the_songs_checks_the_combination() -> None:
    build, check = ftb.split([f"s{n}" for n in range(9)])
    assert len(check) == 3 and not set(build) & set(check)


def test_the_combination_keeps_only_what_helps_on_top(tmp_path) -> None:
    hand = [1.0, 5.0]
    changes = (ftb.Variant("a", gap_text=False),
               ftb.Variant("b", models=("B578",)),
               ftb.Variant("c", models=("B579",)))
    results = {"S": {"baseline": _result([2.0, 6.0], hand),
                     "a": _result([1.5, 5.5], hand),
                     "b": _result([1.8, 5.8], hand),
                     "c": _result([3.0, 7.0], hand)}}

    def results_for(variant):
        # a together with b is worse than a alone
        value = {("a",): [1.5, 5.5], ("a", "b"): [1.7, 5.7]}.get(
            variant.parts, [2.0, 6.0])
        results["S"][variant.key] = _result(value, hand)

    chosen = ftb.greedy(results_for, results, changes, ["S"],
                        lambda: False)
    assert chosen.parts == ("a",) and not chosen.gap_text
    assert set(ftb.combined(changes[:2]).models) == set(
        ftb.BASELINE.models) | {"B578"}


def test_listening_again_above_the_threshold_only(tmp_path,
                                                  monkeypatch) -> None:
    areas = [{"low": 1.0, "high": 2.0, "replaced": [],
              "candidates": [{"kind": "aligned", "words": [["a", 1, 2, .9]],
                              "score": 0.8}]},
             {"low": 3.0, "high": 4.0, "replaced": [],
              "candidates": [{"kind": "aligned", "words": [["b", 3, 4, .1]],
                              "score": 0.2}]}]
    taken = []
    monkeypatch.setattr(pipeline, "listen_again", lambda c, **k: areas)
    monkeypatch.setattr(pipeline, "accept_heard_again",
                        lambda c, chosen: taken.append(chosen) or len(chosen))
    assert ftb._take_over(None, "threshold", lambda: False) == 1
    assert ftb._take_over(None, "best", lambda: False) == 2


def test_a_night_run_measures_reports_and_touches_nothing(
        tmp_path, monkeypatch) -> None:
    from modules import test_panel

    root, context = _install(tmp_path)
    before = _fingerprint(root)
    whisper_calls = []

    def fake_detect(copy, track, progress=None, cancelled=None):
        found = whisper.transcribe_slice(
            copy.paths.cache_dir / "original_vocals.wav",
            copy.config.whisper, start=0.0, end=None, initial_prompt="h")
        whisper.save_segments(found, pipeline.transcript_cache(copy, track))
        copy.store.set_step("whisper_original", {"segments": len(found)})

    def fake_slice(audio, settings, start=0.0, end=None, initial_prompt="",
                   language_override=None, cancelled=None):
        whisper_calls.append((audio, start, end, initial_prompt))
        return (Segment(0, "ik zie", 1.0, 2.0,
                        (Word("ik", 1.0, 1.4, 0.9),
                         Word("zie", 1.4, 2.0, 0.9))),)

    real_pairing = test_panel._regression_module().paired_lines

    class _Timing:
        paired_lines = staticmethod(real_pairing)

        @staticmethod
        def timing_for(copy, hand):
            from modules.timing import Syllable, TimedLine
            steps = copy.store.get_step("whisper_original") or {}
            late = 0.5 if "B595" in model_register.disabled_now() else 0.0
            return ([TimedLine(index=n, text="x", crowd=False, syllables=(
                Syllable("x", float(line["syllables"][0]["start"]) + late,
                         float(line["syllables"][0]["start"]) + 1),))
                     for n, line in enumerate(hand)], len(hand) + 0 * len(
                         steps))

    monkeypatch.setattr(pipeline, "detect_track", fake_detect)
    monkeypatch.setattr(whisper, "transcribe_slice", fake_slice)
    monkeypatch.setattr(pipeline, "_original_vocal_windows",
                        lambda c: [(0.5, 3.0)])
    monkeypatch.setattr(test_panel, "_regression_module", lambda: _Timing)
    from modules import rhythm
    monkeypatch.setattr(rhythm, "is_available", lambda: False)
    said = []
    try:
        text = ftb.run(context, lambda *a: said.append(a), lambda: False)
    finally:
        model_register.restore_all()

    assert _fingerprint(root) == before, "the user's files stay as they were"
    assert "## " + ftb.t("front_to_back_title") in text
    for variant in (ftb.BASELINE, *ftb.CHANGES, ftb.BOTH):
        assert ftb._label(variant) in text
    # The whole song is heard once per song, however many ways ask for
    # it; "Listen again" asks per hint, and each hint once.
    wholes = [call for call in whisper_calls if call[2] is None]
    assert len(wholes) == 2
    assert len(whisper_calls) == len({call[1:] + (call[0].parts[-2],)
                                      for call in whisper_calls})
    assert "failed" not in json.dumps(json.loads(
        (ftb.scratch_root(context) / "results.json").read_text("utf-8")))
    scrap = ftb.scratch_root(context)
    assert (scrap / "results.json").exists()
    assert not any((scrap / "projects").glob("*/*")), \
        "every copy goes once it has been measured"

    # A second night reuses what the first one measured.
    monkeypatch.setattr(ftb, "measure_one", lambda *a, **k: pytest.fail(
        "measured again"))
    again = ftb.run(context, lambda *a: None, lambda: False)
    model_register.restore_all()
    assert ftb.t("front_to_back_title") in again


def test_the_panel_offers_it_as_a_deliberate_choice() -> None:
    from modules import test_panel

    action = next(a for a in test_panel.ACTIONS if a.code == "1.5.13")
    assert action.on_request and not action.heavy
    # v1.0.15: two nights answered what it was for; off, not deleted.
    assert action.done and callable(action.function)
    assert action not in test_panel.visible_actions()


def test_a_failure_or_a_changed_hand_timing_is_measured_again(
        tmp_path, monkeypatch) -> None:
    root, context = _install(tmp_path, songs=("Song_A",))
    calls = []

    def measure(ctx, song, variant, work, heard, cancelled):
        calls.append(variant.key)
        if len(calls) == 1:
            return {"failed": "out of memory"}
        return _result([1.0, 5.0], [1.0, 5.0])

    monkeypatch.setattr(ftb, "measure_one", measure)
    monkeypatch.setattr(ftb, "greedy", lambda *a, **k: ftb.BASELINE)
    ftb.run(context, lambda *a: None, lambda: False)
    first = len(calls)
    ftb.run(context, lambda *a: None, lambda: False)
    assert len(calls) == first + 1, "only the failure is measured again"
    hand = ProjectPaths(root=root, song="Song_A").settings_dir / "timing.json"
    hand.write_text(json.dumps(_hand([1.5, 5.0])), encoding="utf-8")
    ftb.run(context, lambda *a: None, lambda: False)
    assert len(calls) == 2 * first + 1, "a new hand timing: all again"


def test_an_aligner_that_gave_up_is_not_remembered(tmp_path) -> None:
    calls = []

    def gave_up(audio, segments, language, device="cpu"):
        calls.append(1)
        return tuple(segments)

    audio = tmp_path / "v.wav"
    audio.write_bytes(b"x")
    refine = ftb.HeardOnce(tmp_path, "S").wrap_aligner(gave_up)
    segments = (Segment(0, "ja", 1.0, 1.5, ()),)
    refine(audio, segments, "nl")
    refine(audio, segments, "nl")
    assert calls == [1, 1]


def test_measuring_again_means_hearing_again(tmp_path, monkeypatch) -> None:
    from modules import test_panel

    root, context = _install(tmp_path, songs=("Song_A",))
    heard = ftb.scratch_root(context) / "whisper"
    heard.mkdir(parents=True)
    (heard / "Song_A.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ftb, "measure_one", lambda *a, **k: _result(
        [1.0, 5.0], [1.0, 5.0]))
    monkeypatch.setattr(ftb, "greedy", lambda *a, **k: ftb.BASELINE)
    monkeypatch.setattr(test_panel, "REMEASURE", True)
    ftb.run(context, lambda *a: None, lambda: False)
    assert not (heard / "Song_A.json").exists()
