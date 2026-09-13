"""Tests voor v0.88.0-fix (B270: de 3-2-1-afteller stond op een vaste
beeldpositie en kon overlappen met een regel die over 2 rijen loopt) en
v0.90.0-fix (B272: tijdens een gat schuift de regel op slot -1 er nu
helemaal uit i.p.v. gewoon zichtbaar te blijven - zie test_v090.py voor de
nieuwe compacte 4-posities-layout zelf; deze twee tests zijn hier herschreven
zodat ze de B270-marge-logica tegen díe nieuwe layout blijven toetsen)."""
from __future__ import annotations

import numpy as np


def _color_top(frame, color, tol=40):
    """Bovenste (kleinste) y-coördinaat waar ``kleur`` voorkomt, of None."""
    arr = np.asarray(frame)
    target = np.array(color)
    mask = np.abs(arr.astype(int) - target).sum(axis=2) < tol
    rows = np.where(mask.any(axis=1))[0]
    return int(rows.min()) if len(rows) else None


# --------------------------------------------------------------------------
# B270/B272/B474 - tijdens een instrumentaal gat valt slot -1 helemaal weg
# (B272) en neemt de afteller de PLEK in van de net gezongen regel (B474).
# Die regel wordt dan niet meer getekend, dus de afteller kan er ook niet
# meer door omlaag geduwd worden; wat blijft is dat hij nooit in de tekst
# van slot 1 mag komen.
# --------------------------------------------------------------------------
def test_gat_afteller_blijft_boven_slot1(tmp_path) -> None:
    """Ook bij een extreem lange regel op slot 0 komt het cijfer nooit in
    slot 1's tekst terecht (harde marge, B270/B272)."""
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import GAP_MIN_S, _DEFAULT_COLORS, _compose_frame

    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    gap = GAP_MIN_S + 2.0
    width, height = 320, 180

    lines = [TextLine(0, "eerste", False),
             TextLine(1, "a " * 200, False),   # extreem lang, staat op slot 0
             TextLine(2, "derde", False)]
    spans = {0: (2.0, 4.0), 1: (5.0, 7.0), 2: (7.0 + gap, 9.0 + gap)}
    timed = generate_skeleton(lines, spans)
    vocal = [t for t in timed if not t.crowd]
    moment = 7.0 + gap - 0.5
    frame = _compose_frame(moment, vocal, 1.0, 60.0, width, height,
                           font, font, logo, "T", _DEFAULT_COLORS)
    y_digit = _color_top(frame, _DEFAULT_COLORS["zang"])
    # B474: slot 1 (de wachtende regel "derde") houdt tijdens het gat
    # gewoon zijn eigen plek; de afteller staat op die van slot 0 en dus
    # erboven.
    slot1_y = int(height * 0.56)
    assert y_digit is not None
    assert y_digit < slot1_y


# --------------------------------------------------------------------------
# B270 - de intro-aftelling vóór de allereerste regel heeft geen slot -1 (er
# is geen regel vóór regel 0), dus de vaste basispositie is hier altijd al
# veilig, ook als regel 0 zelf lang is en over 2 rijen loopt.
# --------------------------------------------------------------------------
def test_intro_afteller_ongewijzigd_bij_lange_eerste_regel() -> None:
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
        moment = 9.0   # binnen COUNTDOWN_S=3s vóór regel 0 (start 10.0)
        first_text = 5.0
        return _compose_frame(moment, vocal, first_text, 60.0, width,
                              height, font, font, logo, "T", _DEFAULT_COLORS)

    short = render("kort")
    held = render("a " * 60)
    y_short = _color_top(short, _DEFAULT_COLORS["zang"])
    y_lang = _color_top(held, _DEFAULT_COLORS["zang"])
    assert y_short == y_lang
