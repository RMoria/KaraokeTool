"""No Dutch outside the translation table (v1.0.11).

The rule is old - everything in the tree is English, and Dutch stands
only where it is content: the ``nl`` translation table, the markup the
user types in his lyrics, the sung words, and the storage names he
chose to keep. It was guarded by :mod:`tests.test_language_guard`, and
that guard works with a deny-list of STEMS, which is exactly as good as
what somebody thought of putting on it. Reading the tree with a word
list at v1.0.11 found what that list had never seen: some sixty Dutch
identifiers (``afwijkingen``, ``controles``, ``verschuiving``,
``_TIENTALLEN_EN``...), nine log lines and six console lines in the
start script - which no guard looked at, because it is not in
``modules/`` - and twenty-five Dutch assertion messages in the tests.

So this file reads the tree with WORDS instead of stems. The list below
is written by hand, on purpose short and limited to words that do not
also exist in English (``door``, ``want``, ``met``, ``map``, ``model``,
``stand``, ``telling`` and ``van`` are all English, and a guard that
fires on English gets switched off). The checks:

* identifiers everywhere, exception names included - no piece of a
  name may be a Dutch word;
* string literals in the program (not in the tests, where sung Dutch
  is test data) - no Dutch word outside ``t(...)`` and the docstrings,
  except the words in :data:`CONTENT`, each with the reason it is
  content and not text;
* a literal handed to ``t()`` has to be a key of the table, because a
  missing key shows itself - that is what makes the exemption above
  safe;
* comments everywhere - no comment of two or more Dutch words, or of
  one in a comment of four words or fewer; quoted words do not count,
  and the comments in :data:`QUOTED` are names spelled as they are;
* what a test says when it fails or skips - assertion messages and
  ``pytest.skip``/``fail``/``xfail`` - is read by a person too;
* the start script logs and prints through the table;
* every allowance is still needed, and is a word of the list.

The allowances are per file and per WORD, so a new Dutch word in a
file that already has content still fails.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Dutch words that are not also English words. See the module text.
DUTCH_WORDS = frozenset((
    "aan", "aangemaakt", "aantal", "aanwijzing", "aanzetten", "achter",
    "actie", "actief", "acties", "actueel", "afgebroken", "afgesloten",
    "afhaken", "afstand", "afwijkend", "afwijkingen", "alle", "alleen",
    "alles", "als", "altijd", "ander", "andere", "antwoord", "automaat",
    "basisduur", "beschikbaar", "bestaand", "bestand", "bestanden",
    "betrokken", "betrouwbaar", "bewaard", "bij", "bijna", "bijzonderheden",
    "blok", "blokje", "blokken", "breedte", "bron", "controle", "controles",
    "daar", "daarna", "deel", "delen", "deze", "dezelfde", "dit", "doelset",
    "draai", "draaien", "drempel", "dubbel", "duizend", "duren", "dus",
    "duur", "een", "eenmalig", "eerder", "eerst", "eerste", "eigen", "eind",
    "einde", "elke", "enkele", "evenredig", "fout", "fouten", "foutief",
    "gaat", "gat", "gaten", "gebruiker", "gebruikt", "gedaan", "gedraaid",
    "geen", "gehoord", "gekoppeld", "gekozen", "gelijk", "gemaakt",
    "gemeten", "gemiddeld", "genoteerd", "geschat", "geschreven", "getal",
    "gevers", "gevonden", "gevuld", "geweest", "gewicht", "gewichten",
    "gewogen", "gezet", "gezien", "grens", "groot", "grootste", "haalt",
    "handmatig", "handmatige", "hebben", "heeft", "herhaling", "herhalingen",
    "herstel", "hersteld", "het", "hier", "hij", "hoeveel", "honderd",
    "hoogte", "hoort", "horen", "huidig", "huidige", "ingang", "ingekort",
    "inzet", "jaar", "kaal", "kan", "kandidaat", "kandidaten", "keer",
    "keuze", "kiezen", "klaar", "kleur", "kleuren", "klik", "knippen",
    "knop", "komen", "koppel", "koppeling", "koppelingen", "kort", "korte",
    "kosten", "kunnen", "laagste", "lange", "langzaam", "laten", "leeg",
    "lege", "lengte", "lettergreep", "lettergrepen", "liedje", "lijn",
    "lijst", "logsleutels", "maar", "maken", "mappen", "markeer", "matig",
    "meer", "meerlettergrepig", "meervoudig", "meetlat", "meldingen",
    "meting", "metingen", "midden", "mij", "mijn", "minuten", "mislukt",
    "modellen", "modelstand", "moet", "moeten", "naam", "naar", "nadruk",
    "nauwelijks", "niet", "niets", "nieuw", "nieuwe", "niveau", "nodig",
    "nog", "nooit", "omdat", "onbekend", "onbekende", "onder",
    "ondertiteling", "ongemoeid", "ongemoeide", "ontbreekt", "ontbreken",
    "ook", "opgeslagen", "opgeteld", "opnieuw", "opruimen", "oude",
    "overgeslagen", "overlappen", "overschot", "paar", "paden", "paren",
    "piek", "plaats", "plek", "positie", "positief", "proef", "proeven",
    "raak", "rechts", "reden", "regel", "regels", "rekentijd", "rij",
    "rijen", "samen", "samengevoegd", "schade", "scheiden", "schoof",
    "schrijven", "seconden", "selectie", "slechter", "sluiten", "snel",
    "sneller", "spreiding", "staan", "staat", "stijl", "stilte", "stuk",
    "stukken", "tegen", "tekort", "tekst", "teksten", "terugval", "tijd",
    "tijden", "tijdens", "tijdstip", "titel", "titels", "toch", "totaal",
    "traag", "trager", "tussen", "twee", "uit", "uitgangspunt", "uitslag",
    "vallen", "vanaf", "veel", "venster", "vensters", "verbeterd",
    "verbeteren", "verplaats", "verplaatst", "verschil", "verschuiving",
    "versie", "versies", "verslag", "verslagen", "vervallen", "vervangen",
    "verwacht", "verwachting", "verwijderd", "verzet", "verzette", "vier",
    "vijf", "voor", "vooraf", "vorige", "vorm", "vormen", "waar", "waarde",
    "waarden", "wat", "weer", "weg", "wel", "welke", "werd", "werkplekken",
    "woord", "woorden", "woordkoppeling", "worden", "wordt", "zangstem",
    "zelfde", "zijn", "zin", "zinnen", "zoals", "zoek", "zoekset", "zonder",
    "zou", "zwak",
))

#: Files that are Dutch by nature: the translation table, and the
#: guards that have to spell the words they look for.
NOT_READ = {"translations.py", "test_language_guard.py",
            "test_dutch_leftovers.py"}

#: Per file, the Dutch words that stand in a string literal and are
#: content or a stored id, not text a person reads.
CONTENT = {
    # Dutch number words and subtitle phrases the hallucination filter
    # and the number reader recognise - vocabulary, not text.
    "modules/cluster.py": {"duizend", "een", "honderd",
                           "ondertiteling", "twee", "vier", "vijf"},
    # Kinds of block and drag modes: ids that the damping list stores.
    "modules/damping_editor.py": {"herstel", "rechts", "verplaats",
                                  "zin"},
    # The markup the user types in his karaoke text: [einde crowd].
    "modules/karaoke_text.py": {"einde"},
    "modules/song_text.py": {"einde", "geschat", "tekst"},
    # Level ids of the model register (printed through model_level_*).
    "modules/model_register.py": {"blok", "koppeling", "venster",
                                  "woord", "zin"},
    "modules/test_panel.py": {"blok", "koppeling", "venster", "woord",
                              "zin",
                              # folder names the user chose to keep
                              "oude", "verslagen"},
    # Dutch stop words, and the stage ids of the diagnostics file,
    # whose header the user chose to keep as it is.
    "modules/phonetics.py": {"een", "het"},
    "modules/pipeline.py": {"een", "het", "inzet", "koppeling",
                            "woorden", "zin", "zinnen"},
    "modules/timing.py": {"bron", "inzet", "koppeling", "kort",
                          "onbekend", "regels", "versie", "woorden",
                          "zinnen"},
    "modules/timing_editor.py": {"rechts", "verplaats"},
    "modules/timing_rules.py": {"duur"},
    # Colour roles of the video settings ("voor", "zang", "na").
    "modules/video.py": {"voor"},
    # Keys of the transcription history, a stored format left alone.
    "modules/whisper.py": {"duur", "rekentijd", "tijdstip", "woorden"},
    # The fingerprint text stored in the measurement history.
    "modules/test_history.py": {"uit"},
    # The owner's own song titles and file names, which the export
    # has to recognise in order to replace them.
    "tools/github_export.py": {"achter", "als", "daar", "einde", "het",
                               "hier", "lange", "metingen", "mij", "niet",
                               "nieuwe", "nog", "verslagen", "zijn"},
    # Old Dutch keys that the migration maps onto English ones -
    # spelled out, so a Dutch word in what it PRINTS still fails.
    "tools/migrate_b299.py": {
        "aangemaakt", "aantal", "actief", "alle", "bestand", "blok",
        "bron", "duur", "eind", "einde", "gewicht", "handmatig", "keuze",
        "kleur", "knop", "koppeling", "korte", "leeg", "lettergreep", "midden",
        "lettergrepen", "lijst", "naam", "nadruk", "regel", "regels",
        "selectie", "tekst", "tijd", "titel", "titels", "uit", "versie",
        "voor", "woord", "woorden", "woordkoppeling", "zangstem", "zin"},
    "tools/rename_module.py": {"modellen"},
    # docs/metingen.md, and the cache folder in the temp directory.
    "tools/timing_regression.py": {"metingen", "meetlat"},
}

#: Per file, comments that are allowed to read Dutch, by a piece of
#: their text: project names and ids spelled as they are.
QUOTED = {
    "modules/test_panel.py": ("Lied_T",),
    "modules/timing.py": ("Lied_T",),
    "tests/test_pipeline.py": ("'Ander'",),
    "tests/test_timing.py": ("Zan-gers voor-aan",),
    "tests/test_v086.py": ("Ik heb de woorden",),
}


def _program() -> list[Path]:
    return sorted(list((ROOT / "modules").glob("*.py"))
                  + list((ROOT / "tools").glob("*.py"))
                  + [ROOT / "KaraokeTool.py"])


def _everything() -> list[Path]:
    return _program() + sorted((ROOT / "tests").glob("*.py"))


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z\u00C0-\u00FF]+", text)]


def _pieces(name: str) -> list[str]:
    return [piece.lower()
            for piece in re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])", name)
            if piece]


def _names(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            yield node.lineno, node.name
        elif isinstance(node, ast.arg):
            yield node.lineno, node.arg
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            yield node.lineno, node.id
        elif isinstance(node, ast.Attribute) \
                and isinstance(node.ctx, ast.Store):
            yield node.lineno, node.attr
        elif isinstance(node, ast.alias):
            yield node.lineno, node.asname or node.name.split(".")[-1]
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.lineno, node.arg
        elif isinstance(node, ast.ExceptHandler) and node.name:
            yield node.lineno, node.name


def _prose_strings(tree: ast.AST) -> set[int]:
    """Docstrings and bare strings: prose, guarded elsewhere."""
    return {id(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)}


def test_no_identifier_is_a_dutch_word() -> None:
    """Every name, in every file - the tests included."""
    found = []
    for path in _everything():
        if path.name in NOT_READ:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, name in _names(tree):
            dutch = [p for p in _pieces(name) if p in DUTCH_WORDS]
            if dutch:
                found.append(f"{_relative(path)}:{line} {name}")
    assert not found, "Dutch in identifiers:\n" + "\n".join(sorted(set(found)))


def test_no_dutch_text_outside_the_translation_table() -> None:
    """What the program writes for a person goes through ``t()``."""
    found = []
    for path in _program():
        if path.name in NOT_READ:
            continue
        allowed = CONTENT.get(_relative(path), set())
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prose = _prose_strings(tree)
        parents = {child: node for node in ast.walk(tree)
                   for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)) or id(node) in prose:
                continue
            parent = parents.get(node)
            if isinstance(parent, ast.Call) \
                    and getattr(parent.func, "id", "") == "t":
                continue
            dutch = {w for w in _words(node.value)
                     if w in DUTCH_WORDS and w not in allowed}
            if dutch:
                found.append(f"{_relative(path)}:{node.lineno} "
                             f"{sorted(dutch)} in {node.value[:50]!r}")
    assert not found, "Dutch text outside t():\n" + "\n".join(found)


def test_no_comment_is_dutch() -> None:
    """Two Dutch words in one comment is a Dutch comment."""
    found = []
    for path in _everything():
        if path.name in NOT_READ:
            continue
        allowed = QUOTED.get(_relative(path), ())
        source = path.read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            if any(piece in token.string for piece in allowed):
                continue
            text = re.sub(r'"[^"]*"|``[^`]*``|`[^`]*`', " ", token.string)
            every = _words(text)
            dutch = [w for w in every if w in DUTCH_WORDS]
            if len(dutch) >= 2 or (dutch and len(every) <= 4):
                found.append(f"{_relative(path)}:{token.start[0]} "
                             f"{token.string.strip()[:60]}")
    assert not found, "Dutch comments:\n" + "\n".join(found)


def _messages(tree: ast.AST):
    """What a failing or skipped test says: assertion messages and the
    text of ``pytest.skip``/``fail``/``xfail``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and node.msg is not None:
            yield node.lineno, node.msg
        elif isinstance(node, ast.Call) \
                and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("skip", "fail", "xfail") \
                and getattr(node.func.value, "id", "") == "pytest":
            for argument in node.args:
                yield node.lineno, argument


def test_no_assertion_message_is_dutch() -> None:
    """The message of a failing test is read by a person too."""
    found = []
    for path in sorted((ROOT / "tests").glob("*.py")):
        if path.name in NOT_READ:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, message in _messages(tree):
            for part in ast.walk(message):
                if isinstance(part, ast.Constant) \
                        and isinstance(part.value, str) \
                        and any(w in DUTCH_WORDS
                                for w in _words(part.value)):
                    found.append(f"{_relative(path)}:{line} "
                                 f"{part.value[:60]!r}")
    assert not found, "Dutch assertion messages:\n" + "\n".join(found)


def test_every_literal_key_is_in_the_table() -> None:
    """``t("some Dutch sentence")`` shows the sentence: a key that is
    not in the table falls back to itself. So a literal handed to
    ``t()`` has to be a key, which is also what keeps it out of the
    check on texts above."""
    from modules.translations import TRANSLATIONS

    missing = []
    for path in _program():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) \
                    and getattr(node.func, "id", "") == "t" \
                    and node.args \
                    and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str) \
                    and node.args[0].value not in TRANSLATIONS["nl"]:
                missing.append(f"{_relative(path)}:{node.lineno} "
                               f"{node.args[0].value[:50]!r}")
    assert not missing, "t() of something that is no key:\n" \
        + "\n".join(missing)


def test_the_start_script_logs_through_the_table() -> None:
    """``KaraokeTool.py`` is not in ``modules/``, so the log guard of
    v0.99.0 never read it - and all fifteen of its lines were Dutch."""
    tree = ast.parse((ROOT / "KaraokeTool.py").read_text(encoding="utf-8"))
    literal = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) \
                and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("debug", "info", "warning", "error",
                                       "exception", "critical") \
                and node.args and isinstance(node.args[0], ast.Constant):
            literal.append(node.lineno)
        if isinstance(node, ast.Call) \
                and getattr(node.func, "id", "") == "print" \
                and any(isinstance(a, (ast.Constant, ast.JoinedStr))
                        for a in node.args):
            literal.append(node.lineno)
    assert not literal, f"literal texts on lines {literal}"


def test_every_allowance_is_still_needed() -> None:
    """An allowance that nothing uses any more is a hole for later."""
    unused = []
    for name, allowed in CONTENT.items():
        unused += [f"{name}: {word} (not a listed word)"
                   for word in sorted(allowed - DUTCH_WORDS)]
        path = ROOT / name
        # The published copy leaves the publication tool itself out.
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prose = _prose_strings(tree)
        present = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) \
                    and isinstance(node.value, str) \
                    and id(node) not in prose:
                present |= set(_words(node.value))
        unused += [f"{name}: {word}" for word in sorted(allowed - present)]
    for name, pieces in QUOTED.items():
        if not (ROOT / name).exists():
            continue
        source = (ROOT / name).read_text(encoding="utf-8")
        unused += [f"{name}: {piece}" for piece in pieces
                   if piece not in source]
    assert not unused, "allowed but not there:\n" + "\n".join(unused)
