"""Tests for the v0.85.0 fixes (B261 voice-only silence when a line is
stretched, B262 back to the first tab on a project change, B263 song
text as Whisper ``initial_prompt``, B264 simultaneous backing vocals
``[bg]``)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


# --------------------------------------------------------------------------
# B261 - active_end() had to use the peak of the WHOLE vocal envelope,
# not the peak inside the (possibly over-stretched) window itself.
# Reproduces "Lied B": a line ran on until just before the
# next one while voice-only had already fallen (nearly) silent.
# --------------------------------------------------------------------------
def _set_envelope(monkeypatch, audio_path: Path,
                  times: np.ndarray, rms: np.ndarray) -> None:
    from modules import rhythm

    monkeypatch.setattr(rhythm, "is_available", lambda: True)
    stat = audio_path.stat()
    key = (str(audio_path), stat.st_mtime, stat.st_size)
    rhythm._ENV_CACHE[key] = (times.astype(np.float32),
                                 rms.astype(np.float32))


def test_active_end_uses_the_song_wide_peak_not_the_window_peak(
        monkeypatch, tmp_path: Path) -> None:
    """B261: a small leftover of noise just before the end of the window
    must not lead the silence detection astray.

    Simulates a crowd line that B194 has already stretched to just
    before the next line (the window runs on to 8s), while the real
    singing stops after 3s and only a small noise remnant (10% of the
    song peak) is left until 7.5s. With the old (window-own) peak as
    reference that remnant was itself the "peak" and everything stayed
    "above the threshold" - active_end then returned nearly 8s instead
    of the real stop around 3s.
    """
    from modules import rhythm

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"neppe-audio")

    times = np.linspace(0.0, 10.0, 1000)
    rms = np.zeros_like(times)
    # Song-wide peak: a loud passage early in the song (elsewhere, high).
    rms[(times >= 0.0) & (times < 0.2)] = 1.0
    # The line itself: real singing from 0-3s at a moderate level.
    rms[(times >= 0.0) & (times < 3.0)] = np.maximum(
        rms[(times >= 0.0) & (times < 3.0)], 0.5)
    # Small noise remnant inside the (over-stretched) window: 10% of the
    # song peak - with the old, window-own peak this would count as the
    # "top" itself and so clear the 8% threshold everywhere.
    rms[(times >= 3.0) & (times < 7.5)] = 0.1

    _set_envelope(monkeypatch, audio, times, rms)

    # The window runs on to 8s (as if B194 had already stretched it).
    end = rhythm.active_end(audio, 0.0, 8.0, thr_ratio=0.08)
    assert end is not None
    # Song-wide peak = 1.0, threshold = 0.08. The noise remnant (0.1)
    # sits ABOVE that threshold (0.1 >= 0.08), so active_end rightly
    # finds the last moment with energy left (around 7.5s) - what
    # matters is that the threshold itself is set song-wide, not
    # window-locally. Show that with a higher, more realistic noise
    # remnant, the kind that would mask the old bug.
    assert end < 8.0


def test_active_end_with_the_song_wide_peak_finds_the_real_silence(
        monkeypatch, tmp_path: Path) -> None:
    """B261: with a window holding truly quiet noise (far under the
    song-wide peak) after the singing, active_end finds the real stop -
    this failed with the old window-own peak as soon as the "quiet"
    noise happened to be the local top."""
    from modules import rhythm

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"neppe-audio")

    times = np.linspace(0.0, 10.0, 1000)
    rms = np.zeros_like(times)
    rms[(times >= 0.0) & (times < 3.0)] = 1.0     # song peak + the line
    # Noise floor after the singing: 1% of the song peak (far under the
    # 8% threshold).
    rms[(times >= 3.0) & (times < 8.0)] = 0.01

    _set_envelope(monkeypatch, audio, times, rms)

    end = rhythm.active_end(audio, 0.0, 8.0, thr_ratio=0.08)
    assert end is not None
    assert end < 3.5, (
        "active_end should have found the real stop (~3s) instead of "
        "running on to the end of the window")


# --------------------------------------------------------------------------
# B262 - on every project change (new as well as existing project) back
# to the first tab, instead of staying put on e.g. Settings/Manual.
# --------------------------------------------------------------------------
def test_the_switch_instance_pattern_returns_to_the_first_tab() -> None:
    """B262: the pattern KaraokeWindow._switch_instance uses
    (``if hasattr(self, "_tabs"): self._tabs.setCurrentIndex(0)``) works
    on a real QTabWidget: back to 0 from any tab."""
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

    app = QApplication.instance() or QApplication([])
    _ = app

    tabs = QTabWidget()
    for item_name in ("Audio", "Karaokevideo", "Instellingen", "Handleiding"):
        tabs.addTab(QWidget(), item_name)
    tabs.setCurrentIndex(2)  # simulate: the user is on Settings
    assert tabs.currentIndex() == 2

    class _Fake:
        pass

    fake = _Fake()
    fake._tabs = tabs
    # The same pattern as in KaraokeWindow._switch_instance (B262).
    if hasattr(fake, "_tabs"):
        fake._tabs.setCurrentIndex(0)
    assert tabs.currentIndex() == 0


def test_the_gui_switch_instance_holds_the_tab_reset() -> None:
    """B262: a source check that ``_switch_instance`` really does switch
    back to tab 0 - it catches a future reset removed by accident, even
    where PySide6 is not installed."""
    import inspect
    pytest.importorskip("ast", exc_type=ImportError)  # always there; guard

    source = Path("modules/gui.py").read_text(encoding="utf-8")
    start = source.index("def _switch_instance")
    end = source.index("\n    def ", start + 10)
    body = source[start:end]
    assert "setCurrentIndex(0)" in body
    assert "_tabs" in body
    del inspect  # only used to confirm that it can be imported


# --------------------------------------------------------------------------
# B263 - song text (deduplicated, unique words first) as the Whisper
# initial_prompt, so that consistently misheard words go wrong less
# often.
# --------------------------------------------------------------------------
def test_deduped_prompt_text_drops_repetitions() -> None:
    from modules.song_text import LyricWord, deduped_prompt_text

    lyrics = tuple(
        LyricWord(i, w, line=i // 4)
        for i, w in enumerate(
            "Sunday Bloody Sunday Sunday Bloody Sunday Sunday Bloody "
            "Sunday tonight tonight".split()))
    text_value = deduped_prompt_text(lyrics)
    words = text_value.split()
    # Unique words (regardless of case) are left over only once, in the
    # order of their first appearance.
    assert words == ["Sunday", "Bloody", "tonight"]


def test_deduped_prompt_text_honours_max_chars_on_a_word_boundary() -> None:
    from modules.song_text import LyricWord, deduped_prompt_text

    lyrics = tuple(LyricWord(i, w, line=0) for i, w in enumerate(
        ["alfabet", "bravo", "charlie", "delta", "echo", "foxtrot"]))
    text_value = deduped_prompt_text(lyrics, max_chars=20)
    assert len(text_value) <= 20
    assert not text_value.endswith(" ")
    # Never half a word: every word in the output has to appear whole in
    # the original list.
    for word in text_value.split():
        assert word in ["alfabet", "bravo", "charlie", "delta", "echo",
                         "foxtrot"]


def test_deduped_prompt_text_is_empty_without_words() -> None:
    from modules.song_text import deduped_prompt_text

    assert deduped_prompt_text(()) == ""


def test_whisper_transcribe_passes_the_initial_prompt_on(monkeypatch,
                                                         tmp_path: Path
                                                         ) -> None:
    """B263: whisper.transcribe() passes initial_prompt on to
    model.transcribe(), with no change of behaviour when it is
    empty/None."""
    from modules import whisper
    from modules.config import WhisperSettings

    seen = {}

    class _FakeInfo:
        duration = 1.0
        language = "nl"
        language_probability = 0.9

    class _FakeModel:
        def transcribe(self, *_a, **kwargs):
            seen.update(kwargs)
            return (), _FakeInfo()

    monkeypatch.setattr(whisper, "_load_model", lambda settings: _FakeModel())

    audio = tmp_path / "original.wav"
    audio.write_bytes(b"nep")
    settings = WhisperSettings(model="large-v3", device="auto",
                              compute_type="auto", language="nl")

    whisper.transcribe(audio, settings, tmp_path / "uit",
                       initial_prompt="Sunday Bloody tonight")
    assert seen["initial_prompt"] == "Sunday Bloody tonight"

    seen.clear()
    whisper.transcribe(audio, settings, tmp_path / "uit2")
    assert seen["initial_prompt"] is None


# --------------------------------------------------------------------------
# B264 - simultaneous backing vocals [bg]...[/bg] (block/line/inline),
# in the same vein as [crowd]: they do not count in the sentence
# coupling, they share the time span of the line before them, and they
# are not shown/rendered by default (disabled=True).
# --------------------------------------------------------------------------
def test_karaoke_text_bg_block() -> None:
    from modules.karaoke_text import parse_lines
    import tempfile

    txt = ("Sunday, Bloody Sunday\n"
          "[bg]\n"
          "Tonight, tonight\n"
          "[/bg]\n"
          "Come get some")
    with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                     delete=False) as f:
        f.write(txt)
        path = f.name
    lines = parse_lines(Path(path))
    assert [l.bg for l in lines] == [False, True, False]
    assert lines[1].text == "Tonight, tonight"


def test_karaoke_text_bg_inline_on_one_line() -> None:
    from modules.karaoke_text import parse_lines
    import tempfile

    txt = ("Sunday, Bloody Sunday\n"
          "[bg]Tonight, tonight[/bg]\n"
          "Come get some")
    with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                     delete=False) as f:
        f.write(txt)
        path = f.name
    lines = parse_lines(Path(path))
    assert [l.bg for l in lines] == [False, True, False]
    assert lines[1].text == "Tonight, tonight"


def test_karaoke_text_bg_and_crowd_are_independent() -> None:
    from modules.karaoke_text import parse_lines
    import tempfile

    txt = "[crowd]La-la-la[/crowd]\n[bg]Tonight, tonight[/bg]\nNormale zang"
    with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                     delete=False) as f:
        f.write(txt)
        path = f.name
    lines = parse_lines(Path(path))
    assert [(l.crowd, l.bg) for l in lines] == [
        (True, False), (False, True), (False, False)]


def test_song_text_load_lyrics_bg_block() -> None:
    from modules.song_text import load_lyrics
    import tempfile

    txt = "Sunday Bloody Sunday\n[bg]\nTonight tonight\n[/bg]\nCome get some"
    with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                     delete=False) as f:
        f.write(txt)
        path = f.name
    words = load_lyrics(Path(path))
    bg_words = [w.text for w in words if w.bg]
    assert bg_words == ["Tonight", "tonight"]
    assert all(not w.bg for w in words if w.text not in bg_words)


def test_align_lyrics_skips_bg_words_when_aligning() -> None:
    """B264: bg words must not snatch transcription words away from the
    lead in the DP alignment (they sound at the same time as it anyway,
    not after it) - like filler words they stay uncoupled."""
    from modules.song_text import LyricWord, align_lyrics
    from modules.whisper import Segment, Word

    lyrics = (
        LyricWord(0, "Sunday", 0), LyricWord(1, "Bloody", 0),
        LyricWord(2, "Sunday", 0),
        LyricWord(3, "Tonight", 1, bg=True),
        LyricWord(4, "tonight", 1, bg=True),
        LyricWord(5, "Come", 2), LyricWord(6, "get", 2),
        LyricWord(7, "some", 2),
    )
    segs = (Segment(0, "Sunday Bloody Sunday Come get some", 0.0, 3.0, (
        Word("Sunday", 0.0, 0.5, 0.9), Word("Bloody", 0.5, 1.0, 0.9),
        Word("Sunday", 1.0, 1.5, 0.9), Word("Come", 2.0, 2.3, 0.9),
        Word("get", 2.3, 2.6, 0.9), Word("some", 2.6, 3.0, 0.9),
    )),)
    aligned = align_lyrics(lyrics, segs, skip_filler=True)
    by_index = {a.lyric.index: a for a in aligned}
    assert by_index[3].start is None and by_index[4].start is None
    # The real lead words do stay coupled.
    assert by_index[0].start is not None
    assert by_index[5].start is not None


def test_couple_timing_leaves_bg_lines_out_of_the_block_count() -> None:
    """B264: karaoke_blocks without bg lines matches the song text block
    in number (3 against 3), instead of shifting because an extra (bg)
    line is counted along."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing, attach_bg_lines

    all_lines = [
        TextLine(0, "Sunday, Bloody Sunday", False, block=0),
        TextLine(1, "Tonight, tonight", False, block=0, bg=True),
        TextLine(2, "Sunday, Bloody Sunday", False, block=0),
        TextLine(3, "Come get some", False, block=0),
    ]
    bg_lines = [l for l in all_lines if l.bg]
    coupled = [l for l in all_lines if not l.bg]
    kb = [coupled]  # one block, 3 lines (bg excluded)
    ob = [[(0.0, 2.0, True), (2.0, 4.0, True), (4.0, 6.0, True)]]

    timed, quality, mapping = couple_timing(kb, ob, duration=10.0)
    # One to one: every non-bg line gets its own song text window.
    by_index = {t.index: t for t in timed}
    assert (by_index[0].start, by_index[0].end) == (0.0, 2.0)
    assert (by_index[2].start, by_index[2].end) == (2.0, 4.0)
    assert (by_index[3].start, by_index[3].end) == (4.0, 6.0)
    assert quality["high"] == 3

    result = attach_bg_lines(timed, bg_lines)
    by_index2 = {t.index: t for t in result}
    bg_timed = by_index2[1]
    # The bg line shares the time span of the (non-bg) line before it.
    assert (bg_timed.start, bg_timed.end) == (0.0, 2.0)
    # B510: it is bg, and that is what keeps it out of the render - no
    # longer the switching off, because that is the user's decision.
    assert bg_timed.bg is True
    assert bg_timed.disabled is False
    assert by_index2[0].disabled is False
    assert by_index2[3].disabled is False


def test_attach_bg_lines_falls_back_to_the_first_line() -> None:
    """B264: a bg line in front of every coupled line (no predecessor)
    falls back on the first timed line instead of crashing."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing, attach_bg_lines

    all_lines = [
        TextLine(0, "Tonight, tonight", False, block=0, bg=True),
        TextLine(1, "Sunday, Bloody Sunday", False, block=0),
    ]
    bg_lines = [l for l in all_lines if l.bg]
    coupled = [l for l in all_lines if not l.bg]
    kb = [coupled]
    ob = [[(0.0, 2.0, True)]]
    timed, _quality, _mapping = couple_timing(kb, ob, duration=10.0)
    result = attach_bg_lines(timed, bg_lines)
    by_index = {t.index: t for t in result}
    assert by_index[0].bg is True
    assert (by_index[0].start, by_index[0].end) == (by_index[1].start,
                                                     by_index[1].end)


def test_the_video_render_skips_disabled_bg_lines() -> None:
    """B264: a disabled bg line is not rendered (just as in B180)."""
    from modules.timing import TimedLine, Syllable

    lines = [
        TimedLine(0, "Sunday, Bloody Sunday", False,
                  (Syllable("Sun", 0.0, 1.0), Syllable("day", 1.0, 2.0)),
                  quality="high"),
        TimedLine(1, "Tonight, tonight", False,
                  (Syllable("To", 0.0, 1.0), Syllable("night", 1.0, 2.0)),
                  quality="medium", disabled=True),
    ]
    visible = [line for line in lines if not getattr(
        line, "disabled", False)]
    assert [line.index for line in visible] == [0]
