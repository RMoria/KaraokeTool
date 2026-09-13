"""Tests voor modules.config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules import config as config_module
from modules.config import ConfigError


def test_default_config_has_expected_values() -> None:
    config = config_module.default_config()
    assert config.whisper.model == "large-v3"
    assert config.karaoke.gain_db == -25.0
    assert config.align.max_offsets == 12


def test_video_meta_roundtrip(tmp_path: Path) -> None:
    """B122/B126: nieuwe video-velden overleven opslaan en laden."""
    from dataclasses import replace
    config = config_module.default_config()
    config = replace(config, video=replace(
        config.video, orig_artist="Normaal", orig_title="Oerend Hard",
        karaoke_title="Zangers Hard", background_image="bg.png"))
    path = tmp_path / "config.json"
    config_module.save_config(config, path)
    geladen = config_module.load_config(path)
    assert geladen.video.orig_artist == "Normaal"
    assert geladen.video.orig_title == "Oerend Hard"
    assert geladen.video.karaoke_title == "Zangers Hard"
    assert geladen.video.background_image == "bg.png"


def test_load_flat_config(tmp_path: Path) -> None:
    """Het platte voorbeeldformaat uit de projectbeschrijving werkt."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "search_words": ["oe", "Koffie"],
        "gain_db": -20,
        "fade_in_ms": 50,
        "fade_out_ms": 40,
    }), encoding="utf-8")
    config = config_module.load_config(path)
    assert config.karaoke.search_words == ("oe", "koffie")
    assert config.karaoke.gain_db == -20.0
    assert config.karaoke.fade_in_ms == 50
    # Ontbrekende secties vallen terug op standaardwaarden.
    assert config.whisper.model == "large-v3"


def test_save_and_reload_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    original = config_module.default_config()
    config_module.save_config(original, path)
    reloaded = config_module.load_config(path)
    assert reloaded == original


def test_parallelle_detectie_default_en_roundtrip(tmp_path: Path) -> None:
    """B90: de parallelle-detectie-optie staat standaard aan en bewaart."""
    from dataclasses import replace
    assert config_module.default_config().advanced.parallel_detection
    path = tmp_path / "config.json"
    cfg = config_module.default_config()
    cfg = replace(cfg, advanced=replace(cfg.advanced,
                                           parallel_detection=False))
    config_module.save_config(cfg, path)
    reloaded = config_module.load_config(path)
    assert reloaded.advanced.parallel_detection is False


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        config_module.load_config(tmp_path / "bestaat_niet.json")


def test_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{kapot", encoding="utf-8")
    with pytest.raises(ConfigError):
        config_module.load_config(path)


def test_positive_gain_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"search_words": ["oe"], "gain_db": 5}),
                    encoding="utf-8")
    with pytest.raises(ConfigError):
        config_module.load_config(path)


def test_empty_search_words_raise(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"search_words": ["oe", ""]}), encoding="utf-8")
    with pytest.raises(ConfigError):
        config_module.load_config(path)


def test_tracks_and_cache_defaults() -> None:
    config = config_module.default_config()
    assert config.tracks.original is True
    assert config.tracks.karaoke is True
    assert config.cache.clear is False   # standaard UIT (B236)


def test_both_tracks_disabled_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "search_words": ["oe"],
        "tracks": {"original": False, "karaoke": False},
    }), encoding="utf-8")
    with pytest.raises(ConfigError):
        config_module.load_config(path)


def test_interface_language_roundtrip(tmp_path: Path) -> None:
    from dataclasses import replace

    path = tmp_path / "config.json"
    config = config_module.default_config()
    assert config.interface.language == "nl"
    config_module.save_config(
        replace(config, interface=replace(config.interface, language="en")),
        path)
    assert config_module.load_config(path).interface.language == "en"


def test_geavanceerd_defaults_and_roundtrip(tmp_path: Path) -> None:
    from dataclasses import replace

    config = config_module.default_config()
    assert config.advanced.demucs is True
    assert config.advanced.forced_alignment is True
    # 'ritme' is geen optie meer: librosa-ritme zit vast in de kern.
    assert not hasattr(config.advanced, "ritme")
    path = tmp_path / "config.json"
    config_module.save_config(
        replace(config, advanced=replace(config.advanced,
                                            demucs=False)), path)
    assert config_module.load_config(path).advanced.demucs is False


def test_video_colors_and_theme_roundtrip(tmp_path: Path) -> None:
    from dataclasses import replace

    config = config_module.default_config()
    assert config.video.color_vocal == "#3CB043"
    assert config.theme.background == ""
    path = tmp_path / "config.json"
    config_module.save_config(replace(
        config,
        video=replace(config.video, color_vocal="#112233"),
        theme=replace(config.theme, background="#202020")), path)
    loaded = config_module.load_config(path)
    assert loaded.video.color_vocal == "#112233"
    assert loaded.theme.background == "#202020"
