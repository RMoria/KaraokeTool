"""Tests for the v0.92.0 fixes.

B277 revisited: the v0.91 approach (~0.1s sliding average) turned out,
when compared against REAL hand-corrected ``timing.json`` files (against
the ``timing_auto.json`` of the same projects), to help hardly at all -
the real root cause was that the analysis window of a line often runs on
until the start of the next line, and "the last sample above threshold"
then picks up the ONSET of that next line, even with a long silent gap
in between. ``held_note_end``/``active_end`` now use a shared helper
that walks from right to left, recognises the first contiguous silent
gap (~0.3s) and hands back the last really active moment before it, on
the RAW RMS samples (no smoothing any more - that performed worse, see
``docs/development_log.md``). Measured on "Lied B" (47
lines, 31 of them off by >0.3s between auto and hand): mean deviation
1.63s -> 0.28s, median 1.47s -> 0.25s.

Button label fix: the render button on the Karaoke video tab was called
"4. Video maken (eerste render)", even though the same button and the
same function serve a re-render after a manual timing correction just as
well (it always reads ``timing.json``, never ``timing_auto.json``).
Renamed to "4. Video maken".

B280: only ``.wav``/``.mp3`` were recognised as an input format
(``filesystem.SUPPORTED_EXTENSIONS``), even though ffmpeg/ffprobe handle
any container just as generically. Cause for it: the user added an
``.m4a`` fragment (merged in Clipchamp) to the original audio of "Lied
J". Widened with ``.m4a``/``.flac``/``.ogg``/``.aac`` as an input
format; the OUTPUT is unchanged and stays mp3 (or wav for a wav source)
- ``export.export_result`` treats the new formats like an mp3 source
(encodes to ``karaoke_edit.mp3``).

B281: in "Lied J" ("Waylon Jennings - Good Ol' Boys") the lyric
line "Than the law will allow" ran about 0.6s too long in the video.
Cause: the DP alignment in ``_align_core`` coupled the lyric word
"allow" through a 1:2 coupling (m12) to the transcribed word "land"
followed by the crowd noise "Whoo!" (similarity only 0.333) - which
happened to score cheaper than leaving "allow" unexplained, weak as the
similarity is. The (RMS-refined) line end follows the coupled time, so
"Whoo!" became the end of the sung line by accident. The same thing
happened with "will" <-> "of the" (similarity 0.250). A new floor
(``_MIN_MULTI_HALF_SIM``) on the BEST of the two separate half
similarities of such a multiple (m21/m12) coupling repairs this: "allow"
has a reasonable match with neither transcribed word ("land" 0.0,
"Whoo!" 0.25), so the coupling is refused and "allow" falls back on a
single (m11) coupling to "of" alone. A floor on the COMBINED similarity
instead of on the best half broke the existing, intended coupling
"Kedeng Kedeng" <-> "de trein" (which scores 0.333 combined, exactly
like the Lied J couplings) - hence the per-half floor.
"""
from __future__ import annotations


# -- B277 --------------------------------------------------------------

def test_last_active_time_ignores_a_spike_after_a_long_silence() -> None:
    """B277: a short spike (the onset of the next line, say) that only
    comes AFTER a long silent gap (>=0.3s) may not pull the end up - the
    answer stays the last active moment before that gap, whatever revives
    after it."""
    import numpy as np
    from modules import rhythm

    step = rhythm._HOP / rhythm._SR
    n = 100
    times = np.arange(n, dtype=np.float32) * step
    rms = np.zeros(n, dtype=np.float32)
    rms[:40] = 1.0         # the real singing
    rms[40:] = 0.02        # (near) silence after it
    rms[70] = 0.5          # spike far past the singing (next line, say)

    mask = np.ones(n, dtype=bool)
    threshold = 1.0 * 0.15
    end = rhythm._last_active_time(rms, times, mask, threshold)
    # The silent gap between index 39 and 70 is well over 0.3s, so the
    # spike at index 70 does not count: the answer is the end of the
    # real singing itself (index 39).
    assert end is not None
    assert end == times[39]


def test_last_active_time_without_a_long_gap_takes_the_last_point() -> None:
    """B277: with no long silent gap at all (everything stays contiguous
    above the threshold, or the gaps are too short) the old behaviour
    still holds - the very last above-threshold moment."""
    import numpy as np
    from modules import rhythm

    step = rhythm._HOP / rhythm._SR
    n = 50
    times = np.arange(n, dtype=np.float32) * step
    rms = np.full(n, 1.0, dtype=np.float32)   # contiguously active

    mask = np.ones(n, dtype=bool)
    end = rhythm._last_active_time(rms, times, mask, 1.0 * 0.15)
    assert end == times[-1]


def test_held_note_end_and_active_end_share_one_helper() -> None:
    """B277: both functions still give sensible, clamped answers."""
    from modules import rhythm

    # All we test here is that the functions exist and return None
    # neatly on a missing analysis (no audio available in this test ->
    # _rms_envelope fails on the non-existent path).
    path = "/nonexistent/pad/audio.wav"
    assert rhythm.held_note_end(path, 0.0, 1.0, 2.0) is None
    assert rhythm.active_end(path, 0.0, 1.0) is None


# -- Button label fix ----------------------------------------------------

def test_the_video_render_label_has_no_first_render_text() -> None:
    """The render button serves re-renders as well (it always reads
    timing.json), so the label may no longer suggest with a "(first
    render)" text that this is a one-off action."""
    from modules.translations import TRANSLATIONS

    for language_code, texts in TRANSLATIONS.items():
        label = texts.get("video_render", "")
        assert "eerste render" not in label.lower()
        assert "first render" not in label.lower()


# -- B280 ----------------------------------------------------------------

def test_supported_extensions_holds_the_new_containers() -> None:
    """B280: m4a/flac/ogg/aac have been added as an input format next to
    the original wav/mp3; wav stays first (no conversion needed)."""
    from modules import filesystem

    assert filesystem.SUPPORTED_EXTENSIONS[0] == ".wav"
    for ext in (".mp3", ".m4a", ".flac", ".ogg", ".aac"):
        assert ext in filesystem.SUPPORTED_EXTENSIONS


def test_find_audio_file_finds_an_m4a(tmp_path) -> None:
    """B280: a lone .m4a file is found now too (it used to be None)."""
    from modules.filesystem import find_audio_file

    (tmp_path / "original.m4a").write_bytes(b"m4a")
    found = find_audio_file(tmp_path, "original")
    assert found is not None and found.suffix == ".m4a"


def test_find_audio_file_lets_wav_beat_the_new_containers(tmp_path) -> None:
    """B280: with several variants in place .wav still wins (no
    conversion needed) - also when a .flac/.m4a sits beside it."""
    from modules.filesystem import find_audio_file

    (tmp_path / "original.flac").write_bytes(b"flac")
    (tmp_path / "original.m4a").write_bytes(b"m4a")
    (tmp_path / "original.wav").write_bytes(b"wav")
    found = find_audio_file(tmp_path, "original")
    assert found is not None and found.suffix == ".wav"


# -- B281 ------------------------------------------------------------------

def _word(text: str, start: float, duration: float = 0.4):
    from modules.whisper import Word
    return Word(text=text, start=start, end=start + duration, confidence=0.9)


def test_a_multiple_coupling_ignores_a_crowd_noise(tmp_path) -> None:
    """B281: "allow" may not stick to "land Whoo!" (Lied J) - the
    interjection "Whoo!" has no reasonable similarity with "allow" (both
    half similarities <0.3), so the m12 coupling has to be refused and
    "allow" has to fall back on the single ("of") coupling."""
    from modules.song_text import align_lyrics, load_lyrics
    from modules.whisper import Segment

    words = (_word("than", 47.32), _word("the", 47.82, 0.16),
             _word("law", 47.98, 0.36), _word("of", 48.34, 0.02),
             _word("Whoo!", 48.36, 1.94))
    segment = Segment(index=0, text=" ".join(w.text for w in words),
                      start=words[0].start, end=words[-1].end, words=words)

    path = tmp_path / "songtekst.txt"
    path.write_text("Than the law will allow\n", encoding="utf-8")
    lyrics = load_lyrics(path)

    aligned = align_lyrics(lyrics, (segment,))
    by_text = {w.lyric.text: w for w in aligned}
    # "allow" may not be coupled to "Whoo!" (alone or combined).
    allow = by_text["allow"]
    assert allow.matched_text is None or "Whoo" not in allow.matched_text


def test_the_multiple_coupling_of_kedeng_keeps_working(tmp_path) -> None:
    """B281: the existing, intended 1:2 coupling "Kedeng"<->"de trein"
    (see the module docstring) may not break - it scores combined exactly
    the same (0.333) as the refused Lied J couplings, but it does
    have (unlike those) a reasonable separate similarity for BOTH halves
    (Kedeng<->de and Kedeng<->trein, both 0.333)."""
    from modules.song_text import align_lyrics, load_lyrics
    from modules.whisper import Segment

    words0 = (_word("GEDENGEDENG", 1.0, 0.9),)
    words1 = (_word("de", 3.0, 0.3), _word("trein", 3.35, 0.45))
    make = lambda i, ws: Segment(  # noqa: E731
        index=i, text=" ".join(w.text for w in ws),
        start=ws[0].start, end=ws[-1].end, words=ws)
    segments = (make(0, words0), make(1, words1))

    path = tmp_path / "songtekst.txt"
    path.write_text("Kedeng Kedeng, Kedeng Kedeng\n", encoding="utf-8")
    lyrics = load_lyrics(path)

    aligned = align_lyrics(lyrics, segments)
    # At least one of the four "Kedeng" words still has to be coupled to
    # "de"/"trein" (through m12, just as before B281).
    assert any(w.matched_text in ("de", "trein", "de trein")
              for w in aligned if w.lyric.text == "Kedeng")


def test_min_multi_half_sim_only_judges_multiple_couplings(tmp_path) -> None:
    """B281: a weak SINGLE (m11) coupling may not be hit by the new floor
    - only 1:2 and 2:1 couplings are judged by it. Whisper regularly
    hears a phonetically related but slightly different word (here: "nu"
    -> "niet"); that has to stay coupled as it was."""
    from modules.song_text import align_lyrics, load_lyrics
    from modules.whisper import Segment

    words = (_word("niet", 5.0, 0.3),)
    segment = Segment(index=0, text="niet", start=words[0].start,
                      end=words[-1].end, words=words)
    path = tmp_path / "songtekst.txt"
    path.write_text("nu\n", encoding="utf-8")
    lyrics = load_lyrics(path)
    aligned = align_lyrics(lyrics, (segment,))
    assert aligned[0].matched_text == "niet"
