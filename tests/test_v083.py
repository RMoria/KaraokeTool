"""Tests voor v0.83.0-functies (B252 underscore-lettergreep, B251 arbitrage)."""
from __future__ import annotations


# --------------------------------------------------------------------------
# B252 - underscore koppelt woorden tot één lettergreep; _ -> spatie in render
# --------------------------------------------------------------------------
def test_underscore_is_one_syllable() -> None:
    """B252: een underscore-woord telt als één lettergreep en houdt de marker."""
    from modules.timing import split_syllables
    assert split_syllables("'k_heb") == ["'k_heb"]
    assert split_syllables("een_twee_drie") == ["een_twee_drie"]
    # gewone woorden blijven normaal splitsen
    assert split_syllables("Zwarte") == ["Zwar", "te"]


def test_underscore_skeleton_single_syllable() -> None:
    """B252: het skelet maakt van een underscore-woord één lettergreep."""
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton, word_spans
    line = generate_skeleton((TextLine(0, "'k_heb het al", False),),
                             {0: (0.0, 3.0)})[0]
    # 3 woorden: "'k_heb" (1 lettergreep) + "het" (1) + "al" (1) -> 3 syls
    assert len(line.syllables) == 3
    assert line.syllables[0].text == "'k_heb"
    # regel reconstrueert exact (underscore blijft intern staan)
    assert "".join(s.text for s in line.syllables) == "'k_heb het al"
    # word_spans ziet één woord met de underscore
    assert word_spans(line.syllables)[0][0] == "'k_heb"


def test_underscore_atomic_in_phonetic_timing() -> None:
    """B252: fonetische timing splitst een underscore-woord niet verder op."""
    from modules.timing import Syllable, TimedLine, apply_phonetic_timing
    line = TimedLine(0, "'k_heb", False,
                     (Syllable("'k_heb", 0.0, 1.0, held=True),))
    out = apply_phonetic_timing([line], "nl")[0]
    assert len(out.syllables) == 1
    assert out.syllables[0].text == "'k_heb"
    assert (out.syllables[0].start, out.syllables[0].end) == (0.0, 1.0)


def test_underscore_renders_as_space() -> None:
    """B252: in de render wordt de underscore een spatie, meten idem."""
    from PIL import ImageFont

    from modules.video import _disp, _wrap_syllables
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    assert _disp("'k_heb") == "'k heb"
    assert _disp("gewoon") == "gewoon"

    # De weergavebreedte wordt op de spatie-vorm gemeten, niet op de underscore.
    font = ImageFont.load_default()
    line = generate_skeleton((TextLine(0, "'k_heb het", False),))[0]
    rows = _wrap_syllables(line.syllables, font, 100000)
    assert len(rows) == 1                       # past ruim op één rij
    # underscore-lettergreep blijft één cel (geen woordgrens door de spatie)
    assert rows[0][0].text == "'k_heb"


# --------------------------------------------------------------------------
# B251 - geordende + gewogen timing-arbitrage met blok-barrières
# --------------------------------------------------------------------------
def _anchor(ref, t, w, block=0):
    from modules.timing_rules import Candidate, KIND_ANCHOR
    return Candidate("line", ref, t, t, w, 1.0, KIND_ANCHOR, block)


def test_candidate_effect_is_weight_times_confidence() -> None:
    from modules.timing_rules import Candidate, KIND_ANCHOR
    c = Candidate("line", 0, 1.0, 1.0, 2.0, 0.5, KIND_ANCHOR)
    assert c.effect == 1.0


def test_arbitrate_within_block_weighted() -> None:
    """B250 blijft: binnen een blok verdringt een zwaarder anker een zwakker."""
    from modules.timing_rules import arbitrate_anchors
    # regel 1 (zwak, t5) ligt na regel 2 (sterk, t4): de sterke wint.
    cands = [_anchor(0, 0.0, 0.5), _anchor(1, 5.0, 0.5), _anchor(2, 4.0, 2.0)]
    kept = arbitrate_anchors(cands)
    assert set(kept) == {0, 2}
    assert list(kept.values()) == sorted(kept.values())   # monotoon


def test_arbitrate_block_barrier_protects_earlier_block() -> None:
    """B251: een later blok verdringt een eerder-blok-anker niet."""
    from modules.timing_rules import arbitrate_anchors
    # refrein (blok 0) op t8; couplet-regel (blok 1) op t6 (vóór het refrein).
    # Zonder barrière zou de tijd terugspringen; met barrière blijft het
    # refrein-anker staan en wordt het niet-monotone couplet-anker overgeslagen.
    cands = [_anchor(0, 0.0, 10.0, 0), _anchor(1, 8.0, 3.0, 0),
             _anchor(2, 6.0, 3.0, 1)]
    kept = arbitrate_anchors(cands)
    assert 1 in kept and kept[1] == 8.0          # refrein-anker beschermd
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
    s, e = clamp_refinement(1.2, 1.1, 1.0, 2.0)   # end < start -> geklemd
    assert s <= e and 1.0 <= s <= 2.0


def test_sanitize_single_block_barrier_noop() -> None:
    """B251: bij één blok verandert de barrière niets (oud gedrag intact)."""
    from modules.timing import Syllable, TimedLine, sanitize_timing

    def line(idx, start, kwal):
        return TimedLine(idx, f"regel {idx}", False,
                         (Syllable(f"r{idx}", start, start + 0.5),),
                         quality=kwal)
    lines = [line(0, 0.0, "high"), line(1, 2.0, "high"),
             line(2, 4.0, "high")]
    aan = sanitize_timing(lines, first_start=0.0, song_duration=10.0,
                          blok_barriere=True)
    uit = sanitize_timing(lines, first_start=0.0, song_duration=10.0,
                          blok_barriere=False)
    assert [ln.start for ln in aan] == [ln.start for ln in uit]


def test_eval_identical_is_zero_and_skips_mismatch() -> None:
    """B251: gelijke timing -> 0 fout; regels met andere tekst tellen niet mee."""
    from modules.timing_eval import compare

    def rows(items):
        return [{"text": t, "block": b,
                 "syllables": [{"start": s, "end": s + 1.0}]}
                for s, t, b in items]
    ref = rows([(0.0, "een", 0), (2.0, "twee", 1)])
    assert compare(ref, ref)["total"]["onset"]["avg"] == 0.0
    # afwijkende tekst wordt overgeslagen; alleen "een" telt (0 ms)
    auto = rows([(0.0, "een", 0), (9.9, "anders", 1)])
    res = compare(auto, ref)
    assert res["total"]["onset"]["n"] == 1
    assert res["total"]["onset"]["avg"] == 0.0


def test_config_roundtrip_timing_arbitrage(tmp_path) -> None:
    """B251: nieuwe geavanceerd-velden overleven een save/load."""
    from dataclasses import replace

    from modules import config as cfg
    base = cfg.default_config()
    gav = replace(base.advanced, block_anchor_barrier=False,
                  anchor_weight_high=2.5, anchor_weight_onset=12.0)
    conf = replace(base, advanced=gav)
    path = tmp_path / "config.json"
    cfg.save_config(conf, path)
    back = cfg.load_config(path)
    assert back.advanced.block_anchor_barrier is False
    assert back.advanced.anchor_weight_high == 2.5
    assert back.advanced.anchor_weight_onset == 12.0
