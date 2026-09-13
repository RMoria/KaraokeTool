"""Tests for v0.148.0.

B518 there is only one reading path for the transcription, B519/B520/B521
the coupling editor keeps its judgement after an edit, B522 an over-long
line keeps its measured start, B523 a line is not spread across a block
boundary into the instrumental.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline
from modules import timing
from modules.timing import TimedLine
from modules.whisper import Segment, Word

ROOT = Path(__file__).resolve().parents[1]

#: Where the raw transcription file may be read outside
#: :func:`pipeline.load_segments` (B518), as ``module: function``.
#:
#: ``detect_track`` hands back the cached run itself (that IS the
#: transcription, not a numbering of it) and the filter row of test 1.5.3
#: measures on purpose what the reading path removes - it cannot use the
#: cleaned list, because the difference is what it reports.
RAW_READERS = {
    "pipeline": {"load_segments", "detect_track"},
    "test_panel": {"_filter_rows > per_project"},
}


def _raw_readers() -> dict[str, set[str]]:
    """Which functions read the raw transcription file themselves.

    The whole path to the function, not just its own name: three
    different functions in ``test_panel`` have a nested ``per_project``
    and only one of them may do this. A bare
    ``from .whisper import load_segments`` counts too - the guard would
    be trivial to walk around otherwise.
    """
    found: dict[str, set[str]] = {}
    for path in sorted((ROOT / "modules").glob("*.py")) + \
            sorted((ROOT / "tools").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        stack: list[str] = []
        bare = set()

        class Walk(ast.NodeVisitor):
            def visit_ImportFrom(self, node):      # noqa: N802
                if (node.module or "").endswith("whisper"):
                    for alias in node.names:
                        if alias.name == "load_segments":
                            bare.add(alias.asname or alias.name)
                self.generic_visit(node)

            def visit_FunctionDef(self, node):     # noqa: N802
                stack.append(node.name)
                self.generic_visit(node)
                stack.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, node):            # noqa: N802
                func = node.func
                attribute = (isinstance(func, ast.Attribute)
                             and func.attr == "load_segments"
                             and isinstance(func.value, ast.Name)
                             and func.value.id in ("whisper",
                                                   "whisper_module"))
                plain = isinstance(func, ast.Name) and func.id in bare
                if (attribute or plain) and stack:
                    found.setdefault(path.stem, set()).add(" > ".join(stack))
                self.generic_visit(node)

        Walk().visit(tree)
    return found


def test_alleen_de_leespad_leest_het_ruwe_bestand():
    """B518: numbering on the raw file cost 82 correct couplings."""
    assert _raw_readers() == RAW_READERS


def test_leespad_haalt_woorden_weg():
    """B518: the file on disk really does hold more words than the app."""
    def word(text: str, start: float, end: float, conf: float = 0.9) -> Word:
        return Word(text=text, start=start, end=end, confidence=conf)

    segments = (
        Segment(index=0, text="een twee", start=0.0, end=1.4,
                words=(word("een", 0.0, 0.4), word("twee", 1.3, 1.4, 0.2))),
        Segment(index=1, text="twee drie", start=1.4, end=2.4,
                words=(word("twee", 1.4, 1.8), word("drie", 2.0, 2.4))))
    cleaned = pipeline._merge_boundary_duplicates(segments)
    assert sum(len(s.words) for s in cleaned) == 3
    assert sum(len(s.words) for s in segments) == 4


def _line(index: int, text: str, start: float, end: float,
          block: int = 0, quality: str = "high") -> TimedLine:
    """A line whose syllables are spread evenly over its span."""
    words = text.split()
    step = (end - start) / len(words)
    return TimedLine(
        index=index, text=text, crowd=False, block=block,
        quality=quality,
        syllables=tuple(
            timing.Syllable(("" if i == 0 else " ") + word,
                            start + i * step, start + (i + 1) * step)
            for i, word in enumerate(words)))


def test_blokken_per_regel_negeren_overgeslagen_bg_regel():
    """B375/B523: a skipped [bg] line is not a block boundary."""
    assert pipeline._line_blocks([0, 1, 2], frozenset()) == [0, 0, 0]
    assert pipeline._line_blocks([0, 1, 3], frozenset()) == [0, 0, 1]
    assert pipeline._line_blocks([0, 1, 3], frozenset({2})) == [0, 0, 0]


def test_blokgrens_ligt_bij_de_langste_stilte():
    """B523: the instrumental between two blocks is the longest silence.

    Both edges come back: where the singing before it stops and where
    the singing after it starts. The instrumental in between belongs to
    neither block.
    """
    active = [(60.0, 62.0), (66.0, 68.4), (74.0, 83.3), (84.0, 86.0)]
    assert pipeline._block_gap(active, 65.4, 83.3) == (68.4, 74.0)


def test_blokgrens_zonder_lange_stilte_is_geen_grens():
    """B523: continuous singing has nothing to clip."""
    active = [(66.0, 68.4), (68.8, 70.0)]
    assert pipeline._block_gap(active, 65.4, 70.0) is None
    assert pipeline._block_gap(active, 65.4, 68.0) is None


def test_regelreeks_wordt_op_de_blokgrens_geknipt():
    """B523: the line of the block before stays before the instrumental."""
    active = [(66.0, 68.4), (74.0, 83.3)]
    parts = pipeline._filler_parts(3, 4, 65.4, 83.3, [0, 0, 0, 0, 1],
                                   active, 5)
    assert parts == [(3, 1, 65.4, 68.4)]


def test_reeks_over_de_grens_krijgt_aan_elke_kant_zijn_eigen_ruimte():
    """B523: two lines, one from each block, each in its own part."""
    active = [(66.0, 68.4), (74.0, 83.3)]
    parts = pipeline._filler_parts(2, 4, 65.4, 84.0, [0, 0, 0, 1, 1],
                                   active, 5)
    # The far side starts where its own block starts singing (74.0), not
    # where the block before it stopped - the instrumental is nobody's.
    assert parts == [(2, 1, 65.4, 68.4), (3, 1, 74.0, 84.0)]


def test_zonder_blokgrens_verandert_er_niets():
    """B523: within one block the whole window stays available."""
    active = [(66.0, 68.4), (74.0, 83.3)]
    whole = [(3, 1, 65.4, 83.3)]
    assert pipeline._filler_parts(3, 4, 65.4, 83.3, [0] * 5, active, 5) \
        == whole
    assert pipeline._filler_parts(3, 4, 65.4, 83.3, None, active, 5) == whole


def test_reeks_aan_het_eind_wordt_niet_geknipt():
    """B523: without a line after it there is no boundary to speak of."""
    active = [(66.0, 68.4), (74.0, 83.3)]
    assert pipeline._filler_parts(3, 5, 65.4, 83.3, [0, 0, 0, 1, 1],
                                  active, 5) == [(3, 2, 65.4, 83.3)]


def test_vastgehouden_noot_stopt_op_de_blokgrens():
    """B523: a held note may not run on over the instrumental."""
    active = [(66.0, 68.4), (74.0, 83.3)]
    blocks = [0, 0, 1]
    # Line 1 is the last of its block; its ceiling is line 2 at 83.3 s.
    assert pipeline._held_ceiling(active, blocks, 1, 67.6, 83.3, 3) == 68.4
    # Within one block nothing changes.
    assert pipeline._held_ceiling(active, [0, 0, 0], 1, 67.6, 83.3, 3) == 83.3
    # And without a block boundary in the singing there is nothing to clip.
    assert pipeline._held_ceiling([(66.0, 68.4)], blocks, 1, 67.6, 83.3, 3) \
        == 83.3
    # The last line of the song has no line after it.
    assert pipeline._held_ceiling(active, blocks, 2, 84.0, 87.0, 3) == 87.0


def test_te_lange_regel_houdt_zijn_gemeten_start():
    """B522: an over-long line is not re-interpolated but capped."""
    lines = tuple([
        _line(0, "een twee drie vier", 10.0, 12.0, block=0),
        _line(1, "vijf zes zeven acht", 14.0, 16.0, block=0),
        _line(2, "negen tien elf twaalf", 18.0, 35.0, block=0),
        _line(3, "dertien veertien vijftien", 36.0, 38.0, block=1),
    ])
    suspect, overlong = timing.implausible_and_overlong(lines, 4.0, {})
    assert 2 in overlong and 2 in suspect
    out = timing.sanitize_timing(lines)
    assert abs(out[2].start - 18.0) < 0.5
    assert out[2].end < 35.0


# --------------------------------------------------------------------------
# B519/B520/B521 - the coupling editor keeps its judgement after an edit
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_knippen_laat_de_koppeling_zichtbaar(qapp) -> None:
    """B519: a cut used to wipe found/sim/status of every lyrics word."""
    from modules.coupling_editor import CouplingCanvas
    transcript = [("OEREND", 0.0, 2.0), ("HARD", 2.0, 3.0)]
    words = [{"index": 0, "text": "oerend", "line": 0,
              "transcript_indices": [1], "found": "HARD", "sim": 0.5,
              "pinned": True}]
    canvas = CouplingCanvas(transcript, words, lambda p: None,
                            on_transcript=lambda tr: None)
    canvas._sel_top = 0
    assert canvas.cut_selected() is True
    entry = canvas._words[0]
    assert entry["transcript_indices"] == [2]
    assert entry["found"] == "HARD"          # was None up to v0.147.0
    assert entry["sim"] > 0.0                # was 0.0, and 0.0 draws red
    assert entry["status"] == "coupled"      # was missing altogether


def test_niet_gekoppeld_woord_houdt_zijn_reden(qapp) -> None:
    """B519: an uncoupled word says WHY it is uncoupled."""
    from modules.coupling_editor import CouplingCanvas
    transcript = [("OEREND", 0.0, 2.0)]
    words = [{"index": 0, "text": "oerend", "line": 0,
              "transcript_indices": [], "found": None, "sim": 0.0,
              "pinned": True},
             {"index": 1, "text": "hard", "line": 0,
              "transcript_indices": [], "found": None, "sim": 0.0,
              "pinned": False}]
    canvas = CouplingCanvas(transcript, words, lambda p: None)
    assert canvas._word_entry(0, "oerend", 0)["status"] == "manually_uncoupled"
    assert canvas._word_entry(1, "hard", 0)["status"] == "no_match"


def test_gevonden_baan_wordt_in_zijn_geheel_herzien():
    """B520: the run rule needs the whole lane, not one word."""
    count = 2 + pipeline.SUSPECT_RUN
    status = pipeline.found_word_status(count, {0, 1}, filtered=(),
                                        in_lyrics=())
    assert status[0] == "coupled"
    assert status[2] == "suspect_run"
    # Coupling ONE word of that run breaks it up, and then no word of it
    # is suspect any more - which is why the whole lane is redone.
    after = pipeline.found_word_status(count, {0, 1, 2}, filtered=(),
                                       in_lyrics=())
    assert "suspect_run" not in set(after.values())


def test_herhaling_uit_de_songtekst_is_geen_verdachte_reeks():
    """B521: a chorus Whisper heard twice is not a hallucination."""
    run = tuple(range(2, 2 + pipeline.SUSPECT_RUN))
    count = 2 + pipeline.SUSPECT_RUN
    plain = pipeline.found_word_status(count, {0, 1}, filtered=(),
                                       in_lyrics=())
    assert plain[run[0]] == "suspect_run"
    known = pipeline.found_word_status(count, {0, 1}, filtered=(),
                                       in_lyrics=run)
    assert all(known[index] == "repeat_missing" for index in run)


class _Lyric:
    """The little bit of a lyrics word that the comparison uses."""

    def __init__(self, text: str) -> None:
        self.text = text


def test_woorden_uit_de_songtekst_worden_fonetisch_herkend():
    """B521: 'doe' in the lyrics recognises 'DOE' among the found words."""
    transcript = [("DOE", 0.0, 0.4), ("MAAR", 0.4, 0.8), ("IETS", 0.8, 1.2)]
    lyrics = [_Lyric("Doe"), _Lyric("maar")]
    assert pipeline.words_in_the_lyrics(transcript, lyrics) \
        == frozenset({0, 1})


# --------------------------------------------------------------------------
# B524 - every test action leaves its lines in a file
# --------------------------------------------------------------------------

def test_testverslag_beschrijft_precies_een_draai(monkeypatch) -> None:
    """B524: a new run STARTS the report, it does not add to it.

    Steered onto one file on purpose, so that this test still catches a
    regression to ``append=True``. That every run gets a file of its own
    (B534) is tested in test_v0149.
    """
    from modules import test_panel
    # Allebei de draaien in HETZELFDE bestand, zodat deze toets nog
    # steeds betrapt dat een draai er niet bij mag schrijven maar
    # opnieuw moet beginnen (B534 gaf ze anders elk hun eigen naam).
    monkeypatch.setattr(test_panel, "_free_path", lambda path: path)
    monkeypatch.setattr(
        test_panel, "report_name",
        lambda codes, version="", scope="", moment=None: "eenzelfde.md")
    test_panel.start_trial_report(["1.5.3"], "alle projecten", "0.148.0")
    eerste = test_panel.TRIAL_REPORT
    test_panel.add_trial_result("1.5.3", "Tekstrijen", "regel een\nregel twee",
                                12.5, 11.0)
    tekst = eerste.read_text(encoding="utf-8")
    assert "1.5.3" in tekst and "regel twee" in tekst and "0.148.0" in tekst
    test_panel.start_trial_report(["1.5.7"], "alle projecten", "0.148.0")
    assert test_panel.TRIAL_REPORT == eerste       # zelfde bestand
    tweede = eerste.read_text(encoding="utf-8")
    assert "regel twee" not in tweede and "1.5.7" in tweede


def test_testverslag_neemt_de_alarmen_mee() -> None:
    """B524: an alarm belongs in the report, not only in the window."""
    from modules import test_panel
    test_panel.start_trial_report(["1.5.9"], "alle projecten")
    test_panel.add_trial_result("1.5.9", "Proef", "uitkomst", 1.0, 1.0,
                                ["let op: iets klopt niet"])
    tekst = test_panel.TRIAL_REPORT.read_text(encoding="utf-8")
    assert "let op: iets klopt niet" in tekst


def test_testverslag_valt_niet_over_een_onschrijfbare_map(tmp_path,
                                                          monkeypatch) -> None:
    """B524: a test may never fall over its own report."""
    from modules import test_panel
    (tmp_path / "bestand").write_text("geen map", encoding="utf-8")
    monkeypatch.setattr(test_panel, "REPORT_DIR", tmp_path / "bestand")
    test_panel.start_trial_report(["1.5.1"], "alle projecten")
    test_panel.add_trial_result("1.5.1", "Vullen", "tekst", 1.0, 1.0)


# --------------------------------------------------------------------------
# B525/B526/B527 - the test panel says less, and what it says is measured
# --------------------------------------------------------------------------

def _word(text: str, start: float, end: float, conf: float = 0.9) -> dict:
    return {"text": text, "start": start, "end": end, "probability": conf}


def test_de_grensovergang_is_uit_de_toetsen(tmp_path) -> None:
    """B525: it compared the parody's words with the original's
    measured boundaries, and reported 44 to 76 per cent on every
    project - a number that is always high measures nothing."""
    from modules import timing_checks
    assert not hasattr(timing_checks, "boundary_check")
    assert not hasattr(timing_checks, "measured_word_boundaries")
    assert "boundary_crossings" not in timing_checks.Findings().as_dict()


def test_de_overgebleven_tellers_staan_er_nog(tmp_path) -> None:
    """B525: pruning is not the same as throwing away."""
    from modules import timing_checks
    keys = timing_checks.Findings().as_dict()
    for name in ("out_of_order", "overlapping", "in_silence", "odd_duration",
                 "empty_lines", "overlapping_lines", "repeat_divergence"):
        assert name in keys, name


def test_afstand_tot_regelbegin_is_de_mediaan(qapp) -> None:
    """B527: one wholly missed line may not decide the table."""
    from modules import test_panel
    spans = [(10.0, 12.0), (20.0, 22.0), (30.0, 32.0)]
    exact = [_word("a", 10.0, 10.4), _word("b", 20.0, 20.4),
             _word("c", 30.0, 30.4)]
    assert test_panel.line_start_distance(exact, spans) == 0.0
    late = [_word("a", 10.2, 10.6), _word("b", 20.1, 20.5),
            _word("c", 45.0, 45.4)]
    assert test_panel.line_start_distance(late, spans) == 0.2


def test_de_tabel_staat_op_afstand_gesorteerd(qapp) -> None:
    """B527: closest to the hand work stands at the top."""
    from modules import test_panel
    windows = [(0.0, 40.0)]
    spans = [(10.0, 12.0), (20.0, 22.0)]
    good = [_word("a", 10.0, 11.0), _word("b", 20.0, 21.0)]
    bad = [_word("a", 14.0, 15.0), _word("b", 25.0, 26.0)]
    lines = test_panel.search_table([("slecht", bad), ("goed", good)],
                                    windows, (), spans)
    body = [line for line in lines if line.startswith("| ")
            and not line.startswith("| draai") and "---" not in line]
    assert body[0].startswith("| goed |")
    assert any("goed" in line for line in lines if "Dichtst" in line
               or "Closest" in line)


def test_zonder_handwerk_zegt_de_tabel_het_erbij(qapp) -> None:
    """B527: no reference, no claim about the hand work."""
    from modules import test_panel
    lines = test_panel.search_table([("een", [_word("a", 1.0, 2.0)])],
                                    [(0.0, 10.0)], (), None)
    head = next(line for line in lines if line.startswith("| draai"))
    assert "regelbegin" not in head


# --------------------------------------------------------------------------
# B528 - wat de kritische herlezing vóór de oplevering nog vond
# --------------------------------------------------------------------------

def test_een_knip_verplaatst_ook_het_filter(qapp) -> None:
    """B528: `_filtered` and `_in_lyrics` are transcript indexes too.

    They stayed behind at a cut, so everything after the cut pointed one
    place too far left: the wrong word was drawn struck through and the
    run rule of B520/B521 judged the wrong words. Exactly the mistake
    B519 repairs on the other lane.
    """
    from modules.coupling_editor import CouplingCanvas
    transcript = [("AA", 0.0, 1.0), ("BB", 1.0, 2.0), ("CC", 2.0, 3.0)]
    words = [{"index": 0, "text": "cc", "line": 0,
              "transcript_indices": [2], "found": "CC", "sim": 0.9,
              "pinned": True}]
    canvas = CouplingCanvas(transcript, words, lambda p: None,
                            on_transcript=lambda tr: None,
                            filtered=[2], in_lyrics=[2])
    canvas._sel_top = 0
    assert canvas.cut_selected() is True          # AA -> A + A
    assert canvas._targets[0] == [3]
    assert canvas._filtered == {3}
    assert canvas._in_lyrics == {3}


def test_een_handmatige_markering_overleeft_een_knip(qapp) -> None:
    """B528: a marking that lives only in the view is gone after a remap."""
    from modules.coupling_editor import CouplingCanvas
    transcript = [("AA", 0.0, 1.0)]
    words = [{"index": 0, "text": "oh", "line": 0,
              "transcript_indices": [], "found": None, "sim": 0.0,
              "pinned": False}]
    canvas = CouplingCanvas(transcript, words, lambda p: None,
                            on_transcript=lambda tr: None)
    canvas._sel_bot = 0
    canvas.mark_selected("filler_skipped")
    assert canvas._words[0]["status"] == "filler_skipped"
    canvas._sel_top = 0
    assert canvas.cut_selected() is True
    assert canvas._words[0]["status"] == "filler_skipped"


def test_een_lege_draai_wint_de_tabel_niet(qapp) -> None:
    """B528: 0.00 s is the score of a perfect run, not of an empty one."""
    from modules import test_panel
    spans = [(10.0, 12.0), (20.0, 22.0)]
    assert test_panel.line_start_distance([], spans) == float("inf")
    rows = [("leeg", []), ("echt", [{"text": "a", "start": 10.1,
                                     "end": 11.0}])]
    lines = test_panel.search_table(rows, [(0.0, 30.0)], (), spans)
    body = [line for line in lines if line.startswith("| ")
            and "---" not in line]
    assert body[1].startswith("| echt |")
    best = [line for line in lines if "Dichtst" in line or "Closest" in line]
    assert best and "echt" in best[0]


def test_de_ankertoets_zit_op_de_functie_die_echt_gedraaid_wordt() -> None:
    """B528: the switch sat on a wrapper nobody called any more, so the
    matrix reported 0.00 s for this model - a measuring error, not a
    measurement."""
    from modules import model_register
    from modules import timing as timing_module

    model = next(m for m in model_register.register()
                 if m.code == "B329/332/340")
    assert [(attr) for _mod, attr, _repl in model.targets] \
        == ["implausible_and_overlong"]
    assert not hasattr(timing_module, "implausible_anchors")


def test_een_scheefgekoppeld_anker_geldt_niet_als_alleen_te_lang(
        monkeypatch) -> None:
    """B528: a packed anchor stands in the wrong PLACE.

    B522 lets a suspect anchor keep its measured start when it is only
    too long. An anchor that is suspect because the coupling put the
    same line down several times over must not slip through that door:
    its start is precisely what is wrong.

    B535 moved the source of that judgement to ``_packed_runs``: the
    run without its first member, because that first start is the one
    that may still be believed. So the test steers the runs.
    """
    lines = tuple([
        _line(0, "een twee drie", 10.0, 13.4, block=0),
        _line(1, "een twee drie", 14.0, 30.0, block=0),
        _line(2, "een twee drie", 31.0, 34.4, block=0),
    ])
    monkeypatch.setattr(timing, "_packed_runs",
                        lambda *args, **kwargs: [[0, 1, 2]])
    suspect, overlong = timing.implausible_and_overlong(lines, 3.4, {})
    assert 1 in suspect                    # too long AND in the wrong place
    assert 1 not in overlong               # so it does not keep its start

    monkeypatch.setattr(timing, "_packed_runs",
                        lambda *args, **kwargs: [])
    suspect, overlong = timing.implausible_and_overlong(lines, 3.4, {})
    assert 1 in suspect and 1 in overlong   # only too long: start is kept
