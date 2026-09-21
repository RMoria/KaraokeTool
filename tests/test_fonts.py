"""Tests for reading the fonts that ship with the program (B102)."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules import fonts


def test_display_name_variants() -> None:
    """File names turn into tidy display names."""
    assert fonts.display_name("BebasNeue-Regular.ttf") == "Bebas Neue"
    assert fonts.display_name("ArchivoBlack-Regular.ttf") == "Archivo Black"
    assert fonts.display_name("Baloo2[wght].ttf") == "Baloo 2"
    assert fonts.display_name("Oswald[wght].ttf") == "Oswald"
    assert fonts.display_name("DejaVuSans-Bold.ttf") == "Deja Vu Sans"


def test_available_fonts_reads_the_folder(tmp_path: Path) -> None:
    """Only .ttf and .otf are found, sorted by display name."""
    (tmp_path / "Anton-Regular.ttf").write_bytes(b"x")
    (tmp_path / "BebasNeue-Regular.ttf").write_bytes(b"x")
    (tmp_path / "leesmij.txt").write_text("geen font", encoding="utf-8")
    found = fonts.available_fonts(tmp_path)
    names = [item_name for item_name, _ in found]
    assert names == ["Anton", "Bebas Neue"]
    assert all(path.endswith(".ttf") for _, path in found)


def test_available_fonts_empty_folder(tmp_path: Path) -> None:
    """A folder that does not exist gives an empty list, not an error."""
    assert fonts.available_fonts(tmp_path / "bestaat_niet") == []


def test_the_bundle_contains_fonts() -> None:
    """The folder assets/fonts holds the fonts install.bat fetches.

    Skipped as long as they are not there yet (B542). In a fresh copy of
    the source DejaVu is the only one that comes along - the rest is
    fetched from Google Fonts by `install.bat`. Turning red would then
    say nothing about the code, only that the install has not run.
    """
    names = {item_name for item_name, _ in fonts.available_fonts()}
    if names <= {"Deja Vu Sans"}:
        pytest.skip("extra fonts not fetched yet; run install.bat")
    assert "Bebas Neue" in names
    assert "Anton" in names
