"""Tests for modules.pipeline (the shared layer under console and GUI)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from modules import pipeline
from modules.align import OffsetRegion, regions_to_dicts
from modules.audio import save_wav
from modules.config import default_config
from modules.filesystem import ProjectPaths, ProjectStore, ensure_directories
from modules.pipeline import AppContext, PipelineError
from modules.whisper import Segment, Word, save_segments


def _context(tmp_path: Path) -> AppContext:
    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    return AppContext(config=default_config(), paths=paths,
                      store=ProjectStore(paths.project_file))


def _write_tone(path: Path, seconds: float = 2.0,
                sample_rate: int = 22_050) -> None:
    time = np.arange(int(seconds * sample_rate)) / sample_rate
    tone = (0.4 * np.sin(2 * np.pi * 440 * time)).astype(np.float32)
    save_wav(path, np.stack([tone, tone], axis=1), sample_rate)


def _fake_segments() -> tuple[Segment, ...]:
    words = (Word("oeh", 0.5, 0.9, 0.9), Word("oe", 1.2, 1.5, 0.85))
    return (Segment(0, "oeh oe", 0.5, 1.5, words),)


def test_alignment_offset_zero_for_generated_karaoke(tmp_path: Path) -> None:
    """B81: karaoke from the original -> alignment skipped, offset 0."""
    context = _context(tmp_path)
    context.store.set_meta("karaoke_from_original", True)
    regions = pipeline.run_alignment(context)
    assert len(regions) == 1
    assert regions[0].offset == 0.0
    assert regions[0].confidence == 1.0


def test_audio_rms_silence_vs_tone(tmp_path: Path) -> None:
    """B83: silence falls below the threshold, a tone above it."""
    silent = tmp_path / "silent.wav"
    save_wav(silent, np.zeros((22_050, 1), dtype=np.float32), 22_050)
    assert pipeline._audio_rms(silent) < pipeline.KARAOKE_VOCAL_SILENCE_RMS
    tone = tmp_path / "tone.wav"
    _write_tone(tone)
    assert pipeline._audio_rms(tone) > pipeline.KARAOKE_VOCAL_SILENCE_RMS


def test_delete_project_removes_dirs(tmp_path: Path) -> None:
    """B84: deleting a project wipes the input, output and cache dirs."""
    from dataclasses import replace
    paths = ProjectPaths(root=tmp_path, song="Lied")
    ensure_directories(paths)
    (paths.input_dir / "original.wav").write_bytes(b"x")
    (paths.output_dir / "something.txt").write_text("y", encoding="utf-8")
    cfg = default_config()
    cfg = replace(cfg, song=replace(cfg.song, title="Lied"))
    ctx = AppContext(config=cfg, paths=paths,
                     store=ProjectStore(paths.project_file))
    pipeline.delete_project(ctx)
    assert not paths.input_dir.exists()
    assert not paths.output_dir.exists()
    assert not paths.cache_dir.exists()


def test_delete_project_requires_loaded(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="Geen project"):
        pipeline.delete_project(_context(tmp_path))


def test_export_demucs_karaoke_to_output(tmp_path: Path,
                                         monkeypatch) -> None:
    """B94: the Demucs instrumental lands in output as karaoke_demucs.mp3."""
    from types import SimpleNamespace

    from modules import ffmpeg
    context = _context(tmp_path)
    instrumental = context.paths.cache_dir / "instrumental.wav"
    _write_tone(instrumental)

    captured: dict = {}
    monkeypatch.setattr(ffmpeg, "probe", lambda p: SimpleNamespace(
        sample_rate=44_100, channels=2))

    def fake_encode(src, target, **kwargs):
        captured["target"] = target
        target.write_bytes(b"ID3")
        return target

    monkeypatch.setattr(ffmpeg, "encode_mp3", fake_encode)
    result = pipeline.export_demucs_karaoke(context, instrumental)
    assert result == context.paths.output_dir / "karaoke_demucs.mp3"
    assert result.exists()
    assert captured["target"].name == "karaoke_demucs.mp3"


def test_check_project_paths_consistent(tmp_path: Path) -> None:
    """B95b: for a freshly loaded project all paths/project.json agree."""
    from dataclasses import replace
    paths = ProjectPaths(root=tmp_path, song="Lied")
    ensure_directories(paths)
    cfg = replace(default_config(),
                  song=replace(default_config().song, title="Lied"))
    ctx = AppContext(config=cfg, paths=paths,
                     store=ProjectStore(paths.project_file))
    ok, _ = pipeline.check_project_paths(ctx)
    assert ok is True


def test_check_project_paths_mismatch(tmp_path: Path) -> None:
    """B95b: a title that does not match the paths is reported."""
    from dataclasses import replace
    paths = ProjectPaths(root=tmp_path, song="Lied")
    ensure_directories(paths)
    # Config says 'Ander', but the paths/store belong to 'Lied'.
    cfg = replace(default_config(),
                  song=replace(default_config().song, title="Ander"))
    ctx = AppContext(config=cfg, paths=paths,
                     store=ProjectStore(paths.project_file))
    ok, message = pipeline.check_project_paths(ctx)
    assert ok is False
    assert "wijken af" in message


def test_filter_hallucinations() -> None:
    """B141: 'MUZIEK' segments are filtered out of the coupling."""
    from modules.whisper import Segment, Word
    segs = (
        Segment(0, "MUZIEK", 28.6, 29.0, (Word("MUZIEK", 28.6, 29.0, 0.5),)),
        Segment(1, "Bertus op zien Norton", 120.1, 123.4,
                (Word("Bertus", 120.1, 120.6, 0.9),
                 Word("op", 120.6, 120.8, 0.9))),
    )
    kept = pipeline._filter_hallucinations(segs)
    assert len(kept) == 1
    assert kept[0].text == "Bertus op zien Norton"


def test_apply_pins_couples_and_uncouples() -> None:
    """B121: manual pins override the automatic coupling."""
    from modules.song_text import AlignedWord, LyricWord, apply_pins
    aligned = (
        AlignedWord(LyricWord(0, "oerend", 0), None, None, None, 0.0),
        AlignedWord(LyricWord(1, "thee", 0), 5.0, 5.4, "PROFITE", 0.3),
    )
    transcript = [("OEHOOR", 3.0, 3.5), ("EN", 3.6, 3.9), ("THEE", 5.0, 5.4)]
    # One-to-many: 'oerend' to two found words; 'thee' uncoupled.
    out = apply_pins(aligned, transcript, {0: [0, 1], 1: []})
    assert out[0].start == 3.0 and out[0].end == 3.9      # covers both
    assert out[0].matched_text == "OEHOOR EN" and out[0].sim == 1.0
    assert out[1].start is None and out[1].sim == 0.0


def test_cut_word_splits_and_remaps_pins() -> None:
    """B153: cut a found word and remap its couplings."""
    from modules.song_text import cut_word, remap_pins
    transcript = [("OEREND", 0.0, 2.0), ("HARD", 2.0, 3.0)]
    new, mapping = cut_word(transcript, 0)      # middle of 'OEREND'
    assert [w[0] for w in new] == ["OER", "END", "HARD"]
    assert new[0][1] == 0.0 and new[1][2] == 2.0
    assert mapping == {0: [0, 1], 1: [2]}
    # A pin on the cut word now points at both halves.
    assert remap_pins({5: [0], 6: [1]}, mapping) == {5: [0, 1], 6: [2]}


def test_merge_words_joins_them() -> None:
    """B153: merge two adjacent found words."""
    from modules.song_text import merge_words, remap_pins
    transcript = [("TIEN", 0.0, 1.0), ("IS", 1.0, 2.0), ("TINUS", 2.0, 3.0)]
    new, mapping = merge_words(transcript, 0)
    assert [w[0] for w in new] == ["TIEN IS", "TINUS"]
    assert new[0] == ("TIEN IS", 0.0, 2.0)
    assert mapping == {0: [0], 1: [0], 2: [1]}
    assert remap_pins({3: [0, 1], 4: [2]}, mapping) == {3: [0], 4: [1]}


def test_transcript_override_roundtrip(tmp_path: Path) -> None:
    """B153: an edited transcript is stored, read back and cleared."""
    context = _context(tmp_path)
    assert pipeline.transcript_override(context) is None
    pipeline.set_transcript_override(context, [("OER", 0.0, 1.0),
                                               ("END", 1.0, 2.0)])
    assert pipeline.transcript_override(context) == [("OER", 0.0, 1.0),
                                                     ("END", 1.0, 2.0)]
    pipeline.set_transcript_override(context, None)
    assert pipeline.transcript_override(context) is None


def test_trim_tail_matches_tail() -> None:
    """B159: weak matches in the tail are uncoupled, the core stays."""
    from modules.song_text import AlignedWord, LyricWord, trim_tail_matches
    aligned = (
        AlignedWord(LyricWord(0, "zangers", 0), 1.0, 2.0, "ZANGERS", 0.9),
        AlignedWord(LyricWord(1, "hard", 0), 2.0, 3.0, "HARD", 0.8),
        AlignedWord(LyricWord(2, "oehoe", 1), 50.0, 51.0, "XZ", 0.2),
        AlignedWord(LyricWord(3, "oehoe", 1), 51.0, 52.0, "QP", 0.1),
    )
    out = trim_tail_matches(aligned, min_sim=0.45)
    assert out[0].start == 1.0 and out[1].start == 2.0     # core stays
    assert out[2].start is None and out[3].start is None    # tail loose


def test_timing_project_mismatch(tmp_path: Path) -> None:
    """B181/B183: mismatch between the stored and the current project."""
    from modules import timing as timing_module
    from modules.timing import Syllable, TimedLine
    context = _context(tmp_path)  # song.title = "" by default
    from dataclasses import replace
    context = replace(context, config=replace(
        context.config, song=replace(context.config.song, title="Lied_N")))
    line = TimedLine(0, "hoi", False, (Syllable("hoi", 0.0, 1.0),))
    # Save timing that belongs to another project:
    timing_module.save_timing((line,), context.paths.timing_file,
                              project="Lied_O")
    assert pipeline.timing_project_mismatch(context) == "Lied_O"
    # Same project -> no mismatch.
    timing_module.save_timing((line,), context.paths.timing_file,
                              project="Lied_N")
    assert pipeline.timing_project_mismatch(context) is None


def test_lyrics_override_roundtrip(tmp_path: Path) -> None:
    """B156: store, read back and clear edited lyric words."""
    context = _context(tmp_path)
    assert pipeline.lyrics_override(context) is None
    pipeline.set_lyrics_override(context, [("oeho", 0), ("erend", 0)])
    assert pipeline.lyrics_override(context) == [("oeho", 0), ("erend", 0)]
    pipeline.set_lyrics_override(context, None)
    assert pipeline.lyrics_override(context) is None


def test_word_pins_roundtrip(tmp_path: Path) -> None:
    """B121: word couplings (lists) are stored and read back."""
    context = _context(tmp_path)
    assert pipeline.word_pins(context) == {}
    pipeline.set_word_pins(context, {0: [3, 4], 2: []})
    assert pipeline.word_pins(context) == {0: [3, 4], 2: []}
    # Invalidation clears the couplings (transcript indices go stale).
    pipeline.invalidate(context, ["input:lyrics"])
    assert pipeline.word_pins(context) == {}


def test_onset_from_signal_after_silence() -> None:
    """B133: onset falls after a silent intro (core function, no ffmpeg)."""
    import numpy as np
    sr = 22_050
    silence = np.zeros(int(3.0 * sr), dtype=np.float32)
    tone = (0.4 * np.sin(2 * np.pi * 300 *
                         np.arange(int(2.0 * sr)) / sr)).astype(np.float32)
    onset = pipeline._onset_from_signal(np.concatenate([silence, tone]), sr)
    assert onset is not None and 2.7 <= onset <= 3.3


def test_ensure_vocal_onset_uses_stored(tmp_path: Path) -> None:
    """B133: an onset already determined is reused (no recomputation)."""
    context = _context(tmp_path)
    context.store.set_meta("vocal_onset_s", 4.2)
    assert pipeline.ensure_vocal_onset(context) == 4.2


def test_has_transcription_and_analysis(tmp_path: Path) -> None:
    """B134: prerequisite checks recognise completed steps."""
    context = _context(tmp_path)
    assert pipeline.has_transcription(context) is False
    assert pipeline.has_analysis(context) is False
    context.store.set_step("whisper_original", {"segments": 3})
    assert pipeline.has_transcription(context) is True
    context.store.set_step("clusters_original", {"selection": []})
    assert pipeline.has_analysis(context) is True


def test_first_vocal_onset(tmp_path: Path) -> None:
    """B130: the onset falls after a silent intro, at the tone's start."""
    import numpy as np
    from modules.audio import save_wav
    sr = 22_050
    silence = np.zeros(int(3.0 * sr), dtype=np.float32)
    tone = (0.4 * np.sin(2 * np.pi * 300 *
                         np.arange(int(2.0 * sr)) / sr)).astype(np.float32)
    data = np.concatenate([silence, tone])
    path = tmp_path / "vocals.wav"
    save_wav(path, np.stack([data, data], axis=1), sr)
    onset = pipeline._first_vocal_onset(path)
    assert onset is not None
    assert 2.7 <= onset <= 3.3      # around 3 s (after the silence)


def test_check_text_alignment_inline_crowd(tmp_path: Path) -> None:
    """B104/B179a: inline crowd (stays inside the sentence) gives no
    false structure mismatch when both texts have the same line
    layout."""
    context = _context(tmp_path)
    (context.paths.input_dir / "songtekst.txt").write_text(
        "K zeg oeh!\nIk zeg ah!\n", encoding="utf-8")
    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "K zeg oeh! [crowd]Oeh![/crowd]\nIk zeg ah! [crowd]Ah![/crowd]\n",
        encoding="utf-8")
    ok, _ = pipeline.check_text_alignment(context)
    assert ok is True


def test_texts_identical(tmp_path: Path) -> None:
    """B115: identical lyrics and karaoke text are recognised."""
    context = _context(tmp_path)
    (context.paths.input_dir / "songtekst.txt").write_text(
        "Rood Witte Zangers", encoding="utf-8")
    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "rood  witte\nzangers", encoding="utf-8")
    assert pipeline.texts_identical(context) is True
    (context.paths.input_dir / "songtekst.txt").write_text(
        "Iets heel anders hier", encoding="utf-8")
    assert pipeline.texts_identical(context) is False


def test_invalidate_derived(tmp_path: Path) -> None:
    """B113/B311: invalidation clears steps and timing files.

    Since B311 this runs through the derivation chain: new karaoke
    audio, so everything that follows from it."""
    context = _context(tmp_path)
    context.store.set_step("whisper_karaoke", {"x": 1})
    context.store.set_step("align", {"regions": []})
    context.paths.timing_file.parent.mkdir(parents=True, exist_ok=True)
    context.paths.timing_file.write_text("[]", encoding="utf-8")
    pipeline.invalidate(context, ["input:karaoke"])
    assert context.store.get_step("whisper_karaoke") is None
    assert context.store.get_step("align") is None
    assert not context.paths.timing_file.exists()


def test_detect_track_demucs_skip(tmp_path: Path, monkeypatch) -> None:
    """B118: Demucs karaoke skips transcribing the residual vocals."""
    context = _context(tmp_path)
    context.store.set_meta("karaoke_from_original", True)
    monkeypatch.setattr(pipeline, "prepare_track",
                        lambda ctx, track: ctx.paths.input_dir / "k.wav")
    monkeypatch.setattr(pipeline.filesystem, "file_sha1", lambda p: "sha")
    called = {"whisper": False}
    monkeypatch.setattr(pipeline.whisper, "transcribe",
                        lambda *a, **k: called.__setitem__("whisper", True))
    result = pipeline.detect_track(context, pipeline.TRACK_KARAOKE)
    assert result.segments == ()
    assert called["whisper"] is False
    assert context.store.get_step("whisper_karaoke")["empty"] is True


def test_diagnostics_toggle_off(tmp_path: Path) -> None:
    """B143: with diagnostics off nothing is written."""
    from dataclasses import replace
    context = _context(tmp_path)
    context = replace(context, config=replace(
        context.config, advanced=replace(
            context.config.advanced, diagnostics=False)))
    res = pipeline.write_transcription_history(
        context, pipeline.TRACK_KARAOKE,
        pipeline.DetectResult(pipeline.TRACK_KARAOKE, _fake_segments(), False))
    assert res is None
    assert not pipeline.diagnostics_dir(context).exists()


def test_diagnostics_in_subdir_and_version(tmp_path: Path) -> None:
    """B143: diagnostics in a subdir; the version is logged on change."""
    import json
    context = _context(tmp_path)
    dr = pipeline.DetectResult(pipeline.TRACK_KARAOKE, _fake_segments(), False)
    path = pipeline.write_transcription_history(
        context, pipeline.TRACK_KARAOKE, dr)
    assert path.parent.name == "diagnostics"
    pipeline.write_transcription_history(context, pipeline.TRACK_KARAOKE, dr)
    runs = json.loads(path.read_text(encoding="utf-8"))["runs"]
    # The first run carries the version, the second (same one) not.
    assert "version" in runs[0]
    assert "version" not in runs[1]


def test_write_transcription_history_appends(tmp_path: Path) -> None:
    """B131: every run is appended to the output with a timestamp."""
    import json
    context = _context(tmp_path)
    seg = _fake_segments()
    pipeline.write_transcription_history(
        context, pipeline.TRACK_KARAOKE,
        pipeline.DetectResult(pipeline.TRACK_KARAOKE, seg, False))
    pipeline.write_transcription_history(
        context, pipeline.TRACK_KARAOKE,
        pipeline.DetectResult(pipeline.TRACK_KARAOKE, seg, True))
    path = pipeline.transcription_history_path(context, pipeline.TRACK_KARAOKE)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 2
    assert all("time" in run for run in data["runs"])
    assert data["runs"][0]["from_cache"] is False
    assert "segments" in data["runs"][0]        # a real run keeps segments
    assert data["runs"][1]["from_cache"] is True


def _prep_parallel(context, monkeypatch):
    """Replace heavy steps so detect_tracks runs without Whisper/ffmpeg."""
    monkeypatch.setattr(pipeline, "prepare_track",
                        lambda ctx, track: context.paths.input_dir /
                        f"{track}.wav")
    monkeypatch.setattr(pipeline, "enabled_tracks",
                        lambda ctx: (pipeline.TRACK_ORIGINAL,
                                     pipeline.TRACK_KARAOKE))


def test_detect_tracks_parallel_both_tracks(tmp_path: Path,
                                            monkeypatch) -> None:
    """B90: parallel yields both tracks and per-track progress."""
    context = _context(tmp_path)
    _prep_parallel(context, monkeypatch)

    def fake_detect(ctx, track, progress=None, cancelled=None):
        if progress is not None:
            progress(1.0, 2.0)  # per-track progress
        return pipeline.DetectResult(track, _fake_segments(), False)

    monkeypatch.setattr(pipeline, "detect_track", fake_detect)
    seen: list[tuple[str, float, float]] = []
    results = pipeline.detect_tracks(
        context, progress=lambda tr, d, t: seen.append((tr, d, t)),
        parallel=True)
    assert set(results) == {pipeline.TRACK_ORIGINAL, pipeline.TRACK_KARAOKE}
    assert {tr for tr, _, _ in seen} == {pipeline.TRACK_ORIGINAL,
                                         pipeline.TRACK_KARAOKE}


def test_detect_tracks_sequential(tmp_path: Path, monkeypatch) -> None:
    """B90: with parallel=False it runs one by one (same result)."""
    context = _context(tmp_path)
    _prep_parallel(context, monkeypatch)
    monkeypatch.setattr(
        pipeline, "detect_track",
        lambda ctx, track, progress=None, cancelled=None:
        pipeline.DetectResult(track, (), False))
    results = pipeline.detect_tracks(context, parallel=False)
    assert set(results) == {pipeline.TRACK_ORIGINAL, pipeline.TRACK_KARAOKE}


def test_detect_tracks_oom_fallback(tmp_path: Path, monkeypatch) -> None:
    """B90: out of memory in the parallel run falls back to sequential."""
    context = _context(tmp_path)
    _prep_parallel(context, monkeypatch)
    calls = {"n": 0}

    def flaky_detect(ctx, track, progress=None, cancelled=None):
        calls["n"] += 1
        # First (parallel) attempt: out of memory on one track.
        if calls["n"] <= 2 and track == pipeline.TRACK_KARAOKE:
            raise MemoryError("out of memory")
        return pipeline.DetectResult(track, (), False)

    monkeypatch.setattr(pipeline, "detect_track", flaky_detect)
    results = pipeline.detect_tracks(context, parallel=True)
    assert set(results) == {pipeline.TRACK_ORIGINAL, pipeline.TRACK_KARAOKE}


def test_detect_tracks_track_done(tmp_path: Path, monkeypatch) -> None:
    """B96: track_done is called exactly once per track."""
    context = _context(tmp_path)
    _prep_parallel(context, monkeypatch)
    monkeypatch.setattr(
        pipeline, "detect_track",
        lambda ctx, track, progress=None, cancelled=None:
        pipeline.DetectResult(track, (), False))
    done: list[str] = []
    pipeline.detect_tracks(context, track_done=done.append, parallel=True)
    assert sorted(done) == [pipeline.TRACK_KARAOKE, pipeline.TRACK_ORIGINAL]


def test_sync_timing_same_structure(tmp_path: Path) -> None:
    """B99: with the same structure only the changed line is updated."""
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton, load_timing, save_timing
    context = _context(tmp_path)
    old_lines = (TextLine(0, "regel een", False, 0),
                 TextLine(1, "regel twee", False, 0))
    timed = generate_skeleton(old_lines, {0: (1.0, 2.0), 1: (3.0, 4.0)})
    save_timing(timed, context.paths.timing_file, offset=-0.1)
    new_lines = (TextLine(0, "regel een", False, 0),
                 TextLine(1, "regel twee anders", False, 0))
    updated, _ = pipeline.sync_timing_with_text_change(
        context, old_lines, new_lines)
    assert updated is True
    result = load_timing(context.paths.timing_file)
    assert result[0].syllables == timed[0].syllables  # unchanged
    assert result[1].text == "regel twee anders"      # updated
    # The line span stays the same (spread over new syllables).
    assert result[1].syllables[0].start == timed[1].syllables[0].start


def test_sync_timing_different_structure(tmp_path: Path) -> None:
    """B99/B113: with a different structure the timing is removed."""
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton, save_timing
    context = _context(tmp_path)
    old_lines = (TextLine(0, "een", False, 0),
                 TextLine(1, "twee", False, 0))
    timed = generate_skeleton(old_lines, {0: (1.0, 2.0), 1: (3.0, 4.0)})
    save_timing(timed, context.paths.timing_file)
    # New text with an extra block -> the structure differs.
    new_lines = (TextLine(0, "een", False, 0),
                 TextLine(1, "twee", False, 1))
    updated, message = pipeline.sync_timing_with_text_change(
        context, old_lines, new_lines)
    assert updated is False
    # The timing no longer fits and is removed (must be remade).
    assert not context.paths.timing_file.exists()


def test_detect_tracks_cancel(tmp_path: Path, monkeypatch) -> None:
    """B90: one shared cancellation aborts the parallel detection."""
    from modules import whisper
    context = _context(tmp_path)
    _prep_parallel(context, monkeypatch)

    def cancelling(ctx, track, progress=None, cancelled=None):
        raise whisper.CancelledError()

    monkeypatch.setattr(pipeline, "detect_track", cancelling)
    with pytest.raises(whisper.CancelledError):
        pipeline.detect_tracks(context, cancelled=lambda: True, parallel=True)


def test_cleanup_after_cancel_clears_steps(tmp_path: Path) -> None:
    """B86: cleaning up after a cancel wipes cache and resets steps."""
    context = _context(tmp_path)
    context.store.set_step("whisper_original", {"x": 1})
    context.store.set_step("align", {"regions": []})
    (context.paths.cache_dir / "rest.txt").write_text("x", encoding="utf-8")
    pipeline.cleanup_after_cancel(context)
    assert context.store.get_step("whisper_original") is None
    assert context.store.get_step("align") is None
    assert not (context.paths.cache_dir / "rest.txt").exists()


def test_prepare_track_missing_input(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(PipelineError, match="original"):
        pipeline.prepare_track(context, "original")


def test_detect_words_uses_cache(tmp_path: Path) -> None:
    """With a valid cache Whisper is not called.

    Runs since B293 through ``detect_tracks(parallel=False)``; the
    separate ``detect_words`` did exactly the same and was removed.

    B545: without Demucs off this test only passes on a machine where
    Demucs is not installed. ``detect_track`` transcribes the separated
    vocal stem, so the key holds the checksum of that stem while this
    test writes the step with the checksum of its own input file - and
    then there is no cache hit at all. What is being tested here is the
    transcription cache, not the separation.
    """
    from dataclasses import replace

    from modules.filesystem import file_sha1

    context = _context(tmp_path)
    context = replace(context, config=replace(
        context.config, advanced=replace(context.config.advanced,
                                         demucs=False)))
    _write_tone(context.paths.input_dir / "original.wav")
    _write_tone(context.paths.input_dir / "karaoke.wav")

    segments = _fake_segments()
    for track in ("original", "karaoke"):
        save_segments(segments, pipeline.transcript_cache(context, track))
        checksum = file_sha1(context.paths.input_dir / f"{track}.wav")
        context.store.set_step(f"whisper_{track}", {
            "wav_sha1": checksum,
            "model": context.config.whisper.model,
            "language": context.config.whisper.language,
        })

    results = pipeline.detect_tracks(context, parallel=False)
    assert set(results) == {"original", "karaoke"}
    for result in results.values():
        assert result.from_cache is True
        assert result.segments == segments
        assert result.word_count == 2


def test_detect_words_uses_cache_along_the_demucs_path(
        tmp_path: Path, monkeypatch) -> None:
    """B545: the same question with the separation on.

    The test above switches Demucs off, which is honest for what it
    asks - but it would leave the branch that nobody here can walk
    without Demucs installed without a single test, and that is exactly
    the branch the machine this is built for walks every day.
    ``detect_track`` transcribes the vocal STEM, so the key has to hold
    the checksum of that stem. The separation is stubbed with a stem
    that is deliberately not its source: if the key were built from the
    mix, the second run would transcribe all over again.

    Chunking and forced alignment are off so that this test asks one
    thing and does not depend on whisperx being installed.
    """
    from dataclasses import replace

    from modules import separation
    from modules.filesystem import file_sha1

    context = _context(tmp_path)
    context = replace(context, config=replace(
        context.config, advanced=replace(
            context.config.advanced, chunked_transcription=False,
            forced_alignment=False)))
    assert context.config.advanced.demucs is True
    _write_tone(context.paths.input_dir / "original.wav")

    stem = {}

    def _fake_separate(audio_path, cache_root, key, model="htdemucs"):
        store = cache_root / f"demucs_stems_{key}"
        store.mkdir(parents=True, exist_ok=True)
        vocals, instrumental = store / "vocals.wav", store / "no_vocals.wav"
        if not vocals.exists():  # other audio than the source, on purpose
            _write_tone(vocals, seconds=1.5)
            _write_tone(instrumental, seconds=1.0)
        stem["vocals"] = vocals
        return {"vocals": vocals, "instrumental": instrumental}

    monkeypatch.setattr(separation, "is_available", lambda: True)
    monkeypatch.setattr(separation, "separate_cached", _fake_separate)
    transcribed = []

    def _fake_transcribe(wav_path, *args, **kwargs):
        transcribed.append(Path(wav_path))
        return _fake_segments()

    monkeypatch.setattr(pipeline.whisper, "transcribe", _fake_transcribe)

    first = pipeline.detect_track(context, pipeline.TRACK_ORIGINAL)
    second = pipeline.detect_track(context, pipeline.TRACK_ORIGINAL)

    assert first.from_cache is False
    assert second.from_cache is True
    assert transcribed == [stem["vocals"]]  # the stem, not the mix
    step = context.store.get_step("whisper_original")
    assert step["wav_sha1"] == file_sha1(stem["vocals"])
    assert step["wav_sha1"] != file_sha1(
        context.paths.input_dir / "original.wav")

    # And the other half of a key: OTHER audio in the stem has to give
    # a new transcription. Without this the suite says nothing about
    # whether the checksum is read at all - the whole condition could
    # be struck and everything would stay green.
    _write_tone(stem["vocals"], seconds=1.25)
    third = pipeline.detect_track(context, pipeline.TRACK_ORIGINAL)
    assert third.from_cache is False
    assert transcribed == [stem["vocals"], stem["vocals"]]
    assert context.store.get_step("whisper_original")["wav_sha1"] == \
        file_sha1(stem["vocals"])


def test_demucs_off_really_skips_the_separation(
        tmp_path: Path, monkeypatch) -> None:
    """B545: the switch, not the machine, decides.

    Two cache tests lean on ``demucs=False`` to keep them off the
    separation branch. That only means something if the option is
    really what turns the branch off, and here - where Demucs is not
    installed - nothing would notice if it were not. With separation
    available and the option off the mix has to be transcribed.
    """
    from dataclasses import replace

    from modules import separation

    context = _context(tmp_path)
    context = replace(context, config=replace(
        context.config, advanced=replace(
            context.config.advanced, demucs=False,
            chunked_transcription=False, forced_alignment=False)))
    mix = context.paths.input_dir / "original.wav"
    _write_tone(mix)

    def _refuse(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("separation ran while the option was off")

    monkeypatch.setattr(separation, "is_available", lambda: True)
    monkeypatch.setattr(separation, "separate_cached", _refuse)
    transcribed = []
    monkeypatch.setattr(pipeline.whisper, "transcribe",
                        lambda wav_path, *a, **k: (
                            transcribed.append(Path(wav_path)),
                            _fake_segments())[1])

    pipeline.detect_track(context, pipeline.TRACK_ORIGINAL)

    assert transcribed == [mix]


def test_load_segments_requires_step_one(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match=r"1\.1\. Detecteer woorden"):
        pipeline.load_segments(_context(tmp_path), "original")


def test_enabled_tracks_always_both(tmp_path: Path) -> None:
    """B174: analysis always runs on original + karaoke, config or not."""
    from dataclasses import replace

    context = _context(tmp_path)
    assert pipeline.enabled_tracks(context) == ("original", "karaoke")
    # Even if the (outdated) config has one track off: both stay.
    karaoke_only = replace(
        context, config=replace(context.config, tracks=replace(
            context.config.tracks, original=False)))
    assert pipeline.enabled_tracks(karaoke_only) == ("original", "karaoke")


def test_run_analysis_and_selection_roundtrip(tmp_path: Path) -> None:
    context = _context(tmp_path)
    save_segments(_fake_segments(),
                  pipeline.transcript_cache(context, "original"))
    context.store.set_step("whisper_original",
                           {"wav_sha1": "x", "model": "large-v3",
                            "language": "nl"})

    result = pipeline.run_analysis(context, "original")
    assert result.track == "original"
    assert result.clusters
    assert result.html_path.exists()
    assert result.html_path.parent.name == "original"  # own dir
    assert result.suggested  # 'oe' is in the default search words

    pipeline.save_cluster_selection(context, "original",
                                    list(result.suggested),
                                    result.json_path, len(result.clusters))
    assert pipeline.selection_exists(context, "original")
    assert not pipeline.selection_exists(context, "karaoke")
    selected = pipeline.selected_clusters(context, "original")
    assert {cluster.id for cluster in selected} == set(result.suggested)


def test_selected_clusters_requires_selection(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match=r"1\.3\. Analyse"):
        pipeline.selected_clusters(_context(tmp_path), "original")


def test_alignment_regions_requires_step_three(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="uitlijning"):
        pipeline.alignment_regions(_context(tmp_path))


def test_run_karaoke_and_export_wav(tmp_path: Path) -> None:
    """Steps 4 and 5 on top of a prepared project record."""
    from dataclasses import asdict

    from modules.ffmpeg import AudioProperties

    context = _context(tmp_path)
    karaoke_wav = context.paths.input_dir / "karaoke.wav"
    _write_tone(karaoke_wav, seconds=3.0)

    properties = AudioProperties(codec="pcm_s16le", sample_rate=22_050,
                                 channels=2, bit_rate=705_600, duration=3.0,
                                 container="wav", is_vbr=None)
    context.store.set_step("source_karaoke", {
        "path": str(karaoke_wav),
        "sha1": pipeline.filesystem.file_sha1(karaoke_wav),
        "wav": str(karaoke_wav),
        "properties": asdict(properties)})
    context.store.set_step("align", {
        "regions": regions_to_dicts((OffsetRegion(0.0, 3.0, 0.0, 0.9),))})

    save_segments(_fake_segments(),
                  pipeline.transcript_cache(context, "original"))
    context.store.set_step("whisper_original",
                           {"wav_sha1": "x", "model": "large-v3",
                            "language": "nl"})
    analyse_result = pipeline.run_analysis(context, "original")
    pipeline.save_cluster_selection(context, "original",
                                    [analyse_result.clusters[0].id],
                                    analyse_result.json_path,
                                    len(analyse_result.clusters))

    karaoke_result = pipeline.run_karaoke(context)
    assert karaoke_result.intervals
    assert karaoke_result.output_wav.exists()
    assert karaoke_result.total_damped_s > 0

    exported = pipeline.run_export(context)
    assert exported.name == "karaoke_edit.wav"
    assert exported.exists()


def test_run_export_requires_karaoke_step(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match=r"1\.4\. Karaoke aanpassen"):
        pipeline.run_export(_context(tmp_path))


def test_run_karaoke_with_karaoke_track_needs_no_alignment(
        tmp_path: Path) -> None:
    """Residual words from the karaoke track are damped without step 3."""
    from dataclasses import asdict

    from modules.ffmpeg import AudioProperties

    context = _context(tmp_path)
    karaoke_wav = context.paths.input_dir / "karaoke.wav"
    _write_tone(karaoke_wav, seconds=3.0)
    properties = AudioProperties(codec="pcm_s16le", sample_rate=22_050,
                                 channels=2, bit_rate=705_600, duration=3.0,
                                 container="wav", is_vbr=None)
    context.store.set_step("source_karaoke", {
        "path": str(karaoke_wav),
        "sha1": pipeline.filesystem.file_sha1(karaoke_wav),
        "wav": str(karaoke_wav),
        "properties": asdict(properties)})

    save_segments(_fake_segments(),
                  pipeline.transcript_cache(context, "karaoke"))
    context.store.set_step("whisper_karaoke",
                           {"wav_sha1": "x", "model": "large-v3",
                            "language": "nl"})
    result = pipeline.run_analysis(context, "karaoke")
    pipeline.save_cluster_selection(context, "karaoke",
                                    [result.clusters[0].id],
                                    result.json_path, len(result.clusters))

    # No 'align' step in the record - and step 4 works all the same.
    karaoke_result = pipeline.run_karaoke(context)
    assert karaoke_result.intervals
    # Times are NOT projected: the first fragment starts at 0.5 s.
    assert karaoke_result.intervals[0].start == pytest.approx(0.5, abs=0.01)


def test_fragment_exclusions_filter_damping(tmp_path: Path) -> None:
    """Unticked fragments are not damped but stay known."""
    from dataclasses import asdict

    from modules.ffmpeg import AudioProperties

    context = _context(tmp_path)
    karaoke_wav = context.paths.input_dir / "karaoke.wav"
    _write_tone(karaoke_wav, seconds=3.0)
    properties = AudioProperties(codec="pcm_s16le", sample_rate=22_050,
                                 channels=2, bit_rate=705_600, duration=3.0,
                                 container="wav", is_vbr=None)
    context.store.set_step("source_karaoke", {
        "path": str(karaoke_wav),
        "sha1": pipeline.filesystem.file_sha1(karaoke_wav),
        "wav": str(karaoke_wav),
        "properties": asdict(properties)})
    save_segments(_fake_segments(),
                  pipeline.transcript_cache(context, "karaoke"))
    context.store.set_step("whisper_karaoke",
                           {"wav_sha1": "x", "model": "large-v3",
                            "language": "nl"})
    result = pipeline.run_analysis(context, "karaoke")
    pipeline.save_cluster_selection(context, "karaoke",
                                    [result.clusters[0].id],
                                    result.json_path, len(result.clusters))

    first = pipeline.run_karaoke(context)
    assert len(first.intervals) == len(first.all_intervals) >= 1

    # Exclude the first fragment: it drops out of the active damping.
    target = first.all_intervals[0]
    pipeline.set_fragment_exclusions(context, [(target.start, target.end)])
    second = pipeline.run_karaoke(context)
    assert len(second.all_intervals) == len(first.all_intervals)
    assert len(second.intervals) == len(first.intervals) - 1

    # Tick it again (empty exclusions): everything is back.
    pipeline.set_fragment_exclusions(context, [])
    third = pipeline.run_karaoke(context)
    assert len(third.intervals) == len(first.intervals)


def test_video_input_status_reports_missing(tmp_path: Path) -> None:
    context = _context(tmp_path)
    # B326: the key is language independent, the name is for the user.
    items = {key: present
             for key, _name, present, _ in pipeline.video_input_status(context)}
    assert items == {"lyrics": False, "karaoke_text": False, "logo": False,
                     "timing": False, "offset": False}

    (context.paths.input_dir / "songtekst.txt").write_text("Kedeng\n",
                                                           encoding="utf-8")
    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "[crowd]\nLa-la-la\n[/crowd]\nEcht zingen\n", encoding="utf-8")
    (context.paths.input_dir / "logo.png").write_bytes(b"png")
    items2 = dict((key, (present, detail)) for key, _name, present, detail
                  in pipeline.video_input_status(context))
    assert items2["lyrics"][0] is True
    assert items2["karaoke_text"] == (True, "2 regels, 1 crowd")
    assert items2["logo"] == (True, "logo.png")
    assert items2["timing"][0] is False


def test_generate_timing_without_alignment(tmp_path: Path) -> None:
    """Without a transcript: best effort, never zeros."""
    from modules.timing import load_timing

    context = _context(tmp_path)
    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "# Intro\nGroen Zwarte Zangers\n[crowd]\nLa-la-la\n[/crowd]\n",
        encoding="utf-8")
    target, count, detail = pipeline.generate_timing(context)
    assert target.exists() and count == 2
    assert "gelijkmatig" in detail
    timed = load_timing(target)
    assert timed[1].crowd is True
    assert all(line.end > line.start > 0 for line in timed)  # no zeros
    # Lines do not overlap and are in order (may touch).
    assert timed[0].end <= timed[1].start


def test_generate_timing_requires_text(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="karaoketekst"):
        pipeline.generate_timing(_context(tmp_path))


def test_generate_timing_falls_back_to_lyrics(tmp_path: Path) -> None:
    """B125: with no karaoke text the video falls back on the lyrics."""
    from modules.timing import load_timing

    context = _context(tmp_path)
    (context.paths.input_dir / "songtekst.txt").write_text(
        "Rood Witte Zangers\nVooraan in de polonaise\n", encoding="utf-8")
    # No karaoketekst.txt present.
    assert pipeline.karaoke_text_path(context).name == "songtekst.txt"
    target, count, _ = pipeline.generate_timing(context)
    assert target.exists() and count == 2
    assert all(line.end > line.start for line in load_timing(target))


def test_apply_manual_damping(tmp_path: Path) -> None:
    """The damping editor can apply and store fragments directly."""
    from dataclasses import asdict

    import numpy as np

    from modules.audio import load_audio, save_wav
    from modules.ffmpeg import AudioProperties

    context = _context(tmp_path)
    karaoke_wav = context.paths.input_dir / "karaoke.wav"
    sample_rate = 22_050
    tone = (0.5 * np.sin(2 * np.pi * 440 *
                         np.arange(3 * sample_rate) / sample_rate)
            ).astype(np.float32)
    save_wav(karaoke_wav, np.stack([tone, tone], axis=1), sample_rate)
    properties = AudioProperties(codec="pcm_s16le", sample_rate=sample_rate,
                                 channels=2, bit_rate=705_600, duration=3.0,
                                 container="wav", is_vbr=None)
    context.store.set_step("source_karaoke", {
        "path": str(karaoke_wav),
        "sha1": pipeline.filesystem.file_sha1(karaoke_wav),
        "wav": str(karaoke_wav),
        "properties": asdict(properties)})

    result = pipeline.apply_manual_damping(context, [(1.0, 1.5), (1.4, 2.0)])
    # Overlapping fragments are merged.
    assert len(result.intervals) == 1
    assert result.intervals[0].start == pytest.approx(1.0)
    assert result.intervals[0].end == pytest.approx(2.0)
    assert result.output_wav.exists()

    # Stored and retrievable for the editor.
    intervals = pipeline.current_damping_intervals(context)
    assert intervals and intervals[0][2] == "manual"

    # The damping really was applied (fragment quieter than before).
    data, _ = load_audio(result.output_wav)
    before = float(np.sqrt(np.mean(data[:int(0.5 * sample_rate), 0] ** 2)))
    during = float(np.sqrt(np.mean(
        data[int(1.6 * sample_rate):int(1.9 * sample_rate), 0] ** 2)))
    assert during < before * 0.2


def test_apply_manual_damping_back_from_original(tmp_path: Path) -> None:
    """B282: a marked fragment is replaced by the original.

    Simulates the Lied J case: the karaoke (a Demucs instrumental)
    weakened or dropped a passage that the original does have (a sound
    effect). "Terug uit origineel" has to make that passage sound
    again - measured here as "clearly louder than the (silent) karaoke
    on that fragment, and close to the level of the original"."""
    from dataclasses import asdict

    import numpy as np

    from modules.audio import load_audio, save_wav
    from modules.ffmpeg import AudioProperties

    context = _context(tmp_path)
    sample_rate = 22_050
    duration_s = 4.0
    n = int(duration_s * sample_rate)

    # Karaoke: silent (as if Demucs removed the sound effect).
    karaoke_wav = context.paths.input_dir / "karaoke.wav"
    silence = np.zeros(n, dtype=np.float32)
    save_wav(karaoke_wav, np.stack([silence, silence], axis=1), sample_rate)
    properties = AudioProperties(codec="pcm_s16le", sample_rate=sample_rate,
                                 channels=2, bit_rate=705_600,
                                 duration=duration_s, container="wav",
                                 is_vbr=None)
    context.store.set_step("source_karaoke", {
        "path": str(karaoke_wav),
        "sha1": pipeline.filesystem.file_sha1(karaoke_wav),
        "wav": str(karaoke_wav),
        "properties": asdict(properties)})

    # Original: a clear tone, also at t=1.0-1.5s (the fragment to be
    # restored). find_audio_file/prepare_track read this from input_dir.
    original_wav = context.paths.input_dir / "original.wav"
    time = np.arange(n) / sample_rate
    tone = (0.6 * np.sin(2 * np.pi * 440 * time)).astype(np.float32)
    save_wav(original_wav, np.stack([tone, tone], axis=1), sample_rate)

    result = pipeline.apply_manual_damping(
        context, [], restore_spans=[(1.0, 1.5, "yeeha")])
    assert result.restore_intervals
    assert result.restore_intervals[0].label == "yeeha"
    assert result.output_wav.exists()

    data, _ = load_audio(result.output_wav)
    outside = float(np.sqrt(np.mean(
        data[int(2.5 * sample_rate):int(3.0 * sample_rate), 0] ** 2)))
    restored = float(np.sqrt(np.mean(
        data[int(1.15 * sample_rate):int(1.35 * sample_rate), 0] ** 2)))
    # Outside the fragment the (silent) karaoke stays unchanged...
    assert outside == pytest.approx(0.0, abs=1e-6)
    # ...but inside the fragment the (loud) original now sounds.
    assert restored > 0.3

    # Stored: a step-4 rerun (e.g. apply_manual_damping with new damping
    # spans but restore_spans=None) must not wipe the choice.
    restored_fragments = pipeline.restore_fragments(context)
    assert len(restored_fragments) == 1
    assert restored_fragments[0].label == "yeeha"

    result2 = pipeline.apply_manual_damping(context, [(2.0, 2.2)])
    assert len(result2.restore_intervals) == 1
    data2, _ = load_audio(result2.output_wav)
    restored2 = float(np.sqrt(np.mean(
        data2[int(1.15 * sample_rate):int(1.35 * sample_rate), 0] ** 2)))
    assert restored2 > 0.3


def test_check_text_alignment(tmp_path: Path) -> None:
    context = _context(tmp_path)
    song = context.paths.input_dir / "songtekst.txt"
    karaoke = context.paths.input_dir / "karaoketekst.txt"

    # Equal number of sections (2 blocks each) -> ok.
    song.write_text("Kedeng kedeng\n\nEen twee drie\n", encoding="utf-8")
    karaoke.write_text("G Z R\n\nnieuwe zin hier\n", encoding="utf-8")
    ok, msg = pipeline.check_text_alignment(context)
    assert ok and "2 secties" in msg

    # A verse dropped out -> warning.
    karaoke.write_text("G Z R\n", encoding="utf-8")
    ok, msg = pipeline.check_text_alignment(context)
    assert not ok and "secties" in msg

    # Crowd does not count as a separate section line.
    karaoke.write_text("G Z R [crowd]Hoi[/crowd]\n\nnieuwe zin hier\n",
                       encoding="utf-8")
    ok, _ = pipeline.check_text_alignment(context)
    assert ok


def test_original_overrides_roundtrip(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assert pipeline.original_overrides(context) == {}
    pipeline.set_original_overrides(context, {"3": [10.0, 12.0]})
    assert pipeline.original_overrides(context) == {"3": [10.0, 12.0]}
    pipeline.clear_original_overrides(context)
    assert pipeline.original_overrides(context) == {}


def test_language_for_uses_the_lyrics_file(tmp_path: Path) -> None:
    """B115: every track detects the language on its own text file.

    Needs ``langdetect``. That library is optional: without it
    ``_language_for`` falls back to "auto" on purpose, and Whisper picks
    for itself. So for years this test failed in environments without
    the library and was carried along as a "known, unrelated failure" -
    while it was not a bug but a missing optional dependency. It now
    skips cleanly instead of standing red, so that a real regression in
    this behaviour does get noticed.
    """
    pytest.importorskip("langdetect")
    context = _context(tmp_path)
    (context.paths.input_dir / "songtekst.txt").write_text(
        "Tu étais formidable, nous étions formidables, formidable",
        encoding="utf-8")
    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "Rood Witte Zangers vooraan in de polonaise, frikandel met mayonaise",
        encoding="utf-8")
    assert pipeline._language_for(context, "original") == "fr"
    # Karaoke detects on the (Dutch) karaoke text, not on the French
    # lyrics.
    assert pipeline._language_for(context, "karaoke") == "nl"


def test_language_for_falls_back_to_auto(tmp_path: Path) -> None:
    context = _context(tmp_path)  # no lyrics file
    assert pipeline._language_for(context, "original") == "auto"


def test_drift_ms_and_collapse(tmp_path: Path) -> None:
    from modules.align import OffsetRegion, regions_to_dicts

    context = _context(tmp_path)
    regions = (OffsetRegion(0.0, 100.0, -0.2, 0.8),
               OffsetRegion(100.0, 200.0, -0.9, 0.7))
    assert pipeline.drift_ms(regions) == pytest.approx(700.0)  # 0.7 s
    assert pipeline.drift_ms(()) == 0.0

    context.store.set_step("align", {"regions": regions_to_dicts(regions)})
    pipeline.collapse_alignment(context)
    step = context.store.get_step("align")
    assert len(step["regions"]) == 1
    # The offset of the most reliable region (-0.2) is what remains.
    assert step["regions"][0]["offset"] == pytest.approx(-0.2)
    assert step["regions"][0]["end"] == pytest.approx(200.0)


def test_demucs_disabled_behaves_as_before(tmp_path: Path) -> None:
    """Without Demucs (off or not installed) nothing changes."""
    from dataclasses import replace

    context = _context(tmp_path)
    # Demucs explicitly off -> _demucs_enabled False.
    context = replace(context, config=replace(
        context.config, advanced=replace(context.config.advanced,
                                             demucs=False)))
    assert pipeline._demucs_enabled(context) is False
    # Missing karaoke -> the usual error message (no generation).
    with pytest.raises(PipelineError, match="karaoke"):
        pipeline.prepare_track(context, "karaoke")


def test_separation_unavailable_raises() -> None:
    from modules import separation
    # In this environment Demucs is not installed.
    if not separation.is_available():
        import pytest as _pytest
        with _pytest.raises(separation.SeparationError):
            separation.separate(Path("x.wav"), Path("/tmp/none"))
