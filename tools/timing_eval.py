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
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print(__doc__)
        return 2
    auto_path, ref_path = args
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
