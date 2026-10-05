"""v1.0.22: the test set, blends, all the stems, and the stem models.

* the test panel runs on a test set of the owner's songs by default -
  good, medium, problem cases - kept in ``config/test_set.json``, with
  all projects a click away (B630);
* separations can be blended (B631): the Demucs blend now, and whatever
  mix of Demucs and Roformer later; 1.5.14 measures the Demucs blend and
  its parts keep their stems for it (B632);
* Demucs keeps all four stems (B632), and three models listen to them:
  the drums as the anchor (B633), the breaths of the lead voice (B634)
  and [bg] from the choir (B635), off until 1.5.19 has measured them;
* the helpers: ffmpeg in the program's bin folder, first; Python 3.12
  and its clean-up gone; the logs on the laptop under the name the
  helper list shows; the card under load in the check of 1.5.18 (B639).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile

from modules import separation, stem_blend, stem_models, test_set
from modules import work_queue as wq
from modules.stem_store import StemStore
from modules.timing import Syllable, TimedLine

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _wav(path: Path, data, rate: int = 44100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(str(path), np.asarray(data, dtype=np.float32), rate,
                    subtype="FLOAT")
    return path


def _noise(seconds: float = 2.0, rate: int = 44100, seed: int = 0):
    return np.random.default_rng(seed).standard_normal(
        (int(seconds * rate), 2)).astype(np.float32) * 0.3


def _line(index, start, end, bg=False, pieces=None):
    syllables = pieces or (Syllable("la", start, (start + end) / 2),
                           Syllable(" la", (start + end) / 2, end))
    return TimedLine(index=index, text="la la", crowd=False,
                     syllables=tuple(syllables), quality="high", bg=bg)


# -- B631: blends ---------------------------------------------------------------

@pytest.mark.parametrize("algorithm", stem_blend.ALGORITHMS)
def test_the_same_part_three_times_is_the_part(algorithm) -> None:
    part = _noise(1.0)
    joined = stem_blend.join([part, part, part], algorithm)
    assert np.max(np.abs(joined - part)) < 1e-5


def test_avg_wave_halves_and_weighs() -> None:
    a, b = np.ones((10, 2), np.float32), np.zeros((10, 2), np.float32)
    assert np.allclose(stem_blend.join([a, b]), 0.5)
    assert np.allclose(stem_blend.join([a, b], weights=(3, 1)), 0.75)
    with pytest.raises(stem_blend.BlendError):
        stem_blend.join([a, b], weights=(1,))
    with pytest.raises(stem_blend.BlendError):
        stem_blend.join([a, b], "nonsense")


def test_the_median_outvotes_one_part_gone_wrong() -> None:
    good = np.full((10, 1), 0.2, np.float32)
    wrong = np.full((10, 1), 9.0, np.float32)
    assert np.allclose(stem_blend.join([good, good, wrong], "median_wave"),
                       0.2)


def test_max_and_min_spec_keep_the_loudest_and_the_quietest() -> None:
    rate = 8000
    moment = np.arange(rate) / rate
    tone = np.sin(2 * np.pi * 440 * moment)[:, None].astype(np.float32)
    quiet = 0.1 * tone
    assert np.max(np.abs(stem_blend.join([tone, quiet], "max_spec")
                         [2048:-2048] - tone[2048:-2048])) < 1e-3
    assert np.max(np.abs(stem_blend.join([tone, quiet], "min_spec")
                         [2048:-2048] - quiet[2048:-2048])) < 1e-3


def test_parts_of_other_rates_and_lengths_are_joined(tmp_path) -> None:
    first = {name: _wav(tmp_path / f"a_{name}.wav", _noise(1.0))
             for name in ("vocals", "instrumental", "drums")}
    second = {name: _wav(tmp_path / f"b_{name}.wav",
                         _noise(0.5, 48000)[:, :1], 48000)
              for name in ("vocals", "instrumental")}
    made = stem_blend.blend_files([first, second], tmp_path / "out")
    assert sorted(made) == ["instrumental", "vocals"], \
        "only what every part has"
    info = soundfile.info(str(made["vocals"]))
    assert (info.samplerate, info.channels, info.frames) == (44100, 2, 44100)
    assert info.subtype == "FLOAT", "the level is kept (B597)"
    with pytest.raises(stem_blend.BlendError):
        stem_blend.blend_files([{"vocals": first["vocals"]}],
                               tmp_path / "x")


def test_a_blend_is_a_way_of_its_own() -> None:
    blend = separation.way_for("demucs_blend")
    assert "demucs_blend" in separation.METHODS
    assert blend.backend == "blend" and blend.parts == (
        separation.Way(), separation.Way("demucs", "htdemucs_ft", 2))
    assert blend.tag == "blend avg_wave (htdemucs | htdemucs_ft shifts=2)"
    assert blend.folder("original").startswith("stems_original_blend")
    assert separation.backends(blend) == {"demucs"}
    assert separation.backends(separation.BLENDS["high"]) == \
        {"demucs", "roformer"}
    weighed = separation.Way("blend", "", 1, "avg_wave", blend.parts, (2, 1))
    assert weighed.tag.startswith("blend avg_wave 2/1 (")
    for way in (blend, separation.BLENDS["high"], weighed,
                separation.Way("roformer", "a+b", algorithm="avg_wave")):
        assert separation.way_from(
            json.loads(json.dumps(separation.way_data(way)))) == way


def test_a_blend_is_there_when_all_its_parts_are(monkeypatch) -> None:
    monkeypatch.setattr(separation.models, "is_available", lambda n: True)
    monkeypatch.setattr(separation, "roformer_problem", lambda: "missing")
    assert separation.is_available(separation.BLENDS["demucs"])
    assert not separation.is_available(separation.BLENDS["high"])


def _fake_parts(monkeypatch, made):
    def one(audio, work, way):
        made.append(way.tag)
        level = 0.5 if way.shifts > 1 else 0.1
        return {name: _wav(work / f"{name}.wav",
                           np.full((100, 2), level, np.float32))
                for name in ("vocals", "instrumental", "drums")}

    monkeypatch.setattr(separation, "_separate_one", one)


def test_a_blend_separates_its_parts_and_keeps_them(tmp_path,
                                                    monkeypatch) -> None:
    made: list = []
    _fake_parts(monkeypatch, made)
    store = StemStore(tmp_path / "kept")
    blend = separation.way_for("demucs_blend")
    stems = separation.separate_way(tmp_path / "mix.wav", tmp_path / "w",
                                    blend, store)
    data, _rate = soundfile.read(str(stems["vocals"]))
    assert np.allclose(data, 0.3) and "drums" in stems
    assert made == ["htdemucs", "htdemucs_ft shifts=2"]
    assert store.has("htdemucs") and store.has("htdemucs_ft shifts=2")
    separation.separate_way(tmp_path / "mix.wav", tmp_path / "w2", blend,
                            store)
    assert made == ["htdemucs", "htdemucs_ft shifts=2"], \
        "the second time from the kept stems"


def test_the_stems_are_kept_small_and_come_back_at_their_level(
        tmp_path) -> None:
    loud = _noise(1.0) * 6.0          # peaks well above full scale
    stems = {"vocals": _wav(tmp_path / "v.wav", loud),
             "instrumental": _wav(tmp_path / "i.wav", loud * 0.1)}
    store = StemStore(tmp_path / "kept")
    assert store.get("x", tmp_path / "back") is None
    assert store.put("x", stems) and store.has("x")
    assert not list((tmp_path / "kept").glob("*.part*"))
    back = store.get("x", tmp_path / "back")
    data, _rate = soundfile.read(str(back["vocals"]), dtype="float32",
                                 always_2d=True)
    assert np.max(np.abs(data - loud)) < 1e-4 * np.max(np.abs(loud))
    assert (tmp_path / "kept" / "x" / "vocals.flac").stat().st_size < \
        (tmp_path / "v.wav").stat().st_size


def test_a_project_blend_reuses_the_stems_it_has(tmp_path,
                                                 monkeypatch) -> None:
    from modules import shared_work

    made: list = []
    _fake_parts(monkeypatch, made)
    monkeypatch.setattr(shared_work, "separate",
                        lambda audio, work, way: separation._separate_one(
                            audio, work, way))
    audio = _wav(tmp_path / "original.wav", np.zeros((100, 2)))
    cache = tmp_path / "cache"
    separation.separate_cached(audio, cache, "original")
    assert made == ["htdemucs"]
    before = (cache / "demucs_stems_original" / "vocals.wav").read_bytes()
    stems = separation.separate_cached(
        audio, cache, "original", way=separation.way_for("demucs_blend"))
    assert made == ["htdemucs", "htdemucs_ft shifts=2"], \
        "the standard stems of the project are reused"
    assert (cache / "demucs_stems_original" / "vocals.wav").read_bytes() \
        == before
    assert stems["vocals"].parent.name.startswith("stems_original_blend")
    assert (cache / "demucs_stems_original" / "drums.wav").exists()
    again = separation.separate_cached(
        audio, cache, "original", way=separation.way_for("demucs_blend"))
    assert made == ["htdemucs", "htdemucs_ft shifts=2"] and \
        again["vocals"] == stems["vocals"]


# -- B632: all four stems ----------------------------------------------------------

def test_demucs_makes_four_stems_and_the_music_is_the_other_three(
        tmp_path, monkeypatch) -> None:
    calls = []

    def fake(command):
        calls.append(command)
        folder = Path(command[command.index("-o") + 1]) / "htdemucs" / "x"
        for name, level in (("vocals", 0.4), ("drums", 0.1), ("bass", 0.2),
                            ("other", 0.3)):
            _wav(folder / f"{name}.wav", np.full((50, 2), level))

    monkeypatch.setattr(separation, "is_available", lambda way=None: True)
    monkeypatch.setattr(separation, "_run_separation", fake)
    stems = separation.separate(tmp_path / "x.wav", tmp_path / "work")
    assert "--two-stems" not in calls[0]
    assert sorted(stems) == ["bass", "drums", "instrumental", "other",
                             "vocals"]
    music, _rate = soundfile.read(str(stems["instrumental"]))
    assert np.allclose(music, 0.6)


def test_an_older_project_gets_its_drums_beside_its_stems(
        tmp_path, monkeypatch) -> None:
    store = tmp_path / "cache" / "demucs_stems_original"
    _wav(store / "vocals.wav", np.full((10, 2), 0.9))
    _wav(store / "no_vocals.wav", np.full((10, 2), 0.8))
    before = (store / "vocals.wav").read_bytes()

    def fake(audio, work, model="htdemucs", shifts=1):
        return {name: _wav(work / f"{name}.wav", np.zeros((10, 2)))
                for name in ("vocals", "instrumental", "drums", "bass",
                             "other")}

    monkeypatch.setattr(separation, "is_available", lambda way=None: True)
    monkeypatch.setattr(separation, "separate", fake)
    found = separation.extra_stem(tmp_path / "o.wav", tmp_path / "cache",
                                  "original", "drums")
    assert found == store / "drums.wav" and (store / "bass.wav").exists()
    assert (store / "vocals.wav").read_bytes() == before, \
        "the stems it has are left exactly as they are"
    assert not (tmp_path / "cache" / "demucs_extra_original").exists()


def test_a_helper_sends_every_stem_back() -> None:
    from modules import shared_work
    import inspect

    source = inspect.getsource(shared_work.run_round)
    assert "for name, path in stems.items()" in source
    assert shared_work.needs_of(separation.way_for("demucs_blend")) == \
        ["demucs"]


# -- 1.5.14 measures the blend -------------------------------------------------------

def test_1_5_14_measures_the_demucs_blend_after_its_parts() -> None:
    from modules import separation_trial as st

    blend = next(way for way in st.WAYS if way.key == "demucs_blend")
    assert st.keeps_stems(blend)
    assert {"htdemucs", "htdemucs_ft shifts=2"} <= st.kept_parts()
    assert st.keeps_stems(st.WAYS[0]) and st.keeps_stems(st.WAYS[1])
    assert not st.keeps_stems(next(w for w in st.WAYS
                                   if w.key == "roformer_dry"))
    assert st.needs_of(blend) == ["ffmpeg", "demucs"]
    from modules import musdb_trial
    assert blend in musdb_trial.ways(), "1.5.17 holds it against the truth"
    import inspect
    assert 'job["priority"] = -1' in inspect.getsource(st._share_out)


def test_the_kept_stems_are_reached_through_the_share(tmp_path) -> None:
    from modules import separation_trial as st

    queue = wq.Queue(tmp_path / "Tools" / wq.QUEUE_NAME)
    root = tmp_path / "Tools" / "_to_delete" / st.SCRATCH_NAME
    mix = _wav(tmp_path / "mix.wav", np.zeros((10, 2)))
    folder = st.stems_folder(root, queue, "Lied R", mix)
    assert folder.startswith("../_to_delete/kt_separation/stems/")
    assert (queue.root / folder).resolve().parent == \
        (root / "stems").resolve()
    assert st.stems_folder(tmp_path / "elsewhere" / "x",
                           wq.Queue(tmp_path / "q" / "kt_work"), "a", mix) \
        == ""
    other = _wav(tmp_path / "other.wav", np.ones((10, 2)))
    assert st.stems_folder(root, queue, "Lied R", other) != folder, \
        "another original gets stems of its own"


# -- B630: the test set ------------------------------------------------------------

def test_spread_takes_the_ends_and_the_middle() -> None:
    assert test_set.spread(list("abcdefg"), 3) == ["a", "d", "g"]
    assert test_set.spread(list("ab"), 3) == ["a", "b"]
    assert test_set.spread(list("abc"), 1) == ["b"]
    assert test_set.spread([], 2) == []


def test_a_proposal_takes_good_medium_and_the_worst() -> None:
    errors = {f"s{n:02d}": n / 10.0 for n in range(12)}
    groups = test_set.propose(errors)
    assert groups["good"] == ["s00", "s02", "s03"]
    assert groups["medium"] == ["s04", "s06", "s07"]
    assert groups["problem"] == ["s09", "s10", "s11"], "the worst ones"


def _installation(tmp_path, names=("A", "B", "C", "D")):
    from dataclasses import replace

    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    root = tmp_path / "Tools" / "KaraokeTool"
    for name in names:
        paths = ProjectPaths(root=root, song=name)
        ensure_directories(paths)
        ProjectStore(paths.project_file).set_meta("x", 1)
    paths = ProjectPaths(root=root, song=names[0])
    config = default_config()
    config = replace(config, song=replace(config.song, title=names[0]))
    return pipeline.AppContext(paths=paths, config=config,
                               store=ProjectStore(paths.project_file))


def test_the_panel_runs_on_the_set(tmp_path) -> None:
    from modules import test_panel

    context = _installation(tmp_path)
    # v1.0.28 (B663): a set the owner saved is pinned.
    test_set.save(context, {"good": ["C"], "medium": ["Gone"],
                            "problem": ["A"]}, basis="owner")
    try:
        test_panel.limit_to("set")
        assert test_panel._projects(context) == ["C", "A"], \
            "in group order; a song that is gone is left out"
        test_panel.limit_to("all")
        assert test_panel._projects(context) == ["A", "B", "C", "D"]
        test_panel.limit_to("current")
        assert test_panel._projects(context) == ["A"]
        test_panel.limit_to("nonsense")
        assert test_panel._SCOPE == "all"
    finally:
        test_panel.limit_to("all")
    assert "C" in test_set.describe(context)


def test_without_a_set_one_is_proposed_from_the_last_night(
        tmp_path) -> None:
    from modules import front_to_back, test_panel

    context = _installation(tmp_path, names=tuple("ABCDEF"))
    scratch = front_to_back.scratch_root(context)
    scratch.mkdir(parents=True)
    runs = {}
    for n, song in enumerate("ABCDEF"):
        for models, error in ((["B1"], 5.0), (["B1", "B2"], n * 0.1)):
            key = f"{song}|x|" + json.dumps({"models": models})
            runs[key] = {"starts": [1.0 + error], "hand": [1.0]}
    (scratch / "results.json").write_text(json.dumps({"runs": runs}))
    assert test_set.errors_from_the_start(context)["C"] == \
        pytest.approx(0.2), "the variant with the most models on"
    try:
        test_panel.limit_to("set")
        assert test_panel._projects(context) == ["A", "B", "C", "D", "E",
                                                 "F"]
    finally:
        test_panel.limit_to("all")
    # v1.0.28 (B663): built, not written.
    assert test_set.load(context) is None
    assert test_set.current(context)["problem"] == ["E", "F"]


def test_without_any_measurement_the_set_is_everything(tmp_path) -> None:
    from modules import test_panel

    context = _installation(tmp_path)
    try:
        test_panel.limit_to("set")
        assert test_panel._projects(context) == ["A", "B", "C", "D"]
    finally:
        test_panel.limit_to("all")
    assert test_set.load(context) is None


def test_the_panel_opens_on_the_set_and_can_choose_it(qapp,
                                                     tmp_path) -> None:
    from modules.test_panel import TestPanel, TestSetDialog

    context = _installation(tmp_path)
    panel = TestPanel(context=context)
    # v1.0.28 (B663): nothing measured yet - no set to offer.
    assert panel.scope() == "all" and panel._set_scope.isHidden()
    panel._current.setChecked(True)
    assert panel.scope() == "current"
    dialog = TestSetDialog(context)
    assert dialog.groups() == {"good": [], "medium": [], "problem": []}


# -- B633-B635: the stem models ------------------------------------------------------

def test_the_drums_pull_a_start_onto_the_grid() -> None:
    lines = [_line(0, 1.03, 2.05), _line(1, 2.1, 3.0), _line(2, 5.5, 6.0)]
    moved = stem_models.on_the_drums(lines, [1.0, 2.0, 2.25, 5.0], 0.12)
    assert moved[0].start == pytest.approx(1.0)
    assert moved[1].start == pytest.approx(2.1), \
        "not before the line in front of it ends (2.0), 2.25 too far"
    assert moved[2].start == pytest.approx(5.5), "too far: left alone"
    assert moved[0].end == pytest.approx(2.05), "the end stays"
    assert stem_models.on_the_drums(lines, [], 0.12) == tuple(lines)


def test_a_start_moves_to_the_end_of_the_breath() -> None:
    lines = [_line(0, 1.0, 3.2), _line(1, 3.1, 5.0), _line(2, 5.0, 7.0)]
    moved = stem_models.at_the_breaths(lines, [(2.9, 3.3), (4.8, 4.98)])
    assert moved[1].start == pytest.approx(3.3)
    assert moved[0].end == pytest.approx(2.9), "ends where the breath begins"
    assert moved[2].start == pytest.approx(5.0), \
        "already at the end of a pause: that is where it belongs"


def test_bg_goes_where_the_choir_sings() -> None:
    bg_line = _line(0, 10.0, 11.0, bg=True)
    inline = _line(1, 20.0, 22.0, pieces=(
        Syllable("ja", 20.0, 21.0), Syllable(" oh", 21.5, 21.8, bg=True),
        Syllable(" ja", 21.0, 22.0)))
    plain = _line(2, 30.0, 31.0)
    moved = stem_models.from_the_choir(
        [bg_line, inline, plain], [10.5, 21.9, 30.2], [(10.45, 12.0)])
    assert (moved[0].start, moved[0].end) == pytest.approx((10.5, 12.0))
    assert moved[1].syllables[1].start == pytest.approx(21.9)
    assert moved[1].syllables[1].end == pytest.approx(22.2), \
        "a piece keeps its length"
    assert moved[1].start == inline.start, "the sung part stays"
    assert moved[2] == plain, "only [bg] is touched"


def test_the_stem_models_are_off_until_measured(tmp_path,
                                                monkeypatch) -> None:
    from modules import model_register, pipeline

    for code in ("B633", "B634", "B635"):
        model = model_register.by_code(code)
        assert model is not None and not model.default_on
        assert model.display_name != f"model_name_{model.key}"
    context = _installation(tmp_path)
    grid = context.paths.cache_dir / pipeline.MODEL_STEMS / "drums.mp3"
    grid.parent.mkdir(parents=True, exist_ok=True)
    grid.write_bytes(b"x")
    monkeypatch.setattr(stem_models, "drum_grid", lambda path: [1.0])
    lines = (_line(0, 1.05, 2.0),)
    model_register.apply_settings({})
    model_register.apply_disabled()
    try:
        assert pipeline._stem_models(context, lines) == lines
        model_register.apply_settings({"B633": True})
        model_register.apply_disabled()
        assert pipeline._stem_models(context, lines)[0].start == \
            pytest.approx(1.0)
    finally:
        model_register.apply_settings({})
        model_register.apply_disabled()


def test_a_stem_is_found_where_the_ways_keep_it(tmp_path) -> None:
    from modules import pipeline

    context = _installation(tmp_path)
    cache = context.paths.cache_dir
    assert pipeline.model_stem(context, "drums") is None
    _wav(cache / "demucs_stems_original" / "drums.wav", np.zeros((10, 2)))
    assert pipeline.model_stem(context, "drums").name == "drums.wav"
    lead = cache / pipeline._karaoke_way().folder("original") / "vocals.wav"
    _wav(lead, np.zeros((10, 2)))
    assert pipeline.model_stem(context, "lead") == lead
    _wav(cache / "demucs_stems_karaoke_music" / "vocals.wav",
         np.zeros((10, 2)))
    assert pipeline.model_stem(context, "choir").parent.name == \
        "demucs_stems_karaoke_music"


def test_a_report_makes_no_stems_and_an_off_model_costs_nothing(
        tmp_path, monkeypatch) -> None:
    from modules import model_register, pipeline

    context = _installation(tmp_path)
    asked = []
    monkeypatch.setattr(separation, "extra_stem",
                        lambda *a, **k: asked.append(a))
    model_register.apply_settings({})
    pipeline.prepare_model_stems(context)
    assert asked == [], "all three off: nothing is made"


def test_the_yardstick_row_knows_the_bg_lines() -> None:
    from modules import stem_trial

    found = stem_trial.bg_figures([{
        "hand_starts": [1.0, 2.0], "new_starts": [1.5, 2.0],
        "bg_rows": [0], "piece_hand": [3.0], "piece_new": [3.25]}])
    assert found == {"bg_lines": 1, "bg_error": 0.5, "pieces": 1,
                     "piece_error": 0.25}
    source = _read(ROOT / "tools" / "timing_regression.py")
    assert '"bg_rows": bg_rows' in source and "MODEL_STEMS" in source


def test_1_5_19_measures_each_model_and_all_three() -> None:
    from modules import model_orders, queue_jobs, stem_trial, test_panel

    labels = [variant.label for variant in stem_trial.VARIANTS]
    assert labels[0] == "baseline" and "B633+B634+B635" in labels
    for variant in stem_trial.VARIANTS:
        states = stem_trial.states_for(variant)
        assert {code for code in stem_trial.CODES if states[code]} == \
            set(variant.on)
        if variant.setting:
            assert model_orders.targets(variant.setting)
    action = next(a for a in test_panel.ACTIONS if a.code == "1.5.19")
    assert action.on_request and action.done      # v1.0.27
    assert queue_jobs.handlers()[stem_trial.PREP_KIND] is \
        stem_trial.prep_round


def test_a_prep_round_makes_the_mp3s_in_the_copy(tmp_path,
                                                 monkeypatch) -> None:
    from modules import ffmpeg, stem_trial

    made: list = []

    def separate(audio, work, way, store=None):
        made.append(way.tag)
        return {name: _wav(work / f"{name}.wav", np.zeros((10, 2)))
                for name in ("vocals", "instrumental", "drums")}

    monkeypatch.setattr(separation, "separate_way", separate)
    monkeypatch.setattr(separation, "is_available", lambda way=None: True)
    monkeypatch.setattr(ffmpeg, "encode_mp3", lambda s, t, *a, **k:
                        t.write_bytes(b"mp3"))
    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    job = {"id": "x", "payload": {"mix": "files/m.wav",
                                  "target": "files/proj/p/cache/S/model_stems",
                                  "karaoke": True, "stems": ""}}
    answer = stem_trial.prep_round(job, queue, lambda: False)
    assert answer == {"made": ["drums", "lead", "choir"]}
    target = queue.root / job["payload"]["target"]
    assert sorted(p.name for p in target.iterdir()) == \
        ["choir.mp3", "drums.mp3", "lead.mp3"]
    assert made[0] == "htdemucs" and made[-1] == "htdemucs", \
        "the choir is Demucs on the karaoke model's music"


# -- the helpers --------------------------------------------------------------------

def test_ffmpeg_of_winget_comes_first(tmp_path, monkeypatch) -> None:
    """v1.0.23: winget keeps it up to date; bin is the fallback."""
    from modules import ffmpeg

    monkeypatch.setattr(ffmpeg, "_BIN_DIR", tmp_path)
    (tmp_path / "ffmpeg.exe").write_bytes(b"x")
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: "/usr/x")
    assert ffmpeg.find_executable("ffmpeg") == "/usr/x"
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: None)
    assert ffmpeg.find_executable("ffmpeg") == str(tmp_path / "ffmpeg.exe")


def test_the_batch_files_take_ffmpeg_from_winget_and_update_it() -> None:
    install = _read(ROOT / "helper" / "install_helper.bat")
    assert install.index("where ffmpeg") < \
        install.index('if exist "%APP%\\bin\\ffmpeg.exe"')
    assert "winget install -e --id Gyan.FFmpeg --scope user" in install
    assert "winget upgrade -e --id Gyan.FFmpeg --silent" in install
    launcher = _read(ROOT / "KaraokeToolGUI.bat")
    assert launcher.index("where ffmpeg") < \
        launcher.index('if exist "bin\\ffmpeg.exe"')
    assert "winget install -e --id Gyan.FFmpeg --scope user" in launcher
    assert "winget upgrade -e --id Gyan.FFmpeg --silent" in launcher
    assert "robocopy \"%SHARE%\" \"%APP%\" /MIR" in install
    mirror = install[install.index('robocopy "%SHARE%" "%APP%" /MIR'):]
    assert " bin " not in mirror.split("\n")[0], "bin goes along"


def test_the_logs_go_under_the_name_of_the_helper_list() -> None:
    for name in ("install_helper.bat", "helper_start.bat"):
        text = _read(ROOT / "helper" / name)
        assert "for /f \"delims=\" %%H in ('hostname 2^>nul')" in text
        assert "\\logs\\helpers\\%HOST%" in text
        assert "\\helpers\\%COMPUTERNAME%" not in text


def test_the_check_puts_the_card_under_load(tmp_path, monkeypatch) -> None:
    """v1.0.23 (B645): a profile of the card, task by task."""
    from modules import diagnose
    from modules.separation_trial import KARAOKE_TRIO
    from modules.translations import t

    assert diagnose._card_seen('warning\n{"cuda_available": true}')
    assert not diagnose._card_seen('{"cuda_available": false}')
    assert not diagnose._card_seen("nonsense")
    assert "memory.used" in diagnose.LOAD_QUERY and \
        "clocks_event_reasons.active" in diagnose.LOAD_QUERY and \
        "clocks_throttle_reasons.active" in diagnose.LOAD_QUERY_OLD
    names = [n for n, _c in diagnose.card_tasks("py", tmp_path, tmp_path /
                                                "s.wav", tmp_path)]
    assert names == ["whisper", "whisper_int8", "demucs"], \
        "no Roformer models: not tried"
    for model in [separation.ROFORMER_MODELS["vocals"],
                  *KARAOKE_TRIO.split("+")]:
        (tmp_path / model).write_bytes(b"x")
    tasks = dict(diagnose.card_tasks("py", tmp_path, tmp_path / "s.wav",
                                     tmp_path))
    assert list(tasks) == ["whisper", "whisper_int8", "roformer",
                           "roformer_small", "demucs", "trio"]
    assert tasks["roformer_small"][-2:] == ["--segment",
                                            str(diagnose.SMALL_SEGMENT)]
    assert "--segment" in tasks["demucs"]
    calls = []
    heat = {"now": 66.0}

    def run(command, env=None, timeout=600):
        calls.append(command[0])
        if command[0] == "nvidia-smi":
            return 0, f"{heat['now']}, 1500, 1800, 40.0, 3900, 4096, 99, " \
                      "0x0000000000000020", 0.1
        import time
        time.sleep(0.15)
        if "--algorithm" in command:
            return 1, "torch.OutOfMemoryError: CUDA out of memory", 3.0
        return 0, "done", 12.0

    monkeypatch.setattr(diagnose, "_run", run)
    monkeypatch.setattr(diagnose, "LOAD_EVERY_S", 0.05)
    monkeypatch.setattr(diagnose, "REST_S", 0.1)
    lines = diagnose.card_profile(Path("python"), tmp_path, lambda: False)
    text = "\n".join(lines)
    assert t("check_task_trio") in text and "CUDA out of memory" in text
    assert "3900/4096" in text and "0x0000000000000020" in text
    assert text.count(t("check_ok")) == 5, "v1.0.24: the smaller Whisper too"
    assert "nvidia-smi" in calls


def test_the_roformer_tool_can_take_smaller_pieces() -> None:
    source = _read(ROOT / "tools" / "roformer_separate.py")
    assert '"--segment"' in source and '"override_model_segment_size": True' \
        in source


def test_the_separator_says_how_much_of_the_card_it_took() -> None:
    source = _read(ROOT / "tools" / "roformer_separate.py")
    assert "max_memory_reserved" in source and "card_peak_gb=" in source


def test_every_new_text_is_in_both_languages() -> None:
    from modules.translations import TRANSLATIONS

    for key in ("test_scope_set", "report_scope_set", "test_set_choose",
                "sep_demucs_blend", "model_name_b633", "model_reason_b635",
                "test_stem_models", "stem_trial_cols", "check_load",
                "log_blend_done", "log_stem_model_applied"):
        assert key in TRANSLATIONS["nl"] and key in TRANSLATIONS["en"], key


# -- what the review before delivery found --------------------------------------------

def test_a_moved_start_never_stretches_a_line_into_the_next() -> None:
    lines = [_line(0, 8.0, 9.9), _line(1, 10.0, 10.4), _line(2, 10.45, 12.0)]
    moved = stem_models.on_the_drums(lines, [10.12], 0.12)
    assert moved[1].end <= lines[2].start
    lines = [_line(0, 8.0, 9.5), _line(1, 10.0, 10.6), _line(2, 10.65, 12.0)]
    moved = stem_models.at_the_breaths(lines, [(9.8, 10.35)])
    assert moved[1].end <= moved[2].start


def test_two_long_tags_never_share_a_folder() -> None:
    from modules.separation_trial import KARAOKE_TRIO
    from modules.stem_store import _safe

    one = separation.Way("roformer", KARAOKE_TRIO, algorithm="avg_wave")
    two = separation.Way("roformer", KARAOKE_TRIO, algorithm="max_spec")
    assert _safe(one.tag) != _safe(two.tag) and len(_safe(one.tag)) < 80
    high = separation.BLENDS["high"]
    other = separation.Way("blend", "", 1, "median_wave", high.parts)
    assert high.folder("original") != other.folder("original")
    assert len(high.folder("original")) < 90
    assert separation.way_for("careful").folder("original") == \
        "stems_original_htdemucs_ft_shifts_2", "an existing folder stays"


def test_a_blend_whose_part_could_not_be_kept_still_blends(
        tmp_path, monkeypatch) -> None:
    from modules import shared_work
    import shutil

    made: list = []
    _fake_parts(monkeypatch, made)
    monkeypatch.setattr(shared_work, "separate",
                        lambda audio, work, way: separation._separate_one(
                            audio, work, way))
    real_copy = shutil.copyfile

    def copyfile(source, target, *a, **k):
        if "htdemucs_ft" not in str(target) and "stems_original_blend" \
                not in str(target):
            raise OSError("disk full")
        return real_copy(source, target, *a, **k)

    monkeypatch.setattr(shutil, "copyfile", copyfile)
    audio = _wav(tmp_path / "original.wav", np.zeros((100, 2)))
    stems = separation.separate_cached(
        audio, tmp_path / "cache", "original",
        way=separation.way_for("demucs_blend"))
    data, _rate = soundfile.read(str(stems["vocals"]))
    assert np.allclose(data, 0.3), "both parts were there to blend"
    assert not list((tmp_path / "cache").glob("demucs_part*"))


def test_a_job_is_for_every_project_even_with_the_set() -> None:
    import inspect

    from modules import gui, test_panel

    jobs = {a.code for a in test_panel.ACTIONS if not a.on_the_set}
    assert jobs == {"1.5.1", "1.5.12"}
    source = inspect.getsource(gui.MainWindow._start_tests)
    assert "not action.on_the_set" in source


def test_a_song_in_two_groups_is_measured_once(tmp_path) -> None:
    context = _installation(tmp_path)
    test_set.save(context, {"good": ["A", "B"], "medium": ["B"],
                            "problem": []}, basis="owner")
    assert test_set.songs(context, ["A", "B"]) == ["A", "B"]


def test_the_choir_goes_with_the_original() -> None:
    from modules import dependencies

    source = _read(ROOT / "modules" / "dependencies.py")
    assert '"cache:model_stems", FILE, ["cache:demucs_original"]' in source
    assert "demucs_stems_karaoke_music" in source
    assert dependencies is not None
