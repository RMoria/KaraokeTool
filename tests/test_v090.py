"""Tests voor v0.90.0-fix.

B272: tijdens een instrumenteel gat (>= GAP_MIN_S) liet de layout de
al-gezongen regel op slot -1 nog staan naast de wachtende regels, met een
groot leeg gat waar de 3-2-1-afteller los in moest passen. De regel op
slot -1 verdwijnt nu helemaal tijdens het gat; de resterende 3 regels
(net gezongen / eerstvolgende / daarna) en de afteller verdelen zich
gelijkmatig over dezelfde verticale band.

B273: de gerenderde video krijgt nu het KaraokeTool-versienummer in de
ffmpeg-metadata (``comment``-tag), zodat achteraf (bv. bij testen) te
achterhalen is met welke versie een videobestand is gemaakt.
"""
from __future__ import annotations

import numpy as np


def _color_top(frame, color, tol=40):
    """Bovenste (kleinste) y-coördinaat waar ``kleur`` voorkomt, of None."""
    arr = np.asarray(frame)
    target = np.array(color)
    mask = np.abs(arr.astype(int) - target).sum(axis=2) < tol
    rows = np.where(mask.any(axis=1))[0]
    return int(rows.min()) if len(rows) else None


def _wittekst_linkerkant_op_y(frame, y, kleur_wit, tol=40):
    """True als er ergens op rij ``y`` een pixel in ``kleur_wit`` staat."""
    arr = np.asarray(frame)
    row = arr[y]
    target = np.array(kleur_wit)
    mask = np.abs(row.astype(int) - target).sum(axis=1) < tol
    return bool(mask.any())


def test_slot_min1_verdwijnt_tijdens_gat() -> None:
    """B272: de regel die normaal op slot -1 zou staan (hier: de allereerste
    regel, twee regels vóór de wachtende regel) komt tijdens het gat nergens
    meer in beeld - alleen de net-gezongen regel, de afteller en de twee
    wachtende regels blijven over."""
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import GAP_MIN_S, _DEFAULT_COLORS, _compose_frame

    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    gap = GAP_MIN_S + 2.0
    width, height = 320, 180

    # Regel 0 zou zonder B272 op slot -1 staan tijdens het gat ná regel 1.
    lines = [TextLine(0, "eerste eerste eerste", False),
             TextLine(1, "tweede", False),
             TextLine(2, "derde", False)]
    spans = {0: (2.0, 4.0), 1: (5.0, 7.0), 2: (7.0 + gap, 9.0 + gap)}
    timed = generate_skeleton(lines, spans)
    vocal = [t for t in timed if not t.crowd]
    moment = 7.0 + gap - 0.5   # binnen het aftelvenster naar regel 2
    frame = _compose_frame(moment, vocal, 1.0, 60.0, width, height,
                           font, font, logo, "T", _DEFAULT_COLORS)

    # "eerste" (regel 0) zou normaal wit zijn (nog niet actief) op de oude
    # slot -1-positie, vlak boven slot 0 (0.56). Die band moet nu leeg zijn.
    oude_slot_min1_y = int(height * (2 * 0.34 - 0.56))
    if 0 <= oude_slot_min1_y < height:
        assert not _wittekst_linkerkant_op_y(
            frame, oude_slot_min1_y, _DEFAULT_COLORS["voor"])


def test_afteller_staat_op_de_plek_van_de_gezongen_regel() -> None:
    """B474: de vier gelijk verdeelde posities zijn eruit. Tijdens het gat
    verdwijnt de net gezongen regel en neemt de afteller precies zijn plek
    (slot 0) in; de wachtende regels blijven staan waar ze staan."""
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
    # Binnen een paar pixels (afronding/font-metrics), niet exact gelijk.
    assert abs(y_digit - int(height * 0.34)) <= 6


def test_video_metadata_bevat_versienummer(tmp_path) -> None:
    """B273: de gerenderde .mp4 krijgt het KaraokeTool-versienummer in de
    ffmpeg-``comment``-metadata."""
    from modules import ffmpeg
    import pytest
    if not ffmpeg.is_available():
        pytest.skip("ffmpeg niet beschikbaar")

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
