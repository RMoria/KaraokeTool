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
        ``{"per_block": {blok: {"onset": {...}, "duration": {...}}}, "total":
        {"onset": {...}, "duration": {...}}}`` with per measure
        ``n/gem/med/max``.
    """
    per_blok_on: dict[int, list[float]] = {}
    per_blok_du: dict[int, list[float]] = {}
    alle_on: list[float] = []
    alle_du: list[float] = []
    for a, h in zip(auto_rows, ref_rows):
        if _norm(a.get("text")) != _norm(h.get("text")):
            continue
        block = int(h.get("block", 0))
        oa, oh = _onset(a), _onset(h)
        if oa is not None and oh is not None:
            error = abs(oa - oh) * 1000.0
            per_blok_on.setdefault(block, []).append(error)
            alle_on.append(error)
        da, dh = _duration(a), _duration(h)
        if da is not None and dh is not None:
            error = abs(da - dh) * 1000.0
            per_blok_du.setdefault(block, []).append(error)
            alle_du.append(error)
    per_block = {
        block: {"onset": _stats(per_blok_on.get(block, [])),
               "duration": _stats(per_blok_du.get(block, []))}
        for block in sorted(set(per_blok_on) | set(per_blok_du))}
    return {"per_block": per_block,
            "total": {"onset": _stats(alle_on), "duration": _stats(alle_du)}}


def compare_paths(auto_path: str | Path,
                    ref_path: str | Path) -> dict[str, Any]:
    """Convenience: load both files and compare (:func:`compare`)."""
    return compare(load_rows(auto_path), load_rows(ref_path))


def format_report(result: dict[str, Any]) -> str:
    """Make a readable per-block table (ms) from :func:`compare`."""
    lines = ["blok |  n | onset gem |  onset max | duur gem",
              "-----+----+-----------+------------+---------"]
    for block, maten in result["per_block"].items():
        on, du = maten["onset"], maten["duration"]
        lines.append(f"{block:>4} | {on['n']:>2} | "
                      f"{on['gem']:>8.0f}ms | {on['max']:>8.0f}ms | "
                      f"{du['gem']:>6.0f}ms")
    tot = result["total"]["onset"]
    lines.append("-----+----+-----------+------------+---------")
    lines.append(f"totaal onset: gem {tot['gem']:.0f}ms, "
                  f"med {tot['med']:.0f}ms, max {tot['max']:.0f}ms "
                  f"(n={tot['n']})")
    return "\n".join(lines)
