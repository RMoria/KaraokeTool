"""Tests voor de vertaallaag."""

from __future__ import annotations

from modules import translations


def test_default_and_switch() -> None:
    translations.set_language("nl")
    assert translations.current_language() == "nl"
    assert translations.t("tab_video") == "Karaokevideo"
    translations.set_language("en")
    assert translations.t("tab_video") == "Karaoke video"
    translations.set_language("nl")  # reset voor andere tests


def test_fallback_to_nl_and_key() -> None:
    translations.set_language("en")
    # Onbekende taal valt terug op nl.
    translations.set_language("xx")
    assert translations.current_language() == "nl"
    # Onbekende sleutel geeft de sleutel zelf terug.
    assert translations.t("bestaat_niet_sleutel") == "bestaat_niet_sleutel"


def test_languages_alphabetical() -> None:
    assert list(translations.LANGUAGES) == sorted(translations.LANGUAGES)
    assert set(translations.LANGUAGES) == {"en", "nl"}


def test_nl_en_keysets_identical() -> None:
    """Elke sleutel bestaat in beide talen (geen half-vertaalde interface)."""
    assert set(translations.TRANSLATIONS["nl"]) == set(translations.TRANSLATIONS["en"])
    # Wees-sleutels van verwijderde functies zijn opgeruimd.
    for orphan in ("listen", "step_align", "step_export", "step_all"):
        assert orphan not in translations.TRANSLATIONS["nl"]
