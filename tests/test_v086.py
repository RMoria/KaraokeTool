"""Tests voor v0.86.0-fix (B265: stale woordkoppeling/uitlijning/timing na
een échte nieuwe transcriptie bij "1 Detecteer woorden")."""
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
# B265 - "1 Detecteer woorden" opnieuw draaien met een échte nieuwe
# transcriptie (andere audio/model/taal/prompt, dus geen cache-hit) liet
# oude, handmatige woordkoppeling ("2 Woorden koppelen") gewoon staan. Die
# verwees daardoor naar transcript-posities die niets meer met de nieuwe
# tekst te maken hadden, en werd alsnog toegepast op de nieuwe transcriptie.
# Reproduceert de melding: "Ik heb de woorden gekoppeld. Er zat nog oude
# data in."
# --------------------------------------------------------------------------
def test_detect_track_wist_stale_koppeling_bij_nieuwe_transcriptie(
        tmp_path: Path, monkeypatch) -> None:
    """Een échte nieuwe transcriptie wist oude woordkoppeling/timing -
    die verwijzen anders naar de oude tekst.

    De UITLIJNING blijft sinds B311 bewust staan: die wordt uit de twee
    audiobestanden berekend en heeft met de transcriptie niets te maken.
    Hem toch weggooien betekende de (trage) offsetbepaling opnieuw doen
    terwijl het antwoord ongewijzigd was."""
    context = _context(tmp_path)
    monkeypatch.setattr(pipeline, "prepare_track",
                        lambda ctx, track: ctx.paths.input_dir / "o.wav")
    monkeypatch.setattr(pipeline.filesystem, "file_sha1", lambda p: "sha-nieuw")
    segments = _fake_segments()
    monkeypatch.setattr(pipeline.whisper, "transcribe",
                        lambda *a, **k: segments)

    # Oude (stale) koppel- en uitlijndata, zoals na een eerdere detectie.
    pipeline.set_word_pins(context, {0: [1]})
    context.store.set_step("align", {"regions": [], "updated": "eerder"})
    context.store.set_step("coupling", {"iets": True})
    context.store.set_step("timing", {"iets": True})
    context.paths.timing_file.parent.mkdir(parents=True, exist_ok=True)
    context.paths.timing_file.write_text("{}", encoding="utf-8")
    context.paths.timing_auto_file.write_text("{}", encoding="utf-8")

    # Geen bestaande whisper_origineel-stap -> gegarandeerd geen cache-hit.
    result = pipeline.detect_track(context, pipeline.TRACK_ORIGINAL)

    assert result.from_cache is False
    assert pipeline.word_pins(context) == {}
    assert context.store.get_step("align") is not None      # B311
    assert context.store.get_step("coupling") is None
    assert context.store.get_step("timing") is None
    assert not context.paths.timing_file.exists()
    assert not context.paths.timing_auto_file.exists()


def test_detect_track_cache_hit_behoudt_koppeling(
        tmp_path: Path, monkeypatch) -> None:
    """Een cache-hit (ongewijzigde herdetectie) mag handmatige woordkoppeling
    NIET weggooien - alleen een echt nieuwe transcriptie doet dat."""
    from modules.filesystem import file_sha1

    context = _context(tmp_path)
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
