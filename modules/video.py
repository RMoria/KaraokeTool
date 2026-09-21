"""Karaoke video renderer (generic, fully data-driven).

All timing comes from ``timing.json``; this renderer contains no
song-specific exceptions. Per song you only replace the logo, the
audio and the timing file (see ``docs/video_standard.md``).

Image build-up: logo at the top; at most two text lines - the active
line (white -> green per syllable -> grey; crowd white -> red ->
grey; long syllables underlined) and below it, already in white, the
next line. Intro: logo only (>= 5 s). The first line appears 5 s
before the first vocals; lines stay for 3 s. Outro: logo + song title
(>= 5 s); if the music is shorter, the video is extended with
silence. Output: H.264 + yuv420p, audio AAC.
"""

from __future__ import annotations

import logging
import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from PIL import Image, ImageDraw, ImageFont

from . import __version__
from . import ffmpeg as ffmpeg_module
from . import karaoke_text
from . import proc
from .timing import TimedLine
from .translations import t

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, float], None]

LEAD_IN_S = 5.0      # line visible before the vocals
HOLD_S = 3.0         # line stays on screen after the vocals
OUTRO_MIN_S = 5.0    # logo + title minimally visible
INTRO_MIN_S = 5.0    # logo/title minimally visible before the text (B203)
COUNTDOWN_S = 3      # countdown seconds (3-2-1) before the vocals (B101)
GAP_MIN_S = 5.0      # instrumental gap from here -> 3-2-1 overlay (B227/B268)
_LINE_TRANSITION_S = 0.35   # duration of the smooth line shift (B242)
#: B501: the intro does not cut over to the text but fades into it over
#: the last half second, and the outro fades in from the text over its
#: first second. Both pictures are built for those frames and laid over
#: each other; that costs about 75 frames per video, so the render time
#: does not notice it.
_INTRO_FADE_S = 0.5
_OUTRO_FADE_S = 1.0
#: What a render in progress is called, next to the final file (B468).
SCRATCH_SUFFIX = ".part.mp4"
#: B476: air between the two rows of ONE sentence that does not fit on
#: the width. This used to be ``ascent + descent`` - the full box of the
#: font, which is bigger than any letter in it - so the halves of a
#: broken sentence stood as far apart as two different sentences and you
#: could not see they belonged together. Measuring on the real ink of
#: THESE rows is the only way to get them closer without an accented
#: capital under a descender: a blanket fraction is either too loose for
#: one font or a collision in another.
_ROW_AIR_FRAC = 0.07
#: B473: free space between two sentences, on top of the height the
#: sentence above really takes up. A fraction of the row, because the
#: font scales with the picture: a fixed number of pixels would put the
#: sentences relatively far apart at 720p and glue them together at 4K.
_LINE_GAP_FRAC = 0.25


def _stroke_width(font) -> int:
    """Thickness of the outline (B477): thin, and scaling with the font.

    The user asked for a THIN outline; at 50 frames a second a thick one
    reads as a second letter behind the first.
    """
    ascent, descent = font.getmetrics()
    return max(1, round((ascent + descent) / 30))


#: How many misses in a row before the frame cache starts backing off
#: (``_CACHE_PATIENCE``, half a second at fifty frames a second), and
#: how often it looks anyway once it has (``_CACHE_PROBE``). Recording
#: costs about a sixteenth of drawing, so two frames in ten comes to
#: roughly one per cent - and a still stretch that starts is picked up
#: within ten frames, a fifth of a second at fifty frames a second and
#: correspondingly longer at a lower frame rate.
_CACHE_PATIENCE = 25
_CACHE_PROBE = 10

#: Layout of one sentence, kept for the length of a render (B541).
#:
#: How a sentence breaks over rows and how tall it is depends on the
#: line, the font and the width - not on the moment. It was worked out
#: again for every frame all the same: fifty times a second, for three
#: sentences, with a font measurement per syllable. That is the cheap
#: half of a frame and it was being paid over and over, in the drawing
#: AND (since the frame cache) in the recording. Cleared per render, so
#: nothing survives into the next one.
_LAYOUT_CACHE: dict = {}


#: The objects whose ``id`` the keys above are made of (B541). Without
#: this the cache holds a NUMBER and not the line, so a line that is
#: cleaned up can hand its address - and with it its layout - to the
#: next one. Reproduced: a sentence over two rows inherited the height
#: of one row, which puts the sentence below it straight through the
#: text. Holding them costs nothing (they live through the render
#: anyway) and it makes the invariant real instead of assumed.
_LAYOUT_ALIVE: list = []


def _cached(key, make, *alive):
    """``make()``, remembered under ``key`` for this render (B541)."""
    found = _LAYOUT_CACHE.get(key)
    if found is None:
        found = make()
        _LAYOUT_CACHE[key] = found
        _LAYOUT_ALIVE.extend(alive)
    return found


def _row_height(font) -> int:
    """Fallback distance between two rows, without knowing the text."""
    ascent, descent = font.getmetrics()
    return max(1, ascent + descent)


def _row_air(font) -> int:
    """The free space that has to stay between two rows of one sentence.

    B487: never less than the outline needs. The rows of a broken
    sentence sit tight against each other on purpose (B476), and an
    outline grows on both sides - without this the two rows would touch
    as soon as the letters got a border.
    """
    ascent, descent = font.getmetrics()
    room = max(1, int((ascent + descent) * _ROW_AIR_FRAC))
    return max(room, 2 * _stroke_width(font) + 2)


def _row_tops(rows, font) -> list[int]:
    """The y of every row of one sentence, relative to the first (B476).

    Measured on the ink of these very rows (``getbbox``): the bottom of
    the deepest letter above plus a little air, against the top of the
    highest letter below. That way a row with no descender sits tight,
    and a row that starts with an accented capital gets the room it
    needs - which a fixed fraction cannot do for every font.
    """
    tops = [0]
    air = _row_air(font)
    for above, below in zip(rows, rows[1:]):
        try:
            bottom = max(font.getbbox(_disp(item.text))[3] for item in above)
            top = min(font.getbbox(_disp(item.text))[1] for item in below)
        except (ValueError, AttributeError, OSError):
            bottom, top = _row_height(font), 0
        tops.append(tops[-1] + max(1, int(bottom) - int(top) + air))
    return tops


def _line_gap(font) -> int:
    """Free space between two sentences (B473); never less than the
    outline needs on both sides (B487)."""
    ascent, descent = font.getmetrics()
    return max(2, int((ascent + descent) * _LINE_GAP_FRAC),
               2 * _stroke_width(font) + 2)


def _sung_syllables(line) -> tuple:
    """The syllables that go into the picture (B485).

    An inline ``[bg]`` piece is background vocals: it belongs to the
    sentence, is shown in the editors and may overlap its neighbours,
    but it is never sung along with - so it stays out of the render. A
    line that is bg from beginning to end is already dropped earlier
    (``TimedLine.bg``, B510); should one get this far, it keeps its own
    syllables so that the sentence does not go out empty.
    """
    kept = tuple(item for item in getattr(line, "syllables", ())
                 if not getattr(item, "bg", False))
    return kept or tuple(getattr(line, "syllables", ()))


def _line_text_height(line, font, width) -> int:
    """Height (in px) that ``line`` actually occupies as text (B270).

    Same calculation as ``_draw_line``: 1 or 2 rows (``_wrap_syllables``)
    through the shared ``_row_height``. Used to stack the lines on their
    real height (B473) instead of on fixed fractions that overlap as soon
    as a sentence runs over two rows.

    A line without pieces still takes up one row: as a stack height zero
    would let the sentence below climb into it.
    """
    return _cached(("height", id(line), id(font), int(width)),
                   lambda: _measure_line_height(line, font, width),
                   line, font)


def _measure_line_height(line, font, width: int) -> int:
    ascent, descent = font.getmetrics()
    pieces = _sung_syllables(line)
    if not pieces:
        return _row_height(font)
    rows = _wrap_syllables(pieces, font, width * _TEXT_WIDTH_FRAC)
    # The last row still needs its full descent; only the space BETWEEN
    # the rows is measured on the ink (B476).
    return _row_tops(rows, font)[-1] + ascent + descent


def countdown_number(moment: float, first_start: float) -> int | None:
    """The countdown digit (3/2/1) at a time before the first vocals, or
    None.

    In the last ``COUNTDOWN_S`` seconds before ``first_start`` it counts
    down: ``(-3s -> 3, -2s -> 2, -1s -> 1)``. Outside that window ``None``.
    """
    remaining = first_start - moment
    if 0 < remaining <= COUNTDOWN_S:
        return int(math.ceil(remaining))
    return None

_WHITE = (255, 255, 255)
_BLACK = (0, 0, 0)
_GREEN = (60, 176, 67)
_RED = (229, 57, 53)
_GREY = (158, 158, 158)
_BACKGROUND = (10, 10, 14)

#: B511: the outline colour that belongs to each of the four standard
#: text colours. A table and not a rule, because the wish cannot be a
#: rule: black under white, grey AND red, white under green. On
#: perceived brightness red sits at 108 and green at 129, so a single
#: boundary would have to lie below the darker colour and above the
#: lighter one at the same time - which no threshold does. The choice is
#: not about brightness either: green is the ACTIVE colour and has to
#: light up, red is the crowd colour and needs weight against a dark
#: background. Only these four are decided here; a colour the user picks
#: himself falls back on the brightness rule in ``contra_colour``, so
#: that corner does not go rudderless.
_STANDARD_OUTLINE: dict[tuple[int, int, int], tuple[int, int, int]] = {
    _WHITE: _BLACK,
    _GREY: _BLACK,
    _RED: _BLACK,
    _GREEN: _WHITE,
}


def _hex_to_rgb(value: str, default: tuple[int, int, int]
                ) -> tuple[int, int, int]:
    """Convert a #RRGGBB string into an RGB tuple (with fallback)."""
    try:
        s = value.lstrip("#")
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except (ValueError, IndexError, AttributeError):
        return default


def contra_colour(colour: tuple[int, int, int]) -> tuple[int, int, int]:
    """The outline colour that belongs to ``colour`` (B477/B511).

    The four standard colours have a fixed answer (``_STANDARD_OUTLINE``);
    see the note there for why that is a table. Everything else is
    judged on perceived brightness: black under a light letter, white
    under a dark one (the eye sees green far brighter than blue, so a
    plain average would put a black outline around dark blue). The
    boundary lies at half brightness; a fixed, reproducible rule, so the
    same letter colour always gives the same outline.
    """
    fixed = _STANDARD_OUTLINE.get(tuple(colour[:3]))
    if fixed is not None:
        return fixed
    red, green, blue = colour[:3]
    brightness = 0.299 * red + 0.587 * green + 0.114 * blue
    return _BLACK if brightness >= 128 else _WHITE


def colors_from_settings(video_settings) -> dict:
    """Build the render colors from the video settings."""
    colours = {
        "voor": _hex_to_rgb(getattr(video_settings, "color_before", ""),
                            _WHITE),
        "zang": _hex_to_rgb(getattr(video_settings, "color_vocal", ""),
                            _GREEN),
        "na": _hex_to_rgb(getattr(video_settings, "color_after", ""), _GREY),
        "crowd": _hex_to_rgb(getattr(video_settings, "color_crowd", ""),
                             _RED),
        "background": _hex_to_rgb(
            getattr(video_settings, "color_background", ""), _BACKGROUND),
    }
    # B477: every text colour of the ACTIVE line gets its own outline, so
    # the text keeps standing out against a background picture. Empty
    # setting = the contra colour of that letter colour; a filled-in one
    # wins. The line that has already been sung gets none - it is behind
    # us and no longer has to be readable.
    for key, setting in (("voor", "outline_before"),
                         ("zang", "outline_vocal"),
                         ("na", "outline_after"),
                         ("crowd", "outline_crowd")):
        chosen = str(getattr(video_settings, setting, "") or "").strip()
        colours["outline_" + key] = (
            _hex_to_rgb(chosen, contra_colour(colours[key])) if chosen
            else contra_colour(colours[key]))
    return colours


def _default_colours() -> dict:
    base = {"voor": _WHITE, "zang": _GREEN, "na": _GREY,
            "crowd": _RED, "background": _BACKGROUND}
    for key in ("voor", "zang", "na", "crowd"):
        base["outline_" + key] = contra_colour(base[key])
    return base


_DEFAULT_COLORS = _default_colours()

#: Bundled default font (guaranteed to be available).
_BUNDLED_FONT = (Path(__file__).resolve().parents[1] / "assets" / "fonts"
                 / "DejaVuSans-Bold.ttf")
_FONT_CANDIDATES = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf")


class VideoError(Exception):
    """Error while rendering the video."""


@dataclass(frozen=True)
class _Window:
    """Visibility window of one line in the active text box."""

    line: TimedLine
    slot1_from: float
    slot1_until: float


def shift_times(lines: Sequence[TimedLine]) -> list[_Window]:
    """Determine per line when it is in the active box.

    A line moves on as soon as the next vocals start, but otherwise
    stays on screen for another ``HOLD_S``.
    """
    minimum_window = 0.4  # every line guaranteed visible
    windows: list[_Window] = []
    previous_shift = max(0.0, lines[0].start - LEAD_IN_S) if lines else 0.0
    for index, line in enumerate(lines):
        if index + 1 < len(lines):
            shift = min(line.end + HOLD_S, lines[index + 1].start)
        else:
            shift = line.end + HOLD_S
        shift = max(shift, previous_shift + minimum_window)
        windows.append(_Window(line=line, slot1_from=previous_shift,
                               slot1_until=shift))
        previous_shift = shift
    return windows


def render_video(
    lines: Sequence[TimedLine],
    audio_path: Path,
    logo_path: Path,
    title: str,
    target: Path,
    width: int = 1280,
    height: int = 720,
    # B448: fifty instead of twenty-five. The line shift takes 0.35 s
    # (B242) and that was nine frames - just few enough to read as steps.
    # At fifty it is eighteen, and together with the sweeping colour
    # (B447) the whole picture moves instead of ticking. Costs render
    # time and file size; the user weighed that up and chose this.
    fps: int = 50,
    font_path: str = "",
    progress: ProgressCallback | None = None,
    colors: dict | None = None,
    artist: str = "",
    orig_title: str = "",
    background_path: str = "",
    loudness_lufs: float | None = None,
    true_peak_db: float = -1.0,
) -> Path:
    """Render the karaoke video.

    ``artist``/``orig_title`` form the credit line under the title in the
    intro/outro (B123/B124). ``background_path`` places a background image
    (center-crop) behind all frames (B126).

    Raises:
        VideoError: On missing times, ffmpeg errors or an
            unreadable logo.
    """
    untimed = [line.index for line in lines if line.end <= 0]
    if untimed:
        raise VideoError("timing.json bevat regels zonder tijden "
                         f"(regelnummers {untimed[:8]}); vul de timing in.")
    # The order of the karaoke text is leading; there is NO sorting on
    # time, so that all lines appear in the given order.
    palette = colors or _DEFAULT_COLORS
    # Disabled lines are not shown in the render (B180), and neither is
    # a line that is background vocals from beginning to end (B510).
    # Those are two different reasons and since B510 two different
    # fields: switching such a line ON in the editor - the only way to
    # see where it really lies - used to put it straight into the video.
    lines = [line for line in lines
             if not getattr(line, "disabled", False)
             and not getattr(line, "bg", False)]
    # Enough intro: if the first vocals come too early for 5 s of
    # logo/title, shift everything and add silence at the front (B203).
    from dataclasses import replace as _replace
    first_sing = min((line.start for line in lines), default=0.0)
    lead_padding = max(0.0, INTRO_MIN_S + LEAD_IN_S - first_sing)
    if lead_padding > 0.05:
        def _shift(line):
            syls = tuple(_replace(s, start=round(s.start + lead_padding, 3),
                                  end=round(s.end + lead_padding, 3))
                         for s in line.syllables)
            return _replace(line, syllables=syls)
        lines = [_shift(line) for line in lines]
    else:
        lead_padding = 0.0
    ordered = sorted(lines, key=lambda line: line.index)
    # B475: a short crowd interjection used to be drawn as an EXTRA line
    # below the active one and did not count towards the three visible
    # lines. It therefore stayed put where every other sentence moves up
    # and pushes the previous one out, which reads as a mistake. It is
    # now an ordinary sentence in the flow; only its colour stays red,
    # and that comes from ``line.crowd`` in ``_draw_line``, not from its
    # place on screen.
    main_lines = list(ordered)
    if not main_lines:
        raise VideoError("Geen zangregels in timing.json.")

    # The audio shifts with the same silence, so effectively longer.
    # B530: the properties are kept - the number of channels decides how
    # the delay names its layout.
    properties = ffmpeg_module.probe(audio_path)
    audio_duration = properties.duration + lead_padding
    # B485: the whole sentence, background piece included - that piece is
    # not in the picture but the music does have to run long enough for it.
    outro_start = max(line.full_end for line in ordered) + HOLD_S
    duration = max(audio_duration, outro_start + OUTRO_MIN_S)
    first_text = max(0.0, main_lines[0].start - LEAD_IN_S)

    # Body font as large as possible but fitting within 85% width (B102).
    font = _fit_body_font(font_path, main_lines, width, int(height * 0.06))
    # Title two steps larger than before (0.05 -> 0.07 of the height),
    # but reduced if needed so it stays on one line in frame (B73).
    title_font = _fit_title_font(font_path, title, int(width * 0.9),
                                 int(height * 0.07))
    # Credit line 'naar: <artist> - <title>' under the title (B123/B124).
    credit = " - ".join(part for part in (artist.strip(), orig_title.strip())
                        if part)
    credit_font = _load_font(font_path, size=int(height * 0.04))
    background = _load_background(background_path, width, height)
    try:
        logo = Image.open(logo_path).convert("RGBA")
    except OSError as exc:
        raise VideoError(f"Logo onleesbaar: {logo_path}") from exc
    logo_large = _scale(logo, int(height * 0.45))  # larger logo (B71)

    executable = ffmpeg_module.find_executable("ffmpeg")
    if executable is None:
        raise VideoError("ffmpeg niet gevonden (zie README.md).")
    target.parent.mkdir(parents=True, exist_ok=True)
    # B468: ffmpeg used to write straight onto ``target`` with ``-y``. It
    # truncates that file the moment it starts, so a render that was
    # stopped or that failed destroyed the video that was already there -
    # two of the user's videos disappeared that way. Render next to it and
    # only move it into place once ffmpeg has finished successfully; the
    # existing file is then never touched until there is a complete
    # replacement. Same directory, so the move is atomic.
    scratch = target.with_name(target.stem + SCRATCH_SUFFIX)
    if scratch.exists():
        _discard(scratch)
    # B530: the chain is built in order, and that order is the whole
    # point. First the silence in front (if the intro was shifted), then
    # the level, then the padding at the end so the outro silence is
    # right (B203). Up to v0.148.0 the delay was pasted on AFTER
    # loudnorm, and that is how three videos ended up with the picture
    # running seconds ahead of the sound.
    parts: list[str] = []
    if lead_padding > 0.0:
        channels = properties.channels or 2
        parts.append(ffmpeg_module.delay_filter(lead_padding, channels))
    # B456: every video came out at its own level, so at every song the
    # amplifier had to be touched. Measured first, then applied with
    # those numbers - a single pass has to guess as it goes and gets the
    # start of a song wrong. Fails silently: a level is a nicety, not a
    # reason to drop a render.
    if loudness_lufs is not None:
        measured = ffmpeg_module.measure_loudness(
            audio_path, loudness_lufs, true_peak_db)
        if measured is not None:
            reachable = ffmpeg_module.reachable_loudness(measured,
                                                         true_peak_db)
            logger.info(t("log_loudness_measured"), measured.integrated,
                        measured.true_peak, loudness_lufs, reachable)
            if reachable < loudness_lufs - 0.05:
                logger.info(t("log_loudness_limited"), loudness_lufs,
                            round(loudness_lufs - reachable, 1))
            parts.append(ffmpeg_module.loudnorm_filter(
                measured, loudness_lufs, true_peak_db))
    parts.append("apad")
    audio_filter = ",".join(parts)
    command = [
        executable, "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
        "-r", str(fps), "-i", "-",
        "-i", str(audio_path),
        "-t", f"{duration:.3f}",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "256k", "-af", audio_filter,
        # B273: version number in the video metadata, so that afterwards
        # (e.g. when testing) it can be traced with which KaraokeTool
        # version a file was made (``ffprobe -show_format``).
        "-metadata", f"comment=KaraokeTool v{__version__}",
        str(scratch),
    ]
    _LAYOUT_CACHE.clear()                       # B541
    _LAYOUT_ALIVE.clear()
    logger.info(t("log_render_started"),
                target.name, width, height, fps, duration)
    # B530: what was actually asked of ffmpeg. Without this line the
    # only way to find out why a render came out wrong was to guess at
    # it afterwards from the file.
    logger.debug(t("log_render_command"), " ".join(command))
    # Deze kan niet door proc.run: de render pompt zelf beelden in de
    # stdin van ffmpeg. Wel aanmelden, zodat Stop hem kan afschieten
    # (B356).
    process = subprocess.Popen(command, stdin=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               **proc.no_window_kwargs())
    proc.register(process)
    assert process.stdin is not None
    try:
        total_frames = int(duration * fps)
        # B541: the same picture is not drawn twice. The intro is one
        # still that used to be built two hundred and fifty times over,
        # the outro likewise, and between two sentences nothing moves
        # either - measured on the user's own render: 249 of 250 intro
        # frames byte-identical to their predecessor, 199 of 250 in the
        # outro and 99 of 250 in the text. What decides is not a rule
        # about time but the list of drawing calls the frame is built
        # out of (see :class:`_Ledger`), so a repeat is a repeat by
        # construction and never a guess.
        #
        # One frame is kept, not a stock of them: identical frames come
        # in RUNS, so the neighbour is the only one worth comparing
        # against, and a stock of 2.7 MB pictures is how a render eats a
        # machine alive.
        last_key = None
        last_bytes = b""
        reused = 0
        missed = 0
        for frame_index in range(total_frames):
            moment = frame_index / fps
            # B541: recording a frame costs about a tenth of drawing
            # one, which is a bargain in a still stretch and a loss in a
            # song that sings from beginning to end. So after a run of
            # misses the recording backs off - to a PAIR of frames in
            # every ten, because seeing that nothing moves takes two
            # frames next to each other. A still stretch is therefore
            # picked up within ten frames, and a song that has none
            # pays about one per cent.
            probe = (missed < _CACHE_PATIENCE
                     or frame_index % _CACHE_PROBE in (0, 1))
            key = _frame_key(moment, main_lines, first_text, outro_start,
                             width, height, font, title_font, logo_large,
                             title, palette, credit, credit_font,
                             background) if probe else None
            if key is not None and key == last_key:
                reused += 1
                missed = 0
            else:
                frame = _compose_frame(moment, main_lines,
                                       first_text, outro_start, width,
                                       height, font, title_font,
                                       logo_large, title, palette, credit,
                                       credit_font, background)
                last_bytes = frame.tobytes()
                # Without a key of its own this frame cannot be compared
                # against, and saying otherwise is how a stale picture
                # gets into a video.
                last_key = key
                missed += 1
            process.stdin.write(last_bytes)
            if progress is not None and frame_index % fps == 0:
                progress(moment, duration)
        if total_frames:
            logger.info(t("log_frames_reused"), reused, total_frames,
                        round(100.0 * reused / total_frames))
        process.stdin.close()
        process.wait()
    except BrokenPipeError as exc:
        process.wait()
        _discard(scratch)
        raise VideoError("ffmpeg brak de verbinding af: "
                         f"{_stderr(process)}") from exc
    except BaseException:
        # Anything else that can go wrong while pumping frames (a picture
        # that will not load, a write error that Windows does not report
        # as a broken pipe) must not leave half a file behind either.
        _discard(scratch)
        raise
    finally:
        proc.unregister(process)
    if process.returncode != 0:
        _discard(scratch)
        raise VideoError(f"ffmpeg faalde: {_stderr(process)}")
    # B530: the render checks its own result before it is put in place.
    # The picture was shifted forward by ``lead_padding`` and exactly
    # that much silence has to stand in front of the sound; if it does
    # not, the whole video runs out of step and that is invisible until
    # someone watches it to the end. It happened: three finished videos
    # ran up to 8.3 s ahead of their music. Better a render that refuses
    # than a video that lies.
    if lead_padding > 0.0:
        _check_lead_silence(scratch, lead_padding)
    try:
        os.replace(scratch, target)
    except OSError as exc:
        # On Windows this fails while the old video is open in a player.
        # The render itself did succeed, so say what is going on and
        # leave the finished file where the user can reach it.
        raise VideoError(t("err_video_in_use").format(
            target=target, scratch=scratch)) from exc
    logger.info(t("log_render_done"), target)
    return target


#: How much less silence than the shift of the picture is still
#: acceptable before the render is refused (B530). A tenth is below
#: what anyone hears and well above the rounding of a filter that works
#: in milliseconds.
LEAD_SILENCE_SLACK_S = 0.10


def _check_lead_silence(path: Path, expected: float) -> None:
    """Does the finished render start with the silence it should?

    Deliberately one-sided: only TOO LITTLE silence is a fault. What is
    measured here is the silence at the front of the finished file, and
    that is the shift of the picture PLUS whatever quiet the song opens
    with - the two touch, so the detector sees one stretch. On the
    user's own collection the difference ran from 0.2 to 0.4 s, and
    every one of those renders was right. Refusing on "more than
    expected" would therefore refuse exactly the healthy ones.

    Raises ``VideoError`` when there is demonstrably too little. Cannot
    measure it (no ffmpeg, an unreadable file)? Then nothing is claimed:
    a check that cannot run may not stop a render that is probably fine,
    but it does say so in the log.
    """
    measured = ffmpeg_module.leading_silence(path, look=expected + 5.0)
    if measured is None:
        logger.warning(t("log_lead_silence_unknown"), path.name)
        return
    if expected - measured > LEAD_SILENCE_SLACK_S:
        _discard(path)
        raise VideoError(t("err_lead_silence").format(
            expected=round(expected, 2), measured=round(measured, 2)))
    logger.info(t("log_lead_silence_ok"), round(measured, 2))


def _discard(path: Path) -> None:
    """Remove a half-finished render; never let that hide the real error."""
    try:
        path.unlink()
    except OSError:
        logger.warning(t("log_delete_failed"), path)


def _stderr(process: subprocess.Popen) -> str:
    if process.stderr is None:
        return "onbekende fout"
    return process.stderr.read().decode(errors="replace").strip()


def _load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a bold font; try common candidates."""
    candidates = ([font_path] if font_path else []) \
        + [str(_BUNDLED_FONT)] + list(_FONT_CANDIDATES)
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    logger.warning(t("log_no_truetype"))
    return ImageFont.load_default()  # type: ignore[return-value]


def _fit_title_font(font_path: str, text: str, max_width: int,
                    start_size: int) -> ImageFont.FreeTypeFont:
    """Choose the largest title font fitting on one line in ``max_width``.

    Starts at ``start_size`` and shrinks step by step; this keeps the
    (larger) title guaranteed on one line (B73).
    """
    size = max(10, start_size)
    while size > 10:
        font = _load_font(font_path, size=size)
        try:
            if not text or font.getlength(text) <= max_width:
                return font
        except (AttributeError, OSError):
            return font
        size -= 2
    return _load_font(font_path, size=10)


def _scale(image: Image.Image, target_height: int) -> Image.Image:
    ratio = target_height / image.height
    return image.resize((max(1, int(image.width * ratio)), target_height))


#: Number of vocal lines shown on screen at once (crowd does not count).
_VISIBLE_LINES = 3


class _Ledger:
    """Records what WOULD be drawn instead of drawing it (B541).

    The frame cache needs a key that says "this picture is the same as
    the previous one", and it has to be exact: a stale frame in a
    finished video is invisible until somebody watches it. Deriving such
    a key by copying the drawing rules into a second function is exactly
    how those two drift apart - the next person changes the drawing and
    not the copy, and then the render silently repeats a frame.

    So the key is not derived, it is RECORDED. The picture is built once
    with this object in the place of the drawing surface: every call
    lands in a list and nothing is rasterised. Two frames whose lists are
    equal were going to be built out of the same calls in the same
    order, and are therefore the same picture by construction. What it
    costs is the layout (the font measurements), not the drawing - and
    the drawing is the expensive half.

    It stands in for BOTH surfaces the render uses: the ``ImageDraw`` it
    draws on and the ``Image`` it pastes into.
    """

    __slots__ = ("width", "height", "calls")

    def __init__(self, width: int, height: int) -> None:
        self.width = int(width)
        self.height = int(height)
        self.calls: list = []

    # -- the ImageDraw side --------------------------------------------
    def text(self, xy, text, font=None, fill=None, stroke_width=0,
             stroke_fill=None, **rest) -> None:
        # No rounding. Pillow puts text on a subpixel position, so two
        # x-values in the same hundredth are not the same picture -
        # measured, 10.006 and 10.014 draw different pixels. Today every
        # coordinate that depends on the moment is a whole number, but
        # that is an invariant somebody can remove, and then a frame
        # would silently stay standing. Floats compare exactly.
        self.calls.append((
            "text", float(xy[0]), float(xy[1]),
            str(text), id(font), _colour(fill), int(stroke_width),
            _colour(stroke_fill), tuple(sorted(rest.items()))))

    def textlength(self, text, font=None, **rest) -> float:
        # A real number: the layout leans on it, and a wrong one would
        # make the recorded picture a different picture.
        return float(font.getlength(str(text))) if font is not None else 0.0

    # -- the Image side ------------------------------------------------
    def crop(self, box):
        self.calls.append(("crop",) + tuple(int(v) for v in box))
        return _CROPPED

    def paste(self, image, box=None, mask=None) -> None:
        # ``id`` and not just the size: a constant picture (the logo)
        # then costs nothing, and a picture made per frame gets a key of
        # its own instead of quietly passing for its predecessor.
        self.calls.append(("paste", tuple(box or ()), id(image),
                           getattr(image, "size", None), mask is not None))

    def key(self) -> tuple:
        return tuple(self.calls)


#: What :meth:`_Ledger.crop` hands back. It is only ever pasted back,
#: and what it holds follows from the calls that came before it.
_CROPPED = object()


def _colour(value):
    """A colour as something that can be compared and hashed."""
    return tuple(value) if isinstance(value, (list, tuple)) else value


def _new_frame(width, height, palette, background) -> Image.Image:
    """An empty picture with the background of this song."""
    if background is not None:
        return background.copy()
    return Image.new("RGB", (width, height), palette["background"])


def _eased_in(fraction: float) -> float:
    """Smoothstep for the cross-fade (B501): starts and ends quietly."""
    t = max(0.0, min(1.0, fraction))
    return t * t * (3.0 - 2.0 * t)


def _blend(first: Image.Image, second: Image.Image,
           share: float) -> Image.Image:
    """``second`` over ``first``, for ``share`` (B501)."""
    return Image.blend(first, second, max(0.0, min(1.0, share)))


def _title_frame(moment, outro_start, width, height, title, title_font,
                 logo_large, palette, credit, credit_font,
                 background, surface=None) -> Image.Image:
    """Logo + title + credit: the intro and the outro (B501).

    With a ``surface`` (B541) nothing is drawn: the calls are recorded
    on it and the picture is never rasterised.
    """
    frame = surface if surface is not None else _new_frame(
        width, height, palette, background)
    draw = surface if surface is not None else ImageDraw.Draw(frame)
    _paste_center(frame, logo_large, int(height * 0.12))
    if title:
        # End title (outro) in the 'sing-now' color; intro white (B72).
        title_key = "zang" if moment >= outro_start else "voor"
        _draw_centered(draw, title, title_font, width,
                       int(height * 0.68), palette[title_key],
                       outline=palette.get("outline_" + title_key),
                       stroke=_stroke_width(title_font))       # B487
    # Credit (artist - original title) only in the intro, not in the
    # outro (B168).
    if credit and credit_font is not None and moment < outro_start:
        _draw_centered(draw, credit, credit_font, width,
                       int(height * 0.80), palette["na"],
                       outline=palette.get("outline_na"),
                       stroke=_stroke_width(credit_font))      # B487
    return frame


def _text_frame(moment, vocal, width, height, font, title_font, palette,
                background, surface=None) -> Image.Image:
    """The picture with the sung text (B501).

    With a ``surface`` (B541) nothing is drawn; see :class:`_Ledger`.
    """
    frame = surface if surface is not None else _new_frame(
        width, height, palette, background)
    draw = surface if surface is not None else ImageDraw.Draw(frame)

    # Three vocal lines, stacked on their real height (B473).
    y_positions = (0.34, 0.56, 0.70)

    # B227/B268/B270/B272/B474: during an instrumental gap (>= GAP_MIN_S)
    # the 3-2-1 countdown has to go somewhere. It used to squeeze the
    # three lines and itself into four evenly spread positions, and with
    # a sentence that runs over two rows there was then too little room
    # left: the lines drew straight through one another. The countdown
    # now takes the PLACE of the line that has just been sung - that one
    # is done and the user does not need it any more - and the lines
    # still to come stay exactly where they always are.
    active_index = max(0, sum(1 for line in vocal
                              if line.start <= moment) - 1)
    gap_active = False
    if vocal and active_index + 1 < len(vocal):
        cur_end = vocal[active_index].end
        next_start = vocal[active_index + 1].start
        gap_active = (moment >= cur_end
                      and (next_start - cur_end) >= GAP_MIN_S)

    # B473: the fixed fractions are the place a line WANTS to have; a
    # sentence over two rows pushes the one below it further down. Only
    # downwards, so the familiar layout is kept as long as everything
    # fits on one row.
    def _height_of(index: int) -> int:
        if 0 <= index < len(vocal):
            return _line_text_height(vocal[index], font, width)
        return _row_height(font)

    def _stack(centre: int) -> dict[int, int]:
        """The place of every slot with ``centre`` as the active line."""
        tops: dict[int, int] = {}
        previous = None
        for slot in range(0, _VISIBLE_LINES):
            wanted = int(height * y_positions[slot])
            tops[slot] = wanted if previous is None else max(wanted, previous)
            previous = (tops[slot] + _height_of(centre + slot)
                        + _line_gap(font))
        # The outgoing line (slot -1) hangs above slot 0 on its own height.
        tops[-1] = tops[0] - (_height_of(centre - 1) + _line_gap(font))
        return tops

    def _place(tops: dict[int, int], slot: int) -> int:
        if slot in tops:
            return tops[slot]
        last = tops[_VISIBLE_LINES - 1]
        return last + (slot - _VISIBLE_LINES + 1) * (
            _row_height(font) + _line_gap(font))

    tops = _stack(active_index)

    def slot_y(slot: int) -> int:
        return _place(tops, slot)

    # B474: the countdown before the FIRST text of the song keeps its own
    # place - there is no sung line yet whose place it could take.
    number_y = slot_y(0) if gap_active else int(height * 0.18)
    # Is the countdown on screen right now? Only then does the line just
    # sung make way for it; during the rest of a long instrumental gap it
    # simply stays where it is instead of leaving an empty band.
    counting_down = False

    # Countdown 3-2-1 before the first vocals, as a separate line above
    # the text in the 'sing-now' color; not a lyric line itself (B101).
    if vocal:
        number = countdown_number(moment, vocal[0].start)
        if number is not None:
            _draw_centered(draw, str(number), title_font, width,
                           number_y, palette["zang"],
                           outline=palette.get("outline_zang"),
                           stroke=_stroke_width(title_font))

    # Instrumental gap: count down 3-2-1 to the next line, in the place
    # of the line that has just been sung (B474).
    if gap_active:
        next_start = vocal[active_index + 1].start
        number = countdown_number(moment, next_start)
        if number is not None:
            counting_down = True
            _draw_centered(draw, str(number), title_font, width,
                           number_y, palette["zang"],
                           outline=palette.get("outline_zang"),
                           stroke=_stroke_width(title_font))

    # B242/B473: the smooth shift. It used to be one distance for every
    # line (``slot_y(1) - slot_y(0)``), which was right as long as all
    # the slots were equally far apart. Now that a sentence over two rows
    # pushes the one below it further down, they are not - and one
    # distance for all made the line that had just been sung JUMP down
    # first and then glide up. Every line therefore starts where it
    # really stood: at the place of the slot below it.
    shift = 0.0
    previous_tops: dict[int, int] | None = None
    if not gap_active and active_index > 0:
        dt = moment - vocal[active_index].start
        if 0.0 <= dt < _LINE_TRANSITION_S:
            shift = _eased_out(dt / _LINE_TRANSITION_S)
            # B505: the stack of BEFORE the change. The movement used to
            # be worked out in the new stack alone ("go to the place of
            # the slot below you"), and with sentences of different
            # heights that mixes two stacks: at the start of the shift
            # the distance between two drawn lines was then smaller than
            # the height of the upper one, and the second row of a broken
            # sentence ran straight through the sentence under it.
            previous_tops = _stack(active_index - 1)
    # During the gap slot 0 makes way for the countdown at the moment it
    # appears (B474) and slot -1 drops out entirely; outside the gap slot -1 stays visible for
    # the smooth B242 transition.
    # B474: buiten het gat wordt slot -1 meegetekend voor de vloeiende
    # verschuiving (B242). Kwam de huidige regel NA een instrumentaal gat,
    # dan is de regel op slot -1 er tijdens dat gat uit gehaald om plaats
    # te maken voor de teller; die mag niet terugspringen op precies de
    # plek waar het cijfer stond.
    after_gap = (active_index > 0
                 and (vocal[active_index].start
                      - vocal[active_index - 1].end) >= GAP_MIN_S)
    first_slot = ((1 if counting_down else 0) if gap_active
                  else (0 if after_gap else -1))
    for slot in range(first_slot, _VISIBLE_LINES):
        index = active_index + slot
        if index < 0 or index >= len(vocal):
            continue
        # Every line walks from where it really stood (one slot lower in
        # the previous stack) to where it stands now.
        if shift and previous_tops is not None:
            was = _place(previous_tops, slot + 1)
            row_y = int(round(slot_y(slot) + shift * (was - slot_y(slot))))
        else:
            row_y = slot_y(slot)
        _draw_line(frame, draw, vocal[index], moment, width,
                   row_y, font,
                   active_slot=(slot == 0), palette=palette,
                   keep_sung=(index == len(vocal) - 1))
    return frame


def _compose_frame(moment, vocal, first_text,
                   outro_start, width, height, font, title_font,
                   logo_large, title, palette, credit="",
                   credit_font=None, background=None,
                   surface=None) -> Image.Image:
    """Build one video frame based on the moment in time.

    Intro (before the first text) and outro show logo + title + credit
    (artist/original title). During the vocals there is NO logo on
    screen; three vocal lines are visible (the active one coloured, the
    next two white). A crowd line simply runs along in that flow and is
    red (B475). An optional background image (B126) lies behind
    everything. On the two boundaries the pictures cross-fade (B501).
    """
    # B501: on the boundary both pictures are made and blended.
    if first_text - _INTRO_FADE_S <= moment < first_text:
        share = (moment - (first_text - _INTRO_FADE_S)) / _INTRO_FADE_S
        if surface is not None:
            # B541: on the boundary both pictures are recorded, and the
            # share along with them - it changes with every frame, so a
            # fading frame is never the same as the one before it.
            surface.calls.append(("blend", round(_eased_in(share), 6)))
            _title_frame(moment, outro_start, width, height, title,
                         title_font, logo_large, palette, credit,
                         credit_font, background, surface)
            return _text_frame(moment, vocal, width, height, font,
                               title_font, palette, background, surface)
        return _blend(
            _title_frame(moment, outro_start, width, height, title,
                         title_font, logo_large, palette, credit,
                         credit_font, background),
            _text_frame(moment, vocal, width, height, font,
                        title_font, palette, background),
            _eased_in(share))
    if outro_start <= moment < outro_start + _OUTRO_FADE_S:
        share = (moment - outro_start) / _OUTRO_FADE_S
        if surface is not None:
            surface.calls.append(("blend", round(_eased_in(share), 6)))
            _text_frame(outro_start - 0.001, vocal, width, height, font,
                        title_font, palette, background, surface)
            return _title_frame(moment, outro_start, width, height, title,
                                title_font, logo_large, palette, credit,
                                credit_font, background, surface)
        return _blend(
            _text_frame(outro_start - 0.001, vocal, width,
                        height, font, title_font, palette, background),
            _title_frame(moment, outro_start, width, height, title,
                         title_font, logo_large, palette, credit,
                         credit_font, background),
            _eased_in(share))
    if moment < first_text or moment >= outro_start:
        return _title_frame(moment, outro_start, width, height, title,
                            title_font, logo_large, palette, credit,
                            credit_font, background, surface)
    return _text_frame(moment, vocal, width, height, font, title_font,
                       palette, background, surface)


def _frame_key(moment, vocal, first_text, outro_start, width, height,
               font, title_font, logo_large, title, palette, credit="",
               credit_font=None, background=None) -> tuple:
    """What the picture at ``moment`` is going to be built out of (B541).

    Runs the whole composition with a :class:`_Ledger` in the place of
    the drawing surface. Equal keys mean equal pictures - not because
    somebody worked out which quantities matter, but because the same
    calls in the same order draw the same thing.
    """
    ledger = _Ledger(width, height)
    _compose_frame(moment, vocal, first_text, outro_start, width, height,
                   font, title_font, logo_large, title, palette, credit,
                   credit_font, background, surface=ledger)
    return ledger.key()


def _disp(text: str) -> str:
    """Display text for the render: underscore -> space (B252).

    An underscore joins words in the karaoke text into one syllable
    (e.g. ``'k_heb``); internally the underscore stays as a marker, but on
    screen there should be a space (``'k heb``). Underscores are never a
    leading space or a punctuation mark, so word-boundary and comma
    detection keep working on the raw text."""
    return text.replace("_", " ")


def _wrap_syllables(syllables, font, max_width):
    """Distribute the syllables over 1 or 2 rows so that they fit.

    Splits into ~two equal parts at a word boundary close to the middle.
    A comma is only used as a split point if it ALSO lies close to the
    middle (so not a comma at the start of the sentence); otherwise just
    the nearest word boundary (B120). Breaking on a comma is therefore
    not mandatory.
    """
    def row_width(items):
        return sum(font.getlength(_disp(s.text)) for s in items)

    if len(syllables) < 2 or row_width(syllables) <= max_width:
        return [list(syllables)]
    n = len(syllables)
    middle = n / 2.0
    # Tolerance: ~1-2 words around the middle (min 1 syllable).
    tol = max(1, round(n * 0.25))
    comma_points = [i + 1 for i, s in enumerate(syllables)
                    if s.text.rstrip().endswith(",") and 0 < i + 1 < n]
    word_points = [i for i, s in enumerate(syllables)
                   if s.text.startswith(" ") and 0 < i < n]
    comma_near = [p for p in comma_points if abs(p - middle) <= tol]
    if comma_near:
        split = min(comma_near, key=lambda i: abs(i - middle))
    elif word_points:
        split = min(word_points, key=lambda i: abs(i - middle))
    else:
        split = n // 2
    return [list(syllables[:split]), list(syllables[split:])]


#: Text may fill at most this fraction of the width (B102, 85% fit).
_TEXT_WIDTH_FRAC = 0.85


def _fit_body_font(font_path: str, lines, width: int,
                   start_size: int) -> "ImageFont.FreeTypeFont":
    """Choose the largest body font at which every line fits within 85%
    of the width (in at most two rows). Shrinks if needed down to a
    lower bound (B102)."""
    max_width = width * _TEXT_WIDTH_FRAC
    sentences = [line for line in lines if _sung_syllables(line)]
    minimum = max(12, int(start_size * 0.5))
    for size in range(int(start_size), minimum - 1, -1):
        font = _load_font(font_path, size=size)
        if all(fits_on_screen(_sung_syllables(line), font, max_width)
               for line in sentences):
            return font
    return _load_font(font_path, size=minimum)


def fits_on_screen(syllables, font, max_width) -> bool:
    """Does the line fit in at most two rows within ``max_width``?"""
    def row_width(items):
        return sum(font.getlength(_disp(s.text)) for s in items)

    rows = _wrap_syllables(syllables, font, max_width)
    return all(row_width(row) <= max_width for row in rows)


def overflowing_lines(timed_lines, width, height, font_path="") -> list[str]:
    """Return the lines that (even after comma splitting) do not fit."""
    font = _load_font(font_path, size=int(height * 0.06))
    max_width = width * _TEXT_WIDTH_FRAC
    result = []
    for line in timed_lines:
        if line.syllables and not fits_on_screen(
                _sung_syllables(line), font, max_width):
            result.append(_disp(line.text))
    return result


def _rows_of(line, font, width: int):
    """The rows of one sentence and the y of each, once per render."""
    rows = _wrap_syllables(_sung_syllables(line), font,
                           width * _TEXT_WIDTH_FRAC)
    return rows, _row_tops(rows, font)   # B476


def _draw_line(image, draw, line: TimedLine, moment: float, width: int,
               y: int, font, active_slot: bool, palette=None,
               keep_sung: bool = False) -> None:
    """Draw one line; colors per syllable on the vocal onset.

    ``keep_sung``: keep the line on the vocal color after its end instead
    of greying out (for the last sentence, until the outro, B204)."""
    palette = palette or _DEFAULT_COLORS
    # B541: the same break and the same row heights for every frame of
    # this line; only the colours move.
    rows, row_tops = _cached(
        ("rows", id(line), id(font), int(width)),
        lambda: _rows_of(line, font, width), line, font)
    for row_index, row in enumerate(rows):
        total = sum(font.getlength(_disp(s.text)) for s in row)
        x = (width - total) / 2
        row_y = y + row_tops[row_index]
        for syllable in row:
            length = font.getlength(_disp(syllable.text))
            # Inline pause: dots that light up on the average beat (B107).
            if karaoke_text.is_pause(syllable.text):
                # Pause dots always in the normal vocal color, also
                # within a crowd context (B179a).
                _draw_pause(draw, x, row_y, length, syllable, moment,
                            line.end, active_slot, palette["zang"], palette,
                            font, stroke=_stroke_width(font))   # B487
                x += length
                continue
            # Color per syllable: inline crowd (or whole crowd line) red,
            # otherwise vocal green (B179a).
            sung_color = (palette["crowd"]
                          if (line.crowd or getattr(syllable, "crowd", False))
                          else palette["zang"])
            # B447: the colour no longer flips per piece but sweeps
            # THROUGH it, from left to right, in step with the time.
            # Flipping whole pieces was jerky, and the more so the longer
            # the piece: a held vowel stood still for two seconds and
            # then jumped over in one frame. The sweep gives a steady
            # wipe, and only the piece being sung right now needs the
            # extra work - everything before it is fully sung, everything
            # after it fully unsung.
            # B477: the outline follows the letter colour, so on the
            # active line it changes along WITH the sweep: the sung half
            # carries the outline of the sing colour, the half still to
            # come that of the waiting colour. Only the active line gets
            # one - a sentence that has been sung no longer has to stand
            # out against the background.
            sung_key = ("crowd" if (line.crowd
                                    or getattr(syllable, "crowd", False))
                        else "zang")
            if not active_slot:
                # B483: a line that is not active was ALWAYS drawn in the
                # waiting colour, so the sentence that had just been sung
                # turned white again the moment it moved up to the top
                # slot. White means "still to come"; what is behind us is
                # grey. Since B473 that line sits right above the active
                # one instead of tucked away at the top of the picture,
                # so it is now plain to see.
                # B487: and it gets an outline too. At B477 I read "the
                # sentence that has been sung no longer has to stand out"
                # as "no outline there", and against a background picture
                # exactly those lines fall away. Every line, always.
                done = moment >= line.end
                past_key = "na" if done else "voor"
                if not done and sung_key == "crowd":
                    past_key = "crowd"
                past = palette[past_key]
                before, after, share = past, past, 0.0
                before_edge = after_edge = palette.get("outline_" + past_key)
            elif moment >= line.end:
                done_key = sung_key if keep_sung else "na"
                done = sung_color if keep_sung else palette["na"]
                before, after, share = done, done, 1.0
                before_edge = after_edge = palette.get("outline_" + done_key)
            else:
                before, after = sung_color, palette["voor"]
                share = _sung_share(syllable, moment)
                before_edge = palette.get("outline_" + sung_key)
                after_edge = palette.get("outline_voor")
            bold = bool(getattr(syllable, "stress", False))
            _draw_swept(image, draw, x, row_y, _disp(syllable.text), font,
                        before, after, share, bold,
                        before_edge, after_edge, _stroke_width(font))
            x += length


def _eased_out(fraction: float) -> float:
    """How much of the shift is still to come, at this point in it (B448).

    Was ``(1 - t) ** 2``: that lands softly but STARTS at full speed, so
    the very first frame of a line shift was a jolt however high the
    frame rate. This is the smoothstep the other way round - it brakes
    at both ends, so the movement begins as quietly as it ends.

    ``1.0`` at the start of the shift (the line still stands a whole slot
    lower), ``0.0`` when it is over.
    """
    t = max(0.0, min(1.0, fraction))
    return 1.0 - t * t * (3.0 - 2.0 * t)


def _sung_share(syllable, moment: float) -> float:
    """How much of this piece has been sung at ``moment`` (B447).

    ``0.0`` before it starts, ``1.0`` once it is past. In between the
    plain time fraction: a piece is sung at an even pace, so the colour
    should cross it at an even pace too.
    """
    start, end = float(syllable.start), float(syllable.end)
    if moment <= start:
        return 0.0
    span = end - start
    if span <= 0:
        return 1.0
    return max(0.0, min(1.0, (moment - start) / span))


def _draw_swept(image, draw, x: float, row_y: float, text: str, font,
                before, after, share: float, bold: bool = False,
                before_edge=None, after_edge=None, stroke: int = 0) -> None:
    """Draw one piece, the left ``share`` of it in ``before`` (B447).

    Pillow cannot colour half a letter, and it has no clip region
    either. So the piece is drawn twice: first entirely in the "not yet"
    colour, then entirely in the "sung" colour, and the strip to the
    RIGHT of the sweep line is put back from the first version. The
    result is one letter in two colours with the boundary exactly on the
    sweep position.

    Only the piece on the boundary pays for this. A share of 0 or 1 - so
    every other piece on screen - takes the plain single draw.

    ``bold`` is the stress accent (B151): the same text once more, one
    pixel to the right, so the line width does not change.

    ``before_edge``/``after_edge`` are the outline colours (B477); they
    are swept along with the fill, so the boundary stays one line and
    not a seam. The strip that is put back is widened by the outline,
    otherwise the outline of the sung half would stay standing over the
    half still to come.
    """
    def _text(fill, edge) -> None:
        width_of_edge = stroke if edge is not None else 0
        draw.text((x, row_y), text, font=font, fill=fill,
                  stroke_width=width_of_edge, stroke_fill=edge)
        if bold:
            draw.text((x + 1, row_y), text, font=font, fill=fill,
                      stroke_width=width_of_edge, stroke_fill=edge)

    if share <= 0.0:
        _text(after, after_edge)
        return
    if share >= 1.0:
        _text(before, before_edge)
        return
    width = font.getlength(text)
    ascent, descent = font.getmetrics()
    margin = stroke + 3
    left = max(0, int(x + width * share))
    top = max(0, int(row_y) - margin)
    right = min(image.width, int(x + width) + margin)
    bottom = min(image.height, int(row_y) + ascent + descent + margin)

    _text(after, after_edge)
    unsung = (image.crop((left, top, right, bottom))
              if right > left and bottom > top else None)
    _text(before, before_edge)
    if unsung is not None:
        image.paste(unsung, (left, top))


def _draw_pause(draw, x: float, row_y: float, length: float, syllable,
                moment: float, line_end: float, active_slot: bool,
                sung_color, palette, font, dots: int = 3,
                stroke: int = 0) -> None:
    """Draw an inline pause as ``dots`` dots that light up one by one.

    The dots light up proportionally over the pause duration ('average
    beat'): before the pause all dim, during the pause one by one in the
    vocal color, and after the line in the after color.

    B487: with an outline, like the letters around them - they stood
    without one against a background picture.
    """
    span = max(1e-6, syllable.end - syllable.start)
    fraction = (moment - syllable.start) / span
    step = max(length / dots, font.getlength("."))
    keys = {id(palette[key]): key for key in ("voor", "na", "zang", "crowd")
            if key in palette}
    for k in range(dots):
        if not active_slot and moment >= line_end:
            # B498: the line above the active one has been sung, so its
            # dots are grey too - white means "still to come".
            color, key = palette["na"], "na"
        elif not active_slot or moment < syllable.start:
            color, key = palette["voor"], "voor"
        elif moment >= line_end:
            color, key = palette["na"], "na"
        elif (k + 1) / dots <= fraction:
            color, key = sung_color, keys.get(id(sung_color), "zang")
        else:
            color, key = palette["voor"], "voor"
        edge = palette.get("outline_" + key)
        draw.text((x + k * step, row_y), ".", font=font, fill=color,
                  stroke_width=(stroke if edge is not None else 0),
                  stroke_fill=edge)


def _load_background(path: str, width: int, height: int
                     ) -> Image.Image | None:
    """Load a background image and center-crop it to the video
    format (B126). ``None`` if there is no path or on a read error."""
    if not path:
        return None
    try:
        image = Image.open(path).convert("RGB")
    except OSError:
        logger.warning(t("log_background_unreadable"), path)
        return None
    scale = max(width / image.width, height / image.height)
    new = image.resize((max(1, int(image.width * scale)),
                          max(1, int(image.height * scale))))
    left = (new.width - width) // 2
    top = (new.height - height) // 2
    return new.crop((left, top, left + width, top + height))


def _paste_center(frame: Image.Image, image: Image.Image, y: int) -> None:
    x = (frame.width - image.width) // 2
    frame.paste(image, (x, y), image)


def _draw_centered(draw, text: str, font, width: int, y: int,
                   color, outline=None, stroke: int = 0) -> None:
    length = draw.textlength(text, font=font)
    draw.text(((width - length) / 2, y), text, font=font, fill=color,
              stroke_width=(stroke if outline is not None else 0),
              stroke_fill=outline)
