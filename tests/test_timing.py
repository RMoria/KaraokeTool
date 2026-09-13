"""Tests voor modules.timing (lettergrepen en timing.json)."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.karaoke_text import TextLine
from modules.timing import (
    editor_view_cells,
    generate_skeleton,
    load_timing,
    save_timing,
    split_line,
    split_syllables,
    word_spans,
)


def test_blok_bewaard_in_timing_json(tmp_path: Path) -> None:
    """B127: het bloknummer overleeft schrijven/lezen van timing.json."""
    lines = generate_skeleton(
        (TextLine(index=0, text="een twee", crowd=False, block=0),
         TextLine(index=1, text="la la", crowd=True, block=2)),
        {0: (0.0, 2.0), 1: (3.0, 4.0)})
    assert [line.block for line in lines] == [0, 2]
    path = tmp_path / "timing.json"
    save_timing(lines, path)
    assert [line.block for line in load_timing(path)] == [0, 2]


def test_editor_view_cells_modi() -> None:
    """B127: blokken/zinnen/woorden geven de juiste cellen."""
    lines = [
        {"text": "een twee", "crowd": False, "block": 0,
         "syllables": [{"text": "een", "start": 0.0, "end": 1.0},
                       {"text": " twee", "start": 1.0, "end": 2.0}]},
        {"text": "drie", "crowd": False, "block": 0,
         "syllables": [{"text": "drie", "start": 2.0, "end": 3.0}]},
        {"text": "la", "crowd": True, "block": 1,
         "syllables": [{"text": "la", "start": 5.0, "end": 6.0}]},
    ]
    assert len(editor_view_cells(lines, "sentences")) == 3
    blocks = editor_view_cells(lines, "blocks")
    assert len(blocks) == 2
    assert blocks[0]["start"] == 0.0 and blocks[0]["end"] == 3.0
    words = editor_view_cells(lines, "words")
    assert [c["text"] for c in words] == ["een", "twee", "drie", "la"]


def test_editor_view_cells_rows() -> None:
    """B162: cellen dragen de bronregels (rows) voor sleep/rek."""
    from modules.timing import editor_view_cells
    lines = [
        {"text": "a b", "crowd": False, "block": 0,
         "syllables": [{"text": "a", "start": 0.0, "end": 1.0},
                       {"text": " b", "start": 1.0, "end": 2.0}]},
        {"text": "c", "crowd": False, "block": 0,
         "syllables": [{"text": "c", "start": 2.0, "end": 3.0}]},
    ]
    assert editor_view_cells(lines, "sentences")[0]["rows"] == [0]
    block = editor_view_cells(lines, "blocks")
    assert block[0]["rows"] == [0, 1]          # heel blok = beide regels
    assert block[0]["text"] == "a b c"          # B163: volledige bloktekst


def test_original_view_cells_modi() -> None:
    """B161: originele baan volgt blokken/zinnen/woorden."""
    from modules.timing import original_view_cells
    originals = [
        {"text": "een twee", "start": 0.0, "end": 2.0, "rows": [0]},
        {"text": "drie", "start": 2.0, "end": 3.0, "rows": [1]},
    ]
    line_block = {0: 0, 1: 0}
    assert len(original_view_cells(originals, "sentences", line_block)) == 2
    assert [c["text"] for c in
            original_view_cells(originals, "words", line_block)] == [
        "een", "twee", "drie"]
    block = original_view_cells(originals, "blocks", line_block)
    assert len(block) == 1 and block[0]["text"] == "een twee drie"


def test_fade_out_herhaling_zelfde_lengte() -> None:
    """B166: een niet-verankerde staartherhaling krijgt de lengte van de
    eerdere zin met dezelfde tekst (i.p.v. gespreid/geplet)."""
    from modules.timing import Syllable, TimedLine, sanitize_timing

    def line(i, text, start, end, kwal):
        return TimedLine(index=i, text=text, crowd=False,
                         syllables=(Syllable(text, start, end),),
                         quality=kwal)
    # Twee verankerde 'oeh'-regels van 2 s, dan een niet-verankerde herhaling.
    lines = (
        line(0, "oeh", 0.0, 2.0, "high"),
        line(1, "tussen", 2.0, 4.0, "high"),
        line(2, "oeh", 6.0, 6.2, "sentence"),      # onbetrouwbaar, moet ~2 s worden
    )
    out = sanitize_timing(lines, song_duration=30.0)
    duration = out[2].end - out[2].start
    assert duration == pytest.approx(2.0, abs=0.3)


def test_klemtoon_default_en_toggle() -> None:
    """B151: standaardklemtoon + verplaatsen/weghalen per woord."""
    from modules.timing import (Syllable, TimedLine, apply_default_stress,
                                set_word_stress)
    line = TimedLine(0, "komen de", False,
                     (Syllable("ko", 0, 1), Syllable("men", 1, 2),
                      Syllable(" de", 2, 3)))
    out = apply_default_stress([line])[0]
    # Meerlettergrepig 'komen' -> eerste lettergreep; 'de' (1 syl) geen.
    assert [s.stress for s in out.syllables] == [True, False, False]
    naar_men = set_word_stress(out.syllables, 1)
    assert [s.stress for s in naar_men] == [False, True, False]
    # Toggle: nog eens klikken haalt de klemtoon weg.
    weg = set_word_stress(naar_men, 1)
    assert [s.stress for s in weg] == [False, False, False]


def test_redistribute_by_stress() -> None:
    """B151: klemtoon weegt zwaarder in de best-effort-duurverdeling; de
    regel-span blijft gelijk en betrouwbare regels blijven onaangeroerd."""
    from modules.timing import (Syllable, TimedLine, redistribute_by_stress)
    sentence = TimedLine(0, "ko men nu", False,
                    (Syllable("ko", 0.0, 1.0, stress=True),
                     Syllable(" men", 1.0, 2.0),
                     Syllable(" nu", 2.0, 3.0)), quality="sentence")
    out = redistribute_by_stress([sentence], weight=1.6)[0]
    duren = [round(s.end - s.start, 2) for s in out.syllables]
    assert duren[0] > duren[1]                      # klemtoon langer
    assert out.start == 0.0 and out.end == pytest.approx(3.0)  # span gelijk
    # Betrouwbare (forced-alignment) regel wordt niet aangeraakt.
    high = TimedLine(1, "a b", False,
                     (Syllable("a", 0.0, 1.0, stress=True),
                      Syllable(" b", 1.0, 2.0)), quality="high")
    assert redistribute_by_stress([high])[0].syllables == high.syllables


def test_inline_crowd_markering(tmp_path: Path) -> None:
    """B179a: inline crowd-woorden krijgen crowd=True op lettergreepniveau,
    en dat overleeft timing.json."""
    from modules.karaoke_text import TextLine
    from modules.timing import (apply_inline_crowd, generate_skeleton,
                                load_timing, save_timing)
    tl = TextLine(index=0, text="G Z R Waertje", crowd=False,
                  crowd_words=frozenset({3}))
    timed = generate_skeleton((tl,), {0: (0.0, 4.0)})
    timed = apply_inline_crowd(timed, (tl,))
    syls = timed[0].syllables
    # Woorden G/Z/R niet crowd; 'Waertje' (2 lettergrepen) wel.
    assert [s.crowd for s in syls][:3] == [False, False, False]
    assert any(s.crowd for s in syls)
    path = tmp_path / "timing.json"
    save_timing(timed, path)
    assert any(s.crowd for s in load_timing(path)[0].syllables)


def test_metadata_en_uitgeschakeld_in_timing_json(tmp_path: Path) -> None:
    """B183/B180: kop (project/versie) + uitgeschakeld-vlag in timing.json."""
    from modules.timing import (Syllable, TimedLine, load_timing,
                                save_timing, timing_project)
    line = TimedLine(0, "hoi", False, (Syllable("hoi", 0.0, 1.0),),
                     disabled=True)
    path = tmp_path / "timing.json"
    save_timing((line,), path, offset=0.0, project="Lied_N",
                versie="0.72.0")
    assert timing_project(path) == "Lied_N"
    back = load_timing(path)
    assert back[0].disabled is True


def test_klemtoon_overleeft_timing_json(tmp_path: Path) -> None:
    """B151: nadruk wordt bewaard in en gelezen uit timing.json."""
    from modules.timing import Syllable, TimedLine, load_timing, save_timing
    line = TimedLine(0, "ko men", False,
                     (Syllable("ko", 0.0, 1.0, stress=True),
                      Syllable(" men", 1.0, 2.0)))
    path = tmp_path / "timing.json"
    save_timing((line,), path)
    back = load_timing(path)
    assert [s.stress for s in back[0].syllables] == [True, False]


def test_word_spans_splitst_op_spatie() -> None:
    """B127: lettergrepen worden op de voorloopspatie tot woorden gegroepeerd."""
    syls = [{"text": "hos", "start": 0.0, "end": 0.5},
            {"text": "sen", "start": 0.5, "end": 1.0},
            {"text": " weer", "start": 1.0, "end": 1.5}]
    assert word_spans(syls) == [("hossen", 0.0, 1.0), ("weer", 1.0, 1.5)]


def test_syllabify_model_indien_beschikbaar() -> None:
    """B150: met pyphen splitsen woorden fijner; reconstructie blijft exact."""
    import pytest as _pytest
    _pytest.importorskip("pyphen")
    # pyphen (nl) splitst 'iederien' in drie lettergrepen; de heuristiek niet.
    pieces = split_syllables("iederien")
    assert "".join(pieces) == "iederien"
    assert len(pieces) == 3


def test_split_syllables_dutch() -> None:
    assert split_syllables("Groen") == ["Groen"]
    assert split_syllables("Zwarte") == ["Zwar", "te"]
    assert split_syllables("Zangers") == ["Zan", "gers"]
    assert split_syllables("polonaise") == ["po", "lo", "nai", "se"]
    assert split_syllables("kedeng") == ["ke", "deng"]
    assert split_syllables("TVX") == ["T", "V", "X"]  # gespelde letters
    assert split_syllables("OE") == ["OE"]  # klinkers -> vocable, 1


def test_split_line_reconstructs_exactly() -> None:
    line = "Rood Witte Zangers, vooraan in de polonaise"
    pieces = split_line(line)
    assert "".join(pieces) == line
    assert pieces[0] == "Rood"
    assert pieces[1] == " Wit"  # nieuw woord: voorloopspatie


def test_generate_skeleton_with_spans() -> None:
    lines = (TextLine(0, "Kedeng Kedeng", False),
             TextLine(1, "La-la-la", True))
    timed = generate_skeleton(lines, {0: (10.0, 12.0)})
    assert timed[0].start == pytest.approx(10.0)
    assert timed[0].end == pytest.approx(12.0)
    # Gelijkmatig verdeeld over 4 lettergrepen (ke/deng ke/deng).
    assert len(timed[0].syllables) == 4
    assert timed[0].syllables[1].start == pytest.approx(10.5)
    # Zonder tijden: alles op 0; crowd blijft behouden.
    assert timed[1].end == 0.0
    assert timed[1].crowd is True


def test_timing_roundtrip(tmp_path: Path) -> None:
    lines = (TextLine(0, "Kedeng Kedeng", False),)
    timed = generate_skeleton(lines, {0: (1.0, 2.0)})
    path = tmp_path / "timing.json"
    save_timing(timed, path)
    assert load_timing(path) == timed


def test_timing_offset_roundtrip_en_oud_formaat(tmp_path: Path) -> None:
    """B98: offset wordt bewaard; oud kale-lijst-formaat blijft leesbaar."""
    import json

    from modules.timing import load_offset
    lines = (TextLine(0, "Kedeng Kedeng", False),)
    timed = generate_skeleton(lines, {0: (1.0, 2.0)})
    path = tmp_path / "timing.json"
    save_timing(timed, path, offset=-0.192)
    assert load_offset(path) == -0.192
    assert load_timing(path) == timed
    # Oud formaat (kale lijst) -> offset onbekend, regels nog leesbaar.
    old = [{"line": 0, "text": "a", "crowd": False, "crowd_section": False,
            "quality": "sentence",
            "syllables": [{"text": "a", "start": 1.0, "end": 2.0,
                              "held": False}]}]
    path.write_text(json.dumps(old), encoding="utf-8")
    assert load_offset(path) is None
    assert len(load_timing(path)) == 1


def _tl(index, text, start, end, quality="sentence"):
    from modules.timing import Syllable, TimedLine
    pieces = split_line(text)
    n = len(pieces)
    width = (end - start) / n if n else 0.0
    syl = tuple(Syllable(p, round(start + i * width, 3),
                         round(start + (i + 1) * width, 3))
                for i, p in enumerate(pieces))
    return TimedLine(index=index, text=text, crowd=False, syllables=syl,
                     quality=quality)


def test_sanitize_timing_begrenst_en_monotoon() -> None:
    """B106: extreme duren worden begrensd, volgorde blijft monotoon."""
    from modules.timing import sanitize_timing
    lines = (
        _tl(0, "Rood Witte Zangers vooraan", 10.0, 12.5, "high"),  # ref
        _tl(1, "Frikandel met mayonaise samen", 12.5, 42.5),  # 30s -> te lang
        _tl(2, "Waar ik altijd verder ga door", 42.6, 42.65),  # ~0 -> te kort
    )
    out = sanitize_timing(lines)
    spans = [ln.end - ln.start for ln in out]
    assert all(sp > 0 for sp in spans)
    assert spans[1] < 12.0          # niet meer 30 s
    assert spans[2] >= 1.0          # echte zin minstens ~1 s
    # monotoon, geen overlap
    assert out[1].start >= out[0].end - 1e-6
    assert out[2].start >= out[1].end - 1e-6


def test_sanitize_timing_herverdeelt_tussen_ankers() -> None:
    """B106: opeengehoopte regels worden tussen ankers verspreid (niet gepropt)."""
    from modules.timing import sanitize_timing
    lines = (
        _tl(0, "Rood Witte Zangers vooraan", 0.0, 2.0, "high"),  # anker
        _tl(1, "Frikandel met mayonaise erbij", 2.0, 2.05),  # gepropt (laag)
        _tl(2, "Waar ik altijd verder ga door", 10.0, 12.0, "high"),  # anker
    )
    out = sanitize_timing(lines)
    # De middelste regel staat nu ergens tussen de ankers, niet meer vlak
    # achter regel 0 op ~2.05 s.
    assert out[1].start > 3.5
    assert out[1].start < out[2].start
    assert out[0].end <= out[1].start + 1e-6      # monotoon


def test_sanitize_timing_pauze_blijft_staan() -> None:
    """B147: een betrouwbare zin houdt zijn echte einde; pauze blijft staan."""
    from modules.timing import sanitize_timing
    lines = (
        _tl(0, "Want ze hadden van de motorcross", 4.0, 6.0, "high"),
        _tl(1, "Oehoe oehoerend hard vooraan", 10.0, 12.0, "high"),
    )
    out = sanitize_timing(lines)
    # Regel 0 eindigt rond zijn echte einde (~6 s), niet dichtgeplakt tot 10.
    assert out[0].end < 8.0
    assert out[1].start - out[0].end > 0.4        # zichtbare pauze


def test_sanitize_timing_kleine_kloof_sluit_aan() -> None:
    """B147: een kleine kloof (<0.4 s) wordt weggepoetst (aansluiten)."""
    from modules.timing import sanitize_timing
    lines = (
        _tl(0, "Rood Witte Zangers samen", 4.0, 7.8, "high"),
        _tl(1, "Frikandel met mayonaise erbij", 8.0, 11.0, "high"),
    )
    out = sanitize_timing(lines)
    assert abs(out[0].end - out[1].start) < 1e-6   # aaneengesloten


def test_sanitize_timing_spreidt_opgepropte_staart() -> None:
    """B139/B148: dicht opeengezette herhaal-/crowdregels worden gespreid,
    niet tot ~0 s geplet."""
    from modules.timing import sanitize_timing
    # Vier meerlettergrepige regels die de koppeling ~0.35 s uit elkaar zette.
    lines = tuple(
        _tl(i, "la la la la la", 100.0 + i * 0.35, 100.0 + i * 0.35 + 0.3,
            "high")
        for i in range(4)
    )
    out = sanitize_timing(lines, song_duration=240.0)
    spans = [ln.end - ln.start for ln in out]
    assert all(sp >= 0.99 for sp in spans)         # niet meer 0.35 s
    # Monotoon oplopend en gespreid (elke start na de vorige).
    for a, b in zip(out, out[1:]):
        assert b.start >= a.end - 1e-6


def test_sanitize_timing_fade_out_vult_tot_eind() -> None:
    """B148: veel staart-regels zonder anker vullen de resttijd tot het eind,
    niet opgepropt vlak na het laatste anker."""
    from modules.timing import sanitize_timing
    # 1 anker rond 180 s, daarna 12 herhaal-fade-out-regels (laag), lied 222 s.
    lines = [_tl(0, "Nooit meer oerend hard samen", 178.0, 181.0, "high")]
    for i in range(1, 13):
        lines.append(_tl(i, "Want de Zangers oehoe oehoe", 181.0, 181.3,
                         "low"))
    out = sanitize_timing(tuple(lines), song_duration=222.0)
    # De laatste fade-out-regel eindigt in de buurt van het lied-einde,
    # niet al rond 193 s (opgepropt).
    assert out[-1].end > 205.0
    # Monotoon en geen 0-regels.
    for a, b in zip(out, out[1:]):
        assert b.start >= a.end - 1e-6
        assert b.end > b.start


def test_sanitize_timing_first_start_anker() -> None:
    """B130: de eerste zin wordt op de onset verankerd."""
    from modules.timing import sanitize_timing
    lines = (_tl(0, "K zeg oeh vooraan samen", 28.0, 40.0),)
    out = sanitize_timing(lines, first_start=3.5)
    assert abs(out[0].start - 3.5) < 1e-6


def test_enforce_monotonic_geen_nul_of_herorden() -> None:
    """B108: begin<eind, geen 0-regel, geen herordening."""
    from modules.timing import enforce_monotonic
    lines = (
        _tl(0, "een twee drie", 5.0, 7.0),
        _tl(1, "vier vijf zes", 3.0, 3.0),   # 0-span én vóór regel 0
    )
    out = enforce_monotonic(lines)
    assert out[0].end > out[0].start
    assert out[1].start >= out[0].end        # niet herordend
    assert out[1].end > out[1].start          # geen 0-regel


def test_timing_report_flags() -> None:
    """B129: het rapport markeert korte regels en overlap."""
    from modules.timing import timing_report
    lines = (
        _tl(0, "een twee drie vier", 5.0, 8.0),
        _tl(1, "vijf zes", 6.0, 6.1),  # overlap + kort
    )
    report = timing_report(lines, offset=-0.192, source_karaoke="demucs")
    assert "bron-karaoke=demucs" in report
    assert "KORT" in report
    assert "OVERLAP" in report


def test_reanchor_verschuift_alle_tijden(tmp_path: Path) -> None:
    """B98: reanchor schuift alle lettergreeptijden met het verschil op."""
    from modules.timing import reanchor
    lines = (TextLine(0, "Kedeng Kedeng", False),)
    timed = generate_skeleton(lines, {0: (1.0, 2.0)})
    shifted = reanchor(timed, 0.192)
    assert shifted[0].syllables[0].start == round(
        timed[0].syllables[0].start + 0.192, 3)
    # Nul-verschuiving laat alles ongemoeid.
    assert reanchor(timed, 0.0) == timed


def test_best_effort_syllable_level() -> None:
    """Gelijk aantal lettergrepen: exacte lettergreeptijden."""
    from modules.timing import best_effort_skeleton

    lines = (TextLine(0, "Zangers vooraan", False),)  # Zan-gers voor-aan
    original = [[("kedeng", 10.0, 11.0), ("kedeng", 11.0, 12.0)]]  # 4 syl
    timed, quality = best_effort_skeleton(lines, original)
    assert quality == {"syllable": 1, "word": 0, "sentence": 0}
    assert timed[0].syllables[0].start == pytest.approx(10.0)
    assert timed[0].syllables[1].start == pytest.approx(10.5)
    assert timed[0].end == pytest.approx(12.0)


def test_best_effort_word_level() -> None:
    """Gelijk aantal woorden: woordtijden, lettergrepen verdeeld."""
    from modules.timing import best_effort_skeleton

    lines = (TextLine(0, "Zangers hey", False),)  # 3 lettergrepen, 2 woorden
    original = [[("kedeng", 10.0, 11.0), ("oe", 11.5, 12.0)]]  # 3 syl? 2+1=3
    # 3 originele lettergrepen == 3 stuks: dit wordt lettergreepniveau;
    # forceer woordniveau met een afwijkend aantal lettergrepen.
    original = [[("trein", 10.0, 11.0), ("oe", 11.5, 12.0)]]  # 1+1=2 syl
    timed, quality = best_effort_skeleton(lines, original)
    assert quality["word"] == 1
    # 'Zangers' (2 lettergrepen) binnen woord 1: 10.0-10.5-11.0.
    assert timed[0].syllables[1].start == pytest.approx(10.5)
    assert timed[0].syllables[2].start == pytest.approx(11.5)  # 'hey'


def test_best_effort_sentence_level_and_projection() -> None:
    from modules.timing import best_effort_skeleton

    lines = (TextLine(0, "Heel veel meer woorden dan origineel", False),)
    original = [[("kort", 10.0, 12.0)]]
    timed, quality = best_effort_skeleton(
        lines, original, project=lambda t: t - 0.5)
    assert quality["sentence"] == 1
    assert timed[0].start == pytest.approx(9.5)  # projectie toegepast
    assert timed[0].end == pytest.approx(11.5)


def test_best_effort_proportional_line_mapping() -> None:
    """Meer karaokeregels dan songtekstregels: proportioneel verdeeld."""
    from modules.timing import best_effort_skeleton

    lines = tuple(TextLine(i, f"regel {i}", False) for i in range(4))
    original = [[("een", 10.0, 11.0)], [("twee", 50.0, 51.0)]]
    timed, _ = best_effort_skeleton(lines, original)
    assert timed[0].start < 12 and timed[1].start < 12   # eerste helft
    assert timed[2].start >= 50 and timed[3].start >= 50  # tweede helft


def test_fallback_even_never_zero() -> None:
    from modules.timing import fallback_even

    lines = tuple(TextLine(i, "la la", i % 2 == 0) for i in range(5))
    timed = fallback_even(lines, 120.0)
    assert all(line.end > line.start >= 8.0 for line in timed)
    starts = [line.start for line in timed]
    assert starts == sorted(starts)


def test_best_effort_splits_shared_lines_in_order() -> None:
    """Regels die dezelfde originele regel delen krijgen opvolgende,
    eigen tijdvakken; volgorde en volledigheid gegarandeerd."""
    from modules.timing import best_effort_skeleton

    lines = tuple(TextLine(i, f"regel {i}", False) for i in range(4))
    original = [[("een", 10.0, 12.0)], [("twee", 50.0, 52.0)]]
    timed, _ = best_effort_skeleton(lines, original)
    assert [line.index for line in timed] == [0, 1, 2, 3]
    # Paar 0/1 deelt 10-12, paar 2/3 deelt 50-52 - opvolgend gesplitst.
    assert timed[0].end == pytest.approx(timed[1].start)
    assert timed[0].start == pytest.approx(10.0)
    assert timed[1].end == pytest.approx(12.0)
    assert timed[2].start == pytest.approx(50.0)
    # Elke regel heeft een eigen tijdvak (geen duplicaten).
    spans = [(line.start, line.end) for line in timed]
    assert len(set(spans)) == 4


def test_quality_is_saved_and_loaded(tmp_path: Path) -> None:
    from modules.timing import best_effort_skeleton, load_timing, save_timing

    lines = (TextLine(0, "Zangers vooraan", False),)
    original = [[("kedeng", 10.0, 11.0), ("kedeng", 11.0, 12.0)]]
    timed, _ = best_effort_skeleton(lines, original)
    assert timed[0].quality == "syllable"
    path = tmp_path / "timing.json"
    save_timing(timed, path)
    assert load_timing(path)[0].quality == "syllable"


def test_fallback_marks_gelijkmatig() -> None:
    from modules.timing import fallback_even

    timed = fallback_even((TextLine(0, "la", False),), 60.0)
    assert timed[0].quality == "even"


def test_snap_time() -> None:
    from modules.timing import snap_time

    # Binnen 10 px op 60 px/s (= 0,167 s): snappen.
    assert snap_time(10.1, 10.0, 60.0) == 10.0
    # Erbuiten: niet snappen.
    assert snap_time(10.5, 10.0, 60.0) == 10.5
    # Meer ingezoomd (200 px/s): 0,1 s is dan 20 px - niet snappen.
    assert snap_time(10.1, 10.0, 200.0) == 10.1
    # Geen afspeellijn: waarde ongemoeid.
    assert snap_time(10.1, None, 60.0) == 10.1


def test_clamp_span_prevents_overlap() -> None:
    from modules.timing import clamp_span

    blocked = [(10.0, 12.0), (15.0, 17.0)]
    # Verschuiven tegen het volgende blok aan: inrekken tot de grens.
    assert clamp_span(13.0, 16.0, blocked) == (13.0, 15.0)
    # Tegen het vorige blok aan: begin opschuiven.
    assert clamp_span(11.0, 14.0, blocked) == (12.0, 14.0)
    # Vrij venster: ongewijzigd.
    assert clamp_span(12.5, 14.5, blocked) == (12.5, 14.5)
    # Midden in een blok: spring naar het dichtstbijzijnde vrije gat.
    tight = [(10.0, 12.0), (12.1, 14.0)]
    jumped = clamp_span(11.9, 12.6, tight, min_length=0.2)
    assert jumped[0] >= 14.0  # achter het blokkerende blok
    # Zonder blokkades: ongewijzigd.
    assert clamp_span(1.0, 2.0, []) == (1.0, 2.0)


def test_line_assignments() -> None:
    from modules.timing import line_assignments

    assert line_assignments(4, 4) == [0, 1, 2, 3]      # 1-op-1
    assert line_assignments(4, 2) == [0, 0, 1, 1]      # delen
    assert line_assignments(2, 4) == [0, 2]            # overslaan
    assert line_assignments(3, 1) == [0, 0, 0]


def test_remap_relative_follows_reference() -> None:
    from modules.timing import remap_relative

    # Referentie schuift 2 s op: karaokezin schuift mee.
    assert remap_relative(11.0, 12.0, (10.0, 14.0), (12.0, 16.0)) == \
        pytest.approx((13.0, 14.0))
    # Referentie wordt 2x zo lang: karaokezin rekt relatief mee.
    start, end = remap_relative(11.0, 12.0, (10.0, 14.0), (10.0, 18.0))
    assert (start, end) == pytest.approx((12.0, 14.0))


def test_interpolate_spans_fills_gaps() -> None:
    from modules.timing import interpolate_spans

    # Regel 1 en 3 gekoppeld; 2 ertussen wordt geïnterpoleerd.
    spans = [(10.0, 12.0), (None, None), (20.0, 22.0)]
    out = interpolate_spans(spans)
    assert out[0] == (10.0, 12.0)
    assert out[2] == (20.0, 22.0)
    assert 12.0 <= out[1][0] < out[1][1] <= 20.0  # netjes in het gat
    # Twee opeenvolgende gaten: gelijkmatig verdeeld.
    spans2 = [(0.0, 2.0), (None, None), (None, None), (12.0, 14.0)]
    out2 = interpolate_spans(spans2)
    assert out2[1][0] == pytest.approx(2.0)
    assert out2[2][1] == pytest.approx(12.0)


def test_interpolate_spans_no_anchor() -> None:
    from modules.timing import interpolate_spans
    assert interpolate_spans([(None, None), (None, None)]) == []


def test_couple_timing_block_level() -> None:
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    # Blok 0 = refrein (1 origineelregel, betrouwbaar), 1 zangregel.
    # Blok 1 = couplet: 1 origineelregel maar 2 karaokeregels -> spreiden.
    karaoke_blocks = [
        [TextLine(0, "G Z R", False, block=0),
         TextLine(1, "Waertje", True, block=0)],
        [TextLine(2, "Van alle kanten", False, block=1),
         TextLine(3, "komt men an", False, block=1)],
    ]
    original_blocks = [
        [(13.0, 15.0, True)],
        [(30.0, 34.0, True)],
    ]
    timed, quality, _ = couple_timing(karaoke_blocks, original_blocks)
    by_index = {t.index: t for t in timed}
    # Refrein 1-op-1 -> hoog, exact op de origineeltijd.
    assert by_index[0].start == pytest.approx(13.0)
    assert by_index[0].end == pytest.approx(15.0)
    assert by_index[0].quality == "high"
    # Crowd 'Waertje' krijgt een eigen kort tijdvak, telt niet mee.
    assert by_index[1].crowd is True
    # Couplet gespreid over 30-34 -> midden.
    assert by_index[2].start == pytest.approx(30.0)
    assert by_index[3].end == pytest.approx(34.0)
    assert by_index[2].quality == "medium"
    assert quality["high"] == 1 and quality["medium"] == 2


def test_couple_timing_interpolated_is_laag() -> None:
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    karaoke_blocks = [[TextLine(0, "G Z R", False, block=0)]]
    original_blocks = [[(13.0, 28.0, False)]]  # geïnterpoleerd refrein
    timed, quality, _ = couple_timing(karaoke_blocks, original_blocks)
    assert timed[0].quality == "low"
    assert quality["low"] == 1


def test_couple_1op1_equal_structure() -> None:
    """Gelijk aantal blokken en regels -> zuivere 1-op-1, alles hoog."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "aa", False, block=0), TextLine(1, "bb", False, block=0)],
          [TextLine(2, "cc", False, block=1)]]
    ob = [[(10.0, 11.0, True), (11.0, 12.0, True)], [(20.0, 21.0, True)]]
    timed, quality, mapping = couple_timing(kb, ob)
    assert quality == {"high": 3, "medium": 0, "low": 0}
    assert mapping == {0: 0, 1: 1, 2: 2}  # 1-op-1 over de platte lijst
    by = {t.index: t for t in timed}
    assert by[1].start == pytest.approx(11.0)
    assert by[2].start == pytest.approx(20.0)


def test_couple_unequal_blocks_fallback() -> None:
    """Ongelijk aantal blokken -> evenredig vangnet, geen crash."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "a", False, block=0)],
          [TextLine(1, "b", False, block=1)],
          [TextLine(2, "c", False, block=2)]]
    ob = [[(0.0, 10.0, True)], [(10.0, 20.0, True)]]  # 2 blokken
    timed, quality, mapping = couple_timing(kb, ob)
    assert len(timed) == 3
    assert set(mapping) == {0, 1, 2}
    assert all(0.0 <= t.start <= t.end for t in timed)


def test_couple_clamps_negative_and_duration() -> None:
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "a", False, block=0), TextLine(1, "b", False, block=0)]]
    ob = [[(0.0, 5.0, True), (5.0, 500.0, True)]]
    # Projectie -10 s zou negatief maken; duur begrenst het einde.
    timed, _, _ = couple_timing(kb, ob, duration=30.0,
                                project=lambda s: s - 10.0)
    assert all(t.start >= 0.0 for t in timed)
    assert all(t.end <= 30.0 for t in timed)


def test_interpolate_leading_not_stretched_to_zero() -> None:
    from modules.timing import interpolate_spans
    # Eén niet-gekoppelde regel vóór het eerste anker (duur ~1s).
    out = interpolate_spans([(None, None), (10.0, 11.0)])
    assert out[0][1] == pytest.approx(10.0)      # eindigt op het anker
    assert out[0][0] == pytest.approx(9.0)       # niet 0, maar ~duur ervoor
    # Afsluitende reeks: vanaf het laatste anker, niet tot het eind.
    out2 = interpolate_spans([(10.0, 12.0), (None, None)])
    assert out2[1][0] == pytest.approx(12.0)
    assert out2[1][1] == pytest.approx(14.0)     # +mediane duur (2s)


def test_couple_over_original_words_preserves_rhythm() -> None:
    """B66: lettergrepen volgen het ritme van de originele woorden i.p.v.
    gelijkmatig; een lang aangehouden woord geeft een langere lettergreep."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "aa bb", False, block=0)]]
    ob = [[(0.0, 3.0, True)]]
    # 'langlang' wordt lang aangehouden (0-2.5), 'kort' kort (2.5-3.0).
    original_words = {0: [("langlang", 0.0, 2.5), ("kort", 2.5, 3.0)]}
    timed, _, _ = couple_timing(kb, ob, original_words=original_words)
    syl = timed[0].syllables
    first = syl[0].end - syl[0].start
    last = syl[-1].end - syl[-1].start
    assert first > last          # niet gelijkmatig (dan zou first == last)
    assert timed[0].start == pytest.approx(0.0, abs=0.05)


def test_couple_chant_snaps_to_beats() -> None:
    """B67: chant-regels (laag vertrouwen) landen op de (onregelmatige)
    beats i.p.v. gelijkmatig."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "G Z R", False, block=0)]]
    ob = [[(0.0, 4.0, False)]]              # onbetrouwbaar -> laag
    beats = [0.0, 0.5, 2.5, 3.0, 4.0]       # bewust onregelmatig
    timed, quality, _ = couple_timing(kb, ob, beats=beats)
    assert quality["low"] == 1
    starts = [s.start for s in timed[0].syllables]
    # De middelste inzet wordt door de beats naar voren getrokken
    # (gelijkmatig zou ~1.33 zijn).
    assert starts[1] == pytest.approx(1.167, abs=0.1)


def test_crowd_section_block_is_coupled() -> None:
    """B75: een blok dat volledig uit crowd bestaat koppelt aan het
    originele blok (echte timing, crowd_section=True), i.p.v. korte slots."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [
        [TextLine(0, "Rood Witte Zangers", False, block=0)],
        [TextLine(1, "La-la 1", True, block=1),
         TextLine(2, "La-la 2", True, block=1)],
    ]
    ob = [[(0.0, 3.0, True)], [(10.0, 14.0, True)]]
    timed, _, mapping = couple_timing(kb, ob)
    by = {t.index: t for t in timed}
    # De crowd-refreinregels koppelen aan het tweede originele blok...
    assert by[1].crowd is True and by[1].crowd_section is True
    assert by[1].start == pytest.approx(10.0)
    assert by[2].end == pytest.approx(14.0)
    # ... en ze staan in de mapping (worden dus echt gekoppeld).
    assert 1 in mapping and 2 in mapping


def test_crowd_interjection_stays_short() -> None:
    """Een crowd-regel in een gemengd blok blijft een korte tussenroep
    (geen crowd_section)."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "G Z R", False, block=0),
           TextLine(1, "Waertje!", True, block=0)]]
    ob = [[(5.0, 7.0, True)]]
    timed, _, _ = couple_timing(kb, ob)
    by = {t.index: t for t in timed}
    assert by[1].crowd is True and by[1].crowd_section is False


def test_timing_save_load_preserves_crowd_section(tmp_path) -> None:
    """B80: crowd_section overleeft opslaan/laden (editor-regressie fix)."""
    from modules.timing import (Syllable, TimedLine, load_timing,
                                save_timing)
    line = TimedLine(0, "La la", True, (Syllable("La", 1.0, 1.5),
                                        Syllable(" la", 1.5, 2.0)),
                     quality="high", crowd_section=True)
    path = tmp_path / "timing.json"
    save_timing((line,), path)
    got = load_timing(path)[0]
    assert got.crowd is True and got.crowd_section is True


def test_couple_even_fallback_without_hints() -> None:
    """Zonder woord-/beat-hints blijft de gelijkmatige verdeling gelden."""
    from modules.karaoke_text import TextLine
    from modules.timing import couple_timing

    kb = [[TextLine(0, "aa bb", False, block=0)]]
    ob = [[(0.0, 4.0, True)]]
    timed, _, _ = couple_timing(kb, ob)
    syl = timed[0].syllables
    assert (syl[0].end - syl[0].start) == pytest.approx(
        syl[-1].end - syl[-1].start, abs=0.01)
