"""Tests for v0.126.0: B394 and B395 - two bugs the profiler found.

Both came out of one question from the user: why does 1.5.10 ask so
little of this computer? The task manager said 15% of a machine with ten
cores, which is one core's worth of work. The obvious answer was
multiprocessing. The profiler gave a better one.

B395: ``cluster._fold_repeats`` is called 636,028 times per yardstick
measurement with 307 distinct inputs - the same word folded two thousand
times over. It is a pure string function, so one ``lru_cache`` line takes
a measurement from 2.44 s to 0.426 s. A factor 5.7 for ten characters,
where four worker processes would have given three or four at the cost of
a Windows multiprocessing harness. And it is not only the test panel: the
coupling runs whenever the user presses 1.3.

B394 came out of reading the results of that same run. The measurement
history had shrunk to nine keys - the per-action totals plus four of the
fourteen projects of 1.5.8, with everything from 1.5.5, 1.5.6 and 1.5.7
gone. ``remember`` does a read-modify-write of the whole file and
``across_projects`` runs two worker threads, with no lock anywhere. The
second writer loads its snapshot before the first has saved and then
saves it back over the top. B362 exists to compare against previous
versions; that only works if the previous versions survive.
"""
from __future__ import annotations

import json
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules import cluster, test_history  # noqa: E402


# --------------------------------------------------------------------------
# B395 - the same word folded two thousand times
# --------------------------------------------------------------------------

def test_folding_is_cached() -> None:
    assert hasattr(cluster._fold_repeats, "cache_info")


def test_the_cache_is_bounded() -> None:
    """Unlimited would grow for as long as the program runs; 307 entries
    cover a whole measurement, so the ceiling is far above need."""
    assert cluster._fold_repeats.cache_info().maxsize >= 100_000


def test_folding_still_folds() -> None:
    """A cache may never change an answer - so pin the answers."""
    cluster._fold_repeats.cache_clear()
    assert cluster._fold_repeats("ketenketen") == "keten"
    assert cluster._fold_repeats("ketenketenk") == "keten"
    assert cluster._fold_repeats("keten") == "keten"
    assert cluster._fold_repeats("") == ""


def test_the_second_call_is_a_hit_and_gives_the_same_answer() -> None:
    cluster._fold_repeats.cache_clear()
    first = cluster._fold_repeats("lalalala")
    before = cluster._fold_repeats.cache_info().hits
    second = cluster._fold_repeats("lalalala")
    assert first == second
    assert cluster._fold_repeats.cache_info().hits == before + 1


def test_the_function_is_pure_and_may_therefore_be_cached() -> None:
    """The licence for the cache. Takes a string, returns a string,
    touches nothing else - so the same input cannot mean two answers."""
    import inspect

    source = inspect.getsource(cluster._fold_repeats.__wrapped__)
    for forbidden in ("global ", "self.", "random", "time.", "open("):
        assert forbidden not in source, forbidden


# --------------------------------------------------------------------------
# B394 - two work slots, one file, no lock
# --------------------------------------------------------------------------

def test_writing_the_history_is_locked() -> None:
    assert isinstance(test_history._WRITE_LOCK, type(threading.Lock()))


def test_two_threads_do_not_overwrite_each_other(tmp_path,
                                                 monkeypatch) -> None:
    """The regression itself. Two work slots writing at the same time
    used to lose entries; the run of v0.125.0 kept four of fourteen
    projects for 1.5.8 and nothing at all for 1.5.5 to 1.5.7."""
    monkeypatch.setattr(test_history, "HISTORY_FILE",
                        tmp_path / "testhistorie.json")
    songs = [f"Lied{n:02d}" for n in range(40)]
    start = threading.Event()

    def write(song: str) -> None:
        start.wait()
        test_history.remember("1.5.5", song, "0.126.0", "vinger",
                              {"project": song})

    threads = [threading.Thread(target=write, args=(s,)) for s in songs]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join()

    kept = json.loads(
        (tmp_path / "testhistorie.json").read_text(encoding="utf-8"))
    missing = [s for s in songs if f"1.5.5|{s}" not in kept]
    assert not missing, f"kwijtgeraakt: {missing}"


def test_a_result_survives_a_second_writer(tmp_path, monkeypatch) -> None:
    """Not just the key: the content has to be the right one."""
    monkeypatch.setattr(test_history, "HISTORY_FILE",
                        tmp_path / "testhistorie.json")
    test_history.remember("1.5.7", "Eerste", "0.126.0", "a", {"n": 1})
    test_history.remember("1.5.7", "Tweede", "0.126.0", "b", {"n": 2})
    assert test_history.lookup("1.5.7", "Eerste", "0.126.0", "a") == {"n": 1}
    assert test_history.lookup("1.5.7", "Tweede", "0.126.0", "b") == {"n": 2}


def test_the_lock_is_named_as_thread_only(tmp_path) -> None:
    """A thread lock is enough for one process. Spreading the
    measurement over PROCESSES is on the list, and would need a file
    lock - so that has to be written down where the next reader looks."""
    import inspect

    source = inspect.getsource(test_history)
    where = source.index("_WRITE_LOCK = ")
    assert "proces" in source[max(0, where - 900):where].lower()
