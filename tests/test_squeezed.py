"""A squeezed line is not a measurement (v1.0.13, B578-B581).

On one of the owner's songs "Listen again" laid four long "jalala"s in
the first second of a seventeen-second stretch of singing, at an aligner
score of nearly zero - and it was offered, ticked, and taken over. The
area as a whole passed the pace check; the LINE did not, and nothing
looked at the line. Invented lyrics throughout.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from modules import listen_again as again
from modules import model_register, pipeline, timing, timing_template
from modules.song_text import AlignedWord, LyricWord

JALA = "jalalajalala"          # six syllables


def _words(texts, start, step):
    return [(text, round(start + n * step, 3),
             round(start + (n + 1) * step - 0.01, 3), 0.1)
            for n, text in enumerate(texts)]


def test_a_line_sung_faster_than_anyone_can_is_squeezed() -> None:
    squeezed = _words([JALA, JALA], 1.0, 0.3)      # 12 syllables in 0.6 s
    fine = _words([JALA, JALA], 1.0, 3.0)          # 12 in 6 s
    assert again.squeezed(squeezed, [0, 0]) == [0]
    assert again.squeezed(fine, [0, 0]) == []


def test_candidate_words_get_the_line_they_belong_to() -> None:
    expected = ["de", "fiets", "staat", "het", "regent"]
    lines = [1, 1, 1, 2, 2]
    words = _words(["de", "fiets", "staat", "het", "regent"], 0, 1)
    assert again.lines_of(words, expected, lines) == lines
    heard = _words(["fiets", "staat", "hmm", "regent"], 0, 1)
    assert again.lines_of(heard, expected, lines) == [1, 1, 1, 2]


def test_a_whole_line_is_held_against_the_same_line_elsewhere() -> None:
    templates, pace = again.line_templates([
        ("de fiets staat", [("de", 10.0, 10.5), ("fiets", 10.5, 11.5),
                            ("staat", 11.5, 13.0)]),
        ("de fiets staat", [("de", 40.0, 40.5), ("fiets", 40.5, 41.5),
                            ("staat", 41.5, 43.0)])])
    key = timing_template.line_key("de fiets staat")
    assert templates[key].duration == pytest.approx(3.0)
    assert templates[key].starts == pytest.approx((0.0, 0.5 / 3, 1.5 / 3))
    texts = {1: "de fiets staat"}
    short = _words(["de", "fiets", "staat"], 70.0, 0.4)     # 1.2 s
    right = _words(["de", "fiets", "staat"], 70.0, 1.0)     # 3.0 s
    assert again.unlike_elsewhere(short, [1, 1, 1], texts, templates,
                                  pace) == [1]
    assert again.unlike_elsewhere(right, [1, 1, 1], texts, templates,
                                  pace) == []
    # Half a line cannot be held against the whole one; there only the
    # song's pace counts, as a floor.
    half = _words(["fiets", "staat"], 70.0, 0.5)
    assert again.unlike_elsewhere(half, [1, 1], texts, templates,
                                  pace) == []
    rushed = _words(["fiets", "staat"], 70.0, 0.05)
    assert again.unlike_elsewhere(rushed, [1, 1], texts, templates,
                                  pace) == [1]


def test_the_song_pace_is_only_a_floor() -> None:
    line = [("ik", 0.0, 0.5), ("zie", 0.5, 1.0), ("de", 1.0, 1.5),
            ("zon", 1.5, 2.0)]
    _templates, pace = again.line_templates([("ik zie de zon", line)])
    assert pace == pytest.approx(0.5)
    # Slower than the pace is never "unlike": a held note is allowed.
    slow = _words(["wij", "lopen"], 0, 5.0)
    assert again.unlike_elsewhere(slow, [3, 3], {3: "wij lopen door"},
                                  {}, pace) == []


def test_coverage_says_how_much_of_the_singing_the_words_take() -> None:
    windows = [(0.0, 10.0)]
    assert again.coverage(_words(["a"] * 10, 0.0, 1.0), 0.0, 10.0,
                          windows) == pytest.approx(1.0)
    little = again.coverage(_words(["a", "b"], 0.0, 0.5), 0.0, 10.0,
                            windows)
    assert little < 0.25
    assert again.coverage([], 20.0, 30.0, windows) is None


def test_coverage_weighs_in_the_referee() -> None:
    area = again.Area(0.0, 18.0, [JALA] * 5, "", [], [],
                      [0, 0, 1, 1, 2])
    windows = [(1.0, 7.0), (8.0, 11.0), (12.0, 18.0)]
    squeezed = again.score(again.Candidate(
        "aligned", _words([JALA] * 5, 1.0, 0.6)), [JALA] * 5, None,
        windows, area=area)
    spread = again.score(again.Candidate(
        "aligned", _words([JALA] * 5, 1.0, 3.4)), [JALA] * 5, None,
        windows, area=area)
    assert spread.evidence["coverage"] > squeezed.evidence["coverage"]
    assert spread.score > squeezed.score


def _intro_area():
    return again.Area(0.0, 22.4, [JALA, JALA, JALA, JALA, "jalalalalalala"],
                      "", [], [], [0, 0, 1, 1, 2])


def test_the_candidate_on_the_singing_puts_a_line_in_every_window() -> None:
    windows = [(1.0, 7.0), (8.0, 11.0), (12.0, 18.0)]
    found = again.on_singing(_intro_area(), windows, None, {}, {})
    assert found.kind == "singing"
    words = found.words
    assert len(words) == 5
    assert 1.0 <= words[0][1] and words[1][2] <= 7.0 + 1e-6
    assert 8.0 <= words[2][1] and words[3][2] <= 11.0 + 1e-6
    assert 12.0 <= words[4][1] and words[4][2] <= 18.0 + 1e-6
    # Nothing else to go by: spread by syllables, and it says so.
    assert words[0][3] == again.ON_SINGING_CONFIDENCE["even"]
    assert again.squeezed(words, [0, 0, 1, 1, 2]) == []


def test_on_the_singing_the_onsets_come_before_an_even_spread() -> None:
    windows = [(1.0, 7.0), (8.0, 11.0), (12.0, 18.0)]
    onsets = [1.2, 4.1, 8.3, 9.8, 12.5]
    found = again.on_singing(_intro_area(), windows, onsets, {}, {})
    assert [w[1] for w in found.words] == pytest.approx(
        [1.2, 4.1, 8.3, 9.8, 12.5])
    assert found.words[0][3] == again.ON_SINGING_CONFIDENCE["onsets"]


def test_on_the_singing_a_line_heard_elsewhere_gives_its_profile() -> None:
    area = again.Area(20.0, 30.0, ["de", "fiets", "staat"], "", [], [],
                      [1, 1, 1])
    templates, _pace = again.line_templates([
        ("de fiets staat", [("de", 10.0, 10.5), ("fiets", 10.5, 11.5),
                            ("staat", 11.5, 13.0)])])
    found = again.on_singing(area, [(21.0, 29.0)], None,
                             {1: "de fiets staat"}, templates)
    assert [w[1] for w in found.words] == pytest.approx([21.0, 21.5, 22.5])
    assert found.words[-1][2] == pytest.approx(24.0)
    assert found.words[0][3] == again.ON_SINGING_CONFIDENCE["profile"]


def test_fewer_windows_than_lines_are_split_by_syllables() -> None:
    slots = again._slots_for(3, [(0.0, 12.0)], [2, 2, 8])
    assert slots == [pytest.approx((0.0, 2.0)), pytest.approx((2.0, 4.0)),
                     pytest.approx((4.0, 12.0))]
    two = again._slots_for(3, [(0.0, 4.0), (5.0, 13.0)], [1, 1, 1])
    assert len(two) == 3 and two[0] == pytest.approx((0.0, 4.0))


# --------------------------------------------------------------------------
# B581: laid on is no measure
# --------------------------------------------------------------------------

def _timed(index, text, start, span, made=False, quality="high"):
    pieces = text.split()
    step = span / len(pieces)
    return timing.TimedLine(index=index, text=text, crowd=False,
                            quality=quality, made=made, syllables=tuple(
                                timing.Syllable(("" if n == 0 else " ") + p,
                                                start + n * step,
                                                start + (n + 1) * step)
                                for n, p in enumerate(pieces)))


def test_a_laid_on_line_does_not_set_the_usual_length() -> None:
    heard = [_timed(n, "ja la ja", 10.0 * n, 4.0 + 0.1 * n)
             for n in range(3)]
    made = [_timed(3 + n, "ja la ja", 40.0 + 10 * n, 0.5, made=True)
            for n in range(3)]
    reference = timing.reference_durations(heard + made)
    assert reference["ja la ja"][0] == pytest.approx(4.1)
    # The same lines, not marked: the squeezed ones pull the measure down
    # (and make it too erratic to be one at all).
    unmarked = timing.reference_durations(
        heard + [replace(line, made=False) for line in made])
    assert unmarked.get("ja la ja", (0.0,))[0] != pytest.approx(4.1)


def test_a_laid_on_line_is_no_template() -> None:
    lines = [_timed(n, "ja la ja", 10.0 * n, 4.0, made=(n == 2))
             for n in range(3)]
    windows = [(0.0, 100.0)]
    found = timing_template.collect(lines, windows)
    assert list(found.values())[0].instances == 2


def test_lines_with_words_taken_over_are_marked_made(tmp_path) -> None:
    from tests.test_listen_again import HEARD, _project, _segment

    context = _project(tmp_path)
    pipeline.accept_heard_again(context, [{
        "low": 2.4, "high": 20.0, "kind": "aligned",
        "words": [["de", 4.0, 4.4, 0.9], ["fiets", 4.4, 5.0, 0.9],
                  ["staat", 5.0, 5.6, 0.9], ["bij", 5.6, 6.0, 0.9],
                  ["de", 6.0, 6.3, 0.9], ["deur", 6.3, 7.0, 0.9]],
        "replaced": []}])
    detailed = pipeline._original_lines_detailed(context)
    made = {line["line_no"]: line["made"] for line in detailed}
    assert made[1] is True
    assert made[0] is False and made[3] is False
    assert HEARD and _segment


# --------------------------------------------------------------------------
# Switched off, each goes back to what v1.0.12 did
# --------------------------------------------------------------------------

@pytest.fixture
def switched():
    def switch(*codes):
        model_register.apply_settings({code: False for code in codes})
        model_register.apply_disabled()
    yield switch
    model_register.apply_settings({})
    model_register.apply_disabled()
    model_register.restore_all()


def test_each_new_idea_can_be_switched_off(switched) -> None:
    squeezed = _words([JALA, JALA], 1.0, 0.3)
    switched("B578", "B579", "B580", "B581")
    assert again.squeezed(squeezed, [0, 0]) == []
    assert again.coverage(squeezed, 0.0, 10.0, [(0.0, 10.0)]) is None
    assert again.unlike_elsewhere(squeezed, [0, 0], {}, {}, 1.0) == []
    assert again.on_singing(_intro_area(), [(1.0, 7.0)], None, {}, {}) \
        is None
    assert pipeline._made_starts(()) == frozenset()


def test_the_referee_is_the_old_one_with_coverage_off(switched) -> None:
    area = _intro_area()
    words = _words([JALA] * 5, 1.0, 3.4)
    switched("B578")
    judged = again.score(again.Candidate("aligned", list(words)),
                         [JALA] * 5, None, [(1.0, 18.0)], area=area)
    assert "coverage" not in judged.evidence


def _aligned(line, text, start=None, end=None, bg=False, estimated=False):
    return AlignedWord(lyric=LyricWord(index=0, text=text, line=line,
                                       bg=bg),
                       start=start, end=end, matched_text=text, sim=1.0,
                       estimated=estimated)


def test_only_a_fully_heard_line_is_a_measure_in_step_1_1() -> None:
    lines = again.heard_lines_of_alignment([
        _aligned(0, "ik", 1.0, 1.3), _aligned(0, "zie", 1.3, 1.6),
        _aligned(1, "de", 5.0, 5.2), _aligned(1, "fiets"),
        _aligned(2, "het", 9.0, 9.2, estimated=True),
        _aligned(3, "oeh", bg=True), _aligned(3, "wij", 12.0, 12.4)])
    assert [text for text, _w in lines] == ["ik zie", "wij"]


def test_only_a_well_coupled_line_is_a_measure_after_1_2() -> None:
    transcript = [("ik", 1.0, 1.3), ("zie", 1.3, 1.6), ("fiets", 5.0, 5.5),
                  ("staat", 5.5, 6.0), ("wij", 9.0, 9.4), ("gaan", 9.4, 9.9)]

    def word(index, text, line, rows, sim=1.0, **extra):
        return dict({"index": index, "text": text, "line": line,
                     "transcript_indices": rows, "sim": sim,
                     "status": "coupled"}, **extra)

    view = {"transcript": transcript, "words": [
        word(0, "ik", 0, [0]), word(1, "zie", 0, [1]),
        word(2, "fiets", 1, [2]), word(3, "staat", 1, [3], sim=0.2),
        word(4, "wij", 2, [4]), word(5, "gaan", 2, [5])]}
    lines = again.heard_lines_of_view(view, [9.4])
    assert [text for text, _w in lines] == ["ik zie"]
    assert lines[0][1] == [("ik", 1.0, 1.3), ("zie", 1.3, 1.6)]


# --------------------------------------------------------------------------
# After the review
# --------------------------------------------------------------------------

def test_one_short_word_of_a_line_is_no_measure_of_its_pace() -> None:
    word = [("ik", 5.0, 5.08, 0.9)]
    assert again.squeezed(word, [0]) == []
    assert again.unlike_elsewhere(word, [0], {0: "ik zie de zon"}, {},
                                  0.3) == []


def test_the_candidate_on_the_singing_does_not_score_itself_up() -> None:
    area = _intro_area()
    windows = [(1.0, 7.0), (8.0, 11.0), (12.0, 18.0)]
    found = again.on_singing(area, windows, None, {}, {})
    judged = again.score(found, area.expected, None, windows, area=area)
    assert judged.evidence["singing"] == 0.5
    assert judged.evidence["coverage"] == 0.5
    assert judged.score < 0.5, "an even spread is below the threshold"


def test_onsets_never_put_a_word_before_the_one_ahead_of_it(
        monkeypatch) -> None:
    # One syllable per letter, so the even spread is easy to see: the
    # words should begin at 0.0, 0.5 and 0.6 of the window.
    monkeypatch.setattr(again, "syllables",
                        lambda words: sum(len(w) for w in words))
    area = again.Area(0.0, 1.0, ["aaaaa", "a", "aaaa"], "", [], [],
                      [0, 0, 0])
    found = again.on_singing(area, [(0.0, 1.0)], [0.0, 0.05, 0.9], {}, {})
    starts = [w[1] for w in found.words]
    # The second word takes the onset at 0.9; the third, with no onset
    # left after it, may not fall back to 0.6 - before the second.
    assert starts[1] == pytest.approx(0.9)
    assert starts == sorted(starts)


def test_a_blip_of_singing_carries_no_line() -> None:
    area = again.Area(9.0, 20.0, ["ja", "la", "hey", "ho"], "", [], [],
                      [0, 0, 1, 1])
    found = again.on_singing(area, [(10.0, 10.08), (11.0, 19.5)], None,
                             {}, {})
    assert all(w[1] >= 11.0 for w in found.words)
    assert again.squeezed(found.words, [0, 0, 1, 1]) == []


def test_what_is_laid_on_the_singing_is_marked_laid_on() -> None:
    from modules import whisper

    assert pipeline._origin_of("singing") == whisper.ORIGIN_ALIGNED
    assert pipeline._origin_of("whisper") == whisper.ORIGIN_HEARD_AGAIN


def test_a_cluster_of_onsets_at_the_end_gives_no_overlapping_words() -> None:
    area = again.Area(0.0, 1.0, ["la", "la", "la", "la"], "", [], [],
                      [0, 0, 0, 0])
    found = again.on_singing(area, [(0.0, 1.0)], [0.90, 0.92, 0.94, 0.96],
                             {}, {})
    words = found.words
    assert all(w[1] < w[2] for w in words)
    assert all(a[2] <= b[1] for a, b in zip(words, words[1:]))
    assert len({w[1] for w in words}) == 4
