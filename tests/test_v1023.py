"""v1.0.23: after Pav switched itself off with the heat.

* the helper has a small window of its own with the program's icon, and
  can stop after the round it is on, or at once (B640);
* a card with less than 6 GB is not used; ``lanes.txt`` says otherwise
  per computer (B641);
* a computer with an NVIDIA card takes no work while it is too hot, and
  gives a round back that keeps it too hot (B642);
* the ensembles of 1.5.14 are blends of single models, one round per
  model through the queue, the blend after them (B643);
* the helper installer fetches the Whisper model, and the window leaves
  out the chatter of the downloads (B648);
* PyTorch that does not load: the Visual C++ runtime brought up to date,
  and no Demucs rounds for a helper where torch does not load (B649);
* the work folder ``kt_work`` in the program's helper folder (B650);
* the known text laid on the voice between the heard lines (B651), and
  test 1.5.20 measuring it through the helpers that have WhisperX
  (B652).
"""
from __future__ import annotations

import importlib.util
import os
import queue as queue_module
from pathlib import Path

import pytest

from modules import __version__, cuda, heat_guard, separation
from modules import work_queue as wq

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _helper():
    spec = importlib.util.spec_from_file_location(
        "helper_v1023", ROOT / "tools" / "helper.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _queue(tmp_path) -> wq.Queue:
    return wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()


def _job(key: str, version: str = "1.0", **extra) -> dict:
    job = {"id": wq.job_id(key), "kind": "k", "class": "c",
           "version": version, "label": key, "needs": [],
           "payload": {"key": key}}
    job.update(extra)
    return job


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# -- B640: stop after the current round -----------------------------------------------

def test_a_worker_finishes_its_round_and_then_stops(tmp_path) -> None:
    queue = _queue(tmp_path)
    for key in ("a", "b"):
        queue.publish(_job(key))
    done, said = [], []
    asked = {"finish": False}

    def handler(job, queue_, stop):
        done.append(job["payload"]["key"])
        asked["finish"] = True          # the owner clicks during the round
        return {"ok": True}

    outcome = wq.work(queue, "pc-cpu", "cpu", "1.0", {"k": handler},
                      lambda: False, say=lambda key, v: said.append(key),
                      idle_s=0, sleep=lambda s: None,
                      finish_check=lambda: asked["finish"])
    assert outcome == "stopped" and done == ["a"], "the round, then stop"
    assert "helper_finish_asked" in said
    assert len(queue.answers()) == 1, "its answer was given"
    assert len(list(queue.jobs.glob("*.json"))) == 1, "b waits for another"
    (status,) = queue.active_workers() or [{"state": "stopped"}]
    assert status["state"] == "stopped"


def test_the_flags_of_the_window(tmp_path) -> None:
    helper = _helper()
    helper.set_flag(helper.FINISH_FLAG, True, home=tmp_path)
    assert (tmp_path / helper.FINISH_FLAG).exists()
    helper.set_flag(helper.FINISH_FLAG, False, home=tmp_path)
    assert not (tmp_path / helper.FINISH_FLAG).exists()
    helper.set_flag(helper.STOP_FLAG, True, home=tmp_path)
    helper.clear_flags(home=tmp_path)
    assert not list(tmp_path.iterdir()), "a new start begins clean"


class _Child:
    def __init__(self, code):
        self.code = code

    def poll(self):
        return self.code


def test_carry_on_after_all_starts_a_lane_that_had_ended(
        tmp_path, monkeypatch) -> None:
    helper = _helper()
    monkeypatch.setattr(helper, "HOME", tmp_path)
    monkeypatch.setattr(helper.time, "sleep", lambda s: None)
    started = []
    rounds = {"n": 0}

    class Child:
        def __init__(self, lane):
            self.lane = lane
            self.polls = 0

        def poll(self):
            self.polls += 1
            rounds["n"] += 1
            if self.lane == "cpu" and len(started) == 2:
                return 0                       # it ended on the flag
            if rounds["n"] == 3:
                helper.set_flag(helper.FINISH_FLAG, False)   # carry on
            return 0 if self.polls > 6 else None

    def start(lane):
        started.append(lane)
        return Child(lane)

    helper.set_flag(helper.FINISH_FLAG, True)
    helper._supervise(start, ["gpu", "cpu"], "")
    assert started.count("cpu") == 2, "started again after 'carry on'"


def test_lanes_txt_as_windows_writes_it(tmp_path) -> None:
    helper = _helper()
    for raw in ("gpu,cpu".encode("utf-16"), b"\xef\xbb\xbfgpu,cpu",
                b"gpu\r\ncpu\r\n"):
        (tmp_path / helper.LANES_FILE).write_bytes(raw)
        assert helper.lanes_wanted("auto", home=tmp_path) == "gpu,cpu"


def test_a_lane_that_ends_after_the_owner_asked_is_not_restarted(
        tmp_path, monkeypatch) -> None:
    helper = _helper()
    monkeypatch.setattr(helper, "HOME", tmp_path)
    monkeypatch.setattr(helper.time, "sleep", lambda s: None)
    started = []

    def start(lane):
        started.append(lane)
        return _Child(1)            # stopped by "stop now": not 0

    helper.set_flag(helper.STOP_FLAG, True)
    codes = helper._supervise(start, ["gpu", "cpu"], "")
    assert started == ["gpu", "cpu"] and codes == {"gpu": 1, "cpu": 1}


def test_the_window_shows_the_lanes_and_asks_the_lanes_to_stop(
        qapp) -> None:
    from modules.helper_window import HelperWindow
    from modules.translations import t

    lines: queue_module.Queue = queue_module.Queue()
    lines.put("[cpu] Bezig: Lied R - Demucs")
    asked = []
    done = {"now": False}
    status = {"cpu": {"state": "working", "job": "Lied R - Demucs",
                      "left_s": 600}, "gpu": {"state": "cooling"}}
    window = HelperWindow("KaraokeTool helper", ["gpu", "cpu"],
                          status.get, lines,
                          lambda on: asked.append(("finish", on)),
                          lambda: asked.append(("now",)),
                          lambda: done["now"])
    assert not window.windowIcon().isNull() or not (
        ROOT / "assets" / "icons" / "karaoketool.ico").exists()
    window._tick()
    assert "Lied R - Demucs" in window._log.toPlainText()
    window.show_status()
    assert window._table.item(1, 1).text() == t("helper_state_working")
    assert "Lied R - Demucs" in window._table.item(1, 2).text()
    assert window._table.item(0, 1).text() == t("helper_state_cooling")
    window._toggle_finish()
    window._toggle_finish()
    assert asked == [("finish", True), ("finish", False)], "undone again"
    window._now()
    assert asked[-1] == ("now",) and not window._stop_button.isEnabled()
    done["now"] = True
    window._tick()
    assert not window.isVisible()


def test_the_helper_starts_in_its_window_and_ends_quietly() -> None:
    start = _read(ROOT / "helper" / "helper_start.bat")
    assert '"%PYW%" "app\\tools\\helper.py" --share "%SHARE%" --window' in \
        start
    assert "if errorlevel 4 if not errorlevel 5 goto :owner_stopped" in start
    stopped = start[start.index("\n:owner_stopped"):]
    assert "pause" not in stopped.split("exit /b 0")[0]
    install = _read(ROOT / "helper" / "install_helper.bat")
    # v1.0.24 (B653): the shortcut starts the window itself, not minimised.
    assert "$s.IconLocation='%APP%\\assets\\icons\\karaoketool.ico,0'" in \
        install and "$s.WindowStyle=1" in install
    helper = _read(ROOT / "tools" / "helper.py")
    assert "OWNER_EXIT = 4" in helper and "_console_python()" in helper


def test_the_lanes_run_under_python_exe_when_the_helper_is_pythonw(
        tmp_path, monkeypatch) -> None:
    helper = _helper()
    (tmp_path / "python.exe").write_bytes(b"")
    monkeypatch.setattr(helper.sys, "executable",
                        str(tmp_path / "pythonw.exe"))
    assert helper._console_python() == str(tmp_path / "python.exe")


# -- B641: the card only where it can -----------------------------------------------

def test_a_small_card_gets_no_lane_unless_the_owner_says_so(
        tmp_path) -> None:
    helper = _helper()
    # v1.0.24 (B646): a small card gets the one lane that does a round on
    # the card or on the processor.
    assert helper.choose_lanes("auto", True, big_enough=False) == \
        [helper.MIXED]
    assert helper.choose_lanes("auto", True, big_enough=True) == \
        ["gpu", "cpu"]
    assert helper.choose_lanes("gpu,cpu", True, big_enough=False) == \
        ["gpu", "cpu"], "the owner's choice"
    assert helper.lanes_wanted("auto", home=tmp_path) == "auto"
    (tmp_path / helper.LANES_FILE).write_text("GPU + CPU\n")
    assert helper.lanes_wanted("auto", home=tmp_path) == "gpu,cpu"
    assert helper.lanes_wanted("cpu", home=tmp_path) == "cpu"


def test_what_is_big_enough() -> None:
    assert cuda.MIN_CARD_GB == 6.0
    assert not cuda.big_enough({"memory_gb": 4.0})
    assert cuda.big_enough({"memory_gb": 8.0})
    assert cuda.big_enough({}), "unknown: the test said it works"
    small = cuda.for_the_program({"gpu_ok": True, "torch": True,
                                  "card": "GTX 1650", "device": "cuda",
                                  "compute": "float16", "memory_gb": 4.0})
    assert small["gpu_ok"] is False and small["device"] == "cpu" and \
        small["too_small"] and small["card"] == "GTX 1650"
    big = {"gpu_ok": True, "memory_gb": 12.0, "device": "cuda"}
    assert cuda.for_the_program(big) == big


# -- B642: the heat ---------------------------------------------------------------------

class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_a_hot_computer_waits_until_it_has_cooled() -> None:
    clock = _Clock()
    degrees = {"now": 75.0}
    guard = heat_guard.HeatGuard(read=lambda: degrees["now"], clock=clock)
    assert guard.must_wait() is None
    degrees["now"] = 82.0
    clock.now += 61
    assert guard.must_wait() == 82.0
    degrees["now"] = 74.0
    clock.now += 61
    assert guard.must_wait() == 74.0, "not below 70 yet"
    degrees["now"] = 69.0
    clock.now += 61
    assert guard.must_wait() is None


def test_a_round_that_stays_too_hot_is_stopped_and_cools_first() -> None:
    clock = _Clock()
    degrees = {"now": 90.0}
    guard = heat_guard.HeatGuard(read=lambda: degrees["now"], clock=clock)
    assert not guard.watch()
    clock.now += 30
    assert not guard.watch()
    clock.now += 31
    assert guard.watch()
    guard.aborted()
    degrees["now"] = 50.0
    clock.now += 61
    assert guard.must_wait() == 50.0, "the cool-down lasts, cold or not"
    clock.now += heat_guard.COOL_S
    assert guard.must_wait() is None
    no_card = heat_guard.HeatGuard(read=lambda: None, clock=clock)
    assert no_card.must_wait() is None and not no_card.watch()


class _Heat:
    WATCH_S = 0.01

    def __init__(self, hot_first=0):
        self.waits = hot_first
        self.aborts = 0

    def must_wait(self):
        if self.waits:
            self.waits -= 1
            return 85.0
        return None

    def watch(self):
        return True

    def aborted(self):
        self.aborts += 1


def test_a_too_hot_round_goes_back_into_the_queue(tmp_path) -> None:
    import time

    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    said = []
    heat = _Heat(hot_first=1)
    rounds = []

    def handler(job, queue_, stop):
        rounds.append(job["id"])
        for _n in range(200):        # Whisper, say: it listens to a stop
            if stop():
                return {"cancelled": True}
            time.sleep(0.01)
        return {"ok": True}

    outcome = wq.work(queue, "pc-gpu", "gpu", "1.0", {"k": handler},
                      lambda: len(rounds) >= 1 and heat.aborts >= 1,
                      say=lambda key, v: said.append(key), idle_s=0,
                      sleep=lambda s: None, heat=heat)
    assert outcome == "stopped"
    assert said[0] == "helper_cooling", "no round while it is hot"
    assert "helper_too_hot" in said and heat.aborts == 1
    (waiting,) = queue.jobs.glob("*.json")
    import json
    assert json.loads(waiting.read_text())["tries"] == 0, \
        "the heat is not the round's fault: no try counted"
    assert not queue.answers()


def test_a_round_done_while_too_hot_keeps_its_answer(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    heat = _Heat()
    outcome = wq.work(queue, "pc-gpu", "gpu", "1.0",
                      {"k": lambda job, q, stop: __import__("time").sleep(
                          0.1) or {"ok": True}},
                      lambda: heat.aborts >= 1, idle_s=0,
                      sleep=lambda s: None, heat=heat)
    assert outcome == "stopped" and len(queue.answers()) == 1
    assert heat.aborts == 1, "it cools down all the same"


def test_the_owners_stop_goes_before_an_update(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    asked = {"finish": False}

    def handler(job, q, stop):
        asked["finish"] = True
        return {"ok": True}

    outcome = wq.work(queue, "pc-cpu", "cpu", "1.0", {"k": handler},
                      lambda: False, idle_s=0, sleep=lambda s: None,
                      update_check=lambda: True,
                      finish_check=lambda: asked["finish"])
    assert outcome == "stopped"


# -- B643: smaller rounds ---------------------------------------------------------------

def test_a_round_waits_for_the_rounds_it_comes_after(tmp_path) -> None:
    queue = _queue(tmp_path)
    part = _job("part")
    blend = _job("blend", after=[part["id"]], priority=5)
    queue.publish(blend)
    queue.publish(part)
    first, _newer = queue.claim("pc", "1.0")
    assert first["id"] == part["id"], "the blend waits, priority or not"
    assert queue.claim("pc", "1.0")[0] is None, "its part is being made"
    queue.finish(first, {"ok": True}, "pc", "cpu")
    second, _newer = queue.claim("pc", "1.0")
    assert second["id"] == blend["id"]


def test_the_ensembles_are_blends_of_single_models() -> None:
    from modules import separation_trial as st

    for key, models in (("roformer_karaoke_trio", st.KARAOKE_TRIO),
                        ("roformer_music_clean", st.MUSIC_CLEAN),
                        ("roformer_voice_clean", st.VOICE_CLEAN)):
        way = next(w for w in st.WAYS if w.key == key).way
        assert way.backend == "blend"
        assert [part.model for part in way.parts] == models.split("+")
        assert all(part.backend == "roformer" for part in way.parts)
        assert st.needs_of(next(w for w in st.WAYS if w.key == key)) == \
            ["ffmpeg", "roformer"]
    trio = next(w for w in st.WAYS if w.key == "roformer_karaoke_trio")
    karaoke = next(w for w in st.WAYS if w.key == "roformer_karaoke")
    parts = st._parts_to_make([trio])
    assert len(parts) == 3
    assert karaoke.way in st._parts_to_make([trio]) and \
        karaoke.way not in st._parts_to_make([trio, karaoke]), \
        "a part that is a way of its own is made by its own round"
    assert st.keeps_stems(karaoke)


def test_a_part_round_keeps_its_stems_for_the_blend(tmp_path,
                                                    monkeypatch) -> None:
    import numpy as np
    import soundfile

    from modules import separation_trial as st

    made = []

    def separate(audio, work, way, store=None):
        made.append(way.tag)
        stems = {}
        for name in ("vocals", "instrumental"):
            path = work / f"{name}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            soundfile.write(str(path), np.zeros((10, 2), np.float32), 44100,
                            subtype="FLOAT")
            stems[name] = path
        store.put(way.tag, stems)
        return stems

    monkeypatch.setattr(separation, "separate_way", separate)
    queue = _queue(tmp_path)
    part = separation.Way("roformer", "a.ckpt")
    job = {"id": "p", "payload": {"part": separation.way_data(part),
                                  "stems": "files/stems/x",
                                  "mix": "files/mix.wav", "key": "k"}}
    answer = st.run_round(job, queue, lambda: False)
    assert answer["kept"] == part.tag and made == [part.tag]
    again = st.run_round(job, queue, lambda: False)
    assert again == {"kept": part.tag, "seconds": 0.0} and \
        made == [part.tag], "kept: not made twice"


def test_1_5_14_puts_the_parts_out_before_their_blend() -> None:
    import inspect

    from modules import separation_trial as st

    source = inspect.getsource(st._share_out)
    assert 'job["after"] = sorted(' in source
    assert '"part": separation.way_data(part)' in source
    assert "parts_of = {song: _parts_to_make(todo_of[song])" in \
        inspect.getsource(st.run)


def test_the_helper_files_carry_this_version() -> None:
    helper = _helper()
    for name in ("install_helper.bat", "helper_start.bat"):
        assert helper.installer_version(ROOT / "helper" / name) == \
            __version__


def test_every_new_text_is_in_both_languages() -> None:
    from modules.translations import TRANSLATIONS

    for key in ("helper_finish", "helper_stop_now", "helper_cooling",
                "helper_too_hot", "helper_card_too_small",
                "helper_state_cooling", "helper_window_title",
                "helper_close_ask", "helper_finish_asked"):
        assert key in TRANSLATIONS["nl"] and key in TRANSLATIONS["en"], key


def test_the_program_can_take_a_part_round_itself() -> None:
    import inspect

    from modules import separation_trial as st

    source = inspect.getsource(st._share_out)
    assert 'kind=job["payload"].get("way") or PART' in source


def test_a_cooling_helper_here_keeps_the_program_off_this_computer(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.status(f"{wq.host_name()}-cpu", "cooling", "cpu")
    assert not wq.may_work_here(queue)
    assert wq.helpers_idle(queue), "and it takes no round either"


# -- B647: a round's input fetched once --------------------------------------------

def test_a_rounds_input_is_fetched_once_and_cleared(tmp_path,
                                                    monkeypatch) -> None:
    from modules import local_copy

    monkeypatch.setattr(local_copy.tempfile, "gettempdir",
                        lambda: str(tmp_path / "temp"))
    root = tmp_path / "share" / "kt_work"
    (root / "files" / "song").mkdir(parents=True)
    (root / "files" / "song" / "audio.wav").write_bytes(b"a" * 100)
    (root / "files" / "mix.wav").write_bytes(b"m" * 10)
    with local_copy.fetched(root, "job/1", ["files/mix.wav", "files/song"],
                            copy=True) as (mix, song):
        assert mix.read_bytes() == b"m" * 10 and mix.parent.parent == \
            tmp_path / "temp" / local_copy.FOLDER_NAME
        assert (song / "audio.wav").exists()
        kept = mix.parent
    assert not kept.exists(), "cleared afterwards"
    with local_copy.fetched(root, "x", ["files/mix.wav"]) as (mix,):
        assert mix == root / "files" / "mix.wav", "a local queue: as is"
    assert local_copy.is_remote(Path(r"\\10.0.0.18\Tools\kt_work"))
    assert not local_copy.is_remote(Path(r"C:/Muziek\kt_work"))


def test_a_copy_goes_also_when_the_round_fails(tmp_path, monkeypatch) -> None:
    from modules import local_copy

    monkeypatch.setattr(local_copy.tempfile, "gettempdir",
                        lambda: str(tmp_path / "temp"))
    (tmp_path / "m.wav").write_bytes(b"x")
    with pytest.raises(RuntimeError):
        with local_copy.fetched(tmp_path, "j", ["m.wav"], copy=True):
            raise RuntimeError("the round fell over")
    assert not list((tmp_path / "temp" / local_copy.FOLDER_NAME).iterdir())


def test_what_a_crash_left_goes_at_the_next_start(tmp_path,
                                                  monkeypatch) -> None:
    import time as time_module

    from modules import local_copy

    monkeypatch.setattr(local_copy.tempfile, "gettempdir",
                        lambda: str(tmp_path))
    old = tmp_path / local_copy.FOLDER_NAME / "old"
    new = tmp_path / local_copy.FOLDER_NAME / "new"
    old.mkdir(parents=True)
    new.mkdir()
    past = time_module.time() - 2 * local_copy.STALE_S
    os.utime(old, (past, past))
    assert local_copy.tidy() == 1 and not old.exists() and new.exists()


def test_every_round_that_reads_a_song_fetches_it_first() -> None:
    import inspect

    from modules import jamendo_trial, musdb_trial, separation_trial
    from modules import shared_work, stem_trial

    for function in (shared_work.run_round, shared_work.run_render_round,
                     separation_trial.run_round, separation_trial.part_round,
                     stem_trial.prep_round, musdb_trial.run_round,
                     jamendo_trial.run_round):
        assert "fetched(queue.root, job[\"id\"]" in \
            inspect.getsource(function), function.__qualname__
    assert "local_copy.tidy()" in _read(ROOT / "tools" / "helper.py")


# -- B648: the Whisper model at the installation, and a quiet window ---------------

def test_the_installer_fetches_the_whisper_model() -> None:
    text = _read(ROOT / "helper" / "install_helper.bat")
    assert 'helper.py" --prefetch-whisper' in text


def test_a_model_that_is_there_is_not_fetched_again(capsys) -> None:
    helper = _helper()
    fetched: list = []
    assert helper.prefetch_whisper(download=fetched.append,
                                   cached=lambda settings: True) == 0
    assert fetched == []
    assert helper.prefetch_whisper(download=fetched.append,
                                   cached=lambda settings: False) == 0
    assert fetched == ["large-v3"], "the model the rounds use"


def test_a_failed_download_is_left_to_the_first_round(capsys) -> None:
    helper = _helper()

    def download(model):
        raise OSError("no network")

    assert helper.prefetch_whisper(download=download,
                                   cached=lambda settings: False) == 1
    assert "no network" in capsys.readouterr().out


def test_the_window_leaves_out_the_download_chatter() -> None:
    import logging

    helper = _helper()
    chatter = helper._NotChatty()

    def record(name: str, level: int) -> logging.LogRecord:
        return logging.LogRecord(name, level, __file__, 1, "x", (), None)

    assert not chatter.filter(record("httpx", logging.INFO))
    assert not chatter.filter(record("huggingface_hub.file_download",
                                     logging.INFO))
    assert chatter.filter(record("httpx", logging.WARNING))
    assert chatter.filter(record("helper", logging.INFO))
    env = helper.quiet_downloads({})
    assert env["HF_HUB_DISABLE_SYMLINKS_WARNING"] == "1"
    assert env["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"
    assert helper.quiet_downloads({"HF_HUB_DISABLE_PROGRESS_BARS": "0"})[
        "HF_HUB_DISABLE_PROGRESS_BARS"] == "0", "the owner's own setting"


def test_the_log_file_keeps_the_chatter(tmp_path) -> None:
    import logging

    from modules import logger

    helper = _helper()
    root = logging.getLogger()
    kept = list(root.handlers)
    try:
        logger.setup_logging(tmp_path)
        helper.quiet_window()
        files = [handler for handler in root.handlers
                 if isinstance(handler, logging.FileHandler)]
        others = [handler for handler in root.handlers
                  if not isinstance(handler, logging.FileHandler)]
        assert files and not any(handler.filters for handler in files)
        assert all(handler.filters for handler in others)
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers[:] = kept


# -- B649: PyTorch that does not load ----------------------------------------------

class _Done:
    def __init__(self, code: int, stderr: str = "") -> None:
        self.returncode, self.stderr, self.stdout = code, stderr, ""


def test_torch_that_does_not_load_is_said_in_its_last_line(
        monkeypatch) -> None:
    from modules import proc

    calls: list = []
    trace = ("Traceback (most recent call last):\n  File ...\n"
             "OSError: [WinError 1114] Error loading \"c10.dll\" or one of "
             "its dependencies.\n")
    monkeypatch.setattr(separation, "_TORCH_CHECKED", {})
    monkeypatch.setattr(proc, "run", lambda command, **kw: calls.append(
        command) or _Done(1, trace))
    problem = separation.torch_problem("py-a")
    assert problem.startswith("OSError: [WinError 1114]")
    assert separation.torch_problem("py-a") == problem
    assert len(calls) == 1, "tried once per environment"
    monkeypatch.setattr(proc, "run", lambda command, **kw: _Done(0))
    assert separation.torch_problem("py-b") is None


def test_a_helper_without_torch_takes_no_demucs_rounds(monkeypatch) -> None:
    from modules import ffmpeg

    helper = _helper()
    monkeypatch.setattr(ffmpeg, "is_available", lambda: True)
    monkeypatch.setattr(separation, "is_available", lambda way=None: True)
    monkeypatch.setattr(separation, "roformer_python", lambda: None)
    said: list = []
    monkeypatch.setattr(separation, "torch_problem",
                        lambda python=None: "OSError: c10.dll")
    have = helper.capabilities(lambda key, values: said.append(key))
    assert "demucs" not in have and "whisper" in have
    assert "helper_no_torch" in said
    monkeypatch.setattr(separation, "torch_problem", lambda python=None: None)
    assert "demucs" in helper.capabilities(lambda key, values: None)


def test_the_visual_cpp_files_torch_needs(tmp_path) -> None:
    setup_check = _load_tool("setup_check")
    assert "vcruntime140_threads.dll" in setup_check.VC_RUNTIME_FILES
    assert "msvcp140_atomic_wait.dll" in setup_check.VC_RUNTIME_FILES
    (tmp_path / "vcruntime140.dll").write_bytes(b"")
    (tmp_path / "msvcp140.dll").write_bytes(b"")
    missing = setup_check.vc_runtime_missing(tmp_path)
    assert "vcruntime140.dll" not in missing
    assert "vcruntime140_1.dll" in missing and len(missing) == 4
    for name in setup_check.VC_RUNTIME_FILES:
        (tmp_path / name).write_bytes(b"")
    assert setup_check.vc_runtime_missing(tmp_path) == []


def test_the_installer_tries_torch_and_updates_the_runtime() -> None:
    text = _read(ROOT / "helper" / "install_helper.bat")
    assert 'call :torch_check "%VENV%"' in text
    assert 'call :torch_check "%SEPENV%"' in text
    assert text.index('call :torch_check "%SEPENV%"') < \
        text.index("roformer_separate.py\" --selftest")
    assert "setup_check.py\" --vc-runtime" in text
    assert "winget upgrade -e --id Microsoft.VCRedist.2015+.x64" in text
    assert "winget install -e --id Microsoft.VCRedist.2015+.x64" in text
    assert "if defined VCDONE exit /b 0" in text, "once per installation"


def _load_tool(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{name}_v1023", ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- B650: kt_work in the helper folder ---------------------------------------------

class _Paths:
    def __init__(self, root: Path) -> None:
        self.root = root


class _Context:
    def __init__(self, root: Path) -> None:
        self.paths = _Paths(root)


def test_the_queue_lives_in_the_programs_helper_folder(tmp_path) -> None:
    program = tmp_path / "Tools" / "KaraokeTool"
    queue = wq.queue_for(_Context(program))
    assert queue.root == program / "helper" / "kt_work"
    assert wq.old_queue_folder(queue.root) == tmp_path / "Tools" / "kt_work"
    assert wq.old_queue_folder(tmp_path / "somewhere" / "kt_work") is None


def test_a_helper_finds_the_queue_in_the_program_folder_on_the_share(
        tmp_path, monkeypatch) -> None:
    import json

    helper = _helper()
    share = tmp_path / "Tools" / "KaraokeTool"
    folder = wq.queue_folder(share)
    folder.mkdir(parents=True)
    (folder / "laptop.json").write_text(json.dumps(
        {"host": "laptop1", "addresses": ["10.0.0.18"]}), encoding="utf-8")
    monkeypatch.setattr(helper, "HOME", tmp_path / "home")
    (tmp_path / "home").mkdir()
    helper.remember(str(share))
    known = json.loads((tmp_path / "home" / "known.json").read_text(
        encoding="utf-8"))
    assert known["host"] == "laptop1"
    source = _read(ROOT / "tools" / "helper.py")
    assert "queue_dir = work_queue.queue_folder(args.share)" in source
    assert "kt_werk" not in source


def test_the_queue_is_not_copied_to_the_helpers_nor_to_github() -> None:
    text = _read(ROOT / "helper" / "install_helper.bat")
    line = [row for row in text.splitlines()
            if row.startswith('robocopy "%SHARE%" "%APP%" /MIR')][0]
    assert " kt_work " in line.split("/XD", 1)[1].split("/XF")[0] + " "
    export = _load_tool("github_export")
    assert "kt_work" in export.SKIPPED_FOLDERS
    assert "helper/kt_work/" in export.GITIGNORE_TEXT


def test_kt_werk_is_gone() -> None:
    assert not hasattr(wq, "LEGACY_QUEUE_NAME")
    assert wq.QUEUE_HOME == "helper"


# -- B651: the text laid on the voice between the heard lines ------------------------

def _tline(index, words, start, quality="high", length=0.4, gap=0.1,
           made=False):
    from modules.timing import Syllable, TimedLine

    pieces, moment = [], start
    for n, word in enumerate(words):
        pieces.append(Syllable(text=(" " if n else "") + word,
                               start=round(moment, 3),
                               end=round(moment + length, 3)))
        moment += length + gap
    return TimedLine(index=index, text=" ".join(words), crowd=False,
                     syllables=tuple(pieces), quality=quality, made=made)


def test_the_stretches_lie_between_the_heard_lines() -> None:
    from modules import pipeline

    timed = (_tline(0, ["ik", "zie"], 1.0),
             _tline(1, ["jou", "niet"], 4.0, "low"),
             _tline(2, ["meer", "hier"], 6.0, "low"),
             _tline(3, ["ja", "ja"], 9.0, "high"),
             _tline(4, ["nee", "nee"], 12.0, "low"))
    rows = list(range(5))
    found = pipeline.stretches(timed, rows)
    assert found[0] == ([1, 2], timed[0].end, timed[3].start)
    assert found[1] == ([4], timed[3].end,
                        timed[4].end + pipeline._STRETCH_EDGE_S)
    # v1.0.27: the qualities the coupling gives are the anchors.
    assert set(pipeline.STRETCH_ANCHORS) <= {"high", "medium", "low"}


def test_a_line_laid_on_is_no_anchor() -> None:
    from modules import pipeline

    timed = (_tline(0, ["ik"], 1.0), _tline(1, ["jou"], 3.0, made=True),
             _tline(2, ["nu"], 5.0))
    assert pipeline.stretches(timed, [0, 1, 2]) == \
        [([1], timed[0].end, timed[2].start)]


def test_the_found_words_go_back_to_their_lines_by_their_letters() -> None:
    from modules import pipeline

    found = [["Ik", 1.0, 1.2, 0.9], ["jou,", 2.0, 2.2, 0.8],
             ["niet", 2.3, 2.5, 0.7]]
    out = pipeline.split_found([["ik", "zie"], ["jou", "niet"]], found)
    assert [len(words) for words in out] == [1, 2], \
        "a skipped word does not push the rest onto the next line"
    assert out[1][0][0] == "jou,"


def test_a_stretch_must_fit_the_aligner_and_a_singer() -> None:
    from modules import pipeline

    lines = [_tline(0, ["een", "twee", "drie", "vier"], 0.0)]
    assert pipeline._fits(lines, 0.0, 2.0)
    assert not pipeline._fits(lines, 0.0, pipeline._STRETCH_MAX_S + 1)
    assert not pipeline._fits(lines, 0.0, 0.2), "no one sings 20 a second"
    assert pipeline._fits(lines, 0.0, 30.0), \
        "the room also holds what the band plays"


class _Store:
    def get_step(self, name):
        return None


class _AlignContext:
    store = _Store()


def _laid_on(monkeypatch, timed, place):
    from modules import pipeline, word_alignment

    asked: list = []
    monkeypatch.setattr(word_alignment, "is_available", lambda: True)
    monkeypatch.setattr(pipeline, "_language_for", lambda c, track: "nl")
    monkeypatch.setattr(pipeline, "ensure_original_vocals",
                        lambda c: Path("vocals.wav"))

    def align(wav, spans, language):
        asked.extend(spans)
        return [place(low, high, words) for low, high, words in spans]

    monkeypatch.setattr(pipeline, "_align_known_text", align)
    out = pipeline._lyrics_between_anchors(_AlignContext(), timed,
                                           lambda s: s, [])
    return out, asked


def test_a_line_the_coupling_put_off_comes_back_where_it_is_sung(
        monkeypatch) -> None:
    timed = (_tline(0, ["ik", "zie"], 1.0),
             _tline(1, ["jou", "niet"], 10.0, "sentence"),
             _tline(2, ["meer", "hier"], 20.0))

    def place(low, high, words):
        return [[word, 5.0 + n, 5.4 + n, 0.9] for n, word in
                enumerate(words)]

    out, asked = _laid_on(monkeypatch, timed, place)
    assert asked == [(timed[0].end, timed[2].start, ["jou", "niet"])], \
        "one piece in the whole room between the heard lines"
    assert out[1].start == pytest.approx(5.0), "far outside B605's 0.75 s"
    assert out[0] == timed[0] and out[2] == timed[2], "anchors stay"


def test_words_placed_without_certainty_keep_their_time(monkeypatch) -> None:
    timed = (_tline(0, ["ik"], 1.0), _tline(1, ["jou"], 10.0, "even"),
             _tline(2, ["nu"], 20.0))
    out, _asked = _laid_on(monkeypatch, timed, lambda low, high, words: [
        [word, 5.0, 5.4, 0.1] for word in words])
    assert out[1] == timed[1]


def test_mutation_without_the_stretch_room_the_line_stays_off(
        monkeypatch) -> None:
    """Laid on where the coupling put it (B605's room), the aligner
    cannot find a line that is sung seconds away."""
    from modules import pipeline

    real = pipeline.stretches

    def narrow(timed, rows, anchors=()):
        return [(group, timed[rows[group[0]]].start - 0.75,
                 timed[rows[group[-1]]].end + 0.75)
                for group, _low, _high in real(timed, rows, anchors)]

    monkeypatch.setattr(pipeline, "stretches", narrow)
    timed = (_tline(0, ["ik"], 1.0), _tline(1, ["jou"], 10.0, "sentence"),
             _tline(2, ["nu"], 20.0))

    def place(low, high, words):
        return [[word, 5.0, 5.4, 0.9] for word in words
                if low <= 5.2 <= high]

    out, _asked = _laid_on(monkeypatch, timed, place)
    assert out[1] == timed[1]


def test_b651_is_registered_off_and_runs_before_b605() -> None:
    import inspect

    from modules import model_register, pipeline
    from modules.translations import TRANSLATIONS

    model = model_register.by_code("B651")
    assert model is not None and model.default_on is False
    module, name, neutral = model.targets[0]
    assert module is pipeline and name == "_lyrics_between_anchors"
    timed = (_tline(0, ["ja"], 1.0),)
    assert neutral(object(), timed, None, []) is timed
    order = inspect.getsource(pipeline._block_models)
    assert order.index("_fill_linked_blocks") < \
        order.index("_lyrics_between_anchors") < order.index("_lyrics_first")
    for language in ("nl", "en"):
        assert TRANSLATIONS[language]["model_name_b651"]
        assert TRANSLATIONS[language]["model_reason_b651"]


def test_strong_is_gone() -> None:
    """v1.0.27: "strong" (only ``syllable``) means nothing at the
    coupling, where a line is high, medium or low."""
    from modules import model_orders

    assert "B651 strong" not in model_orders.names()


# -- B652: test 1.5.20, and WhisperX on the helpers -----------------------------------

def test_1_5_20_measures_the_aligner_ways_on_request() -> None:
    from modules import lyrics_trial, test_panel

    action = [a for a in test_panel.ACTIONS if a.code == "1.5.20"][0]
    assert action.on_request
    assert lyrics_trial.VARIANTS[0].on == ()
    assert {code for v in lyrics_trial.VARIANTS for code in v.on} == \
        {"B651"}
    assert set(lyrics_trial.CODES) == {"B605", "B651"}
    for variant in lyrics_trial.VARIANTS:
        assert "whisperx" in lyrics_trial.needs_of(variant), \
            "the baseline too, from a computer that times alike"
        states = lyrics_trial.states_for(variant)
        assert states["B651"] is ("B651" in variant.on)
        assert states["B605"] is ("B605" in variant.on)


def test_the_moved_lines_are_counted_better_and_worse() -> None:
    from modules import lyrics_trial

    base = [{"project": "a", "hand_index": [0, 1, 2],
             "hand_starts": [1.0, 5.0, 9.0], "new_starts": [1.0, 7.0, 9.0]}]
    rows = [{"project": "a", "hand_index": [0, 1, 2],
             "hand_starts": [1.0, 5.0, 9.0], "new_starts": [1.02, 5.2, 11.0]}]
    assert lyrics_trial.movement(base, rows) == \
        {"moved": 2, "better": 1, "worse": 1}


def test_b605_rounds_of_1_5_15_need_whisperx() -> None:
    from modules import block_trial

    for variant in block_trial.VARIANTS:
        needs = block_trial.needs_of(variant)
        assert ("whisperx" in needs) is ("B605" in variant.on)


def test_a_helper_aligns_only_where_whisperx_and_torch_are(
        monkeypatch) -> None:
    from modules import ffmpeg, word_alignment

    helper = _helper()
    monkeypatch.setattr(ffmpeg, "is_available", lambda: True)
    monkeypatch.setattr(separation, "is_available", lambda way=None: True)
    monkeypatch.setattr(separation, "roformer_python", lambda: None)
    monkeypatch.setattr(separation, "torch_problem", lambda python=None: None)
    monkeypatch.setattr(word_alignment, "is_available", lambda: True)
    said: list = []
    have = helper.capabilities(lambda key, values: said.append(
        (key, values)))
    assert "whisperx" in have
    ways = dict(said)["helper_can"]["ways"]
    assert "whisperx" not in ways, "it separates with nothing new"
    monkeypatch.setattr(separation, "torch_problem",
                        lambda python=None: "c10.dll")
    assert "whisperx" not in helper.capabilities(lambda k, v: None)
    monkeypatch.setattr(separation, "torch_problem", lambda python=None: None)
    monkeypatch.setattr(word_alignment, "is_available", lambda: False)
    assert "whisperx" not in helper.capabilities(lambda k, v: None)


def test_the_helper_installer_brings_whisperx_before_demucs() -> None:
    text = _read(ROOT / "helper" / "install_helper.bat")
    whisperx = text.index('-m pip install whisperx %TORCHIDX%')
    demucs = text.index('-m pip install -U "demucs>=4.1" %TORCHIDX%')
    assert whisperx < demucs


def test_the_aligner_models_are_fetched_at_the_installation(capsys) -> None:
    helper = _helper()
    loaded: list = []
    assert helper.prefetch_aligners(load=loaded.append) == 0
    assert loaded == ["nl", "en"]

    def broken(language):
        raise OSError("gone")

    assert helper.prefetch_aligners(("nl",), load=broken) == 1
    assert "gone" in capsys.readouterr().out
