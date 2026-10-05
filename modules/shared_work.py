"""Ordinary work on a helper when that is sooner done (v1.0.20).

The helpers were built for the long tests. The owner's wish: let them
help with ordinary karaoke too - but only when that is faster. The
longest step of an ordinary song is separating the voice from the
music (Demucs, or Roformer for High performance), and that is what goes
out: a separation, as one round in the work queue. v1.0.21: and the
render of the video, the second longest; 1.5.12 renders every video
through the queue at once.

Whether it goes out is decided from what the queue knows about speeds
(:mod:`modules.work_queue`): only when a helper waits that can do this
way of separating and is expected to be done with it well before this
computer (at most 80 % of the time). Without helpers, without a speed
known for this computer, or with every helper busy or slower, the
separation runs here exactly as before, and its time is noted so the
next decision knows it. Once out, the queue's own rules apply: should
the helper be taken meanwhile, this computer does the round itself, and
should a helper vanish, the round comes back.

Whisper stays on this computer: what it hears depends on the whole
project (the text as a hint, the language, the pieces), and moving all
of that is not worth what it would save.
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

from .translations import t

logger = logging.getLogger(__name__)

#: The kind of round a shared separation is in the work queue.
JOB_KIND = "split_round"
#: The work queue this program shares its work through, or ``None``.
_QUEUE_ROOT: Path | None = None


def use_queue(root: Path | None) -> None:
    """Called at the start: where the queue is. Nothing is made there -
    without helpers the folder may never exist."""
    global _QUEUE_ROOT
    _QUEUE_ROOT = Path(root) if root else None


def job_class(way) -> str:
    return f"split:{way.tag}"


def needs_of(way) -> list[str]:
    from . import separation

    return sorted(separation.backends(way))


def _queue():
    from . import work_queue

    if _QUEUE_ROOT is None or not _QUEUE_ROOT.is_dir():
        return None
    return work_queue.Queue(_QUEUE_ROOT)


def worth_sharing(queue, job: dict) -> bool:
    """Is a helper waiting that would be done with this round well
    before this computer?"""
    from . import work_queue

    me = work_queue.own_worker()
    speeds = queue.read_speeds()
    cls = work_queue.job_class(job)
    mine = work_queue.estimate(speeds, me, cls)
    if mine is None:
        return False
    for status in queue.active_workers():
        worker = str(status.get("worker", ""))
        if worker == me or worker.endswith(work_queue.OWN_LANE) or \
                status.get("state") != "waiting":
            continue
        can = status.get("can")
        if can is None or not set(job["needs"]) <= set(can):
            continue
        theirs = work_queue.estimate(speeds, worker, cls)
        if theirs is not None and theirs < work_queue._FASTER_SHARE * mine:
            return True
    return False


def local_capabilities() -> set[str]:
    from .separation_trial import local_capabilities as found

    return found()


def separate(audio_path: Path, work_dir: Path, way) -> dict[str, Path]:
    """Separate ``audio_path`` the way ``way`` says - here, or on a
    helper that is sooner done. Returns the stems as
    :func:`modules.separation.separate_way` does, in ``work_dir``."""
    from . import __version__, proc, separation, work_queue

    queue = None if work_queue.running() else _queue()
    job = None
    if queue is not None:
        try:
            job = {"id": work_queue.job_id(
                       f"split|{audio_path}|{way.tag}|{time.time_ns()}"),
                   "kind": JOB_KIND, "class": job_class(way),
                   "needs": needs_of(way),
                   "label": f"{audio_path.parent.name} - {way.tag}",
                   "payload": {"way": _way_data(way)}}
            if not worth_sharing(queue, job):
                job = None
        except OSError:
            job = None
    if job is None:
        began = time.monotonic()
        stems = separation.separate_way(audio_path, work_dir, way)
        _note_own(queue, job_class(way), time.monotonic() - began)
        return stems
    logger.info(t("log_shared_separation"), audio_path.name, way.tag)
    folder = queue.files / "split" / job["id"]
    folder.mkdir(parents=True, exist_ok=True)
    mix = folder / ("mix" + audio_path.suffix)
    shutil.copyfile(audio_path, mix)
    job["payload"]["mix"] = mix.relative_to(queue.root).as_posix()
    found: dict = {}

    def here(job_, queue_, cancelled) -> dict:
        if job_["id"] != job["id"]:
            return {"release": True}      # not this song's round
        stems = separation.separate_way(audio_path, work_dir, way)
        found.update(stems)
        return {"here": True}

    def on_answer(answer: dict) -> None:
        result = answer.get("result") or {}
        if answer["job"]["id"] != job["id"]:
            # A separation of an earlier song that was stopped: not ours.
            shutil.rmtree(queue.out_dir(answer["job"]["id"]),
                          ignore_errors=True)
            return
        if result.get("here"):
            return
        if "failed" in result:
            found["failed"] = result["failed"]
            return
        made = queue.out_dir(answer["job"]["id"])
        work_dir.mkdir(parents=True, exist_ok=True)
        for name, file_name in (result.get("stems") or {}).items():
            target = work_dir / f"{name}.wav"
            shutil.move(str(made / file_name), str(target))
            found[name] = target
        logger.info(t("log_shared_separation_done"), answer.get("worker", ""),
                    result.get("seconds", 0))

    try:
        work_queue.run_jobs(
            queue, [job], __version__, {JOB_KIND: here}, on_answer,
            proc.stopped_since(proc.stops()),
            local_accept=_only(job["id"], work_queue.accept_for(
                local_capabilities(), {JOB_KIND: here})),
            poll_s=2.0, can=sorted(local_capabilities()))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        shutil.rmtree(queue.out_dir(job["id"]), ignore_errors=True)
    if "failed" in found:
        raise separation.SeparationError(str(found["failed"]))
    if "vocals" not in found or "instrumental" not in found:
        raise separation.SeparationError(t("err_shared_separation_stopped"))
    return {name: path for name, path in found.items()
            if isinstance(path, Path)}


def tidy_at_start() -> int:
    """At the program's start: rounds of ordinary work still waiting are
    of a run that is gone (the program was closed halfway) - nobody wants
    their answer, so they go, with their files."""
    queue = _queue()
    if queue is None:
        return 0
    count = 0
    try:
        for path in sorted(queue.jobs.glob("*.json")):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(job, dict) or \
                    job.get("kind") not in (JOB_KIND, RENDER_KIND):
                continue
            payload = job.get("payload") or {}
            path.unlink()
            count += 1
            folder = payload.get("folder") or (
                str(Path(payload["mix"]).parent) if payload.get("mix")
                else "")
            if folder:
                shutil.rmtree(queue.root / folder, ignore_errors=True)
    except OSError:
        pass
    return count


def _only(job_id: str, accept):
    """This computer takes only its own round: a waiting round of an
    earlier song (the program was closed halfway) is not its work."""
    return lambda job: job.get("id") == job_id and accept(job)


def _unique(worker_hint: str = "") -> str:
    """A name part no other worker on the same round uses: twins of a
    round write beside each other, never into each other's file."""
    import os

    return f"{os.getpid()}_{time.time_ns()}{worker_hint}"


def _note_own(queue, cls: str, seconds: float) -> None:
    """The time of a round done here, for the next decision."""
    from . import work_queue

    if queue is None:
        return
    try:
        queue.note_speed(work_queue.own_worker(), cls, seconds)
    except OSError:
        pass


def _way_data(way) -> dict:
    from . import separation

    return separation.way_data(way)


def run_round(job: dict, queue, stop) -> dict:
    """A separation for the program, on a helper."""
    from . import separation

    from .local_copy import fetched

    payload = job["payload"]
    way = separation.way_from(payload["way"])
    began = time.monotonic()
    out = queue.out_dir(job["id"])
    # v1.0.23 (B647): the song fetched once, not read over the network.
    with fetched(queue.root, job["id"], [payload["mix"]]) as (mix,), \
            tempfile.TemporaryDirectory(prefix="kt_split_",
                                        ignore_cleanup_errors=True) as folder:
        stems = separation.separate_way(mix, Path(folder) / "work", way)
        out.mkdir(parents=True, exist_ok=True)
        names = {}
        mark = _unique()
        # v1.0.22: every stem, the drums and the rest too (B632).
        for name, path in stems.items():
            target = out / f"{name}_{mark}.wav"
            shutil.copyfile(path, target)
            names[name] = target.name
    return {"stems": names, "seconds": round(time.monotonic() - began, 1)}



# -- the render of a video (v1.0.21) -------------------------------------------------

#: The kind of round a render is in the work queue.
RENDER_KIND = "render_round"
#: What a render needs: ffmpeg, and a processor lane - the card lane of a
#: helper would only take the cores from the processor lane beside it.
RENDER_NEEDS = ("ffmpeg", "processor")


def render_class(options: dict) -> str:
    return (f"render:{options.get('width', 1280)}x"
            f"{options.get('height', 720)}@{options.get('fps', 50)}")


def lines_data(lines) -> list[dict]:
    """Timed lines as plain data, exactly (every field)."""
    from dataclasses import asdict

    return [asdict(line) for line in lines]


def lines_from(data) -> tuple:
    from .timing import Syllable, TimedLine

    return tuple(TimedLine(**dict(item, syllables=tuple(
        Syllable(**syllable) for syllable in item["syllables"])))
        for item in data)


def render_job(queue, key: str, lines, audio: Path, logo: Path, title: str,
               options: dict) -> dict:
    """A render as a job: what it needs copied next to the queue."""
    from . import work_queue

    job_id = work_queue.job_id(f"render|{key}|{time.time_ns()}")
    folder = queue.files / "render" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    names = {}
    for role, source in (("audio", audio), ("logo", logo),
                         ("background", options.get("background_path")),
                         ("font", options.get("font_path"))):
        if source and Path(source).is_file():
            target = folder / f"{role}{Path(source).suffix}"
            shutil.copyfile(source, target)
            names[role] = target.name
    (folder / "lines.json").write_text(json.dumps(lines_data(lines)),
                                       encoding="utf-8")
    plain = {key_: value for key_, value in options.items()
             if key_ not in ("background_path", "font_path")}
    if options.get("font_path") and "font" not in names:
        # A font name the render looks up among the system fonts.
        plain["font_path"] = str(options["font_path"])
    return {"id": job_id, "kind": RENDER_KIND,
            "class": render_class(options), "needs": list(RENDER_NEEDS),
            "label": title,
            "payload": {"folder": folder.relative_to(queue.root).as_posix(),
                        "files": names, "title": title, "options": plain}}


def run_render_round(job: dict, queue, stop) -> dict:
    """A render from a job: on a helper, or here from the same copies."""
    from .local_copy import fetched

    payload = job["payload"]
    # v1.0.23 (B647): the audio, the logo, the background and the font
    # fetched once - ffmpeg read them over the network for minutes.
    with fetched(queue.root, job["id"], [payload["folder"]]) as (folder,):
        return _render_from(job, queue, folder)


def _render_from(job: dict, queue, folder: Path) -> dict:
    from . import video

    payload = job["payload"]
    names = payload["files"]
    options = dict(payload["options"])
    options["colors"] = {key: tuple(value) for key, value in
                         (options.get("colors") or {}).items()}
    lines = lines_from(json.loads((folder / "lines.json").read_text(
        encoding="utf-8")))
    out = queue.out_dir(job["id"])
    began = time.monotonic()
    if "font" in names:
        options["font_path"] = str(folder / names["font"])
    # Rendered on this computer's own disk and put next to the queue
    # when done: ffmpeg does not write to the share for minutes, and a
    # twin of the round never writes into the same file.
    with tempfile.TemporaryDirectory(prefix="kt_render_",
                                     ignore_cleanup_errors=True) as here:
        local = Path(here) / "video.mp4"
        video.render_video(
            lines, folder / names["audio"],
            folder / names["logo"] if "logo" in names else None,
            payload["title"], local,
            background_path=str(folder / names["background"])
            if "background" in names else "", **options)
        out.mkdir(parents=True, exist_ok=True)
        name = f"video_{_unique()}.mp4"
        shutil.copyfile(local, out / name)
    return {"video": name, "seconds": round(time.monotonic() - began, 1)}


def render(lines, audio: Path, logo: Path, title: str, target: Path,
           progress=None, **options) -> Path:
    """The render of :func:`modules.pipeline.run_video`: here, or on a
    helper that is sooner done. Raises what the render raises."""
    from . import __version__, proc, video, work_queue

    queue = None if work_queue.running() else _queue()
    cls = render_class(options)
    wanted = {"class": cls, "needs": list(RENDER_NEEDS)}
    try:
        share = queue is not None and worth_sharing(queue, wanted)
    except OSError:
        share = False
    if not share:
        began = time.monotonic()
        video.render_video(lines, audio, logo, title, target,
                           progress=progress, **options)
        _note_own(queue, cls, time.monotonic() - began)
        return target
    try:
        job = render_job(queue, str(target), lines, audio, logo, title,
                         options)
    except OSError:
        # The share is full or away: here, as always.
        video.render_video(lines, audio, logo, title, target,
                           progress=progress, **options)
        return target
    logger.info(t("log_shared_render"), title)
    outcome: dict = {}

    def here(job_, queue_, cancelled) -> dict:
        if job_["id"] != job["id"]:
            return {"release": True}      # not this video's round
        video.render_video(lines, audio, logo, title, target,
                           progress=progress, **options)
        outcome["here"] = True
        return {"here": True}

    def on_answer(answer: dict) -> None:
        result = answer.get("result") or {}
        if answer["job"]["id"] != job["id"]:
            shutil.rmtree(queue.out_dir(answer["job"]["id"]),
                          ignore_errors=True)
            return
        if result.get("here"):
            return
        if "failed" in result:
            outcome["failed"] = result["failed"]
            return
        outcome["made"] = queue.out_dir(job["id"]) / str(
            result.get("video", ""))
        outcome["worker"] = answer.get("worker", "")
        outcome["seconds"] = result.get("seconds", 0)

    try:
        work_queue.run_jobs(
            queue, [job], __version__, {RENDER_KIND: here}, on_answer,
            proc.stopped_since(proc.stops()),
            local_accept=_only(job["id"], work_queue.accept_for(
                local_capabilities(), {RENDER_KIND: here})),
            poll_s=2.0, can=sorted(local_capabilities()))
        if "made" in outcome:
            # Beside the target first and then in its place, as a render
            # here does (B468): an existing video is only replaced by a
            # whole one - and one open in a player says so.
            spare = target.with_name(target.stem + video.SCRATCH_SUFFIX)
            try:
                shutil.move(str(outcome["made"]), str(spare))
                spare.replace(target)
            except OSError as exc:
                raise video.VideoError(t("err_video_in_use").format(
                    target=target, scratch=spare)) from exc
            logger.info(t("log_shared_render_done"), outcome["worker"],
                        outcome["seconds"])
    finally:
        shutil.rmtree(queue.root / job["payload"]["folder"],
                      ignore_errors=True)
        shutil.rmtree(queue.out_dir(job["id"]), ignore_errors=True)
    if "failed" in outcome:
        raise video.VideoError(str(outcome["failed"]))
    if not (outcome.get("here") or outcome.get("made")):
        raise video.VideoError(t("err_shared_render_stopped"))
    return target
