"""Tests for v0.136.0: B422 to B431.

The theme is a correction of my own work. Sharing one Whisper model
(B419) removed the per-piece loading and put a queue in its place: the
same night job went from 3902 s to 5522 s, and the user saw four busy
cores where two runs should have been. A shared model needs to be told
that several threads will call it.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from modules import measure_pool, pipeline


# --------------------------------------------------------------------------
# B422 - the shared model has to be allowed to serve several callers
# --------------------------------------------------------------------------

def test_the_model_is_told_how_many_runs_will_call_it() -> None:
    from modules import whisper

    source = inspect.getsource(whisper._load_model)
    assert "num_workers=workers" in source
    assert "cpu_threads=threads" in source


def test_the_lanes_and_the_threads_come_from_one_sum() -> None:
    """The library quietly defaults to four threads and this module
    assumed four; those agreeing was luck, not design."""
    assert measure_pool.whisper_lanes() >= 1
    assert measure_pool.threads_per_lane() >= 1
    assert measure_pool.threads_per_lane() <= measure_pool.WHISPER_THREADS


def test_the_slots_and_the_workers_are_the_same_number() -> None:
    many = measure_pool.whisper_workers(99)
    assert many == measure_pool.whisper_lanes()


def test_the_cache_key_knows_the_lanes() -> None:
    """A model built for one caller may not be handed to two."""
    from modules import whisper

    source = inspect.getsource(whisper._load_model)
    assert "workers, threads)" in source


# --------------------------------------------------------------------------
# B423 - the pieces go through the queue
# --------------------------------------------------------------------------

def _probe():
    import importlib.util

    import modules

    path = Path(modules.__file__).resolve().parents[1] / "tools" \
        / "whisper_probe.py"
    spec = importlib.util.spec_from_file_location("probe_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_pieces_are_spread_over_the_slots() -> None:
    source = inspect.getsource(_probe().run_chunked)
    assert "whisper_lanes" in source
    assert "threading.Thread" in source


def test_every_piece_is_transcribed_exactly_once(monkeypatch) -> None:
    from modules import whisper_chunks as wc

    probe = _probe()
    seen = []

    def fake(stem, settings, prompt, language, start=0.0, end=None):
        seen.append((start, end))
        return [{"start": start, "end": end or start + 1.0, "text": "x",
                 "words": []}]

    monkeypatch.setattr(probe, "run_once", fake)
    pieces = [wc.Chunk(float(i), float(i) + 1.0) for i in range(7)]
    out = probe.run_chunked(None, None, "nl", pieces, lambda p: "", lanes=3)
    assert len(out) == 7
    assert sorted(seen) == [(float(i), float(i) + 1.0) for i in range(7)]


def test_the_result_stays_in_time_order(monkeypatch) -> None:
    """Threads finish out of order; the paste-together may not."""
    from modules import whisper_chunks as wc

    probe = _probe()
    monkeypatch.setattr(probe, "run_once",
                        lambda stem, s, p, lang, start=0.0, end=None: [
                            {"start": start, "end": start + 1.0,
                             "text": "x", "words": []}])
    pieces = [wc.Chunk(float(i), float(i) + 1.0) for i in range(9)]
    out = probe.run_chunked(None, None, "nl", pieces, lambda p: "", lanes=4)
    assert [s["start"] for s in out] == sorted(s["start"] for s in out)


def test_one_slot_still_walks_them_one_by_one(monkeypatch) -> None:
    from modules import whisper_chunks as wc

    probe = _probe()
    monkeypatch.setattr(probe, "run_once",
                        lambda stem, s, p, lang, start=0.0, end=None: [
                            {"start": start, "end": start + 1.0,
                             "text": "x", "words": []}])
    pieces = [wc.Chunk(0.0, 1.0), wc.Chunk(1.0, 2.0)]
    assert len(probe.run_chunked(None, None, "nl", pieces,
                                 lambda p: "", lanes=1)) == 2


# --------------------------------------------------------------------------
# B424/B425 - the two open questions get a variant
# --------------------------------------------------------------------------

def test_the_prompt_is_isolated_by_a_variant() -> None:
    from modules import test_panel

    from modules.translations import TRANSLATIONS

    source = inspect.getsource(test_panel._chunk_one_song)
    assert "chunked_global" in test_panel._CHUNK_PLAN
    assert 'name == "chunked_global"' in source
    assert (TRANSLATIONS["nl"]["rep_chunk_run_chunked_global"]
            == "knippen (globale prompt)")


def test_cutting_with_vad_is_measured() -> None:
    from modules import test_panel

    from modules.translations import TRANSLATIONS

    source = inspect.getsource(test_panel._chunk_one_song)
    assert "chunked_vad" in test_panel._CHUNK_PLAN
    assert 'name == "chunked_vad"' in source
    assert 'VARIANTS["vad"]' in source
    assert TRANSLATIONS["nl"]["rep_chunk_run_chunked_vad"] == "knippen + vad"


# --------------------------------------------------------------------------
# B427 - the guard uses both texts
# --------------------------------------------------------------------------

def test_the_vocabulary_comes_from_both_texts(tmp_path) -> None:
    """The original sings "na-na-na" and Whisper writes "la"; the karaoke
    text writes that same passage as "la-la-la". Judging on the original
    alone rejected a correct run."""
    from modules import cluster, song_text, karaoke_text, test_panel
    from modules.config import AppConfig
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    (paths.input_dir / song_text.LYRICS_FILENAME).write_text(
        "Na-na-na-na-na\n", encoding="utf-8")
    (paths.input_dir / karaoke_text.FILENAME).write_text(
        "La-la-la-la-la\n", encoding="utf-8")
    context = pipeline.AppContext(paths=paths, config=AppConfig(),
                                  store=ProjectStore(paths.project_file))
    keys = test_panel._lyric_keys(context)
    assert cluster.phonetic_key("na") in keys
    assert cluster.phonetic_key("la") in keys


def test_without_a_karaoke_text_it_still_works(tmp_path) -> None:
    from modules import cluster, song_text, test_panel
    from modules.config import AppConfig
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    (paths.input_dir / song_text.LYRICS_FILENAME).write_text(
        "zing maar mee\n", encoding="utf-8")
    context = pipeline.AppContext(paths=paths, config=AppConfig(),
                                  store=ProjectStore(paths.project_file))
    keys = test_panel._lyric_keys(context)
    assert cluster.phonetic_key("zing") in keys
    assert "" not in keys


# --------------------------------------------------------------------------
# B428 - step 4 without a cluster selection
# --------------------------------------------------------------------------

def test_restoring_needs_no_cluster_selection() -> None:
    source = inspect.getsource(pipeline.run_karaoke)
    assert "or restore_fragments(context)" in source


def test_without_selection_and_without_restores_it_still_complains() -> None:
    source = inspect.getsource(pipeline.run_karaoke)
    assert 'err_no_cluster_selection' in source


def test_the_button_does_not_demand_an_analysis_for_a_restore() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._do_karaoke)
    assert "restore_fragments(context)" in source
    assert "prereq_need_analyse" in source


# --------------------------------------------------------------------------
# B429 - a changed model no longer silently wipes the handwork
# --------------------------------------------------------------------------

def _project(tmp_path, texts):
    from modules import karaoke_text, timing
    from modules.config import AppConfig
    from modules.filesystem import ProjectPaths, ProjectStore, \
        ensure_directories

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    (paths.input_dir / karaoke_text.FILENAME).write_text(
        "\n".join(texts) + "\n", encoding="utf-8")
    context = pipeline.AppContext(paths=paths, config=AppConfig(),
                                  store=ProjectStore(paths.project_file))
    pipeline.remember_sources(context)
    lines = [timing.timedline_from_text(i, text, 10.0 + i * 4, 13.0 + i * 4)
             for i, text in enumerate(texts)]
    timing.save_timing(lines, paths.timing_file, offset=0.0,
                       project="Proef", version="0.136.0")
    context.store.set_step("timing", {"lines": len(lines)})
    return context


def test_a_model_change_keeps_the_timing(tmp_path) -> None:
    """The afternoon that was lost: a model set differently, and
    timing.json gone without a question or a line in the log."""
    from modules import timing

    context = _project(tmp_path, ["eerste regel", "tweede regel"])
    groups = dict(pipeline._config_signature(context.config))
    groups["config:models"] = "iets anders"
    context.store.set_step("config_signature", {"groups": groups})

    changed = pipeline.sync_input_changes(context)
    assert "config:models" in changed
    assert context.paths.timing_file.exists()
    kept = list(timing.load_timing(context.paths.timing_file))
    assert [line.text for line in kept] == ["eerste regel", "tweede regel"]


def test_what_derives_from_the_change_does_go(tmp_path) -> None:
    """Rescuing the handwork is not pretending nothing happened."""
    context = _project(tmp_path, ["eerste regel", "tweede regel"])
    groups = dict(pipeline._config_signature(context.config))
    groups["config:models"] = "iets anders"
    context.store.set_step("config_signature", {"groups": groups})
    context.store.set_step("coupling", {"mapping": {}})

    pipeline.sync_input_changes(context)
    assert context.store.get_step("coupling") is None


def test_a_change_that_leaves_the_timing_alone_needs_no_rescue() -> None:
    assert pipeline._timing_would_go(["config:models"]) is True
    assert pipeline._timing_would_go(["input:logo"]) is False


def test_an_unknown_name_does_not_fall_over() -> None:
    assert pipeline._timing_would_go(["iets:onbekends"]) is False


# --------------------------------------------------------------------------
# B430/B431 - the panel tidies up after itself
# --------------------------------------------------------------------------

def test_the_chips_are_cleared_when_the_action_is_done() -> None:
    from modules import gui

    source = inspect.getsource(gui.MainWindow._reset_track_progress)
    assert "_clear_slot_chips()" in source
    # B435: and the same tidying up BETWEEN the rounds as well.
    assert "_clear_slot_chips" in inspect.getsource(gui.MainWindow._do_fill_cache)


def test_the_grey_note_under_the_video_button_is_gone() -> None:
    from modules import gui
    from modules.translations import TRANSLATIONS

    assert "video_render_note" not in inspect.getsource(gui)
    for language in ("nl", "en"):
        assert "video_render_note" not in TRANSLATIONS[language]
