"""Eval harness for the timing: auto vs. reference per block (B251).

Makes "closer to my version" measurable. Compares an automatic
``timing_auto.json`` with a manual reference (e.g. ``timing.json.bak`` or
a designated *golden* file) and reports per block and in total the
average/median/maximum |onset error| and |duration error| (in ms).

Only lines with exactly the same text count, so that the comparison is not
skewed by a different line division. The functions are pure (json +
statistics); the CLI lives in ``tools/timing_eval.py``.
"""

from __future__ import annotations

import json
import statistics as _st
from pathlib import Path
from typing import Any, Sequence

from .translations import t


def load_rows(path: str | Path) -> list[dict[str, Any]]:
    """Read the line list from a timing file (object or list format)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("lines", []))
    return list(data)


def _syls(row: dict[str, Any]) -> list[dict[str, Any]]:
    return row.get("syllables") or []


def _onset(row: dict[str, Any]) -> float | None:
    syls = _syls(row)
    return float(syls[0]["start"]) if syls else None


def _duration(row: dict[str, Any]) -> float | None:
    syls = _syls(row)
    if not syls:
        return None
    return float(syls[-1]["end"]) - float(syls[0]["start"])


def _norm(text_value: Any) -> str:
    return " ".join(str(text_value or "").split()).lower()


def _stats(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"n": 0, "avg": 0.0, "med": 0.0, "max": 0.0}
    return {"n": len(values),
            "avg": _st.mean(values),
            "med": _st.median(values),
            "max": max(values)}


def compare(auto_rows: Sequence[dict[str, Any]],
              ref_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Compare auto with reference lines; error measures per block, total.

    Lines are paired in order; only pairs with exactly the same
    (normalised) text count. Error measures in **milliseconds**.

    Returns:
        ``{"per_block": {block: {"onset": {...}, "duration": {...}}},
        "total": {"onset": {...}, "duration": {...}}}`` with per measure
        ``n/avg/med/max``.
    """
    per_block_on: dict[int, list[float]] = {}
    per_block_du: dict[int, list[float]] = {}
    all_on: list[float] = []
    all_du: list[float] = []
    for a, h in zip(auto_rows, ref_rows):
        if _norm(a.get("text")) != _norm(h.get("text")):
            continue
        block = int(h.get("block", 0))
        oa, oh = _onset(a), _onset(h)
        if oa is not None and oh is not None:
            error = abs(oa - oh) * 1000.0
            per_block_on.setdefault(block, []).append(error)
            all_on.append(error)
        da, dh = _duration(a), _duration(h)
        if da is not None and dh is not None:
            error = abs(da - dh) * 1000.0
            per_block_du.setdefault(block, []).append(error)
            all_du.append(error)
    per_block = {
        block: {"onset": _stats(per_block_on.get(block, [])),
               "duration": _stats(per_block_du.get(block, []))}
        for block in sorted(set(per_block_on) | set(per_block_du))}
    return {"per_block": per_block,
            "total": {"onset": _stats(all_on), "duration": _stats(all_du)}}


def compare_paths(auto_path: str | Path,
                    ref_path: str | Path) -> dict[str, Any]:
    """Convenience: load both files and compare (:func:`compare`)."""
    return compare(load_rows(auto_path), load_rows(ref_path))


def format_report(result: dict[str, Any]) -> str:
    """Make a readable per-block table (ms) from :func:`compare`.

    B562: this raised a ``KeyError`` on every call. It asked for
    ``gem``, and :func:`_stats` has written ``avg`` since the rename of
    B299 - so the only thing this function could produce was a
    traceback, and the only caller is a command-line tool that was
    itself broken (B550 found that one: it called ``vergelijk_paden``,
    which was renamed in the same round). Two halves of one tool, both
    dead, neither noticed, because nothing ran it. It has a test now.
    """
    # B562: the separators of the header sat one column to the left of
    # the ones in the rows - the value is eight wide and "ms" makes ten
    # in a column of eleven. Nobody had seen it, because this function
    # raised before it could print anything.
    header = t("eval_report_header")
    rule = "-----+----+------------+------------+---------"
    lines = [header, rule]
    for block, measures in result["per_block"].items():
        on, du = measures["onset"], measures["duration"]
        lines.append(f"{block:>4} | {on['n']:>2} | "
                      f"{on['avg']:>8.0f}ms | {on['max']:>8.0f}ms | "
                      f"{du['avg']:>6.0f}ms")
    tot = result["total"]["onset"]
    lines.append(rule)
    lines.append(t("eval_report_total").format(
        avg=f"{tot['avg']:.0f}", med=f"{tot['med']:.0f}",
        max=f"{tot['max']:.0f}", n=tot["n"]))
    return "\n".join(lines)
