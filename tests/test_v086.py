"""Tests for v0.86.0-fix (B265: stale word pins/alignment/timing after a
genuinely new transcription at "1 Detecteer woorden")."""
from __future__ import annotations

from pathlib import Path

from modules import pipeline
from modules.config import default_config
from modules.filesystem import ProjectPaths, ProjectStore, ensure_directories
from modules.pipeline import AppContext
from modules.whisper import Segment, Word, save_segments


def _context(tmp_path: Path) -> AppContext:
    paths = ProjectPaths(root=tmp_path)
    ensure_directories(paths)
    return AppContext(config=default_config(), paths=paths,
                      store=ProjectStore(paths.project_file))


def _fake_segments() -> tuple[Segment, ...]:
    words = (Word("oeh", 0.5, 0.9, 0.9), Word("oe", 1.2, 1.5, 0.85))
    return (Segment(0, "oeh oe", 0.5, 1.5, words),)


def _write_tone(path: Path, seconds: float = 2.0,
                sample_rate: int = 22_050) -> None:
    import numpy as np
    from modules.audio import save_wav

    time = np.arange(int(seconds * sample_rate)) / sample_rate
    tone = (0.4 * np.sin(2 * np.pi * 440 * time)).astype(np.float32)
    save_wav(path, np.stack([tone, tone], axis=1), sample_rate)


# --------------------------------------------------------------------------
# B265 - running "1 Detecteer woorden" again with a genuinely new
# transcription (other audio/model/language/prompt, so no cache hit) left
# the old, hand-made word pins ("2 Woorden koppelen") standing. Those
# pointed at transcript positions that had nothing to do with the new text
# any more, and were applied to the new transcription all the same.
# Reproduces the report: "Ik heb de woorden gekoppeld. Er zat nog oude
# data in."
# --------------------------------------------------------------------------
def test_detect_track_clears_stale_pins_on_a_new_transcription(
        tmp_path: Path, monkeypatch) -> None:
    """A genuinely new transcription clears old word pins and timing -
    those refer to the old text.

    The ALIGNMENT has deliberately stayed put since B311: it is computed
    from the two audio files and has nothing to do with the
    transcription. Throwing it away anyway meant redoing the (slow)
    offset search while the answer was unchanged.
    """
    context = _context(tmp_path)
    monkeypatch.setattr(pipeline, "prepare_track",
                        lambda ctx, track: ctx.paths.input_dir / "o.wav")
    monkeypatch.setattr(pipeline.filesystem, "file_sha1", lambda p: "sha-nieuw")
    segments = _fake_segments()
    monkeypatch.setattr(pipeline.whisper, "transcribe",
                        lambda *a, **k: segments)

    # Old (stale) pin and alignment data, as left by an earlier detection.
    pipeline.set_word_pins(context, {0: [1]})
    context.store.set_step("align", {"regions": [], "updated": "eerder"})
    context.store.set_step("coupling", {"iets": True})
    context.store.set_step("timing", {"iets": True})
    context.paths.timing_file.parent.mkdir(parents=True, exist_ok=True)
    context.paths.timing_file.write_text("{}", encoding="utf-8")
    context.paths.timing_auto_file.write_text("{}", encoding="utf-8")

    # No existing whisper_origineel step -> guaranteed no cache hit.
    result = pipeline.detect_track(context, pipeline.TRACK_ORIGINAL)

    assert result.from_cache is False
    assert pipeline.word_pins(context) == {}
    assert context.store.get_step("align") is not None      # B311
    assert context.store.get_step("coupling") is None
    assert context.store.get_step("timing") is None
    assert not context.paths.timing_file.exists()
    assert not context.paths.timing_auto_file.exists()


def test_detect_track_cache_hit_keeps_the_pins(
        tmp_path: Path, monkeypatch) -> None:
    """A cache hit (an unchanged re-detection) may NOT throw away
    hand-made word pins - only a genuinely new transcription does.

    B545: Demucs off, otherwise there is nothing to hit. With Demucs on
    the transcription runs on the separated vocal stem, whose checksum
    is not the one this test writes into the step, and the cache miss
    turns the test into a question about separation instead of about
    the pins.
    """
    from dataclasses import replace

    from modules.filesystem import file_sha1

    context = _context(tmp_path)
    context = replace(context, config=replace(
        context.config, advanced=replace(context.config.advanced,
                                         demucs=False)))
    _write_tone(context.paths.input_dir / "original.wav")
    monkeypatch.setattr(pipeline, "prepare_track",
                        lambda ctx, track: ctx.paths.input_dir /
                        "original.wav")
    segments = _fake_segments()
    save_segments(segments, pipeline.transcript_cache(context, "original"))
    checksum = file_sha1(context.paths.input_dir / "original.wav")
    context.store.set_step("whisper_original", {
        "wav_sha1": checksum,
        "model": context.config.whisper.model,
        "language": context.config.whisper.language,
        "initial_prompt": "",
    })
    pipeline.set_word_pins(context, {0: [1]})
    called = {"whisper": False}
    monkeypatch.setattr(pipeline.whisper, "transcribe",
                        lambda *a, **k: called.__setitem__("whisper", True))

    result = pipeline.detect_track(context, pipeline.TRACK_ORIGINAL)

    assert result.from_cache is True
    assert called["whisper"] is False
    assert pipeline.word_pins(context) == {0: [1]}
