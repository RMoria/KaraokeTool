"""Tests for modules.whisper (serialisation and output, without a model)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from modules.whisper import (
    CSV_DELIMITER,
    Segment,
    Word,
    WhisperError,
    load_segments,
    save_segments,
    segments_from_dicts,
    segments_to_dicts,
    write_outputs,
)


def _example_segments() -> tuple[Segment, ...]:
    return (
        Segment(index=0, text="Kedeng kedeng", start=1.0, end=2.5, words=(
            Word(text="Kedeng", start=1.0, end=1.7, confidence=0.95),
            Word(text="kedeng", start=1.8, end=2.5, confidence=0.91),
        )),
        Segment(index=1, text="oe oe", start=3.0, end=4.0, words=(
            Word(text="oe", start=3.0, end=3.4, confidence=0.42),
            Word(text="oe", start=3.6, end=4.0, confidence=0.88),
        )),
    )


def test_serialisation_roundtrip() -> None:
    segments = _example_segments()
    assert segments_from_dicts(segments_to_dicts(segments)) == segments


def test_save_and_load_segments(tmp_path: Path) -> None:
    segments = _example_segments()
    cache = tmp_path / "transcriptie.json"
    save_segments(segments, cache)
    assert load_segments(cache) == segments


def test_load_segments_corrupt(tmp_path: Path) -> None:
    cache = tmp_path / "transcriptie.json"
    cache.write_text("{kapot", encoding="utf-8")
    with pytest.raises(WhisperError):
        load_segments(cache)


def test_write_outputs_creates_all_files(tmp_path: Path) -> None:
    write_outputs(_example_segments(), {"model": "large-v3"}, tmp_path)
    for name in ("transcript.txt", "words.csv", "woorden.json",
                 "segmenten.json", "run_info.json"):
        assert (tmp_path / name).exists(), name


def test_transcript_content(tmp_path: Path) -> None:
    write_outputs(_example_segments(), {}, tmp_path)
    lines = (tmp_path / "transcript.txt").read_text(encoding="utf-8").splitlines()
    assert lines == ["Kedeng kedeng", "oe oe"]


def test_words_csv_content(tmp_path: Path) -> None:
    write_outputs(_example_segments(), {}, tmp_path)
    with (tmp_path / "words.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=CSV_DELIMITER))
    assert rows[0] == ["word", "start", "end", "confidence", "segment"]
    assert len(rows) == 5  # header + 4 words
    assert rows[1][0] == "Kedeng"
    assert rows[3][4] == "1"  # segment index of 'oe'


def test_words_json_content(tmp_path: Path) -> None:
    write_outputs(_example_segments(), {}, tmp_path)
    words = json.loads((tmp_path / "woorden.json").read_text(encoding="utf-8"))
    assert len(words) == 4
    assert words[2] == {"text": "oe", "start": 3.0, "end": 3.4,
                        "confidence": 0.42, "segment": 1}


def _clean_hf_env(monkeypatch, home: Path) -> None:
    """A known Hugging Face environment, whatever the machine has set.

    ``Path.home()`` reads ``HOME`` on Linux and ``USERPROFILE`` on
    Windows, so both go; the three cache variables are emptied because
    a machine that has one of them set points at a filled cache that
    would answer the question instead of the test.
    """
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "XDG_CACHE_HOME",
                 "HF_HOME"):
        monkeypatch.delenv(name, raising=False)


def test_model_cached_reads_the_cache_that_will_be_used(
        tmp_path, monkeypatch) -> None:
    """B545: the folder faster-whisper downloads into decides, not the
    default one.

    The old code built the hub folder out of ``HF_HOME`` and fell back
    to ``~/.cache/huggingface/hub`` when that did not exist yet - which
    is precisely when the model still has to come down. The middle
    assertion is the one that pins it: a filled default cache, an
    ``HF_HOME`` pointing somewhere else that is still empty. The old
    code answered True there and kept the download message away.
    """
    from modules.config import WhisperSettings
    from modules.whisper import model_cached

    home = tmp_path / "home"
    (home / ".cache" / "huggingface" / "hub"
     / "models--Systran--faster-whisper-large-v3").mkdir(parents=True)
    _clean_hf_env(monkeypatch, home)
    # model_cached reads a model name that IS a folder as a model on
    # disk, so run from somewhere that certainly has no folder called
    # large-v3 - otherwise this test answers about the current
    # directory instead of about the cache.
    monkeypatch.chdir(tmp_path)
    settings = WhisperSettings(model="large-v3")

    assert model_cached(settings) is True  # the default cache holds it

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("HF_HOME", str(elsewhere))
    assert model_cached(settings) is False

    (elsewhere / "hub"
     / "models--Systran--faster-whisper-large-v3").mkdir(parents=True)
    assert model_cached(settings) is True


def test_a_half_downloaded_model_is_not_cached(tmp_path, monkeypatch) -> None:
    """B547: an interrupted download is exactly what the message is for.

    huggingface_hub writes the pieces as ``blobs/<sha>.incomplete``.
    The old check accepted any folder whose name held the model, so
    closing the app halfway and starting it again gave no message at
    all and a window that looks frozen for ten minutes.
    """
    from modules.config import WhisperSettings
    from modules.whisper import model_cached

    home = tmp_path / "home"
    home.mkdir()
    _clean_hf_env(monkeypatch, home)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    model = (tmp_path / "hf" / "hub"
             / "models--Systran--faster-whisper-large-v3")
    (model / "blobs").mkdir(parents=True)
    settings = WhisperSettings(model="large-v3")

    (model / "blobs" / "abc.incomplete").write_text("x", encoding="utf-8")
    assert model_cached(settings) is False

    (model / "blobs" / "abc.incomplete").unlink()
    (model / "blobs" / "abc").write_text("x", encoding="utf-8")
    assert model_cached(settings) is True


def test_a_neighbouring_model_is_not_this_model(tmp_path, monkeypatch) -> None:
    """B547: large-v3-turbo is another model, another download."""
    from modules.config import WhisperSettings
    from modules.whisper import model_cached

    home = tmp_path / "home"
    home.mkdir()
    _clean_hf_env(monkeypatch, home)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    hub = tmp_path / "hf" / "hub"
    (hub / "models--Systran--faster-whisper-large-v3-turbo").mkdir(
        parents=True)

    assert model_cached(WhisperSettings(model="large-v3")) is False
    assert model_cached(WhisperSettings(model="large-v3-turbo")) is True
    # And the whole repository name finds it just as well.
    assert model_cached(WhisperSettings(
        model="Systran/faster-whisper-large-v3-turbo")) is True


def test_the_three_models_the_app_offers_are_found(
        tmp_path, monkeypatch) -> None:
    """B547: `distil-large-v3` is one of the three in the drop-down.

    Its folder is `models--Systran--faster-distil-whisper-large-v3`:
    the maker put `whisper` in the MIDDLE of the name, so a rule that
    wants the model in one piece never finds it and the download
    message would show on every single run. The pieces have to appear
    in order, not next to each other - and the folder still has to end
    on the last of them, which is what keeps `-turbo` out.
    """
    from modules.config import WhisperSettings
    from modules.whisper import model_cached

    home = tmp_path / "home"
    home.mkdir()
    _clean_hf_env(monkeypatch, home)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    hub = tmp_path / "hf" / "hub"
    for folder in ("models--Systran--faster-whisper-large-v3",
                   "models--Systran--faster-distil-whisper-large-v3",
                   "models--Systran--faster-whisper-small"):
        (hub / folder).mkdir(parents=True)

    for model in ("large-v3", "distil-large-v3", "small"):
        assert model_cached(WhisperSettings(model=model)) is True, model
    # Neighbours of those three are still not those three.
    for model in ("large-v3-turbo", "medium", "small.en"):
        assert model_cached(WhisperSettings(model=model)) is False, model


def test_hub_cache_dir_follows_the_whole_order(tmp_path, monkeypatch) -> None:
    """B545: five steps, and every one of them in its place."""
    from modules.whisper import hub_cache_dir

    home = tmp_path / "home"
    home.mkdir()
    _clean_hf_env(monkeypatch, home)
    assert hub_cache_dir() == home / ".cache" / "huggingface" / "hub"

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert hub_cache_dir() == tmp_path / "xdg" / "huggingface" / "hub"

    monkeypatch.setenv("HF_HOME", str(tmp_path / "hfhome"))
    assert hub_cache_dir() == tmp_path / "hfhome" / "hub"

    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", str(tmp_path / "legacy"))
    assert hub_cache_dir() == tmp_path / "legacy"

    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    assert hub_cache_dir() == tmp_path / "hub"


def test_hub_cache_dir_takes_an_empty_variable_as_set(
        tmp_path, monkeypatch) -> None:
    """B545: set but empty is set, because that is what os.getenv says.

    ``set HF_HUB_CACHE=%MODELDIR%`` with an undefined ``MODELDIR`` is
    an ordinary Windows accident and leaves exactly this. The download
    then goes to the working directory; skipping the empty variable
    would send this answer to the home cache, find an older model there
    and keep the message away - the very thing B545 is about.
    """
    from modules.whisper import hub_cache_dir

    home = tmp_path / "home"
    home.mkdir()
    _clean_hf_env(monkeypatch, home)
    monkeypatch.setenv("HF_HOME", "")
    assert hub_cache_dir() == Path("hub")

    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", "")
    assert hub_cache_dir() == Path(".")

    monkeypatch.setenv("HF_HUB_CACHE", "")
    assert hub_cache_dir() == Path(".")


def test_hub_cache_dir_expands_a_tilde(tmp_path, monkeypatch) -> None:
    """B545: huggingface_hub expands it, so a literal ~ in HF_HOME is a
    real folder and not a folder called '~'."""
    from modules.whisper import hub_cache_dir

    home = tmp_path / "home"
    home.mkdir()
    _clean_hf_env(monkeypatch, home)
    monkeypatch.setenv("HF_HOME", "~/models")
    assert hub_cache_dir() == home / "models" / "hub"


def test_hub_cache_dir_agrees_with_huggingface_hub(monkeypatch) -> None:
    """B545: the order is copied, so it can drift.

    ``hub_cache_dir`` deliberately does not import huggingface_hub -
    the answer has to be there even when it is not installed. The price
    is a copy, and this is what keeps the copy honest on a machine
    where the library IS there. The cases are the ones a copy gets
    wrong: a tilde and a variable in each of the four names (the legacy
    one was expanded nowhere in the first version of this function),
    and the set-but-empty value that ``os.getenv`` hands back as a
    value. The constants are computed at import time, hence the reload.
    """
    import importlib

    constants = pytest.importorskip("huggingface_hub.constants")
    if not hasattr(constants, "HF_HUB_CACHE"):  # pragma: no cover
        pytest.skip("this huggingface_hub does not have HF_HUB_CACHE")
    from modules.whisper import hub_cache_dir

    names = ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HOME",
             "XDG_CACHE_HOME")
    cases = ({},
             {"XDG_CACHE_HOME": "~/xdgcache"},
             {"HF_HOME": "~/models"},
             {"HUGGINGFACE_HUB_CACHE": "~/legacymodels"},
             {"HF_HUB_CACHE": "~/hubmodels"},
             {"HF_HOME": "$HOME/var"},
             {"HUGGINGFACE_HUB_CACHE": "$HOME/legacyvar"},
             {"HF_HUB_CACHE": ""},
             {"HUGGINGFACE_HUB_CACHE": ""},
             {"HF_HOME": ""},
             {"XDG_CACHE_HOME": ""},
             {"HF_HUB_CACHE": "", "HUGGINGFACE_HUB_CACHE": "keep"},
             {"HUGGINGFACE_HUB_CACHE": "", "HF_HOME": "keep"},
             {"HF_HUB_CACHE": "hub", "HUGGINGFACE_HUB_CACHE": "legacy",
              "HF_HOME": "home", "XDG_CACHE_HOME": "xdg"})
    try:
        for case in cases:
            for name in names:
                monkeypatch.delenv(name, raising=False)
            for name, value in case.items():
                monkeypatch.setenv(name, value)
            importlib.reload(constants)
            assert hub_cache_dir() == Path(constants.HF_HUB_CACHE), case
    finally:
        # monkeypatch puts the environment back by itself, but the
        # constants were computed against the last case and stay that
        # way until they are read again.
        monkeypatch.undo()
        importlib.reload(constants)


def test_collect_segments_cancels() -> None:
    """B86: _collect_segments stops with CancelledError as soon as
    cancelled()."""
    from modules.whisper import CancelledError, _collect_segments

    class _Raw:
        def __init__(self, end: float) -> None:
            self.start, self.end, self.text, self.words = 0.0, end, "a", ()

    with pytest.raises(CancelledError):
        _collect_segments(iter([_Raw(1.0), _Raw(2.0)]), 10.0, None,
                          lambda: True)
