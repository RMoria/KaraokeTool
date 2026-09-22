"""Write ``docs/dependencies.md`` from the derivation chain (B311).

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

DOC = Path(__file__).resolve().parents[1] / "docs" / "dependencies.md"

_KIND_NAME = {
    deps.SOURCE: "source",
    deps.STEP: "step",
    deps.META: "project value",
    deps.FILE: "file",
}

_INTRO = """\
# What carries through to what

Everything this tool makes comes, through a chain of intermediate steps,
from four source files: the original, the karaoke version, the lyrics and
the karaoke text. If something near the start of such a chain changes,
almost nothing after it is still right.

This file is the readable side of `modules/dependencies.py`, where that
chain is laid down as data. **It is generated** by
`tools/write_dependency_doc.py`; change the chain in the module, not
here. One test compares this file with what the generator makes, and a
second checks that every step and every project value the code uses is
really in the chain. That way no derivative can exist without somebody
having decided when it goes stale.

## How to read it

Under **From source to derivative** each source file is listed with
everything that follows from it: change that file and the whole list
lapses. Under **Per artefact** you get the reverse: what this thing
itself depends on.

Two couplings are not obvious and explain a lot:

- `karaoke_text.txt` also steers the **word coupling of the lyrics**,
  through the filler-word priority, and therefore the line times. Your
  parody text helps decide which original words get coupled.
- `lyrics.txt` sits in the cache key of Whisper (as the initial
  prompt). Changing the lyrics can force a full re-transcription.

What deliberately does NOT carry through matters just as much, because
throwing away too much costs hand work. Changing the parody text leaves
the transcription and the manual word couplings alone; a fresh karaoke
transcription (leftover vocals) costs no hand work on the original; a
different logo only makes the video old. And the rendered video itself
is never thrown away - it costs minutes, and the user decides for
himself when to render again.
"""


def _rows() -> list[str]:
    lines: list[str] = []
    lines.append("\n## From source to derivative\n")
    for name, artefact in deps.ARTEFACTS.items():
        if artefact.kind != deps.SOURCE:
            continue
        steps, metas, files = deps.invalidation_plan([name])
        total = len(steps) + len(metas) + len(files)
        lines.append(f"\n### `{name}` — {artefact.what}\n")
        lines.append(f"Change this and {total} derivatives lapse.\n")
        for label, group in (("Steps", steps),
                             ("Project values", metas),
                             ("Files", files)):
            if group:
                joined = ", ".join(f"`{item}`" for item in group)
                lines.append(f"- {label}: {joined}")
        if total:
            lines.append("")

    lines.append("\n## Per artefact\n")
    lines.append("| Artefact | Kind | What it is | Derived from |")
    lines.append("|---|---|---|---|")
    for name, artefact in deps.ARTEFACTS.items():
        sources = ", ".join(f"`{item}`" for item in artefact.sources)
        if not sources:
            sources = ("*(source)*" if artefact.kind == deps.SOURCE
                       else "*(none — always stays valid)*")
        lines.append(f"| `{name}` | {_KIND_NAME[artefact.kind]} | "
                     f"{artefact.what} | {sources} |")
    return lines


def render() -> str:
    return _INTRO + "\n".join(_rows()) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the document, or only check that it is current.

    B564: through argparse, so ``--help`` prints help instead of
    rewriting the document - which is what it did.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Write docs/dependencies.md from the chain itself.")
    parser.add_argument("--check", action="store_true",
                        help="only report whether it is current")
    arguments = parser.parse_args(argv)
    text = render()
    if arguments.check:
        current = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
        if current == text:
            print("docs/dependencies.md is up to date")
            return 0
        print("docs/dependencies.md lags behind the chain; "
              "run this tool without --check")
        return 1
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(text, encoding="utf-8")
    print(f"written: {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
