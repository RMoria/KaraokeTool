"""Tests for v0.83.0 (B252 underscore syllable, B251 arbitration)."""
from __future__ import annotations


# --------------------------------------------------------------------------
# B252 - an underscore joins words into one syllable; _ -> space on screen
# --------------------------------------------------------------------------
def test_underscore_is_one_syllable() -> None:
    """B252: an underscore word counts as one syllable and keeps its mark."""
    from modules.timing import split_syllables
    assert split_syllables("'k_heb") == ["'k_heb"]
    assert split_syllables("een_twee_drie") == ["een_twee_drie"]
    # ordinary words still split as usual
    assert split_syllables("Zwarte") == ["Zwar", "te"]


def test_underscore_skeleton_single_syllable() -> None:
    """B252: the skeleton makes one syllable of an underscore word."""
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton, word_spans
    line = generate_skeleton((TextLine(0, "'k_heb het al", False),),
                             {0: (0.0, 3.0)})[0]
    # 3 words: "'k_heb" (1 syllable) + "het" (1) + "al" (1) -> 3 syls
    assert len(line.syllables) == 3
    assert line.syllables[0].text == "'k_heb"
    # the line reconstructs exactly (the underscore stays in place)
    assert "".join(s.text for s in line.syllables) == "'k_heb het al"
    # word_spans sees one word, underscore and all
    assert word_spans(line.syllables)[0][0] == "'k_heb"


def test_underscore_atomic_in_phonetic_timing() -> None:
    """B252: phonetic timing does not split an underscore word further."""
    from modules.timing import Syllable, TimedLine, apply_phonetic_timing
    line = TimedLine(0, "'k_heb", False,
                     (Syllable("'k_heb", 0.0, 1.0, held=True),))
    out = apply_phonetic_timing([line], "nl")[0]
    assert len(out.syllables) == 1
    assert out.syllables[0].text == "'k_heb"
    assert (out.syllables[0].start, out.syllables[0].end) == (0.0, 1.0)


def test_underscore_renders_as_space() -> None:
    """B252: in the render the underscore becomes a space, and it is
    measured that way too."""
    from PIL import ImageFont

    from modules.video import _disp, _wrap_syllables
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    assert _disp("'k_heb") == "'k heb"
    assert _disp("gewoon") == "gewoon"

    # The display width is measured on the space form, not the underscore.
    font = ImageFont.load_default()
    line = generate_skeleton((TextLine(0, "'k_heb het", False),))[0]
    rows = _wrap_syllables(line.syllables, font, 100000)
    assert len(rows) == 1                       # fits easily on one row
    # the underscore syllable stays one cell (the space is no word break)
    assert rows[0][0].text == "'k_heb"


# --------------------------------------------------------------------------
# B251 - ordered and weighted timing arbitration with block barriers
# --------------------------------------------------------------------------
def _anchor(ref, t, w, block=0):
    from modules.timing_rules import Candidate, KIND_ANCHOR
    return Candidate("line", ref, t, t, w, 1.0, KIND_ANCHOR, block)


def test_candidate_effect_is_weight_times_confidence() -> None:
    from modules.timing_rules import Candidate, KIND_ANCHOR
    c = Candidate("line", 0, 1.0, 1.0, 2.0, 0.5, KIND_ANCHOR)
    assert c.effect == 1.0


def test_arbitrate_within_block_weighted() -> None:
    """B250 still holds: inside a block a heavier anchor wins."""
    from modules.timing_rules import arbitrate_anchors
    # line 1 (weak, t5) sits after line 2 (strong, t4): the strong one wins.
    cands = [_anchor(0, 0.0, 0.5), _anchor(1, 5.0, 0.5), _anchor(2, 4.0, 2.0)]
    kept = arbitrate_anchors(cands)
    assert set(kept) == {0, 2}
    assert list(kept.values()) == sorted(kept.values())   # monotonic


def test_arbitrate_block_barrier_protects_earlier_block() -> None:
    """B251: a later block does not push out an earlier block's anchor."""
    from modules.timing_rules import arbitrate_anchors
    # Chorus (block 0) at t8; verse line (block 1) at t6, before it.
    # Without the barrier time would jump back; with it the chorus anchor
    # stays and the non-monotonic verse anchor is skipped.
    cands = [_anchor(0, 0.0, 10.0, 0), _anchor(1, 8.0, 3.0, 0),
             _anchor(2, 6.0, 3.0, 1)]
    kept = arbitrate_anchors(cands)
    assert 1 in kept and kept[1] == 8.0          # chorus anchor protected
    assert list(kept.values()) == sorted(kept.values())


def test_best_per_ref_keeps_strongest() -> None:
    from modules.timing_rules import best_per_ref
    cands = [_anchor(0, 1.0, 1.0), _anchor(0, 2.0, 3.0), _anchor(1, 4.0, 1.0)]
    best = best_per_ref(cands)
    assert best[0].start == 2.0 and best[0].effect == 3.0
    assert set(best) == {0, 1}


def test_clamp_refinement_stays_within_span() -> None:
    from modules.timing_rules import clamp_refinement
    assert clamp_refinement(0.5, 3.0, 1.0, 2.0) == (1.0, 2.0)
    s, e = clamp_refinement(1.2, 1.1, 1.0, 2.0)   # end < start -> clamped
    assert s <= e and 1.0 <= s <= 2.0


def test_sanitize_single_block_barrier_noop() -> None:
    """B251: with one block the barrier changes nothing (old behaviour)."""
    from modules.timing import Syllable, TimedLine, sanitize_timing

    def line(idx, start, quality):
        return TimedLine(idx, f"regel {idx}", False,
                         (Syllable(f"r{idx}", start, start + 0.5),),
                         quality=quality)
    lines = [line(0, 0.0, "high"), line(1, 2.0, "high"),
             line(2, 4.0, "high")]
    on = sanitize_timing(lines, first_start=0.0, song_duration=10.0,
                         blok_barriere=True)
    off = sanitize_timing(lines, first_start=0.0, song_duration=10.0,
                          blok_barriere=False)
    assert [ln.start for ln in on] == [ln.start for ln in off]


def test_eval_identical_is_zero_and_skips_mismatch() -> None:
    """B251: identical timing -> 0 error; lines with other text do not
    count."""
    from modules.timing_eval import compare

    def rows(items):
        return [{"text": t, "block": b,
                 "syllables": [{"start": s, "end": s + 1.0}]}
                for s, t, b in items]
    ref = rows([(0.0, "een", 0), (2.0, "twee", 1)])
    assert compare(ref, ref)["total"]["onset"]["avg"] == 0.0
    # differing text is skipped; only "een" counts (0 ms)
    auto = rows([(0.0, "een", 0), (9.9, "anders", 1)])
    res = compare(auto, ref)
    assert res["total"]["onset"]["n"] == 1
    assert res["total"]["onset"]["avg"] == 0.0


def test_config_roundtrip_timing_arbitration(tmp_path) -> None:
    """B251: the new advanced fields survive a save/load."""
    from dataclasses import replace

    from modules import config as cfg
    base = cfg.default_config()
    advanced = replace(base.advanced, block_anchor_barrier=False,
                       anchor_weight_high=2.5, anchor_weight_onset=12.0)
    conf = replace(base, advanced=advanced)
    path = tmp_path / "config.json"
    cfg.save_config(conf, path)
    back = cfg.load_config(path)
    assert back.advanced.block_anchor_barrier is False
    assert back.advanced.anchor_weight_high == 2.5
    assert back.advanced.anchor_weight_onset == 12.0
