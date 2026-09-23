"""Tests for v0.124.0: B384, B385, B386 - and the B377 verdict.

Three repairs that came out of measuring rather than guessing, and one
decision that measuring settled the other way round from what the number
first suggested.

B377 is the interesting one. The yardstick went from 3.25 s to 3.32 s
when the vocal-stem referee shipped, and on Lied_P it cost
0.49 s - which reads as "this model is a regression". Per line it turns
out to be nothing of the sort: 45 of the 50 lines are identical with the
model on or off, none get better, and five consecutive lines (28 to 32)
carry all of it, three of them 19.88 of the 21.82 seconds. Those five sit
in one stretch of the song. And what B377 drops there is a single
segment: "Thank you." at 167.07-167.87, with 0 of its 2 words on measured
singing, sitting in a 22-second hole where nobody sings at all. That is
not a threshold mistake, it is the model doing exactly its job.

The damage is real anyway, and the reason is worth writing down: the
false anchor was load-bearing. With it gone there is no transcription at
all between 155.64 and 194.98, and the interpolation drifts - line 31
lands 14 seconds late. So B377 stays on and the fallback is what needs
fixing. Where the measurement points is recorded in B392 (see the
development log): of the eight lines with no transcription within a
second, four sit within 0.22 s of a measured vocal onset and two within
0.03 s - including the two worst-drifting ones. The anchors are already
measured, they are just not used.
"""
from __future__ import annotations

import inspect
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import model_register, rhythm, test_panel  # noqa: E402


# --------------------------------------------------------------------------
# B384 - the energy cache could never hit
# --------------------------------------------------------------------------

def test_the_measurement_keeps_one_work_directory_per_project() -> None:
    """A fresh temporary directory per call gave the vocal stem a new
    path every time, and the cache key in ``rhythm`` contains the path.
    Result: one miss and a 50 MB copy on every single measurement."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "regression_b384", root / "tools" / "timing_regression.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    first = module._work_dir("Proef")
    assert module._work_dir("Proef") == first, "same project, same folder"
    assert module._work_dir("Ander") != first, "other project, other folder"


def test_the_cache_key_is_why_it_matters() -> None:
    """Pins the reason, so the next reader does not 'simplify' the work
    directory back to a fresh one."""
    source = inspect.getsource(rhythm._rms_envelope)
    assert "stat.st_mtime" in source and "str(audio_path)" in source, \
        "the key holds the path, so that path has to be stable"


def test_the_vocal_stem_is_linked_and_not_copied() -> None:
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "tools" / "timing_regression.py").read_text(
        encoding="utf-8")
    assert "os.link(" in source, "a hard link costs no disk space"
    assert "shutil.copy2" in source, "and a fallback across volumes"
    assert importlib.util  # noqa: B018 - import used for the path only


# --------------------------------------------------------------------------
# B385 - bailing out is not the same as having run
# --------------------------------------------------------------------------

def test_a_trial_that_cannot_measure_raises_instead_of_returning() -> None:
    """The whole point: a returned list is indistinguishable from a real
    result, and that is how 1.5.11a booked twenty versions of silence for
    a measurement of 0.2 seconds that produced a table of zeros."""
    source = inspect.getsource(test_panel)
    for spot in ("heavy_needs_matrix", "heavy_no_clusters",
                 "heavy_no_measurable", "heavy_too_few_songs",
                 "heavy_probe_nowhere"):
        where = source.index(spot)
        before = source[max(0, where - 200):where]
        assert "TrialSkipped" in before, f"{spot} should drop out"


def test_the_reason_still_reaches_the_report() -> None:
    """Not counting as a run must not mean saying nothing."""
    skipped = test_panel.TrialSkipped(["omdat dit en dat"])
    assert skipped.lines == ["omdat dit en dat"]
    source = inspect.getsource(test_panel.heavy_trial)
    assert "skipped.lines" in source


def test_a_skipped_trial_records_no_duration() -> None:
    """The version threshold reads the durations, so recording one is
    exactly what booked the holiday."""
    source = inspect.getsource(test_panel.heavy_trial)
    caught = source.index("except TrialSkipped")
    remembered = source.index("remember_duration")
    assert caught < remembered, "drop out first, only then keep the time"
    tail = source[caught:remembered]
    assert "continue" in tail, "a dropout skips the keeping"


# --------------------------------------------------------------------------
# B386 - probe where there is something to probe
# --------------------------------------------------------------------------

def test_choosing_costs_no_whisper_run() -> None:
    """The choice leans on 1.5.8's machinery, which reads word times
    against measured singing. Probing badly costs half an hour; choosing
    well costs seconds."""
    source = inspect.getsource(test_panel._gaps_in)
    assert "_vocal_windows" in source and "load_segments" in source
    assert "whisper" not in source.lower()


def test_nowhere_to_probe_is_a_skip_and_not_a_verdict(tmp_path) -> None:
    """It used to report "no gap" about whichever song happened to be
    selected, which reads as an answer while nothing was measured."""
    from dataclasses import replace

    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Leeg")
    ensure_directories(paths)
    config = default_config()
    config = replace(config, song=replace(config.song, title="Leeg"))
    context = pipeline.AppContext(paths=paths, config=config,
                                  store=ProjectStore(paths.project_file))
    with pytest.raises(test_panel.TrialSkipped):
        test_panel.chunk_trial(context, lambda *a, **k: None,
                               lambda: False)


# --------------------------------------------------------------------------
# B377 - stays on, and the register says so
# --------------------------------------------------------------------------

def test_the_referee_stays_on() -> None:
    """Measured per line the model is right: it drops one segment on
    Lied_P, "Thank you." on 0 of 2 words on measured singing, in
    a 22-second hole. The 0.49 s is the price of removing a lie the
    interpolation was leaning on - not a reason to keep lying."""
    model = model_register.by_code("B377")
    assert model is not None
    assert model.default_on


def test_the_threshold_was_not_quietly_widened() -> None:
    """The tempting repair - lower the share until the segment survives -
    would have kept the hallucination. Pin the number."""
    from modules import pipeline

    assert pipeline._SUNG_MIN_SHARE == pytest.approx(0.34)
