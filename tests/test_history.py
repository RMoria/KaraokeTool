"""The kept versions of the hand work (B568).

``timing.json`` and ``project.json`` hold work that no run can make
again, and both are overwritten in place. ``modules/history.py`` copies
the version that is about to disappear into ``settings/history/`` and
keeps the last ten.

Tested from two sides: the mechanism on its own (what is copied, when
nothing is copied, and that the ring really drops the OLDEST), and the
three places the program makes such a file disappear - the timing
write, the project record, and invalidation, which deletes.

Three of the tests here are about a folder that holds copies of two
files whose names begin the same way. That is not hypothetical:
``timing.json`` and ``timing_auto.json`` lie beside each other in every
project, and the first version of this module matched its own copies
with a glob, so the automatic file pushed the hand work out of its own
ring and switched off the "only when it really differs" rule while it
was at it.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from modules import history


def _file(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class _Clock:
    """A clock that stands still unless a test moves it."""

    def __init__(self) -> None:
        self.now = datetime(2026, 9, 22, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    """Freeze the clock the copies are named after.

    Without this, "two copies in one second" is a test that only tests
    what it says when the two calls happen to fall inside the same
    second, and a settling time can only be tested by waiting.
    """
    ticking = _Clock()

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):           # noqa: D102 - stands in for now()
            return ticking()

    monkeypatch.setattr(history, "datetime", Frozen)
    return ticking


# --------------------------------------------------------------------------
# The mechanism
# --------------------------------------------------------------------------

def test_the_version_that_is_overwritten_is_the_one_that_is_kept(
        tmp_path) -> None:
    """The point of the whole thing: the copy is of the OLD content.

    Called before the write, so what lands in ``history/`` is what the
    user still had. A copy made afterwards would be a copy of the
    damage.
    """
    path = _file(tmp_path / "timing.json", "hand work")

    kept = history.keep_a_copy(path)
    path.write_text("a run went over it", encoding="utf-8")

    assert kept is not None
    assert kept.read_text(encoding="utf-8") == "hand work"
    assert kept.parent == tmp_path / "history"
    assert kept.name.startswith("timing_") and kept.suffix == ".json"


def test_a_first_write_has_nothing_to_keep(tmp_path) -> None:
    """A project that does not exist yet may not leave an empty folder."""
    assert history.keep_a_copy(tmp_path / "timing.json") is None
    assert not (tmp_path / "history").exists()


def test_the_same_content_is_not_kept_twice(tmp_path) -> None:
    """Running the same step again may not push the ring empty.

    Ten copies of an identical automatic timing would cost exactly the
    ten places that a day of hand work needs.
    """
    path = _file(tmp_path / "timing.json", "one")
    assert history.keep_a_copy(path) is not None
    assert history.keep_a_copy(path) is None
    path.write_text("two", encoding="utf-8")
    assert history.keep_a_copy(path) is not None
    assert len(history.copies_of(path)) == 2


def test_the_eleventh_pushes_the_oldest_out(tmp_path, clock) -> None:
    """Ten per file, oldest first out - and the newest ten are kept."""
    path = _file(tmp_path / "timing.json", "version 0")
    for number in range(1, 13):
        history.keep_a_copy(path)
        path.write_text(f"version {number}", encoding="utf-8")

    copies = history.copies_of(path)
    assert len(copies) == history.KEEP
    assert [item.read_text(encoding="utf-8") for item in copies] == [
        f"version {number}" for number in range(2, 12)]


def test_the_order_holds_past_the_ring(tmp_path, clock) -> None:
    """Which copy is the oldest is read out of the names.

    Sixteen copies inside one second is what the ring has to survive.
    Two things break the plain sort order: ``_10`` sorts before ``_2``,
    and the bare name (the first copy of that second) comes free again
    once the ring has dropped it - after which the YOUNGEST copy has
    the name that sorts first. Both of them make the ring throw away
    the newest work instead of the oldest.
    """
    path = _file(tmp_path / "timing.json", "version 0")
    for number in range(1, 17):
        history.keep_a_copy(path)
        path.write_text(f"version {number}", encoding="utf-8")

    held = [item.read_text(encoding="utf-8")
            for item in history.copies_of(path)]
    assert held == [f"version {number}" for number in range(6, 16)]


def test_two_copies_in_one_second_do_not_overwrite_each_other(
        tmp_path, clock) -> None:
    """The name carries seconds, and a step writes faster than that."""
    path = _file(tmp_path / "timing.json", "one")
    first = history.keep_a_copy(path)
    path.write_text("two", encoding="utf-8")
    second = history.keep_a_copy(path)

    assert first != second
    assert first.read_text(encoding="utf-8") == "one"
    assert second.read_text(encoding="utf-8") == "two"


# --------------------------------------------------------------------------
# One folder, two files whose names begin the same way
# --------------------------------------------------------------------------

def test_the_automatic_timing_has_a_ring_of_its_own(tmp_path,
                                                    clock) -> None:
    """``timing_auto.json`` may not push ``timing.json`` out.

    They lie in one folder and therefore share one ``history/``. The
    automatic file is rebuilt on every timing run, so if its copies
    counted as copies of ``timing.json`` the hand work would be the
    first thing gone - twelve automatic runs and an evening of
    dragging is out of the ring.
    """
    hand = _file(tmp_path / "timing.json", "hand work")
    auto = _file(tmp_path / "timing_auto.json", "auto 0")
    history.keep_a_copy(hand)
    for number in range(1, 15):
        history.keep_a_copy(auto)
        auto.write_text(f"auto {number}", encoding="utf-8")

    assert [item.read_text(encoding="utf-8")
            for item in history.copies_of(hand)] == ["hand work"]
    assert len(history.copies_of(auto)) == history.KEEP


def test_the_neighbour_does_not_switch_off_the_content_check(
        tmp_path, clock) -> None:
    """And it may not make the hand work look changed either.

    "Only when it really differs" is a comparison against the youngest
    copy. Pick the wrong youngest - a copy of the neighbouring file -
    and every save writes a new copy, which empties the ring just as
    thoroughly as the eviction above.
    """
    hand = _file(tmp_path / "timing.json", "hand work")
    auto = _file(tmp_path / "timing_auto.json", "auto")
    history.keep_a_copy(hand)
    history.keep_a_copy(auto)

    assert history.keep_a_copy(hand) is None
    assert len(history.copies_of(hand)) == 1


def test_each_file_has_a_ring_of_its_own(tmp_path, clock) -> None:
    """``project.json`` may not push ``timing.json`` out of the folder."""
    timing = _file(tmp_path / "timing.json", "hand work")
    project = _file(tmp_path / "project.json", "{}")
    history.keep_a_copy(timing)
    for number in range(history.KEEP + 3):
        history.keep_a_copy(project)
        project.write_text(json.dumps({"n": number}), encoding="utf-8")

    assert len(history.copies_of(timing)) == 1
    assert history.copies_of(timing)[0].read_text(
        encoding="utf-8") == "hand work"


# --------------------------------------------------------------------------
# The settling time, for a file that is written continuously
# --------------------------------------------------------------------------

def test_the_settling_time_keeps_the_state_the_run_started_on(
        tmp_path, clock) -> None:
    """``project.json`` is written by every step; not every one is kept."""
    path = _file(tmp_path / "project.json", "as the user left it")
    assert history.keep_a_copy(path, settle=history.SETTLE_S) is not None
    for number in range(5):
        clock.now += timedelta(seconds=60)
        path.write_text(f"step {number}", encoding="utf-8")
        assert history.keep_a_copy(path, settle=history.SETTLE_S) is None

    copies = history.copies_of(path)
    assert len(copies) == 1
    assert copies[0].read_text(encoding="utf-8") == "as the user left it"


def test_work_done_later_in_the_run_is_kept_too(tmp_path, clock) -> None:
    """After the settling time the next change IS kept.

    This is what the settling time is for and not against: an
    afternoon of pinning is a hundred writes of the same file, and a
    rule of "once per program start" would keep none of it.
    """
    path = _file(tmp_path / "project.json", "as the user left it")
    history.keep_a_copy(path, settle=history.SETTLE_S)
    path.write_text("an hour of pinning", encoding="utf-8")
    clock.now += timedelta(seconds=history.SETTLE_S + 1)

    kept = history.keep_a_copy(path, settle=history.SETTLE_S)

    assert kept is not None
    assert kept.read_text(encoding="utf-8") == "an hour of pinning"
    assert len(history.copies_of(path)) == 2


# --------------------------------------------------------------------------
# Hooked in where the files really disappear
# --------------------------------------------------------------------------

def test_saving_a_timing_keeps_the_previous_one(tmp_path) -> None:
    """Every timing write in the program goes through ``save_timing``."""
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton, save_timing

    lines = generate_skeleton(
        (TextLine(index=0, text="a line", crowd=False, block=0),),
        {0: (1.0, 2.0)})
    path = tmp_path / "settings" / "timing.json"
    save_timing(lines, path, project="Song_A", version="0.1")
    first = path.read_text(encoding="utf-8")
    save_timing(lines, path, project="Song_A", version="0.2")

    copies = history.copies_of(path)
    assert len(copies) == 1
    assert copies[0].read_text(encoding="utf-8") == first
    assert "0.2" in path.read_text(encoding="utf-8")


def test_a_backup_that_fails_does_not_stop_the_timing_write(
        tmp_path, monkeypatch) -> None:
    """The net may never be the thing that breaks the save.

    A full disk, a folder someone has open, a read-only output folder:
    all of that has to cost the copy and nothing else. Driven through
    ``save_timing``, because that is where it would cost the user his
    work and not only his copy.
    """
    from modules.karaoke_text import TextLine
    from modules.timing import generate_skeleton, save_timing

    def refuse(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(history.shutil, "copy2", refuse)
    lines = generate_skeleton(
        (TextLine(index=0, text="a line", crowd=False, block=0),),
        {0: (1.0, 2.0)})
    path = tmp_path / "settings" / "timing.json"
    save_timing(lines, path, project="Song_A", version="0.1")
    save_timing(lines, path, project="Song_A", version="0.2")

    assert "0.2" in path.read_text(encoding="utf-8")
    assert history.copies_of(path) == []


def test_saving_the_project_record_keeps_the_previous_one(
        tmp_path) -> None:
    """And the record that every step writes, on the first save."""
    from modules.filesystem import ProjectStore

    path = tmp_path / "settings" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"created": "yesterday", "steps": {}}),
                    encoding="utf-8")

    store = ProjectStore(path)
    store.set_step("whisper_original", {"segments": 1})
    store.set_step("word_coupling", {"pins": {}})

    copies = history.copies_of(path)
    assert len(copies) == 1
    assert json.loads(copies[0].read_text(encoding="utf-8")) == {
        "created": "yesterday", "steps": {}}


def test_invalidation_keeps_the_timing_it_deletes(tmp_path) -> None:
    """The cheapest way to lose the hand work is not a write at all.

    ``invalidate_timing`` removes ``timing.json`` when the karaoke text
    changes structurally. Before B568 that left nothing behind.
    """
    from modules import pipeline
    from modules.config import default_config
    from modules.filesystem import (ProjectPaths, ProjectStore,
                                    ensure_directories)

    paths = ProjectPaths(root=tmp_path, song="Song_A")
    ensure_directories(paths)
    context = pipeline.AppContext(paths=paths, config=default_config(),
                                  store=ProjectStore(paths.project_file))
    paths.timing_file.write_text("hand work", encoding="utf-8")

    pipeline.invalidate_timing(context)

    assert not paths.timing_file.exists()
    copies = history.copies_of(paths.timing_file)
    assert len(copies) == 1
    assert copies[0].read_text(encoding="utf-8") == "hand work"
