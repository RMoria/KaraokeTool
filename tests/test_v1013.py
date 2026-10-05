"""v1.0.13: the smaller repairs of this round.

B577 - the very first line is on the active slot before it has begun,
and a crowd line stood white there during the whole lead-in while it is
red everywhere else before it is sung.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from modules import video
from modules.timing import Syllable, TimedLine


def _colours_drawn(monkeypatch, line, moment, active=True):
    seen = []

    def swept(image, draw, x, y, text, font, before, after, share, *rest):
        seen.append((text, before, after, share))

    monkeypatch.setattr(video, "_draw_swept", swept)
    image = Image.new("RGB", (640, 360))
    video._draw_line(image, ImageDraw.Draw(image), line, moment, 640, 100,
                     ImageFont.load_default(), active_slot=active)
    return seen


def _line(crowd):
    return TimedLine(index=0, text="ja la", crowd=crowd, syllables=(
        Syllable("ja", 5.0, 5.5), Syllable(" la", 5.5, 6.0)))


def test_a_crowd_line_waits_red_also_on_the_active_slot(monkeypatch):
    colours = video._DEFAULT_COLORS
    early = _colours_drawn(monkeypatch, _line(crowd=True), moment=2.0)
    assert early and all(before == after == colours["crowd"]
                         for _t, before, after, _s in early)
    # In the next slot it looked the same all along.
    waiting = _colours_drawn(monkeypatch, _line(crowd=True), moment=2.0,
                             active=False)
    assert [c[1:] for c in waiting] == [c[1:] for c in early]


def test_once_sung_the_crowd_line_sweeps_over_red(monkeypatch):
    """v1.0.14 (B596): the sweep is the ordinary singing colour, over red
    instead of over white; tests/test_v1015.py holds the rest."""
    colours = video._DEFAULT_COLORS
    during = _colours_drawn(monkeypatch, _line(crowd=True), moment=5.25)
    text, before, after, share = during[0]
    assert before == colours["zang"] and after == colours["crowd"]
    assert 0.0 < share < 1.0


def test_an_ordinary_line_before_it_begins_stays_white(monkeypatch):
    colours = video._DEFAULT_COLORS
    early = _colours_drawn(monkeypatch, _line(crowd=False), moment=2.0)
    assert all(before == after == colours["voor"]
               for _t, before, after, _s in early)
