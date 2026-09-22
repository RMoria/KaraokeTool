"""What a test run and a panel action may NOT touch (B566/B567).

Two guards over the same kind of damage, one folder apart.

B566 is about the user's own documents. ``conftest`` moves seven
constants that point into ``docs/`` aside for every test, and that list
had a hole: ``docs/metingen.md`` is written by
``tools/timing_regression.py``, which is loaded by file path and
therefore has no module on that list at all. A test that called its
``main(--record)`` rewrote the real measurement file from inside pytest.
The rule is now the session guard in ``conftest`` - the whole folder,
read before and held against itself afterwards - and the test here
proves the known hole is shut.

B567 is about the user's own PROJECTS. The header of
``modules/test_panel.py`` promises which actions write into them, and
that promise was wrong for years: three of the five reports that make
up action 1.5.2 saved a ``word_coupling`` step into the
``project.json`` of every project they touched - the user's hand-made
pin work, written over by a report that only claims to look. B567
pinned that behaviour as it was; B571 repaired it, and this file
turned around with it. It now holds the reports to writing nothing at
all, and holds the repair to the other side of the same coin: what a
read-only report SEES has to be what the program sees, or the
measurement is worth nothing.

"The projects", and not the whole installation: a panel action also
writes the measurement history and its own report into ``docs/``, and
that is what ``with_history`` is for. That folder is what B566 above
guards.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from modules import pipeline, test_panel

ROOT = Path(__file__).resolve().parents[1]

#: B567: which panel actions write into the projects on purpose, by
#: code, with the reason. Everything the panel shows is either here or
#: has to leave the projects byte-identical - a new visible action
#: without a decision fails
#: :func:`test_every_visible_action_is_silent_or_declared`.
WRITES_ON_PURPOSE = {
    "1.5.1": "fills the transcription cache and rebuilds a missing "
             "timing_auto.json (B463) - that IS the job of the action",
    "1.5.12": "renders the videos again (B531) - a job, not a "
              "measurement",
}

#: B571: the visible actions that write NOTHING, with the test in this
#: file that proves it. Together with :data:`WRITES_ON_PURPOSE` this
#: covers every line the panel shows, so a new action cannot slip in
#: without somebody saying which of the two it is.
PROVEN_SILENT = {
    "1.5.2": "test_action_1_5_2_writes_nothing_at_all",
}

#: One segment of sung words. Two of them are not in the lyrics, so
#: ``missing_repetitions`` has something to report.
WORDS = (("shalalie", 10.0, 10.7, 0.7), ("shalala", 10.7, 11.4, 0.7),
         ("shalalie", 11.4, 12.1, 0.7), ("shalala", 12.1, 12.9, 0.7),
         ("ja", 13.0, 13.2, 0.9), ("ik", 13.2, 13.4, 0.9),
         ("weet", 13.4, 13.7, 0.9), ("het", 13.7, 13.9, 0.9),
         ("alweer", 13.9, 14.4, 0.9))

LYRICS = "shalalie shalala\nja ik weet het alweer\n"
KARAOKE = "biertje hier\nen morgen nog een keer\n"


def _segments() -> list[dict]:
    return [{"index": 0, "text": " ".join(w[0] for w in WORDS),
             "start": WORDS[0][1], "end": WORDS[-1][2],
             "words": [{"text": text, "start": start, "end": end,
                        "confidence": confidence}
                       for text, start, end, confidence in WORDS]}]


def _project(root: Path, song: str):
    """One project on disk, as complete as the reports need it.

    Lyrics and karaoke text in ``input/``, the transcription in the
    cache AND as the diagnostics copy in ``original/segments.json``
    (without that one the yardstick skips the project and measures
    nothing at all), and a hand-corrected timing beside the automatic
    one - that pair is what makes a project measurable.
    """
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton, save_timing

    paths = ProjectPaths(root=root, song=song)
    ensure_directories(paths)
    (paths.input_dir / "lyrics.txt").write_text(LYRICS, encoding="utf-8")
    (paths.input_dir / "karaoke_text.txt").write_text(KARAOKE,
                                                      encoding="utf-8")
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    cache = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(_segments()), encoding="utf-8")
    context.store.set_step("whisper_original", {"segments": 1})
    stored = paths.output_dir / "original" / "segments.json"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_text(json.dumps(_segments()), encoding="utf-8")
    lines = generate_skeleton(
        (TextLine(index=0, text="biertje hier", crowd=False, block=0),
         TextLine(index=1, text="en morgen nog een keer", crowd=False,
                  block=0)),
        {0: (10.0, 11.4), 1: (13.0, 14.4)})
    save_timing(lines, paths.timing_file, project=song, version="0.1")
    save_timing(lines, paths.timing_auto_file, project=song, version="0.1")
    return context


def _installation(tmp_path: Path, name: str = "KaraokeTool",
                  songs=("Song_A", "Song_B")):
    """An installation with a couple of projects, under its own folder.

    Under its own folder on purpose: ``tmp_path`` is also where
    ``conftest`` sends the redirected reports, and a measurement history
    landing beside the projects would look like a project that changed.
    """
    root = tmp_path / name
    contexts = [_project(root, song) for song in songs]
    return root, contexts[0]


def _snapshot(root: Path) -> dict:
    """``path -> (size, sha1)`` for every file under ``root``.

    With forward slashes, because the expected paths below are written
    that way and ``str()`` of a relative path gives backslashes on the
    machine this program actually runs on.

    Folders are in it too, by presence (B571). A file snapshot cannot
    see a folder being made, and ``context_for_project`` made six of
    them per project it looked at - which is not writing, but it is not
    "leaves the project alone" either.
    """
    state = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_dir():
            state[name + "/"] = (-1, "")
        elif path.is_file():
            data = path.read_bytes()
            state[name] = (len(data), hashlib.sha1(data).hexdigest())
    return state


def _changed(before: dict, after: dict) -> list[str]:
    return sorted(name for name in set(before) | set(after)
                  if before.get(name) != after.get(name))


def _steps(root: Path, song: str) -> dict:
    path = root / "output" / song / "settings" / "project.json"
    return json.loads(path.read_text(encoding="utf-8"))["steps"]


def _run(function, context):
    return function(context, lambda *a, **k: None, lambda: False)


# --------------------------------------------------------------------------
# B566 - the hole in the redirect list: docs/metingen.md
# --------------------------------------------------------------------------

def test_recording_the_yardstick_stays_out_of_the_documents(
        tmp_path, monkeypatch) -> None:
    """``main(--record)`` may not reach the real ``docs/metingen.md``.

    Proven this week: it did. The tool builds its own path out of
    ``__file__`` and hands it to ``note``, so there is no constant for
    the redirect list to move aside - and being loaded by file path, it
    has no module on that list either. ``conftest`` therefore moves the
    only thing that writes the file, ``note``, and lets a path outside
    ``docs/`` through untouched.

    Loaded the way the app loads it (``_regression_module``), because
    that is the copy a test gets and therefore the copy that has to be
    harmless.
    """
    real = ROOT / "docs" / "metingen.md"
    before = real.read_bytes() if real.exists() else None

    root, _context = _installation(tmp_path)
    module = test_panel._regression_module()
    monkeypatch.setattr(sys, "argv",
                        ["timing_regression.py", str(root / "output"),
                         "--record"])
    assert module.main() == 0

    assert (real.read_bytes() if real.exists() else None) == before
    written = tmp_path / "metingen.md"
    assert written.exists(), "the recording went somewhere else entirely"
    assert "| Song_A |" in written.read_text(encoding="utf-8")


def test_a_path_of_its_own_is_left_alone(tmp_path) -> None:
    """The redirect is about ``docs/``, not about the tool.

    A test that hands the yardstick a file of its own has to be able to
    read back what it wrote - otherwise the guard costs more than it
    saves.
    """
    module = test_panel._regression_module()
    mine = tmp_path / "elsewhere" / "metingen.md"
    mine.parent.mkdir(parents=True)
    module.note([{"project": "Song_A", "lines": 2, "coupled": 2,
                  "moved": 1, "new_moved": 0.25}], mine, "0.1", "2026-01-01")
    assert "| Song_A |" in mine.read_text(encoding="utf-8")


def test_the_snapshot_reaches_into_the_subfolders(
        tmp_path, monkeypatch) -> None:
    """Every file, including the ones in a subfolder of ``docs/``.

    B440 was one constant short and B566 one module; a snapshot that
    stopped at the top level would be the same mistake a third time.
    Size and sha1 both: a report rewritten with the output of an empty
    test project can be exactly as long as the real one.

    Measured on a folder of its own, because which files lie in the
    real ``docs/`` differs per installation - the measurement files are
    the user's and are not in the published copy. That the snapshot
    really points at the real folder is the test below.
    """
    import conftest

    (tmp_path / "manual.md").write_bytes(b"one")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "run.md").write_bytes(b"two")
    (tmp_path / "reports" / "deeper").mkdir()
    (tmp_path / "reports" / "deeper" / "run.md").write_bytes(b"three")
    monkeypatch.setattr(conftest, "DOCS", tmp_path)

    state = conftest._documents_now()
    assert set(state) == {"manual.md",
                          str(Path("reports") / "run.md"),
                          str(Path("reports") / "deeper" / "run.md")}
    assert state["manual.md"] == (3, hashlib.sha1(b"one").hexdigest())
    assert state[str(Path("reports") / "deeper" / "run.md")] == (
        5, hashlib.sha1(b"three").hexdigest())


def test_the_session_guard_watches_the_real_documents_folder() -> None:
    """And it is the user's own ``docs/`` that is being watched.

    The test above proves the walk; this one proves where it walks. A
    snapshot over the wrong folder is empty and stays green forever,
    which is exactly the hole B566 was about.
    """
    import conftest

    assert conftest.DOCS == ROOT / "docs"
    state = conftest._documents_now()
    assert state, "docs/ is not being watched at all"
    for name in ("development_log.md", "manual.md"):
        assert name in state, name
        data = (ROOT / "docs" / name).read_bytes()
        assert state[name] == (len(data), hashlib.sha1(data).hexdigest())


# --------------------------------------------------------------------------
# B567 - a panel action may not change the user's projects
# --------------------------------------------------------------------------

def test_every_visible_action_is_silent_or_declared() -> None:
    """A new line in the panel forces a decision here.

    The header of ``test_panel`` promised for years that the actions
    wrote nothing "with exactly two exceptions", and it was wrong
    because nobody had to say so anywhere. Now they do: every visible
    action is either in :data:`WRITES_ON_PURPOSE` with a written
    reason, or in :data:`PROVEN_SILENT` with the name of the test below
    that holds it to it.
    """
    visible = [action.code for action in test_panel.visible_actions()]
    assert set(WRITES_ON_PURPOSE) | set(PROVEN_SILENT) == set(visible)
    assert not set(WRITES_ON_PURPOSE) & set(PROVEN_SILENT)
    for code, reason in WRITES_ON_PURPOSE.items():
        assert len(reason) > 30, code
    for code, name in PROVEN_SILENT.items():
        assert name in globals(), f"{code}: {name} is not in this file"


def test_the_reports_that_only_look_leave_the_projects_alone(
        tmp_path) -> None:
    """Two of the five parts of 1.5.2 really are read-only.

    ``benchmark_status`` reads the files and counts, and the yardstick
    rebuilds the whole pipeline in a temporary directory of its own
    (B384) - that copy is exactly why it may touch a coupling without
    the user's project noticing. Byte for byte over the whole
    installation, so a stray cache file or a rewritten timing counts as
    damage too.
    """
    root, context = _installation(tmp_path)
    before = _snapshot(root)
    assert "Song_A" in _run(test_panel.benchmark_status, context)
    assert "Song_A" in _run(test_panel.yardstick, context)
    assert _changed(before, _snapshot(root)) == []


@pytest.mark.parametrize("part", ["project_report", "missing_repetitions",
                                  "syllable_checks"])
def test_the_three_reports_that_used_to_write_leave_it_alone(
        tmp_path, part) -> None:
    """B571: the three that DID write, and now write nothing.

    ``project_report`` (through ``_structure_rows``) and
    ``syllable_checks`` go through ``pipeline.build_coupling``,
    ``missing_repetitions`` through ``pipeline.word_coupling_view``, and
    all three saved a ``word_coupling`` step in every project they
    touched - measured on this fixture, ``project.json`` went from 161
    to 434 bytes. Not because they wanted to write, but because reading
    a coupling runs the pin conversions of B309/B417/B506 and those
    write their result back.

    Each report now asks for its projects through
    ``pipeline.read_only``, so the conversions still run and the report
    sees the same thing - only nothing is written. Byte for byte over
    the whole installation, so a stray cache file counts as damage too.
    """
    root, context = _installation(tmp_path)
    before = _snapshot(root)

    text = _run(getattr(test_panel, part), context)

    assert "Song_A" in str(text), "the report has to have looked"
    assert _changed(before, _snapshot(root)) == []
    for song in ("Song_A", "Song_B"):
        assert set(_steps(root, song)) == {"whisper_original"}


def test_a_report_does_not_touch_the_users_own_pin_work(tmp_path) -> None:
    """The step that holds handwork stays exactly as the user left it.

    This is what the old exception cost him. The report read the
    coupling and saved it back with the relocation description
    (``marks``) and the list fingerprints beside it - the path that
    relocates pins on its way, over the one step in ``project.json``
    that IS handwork. Now it reads and stops there, byte for byte.
    """
    root, context = _installation(tmp_path)
    pipeline.set_word_pins(context, {0: [1]})
    kept = context.store.get_step("word_coupling")
    assert set(kept) == {"pins", "layout", "lyrics_layout", "updated"}
    before = _snapshot(root)

    _run(test_panel.project_report, context)

    assert _steps(root, "Song_A")["word_coupling"] == kept
    assert _changed(before, _snapshot(root)) == []


def test_the_conversions_still_run_on_the_way(tmp_path) -> None:
    """Read-only may not mean "reads something else".

    The pin conversions (B309/B417/B506) are what made the reports
    write, and switching them off instead of only their writing would
    give the report a different answer than the program gets. So the
    same coupling is asked for twice - once through a record that
    writes and once through one that does not - and the two have to
    agree.
    """
    root, context = _installation(tmp_path)
    pipeline.set_word_pins(context, {0: [1]})
    quiet = pipeline.read_only(context)
    before = _snapshot(root)

    seen = pipeline.word_coupling_view(quiet)

    assert _changed(before, _snapshot(root)) == []
    writing = pipeline.word_coupling_view(context)
    assert seen == writing


def test_action_1_5_2_writes_nothing_at_all(tmp_path) -> None:
    """The whole action, the way the panel runs it.

    Per part is where the truth is, but the user clicks one button, and
    what that button costs him is now nothing: not a project record,
    not a timing, not a text, not a cache file. The five parts together
    are a measurement, and a measurement that changes what it measures
    is not one.
    """
    root, context = _installation(tmp_path)
    before = _snapshot(root)

    text = _run(test_panel.check_all_projects, context)

    assert "Song_A" in text
    assert _changed(before, _snapshot(root)) == []
    for song in ("Song_A", "Song_B"):
        assert set(_steps(root, song)) == {"whisper_original"}


def test_a_report_starts_no_demucs(tmp_path, monkeypatch) -> None:
    """1.5.2 promises files that are lying there anyway, in a minute.

    ``syllable_checks`` asks for the vocal stem twice on its way. When
    that stem is not in the cache, making it is Demucs: minutes per
    project, two mp3s in the user's output folder and a wav in his
    cache - from an action that says it only looks. Filling that cache
    is 1.5.1, a button of its own.
    """
    root, context = _installation(tmp_path)
    asked = []
    monkeypatch.setattr(pipeline.separation, "is_available",
                        lambda: asked.append("asked") or True)

    quiet = pipeline.read_only(context)
    assert pipeline.ensure_original_vocals(quiet) is None
    assert asked == [], "a report asked Demucs whether it could run"

    # ... while the same call from the program itself does go on.
    pipeline.ensure_original_vocals(context)
    assert asked == ["asked"]


def test_a_report_makes_no_folders(tmp_path) -> None:
    """Not writing is not the same as leaving alone.

    ``context_for_project`` calls ``ensure_directories`` for every
    project it hands out, which makes six folders. For the program that
    is right - it may be about to write in them. A report found its
    projects by looking, so they are already there.
    """
    import shutil

    root, context = _installation(tmp_path)
    shutil.rmtree(root / "cache" / "Song_B")
    before = _snapshot(root)

    other = pipeline.context_for_project(pipeline.read_only(context),
                                         "Song_B")

    assert other.store.quiet
    assert _changed(before, _snapshot(root)) == []


def test_the_program_still_writes_when_no_song_is_chosen_yet(
        tmp_path) -> None:
    """The trap under B571, and the reason for a second flag.

    The program's own context starts WITHOUT a song (B111), so its
    record is not writable - that is B445. A panel action walks from
    that context to every project, and if "may not write" were one
    flag, those projects would all be read-only: 1.5.1 would fill a
    cache whose checksum it cannot record and 1.5.12 would render
    videos that ``project.json`` never hears about. Silently, because a
    record that does not write does not complain.
    """
    from dataclasses import replace
    from modules.filesystem import ProjectStore

    root, context = _installation(tmp_path)
    at_startup = replace(context, store=ProjectStore(
        context.paths.project_file, writable=False))

    other = pipeline.context_for_project(at_startup, "Song_B")

    assert other.store.writable and not other.store.quiet
    other.store.set_step("video", {"file": "x.mp4"})
    assert "video" in _steps(root, "Song_B")
