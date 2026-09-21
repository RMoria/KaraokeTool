"""Tests for v0.110.0: B353, B354 and the temporary button 1.5.

B353 - the video that was made is no longer declared invalid because
       something upstream changes.
B354 - rendering asks what should happen to an existing video; "keep
       both side by side" numbers the NEW one.
1.5  - temporary button that puts the transcription cache file back
       without throwing anything away.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import dependencies as deps  # noqa: E402
from modules import pipeline  # noqa: E402
from modules.config import default_config  # noqa: E402
from modules.filesystem import (ProjectPaths, ProjectStore,  # noqa: E402
                                ensure_directories)


def _context(tmp_path: Path, name: str = "Proef"):
    paths = ProjectPaths(root=tmp_path, song=name)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B353: the video stays
# --------------------------------------------------------------------------

def test_the_video_hangs_on_nothing_any_more() -> None:
    assert not deps.ARTEFACTS["video"].sources


def test_a_new_transcription_leaves_the_video_standing() -> None:
    """Everything below it lapses, the video does not."""
    steps, _metas, files = deps.invalidation_plan(
        ["whisper_original"], (), include_changed=False)
    assert "timing" in steps and "coupling" in steps   # those do lapse
    assert "video" not in steps
    assert not any("video" in f for f in files)


def test_a_timing_change_leaves_the_video_standing_too() -> None:
    steps, _metas, _files = deps.invalidation_plan(
        ["timing"], (), include_changed=False)
    assert "video" not in steps


# --------------------------------------------------------------------------
# B354: ask instead of overwrite
# --------------------------------------------------------------------------

def test_the_file_name_of_the_render(tmp_path) -> None:
    context = _context(tmp_path, "Biertje")
    context.store.set_meta("display_name", "Lied C")
    target = pipeline.video_target(context)
    assert target.name == "Lied C.mp4"
    assert target.parent == context.paths.output_dir


def test_another_combination_gets_its_own_name(tmp_path) -> None:
    """B271 still stands: a deviating render does not collide with the
    ordinary one."""
    context = _context(tmp_path, "Biertje")
    context.store.set_meta("display_name", "Biertje")
    normal = pipeline.video_target(context, "karaoke", "karaoke")
    other = pipeline.video_target(context, "origineel", "vocals")
    assert normal != other


def test_the_sequence_number_goes_to_the_new_one(tmp_path) -> None:
    """The existing video is never touched."""
    existing = tmp_path / "Biertje.mp4"
    existing.write_bytes(b"oud")
    following = pipeline.next_video_target(existing)
    assert following.name == "Biertje_2.mp4"
    assert existing.read_bytes() == b"oud"
    following.write_bytes(b"nieuw")
    assert pipeline.next_video_target(existing).name == "Biertje_3.mp4"


def test_the_render_uses_the_target_of_its_caller() -> None:
    """The GUI passes the chosen path on; run_video has to follow it."""
    import inspect

    signature = inspect.signature(pipeline.run_video)
    assert "target" in signature.parameters
    source = inspect.getsource(pipeline.run_video)
    assert "if target is None:" in source


def test_the_gui_asks_before_it_overwrites() -> None:
    from modules import gui

    source = __import__("inspect").getsource(gui.MainWindow._do_render_video)
    assert "video_target" in source and "_ask_video_exists" in source


# --------------------------------------------------------------------------
# 1.5: put the cache back without throwing anything away
# --------------------------------------------------------------------------

def _project(root: Path, name: str, *, step: bool, cache: bool,
             audio: bool = True) -> None:
    paths = ProjectPaths(root=root, song=name)
    ensure_directories(paths)
    if audio:
        (paths.input_dir / "original.mp3").write_bytes(b"x")
    store = ProjectStore(paths.project_file)
    if step:
        store.set_step("whisper_original", {"language": "nl"})
    else:
        store.set_meta("display_name", name)
    if cache:
        (paths.cache_dir / "transcription_original.json").write_text(
            "[]", encoding="utf-8")


def test_only_projects_with_a_hole_are_named(tmp_path) -> None:
    _project(tmp_path, "MetCache", step=True, cache=True)
    _project(tmp_path, "ZonderCache", step=True, cache=False)
    _project(tmp_path, "NooitGedraaid", step=False, cache=False)
    _project(tmp_path, "GeenAudio", step=True, cache=False, audio=False)
    context = _context(tmp_path, "MetCache")
    assert pipeline.projects_without_cache(context) == ["ZonderCache"]


def test_the_sister_context_points_at_the_other_project(tmp_path) -> None:
    _project(tmp_path, "Eerste", step=True, cache=True)
    _project(tmp_path, "Tweede", step=True, cache=False)
    context = _context(tmp_path, "Eerste")
    other = pipeline.context_for_project(context, "Tweede")
    assert other.paths.song == "Tweede"
    assert other.config.song.title == "Tweede"
    assert other.paths.root == context.paths.root


def test_an_existing_cache_is_left_alone(tmp_path) -> None:
    _project(tmp_path, "MetCache", step=True, cache=True)
    context = _context(tmp_path, "MetCache")
    assert pipeline.fill_transcription_cache(context) is False


def test_filling_the_cache_throws_nothing_away() -> None:
    """Its whole reason for existing: no step bookkeeping, no cleanup."""
    import inspect

    source = inspect.getsource(pipeline.fill_transcription_cache)
    assert "set_step" not in source
    assert "invalidate" not in source
    assert "save_segments" in source


def test_the_button_stands_on_tab_1(qapp=None, tmp_path=None) -> None:
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    import tempfile

    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from modules import gui
    from modules.translations import t

    with tempfile.TemporaryDirectory() as tmp:
        window = gui.MainWindow(_context(Path(tmp), "Proef"))
        names = [b.text() for b in window._step_buttons]
    assert t("step_fill_cache") in names
    assert names[0].startswith("1.1.") and names[-1].startswith("1.5.")


def test_filling_the_cache_gets_a_callable_stop_question(tmp_path,
                                                         monkeypatch) -> None:
    """The reported error: 'Event' object is not callable.

    ``whisper.transcribe`` wants a function that returns ``True`` when
    it has to stop, not a ``threading.Event``.
    """
    import threading

    from modules import whisper as whisper_module

    _project(tmp_path, "Zonder", step=True, cache=False)
    context = pipeline.context_for_project(_context(tmp_path, "Zonder"),
                                           "Zonder")
    seen = {}

    def fake_transcribe(wav, settings, output_dir, progress=None,
                        language_override=None, cancelled=None,
                        initial_prompt=""):
        seen["cancelled"] = cancelled
        return ()

    monkeypatch.setattr(pipeline, "prepare_track",
                        lambda ctx, track: tmp_path / "vocals.wav")
    monkeypatch.setattr(pipeline, "_demucs_enabled", lambda ctx: False)
    monkeypatch.setattr(whisper_module, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline.word_alignment, "is_available",
                        lambda: False)

    stop = threading.Event()
    assert pipeline.fill_transcription_cache(
        context, cancelled=stop.is_set) is True
    assert callable(seen["cancelled"])
    assert seen["cancelled"]() is False
    stop.set()
    assert seen["cancelled"]() is True


def test_the_button_passes_the_function_and_not_the_event() -> None:
    """Exactly the error the user reported, pinned down.

    Filling the cache moved to 1.5.1 in the test panel; the demand has
    stayed the same - what is passed on has to be callable.
    """
    import inspect

    from modules import gui, test_panel

    source = inspect.getsource(test_panel.fill_cache)
    assert "cancelled=cancelled" in source
    panel = inspect.getsource(gui.MainWindow._do_fill_cache)
    assert "cancel.is_set" in panel


def test_two_run_at_once_and_one_failure_does_not_stop_the_rest() -> None:
    """Since B357 the shared dispatcher does that for every action."""
    import inspect

    from modules import test_panel

    dispatcher = inspect.getsource(test_panel.across_projects)
    # B396: the number of work places became an argument (two for pure
    # Python, more for Whisper work that lets go of the GIL).
    assert "range(max(1, int(slots)))" in dispatcher
    assert "never stops the rest" in dispatcher
    assert "across_projects" in inspect.getsource(test_panel.fill_cache)


def test_projects_with_manual_timing_come_first(tmp_path) -> None:
    """Stop halfway and the useful projects are the ones that are done."""
    _project(tmp_path, "Aaa_zonder_timing", step=True, cache=False)
    _project(tmp_path, "Zzz_met_timing", step=True, cache=False)
    paths = ProjectPaths(root=tmp_path, song="Zzz_met_timing")
    paths.timing_file.write_text("{}", encoding="utf-8")
    context = _context(tmp_path, "Aaa_zonder_timing")
    assert pipeline.projects_without_cache(context)[0] == "Zzz_met_timing"
