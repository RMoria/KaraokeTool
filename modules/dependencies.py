"""The derivation chain: what is derived from what (B311).

Everything this tool makes comes, via a chain of intermediate steps, from
four source files: the original audio, the karaoke audio, the lyrics and
the karaoke text. If something at the beginning of such a chain changes,
almost everything after it is no longer valid.

Up to and including v0.97 that knowledge was scattered over three
invalidation functions, each with its own hand-written list of keys.
Every new step had to be added to the right list by hand, and that went
wrong repeatedly: the cluster selection survived new audio (and then
damped at the timestamps of the previous song), the manually marked
fragments kept their absolute times on a timeline that no longer
existed, and the project-wide markers ("karaoke made from the original",
the vocal onset, the fixed language) survived everything because
``clear_step`` by definition does not touch them.

This module holds that knowledge ONCE, as data. Every artefact - a step
in ``project.json``, a project-wide marker, or a file on disk - names the
artefacts it is derived from. Invalidating is then no longer a list to
maintain but a question you ask the graph: what depends, directly or
indirectly, on what changed here?

The accompanying tests guard two things: that the graph has no cycles,
and that every step/meta key occurring anywhere in the code is really
described here. That last one is what keeps this map honest - a new step
that nobody placed in the chain makes the test go red instead of
silently causing stale data years later.

``docs/dependencies.md`` is the readable side of this same map.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from . import karaoke_text, song_text

logger = logging.getLogger(__name__)

#: The two tracks. Deliberately repeated here instead of imported from
#: ``pipeline``: this module may not depend on the pipeline (the pipeline
#: uses it), and these two names are part of the description of the chain
#: itself.
TRACKS = ("original", "karaoke")

#: Kinds of artefact.
SOURCE = "source"      # a file the user provides, or a settings group
STEP = "step"          # an entry under "steps" in project.json
META = "meta"          # a project-wide value at the top level of project.json
FILE = "file"          # a file or folder that the tool writes itself


@dataclass(frozen=True)
class Artefact:
    """One node in the derivation chain."""

    name: str
    kind: str
    #: The artefacts this one is derived from. Empty for a source.
    sources: tuple[str, ...] = ()
    #: Short description, for the documentation and the log.
    what: str = ""
    #: For ``FILE``: gives the paths belonging to this artefact.
    paths: Callable[..., Sequence[Path]] | None = field(
        default=None, compare=False, repr=False)


def _artefacts() -> dict[str, Artefact]:
    """Build the map. One function so the order stays readable."""
    items: list[Artefact] = []

    def add(name: str, kind: str, sources: Iterable[str] = (),
            what: str = "", paths=None) -> None:
        items.append(Artefact(name=name, kind=kind,
                              sources=tuple(sources), what=what,
                              paths=paths))

    # -- the sources -----------------------------------------------------
    add("input:original", SOURCE,
        what="input/origineel.* (the original recording)")
    add("input:karaoke", SOURCE, what="input/karaoke.* (the karaoke version)")
    add("input:lyrics", SOURCE,
        what=f"input/{song_text.LYRICS_FILENAME}")
    add("input:karaoke_text", SOURCE,
        what=f"input/{karaoke_text.FILENAME}")
    add("input:logo", SOURCE,
        what="input/logo.* (the logo shown in the video)")
    add("config:whisper", SOURCE, what="setting: Whisper model and language")
    add("config:forced_alignment", SOURCE,
        what="setting: more precise word times (wav2vec2)")
    add("config:chunked", SOURCE,
        what="setting: transcription in chunks (fills the gaps)")
    add("config:analysis", SOURCE, what="setting: analysis thresholds")
    add("config:cluster", SOURCE, what="setting: cluster thresholds")
    add("config:align", SOURCE, what="setting: alignment")
    add("config:karaoke", SOURCE, what="setting: damping (gain, fades)")
    add("config:timing", SOURCE,
        what="setting: vocal analysis, anchor weights, phonetic "
             "timing")
    add("config:video", SOURCE, what="setting: video (colours, fonts)")
    # B387: this should have stood here since B361. The signature in
    # ``_config_signature`` knew "config:models", this map did not, and
    # ``dependents()`` raises a KeyError on an unknown name. As long as
    # the stored signature did not change nobody noticed; the moment a
    # model was added (B380 in v0.121.0) every existing project reported
    # "config:models changed" and steps 1.1 and 1.3 fell over.
    add("config:models", SOURCE,
        what="setting: which models are switched on")

    # -- fingerprints of the source files --------------------------------
    # These steps exist only to NOTICE that a source file was changed
    # outside the app (B311/G1): they keep the sha1 of what the program
    # saw the previous time.
    add("source_original", STEP, ["input:original"],
        "sha1 + wav path of the prepared original")
    add("source_karaoke", STEP, ["input:karaoke"],
        "sha1 + wav path of the prepared karaoke")
    add("source_lyrics", STEP, ["input:lyrics"],
        f"sha1 of {song_text.LYRICS_FILENAME} as the program knows it")
    add("source_karaoke_text", STEP, ["input:karaoke_text"],
        f"sha1 of {karaoke_text.FILENAME} as the program knows it")
    add("source_logo", STEP, ["input:logo"],
        "sha1 of the logo as the program knows it")
    add("config_signature", STEP, [],
        "the settings in use, per group (to notice a change)")
    add("cache:original_wav", FILE, ["source_original"],
        "cache/original.wav",
        lambda paths: [paths.cache_dir / "original.wav"])
    add("cache:karaoke_wav", FILE, ["source_karaoke"],
        "cache/karaoke.wav",
        lambda paths: [paths.cache_dir / "karaoke.wav"])

    # -- separating the vocals -------------------------------------------
    add("cache:demucs_original", FILE, ["cache:original_wav"],
        "cache/demucs_stems_original/ (vocals + instrumental)",
        lambda paths: [paths.cache_dir / "demucs_stems_original"])
    add("cache:demucs_karaoke", FILE, ["cache:karaoke_wav"],
        "cache/demucs_stems_karaoke/",
        lambda paths: [paths.cache_dir / "demucs_stems_karaoke"])
    add("cache:original_vocals", FILE, ["cache:demucs_original"],
        "cache/original_vocals.wav (vocals for the energy analysis)",
        lambda paths: [paths.cache_dir / "original_vocals.wav"])
    add("cache:karaoke_generated", FILE, ["cache:demucs_original"],
        "cache/karaoke_generated.wav (instrumental from the original)",
        lambda paths: [paths.cache_dir / "karaoke_generated.wav"])
    add("output:demucs_mp3", FILE, ["cache:demucs_original"],
        "output/karaoke_demucs.mp3 and vocal_demucs.mp3",
        lambda paths: [paths.output_dir / "karaoke_demucs.mp3",
                       paths.output_dir / "vocal_demucs.mp3"])
    add("vocal_onset_s", META, ["cache:demucs_original"],
        "where the singing starts (anchor for the first line)")
    add("vocal_end_s", META, ["cache:demucs_original"],
        "where the singing stops (anchor for the tail, B319)")
    add("karaoke_from_original", META, ["input:original", "input:karaoke"],
        "whether the karaoke was made from the original (skips alignment)")

    # -- language ---------------------------------------------------------
    # Deliberately NOT dependent on the karaoke text: the user pins the
    # language by hand precisely because the detection is unsure, and
    # then it is unkind to throw that choice away the moment he changes a
    # line in his parody. The lyrics decide the language of the original,
    # and that is what this choice is about.
    add("language_choice", META, ["input:lyrics"],
        "the language pinned by hand")

    # -- step 1: detect words ---------------------------------------------
    # B316: deliberately NOT dependent on ``lyrics_override``. The lyrics
    # travel to Whisper as the initial prompt, so strictly speaking the
    # transcription is based on them - but the prompt is a hint and the
    # override is a correction to the WORD LIST for the coupling. Cutting
    # one word in the coupling editor thereby threw away a transcription
    # of two and a half minutes of compute, including the manual
    # couplings just made. The prompt is already in the cache key of the
    # transcription, so whoever deliberately runs step 1 again gets the
    # changed lyrics along after all.
    add("whisper_original", STEP,
        ["cache:demucs_original", "cache:original_wav", "input:lyrics",
         "config:whisper", "config:forced_alignment", "config:chunked"],
        "transcription of the original (sha1, model, language, prompt)")
    add("whisper_karaoke", STEP,
        ["cache:karaoke_wav", "config:whisper", "config:forced_alignment",
         "karaoke_from_original"],
        "transcription of the karaoke (leftover vocals)")
    add("cache:transcription_original", FILE, ["whisper_original"],
        "cache/transcription_original.json",
        lambda paths: [paths.cache_dir / "transcription_original.json"])
    add("cache:transcription_karaoke", FILE, ["whisper_karaoke"],
        "cache/transcription_karaoke.json",
        lambda paths: [paths.cache_dir / "transcription_karaoke.json"])

    # -- hand corrections to the text and the transcription --------------
    add("transcript_override", STEP, ["whisper_original"],
        "the cut and merged transcription (hand work)")
    add("lyrics_override", STEP, ["input:lyrics"],
        "the cut and merged lyric words (hand work)")
    add("word_coupling", STEP,
        ["whisper_original", "transcript_override", "lyrics_override",
         "input:lyrics", "config:models"],
        "manual word couplings (lyric word -> detected word)")
    add("original_overrides", STEP, ["input:lyrics", "lyrics_override"],
        "hand-corrected line times of the original")
    add("stress_anchors", STEP,
        ["input:lyrics", "input:karaoke_text", "lyrics_override"],
        "hand-coupled pieces of original <-> karaoke, per line")

    # -- step 2: analysis and clusters -----------------------------------
    for track in TRACKS:
        add(f"analysis_{track}", STEP,
            [f"whisper_{track}", "config:analysis"],
            f"analysis figures for the {track} transcription")
        add(f"output:analysis_{track}", FILE, [f"analysis_{track}"],
            f"output/{track}/statistics.json and the csv reports",
            lambda paths, _t=track: [
                paths.output_dir / _t / "statistics.json",
                paths.output_dir / _t / "frequency.csv",
                paths.output_dir / _t / "short_words.csv",
                paths.output_dir / _t / "low_confidence.csv"])
    add("clusters_original", STEP,
        ["whisper_original", "config:cluster", "input:lyrics",
         "lyrics_override"],
        "the chosen sound clusters of the original")
    add("clusters_karaoke", STEP,
        ["whisper_karaoke", "config:cluster"],
        "the chosen sound clusters of the karaoke (leftover vocals)")
    for track in TRACKS:
        add(f"output:clusters_{track}", FILE, [f"clusters_{track}"],
            f"output/{track}/clusters.json and clusters.html",
            lambda paths, _t=track: [
                paths.output_dir / _t / "clusters.json",
                paths.output_dir / _t / "clusters.html"])
    add("output:lyrics_alignment", FILE,
        ["word_coupling", "input:karaoke_text"],
        "output/original/lyrics_alignment.txt",
        lambda paths: [paths.output_dir / "original"
                       / "lyrics_alignment.txt"])

    # -- step 3: aligning ------------------------------------------------
    add("align", STEP,
        ["cache:original_wav", "cache:karaoke_wav", "config:align",
         "karaoke_from_original"],
        "the offset regions between original and karaoke")
    add("output:alignment_json", FILE, ["align"],
        "output/alignment.json (report)",
        lambda paths: [paths.output_dir / "alignment.json"])

    # -- line coupling and timing ----------------------------------------
    add("coupling", STEP,
        ["word_coupling", "align", "input:lyrics", "input:karaoke_text",
         "lyrics_override", "transcript_override", "original_overrides",
         "config:timing", "config:models"],
        "original lines with times + which karaoke line goes with which")
    add("lyrics", STEP, ["clusters_original", "word_coupling"],
        "how many extra damping fragments come from the lyrics")
    # B330: the line starts are laid on the vocal onsets, so the timing
    # now also hangs directly off the vocal stem itself and not only off
    # the first onset derived from it.
    add("timing", STEP,
        ["coupling", "input:karaoke_text", "vocal_onset_s", "align",
         "cache:original_vocals", "language_choice", "config:timing",
         "config:models"],
        "the line and syllable timing for the video")
    add("output:timing", FILE, ["timing"],
        "output/settings/timing.json and timing_auto.json",
        lambda paths: [paths.timing_file, paths.timing_auto_file])
    add("output:timing_diagnostics", FILE, ["timing"],
        "output/diagnostics/timing_diagnostics.txt",
        lambda paths: [paths.output_dir / "diagnostics"
                       / "timing_diagnostics.txt"])

    # -- step 4: damping -------------------------------------------------
    add("fragment_exclusions", STEP, ["cache:karaoke_wav"],
        "unticked damping fragments (times on the karaoke timeline)")
    add("restore_fragments", STEP, ["cache:karaoke_wav"],
        "'back from the original' fragments (karaoke timeline)")
    # B496: the sentences marked in the timing editor to be fetched back
    # from the original. Deliberately NOT hung on the timing: these are
    # line numbers, and those do not change when the timing shifts. The
    # window is derived from the timing of the moment, the same way the
    # rest of step 4 treats the karaoke - a timing change deliberately
    # does not invalidate the edited karaoke.
    add("restore_lines", STEP, ["cache:karaoke_wav"],
        "lines fetched back from the original (line numbers)")
    # B499: and where such a piece was moved to by hand in 1.4. Hangs on
    # the same thing as the marking itself.
    add("restore_moved", STEP, ["restore_lines"],
        "moved 'back from the original' pieces (per line number)")
    add("original_restore_resample", STEP,
        ["input:original", "cache:karaoke_wav"],
        "sha1 + sample rate of the reused original")
    add("cache:original_for_restore", FILE, ["original_restore_resample"],
        "cache/original_for_restore.wav",
        lambda paths: [paths.cache_dir / "original_for_restore.wav"])
    add("karaoke", STEP,
        ["cache:karaoke_wav", "clusters_original", "clusters_karaoke",
         "fragment_exclusions", "restore_fragments", "restore_lines",
         "restore_moved",
         "align", "config:karaoke"],
        "the edited karaoke (which fragments are damped)")
    add("cache:karaoke_edited", FILE, ["karaoke"],
        "cache/karaoke_edited.wav",
        lambda paths: [paths.cache_dir / "karaoke_edited.wav"])
    add("output:karaoke_edit", FILE, ["karaoke"],
        "output/karaoke_edit.mp3 and karaoke_edit.wav",
        lambda paths: [paths.output_dir / "karaoke_edit.mp3",
                       paths.output_dir / "karaoke_edit.wav"])


    # -- project data that is NOT a derivative ----------------------------
    # These deliberately belong to nothing: they describe the project
    # itself and stay valid however often you replace the content.
    add("display_name", META, [], "the readable project name")
    add("input_names", META, [],
        "where the input files came from (for the file chooser)")
    add("input_last_dir", META, [],
        "the last folder used in this project, whatever the input "
        "(B413)")
    add("video_titles", META, [], "artist/title to show in the video")
    # -- step 5: video ------------------------------------------------------
    # B353: deliberately belongs to nothing. The rendered video is an end
    # product; changing the timing afterwards does not make the file
    # invalid, at most it makes it outdated - and that is the user's
    # call. The mp4 was never thrown away anyway (video is a STEP, not a
    # FILE), but the bookkeeping around it was, so after a restart the
    # app had forgotten that a video existed.
    add("video", STEP, [], "the rendered video (path + audio source used)")

    return {item.name: item for item in items}


#: The chain. Read-only; ``dependents`` and ``invalidation_plan`` are the
#: intended ways in.
ARTEFACTS: dict[str, Artefact] = _artefacts()


def _dependants_index() -> dict[str, tuple[str, ...]]:
    """Per artefact the artefacts that directly derive from it."""
    index: dict[str, list[str]] = {name: [] for name in ARTEFACTS}
    for artefact in ARTEFACTS.values():
        for source in artefact.sources:
            if source not in index:
                raise KeyError(
                    f"Unknown source {source!r} for {artefact.name!r}")
            index[source].append(artefact.name)
    return {name: tuple(children) for name, children in index.items()}


_DEPENDANTS = _dependants_index()


def dependents(changed: Iterable[str], include_self: bool = False
               ) -> set[str]:
    """Everything that derives, directly or indirectly, from ``changed``.

    Args:
        changed: Names of the artefacts that have changed.
        include_self: Also give back the changed artefacts themselves.

    Returns:
        The set of names that are no longer valid.

    Raises:
        KeyError: On an unknown name - better a loud error than silently
            invalidating nothing.
    """
    start = list(changed)
    for name in start:
        if name not in ARTEFACTS:
            raise KeyError(f"Unknown artefact: {name!r}")
    seen: set[str] = set()
    queue = list(start)
    while queue:
        name = queue.pop()
        for child in _DEPENDANTS.get(name, ()):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    if include_self:
        seen |= set(start)
    return seen


def direct_products(names: Iterable[str]) -> set[str]:
    """The files that ``names`` write THEMSELVES (B312).

    A step and the file it writes are two sides of the same thing: the
    step record is the administration, the file is the content. The
    transcription step and ``transcription_original.json`` are made in
    one and the same action.

    That distinction matters when invalidating. "The transcription has
    been renewed, clear what was based on the previous one" means
    everything AFTER the transcription - not the file that has just been
    written. Without this rule the freshly written transcription was
    deleted immediately after the step that made it (B312), after which
    step 2 reported that there was no transcription.

    A file counts as the product of an artefact if that artefact is its
    ONLY source. A file with several sources (such as
    ``output:lyrics_alignment``, which follows from both the coupling and
    the karaoke text) is a real derivative and does lapse.
    """
    owners = set(names)
    return {name for name, artefact in ARTEFACTS.items()
            if artefact.kind == FILE and len(artefact.sources) == 1
            and artefact.sources[0] in owners}


def invalidation_plan(changed: Iterable[str], keep: Iterable[str] = (),
                      include_changed: bool = False
                      ) -> tuple[tuple[str, ...], tuple[str, ...],
                                 tuple[str, ...]]:
    """What has to disappear if ``changed`` has changed.

    Args:
        changed: The artefacts that have changed.
        keep: Artefacts that are known to still be valid and that
            (together with everything derived from them) must be spared.
            Used for "karaoke made from the original": the original stems
            stay good, so the expensive separation does not have to be
            done again.
        include_changed: Also give back the changed artefacts themselves.
            Off by default: usually they have just been rewritten with a
            new value and only what comes AFTER them is stale.

    Returns:
        ``(steps, metas, files)`` - the names per kind, sorted.
    """
    stale = dependents(changed, include_self=include_changed)
    if not include_changed:
        # B312: what the changed artefact writes itself has just been
        # made and is precisely the new result. Only with
        # ``include_changed`` (the timing being thrown away on purpose)
        # does it go along.
        stale -= direct_products(changed)
    if keep:
        spared = dependents(keep, include_self=True)
        stale -= spared
    steps, metas, files = [], [], []
    for name in sorted(stale):
        kind = ARTEFACTS[name].kind
        if kind == STEP:
            steps.append(name)
        elif kind == META:
            metas.append(name)
        elif kind == FILE:
            files.append(name)
    return tuple(steps), tuple(metas), tuple(files)


def paths_for(name: str, paths) -> list[Path]:
    """The paths belonging to file artefact ``name``."""
    artefact = ARTEFACTS[name]
    if artefact.kind != FILE or artefact.paths is None:
        return []
    return list(artefact.paths(paths))


def describe(name: str) -> str:
    """One readable line about an artefact (for the log)."""
    artefact = ARTEFACTS.get(name)
    return f"{name} ({artefact.what})" if artefact else name
