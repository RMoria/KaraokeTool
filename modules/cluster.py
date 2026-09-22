"""Phonetic clustering of recognised sounds.

Whisper does not consistently write down the same sound the same way
("Kedeng kedeng" becomes GEDENGEDENG, KREEG ER EEN or KREGERING). This
module therefore makes the software independent of exact spelling:

1. Consecutive words are merged (with short pauses) into candidate
   sounds (n-grams).
2. Every sound gets a phonetic key, tuned to sung Dutch (g=k, d=t,
   h and r drop out, vowels simplified).
3. Sounds with comparable keys (edit distance, repetition and
   containment) end up in the same cluster.

The user then chooses which clusters are interesting; the rest of the
software works with clusters, not with loose words. Whisper therefore
does not have to be right: the software learns the sound, not the
spelling.
"""

from __future__ import annotations

import functools

import html as html_module
import json
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import ClusterSettings
from .translations import t
from .whisper import Segment

try:  # RapidFuzz speeds up the distance computation; there is a fallback.
    from rapidfuzz.distance import Levenshtein as _RapidLevenshtein
except ImportError:  # pragma: no cover - depends on the installation
    _RapidLevenshtein = None

logger = logging.getLogger(__name__)

_VOWEL_DIGRAPHS: tuple[tuple[str, str], ...] = (
    ("aa", "a"), ("ee", "e"), ("oo", "o"), ("uu", "u"), ("ie", "i"),
    ("oe", "u"), ("eu", "u"), ("ui", "u"), ("ou", "o"), ("au", "o"),
    ("ij", "i"), ("ei", "i"),
)
_CONSONANT_MAP: dict[str, str] = {
    "b": "p", "d": "t", "g": "k", "c": "k", "q": "k",
    "v": "f", "w": "f", "z": "s", "y": "i", "j": "i", "u": "o",
}
_DROPPED = "hr"

#: Known Whisper hallucinations on instrumental passages; sounds with
#: these words are not included in the clustering.
HALLUCINATIONS: frozenset[str] = frozenset({
    "muziek", "ondertiteling", "ondertiteld", "amara", "amaraorg",
    "ondertitels",
})


@dataclass(frozen=True)
class Occurrence:
    """One occurrence of a sound in the original."""

    text: str
    start: float
    end: float
    confidence: float
    segment: int


@dataclass(frozen=True)
class Cluster:
    """A group of phonetically comparable sounds."""

    id: int
    label: str
    members: tuple[tuple[str, int], ...]
    occurrences: tuple[Occurrence, ...]
    segments: tuple[int, ...]
    frequency: int
    avg_confidence: float
    avg_duration_s: float
    avg_pause_s: float


def normalize_for_filter(text: str) -> str:
    """Normalise a word for the hallucination filter."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


#: Digits -> number written out in full, separately in NL and EN (B274). A
#: lyrics word consisting purely of digits (e.g. "500", "1000") got an EMPTY
#: phonetic key without this (``phonetic_key`` keeps only letters), and could
#: therefore never couple to Whisper's transcription - not even if Whisper
#: happened to write digits too, because the comparison always goes via the
#: key. The two language forms are deliberately NOT merged into one key (that
#: lengthens/pollutes the key too much for a good phonetic match) but offered
#: separately via :func:`number_word_forms`, so that the caller
#: (``_align_core``) can compare per language form separately and use the
#: best one. Only non-negative whole numbers up to 999.999.999 (e.g.
#: "10.000.000" does occur in lyrics now and then; "miljard"/"billion" and
#: higher does not); larger/negative/decimal forms return ``()`` (the caller
#: then falls back on the digits themselves, as before - no regression).
_EEN_TWINTIG_NL = ("nul", "een", "twee", "drie", "vier", "vijf", "zes",
                   "zeven", "acht", "negen", "tien", "elf", "twaalf",
                   "dertien", "veertien", "vijftien", "zestien",
                   "zeventien", "achttien", "negentien")
_TIENTALLEN_NL = ("", "", "twintig", "dertig", "veertig", "vijftig",
                  "zestig", "zeventig", "tachtig", "negentig")
_EEN_TWINTIG_EN = ("zero", "one", "two", "three", "four", "five", "six",
                   "seven", "eight", "nine", "ten", "eleven", "twelve",
                   "thirteen", "fourteen", "fifteen", "sixteen",
                   "seventeen", "eighteen", "nineteen")
_TIENTALLEN_EN = ("", "", "twenty", "thirty", "forty", "fifty", "sixty",
                  "seventy", "eighty", "ninety")


def _honderdtal_nl(n: int) -> str:
    """Number 0-999 written out in Dutch (joined up, as it is sung).

    B412: units FIRST and then the tens, with "en" in between - that is
    how Dutch says it and therefore how it is sung. This used to glue
    them the English way round, so 45 became "veertigvijf" and its
    phonetic key was ``fetikfif`` where the sung "vijfenveertig" gives
    ``fifenfetik``. A key that can never match anything is worse than no
    key at all, because it looks like the number is taken into account.
    Written without a trema ("tweeenveertig"): this string exists to be
    turned into a phonetic key, not to be shown to anybody.
    """
    if n < 20:
        return _EEN_TWINTIG_NL[n]
    if n < 100:
        tien, een = divmod(n, 10)
        if not een:
            return _TIENTALLEN_NL[tien]
        return _EEN_TWINTIG_NL[een] + "en" + _TIENTALLEN_NL[tien]
    honderd, rest = divmod(n, 100)
    word = (_EEN_TWINTIG_NL[honderd] if honderd > 1 else "") + "honderd"
    return word + (_honderdtal_nl(rest) if rest else "")


def _honderdtal_en(n: int) -> str:
    """Number 0-999 written out in English (loose, ``and`` skipped)."""
    if n < 20:
        return _EEN_TWINTIG_EN[n]
    if n < 100:
        tien, een = divmod(n, 10)
        word = _TIENTALLEN_EN[tien]
        return f"{word} {_EEN_TWINTIG_EN[een]}" if een else word
    honderd, rest = divmod(n, 100)
    word = f"{_EEN_TWINTIG_EN[honderd]} hundred"
    return f"{word} {_honderdtal_en(rest)}" if rest else word


def number_word_forms(n: int) -> tuple[str, ...]:
    """Convert a non-negative whole number to written-out forms (B274).

    Returns the Dutch and English written-out form as SEPARATE strings
    (each written joined up as it is sung, no space between the
    million/thousand/hundred parts in Dutch). Supports 0 up to and
    including 999.999.999 (millions + thousands + hundreds - "miljard"/
    "billion" and higher hardly ever occurs in lyrics); larger numbers
    return ``()`` (the caller then falls back on the digits
    themselves).
    """
    if n < 0 or n > 999_999_999:
        return ()
    if n == 0:
        return ("nul", "zero")
    miljoen, rest_m = divmod(n, 1_000_000)
    duizend, rest = divmod(rest_m, 1000)
    nl_parts = []
    en_parts = []
    if miljoen:
        nl_parts.append((_honderdtal_nl(miljoen) if miljoen > 1 else "")
                        + "miljoen")
        en_parts.append(f"{_honderdtal_en(miljoen)} million")
    if duizend:
        nl_parts.append((_honderdtal_nl(duizend) if duizend > 1 else "")
                        + "duizend")
        en_parts.append(f"{_honderdtal_en(duizend)} thousand")
    if rest or not (miljoen or duizend):
        nl_parts.append(_honderdtal_nl(rest))
        en_parts.append(_honderdtal_en(rest))
    return ("".join(nl_parts), " ".join(en_parts))


def phonetic_key(text: str) -> str:
    """Determine the phonetic key of a sound (Dutch, sung).

    Spaces and punctuation drop out; voiced/voiceless are taken
    together (g=k, d=t, ...); ``h`` and ``r`` drop out (they are often
    not recognised in singing); double vowels and sounds like ``oe``,
    ``oh`` and ``ooh`` are simplified; repeated letters are folded
    together.

    Examples: ``kedeng -> ketenk``, ``gedengedeng -> ketenketenk``,
    ``oe/oeh/ooh/oh -> o``.

    If ``text`` consists entirely of digits (e.g. "500"), the Dutch
    written-out form is used instead of the digits themselves (B274)
    - otherwise this function keeps only letters and an empty (thus
    never matching) key remains. For the full NL+EN comparison (e.g. if
    Whisper transcribed it in English) see
    :func:`number_key_best_match`.
    """
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits and digits == "".join(ch for ch in text if ch.isalnum()):
        shapes = number_word_forms(int(digits))
        if shapes:
            text = shapes[0]
    letters = "".join(ch for ch in text.lower() if ch.isalpha())
    letters = letters.replace("sch", "sk").replace("ch", "k")
    for old, new in _VOWEL_DIGRAPHS:
        letters = letters.replace(old, new)

    result: list[str] = []
    for ch in letters:
        if ch in _DROPPED:
            continue
        if ch == "x":
            ch = "ks"
        else:
            ch = _CONSONANT_MAP.get(ch, ch)
        if not result or result[-1] != ch[-1] or len(ch) > 1:
            result.append(ch)
    return "".join(result)


def similarity(key_a: str, key_b: str) -> float:
    """Determine the similarity between two phonetic keys (0..1).

    Rules: equal keys are 1.0; keys that are equal after folding away
    repetitions are 0.95; with containment (``koffie`` in
    ``koffiethee``) the length ratio counts, so that short everyday
    words do not keep sticking to every longer word; otherwise
    normalised Levenshtein similarity.
    """
    if not key_a or not key_b:
        return 0.0
    if key_a == key_b:
        return 1.0
    folded_a, folded_b = _fold_repeats(key_a), _fold_repeats(key_b)
    if folded_a == folded_b:
        return 0.95
    short, long = sorted((folded_a, folded_b), key=len)
    if len(short) >= 3 and short in long:
        return len(short) / len(long)
    distance = _levenshtein(folded_a, folded_b)
    return 1.0 - distance / max(len(folded_a), len(folded_b))


def is_pure_number(text: str) -> bool:
    """Does ``text`` consist purely of digits (e.g. "500", "1.000")? (B274)"""
    digits = "".join(ch for ch in text if ch.isdigit())
    return bool(digits) and digits == "".join(ch for ch in text
                                                if ch.isalnum())


def number_key_best_match(text: str, other_key: str) -> str:
    """Best phonetic key for digit word ``text`` against ``other_key``.

    ``phonetic_key`` always uses the Dutch written-out form for a digit
    word (a tidy default choice for standalone comparisons), but if Whisper
    transcribed the number in English ("five hundred" instead of
    "vijfhonderd") that matches the English form better (B274). This
    function tries both written-out forms against ``other_key`` and gives
    back the key that yields the highest ``similarity`` - that way the
    caller implicitly picks the language that fits best, without the two
    forms ever being merged into one (too long, polluted) key.
    If ``text`` is not a pure digit word, this is simply
    ``phonetic_key(text)``.
    """
    if not is_pure_number(text):
        return phonetic_key(text)
    digits = "".join(ch for ch in text if ch.isdigit())
    shapes = number_word_forms(int(digits))
    if not shapes:
        return phonetic_key(text)
    candidates = [phonetic_key(shape) for shape in shapes]
    return max(candidates, key=lambda k: similarity(k, other_key))


def build_tokens(
    segments: Sequence[Segment],
    settings: ClusterSettings,
) -> list[Occurrence]:
    """Make candidate sounds: words and short word groups (n-grams).

    Words are only combined within one segment, if the pause between
    them is at most ``merge_gap_ms`` and the total duration at most
    ``max_token_duration_s``.
    """
    gap_s = settings.merge_gap_ms / 1000.0
    tokens: list[Occurrence] = []
    for segment in segments:
        words = segment.words
        for start_index in range(len(words)):
            for size in range(1, settings.max_ngram + 1):
                end_index = start_index + size - 1
                if end_index >= len(words):
                    break
                group = words[start_index:end_index + 1]
                if any(group[i + 1].start - group[i].end > gap_s
                       for i in range(len(group) - 1)):
                    break
                if group[-1].end - group[0].start > settings.max_token_duration_s:
                    break
                if any(normalize_for_filter(word.text) in HALLUCINATIONS
                       for word in group):
                    continue
                tokens.append(Occurrence(
                    text=" ".join(word.text for word in group),
                    start=group[0].start,
                    end=group[-1].end,
                    confidence=sum(w.confidence for w in group) / len(group),
                    segment=segment.index,
                ))
    return tokens


def build_clusters(
    segments: Sequence[Segment],
    settings: ClusterSettings,
) -> tuple[Cluster, ...]:
    """Full clustering: make tokens and group them phonetically."""
    return cluster_tokens(build_tokens(segments, settings), settings)


def cluster_tokens(
    tokens: Iterable[Occurrence],
    settings: ClusterSettings,
) -> tuple[Cluster, ...]:
    """Group sounds with comparable phonetic keys.

    Keys are handled by frequency (most frequent first); a key joins
    the best fitting existing cluster if the similarity is at least
    ``similarity_threshold``, otherwise it starts a new cluster.
    Overlapping occurrences within a cluster are deduplicated
    afterwards (shortest unit wins).
    """
    by_key: dict[str, list[Occurrence]] = {}
    for token in tokens:
        key = phonetic_key(token.text)
        if key:
            by_key.setdefault(key, []).append(token)

    ordered_keys = sorted(by_key, key=lambda key: (-len(by_key[key]), key))
    groups: list[dict[str, Any]] = []
    for key in ordered_keys:
        best_group: dict[str, Any] | None = None
        best_score = 0.0
        for group in groups:
            score = _group_similarity(group, key,
                                      settings.similarity_threshold)
            if score > best_score:
                best_group, best_score = group, score
        if best_group is not None and best_score >= settings.similarity_threshold:
            best_group["keys"][key] = len(by_key[key])
            best_group["occurrences"].extend(by_key[key])
        else:
            groups.append({"keys": {key: len(by_key[key])},
                           "occurrences": list(by_key[key])})

    groups = _merge_groups(groups, settings.similarity_threshold)
    clusters = [_finalize(group) for group in groups]
    clusters = [cluster for cluster in clusters if cluster is not None]
    clusters = _suppress_overlaps(clusters)
    clusters.sort(key=lambda cluster: (-cluster.frequency, cluster.label))
    return tuple(
        Cluster(id=index + 1, label=cluster.label, members=cluster.members,
                occurrences=cluster.occurrences, segments=cluster.segments,
                frequency=cluster.frequency,
                avg_confidence=cluster.avg_confidence,
                avg_duration_s=cluster.avg_duration_s, avg_pause_s=cluster.avg_pause_s)
        for index, cluster in enumerate(clusters)
    )


def suggest_clusters(
    clusters: Sequence[Cluster],
    search_words: Sequence[str],
    threshold: float,
) -> list[int]:
    """Suggest clusters that phonetically fit the search words."""
    suggested: list[int] = []
    keys = [phonetic_key(word) for word in search_words]
    for cluster in clusters:
        member_keys = {phonetic_key(member) for member, _ in cluster.members}
        if any(similarity(key, member_key) >= threshold
               for key in keys for member_key in member_keys if key):
            suggested.append(cluster.id)
    return suggested


def format_overview(clusters: Sequence[Cluster], max_members: int = 6,
                    max_clusters: int = 15) -> str:
    """Make a readable overview of the clusters (console and GUI)."""
    lines: list[str] = []
    for cluster in clusters[:max_clusters]:
        lines.append(f"Cluster {cluster.id}")
        for member, count in cluster.members[:max_members]:
            lines.append(f"  {member.upper()}  ({count}x)")
        if len(cluster.members) > max_members:
            lines.append(f"  ... en {len(cluster.members) - max_members} andere spellingen")
        lines.append(f"  gevonden: {cluster.frequency} keer, "
                     f"confidence {cluster.avg_confidence:.2f}, "
                     f"duur {cluster.avg_duration_s:.2f} s, "
                     f"pauze {cluster.avg_pause_s:.1f} s")
        lines.append("-" * 40)
    if len(clusters) > max_clusters:
        lines.append(f"... en {len(clusters) - max_clusters} kleinere clusters "
                     "(zie clusters.csv)")
    return "\n".join(lines)


def write_outputs(clusters: Sequence[Cluster], segments: Sequence[Segment],
                  output_dir: Path) -> tuple[Path, Path]:
    """Write ``clusters.json`` (data) and ``clusters.html`` (report).

    The HTML report can be opened in a browser and shows per cluster:
    name, variants, frequency, confidence, average duration and pause,
    all timestamps, segment numbers and a sample text. Clusters can be
    ticked; the resulting selection (e.g. ``1,3``) can be entered in
    menu step 2.

    Returns:
        Tuple of (path clusters.json, path clusters.html).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "clusters.json"
    json_path.write_text(
        json.dumps(clusters_to_dicts(clusters), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    html_path = output_dir / "clusters.html"
    html_path.write_text(_render_html(clusters, segments), encoding="utf-8")
    logger.info(t("log_cluster_written"),
                json_path.name, html_path.name, len(clusters))
    return json_path, html_path


def format_time(seconds: float) -> str:
    """Format seconds as ``m:ss.s``.

    Public since B293: ``gui.py`` had a literally identical private copy.
    The time display now lives in one place, so that the cluster report
    and the windows in the interface cannot drift apart.
    """
    minutes = int(seconds // 60)
    return f"{minutes}:{seconds % 60:04.1f}"


def _render_html(clusters: Sequence[Cluster],
                 segments: Sequence[Segment]) -> str:
    """Build the HTML report (standalone file, no server needed)."""
    escape = html_module.escape
    segment_texts = {segment.index: segment.text for segment in segments}
    sections: list[str] = []
    for cluster in clusters:
        variants = "".join(
            f"<li>{escape(member.upper())} <span class=aantal>({count}x)"
            "</span></li>"
            for member, count in cluster.members)
        times = " ".join(f"<span class=tijd>{format_time(occ.start)}</span>"
                         for occ in cluster.occurrences)
        segment_numbers = ", ".join(str(index) for index in cluster.segments)
        example = escape(segment_texts.get(cluster.occurrences[0].segment, ""))
        sections.append(f"""
<section class=cluster>
  <header>
    <label><input type=checkbox class=kies value={cluster.id}>
      <strong>{t("html_cluster").format(id=cluster.id)}</strong> - {escape(cluster.label.upper())}
    </label>
    <span class=freq>{t("html_found_times").format(count=cluster.frequency)}</span>
  </header>
  <dl>
    <dt>{t("html_variants")}</dt><dd><ul>{variants}</ul></dd>
    <dt>{t("html_confidence")}</dt><dd>{cluster.avg_confidence:.2f}</dd>
    <dt>{t("html_avg_duration")}</dt><dd>{cluster.avg_duration_s:.2f} s</dd>
    <dt>{t("html_avg_pause")}</dt><dd>{cluster.avg_pause_s:.1f} s</dd>
    <dt>{t("html_times")}</dt><dd class=tijden>{times}</dd>
    <dt>{t("html_segments")}</dt><dd>{segment_numbers}</dd>
    <dt>{t("html_sample_text")}</dt><dd><em>{example}</em></dd>
  </dl>
</section>""")

    body = "\n".join(sections)
    return f"""<!DOCTYPE html>
<html lang={t("html_lang")}>
<head>
<meta charset=utf-8>
<title>{t("html_title")}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; margin: 2rem auto;
         max-width: 56rem; padding-bottom: 6rem; color: #222; }}
  h1 {{ font-size: 1.4rem; }}
  section.cluster {{ border: 1px solid #ccc; border-radius: 8px;
                     padding: 1rem 1.25rem; margin: 1rem 0; }}
  section.cluster header {{ display: flex; justify-content: space-between;
                            align-items: baseline; }}
  .freq {{ color: #b3261e; font-weight: 600; }}
  dl {{ display: grid; grid-template-columns: 9rem 1fr; gap: .25rem .75rem;
       margin: .75rem 0 0; }}
  dt {{ color: #666; }}
  dd {{ margin: 0; }}
  ul {{ margin: 0; padding-left: 1.1rem; }}
  .aantal {{ color: #888; }}
  .tijden {{ line-height: 1.7; }}
  .tijd {{ background: #eef; border-radius: 4px; padding: 0 .3rem;
          margin-right: .2rem; white-space: nowrap; }}
  footer {{ position: fixed; bottom: 0; left: 0; right: 0; background: #fff;
           border-top: 2px solid #b3261e; padding: .75rem 2rem; }}
  footer input {{ font-size: 1.1rem; width: 12rem; }}
</style>
</head>
<body>
<h1>{t("html_heading")}</h1>
<p>{t("html_intro")}</p>
{body}
<footer>
  {t("html_footer_label")}
  <input id=selectie readonly value="" placeholder="{t("html_nothing_selected")}">
  <button onclick="kopieer()">{t("html_copy")}</button>
</footer>
<script>
  const boxes = document.querySelectorAll('.kies');
  function update() {{
    const ids = [...boxes].filter(b => b.checked).map(b => b.value);
    document.getElementById('selectie').value = ids.join(',');
  }}
  boxes.forEach(b => b.addEventListener('change', update));
  function kopieer() {{
    navigator.clipboard.writeText(document.getElementById('selectie').value);
  }}
</script>
</body>
</html>
"""


def clusters_to_dicts(clusters: Sequence[Cluster]) -> list[dict[str, Any]]:
    """Convert clusters into JSON-serialisable dicts."""
    return [
        {
            "id": cluster.id,
            "label": cluster.label,
            "frequency": cluster.frequency,
            "avg_confidence": cluster.avg_confidence,
            "avg_duration_s": cluster.avg_duration_s,
            "avg_pause_s": cluster.avg_pause_s,
            "segments": list(cluster.segments),
            "members": [{"spelling": member, "count": count}
                      for member, count in cluster.members],
            "occurrences": [
                {"text": occ.text, "start": occ.start, "end": occ.end,
                 "confidence": occ.confidence, "segment": occ.segment}
                for occ in cluster.occurrences
            ],
        }
        for cluster in clusters
    ]


def clusters_from_dicts(data: list[dict[str, Any]]) -> tuple[Cluster, ...]:
    """Rebuild clusters from dicts (the inverse of serialisation)."""
    return tuple(
        Cluster(
            id=int(item["id"]),
            label=str(item["label"]),
            frequency=int(item["frequency"]),
            avg_confidence=float(item["avg_confidence"]),
            avg_duration_s=float(item["avg_duration_s"]),
            avg_pause_s=float(item["avg_pause_s"]),
            segments=tuple(int(s) for s in item.get("segments", ())),
            members=tuple((str(m["spelling"]), int(m["count"]))
                        for m in item["members"]),
            occurrences=tuple(
                Occurrence(text=str(o["text"]), start=float(o["start"]),
                           end=float(o["end"]),
                           confidence=float(o["confidence"]),
                           segment=int(o.get("segment", -1)))
                for o in item["occurrences"]
            ),
        )
        for item in data
    )


def _rep_key(group: dict[str, Any]) -> str:
    """The representative key of a group (most frequent, then longest)."""
    keys: dict[str, int] = group["keys"]
    return max(keys, key=lambda key: (keys[key], len(key)))


def _group_similarity(group: dict[str, Any], key: str,
                      threshold: float) -> float:
    """Similarity of a key with a group (anchored coupling).

    The best similarity with a group member counts, but only if the
    key also resembles the representative key of the group closely
    enough (80% of the threshold). Without that anchor, everyday words
    would melt together into one chain cluster via intermediate steps.
    """
    best = max(similarity(key, member) for member in group["keys"])
    if best < threshold:
        return best
    if similarity(key, _rep_key(group)) < threshold * 0.8:
        return 0.0
    return best


def _suppress_overlaps(clusters: list[Cluster]) -> list[Cluster]:
    """Suppress leftover clusters of sub-tokens.

    Large clusters claim their time slots first; occurrences of
    smaller clusters that fall (almost) entirely within a claimed
    time slot (such as ``ER`` within ``KREEG ER EEN``) drop out.
    Clusters without any remaining occurrences disappear.
    """
    ordered = sorted(clusters, key=lambda cluster: -cluster.frequency)
    claimed: list[tuple[float, float]] = []
    result: list[Cluster] = []
    for cluster in ordered:
        kept = [occ for occ in cluster.occurrences
                if not any(occ.start < end - 0.02 and occ.end > start + 0.02
                           for start, end in claimed)]
        if not kept:
            continue
        claimed.extend((occ.start, occ.end) for occ in kept)
        result.append(_from_occurrences(kept))
    return result


def _merge_groups(groups: list[dict[str, Any]],
                  threshold: float) -> list[dict[str, Any]]:
    """Merge groups that do belong together phonetically after all.

    The first assignment is order-dependent; this follow-up round repairs
    that by adding small groups to larger ones as long as one of their
    keys resembles a key of the other group closely enough AND the
    representative keys lie close to each other (that last part prevents
    chain forming of everyday words).
    """
    for _ in range(5):
        changed = False
        groups.sort(key=lambda group: len(group["occurrences"]))
        remaining: list[dict[str, Any]] = []
        while groups:
            small = groups.pop(0)
            target: dict[str, Any] | None = None
            for other in groups:
                anchored = similarity(_rep_key(small),
                                      _rep_key(other)) >= threshold * 0.8
                if anchored and any(
                        similarity(key_a, key_b) >= threshold
                        for key_a in small["keys"]
                        for key_b in other["keys"]):
                    target = other
                    break
            if target is None:
                remaining.append(small)
            else:
                for key, count in small["keys"].items():
                    target["keys"][key] = target["keys"].get(key, 0) + count
                target["occurrences"].extend(small["occurrences"])
                changed = True
        groups = remaining
        if not changed:
            break
    return groups


def _finalize(group: dict[str, Any]) -> Cluster | None:
    """Deduplicate overlapping occurrences and compute statistics.

    With overlapping candidates (e.g. ``oeh``, ``oe`` and ``oeh oe``)
    the token whose phonetic key best fits the representative key of
    the cluster wins; with an equal score the shortest unit wins.
    """
    keys: dict[str, int] = group["keys"]
    rep_key = max(keys, key=lambda key: (keys[key], len(key)))
    ordered = sorted(
        group["occurrences"],
        key=lambda occ: (occ.start,
                         -similarity(phonetic_key(occ.text), rep_key),
                         occ.end - occ.start),
    )
    kept: list[Occurrence] = []
    last_end = -1.0
    for occ in ordered:
        if occ.start >= last_end - 0.02:
            kept.append(occ)
            last_end = occ.end
    if not kept:
        return None
    return _from_occurrences(kept)


def _from_occurrences(kept: list[Occurrence]) -> Cluster:
    """Build a cluster (id 0) with statistics from occurrences."""
    spelling_counts = Counter(occ.text.strip().upper() for occ in kept)
    members = tuple(spelling_counts.most_common())
    pauses = [kept[i + 1].start - kept[i].end for i in range(len(kept) - 1)]
    return Cluster(
        id=0,
        label=members[0][0],
        members=members,
        occurrences=tuple(kept),
        segments=tuple(sorted({occ.segment for occ in kept})),
        frequency=len(kept),
        avg_confidence=round(sum(o.confidence for o in kept) / len(kept), 4),
        avg_duration_s=round(sum(o.end - o.start for o in kept) / len(kept), 3),
        avg_pause_s=round(sum(pauses) / len(pauses), 2) if pauses else 0.0,
    )


@functools.lru_cache(maxsize=200_000)
def _fold_repeats(key: str) -> str:
    """Fold away repetitions, also with a remainder part.

    ``ketenketen -> keten`` and ``ketenketenk -> keten`` (at least two
    complete repetitions, optionally followed by the beginning of the
    unit).

    B395: cached, and that one decorator is worth more than every other
    speed-up in this project put together. Profiled over one yardstick
    measurement this function is called **636,028 times with 307
    distinct inputs** - the same word folded two thousand times over.
    It is pure (str in, str out, no state), so the cache cannot change
    an answer, and measuring confirms it: identical results on every
    project, down to the hundredth.

    What it does change is the clock. One measurement went from 2.44 s
    to 0.426 s, a factor 5.7, and the coupling is not only the test
    panel - it runs every time the user presses 1.3.

    The size is bounded rather than unlimited: 200,000 entries is far
    above what any song needs (307 for a whole measurement) and keeps a
    long session from growing without end.
    """
    length = len(key)
    for unit_length in range(1, length // 2 + 1):
        unit = key[:unit_length]
        repeats, remainder = divmod(length, unit_length)
        if repeats >= 2 and unit * repeats + unit[:remainder] == key:
            return unit
    return key


def _levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein distance (RapidFuzz if installed)."""
    if _RapidLevenshtein is not None:
        return int(_RapidLevenshtein.distance(a, b))
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + cost))
        previous = current
    return previous[-1]
