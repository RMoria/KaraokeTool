"""Tests voor v0.87.0-fixes (B266 dubbeltalige video-klaar-prompt, B267
"Map openen"-knop naast video-klaar, B268 3-2-1-afteller als overlay bij een
instrumentaal gat i.p.v. de regels te verbergen)."""
from __future__ import annotations

from pathlib import Path

import numpy as np


# --------------------------------------------------------------------------
# B266 - de Nederlandse "video klaar"-vraag toonde per ongeluk zowel de
# Nederlandse als de Engelse tekst ("Meteen openen? / Open now?"). Nu alleen
# de actieve taal.
# --------------------------------------------------------------------------
def test_video_done_prompt_alleen_actieve_taal() -> None:
    from modules import translations

    translations.set_language("nl")
    nl_prompt = translations.t("video_done_prompt")
    assert "Meteen openen?" in nl_prompt
    assert "Open now?" not in nl_prompt

    translations.set_language("en")
    en_prompt = translations.t("video_done_prompt")
    assert "Open now?" in en_prompt
    assert "Meteen openen?" not in en_prompt
    translations.set_language("nl")  # reset voor andere tests


# --------------------------------------------------------------------------
# B267 - naast "Video openen" ook een knop "Map openen" die een
# bestandsbeheerder opent op de map van het gerenderde bestand.
# --------------------------------------------------------------------------
def test_open_folder_gebruikt_bevattende_map(tmp_path: Path, monkeypatch) -> None:
    import os
    import sys

    from modules import pipeline

    sub = tmp_path / "output" / "Lied_P"
    sub.mkdir(parents=True)
    video = sub / "Zondag Lied P.mp4"
    video.write_bytes(b"x")

    geopend = {}

    def fake_startfile(path):
        geopend["path"] = path

    monkeypatch.setattr(os, "startfile", fake_startfile, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    pipeline.open_folder(video)
    assert geopend["path"] == str(sub)


def test_open_folder_bestaat_niet_doet_niets(tmp_path: Path, monkeypatch) -> None:
    import os

    from modules import pipeline

    geroepen = {"aantal": 0}
    monkeypatch.setattr(
        os, "startfile",
        lambda p: geroepen.__setitem__("aantal", geroepen["aantal"] + 1),
        raising=False)
    pipeline.open_folder(tmp_path / "bestaat" / "niet.mp4")
    assert geroepen["aantal"] == 0


# --------------------------------------------------------------------------
# B268 - tijdens een instrumentaal gat (>= GAP_MIN_S) blijven de al gezongen
# en de wachtende regel gewoon zichtbaar; de 3-2-1-afteller komt als overlay
# bovenop, niet in de plaats van de tekst.
# --------------------------------------------------------------------------
def _has_colour(image, rgb, tol) -> bool:
    arr = np.asarray(image).reshape(-1, 3).astype(int)
    target = np.array(rgb)
    return bool((np.abs(arr - target).sum(axis=1) < tol).any())


def test_instrumentaal_gat_toont_regels_naast_afteller(tmp_path) -> None:
    """De wachtende regels blijven staan tijdens het gat i.p.v. te verdwijnen
    achter de afteller. B474: de net gezongen regel maakt wel plaats."""
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import GAP_MIN_S, _DEFAULT_COLORS, _compose_frame

    # Regel 0 eindigt op 10s, regel 1 begint pas op 10 + GAP_MIN_S + 2s ->
    # een gat ruim boven de drempel.
    gap = GAP_MIN_S + 2.0
    lines = [TextLine(0, "regel een", False), TextLine(1, "regel twee", False)]
    spans = {0: (8.0, 10.0), 1: (10.0 + gap, 12.0 + gap)}
    timed = generate_skeleton(lines, spans)
    vocal = [t for t in timed if not t.crowd]
    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))

    # Moment vlak vóór regel 1 start: binnen het aftelvenster (cijfer "1").
    moment = 10.0 + gap - 0.5
    frame = _compose_frame(moment, vocal, 5.0, 60.0, 320, 180, font, font,
                           logo, "Titel", _DEFAULT_COLORS)
    # B474: de net gezongen regel maakt tijdens het gat plaats voor de
    # afteller; de wachtende regel 1 staat er wel (wit = "voor"-kleur).
    assert _has_colour(frame, _DEFAULT_COLORS["voor"], tol=40)
    # De afteller zelf staat er (groen).
    assert _has_colour(frame, _DEFAULT_COLORS["zang"], tol=40)

    # Vlak na het einde van het aftelvenster is het cijfer weer weg, maar de
    # regels blijven staan.
    later = 10.0 + gap + 0.5
    frame2 = _compose_frame(later, vocal, 5.0, 60.0, 320, 180, font, font,
                            logo, "Titel", _DEFAULT_COLORS)
    assert _has_colour(frame2, _DEFAULT_COLORS["voor"], tol=40)
