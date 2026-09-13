"""Scope-bewust hernoemen van modulenamen (B299, fase 1).

Waarom niet zoek-en-vervang: `analyse` is in deze codebase tegelijk een
module (`from . import analyse`), een config-sectie
(`context.config.analyse.min_confidence`) en een prefix van opgeslagen
stapnamen (`"analysis_original"`). Alleen de eerste mag hernoemd worden.

Deze tool gebruikt de AST om precies te bepalen wat wat is:
- `ast.Name` met id == oude naam  -> een verwijzing naar de module (hernoemen)
- `ast.Attribute` met attr == oude naam -> een attribuut van iets anders
  (bv. `config.analyse`) -> NIET aanraken
- stringliteralen -> NIET aanraken
- import-statements -> apart afgehandeld

Bewerkingen gaan van achter naar voren zodat eerdere posities geldig blijven.
"""
from __future__ import annotations

import ast
import pathlib
import sys


def _line_offsets(source: str) -> list[int]:
    offsets, pos = [0], 0
    for line_number in source.splitlines(keepends=True):
        pos += len(line_number)
        offsets.append(pos)
    return offsets


def bewerkingen_voor(source: str, old: str) -> list[tuple[int, int]]:
    """Geef (start, eind)-byteposities van elke te hernoemen naam."""
    boom = ast.parse(source)
    offsets = _line_offsets(source)
    points: list[tuple[int, int]] = []

    def pos(node, veld_lineno, veld_col, length):
        start = offsets[veld_lineno - 1] + veld_col
        return (start, start + length)

    for node in ast.walk(boom):
        # `from . import songtekst`  /  `from . import songtekst as x`
        if isinstance(node, ast.ImportFrom) and node.module is None:
            for alias in node.names:
                if alias.name == old:
                    # zoek de naam binnen de regel(s) van dit statement
                    startregel = node.lineno - 1
                    eindregel = getattr(node, "end_lineno", node.lineno)
                    block_start = offsets[startregel]
                    block_end = offsets[eindregel]
                    block = source[block_start:block_end]
                    idx = 0
                    while True:
                        idx = block.find(old, idx)
                        if idx < 0:
                            break
                        voor = block[idx - 1] if idx else " "
                        na = block[idx + len(old)] if idx + len(old) < len(block) else " "
                        if not (voor.isalnum() or voor == "_") and \
                           not (na.isalnum() or na == "_"):
                            points.append((block_start + idx,
                                           block_start + idx + len(old)))
                            break
                        idx += len(old)
        # `from .songtekst import X`  /  `from modules.songtekst import X`
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if old in parts or any(a.name == old for a in node.names):
                startregel = node.lineno - 1
                block_start = offsets[startregel]
                eindregel = getattr(node, "end_lineno", node.lineno)
                block = source[block_start:offsets[eindregel]]
                idx = block.find(old)
                if idx >= 0:
                    points.append((block_start + idx, block_start + idx + len(old)))
        # `import songtekst`
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == old or alias.name.startswith(old + "."):
                    block_start = offsets[node.lineno - 1]
                    block = source[block_start:offsets[
                        getattr(node, "end_lineno", node.lineno)]]
                    idx = block.find(old)
                    if idx >= 0:
                        points.append((block_start + idx,
                                       block_start + idx + len(old)))
        # gewone verwijzing: songtekst.foo  ->  Name(id='songtekst')
        elif isinstance(node, ast.Name) and node.id == old \
                and isinstance(node.ctx, ast.Load):
            points.append(pos(node, node.lineno, node.col_offset, len(old)))

    return sorted(set(points), reverse=True)


def hernoem_in_bestand(path: pathlib.Path, mapping: dict[str, str]) -> int:
    source = path.read_text(encoding="utf-8")
    original = source
    for old, new in mapping.items():
        if old not in source:
            continue
        try:
            points = bewerkingen_voor(source, old)
        except SyntaxError as exc:
            print(f"  !! syntaxfout in {path}: {exc}")
            return 0
        for start, end in points:
            source = source[:start] + new + source[end:]
    if source != original:
        path.write_text(source, encoding="utf-8")
        return 1
    return 0


def main() -> None:
    wortel = pathlib.Path(sys.argv[1])
    # mapping oud -> nieuw
    MAPPING = {
        "lyrics": "song_text",
        "karaoketekst": "karaoke_text",
        "language": "translations",
        "ritme": "rhythm",
        "analysis": "analysis",
        "scheiding": "separation",
        "fonetiek": "phonetics",
        "modellen": "models",
        "woorduitlijning": "word_alignment",
        "koppeleditor": "coupling_editor",
        "timingeditor": "timing_editor",
        "dempingeditor": "damping_editor",
        "klemtooneditor": "stress_editor",
    }
    changed = 0
    for path in sorted(wortel.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        changed += hernoem_in_bestand(path, MAPPING)
    print(f"bestanden aangepast: {changed}")


if __name__ == "__main__":
    main()
