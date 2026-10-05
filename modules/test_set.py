"""The test set: a few of the owner's songs instead of all (v1.0.22, B630).

The owner's words: "from now on test on a smaller set of my songs -
good, medium, problem cases. Later we can go back to the whole set and
the data sets." A night of 1.5.14 over twenty-two songs is two nights;
over nine it is one, and a verdict on a new model comes a day sooner.

The set is three groups - songs the program already times well, songs
in the middle, and the songs it gets most wrong - so a change that
helps the problem cases and quietly breaks the good ones shows as well.
It is kept in ``config/test_set.json``, which the owner may change (the
panel has a window for it). Without that file the program proposes one
from the last measurement from the start (1.5.13): the songs ranked by
their mean start error against the hand timing, and from the best, the
middle and the worst third the songs spread evenly over it.

The panel runs on the set by default; "all projects" and "only this
project" stay a click away, and the data sets (1.5.16, 1.5.17) are
tests of their own.

v1.0.28 (B663): the set is built as the program goes, not shipped. Every
yardstick test (1.5.15, 1.5.19, 1.5.20) leaves the start error per song
of its baseline in ``config/song_errors.json``; the set is proposed from
the newest of those (and from 1.5.13) every time it is asked for, and
the panel only offers it once there are songs enough for two per group.
A set the owner chose and saved himself is pinned and stays as it is
until he lets it go back to automatic.
"""
from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .translations import t

logger = logging.getLogger(__name__)

FILENAME = "test_set.json"
#: v1.0.28 (B663): the start error per song, as the yardsticks measured it.
ERRORS_FILE = "song_errors.json"
#: At least this many songs per group before the set is offered.
LEAST_PER_KIND = 2
#: The groups, in the order the panel and the reports show them.
KINDS = ("good", "medium", "problem")
#: How many songs a group gets in a proposal.
PER_KIND = 3
#: A start error counts for at most this, as 1.5.13 counts it: one
#: derailed song may not decide the ranking.
_CAP_S = 2.0


def path_for(context) -> Path:
    return context.paths.config_dir / FILENAME


def load(context) -> dict[str, list[str]] | None:
    """The set as the owner keeps it, or ``None`` without a (readable)
    file."""
    try:
        data = json.loads(path_for(context).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, dict):
        return None
    return {kind: [str(song) for song in groups.get(kind) or ()]
            for kind in KINDS}


def pinned(context) -> bool:
    """Did the owner choose the set himself (B663)?"""
    try:
        data = json.loads(path_for(context).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    # A proposal of v1.0.22 to v1.0.27 said "1.5.13"; every other basis
    # is a set somebody chose (the owner's, or one picked by hand with
    # him, like the [bg] and crowd songs of 27 September).
    return isinstance(data, dict) and bool(data.get("basis")) and \
        data.get("basis") != "1.5.13"


def unpin(context) -> None:
    """Back to the set the program builds."""
    try:
        path_for(context).unlink()
    except OSError:
        pass


def note_errors(context, errors: Mapping[str, float], source: str) -> None:
    """v1.0.28 (B663): a yardstick's baseline error per song, kept - the
    newest measurement of a song wins."""
    target = Path(context.paths.config_dir) / ERRORS_FILE
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    songs_ = data.get("songs") if isinstance(data, dict) else None
    songs_ = dict(songs_) if isinstance(songs_, dict) else {}
    for song, error in errors.items():
        if error is not None:
            songs_[str(song)] = {"error": round(float(error), 4),
                                 "source": source}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"songs": songs_}, indent=2,
                                     ensure_ascii=False) + "\n",
                          encoding="utf-8")
    except OSError:
        pass


def errors(context) -> dict[str, float]:
    """Per song the newest start error: the yardsticks over 1.5.13."""
    out = dict(errors_from_the_start(context))
    try:
        data = json.loads((Path(context.paths.config_dir) / ERRORS_FILE)
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    for song, entry in ((data or {}).get("songs") or {}).items():
        if isinstance(entry, dict) and entry.get("error") is not None:
            out[str(song)] = min(float(entry["error"]), _CAP_S)
    return out


def current(context, available: Iterable[str] | None = None
            ) -> dict[str, list[str]] | None:
    """The set as it stands now: the owner's, or the one built from the
    measurements; ``None`` while there are not songs enough."""
    if pinned(context):
        return load(context)
    found = errors(context)
    if available is not None:
        there = set(available)
        found = {song: error for song, error in found.items()
                 if song in there}
    if len(found) < LEAST_PER_KIND * len(KINDS):
        return None
    per_kind = PER_KIND if len(found) >= PER_KIND * len(KINDS) * 2 \
        else LEAST_PER_KIND
    return propose(found, per_kind)


def ready(context, available: Iterable[str] | None = None) -> bool:
    """Is there a set to offer (B663)?"""
    return current(context, available) is not None


def save(context, groups: Mapping[str, Sequence[str]],
         basis: str = "") -> Path:
    """Keep the set (the owner's choice, or a proposal)."""
    target = path_for(context)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"groups": {kind: list(groups.get(kind) or ()) for kind in KINDS},
            "basis": basis}
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return target


def spread(items: Sequence[str], count: int) -> list[str]:
    """``count`` items spread evenly over ``items``, first and last
    included when there is room."""
    if count <= 0 or not items:
        return []
    if len(items) <= count:
        return list(items)
    if count == 1:
        return [items[len(items) // 2]]
    step = (len(items) - 1) / (count - 1)
    return [items[round(n * step)] for n in range(count)]


def propose(errors: Mapping[str, float],
            per_kind: int = PER_KIND) -> dict[str, list[str]]:
    """Three groups from a mean start error per song (lower is better):
    the best, the middle and the worst third, each spread evenly - and
    of the worst third the worst ones, since those are the problem."""
    ranked = sorted(errors, key=lambda song: (errors[song], song))
    third = len(ranked) / 3.0
    best = ranked[:round(third)]
    middle = ranked[round(third):round(2 * third)]
    worst = ranked[round(2 * third):]
    return {"good": spread(best, per_kind),
            "medium": spread(middle, per_kind),
            "problem": worst[-per_kind:] if per_kind else []}


def errors_from_the_start(context) -> dict[str, float]:
    """Per song the mean start error of the last 1.5.13 night, on the
    variant the program runs now (the one with the most models on)."""
    from .front_to_back import scratch_root

    try:
        data = json.loads((scratch_root(context) / "results.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    best: dict[str, tuple[int, float]] = {}
    for key, run in (data.get("runs") or {}).items():
        song, _sep, rest = str(key).partition("|")
        _inputs, _sep, variant = rest.partition("|")
        try:
            models = len(json.loads(variant).get("models") or ())
        except (ValueError, AttributeError):
            models = 0
        pairs = [(a, b) for a, b in zip(run.get("starts") or (),
                                        run.get("hand") or ())
                 if a is not None and b is not None]
        if not pairs:
            continue
        error = statistics.mean(min(abs(float(a) - float(b)), _CAP_S)
                                for a, b in pairs)
        if song not in best or models > best[song][0]:
            best[song] = (models, error)
    return {song: error for song, (_models, error) in best.items()}


def songs(context, available: Iterable[str]) -> list[str]:
    """The songs of the set that are there, good first; the set is
    proposed and kept when there is none yet. Empty when no set can be
    made - the caller then runs on everything, and says so."""
    available = list(available)
    # v1.0.28 (B663): built afresh from the newest measurements, unless
    # the owner pinned it; nothing is written.
    groups = current(context, available)
    if groups is None:
        return []
    there = set(available)
    chosen: list[str] = []
    for kind in KINDS:
        for song in groups.get(kind, ()):
            if song in there and song not in chosen:
                chosen.append(song)
    return chosen


def describe(context) -> str:
    """One line for the panel and the report: the set by group."""
    groups = current(context)
    if groups is None:
        return t("test_set_none")
    return "; ".join(
        f"{t(f'test_set_{kind}')}: " + (", ".join(groups[kind]) or "-")
        for kind in KINDS)
