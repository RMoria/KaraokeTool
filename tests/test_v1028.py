"""v1.0.28: the owner's choices after the tests, and the rest of the
build in one go.

* High and Normal separate with the two Roformer models for clean music,
  falling back to the Demucs blend, then the standard way; Quick stays
  plain. 1.5.14 measures one new way: the Demucs blend with clean music;
* 1.5.15 and 1.5.20 are done;
* numba keeps its compiled code in a folder of the program's own;
* the count and the end time move while this computer works on a round
  of its own (B662), and an end time partly guessed says "about" (B661).
"""
from __future__ import annotations

import threading
from pathlib import Path

from modules import profiles, separation, separation_trial, test_panel
from modules import work_queue as wq

ROOT = Path(__file__).resolve().parents[1]


# -- the separation of the stands ---------------------------------------------------

def test_high_and_normal_make_clean_music_quick_stays_plain() -> None:
    assert profiles.PROFILES["high"]["separation"] == "music_clean"
    assert profiles.PROFILES["normal"]["separation"] == "music_clean"
    assert profiles.PROFILES["quick"]["separation"] == "standard"
    way = separation.way_for("music_clean")
    assert way.backend == "blend" and way.algorithm == "max_spec"
    assert "+".join(part.model for part in way.parts) == \
        separation.MUSIC_CLEAN
    assert separation_trial.MUSIC_CLEAN == separation.MUSIC_CLEAN


def test_the_way_falls_back_where_roformer_is_missing(monkeypatch) -> None:
    from modules import pipeline

    class Store:
        def __init__(self):
            self.meta = {}

        def get_meta(self, key):
            return self.meta.get(key)

        def set_meta(self, key, value):
            self.meta[key] = value

    context = type("C", (), {})()
    context.store = Store()
    monkeypatch.setattr(pipeline, "_worked_on", lambda c: False)
    monkeypatch.setattr(pipeline, "project_settings",
                        lambda c: {"separation": "music_clean"})
    monkeypatch.setattr(pipeline, "_way_available",
                        lambda way: "roformer" not in
                        separation.backends(way))
    assert pipeline.separation_method(context) == "demucs_blend"
    assert context.store.meta["separation"] == "demucs_blend", \
        "the project keeps the way its stems are made with"
    context.store = Store()
    monkeypatch.setattr(pipeline, "_way_available", lambda way: False)
    assert pipeline.separation_method(context) == "standard"
    assert "separation" not in context.store.meta


def test_1_5_14_measures_the_blend_with_clean_music() -> None:
    keys = [way.key for way in separation_trial.WAYS]
    assert keys[-2] == "demucs_music_clean"
    blend = separation_trial.WAYS[-2].way
    assert separation.way_for("music_clean") in blend.parts
    assert separation_trial.keeps_stems(separation_trial.WAYS[-2])
    action = [a for a in test_panel.ACTIONS if a.code == "1.5.14"][0]
    assert not action.done
    for code in ("1.5.15", "1.5.20"):
        assert [a for a in test_panel.ACTIONS if a.code == code][0].done


def test_numba_keeps_its_code_in_a_folder_of_its_own() -> None:
    text = (ROOT / "KaraokeTool.py").read_text(encoding="utf-8")
    assert text.index("NUMBA_CACHE_DIR") < text.index(
        "from modules.pipeline import"), "before librosa is imported"


# -- B662: the bar moves during a round of this computer -----------------------------

def test_answers_come_in_while_this_computer_works(tmp_path) -> None:
    queue = wq.Queue(tmp_path / "kt_work").ensure()
    jobs = [{"id": wq.job_id(k), "kind": "k", "class": "c", "needs": [],
             "label": k, "payload": {"key": k}} for k in ("a", "b")]
    seen_b = threading.Event()

    def handler(job, q, stop):
        # A helper takes the other round and answers it while this one
        # still runs; this round ends only once that answer was heard.
        other, _ = q.claim("Pav-mixed", "1.0")
        if other is not None:
            q.finish(other, {"ok": 1, "seconds": 2.0}, "Pav-mixed", "cpu")
        return {"heard": seen_b.wait(10.0)}

    answers = []

    def on_answer(answer):
        answers.append(answer)
        if answer["worker"] == "Pav-mixed":
            seen_b.set()

    wq.run_jobs(queue, jobs, "1.0", {"k": handler}, on_answer,
                lambda: False, poll_s=0.05, sleep=lambda s: None)
    mine = [a for a in answers if a["worker"] != "Pav-mixed"]
    assert mine and mine[0]["result"]["heard"] is True


def test_a_bar_is_told_at_every_look(monkeypatch) -> None:
    calls = []

    class Bar:
        def refresh(self):
            calls.append(1)

    bar = Bar()
    wq.watch(bar.refresh)
    wq._tell_watchers()
    assert calls == [1]
    del bar
    wq._tell_watchers()
    assert calls == [1], "a bar that is gone is forgotten"


def test_steps_refresh_between_rounds_and_say_about(monkeypatch) -> None:
    sent = []
    steps = test_panel.Steps(lambda *a: sent.append(a), "x", 3,
                             forecast=lambda: {"seconds": 600.0,
                                               "lanes": 1, "rough": True})
    from modules.translations import t
    assert t("steps_eta_rough").split("{")[0].strip() in sent[-1][1]
    count = len(sent)
    steps.refresh()
    assert len(sent) == count, "not more than every few seconds"
    steps._sent -= test_panel.Steps.REFRESH_S + 1
    steps.refresh()
    assert len(sent) == count + 1


# -- B661: a guess where nothing is known yet ---------------------------------------

def test_a_round_nobody_timed_yet_is_guessed(tmp_path) -> None:
    queue = wq.Queue(tmp_path / "kt_work").ensure()
    queue.publish({"id": wq.job_id("n"), "kind": "k", "class": "new",
                   "version": "1.0", "needs": [], "label": "n",
                   "payload": {}})
    queue.note_speed("Pav-mixed", "old", 120)
    queue.status("Pav-mixed", "waiting", "cpu", can=["ffmpeg"])
    found = wq.forecast(queue, "1.0")
    assert found["seconds"] == 120.0 and found["rough"] is True


# -- B657/B658: what helpers start ------------------------------------------------

def test_a_hidden_console_rather_than_pythonw(monkeypatch, tmp_path) -> None:
    from modules import proc

    (tmp_path / "python.exe").write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    monkeypatch.setattr(proc.sys, "platform", "win32")
    monkeypatch.setattr(proc.sys, "executable", str(tmp_path / "pythonw.exe"))
    assert proc.hidden_console_python() == str(tmp_path / "python.exe")
    assert separation._windowless(tmp_path / "pythonw.exe") == \
        str(tmp_path / "python.exe")
    text = (ROOT / "modules" / "separation.py").read_text(encoding="utf-8")
    assert "proc.windowless_python()" not in text


def test_children_speak_utf8_without_bars(monkeypatch) -> None:
    from modules import proc

    monkeypatch.delenv("TQDM_DISABLE", raising=False)
    env = proc.child_env()
    assert env["PYTHONIOENCODING"] == "utf-8" and env["TQDM_DISABLE"] == "1"
    import sys

    done = proc.run([sys.executable, "-c",
                     "import sys; sys.stdout.buffer.write(b'caf\\xc3\\xa9 "
                     "\\x9d|')"])
    assert done.stdout.startswith("café"), "UTF-8, and a bad byte replaced"


def test_the_probe_goes_through_the_door() -> None:
    text = (ROOT / "tools" / "helper.py").read_text(encoding="utf-8")
    start = text.index("def _probe_elsewhere")
    body = text[start:text.index("\ndef ", start + 10)]
    assert "proc.run(" in body and "subprocess.run" not in body


# -- B659/B660: the helper's language, English batch files --------------------------

def test_the_helper_follows_the_programs_language(tmp_path) -> None:
    import importlib.util
    import json

    from modules import translations

    spec = importlib.util.spec_from_file_location(
        "helper_v1028", ROOT / "tools" / "helper.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    before = translations.current_language()
    try:
        queue = wq.Queue(tmp_path / "kt_work").ensure()
        translations.set_language("en")
        queue.write_where()
        assert json.loads((queue.root / "laptop.json").read_text(
            encoding="utf-8"))["language"] == "en"
        translations.set_language("nl")
        home = tmp_path / "home"
        home.mkdir()
        assert helper.follow_language(queue.root, home) == "en"
        translations.set_language("nl")
        assert helper.follow_language(None, home) == "en", "remembered"
        text = (ROOT / "tools" / "helper.py").read_text(encoding="utf-8")
        for literal in ('"helper stopped by an error"',
                        '"helper start failed"', '"could not remove %s"'):
            assert literal not in text
    finally:
        translations.set_language(before)


def test_batch_files_speak_english() -> None:
    for name in ("KaraokeToolGUI.bat", "helper/install_helper.bat",
                 "helper/helper_start.bat", "tools/find_python.bat"):
        data = (ROOT / name).read_bytes()
        assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
        text = data.decode("cp1252")
        assert "choice /C JN" not in text, name
        for word in ("Let op", "niet gevonden", "INSTALLATIE MISLUKT",
                     "opnieuw"):
            assert word not in text, (name, word)


# -- B665/B666: signs, stop after the current rounds, a central stop ---------------

def test_a_sign_every_five_minutes_and_half_an_hour_of_silence() -> None:
    assert wq.HEARTBEAT_S == 300.0 and wq.STALE_S == 1800.0
    assert wq.STATUS_S < wq.WORKER_FRESH_S, \
        "the status is written often enough to count as alive"


def test_stop_after_the_current_round(tmp_path) -> None:
    queue = wq.Queue(tmp_path / "kt_work").ensure()
    jobs = [{"id": wq.job_id(k), "kind": "k", "class": "c", "needs": [],
             "label": k, "payload": {}} for k in ("a", "b", "c")]
    done = []
    try:
        wq.run_jobs(queue, jobs, "1.0",
                    {"k": lambda job, q, s: done.append(job["id"]) or {}},
                    lambda answer: wq.request_finish(), lambda: False,
                    poll_s=0.05, sleep=lambda s: None)
        assert len(done) == 1, "after the first answer no new round"
        assert not list(queue.jobs.glob("*.json")), "the rest taken back"
        counts = wq.run_jobs(queue, jobs, "1.0", {"k": lambda *a: {}},
                             lambda a: None, lambda: False)
        assert counts["answered"] == 0 and not list(queue.jobs.glob("*"))
    finally:
        wq.clear_finish()


def test_the_helpers_stop_when_everything_is_in(tmp_path) -> None:
    queue = wq.Queue(tmp_path / "kt_work").ensure()
    said = []
    outcome = wq.work(queue, "Pav-mixed", "cpu", "1.0", {}, lambda: False,
                      lambda key, values: said.append(key), once=True,
                      sleep=lambda s: None)
    assert outcome == "stopped" and "helper_central_stop" not in said
    queue.ask_helpers_to_stop()
    said.clear()
    wq.work(queue, "Pav-mixed", "cpu", "1.0", {}, lambda: False,
            lambda key, values: said.append(key), once=True,
            sleep=lambda s: None)
    # The stop was written before this worker started: not for it.
    assert "helper_central_stop" not in said
    import os
    import time as _time

    flag = queue.root / wq.STOP_HELPERS
    later = _time.time() + 60
    os.utime(flag, (later, later))
    wq.work(queue, "Pav-mixed", "cpu", "1.0", {}, lambda: False,
            lambda key, values: said.append(key), once=True,
            sleep=lambda s: None)
    assert "helper_central_stop" in said
    queue.clear_stop_helpers()
    assert not flag.exists()


def test_an_answer_waits_on_the_helper_until_the_share_is_back(
        tmp_path, monkeypatch) -> None:
    queue = wq.Queue(tmp_path / "kt_work").ensure()
    queue.publish({"id": wq.job_id("a"), "kind": "k", "class": "c",
                   "version": "1.0", "needs": [], "label": "a",
                   "payload": {}})
    parked = tmp_path / "parked"
    real = wq.Queue.finish
    away = {"on": True}

    def finish(self, *args, **kwargs):
        if away["on"]:
            raise OSError("the share is away")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(wq.Queue, "finish", finish)
    said = []
    wq.work(queue, "Pav-mixed", "cpu", "1.0", {"k": lambda *a: {"ok": 1}},
            lambda: False, lambda key, values: said.append(key), once=True,
            sleep=lambda s: None, parked=parked)
    assert "helper_answer_parked" in said and list(parked.glob("*.json"))
    away["on"] = False
    assert wq._deliver_parked(queue, parked, lambda *a: None) == 1
    assert not list(parked.glob("*.json"))
    assert queue.answers()[0]["result"]["ok"] == 1


# -- B673: tests go on after a restart -----------------------------------------------

def test_interrupted_tests_are_remembered_and_forgotten(tmp_path) -> None:
    test_panel.remember_running(tmp_path, ["1.5.14", "9.9.9"], "set", True,
                                (), True)
    found = test_panel.interrupted(tmp_path)
    assert found["codes"] == ["1.5.14"], "only what still exists"
    assert found["scope"] == "set" and found["stop_helpers"] is True
    test_panel.forget_running(tmp_path)
    assert test_panel.interrupted(tmp_path) is None
    test_panel.remember_running(tmp_path, ["1.5.15"], "all")
    assert test_panel.interrupted(tmp_path) is None, "1.5.15 is done"
    assert not (tmp_path / test_panel.RUNNING_FILE).exists()


def test_the_window_goes_on_with_them_and_can_stop_after_current() -> None:
    text = (ROOT / "modules" / "gui.py").read_text(encoding="utf-8")
    assert "QTimer.singleShot(self.RESUME_AFTER_MS, self._resume_tests)" \
        in text
    assert "work_queue.request_finish()" in text
    assert "test_panel.forget_running(logs_dir)" in text


def test_the_daily_log_clean_leaves_the_crash_log(tmp_path) -> None:
    from modules import filesystem

    for day in range(1, 9):
        (tmp_path / f"2026-10-0{day}.log").write_text("x")
    (tmp_path / "crash.log").write_text("x")
    filesystem.clean_logs(tmp_path, keep=5)
    assert (tmp_path / "crash.log").exists()
    assert len(list(tmp_path.glob("2026*.log"))) == 5


# -- B664: a video without a logo has no intro and no outro ------------------------

def test_a_video_without_a_logo_starts_with_the_song(monkeypatch,
                                                      tmp_path) -> None:
    import importlib

    old = importlib.import_module("tests.test_v0149") \
        if (ROOT / "tests" / "__init__.py").exists() else None
    from modules import video

    if old is None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "v0149", ROOT / "tests" / "test_v0149.py")
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
    real = video.render_video

    def no_logo(lines, audio, logo, *args, **kwargs):
        return real(lines, audio, None, *args, **kwargs)

    monkeypatch.setattr(video, "render_video", no_logo)
    seen = old._capture(monkeypatch, tmp_path, old._lines(3.785),
                        silence=0.0)
    assert "error" not in seen, seen.get("error")
    assert old._audio_filter(seen["command"]) == "apad", \
        "no silence put in front for an intro"
    from modules import pipeline

    assert "logo" in pipeline.VIDEO_INPUT_OPTIONAL


# -- B663: the test set builds itself ------------------------------------------------

def test_the_set_appears_with_two_songs_per_group(tmp_path) -> None:
    from modules import test_set

    context = type("C", (), {})()
    context.paths = type("P", (), {})()
    context.paths.config_dir = tmp_path / "config"
    context.paths.root = tmp_path
    import modules.front_to_back as ftb

    original = ftb.scratch_root
    ftb.scratch_root = lambda c: tmp_path / "none"
    try:
        test_set.note_errors(context, {f"S{n}": n * 0.1 for n in range(5)},
                             "1.5.15")
        assert not test_set.ready(context), "five songs: not yet"
        test_set.note_errors(context, {"S5": 0.5}, "1.5.20")
        groups = test_set.current(context)
        assert groups == {"good": ["S0", "S1"], "medium": ["S2", "S3"],
                          "problem": ["S4", "S5"]}
        test_set.note_errors(context, {"S0": 3.0}, "1.5.15")
        assert "S0" in test_set.current(context)["problem"], \
            "the newest measurement counts"
        test_set.save(context, {"good": ["S9"], "medium": [], "problem": []},
                      basis="owner")
        assert test_set.current(context)["good"] == ["S9"], "pinned"
        test_set.unpin(context)
        assert test_set.current(context)["good"] != ["S9"]
        test_set.save(context, {"good": ["S9"], "medium": [], "problem": []},
                      basis="1.5.13")
        assert not test_set.pinned(context), "an old proposal is not pinned"
        test_set.save(context, {"good": ["S9"], "medium": [], "problem": []},
                      basis="chosen by hand")
        assert test_set.pinned(context)
    finally:
        ftb.scratch_root = original


def test_the_yardsticks_leave_their_errors() -> None:
    for name in ("block_trial", "stem_trial", "lyrics_trial"):
        text = (ROOT / "modules" / f"{name}.py").read_text(encoding="utf-8")
        assert "remember_errors(context, results" in text, name


# -- B667/B668: dips in the music ----------------------------------------------------

def _tone(seconds, rate=8000, hole=None):
    import numpy as np

    t_ = np.arange(int(seconds * rate)) / rate
    out = (0.3 * np.sin(2 * np.pi * 220 * t_)).astype(np.float32)
    if hole is not None:
        out[int(hole[0] * rate):int(hole[1] * rate)] *= 0.001
    return out[:, None]


def test_a_dip_is_filled_from_the_part_that_kept_the_music() -> None:
    import numpy as np

    from modules import stem_blend

    full = _tone(10.0)
    holed = _tone(10.0, hole=(4.0, 6.0))
    joined = stem_blend.join([full, holed], "avg_wave")
    fixed, spans = stem_blend.repair_dips(joined, [full, holed], 8000)
    assert spans and spans[0][0] <= 4.1 and spans[0][1] >= 5.9
    middle = slice(int(4.5 * 8000), int(5.5 * 8000))
    assert np.allclose(fixed[middle], full[middle], atol=1e-4), \
        "at the part's own level"
    assert np.allclose(fixed[:int(3.5 * 8000)], joined[:int(3.5 * 8000)])
    same, none = stem_blend.repair_dips(full, [full, full], 8000)
    assert none == []


def test_the_repair_is_a_way_of_its_own_in_1_5_14() -> None:
    way = separation.BLENDS["demucs_repair"]
    assert way.algorithm == "avg_wave+repair"
    assert separation_trial.WAYS[-1].key == "demucs_blend_repair"
    assert "+" not in way.folder("original")


def test_the_dips_of_a_music_track_are_placed_in_time() -> None:
    mix = _tone(20.0)
    music = _tone(20.0, hole=(8.0, 11.0))
    spans = separation_trial.dip_spans(music, 8000, mix, 8000)
    assert spans == [(8.0, 11.0)]
    assert separation_trial.dip_spans(mix, 8000, mix, 8000) == []


def test_the_github_texts_say_what_it_is_for() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "original lyrics or with lyrics of your" in text
    assert "Create karaoke videos for carnival parodies" not in text


def test_stopping_after_current_never_waits_for_a_round_that_came_back(
        tmp_path) -> None:
    import os

    queue = wq.Queue(tmp_path / "kt_work").ensure()
    jobs = [{"id": wq.job_id(k), "kind": "k", "class": "c", "needs": [],
             "label": k, "payload": {}} for k in ("a", "b")]

    def handler(job, q, stop):
        other, _ = q.claim("Pav-mixed", "1.0")
        wq.request_finish()
        if other is not None:
            # Its helper falls silent and the round comes back.
            name = f"{other['id']}.json"
            os.replace(q.claimed / name, q.jobs / name)
        return {}

    result = {}

    def go():
        result["counts"] = wq.run_jobs(queue, jobs, "1.0", {"k": handler},
                                       lambda a: None, lambda: False,
                                       poll_s=0.05, sleep=lambda s: None)

    worker = threading.Thread(target=go, daemon=True)
    try:
        worker.start()
        worker.join(10.0)
        assert not worker.is_alive(), "the test ends"
        assert result["counts"]["local"] == 1
    finally:
        wq.clear_finish()
