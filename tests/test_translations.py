"""Tests for the translation layer."""

from __future__ import annotations

from modules import translations


def test_default_and_switch() -> None:
    translations.set_language("nl")
    assert translations.current_language() == "nl"
    assert translations.t("tab_video") == "Karaokevideo"
    translations.set_language("en")
    assert translations.t("tab_video") == "Karaoke video"
    translations.set_language("nl")  # reset for the other tests


def test_fallback_to_nl_and_key() -> None:
    translations.set_language("en")
    # An unknown language falls back to nl.
    translations.set_language("xx")
    assert translations.current_language() == "nl"
    # An unknown key returns the key itself.
    assert translations.t("bestaat_niet_sleutel") == "bestaat_niet_sleutel"


def test_languages_alphabetical() -> None:
    assert list(translations.LANGUAGES) == sorted(translations.LANGUAGES)
    assert set(translations.LANGUAGES) == {"en", "nl"}


def test_nl_en_keysets_identical() -> None:
    """Every key exists in both languages (no half-translated interface)."""
    assert set(translations.TRANSLATIONS["nl"]) == set(translations.TRANSLATIONS["en"])
    # Orphan keys of removed features have been cleaned up.
    for orphan in ("listen", "step_align", "step_export", "step_all"):
        assert orphan not in translations.TRANSLATIONS["nl"]
