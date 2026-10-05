"""v1.0.19: a smarter helper system, one launcher, and the full karaoke.

* the queue shares out by speed: a slow worker leaves the last rounds to
  a faster one, and at the end an idle fast worker does a round a slow
  one holds too (a twin) - the first good answer counts;
* every test goes through the queue, the program's own computer too;
* a helper finds the laptop itself and brings itself up to date;
* ``install.bat`` went up in ``KaraokeToolGUI.bat``;
* "Make full karaoke": the original alone, a text of what was heard to
  check, then timing and video;
* tests 1.5.16 (JamendoLyrics) and 1.5.17 (MUSDB18).

The rules that decide who does what have a mutation check: the test is
run once more with the rule taken out and has to fail then.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from modules import work_queue as wq

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hulp():
    # v1.0.20: tools/helper.py.
    return _load("helper_v1019", "tools/helper.py")


def _queue(tmp_path) -> wq.Queue:
    return wq.Queue(tmp_path / wq.QUEUE_NAME).ensure()


def _job(key: str, cls: str = "c", version: str = "1.0",
         kind: str = "k", needs=()) -> dict:
    return {"id": wq.job_id(key), "run": "r1", "kind": kind, "class": cls,
            "version": version, "label": key, "needs": list(needs),
            "payload": {"key": key}}


def _speeds(queue: wq.Queue, **seconds) -> None:
    for worker, value in seconds.items():
        queue.note_speed(worker, "c", value)


# -- speeds -------------------------------------------------------------------

def test_a_worker_is_known_by_its_own_rounds_or_by_the_others() -> None:
    speeds = {"slow": {"c": [200.0, 2], "d": [40.0, 1]},
              "fast": {"c": [20.0, 2], "d": [4.0, 1], "e": [6.0, 1]}}
    assert wq.estimate(speeds, "slow", "c") == 100.0
    # slow is ten times as slow on what both did: e takes it ten times 6 s
    assert wq.estimate(speeds, "slow", "e") == pytest.approx(60.0)
    assert wq.estimate(speeds, "new", "c") is None, "nothing known of it"
    assert wq.estimate(speeds, "slow", "unknown") is None


def test_the_speeds_are_noted_per_worker_and_class(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.note_speed("pc", "c", 10)
    queue.note_speed("pc", "c", 30)
    queue.note_speed("pc", "c", None)
    queue.note_speed("", "c", 5)
    assert queue.read_speeds() == {"pc": {"c": [40.0, 2]}}


# -- who takes the last rounds --------------------------------------------------

def test_a_slow_worker_leaves_the_last_round_to_a_faster_one(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    _speeds(queue, slow=100, fast=10)
    queue.status("fast", "waiting", "cpu")
    queue.publish(_job("last"))
    job, _ = wq.Smart(queue, "slow").claim("1.0", lambda job: True)
    assert job is None and list(queue.jobs.glob("*.json"))
    job, _ = wq.Smart(queue, "fast").claim("1.0", lambda job: True)
    assert job is not None


def test_a_slow_worker_takes_work_while_there_is_plenty(tmp_path) -> None:
    queue = _queue(tmp_path)
    _speeds(queue, slow=100, fast=10)
    queue.status("fast", "waiting", "cpu")
    for key in ("a", "b"):
        queue.publish(_job(key))
    job, _ = wq.Smart(queue, "slow").claim("1.0", lambda job: True)
    assert job is not None


def test_the_time_a_faster_worker_still_needs_counts(tmp_path) -> None:
    """Fast but busy for another 200 s: the slow one is done sooner."""
    queue = _queue(tmp_path)
    _speeds(queue, slow=100, fast=10)
    queue.status("fast", "working", "cpu", _job("other"), left_s=200.0)
    queue.publish(_job("last"))
    job, _ = wq.Smart(queue, "slow").claim("1.0", lambda job: True)
    assert job is not None


def test_mutation_without_the_rule_the_slow_one_holds_up_the_end(
        tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wq.Smart, "leave", lambda self, job: False)
    with pytest.raises(AssertionError):
        test_a_slow_worker_leaves_the_last_round_to_a_faster_one(tmp_path)


# -- twins ----------------------------------------------------------------------

def _held(tmp_path, left_s: float = 90.0):
    queue = _queue(tmp_path)
    _speeds(queue, slow=100, fast=10)
    queue.publish(_job("held"))
    job, _ = queue.claim("slow", "1.0")
    queue.status("slow", "working", "cpu", job, left_s=left_s)
    return queue, job


def test_an_idle_fast_worker_twins_a_round_a_slow_one_holds(
        tmp_path) -> None:
    queue, held = _held(tmp_path)
    twin, _ = wq.Smart(queue, "fast").claim("1.0", lambda job: True)
    assert twin is not None and twin["twin"] and twin["id"] == held["id"]
    assert wq.Smart(queue, "fast2").claim("1.0", lambda job: True)[0] is None
    queue.finish(twin, {"value": "fast"}, "fast", "cpu")
    assert queue.answered(held["id"])
    queue.finish(held, {"value": "slow"}, "slow", "cpu")
    (answer,) = queue.answers()
    assert answer["result"] == {"value": "fast"}, "the first answer counts"
    assert answer["worker"] == "fast"
    assert not list(queue.claimed.iterdir())


def test_no_twin_when_the_holder_is_nearly_done(tmp_path) -> None:
    queue, _held_job = _held(tmp_path, left_s=5.0)
    assert wq.Smart(queue, "fast").claim("1.0", lambda job: True)[0] is None


def test_a_failed_twin_leaves_the_holder_alone(tmp_path) -> None:
    queue, held = _held(tmp_path)
    twin, _ = wq.Smart(queue, "fast").claim("1.0", lambda job: True)
    queue.finish(twin, {"failed": "boom"}, "fast", "cpu")
    assert not queue.answered(held["id"]) and not queue.answers()
    queue.finish(held, {"value": "slow"}, "slow", "cpu")
    assert queue.answers()[0]["result"] == {"value": "slow"}


def test_an_answered_holder_is_cleared_only_once_it_stops_beating(
        tmp_path) -> None:
    """While the slow worker still beats, the marker stays so that it
    sees it and stops; when it is gone, nothing goes back in the queue."""
    queue, held = _held(tmp_path)
    twin, _ = wq.Smart(queue, "fast").claim("1.0", lambda job: True)
    queue.finish(twin, {"value": "fast"}, "fast", "cpu")
    seen: dict = {}
    moment = 0.0
    for count in range(12):                       # it still beats
        queue.heartbeat(held["id"], "slow", count + 1, held["token"])
        queue.requeue_stale(seen, now=moment)
        moment += 30.0
    assert queue.answered(held["id"])
    while moment < 30.0 * 12 + 2 * wq.STALE_S:   # and then it is gone
        queue.requeue_stale(seen, now=moment)
        moment += 30.0
    assert not list(queue.claimed.iterdir())
    assert not list(queue.jobs.glob("*.json")), "the answer is there"


def test_a_worker_whose_round_was_twinned_stops_and_moves_on(
        tmp_path, monkeypatch) -> None:
    """In the helper loop: the heartbeat sees the answer and stops what
    runs; the late answer is dropped."""
    queue, held = _held(tmp_path)
    queue.jobs.mkdir(exist_ok=True)
    monkeypatch.setattr(wq, "HEARTBEAT_S", 0.05)
    monkeypatch.setattr(wq, "STATUS_S", 0.05)      # v1.0.28
    lost = []
    said = []
    queue.release(held)                    # the loop claims it itself

    def handler(job, queue_, stop):
        twin = dict(job, twin=True, token="t")
        (queue.claimed / f"{job['id']}.twin").write_text("fast")
        queue.finish(twin, {"value": "fast"}, "fast", "cpu")
        import time
        deadline = time.time() + 5
        while not lost and time.time() < deadline:
            time.sleep(0.02)
        return {"value": "slow"}

    wq.work(queue, "slow", "cpu", "1.0", {"k": handler}, lambda: False,
            say=lambda key, values: said.append(key), once=True,
            on_lost=lambda: lost.append(True))
    assert lost and "helper_job_lost" in said
    assert queue.answers()[0]["result"] == {"value": "fast"}


# -- every test through the queue -------------------------------------------------

def _handlers(done: list):
    def handler(job, queue, cancelled):
        done.append(job["payload"]["key"])
        return {"key": job["payload"]["key"], "seconds": 2.0}
    return {"k": handler}


def test_without_helpers_the_program_does_every_round_itself(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    done: list = []
    answers: list = []
    counts = wq.run_jobs(queue, [_job(n) for n in "abc"], "1.0",
                         _handlers(done), answers.append, lambda: False,
                         poll_s=1, sleep=lambda s: None)
    assert sorted(done) == ["a", "b", "c"]
    assert counts["local"] == 3 and counts["answered"] == 3
    assert len(answers) == 3
    assert wq.own_worker() in queue.read_speeds()
    assert json.loads((queue.root / "laptop.json").read_text())["host"]


def test_a_waiting_round_of_another_version_is_taken_out(tmp_path) -> None:
    queue = _queue(tmp_path)
    old = _job("old", version="0.9")
    queue.publish(old)
    wq.run_jobs(queue, [_job("a")], "1.0", _handlers([]), lambda a: None,
                lambda: False, poll_s=1, sleep=lambda s: None)
    assert not (queue.jobs / f"{old['id']}.json").exists()


def test_light_rounds_run_side_by_side_on_the_programs_computer(
        tmp_path, monkeypatch) -> None:
    queue = _queue(tmp_path)
    monkeypatch.setattr(wq, "_pool", lambda lanes: ThreadPoolExecutor(lanes))
    ran: list = []
    monkeypatch.setattr(wq, "_child_round",
                        lambda kind, job, root: ran.append(job["id"])
                        or {"seconds": 1.0})
    answers: list = []
    counts = wq.run_jobs(queue, [_job(n) for n in "abcd"], "1.0", {},
                         answers.append, lambda: False, poll_s=1,
                         sleep=lambda s: None, local_lanes=2)
    assert len(ran) == 4 and counts["local"] == 4 and len(answers) == 4


def test_the_program_takes_over_when_its_own_helper_cannot(
        tmp_path) -> None:
    """A helper on this same computer waits while work waits (a way it
    cannot do): after a while the program does it itself."""
    queue = _queue(tmp_path)
    queue.status("here-cpu", "waiting", "cpu")
    assert not wq.may_work_here(queue)
    done: list = []
    counts = wq.run_jobs(queue, [_job("a")], "1.0", _handlers(done),
                         lambda a: None, lambda: False, poll_s=1,
                         sleep=lambda s: None, stuck_s=-1.0)
    assert done == ["a"] and counts["local"] == 1


def test_mutation_without_taking_over_the_test_would_wait(tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.status("here-cpu", "waiting", "cpu")
    ticks: list = []
    counts = wq.run_jobs(queue, [_job("a")], "1.0", _handlers([]),
                         lambda a: None, lambda: len(ticks) > 20, poll_s=1,
                         sleep=ticks.append, stuck_s=1e9)
    assert counts["local"] == 0
    assert not list(queue.jobs.glob("*.json")), "a stop takes it back"


def _old_round_given_back(tmp_path, monkeypatch, every_s: float) -> list:
    queue = _queue(tmp_path)
    old = _job("a", version="0.9")
    queue.publish(old)
    held, _ = queue.claim("oldpc", "0.9")
    monkeypatch.setattr(wq, "_REPUBLISH_S", every_s)
    done: list = []
    ticks: list = []

    def sleep(seconds):
        ticks.append(seconds)
        if len(ticks) == 2:
            queue.release(held)           # the old helper is closed

    wq.run_jobs(queue, [_job("a")], "1.0", _handlers(done), lambda a: None,
                lambda: len(ticks) > 50, poll_s=1, sleep=sleep, stuck_s=1e9)
    return done


def test_a_round_an_older_helper_gave_back_is_put_out_again(
        tmp_path, monkeypatch) -> None:
    """A round the test put out while an older version's helper held it
    comes back into the queue as the OLD job, which no worker of today
    takes. The program puts its rounds out again now and then."""
    assert _old_round_given_back(tmp_path, monkeypatch, 0.0) == ["a"]


def test_mutation_without_putting_out_again_the_test_waits(
        tmp_path, monkeypatch) -> None:
    assert _old_round_given_back(tmp_path, monkeypatch, 1e9) == []


def test_the_last_round_is_not_left_to_a_worker_that_never_did_one(
        tmp_path) -> None:
    """Fast on other rounds, never did this class (no Roformer, say):
    leaving the round to it would leave it to nobody."""
    queue = _queue(tmp_path)
    queue.note_speed("slow", "c", 100)
    queue.note_speed("slow", "d", 100)
    queue.note_speed("fast", "d", 10)
    queue.status("fast", "waiting", "cpu", can=["ffmpeg"])
    queue.publish(_job("last", needs=["roformer"]))
    job, _ = wq.Smart(queue, "slow").claim("1.0", lambda job: True)
    assert job is not None


def test_marks_of_an_earlier_claim_do_not_swallow_a_new_one(
        tmp_path) -> None:
    queue = _queue(tmp_path)
    queue.publish(_job("a"))
    jid = wq.job_id("a")
    (queue.claimed / f"{jid}.answered").write_text("{}")
    (queue.claimed / f"{jid}.twin").write_text("x")
    job, _ = queue.claim("pc", "1.0")
    queue.finish(job, {"value": 1}, "pc", "cpu")
    assert queue.answers()[0]["result"] == {"value": 1}


def test_a_twin_stops_when_the_holder_answers_first(tmp_path,
                                                    monkeypatch) -> None:
    queue, held = _held(tmp_path)
    monkeypatch.setattr(wq, "HEARTBEAT_S", 0.05)
    monkeypatch.setattr(wq, "STATUS_S", 0.05)      # v1.0.28
    queue.status("slow", "working", "cpu", held, left_s=90.0)
    queue.note_speed("fast", "c", 10)
    lost: list = []
    said: list = []

    def handler(job, queue_, stop):
        assert job.get("twin")
        queue.finish(held, {"value": "slow"}, "slow", "cpu")
        import time
        deadline = time.time() + 5
        while not lost and time.time() < deadline:
            time.sleep(0.02)
        return {"value": "fast"}

    wq.work(queue, "fast", "cpu", "1.0", {"k": handler}, lambda: False,
            say=lambda key, values: said.append(key), once=True,
            on_lost=lambda: lost.append(True))
    assert lost and "helper_job_lost" in said
    assert queue.answers()[0]["result"] == {"value": "slow"}


def test_workers_are_judged_on_the_shares_clock(tmp_path) -> None:
    """A helper whose own clock runs behind still sees who is gone."""
    queue = _queue(tmp_path)
    queue.status("alive", "waiting", "cpu")
    queue.status("gone", "waiting", "cpu")
    now = os.stat(queue.workers / "alive.json").st_mtime
    os.utime(queue.workers / "gone.json", (now - 600, now - 600))
    os.utime(queue.workers / "alive.json", (now + 3600, now + 3600))
    names = [status["worker"] for status in queue.active_workers()]
    assert names == ["alive"]


def test_a_worker_takes_only_what_it_can_do() -> None:
    accept = wq.accept_for({"ffmpeg", "whisper"}, {"k": lambda *a: None})
    assert accept(_job("a", needs=["ffmpeg"]))
    assert not accept(_job("b", needs=["roformer"]))
    assert not accept(_job("c", kind="other"))


def test_every_test_of_the_panel_goes_through_the_queue() -> None:
    from modules import (block_trial, jamendo_trial, musdb_trial, queue_jobs,
                         separation_trial)

    handlers = queue_jobs.handlers()
    for module in (separation_trial, block_trial, jamendo_trial,
                   musdb_trial):
        assert handlers[module.JOB_KIND] is module.run_round
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "run_jobs(" in source, module.__name__


# -- 1.5.15 through the queue -------------------------------------------------------

def test_a_project_travels_as_a_copy_with_the_language_collection(
        tmp_path, monkeypatch) -> None:
    from modules import block_trial, measure_pool
    from tests.test_front_to_back import _install

    root, context = _install(tmp_path, songs=("Song_A",))
    (root / "languages" / "nl.json").write_text('{"own": 1}',
                                                encoding="utf-8")
    queue = wq.Queue(root.parent / wq.QUEUE_NAME).ensure()
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    folder = block_trial.snapshot(context, "Song_A", queue)
    base = queue.root / folder
    assert (base / "output" / "Song_A" / "settings" / "timing.json").exists()
    assert (base / "input" / "Song_A" / "lyrics.txt").exists()
    assert json.loads((base / "languages" / "nl.json").read_text()) == \
        {"own": 1}
    assert sorted(p.relative_to(root).as_posix()
                  for p in root.rglob("*")) == before, "the project is read"
    assert block_trial.snapshot(context, "Song_A", queue) == folder
    seen = []
    monkeypatch.setattr(measure_pool, "_serial",
                        lambda items, report, cancelled:
                        seen.extend(items) or [{"project": "Song_A"}])
    answer = block_trial.run_round(
        {"payload": {"snapshot": folder, "song": "Song_A", "states": {},
                     "setting": ""}}, queue, lambda: False)
    assert answer == {"row": {"project": "Song_A"}}
    assert seen[0][0] == str(base) and seen[0][1] == "Song_A"


# -- a helper finds the laptop ------------------------------------------------------

SHARE = r"\\10.0.0.18\Tools\KaraokeTool"


def test_the_places_to_look_come_in_the_owners_order() -> None:
    hulp = _hulp()
    known = {"host": "LAPTOP", "addresses": ["10.0.0.18", "10.0.0.25"]}
    assert hulp.candidates(SHARE, known) == [
        SHARE, r"\\LAPTOP\Tools\KaraokeTool", r"\\10.0.0.25\Tools\KaraokeTool"]
    assert hulp.split_unc(SHARE) == ("10.0.0.18", ["Tools", "KaraokeTool"])
    assert hulp.split_unc(r"C:/Muziek") == ("", [])


def test_the_laptop_is_found_by_its_other_address(tmp_path,
                                                  monkeypatch) -> None:
    hulp = _hulp()
    monkeypatch.setattr(hulp, "HOME", tmp_path)
    (tmp_path / "known.json").write_text(json.dumps(
        {"host": "LAPTOP", "addresses": ["10.0.0.25"]}))
    looked: list = []

    def reachable(path):
        looked.append(path)
        return path == r"\\10.0.0.25\Tools\KaraokeTool"

    assert hulp.find_share(SHARE, reachable, networks=[]) == \
        r"\\10.0.0.25\Tools\KaraokeTool"
    assert looked[0] == SHARE, "first where the installation came from"


def test_the_own_network_is_the_last_resort(tmp_path, monkeypatch) -> None:
    hulp = _hulp()
    monkeypatch.setattr(hulp, "HOME", tmp_path)
    target = r"\\192.168.1.77\Tools\KaraokeTool"
    assert hulp.find_share(SHARE, lambda path: path == target,
                           networks=["192.168.1"]) == target
    assert hulp.find_share(SHARE, lambda path: False, networks=[]) is None


def test_what_worked_is_remembered(tmp_path, monkeypatch) -> None:
    hulp = _hulp()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(hulp, "HOME", home)
    share = tmp_path / "Tools" / "KaraokeTool"
    # v1.0.23 (B650): the queue is in the program's helper folder.
    wq.queue_folder(share).mkdir(parents=True)
    (wq.queue_folder(share) / "laptop.json").write_text(
        json.dumps({"host": "LAPTOP", "addresses": ["10.0.0.30"]}))
    hulp.remember(str(share))
    known = json.loads((home / "known.json").read_text())
    assert known["host"] == "LAPTOP" and known["addresses"] == ["10.0.0.30"]
    assert (home / "share.txt").read_text().strip() == str(share)


def test_find_says_where_and_keeps_it(tmp_path, monkeypatch, capsys) -> None:
    hulp = _hulp()
    monkeypatch.setattr(hulp, "HOME", tmp_path)
    monkeypatch.setattr(hulp, "find_share", lambda stored: stored + "X")
    assert hulp.main(["--find", "somewhere"]) == 0
    assert capsys.readouterr().out.strip() == "somewhereX"
    assert (tmp_path / "share.txt").read_text().strip() == "somewhereX"
    monkeypatch.setattr(hulp, "find_share", lambda stored: None)
    assert hulp.main(["--find", "somewhere"]) == 1


# -- a helper brings itself up to date ---------------------------------------------

# (v1.0.19's setup stamp and self-swapping start file were replaced at
# v1.0.20 by the version in the installer: see tests/test_v1020.py.)


# -- one launcher -------------------------------------------------------------------

def test_install_bat_went_up_in_the_launcher() -> None:
    assert not (ROOT / "install.bat").exists()
    raw = (ROOT / "KaraokeToolGUI.bat").read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n"), "CRLF"
    launcher = raw.decode("utf-8")
    assert "setup_check.py" in launcher and "--write" in launcher
    assert "roformer_keuze.txt" in launcher
    assert "install.log" in launcher
    for folder in ("modules", "tools"):
        for path in (ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for row in text.splitlines():
                if "install.bat" in row and "install_hulp.bat" not in row:
                    assert "is gone" in row or "went up" in row, \
                        f"{path.name}: {row.strip()}"


def test_the_launcher_sets_up_only_what_changed(tmp_path) -> None:
    check = _load("setup_check_v1019", "tools/setup_check.py")
    venv = tmp_path / "venv"
    venv.mkdir()
    assert check.main([str(venv), "J"]) == 1, "never set up"
    assert check.main([str(venv), "J", "--write"]) == 0
    assert check.main([str(venv), "J"]) == 0
    assert check.main([str(venv), "N"]) == 1, "another Roformer choice"
    other = tmp_path / "root"
    other.mkdir()
    (other / "requirements.txt").write_text("numpy\n")
    first = check.stamp("J", other)
    (other / "requirements.txt").write_text("numpy\nscipy\n")
    assert check.stamp("J", other) != first


# -- Make full karaoke ------------------------------------------------------------

def _words(*rows):
    return [(word, start, start + 0.3) for word, start in rows]


def test_what_was_heard_becomes_lines_and_blocks() -> None:
    from modules import pipeline

    words = _words(("ik", 1.0), ("zie", 1.4), ("de", 1.8), ("zon", 2.2),
                   ("wij", 3.5), ("lopen", 3.9), ("♪", 4.2),
                   ("daar", 10.0), ("gaan", 10.4), ("we", 10.8))
    lines = pipeline.text_from_words(words)
    assert [line["text"] for line in lines] == ["ik zie de zon", "wij lopen",
                                                "daar gaan we"]
    assert [line["block"] for line in lines] == [0, 0, 1]
    assert lines[0]["start"] == 1.0 and lines[0]["end"] == 2.5
    assert pipeline.text_file_of(lines) == \
        "ik zie de zon\nwij lopen\n\ndaar gaan we\n"


def test_a_long_line_is_cut_even_without_a_pause() -> None:
    from modules import pipeline

    words = [(f"w{n}", n * 0.35, n * 0.35 + 0.3) for n in range(30)]
    lines = pipeline.text_from_words(words)
    assert all(len(line["text"].split()) <= pipeline._LINE_MAX_WORDS
               for line in lines)
    assert sum(len(line["text"].split()) for line in lines) == 30


def _full_context(tmp_path, monkeypatch, texts: bool = False):
    from modules import pipeline
    from modules.whisper import Segment, Word
    from tests.test_front_to_back import _install

    root, _context = _install(tmp_path, songs=("Song_A",))
    context = pipeline.context_for_project(_context, "Song_A")
    folder = context.paths.input_dir
    if not texts:
        (folder / "lyrics.txt").unlink()
    calls: list = []

    def make(ctx):
        calls.append("karaoke")
        (folder / "karaoke.mp3").write_bytes(b"mp3")
        return folder / "karaoke.mp3"

    monkeypatch.setattr(pipeline, "make_karaoke_from_original", make)
    monkeypatch.setattr(pipeline, "detect_track",
                        lambda ctx, track, progress=None, cancelled=None:
                        calls.append(("detect",
                                      (folder / "lyrics.txt").exists())))
    heard = [Segment(0, "ik zie zon", 0.0, 3.0,
                     (Word("ik", 1.0, 1.2, 0.9), Word("zie", 1.4, 1.6, 0.9),
                      Word("zon", 2.0, 2.4, 0.9))),
             Segment(1, "daar", 8.0, 9.0, (Word("daar", 8.0, 8.5, 0.9),))]
    monkeypatch.setattr(pipeline, "load_segments",
                        lambda ctx, track, heard_=True: tuple(heard))
    return pipeline, context, calls


def test_full_karaoke_makes_a_text_of_what_was_heard(tmp_path,
                                                     monkeypatch) -> None:
    pipeline, context, calls = _full_context(tmp_path, monkeypatch)
    path = pipeline.normal_karaoke_start(context)
    folder = context.paths.input_dir
    assert path.read_text(encoding="utf-8") == "ik zie zon\n\ndaar\n"
    assert (folder / "lyrics.txt").read_text(encoding="utf-8") == \
        "ik zie zon\n\ndaar\n"
    assert pipeline.own_text(context)
    assert context.store.get_meta("own_text_times") == [
        [1.0, 2.4, "ik zie zon"], [8.0, 8.5, "daar"]]
    assert calls == ["karaoke", ("detect", False)], "heard without a hint"
    assert pipeline.full_karaoke_heard(context)


def test_full_karaoke_sets_the_old_texts_aside_first(tmp_path,
                                                     monkeypatch) -> None:
    pipeline, context, calls = _full_context(tmp_path, monkeypatch,
                                             texts=True)
    folder = context.paths.input_dir
    old = (folder / "lyrics.txt").read_text(encoding="utf-8")
    assert pipeline.has_texts(context)
    pipeline.normal_karaoke_start(context)
    assert (folder / ("lyrics.txt" + pipeline.SET_ASIDE_SUFFIX)).read_text(
        encoding="utf-8") == old
    assert ("detect", False) in calls, "the old text is no hint"
    pipeline.forget_own_text(context)
    pipeline.normal_karaoke_start(context)
    assert (folder / ("lyrics.txt" + pipeline.SET_ASIDE_SUFFIX)).read_text(
        encoding="utf-8") == old, "an earlier one is never overwritten"
    assert (folder / ("lyrics.txt" + pipeline.SET_ASIDE_SUFFIX + "2")
            ).exists()


def test_hand_work_on_the_old_texts_lapses(tmp_path, monkeypatch) -> None:
    pipeline, context, _calls = _full_context(tmp_path, monkeypatch,
                                              texts=True)
    context.store.set_step("block_links", {"groups": [[0, 1]]})
    pipeline.normal_karaoke_start(context)
    assert context.store.get_step("block_links") is None


def test_the_checked_text_is_heard_again_then_timed_and_rendered(
        tmp_path, monkeypatch) -> None:
    pipeline, context, calls = _full_context(tmp_path, monkeypatch)
    pipeline.normal_karaoke_start(context)
    order: list = []
    monkeypatch.setattr(pipeline, "invalidate",
                        lambda ctx, changed, keep=(), include_changed=False:
                        order.append(("invalidate", tuple(changed))))
    monkeypatch.setattr(pipeline, "detect_track",
                        lambda ctx, track, progress=None, cancelled=None:
                        order.append("detect"))
    monkeypatch.setattr(pipeline, "generate_timing",
                        lambda ctx: order.append("timing"))
    monkeypatch.setattr(pipeline, "run_video",
                        lambda ctx, progress=None: order.append("video")
                        or Path("video.mp4"))
    pipeline.save_own_text(context, "ik zie de zon\r\n[bg]oh[/bg]\r\n\r\n")
    folder = context.paths.input_dir
    assert (folder / "karaoke_text.txt").read_text(encoding="utf-8") == \
        "ik zie de zon\n[bg]oh[/bg]\n"
    assert pipeline.normal_karaoke_finish(context) == Path("video.mp4")
    assert order == [("invalidate", ("input:lyrics", "input:karaoke_text")),
                     ("invalidate", ("whisper_original",)), "detect",
                     "timing", "video"]


def test_a_text_chosen_by_hand_is_no_longer_the_heard_one(
        tmp_path, monkeypatch) -> None:
    pipeline, context, _calls = _full_context(tmp_path, monkeypatch)
    pipeline.normal_karaoke_start(context)
    pipeline.forget_own_text(context)
    assert not pipeline.own_text(context)


def test_the_gui_wires_the_full_karaoke_and_its_pause() -> None:
    source = (ROOT / "modules" / "gui.py").read_text(encoding="utf-8")
    assert 't("full_karaoke_button")' in source
    assert "normal_karaoke_start" in source and "normal_karaoke_finish" in \
        source and "TextReviewDialog" in source and "save_own_text" in source
    assert "not pipeline.own_text(self._context)" in source, \
        "equal texts are meant to be equal here"
    assert source.count("pipeline.forget_own_text(self._context)") == 2


def test_the_text_check_marks_and_finds_the_line() -> None:
    from modules import text_review

    text = "ik zie de zon\n[crowd]\nhee\n[/crowd]\n\ndaar gaan we\n"
    assert text_review.wrap("abc def", 4, 7, "bg") == ("abc [bg]def[/bg]",
                                                       16)
    assert text_review.line_span(text, 3) == (0, 13)
    assert text_review.sung_index(text, 2) == 0
    assert text_review.sung_index(text, text.index("hee")) == 1
    assert text_review.sung_index(text, text.index("[crowd]") + 1) is None
    assert text_review.sung_index(text, text.index("daar")) == 2
    assert text_review.sung_index(text, text.index("\n\n") + 1) is None


def test_a_line_plays_its_own_heard_time_after_lines_were_added() -> None:
    from modules import text_review

    times = [[1.0, 2.0, "ik zie de zon"], [5.0, 6.0, "daar gaan we"]]
    assert text_review.heard_line("[bg]daar gaan we![/bg]", times, 0) == \
        (5.0, 6.0), "found by its words, not its place"
    assert text_review.heard_line("iets heel anders", times, 1) == (5.0, 6.0)
    assert text_review.heard_line("iets heel anders", times, 7) is None
    assert text_review.heard_line("x", [[1.0, 2.0]], 0) == (1.0, 2.0)


def test_the_text_check_window_opens(qapp_offscreen) -> None:
    from modules import text_review

    dialog = text_review.TextReviewDialog("een\ntwee\n", [[0.0, 1.0]], None)
    dialog._edit.textCursor()
    dialog._mark("bg")
    assert dialog.text().startswith("[bg]een[/bg]")
    assert not dialog._play.isEnabled(), "no audio, nothing to play"
    dialog.reject()


@pytest.fixture
def qapp_offscreen():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# -- 1.5.16 JamendoLyrics -------------------------------------------------------

RECORD = {"text": "one two\nthree\n\nfour five\n",
          "words": [{"text": "one", "start": 1, "end": 1.2},
                    {"text": "two", "start": 1.3, "end": 1.5,
                     "line_end": True},
                    {"text": "three", "start": 2, "end": 2.4,
                     "line_end": True},
                    {"text": "four", "start": 5, "end": 5.3},
                    {"text": "five", "start": 5.4, "end": 5.8,
                     "line_end": True}]}


def test_the_hand_times_of_jamendo_become_a_hand_timing() -> None:
    from modules import jamendo_trial as jt

    lines = jt.hand_lines(RECORD)
    assert [line["text"] for line in lines] == ["one two", "three",
                                                "four five"]
    assert [line["block"] for line in lines] == [0, 0, 1]
    assert lines[0]["syllables"][1] == {"text": " two", "start": 1.3,
                                        "end": 1.5}
    assert jt.lyrics_text(lines) == "one two\nthree\n\nfour five\n"
    assert jt._block_of_lines("a\n\n\nb\nc") == [0, 1, 1]


def test_jamendo_counts_like_1_5_13(monkeypatch) -> None:
    from modules import jamendo_trial as jt

    rows = [{"starts": [1.0, 2.5, 10.0], "hand": [1.1, 2.0, 5.0]}]
    found = jt.figures(rows)
    assert found["lines"] == 3 and found["runaway"] == 1
    assert found["within"] == pytest.approx(100 / 3)
    songs = [{"name": "a", "language": "en"}, {"name": "b", "language": "fr"}]
    text = jt.report_text({"a|baseline|9": rows[0],
                           "b|baseline|9": {"failed": "x"}}, songs, "9")
    assert "| en | 1 | 3 |" in text and "| fr | 0 | 0 |" in text


# -- 1.5.17 MUSDB18 ---------------------------------------------------------------

def test_the_distance_to_the_real_part_is_in_decibels() -> None:
    from modules import musdb_trial as mt

    truth = np.sin(np.linspace(0, 50, 1000))[:, None].repeat(2, axis=1)
    assert mt.sdr(truth, truth) == 100.0
    assert mt.sdr(truth, truth * 0.5) == pytest.approx(6.02, abs=0.01)
    assert mt.sdr(truth, truth[:, :1]) == 100.0, "mono against stereo"
    assert np.isnan(mt.sdr(truth[:0], truth))


def test_musdb_reports_each_way_against_demucs() -> None:
    from modules import musdb_trial as mt

    ways = mt.ways()[:2]
    results = {f"t1|{ways[0].tag}": {"voice": 5.0, "music": 10.0,
                                     "seconds": 3},
               f"t1|{ways[1].tag}": {"voice": 7.0, "music": 12.5,
                                     "seconds": 9}}
    text = mt.report_text(results, ["t1"], ways, [])
    assert "| 1 | 7.00 | 12.50 | +2.50 | 9 | 0 |" in text


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_the_stems_of_a_musdb_file_are_taken_apart(tmp_path) -> None:
    from modules import ffmpeg

    source = tmp_path / "x.stem.mp4"
    inputs = []
    for frequency in (220, 330, 440, 550, 660):
        inputs += ["-f", "lavfi", "-i",
                   f"sine=frequency={frequency}:duration=1:sample_rate=44100"]
    maps = [part for n in range(5) for part in ("-map", str(n))]
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, *maps,
                    "-c:a", "aac", str(source)], check=True)
    out = ffmpeg.extract_stems(source, tmp_path / "t")
    assert all(path.exists() and path.stat().st_size > 1000
               for path in out.values())
