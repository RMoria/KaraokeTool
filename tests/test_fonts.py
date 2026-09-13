"""Tests voor het uitlezen van meegeleverde lettertypen (B102)."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules import fonts


def test_display_name_varianten() -> None:
    """Bestandsnamen worden nette weergavenamen."""
    assert fonts.display_name("BebasNeue-Regular.ttf") == "Bebas Neue"
    assert fonts.display_name("ArchivoBlack-Regular.ttf") == "Archivo Black"
    assert fonts.display_name("Baloo2[wght].ttf") == "Baloo 2"
    assert fonts.display_name("Oswald[wght].ttf") == "Oswald"
    assert fonts.display_name("DejaVuSans-Bold.ttf") == "Deja Vu Sans"


def test_available_fonts_leest_map(tmp_path: Path) -> None:
    """Alleen .ttf/.otf worden gevonden, gesorteerd op weergavenaam."""
    (tmp_path / "Anton-Regular.ttf").write_bytes(b"x")
    (tmp_path / "BebasNeue-Regular.ttf").write_bytes(b"x")
    (tmp_path / "leesmij.txt").write_text("geen font", encoding="utf-8")
    found = fonts.available_fonts(tmp_path)
    names = [item_name for item_name, _ in found]
    assert names == ["Anton", "Bebas Neue"]
    assert all(path.endswith(".ttf") for _, path in found)


def test_available_fonts_lege_map(tmp_path: Path) -> None:
    """Een niet-bestaande map geeft een lege lijst (geen fout)."""
    assert fonts.available_fonts(tmp_path / "bestaat_niet") == []


def test_bundel_bevat_fonts() -> None:
    """De map assets/fonts bevat de lettertypen die install.bat ophaalt.

    Overgeslagen zolang ze er nog niet staan (B542). In een verse kopie
    van de broncode is DejaVu de enige die meekomt - de rest wordt door
    `install.bat` bij Google Fonts opgehaald. Rood worden zegt dan niets
    over de code, alleen dat de installatie nog niet gedraaid heeft.
    """
    names = {item_name for item_name, _ in fonts.available_fonts()}
    if names <= {"Deja Vu Sans"}:
        pytest.skip("extra lettertypen nog niet opgehaald; draai install.bat")
    assert "Bebas Neue" in names
    assert "Anton" in names
