"""Tests for v0.108.0 and v0.109.0: B349, B350, B351 and B352.

B349 - the progress showed the percentage twice: once in the bar itself
       and once in the text beside it.
B350 - a report when something is heard with high confidence that is not
       in the lyrics, telling a missing repetition apart from unknown
       text.
B351 - a line that starts after a pause starts too late: the anchor
       comes out of the alignment, and that puts the start of the word
       after the singing comes in.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline  # noqa: E402
from modules.timing import (  # noqa: E402
    Syllable, TimedLine, _onset_before_start, snap_to_onsets,
)
from modules.translations import TRANSLATIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _line(index: int, start: float, end: float,
          quality: str = "high") -> TimedLine:
    return TimedLine(index=index, text=f"regel {index}", crowd=False,
                     syllables=(Syllable(text="la", start=start, end=end),),
                     quality=quality)


# --------------------------------------------------------------------------
# B349: the percentage was there twice
# --------------------------------------------------------------------------

def test_the_progress_text_no_longer_holds_a_percentage() -> None:
    """The bar already shows '20%' itself; the text beside it keeps the
    seconds."""
    for language in ("nl", "en"):
        text = TRANSLATIONS[language]["progress_pct"]
        assert "%" not in text, f"{language} shows the percentage twice"
        assert "{done" in text and "{total" in text


def test_the_progress_text_tolerates_the_old_call() -> None:
    """``pct`` is still passed in; an unused key is allowed."""
    text = TRANSLATIONS["nl"]["progress_pct"].format(
        pct=20, done=12.0, total=60.0)
    assert text == "Voortgang: 12 / 60 s"


# --------------------------------------------------------------------------
# B351: the start after a pause
# --------------------------------------------------------------------------

def test_an_anchor_after_a_pause_moves_to_the_onset() -> None:
    """Measured case: start at 151.46 while the singing comes in at
    150.98."""
    line = _line(1, 151.46, 154.0)
    onset = _onset_before_start(line, previous_end=149.0,
                                ordered=[145.0, 150.98, 151.60])
    assert onset == pytest.approx(150.98)


def test_without_a_pause_the_anchor_stays_put() -> None:
    """Lines that follow straight on are right as they are - there is
    nothing to be won there."""
    line = _line(1, 151.46, 154.0)
    assert _onset_before_start(line, previous_end=151.20,
                               ordered=[150.98, 151.60]) is None


def test_a_small_difference_is_left_alone() -> None:
    """Lines the user left as they were sit 0.10-0.23 s behind their
    onset; that threshold leaves them in peace."""
    line = _line(1, 151.46, 154.0)
    assert _onset_before_start(line, previous_end=149.0,
                               ordered=[151.30]) is None


def test_never_further_back_than_the_previous_line() -> None:
    line = _line(1, 151.46, 154.0)
    assert _onset_before_start(line, previous_end=151.0,
                               ordered=[150.50]) is None


def test_snap_moves_a_measured_line_that_follows_a_pause() -> None:
    """The whole path: B330 leaves measured lines alone, B351 makes one
    exception to that."""
    lines = (_line(0, 140.0, 149.0), _line(1, 151.46, 154.0))
    out = snap_to_onsets(lines, [150.98], period=None)
    assert out[0].start == pytest.approx(140.0)      # untouched
    assert out[1].start == pytest.approx(150.98)
    assert out[1].end == pytest.approx(154.0)        # the end stays put


def test_snap_leaves_an_adjoining_measured_line_alone() -> None:
    lines = (_line(0, 140.0, 151.20), _line(1, 151.46, 154.0))
    out = snap_to_onsets(lines, [150.98], period=None)
    assert out[1].start == pytest.approx(151.46)


# --------------------------------------------------------------------------
# B350: a report on what was heard but is not in the lyrics
# --------------------------------------------------------------------------

def _project(tmp_path: Path, lyrics: str, karaoke_text: str,
             segments: list[dict]):
    import json

    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    (paths.input_dir / "songtekst.txt").write_text(lyrics,
                                                   encoding="utf-8")
    (paths.input_dir / "karaoketekst.txt").write_text(karaoke_text,
                                                      encoding="utf-8")
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    cache = pipeline.transcript_cache(context, pipeline.TRACK_ORIGINAL)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(segments), encoding="utf-8")
    context.store.set_step("whisper_original", {"segments": len(segments)})
    return context


def _segment(index: int, words: list[tuple[str, float, float, float]]
             ) -> dict:
    return {"index": index, "text": " ".join(w[0] for w in words),
            "start": words[0][1], "end": words[-1][2],
            "words": [{"text": t, "start": s, "end": e, "confidence": c}
                      for t, s, e, c in words]}


def test_a_missing_repetition_is_reported(tmp_path) -> None:
    """The measured case: the singing does the pair twice, the text
    once."""
    context = _project(
        tmp_path,
        "shalalie shalala\nja ik weet het alweer\n",
        "biertje hier\nen morgen nog een keer\n",
        [_segment(0, [("shalalie", 10.0, 10.7, 0.7),
                      ("shalala", 10.7, 11.4, 0.7),
                      ("shalalie", 11.4, 12.1, 0.7),
                      ("shalala", 12.1, 12.9, 0.7),
                      ("ja", 13.0, 13.2, 0.9),
                      ("ik", 13.2, 13.4, 0.9),
                      ("weet", 13.4, 13.7, 0.9),
                      ("het", 13.7, 13.9, 0.9),
                      ("alweer", 13.9, 14.4, 0.9)])])
    reported = pipeline.missing_repetitions(context)
    assert [m["repetition"] for m in reported] == [True]
    assert reported[0]["text"].lower().startswith("shalalie")
    assert reported[0]["similarity"] >= 0.9


def test_text_that_matches_gives_no_report(tmp_path) -> None:
    context = _project(
        tmp_path,
        "shalalie shalala shalalie shalala\nja ik weet het alweer\n",
        "Lied C\nen morgen nog een keer\n",
        [_segment(0, [("shalalie", 10.0, 10.7, 0.7),
                      ("shalala", 10.7, 11.4, 0.7),
                      ("shalalie", 11.4, 12.1, 0.7),
                      ("shalala", 12.1, 12.9, 0.7),
                      ("ja", 13.0, 13.2, 0.9),
                      ("ik", 13.2, 13.4, 0.9),
                      ("weet", 13.4, 13.7, 0.9),
                      ("het", 13.7, 13.9, 0.9),
                      ("alweer", 13.9, 14.4, 0.9)])])
    assert [m for m in pipeline.missing_repetitions(context)
            if m["repetition"]] == []


def test_an_uncertain_word_gives_no_report(tmp_path) -> None:
    """Below the threshold it is the mumbling at the end of a line."""
    context = _project(
        tmp_path,
        "shalalie shalala\nja ik weet het alweer\n",
        "biertje hier\nen morgen nog een keer\n",
        [_segment(0, [("shalalie", 10.0, 10.7, 0.7),
                      ("shalala", 10.7, 11.4, 0.7),
                      ("shalalie", 11.4, 12.1, 0.900),
                      ("shalala", 12.1, 12.9, 0.05),
                      ("ja", 13.0, 13.2, 0.9),
                      ("ik", 13.2, 13.4, 0.9),
                      ("weet", 13.4, 13.7, 0.9),
                      ("het", 13.7, 13.9, 0.9),
                      ("alweer", 13.9, 14.4, 0.9)])])
    reported = pipeline.missing_repetitions(context)
    assert all(m["similarity"] >= 0.9 or not m["repetition"]
               for m in reported)


def test_the_report_comes_after_the_coupling_editor(tmp_path) -> None:
    """The check runs after 1.2, because that is where the coupling is
    made."""
    source = (ROOT / "modules" / "gui.py").read_text(encoding="utf-8")
    head = source[source.index("def _open_word_couple("):]
    body = head[:head.index("\n    def _report_missing(")]
    assert "_report_missing" in body
    assert "missing_repetitions" in source


# --------------------------------------------------------------------------
# B352: the yardstick did not pass on the vocal windows
# --------------------------------------------------------------------------

def test_the_yardstick_passes_on_the_vocal_windows() -> None:
    """The app does, so everything that leans on them was never
    measured."""
    source = (ROOT / "tools" / "timing_regression.py").read_text(
        encoding="utf-8")
    call = source[source.index("sanitize_timing("):]
    call = call[:call.index(")\n")]
    assert "active_windows" in call
    app = (ROOT / "modules" / "pipeline.py").read_text(encoding="utf-8")
    assert "active_windows=_vocal_windows(context)" in app
