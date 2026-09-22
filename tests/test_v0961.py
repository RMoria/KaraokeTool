"""Tests for v0.96.1 (B303/B304).

The English rename (B299) renamed one Python builtin by accident: the Dutch
word "map" (folder) was in the vocabulary as ``map`` -> ``dir``, which
turned ``', '.join(map(str, ...))`` into ``', '.join(dir(str, ...))``. That
crashed the analysis, in a GUI path no test touched.

These tests encode the two lessons: a rename vocabulary may never contain a
Python builtin, and ``dir()`` may never be called like a two-argument
function anywhere in the code.
"""

from __future__ import annotations

import ast
import builtins
import pathlib

MODULES = pathlib.Path(__file__).resolve().parent.parent / "modules"
TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
BUILTINS = set(dir(builtins))


def test_dir_is_never_called_with_two_arguments() -> None:
    """B303: the exact regression. ``dir()`` takes at most one argument, so
    a two-argument call is always a ``map()`` that was renamed by mistake."""
    wrong = []
    for path in sorted(MODULES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "dir" and len(node.args) > 1:
                wrong.append(f"{path.name}:{node.lineno}")
    assert not wrong, f"dir() called with several arguments: {wrong}"


#: B571: ``test_rename_vocabulary_holds_no_python_builtin_as_source``
#: stood here. It read ``tools/b299_dictionary.py``, the word list
#: of the B299 rename, and that file is gone: a later rename wave
#: had run over the data itself (37 of its 285 entries read
#: "english -> the same english"), nothing imported it, and the
#: migration it belonged to finished at v0.96.1. The test already
#: returned without asserting anything when the file was absent,
#: so keeping it would have been a green line that measures
#: nothing. What it guarded - a rename that hits a builtin - is
#: still covered by the two tests around this note.


def test_no_builtin_is_shadowed_and_called_in_the_same_scope() -> None:
    """A wider net: within one function a builtin name may not be both
    assigned and called - then the call hits the local value instead."""
    clashes = []
    for path in sorted(MODULES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in [n for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            assigned, called = set(), set()
            for node in ast.walk(func):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    assigned.add(node.id)
                elif isinstance(node, ast.arg):
                    assigned.add(node.arg)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    called.add(node.func.id)
            both = assigned & called & BUILTINS
            if both:
                clashes.append(f"{path.name}:{func.name} {sorted(both)}")
    assert not clashes, f"builtin shadowed and called: {clashes}"


def test_migration_renames_folders_ending_in_origineel() -> None:
    """B304: the migration only renamed folders called exactly "origineel",
    so ``demucs_stems_origineel`` stayed behind in five projects and Demucs
    re-ran needlessly (minutes per song)."""
    script = TOOLS / "migrate_b299.py"
    if not script.exists():
        return
    namespace: dict = {}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"),
         namespace)
    target = namespace["dir_target_name"]
    assert target("origineel") == "original"
    assert target("demucs_stems_origineel") == "demucs_stems_original"
    assert target("talen") == "languages"
    assert target("diagnostiek") == "diagnostics"
    assert target("output") is None          # untouched
    assert target("original") is None        # already converted
