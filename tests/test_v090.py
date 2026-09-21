"""Tests for v0.90.0-fix.

B272: during an instrumental gap (>= GAP_MIN_S) the layout still kept
the already-sung line on slot -1 beside the waiting lines, with a wide
empty hole the 3-2-1 countdown had to fit into on its own. The line on
slot -1 now disappears altogether during the gap; the three remaining
lines (just sung / next / the one after) and the countdown spread
evenly over the same vertical band.

B273: the rendered video now carries the KaraokeTool version number in
the ffmpeg metadata (``comment`` tag), so that afterwards (when
testing, for instance) it can be traced which version made a video
file.
"""
from __future__ import annotations

import numpy as np


def _color_top(frame, color, tol=40):
    """Topmost (smallest) y coordinate where ``color`` occurs, or None."""
    arr = np.asarray(frame)
    target = np.array(color)
    mask = np.abs(arr.astype(int) - target).sum(axis=2) < tol
    rows = np.where(mask.any(axis=1))[0]
    return int(rows.min()) if len(rows) else None


def _white_text_on_row(frame, y, white, tol=40):
    """True if row ``y`` holds a pixel anywhere in ``white``."""
    arr = np.asarray(frame)
    row = arr[y]
    target = np.array(white)
    mask = np.abs(row.astype(int) - target).sum(axis=1) < tol
    return bool(mask.any())


def test_slot_min1_disappears_during_the_gap() -> None:
    """B272: the line that would normally sit on slot -1 (here: the very
    first line, two lines before the waiting one) is nowhere on screen
    during the gap - only the just-sung line, the countdown and the two
    waiting lines are left."""
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import GAP_MIN_S, _DEFAULT_COLORS, _compose_frame

    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    gap = GAP_MIN_S + 2.0
    width, height = 320, 180

    # Without B272 line 0 would sit on slot -1 during the gap after
    # line 1.
    lines = [TextLine(0, "eerste eerste eerste", False),
             TextLine(1, "tweede", False),
             TextLine(2, "derde", False)]
    spans = {0: (2.0, 4.0), 1: (5.0, 7.0), 2: (7.0 + gap, 9.0 + gap)}
    timed = generate_skeleton(lines, spans)
    vocal = [t for t in timed if not t.crowd]
    moment = 7.0 + gap - 0.5   # inside the countdown window to line 2
    frame = _compose_frame(moment, vocal, 1.0, 60.0, width, height,
                           font, font, logo, "T", _DEFAULT_COLORS)

    # "eerste" (line 0) would normally be white (not active yet) on the
    # old slot -1 position, just above slot 0 (0.56). That band has to
    # be empty now.
    old_slot_min1_y = int(height * (2 * 0.34 - 0.56))
    if 0 <= old_slot_min1_y < height:
        assert not _white_text_on_row(
            frame, old_slot_min1_y, _DEFAULT_COLORS["voor"])


def test_the_countdown_sits_where_the_sung_line_was() -> None:
    """B474: the four evenly spread positions are gone. During the gap
    the just-sung line disappears and the countdown takes exactly its
    place (slot 0); the waiting lines stay where they are."""
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import GAP_MIN_S, _DEFAULT_COLORS, _compose_frame

    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    gap = GAP_MIN_S + 2.0
    width, height = 320, 180

    lines = [TextLine(0, "eerste", False),
             TextLine(1, "tweede", False),
             TextLine(2, "derde", False)]
    spans = {0: (2.0, 4.0), 1: (5.0, 7.0), 2: (7.0 + gap, 9.0 + gap)}
    timed = generate_skeleton(lines, spans)
    vocal = [t for t in timed if not t.crowd]
    moment = 7.0 + gap - 0.5
    frame = _compose_frame(moment, vocal, 1.0, 60.0, width, height,
                           font, font, logo, "T", _DEFAULT_COLORS)

    y_digit = _color_top(frame, _DEFAULT_COLORS["zang"])
    assert y_digit is not None
    # Within a few pixels (rounding, font metrics), not exactly equal.
    assert abs(y_digit - int(height * 0.34)) <= 6


def test_the_video_metadata_carries_the_version_number(tmp_path) -> None:
    """B273: the rendered .mp4 gets the KaraokeTool version number in
    the ffmpeg ``comment`` metadata."""
    from modules import ffmpeg
    import pytest
    if not ffmpeg.is_available():
        pytest.skip("ffmpeg not available")

    import json as json_module
    import subprocess

    from PIL import Image

    from modules import __version__
    from modules.audio import save_wav
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import render_video

    sample_rate = 22_050
    duration_s = 12
    tone = (0.3 * np.sin(2 * np.pi * 220 *
                         np.arange(duration_s * sample_rate) / sample_rate)
            ).astype(np.float32)
    audio = tmp_path / "karaoke.wav"
    save_wav(audio, np.stack([tone, tone], axis=1), sample_rate)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (200, 80), (60, 176, 67, 255)).save(logo)

    lines = (TextLine(0, "Kedeng Kedeng", False),)
    timed = generate_skeleton(lines, {0: (6.0, 8.0)})

    target = render_video(timed, audio, logo, "Testlied",
                          tmp_path / "video.mp4", width=320, height=180,
                          fps=5)

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
         str(target)], capture_output=True, text=True, check=True)
    tags = json_module.loads(result.stdout)["format"].get("tags", {})
    comment = tags.get("comment", "")
    assert __version__ in comment
