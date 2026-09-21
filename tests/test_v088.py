"""Tests for the v0.88.0 fix (B270: the 3-2-1 countdown sat at a fixed
position on screen and could overlap a line that runs over 2 rows) and
the v0.90.0 fix (B272: during a gap the line in slot -1 now slides out
of view entirely instead of simply staying visible - see test_v090.py
for the new compact 4-position layout itself; these two tests are
rewritten here so that they keep checking the B270 margin logic against
that new layout)."""
from __future__ import annotations

import numpy as np


def _color_top(frame, color, tol=40):
    """Topmost (smallest) y coordinate where ``color`` occurs, or None."""
    arr = np.asarray(frame)
    target = np.array(color)
    mask = np.abs(arr.astype(int) - target).sum(axis=2) < tol
    rows = np.where(mask.any(axis=1))[0]
    return int(rows.min()) if len(rows) else None


# --------------------------------------------------------------------------
# B270/B272/B474 - during an instrumental gap slot -1 drops out entirely
# (B272) and the countdown takes the PLACE of the line just sung (B474).
# That line is no longer drawn, so it can no longer push the countdown
# down either; what is left to check is that the countdown never lands
# in the text of slot 1.
# --------------------------------------------------------------------------
def test_gap_countdown_stays_above_slot1(tmp_path) -> None:
    """Even with an extremely long line in slot 0 the digit never ends
    up in slot 1's text (hard margin, B270/B272)."""
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import GAP_MIN_S, _DEFAULT_COLORS, _compose_frame

    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    gap = GAP_MIN_S + 2.0
    width, height = 320, 180

    lines = [TextLine(0, "eerste", False),
             TextLine(1, "a " * 200, False),   # very long, sits in slot 0
             TextLine(2, "derde", False)]
    spans = {0: (2.0, 4.0), 1: (5.0, 7.0), 2: (7.0 + gap, 9.0 + gap)}
    timed = generate_skeleton(lines, spans)
    vocal = [t for t in timed if not t.crowd]
    moment = 7.0 + gap - 0.5
    frame = _compose_frame(moment, vocal, 1.0, 60.0, width, height,
                           font, font, logo, "T", _DEFAULT_COLORS)
    y_digit = _color_top(frame, _DEFAULT_COLORS["zang"])
    # B474: slot 1 (the waiting line "derde") simply keeps its own place
    # during the gap; the countdown sits in slot 0's place and therefore
    # above it.
    slot1_y = int(height * 0.56)
    assert y_digit is not None
    assert y_digit < slot1_y


# --------------------------------------------------------------------------
# B270 - the intro countdown before the very first line has no slot -1
# (there is no line before line 0), so the fixed base position is always
# safe here, even when line 0 itself is long and runs over 2 rows.
# --------------------------------------------------------------------------
def test_intro_countdown_unchanged_on_a_long_first_line() -> None:
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import _DEFAULT_COLORS, _compose_frame

    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    width, height = 320, 180

    def render(text_value: str):
        lines = [TextLine(0, text_value, False)]
        timed = generate_skeleton(lines, {0: (10.0, 12.0)})
        vocal = [t for t in timed if not t.crowd]
        moment = 9.0   # within COUNTDOWN_S=3s before line 0 (starts 10.0)
        first_text = 5.0
        return _compose_frame(moment, vocal, first_text, 60.0, width,
                              height, font, font, logo, "T", _DEFAULT_COLORS)

    short = render("kort")
    long_line = render("a " * 60)
    y_short = _color_top(short, _DEFAULT_COLORS["zang"])
    y_long = _color_top(long_line, _DEFAULT_COLORS["zang"])
    assert y_short == y_long
