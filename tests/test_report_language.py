"""The texts people read follow the interface language (v1.0.11).

Until this version the translation table covered the interface, the
errors and the log lines of ``modules/`` - and not the reports of the
test panel, the model register, the cluster overview, the yardstick's
measurement document, or the start script, which lives outside
``modules/`` and was read by no guard. All of that goes through
``t()`` now, with the Dutch text byte for byte what it was.

``tests/test_dutch_leftovers.py`` holds the source to that. This file
holds the result: run in English, the program writes English - down to
the first line of the log, which is written before the settings are
properly loaded and therefore used to be Dutch whatever was chosen.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from modules import config as config_module
from modules import model_orders, model_register, translations
from modules.translations import t

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def english():
    previous = translations.current_language()
    translations.set_language("en")
    yield
    translations.set_language(previous)


def _dutch_words():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_dutch_leftovers import DUTCH_WORDS
    return DUTCH_WORDS


# --------------------------------------------------------------------------
# The language before the settings are loaded
# --------------------------------------------------------------------------

def test_the_language_can_be_read_without_loading(tmp_path) -> None:
    """Raw, and ``None`` for everything that does not say."""
    path = tmp_path / "config.json"
    assert config_module.read_interface_language(path) is None
    path.write_text("{not json", encoding="utf-8")
    assert config_module.read_interface_language(path) is None
    path.write_text(json.dumps({"interface": {}}), encoding="utf-8")
    assert config_module.read_interface_language(path) is None
    path.write_text(json.dumps({"interface": {"language": "en"}}),
                    encoding="utf-8")
    assert config_module.read_interface_language(path) == "en"


def test_the_start_of_the_log_is_in_the_chosen_language(tmp_path) -> None:
    """The first lines, AND the failure of loading the settings.

    Run for real, as a separate process: a settings file that says
    English and that cannot be loaded (a negative fade). Before
    v1.0.11 both the start line and the complaint were Dutch here,
    because the language was only set after a successful load.
    """
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    (data / "config" / "config.json").write_text(
        json.dumps({"interface": {"language": "en"}, "fade_in_ms": -5}),
        encoding="utf-8")
    environment = dict(os.environ, KARAOKETOOL_DATA=str(data),
                       QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, str(ROOT / "KaraokeTool.py")],
                            cwd=str(tmp_path), env=environment,
                            capture_output=True, text=True, timeout=120)

    assert result.returncode == 1, result.stdout + result.stderr
    log = "".join(path.read_text(encoding="utf-8")
                  for path in (data / "logs").glob("*.log"))
    english_start = translations.TRANSLATIONS["en"]["log_app_started"]
    assert english_start.split("%s")[0] in log
    assert translations.TRANSLATIONS["en"]["log_config_unreadable"] in log
    assert "gestart" not in log and "Configuratie" not in log
    assert "Error in the configuration" in result.stdout


# --------------------------------------------------------------------------
# What the reports are made of
# --------------------------------------------------------------------------

def test_the_model_register_reads_in_both_languages(english) -> None:
    """Names, levels and reasons, looked up when they are shown."""
    dutch = _dutch_words()
    for model in model_register.register():
        for text in (model.display_name, model.display_level,
                     model.display_reason, model.label):
            # A project name such as ``Lied_T`` is a name.
            text = re.sub(r"\w+_\w+", " ", text)
            words = {w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ]+",
                                                     text)}
            assert not words & dutch, (model.code, text)
    translations.set_language("nl")
    assert model_register.by_code("B250/B251").display_name == "blokgrens"


def test_an_order_is_printed_in_the_language_and_kept_as_an_id(
        english) -> None:
    """The name travels to a child process; only its print changes."""
    for name in model_orders.names():
        assert "vóór" in name
        assert "vóór" not in model_orders.label(name)
        assert t("model_order_before") in model_orders.label(name)


def test_the_panel_reports_speak_english(tmp_path, english) -> None:
    """Action 1.5.2 over two projects: English, apart from the song.

    The fixture's own lyrics and karaoke text are Dutch, and a report
    quotes the song - so the words that come from the song are taken
    out before looking.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_project_safety as fixture
    from modules import test_panel

    root, context = fixture._installation(tmp_path)
    text = test_panel.check_all_projects(context, lambda *a, **k: None,
                                         lambda: False)
    song = {w.lower() for w in re.findall(
        r"[A-Za-zÀ-ÿ]+", fixture.LYRICS + fixture.KARAOKE)}
    song |= {w[0] for w in fixture.WORDS}
    dutch = _dutch_words() - song
    found = sorted({w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ]+",
                                                   text)} & dutch)
    assert "Song_A" in text
    assert not found, found


# --------------------------------------------------------------------------
# The yardstick's own document, and how it finds its language
# --------------------------------------------------------------------------

def test_the_measurement_document_follows_the_language(tmp_path,
                                                       english) -> None:
    """``docs/metingen.md`` was Dutch whatever the interface said."""
    from modules import test_panel

    module = test_panel._regression_module()
    target = tmp_path / "measurements.md"
    module.note([{"project": "Song_A", "lines": 2, "coupled": 2,
                  "moved": 1, "new_moved": 0.25}], target, "0.1",
                "2026-01-01")
    text = target.read_text(encoding="utf-8")
    assert "## v0.1 — 2026-01-01" in text      # the marker stays as it was
    found = {w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ]+", text)}
    assert not found & _dutch_words(), sorted(found & _dutch_words())


def test_the_yardstick_reads_the_language_of_the_installation(
        tmp_path) -> None:
    """Run on its own, it takes the language of the folder it measures."""
    from modules import test_panel

    module = test_panel._regression_module()
    (tmp_path / "config").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "config" / "config.json").write_text(
        json.dumps({"interface": {"language": "en"}}), encoding="utf-8")
    assert module.installation_language(tmp_path / "output") == "en"
