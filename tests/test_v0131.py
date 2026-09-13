"""Tests for v0.131.0: B400 - dead translation keys, and a guard.

The working agreement has said since the beginning that every change
should look for code that has become redundant. Translations were the
blind spot: a renamed button or a merged test leaves its texts behind,
and nothing ever noticed. Thirty of them had piled up - ``fill_cache_*``
from before that became action 1.5.1, ``test_texts``/``test_filters``/
``test_structure`` from the three reports B365 merged into 1.5.3,
``test_probe_*`` from the window test that moved to the heavy bin in
B374.

Removing them cost one lesson, and the suite taught it. Twelve of the
thirty were not dead at all: ``lane_original`` and ``view_blocks`` and
the ``model_*_desc`` texts are never written out in full anywhere,
because they are composed at run time (``t(f"lane_{name}")``). A search
for the literal key finds nothing and concludes the text is unused. The
guard below therefore looks for the PREFIXES of composed keys too - and
that is exactly why the guard is worth more than the clean-up.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _sources() -> str:
    return " ".join(
        p.read_text(encoding="utf-8")
        for p in list((ROOT / "modules").glob("*.py"))
        + list((ROOT / "tools").glob("*.py"))
        if p.name != "translations.py")


def _composed_prefixes(text: str) -> set[str]:
    """Prefixes of keys that are built at run time.

    ``t(f"lane_{name}")`` never mentions ``lane_original``, so anything
    starting with ``lane_`` has to count as used.
    """
    found = set(re.findall(r't\(f"([a-z_]*?)\{', text))
    found |= set(re.findall(r'f"([a-z_]*?)\{[a-z_]+\}[a-z_]*"', text))
    return {p for p in found if p}


def test_no_translation_key_is_unused() -> None:
    """The guard. A key nobody asks for is a text nobody reads, and it
    makes the table unreliable to search."""
    from modules.translations import TRANSLATIONS

    text = _sources()
    prefixes = _composed_prefixes(text)
    dead = [key for key in TRANSLATIONS["nl"]
            if f'"{key}"' not in text and f"'{key}'" not in text
            and not any(key.startswith(p) for p in prefixes)]
    assert not dead, "ongebruikte vertaalsleutels: " + ", ".join(sorted(dead))


def test_the_guard_sees_composed_keys() -> None:
    """Without this the guard would delete twelve texts that ARE used -
    which is what nearly happened."""
    prefixes = _composed_prefixes(_sources())
    for prefix in ("lane_", "view_", "model_"):
        assert prefix in prefixes, prefix


def test_the_lane_labels_still_have_their_texts() -> None:
    """The twelve that were nearly removed."""
    from modules.translations import TRANSLATIONS

    for key in ("lane_original", "lane_karaoke", "lane_vocals",
                "view_blocks", "view_sentences", "view_words",
                "model_demucs_desc", "model_forced_alignment_desc"):
        for language in ("nl", "en"):
            assert TRANSLATIONS[language].get(key, "").strip(), key


def test_the_merged_reports_left_no_texts_behind() -> None:
    """B365 merged three reports into 1.5.3; their labels went with it."""
    from modules.translations import TRANSLATIONS

    for key in ("test_texts", "test_filters", "test_structure",
                "test_probe", "fill_cache_title", "fill_cache_body"):
        assert key not in TRANSLATIONS["nl"], key
        assert key not in TRANSLATIONS["en"], key


def test_both_languages_stayed_equal() -> None:
    from modules.translations import TRANSLATIONS

    assert set(TRANSLATIONS["nl"]) == set(TRANSLATIONS["en"])


# --------------------------------------------------------------------------
# B401 - nine processes must not outlive their window
# --------------------------------------------------------------------------

def test_the_pool_is_closed_when_the_program_stops() -> None:
    """Stop halfway, the window closed, an exception in the runner - in
    all of those the tidy path is not taken and nine interpreters would
    keep standing."""
    import atexit
    import inspect

    from modules import measure_pool

    source = inspect.getsource(measure_pool)
    assert "atexit.register" in source
    assert callable(measure_pool._close_at_exit)
    assert atexit  # noqa: B018 - import used for the check above


def test_closing_the_window_lets_the_workers_go() -> None:
    import inspect

    from modules import gui

    source = inspect.getsource(gui.MainWindow.closeEvent)
    assert "close_pool()" in source


def test_closing_never_breaks_closing() -> None:
    """Tidying up may not stop the window from closing."""
    import inspect

    from modules import gui

    source = inspect.getsource(gui.MainWindow.closeEvent)
    where = source.index("close_pool()")
    assert "try:" in source[max(0, where - 120):where]


# --------------------------------------------------------------------------
# B391 - is the prompt budget being left unused?
# --------------------------------------------------------------------------

def test_the_probe_can_vary_the_prompt_length() -> None:
    """The question was whether 400 characters is too careful, since
    Whisper only truncates around 224 tokens.

    B437: answered, and the answer was no - twice, on the same song: a
    longer prompt gives MORE segments (26 to 40), FEWER words (196 to
    184) and exactly the same coverage of the gap. The longer lengths
    have therefore been retired and only the one in use is left. The
    machinery to vary it stays, so the question can be reopened in one
    line if something changes in Whisper."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "probe_prompt", ROOT / "tools" / "whisper_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert 400 in module.PROMPT_LENGTHS
    assert module.prompt_for_project.__doc__


def test_a_longer_prompt_really_carries_more() -> None:
    from modules import song_text

    made = [song_text.LyricWord(index=n, text=f"woord{n}", line=0)
            for n in range(300)]
    short = song_text.deduped_prompt_text(made, max_chars=400)
    long = song_text.deduped_prompt_text(made, max_chars=900)
    assert len(long) > len(short)
    assert long.startswith(short[:200])


