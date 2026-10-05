"""Work shared out over the computers in the owner's network (v1.0.18).

The long tests ran on one laptop: 1.5.14 was five days of separating
and listening. The owner has more computers, one with an NVIDIA card,
and a shared folder on the laptop (``\\\\10.0.0.18\\Tools``). This is
the simplest thing that lets them all help: a folder of small jobs.

The laptop (the program, running a test) puts every round of the test
in ``kt_work/jobs`` as one JSON file, with the files it needs next to
it. Any computer running the helper (``tools/helper.py``) - the laptop
itself too - takes one by moving it to ``claimed``, works on it, writes
the answer to ``done`` and takes the next; with nothing to do it waits
until something comes. The laptop gathers the answers into the test as
if it had worked them out itself.

Why a folder and not a server: it needs nothing but the share the owner
already has - no port to open, no service to install, nothing that
talks over the network except Windows file sharing - and every step
leaves a file that can be looked at.

The rules that make it safe:

* **one job, one worker.** Taking a job is a rename, and a rename of a
  file that is already gone fails, so of two computers reaching for
  the same job one gets it and the other takes the next.
* **nothing is lost.** A worker that is working says so every
  :data:`HEARTBEAT_S` seconds, by counting up in a file next to its
  job. The laptop watches that count on its own clock (the computers'
  clocks need not agree): when it has not moved for :data:`STALE_S`,
  the job goes back into the queue. A worker that is stopped puts its
  job back itself.
* **one version.** A job carries the version of the program that made
  it, and a worker only takes a job of its own version: the helper
  fetches the program from the share at every start, so when the
  laptop has a newer version the helper stops, fetches it and starts
  again (exit code :data:`UPDATE_EXIT`).

Standard library only, so a helper that has nothing else yet can read
it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import socket
import threading
import time
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

#: The queue folder's name.
QUEUE_NAME = "kt_work"
#: v1.0.23 (B650): the queue folder lives in the program's ``helper``
#: folder, next to ``install_helper.bat`` (the owner's choice), not next
#: to the program folder in ``Tools``. Helpers of v1.0.20 to v1.0.22 still
#: work in the old place for a while: the program reads their answers
#: from it and tells them to update (see :class:`_Legacy`).
QUEUE_HOME = "helper"
#: How often a working worker says it is still at it. v1.0.28 (B665): the
#: owner's numbers - a sign every five minutes, and half an hour without
#: one counts as stopped: a long round on a busy share was put back while
#: its helper still worked on it.
HEARTBEAT_S = 300.0
#: A claimed job whose worker has not said anything for this long goes
#: back into the queue.
STALE_S = 1800.0
#: v1.0.28: how often a working worker writes its status (what it does,
#: how long it still takes) - between two signs, for the count and the
#: end time on the laptop.
STATUS_S = 30.0
#: A worker's status older than this: it is gone.
WORKER_FRESH_S = 120.0
#: How long a worker with nothing to do waits before it looks again.
IDLE_S = 15.0
#: Between two looks of the program longer than this, the counts start
#: afresh (see :meth:`Queue.requeue_stale`).
_LOOK_GAP_S = 60.0
#: The exit code of a helper that needs the newer program from the share.
UPDATE_EXIT = 3
#: v1.0.28 (B666): the program's sign that the helpers may stop once
#: there is nothing left for them.
STOP_HELPERS = "stop_helpers.json"


#: A job that took its worker down this often is answered as failed
#: instead of taking the next one down too.
MAX_TRIES = 3


def version_key(version: str) -> tuple:
    """``"1.0.18"`` -> ``(1, 0, 18)``, to tell newer from older."""
    return tuple(int(part) if part.isdigit() else 0
                 for part in str(version).split("."))


def host_name() -> str:
    return socket.gethostname() or "pc"


def job_id(key: str) -> str:
    """A job's id from what it measures, so the same round is never in
    the queue twice."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _plain(value):
    """What json cannot write itself: numbers of numpy, sets, paths."""
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    return str(value)


def _write_json(path: Path, data) -> None:
    """Write whole or not at all: a reader on another computer never
    sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    spare = path.with_name(path.name + f".{os.getpid()}.tmp")
    spare.write_text(json.dumps(data, ensure_ascii=False, default=_plain),
                     encoding="utf-8")
    os.replace(spare, path)


def _text(key: str) -> str:
    """A text of the translation table; the key itself where there is
    none (this module also runs where only the standard library is)."""
    try:
        from .translations import t

        return t(key)
    except Exception:  # noqa: BLE001 - a helper without texts
        return key


def queue_folder(program: Path | str) -> Path:
    """The queue folder of the program folder ``program`` (on the laptop
    or, from a helper, on the share): ``helper\\kt_work`` in it
    (v1.0.23, B650)."""
    return Path(program) / QUEUE_HOME / QUEUE_NAME


def old_queue_folder(root: Path | str) -> Path | None:
    """Where the queue was up to v1.0.22 - next to the program folder -
    seen from the queue folder ``root`` of now; ``None`` for a queue that
    is not in a program's helper folder."""
    root = Path(root)
    if root.parent.name.lower() != QUEUE_HOME:
        return None
    return root.parent.parent.parent / QUEUE_NAME


def queue_for(context) -> "Queue":
    """The work queue of an installation: in the program's helper folder,
    on the share, where the helpers find it (v1.0.18; v1.0.23 there)."""
    return Queue(queue_folder(context.paths.root))


def data_root(queue: "Queue") -> Path:
    """Where the test data sets (JamendoLyrics, MUSDB18) are kept, next
    to the queue and never cleared with it."""
    return queue.root.parent / "kt_data"


def accept_for(capabilities, handlers) -> Callable[[dict], bool]:
    """A worker takes a job whose kind it knows and whose ``needs``
    (``demucs``, ``roformer``, ...) it has."""
    have = set(capabilities)

    def accept(job: dict) -> bool:
        return job.get("kind") in handlers and \
            set(job.get("needs") or ()) <= have

    return accept


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@dataclass
class Queue:
    """The queue folder and what can be done with it."""

    root: Path

    @property
    def jobs(self) -> Path:
        return self.root / "jobs"

    @property
    def claimed(self) -> Path:
        return self.root / "claimed"

    @property
    def done(self) -> Path:
        return self.root / "done"

    @property
    def files(self) -> Path:
        return self.root / "files"

    @property
    def workers(self) -> Path:
        return self.root / "workers"

    def ensure(self) -> "Queue":
        for folder in (self.jobs, self.claimed, self.done, self.files,
                       self.workers, self.root / "out"):
            folder.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def speeds_path(self) -> Path:
        return self.root / "speeds.json"

    def read_speeds(self) -> dict:
        """Per worker per class of job: ``[total seconds, rounds]``."""
        data = _read_json(self.speeds_path)
        return data if isinstance(data, dict) else {}

    def note_speed(self, worker: str, cls: str, seconds) -> None:
        """How long a round of this class took this worker (the program
        writes this, alone, from the answers it takes over)."""
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            return
        if not worker or seconds <= 0:
            return
        data = self.read_speeds()
        total, count = data.setdefault(worker, {}).get(cls, [0.0, 0])
        data[worker][cls] = [total + seconds, count + 1]
        try:
            _write_json(self.speeds_path, data)
        except OSError:
            pass

    def write_where(self) -> None:
        """Who holds this queue: the name and addresses of the computer,
        so a helper can find it again when its address changes."""
        host = host_name()
        addresses = []
        try:
            addresses = sorted(set(socket.gethostbyname_ex(host)[2]))
        except OSError:
            pass
        try:
            from .translations import current_language
            language = current_language()
        except Exception:  # noqa: BLE001 - a helper without texts
            language = ""
        try:
            # v1.0.28 (B659): and the language the program speaks, which
            # the helpers follow.
            _write_json(self.root / "laptop.json",
                        {"host": host, "addresses": addresses,
                         "language": language})
        except OSError:
            pass

    def ask_helpers_to_stop(self) -> None:
        """v1.0.28 (B666): the helpers may stop once there is nothing
        left for them - the owner's choice in the test panel, written when
        all rounds of the tests are in."""
        try:
            _write_json(self.root / STOP_HELPERS, {"at": time.time()})
        except OSError:
            pass

    def clear_stop_helpers(self) -> None:
        try:
            (self.root / STOP_HELPERS).unlink()
        except OSError:
            pass

    def helpers_asked_to_stop(self, since: float) -> bool:
        """Was the stop written after ``since`` (this worker's start, on
        the clock of the computer that wrote it - compared on the share's
        file time, so clocks need not agree)?"""
        try:
            return (self.root / STOP_HELPERS).stat().st_mtime > since
        except OSError:
            return False

    def out_dir(self, job: str) -> Path:
        """Where a worker leaves the files a job makes besides its
        answer (listening copies)."""
        return self.root / "out" / job

    # -- the program's side -----------------------------------------------

    def known(self, job: str) -> bool:
        """Is this job waiting, being worked on or answered?"""
        return any((folder / f"{job}.json").exists()
                   for folder in (self.jobs, self.claimed, self.done))

    def publish(self, job: dict) -> bool:
        """Put a job in the queue, unless it is already there. A job of
        the same round still waiting from another version or run is
        replaced: left alone, no worker of today would take it and the
        test would wait for it for ever."""
        waiting = self.jobs / f"{job['id']}.json"
        old = _read_json(waiting) if waiting.exists() else None
        if isinstance(old, dict) and (old.get("version") != job["version"]
                                      or old.get("run") != job.get("run")):
            _write_json(waiting, job)
            return True
        if self.known(job["id"]):
            return False
        _write_json(waiting, job)
        return True

    def withdraw_other_versions(self, kind: str, version: str) -> int:
        """Take out the waiting jobs of this kind made by another version
        of the program (a test that was closed without being stopped)."""
        count = 0
        for path in sorted(self.jobs.glob("*.json")):
            job = _read_json(path)
            if isinstance(job, dict) and job.get("kind") == kind and \
                    job.get("version") != version:
                try:
                    path.unlink()
                    count += 1
                except OSError:
                    pass
        return count

    def referenced(self) -> set[str]:
        """The files the waiting and claimed jobs still need."""
        out = set()
        for folder in (self.jobs, self.claimed):
            for path in folder.glob("*.json"):
                job = _read_json(path)
                if isinstance(job, dict):
                    mix = (job.get("payload") or {}).get("mix")
                    if mix:
                        out.add(Path(mix).parent.as_posix())
        return out

    def withdraw(self, run: str) -> int:
        """Take back the jobs of a run nobody has taken yet (the test was
        stopped). Jobs being worked on finish; their answers are kept for
        the next run."""
        count = 0
        for path in sorted(self.jobs.glob("*.json")):
            job = _read_json(path)
            if job and job.get("run") == run:
                try:
                    path.unlink()
                    count += 1
                except OSError:
                    pass
        return count

    def answers(self) -> list[dict]:
        """Every answer lying in ``done``."""
        out = []
        for path in sorted(self.done.glob("*.json")):
            answer = _read_json(path)
            if isinstance(answer, dict) and "job" in answer:
                out.append(answer)
        return out

    def take_answer(self, job: str) -> None:
        """An answer taken over by the program leaves the queue."""
        for path in (self.done / f"{job}.json",):
            try:
                path.unlink()
            except OSError:
                pass

    def requeue_stale(self, seen: dict, now: float | None = None) -> list[str]:
        """Put back what a worker stopped answering for. ``seen`` is the
        program's memory between calls: per claimed job the last count
        and when (on this clock) it last moved."""
        now = time.monotonic() if now is None else now
        # The program itself was away (the laptop slept, a long round of
        # its own): every count gets a fresh start instead of all jobs
        # looking silent at once.
        last_look = seen.get("__look__")
        if last_look is not None and now - last_look > _LOOK_GAP_S:
            for job in list(seen):
                if job != "__look__":
                    seen[job] = (seen[job][0], now)
        seen["__look__"] = now
        back = []
        present = set()
        for path in sorted(self.claimed.glob("*.json")):
            job = path.stem
            present.add(job)
            beat = _read_json(self.claimed / f"{job}.alive") or {}
            count = beat.get("beat")
            last = seen.get(job)
            if last is None or last[0] != count:
                seen[job] = (count, now)
                continue
            if now - last[1] >= STALE_S and \
                    (self.claimed / f"{job}.answered").exists():
                # A twin gave the answer and the first worker is gone:
                # nothing to put back. While it still beats, the marker
                # stays so that it sees it and stops.
                self._clear_claim(job)
                seen.pop(job, None)
                continue
            if now - last[1] >= STALE_S:
                try:
                    os.replace(path, self.jobs / path.name)
                    back.append(job)
                except OSError:
                    continue
                self._forget_beat(job)
                try:
                    (self.claimed / f"{job}.twin").unlink()
                except OSError:
                    pass
                seen.pop(job, None)
        for job in list(seen):
            if job not in present and job != "__look__":
                seen.pop(job, None)
        return back

    def active_workers(self, fresh_s: float = WORKER_FRESH_S) -> list[dict]:
        """The workers that said something lately, by their own count:
        a worker writes its status every few seconds, and one whose file
        has not changed on the share for ``fresh_s`` is gone. The file
        time is the share's, so clocks need not agree."""
        out = []
        found = []
        for path in sorted(self.workers.glob("*.json")):
            try:
                found.append((path, path.stat().st_mtime))
            except OSError:
                continue
        # On the share's clock: a computer whose own clock runs behind
        # would otherwise take workers that are gone for alive.
        now = max([time.time()] + [moment for _path, moment in found])
        for path, moment in found:
            age = now - moment
            status = _read_json(path)
            if isinstance(status, dict) and age <= fresh_s:
                out.append(status)
        return out

    # -- the worker's side ----------------------------------------------------

    def claim(self, worker: str, version: str,
              accept: Callable[[dict], bool] = lambda job: True
              ) -> tuple[dict | None, bool]:
        """Take the oldest job of this version this worker can do.
        Returns ``(job, newer)``: ``newer`` says a job of a NEWER version
        is waiting - the program on the share is newer than this worker.
        A job of an older version is left for its own program to replace.
        The job comes back with a ``token``: this claim, so that a worker
        whose job was given to another meanwhile does not undo the
        other's claim."""
        newer = False
        mine = version_key(version)
        found = []
        for path in self.jobs.glob("*.json"):
            job = self._waiting_job(path)
            if isinstance(job, dict):
                found.append((-_priority(job), _mtime(path), path.name,
                              path, job))
        # v1.0.21: a round with a priority (a check of a helper) comes
        # before the rounds of a test; otherwise the oldest first.
        for _order, _moment, _name, path, job in sorted(
                found, key=lambda item: item[:3]):
            if job.get("version") != version:
                if version_key(job.get("version", "")) > mine:
                    newer = True
                continue
            if not addressed_to(job, worker) or not accept(job):
                continue
            if self.waits_for_others(job):
                continue
            target = self.claimed / path.name
            try:
                os.rename(path, target)
            except OSError:
                continue            # someone else was first
            job = _read_json(target) or job
            _WAITING.pop(str(path), None)
            # Marks of an earlier claim of the same round (a re-run of it)
            # are not about this claim.
            for suffix in (".answered", ".twin"):
                try:
                    (self.claimed / f"{job['id']}{suffix}").unlink()
                except OSError:
                    pass
            job["tries"] = int(job.get("tries", 0)) + 1
            job["token"] = f"{worker}-{os.getpid()}-{time.time_ns()}"
            try:
                _write_json(target, {key: value for key, value in
                                     job.items() if key != "token"})
            except OSError:
                pass
            self.heartbeat(job["id"], worker, 0, job["token"])
            return job, newer
        return None, newer

    def waits_for_others(self, job: dict) -> bool:
        """v1.0.23: a round that needs the answers of others first (a
        blend, the rounds of its parts - ``after``) waits while one of
        them is still waiting or being worked on."""
        for other in job.get("after") or ():
            name = f"{other}.json"
            try:
                if (self.jobs / name).exists() or \
                        (self.claimed / name).exists():
                    return True
            except OSError:
                return True
        return False

    def _waiting_job(self, path: Path):
        """A waiting job, read once per change: a lane looks at every
        waiting job after each round, and on the share that is a read
        per job."""
        moment = _mtime(path)
        known = _WAITING.get(str(path))
        if known is not None and known[0] == moment:
            return known[1]
        job = _read_json(path)
        if isinstance(job, dict):
            if len(_WAITING) > 5000:
                _WAITING.clear()
            _WAITING[str(path)] = (moment, job)
        return job

    def owns(self, job: dict) -> bool:
        """Is this claim still the worker's own? (Not when the job was
        given to another meanwhile.)"""
        beat = _read_json(self.claimed / f"{job['id']}.alive") or {}
        return beat.get("token") == job.get("token")

    def heartbeat(self, job: str, worker: str, count: int,
                  token: str = "") -> None:
        try:
            _write_json(self.claimed / f"{job}.alive",
                        {"worker": worker, "beat": count, "token": token})
        except OSError:
            pass                    # the share is away for a moment

    def finish(self, job: dict, answer: dict, worker: str,
               device: str) -> None:
        """The answer, and the job out of ``claimed``. A twin (see
        :meth:`claim_twin`) that answered first wins: then this answer
        is dropped."""
        if job.get("twin"):
            self._finish_twin(job, answer, worker, device)
            return
        owned = self.owns(job) if job.get("token") else True
        if owned and not self._win(job["id"], worker):
            self._clear_claim(job["id"])    # a twin answered first
            return
        if not owned and self.answered(job["id"]):
            return
        record = {key: value for key, value in job.items()
                  if key not in ("token", "twin")}
        _write_json(self.done / f"{job['id']}.json",
                    {"job": record, "result": answer, "worker": worker,
                     "device": device})
        if not owned:
            return                  # another took it over; leave theirs
        self._clear_claim(job["id"])

    def answered(self, job: str) -> bool:
        try:
            return (self.claimed / f"{job}.answered").exists()
        except OSError:
            return False            # the share is away for a moment

    def _win(self, job: str, worker: str) -> bool:
        """The one answer of a round that a twin works on too: whoever
        makes the mark first. Made before the answer is written, so two
        answers can never both count."""
        try:
            handle = os.open(self.claimed / f"{job}.answered",
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        except OSError:
            return True             # cannot mark: answer as before
        try:
            os.write(handle, json.dumps({"by": worker}).encode("utf-8"))
        finally:
            os.close(handle)
        return True

    def _finish_twin(self, job: dict, answer: dict, worker: str,
                     device: str) -> None:
        jid = job["id"]
        try:
            (self.claimed / f"{jid}.twin").unlink()
        except OSError:
            pass
        if "failed" in answer or answer.get("cancelled") or \
                not (self.claimed / f"{jid}.json").exists() or \
                not self._win(jid, worker):
            return                  # the first worker is done or did it
        if not (self.claimed / f"{jid}.json").exists():
            # The first worker finished (and cleared) in between.
            try:
                (self.claimed / f"{jid}.answered").unlink()
            except OSError:
                pass
            return
        record = {key: value for key, value in job.items()
                  if key not in ("token", "twin")}
        _write_json(self.done / f"{jid}.json",
                    {"job": record, "result": answer, "worker": worker,
                     "device": device})

    def claim_twin(self, worker: str, version: str,
                   accept: Callable[[dict], bool],
                   faster: Callable[[dict, dict], bool]) -> dict | None:
        """At the end of a test: do a job another worker is on too, when
        this one would finish it well before (``faster(job, beat)``).
        One twin per job; the first good answer counts."""
        for path in sorted(self.claimed.glob("*.json")):
            jid = path.stem
            if self.answered(jid) or (self.claimed / f"{jid}.twin").exists():
                continue
            job = _read_json(path)
            beat = _read_json(self.claimed / f"{jid}.alive") or {}
            if not isinstance(job, dict) or job.get("version") != version \
                    or beat.get("worker") == worker or not accept(job) \
                    or not addressed_to(job, worker) \
                    or not faster(job, beat):
                continue
            try:
                handle = os.open(self.claimed / f"{jid}.twin",
                                 os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(handle, worker.encode("utf-8"))
                os.close(handle)
            except OSError:
                continue
            job["twin"] = True
            job["token"] = f"twin-{worker}-{os.getpid()}"
            return job
        return None

    def _clear_claim(self, job: str) -> None:
        for suffix in (".json", ".alive", ".answered", ".twin"):
            try:
                (self.claimed / f"{job}{suffix}").unlink()
            except OSError:
                pass

    def release(self, job: dict, count_try: bool = True) -> None:
        """Back into the queue: the worker was stopped. ``count_try``
        False (v1.0.23): it was not the round's fault (the heat), so the
        claim is not counted against it."""
        if job.get("twin"):
            try:
                (self.claimed / f"{job['id']}.twin").unlink()
            except OSError:
                pass
            return
        if self.answered(job["id"]):
            self._clear_claim(job["id"])
            return
        if job.get("token") and not self.owns(job):
            return
        if not count_try:
            try:
                path = self.claimed / f"{job['id']}.json"
                stored = _read_json(path)
                if isinstance(stored, dict):
                    stored["tries"] = max(0, int(stored.get("tries", 1)) - 1)
                    _write_json(path, stored)
            except (OSError, ValueError, TypeError):
                pass
        try:
            os.replace(self.claimed / f"{job['id']}.json",
                       self.jobs / f"{job['id']}.json")
        except OSError:
            pass
        self._forget_beat(job["id"])

    def status(self, worker: str, state: str, device: str,
               job: dict | None = None, done: int = 0,
               left_s: float | None = None, can=(),
               lanes: int = 1, version: str = "") -> None:
        try:
            _write_json(self.workers / f"{_safe(worker)}.json",
                        {"worker": worker, "host": host_name(),
                         "state": state, "device": device, "done": done,
                         "job": (job or {}).get("label", ""),
                         "class": job_class(job) if job else "",
                         "left_s": left_s, "can": sorted(can),
                         "lanes": max(1, int(lanes)),
                         "version": version})
        except OSError:
            pass                    # the share is away for a moment

    def _forget_beat(self, job: str) -> None:
        try:
            (self.claimed / f"{job}.alive").unlink()
        except OSError:
            pass


#: Waiting jobs as last read: path -> (modification time, job).
_WAITING: dict[str, tuple[float, dict]] = {}


def _priority(job: dict) -> int:
    try:
        return int(job.get("priority", 0) or 0)
    except (TypeError, ValueError):
        return 0


def addressed_to(job: dict, worker: str) -> bool:
    """A round for one computer (``for``, v1.0.21: a check) is taken only
    by a lane of that computer."""
    target = str(job.get("for") or "").strip().lower()
    if not target:
        return True
    return target in (worker.lower(), host_name().lower(),
                      worker.lower().rsplit("-", 1)[0])


def job_class(job: dict | None) -> str:
    """What a job's time is compared by: rounds of one class take about
    as long on one computer."""
    if not job:
        return ""
    if not job.get("class") and job.get("kind") == "separation_round":
        # v1.0.21: a round of 1.5.14 made by v1.0.18 has no class of its
        # own; its way is the class, as v1.0.19 gives it.
        way = (job.get("payload") or {}).get("way")
        if way:
            return f"sep:{way}"
    return str(job.get("class") or job.get("kind") or "")


def estimate(speeds: dict, worker: str, cls: str) -> float | None:
    """How long a round of ``cls`` takes ``worker``, from what it and the
    others did: its own mean when it did one, otherwise the class's mean
    over the others scaled by how fast this worker is on the classes they
    share. ``None`` when nothing is known."""
    def mean(entry):
        total, count = entry
        return total / count if count else None

    own = speeds.get(worker, {})
    if cls in own and mean(own[cls]):
        return mean(own[cls])
    others = [mean(table[cls]) for name, table in speeds.items()
              if name != worker and cls in table and mean(table[cls])]
    if not others:
        return None
    ratios = []
    for shared, entry in own.items():
        mine = mean(entry)
        theirs = [mean(table[shared]) for name, table in speeds.items()
                  if name != worker and shared in table
                  and mean(table[shared])]
        if mine and theirs:
            ratios.append(mine / (sum(theirs) / len(theirs)))
    if not ratios:
        return None
    ratios.sort()
    return sorted(others)[len(others) // 2] * ratios[len(ratios) // 2]


#: A worker leaves a round to another when that one is expected to be
#: done with it this much sooner (and at the end, twins when this much).
_FASTER_SHARE = 0.8
#: How long what the helpers said is trusted before it is read again.
_LOOK_S = 20.0


class Smart:
    """Who takes what at the end of a test (v1.0.19).

    The owner's wish: a slow computer should not get the last round and
    keep the test waiting. Each worker knows from the answers how long
    each class of round takes every worker (:meth:`Queue.note_speed`).
    While there is plenty to do, everybody takes work. When no more
    rounds wait than there are workers that would finish one sooner -
    counting the time they still need for the round they are on - a slow
    worker leaves them to those. And when nothing waits at all, a worker
    that is idle does a round another is still on too, if it would be
    done with it well before; the first good answer counts.
    """

    def __init__(self, queue: Queue, worker: str,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.queue = queue
        self.worker = worker
        self.clock = clock
        self._seen_at = -1e9
        self._speeds: dict = {}
        self._workers: list[dict] = []

    def _look(self) -> None:
        if self.clock() - self._seen_at < _LOOK_S:
            return
        self._seen_at = self.clock()
        self._speeds = self.queue.read_speeds()
        self._workers = [status for status in self.queue.active_workers()
                         if status.get("worker") != self.worker]

    def mine(self, cls: str) -> float | None:
        self._look()
        return estimate(self._speeds, self.worker, cls)

    def leave(self, job: dict) -> bool:
        """Leave this waiting round to a faster worker?"""
        self._look()
        cls = job_class(job)
        mine = estimate(self._speeds, self.worker, cls)
        if mine is None or job.get("for"):
            # A round for this computer (a check) is nobody else's.
            return False
        faster = 0
        for status in self._workers:
            theirs = self._theirs(status, job, cls)
            if theirs is None:
                continue
            if status.get("state") == "waiting":
                busy = 0.0
            elif status.get("state") == "working" and \
                    status.get("left_s") is not None:
                busy = max(0.0, float(status["left_s"]))
            else:
                continue
            if busy + theirs < _FASTER_SHARE * mine:
                faster += 1
        if not faster:
            return False
        waiting = sum(1 for _path in self.queue.jobs.glob("*.json"))
        return waiting <= faster

    def _theirs(self, status: dict, job: dict, cls: str) -> float | None:
        """How long another worker would take for this round - only for
        one that can do it: a worker that did this class itself, or one
        that says it has what the round needs (v1.0.20: helpers write
        what they can in their status). Leaving a round to one that
        cannot do it would leave it to nobody."""
        worker = status.get("worker", "")
        entry = self._speeds.get(worker, {}).get(cls)
        if entry and entry[1]:
            return entry[0] / entry[1]
        can = status.get("can")
        if can is None or not set(job.get("needs") or ()) <= set(can):
            return None
        return estimate(self._speeds, worker, cls)

    def twin_worth_it(self, job: dict, beat: dict) -> bool:
        """Would this worker finish a round another is on well before?"""
        if job.get("for"):
            return False                  # a check: one at a time
        self._look()
        mine = estimate(self._speeds, self.worker, job_class(job))
        if mine is None:
            return False
        holder = next((status for status in self._workers
                       if status.get("worker") == beat.get("worker")), None)
        if holder is None or holder.get("left_s") is None:
            return False
        return mine < _FASTER_SHARE * float(holder["left_s"])

    def claim(self, version: str, accept: Callable[[dict], bool]):
        """A job to do, or a twin of one at the end, or ``None``; and
        whether a newer version waits."""
        job, newer = self.queue.claim(
            self.worker, version,
            lambda candidate: accept(candidate) and not self.leave(candidate))
        if job is None and not newer and \
                not any(self.queue.jobs.glob("*.json")):
            job = self.queue.claim_twin(self.worker, version, accept,
                                        self.twin_worth_it)
        return job, newer


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)


class Stop:
    """Asked from outside to stop: a flag a worker loop looks at, and the
    job it is on, so a handler for a closing window can put it back."""

    def __init__(self) -> None:
        self.asked = False
        self.current: dict | None = None

    def __call__(self) -> bool:
        return self.asked


def work(queue: Queue, worker: str, device: str, version: str,
         handlers: dict[str, Callable], stop: Callable[[], bool],
         say: Callable[[str, dict], None] = lambda key, values: None,
         idle_s: float = IDLE_S, sleep=time.sleep,
         once: bool = False,
         accept: Callable[[dict], bool] = lambda job: True,
         on_lost: Callable[[], None] = lambda: None,
         can=(), update_check: Callable[[], bool] | None = None,
         clock: Callable[[], float] = time.monotonic,
         finish_check: Callable[[], bool] | None = None,
         heat=None, parked: Path | None = None) -> str:
    """A worker: take a job, do it, give the answer, take the next; wait
    when there is none. Returns ``"stopped"`` or ``"update"``.

    v1.0.23: ``finish_check()`` says the owner asked to stop after the
    current job (the helper's window): asked before every claim, so the
    job that runs is finished and then the worker ends. ``heat`` (a
    :class:`modules.heat_guard.HeatGuard`) keeps a hot computer from
    taking work until it has cooled down, and stops a round that stays
    too hot - the round goes back into the queue for another computer.

    ``can`` is what this worker has (see :func:`accept_for`), written in
    its status so the others know which rounds it can take over.
    ``update_check()`` says a newer version of the helper waits (v1.0.20):
    asked after every job and every :data:`UPDATE_LOOK_S` while waiting,
    and then the worker ends with ``"update"``. Without it (no share
    known) a waiting job of a newer version is the sign to update; with
    it only a newer installer is - a newer job alone (another copy of the
    program on the same share, say) would otherwise restart the helper
    over and over.

    ``handlers`` has per kind of job ``handler(job, queue, stop) ->
    answer``. A handler that raises gives an answer with ``failed``, so
    the test reports it the way it reports a failure on the laptop.
    ``say(key, values)`` tells the person watching what happens, by
    translation key.

    v1.0.28 (B665): an answer that cannot reach the share is kept in
    ``parked`` (a folder of the helper's own) and delivered when the
    share is back - also after a stop or a restart. (B666) When the
    program asks the helpers to stop and there is nothing left, the
    worker ends.
    """

    done = 0
    started = _share_now(queue)
    _deliver_parked(queue, parked, say)
    waiting_said = False
    away_said = False
    smart = Smart(queue, worker)
    looked = [clock()]

    def newer_helper(now_too: bool = False) -> bool:
        if update_check is None:
            return False
        if not now_too and clock() - looked[0] < UPDATE_LOOK_S:
            return False
        looked[0] = clock()
        try:
            return bool(update_check())
        except Exception:  # noqa: BLE001 - a look, never a reason to fall
            return False

    cooling_said = False
    while not stop():
        if finish_check is not None and _asked(finish_check):
            say("helper_finish_asked", {})
            break
        hot = heat.must_wait() if heat is not None else None
        if hot is not None:
            try:
                queue.status(worker, "cooling", device, done=done, can=can,
                             version=version)
            except OSError:
                pass
            if not cooling_said:
                say("helper_cooling", {"degrees": hot})
                cooling_said = True
            for _step in range(max(1, int(idle_s))):
                if stop():
                    break
                sleep(1.0)
            continue
        if cooling_said:
            say("helper_cooled", {})
            cooling_said = False
        try:
            queue.ensure()
            job, newer = smart.claim(version, accept)
        except OSError:
            # The laptop sleeps or the network is gone: wait, do not fall
            # over - the helper is meant to stay open.
            if not away_said:
                say("helper_share_away", {"queue": queue.root})
                away_said = True
            for _step in range(max(1, int(idle_s))):
                if stop():
                    break
                sleep(1.0)
            continue
        away_said = False
        if parked is not None:
            _deliver_parked(queue, parked, say)
        if job is None:
            if queue.helpers_asked_to_stop(started):
                say("helper_central_stop", {})
                break
            if (newer and update_check is None) or newer_helper(
                    now_too=newer):
                say("helper_update", {})
                queue.status(worker, "stopped", device, done=done, can=can)
                return "update"
            queue.status(worker, "waiting", device, done=done, can=can,
                         version=version)
            if not waiting_said:
                say("helper_waiting", {})
                waiting_said = True
            if once:
                return "stopped"
            for _step in range(max(1, int(idle_s))):
                if stop():
                    break
                sleep(1.0)
            continue
        waiting_said = False
        if int(job.get("tries", 1)) > MAX_TRIES:
            # It took its worker down before, every time: say so rather
            # than go down with it.
            queue.finish(job, {"failed": f"crashed {MAX_TRIES} times"},
                         worker, device)
            continue
        if hasattr(stop, "current"):
            stop.current = job
        expected = smart.mine(job_class(job))
        began = time.monotonic()

        def left() -> float | None:
            if expected is None:
                return None
            return max(0.0, expected - (time.monotonic() - began))

        queue.status(worker, "working", device, job, done, left(),
                     can=can, version=version)
        say("helper_twin" if job.get("twin") else "helper_job",
            {"job": job.get("label", job["id"])})
        beating = threading.Event()

        def beat(job_id=job["id"], token=job.get("token", ""),
                 twin=bool(job.get("twin"))) -> None:
            count = 0
            last = time.monotonic()
            while not beating.wait(STATUS_S):
                if time.monotonic() - last >= HEARTBEAT_S:
                    last = time.monotonic()
                    count += 1
                    if not twin:
                        queue.heartbeat(job_id, worker, count, token)
                queue.status(worker, "working", device, job, done, left(),
                             can=can, version=version)
                if twin:
                    try:
                        lost = not (queue.claimed / f"{job_id}.json").exists()
                    except OSError:
                        lost = False
                else:
                    lost = queue.answered(job_id)
                if lost and not beating.is_set():
                    # The other worker did it meanwhile: stop what runs.
                    on_lost()
                    return

        beater = threading.Thread(target=beat, daemon=True)
        beater.start()
        too_hot = threading.Event()
        # v1.0.24 (B656): a round that watches the card itself (the check
        # of 1.5.18) is not stopped by the lane.
        if heat is not None and not job.get("own_heat"):
            def watch_heat() -> None:
                while not beating.wait(heat.WATCH_S):
                    if heat.watch():
                        too_hot.set()
                        on_lost()
                        return

            threading.Thread(target=watch_heat, daemon=True).start()
        try:
            handler = handlers.get(job.get("kind"))
            if handler is None:
                answer = {"failed": f"unknown kind {job.get('kind')}"}
            else:
                # Too hot stops what listens to it (Whisper) as a stop does.
                answer = handler(job, queue, _either(stop, too_hot.is_set))
        except KeyboardInterrupt:
            beating.set()
            queue.release(job)
            raise
        except Exception as exc:  # noqa: BLE001 - one job, not the helper
            answer = {"failed": f"{type(exc).__name__}: {exc}"[:300]}
        finally:
            beating.set()
            beater.join(timeout=STATUS_S + 5.0)
            if hasattr(stop, "current"):
                stop.current = None
        hot_now = too_hot.is_set()
        if hot_now and ("failed" in answer or answer.get("cancelled")
                        or answer.get("release")):
            # Too hot for too long: the round goes back for a computer
            # that can take it - not counted as a try, the round did no
            # wrong - and this one cools down first. A round that got
            # done all the same keeps its answer.
            queue.release(job, count_try=False)
            heat.aborted()
            say("helper_too_hot", {"job": job.get("label", job["id"])})
            continue
        if job.get("twin"):
            try:
                gone = not (queue.claimed / f"{job['id']}.json").exists()
            except OSError:
                gone = False
        else:
            gone = queue.answered(job["id"])
        if gone:
            queue.finish(job, answer, worker, device)     # clears only
            say("helper_job_lost", {"job": job.get("label", job["id"])})
            continue
        if stop() or answer.get("cancelled") or answer.get("release"):
            # Stopped halfway, or a job this worker turned out unable to
            # do: back for another.
            queue.release(job)
            if stop() or answer.get("cancelled"):
                break
            continue
        answer.setdefault("seconds", round(time.monotonic() - began, 1))
        while True:
            try:
                queue.finish(job, answer, worker, device)
                break
            except OSError:
                # Keep the answer until the share is back: it cost work.
                # v1.0.28 (B665): on this computer's disk, so a stop or a
                # restart does not lose it either.
                if parked is not None:
                    _park(parked, job, answer, worker, device)
                    say("helper_answer_parked",
                        {"job": job.get("label", job["id"])})
                    break
                if stop():
                    return "stopped"
                say("helper_share_away", {"queue": queue.root})
                sleep(max(1.0, idle_s))
        done += 1
        say("helper_job_done", {"job": job.get("label", job["id"]),
                                "seconds": answer["seconds"]})
        if hot_now:
            heat.aborted()
        if finish_check is not None and _asked(finish_check):
            # The owner's "stop after this round" goes before an update:
            # the update is found at the next start all the same.
            continue
        if newer_helper(now_too=True):
            say("helper_update", {})
            queue.status(worker, "stopped", device, done=done, can=can)
            return "update"
        if once:
            return "stopped"
    queue.status(worker, "stopped", device, done=done)
    return "stopped"


def _share_now(queue: "Queue") -> float:
    """The share's clock now: the time of a file just written there (the
    computers' clocks need not agree)."""
    probe = queue.root / "workers" / f".now_{os.getpid()}"
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("", encoding="utf-8")
        moment = probe.stat().st_mtime
        probe.unlink()
        return moment
    except OSError:
        return time.time()


def _park(folder: Path, job: dict, answer: dict, worker: str,
          device: str) -> None:
    """v1.0.28 (B665): an answer kept on this computer until the share is
    back."""
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        _write_json(Path(folder) / f"{job['id']}.json",
                    {"job": job, "answer": answer, "worker": worker,
                     "device": device})
    except OSError:
        pass


def _deliver_parked(queue: "Queue", folder: Path | None, say) -> int:
    """The kept answers to the share, when it is there. Returns how many
    went."""
    if folder is None:
        return 0
    count = 0
    for path in sorted(Path(folder).glob("*.json")):
        kept = _read_json(path)
        if not isinstance(kept, dict) or "job" not in kept:
            continue
        try:
            queue.finish(kept["job"], kept["answer"], kept.get("worker", ""),
                         kept.get("device", "cpu"))
        except OSError:
            return count
        try:
            path.unlink()
        except OSError:
            pass
        count += 1
        say("helper_answer_delivered",
            {"job": kept["job"].get("label", kept["job"].get("id", ""))})
    return count


def _either(first: Callable[[], bool], second: Callable[[], bool]):
    """A stop that is asked when either is."""
    return lambda: bool(first()) or bool(second())


def _asked(check: Callable[[], bool]) -> bool:
    try:
        return bool(check())
    except Exception:  # noqa: BLE001 - a look, never a reason to fall
        return False


#: The program's own lane in the queue.
OWN_LANE = "program"
#: How often the program puts its rounds out again (see run_jobs).
_REPUBLISH_S = 60.0
#: How often a waiting worker asks whether a newer helper waits.
UPDATE_LOOK_S = 60.0


def own_worker() -> str:
    return f"{host_name()}-{OWN_LANE}"


def helpers_idle(queue: Queue) -> bool:
    """Are there helpers, and do they all wait?"""
    helpers = [status for status in queue.active_workers()
               if not str(status.get("worker", "")).endswith(OWN_LANE)]
    # v1.0.23: a helper that cools down takes no round either.
    return bool(helpers) and all(status.get("state") in ("waiting",
                                                         "cooling")
                                 for status in helpers)


def may_work_here(queue: Queue) -> bool:
    """The program works on the queue itself unless a helper runs on
    this same computer - then that one does, with its own lanes."""
    here = host_name()
    # v1.0.23: a helper here that cools down is there too - the program
    # taking its rounds would heat the very computer that cools.
    return not any(status.get("host") == here
                   and not str(status.get("worker", "")).endswith(OWN_LANE)
                   and status.get("state") in ("waiting", "working",
                                               "cooling")
                   for status in queue.active_workers())


def _never() -> bool:
    return False


def _child_round(kind: str, job: dict, root: str) -> dict:
    """One round in a process of its own on the program's computer."""
    from . import queue_jobs

    handler = queue_jobs.handlers()[kind]
    started = time.monotonic()
    answer = handler(job, Queue(Path(root)), _never)
    answer.setdefault("seconds", round(time.monotonic() - started, 1))
    return answer


def helper_can(queue: "Queue", capability: str) -> bool:
    """Does a helper (not this program) that is alive have ``capability``?"""
    try:
        return any(capability in (status.get("can") or ())
                   for status in queue.active_workers()
                   if not str(status.get("worker", "")).endswith(OWN_LANE))
    except OSError:
        return False


#: v1.0.26 (B674): what the program leaves to a helper that has it. The
#: WhisperX aligner (wav2vec2) took the whole program down twice, without
#: a word in the log - a native crash or memory running out.
LEAVE_TO_HELPERS = ("whisperx",)


def program_capabilities(queue: "Queue", local) -> set:
    """What the program itself takes on: ``local`` without what a helper
    that has it does better away from the program (B674)."""
    have = set(local)
    for capability in LEAVE_TO_HELPERS:
        if capability in have and helper_can(queue, capability):
            have.discard(capability)
    return have


def _isolated_round(job: dict, queue: "Queue") -> dict:
    """v1.0.26 (B674): a round meant for a process of its own, after the
    pool fell over - still in a process of its own, a fresh one, so a
    crash costs the round and not the program."""
    pool = _pool(1)
    if pool is None:
        return _child_round(job["kind"], job, str(queue.root))
    try:
        return pool.submit(_child_round, job["kind"], job,
                           str(queue.root)).result()
    except BrokenProcessPool:
        return {"failed": "the round's process stopped abruptly",
                "crashed": True}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _helper_for(queue: "Queue", job: dict) -> bool:
    """v1.0.27: is a helper alive (not this program) that has what the
    round needs?"""
    needs = set(job.get("needs") or ())
    try:
        return any(needs <= set(status.get("can") or ())
                   for status in queue.active_workers()
                   if not str(status.get("worker", "")).endswith(OWN_LANE))
    except OSError:
        return False


#: v1.0.27: kept open in a child process for faulthandler.
_CHILD_CRASH_FILE = None


def _child_start() -> None:
    """v1.0.27: a process of the pool writes its stacks into the
    program's crash log when it dies natively (``KT_CRASH_LOG``, set by
    the program) - on 5 October every process of the laptop's pool died
    within seconds, without a word."""
    global _CHILD_CRASH_FILE
    path = os.environ.get("KT_CRASH_LOG")
    if not path:
        return
    try:
        import faulthandler

        _CHILD_CRASH_FILE = open(path, "a", encoding="utf-8")
        _CHILD_CRASH_FILE.write(
            f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} child pid "
            f"{os.getpid()}\n")
        _CHILD_CRASH_FILE.flush()
        faulthandler.enable(file=_CHILD_CRASH_FILE, all_threads=True)
    except (OSError, RuntimeError, ValueError):
        pass


def _pool(lanes: int):
    try:
        from concurrent.futures import ProcessPoolExecutor

        return ProcessPoolExecutor(max_workers=lanes,
                                   initializer=_child_start)
    except Exception:  # noqa: BLE001 - then one at a time
        return None


def _bring_out(source: Queue, target: Queue, job: str) -> None:
    """The files an answer of the old folder made, to where the program
    looks for them."""
    made = source.out_dir(job)
    if not made.is_dir():
        return
    goal = target.out_dir(job)
    goal.mkdir(parents=True, exist_ok=True)
    for path in sorted(made.iterdir()):
        try:
            shutil.move(str(path), str(goal / path.name))
        except OSError:
            pass
    shutil.rmtree(made, ignore_errors=True)


class _Legacy:
    """The queue folder of v1.0.20 to v1.0.22, next to the program folder,
    while helpers of that time still work in it (v1.0.23, B650; up to
    then this was ``kt_werk`` of v1.0.18/v1.0.19). Their answers are
    taken over, a round one of them holds is not put out twice, and a
    marker job of the new version tells them to update: a worker of an
    older version that sees a newer job waiting stops and fetches the
    new program, and its installer brings it over to the new place. When
    nobody works in it any more, the folder goes."""

    def __init__(self, queue: Queue) -> None:
        folder = old_queue_folder(queue.root)
        self.queue = Queue(folder) if folder is not None and \
            folder != queue.root and folder.is_dir() else None
        self.seen: dict = {}

    def holds(self, job: str) -> bool:
        if self.queue is None:
            return False
        return any((folder / f"{job}.json").exists()
                   for folder in (self.queue.claimed, self.queue.done))

    def beacon(self, version: str) -> None:
        if self.queue is None:
            return
        try:
            _write_json(self.queue.jobs / "update.json",
                        {"id": "update", "kind": "update",
                         "version": version, "label": "update"})
        except OSError:
            pass

    def answers(self) -> list[tuple[Queue, dict]]:
        if self.queue is None:
            return []
        try:
            return [(self.queue, answer) for answer in self.queue.answers()]
        except OSError:
            return []

    def tend(self) -> None:
        """A helper of that time that fell silent: its round is not put
        back there (nobody of this version looks there), so it can be
        put out anew here."""
        if self.queue is None:
            return
        try:
            for job in self.queue.requeue_stale(self.seen):
                try:
                    (self.queue.jobs / f"{job}.json").unlink()
                except OSError:
                    pass
        except OSError:
            pass

    def tidy(self) -> None:
        if self.queue is None:
            return
        try:
            busy = any(self.queue.claimed.glob("*.json")) or \
                any(self.queue.done.glob("*.json")) or \
                any(status.get("state") in ("waiting", "working")
                    for status in self.queue.active_workers())
        except OSError:
            return
        if not busy:
            shutil.rmtree(self.queue.root, ignore_errors=True)
            self.queue = None


def _own_idle(queue: Queue) -> str:
    """What the program's lane says when it has nothing: ``waiting`` only
    when it would take work - with a helper on this computer it does not,
    and then nobody should leave a round to it."""
    return "waiting" if may_work_here(queue) else "standby"


def announce(queue: Queue, version: str) -> None:
    """At the program's start: tell the helpers of an older version in the
    old work folder that a newer version is there, also when no test
    runs (v1.0.20; v1.0.23: the helpers of v1.0.20 to v1.0.22)."""
    _Legacy(queue).beacon(version)


def forecast(queue: Queue, version: str) -> dict:
    """How long the rounds of this version in the queue will still take,
    over the workers there are (v1.0.20): every waiting round goes, in
    turn, to the worker that would be done with it first - counting the
    time each still needs for the round it is on - by what the answers
    say about each worker's speed. ``{"seconds": s or None, "lanes": n}``;
    ``seconds`` is ``None`` when a round waits that no worker is known
    for, ``lanes`` how many rounds can run at once.

    v1.0.28 (B661): a round no worker has a speed for yet, but that one
    of them can take, is counted at the mean of its class over every
    computer (or of everything measured) - ``"rough": True`` then, and
    the top bar says "about"."""
    try:
        speeds = queue.read_speeds()
        workers = [status for status in queue.active_workers()
                   if status.get("state") in ("waiting", "working")]
        waiting = []
        for path in sorted(queue.jobs.glob("*.json"),
                           key=lambda path: (_mtime(path), path.name)):
            job = _read_json(path)
            if isinstance(job, dict) and job.get("version") == version:
                waiting.append(job)
        held = sum(1 for path in queue.claimed.glob("*.json"))
    except OSError:
        return {"seconds": None, "lanes": 1}
    slots = []
    for status in workers:
        busy = float(status.get("left_s") or 0.0) \
            if status.get("state") == "working" else 0.0
        for lane in range(max(1, int(status.get("lanes", 1) or 1))):
            slots.append([busy if lane == 0 else 0.0, status])
    lanes = max(1, len(slots))
    if not slots or not (waiting or held):
        return {"seconds": None, "lanes": lanes}
    rough = False
    for job in waiting:
        cls = job_class(job)
        best = None
        for slot in slots:
            status = slot[1]
            entry = speeds.get(status.get("worker", ""), {}).get(cls)
            if entry and entry[1]:
                takes = entry[0] / entry[1]
            elif status.get("can") is not None and \
                    set(job.get("needs") or ()) <= set(status["can"]):
                takes = estimate(speeds, status.get("worker", ""), cls)
            else:
                takes = None
            if takes is None and _can_take(status, job):
                takes = _rough_takes(speeds, cls)
                if takes is not None:
                    rough = True
            if takes is not None and (best is None
                                      or slot[0] + takes < best[0]):
                best = (slot[0] + takes, slot)
        if best is None:
            return {"seconds": None, "lanes": lanes}
        best[1][0] = best[0]
    return {"seconds": max(slot[0] for slot in slots), "lanes": lanes,
            "rough": rough}


def _can_take(status: dict, job: dict) -> bool:
    can = status.get("can")
    return can is None or set(job.get("needs") or ()) <= set(can)


def _rough_takes(speeds: dict, cls: str) -> float | None:
    """B661: the mean time of ``cls`` over every computer, otherwise of
    every round measured - a guess, but better than no end time."""
    same = [total / count for table in speeds.values()
            for name, (total, count) in table.items()
            if name == cls and count]
    if same:
        return sum(same) / len(same)
    every = [total / count for table in speeds.values()
             for total, count in table.values() if count]
    return sum(every) / len(every) if every else None


def forecaster(queue: Queue, version: str, every_s: float = 5.0):
    """:func:`forecast` for the top bar, read at most every ``every_s``."""
    memory = {"at": -1e9, "value": {"seconds": None, "lanes": 1}}

    def ask() -> dict:
        if time.monotonic() - memory["at"] >= every_s:
            memory["at"] = time.monotonic()
            memory["value"] = forecast(queue, version)
        return memory["value"]

    return ask


#: v1.0.28 (B662): what wants to hear every look at the queue - the top
#: bar of a test, so its count and end time keep moving while this
#: computer works on a round of its own. Weak, so a finished bar goes.
_WATCHERS: list = []


def watch(callback) -> None:
    """Call ``callback`` (a bound method) at every look at the queue."""
    import weakref

    try:
        _WATCHERS.append(weakref.WeakMethod(callback))
    except TypeError:
        _WATCHERS.append(lambda: callback)


def _tell_watchers() -> None:
    for ref in list(_WATCHERS):
        callback = ref()
        if callback is None:
            _WATCHERS.remove(ref)
            continue
        try:
            callback()
        except Exception:  # noqa: BLE001 - a bar never stops a test
            pass


#: v1.0.28 (B665): the owner's "stop after the current round" in the
#: program: no new rounds are taken here or by a helper (the rounds
#: nobody took yet are taken back), the rounds being worked on finish and
#: are counted, and the test ends with what it has.
_FINISH = threading.Event()


def request_finish() -> None:
    _FINISH.set()


def clear_finish() -> None:
    _FINISH.clear()


def finishing() -> bool:
    return _FINISH.is_set()


#: How many :func:`run_jobs` run in this process right now.
_RUNNING = 0


def running() -> bool:
    """Is a run of rounds going on in this process? Then work inside one
    of its rounds is not shared out again (v1.0.20)."""
    return _RUNNING > 0


def run_jobs(*args, **kwargs) -> dict:
    """See :func:`_run_jobs`; counts itself in :func:`running`."""
    global _RUNNING
    _RUNNING += 1
    try:
        return _run_jobs(*args, **kwargs)
    finally:
        _RUNNING -= 1


def _run_jobs(queue: Queue, jobs: list[dict], version: str,
              handlers: dict[str, Callable],
              on_answer: Callable[[dict], None],
              cancelled: Callable[[], bool],
              on_local: Callable[[dict], None] = lambda job: None,
              local_accept: Callable[[dict], bool] = lambda job: True,
              poll_s: float = 5.0, sleep=time.sleep,
              stuck_s: float = 60.0, local_lanes: int = 1,
              can=()) -> dict:
    """Every job of a test through the queue (v1.0.19, for all tests).

    Puts the jobs out, lets any worker take them - this computer too,
    unless a helper runs on it - and hands every answer to
    ``on_answer`` as it comes, also an answer a helper finished for the
    same round after an earlier run was stopped. When helpers all wait
    while work waits (a way they cannot do), this computer takes it after
    ``stuck_s``. Returns ``{"answered", "local", "run"}``; on a stop the
    rounds nobody took are taken back.

    ``local_lanes`` above one runs that many rounds at once on this
    computer, each in a process of its own - for light rounds of pure
    Python (1.5.15), which used a process pool before they went through
    the queue. Heavy rounds (a separation takes the cores itself) stay
    one at a time.

    ``can`` is what this computer has; with it the program says in the
    queue what it is doing, like a helper does (v1.0.20), so that helpers
    can leave a round to it and the forecast counts it.
    """
    queue.ensure()
    queue.write_where()
    # B666: a new test, so the helpers are wanted again.
    queue.clear_stop_helpers()
    if finishing():
        return {"answered": 0, "local": 0, "run": ""}
    legacy = _Legacy(queue)
    legacy.beacon(version)
    run = f"{int(time.time())}-{os.getpid()}"
    kinds = {job["kind"] for job in jobs}
    for kind in kinds:
        queue.withdraw_other_versions(kind, version)
    wanted = {}
    for job in jobs:
        job = dict(job, run=run, version=version)
        wanted[job["id"]] = job
    counts = {"answered": 0, "local": 0, "run": run}
    published = [time.monotonic()]

    def republish() -> None:
        # A round an older version still held can come back into the
        # queue as ITS job (its helper was closed or fell silent), and no
        # worker of this version would ever take it: put it out again as
        # ours. publish() leaves rounds being worked on or answered alone.
        if time.monotonic() - published[0] < _REPUBLISH_S:
            return
        published[0] = time.monotonic()
        for job in list(wanted.values()):
            if legacy.holds(job["id"]):
                continue
            try:
                queue.publish(job)
            except OSError:
                pass

    def gather() -> None:
        legacy.tend()
        for where, answer in [(queue, answer) for answer in queue.answers()] \
                + legacy.answers():
            job = answer.get("job") or {}
            if job.get("kind") not in kinds:
                continue
            if where is not queue:
                _bring_out(where, queue, job["id"])
            where.take_answer(job["id"])
            result = answer.get("result") or {}
            if result.get("cancelled"):
                continue
            if "failed" not in result and not job.get("for"):
                queue.note_speed(answer.get("worker", ""), job_class(job),
                                 result.get("seconds"))
            on_answer(answer)
            if wanted.pop(job["id"], None) is not None:
                counts["answered"] += 1
        _tell_watchers()

    gather()
    for job in wanted.values():
        if not legacy.holds(job["id"]):
            queue.publish(job)
    me = own_worker()

    def say_own(state: str, job: dict | None = None,
                began: float | None = None) -> None:
        left = None
        if job is not None and began is not None:
            mine = smart.mine(job_class(job))
            if mine is not None:
                left = max(0.0, mine - (time.monotonic() - began))
        queue.status(me, state, "cpu", job, counts["local"], left,
                     can=can, lanes=local_lanes)

    smart = Smart(queue, me)
    finished = [False]

    def finish_if_asked() -> None:
        # B665: once, the first time the owner's stop-after-current is
        # seen: what nobody took goes, what is being worked on stays.
        # Every look after that: a round that came back (its helper fell
        # silent) is taken back too, or the test would wait for ever.
        if not finishing():
            return
        if finished[0]:
            back = [job_id for job_id in wanted
                    if not (queue.claimed / f"{job_id}.json").exists()]
            if back:
                queue.withdraw(run)
                for job_id in back:
                    wanted.pop(job_id, None)
            return
        finished[0] = True
        queue.withdraw(run)
        for job_id in list(wanted):
            if not (queue.claimed / f"{job_id}.json").exists():
                wanted.pop(job_id, None)
        logging.getLogger(__name__).info(_text("log_queue_finishing"),
                                         len(wanted))

    seen: dict = {}
    idle_since = None
    clock = time.monotonic
    pool = _pool(local_lanes) if local_lanes > 1 else None
    running: dict = {}                  # future -> (job, count)

    def collect(wait: bool = False) -> None:
        for future in list(running):
            if not (wait or future.done()):
                job, count = running[future]
                count += 1
                running[future] = (job, count)
                if not job.get("twin"):     # the holder's beat is its own
                    queue.heartbeat(job["id"], me, count,
                                    job.get("token", ""))
                continue
            job, _count = running.pop(future)
            try:
                answer = future.result()
            except BrokenProcessPool:
                # v1.0.25 (B672): the pool fell over, not the round - it
                # goes back for another (or for this computer, serially).
                queue.release(job, count_try=False)
                broken[0] = True
                continue
            except Exception as exc:  # noqa: BLE001 - one job
                answer = {"failed": f"{type(exc).__name__}: {exc}"[:300]}
            queue.finish(job, answer, me, "cpu")
            counts["local"] += 1

    broken = [False]
    local_off = [False]
    while pool is not None and wanted and not cancelled():
        try:
            gather()
            collect()
            queue.requeue_stale(seen)
            republish()
            finish_if_asked()
            if not wanted:
                break
            say_own("working" if running else _own_idle(queue))
            while not broken[0] and not finishing() and \
                    len(running) < local_lanes and (
                    may_work_here(queue) or helpers_idle(queue)):
                job, _newer = smart.claim(version, local_accept)
                if job is None:
                    break
                on_local(job)
                try:
                    running[pool.submit(_child_round, job["kind"], job,
                                        str(queue.root))] = (job, 0)
                except BrokenProcessPool:
                    queue.release(job, count_try=False)
                    broken[0] = True
        except BrokenProcessPool:
            broken[0] = True
        if broken[0]:
            # B672: 1.5.15 stopped on this (a child process died, the whole
            # test fell over). Now what the pool held goes back into the
            # queue and this computer goes on without the pool, one round
            # at a time.
            for job, _count in running.values():
                queue.release(job, count_try=False)
            running.clear()
            pool.shutdown(wait=False, cancel_futures=True)
            pool = None
            logging.getLogger(__name__).warning(_text("log_pool_broken"))
            break
        for _tick in range(max(1, int(poll_s))):
            if cancelled():
                break
            sleep(1.0)
    if pool is not None:
        if cancelled():
            for future in running:
                future.cancel()
            for job, _count in running.values():
                queue.release(job)
            running.clear()
        else:
            collect(wait=True)
            gather()
        pool.shutdown(wait=not cancelled(), cancel_futures=True)
    while pool is None and wanted and not cancelled():
        gather()
        queue.requeue_stale(seen)
        republish()
        if not wanted:
            break
        if helpers_idle(queue) and any(queue.jobs.glob("*.json")):
            idle_since = idle_since if idle_since is not None else clock()
        else:
            idle_since = None
        finish_if_asked()
        if not wanted:
            break
        stuck = idle_since is not None and clock() - idle_since > stuck_s
        if finishing():
            stuck = False
        if stuck or (not finishing() and not local_off[0]
                     and may_work_here(queue)):
            if stuck:
                job, _newer = queue.claim(me, version, local_accept)
            else:
                job, _newer = smart.claim(version, local_accept)
            if job is not None:
                on_local(job)
                handler = handlers.get(job.get("kind"))
                began = clock()
                beating = threading.Event()

                def beat(job=job, began=began) -> None:
                    # The program's own round beats like a helper's, so it
                    # is not put back while it runs, and says how long it
                    # still takes.
                    count = 0
                    last = time.monotonic()
                    say_own("working", job, began)
                    while not beating.wait(STATUS_S):
                        if time.monotonic() - last >= HEARTBEAT_S:
                            last = time.monotonic()
                            count += 1
                            if not job.get("twin"):
                                queue.heartbeat(job["id"], me, count,
                                                job.get("token", ""))
                        say_own("working", job, began)

                beater = threading.Thread(target=beat, daemon=True)
                beater.start()
                box: dict = {}

                def work_round(job=job, handler=handler) -> None:
                    try:
                        if handler is None:
                            box["answer"] = {
                                "failed": f"unknown kind {job['kind']}"}
                        elif local_lanes > 1:
                            # B674: rounds meant for a process of their
                            # own never run inside the program, also not
                            # after the pool fell over.
                            box["answer"] = _isolated_round(job, queue)
                        else:
                            box["answer"] = handler(job, queue, cancelled)
                    except Exception as exc:  # noqa: BLE001 - one job
                        box["answer"] = {
                            "failed": f"{type(exc).__name__}: {exc}"[:300]}

                # v1.0.28 (B662): the round runs beside the look at the
                # queue, so the answers of the helpers keep coming in and
                # the count and the end time keep moving meanwhile.
                worker = threading.Thread(target=work_round, daemon=True)
                worker.start()
                try:
                    while worker.is_alive():
                        worker.join(timeout=float(poll_s))
                        if worker.is_alive():
                            gather()
                            queue.requeue_stale(seen)
                            republish()
                finally:
                    beating.set()
                    beater.join(timeout=STATUS_S + 5.0)
                answer = box.get("answer") or {"failed": "no answer"}
                if answer.get("cancelled") or cancelled():
                    queue.release(job)
                    break
                if answer.get("crashed") and not stuck and \
                        _helper_for(queue, job):
                    # v1.0.27: the round's process died on this computer
                    # - a helper does it, and this computer takes no more
                    # rounds of this test unless the helpers cannot.
                    queue.release(job, count_try=False)
                    if not local_off[0]:
                        logging.getLogger(__name__).warning(
                            _text("log_local_rounds_off"))
                    local_off[0] = True
                    continue
                answer.setdefault("seconds", round(clock() - began, 1))
                queue.finish(job, answer, me, "cpu")
                counts["local"] += 1
                continue
        say_own(_own_idle(queue))
        for _tick in range(max(1, int(poll_s))):
            if cancelled():
                break
            sleep(1.0)
    gather()
    say_own("stopped")
    legacy.tidy()
    if cancelled():
        taken_back = queue.withdraw(run)
        try:
            from .translations import t

            logging.getLogger(__name__).info(t("log_queue_withdrawn"),
                                             taken_back)
        except Exception:  # noqa: BLE001 - a helper without texts
            pass
    return counts
