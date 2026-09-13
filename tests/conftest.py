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
