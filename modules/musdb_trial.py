"""Test 1.5.17 - the separations against real stems (MUSDB18, v1.0.19).

1.5.14 judges a separation by what Whisper still hears in the music and
how well it hears the voice: fair, but roundabout. MUSDB18 has songs of
which the real parts exist on their own - the voice, the drums, the
bass, the rest - so a separation can be held against the truth. The
free sample is used: seven seconds of each of the 150 songs, of which
the 50 of the test half are measured. The owner's words: for testing
and optimising, not for the program itself - the files are fetched once
into ``kt_data/musdb`` next to the work queue and never shipped.

Per way of separating (the ways of 1.5.14) and song: how far the voice
it makes is from the real voice, and the music from the real
accompaniment, as the signal-to-distortion ratio in dB (more is
better; +3 dB is half the error energy). The rounds go through the work
queue like every test, so the helpers in the network take them.
"""
from __future__ import annotations

import json
import logging
import shutil
import statistics
import tempfile
import time
import zipfile
from pathlib import Path

import numpy as np

from . import separation
from .translations import t

logger = logging.getLogger(__name__)

#: The free 7-second sample of MUSDB18 (sigsep/sigsep-mus-db).
SAMPLE_URL = ("https://github.com/sigsep/sigsep-mus-db/releases/download/"
              "v0.4.0/MUSDB18-7-STEMS.zip")
#: The kind of job a round of 1.5.17 is in the work queue.
JOB_KIND = "musdb_round"
#: Which half is measured.
SPLIT = "test"


def data_dir(queue) -> Path:
    from . import work_queue

    return work_queue.data_root(queue) / "musdb"


def sdr(reference: np.ndarray, estimate: np.ndarray) -> float:
    """Signal-to-distortion ratio in dB, over the whole excerpt: the
    energy of the truth against the energy of what the estimate gets
    wrong. Both are made the same length and channel count first."""
    count = min(len(reference), len(estimate))
    if count == 0:
        return float("nan")
    ref = np.asarray(reference[:count], dtype=np.float64)
    est = np.asarray(estimate[:count], dtype=np.float64)
    if ref.ndim == 1:
        ref = ref[:, None]
    if est.ndim == 1:
        est = est[:, None]
    if est.shape[1] != ref.shape[1]:
        est = np.repeat(est.mean(axis=1, keepdims=True), ref.shape[1],
                        axis=1)
    error = float(np.sum((ref - est) ** 2))
    energy = float(np.sum(ref ** 2))
    if energy <= 0:
        return float("nan")
    if error <= 0:
        return 100.0
    return 10.0 * float(np.log10(energy / error))


def prepare(queue, report=lambda *a: None) -> list[str]:
    """The tracks of the test half, fetched and taken apart once."""
    from urllib.request import urlopen

    from . import ffmpeg

    folder = data_dir(queue)
    tracks = folder / "tracks"
    done = folder / "ready.json"
    if done.exists():
        try:
            return json.loads(done.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / "MUSDB18-7-STEMS.zip"
    if not archive.exists():
        report(0, t("musdb_trial_download"))
        spare = archive.with_suffix(".part")
        with urlopen(SAMPLE_URL, timeout=120) as answer, \
                open(spare, "wb") as out:
            shutil.copyfileobj(answer, out, 1 << 20)
        spare.replace(archive)
    names = []
    with zipfile.ZipFile(archive) as zipped:
        members = sorted(name for name in zipped.namelist()
                         if name.startswith(SPLIT + "/")
                         and name.endswith(".stem.mp4"))
        for member in members:
            name = Path(member).name[:-len(".stem.mp4")]
            target = tracks / name
            if not (target / "accompaniment.wav").exists():
                with tempfile.TemporaryDirectory() as work:
                    source = Path(work) / "stem.mp4"
                    with zipped.open(member) as src, open(source, "wb") as out:
                        shutil.copyfileobj(src, out)
                    ffmpeg.extract_stems(source, target)
            names.append(name)
    done.write_text(json.dumps(names), encoding="utf-8")
    return names


def ways():
    """The ways of 1.5.14 that make a voice and a music track."""
    from .separation_trial import WAYS

    return [way for way in WAYS if way.measure == "separation"]


def run_round(job: dict, queue, stop) -> dict:
    """One track one way: separate its mixture, hold both results
    against the real parts."""
    from . import audio as audio_module
    from .separation_trial import _dry_stem

    from .local_copy import fetched

    payload = job["payload"]
    way = next(way for way in ways() if way.key == payload["way"])
    began = time.monotonic()
    # v1.0.23 (B647): the track fetched once, not read over the network.
    with fetched(queue.root, job["id"], [payload["track"]]) as (track,), \
            tempfile.TemporaryDirectory(prefix="kt_musdb_",
                                        ignore_cleanup_errors=True) as folder:
        work = Path(folder) / "work"
        stems = separation.separate_way(track / "mixture.wav", work, way.way)
        if way.then:
            stems = dict(stems)
            stems["vocals"] = _dry_stem(separation.separate_roformer(
                stems["vocals"], work / "then", way.then))
        voice, _rate = audio_module.load_audio(stems["vocals"])
        music, _rate = audio_module.load_audio(stems["instrumental"])
        true_voice, _rate = audio_module.load_audio(track / "vocals.wav")
        true_music, _rate = audio_module.load_audio(
            track / "accompaniment.wav")
        return {"voice": round(sdr(true_voice, voice), 2),
                "music": round(sdr(true_music, music), 2),
                "seconds": round(time.monotonic() - began, 1)}


def _mean(values):
    values = [value for value in values if value == value]   # no NaN
    return statistics.mean(values) if values else None


def report_text(results: dict, names, chosen, skipped) -> str:
    """One row per way: its mean over the tracks, and its gain on
    Demucs over the tracks both managed."""
    lines = ["## " + t("musdb_trial_title"), "",
             t("musdb_trial_intro").format(count=len(names)), "",
             t("musdb_trial_cols"), "| --- |" + " ---: |" * 6]
    base = {name: results.get(f"{name}|{chosen[0].tag}") for name in names} \
        if chosen else {}
    for way in chosen:
        rows = {name: results.get(f"{name}|{way.tag}") for name in names}
        good = {name: row for name, row in rows.items()
                if row and "failed" not in row}
        voice = _mean([row["voice"] for row in good.values()])
        music = _mean([row["music"] for row in good.values()])
        both = [name for name in good
                if base.get(name) and "failed" not in base[name]]
        gain = _mean([good[name]["music"] - base[name]["music"]
                      for name in both]) if way is not chosen[0] else 0.0
        seconds = _mean([row.get("seconds", 0.0) for row in good.values()])

        def cell(value, pattern="{:.2f}"):
            return "-" if value is None else pattern.format(value)

        lines.append(f"| {t(f'sep_{way.key}')} | {len(good)} | "
                     f"{cell(voice)} | {cell(music)} | "
                     f"{cell(gain, '{:+.2f}')} | {cell(seconds, '{:.0f}')} "
                     f"| {len(rows) - len(good)} |")
    if skipped:
        lines += ["", t("separation_trial_install_hint")]
    return "\n".join(lines)


def run(context, report, cancelled) -> str:
    """1.5.17 itself, through the work queue."""
    from . import __version__, test_panel, work_queue
    from .separation_trial import local_capabilities, needs_of

    queue = work_queue.queue_for(context).ensure()
    try:
        names = prepare(queue, report)
    except Exception as exc:  # noqa: BLE001 - no data, no test
        logger.exception(t("musdb_trial_no_data"))
        return t("musdb_trial_no_data") + f" ({separation.last_line(str(exc))})"
    store_path = data_dir(queue) / "results.json"
    try:
        results = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        results = {}
    if test_panel.REMEASURE:
        results = {}
    chosen = [way for way in ways() if separation.is_available(way.way)]
    skipped = [way for way in ways() if way not in chosen]
    jobs = []
    for way in chosen:
        for name in names:
            key = f"{name}|{way.tag}"
            if key in results and "failed" not in results[key]:
                continue
            track = (data_dir(queue) / "tracks" / name)
            jobs.append({"id": work_queue.job_id("mus|" + key),
                         "kind": JOB_KIND, "class": f"mus:{way.key}",
                         "needs": needs_of(way),
                         "label": f"{name} - {t(f'sep_{way.key}')}",
                         "payload": {"key": key, "way": way.key,
                                     "track": Path("..").joinpath(
                                         track.relative_to(
                                             queue.root.parent)).as_posix()}})
    steps = test_panel.Steps(report, "1.5.17", len(jobs),
                             plan=[job["class"] for job in jobs],
                             forecast=work_queue.forecaster(queue,
                                                            __version__))
    ids = {job["id"] for job in jobs}

    def on_answer(answer: dict) -> None:
        job = answer["job"]
        result = dict(answer.get("result") or {})
        result["worker"] = answer.get("worker", "")
        key = job["payload"]["key"]
        earlier = results.get(key)
        if not ("failed" in result and earlier and "failed" not in earlier):
            results[key] = result
            try:
                store_path.write_text(json.dumps(results), encoding="utf-8")
            except OSError:
                pass
        if job["id"] in ids:
            ids.discard(job["id"])
            steps.tick(kind=job.get("class"))
            report(0, f"{job.get('label', '')}  ({result['worker']})")

    handlers = {JOB_KIND: run_round}
    work_queue.run_jobs(queue, jobs, __version__, handlers, on_answer,
                        cancelled,
                        local_accept=work_queue.accept_for(
                            local_capabilities(), handlers),
                        can=sorted(local_capabilities()))
    return report_text(results, names, chosen, skipped)
