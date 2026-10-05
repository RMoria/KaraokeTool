"""v1.0.24: a small card that does a round on the card or on the processor,
and the helper without a console, able to take itself off a computer.

* a card under 6 GB gets one lane that takes a round on the card when it
  goes faster there (a separation) and otherwise on the processor, never
  two at once, and no temperature rules of the program's own on top of
  the card's own slowing down (B646);
* the shortcut starts the helper's window at once, without a console; the
  finding of the laptop and the updating happen in it (B653);
* the Roformer environment keeps the processor's onnxruntime, and the
  trial separation says nothing of its short tone (B654);
* "Helper verwijderen" takes the helper and what it fetched off the
  computer (B655);
* the card profile of 1.5.18 is not stopped by the lane's heat guard,
  measures the smaller Whisper too and says why a task ended (B656).
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from modules import work_queue as wq

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _helper():
    return _load("helper_v1024", "tools/helper.py")


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


@pytest.fixture
def helper(tmp_path, monkeypatch):
    module = _helper()
    home = tmp_path / "KaraokeToolHelper"
    (home / "logs").mkdir(parents=True)
    monkeypatch.setattr(module, "HOME", home)
    monkeypatch.setattr(module, "_SINK", None)
    return module


# -- B646: the card or the processor -----------------------------------------------------

def test_a_small_card_does_a_round_on_the_card_or_the_processor() -> None:
    helper = _helper()
    assert helper.choose_lanes("auto", True, big_enough=False) == ["mixed"]
    assert helper.choose_lanes("auto", True, big_enough=True) == \
        ["gpu", "cpu"]
    assert helper.choose_lanes("auto", False, big_enough=False) == ["cpu"]
    for word in ("gpu-or-cpu", "gpu|cpu", "mixed"):
        assert helper.choose_lanes(word, True, big_enough=False) == \
            ["mixed"], word
    assert helper.choose_lanes("gpu-or-cpu,cpu", True) == ["mixed"], \
        "never a processor lane beside it"
    assert helper.choose_lanes("gpu-or-cpu", False) == ["cpu"]


def test_lanes_txt_may_say_gpu_or_cpu(tmp_path) -> None:
    helper = _helper()
    (tmp_path / helper.LANES_FILE).write_text("gpu-or-cpu\n")
    assert helper.lanes_wanted("auto", home=tmp_path) == "gpu-or-cpu"


def test_a_separation_goes_on_the_card_the_rest_on_the_processor() -> None:
    helper = _helper()
    assert helper.card_round({"needs": ["ffmpeg", "roformer"]})
    assert helper.card_round({"needs": ["ffmpeg", "demucs"]})
    assert not helper.card_round({"needs": ["ffmpeg", "processor"]})
    assert not helper.card_round({"needs": ["ffmpeg", "whisperx"]})
    assert not helper.card_round({"needs": []})


def test_the_mixed_lane_switches_the_card_per_round(monkeypatch) -> None:
    helper = _helper()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    seen = []

    def handler(job, queue, stop):
        seen.append((os.environ.get("CUDA_VISIBLE_DEVICES"),
                     os.environ.get("KT_WHISPER_DEVICE")))
        return {"ok": True}

    card = {"CUDA_VISIBLE_DEVICES": None, "KT_WHISPER_DEVICE": "cuda"}
    cpu = {"CUDA_VISIBLE_DEVICES": "-1", "KT_WHISPER_DEVICE": "cpu"}
    said = []
    wrapped = helper.mixed_handlers({"k": handler}, card, cpu,
                                    lambda key, v: said.append(key))
    wrapped["k"]({"needs": ["demucs"], "class": "sep"}, None, lambda: False)
    wrapped["k"]({"needs": ["processor"], "class": "rnd"}, None,
                 lambda: False)
    assert seen == [(None, "cuda"), ("-1", "cpu")]
    assert said == ["helper_on_card", "helper_on_processor"]


def test_a_round_the_card_cannot_take_runs_on_the_processor(
        monkeypatch) -> None:
    helper = _helper()
    tries = []

    def handler(job, queue, stop):
        tries.append(os.environ.get("KT_WHISPER_DEVICE"))
        if os.environ.get("KT_WHISPER_DEVICE") == "cuda":
            return {"failed": "RuntimeError: CUDA out of memory"}
        return {"ok": True}

    wrapped = helper.mixed_handlers(
        {"k": handler}, {"KT_WHISPER_DEVICE": "cuda"},
        {"KT_WHISPER_DEVICE": "cpu"})
    job = {"needs": ["roformer"], "class": "sep:roformer"}
    assert wrapped["k"](job, None, lambda: False) == {"ok": True}
    assert tries == ["cuda", "cpu"]
    wrapped["k"](job, None, lambda: False)
    assert tries[-1] == "cpu" and len(tries) == 3, \
        "that kind of round goes to the processor from then on"


def test_mutation_an_ordinary_failure_is_not_tried_again() -> None:
    helper = _helper()
    tries = []

    def handler(job, queue, stop):
        tries.append(1)
        return {"failed": "ValueError: no lyrics"}

    wrapped = helper.mixed_handlers({"k": handler}, {}, {})
    assert "failed" in wrapped["k"]({"needs": ["demucs"], "class": "x"},
                                    None, lambda: False)
    assert tries == [1]


def test_the_mixed_lane_has_no_temperature_rules_of_its_own() -> None:
    source = _read(ROOT / "tools" / "helper.py")
    assert "heat_guard.HeatGuard() if heat_guard.present() and \\\n" \
        "        lane != MIXED else None" in source
    assert 'have.add("processor")' in source
    assert 'env["KT_WHISPER_COMPUTE"] = SMALL_CARD_COMPUTE' in source
    helper = _helper()
    assert helper.SMALL_CARD_COMPUTE == "int8_float16"


# -- B656: the card profile -----------------------------------------------------------------

class _Hot:
    WATCH_S = 0.01

    def __init__(self):
        self.aborts = 0

    def must_wait(self):
        return None

    def watch(self):
        return True

    def aborted(self):
        self.aborts += 1


def test_the_check_is_not_stopped_by_the_lanes_heat_guard(tmp_path) -> None:
    import time

    from modules import diagnose

    queue = wq.Queue(tmp_path / "kt_work").ensure()
    job = diagnose.check_job(wq.host_name(), "1.0")
    assert job["own_heat"] is True
    job["for"] = None
    queue.publish(job)
    heat = _Hot()

    def slow(job, queue_, stop):
        time.sleep(0.2)
        return {"report": "done", "stopped": stop()}

    outcome = wq.work(queue, "pc-cpu", "cpu", "1.0",
                      {diagnose.JOB_KIND: slow},
                      lambda: len(queue.answers()) >= 1, idle_s=0,
                      sleep=lambda s: None, heat=heat)
    assert outcome == "stopped"
    (answer,) = queue.answers()
    assert answer["result"]["stopped"] is False and heat.aborts == 0


def test_a_task_says_why_it_ended() -> None:
    from modules import diagnose
    from modules.translations import t

    assert diagnose.task_outcome({"code": 0}) == t("check_ok")
    assert diagnose.task_outcome({"code": -1, "timeout": True}) == \
        t("check_profile_timeout")
    pav = ("RuntimeError: CUDA error: out of memory\n"
           "Please follow https://onnxruntime.ai/docs/install/ to install "
           "CUDA.")
    assert diagnose.task_outcome({"code": 1, "text": pav}).startswith(
        "RuntimeError"), "the error, not the warning after it"


def test_the_profile_measures_the_smaller_whisper_too(tmp_path) -> None:
    from modules import diagnose

    tasks = dict(diagnose.card_tasks("py", tmp_path, tmp_path / "s.wav",
                                     tmp_path))
    assert tasks["whisper"][-1] == "float16"
    assert tasks["whisper_int8"][-1] == "int8_float16"
    source = _read(ROOT / "modules" / "diagnose.py")
    assert "PROFILE_STOP" not in source, "no temperature rules of its own"


# -- B653: no console ---------------------------------------------------------------------

class _Window(dict):
    def __init__(self):
        super().__init__(ended=self._end, lines=None)
        self.over = False

    def _end(self):
        self.over = True


def test_the_start_looks_for_the_laptop_in_the_window(helper, tmp_path,
                                                      monkeypatch) -> None:
    said = []
    monkeypatch.setattr(helper, "_tell", said.append)
    share = tmp_path / "Tools" / "KaraokeTool"
    share.mkdir(parents=True)
    found = iter([None, str(share)])
    served = []

    def serve(share_, queue_dir, requested, window):
        served.append(queue_dir)
        return helper.OWNER_EXIT

    code = helper.session("auto", _Window(), find=lambda stored: next(found),
                          serve_=serve, sleep=lambda s: None)
    assert code == helper.OWNER_EXIT
    from modules.translations import t
    assert said[0] == t("helper_start_no_laptop")
    assert t("helper_start_found").format(share=share) in said
    assert served == [wq.queue_folder(str(share))]


def test_the_start_fetches_a_newer_version(helper, tmp_path,
                                           monkeypatch) -> None:
    monkeypatch.setattr(helper, "_tell", lambda text: None)
    share = tmp_path / "Tools" / "KaraokeTool"
    (share / "helper").mkdir(parents=True)
    (share / "helper" / "install_helper.bat").write_text(
        'set "HELPER_VERSION=9.9.9"\r\n')
    (helper.HOME / helper.INSTALLED_FILE).write_text("1.0.24\n")
    started = []
    code = helper.session("auto", _Window(), find=lambda s: str(share),
                          serve_=lambda *a: pytest.fail("no lanes"),
                          update=lambda s: started.append(s) or True,
                          sleep=lambda s: None)
    assert code == wq.UPDATE_EXIT and started == [str(share)]


def test_after_the_lanes_update_the_start_goes_round_again(
        helper, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(helper, "_tell", lambda text: None)
    share = tmp_path / "share" / "KaraokeTool"
    share.mkdir(parents=True)
    codes = iter([wq.UPDATE_EXIT, 0])
    window = _Window()
    code = helper.session("auto", window, find=lambda s: str(share),
                          serve_=lambda *a: next(codes),
                          sleep=lambda s: None)
    assert code == 0 and window.over, "stopped by itself: the window stays"


def test_the_owner_can_stop_while_it_looks_for_the_laptop(
        helper, monkeypatch) -> None:
    monkeypatch.setattr(helper, "_tell", lambda text: None)
    looks = []

    def find(stored):
        looks.append(1)
        helper.set_flag(helper.STOP_FLAG, True)
        return None

    assert helper.session("auto", _Window(), find=find,
                          sleep=lambda s: None) == helper.OWNER_EXIT
    assert looks == [1] and not (helper.HOME / helper.STOP_FLAG).exists()


def test_while_it_is_being_updated_it_waits(helper, monkeypatch) -> None:
    said = []
    monkeypatch.setattr(helper, "_tell", said.append)
    (helper.HOME / "installing.lock").write_text("now")
    assert helper.session("auto", _Window(),
                          find=lambda s: pytest.fail("not now"),
                          sleep=lambda s: None) == 0
    assert said


def test_the_shortcut_starts_the_window_without_a_console() -> None:
    install = _read(ROOT / "helper" / "install_helper.bat")
    assert "$s.TargetPath='%PYW%'" in install
    assert "$s.Arguments='\\\"%APP%\\tools\\helper.py\\\" --start'" in \
        install
    assert 'set "PYW=%APP%\\venv\\Scripts\\pythonw.exe"' in install
    assert "helper_start.bat" in install, "the way in by hand stays"
    assert (ROOT / "helper" / "helper_start.bat").exists()


def test_the_window_takes_its_lanes_when_they_start(qapp) -> None:
    import queue as queue_module

    from modules import helper_window

    lanes: list = []
    over = {"ended": False}
    window = helper_window.HelperWindow(
        "t", lambda: lanes, lambda lane: {"state": "waiting"},
        queue_module.Queue(), lambda on: None, lambda: None,
        lambda: False, remove=lambda: None, ended=lambda: over["ended"])
    assert window._table.rowCount() == 0
    lanes.append("mixed")
    window._lanes_changed()
    assert window._table.rowCount() == 1
    assert window._remove_button.isVisibleTo(window)
    over["ended"] = True
    window._tick()
    assert not window._stop_button.isEnabled()
    window.close()


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# -- B654: onnxruntime and the short tone -------------------------------------------------

def test_the_roformer_environment_keeps_the_processors_onnxruntime() -> None:
    install = _read(ROOT / "helper" / "install_helper.bat")
    assert 'set "SEPKIND=gpu"' not in install
    assert "pip uninstall -y onnxruntime-gpu" in install
    assert "--force-reinstall --no-deps onnxruntime" in install


def test_the_trial_says_nothing_of_its_short_tone(monkeypatch) -> None:
    import logging

    monkeypatch.setattr(logging.Filterer, "filter", logging.Filterer.filter)
    tool = _load("roformer_v1024", "tools/roformer_separate.py")
    tool._quiet_about_short_audio()
    kept = []

    class Keep(logging.Handler):
        def emit(self, record):
            kept.append(record.getMessage())

    log = logging.getLogger("mdxc_separator_test")
    log.addHandler(Keep())
    log.warning("Audio duration (3.00s) is less than 10 seconds.")
    log.warning("Automatically enabling override_model_segment_size.")
    log.warning("something else")
    assert kept == ["something else"]


# -- B655: taking the helper off ----------------------------------------------------------

def test_what_the_helper_installed_itself(tmp_path) -> None:
    helper = _helper()
    assert helper.installed_by_helper(tmp_path) == {"ffmpeg", "python"}, \
        "no note: both (the owner)"
    note = tmp_path / helper.INSTALLED_BY_FILE
    note.write_text("unknown\n")
    assert helper.installed_by_helper(tmp_path) == {"ffmpeg", "python"}
    note.write_text("ffmpeg\n")
    assert helper.installed_by_helper(tmp_path) == {"ffmpeg"}
    note.write_text("")
    assert helper.installed_by_helper(tmp_path) == set()


def test_on_the_laptop_what_the_program_needs_stays() -> None:
    helper = _helper()
    assert helper.program_here(r"\\laptop1\Tools\KaraokeTool",
                               host="Laptop1", addresses=[])
    assert helper.program_here(r"\\10.0.0.18\Tools\KaraokeTool",
                               host="Pav", addresses=["10.0.0.18"])
    assert not helper.program_here(r"\\10.0.0.18\Tools\KaraokeTool",
                                   host="Pav", addresses=["10.0.0.7"])
    assert helper.program_here(r"C:/Muziek/KaraokeTool", host="x",
                               addresses=[])


def _plan_world(helper, tmp_path, monkeypatch, here: bool):
    local = tmp_path / "Local"
    (local / "KaraokeToolHulp").mkdir(parents=True)
    temp = tmp_path / "Temp" / "KaraokeToolHelper"
    temp.mkdir(parents=True)
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    (desktop / "KaraokeTool helper.lnk").write_text("x")
    model = tmp_path / "hub" / "models--Systran--faster-whisper-large-v3"
    model.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    from modules import local_copy
    monkeypatch.setattr(local_copy, "base", lambda: temp)
    monkeypatch.setattr(helper, "_desktop", lambda: desktop)
    monkeypatch.setattr(helper, "_model_caches", lambda: [model])
    monkeypatch.setattr(helper, "program_here", lambda share: here)
    return local, temp, desktop, model


def test_the_removal_takes_everything_of_the_helper(helper, tmp_path,
                                                    monkeypatch) -> None:
    local, temp, desktop, model = _plan_world(helper, tmp_path, monkeypatch,
                                              here=False)
    share = tmp_path / "Tools" / "KaraokeTool"
    workers = wq.Queue(wq.queue_folder(str(share))).ensure().workers
    mine = workers / f"{wq._safe(wq.host_name() + '-cpu')}.json"
    mine.write_text("{}")
    speeds = wq.queue_folder(str(share)) / "speeds.json"
    speeds.write_text("{}")
    monkeypatch.setattr(helper, "_tell", lambda text: None)
    script = helper.remove_helper(str(share), pid=4242, start=False)
    assert not (local / "KaraokeToolHulp").exists() and not temp.exists()
    assert not (desktop / "KaraokeTool helper.lnk").exists()
    assert not model.exists(), "the downloaded models go"
    assert not mine.exists() and speeds.exists(), "its speeds stay"
    text = script.read_bytes().decode("cp1252")
    assert '"PID eq 4242"' in text
    assert "winget uninstall -e --id Gyan.FFmpeg" in text
    assert "winget uninstall -e --id Python.Python.3.13" in text
    assert f'rd /s /q "{helper.HOME}"' in text
    assert text.count("\n") == text.count("\r\n")
    assert text.index("PID eq 4242") < text.index("rd /s /q"), \
        "the folder only after the helper stopped"


def test_on_the_laptop_python_ffmpeg_and_the_models_stay(
        helper, tmp_path, monkeypatch) -> None:
    _local, _temp, _desktop, model = _plan_world(helper, tmp_path,
                                                 monkeypatch, here=True)
    monkeypatch.setattr(helper, "_tell", lambda text: None)
    script = helper.remove_helper("", pid=1, start=False)
    assert model.exists()
    assert "winget uninstall" not in script.read_text(encoding="cp1252")


def test_a_running_helper_is_asked_to_remove_itself(helper,
                                                    monkeypatch) -> None:
    (helper.HOME / helper.PID_FILE).write_text("777")
    monkeypatch.setattr(helper, "_alive", lambda pid: pid == 777)
    monkeypatch.setattr(helper, "remove_helper",
                        lambda *a, **k: pytest.fail("the running one does"))
    assert helper.remove_command() == 0
    assert (helper.HOME / helper.REMOVE_FLAG).exists()
    assert (helper.HOME / helper.STOP_FLAG).exists()


def test_the_window_s_remove_is_done_when_the_lanes_have_stopped(
        helper, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(helper, "_tell", lambda text: None)
    share = tmp_path / "Tools" / "KaraokeTool"
    share.mkdir(parents=True)
    removed = []
    monkeypatch.setattr(helper, "remove_helper",
                        lambda share_, *a, **k: removed.append(share_))

    def serve(*args):
        helper.set_flag(helper.REMOVE_FLAG, True)
        helper.set_flag(helper.STOP_FLAG, True)
        helper.clear_flags()            # what serve does on the owner's stop
        return helper.OWNER_EXIT

    assert helper.session("auto", _Window(), find=lambda s: str(share),
                          serve_=serve, sleep=lambda s: None) == \
        helper.OWNER_EXIT
    assert removed == [str(share)]


def test_the_installer_notes_what_it_installed_and_can_remove() -> None:
    install = _read(ROOT / "helper" / "install_helper.bat")
    assert 'if /i "%~1"=="/remove" goto :remove_helper' in install
    assert install.index('goto :remove_helper') < \
        install.index('mkdir "%HOME_DIR%\\logs"')
    assert "call :record python" in install
    assert "&& call :record ffmpeg" in install
    assert 'echo unknown' in install
    assert '"%APP%\\tools\\helper.py" --remove' in install


def test_the_version_everywhere() -> None:
    from modules import __version__

    for name in ("install_helper.bat", "helper_start.bat"):
        assert f'set "HELPER_VERSION={__version__}"' in _read(
            ROOT / "helper" / name)
