"""Tests for v0.104.0: B334 up to and including B338.

B334 - a run of words without duration at the same moment is Whisper's
       repetition loop and goes out.
B335 - a karaoke that was made from the original is named that way too.
B336 - the tail is spread over the vocal windows, on whole phrases.
B337 - the hallucination and filler lists belong to the LANGUAGE, are
       judged at the POSITION in the lyrics, and can be extended by hand
       from the coupling editor.
B338 - the yardstick runs the real pipeline and leaves the user's manual
       corrections out of the input.
"""
from __future__ import annotations

import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import phonetics  # noqa: E402
from modules import pipeline  # noqa: E402
from modules import timing as T  # noqa: E402
from modules.whisper import Segment, Word  # noqa: E402


# --------------------------------------------------------------------------
# B334: the repetition loop
# --------------------------------------------------------------------------

def _segment(*words: tuple[str, float, float]) -> Segment:
    ws = tuple(Word(t, s, e, 0.9) for t, s, e in words)
    return Segment(0, " ".join(w[0] for w in words),
                   ws[0].start, ws[-1].end, ws)


def test_a_loop_of_four_goes_out() -> None:
    """The measured case: 34x "now," all at exactly 193.500 s, with a
    confidence of 0.98 - invisible to any check on content, but a word
    without duration can never yield a timing."""
    seg = _segment(("echt", 10.0, 10.5), *[("now", 11.0, 11.0)] * 6)
    out = pipeline._drop_repetition_loop((seg,))
    assert [w.text for w in out[0].words] == ["echt"]


def test_a_short_run_stays() -> None:
    """Eight of the eleven projects have no word without duration at
    all, two have one, and one has a run of three. The threshold sits
    above that, because removing that trio made that song measurably
    (if slightly) worse."""
    seg = _segment(("a", 1.0, 1.4), *[("oe", 2.0, 2.0)] * 3, ("b", 3.0, 3.4))
    out = pipeline._drop_repetition_loop((seg,))
    assert len(out[0].words) == 5


def test_without_a_loop_nothing_changes() -> None:
    seg = _segment(("een", 1.0, 1.4), ("twee", 1.4, 1.9), ("drie", 1.9, 2.5))
    assert pipeline._drop_repetition_loop((seg,)) == (seg,)


def test_stray_zero_length_words_elsewhere_do_not_count() -> None:
    """Only a run at the SAME moment is the loop; stray zero-length
    words scattered through the song are something else."""
    seg = _segment(("a", 1.0, 1.0), ("b", 2.0, 2.0), ("c", 3.0, 3.0),
                   ("d", 4.0, 4.0))
    assert len(pipeline._drop_repetition_loop((seg,))[0].words) == 4


def test_a_segment_that_is_all_loop_disappears() -> None:
    seg = _segment(*[("now", 5.0, 5.0)] * 8)
    assert pipeline._drop_repetition_loop((seg,)) == ()


# --------------------------------------------------------------------------
# B336: the tail over the vocal windows
# --------------------------------------------------------------------------

def test_only_whole_phrases_get_lines() -> None:
    """The measured case: 14.56 s = 3.90 phrases -> 4 lines, 29.88 s =
    8.01 -> 8 lines, while a blip of 0.88 s and a held note of 4.78 s
    get none."""
    windows = [(133.07, 147.63), (160.43, 161.31), (172.06, 176.84),
               (177.75, 207.63)]
    out = T.tail_over_windows(12, windows, 3.73, 131.98)
    assert out is not None and len(out) == 12
    assert math.isclose(out[0], 133.07, abs_tol=0.01)
    assert math.isclose(out[4], 177.75, abs_tol=0.01)


def test_a_count_that_does_not_add_up_does_nothing() -> None:
    """Rather nothing than a confident mistake: if the windows do not
    explain the tail exactly, the caller keeps its own distribution."""
    windows = [(133.07, 147.63), (177.75, 207.63)]
    assert T.tail_over_windows(11, windows, 3.73, 131.98) is None


def test_a_held_note_of_one_and_a_half_phrases_carries_nothing() -> None:
    assert T.tail_over_windows(1, [(10.0, 14.78)], 3.73, 0.0) is None


def test_a_window_before_the_anchor_does_not_count() -> None:
    """A window that still belongs to the coupled part is cut off at the
    last anchor."""
    assert T.tail_over_windows(4, [(100.0, 132.12), (133.07, 147.63)],
                               3.73, 131.98) is not None


def test_without_windows_or_period_there_is_no_verdict() -> None:
    assert T.tail_over_windows(4, [], 3.73, 0.0) is None
    assert T.tail_over_windows(4, [(0.0, 15.0)], 0.0, 0.0) is None


# --------------------------------------------------------------------------
# B337: the lists belong to the language
# --------------------------------------------------------------------------

@pytest.mark.parametrize("code", sorted(phonetics.LANGUAGES))
@pytest.mark.parametrize("kind", phonetics.WORD_LISTS)
def test_every_built_in_language_has_both_lists(code: str,
                                                kind: str) -> None:
    """The guard the user asked for: no language can arrive without
    someone taking a decision about its artefacts. Empty is allowed,
    missing is not."""
    assert kind in phonetics.LANGUAGES[code], f"{code} is missing {kind}"


def test_an_unknown_language_starts_empty() -> None:
    """A Danish song makes its own da.json with empty lists; nothing
    from the shipped set ends up in it."""
    seed = phonetics.generate_language("da")
    assert seed["hallucinations"] == []
    assert seed["fillers"] == []


def test_the_list_is_shipped_plus_collected() -> None:
    """Deliberately a union and not "the first one wins" as with the
    phonetics: otherwise a collected en.json for a built-in language is
    silently ignored and marking a word does nothing at all."""
    try:
        assert phonetics.add_word("en", "hallucinations", "bye") is True
        words = phonetics.word_list("en", "hallucinations")
        assert "bye" in words and "thank" in words
        assert phonetics.add_word("en", "hallucinations", "bye") is False
    finally:
        phonetics.remove_word("en", "hallucinations", "bye")
    assert "bye" not in phonetics.word_list("en", "hallucinations")


def test_a_shipped_word_cannot_be_erased_by_hand() -> None:
    assert phonetics.remove_word("en", "hallucinations", "thank") is False
    assert "thank" in phonetics.word_list("en", "hallucinations")


def test_the_language_file_carries_the_lists() -> None:
    payload = phonetics.language_payload("en", "0.104.0")
    assert "hallucinations" in payload and "fillers" in payload
    assert "thank" in payload["hallucinations"]


def test_the_english_fillers_cover_thank_you() -> None:
    """"Thank you." can only be filtered once "you" stops counting as a
    content word. The filler list solves that - safer than putting "you"
    on the hallucination list, because that word is all over England."""
    assert "you" in phonetics.word_list("en", "fillers")
    assert "you" not in phonetics.word_list("en", "hallucinations")


def test_the_pipeline_falls_back_to_the_base_list() -> None:
    """Without language data the old, small set is what is left."""
    assert "zang" in pipeline._language_words("xx", "hallucinations")
    assert pipeline._language_words("xx", "fillers")


# --------------------------------------------------------------------------
# B337: marking from the coupling editor
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_only_a_judgement_can_be_marked() -> None:
    """Of the five markings three are a measurement - "Whisper heard
    nothing here", "timed on the vocal stem", "no match". Being able to
    set those by hand would state something that is not true."""
    from modules.coupling_editor import MARKABLE, _STATUS_STYLE

    assert set(MARKABLE) == {"hallucination_filtered", "filler_skipped"}
    assert set(MARKABLE) < set(_STATUS_STYLE)


def test_the_legend_turns_clickable_only_when_allowed() -> None:
    from modules.coupling_editor import legend_html

    assert legend_html(clickable=True).count("<a href=") == 2
    assert legend_html().count("<a href=") == 0


def test_marking_picks_the_right_row(qapp) -> None:
    """A hallucination is about what Whisper found (top row), a filler
    about the lyrics (bottom row)."""
    from modules.coupling_editor import CouplingEditorDialog

    transcript = [("Thank", 1.0, 1.5), ("you", 1.5, 2.0)]
    words = [{"index": i, "text": f"L{i}", "transcript_indices": [],
              "pinned": False, "sim": 0.0, "line": 0} for i in range(2)]
    seen: list[tuple[str, str]] = []
    dialog = CouplingEditorDialog(
        transcript, words, lambda pins: None,
        on_mark=lambda kind, word: (seen.append((kind, word)) or True))

    dialog._canvas._sel_top = 0
    dialog._mark_selected("hallucination_filtered")
    assert seen == [("hallucinations", "Thank")]
    assert 0 in dialog._canvas._filtered

    dialog._canvas._sel_top = None
    dialog._canvas._sel_bot = 1
    dialog._mark_selected("filler_skipped")
    assert seen[-1] == ("fillers", "L1")
    assert words[1]["status"] == "filler_skipped"


def test_clicking_again_removes_the_marking(qapp) -> None:
    from modules.coupling_editor import CouplingEditorDialog

    dialog = CouplingEditorDialog(
        [("Thank", 1.0, 1.5)], [], lambda pins: None,
        on_mark=lambda kind, word: True)
    dialog._canvas._sel_top = 0
    dialog._mark_selected("hallucination_filtered")
    dialog._mark_selected("hallucination_filtered")
    assert not dialog._canvas._filtered


def test_a_measurement_cannot_be_set_by_hand(qapp) -> None:
    from modules.coupling_editor import CouplingEditorDialog

    seen = []
    dialog = CouplingEditorDialog(
        [("iets", 1.0, 1.5)], [], lambda pins: None,
        on_mark=lambda kind, word: (seen.append(kind) or True))
    dialog._canvas._sel_top = 0
    for status in ("transcription_gap", "energy_placed", "no_match"):
        dialog._mark_selected(status)
    assert seen == []


# --------------------------------------------------------------------------
# B335: the label on a karaoke made from the original
# --------------------------------------------------------------------------

def test_the_label_exists_in_both_languages() -> None:
    from modules.translations import TRANSLATIONS

    for language in ("nl", "en"):
        assert TRANSLATIONS[language]["karaoke_from_original_label"].strip()


def test_from_the_original_beats_the_file_name(qapp, tmp_path) -> None:
    """The flag hangs on input:karaoke in the derivation chain, so the
    moment a real karaoke is chosen after all, the name comes back of
    its own accord."""
    from modules import gui
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)
    from modules.translations import t

    paths = ProjectPaths(root=tmp_path, song="Label")
    ensure_directories(paths)
    (paths.input_dir / "karaoke.wav").write_bytes(b"x")
    store = ProjectStore(paths.project_file)
    store.set_meta("karaoke_from_original", True)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=store)
    window = gui.MainWindow(context)
    window._refresh_inputs()
    assert window._input_labels[pipeline.TRACK_KARAOKE].text() == \
        t("karaoke_from_original_label")

    # A genuinely chosen file wins again.
    pipeline.set_input_origin(context, pipeline.TRACK_KARAOKE,
                              tmp_path / "mijn karaoke.wav")
    window._refresh_inputs()
    assert window._input_labels[pipeline.TRACK_KARAOKE].text() == \
        "mijn karaoke.wav"


# --------------------------------------------------------------------------
# B338: the yardstick measures the tool, not the handwork
# --------------------------------------------------------------------------

def test_the_yardstick_leaves_out_the_manual_steps() -> None:
    """The stored coupling holds the user's corrections on the original
    track - in one project 58 of the 64 sentences. Measuring against
    that is marking your own homework."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "tools" / \
        "timing_regression.py"
    spec = importlib.util.spec_from_file_location("timing_regression", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for step in ("original_overrides", "word_coupling", "lyrics_override",
                 "coupling"):
        assert step in module.MANUAL_STEPS
