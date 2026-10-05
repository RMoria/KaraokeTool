"""v1.0.27: what the tests of 5 October said, and why they had gaps.

* 1.5.19 is done (no stem model helped); 1.5.15 and 1.5.20 lose their
  B605 rounds (measured: worse);
* B651 moved nothing: its anchors were qualities the coupling never
  gives - now ``high``;
* a report names its rounds without a measurement, and compares the
  rounds on only the songs every round measured;
* a round whose process dies on the laptop goes to a helper, and the
  processes of the pool write into the crash log.
"""
from __future__ import annotations

import json

from modules import block_trial, lyrics_trial, pipeline, test_panel
from modules import work_queue as wq
from modules.translations import t


def test_what_is_done_is_off() -> None:
    action = [a for a in test_panel.ACTIONS if a.code == "1.5.19"][0]
    assert action.done
    assert not any("B605" in v.on for v in block_trial.VARIANTS)
    assert not any("B605" in v.on for v in lyrics_trial.VARIANTS)
    assert all(block_trial.needs_of(v) == ["ffmpeg"]
               for v in block_trial.VARIANTS)


def test_b651_finds_anchors_at_the_coupling() -> None:
    from modules.timing import Syllable, TimedLine

    def line(index, start, quality):
        return TimedLine(index=index, text="la la", crowd=False,
                         syllables=(Syllable("la", start, start + 0.4),
                                    Syllable(" la", start + 0.5,
                                             start + 0.9)),
                         quality=quality)

    timed = (line(0, 1.0, "high"), line(1, 4.0, "low"),
             line(2, 8.0, "high"))
    found = pipeline.stretches(timed, [0, 1, 2])
    assert found == [([1], timed[0].end, timed[2].start)]
    assert pipeline._fits([timed[1]], found[0][1], found[0][2])


def _answer(variant, song, result, worker="Pav-mixed"):
    return {"job": {"payload": {"variant": variant, "song": song}},
            "result": result, "worker": worker}


def test_a_report_names_its_gaps_and_compares_fairly() -> None:
    missing: dict = {}
    block_trial.note_missing(missing, _answer("B602", "Lied R",
                                              {"failed": "boom"}))
    results = [(block_trial.Variant("baseline", ()),
                {"songs": {"A": 1.0, "B": 3.0}}),
               (block_trial.Variant("B602", ("B602",)),
                {"songs": {"A": 0.5}})]
    text = block_trial.coverage_text(results, missing)
    assert "baseline 1.00" in text and "B602 0.50" in text, \
        "only song A, which both measured"
    assert t("trial_missing_head") in text
    assert "| B602 | Lied R | Pav-mixed | boom |" in text
    assert block_trial.coverage_text([], {}) == ""


def test_a_crashed_round_goes_to_a_helper(tmp_path, monkeypatch) -> None:
    queue = wq.Queue(tmp_path / "kt_work").ensure()
    (queue.workers / "Pav-mixed.json").write_text(json.dumps(
        {"worker": "Pav-mixed", "host": "Pav", "can": ["ffmpeg"],
         "state": "working"}), encoding="utf-8")
    monkeypatch.setattr(wq, "_pool", lambda lanes: None)
    tries = []

    def isolated(job, q):
        tries.append(job["id"])
        return {"failed": "gone", "crashed": True}

    monkeypatch.setattr(wq, "_isolated_round", isolated)
    released = []
    real = wq.Queue.release

    def release(self, job, count_try=True):
        released.append((job["id"], count_try))
        return real(self, job, count_try)

    monkeypatch.setattr(wq.Queue, "release", release)
    jobs = [{"id": wq.job_id(k), "kind": "k", "class": "c",
             "needs": ["ffmpeg"], "label": k, "payload": {}}
            for k in ("a", "b")]
    stop = {"n": 0}

    def cancelled():
        stop["n"] += 1
        return stop["n"] > 40

    wq.run_jobs(queue, jobs, "1.0", {"k": lambda job, q, s: {}},
                lambda answer: None, cancelled, local_lanes=2, poll_s=1,
                sleep=lambda s: None, stuck_s=10_000)
    assert len(tries) == 1, "after one crash this computer takes no more"
    assert released[0] == (tries[0], False)


def test_the_pool_writes_into_the_crash_log(tmp_path, monkeypatch) -> None:
    log = tmp_path / "crash.log"
    monkeypatch.setenv("KT_CRASH_LOG", str(log))
    import faulthandler

    was = faulthandler.is_enabled()
    try:
        wq._child_start()
        assert "child pid" in log.read_text(encoding="utf-8")
    finally:
        faulthandler.disable()
        if was:
            faulthandler.enable()
        if wq._CHILD_CRASH_FILE is not None:
            wq._CHILD_CRASH_FILE.close()
            wq._CHILD_CRASH_FILE = None
