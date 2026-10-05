"""v1.0.18: other computers in the network help with the long tests.

The work queue (:mod:`modules.work_queue`), the helper (``tools/hulp.py``)
and 1.5.14 putting its rounds out through the queue. Each rule of the
queue has a test, and the rules that matter most - one job one worker,
nothing lost, one version - a mutation check too.
"""
from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest

from modules import work_queue as wq

ROOT = Path(__file__).resolve().parents[1]


def _job(key: str, version: str = "1.0", run: str = "r1") -> dict:
    return {"id": wq.job_id(key), "run": run, "kind": "k",
            "version": version, "label": key, "payload": {"key": key}}


def _queue(tmp_path) -> wq.Queue:
    return wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()


# -- the queue --------------------------------------------------------------

def test_a_job_is_taken_by_one_worker_only(tmp_path) -> None:
    queue = _queue(tmp_path)
    assert queue.publish(_job("a"))
    assert not queue.publish(_job("a")), "the same round is not put twice"
    first, _ = queue.claim("pc1-cpu", "1.0")
    second, _ = queue.claim("pc2-gpu", "1.0")
    assert first is not None and second is None
    assert not list(queue.jobs.glob("*.json"))


def test_two_workers_reaching_at_once_never_share_a_job(tmp_path) -> None:
    queue = _queue(tmp_path)
    for n in range(40):
        queue.publish(_job(f"j{n}"))
    taken: list[str] = []
    lock = threading.Lock()

    def grab(name: str) -> None:
        while True:
            job, _ = queue.claim(name, "1.0")
            if job is None:
                return
            with lock:
                taken.append(job["id"])

    threads = [threading.Thread(target=grab, args=(f"w{n}",))
               for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(taken) == 40 and len(set(taken)) == 40


def test_a_worker_takes_only_jobs_of_its_own_version(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("new", version="2.0"))
    job, newer = queue.claim("pc1-cpu", "1.0")
    assert job is None and newer
    job, newer = queue.claim("pc1-cpu", "2.0")
    assert job is not None and not newer


def test_a_silent_worker_loses_its_job_on_the_programs_clock(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    job, _ = queue.claim("pc1-cpu", "1.0")
    seen: dict = {}
    moment = 0.0
    queue.heartbeat(job["id"], "pc1-cpu", 1, job["token"])   # still at it
    back = []
    while moment < 2 * wq.STALE_S and not back:
        back = queue.requeue_stale(seen, now=moment)
        moment += 5.0                       # the program looks every 5 s
    assert back == [job["id"]]
    assert moment == pytest.approx(wq.STALE_S + 5.0)
    again, _ = queue.claim("pc2-gpu", "1.0")
    assert again is not None and again["id"] == job["id"]


def test_a_program_that_slept_does_not_rob_the_workers(tmp_path) -> None:
    """Review of v1.0.18: after the laptop slept for longer than the
    limit, every job looked silent at once and was given away within
    seconds of waking. A long gap between two looks starts the counts
    afresh."""
    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    job, _ = queue.claim("pc1-cpu", "1.0")
    seen: dict = {}
    assert queue.requeue_stale(seen, now=0.0) == []
    assert queue.requeue_stale(seen, now=3 * wq.STALE_S) == []
    queue.heartbeat(job["id"], "pc1-cpu", 1, job["token"])
    assert queue.requeue_stale(seen, now=3 * wq.STALE_S + 5) == []


def test_a_worker_whose_job_was_given_away_leaves_the_new_claim(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    first, _ = queue.claim("pc1-cpu", "1.0")
    seen: dict = {}
    moment = 0.0
    while not queue.requeue_stale(seen, now=moment):
        moment += 5.0
    second, _ = queue.claim("pc2-gpu", "1.0")
    queue.finish(first, {"ok": 1}, "pc1-cpu", "cpu")
    assert (queue.claimed / f"{second['id']}.json").exists(), \
        "the second claim stands"
    queue.release(first)
    assert (queue.claimed / f"{second['id']}.json").exists()
    assert queue.owns(second)


def test_an_older_version_job_is_replaced_not_waited_for(tmp_path) -> None:
    """Review of v1.0.18: jobs of a closed run of an older version were
    never taken and the test waited for ever, while helpers restarted
    to 'update' every few seconds."""
    queue = _queue(tmp_path)
    queue.publish(_job("a", version="1.0.18", run="old"))
    job, newer = queue.claim("w", "1.0.19")
    assert job is None and not newer, "older is not newer"
    assert queue.publish(_job("a", version="1.0.19", run="new"))
    job, _ = queue.claim("w", "1.0.19")
    assert job is not None and job["version"] == "1.0.19"
    queue.publish(_job("b", version="1.0.18", run="old"))
    assert queue.withdraw_other_versions("k", "1.0.19") == 1


def test_a_job_that_keeps_crashing_its_worker_is_answered(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    for _n in range(wq.MAX_TRIES):
        job, _ = queue.claim("w", "1.0")
        queue.release(job)
    wq.work(queue, "w", "cpu", "1.0",
            {"k": lambda job, q, stop: pytest.fail("not again")},
            lambda: False, once=True)
    (answer,) = queue.answers()
    assert "crashed" in answer["result"]["failed"]


def test_a_worker_leaves_what_it_cannot_do(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("roformer"))
    job, _ = queue.claim("w", "1.0",
                         accept=lambda job: job["label"] != "roformer")
    assert job is None
    assert (queue.jobs / f"{wq.job_id('roformer')}.json").exists()


def test_the_heartbeat_keeps_a_long_job(tmp_path) -> None:
    """Mutation check on the rule above: a worker that keeps counting is
    never robbed, however long its job takes (a Roformer round on the
    laptop took 55 minutes)."""
    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    job, _ = queue.claim("pc1-cpu", "1.0")
    seen: dict = {}
    for n in range(20):
        queue.heartbeat(job["id"], "pc1-cpu", n + 1, job["token"])
        assert queue.requeue_stale(seen, now=n * 30.0) == []


def test_a_stopped_test_takes_back_only_its_untaken_jobs(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a", run="r1"))
    queue.publish(_job("b", run="r1"))
    queue.publish(_job("c", run="r2"))
    taken, _ = queue.claim("pc1-cpu", "1.0")
    assert queue.withdraw("r1") == 1
    left = {path.stem for path in queue.jobs.glob("*.json")}
    assert wq.job_id("c") in left
    assert (queue.claimed / f"{taken['id']}.json").exists()


# -- the worker ---------------------------------------------------------------

def test_a_worker_answers_and_says_what_it_does(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    said = []
    outcome = wq.work(queue, "pc1-cpu", "cpu", "1.0",
                      {"k": lambda job, q, stop: {"value": 7}},
                      lambda: False, lambda key, values: said.append(key),
                      once=True)
    assert outcome == "stopped"
    (answer,) = queue.answers()
    assert answer["result"]["value"] == 7 and answer["worker"] == "pc1-cpu"
    assert "seconds" in answer["result"]
    assert not list(queue.claimed.glob("*"))
    assert "helper_job" in said and "helper_job_done" in said
    (status,) = queue.active_workers()
    assert status["worker"] == "pc1-cpu"


def test_a_failing_job_is_an_answer_not_a_crash(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a"))

    def broken(job, q, stop):
        raise RuntimeError("CUDA out of memory")

    wq.work(queue, "pc1-gpu", "gpu", "1.0", {"k": broken}, lambda: False,
            once=True)
    (answer,) = queue.answers()
    assert "CUDA out of memory" in answer["result"]["failed"]


def test_a_stopped_worker_puts_its_job_back(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a"))

    def interrupted(job, q, stop):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        wq.work(queue, "pc1-cpu", "cpu", "1.0", {"k": interrupted},
                lambda: False, once=True)
    assert (queue.jobs / f"{wq.job_id('a')}.json").exists()
    assert not list(queue.claimed.glob("*"))


def test_a_worker_waits_and_goes_on_when_work_comes(tmp_path) -> None:
    queue = _queue(tmp_path)
    stop = wq.Stop()
    naps = []

    def nap(seconds):
        naps.append(seconds)
        if len(naps) == 3:
            queue.publish(_job("late"))
        if queue.answers():
            stop.asked = True

    wq.work(queue, "pc1-cpu", "cpu", "1.0",
            {"k": lambda job, q, s: {"ok": True}}, stop, idle_s=1,
            sleep=nap)
    assert len(queue.answers()) == 1 and len(naps) >= 3


def test_a_worker_with_an_old_version_stops_to_update(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a", version="9.9"))
    assert wq.work(queue, "pc1-cpu", "cpu", "1.0", {}, lambda: False) == \
        "update"


# -- the helper -------------------------------------------------------------------

def _hulp():
    # v1.0.20: the helper is tools/helper.py.
    spec = importlib.util.spec_from_file_location(
        "helper", ROOT / "tools" / "helper.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_computer_with_a_working_card_works_in_two_lanes() -> None:
    hulp = _hulp()
    assert hulp.choose_lanes("auto", True) == ["gpu", "cpu"]
    assert hulp.choose_lanes("auto", False) == ["cpu"]
    assert hulp.choose_lanes("gpu", False) == ["cpu"], "no card, no card lane"
    assert hulp.choose_lanes("cpu", True) == ["cpu"]


def test_an_older_card_gets_what_it_does_well() -> None:
    from modules import cuda      # v1.0.20: shared with the program

    assert cuda.choose_compute({"float16", "int8", "float32"}) == "float16"
    assert cuda.choose_compute({"int8", "float32"}) == "int8"
    assert cuda.choose_compute({"float32"}) == "float32"
    assert cuda.choose_compute(()) == "float32"


def test_the_helper_scripts_install_and_start_as_agreed() -> None:
    # v1.0.20: English names; the program is fetched by the installer,
    # which the start file runs when the share has a newer version.
    install = (ROOT / "helper" / "install_helper.bat").read_text(
        encoding="utf-8")
    start = (ROOT / "helper" / "helper_start.bat").read_text(
        encoding="utf-8")
    assert "download.pytorch.org/whl/cu126" in install
    assert "audio-separator[%SEPKIND%]" in install and "audioread" in install
    assert "--selftest" in install and "helper.py\" --check" in install
    for row in install.splitlines():
        if " -m pip install" in row:
            assert "%TEE%" in row, row
    assert "/XD venv venv_separator models" in install
    assert "if errorlevel 3 if not errorlevel 4 goto :again" in start
    assert "share.txt" in install and "share.txt" in start


# -- 1.5.14 through the queue -----------------------------------------------

def _trial_setup(tmp_path, monkeypatch):
    from modules import ffmpeg, pipeline, separation
    from modules import separation_trial as st
    from tests.test_front_to_back import _install

    root, context = _install(tmp_path)
    monkeypatch.setattr(separation, "roformer_python", lambda: None)
    monkeypatch.setattr(separation, "is_available",
                        lambda way=None: way is None
                        or way.backend == "demucs")

    def convert(source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"wav")
        return target

    monkeypatch.setattr(ffmpeg, "convert_to_wav", convert)
    monkeypatch.setattr(pipeline, "_language_for", lambda c, track: "nl")
    monkeypatch.setattr(st, "_POLL_S", 1.0)
    return root, context, st


def test_1_5_14_takes_the_answers_of_a_helper(tmp_path, monkeypatch) -> None:
    """A helper on this same computer: the program leaves the work to it,
    takes its answers over, moves its listening copies and says in the
    report who did how much."""
    root, context, st = _trial_setup(tmp_path, monkeypatch)
    from modules import __version__

    done_here = []
    monkeypatch.setattr(st, "run_round", lambda job, queue, stop: (
        done_here.append(job["id"]), {"dips": 0.0})[1])
    queue = wq.Queue(st.queue_root(context)).ensure()
    stop = wq.Stop()

    def helper_round(job, q, s):
        folder = q.out_dir(job["id"])
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{job['payload']['way']}_music.mp3").write_bytes(b"mp3")
        return {"dips": 1.5, "residue": 3, "certainty": 0.9,
                "in_text": 90.0, "unheard": 1.0, "hits": 80.0, "words": 9}

    helper = threading.Thread(target=wq.work, args=(
        queue, f"{wq.host_name()}-gpu", "gpu", __version__,
        {st.JOB_KIND: helper_round}, stop), kwargs={"idle_s": 1})
    helper.start()
    try:
        deadline = time.time() + 10
        while not queue.active_workers() and time.time() < deadline:
            time.sleep(0.1)
        text = st.run(context, lambda *a: None, lambda: False)
    finally:
        stop.asked = True
        helper.join(timeout=10)
    assert done_here == [], "a helper runs here, so the program leaves it"
    assert st.t("separation_trial_helpers") in text
    assert f"{wq.host_name()}-gpu" in text
    scrap = st.scratch_root(context)
    stored = json.loads((scrap / "results.json").read_text("utf-8"))
    assert stored["runs"] and all(run.get("device") == "gpu"
                                  for run in stored["runs"].values())
    assert (scrap / "listen" / "Song_A" / "demucs_music.mp3").exists()
    assert not list(queue.jobs.glob("*.json"))
    assert not (queue.files / "sep").exists(), "the originals are cleared"


def test_1_5_14_works_itself_when_nobody_helps(tmp_path, monkeypatch) -> None:
    root, context, st = _trial_setup(tmp_path, monkeypatch)
    done_here = []
    monkeypatch.setattr(st, "run_round", lambda job, queue, stop: (
        done_here.append(job["payload"]["way"]), {"dips": 0.0})[1])
    st.run(context, lambda *a: None, lambda: False)
    assert sorted(set(done_here)) == ["demucs", "demucs_careful"]
    # A second run finds everything measured and puts nothing out.
    done_here.clear()
    st.run(context, lambda *a: None, lambda: False)
    assert done_here == []


def test_a_round_travels_as_plain_data(tmp_path, monkeypatch) -> None:
    root, context, st = _trial_setup(tmp_path, monkeypatch)
    facts = st.song_facts(context, "Song_A")
    assert json.loads(json.dumps(facts)) == facts
    settings = st.settings_from(facts["whisper"])
    assert settings == context.config.whisper
    assert st.settings_from({"model": "small", "unknown": 1}).model == \
        "small"


def test_a_helper_outlives_a_share_that_goes_away(tmp_path) -> None:
    """The laptop sleeps: the helper waits instead of falling over, and
    an answer it has keeps until the share is back."""
    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    real_finish = queue.finish
    tries = []

    def flaky_finish(job, answer, worker, device):
        tries.append(1)
        if len(tries) < 3:
            raise OSError("network name is no longer available")
        real_finish(job, answer, worker, device)

    queue.finish = flaky_finish
    said = []
    wq.work(queue, "pc1-cpu", "cpu", "1.0",
            {"k": lambda job, q, stop: {"ok": True}}, lambda: False,
            lambda key, values: said.append(key), sleep=lambda s: None,
            once=True)
    assert len(queue.answers()) == 1 and len(tries) == 3
    assert "helper_share_away" in said

    gone = wq.Queue(tmp_path / "nowhere" / "file.txt" / "kt_werk")
    (tmp_path / "nowhere").mkdir()
    (tmp_path / "nowhere" / "file.txt").write_text("x")
    stop = wq.Stop()
    naps = []

    def nap(seconds):
        naps.append(seconds)
        stop.asked = len(naps) >= 2

    said.clear()
    assert wq.work(gone, "pc1-cpu", "cpu", "1.0", {}, stop,
                   lambda key, values: said.append(key), idle_s=1,
                   sleep=nap) == "stopped"
    assert said == ["helper_share_away"]
