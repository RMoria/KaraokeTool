"""Tests for the v0.81.0 features (B239, B241)."""

from __future__ import annotations

from modules import phonetics, song_text, timing
from modules.timing import Syllable, TimedLine


# -- B239: punctuation/symbol tokens ---------------------------------------

def test_is_symbol_token():
    assert song_text.is_symbol_token("?")
    assert song_text.is_symbol_token(">>")
    assert song_text.is_symbol_token("…")
    assert song_text.is_symbol_token("«")
    assert not song_text.is_symbol_token("Reviens")
    assert not song_text.is_symbol_token("m'appelle")


def test_flat_transcript_filters_symbols():
    from modules.whisper import Segment, Word

    def w(t, s, e):
        return Word(text=t, start=s, end=e, confidence=0.9)
    seg = Segment(index=0, start=0.0, end=2.0, text="? Reviens",
                  words=(w("?", 0.0, 0.4), w("Reviens", 0.4, 1.0),
                         w(">>", 1.0, 1.2)))
    flat = song_text.flat_transcript([seg])
    assert [t for t, _s, _e in flat] == ["Reviens"]


# -- B241: phonetic segmentation -------------------------------------------

def test_segment_word_nl():
    assert phonetics.segment_word("boom", "nl") == ["b", "oo", "m"]
    assert phonetics.segment_word("school", "nl") == ["sch", "oo", "l"]


def test_segment_word_en():
    assert phonetics.segment_word("through", "en") == ["thr", "ough"]


def test_segment_weight_vowel_is_heavier():
    cfg = phonetics.SegmentConfig()
    assert phonetics.segment_weight("oo", cfg) > phonetics.segment_weight("b", cfg)
    assert phonetics.segment_weight("m", cfg) > phonetics.segment_weight("b", cfg)


def test_distribute_word_vowel_gets_more():
    segs = phonetics.distribute_word("boom", 0.0, 0.55, "nl")
    durations = {s: round(e - a, 3) for s, a, e in segs}
    assert set(durations) == {"b", "oo", "m"}
    assert durations["oo"] > durations["m"] > durations["b"]
    # reconstructs the word and spans exactly [0, 0.55]
    assert "".join(s for s, _a, _e in segs) == "boom"
    assert abs(segs[0][1] - 0.0) < 1e-6 and abs(segs[-1][2] - 0.55) < 1e-6


def test_distribute_word_final_vowel_lengthened():
    segs = phonetics.distribute_word("formidable", 0.0, 2.0, "en")
    # the last vowel group is 'e' (or 'a'); it gets extra from the reserve
    last_vowel = max((k for k, (s, _a, _e) in enumerate(segs)
                           if phonetics._is_vowel_segment(s)))
    duration = segs[last_vowel][2] - segs[last_vowel][1]
    assert duration > 0.4          # ~30% reserve of 2s + weight


def test_apply_phonetic_timing_keeps_span_and_reconstructs():
    # "boom" as one word, 2 pyphen syllables 0..1 and 1..2
    line = TimedLine(index=0, text="boom", crowd=False, syllables=(
        Syllable(text="boo", start=0.0, end=1.0, held="nl"),
        Syllable(text="m", start=1.0, end=2.0, held="nl"),
    ))
    out = timing.apply_phonetic_timing([line], "nl")[0]
    assert "".join(s.text for s in out.syllables) == "boom"
    assert out.syllables[0].start == 0.0
    assert abs(out.syllables[-1].end - 2.0) < 1e-6
    assert [s.text for s in out.syllables] == ["b", "oo", "m"]


def test_apply_phonetic_timing_keeps_crowd_and_spaces():
    line = TimedLine(index=0, text="oh la", crowd=True, syllables=(
        Syllable(text="oh", start=0.0, end=1.0, held="nl", crowd=True),
        Syllable(text=" la", start=1.0, end=2.0, held="nl", crowd=True),
    ))
    out = timing.apply_phonetic_timing([line], "nl")[0]
    assert all(s.crowd for s in out.syllables)
    # the second word keeps its leading space
    assert any(s.text.startswith(" ") for s in out.syllables)
    assert "".join(s.text for s in out.syllables) == "oh la"
