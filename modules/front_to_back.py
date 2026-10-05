"""1.5.13 - every song from the start, in every way (v1.0.13, B584).

The owner's question: which way of listening, laying on and hearing
again gives the best timing - measured on ALL his songs with a hand-made
timing, each made again from step 1.1, and first the way the program
does it now. His hand timings are the measure and are only ever read:
every run happens on a copy in the scrap folder next to the program
(``_to_delete``), one project at a time, and the copy goes when it has
been measured.

The first night (v1.0.13) measured every way there was: the old way of
cutting, cutting everywhere, no known text, a hint per piece, "Listen
again" taken over automatically in three forms, and each new check.
Its answers are in the development log (B594); the axes stay in
:class:`Variant` so any of them can be measured again in one line.
The second, short night (v1.0.14) measures what was left open:

* **the zero measurement** - the program as v1.0.13 ships it;
* **one change at a time** from there - the hint per piece (B583) and
  stacked lines losing their anchor (B595);
* **both together**, and
* **a combination**, built greedily on two thirds of the songs from the
  changes that helped, and then held against the third that took no part
  in building it - with twenty songs, whatever wins on all of them may
  simply have been lucky.

The yardstick (B594): the share of lines within 0.3 s of the hand
timing, the error capped at 2 s, lines more than 2 s off, and per song
whether it got better or worse. The first night judged on the plain
mean, and one song running seven seconds off for its last eighteen
lines decided the whole combination; capped, one runaway song weighs
like any other. Held against the zero measurement as well: lines it
got wrong that are now right, and lines it got right that are now worse.
Beside it how much measured singing stays without a word and which share
of the words is in the lyrics, so a variant cannot win by inventing.

Whisper is the cost. Every piece that two variants hear the same way -
same stretch, same hint, same settings - is heard once: the results are
kept per song in the scrap folder, so a night that was broken off picks
up where it stopped, and so does a second night.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import statistics
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable, Sequence

from . import pipeline, whisper
from .translations import t

logger = logging.getLogger(__name__)

#: The scrap folder of this trial, inside ``_to_delete``.
SCRATCH_NAME = "kt_front_to_back"

#: "Listen again" above a threshold takes a candidate only from this
#: score on. The referee's scale; half of it is where a candidate is
#: more supported than not.
THRESHOLD = 0.5

#: Every third song stays out of building the combination.
HOLDOUT_EVERY = 3

#: A line counts as wrong from this far off the hand timing - the same
#: 0.3 s the yardstick calls "moved by hand".
WRONG_S = 0.3

#: B594: an error counts for at most this much, and a line further off
#: counts as run away.
CAP_S = 2.0

#: B594: a song is better or worse when its capped mean moves more than
#: this.
SONG_MARGIN_S = 0.03

#: The ideas of these rounds in the model register; the rest of the
#: register stays as the user set it.
NEW_MODELS = ("B578", "B579", "B580", "B581", "B583", "B595")


@dataclass(frozen=True)
class Variant:
    """One way of making a song, from 1.1 to the timing."""

    key: str
    #: "v1011" (30-second pieces, no known text), "v1012" (short pieces
    #: through singing) or "everywhere" (the whole song in short pieces).
    listening: str = "v1012"
    gap_text: bool = True
    #: "none", "best" or "threshold".
    again: str = "none"
    hint: str = "lines"
    #: New models switched ON; the rest of :data:`NEW_MODELS` is off.
    models: tuple[str, ...] = ()
    #: The changes this variant is made of, for the report.
    parts: tuple[str, ...] = field(default=(), compare=False)

    def signature(self) -> str:
        data = asdict(self)
        data.pop("key")
        data.pop("parts")
        data["models"] = sorted(self.models)
        return json.dumps(data, sort_keys=True)


#: The zero measurement: what v1.0.13 ships - the four checks on, no
#: hint per piece, and "Listen again" is the user's button, not
#: automatic. (B594: the first night measured from v1.0.12; v1.0.13
#: came out level with it, 72.9% of the lines within 0.3 s against
#: 72.7%, no song worse.)
SHIPPED_MODELS = ("B578", "B579", "B580", "B581")
BASELINE = Variant("baseline", models=SHIPPED_MODELS)

#: One change at a time from the zero measurement: what the first night
#: left open. ``again`` changes that only mean something with "Listen
#: again" carry it along.
CHANGES: tuple[Variant, ...] = (
    Variant("piece_hint", models=SHIPPED_MODELS + ("B583",)),
    Variant("stacked", models=SHIPPED_MODELS + ("B595",)),
)


def combined(changes: Sequence[Variant], key: str = "combined") -> Variant:
    """One variant that makes all ``changes`` at once."""
    out = replace(BASELINE, key=key)
    models: set[str] = set(BASELINE.models)
    for change in changes:
        if change.listening != BASELINE.listening:
            out = replace(out, listening=change.listening)
        if change.gap_text != BASELINE.gap_text:
            out = replace(out, gap_text=change.gap_text)
        if change.again != BASELINE.again:
            # "best" wins over "threshold": taking more is the bolder
            # change, and the threshold variant can still win on its own.
            if out.again == BASELINE.again or change.again == "best":
                out = replace(out, again=change.again)
        if change.hint != BASELINE.hint:
            out = replace(out, hint=change.hint)
        models.update(change.models)
    return replace(out, models=tuple(sorted(models)),
                   parts=tuple(change.key for change in changes))


#: Both changes of the short night together, measured whatever the
#: greedy search makes of them: the owner asked for it by name.
BOTH = combined(CHANGES, key="both")


# --------------------------------------------------------------------------
# Measuring one song in one way
# --------------------------------------------------------------------------

def _hand_lines(project_dir: Path) -> list[dict] | None:
    path = project_dir / "settings" / "timing.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = data["lines"] if isinstance(data, dict) else data
    return lines or None


def _start(line: dict) -> float:
    pieces = line.get("syllables") or []
    return float(pieces[0]["start"]) if pieces else 0.0


def songs_with_hand_timing(context) -> list[str]:
    """The projects this trial can measure: a hand timing and lyrics."""
    from . import song_text
    from .test_panel import _projects

    out = []
    for song in _projects(context):
        other = pipeline.context_for_project(pipeline.read_only(context),
                                             song)
        if (_hand_lines(other.paths.output_dir) is not None
                and (other.paths.input_dir
                     / song_text.LYRICS_FILENAME).exists()):
            out.append(song)
    return out


def _inputs_of(context, song: str) -> str:
    """What a measurement of this song rests on besides the program:
    its hand timing, lyrics and karaoke text. Change one between two
    nights and the song is measured again."""
    from . import karaoke_text, song_text

    other = pipeline.context_for_project(pipeline.read_only(context), song)
    digest = hashlib.sha1()
    for path in (other.paths.output_dir / "settings" / "timing.json",
                 other.paths.input_dir / song_text.LYRICS_FILENAME,
                 other.paths.input_dir / karaoke_text.FILENAME):
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"-")
    return digest.hexdigest()[:12]


def scratch_root(context) -> Path:
    """``_to_delete`` next to the program folder, as the user asked."""
    outside = context.paths.root.parent
    if outside != context.paths.root and \
            pipeline.filesystem.is_writable(outside):
        return outside / "_to_delete" / SCRATCH_NAME
    return context.paths.root / "_to_delete" / SCRATCH_NAME


#: What of the user's project.json the copy may not have: his own work,
#: and what the run makes again.
_LEFT_OUT = ("original_overrides", "word_coupling", "lyrics_override",
             "transcript_override", "stress_original", "coupling",
             "heard_again", "whisper_original", "timing", "video",
             "stress_anchors")


def copy_project(context, song: str, into: Path, listening: str):
    """A working copy of one project under ``into``; its context.

    Input and cache are copied - not linked: the pipeline writes into
    its cache, and through a link that would be the user's own file.
    Only the transcription of the original stays behind, and his hand
    work in ``project.json`` (see :data:`_LEFT_OUT`). The copy
    transcribes like a project from before v1.0.12 when ``listening`` is
    "v1011" - that is what the step without its "listening" mark means.
    """
    source = pipeline.context_for_project(pipeline.read_only(context), song)
    paths = pipeline.filesystem.ProjectPaths(root=into, song=song)
    pipeline.filesystem.ensure_directories(paths)
    for folder, target in ((source.paths.input_dir, paths.input_dir),
                           (source.paths.cache_dir, paths.cache_dir)):
        if not folder.is_dir():
            continue
        for item in folder.rglob("*"):
            if not item.is_file() or item.name == \
                    "transcription_original.json":
                continue
            goal = target / item.relative_to(folder)
            goal.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, goal)
    languages = context.paths.languages_dir
    if languages.is_dir() and not (into / "languages").exists():
        shutil.copytree(languages, into / "languages")
    data = json.loads(source.paths.project_file.read_text(encoding="utf-8"))
    steps = {name: value for name, value in (data.get("steps") or {}).items()
             if name not in _LEFT_OUT}
    if listening == "v1011":
        # The mark of a project transcribed before v1.0.12: a step with
        # no "listening" in it. Only its presence matters.
        steps["whisper_original"] = {"segments": 0}
    data["steps"] = steps
    paths.project_file.parent.mkdir(parents=True, exist_ok=True)
    paths.project_file.write_text(json.dumps(data, ensure_ascii=False),
                                  encoding="utf-8")
    config = replace(context.config,
                     song=replace(context.config.song, title=song))
    return pipeline.AppContext(
        paths=paths, config=config,
        store=pipeline.filesystem.ProjectStore(paths.project_file))


class HeardOnce:
    """Whisper, but every question is asked only once (per song).

    The key is what decides the answer - the stretch, the hint, the
    language and the settings - plus the size of the audio, so the
    copies of one song share it and two songs never do.
    """

    def __init__(self, folder: Path, song: str) -> None:
        self._path = folder / f"{song}.json"
        self._song = song
        try:
            self._known = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._known = {}
        self.asked = 0
        self.heard = 0
        # The Whisper lanes ask from several threads at once.
        self._lock = threading.Lock()

    def _look(self, key: str):
        with self._lock:
            self.asked += 1
            return self._known.get(key)

    def _keep(self, key: str, found) -> None:
        with self._lock:
            self.heard += 1
            self._known[key] = whisper.segments_to_dicts(tuple(found))
            self._save()

    def _key(self, audio, settings, start, end, prompt, language) -> str:
        try:
            size = Path(audio).stat().st_size
        except OSError:
            size = 0
        raw = json.dumps([self._song, Path(audio).name, size,
                          round(float(start or 0.0), 3),
                          None if end is None else round(float(end), 3),
                          str(prompt or ""), str(language or ""),
                          asdict(settings)], sort_keys=True, default=str)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def wrap(self, real: Callable) -> Callable:
        def transcribe_slice(audio_path, settings, start=0.0, end=None,
                             initial_prompt="", language_override=None,
                             cancelled=None):
            key = self._key(audio_path, settings, start, end,
                            initial_prompt, language_override)
            known = self._look(key)
            if known is not None:
                return whisper.segments_from_dicts(known)
            found = real(audio_path, settings, start=start, end=end,
                         initial_prompt=initial_prompt,
                         language_override=language_override,
                         cancelled=cancelled)
            self._keep(key, found)
            return found

        return transcribe_slice

    def wrap_whole(self, real: Callable) -> Callable:
        """The same for a plain run over the whole song."""
        def transcribe(audio_path, settings, output_dir, progress=None,
                       language_override=None, cancelled=None,
                       initial_prompt=""):
            key = "whole:" + self._key(audio_path, settings, 0.0, None,
                                       initial_prompt, language_override)
            known = self._look(key)
            if known is not None:
                return whisper.segments_from_dicts(known)
            found = real(audio_path, settings, output_dir,
                         progress=progress,
                         language_override=language_override,
                         cancelled=cancelled, initial_prompt=initial_prompt)
            self._keep(key, found)
            return found

        return transcribe

    def wrap_aligner(self, real: Callable) -> Callable:
        """The forced aligner as well: it loads its model and the whole
        vocal stem on every call, and a variant that did not change what
        Whisper heard asks it exactly the same question again."""
        def refine(audio_path, segments, language, device="cpu"):
            try:
                size = Path(audio_path).stat().st_size
            except OSError:
                size = 0
            raw = json.dumps(["align", self._song, Path(audio_path).name,
                              size, str(language),
                              whisper.segments_to_dicts(tuple(segments))],
                             sort_keys=True, default=str)
            key = hashlib.sha1(raw.encode("utf-8")).hexdigest()
            known = self._look(key)
            if known is not None:
                return whisper.segments_from_dicts(known)
            found = real(audio_path, segments, language, device)
            # The aligner hands its input back unchanged when it fails
            # (memory, a model that would not load): that is no answer
            # to keep for the next variant or the next night.
            if whisper.segments_to_dicts(tuple(found)) != \
                    whisper.segments_to_dicts(tuple(segments)):
                self._keep(key, found)
            return found

        return refine

    def _save(self) -> None:
        """Written whole to a side file and then put in place, so a
        night that stops halfway never leaves half a file behind."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            spare = self._path.with_suffix(".tmp")
            spare.write_text(json.dumps(self._known), encoding="utf-8")
            spare.replace(self._path)
        except OSError:
            # A virus scanner holding the file costs this one save, not
            # the answer: it is still in memory, and saved with the next.
            logger.warning(t("log_report_write_failed"), self._path)


def _everywhere(windows, total, first_sound=0.0, window_s=None,
                forced_s=None):
    """The whole song in short overlapping pieces, silence or not."""
    from . import whisper_chunks as wc

    length = wc.FORCED_S
    pieces = []
    cursor = float(first_sound)
    while cursor < total - 1e-6:
        end = min(total, cursor + length)
        pieces.append(wc.Chunk(round(cursor, 3), round(end, 3), True))
        if end >= total - 1e-6:
            break
        cursor = end - wc.OVERLAP_S
    return tuple(pieces)


@contextmanager
def ways(variant: Variant, heard: HeardOnce):
    """Everything this variant changes, and back afterwards."""
    from . import listen_again, model_register, word_alignment
    from . import whisper_chunks as wc

    saved = [(word_alignment, "refine", word_alignment.refine),
             (whisper, "transcribe_slice", whisper.transcribe_slice),
             (whisper, "transcribe", whisper.transcribe),
             (wc, "cut_points", wc.cut_points),
             (pipeline, "_with_gap_text", pipeline._with_gap_text),
             (listen_again, "HINT", listen_again.HINT)]
    settings = model_register.current_settings()
    try:
        whisper.transcribe_slice = heard.wrap(whisper.transcribe_slice)
        whisper.transcribe = heard.wrap_whole(whisper.transcribe)
        word_alignment.refine = heard.wrap_aligner(word_alignment.refine)
        if variant.listening == "everywhere":
            wc.cut_points = _everywhere
        if not variant.gap_text:
            pipeline._with_gap_text = (
                lambda context, segments, *a, **k: tuple(segments))
        listen_again.HINT = variant.hint
        states = dict(settings)
        for code in NEW_MODELS:
            states[code] = code in variant.models
        model_register.apply_settings(states)
        model_register.apply_disabled()
        yield
    finally:
        for module, name, value in saved:
            setattr(module, name, value)
        model_register.apply_settings(settings)
        model_register.apply_disabled()


def _take_over(context, how: str, cancelled) -> int:
    """"Listen again" the way the user would press it, automatically."""
    areas = pipeline.listen_again(context, cancelled=cancelled)
    chosen = []
    for area in areas:
        candidates = area.get("candidates") or []
        if not candidates:
            continue
        best = candidates[0]
        if how == "threshold" and float(best["score"]) < THRESHOLD:
            continue
        chosen.append({"low": area["low"], "high": area["high"],
                       "kind": best["kind"], "words": best["words"],
                       "replaced": area.get("replaced", [])})
    return pipeline.accept_heard_again(context, chosen) if chosen else 0


def measure_one(context, song: str, variant: Variant, work: Path,
                heard: HeardOnce, cancelled) -> dict:
    """One song made in one way, and held against the hand timing."""
    from . import whisper_chunks as wc
    from .test_panel import _regression_module, in_the_text

    import time

    began = time.monotonic()
    hand = _hand_lines(pipeline.context_for_project(
        pipeline.read_only(context), song).paths.output_dir)
    folder = work / variant.key
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    try:
        copy = copy_project(context, song, folder, variant.listening)
        with ways(variant, heard):
            pipeline.detect_track(copy, pipeline.TRACK_ORIGINAL,
                                  cancelled=cancelled)
            taken = (_take_over(copy, variant.again, cancelled)
                     if variant.again != "none" else 0)
            made = _regression_module().timing_for(copy, hand)
            segments = pipeline.load_segments(copy, pipeline.TRACK_ORIGINAL)
            words = wc.words_of(segments)
            windows = pipeline._original_vocal_windows(copy)
            unheard = wc.unheard_seconds(words, windows) if windows else 0.0
            in_text = in_the_text(words, pipeline.lyric_keys(copy))
    except whisper.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - one song, not the night
        logger.exception(t("log_front_to_back_failed"), song, variant.key)
        return {"failed": str(exc)[:200]}
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if made is None:
        return {"failed": t("front_to_back_no_timing")}
    fresh, _coupled = made
    # B593: the lines that begin on the same word, also when the hand
    # timing split a line in two.
    pairs = _regression_module().paired_lines(
        [str(line.get("text", "")) for line in hand],
        [line.text for line in fresh])
    if not pairs:
        return {"failed": t("front_to_back_no_timing")}
    return {"starts": [round(float(fresh[j].start), 3) for _i, j in pairs],
            "hand": [round(_start(hand[i]), 3) for i, _j in pairs],
            "index": [i for i, _j in pairs],
            "unheard": round(float(unheard), 2),
            "in_text": round(float(in_text), 4),
            "words": len(words), "taken": int(taken),
            # B599: how long it took, for the time left next time.
            "seconds": round(time.monotonic() - began, 1)}


# --------------------------------------------------------------------------
# Adding it up
# --------------------------------------------------------------------------

@dataclass
class Tally:
    """One variant over a set of songs."""

    lines: int = 0
    #: B594: every error counted for at most :data:`CAP_S`.
    capped: float = 0.0
    good: int = 0
    runaway: int = 0
    fixed: int = 0
    broken: int = 0
    songs_better: int = 0
    songs_worse: int = 0
    unheard: float = 0.0
    in_text: list = field(default_factory=list)
    failed: int = 0

    @property
    def mean(self) -> float:
        """The capped mean: what the combination is chosen on."""
        return self.capped / self.lines if self.lines else float("inf")

    @property
    def share_good(self) -> float:
        return 100.0 * self.good / self.lines if self.lines else 0.0


def _paired(run: dict) -> dict[int, tuple[float, float]]:
    """Hand line -> (start found, hand start) of one stored run."""
    index = run.get("index") or range(len(run["hand"]))
    return {i: (now, truth)
            for i, now, truth in zip(index, run["starts"], run["hand"])}


def tally(results: dict, variant: str, songs: Sequence[str],
          baseline: str = "baseline") -> Tally:
    """Add up one variant over ``songs``; a song where it or the zero
    measurement failed counts as failed and is left out of the sums, so
    two variants are always compared on the same lines."""
    out = Tally()
    for song in songs:
        mine = results.get(song, {}).get(variant)
        zero = results.get(song, {}).get(baseline)
        if not mine or "starts" not in mine or not zero \
                or "starts" not in zero:
            out.failed += 1
            continue
        found, before_of = _paired(mine), _paired(zero)
        common = [i for i in found if i in before_of]
        if not common:
            out.failed += 1
            continue
        mine_capped = zero_capped = 0.0
        for i in common:
            now, truth = found[i]
            off = abs(now - truth)
            before = abs(before_of[i][0] - truth)
            out.lines += 1
            out.capped += min(off, CAP_S)
            mine_capped += min(off, CAP_S)
            zero_capped += min(before, CAP_S)
            out.good += off <= WRONG_S
            out.runaway += off > CAP_S
            if before > WRONG_S >= off:
                out.fixed += 1
            if off > before + WRONG_S:
                out.broken += 1
        shift = (mine_capped - zero_capped) / len(common)
        out.songs_better += shift < -SONG_MARGIN_S
        out.songs_worse += shift > SONG_MARGIN_S
        out.unheard += float(mine.get("unheard", 0.0))
        out.in_text.append(float(mine.get("in_text", 0.0)))
    return out


def helps(trial: Tally, against: Tally) -> bool:
    """B594: a lower capped mean, and no more songs worse than better."""
    return trial.mean < against.mean and \
        trial.songs_better >= trial.songs_worse


def split(songs: Sequence[str]) -> tuple[list[str], list[str]]:
    """The songs that build the combination, and those that check it."""
    check = [song for n, song in enumerate(songs)
             if n % HOLDOUT_EVERY == HOLDOUT_EVERY - 1]
    return [song for song in songs if song not in check], check


def greedy(results_for: Callable[[Variant], None], results: dict,
           changes: Sequence[Variant], songs: Sequence[str],
           cancelled) -> Variant:
    """Build the combination on ``songs``: the changes that helped on
    their own, best first, each kept only if it helps on top of the rest.

    ``results_for`` measures a variant on every song (and fills
    ``results``); the combinations are measured as they are tried.
    """
    zero = tally(results, BASELINE.key, songs)
    helped = sorted((change for change in changes
                     if helps(tally(results, change.key, songs), zero)),
                    key=lambda change: tally(results, change.key,
                                             songs).mean)
    chosen: list[Variant] = []
    best = BASELINE.key
    for change in helped:
        if cancelled():
            break
        trial = combined(chosen + [change],
                         key="combined_" + "_".join(
                             c.key for c in chosen + [change]))
        results_for(trial)
        # B594: held against the best so far, songs counted against it.
        if helps(tally(results, trial.key, songs, baseline=best),
                 tally(results, best, songs, baseline=best)):
            chosen.append(change)
            best = trial.key
    return combined(chosen, key="combined_" + "_".join(
        c.key for c in chosen)) if chosen else BASELINE


# --------------------------------------------------------------------------
# The trial
# --------------------------------------------------------------------------

def _row(label: str, tallied: Tally, zero: Tally) -> str:
    share = statistics.mean(tallied.in_text) if tallied.in_text else 0.0
    gain = zero.mean - tallied.mean if tallied.lines else 0.0
    mean = f"{tallied.mean:.3f}" if tallied.lines else "-"
    return (f"| {label} | {tallied.lines} | {tallied.share_good:.1f}% |"
            f" {mean} | {gain:+.3f} | {tallied.runaway} |"
            f" {tallied.songs_better} / {tallied.songs_worse} |"
            f" {tallied.fixed} | {tallied.broken} |"
            f" {tallied.unheard:.1f} | {share:.1f}% | {tallied.failed} |")


#: The separator under :func:`_row`'s header, one cell per column.
_RULE = "| --- |" + " ---: |" * 11


def _label(variant: Variant) -> str:
    if variant.parts:
        return " + ".join(t(f"ftb_{part}") for part in variant.parts)
    return t(f"ftb_{variant.key}")


def run(context, report, cancelled) -> str:
    """1.5.13 itself. Returns the report as text."""
    from . import __version__
    from . import test_panel

    songs = songs_with_hand_timing(context)
    if not songs:
        return t("front_to_back_nothing")
    root = scratch_root(context)
    work = root / "projects"
    store_path = root / "results.json"
    try:
        stored = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if test_panel.REMEASURE or stored.get("version") != __version__:
        stored = {"version": __version__, "runs": {}}
    if test_panel.REMEASURE:
        # "Measure again" means hearing again too.
        shutil.rmtree(root / "whisper", ignore_errors=True)
    runs: dict = stored["runs"]
    results: dict = {}
    heard_by_song = {song: HeardOnce(root / "whisper", song)
                     for song in songs}

    plan = [BASELINE, *CHANGES, BOTH]
    inputs = {song: _inputs_of(context, song) for song in songs}
    # B599: how long a way took, from what was kept, for the time left.
    prior = {}
    for variant in plan:
        spent = [float(run["seconds"]) for key, run in runs.items()
                 if key.endswith("|" + variant.signature())
                 and run.get("seconds")]
        if spent:
            prior[variant.key] = statistics.mean(spent)
    steps = test_panel.Steps(
        report, "1.5.13", len(plan) * len(songs),
        plan=[variant.key for variant in plan for _song in songs],
        prior=prior)

    def results_for(variant: Variant, counted: bool = False) -> None:
        for song in songs:
            if cancelled():
                return
            key = f"{song}|{inputs[song]}|{variant.signature()}"
            # A failure is tried again next time: it may have been the
            # machine (memory, a busy GPU) and not the way.
            if key not in runs or "failed" in runs[key]:
                report(0, f"{song}  {_label(variant)}")
                runs[key] = measure_one(context, song, variant, work,
                                        heard_by_song[song], cancelled)
                try:
                    root.mkdir(parents=True, exist_ok=True)
                    spare = store_path.with_suffix(".tmp")
                    spare.write_text(json.dumps(stored), encoding="utf-8")
                    spare.replace(store_path)
                except OSError:
                    logger.warning(t("log_report_write_failed"), store_path)
            results.setdefault(song, {})[variant.key] = runs[key]
            if counted:
                steps.tick(1, kind=variant.key)

    for variant in plan:
        if cancelled():
            break
        steps.name(f"1.5.13  {_label(variant)}", kind=variant.key)
        results_for(variant, counted=True)
    build, check = split(songs)
    chosen = BASELINE
    if not cancelled():
        steps.name(f"1.5.13  {t('ftb_combining')}")
        chosen = greedy(results_for, results, CHANGES, build, cancelled)
        if chosen.key != BASELINE.key:
            results_for(chosen)

    lines = ["## " + t("front_to_back_title"), "",
             t("front_to_back_intro").format(count=len(songs),
                                             folder=root), "",
             t("front_to_back_cols"), _RULE]
    zero = tally(results, BASELINE.key, songs)
    for variant in plan:
        lines.append(_row(_label(variant), tally(results, variant.key,
                                                 songs), zero))
    lines += ["", "### " + t("front_to_back_combination"), ""]
    if chosen.key == BASELINE.key:
        lines.append(t("front_to_back_no_combination"))
    else:
        lines += [t("front_to_back_combination_is").format(
                      parts=_label(chosen)), "",
                  t("front_to_back_cols"), _RULE]
        for name, group in ((t("ftb_build_songs"), build),
                            (t("ftb_check_songs"), check)):
            lines.append(_row(f"{name}: {t('ftb_baseline')}",
                              tally(results, BASELINE.key, group),
                              tally(results, BASELINE.key, group)))
            lines.append(_row(f"{name}: {_label(chosen)}",
                              tally(results, chosen.key, group),
                              tally(results, BASELINE.key, group)))
    asked = sum(h.asked for h in heard_by_song.values())
    heard = sum(h.heard for h in heard_by_song.values())
    lines += ["", t("front_to_back_whisper").format(asked=asked,
                                                    heard=heard)]
    failures = [(song, key, value["failed"])
                for song, per in results.items()
                for key, value in per.items() if "failed" in value]
    if failures:
        lines += ["", t("front_to_back_failures")]
        lines += [f"- {song} / {key}: {why}" for song, key, why in failures]
    return "\n".join(lines)
