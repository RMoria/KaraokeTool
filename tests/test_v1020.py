"""v1.0.20: helpers that keep themselves up to date, Python 3.13, the
NVIDIA card in the program, ordinary work on a faster helper, and how
long things still take.

* a helper compares the version in the installer on the share with the
  one it was installed with, after every job; a newer one stops it, its
  start file runs the installer, and the installer starts it again;
* everything of the helper has an English name; the helpers of v1.0.18
  are bridged (their queue folder, their start file);
* the program and its helpers run on Python 3.13 with 3.12 as the
  fallback; an environment of another Python is made anew;
* the launcher installs what computes on an NVIDIA card and tests it;
  the program takes the card only for what worked, and falls back to
  the processor when Whisper fails on it;
* a separation of ordinary work goes to a helper that is sooner done;
* the tests forecast their end over all workers, ordinary steps say how
  long they still take.

The rules that decide something have a mutation check: the test is run
once more with the rule taken out and has to fail then.
"""
from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
from pathlib import Path

import pytest

from modules import __version__
from modules import work_queue as wq

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _helper():
    return _load("helper_v1020", "tools/helper.py")


def _queue(tmp_path, name: str = wq.QUEUE_NAME) -> wq.Queue:
    return wq.Queue(tmp_path / name).ensure()


def _new_and_old(tmp_path) -> tuple[wq.Queue, wq.Queue]:
    """v1.0.23 (B650): the queue in the program's helper folder, and the
    old one next to the program folder, where the bridge now looks (it
    looked for ``kt_werk`` up to then)."""
    program = tmp_path / "Tools" / "KaraokeTool"
    return (wq.Queue(wq.queue_folder(program)).ensure(),
            wq.Queue(tmp_path / "Tools" / wq.QUEUE_NAME).ensure())


def _job(key: str, cls: str = "c", version: str = "1.0", kind: str = "k",
         needs=()) -> dict:
    return {"id": wq.job_id(key), "run": "r1", "kind": kind, "class": cls,
            "version": version, "label": key, "needs": list(needs),
            "payload": {"key": key}}


def _handlers(done: list):
    def handler(job, queue, cancelled):
        done.append(job["payload"]["key"])
        return {"key": job["payload"]["key"], "seconds": 2.0}
    return {"k": handler}


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


# -- a helper keeps itself up to date ------------------------------------------

def _share_with(tmp_path, version: str) -> Path:
    share = tmp_path / "Tools" / "KaraokeTool"
    (share / "helper").mkdir(parents=True)
    (share / "helper" / "install_helper.bat").write_text(
        f'@echo off\r\nset "HELPER_VERSION={version}"\r\n', encoding="utf-8")
    return share


def test_a_newer_installer_on_the_share_is_an_update(tmp_path) -> None:
    helper = _helper()
    share = _share_with(tmp_path, "1.0.21")
    home = tmp_path / "home"
    home.mkdir()
    assert helper.update_waiting(str(share), home), "never installed"
    (home / helper.INSTALLED_FILE).write_text("1.0.20\n")
    assert helper.update_waiting(str(share), home)
    (home / helper.INSTALLED_FILE).write_text("1.0.21\n")
    assert not helper.update_waiting(str(share), home)
    (home / helper.INSTALLED_FILE).write_text("1.0.22\n")
    assert not helper.update_waiting(str(share), home), "only newer counts"
    assert not helper.update_waiting(str(tmp_path / "gone"), home), \
        "a share that is away is no update"


def test_the_version_is_asked_and_noted_from_the_command_line(
        tmp_path, monkeypatch) -> None:
    helper = _helper()
    monkeypatch.setattr(helper, "HOME", tmp_path)
    share = _share_with(tmp_path, "1.0.21")
    assert helper.main(["--needs-update", str(share)]) == 1
    assert helper.main(["--installed", "1.0.21"]) == 0
    assert (tmp_path / helper.INSTALLED_FILE).read_text().strip() == "1.0.21"
    assert helper.main(["--needs-update", str(share)]) == 0


def test_the_helper_files_carry_the_programs_version() -> None:
    helper = _helper()
    for name in ("install_helper.bat", "helper_start.bat"):
        assert helper.installer_version(ROOT / "helper" / name) == \
            __version__, name


def test_a_worker_stops_for_a_newer_helper_after_its_job(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a", version=__version__))
    queue.publish(_job("b", version=__version__))
    done: list = []
    said: list = []
    outcome = wq.work(queue, "pc-cpu", "cpu", __version__, _handlers(done),
                      lambda: False, say=lambda key, values: said.append(key),
                      idle_s=0, sleep=lambda s: None,
                      update_check=lambda: True)
    assert outcome == "update" and done == ["a"], "one job, then update"
    assert "helper_update" in said
    (status,) = queue.active_workers()
    assert status["state"] == "stopped"


def test_a_waiting_worker_looks_for_a_newer_helper_now_and_then(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    moments = iter([0.0] + [10.0] * 3 + [wq.UPDATE_LOOK_S + 1] * 50)
    looked: list = []

    def check() -> bool:
        looked.append(True)
        return True

    outcome = wq.work(queue, "pc-cpu", "cpu", __version__, {}, lambda: False,
                      idle_s=0, sleep=lambda s: None, update_check=check,
                      clock=lambda: next(moments))
    assert outcome == "update" and len(looked) == 1


def test_mutation_without_the_check_a_helper_never_updates(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a", version=__version__))
    outcome = wq.work(queue, "pc-cpu", "cpu", __version__, _handlers([]),
                      lambda: False, idle_s=0, sleep=lambda s: None,
                      once=True, update_check=lambda: False)
    assert outcome == "stopped"


def test_the_start_file_runs_the_installer_and_ends() -> None:
    raw = (ROOT / "helper" / "helper_start.bat").read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n"), "CRLF"
    start = raw.decode("utf-8")
    assert "--find" in start and "--needs-update" in start
    assert 'copy /y "%SHARE%\\helper\\install_helper.bat" ' \
           '"install_helper_run.bat"' in start
    install_row = next(row for row in start.splitlines()
                       if row.startswith("start ") and "/update" in row)
    after = start[start.index(install_row):].splitlines()
    assert after[-1 if len(after) == 1 else 1].strip() == "exit /b 0", \
        "the helper closes for the update"
    assert 'cmd /c ""%~dp0install_helper_run.bat" /update"' in install_row, \
        "no window left open at a prompt"
    assert "installing.lock" in start, "not a second installation at once"
    assert '"app\\venv\\Scripts\\python.exe" -c ""' in start, \
        "an environment whose Python is gone is installed anew"
    assert "if errorlevel 3 if not errorlevel 4 goto :again" in start
    assert 'rd /s /q "%LOCALAPPDATA%\\KaraokeToolHulp"' in start


def test_the_installer_updates_and_starts_the_helper_again() -> None:
    raw = (ROOT / "helper" / "install_helper.bat").read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n"), "CRLF"
    install = raw.decode("utf-8")
    assert 'call "%APP%\\tools\\find_python.bat" %ASK%' in install
    assert 'if defined UPDATE set "ASK=auto"' in install
    assert '--installed %HELPER_VERSION%' in install
    ending = install[install.index("--installed %HELPER_VERSION%"):]
    # v1.0.24 (B653): the helper starts in its window, without a console.
    assert 'start "" "%PYW%" "%APP%\\tools\\helper.py" --start' \
        in ending.split(":error")[0], "the loop closes: the helper starts"
    assert 'del "%HOME_DIR%\\installing.lock"' in ending
    error = install[install.index(":error"):]
    assert "timeout /t 600" in error and "helper_start.bat" in error, \
        "a failed update tries again by itself"
    assert "KaraokeTool helper.lnk" in install and \
        "KaraokeTool hulp.lnk" in install
    assert "--same-python" in install and "call :renew" in install
    # v1.0.22: 3.12 is gone from every computer, and its clean-up too.
    assert "Python.Python.3.12" not in install


def test_every_batch_file_is_crlf() -> None:
    for path in sorted(ROOT.rglob("*.bat")):
        raw = path.read_bytes()
        assert raw.count(b"\n") == raw.count(b"\r\n"), path.name


# -- English names, and the bridge for the helpers of v1.0.18 ----------------------

def test_the_helper_has_english_names_everywhere() -> None:
    assert not (ROOT / "hulp").exists()
    assert wq.QUEUE_NAME == "kt_work" and wq.OWN_LANE == "program"
    for path in [*(ROOT / "modules").glob("*.py"), ROOT / "tools/helper.py",
                 *(ROOT / "helper").glob("*.bat"), ROOT / "KaraokeToolGUI.bat"]:
        text = _read(path)
        for word in ("KaraokeToolHulp", "hulp_start", "install_hulp",
                     "roformer_keuze", "install_vorige"):
            for row in text.splitlines():
                if word in row:
                    assert any(mark in row for mark in (
                        "OLD_HOME", "up to v1.0.19", "Its name up to",
                        "v1.0.18", "old name", "del ", "move /y",
                        "LEGACY", "rd /s /q", "--made-with")), \
                        f"{path.name}: {row.strip()}"
    from modules.translations import TRANSLATIONS
    for language in TRANSLATIONS.values():
        assert not [key for key in language if key.startswith("hulp_")]


def test_answers_in_the_old_queue_folder_are_taken_over(tmp_path) -> None:
    """A helper of v1.0.18 finishes a round it held into ``kt_werk``."""
    queue, legacy = _new_and_old(tmp_path)
    job = _job("held", version="1.0.18")
    legacy.publish(job)
    held, _ = legacy.claim("oldpc-cpu", "1.0.18")
    answers: list = []
    ticks: list = []

    def sleep(seconds):
        ticks.append(seconds)
        if len(ticks) == 2:
            legacy.finish(held, {"value": "old"}, "oldpc-cpu", "cpu")

    counts = wq.run_jobs(queue, [_job("held")], "1.0", _handlers([]),
                         answers.append, lambda: len(ticks) > 30, poll_s=1,
                         sleep=sleep, stuck_s=1e9)
    assert [a["result"] for a in answers] == [{"value": "old"}]
    assert counts["local"] == 0, "the round was not done twice"
    assert not legacy.root.exists(), \
        "nobody works there any more: the old folder goes"


def test_mutation_without_the_bridge_a_held_round_is_done_twice(
        tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wq._Legacy, "holds", lambda self, job: False)
    monkeypatch.setattr(wq._Legacy, "answers", lambda self: [])
    queue, legacy = _new_and_old(tmp_path)
    legacy.publish(_job("held", version="1.0.18"))
    legacy.claim("oldpc-cpu", "1.0.18")
    counts = wq.run_jobs(queue, [_job("held")], "1.0", _handlers([]),
                         lambda a: None, lambda: False, poll_s=1,
                         sleep=lambda s: None)
    assert counts["local"] == 1


def test_old_helpers_are_told_to_update(tmp_path) -> None:
    queue, legacy = _new_and_old(tmp_path)
    legacy.status("oldpc-cpu", "waiting", "cpu")          # keeps it there
    wq.run_jobs(queue, [_job("a")], "1.0.20", _handlers([]), lambda a: None,
                lambda: False, poll_s=1, sleep=lambda s: None)
    job, newer = legacy.claim("oldpc-cpu", "1.0.18")
    assert job is None and newer, "a v1.0.18 worker sees a newer version"


# -- who can take a round over -------------------------------------------------------

def test_a_helper_says_what_it_can_and_is_trusted_with_that(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.note_speed("slow", "d", 100)
    queue.note_speed("slow", "c", 100)
    queue.note_speed("fast", "d", 10)
    queue.status("fast", "waiting", "cpu", can=["roformer", "ffmpeg"])
    queue.publish(_job("last", needs=["roformer"]))
    job, _ = wq.Smart(queue, "slow").claim("1.0", lambda job: True)
    assert job is None, "fast never did class c, but says it can: left"
    (status,) = queue.active_workers()
    assert status["can"] == ["ffmpeg", "roformer"] and status["lanes"] == 1


# -- the forecast ----------------------------------------------------------------------

def test_the_forecast_shares_the_rounds_over_the_workers(tmp_path) -> None:
    queue = _queue(tmp_path)
    for n in range(6):
        queue.publish(_job(f"j{n}", version="1.0"))
    queue.note_speed("a", "c", 100)
    queue.note_speed("b", "c", 100)
    queue.status("a", "waiting", "cpu")
    queue.status("b", "working", "cpu", _job("x"), left_s=50.0)
    found = wq.forecast(queue, "1.0")
    # a: 3 rounds = 300; b: 50 + 3 x 100 = 350 -> greedy: a 300, b 350
    assert found == {"seconds": 350.0, "lanes": 2, "rough": False}


def test_mutation_adding_up_the_rounds_would_be_twice_too_long(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    for n in range(6):
        queue.publish(_job(f"j{n}", version="1.0"))
    queue.note_speed("a", "c", 100)
    queue.status("a", "waiting", "cpu")
    queue.status("b", "waiting", "cpu", can=[])
    queue.note_speed("b", "c", 100)
    assert wq.forecast(queue, "1.0")["seconds"] == 300.0
    queue.status("b", "stopped", "cpu")
    assert wq.forecast(queue, "1.0")["seconds"] == 600.0


def test_the_forecast_says_nothing_about_rounds_nobody_is_known_for(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("j", version="1.0", needs=["roformer"]))
    queue.status("a", "waiting", "cpu", can=["ffmpeg"])
    assert wq.forecast(queue, "1.0") == {"seconds": None, "lanes": 1}
    assert wq.forecast(_queue(tmp_path / "empty"), "1.0")["seconds"] is None


def test_the_top_bar_uses_the_forecast_or_shares_its_own_guess(
        monkeypatch) -> None:
    from modules import test_panel

    seen: list = []
    steps = test_panel.Steps(lambda *a: seen.append(a), "1.5.14", 4,
                             plan=["x"] * 4, prior={"x": 100.0},
                             forecast=lambda: {"seconds": 123.0, "lanes": 3})
    assert steps.remaining_s() == 123.0
    steps = test_panel.Steps(lambda *a: seen.append(a), "1.5.14", 4,
                             plan=["x"] * 4, prior={"x": 100.0},
                             forecast=lambda: {"seconds": None, "lanes": 4})
    assert steps.remaining_s() == 100.0, "400 s over four lanes"
    steps = test_panel.Steps(lambda *a: seen.append(a), "1.5.14", 4,
                             plan=["x"] * 4, prior={"x": 100.0})
    assert steps.remaining_s() == 400.0


def test_the_programs_own_round_beats_and_says_what_it_does(
        tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wq, "HEARTBEAT_S", 0.05)
    monkeypatch.setattr(wq, "STATUS_S", 0.05)      # v1.0.28
    queue = _queue(tmp_path)
    queue.note_speed(wq.own_worker(), "c", 100)
    seen: list = []

    def handler(job, queue_, cancelled):
        time.sleep(0.3)
        beat = json.loads((queue.claimed / f"{job['id']}.alive").read_text())
        seen.append((beat["beat"], [s["state"] for s in
                                    queue.active_workers()]))
        return {"seconds": 1.0}

    wq.run_jobs(queue, [_job("a")], "1.0", {"k": handler}, lambda a: None,
                lambda: False, poll_s=1, sleep=lambda s: None,
                can=["ffmpeg"])
    ((count, states),) = seen
    assert count >= 2 and states == ["working"]
    (status,) = queue.active_workers()
    assert status["state"] == "stopped" and status["can"] == ["ffmpeg"]


def test_the_trials_forecast_through_the_queue() -> None:
    for name in ("separation_trial", "block_trial", "jamendo_trial",
                 "musdb_trial"):
        source = _read(ROOT / "modules" / f"{name}.py")
        assert "forecast=work_queue.forecaster(" in source, name
        assert "can=" in source, name


# -- ordinary steps: how long still ------------------------------------------------

def test_a_step_learns_how_long_it_takes(tmp_path, monkeypatch) -> None:
    from modules import step_times

    monkeypatch.setattr(step_times, "_FILE", tmp_path / "step_times.json")
    assert step_times.expected("separate:x", 200.0) is None
    step_times.note("separate:x", 200.0, 100.0)          # 0.5 s per s
    assert step_times.expected("separate:x", 100.0) == pytest.approx(50.0)
    step_times.note("separate:x", 100.0, 100.0)          # 1.0 s per s
    assert step_times.expected("separate:x", 100.0) == pytest.approx(75.0)
    step_times.note("separate:x", 100.0, 0.5)            # a cache hit
    assert step_times.expected("separate:x", 100.0) == pytest.approx(75.0)
    with step_times.timed("separate:x", 100.0):
        left = step_times.current_left()
        assert left == pytest.approx(75.0, abs=1.0)
    assert step_times.current_left() is None


def test_a_bar_says_how_long_is_left() -> None:
    from modules import step_times

    assert step_times.left_from_progress(25, 100, 60) == pytest.approx(180)
    assert step_times.left_from_progress(1, 100, 60) is None, "too early"
    assert step_times.left_from_progress(0, 0, 60) is None


def test_the_window_shows_the_time_left() -> None:
    source = _read(ROOT / "modules" / "gui.py")
    assert source.count('t("progress_left")') == 2
    assert "step_times.current_left()" in source
    assert "step_times.left_from_progress(" in source
    separation = _read(ROOT / "modules" / "separation.py")
    assert 'step_times.timed(f"separate:{way.tag}"' in separation


# -- ordinary work on a helper that is sooner done ------------------------------------

def _fake_split(monkeypatch):
    from modules import separation

    def split(audio_path, work_dir, way):
        work_dir.mkdir(parents=True, exist_ok=True)
        out = {}
        for name in ("vocals", "instrumental"):
            path = work_dir / f"{name}.wav"
            path.write_bytes(name.encode() + b" of " + audio_path.name.encode())
            out[name] = path
        return out

    monkeypatch.setattr(separation, "separate_way", split)
    return separation


def test_a_separation_stays_here_without_a_faster_helper(
        tmp_path, monkeypatch) -> None:
    from modules import shared_work

    separation = _fake_split(monkeypatch)
    queue = _queue(tmp_path)
    monkeypatch.setattr(shared_work, "_QUEUE_ROOT", queue.root)
    source = tmp_path / "original.wav"
    source.write_bytes(b"wav")
    stems = shared_work.separate(source, tmp_path / "work", separation.Way())
    assert stems["vocals"].read_bytes() == b"vocals of original.wav"
    speeds = queue.read_speeds()[wq.own_worker()]
    assert "split:htdemucs" in speeds, "its time is noted for next time"
    assert not list(queue.jobs.glob("*.json"))


def test_a_separation_goes_to_a_helper_that_is_sooner_done(
        tmp_path, monkeypatch) -> None:
    from modules import shared_work

    separation = _fake_split(monkeypatch)
    queue = _queue(tmp_path)
    monkeypatch.setattr(shared_work, "_QUEUE_ROOT", queue.root)
    monkeypatch.setattr(shared_work, "local_capabilities",
                        lambda: {"demucs"})
    queue.note_speed(wq.own_worker(), "split:htdemucs", 100)
    queue.note_speed("pc-cpu", "split:htdemucs", 10)
    queue.status("pc-cpu", "waiting", "cpu", can=["demucs"])
    stop = threading.Event()
    helper = threading.Thread(target=wq.work, args=(
        queue, "pc-cpu", "cpu", __version__,
        {shared_work.JOB_KIND: shared_work.run_round}, stop.is_set),
        kwargs={"idle_s": 1, "can": ["demucs"]}, daemon=True)
    helper.start()
    source = tmp_path / "original.wav"
    source.write_bytes(b"wav")
    try:
        stems = shared_work.separate(source, tmp_path / "work",
                                     separation.Way())
    finally:
        stop.set()
        helper.join(timeout=10)
    assert stems["vocals"].read_bytes() == b"vocals of mix.wav", \
        "made by the helper, from the copy on the share"
    assert stems["vocals"].parent == tmp_path / "work"
    assert not (queue.files / "split").exists() or \
        not any((queue.files / "split").iterdir())


def test_mutation_a_slower_helper_gets_nothing(tmp_path, monkeypatch) -> None:
    from modules import shared_work

    queue = _queue(tmp_path)
    job = {"needs": ["demucs"], "class": "split:htdemucs"}
    queue.note_speed(wq.own_worker(), "split:htdemucs", 100)
    queue.note_speed("pc-cpu", "split:htdemucs", 90)
    queue.status("pc-cpu", "waiting", "cpu", can=["demucs"])
    assert not shared_work.worth_sharing(queue, job)
    queue.note_speed("pc-cpu", "split:htdemucs", 1)     # mean now 45.5
    assert shared_work.worth_sharing(queue, job)
    queue.status("pc-cpu", "waiting", "cpu", can=["roformer"])
    assert not shared_work.worth_sharing(queue, job), "cannot do Demucs"


def test_work_inside_a_round_is_not_shared_again(tmp_path,
                                                 monkeypatch) -> None:
    from modules import shared_work

    separation = _fake_split(monkeypatch)
    queue = _queue(tmp_path)
    monkeypatch.setattr(shared_work, "_QUEUE_ROOT", queue.root)
    monkeypatch.setattr(shared_work, "worth_sharing",
                        lambda queue, job: pytest.fail("asked inside a run"))
    source = tmp_path / "original.wav"
    source.write_bytes(b"wav")
    monkeypatch.setattr(wq, "_RUNNING", 1)
    stems = shared_work.separate(source, tmp_path / "work", separation.Way())
    assert stems["vocals"].exists()


def test_the_program_knows_its_queue_and_its_card_at_the_start() -> None:
    source = _read(ROOT / "KaraokeTool.py")
    assert "shared_work.use_queue(work_queue.queue_for(context).root)" in \
        source
    assert '_cuda.use_card_file(paths.config_dir / "cuda.json")' in source
    assert '_step_times.use_file(paths.config_dir / "step_times.json")' in \
        source
    from modules import queue_jobs, shared_work
    assert queue_jobs.handlers()[shared_work.JOB_KIND] is \
        shared_work.run_round


# -- the NVIDIA card in the program ------------------------------------------------------

def test_the_card_is_used_only_for_what_worked(tmp_path, monkeypatch) -> None:
    from modules import cuda

    monkeypatch.setattr(cuda, "add_cuda_libraries", lambda: None)
    card = tmp_path / "cuda.json"
    assert cuda.use_card_file(card) is None
    assert cuda.whisper_device() == ("cpu", "int8")
    card.write_text(json.dumps({"gpu_ok": True, "torch": False,
                                "device": "cuda", "compute": "int8_float16"}))
    assert cuda.use_card_file(card)["device"] == "cuda"
    assert cuda.whisper_device() == ("cuda", "int8_float16")
    assert not cuda.torch_on_card()
    assert cuda.processor_only_env({})["CUDA_VISIBLE_DEVICES"] == "-1"
    card.write_text(json.dumps({"gpu_ok": True, "torch": True,
                                "device": "cpu", "compute": "int8"}))
    cuda.use_card_file(card)
    assert cuda.torch_on_card() and "CUDA_VISIBLE_DEVICES" not in \
        cuda.processor_only_env({})
    assert cuda.whisper_device() == ("cpu", "int8")
    monkeypatch.setattr(cuda, "_CARD", None)
    monkeypatch.setattr(cuda, "_READ", False)
    assert "CUDA_VISIBLE_DEVICES" not in cuda.processor_only_env({}), \
        "a helper decides about its card itself"


def test_whisper_goes_to_the_processor_when_the_card_fails(
        tmp_path, monkeypatch) -> None:
    from modules import cuda, whisper
    from modules.config import WhisperSettings

    monkeypatch.setattr(cuda, "_CARD", {"gpu_ok": True, "device": "cuda",
                                        "compute": "float16"})
    monkeypatch.setattr(whisper, "_CUDA_FAILED", False)
    used: list = []

    class Model:
        def __init__(self, device):
            self.device = device

        def transcribe(self, audio, **options):
            used.append(self.device)
            if self.device == "cuda":
                raise RuntimeError("Library cublas64_12.dll is not found")
            return iter(()), None

    monkeypatch.setattr(whisper, "_load_model", lambda settings: Model(
        whisper._resolve_device(settings)[0]))
    settings = WhisperSettings()
    assert whisper._resolve_device(settings) == ("cuda", "float16")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    assert whisper.transcribe_slice(audio, settings) == ()
    assert used == ["cuda", "cpu"]
    assert whisper._resolve_device(settings)[0] == "cpu", "for the session"


def test_mutation_an_ordinary_error_is_not_blamed_on_the_card(
        monkeypatch) -> None:
    from modules import cuda, whisper
    from modules.config import WhisperSettings

    monkeypatch.setattr(cuda, "_CARD", {"gpu_ok": True, "device": "cuda",
                                        "compute": "float16"})
    monkeypatch.setattr(whisper, "_CUDA_FAILED", False)
    assert not whisper._on_card_trouble(ValueError("bad audio"),
                                        WhisperSettings())
    assert whisper._resolve_device(WhisperSettings())[0] == "cuda"


def test_the_separations_stay_off_a_card_that_failed() -> None:
    source = _read(ROOT / "modules" / "separation.py")
    assert source.count("env=cuda.processor_only_env()") == 2


def test_the_card_test_writes_what_it_found(tmp_path, monkeypatch) -> None:
    from modules import cuda

    monkeypatch.setattr(cuda, "probe", lambda whisper_too=True: {
        "gpu_ok": True, "torch": True, "card": "GTX", "device": "cuda",
        "compute": "int8_float16"})
    assert cuda.main(["--write", str(tmp_path / "c.json")]) == 0
    assert json.loads((tmp_path / "c.json").read_text())["card"] == "GTX"
    assert cuda.main(["--none", str(tmp_path / "n.json")]) == 0
    assert json.loads((tmp_path / "n.json").read_text())["gpu_ok"] is False


# -- the launcher: Python 3.13, the card, 3.12 away ---------------------------------------

def test_python_313_is_looked_for_first() -> None:
    finder = _read(ROOT / "tools" / "find_python.bat")
    # v1.0.22: and only 3.13 - the fallback on 3.12 went.
    assert "call :try 3.13" in finder
    assert "3.12)" not in finder and "call :try 3.12" not in finder
    assert "winget install -e --id Python.Python.3.13 --scope user" in finder
    assert '/i "%~1"=="auto" goto :install' in finder


def test_the_launcher_makes_environments_of_another_python_anew() -> None:
    launcher = _read(ROOT / "KaraokeToolGUI.bat")
    check = launcher[:launcher.index("\n:setup")]
    assert "call tools\\find_python.bat none" in check
    assert 'setup_check.py --same-python "%VENV%"' in check
    assert "PYCHOICE" not in launcher, "v1.0.22: no choice for 3.12"
    assert "%CUDAFLAG%" in check
    # What v1.0.20 kept about 3.12 goes.
    assert "python_choice.txt python312_keep.txt" in check
    setup = launcher[launcher.index("\n:setup"):]
    assert "call tools\\find_python.bat ask" in setup
    assert 'call :set_aside "%VENV%" || goto :error' in setup
    assert '--set-aside "%~1" "%~dp0..\\_to_delete"' in setup
    assert ":remove_312" not in launcher
    assert "Python.Python.3.12" not in launcher


def test_the_launcher_installs_for_the_card_and_tests_it() -> None:
    launcher = _read(ROOT / "KaraokeToolGUI.bat")
    assert "--extra-index-url https://download.pytorch.org/whl/cu126" in \
        launcher
    assert launcher.index("pip install whisperx %TORCHIDX%") < \
        launcher.index('pip install -U "demucs>=4.1" %TORCHIDX%'), \
        "WhisperX pins PyTorch first"
    assert 'nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"' in launcher
    assert '-m modules.cuda --write "%CONFIGDIR%\\cuda.json"' in launcher
    assert '-m modules.cuda --none "%CONFIGDIR%\\cuda.json"' in launcher
    assert 'set "SEPKIND=gpu"' in launcher


def test_the_setup_notes_python_and_card(tmp_path) -> None:
    check = _load("setup_check_v1020", "tools/setup_check.py")
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = C:\\x\nversion = 3.12.10\n")
    assert check.venv_python(venv) == "3.12"
    assert check.main([str(venv), "J", "--write"]) == 0
    assert check.main([str(venv), "J"]) == 0
    assert check.main([str(venv), "J", "--cuda"]) == 1, "a card came"
    (venv / "pyvenv.cfg").write_text("version = 3.13.7\n")
    assert check.main([str(venv), "J"]) == 1, "another Python"
    same = check.main(["--same-python", str(venv)])
    assert same == (0 if check.running_python() == "3.13" else 1)


def test_an_environment_is_set_aside_not_lost(tmp_path) -> None:
    check = _load("setup_check_v1020b", "tools/setup_check.py")
    venv = tmp_path / "app" / "venv"
    venv.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("version = 3.12.10\n")
    trash = tmp_path / "_to_delete"
    blocker = tmp_path / "a_file"
    blocker.write_text("x")
    target = check.set_aside(venv, [blocker / "cannot", trash])
    assert target is not None and target.parent == trash
    assert target.name.startswith("venv_py312_") and not venv.exists()
    assert (target / "pyvenv.cfg").exists()


def test_the_choice_about_roformer_has_an_english_name() -> None:
    launcher = _read(ROOT / "KaraokeToolGUI.bat")
    assert 'set "CHOICE=%CONFIGDIR%\\roformer_choice.txt"' in launcher
    assert 'move /y "%CONFIGDIR%\\roformer_keuze.txt" "%CHOICE%"' in launcher
    assert "install_previous.log" in launcher


# -- where the time of a helper goes ------------------------------------------------------

def test_the_report_says_how_much_of_a_round_is_separating() -> None:
    from modules import separation_trial as st

    rows = {"song": {"a": {"worker": "Pav-gpu", "seconds": 600.0,
                           "separate_s": 450.0, "whisper_device": "cuda"},
                     "b": {"worker": "Pav-gpu", "seconds": 600.0,
                           "separate_s": 150.0, "whisper_device": "cuda"},
                     "c": {"worker": "old", "seconds": 60.0}}}
    found = st._by_worker(rows)
    assert found["Pav-gpu"] == (2, 1200.0, 0.5, "cuda")
    assert found["old"] == (1, 60.0, -1.0, "-")
    source = _read(ROOT / "modules" / "separation_trial.py")
    assert '"separate_s": separated' in source


def test_the_requirements_run_on_313() -> None:
    text = _read(ROOT / "requirements.txt")
    assert text.startswith("# KaraokeTool - Python 3.13")
    assert "librosa>=0.10,<1" in text
    assert os.path.exists(ROOT / "tools" / "find_python.bat")


# -- what the review before delivery found ------------------------------------------

def test_a_newer_job_alone_does_not_restart_a_helper_that_knows_its_share(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("new", version="9.9"))
    outcome = wq.work(queue, "pc-cpu", "cpu", "1.0", {}, lambda: False,
                      idle_s=0, sleep=lambda s: None, once=True,
                      update_check=lambda: False)
    assert outcome == "stopped", "no newer installer: it waits"
    outcome = wq.work(queue, "pc-cpu", "cpu", "1.0", {}, lambda: False,
                      idle_s=0, sleep=lambda s: None, once=True)
    assert outcome == "update", "without a share the job is the sign"


def test_the_program_is_on_standby_when_its_helper_works_here(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    assert wq._own_idle(queue) == "waiting"
    queue.status("here-cpu", "working", "cpu")
    assert wq._own_idle(queue) == "standby"


def test_old_helpers_hear_of_the_new_version_at_the_start(tmp_path) -> None:
    queue = wq.Queue(wq.queue_folder(tmp_path / "Tools" / "KaraokeTool"))
    old = tmp_path / "Tools" / wq.QUEUE_NAME
    wq.announce(queue, "1.0.20")                  # no old folder: nothing
    assert not old.exists()
    legacy = wq.Queue(old).ensure()
    wq.announce(queue, "1.0.20")
    assert legacy.claim("oldpc-cpu", "1.0.18") == (None, True)
    source = _read(ROOT / "KaraokeTool.py")
    assert "work_queue.announce(" in source


def test_the_listening_copies_of_an_old_answer_come_along(tmp_path) -> None:
    queue, legacy = _new_and_old(tmp_path)
    job = _job("held", version="1.0.18")
    legacy.publish(job)
    held, _ = legacy.claim("oldpc-cpu", "1.0.18")
    legacy.out_dir(job["id"]).mkdir(parents=True)
    (legacy.out_dir(job["id"]) / "music.mp3").write_bytes(b"mp3")
    legacy.finish(held, {"value": 1}, "oldpc-cpu", "cpu")
    moved: list = []

    def on_answer(answer):
        moved.append((queue.out_dir(answer["job"]["id"]) /
                      "music.mp3").exists())

    wq.run_jobs(queue, [_job("held")], "1.0", _handlers([]), on_answer,
                lambda: False, poll_s=1, sleep=lambda s: None)
    assert moved == [True]


def test_an_answer_of_an_earlier_stopped_separation_is_not_taken(
        tmp_path, monkeypatch) -> None:
    from modules import shared_work

    separation = _fake_split(monkeypatch)
    queue = _queue(tmp_path)
    monkeypatch.setattr(shared_work, "_QUEUE_ROOT", queue.root)
    monkeypatch.setattr(shared_work, "worth_sharing", lambda q, job: True)
    monkeypatch.setattr(shared_work, "local_capabilities",
                        lambda: {"demucs"})
    stale = {"id": "stale", "kind": shared_work.JOB_KIND, "version": "x"}
    queue.out_dir("stale").mkdir(parents=True)
    (queue.out_dir("stale") / "vocals.wav").write_bytes(b"other song")
    (queue.done / "stale.json").write_text(json.dumps(
        {"job": stale, "result": {"stems": {"vocals": "vocals.wav",
                                            "instrumental": "vocals.wav"}},
         "worker": "pc-cpu"}))
    source = tmp_path / "original.wav"
    source.write_bytes(b"wav")
    stems = shared_work.separate(source, tmp_path / "work", separation.Way())
    assert stems["vocals"].read_bytes() == b"vocals of original.wav"
    assert not queue.out_dir("stale").exists()


def test_whisper_on_the_processor_takes_a_processor_type(monkeypatch) -> None:
    from modules import cuda, whisper
    from modules.config import WhisperSettings

    monkeypatch.setattr(cuda, "_CARD", None)
    monkeypatch.setattr(whisper, "_CUDA_FAILED", True)
    card_lane = WhisperSettings(device="cuda", compute_type="float16")
    assert whisper._resolve_device(card_lane) == ("cpu", "int8")
    kept = WhisperSettings(device="cuda", compute_type="float32")
    assert whisper._resolve_device(kept) == ("cpu", "float32")


def test_a_separation_that_fails_on_the_card_runs_on_the_processor(
        monkeypatch) -> None:
    import subprocess

    from modules import cuda, proc, separation

    monkeypatch.setattr(cuda, "_CARD", {"gpu_ok": True, "torch": True})
    monkeypatch.setattr(cuda, "_READ", True)
    runs: list = []

    def run(command, check=True, env=None):
        runs.append(env.get("CUDA_VISIBLE_DEVICES"))
        if len(runs) == 1:
            raise subprocess.CalledProcessError(
                1, command, "", "RuntimeError: CUDA out of memory")

    monkeypatch.setattr(proc, "run", run)
    separation._run_separation(["demucs"])
    assert runs == [None, "-1"] and not cuda.torch_on_card()


def test_mutation_an_ordinary_failure_is_not_run_twice(monkeypatch) -> None:
    import subprocess

    from modules import cuda, proc, separation

    monkeypatch.setattr(cuda, "_CARD", {"gpu_ok": True, "torch": True})
    runs: list = []

    def run(command, check=True, env=None):
        runs.append(1)
        raise subprocess.CalledProcessError(1, command, "", "no such file")

    monkeypatch.setattr(proc, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        separation._run_separation(["demucs"])
    assert runs == [1]


def test_the_clean_up_of_python_312_is_gone(tmp_path) -> None:
    """v1.0.22: 3.12 is uninstalled everywhere; the guard that kept it
    for a helper on it, and the helper's old home, went with it."""
    check = _load("setup_check_v1020c", "tools/setup_check.py")
    assert "--made-with" not in _read(ROOT / "tools" / "setup_check.py")
    assert check.main(["--python-of", str(tmp_path)]) == 0
    install = _read(ROOT / "helper" / "install_helper.bat")
    assert '"%OLD_HOME%\\app\\models"' not in install
    assert "OLDPY=<\"%HOME_DIR%\\logs\\python_of_env.txt\"" in install, \
        "an environment of another Python still says which it was"
