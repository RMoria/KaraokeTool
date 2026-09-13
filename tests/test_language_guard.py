"""The internal language is English - and now something checks it.

The working agreement has said so since B299/B300, but nothing enforced
it, so it drifted: over a hundred versions the test names became Dutch,
and in one week a whole temporary module plus five test files were added
in Dutch without anyone noticing. Every other agreement in this project
has a test that turns red (no bare ``subprocess``, no literal log texts,
temporary code on the publication list, ``SystemExit`` only in
``main()``). This one did not. That is the difference between a rule and
a habit.

Two guards here, and the second is the one that matters:

* files that are already converted may never regress;
* files still on the TODO list must ACTUALLY still contain Dutch. The
  moment one is cleaned up, this test demands it be struck from the
  list. So the list can only shrink, and it cannot quietly rot into a
  permanent exemption.

As of v0.122.0 the TODO list is empty and the first guard reads more than
``def`` lines: arguments and assigned variables count too. Both of those
followed from finishing the job rather than preceding it - a wide guard
over a wide backlog is a wall of red that gets switched off, and a list
of exemptions with nothing ever struck from it is the same thing more
politely.

Dutch that is deliberate stays out of scope: the ``nl`` texts in
``translations.py``, the documents in ``docs/``, project names and the
song text files. Those are what the user reads.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Dutch stems that give away an identifier. Deliberately a deny-list
#: and not a dictionary: a word list of Dutch would also flag "over",
#: "index" and "single", and a guard with false alarms gets switched off.
DUTCH = re.compile(
    r"^_?(zang|zangstem|draai|dekking|vergelijk|noteer|datum|koppel|"
    r"meetlat|melden|melder|weglaat|grens|dubbel|schrijf|onthoud|beperk|"
    r"kenmerk|mechanisme|volgorde|klim|proef|proeven|zwaar|zware|"
    r"projecten|paden|regel|regels|woord|woorden|tekst|teksten|uitslag|"
    r"uitkomst|bestand|bestanden|drempel|sleutel|lijst|niveau|venster|"
    r"vensters|lettergreep|instelling|verslag|historie|overgeslagen|"
    r"varianten|huidig|ruimer|terugval|nulmeting|opnieuw|gekozen|"
    r"zichtbare|acties|actie|vinkjes|knop)(_|$)", re.I)

#: Files that are known to be still Dutch, with the reason. This list may
#: only ever get shorter. A file that is cleaned up has to disappear from
#: here, and the test below enforces that.
#:
#: It is EMPTY as of v0.122.0, and that is the point: ``modules/`` and
#: ``tools/`` are done. What is left lives in ``tests/`` - the test names
#: themselves plus the docstrings under them, which carry the reasoning
#: for why a test exists and usually the measurement with it. That is the
#: largest stack and it gets its own release, with nothing else in it, so
#: a regression stays visible. Until then it is deliberately out of scope
#: here rather than parked on this list, because an entry that can never
#: be struck is exactly the permanent exemption this guard exists to
#: prevent.
TODO: dict[str, str] = {}


def _dutch_identifiers(path: Path) -> list[str]:
    """Names in this file that look Dutch.

    Functions, classes, arguments AND assigned variables. It started at
    functions and classes only, and v0.122.0 is why it does not stop
    there: with ``modules/`` and ``tools/`` converted, the leftovers were
    all locals and parameters - ``tekst_grp``, ``muziek_keuzes``,
    ``grens``, ``overgeslagen`` - which a guard that only reads ``def``
    lines cannot see. Widening it was only possible once the list was
    short; doing it earlier would have produced hundreds of hits and a
    guard nobody runs.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            if DUTCH.match(node.name):
                found.append(node.name)
        elif isinstance(node, ast.arg) and DUTCH.match(node.arg):
            found.append(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) \
                and DUTCH.match(node.id):
            found.append(node.id)
    return sorted(set(found))


def _sources() -> list[Path]:
    return sorted(p for folder in ("modules", "tools")
                  for p in (ROOT / folder).glob("*.py"))


def test_converted_files_stay_english() -> None:
    """The guard itself: no Dutch identifiers outside the TODO list."""
    offenders = {}
    for path in _sources():
        relative = path.relative_to(ROOT).as_posix()
        if relative in TODO:
            continue
        names = _dutch_identifiers(path)
        if names:
            offenders[relative] = names
    assert not offenders, (
        "Dutch identifiers in already-converted files: "
        + "; ".join(f"{k}: {', '.join(v)}" for k, v in offenders.items()))


def test_the_todo_list_can_only_shrink() -> None:
    """A cleaned-up file has to leave the list.

    Without this the list becomes a permanent exemption and the guard is
    worth nothing: everything troublesome simply gets added to it.
    """
    stale = []
    for relative in TODO:
        path = ROOT / relative
        if not path.exists():
            stale.append(f"{relative} (file is gone)")
        elif not _dutch_identifiers(path):
            stale.append(f"{relative} (is clean - strike it from TODO)")
    assert not stale, "TODO list is out of date: " + "; ".join(stale)


def test_the_command_line_options_are_english() -> None:
    """These are what the user types, so they were the most visible."""
    for name in ("whisper_probe.py", "timing_regression.py"):
        source = (ROOT / "tools" / name).read_text(encoding="utf-8")
        for dutch in ("--gat", "--varianten", "--taal", "--vergelijk",
                      "--noteer", "--datum"):
            assert dutch not in source, f"{name}: {dutch}"


def test_the_probe_variants_are_english() -> None:
    import importlib.util

    path = ROOT / "tools" / "whisper_probe.py"
    spec = importlib.util.spec_from_file_location("probe_lang", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for key in module.VARIANTS:
        assert not DUTCH.match(key), key


def test_the_rule_is_written_down() -> None:
    """A guard without the reasoning beside it gets deleted by the next
    person who finds it annoying."""
    document = (ROOT / "docs" / "doorontwikkeling.md").read_text(
        encoding="utf-8")
    assert "Engels is de interne voertaal" in document
    assert "tests/test_language_guard.py" in document, \
        "the guard has to be named in the working agreement"
