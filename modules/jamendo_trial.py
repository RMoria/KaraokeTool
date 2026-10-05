"""Test 1.5.16 - other people's songs, front to back (JamendoLyrics, v1.0.19).

Every improvement so far was measured on the owner's own 22 songs with
hand timing - Dutch party songs. That is the program's real work, and
also a risk: what is tuned on 22 songs may be tuned to them. JamendoLyrics
is 79 songs in English, French, German and Spanish of which every word
has its start and end, made by hand: exactly what the owner's hand
timings are for us, on songs that are not his.

Every song is made the way the new "normal karaoke" path makes one: the
original only, the music made from it, the lyrics as both texts, the
words heard, coupled and timed - and every line start held against the
hand timing, the way 1.5.13 did it: the share within 0.3 s, the error
capped at 2 s, the lines more than 2 s off. Per language too, since a
change can help one and cost another.

The files are fetched once from Hugging Face into ``kt_data/jamendo``
next to the work queue and never shipped (the songs carry Creative
Commons licences, most of them non-commercial). A round is one song; it
goes through the work queue, so the helpers take them. What was measured
is kept per song and program version: a new version measures again, the
same one does not.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import statistics
import tempfile
import time
from pathlib import Path

from .translations import t

logger = logging.getLogger(__name__)

#: The dataset on Hugging Face.
REPO = "jamendolyrics/jamendolyrics"
#: The kind of job a round of 1.5.16 is in the work queue.
JOB_KIND = "jamendo_round"
#: The ways a song is made. One for now: the program as it is.
VARIANTS = ("baseline",)


def data_dir(queue) -> Path:
    from . import work_queue

    return work_queue.data_root(queue) / "jamendo"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:80] or "song"


def hand_lines(record: dict) -> list[dict]:
    """The dataset's word times as a hand timing of this program: one
    line per line of the song, one piece per word. Blocks follow the
    empty lines of the song text, where it has them."""
    blocks = _block_of_lines(record.get("text", ""))
    lines: list[dict] = []
    current: list[dict] = []
    for word in record.get("words") or ():
        current.append(word)
        if word.get("line_end"):
            lines.append(_line(len(lines), current))
            current = []
    if current:
        lines.append(_line(len(lines), current))
    for line in lines:
        line["block"] = blocks[line["index"]] \
            if line["index"] < len(blocks) else (blocks[-1] if blocks else 0)
    return lines


def _line(index: int, words: list[dict]) -> dict:
    pieces = [{"text": ("" if n == 0 else " ") + str(word["text"]),
               "start": round(float(word["start"]), 3),
               "end": round(float(word["end"]), 3)}
              for n, word in enumerate(words)]
    return {"index": index, "text": " ".join(str(w["text"]) for w in words),
            "crowd": False, "block": 0, "disabled": False,
            "syllables": pieces}


def _block_of_lines(text: str) -> list[int]:
    """The block number of every non-empty line of a song text."""
    out, block, gap = [], 0, False
    for raw in str(text).splitlines():
        if not raw.strip():
            gap = bool(out)
            continue
        if gap:
            block += 1
            gap = False
        out.append(block)
    return out


def lyrics_text(lines: list[dict]) -> str:
    """The song text the program is given: the lines, an empty line
    between blocks."""
    rows, block = [], None
    for line in lines:
        if block is not None and line["block"] != block:
            rows.append("")
        rows.append(line["text"])
        block = line["block"]
    return "\n".join(rows) + "\n"


def prepare(queue, report=lambda *a: None) -> list[dict]:
    """The songs, fetched once: per song its mp3, its hand timing and
    its text, in ``kt_data/jamendo/songs/<name>``."""
    folder = data_dir(queue)
    ready = folder / "ready.json"
    if ready.exists():
        try:
            return json.loads(ready.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    from huggingface_hub import hf_hub_download

    folder.mkdir(parents=True, exist_ok=True)
    report(0, t("jamendo_trial_download"))
    meta = Path(hf_hub_download(REPO, "metadata.jsonl", repo_type="dataset",
                                local_dir=str(folder / "hf")))
    songs = []
    for raw in meta.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        record = json.loads(raw)
        name = _safe(record.get("name") or record["file_name"])
        target = folder / "songs" / name
        mp3 = target / "original.mp3"
        if not mp3.exists():
            report(0, t("jamendo_trial_download_song").format(song=name))
            fetched = Path(hf_hub_download(
                REPO, record["file_name"], repo_type="dataset",
                local_dir=str(folder / "hf")))
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fetched, mp3)
        lines = hand_lines(record)
        (target / "hand.json").write_text(json.dumps(lines),
                                          encoding="utf-8")
        (target / "lyrics.txt").write_text(lyrics_text(lines),
                                           encoding="utf-8")
        songs.append({"name": name, "language": record.get("language", ""),
                      "folder": target.relative_to(folder).as_posix()})
    ready.write_text(json.dumps(songs), encoding="utf-8")
    return songs


def make_song(folder: Path, language: str, work: Path, cancelled):
    """A normal karaoke of one song in a scratch installation of its
    own: the music made from the original, the words heard with the song
    text as hint, coupled and timed. Returns ``(fresh lines, hand)``."""
    from dataclasses import replace

    from . import karaoke_text, pipeline, song_text
    from .config import default_config
    from .filesystem import ProjectPaths, ProjectStore, ensure_directories
    from .test_panel import _regression_module

    paths = ProjectPaths(root=work, song="song")
    ensure_directories(paths)
    shutil.copy2(folder / "original.mp3", paths.input_dir / "original.mp3")
    shutil.copy2(folder / "lyrics.txt",
                 paths.input_dir / song_text.LYRICS_FILENAME)
    shutil.copy2(folder / "lyrics.txt",
                 paths.input_dir / karaoke_text.FILENAME)
    hand = json.loads((folder / "hand.json").read_text(encoding="utf-8"))
    config = default_config()
    config = replace(config, song=replace(config.song, title="song"))
    context = pipeline.AppContext(paths=paths, config=config,
                                  store=ProjectStore(paths.project_file))
    if language:
        context.store.set_meta("language_choice", language)
    pipeline.make_karaoke_from_original(context)
    pipeline.detect_track(context, pipeline.TRACK_ORIGINAL,
                          cancelled=cancelled)
    made = _regression_module().timing_for(context, hand)
    if made is None:
        return None, hand
    return made[0], hand


def run_round(job: dict, queue, stop) -> dict:
    """One song made front to back and held against its hand timing."""
    from . import whisper
    from .front_to_back import _start
    from .test_panel import _regression_module

    from .local_copy import fetched

    payload = job["payload"]
    began = time.monotonic()
    # v1.0.23 (B647): the song fetched once, not read over the network.
    with fetched(queue.root, job["id"], [payload["folder"]]) as (folder,), \
            tempfile.TemporaryDirectory(prefix="kt_jamendo_",
                                        ignore_cleanup_errors=True) as work:
        try:
            fresh, hand = make_song(folder, payload.get("language", ""),
                                    Path(work), stop)
        except whisper.CancelledError:
            return {"cancelled": True}
    if not fresh:
        return {"failed": t("front_to_back_no_timing")}
    pairs = _regression_module().paired_lines(
        [str(line.get("text", "")) for line in hand],
        [line.text for line in fresh])
    if not pairs:
        return {"failed": t("front_to_back_no_timing")}
    return {"starts": [round(float(fresh[j].start), 3) for _i, j in pairs],
            "hand": [round(_start(hand[i]), 3) for i, _j in pairs],
            "lines": len(hand),
            "seconds": round(time.monotonic() - began, 1)}


def figures(rows: list[dict]) -> dict:
    """Lines, share within 0.3 s, capped mean error, lines > 2 s off."""
    from .front_to_back import CAP_S, WRONG_S

    errors = [abs(now - truth) for row in rows
              for now, truth in zip(row["starts"], row["hand"])]
    if not errors:
        return {"songs": len(rows), "lines": 0}
    return {"songs": len(rows), "lines": len(errors),
            "within": 100.0 * sum(e <= WRONG_S for e in errors) / len(errors),
            "capped": statistics.mean(min(e, CAP_S) for e in errors),
            "runaway": sum(e > CAP_S for e in errors)}


def report_text(results: dict, songs: list[dict], version: str) -> str:
    lines = ["## " + t("jamendo_trial_title"), "",
             t("jamendo_trial_intro").format(count=len(songs)), "",
             t("jamendo_trial_cols"), "| --- |" + " ---: |" * 6]
    for variant in VARIANTS:
        groups: dict[str, list] = {}
        failed: dict[str, int] = {}
        for song in songs:
            row = results.get(f"{song['name']}|{variant}|{version}")
            language = song.get("language") or "?"
            if not row or "failed" in row:
                failed[language] = failed.get(language, 0) + 1
                continue
            groups.setdefault(language, []).append(row)
        everything = [row for rows in groups.values() for row in rows]
        # A language whose songs all failed still gets its row.
        languages = sorted(set(groups) | set(failed))
        for label, rows in [(name, groups.get(name, []))
                            for name in languages] + [
                (t("jamendo_trial_all"), everything)]:
            found = figures(rows)
            fails = sum(failed.values()) if rows is everything \
                else failed.get(label, 0)
            if not found.get("lines"):
                lines.append(f"| {label} | {found['songs']} | 0 | - | - | - "
                             f"| {fails} |")
                continue
            lines.append(f"| {label} | {found['songs']} | {found['lines']} "
                         f"| {found['within']:.1f}% | {found['capped']:.3f} "
                         f"| {found['runaway']} | {fails} |")
    lines += ["", t("jamendo_trial_legend")]
    return "\n".join(lines)


def run(context, report, cancelled) -> str:
    """1.5.16 itself, through the work queue."""
    from . import __version__, test_panel, work_queue
    from .separation_trial import local_capabilities

    queue = work_queue.queue_for(context).ensure()
    try:
        songs = prepare(queue, report)
    except Exception as exc:  # noqa: BLE001 - no data, no test
        logger.exception(t("jamendo_trial_no_data"))
        return t("jamendo_trial_no_data") + f" ({str(exc)[:200]})"
    store_path = data_dir(queue) / "results.json"
    try:
        results = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        results = {}
    if test_panel.REMEASURE:
        results = {key: value for key, value in results.items()
                   if not key.endswith("|" + __version__)}
    jobs = []
    for variant in VARIANTS:
        for song in songs:
            key = f"{song['name']}|{variant}|{__version__}"
            if key in results and "failed" not in results[key]:
                continue
            folder = data_dir(queue) / song["folder"]
            jobs.append({"id": work_queue.job_id("jam|" + key),
                         "kind": JOB_KIND, "class": f"jam:{variant}",
                         "needs": ["ffmpeg", "demucs", "whisper"],
                         "label": f"{song['name']} ({song['language']})",
                         "payload": {"key": key, "language": song["language"],
                                     "folder": Path("..").joinpath(
                                         folder.relative_to(
                                             queue.root.parent)).as_posix()}})
    steps = test_panel.Steps(report, "1.5.16", len(jobs),
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
    return report_text(results, songs, __version__)
