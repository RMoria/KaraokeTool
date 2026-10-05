"""Test 1.5.20 - the text laid on the voice (v1.0.23, B651/B652).

The owner asked whether there is something besides Whisper worth
trying. The text of every song is known, so rather than let Whisper
guess what is sung and couple that to the text, the forced aligner can
lay the text itself on the voice: it only has to find WHERE each word
is, not WHAT is sung. The program does that already in two small ways -
the words of what Whisper heard (WhisperX) and, since B575, the known
text in stretches where Whisper heard nothing. B651 goes further: every
run of lines whose coupling is weak is laid on in one piece, in the
whole room between the heard lines around it. B605 (1.5.15) is the
other, narrower road: every line on its own, at most 0.75 s around
where the coupling put it.

Measured the yardstick's way, as 1.5.15: on the stored transcriptions,
on a copy of every project next to the work queue, so the projects are
only read; through the queue, on the test set by default. Every round
needs WhisperX - a computer without it takes none of them, so no round
quietly measures the baseline under another name.

Besides the numbers of 1.5.15 - the mean start error, the lines within
0.3 s, the blocks on the right spot - how many lines a variant moved
from where the baseline puts them, and of those how many came closer to
the hand timing and how many went further away.
"""
from __future__ import annotations

from dataclasses import dataclass

from .translations import t

#: A line counts as moved when its start is this far from the baseline.
MOVED_S = 0.05

#: The models this test switches.
CODES = ("B605", "B651")


@dataclass(frozen=True)
class Variant:
    label: str
    on: tuple[str, ...]
    setting: str = ""


#: v1.0.27: B605 is measured (worse) and stays off. B651 moved nothing on
#: 5 October: it took only lines of quality ``syllable``/``word`` as
#: anchors, and at the coupling a line is ``high``, ``medium`` or ``low``
#: - so no line was an anchor, the whole song one stretch, too long for
#: the aligner. Fixed (``pipeline.STRETCH_ANCHORS``); "strong" (only
#: ``syllable``) has no meaning at the coupling and is gone.
VARIANTS = (
    Variant("baseline", ()),
    Variant("B651", ("B651",)),
)


def states_for(variant: Variant) -> dict[str, bool]:
    """As the program runs now, with the models of the variant on and the
    other aligner models off."""
    from . import model_register

    states = {model.code: model_register.enabled(model.code)
              for model in model_register.register()}
    for code in CODES:
        states[code] = code in variant.on
    return states


def needs_of(variant: Variant) -> list[str]:
    """What a computer must have for a round: the baseline too runs where
    the aligner is, so both sides of a comparison come from computers
    that time alike."""
    return ["ffmpeg", "whisperx"]


def movement(base_rows: list[dict], rows: list[dict]) -> dict:
    """How many lines a variant moved from the baseline, and of those how
    many came closer to the hand timing and how many went further."""
    before = {row.get("project", ""): row for row in base_rows}
    moved = better = worse = 0
    for row in rows:
        other = before.get(row.get("project", ""))
        if other is None:
            continue
        old = dict(zip(other.get("hand_index", ()),
                       other.get("new_starts", ())))
        for index, hand, new in zip(row.get("hand_index", ()),
                                    row.get("hand_starts", ()),
                                    row.get("new_starts", ())):
            if index not in old:
                continue
            was = float(old[index])
            if abs(float(new) - was) < MOVED_S:
                continue
            moved += 1
            if abs(float(new) - float(hand)) < abs(was - float(hand)):
                better += 1
            else:
                worse += 1
    return {"moved": moved, "better": better, "worse": worse}


def _number(value, pattern: str = "{:.2f}") -> str:
    return "-" if value is None else pattern.format(value)


def report_text(results: list[tuple[Variant, dict]], songs: int) -> str:
    from . import __version__

    lines = ["# " + t("lyrics_trial_title"), "",
             t("lyrics_trial_intro").format(songs=songs), "",
             t("test_matrix_made_with").format(version=__version__), "",
             t("lyrics_trial_cols"),
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    base = results[0][1]["error"] if results else None
    for variant, found in results:
        change = (found["error"] - base) if (
            found["error"] is not None and base is not None) else None
        moved = ("-" if variant.label == "baseline" else
                 f"{found['moved']} ({found['better']} / {found['worse']})")
        lines.append(
            f"| {variant.label} | {found['lines']} | "
            f"{_number(found['error'])} | {_number(change, '{:+.2f}')} | "
            f"{_number(found['within'], '{:.0f}%')} | "
            f"{_number(found['blocks'], '{:.0f}%')} | {moved} |")
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
    lines += ["", t("lyrics_trial_legend").format(moved=MOVED_S)]
    return "\n".join(lines) + "\n"


def run(context, report, cancelled) -> str:
    """1.5.20 itself, through the work queue. Returns the report."""
    from . import __version__, block_trial, measure_pool, separation_trial
    from . import stem_trial, test_panel, work_queue
    from .front_to_back import songs_with_hand_timing

    songs = songs_with_hand_timing(context)
    if not songs:
        return t("front_to_back_nothing")
    queue = work_queue.queue_for(context).ensure()
    local = separation_trial.local_capabilities() & {"ffmpeg", "whisper",
                                                      "whisperx"}
    # v1.0.26 (B674): the aligner crashed the program; a helper that has
    # it does those rounds.
    local = work_queue.program_capabilities(queue, local)
    if "whisperx" not in local and not stem_trial._somebody_can(
            queue, "whisperx"):
        # Every round needs the aligner: without it they would wait for
        # ever.
        return "# " + t("lyrics_trial_title") + "\n\n" + \
            t("lyrics_trial_no_aligner") + "\n"
    snapshots = {song: block_trial.snapshot(context, song, queue)
                 for song in songs}
    shapes = {}
    for song in songs:
        folder = test_panel._paths_for(context, song).output_dir
        shapes[song] = (block_trial.line_blocks(folder),
                        block_trial.block_kinds(folder))
    jobs = []
    for variant in VARIANTS:
        states = states_for(variant)
        for song in songs:
            key = f"lyr|{__version__}|{variant.label}|{song}|" \
                  f"{snapshots[song]}"
            jobs.append({"id": work_queue.job_id(key),
                         "kind": block_trial.JOB_KIND,
                         "class": "lyr:aligner", "needs": needs_of(variant),
                         "label": f"{song} - {variant.label}",
                         "payload": {"variant": variant.label, "song": song,
                                     "snapshot": snapshots[song],
                                     "states": states,
                                     "setting": variant.setting}})
    ids = {job["id"] for job in jobs}
    rows: dict[str, list] = {variant.label: [] for variant in VARIANTS}
    missing: dict = {}
    steps = test_panel.Steps(report, "1.5.20", len(jobs),
                             plan=["lyr:aligner"] * len(jobs),
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
            block_trial.note_missing(missing, answer)
        steps.tick(kind="lyr:aligner")
        report(0, f"{job.get('label', '')}  ({answer.get('worker', '')})")

    handlers = {block_trial.JOB_KIND: block_trial.run_round}
    work_queue.run_jobs(
        queue, jobs, __version__, handlers, on_answer, cancelled,
        local_accept=work_queue.accept_for(local, handlers),
        local_lanes=measure_pool.worker_count(len(jobs)),
        can=sorted(local))
    results = []
    base = sorted(rows["baseline"], key=lambda r: r.get("project", ""))
    for variant in VARIANTS:
        ordered = sorted(rows[variant.label],
                         key=lambda r: r.get("project", ""))
        found = block_trial.figures(ordered, shapes)
        found.update(movement(base, ordered))
        results.append((variant, found))
    block_trial.remember_errors(context, results, "1.5.20")
    return report_text(results, len(songs)) + \
        block_trial.coverage_text(results, missing)
