"""Test 1.5.15 - blocks that come back, timed together (v1.0.15).

Measures the four block models (:mod:`block_timing`, B602-B605) against
the owner's hand timings: each on its own, the fused hearing with three
widths for "the same spot", the three block models together and all
four together. On the stored transcriptions, the yardstick's way - on a
copy of every project in a folder of its own that is thrown away, so the
projects are only read.

Per variant: the mean start error of the lines, the share of lines
within 0.3 s, the share of blocks on the right spot (the median error of
its lines within a second), and the error split by kind of block -
linked blocks (the same text), blocks of the same shape with other words
(verses) and the rest - because the models may help the one and not the
other. And per song, so a song that goes the other way stands out.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from dataclasses import dataclass

from . import song_structure
from .translations import t

#: A block counts as on the right spot when the median error of its
#: lines is within this.
BLOCK_RIGHT_S = 1.0

#: A line counts as right within this.
LINE_RIGHT_S = 0.3

#: The block models.
CODES = ("B602", "B603", "B604", "B605")


@dataclass(frozen=True)
class Variant:
    """One round: the block models switched on, and a setting by name
    (:mod:`model_orders`)."""

    label: str
    on: tuple[str, ...]
    setting: str = ""

    @property
    def kind(self) -> str:
        # The forced alignment costs far more per round than the rest.
        return "lyrics" if "B605" in self.on else "plain"


VARIANTS = (
    Variant("baseline", ()),
    Variant("B602", ("B602",)),
    Variant("B603", ("B603",)),
    Variant("B603 0.05 s", ("B603",), "B603 0.05 s"),
    Variant("B603 0.2 s", ("B603",), "B603 0.2 s"),
    Variant("B604", ("B604",)),
    # v1.0.27: B605 is measured - worse on 19 of 22 songs (1.5.15 and
    # 1.5.20 of 5 October) - and stays off; its rounds are gone, and with
    # them the need for WhisperX in this test.
    Variant("B602+B603+B604", ("B602", "B603", "B604")),
)


def needs_of(variant: Variant) -> list[str]:
    """What a computer must have for a round of this variant. v1.0.23
    (B652): B605 lays the text on with WhisperX, and a helper had no
    WhisperX - its B605 rounds quietly measured the baseline."""
    return ["ffmpeg", "whisperx"] if "B605" in variant.on else ["ffmpeg"]


def states_for(variant: Variant) -> dict[str, bool]:
    """The full model state of a round: as the program runs now, with the
    block models of the variant on and the others off."""
    from . import model_register

    states = {model.code: model_register.enabled(model.code)
              for model in model_register.register()}
    for code in CODES:
        states[code] = code in variant.on
    return states


def block_kinds(project_dir) -> dict[int, str]:
    """Per block of the hand timing: ``linked``, ``shape`` or ``single``.
    The links are the project's own (tab 1), or what the program links."""
    from .timing import FILENAME

    try:
        data = json.loads((project_dir / "settings" / FILENAME)
                          .read_text(encoding="utf-8"))
        project = json.loads((project_dir / "settings" / "project.json")
                             .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    lines = data["lines"] if isinstance(data, dict) else data
    blocks = song_structure.blocks_of(lines)
    step = (project.get("steps") or {}).get(song_structure.STEP)
    links = song_structure.stored_links(step, blocks)
    if links is None:
        links = song_structure.auto_links(blocks)
    linked = {n for group in links for n in group}
    shaped = {n for group in song_structure.shape_groups(blocks)
              for n in group}
    return {block.number: ("linked" if block.number in linked
                           else "shape" if block.number in shaped
                           else "single")
            for block in blocks}


def line_blocks(project_dir) -> list[int]:
    """The block of every hand line, by position."""
    from .timing import FILENAME

    try:
        data = json.loads((project_dir / "settings" / FILENAME)
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    lines = data["lines"] if isinstance(data, dict) else data
    return [int(line.get("block", 0) or 0) for line in lines]


def figures(rows: list[dict], shapes: dict[str, tuple]) -> dict:
    """The numbers of one round. ``shapes`` holds per project
    ``(block per hand line, kind per block)``."""
    errors: list[float] = []
    by_kind: dict[str, list[float]] = {"linked": [], "shape": [],
                                       "single": []}
    blocks_right = blocks_all = 0
    per_song: dict[str, float] = {}
    for row in rows:
        song = row.get("project", "")
        of_line, kinds = shapes.get(song, ([], {}))
        mine: dict[int, list[float]] = {}
        song_errors = []
        for index, hand, new in zip(row.get("hand_index", ()),
                                    row.get("hand_starts", ()),
                                    row.get("new_starts", ())):
            error = float(new) - float(hand)
            errors.append(abs(error))
            song_errors.append(abs(error))
            block = of_line[index] if index < len(of_line) else None
            if block is not None:
                mine.setdefault(block, []).append(error)
                by_kind[kinds.get(block, "single")].append(abs(error))
        for values in mine.values():
            blocks_all += 1
            if abs(statistics.median(values)) <= BLOCK_RIGHT_S:
                blocks_right += 1
        if song_errors:
            per_song[song] = statistics.mean(song_errors)

    def mean(values):
        return statistics.mean(values) if values else None

    return {"lines": len(errors), "error": mean(errors),
            "within": (100.0 * sum(1 for e in errors if e <= LINE_RIGHT_S)
                       / len(errors)) if errors else None,
            "blocks": (100.0 * blocks_right / blocks_all)
            if blocks_all else None,
            "linked": mean(by_kind["linked"]),
            "shape": mean(by_kind["shape"]),
            "single": mean(by_kind["single"]),
            "songs": per_song}


def _number(value, pattern: str = "{:.2f}") -> str:
    return "-" if value is None else pattern.format(value)


def report_text(results: list[tuple[Variant, dict]]) -> str:
    """The report: one table of variants, one of songs."""
    from . import __version__

    lines = ["# " + t("block_trial_title"), "",
             t("block_trial_intro"), "",
             t("test_matrix_made_with").format(version=__version__), "",
             "## " + t("block_trial_head_variants"), "",
             t("block_trial_cols"),
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    base = results[0][1]["error"] if results else None
    for variant, found in results:
        change = (found["error"] - base) if (
            found["error"] is not None and base is not None) else None
        lines.append(
            f"| {variant.label} | {found['lines']} | "
            f"{_number(found['error'])} | {_number(change, '{:+.2f}')} | "
            f"{_number(found['within'], '{:.0f}%')} | "
            f"{_number(found['blocks'], '{:.0f}%')} | "
            f"{_number(found['linked'])} | {_number(found['shape'])} | "
            f"{_number(found['single'])} |")
    songs = sorted({song for _v, found in results for song in found["songs"]})
    if songs:
        lines += ["", "## " + t("block_trial_head_songs"), "",
                  "| " + t("block_trial_song") + " | "
                  + " | ".join(variant.label for variant, _f in results)
                  + " |",
                  "| --- |" + " ---: |" * len(results)]
        for song in songs:
            lines.append(f"| {song} | " + " | ".join(
                _number(found["songs"].get(song)) for _v, found in results)
                + " |")
    lines += ["", t("block_trial_legend").format(
        block=BLOCK_RIGHT_S, line=LINE_RIGHT_S)]
    return "\n".join(lines) + "\n"


def note_missing(missing: dict, answer: dict) -> None:
    """v1.0.27: a round that brought no measurement, by variant - with
    why, so a gap in the tables has a reason in the report."""
    job = answer.get("job") or {}
    payload = job.get("payload") or {}
    result = answer.get("result") or {}
    reason = str(result.get("failed") or "-")[:120]
    missing.setdefault(payload.get("variant", "?"), []).append(
        (payload.get("song", "?"), reason, answer.get("worker", "")))


def remember_errors(context, results: list, source: str) -> None:
    """v1.0.28 (B663): the baseline's start error per song, for the test
    set that builds itself."""
    from . import test_set

    if not results:
        return
    variant, found = results[0]
    if variant.on:
        return
    test_set.note_errors(context, found.get("songs") or {}, source)


def coverage_text(results: list, missing: dict) -> str:
    """v1.0.27: under a report, the rounds without a measurement and the
    errors on only the songs every round measured - the mean of the
    table runs over other songs per round when rounds are missing, and
    then the rounds cannot be compared on it."""
    lines = []
    sets = [set(found.get("songs") or {}) for _v, found in results]
    if sets and any(sets):
        common = sorted(set.intersection(*sets))
        if common:
            parts = []
            for variant, found in results:
                values = [found["songs"][song] for song in common
                          if found["songs"].get(song) is not None]
                mean = sum(values) / len(values) if values else None
                parts.append(f"{variant.label} {_number(mean)}")
            lines += ["", t("trial_common_songs").format(
                count=len(common), values=", ".join(parts))]
    if missing:
        lines += ["", "## " + t("trial_missing_head"), "",
                  t("trial_missing_cols"), "| --- | --- | --- | --- |"]
        for label in sorted(missing):
            for song, reason, worker in sorted(missing[label]):
                lines.append(f"| {label} | {song} | {worker} | {reason} |")
    return ("\n".join(lines) + "\n") if lines else ""


#: The kind of job a round of 1.5.15 is in the work queue (v1.0.19).
JOB_KIND = "block_round"


def snapshot(context, song: str, queue) -> str:
    """What the yardstick reads of a project, copied next to the queue
    once, where every computer can read it: ``kt_werk/files/proj/<id>``
    as an installation of its own. Only read by the rounds; the project
    itself is not touched. Returns the path relative to the queue."""
    import shutil

    from . import filesystem, pipeline, song_text, work_queue
    from . import karaoke_text
    from .timing import FILENAME

    paths = pipeline.context_for_project(pipeline.read_only(context),
                                         song).paths
    wanted = [(paths.output_dir / "settings" / name, Path("output") / song
               / "settings" / name)
              for name in ("project.json", FILENAME, "timing_auto.json")]
    wanted += [(paths.output_dir / "original" / "segments.json",
                Path("output") / song / "original" / "segments.json"),
               (paths.output_dir / "vocal_demucs.mp3",
                Path("output") / song / "vocal_demucs.mp3"),
               (paths.cache_dir / "transcription_original.json",
                Path("cache") / song / "transcription_original.json")]
    for name in (song_text.LYRICS_FILENAME, karaoke_text.FILENAME):
        wanted.append((paths.input_dir / name,
                       Path("input") / song / name))
    karaoke = filesystem.find_audio_file(paths.input_dir,
                                         pipeline.TRACK_KARAOKE)
    if karaoke is not None:
        wanted.append((karaoke, Path("input") / song / karaoke.name))
    # The language collection of the installation (the owner's own
    # words among them) steers the timing too: without it a helper would
    # time differently from the laptop.
    languages = context.paths.languages_dir
    if languages.is_dir():
        wanted += [(path, Path("languages") / path.name)
                   for path in sorted(languages.glob("*.json"))]
    present = [(source, target) for source, target in wanted
               if source.exists()]
    signature = "|".join(f"{target}:{source.stat().st_size}:"
                         f"{int(source.stat().st_mtime)}"
                         for source, target in present)
    folder = Path("files") / "proj" / work_queue.job_id(song + signature)
    base = queue.root / folder
    for source, target in present:
        goal = base / target
        if not goal.exists():
            goal.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, goal)
    return folder.as_posix()


def run_round(job: dict, queue, stop) -> dict:
    """One variant on one song, the yardstick's way, on this computer."""
    from . import measure_pool

    payload = job["payload"]
    item = (str(queue.root / payload["snapshot"]), payload["song"], None,
            tuple(sorted((code, bool(on)) for code, on
                         in payload["states"].items())),
            payload.get("setting", ""))
    rows = measure_pool._serial([item], None, stop)
    return {"row": rows[0]} if rows else {"failed": "no measurement"}


def run(context, report, cancelled) -> str:
    """1.5.15 itself, through the work queue. Returns the report."""
    from . import __version__, measure_pool, test_panel, work_queue
    from .front_to_back import songs_with_hand_timing

    songs = songs_with_hand_timing(context)
    if not songs:
        return t("front_to_back_nothing")
    shapes = {}
    for song in songs:
        folder = test_panel._paths_for(context, song).output_dir
        shapes[song] = (line_blocks(folder), block_kinds(folder))
    queue = work_queue.queue_for(context).ensure()
    snapshots = {song: snapshot(context, song, queue) for song in songs}
    from . import separation_trial, stem_trial

    local = separation_trial.local_capabilities() & {"ffmpeg", "whisper",
                                                      "whisperx"}
    # v1.0.26 (B674): the aligner crashed the program; a helper that has
    # it does those rounds.
    local = work_queue.program_capabilities(queue, local)
    # v1.0.23 (B652): the B605 rounds need WhisperX; with nobody who has
    # it they would wait for ever - they are left out, and said so.
    aligner = "whisperx" in local or stem_trial._somebody_can(queue,
                                                              "whisperx")
    variants = [variant for variant in VARIANTS
                if aligner or "whisperx" not in needs_of(variant)]
    jobs = []
    for variant in variants:
        states = states_for(variant)
        for song in songs:
            key = f"blk|{__version__}|{variant.label}|{song}|" \
                  f"{snapshots[song]}"
            jobs.append({"id": work_queue.job_id(key), "kind": JOB_KIND,
                         "class": f"blk:{variant.kind}",
                         "needs": needs_of(variant),
                         "label": f"{song} - {variant.label}",
                         "payload": {"variant": variant.label, "song": song,
                                     "snapshot": snapshots[song],
                                     "states": states,
                                     "setting": variant.setting}})
    ids = {job["id"] for job in jobs}
    rows: dict[str, list] = {variant.label: [] for variant in variants}
    missing: dict = {}
    steps = test_panel.Steps(report, "1.5.15", len(jobs),
                             plan=[variant.kind for variant in variants
                                   for _song in songs],
                             forecast=work_queue.forecaster(queue,
                                                            __version__))

    def on_answer(answer: dict) -> None:
        job = answer["job"]
        if job["id"] not in ids:
            return
        ids.discard(job["id"])
        row = (answer.get("result") or {}).get("row")
        if row:
            rows[job["payload"]["variant"]].append(row)
        else:
            note_missing(missing, answer)
        steps.tick(kind=job.get("class", "").split(":")[-1])
        report(0, f"{job.get('label', '')}  ({answer.get('worker', '')})")

    handlers = {JOB_KIND: run_round}
    work_queue.run_jobs(
        queue, jobs, __version__, handlers, on_answer, cancelled,
        local_accept=work_queue.accept_for(local, handlers),
        local_lanes=measure_pool.worker_count(len(jobs)),
        can=sorted(local))
    results = [(variant, figures(sorted(rows[variant.label],
                                        key=lambda r: r.get("project", "")),
                                 shapes))
               for variant in variants]
    remember_errors(context, results, "1.5.15")
    text = report_text(results) + coverage_text(results, missing)
    if len(variants) < len(VARIANTS):
        text += "\n" + t("block_trial_no_aligner") + "\n"
    return text
