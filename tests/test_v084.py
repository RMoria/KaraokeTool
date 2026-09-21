"""Tests for the v0.84.0 fixes (B254 forced-alignment window, B256
RMS-envelope cache, B257/B260 crowd coupling in a mixed block, B258
hallucination variants with a function word in them)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


# --------------------------------------------------------------------------
# B256 - RMS envelope: a failure is cached too (no repeated identical
# expensive or broken librosa calls plus a stack trace per line).
# --------------------------------------------------------------------------
def test_rms_envelope_caches_failure(monkeypatch, tmp_path: Path) -> None:
    from modules import rhythm

    rhythm._ENV_CACHE.clear()
    rhythm._ENV_FAILED_LOGGED.clear()
    monkeypatch.setattr(rhythm, "is_available", lambda: True)

    audio = tmp_path / "broken.wav"
    audio.write_bytes(b"niet echt audio")

    calls = {"n": 0}

    class _BrokenLibrosa:
        def load(self, *_a, **_kw):
            calls["n"] += 1
            raise AttributeError("module 'numba' has no attribute 'core'")

    import sys
    monkeypatch.setitem(sys.modules, "librosa", _BrokenLibrosa())

    first = rhythm._rms_envelope(audio)
    second = rhythm._rms_envelope(audio)
    third = rhythm._rms_envelope(audio)

    assert first is None and second is None and third is None
    # Without the fix every call would try librosa.load again (n == 3).
    assert calls["n"] == 1
    # The failure sits in the cache explicitly (as None), not merely
    # "absent" - otherwise there is no telling it apart from "not tried
    # yet".
    key = next(iter(rhythm._ENV_CACHE))
    assert rhythm._ENV_CACHE[key] is None


def test_rms_envelope_failure_logged_once(monkeypatch, tmp_path: Path,
                                          caplog) -> None:
    from modules import rhythm

    rhythm._ENV_CACHE.clear()
    rhythm._ENV_FAILED_LOGGED.clear()
    monkeypatch.setattr(rhythm, "is_available", lambda: True)
    audio = tmp_path / "broken2.wav"
    audio.write_bytes(b"x")

    class _BrokenLibrosa:
        def load(self, *_a, **_kw):
            raise RuntimeError("kapot")

    import sys
    monkeypatch.setitem(sys.modules, "librosa", _BrokenLibrosa())

    with caplog.at_level("ERROR", logger="modules.rhythm"):
        rhythm._rms_envelope(audio)
        rhythm._rms_envelope(audio)
        rhythm._rms_envelope(audio)

    messages = [r for r in caplog.records
                if "RMS-omhullende bepalen mislukt" in r.message]
    assert len(messages) == 1


# --------------------------------------------------------------------------
# B254 - forced alignment: the resampling falls back on scipy when
# librosa (numba) is broken, so that the audio is still loaded in-process
# and no WhisperX ffmpeg window pops up.
# --------------------------------------------------------------------------
def test_resample_falls_back_on_scipy_with_a_broken_librosa(
        monkeypatch) -> None:
    from modules import word_alignment

    class _BrokenLibrosa:
        def resample(self, *_a, **_kw):
            raise AttributeError("module 'numba' has no attribute 'core'")

    import sys
    monkeypatch.setitem(sys.modules, "librosa", _BrokenLibrosa())

    sr = 44_100
    target = 16_000
    tone = (0.3 * np.sin(2 * np.pi * 220 *
                         np.arange(sr) / sr)).astype(np.float32)
    out = word_alignment._resample_to(tone, sr, target)
    assert out is not None
    # ~1 s of audio -> ~16000 samples after resampling.
    assert abs(len(out) - target) < 200


def test_load_mono_16k_works_with_a_broken_librosa_resample(
        monkeypatch, tmp_path: Path) -> None:
    pytest.importorskip("soundfile", exc_type=ImportError)
    from modules import word_alignment
    from modules.audio import save_wav

    sr = 44_100
    tone = (0.3 * np.sin(2 * np.pi * 220 *
                         np.arange(sr) / sr)).astype(np.float32)
    path = tmp_path / "audio.wav"
    save_wav(path, tone.reshape(-1, 1), sr)

    monkeypatch.setattr(word_alignment, "_resample_to",
                        lambda data, sr, target_sr: (_ for _ in ()).throw(
                            AttributeError("numba kapot")))

    # _load_mono_16k catches the error from _resample_to itself (a clean
    # fallback onto the path); this confirms that a broken resampling
    # does not crash but hands back a plain None instead of propagating
    # an exception.
    data = word_alignment._load_mono_16k(path)
    assert data is None


# --------------------------------------------------------------------------
# B260 - crowd lines in a mixed block couple one-to-one to the lyrics as
# soon as the number of lines (crowd included) matches exactly, instead
# of always ending up as a loose interjection. Reproduces "Lied B
# ": a block with 2 crowd lines + 3 sung lines against 5 lyrics
# lines.
# --------------------------------------------------------------------------
def test_couple_crowd_counts_when_block_sizes_match() -> None:
    """B260: 5 karaoke lines (2 crowd + 3 sung) against 5 lyrics lines
    couple one-to-one - the crowd lines too, not as an interjection."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[
        TextLine(0, "De Rood Wit-te Zangers...", True, block=0),
        TextLine(1, "Ik zeg rot hier nu maar op.", False, block=0),
        TextLine(2, "De Rood Wit-te Zangers...", True, block=0),
        TextLine(3, "Ik zeg vrienden, ga maar,", False, block=0),
        TextLine(4, "Het bier is op.", False, block=0),
    ]]
    ob = [[
        (10.0, 12.0, True),   # "Met bloed, zweet en tranen"
        (12.0, 14.0, True),   # "zei ik rot hier nu maar op"
        (14.0, 16.0, True),   # "met bloed, zweet en tranen"
        (16.0, 18.0, True),   # "zei ik vrienden dag vrienden"
        (18.0, 20.0, True),   # "de koek is op"
    ]]
    timed, quality, mapping = couple_timing(kb, ob)
    by = {t.index: t for t in timed}

    # All 5 lines are in the mapping (so really coupled one-to-one),
    # the two crowd lines (index 0 and 2) included.
    assert set(mapping) == {0, 1, 2, 3, 4}
    assert mapping[0] == 0 and mapping[2] == 2

    # The crowd line stands at the time of ITS lyrics line, not in a
    # short interjection slot after the line before it.
    assert by[0].crowd is True
    assert by[0].start == pytest.approx(10.0)
    assert by[0].end == pytest.approx(12.0)
    assert by[2].crowd is True
    assert by[2].start == pytest.approx(14.0)
    assert by[2].end == pytest.approx(16.0)

    # All of it high confidence (one-to-one, reliable original spans).
    assert quality == {"high": 5, "medium": 0, "low": 0}
    # Not one line went down the interjection path (that would give
    # "medium" with a 0.8 s slot instead of the real 2 s lyrics span).
    assert all(round(by[i].end - by[i].start, 3) == 2.0 for i in range(5))


def test_couple_crowd_interjection_still_short_when_counts_differ() -> None:
    """Existing behaviour stands: if the counts do not match, a loose
    crowd line stays a short interjection (an "Oeh!" from the crowd)."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "G Z R", False, block=0),
          TextLine(1, "Oeh!", True, block=0)]]
    ob = [[(5.0, 7.0, True)]]          # 1 lyrics line, 2 karaoke lines
    timed, _, mapping = couple_timing(kb, ob)
    by = {t.index: t for t in timed}
    assert by[1].crowd is True and by[1].crowd_section is False
    # B472: the TIMING stays a short interjection, but the line does get
    # a coupling to the original sentence it comes after - without a
    # coupling it cannot be placed in the editor.
    assert mapping[1] == 0


def test_couple_crowd_matches_original_view_cells_have_no_duplicate() -> None:
    """B257: once the crowd line couples neatly through B260, it should
    no longer show up as a loose, stray cell in the original lane - its
    karaoke index is then simply part of the normal coupling."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[
        TextLine(0, "Crowd-regel", True, block=0),
        TextLine(1, "Zangregel", False, block=0),
    ]]
    ob = [[(0.0, 2.0, True), (2.0, 4.0, True)]]
    _, _, mapping = couple_timing(kb, ob)
    # Both karaoke indexes are in the mapping (so "coupled" as far as
    # the mirror logic in gui.py is concerned) - there is no crowd line
    # left that is treated as having no lyrics equivalent.
    assert set(mapping) == {0, 1}


# --------------------------------------------------------------------------
# B257 - a mirrored crowd line (for the remaining, genuinely uncoupled
# case) is recognisable as such; the crowd flag travels along through
# original_view_cells in all three views.
# --------------------------------------------------------------------------
def test_original_view_cells_marks_mirrored_crowd() -> None:
    from modules.timing import original_view_cells

    originals = [
        {"text": "Een echte originele zin", "start": 0.0, "end": 2.0,
         "rows": [0], "crowd": False},
        {"text": "Oeh!", "start": 2.0, "end": 2.8,
         "rows": [1], "crowd": True},
    ]
    cells = original_view_cells(originals, "sentences")
    assert cells[0]["crowd"] is False
    assert cells[1]["crowd"] is True


def test_original_view_cells_words_mode_propagates_crowd() -> None:
    from modules.timing import original_view_cells

    originals = [
        {"text": "Oeh Oeh", "start": 0.0, "end": 2.0,
         "rows": [0], "crowd": True},
    ]
    cells = original_view_cells(originals, "words")
    assert cells and all(c["crowd"] for c in cells)


def test_original_view_cells_blocks_mode_all_crowd_is_crowd() -> None:
    from modules.timing import original_view_cells

    originals = [
        {"text": "Regel een", "start": 0.0, "end": 1.0, "rows": [0],
         "crowd": True},
        {"text": "Regel twee", "start": 1.0, "end": 2.0, "rows": [1],
         "crowd": True},
    ]
    cells = original_view_cells(originals, "blocks", {0: 0, 1: 0})
    assert len(cells) == 1
    assert cells[0]["crowd"] is True


def test_original_view_cells_missing_crowd_defaults_false() -> None:
    """Backwards compatibility: dicts without "crowd" -> False."""
    from modules.timing import original_view_cells

    originals = [{"text": "Oud formaat", "start": 0.0, "end": 1.0,
                 "rows": [0]}]
    cells = original_view_cells(originals, "sentences")
    assert cells[0]["crowd"] is False


# --------------------------------------------------------------------------
# B258 - the "ZANG EN MUZIEK" hallucination: a function word ("en")
# glues two hallucination words together, so that the segment no longer
# consists purely of known HALLUCINATIONS words and survived (from the
# diagnostics of "Lied B"). "zang" only counts as a
# hallucination signal when it does not appear anywhere in the lyrics of
# this song - otherwise a song that really does sing the word "zang"
# would lose that word.
# --------------------------------------------------------------------------
def test_filter_hallucinations_with_a_function_word_in_between() -> None:
    """B258: 'ZANG EN MUZIEK' (with the function word 'en' in between) is
    filtered out of the coupling just like a bare 'MUZIEK' (B141), as
    long as "zang" appears nowhere in the lyrics of this song."""
    from modules import pipeline
    from modules.song_text import LyricWord
    from modules.whisper import Segment, Word

    segs = (
        Segment(0, "ZANG EN MUZIEK", 229.88, 241.04, (
            Word("ZANG", 229.88, 231.28, 0.42),
            Word("EN", 231.28, 232.68, 0.99),
            Word("MUZIEK", 232.68, 241.04, 0.98),
        )),
        Segment(1, "Bertus op zien Norton", 120.1, 123.4,
                (Word("Bertus", 120.1, 120.6, 0.9),
                 Word("op", 120.6, 120.8, 0.9))),
    )
    # The lyrics of "Lied B" hold no "zang"/"muziek".
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "Ik heb veel bier getapt maar ook veel bier gemorst".split()))
    kept = pipeline._filter_hallucinations(segs, lyrics)
    assert len(kept) == 1
    assert kept[0].text == "Bertus op zien Norton"


def test_filter_hallucinations_without_lyrics_still_filters() -> None:
    """Without lyrics (lyrics=None, as on the old call path) 'zang' keeps
    counting as a signal word - no lyrics means no context that could
    spare the word."""
    from modules import pipeline
    from modules.whisper import Segment, Word

    segs = (
        Segment(0, "ZANG EN MUZIEK", 229.88, 241.04, (
            Word("ZANG", 229.88, 231.28, 0.42),
            Word("EN", 231.28, 232.68, 0.99),
            Word("MUZIEK", 232.68, 241.04, 0.98),
        )),
    )
    kept = pipeline._filter_hallucinations(segs)
    assert len(kept) == 0


def test_filter_hallucinations_spares_zang_when_in_lyrics() -> None:
    """The heart of B258: if "zang" IS in the lyrics of this song
    (phonetically), the segment may NOT be thrown away as a
    hallucination - it can be a word genuinely sung at that moment."""
    from modules import pipeline
    from modules.song_text import LyricWord
    from modules.whisper import Segment, Word

    segs = (
        Segment(0, "Zang en muziek", 50.0, 52.0, (
            Word("Zang", 50.0, 50.5, 0.9),
            Word("en", 50.5, 50.7, 0.9),
            Word("muziek", 50.7, 52.0, 0.9),
        )),
    )
    # These lyrics sing "zang" literally.
    lyrics = tuple(LyricWord(i, t, 0) for i, t in enumerate(
        "Wat een mooie zang klinkt hier".split()))
    kept = pipeline._filter_hallucinations(segs, lyrics)
    assert len(kept) == 1
    assert kept[0].text == "Zang en muziek"


def test_filter_hallucinations_still_needs_real_hallucination_word() -> None:
    """A segment of function words plus one word that is no hallucination
    ('zang' on its own does not count without 'muziek'/'ondertiteling')
    does not survive because the rule got looser: this is the negative
    control that 'zang' alone filters nothing it did not already filter,
    only the combination with a real HALLUCINATIONS word."""
    from modules import pipeline
    from modules.whisper import Segment, Word

    # "Zang en dans" - "dans" is no hallucination word, so this segment
    # has to SURVIVE (this is real text, not an instrumental
    # hallucination).
    segs = (
        Segment(0, "Zang en dans", 10.0, 12.0, (
            Word("Zang", 10.0, 10.5, 0.9),
            Word("en", 10.5, 10.7, 0.9),
            Word("dans", 10.7, 12.0, 0.9),
        )),
    )
    kept = pipeline._filter_hallucinations(segs)
    assert len(kept) == 1
    assert kept[0].text == "Zang en dans"


def test_filter_hallucinations_pure_muziek_still_filtered() -> None:
    """B141 keeps working: a bare 'MUZIEK' is still filtered, even with
    lyrics that do not hold the word - generic Whisper artefacts of the
    MUZIEK/ondertiteling kind stay hallucinations whatever the lyrics
    say (only the separate 'zang' signal-word list is weighed against
    the lyrics)."""
    from modules import pipeline
    from modules.song_text import LyricWord
    from modules.whisper import Segment, Word

    segs = (Segment(0, "MUZIEK", 28.6, 29.0,
                    (Word("MUZIEK", 28.6, 29.0, 0.5),)),)
    lyrics = (LyricWord(0, "muziek", 0),)   # even if the lyrics hold it
    kept = pipeline._filter_hallucinations(segs, lyrics)
    assert len(kept) == 0
