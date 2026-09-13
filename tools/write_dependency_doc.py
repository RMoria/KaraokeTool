"""Write ``docs/afhankelijkheden.md`` from the derivation chain (B311).

The document is not maintained by hand. A hand-written map ages the
moment someone adds a step and forgets the document; a generated one
cannot. ``tests/test_v098.py`` checks that the committed file is exactly
what this tool produces, so a change to the chain that is not written
out makes the test go red.

Usage::

    python tools/write_dependency_doc.py          # write
    python tools/write_dependency_doc.py --check  # only compare
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules import dependencies as deps  # noqa: E402

DOC = Path(__file__).resolve().parents[1] / "docs" / "afhankelijkheden.md"

_KIND_NAME = {
    deps.SOURCE: "bron",
    deps.STEP: "stap",
    deps.META: "projectgegeven",
    deps.FILE: "bestand",
}

_INTRO = """\
# Wat werkt waarin door

Alles wat dit gereedschap maakt komt via een keten van tussenstappen uit
vier bronbestanden: het origineel, de karaokeversie, de songtekst en de
karaoketekst. Verandert er iets aan het begin van zo'n keten, dan klopt
bijna alles daarna niet meer.

Dit bestand is de leesbare kant van `modules/dependencies.py`, waar die
keten als gegevens vastligt. **Het wordt gegenereerd** door
`tools/write_dependency_doc.py`; wijzig de keten in de module, niet hier.
Een test vergelijkt dit bestand met wat de generator maakt, en een tweede
test controleert dat elke stap en elk projectgegeven dat de code gebruikt
ook echt in de keten staat. Zo kan er geen afgeleide meer bestaan waarvan
niemand heeft bepaald wanneer hij verouderd is.

## Hoe je het leest

Onder **Van bron naar afgeleide** staat per bronbestand alles wat eruit
volgt: verander je dat bestand, dan vervalt die hele lijst. Onder **Per
artefact** staat het omgekeerde: waar hangt dit ding zelf van af.

Twee koppelingen zijn niet vanzelfsprekend en verklaren veel:

- `karaoketekst.txt` stuurt via de vulwoord-prioriteit ook de
  **woordkoppeling van de songtekst**, en dus de regeltijden. Je
  parodietekst bepaalt mede welke originele woorden gekoppeld worden.
- `songtekst.txt` zit in de cachesleutel van Whisper (als beginprompt).
  De songtekst wijzigen kan dus een volledige hertranscriptie afdwingen.

Wat bewust NIET doorwerkt is net zo belangrijk, want te veel weggooien
kost handwerk. De parodietekst wijzigen raakt de transcriptie en de
handmatige woordkoppelingen niet; een verse karaoke-transcriptie
(restzang) kost geen handwerk aan het origineel; een ander beeldmerk
maakt alleen de video oud. En de gerenderde video zelf wordt nooit
weggegooid - die kost minuten en de gebruiker beslist zelf wanneer hij
opnieuw rendert.
"""


def _rows() -> list[str]:
    lines: list[str] = []
    lines.append("\n## Van bron naar afgeleide\n")
    for name, artefact in deps.ARTEFACTS.items():
        if artefact.kind != deps.SOURCE:
            continue
        steps, metas, files = deps.invalidation_plan([name])
        total = len(steps) + len(metas) + len(files)
        lines.append(f"\n### `{name}` — {artefact.what}\n")
        lines.append(f"Verandert dit, dan vervallen {total} afgeleiden.\n")
        for label, group in (("Stappen", steps),
                             ("Projectgegevens", metas),
                             ("Bestanden", files)):
            if group:
                joined = ", ".join(f"`{item}`" for item in group)
                lines.append(f"- {label}: {joined}")
        if total:
            lines.append("")

    lines.append("\n## Per artefact\n")
    lines.append("| Artefact | Soort | Wat het is | Afgeleid van |")
    lines.append("|---|---|---|---|")
    for name, artefact in deps.ARTEFACTS.items():
        sources = ", ".join(f"`{item}`" for item in artefact.sources)
        if not sources:
            sources = ("*(bron)*" if artefact.kind == deps.SOURCE
                       else "*(geen — blijft altijd geldig)*")
        lines.append(f"| `{name}` | {_KIND_NAME[artefact.kind]} | "
                     f"{artefact.what} | {sources} |")
    return lines


def render() -> str:
    return _INTRO + "\n".join(_rows()) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        current = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
        if current == text:
            print("docs/afhankelijkheden.md is bij de tijd")
            return 0
        print("docs/afhankelijkheden.md loopt achter op de keten; "
              "draai dit gereedschap zonder --check")
        return 1
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(text, encoding="utf-8")
    print(f"geschreven: {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
