"""Make the ``modules`` package importable from the tests, and keep the
test run out of the user's own documents (B440).

The second part is the newer one and it was found the hard way. Running
the suite quietly overwrote ``docs/modelcombinaties.md`` - the real
report of a heavy trial that had taken the user's laptop the better part
of an hour - because two tests walk every action in the panel and only
redirected the matrix report, not the combination report. The result of
a night's measuring was replaced by the output of an empty test project,
and nothing said so.

Redirecting per test is exactly the kind of thing you remember fourteen
times and forget the fifteenth, so it is not done per test any more. The
constants that point into ``docs/`` are moved aside for EVERY test here.
A test that really wants to read the real file can still do so by path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


#: ``(module name, attribute, file name under the temporary folder)`` for
#: everything a test could write into the user's documents folder.
_REDIRECTED = (
    ("modules.test_panel", "MATRIX_REPORT", "modelmatrix.md"),
    ("modules.test_panel", "COMBINATION_REPORT", "modelcombinaties.md"),
    ("modules.test_panel", "CHUNK_WORDS", "knipwoorden.txt"),
    ("modules.test_panel", "REPORT_DIR", "verslagen"),
    ("modules.test_history", "HISTORY_FILE", "testhistorie.json"),
    ("modules.versions", "VERSION_LOG", "pakketversies.json"),
    ("modules.versions", "UPDATE_FILE", "updates.json"),
)


@pytest.fixture(autouse=True)
def _keep_the_real_documents(tmp_path, monkeypatch):
    """Point every report path at a throwaway folder."""
    import importlib

    for module_name, attribute, file_name in _REDIRECTED:
        try:
            module = importlib.import_module(module_name)
        except ImportError:                  # pragma: no cover - no Qt
            continue
        if hasattr(module, attribute):
            monkeypatch.setattr(module, attribute, tmp_path / file_name)
    # B534: the report of a run that is busy points into the previous
    # test's throwaway folder, and that folder is gone.
    try:
        panel = importlib.import_module("modules.test_panel")
    except ImportError:                          # pragma: no cover - no Qt
        panel = None
    if panel is not None:
        monkeypatch.setattr(panel, "TRIAL_REPORT", None)
    yield


@pytest.fixture(autouse=True)
def _keep_the_register_clean():
    """Put every neutralised model back after EVERY test (B536).

    A model that is off is switched off by REPLACING a function on its
    module, and that replacement stays there for the rest of the
    interpreter. As long as only B213 and B380 were off nobody noticed,
    because no test measured those functions - but the moment the
    hallucination filter went off (B536) fourteen tests of that very
    filter started failing, and only when the whole suite ran. A test
    that switches models must not be able to poison the tests that come
    after it, and remembering that per file is exactly the kind of thing
    that gets forgotten - so it happens here, for everything.

    Before AND after. Only afterwards is not enough: this fixture breaks
    down BEFORE monkeypatch does, so a test that switches a model off
    and then monkeypatches that same function keeps the replacement as
    "the original" and monkeypatch puts it back afterwards. Cleaning up
    beforehand as well means every test starts on the real functions
    whatever leaked.
    """
    from modules import model_register

    model_register.restore_all()
    model_register.apply_settings({})
    yield
    model_register.restore_all()
    model_register.apply_settings({})


@pytest.fixture
def demucs_installed(monkeypatch, tmp_path):
    """A machine that has Demucs, on a machine that does not (B553).

    Asked for by name, never automatic: it is an arrangement, and an
    arrangement that switches itself on is the same thing as not
    knowing what you are testing.

    Stubbed are exactly the two places ``modules.separation`` touches
    the outside world - whether the package is there
    (``models.is_available("demucs")``) and the subprocess that would
    run it (``proc.run``). Everything else runs for real: the command
    building, the work folder, finding the stems, copying them into the
    fixed place, the marker and its staleness check. Stubbing higher
    up, at ``separate_cached`` itself, is what a first attempt did, and
    then the test is about the stub instead of about the code - it also
    breaks ``test_demucs_separate_cached_reuses``, which is about that
    very function.

    This exists because the whole separation branch of
    ``detect_track`` and every line of ``separate_cached`` beyond the
    first call ran on nobody's machine: not here, because Demucs is not
    installed, and not in a measurement run, because those do not run
    the suite. B545 was the bill for that.

    Yields a dict with ``runs`` (the commands that were "run") and
    ``frames`` (how long the fake stems are), so a test can see whether
    Demucs was asked at all and can make the next separation differ
    from the last.
    """
    import wave

    from modules import models, proc

    state = {"runs": [], "frames": 11025}
    real_is_available = models.is_available
    real_run = proc.run

    def _write_wav(path: Path, frames: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(22_050)
            handle.writeframes(b"\x10\x27" * 2 * frames)

    def fake_is_available(name):
        return True if name == "demucs" else real_is_available(name)

    def fake_run(command, *args, **kwargs):
        parts = [str(part) for part in command]
        if "demucs" not in parts:          # ffmpeg and the rest stay real
            return real_run(command, *args, **kwargs)
        state["runs"].append(parts)
        out = Path(parts[parts.index("-o") + 1])
        model = parts[parts.index("-n") + 1]
        source = Path(parts[-1])
        stem = out / model / source.stem
        _write_wav(stem / "vocals.wav", state["frames"])
        _write_wav(stem / "no_vocals.wav", max(1, state["frames"] // 2))

        class _Result:
            returncode = 0
            stdout = stderr = ""

        return _Result()

    monkeypatch.setattr(models, "is_available", fake_is_available)
    monkeypatch.setattr(proc, "run", fake_run)
    return state
