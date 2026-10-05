"""Test 1.5.19 - the models on the other stems (v1.0.22, B633-B635).

Measures the drums as the anchor (B633), the breaths and pauses of the
lead voice (B634) and ``[bg]`` from the choir (B635) against the owner's
hand timings, each on its own - the drums with three reaches - and the
three together, on the test set by default (:mod:`modules.test_set`).
The yardstick's way, as 1.5.15: on the stored transcriptions, on a copy
of every project next to the work queue, so the projects are only read.

The stems these models listen to are made first, one round per song
through the queue: the drums of the standard Demucs way, and with the
Roformer environment somewhere in the network the lead voice of the
karaoke model and the choir (its music split by Demucs once more - the
voice of that is the choir). They go into the copy as mp3s, which is
all a model needs; the separations are kept beside 1.5.14's stems
(:mod:`modules.stem_store`), so the next time costs nothing.

Besides the numbers of 1.5.15 - the mean start error, the lines within
0.3 s, the blocks on the right spot - the error of the ``[bg]`` lines
and of the starts of the inline ``[bg]`` pieces, since B635 touches
nothing else. Only one song of the owner has ``[bg]`` (Lied R); the
report says how few they are.
"""
from __future__ import annotations

import logging
import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .translations import t

logger = logging.getLogger(__name__)

#: The kind of job that makes a song's stems for the models.
PREP_KIND = "model_stems_round"
#: The models.
CODES = ("B633", "B634", "B635")


@dataclass(frozen=True)
class Variant:
    label: str
    on: tuple[str, ...]
    setting: str = ""


VARIANTS = (
    Variant("baseline", ()),
    Variant("B633", ("B633",)),
    Variant("B633 0.06 s", ("B633",), "B633 0.06 s"),
    Variant("B633 0.2 s", ("B633",), "B633 0.2 s"),
    Variant("B634", ("B634",)),
    Variant("B635", ("B635",)),
    Variant("B633+B634+B635", CODES),
)


def states_for(variant: Variant) -> dict[str, bool]:
    """As the program runs now, with the models of the variant on and the
    other stem models off."""
    from . import model_register

    states = {model.code: model_register.enabled(model.code)
              for model in model_register.register()}
    for code in CODES:
        states[code] = code in variant.on
    return states


# -- the stems, one round per song ------------------------------------------

def stems_target(snapshot: str, song: str) -> str:
    """Where a song's stems go in its copy (relative to the queue)."""
    from .pipeline import MODEL_STEMS

    return f"{snapshot}/cache/{song}/{MODEL_STEMS}"


def _mp3(source: Path, target: Path) -> None:
    from . import ffmpeg

    target.parent.mkdir(parents=True, exist_ok=True)
    spare = target.with_name(target.stem + ".part.mp3")
    ffmpeg.encode_mp3(source, spare, 44100, 2, vbr_quality=4)
    spare.replace(target)


def prep_round(job: dict, queue, stop) -> dict:
    """The drums, and where Roformer is here the lead voice and the
    choir, of one song, as mp3s in its copy."""
    from .local_copy import fetched

    payload = job["payload"]
    # v1.0.23 (B647): the song fetched once, not read over the network.
    with fetched(queue.root, job["id"], [payload["mix"]]) as (mix,):
        return _prep(payload, queue, mix, stop)


def _prep(payload: dict, queue, mix: Path, stop) -> dict:
    from . import separation
    from .stem_store import StemStore

    target = queue.root / payload["target"]
    store = StemStore(queue.root / payload["stems"]) \
        if payload.get("stems") else None
    made = []
    with tempfile.TemporaryDirectory(prefix="kt_model_stems_",
                                     ignore_cleanup_errors=True) as folder:
        work = Path(folder)
        standard = separation.Way()
        stems = store.get(standard.tag, work / "std") if store else None
        if stems is None or "drums" not in stems:
            stems = separation.separate_way(mix, work / "std", standard,
                                            store)
        if stems.get("drums"):
            _mp3(stems["drums"], target / "drums.mp3")
            made.append("drums")
        karaoke = separation.way_for("roformer", "karaoke")
        if payload.get("karaoke") and separation.is_available(karaoke) \
                and not stop():
            kept = store.get(karaoke.tag, work / "kar") if store else None
            if kept is None:
                kept = separation.separate_way(mix, work / "kar", karaoke,
                                               store)
            _mp3(kept["vocals"], target / "lead.mp3")
            made.append("lead")
            choir = separation.separate_way(kept["instrumental"],
                                            work / "choir", standard)
            _mp3(choir["vocals"], target / "choir.mp3")
            made.append("choir")
    return {"made": made}


def _have(target: Path, karaoke: bool) -> bool:
    names = ["drums"] + (["lead", "choir"] if karaoke else [])
    return all((target / f"{name}.mp3").is_file() for name in names)


def _somebody_can(queue, capability: str) -> bool:
    from . import separation

    if capability == "roformer" and separation.roformer_python() is not None:
        return True
    try:
        return any(capability in (status.get("can") or ())
                   for status in queue.active_workers())
    except OSError:
        return False


# -- the figures ---------------------------------------------------------------

def bg_figures(rows: list[dict]) -> dict:
    """The error of the ``[bg]`` lines and of the inline pieces' starts."""
    lines, pieces = [], []
    for row in rows:
        starts = list(zip(row.get("hand_starts", ()),
                          row.get("new_starts", ())))
        for k in row.get("bg_rows", ()):
            if k < len(starts):
                lines.append(abs(float(starts[k][1]) - float(starts[k][0])))
        pieces += [abs(float(new) - float(hand)) for hand, new
                   in zip(row.get("piece_hand", ()),
                          row.get("piece_new", ()))]

    def mean(values):
        return statistics.mean(values) if values else None

    return {"bg_lines": len(lines), "bg_error": mean(lines),
            "pieces": len(pieces), "piece_error": mean(pieces)}


def _number(value, pattern: str = "{:.2f}") -> str:
    return "-" if value is None else pattern.format(value)


def report_text(results: list[tuple[Variant, dict]], songs: int,
                made: dict[str, int]) -> str:
    from . import __version__

    lines = ["# " + t("stem_trial_title"), "",
             t("stem_trial_intro").format(songs=songs, **made), "",
             t("test_matrix_made_with").format(version=__version__), "",
             t("stem_trial_cols"),
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    base = results[0][1]["error"] if results else None
    for variant, found in results:
        change = (found["error"] - base) if (
            found["error"] is not None and base is not None) else None
        lines.append(
            f"| {variant.label} | {found['lines']} | "
            f"{_number(found['error'])} | {_number(change, '{:+.2f}')} | "
            f"{_number(found['within'], '{:.0f}%')} | "
            f"{_number(found['blocks'], '{:.0f}%')} | "
            f"{_number(found['bg_error'])} ({found['bg_lines']}) | "
            f"{_number(found['piece_error'])} ({found['pieces']}) |")
    names = sorted({song for _v, found in results for song in found["songs"]})
    if names:
        lines += ["", "## " + t("block_trial_head_songs"), "",
                  "| " + t("block_trial_song") + " | "
                  + " | ".join(variant.label for variant, _f in results)
                  + " |", "| --- |" + " ---: |" * len(results)]
        for song in names:
            lines.append(f"| {song} | " + " | ".join(
                _number(found["songs"].get(song)) for _v, found in results)
                + " |")
    lines += ["", t("stem_trial_legend")]
    return "\n".join(lines) + "\n"


# -- the test ------------------------------------------------------------------

def run(context, report, cancelled) -> str:
    """1.5.19 itself, through the work queue. Returns the report."""
    from . import __version__, block_trial, ffmpeg, filesystem, measure_pool
    from . import pipeline, separation_trial, test_panel, work_queue
    from .front_to_back import songs_with_hand_timing

    songs = songs_with_hand_timing(context)
    if not songs:
        return t("front_to_back_nothing")
    queue = work_queue.queue_for(context).ensure()
    snapshots = {song: block_trial.snapshot(context, song, queue)
                 for song in songs}
    shapes = {}
    for song in songs:
        folder = test_panel._paths_for(context, song).output_dir
        shapes[song] = (block_trial.line_blocks(folder),
                        block_trial.block_kinds(folder))
    karaoke = _somebody_can(queue, "roformer")
    root = separation_trial.scratch_root(context)

    # The stems first: one round per song that lacks them.
    prep = []
    for song in songs:
        target = stems_target(snapshots[song], song)
        if _have(queue.root / target, karaoke) or cancelled():
            continue
        folder = queue.files / "sep" / work_queue.job_id(song)
        mix = folder / "original.wav"
        try:
            if not mix.exists():
                project = pipeline.context_for_project(
                    pipeline.read_only(context), song)
                source = filesystem.find_audio_file(
                    project.paths.input_dir, pipeline.TRACK_ORIGINAL)
                if source is None:
                    continue
                folder.mkdir(parents=True, exist_ok=True)
                ffmpeg.convert_to_wav(source, mix)
        except Exception:  # noqa: BLE001 - one song, not the test
            logger.exception(t("log_separation_trial_failed"), song, "-")
            continue
        needs = ["ffmpeg", "demucs"] + (["roformer"] if karaoke else [])
        prep.append({"id": work_queue.job_id(f"stems|{song}|{target}"),
                     "kind": PREP_KIND, "class": "stems:prep",
                     "needs": needs, "label": f"{song} - stems",
                     "payload": {"mix": mix.relative_to(queue.root)
                                 .as_posix(), "target": target,
                                 "karaoke": karaoke,
                                 "stems": separation_trial.stems_folder(
                                     root, queue, song, mix)}})
    jobs = []
    for variant in VARIANTS:
        states = states_for(variant)
        for song in songs:
            key = f"stm|{__version__}|{variant.label}|{song}|" \
                  f"{snapshots[song]}"
            jobs.append({"id": work_queue.job_id(key),
                         "kind": block_trial.JOB_KIND,
                         "class": "stm:plain", "needs": ["ffmpeg"],
                         "label": f"{song} - {variant.label}",
                         "payload": {"variant": variant.label, "song": song,
                                     "snapshot": snapshots[song],
                                     "states": states,
                                     "setting": variant.setting}})
    steps = test_panel.Steps(report, "1.5.19", len(prep) + len(jobs),
                             plan=["stems:prep"] * len(prep)
                             + ["stm:plain"] * len(jobs),
                             forecast=work_queue.forecaster(queue,
                                                            __version__))
    local = separation_trial.local_capabilities()
    if prep:
        ids = {job["id"] for job in prep}

        def on_prep(answer: dict) -> None:
            if answer["job"]["id"] in ids:
                ids.discard(answer["job"]["id"])
                steps.tick(kind="stems:prep")
                report(0, f"{answer['job'].get('label', '')}  "
                          f"({answer.get('worker', '')})")

        handlers = {PREP_KIND: prep_round}
        work_queue.run_jobs(queue, prep, __version__, handlers, on_prep,
                            cancelled,
                            local_accept=work_queue.accept_for(local,
                                                               handlers),
                            can=sorted(local))
        separation_trial._clear_files(queue, "sep")
    made = {name: sum(1 for song in songs
                      if (queue.root / stems_target(snapshots[song], song)
                          / f"{name}.mp3").is_file())
            for name in ("drums", "lead", "choir")}
    ids = {job["id"] for job in jobs}
    rows: dict[str, list] = {variant.label: [] for variant in VARIANTS}
    missing: dict = {}

    def on_answer(answer: dict) -> None:
        job = answer["job"]
        if job["id"] not in ids:
            return
        ids.discard(job["id"])
        row = (answer.get("result") or {}).get("row")
        if row:
            rows[job["payload"]["variant"]].append(row)
        else:
            block_trial.note_missing(missing, answer)
        steps.tick(kind="stm:plain")
        report(0, f"{job.get('label', '')}  ({answer.get('worker', '')})")

    handlers = {block_trial.JOB_KIND: block_trial.run_round}
    if not cancelled():
        work_queue.run_jobs(
            queue, jobs, __version__, handlers, on_answer, cancelled,
            local_accept=work_queue.accept_for({"ffmpeg", "whisper"},
                                               handlers),
            local_lanes=measure_pool.worker_count(len(jobs)),
            can=["ffmpeg", "whisper"])
    results = []
    for variant in VARIANTS:
        ordered = sorted(rows[variant.label],
                         key=lambda r: r.get("project", ""))
        found = block_trial.figures(ordered, shapes)
        found.update(bg_figures(ordered))
        results.append((variant, found))
    block_trial.remember_errors(context, results, "1.5.19")
    return report_text(results, len(songs), made) + \
        block_trial.coverage_text(results, missing)

