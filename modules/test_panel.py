"""Test panel behind button 1.5 (TEMPORARY).

A tick list of numbered test functions that run on the user's machine
instead of on mine. Every action gets a number (1.5.1 up to 1.5.10) so
it can be referred to in conversation: "just run 1.5.3". The maximum is
TEN: small tests are merged rather than letting the list grow.

TEMPORARY: this whole file does not belong in a publication. See
``docs/development_log.md``, section "Decide before release".

Agreements that hold for every action:

* The ticks are ALWAYS off when the window opens. A forgotten tick on a
  heavy test costs half an hour, and that must not happen by accident.
* Every action looks at ``cancelled()`` inside its loop, so the Stop
  button works here too.
* An action returns text; that lands in the log window. They write
  nothing to the projects, with exactly two exceptions that say so in
  their own description (1.5.1 fills the cache, 1.5.10 writes the model
  matrix). The measurement history in ``docs/testhistorie.json`` IS
  updated by every action that has a code (B362).
"""
from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from . import measure_pool
from . import model_orders
from . import pipeline
from .translations import t

logger = logging.getLogger(__name__)

#: How an action reports its progress::
#:
#:     report(slot: int, name: str, done: int = 0, total: int = 0) -> None
#:
#: ``slot`` is the work slot (0 or 1) and therefore the bar it lands on,
#: ``name`` the label above it, ``done``/``total`` the state. With
#: ``total`` zero the bar animates instead of filling.
#:
#: B360: this said ``Callable[[str], None]`` - the shape from before
#: B357, when there was still a single bar. Every action in this file was
#: therefore annotated with the WRONG contract, and that is how
#: ``omission_trial`` kept its old ``report(name)`` until it fell over on
#: screen. A type hint that is wrong is worse than none: it actively
#: points the next reader the wrong way.
Reporter = Callable[..., None]


@dataclass(frozen=True)
class TestAction:
    """One numbered action in the panel."""

    code: str
    name_key: str
    explanation_key: str
    #: Does this action work across all projects or only the current one?
    all_projects: bool
    function: Callable[..., str]
    #: B371: a heavy action NEVER joins the 'all' button, and drops out
    #: of the list entirely when there is nothing under it.
    heavy: bool = False
    #: B531: a job, not a measurement. Always in the list, never in the
    #: 'all' tick, and it does not count towards :data:`MAX_ACTIONS` -
    #: that ceiling is about the numbered measurements. Deliberately its
    #: own field and not ``heavy``: this one may not disappear from the
    #: list, and it is not hours of computing either.
    on_request: bool = False

# -- the individual actions ----------------------------------------------

#: B359: the two radio buttons at the bottom of the panel did nothing -
#: the runner simply handed every action the current context and read
#: neither this button nor the action's own ``all_projects`` flag. With
#: this True, ``_projects`` yields only the chosen project. The runner
#: sets it afresh on every run, so a previous choice never lingers.
_ONLY_CURRENT = False


def limit_to_current(yes: bool) -> None:
    """Set the scope for the coming run (B359)."""
    global _ONLY_CURRENT
    _ONLY_CURRENT = bool(yes)


def _projects(context) -> list[str]:
    root = context.paths.output_root
    if not root.is_dir():
        return []
    names = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        paths = pipeline.filesystem.ProjectPaths(
            root=context.paths.root, song=folder.name,
            output_base=context.paths.output_base)
        if paths.project_file.exists():
            names.append(folder.name)
    if _ONLY_CURRENT:
        current = (context.config.song.title or "").strip()
        return [current] if current in names else []
    return names


def across_projects(context, songs, work, report, cancelled,
                    slots: int = 2) -> list[str]:
    """Spread projects over TWO work slots and collect the lines.

    Every slot reports through ``report(slot, name, done, total)`` what it
    is busy with; the panel puts that on its own bar. That way every
    action runs over two lines instead of only 1.5.1, and you can see on
    screen which two projects are running at that moment.

    A project that stumbles does not stop the rest: it becomes a line in
    the result and the queue carries on.
    """
    import threading

    queue = list(songs)
    lines: list[tuple[int, str]] = []
    progress = {"gedaan": 0}
    lock = threading.Lock()
    total = len(queue)

    def worker(slot: int) -> None:
        while True:
            with lock:
                if cancelled() or not queue:
                    return
                position = total - len(queue)
                song = queue.pop(0)
            report(slot, song, progress["gedaan"], total)
            try:
                outcome = work(song)
            except Exception:  # noqa: BLE001 - one project never stops the rest
                logger.exception(t("log_test_project_failed"), song)
                outcome = [t("test_project_failed").format(name=song)]
            with lock:
                progress["gedaan"] += 1
                # B362: an action may also return one composite answer
                # (the yardstick yields a dict per project). Without this
                # split the loop ran over the KEYS of that dict, and that
                # is silently the wrong result.
                if isinstance(outcome, (list, tuple)):
                    for line in outcome:
                        lines.append((position, line))
                elif outcome is not None:
                    lines.append((position, outcome))
                done = progress["gedaan"]
            report(slot, song, done, total)

    # B396: the number of slots is an argument. Two was right for pure
    # Python (more threads only take turns holding the GIL), but Whisper
    # work releases the GIL, so there more slots really do run side by
    # side - see ``measure_pool.whisper_workers``.
    threads = [threading.Thread(target=worker, args=(n,), name=f"test-{n}")
               for n in range(max(1, int(slots)))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return [line for _position, line in sorted(lines, key=lambda r: r[0])]


#: B362: how many projects were skipped on the previous run because a
#: result was already stored for this version AND this state of the
#: project.
SKIPPED: dict[str, int] = {}

#: B362: with this on, every stored result is ignored. The runner sets it
#: afresh on every run from the tick box in the panel.
REMEASURE = False


#: B453: which letters of 1.5.11 to run this time. Empty = all of them,
#: so nothing changes for anyone who just ticks 1.5.11. Set afresh per
#: run, like ``REMEASURE`` and ``limit_to_current``.
_HEAVY_CHOICE: tuple[str, ...] = ()


def limit_heavy_to(codes) -> None:
    """Only run these letters of 1.5.11 (B453)."""
    global _HEAVY_CHOICE
    _HEAVY_CHOICE = tuple(str(code) for code in (codes or ()))


def _wanted(code: str) -> bool:
    return not _HEAVY_CHOICE or code in _HEAVY_CHOICE


def _heavy_fingerprint(context) -> str:
    """One fingerprint over every project a heavy trial looks at (B452).

    The light actions remember per project, and that is right for them:
    they walk projects one by one. 1.5.11a and 1.5.11b measure the SET as
    a whole - one answer over all songs together - so their unit is the
    whole set. Change a file, add a project or switch a model, and this
    changes with it.
    """
    from . import test_history

    parts = [test_history.project_fingerprint(context, song)
             for song in _projects(context)]
    import hashlib

    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def _heavy_done(context, code: str) -> str | None:
    """The version that already ran this trial on this state, or ``None``."""
    from . import __version__, test_history

    saved = test_history.lookup(code, "*", __version__,
                                _heavy_fingerprint(context))
    return __version__ if saved is not None else None


def _remember_heavy(context, code: str, seconds: float) -> None:
    """Note that this trial has been done on this state (B452)."""
    from . import __version__, test_history

    test_history.remember(code, "*", __version__,
                          _heavy_fingerprint(context),
                          {"seconds": round(seconds, 1)}, seconds=seconds)


def with_history(context, songs, work, report, cancelled, code: str,
                 again: bool = False) -> list:
    """Like :func:`across_projects`, but with a memory (B362).

    If a result for this project from THIS version and THIS state of the
    files is already stored, it is reused instead of measured again. The
    fingerprint looks at the project files, the transcription cache AND
    the switched-off models, so new data or a different model means an
    automatic re-measurement.
    """
    from . import __version__, test_history

    SKIPPED[code] = 0
    fingerprints = {song: test_history.project_fingerprint(context, song)
               for song in songs}

    def work_with_memory(song: str):
        import time as _time

        if not (again or REMEASURE):
            saved = test_history.lookup(code, song, __version__,
                                          fingerprints[song])
            if saved is not None:
                SKIPPED[code] += 1
                return saved
        start = _time.monotonic()
        outcome = work(song)
        test_history.remember(code, song, __version__, fingerprints[song],
                              outcome, seconds=_time.monotonic() - start)
        return outcome

    return across_projects(context, songs, work_with_memory, report,
                          cancelled)


def remember_duration(code: str, seconds: float) -> None:
    """The runner reports how long an action took (B370).

    No warning inside the program itself: the number is stored, and the
    question of whether something belongs in 1.5.11 is one I ask when I
    look at the data.
    """
    from . import __version__, test_history

    try:
        test_history.remember_duration(code, __version__, seconds)
    except Exception:  # noqa: BLE001 - measuring must never break running
        logger.exception(t("log_history_delete_failed"), code)


def _skipped_line(code: str) -> list[str]:
    """One line under a table: how much was reused."""
    count = SKIPPED.get(code, 0)
    return [t("test_skipped_note").format(count=count)] if count else []


def _paths_for(context, song):
    """The paths of another project of the same installation."""
    return pipeline.filesystem.ProjectPaths(
        root=context.paths.root, song=song,
        output_base=context.paths.output_base)


def fill_cache(context, report: Reporter, cancelled) -> str:
    """1.5.1 - make everything the measurement needs but does not have.

    Two at a time through :func:`across_projects`: transcribing is the
    slow part and a single run does not fill the machine. A project that
    stumbles does not stop the rest.

    B463: besides the transcription cache this also rebuilds a missing
    ``timing_auto.json``. That file is not handwork - it is what the
    coupling produces - but without it the yardstick skips the project
    entirely, and it does that silently. This is the preparation step
    for measuring, so this is where it belongs. ``timing.json`` is not
    touched: that one IS handwork.
    """
    songs = pipeline.projects_without_cache(context)
    _measurable, missing_auto = _measurable_split(context)
    if not songs and not missing_auto:
        return t("fill_cache_none")
    counter = {"n": 0, "auto": 0}

    def per_project(song: str) -> list[str]:
        other = pipeline.context_for_project(context, song)
        if pipeline.fill_transcription_cache(other, cancelled=cancelled):
            counter["n"] += 1
        return []

    failed = across_projects(context, songs, per_project, report, cancelled)
    rebuilt: list[str] = []
    for song, _why in missing_auto:
        if cancelled():
            break
        other = pipeline.context_for_project(context, song)
        if pipeline.rebuild_auto_timing(other) is not None:
            counter["auto"] += 1
            rebuilt.append(song)
    text = t("fill_cache_done").format(count=counter["n"])
    if rebuilt:
        text += " " + t("fill_cache_auto").format(count=counter["auto"],
                                                  names=", ".join(rebuilt))
    if failed:
        text += " " + "; ".join(failed)
    return text


def benchmark_status(context, report: Reporter, cancelled) -> str:
    """1.5.2 - which projects are measurable, and on what."""
    import json

    def per_project(song: str) -> list[str]:
        paths = _paths_for(context, song)
        cache = paths.cache_dir / "transcription_original.json"
        auto = paths.timing_auto_file
        version, count = "-", "-"
        if auto.exists():
            data = json.loads(auto.read_text(encoding="utf-8"))
            version = str(data.get("version") or "?")
            count = str(len(data.get("lines") or ()))
        return [f"{song:30s} {'ja' if cache.exists() else 'NEE':>6s} "
                f"{'ja' if paths.timing_file.exists() else '-':>7s} "
                f"{count:>7s}  {version}"]

    header = (f"{'project':30s} {'cache':>6s} {'timing':>7s} {'regels':>8s}"
           f"  auto-versie")
    return "\n".join([header] + across_projects(context, _projects(context),
                                            per_project, report, cancelled))


def _text_rows(context, report: Reporter, cancelled) -> list[str]:
    """Lyrics and karaoke text side by side (part of 1.5.3)."""
    from . import karaoke_text
    from . import song_text

    def blocks(path: Path) -> list[int]:
        if not path.exists():
            return []
        sizes, current = [], 0
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                if current:
                    sizes.append(current)
                    current = 0
                continue
            current += 1
        if current:
            sizes.append(current)
        return sizes

    def per_project(song: str) -> list[str]:
        paths = _paths_for(context, song)
        lyrics_blocks = blocks(paths.input_dir / song_text.LYRICS_FILENAME)
        karaoke_blocks = blocks(paths.input_dir / karaoke_text.FILENAME)
        if not lyrics_blocks or not karaoke_blocks:
            return []
        same = (len(lyrics_blocks) == len(karaoke_blocks) and sum(lyrics_blocks) == sum(karaoke_blocks))
        return [f"{song:30s} songtekst {sum(lyrics_blocks):3d}/{len(lyrics_blocks):2d} blok"
                f"  karaoke {sum(karaoke_blocks):3d}/{len(karaoke_blocks):2d} blok"
                f"{'' if same else '   <<< WIJKT AF'}"]

    return across_projects(context, _projects(context), per_project,
                          report, cancelled)


def _filter_rows(context, report: Reporter, cancelled) -> list[str]:
    """What the read-path filters remove (part of 1.5.3)."""
    from . import whisper

    def per_project(song: str) -> list[str]:
        cache_file = (_paths_for(context, song).cache_dir
                   / "transcription_original.json")
        if not cache_file.exists():
            return []
        raw = whisper.load_segments(cache_file)
        n0 = sum(len(seg.words) for seg in raw)
        after_loop = pipeline._drop_repetition_loop(raw)
        n1 = sum(len(seg.words) for seg in after_loop)
        after_boundary = pipeline._merge_boundary_duplicates(after_loop)
        n2 = sum(len(seg.words) for seg in after_boundary)
        n3 = sum(len(seg.words) for seg
                 in pipeline._drop_phantom_words(after_boundary))
        return [f"{song:30s} {n0:8d} {n0 - n1:5d} {n1 - n2:6d} {n2 - n3:6d}"]

    header = (f"{'project':30s} {'woorden':>8s} {'lus':>5s} {'grens':>6s}"
           f" {'spook':>6s}")
    return [header] + across_projects(context, _projects(context), per_project,
                                  report, cancelled)


def _structure_rows(context, report: Reporter, cancelled) -> list[str]:
    """Phrase period, anchors and gaps (part of 1.5.3)."""
    from . import timing as timing_module

    def per_project(song: str) -> list[str]:
        other = pipeline.context_for_project(context, song)
        coupling = pipeline.build_coupling(other)
        if not coupling:
            return []
        lines_ = coupling["timed"]
        period = timing_module.phrase_period(lines_)
        anchors = [i for i, r in enumerate(lines_)
                  if timing_module._reliable(r)]
        gaps = sum(1 for a, b in zip(anchors, anchors[1:]) if b - a > 1)
        return [f"{song:30s} "
                f"{('-' if period is None else f'{period:.2f}'):>8s} "
                f"{len(anchors):7d} {len(lines_):7d} {gaps:6d}"]

    header = (f"{'project':30s} {'periode':>8s} {'ankers':>7s} {'zinnen':>7s}"
           f" {'gaten':>6s}")
    return [header] + across_projects(context, _projects(context), per_project,
                                  report, cancelled)


def project_report(context, report: Reporter, cancelled) -> str:
    """1.5.3 - the three cheap project reports in one action.

    B365: these were 1.5.3 (texts), 1.5.4 (filters) and 1.5.5
    (structure). All three do the same kind of work - one line per
    project out of files that are lying there anyway - and together they
    take less than a minute. The maximum under 1.5 is ten, so small tests
    belong together.
    """
    parts = ((t("test_part_texts"), _text_rows),
             (t("test_part_filters"), _filter_rows),
             (t("test_part_structure"), _structure_rows))
    lines: list[str] = []
    for name, function in parts:
        if cancelled():
            break
        lines += ["", f"--- {name} ---"] + list(
            function(context, report, cancelled))
    return "\n".join(lines).strip() or t("test_no_projects")


def missing_repetitions(context, report: Reporter, cancelled) -> str:
    """1.5.4 - heard but not in the lyrics, across all projects."""
    def per_project(song: str) -> list[str]:
        other = pipeline.context_for_project(context, song)
        lines = []
        for item in pipeline.missing_repetitions(other):
            kind = "herhaling" if item["repetition"] else "onbekend "
            lines.append(f"{song:26s} {item['start']:8.1f} s  {kind}"
                          f"  regel {item['line'] + 1:3d}"
                          f"  {item['text'][:28]}")
        return lines

    lines = across_projects(context, _projects(context), per_project,
                            report, cancelled)
    return "\n".join(lines) or t("test_nothing_found")


_REGRESSION = None


def _regression_module():
    """The yardstick, loaded once (B364).

    This used to sit inside ``_yardstick_rows``, so during the big trial
    the file was read and executed again for every variant - and the
    stock of converted vocal stems was lost every single time.
    """
    global _REGRESSION
    if _REGRESSION is None:
        import importlib.util
        path = (Path(__file__).resolve().parents[1] / "tools"
               / "timing_regression.py")
        spec = importlib.util.spec_from_file_location("regressie", path)
        _REGRESSION = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_REGRESSION)
    return _REGRESSION


def _yardstick_rows(context, report: Reporter, cancelled, code: str = "",
                   again: bool = False, chosen=(),
                   order: str = "") -> list[dict]:
    """The yardstick per project, over two work slots.

    With a ``code`` the result goes through the history (B362): a project
    is skipped when a measurement from this version on this state of the
    files already exists. The big trial deliberately passes NO code - it
    moves the models per variant, and then a stored result from another
    variant is precisely the wrong answer.

    ``chosen`` are the model CODES to set the other way, ``order`` the
    name of an order (B439). Both travel to the child, which builds the
    state itself. They used to be applied with ``setattr`` in the parent
    by the caller, and since B396 the measuring happens in a child - so
    the parent was decorating a room nobody was in. See the note there.
    """
    regression = _regression_module()

    def per_project(song: str):
        return regression.measure(_paths_for(context, song).output_dir)

    if code:
        outcomes = with_history(context, _projects(context), per_project,
                                  report, cancelled, code, again)
        rows = [row for row in outcomes
                if isinstance(row, dict) and "project" in row]
        return sorted(rows, key=lambda r: r["project"])
    # B396: no history means every project really is measured, and that
    # is pure Python - so it belongs on processes and not on two threads
    # that take turns holding the GIL.
    return _rows_over_processes(context, report, cancelled, chosen, order)


def _model_state_now() -> dict:
    """The complete model state, to hand to a child process (B396).

    Explicit rather than "whatever is set": a child interpreter has no
    way of knowing what the parent switched with ``setattr``.
    """
    from . import model_register

    return {model.code: model_register.enabled(model.code)
            for model in model_register.register()}


def _states_with(chosen) -> dict:
    """The complete model state with these codes set the other way (B439).

    One place, so the trial and the search can no longer disagree about
    what "this variant" means. A code that does not exist is ignored
    rather than added: an unknown code in a child would be a warning per
    project per round.
    """
    states = _model_state_now()
    for code in chosen or ():
        if code in states:
            states[code] = not states[code]
    return states


def _rows_over_processes(context, report, cancelled, chosen=(),
                         order: str = "") -> list[dict]:
    """The yardstick over separate interpreters (B396/B439)."""
    from . import measure_pool

    rows = measure_pool.measure_rows(
        context.paths.root, _projects(context),
        context.paths.output_base, _states_with(chosen),
        report=report, cancelled=cancelled, order=order)
    note_alarms(rows, chosen)                    # B435
    return rows


def yardstick(context, report: Reporter, cancelled) -> str:
    """1.5.5 - the yardstick over all projects, previous versions beside it."""
    from . import __version__, test_history

    rows = _yardstick_rows(context, report, cancelled, code="1.5.5")
    if not rows:
        return t("test_no_projects")
    lines = [f"{'project':30s} {'zinnen':>7s}{'gekop.':>7s}{'verzet':>7s} |"
              f" {'fout verzet':>12s}{'fout rest':>11s}"]
    for row in rows:
        lines.append(f"{row['project']:30s} {row['lines']:7d}"
                      f"{row['coupled']:7d}{row['moved']:7d} | "
                      f"{row['new_moved']:12.2f}{row['new_kept']:11.2f}")
    weight = sum(row["moved"] for row in rows) or 1
    error = sum(row["new_moved"] * row["moved"] for row in rows) / weight
    lines.append(t("test_weighted").format(count=int(weight), error=error))
    lines += _skipped_line("1.5.5")
    # B362: next to the previous versions, so a regression stands out in
    # the report itself and not only in somebody's memory.
    comparison = test_history.comparison(
        "1.5.5", [row["project"] for row in rows], __version__, "new_moved")
    if comparison:
        lines += ["", t("test_history_head")] + comparison
    lines += alarm_lines()                       # B435
    return "\n".join(lines)


def syllable_checks(context, report: Reporter, cancelled) -> str:
    """1.5.7 - word and syllable checks per project (B363).

    Three kinds of check, none of them needing a hand-set syllable:
    against the shape (order, overlap, gaps, too short, too fast),
    against the audio (without duration, in silence, distance to the
    onset) and against itself (repeated lines should carry the same
    rhythm).

    B525: the fourth kind is gone. It held the KARAOKE words against the
    measured word boundaries of the ORIGINAL, and in a parody those are
    different words - "app me terug" against "Write to me". Over twenty
    projects it reported between 44% and 76% crossings, which says
    nothing about the timing and everything about the fact that a
    parody has its own words. A number that is always high is not a
    measurement; it is noise that hides the counters that DO mean
    something.
    """
    from . import __version__, test_history
    from . import timing as timing_module
    from . import timing_checks

    def per_project(song: str):
        other = pipeline.context_for_project(context, song)
        coupling = pipeline.build_coupling(other)
        if not coupling:
            return None
        onset = other.store.get_meta("vocal_onset_s")
        lines_ = timing_module.sanitize_timing(
            coupling["timed"],
            first_start=float(onset) if onset is not None else None,
            active_windows=pipeline._vocal_windows(other))
        lines_ = pipeline._snap_lines_to_onsets(other, lines_)
        try:
            lines_ = pipeline._apply_energy_word_timing(other, lines_)
        except Exception:  # noqa: BLE001 - a hint, not production
            pass
        outcome = timing_checks.inspect(other, lines_)
        outcome["project"] = song
        return outcome

    outcomes = with_history(context, _projects(context), per_project,
                              report, cancelled, "1.5.7")
    rows = sorted((u for u in outcomes
                    if isinstance(u, dict) and "project" in u),
                   key=lambda r: r["project"])
    if not rows:
        return t("test_no_projects")
    lines = [t("test_syllable_intro"), "",
              f"{'project':30s} {'regels':>6s}{'woorden':>8s}{'lettergr.':>10s}"
              f" | {'vorm':>5s}{'stilte':>7s}{'tussen':>7s}{'duur':>6s}"
              f"{'inzet':>7s}{'herhaal':>8s}"]
    total = dict(shape=0, silence=0, between=0, duration=0)
    for row in rows:
        shape = (row["out_of_order"] + row["overlapping"] + row["gaps_in_word"]
                + row["too_short"] + row["too_fast_lines"]
                + row["held_not_last"])
        between = (row["empty_lines"] + row["overlapping_lines"]
                   + row["lines_out_of_order"])
        total["shape"] += shape
        total["silence"] += row["in_silence"]
        total["between"] += between
        total["duration"] += row["odd_duration"]
        lines.append(
            f"{row['project']:30s} {row['lines']:6d}{row['words']:8d}"
            f"{row['syllables']:10d} | {shape:5d}{row['in_silence']:7d}"
            f"{between:7d}{row['odd_duration']:6d}"
            f"{row['onset_distance']:6.2f}s{row['repeat_divergence']:8.3f}")
    lines.append("")
    lines.append(t("test_syllable_total").format(
        shape=total["shape"], silence=total["silence"],
        between=total["between"], duration=total["duration"]))
    lines += _skipped_line("1.5.7")
    comparison = test_history.comparison(
        "1.5.7", [row["project"] for row in rows], __version__,
        "in_silence")
    if comparison:
        lines += ["", t("test_history_head")] + comparison
    # B437: three more countings that need no Whisper and no models.
    # Deliberately here and not as an eleventh action: the panel has a
    # ceiling of ten on purpose, and this is the action where the
    # countings over all projects already live.
    lines += ["", ""] + inventory_lines(context, cancelled)
    return "\n".join(lines)


def unique_against_repeated(context, report: Reporter, cancelled) -> str:
    """1.5.6 - error on unique against repeated lines.

    Replaced the separate ``timing_eval`` comparison: that one weighed
    two files against each other, but this split is what the measurement
    really shows - repeated lines are far more wrong than unique ones.
    """
    import json
    from collections import Counter

    unique, repeated = [], []
    lines = [f"{'project':30s} {'uniek':>15s} {'herhaald':>15s}"]
    for row in _yardstick_rows(context, report, cancelled):
        paths = pipeline.filesystem.ProjectPaths(
            root=context.paths.root, song=row["project"],
            output_base=context.paths.output_base)
        texts = [r["text"].strip().lower() for r in
                   json.loads(paths.timing_file.read_text(
                       encoding="utf-8"))["lines"]]
        counts = Counter(texts)
        u, h = [], []
        for index, (hand, new) in enumerate(zip(row["hand_starts"],
                                                  row["new_starts"])):
            (h if counts[texts[index]] > 1 else u).append(abs(new - hand))
        unique += u
        repeated += h
        lines.append(
            f"{row['project']:30s} {len(u):4d} x "
            f"{statistics.mean(u) if u else 0:6.2f} s {len(h):4d} x "
            f"{statistics.mean(h) if h else 0:6.2f} s")
    if unique or repeated:
        lines.append(t("test_unique_repeated").format(
            unique=statistics.mean(unique) if unique else 0.0,
            repeated=statistics.mean(repeated) if repeated else 0.0))
    return "\n".join(lines)


def _variants_from_register(levels=("blok", "zin", "koppeling")):
    """The models the yardstick can see, from the register (B361).

    Yields ``(level, model, targets, on)``. For a model that is ON the
    targets are the neutral replacements ("what does switching off
    cost"); for a model that is OFF they are the real functions ("what
    would switching on gain"). That keeps the matrix symmetrical and lets
    a switched-off idea keep taking part.
    """
    from . import model_register

    # First bring the world in line with the register. Without this a
    # model that is OFF but not yet neutralised drops silently out of the
    # matrix - and those are exactly the ones that must keep taking part.
    model_register.apply_disabled()
    result = []
    for model in model_register.register():
        if model.level not in levels:
            continue
        on = model_register.enabled(model.code)
        if on:
            targets = list(model.targets)
        else:
            # Off: the "other" is the REAL function. It sits aside in the
            # register, because apply_disabled replaced it.
            targets = [(m, a, real) for m, a, real
                      in model_register._DISABLED_NOW.get(model.code, ())]
            if not targets:
                continue
        result.append((model.level, model, targets, on))
    return tuple(result)


def omission_trial(context, report: Reporter, cancelled) -> str:
    """1.5.9 - each check set differently in turn, and measure the cost.

    The quick brother of the big trial: only the individual models, no
    pairs, no orders, no coverage. B361: the list now comes from the
    register instead of from its own copy, so it can no longer lag behind
    reality.
    """
    def weighted(chosen=()) -> float:
        rows = _yardstick_rows(context, report, cancelled, chosen=chosen)
        return _weigh(rows)

    report(0, t("test_leave_out"), 0, 0)
    base = weighted()
    lines = [f"{'variant':34s} {'fout':>7s} {'verschil':>9s}",
              f"{'uitgangspunt':34s} {base:7.2f}"]
    for _level, model, _targets, on in _variants_from_register():
        if cancelled():
            break
        report(0, model.label, 0, 0)
        error = weighted([model.code])
        word = t("test_without") if on else t("test_with")
        lines.append(f"{word} {model.label:<28.28s} {error:7.2f} "
                      f"{error - base:+9.2f}")
    lines.append("")
    lines.append(t("test_model_state").format(state=_state_line()))
    return "\n".join(lines)


def _state_line() -> str:
    from . import model_register
    return model_register.state_line()


# -- 1.5.10: the big trial -----------------------------------------------

#: Where the report of 1.5.10 goes. A constant so a test can redirect it
#: instead of overwriting the real report.
MATRIX_REPORT = Path(__file__).resolve().parents[1] / "docs" / "modelmatrix.md"

#: B361: below this similarity a coupling is called "weak". In v0.115.0
#: the median sat at 1.00 everywhere - saturated, and therefore blind to
#: exactly the question that column was meant for: does a model couple
#: MORE but worse? A share below a threshold does measure that.
_WEAK_COUPLING = 0.75


def _orders():
    """The orders, from :mod:`modules.model_orders` (B439).

    They moved out of here: a child interpreter has to be able to build
    an order too, and this module imports PySide6 at the top - a
    measuring process must not start a widget toolkit. Kept as a name
    here because the guarding tests reach for it.
    """
    return model_orders.build_all()


def _coupling_features(context, song: str) -> dict:
    """Coverage of the word coupling for a project (1.5.10).

    No "error": there is no hand-coupled truth. But more coverage at
    equal quality is demonstrably better, and if a model merely shifts
    words from "no match" to "coupled at 0.3", the share of weak
    couplings shows it.
    """
    other = pipeline.context_for_project(context, song)
    view = pipeline.word_coupling_view(other)
    if not view:
        return {}
    words = view["words"]
    if not words:
        return {}
    counts: dict[str, int] = {}
    for w in words:
        counts[w.get("status", "")] = counts.get(w.get("status", ""), 0) + 1
    coupled = [w for w in words if w["transcript_indices"]]
    sims = [float(w["sim"]) for w in coupled]
    weak = sum(1 for s in sims if s < _WEAK_COUPLING)
    return {
        "project": song,
        "words": len(words),
        "coupled": len(coupled),
        "multiple": sum(1 for w in coupled
                        if len(w["transcript_indices"]) > 1),
        "weak": weak,
        "weak_share": (100.0 * weak / len(sims)) if sims else 0.0,
        "lowest": min(sims) if sims else 0.0,
        "energy": counts.get("energy_placed", 0),
        "gap": counts.get("transcription_gap", 0),
        "filtered": counts.get("hallucination_filtered", 0),
        "filler": counts.get("filler_skipped", 0),
        "no_match": counts.get("no_match", 0),
    }


def _word_features(context, song: str) -> dict:
    """The word and syllable checks for a project (1.5.10, B363)."""
    from . import timing as timing_module
    from . import timing_checks

    other = pipeline.context_for_project(context, song)
    coupling = pipeline.build_coupling(other)
    if not coupling:
        return {}
    onset = other.store.get_meta("vocal_onset_s")
    lines_ = timing_module.sanitize_timing(
        coupling["timed"],
        first_start=float(onset) if onset is not None else None,
        active_windows=pipeline._vocal_windows(other))
    lines_ = pipeline._snap_lines_to_onsets(other, lines_)
    try:
        lines_ = pipeline._apply_energy_word_timing(other, lines_)
    except Exception:  # noqa: BLE001 - a hint, not production
        pass
    outcome = timing_checks.inspect(other, lines_)
    outcome["project"] = song
    return outcome


def big_trial(context, report: Reporter, cancelled) -> str:
    """1.5.10 - what each model is worth, per level and per project.

    Seven sections: the baseline, each model set differently on its own
    (block, sentence and coupling), where it comes into its own, ALL
    pairs, order, the coverage of the word coupling and the
    word/syllable checks. The file is written after EVERY variant to
    ``docs/modelmatrix.md`` - a hang at three in the morning must not
    throw away the whole night.

    B361: the models come from the register, so the trial is
    symmetrical. For a model that is on it measures what switching off
    costs, for a model that is off what switching on would gain. A
    switched-off idea keeps taking part that way, and speaks up the
    moment it IS worth something on new songs.
    """
    import itertools

    report_file = MATRIX_REPORT
    report_file.parent.mkdir(parents=True, exist_ok=True)
    # B534: the copy is made BEFORE this run starts writing, not after
    # it finishes. What has to be saved is the PREVIOUS run, and a run
    # that is stopped or falls over is exactly the run that would
    # otherwise take it with it.
    keep_dated_copy(report_file)
    models = _variants_from_register()
    from . import __version__

    lines: list[str] = [
        "# Modelmatrix", "",
        t("test_matrix_intro"), "",
        t("test_matrix_state").format(state=_state_line()), "",
        # B440: which version made this. Ten versions of nought-reports
        # were indistinguishable from a real one on sight.
        t("test_matrix_made_with").format(version=__version__), "",
    ]

    def write_report() -> None:
        report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def weighted(chosen=(), order: str = "") -> tuple[float, float, dict]:
        """B439: model CODES and an order NAME, not replacements.

        This is the whole repair. The measuring moved to child
        interpreters in B396, but this function kept applying its variant
        with ``setattr`` on module globals in the PARENT - and the child
        rebuilds its world from the state map it is handed, which knew
        nothing of that. So every one of the 256 rounds measured the
        untouched starting position, and the report said +0.00 for all
        twenty models, all 190 pairs and both orders, for ten versions
        long. The route with codes already existed next to it (B410, for
        1.5.11b); it just never arrived here.
        """
        rows = _yardstick_rows(context, report, cancelled,
                               chosen=chosen, order=order)
        error = _weigh(rows)
        damage = (sum(r["new_kept"] for r in rows) / len(rows)) if rows \
            else 0.0
        return error, damage, {r["project"]: round(r["new_moved"], 2)
                              for r in rows}

    base, base_damage, per_project = weighted()
    lines += ["## Uitgangspunt", "",
               f"- gewogen fout: **{base:.2f} s**",
               f"- schade op ongemoeide regels: {base_damage:.2f} s", ""]
    lines += ["| project | fout |", "| --- | ---: |"]
    lines += [f"| {name} | {value:.2f} s |"
               for name, value in sorted(per_project.items())]
    lines += ["", "## Elk model apart anders", "",
               t("test_matrix_symmetry"), "",
               "| niveau | model | stand | fout | verschil | schade |",
               "| --- | --- | --- | ---: | ---: | ---: |"]
    write_report()

    # B402: count the rounds up front. The top bar used to show the
    # progress WITHIN one round, so a run of eight minutes sat at 11%
    # and looked stuck.
    pairs_count = len(models) * (len(models) - 1) // 2
    window_count = len(_variants_from_register(levels=("venster",)))
    word_count = len(_variants_from_register(levels=("woord",)))
    steps = Steps(report, "1.5.10",
                  1 + len(models) + pairs_count + len(model_orders.names())
                  + window_count + 2 + word_count + 1)

    singles: list[tuple] = []
    for level, model, targets, on in models:
        if cancelled():
            break
        steps.tick()
        error, damage, per = weighted([model.code])
        singles.append((level, model, targets, on, error, per))
        lines.append(f"| {level} | {model.label} | "
                      f"{t('test_on') if on else t('test_off')} | "
                      f"{error:.2f} s | {error - base:+.2f} | {damage:.2f} s |")
        write_report()

    lines += ["", "## Waar komt elk model tot zijn recht", "",
               t("test_matrix_where"), "",
               "| model | grootste winst | grootste verlies |",
               "| --- | --- | --- |"]
    for _level, model, _targets, _on, _error, per in singles:
        differences = {p: per.get(p, 0.0) - per_project.get(p, 0.0)
                       for p in per_project}
        if not differences:
            continue
        gain = max(differences.items(), key=lambda kv: kv[1])
        loss = min(differences.items(), key=lambda kv: kv[1])
        lines.append(f"| {model.label} | {gain[0]} {gain[1]:+.2f} s | "
                      f"{loss[0]} {loss[1]:+.2f} s |")
    write_report()

    # B366: no pruning threshold any more. In v0.115.0 only models with
    # an own effect of >=0.02 s entered the pair work, and that very
    # table showed why that is wrong: the anchor check and the energy
    # placement switched off together give 5.66 s where 3.66 was expected
    # from adding them up separately. A model that does nothing on its
    # own can still be a safety net. With the yardstick at ~8 s per run,
    # measuring everything costs half an hour, and that is worth it.
    separate = {m.code: error for _n, m, _d, _a, error, _p in singles}
    lines += ["", "## Twee tegelijk anders", "", t("test_matrix_pairs"), ""]
    count = len(singles) * (len(singles) - 1) // 2
    lines += [t("test_matrix_pairs_all").format(count=count), "",
               "| model A | model B | samen | los opgeteld | verschil |",
               "| --- | --- | ---: | ---: | ---: |"]
    write_report()
    for (_na, ma, da, _aa, _fa, _pa), (_nb, mb, db, _ab, _fb, _pb) in \
            itertools.combinations(singles, 2):
        if cancelled():
            break
        steps.tick()
        error, _damage, _per = weighted([ma.code, mb.code])
        added_up = (separate.get(ma.code, base) - base) + \
                   (separate.get(mb.code, base) - base) + base
        lines.append(f"| {ma.label} | {mb.label} | {error:.2f} s | "
                      f"{added_up:.2f} s | {error - added_up:+.2f} |")
        write_report()

    lines += ["", "## Volgorde", "", t("test_matrix_order"), "",
               "| volgorde | fout | verschil |", "| --- | ---: | ---: |"]
    write_report()
    for name in model_orders.names():
        if cancelled():
            break
        steps.tick()
        # B536: an order that moves a step which is switched off cannot
        # be measured. It used to come out as a tidy "+0.00" - a number
        # for something that was never tried.
        off = model_orders.measurable(name)
        if off:
            lines.append(f"| {name} | {t('test_order_skipped')} "
                          f"({', '.join(off)}) | |")
            write_report()
            continue
        error, _damage, _per = weighted(order=name)
        lines.append(f"| {name} | {error:.2f} s | {error - base:+.2f} |")
        write_report()

    # B364: these two sections ran a plain loop over the projects and
    # therefore used only one work slot. Now through the same spreader as
    # the rest.
    lines += ["", "## Woordkoppeling (dekking)", "",
               t("test_matrix_coupling"), "",
               "| variant | project | woorden | gekoppeld | meervoudig |"
               " zwak | zwak% | laagste | energie | gat | gefilterd |"
               " vulwoord | geen match |",
               "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"
               " ---: | ---: | ---: | ---: | ---: |"]
    write_report()
    window = _variants_from_register(levels=("venster",))
    coupling_variants = [(t("test_all_on"), [])] + [
        (model.label, targets) for _n, model, targets, _a in window]
    if len(window) > 1:
        coupling_variants.append(
            (" + ".join(m.code for _n, m, _d, _a in window),
             [d for _n, _m, targets, _a in window for d in targets]))
    for name, targets in coupling_variants:
        if cancelled():
            break
        steps.tick()
        saved = [(m, a, getattr(m, a)) for m, a, _ in targets]
        for m, a, v in targets:
            setattr(m, a, v)
        try:
            outcomes = across_projects(
                context, _projects(context),
                lambda song: _coupling_features(context, song),
                lambda slot, what, k=0, total=0: report(
                    slot, f"1.5.10 {name}: {what}", k, total),
                cancelled)
        finally:
            for m, a, v in saved:
                setattr(m, a, v)
        for k in sorted((u for u in outcomes
                         if isinstance(u, dict) and u.get("project")),
                        key=lambda r: r["project"]):
            lines.append(
                f"| {name} | {k['project']} | {k['words']} |"
                f" {k['coupled']} | {k['multiple']} | {k['weak']} |"
                f" {k['weak_share']:.1f}% | {k['lowest']:.2f} |"
                f" {k['energy']} | {k['gap']} | {k['filtered']} |"
                f" {k['filler']} | {k['no_match']} |")
        write_report()

    lines += ["", "## Woord en lettergreep", "", t("test_matrix_words"), "",
               "| variant | project | regels | woorden | lettergrepen |"
               " vorm | zonder duur | in stilte |"
               " afstand tot inzet | herhaalverschil |",
               "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"
               " ---: | ---: |"]
    write_report()
    word_variants = [(t("test_all_on"), [])] + [
        (model.label, targets) for _n, model, targets, _a
        in _variants_from_register(levels=("woord",))]
    for name, targets in word_variants:
        if cancelled():
            break
        steps.tick()
        saved = [(m, a, getattr(m, a)) for m, a, _ in targets]
        for m, a, v in targets:
            setattr(m, a, v)
        try:
            outcomes = across_projects(
                context, _projects(context),
                lambda song: _word_features(context, song),
                lambda slot, what, k=0, total=0: report(
                    slot, f"1.5.10 {name}: {what}", k, total),
                cancelled)
        finally:
            for m, a, v in saved:
                setattr(m, a, v)
        for k in sorted((u for u in outcomes
                         if isinstance(u, dict) and u.get("project")),
                        key=lambda r: r["project"]):
            shape = (k["out_of_order"] + k["overlapping"] + k["gaps_in_word"]
                    + k["too_short"] + k["too_fast_lines"]
                    + k["held_not_last"])
            lines.append(
                f"| {name} | {k['project']} | {k['lines']} | {k['words']} |"
                f" {k['syllables']} | {shape} |"
                f" {k['without_duration']} | {k['in_silence']} |"
                f" {k['onset_distance']:.2f} s |"
                f" {k['repeat_divergence']:.3f} |")
        write_report()
    lines += alarm_lines()                       # B435
    write_report()
    return t("test_matrix_done").format(path=report_file.name,
                                        count=len(lines))


# -- 1.5.11: the heavy bin (B371) ----------------------------------------

#: Where the reports of the heavy investigations go.
COMBINATION_REPORT = (Path(__file__).resolve().parents[1] / "docs"
                      / "modelcombinaties.md")

#: The words that 1.5.11d heard, so that "more words" can be CHECKED
#: against the lyrics instead of believed (B410).
CHUNK_WORDS = (Path(__file__).resolve().parents[1] / "docs"
               / "knipwoorden.txt")

#: How much lower the share of words-in-the-lyrics may be than the
#: current run before a variant is disqualified as the merge base
#: (B420). Not zero: cutting hears MORE, and a couple of extra words
#: outside the lyrics is normal - a loop is not a couple.
_PURITY_SLACK = 5.0

#: How many projects 1.5.11d takes, worst hole first (B416). Four runs
#: per song over two Whisper slots is roughly seven minutes a song, so
#: this is about half an hour - a night job, which is what it is filed
#: under. One song was cheaper and said nothing about the rest: cutting
#: makes a new edge at every cut, and whether that costs more than it
#: yields can only show on a song that has little to win.
CHUNK_SONGS = 4

#: From this difference between "together" and "added up separately"
#: onward a pair is called an INTERACTION and both models go into the
#: same cluster. Measured on the benchmark set it stands out: nine of the
#: hundred and thirty-six pairs come above it, and the largest sits at
#: +2.00 (the anchor check with the energy placement). Below 0.10 it is
#: noise on a measurement that itself talks in hundredths of a second.
_INTERACTION = 0.10

#: How many models a cluster may hold at most before exhausting it fully
#: becomes unaffordable. Ten is 1024 measurements, a good three hours -
#: that is still one night. Above that only the hill climb does the work.
_MAX_CLUSTER = 10

#: How many times the hill climb starts over from a different state.
#: Climbing once yields a local optimum; restarting is the cheapest way
#: to notice that there is a better hill next to it.
_RESTARTS = 3

#: Share of the projects that stays outside the search. With 131,072
#: possible combinations and 188 moved lines, a thorough search is
#: guaranteed to find something that scores well by chance; only songs
#: that did NOT take part can show that difference.
_HELD_BACK = 3


#: B397: which heavy trial is running right now. 1.5.11 is four
#: investigations under one number, and the panel showed only "1.5.11"
#: plus a Dutch title - so on screen and in the report there was no way
#: to tell whether you were looking at a, b, c or d. The user could not
#: say which trial to talk about, which is the whole reason those
#: letters exist.
#:
#: Set by ``heavy_trial`` around each investigation, so a trial does not
#: have to be handed its own code through every call.
_RUNNING_CODE = "1.5.11"


def running_code() -> str:
    """The code of the investigation now running (B397)."""
    return _RUNNING_CODE


#: B402: the slot number that means "the action as a whole". The GUI
#: puts that on the top row, so 1.5.10 can say "round 34 of 258" while
#: the work slots show which project they are chewing on. Without this
#: the top bar showed the progress WITHIN one round, and a run of eight
#: minutes looked like it was stuck at 11%.
ACTION_SLOT = -1


class Steps:
    """Counts the rounds of an action, for the top bar (B402).

    Deliberately dumb: the action says up front how many rounds there
    are and ticks one off each time. Guessing a total from the work done
    so far gives a bar that walks backwards, and that is worse than no
    bar.
    """

    def __init__(self, report, label: str, total: int) -> None:
        self._report = report
        self._label = label
        self._total = max(1, int(total))
        self._done = 0
        self.tick(0)

    def name(self, label: str) -> None:
        """Rename the running round (B409).

        1.5.11 is four investigations under one button. With a fixed
        label the top row read "1.5.11  2/4" and the user could see that
        something was running but not WHICH of the four - the letter was
        reported to work slot 0 and overwritten a moment later by the
        first project name.
        """
        self._label = label
        self._report(ACTION_SLOT, self._label, self._done, self._total)

    def tick(self, step: int = 1) -> None:
        self._done = min(self._total, self._done + step)
        self._report(ACTION_SLOT, self._label, self._done, self._total)


class TrialSkipped(Exception):
    """This trial could not measure anything (B385).

    Raised instead of returning the explanation as a normal result, and
    that distinction is the whole point. A trial that bails out - no
    model matrix yet, no clusters, no project with hand-made timing, no
    gap to probe - used to be indistinguishable from one that did the
    work: both returned a list of lines, so both were recorded as "ran"
    and both booked the full version holiday.

    On this project that really happened. 1.5.11a bailed out in 0.2 s on
    v0.118.0 (the scope stood on one project without hand timing, so the
    yardstick gave 0.00 everywhere) and thereby claimed twenty versions
    of silence for a measurement that never took place. Four versions
    later it was still skipping itself, with the user asking why 1.5.11
    was so quick.

    Carries the lines that belong in the report, so the reason is still
    written down - it just does not count as a run.
    """

    def __init__(self, lines) -> None:
        super().__init__(" ".join(lines))
        self.lines = list(lines)


@dataclass(frozen=True)
class HeavyTrial:
    """One investigation under 1.5.11."""

    code: str
    name_key: str
    function: Callable[..., list]
    #: B454: switched off, not deleted - the same way a model is. Its
    #: question has been answered and the answer is in production; the
    #: idea stays readable and is one word away from measuring again.
    off: bool = False
    #: Why it is off, for the report.
    reason: str = ""


#: What the logic checks found during the model measurements (B435).
#: Filled by every measurement, emptied at the start of an action, and
#: written under the report so a model that wrecks the shape of a line
#: cannot hide behind an average that only weighs line starts.
_SANITY_ALARMS: list = []


def reset_alarms() -> None:
    """Forget the alarms of the previous action (B435)."""
    _SANITY_ALARMS.clear()


def note_alarms(rows, chosen=()) -> None:
    """Remember which measurement left broken timing behind (B435)."""
    from . import timing_checks

    for row in rows:
        if not isinstance(row, dict):
            continue
        counts = row.get("sanity")
        if isinstance(counts, dict) and timing_checks.broken(counts):
            _SANITY_ALARMS.append({
                "project": row.get("project", "?"),
                "models": ", ".join(chosen) or t("test_all_on"),
                "counts": {k: v for k, v in counts.items() if v},
            })


def alarm_lines() -> list[str]:
    """The alarms as report lines, or a single reassuring one (B435).

    For a report BODY, where the reassuring line belongs: it says the
    check ran and found nothing.
    """
    rows = alarm_rows()
    return [""] + rows if rows else ["", t("sanity_all_clear")]


def alarm_rows() -> list[str]:
    """The alarm table, and nothing at all when there is no alarm (B537).

    For a place that only wants to show something when something IS
    wrong - the run report puts a heading "Alarms" above it, and under
    such a heading an all-clear reads as an alarm.
    """
    if not _SANITY_ALARMS:
        return []
    lines = [t("sanity_found").format(count=len(_SANITY_ALARMS)), "",
             "| project | anders gezet | wat er mis is |",
             "| --- | --- | --- |"]
    seen = set()
    for alarm in _SANITY_ALARMS:
        key = (alarm["project"], alarm["models"])
        if key in seen:
            continue
        seen.add(key)
        wat = ", ".join(f"{name} {value}"
                        for name, value in sorted(alarm["counts"].items()))
        lines.append(f"| {alarm['project']} | {alarm['models']} | {wat} |")
    return lines


def _weigh(rows) -> float:
    weight = sum(r["moved"] for r in rows) or 1
    return sum(r["new_moved"] * r["moved"] for r in rows) / weight


def _measure(context, report, cancelled, chosen, songs=None) -> float:
    """The weighted error with these models set the other way (B410).

    ``chosen`` are model CODES, not ``(module, attribute, replacement)``
    triples. That change is what lets this measurement run over separate
    interpreters: a triple contains a live function object and cannot be
    handed to a process, a code can. The child rebuilds the state itself
    from the complete on/off map.

    That matters because this is the busiest measurement there is.
    1.5.11b walks two hundred and forty of these rounds, and until now
    every one of them ran over two threads that take turns holding the
    GIL - one core of the twelve, which the user saw in the task manager
    and asked about more than once. Over the pool it is the same work on
    nine interpreters.
    """
    from . import measure_pool

    rows = measure_pool.measure_rows(
        context.paths.root, songs or _projects(context),
        context.paths.output_base, _states_with(chosen),
        report=report, cancelled=cancelled)
    note_alarms(rows, chosen)                    # B435
    return _weigh([r for r in rows
                  if isinstance(r, dict) and "project" in r])


def _pairs_from_report() -> list[tuple[str, str, float]]:
    """The interactions from the last model matrix (1.5.10).

    Deliberately reused instead of measured again: those hundred and
    thirty-six pairs cost half an hour, and they are already there. With
    no report this returns nothing and the trial says 1.5.10 has to run
    first - better than silently gambling on one big cluster.
    """
    if not MATRIX_REPORT.exists():
        return []
    text = MATRIX_REPORT.read_text(encoding="utf-8")
    head_at = text.find("## Twee tegelijk anders")
    if head_at < 0:
        return []
    end_at = text.find("\n## ", head_at + 4)
    result = []
    for line in text[head_at:end_at if end_at > 0
                       else len(text)].splitlines():
        fields = [v.strip() for v in line.strip().strip("|").split("|")]
        if len(fields) != 5 or "---" in line:
            continue
        try:
            difference = float(re.search(r"-?\d+\.\d+", fields[4]).group())
        except (AttributeError, ValueError):
            continue
        result.append((fields[0], fields[1], difference))
    return result


def flat_report(pairs) -> bool:
    """Is this matrix a measurement, or a broken one (B440)?

    Between v0.128.0 and v0.137.0 the trial measured the untouched
    starting position every round, and the pair table came out with
    +0.00 on all hundred and ninety lines. That is not a finding, and
    the cluster trial happily read it as one: no interaction anywhere,
    so nothing to exhaust, and it said so in a report for months.

    A real measurement never gives exactly nought a hundred and ninety
    times over - one project moving by a hundredth is enough to break
    it. So "every difference exactly nought" means the file is rubbish,
    not that the models are independent.
    """
    return bool(pairs) and all(difference == 0.0
                               for _a, _b, difference in pairs)


def clusters_from_pairs(pairs) -> list[set]:
    """Groups of models that demonstrably touch each other (B371).

    Two models sit in the same cluster when their pair deviates from the
    sum of their separate effects by more than ``_INTERACTION``. A model
    that touches nobody needs no cluster: for that one the single-model
    table of 1.5.10 is already the whole answer.
    """
    groups: list[set] = []
    for a, b, difference in pairs:
        if abs(difference) < _INTERACTION:
            continue
        touching = [g for g in groups if a in g or b in g]
        new = {a, b}
        for g in touching:
            new |= g
            groups.remove(g)
        groups.append(new)
    return sorted(groups, key=len, reverse=True)


def _measurable_projects(context) -> list[str]:
    """The projects the yardstick can say anything about (B378/B410).

    Without a hand-made ``timing.json`` there is nothing to compare
    against and the error comes out at 0.00 for every model - a project
    that thereby quietly waters down the average. 1.5.11a already
    checked this; the search did not, and so it reported "searched on 14
    songs" while twelve were measured.
    """
    return [song for song, _why in _measurable_split(context)[0]]


def _measurable_split(context):
    """(measurable, skipped-with-reason) - and say so (B462).

    The yardstick needs BOTH ``timing.json`` and ``timing_auto.json``: it
    measures how far the hand moved the automatic timing, so with one of
    the two it returns nothing at all. This function only looked at the
    first, so a project without the automatic file counted towards
    "measured on 16 projects" while contributing nothing - which is
    exactly the kind of quiet miscounting the docstring above claims to
    have solved. Lied_Q and Lied_O were in that position for
    a day without a word anywhere.
    """
    measurable, skipped = [], []
    for song in _projects(context):
        settings = _paths_for(context, song).output_dir / "settings"
        hand = (settings / "timing.json").exists()
        auto = (settings / "timing_auto.json").exists()
        if hand and auto:
            measurable.append((song, ""))
        elif hand:
            skipped.append((song, "no_auto"))
        # No hand timing at all is not worth reporting: there is simply
        # nothing to measure there, and that is the normal state of a
        # project nobody has timed yet.
    return measurable, skipped


def _skipped_projects_note(context) -> list[str]:
    """A line naming what falls outside the measurement, if anything."""
    _measurable, skipped = _measurable_split(context)
    if not skipped:
        return []
    return ["", t("test_skipped_projects").format(
        names=", ".join(song for song, _why in skipped))]


def cluster_trial(context, report, cancelled) -> list[str]:
    """ALL combinations within each cluster (B371).

    Exhausting all seventeen models fully is 131,072 measurements, a good
    four hundred hours. But nine of the seventeen touch nobody, and the
    rest falls apart into two small clusters - and then 2^6 + 2^2 = 68
    measurements buy exactly the same knowledge.
    """
    import itertools

    from . import model_register

    # B410: the CODE per label, no longer the setattr triples - the
    # measurement runs in a child interpreter and a code travels, a
    # function object does not.
    models = {m.label: m.code for _n, m, _targets, _a
                in _variants_from_register()}
    pairs = _pairs_from_report()
    if not pairs:
        raise TrialSkipped([t("heavy_needs_matrix")])
    if flat_report(pairs):                       # B440
        raise TrialSkipped([t("heavy_flat_matrix")])
    groups = [g for g in clusters_from_pairs(pairs)
               if all(name in models for name in g)]
    if not groups:
        raise TrialSkipped([t("heavy_no_clusters")])

    # B378: first check whether there is anything to measure at all.
    # Without a project with hand-made timing the yardstick gives 0.00
    # everywhere, and then this trial did sixty-eight measurements of
    # nothing and put the result in the report as a table - which reads
    # as "not one model does anything". The search already checked this.
    measurable = _measurable_projects(context)
    if not measurable:
        raise TrialSkipped([t("heavy_no_measurable")])
    base = _measure(context, report, cancelled, [])
    lines = [t("heavy_cluster_intro"), "",
              f"- gemeten op {len(measurable)} project(en) met handmatige timing",
              f"- uitgangspunt: **{base:.2f} s**",
              f"- {model_register.state_line()}"]
    lines += _skipped_projects_note(context) + [""]     # B462
    for number, group in enumerate(groups, start=1):
        members = sorted(group)
        if len(members) > _MAX_CLUSTER:
            lines.append(t("heavy_cluster_too_big").format(
                count=len(members), max=_MAX_CLUSTER,
                names=", ".join(members)))
            continue
        lines += ["", f"### Cluster {number}: {len(members)} modellen", "",
                   "| combinatie (anders gezet) | fout | verschil |",
                   "| --- | ---: | ---: |"]
        for count in range(len(members) + 1):
            for choice in itertools.combinations(members, count):
                if cancelled():
                    return lines
                report(0, f"{running_code()} {number}/{len(groups)}: "
                          f"{len(choice)} van {len(members)}", 0, 0)
                error = _measure(context, report, cancelled,
                                 [models[name] for name in choice])
                name = " + ".join(k.split()[0] for k in choice) or t("test_all_on")
                lines.append(f"| {name} | {error:.2f} s | "
                              f"{error - base:+.2f} |")
    return lines


def _climb(context, report, cancelled, models, songs, base) -> tuple:
    """One climb: add the best single switch each time, until nothing helps."""
    chosen: list[str] = []
    current = base
    measurements = 0
    while True:
        best, best_error = None, current
        for name in models:
            if name in chosen or cancelled():
                continue
            report(0, f"{running_code()} klim {len(chosen) + 1}: {name}", 0, 0)
            combined = [models[k] for k in chosen + [name]]
            error = _measure(context, report, cancelled, combined, songs)
            measurements += 1
            if error < best_error - 0.001:
                best, best_error = name, error
        if best is None:
            return chosen, current, measurements
        chosen.append(best)
        current = best_error


def search_trial(context, report, cancelled) -> list[str]:
    """Climb to the best combination, and check it separately (B371).

    Exhausting is an inventory, this is a choice. From the current state
    take the switch that gains the most each time, until nothing helps
    any more; starting over a few times covers the case where you ended
    up on a lower hill.

    The last step is the most important one. With 131,072 possible states
    and 188 moved lines, a thorough search is guaranteed to find
    something that scores well by chance. That is why part of the songs
    stays OUTSIDE the search, and only what the found combination does on
    those held-back songs counts.
    """
    import random

    # B410: only projects that can actually be measured, and spread
    # instead of the alphabetical tail.
    #
    # ``all_songs[-3:]`` gave, on this collection, Lied_S,
    # Lied_T and Lied_U - and the last of those
    # has no hand-made timing, so it weighs nothing. Three held-back
    # songs on paper, two in reality, and one of those two happened to
    # be the worst song there is. The conclusion "this overfits" still
    # stood, but the +7.21 s that carried it was one song. Spreading
    # takes every third measurable project, so the control set is not
    # systematically the end of the alphabet.
    all_songs = _measurable_projects(context)
    if len(all_songs) <= _HELD_BACK + 1:
        raise TrialSkipped(
            [t("heavy_too_few_songs").format(count=len(all_songs))])
    step = max(1, len(all_songs) // _HELD_BACK)
    held = [all_songs[i * step] for i in range(_HELD_BACK)]
    search = [s for s in all_songs if s not in held]
    models = {m.label: m.code for _n, m, _targets, _a
                in _variants_from_register()}

    base_search = _measure(context, report, cancelled, [], search)
    base_held = _measure(context, report, cancelled, [], held)
    lines = [t("heavy_search_intro"), "",
              t("heavy_search_split").format(
                  search=len(search), held=len(held),
                  names=", ".join(held)), "",
              f"- uitgangspunt zoekset: **{base_search:.2f} s**",
              f"- uitgangspunt achtergehouden: **{base_held:.2f} s**", "",
              "| start | gevonden combinatie | zoekset | achtergehouden |"
              " metingen |", "| --- | --- | ---: | ---: | ---: |"]
    names = list(models)
    chooser = random.Random(20240812)      # fixed sequence: repeatable
    best_overall = None
    for attempt in range(_RESTARTS):
        if cancelled():
            break
        preset = [] if attempt == 0 else chooser.sample(
            names, k=min(3, len(names)))
        start_codes = [models[k] for k in preset]
        start_error = (base_search if not preset
                      else _measure(context, report, cancelled, start_codes,
                                 search))
        chosen, error, measurements = _climb(context, report, cancelled,
                                        {k: v for k, v in models.items()
                                         if k not in preset},
                                        search, start_error)
        combination = preset + chosen
        on_held = _measure(context, report, cancelled,
                           [models[k] for k in combination], held)
        label = " + ".join(k.split()[0] for k in combination) or t("test_all_on")
        lines.append(
            f"| {'huidige stand' if attempt == 0 else f'willekeurig {attempt}'} |"
            f" {label} | {error:.2f} s ({error - base_search:+.2f}) |"
            f" {on_held:.2f} s ({on_held - base_held:+.2f}) |"
            f" {measurements} |")
        if best_overall is None or error < best_overall[1]:
            best_overall = (combination, error, on_held)
    if best_overall:
        combination, error, on_held = best_overall
        # B410: the same sign convention as the table above it. The
        # verdict counted a gain positive while the table counted the
        # difference, so one line read "+0.32" and the other "(-0.32)"
        # for the very same measurement.
        gain_on_search = error - base_search
        gain_on_held = on_held - base_held
        lines += ["", t("heavy_search_verdict").format(
            gain=gain_on_search, held=gain_on_held,
            names=", ".join(k.split()[0] for k in combination) or "-")]
        if -gain_on_held < -gain_on_search / 2:
            lines.append(t("heavy_search_overfit"))
    return lines


def probe_language(context, song: str) -> str:
    """ONE language for the whole song, for every Whisper trial (B403).

    The app has done this properly for a long time:
    ``pipeline._language_for`` decides once, from the COMPLETE lyrics -
    a manual choice first, then detection on the text, and only "auto"
    when that is too uncertain. The test panel walked straight past it
    and handed Whisper ``config.whisper.language``, which is "auto" by
    default. So every variant detected its own language, and the user
    watched Spanish go by in a Dutch song.

    That is not cosmetic. It pollutes the comparison the trial exists
    for: a variant can then differ from its neighbour not because of the
    setting under test but because that run decided the song was
    Spanish.

    B404 makes it worse in the chunked run: ten pieces are ten
    INDEPENDENT detections, and a short piece - a "la la la", a
    fade-out - is the most fragile of all. So the language is pinned
    here, once, and handed to every variant and every piece.

    Order: what the app itself would choose, and failing that what
    Whisper decided on the whole original last time (that answer is
    already in ``run_info.json``). Only if both are silent does "auto"
    remain - and then the trial says so, because a measurement whose
    language wanders is worth knowing about.
    """
    import json as _json

    other = pipeline.context_for_project(context, song)
    code = pipeline._language_for(other, pipeline.TRACK_ORIGINAL)
    if code and code != "auto":
        return code
    info = (other.paths.output_dir / pipeline.TRACK_ORIGINAL
            / "run_info.json")
    if info.exists():
        try:
            stored = _json.loads(info.read_text(encoding="utf-8"))
            found = str(stored.get("language") or "").strip()
            if found:
                return found
        except (OSError, ValueError, KeyError):
            pass
    return "auto"


#: From this many uninterrupted seconds of "singing but no text" onward
#: it counts as a gap (B374). Shorter is simply breath between two lines.
_GAP_MIN_S = 5.0


def _gaps_in(context, song: str):
    """The unheard stretches of one project.

    B526: this was the heart of action 1.5.8, and that action has gone.
    Its answer was always the same one - a project has a hole or it does
    not - and knowing THAT never changed anything; only 1.5.11 can say
    what to do about it. The measurement itself is still needed there,
    so it stays as a helper.
    """
    other = pipeline.context_for_project(context, song)
    try:
        segments = pipeline.load_segments(other, pipeline.TRACK_ORIGINAL)
    except Exception:  # noqa: BLE001 - no transcription, no opinion
        return []
    windows = pipeline._original_vocal_windows(other)    # B467
    if not windows:
        return []
    covered = sorted((w.start, w.end) for s in segments for w in s.words)
    gaps = []
    for low, high in windows:
        cursor = low
        for start, end in covered:
            if end <= low or start >= high:
                continue
            if start - cursor >= _GAP_MIN_S:
                gaps.append((cursor, start))
            cursor = max(cursor, end)
        if high - cursor >= _GAP_MIN_S:
            gaps.append((cursor, high))
    return gaps


def _projects_by_gap(context, cancelled) -> list:
    """Every project with a hole, worst first (B416).

    1.5.11d measured one song, and deliberately so: the song with the
    biggest hole is where there is most to win. But that also makes it
    the least representative song there is, and a conclusion about
    cutting on one song is not a conclusion. Cutting makes a new edge at
    every cut, so on a song WITHOUT holes it can just as easily do
    damage - and that is exactly what a night job is for.
    """
    ranked = []
    for song in _projects(context):
        if cancelled():
            break
        gaps = _gaps_in(context, song)
        if gaps:
            ranked.append((song, max(gaps, key=lambda g: g[1] - g[0])))
    ranked.sort(key=lambda item: item[1][1] - item[1][0], reverse=True)
    return ranked


def chunk_trial(context, report, cancelled) -> list[str]:
    """1.5.11d - does looking again fill the holes? (B390)

    Four ways of showing Whisper the same vocal stem, on the project
    with the most unheard singing: as it is now, with the start shifted
    (twice), and cut into pieces on the silences with a prompt per piece.
    What counts is one number - seconds of MEASURED singing carrying no
    word at all - because that is the damage ``_gaps_in`` reports and
    the whole reason for this experiment.

    Deliberately reports every variant separately AND the merge. The
    merge may only fill holes, never overrule (see
    ``whisper_chunks.merge_runs``): two runs share their initial prompt,
    so agreement between them is not evidence.
    """
    ranked = _projects_by_gap(context, cancelled)[:CHUNK_SONGS]
    if not ranked:
        raise TrialSkipped([t("heavy_probe_nowhere")])
    lines: list[str] = []
    words_per_song: dict[str, tuple] = {}
    for song, _widest in ranked:
        if cancelled():
            break
        lines += _chunk_one_song(context, song, report, cancelled,
                                 words_per_song)
    _write_chunk_words(words_per_song)
    lines += ["", t("heavy_chunk_words").format(path=CHUNK_WORDS.name)]
    return lines


def _chunk_one_song(context, song, report, cancelled,
                    words_per_song) -> list[str]:
    """1.5.11d for one project (B416)."""
    import importlib.util
    import threading
    import time as _time

    from . import whisper_chunks as wc

    other = pipeline.context_for_project(context, song)
    # B467: same clock as 1.5.11e. Both transcribe the vocal stem of the
    # original, so both weigh against the windows of that same file -
    # otherwise their columns cannot be laid side by side, which is
    # exactly what went wrong (Viva gave 49.2 s in one and 68.8 s in the
    # other for the same run).
    windows = pipeline._original_vocal_windows(other)
    if not windows:
        return [f"### {song}", "", t("heavy_probe_nowhere")]
    total = max(high for _low, high in windows)

    path = (Path(__file__).resolve().parents[1] / "tools"
            / "whisper_probe.py")
    spec = importlib.util.spec_from_file_location("probe", path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    try:
        stem = probe.vocal_stem(context.paths.root, song)
    except BaseException as exc:  # noqa: BLE001 - a tool, not the app
        return [f"### {song}", "", f"{song}: {exc}"]
    prompt = probe.prompt_for_project(context.paths.root, song)
    base = context.config.whisper

    # The lines as the first run placed them: the material for a prompt
    # per piece. Wrong at the end - which is why the slice is generous.
    placed = [(float(ln["start"]), str(ln.get("text", "")))
              for ln in (_placed_lines(other) or ())]
    pieces = wc.cut_points(windows, total)
    lyric_keys = _lyric_keys(other)
    # B403/B404: pin the language BEFORE cutting. Ten pieces would
    # otherwise be ten independent detections, and a short piece is the
    # most fragile of all.
    language = probe_language(context, song)

    tail = _sung_after_the_text(other, windows)
    lines = [f"### {song}", "", t("heavy_chunk_intro").format(
        name=song, seconds=round(sum(h - l for l, h in windows), 1),
        pieces=len(pieces)), ""]
    if tail > 1.0:
        # B416: singing after the last line of the text is not damage but
        # missing text - the user left the last chorus out of this song
        # on purpose. Counting that as "not heard" would blame Whisper
        # for a hole that the lyrics themselves have.
        lines += [t("heavy_chunk_tail").format(seconds=round(tail, 1)), ""]
    lines += [
        "| variant | segmenten | woorden | in tekst | niet gehoord |"
        " gevuld | rekentijd |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]

    def words_of(segments):
        return [w for s in segments for w in s.get("words", ())]

    runs: dict[str, list] = {}
    timings: dict[str, float] = {}
    bookkeeping = threading.Lock()
    # B424/B425: two variants that each answer one question the earlier
    # rounds left open. "globale prompt" cuts exactly as the normal
    # chunked run but hands every piece the SAME deduplicated word list,
    # so the difference with "knippen" is the prompt per piece and
    # nothing else - and that decides whether the cutting has to wait for
    # a first transcription at all. "knippen + vad" is the combination
    # nobody has measured: 1.5.11c measured VAD on the whole song,
    # 1.5.11d cutting without VAD, and the two are not alternatives -
    # VAD removes silence, cutting cuts IN silence.
    plan = ["huidig", "offset 10 s", "offset 20 s", "knippen",
            "knippen (globale prompt)", "knippen + vad"]
    from dataclasses import replace as _replace
    met_vad = _replace(base, **probe.VARIANTS["vad"])

    def one_run(name: str) -> list[str]:
        """One way of listening, as its own work slot (B410).

        These used to run strictly one after another in a plain for loop
        - 873 s of the 3551 s that 1.5.11 took, on one core, while
        Whisper releases the GIL and two runs genuinely fit side by side.
        """
        started = _time.monotonic()
        try:
            if name.startswith("knippen"):
                settings = met_vad if name.endswith("vad") else base
                per_piece = (
                    (lambda piece: prompt)
                    if "globale" in name
                    else (lambda piece: wc.chunk_prompt(placed, piece)
                          or prompt))
                found = probe.run_chunked(stem, settings, language, pieces,
                                          per_piece)
            else:
                offset = {"huidig": 0.0, "offset 10 s": 10.0,
                          "offset 20 s": 20.0}[name]
                found = probe.run_once(stem, base, prompt, language,
                                       start=offset)
        except BaseException as exc:  # noqa: BLE001 - a variant may fail
            logger.exception(t("log_test_project_failed"), name)
            return [f"| {name} | - | - | - | - | - | {exc} |"]
        spent = _time.monotonic() - started
        with bookkeeping:
            runs[name] = found
            timings[name] = spent
        words = words_of(found)
        label = (f"{name} ({len(pieces)} stukken)"
                 if name.startswith("knippen") else name)
        return [f"| {label} | {len(found)} | {len(words)} |"
                f" {in_the_text(words, lyric_keys):.0f}% |"
                f" {wc.unheard_seconds(words, windows):.1f} s | - |"
                f" {spent:.0f} s |"]

    lines += across_projects(
        context, plan, one_run,
        lambda slot, name, done=0, total=0: report(slot, name, done, total),
        cancelled, slots=measure_pool.whisper_workers(len(plan)))

    # B410: merge onto the BEST run, not onto "huidig".
    #
    # The merge may only fill holes, and that rule is right. Which run it
    # fills holes IN was not: it was always the current one, the run with
    # the most unheard singing there is. On the measured song that cost
    # seven seconds of coverage - cutting on its own reached 29.3 s
    # unheard and the merge onto "huidig" came out at 36.5 s, worse than
    # its own best ingredient. Starting from the best run and filling the
    # rest into it can only be better: every hole that another run can
    # fill is still filled, and the ones the best run already had right
    # are no longer thrown away.
    if runs:
        def unheard(name: str) -> float:
            return wc.unheard_seconds(words_of(runs[name]), windows)

        def purity(name: str) -> float:
            return in_the_text(words_of(runs[name]), lyric_keys)

        # B420: the fullest run is only the best run if what it heard is
        # also in the lyrics. Choosing on seconds alone would hand a
        # looping run the base position, and then its invented words are
        # exactly the ones that are kept.
        clean = [name for name in runs
                 if purity(name) >= purity("huidig") - _PURITY_SLACK] \
            or list(runs)
        best = min(clean, key=unheard)
        merged = words_of(runs[best])
        filled_total = 0
        for name in sorted(runs):
            if name == best:
                continue
            merged, filled = wc.merge_runs(merged, words_of(runs[name]),
                                           windows, lyric_keys)
            filled_total += filled
        lines.append(
            f"| **samengevoegd (basis: {best})** | - | {len(merged)} |"
            f" {in_the_text(merged, lyric_keys):.0f}% |"
            f" {wc.unheard_seconds(merged, windows):.1f} s |"
            f" {filled_total} | - |")
        # The words themselves, so that "are those 248 words real?" can
        # be answered against lyrics.txt instead of believed (B410).
        words_per_song[song] = (dict(runs), list(merged))
    lines += ["", t("heavy_language_used").format(
        code=language if language != "auto" else t("heavy_language_auto"))]
    lines += ["", t("heavy_chunk_advice")]
    return lines


def _sung_after_the_text(context, windows) -> float:
    """Seconds of singing after the LAST line of the text (B416).

    Not damage but missing text. On "Lied M" the user left the
    final chorus out of the lyrics on purpose - the song is played by
    feel and the words are hard to make out - and then there really is
    singing that no word can cover. Counting that as "not heard" blames
    Whisper for a hole in the lyrics, and that is how a measurement
    starts lying.
    """
    placed = _placed_lines(context) or ()
    if not placed or not windows:
        return 0.0
    last = max(float(line["start"]) for line in placed)
    return sum(max(0.0, high - max(low, last))
               for low, high in windows if high > last)


def _write_chunk_words(per_song) -> None:
    """Write down what every way of listening heard (B410).

    1.5.11d reported that cutting yields 248 words against 197 - and
    that number is worthless as long as nobody can see WHICH words those
    are. The previous round it turned out that half of them were Spanish
    hallucinations, and only because the user happened to see the
    language flash past. So: on paper, one word per line with its time,
    and the lyrics beside it is then a matter of reading.
    """
    out: list[str] = []
    for song in sorted(per_song):
        runs, merged = per_song[song]
        out += [f"# {song}", ""]
        for name in sorted(runs):
            words = [w for seg in runs[name] for w in seg.get("words", ())]
            out += [f"## {name} ({len(words)} woorden)", ""]
            out += [f"{float(w['start']):8.2f}  {str(w['text']).strip()}"
                    for w in words]
            out.append("")
        out += [f"## samengevoegd ({len(merged)} woorden)", ""]
        out += [f"{float(w['start']):8.2f}  {str(w['text']).strip()}"
                for w in merged]
        out.append("")
    try:
        CHUNK_WORDS.parent.mkdir(parents=True, exist_ok=True)
        CHUNK_WORDS.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError:
        logger.warning(t("log_chunk_words_failed"))


def _placed_lines(context):
    """The lines with their times from the last run, or nothing."""
    try:
        coupling = pipeline.build_coupling(context)
    except Exception:  # noqa: BLE001 - material, not production
        return ()
    if not coupling:
        return ()
    out = []
    for line in coupling["timed"]:
        syllables = getattr(line, "syllables", ())
        if syllables:
            out.append({"start": float(syllables[0].start),
                        "text": getattr(line, "text", "")})
    return out


def in_the_text(words, keys) -> float:
    """Share of heard words that occur in the lyrics (B420).

    The counter-check that "not heard" cannot do on its own. That
    number only measures whether a hole has been FILLED, and a Whisper
    loop fills a hole beautifully - so the metric rewards exactly the
    failure it is supposed to catch. It happened twice: a run in Spanish
    that scored best, and a chunked run that found 456 words of which
    over half were invented. Both times it was the user or a hand count
    that noticed, not the trial.

    Compared on the phonetic key, so a spelling variant of the same
    sound still counts - the same notion of "the same word" that the
    coupling uses. Words the lyrics simply do not have (a chorus left
    out of the text) push this down honestly; that is why it stands
    beside the seconds and not instead of them.
    """
    from . import cluster as cluster_module

    if not words or not keys:
        return 0.0
    hits = sum(1 for word in words
               if cluster_module.phonetic_key(str(word["text"])) in keys)
    return 100.0 * hits / len(words)


def _lyric_keys(context):
    """The phonetic keys of the lyrics (B427), from the pipeline.

    B442: the program cuts its own songs now, so this had to leave the
    test panel and go where production can reach it. Kept as a name here
    because the trials read like prose with it.
    """
    return pipeline.lyric_keys(context)


#: The levels 1.5.11e listens at (B457). "zoals nu" is the untouched
#: stem; the others are normalised on it with the same EBU R128 measure
#: the video uses, so a win here is a setting and not a coincidence.
GAIN_LEVELS: tuple[tuple[str, float | None], ...] = (
    ("zoals nu", None),
    ("-16 LUFS", -16.0),
    ("-11 LUFS", -11.0),
)


def gain_trial(context, report, cancelled) -> list[str]:
    """1.5.11e - does a louder vocal stem help Whisper (B457/B460)?

    The question comes from the user and it is a fair one: he normalises
    his other music to one level, and a quiet stem might simply be
    harder to hear. Measured over eighteen projects the stems run from
    -10.5 to -26.9 LUFS - sixteen decibels - so if level matters at all
    it should be visible here.

    What the numbers so far say: the correlation between the loudness of
    a stem and the error of that project is -0.3, which points the right
    way but is far too weak to build on, and the quietest song of them
    all (Groen, -26.9) got the BEST result in 1.5.11d. So this is a
    genuinely open question, which is exactly why it is worth measuring
    instead of assuming.

    B460: every run goes into ONE queue over the Whisper lanes, longest
    song first. The first version walked song by song and level by level
    on a single lane - the user saw one Whisper process where the rule
    has said two since B396, and he was right: that is half the machine
    standing still for an hour.

    Deliberately built to be able to answer and then go. It reports one
    thing - words heard, share in the text, unheard singing per level -
    and once that says yes or no this trial goes off like 1.5.11c and d.
    """
    # B482: the converted levels used to go into a fresh mkdtemp per
    # file and were never removed, so every run left a trail of
    # ``karaoke_gain_*`` folders behind in %TEMP%. One folder for the
    # whole trial, cleared up whatever happens - also when the user
    # presses Stop halfway.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="karaoke_gain_") as scratch:
        return _gain_trial(context, report, cancelled, Path(scratch))


def _gain_trial(context, report, cancelled, scratch: Path) -> list[str]:
    """The work of 1.5.11e; ``scratch`` is cleaned up by the caller
    (B482)."""
    import importlib.util
    import threading
    import time as _time

    ranked = _projects_by_gap(context, cancelled)
    songs = [song for song, _gap in ranked[:CHUNK_SONGS]]
    if not songs:
        raise TrialSkipped([t("heavy_probe_nowhere")])

    path = (Path(__file__).resolve().parents[1] / "tools"
            / "whisper_probe.py")
    spec = importlib.util.spec_from_file_location("probe", path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    # First everything that is NOT Whisper: the stems, the prompts and
    # the converted levels. That is ffmpeg and file work, it is quick,
    # and doing it up front keeps the lanes below busy with nothing but
    # transcribing.
    prepared: list[dict] = []
    lines = [t("heavy_gain_intro").format(count=len(songs)), ""]
    for song in songs:
        if cancelled():
            break
        other = pipeline.context_for_project(context, song)
        windows = pipeline._original_vocal_windows(other)
        if not windows:
            continue
        try:
            stem = probe.vocal_stem(context.paths.root, song)
        except BaseException as exc:  # noqa: BLE001 - a tool, not the app
            lines += [f"### {song}", "", f"{song}: {exc}", ""]
            continue
        level = pipeline.ffmpeg.measure_loudness(stem)
        for name, target in GAIN_LEVELS:
            if cancelled():
                break
            prepared.append({
                "song": song, "level": name, "windows": windows,
                "prompt": probe.prompt_for_project(context.paths.root, song),
                "language": probe_language(context, song),
                "keys": _lyric_keys(other), "measured": level,
                "audio": _at_level(stem, target, scratch, song),
                "seconds": max(high for _low, high in windows)})

    # Longest song first: the user's rule for a queue, and here it is
    # simply the largest piece of work.
    queue = sorted(prepared, key=lambda job: -job["seconds"])
    steps = Steps(report, "1.5.11e", len(queue))
    lock = threading.Lock()
    done: dict[tuple, dict] = {}

    def take():
        with lock:
            return queue.pop(0) if queue else None

    def worker() -> None:
        while True:
            job = take()
            if job is None or cancelled():
                return
            started = _time.monotonic()
            words: list = []
            if job["audio"] is not None:
                try:
                    found = probe.run_once(job["audio"],
                                           context.config.whisper,
                                           job["prompt"], job["language"])
                    words = [w for seg in found
                             for w in seg.get("words", ())]
                except Exception:  # noqa: BLE001 - one level is not the run
                    logger.exception(t("log_measure_failed"))
            with lock:
                done[(job["song"], job["level"])] = {
                    "words": words, "job": job,
                    "seconds": _time.monotonic() - started}
            steps.tick()
            steps.name(f"1.5.11e  {job['song']}  {job['level']}")

    lanes = max(1, measure_pool.whisper_lanes())
    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(min(lanes, max(1, len(queue))))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    from . import whisper_chunks as wc

    for song in songs:
        rows = [(name, done.get((song, name))) for name, _t in GAIN_LEVELS]
        if not any(row for _n, row in rows):
            continue
        lines += [f"### {song}", ""]
        measured = next((row["job"]["measured"] for _n, row in rows
                         if row and row["job"]["measured"]), None)
        if measured is not None:
            lines += [t("heavy_gain_level").format(
                lufs=measured.integrated, peak=measured.true_peak), ""]
        lines += ["| niveau | woorden | in tekst | niet gehoord |"
                  " rekentijd |",
                  "| --- | ---: | ---: | ---: | ---: |"]
        for name, row in rows:
            if row is None or not row["words"]:
                lines.append(f"| {name} | - | - | - | - |")
                continue
            words = row["words"]
            lines.append(
                f"| {name} | {len(words)} | "
                f"{in_the_text(words, row['job']['keys']):.0f}% | "
                f"{wc.unheard_seconds(words, row['job']['windows']):.1f} s | "
                f"{row['seconds']:.0f} s |")
        lines.append("")
    lines.append(t("heavy_gain_note"))
    return lines


def _at_level(stem, target, folder: Path, song: str):
    """The stem at this loudness, as a temporary file (B457).

    ``None`` for "as it is" - then the original file is used, so the
    reference run costs no conversion and cannot differ by one.

    B482: ``folder`` is the scratch folder of the whole trial, which is
    cleaned up afterwards; this used to make one of its own per file and
    leave it behind.
    """
    if target is None:
        return stem
    from . import ffmpeg as ffmpeg_module

    measured = ffmpeg_module.measure_loudness(stem, target)
    if measured is None:
        return None
    # The stem is called ``vocals.wav`` in EVERY project, so the name has
    # to carry the project or all the songs write over each other in the
    # shared scratch folder - and then every measurement reads the last
    # one (B482).
    out = (folder
           / f"{song}_{stem.stem}_{str(target).replace('.', '_')}.wav")
    try:
        ffmpeg_module._run([
            ffmpeg_module._tool("ffmpeg"), "-nostdin", "-hide_banner", "-y",
            "-i", str(stem), "-af",
            ffmpeg_module.loudnorm_filter(measured, target),
            "-ar", "16000", "-ac", "1", str(out)])
    except ffmpeg_module.FfmpegError:
        logger.exception(t("log_loudness_failed"))
        return None
    return out


# --------------------------------------------------------------------------
# B516 - two transcriptions of the same audio side by side
# --------------------------------------------------------------------------

#: A difference between two runs shorter than this is not a finding but
#: a word boundary that fell a fraction differently (B516).
_ONLY_MIN_S = 0.5


def covered_seconds(words, windows) -> float:
    """The measured singing that these words really cover (B516)."""
    from . import whisper_chunks as wc

    sung = sum(high - low for low, high in windows)
    return round(sung - wc.unheard_seconds(words, windows), 2)


def only_in(words, other, windows, minimum: float = _ONLY_MIN_S) -> list:
    """Sung stretches that ``words`` cover and ``other`` does not (B516).

    This is the number ``_gaps_in`` cannot give. That one counts holes
    of five seconds and longer, and the difference between two runs is
    almost never one big hole - measured on "Lied R" against "Lied_R2"
    it gave exactly 5.3 s three times in a row, while one run covered 21.5
    seconds the other did not have at all. Whoever compares two ways of
    listening has to be able to see where they differ, not only how much
    is missing from both.
    """
    def spans(items):
        """The words as time slots, with touching ones joined.

        Joining matters: Whisper words are a third of a second, so a
        whole line that the other run misses arrives here as eight
        little pieces of 0.4 s. Judged one by one they all fall under
        ``minimum`` and the difference is reported as zero - the very
        blindness this measuring stick was made to end.
        """
        joined: list[list[float]] = []
        for start, end in sorted((float(w["start"]), float(w["end"]))
                                 for w in items):
            if joined and start <= joined[-1][1] + 0.05:
                joined[-1][1] = max(joined[-1][1], end)
            else:
                joined.append([start, end])
        return [(low, high) for low, high in joined]

    mine, theirs = spans(words), spans(other)
    out = []
    for low, high in windows:
        cursor = float(low)
        for start, end in mine:
            if end <= cursor or start >= high:
                continue
            begin, stop = max(start, cursor), min(end, high)
            cursor = max(cursor, end)
            # What of this piece does the other one NOT have?
            edge = begin
            for a, b in theirs:
                if b <= edge or a >= stop:
                    continue
                if a > edge:
                    out.append((edge, min(a, stop)))
                edge = max(edge, b)
                if edge >= stop:
                    break
            if edge < stop:
                out.append((edge, stop))
    return [(round(a, 2), round(b, 2)) for a, b in out if b - a >= minimum]


def words_between(words, low: float, high: float) -> str:
    """The text of the words in this stretch (B516)."""
    return " ".join(str(w.get("text", "")).strip() for w in words
                    if float(w["end"]) > low and float(w["start"]) < high)


def on_the_lines(words, spans) -> float:
    """Share of heard words that land on a hand-timed sentence (B516).

    The user's idea, and it plugs a real hole. "In text" compares a word
    with the lyrics phonetically, and for a passage in another script
    that comparison cannot work: at "Lied R" the Korean is written in
    Latin letters ("Twee-uh"), so a correct Korean word (뛰어) scores
    zero however right it is. Where a project has hand-made timing, the
    truth about WHERE singing happens is already in the house, and that
    reference knows nothing of spelling or language.
    """
    if not spans or not words:
        return 0.0
    ordered = sorted((float(a), float(b)) for a, b in spans)
    hit = 0
    for word in words:
        middle = (float(word["start"]) + float(word["end"])) / 2.0
        if any(low <= middle <= high for low, high in ordered):
            hit += 1
    return 100.0 * hit / len(words)


def line_start_distance(words, spans) -> float:
    """Median distance from a hand-set line start to the nearest word
    start (B527).

    :func:`on_the_lines` says whether a run puts its words where singing
    happens; this says whether it puts a word ON THE FIRST BEAT of a
    sentence. That is what the timing needs from a transcription: every
    line start it anchors on comes from a word start, so the distance
    from the user's own line starts to the nearest word start IS the
    distance between this run and his hand work.

    The median and not the mean: one line that a run misses entirely
    lies twenty seconds away, and that one line should not be able to
    decide the whole table.
    """
    import bisect
    import math

    starts = sorted(float(w["start"]) for w in words)
    if not spans or not starts:
        # Deliberately not 0.0: that is the score of a run that hits
        # every line start exactly, and a run that produced nothing at
        # all would then win the table.
        return math.inf
    distances = []
    for low, _high in sorted((float(a), float(b)) for a, b in spans):
        position = bisect.bisect_left(starts, low)
        near = [starts[i] for i in (position - 1, position)
                if 0 <= i < len(starts)]
        if near:
            distances.append(min(abs(low - moment) for moment in near))
    import math
    return (round(statistics.median(distances), 3) if distances
            else math.inf)


def rank_variants(rows, windows, reference) -> list[tuple]:
    """The variants best first (B527).

    Yields ``(label, words, share on a real line, distance to a line
    start, covered seconds)``. With a hand-timed reference the order is
    the distance to that hand work - lowest first, because that is the
    whole question - and without one the covered singing, which is the
    best that can be said without a truth.
    """
    measured = []
    for label, words in rows:
        measured.append((label, words,
                         on_the_lines(words, reference) if reference else 0.0,
                         line_start_distance(words, reference)
                         if reference else 0.0,
                         covered_seconds(words, windows)))
    if reference:
        measured.sort(key=lambda row: (row[3], -row[2]))
    else:
        measured.sort(key=lambda row: -row[4])
    return measured


def search_table(rows, windows, lyric_keys, reference) -> list[str]:
    """Every variant and every combination in one sorted table (B527).

    ``rows`` are ``(label, words)``. With a hand-timed reference the
    table is sorted on the distance to that hand work - lowest first,
    because that is the whole question - and without one on the covered
    singing, which is the best that can be said without a truth.
    """
    from . import whisper_chunks as wc

    sung = round(sum(high - low for low, high in windows), 1)
    lines = [t("search_intro").format(seconds=sung, count=len(rows)), ""]
    head = (f"| {t('search_col_run')} | {t('search_col_words')}"
            f" | {t('search_col_in_text')} | {t('search_col_covered')}"
            f" | {t('search_col_unheard')} |")
    rule = "| --- | ---: | ---: | ---: | ---: |"
    if reference:
        head += (f" {t('search_col_on_line')} |"
                 f" {t('search_col_distance')} |")
        rule += " ---: | ---: |"
    lines += [head, rule]
    measured = rank_variants(rows, windows, reference)
    for label, words, share, distance, covered in measured:
        row = (f"| {label} | {len(words)} |"
               f" {in_the_text(words, lyric_keys):.0f}%"
               f" | {covered:.1f} s |"
               f" {wc.unheard_seconds(words, windows):.1f} s |")
        if reference:
            shown = "-" if distance == float("inf") else f"{distance:.2f} s"
            row += f" {share:.0f}% | {shown} |"
        lines.append(row)
    scored = [row for row in measured if row[3] != float("inf")]
    if scored and reference:
        best = scored[0]
        lines += ["", t("search_best").format(
            name=best[0], distance=best[3], share=best[2])]
    return lines


def reference_timing(context, song: str):
    """Hand-made timing of a project with the SAME audio (B516).

    Two projects can share one recording - "Lied R" and "Lied_R2" are
    the same m4a with a different lyrics file - and then the hand work
    of the one is a reference for the other. Returns
    ``(project, spans)`` or ``None``; only real hand work counts, so a
    timing that is still equal to the automatic one is skipped.
    """
    from . import timing as timing_module

    mine = pipeline.context_for_project(context, song)
    step = mine.store.get_step("source_original") or {}
    fingerprint = step.get("sha1")
    if not fingerprint:
        return None
    for other_song in _projects(context):
        if other_song == song:
            continue
        other = pipeline.context_for_project(context, other_song)
        source = other.store.get_step("source_original") or {}
        if source.get("sha1") != fingerprint:
            continue
        paths = _paths_for(context, other_song)
        if not (paths.timing_file.exists() and paths.timing_auto_file.exists()):
            continue
        try:
            hand = timing_module.load_timing(paths.timing_file)
            auto = timing_module.load_timing(paths.timing_auto_file)
        except (OSError, ValueError, KeyError):
            continue
        if len(hand) == len(auto) and all(
                abs(a.start - b.start) < 0.002 and abs(a.end - b.end) < 0.002
                for a, b in zip(hand, auto)):
            continue                       # never touched by hand
        # The timing lies on the KARAOKE timeline and the words of a
        # Whisper run on that of the original vocal stem. Where the
        # karaoke was made from the original those two coincide, but
        # that is not a rule to lean on - so the spans are projected
        # back, with the alignment of the project the timing comes from.
        from . import align

        step = other.store.get_step("align") or {}
        regions = align.regions_from_dicts(step.get("regions") or [])
        spans = [(align.project_time_reverse(line.start, regions),
                  align.project_time_reverse(line.end, regions))
                 for line in hand
                 if not line.disabled and line.end > line.start]
        spans = [(low, high) for low, high in spans if high > low]
        if spans:
            return other_song, spans
    return None


def differences(label_a: str, words_a, label_b: str, words_b,
                windows, limit: int = 8) -> list[str]:
    """Where two runs on the same audio really differ (B516).

    The table of :func:`search_table` gives numbers; this gives the
    seconds behind them. Used on the winner against the run production
    makes today, because "0.3 s closer" is a claim and "these four
    lines" is the evidence for it.
    """
    lines: list[str] = []
    for label, mine, theirs, other_label in (
            (label_a, words_a, words_b, label_b),
            (label_b, words_b, words_a, label_a)):
        stretches = only_in(mine, theirs, windows)
        total = round(sum(b - a for a, b in stretches), 1)
        lines += ["", t("ab_only").format(name=label, other=other_label,
                                          seconds=total,
                                          count=len(stretches)), ""]
        if stretches:
            # Its own header row: without one these lines are not a
            # table but a paragraph full of raw pipes on the screen.
            lines += [f"| {t('search_col_spot')} | {label} |",
                      "| --- | --- |"]
        for low, high in sorted(stretches,
                                key=lambda s: s[0] - s[1])[:limit]:
            lines.append(f"| {low:.1f}-{high:.1f} ({high - low:.1f} s) |"
                         f" {words_between(mine, low, high)[:60]} |")
        if len(stretches) > limit:
            lines.append(t("ab_more").format(count=len(stretches) - limit))
    return lines


# --------------------------------------------------------------------------
# B515/B538 - 1.5.11g: how to read a song with two languages in it
# --------------------------------------------------------------------------
#
# What is NOT here any more, and the answer that took its place (B538).
# 1.5.11g was built around an idea of mine: run the second language over
# exactly the WEAK SPOTS of the first - the stretches where the first run
# says too little. It ran on 31 August on "Lied_R2", the only project
# with a second script, and the idea does not work. The second language
# on the weak spots gave six words and scored 0% on a single real
# sentence: a spot of a few seconds is too little run-up for Whisper,
# even padded by three seconds on either side.
#
# What DOES work is the most careful merge of all: the whole song in the
# first language, with the second language allowed only to fill silence.
# 0.08 s from the hand-set line starts against 0.09 s for the bare first
# language, and 2.0 s of singing recovered in three pieces - exactly the
# three Korean shouts. Nothing lost: zero seconds that the first
# language had and the merge did not.
#
# So that route went to production (B538, in ``_transcribe_in_pieces``)
# and the weak-spot machinery went out: ``weak_by_ratio``,
# ``useful_spans``, ``_pad_and_cap``, ``combine_in_spots`` and their
# constants. Like 1.5.8 and 1.5.11c: the answer stays, the road to it
# does not. What the trial still does is check, on a new song, whether
# that merge is still the best of the ways of reading - because it is
# one song, and one song is not a rule.


def without_runaways(words) -> tuple[list, int]:
    """The words minus the runaway loops (B514/B515).

    ``probe.run_once`` hands back raw Whisper output; production runs it
    through the hallucination filter first. Without that step a runaway
    loop counts here as twenty-seven seconds of COVERED singing, and
    then the very spot that needs a second attempt is the one this trial
    would call healthy.
    """
    import statistics as _stat

    spans = [float(w["end"]) - float(w["start"]) for w in words
             if float(w["end"]) > float(w["start"])]
    middle = _stat.median(spans) if len(spans) >= 8 else 0.0
    limit = (max(pipeline._RUNAWAY_MIN_S, pipeline._RUNAWAY_FACTOR * middle)
             if middle > 0 else pipeline._RUNAWAY_MIN_S)

    def loop(word: dict) -> bool:
        return (float(word["end"]) - float(word["start"]) >= limit
                or len(str(word.get("text", "")).strip())
                >= pipeline._RUNAWAY_LETTERS)

    kept = [w for w in words if not loop(w)]
    return kept, len(words) - len(kept)


def two_language_trial(context, report, cancelled) -> list[str]:
    """1.5.11g - which way of listening comes closest to the hand work?

    B527: this was one comparison and one comparison cannot find a
    common denominator, so it became a search. B538 shortened that
    search again, because it has an answer now (see the note above this
    section): what is left are the three ways of reading and the one
    merge that won.

    * the whole song in the biggest language;
    * the whole song in the second language (B495 measured this loses on
      its own - it belongs in the table to show by how much);
    * the biggest language cut on the silences (B390);
    * and the merge production makes since B538: the first run stays the
      truth and the second language may only fill silence.

    All of them laid against the user's own timing of the same
    recording, sorted on the number that matters: how far his line
    starts are from the nearest word start. Nothing is decided here -
    the trial exists to say, on a NEW song, whether that merge is still
    the best of them. One song is not a rule.
    """
    import importlib.util
    import time as _time

    from . import whisper_chunks as wc

    songs = []
    for song in _projects(context):
        other = pipeline.context_for_project(context, song)
        second = pipeline.second_language_of(other)
        if second is not None:
            songs.append((song, second))
    if not songs:
        raise TrialSkipped([t("heavy_two_languages_nowhere")])
    # Same brake as 1.5.11d/e: this is Whisper time on the user's own
    # machine, and a trial that quietly walks every project is how a
    # night job becomes a night.
    songs = songs[:CHUNK_SONGS]

    path = (Path(__file__).resolve().parents[1] / "tools"
            / "whisper_probe.py")
    spec = importlib.util.spec_from_file_location("probe", path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    lines = [t("heavy_two_languages_intro").format(count=len(songs))]
    steps = Steps(report, "1.5.11g", len(songs))
    for song, (code, number) in songs:
        if cancelled():
            break
        steps.tick()
        steps.name(f"1.5.11g  {song}")
        other = pipeline.context_for_project(context, song)
        windows = pipeline._original_vocal_windows(other)
        if not windows:
            lines += ["", f"### {song}", "", t("heavy_probe_nowhere")]
            continue
        try:
            stem = probe.vocal_stem(context.paths.root, song)
        except BaseException as exc:  # noqa: BLE001 - a tool, not the app
            lines += ["", f"### {song}", "", str(exc)]
            continue
        prompt = probe.prompt_for_project(context.paths.root, song)
        base = context.config.whisper
        first = probe_language(context, song)
        lyric_keys = _lyric_keys(other)
        lines += ["", f"### {song}", "",
                  t("heavy_two_languages_pair").format(
                      first=first if first != "auto" else t(
                          "heavy_language_auto"),
                      second=code, count=number)]
        started = _time.monotonic()

        def read(label: str, run) -> list | None:
            """One transcription, minus its runaway loops."""
            try:
                words, loops = without_runaways(wc.words_of(run()))
            except BaseException as exc:  # noqa: BLE001 - one run, not the rest
                logger.exception(t("log_test_project_failed"), song)
                lines.append("")
                lines.append(str(exc))
                return None
            if loops:
                lines.append("")
                lines.append(t("heavy_two_languages_runaway").format(
                    count=loops, name=label))
            return words

        whole_first = read(first, lambda: probe.run_once(stem, base, prompt,
                                                         first))
        if whole_first is None:
            continue
        whole_second = read(code, lambda: probe.run_once(stem, base, prompt,
                                                         code))
        pieces = wc.cut_points(windows, max(high for _low, high in windows))
        chunked_first = read(f"{first} {t('search_chunked')}",
                             lambda: probe.run_chunked(
                                 stem, base, first, pieces,
                                 lambda _piece: prompt))

        rows = [(first, whole_first)]
        if whole_second is not None:
            rows.append((f"{code} {t('search_whole')}", whole_second))
        if chunked_first is not None:
            rows.append((f"{first} {t('search_chunked')}", chunked_first))
        if whole_second is not None:
            # B538: the merge production really makes since v0.151.0 -
            # the first run stays the truth, and the pieces AND the
            # second language may fill its silences. The pieces belong
            # in it: leaving them out would put a different merge in the
            # table than the one the program makes. ``merge_runs`` hands
            # back (words, filled); the count is not a word list.
            extra = list(whole_second)
            if chunked_first is not None:
                extra += list(chunked_first)
            rows.append((t("search_fill_silence"),
                         list(wc.merge_runs(whole_first, extra,
                                            windows, lyric_keys)[0])))
        reference = reference_timing(context, song)
        if reference is None:
            lines += ["", t("search_no_reference")]
        else:
            lines += ["", t("heavy_two_languages_reference").format(
                name=reference[0], count=len(reference[1]))]
        lines += [""] + search_table(rows, windows, lyric_keys,
                                     reference[1] if reference else None)
        lines += ["", t("search_took").format(
            seconds=round(_time.monotonic() - started, 0))]
        # And where the winner really differs from what production does
        # today - the table gives numbers, this gives the seconds.
        ranked = [row for row in rank_variants(
            rows, windows, reference[1] if reference else None)
            if row[3] != float("inf")]
        if ranked and ranked[0][1] is not whole_first:
            lines += differences(ranked[0][0], ranked[0][1],
                                 first, whole_first, windows)
        # And what the second language says where the first one heard
        # nothing - the table gives numbers, this gives the words behind
        # them. Exactly the seconds the merge fills, so the user can
        # read what was bought.
        if whole_second is not None:
            filled = wc.words_to_add(whole_first, whole_second, windows,
                                     lyric_keys)
            lines += ["", t("heavy_two_languages_filled").format(
                count=len(filled), name=code), ""]
            if filled:
                lines += [f"| {t('search_col_spot')} | {code} |",
                          "| --- | --- |"]
            for word in filled:
                lines.append(
                    f"| {float(word['start']):.1f}-{float(word['end']):.1f} |"
                    f" {str(word.get('text', ''))[:44]} |")
    lines += ["", t("heavy_two_languages_note")]
    return lines


# --------------------------------------------------------------------------
# B531 - 1.5.12: every video again
# --------------------------------------------------------------------------

#: Which stored background belongs on every video (B531). The user
#: wants one look over the whole collection; this is the picture he
#: picked.
STANDARD_BACKGROUND = "background_001.png"


def _old_videos_folder(context, song: str) -> Path:
    """Where the replaced videos go (B531).

    Next to the program folder, in the scrap folder the user empties
    himself - inside it they would be pollution in a folder that is
    supposed to hold the program. Is that not writable, then a folder in
    the project root, so the job never fails on where to put things.
    """
    outside = context.paths.root.parent
    if outside != context.paths.root and \
            pipeline.filesystem.is_writable(outside):
        base = outside / "_to_delete" / "oude_videos"
    else:
        base = context.paths.root / "_to_delete" / "oude_videos"
    return base / song if song else base


def rebuild_videos(context, report: Reporter, cancelled) -> str:
    """1.5.12 - render every video again (B531).

    Not a measurement but a job, and it is the second time it is needed:
    the first after the outlining was improved (v0.146.0), now after the
    silence in front of the sound was repaired (B530). Whenever
    something about the picture changes, everything that was already
    finished is a version behind.

    Per project, in this order: put the standard background in place,
    render beside the existing files, and only when that render has
    passed its own check (B530 refuses a video that runs out of step)
    move the old ones to the scrap folder and give the new one the plain
    name. Goes something wrong, then nothing is thrown away and the
    table says so.
    """
    import shutil

    songs = _projects(context)
    if not songs:
        return t("test_no_projects")
    stored = context.paths.backgrounds_dir / STANDARD_BACKGROUND
    # Worked out once: the check behind it writes a probe file, and
    # doing that per project would leave a trail next to the program
    # folder.
    scrap = _old_videos_folder(context, "")
    lines = [t("rebuild_intro").format(count=len(songs),
                                       background=STANDARD_BACKGROUND), "",
             f"{'project':32s} {'uitkomst':>10s}  {'oud':>4s}  bijzonderheden"]
    made = replaced = 0
    steps = Steps(report, "1.5.12", len(songs))
    for song in songs:
        if cancelled():
            break
        steps.tick()
        steps.name(f"1.5.12  {song}")
        other = pipeline.context_for_project(context, song)
        if not other.paths.timing_file.exists():
            lines.append(f"{song:32s} {'overgeslagen':>10s}  {'-':>4s}"
                         f"  {t('rebuild_no_timing')}")
            continue
        note = ""
        if stored.exists():
            try:
                pipeline.apply_background(other, stored)
            except OSError as exc:      # noqa: PERF203 - one project, not the rest
                note = f"{t('rebuild_background_failed')}: {exc}"
        else:
            note = t("rebuild_background_missing")
        plain = pipeline.video_target(other)
        old = pipeline.existing_videos(other, like=plain)
        fresh = pipeline.next_video_target(plain)
        try:
            pipeline.run_video(other, target=fresh)
        except Exception as exc:        # noqa: BLE001 - one project, not the rest
            logger.exception(t("log_test_project_failed"), song)
            trouble = f"{note}; {exc}" if note else str(exc)
            lines.append(f"{song:32s} {'MISLUKT':>10s} {len(old):5d}"
                         f"  {trouble[:70]}")
            continue
        made += 1
        # The render checked itself (B530); only now may the old ones go.
        folder = scrap / song
        moved = 0
        kept = []
        for path in old:
            try:
                folder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(folder / path.name))
                moved += 1
            except OSError as exc:      # noqa: PERF203
                kept.append(path)
                note = (note + "; " if note else "") + str(exc)[:50]
        replaced += moved
        # Only give the new render the plain name when the old file of
        # that name really is out of the way. ``replace`` overwrites, so
        # doing it anyway would destroy the very video that could not be
        # put safely aside.
        if plain in kept:
            note = (note + "; " if note else "") + t("rebuild_kept_name")
        else:
            try:
                fresh.replace(plain)
                step = dict(other.store.get_step("video") or {})
                step["file"] = str(plain)
                other.store.set_step("video", step)
            except OSError as exc:
                note = (note + "; " if note else "") + str(exc)[:50]
        lines.append(f"{song:32s} {'nieuw':>10s} {moved:5d}  {note}")
    lines += ["", t("rebuild_total").format(
        made=made, replaced=replaced, folder=scrap / "<project>")]
    return "\n".join(lines)


#: The heavy investigations. With this list empty, 1.5.11 does not
#: appear in the panel at all - no empty line and no greyed-out button
#: (B371).
HEAVY_TRIALS: tuple[HeavyTrial, ...] = (
    HeavyTrial("1.5.11a", "heavy_clusters", cluster_trial),
    HeavyTrial("1.5.11b", "heavy_search", search_trial),
    # B454/B512: 1.5.11c answered B391 three times with "no", six of its
    # eight variants were already retired, and on its own measure
    # "current" beats VAD. It stood switched off since v0.144.0; with
    # the decision that the whole panel goes at publication there is no
    # reason left to keep a trial that can only repeat its answer.
    # B454: the cutting is in production since v0.138.0 and this trial
    # took 3975 of the 4297 seconds of the whole heavy bin - 92% - to
    # confirm every time what we already know.
    HeavyTrial("1.5.11d", "heavy_chunk", chunk_trial, off=True,
               reason="chunk_answered"),
    # B491: answered, and the answer is no. Over four songs the loudest
    # level wins on the total (193.5 s unheard against 220.2 as it is),
    # but it loses hard on Lied_T, where "in the text"
    # drops to 62% - those extra words are inventions, not singing that
    # was finally heard. And the assumption underneath it is refuted:
    # Groen is by far the quietest stem (-27.0 LUFS) and hardly changes,
    # while the song that gains most sits at an ordinary -14.3. Level is
    # not what makes the difference, so nothing goes to production and
    # this goes off - like c and d.
    HeavyTrial("1.5.11e", "heavy_gain", gain_trial, off=True,
               reason="gain_answered"),
    # B515/B538: not "the whole song in the other language" - that was
    # measured at B495 and it loses - and no longer the second language
    # over the weak spots of the first either, which is the route this
    # trial was built around and which turned out not to work. What it
    # does now is check, on a NEW song, whether the merge production
    # makes since B538 is still the best of the ways of reading.
    HeavyTrial("1.5.11g", "heavy_two_languages", two_language_trial),
    # B504: what the button of B497 was worth is answered - nothing.
    # Over eighteen projects the pooled median stayed on 1 ms before and
    # 1 ms after; on the five songs where the user really had moved
    # syllables by hand it won nothing four times and lost 14 ms once.
    # Where c, d and e were switched off and kept, this one went out
    # with its subject: the button is gone, so a trial that measures it
    # can no longer run. The numbers are in development_log.md.
)


#: A syllable counts as HELD from this length, and only if it is far
#: above the median of its own line (B437). Both conditions matter: a
#: slow song has long syllables everywhere, and then none of them is
#: special.
HELD_S = 0.35
HELD_FACTOR = 4.0


def inventory_lines(context, cancelled) -> list[str]:
    """Three countings that need no Whisper, under 1.5.7 (B437).

    Deliberately cheap and deliberately together. Each of the three
    turns a hunch into a number, and each has a history of hunches that
    were wrong:

    * which lyric words NEVER couple - twice now that turned out to be a
      whole class of words that could not match in principle (digits,
      B412; hyphens, B418), and both times it was found by hand;
    * how often a syllable is HELD - the render can already show that
      (``Syllable.held``), but nothing sets it, so over all projects
      there is not one;
    * whether blocks that repeat also last equally long - the drift runs
      of B389 are a block phenomenon and every correction we have works
      per line.
    """
    lines = [t("inventory_intro"), ""]
    lines += _uncoupled_words(context, cancelled)
    lines += _held_syllables(context, cancelled)
    lines += _block_drift(context, cancelled)
    return lines


def _uncoupled_words(context, cancelled) -> list[str]:
    """Which lyric words never couple, over all projects (B437)."""
    import collections
    import re

    never = collections.Counter()
    total = coupled = 0
    for song in _projects(context):
        if cancelled():
            break
        path = (_paths_for(context, song).output_dir / "original"
                / "lyrics_alignment.txt")
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "->" not in line:
                continue
            total += 1
            word = line.split("->")[0].strip()
            if "(niet gekoppeld)" in line:
                never[word.lower()] += 1
            elif re.search(r"sim 0\.00", line):
                never[word.lower()] += 1
            else:
                coupled += 1
    out = ["## " + t("inventory_uncoupled"), ""]
    if not total:
        return out + [t("inventory_no_material"), ""]
    out.append(t("inventory_uncoupled_head").format(
        total=total, never=total - coupled,
        percent=100.0 * (total - coupled) / max(1, total)))
    out += ["", "| woord | keer | lengte |", "| --- | ---: | ---: |"]
    for word, count in never.most_common(25):
        out.append(f"| {word} | {count} | {len(word)} |")
    return out + [""]


def _held_syllables(context, cancelled) -> list[str]:
    """How often a syllable is held long, and where (B437)."""
    import statistics

    from . import timing as timing_module

    found = []
    total = 0
    for song in _projects(context):
        if cancelled():
            break
        path = _paths_for(context, song).timing_file
        if not path.exists():
            continue
        for line in timing_module.load_timing(path):
            spans = [s.end - s.start for s in line.syllables]
            if not spans:
                continue
            total += len(spans)
            middle = statistics.median(spans)
            for syllable, span in zip(line.syllables, spans):
                if span >= HELD_S and middle > 0 \
                        and span >= HELD_FACTOR * middle:
                    found.append((span, song, line.index,
                                  syllable.text.strip()))
    found.sort(reverse=True)
    out = ["## " + t("inventory_held"), ""]
    if not total:
        return out + [t("inventory_no_material"), ""]
    out.append(t("inventory_held_head").format(
        count=len(found), total=total,
        percent=100.0 * len(found) / max(1, total)))
    out += ["", "| duur | project | regel | lettergreep |",
            "| ---: | --- | ---: | --- |"]
    for span, song, index, text in found[:20]:
        out.append(f"| {span:.2f} s | {song} | {index} | {text} |")
    return out + ["", t("inventory_held_note"), ""]


def _block_drift(context, cancelled) -> list[str]:
    """Do blocks that repeat also last equally long? (B437)"""
    import collections
    import statistics

    from . import timing as timing_module

    rows = []
    for song in _projects(context):
        if cancelled():
            break
        path = _paths_for(context, song).timing_file
        if not path.exists():
            continue
        blocks = collections.defaultdict(list)
        for line in timing_module.load_timing(path):
            if line.syllables:
                blocks[line.block].append(line)
        shapes = collections.defaultdict(list)
        for number, block in sorted(blocks.items()):
            key = " | ".join(_norm(line.text) for line in block)
            span = (block[-1].syllables[-1].end
                    - block[0].syllables[0].start)
            shapes[key].append((number, span))
        for key, occurrences in shapes.items():
            if len(occurrences) < 2:
                continue
            spans = [span for _n, span in occurrences]
            spread = max(spans) - min(spans)
            rows.append((spread, song, len(occurrences),
                         statistics.median(spans), key))
    rows.sort(reverse=True)
    out = ["## " + t("inventory_blocks"), ""]
    if not rows:
        return out + [t("inventory_no_material"), ""]
    out.append(t("inventory_blocks_head").format(count=len(rows)))
    out += ["", "| spreiding | project | keer | mediaan | blok |",
            "| ---: | --- | ---: | ---: | --- |"]
    for spread, song, count, middle, key in rows[:20]:
        out.append(f"| {spread:.2f} s | {song} | {count} | {middle:.2f} s |"
                   f" {key[:44]} |")
    return out + [""]


def _norm(text: str) -> str:
    return " ".join(str(text).lower().split())


def heavy_trial(context, report: Reporter, cancelled) -> str:
    """1.5.11 - the night jobs, kept away from the 'all' button.

    Every investigation has its own version threshold and skips itself as
    long as that is not met; "Measure again" forces it anyway. The file
    is written after every investigation to ``docs/modelcombinaties.md``.
    """
    from . import __version__, test_history

    report_file = COMBINATION_REPORT
    report_file.parent.mkdir(parents=True, exist_ok=True)
    keep_dated_copy(report_file)                 # B534, see big_trial
    lines = ["# Modelcombinaties", "", t("heavy_intro"), ""]

    def write_report() -> None:
        report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    write_report()
    # B402: the top row is the ACTION - which of the four investigations
    # we are in. The work slots below say what they are chewing on.
    steps = Steps(report, "1.5.11", len(HEAVY_TRIALS))
    for trial in HEAVY_TRIALS:
        if cancelled():
            break
        steps.tick()
        steps.name(trial.code)          # B409: de letter op de bovenste rij
        head = ["", f"## {trial.code} {t(trial.name_key)}", ""]
        if trial.off:                                    # B454
            lines += head + [t("heavy_switched_off").format(
                reason=t(f"heavy_off_{trial.reason}"))]
            write_report()
            continue
        if not _wanted(trial.code):                      # B453
            lines += head + [t("heavy_not_chosen")]
            write_report()
            continue
        # B452: the twenty-version brake is gone. It held back exactly
        # the two trials that needed to run, and it protected an outcome
        # we knew was invalid. What is left is the rule the light
        # actions already had - measured once on this version and this
        # state of the files, then reused. The letters you tick are the
        # brake now.
        done = _heavy_done(context, trial.code)
        if done is not None and not REMEASURE:
            lines += head + [t("heavy_already").format(version=done)]
            write_report()
            continue
        global _RUNNING_CODE
        _RUNNING_CODE = trial.code
        import time as _time
        start = _time.monotonic()
        lines += head
        try:
            lines += list(trial.function(context, report, cancelled))
        except TrialSkipped as skipped:
            # B385: the reason goes in the report, but this does NOT
            # count as a run - otherwise the trial books its whole
            # version holiday for a measurement that never happened.
            lines += skipped.lines
            write_report()
            continue
        write_report()
        seconds = _time.monotonic() - start
        test_history.remember_duration(trial.code, __version__, seconds)
        _remember_heavy(context, trial.code, seconds)     # B452
    lines += alarm_lines()                       # B435
    write_report()
    return t("heavy_done").format(path=report_file.name, count=len(lines))


#: The list as it stands in the panel.
#:
#: B365: the maximum is TEN. That forces merging instead of endless
#: growth, and ten still fits in one window. The numbering was relaid at
#: the same time: 1.5.3, 1.5.4 and 1.5.5 were three cheap reports over
#: the same files and are now 1.5.3 together, and the omission trial and
#: the big trial moved back. That means "run 1.5.7" is something else
#: than last week; the manual and the conversation have to follow.
MAX_ACTIONS = 10

ACTIONS: tuple[TestAction, ...] = (
    TestAction("1.5.1", "test_fill_cache", "test_fill_cache_hint",
              True, fill_cache),
    TestAction("1.5.2", "test_status", "test_status_hint",
              True, benchmark_status),
    TestAction("1.5.3", "test_reports", "test_reports_hint",
              True, project_report),
    TestAction("1.5.4", "test_missing", "test_missing_hint",
              True, missing_repetitions),
    TestAction("1.5.5", "test_ruler", "test_ruler_hint", True, yardstick),
    TestAction("1.5.6", "test_split", "test_split_hint",
              True, unique_against_repeated),
    TestAction("1.5.7", "test_syllables", "test_syllables_hint",
              True, syllable_checks),
    TestAction("1.5.9", "test_leave_out", "test_leave_out_hint",
              True, omission_trial),
    TestAction("1.5.10", "test_matrix", "test_matrix_hint",
              True, big_trial),
    # B371: the heavy bin. With nothing in HEAVY_TRIALS the panel leaves
    # this line out entirely.
    TestAction("1.5.11", "test_heavy", "test_heavy_hint",
              True, heavy_trial, heavy=True),
    # B531: a job and not a measurement, so it stands at the end, never
    # joins the 'all' tick and does not count towards MAX_ACTIONS.
    TestAction("1.5.12", "test_rebuild", "test_rebuild_hint",
              True, rebuild_videos, on_request=True),
)


#: Where every test action writes its lines (B524/B534). The log window
#: keeps them too, but that window lives on the user's machine and its
#: text cannot be handed over; these files can.
#:
#: B534: a folder and no longer one fixed file. The single file was
#: overwritten by the next run, and that is precisely what the user does
#: NOT want: he measures everything, then makes a new project, measures
#: that one alone - and the first result was gone. Measurement files:
#: they are never shipped, and the user empties the folder himself.
REPORT_DIR = Path(__file__).resolve().parents[1] / "docs" / "verslagen"

#: The report of the run that is busy (B534). ``start_trial_report``
#: gives it a name; until then there is none.
TRIAL_REPORT: Path | None = None


def report_name(codes: Sequence[str], version: str = "", scope: str = "",
                moment=None) -> str:
    """The name of one report: when, which version, what was run (B534).

    Everything that tells two runs apart is in the name, because that is
    all the user sees in his folder. A long tick list becomes "first to
    last": twelve codes in a file name help nobody.
    """
    from datetime import datetime

    moment = moment or datetime.now()
    codes = [str(code) for code in codes if str(code)]
    if len(codes) > 3:
        what = f"{codes[0]}-tm-{codes[-1]}"
    else:
        what = "-".join(codes) or "los"
    parts = [f"testverslag_{moment.strftime('%Y-%m-%d_%H%M%S')}"]
    if version:
        parts.append(f"v{version}")
    parts.append(what)
    if scope:
        parts.append(scope)
    return _tidy_name("_".join(parts)) + ".md"


def _tidy_name(text: str) -> str:
    """A file name Windows accepts, without losing what it says."""
    keep = [c if (c.isalnum() or c in "._-") else "-" for c in str(text)]
    name = "".join(keep)
    while "--" in name:
        name = name.replace("--", "-")
    return name.strip("-_") or "testverslag"


def _free_path(path: Path) -> Path:
    """``path``, or the first free ``_2``, ``_3``, ... beside it (B534).

    Two runs within the same second is unlikely, but "unlikely" is what
    the fixed file name was too, and that is exactly what cost the user
    a morning of measuring.
    """
    if not path.exists():
        return path
    for number in range(2, 100):
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        if not candidate.exists():
            return candidate
    # A hundred within the same second is not to be believed - but the
    # fixed file name was not to be believed either.
    from uuid import uuid4

    return path.with_name(f"{path.stem}_{uuid4().hex[:8]}{path.suffix}")


def keep_dated_copy(path: Path) -> Path | None:
    """Put a dated copy of a report beside the others (B534).

    ``modelmatrix.md`` and ``modelcombinaties.md`` are overwritten
    during their own run - that is right, they describe the run that is
    busy - but they may not quietly wipe the previous run. Returns the
    copy, or ``None`` when there was nothing to copy: a report that
    failed may never take a test down with it.

    Is the folder of reports unusable, then the copy lands BESIDE the
    source. That folder is by definition writable - the run is about to
    write its report there - and a copy in an awkward place is worth
    more than the previous run being overwritten after all, which is
    exactly what B534 exists to prevent.
    """
    import shutil
    from datetime import datetime

    path = Path(path)
    if not path.exists():
        return None
    moment = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = _tidy_name(f"{path.stem}_{moment}") + path.suffix
    for folder in (REPORT_DIR, path.parent):
        target = _free_path(folder / name)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        except OSError:
            continue
        return target
    logger.warning(t("log_report_write_failed"), REPORT_DIR / name)
    return None


def start_trial_report(codes: Sequence[str], scope: str,
                       version: str = "") -> None:
    """Begin a fresh report for the coming run (B524/B534)."""
    from datetime import datetime

    global TRIAL_REPORT

    moment = datetime.now()
    TRIAL_REPORT = _free_path(
        REPORT_DIR / report_name(codes, version, scope, moment))
    lines = ["# " + t("report_title"), ""]
    lines += [t("report_when") % moment.strftime("%Y-%m-%d %H:%M"), ""]
    if version:
        lines += [t("report_version") % version, ""]
    lines += [t("report_scope") % scope, "",
              t("report_actions") % ", ".join(codes), ""]
    _write_trial_report("\n".join(lines) + "\n", append=False)
    # B534: which file this run is in. There are many of them now, and
    # the user has to be able to find the right one afterwards.
    logger.info(t("log_report_file"), TRIAL_REPORT)


def add_trial_result(code: str, name: str, text: str,
                     seconds: float, cpu: float,
                     alarms: Sequence[str] = ()) -> None:
    """Add the lines of one finished action to the report (B524)."""
    lines = ["", f"## {code} - {name}", "",
             t("report_time") % (seconds, cpu), "", "```"]
    lines.extend(str(text).splitlines() or [""])
    lines.append("```")
    # B537: the alarms are a table with a sentence above it, and they
    # used to be written away line by line as a bullet. That gave an
    # empty bullet (the blank line the block opens with), a table that
    # could no longer render, and under no alarm at all a reassuring
    # line under "Alarms:". They now go in as a block, and that line
    # only appears when there is something to say.
    block = list(alarms)
    while block and not str(block[0]).strip():
        block.pop(0)
    while block and not str(block[-1]).strip():
        block.pop()
    if block:
        lines.extend(["", t("report_alarms"), ""])
        lines.extend(str(line) for line in block)
    _write_trial_report("\n".join(lines) + "\n", append=True)


def _write_trial_report(text: str, append: bool) -> None:
    """Write to the report file; a failure may never stop a test.

    B534: an action that runs without a started report (the panel is not
    the only way in) begins one of its own. Writing on the newest report
    that happens to be lying there looked friendlier, but that report
    says at the top when it was made and with which version, and those
    lines would then be about a different run.
    """
    global TRIAL_REPORT

    if TRIAL_REPORT is None:
        TRIAL_REPORT = _free_path(REPORT_DIR / report_name([]))
    target = TRIAL_REPORT
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a" if append else "w",
                  encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        logger.warning(t("log_report_write_failed"), target)


def visible_actions() -> tuple[TestAction, ...]:
    """The actions that end up in the panel (B371).

    A heavy action with no investigations under it does not appear: no
    empty line, no greyed-out button.
    """
    return tuple(a for a in ACTIONS
                 if not a.heavy or HEAVY_TRIALS)


class TestPanel(QDialog):
    """Tick list with the numbered test functions (TEMPORARY)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("test_panel_title"))
        outer = QVBoxLayout(self)
        outer.addWidget(QLabel(t("test_panel_intro")))

        # B367: one button at the top that toggles. All on, clicking
        # again is all off. The rule that nothing is on when the window
        # OPENS stays: this is a deliberate click, not a state that
        # lingers.
        top_row = QHBoxLayout()
        self._all_button = QPushButton(t("test_select_all"))
        self._all_button.clicked.connect(self._toggle_all)
        top_row.addWidget(self._all_button)
        self._again = QCheckBox(t("test_force_again"))
        self._again.setToolTip(t("test_force_again_hint"))
        top_row.addWidget(self._again)
        top_row.addStretch(1)
        outer.addLayout(top_row)

        group = QGroupBox()
        inner = QVBoxLayout(group)
        self._actions = visible_actions()
        self._ticks: list[QCheckBox] = []
        for action in self._actions:
            tick = QCheckBox(f"{action.code}  {t(action.name_key)}")
            # Always off when opening: a forgotten tick on a heavy test
            # costs half an hour.
            tick.setChecked(False)
            explanation = QLabel(t(action.explanation_key))
            explanation.setWordWrap(True)
            explanation.setStyleSheet("color: #666; margin-left: 22px;")
            inner.addWidget(tick)
            inner.addWidget(explanation)
            self._ticks.append(tick)
            if action.heavy and HEAVY_TRIALS:
                # B453: the letters used to be a grey line of prose under
                # the number (B397). They are ticks now, so you can run
                # one investigation instead of the whole bin - which is
                # what replaces the twenty-version brake that came out
                # with B452.
                self._letters = []
                for trial in HEAVY_TRIALS:
                    label = f"{trial.code}  {t(trial.name_key)}"
                    if trial.off:
                        label += "  " + t("test_letter_off")
                    letter = QCheckBox(label)
                    letter.setEnabled(not trial.off)
                    # B461: off, like the number above them. They used to
                    # open TICKED while 1.5.11 itself was not, so the
                    # panel showed "a, b, e chosen" and meant "nothing
                    # chosen" - press start and nothing happens.
                    letter.setChecked(False)
                    letter.setStyleSheet("margin-left: 22px;")
                    letter.toggled.connect(self._letters_changed)
                    inner.addWidget(letter)
                    self._letters.append((letter, trial))
                tick.toggled.connect(self._heavy_toggled)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        holder.setLayout(QVBoxLayout())
        holder.layout().addWidget(group)
        scroll.setWidget(holder)
        outer.addWidget(scroll, stretch=1)

        self._current = QRadioButton(t("test_scope_current"))
        self._all_scope = QRadioButton(t("test_scope_all"))
        self._all_scope.setChecked(True)
        outer.addWidget(self._current)
        outer.addWidget(self._all_scope)

        buttons = QDialogButtonBox()
        self._start = QPushButton(t("test_start"))
        buttons.addButton(self._start, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.resize(720, 560)

    def _toggle_all(self) -> None:
        """All on, or - if all is already on - all off (B367).

        B371: a heavy action NEVER joins in here. It costs hours and
        should be a deliberate choice, even when you mean 'all'.

        B531: neither does a job like 1.5.12. Making every video again
        overwrites finished work; that is a choice you make on purpose
        and never by ticking 'all'.
        """
        light = [v for v, a in zip(self._ticks, self._actions)
                 if not a.heavy and not a.on_request]
        turn_on = not all(v.isChecked() for v in light)
        for tick in light:
            tick.setChecked(turn_on)
        self._all_button.setText(t("test_select_none") if turn_on
                                else t("test_select_all"))

    def _heavy_tick(self):
        """The 1.5.11 tick itself, or ``None`` when it is not there."""
        return next((tick for tick, action
                     in zip(self._ticks, self._actions) if action.heavy),
                    None)

    def _heavy_toggled(self, on: bool) -> None:
        """1.5.11 on = all its letters on, off = all of them off (B453).

        The lock is not decoration: the number sets the letters and the
        letters set the number, so without it the two would keep waking
        each other up.
        """
        if getattr(self, "_busy", False):
            return
        self._busy = True
        try:
            for letter, trial in getattr(self, "_letters", ()):
                if not trial.off:
                    letter.setChecked(on)
        finally:
            self._busy = False

    def _letters_changed(self, _on: bool) -> None:
        """The number follows its letters (B453/B461).

        At least one letter ticked means 1.5.11 runs; the last one off
        means it does not. Before B461 only the second half of that was
        true, so ticking a letter looked like a choice and did nothing.
        """
        if getattr(self, "_busy", False):
            return
        letters = getattr(self, "_letters", ())
        tick = self._heavy_tick()
        if not letters or tick is None:
            return
        any_on = any(box.isChecked() for box, trial in letters
                     if not trial.off)
        if tick.isChecked() == any_on:
            return
        self._busy = True
        try:
            tick.setChecked(any_on)
        finally:
            self._busy = False

    def heavy_choice(self) -> list[str]:
        """The ticked letters of 1.5.11 (B453)."""
        return [trial.code for box, trial in getattr(self, "_letters", ())
                if box.isChecked() and not trial.off]

    def remeasure(self) -> bool:
        """Ignore stored results and do everything again (B362)."""
        return self._again.isChecked()

    def chosen(self) -> list[TestAction]:
        """The ticked actions, in numeric order."""
        return [action for action, tick in zip(self._actions, self._ticks)
                if tick.isChecked()]

    def only_this_project(self) -> bool:
        return self._current.isChecked()
