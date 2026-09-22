"""Measure the timing against hand-corrected projects.

The user corrects ``timing.json`` by hand in the waveform editor while
``timing_auto.json`` keeps the automatic result. Those two files
together are a ground truth: every line the user moved is a line the
automatic placement got wrong.

This tool runs the REAL pipeline over the stored transcription of every
project and holds the result against the hand-corrected timing. Two
numbers come out of it, and the second matters most:

* how far the still-automatic result is from the hand-corrected times on
  the lines the user moved;
* how many lines the user did NOT touch get worse - those were already
  right, so there is only damage to be done there.

Every manual correction is deliberately stripped from the input first
(B338). The stored sentence coupling contains the user's own corrections
to the original lane; measuring against that flatters the result,
because the timing is then handed an input that was already put right by
hand. Measured: in one project 58 of the 64 original sentences were
hand-set.

    python tools/timing_regression.py <output-map> [--json uit.json]
    python tools/timing_regression.py <output-map> --compare eerder.json
    python tools/timing_regression.py <output-map> --record

``<output-map>`` is the ``output/`` folder of an installation. A project
is measured when it has ``settings/timing.json``,
``settings/timing_auto.json`` and ``original/segments.json``.

The stored ``timing_auto.json`` is often made by a much older version of
the app (its version is in the header), so a comparison against it says
what has improved since then and not what one change is worth. Save a
run with ``--json`` before a change and hold the run after it against it
with ``--compare``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import karaoke_text, song_text               # noqa: E402
from modules import pipeline                              # noqa: E402
from modules import timing_checks                         # noqa: E402
from modules import timing as timing_module               # noqa: E402
from modules.config import default_config                 # noqa: E402
from modules.filesystem import (ProjectPaths, ProjectStore,  # noqa: E402
                                ensure_directories)

#: A line counts as "moved by hand" from this many seconds of shift.
MOVED_S = 0.3

#: Which transcription a project was measured on (B348): "cache" is what
#: the app really couples on (after forced alignment), "ruw" is the
#: diagnostics copy from before that step - only used where the cache has
#: been cleared, and then the number says less.
SOURCE: dict[str, str] = {}

#: Steps in project.json that hold the user's OWN corrections. They are
#: left out when rebuilding, otherwise the measurement is partly marking
#: its own homework (B338).
MANUAL_STEPS = ("original_overrides", "word_coupling", "lyrics_override",
                "transcript_override", "stress_original", "coupling")


def _lines(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["lines"] if isinstance(data, dict) else data


def _start(line: dict) -> float:
    syls = line.get("syllables") or []
    return float(syls[0]["start"]) if syls else 0.0


def _end(line: dict) -> float:
    syls = line.get("syllables") or []
    return float(syls[-1]["end"]) if syls else 0.0


def _build_project(project_dir: Path, work: Path) -> tuple | None:
    """Set up a clean copy of the project and return its context.

    Takes the stored transcription (the diagnostics copy of the
    segments, which survives a cleared cache), the input texts and the
    project data without the manual steps.
    """
    settings = project_dir / "settings"
    segments = project_dir / "original" / "segments.json"
    if not (settings / "project.json").exists() or not segments.exists():
        return None
    song = project_dir.name
    paths = ProjectPaths(root=work, song=song)
    ensure_directories(paths)

    source_input = project_dir / "input"
    if not source_input.is_dir():
        source_input = project_dir.parents[1] / "input" / song
    for name in (song_text.LYRICS_FILENAME, karaoke_text.FILENAME):
        origin = source_input / name
        if origin.exists():
            shutil.copyfile(origin, paths.input_dir / name)
    if not (paths.input_dir / song_text.LYRICS_FILENAME).exists():
        return None

    # B348: the app couples on the CACHE, and that holds the segments
    # AFTER forced alignment; ``original/segments.json`` is written by
    # Whisper before that step and therefore holds the raw, contiguous
    # word times. Measured on Lied D: "Lightning" starts at 10.660 raw
    # against 11.201 aligned, and the twenty-millisecond artefacts that
    # alignment leaves behind (B343) do not occur in the raw file at all.
    # So take the real cache where it is still there, fall back to the
    # diagnostics copy where it has been cleared - and say which of the
    # two it was.
    cache = (project_dir.parents[1] / "cache" / song
             / "transcription_original.json")
    aligned = cache.exists()
    shutil.copyfile(cache if aligned else segments,
                    pipeline.transcript_cache(paths_context(paths),
                                              pipeline.TRACK_ORIGINAL))
    SOURCE[song] = "cache" if aligned else "ruw"

    data = json.loads((settings / "project.json").read_text(encoding="utf-8"))
    steps = {k: v for k, v in (data.get("steps") or {}).items()
             if k not in MANUAL_STEPS}
    data["steps"] = steps
    paths.project_file.parent.mkdir(parents=True, exist_ok=True)
    paths.project_file.write_text(json.dumps(data, ensure_ascii=False),
                                  encoding="utf-8")

    config = default_config()
    config = replace(config, song=replace(config.song, title=song))
    return pipeline.AppContext(paths=paths, config=config,
                               store=ProjectStore(paths.project_file))


def paths_context(paths: ProjectPaths):
    """Minimal stand-in so ``transcript_cache`` can be reused."""
    return pipeline.AppContext(paths=paths, config=default_config(),
                               store=ProjectStore(paths.project_file))


#: B364: the converted vocal stem per project, outside the temporary
#: directory. ``measure()`` makes a fresh temporary directory per call,
#: so without this store ffmpeg ran again for EVERY project on EVERY
#: variant - on the big trial some hundred and ninety times the same
#: work, and that is waiting, not computing.
_VOCALS_READY: dict[str, Path] = {}

#: B384: ONE work directory per project, kept for the life of the
#: process, instead of a fresh ``TemporaryDirectory`` per measurement.
#:
#: The fresh directory looked harmless and cost half the running time.
#: Measured on one project: 1.91 s per measurement, of which 0.97 s was
#: nothing but reading the vocal stem again. The energy envelope in
#: ``rhythm`` is cached on (path, mtime, size) and the path lived inside
#: the temporary directory, so the key was different every single call -
#: 1 miss and 100 hits per measurement, and the miss was the expensive
#: one. On top of that ``_vocals_into_cache`` copied a 50 MB wav on every
#: call, because its "already there?" check also looked inside that
#: fresh directory.
#:
#: Over the big trial (1.5.10, 256 rounds x 12 projects) that is roughly
#: 3000 needless reads and copies. Reusing the directory is safe because
#: ``_build_project`` rewrites ``project.json`` in full from the user's
#: stored project on every call, so no state carries over between
#: variants - which is the whole reason the fresh directory existed.
_WORK_DIRS: dict[str, tempfile.TemporaryDirectory] = {}


def _work_dir(song: str) -> Path:
    """The stable work directory for this project (B384)."""
    keeper = _WORK_DIRS.get(song)
    if keeper is None:
        keeper = tempfile.TemporaryDirectory(prefix=f"kt_yardstick_{song}_")
        _WORK_DIRS[song] = keeper
    return Path(keeper.name)


def _stable_vocals(project_dir: Path, stem: Path) -> Path | None:
    """The converted vocal stem, once per project per run (B364)."""
    kept = _VOCALS_READY.get(project_dir.name)
    if kept is not None and kept.exists():
        return kept
    # B356: through the app's ffmpeg layer. Calling it bare did two
    # things wrong: on Windows a cmd window flashed per project, and it
    # looked for "ffmpeg" in PATH only while the app also looks in its
    # own folder and at the setting.
    from modules import ffmpeg as ffmpeg_module
    store = Path(tempfile.gettempdir()) / "karaoketool_meetlat"
    store.mkdir(parents=True, exist_ok=True)
    target = store / f"{project_dir.name}_vocals.wav"
    if not target.exists():
        try:
            ffmpeg_module.resample_to_match(stem, target, sample_rate=22050,
                                            channels=1)
        except Exception:                # noqa: BLE001 - meting mag door
            return None
    _VOCALS_READY[project_dir.name] = target
    return target


def _vocals_into_cache(project_dir: Path, context) -> None:
    """Put the vocal stem in the cache as wav, so the energy steps run.

    Without it everything falls back neatly, but then the measurement
    covers less than the app really does.
    """
    stem = project_dir / "vocal_demucs.mp3"
    target = context.paths.cache_dir / "original_vocals.wav"
    if not stem.exists() or target.exists():
        return
    kept = _stable_vocals(project_dir, stem)
    if kept is None:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        # B384: a hard link, so the 50 MB is not copied at all. Falls
        # back to copy2 across volumes; that one keeps the modification
        # time, so the energy cache in ``rhythm`` still recognises the
        # file. Together with the stable work directory this happens
        # once per project instead of once per measurement.
        try:
            os.link(kept, target)
        except (OSError, AttributeError):
            shutil.copy2(kept, target)
    except OSError:                      # noqa: BLE001 - meting mag door
        pass


def measure(project_dir: Path) -> dict | None:
    settings = project_dir / "settings"
    hand_path = settings / "timing.json"
    auto_path = settings / "timing_auto.json"
    if not (hand_path.exists() and auto_path.exists()):
        return None
    hand = _lines(hand_path)
    auto = _lines(auto_path)
    if len(hand) != len(auto):
        return None

    # B384: a stable directory per project, so the vocal stem keeps its
    # path and the energy cache in ``rhythm`` actually hits.
    if True:
        context = _build_project(project_dir, _work_dir(project_dir.name))
        if context is None:
            return None
        _vocals_into_cache(project_dir, context)
        try:
            coupling = pipeline.build_coupling(context)
        except Exception:                       # noqa: BLE001 - meting
            coupling = None
        if coupling is None or len(coupling["timed"]) != len(hand):
            return None
        source = coupling["timed"]
        coupled = sum(1 for line in source
                      if line.quality in ("high", "syllable")
                      and line.end > line.start)
        onset = context.store.get_meta("vocal_onset_s")
        duration = max(_end(line) for line in hand) + 5.0
        # B352: the app hands the sung windows to sanitize_timing
        # (pipeline.generate_timing does, via _vocal_windows), the
        # measurement did not. Everything that leans on those windows -
        # B336 for the tail and B344 for a hole in between - was
        # therefore never measured at all; that explains why B336
        # "changed no numbers" back in v0.104.
        fresh = timing_module.sanitize_timing(
            source, first_start=float(onset) if onset is not None else None,
            song_duration=duration,
            active_windows=pipeline._vocal_windows(context))
        fresh = pipeline._snap_lines_to_onsets(context, fresh)

    hand_starts = [_start(line) for line in hand]
    auto_starts = [_start(line) for line in auto]
    new_starts = [line.start for line in fresh]
    moved = [i for i, (a, h) in enumerate(zip(auto_starts, hand_starts))
             if abs(a - h) > MOVED_S]
    kept = [i for i in range(len(hand)) if i not in set(moved)]
    stored = json.loads(auto_path.read_text(encoding="utf-8"))

    def mean(values: list[float]) -> float:
        return statistics.mean(values) if values else 0.0

    return {
        "project": project_dir.name,
        "source": SOURCE.get(project_dir.name, "?"),
        "lines": len(hand),
        "moved": len(moved),
        "coupled": coupled,
        "auto_version": (stored.get("version")
                         if isinstance(stored, dict) else None),
        "hand_starts": hand_starts,
        "new_starts": new_starts,
        "moved_index": moved,
        "auto_moved": mean([abs(auto_starts[i] - hand_starts[i])
                            for i in moved]),
        "new_moved": mean([abs(new_starts[i] - hand_starts[i])
                           for i in moved]),
        "auto_kept": mean([abs(auto_starts[i] - hand_starts[i])
                           for i in kept]),
        "new_kept": mean([abs(new_starts[i] - hand_starts[i])
                          for i in kept]),
        "worse_kept": sum(1 for i in kept
                          if abs(new_starts[i] - hand_starts[i]) >
                          abs(auto_starts[i] - hand_starts[i]) + MOVED_S),
        # B435: the cheap logic checks, run WITH this model state. The
        # weighted error only looks at line starts, so a model can score
        # fine and still leave syllables of length zero or a word on one
        # instant behind - and that is what shows up in the video.
        "sanity": timing_checks.sanity(fresh),
    }


def compare(rows: list[dict], earlier: list[dict]) -> None:
    """Report this run against an earlier one (``--compare``)."""
    before = {row["project"]: row for row in earlier}
    print(f"{'project':<28}{'moved':>7} | {'before':>8}{'now':>8}"
          f"{'gain':>8} | {'untouched worse':>20}")
    print("-" * 84)
    total_before = total_now = weight = damage = 0.0
    for row in rows:
        old = before.get(row["project"])
        if old is None or len(old.get("new_starts", ())) != len(
                row["new_starts"]):
            continue
        hand = row["hand_starts"]
        moved = row["moved_index"]
        kept = [i for i in range(len(hand)) if i not in set(moved)]

        def mean(values: list[float]) -> float:
            return statistics.mean(values) if values else 0.0

        was = mean([abs(old["new_starts"][i] - hand[i]) for i in moved])
        now = mean([abs(row["new_starts"][i] - hand[i]) for i in moved])
        worse = sum(1 for i in kept
                    if abs(row["new_starts"][i] - hand[i]) >
                    abs(old["new_starts"][i] - hand[i]) + MOVED_S)
        total_before += was * len(moved)
        total_now += now * len(moved)
        weight += len(moved)
        damage += worse
        print(f"{row['project']:<28}{len(moved):>7} | {was:>8.2f}{now:>8.2f}"
              f"{was - now:>8.2f} | {worse:>20}")
    print("-" * 84)
    if weight:
        print(f"weighed: {total_before / weight:.2f} s -> "
              f"{total_now / weight:.2f} s")
    print(f"untouched lines that get worse: {int(damage)}")


#: The text of the document itself stays Dutch: ``docs/metingen.md``
#: is the owner's own measurement file, in the language he reads it
#: in. What the tool says on the console is program text and is
#: English like the rest of the tree.
HEADER = """# Meetlat: koppeling en timing per versie

De gebruiker corrigeert `timing.json` met de hand in de golfvorm-editor,
terwijl `timing_auto.json` het automatische resultaat bewaart. Elke regel
die hij heeft verschoven is een regel die de automaat fout had. Dit
bestand houdt per versie bij hoe ver de automaat er nog naast zit.

**Zinnen** is het aantal karaokeregels, **gekoppeld** hoeveel daarvan een
echt gemeten tijd uit de transcriptie kregen (dat is de uitslag van de
koppeling), **verzet** hoeveel regels de gebruiker daarna nog met de hand
heeft verschoven, en **fout op verzette regels** hoe ver de code op
precies die regels van zijn handmatige tijd afligt.

Het gereedschap draait de echte pijplijn over de opgeslagen transcriptie
en laat daarbij alle handmatige correcties weg (B338): de opgeslagen
koppeling bevat de correcties van de gebruiker op de originele baan, en
daartegen meten vleit het resultaat. Het aantal verzette regels ligt vast
in het project en beweegt niet mee: dat is de lijst van plekken waar de
tool het destijds fout had, en die blijft de toetssteen.

Bijwerken: `python tools/timing_regression.py <output-map> --record`.

"""


def note(rows: list[dict], path: Path, version: str, stamp: str) -> None:
    """Add the results of this version to ``docs/metingen.md``."""
    weight = sum(row["moved"] for row in rows) or 1
    average = sum(row["new_moved"] * row["moved"] for row in rows) / weight
    lines = [f"## v{version} — {stamp}", "",
             "| project | zinnen | gekoppeld | verzet | fout op verzette"
             " regels |", "| --- | ---: | ---: | ---: | ---: |"]
    for row in sorted(rows, key=lambda r: r["project"]):
        lines.append(
            f"| {row['project']} | {row['lines']} | {row['coupled']} "
            f"| {row['moved']} | {row['new_moved']:.2f} s |")
    lines += ["", f"Gewogen over {int(weight)} verzette regels: "
              f"**{average:.2f} s**.", ""]
    block = "\n".join(lines)

    if path.exists():
        text = path.read_text(encoding="utf-8")
        heading = f"## v{version} —"
        if heading in text:
            start = text.index(heading)
            stop = text.find("\n## ", start + 1)
            text = text[:start] + block + (text[stop + 1:] if stop >= 0 else "")
        else:
            spot = text.find("\n## ")
            text = (text[:spot + 1] + block + text[spot + 1:] if spot >= 0
                    else text.rstrip() + "\n\n" + block)
    else:
        text = HEADER + block
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    print(f"written down in {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--compare", type=Path, default=None,
                        help="json of an earlier run to measure against")
    parser.add_argument("--record", action="store_true",
                        help="add the result to docs/metingen.md")
    parser.add_argument("--date", default="")
    args = parser.parse_args()

    rows = [row for row in
            (measure(p) for p in sorted(args.output_dir.iterdir())
             if p.is_dir())
            if row]
    if not rows:
        print("no measurable projects found")
        return 1

    if args.record:
        import datetime
        from modules import __version__ as app_version
        stamp = args.date or datetime.date.today().isoformat()
        note(rows, Path(__file__).resolve().parents[1] / "docs" /
             "metingen.md", app_version, stamp)

    if args.compare and args.compare.exists():
        compare(rows, json.loads(args.compare.read_text(encoding="utf-8")))
    else:
        # Deliberately no "worse" column here. This run leaves out the
        # user's manual corrections (B338), so a difference with the
        # stored automatic timing is not damage but the absence of that
        # handwork. Damage is what two runs of THIS tool show against
        # each other - see --compare.
        print(f"{'project':<28}{'lines':>7}{'coupled':>7}{'moved':>7} | "
              f"{'error moved':>12}{'error rest':>11}  source")
        print("-" * 82)
        for row in rows:
            print(f"{row['project']:<28}{row['lines']:>7}{row['coupled']:>7}"
                  f"{row['moved']:>7} | "
                  f"{row['new_moved']:>12.2f}{row['new_kept']:>11.2f}"
                  f"  {row.get('source', '?')}")
        weight = sum(row["moved"] for row in rows) or 1
        new = sum(row["new_moved"] * row["moved"] for row in rows) / weight
        print("-" * 74)
        print(f"weighed error on {int(weight)} moved lines: {new:.2f} s")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
