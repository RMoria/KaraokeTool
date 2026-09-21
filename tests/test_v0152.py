"""Tests for v0.152.0.

B541 - the same frame is not drawn twice. The render loop builds every
frame DRY first (a ledger of drawing orders instead of pixels) and
reuses the previous bytes when those orders are equal. On top of that
the layout of a line - how it breaks over rows and how tall it is - is
worked out once per render instead of fifty times a second.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image                                 # noqa: E402

from modules import video                             # noqa: E402
from modules.timing import Syllable, TimedLine        # noqa: E402


def _line(index, text, start, end, crowd=False):
    words = text.split()
    step = (end - start) / len(words)
    return TimedLine(
        index=index, text=text, crowd=crowd, block=0, quality="high",
        syllables=tuple(
            Syllable(("" if k == 0 else " ") + w,
                     start + k * step, start + (k + 1) * step)
            for k, w in enumerate(words)))


@pytest.fixture
def song():
    """A song with everything in it: an intro, a long line over two
    rows, a sing-along line, an instrumental gap with a countdown, and
    an outro - so both crossfades as well."""
    lines = [
        _line(0, "een twee drie vier vijf zes zeven acht negen tien elf",
              12.0, 15.5),
        _line(1, "vijf zes zeven acht", 16.0, 19.0),
        _line(2, "roep maar mee", 19.5, 21.0, crowd=True),
        _line(3, "negen tien elf twaalf", 30.0, 33.0),
        _line(4, "dertien veertien", 34.0, 36.0),
    ]
    font = video._load_font("", 26)
    title_font = video._load_font("", 34)
    logo = Image.new("RGBA", (60, 60), (0, 200, 0, 255))
    return lines, (lines, 7.0, 40.0, 240, 135, font, title_font, logo,
                   "Titel", video._DEFAULT_COLORS, "naar: X", font, None)


def _moments(fps=25, until=44.0):
    return [i / fps for i in range(int(until * fps))]


# --------------------------------------------------------------------------
# The promise: an equal key means an equal frame
# --------------------------------------------------------------------------

def test_an_equal_key_means_an_equal_frame(song) -> None:
    """This is the whole agreement the reuse rests on, and the reason
    the key is RECORDED and not rebuilt: if anything about the drawing
    ever changes, this test falls over."""
    _lines, args = song
    video._LAYOUT_CACHE.clear()
    previous_key = None
    previous_bytes = None
    checked = 0
    for moment in _moments():
        key = video._frame_key(moment, *args)
        frame = video._compose_frame(moment, *args).tobytes()
        if key == previous_key:
            assert frame == previous_bytes, f"moment {moment}"
            checked += 1
        previous_key, previous_bytes = key, frame
    assert checked > 100, "too few equal frames to say anything"


def test_the_whole_render_comes_out_the_same(song) -> None:
    """With and without reuse, byte for byte the same, including the
    fallback rule that no longer records every frame."""
    _lines, args = song
    video._LAYOUT_CACHE.clear()
    without = [video._compose_frame(m, *args).tobytes() for m in _moments()]
    video._LAYOUT_CACHE.clear()
    with_reuse = []
    key = None
    last = b""
    misses = 0
    for number, moment in enumerate(_moments()):
        look = (misses < video._CACHE_PATIENCE
                or number % video._CACHE_PROBE in (0, 1))
        now = video._frame_key(moment, *args) if look else None
        if now is not None and now == key:
            misses = 0
        else:
            last = video._compose_frame(moment, *args).tobytes()
            key = now
            misses += 1
        with_reuse.append(last)
    assert with_reuse == without


def test_there_really_is_something_to_reuse(song) -> None:
    """Otherwise the test above proves nothing."""
    _lines, args = song
    video._LAYOUT_CACHE.clear()
    keys = [video._frame_key(m, *args) for m in _moments()]
    equal = sum(1 for a, b in zip(keys, keys[1:]) if a == b)
    assert equal > 0.4 * len(keys)


# --------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------

def test_the_intro_is_a_still_frame(song) -> None:
    _lines, args = song
    assert video._frame_key(1.0, *args) == video._frame_key(4.0, *args)


def test_something_does_move_during_the_singing(song) -> None:
    _lines, args = song
    assert video._frame_key(13.0, *args) != video._frame_key(13.04, *args)


def test_a_crossfade_is_never_twice_the_same(song) -> None:
    """During a crossfade the blend changes every frame; without that
    blend in the key half a transition would stay put."""
    _lines, args = song
    # the intro crossfade runs from 6.5 to 7.0 s
    inside = [video._frame_key(6.55 + k * 0.02, *args) for k in range(8)]
    assert len(set(inside)) == len(inside)


def test_the_ledger_draws_nothing() -> None:
    """Otherwise the key costs as much as the frame itself."""
    ledger = video._Ledger(320, 180)
    font = video._load_font("", 20)
    ledger.text((1.0, 2.0), "hallo", font=font, fill=(1, 2, 3))
    assert ledger.width == 320 and ledger.key()[0][0] == "text"
    assert ledger.textlength("hallo", font=font) > 0


def test_two_different_colours_give_two_keys() -> None:
    ledger = video._Ledger(10, 10)
    font = video._load_font("", 20)
    ledger.text((0, 0), "x", font=font, fill=(255, 0, 0))
    first = ledger.key()
    second = video._Ledger(10, 10)
    second.text((0, 0), "x", font=font, fill=(0, 255, 0))
    assert first != second.key()


# --------------------------------------------------------------------------
# The layout of a line, once per render
# --------------------------------------------------------------------------

def test_the_layout_of_a_line_is_remembered(song) -> None:
    lines, args = song
    video._LAYOUT_CACHE.clear()
    font = args[5]
    first = video._line_text_height(lines[0], font, 240)
    assert video._LAYOUT_CACHE
    again = video._line_text_height(lines[0], font, 240)
    assert first == again


def test_another_width_gets_its_own_layout(song) -> None:
    lines, args = song
    video._LAYOUT_CACHE.clear()
    font = args[5]
    narrow = video._line_text_height(lines[0], font, 200)
    wide = video._line_text_height(lines[0], font, 2000)
    assert narrow >= wide          # narrow breaks over two rows
    assert len(video._LAYOUT_CACHE) == 2


def test_the_layout_does_not_carry_into_the_next_render() -> None:
    """The cache is keyed on line objects of THIS render; leaving it
    would mean a next song gets the rows of the previous one."""
    import inspect
    source = inspect.getsource(video.render_video)
    assert "_LAYOUT_CACHE.clear()" in source


# --------------------------------------------------------------------------
# The fallback rule
# --------------------------------------------------------------------------

def test_a_real_render_is_equal_with_and_without_reuse(
        tmp_path, monkeypatch) -> None:
    """The test that really pins down this round's risk: render the same
    video twice, once with every frame drawn, and compare the frame
    stream. A source check with ``inspect`` stays green on a real fault;
    this one does not."""
    import subprocess

    import numpy as np

    from modules import ffmpeg
    if not ffmpeg.is_available():
        pytest.skip("ffmpeg not available")
    from modules.audio import save_wav
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    rate = 22_050
    tone = (0.3 * np.sin(2 * np.pi * 220
                         * np.arange(12 * rate) / rate)).astype("float32")
    audio = tmp_path / "karaoke.wav"
    save_wav(audio, np.stack([tone, tone], axis=1), rate)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (120, 60), (60, 176, 67, 255)).save(logo)
    lines = generate_skeleton(
        (TextLine(0, "Kedeng Kedeng", False), TextLine(1, "La-la-la", True)),
        {0: (6.0, 8.0), 1: (9.0, 11.0)})

    def raw(path):
        done = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
        return done.stdout

    with_reuse = video.render_video(lines, audio, logo, "Testlied",
                                    tmp_path / "met.mp4", width=160,
                                    height=90, fps=10)
    # No key means no reuse: every frame is drawn.
    monkeypatch.setattr(video, "_frame_key", lambda *a, **k: None)
    without = video.render_video(lines, audio, logo, "Testlied",
                                 tmp_path / "zonder.mp4", width=160,
                                 height=90, fps=10)
    assert raw(with_reuse) == raw(without)


def test_two_renders_in_a_row_share_no_layout(tmp_path) -> None:
    """1.5.12 renders twenty-one videos in a row in the same process;
    the layout cache is keyed on line objects of one render."""
    import numpy as np

    from modules import ffmpeg
    if not ffmpeg.is_available():
        pytest.skip("ffmpeg not available")
    from modules.audio import save_wav
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton

    rate = 22_050
    tone = (0.3 * np.sin(2 * np.pi * 220
                         * np.arange(12 * rate) / rate)).astype("float32")
    audio = tmp_path / "karaoke.wav"
    save_wav(audio, np.stack([tone, tone], axis=1), rate)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (120, 60), (60, 176, 67, 255)).save(logo)
    first = generate_skeleton(
        (TextLine(0, "Kedeng Kedeng", False),), {0: (6.0, 8.0)})
    second = generate_skeleton(
        (TextLine(0, "Een veel langere zin die over twee rijen breekt",
                  False),), {0: (6.0, 8.0)})
    video.render_video(first, audio, logo, "Een", tmp_path / "een.mp4",
                       width=160, height=90, fps=10)
    heights_after_first = dict(video._LAYOUT_CACHE)
    video.render_video(second, audio, logo, "Twee", tmp_path / "twee.mp4",
                       width=160, height=90, fps=10)
    # Nothing from the first render is left in the second one's cache.
    assert not (set(heights_after_first) & set(video._LAYOUT_CACHE))


def test_without_a_key_nothing_is_reused() -> None:
    """A frame that was not recorded has no key, and then nothing may be
    compared against it - that is exactly how an old frame ends up in a
    video."""
    import inspect
    source = inspect.getsource(video.render_video)
    # The bytes and the key are set together in one place; if there is
    # ever a path where only the bytes change, an old key belongs to a
    # new frame.
    assert source.count("last_bytes = frame.tobytes()") == 1
    assert source.count("last_key = key") == 1
    assert "if key is not None and key == last_key:" in source


def test_the_fallback_looks_in_pairs() -> None:
    """Seeing that nothing moves takes two frames side by side; one
    frame in ten never finds a second to compare with."""
    import inspect
    source = inspect.getsource(video.render_video)
    assert "frame_index % _CACHE_PROBE in (0, 1)" in source
