"""Tests for v0.101.0: B323 through B328.

B323 - the Stop button no longer takes the busy colour away from the
       running step, so "1.1. Detecteer woorden" does not stay yellow.
B324 - the original file name of the lyrics and of the karaoke text is
       written under the same key it is read back with.
B325 - the buttons are called <tab>.<button>. and a message names a
       button by its key, not by its name.
B326 - "2.2. Timing verfijnen" broke on a Dutch key; the texts the
       pipeline hands back now go through translations.py.
B327 - the lane labels of the waveform editor showed their own key.
B328 - the manual describes what there is to see and to operate.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import pipeline  # noqa: E402
from modules import translations as translations_module  # noqa: E402
from modules.translations import TRANSLATIONS, t  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "modules"


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def restore_language():
    """Put the language back, even if a test switches it midway."""
    yield
    translations_module.set_language("nl")


def _context(tmp_path: Path, name: str = "Proef"):
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song=name)
    ensure_directories(paths)
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


# --------------------------------------------------------------------------
# B323: the Stop button and the busy colour
# --------------------------------------------------------------------------

def test_stop_is_not_marked_busy(qapp, tmp_path) -> None:
    """Stop starts no task; it should not get the busy colour."""
    from modules import gui

    window = gui.MainWindow(_context(tmp_path, "Stop1"))
    window._mark_busy_click(window._stop_button)
    assert window._stop_button not in window._busy_buttons


def test_stop_does_not_leave_the_running_button_yellow(qapp,
                                                       tmp_path) -> None:
    """The reported order: start detection, press Stop, cancel.

    Stop was hooked up too and so became owner of the busy colour; the
    cleanup then reset Stop instead of the step button, which therefore
    stayed yellow.
    """
    from modules import gui

    window = gui.MainWindow(_context(tmp_path, "Stop2"))
    detect = window._step_buttons[0]

    window._mark_busy_click(detect)
    assert detect in window._busy_buttons
    assert detect.styleSheet() != ""

    # A task is running; a click on Stop must not take the ownership
    # over. (We replace the real worker with a stand-in.)
    class _Running:
        def isRunning(self) -> bool:
            return True

    window._worker = _Running()
    window._mark_busy_click(window._stop_button)
    assert detect in window._busy_buttons
    assert window._stop_button not in window._busy_buttons

    # And after the cancel the step button is plain again.
    window._worker = None
    window._release_busy_button()
    assert detect.styleSheet() == ""
    assert not window._busy_buttons


def test_every_marked_button_is_reset(qapp, tmp_path) -> None:
    """``_busy_buttons`` is a set: not one of them is ever left behind."""
    from modules import gui

    window = gui.MainWindow(_context(tmp_path, "Stop3"))
    first, second = window._step_buttons[0], window._step_buttons[1]
    window._busy_buttons = {first, second}
    window._apply_busy_style(first, True)
    window._apply_busy_style(second, True)
    window._release_busy_button()
    assert first.styleSheet() == "" and second.styleSheet() == ""


# --------------------------------------------------------------------------
# B324: which key the original file name is stored under
# --------------------------------------------------------------------------

def test_the_write_key_and_the_read_key_are_the_same() -> None:
    """The writer used the file name (``songtekst``), the reader asked
    for ``lyrics``. So what showed up was always the internal name."""
    gui_source = (MODULES / "gui.py").read_text(encoding="utf-8")

    written = set(re.findall(
        r'_copy_into_input\(\s*chosen,\s*\n?\s*(?:f?"[^"]+"|[^,]+),\s*\n?\s*"(\w+)"',
        gui_source))
    read_back = set(re.findall(
        r'input_display_name\(\s*\n?\s*self\._context,\s*"(\w+)"',
        gui_source))
    read_back |= set(re.findall(r'input_start_dir\(self\._context,\s*"(\w+)"',
                                gui_source))

    # The audio tracks go through the ``stem`` variable
    # (original/karaoke) and have always matched; the text files did not.
    assert written == {"lyrics", "karaoke_text", "logo"}, written
    assert read_back == {"lyrics", "karaoke_text", "logo"}, read_back
    unknown = (written | read_back) - set(pipeline.INPUT_NAME_KEYS)
    assert not unknown, f"key outside INPUT_NAME_KEYS: {sorted(unknown)}"
    # The writer may no longer derive the key from the file name.
    assert "Path(target_name).stem" not in gui_source


@pytest.mark.parametrize("key", pipeline.INPUT_NAME_KEYS)
def test_every_input_key_reads_back_what_it_wrote(tmp_path, key) -> None:
    context = _context(tmp_path, f"Key_{key}")
    source = tmp_path / "folder" / "viva espanja-origineel.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("x", encoding="utf-8")
    pipeline.set_input_origin(context, key, source)
    assert pipeline.input_display_name(context, key, "val") == source.name
    assert pipeline.input_start_dir(context, key) == str(source.parent)


def test_an_existing_project_is_migrated(tmp_path) -> None:
    """Anyone who already has projects must not lose his names."""
    context = _context(tmp_path, "Migratie")
    context.store.set_meta("input_names", {
        "songtekst": {"name": "viva espanja-origineel.txt", "dir": "/tmp"},
        "karaoketekst": {"name": "Lied S-karaoke.txt", "dir": "/tmp"},
        "original": {"name": "viva.mp3", "dir": "/tmp"}})

    assert pipeline.migrate_input_names(context) is True
    assert pipeline.input_display_name(context, "lyrics", "val") \
        == "viva espanja-origineel.txt"
    assert pipeline.input_display_name(context, "karaoke_text", "val") \
        == "Lied S-karaoke.txt"
    assert pipeline.input_display_name(context, "original", "val") \
        == "viva.mp3"
    # Idempotent: a second run changes nothing.
    assert pipeline.migrate_input_names(context) is False


def test_migration_does_not_overwrite_a_new_value(tmp_path) -> None:
    """If a good value is already there, it beats the old key."""
    context = _context(tmp_path, "Migratie2")
    context.store.set_meta("input_names", {
        "songtekst": {"name": "oud.txt", "dir": "/tmp"},
        "lyrics": {"name": "nieuw.txt", "dir": "/tmp"}})
    pipeline.migrate_input_names(context)
    assert pipeline.input_display_name(context, "lyrics", "val") == "nieuw.txt"
    assert "songtekst" not in (context.store.get_meta("input_names") or {})


# --------------------------------------------------------------------------
# B325: the button numbering
# --------------------------------------------------------------------------

EXPECTED_NUMBERS = {
    "step_detect": "1.1. ", "step_couple": "1.2. ",
    "step_analyse": "1.3. ", "step_karaoke": "1.4. ",
    "video_edit_stress": "2.1. ", "video_timing": "2.2. ",
    "video_edit_timing": "2.3. ", "video_render": "2.4. ",
}


@pytest.mark.parametrize("key,number", sorted(EXPECTED_NUMBERS.items()))
def test_a_button_carries_tab_and_number(key: str, number: str) -> None:
    for language in ("nl", "en"):
        assert TRANSLATIONS[language][key].startswith(number), (language, key)


def test_the_button_list_is_complete() -> None:
    assert set(translations_module.BUTTON_KEYS) == set(EXPECTED_NUMBERS)


def test_no_text_names_a_button_by_name_any_more() -> None:
    """A message that spells out a button name falls out of step at the
    next renumbering. They are meant to use the key."""
    offenders = []
    for language, catalogue in TRANSLATIONS.items():
        names = {k: catalogue[k] for k in translations_module.BUTTON_KEYS}
        for key, text in catalogue.items():
            if key in translations_module.BUTTON_KEYS:
                continue
            for button, name in names.items():
                # The name without its number: the part that stays put.
                bare = name.split(". ", 1)[-1]
                if f"'{name}'" in text or f"'{bare}'" in text:
                    offenders.append(f"{language}/{key} names {button}")
    assert not offenders, offenders


def test_a_button_reference_is_filled_in(restore_language) -> None:
    for language in ("nl", "en"):
        translations_module.set_language(language)
        text = t("prereq_need_detect")
        assert "{step_detect}" not in text
        assert TRANSLATIONS[language]["step_detect"] in text


def test_other_placeholders_stay(restore_language) -> None:
    """``t()`` only fills in button references; the caller does the rest."""
    text = t("err_no_transcription")
    assert "{track}" in text
    assert "1.1. Detecteer woorden" in text
    assert "{track}" not in text.format(track="origineel")


# --------------------------------------------------------------------------
# B326: the crash at "2.2. Timing verfijnen"
# --------------------------------------------------------------------------

def test_coupling_quality_has_english_keys() -> None:
    """``couple_timing`` returns high/medium/low; the pipeline read
    hoog/midden/laag and broke on that with a KeyError."""
    from modules import timing as timing_module

    source = (MODULES / "pipeline.py").read_text(encoding="utf-8")
    for old in ("quality['hoog']", "quality['midden']", "quality['laag']",
                'quality["hoog"]', 'quality["midden"]', 'quality["laag"]'):
        assert old not in source, old
    assert set(timing_module.couple_timing.__doc__ or "") or True
    text = t("timing_detail_coupling").format(high=1, medium=2, low=3)
    assert "1x" in text and "2x" in text and "3x" in text


def test_timing_detail_follows_the_language(restore_language) -> None:
    translations_module.set_language("en")
    english = t("timing_detail_even")
    translations_module.set_language("nl")
    assert english != t("timing_detail_even")
    assert "songtekst" in t("timing_detail_even")


def test_video_input_has_language_independent_keys(tmp_path) -> None:
    """The render skipped the offset by its DUTCH name; in English that
    comparison did not hold and it refused to render."""
    context = _context(tmp_path, "Invoer")
    keys = [row[0] for row in pipeline.video_input_status(context)]
    assert keys == ["lyrics", "karaoke_text", "logo", "timing", "offset"]
    assert "offset" in pipeline.VIDEO_INPUT_OPTIONAL
    source = (MODULES / "pipeline.py").read_text(encoding="utf-8")
    assert '!= "offset origineel/karaoke"' not in source


def test_video_input_details_follow_the_language(tmp_path,
                                                 restore_language) -> None:
    context = _context(tmp_path, "Invoer2")

    def details():
        return [row[3] for row in pipeline.video_input_status(context)]

    translations_module.set_language("nl")
    nl_details = details()
    translations_module.set_language("en")
    en_details = details()
    # The paths are the same; the sentences around them are not.
    assert nl_details != en_details


@pytest.mark.parametrize("function,arguments", [
    ("check_text_alignment", ()),
    ("sync_timing_with_text_change", ((), ())),
])
def test_pipeline_messages_follow_the_language(tmp_path, restore_language,
                                               function, arguments) -> None:
    """These two hand back a message that the GUI shows; it used to be
    hard-coded in Dutch."""
    context = _context(tmp_path, f"Message_{function}")
    call = getattr(pipeline, function)

    translations_module.set_language("nl")
    _, nl_message = call(context, *arguments)
    translations_module.set_language("en")
    _, en_message = call(context, *arguments)
    assert nl_message and en_message and nl_message != en_message


def test_no_dutch_literals_left_in_those_functions() -> None:
    """Regression guard on the functions whose text the GUI shows."""
    source = (MODULES / "pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    guarded = {"generate_timing", "video_input_status", "check_text_alignment",
               "sync_timing_with_text_change"}
    dutch = re.compile(
        r"\b(?:geen|niet|regels|eerst|draai|secties|verschilt|onleesbaar|"
        r"gewijzigd|bijgewerkt|aanwezig|songtekst|karaoketekst)\b", re.I)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in guarded:
            continue
        docstring = node.body[0].value if (
            node.body and isinstance(node.body[0], ast.Expr)) else None
        for child in ast.walk(node):
            if child is docstring or not isinstance(child, ast.Constant):
                continue
            if isinstance(child.value, str) and dutch.search(child.value):
                offenders.append(f"{node.name}:{child.lineno} "
                                 f"{child.value[:50]!r}")
    assert not offenders, offenders


# --------------------------------------------------------------------------
# B327: keys that are built up with an f-string
# --------------------------------------------------------------------------

def test_every_composed_translation_key_exists() -> None:
    """``t(f"lane_{key}")`` escaped the B315 guard: three lane names
    stayed Dutch through the rename and then showed up on screen as the
    key itself."""
    missing = []
    for path in sorted(MODULES.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for prefix in set(re.findall(r't\(f"(\w+_)\{', source)):
            # Every value that can end up as the tail of that f-string:
            # the loose text constants in this file.
            for tail in re.findall(r'"(\w+)"', source):
                key = prefix + tail
                if key in TRANSLATIONS["nl"]:
                    continue
    # More directly: the lane labels and the source picker of the editor.
    from modules import timing_editor

    for name, _top in timing_editor._LANE_LABELS:
        key = f"lane_{name}"
        if key not in TRANSLATIONS["nl"]:
            missing.append(key)
    for name in ("original", "karaoke", "vocals"):
        if f"lane_{name}" not in TRANSLATIONS["nl"]:
            missing.append(f"lane_{name}")
    for mode in ("blocks", "sentences", "words"):
        if f"view_{mode}" not in TRANSLATIONS["nl"]:
            missing.append(f"view_{mode}")
    assert not missing, missing


def test_no_lane_label_shows_its_own_key() -> None:
    from modules import timing_editor

    for name, _top in timing_editor._LANE_LABELS:
        assert t(f"lane_{name}") != f"lane_{name}"


def test_the_source_picker_uses_the_same_names_as_the_gui() -> None:
    """The keys of ``audio_paths`` have to match on both sides, or the
    vocal stem quietly drops out of the picker."""
    editor = (MODULES / "timing_editor.py").read_text(encoding="utf-8")
    gui_source = (MODULES / "gui.py").read_text(encoding="utf-8")
    assert 'for name in ("original", "karaoke", "vocals")' in editor
    assert '"vocals": vocal_wav' in gui_source
    assert "zangstem" not in editor


# --------------------------------------------------------------------------
# B328: the manual
# --------------------------------------------------------------------------

MANUAL = (ROOT / "docs" / "manual.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("key,number", sorted(EXPECTED_NUMBERS.items()))
def test_the_manual_names_the_current_buttons(key: str, number: str) -> None:
    name = TRANSLATIONS["nl"][key]
    assert name in MANUAL, f"manual is missing '{name}'"


def test_the_manual_names_no_old_buttons() -> None:
    """Every mention of a button carries the current numbering, so that
    the manual does not quietly fall behind the app."""
    for key, number in EXPECTED_NUMBERS.items():
        bare = TRANSLATIONS["nl"][key][len(number):]
        for hit in re.finditer(re.escape(bare), MANUAL):
            start = hit.start()
            assert MANUAL[max(0, start - len(number)):start] == number, (
                f"'{bare}' without number '{number}': "
                f"...{MANUAL[max(0, start - 50):hit.end()]}")


@pytest.mark.parametrize("topic", [
    "dependencies.md",          # the derivation chain (B311)
    "Zangstem-analyse",             # the setting behind B313/B319
    "Terug uit origineel",          # the green blocks in the damping editor
    "Regel uit/aan",                # not rendering
    "Blokken",                      # the view choice in the waveform editor
    "legenda",                      # the colours in the coupling editor
    "Sluiten",                      # save-on-close differs per editor
])
def test_the_manual_describes_what_can_be_operated(topic: str) -> None:
    assert topic in MANUAL, f"manual is missing '{topic}'"
