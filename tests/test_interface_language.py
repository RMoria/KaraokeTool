"""The interface is walked in BOTH languages, not only in Dutch (B569).

The owner runs the program in Dutch and ``translations._CURRENT``
starts at ``"nl"``, so every test that builds a window has so far built
the Dutch one. That made a whole class of mistake invisible: a
dictionary that is FILLED under one name and READ BACK under another
lines up only as long as both happen to spell the same word.

B557 was exactly that. The two extra rows of the input panel were
registered in ``gui.MainWindow._extra_labels`` under the Dutch literals
"Songtekst" and "Karaoketekst", while ``_refresh_inputs`` had already
moved on to the internal ids. In Dutch ``t("lyrics")`` IS "Songtekst",
so the lookup matched by accident and 1784 tests stayed green. In
English it is "Original lyrics", and the very first refresh raised
``KeyError: 'Lyrics'``. The language is a real setting
(``interface.language``) and ``modules/gui.py`` calls ``set_language``
while the program runs, so a user switching to English would have met
that crash on his next refresh.

So every test here does the same walk twice, once per language, and
the two halves of that mistake are covered on purpose:

* the READ side - drive the code that indexes such a dictionary
  (``_refresh_inputs`` first of all) and let it raise;
* the WRITE side - compare the KEYS of every widget register of the
  window between the two languages, and refuse a key that is a
  displayed word. Keys that change with the language are what no
  single-language run can see; a hard-coded Dutch literal is what
  B557 actually shipped, and that one does not change with the
  language, so it needs its own check.

And one check that the walk means anything at all: labels whose two
texts really differ must show the other one in English, otherwise the
language never took and everything else here passes for nothing.

The test panel (``modules/test_panel.py``) is built in both languages
too. It was rebuilt in B563 and is nothing but translated labels.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline  # noqa: E402
from modules import translations  # noqa: E402
from modules.translations import TRANSLATIONS, t  # noqa: E402

#: Every language the interface offers. Dutch first, the way the
#: program starts, so a failure in English is easy to place.
LANGUAGES = ("nl", "en")

#: Keys that are on screen in the main window. Each one is also
#: asserted to HAVE two different texts, so this list cannot quietly
#: decay into a list of words that read the same in both languages.
WINDOW_KEYS = ("inputs_group", "song_group", "choose_file", "lyrics",
               "karaoke_text", "theme_group", "video_colors_group",
               "make_karaoke", "ready")

#: The same for the test panel (B563). Its Start button reads the same
#: in both languages, so it says nothing here; the window title is in
#: the haystack below but not in this list, for the same reason.
PANEL_KEYS = ("test_panel_intro", "test_scope_current", "test_scope_all",
              "test_force_again", "test_fill_cache_hint",
              "test_check_all_hint")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def restore_language():
    """Put the interface language back, whatever the test did.

    ``tests/test_v0101.py`` has a fixture of this name, but it is local
    to that file, so this is its own copy in the same shape. It puts
    back what it found instead of assuming Dutch, so it stays honest if
    the suite is ever started in another language.
    """
    previous = translations.current_language()
    yield
    translations.set_language(previous)


def _context(root: Path, name: str = "Proof"):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=root, song=name)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


@pytest.fixture
def build(qapp, tmp_path, restore_language):
    """Build the main window with the interface set to ``language``.

    One window per language and not one per assertion: building costs
    about a twentieth of a second, and a test that walks the window
    twice would otherwise pay for it twice for nothing.
    """
    def _build(language: str):
        from modules import gui

        translations.set_language(language)
        return gui.MainWindow(_context(tmp_path / language))

    return _build


def _fill_inputs(window) -> None:
    """Put every input file in place, so the refresh runs the branch
    that shows a name as well as the branch that misses one."""
    from modules import karaoke_text, song_text

    input_dir = window._context.paths.input_dir
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / song_text.LYRICS_FILENAME).write_text(
        "a line\n", encoding="utf-8")
    (input_dir / karaoke_text.FILENAME).write_text(
        "a line\n", encoding="utf-8")
    (input_dir / "logo.png").write_bytes(b"not really a picture")


def _registers(widget) -> dict[str, set[str]]:
    """Every ``name -> {key}`` dictionary of widgets on ``widget``.

    Found by looking rather than by a list, because the point is the
    pattern and not the one instance: a panel added next week that
    keeps its widgets in a dictionary is checked without anybody
    remembering to add it here.
    """
    from PySide6.QtWidgets import QWidget

    found = {}
    for name, value in vars(widget).items():
        if (isinstance(value, dict) and value
                and all(isinstance(item, QWidget)
                        for item in value.values())):
            found[name] = set(value)
    return found


def _texts(widget) -> set[str]:
    """Every text the window actually shows."""
    from PySide6.QtWidgets import (QCheckBox, QGroupBox, QLabel,
                                   QPushButton, QRadioButton)

    shown = set()
    for kind in (QLabel, QPushButton, QCheckBox, QRadioButton):
        shown |= {item.text() for item in widget.findChildren(kind)
                  if item.text()}
    shown |= {item.title() for item in widget.findChildren(QGroupBox)
              if item.title()}
    return shown


# --------------------------------------------------------------------------
# The read side: code that indexes a dictionary keyed by an id
# --------------------------------------------------------------------------

@pytest.mark.parametrize("language", LANGUAGES)
def test_the_input_panel_refreshes_in_both_languages(build,
                                                     language) -> None:
    """Prevents the B557 crash: ``KeyError`` on the first refresh.

    This is the exact path that broke. It is driven twice, once with an
    empty input folder and once with every file in place, because the
    two halves of ``_refresh_inputs`` read ``_extra_labels`` in
    different branches and only one of them would have been reached.
    """
    window = build(language)
    window._refresh_inputs()
    _fill_inputs(window)
    window._refresh_inputs()
    for key, label in window._extra_labels.items():
        assert label.text(), key


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_widget_register_is_read_back_in_both_languages(
        build, language) -> None:
    """Prevents the same mistake in the panels beside the input one.

    ``_track_bars``, ``_meta_fields``, ``_theme_buttons`` and
    ``_color_buttons`` are filled in one method and indexed in another,
    which is the shape that failed. The progress bars are the quiet
    case: they are looked up with ``.get()``, so a key that followed
    the language would not raise but would simply stop moving the bar.
    """
    window = build(language)
    tracks = [pipeline.TRACK_ORIGINAL, pipeline.TRACK_KARAOKE]
    window._start_track_progress(tracks)
    assert set(window._track_bars) == set(tracks)
    window._on_track_progress(pipeline.TRACK_ORIGINAL, 1.0, 2.0)
    window._on_track_done(pipeline.TRACK_KARAOKE)
    assert window._track_bars[pipeline.TRACK_KARAOKE].value() == 100

    window._meta_fields["karaoke_title"].setText("Proof")
    window._save_meta_field("karaoke_title")
    assert window._context.config.video.karaoke_title == "Proof"

    window._reset_theme()
    window._reset_video_colors()


# --------------------------------------------------------------------------
# The write side: what the registers are keyed on
# --------------------------------------------------------------------------

def test_a_register_is_keyed_on_the_same_thing_in_both_languages(
        build) -> None:
    """Prevents a register that is FILLED under a translated word.

    The reading side would then be right and the writing side wrong,
    which is B557 the other way round and just as invisible in one
    language: the keys simply become other words, and everything that
    looks them up by id misses.
    """
    registers = {language: _registers(build(language))
                 for language in LANGUAGES}
    assert "_extra_labels" in registers["nl"], _registers.__doc__
    assert registers["nl"] == registers["en"]


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_register_is_keyed_on_a_word_from_the_screen(build,
                                                        language) -> None:
    """Prevents the literal that B557 actually shipped.

    A key that is a hard-coded Dutch word is the same in both
    languages, so comparing the two runs cannot see it. What gives it
    away is that the key is a Dutch TEXT out of the table, and an id
    never is.

    Refused is a Dutch text that the English table spells differently,
    and only that. Two tables that agree on a word cannot be the
    mistake this test is about - "Logo" stays "Logo", so a register
    keyed on it lines up in either language - while the internal
    language being English (see ``tests/test_language_guard.py``) means
    an id and an English text may legitimately read the same:
    ``t("couple_lyrics")`` is "Lyrics:" and the id is ``lyrics``.
    """
    window = build(language)
    words = {value.rstrip(":").casefold()
             for key, value in TRANSLATIONS["nl"].items()
             if TRANSLATIONS["en"].get(key, value) != value}
    for name, keys in _registers(window).items():
        for key in keys:
            assert key.casefold() not in words, f"{name}[{key!r}]"


# --------------------------------------------------------------------------
# The test panel (B563)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("language", LANGUAGES)
def test_the_test_panel_builds_and_answers_in_both_languages(
        qapp, restore_language, language) -> None:
    """Prevents a crash in the window that is nothing but labels.

    Building it is half the check; the other half is that the answers
    it gives back still come out, because those walk the same lists of
    actions that the labels were made from.
    """
    from modules import test_panel

    translations.set_language(language)
    panel = test_panel.TestPanel()
    assert panel._ticks, "the panel drew no actions at all"
    assert not any(tick.isChecked() for tick in panel._ticks)
    panel._toggle_all()
    assert [action.code for action in panel.chosen()] == ["1.5.2"]
    assert panel.heavy_choice() == []
    assert panel.remeasure() is False
    assert panel.only_this_project() is False


# --------------------------------------------------------------------------
# Did the language take at all?
# --------------------------------------------------------------------------

@pytest.mark.parametrize("language", LANGUAGES)
def test_the_window_shows_the_language_that_was_set(build,
                                                    language) -> None:
    """Prevents this whole file from passing for nothing.

    Every other test here is worth exactly as much as the switch is. A
    label that reads the same in Dutch and in English for a key that
    HAS two texts means ``set_language`` did not take, and then the
    English half of the file walks the Dutch interface.
    """
    shown = "\n".join(_texts(build(language)))
    for key in WINDOW_KEYS:
        assert TRANSLATIONS["nl"][key] != TRANSLATIONS["en"][key], key
        assert t(key) in shown, key


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_test_panel_shows_the_language_that_was_set(
        qapp, restore_language, language) -> None:
    """The same, for the panel: it has its own texts (B563)."""
    from modules import test_panel

    translations.set_language(language)
    panel = test_panel.TestPanel()
    shown = "\n".join(_texts(panel) | {panel.windowTitle()})
    for key in PANEL_KEYS:
        assert TRANSLATIONS["nl"][key] != TRANSLATIONS["en"][key], key
        assert t(key) in shown, key
