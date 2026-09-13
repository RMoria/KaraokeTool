"""Tests voor modules.pipeline (gedeelde laag onder console en GUI)."""

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
    """B81: karaoke uit origineel -> uitlijning overgeslagen, offset 0."""
    context = _context(tmp_path)
    context.store.set_meta("karaoke_from_original", True)
    regions = pipeline.run_alignment(context)
    assert len(regions) == 1
    assert regions[0].offset == 0.0
    assert regions[0].confidence == 1.0


def test_audio_rms_silence_vs_tone(tmp_path: Path) -> None:
    """B83: stilte valt onder de drempel, een toon erboven."""
    silent = tmp_path / "stil.wav"
    save_wav(silent, np.zeros((22_050, 1), dtype=np.float32), 22_050)
    assert pipeline._audio_rms(silent) < pipeline.KARAOKE_VOCAL_SILENCE_RMS
    tone = tmp_path / "toon.wav"
    _write_tone(tone)
    assert pipeline._audio_rms(tone) > pipeline.KARAOKE_VOCAL_SILENCE_RMS


def test_delete_project_removes_dirs(tmp_path: Path) -> None:
    """B84: project verwijderen wist input-, output- en cachemap."""
    from dataclasses import replace
    paths = ProjectPaths(root=tmp_path, song="Lied")
    ensure_directories(paths)
    (paths.input_dir / "original.wav").write_bytes(b"x")
    (paths.output_dir / "iets.txt").write_text("y", encoding="utf-8")
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


def test_export_demucs_karaoke_naar_output(tmp_path: Path,
                                           monkeypatch) -> None:
    """B94: de Demucs-instrumentaal komt als karaoke_demucs.mp3 in output."""
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
    """B95b: bij een net geladen project kloppen alle paden/project.json."""
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
    """B95b: een titel die niet bij de paden past wordt gesignaleerd."""
    from dataclasses import replace
    paths = ProjectPaths(root=tmp_path, song="Lied")
    ensure_directories(paths)
    # Config zegt 'Ander', maar de paden/store horen bij 'Lied'.
    cfg = replace(default_config(),
                  song=replace(default_config().song, title="Ander"))
    ctx = AppContext(config=cfg, paths=paths,
                     store=ProjectStore(paths.project_file))
    ok, message = pipeline.check_project_paths(ctx)
    assert ok is False
    assert "wijken af" in message


def test_filter_hallucinations() -> None:
    """B141: 'MUZIEK'-segmenten worden uit de koppeling gefilterd."""
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


def test_apply_pins_koppelt_en_ontkoppelt() -> None:
    """B121: handmatige pins overschrijven de auto-koppeling."""
    from modules.song_text import AlignedWord, LyricWord, apply_pins
    aligned = (
        AlignedWord(LyricWord(0, "oerend", 0), None, None, None, 0.0),
        AlignedWord(LyricWord(1, "thee", 0), 5.0, 5.4, "PROFITE", 0.3),
    )
    transcript = [("OEHOOR", 3.0, 3.5), ("EN", 3.6, 3.9), ("THEE", 5.0, 5.4)]
    # 1-op-meer: 'oerend' aan twee gevonden woorden; 'thee' losgekoppeld.
    out = apply_pins(aligned, transcript, {0: [0, 1], 1: []})
    assert out[0].start == 3.0 and out[0].end == 3.9      # omvat beide
    assert out[0].matched_text == "OEHOOR EN" and out[0].sim == 1.0
    assert out[1].start is None and out[1].sim == 0.0


def test_cut_word_splitst_en_hermapt_pins() -> None:
    """B153: een gevonden woord knippen + koppelingen hermappen."""
    from modules.song_text import cut_word, remap_pins
    transcript = [("OEREND", 0.0, 2.0), ("HARD", 2.0, 3.0)]
    new, mapping = cut_word(transcript, 0)      # midden van 'OEREND'
    assert [w[0] for w in new] == ["OER", "END", "HARD"]
    assert new[0][1] == 0.0 and new[1][2] == 2.0
    assert mapping == {0: [0, 1], 1: [2]}
    # Een pin op het geknipte woord verwijst nu naar beide helften.
    assert remap_pins({5: [0], 6: [1]}, mapping) == {5: [0, 1], 6: [2]}


def test_merge_words_voegt_samen() -> None:
    """B153: twee aangrenzende gevonden woorden samenvoegen."""
    from modules.song_text import merge_words, remap_pins
    transcript = [("TIEN", 0.0, 1.0), ("IS", 1.0, 2.0), ("TINUS", 2.0, 3.0)]
    new, mapping = merge_words(transcript, 0)
    assert [w[0] for w in new] == ["TIEN IS", "TINUS"]
    assert new[0] == ("TIEN IS", 0.0, 2.0)
    assert mapping == {0: [0], 1: [0], 2: [1]}
    assert remap_pins({3: [0, 1], 4: [2]}, mapping) == {3: [0], 4: [1]}


def test_transcript_override_roundtrip(tmp_path: Path) -> None:
    """B153: bewerkte transcriptie wordt bewaard, teruggelezen en gewist."""
    context = _context(tmp_path)
    assert pipeline.transcript_override(context) is None
    pipeline.set_transcript_override(context, [("OER", 0.0, 1.0),
                                               ("END", 1.0, 2.0)])
    assert pipeline.transcript_override(context) == [("OER", 0.0, 1.0),
                                                     ("END", 1.0, 2.0)]
    pipeline.set_transcript_override(context, None)
    assert pipeline.transcript_override(context) is None


def test_trim_tail_matches_staart() -> None:
    """B159: zwakke matches in de staart worden losgekoppeld, kern blijft."""
    from modules.song_text import AlignedWord, LyricWord, trim_tail_matches
    aligned = (
        AlignedWord(LyricWord(0, "zangers", 0), 1.0, 2.0, "ZANGERS", 0.9),
        AlignedWord(LyricWord(1, "hard", 0), 2.0, 3.0, "HARD", 0.8),
        AlignedWord(LyricWord(2, "oehoe", 1), 50.0, 51.0, "XZ", 0.2),
        AlignedWord(LyricWord(3, "oehoe", 1), 51.0, 52.0, "QP", 0.1),
    )
    out = trim_tail_matches(aligned, min_sim=0.45)
    assert out[0].start == 1.0 and out[1].start == 2.0     # kern blijft
    assert out[2].start is None and out[3].start is None    # staart los


def test_timing_project_mismatch(tmp_path: Path) -> None:
    """B181/B183: mismatch tussen opgeslagen project en huidig project."""
    from modules import timing as timing_module
    from modules.timing import Syllable, TimedLine
    context = _context(tmp_path)  # song.titel = "" standaard
    from dataclasses import replace
    context = replace(context, config=replace(
        context.config, song=replace(context.config.song, title="Lied_N")))
    line = TimedLine(0, "hoi", False, (Syllable("hoi", 0.0, 1.0),))
    # Timing van een ánder project opslaan:
    timing_module.save_timing((line,), context.paths.timing_file,
                              project="Lied_O")
    assert pipeline.timing_project_mismatch(context) == "Lied_O"
    # Zelfde project -> geen mismatch.
    timing_module.save_timing((line,), context.paths.timing_file,
                              project="Lied_N")
    assert pipeline.timing_project_mismatch(context) is None


def test_lyrics_override_roundtrip(tmp_path: Path) -> None:
    """B156: bewerkte songtekstwoorden bewaren, teruglezen en wissen."""
    context = _context(tmp_path)
    assert pipeline.lyrics_override(context) is None
    pipeline.set_lyrics_override(context, [("oeho", 0), ("erend", 0)])
    assert pipeline.lyrics_override(context) == [("oeho", 0), ("erend", 0)]
    pipeline.set_lyrics_override(context, None)
    assert pipeline.lyrics_override(context) is None


def test_word_pins_roundtrip(tmp_path: Path) -> None:
    """B121: woordkoppelingen (lijsten) worden bewaard en teruggelezen."""
    context = _context(tmp_path)
    assert pipeline.word_pins(context) == {}
    pipeline.set_word_pins(context, {0: [3, 4], 2: []})
    assert pipeline.word_pins(context) == {0: [3, 4], 2: []}
    # invalidatie wist de koppelingen (transcript-indices worden ongeldig).
    pipeline.invalidate(context, ["input:lyrics"])
    assert pipeline.word_pins(context) == {}


def test_onset_from_signal_na_stilte() -> None:
    """B133: onset valt na een stille intro (kern-functie, geen ffmpeg)."""
    import numpy as np
    sr = 22_050
    silence = np.zeros(int(3.0 * sr), dtype=np.float32)
    tone = (0.4 * np.sin(2 * np.pi * 300 *
                         np.arange(int(2.0 * sr)) / sr)).astype(np.float32)
    onset = pipeline._onset_from_signal(np.concatenate([silence, tone]), sr)
    assert onset is not None and 2.7 <= onset <= 3.3


def test_ensure_vocal_onset_gebruikt_bewaarde(tmp_path: Path) -> None:
    """B133: een al bepaalde onset wordt hergebruikt (geen herberekening)."""
    context = _context(tmp_path)
    context.store.set_meta("vocal_onset_s", 4.2)
    assert pipeline.ensure_vocal_onset(context) == 4.2


def test_has_transcription_and_analysis(tmp_path: Path) -> None:
    """B134: prerequisite-checks herkennen uitgevoerde stappen."""
    context = _context(tmp_path)
    assert pipeline.has_transcription(context) is False
    assert pipeline.has_analysis(context) is False
    context.store.set_step("whisper_original", {"segments": 3})
    assert pipeline.has_transcription(context) is True
    context.store.set_step("clusters_original", {"selection": []})
    assert pipeline.has_analysis(context) is True


def test_first_vocal_onset(tmp_path: Path) -> None:
    """B130: de onset valt na een stille intro, bij het begin van de toon."""
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
    assert 2.7 <= onset <= 3.3      # rond 3 s (na de stilte)


def test_check_text_alignment_inline_crowd(tmp_path: Path) -> None:
    """B104/B179a: inline-crowd (blijft in de zin) geeft geen valse
    structuur-mismatch als beide teksten dezelfde regelindeling hebben."""
    context = _context(tmp_path)
    (context.paths.input_dir / "songtekst.txt").write_text(
        "K zeg oeh!\nIk zeg ah!\n", encoding="utf-8")
    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "K zeg oeh! [crowd]Oeh![/crowd]\nIk zeg ah! [crowd]Ah![/crowd]\n",
        encoding="utf-8")
    ok, _ = pipeline.check_text_alignment(context)
    assert ok is True


def test_texts_identical(tmp_path: Path) -> None:
    """B115: identieke songtekst en karaoketekst worden herkend."""
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
    """B113/B311: invalidatie wist stappen en timingbestanden.

    Loopt sinds B311 via de afleidingsketen: nieuwe karaoke-audio, dus
    alles wat daaruit volgt."""
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
    """B118: Demucs-karaoke slaat de restzang-transcriptie over."""
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


def test_diagnostiek_toggle_uit(tmp_path: Path) -> None:
    """B143: staat diagnostiek uit, dan wordt er niets geschreven."""
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


def test_diagnostiek_in_submap_en_versie(tmp_path: Path) -> None:
    """B143: diagnostiek in submap; versie alleen bij wijziging gelogd."""
    import json
    context = _context(tmp_path)
    dr = pipeline.DetectResult(pipeline.TRACK_KARAOKE, _fake_segments(), False)
    path = pipeline.write_transcription_history(
        context, pipeline.TRACK_KARAOKE, dr)
    assert path.parent.name == "diagnostics"
    pipeline.write_transcription_history(context, pipeline.TRACK_KARAOKE, dr)
    runs = json.loads(path.read_text(encoding="utf-8"))["runs"]
    # Eerste run bevat de versie, tweede (zelfde versie) niet meer.
    assert "version" in runs[0]
    assert "version" not in runs[1]


def test_write_transcription_history_appends(tmp_path: Path) -> None:
    """B131: elke run wordt met tijdstempel aangevuld in de output."""
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
    assert "segments" in data["runs"][0]        # echte run bewaart segmenten
    assert data["runs"][1]["from_cache"] is True


def _prep_parallel(context, monkeypatch):
    """Vervang zware stappen zodat detect_tracks zonder Whisper/ffmpeg draait."""
    monkeypatch.setattr(pipeline, "prepare_track",
                        lambda ctx, track: context.paths.input_dir /
                        f"{track}.wav")
    monkeypatch.setattr(pipeline, "enabled_tracks",
                        lambda ctx: (pipeline.TRACK_ORIGINAL,
                                     pipeline.TRACK_KARAOKE))


def test_detect_tracks_parallel_beide_tracks(tmp_path: Path,
                                             monkeypatch) -> None:
    """B90: parallel levert beide tracks en per-track voortgang."""
    context = _context(tmp_path)
    _prep_parallel(context, monkeypatch)

    def fake_detect(ctx, track, progress=None, cancelled=None):
        if progress is not None:
            progress(1.0, 2.0)  # per-track voortgang
        return pipeline.DetectResult(track, _fake_segments(), False)

    monkeypatch.setattr(pipeline, "detect_track", fake_detect)
    seen: list[tuple[str, float, float]] = []
    results = pipeline.detect_tracks(
        context, progress=lambda tr, d, t: seen.append((tr, d, t)),
        parallel=True)
    assert set(results) == {pipeline.TRACK_ORIGINAL, pipeline.TRACK_KARAOKE}
    assert {tr for tr, _, _ in seen} == {pipeline.TRACK_ORIGINAL,
                                         pipeline.TRACK_KARAOKE}


def test_detect_tracks_sequentieel(tmp_path: Path, monkeypatch) -> None:
    """B90: met parallel=False draait het één-voor-één (zelfde resultaat)."""
    context = _context(tmp_path)
    _prep_parallel(context, monkeypatch)
    monkeypatch.setattr(
        pipeline, "detect_track",
        lambda ctx, track, progress=None, cancelled=None:
        pipeline.DetectResult(track, (), False))
    results = pipeline.detect_tracks(context, parallel=False)
    assert set(results) == {pipeline.TRACK_ORIGINAL, pipeline.TRACK_KARAOKE}


def test_detect_tracks_oom_terugval(tmp_path: Path, monkeypatch) -> None:
    """B90: geheugentekort in de parallelle run valt terug op sequentieel."""
    context = _context(tmp_path)
    _prep_parallel(context, monkeypatch)
    calls = {"n": 0}

    def flaky_detect(ctx, track, progress=None, cancelled=None):
        calls["n"] += 1
        # Eerste (parallelle) poging: geheugentekort op één track.
        if calls["n"] <= 2 and track == pipeline.TRACK_KARAOKE:
            raise MemoryError("out of memory")
        return pipeline.DetectResult(track, (), False)

    monkeypatch.setattr(pipeline, "detect_track", flaky_detect)
    results = pipeline.detect_tracks(context, parallel=True)
    assert set(results) == {pipeline.TRACK_ORIGINAL, pipeline.TRACK_KARAOKE}


def test_detect_tracks_track_done(tmp_path: Path, monkeypatch) -> None:
    """B96: track_done wordt precies één keer per track aangeroepen."""
    context = _context(tmp_path)
    _prep_parallel(context, monkeypatch)
    monkeypatch.setattr(
        pipeline, "detect_track",
        lambda ctx, track, progress=None, cancelled=None:
        pipeline.DetectResult(track, (), False))
    done: list[str] = []
    pipeline.detect_tracks(context, track_done=done.append, parallel=True)
    assert sorted(done) == [pipeline.TRACK_KARAOKE, pipeline.TRACK_ORIGINAL]


def test_sync_timing_gelijke_structuur(tmp_path: Path) -> None:
    """B99: bij gelijke structuur wordt alleen de gewijzigde regel bijgewerkt."""
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
    assert result[0].syllables == timed[0].syllables  # ongewijzigd
    assert result[1].text == "regel twee anders"      # bijgewerkt
    # De regel-span blijft gelijk (herverdeeld over nieuwe lettergrepen).
    assert result[1].syllables[0].start == timed[1].syllables[0].start


def test_sync_timing_afwijkende_structuur(tmp_path: Path) -> None:
    """B99/B113: bij een andere structuur wordt de timing verwijderd."""
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton, save_timing
    context = _context(tmp_path)
    old_lines = (TextLine(0, "een", False, 0),
                 TextLine(1, "twee", False, 0))
    timed = generate_skeleton(old_lines, {0: (1.0, 2.0), 1: (3.0, 4.0)})
    save_timing(timed, context.paths.timing_file)
    # Nieuwe tekst met een extra blok -> structuur wijkt af.
    new_lines = (TextLine(0, "een", False, 0),
                 TextLine(1, "twee", False, 1))
    updated, message = pipeline.sync_timing_with_text_change(
        context, old_lines, new_lines)
    assert updated is False
    # De niet meer kloppende timing is verwijderd (moet opnieuw gemaakt).
    assert not context.paths.timing_file.exists()


def test_detect_tracks_cancel(tmp_path: Path, monkeypatch) -> None:
    """B90: één gedeelde annulering breekt de parallelle detectie af."""
    from modules import whisper
    context = _context(tmp_path)
    _prep_parallel(context, monkeypatch)

    def cancelling(ctx, track, progress=None, cancelled=None):
        raise whisper.CancelledError()

    monkeypatch.setattr(pipeline, "detect_track", cancelling)
    with pytest.raises(whisper.CancelledError):
        pipeline.detect_tracks(context, cancelled=lambda: True, parallel=True)


def test_cleanup_after_cancel_clears_steps(tmp_path: Path) -> None:
    """B86: opruimen na afbreken wist cache en zet stappen terug."""
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
    """Met een geldige cache wordt Whisper niet aangeroepen.

    Draait sinds B293 via ``detect_tracks(parallel=False)``; het losse
    ``detect_words`` deed exact hetzelfde en is verwijderd.
    """
    from modules.filesystem import file_sha1

    context = _context(tmp_path)
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


def test_load_segments_requires_step_one(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match=r"1\.1\. Detecteer woorden"):
        pipeline.load_segments(_context(tmp_path), "original")


def test_enabled_tracks_altijd_beide(tmp_path: Path) -> None:
    """B174: analyse draait altijd op origineel + karaoke, ongeacht config."""
    from dataclasses import replace

    context = _context(tmp_path)
    assert pipeline.enabled_tracks(context) == ("original", "karaoke")
    # Ook als de (verouderde) config één track uit heeft staan: beide blijven.
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
    assert result.html_path.parent.name == "original"  # eigen map
    assert result.suggested  # 'oe' staat in de standaard-zoekwoorden

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
    """Stap 4 en 5 op basis van een voorbereide administratie."""
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
    """Restwoorden uit de karaoketrack worden zonder stap 3 gedempt."""
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

    # Geen 'align'-stap in de administratie - en toch werkt stap 4.
    karaoke_result = pipeline.run_karaoke(context)
    assert karaoke_result.intervals
    # Tijden zijn NIET geprojecteerd: eerste fragment begint op 0.5 s.
    assert karaoke_result.intervals[0].start == pytest.approx(0.5, abs=0.01)


def test_fragment_exclusions_filter_damping(tmp_path: Path) -> None:
    """Uitgevinkte fragmenten worden niet gedempt maar blijven bekend."""
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

    # Sluit het eerste fragment uit: het verdwijnt uit de actieve demping.
    target = first.all_intervals[0]
    pipeline.set_fragment_exclusions(context, [(target.start, target.end)])
    second = pipeline.run_karaoke(context)
    assert len(second.all_intervals) == len(first.all_intervals)
    assert len(second.intervals) == len(first.intervals) - 1

    # Weer aanvinken (lege uitsluitingen): alles is terug.
    pipeline.set_fragment_exclusions(context, [])
    third = pipeline.run_karaoke(context)
    assert len(third.intervals) == len(first.intervals)


def test_video_input_status_reports_missing(tmp_path: Path) -> None:
    context = _context(tmp_path)
    # B326: de sleutel is taalonafhankelijk, de naam is voor de gebruiker.
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
    """Zonder transcriptie: best-effort, nooit nullen."""
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
    assert all(line.end > line.start > 0 for line in timed)  # geen nullen
    # Regels overlappen niet en staan op volgorde (mogen aansluiten).
    assert timed[0].end <= timed[1].start


def test_generate_timing_requires_text(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="karaoketekst"):
        pipeline.generate_timing(_context(tmp_path))


def test_generate_timing_falls_back_to_lyrics(tmp_path: Path) -> None:
    """B125: zonder karaoketekst valt de video terug op de songtekst."""
    from modules.timing import load_timing

    context = _context(tmp_path)
    (context.paths.input_dir / "songtekst.txt").write_text(
        "Rood Witte Zangers\nVooraan in de polonaise\n", encoding="utf-8")
    # Geen karaoketekst.txt aanwezig.
    assert pipeline.karaoke_text_path(context).name == "songtekst.txt"
    target, count, _ = pipeline.generate_timing(context)
    assert target.exists() and count == 2
    assert all(line.end > line.start for line in load_timing(target))


def test_apply_manual_damping(tmp_path: Path) -> None:
    """De dempings-editor kan fragmenten direct toepassen en bewaren."""
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
    # Overlappende fragmenten worden samengevoegd.
    assert len(result.intervals) == 1
    assert result.intervals[0].start == pytest.approx(1.0)
    assert result.intervals[0].end == pytest.approx(2.0)
    assert result.output_wav.exists()

    # Bewaard en terug op te halen voor de editor.
    intervals = pipeline.current_damping_intervals(context)
    assert intervals and intervals[0][2] == "manual"

    # De demping is echt toegepast (fragment stiller dan ervoor).
    data, _ = load_audio(result.output_wav)
    before = float(np.sqrt(np.mean(data[:int(0.5 * sample_rate), 0] ** 2)))
    during = float(np.sqrt(np.mean(
        data[int(1.6 * sample_rate):int(1.9 * sample_rate), 0] ** 2)))
    assert during < before * 0.2


def test_apply_manual_damping_terug_uit_origineel(tmp_path: Path) -> None:
    """B282: een gemarkeerd fragment wordt vervangen door het origineel.

    Simuleert het Lied J-scenario: de karaoke (Demucs-instrumentaal)
    heeft een stuk verzwakt/weggehaald dat wel in het origineel zit (een
    geluidseffect). "Terug uit origineel" moet dat stuk weer laten
    klinken - hier gemeten als "duidelijk luider dan de (stille) karaoke
    op dat fragment, en dicht bij het origineel-niveau"."""
    from dataclasses import asdict

    import numpy as np

    from modules.audio import load_audio, save_wav
    from modules.ffmpeg import AudioProperties

    context = _context(tmp_path)
    sample_rate = 22_050
    duration_s = 4.0
    n = int(duration_s * sample_rate)

    # Karaoke: stil (alsof Demucs het geluidseffect heeft weggehaald).
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

    # Origineel: een duidelijke toon, ook op t=1.0-1.5s (het te herstellen
    # fragment). find_audio_file/prepare_track lezen dit uit input_dir.
    origineel_wav = context.paths.input_dir / "original.wav"
    time = np.arange(n) / sample_rate
    tone = (0.6 * np.sin(2 * np.pi * 440 * time)).astype(np.float32)
    save_wav(origineel_wav, np.stack([tone, tone], axis=1), sample_rate)

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
    # Buiten het fragment blijft de (stille) karaoke ongewijzigd...
    assert outside == pytest.approx(0.0, abs=1e-6)
    # ...maar binnen het fragment klinkt nu het (luide) origineel.
    assert restored > 0.3

    # Bewaard: een stap-4-herrun (bv. via apply_manual_damping met nieuwe
    # damping-spans maar restore_spans=None) mag de keuze niet wegvegen.
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

    # Gelijk aantal secties (2 blokken elk) -> ok.
    song.write_text("Kedeng kedeng\n\nEen twee drie\n", encoding="utf-8")
    karaoke.write_text("G Z R\n\nnieuwe zin hier\n", encoding="utf-8")
    ok, msg = pipeline.check_text_alignment(context)
    assert ok and "2 secties" in msg

    # Couplet weggevallen -> waarschuwing.
    karaoke.write_text("G Z R\n", encoding="utf-8")
    ok, msg = pipeline.check_text_alignment(context)
    assert not ok and "secties" in msg

    # Crowd telt niet mee als aparte sectie-regel.
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


def test_language_for_uses_songtekst(tmp_path: Path) -> None:
    """B115: elke track detecteert de taal op zijn eigen tekstbestand.

    Vereist ``langdetect``. Die library is optioneel: zonder haar valt
    ``_language_for`` bewust terug op "auto" (Whisper kiest dan zelf). Deze
    test faalde daardoor jarenlang in omgevingen zonder die library, en werd
    telkens als "bekende, niet-gerelateerde faal" meegesleept - terwijl het
    geen bug was maar een ontbrekende optionele dependency. Nu slaat hij
    netjes over in plaats van rood te staan, zodat een echte regressie in
    dit gedrag wél opvalt.
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
    # Karaoke detecteert op de (Nederlandse) karaoketekst, niet op de FR
    # songtekst.
    assert pipeline._language_for(context, "karaoke") == "nl"


def test_language_for_falls_back_to_auto(tmp_path: Path) -> None:
    context = _context(tmp_path)  # geen songtekst
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
    # De offset van de meest betrouwbare regio (-0.2) blijft over.
    assert step["regions"][0]["offset"] == pytest.approx(-0.2)
    assert step["regions"][0]["end"] == pytest.approx(200.0)


def test_demucs_disabled_behaves_as_before(tmp_path: Path) -> None:
    """Zonder Demucs (uit of niet geïnstalleerd) blijft alles bij het oude."""
    from dataclasses import replace

    context = _context(tmp_path)
    # Demucs expliciet uit -> _demucs_enabled False.
    context = replace(context, config=replace(
        context.config, advanced=replace(context.config.advanced,
                                             demucs=False)))
    assert pipeline._demucs_enabled(context) is False
    # Ontbrekende karaoke -> gewone foutmelding (geen generatie).
    with pytest.raises(PipelineError, match="karaoke"):
        pipeline.prepare_track(context, "karaoke")


def test_scheiding_unavailable_raises() -> None:
    from modules import separation
    # In deze omgeving is Demucs niet geïnstalleerd.
    if not separation.is_available():
        import pytest as _pytest
        with _pytest.raises(separation.SeparationError):
            separation.separate(Path("x.wav"), Path("/tmp/none"))
