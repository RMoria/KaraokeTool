"""Tests voor v0.76.0-functies (B210, B212, B213)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from modules import pipeline, song_text
from modules.config import default_config
from modules.filesystem import ProjectPaths, ProjectStore, ensure_directories
from modules.pipeline import AppContext
from modules.whisper import Segment, Word


def _context(tmp_path: Path, title: str = "Test") -> AppContext:
    paths = ProjectPaths(root=tmp_path, song=title)
    ensure_directories(paths)
    cfg = replace(default_config(),
                  song=replace(default_config().song, title=title))
    return AppContext(config=cfg, paths=paths,
                      store=ProjectStore(paths.project_file))


# -- B210: titels per project ----------------------------------------------

def test_apply_project_titles_migreert_globaal(tmp_path):
    ctx = _context(tmp_path)
    ctx = replace(ctx, config=replace(ctx.config, video=replace(
        ctx.config.video, orig_artist="Gala",
        orig_title="Freed from desire")))
    # Eerste keer: geen opgeslagen titels -> globale waarden worden vastgelegd.
    ctx2 = pipeline.apply_project_titles(ctx)
    assert ctx2.config.video.orig_artist == "Gala"
    saved = ctx2.store.get_meta("video_titles")
    assert saved["orig_artist"] == "Gala"
    assert saved["orig_title"] == "Freed from desire"


def test_apply_project_titles_laadt_uit_project(tmp_path):
    ctx = _context(tmp_path)
    pipeline.set_project_title(ctx, "orig_artist", "Gala")
    pipeline.set_project_title(ctx, "orig_title", "Freed from desire")
    # Config leeg, project.json gevuld -> config wordt gevuld vanuit project.
    ctx = replace(ctx, config=replace(ctx.config, video=replace(
        ctx.config.video, orig_artist="", orig_title="")))
    ctx = pipeline.apply_project_titles(ctx)
    assert ctx.config.video.orig_artist == "Gala"
    assert ctx.config.video.orig_title == "Freed from desire"


def test_project_titles_gescheiden_per_project(tmp_path):
    a = _context(tmp_path, "SongA")
    pipeline.set_project_title(a, "orig_artist", "Artiest A")
    b = _context(tmp_path, "SongB")
    pipeline.set_project_title(b, "orig_artist", "Artiest B")
    a2 = pipeline.apply_project_titles(replace(a, config=replace(
        a.config, video=replace(a.config.video, orig_artist=""))))
    b2 = pipeline.apply_project_titles(replace(b, config=replace(
        b.config, video=replace(b.config.video, orig_artist=""))))
    assert a2.config.video.orig_artist == "Artiest A"
    assert b2.config.video.orig_artist == "Artiest B"


# -- B212: stem-export helper ----------------------------------------------

def test_export_demucs_stems_slaat_ontbrekende_over(tmp_path):
    ctx = _context(tmp_path)
    # Geen bestaande bestanden -> geen crash, niets geschreven.
    pipeline.export_demucs_stems(ctx, {"instrumental": tmp_path / "nope.wav"})
    assert not (ctx.paths.output_dir / "karaoke_demucs.mp3").exists()


# -- B213: vulwoorden overslaan in de uitlijning ---------------------------

def test_is_filler_word():
    assert song_text.is_filler_word("na")
    assert song_text.is_filler_word("Na-na-na-na-na")
    assert song_text.is_filler_word("lala")
    assert song_text.is_filler_word("oh")
    assert not song_text.is_filler_word("banana")
    assert not song_text.is_filler_word("desire")
    assert not song_text.is_filler_word("freedom")


def _seg(words):
    ws = [Word(text=t, start=s, end=e, confidence=0.9) for t, s, e in words]
    return Segment(index=0, start=ws[0].start, end=ws[-1].end,
                   text=" ".join(w.text for w in ws), words=tuple(ws))


def test_align_lyrics_skip_filler_houdt_echte_lijnen_recht():
    # Songtekst: freed from desire <na-na x3> want more
    lyrics = tuple(song_text.LyricWord(i, t, 0) for i, t in enumerate(
        ["freed", "from", "desire", "na-na-na", "na-na-na", "na-na-na",
         "want", "more"]))
    # Transcript heeft alleen de echte woorden (geen na-na).
    segs = [_seg([("freed", 0.0, 0.5), ("from", 0.5, 1.0),
                  ("desire", 1.0, 1.5), ("want", 5.0, 5.5),
                  ("more", 5.5, 6.0)])]
    aligned = song_text.align_lyrics(lyrics, segs, skip_filler=True)
    by_index = {a.lyric.text: a for a in aligned}
    # echte woorden gekoppeld
    assert by_index["freed"].start is not None
    assert by_index["want"].start is not None
    assert by_index["more"].start is not None
    # vulwoorden ongekoppeld (geen scheve lijnen)
    na = [a for a in aligned if a.lyric.text == "na-na-na"]
    assert all(a.start is None for a in na)


def test_align_lyrics_zonder_skip_ongewijzigd():
    lyrics = tuple(song_text.LyricWord(i, t, 0)
                   for i, t in enumerate(["freed", "from", "desire"]))
    segs = [_seg([("freed", 0.0, 0.5), ("from", 0.5, 1.0),
                  ("desire", 1.0, 1.5)])]
    a1 = song_text.align_lyrics(lyrics, segs)
    a2 = song_text.align_lyrics(lyrics, segs, skip_filler=True)
    assert [w.matched_text for w in a1] == [w.matched_text for w in a2]
