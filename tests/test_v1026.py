"""v1.0.26 (B674): the program no longer falls over on the aligner.

* rounds that need WhisperX are left to a helper that has it;
* a round meant for a process of its own never runs inside the program,
  also not after the pool fell over - a crash costs the round;
* a native crash leaves its stacks in ``logs/crash.log``.
"""
from __future__ import annotations

import json
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from modules import work_queue as wq

ROOT = Path(__file__).resolve().parents[1]


def _worker(queue: wq.Queue, name: str, can) -> None:
    queue.ensure()
    (queue.workers / f"{name}.json").write_text(
        json.dumps({"worker": name, "can": list(can)}), encoding="utf-8")


def test_the_aligner_is_left_to_a_helper(tmp_path) -> None:
    queue = wq.Queue(tmp_path / "kt_work").ensure()
    local = {"ffmpeg", "whisper", "whisperx"}
    assert wq.program_capabilities(queue, local) == local, \
        "nobody else has it: the program keeps it"
    _worker(queue, f"Laptop-{wq.OWN_LANE}", ["whisperx"])
    assert "whisperx" in wq.program_capabilities(queue, local), \
        "the program's own status is no helper"
    _worker(queue, "Pav-mixed", ["ffmpeg", "whisperx"])
    assert wq.program_capabilities(queue, local) == {"ffmpeg", "whisper"}


class _Future:
    def result(self):
        raise BrokenProcessPool("a child process terminated abruptly")


class _CrashingPool:
    def submit(self, *args, **kwargs):
        return _Future()

    def shutdown(self, wait=True, cancel_futures=False):
        pass


def test_a_crashing_round_costs_the_round(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wq, "_pool", lambda lanes: _CrashingPool())
    queue = wq.Queue(tmp_path / "kt_work").ensure()
    answer = wq._isolated_round({"kind": "k", "id": "x"}, queue)
    assert "failed" in answer


def test_no_round_of_a_pool_runs_in_the_program(tmp_path,
                                                monkeypatch) -> None:
    class _Broken:
        def submit(self, *args, **kwargs):
            raise BrokenProcessPool("gone")

        def shutdown(self, wait=True, cancel_futures=False):
            pass

    queue = wq.Queue(tmp_path / "kt_work").ensure()
    monkeypatch.setattr(wq, "_pool", lambda lanes: _Broken())
    isolated = []
    monkeypatch.setattr(wq, "_isolated_round",
                        lambda job, q: isolated.append(job["id"]) or {})
    inside = []
    jobs = [{"id": wq.job_id("a"), "kind": "k", "class": "c", "needs": [],
             "label": "a", "payload": {}}]
    wq.run_jobs(queue, jobs, "1.0",
                {"k": lambda job, q, stop: inside.append(1) or {}},
                lambda answer: None, lambda: False, local_lanes=2,
                poll_s=1, sleep=lambda s: None)
    assert isolated and not inside


def test_the_program_keeps_a_crash_log() -> None:
    text = (ROOT / "KaraokeTool.py").read_text(encoding="utf-8")
    assert "faulthandler.enable(" in text and "crash.log" in text
    assert "_install_crash_log(paths.logs_dir)" in text
