"""Tests for the v0.87.0 fixes (B266 bilingual video-ready prompt, B267
an "Open folder" button beside video-ready, B268 the 3-2-1 countdown as an
overlay during an instrumental gap instead of hiding the lines)."""
from __future__ import annotations

from pathlib import Path

import numpy as np


# --------------------------------------------------------------------------
# B266 - the Dutch "video ready" question accidentally showed both the
# Dutch and the English text ("Meteen openen? / Open now?"). Now only the
# active language.
# --------------------------------------------------------------------------
def test_video_done_prompt_only_the_active_language() -> None:
    from modules import translations

    translations.set_language("nl")
    nl_prompt = translations.t("video_done_prompt")
    assert "Meteen openen?" in nl_prompt
    assert "Open now?" not in nl_prompt

    translations.set_language("en")
    en_prompt = translations.t("video_done_prompt")
    assert "Open now?" in en_prompt
    assert "Meteen openen?" not in en_prompt
    translations.set_language("nl")  # reset for the other tests


# --------------------------------------------------------------------------
# B267 - beside "Open video" also an "Open folder" button that opens a file
# manager on the folder of the rendered file.
# --------------------------------------------------------------------------
def test_open_folder_uses_the_containing_folder(tmp_path: Path,
                                                monkeypatch) -> None:
    import os
    import sys

    from modules import pipeline

    sub = tmp_path / "output" / "Lied_P"
    sub.mkdir(parents=True)
    video = sub / "Zondag Lied P.mp4"
    video.write_bytes(b"x")

    opened = {}

    def fake_startfile(path):
        opened["path"] = path

    monkeypatch.setattr(os, "startfile", fake_startfile, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    pipeline.open_folder(video)
    assert opened["path"] == str(sub)


def test_open_folder_does_nothing_when_absent(tmp_path: Path,
                                              monkeypatch) -> None:
    import os

    from modules import pipeline

    called = {"count": 0}
    monkeypatch.setattr(
        os, "startfile",
        lambda p: called.__setitem__("count", called["count"] + 1),
        raising=False)
    pipeline.open_folder(tmp_path / "bestaat" / "niet.mp4")
    assert called["count"] == 0


# --------------------------------------------------------------------------
# B268 - during an instrumental gap (>= GAP_MIN_S) both the line just sung
# and the waiting line stay visible; the 3-2-1 countdown comes as an overlay
# on top, not in place of the text.
# --------------------------------------------------------------------------
def _has_colour(image, rgb, tol) -> bool:
    arr = np.asarray(image).reshape(-1, 3).astype(int)
    target = np.array(rgb)
    return bool((np.abs(arr - target).sum(axis=1) < tol).any())


def test_instrumental_gap_shows_lines_beside_countdown(tmp_path) -> None:
    """The waiting lines stay up during the gap instead of vanishing
    behind the countdown. B474: the line just sung does make way."""
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import GAP_MIN_S, _DEFAULT_COLORS, _compose_frame

    # Line 0 ends at 10 s, line 1 only starts at 10 + GAP_MIN_S + 2 s ->
    # a gap well above the threshold.
    gap = GAP_MIN_S + 2.0
    lines = [TextLine(0, "regel een", False), TextLine(1, "regel twee", False)]
    spans = {0: (8.0, 10.0), 1: (10.0 + gap, 12.0 + gap)}
    timed = generate_skeleton(lines, spans)
    vocal = [t for t in timed if not t.crowd]
    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))

    # A moment just before line 1 starts: inside the countdown window
    # (digit "1").
    moment = 10.0 + gap - 0.5
    frame = _compose_frame(moment, vocal, 5.0, 60.0, 320, 180, font, font,
                           logo, "Titel", _DEFAULT_COLORS)
    # B474: during the gap the line just sung makes way for the countdown;
    # the waiting line 1 is there (white = the "voor" colour).
    assert _has_colour(frame, _DEFAULT_COLORS["voor"], tol=40)
    # The countdown itself is there (green).
    assert _has_colour(frame, _DEFAULT_COLORS["zang"], tol=40)

    # Just after the end of the countdown window the digit is gone again,
    # but the lines stay up.
    later = 10.0 + gap + 0.5
    frame2 = _compose_frame(later, vocal, 5.0, 60.0, 320, 180, font, font,
                            logo, "Titel", _DEFAULT_COLORS)
    assert _has_colour(frame2, _DEFAULT_COLORS["voor"], tol=40)
