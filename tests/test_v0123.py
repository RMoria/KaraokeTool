"""Tests for v0.123.0: B387 - "Onbekend artefact: 'config:models'".

Steps 1.1 and 1.3 fell over on every EXISTING project with a KeyError
from ``dependencies.dependents()``. The cause was two years of two lists
drifting apart: B361 (v0.116.0) added ``config:models`` to the settings
fingerprint in ``pipeline._config_signature`` so that switching a model
off would invalidate the derived timing - but nobody put that name in the
derivation chain. ``dependents()`` raises on a name it does not know, on
purpose ("better a loud error than silently invalidating nothing"), and
that is exactly what it did.

It stayed invisible for five versions because nothing made the stored
fingerprint change. v0.121.0 added B380 to the register, the fingerprint
moved, and from that moment every project carrying an older signature
reported "config:models changed" and then crashed. New projects were fine
(fresh signature) and the whole 1.5.x panel never calls
``sync_input_changes`` - which is why the suite stayed green through two
releases while the program was broken for its actual user.

The repair is the boring half. The interesting half is the guard: the
existing check in ``test_v098`` reads ``set_step``/``set_meta`` calls out
of the source, and the ``config:`` keys never come from those - they are
a dict literal inside ``_config_signature``. So a whole category of key
was never checked at all. That hole is closed here by asking the function
itself instead of reading the source.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import dependencies, pipeline  # noqa: E402
from modules.config import default_config  # noqa: E402


# --------------------------------------------------------------------------
# The guard that was missing
# --------------------------------------------------------------------------

def test_every_settings_key_is_in_the_chain() -> None:
    """The guard for B387, and for the next one of its kind.

    Deliberately asks ``_config_signature`` for its real keys instead of
    grepping the source: the keys are a dict literal, so no pattern over
    ``set_step``-style calls can see them. That is precisely how this one
    got through.
    """
    signature = pipeline._config_signature(default_config())
    missing = sorted(k for k in signature if k not in dependencies.ARTEFACTS)
    assert not missing, (
        "settings keys not described in modules/dependencies.py: "
        + ", ".join(missing))


def test_the_chain_describes_no_settings_that_do_not_exist() -> None:
    """The other direction: a ``config:`` artefact nobody produces is a
    dead entry that quietly invalidates nothing."""
    signature = pipeline._config_signature(default_config())
    described = {name for name in dependencies.ARTEFACTS
                 if name.startswith("config:")}
    stale = sorted(described - set(signature))
    assert not stale, "described but never fingerprinted: " + ", ".join(stale)


def test_an_unknown_name_still_raises_loudly() -> None:
    """The repair must not be "catch the KeyError". A name that really
    does not exist has to keep going bang."""
    with pytest.raises(KeyError):
        dependencies.dependents(["config:does_not_exist"])


# --------------------------------------------------------------------------
# What config:models invalidates, and what it must NOT
# --------------------------------------------------------------------------

def test_switching_a_model_invalidates_coupling_and_timing() -> None:
    steps, _metas, _files = dependencies.invalidation_plan(["config:models"])
    assert {"word_coupling", "coupling", "timing"} <= set(steps)


def test_switching_a_model_does_not_force_a_new_transcription() -> None:
    """The read-path filters (B334/B342/B343) run when the cache is READ,
    not when it is written. A different model must therefore never cost
    the user a Whisper run - that would be half an hour for nothing.
    """
    steps, _metas, files = dependencies.invalidation_plan(["config:models"])
    assert "whisper_original" not in steps
    assert "whisper_karaoke" not in steps
    assert not [f for f in files if "transcription" in f]


def test_switching_a_model_does_not_throw_away_demucs() -> None:
    """Separating the stems costs minutes and has nothing to do with
    which timing model is on."""
    _steps, _metas, files = dependencies.invalidation_plan(["config:models"])
    assert not [f for f in files if "demucs" in f]


def test_the_models_artefact_is_a_source() -> None:
    """A settings group is a source, not something we derive."""
    artefact = dependencies.ARTEFACTS["config:models"]
    assert artefact.kind == dependencies.SOURCE
    assert artefact.sources == ()
    assert artefact.what


# --------------------------------------------------------------------------
# The path that actually crashed
# --------------------------------------------------------------------------

def _context(tmp_path):
    from dataclasses import replace

    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Proef")
    ensure_directories(paths)
    (paths.input_dir / "songtekst.txt").write_text("Regel een\n",
                                                   encoding="utf-8")
    config = default_config()
    config = replace(config, song=replace(config.song, title="Proef"))
    return pipeline.AppContext(paths=paths, config=config,
                               store=ProjectStore(paths.project_file))


def _remember(context, groups) -> None:
    """Store a settings fingerprint the way the app stores it."""
    context.store.set_step("config_signature", {"groups": dict(groups)})


def test_a_signature_from_before_the_models_entry_does_not_crash(
        tmp_path) -> None:
    """A project fingerprinted before B361 knows no ``config:models`` at
    all. Such a group is not compared (``group in kept``), so nothing is
    invalidated and nothing may crash either."""
    context = _context(tmp_path)
    signature = pipeline._config_signature(context.config)
    _remember(context, {k: v for k, v in signature.items()
                        if k != "config:models"})
    context.store.set_step("timing", {"dummy": True})
    assert pipeline.sync_input_changes(context) == ()
    assert context.store.get_step("timing") is not None


def test_the_case_that_crashed_on_the_user_machine(tmp_path) -> None:
    """THE regression. A project fingerprinted between v0.116.0 and
    v0.120.0 does know ``config:models``, and v0.121.0 moved that value
    by adding B380 to the register. From that moment the group was
    reported as changed and ``dependents()`` raised on a name that was
    not in the chain.
    """
    context = _context(tmp_path)
    signature = dict(pipeline._config_signature(context.config))
    signature["config:models"] = "de_stand_van_voor_B380"
    _remember(context, signature)
    context.store.set_step("timing", {"dummy": True})

    changed = pipeline.sync_input_changes(context)          # viel hier om

    assert "config:models" in changed
    assert context.store.get_step("timing") is None, \
        "de timing hoort te vervallen als de modelstand verandert"
