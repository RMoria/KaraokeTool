"""Tests for v0.98.0: B311 - the derivation chain.

The most important test in this file is
``test_every_step_and_meta_is_in_the_chain``. It does not guard a bug
but a WORKING METHOD: whoever adds a new step or meta without deciding
where it belongs in the chain gets red now, instead of silently stale
data half a year from now.
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from modules import dependencies as deps
from modules import filesystem, pipeline
from modules.config import AppConfig
from modules.filesystem import ProjectPaths, ProjectStore


# --------------------------------------------------------------------------
# The chain itself
# --------------------------------------------------------------------------

def test_chain_has_no_cycle() -> None:
    """A derivative must never depend on itself by some detour - the
    invalidation would then never stop."""
    color: dict[str, str] = {}

    def visit(name: str, path: list[str]) -> list[str] | None:
        if color.get(name) == "busy":
            return path + [name]
        if color.get(name) == "done":
            return None
        color[name] = "busy"
        for source in deps.ARTEFACTS[name].sources:
            found = visit(source, path + [name])
            if found:
                return found
        color[name] = "done"
        return None

    for name in deps.ARTEFACTS:
        cycle = visit(name, [])
        assert cycle is None, f"cycle: {' -> '.join(cycle)}"


def test_every_source_exists() -> None:
    """Every source named must itself be on the map as well."""
    for artefact in deps.ARTEFACTS.values():
        for source in artefact.sources:
            assert source in deps.ARTEFACTS, \
                f"{artefact.name} points at unknown source {source}"


def test_every_artefact_is_described() -> None:
    """Without a description the map cannot be read and is worthless."""
    for artefact in deps.ARTEFACTS.values():
        assert artefact.what.strip(), f"{artefact.name} has no description"


def test_every_file_artefact_yields_paths() -> None:
    paths = ProjectPaths(root=Path("/tmp/x"), song="lied")
    for artefact in deps.ARTEFACTS.values():
        if artefact.kind != deps.FILE:
            continue
        found = deps.paths_for(artefact.name, paths)
        assert found, f"{artefact.name} yields no paths"


def test_only_sources_have_no_origin() -> None:
    """A derivative without a source is a derivative that never goes
    stale - which is nearly always a mistake. The exceptions are
    explicit."""
    standalone = {name for name, a in deps.ARTEFACTS.items()
                  if not a.sources and a.kind != deps.SOURCE}
    # B353: "video" belongs here on purpose. The video that was made is
    # an end product; a later change makes it outdated, not invalid, and
    # that judgement is the user's.
    # B413: "input_last_dir" belongs here too - where the user fetched
    # his files from does not go stale because of something the program
    # works out.
    assert standalone == {"display_name", "input_names", "input_last_dir",
                          "video_titles", "config_signature", "video"}


# --------------------------------------------------------------------------
# The guard: is every key from the code on the map?
# --------------------------------------------------------------------------

_STEP_CALL = re.compile(
    r"""(?:set|get|clear)_step\(\s*f?["']([^"']+)["']""")
_META_CALL = re.compile(
    r"""(?:set|get|clear)_meta\(\s*f?["']([^"']+)["']""")


#: Placeholders in f-strings, written out to the real key.
_PLACEHOLDERS = ("{track}", "{stem}", "{TRACK_ORIGINAL}", "{TRACK_KARAOKE}")


def _module_sources() -> list[str]:
    modules_dir = Path(__file__).resolve().parents[1] / "modules"
    return [path.read_text(encoding="utf-8")
            for path in sorted(modules_dir.glob("*.py"))]


def _keys_in_code(pattern: re.Pattern[str]) -> set[str]:
    """Every key that is used somewhere in modules/.

    ``{track}``/``{stem}`` and the constant names are written out over
    the two tracks, because that is how they stand in project.json too.
    """
    found: set[str] = set()
    for text in _module_sources():
        for key in pattern.findall(text):
            if any(p in key for p in _PLACEHOLDERS):
                for track in deps.TRACKS:
                    written = key
                    for placeholder in _PLACEHOLDERS:
                        written = written.replace(placeholder, track)
                    found.add(written)
            else:
                found.add(key)
    return found


def _quoted_literals() -> set[str]:
    """Every text in modules/ that stands between quotes.

    A step does not have to run through ``set_step("name")``: the
    fingerprint steps sit in a table. For the reverse check ("does the
    map describe only things that really exist?") every literal text
    therefore counts."""
    literal = re.compile(r"""["']([^"'\n]+)["']""")
    found: set[str] = set()
    for text in _module_sources():
        found.update(literal.findall(text))
    return found


def test_every_step_and_meta_is_in_the_chain() -> None:
    """THE guard of this whole design.

    Up to and including v0.97 the invalidation sat in three functions as
    hand-written little lists. Every new step had to be added to the
    right list by someone, and that went wrong time after time: the
    cluster selection survived new audio, the manually marked fragments
    kept their times on a timeline that no longer existed, and the
    project-wide markings survived everything.

    This test makes that structurally impossible: if the code uses a step
    or meta that is not in ``dependencies.ARTEFACTS``, it turns red. Add
    a step and you have to decide what it is derived from - exactly the
    question that used to be skipped.
    """
    steps = _keys_in_code(_STEP_CALL)
    metas = _keys_in_code(_META_CALL)
    known = set(deps.ARTEFACTS)
    missing = sorted((steps | metas) - known)
    assert not missing, (
        "these step/meta keys are not in the derivation chain "
        f"(modules/dependencies.py): {missing}")


def test_the_chain_describes_no_invented_keys() -> None:
    """The other way round just as much: a step on the map that is no
    longer used anywhere is dead administration."""
    used = (_keys_in_code(_STEP_CALL) | _keys_in_code(_META_CALL)
            | _quoted_literals())
    described = {name for name, a in deps.ARTEFACTS.items()
                 if a.kind in (deps.STEP, deps.META)}
    unused = sorted(described - used)
    assert not unused, (
        f"these artefacts are not used anywhere any more: {unused}")


# --------------------------------------------------------------------------
# What follows from a change?
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source,expected", [
    ("input:original", "whisper_original"),
    ("input:original", "clusters_original"),
    ("input:original", "karaoke"),
    ("input:original", "karaoke_from_original"),
    ("input:original", "vocal_onset_s"),
    ("input:karaoke", "fragment_exclusions"),
    ("input:karaoke", "restore_fragments"),
    ("input:karaoke", "align"),
    ("input:lyrics", "word_coupling"),
    ("input:lyrics", "stress_anchors"),
    ("input:lyrics", "original_overrides"),
    ("input:lyrics", "language_choice"),
    ("input:karaoke_text", "coupling"),
    ("input:karaoke_text", "timing"),
    ("config:forced_alignment", "whisper_original"),
    ("config:karaoke", "karaoke"),
    ("clusters_original", "karaoke"),
    ("word_coupling", "timing"),
])
def test_change_carries_through(source: str, expected: str) -> None:
    """The holes from the review, one by one: this MUST be dropped."""
    assert expected in deps.dependents([source])


@pytest.mark.parametrize("source,spared", [
    # Another parody text does not touch the transcription or the manual
    # word couplings: those are about the original.
    ("input:karaoke_text", "whisper_original"),
    ("input:karaoke_text", "word_coupling"),
    ("input:karaoke_text", "clusters_original"),
    # Another damping setting does not touch the transcription.
    ("config:karaoke", "whisper_original"),
    ("config:karaoke", "timing"),
    # The vocal-stem/anchor settings do not touch the transcription.
    ("config:timing", "whisper_original"),
    ("config:timing", "karaoke"),
    # A new logo only makes the video outdated.
    ("input:logo", "timing"),
    ("input:logo", "karaoke"),
    # A fresh karaoke transcription costs no handwork on the original.
    ("whisper_karaoke", "word_coupling"),
    ("whisper_karaoke", "transcript_override"),
])
def test_change_deliberately_does_NOT_carry_through(source: str,
                                                   spared: str) -> None:
    """Throwing away too much costs the user handwork and is just as
    wrong as throwing away too little. These pairs belong apart."""
    assert spared not in deps.dependents([source])


def test_spared_branch_stays() -> None:
    """'Karaoke made from the original': the separated vocals of the
    original stay valid and must not go - that separation costs minutes
    per song (B248)."""
    steps, _metas, files = deps.invalidation_plan(
        ["input:karaoke"], keep=["cache:demucs_original"])
    assert "cache:demucs_original" not in files
    assert "cache:original_vocals" not in files
    assert "whisper_original" not in steps
    assert "cache:karaoke_wav" in files


def test_unknown_artefact_is_a_loud_error() -> None:
    """Rather an exception than silently invalidating nothing."""
    with pytest.raises(KeyError):
        deps.dependents(["input:does_not_exist"])


# --------------------------------------------------------------------------
# The fingerprints: editing outside the app is noticed
# --------------------------------------------------------------------------

def _context(tmp_path: Path) -> pipeline.AppContext:
    paths = ProjectPaths(root=tmp_path, song="lied")
    paths.input_dir.mkdir(parents=True, exist_ok=True)
    paths.settings_dir.mkdir(parents=True, exist_ok=True)
    paths.cache_dir.mkdir(parents=True, exist_ok=True)
    store = ProjectStore(paths.project_file)
    return pipeline.AppContext(paths=paths, config=AppConfig(), store=store)


def test_lyrics_edited_outside_the_app_are_noticed(
        tmp_path: Path) -> None:
    """The real scenario: you fix a line in a text editor. Up to and
    including v0.97 the program noticed that nowhere, and the timing and
    the manual couplings kept pointing at the old text."""
    context = _context(tmp_path)
    lyrics = context.paths.input_dir / "songtekst.txt"
    lyrics.write_text("een twee drie\n", encoding="utf-8")
    pipeline.remember_sources(context)

    context.store.set_step("timing", {"lines": 3})
    context.store.set_step("word_coupling", {"pins": {"0": [1]}})
    context.store.set_step("coupling", {"mapping": {}})

    assert pipeline.sync_input_changes(context) == ()      # nothing changed
    assert context.store.get_step("timing") is not None

    lyrics.write_text("een twee vier\n", encoding="utf-8")
    assert pipeline.sync_input_changes(context) == ("input:lyrics",)
    assert context.store.get_step("timing") is None
    assert context.store.get_step("word_coupling") is None
    assert context.store.get_step("coupling") is None


def test_karaoke_text_edited_outside_the_app_spares_the_coupling(
        tmp_path: Path) -> None:
    """And the other way round: changing the parody text must NOT cost
    the manual word couplings."""
    context = _context(tmp_path)
    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "regel een\n", encoding="utf-8")
    pipeline.remember_sources(context)
    context.store.set_step("word_coupling", {"pins": {"0": [1]}})
    context.store.set_step("timing", {"lines": 1})

    (context.paths.input_dir / "karaoketekst.txt").write_text(
        "regel twee\n", encoding="utf-8")
    assert pipeline.sync_input_changes(context) == ("input:karaoke_text",)
    assert context.store.get_step("timing") is None
    assert context.store.get_step("word_coupling") is not None


def test_changing_a_setting_is_noticed(tmp_path: Path) -> None:
    """Switching forced alignment off did change the word times but
    invalidated nothing: the transcription cache kept on hitting."""
    context = _context(tmp_path)
    pipeline.remember_sources(context)
    context.store.set_step("whisper_original", {"segments": 12})

    off = replace(context.config,
                  advanced=replace(context.config.advanced,
                                   forced_alignment=False))
    context = pipeline.AppContext(paths=context.paths, config=off,
                                  store=context.store)
    assert pipeline.sync_input_changes(context) == \
        ("config:forced_alignment",)
    assert context.store.get_step("whisper_original") is None


def test_unchanged_project_throws_nothing_away(tmp_path: Path) -> None:
    """The opposite risk: throwing everything away at every step because
    the fingerprint has never been stored yet."""
    context = _context(tmp_path)
    (context.paths.input_dir / "songtekst.txt").write_text(
        "een twee\n", encoding="utf-8")
    context.store.set_step("timing", {"lines": 2})
    # First time: no fingerprints known yet -> throw nothing away.
    assert pipeline.sync_input_changes(context) == ()
    assert context.store.get_step("timing") is not None
    # Second time, unchanged: still throw nothing away.
    assert pipeline.sync_input_changes(context) == ()
    assert context.store.get_step("timing") is not None


def test_invalidation_removes_the_files_too(tmp_path: Path) -> None:
    """Clearing a step without clearing the file leaves an outdated
    result on disk that is simply used again later (the old
    karaoke_edit.mp3 that the video took as its source)."""
    context = _context(tmp_path)
    export = context.paths.output_dir / "karaoke_edit.mp3"
    export.parent.mkdir(parents=True, exist_ok=True)
    export.write_bytes(b"old")
    edited = context.paths.cache_dir / "karaoke_edited.wav"
    edited.write_bytes(b"old")
    context.store.set_step("karaoke", {"wav": str(edited)})

    pipeline.invalidate(context, ["clusters_original"])
    assert not export.exists()
    assert not edited.exists()
    assert context.store.get_step("karaoke") is None


def test_meta_is_really_cleared_too(tmp_path: Path) -> None:
    """``clear_step`` does not touch the top level of project.json;
    that is how the project-wide markings survived everything."""
    context = _context(tmp_path)
    context.store.set_meta("karaoke_from_original", True)
    context.store.set_meta("vocal_onset_s", 1.25)
    pipeline.invalidate(context, ["input:original"])
    assert context.store.get_meta("karaoke_from_original") is None
    assert context.store.get_meta("vocal_onset_s") is None


def test_project_name_survives_a_source_change(tmp_path: Path) -> None:
    """Not everything is a derivative: what the project is called and
    which titles go into the video stay, whatever you replace."""
    context = _context(tmp_path)
    context.store.set_meta("display_name", "Lied S")
    context.store.set_meta("video_titles", {"karaoke_title": "Viva"})
    pipeline.invalidate(context, ["input:original"])
    pipeline.invalidate(context, ["input:lyrics"])
    assert context.store.get_meta("display_name") == "Lied S"
    assert context.store.get_meta("video_titles") is not None


# --------------------------------------------------------------------------
# Demucs stems belong to one particular audio file
# --------------------------------------------------------------------------

def test_demucs_stems_of_other_audio_are_not_reused(
        tmp_path: Path) -> None:
    """Precisely the chain that v0.96 broke: Whisper transcribes the
    vocal stem, so a stem from another song silently gives a
    transcription of music that is no longer there."""
    from modules import separation

    cache = tmp_path / "cache"
    store = cache / "demucs_stems_original"
    store.mkdir(parents=True)
    (store / "vocals.wav").write_bytes(b"vocals")
    (store / "no_vocals.wav").write_bytes(b"music")

    source = tmp_path / "original.wav"
    source.write_bytes(b"song one")
    separation._write_marker(store / "source.sha1",
                             filesystem.file_sha1(source), "htdemucs")
    assert separation._marker_matches(store / "source.sha1",
                                      filesystem.file_sha1(source),
                                      "htdemucs")

    source.write_bytes(b"a completely different song")
    assert not separation._marker_matches(store / "source.sha1",
                                          filesystem.file_sha1(source),
                                          "htdemucs")


def test_demucs_stems_without_a_marker_stay_usable(tmp_path: Path) -> None:
    """Stems from before this version carry no marker. Throwing those
    away costs minutes per song for a separation that is probably
    right."""
    from modules import separation

    store = tmp_path / "demucs_stems_original"
    store.mkdir(parents=True)
    assert separation._marker_matches(store / "source.sha1", "abc123",
                                      "htdemucs")


def test_stems_of_another_model_are_not_reused(tmp_path: Path) -> None:
    """B548: the model was accepted, passed on and never written down.

    ``separate_cached(..., model="htdemucs_ft")`` handed back the
    stems of ``htdemucs`` and said nothing, because the marker only
    knew which audio they came from.
    """
    from modules import separation

    marker = tmp_path / "source.sha1"
    separation._write_marker(marker, "abc123", "htdemucs")
    assert separation._marker_matches(marker, "abc123", "htdemucs")
    assert not separation._marker_matches(marker, "abc123", "htdemucs_ft")


def test_stems_of_another_demucs_are_not_reused(tmp_path: Path,
                                                monkeypatch) -> None:
    """B548: `pip install -U demucs` is what install.bat invites.

    Without the version in the marker the old model's stems keep
    matching for ever and Whisper keeps transcribing them - the B311
    failure through another door.

    The version is monkeypatched because Demucs is not installed
    everywhere this suite runs, and without that this test passes with
    the version left out of the stamp altogether - it would be asking
    whether "" equals "".
    """
    from modules import separation

    marker = tmp_path / "source.sha1"
    monkeypatch.setattr(separation, "_demucs_version", lambda: "4.0.0")
    separation._write_marker(marker, "abc123", "htdemucs")
    assert "4.0.0" in marker.read_text(encoding="utf-8")
    assert separation._marker_matches(marker, "abc123", "htdemucs")

    monkeypatch.setattr(separation, "_demucs_version", lambda: "4.1.0")
    assert not separation._marker_matches(marker, "abc123", "htdemucs")


def test_a_marker_from_before_this_check_is_not_trusted(
        tmp_path: Path) -> None:
    """B548: one line says which audio, and nothing about the rest.

    Letting it pass on its checksum was the first thought, since those
    stems were probably made by the Demucs that is installed now. But
    a marker from before this check is precisely the one that may
    predate an upgrade, and passing it would stamp those stems as
    belonging to the new version - after which the mistake can never
    be found again. It costs one separation per project, once.

    Half a marker - a write torn after the first line - lands in the
    same branch, and that is the second reason for it.
    """
    from modules import separation

    marker = tmp_path / "source.sha1"
    marker.write_text("abc123", encoding="utf-8")
    assert not separation._marker_matches(marker, "abc123", "htdemucs")

    separation._write_marker(marker, "abc123", "htdemucs")
    assert marker.read_text(encoding="utf-8").count("\n") == 2
    assert separation._marker_matches(marker, "abc123", "htdemucs")


def test_stems_without_any_marker_are_still_accepted(tmp_path: Path) -> None:
    """The rule from B311 is untouched: no marker at all is from
    before that check and stays usable."""
    from modules import separation

    assert separation._marker_matches(tmp_path / "source.sha1", "abc123",
                                      "htdemucs")


# --------------------------------------------------------------------------
# The document keeps up with the chain
# --------------------------------------------------------------------------

def test_document_is_up_to_date() -> None:
    """``docs/dependencies.md`` is generated from the chain.

    A map kept up by hand goes stale the moment someone adds a step and
    forgets the document. This test compares the file on disk with what
    the generator makes; if it lags behind, run
    ``python tools/write_dependency_doc.py``.
    """
    import importlib.util

    tool = (Path(__file__).resolve().parents[1] / "tools"
            / "write_dependency_doc.py")
    spec = importlib.util.spec_from_file_location("_doc_tool", tool)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.DOC.exists(), "docs/dependencies.md is missing"
    on_disk = module.DOC.read_text(encoding="utf-8")
    assert on_disk == module.render(), (
        "docs/dependencies.md lags behind modules/dependencies.py; "
        "run: python tools/write_dependency_doc.py")


# --------------------------------------------------------------------------
# B312: a step does not throw away the file it just wrote itself
# --------------------------------------------------------------------------

def test_fresh_transcript_stays_on_disk(tmp_path: Path) -> None:
    """The regression that v0.98.0 brought along, in one test.

    After a genuinely new transcription ``detect_track`` cleared
    everything that rested on the PREVIOUS text. The chain counted the
    just-written ``transcription_original.json`` among that, because
    that file is derived from the step ``whisper_original``. Result: the
    file was removed the moment it had been written, and step 2 reported
    that there was no transcription.
    """
    context = _context(tmp_path)
    cache = pipeline.transcript_cache(context, "original")
    cache.write_bytes(b"[]")
    context.store.set_step("whisper_original", {"segments": 28})
    context.store.set_step("coupling", {"mapping": {}})
    context.store.set_step("timing", {"lines": 59})

    pipeline.invalidate_after_fresh_transcript(context, "original")

    assert cache.exists(), "the fresh transcript must not be cleared"
    assert context.store.get_step("whisper_original") is not None
    assert context.store.get_step("coupling") is None
    assert context.store.get_step("timing") is None


def test_fresh_karaoke_transcript_stays_too(tmp_path: Path) -> None:
    """The same for the transcription of the residual vocals."""
    context = _context(tmp_path)
    cache = pipeline.transcript_cache(context, "karaoke")
    cache.write_bytes(b"[]")
    context.store.set_step("whisper_karaoke", {"segments": 0})
    pipeline.invalidate_after_fresh_transcript(context, "karaoke")
    assert cache.exists()


def test_every_step_spares_its_own_product() -> None:
    """Generally, not only for the transcription: the file a step writes
    itself must never perish when THAT step has just been refreshed.
    Otherwise the same bug returns at the next step that writes a file
    (clusters.json, alignment.json, karaoke_edited.wav)."""
    for name, artefact in deps.ARTEFACTS.items():
        if artefact.kind != deps.STEP:
            continue
        products = deps.direct_products([name])
        if not products:
            continue
        _steps, _metas, files = deps.invalidation_plan([name])
        overlap = products & set(files)
        assert not overlap, (
            f"{name} would throw away the file(s) it just wrote "
            f"itself: {sorted(overlap)}")


def test_discarding_timing_does_take_the_files_along() -> None:
    """The opposite risk: throwing away too little. With
    ``invalidate_timing`` timing.json is meant to go, otherwise an
    outdated timing simply stays in use."""
    _steps, _metas, files = deps.invalidation_plan(
        ["timing"], include_changed=True)
    assert "output:timing" in files


def test_a_file_with_several_sources_is_no_own_product() -> None:
    """``lyrics_alignment.txt`` follows from the coupling AND the karaoke
    text; that is a real derivative and it should be dropped."""
    assert "output:lyrics_alignment" not in deps.direct_products(
        ["word_coupling"])
    _steps, _metas, files = deps.invalidation_plan(["word_coupling"])
    assert "output:lyrics_alignment" in files
