"""CLI: vergelijk automatische timing met een referentie (B251).

Gebruik:
    python -m tools.timing_eval <auto.json> <referentie.json>

Bijvoorbeeld, om na "stap 0" (opnieuw genereren op de huidige versie) te meten
hoe dicht de automatische timing bij je handmatige versie zit:

    python -m tools.timing_eval output/<lied>/settings/timing_auto.json \\
                                 output/<lied>/settings/timing.json.bak

Print een per-blok-tabel met de gemiddelde/maximale |onset-fout| en de
gemiddelde |duur-fout| (in ms) plus de totalen. Alleen regels met exact
dezelfde tekst tellen mee.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Zorg dat 'modules' importeerbaar is, ook los aangeroepen.
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
            print(f"Bestand niet gevonden: {path}", file=sys.stderr)
            return 1
    result = timing_eval.vergelijk_paden(auto_path, ref_path)
    print(f"auto:       {auto_path}")
    print(f"referentie: {ref_path}\n")
    print(timing_eval.format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
