"""Tests for v0.99.0: B313, B314 and B315.

B313 - skipped lyrics words get a time from the vocal stem.
B314 - the Whisper decoding options are settings instead of defaults.
B315 - the log lines go through the translation layer.
"""
from __future__ import annotations

import re
import types
from dataclasses import replace
from pathlib import Path

import pytest

from modules import pipeline, translations, whisper
from modules.config import WhisperSettings, default_config
from modules.song_text import AlignedWord, LyricWord


# --------------------------------------------------------------------------
# B315: every log line is translated, matching placeholders in both languages
# --------------------------------------------------------------------------

#: ``%`` conversions as the logger fills them in. Deliberately NOT "%%"
#: (that is a literal percent sign and not a placeholder).
_PERCENT = re.compile(r"%(?!%)[-+ #0]*[0-9]*(?:\.[0-9]+)?[a-zA-Z]")
#: ``{name}`` fields as ``str.format`` fills them in.
_FIELD = re.compile(r"\{(\w+)\}")


def test_the_placeholders_match_in_both_languages(monkeypatch) -> None:
    """The most important guard on the translation layer.

    The logger fills ``%`` placeholders POSITIONALLY: where the English
    has a ``%d`` and the Dutch a ``%s``, you get a wrongly filled line
    or an exception halfway through logging. For ``{name}`` fields the
    order does not count, but the set has to be equal, otherwise a value
    is missing.

    This test looks at ALL keys, not only the new ones: until now this
    was checked nowhere.
    """
    nl = translations.TRANSLATIONS["nl"]
    en = translations.TRANSLATIONS["en"]
    fouten = []
    for key in sorted(nl):
        dutch, english = str(nl[key]), str(en.get(key, ""))
        if _PERCENT.findall(dutch) != _PERCENT.findall(english):
            fouten.append(f"{key}: % nl={_PERCENT.findall(dutch)} "
                          f"en={_PERCENT.findall(english)}")
        if sorted(_FIELD.findall(dutch)) != sorted(_FIELD.findall(english)):
            fouten.append(f"{key}: velden nl={_FIELD.findall(dutch)} "
                          f"en={_FIELD.findall(english)}")
    assert not fouten, "\n".join(fouten)


def test_both_languages_have_the_same_keys() -> None:
    nl = set(translations.TRANSLATIONS["nl"])
    en = set(translations.TRANSLATIONS["en"])
    assert nl == en, sorted(nl ^ en)


def test_no_literal_log_texts_left_in_the_modules() -> None:
    """Every ``logger.x(...)`` takes its text from the translation layer.

    Without this test the next log line simply slips back in in Dutch,
    and the log window then stops following the language choice.
    """
    import ast

    modules_dir = Path(__file__).resolve().parents[1] / "modules"
    offenders = []
    for path in sorted(modules_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not (isinstance(f, ast.Attribute)
                    and isinstance(f.value, ast.Name)
                    and f.value.id == "logger"):
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) \
                    and isinstance(first.value, str):
                offenders.append(f"{path.name}:{node.lineno} "
                                 f"{first.value[:50]!r}")
    assert not offenders, ("logregels met een letterlijke tekst in plaats "
                           "van t(...):\n" + "\n".join(offenders))


def test_the_log_keys_really_exist() -> None:
    """Every ``t("log_...")`` in the code has to have a key."""
    modules_dir = Path(__file__).resolve().parents[1] / "modules"
    pattern = re.compile(r't\("(log_\w+)"\)')
    used = set()
    for path in sorted(modules_dir.glob("*.py")):
        used.update(pattern.findall(path.read_text(encoding="utf-8")))
    missing = sorted(used - set(translations.TRANSLATIONS["nl"]))
    assert not missing, missing
    assert len(used) > 150, "verwacht ~185 logsleutels, gevonden " \
                            f"{len(used)}"


def test_no_bug_numbers_in_the_log_texts() -> None:
    """The log lines sit in the window the user reads; internal
    B-numbers belong in the comments, not there."""
    for language, texts in translations.TRANSLATIONS.items():
        for key, value in texts.items():
            if key.startswith("log_"):
                assert not re.search(r"\bB\d{2,3}\b", str(value)), \
                    f"{language}/{key}: {value}"


# --------------------------------------------------------------------------
# B314: the Whisper settings
# --------------------------------------------------------------------------

def test_the_decode_options_come_from_the_settings() -> None:
    settings = replace(WhisperSettings(), temperature=(0.0, 0.4),
                       no_speech_threshold=None, vad_filter=True,
                       hallucination_silence_threshold=2.0,
                       log_prob_threshold=-2.0)
    options = whisper.decode_options(settings)
    assert options["temperature"] == [0.0, 0.4]
    assert options["no_speech_threshold"] is None
    assert options["log_prob_threshold"] == -2.0
    assert options["vad_filter"] is True
    assert options["hallucination_silence_threshold"] == 2.0


def test_the_default_is_repeatable_decoding() -> None:
    """The default is one temperature, so no sampling.

    Faster-whisper falls back over a ladder of temperatures by default
    and then decodes WITH sampling, without a seed. On one and the same
    source file that gave 36, 28 and 27 segments. A karaoke video you
    cannot reproduce is useless."""
    options = whisper.decode_options(default_config().whisper)
    assert options["temperature"] == [0.0]


def test_an_empty_temperature_falls_back_to_zero() -> None:
    settings = replace(WhisperSettings(), temperature=())
    assert whisper.decode_options(settings)["temperature"] == [0.0]


def test_whisper_settings_survive_saving_and_reading(
        tmp_path: Path) -> None:
    """The store wrote out a hand-written list of keys, so a new setting
    quietly disappeared on the next save."""
    from dataclasses import fields

    from modules import config as config_module

    target = tmp_path / "config.json"
    original = replace(
        default_config(),
        whisper=replace(default_config().whisper,
                        temperature=(0.0, 0.4), no_speech_threshold=0.9,
                        log_prob_threshold=-2.0, vad_filter=True,
                        hallucination_silence_threshold=2.0))
    config_module.save_config(original, target)
    back = config_module.load_config(target)
    for field in fields(WhisperSettings):
        assert getattr(back.whisper, field.name) == \
            getattr(original.whisper, field.name), field.name


# --------------------------------------------------------------------------
# B313: placing skipped words on the vocal stem
# --------------------------------------------------------------------------

def _words(spec: list[tuple[str, float | None, float]]):
    """(text, start time or None, similarity) -> aligned words."""
    out = []
    for index, (text, start, sim) in enumerate(spec):
        out.append(AlignedWord(
            LyricWord(index=index, text=text, line=index // 4),
            start, None if start is None else start + 0.3,
            text if start is not None else None, sim))
    return tuple(out)


def _context(windows, monkeypatch):
    """Stand-in with a vocal stem whose active windows are fixed.

    Through ``monkeypatch``, so that the replacement is undone after the
    test - otherwise it carries over into tests that use the real
    vocal-stem analysis.
    """
    from modules import rhythm

    context = types.SimpleNamespace(
        config=types.SimpleNamespace(
            advanced=types.SimpleNamespace(vocal_analysis=True)),
        store=types.SimpleNamespace(get_step=lambda _name: None,
                                    set_meta=lambda *_a: None))
    monkeypatch.setattr(rhythm, "active_windows",
                        lambda *_a, **_k: windows)
    monkeypatch.setattr(pipeline, "ensure_original_vocals",
                        lambda _c: Path("fake.wav"))
    return context


def test_skipped_words_get_a_time(monkeypatch) -> None:
    aligned = _words([("een", 1.0, 1.0), ("twee", None, 0.0),
                      ("drie", None, 0.0), ("vier", 10.0, 1.0)])
    out = pipeline._place_skipped_on_energy(_context([(0.0, 12.0)], monkeypatch), aligned)
    assert all(w.start is not None for w in out)
    assert out[1].estimated and out[2].estimated
    assert 1.3 <= out[1].start < out[2].start <= 10.0


def test_good_couplings_stay_untouched(monkeypatch) -> None:
    """The hard requirement: a word that is coupled well we leave be."""
    aligned = _words([("een", 1.0, 1.0), ("twee", None, 0.0),
                      ("drie", 5.0, 0.9), ("vier", 10.0, 1.0)])
    out = pipeline._place_skipped_on_energy(_context([(0.0, 12.0)], monkeypatch), aligned)
    for original, new in zip(aligned, out):
        if original.sim >= pipeline._ESTIMATE_MAX_SIM:
            assert new == original, original.lyric.text


def test_a_weak_coupling_counts_as_skipped(monkeypatch) -> None:
    """"alle" on "la," with 0.25 says more about the desperation of the
    alignment than about the word; that one may be placed again."""
    aligned = _words([("een", 1.0, 1.0), ("alle", 9.5, 0.25),
                      ("vier", 10.0, 1.0)])
    out = pipeline._place_skipped_on_energy(_context([(0.0, 12.0)], monkeypatch), aligned)
    assert out[1].estimated and out[1].start < 9.5


def test_the_order_is_preserved(monkeypatch) -> None:
    aligned = _words([("a", 1.0, 1.0)] + [(f"w{i}", None, 0.0)
                                          for i in range(10)]
                     + [("z", 20.0, 1.0)])
    out = pipeline._place_skipped_on_energy(_context([(0.0, 25.0)], monkeypatch), aligned)
    times = [w.start for w in out if w.start is not None]
    assert times == sorted(times)


def test_silence_is_skipped(monkeypatch) -> None:
    """Words land in the sung stretches, not in the silence between."""
    aligned = _words([("a", 0.5, 1.0)] + [(f"w{i}", None, 0.0)
                                          for i in range(4)]
                     + [("z", 30.0, 1.0)])
    out = pipeline._place_skipped_on_energy(
        _context([(0.0, 1.0), (5.0, 9.0), (20.0, 24.0)], monkeypatch), aligned)
    for word in out[1:5]:
        assert (5.0 <= word.start <= 9.0) or (20.0 <= word.start <= 24.0), \
            word.start


def test_a_lone_anchor_that_demands_too_fast_singing_is_let_go(monkeypatch) -> None:
    """The measured Viva case: the lyrics word "muziek" coupled to a
    hallucinated "MUZIEK" with a perfect 1.00, in the middle of a gap.
    That one anchor squeezed twenty-eight words into three and a half
    seconds."""
    spec = [("start", 1.0, 1.0)]
    spec += [(f"a{i}", None, 0.0) for i in range(5)]
    spec += [("muziek", 30.0, 1.0)]                 # a loner in the gap
    spec += [(f"b{i}", None, 0.0) for i in range(28)]
    spec += [("eind", 33.5, 1.0)]
    aligned = _words(spec)
    out = pipeline._place_skipped_on_energy(_context([(0.0, 40.0)], monkeypatch), aligned)
    anchor = out[6]
    assert anchor.estimated, "het valse anker had losgelaten moeten worden"
    assert anchor.start < 30.0
    spans = [w.end - w.start for w in out if w.estimated]
    assert min(spans) > 0.2, "geen enkel woord in een fractie van een seconde"


def test_an_anchor_with_neighbours_is_never_let_go(monkeypatch) -> None:
    """A correct coupling rarely stands alone: its neighbours fit too.
    Such a group stays put, even when the window beside it is tight."""
    spec = [("start", 1.0, 1.0)]
    spec += [(f"a{i}", None, 0.0) for i in range(3)]
    spec += [("serenade", 30.0, 1.0), ("aan", 30.4, 1.0)]   # a small group
    spec += [(f"b{i}", None, 0.0) for i in range(28)]
    spec += [("eind", 33.5, 1.0)]
    aligned = _words(spec)
    out = pipeline._place_skipped_on_energy(_context([(0.0, 40.0)], monkeypatch), aligned)
    assert not out[4].estimated and out[4].start == 30.0
    assert not out[5].estimated and out[5].start == 30.4


def test_without_a_vocal_stem_nothing_changes() -> None:
    aligned = _words([("een", 1.0, 1.0), ("twee", None, 0.0)])
    context = types.SimpleNamespace(
        config=types.SimpleNamespace(
            advanced=types.SimpleNamespace(vocal_analysis=False)),
        store=types.SimpleNamespace(get_step=lambda _name: None))
    assert pipeline._place_skipped_on_energy(context, aligned) == aligned


def test_an_estimate_does_not_count_as_a_reliable_line() -> None:
    """An estimate must not quietly take on the weight of a measurement:
    the line would then be called reliable, be stretched by B194 and
    miss the energy placement of B209/B310."""
    word = AlignedWord(LyricWord(0, "la", 0), 1.0, 2.0, None, 0.0,
                       estimated=True)
    assert word.estimated is True
    normal = AlignedWord(LyricWord(0, "la", 0), 1.0, 2.0, "la", 1.0)
    assert normal.estimated is False


@pytest.mark.parametrize("count,window,feasible", [
    (2, 1.0, True),      # 2 words per second: fine
    (6, 1.0, True),      # exactly on the bound still counts as feasible
    (7, 1.0, False),     # above that it no longer does
    (28, 3.5, False),    # the measured Viva case
])
def test_the_bound_for_feasible_singing(count: int, window: float,
                                        feasible: bool) -> None:
    assert (count / window <= pipeline._MAX_WORDS_PER_SECOND) is feasible
