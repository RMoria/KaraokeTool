"""v1.0.21: the helpers' logs on the laptop, and the videos through the
queue.

* every helper puts its logs - the window's messages, its lanes, its
  start file and its installations - in ``KaraokeTool\\logs\\helpers\\
  <computer>`` on the laptop, the ones from before too, and keeps 30
  days of them;
* a video is rendered on a helper when one is sooner done, and 1.5.12
  renders all videos through the queue at once;
* the bridge for the helpers of v1.0.18 is gone: all of them moved.
"""
from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
from pathlib import Path

from modules import __version__
from modules import work_queue as wq

ROOT = Path(__file__).resolve().parents[1]


def _helper():
    spec = importlib.util.spec_from_file_location(
        "helper_v1021", ROOT / "tools" / "helper.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


# -- the logs on the laptop --------------------------------------------------------

def test_the_logs_go_to_the_programs_log_folder_per_computer() -> None:
    helper = _helper()
    share = r"\\10.0.0.18\Tools\KaraokeTool"
    assert helper.central_logs(share) == \
        Path(share) / "logs" / "helpers" / wq.host_name()
    assert helper.KEEP_LOG_DAYS == 30


def test_the_logs_are_mirrored_the_old_ones_too(tmp_path) -> None:
    helper = _helper()
    local = tmp_path / "local"
    central = tmp_path / "share" / "logs" / "helpers" / "PC"
    (local / "helper_cpu").mkdir(parents=True)
    (local / "install_helper.log").write_text("installed")
    (local / "helper_cpu" / "2026-09-01.log").write_text("from before")
    assert helper.mirror_logs(local, central) == 2
    assert (central / "helper_cpu" / "2026-09-01.log").read_text() == \
        "from before", "what was there before the move goes along"
    assert helper.mirror_logs(local, central) == 0, "unchanged: not again"
    time.sleep(0.01)
    (local / "install_helper.log").write_text("installed again, longer")
    assert helper.mirror_logs(local, central) == 1
    assert (central / "install_helper.log").read_text().endswith("longer")


def test_logs_older_than_thirty_days_go_here_and_there(tmp_path) -> None:
    helper = _helper()
    local = tmp_path / "local"
    central = tmp_path / "central"
    local.mkdir()
    old = local / "2026-07-01.log"
    old.write_text("old")
    helper.mirror_logs(local, central)
    stale = time.time() - 31 * 86400
    os.utime(old, (stale, stale))
    os.utime(central / old.name, (stale, stale))
    (central / "someone.log").write_text("fresh")
    helper.mirror_logs(local, central)
    assert not old.exists() and not (central / old.name).exists()
    assert (central / "someone.log").exists()


def test_mutation_keeping_everything_keeps_the_old_log(tmp_path) -> None:
    helper = _helper()
    local = tmp_path / "local"
    local.mkdir()
    old = local / "2026-07-01.log"
    old.write_text("old")
    stale = time.time() - 31 * 86400
    os.utime(old, (stale, stale))
    helper.mirror_logs(local, tmp_path / "central", keep_days=1e6)
    assert old.exists()


def test_a_share_that_is_away_is_no_problem(tmp_path) -> None:
    helper = _helper()
    local = tmp_path / "local"
    local.mkdir()
    (local / "a.log").write_text("x")
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    assert helper.mirror_logs(local, blocker / "logs") == 0
    assert (local / "a.log").exists()


def test_the_command_line_mirrors_too(tmp_path, monkeypatch) -> None:
    helper = _helper()
    monkeypatch.setattr(helper, "HOME", tmp_path / "home")
    (tmp_path / "home" / "logs").mkdir(parents=True)
    (tmp_path / "home" / "logs" / "helper_start.log").write_text("hi")
    share = tmp_path / "Tools" / "KaraokeTool"
    assert helper.main(["--mirror-logs", str(share)]) == 0
    assert (helper.central_logs(str(share)) / "helper_start.log").exists()


def test_what_the_window_says_is_in_the_log(caplog) -> None:
    import logging

    helper = _helper()
    with caplog.at_level(logging.DEBUG, logger="helper"):
        helper._say("cpu")("helper_waiting", {})
        helper._tell("a line")
    texts = [record.getMessage() for record in caplog.records]
    assert any("[cpu]" in text for text in texts) and "a line" in texts
    assert all(record.levelno == logging.DEBUG for record in caplog.records
               if record.name == "helper"), "not twice in the window"


def test_the_batch_files_put_their_logs_on_the_laptop() -> None:
    # v1.0.22: under the name the helper list shows (``hostname``).
    target = '"%SHARE%\\logs\\helpers\\%HOST%" /E /XO'
    start = _read(ROOT / "helper" / "helper_start.bat")
    assert target in start and 'set "LOG=%~dp0logs\\helper_start.log"' in \
        start
    assert start.count("call :mirror") >= 3
    assert ">> \"%LOG%\" echo(%TIME% %*" in start
    for row in start.splitlines():
        if row.strip().startswith("echo ") and "%LOG%" not in row:
            assert row.strip() in ("echo.",), \
                f"a message that is not in the log: {row.strip()}"
    install = _read(ROOT / "helper" / "install_helper.bat")
    assert target in install
    assert install.count("call :mirror") == 2, "at the end and on an error"


def test_the_helper_mirrors_while_it_runs() -> None:
    source = _read(ROOT / "tools" / "helper.py")
    assert "_keep_mirroring(args.share" in source
    assert source.count("mirror_logs(HOME / \"logs\", central_logs(") >= 4
    assert 'setup_logging(HOME / "logs" / "helper")' in source


# -- rounds of v1.0.18 are known by their way ----------------------------------------

def test_an_old_round_of_1_5_14_gets_its_way_as_class() -> None:
    old = {"kind": "separation_round", "payload": {"way": "roformer"}}
    assert wq.job_class(old) == "sep:roformer"
    assert wq.job_class(dict(old, **{"class": "sep:x"})) == "sep:x"
    assert wq.job_class({"kind": "block_round"}) == "block_round"


# -- videos through the queue --------------------------------------------------------

def test_timed_lines_travel_exactly() -> None:
    from modules import shared_work
    from modules.timing import Syllable, TimedLine

    lines = (TimedLine(index=3, text="la la", crowd=True, block=2,
                       syllables=(Syllable("la", 1.0, 1.5, stress=True),
                                  Syllable(" la", 1.5, 2.0, bg=True)),
                       quality="word", disabled=False, bg=False),)
    data = json.loads(json.dumps(shared_work.lines_data(lines)))
    assert shared_work.lines_from(data) == lines


def _fake_render(monkeypatch):
    from modules import video

    made: list = []

    def render(lines, audio, logo, title, target, **options):
        made.append((Path(audio).name, dict(options)))
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(b"video of " + title.encode())
        return target

    monkeypatch.setattr(video, "render_video", render)
    return made


def _inputs(tmp_path):
    audio = tmp_path / "karaoke.wav"
    audio.write_bytes(b"wav")
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"png")
    options = {"width": 1280, "height": 720, "fps": 50,
               "colors": {"voor": (255, 255, 255)}, "artist": "A",
               "orig_title": "B", "background_path": "", "font_path": "",
               "loudness_lufs": -14.0, "true_peak_db": -1.0}
    return audio, logo, options


def test_a_video_is_made_here_without_a_faster_helper(tmp_path,
                                                      monkeypatch) -> None:
    from modules import shared_work

    made = _fake_render(monkeypatch)
    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    monkeypatch.setattr(shared_work, "_QUEUE_ROOT", queue.root)
    audio, logo, options = _inputs(tmp_path)
    target = tmp_path / "out" / "Song.mp4"
    shared_work.render((), audio, logo, "Song", target, **options)
    assert target.read_bytes() == b"video of Song"
    assert made[0][0] == "karaoke.wav", "from the project, not a copy"
    assert "render:1280x720@50" in queue.read_speeds()[wq.own_worker()]


def test_a_video_is_made_on_a_helper_that_is_sooner_done(
        tmp_path, monkeypatch) -> None:
    from modules import shared_work

    made = _fake_render(monkeypatch)
    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    monkeypatch.setattr(shared_work, "_QUEUE_ROOT", queue.root)
    monkeypatch.setattr(shared_work, "local_capabilities",
                        lambda: {"ffmpeg", "processor"})
    queue.note_speed(wq.own_worker(), "render:1280x720@50", 200)
    queue.note_speed("pc-cpu", "render:1280x720@50", 20)
    queue.status("pc-cpu", "waiting", "cpu", can=["ffmpeg", "processor"])
    stop = threading.Event()
    helper = threading.Thread(target=wq.work, args=(
        queue, "pc-cpu", "cpu", __version__,
        {shared_work.RENDER_KIND: shared_work.run_render_round}, stop.is_set),
        kwargs={"idle_s": 1, "can": ["ffmpeg", "processor"]}, daemon=True)
    helper.start()
    audio, logo, options = _inputs(tmp_path)
    target = tmp_path / "out" / "Song.mp4"
    target.parent.mkdir()
    target.write_bytes(b"the video that was there")
    try:
        shared_work.render((), audio, logo, "Song", target, **options)
    finally:
        stop.set()
        helper.join(timeout=10)
    assert target.read_bytes() == b"video of Song"
    assert made[0][0] == "audio.wav", "made from the copy next to the queue"
    assert made[0][1]["colors"] == {"voor": (255, 255, 255)}
    assert not any((queue.files / "render").iterdir())


def test_1_5_12_renders_through_the_queue_and_puts_the_old_aside(
        tmp_path, monkeypatch) -> None:
    from modules import pipeline, test_panel
    from tests.test_v0149 import _project

    _fake_render(monkeypatch)
    root = tmp_path / "Tools" / "KaraokeTool"
    songs = ["Een", "Twee"]
    contexts = {song: _project(root, song) for song in songs}
    for context in contexts.values():
        context.paths.timing_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(test_panel, "_projects", lambda context: songs)
    audio, logo, options = _inputs(tmp_path)

    def inputs(context, text_source="karaoke", audio_source="karaoke"):
        return context, (), audio, logo, context.paths.song, options

    monkeypatch.setattr(pipeline, "video_render_inputs", inputs)
    context = contexts["Een"]
    report = test_panel.rebuild_videos(context, lambda *a: None,
                                       lambda: False)
    for song in songs:
        other = pipeline.context_for_project(context, song)
        plain = pipeline.video_target(other)
        assert plain.read_bytes() == f"video of {song}".encode(), report
        scrap = test_panel._old_videos_folder(context, song)
        assert sorted(path.read_bytes() for path in scrap.iterdir()) == \
            [b"film", b"nieuwere film"]
        assert other.store.get_step("video")["file"] == str(plain)
    assert "2" in report


# -- the bridge of v1.0.20 is gone ------------------------------------------------------

def test_the_bridge_for_the_old_helpers_is_gone() -> None:
    assert not (ROOT / "tools" / "hulp.py").exists()
    from modules.translations import TRANSLATIONS
    for language in TRANSLATIONS.values():
        assert "helper_handed_over" not in language
    for name in ("install_helper.bat", "helper_start.bat"):
        assert f'set "HELPER_VERSION={__version__}"' in \
            _read(ROOT / "helper" / name)



# -- what the review before delivery found ------------------------------------------

def test_a_waiting_round_of_an_earlier_run_is_not_this_computers_work(
        tmp_path, monkeypatch) -> None:
    from modules import shared_work

    made = _fake_render(monkeypatch)
    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    monkeypatch.setattr(shared_work, "_QUEUE_ROOT", queue.root)
    monkeypatch.setattr(shared_work, "worth_sharing", lambda q, job: True)
    monkeypatch.setattr(shared_work, "local_capabilities",
                        lambda: {"ffmpeg", "processor"})
    audio, logo, options = _inputs(tmp_path)
    stale = shared_work.render_job(queue, "old", (), audio, logo, "Old",
                                   options)
    queue.publish(dict(stale, version=__version__, run="gone"))
    target = tmp_path / "out" / "Song.mp4"
    shared_work.render((), audio, logo, "Song", target, **options)
    assert len(made) == 1 and target.read_bytes() == b"video of Song"
    assert shared_work.tidy_at_start() == 1, "gone at the next start"
    assert not list(queue.jobs.glob("*.json"))
    assert not (queue.root / stale["payload"]["folder"]).exists()
    source = _read(ROOT / "KaraokeTool.py")
    assert "shared_work.tidy_at_start()" in source


def test_twins_of_a_render_never_write_into_one_file(tmp_path,
                                                    monkeypatch) -> None:
    from modules import shared_work

    _fake_render(monkeypatch)
    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    audio, logo, options = _inputs(tmp_path)
    job = shared_work.render_job(queue, "s", (), audio, logo, "S", options)
    first = shared_work.run_render_round(job, queue, lambda: False)
    second = shared_work.run_render_round(job, queue, lambda: False)
    assert first["video"] != second["video"]
    assert (queue.out_dir(job["id"]) / first["video"]).read_bytes() == \
        b"video of S"


def test_a_share_that_is_full_leaves_the_render_here(tmp_path,
                                                     monkeypatch) -> None:
    from modules import shared_work

    made = _fake_render(monkeypatch)
    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    monkeypatch.setattr(shared_work, "_QUEUE_ROOT", queue.root)
    monkeypatch.setattr(shared_work, "worth_sharing", lambda q, job: True)

    def full(*args, **kwargs):
        raise OSError("no space left")

    monkeypatch.setattr(shared_work, "render_job", full)
    audio, logo, options = _inputs(tmp_path)
    target = tmp_path / "Song.mp4"
    shared_work.render((), audio, logo, "Song", target, **options)
    assert made[0][0] == "karaoke.wav"


def test_a_render_goes_to_a_processor_lane() -> None:
    from modules import shared_work
    from modules.separation_trial import local_capabilities

    assert set(shared_work.RENDER_NEEDS) == {"ffmpeg", "processor"}
    assert "processor" in local_capabilities()
    source = _read(ROOT / "tools" / "helper.py")
    # v1.0.24 (B646): and the lane that does card or processor rounds.
    assert 'if lane in ("cpu", MIXED) and have:' in source


def test_1_5_12_says_which_videos_it_did_not_make(tmp_path,
                                                  monkeypatch) -> None:
    from modules import pipeline, test_panel
    from tests.test_v0149 import _project

    _fake_render(monkeypatch)
    root = tmp_path / "Tools" / "KaraokeTool"
    context = _project(root, "Een")
    context.paths.timing_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(test_panel, "_projects", lambda context: ["Een"])
    audio, logo, options = _inputs(tmp_path)
    monkeypatch.setattr(pipeline, "video_render_inputs",
                        lambda c, text_source="karaoke",
                        audio_source="karaoke":
                        (c, (), audio, logo, "Een", options))
    asked: list = []

    def cancelled() -> bool:            # planned, then Stop
        asked.append(True)
        return len(asked) > 1

    report = test_panel.rebuild_videos(context, lambda *a: None, cancelled)
    assert "gestopt" in report or "stopped" in report
    plain = pipeline.video_target(context)
    assert plain.read_bytes() == b"film", "nothing was touched"


def test_a_long_start_log_starts_anew() -> None:
    start = _read(ROOT / "helper" / "helper_start.bat")
    assert "%%~zA GTR 1000000" in start and "helper_start_previous.log" in \
        start


# -- a check of a helper through the queue -------------------------------------------

def test_a_check_goes_to_its_own_computer_before_the_rest(tmp_path) -> None:
    from modules import diagnose

    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    queue.publish({"id": "round", "kind": "k", "version": "1.0",
                   "label": "a test round", "payload": {}})
    time.sleep(0.01)
    check = diagnose.check_job("Pav", "1.0")
    queue.publish(check)
    accept = lambda job: True                           # noqa: E731
    job, _ = queue.claim("MiniPC3-cpu", "1.0", accept)
    assert job["id"] == "round", "not for MiniPC3"
    queue.release(job)
    job, _ = queue.claim("Pav-cpu", "1.0", accept)
    assert job["id"] == check["id"], "for Pav, and before the older round"
    assert wq.addressed_to({"for": "pav"}, "Pav-gpu")
    assert not wq.addressed_to({"for": "Pav"}, "BarWin10-cpu") or \
        wq.host_name().lower() == "pav"
    assert wq.addressed_to({}, "anyone")


def test_mutation_without_priority_the_check_waits_behind_the_test(
        tmp_path) -> None:
    from modules import diagnose

    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    queue.publish({"id": "round", "kind": "k", "version": "1.0",
                   "label": "r", "payload": {}})
    time.sleep(0.01)
    check = dict(diagnose.check_job("Pav", "1.0"), priority=0)
    queue.publish(check)
    job, _ = queue.claim("Pav-cpu", "1.0", lambda job: True)
    assert job["id"] == "round"


def test_the_check_reports_what_it_found(tmp_path, monkeypatch) -> None:
    from modules import diagnose, separation

    seen: list = []

    def run(command, env=None, timeout=600):
        seen.append((command, dict(env or {})))
        if "nvidia-smi" in command[0]:
            return 0, "GeForce GTX 1050 | 2048MiB", 0.1
        if "--selftest" in command:
            slow = (env or {}).get("CUDA_VISIBLE_DEVICES") == "-1"
            return 0, "ok", 40.0 if slow else 9.0
        if "-c" in command:
            return 0, '{"torch": "2.8.0+cu126", "cuda_available": true}', 1
        return 0, "", 1.0

    monkeypatch.setattr(diagnose, "_run", run)
    monkeypatch.setattr(separation, "roformer_python",
                        lambda: tmp_path / "python.exe")
    monkeypatch.setattr(separation, "roformer_models_dir",
                        lambda: tmp_path / "models")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / separation.ROFORMER_MODELS["vocals"]).write_text(
        "m")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")    # a processor lane
    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    answer = diagnose.run_round(diagnose.check_job("Pav", "1.0"), queue,
                                lambda: False)
    text = answer["report"]
    assert "GTX 1050" in text and "2.8.0+cu126" in text
    assert "9 s" in text and "40 s" in text
    trials = [env for command, env in seen if "--selftest" in command]
    assert "CUDA_VISIBLE_DEVICES" not in trials[0], "the card is shown"
    assert trials[1]["CUDA_VISIBLE_DEVICES"] == "-1"


def test_1_5_18_asks_every_helper_and_keeps_the_report(
        tmp_path, monkeypatch) -> None:
    from modules import diagnose, test_panel
    from tests.test_v0149 import _project

    root = tmp_path / "Tools" / "KaraokeTool"
    context = _project(root, "Een")
    queue = wq.queue_for(context).ensure()
    queue.status("Pav-gpu", "working", "gpu", version=__version__)
    status = json.loads((queue.workers / "Pav-gpu.json").read_text())
    status["host"] = "Pav"
    (queue.workers / "Pav-gpu.json").write_text(json.dumps(status))
    monkeypatch.setattr(diagnose, "run_round",
                        lambda job, queue_, stop: {"report": "## Pav ok"})

    def helper():
        for _ in range(100):
            job, _new = queue.claim("Pav-cpu", __version__, lambda j: True)
            if job is None and wq.host_name().lower() != "pav":
                # this test machine is not Pav: take it as Pav would
                paths = list(queue.jobs.glob("*.json"))
                if paths:
                    job = json.loads(paths[0].read_text())
                    paths[0].rename(queue.claimed / paths[0].name)
            if job is not None:
                queue.finish(job, {"report": "## Pav ok"}, "Pav-cpu", "cpu")
                return
            time.sleep(0.05)

    thread = threading.Thread(target=helper, daemon=True)
    thread.start()
    text = test_panel.check_helpers(context, lambda *a: None, lambda: False)
    thread.join(timeout=5)
    assert "## Pav ok" in text
    kept = list((context.paths.logs_dir / "helpers" / "Pav").glob(
        "check_*.md"))
    assert kept and kept[0].read_text() == "## Pav ok"


def test_a_check_is_left_to_nobody_and_twinned_by_nobody(tmp_path) -> None:
    from modules import diagnose

    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    queue.note_speed("Pav-cpu", diagnose.JOB_KIND, 600)
    queue.note_speed("MiniPC3-cpu", diagnose.JOB_KIND, 60)
    queue.status("MiniPC3-cpu", "waiting", "cpu", can=[])
    check = diagnose.check_job("Pav", "1.0")
    queue.publish(check)
    smart = wq.Smart(queue, "Pav-cpu")
    assert not smart.leave(check), "only Pav can take it"
    assert not smart.twin_worth_it(check, {"worker": "Pav-gpu"})


def test_a_check_skips_the_card_while_the_card_lane_works(
        tmp_path, monkeypatch) -> None:
    from modules import diagnose, separation

    seen: list = []
    monkeypatch.setattr(diagnose, "_run", lambda command, env=None,
                        timeout=600: seen.append(command) or (0, "", 1.0))
    monkeypatch.setattr(separation, "roformer_python",
                        lambda: tmp_path / "python.exe")
    monkeypatch.setattr(separation, "roformer_models_dir",
                        lambda: tmp_path / "models")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / separation.ROFORMER_MODELS["vocals"]).write_text(
        "m")
    monkeypatch.setenv("KT_WHISPER_DEVICE", "cpu")
    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    queue.status(f"{wq.host_name()}-gpu", "working", "gpu")
    text = diagnose.run_round(diagnose.check_job("x", "1.0"), queue,
                              lambda: False)["report"]
    assert not any("modules.cuda" in command for command in seen)
    assert sum("--selftest" in command for command in seen) == 1
    assert "nvidia-smi" in " ".join(seen[0]) and "kaartbaan" in text or \
        "card lane" in text


def test_1_5_18_only_asks_helpers_of_this_version(tmp_path) -> None:
    from modules import test_panel
    from tests.test_v0149 import _project

    context = _project(tmp_path / "Tools" / "KaraokeTool", "Een")
    queue = wq.queue_for(context).ensure()
    queue.status("old-cpu", "waiting", "cpu", version="1.0.20")
    queue.status("gone-cpu", "stopped", "cpu", version=__version__)
    text = test_panel.check_helpers(context, lambda *a: None, lambda: False)
    assert "geen helper" in text.lower() or "no helper" in text.lower()


def test_a_bad_priority_does_not_take_a_lane_down(tmp_path) -> None:
    queue = wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()
    queue.publish({"id": "a", "kind": "k", "version": "1.0", "label": "a",
                   "priority": "high", "payload": {}})
    job, _ = queue.claim("pc-cpu", "1.0")
    assert job["id"] == "a"
