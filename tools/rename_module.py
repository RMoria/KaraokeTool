"""Scope-aware renaming of module names (B299, phase 1).

Why not search-and-replace: `analyse` is in this codebase at once a
module (`from . import analyse`), a config section
(`context.config.analyse.min_confidence`) and a prefix of stored step
names (`"analysis_original"`). Only the first may be renamed.

This tool uses the AST to work out exactly what is what:
- `ast.Name` with id == old name -> a reference to the module (rename)
- `ast.Attribute` with attr == old name -> an attribute of something
  else (e.g. `config.analyse`) -> DO NOT touch
- string literals -> DO NOT touch
- import statements -> handled separately

Edits run from back to front so that earlier positions stay valid.
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


def edits_for(source: str, old: str) -> list[tuple[int, int]]:
    """Return the (start, end) byte positions of every name to rename."""
    tree = ast.parse(source)
    offsets = _line_offsets(source)
    points: list[tuple[int, int]] = []

    def pos(node, line, col, length):
        start = offsets[line - 1] + col
        return (start, start + length)

    for node in ast.walk(tree):
        # `from . import songtekst`  /  `from . import songtekst as x`
        if isinstance(node, ast.ImportFrom) and node.module is None:
            for alias in node.names:
                if alias.name == old:
                    # find the name inside the line(s) of this statement
                    start_line = node.lineno - 1
                    end_line = getattr(node, "end_lineno", node.lineno)
                    block_start = offsets[start_line]
                    block_end = offsets[end_line]
                    block = source[block_start:block_end]
                    idx = 0
                    while True:
                        idx = block.find(old, idx)
                        if idx < 0:
                            break
                        before = block[idx - 1] if idx else " "
                        after = (block[idx + len(old)]
                                 if idx + len(old) < len(block) else " ")
                        if not (before.isalnum() or before == "_") and \
                           not (after.isalnum() or after == "_"):
                            points.append((block_start + idx,
                                           block_start + idx + len(old)))
                            break
                        idx += len(old)
        # `from .songtekst import X`  /  `from modules.songtekst import X`
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if old in parts or any(a.name == old for a in node.names):
                start_line = node.lineno - 1
                block_start = offsets[start_line]
                end_line = getattr(node, "end_lineno", node.lineno)
                block = source[block_start:offsets[end_line]]
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
        # ordinary reference: songtekst.foo -> Name(id='songtekst')
        elif isinstance(node, ast.Name) and node.id == old \
                and isinstance(node.ctx, ast.Load):
            points.append(pos(node, node.lineno, node.col_offset, len(old)))

    return sorted(set(points), reverse=True)


def rename_in_file(path: pathlib.Path, mapping: dict[str, str]) -> int:
    source = path.read_text(encoding="utf-8")
    original = source
    for old, new in mapping.items():
        if old not in source:
            continue
        try:
            points = edits_for(source, old)
        except SyntaxError as exc:
            print(f"  !! syntax error in {path}: {exc}")
            return 0
        for start, end in points:
            source = source[:start] + new + source[end:]
    if source != original:
        path.write_text(source, encoding="utf-8")
        return 1
    return 0


def main(argv: list[str] | None = None) -> None:
    """B564: through argparse. Without a folder it walked
    ``sys.argv[1]`` straight into an IndexError, and with ``--help`` it
    read that as the folder and rewrote every .py file it found."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Rename the old module names in a tree (B299/B300).")
    parser.add_argument("root", help="folder to walk")
    arguments = parser.parse_args(argv)
    root = pathlib.Path(arguments.root)
    # mapping old -> new
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
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        changed += rename_in_file(path, MAPPING)
    print(f"files changed: {changed}")


if __name__ == "__main__":
    main(sys.argv[1:])
