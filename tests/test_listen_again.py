"""Listening again where the first listen heard nothing (v1.0.12).

One of the owner's songs: 31.5 seconds of singing without a pause,
Whisper heard nothing in 25 of them apart from the subtitle it invents when it
thinks nothing is sung, and the chunked run could not help, because the
stretch had no silence to cut in. Three answers, each tested here:

* pieces cut through singing are short (``whisper_chunks.FORCED_S``);
* in step 1.1, the known lyrics are laid on every stretch of singing
  that is still unheard (``pipeline._with_gap_text``);
* after 1.2, "Listen again" in the coupling editor: every problem place
  gets candidates from Whisper and from the aligner, the vocal stem
  judges them, and what the user takes over becomes part of the
  transcription - without touching good couplings or his pins.

Whisper and the aligner are replaced by stand-ins: what is tested is
what the program DOES with their answers.
"""
from __future__ import annotations

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import listen_again as again
from modules import pipeline, song_text, whisper
from modules import whisper_chunks as chunks
from modules.config import default_config
from modules.filesystem import ProjectPaths, ProjectStore, ensure_directories
from modules.whisper import Segment, Word

LYRICS = ("ik zie de zon\n"
          "de fiets staat bij de deur\n"
          "het regent op het plein vandaag\n"
          "wij lopen door de stad\n")

#: What the first listen heard: the first and the last line, and nothing
#: in the eighteen seconds between them.
HEARD = ((("ik", 1.0, 1.3), ("zie", 1.3, 1.6), ("de", 1.6, 1.8),
          ("zon", 1.8, 2.4)),
         (("wij", 20.0, 20.4), ("lopen", 20.4, 21.2), ("door", 21.2, 21.5),
          ("de", 21.5, 21.7), ("stad", 21.7, 22.0)))

#: The missing lines, as a stand-in Whisper hears them on a second try.
MISSING = ("de fiets staat bij de deur het regent op het plein "
           "vandaag").split()

WINDOWS = [(0.8, 22.4)]


def _segment(index, words, origin=""):
    items = tuple(Word(text=t, start=s, end=e, confidence=0.9)
                  for t, s, e in words)
    return Segment(index=index, text=" ".join(w.text for w in items),
                   start=items[0].start, end=items[-1].end, words=items,
                   origin=origin)


def _numbered(segments):
    ordered = sorted(segments, key=lambda seg: float(seg.start))
    return tuple(replace(seg, index=n) for n, seg in enumerate(ordered))


def _spread(words, low, high, confidence):
    step = (high - low) / len(words)
    return tuple(Word(text=w, start=round(low + n * step, 3),
                      end=round(low + (n + 1) * step - 0.05, 3),
                      confidence=confidence)
                 for n, w in enumerate(words))


def _project(tmp_path):
    paths = ProjectPaths(root=tmp_path, song="Song_A")
    ensure_directories(paths)
    config = replace(default_config(), advanced=replace(
        default_config().advanced, vocal_analysis=False,
        forced_alignment=True))
    context = pipeline.AppContext(paths=paths, config=config,
                                  store=ProjectStore(paths.project_file))
    (paths.input_dir / song_text.LYRICS_FILENAME).write_text(
        LYRICS, encoding="utf-8")
    segments = tuple(_segment(i, words) for i, words in enumerate(HEARD))
    cache = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    cache.parent.mkdir(parents=True, exist_ok=True)
    whisper.save_segments(segments, cache)
    context.store.set_step("whisper_original", {"segments": 2})
    return context


@pytest.fixture
def stand_ins(monkeypatch, tmp_path):
    """Whisper, the aligner and the vocal stem, answering on cue."""
    vocals = tmp_path / "vocals.wav"
    vocals.write_bytes(b"")
    heard_calls = []

    def slice_(path, settings, start=0.0, end=None, initial_prompt="",
               language_override=None, cancelled=None):
        heard_calls.append((start, end, initial_prompt,
                            settings.no_speech_threshold))
        return (Segment(index=0, text=" ".join(MISSING), start=4.0,
                        end=18.0, words=_spread(MISSING, 4.0, 18.0, 0.85)),)

    def refine(path, segments, language, device="cpu"):
        out = []
        for seg in segments:
            words = seg.words or _spread(seg.text.split(), seg.start,
                                         seg.end, 0.6)
            out.append(replace(seg, words=words))
        return tuple(out)

    monkeypatch.setattr(pipeline, "ensure_original_vocals", lambda c: vocals)
    monkeypatch.setattr(pipeline, "_original_vocal_windows",
                        lambda c: list(WINDOWS))
    monkeypatch.setattr(pipeline, "_language_for", lambda c, track: "nl")
    monkeypatch.setattr(whisper, "transcribe_slice", slice_)
    monkeypatch.setattr(pipeline.word_alignment, "is_available", lambda: True)
    monkeypatch.setattr(pipeline.word_alignment, "refine", refine)
    from modules import rhythm
    monkeypatch.setattr(rhythm, "is_available", lambda: True)
    monkeypatch.setattr(rhythm, "energy_onsets",
                        lambda path, low, high, expected=None:
                        [low + n * 0.9 for n in range(14)])
    return heard_calls


# --------------------------------------------------------------------------
# 1.1: shorter pieces through singing
# --------------------------------------------------------------------------

def test_singing_without_a_pause_is_cut_short() -> None:
    """The stretch of the report: 144.1-175.6 s without one silence.

    The piece covering it used to be 30.0 s - Whisper's own window, so
    the second try asked the same question as the first.
    """
    windows = ((128.5, 143.5), (144.1, 175.6), (177.3, 192.3))
    cut = chunks.cut_points(windows, total=192.3)
    through = [c for c in cut if c.start < 175.6 and c.end > 144.1]
    # Every piece that covers this singing, not only the first one: after
    # a cut inside it, a silence 30 s ahead may not make the next piece
    # long again.
    assert len(through) >= 3
    assert max(c.duration for c in through) <= chunks.FORCED_S + 1e-6
    covered = sorted((c.start, c.end) for c in cut)
    for (_s1, e1), (s2, _e2) in zip(covered, covered[1:]):
        assert s2 <= e1 + 1e-6, "no singing may fall between two pieces"


def test_a_cut_in_silence_is_as_long_as_before() -> None:
    windows = ((0.0, 10.0), (14.0, 24.0), (28.0, 40.0))
    cut = chunks.cut_points(windows, total=40.0)
    assert cut[0].end == pytest.approx(26.0) and not cut[0].forced


# --------------------------------------------------------------------------
# The pieces that need no model
# --------------------------------------------------------------------------

def test_an_unheard_stretch_is_found_and_small_pauses_are_not() -> None:
    words = [(1.0, 2.4), (2.6, 3.0), (20.0, 22.0)]
    assert again.unheard_stretches([(0.8, 22.4)], words) == [(3.4, 19.6)]
    assert again.unheard_stretches([(0.8, 22.4)],
                                   words + [(10.0, 11.0)],
                                   minimum=9.0) == []


def test_words_that_do_not_fit_their_stretch_are_not_laid_on_it() -> None:
    assert again.plausible(MISSING, 4.0, 18.0)
    assert not again.plausible(MISSING, 4.0, 5.0)         # far too fast
    assert not again.plausible(["ja"], 0.0, 30.0)          # far too slow


def test_an_origin_is_only_written_when_there_is_one() -> None:
    """A transcription without additions keeps its bytes - and so the
    fingerprint that protects a coupling from an empty cache (B549)."""
    plain = _segment(0, HEARD[0])
    assert "origin" not in whisper.segments_to_dicts((plain,))[0]
    marked = _segment(0, HEARD[0], origin=whisper.ORIGIN_ALIGNED)
    data = whisper.segments_to_dicts((marked,))
    assert data[0]["origin"] == whisper.ORIGIN_ALIGNED
    assert whisper.segments_from_dicts(data)[0].origin == \
        whisper.ORIGIN_ALIGNED


def test_the_referee_prefers_what_the_voice_supports() -> None:
    windows = [(4.0, 18.0)]
    onsets = [4.0 + n for n in range(14)]
    good = again.score(again.Candidate("whisper", [
        (w.text, w.start, w.end, 0.85)
        for w in _spread(MISSING, 4.0, 18.0, 0.85)]),
        MISSING, onsets, windows)
    off_singing = again.score(again.Candidate("whisper", [
        (w.text, w.start + 30, w.end + 30, 0.85)
        for w in _spread(MISSING, 4.0, 18.0, 0.85)]),
        MISSING, onsets, windows)
    wrong = again.score(again.Candidate("whisper", [
        ("muziek", 5.0, 6.0, 0.9)]), MISSING, onsets, windows)
    assert good.score > off_singing.score
    assert good.score > wrong.score


def test_a_recited_prompt_is_suspected() -> None:
    """The same words as the hint at a low confidence: probably not
    heard but read back (the prompt echo of B390)."""
    words = [(w.text, w.start, w.end, 0.2)
             for w in _spread(MISSING, 4.0, 18.0, 0.2)]
    judged = again.score(again.Candidate("whisper", words), MISSING,
                         None, [(4.0, 18.0)])
    assert judged.evidence["echo"] is True
    sure = again.score(again.Candidate("whisper", [
        (text, start, end, 0.9) for text, start, end, _c in words]),
        MISSING, None, [(4.0, 18.0)])
    assert sure.evidence["echo"] is False
    # The penalty is what makes the difference, not only the lower
    # confidence: without it the recital would score this much higher.
    plain = 0.45 * judged.evidence["evidence"] + \
        0.30 * judged.evidence["singing"] + 0.25 * judged.evidence["rhythm"]
    assert judged.score == pytest.approx(
        round(plain * (1.0 - again.ECHO_PENALTY), 3))


def test_the_echo_is_measured_on_the_expected_words_not_the_hint() -> None:
    """The hint holds whole lines; the area only the missing words of
    them. An answer that is exactly those words, read back without
    confidence, is the echo - even though it is not the whole hint."""
    part = MISSING[:6]
    words = [(w.text, w.start, w.end, 0.2)
             for w in _spread(part, 4.0, 10.0, 0.2)]
    judged = again.score(again.Candidate("whisper", words), part, None,
                         [(4.0, 10.0)])
    assert judged.evidence["echo"] is True


def test_the_aligner_is_judged_on_its_own_confidence() -> None:
    """Its text IS the expected text; matching it to itself proves
    nothing."""
    low = again.score(again.Candidate("aligned", [
        (w.text, w.start, w.end, 0.1)
        for w in _spread(MISSING, 4.0, 18.0, 0.1)]),
        MISSING, None, [(4.0, 18.0)])
    high = again.score(again.Candidate("aligned", [
        (w.text, w.start, w.end, 0.9)
        for w in _spread(MISSING, 4.0, 18.0, 0.9)]),
        MISSING, None, [(4.0, 18.0)])
    assert high.score > low.score


# --------------------------------------------------------------------------
# 1.1: the known text on the unheard singing
# --------------------------------------------------------------------------

def test_step_1_1_lays_the_missing_lines_on_the_singing(tmp_path,
                                                        stand_ins) -> None:
    context = _project(tmp_path)
    segments = tuple(_segment(i, words) for i, words in enumerate(HEARD))

    out = pipeline._with_gap_text(context, segments, "vocals.wav", "nl")

    aligned = [seg for seg in out if seg.origin == whisper.ORIGIN_ALIGNED]
    assert len(aligned) == 1
    assert aligned[0].text.split() == MISSING
    assert 2.4 < aligned[0].start and aligned[0].end < 20.0
    assert [seg.index for seg in out] == list(range(len(out)))
    heard = [seg for seg in out if not seg.origin]
    assert heard == [replace(seg, index=seg.index) for seg in heard]


def test_step_1_1_does_it_on_a_real_transcription_run(
        tmp_path, stand_ins, monkeypatch) -> None:
    """Through ``detect_track`` itself, so the hook is proven and not
    only the function behind it: the known text goes in before the
    aligner, gets its times from it, and lands in the cache."""
    import wave

    context = _project(tmp_path)
    context = replace(context, config=replace(
        context.config, advanced=replace(
            context.config.advanced, demucs=False,
            chunked_transcription=False, forced_alignment=True)))
    context.store.clear_step("whisper_original")
    tone = context.paths.input_dir / "original.wav"
    with wave.open(str(tone), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x00\x00" * 16000)
    monkeypatch.setattr(pipeline, "prepare_track", lambda ctx, track: tone)
    heard = tuple(_segment(i, words) for i, words in enumerate(HEARD))
    monkeypatch.setattr(pipeline.whisper, "transcribe",
                        lambda *a, **k: heard)

    pipeline.detect_track(context, pipeline.TRACK_ORIGINAL)

    cached = whisper.load_segments(
        pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL))
    aligned = [seg for seg in cached if seg.origin == whisper.ORIGIN_ALIGNED]
    assert len(aligned) == 1 and len(aligned[0].words) == len(MISSING)


def test_step_1_1_leaves_a_transcription_without_holes_alone(
        tmp_path, stand_ins, monkeypatch) -> None:
    context = _project(tmp_path)
    monkeypatch.setattr(pipeline, "_original_vocal_windows",
                        lambda c: [(0.8, 2.6), (19.8, 22.2)])
    segments = tuple(_segment(i, words) for i, words in enumerate(HEARD))
    assert pipeline._with_gap_text(context, segments, "vocals.wav",
                                   "nl") == segments


# --------------------------------------------------------------------------
# After 1.2: Listen again
# --------------------------------------------------------------------------

def test_the_problem_place_is_found_between_the_good_anchors(
        tmp_path, stand_ins) -> None:
    context = _project(tmp_path)
    view = pipeline.word_coupling_view(context)
    lines = {0: "ik zie de zon", 1: "de fiets staat bij de deur",
             2: "het regent op het plein vandaag",
             3: "wij lopen door de stad"}

    areas = again.problem_areas(view, lines, 22.4)

    assert len(areas) == 1
    area = areas[0]
    assert area.expected == MISSING
    assert area.low == pytest.approx(2.4) and area.high == pytest.approx(20.0)
    assert "de fiets staat bij de deur" in area.prompt
    assert area.replaceable == []


def test_listening_again_gives_ranked_candidates(tmp_path,
                                                  stand_ins) -> None:
    context = _project(tmp_path)

    areas = pipeline.listen_again(context)

    assert len(areas) == 1
    kinds = [c["kind"] for c in areas[0]["candidates"]]
    assert set(kinds) == {"whisper", "aligned"}
    scores = [c["score"] for c in areas[0]["candidates"]]
    assert scores == sorted(scores, reverse=True)
    # Whisper was asked about that stretch only, with its lines as the
    # hint, and without the "nothing is sung here" threshold.
    (start, end, prompt, threshold), = stand_ins
    assert start == pytest.approx(2.4 - again.MARGIN_S)
    assert end == pytest.approx(20.0 + again.MARGIN_S)
    assert "het regent op het plein vandaag" in prompt
    assert threshold is None


def test_what_is_taken_over_becomes_part_of_the_transcription(
        tmp_path, stand_ins) -> None:
    context = _project(tmp_path)
    areas = pipeline.listen_again(context)
    best = areas[0]["candidates"][0]

    pipeline.accept_heard_again(context, [{
        "low": areas[0]["low"], "high": areas[0]["high"],
        "kind": best["kind"], "words": best["words"],
        "replaced": areas[0]["replaced"]}])

    segments = pipeline.load_segments(context, pipeline.TRACK_ORIGINAL)
    added = [seg for seg in segments if seg.origin]
    assert len(added) == 1 and added[0].text.split() == MISSING
    view = pipeline.word_coupling_view(context)
    coupled = {w["text"] for w in view["words"] if w["transcript_indices"]}
    assert {"fiets", "regent", "plein"} <= coupled
    assert len(view["origins"]) == len(MISSING)


def test_the_users_pins_stay_on_their_word(tmp_path, stand_ins) -> None:
    """Every word taken over shifts the found words after it. A pin is a
    number in that list, and it has to end up on the same WORD."""
    context = _project(tmp_path)
    view = pipeline.word_coupling_view(context)
    pin_word = next(w for w in view["words"] if w["text"] == "stad")
    found = [i for i, row in enumerate(view["transcript"])
             if row[0] == "stad"]
    pipeline.set_word_pins(context, {pin_word["index"]: found})

    areas = pipeline.listen_again(context)
    best = areas[0]["candidates"][0]
    pipeline.accept_heard_again(context, [{
        "low": areas[0]["low"], "high": areas[0]["high"],
        "kind": best["kind"], "words": best["words"],
        "replaced": areas[0]["replaced"]}])

    after = pipeline.word_coupling_view(context)
    pinned = next(w for w in after["words"] if w["index"] == pin_word["index"])
    assert pinned["pinned"]
    assert pinned["transcript_indices"] != found, \
        "the list did not shift, so this proves nothing"
    assert [after["transcript"][i][0] for i in
            pinned["transcript_indices"]] == ["stad"]


def test_taking_over_keeps_the_couplings_and_drops_what_follows_them(
        tmp_path, stand_ins) -> None:
    context = _project(tmp_path)
    context.store.set_step("word_coupling", {"pins": {}})
    context.store.set_step("coupling", {"lines": 1})
    context.store.set_step("timing", {"file": "x"})

    pipeline.accept_heard_again(context, [{
        "low": 2.4, "high": 20.0, "kind": "whisper",
        "words": [["fiets", 5.0, 5.5, 0.9]], "replaced": []}])

    assert context.store.get_step("word_coupling") is not None
    assert context.store.get_step("coupling") is None
    assert context.store.get_step("timing") is None


def test_doing_it_again_replaces_the_earlier_answer(tmp_path,
                                                    stand_ins) -> None:
    context = _project(tmp_path)
    first = {"low": 2.4, "high": 20.0, "kind": "aligned",
             "words": [["fiets", 5.0, 5.5, 0.4]], "replaced": []}
    second = {"low": 3.0, "high": 19.0, "kind": "whisper",
              "words": [["fiets", 6.0, 6.5, 0.9]], "replaced": []}
    pipeline.accept_heard_again(context, [first])
    pipeline.accept_heard_again(context, [second])
    kept = pipeline.heard_again(context)
    assert len(kept) == 1 and kept[0]["kind"] == "whisper"

    pipeline.clear_heard_again(context)
    assert pipeline.heard_again(context) == []
    segments = pipeline.load_segments(context, pipeline.TRACK_ORIGINAL)
    assert not any(seg.origin for seg in segments)


def test_a_weak_found_word_is_replaced_not_kept_beside_it(
        tmp_path, stand_ins) -> None:
    """Between two good anchors a wrong word is the problem, so taking
    over an answer takes that word out instead of adding beside it."""
    context = _project(tmp_path)
    cache = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    segments = list(whisper.load_segments(cache))
    segments.insert(1, _segment(1, (("muziek", 10.0, 10.8),)))
    whisper.save_segments(_numbered(segments), cache)

    areas = pipeline.listen_again(context)
    assert ["muziek", 10.0, 10.8] in areas[0]["replaced"]
    best = areas[0]["candidates"][0]
    pipeline.accept_heard_again(context, [{
        "low": areas[0]["low"], "high": areas[0]["high"],
        "kind": best["kind"], "words": best["words"],
        "replaced": areas[0]["replaced"]}])
    texts = [w.text for seg in pipeline.load_segments(
        context, pipeline.TRACK_ORIGINAL) for w in seg.words]
    assert "muziek" not in texts


def test_the_step_is_in_the_derivation_chain() -> None:
    """What follows the coupling lapses; the pins themselves do not."""
    from modules import dependencies

    after = set(dependencies.dependents(["heard_again"]))
    assert {"coupling", "timing"} <= after
    assert "word_coupling" not in after
    assert "heard_again" in set(dependencies.dependents(
        ["whisper_original"]))


# --------------------------------------------------------------------------
# The windows
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_the_dialog_takes_over_the_ticked_places(qapp) -> None:
    from modules.coupling_editor import ListenAgainDialog

    areas = [{"low": 2.4, "high": 20.0, "expected": MISSING,
              "replaced": [["muziek", 10.0]],
              "candidates": [
                  {"kind": "whisper", "words": [["fiets", 5.0, 5.5, 0.9]],
                   "score": 0.8, "evidence": {}},
                  {"kind": "aligned", "words": [["fiets", 5.1, 5.6, 0.6]],
                   "score": 0.6, "evidence": {}}]},
             {"low": 30.0, "high": 35.0, "expected": ["ja"],
              "replaced": [], "candidates": []}]
    dialog = ListenAgainDialog(areas, has_earlier=True)
    chosen = dialog.chosen()
    assert len(chosen) == 1
    assert chosen[0]["kind"] == "whisper"
    assert chosen[0]["replaced"] == [["muziek", 10.0]]
    dialog._rows[0][1].setCurrentIndex(1)
    assert dialog.chosen()[0]["kind"] == "aligned"
    dialog._rows[0][0].setChecked(False)
    assert dialog.chosen() == []


def test_the_editor_offers_it_and_closes_to_do_it(qapp) -> None:
    from modules.coupling_editor import CouplingEditorDialog

    dialog = CouplingEditorDialog([("ik", 1.0, 1.3)],
                                  [{"index": 0, "text": "ik", "line": 0,
                                    "transcript_indices": [0],
                                    "found": "ik", "sim": 1.0,
                                    "pinned": False, "status": "coupled"}],
                                  lambda pins: None, can_listen_again=True)
    assert not dialog.listen_again_requested
    dialog._ask_listen_again()
    assert dialog.listen_again_requested


# --------------------------------------------------------------------------
# v1.0.12 review: what the first version got wrong
# --------------------------------------------------------------------------

def _accept_best(context, areas):
    best = areas[0]["candidates"][0]
    return pipeline.accept_heard_again(context, [{
        "low": areas[0]["low"], "high": areas[0]["high"],
        "kind": best["kind"], "words": best["words"],
        "replaced": areas[0]["replaced"]}])


def _flat_starts(segments):
    return [float(w.start) for seg in segments for w in seg.words]


def test_added_words_go_between_the_words_of_a_segment_around_them() -> None:
    """A Whisper segment that spans the hole: its last word is after the
    hole. Sorting whole segments put the added words behind it."""
    around = _segment(0, (("ik", 1.0, 1.3), ("zie", 1.3, 1.6),
                          ("stad", 21.7, 22.0)))
    after = _segment(1, (("ja", 23.0, 23.4),))
    added = _segment(2, (("fiets", 5.0, 5.5), ("deur", 6.0, 6.5)),
                     origin=whisper.ORIGIN_ALIGNED)

    out = pipeline._interleaved([around, after, added])

    starts = _flat_starts(out)
    assert starts == sorted(starts)
    assert [seg.origin for seg in out] == ["", whisper.ORIGIN_ALIGNED, "",
                                           ""]
    assert out[3] == replace(after, index=3), \
        "a segment nothing came into stays what it was"


def test_taking_over_keeps_the_found_words_in_time_order(
        tmp_path, stand_ins) -> None:
    context = _project(tmp_path)
    cache = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    # One segment holding both the first and the last line.
    whisper.save_segments((_segment(0, HEARD[0] + HEARD[1]),), cache)
    areas = pipeline.listen_again(context)

    _accept_best(context, areas)

    segments = pipeline.load_segments(context, pipeline.TRACK_ORIGINAL)
    starts = _flat_starts(segments)
    assert starts == sorted(starts)
    view = pipeline.word_coupling_view(context)
    coupled = {w["text"] for w in view["words"] if w["transcript_indices"]}
    assert {"ik", "fiets", "plein", "lopen", "stad"} <= coupled


def test_a_later_small_area_keeps_the_rest_of_an_earlier_answer(
        tmp_path, stand_ins) -> None:
    context = _project(tmp_path)
    pipeline.accept_heard_again(context, [{
        "low": 2.4, "high": 20.0, "kind": "aligned",
        "words": [["fiets", 5.0, 5.5, 0.4], ["plein", 15.0, 15.5, 0.4]],
        "replaced": []}])
    pipeline.accept_heard_again(context, [{
        "low": 14.0, "high": 16.0, "kind": "whisper",
        "words": [["plein", 14.8, 15.3, 0.9]], "replaced": []}])

    words = sorted((w[0], w[1]) for area in pipeline.heard_again(context)
                   for w in area["words"])
    assert words == [("fiets", 5.0), ("plein", 14.8)]


def test_cutting_after_taking_over_does_not_count_words_twice(
        tmp_path, stand_ins) -> None:
    """The editor saves its whole found list when the user cuts or
    merges; what was heard again is in that list only for showing."""
    context = _project(tmp_path)
    _accept_best(context, pipeline.listen_again(context))
    view = pipeline.word_coupling_view(context)
    before = [row[0] for row in view["transcript"]]

    pipeline.set_transcript_override(context, view["transcript"])

    stored = [row[0] for row in pipeline.transcript_override(context)]
    assert not set(MISSING) - {"de", "het"} & set(stored), \
        "the heard words are kept in their own step, not in the list"
    after = [row[0] for row in
             pipeline.word_coupling_view(context)["transcript"]]
    assert after == before


def test_a_heard_word_the_user_cut_is_not_added_back(tmp_path,
                                                     stand_ins) -> None:
    context = _project(tmp_path)
    _accept_best(context, pipeline.listen_again(context))
    rows = list(pipeline.word_coupling_view(context)["transcript"])
    number = next(i for i, row in enumerate(rows) if row[0] == "vandaag")
    text, start, end = rows[number]
    middle = (start + end) / 2.0
    rows[number:number + 1] = [("van", start, middle), ("daag", middle, end)]

    pipeline.set_transcript_override(context, rows)

    after = [row[0] for row in
             pipeline.word_coupling_view(context)["transcript"]]
    assert "vandaag" not in after
    assert after.count("van") == 1 and after.count("daag") == 1


def test_an_area_chosen_on_an_edited_list_also_names_the_first_words(
        tmp_path, stand_ins) -> None:
    """Chosen while a hand-edited list stood; that list can go again
    later, and then the words of the first listen may not come back."""
    context = _project(tmp_path)
    cache = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    segments = list(whisper.load_segments(cache))
    segments.insert(1, _segment(1, (("muzi", 10.0, 10.8),)))
    whisper.save_segments(_numbered(segments), cache)
    rows = [(w.text, float(w.start), float(w.end))
            for seg in whisper.load_segments(cache) for w in seg.words]
    rows = [("mu", 10.0, 10.4) if r[0] == "muzi" else r for r in rows]
    pipeline.set_transcript_override(context, rows)

    areas = pipeline.listen_again(context)

    assert ["mu", 10.0, 10.4] in areas[0]["replaced"]
    assert ["muzi", 10.0, 10.8] in areas[0]["replaced"]
    _accept_best(context, areas)
    pipeline.set_transcript_override(context, None)
    texts = [w.text for seg in pipeline.load_segments(
        context, pipeline.TRACK_ORIGINAL) for w in seg.words]
    assert "muzi" not in texts


def test_the_aligner_is_started_once_for_all_places(tmp_path, stand_ins,
                                                    monkeypatch) -> None:
    context = _project(tmp_path)
    calls = []
    original = pipeline.word_alignment.refine

    def counting(path, segments, language, device="cpu"):
        calls.append(len(segments))
        return original(path, segments, language, device)

    monkeypatch.setattr(pipeline.word_alignment, "refine", counting)
    monkeypatch.setattr(again, "problem_areas", lambda view, lines, end: [
        again.Area(3.0, 9.0, ["fiets", "staat"], "", []),
        again.Area(11.0, 18.0, ["regent", "plein"], "", [])])

    areas = pipeline.listen_again(context)

    assert calls == [2]
    assert [c["kind"] for a in areas for c in a["candidates"]].count(
        "aligned") == 2


def test_a_candidate_word_on_an_anchor_is_left_out() -> None:
    words = [("zon", 1.9, 2.3, 0.9), ("fiets", 5.0, 5.5, 0.9)]
    assert again.inside(words, 0.0, 10.0, [(1.8, 2.4)]) == [words[1]]


def _view(words, transcript):
    return {"transcript": transcript, "words": words}


def _lw(index, text, line, indices, status="coupled", sim=1.0, **extra):
    return dict({"index": index, "text": text, "line": line,
                 "transcript_indices": indices, "sim": sim,
                 "pinned": False, "status": status}, **extra)


TRANSCRIPT = [("ik", 1.0, 1.3), ("muziek", 5.0, 6.0), ("stad", 20.0, 20.5)]


def test_a_weak_coupling_is_a_problem_and_a_good_one_an_anchor() -> None:
    words = [_lw(0, "ik", 0, [0]), _lw(1, "fiets", 1, [1], sim=0.2),
             _lw(2, "stad", 2, [2])]
    areas = again.problem_areas(_view(words, TRANSCRIPT), {}, 30.0)
    assert [a.expected for a in areas] == [["fiets"]]
    assert areas[0].replaceable == [1]
    words[1]["sim"] = again.WEAK_SIM
    assert again.problem_areas(_view(words, TRANSCRIPT), {}, 30.0) == []


def test_a_pinned_word_is_an_anchor_even_when_it_looks_weak() -> None:
    words = [_lw(0, "ik", 0, [0]), _lw(1, "fiets", 1, [1], sim=0.1,
                                       pinned=True),
             _lw(2, "deur", 1, [], status="no_match"), _lw(3, "stad", 2, [2])]
    areas = again.problem_areas(_view(words, TRANSCRIPT), {}, 30.0)
    assert len(areas) == 1 and areas[0].expected == ["deur"]
    assert areas[0].low == pytest.approx(6.0)
    assert areas[0].replaceable == [] and areas[0].claimed_spans == []


def test_what_the_user_or_the_song_left_loose_is_no_problem() -> None:
    for status in ("manually_uncoupled", "filler_skipped", "background"):
        words = [_lw(0, "ik", 0, [0]), _lw(1, "oh", 1, [], status=status),
                 _lw(2, "stad", 2, [2])]
        assert again.problem_areas(_view(words, TRANSCRIPT), {}, 30.0) == \
            [], status


def test_a_backing_vocal_is_neither_an_anchor_nor_a_problem() -> None:
    """It sounds WITH a line: its time says nothing about the words
    around it, so it may not cut an area in two."""
    words = [_lw(0, "ik", 0, [0]),
             _lw(1, "fiets", 1, [], status="no_match"),
             _lw(2, "oeh", 1, [1], bg=True),
             _lw(3, "deur", 1, [], status="no_match"),
             _lw(4, "stad", 2, [2])]
    areas = again.problem_areas(_view(words, TRANSCRIPT), {}, 30.0)
    assert [a.expected for a in areas] == [["fiets", "deur"]]
    # What it was heard as is no word to replace: no candidate brings a
    # backing vocal back.
    assert areas[0].replaceable == []
    assert areas[0].claimed_spans == [(5.0, 6.0)]
    # Coupled weakly, it is still no problem to hear again.
    words = [_lw(0, "ik", 0, [0]), _lw(1, "oeh", 1, [1], sim=0.2, bg=True),
             _lw(2, "stad", 2, [2])]
    assert again.problem_areas(_view(words, TRANSCRIPT), {}, 30.0) == []


def test_a_found_word_an_anchor_claims_is_never_replaced() -> None:
    """A repeated line: a later lyric word is coupled well to a found
    word inside the span of an earlier problem place."""
    words = [_lw(0, "ik", 0, [0]), _lw(1, "fiets", 1, [], status="no_match"),
             _lw(2, "stad", 2, [2]), _lw(3, "zon", 3, [1])]
    areas = again.problem_areas(_view(words, TRANSCRIPT), {}, 30.0)
    assert len(areas) == 1
    assert areas[0].replaceable == []
    assert areas[0].claimed_spans == [(5.0, 6.0)]


def test_a_word_two_holes_would_claim_goes_to_the_first() -> None:
    lyric = [song_text.LyricWord(text=w, line=0, index=n)
             for n, w in enumerate(("de", "fiets", "staat", "hier"))]
    aligned = [song_text.AlignedWord(lyric=w, start=None, end=None,
                                     matched_text="", sim=0.0)
               for w in lyric]
    out = again.gap_segments([(1.0, 3.0), (4.0, 6.0)], aligned)
    assert len(out) == 1 and out[0].text == "de fiets staat hier"


def test_clearing_lets_what_follows_the_coupling_lapse(tmp_path) -> None:
    context = _project(tmp_path)
    pipeline.accept_heard_again(context, [{
        "low": 2.4, "high": 20.0, "kind": "whisper",
        "words": [["fiets", 5.0, 5.5, 0.9]], "replaced": []}])
    context.store.set_step("coupling", {"lines": 1})
    context.store.set_step("timing", {"file": "x"})

    pipeline.clear_heard_again(context)

    assert context.store.get_step("coupling") is None
    assert context.store.get_step("timing") is None


def test_the_figures_of_the_original_follow_what_was_heard_again() -> None:
    from modules import dependencies

    after = set(dependencies.dependents(["heard_again"]))
    assert "analysis_original" in after
    assert "analysis_karaoke" not in after


# --------------------------------------------------------------------------
# Old projects keep the old way of listening
# --------------------------------------------------------------------------

def test_only_a_new_or_new_style_project_listens_the_new_way() -> None:
    assert pipeline._listens_anew(None)
    assert pipeline._listens_anew({"listening": pipeline.LISTENING})
    assert not pipeline._listens_anew({"segments": 12})


def test_an_old_project_is_cut_as_before() -> None:
    windows = ((0.0, 61.0),)
    old = chunks.cut_points(windows, 61.0, forced_s=chunks.WINDOW_S)
    assert [(c.start, c.end) for c in old] == [(0.0, 30.0), (26.0, 56.0),
                                               (52.0, 61.0)]
    new = chunks.cut_points(windows, 61.0)
    assert max(c.duration for c in new) == pytest.approx(chunks.FORCED_S)


def test_the_new_way_does_not_chop_an_intro_into_short_pieces() -> None:
    cut = chunks.cut_points(((20.0, 40.0), (42.0, 50.0)), 50.0)
    assert cut[0].end == pytest.approx(20.0 - chunks.ONSET_MARGIN_S)
    assert not cut[0].forced
    long_intro = chunks.cut_points(((100.0, 110.0),), 110.0)
    assert long_intro[0].duration == pytest.approx(chunks.WINDOW_S)


def _run_detect(tmp_path, monkeypatch, step, pieces=False):
    import wave

    context = _project(tmp_path)
    context = replace(context, config=replace(
        context.config, advanced=replace(
            context.config.advanced, demucs=False,
            chunked_transcription=pieces, forced_alignment=True)))
    context.store.clear_step("whisper_original")
    if step is not None:
        context.store.set_step("whisper_original", step)
        pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL).unlink()
    tone = context.paths.input_dir / "original.wav"
    with wave.open(str(tone), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x00\x00" * 16000)
    monkeypatch.setattr(pipeline, "prepare_track", lambda ctx, track: tone)
    heard = tuple(_segment(i, words) for i, words in enumerate(HEARD))
    monkeypatch.setattr(pipeline.whisper, "transcribe",
                        lambda *a, **k: heard)
    pipeline.detect_track(context, pipeline.TRACK_ORIGINAL)
    cached = whisper.load_segments(
        pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL))
    return context, cached


def test_a_new_transcription_is_marked_as_the_new_way(
        tmp_path, stand_ins, monkeypatch) -> None:
    context, cached = _run_detect(tmp_path, monkeypatch, None)
    assert context.store.get_step("whisper_original")["listening"] == \
        pipeline.LISTENING
    assert any(seg.origin == whisper.ORIGIN_ALIGNED for seg in cached)


@pytest.mark.parametrize("step, forced", [
    (None, chunks.FORCED_S), ({"segments": 2}, chunks.WINDOW_S)])
def test_the_pieces_are_cut_the_way_the_project_was_made(
        tmp_path, stand_ins, monkeypatch, step, forced) -> None:
    asked = []

    def cut(windows, total, first_sound=0.0, window_s=chunks.WINDOW_S,
            forced_s=chunks.FORCED_S):
        asked.append(forced_s)
        return ()

    monkeypatch.setattr(chunks, "cut_points", cut)
    _run_detect(tmp_path, monkeypatch, step, pieces=True)
    assert asked and set(asked) == {forced}


def test_an_old_project_transcribed_again_gets_no_known_text(
        tmp_path, stand_ins, monkeypatch) -> None:
    """After "Nu legen" it must hear the same words as before, or B549
    no longer recognises the transcription and the coupling lapses."""
    context, cached = _run_detect(tmp_path, monkeypatch, {"segments": 2})
    assert not any(seg.origin for seg in cached)
    assert "listening" not in context.store.get_step("whisper_original")


# --------------------------------------------------------------------------
# The windows, after the review
# --------------------------------------------------------------------------

def test_an_added_word_shows_where_it_came_from(qapp) -> None:
    from modules.coupling_editor import CouplingCanvas

    canvas = CouplingCanvas([("ik", 1.0, 1.3), ("fiets", 5.0, 5.5),
                             ("zon", 7.0, 7.5)],
                            [{"index": 0, "text": "ik", "line": 0,
                              "transcript_indices": [0], "found": "ik",
                              "sim": 1.0, "pinned": False,
                              "status": "coupled"},
                             {"index": 1, "text": "fiets", "line": 0,
                              "transcript_indices": [1], "found": "fiets",
                              "sim": 1.0, "pinned": False,
                              "status": "coupled"}],
                            lambda pins: None,
                            found_status={0: "coupled", 1: "coupled",
                                          2: "no_match"},
                            origins=[(5.0, whisper.ORIGIN_HEARD_AGAIN),
                                     (7.0, whisper.ORIGIN_ALIGNED)])
    assert canvas._found_style(1) == "heard_again"
    assert canvas._found_style(0) in ("", "coupled")
    assert canvas._found_style(2) == "no_match", \
        "a loose word keeps its problem, wherever it came from"


def test_the_dialog_opens_to_clear_when_nothing_new_was_found(qapp) -> None:
    from modules.coupling_editor import ListenAgainDialog

    dialog = ListenAgainDialog([], has_earlier=True)
    assert dialog.chosen() == []
    dialog._clear()
    assert dialog.clear_requested


class _Window:
    """Just enough of the main window for ``_listen_again``."""

    def __init__(self, context, busy=False):
        from modules import gui

        self._context = context
        self._worker = type("W", (), {"isRunning": lambda s: busy})()
        self.task = None
        self.done = None
        self.reopened = 0
        self.logged = []
        self.failed = []
        self._listen_again = gui.MainWindow._listen_again.__get__(self)

    def _run(self, task, on_done, cancel_event=None):
        self.task, self.done, self.cancel = task, on_done, cancel_event

    def _open_word_couple(self):
        self.reopened += 1

    def _log(self, text):
        self.logged.append(text)

    def _on_failed(self, text):
        self.failed.append(text)

    def _choose_heard_again(self, areas):
        self.chosen = areas


def test_stop_during_listening_again_costs_nothing(tmp_path,
                                                   monkeypatch) -> None:
    """The general cancel of a step clears its half-made work - here
    that would have been the couplings and the timing."""
    context = _project(tmp_path)
    context.store.set_step("timing", {"file": "x"})
    monkeypatch.setattr(pipeline, "cleanup_after_cancel",
                        lambda c: pytest.fail("no general cleanup"))

    def stopped(context, progress=None, cancelled=None):
        raise whisper.CancelledError()

    monkeypatch.setattr(pipeline, "listen_again", stopped)
    window = _Window(context)
    window._listen_again()
    result = window.task(lambda *a: None, lambda *a: None)
    window.done(result)

    assert result == {"cancelled": True}
    assert window.reopened == 1
    assert context.store.get_step("timing") is not None


def test_a_failure_while_listening_again_goes_back_to_the_editor(
        tmp_path, monkeypatch) -> None:
    context = _project(tmp_path)

    def broken(context, progress=None, cancelled=None):
        raise pipeline.PipelineError("no vocals")

    monkeypatch.setattr(pipeline, "listen_again", broken)
    window = _Window(context)
    window._listen_again()
    window.done(window.task(lambda *a: None, lambda *a: None))
    assert window.failed == ["no vocals"] and window.reopened == 1


def test_another_busy_task_sends_the_user_back_to_the_editor(
        tmp_path, monkeypatch) -> None:
    from modules import gui

    context = _project(tmp_path)
    monkeypatch.setattr(gui.QMessageBox, "information",
                        lambda *a, **k: None)
    window = _Window(context, busy=True)
    window._listen_again()
    assert window.task is None and window.reopened == 1


def test_without_the_aligner_setting_only_whisper_answers(
        tmp_path, stand_ins) -> None:
    context = _project(tmp_path)
    context = replace(context, config=replace(context.config, advanced=replace(
        context.config.advanced, forced_alignment=False)))
    areas = pipeline.listen_again(context)
    assert [c["kind"] for c in areas[0]["candidates"]] == ["whisper"]


# --------------------------------------------------------------------------
# v1.0.12, second review
# --------------------------------------------------------------------------

def test_what_the_filter_threw_out_in_a_filled_stretch_stays_out(
        tmp_path, stand_ins) -> None:
    """Split up between the known words, "ZANG EN MUZIEK" would be judged
    word by word, and a lone "EN" is no hallucination to the filter."""
    context = _project(tmp_path)
    invented = Segment(index=1, text="ZANG EN MUZIEK", start=5.0, end=16.0,
                       words=(Word("ZANG", 5.0, 5.5, 0.3),
                              Word("EN", 10.0, 10.3, 0.3),
                              Word("MUZIEK", 15.0, 15.8, 0.3)))
    segments = (_segment(0, HEARD[0]), invented, _segment(2, HEARD[1]))
    clean, _aligned = pipeline._clean_segments_and_alignment(
        context, pipeline._effective_lyrics(
            context, context.paths.input_dir / song_text.LYRICS_FILENAME),
        segments)
    assert "EN" not in [w.text for seg in clean for w in seg.words], \
        "the filter does not drop it here, so this proves nothing"

    out = pipeline._with_gap_text(context, segments, "vocals.wav", "nl")

    texts = [w.text for seg in out for w in seg.words]
    assert not {"ZANG", "EN", "MUZIEK"} & set(texts)
    assert any(seg.origin == whisper.ORIGIN_ALIGNED for seg in out)


def test_a_segment_that_starts_before_its_first_word_keeps_its_place(
        ) -> None:
    late = Segment(index=0, text="tien elf", start=9.2, end=11.3,
                   words=(Word("tien", 10.0, 10.3, 0.9),
                          Word("elf", 11.0, 11.3, 0.9)))
    early = _segment(1, (("negen", 9.5, 9.7), ("half", 9.75, 9.9)),
                     origin=whisper.ORIGIN_HEARD_AGAIN)
    out = pipeline._interleaved([late, early])
    assert [w.text for seg in out for w in seg.words] == \
        ["negen", "half", "tien", "elf"]
    assert [seg.index for seg in out] == [0, 1]


def test_clearing_brings_back_what_was_replaced_after_a_cut(
        tmp_path, stand_ins) -> None:
    context = _project(tmp_path)
    cache = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    segments = list(whisper.load_segments(cache))
    segments.insert(1, _segment(1, (("muzi", 10.0, 10.8),)))
    whisper.save_segments(_numbered(segments), cache)
    _accept_best(context, pipeline.listen_again(context))
    rows = list(pipeline.word_coupling_view(context)["transcript"])
    assert "muzi" not in [row[0] for row in rows]
    number = next(i for i, row in enumerate(rows) if row[0] == "stad")
    text, start, end = rows[number]
    rows[number:number + 1] = [("st", start, (start + end) / 2),
                               ("ad", (start + end) / 2, end)]
    pipeline.set_transcript_override(context, rows)
    assert "muzi" not in [row[0] for row in
                          pipeline.word_coupling_view(context)["transcript"]]

    pipeline.clear_heard_again(context)

    after = [row[0] for row in
             pipeline.word_coupling_view(context)["transcript"]]
    assert "muzi" in after, "cleared, the first listen is back"
    assert "st" in after and "ad" in after, "and the cut is kept"
    assert not set(MISSING) - {"de", "het"} & set(after)


def test_an_earlier_area_wholly_inside_a_new_one_still_keeps_out_its_words(
        tmp_path) -> None:
    context = _project(tmp_path)
    pipeline.accept_heard_again(context, [{
        "low": 2.4, "high": 20.0, "kind": "aligned",
        "words": [["fiets", 5.0, 5.5, 0.4]],
        "replaced": [["muziek", 12.0, 12.5]]}])
    pipeline.accept_heard_again(context, [{
        "low": 4.0, "high": 6.0, "kind": "whisper",
        "words": [["fiets", 5.1, 5.6, 0.9]], "replaced": []}])
    assert ("muziek", 12.0) in pipeline._replaced_keys(
        pipeline.heard_again(context))


def test_the_fingerprint_is_of_what_whisper_heard(tmp_path, stand_ins,
                                                  monkeypatch) -> None:
    """The known text depends on the editor's word lists as well; with it
    in the fingerprint, an unchanged transcription would count as new."""
    context, cached = _run_detect(tmp_path, monkeypatch, None)
    assert any(seg.origin for seg in cached)
    heard = tuple(_segment(i, words) for i, words in enumerate(HEARD))
    assert context.store.get_step("whisper_original")["transcript_sha1"] \
        == pipeline.transcript_fingerprint(heard)


def test_the_dialog_says_why_a_candidate_scored_what_it_did(qapp) -> None:
    from PySide6.QtCore import Qt
    from modules.coupling_editor import ListenAgainDialog
    from modules.translations import t

    dialog = ListenAgainDialog([{
        "low": 2.4, "high": 20.0, "expected": MISSING, "replaced": [],
        "candidates": [{"kind": "whisper", "words": [["fiets", 5, 5.5, .2]],
                        "score": 0.3, "evidence": {
                            "evidence": 0.2, "singing": 1.0, "rhythm": 0.5,
                            "echo": True}}]}])
    tip = dialog._rows[0][1].itemData(0, Qt.ToolTipRole)
    assert tip.endswith(t("listen_again_echo")) and "0.20" in tip


def test_places_where_nothing_was_found_are_not_offered(tmp_path,
                                                        monkeypatch) -> None:
    from modules import gui

    context = _project(tmp_path)
    shown = []
    monkeypatch.setattr(gui.QMessageBox, "information",
                        lambda *a, **k: shown.append(a[2]))
    window = _Window(context)
    gui.MainWindow._choose_heard_again(window, [
        {"low": 1.0, "high": 3.0, "expected": ["ja"], "replaced": [],
         "candidates": []}])
    from modules.translations import t
    assert shown == [t("listen_again_nothing")]
