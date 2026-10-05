"""v1.0.25: the yardstick measures every song again, a fallen pool no
longer stops a test, and 1.5.14 is done.

* B671: the yardstick took only songs with ``original/segments.json`` -
  since the rename of B558 one of the owner's 22 - although it measures
  on the cache first; now the cache is enough, and the old name counts;
* B672: a process pool on the laptop that falls over sends its rounds
  back into the queue and the test goes on without it.
"""
from __future__ import annotations

import importlib.util
import json
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from modules import test_panel
from modules import work_queue as wq

ROOT = Path(__file__).resolve().parents[1]


def _regression():
    spec = importlib.util.spec_from_file_location(
        "timing_regression_v1025", ROOT / "tools" / "timing_regression.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project(root: Path, song: str = "Song") -> Path:
    out = root / "output" / song
    (out / "settings").mkdir(parents=True)
    (out / "settings" / "project.json").write_text(
        json.dumps({"steps": {}}), encoding="utf-8")
    (root / "input" / song).mkdir(parents=True)
    (root / "input" / song / "lyrics.txt").write_text("la la\n",
                                                       encoding="utf-8")
    return out


def test_the_cache_is_enough_for_the_yardstick(tmp_path) -> None:
    regression = _regression()
    project = _project(tmp_path / "inst")
    assert regression._build_project(project, tmp_path / "w1") is None, \
        "nothing to measure on"
    cache = tmp_path / "inst" / "cache" / "Song"
    cache.mkdir(parents=True)
    (cache / "transcription_original.json").write_text("[]",
                                                       encoding="utf-8")
    assert regression._build_project(project, tmp_path / "w2") is not None
    assert regression.SOURCE["Song"] == "cache"


def test_the_old_name_of_the_segments_counts(tmp_path) -> None:
    regression = _regression()
    project = _project(tmp_path / "inst")
    (project / "original").mkdir()
    (project / "original" / "segmenten.json").write_text("[]",
                                                         encoding="utf-8")
    assert regression._build_project(project, tmp_path / "w") is not None
    assert regression.SOURCE["Song"] == "ruw"


class _BrokenPool:
    def submit(self, *args, **kwargs):
        raise BrokenProcessPool("a child process terminated abruptly")

    def shutdown(self, wait=True, cancel_futures=False):
        pass


def test_a_fallen_pool_does_not_stop_the_test(tmp_path, monkeypatch) -> None:
    queue = wq.Queue(tmp_path / "kt_work").ensure()
    monkeypatch.setattr(wq, "_pool", lambda lanes: _BrokenPool())
    # v1.0.26 (B674): after the break every round gets a fresh process of
    # its own; here that is the round itself.
    monkeypatch.setattr(wq, "_isolated_round",
                        lambda job, queue: {"ok": job["id"]})
    jobs = [{"id": wq.job_id(key), "kind": "k", "class": "c",
             "needs": [], "label": key, "payload": {"key": key}}
            for key in ("a", "b")]
    answers = []
    counts = wq.run_jobs(
        queue, jobs, "1.0", {"k": lambda job, q, stop: {"ok": job["id"]}},
        answers.append, lambda: False, local_lanes=2, poll_s=1,
        sleep=lambda s: None)
    assert len(answers) == 2 and counts["local"] == 2, \
        "this computer goes on, one round at a time"
    assert all(a["result"].get("ok") for a in answers)


def test_1_5_14_is_done() -> None:
    action = [a for a in test_panel.ACTIONS if a.code == "1.5.14"][0]
    # v1.0.28: on again, for the Demucs blend with Roformer clean music.
    assert not action.done and callable(action.function)
    assert "1.5.14" in [a.code for a in test_panel.visible_actions()]
