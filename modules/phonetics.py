"""Phonetic segmentation for more natural karaoke timing (B241).

Language-independent engine: it only knows *segments* (a vowel group, a
consonant cluster or a single loose letter) and divides the word duration
based on weights. The language knowledge (vowel groups/clusters per language)
lives in ``LANGUAGES``; a new language = one extra entry there, without
changing the engine.

Philosophy: when singing it is mainly the vowels that are held and consonants
are short transitions. By computing per segment (not per letter) and giving
vowels more weight, the result matches the singing much better — without audio
analysis. ("boom" -> b/oo/m, "school" -> sch/oo/l, "through" -> thr/ough.)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Sonorants ring on longer than ordinary consonants.
SONORANTS = frozenset("mnlr")
_VOWEL_CHARS = "aeiouyàâäáéèêëíïîóôöúùûüïœæ"

#: Per language: vowel groups and consonant clusters (longest matched first).
#: New language? Add an entry here; the engine stays unchanged.
LANGUAGES: dict[str, dict[str, list[str]]] = {
    "nl": {
        "vowels": ["aai", "ooi", "oei", "eeu", "ieu",
                   "aa", "ee", "oo", "uu", "ie", "oe", "ou", "au", "ei",
                   "ij", "ui", "eu", "ai", "oi",
                   "a", "e", "i", "o", "u", "y"],
        "clusters": ["sch", "ng", "nk", "ch", "sj", "tj", "dr", "tr", "st",
                     "sp", "sl", "sk", "sm", "sn", "pl", "pr", "br", "bl",
                     "gr", "gl", "kr", "kl", "fr", "fl", "vl", "vr", "kn",
                     "zw", "tw", "dw", "th"],
        "hallucinations": ["zang", "tv", "gelderland"],
        "fillers": ["en", "de", "het", "een", "van", "in", "op"],
    },
    "en": {
        "vowels": ["eau", "iou", "ough", "augh", "eigh",
                   "ai", "ay", "ea", "ee", "ei", "ie", "oa", "oo", "ou",
                   "ow", "oi", "oy", "au", "aw", "ew", "ue", "ui", "igh",
                   "a", "e", "i", "o", "u", "y"],
        "clusters": ["sch", "scr", "shr", "spl", "spr", "str", "thr", "chr",
                     "tch", "dge", "ck", "ch", "sh", "th", "ph", "wh", "ng",
                     "nk", "qu", "gh", "st", "sp", "sk", "sl", "sm", "sn",
                     "pl", "pr", "br", "bl", "gr", "gl", "cr", "cl", "fr",
                     "fl", "dr", "tr", "kn", "wr"],
        # Whisper's standard end-of-audio artefacts in English. "thank"
        # is enough for "Thank you.": "you" is a filler here, so it does
        # not count as a core word (B337). "amen" is one of the same
        # family - measured at 0.11 s with confidence 0.032, in a segment
        # of its own, two seconds after the singing had stopped. Safe to
        # ship because the check looks at the POSITION in the lyrics: a
        # song that really does sing amen there keeps it (B337).
        "hallucinations": ["thank", "thanks", "watching", "subscribe",
                           "subtitles", "subtitled", "captions", "amen"],
        "fillers": ["the", "a", "an", "and", "of", "to", "for", "you",
                    "it", "is", "in", "on"],
    },
    "fr": {
        # French (e.g. 'Formidable'): many vowel digraphs and nasals. The
        # accents are handled separately; here the bare vowel groups.
        "vowels": ["eau", "eaux", "aient",
                   "ai", "au", "ou", "oi", "eu", "ei", "ai", "oe", "ue",
                   "ui", "ie", "ay", "ey", "oy", "an", "en", "in", "on",
                   "un", "am", "em", "im", "om",
                   "a", "e", "i", "o", "u", "y", "é", "è", "ê", "ë", "à",
                   "â", "î", "ï", "ô", "û", "ù", "ü", "œ", "æ"],
        "clusters": ["sch", "tch", "gn", "ch", "ph", "th", "qu", "ll", "ss",
                     "st", "sp", "sc", "pl", "pr", "br", "bl", "gr", "gl",
                     "cr", "cl", "fr", "fl", "dr", "tr", "vr", "cr"],
        # "C'est parti !" stood at the end of one song without being
        # sung there; ``normalize_for_filter`` strips the apostrophe.
        "hallucinations": ["merci", "cest", "parti", "soustitrage",
                           "soustitres"],
        "fillers": ["le", "la", "les", "de", "des", "du", "et", "un",
                    "une", "a"],
    },
}
_DEFAULT_LANG = "nl"

# --- Languages 'on-the-go' (B241) -----------------------------------------
# Besides the built-in languages above, the tool can lay down missing
# languages itself: detected from the lyrics (e.g. French for 'Formidable').
# Such a language is (1) placed in the project diagnostics with a clear
# header/version so the whole folder can be sent in, and (2) - if there is a
# writable collection folder - stored there for direct reuse in subsequent
# builds. Everything that has been collected is loaded before every build;
# newly generated languages carry the current build version.

#: Runtime cache of loaded/generated languages on top of the built-in set.
_EXTRA_LANGUAGES: dict[str, dict[str, list[str]]] = {}

#: Seed data to serve an unknown language reasonably anyway: a neutral,
#: broadly applicable set of vowel groups and clusters (Latin script). Better
#: than falling back on the Dutch model for a foreign language.
_GENERIC_SEED: dict[str, list[str]] = {
    "vowels": ["eau", "aai", "ooi",
               "ai", "au", "ou", "oi", "eu", "ei", "ie", "oo", "ee", "aa",
               "ea", "oa", "ue", "ui", "ay", "ey", "oy",
               "a", "e", "i", "o", "u", "y",
               "á", "é", "í", "ó", "ú", "à", "è", "ì", "ò", "ù",
               "â", "ê", "î", "ô", "û", "ä", "ë", "ï", "ö", "ü", "ñ", "ç"],
    "clusters": ["sch", "str", "chr", "gn", "ch", "sh", "th", "ph", "qu",
                 "ng", "nk", "ll", "ss", "st", "sp", "sc", "sk", "sl", "sm",
                 "sn", "pl", "pr", "br", "bl", "gr", "gl", "cr", "cl", "fr",
                 "fl", "dr", "tr", "vr", "kn", "wr"],
}


# B293: ``_lang_dir_name()`` used to be here; it only returned the fixed
# string "languages" and was never called anywhere; the folder name comes from
# ``filesystem.talen_dir``.


def generate_language(code: str) -> dict[str, list[str]]:
    """Build a language registry 'on-the-go' for an unknown code (B241).

    Supplies the generic seed data, so that a foreign language does not
    fall back on the Dutch model. Purely data-driven; the phonetics engine
    stays unchanged.

    ``code`` is not used at this moment: there are (as yet) no built-in
    hints per language, so every unknown language gets the same seed data.
    The parameter stays because the callers already pass it and
    language-specific hints would logically end up here. The docstring
    previously claimed that those hints already existed (B293).
    """
    seed = {"vowels": list(_GENERIC_SEED["vowels"]),
            "clusters": list(_GENERIC_SEED["clusters"]),
            # B337: deliberately EMPTY. Which words Whisper invents at
            # the end of a song differs per language, and guessing is
            # worse than not knowing. The lists travel with the language
            # file, so a Danish song gets its own ``da.json`` that the
            # user fills in himself - and nothing lands in the set that
            # is shipped.
            "hallucinations": [],
            "fillers": []}
    return seed


#: The lists that a language carries besides its phonetics (B337).
#: Every built-in language must have BOTH keys, even if empty - the test
#: enforces that, so a new language cannot be added without someone
#: making a decision about it.
WORD_LISTS = ("hallucinations", "fillers")


def word_list(code: str, kind: str) -> frozenset[str]:
    """The words of one list for a language: shipped PLUS collected.

    Deliberately a union and not "first one wins" like the phonetics
    (:func:`_registry`). For a built-in language a collected file is
    then an ADDITION - which is exactly what a word marked by hand in
    the coupling editor is - instead of being silently ignored.
    """
    code = (code or "").lower()[:2]
    words: set[str] = set()
    for source in (LANGUAGES.get(code), _EXTRA_LANGUAGES.get(code)):
        if source:
            words.update(str(w).lower() for w in (source.get(kind) or ()))
    return frozenset(words)


def add_word(code: str, kind: str, word: str, collection_dir=None,
             app_version: str = "") -> bool:
    """Add a word to a language list and store it (B337).

    Lands in the runtime cache and, if a writable collection folder is
    given, in ``languages/<code>.json`` so that every following project
    in this language benefits. Returns whether something changed.
    """
    code = (code or "").lower()[:2]
    word = (word or "").strip().lower()
    if not code or not word or kind not in WORD_LISTS:
        return False
    if word in word_list(code, kind):
        return False
    entry = _EXTRA_LANGUAGES.setdefault(code, generate_language(code))
    entry.setdefault(kind, [])
    entry[kind].append(word)
    if collection_dir is not None:
        save_language(code, collection_dir, app_version)
    return True


def remove_word(code: str, kind: str, word: str, collection_dir=None,
                app_version: str = "") -> bool:
    """Undo :func:`add_word` for a word added by hand.

    A word from the shipped set cannot be removed this way; that stays
    a code decision.
    """
    code = (code or "").lower()[:2]
    word = (word or "").strip().lower()
    entry = _EXTRA_LANGUAGES.get(code) or {}
    if word not in (entry.get(kind) or ()):
        return False
    entry[kind] = [w for w in entry[kind] if w != word]
    if collection_dir is not None:
        save_language(code, collection_dir, app_version)
    return True


def language_payload(code: str, app_version: str = "") -> dict:
    """Build the language object to store, with clear header/version (B241)."""
    code = (code or "").lower()[:2]
    data = (LANGUAGES.get(code) or _EXTRA_LANGUAGES.get(code)
            or generate_language(code))
    return {
        "_header": "KaraokeTool taalregistry (fonetische timing)",
        "language": code,
        "generated_with_version": app_version,
        "origin": ("builtin" if code in LANGUAGES else "generated"),
        "vowels": list(data["vowels"]),
        "clusters": list(data["clusters"]),
        "hallucinations": list(data.get("hallucinations") or []),
        "fillers": list(data.get("fillers") or []),
    }


def load_language_dir(directory) -> int:
    """Load all language files from a collection folder into the cache.

    File name ``<code>.json``. To be called before every build so that
    previously collected languages are available again. Returns the number
    of languages loaded. A missing folder or unreadable files are silently
    skipped.
    """
    import json
    directory = Path(directory)
    if not directory.is_dir():
        return 0
    n = 0
    for entry in sorted(directory.glob("*.json")):
        try:
            obj = json.loads(entry.read_text(encoding="utf-8"))
            code = str(obj.get("language") or entry.stem).lower()[:2]
            if obj.get("vowels") and obj.get("clusters"):
                _EXTRA_LANGUAGES[code] = {
                    "vowels": list(obj["vowels"]),
                    "clusters": list(obj["clusters"]),
                    "hallucinations": list(obj.get("hallucinations") or []),
                    "fillers": list(obj.get("fillers") or [])}
                n += 1
        except (OSError, ValueError):
            continue
    return n


def save_language(code: str, directory, app_version: str = "") -> "Path | None":
    """Write a language as ``<code>.json`` to a (writable) folder (B241).

    Used for both the project diagnostics and the collection folder. Returns
    the path, or ``None`` if writing fails (folder not writable etc.).
    """
    import json
    code = (code or "").lower()[:2]
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{code}.json"
        target.write_text(
            json.dumps(language_payload(code, app_version),
                       ensure_ascii=False, indent=2),
            encoding="utf-8")
        return target
    except OSError:
        return None


def ensure_language(code: str, diagnostics_dir=None, collection_dir=None,
                    app_version: str = "") -> str:
    """Ensure a language is available; lay it down on-the-go if needed (B241).

    - Unknown language -> generate it and put it in the runtime cache.
    - ``diagnostics_dir`` (if given) -> always drop a copy there with
      header/version, so the whole diagnostics folder can be sent in.
    - ``collection_dir`` (if writable) -> also store it there for direct
      reuse in subsequent builds.

    Returns the language code used (may be the shortened 2-letter code).
    """
    code = (code or "").lower()[:2]
    if not code:
        return _DEFAULT_LANG
    if code not in LANGUAGES and code not in _EXTRA_LANGUAGES:
        _EXTRA_LANGUAGES[code] = generate_language(code)
    if diagnostics_dir is not None:
        save_language(code, diagnostics_dir, app_version)
    if collection_dir is not None:
        save_language(code, collection_dir, app_version)
    return code


@dataclass(frozen=True)
class SegmentConfig:
    """Configurable weights and limits for the segment timing (B241)."""

    weight_consonant: float = 1.0
    weight_sonorant: float = 2.0
    weight_short_vowel: float = 6.0
    weight_long_vowel: float = 8.0
    last_vowel_fraction: float = 0.30
    min_segment_s: float = 0.015


def _registry(language: str) -> tuple[list[str], list[str]]:
    code = (language or "").lower()[:2]
    language_data = (LANGUAGES.get(code) or _EXTRA_LANGUAGES.get(code)
            or LANGUAGES[_DEFAULT_LANG])
    vowels = sorted(language_data["vowels"], key=len, reverse=True)
    clusters = sorted(language_data["clusters"], key=len, reverse=True)
    return vowels, clusters


def _is_vowel_segment(seg: str) -> bool:
    core = "".join(ch for ch in seg.lower() if ch.isalpha())
    return bool(core) and all(ch in _VOWEL_CHARS for ch in core)


def _longest_match(low: str, i: int, opties: list[str]) -> int:
    for optie in opties:
        n = len(optie)
        if n and low[i:i + n] == optie:
            return n
    return 0


def segment_word(word: str, language: str = _DEFAULT_LANG) -> list[str]:
    """Split a word into phonetic segments (vowel groups/clusters).

    Greedy: at each position first the longest known vowel group, then the
    longest cluster, otherwise a single loose letter. Non-letters
    (punctuation) join the previous segment, so the word stays exactly
    reconstructible.
    """
    vowels, clusters = _registry(language)
    low = word.lower()
    out: list[str] = []
    i, n = 0, len(word)
    while i < n:
        if not low[i].isalpha():
            if out:
                out[-1] += word[i]
            else:
                out.append(word[i])
            i += 1
            continue
        m = _longest_match(low, i, vowels) or _longest_match(low, i, clusters)
        m = m or 1
        out.append(word[i:i + m])
        i += m
    return out or [word]


def segment_weight(seg: str, config: SegmentConfig) -> float:
    letters = "".join(ch for ch in seg if ch.isalpha())
    if _is_vowel_segment(seg):
        return (config.weight_long_vowel if len(letters) >= 2
                else config.weight_short_vowel)
    if len(letters) == 1 and letters.lower() in SONORANTS:
        return config.weight_sonorant
    return config.weight_consonant


def _enforce_min(duren: list[float], minimum: float,
                 total: float) -> list[float]:
    if minimum * len(duren) >= total or not duren:
        return [total / len(duren)] * len(duren) if duren else duren
    d = list(duren)
    for _ in range(len(d)):
        tekort = [(i, minimum - v) for i, v in enumerate(d) if v < minimum]
        if not tekort:
            break
        nodig = sum(t for _i, t in tekort)
        gevers = [i for i, v in enumerate(d) if v > minimum]
        overschot = sum(d[i] - minimum for i in gevers) or 1.0
        for i, _t in tekort:
            d[i] = minimum
        for i in gevers:
            d[i] = max(minimum, d[i] - nodig * (d[i] - minimum) / overschot)
    return d


def distribute_word(word: str, start: float, end: float,
                    language: str = _DEFAULT_LANG,
                    config: SegmentConfig | None = None
                    ) -> list[tuple[str, float, float]]:
    """Divide the duration of one word over its phonetic segments (B241).

    The last vowel group first gets a fixed share
    (``laatste_klinker_fractie``); the rest goes by weight. Every segment
    gets at least ``min_segment_s``. The segments reconstruct the word and
    together span exactly ``[start, end]``.
    """
    config = config or SegmentConfig()
    segs = segment_word(word, language)
    duration = max(float(end) - float(start), 0.0)
    n = len(segs)
    if n == 1 or duration <= 0:
        return [(s, round(start, 3), round(end, 3)) for s in segs]
    weight_map = [segment_weight(s, config) for s in segs]
    last_vowel = next((k for k in range(n - 1, -1, -1)
                            if _is_vowel_segment(segs[k])), None)
    reserve = (duration * config.last_vowel_fraction
               if last_vowel is not None
               and 0.0 < config.last_vowel_fraction < 1 else 0.0)
    rest = duration - reserve
    total_weight = sum(weight_map) or 1.0
    duren = [rest * g / total_weight for g in weight_map]
    if last_vowel is not None:
        duren[last_vowel] += reserve
    duren = _enforce_min(duren, config.min_segment_s, duration)
    out: list[tuple[str, float, float]] = []
    t = float(start)
    for k, seg in enumerate(segs):
        e = end if k == n - 1 else t + duren[k]
        out.append((seg, round(t, 3), round(e, 3)))
        t = e
    return out
