"""Tests for the v0.89.0 fix (B271: a file-name suffix for non-standard
video renders, so that several variants can sit side by side without
overwriting each other)."""
from __future__ import annotations


def test_the_standard_combination_gets_no_suffix() -> None:
    """Karaoke music plus karaoke text - the standard - gives the bare
    file name; no change to existing behaviour."""
    from modules.pipeline import render_filename_suffix

    assert render_filename_suffix("karaoke", "karaoke") == ""


def test_other_combinations_get_a_music_then_text_code() -> None:
    """The suffix is ``_<music>_<text>`` in three-letter codes: music
    first, text second, as asked for."""
    from modules.pipeline import render_filename_suffix

    assert render_filename_suffix("vocals", "original") == "_voc_ori"
    assert render_filename_suffix("original", "karaoke") == "_ori_kar"
    assert render_filename_suffix("vocals", "karaoke") == "_voc_kar"
    assert render_filename_suffix("karaoke", "original") == "_kar_ori"


def test_the_demucs_code_for_future_use() -> None:
    """The 'demucs' path in _render_audio - not in the GUI dialog, but
    there all the same - gets a proper three-letter code too."""
    from modules.pipeline import render_filename_suffix

    assert render_filename_suffix("demucs", "original") == "_dem_ori"


def test_an_unknown_source_falls_back_to_three_letters() -> None:
    """An unknown source - the GUI should never produce one - does not
    crash but falls back on the first three letters of the source text
    itself."""
    from modules.pipeline import render_filename_suffix

    assert render_filename_suffix("onbekend", "karaoke") == "_onb_kar"
