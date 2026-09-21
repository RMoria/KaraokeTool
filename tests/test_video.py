"""Tests for modules.video (line windows + a real mini render)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from modules import ffmpeg
from modules.karaoke_text import TextLine
from modules.timing import generate_skeleton
from modules.video import VideoError, render_video, shift_times


def _timed_lines():
    lines = (TextLine(0, "Kedeng Kedeng", False),
             TextLine(1, "La-la-la", True))
    return generate_skeleton(lines, {0: (6.0, 8.0), 1: (9.0, 11.0)})


def test_load_background_center_crop(tmp_path: Path) -> None:
    """B126: the background image is center-cropped to the video size."""
    from PIL import Image
    from modules.video import _load_background
    src = tmp_path / "bg.png"
    Image.new("RGB", (2000, 500), (10, 20, 30)).save(src)
    bg = _load_background(str(src), 1280, 720)
    assert bg is not None and bg.size == (1280, 720)
    assert _load_background("", 1280, 720) is None
    assert _load_background(str(tmp_path / "weg.png"), 1280, 720) is None


def test_disabled_lines_are_not_in_the_render(tmp_path: Path) -> None:
    """B180: with every line disabled there is no singing line left."""
    from dataclasses import replace
    lines = [replace(line, disabled=True) for line in _timed_lines()]
    logo = tmp_path / "logo.png"
    from PIL import Image
    Image.new("RGB", (10, 10)).save(logo)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")  # content is irrelevant; it fails earlier
    with pytest.raises(VideoError):
        render_video(lines, audio, logo, "T", tmp_path / "out.mp4")


def test_fit_body_font_shrinks_long_line() -> None:
    """B102: a long line makes the body font shrink to fit within 85%; a
    short line keeps the base size."""
    from modules.timing import Syllable, TimedLine
    from modules.video import _fit_body_font
    base = int(720 * 0.06)
    short = [TimedLine(0, "hoi", False, (Syllable("hoi", 0.0, 1.0),))]
    long_text = "a" * 200
    long_line = [TimedLine(0, long_text, False,
                           (Syllable(long_text, 0.0, 1.0),))]
    assert _fit_body_font("", short, 1280, base).size == base
    assert _fit_body_font("", long_line, 1280, base).size < base


def test_countdown_number() -> None:
    """B101: 3-2-1 in the last 3 s before the first singing, nothing
    outside that."""
    from modules.video import countdown_number
    first = 10.0
    assert countdown_number(6.9, first) is None   # > 3 s before
    assert countdown_number(7.0, first) == 3      # exactly 3 s before
    assert countdown_number(7.5, first) == 3
    assert countdown_number(8.5, first) == 2
    assert countdown_number(9.5, first) == 1
    assert countdown_number(10.0, first) is None  # the singing starts
    assert countdown_number(11.0, first) is None  # during the singing


def test_shift_times_windows() -> None:
    windows = shift_times(_timed_lines())
    # First line visible from 5 s before the singing (6.0 - 5).
    assert windows[0].slot1_from == pytest.approx(1.0)
    # Moves on as soon as line 2 starts (9.0 < 8.0 + 3).
    assert windows[0].slot1_until == pytest.approx(9.0)
    # The last line stays up for 3 s.
    assert windows[1].slot1_until == pytest.approx(14.0)


def test_render_requires_times() -> None:
    untimed = generate_skeleton((TextLine(0, "Kedeng", False),))
    with pytest.raises(VideoError, match="zonder tijden"):
        render_video(untimed, Path("x.wav"), Path("logo.png"), "T",
                     Path("uit.mp4"))


def test_render_small_video(tmp_path: Path) -> None:
    """A real mini render: mp4 with H.264/yuv420p and AAC."""
    if not ffmpeg.is_available():
        pytest.skip("ffmpeg not available")
    from PIL import Image

    from modules.audio import save_wav

    sample_rate = 22_050
    tone = (0.3 * np.sin(2 * np.pi * 220 *
                         np.arange(12 * sample_rate) / sample_rate)
            ).astype(np.float32)
    audio = tmp_path / "karaoke.wav"
    save_wav(audio, np.stack([tone, tone], axis=1), sample_rate)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (200, 80), (60, 176, 67, 255)).save(logo)

    target = render_video(_timed_lines(), audio, logo, "Testlied",
                          tmp_path / "video.mp4", width=320, height=180,
                          fps=5)
    assert target.exists() and target.stat().st_size > 10_000

    import json as json_module
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
         str(target)], capture_output=True, text=True, check=True)
    streams = {stream["codec_type"]: stream
               for stream in json_module.loads(result.stdout)["streams"]}
    assert streams["video"]["codec_name"] == "h264"
    assert streams["video"]["pix_fmt"] == "yuv420p"
    assert streams["audio"]["codec_name"] == "aac"
    # Outro: the last line ends at 11 s -> video >= 11 + 3 + 5 s.
    assert float(streams["video"]["duration"]) >= 18.5


def test_every_line_gets_a_window_even_with_equal_times() -> None:
    """Lines with identical times all stay visible, in order."""
    lines = (TextLine(0, "regel een", False), TextLine(1, "regel twee",
                                                       False))
    timed = generate_skeleton(lines, {0: (10.0, 12.0), 1: (10.0, 12.0)})
    windows = shift_times(timed)
    assert windows[0].line.index == 0 and windows[1].line.index == 1
    assert all(w.slot1_until > w.slot1_from for w in windows)


def test_compose_frame_layout(tmp_path) -> None:
    """The intro shows logo and title; during the singing 3 lines and no
    logo."""
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import _compose_frame

    # Line 0 (singing) with crowd 'La la' under it, then more singing.
    lines = [TextLine(0, "regel 0", False), TextLine(1, "La la", True),
             TextLine(2, "regel 1", False), TextLine(3, "regel 2", False),
             TextLine(4, "regel 3", False)]
    spans = {0: (10.0, 11.0), 1: (10.2, 10.9), 2: (12.0, 13.0),
             3: (14.0, 15.0), 4: (16.0, 17.0)}
    timed = generate_skeleton(lines, spans)
    # B475: a crowd line simply runs along in the stream, no longer as a
    # separate extra line underneath.
    vocal = sorted(timed, key=lambda line: line.index)
    font = ImageFont.load_default()
    logo = Image.new("RGBA", (80, 40), (0, 200, 0, 255))

    # Intro (before the first text at 10-5=5s): logo visible (green
    # pixel).
    from modules.video import _DEFAULT_COLORS
    intro = _compose_frame(1.0, vocal, 5.0, 30.0, 320, 180,
                           font, font, logo, "Titel", _DEFAULT_COLORS)
    assert _has_colour(intro, (0, 200, 0), tol=60)

    # During the singing: no logo (no green block), but text.
    singing = _compose_frame(10.5, vocal, 5.0, 30.0, 320,
                             180, font, font, logo, "Titel",
                             _DEFAULT_COLORS)
    assert not _has_colour(singing, (0, 200, 0), tol=40)
    # The red crowd line 'La la' (10.2-10.9) is the active line at that
    # moment and so runs along in the stream (B475).
    assert _has_colour(singing, (229, 57, 53), tol=60)


def test_outro_title_uses_the_vocal_colour(tmp_path) -> None:
    """B72: the closing title (outro) is in the 'singing now' colour; the
    intro is white."""
    from PIL import Image, ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import _DEFAULT_COLORS, _compose_frame

    lines = [TextLine(0, "regel 0", False)]
    timed = generate_skeleton(lines, {0: (10.0, 11.0)})
    vocal = [t for t in timed if not t.crowd]
    font = ImageFont.load_default()
    logo = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    # Outro (after outro_start): title in the vocal colour (green).
    outro = _compose_frame(40.0, vocal, 5.0, 30.0, 320, 180, font, font,
                           logo, "Titel", _DEFAULT_COLORS)
    assert _has_colour(outro, (60, 176, 67), tol=40)


def test_fit_title_font_shrinks_to_width() -> None:
    """B73: the title is shrunk so that it gets narrower and, where it
    can, fits on one line within the width."""
    from modules.video import _fit_title_font, _load_font

    title = "Een lange songtitel die verkleind moet worden"
    big = _load_font("", 48)
    try:
        # With a tight width the title gets smaller than the start size.
        fitted = _fit_title_font("", title, max_width=200, start_size=48)
        assert fitted.getlength(title) < big.getlength(title)
        # With an attainable width the title really fits within the
        # limit.
        fitting = _fit_title_font("", title, max_width=600, start_size=48)
        assert fitting.getlength(title) <= 600
        # With a roomy width a short title keeps the start size.
        roomy = _fit_title_font("", "Titel", max_width=100000, start_size=48)
        assert roomy.getlength("Titel") == big.getlength("Titel")
    except AttributeError:  # load_default without getlength
        pass


def _has_colour(image, rgb, tol) -> bool:
    import numpy as np
    arr = np.asarray(image).reshape(-1, 3).astype(int)
    target = np.array(rgb)
    return bool((np.abs(arr - target).sum(axis=1) < tol).any())


def test_colors_from_settings_and_hex() -> None:
    from modules.config import VideoSettings
    from modules.video import _hex_to_rgb, colors_from_settings

    assert _hex_to_rgb("#3CB043", (0, 0, 0)) == (60, 176, 67)
    assert _hex_to_rgb("kapot", (1, 2, 3)) == (1, 2, 3)
    palette = colors_from_settings(VideoSettings())
    assert palette["zang"] == (60, 176, 67)
    assert palette["crowd"] == (229, 57, 53)
    assert palette["background"] == (10, 10, 14)


def test_wrap_and_overflow() -> None:
    from PIL import ImageFont

    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton
    from modules.video import (_wrap_syllables, fits_on_screen,
                               overflowing_lines)

    font = ImageFont.load_default()
    short = generate_skeleton((TextLine(0, "Kort zinnetje", False),))[0]
    # Roomy width: fits on one row.
    assert len(_wrap_syllables(short.syllables, font, 100000)) == 1
    # Zero-wide limit: forces a split into two rows.
    long_line = generate_skeleton(
        (TextLine(0, "Een langere zin, met een komma erin", False),))[0]
    rows = _wrap_syllables(long_line.syllables, font, 1.0)
    assert len(rows) == 2
    # Split at the comma: the first row ends on a comma word.
    assert rows[0][-1].text.rstrip().endswith(",")
    assert fits_on_screen(short.syllables, font, 100000) is True

    lines = generate_skeleton((TextLine(0, "x " * 200, False),))
    assert overflowing_lines(lines, 320, 180, "")  # far too long
