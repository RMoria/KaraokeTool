"""Tests voor v0.89.0-fix (B271: bestandsnaam-achtervoegsel voor
niet-standaard videorenders, zodat meerdere varianten naast elkaar kunnen
bestaan zonder elkaar te overschrijven)."""
from __future__ import annotations


def test_standaardcombinatie_geen_achtervoegsel() -> None:
    """Karaoke-muziek + karaoketekst (de standaard) levert de kale
    bestandsnaam op - geen wijziging in bestaand gedrag."""
    from modules.pipeline import render_filename_suffix

    assert render_filename_suffix("karaoke", "karaoke") == ""


def test_afwijkende_combinaties_krijgen_muziek_dan_tekst_code() -> None:
    """Achtervoegsel is ``_<muziek>_<tekst>`` met 3-letter-codes; muziek
    eerst, tekst tweede (zoals gevraagd)."""
    from modules.pipeline import render_filename_suffix

    assert render_filename_suffix("vocals", "original") == "_voc_ori"
    assert render_filename_suffix("original", "karaoke") == "_ori_kar"
    assert render_filename_suffix("vocals", "karaoke") == "_voc_kar"
    assert render_filename_suffix("karaoke", "original") == "_kar_ori"


def test_demucs_code_voor_toekomstig_gebruik() -> None:
    """Het 'demucs'-codepad in _render_audio (niet in de GUI-dialoog, maar
    wel bestaand) krijgt ook een nette 3-letter-code."""
    from modules.pipeline import render_filename_suffix

    assert render_filename_suffix("demucs", "original") == "_dem_ori"


def test_onbekende_bron_valt_terug_op_eerste_3_letters() -> None:
    """Een onbekende bron (zou niet via de GUI moeten voorkomen) crasht niet
    maar valt terug op de eerste 3 letters van de brontekst zelf."""
    from modules.pipeline import render_filename_suffix

    assert render_filename_suffix("onbekend", "karaoke") == "_onb_kar"
