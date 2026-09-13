"""Tests voor v0.81.0-functies (B239, B241)."""

from __future__ import annotations

from modules import phonetics, song_text, timing
from modules.timing import Syllable, TimedLine


# -- B239: leesteken-/symbool-tokens ---------------------------------------

def test_is_symbol_token():
    assert song_text.is_symbol_token("?")
    assert song_text.is_symbol_token(">>")
    assert song_text.is_symbol_token("…")
    assert song_text.is_symbol_token("«")
    assert not song_text.is_symbol_token("Reviens")
    assert not song_text.is_symbol_token("m'appelle")


def test_flat_transcript_filtert_symbolen():
    from modules.whisper import Segment, Word

    def w(t, s, e):
        return Word(text=t, start=s, end=e, confidence=0.9)
    seg = Segment(index=0, start=0.0, end=2.0, text="? Reviens",
                  words=(w("?", 0.0, 0.4), w("Reviens", 0.4, 1.0),
                         w(">>", 1.0, 1.2)))
    flat = song_text.flat_transcript([seg])
    assert [t for t, _s, _e in flat] == ["Reviens"]


# -- B241: fonetische segmentatie ------------------------------------------

def test_segment_word_nl():
    assert phonetics.segment_word("boom", "nl") == ["b", "oo", "m"]
    assert phonetics.segment_word("school", "nl") == ["sch", "oo", "l"]


def test_segment_word_en():
    assert phonetics.segment_word("through", "en") == ["thr", "ough"]


def test_segment_weight_klinker_zwaarder():
    cfg = phonetics.SegmentConfig()
    assert phonetics.segment_weight("oo", cfg) > phonetics.segment_weight("b", cfg)
    assert phonetics.segment_weight("m", cfg) > phonetics.segment_weight("b", cfg)


def test_distribute_word_klinker_krijgt_meer():
    segs = phonetics.distribute_word("boom", 0.0, 0.55, "nl")
    duren = {s: round(e - a, 3) for s, a, e in segs}
    assert set(duren) == {"b", "oo", "m"}
    assert duren["oo"] > duren["m"] > duren["b"]
    # reconstrueert het woord en beslaat exact [0, 0.55]
    assert "".join(s for s, _a, _e in segs) == "boom"
    assert abs(segs[0][1] - 0.0) < 1e-6 and abs(segs[-1][2] - 0.55) < 1e-6


def test_distribute_word_slotklinker_verlengd():
    segs = phonetics.distribute_word("formidable", 0.0, 2.0, "en")
    # laatste klinkergroep is 'e' (of 'a'); die krijgt extra door de reserve
    last_vowel = max((k for k, (s, _a, _e) in enumerate(segs)
                           if phonetics._is_vowel_segment(s)))
    duration = segs[last_vowel][2] - segs[last_vowel][1]
    assert duration > 0.4          # ~30% reserve van 2s + gewicht


def test_apply_phonetic_timing_behoudt_span_en_reconstrueert():
    # "boom" als één woord, 2 pyphen-lettergrepen 0..1 en 1..2
    line = TimedLine(index=0, text="boom", crowd=False, syllables=(
        Syllable(text="boo", start=0.0, end=1.0, held="nl"),
        Syllable(text="m", start=1.0, end=2.0, held="nl"),
    ))
    out = timing.apply_phonetic_timing([line], "nl")[0]
    assert "".join(s.text for s in out.syllables) == "boom"
    assert out.syllables[0].start == 0.0
    assert abs(out.syllables[-1].end - 2.0) < 1e-6
    assert [s.text for s in out.syllables] == ["b", "oo", "m"]


def test_apply_phonetic_timing_behoudt_crowd_en_spaties():
    line = TimedLine(index=0, text="oh la", crowd=True, syllables=(
        Syllable(text="oh", start=0.0, end=1.0, held="nl", crowd=True),
        Syllable(text=" la", start=1.0, end=2.0, held="nl", crowd=True),
    ))
    out = timing.apply_phonetic_timing([line], "nl")[0]
    assert all(s.crowd for s in out.syllables)
    # tweede woord houdt zijn leidende spatie
    assert any(s.text.startswith(" ") for s in out.syllables)
    assert "".join(s.text for s in out.syllables) == "oh la"
