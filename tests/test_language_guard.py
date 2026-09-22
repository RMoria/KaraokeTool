"""The internal language is English - and now something checks it.

The working agreement has said so since B299/B300, but nothing enforced
it, so it drifted: over a hundred versions the test names became Dutch,
and in one week a whole temporary module plus five test files were added
in Dutch without anyone noticing. Every other agreement in this project
has a test that turns red (no bare ``subprocess``, no literal log texts,
temporary code on the publication list, ``SystemExit`` only in
``main()``). This one did not. That is the difference between a rule and
a habit.

As of B543 the rule is the whole tree, not two folders: identifiers,
prose (comments, docstrings, documents) and file names. Three guards,
each with its own TODO list, and each list may only ever shrink - a file
that is cleaned up has to disappear from it, and a test enforces that.
The lists were filled once, from what the tree actually contained on the
day the rule widened; nothing may be added to them afterwards.

Deliberate Dutch stays out of scope, because it is content and not the
language of the code: the ``nl`` half of ``translations.py``, the file
``languages/nl.json``, and the markup the user types in his own lyrics
(``[pauze]`` beside ``[pause]``). The data files his projects are built
from were Dutch too, and were waiting on a migration rather than on a
translation, because renaming them rewrites every project on his disk.
B555 did the migration: they are now ``lyrics.txt`` and
``karaoke_text.txt``, with the keys of the same name in
``project.json``. The old words stay in :data:`DUTCH_NAMES`, so the
guard still catches them if they ever come back.

The prose guard is the weakest of the three and says so out loud. It
weighs Dutch function words against English ones, which is a heuristic,
not a fact. A short file can fall the wrong way, so a file with too few
countable words gets no verdict at all.
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
    r"zichtbare|acties|actie|vinkjes|knop|achtergrond|voorvoegsel|"
    r"vooraf|haalt|fout|aantal|waarde|naam|activiteit|bron|"
    r"diagnostiek|keuze|leeg|patronen|punten|verbergen|voor|wortel|"
    r"zoek|klemtoon|"
    # B570: the ones that were still standing in modules/ and tools/
    # when this list was widened. Every stem here cost a rename, so
    # what the list guards is not a rule but a repair.
    r"versie|versies|schoon|gewicht|gewichten|lengte|breedte|hoogte|"
    r"positie|geplaatst|deel|delen|veld|velden|stuk|optie|opties|"
    r"blok|blokje|kop|koppen|nieuw|nieuwe|eind|binnen|plek|vorige|"
    # "cel"/"cellen" are deliberately NOT here: the guard matches
    # a stem at the start OR the end of a piece, and that makes
    # them fire on the English "cell", "cells" and "cancel".
    r"aangemaakt|genoteerd|onbekend|vak|vakken|beschikbaar|"
    r"kandidaat|kandidaten|eigen|behoud|vorm|vormen|verplaatst|reden|"
    r"melding|meldingen)(_|$)", re.I)

#: Words that exist in Dutch and not in English. Function words only:
#: they are what prose is made of, they are too common to avoid, and
#: unlike nouns they do not turn up as identifiers or product names.
DUTCH_WORDS = re.compile(
    r"\b(de|het|een|niet|geen|maar|want|dus|omdat|zodat|terwijl|wordt|"
    r"worden|werd|werden|blijft|blijven|staat|staan|gaat|gaan|heeft|"
    r"hebben|zijn|wij|hij|zij|jij|jou|jouw|nog|ook|wel|toch|daar|hier|"
    r"waar|hoe|wie|met|voor|naar|van|bij|aan|uit|onder|tussen|zonder|"
    r"tegen|door|dat|die|deze|dit|als|dan|ze|je|er|om|te|zo|al|elke|"
    r"elk|alle|meer|minder|eerst|daarna|nu|zelf|weer|altijd|nooit|"
    r"soms|vaak|omhoog|omlaag|erbij|eruit|erin|ervan)\b", re.I)

#: And the other way round. Both lists are needed: a file with neither
#: is a table of numbers, not prose, and gets no verdict.
ENGLISH_WORDS = re.compile(
    r"\b(the|and|of|to|this|that|with|from|for|not|but|because|which|"
    r"when|where|what|how|does|should|must|will|would|there|their|they|"
    r"are|was|were|been|being|have|has|had|its|only|also|each|every|"
    r"both|more|less|first|then|than|into|over|under|between|without|"
    r"against|through|after|before|while|about|again|still|never|"
    r"always|already|enough|instead|rather)\b", re.I)

#: Below this many countable words the weighing gets no verdict. A
#: one-line comment is not evidence of anything, and a guard that fires
#: on it is a guard that gets switched off.
PROSE_FLOOR = 25

#: But a file can be short AND unmistakable, and B550 is the bill for
#: not seeing that: fifteen files sat under the floor with Dutch
#: function words and no English ones at all - ``tests/test_v077.py``
#: had twenty-two against nought - while the README said the whole tree
#: was English and all three lists were empty. The floor was doing the
#: forgiving. So below it a second question is asked: enough Dutch to
#: be no accident, and at least twice as much Dutch as English.
CLEARLY_DUTCH = 3

#: Dutch words that turn up in file names here. A deny-list again, for
#: the same reason as :data:`DUTCH`.
DUTCH_NAMES = re.compile(
    r"(songtekst|karaoketekst|woorduitlijning|woordenboek|taal|talen|"
    r"modellen|afhankelijkheden|handleiding|doorontwikkeling|werkwijze|"
    r"hernoeming|verslag|verslagen|meting|metingen|knipwoorden|"
    r"instelling|instellingen|uitlijning|origineel|leesmij|licentie|"
    r"plaats_fonts_hier|woorden)", re.I)

#: Files that still have Dutch identifiers. ``modules/`` and ``tools/``
#: were emptied off this list at v0.122.0; what stands here now came in
#: with B543, when ``tests/`` entered the rule - helper functions and
#: local variables inside the tests, not the tests themselves.
TODO: dict[str, str] = {
}

#: Files whose prose (comments, docstrings, or the document itself) is
#: still Dutch. Filled once at B543 from what the tree contained; it can
#: only shrink from here. The documents are the heavy end: the log alone
#: is four hundred kilobytes of reasoning that has to be carried over by
#: hand, not by a dictionary.
PROSE_TODO: dict[str, str] = {
}

#: Files whose name is still Dutch. Same rule. Empty as of B543: the
#: twelve that were on it have been renamed, which is why this guard
#: could start life with nothing to forgive.
NAME_TODO: dict[str, str] = {}


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
            if _dutch_name_part(node.name):
                found.append(node.name)
        elif isinstance(node, ast.arg) and _dutch_name_part(node.arg):
            found.append(node.arg)
        elif isinstance(node, ast.alias):
            # B556: an import alias is a name like any other, and this
            # walk did not look at one. `from . import song_text as
            # songtekst_module` stood three times in `pipeline.py`, in
            # the module the rename of B555 is about, and the guard
            # reported that file clean.
            name = node.asname or node.name.rsplit(".", 1)[-1]
            if _dutch_name_part(name):
                found.append(name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) \
                and _dutch_name_part(node.id):
            found.append(node.id)
    return sorted(set(found))


#: The stems of :data:`DUTCH`, on their own, for the check below.
#:
#: B560: this used to cut the pattern on its LAST bracket, which is the
#: one of the trailing ``(_|$)`` - so the final stem came out as
#: ``zoek)(_`` and a stray ``$``, and whichever word stood last in the
#: list was quietly dead. Two people worked around that by keeping a
#: known-dead word in last place instead of fixing it. The group of
#: stems is the FIRST bracket, so that is the one to read.
DUTCH_STEMS = tuple(part for part in
                    DUTCH.pattern.split("(", 1)[1].split(")", 1)[0].split("|")
                    if part)


def _dutch_name_part(name: str) -> str:
    """The Dutch piece of an identifier, wherever in the name it sits.

    B550: :data:`DUTCH` is anchored at the start of the name, which is
    fine for ``woord_index`` and blind to ``test_woorduitlijning`` -
    and every test name starts with ``test_``, so the anchor made the
    identifier guard nearly powerless over the file type that had the
    most Dutch in it. Every piece between the underscores is weighed
    now, and a stem counts when the piece begins OR ends with it,
    because Dutch glues its compounds together and the head of such a
    compound is the LAST part: ``woorduitlijning`` is ``woord`` plus
    ``uitlijning``, and ``kernwoorden`` ends on the very stem that
    gives it away. The first version only looked at the beginning and
    walked past that whole half.
    """
    for part in name.lower().lstrip("_").split("_"):
        for stem in DUTCH_STEMS:
            if part.startswith(stem) or part.endswith(stem):
                return part
    return ""


def _prose(path: Path) -> str:
    """The human-readable text of a file.

    For a document that is the whole thing. For a module it is the
    comments and the docstrings: the code itself is guarded by
    :func:`_dutch_identifiers`, and string literals are excluded on
    purpose - they carry lyrics, markup and the ``nl`` translations,
    which are supposed to be Dutch.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".bat":
        # B550: the same division as for a module. The ``rem`` lines are
        # this project talking to whoever reads the script; the ``echo``
        # lines are the program talking to the user, and his interface
        # is Dutch on purpose - the same reason the manual keeps the
        # Dutch button names.
        return "\n".join(line for line in text.splitlines()
                          if line.strip().lower().startswith(("rem ", "::")))
    if path.suffix != ".py":
        return text
    pieces = re.findall(r"#.*", text)
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc:
                pieces.append(doc)
    return "\n".join(pieces)


def _verdict(text: str) -> str:
    """``"nl"``, ``"en"``, or ``""`` when there is too little to judge."""
    dutch = len(DUTCH_WORDS.findall(text))
    english = len(ENGLISH_WORDS.findall(text))
    if dutch + english >= PROSE_FLOOR:
        return "nl" if dutch > english else "en"
    if dutch >= CLEARLY_DUTCH and dutch > 2 * english:  # B550
        return "nl"
    return ""


def _blocks(path: Path) -> list[str]:
    """The prose of a file, cut into the pieces someone wrote (B550).

    A run of comment lines is one piece, and so is every docstring. The
    file as a whole is not, and that is the point: weighing a whole
    file lets a Dutch docstring hide behind the English around it.
    ``modules/test_history.py`` had forty Dutch function words against
    two hundred and thirty-six English ones - three of its docstrings
    are Dutch from the first word to the last, and the file passed.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".py":
        return [text]
    pieces: list[str] = []
    run: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            run.append(stripped.lstrip("#").strip())
            continue
        if run:
            pieces.append(" ".join(run))
            run = []
    if run:
        pieces.append(" ".join(run))
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            document = ast.get_docstring(node)
            if document:
                pieces.append(document)
    return pieces


def _dutch_blocks(path: Path) -> list[str]:
    """Every piece of this file that is Dutch on its own."""
    found = []
    for piece in _blocks(path):
        dutch = len(DUTCH_WORDS.findall(piece))
        english = len(ENGLISH_WORDS.findall(piece))
        if dutch >= CLEARLY_DUTCH and dutch > 2 * english:
            found.append(" ".join(piece.split())[:60])
    return found


def _dutch_name(path: Path) -> str:
    """The Dutch word in this file's name, or ``""``."""
    found = DUTCH_NAMES.search(path.name)
    return found.group(0) if found else ""


#: Folders that hold the user's own material rather than this program:
#: his recordings and projects, his settings, the measurement work, and
#: the binaries he drops in himself. Deliberately a copy of what the
#: publication tool leaves out, and not an import of it - that tool does
#: not travel to the public repository, so importing it would make this
#: test fail everywhere except on one machine.
OUTSIDE_FOLDERS = {"venv", "__pycache__", ".pytest_cache", ".git", ".idea",
                   ".vscode", "input", "output", "cache", "logs", "config",
                   "bin", "verslagen"}

#: The measurement files and the finished internal work orders. Same
#: reasoning: they belong to one reference collection on one machine and
#: never leave it, so the language of this project does not govern them.
OUTSIDE_FILES = {"testhistorie.json", "modelmatrix.md",
                 "modelcombinaties.md", "metingen.md", "testverslag.md",
                 "knipwoorden.txt", "hernoeming_B299_B300.md",
                 "pakketversies.json", "updates.json"}


def _inside(path: Path) -> bool:
    """Whether this project's language rule governs this file."""
    if path.name in OUTSIDE_FILES:
        return False
    return not any(part in OUTSIDE_FOLDERS
                   for part in path.relative_to(ROOT).parts)


def _sources() -> list[Path]:
    """Every Python file that carries code of this project."""
    return sorted(p for p in [ROOT / "KaraokeTool.py"]
                  + [q for folder in ("modules", "tools", "tests")
                     for q in (ROOT / folder).glob("*.py")]
                  if _inside(p))


def _documents() -> list[Path]:
    """Every document that is meant to be read.

    B550: the ``.txt`` and ``.bat`` files are in here now. They were
    read by nothing, and ``requirements.txt`` - which anyone who
    installs this project reads first - was Dutch from top to bottom
    while the README said the whole tree was English.
    """
    return sorted(p for p in [ROOT / "README.md"]
                  + list((ROOT / "docs").glob("*.md"))
                  + list(ROOT.glob("*.txt")) + list(ROOT.glob("*.bat"))
                  + list((ROOT / "assets" / "fonts").glob("*.txt"))
                  if _inside(p))


def _named() -> list[Path]:
    """Every file whose name this project chooses itself.

    The fonts are excluded: those names come from Google, not from here.
    """
    return sorted(p for p in ROOT.rglob("*")
                  if p.is_file() and _inside(p)
                  and p.suffix.lower() not in {".ttf", ".otf"})


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


def test_the_prose_is_english() -> None:
    """Comments, docstrings and documents, outside PROSE_TODO."""
    offenders = []
    for path in _sources() + _documents():
        relative = path.relative_to(ROOT).as_posix()
        if relative in PROSE_TODO:
            continue
        if _verdict(_prose(path)) == "nl":
            offenders.append(relative)
    assert not offenders, ("Dutch prose in files that should be English: "
                           + ", ".join(offenders))


def test_no_single_block_is_dutch() -> None:
    """Per comment and per docstring, not per file (B550).

    The file-wide weighing is a majority vote, and a majority hides a
    minority: three Dutch docstrings in a file of two hundred English
    ones never showed up. Twenty-one such pieces stood in ten files
    while the README said the tree was English. Judged one by one
    there is nothing for them to hide behind.
    """
    offenders = {}
    for path in _sources() + _documents():
        relative = path.relative_to(ROOT).as_posix()
        if relative in PROSE_TODO:
            continue
        pieces = _dutch_blocks(path)
        if pieces:
            offenders[relative] = pieces
    assert not offenders, (
        "Dutch comments or docstrings: "
        + "; ".join(f"{k} ({len(v)}): {v[0]}" for k, v in offenders.items()))


def test_the_prose_todo_can_only_shrink() -> None:
    """Same rule as the identifier list, for the same reason."""
    stale = []
    for relative in PROSE_TODO:
        path = ROOT / relative
        if not path.exists():
            stale.append(f"{relative} (file is gone)")
        elif _verdict(_prose(path)) != "nl":
            stale.append(f"{relative} (reads as English - strike it)")
    assert not stale, "PROSE_TODO is out of date: " + "; ".join(stale)


def test_the_file_names_are_english() -> None:
    """Names are the most visible Dutch of all: they are in every path."""
    offenders = []
    for path in _named():
        relative = path.relative_to(ROOT).as_posix()
        if relative in NAME_TODO:
            continue
        word = _dutch_name(path)
        if word:
            offenders.append(f"{relative} ({word})")
    assert not offenders, ("Dutch file names: " + ", ".join(offenders))


def test_the_name_todo_can_only_shrink() -> None:
    """Same rule again."""
    stale = []
    for relative in NAME_TODO:
        path = ROOT / relative
        if not path.exists():
            stale.append(f"{relative} (file is gone)")
        elif not _dutch_name(path):
            stale.append(f"{relative} (is clean - strike it)")
    assert not stale, "NAME_TODO is out of date: " + "; ".join(stale)


def test_a_short_file_gets_no_verdict() -> None:
    """The floor under the prose guard, tested rather than trusted.

    Without it a two-line Dutch comment in an otherwise English file
    would turn the suite red, and a guard with false alarms is a guard
    that gets switched off.
    """
    assert _verdict("De regel telt niet mee.") == ""
    assert _verdict("Not enough words here either.") == ""
    assert _verdict("de het een niet geen maar want dus omdat zodat "
                    "terwijl wordt worden werd blijft staat gaat heeft "
                    "zijn nog ook wel toch daar hier waar hoe wie") == "nl"
    assert _verdict("the and of to this that with from for not but "
                    "because which when where what how does should must "
                    "will would there their they are was were been") == "en"


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
    document = (ROOT / "docs" / "development_log.md").read_text(
        encoding="utf-8")
    assert "English is the working language of this project" in document
    assert "tests/test_language_guard.py" in document, \
        "the guard has to be named in the working agreement"
