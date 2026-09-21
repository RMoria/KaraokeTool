"""Tests for v0.118.0: B372 through B374.

B372 the tool ``whisper_probe`` fell over immediately: it converted
     ``device: "auto"`` to ``None`` itself instead of using the app's own
     function, and ctranslate2 wants a string there.
B373 on a duplicate at a segment boundary the LYRICS now decide, instead
     of four thresholds.
B374 1.5.8 points out the gaps (cheap), 1.5.11c measures which setting
     closes them (expensive).

The closing word of a Whisper segment has been measured as half as
reliable as any other word: over 347 transitions in fourteen projects it
averages 0.42 against 0.70, and a third of them sit below 0.30. That is
not bad luck but construction - on a window edge the decoder has no
right-hand context - and that is why there is a row of tests around it.
"""
from __future__ import annotations

import inspect
import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import model_register, pipeline, test_history  # noqa: E402
from modules import test_panel  # noqa: E402
from modules.translations import TRANSLATIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setattr(test_history, "HISTORY_FILE",
                        tmp_path / "testhistorie.json")
    monkeypatch.setattr(test_panel, "COMBINATION_REPORT",
                        tmp_path / "modelcombinaties.md")
    yield
    model_register.restore_all()
    model_register.apply_settings({})


def _word(text, start, end, confidence=0.5):
    from modules.whisper import Word
    return Word(text=text, start=start, end=end, confidence=confidence)


def _segment(words):
    from modules.whisper import Segment
    return Segment(index=0, text=" ".join(w.text for w in words),
                   start=words[0].start, end=words[-1].end,
                   words=tuple(words))


def _lyrics(line: str):
    from modules.song_text import LyricWord
    return tuple(LyricWord(text=w, index=n, line=0, bg=False)
                 for n, w in enumerate(line.split()))


# --------------------------------------------------------------------------
# B372 - the tool starts again
# --------------------------------------------------------------------------

def test_the_probe_uses_the_device_choice_of_the_app() -> None:
    """Its own conversion passed ``device=None``; ctranslate2 wants str."""
    source = (ROOT / "tools" / "whisper_probe.py").read_text(encoding="utf-8")
    # B419: the model now comes in through ``whisper._load_model``, and
    # that one makes the device choice itself - still the app's choice,
    # and now with the model cache behind it as well.
    assert "whisper._load_model(settings)" in source
    assert "WhisperModel(settings.model" not in source
    assert "device=None if" not in source


def test_the_device_choice_always_gives_strings() -> None:
    from modules import whisper
    from modules.config import WhisperSettings

    for setting in (WhisperSettings(),
                    replace(WhisperSettings(), device="cpu",
                            compute_type="int8")):
        device, compute = whisper._resolve_device(setting)
        assert isinstance(device, str) and device
        assert isinstance(compute, str) and compute


# --------------------------------------------------------------------------
# B373 - the lyrics decide
# --------------------------------------------------------------------------

def test_a_word_cut_in_two_is_merged() -> None:
    """"so" does not occur twice in the lyrics, so two "so" close
    together are one word cut in half on the window edge."""
    left = _segment([_word("stand", 1.0, 1.4), _word("so", 1.4, 1.46,
                                                     0.36)])
    right = _segment([_word("so", 1.50, 1.74, 0.73),
                      _word("close", 1.8, 2.2)])
    out = pipeline._merge_boundary_duplicates(
        (left, right), lyrics=_lyrics("don't stand so close to me"))
    assert [w.text for s in out for w in s.words] == ["stand", "so", "close"]
    # The word that is left begins where the piece began.
    merged = [w for s in out for w in s.words if w.text == "so"][0]
    assert merged.start == pytest.approx(1.4)


def test_a_real_repeat_stays() -> None:
    """"Sunday, Sunday" DOES occur twice in the lyrics - then two
    "Sunday" side by side are not a fault but the singing."""
    left = _segment([_word("Bloody", 1.0, 1.4), _word("Sunday", 1.4, 1.8)])
    right = _segment([_word("Sunday", 1.9, 2.4), _word("morning", 2.5, 3.0)])
    out = pipeline._merge_boundary_duplicates(
        (left, right), lyrics=_lyrics("sunday sunday bloody sunday"))
    assert [w.text for s in out for w in s.words] == \
        ["Bloody", "Sunday", "Sunday", "morning"]


def test_a_large_gap_is_never_merged() -> None:
    """Even when the word does not occur twice in the lyrics: three
    seconds in between is a repeat, not a word cut in half."""
    left = _segment([_word("een", 1.0, 1.4), _word("so", 1.4, 1.8)])
    right = _segment([_word("so", 4.8, 5.2), _word("twee", 5.3, 5.7)])
    out = pipeline._merge_boundary_duplicates(
        (left, right), lyrics=_lyrics("een so twee so"))
    assert sum(len(s.words) for s in out) == 4


def test_different_words_stay_different() -> None:
    left = _segment([_word("een", 1.0, 1.4), _word("taart", 1.4, 1.6)])
    right = _segment([_word("maar", 1.7, 2.0), _word("twee", 2.1, 2.4)])
    out = pipeline._merge_boundary_duplicates(
        (left, right), lyrics=_lyrics("een taart maar twee"))
    assert sum(len(s.words) for s in out) == 4


def test_without_lyrics_the_old_cautious_check_applies() -> None:
    """The reading path may not fall over on a project without lyrics."""
    left = _segment([_word("stand", 1.0, 1.4), _word("so", 1.4, 1.46,
                                                     0.36)])
    right = _segment([_word("so", 1.50, 1.74, 0.73)])
    out = pipeline._merge_boundary_duplicates((left, right))
    assert sum(len(s.words) for s in out) == 3      # nothing merged


def test_the_doublings_in_the_lyrics_are_recognised() -> None:
    doubled = pipeline._doubled_lyric_keys(
        _lyrics("ooh ooh don't stand so close to me"))
    from modules.cluster import phonetic_key
    assert phonetic_key("ooh") in doubled
    assert phonetic_key("so") not in doubled
    assert phonetic_key("stand") not in doubled


def test_the_reading_path_passes_the_lyrics_along() -> None:
    source = inspect.getsource(pipeline.load_segments)
    assert "lyrics=_lyrics_for_boundaries(context)" in source


def test_missing_lyrics_give_none(tmp_path) -> None:
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    assert pipeline._lyrics_for_boundaries(context) is None


# --------------------------------------------------------------------------
# B374 - point them out cheaply first, then measure them expensively
# --------------------------------------------------------------------------

def test_the_gap_detector_is_no_longer_an_action() -> None:
    """B526: 1.5.8 is gone; its answer stands in the log.

    The action always said the same thing - this project has a gap or it
    does not - and knowing that never changed anything. Only 1.5.11 can
    say what to do about it, and that one measures the gap itself.
    """
    assert not any(a.code == "1.5.8" for a in test_panel.ACTIONS)
    assert not hasattr(test_panel, "transcription_gaps")


def test_the_gap_measurement_itself_starts_no_whisper() -> None:
    """The whole gain: it costs seconds instead of eight transcriptions."""
    source = inspect.getsource(test_panel._gaps_in)
    assert "WhisperModel" not in source and "probe" not in source
    assert "_original_vocal_windows" in source


def test_a_small_gap_does_not_count() -> None:
    """A breath between two lines is not a skipped window."""
    assert test_panel._GAP_MIN_S >= 5.0


def test_the_window_trial_is_gone(qapp=None) -> None:
    """B512: 1.5.11c had been off since v0.144.0 with its answer beside
    it and is now gone. The heavy bin itself stays one action."""
    codes = [p.code for p in test_panel.HEAVY_TRIALS]
    assert "1.5.11c" not in codes
    assert not hasattr(test_panel, "window_trial")
    heavy = [a for a in test_panel.ACTIONS if a.heavy]
    assert [a.code for a in heavy] == ["1.5.11"]


def test_the_gap_detector_texts_were_swept_up_too() -> None:
    """B526: an action that is removed leaves no texts behind."""
    for key in ("test_gaps", "test_gaps_hint", "test_gaps_intro",
                "test_gaps_advice"):
        for language in ("nl", "en"):
            assert key not in TRANSLATIONS[language], f"{key} ({language})"
