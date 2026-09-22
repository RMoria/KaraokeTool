"""CLI: compare automatic timing against a reference (B251).

Usage:
    python -m tools.timing_eval <auto.json> <reference.json>

For example, to measure after "step 0" (regenerating on the current
version) how close the automatic timing sits to your manual version:

    python -m tools.timing_eval output/<song>/settings/timing_auto.json \\
                                 output/<song>/settings/timing.json.bak

Prints a per-block table with the average/maximum |onset error| and the
average |duration error| (in ms) plus the totals. Only lines with
exactly the same text count.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure 'modules' is importable, also when called on its own.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import timing_eval  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """B564: through argparse, like the rest of the tools."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Compare automatic timing against a reference (B251).")
    parser.add_argument("auto", metavar="<auto.json>",
                        help="the automatic timing")
    parser.add_argument("reference", metavar="<reference.json>",
                        help="the timing to compare it with")
    arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    auto_path, ref_path = arguments.auto, arguments.reference
    for path in (auto_path, ref_path):
        if not Path(path).exists():
            print(f"File not found: {path}", file=sys.stderr)
            return 1
    result = timing_eval.compare_paths(auto_path, ref_path)
    print(f"auto:      {auto_path}")
    print(f"reference: {ref_path}\n")
    print(timing_eval.format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
