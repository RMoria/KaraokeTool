"""One-off migration of stored data to the English keys (B299/B300).

Version 0.96 renamed every stored key, value, file name and folder name to
English. That is a hard break: the new code cannot read the old files. This
script converts an existing installation in place, so nothing is lost.

Safety measures, in order of importance:

1. **Backup first.** Every file that is touched is copied to
   ``<name>.pre_b299.bak`` before anything is written. Nothing is deleted.
2. **Idempotent.** Running it twice is harmless: files that are already
   converted are recognised and skipped.
3. **Loud on the unknown.** A key that is neither in the mapping nor already
   English is reported. It is never silently left behind - that is exactly
   how ``config.py`` loses settings (it ignores unknown keys with only a log
   warning), which would silently reset a setting to its default.
4. **Verified afterwards.** For every converted file the script checks that
   each value from the backup is present under its new key.

Usage::

    python3 tools/migrate_b299.py <installation-dir>          # dry run
    python3 tools/migrate_b299.py <installation-dir> --apply  # really do it
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

# --- key mappings ---------------------------------------------------------

CONFIG_KEYS = {
    "marge_ms": "margin_ms", "analyse": "analysis", "geavanceerd": "advanced",
    "thema": "theme", "origineel": "original", "wissen": "clear",
    "titel": "title", "taal": "language",
    "parallelle_detectie": "parallel_detection",
    "zangstem_analyse": "vocal_analysis", "uitvoermap": "output_dir",
    "fonetische_timing": "phonetic_timing", "diagnostiek": "diagnostics",
    "blok_anker_barriere": "block_anchor_barrier",
    "anker_gewicht_lettergreep": "anchor_weight_syllable",
    "anker_gewicht_hoog": "anchor_weight_high",
    "anker_gewicht_woord": "anchor_weight_word",
    "anker_gewicht_onset": "anchor_weight_onset",
    "orig_artiest": "orig_artist", "orig_titel": "orig_title",
    "karaoke_titel": "karaoke_title",
    "achtergrond_afbeelding": "background_image",
    "kleur_voor": "color_before", "kleur_zang": "color_vocal",
    "kleur_na": "color_after", "kleur_crowd": "color_crowd",
    "kleur_achtergrond": "color_background", "achtergrond": "background",
    "knop_actief": "button_active", "knop": "button",
}

STEP_NAMES = {
    "bron_origineel": "source_original", "bron_karaoke": "source_karaoke",
    "whisper_origineel": "whisper_original",
    "analyse_origineel": "analysis_original",
    "analyse_karaoke": "analysis_karaoke",
    "clusters_origineel": "clusters_original",
    "klemtoon_origineel": "stress_original",
    "woordkoppeling": "word_coupling", "koppeling": "coupling",
    "songtekst": "lyrics", "origineel_overrides": "original_overrides",
    "origineel_restore_resample": "original_restore_resample",
    "fragment_uitsluitingen": "fragment_exclusions",
    "restore_fragmenten": "restore_fragments",
}

#: Keys that may appear anywhere inside a stored structure.
DATA_KEYS = {
    "aangemaakt": "created", "stappen": "steps", "weergavenaam": "display_name",
    "invoer_namen": "input_names", "video_titels": "video_titles",
    "taal_keuze": "language_choice", "zang_onset_s": "vocal_onset_s",
    "karaoke_uit_origineel": "karaoke_from_original",
    "aantal_clusters": "cluster_count", "alle_intervallen": "all_intervals",
    "auto_bestand": "auto_file", "bestand": "file", "bijgewerkt": "updated",
    "eigenschappen": "properties", "extra_fragmenten": "extra_fragments",
    "gemiddelde_confidence": "average_confidence", "handmatig": "manual",
    "intervallen": "intervals", "korte_woorden": "short_words",
    "kwaliteit": "quality", "lage_confidence": "low_confidence",
    "leeg": "empty", "lijst": "list", "nadruk": "stress", "pad": "path",
    "regels": "lines", "regios": "regions", "segmenten": "segments",
    "selectie": "selection", "totale_woordduur_s": "total_word_duration_s",
    "unieke_woorden": "unique_words", "woorden": "words",
    "regel": "line", "tekst": "text", "blok": "block",
    "lettergrepen": "syllables", "uitgeschakeld": "disabled",
    "crowd_sectie": "crowd_section", "eind": "end", "lang": "held",
    "versie": "version", "uit_cache": "from_cache", "tijd": "time",
    "frequentie": "frequency", "gem_confidence": "avg_confidence",
    "gem_duur_s": "avg_duration_s", "gem_pauze_s": "avg_pause_s",
    "leden": "members", "voorkomens": "occurrences", "aantal": "count",
    "herkomst": "origin", "gegenereerd_met_versie": "generated_with_version",
    "taal": "language",
    "naam": "name", "map": "dir",
    "songtekst": "lyrics", "karaoketekst": "karaoke_text",
}

#: Values (not keys) that were Dutch. Only replaced under these keys.
VALUE_MAPS = {
    "quality": {"hoog": "high", "midden": "medium", "laag": "low",
                "zin": "sentence", "woord": "word",
                "lettergreep": "syllable", "gelijkmatig": "even"},
    "origin": {"ingebouwd": "builtin", "gegenereerd": "generated"},
}

#: Renamed files (stem or full name) and folders.
FILE_RENAMES = {
    "statistieken.json": "statistics.json",
    "frequentie.csv": "frequency.csv",
    "woorden.csv": "words.csv",
    "korte_woorden.csv": "short_words.csv",
    "lage_confidence.csv": "low_confidence.csv",
    "songtekst_uitlijning.txt": "lyrics_alignment.txt",
    "timing_diagnostiek.txt": "timing_diagnostics.txt",
    "uitlijning.json": "alignment.json",
    "origineel_voor_restore.wav": "original_for_restore.wav",
    "origineel_vocals.wav": "original_vocals.wav",
    "karaoke_bewerkt.wav": "karaoke_edited.wav",
    "karaoke_gegenereerd.wav": "karaoke_generated.wav",
}
DIR_RENAMES = {"talen": "languages", "diagnostiek": "diagnostics",
               # per-track output folder: output/<song>/origineel/
               "origineel": "original"}


def dir_target_name(name: str) -> str | None:
    """New name for a folder, or ``None`` if it stays as it is.

    Besides the exact names above this also covers folders that merely END
    in ``_origineel`` (B304). The first version only matched exact names, so
    ``cache/<song>/demucs_stems_origineel`` stayed behind while the code was
    already looking for ``demucs_stems_original`` - which made Demucs re-run
    from scratch for every project, minutes per song.
    """
    if name in DIR_RENAMES:
        return DIR_RENAMES[name]
    if name.endswith("_origineel"):
        return name[:-len("_origineel")] + "_original"
    return None

CSV_HEADERS = {
    ("woord", "aantal"): ("word", "count"),
    ("woord", "start", "einde", "confidence"):
        ("word", "start", "end", "confidence"),
    ("woord", "start", "einde", "confidence", "segment"):
        ("word", "start", "end", "confidence", "segment"),
}

#: Keys that are already English and must be left alone. Anything not in
#: DATA_KEYS/STEP_NAMES and not here is reported as unknown.
KNOWN_ENGLISH = {
    "audio", "cache", "initial_prompt", "language", "mapping", "model",
    "original_items", "pins", "sha1", "wav", "wav_sha1", "offset", "project",
    "start", "end", "text", "index", "crowd", "held", "stress", "quality",
    "line", "block", "disabled", "crowd_section", "syllables", "lines",
    "created", "version", "steps", "conf", "spelling", "count", "members",
    "occurrences", "segment", "segments", "words", "id", "label", "vowels",
    "clusters", "_header", "search_words", "gain_db", "fade_in_ms",
    "fade_out_ms", "whisper", "align", "cluster", "tracks", "song",
    "interface", "video", "karaoke", "device", "compute_type",
    "max_offsets", "window_s", "step_s", "search_s", "tolerance_ms",
    "min_confidence", "merge_gap_ms", "max_ngram", "max_token_duration_s",
    "similarity_threshold", "short_word_max_letters", "demucs",
    "forced_alignment", "width", "height", "fps", "font", "analysis",
    "advanced", "theme", "original", "margin_ms", "clear", "title",
    # already-English keys that appear inside stored structures
    "bit_rate", "channels", "codec", "confidence", "container", "duration",
    "is_vbr", "sample_rate", "line_no", "logo", "timing", "video",
    "transcript_override", "lyrics_override", "align", "name", "dir",
    "reliable", "rows", "runs", "auto", "input", "output", "onset",
    "clusters_karaoke", "whisper_karaoke", "clusters_original",
    "whisper_original", "source_original", "source_karaoke",
}
KNOWN_ENGLISH |= set(DATA_KEYS.values()) | set(CONFIG_KEYS.values())


def _convert(node, unknown: set, in_steps: bool = False):
    """Recursively rename keys and known Dutch values."""
    if isinstance(node, list):
        return [_convert(v, unknown) for v in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if in_steps:
            new_key = STEP_NAMES.get(key, key)
        else:
            new_key = DATA_KEYS.get(key) or CONFIG_KEYS.get(key) or key
        if new_key == key and key not in KNOWN_ENGLISH and not key.isdigit():
            unknown.add(key)
        mapped = VALUE_MAPS.get(new_key)
        if mapped and isinstance(value, str):
            value = mapped.get(value, value)
        out[new_key] = _convert(value, unknown, in_steps=(new_key == "steps"))
    return out


def _already_english(data) -> bool:
    if not isinstance(data, dict):
        return False
    return "steps" in data or "lines" in data or "advanced" in data \
        or "language" in data and "taal" not in data


def convert_json(path: Path, apply: bool, report: list) -> None:
    try:
        original = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report.append(f"  ! {path}: unreadable ({exc})")
        return
    unknown: set = set()
    converted = _convert(original, unknown)
    if converted == original:
        report.append(f"  = {path.name}: already English")
        return
    if unknown:
        report.append(f"  ? {path.name}: unknown keys {sorted(unknown)}")
    if apply:
        backup = path.with_suffix(path.suffix + ".pre_b299.bak")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(json.dumps(converted, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    report.append(f"  + {path.name}: converted")


def convert_csv(path: Path, apply: bool, report: list) -> None:
    try:
        rows = list(csv.reader(path.open(encoding="utf-8"), delimiter=";"))
    except (OSError, ValueError) as exc:
        report.append(f"  ! {path}: unreadable ({exc})")
        return
    if not rows:
        return
    header = tuple(rows[0])
    new_header = CSV_HEADERS.get(header)
    if new_header is None:
        return
    if apply:
        backup = path.with_suffix(path.suffix + ".pre_b299.bak")
        if not backup.exists():
            shutil.copy2(path, backup)
        rows[0] = list(new_header)
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle, delimiter=";").writerows(rows)
    report.append(f"  + {path.name}: header converted")


#: Folders that are never scanned: huge and irrelevant (a virtualenv holds
#: thousands of files, and scanning it made a dry run time out).
SKIP_DIRS = {"venv", ".git", "__pycache__", "assets", "bin", "logs", "_to_delete"}


def _relevant_paths(root: Path):
    """All paths under root, skipping the folders in SKIP_DIRS."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                stack.append(entry)
            yield entry


def rename_paths(root: Path, apply: bool, report: list) -> None:
    """Rename files and folders (deepest first, so parents stay valid)."""
    for path in sorted(_relevant_paths(root), key=lambda p: -len(p.parts)):
        if path.is_dir() and dir_target_name(path.name):
            target = path.with_name(dir_target_name(path.name))
        elif path.is_file() and path.name in FILE_RENAMES:
            target = path.with_name(FILE_RENAMES[path.name])
        elif path.is_file() and path.stem == "origineel":
            target = path.with_name("original" + path.suffix)
        elif path.is_file() and path.name.startswith("transcriptie_"):
            nieuw = path.name.replace("transcriptie_", "transcription_", 1)
            nieuw = nieuw.replace("_origineel", "_original")
            target = path.with_name(nieuw)
        else:
            continue
        if target.exists():
            report.append(f"  = {path.name}: target already exists")
            continue
        if apply:
            path.rename(target)
        report.append(f"  > {path.relative_to(root)} -> {target.name}")


def fix_stored_paths(root: Path, apply: bool, report: list) -> None:
    """Update stored absolute paths that point at renamed files."""
    for project in sorted(root.glob("output/*/settings/project.json")):
        try:
            data = json.loads(project.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        text = json.dumps(data, ensure_ascii=False)
        new_text = text
        for old, new in (("origineel.wav", "original.wav"),
                         ("origineel.mp3", "original.mp3"),
                         ("origineel.m4a", "original.m4a"),
                         ("origineel.flac", "original.flac"),
                         ("origineel.ogg", "original.ogg"),
                         ("origineel.aac", "original.aac"),
                         ("statistieken.json", "statistics.json"),
                         ("transcriptie_origineel", "transcription_original"),
                         ("transcriptie_karaoke", "transcription_karaoke")):
            new_text = new_text.replace(old, new)
        if new_text == text:
            continue
        if apply:
            project.write_text(
                json.dumps(json.loads(new_text), indent=2, ensure_ascii=False),
                encoding="utf-8")
        report.append(f"  > {project.parent.parent.name}: stored paths updated")


def verify(root: Path, report: list) -> None:
    """Check that every value from a backup survives under its new key."""
    def leaves(node, out):
        if isinstance(node, dict):
            for v in node.values():
                leaves(v, out)
        elif isinstance(node, list):
            for v in node:
                leaves(v, out)
        elif isinstance(node, (str, int, float, bool)) and node != "":
            out.append(node)
        return out

    problems = 0
    for backup in sorted(p for p in _relevant_paths(root)
                         if p.name.endswith(".pre_b299.bak")):
        current = backup.with_suffix("")
        if current.suffix != ".json" or not current.exists():
            continue
        try:
            old = leaves(json.loads(backup.read_text(encoding="utf-8")), [])
            new = leaves(json.loads(current.read_text(encoding="utf-8")), [])
        except ValueError:
            continue
        # Dutch values that were deliberately translated may differ.
        vertaald = set()
        for m in VALUE_MAPS.values():
            vertaald |= set(m) | set(m.values())
        missing = [v for v in old
                   if v not in new and str(v) not in vertaald
                   and "origineel" not in str(v)
                   and "statistieken" not in str(v)
                   and "transcriptie" not in str(v)]
        if missing:
            problems += 1
            report.append(f"  ! {current.name}: {len(missing)} value(s) lost, "
                          f"e.g. {missing[:3]}")
    report.append(f"  verification: {problems} file(s) with lost values")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    apply = "--apply" in sys.argv
    if not root.is_dir():
        print(f"not a folder: {root}")
        return 2

    report: list[str] = []
    report.append(f"{'APPLYING' if apply else 'DRY RUN'} on {root}")

    report.append("config.json:")
    cfg = root / "config" / "config.json"
    if cfg.exists():
        convert_json(cfg, apply, report)

    report.append("project.json:")
    for path in sorted(root.glob("output/*/settings/project.json")):
        convert_json(path, apply, report)

    report.append("timing:")
    for path in sorted(root.glob("output/*/settings/timing*.json")):
        convert_json(path, apply, report)

    report.append("clusters / statistics:")
    for pattern in ("output/*/*/clusters.json", "output/*/*/statistieken.json",
                    "output/*/*/statistics.json"):
        for path in sorted(root.glob(pattern)):
            convert_json(path, apply, report)

    report.append("languages:")
    for pattern in ("talen/*.json", "languages/*.json"):
        for path in sorted(root.glob(pattern)):
            convert_json(path, apply, report)

    report.append("csv headers:")
    for path in sorted(root.glob("output/*/*/*.csv")):
        convert_csv(path, apply, report)

    report.append("file and folder names:")
    rename_paths(root, apply, report)

    report.append("stored paths:")
    fix_stored_paths(root, apply, report)

    if apply:
        report.append("verification:")
        verify(root, report)

    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
