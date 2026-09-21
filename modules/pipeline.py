"""Orchestration of the pipeline steps, independent of the interface.

The graphical interface (``gui.py``) calls these functions; so do the
command line tools in ``tools/``. Expected errors (missing input,
skipped steps) are reported via :class:`PipelineError` with a neat
Dutch message.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:      # only for type annotations (B293)
    # numpy is only imported inside the functions in this file (it is a
    # heavy import that is not needed at every start), but it does occur
    # in an annotation. Thanks to ``from __future__ import annotations``
    # that annotation is never executed; this block only makes it
    # visible to pyflakes and type checkers.
    import numpy as np

from . import __version__ as _APP_VERSION
from . import align, analysis, ffmpeg, filesystem, fonts, karaoke, proc, separation
from . import dependencies, word_alignment
from . import song_text, whisper
from . import cluster as cluster_module
from . import export as export_module
from .analysis import AnalysisStats
from .config import AppConfig
from .filesystem import ProjectPaths, ProjectStore
from .translations import t
from .whisper import ProgressCallback, Segment, Word

logger = logging.getLogger(__name__)

TRACK_ORIGINAL = "original"
TRACK_KARAOKE = "karaoke"
TRACKS = (TRACK_ORIGINAL, TRACK_KARAOKE)

#: Below this alignment confidence the GUI warns that the songs
#: probably differ too much.
ALIGN_MIN_CONFIDENCE = 0.25

#: Above this drift (ms over the song) the GUI asks for correction.
DRIFT_WARN_MS = 400.0

#: Below this RMS (on the separated karaoke vocal stem) we consider the
#: stem (nearly) empty and we skip the Whisper transcription.
KARAOKE_VOCAL_SILENCE_RMS = 0.004


class PipelineError(Exception):
    """Expected error with a clear message for the user."""


@dataclass(frozen=True)
class AppContext:
    """Shared context (configuration, paths, project administration)."""

    config: AppConfig
    paths: ProjectPaths
    store: ProjectStore


@dataclass(frozen=True)
class DetectResult:
    """Result of step 1 (detecting words) for one track."""

    track: str
    segments: tuple[Segment, ...]
    from_cache: bool

    @property
    def word_count(self) -> int:
        return sum(len(segment.words) for segment in self.segments)


@dataclass(frozen=True)
class AnalyseResult:
    """Result of step 2 (analysis and clustering) for one track."""

    track: str
    stats: AnalysisStats
    clusters: tuple[cluster_module.Cluster, ...]
    json_path: Path
    html_path: Path
    suggested: tuple[int, ...]


@dataclass(frozen=True)
class KaraokeResult:
    """Result of step 4 (karaoke processing).

    ``all_intervals`` contains all fragments found; ``intervals`` only
    the active (not excluded by the user) fragments that were actually
    damped. ``restore_intervals`` (B282) are the "back from original"
    fragments from the damping editor - separate from the damping,
    because they replace a piece of karaoke audio with the original
    instead of lowering it.
    """

    intervals: tuple[karaoke.DampingInterval, ...]
    all_intervals: tuple[karaoke.DampingInterval, ...]
    output_wav: Path
    restore_intervals: tuple[karaoke.RestoreInterval, ...] = ()

    @property
    def total_damped_s(self) -> float:
        return sum(interval.end - interval.start
                   for interval in self.intervals)


def _demucs_enabled(context: AppContext) -> bool:
    """Demucs wanted (option on) and available?"""
    return context.config.advanced.demucs and separation.is_available()


def delete_project(context: AppContext) -> None:
    """Delete the active project completely (B84).

    Clears the cache (as on startup/shutdown) and removes the
    ``input`` and ``output`` subfolders of this project recursively.

    Raises:
        PipelineError: If no project is loaded.
    """
    if not context.config.song.title:
        raise PipelineError(t("err_no_project_delete"))
    import shutil
    paths = context.paths
    filesystem.clean_cache(paths.cache_dir)
    for directory in (paths.input_dir, paths.output_dir, paths.cache_dir):
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
    logger.info(t("log_project_deleted"),
                context.config.song.title)


def _audio_rms(path: Path) -> float:
    """RMS level (0..1) of an audio file; 0 on a read error."""
    try:
        from . import audio as audio_module
        import numpy as np
        data, _ = audio_module.load_audio(path)
        if data.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(data.astype("float64") ** 2)))
    except Exception:  # noqa: BLE001 - check must never break the pipeline
        return 1.0  # when in doubt do not skip


def _onset_from_signal(data, sr: int, window_s: float = 0.1) -> float | None:
    """First window with noteworthy energy in a (mono) signal."""
    import numpy as np
    if getattr(data, "ndim", 1) > 1:
        data = data.mean(axis=1)
    if data.size == 0 or sr <= 0:
        return None
    win = max(1, int(window_s * sr))
    n = data.size // win
    if n < 4:
        return None
    frames = data[:n * win].reshape(n, win).astype("float64")
    energy = np.sqrt(np.mean(frames ** 2, axis=1))
    peak = float(np.max(energy))
    if peak <= 0:
        return None
    # Floor from the quiet intro (10th percentile), not the median of the
    # whole song: in a vocals-rich song the median is high and otherwise
    # only the loudest vocals counted, which made the soft intro be
    # skipped (explained the too late onset, B133 refinement v2).
    floor = float(np.percentile(energy, 10))
    threshold = max(floor + 0.10 * (peak - floor), 0.004)
    # At least three consecutive windows above the threshold: ignores stray
    # ticks/noise peaks but reacts to a real (soft) entry.
    for idx in range(energy.size - 2):
        if (energy[idx] > threshold and energy[idx + 1] > threshold
                and energy[idx + 2] > threshold):
            return round(float(idx) * window_s, 3)
    above = np.where(energy > threshold)[0]
    if above.size:
        return round(float(above[0]) * window_s, 3)
    return None


def _first_vocal_onset(path: Path, window_s: float = 0.1) -> float | None:
    """First moment (s) with noteworthy vocal energy in a stem (B130).

    Divides the audio into windows and gives the start of the first
    window that clearly rises above the median energy. ``None`` on a
    read error or if there is no clear entry.
    """
    try:
        from . import audio as audio_module
        data, sr = audio_module.load_audio(path)
        return _onset_from_signal(data, sr, window_s)
    except Exception:  # noqa: BLE001 - onset is nice-to-have
        logger.debug(t("log_onset_failed"), path)
        return None


def _onset_from_difference(context: AppContext) -> float | None:
    """Vocal onset from ``origineel - karaoke`` (B133).

    Works above all when the karaoke is the instrumental of the
    original (e.g. a supplied Demucs version): the difference is then
    ~the vocals, and the first energy in it is the vocal entry. Both
    tracks are assumed to be on the karaoke timeline (offset ~0).
    """
    try:
        from . import audio as audio_module
        orig = filesystem.find_audio_file(context.paths.input_dir,
                                          TRACK_ORIGINAL)
        kar = filesystem.find_audio_file(context.paths.input_dir,
                                         TRACK_KARAOKE)
        if orig is None or kar is None:
            return None
        o_wav = prepare_track(context, TRACK_ORIGINAL)
        k_wav = prepare_track(context, TRACK_KARAOKE)
        od, osr = audio_module.load_audio(o_wav)
        kd, ksr = audio_module.load_audio(k_wav)
        if osr != ksr:
            return None
        if getattr(od, "ndim", 1) > 1:
            od = od.mean(axis=1)
        if getattr(kd, "ndim", 1) > 1:
            kd = kd.mean(axis=1)
        length = min(od.size, kd.size)
        if length <= 0:
            return None
        diff = od[:length].astype("float64") - kd[:length].astype("float64")
        return _onset_from_signal(diff, osr)
    except Exception:  # noqa: BLE001 - nice-to-have
        logger.debug(t("log_onset_difference_failed"))
        return None


def ensure_vocal_onset(context: AppContext) -> float | None:
    """Determine (and keep) the vocal onset, however possible (B133).

    Order: already kept -> from ``origineel - karaoke`` (supplied
    Demucs instrumental). This way the first sentence gets a good
    anchor even without the in-app "Karaoke uit origineel" button.
    """
    stored = context.store.get_meta("vocal_onset_s")
    if stored is not None:
        return float(stored)
    onset = _onset_from_difference(context)
    if onset is not None:
        context.store.set_meta("vocal_onset_s", onset)
        logger.info(t("log_onset_from_difference"), onset)
    return onset


def ensure_original_vocals(context: AppContext) -> Path | None:
    """Ensure the vocal stem of the ORIGINAL is available (B195).

    Needed for the vocal stem energy analysis (B194/B209): lengthening
    held notes and placing 'na-na' filler lines on their energy pulses.
    The stem is kept in the cache (``origineel_vocals.wav``) and is only
    remade with Demucs if it is not there yet. ``None`` if Demucs is
    missing or the original is not there (neat fallback).
    """
    cache = context.paths.cache_dir / "original_vocals.wav"
    if cache.exists():
        return cache
    if not separation.is_available():
        return None
    if filesystem.find_audio_file(context.paths.input_dir,
                                  TRACK_ORIGINAL) is None:
        return None
    try:
        original_wav = prepare_track(context, TRACK_ORIGINAL)
        stems = separation.separate_cached(
            original_wav, context.paths.cache_dir, "original")
    except (separation.SeparationError, PipelineError):
        logger.exception(t("log_vocals_failed"))
        return None
    import shutil
    context.paths.cache_dir.mkdir(parents=True, exist_ok=True)
    export_demucs_stems(context, stems)          # B212: mp3's in output
    try:
        shutil.copyfile(stems["vocals"], cache)
    except OSError:
        logger.warning(t("log_vocals_copy_failed"))
        return stems["vocals"]
    logger.info(t("log_vocals_ready"), cache)
    return cache


def make_karaoke_from_original(context: AppContext) -> Path:
    """Explicitly make an instrumental (karaoke) version from the original.

    Uses Demucs to take the vocals out and puts the instrumental stem
    as ``karaoke`` in the input folder. Because the karaoke thus shares
    exactly the same timeline as the original, that is remembered so
    that the alignment can be skipped (offset 0).

    Raises:
        PipelineError: If Demucs is missing/fails or the original is
            absent.
    """
    if not separation.is_available():
        raise PipelineError(t("err_demucs_unavailable"))
    if filesystem.find_audio_file(context.paths.input_dir,
                                  TRACK_ORIGINAL) is None:
        raise PipelineError(t("err_no_original_instrumental"))
    original_wav = prepare_track(context, TRACK_ORIGINAL)
    try:
        stems = separation.separate_cached(
            original_wav, context.paths.cache_dir, "original")
    except separation.SeparationError as exc:
        raise PipelineError(
            t("err_instrumental_failed").format(error=exc)) from exc
    import shutil
    for ext in filesystem.SUPPORTED_EXTENSIONS:
        (context.paths.input_dir / f"{TRACK_KARAOKE}{ext}").unlink(
            missing_ok=True)
    target = context.paths.input_dir / f"{TRACK_KARAOKE}.wav"
    shutil.copyfile(stems["instrumental"], target)
    # Both stems as a shareable mp3 in the output folder (B94/B212):
    # instrumental as karaoke_demucs.mp3, vocals as vocal_demucs.mp3.
    export_demucs_stems(context, stems)
    # Determine the vocal onset from the separated vocal stem before the
    # invalidation (which clears the cache with the stems). Offset 0 ->
    # coincides with the first sung line on the karaoke timeline (B130/B133).
    onset = _first_vocal_onset(stems["vocals"])
    # New karaoke -> derived data invalid (B113/B135), but the
    # original stems stay valid and are kept so that the later
    # transcription does not have to separate the original once more (B248).
    invalidate(context, ["input:karaoke"], keep=["cache:demucs_original"])
    context.store.set_meta("karaoke_from_original", True)
    if onset is not None:
        context.store.set_meta("vocal_onset_s", onset)
        logger.info(t("log_onset_from_demucs"), onset)
    context.store.clear_step(f"source_{TRACK_KARAOKE}")
    logger.info(t("log_instrumental_made"), target)
    return target


def export_demucs_karaoke(context: AppContext, instrumental_wav: Path) -> Path:
    """Write the Demucs instrumental as ``karaoke_demucs.mp3`` (B94).

    Always delivers into the output folder of the active project. The
    sample rate and channels are taken over from the separated stem.

    Returns:
        The path to ``output/<titel>/karaoke_demucs.mp3``.
    """
    context.paths.output_dir.mkdir(parents=True, exist_ok=True)
    target = context.paths.output_dir / "karaoke_demucs.mp3"
    props = ffmpeg.probe(instrumental_wav)
    ffmpeg.encode_mp3(instrumental_wav, target,
                      sample_rate=props.sample_rate or 44_100,
                      channels=props.channels or 2,
                      vbr_quality=2)
    logger.info(t("log_demucs_karaoke_done"), target)
    return target


#: Demucs stem -> mp3 name in the output folder (B212).
_DEMUCS_STEM_EXPORT = (("instrumental", "karaoke_demucs.mp3"),
                       ("vocals", "vocal_demucs.mp3"))


def remove_demucs_stems(context: AppContext) -> None:
    """Remove the derived Demucs mp3's from the output folder (B215).

    ``karaoke_demucs.mp3`` and ``vocal_demucs.mp3`` belong to the
    previous original; with a new original they are outdated and
    misleading, so away with them. They are remade at the next Demucs
    split.
    """
    for item_name in ("karaoke_demucs.mp3", "vocal_demucs.mp3"):
        try:
            (context.paths.output_dir / item_name).unlink(missing_ok=True)
        except OSError:
            logger.warning(t("log_could_not_remove"), item_name)


def export_demucs_stems(context: AppContext, stems: dict) -> None:
    """Write the Demucs stems as mp3 in the output folder (B212).

    No matter through which button Demucs ran (residual vocal
    detection, vocal stem safeguarding or 'Karaoke uit origineel'): the
    instrumental goes as ``karaoke_demucs.mp3`` and the vocals as
    ``vocal_demucs.mp3`` into ``output/<titel>/``. Fails silently (with
    a log warning) if ffmpeg cannot write the mp3; the pipeline simply
    keeps running.
    """
    context.paths.output_dir.mkdir(parents=True, exist_ok=True)
    for key, item_name in _DEMUCS_STEM_EXPORT:
        source = stems.get(key)
        if not source or not Path(source).exists():
            continue
        try:
            props = ffmpeg.probe(source)
            ffmpeg.encode_mp3(source, context.paths.output_dir / item_name,
                              sample_rate=props.sample_rate or 44_100,
                              channels=props.channels or 2, vbr_quality=2)
            logger.info(t("log_demucs_stem_done"), item_name)
        except ffmpeg.FfmpegError:
            logger.warning(t("log_could_not_write_ffmpeg"), item_name)


def check_project_paths(context: AppContext) -> tuple[bool, str]:
    """Check that all project paths belong to the active song title (B95b).

    After a project switch the input, output and cache folder and the
    project administration (``project.json``) must all point to the
    same subdir (the active title). Returns ``(ok, melding)``; on a
    mismatch the message describes what deviates.
    """
    title = context.config.song.title
    expected = ProjectPaths(root=context.paths.root, song=title,
                            output_base=context.paths.output_base)
    afwijkingen: list[str] = []
    if context.paths.song != title:
        afwijkingen.append(
            f"paden.song='{context.paths.song}' != titel='{title}'")
    controles = {
        "input": (context.paths.input_dir, expected.input_dir),
        "output": (context.paths.output_dir, expected.output_dir),
        "cache": (context.paths.cache_dir, expected.cache_dir),
    }
    for item_name, (actueel, expected_path) in controles.items():
        if actueel != expected_path:
            afwijkingen.append(f"{item_name}: {actueel} != {expected_path}")
    if context.store.path != expected.project_file:
        afwijkingen.append(
            f"project.json: {context.store.path} != {expected.project_file}")
    if afwijkingen:
        return False, "Projectpaden wijken af: " + "; ".join(afwijkingen)
    return True, f"Projectpaden consistent voor '{title or '(geen titel)'}'."


def output_writable(directory: Path) -> tuple[bool, str]:
    """Can ``directory`` be written to? (B214)

    Creates the folder if needed and tests with a temporary file. Gives
    ``(ok, melding)``; on UNC/permission problems the reason is in the message.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".karaoketool_schrijftest"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, "schrijfbaar"
    except OSError as exc:
        return False, str(exc)


def relocate_output_base(context: AppContext,
                         new_base: Path) -> tuple[bool, str, AppContext]:
    """Move the output folder to ``new_base`` and adjust everything (B214).

    First checks whether writing is allowed, then moves all existing
    project folders to the new main folder, rewrites the path
    references in each ``project.json``, and keeps the choice globally in
    the config. If ``new_base`` points to ``<root>/output``, the default
    applies again (no own folder). Returns ``(ok, melding, nieuwe_context)``.
    """
    import shutil
    from dataclasses import replace as _r
    from . import config as config_module

    default_root = context.paths.root / "output"
    new_root = Path(new_base)
    old_root = context.paths.output_root

    ok, reden = output_writable(new_root)
    if not ok:
        return False, f"Kan niet schrijven in {new_root}: {reden}", context
    if new_root.resolve() == old_root.resolve():
        return False, "Dit is al de huidige output-map.", context

    verplaatst: list[str] = []
    if old_root.exists():
        for child in sorted(old_root.iterdir()):
            if not child.is_dir():
                continue
            target = new_root / child.name
            if target.exists():
                logger.warning(t("log_already_exists"), target)
                continue
            try:
                shutil.move(str(child), str(target))
                verplaatst.append(child.name)
            except OSError:
                logger.exception(t("log_move_failed"), child)
                return (False,
                        f"Verplaatsen van '{child.name}' mislukt; "
                        "controleer of er geen bestanden open staan.",
                        context)

    # Rewrite the path references in each moved project.json.
    for item_name in verplaatst:
        pj = new_root / item_name / "settings" / "project.json"
        if pj.exists():
            try:
                ProjectStore(pj).rewrite_prefix(old_root, new_root)
            except OSError:
                logger.warning(t("log_rewrite_failed"), pj)

    is_default = new_root.resolve() == default_root.resolve()
    new_paths = _r(context.paths,
                   output_base=None if is_default else new_root)
    filesystem.ensure_directories(new_paths)
    new_store = ProjectStore(new_paths.project_file)
    output_dir = "" if is_default else str(new_root)
    new_config = _r(context.config, advanced=_r(
        context.config.advanced, output_dir=output_dir))
    config_module.save_config(new_config, new_paths.config_file)
    message = (f"Output-map ingesteld op {new_root} "
               f"({len(verplaatst)} project(en) verplaatst).")
    logger.info(message)
    return True, message, _r(context, config=new_config, paths=new_paths,
                             store=new_store)


def _generate_karaoke_from_original(context: AppContext) -> Path | None:
    """Make an instrumental (karaoke) version from the original (Demucs).

    Returns the path to the generated wav, or ``None`` if it does not
    work (then the pipeline falls back to 'karaoke missing').
    """
    original = filesystem.find_audio_file(context.paths.input_dir,
                                          TRACK_ORIGINAL)
    if original is None:
        return None
    original_wav = prepare_track(context, TRACK_ORIGINAL)
    try:
        stems = separation.separate_cached(
            original_wav, context.paths.cache_dir, "original")
    except separation.SeparationError:
        logger.exception(t("log_karaoke_from_original_failed"))
        return None
    target = context.paths.cache_dir / "karaoke_generated.wav"
    import shutil
    shutil.copyfile(stems["instrumental"], target)
    export_demucs_stems(context, stems)          # B212: mp3's in output
    logger.info(t("log_karaoke_generated"), target)
    return target


def prepare_track(context: AppContext, stem: str) -> Path:
    """Find an input file, keep the properties and deliver wav.

    Mp3 is converted to wav in ``cache``; via the checksum in
    ``project.json`` reconversion within a session is prevented.

    Raises:
        PipelineError: On missing input or missing ffmpeg.
    """
    paths = context.paths
    source = filesystem.find_audio_file(paths.input_dir, stem)
    if source is None and stem == TRACK_KARAOKE and _demucs_enabled(context):
        source = _generate_karaoke_from_original(context)
    if source is None:
        names = ", ".join(f"'{stem}{ext}'"
                          for ext in filesystem.SUPPORTED_EXTENSIONS)
        raise PipelineError(t("err_no_input_found").format(
            names=names, dir=paths.input_dir))
    if not ffmpeg.is_available():
        raise PipelineError(t("err_ffmpeg_missing"))

    checksum = filesystem.file_sha1(source)
    step_name = f"source_{stem}"
    previous = context.store.get_step(step_name)
    properties = ffmpeg.probe(source)

    if source.suffix.lower() == ".wav":
        wav_path = source
    else:
        wav_path = paths.cache_dir / f"{stem}.wav"
        cache_valid = (previous is not None
                       and previous.get("sha1") == checksum
                       and wav_path.exists())
        if cache_valid:
            logger.info(t("log_cache_current"),
                        stem)
        else:
            ffmpeg.convert_to_wav(source, wav_path)

    context.store.set_step(step_name, {
        "path": str(source),
        "sha1": checksum,
        "wav": str(wav_path),
        "properties": asdict(properties),
    })
    return wav_path


def enabled_tracks(context: AppContext) -> tuple[str, ...]:
    """The tracks on which transcription/analysis runs.

    Since v0.72 always original and karaoke (B174): they belong together
    and the choice has been taken out of the interface. The ``tracks``
    setting remains for compatibility but is no longer used here.
    """
    return (TRACK_ORIGINAL, TRACK_KARAOKE)


def track_output_dir(context: AppContext, track: str) -> Path:
    """Output folder of one track (``output/origineel`` or ``.../karaoke``)."""
    directory = context.paths.output_dir / track
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def set_input_origin(context: AppContext, key: str, source: Path) -> None:
    """Remember the original file name and location of an input (B206).

    Under water we keep fixed names (``origineel.mp3`` etc.), but the
    user recognises his own name better. We keep that name plus the folder
    he chose from, so that the file chooser opens there again the next
    time (provided the folder still exists)."""
    names = dict(context.store.get_meta("input_names") or {})
    names[key] = {"name": source.name, "dir": str(source.parent)}
    context.store.set_meta("input_names", names)
    # B413: also as the folder of THIS PROJECT, without the input kind.
    # The user puts everything for a song together in one folder first
    # and then picks the files one by one; with a memory per kind the
    # second chooser opened somewhere else again, while the file he
    # wants is next to the one he just chose.
    context.store.set_meta("input_last_dir", str(source.parent))


def input_origin(context: AppContext, key: str) -> dict | None:
    """Remembered original name/location of an input, or ``None`` (B206)."""
    return (context.store.get_meta("input_names") or {}).get(key)


#: The keys under which the original name/location of an input is kept
#: (B324). These are the same keys everywhere: writing and reading.
INPUT_NAME_KEYS = ("original", "karaoke", "lyrics", "karaoke_text", "logo")

#: Old key -> new key in ``input_names`` (B324). Up to and including
#: v0.100 the writer used the file stem (``songtekst``/``karaoketekst``)
#: while the reader asked for ``lyrics``/``karaoke_text``; the original
#: name of both text files was therefore never shown and the file
#: chooser did not open in the last folder again.
_INPUT_NAME_RENAMES = {"songtekst": "lyrics", "karaoketekst": "karaoke_text"}


def migrate_input_names(context: AppContext) -> bool:
    """Put the keys of ``input_names`` under their current name (B324).

    Returns whether something has been changed. Idempotent: an already
    correct project is left alone.
    """
    names = context.store.get_meta("input_names") or {}
    if not any(old in names for old in _INPUT_NAME_RENAMES):
        return False
    updated = dict(names)
    moved = 0
    for old, new in _INPUT_NAME_RENAMES.items():
        if old not in updated:
            continue
        value = updated.pop(old)
        # A value already stored under the new key wins: that one comes
        # from a version that did it right.
        if new not in updated:
            updated[new] = value
        moved += 1
    context.store.set_meta("input_names", updated)
    logger.info(t("log_input_names_migrated"), moved)
    return True


#: Title fields that are kept per project (in project.json) instead of
#: globally in config.json (B210): they belong to the song, not to the app.
VIDEO_TITLE_KEYS = ("karaoke_title", "orig_artist", "orig_title")


def set_project_title(context: AppContext, key: str, value: str) -> None:
    """Keep one title field per project in project.json (B210)."""
    if key not in VIDEO_TITLE_KEYS:
        return
    titels = dict(context.store.get_meta("video_titles") or {})
    titels[key] = value
    context.store.set_meta("video_titles", titels)


def apply_project_titles(context: AppContext) -> AppContext:
    """Load the per-project titles (project.json) in ``config.video`` (B210).

    One-off migration: if this project has no stored titles yet but
    there are (old, global) values in the config, those are recorded as
    project values so that they are not lost. Returns a (possibly)
    updated context; the render reads ``config.video`` and therefore
    works unchanged.
    """
    from dataclasses import replace as _replace
    saved = context.store.get_meta("video_titles")
    video = context.config.video
    if saved is None:
        migratie = {k: getattr(video, k, "") for k in VIDEO_TITLE_KEYS}
        if any(v.strip() for v in migratie.values()):
            context.store.set_meta("video_titles", migratie)
        return context
    # B470: keys that this project does not have were SKIPPED, so the
    # value of the previously opened project stayed in the config and was
    # rendered into someone else's video. A title that is not there is
    # empty, never the one from before.
    new = {k: str(saved.get(k) or "") for k in VIDEO_TITLE_KEYS}
    return _replace(context, config=_replace(
        context.config, video=_replace(video, **new)))


def input_display_name(context: AppContext, key: str, fallback: str) -> str:
    """Original file name for display, with fallback on ``fallback`` (B206)."""
    origin = input_origin(context, key)
    if origin and origin.get("name"):
        return str(origin["name"])
    return fallback


def input_start_dir(context: AppContext, key: str) -> str:
    """Start folder for the file chooser (B206, B388).

    The last used location of THIS project if it still exists. B388: if
    there is none - a fresh project - this used to return an empty
    string, and that is not neutral: handed an empty path, Qt fills in
    the last folder used anywhere in this run of the program. So a new
    project opened in the folder of the previous one, which reads as the
    program having forgotten that you started something new.

    Returning a real path is what stops that. The home folder is the
    neutral answer: it belongs to nobody's previous project and it is
    where the user's own music lives.
    """
    origin = input_origin(context, key)
    if origin and origin.get("dir"):
        path = Path(str(origin["dir"]))
        if path.exists():
            return str(path)
    # B413: no folder for this kind yet - then the last folder of this
    # project, because that is where the rest of this song stands.
    last = context.store.get_meta("input_last_dir")
    if last:
        path = Path(str(last))
        if path.exists():
            return str(path)
    try:
        return str(Path.home())
    except (OSError, RuntimeError):     # noqa: BLE001 - geen thuismap
        return ""


#: Minimum probability at which the detected lyrics language is
#: passed on to Whisper; below that Whisper detects it itself
#: (or the GUI asks for a manual choice).
LANGUAGE_MIN_PROB = 0.70

#: Margin within which two language candidates count as "equally likely"
#: and the GUI still asks for a manual choice (B208). 0.05 = 5%.
LANGUAGE_AMBIGUOUS_MARGIN = 0.05


def _is_filler_line(line: str) -> bool:
    """Is this line a non-lexical filler line (na-na, la-la, oh-oh)? (B207)

    Purely structural, no word list: crowd/pause markers and hyphens
    away, then a line is 'filler' if it consists only of a few short,
    repeating syllables. Such lines (and carnival is full of them)
    disturb the language detection and are therefore filtered out.
    """
    import re as _re
    text = _re.sub(r"(?i)\[/?crowd\]|\[/?pause\]", " ", line)
    text = _re.sub(r"[-–—_]", " ", text)
    tokens = _re.findall(r"[^\W\d]+", text.lower(), flags=_re.UNICODE)
    if not tokens:
        return True                      # only markers/punctuation
    distinct = set(tokens)
    # Several short syllables with at most two variants -> "na na na".
    if len(tokens) >= 2 and all(len(w) <= 3 for w in tokens) \
            and len(distinct) <= 2:
        return True
    # One token that repeats a short syllable -> "lalala", "nanana".
    if len(tokens) == 1:
        w = tokens[0]
        for base in (1, 2, 3):
            if len(w) > base and w == w[:base] * (len(w) // base) \
                    and len(w) % base == 0:
                return True
    return False


def _strip_filler_for_language(text: str) -> str:
    """Remove filler lines before the language detection (B207).

    Falls back to the original text if nothing sensible remains after
    filtering, so that a song which consists almost entirely of 'na-na'
    can still be detected.
    """
    kept = [ln for ln in text.splitlines() if not _is_filler_line(ln)]
    schoon = "\n".join(kept).strip()
    return schoon or text


#: B495: a second language only counts as a second language once there
#: is a real passage of it - more than two words in a row, or more than
#: five over the whole song. Below that it is a loan word or a title.
SECOND_LANGUAGE_RUN = 2
SECOND_LANGUAGE_TOTAL = 5

#: Unicode blocks with the language they point at. Deliberately by
#: SCRIPT and not by statistics: a passage in Korean characters is not a
#: probability but a fact, and that is precisely the case the language
#: detection cannot see (it works on Latin words).
_SCRIPTS: tuple[tuple[str, int, int], ...] = (
    ("ko", 0xAC00, 0xD7A3),      # Hangul syllables
    ("ko", 0x1100, 0x11FF),      # Hangul Jamo
    ("ja", 0x3040, 0x30FF),      # Hiragana + Katakana
    ("zh", 0x4E00, 0x9FFF),      # CJK
    ("ru", 0x0400, 0x04FF),      # Cyrillic
    ("el", 0x0370, 0x03FF),      # Greek
    ("ar", 0x0600, 0x06FF),      # Arabic
    ("he", 0x0590, 0x05FF),      # Hebrew
    ("th", 0x0E00, 0x0E7F),      # Thai
)


def _script_of(word: str) -> str | None:
    """The language a word points at by its characters, or ``None``."""
    for letter in word:
        code = ord(letter)
        for language, low, high in _SCRIPTS:
            if low <= code <= high:
                return language
    return None


def second_language(text: str) -> tuple[str, int] | None:
    """A second language in this text, by its characters (B495).

    Returns ``(code, number of words)`` as soon as the passage is big
    enough: more than ``SECOND_LANGUAGE_RUN`` words in a row or more
    than ``SECOND_LANGUAGE_TOTAL`` over the whole text. ``None``
    otherwise. The user's own rule, and a sensible one - one foreign
    word is a name, a whole line is a language.
    """
    import re as _re

    counts: dict[str, int] = {}
    longest: dict[str, int] = {}
    running: dict[str, int] = {}
    for line in text.splitlines():
        running.clear()
        for word in _re.findall(r"\S+", line):
            language = _script_of(word)
            for code in list(running):
                if code != language:
                    running[code] = 0
            if language is None:
                continue
            counts[language] = counts.get(language, 0) + 1
            running[language] = running.get(language, 0) + 1
            longest[language] = max(longest.get(language, 0),
                                    running[language])
    for language, total in sorted(counts.items(), key=lambda kv: -kv[1]):
        if (longest.get(language, 0) > SECOND_LANGUAGE_RUN
                or total > SECOND_LANGUAGE_TOTAL):
            return language, total
    return None


def second_language_of(context: AppContext,
                       track: str = TRACK_ORIGINAL) -> tuple[str, int] | None:
    """The second language in the text of this track (B495)."""
    path = _text_for_language(context, track)
    if not path.exists():
        return None
    try:
        return second_language(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def language_ambiguous(candidates: list[tuple[str, float]],
                       margin: float = LANGUAGE_AMBIGUOUS_MARGIN) -> bool:
    """Do the two best language candidates lie within ``margin`` of each
    other? (B208)

    If so, the detection is effectively a guess and the GUI had better
    ask for a manual choice, even though the leader reaches the
    threshold.
    """
    if len(candidates) < 2:
        return False
    return (candidates[0][1] - candidates[1][1]) < margin


def _detect_language_probs(text: str) -> list[tuple[str, float]]:
    """Detect language candidates with probability (langdetect).

    langdetect is non-deterministic by default (random seed), which
    made the same text yield 'nl' one time and 'auto' another time.
    With a fixed seed the detection is reproducible (B149).
    """
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 0
        return [(str(item.lang), float(item.prob))
                for item in detect_langs(text)]
    except Exception:  # noqa: BLE001 - lib missing or too little text
        return []


def _text_for_language(context: AppContext, track: str) -> Path:
    """The text file on which the language of a track is detected.

    Original -> lyrics.txt, karaoke -> karaoke_text.txt (B115).
    """
    from . import karaoke_text
    if track == TRACK_KARAOKE:
        return context.paths.input_dir / karaoke_text.FILENAME
    return context.paths.input_dir / song_text.LYRICS_FILENAME


def language_candidates(context: AppContext,
                        track: str = TRACK_ORIGINAL
                        ) -> list[tuple[str, float]]:
    """Language candidates (code, chance) based on the text of this track.

    Per track on its own text file (B115): original on the lyrics,
    karaoke on the karaoke text. Empty if the file is missing.
    """
    path = _text_for_language(context, track)
    if not path.exists():
        return []
    schoon = _strip_filler_for_language(path.read_text(encoding="utf-8"))
    return _detect_language_probs(schoon)


def word_pins(context: AppContext) -> dict[int, list[int]]:
    """Manual word couplings: lyrics index -> list of transcript
    indices (empty = uncoupled) (B121)."""
    step = context.store.get_step("word_coupling") or {}
    pins: dict[int, list[int]] = {}
    for key, value in (step.get("pins") or {}).items():
        if isinstance(value, list):
            pins[int(key)] = [int(v) for v in value]
        elif value is None:
            pins[int(key)] = []
        else:                              # old 1-to-1 format
            pins[int(key)] = [int(value)]
    return pins


#: Marker in the ``word_coupling`` step saying that the transcript
#: indices of the manual couplings count the FULL transcription,
#: including the words that the hallucination filter throws out (B309).
#: Up to and including v0.96 those words were missing from the list, so
#: that every filtered segment shifted all subsequent indices - and
#: therefore silently displaced the manual couplings after it. Without
#: this marker the stored pins are still in the old layout and are
#: converted once (``_pins_for_transcript``).
_PIN_LAYOUT_FULL = "full"


#: Marker saying that the pin KEYS count positions in the lyric word
#: list as it has been since v0.135.0 (B417). Digits now stay in that
#: list (B412) and a hyphen splits a word (B418), so both changes shift
#: every pin after the first number or hyphen - silently, because a pin
#: keeps working, it just points at a different word. On the measured
#: collection that was eight pins over two projects. Without this marker
#: the stored keys are still in the old layout and are converted once.
_PIN_LYRICS_SPLIT = "split"


def migrate_lyric_pins(context: AppContext) -> dict[int, list[int]]:
    """Convert the pin keys once to the current word list (B417).

    Deliberately not by counting the numbers and hyphens: that would be
    a rule that has to be extended at every next change of the
    tokenisation, and would be wrong exactly once. Instead both lists
    are built - the old shape from ``words_before_b418``, the new one
    from ``split_word`` - and laid against each other; what stays the
    same keeps its place, and a word that fell apart takes its first
    piece. That way this conversion also survives the next change.
    """
    step = context.store.get_step("word_coupling") or {}
    pins = word_pins(context)
    if step.get("lyrics_layout") == _PIN_LYRICS_SPLIT:
        return pins
    path = context.paths.input_dir / song_text.LYRICS_FILENAME
    if not pins or not path.exists():
        _keep_pins(context, pins, step)
        return pins
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return pins
    old_words = song_text.words_before_b418(text)
    new_words = [piece for raw in text.split()
                 for piece in song_text.split_word(raw)]
    moved = _remap_lyric_indexes(old_words, new_words)
    changed = sum(1 for key in pins if moved.get(key, key) != key)
    pins = {moved.get(key, key): value for key, value in pins.items()}
    if changed:
        logger.info(t("log_pins_relocated"), changed, len(pins))
    _keep_pins(context, pins, step)
    return pins


def _remap_lyric_indexes(old_words, new_words) -> dict[int, int]:
    """Old position -> new position in the lyric word list (B417)."""
    import difflib

    moved: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(a=old_words, b=new_words,
                                      autojunk=False)
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(a2 - a1):
                moved[a1 + offset] = b1 + offset
        elif b2 > b1:
            # A word that changed shape ("la-la-la" into three, "45"
            # which did not exist before): take the first new piece, so
            # the pin lands on the same spot in the song.
            for offset in range(a2 - a1):
                moved[a1 + offset] = min(b1 + offset, b2 - 1)
    return moved


def _keep_pins(context: AppContext, pins: dict[int, list[int]],
               step: dict) -> None:
    """Write the pins back WITH both layout markers (B417).

    Explicitly not through ``set_word_pins``: that one sets the
    transcript marker to "full", and doing that here would skip the
    B309 conversion that may still be waiting.
    """
    kept = {"pins": {str(k): list(v) for k, v in pins.items()},
            "lyrics_layout": _PIN_LYRICS_SPLIT}
    if step.get("layout"):
        kept["layout"] = step["layout"]
    context.store.set_step("word_coupling", kept)


def set_word_pins(context: AppContext, pins: dict[int, list[int]]) -> None:
    """Keep the manual word couplings (B121).

    B506: WITH both layout markers. Without ``lyrics_layout`` the B417
    conversion runs again at the next read, on keys that are already in
    the new shape - and shifts them again. Measured on a text with a
    hyphen in it that was two words per save, compounding: a pin on
    "hey" walked to "het" and then to "nu". Every save through the
    coupling editor comes through here, so this is the most likely way
    the couplings at "Lied R" drifted in the first place.

    The description (``marks``) and the list fingerprints are
    deliberately NOT written: what the user has just saved means what it
    points at right now, so the next read adopts that instead of
    relocating onto it.
    """
    context.store.set_step("word_coupling", {
        "pins": {str(k): list(v) for k, v in pins.items()},
        "layout": _PIN_LAYOUT_FULL,
        "lyrics_layout": _PIN_LYRICS_SPLIT})
    logger.info(t("log_pins_saved"), len(pins))


#: B506: the manual couplings, written down by WHAT they mean instead of
#: only by where they sat. A pin is two bare numbers - a position in the
#: lyric word list and a position in the transcription - and both lists
#: keep changing shape. B412 kept the digits in, B418 split on a hyphen,
#: B484/B485 changed what ``[bg]`` does to the tokens; each of those
#: shifts every pin after the first affected word. It was migrated once
#: per change, with a marker saying it had been done, and that marker is
#: the flaw: it promises that the list will never change again. At
#: "Lied R" that cost sixty-six couplings, drifted by two to thirteen
#: places, and they did not fail loudly - they pointed at another word.
#:
#: So next to the numbers each pin now carries a description: which
#: lyrics word (text, line number, which occurrence within that line)
#: and which found words (text and start time). Plus a fingerprint of
#: both lists. Do the fingerprints still match, then the numbers are
#: used unchanged; do they not, then every pin is looked up again by its
#: description, and one that can no longer be found is let go WITH a log
#: line instead of silently landing somewhere else.
_PIN_MARKS = "marks"
_PIN_LISTS = "lists"


def _fingerprint(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _lyrics_fingerprint(lyrics: Sequence) -> str:
    return _fingerprint("\n".join(f"{word.line}\t{word.text}"
                                  for word in lyrics))


def _transcript_fingerprint(transcript: Sequence) -> str:
    return _fingerprint("\n".join(f"{row[0]}\t{float(row[1]):.3f}"
                                  for row in transcript))


def _lyric_marks(lyrics: Sequence) -> list[dict]:
    """Per lyrics word its description (B506).

    Text plus line number plus which occurrence of that word within that
    line. Deliberately not the position in the whole song: that is the
    number this is meant to survive. "The second 'you' on line 19" keeps
    meaning the same word when the tokenisation changes.

    The line number counted here is the number of the line among the
    lines that HAVE words, not the raw file line. ``LyricWord.line``
    counts every line in the file, blank ones included, so adding one
    blank line renumbers the whole rest of the song while not a single
    word moves - and every pin after it would be let go for nothing.
    """
    numbers: dict[int, int] = {}
    seen: dict[tuple, int] = {}
    out = []
    for word in lyrics:
        raw = int(word.line)
        if raw not in numbers:
            numbers[raw] = len(numbers)
        line = numbers[raw]
        key = (line, str(word.text).casefold())
        nth = seen.get(key, 0)
        seen[key] = nth + 1
        out.append({"text": str(word.text), "line": line, "nth": nth})
    return out


#: How far a found word may have moved and still be the same word
#: (B506). A cut or a merge shifts a start by a fraction; a different
#: transcription puts other words there altogether, and then letting go
#: is the right answer.
_PIN_TARGET_SLACK_S = 0.35


def _find_target(mark: dict, transcript: Sequence,
                 taken: set[int] | None = None) -> int | None:
    """The found word this pin means, or ``None`` (B506).

    ``taken`` holds the found words that another pin has already
    claimed. Without that a row of identical words ("na na na") that all
    shifted a little collapses onto one index: every pin then picks the
    same nearest match, two lyrics words get the same time span, and the
    order of the sentence breaks - while the log cheerfully reports that
    nothing was let go.
    """
    want = str(mark.get("text", "")).casefold()
    start = float(mark.get("start", -1.0))
    used = taken or set()
    best = None
    for index, row in enumerate(transcript):
        if index in used or str(row[0]).casefold() != want:
            continue
        gap = abs(float(row[1]) - start)
        if gap <= _PIN_TARGET_SLACK_S and (best is None or gap < best[1]):
            best = (index, gap)
    return None if best is None else best[0]


def _marks_from_pins(pins: dict[int, list[int]], lyrics: Sequence,
                     transcript: Sequence
                     ) -> tuple[list[dict], dict[int, list[int]]]:
    """Describe the pins as they stand now (B506).

    Returns the descriptions AND the pins that could be described. A pin
    that points outside one of the lists says nothing about what it
    meant, so describing it would freeze a guess - but keeping it in the
    numbers while it has no description means it disappears silently at
    the next relocation. It is dropped here instead, where it can be
    counted.
    """
    labels = _lyric_marks(lyrics)
    marks = []
    kept: dict[int, list[int]] = {}
    for lyric, targets in sorted(pins.items()):
        if not (0 <= lyric < len(labels)):
            continue
        if any(not (0 <= target < len(transcript)) for target in targets):
            continue
        entry = dict(labels[lyric])
        entry["targets"] = [
            {"text": str(transcript[target][0]),
             "start": round(float(transcript[target][1]), 3)}
            for target in targets]
        marks.append(entry)
        kept[lyric] = list(targets)
    return marks, kept


def _pins_from_marks(marks: Sequence[dict], lyrics: Sequence,
                     transcript: Sequence) -> tuple[dict[int, list[int]], int]:
    """Look the pins up again by their description (B506)."""
    by_word = {(entry["line"], entry["text"].casefold(), entry["nth"]): index
               for index, entry in enumerate(_lyric_marks(lyrics))}
    out: dict[int, list[int]] = {}
    taken: set[int] = set()
    lost = 0
    for mark in marks:
        try:
            key = (int(mark["line"]), str(mark["text"]).casefold(),
                   int(mark["nth"]))
        except (KeyError, TypeError, ValueError):
            lost += 1
            continue
        lyric = by_word.get(key)
        if lyric is None:
            lost += 1
            continue
        targets = []
        for item in mark.get("targets") or ():
            found = _find_target(item, transcript, taken)
            if found is None:
                targets = None
                break
            targets.append(found)
        if targets is None:
            lost += 1
            continue
        taken.update(targets)
        # An EMPTY pin survives on its own: "I uncoupled this word" is a
        # decision about the lyrics word and needs no found word.
        out[lyric] = targets
    return out, lost


def anchor_pins(context: AppContext, pins: dict[int, list[int]],
                lyrics: Sequence, transcript: Sequence
                ) -> dict[int, list[int]]:
    """Keep the manual couplings on the words they mean (B506).

    The first time round nothing is relocated: what stands there now is
    adopted as the truth and written down. Only from then on can a
    shift be seen, and only then is anything moved.
    """
    step = context.store.get_step("word_coupling") or {}
    keys = {"lyrics": _lyrics_fingerprint(lyrics),
            "transcript": _transcript_fingerprint(transcript)}
    marks = step.get(_PIN_MARKS)
    if marks is not None and (step.get(_PIN_LISTS) or {}) == keys:
        return pins
    if marks is None:
        out, lost = dict(pins), 0
    else:
        out, lost = _pins_from_marks(marks, lyrics, transcript)
    before = len(out)
    described, out = _marks_from_pins(out, lyrics, transcript)
    lost += before - len(out)
    if lost or (marks is not None and out != pins):
        logger.info(t("log_pins_relocated_by_text"), len(out), lost)
    kept = {"pins": {str(k): list(v) for k, v in out.items()},
            _PIN_MARKS: described,
            _PIN_LISTS: keys}
    for name in ("layout", "lyrics_layout"):
        if step.get(name):
            kept[name] = step[name]
    context.store.set_step("word_coupling", kept)
    return out


def _shift_pin_index(index: int, filtered: Sequence[int]) -> int:
    """An old transcript index converted to the full transcription (B309).

    ``filtered`` holds the positions that the filtered out words occupy
    in the NEW list. Every such position at or before the word shifts it
    one place further.
    """
    shifted = index
    for position in sorted(filtered):
        if position <= shifted:
            shifted += 1
    return shifted


def _pins_for_transcript(context: AppContext,
                         filtered: Sequence[int]) -> dict[int, list[int]]:
    """The manual couplings, converted once to the full transcription
    (B309). See ``_PIN_LAYOUT_FULL`` for why that conversion is needed."""
    pins = word_pins(context)
    step = context.store.get_step("word_coupling") or {}
    if step.get("layout") == _PIN_LAYOUT_FULL:
        return pins
    if pins and filtered:
        pins = {lyric: [_shift_pin_index(target, filtered)
                        for target in targets]
                for lyric, targets in pins.items()}
        logger.info(t("log_pins_migrated"), len(pins))
    set_word_pins(context, pins)
    return pins


def transcript_override(context: AppContext
                        ) -> list[tuple[str, float, float]] | None:
    """The manually edited (cut/merged) transcription (B153).

    ``None`` if the user has not adjusted the words found; then the
    original Whisper transcription applies.
    """
    step = context.store.get_step("transcript_override") or {}
    rows = step.get("words")
    if not rows:
        return None
    return [(str(t), float(s), float(e)) for t, s, e in rows]


def set_transcript_override(
        context: AppContext,
        transcript: list[tuple[str, float, float]] | None) -> None:
    """Keep (or clear) the edited transcription for the coupling (B153)."""
    if not transcript:
        context.store.clear_step("transcript_override")
        logger.info(t("log_transcript_override_cleared"))
        return
    context.store.set_step("transcript_override", {
        "words": [[t, s, e] for t, s, e in transcript]})
    logger.info(t("log_transcript_override_saved"),
                len(transcript))


def lyrics_override(context: AppContext) -> list[tuple[str, int]] | None:
    """The edited (cut/merged) lyrics words (B156).

    ``None`` if the user has not adjusted the lyrics words in the
    coupling editor; then the normal lyrics.txt applies. This only
    changes the coupling/analysis, not the karaoke text shown in the
    video.
    """
    step = context.store.get_step("lyrics_override") or {}
    rows = step.get("words")
    if not rows:
        return None
    return [(str(t), int(r)) for t, r in rows]


def set_lyrics_override(context: AppContext,
                        lyrics: list[tuple[str, int]] | None) -> None:
    """Keep (or clear) the edited lyrics words for the coupling (B156)."""
    if not lyrics:
        context.store.clear_step("lyrics_override")
        logger.info(t("log_lyrics_override_cleared"))
        return
    context.store.set_step("lyrics_override", {
        "words": [[t, r] for t, r in lyrics]})
    logger.info(t("log_lyrics_override_saved"), len(lyrics))


def _effective_lyrics(context: AppContext, lyrics_path: Path):
    """The lyrics words: the override if there is one, otherwise the file."""
    override = lyrics_override(context)
    if override:
        return tuple(song_text.LyricWord(index=i, text=t, line=r)
                     for i, (t, r) in enumerate(override))
    return song_text.load_lyrics(lyrics_path)


def _word_overlaps_dropped_segment(
    aligned: tuple, index: int, dropped_segments: list,
) -> bool:
    """Does the estimated position of uncoupled lyrics word ``index``
    (in ``aligned``) fall within a Whisper segment filtered as a
    hallucination (B287)?

    Uses the same anchor window idea as the filler word match attempt in
    ``song_text.align_lyrics`` (B276): the time span between the nearest
    neighbouring words before and after it that are coupled. If a
    filtered out hallucination segment falls (partly) within it, that is
    presumably the reason this word could not be coupled.
    """
    if not dropped_segments:
        return False
    prev_a = next((p for p in range(index - 1, -1, -1)
                  if aligned[p].start is not None), None)
    next_a = next((p for p in range(index + 1, len(aligned))
                  if aligned[p].start is not None), None)
    lo = 0.0 if prev_a is None else aligned[prev_a].end
    hi = None if next_a is None else aligned[next_a].start
    for seg in dropped_segments:
        if seg.end <= lo:
            continue
        if hi is not None and seg.start >= hi:
            continue
        return True
    return False


def _anchor_window_times(aligned: tuple,
                         index: int) -> tuple[float, float | None]:
    """The time span in which uncoupled lyrics word ``index`` must lie.

    Bounded by the nearest coupled words before and after it. ``None`` as
    upper bound means: there is no coupled word after it any more, so the
    span runs on to the end of the song.
    """
    prev_a = next((p for p in range(index - 1, -1, -1)
                  if aligned[p].start is not None), None)
    next_a = next((p for p in range(index + 1, len(aligned))
                  if aligned[p].start is not None), None)
    return (0.0 if prev_a is None else aligned[prev_a].end,
            None if next_a is None else aligned[next_a].start)


def _word_in_transcription_gap(aligned: tuple, index: int,
                               segments: tuple) -> bool:
    """Did Whisper simply produce nothing at this position? (B308)

    An uncoupled lyrics word used to be marked as "hallucination
    filtered" as soon as a filtered out segment happened to fall in its
    anchor window - also when the real cause was quite different: Whisper
    recognised nothing at all there for tens of seconds (a la-la-la
    outro, a shouting crowd, a heavily instrumental piece). That is a
    different problem with a different solution, and the editor
    therefore has to name it differently.

    This function establishes the hole itself: within the anchor window
    of the word there is no single KEPT transcription segment, and the
    window is at least ``_TRANSCRIPTION_GAP_MIN_S`` long (or runs on to
    the end of the song, in which case there is nothing at all after it).
    """
    lo, hi = _anchor_window_times(aligned, index)
    if hi is not None and hi - lo < _TRANSCRIPTION_GAP_MIN_S:
        return False
    for seg in segments:
        if seg.end <= lo:
            continue
        if hi is not None and seg.start >= hi:
            continue
        return False
    return True


def _full_transcript(segments: tuple, clean: tuple
                     ) -> tuple[list[tuple[str, float, float]], list[int]]:
    """The transcription INCLUDING the filtered out words (B309).

    The coupling editor shows every word that Whisper produced, also the
    ones the hallucination filter threw out - otherwise you cannot see
    that they were there, let alone couple one after all if the filter
    was wrong. The automatic coupling keeps working on the filtered
    segments only; the filtered words are handed over separately so that
    the caller can keep them out of the automatic coupling.

    A second gain: the transcript index of a word no longer depends on
    what the filter decides. Previously every filtered segment shifted
    all subsequent indices, and thus silently displaced the manual
    couplings after it.

    Returns:
        ``(transcript, filtered)`` - the flat list of all words and the
        indices in it of the filtered out words.
    """
    transcript = song_text.flat_transcript(segments)
    kept = {round(start, 3)
            for _text, start, _end in song_text.flat_transcript(clean)}
    filtered = [index for index, (_text, start, _end)
                in enumerate(transcript) if round(start, 3) not in kept]
    return transcript, filtered


def _coupling_transcript(context: AppContext, segments: tuple, clean: tuple
                         ) -> tuple[list[tuple[str, float, float]],
                                    list[int]]:
    """The word list on which the manual couplings are numbered.

    The manually edited transcription (cut/merge, B153) takes precedence:
    if the user has taken over the word list himself, that list counts
    and there is nothing filtered out in it.
    """
    override = transcript_override(context)
    if override:
        return override, []
    return _full_transcript(segments, clean)


def held_transcript_words(transcript) -> frozenset:
    """Which FOUND words are held long (B441).

    The same question the render asks of a syllable, asked here of the
    transcription - and here it can be asked before there is any timing
    at all, because Whisper already says per word how long it lasted.
    That is what makes it useful in the coupling editor: the user is
    deciding there how to spread the stresses over the karaoke text, and
    "this word is sung for two and a half seconds" is exactly the thing
    he cannot hear from the text.

    Same rule and the same two thresholds as ``timing.mark_held``, but
    measured against the median of the WHOLE song instead of one line: a
    transcription has no lines, and a segment boundary is not a musical
    one.
    """
    from . import timing as timing_module

    spans = [(index, float(end) - float(start))
             for index, (_text, start, end) in enumerate(transcript)
             if end is not None and start is not None]
    lengths = [span for _index, span in spans if span > 0]
    if len(lengths) < timing_module.HELD_MIN_SYLLABLES:
        return frozenset()
    middle = statistics.median(lengths)
    if middle <= 0:
        return frozenset()
    return frozenset(
        index for index, span in spans
        if span >= timing_module.HELD_MIN_S
        and span >= timing_module.HELD_FACTOR * middle)


def word_coupling_view(context: AppContext) -> dict | None:
    """Data for the word coupling editor (B121).

    Gives the transcription words found (original, INCLUDING the ones
    filtered out as hallucinations - B309) and per lyrics word the
    current coupling (transcript index, text found, confidence, whether
    it was pinned manually, and a ``status`` for the editor display of
    words that are (still) not coupled (B287/B308: "filler_skipped",
    "no_match", "hallucination_filtered" or "transcription_gap")).
    ``None`` if lyrics/transcription is missing.

    Returns (besides ``transcript`` and ``words``) ``filtered``: the
    transcript indices of the filtered out words. The editor shows those
    struck through and the automatic coupling leaves them alone, but the
    user can still couple one by hand if the filter was wrong.
    """
    lyrics_path = context.paths.input_dir / song_text.LYRICS_FILENAME
    if not lyrics_path.exists():
        return None
    try:
        segments = load_segments(context, TRACK_ORIGINAL)
    except PipelineError:
        return None
    # B417: the keys of the manual couplings count positions in the word
    # list, and that list changed shape. Convert first, so before anybody
    # reads a pin.
    migrate_lyric_pins(context)
    lyrics = _effective_lyrics(context, lyrics_path)
    dropped_segments: list = []
    clean, aligned = _clean_segments_and_alignment(
        context, lyrics, segments, dropped_out=dropped_segments)
    aligned = _place_skipped_on_energy(context, aligned)  # B313
    # Show the edited transcription if there is one (cut/merge, B153).
    transcript, filtered = _coupling_transcript(context, segments, clean)
    blocked = set(filtered)
    repeated_filler = song_text.repeated_filler_lines(lyrics)  # B286
    pins = _pins_for_transcript(context, filtered)
    pins = anchor_pins(context, pins, lyrics, transcript)      # B506
    # transcript index per (start,text) to show the auto coupling.
    index_by_start = {round(s, 3): i for i, (_t, s, _e)
                      in enumerate(transcript)}
    # First round: the automatic 1-to-1 base coupling per word, so that
    # we know which found words are already claimed before we possibly
    # extend them (B191).
    auto_base: dict[int, int | None] = {}
    for aw in aligned:
        if aw.start is not None:
            auto_base[aw.lyric.index] = index_by_start.get(round(aw.start, 3))
    claimed = {v for v in auto_base.values() if v is not None}
    words = []
    for aw in aligned:
        li = aw.lyric.index
        if li in pins:
            targets = list(pins[li])
        elif auto_base.get(li) is not None:
            base = auto_base[li]
            # Neighbours of other words may not be stolen, and a filtered
            # out word is never attached automatically (B309).
            others = (claimed | blocked) - {base}
            targets = song_text.extend_coupling(
                aw.lyric.text, transcript, base, others)
        else:
            targets = []
        words.append({
            "index": li, "text": aw.lyric.text, "line": aw.lyric.line,
            "transcript_indices": targets, "found": aw.matched_text,
            "sim": round(float(aw.sim), 3), "pinned": li in pins,
        })
    # Creative addition (B228): 2-to-1 ("fort minable" -> "formidable") and
    # real 1-to-1 gaps within the anchor window. Pinned words stay as the
    # user set them.
    verbeterd = song_text.creative_couplings(
        [w["text"] for w in words], transcript,
        [w["transcript_indices"] for w in words], blocked=blocked)
    from .cluster import phonetic_key as _pk, similarity as _sim
    for w, new in zip(words, verbeterd):
        if w["pinned"] or new == w["transcript_indices"]:
            continue
        w["transcript_indices"] = new
        if new:
            found = " ".join(transcript[t][0] for t in new
                                if 0 <= t < len(transcript))
            w["found"] = found
            w["sim"] = round(float(_sim(_pk(w["text"]), _pk(found))), 3)
    # Status marking for the editor (B287/B308): four visually different
    # signals for words that (after all the coupling attempts above) still
    # have no coupling, so that the user sees at a glance whether he has
    # to do something himself AND what the cause is. Backing vocals (bg)
    # and manually pinned words get no marking: those were already
    # handled deliberately, also if the user left a word explicitly
    # loose. Order of precedence: first the hole in the transcription
    # (B308) - if Whisper produced nothing at all there, that is the
    # cause, even if a filtered out hallucination happens to fall in the
    # same span; then a filtered out hallucination segment (B287); then a
    # deliberately skipped filler word (B213/B276/B287); otherwise the
    # generic "no match".
    for i, (aw, w) in enumerate(zip(aligned, words)):
        if w["transcript_indices"]:
            w["status"] = "coupled"
        elif aw.lyric.bg:
            # B507: background vocals, shown everywhere except in the
            # render. "Not coupled" says nothing about them, but calling
            # them coupled says something untrue - so they get their own
            # code.
            w["status"] = "background"
        elif w["pinned"]:
            # B506: the user uncoupled this word himself. That beats the
            # automatic coupling, and up to v0.145.0 it was invisible:
            # the word stayed loose while nothing said why.
            w["status"] = "manually_uncoupled"
        elif aw.estimated:
            # B313: not coupled, but a time WAS measured on the vocal
            # stem. That is something other than "there is nothing here"
            # and the user has to be able to see the difference.
            w["status"] = "energy_placed"
        elif _word_in_transcription_gap(aligned, i, clean):
            w["status"] = "transcription_gap"
        elif _word_overlaps_dropped_segment(aligned, i, dropped_segments):
            w["status"] = "hallucination_filtered"
        elif song_text.is_filler_word(aw.lyric.text) \
                and aw.lyric.line not in repeated_filler:
            w["status"] = "filler_skipped"
        else:
            w["status"] = "no_match"
    # B441: and which of them is held long. Not a status - a held word is
    # normally coupled just fine, so it would push the real status out of
    # the way. It is its own mark, drawn the way the render draws it: a
    # line underneath.
    held = held_transcript_words(transcript)
    for w in words:
        w["held"] = any(index in held for index in w["transcript_indices"])
    in_lyrics = words_in_the_lyrics(transcript, lyrics)          # B521
    return {"transcript": transcript, "words": words, "filtered": filtered,
            "held": sorted(held), "in_lyrics": sorted(in_lyrics),
            "found_status": _transcript_status(transcript, words, filtered,
                                               in_lyrics)}


#: B502: this many transcription words in a row without a single
#: coupling before it is called a suspected hallucination. Below that it
#: is an ordinary missed word; from here on it is a passage that belongs
#: to nothing - which is exactly what the user pointed at.
SUSPECT_RUN = 4


#: B521: from this share of a run occurring in the lyrics, the run is a
#: REPETITION the text does not have instead of a suspected invention.
#: Two thirds, so one mis-heard word in a run of four does not tip it.
_REPEAT_RUN_SHARE = 0.66


def found_word_status(count: int, used, filtered,
                      in_lyrics=()) -> dict[int, str]:
    """A status per FOUND word, for the top lane of the editor (B502).

    That lane had two states: normal, or filtered out. A word that was
    found but coupled to nothing got no marking at all, while that is
    the case you want to see - and a whole row of them together is what
    a hallucination looks like on screen.

    Deliberately measured AFTER the coupling instead of before it: a run
    without any coupling can by definition not contain a coupled word,
    so this can never touch one. And it is a marking, not a removal - in
    a song with a passage in another language such a run is real
    singing, and then the user overrules it by hand.

    B521: a run whose words DO occur in the lyrics is not a suspected
    invention but a repetition the text does not have - the song sings
    the line twice and it is written once, so the coupling has already
    used those words up. Measured on the user's own project: "at a bar
    called O'Malley." at 268.8 s was marked as looking like a
    hallucination while it is literally line 34 of his lyrics.

    B520: this is the ONE place that decides, so the editor can redo it
    after every edit instead of falling back on a cruder version.
    """
    used = set(used)
    blocked = set(filtered)
    known = set(in_lyrics)
    out: dict[int, str] = {}
    for index in range(count):
        if index in used:
            out[index] = "coupled"
        elif index in blocked:
            out[index] = "hallucination_filtered"
        else:
            out[index] = "no_match"
    # Runs of at least SUSPECT_RUN uncoupled words in a row. Only words
    # that are still there count: one that the filter has already thrown
    # out keeps its own marking and does not lower the threshold.
    run: list[int] = []
    for index in range(count + 1):
        if index < count and out.get(index) == "no_match":
            run.append(index)
            continue
        if len(run) >= SUSPECT_RUN:
            share = (sum(1 for position in run if position in known)
                     / len(run))
            label = ("repeat_missing" if share >= _REPEAT_RUN_SHARE
                     else "suspect_run")
            for position in run:
                out[position] = label
        run = []
    return out


def _transcript_status(transcript, words, filtered,
                       in_lyrics=()) -> dict[int, str]:
    """The statuses of the found words for this view (B502/B521)."""
    used = {index for w in words for index in w["transcript_indices"]}
    return found_word_status(len(transcript), used, filtered, in_lyrics)


def words_in_the_lyrics(transcript, lyrics) -> frozenset:
    """Which found words occur (phonetically) in the lyrics (B521)."""
    keys = frozenset(cluster_module.phonetic_key(w.text) for w in lyrics)
    return frozenset(
        index for index, row in enumerate(transcript)
        if cluster_module.phonetic_key(str(row[0])) in keys)


#: B350: from this confidence a found word without a coupling counts as
#: "really heard". Measured over four projects the uncoupled words with
#: 0.5 or more form a short list (0 to 12 per song); below it is the
#: usual mumbling at the end of a line.
_MISSING_MIN_CONF = 0.5
#: And from this phonetic similarity to a lyrics word in the
#: neighbourhood it is not unknown text but a REPETITION missing from the
#: lyrics. Deliberately high: "Collections" against "reflections" scores
#: 0.80 and that is a mishearing, not a missing repetition.
_MISSING_MIN_SIMILARITY = 0.9
#: How far around the position it looks for that same word.
_MISSING_WINDOW = 8


def missing_repetitions(context: AppContext) -> list[dict]:
    """Words that were clearly heard but are not in the lyrics (B350).

    Lyrics from the internet are typed out by hand, and with vocalises a
    repetition drops out easily - four times "shalalie shalala" in a row
    feels like a mistake, so two get written. The tool knows both sides:
    it hears four and it sees two. Per stretch of consecutive uncoupled
    words it reports the time, the text, the lyrics line it belongs to
    and whether it is a missing repetition (that same word IS there
    nearby) or unknown text.
    """
    from .cluster import phonetic_key, similarity

    view = word_coupling_view(context)
    if not view:
        return []
    transcript = view["transcript"]
    words = view["words"]
    blocked = set(view.get("filtered") or ())
    used = {i for w in words for i in w["transcript_indices"]}
    confidence = _transcript_confidence(context)
    loose = [i for i, (_t, start, _e) in enumerate(transcript)
             if i not in used and i not in blocked
             and confidence.get(round(start, 3), 0.0) >= _MISSING_MIN_CONF]
    if not loose or not words:
        return []
    owner = {i: wi for wi, w in enumerate(words)
             for i in w["transcript_indices"]}
    runs: list[list[int]] = []
    for index in loose:
        if runs and index == runs[-1][-1] + 1:
            runs[-1].append(index)
        else:
            runs.append([index])
    found: list[dict] = []
    for run in runs:
        before = [owner[k] for k in range(run[0] - 1, -1, -1) if k in owner]
        after = [owner[k] for k in range(run[-1] + 1, len(transcript))
                 if k in owner]
        low = before[0] if before else 0
        high = after[0] if after else len(words) - 1
        neighbourhood = words[max(0, low - _MISSING_WINDOW):
                              min(len(words), high + _MISSING_WINDOW + 1)]
        best, twin = 0.0, None
        for index in run:
            key = phonetic_key(transcript[index][0])
            for candidate in neighbourhood:
                score = float(similarity(key, phonetic_key(candidate["text"])))
                if score > best:
                    best, twin = score, candidate
        repetition = best >= _MISSING_MIN_SIMILARITY and twin is not None
        found.append({
            "start": float(transcript[run[0]][1]),
            "text": " ".join(transcript[i][0] for i in run),
            "line": int(twin["line"] if repetition else words[low]["line"]),
            "repetition": repetition,
            "similarity": round(best, 2),
        })
    # One report per lyrics line: a repeating outro would otherwise give
    # six messages about the same spot.
    per_line: dict[tuple[int, bool], dict] = {}
    for item in found:
        key = (item["line"], item["repetition"])
        if key not in per_line or item["start"] < per_line[key]["start"]:
            per_line[key] = item
    return sorted(per_line.values(), key=lambda item: item["start"])


def _transcript_confidence(context: AppContext) -> dict[float, float]:
    """Whisper's confidence per word start (B350)."""
    try:
        segments = load_segments(context, TRACK_ORIGINAL)
    except PipelineError:
        return {}
    return {round(w.start, 3): float(w.confidence)
            for segment in segments for w in segment.words}


def texts_identical(context: AppContext) -> bool:
    """Are the lyrics and karaoke text (virtually) equal in content? (B115)

    Quick sanity check: if both files are the same after normalisation
    (lower case, crowd markers and whitespace away), the wrong text is
    probably with the original.
    """
    from . import karaoke_text
    lyrics = context.paths.input_dir / song_text.LYRICS_FILENAME
    karaoke = context.paths.input_dir / karaoke_text.FILENAME
    if not (lyrics.exists() and karaoke.exists()):
        return False

    import re as _re

    def norm(path: Path) -> str:
        text = path.read_text(encoding="utf-8").lower()
        text = _re.sub(r"(?i)\[/?crowd\]|\[/?pause\]", " ", text)
        text = _re.sub(r"[^\wàâçéèêëîïôûùüÿœæ]+", " ", text)
        return " ".join(text.split())

    return bool(norm(lyrics)) and norm(lyrics) == norm(karaoke)


def language_choice(context: AppContext) -> str | None:
    """The manually chosen language for this project, or ``None``."""
    return context.store.get_meta("language_choice")


def set_language_choice(context: AppContext, code: str) -> None:
    """Keep the manually chosen language (applies to Whisper and forced
    alignment) permanently in the project."""
    context.store.set_meta("language_choice", code)
    logger.info(t("log_language_fixed"), code)


def _language_for(context: AppContext, track: str) -> str:
    """Determine the transcription language and log the reasoning.

    Order: manual choice -> lyrics detection (only above the
    threshold) -> for the karaoke the language detected on the original
    -> 'auto'. At a low probability the function lets Whisper choose
    itself; the GUI can ask for a manual choice beforehand.
    """
    import json as _json

    manual = language_choice(context)
    if manual:
        logger.info(t("log_language_manual"), track, manual)
        return manual

    candidates = language_candidates(context, track)
    if candidates:
        top_code, top_prob = candidates[0]
        overview = ", ".join(f"{code} {prob:.0%}"
                              for code, prob in candidates[:3])
        if language_ambiguous(candidates):
            logger.info(t("log_language_too_close"), track, overview)
            return "auto"
        if top_prob >= LANGUAGE_MIN_PROB:
            logger.info(t("log_language_from_text"), track, top_code, overview)
            return top_code
        logger.info(t("log_language_uncertain"), track, overview)
        return "auto"

    if track == TRACK_KARAOKE:
        run_info = (context.paths.output_dir / TRACK_ORIGINAL
                    / "run_info.json")
        if run_info.exists():
            try:
                code = str(_json.loads(run_info.read_text(
                    encoding="utf-8"))["language"])
                logger.info(t("log_language_from_original"), code)
                return code
            except (OSError, ValueError, KeyError):
                pass
    logger.info(t("log_no_lyrics_language"),
                track, context.config.whisper.language)
    return context.config.whisper.language


def detect_track(context: AppContext, track: str,
                 progress: ProgressCallback | None = None,
                 cancelled=None) -> DetectResult:
    """Transcribe one track (with cache within the session)."""
    wav_path = prepare_track(context, track)
    # If the karaoke is the earlier made Demucs instrumental, then there is
    # by definition no vocals: the whole residual vocal analysis (Demucs +
    # Whisper) is superfluous and is skipped (B118).
    if track == TRACK_KARAOKE and context.store.get_meta(
            "karaoke_from_original"):
        logger.info(t("log_karaoke_is_instrumental"))
        cache_file = transcript_cache(context, track)
        whisper.save_segments((), cache_file)
        context.store.set_step(f"whisper_{track}", {
            "wav_sha1": filesystem.file_sha1(wav_path),
            "model": context.config.whisper.model,
            "language": "n.v.t.", "cache": str(cache_file),
            "segments": 0, "words": 0, "empty": True})
        return DetectResult(track, (), False)
    if track == TRACK_KARAOKE and _demucs_enabled(context):
        try:
            logger.info(t("log_demucs_started_residual"))
            stems = separation.separate_cached(
                wav_path, context.paths.cache_dir, "karaoke")
            wav_path = stems["vocals"]  # transcribe only the (residual) vocals
            logger.info(t("log_residual_on_stem"))
            rms = _audio_rms(wav_path)
            if rms < KARAOKE_VOCAL_SILENCE_RMS:
                logger.info(t("log_karaoke_vocals_empty"), rms,
                            KARAOKE_VOCAL_SILENCE_RMS)
                cache_file = transcript_cache(context, track)
                whisper.save_segments((), cache_file)
                context.store.set_step(f"whisper_{track}", {
                    "wav_sha1": filesystem.file_sha1(wav_path),
                    "model": context.config.whisper.model,
                    "language": "n.v.t.", "cache": str(cache_file),
                    "segments": 0, "words": 0, "empty": True})
                return DetectResult(track, (), False)
            # Real (residual) vocals found: the onset is immediately a good
            # anchor for the first sentence (B133).
            if context.store.get_meta("vocal_onset_s") is None:
                onset = _first_vocal_onset(wav_path)
                if onset is not None:
                    context.store.set_meta("vocal_onset_s", onset)
                    logger.info(t("log_onset_from_karaoke"),
                                onset)
        except separation.SeparationError:
            logger.exception(t("log_separation_failed_karaoke"))
    # Transcribe the original on the separated VOCAL STEM (B142): on the
    # full mix (vocals + instruments, certainly with dialect) Whisper
    # largely makes "MUZIEK" of it and misses the first half. On the
    # isolated vocals the words and their times are much more reliable,
    # which strongly improves the coupling and timing. Fallback on the mix.
    if track == TRACK_ORIGINAL and _demucs_enabled(context):
        try:
            logger.info(t("log_demucs_started_original"))
            stems = separation.separate_cached(
                wav_path, context.paths.cache_dir, "original")
            # This split is the useful one: instrumental = karaoke,
            # vocals = the original vocals. Both as mp3 in output (B212),
            # also without "Karaoke uit origineel" having been used.
            export_demucs_stems(context, stems)
            wav_path = stems["vocals"]
            if context.store.get_meta("vocal_onset_s") is None:
                onset = _first_vocal_onset(wav_path)
                if onset is not None:
                    context.store.set_meta("vocal_onset_s", onset)
                    logger.info(t("log_onset_from_original"),
                                onset)
        except separation.SeparationError:
            logger.exception(t("log_separation_failed_original"))
    settings = context.config.whisper
    # Determine the actually used language (lyrics detection -> Whisper)
    # already here, so that the cache key and the administration contain
    # the real language (not the config default 'auto'); this way another
    # detected language causes a re-transcription and the diagnostics fit.
    language_code = _language_for(context, track)
    # B263: pass the (deduplicated) lyrics along as Whisper context,
    # only for the original (the karaoke text is the parody, other
    # vocabulary). Without lyrics.txt this stays empty (no behaviour
    # change). The prompt counts in the cache key: edited lyrics
    # without an audio change must be transcribed again.
    prompt = ""
    if track == TRACK_ORIGINAL:
        lyrics_path = context.paths.input_dir / song_text.LYRICS_FILENAME
        if lyrics_path.exists():
            try:
                prompt = song_text.deduped_prompt_text(
                    _effective_lyrics(context, lyrics_path))
            except Exception:  # noqa: BLE001 - prompt is best-effort
                logger.exception(t("log_prompt_failed"))
                prompt = ""
    checksum = filesystem.file_sha1(wav_path)
    cache_file = transcript_cache(context, track)
    # B311: forced alignment belongs in the cache key. That option
    # rewrites the word times of the transcription below, so a cached
    # transcription made WITH it is a different result from one without.
    # Turning the option off used to change nothing at all, because the
    # cache kept hitting on the four keys that were checked.
    refine_times = bool(context.config.advanced.forced_alignment)
    # B442: chunking belongs in the cache key for exactly the reason
    # forced alignment does (B311) - a transcription made WITH it is a
    # different result, and without this the cache would keep handing
    # back the one-run answer after the option was switched on.
    in_pieces = (track == TRACK_ORIGINAL
                 and bool(context.config.advanced.chunked_transcription))
    # B538: and so does the second language, for the same reason. Add a
    # Korean verse to the text and the cached transcription is the
    # answer to a different question - without this key the app would
    # keep handing back the run that never heard it.
    second_code = (_second_language_code(context, language_code, track)
                   if in_pieces else "")
    step = context.store.get_step(f"whisper_{track}")
    # B549: kept before the step is overwritten below.
    earlier_fingerprint = str((step or {}).get("transcript_sha1", ""))
    if (step is not None
            and step.get("wav_sha1") == checksum
            and step.get("model") == settings.model
            and step.get("language") == language_code
            and step.get("initial_prompt", "") == prompt
            and bool(step.get("forced_alignment",
                              refine_times)) == refine_times
            and bool(step.get("chunked", in_pieces)) == in_pieces
            and str(step.get("second_language", second_code)) == second_code
            and cache_file.exists()):
        cached = whisper.load_segments(cache_file)
        # B549: a project from before this version has no fingerprint in
        # its step, and a cache hit returns here before the step is
        # written - so without this it would never get one, and the
        # first "Nu legen" after the update would still cost the user
        # his coupling. The hit itself says these segments belong to
        # this key, so this is the moment to note it down.
        if not earlier_fingerprint:
            step["transcript_sha1"] = transcript_fingerprint(cached)
            context.store.set_step(f"whisper_{track}", step)
        return DetectResult(track, cached, True)

    filled = 0
    if in_pieces:
        # B538: the third value is the second language that was REALLY
        # read. Without measured singing there is none, and then it may
        # not end up in the key either - the next run would see a
        # different key and transcribe the whole song again for nothing.
        segments, filled, second_code = _transcribe_in_pieces(
            context, wav_path, settings, prompt, language_code,
            track_output_dir(context, track), progress, cancelled)
    else:
        segments = whisper.transcribe(wav_path, settings,
                                      track_output_dir(context, track),
                                      progress=progress,
                                      language_override=language_code,
                                      cancelled=cancelled,
                                      initial_prompt=prompt)
    if (track == TRACK_ORIGINAL
            and context.config.advanced.forced_alignment
            and word_alignment.is_available()):
        if language_code and language_code != "auto":
            logger.info(t("log_forced_alignment_started"), language_code)
        else:
            logger.info(t("log_forced_alignment_skipped"))
        segments = word_alignment.refine(wav_path, segments, language_code)
    whisper.save_segments(segments, cache_file)
    fingerprint = transcript_fingerprint(segments)  # B549
    context.store.set_step(f"whisper_{track}", {
        "wav_sha1": checksum,
        "model": settings.model,
        "language": language_code,  # actually used language (B149)
        "cache": str(cache_file),
        "segments": len(segments),
        "words": sum(len(segment.words) for segment in segments),
        "initial_prompt": prompt,  # B263
        "forced_alignment": refine_times,  # B311
        "chunked": in_pieces,  # B442
        "filled_from_pieces": filled,  # B442
        "second_language": second_code,  # B538
        "transcript_sha1": fingerprint,  # B549
    })
    # B265: this is a real new transcription (not a cache hit from the
    # check above) - any manual word coupling and the alignment/timing
    # built on it refer to the OLD text and must therefore lapse,
    # otherwise old coupling data keeps hanging around and is later
    # unleashed on the new transcription.
    #
    # B549: unless the text is word for word the one the handiwork was
    # made on. "Nu legen" removes the transcription from the cache, and
    # the cache hit above needs that file, so after emptying there is
    # never a hit and the coupling, timing.json and timing_auto.json
    # went every single time - even though the transcription that came
    # back was identical. Missing the cache is not the same as a new
    # answer. The fingerprint stands in the step, which lives in
    # project.json and therefore survives an emptied cache.
    if fingerprint and fingerprint == earlier_fingerprint:
        logger.info(t("log_transcript_unchanged"), track)
    else:
        invalidate_after_fresh_transcript(context, track)
    return DetectResult(track, segments, False)


def chanted_keys(context: AppContext) -> frozenset:
    """Syllables the TEXTS themselves repeat back to back (B464).

    This is what tells a carnival chant apart from a Whisper loop, and
    the difference matters because they look identical from the outside.
    B455 exempted any short word repeated three times from the
    hallucination check, reasoning that Whisper invents plausible
    sentences and not singing. That reasoning is wrong: a repetition
    loop is one of Whisper's signature hallucinations - on an
    instrumental stretch it will happily produce "la la la la la". The
    measurement said so plainly. The filter was worth +0.07 s before
    B455, -0.49 after it, and -0.40 after the first repair; the broad
    exemption cost about half a second of timing all by itself.

    So the text decides. The user writes "la-la-la" or "na-na-na" when a
    passage really is chanted, and a word he only sings once stands in
    the text once. A key lands in here only when the same syllable
    follows itself somewhere in the lyrics or in the karaoke text.
    """
    from . import cluster as cluster_module
    from . import karaoke_text

    found: set[str] = set()

    def scan(words) -> None:
        previous = ""
        run = 1
        for word in words:
            key = cluster_module.phonetic_key(word)
            if key and key == previous:
                run += 1
                if run >= _CHANT_REPEATS:
                    found.add(key)
            else:
                previous, run = key, 1

    lyrics_path = context.paths.input_dir / song_text.LYRICS_FILENAME
    if lyrics_path.exists():
        try:
            scan([w.text for w in song_text.load_lyrics(lyrics_path)])
        except OSError:
            pass
    karaoke = context.paths.input_dir / karaoke_text.FILENAME
    if karaoke.exists():
        try:
            for line in karaoke_text.parse_lines(karaoke):
                scan([piece for word in str(line.text).split()
                      for piece in song_text.split_word(word)])
        except OSError:
            pass
    found.discard("")
    return frozenset(found)


def lyric_keys(context: AppContext) -> frozenset:
    """The phonetic keys of the lyrics, to score a candidate word.

    B427: from BOTH texts. The check exists to catch invented words, and
    it was rejecting correct ones. On a song where the original sings
    "na-na-na" and Whisper writes "la", the chunked run scored 32% and
    was disqualified as the merge base - while those words were simply
    heard right and only spelled differently. The karaoke text of that
    same song writes the passage as "la-la-la". Two texts of one song,
    and together they describe what may be sung; for a guard, too mild
    beats too strict.

    B442: this was a private function in the test panel while the trial
    was the only thing that cut anything. The program cuts now, so it
    lives here and the panel asks it here - the B360 lesson, knowledge in
    two places drifts apart.
    """
    from . import cluster as cluster_module
    from . import karaoke_text

    keys = set()
    lyrics = context.paths.input_dir / song_text.LYRICS_FILENAME
    if lyrics.exists():
        keys.update(cluster_module.phonetic_key(w.text)
                    for w in song_text.load_lyrics(lyrics))
    karaoke = context.paths.input_dir / karaoke_text.FILENAME
    if karaoke.exists():
        try:
            for line in karaoke_text.parse_lines(karaoke):
                # Same splitting as the lyrics side (B418), otherwise
                # "La-la-la-la-la" becomes one key that nothing matches.
                keys.update(cluster_module.phonetic_key(piece)
                            for word in str(line.text).split()
                            for piece in song_text.split_word(word))
        except OSError:
            pass
    keys.discard("")
    return frozenset(keys)


def _second_language_code(context: AppContext, language_code: str,
                          track: str = TRACK_ORIGINAL) -> str:
    """The second language to read this track in as well, or "" (B538).

    Only when the TEXT really holds a passage in another script (B495),
    and never when it is the language of the run itself - reading the
    same song twice in the same language buys nothing and costs a
    Whisper run.
    """
    found = second_language_of(context, track)
    if found is None:
        return ""
    code = str(found[0])
    first = str(language_code or "")
    # Kanji count as Chinese by their block (B495), and a Japanese song
    # is full of them. Reading such a song once more "in Chinese" is a
    # whole Whisper run for a script the first run already knows.
    if first == "ja" and code == "zh":
        return ""
    return "" if code == first else code


def _transcribe_in_pieces(context: AppContext, wav_path: Path, settings,
                          prompt: str, language_code: str, output_dir: Path,
                          progress=None, cancelled=None):
    """The whole song AND its pieces, in one queue (B442).

    What the night job of v0.136.0 measured, brought into production.
    Four songs, unheard singing: 197.7 s for the single run against 71.5
    s once the pieces fill the holes. Two findings shape this:

    * the gain comes from the CUTTING, not from a prompt per piece. The
      global prompt beat the per-piece one on two songs and tied on a
      third, so the pieces need no first transcription to lean on - and
      that is precisely what lets everything go into ONE queue instead
      of two rounds;
    * cutting plus VAD was worse on all four, so no VAD here.

    The whole run is the heaviest single job and therefore starts first,
    the pieces follow by descending length - the user's rule. A piece
    may only FILL: where the whole run heard a word, that word stands,
    and a piece never overrules it.

    Falls back to the plain run without complaining when there is
    nothing to cut on (no vocal windows, so no Demucs or no singing
    found). Better one honest run than a cut in the wrong place.

    B538: does the text hold a real passage in another script, then the
    whole song is read once more in THAT language and joins the queue as
    one more job. It may fill silence, like a piece, and it can never
    overrule a word the first run heard. Measured on "Lied_R2"
    (1.5.11g, 31 August): 0.08 s against 0.09 s for the bare first
    language on the line starts, and 2.0 s of singing recovered in three
    pieces - exactly the three Korean shouts. Nothing was lost: zero
    seconds that the first language had and the merge did not.
    """
    from . import whisper_chunks as wc

    # B442: the ORIGINAL's own timeline. This function cuts the original
    # vocal stem and weighs word times measured in that same file, so a
    # projection onto the karaoke would put both beside the truth.
    windows = _original_vocal_windows(context)
    total = max((high for _low, high in windows), default=0.0)
    pieces = wc.cut_points(windows, total) if windows else ()
    # B538: without measured singing a second reading can contribute
    # nothing at all - a word only counts as a filler when it sits on
    # singing - so it would be a whole Whisper run for certain nothing,
    # and it would take the progress bar with it (the bar counts jobs
    # and needs a duration). Then the plain honest run.
    second = _second_language_code(context, language_code) if windows else ""
    if len(pieces) < 2 and not second:
        logger.info(t("log_chunked_skipped"))
        return whisper.transcribe(wav_path, settings, output_dir,
                                  progress=progress,
                                  language_override=language_code,
                                  cancelled=cancelled,
                                  initial_prompt=prompt), 0, ""

    cut = pieces if len(pieces) >= 2 else ()
    jobs = wc.jobs_heaviest_first(cut, total, second)
    logger.info(t("log_chunked_started"), len(cut))
    if second:
        logger.info(t("log_second_language_run"), second)

    def per_job(ready: int, count: int) -> None:
        # A piece is not a stream, so there is nothing to report DURING
        # one - the honest unit here is "so many of so many done".
        if progress is not None and total > 0 and count:
            progress(min(total, total * ready / count), total)

    found = wc.run_over_lanes(wav_path, settings, jobs, prompt,
                              language_code, cancelled=cancelled,
                              on_done=per_job)
    base = found.get((0.0, None), ())
    base_words = wc.words_of(base)
    added = wc.words_to_add(base_words, wc.extra_words_from(found),
                            windows, lyric_keys(context))
    segments = list(whisper.segments_to_dicts(base))
    segments += wc.segments_from_words(added, first_index=len(segments))
    segments.sort(key=lambda s: float(s["start"]))
    for number, segment in enumerate(segments):
        segment["index"] = number
    logger.info(t("log_chunked_filled"), len(added),
                round(wc.unheard_seconds(base_words, windows), 1),
                round(wc.unheard_seconds(base_words + added, windows), 1))
    if second:
        # B538: what the second language contributed on its own, so the
        # log says whether it was worth its run and not only that it ran.
        from_second = wc.words_of(found.get((0.0, None, second), ()))
        starts = {round(float(w["start"]), 3) for w in from_second}
        logger.info(t("log_second_language_filled"), second,
                    sum(1 for w in added
                        if round(float(w["start"]), 3) in starts))
    merged = whisper.segments_from_dicts(segments)
    whisper.write_outputs(merged, {
        "file": str(wav_path), "model": settings.model,
        "language": language_code, "segments": len(merged),
        "words": sum(len(s.words) for s in merged),
        "chunked_pieces": len(cut),
        "filled_from_pieces": len(added),
        "second_language": second,          # B538
    }, output_dir)
    return merged, len(added), second


# B293: here stood ``detect_words`` and the type alias
# ``TrackProgressCallback``. ``detect_words`` did exactly what
# ``detect_tracks(..., parallel=False)`` does (preparing + transcribing the
# ticked tracks one by one) and was called by nothing in the application
# - the GUI uses ``detect_tracks``. Keeping two entrances to the same
# step 1 means that a change in the one silently passes by the other.
# ``TrackProgressCallback`` was a type alias as a string that was used
# nowhere as an annotation or import.


def _looks_like_oom(exc: BaseException) -> bool:
    """Recognise a memory shortage (RAM or GPU/VRAM)."""
    if isinstance(exc, MemoryError):
        return True
    text_value = str(exc).lower()
    return any(key in text_value for key in
               ("out of memory", "cuda out of memory", "oom",
                "cannot allocate", "geheugen"))


def projects_without_cache(context: AppContext) -> list[str]:
    """Projects that were transcribed once but whose cache is gone (1.5).

    TEMPORARY tool. With a cleared cache the measurement - and a rebuild
    of the coupling - runs on ``original/segments.json``, and that is
    the RAW transcription from before the forced alignment (B348). Only
    projects whose audio is still there are named, because without that
    nothing can be transcribed.
    """
    root = context.paths.output_root
    if not root.is_dir():
        return []
    found = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        song = folder.name
        paths = filesystem.ProjectPaths(root=context.paths.root, song=song,
                                        output_base=context.paths.output_base)
        if not paths.project_file.exists():
            continue
        store = filesystem.ProjectStore(paths.project_file)
        if store.get_step(f"whisper_{TRACK_ORIGINAL}") is None:
            continue
        if (paths.cache_dir / f"transcription_{TRACK_ORIGINAL}.json").exists():
            continue
        if not sorted(paths.input_dir.glob(f"{TRACK_ORIGINAL}.*")):
            continue
        found.append((not paths.timing_file.exists(), song))
    # Projects with hand-corrected timing first: those are the ones that
    # make the measurement worth something, so if the run is stopped
    # halfway they are the ones that are done.
    return [song for _later, song in sorted(found)]


def context_for_project(context: AppContext, song: str) -> AppContext:
    """A sibling context for another project of the same installation."""
    paths = filesystem.ProjectPaths(root=context.paths.root, song=song,
                                    output_base=context.paths.output_base)
    filesystem.ensure_directories(paths)
    config = replace(context.config,
                     song=replace(context.config.song, title=song))
    return AppContext(paths=paths, config=config,
                      store=filesystem.ProjectStore(paths.project_file))


def fill_transcription_cache(context: AppContext, progress=None,
                             cancelled=None) -> bool:
    """Write ONLY the transcription cache of the original (1.5).

    Does exactly what "1.1 Detect words" does up to and including the
    cache file, and then stops: no step administration, no invalidation,
    no output files. That is the whole point - re-running 1.1 would
    throw away everything derived from it, including the hand-corrected
    ``timing.json``, and that handwork is precisely what makes these
    projects worth measuring.

    Returns ``False`` when the cache was already there.
    """
    import tempfile

    cache_file = transcript_cache(context, TRACK_ORIGINAL)
    if cache_file.exists():
        return False
    wav_path = prepare_track(context, TRACK_ORIGINAL)
    if _demucs_enabled(context):
        try:
            stems = separation.separate_cached(
                wav_path, context.paths.cache_dir, "original")
            wav_path = stems["vocals"]
        except separation.SeparationError:
            logger.exception(t("log_separation_failed_original"))
    step = context.store.get_step(f"whisper_{TRACK_ORIGINAL}") or {}
    language_code = (step.get("language")
                     or _language_for(context, TRACK_ORIGINAL))
    # The prompt as it was at the time, so the transcription comes out
    # the same as the one the stored coupling was made from.
    prompt = step.get("initial_prompt", "")
    with tempfile.TemporaryDirectory() as scratch:
        segments = whisper.transcribe(
            wav_path, context.config.whisper, Path(scratch),
            progress=progress, language_override=language_code,
            cancelled=cancelled, initial_prompt=prompt)
    if (context.config.advanced.forced_alignment
            and word_alignment.is_available()):
        segments = word_alignment.refine(wav_path, segments, language_code)
    whisper.save_segments(segments, cache_file)
    logger.info(t("log_cache_filled"), context.config.song.title,
                len(segments))
    return True


def detect_tracks(context: AppContext, progress=None, cancelled=None,
                  parallel: bool | None = None,
                  track_done=None) -> dict[str, DetectResult]:
    """Transcribe the ticked tracks, possibly in parallel (B90).

    Args:
        context: The application context.
        progress: Optional feedback ``(track, verwerkte_s, totaal_s)``
            so that the GUI can show its own progress bar per track.
        cancelled: Callable that returns ``True`` as soon as the user
            presses Stop; is shared by all (parallel) tasks.
        parallel: Force parallel/sequential; ``None`` = follow the
            setting ``geavanceerd.parallelle_detectie``.
        track_done: Optional feedback ``(track)`` as soon as one track
            is completely done (transcription + any forced alignment),
            so that the GUI can put that bar on 100%/"done" (B96).

    Returns:
        ``{track: DetectResult}``.

    Raises:
        whisper.CancelledError: If the user aborts.

    The input is prepared first. With one active track or when the
    option is off, it runs sequentially. If a parallel run hits a
    memory shortage, it falls back neatly on sequential.
    """
    sync_input_changes(context)          # B311
    prepare_track(context, TRACK_ORIGINAL)
    prepare_track(context, TRACK_KARAOKE)
    tracks = list(enabled_tracks(context))
    if parallel is None:
        parallel = context.config.advanced.parallel_detection

    def per_track(track: str):
        if cancelled is not None and cancelled():
            raise whisper.CancelledError()
        cb = None
        if progress is not None:
            cb = lambda done, total, tr=track: progress(tr, done, total)  # noqa: E731
        result = detect_track(context, track, cb, cancelled)
        try:
            write_transcription_history(context, track, result)
        except OSError:
            logger.warning(t("log_history_write_failed"),
                           track)
        if track_done is not None:
            track_done(track)
        return result

    if not parallel or len(tracks) < 2:
        return {track: per_track(track) for track in tracks}

    logger.info(t("log_parallel_detection"), ", ".join(tracks))
    results: dict[str, DetectResult] = {}
    errors: dict[str, BaseException] = {}

    def worker(track: str) -> None:
        try:
            results[track] = per_track(track)
        except BaseException as exc:  # noqa: BLE001 - keep per thread
            errors[track] = exc

    threads = [threading.Thread(target=worker, args=(track,),
                                name=f"detect-{track}")
               for track in tracks]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if any(isinstance(exc, whisper.CancelledError)
           for exc in errors.values()):
        raise whisper.CancelledError()
    if errors:
        first = next(iter(errors.values()))
        if any(_looks_like_oom(exc) for exc in errors.values()):
            logger.warning(t("log_parallel_out_of_memory"))
            return {track: per_track(track) for track in tracks}
        raise first
    return results


def diagnostics_dir(context: AppContext) -> Path:
    """Subfolder for local diagnostics in the output (B143)."""
    return context.paths.output_dir / "diagnostics"


def diagnostics_enabled(context: AppContext) -> bool:
    """May local diagnostic files be written? (B143)"""
    return bool(context.config.advanced.diagnostics)


def transcription_history_path(context: AppContext, track: str) -> Path:
    """Path to the permanent transcription history file (B131/B143)."""
    return diagnostics_dir(context) / f"transcription_{track}.json"


def write_transcription_history(context: AppContext, track: str,
                                result: DetectResult) -> Path | None:
    """Add a transcription run to the diagnostics file (B131/B143).

    Does not overwrite, but appends a run per detection with a
    timestamp, so that it is visible whether and when a step was done
    again. The app version is written along, but only when it has
    changed compared to the previous run (less noise). On a real
    (non-cache) run the segments are written along too. Writes nothing
    if diagnostics is off.
    """
    from datetime import datetime, timezone

    if not diagnostics_enabled(context):
        return None
    path = transcription_history_path(context, track)
    data: dict = {"track": track, "runs": []}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("runs"),
                                                       list):
                data = loaded
        except (OSError, json.JSONDecodeError):
            logger.warning(t("log_history_unreadable"))

    step = context.store.get_step(f"whisper_{track}") or {}
    entry: dict = {
        "time": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"),
        "from_cache": bool(result.from_cache),
        "model": step.get("model"),
        "language": step.get("language"),
        "segments": len(result.segments),
        "words": sum(len(s.words) for s in result.segments),
    }
    # Only log the app version if it has changed compared to the previous
    # run (less noise, B143).
    vorige_versie = next((r.get("version") for r in reversed(data["runs"])
                          if r.get("version")), None)
    if _APP_VERSION != vorige_versie:
        entry["version"] = _APP_VERSION
    if not result.from_cache:
        entry["segments"] = [
            {"start": s.start, "end": s.end, "text": s.text,
             "words": [{"text": w.text, "start": w.start, "end": w.end,
                          "conf": w.confidence} for w in s.words]}
            for s in result.segments
        ]
    data["runs"].append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    logger.info(t("log_history_updated"),
                path.name, len(data["runs"]),
                "cache" if result.from_cache else "nieuw")
    return path


def _remove_artefact_path(path: Path) -> bool:
    """Remove one file or folder; ``True`` if something disappeared."""
    if not path.exists():
        return False
    try:
        if path.is_dir():
            import shutil
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink()
    except OSError:
        logger.warning(t("log_derived_delete_failed"),
                       path)
        return False
    return True


def invalidate(context: AppContext, changed: Sequence[str],
               keep: Sequence[str] = (),
               include_changed: bool = False) -> tuple[str, ...]:
    """Remove everything that derives from ``changed`` (B311).

    This is the ONE place where invalidation happens. What has to go is
    not a list maintained here but a question to the derivation chain in
    :mod:`modules.dependencies`: what depends, directly or indirectly, on
    what changed? That way a new step can no longer be forgotten - the
    chain describes it, or the guard test goes red.

    Args:
        context: The project.
        changed: Names of the artefacts that have changed, e.g.
            ``["input:lyrics"]`` or ``["whisper_original"]``.
        keep: Artefacts that are known to be still valid and that
            (with everything under them) must be spared. Used for
            "karaoke made from the original": the separated stems of the
            original stay good, so that expensive separation does not
            have to be done again (B248).
        include_changed: Also clear the changed artefacts themselves.
            Off by default: usually they have just been rewritten.

    Returns:
        The names of everything that was actually removed.
    """
    steps, metas, files = dependencies.invalidation_plan(
        changed, keep, include_changed=include_changed)
    removed: list[str] = []
    for name in steps:
        if context.store.get_step(name) is not None:
            removed.append(name)
        context.store.clear_step(name)
    for name in metas:
        if context.store.get_meta(name) is not None:
            removed.append(name)
        context.store.clear_meta(name)
    for name in files:
        gone = [_remove_artefact_path(path)
                for path in dependencies.paths_for(name, context.paths)]
        if any(gone):
            removed.append(name)
    if removed:
        logger.info(t("log_derived_removed"),
                    ", ".join(changed), ", ".join(sorted(removed)))
    else:
        logger.info(t("log_derived_nothing"),
                    ", ".join(changed))
    return tuple(removed)


def invalidate_timing(context: AppContext) -> None:
    """Remove the timing and everything after it (B99/B113/B311).

    Used when the karaoke text changes structurally: transcription and
    alignment stay valid, but the timing has to be made again.
    """
    invalidate(context, ["timing"], include_changed=True)


def transcript_fingerprint(segments) -> str:
    """One value that says whether two transcriptions are the same text.

    B549: written into the step beside the cache key, so that a run
    after an emptied cache can tell "I had to transcribe again" apart
    from "the answer is different". Only the first of those is a reason
    to throw away the user's coupling and timing.

    Over the serialised segments, so the words and their times count -
    a text that reads the same but sits at other moments is another
    transcription and the coupling on it is worth nothing.
    """
    import hashlib
    import json as _json

    try:
        # Sorted, because chunked transcription fills its result in the
        # order the threads finish and equal starts then land either way
        # round. Sorting takes that out; what it cannot take out is a
        # run that picks a DIFFERENT word on a tie, and then the answer
        # really is another text. That fails towards throwing the
        # coupling away, which is what happened before this at every
        # single run.
        payload = _json.dumps(
            sorted(whisper.segments_to_dicts(segments),
                   key=lambda item: _json.dumps(item, sort_keys=True,
                                                ensure_ascii=False)),
            sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):  # never let a fingerprint break a run
        logger.exception(t("log_transcript_fingerprint_failed"))
        return ""
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def invalidate_after_fresh_transcript(context: AppContext,
                                      track: str) -> None:
    """Clear what is based on the OLD transcription of ``track`` (B265).

    Run "1.1. Detecteer woorden" again and if that yields a really new
    transcription (no cache hit: other audio/model/language/prompt), then
    everything built on the previous text lapses: the manual word
    couplings point at transcript indices that no longer have anything to
    do with the new text, and the alignment, sentence coupling and timing
    are built on it.

    Per TRACK (B311): up to and including v0.97 a fresh KARAOKE
    transcription also threw away the manual word couplings, while those
    refer exclusively to the original. The derivation chain knows the
    difference, so the residual-vocals track no longer costs the user his
    handiwork on the original.

    Is only called on a really new transcription (not on a cache hit): an
    unchanged redetection must precisely not throw away the manual
    couplings of the user.
    """
    invalidate(context, [f"whisper_{track}"])


#: Per source artefact the step in which its fingerprint is kept and the
#: function that gives the file (B311). The audio tracks are not in here:
#: their sha1 is already kept by ``prepare_track`` in ``source_<track>``,
#: and that entry is checked in the same way (see ``_source_files``).
_FINGERPRINTED: dict[str, str] = {
    "input:original": "source_original",
    "input:karaoke": "source_karaoke",
    "input:lyrics": "source_lyrics",
    "input:karaoke_text": "source_karaoke_text",
    "input:logo": "source_logo",
}


def _source_file(context: AppContext, source: str) -> Path | None:
    """The file on disk belonging to a source artefact, if it exists."""
    from . import karaoke_text
    input_dir = context.paths.input_dir
    if source == "input:lyrics":
        path = input_dir / song_text.LYRICS_FILENAME
        return path if path.exists() else None
    if source == "input:karaoke_text":
        path = input_dir / karaoke_text.FILENAME
        return path if path.exists() else None
    if source == "input:logo":
        found = sorted(input_dir.glob("logo.*"))
        return found[0] if found else None
    track = (TRACK_ORIGINAL if source == "input:original"
             else TRACK_KARAOKE)
    return filesystem.find_audio_file(input_dir, track)


def _config_signature(config: AppConfig) -> dict[str, str]:
    """A short fingerprint per settings group (B311).

    Settings steer derivatives just as hard as the input files do:
    another Whisper model gives another transcription, another damping
    gives another karaoke wav. Only the Whisper model and the language
    were covered (via the transcription cache key) - turning
    ``forced_alignment`` off, for instance, changed the word times in a
    cached transcription without anything noticing.
    """
    import hashlib

    def digest(value: Any) -> str:
        text = json.dumps(value, sort_keys=True, default=str)
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

    advanced = config.advanced
    timing_fields = {
        key: getattr(advanced, key) for key in (
            "vocal_analysis", "phonetic_timing", "block_anchor_barrier",
            "anchor_weight_syllable", "anchor_weight_high",
            "anchor_weight_word", "anchor_weight_onset")}
    return {
        "config:whisper": digest(asdict(config.whisper)),
        "config:forced_alignment": digest(advanced.forced_alignment),
        # B442: switching the chunking on or off gives a different
        # transcription, so everything derived from it has to go - the
        # same reasoning as the forced alignment above.
        "config:chunked": digest(advanced.chunked_transcription),
        "config:analysis": digest(asdict(config.analysis)),
        "config:cluster": digest(asdict(config.cluster)),
        "config:align": digest(asdict(config.align)),
        "config:karaoke": digest(asdict(config.karaoke)),
        "config:timing": digest(timing_fields),
        "config:video": digest(asdict(config.video)),
        # B361: a switched-off model changes the derived timing just as
        # hard as any other setting. The EFFECTIVE state counts (so
        # including the defaults from the register), not only what
        # happens to sit in config.json.
        "config:models": digest(_model_states(config)),
    }


def _model_states(config: AppConfig) -> dict[str, bool]:
    """The effective on/off state of every model (B361)."""
    from . import model_register

    overrides = dict(getattr(config, "models", {}) or {})
    return {model.code: bool(overrides.get(model.code, model.default_on))
            for model in model_register.register()}


def unmigrated_texts(context: AppContext) -> tuple[str, ...]:
    """The old text file names still lying in this project (B555).

    A project is unmigrated when the old name is there and the new one
    is not. Both present is not this function's business: the migration
    leaves that case alone on purpose, and the program simply reads the
    new one.

    Returns the OLD names, so the message can say what to look for.
    """
    from . import karaoke_text

    pairs = (("songtekst.txt", song_text.LYRICS_FILENAME),
             ("karaoketekst.txt", karaoke_text.FILENAME))
    directory = context.paths.input_dir
    return tuple(old_name for old_name, new_name in pairs
                 if (directory / old_name).exists()
                 and not (directory / new_name).exists())


def sync_input_changes(context: AppContext) -> tuple[str, ...]:
    """Notice that a source has changed outside the app, and act (B311).

    The user edits ``lyrics.txt`` in Notepad, drops another
    ``origineel.mp3`` into the folder with Explorer, or turns a setting
    off. Nothing in the program noticed that: the timing, the sentence
    coupling, the manual couplings (which count word POSITIONS) and the
    cluster selection simply stayed and were applied to the new content.

    This function compares the fingerprint of every source with what was
    kept the previous time and removes everything derived from a source
    that has changed. It is called at the start of every step, so that no
    route can bypass it.

    Returns:
        The names of the changed sources.

    Raises:
        PipelineError: If the project still carries the file names from
            before B555. See :func:`unmigrated_texts`.
    """
    # B555: a project that has not been migrated looks, from here, like
    # one whose lyrics have been DELETED - and this function's answer to
    # a deleted source is to throw away everything derived from it. One
    # click on any step button would cost the word coupling, timing.json
    # and timing_auto.json, without a question and without a backup,
    # because the rescue of B407/B429 needs the karaoke text and that is
    # missing under its new name too. So this is the gate: it runs at
    # the head of every step, which is exactly where the refusal has to
    # sit.
    stale = unmigrated_texts(context)
    if stale:
        raise PipelineError(t("err_not_migrated").format(
            names=", ".join(stale)))

    changed: list[str] = []
    for source, step_name in _FINGERPRINTED.items():
        path = _source_file(context, source)
        step = context.store.get_step(step_name) or {}
        known = step.get("sha1")
        if path is None:
            # Source gone: only worth acting on if we knew one.
            if known:
                changed.append(source)
            continue
        current = filesystem.file_sha1(path)
        if known and known != current:
            changed.append(source)

    signature = _config_signature(context.config)
    kept = (context.store.get_step("config_signature") or {}).get("groups")
    if isinstance(kept, dict):
        changed.extend(group for group, value in signature.items()
                       if group in kept and kept[group] != value)

    if changed:
        logger.info(t("log_source_changed"),
                    ", ".join(changed))
        # B407/B429: the hand-made timing is rescued across the
        # invalidation whenever the karaoke text still lines up with it.
        #
        # B407 did this only for a changed karaoke text, and that was too
        # narrow. A user lost an afternoon of hand timing because a MODEL
        # was set differently: ``config:models`` counts as a changed
        # source, the timing hangs off it, and it was gone without a
        # question or a line in the log. A model changes what the
        # AUTOMATIC coupling makes of the song - it says nothing about
        # where the user placed his sentences by hand. The same goes for
        # an edited karaoke track: other audio, same sentences.
        #
        # So: what derives from the change goes (the coupling, the
        # automatic timing, the diagnostics), and the handwork stays,
        # with a line in the log naming the cause. Does the user think
        # the timing has gone stale, then 2.2 makes it anew - that is his
        # call, and now it IS a call.
        rescue = (_timing_across_text_change(context)
                  if _timing_would_go(changed) else None)
        # B451: read the automatic timing BEFORE the invalidation removes
        # it, so the pair can be put back together.
        auto = (_read_auto_timing(context, rescue[0])
                if rescue is not None else None)
        invalidate(context, changed)
        if rescue is not None:
            _write_rescued_timing(context, rescue, changed, auto)
    remember_sources(context)
    return tuple(changed)


def rebuild_auto_timing(context: AppContext, force: bool = False):
    """Make a missing ``timing_auto.json`` again (B463).

    The automatic timing is not handwork: it is what the coupling
    produces, so it can be made again at any moment from the same
    sources - which is exactly what the yardstick does internally on
    every measurement. What it may NOT do is touch ``timing.json``, and
    it does not: that file is not opened here.

    Refuses when the file already exists (unless ``force``) and when the
    number of lines does not match the hand timing - a pair that does
    not match is worse than a missing one, because a missing one is at
    least visible.

    Returns the path written, or ``None``.
    """
    from . import timing as timing_module

    target = context.paths.timing_auto_file
    if target.exists() and not force:
        return None
    hand_path = context.paths.timing_file
    if not hand_path.exists():
        return None
    try:
        hand = timing_module.load_timing(hand_path)
        coupling = build_coupling(context)
    except Exception:  # noqa: BLE001 - rebuilding may never break a step
        logger.exception(t("log_auto_rebuild_failed"))
        return None
    if not coupling or len(coupling["timed"]) != len(hand):
        # B466: with the numbers, because "a different number of lines"
        # says nothing about what to do. Lied_O has 55 hand-timed
        # lines against a karaoke text that now yields 41: the handwork
        # is older than the text and describes lines that no longer
        # exist. That is not something to repair here - writing an
        # automatic file of 41 lines beside a hand file of 55 would give
        # exactly the mismatched pair this refuses to make - but the
        # user does have to be able to see it.
        logger.warning(t("log_auto_rebuild_mismatch"), context.paths.song,
                       len(hand),
                       len(coupling["timed"]) if coupling else 0)
        return None
    onset = context.store.get_meta("vocal_onset_s")
    fresh = timing_module.sanitize_timing(
        coupling["timed"],
        first_start=float(onset) if onset is not None else None,
        song_duration=max(line.end for line in hand) + 5.0,
        active_windows=_vocal_windows(context))
    fresh = _snap_lines_to_onsets(context, fresh)
    try:
        timing_module.save_timing(
            fresh, target, offset=timing_module.load_offset(hand_path),
            project=context.config.song.title, versie=_APP_VERSION)
    except OSError:
        logger.warning(t("log_timing_auto_failed"))
        return None
    logger.info(t("log_auto_rebuilt"), target.name, len(fresh))
    return target


def _read_auto_timing(context: AppContext, like=None):
    """The automatic timing, carried over the same way (B451).

    ``like`` is the rescued hand timing. The automatic timing has to end
    up with exactly the same lines, because the yardstick compares the
    two line by line and gives up on a pair that does not match. So it
    goes through the same ``carry_over`` as the hand timing did: a
    chorus added to the karaoke text costs both of them the same lines.
    Does that not work out, then no automatic timing is written at
    all - a mismatched pair is worse than a missing one, because a
    missing one is at least visible.
    """
    from . import karaoke_text
    from . import timing as timing_module

    path = context.paths.timing_auto_file
    if not path.exists():
        return None
    try:
        lines = timing_module.load_timing(path)
    except (OSError, ValueError, KeyError):
        return None
    if like is None or len(lines) == len(like):
        return lines
    text_path = karaoke_text_path(context)
    if text_path is None:
        return None
    try:
        carried = timing_module.carry_over(
            list(lines), karaoke_text.parse_lines(text_path))
    except Exception:  # noqa: BLE001 - a rescue may never break a step
        logger.exception(t("log_timing_rescue_failed"))
        return None
    return carried if len(carried) == len(like) else None


def _timing_would_go(changed) -> bool:
    """Would this change remove the timing? (B429)"""
    try:
        _steps, _metas, files = dependencies.invalidation_plan(changed, ())
    except KeyError:                       # unknown name: better loud elsewhere
        return False
    return "output:timing" in files


def _timing_across_text_change(context: AppContext):
    """The hand-made timing, adjusted to the new karaoke text (B407).

    Choosing the karaoke text again through the file dialog has always
    kept the timing: :func:`sync_timing_with_text_change` carries the
    text differences through and leaves the line spans alone (B99).
    Editing that same file in Notepad went a completely different way -
    past that carry-through and straight into
    :func:`sync_input_changes`, which simply removed everything derived
    from the karaoke text. Including ``timing.json``, so an afternoon of
    hand-made timing was gone without a question being asked. Two routes
    to the same change, two opposite outcomes; that difference is what
    this repairs.

    It needs no memory of the old text: ``timing.json`` carries the text
    of every line itself, and that IS the old state. Changed lines get
    their syllables split again and spread evenly over the span the line
    already had; unchanged lines are not touched at all.

    Returns:
        ``(lines, offset)`` to write back after the invalidation, or
        ``None`` when there is nothing to rescue (no timing, a different
        number of lines - then the timing really can no longer be right
        and it goes, as before).
    """
    from . import karaoke_text
    from . import timing as timing_module

    path = context.paths.timing_file
    if not path.exists():
        return None
    text_path = karaoke_text_path(context)
    if text_path is None:
        return None
    try:
        new_lines = karaoke_text.parse_lines(text_path)
        timed = list(timing_module.load_timing(path))
        offset = timing_module.load_offset(path)
    except Exception:  # noqa: BLE001 - a rescue may never break a step
        logger.exception(t("log_timing_rescue_failed"))
        return None
    if not timed or not new_lines:
        return None

    # B411: no longer only at an equal number of lines. Lines are matched
    # on their text, so a chorus added at the end costs the four new
    # lines and nothing more.
    result = timing_module.carry_over(timed, new_lines)
    if len(result) != len(new_lines):
        return None
    kept = sum(1 for line, new_line in zip(result, new_lines)
               if line.text == new_line.text
               and any(line.text == old.text for old in timed))
    logger.info(t("log_timing_rescued"), len(result), len(result) - kept)
    return result, offset


def _write_rescued_timing(context: AppContext, rescue,
                          changed=(), auto=None) -> None:
    """Put the rescued timing back after the invalidation (B407/B429).

    B451: and its automatic counterpart with it. ``output:timing`` covers
    ``timing.json`` AND ``timing_auto.json``, so the invalidation takes
    both; the rescue only wrote the first one back. The handwork survived
    and looked fine - but the yardstick needs the PAIR (it measures how
    far the hand moved the automatic timing) and silently skips a project
    that is missing one of the two. Lied_Q and Lied_O had
    disappeared from every measurement that way, without a word
    anywhere.
    """
    from . import timing as timing_module

    lines, offset = rescue
    try:
        timing_module.save_timing(lines, context.paths.timing_file,
                                  offset=offset,
                                  project=context.config.song.title,
                                  versie=_APP_VERSION)
    except OSError:
        logger.warning(t("log_timing_rescue_failed"))
        return
    if auto:
        try:
            timing_module.save_timing(auto, context.paths.timing_auto_file,
                                      offset=offset,
                                      project=context.config.song.title,
                                      versie=_APP_VERSION)
        except OSError:
            logger.warning(t("log_timing_auto_failed"))
    logger.info(t("log_timing_kept"), ", ".join(changed) or "?")


def remember_sources(context: AppContext) -> None:
    """Record the current fingerprints of the sources (B311)."""
    for source, step_name in _FINGERPRINTED.items():
        if step_name in ("source_original", "source_karaoke"):
            continue          # kept by ``prepare_track`` itself
        path = _source_file(context, source)
        if path is None:
            context.store.clear_step(step_name)
            continue
        context.store.set_step(step_name, {
            "path": str(path), "sha1": filesystem.file_sha1(path)})
    context.store.set_step("config_signature",
                           {"groups": _config_signature(context.config)})


def cleanup_after_cancel(context: AppContext) -> None:
    """Clean up the leftovers after an aborted detection/transcription.

    The cache is regenerable and is cleared; the (half-finished)
    transcription and alignment steps are reset, so that a next
    run starts clean.
    """
    filesystem.clean_cache(context.paths.cache_dir)
    for track in TRACKS:
        context.store.clear_step(f"whisper_{track}")
    context.store.clear_step("align")
    logger.info(t("log_cleaned_after_cancel"))


def transcript_cache(context: AppContext, track: str) -> Path:
    """Path to the cached transcription of one track."""
    return context.paths.cache_dir / f"transcription_{track}.json"


#: A run of this many words that all have length zero AND stand at the
#: same moment is Whisper's repetition loop (B334). Measured over eleven
#: projects: eight have no such word at all, two have a single one, one
#: has a run of 3 and the song with the real loop has 34. Four therefore
#: sits in a wide gap - the run of 3 is left alone, because taking it
#: away made that song measurably (if slightly) worse.
_LOOP_MIN_RUN = 4
#: Word length below which a word carries no time at all.
_ZERO_LENGTH_S = 0.001


def _drop_repetition_loop(segments: tuple) -> tuple:
    """Remove Whisper's repetition loop from a transcription (B334).

    When faster-whisper gets stuck it spits out the same word dozens of
    times at the moment its window runs out: measured, 34x "now," all at
    exactly 193.500 s with a confidence of 0.98. The existing
    hallucination checks cannot see that - the confidence is sky-high and
    the word really does occur in the lyrics - but the shape gives it
    away: a word whose start equals its end carries NO time. It can
    therefore never contribute a timing, only become a wrong anchor.

    Dropping it is safe for exactly that reason. It happens on reading,
    so an existing project benefits without Whisper having to run again
    and without the cache file itself being touched.
    """
    result = []
    dropped = 0
    for segment in segments:
        words = list(segment.words or ())
        if len(words) < _LOOP_MIN_RUN:
            result.append(segment)
            continue
        keep = [True] * len(words)
        start = 0
        while start < len(words):
            if words[start].end - words[start].start >= _ZERO_LENGTH_S:
                start += 1
                continue
            stop = start
            while (stop + 1 < len(words)
                   and words[stop + 1].end - words[stop + 1].start
                   < _ZERO_LENGTH_S
                   and abs(words[stop + 1].start - words[start].start)
                   < _ZERO_LENGTH_S):
                stop += 1
            if stop - start + 1 >= _LOOP_MIN_RUN:
                for index in range(start, stop + 1):
                    keep[index] = False
                dropped += stop - start + 1
            start = stop + 1
        if all(keep):
            result.append(segment)
            continue
        kept_words = tuple(w for w, ok in zip(words, keep) if ok)
        if not kept_words:
            continue
        result.append(replace(
            segment, words=kept_words,
            text=" ".join(w.text for w in kept_words)))
    if dropped:
        logger.info(t("log_repetition_loop_dropped"), dropped)
    return tuple(result)


#: Whisper decodes in chunks, and a word that falls exactly on the cut
#: comes out TWICE: a clipped stub at the end of one segment and the
#: whole word at the start of the next - with a capital letter, because
#: that is where a new sentence begins for it, and sometimes misheard
#: because it hears that piece again without its run-up ("Collections"
#: for "reflections"). Measured over two projects, four cases, always
#: with the same shape: the stub is shorter (0.08-0.38 s) AND less
#: certain (0.01-0.25) than its twin. The proof that it is one word:
#: "dreaming" runs 1.31 s and 1.36 s where it does not fall on a cut,
#: and the two pieces together span 1.29 s.
_BOUNDARY_MIN_SIMILARITY = 0.6
#: Only glue back together what is really adjacent. Measured gaps:
#: 0.020, 0.120 and 0.201 s. A fourth case sits at 0.702 s; that stub is
#: 0.08 s at confidence 0.01 and merging it would put 0.7 s of silence
#: inside a word, so that one is deliberately left alone.
_BOUNDARY_MAX_GAP_S = 0.30
_BOUNDARY_STUB_MAX_S = 0.40
_BOUNDARY_STUB_MAX_CONF = 0.30


def _boundary_stub(first: Word, second: Word) -> bool:
    """Is ``first`` the clipped half of ``second`` (B342)?"""
    import difflib

    left = cluster_module.normalize_for_filter(first.text)
    right = cluster_module.normalize_for_filter(second.text)
    if not left or not right:
        return False
    gap = second.start - first.start if second.start < first.end \
        else second.start - first.end
    if not 0.0 <= gap <= _BOUNDARY_MAX_GAP_S:
        return False
    if first.end - first.start > _BOUNDARY_STUB_MAX_S \
            or first.confidence > _BOUNDARY_STUB_MAX_CONF:
        return False
    if first.end - first.start >= second.end - second.start \
            or first.confidence >= second.confidence:
        return False
    return difflib.SequenceMatcher(None, left, right).ratio() \
        >= _BOUNDARY_MIN_SIMILARITY


#: B373: up to this gap two equal words count as ONE word that the
#: segment boundary cut in half. Measured over fourteen projects the
#: distinction falls out with nothing in between: the cut words lie
#: 0.00-0.21 s apart, the real repetitions 0.70-6.56 s. Wider than the
#: old 0.30 therefore, and that is allowed because the lyrics have the
#: last word.
_SPLIT_MAX_GAP_S = 0.35


def _doubled_lyric_keys(lyrics) -> frozenset:
    """Words that stand DIRECTLY after each other in the lyrics (B373).

    That is the only information needed to tell a word cut in two from
    a real repetition, and we already had it lying around. Does "sunday
    sunday" stand nowhere in the lyrics, then two "sunday" next to each
    other in the transcription are not a repetition but one word that
    was cut at the window edge.
    """
    keys = [cluster_module.phonetic_key(w.text) for w in (lyrics or ())]
    return frozenset(a for a, b in zip(keys, keys[1:]) if a and a == b)


def _boundary_split(stub: Word, whole: Word, doubled: frozenset) -> bool:
    """Is this one word cut in two, according to the lyrics? (B373)"""
    left = cluster_module.phonetic_key(stub.text)
    right = cluster_module.phonetic_key(whole.text)
    if not left or not right or left != right:
        return False
    if left in doubled:
        return False           # the lyrics really do sing it twice
    gap = whole.start - stub.end
    return -0.05 <= gap <= _SPLIT_MAX_GAP_S


def _merge_boundary_duplicates(segments: tuple, lyrics=None) -> tuple:
    """Glue a word that was cut in two by a segment boundary back
    together (B342/B373).

    The stub disappears from the previous segment and the whole word
    takes over its start, so the coupling sees one word and the timing
    gets the real onset. Kept on purpose: the TEXT of the surviving word
    (that is the one Whisper heard with the most confidence) and its
    confidence.

    B373: with ``lyrics`` alongside, the LYRICS decide. The closing
    word of a segment was measured to be half as reliable as any other
    word (0.42 against 0.70 over 347 boundaries), and stacking four
    thresholds on top of that let the real cases fall just outside:
    "so"/"so" tripped over a confidence of 0.36 against a limit of
    0.30. Does the word not stand twice in the lyrics, then it is one
    word that has been cut through - however certain or however long
    the piece is. Without ``lyrics`` the old, cautious test keeps
    applying.
    """
    doubled = _doubled_lyric_keys(lyrics) if lyrics else None
    result = list(segments)
    merged = 0
    for index in range(len(result) - 1):
        left, right = result[index], result[index + 1]
        if not left.words or not right.words:
            continue
        stub, whole = left.words[-1], right.words[0]
        by_the_lyrics = (doubled is not None
                         and _boundary_split(stub, whole, doubled))
        if not by_the_lyrics and not _boundary_stub(stub, whole):
            continue
        kept = left.words[:-1]
        if not kept:      # the stub was the whole segment: leave it be
            continue
        result[index] = replace(
            left, words=kept, end=kept[-1].end,
            text=" ".join(w.text for w in kept))
        widened = (replace(whole, start=stub.start),) + right.words[1:]
        result[index + 1] = replace(
            right, words=widened, start=min(right.start, stub.start))
        merged += 1
    if merged:
        logger.info(t("log_boundary_merged"), merged)
    return tuple(result)


#: A word of twenty milliseconds that Whisper itself scores at 0.004 is
#: not a word (B343). Measured over Lied D: of 270 words eleven are
#: shorter than 0.06 s, and those fall into two groups with nothing in
#: between - five with a confidence of 0.000-0.006 ('I', 'I', 'I', 'of',
#: 'I') and six ordinary short words with 0.11-0.95 ('a', 'it', 'of').
#: Duration alone therefore says nothing: 'a' of 0.040 s scores 0.952.
#: The two conditions together do separate them. It hurts because such a
#: word lands exactly on a line boundary, where the coupling takes the
#: first word as the start of the sentence: four of those five became a
#: sentence start and one demonstrably cost a correction of 2.11 s.
_PHANTOM_MAX_S = 0.05
_PHANTOM_MAX_CONF = 0.01


def _drop_phantom_words(segments: tuple) -> tuple:
    """Remove words that carry neither time nor confidence (B343)."""
    result = []
    dropped = 0
    for segment in segments:
        words = tuple(segment.words or ())
        if not words:
            result.append(segment)
            continue
        kept = tuple(w for w in words
                     if not (w.end - w.start <= _PHANTOM_MAX_S
                             and w.confidence <= _PHANTOM_MAX_CONF))
        if len(kept) == len(words):
            result.append(segment)
            continue
        dropped += len(words) - len(kept)
        if not kept:
            continue
        result.append(replace(
            segment, words=kept, start=kept[0].start, end=kept[-1].end,
            text=" ".join(w.text for w in kept)))
    if dropped:
        logger.info(t("log_phantom_words_dropped"), dropped)
    return tuple(result)


def load_segments(context: AppContext, track: str) -> tuple[Segment, ...]:
    """Load the cached transcription of one track.

    THE reading path. Anything that reasons about words - the coupling,
    the alignment, the checks, every measurement - has to come through
    here, because the file on disk is not the list the program works
    with: three repairs run over it below and they remove words. At
    "Lied R" that is two ("in" at position 27 and "I" at 144), so the
    raw file has 291 words and the program 289. Number a coupling on the
    raw file and everything after position 27 is one place out and
    everything after 144 two - which looks exactly like drift and is
    not. That cost the user a set of eighty-two correct couplings
    (B518), and ``tests/test_v0148.py`` now guards it.

    Raises:
        PipelineError: If step 1 has not yet been executed.
    """
    cache_file = transcript_cache(context, track)
    if (context.store.get_step(f"whisper_{track}") is None
            or not cache_file.exists()):
        raise PipelineError(t("err_no_transcription").format(track=track))
    # B334/B342/B343: the only reading path, so every existing project is
    # cleaned up too, without Whisper having to run again.
    # B373: the lyrics travel along, because they decide whether two
    # equal words on a segment boundary are one cut word or a real
    # repetition.
    return _drop_phantom_words(_merge_boundary_duplicates(
        _drop_repetition_loop(whisper.load_segments(cache_file)),
        lyrics=_lyrics_for_boundaries(context)))


def _lyrics_for_boundaries(context: AppContext):
    """The lyrics words, or ``None`` if there are no lyrics."""
    path = context.paths.input_dir / song_text.LYRICS_FILENAME
    if not path.exists():
        return None
    try:
        return _effective_lyrics(context, path)
    except Exception:  # noqa: BLE001 - the read path may never trip here
        logger.exception(t("log_lyrics_alignment_failed"))
        return None


def run_analysis(context: AppContext, track: str) -> AnalyseResult:
    """Step 2: analysis and phonetic clustering of one track.

    Analysis of the karaoke track traces residual words that have
    stayed behind in the karaoke version. The cluster selection itself
    is done by the interface and is kept with
    :func:`save_cluster_selection`.
    """
    segments = load_segments(context, track)
    config = context.config
    output_dir = track_output_dir(context, track)

    stats = analysis.run_analysis(segments, config.analysis, output_dir)
    context.store.set_step(f"analysis_{track}", asdict(stats))

    found = cluster_module.build_clusters(segments, config.cluster)
    if track == TRACK_ORIGINAL:
        aligned = _lyrics_alignment(context, segments)
        if aligned is not None:
            song_text.write_report(aligned,
                                   output_dir / "lyrics_alignment.txt")
            found = song_text.relabel_clusters(found, aligned)
    json_path, html_path = cluster_module.write_outputs(found, segments,
                                                        output_dir)
    suggested = tuple(cluster_module.suggest_clusters(
        found, config.karaoke.search_words,
        config.cluster.similarity_threshold))
    return AnalyseResult(track=track, stats=stats, clusters=found,
                         json_path=json_path, html_path=html_path,
                         suggested=suggested)


def run_analyses(context: AppContext) -> dict[str, AnalyseResult]:
    """Step 2 for all ticked tracks."""
    sync_input_changes(context)          # B311
    return {track: run_analysis(context, track)
            for track in enabled_tracks(context)}


def save_cluster_selection(context: AppContext, track: str,
                           selection: Sequence[int], json_path: Path,
                           total: int) -> None:
    """Keep the chosen clusters of one track.

    A different choice means different damping, so the already processed
    karaoke and its export no longer match (B311). Only on a REAL change:
    the interface saves the selection again on every redraw, and throwing
    away a processed wav that is still correct costs the user time for
    nothing.
    """
    previous = context.store.get_step(f"clusters_{track}") or {}
    changed = (list(previous.get("selection") or []) != list(selection)
               or str(previous.get("file") or "") != str(json_path))
    context.store.set_step(f"clusters_{track}", {
        "selection": list(selection),
        "file": str(json_path),
        "cluster_count": total,
    })
    logger.info(t("log_cluster_selection_saved"), track,
                list(selection))
    if changed and previous:
        invalidate(context, [f"clusters_{track}"])


def selection_exists(context: AppContext, track: str) -> bool:
    """Is a non-empty cluster selection kept for this track?"""
    step = context.store.get_step(f"clusters_{track}")
    return step is not None and bool(step.get("selection"))


def has_transcription(context: AppContext) -> bool:
    """Has step 1 (Detect words) been executed for a ticked track? (B134)"""
    return any(context.store.get_step(f"whisper_{track}") is not None
               for track in enabled_tracks(context))


def has_analysis(context: AppContext) -> bool:
    """Has step 2 (Analysis) been executed for a ticked track? (B134)"""
    return any(context.store.get_step(f"clusters_{track}") is not None
               for track in enabled_tracks(context))


def selected_clusters(context: AppContext,
                      track: str) -> tuple[cluster_module.Cluster, ...]:
    """Load the chosen clusters of one track.

    Raises:
        PipelineError: If there is no (valid) selection.
    """
    step = context.store.get_step(f"clusters_{track}")
    if step is None or not step.get("selection"):
        raise PipelineError(
            t("err_no_cluster_selection_track").format(track=track))
    cluster_file = Path(step["file"])
    if not cluster_file.exists():
        raise PipelineError(
            t("err_cluster_file_missing").format(file=cluster_file))
    all_clusters = cluster_module.clusters_from_dicts(
        json.loads(cluster_file.read_text(encoding="utf-8")))
    selection = set(step["selection"])
    selected = tuple(cluster for cluster in all_clusters
                     if cluster.id in selection)
    if not selected:
        raise PipelineError(
            t("err_selection_mismatch").format(track=track))
    return selected


def stored_wav(context: AppContext, stem: str) -> Path:
    """Give the wav path of a prepared track.

    Raises:
        PipelineError: If step 1 has not yet been executed.
    """
    step = context.store.get_step(f"source_{stem}")
    if step is not None:
        path = Path(step.get("wav", ""))
        if path.exists():
            return path
    raise PipelineError(t("err_no_prepared_audio"))


def run_alignment(context: AppContext) -> tuple[align.OffsetRegion, ...]:
    """Step 3: align original and karaoke (determine offset regions).

    If the karaoke was made from the original (Demucs instrumental),
    both share exactly the same timeline and the alignment is skipped
    with a fixed offset 0 (B81).
    """
    sync_input_changes(context)          # B311
    if context.store.get_meta("karaoke_from_original"):
        duration = _karaoke_duration(context) or 1.0
        regions = (align.OffsetRegion(start=0.0, end=max(duration, 1.0),
                                      offset=0.0, confidence=1.0),)
        logger.info(t("log_alignment_skipped"))
    else:
        original_wav = stored_wav(context, TRACK_ORIGINAL)
        karaoke_wav = stored_wav(context, TRACK_KARAOKE)
        regions = align.determine_offsets(
            original_wav, karaoke_wav, context.config.align)
    context.store.set_step("align", {
        "regions": align.regions_to_dicts(regions),
    })
    report_path = context.paths.output_dir / "alignment.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(align.regions_to_dicts(regions), indent=2,
                   ensure_ascii=False) + "\n",
        encoding="utf-8")
    return regions


def alignment_regions(context: AppContext) -> tuple[align.OffsetRegion, ...]:
    """Load the offset regions from step 3.

    Raises:
        PipelineError: If step 3 has not yet been executed.
    """
    step = context.store.get_step("align")
    if step is None:
        raise PipelineError(t("err_no_alignment"))
    return align.regions_from_dicts(step["regions"])


def run_karaoke(context: AppContext) -> KaraokeResult:
    """Step 4: damp selected clusters in the karaoke version.

    Clusters from the original are projected via the alignment (step
    3); clusters from the karaoke track itself (residual words) are
    already on the karaoke timeline and are damped without projection.
    """
    sync_input_changes(context)          # B311
    # B428: an empty selection is allowed as long as there IS something
    # to do. Damping and "back from the original" are two different jobs
    # that happen to share this step: the first needs clusters, the
    # second does not. Demanding a selection meant that restoring one
    # toeter forced the user to tick clusters he did not want damped -
    # and on a fresh transcription even to walk through step 3 again for
    # a selection that would then be thrown away.
    if not (selection_exists(context, TRACK_ORIGINAL)
            or selection_exists(context, TRACK_KARAOKE)
            or restore_fragments(context)):
        raise PipelineError(t("err_no_cluster_selection"))
    karaoke_wav = stored_wav(context, TRACK_KARAOKE)
    settings = context.config.karaoke

    combined: list[karaoke.DampingInterval] = []
    if selection_exists(context, TRACK_ORIGINAL):
        regions = _ensure_alignment(context)
        selected_original = selected_clusters(context, TRACK_ORIGINAL)
        combined.extend(karaoke.find_intervals(selected_original, regions,
                                               settings))
        combined.extend(_lyrics_damping_intervals(context, selected_original,
                                                  regions, settings))
    if selection_exists(context, TRACK_KARAOKE):
        combined.extend(karaoke.find_intervals(
            selected_clusters(context, TRACK_KARAOKE), (), settings))
    all_intervals = karaoke.merge_intervals(combined)
    if not all_intervals and not restore_fragments(context):
        raise PipelineError(t("err_no_fragments"))
    exclusions = fragment_exclusions(context)
    intervals = tuple(interval for interval in all_intervals
                      if not any(_overlaps(interval.start, interval.end,
                                           start, end)
                                 for start, end in exclusions))
    if not intervals:
        logger.warning(t("log_all_excluded"))
    # B282: kept "back from original" fragments survive a
    # step-4 rerun (new cluster selection) and are applied here AFTER the
    # damping again, so that they do not disappear.
    restore = restore_fragments(context)
    karaoke_props = ffmpeg.probe(karaoke_wav)
    restore_prepared = _prepared_restore_intervals(
        context, restore, karaoke_props.sample_rate or 44_100)
    output_wav = context.paths.cache_dir / "karaoke_edited.wav"
    karaoke.apply_damping(karaoke_wav, intervals, settings, output_wav,
                         restore_intervals=restore_prepared)
    context.store.set_step("karaoke", {
        "wav": str(output_wav),
        "intervals": karaoke.intervals_to_dicts(intervals),
        "all_intervals": karaoke.intervals_to_dicts(all_intervals),
    })
    return KaraokeResult(intervals=intervals, all_intervals=all_intervals,
                         output_wav=output_wav, restore_intervals=restore)


def drift_ms(regions) -> float:
    """How much the offset runs off over the song, in milliseconds.

    Big difference = drift (one track runs faster/slower).
    """
    if not regions:
        return 0.0
    offsets = [region.offset for region in regions]
    return (max(offsets) - min(offsets)) * 1000.0


def collapse_alignment(context: AppContext) -> None:
    """Replace the alignment by one fixed (global) offset.

    Used when the user does NOT want drift correction: all
    regions are merged into one with the best fitting offset.
    """
    step = context.store.get_step("align")
    if step is None or not step.get("regions"):
        return
    regions = align.regions_from_dicts(step["regions"])
    best = max(regions, key=lambda r: r.confidence)
    total_end = max(r.end for r in regions)
    single = align.OffsetRegion(start=0.0, end=total_end,
                                offset=best.offset,
                                confidence=best.confidence)
    context.store.set_step("align", {
        "regions": align.regions_to_dicts((single,))})
    logger.info(t("log_alignment_collapsed"), best.offset * 1000)


def ensure_alignment(
        context: AppContext) -> tuple[align.OffsetRegion, ...]:
    """Give the alignment; make it automatically (again) if it is missing.

    First prepares the audio if needed (after a cache clearing the
    wav conversions are gone). This way no separate 'Align' button is
    needed anymore.
    """
    try:
        return alignment_regions(context)
    except PipelineError:
        logger.info(t("log_no_alignment"))
        prepare_track(context, TRACK_ORIGINAL)
        prepare_track(context, TRACK_KARAOKE)
        return run_alignment(context)


_ensure_alignment = ensure_alignment  # old name keeps working


#: Short function words that glue a hallucination segment such as
#: "ZANG EN MUZIEK" together (B258). They do not count when determining
#: whether a segment is entirely hallucination: only the meaning-bearing
#: words must be hallucination. A separate, small list - not added to
#: ``cluster.HALLUCINATIONS`` itself, so as to have no influence on the
#: sound clustering/damping (that set filters n-grams, and treating
#: "en"/"de" as a hallucination word could make correct sounds there
#: disappear).
_HALLUCINATION_FILLERS: frozenset[str] = frozenset({"en", "de", "het", "een"})

#: Extra meaning-bearing words that can point to an instrumental outro
#: notice (e.g. "ZANG EN MUZIEK", B258) if they also really occur
#: nowhere in the lyrics of this song (see
#: ``_word_in_lyrics``). Deliberately not added to ``cluster.HALLUCINATIONS``
#: itself: that would also treat "zang" as a hallucination in the sound
#: clustering/damping, and that check has no lyrics context to test
#: whether the word really occurs there.
_HALLUCINATION_SEGMENT_WORDS: frozenset[str] = frozenset({"zang"})


def _language_words(language: str, kind: str) -> frozenset[str]:
    """The word list of a language, shipped plus collected (B337).

    The lists used to be one fixed, Dutch set while most originals are
    English or French. They now live with the language itself
    (``phonetics.LANGUAGES`` and ``languages/<code>.json``), so a
    language that appears anywhere brings its own artefacts along - and
    a language nobody has filled in yet simply has none.
    """
    from . import phonetics
    words = phonetics.word_list(language, kind)
    if kind == "fillers":
        return words or _HALLUCINATION_FILLERS
    return words | _HALLUCINATION_SEGMENT_WORDS

#: Minimum phonetic similarity to count a word as "occurs in the
#: lyrics" in the hallucination check (B258). Well below the usual
#: match thresholds of the alignment itself: this only has to
#: distinguish roughly "is not there at all" from "is there/resembles
#: it", not be a precise word-for-word coupling.
_LYRICS_PRESENCE_SIM = 0.75


#: Lower bound for the broad, song-wide hallucination check (B285): a
#: segment of which all core words match the lyrics weakly (< this
#: threshold) is suspect - also if none of the words is on a fixed
#: hallucination list (such as "Heerlijke Heer" after a long
#: transcription silence). Wider than ``_LYRICS_PRESENCE_SIM`` (0.75):
#: here it does not have to be established exactly that it "occurs",
#: only that it "does not resemble it at all".
_SEGMENT_HALLUCINATION_MATCH_FLOOR = 0.65
#: Only let the broad check weigh in from this number of core words: with
#: one short core word there is too little phonetic material to establish
#: reliably "belongs nowhere with the lyrics", so then only the
#: fixed-word-list check (above) remains.
_SEGMENT_HALLUCINATION_MIN_CORE_WORDS = 2

#: B514: a runaway loop. Whisper sometimes gets stuck on a repetition
#: and does not come out of it: at "Lied_R2" (Korean) it produced ONE
#: word of 223 characters that ran from 116.8 to 143.8 seconds -
#: twenty-seven seconds, over the whole second chorus. And it slipped
#: through every check, because the broad one needs at least two core
#: words and this segment has exactly one. The safety valve "too little
#: material to judge" let the worst case through.
#:
#: What this rule says is NOT "nothing was sung here". The loop
#: demonstrably starts on real singing - the user recognised his four
#: repeated shouts in it. What it says is that one word of twenty-seven
#: seconds carries no usable word TIMES: where in those seconds those
#: shouts lie cannot be derived from it. So it is worthless for the
#: coupling and for the timing, and dropping it turns it into an honest
#: hole instead of twenty-seven seconds of false text. A hole is
#: something the next attempt can go looking for (B515).
#:
#: Two signals. A word with more letters than any word has is one on its
#: own - both measured loops had well over two hundred ("D.O.D.O..." 223,
#: "La-da-da-da..." 323). Length in TIME only counts together with a
#: text that is already long, because a held note is exactly a word that
#: lasts long and is short in letters: "aaaaah" of nine seconds is
#: singing, not a loop, and dropping that would be the cure killing the
#: patient.
_RUNAWAY_FACTOR = 8.0
_RUNAWAY_MIN_S = 8.0
_RUNAWAY_LETTERS = 60
_RUNAWAY_LONG_LETTERS = 20
#: How much of a segment the loop has to fill before the whole segment
#: goes. A segment that is mostly loop says nothing usable any more; one
#: long word between nine good ones must not take those nine with it.
_RUNAWAY_SHARE = 0.6


def _median_word_seconds(segments: Sequence) -> float:
    """The usual length of a word in this song (B514), 0.0 if unknown."""
    lengths = [float(word.end) - float(word.start)
               for seg in segments for word in (seg.words or ())
               if word.end is not None and word.start is not None
               and float(word.end) > float(word.start)]
    return statistics.median(lengths) if len(lengths) >= 8 else 0.0


def runaway_words(seg, middle: float) -> list:
    """The words of ``seg`` that are a runaway loop (B514).

    Without a median (a song with barely any word times) the time signal
    is dropped entirely and only the letter count remains - the same
    restraint ``held_transcript_words`` shows when it has too little to
    measure against.
    """
    limit = max(_RUNAWAY_MIN_S, _RUNAWAY_FACTOR * middle) if middle > 0 \
        else None
    out = []
    for word in (seg.words or ()):
        text = str(word.text or "").strip()
        span = (float(word.end) - float(word.start)
                if word.end is not None and word.start is not None else 0.0)
        long_in_time = (limit is not None and span >= limit
                        and len(text) >= _RUNAWAY_LONG_LETTERS)
        if long_in_time or len(text) >= _RUNAWAY_LETTERS:
            out.append(word)
    return out


def _runaway_share(seg, loop: Sequence) -> float:
    """How much of ``seg`` the loop fills (B514)."""
    span = float(seg.end) - float(seg.start)
    if span <= 0:
        return 1.0
    inside = sum(float(w.end) - float(w.start) for w in loop
                 if w.end is not None and w.start is not None)
    return inside / span
#: Whisper's own word confidence must be at or above this bound for EVERY
#: core word before the broad check may drop a segment (B285): a word that
#: Whisper itself was already not sure of is precisely the sign of a
#: hallucination (e.g. "Heerlijke" at 0.34 between otherwise high
#: scoring neighbouring words) - the LOWEST confidence in the segment
#: counts, no average, otherwise one certain word suppresses the doubt
#: about the rest. Segments without word confidence (e.g. a text-only
#: fallback) do not enjoy this protection.
_SEGMENT_HALLUCINATION_CONF_CEILING = 0.6

#: Minimum similarity for a coupled lyrics word to count as an ANCHOR in
#: the position-aware hallucination check (B307). Only strong couplings
#: may fix a position: a weak coupling can itself be the mistake and
#: would then pin the window in the wrong place.
_POSITION_ANCHOR_SIM = 0.80

#: The lyrics window around a suspect segment is widened to at least
#: this many words (B307). Between two anchors lying close together the
#: window is otherwise only one or two words long, and then almost every
#: segment "matches nothing" - a false accusation. Twelve words is
#: roughly two song lines: wide enough to be forgiving, narrow enough
#: that the outro of a song is not compared with the chorus. Measured
#: over the real project data the outcome stays the same from 1 up to
#: and including 16 words; only from about 25 words does the check start
#: to let real hallucinations ("Thank you.") through again.
_POSITION_WINDOW_MIN_WORDS = 12

#: From this length a hole in the transcription counts as "Whisper
#: simply produced nothing here" (B308) instead of as an uncoupled word
#: with some other cause. Half a song line is too short for that
#: judgement; four seconds is longer than a normal pause between two
#: lines.
_TRANSCRIPTION_GAP_MIN_S = 4.0


def _word_in_lyrics(word: str, lyric_keys: frozenset[str]) -> bool:
    """Does ``word`` occur (phonetically) somewhere in the lyrics? (B258)

    Used to determine whether a hallucination-suspect word ("zang",
    "muziek") happens to be really sung in THIS song - in that case it
    may not be thrown away as a hallucination, even though it is on the
    signal word list.

    Only for that fixed signal word list therefore, with the strict
    threshold ``_LYRICS_PRESENCE_SIM``. The broader song-wide check
    (B285) does NOT use this function but goes via ``_best_lyrics_match``
    with its own, more lenient threshold. There was a ``floor``
    parameter here that did suggest that but was never called other than
    with the default; it is gone, so that it is clear which threshold
    belongs where (B292).
    """
    key = cluster_module.phonetic_key(word)
    if not key:
        return False
    return any(cluster_module.similarity(key, lk) >= _LYRICS_PRESENCE_SIM
               for lk in lyric_keys)


#: Minimum length of a phonetic key to count in the broad
#: hallucination check (B285). Short words such as "heer" lose both the
#: 'h' and the 'r' when phoneticised (``cluster._DROPPED``) and then
#: sometimes keep only one letter ("e") - just like e.g. the lyrics word
#: "E" (from "E viva Espagna"). Two such one-letter keys are always
#: identical, regardless of how the words sound, so without this lower
#: bound almost every short word would "match" by chance and make the
#: broad check useless.
_MIN_BROAD_MATCH_KEY_LEN = 2


def _best_lyrics_match(word: str, lyric_keys: frozenset[str]) -> float:
    """Best phonetic similarity of ``word`` with the lyrics (B285).

    ``0.0`` if there are no lyrics, or the word yields no usable phonetic
    key (e.g. empty after normalising, or too short to compare
    reliably - see ``_MIN_BROAD_MATCH_KEY_LEN``).
    """
    key = cluster_module.phonetic_key(word)
    if len(key) < _MIN_BROAD_MATCH_KEY_LEN or not lyric_keys:
        return 0.0
    return max((cluster_module.similarity(key, lk) for lk in lyric_keys),
               default=0.0)


#: How often a short word has to be repeated inside one segment before
#: it counts as a chant instead of a hallucination (B455).
_CHANT_REPEATS = 3

#: And how short such a word is. "la", "na", "oe", "hey" - anything
#: longer is a real word and gets judged on its own merits.
_CHANT_MAX_LETTERS = 4


def _is_chant(core_words) -> bool:
    """Is this segment one short word, sung over and over (B455)?

    Whisper's hallucinations are plausible SENTENCES - "Ondertiteling
    door...", "Heerlijke Heer, Heerlijke Heer". A row of the same short
    syllable is the opposite of that shape, and it is exactly what a
    carnival song is full of: la-la-la, na-na-na, oe-oe-oe. Those were
    being thrown out because the broad check (B285) asks "does any of
    these words resemble the lyrics" and "la" scores 0.50 against
    "lang" - just under the floor.
    """
    words = [w for w in core_words if w]
    if len(words) < _CHANT_REPEATS:
        return False
    unique = set(words)
    return (len(unique) == 1
            and len(next(iter(unique))) <= _CHANT_MAX_LETTERS)


def _filter_hallucinations(
    segments: tuple, lyrics=None, dropped_out: list | None = None,
    extra_keys=None, song_wide: bool = True,
) -> tuple:
    """Remove segments that consist entirely of Whisper hallucinations.

    On instrumental parts Whisper often writes "MUZIEK",
    "Ondertiteling", etc. Such segments may not become an anchor for the
    lyrics alignment and timing (they caused e.g. a first sentence at
    28.6 s because a "MUZIEK" segment stood there, B141). Whisper glues
    this kind of outro hallucination together with a function word now
    and then (e.g. "ZANG EN MUZIEK"); those function words ("en", "de",
    ...) do not count when determining whether the segment is entirely
    hallucination, as long as at least one real hallucination word is in
    it (B258).

    Words such as "zang"/"muziek" can also simply really be sung. Pass
    ``lyrics`` (the lyrics words of this song) along therefore: a word
    from ``_HALLUCINATION_SEGMENT_WORDS`` only counts as a hallucination
    signal if it occurs (phonetically) nowhere in the lyrics. Words from
    ``cluster.HALLUCINATIONS`` itself ("muziek", "ondertiteling", ...)
    do always keep counting, regardless of the lyrics - those are
    generic Whisper artefacts, not words that are to be expected in a
    carnival parody.

    In addition (B285) a broader, song-wide check: also without a word
    standing on a fixed hallucination list, a segment can be a
    hallucination - e.g. after a long silence in the transcription
    Whisper sometimes hallucinates a plausible sounding but completely
    invented sentence ("Heerlijke Heer, Heerlijke Heer."). Such a
    segment is dropped if (a) there are at least
    ``_SEGMENT_HALLUCINATION_MIN_CORE_WORDS`` core words, (b) none of
    them matches the lyrics even reasonably
    (``_SEGMENT_HALLUCINATION_MATCH_FLOOR``), and (c) Whisper's own
    lowest word confidence in the segment stays below
    ``_SEGMENT_HALLUCINATION_CONF_CEILING``. Point (c) is a safety net: a
    segment of which Whisper itself was sure of every word we leave
    standing, even though it happens not to match the lyrics - that can
    be an ad-lib or creative deviation, not a hallucination. Without
    lyrics (``lyrics`` empty/``None``) we skip this broader check
    entirely: then there is nothing to set "matches nothing" against and
    it would hit home too easily.

    ``song_wide=False`` switches off exactly the two judgements this
    function is named after in the register - the word list that only
    counts outside the lyrics (B258) and the song-wide match floor
    (B285). What stays is what has nothing to do with them and happens
    to live in the same function: the fixed list of Whisper artefacts
    (B141, "MUZIEK", "Ondertiteling") and the runaway repetition (B514).
    B536 found that out the hard way: switching the model off took two
    ideas with it that had been measured apart from it and were good,
    and then the number that decided the switch was the average of four
    things instead of two.
    """
    kept = []
    dropped = 0
    median_word = _median_word_seconds(segments)          # B514
    lyric_keys = frozenset(
        cluster_module.phonetic_key(w.text) for w in lyrics) if lyrics \
        else frozenset()
    # B458/B464: the karaoke text is NOT thrown in with the lyrics here.
    # Widening the general match floor with the words of the parody made
    # almost any invented segment find something above 0.65 somewhere.
    # And ``extra_keys`` is no longer "every word of both texts" but
    # only the syllables those texts REPEAT back to back - the one thing
    # that tells a chant apart from a Whisper loop.
    chant_keys = frozenset(extra_keys or ())
    for seg in segments:
        word_objs = list(seg.words) if seg.words else []
        if word_objs:
            paren = [(cluster_module.normalize_for_filter(w.text),
                     w.confidence) for w in word_objs]
        else:
            paren = [(cluster_module.normalize_for_filter(seg.text), None)]
        paren = [(w, c) for w, c in paren if w]
        # B536: with the model off, a word from the B258 list counts as
        # neither a signal nor a defence - it drops out of the judgement
        # the way a function word does. Exonerating it would have taken
        # B141 with it: "ZANG EN MUZIEK" would then no longer be
        # entirely hallucination and would survive, while plain "MUZIEK"
        # is thrown out. That is the very example the B258 docstring
        # opens with.
        skip = set(_HALLUCINATION_FILLERS)
        if not song_wide:
            skip |= set(_HALLUCINATION_SEGMENT_WORDS)
        core_pairs = [(w, c) for w, c in paren if w not in skip]
        core_words = [w for w, _c in core_pairs]

        def _is_a_hallucination_word(w: str) -> bool:
            # B337: only the unconditional list here. Whether a word from
            # a language list counts depends on the PLACE in the lyrics,
            # and that needs a first alignment - so it happens one round
            # later, in _filter_hallucinations_in_position.
            if w in cluster_module.HALLUCINATIONS:
                return True                      # B141: always
            if not song_wide:
                return False        # B536: and B258 is already skipped
            if w in _HALLUCINATION_SEGMENT_WORDS:
                return not _word_in_lyrics(w, lyric_keys)
            return False

        segment_is_hallucination = bool(core_words) and all(
            _is_a_hallucination_word(w) for w in core_words)

        # B464: a row of the same short syllable is only singing when
        # the TEXT chants it too. Without that condition this exempted
        # the most common hallucination Whisper produces - a repetition
        # loop on an instrumental stretch - and that cost about half a
        # second of timing. The original may sing "na-na-na" where the
        # karaoke text writes "la-la-la"; either spelling counts, but
        # one of the two has to have it.
        chant = _is_chant(core_words) and any(
            _word_in_lyrics(w, chant_keys) for w in core_words)
        if chant:
            segment_is_hallucination = False

        # B514: deliberately AFTER the chant exemption. A chant of
        # twenty-seven seconds in one word is still one word of
        # twenty-seven seconds, and the exemption is about text that is
        # really repeated - not about a word that never ends.
        loop = runaway_words(seg, median_word)
        if loop and _runaway_share(seg, loop) >= _RUNAWAY_SHARE:
            timed = [w for w in loop
                     if w.end is not None and w.start is not None]
            longest = max(timed, key=lambda w: float(w.end) - float(w.start),
                          default=None)
            logger.info(
                t("log_runaway_filtered"), seg.start, seg.end,
                (float(longest.end) - float(longest.start))
                if longest is not None else 0.0,
                max(len(str(w.text or "").strip()) for w in loop))
            segment_is_hallucination = True

        best_match = 0.0
        if song_wide and not segment_is_hallucination and lyric_keys \
                and not chant \
                and len(core_words) >= _SEGMENT_HALLUCINATION_MIN_CORE_WORDS:
            best_match = max(
                (_best_lyrics_match(w, lyric_keys) for w in core_words),
                default=0.0)
            if best_match < _SEGMENT_HALLUCINATION_MATCH_FLOOR:
                confidences = [c for _w, c in core_pairs if c is not None]
                lowest_conf = min(confidences) if confidences else None
                if lowest_conf is None \
                        or lowest_conf < _SEGMENT_HALLUCINATION_CONF_CEILING:
                    segment_is_hallucination = True

        if segment_is_hallucination:
            dropped += 1
            if dropped_out is not None:
                dropped_out.append(seg)
            logger.info(
                t("log_hallucination_filtered"), seg.text, seg.start, seg.end,
                best_match)
            continue
        kept.append(seg)
    if dropped:
        logger.info(t("log_hallucinations_filtered"), dropped)
    return tuple(kept)


def _position_anchors(aligned: tuple) -> list[tuple[float, int]]:
    """(time, lyrics index) of every STRONGLY coupled word (B307).

    Sorted by time. These pairs are the only thing the position-aware
    check needs from a first alignment round: they say which lyrics word
    was sung at which moment, and therefore which lyrics words can still
    belong in the space in between.
    """
    anchors = [(float(a.start), int(a.lyric.index)) for a in aligned
               if a.start is not None
               and float(a.sim) >= _POSITION_ANCHOR_SIM]
    anchors.sort()
    return anchors


def _position_window(seg, anchors: list[tuple[float, int]],
                     n_lyrics: int) -> tuple[int, int]:
    """The lyrics words that can belong at the position of ``seg`` (B307).

    The lyrics have no timing (determining it is precisely what this tool
    is for) but they DO have the right word order. The last anchor before
    the segment and the first anchor after it therefore bound a window in
    the lyrics: whatever is really sung there has to be within it. The
    window is widened to ``_POSITION_WINDOW_MIN_WORDS`` words so that
    closely spaced anchors do not produce an unreasonably narrow window.

    Returns:
        ``(lo, hi)``, both inclusive lyrics indices.
    """
    lo = 0
    for time, index in anchors:
        if time <= seg.start + 0.01:
            lo = index
        else:
            break
    hi = n_lyrics - 1
    for time, index in anchors:
        if time >= seg.end - 0.01:
            hi = index
            break
    hi = max(hi, lo)
    while hi - lo + 1 < _POSITION_WINDOW_MIN_WORDS \
            and (lo > 0 or hi < n_lyrics - 1):
        if lo > 0:
            lo -= 1
        if hi < n_lyrics - 1 and hi - lo + 1 < _POSITION_WINDOW_MIN_WORDS:
            hi += 1
    return lo, hi


def _segment_has_coupling(seg, aligned: tuple) -> bool:
    """Did any lyrics word get coupled within this segment? (B307)

    If so, the segment is by definition not a hallucination: the
    alignment found real matches in it. Only segments to which nothing
    at all attached are candidates for the position-aware check.
    """
    return any(a.start is not None
               and seg.start - 0.01 <= a.start <= seg.end + 0.01
               for a in aligned)


def _filter_hallucinations_in_position(
    segments: tuple, lyrics, aligned: tuple,
    dropped_out: list | None = None, language: str = "",
    extra_keys=None,
) -> tuple:
    """Second round of the hallucination check, aware of position (B307).

    The song-wide check (B285) asks "does this segment resemble anything
    in the lyrics at all?". That is too lenient at exactly the place
    where Whisper hallucinates most: after a long silence, at the end of
    a song. "SPANNENDE MUZIEK" scores a perfect match song-wide because
    "muziek" really does occur - halfway through the first verse. At the
    position where the segment stands (the outro, after the last coupled
    word) that word appears nowhere.

    This round therefore compares only with the lyrics words that can
    belong at that position: the window between the nearest coupled
    anchors before and after it (``_position_window``). Two guards keep
    the check safe: a segment in which the alignment did couple
    something is never touched, and Whisper's own word confidence has to
    be low - the same safety net as in B285.

    Args:
        segments: The segments left after the song-wide round.
        lyrics: The lyrics words of this song.
        aligned: A first alignment of ``lyrics`` on ``segments``.
        dropped_out: Optional list to which dropped segments are appended
            (the coupling editor shows them, B287/B309).

    Returns:
        The segments that survive this round too.
    """
    if not lyrics or not aligned:
        return segments
    anchors = _position_anchors(aligned)
    if not anchors:
        return segments
    chant_keys = frozenset(extra_keys or ())         # B464
    kept = []
    for seg in segments:
        word_objs = list(seg.words) if seg.words else []
        if word_objs:
            paren = [(cluster_module.normalize_for_filter(w.text),
                      w.confidence) for w in word_objs]
        else:
            paren = [(cluster_module.normalize_for_filter(seg.text), None)]
        paren = [(w, c) for w, c in paren if w]
        fillers = _language_words(language, "fillers")
        core_words = [w for w, _c in paren if w not in fillers]
        if _segment_has_coupling(seg, aligned):
            kept.append(seg)
            continue
        if _is_chant(core_words) and any(
                _word_in_lyrics(w, chant_keys) for w in core_words):
            # Same reasoning as in the round before this one: a row of
            # the same short syllable has the shape of singing, not of a
            # hallucination - and this round is the stricter of the two,
            # so it would certainly have thrown it out. B458: only for a
            # syllable that occurs in one of the two texts; a chant of
            # something that is sung nowhere is still suspect.
            kept.append(seg)
            continue
        lo, hi = _position_window(seg, anchors, len(lyrics))
        window_keys = frozenset(cluster_module.phonetic_key(w.text)
                                for w in lyrics[lo:hi + 1])
        # B337: a word from the language list only counts as an artefact
        # where the lyrics do NOT have it. Song-wide was too lenient:
        # measured, all eight occurrences of "you" in one song sat in the
        # first 36%, and they protected a "Thank you." in the outro two
        # hundred words further on.
        artefacts = _language_words(language, "hallucinations")
        if core_words and all(w in artefacts for w in core_words) \
                and not any(_word_in_lyrics(w, window_keys)
                            for w in core_words):
            if dropped_out is not None:
                dropped_out.append(seg)
            logger.info(t("log_artifact_in_position"), seg.text,
                        seg.start, seg.end, language or "?")
            continue
        if len(core_words) < _SEGMENT_HALLUCINATION_MIN_CORE_WORDS:
            kept.append(seg)
            continue
        best_match = max((_best_lyrics_match(w, window_keys)
                          for w in core_words), default=0.0)
        if best_match >= _SEGMENT_HALLUCINATION_MATCH_FLOOR:
            kept.append(seg)
            continue
        confidences = [c for _w, c in paren if c is not None]
        lowest_conf = min(confidences) if confidences else None
        if lowest_conf is not None \
                and lowest_conf >= _SEGMENT_HALLUCINATION_CONF_CEILING:
            kept.append(seg)
            continue
        if dropped_out is not None:
            dropped_out.append(seg)
        logger.info(
            t("log_hallucination_position"),
            seg.text, seg.start, seg.end, lo, hi, best_match)
    return tuple(kept)


#: B377: below this share of words-on-measured-singing a segment counts
#: as "nothing is sung here". Measured on "Lied K" all
#: real segments sit at 50 to 100 percent and the two false ones at
#: exactly zero - a gap no threshold can fall into. A third leaves room
#: for a segment that runs across a breath pause.
_SUNG_MIN_SHARE = 0.34


def _drop_unsung_segments(context: AppContext, segments: tuple,
                          dropped_out: list | None = None) -> tuple:
    """Throw away whatever sits on no measured singing at all (B377).

    The three kinds of rubbish we know of - invented text ("MUZIEK",
    "Thank you"), misheard singing, and the PROMPT ECHO where Whisper
    simply pronounces the lyrics it was handed during an instrumental
    intro - cannot be told apart by their text lines. The prompt echo
    is even word for word the real lyrics, so every test of the form
    "does this look like the lyrics?" says yes without hesitation.

    The singing voice does know. That measurement was already there
    (``_vocal_windows``, built for the timing) and has never been used
    to filter with. Does a segment not sit on measured singing, then
    nothing is being sung there - whatever the text claims.

    Deliberately at WORD level: Whisper regularly stretches the end of
    a segment far past the last note, and then a real segment drops
    through the threshold at segment level. At word level the
    reference set reached 50 to 100 percent for every real segment.
    """
    try:
        windows = _vocal_windows(context)
    except Exception:  # noqa: BLE001 - no measurement, no verdict
        return segments
    if not windows:
        return segments

    def on_singing(moment: float) -> bool:
        return any(low - 0.1 <= moment <= high + 0.1
                   for low, high in windows)

    kept, dropped = [], 0
    for segment in segments:
        words = list(segment.words)
        if not words:
            kept.append(segment)
            continue
        raak = sum(1 for w in words if on_singing(w.start) or on_singing(w.end))
        if raak / len(words) >= _SUNG_MIN_SHARE:
            kept.append(segment)
            continue
        dropped += 1
        if dropped_out is not None:
            dropped_out.append(segment)
        logger.info(t("log_unsung_dropped"), segment.start, segment.text[:40])
    if dropped:
        logger.info(t("log_unsung_total"), dropped)
    return tuple(kept)


def _clean_segments_and_alignment(
    context: AppContext, lyrics, segments: tuple,
    dropped_out: list | None = None,
) -> tuple[tuple, tuple]:
    """Filtered segments plus the matching lyrics alignment.

    Brings the three hallucination rounds together in one place so that
    the coupling editor and the timing always work with exactly the same
    result: the fixed word list (B258), the song-wide check (B285) and
    the position-aware check (B307). The alignment that the second round
    needs is reused as the final result if nothing more was dropped;
    only if B307 does strike is a new alignment made.
    """
    priority = _filler_priority_lines(context)  # B276

    def _align(segs):
        return song_text.trim_tail_matches(
            song_text.align_lyrics(lyrics, segs, skip_filler=True,
                                   priority_lines=priority))  # B159/B213/B276

    # B377: let the vocal stem speak first. What sits on no measured
    # singing is not singing, and then no line of text has to pass
    # judgement on it any more.
    segments = _drop_unsung_segments(context, segments,
                                     dropped_out=dropped_out)
    chanted = chanted_keys(context)                      # B464
    clean = _filter_hallucinations(segments, lyrics,
                                   dropped_out=dropped_out,
                                   extra_keys=chanted)     # B258/B285
    aligned = _align(clean)
    tighter = _filter_hallucinations_in_position(
        clean, lyrics, aligned, dropped_out=dropped_out,
        language=_language_for(context, TRACK_ORIGINAL),
        extra_keys=chanted)                                # B307/B337/B464
    if len(tighter) != len(clean):
        clean = tighter
        aligned = _align(clean)
    return clean, aligned


def _filler_priority_lines(context: AppContext) -> frozenset[int]:
    """Karaoke text line numbers where a filler word is extra important (B276).

    Gives the line numbers of karaoke_text.txt that contain real
    (non-filler word) content. Lyrics and karaoke text share the same
    structure separated by empty lines, so line number ``n`` in the one
    corresponds to line number ``n`` in the other; this function
    therefore only reads the karaoke text, and ``song_text.align_lyrics``
    subsequently tests the line number of each lyrics word against it
    (B288). If there is a filler word on such a line in the lyrics (e.g.
    lyrics "Oh, de mooiste momenten," / karaoke text "Ben ik een
    pinguïn,"), then the timing of that filler word is extra important:
    it determines directly where the (unrelated) karaoke content comes
    to stand in the video. Gives an empty set if the karaoke text is
    missing (no separate parody text, so no signal).
    """
    from . import karaoke_text
    karaoke_path = context.paths.input_dir / karaoke_text.FILENAME
    if not karaoke_path.exists():
        return frozenset()
    try:
        karaoke_lines = karaoke_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    priority = set()
    for line_no, raw in enumerate(karaoke_lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        words = re.findall(r"[^\W\d_]+", stripped, flags=re.UNICODE)
        if any(not song_text.is_filler_word(w) for w in words):
            priority.add(line_no)
    return frozenset(priority)


#: A coupling below this similarity counts as "skipped" and may be
#: replaced by an estimate from the vocal stem (B313). The same bound
#: that ``trim_tail_matches`` uses to unlink a weak tail: below it the
#: coupling says more about the desperation of the alignment than about
#: the word. Measured case: "alle" and "dagen" coupled to "la," at 0.25,
#: because the real chorus was missing from the transcription.
_ESTIMATE_MAX_SIM = 0.45

#: A window between two anchors shorter than this offers nothing to
#: distribute (B313).
_ESTIMATE_MIN_WINDOW_S = 0.2

#: How much longer a trailing window may be than the singing in it needs
#: before the words are fitted from the BACK (B319). A tail run has no
#: anchor after it, so its window runs to the end of the singing; if that
#: window offers far more time than the words need, spreading over the
#: whole of it stretches every word out of proportion and the repetitions
#: at the end no longer line up with what you hear. Counting back from
#: the end is then the better fit - that is also the side where the
#: certainty lies.
_TAIL_BACKWARD_SLACK = 1.3

#: Fallback for the duration of one syllable (B319) when there is nothing
#: to measure: about a quarter of a second is a normal sung syllable.
_DEFAULT_SECONDS_PER_SYLLABLE = 0.25

#: More words per second than this cannot be sung (B313). Fast patter in
#: Dutch reaches about four words per second; six is a generous outer
#: bound that no real singing crosses. If a window between two anchors
#: demands more, then one of those two anchors is in the wrong place -
#: see ``_relax_implausible_anchors``.
_MAX_WORDS_PER_SECOND = 6.0


def _runs_between_anchors(anchors: list[bool], times: list, count: int,
                          song_end: float) -> list[tuple[int, int, float,
                                                         float]]:
    """The runs of non-anchors, with the window they have to fit in."""
    runs = []
    index = 0
    while index < count:
        if anchors[index]:
            index += 1
            continue
        end_index = index
        while end_index < count and not anchors[end_index]:
            end_index += 1
        previous = next((p for p in range(index - 1, -1, -1)
                         if anchors[p]), None)
        following = next((n for n in range(end_index, count)
                          if anchors[n]), None)
        low = float(times[previous][1]) if previous is not None else 0.0
        high = (float(times[following][0]) if following is not None
                else song_end)
        runs.append((index, end_index, low, high))
        index = end_index
    return runs


def _relax_implausible_anchors(anchors: list[bool], times: list,
                               fixed: set[int], song_end: float) -> int:
    """Drop anchors that demand impossible singing (B313).

    A hallucination that happens to contain a real word becomes a
    perfect coupling and thus an anchor - measured case: the lyrics word
    "muziek" on a hallucinated "MUZIEK" with similarity 1.00, right in
    the middle of a hole in the transcription. That one anchor squeezed
    the twenty-eight following words into three and a half seconds:
    eight words per second, which nobody sings.

    Similarity does not expose such an anchor (it is a perfect match in
    the wrong place); the consequence does. So this function looks at
    what an anchor DEMANDS: for every window that is too dense it
    considers dropping the anchor to its left and the one to its right.

    Two conditions keep good couplings out of reach. Only an ISOLATED
    anchor may go - one with no anchor directly before or after it in the
    lyrics. A correct coupling hardly ever stands alone: its neighbours
    match as well, and such a group stays untouched. A wrongly placed one
    is by its nature a loner, in a hole where nothing else could be
    coupled. And a manually pinned word is never dropped: the user has
    the last word.

    Without that isolation test the repair dragged correct anchors along
    with it - measured: "serenade" and "aan" (similarity 1.00) shifted by
    a second, and the real la-la couplings by five.

    Mutates ``anchors``; returns how many were dropped.
    """
    count = len(anchors)

    def is_loner(index: int) -> bool:
        before = index > 0 and anchors[index - 1]
        after = index + 1 < count and anchors[index + 1]
        return not before and not after

    def worst_density(current: list[bool]) -> float:
        """The heaviest window that words are really placed in.

        Windows shorter than ``_ESTIMATE_MIN_WINDOW_S`` do not count:
        nothing is placed there, so they cannot be improved either. Let
        them count and the score is permanently dominated by an
        unfixable sliver, after which no single drop looks like an
        improvement and the repair never happens.
        """
        worst = 0.0
        for start, stop, low, high in _runs_between_anchors(
                current, times, count, song_end):
            span = high - low
            if span < _ESTIMATE_MIN_WINDOW_S:
                continue
            worst = max(worst, (stop - start) / span)
        return worst

    def overloaded_runs(current: list[bool]):
        """Runs that demand impossible singing, worst first.

        A window shorter than ``_ESTIMATE_MIN_WINDOW_S`` is left out: no
        word is placed there anyway, so its density says nothing. Without
        that exception a single word between two adjacent anchors (two
        hundredths of a second apart) was always the "worst" case, while
        nothing can be done about it - and the repair stopped before it
        ever reached the real problem.
        """
        runs = [r for r in _runs_between_anchors(current, times, count,
                                                 song_end)
                if r[3] - r[2] >= _ESTIMATE_MIN_WINDOW_S]
        heavy = [r for r in runs
                 if (r[1] - r[0]) / (r[3] - r[2]) > _MAX_WORDS_PER_SECOND]
        return sorted(heavy, key=lambda r: -(r[1] - r[0]) / (r[3] - r[2]))

    dropped = 0
    while True:
        heavy = overloaded_runs(anchors)
        if not heavy:
            return dropped
        chosen = None
        # Walk the overloaded windows from bad to less bad and take the
        # first one where dropping an anchor really helps. Deliberately
        # not stopping at the first window without a candidate: that is
        # usually an unfixable sliver, and the real culprit lies further
        # along.
        for start, stop, _low, _high in heavy:
            kandidaten = [p for p in
                          (next((p for p in range(start - 1, -1, -1)
                                 if anchors[p]), None),
                           next((n for n in range(stop, count)
                                 if anchors[n]), None))
                          if p is not None and p not in fixed and is_loner(p)]
            best, best_score = None, worst_density(anchors)
            for kandidaat in kandidaten:
                trial = list(anchors)
                trial[kandidaat] = False
                score = worst_density(trial)
                if score < best_score:
                    best, best_score = kandidaat, score
            if best is not None:
                chosen = best
                break
        if chosen is None:
            return dropped          # niets meer te verbeteren
        anchors[chosen] = False
        dropped += 1


def _drop_couplings_after(aligned: tuple, song_end: float) -> tuple:
    """Unlink couplings that lie after the last sung moment (B319).

    Whisper sometimes writes something down after the singing has
    stopped - applause, a fade-out, a hallucination. A lyrics word
    coupled to that lands beyond the end of the song, and it drags
    everything before it out of position because the alignment counts on
    it as an anchor. The end of the singing is measurable, so such a
    coupling can simply be rejected: the word becomes uncoupled again and
    is placed by the estimate, within the window that does exist.
    """
    result = []
    dropped = 0
    for word in aligned:
        if word.start is not None and not word.estimated \
                and float(word.start) > song_end + 0.05:
            result.append(replace(word, start=None, end=None,
                                  matched_text=None, sim=0.0))
            dropped += 1
        else:
            result.append(word)
    if dropped:
        logger.info(t("log_after_song_end"), dropped, song_end)
    return tuple(result)


def _seconds_per_syllable(aligned: tuple) -> float:
    """How long one sung syllable lasts in THIS song (B319).

    Measured on the well-coupled words, so the estimate follows the tempo
    of the song instead of a fixed assumption. The median, because one
    held note should not pull the whole thing up.
    """
    from . import timing as timing_module

    durations = []
    for word in aligned:
        if word.start is None or word.estimated \
                or float(word.sim) < _ESTIMATE_MAX_SIM:
            continue
        syllables = max(1, len(timing_module.split_syllables(
            word.lyric.text)))
        span = float(word.end) - float(word.start)
        if 0.02 < span < 3.0:
            durations.append(span / syllables)
    if not durations:
        return _DEFAULT_SECONDS_PER_SYLLABLE
    durations.sort()
    return durations[len(durations) // 2]


def _fit_from_the_back(windows: list[tuple[float, float]],
                       needed: float) -> list[tuple[float, float]]:
    """Keep only the LAST ``needed`` seconds of singing (B319).

    Used for a run at the end of the song. The end of the singing is a
    fact; where such a run starts is not. So the words are counted back
    from the end instead of spread over everything that is left over -
    that is what makes a repeated closing phrase line up with what you
    hear instead of drifting.
    """
    total = sum(e - s for s, e in windows)
    if total <= needed:
        return windows
    left = needed
    kept: list[tuple[float, float]] = []
    for start, end in reversed(windows):
        span = end - start
        if left >= span:
            kept.append((start, end))
            left -= span
        else:
            kept.append((end - left, end))
            break
    return list(reversed(kept))


def _place_skipped_on_energy(context: AppContext, aligned: tuple) -> tuple:
    """Give skipped lyrics words a time from the vocal stem (B313).

    The alignment couples on sound. What Whisper did not produce cannot
    be coupled - and after a hole in the transcription the alignment
    sometimes grabs the only thing within reach, which yields couplings
    such as "alle" on "la," with a similarity of 0.25. Both cases leave a
    word without a usable time, while the vocal stem simply shows where
    singing is going on.

    This function fills in those places as best it can: for every run of
    skipped words between two GOOD anchors, the sung time in that window
    is divided over the words in order. Three rules keep it honest:

    * A well-coupled word (similarity at or above ``_ESTIMATE_MAX_SIM``)
      is never touched, nor is a manually pinned one. Those are exactly
      the anchors that bound the window.
    * The order of the lyrics is preserved: a run stays inside the window
      between its neighbours, so no word can end up before its
      predecessor.
    * The result is marked ``estimated``. Everything that judges the
      quality of the timing can therefore see that this is a measurement
      of the singing and not a recognised word.

    Without a vocal stem (analysis off, Demucs missing) the alignment
    comes back unchanged.
    """
    if not context.config.advanced.vocal_analysis or not aligned:
        return aligned
    from . import rhythm
    from . import timing as timing_module
    if not rhythm.is_available():
        return aligned
    vocals = ensure_original_vocals(context)
    if vocals is None:
        return aligned
    active = rhythm.active_windows(vocals)
    if not active:
        return aligned
    # B319: the end of the singing is just as hard a fact as the start
    # (which has been an anchor since B130/B133 as ``vocal_onset_s``).
    # Nothing can be sung after it, so nothing may be placed there - and
    # a coupling that lands beyond it is wrong by definition.
    song_end = active[-1][1]
    context.store.set_meta("vocal_end_s", round(float(song_end), 3))
    aligned = _drop_couplings_after(aligned, song_end)
    pinned = set(word_pins(context))

    def is_anchor(word) -> bool:
        return word.start is not None and not word.estimated and (
            word.lyric.index in pinned
            or float(word.sim) >= _ESTIMATE_MAX_SIM)

    def untouchable(word) -> bool:
        return word.lyric.index in pinned or word.lyric.bg

    result = list(aligned)
    count = len(result)
    # Words that may not be touched count as anchors, so that a run never
    # runs straight through them and the order stays intact.
    anchors = [is_anchor(w) or untouchable(w) for w in result]
    times = [(w.start if w.start is not None else 0.0,
              w.end if w.end is not None else 0.0) for w in result]
    fixed = {i for i, w in enumerate(result) if untouchable(w)}
    dropped = _relax_implausible_anchors(anchors, times, fixed, song_end)
    if dropped:
        logger.info(t("log_anchors_released"), dropped)

    per_syllable = _seconds_per_syllable(aligned)
    runs = _runs_between_anchors(anchors, times, count, song_end)
    last_run = runs[-1] if runs else None
    placed = 0
    for run in runs:
        start_index, end_index, low, high = run
        run_count = end_index - start_index
        if high - low < _ESTIMATE_MIN_WINDOW_S or run_count < 1:
            continue
        within = [(max(s, low), min(e, high)) for s, e in active
                  if e > low + 0.02 and s < high - 0.02]
        # B318: weigh by syllable count, so "Espagna" gets more time than
        # "e" instead of exactly as much.
        gewichten = [max(1, len(timing_module.split_syllables(
            result[start_index + k].lyric.text))) for k in range(run_count)]
        # B319: a run at the END of the song has no anchor after it, so
        # its window runs on to where the singing stops. Does that window
        # offer far more sung time than these words need, then counting
        # back from the end fits better than spreading over everything.
        if run is last_run and end_index >= count:
            needed = sum(gewichten) * per_syllable
            beschikbaar = sum(e - s for s, e in within)
            if beschikbaar > needed * _TAIL_BACKWARD_SLACK:
                within = _fit_from_the_back(within, needed)
                logger.info(t("log_tail_from_the_back"),
                            run_count, beschikbaar, needed)
        for offset, (start, stop) in enumerate(
                timing_module.spread_over_active(run_count, within,
                                                 weights=gewichten)):
            word = result[start_index + offset]
            if untouchable(word):
                continue
            result[start_index + offset] = replace(
                word, start=round(start, 3), end=round(stop, 3),
                matched_text=None, sim=0.0, estimated=True)
            placed += 1
    if placed:
        logger.info(t("log_skipped_placed"), placed)
    return tuple(result)


def _lyrics_alignment(context: AppContext,
                      segments: tuple) -> tuple | None:
    """Align the lyrics if ``input/lyrics.txt`` exists."""
    lyrics_path = context.paths.input_dir / song_text.LYRICS_FILENAME
    if not lyrics_path.exists():
        return None
    try:
        lyrics = _effective_lyrics(context, lyrics_path)
        clean, aligned = _clean_segments_and_alignment(
            context, lyrics, segments)  # B258/B285/B307
        # The same word list as the coupling editor numbers on, so that a
        # pin means the same thing in both places (B153/B309).
        transcript, filtered = _coupling_transcript(context, segments, clean)
        migrate_lyric_pins(context)                    # B417
        pins = _pins_for_transcript(context, filtered)  # B121
        pins = anchor_pins(context, pins, lyrics, transcript)  # B506
        if pins:
            aligned = song_text.apply_pins(aligned, transcript, pins)
        return _place_skipped_on_energy(context, aligned)  # B313
    except Exception:  # noqa: BLE001 - lyrics must never break step 2/4
        logger.exception(t("log_lyrics_alignment_failed"))
        return None


def _lyrics_damping_intervals(
    context: AppContext,
    selected: tuple[cluster_module.Cluster, ...],
    regions: tuple[align.OffsetRegion, ...],
    settings,
) -> list[karaoke.DampingInterval]:
    """Extra fragments from the lyrics (original -> karaoke timeline)."""
    aligned = _lyrics_alignment(context,
                                load_segments(context, TRACK_ORIGINAL))
    if aligned is None:
        return []
    target_keys = {cluster_module.phonetic_key(member)
                   for cluster in selected for member, _ in cluster.members}
    target_keys |= {cluster_module.phonetic_key(cluster.label)
                    for cluster in selected}
    known = [(occurrence.start, occurrence.end)
             for cluster in selected for occurrence in cluster.occurrences]
    margin = settings.margin_ms / 1000.0
    intervals = []
    for start, end, label in song_text.extra_intervals(aligned, target_keys,
                                                       known):
        intervals.append(karaoke.DampingInterval(
            label=label,
            start=max(0.0, align.project_time(start, regions) - margin),
            end=align.project_time(end, regions) + margin,
            gain_db=settings.gain_db,
        ))
    if intervals:
        context.store.set_step("lyrics", {"extra_fragments":
                                             len(intervals)})
    return intervals


def reset_damping(context: AppContext) -> None:
    """Set the karaoke back to the original sound.

    Removes the processed wav, the exported ``karaoke_edit`` and the
    damping/exclusion administration, so that nothing is damped anymore
    and the video uses the clean karaoke again. Also clears the kept
    "back from original" fragments (B282) - a reset unambiguously means
    back to the unchanged karaoke.
    """
    edited = context.paths.cache_dir / "karaoke_edited.wav"
    resampled = context.paths.cache_dir / "original_for_restore.wav"
    for path in (edited, resampled,
                 context.paths.output_dir / "karaoke_edit.mp3",
                 context.paths.output_dir / "karaoke_edit.wav"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning(t("log_file_delete_failed"), path)
    context.store.clear_step("karaoke")
    context.store.clear_step("fragment_exclusions")
    context.store.clear_step("restore_fragments")
    context.store.clear_step("original_restore_resample")
    logger.info(t("log_damping_reset"))


def apply_manual_damping(
    context: AppContext,
    spans: Sequence[tuple[float, float]],
    restore_spans: Sequence[tuple[float, float, str]] | None = None,
) -> KaraokeResult:
    """Apply a manually edited set of damping fragments and export.

    Used by the damping editor: the fragments (windows on the karaoke
    timeline) are damped directly, regardless of the clusters. The
    choice is kept so that a next session/step reuses them.

    ``restore_spans`` (B282, ``(start, end, label)``) are "back from
    original" fragments from the same editor: as ``None`` the earlier
    kept restore selection stays unchanged (e.g. on an ordinary damping
    change); an empty list precisely clears the restore selection
    explicitly.
    """
    karaoke_wav = stored_wav(context, TRACK_KARAOKE)
    settings = context.config.karaoke
    raw = [karaoke.DampingInterval(label="manual", start=max(0.0, s),
                                   end=e, gain_db=settings.gain_db)
           for s, e in spans if e > s]
    intervals = karaoke.merge_intervals(raw)

    if restore_spans is not None:
        # B498: a block that came from a marked sentence may be deleted
        # here (or the sentence unmarked another way), and that has to
        # reach the marking itself - otherwise deleting it did nothing
        # and it was simply back the next time, without a word.
        kept_lines = {line_of_restore_label(label)
                      for _s, _e, label in restore_spans}
        kept_lines.discard(None)
        # B499: only when the derivation really worked. Could the timing
        # not be read, then 1.4 shows no sentence blocks at all and
        # saving would silently wipe every marking.
        marked = restore_lines(context)
        readable = bool(_restore_from_lines(context, apply_moves=False)) \
            or not marked
        if readable:
            set_restore_lines(context, [number for number in marked
                                        if number in kept_lines])
        set_restore_fragments(context, [
            (max(0.0, s), e, label) for s, e, label in restore_spans
            if e > s and line_of_restore_label(label) is None])
        # B499: a derived block that has been MOVED or stretched here was
        # thrown away and derived again at the next pass, so the move
        # simply did not survive. It is kept per line number now, so the
        # timing editor can show that the piece no longer lies on its
        # sentence - and can put it back.
        derived = {item.label: (item.start, item.end)
                   for item in _restore_from_lines(context,
                                                   apply_moves=False)}
        moved: dict[int, list[float]] = {}
        for start, end, label in restore_spans:
            number = line_of_restore_label(label)
            if number is None or end <= start:
                continue
            own = derived.get(label)
            if own is None or abs(own[0] - start) > 0.02 \
                    or abs(own[1] - end) > 0.02:
                moved[number] = [round(max(0.0, start), 3), round(end, 3)]
        if readable:
            set_moved_restores(context, moved)
    restore = restore_fragments(context)
    karaoke_props = ffmpeg.probe(karaoke_wav)
    restore_prepared = _prepared_restore_intervals(
        context, restore, karaoke_props.sample_rate or 44_100)

    output_wav = context.paths.cache_dir / "karaoke_edited.wav"
    karaoke.apply_damping(karaoke_wav, intervals, settings, output_wav,
                         restore_intervals=restore_prepared)
    context.store.set_step("karaoke", {
        "wav": str(output_wav),
        "intervals": karaoke.intervals_to_dicts(intervals),
        "all_intervals": karaoke.intervals_to_dicts(intervals),
        "manual": True,
    })
    logger.info(t("log_manual_damping"),
                len(intervals))
    return KaraokeResult(intervals=intervals, all_intervals=intervals,
                         output_wav=output_wav, restore_intervals=restore)


def current_damping_intervals(
        context: AppContext) -> list[tuple[float, float, str]]:
    """Current damping fragments (from step 4), for the damping editor."""
    step = context.store.get_step("karaoke")
    if step is None:
        return []
    data = step.get("all_intervals") or step.get("intervals") or []
    intervals = karaoke.intervals_from_dicts(data)
    return [(iv.start, iv.end, iv.label) for iv in intervals]


def set_fragment_exclusions(
        context: AppContext,
        exclusions: Sequence[tuple[float, float]]) -> None:
    """Keep which fragments the user has excluded (unticked)."""
    context.store.set_step("fragment_exclusions", {
        "list": [[start, end] for start, end in exclusions],
    })
    logger.info(t("log_fragment_exclusions"), len(exclusions))


def fragment_exclusions(
        context: AppContext) -> tuple[tuple[float, float], ...]:
    """The excluded fragments (empty tuple if there are none)."""
    step = context.store.get_step("fragment_exclusions")
    if step is None:
        return ()
    return tuple((float(start), float(end))
                 for start, end in step.get("list", ()))


def set_restore_fragments(
        context: AppContext,
        fragments: Sequence[tuple[float, float, str]]) -> None:
    """Keep the "back from original" fragments (B282, damping editor).

    Kept separately from ``fragment_uitsluitingen``/the cluster damping,
    so that a later step-4 rerun (new cluster selection) does not sweep
    away these manual choices - ``run_karaoke``/``apply_manual_damping``
    both apply them again.
    """
    context.store.set_step("restore_fragments", {
        "list": [[start, end, label] for start, end, label in fragments],
    })
    logger.info(t("log_restore_saved"), len(fragments))


#: B496: prefix on the label of a restore fragment that came from a
#: sentence marked in the timing editor. The damping editor draws those
#: in their own colour, and it says at a glance where the fragment comes
#: from.
LINE_RESTORE_PREFIX = "zin "


def moved_restores(context: AppContext) -> dict[int, tuple[float, float]]:
    """Marked sentences whose piece of original was moved in 1.4 (B499).

    Empty for every sentence whose piece still lies exactly on it. The
    timing editor draws those with a dotted border, and one more click on
    "back from the original" puts the piece back on the sentence.
    """
    step = context.store.get_step("restore_moved")
    if step is None:
        return {}
    out: dict[int, tuple[float, float]] = {}
    for number, span in (step.get("list") or {}).items():
        try:
            start, end = float(span[0]), float(span[1])
        except (TypeError, ValueError, IndexError):
            continue
        if end > start:
            out[int(number)] = (start, end)
    return out


def set_moved_restores(context: AppContext,
                       spans: dict[int, Sequence[float]]) -> None:
    """Keep which pieces were moved in 1.4 (B499)."""
    context.store.set_step("restore_moved", {
        "list": {str(number): [float(span[0]), float(span[1])]
                 for number, span in spans.items()},
    })


def reset_moved_restore(context: AppContext, number: int) -> None:
    """Put the piece of this sentence back on the sentence (B499)."""
    spans = moved_restores(context)
    if spans.pop(int(number), None) is not None:
        set_moved_restores(context, spans)


def restore_lines(context: AppContext) -> tuple[int, ...]:
    """Karaoke line numbers marked as "back from the original" (B496)."""
    step = context.store.get_step("restore_lines")
    if step is None:
        return ()
    return tuple(sorted({int(number) for number in step.get("list", ())}))


def set_restore_lines(context: AppContext,
                      numbers: Sequence[int]) -> None:
    """Keep which sentences are fetched back from the original (B496)."""
    context.store.set_step("restore_lines",
                           {"list": sorted({int(n) for n in numbers})})


def _restore_from_lines(context: AppContext, apply_moves: bool = True
                        ) -> tuple[karaoke.RestoreInterval, ...]:
    """The marked sentences as restore fragments, on today's timing
    (B496).

    Deliberately derived and not frozen as a time: move the sentence in
    the timing editor and the piece of original moves with it, which is
    the only way the two can stay together.

    ``apply_moves=False`` gives the bare derivation, without a move made
    in 1.4 (B499) - that is what the detection of such a move compares
    against.
    """
    numbers = restore_lines(context)
    if not numbers:
        return ()
    try:
        lines = {line.index: line for line in load_timing_reanchored(context)}
    except (OSError, ValueError, KeyError, PipelineError):
        return ()
    out: list[karaoke.RestoreInterval] = []
    for number in numbers:
        line = lines.get(number)
        if line is None or line.end <= line.start:
            continue
        out.append(karaoke.RestoreInterval(
            label=f"{LINE_RESTORE_PREFIX}{number}: {line.text}"[:60],
            start=float(line.start), end=float(line.end)))
    # B499: a piece that was moved in 1.4 keeps its own place.
    from dataclasses import replace

    moved = moved_restores(context) if apply_moves else {}
    if moved:
        out = [replace(item, start=moved[number][0], end=moved[number][1])
               if (number := line_of_restore_label(item.label)) in moved
               else item for item in out]
    return tuple(out)


def line_of_restore_label(label: str) -> int | None:
    """The line number in a derived restore label, or ``None`` (B498).

    The damping editor may delete and move those blocks, and then that
    has to reach back to the marking - otherwise deleting one does
    nothing and it is simply there again the next time.
    """
    import re

    match = re.match(re.escape(LINE_RESTORE_PREFIX) + r"(\d+):", str(label))
    return int(match.group(1)) if match else None


def restore_fragments(
        context: AppContext) -> tuple[karaoke.RestoreInterval, ...]:
    """The kept "back from original" fragments (empty if there are none).

    B496: the sentences marked in the timing editor come along here, so
    that everything that has to be fetched back from the original walks
    one and the same road through 1.4.
    """
    step = context.store.get_step("restore_fragments")
    drawn = () if step is None else tuple(
        karaoke.RestoreInterval(label=str(label), start=float(start),
                                end=float(end))
        for start, end, label in step.get("list", ())
        if line_of_restore_label(label) is None)
    return tuple(sorted(drawn + _restore_from_lines(context),
                        key=lambda item: item.start))


def _prepared_restore_intervals(
    context: AppContext,
    intervals: Sequence[karaoke.RestoreInterval],
    karaoke_sample_rate: int,
) -> list[tuple[karaoke.RestoreInterval, np.ndarray, int]]:
    """Cut out for each restore fragment the corresponding original piece.

    Each fragment lies on the KARAOKE timeline; via
    :func:`align.project_time_reverse` the corresponding window in the
    original is determined. The original is resampled once to the sample
    rate of the karaoke track (in the cache, reused as long as the
    original does not change) so that :func:`karaoke.apply_restore` can
    mix the two without further conversion. Fragments for which the
    original is missing or the projection fails are skipped (with a
    warning) instead of letting the whole processing fail.
    """
    if not intervals:
        return []
    import numpy as np
    from . import audio as audio_module

    try:
        original_source = filesystem.find_audio_file(
            context.paths.input_dir, TRACK_ORIGINAL)
        if original_source is None:
            logger.warning(t("log_restore_no_original"), len(intervals))
            return []
        original_wav = prepare_track(context, TRACK_ORIGINAL)
        properties = ffmpeg.probe(original_wav)
        if properties.sample_rate != karaoke_sample_rate:
            resampled = (context.paths.cache_dir
                        / "original_for_restore.wav")
            checksum = filesystem.file_sha1(original_source)
            step = context.store.get_step("original_restore_resample")
            if not (step and step.get("sha1") == checksum
                    and step.get("sample_rate") == karaoke_sample_rate
                    and resampled.exists()):
                ffmpeg.resample_to_match(
                    original_wav, resampled, karaoke_sample_rate,
                    properties.channels or 2)
                context.store.set_step("original_restore_resample", {
                    "sha1": checksum, "sample_rate": karaoke_sample_rate})
            original_wav = resampled
        data, sample_rate = audio_module.load_audio(original_wav)
    except Exception as exc:  # noqa: BLE001 - must never break step 4
        logger.exception(t("log_restore_unusable"), exc)
        return []

    regions = ()
    try:
        regions = alignment_regions(context)
    except PipelineError:
        pass  # No alignment (e.g. Demucs karaoke, offset 0) -> ok.

    prepared: list[tuple[karaoke.RestoreInterval, np.ndarray, int]] = []
    for interval in intervals:
        orig_start = align.project_time_reverse(interval.start, regions)
        orig_end = align.project_time_reverse(interval.end, regions)
        i0 = audio_module.seconds_to_samples(orig_start, sample_rate)
        i1 = audio_module.seconds_to_samples(orig_end, sample_rate)
        i0 = max(0, min(i0, data.shape[0]))
        i1 = max(0, min(i1, data.shape[0]))
        if i1 <= i0:
            logger.warning(t("log_restore_empty"), interval.label)
            continue
        prepared.append((interval, data[i0:i1], sample_rate))
    return prepared


def _overlaps(a_start: float, a_end: float,
              b_start: float, b_end: float) -> bool:
    """Do two windows overlap each other (with small tolerance)?"""
    return a_start < b_end - 0.01 and a_end > b_start + 0.01


def run_export(context: AppContext) -> Path:
    """Step 5: export the end result in the source format."""
    karaoke_step = context.store.get_step("karaoke")
    if karaoke_step is None or not Path(karaoke_step["wav"]).exists():
        raise PipelineError(t("err_no_edited_karaoke"))
    source_step = context.store.get_step(f"source_{TRACK_KARAOKE}")
    if source_step is None:
        raise PipelineError(t("err_no_source_properties"))
    properties = ffmpeg.AudioProperties(**source_step["properties"])
    suffix = Path(source_step["path"]).suffix
    return export_module.export_result(Path(karaoke_step["wav"]), properties,
                                       suffix, context.paths.output_dir)


def build_coupling(context: AppContext) -> dict | None:
    """Shared sentence coupling for both timing and the editor.

    Delivers everything that is needed to couple the karaoke text to
    the lyrics: the timed lines, the quality, the mapping and the
    original lines (text + projected time span). This way
    ``generate_timing`` and the timing editor guaranteed use the same
    coupling.

    Returns:
        Dict or ``None`` if lyrics/transcription is missing.
    """
    from . import karaoke_text
    from . import timing as timing_module

    text_path = karaoke_text_path(context)          # B125: fallback lyrics
    if text_path is None:
        return None
    karaoke_lines = karaoke_text.parse_lines(text_path)
    if not karaoke_lines:
        return None
    detailed = _original_lines_detailed(context)
    if detailed is None:
        return None

    original_blocks: list[list[tuple[float, float, bool]]] = [[]]
    previous_block = detailed[0]["block"]
    for line in detailed:
        if line["block"] != previous_block:
            original_blocks.append([])
            previous_block = line["block"]
        original_blocks[-1].append(
            (line["start"], line["end"], line["reliable"]))
    # No empty blocks can arise on this side: ``detailed`` only counts a
    # block boundary where a line really follows (B375 already leaves the
    # [bg]-only lines out of that counting), so a skipped block never
    # gets a number of its own here. The filter is a safety net.
    original_blocks = [b for b in original_blocks if b]

    # B264: simultaneous backing vocals ([bg] in the karaoke text) do not
    # count in the sentence coupling - they sound at the same time as the
    # previous line instead of after it, and would disturb the block/line
    # count just like an uncounted crowd block (B260). They are hereafter
    # uncoupled from ``couple_timing`` and hung on their previous non-bg line.
    bg_lines = [line for line in karaoke_lines if line.bg]
    coupled_lines = [line for line in karaoke_lines if not line.bg]

    # B488: a block that holds nothing but whole-[bg] lines becomes
    # empty here, and throwing it away shifts every block after it. That
    # is enough to make the block counts differ (Lied R: 11 against 12),
    # and then ``couple_timing`` falls back on its coarsest branch -
    # spreading all the karaoke lines evenly over all the lyrics lines.
    # Measured on the user's own texts that skipped two lyrics lines and
    # put everything after them one line out; keeping the empty block as
    # an empty place gives 53 out of 53 exactly right. The block still
    # counts as a place; it just has nothing in it.
    blocks_in_text = (max((line.block for line in karaoke_lines),
                          default=-1) + 1)
    karaoke_blocks: list[list] = [[] for _ in range(blocks_in_text)]
    for line in coupled_lines:
        karaoke_blocks[line.block].append(line)
    # Trailing empty blocks say nothing about the order, and an original
    # text that simply has fewer blocks should not trip over them.
    while karaoke_blocks and not karaoke_blocks[-1] \
            and len(karaoke_blocks) > len(original_blocks):
        karaoke_blocks.pop()

    step = context.store.get_step("align")
    regions = (align.regions_from_dicts(step["regions"])
               if step is not None else ())
    project = lambda seconds: align.project_time(seconds, regions)  # noqa: E731
    duration = _karaoke_duration(context)

    # Rough word times per flat original line index (same order as
    # ``original_blocks``); couple_timing projects them itself. This way the
    # syllables follow the rhythm of the original (B66).
    # B471: the coupling keeps the FILTERED set - a line whose word
    # times are all estimates gets its rhythm from B234 (see B313). Only
    # the editor sees them all.
    original_words = {index: line["words"]
                      for index, line in enumerate(detailed)
                      if line.get("words") and not line.get("words_estimated")}
    beats = _karaoke_beats(context)

    timed, quality, mapping = timing_module.couple_timing(
        karaoke_blocks, original_blocks, duration=duration, project=project,
        original_words=original_words, beats=beats)

    overrides = original_overrides(context)

    def _original_span(index: int) -> tuple[float, float]:
        """Where lyrics sentence ``index`` lies on the karaoke timeline.

        A hand correction on that sentence wins (B283), so a bg line
        that hangs on it in B509 follows the correction instead of the
        raw measurement.
        """
        line = detailed[index]
        key = str(line["line_no"])
        if key in overrides and len(overrides[key]) == 2:
            return float(overrides[key][0]), float(overrides[key][1])
        return (max(0.0, project(line["start"])),
                max(0.0, project(line["end"])))

    # B509: a whole-[bg] line is kept out of the counting, and up to
    # v0.145.0 that also left it out of the coupling - so it stood in
    # the lane as an orphan, with the lyrics sentence that belongs to it
    # standing there as a second orphan right across from it. Give them
    # each other back, and the bg line its own time with it.
    mapping = _couple_bg_lines(mapping, detailed, bg_lines)
    if bg_lines:
        own_spans = {}
        for line in bg_lines:
            oi = mapping.get(line.index)
            if oi is not None:
                own_spans[line.index] = _original_span(oi)
        timed = timing_module.attach_bg_lines(timed, bg_lines, own_spans)

    original_items = []
    for index, line in enumerate(detailed):
        start, end = _original_span(index)
        original_items.append({"text": line["text"],
                               "line_no": line["line_no"],
                               "bg": line.get("bg_text", ""),
                               "start": float(start), "end": float(end)})
    equal = ([len(b) for b in original_blocks]
             == [len(kb) if all(l.crowd for l in kb)
                 else len([l for l in kb if not l.crowd])
                 for kb in karaoke_blocks])
    # B450: the word times of the original, projected onto the karaoke
    # timeline like the line spans above. The stress editor needs them:
    # a word boundary in the original is MEASURED, and that is the only
    # honest thing to hang the coupling on.
    projected_words = {}
    for index, line in enumerate(detailed):
        spans = line.get("words") or []
        if spans:
            projected_words[index] = [
                (text, max(0.0, project(float(start))),
                 max(0.0, project(float(end))))
                for text, start, end in spans]
    return {"karaoke_lines": karaoke_lines, "timed": timed,
            "quality": quality, "mapping": mapping,
            "original_items": original_items,
            "original_words": projected_words,
            "same_structure": equal}


def _couple_bg_lines(mapping: dict[int, int], detailed: Sequence[dict],
                     bg_lines: Sequence) -> dict[int, int]:
    """Couple whole-``[bg]`` lines to a leftover lyrics sentence (B509).

    Deliberately by POSITION and not by block number: the two texts each
    count their own blank lines, and leaning on those numbers being
    equal is exactly the kind of assumption that broke at B488. A bg
    line looks at the coupled karaoke line before it and the one after
    it, and takes the first still uncoupled lyrics sentence that lies
    between their sentences. That keeps the order intact and needs no
    agreement about numbering.

    Nothing to be had, then nothing happens: a bg line without a
    counterpart keeps hanging on its neighbour (``attach_bg_lines``),
    which is the right picture for one that really does sound along.
    """
    out = dict(mapping)
    claimed = set(out.values())
    free = [index for index in range(len(detailed)) if index not in claimed]
    for line in sorted(bg_lines, key=lambda item: item.index):
        if not free:
            break
        before = max((row for row in out if row < line.index), default=None)
        after = min((row for row in out if row > line.index), default=None)
        low = out[before] if before is not None else -1
        high = out[after] if after is not None else len(detailed)
        chosen = next((index for index in free if low < index < high), None)
        if chosen is None:
            continue
        free.remove(chosen)
        out[line.index] = chosen
    return out


def place_between_neighbours(items: list[dict],
                             minimum: float = 0.4) -> None:
    """Put original sentences without a karaoke line between their
    neighbours (B489). Changes ``items`` in place.

    A coupled sentence takes the time of the karaoke line it belongs to;
    an uncoupled one used to fall back on its OWN time from the original.
    Those are two different clocks - at "Lied R" they are half a minute
    apart - so such a sentence jumped visibly forwards in the lane and
    stood in the wrong order. Between the neighbours it is at least in
    the right place, and the whole lane is on one clock.

    ``items`` must be in the order of the original text; ``rows`` says
    whether a sentence is coupled.
    """
    anchors = [index for index, item in enumerate(items) if item.get("rows")]
    if not anchors or len(anchors) == len(items):
        return
    for index, item in enumerate(items):
        if item.get("rows"):
            continue
        before = max((a for a in anchors if a < index), default=None)
        after = min((a for a in anchors if a > index), default=None)
        # Which number in a row of uncoupled sentences is this one? They
        # each need their own little place - laying them on top of each
        # other makes them impossible to point at, and a row of them is
        # exactly what happens at the end of a song.
        place = index - (before if before is not None else -1)
        total = ((after if after is not None else len(items))
                 - (before if before is not None else -1))
        if before is not None and after is not None:
            low = float(items[before]["end"])
            high = float(items[after]["start"])
            gap = high - low
            if gap >= total * minimum:
                width = gap / total
                start = low + place * width - width
                item["start"] = round(start, 3)
                item["end"] = round(start + width, 3)
            else:
                # Not enough room between the neighbours: side by side on
                # the minimum, starting at the left neighbour.
                start = low + (place - 1) * minimum
                item["start"] = round(start, 3)
                item["end"] = round(start + minimum, 3)
        elif before is not None:              # tail of the song
            start = float(items[before]["end"]) + (place - 1) * minimum
            item["start"], item["end"] = round(start, 3), round(
                start + minimum, 3)
        else:                                  # head of the song
            end = float(items[after]["start"])
            start = max(0.0, end - (total - place + 1) * minimum)
            item["start"] = round(start, 3)
            item["end"] = round(start + minimum, 3)


def editor_originals(context: AppContext) -> tuple[list, dict]:
    """Original sentences + coupling for the timing editor.

    Uses the fresh coupling if the transcription is available and keeps
    it permanently; if the transcription has been cleared after a
    restart, it falls back on the earlier kept coupling so that the
    editor can show the original-text lane after all (without Whisper
    again).
    """
    coupling = build_coupling(context)
    if coupling is not None:
        context.store.set_step("coupling", {
            "original_items": coupling["original_items"],
            "mapping": {str(k): v for k, v in coupling["mapping"].items()}})
        return coupling["original_items"], coupling["mapping"]
    step = context.store.get_step("coupling")
    if step:
        mapping = {int(k): v for k, v in step.get("mapping", {}).items()}
        return step.get("original_items", []), mapping
    return _originals_without_coupling(context)


def _originals_without_coupling(context: AppContext) -> tuple[list, dict]:
    """The original text lane when there is no coupling at all (B471).

    An empty lane used to be the answer, and then the user cannot put
    anything in its place - which is exactly what he needs the editor
    for. The text is in ``lyrics.txt``; only its timing is unknown.
    Every sentence is spread evenly over the song so it is at least
    visible and can be dragged to where it belongs, and every karaoke
    line is coupled proportionally so it has something to hang on.

    Deliberately only here and not in ``_original_lines_detailed``: the
    render timing has its own road for this case (``fallback_even``) and
    must not start following a guess.
    """
    from . import karaoke_text

    path = context.paths.input_dir / song_text.LYRICS_FILENAME
    if not path.exists():
        return [], {}
    per_line: dict[int, list[str]] = {}
    for word in song_text.load_lyrics(path):
        if getattr(word, "bg", False):
            continue
        per_line.setdefault(word.line, []).append(word.text)
    numbers = sorted(per_line)
    if not numbers:
        return [], {}
    total = _karaoke_duration(context) or float(len(numbers))
    width = total / len(numbers)
    items = [{"text": " ".join(per_line[number]), "line_no": number,
              "start": index * width, "end": (index + 1) * width}
             for index, number in enumerate(numbers)]
    text_path = karaoke_text_path(context)
    karaoke_lines = (karaoke_text.parse_lines(text_path)
                     if text_path is not None else [])
    mapping = {line.index: min(len(numbers) - 1,
                               index * len(numbers) // max(1, len(karaoke_lines)))
               for index, line in enumerate(karaoke_lines)}
    logger.warning(t("log_original_times_guessed"), len(items))
    return items, mapping


def language_for_original(context: AppContext) -> str:
    """The language the original was transcribed in, for the editor.

    Falls back to Dutch: the phonetic division needs a language, and a
    view may not fail over it.
    """
    code = _language_for(context, TRACK_ORIGINAL)
    return code if code and code != "auto" else "nl"


def original_pieces(text: str, words, language: str = "nl"):
    """The original sentence as timed phonetic pieces (B450).

    Built the way the honesty of the data allows: the WORD boundaries
    come from the forced alignment, so those are measured, and inside a
    word the duration is divided over the phonetic segments by the same
    rule the karaoke side uses (B241). So the editor shows measurement
    where there is measurement and a model where there is none - and the
    two rows are comparable because they were divided the same way.

    Falls back to an even division over the sentence when the word count
    does not match the text (punctuation, an odd token): then the shape
    is still right and only the rhythm within the sentence is a guess.
    """
    from . import timing as timing_module

    spans = [(str(t), float(a), float(b)) for t, a, b in (words or ())
             if b > a]
    if not text.strip():
        return []
    start = spans[0][1] if spans else 0.0
    end = spans[-1][2] if spans else start + 1.0
    line = timing_module.timedline_from_text(0, text, start, end)
    grouped: list[list] = []
    for syllable in line.syllables:
        if not grouped or syllable.text.startswith(" "):
            grouped.append([syllable])
        else:
            grouped[-1].append(syllable)
    if len(grouped) == len(spans):
        placed = []
        for group, (_text, low, high) in zip(grouped, spans):
            step = (high - low) / len(group)
            for number, syllable in enumerate(group):
                placed.append(replace(syllable,
                                      start=low + number * step,
                                      end=low + (number + 1) * step))
        line = replace(line, syllables=tuple(placed))
    line = timing_module.apply_default_stress([line])[0]
    try:
        line = timing_module.apply_phonetic_timing([line],
                                                   language=language)[0]
    except Exception:  # noqa: BLE001 - a view may never break
        logger.exception(t("log_phonetic_timing_skipped"))
    return list(timing_module.mark_held([line])[0].syllables)


def stress_anchors(context: AppContext) -> dict:
    """The coupled pieces per sentence (B450).

    ``{karaoke line number: {karaoke piece: original piece}}``. Kept as
    the user's own judgement, so it survives everything the automatic
    side does.
    """
    step = context.store.get_step("stress_anchors") or {}
    out: dict[int, dict[int, int]] = {}
    for line, pairs in (step.get("list") or {}).items():
        try:
            out[int(line)] = {int(k): int(v) for k, v in dict(pairs).items()}
        except (TypeError, ValueError):
            continue
    return out


def set_stress_anchors(context: AppContext, anchors: dict) -> None:
    """Keep the coupled pieces per sentence (B450)."""
    context.store.set_step("stress_anchors", {"list": {
        str(line): {str(k): int(v) for k, v in dict(pairs).items()}
        for line, pairs in (anchors or {}).items() if pairs}})


def _karaoke_duration(context: AppContext) -> float | None:
    """Duration of the karaoke audio in seconds, if determinable."""
    audio = filesystem.find_audio_file(context.paths.input_dir,
                                       TRACK_KARAOKE)
    if audio is None or not ffmpeg.is_available():
        return None
    try:
        return ffmpeg.probe(audio).duration
    except ffmpeg.FfmpegError:
        return None


def _karaoke_beats(context: AppContext) -> list[float] | None:
    """Beat times of the karaoke audio (for chant timing), or ``None``.

    The beats are already on the karaoke timeline and do not have to be
    projected. With missing librosa or audio: ``None`` (fallback).
    """
    from . import rhythm
    if not rhythm.is_available():
        return None
    audio = filesystem.find_audio_file(context.paths.input_dir,
                                       TRACK_KARAOKE)
    if audio is None:
        return None
    beats = rhythm.beat_times(audio)
    return beats or None


#: This far a held final note may run on at most if there is no
#: next entry that bounds it (B194).
_HELD_MAX_EXTEND_S = 3.0

#: Shortest plausible duration of a filler line (la-la, na-na) placed on
#: energy pulses (B310). Below this the placement is not a time slot but
#: an artefact of the onset detection; the whole series is then divided
#: over the sung time instead. Even the shortest shout ("Ole!") lasts
#: longer than four tenths of a second.
_FILLER_LINE_MIN_S = 0.4

#: Shortest silence that may count as the instrumental between two
#: blocks (B523). Below this the singing is still one stretch and there
#: is nothing to clip.
_BLOCK_GAP_MIN_S = 2.0

#: Shortest part left after clipping on a block boundary (B523). A
#: sliver cannot carry a line; the run then keeps the whole window.
_BLOCK_PART_MIN_S = 0.3


def _line_blocks(lines_present: Sequence[int],
                 bg_only: frozenset[int]) -> list[int]:
    """Block number per entry of ``lines_present``.

    A block boundary is a gap in the lyrics line numbers (a blank line
    in ``lyrics.txt``).

    B375: a [bg] line drops out of ``lines_present`` (those words sound
    at the same time as the neighbouring line and do not count as a line
    of their own), and such an omitted line gives exactly the same gap
    as a blank line. Every [bg] line in the middle of a block therefore
    cut that block in two: measured on "Lied K" the
    lyrics went from 8 to 13 blocks while the karaoke kept 8, and the
    one-to-one coupling flipped from 47 to 0 lines of high quality. The
    manual promised the opposite. The skipped bg lines therefore do not
    count towards the gap.
    """
    blocks: list[int] = []
    block = 0
    for index, line_no in enumerate(lines_present):
        if index > 0:
            previous = lines_present[index - 1]
            skipped = sum(1 for n in range(previous + 1, line_no)
                          if n in bg_only)
            if line_no - previous - skipped > 1:
                block += 1
        blocks.append(block)
    return blocks


def _block_gap(active: Sequence[tuple[float, float]],
               low: float, high: float
               ) -> tuple[float, float] | None:
    """Where the singing between ``low`` and ``high`` falls apart (B523).

    Between two blocks there is an instrumental, and that instrumental
    belongs to no block at all - so no line may be placed in it. Returns
    ``(end of the singing before it, start of the singing after it)``,
    or ``None`` when there is no silence long enough to be that
    instrumental.

    The longest silence and not the first: a block can hold a pause of
    its own, and the break between two blocks is longer than any of
    them. What this cannot do is tell a short burst of energy inside the
    instrumental from a real short line - if such a burst sits close
    behind the block, the boundary lands behind IT instead. That costs
    at most the seconds up to that burst, which is a smaller error than
    the whole instrumental, and it is why the constant below is a
    measured minimum and not a guess.
    """
    within = [(max(s, low), min(e, high)) for s, e in active
              if e > low + 0.05 and s < high - 0.05]
    within = [(s, e) for s, e in within if e > s]
    if len(within) < 2:
        return None
    silence, at = max((within[k + 1][0] - within[k][1], k)
                      for k in range(len(within) - 1))
    if silence < _BLOCK_GAP_MIN_S:
        return None
    return within[at][1], within[at + 1][0]


def _held_ceiling(active: Sequence[tuple[float, float]],
                  blocks: Sequence[int] | None, index: int,
                  end: float, ceil: float, total: int) -> float:
    """How far a held note may run on at most (B523).

    The last line of a block has the FIRST LINE OF THE NEXT BLOCK as its
    ceiling, and in between lies an instrumental. A phantom voice in
    that instrumental reads as a held note and the line is stretched
    right over it: measured on "Lied H" lyrics
    line 16 grew from 66.39-67.60 to 66.39-83.31, and the timing built
    on that put its START at 73.0 s while the user had it at 66.13.
    The instrumental belongs to no block, so the ceiling stops where the
    singing of this block stops.
    """
    if blocks is None or index + 1 >= total \
            or blocks[index] == blocks[index + 1]:
        return ceil
    found = _block_gap(active, end, ceil)
    if found is not None and end < found[0] < ceil:
        return found[0]
    return ceil


def _filler_parts(start: int, stop: int, low: float, high: float,
                  blocks: Sequence[int] | None,
                  active: Sequence[tuple[float, float]],
                  total: int) -> list[tuple[int, int, float, float]]:
    """Split a run of unplaced lines on the block boundary (B523).

    A series of lines without a time of its own is placed on the vocal
    energy between the two anchors around it. When a block boundary lies
    in between, that space holds an instrumental that belongs to neither
    block - and the energy in it (a phantom voice, a held synth) pulls a
    line right into it. Measured on "Lied H":
    line 16 of the lyrics moved to 73.98-83.31 while the singing that
    belongs to it lies at 66.09-68.39, where the user had put it by hand.

    The windows a line may be spread over are therefore clipped at the
    block boundary - the same thought as the block barrier for anchors
    (B251), but for the placing. Returns one part per side, or the whole
    run unchanged when there is nothing to clip.
    """
    whole = [(start, stop - start, low, high)]
    if blocks is None or start <= 0 or stop >= total:
        return whole
    before_block, after_block = blocks[start - 1], blocks[stop]
    if before_block == after_block:
        return whole
    before = [k for k in range(start, stop) if blocks[k] == before_block]
    after = [k for k in range(start, stop) if blocks[k] == after_block]
    if len(before) + len(after) != stop - start:
        return whole                     # a whole block of its own in between
    if before and after and before[-1] > after[0]:
        return whole
    found = _block_gap(active, low, high)
    if found is None:
        return whole
    ends, resumes = found
    parts: list[tuple[int, int, float, float]] = []
    if before and ends - low >= _BLOCK_PART_MIN_S:
        parts.append((before[0], len(before), low, ends))
    # The far side starts where the singing of the next block starts,
    # not where this block's singing stopped - otherwise the first line
    # of that block may be placed in the instrumental after all.
    if after and high - resumes >= _BLOCK_PART_MIN_S:
        parts.append((after[0], len(after), resumes, high))
    if len(parts) != bool(before) + bool(after):
        return whole
    return parts


def _refine_with_vocals(context: AppContext, lines_present: list[int],
                        filled: list[tuple[float, float]],
                        reliable: list[bool],
                        per_line_word_spans: dict[int, list],
                        blocks: Sequence[int] | None = None) -> None:
    """Refine the original line timing with the vocal stem energy (B194/B209).

    B194: stretch reliable lines up to where the vocals really stop
    (held notes), bounded by the next entry. B209: place a series of
    non-transcribed filler lines on the energy pulses in the gap between
    the surrounding anchors; if that does not work, the interpolation
    stays. B523: with ``blocks`` (the block number per line) such a
    series is not spread across a block boundary - see
    :func:`_filler_parts`. Mutates ``filled`` and ``per_line_word_spans``
    in place.
    """
    if not context.config.advanced.vocal_analysis:
        return
    from . import rhythm
    if not rhythm.is_available():
        return
    vocals = ensure_original_vocals(context)
    if vocals is None:
        return

    from . import timing as timing_module
    active = rhythm.active_windows(vocals)

    # B194: lengthen held notes of reliable lines.
    for i, betrouwbaar in enumerate(reliable):
        if not betrouwbaar:
            continue
        start, end = filled[i]
        ceil = (filled[i + 1][0] if i + 1 < len(filled)
                else end + _HELD_MAX_EXTEND_S)
        capped = _held_ceiling(active, blocks, i, end, ceil, len(filled))
        if capped < ceil - 0.05:
            logger.info(t("log_held_note_capped"),
                        lines_present[i], ceil, capped)
        ceil = capped
        new = rhythm.held_note_end(vocals, start, end, ceil)
        if new is not None and new > end + 0.05:
            filled[i] = (start, new)
            spans = per_line_word_spans.get(lines_present[i])
            if spans:
                wt, ws, we = spans[-1]
                if new > we:
                    spans[-1] = (wt, ws, new)

    # B209/B310: place filler line series on energy pulses.
    i = 0
    while i < len(filled):
        if reliable[i]:
            i += 1
            continue
        j = i
        while j < len(filled) and not reliable[j]:
            j += 1
        prev_end = filled[i - 1][1] if i > 0 else filled[i][0]
        if j < len(filled):
            next_start = filled[j][0]
        else:
            # B310: a series at the END of the song has no anchor after it,
            # so ``interpolate_spans`` simply keeps marching on with the
            # median line duration. With short coupled lines that stops
            # far too early - the whole la-la outro is then squeezed into
            # the first seconds and the rest of the sung time stays empty;
            # with many lines it runs on past the end of the song. Where
            # the singing really stops IS known: the end of the last
            # vocal-active window. Deliberately not ``active_end``: that
            # looks for the first sustained silence after ``prev_end``
            # (B277) and would therefore already stop at the first pause
            # WITHIN the outro.
            sung_end = active[-1][1] if active else 0.0
            next_start = max(filled[j - 1][1], sung_end)
        # B523: an instrumental between two blocks belongs to no block,
        # so no line may be placed in it. The run is cut on that
        # boundary and each side keeps its own part of the space.
        parts = _filler_parts(i, j, prev_end, next_start, blocks, active,
                              len(filled))
        if len(parts) > 1 or (parts and parts[0][2:] != (prev_end, next_start)):
            logger.info(t("log_block_gap_clipped"),
                        j - i, prev_end, next_start, len(parts))
        for first, count, low, high in parts:
            if high <= low + 0.3 or count < 1:
                continue
            slots: list[tuple[float, float]] = []
            onsets = sorted(rhythm.energy_onsets(
                vocals, low, high, expected=count))
            if len(onsets) >= count:
                slots = [(onsets[k],
                          onsets[k + 1] if k + 1 < count else high)
                         for k in range(count)]
                # B310: quality gate. Onset detection also finds pulses in
                # a passage where nothing is sung at all (the reverb tail
                # of a note, the build-up of the following instrument),
                # and then squeezes a line into a fraction of a second
                # while the rest of the passage stays empty. An
                # implausibly short line is the sign that the pulses do
                # not describe this passage; the placement is then
                # discarded as a whole - not per line, because the lines
                # follow each other and one wrong boundary displaces its
                # neighbours as well.
                shortest = min(e - s for s, e in slots)
                if shortest < _FILLER_LINE_MIN_S:
                    logger.info(
                        t("log_onset_placement_rejected"),
                        shortest, count, low, high)
                    slots = []
                else:
                    logger.info(
                        t("log_filler_on_energy"), count, low, high)
            if not slots:
                # B310: no usable pulses. Formerly nothing happened at all
                # then and the even interpolation stayed - including over
                # instrumental silences. Dividing over the SUNG time is a
                # better estimate: the lines then stand where something is
                # really being sung, even if the pulses themselves are not
                # distinguishable.
                within = [(max(s, low), min(e, high))
                          for s, e in active
                          if e > low + 0.05 and s < high - 0.05]
                slots = timing_module.spread_over_active(count, within)
                if slots:
                    logger.info(
                        t("log_filler_spread"),
                        count, low, high, len(onsets))
            for k, (s, e) in enumerate(slots):
                filled[first + k] = (s, max(s + 0.1, e))
        i = j

    # B224: shorten lines that run on into a vocals-empty area to where the
    # vocals really stop (prevents na-na's/lines over silent parts).
    # B492: measured with ``last_energy`` and no longer with
    # ``active_end``. That one stops at the silent gap before the last
    # sound episode, so a sentence with a pause of its own in the middle
    # ("Lied Q ... kom maar, Lied Q") was cut back to the part
    # BEFORE the pause - the user had to drag every such line over its
    # second half by hand. What has to be trimmed here is trailing
    # silence, and that is what the last singing in the window says.
    for idx in range(len(filled)):
        start, end = filled[idx]
        ae = rhythm.last_energy(vocals, start, end)
        if ae is not None and end - ae >= 1.5:
            new_end = max(start + 0.3, ae)
            if new_end < end:
                filled[idx] = (start, round(new_end, 3))
                spans = per_line_word_spans.get(lines_present[idx])
                if spans:
                    wt, ws, we = spans[-1]
                    if we > new_end:
                        spans[-1] = (wt, ws, round(max(ws + 0.05,
                                                       new_end), 3))


def _apply_energy_word_timing(context: AppContext, timed):
    """Refine the word/pause timing within each line on the vocal energy
    (B234).

    Distributes per line the words over the vocals-active subwindows
    (pauses between words thus appear in the timing). The vocal stem is
    on the original timeline and is projected to the karaoke timeline.
    Neat fallback (unchanged) if the vocal stem/analysis is missing.
    """
    if not context.config.advanced.vocal_analysis:
        return timed
    from . import rhythm
    from . import timing as timing_module
    if not rhythm.is_available():
        return timed
    vocals = ensure_original_vocals(context)
    if vocals is None:
        return timed
    windows = rhythm.active_windows(vocals)
    if not windows:
        return timed
    step = context.store.get_step("align")
    if step is not None and step.get("regions"):
        regions = align.regions_from_dicts(step["regions"])
        project = lambda s: align.project_time(s, regions)  # noqa: E731
    else:
        project = lambda s: s                                # noqa: E731
    win_k = [(project(s), project(e)) for s, e in windows]
    uit = []
    for line in timed:
        s, e = line.start, line.end
        binnen = [(max(a, s), min(b, e)) for a, b in win_k
                  if b > s + 0.05 and a < e - 0.05]
        binnen = [(a, b) for a, b in binnen if b - a > 0.05]
        if len(binnen) >= 2 and not line.crowd:
            # B290: catch per line. The caller has a safety-net except
            # around the whole step, but that switched off the energy
            # word timing of the complete song at one problem line. Now
            # only that one line loses its refinement and the others keep it.
            try:
                uit.append(timing_module.distribute_over_windows(line, binnen))
            except Exception:  # noqa: BLE001 - one line may not break the rest
                logger.exception(
                    t("log_energy_word_line_skipped"),
                    line.index, line.text)
                uit.append(line)
        else:
            uit.append(line)
    return tuple(uit)


def _bg_only_lines(context: AppContext) -> frozenset[int]:
    """Line numbers that consist entirely of [bg] words (B375).

    Those lines sound at the same time as their neighbouring line and
    therefore get no place of their own in the sentence coupling - but
    they may not make a block boundary either.
    """
    lyrics = _lyrics_for_boundaries(context)
    if not lyrics:
        return frozenset()
    per_line: dict[int, list] = {}
    for word in lyrics:
        per_line.setdefault(word.line, []).append(word)
    return frozenset(line for line, words in per_line.items()
                     if words and all(w.bg for w in words))


def _original_lines_detailed(context: AppContext) -> list[dict] | None:
    """Per lyrics line: text, window (interpolated), reliable,
    block. ``None`` if lyrics/transcription is missing."""
    from . import timing as timing_module

    try:
        segments = load_segments(context, TRACK_ORIGINAL)
    except PipelineError:
        return None
    aligned = _lyrics_alignment(context, segments)
    if aligned is None:
        return None

    per_line_words: dict[int, list[str]] = {}
    bg_text: dict[int, list[str]] = {}
    per_line_times: dict[int, list[tuple[float, float]]] = {}
    per_line_word_spans: dict[int, list[tuple[str, float, float]]] = {}
    for word in aligned:
        # B264: simultaneous backing vocals ([bg] in lyrics.txt) do not
        # count as an own lyrics line - those sound at the same time as the
        # surrounding line instead of after each other, and would otherwise
        # disturb the sentence coupling just like an uncounted crowd block
        # (B260). The text does stay available via ``bg_lyrics`` (B263/B258).
        if word.lyric.bg:
            # B485: the background piece is not timed and does not count
            # in the coupling (B264), but it IS part of the sentence and
            # belongs on screen in the editor. Only for a line that also
            # has lead words - a line that is background from beginning
            # to end stays out, otherwise it would count as an extra
            # original line and pull the block counting askew.
            bg_text.setdefault(word.lyric.line, []).append(word.lyric.text)
            continue
        per_line_words.setdefault(word.lyric.line, []).append(
            word.lyric.text)
        if word.start is not None:
            # B313: an ESTIMATED time (measured on the vocal stem, not
            # coupled to a recognised word) does count for the word
            # rhythm within the line - that is exactly what it is for -
            # but not for the judgement of whether this line is
            # reliable. Otherwise a guess would silently gain the weight
            # of a measurement: the line would count as reliable, get
            # stretched by B194, and be passed over by the energy
            # placement of B209/B310 that is meant precisely for it.
            if not word.estimated:
                per_line_times.setdefault(word.lyric.line, []).append(
                    (word.start, word.end))
            per_line_word_spans.setdefault(word.lyric.line, []).append(
                (word.lyric.text, float(word.start), float(word.end)))
    # B313: for a line without a single real coupling the LINE timing
    # comes from the energy placement further down (B209/B310). Word
    # times estimated separately could then fall outside that window and
    # contradict it; such a line gets its word rhythm from B234 instead.
    # B471: those word times used to be THROWN AWAY here, and with them
    # the line disappeared from the original lane of the editor - which
    # is exactly the case in which the user needs to see it, because a
    # bad coupling is what he is there to correct. They are kept and
    # marked instead: the timing still ignores them (see
    # ``original_words`` in ``build_coupling``), the editor shows them.
    estimated_only = {ln for ln in per_line_word_spans
                      if ln not in per_line_times}

    lines_present = sorted(per_line_words)
    if not lines_present:
        return None

    raw = [(min(s for s, _ in per_line_times[ln]),
            max(e for _, e in per_line_times[ln]))
           if ln in per_line_times else (None, None)
           for ln in lines_present]
    reliable = [span[0] is not None for span in raw]
    # B392: hand the measured singing to the interpolation, so a hole in
    # the middle of the song is filled the way B336 already fills the
    # tail - on the windows instead of on a straight line.
    filled = timing_module.interpolate_spans(raw, _vocal_windows(context))
    if not filled:
        # No usable time at all. The TIMING then keeps its old road
        # (``fallback_even`` in ``generate_timing``); the editor gets its
        # own safety net, see ``editor_originals`` (B471).
        return None

    # B523: which block a line belongs to has to be known BEFORE the
    # placement, because the placement may not cross a block boundary.
    bg_only = _bg_only_lines(context)
    blocks = _line_blocks(lines_present, bg_only)

    # Vocal stem energy: lengthen held notes (B194) and place non-
    # transcribed filler lines (na-na) on their energy pulses
    # (B209). If the analysis fails, the interpolation stays.
    try:
        _refine_with_vocals(context, lines_present, filled, reliable,
                            per_line_word_spans, blocks)
    except Exception:  # noqa: BLE001 - analysis must never break the timing
        logger.exception(t("log_vocal_refine_skipped"))

    detailed: list[dict] = []
    for index, ln in enumerate(lines_present):
        detailed.append({
            # B485: the sentence keeps ITS OWN words. Sticking the
            # background piece onto the text made the word count differ
            # from the measured word windows, and then the stress editor
            # (B450) fell back on spreading evenly - on exactly the
            # sentences this release is about. The piece travels
            # alongside, for showing.
            "text": " ".join(per_line_words[ln]),
            "bg_text": " ".join(bg_text.get(ln, [])),
            "start": filled[index][0], "end": filled[index][1],
            "reliable": reliable[index], "block": blocks[index],
            "line_no": ln,
            "words": per_line_word_spans.get(ln, []),
            "words_estimated": ln in estimated_only})
    return detailed


def original_overrides(context: AppContext) -> dict[str, list[float]]:
    """Manual corrections on the original timing (projected), per
    lyrics line number. Empty if there are none."""
    step = context.store.get_step("original_overrides")
    return dict(step.get("list", {})) if step else {}


def set_original_overrides(context: AppContext,
                           overrides: dict[str, list[float]]) -> None:
    """Keep/update the manual original-timing corrections."""
    context.store.set_step("original_overrides", {"list": overrides})


def clear_original_overrides(context: AppContext) -> None:
    """Remove all manual original-timing corrections (reset)."""
    context.store.set_step("original_overrides", {"list": {}})


def karaoke_text_path(context: AppContext) -> Path | None:
    """The song text file to be shown for the video (B125).

    Normally ``karaoke_text.txt`` (the parody). If that is missing, the
    tool falls back on ``lyrics.txt`` so that you can also make a
    karaoke video of the original without a separate karaoke text.
    ``None`` if neither of the two exists.
    """
    from . import karaoke_text
    kar = context.paths.input_dir / karaoke_text.FILENAME
    if kar.exists():
        return kar
    lyrics = context.paths.input_dir / song_text.LYRICS_FILENAME
    if lyrics.exists():
        return lyrics
    return None


def _original_vocal_windows(context: AppContext) -> list[tuple[float, float]]:
    """The sung windows on the ORIGINAL's own timeline (B442).

    :func:`_vocal_windows` projects onto the karaoke timeline, and that
    is right for everything that works on the karaoke text. It is wrong
    for anything that works on the ORIGINAL vocal stem itself - and the
    chunked transcription does exactly that: it cuts that file and it
    judges word times measured in that file. With an alignment in place
    the projection shifts both, so cuts land beside the real silences
    and correctly heard words get scored as "not on singing" and thrown
    away. Unnoticeable on a first run, where the projection is still the
    identity, and wrong on every re-transcription after that.
    """
    if not context.config.advanced.vocal_analysis:
        return []
    from . import rhythm
    if not rhythm.is_available():
        return []
    vocals = ensure_original_vocals(context)
    if vocals is None:
        return []
    return [(float(start), float(end))
            for start, end in rhythm.active_windows(vocals)]


def _vocal_windows(context: AppContext) -> list[tuple[float, float]]:
    """The sung windows on the KARAOKE timeline (B336).

    The vocal stem lies on the timeline of the original, so every window
    is projected via the alignment. Empty when there is no stem.
    """
    step = context.store.get_step("align")
    regions = (align.regions_from_dicts(step["regions"])
               if step is not None else ())
    return [(align.project_time(start, regions),
             align.project_time(end, regions))
            for start, end in _original_vocal_windows(context)]


def mark_language_word(context: AppContext, kind: str,
                       word: str) -> tuple[bool, str]:
    """Add a word to (or remove it from) a language list (B337).

    ``kind`` is ``"hallucinations"`` or ``"fillers"``. The word lands
    with the AUDIO language of this project, in the shared
    ``languages/`` folder, so every following project in that language
    benefits. Returns ``(added, language)``; ``added`` is ``False`` when
    the word was already there and has now been taken out again.
    """
    from . import phonetics
    language = _language_for(context, TRACK_ORIGINAL)
    if not language or language == "auto":
        language = "nl"
    collection = (context.paths.languages_dir
                  if filesystem.is_writable(context.paths.root) else None)
    normalized = cluster_module.normalize_for_filter(word)
    if phonetics.add_word(language, kind, normalized, collection,
                          _APP_VERSION):
        logger.info(t("log_language_word_added"), normalized, kind, language)
        return True, language
    phonetics.remove_word(language, kind, normalized, collection,
                          _APP_VERSION)
    logger.info(t("log_language_word_removed"), normalized, kind, language)
    return False, language


def _retime_from_templates(context: AppContext, timed: tuple) -> tuple:
    """Repair implausible line timings from a measured template (B380)."""
    from . import timing_template

    try:
        return timing_template.repair(timed, _vocal_windows(context))
    except Exception:  # noqa: BLE001 - de timing mag hier nooit op vallen
        logger.exception(t("log_template_failed"))
        return timed


def _snap_lines_to_onsets(context: AppContext, timed: tuple) -> tuple:
    """Pull estimated line starts to the onsets of the vocal stem (B330).

    The vocal stem lies on the timeline of the ORIGINAL, the timing on
    that of the karaoke, so every onset is projected via the alignment
    first. Without a stem (analysis off, Demucs missing) the timing comes
    back unchanged.
    """
    if not context.config.advanced.vocal_analysis or not timed:
        return timed
    from . import rhythm
    from . import timing as timing_module
    if not rhythm.is_available():
        return timed
    vocals = ensure_original_vocals(context)
    if vocals is None:
        return timed
    moments = rhythm.onsets(vocals)
    if not moments:
        return timed
    step = context.store.get_step("align")
    regions = (align.regions_from_dicts(step["regions"])
               if step is not None else ())
    projected = [align.project_time(moment, regions) for moment in moments]
    period = timing_module.phrase_period(timed)
    result = timing_module.snap_to_onsets(timed, projected, period)
    moved = sum(1 for old, new in zip(timed, result)
                if abs(old.start - new.start) > 0.05)
    if moved:
        logger.info(t("log_lines_snapped"), moved, len(projected))
    return result


def generate_timing(context: AppContext) -> tuple[Path, int, str]:
    """Make best-effort timing (``timing.json``) from the karaoke text.

    Uses the shared sentence coupling (see :func:`build_coupling`);
    without lyrics the lines are distributed evenly over the song.
    Afterwards refine with the timing editor.
    """
    from . import karaoke_text
    from . import timing as timing_module

    sync_input_changes(context)          # B311
    text_path = karaoke_text_path(context)          # B125: fallback lyrics
    if text_path is None:
        raise PipelineError(t("err_no_text_files"))
    lines = karaoke_text.parse_lines(text_path)
    if not lines:
        raise PipelineError(t("err_no_sung_lines"))

    coupling = build_coupling(context)
    if coupling is not None:
        timed = coupling["timed"]
        quality = coupling["quality"]
        # B326: the keys are high/medium/low since the B299 rename; the
        # Dutch words stayed behind here and crashed this step.
        detail = t("timing_detail_coupling").format(
            high=quality["high"], medium=quality["medium"],
            low=quality["low"])
        # Keep the coupling permanently at once, so that the editor shows the
        # original lane also after the cache (transcription) is cleared (B132).
        context.store.set_step("coupling", {
            "original_items": coupling["original_items"],
            "mapping": {str(k): v for k, v in coupling["mapping"].items()}})
    else:
        duration = _karaoke_duration(context) or 240.0
        timed = timing_module.fallback_even(lines, duration)
        detail = t("timing_detail_even")

    # B408: hold on to the span per stage, so the diagnostics can show
    # WHERE a line becomes shorter instead of only that it is short.
    stages: dict[str, list[tuple[float, float]]] = {
        "koppeling": [(line.start, line.end) for line in timed]}

    # Smart clean-up: bound the durations to the base tempo, keep the order
    # monotone, anchor the first sentence on the vocal onset (B106/B130/B133).
    onset = ensure_vocal_onset(context)
    duration = _karaoke_duration(context)
    _gav = context.config.advanced
    timed = timing_module.sanitize_timing(
        timed, first_start=float(onset) if onset is not None else None,
        song_duration=duration,
        blok_barriere=_gav.block_anchor_barrier,
        weight_map={"syllable": _gav.anchor_weight_syllable,
                   "high": _gav.anchor_weight_high,
                   "word": _gav.anchor_weight_word,
                   "onset": _gav.anchor_weight_onset},
        active_windows=_vocal_windows(context))          # B336
    # Fine-tuning on top of the sentence structure (B330): an estimated
    # line start moves to the onset of the singing it belongs to. Never
    # before the structure - see the docstring of ``snap_to_onsets``.
    stages["zinnen"] = [(line.start, line.end) for line in timed]   # B408
    timed = _snap_lines_to_onsets(context, timed)
    # B415: snapping to the vocal onset is a step of its own and should
    # therefore have a column of its own - otherwise two steps that can
    # both shorten a line cannot be told apart.
    stages["inzet"] = [(line.start, line.end) for line in timed]
    # B380: a line whose duration cannot be right takes its timing from
    # the same line elsewhere in the song, where it WAS heard properly.
    # That is exactly where the error sits: repeated lines carry 1.89 s
    # against 0.48 s for unique ones, and towards the end of a song the
    # repetitions pile up.
    timed = _retime_from_templates(context, timed)
    # Default stress per word (B151); manually correctable. The
    # stress weighs in immediately in the best-effort duration division.
    timed = timing_module.apply_default_stress(timed)
    timed = timing_module.redistribute_by_stress(timed)
    # Mark inline crowd words (red) at syllable level (B179a).
    timed = timing_module.apply_inline_crowd(timed, lines)
    # Word/pause timing within the lines on the vocal energy (B234): pauses
    # between words thus come into the timing. Falls back neatly.
    try:
        timed = _apply_energy_word_timing(context, timed)
    except Exception:  # noqa: BLE001 - must never break the timing
        logger.exception(t("log_energy_word_skipped"))
    stages["woorden"] = [(line.start, line.end) for line in timed]   # B408
    # Phonetic segments within each word (B241): vowels longer, final
    # vowel stretched; language-independent. Falls back neatly.
    if context.config.advanced.phonetic_timing:
        try:
            from . import phonetics as _fon
            # Load all earlier collected languages before the build (B241).
            _fon.load_language_dir(context.paths.languages_dir)
            language_code = _language_for(context, TRACK_KARAOKE)
            language_code = language_code if language_code and language_code != "auto" else "nl"
            # Put a missing language_code (e.g. 'fr' for Formidable) in place
            # on the go: always in the project diagnostics (submittable) and,
            # if the collection folder is writable, also there for reuse.
            diag = diagnostics_dir(context) if diagnostics_enabled(context) \
                else None
            collection = (context.paths.languages_dir
                          if filesystem.is_writable(context.paths.root)
                          else None)
            language_code = _fon.ensure_language(
                language_code, diagnostics_dir=diag, collection_dir=collection,
                app_version=_APP_VERSION)
            timed = timing_module.apply_phonetic_timing(timed, language=language_code)
        except Exception:  # noqa: BLE001 - must never break the timing
            logger.exception(t("log_phonetic_timing_skipped"))

    # B441: which syllables are really held. Last, because everything
    # above still moves syllable boundaries and the mark is a judgement
    # on the final spans. The render has drawn a line under a held
    # syllable since B92 and nothing ever set the field - over fourteen
    # thousand syllables there was not one.
    timed = timing_module.mark_held(timed)

    # B500: and then the logic over the whole once more. There is a
    # clean-up halfway (``sanitize_timing``), but after that the energy
    # word timing and the phonetic division still shift everything - and
    # what comes out of there went into the editor and into the render
    # unchecked. Only the real defects are repaired (a line of zero
    # length, two lines over each other) and never by moving a line
    # START: that one is often measured. Before the diagnostics, so that
    # the report describes what is really saved.
    timed, corrected = timing_module.repair_line_edges(timed)
    if corrected:
        logger.warning(t("log_timing_corrected"), corrected)
        # The repair moves ends, so weigh the held notes again - that
        # mark is a judgement about the final spans.
        timed = timing_module.mark_held(timed)

    # Token-thrifty diagnostics in the diagnostics subfolder (B129/B143).
    if diagnostics_enabled(context):
        try:
            source = ("demucs" if context.store.get_meta("karaoke_from_original")
                    else "")
            report = timing_module.timing_report(
                timed, offset=current_offset(context), source_karaoke=source,
                versie=_APP_VERSION, stages=stages)          # B408
            diagnostics_dir(context).mkdir(parents=True, exist_ok=True)
            (diagnostics_dir(context) / "timing_diagnostics.txt").write_text(
                report, encoding="utf-8")
        except OSError:
            logger.warning(t("log_timing_diagnostics_failed"))

    target = context.paths.timing_file
    offset = current_offset(context)
    title = context.config.song.title
    timing_module.save_timing(timed, target, offset=offset,
                              project=title, versie=_APP_VERSION)
    # Also keep the automatic timing separately, so that manual
    # corrections can be compared later (B68).
    try:
        timing_module.save_timing(timed, context.paths.timing_auto_file,
                                  offset=offset, project=title,
                                  versie=_APP_VERSION)
    except OSError:
        logger.warning(t("log_timing_auto_failed"))
    context.store.set_step("timing", {"file": str(target),
                                      "auto_file":
                                      str(context.paths.timing_auto_file),
                                      "lines": len(lines),
                                      "quality": detail})
    return target, len(lines), detail


def sync_timing_with_text_change(context: AppContext, old_lines,
                                 new_lines) -> tuple[bool, str]:
    """Carry a karaoke text change through in an existing timing.json (B99).

    Compares the old and new karaoke text. Only when the structure is
    equal (same number of blocks and sentences per block) and a
    ``timing.json`` already exists are the text differences carried
    through: unchanged lines stay exactly as they are; on a changed
    line the text is replaced, the syllables are split again and the
    existing line time span is divided evenly over them. With a
    deviating structure ``timing.json`` stays untouched.

    Returns:
        ``(bijgewerkt, melding)``.
    """
    from . import timing as timing_module

    path = context.paths.timing_file
    if not path.exists():
        return False, t("timing_sync_no_file")
    old_struct = [line.block for line in old_lines]
    new_struct = [line.block for line in new_lines]
    if old_struct != new_struct:
        # Structure deviates: the existing timing can no longer be right;
        # remove it so that it is made again (B99+B113).
        invalidate_timing(context)
        return False, t("timing_sync_structure_changed")
    timed = list(timing_module.load_timing(path))
    if len(timed) != len(new_lines):
        return False, t("timing_sync_count_mismatch")

    offset = timing_module.load_offset(path)
    changed = 0
    result: list = []
    for line, old_line, new_line in zip(timed, old_lines, new_lines):
        if new_line.text == old_line.text and new_line.crowd == line.crowd:
            result.append(line)
            continue
        changed += 1
        if line.syllables:
            span0 = line.syllables[0].start
            span1 = line.syllables[-1].end
        else:
            span0 = span1 = 0.0
        pieces = timing_module.split_line(new_line.text)
        width = (span1 - span0) / len(pieces) if pieces else 0.0
        syllables = tuple(
            timing_module.Syllable(
                text=piece,
                start=round(span0 + position * width, 3),
                end=round(span0 + (position + 1) * width, 3),
                held=False)
            for position, piece in enumerate(pieces)
        )
        # B291: ``blok`` and ``uitgeschakeld`` must go along explicitly.
        # They were not included here, so they fell back on their defaults
        # (0 and False): a line that the user had switched off (B180) came
        # back into the video normally after a simple text correction, and
        # the block division of the timing editor (B127) collapsed to block
        # 0. Only text/syllables ought to change here.
        result.append(timing_module.TimedLine(
            index=line.index, text=new_line.text, crowd=new_line.crowd,
            crowd_section=line.crowd_section, quality=line.quality,
            block=line.block, disabled=line.disabled,
            # B510: the new TEXT decides whether this is background
            # vocals - the same reason the fields above are carried over.
            bg=bool(getattr(new_line, "bg", False)),
            syllables=syllables))

    if changed == 0:
        return False, t("timing_sync_no_diff")
    timing_module.save_timing(result, path, offset=offset,
                              project=context.config.song.title,
                              versie=_APP_VERSION)
    logger.info(t("log_timing_synced"), changed)
    return True, t("timing_sync_updated").format(count=changed)


def current_offset(context: AppContext) -> float | None:
    """The current primary original↔karaoke offset (s), or ``None``.

    Derived from the first offset region of the alignment.
    """
    step = context.store.get_step("align")
    if step and step.get("regions"):
        return float(step["regions"][0].get("offset", 0.0))
    return None


def timing_project_mismatch(context: AppContext) -> str | None:
    """Give the deviating project title if ``timing.json`` belongs to
    another project than the current one, otherwise ``None`` (B181/B183)."""
    from . import timing as timing_module
    path = context.paths.timing_file
    if not path.exists():
        return None
    saved = timing_module.timing_project(path)
    current = context.config.song.title
    if saved and current and saved != current:
        return saved
    return None


def _warn_timing_project_mismatch(context: AppContext, path: Path) -> None:
    afwijkend = timing_project_mismatch(context)
    if afwijkend:
        logger.warning(t("log_timing_project_mismatch"),
                       afwijkend, context.config.song.title, path)


def mark_inline_pieces(context: AppContext, lines):
    """Refresh the inline crowd/bg marking from the karaoke text (B485).

    Those marks live per syllable in ``timing.json``, but they come from
    the text. Adding ``[bg]...[/bg]`` to a song that has already been
    timed changes no single letter of the sentence (the markers are
    stripped out), so nothing noticed it: neither the comparison in
    ``sync_timing_with_text_change`` nor the carry-over on an edited
    text. The piece then stood in the video after all. Reading them back
    from the text on load costs nothing and is always right - the text is
    where they were written.
    """
    from . import karaoke_text
    from . import timing as timing_module

    text_path = karaoke_text_path(context)
    if text_path is None:
        return lines
    try:
        text_lines = karaoke_text.parse_lines(text_path)
    except (OSError, ValueError, UnicodeDecodeError):
        return lines
    marked = timing_module.apply_inline_crowd(lines, text_lines)
    # ``load_timing`` has already weighed the held notes, but at that
    # moment the bg piece was still an ordinary syllable and it counted
    # in the median of its line. Weigh again now that it is marked.
    return timing_module.mark_held(marked)


def load_timing_reanchored(context: AppContext):
    """Load ``timing.json`` and re-anchor on a changed offset (B98).

    If the currently valid alignment offset deviates from the offset
    with which the timing was stored, all times are shifted by the
    difference so that the timing falls on the (new) karaoke again.
    Without a stored offset (old file) nothing happens.
    """
    from . import timing as timing_module
    path = context.paths.timing_file
    # Trace cross-contamination: is this timing of this project? (B181/B183)
    _warn_timing_project_mismatch(context, path)
    lines = mark_inline_pieces(context, timing_module.load_timing(path))
    stored = timing_module.load_offset(path)
    current = current_offset(context)
    if stored is not None and current is not None and abs(stored - current) > 1e-6:
        delta = stored - current
        logger.info(t("log_timing_reanchored"),
                    stored * 1000, current * 1000, delta * 1000)
        lines = timing_module.reanchor(lines, delta)
    return lines


def check_text_alignment(context: AppContext) -> tuple[bool, str]:
    """Compare the section structure of lyrics and karaoke text.

    Gives ``(ok, melding)`` with per section the numbers of sentences
    next to each other, so that you see immediately which block
    deviates (e.g. a verse that has dropped out).
    """
    from . import karaoke_text
    lyrics_path = context.paths.input_dir / song_text.LYRICS_FILENAME
    karaoke_path = context.paths.input_dir / karaoke_text.FILENAME
    if not (lyrics_path.exists() and karaoke_path.exists()):
        return True, t("text_align_missing")

    def song_blocks(path: Path) -> list[int]:
        """Lines per block, counted the way the COUPLING counts them.

        B376: this simply counted the non-empty lines, so it knew about
        ``#`` comments but not about ``[bg]``. A line that consists
        entirely of background vocals does not count for the coupling
        (it sounds at the same time as its neighbour), so this warning
        reported a difference that was not there - 18 against 12 on one
        project while the coupling itself saw 12 against 12. A warning
        that rejects a correct file is worse than no warning: the user
        goes and "repairs" it.
        """
        counts: list[int] = []
        current = 0
        seen = False
        for raw in path.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not stripped:
                if seen:
                    counts.append(current)
                    current = 0
                    seen = False
                continue
            if stripped.startswith("#"):
                continue
            if song_text.is_bg_only_line(stripped):
                seen = True          # wél binnen het blok, niet geteld
                continue
            current += 1
            seen = True
        if seen:
            counts.append(current)
        return counts

    song = song_blocks(lyrics_path)
    karaoke_lines = karaoke_text.parse_lines(karaoke_path)
    # Per block we count two variants: only the sung lines, and all
    # lines (incl. crowd). Crowd can namely be two things: a short
    # interjection without a counterpart in the lyrics (then 'only
    # vocals' counts), or an echo that in the lyrics is an own line (then
    # 'all lines' counts). A section is OK if the lyrics correspond with
    # one of the two; only if neither fits has a block really dropped
    # out (B75/B104).
    blocks: dict[int, list] = {}
    for line in karaoke_lines:
        blocks.setdefault(line.block, []).append(line)
    kar_sung = []
    kar_all = []
    for block in sorted(blocks):
        block = blocks[block]
        kar_all.append(len(block))
        kar_sung.append(sum(1 for line in block if not line.crowd) or
                        len(block))

    rows = []
    ok = True
    for index in range(max(len(song), len(kar_all))):
        s = song[index] if index < len(song) else "-"
        ksu = kar_sung[index] if index < len(kar_sung) else "-"
        kal = kar_all[index] if index < len(kar_all) else "-"
        match = (s != "-" and (s == ksu or s == kal))
        k = ksu if ksu == kal else f"{ksu}/{kal}"
        mark = t("text_align_mark_ok") if match \
            else t("text_align_mark_diff")
        if not match:
            ok = False
        rows.append(t("text_align_row").format(
            index=index + 1, lyrics=s, karaoke=k, mark=mark))
    header = (t("text_align_header_ok").format(count=len(song)) if ok
              else t("text_align_header_diff").format(
                  lyrics=len(song), karaoke=len(kar_all)))
    return ok, header + "\n" + "\n".join(rows)


#: The item of :func:`video_input_status` that the render may miss: the
#: offset is optional, because the karaoke step aligns by itself (B326:
#: previously recognised by its translated name, which meant that in
#: English the render refused on a missing offset).
VIDEO_INPUT_OPTIONAL = ("offset",)


def video_input_status(
        context: AppContext) -> list[tuple[str, str, bool, str]]:
    """Check whether all input for the karaoke video is present.

    The video is only made when everything is there (see
    ``docs/video_standard.md``). Each line is
    ``(key, name, present, detail)``; ``key`` is language-independent
    and is what the caller tests against (B326), ``name`` and ``detail``
    are for the user.
    """
    from . import karaoke_text

    input_dir = context.paths.input_dir
    items: list[tuple[str, str, bool, str]] = []

    lyrics = input_dir / song_text.LYRICS_FILENAME
    items.append(("lyrics", t("vi_lyrics"), lyrics.exists(), str(lyrics)))

    karaoke_text_path = input_dir / karaoke_text.FILENAME
    if karaoke_text_path.exists():
        try:
            lines = karaoke_text.parse_lines(karaoke_text_path)
            crowd = sum(1 for line in lines if line.crowd)
            detail = t("vi_detail_lines_crowd").format(
                lines=len(lines), crowd=crowd)
        except OSError:
            detail = t("vi_detail_unreadable")
        items.append(("karaoke_text", t("vi_karaoke_text"), True, detail))
    elif lyrics.exists():
        # B125: without karaoke text the lyrics can serve (video of
        # the original).
        items.append(("karaoke_text", t("vi_karaoke_text"), True,
                      t("vi_detail_lyrics_fallback")))
    else:
        items.append(("karaoke_text", t("vi_karaoke_text"), False,
                      t("vi_detail_karaoke_text_missing").format(
                          path=karaoke_text_path)))

    logos = sorted(input_dir.glob("logo.*"))
    items.append(("logo", t("vi_logo"), bool(logos),
                  logos[0].name if logos else f"{input_dir / 'logo.<ext>'}"))

    from . import timing as timing_module
    timing_path = context.paths.timing_file
    if timing_path.exists():
        try:
            timed = timing_module.load_timing(timing_path)
            filled = sum(1 for line in timed if line.end > 0)
            detail = t("vi_detail_timing_lines").format(
                lines=len(timed), filled=filled)
        except (OSError, ValueError, KeyError):
            detail = t("vi_detail_unreadable")
        items.append(("timing", t("vi_timing"), True, detail))
    else:
        items.append(("timing", t("vi_timing"), False,
                      t("vi_detail_no_timing")))

    has_offset = context.store.get_step("align") is not None
    items.append(("offset", t("vi_offset"), has_offset,
                  t("vi_detail_offset_done") if has_offset
                  else t("vi_detail_offset_missing")))
    return items


#: Allowed render sources (B226).
TEXT_SOURCES = ("karaoke", "original")
AUDIO_SOURCES = ("karaoke", "original", "demucs", "vocals")


def _render_audio(context: AppContext, audio_source: str) -> Path:
    """Choose the audio file for the render from ``audio_source`` (B226)."""
    out = context.paths.output_dir
    if audio_source == "original":
        audio = filesystem.find_audio_file(context.paths.input_dir,
                                           TRACK_ORIGINAL)
        if audio is None:
            raise PipelineError(t("err_no_original_audio"))
        return audio
    if audio_source == "demucs":
        path = out / "karaoke_demucs.mp3"
        if not path.exists():
            raise PipelineError(t("err_no_demucs_instrumental"))
        return path
    if audio_source == "vocals":
        path = out / "vocal_demucs.mp3"
        if not path.exists():
            raise PipelineError(t("err_no_vocals"))
        return path
    # default: karaoke (processed if there is one, otherwise bare)
    audio = next((c for c in (out / "karaoke_edit.mp3",
                              out / "karaoke_edit.wav") if c.exists()), None)
    if audio is None:
        audio = filesystem.find_audio_file(context.paths.input_dir,
                                           TRACK_KARAOKE)
    if audio is None:
        raise PipelineError(t("err_no_karaoke_audio"))
    return audio


def _render_timed_lines(context: AppContext, text_source: str):
    """Choose the timed lines for the render (B226).

    ``karaoke`` = the processed karaoke text timing (timing.json).
    ``origineel`` = the original lyrics lines with their (coupled) times,
    built up into timed lines."""
    from . import timing as timing_module
    if text_source == "original":
        original_items, _mapping = editor_originals(context)
        lines = [timing_module.timedline_from_text(
            i, it["text"], float(it.get("start", 0.0)),
            float(it.get("end", it.get("start", 0.0) + 1.0)))
            for i, it in enumerate(sorted(original_items,
                                          key=lambda x: x.get("start", 0.0)))]
        if not lines:
            raise PipelineError(t("err_no_original_timing"))
        return timing_module.enforce_monotonic(lines)
    return load_timing_reanchored(context)


#: 3-letter codes per music/text source for the file name suffix (B271).
#: Unknown sources (should not be able to occur via the GUI dialogue)
#: fall back on the source text itself, shortened to 3 characters.
_AUDIO_SUFFIX_CODES = {"karaoke": "kar", "original": "ori",
                       "vocals": "voc", "demucs": "dem"}
_TEXT_SUFFIX_CODES = {"karaoke": "kar", "original": "ori"}


def render_filename_suffix(audio_source: str, text_source: str) -> str:
    """File name suffix for a render (B271).

    The default combination (karaoke music + karaoke text) yields an
    empty suffix - the file name thus stays exactly as before. Every
    other combination gets ``_<muziek>_<tekst>`` with 3-letter codes
    (e.g. ``_voc_ori`` for voice-only music with the original text), so
    that several variants of the same title can exist next to each other
    in the output folder without overwriting each other.
    """
    if audio_source == "karaoke" and text_source == "karaoke":
        return ""
    audio_code = _AUDIO_SUFFIX_CODES.get(audio_source, audio_source[:3])
    text_code = _TEXT_SUFFIX_CODES.get(text_source, text_source[:3])
    return f"_{audio_code}_{text_code}"


def video_target(context: AppContext, text_source: str = "karaoke",
                 audio_source: str = "karaoke") -> Path:
    """Where the render lands (B354).

    Split off from :func:`run_video` so that the GUI can ask BEFORE the
    render whether an existing file may be overwritten - previously it
    was silently written over.
    """
    import re

    display = context.store.get_meta("display_name")
    title = (context.config.video.karaoke_title.strip()
             or display or context.config.song.title.replace("_", " ")
             or "Karaoke")
    safe = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" .") or "karaoke_video"
    suffix = render_filename_suffix(audio_source, text_source)
    return context.paths.output_dir / f"{safe}{suffix}.mp4"


#: B480: chosen background images are kept centrally (next to the global
#: settings) under a running number, so a picture chosen once can be used
#: again for another song. In the project itself it is called plainly
#: ``background.<ext>`` - the number belongs to the store, not to the
#: song.
BACKGROUND_STEM = "background"

_BACKGROUND_PATTERN = "background_*"


def stored_backgrounds(context: AppContext) -> list[Path]:
    """The centrally stored background images, in numbered order (B480)."""
    folder = context.paths.backgrounds_dir
    if not folder.exists():
        return []
    found = [path for path in folder.glob(_BACKGROUND_PATTERN)
             if path.is_file()]
    return sorted(found, key=lambda path: (_background_number(path),
                                           path.name))


def _background_number(path: Path) -> int:
    import re

    match = re.search(r"_(\d+)$", path.stem)
    return int(match.group(1)) if match else 0


def _file_digest(path: Path) -> str:
    import hashlib

    return hashlib.sha1(path.read_bytes()).hexdigest()


def store_background(context: AppContext, source: Path) -> Path:
    """Put ``source`` in the central store and return the stored file
    (B480).

    The same picture chosen twice does not end up in the list twice:
    compared on content, not on name. The number is the highest existing
    one plus one, so a gap left by a deleted picture is not filled up
    again with a name that was used before.
    """
    import shutil

    folder = context.paths.backgrounds_dir
    folder.mkdir(parents=True, exist_ok=True)
    existing = stored_backgrounds(context)
    digest = _file_digest(source)
    for path in existing:
        if _file_digest(path) == digest:
            return path
    highest = max((_background_number(path) for path in existing),
                  default=0)
    target = (folder
              / f"{BACKGROUND_STEM}_{highest + 1:03d}{_image_suffix(source)}")
    shutil.copy2(source, target)
    return target


def _image_suffix(source: Path) -> str:
    """The extension the stored copy gets (B480).

    A file without one would give ``background_001`` and ``background``,
    and then ``project_background`` (which globs ``background.*``) can no
    longer find it: the picture is there and the app says there is none.
    The type is then read from the file itself.
    """
    if source.suffix:
        return source.suffix.lower()
    try:
        from PIL import Image

        with Image.open(source) as image:
            fmt = (image.format or "").lower()
    except Exception:  # noqa: BLE001 - an unreadable picture is not a crash
        fmt = ""
    return {"jpeg": ".jpg", "png": ".png", "webp": ".webp",
            "bmp": ".bmp", "gif": ".gif"}.get(fmt, ".png")


def picture_start_dir(context: AppContext) -> str:
    """Where the file chooser for a background image opens (B480).

    The folder the previous background came from, otherwise the one the
    logo came from - that is a picture too, so it is the best guess we
    have. Deliberately not an own entry in ``input_names``: the picture
    does not go into the project by that route.
    """
    chosen = str(context.config.video.background_image or "").strip()
    if chosen:
        folder = Path(chosen).parent
        if folder.is_dir() and folder != context.paths.backgrounds_dir:
            return str(folder)
    return input_start_dir(context, "logo")


def stored_match(context: AppContext, used: Path | None) -> Path | None:
    """Which stored picture ``used`` is a copy of (B480), or ``None``.

    Compared on content: the copy in the project is called plainly
    ``background.<ext>`` and no longer carries its number.
    """
    if used is None or not used.exists():
        return None
    digest = _file_digest(used)
    for path in stored_backgrounds(context):
        if _file_digest(path) == digest:
            return path
    return None




def project_background(context: AppContext) -> Path | None:
    """The background image of THIS project (``input/background.<ext>``),
    or ``None`` (B480)."""
    found = sorted(context.paths.input_dir.glob(BACKGROUND_STEM + ".*"))
    return found[0] if found else None


def apply_background(context: AppContext, stored: Path) -> Path:
    """Copy a (stored) background into the project as
    ``input/background.<ext>`` (B480).

    A picture that is swapped for one with another extension would
    otherwise leave the old file behind, and then the render cannot tell
    which of the two it should take - so first everything with this name
    goes, then the new one comes.
    """
    import shutil

    if not context.paths.song:
        # Without a chosen song ``input_dir`` is the shared input folder;
        # writing there leaves a stray file that then travels along to
        # the next new project (B445).
        raise PipelineError(t("err_no_project_for_background"))
    clear_background(context)
    context.paths.input_dir.mkdir(parents=True, exist_ok=True)
    target = (context.paths.input_dir
              / f"{BACKGROUND_STEM}{stored.suffix.lower()}")
    shutil.copy2(stored, target)
    return target


def clear_background(context: AppContext) -> None:
    """Remove the background image from this project (B480). The central
    store is left alone - that is a different action."""
    for path in context.paths.input_dir.glob(BACKGROUND_STEM + ".*"):
        try:
            path.unlink()
        except OSError:
            logger.warning(t("log_delete_failed"), path)


def remove_stored_background(path: Path) -> bool:
    """Delete a picture from the central store (B480).

    Projects that use it keep their own copy in ``input``, so this can
    never break a render.
    """
    try:
        path.unlink()
    except OSError:
        logger.warning(t("log_delete_failed"), path)
        return False
    return True


def video_version(path: Path) -> int:
    """The sequence number of a rendered video (B478).

    ``<name>.mp4`` is the first one and counts as 1; ``<name>_2.mp4``,
    ``_3`` and so on carry their number in the name (see
    :func:`next_video_target`). Read as a number, not as text - sorted
    as text ``_10`` lands before ``_3``.
    """
    import re

    match = re.search(r"_(\d+)$", path.stem)
    if match is None:
        return 1
    return int(match.group(1))


def existing_videos(context: AppContext,
                    like: Path | None = None) -> list[Path]:
    """Every rendered video already in the output folder of this project
    (B478), oldest number first.

    The button "Open video" used to know only what THIS session had
    rendered, so after a project change it still pointed at the video of
    the previous one, and a video made yesterday could not be opened at
    all. What is on disk is the truth.

    ``like`` narrows it down to the numbered family of ONE file
    (B498): ``Titel.mp4``, ``Titel_2.mp4``, ``Titel_3.mp4`` belong
    together, but ``Titel_voc_ori.mp4`` is another render altogether
    (B271) and an old title leaves its own files behind. Without that
    boundary "overwrite" takes the newest file of the whole folder,
    which can be a completely different video.
    """
    from . import video as video_module

    folder = context.paths.output_dir
    if not folder.exists():
        return []
    # A render that is still busy (or was broken off) writes
    # ``<name>.part.mp4`` next to it (B468); that is not a video to
    # offer.
    found = [path for path in folder.glob("*.mp4")
             if not path.name.endswith(video_module.SCRATCH_SUFFIX)]
    if like is not None:
        import re

        stem = like.stem
        found = [path for path in found
                 if path.stem == stem
                 or re.fullmatch(re.escape(stem) + r"_\d+", path.stem)]
    return sorted(found,
                  key=lambda path: (video_version(path), path.name))


def projects_with_video(context: AppContext) -> list[str]:
    """Every project that has at least one rendered video (B532).

    Builds the paths itself instead of going through
    ``context_for_project``: that one calls ``ensure_directories`` and
    would create folders in every subfolder of ``output`` just because
    somebody looked. Listing may not change anything.
    """
    root = context.paths.output_root
    if not root.is_dir():
        return []
    found = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        paths = filesystem.ProjectPaths(root=context.paths.root,
                                        song=folder.name,
                                        output_base=context.paths.output_base)
        if not paths.project_file.exists():
            continue
        peek = AppContext(paths=paths, config=context.config,
                          store=filesystem.ProjectStore(paths.project_file))
        # Deliberately every render and not only the default variant:
        # the question here is "is there anything to collect", and
        # working out the file name of another project needs its titles
        # loaded. ``collect_videos`` does that and narrows it down.
        if existing_videos(peek):
            found.append(folder.name)
    return found


def collect_destination_ok(context: AppContext, destination: Path) -> None:
    """Refuse a destination inside the projects themselves (B532).

    With "the whole set" the folder per project would be the output
    folder of that project, and then the recording and the texts are
    copied into it. Nothing breaks, but the projects come back dirty -
    and the user gets the message before the copying starts instead of
    a surprise afterwards.
    """
    root = context.paths.output_root
    if destination == root or root in destination.parents:
        raise PipelineError(t("err_collect_inside"))


def collect_videos(context: AppContext, destination: Path,
                   with_sources: bool, progress=None,
                   cancelled=None) -> tuple[int, int]:
    """Copy the finished work to one folder (B532).

    Only the video, or the whole set that belongs to a song: the video,
    the original recording, the lyrics and the karaoke text. The set
    goes into a subfolder per project, because four files with the same
    names from twenty songs in one folder is not a collection but a
    heap; the videos on their own stay flat, since their file names are
    the song titles already.

    Of a project with several renders the NEWEST goes along - that is
    the one with the highest sequence number (see ``existing_videos``),
    not the one with the newest name.

    Returns ``(projects, files)``.
    """
    import shutil

    from . import karaoke_text
    from . import song_text as song_text_module

    songs = projects_with_video(context)
    # Not into the projects themselves: with "the whole set" the folder
    # per project would be the output folder of that project, and then
    # the recording and the texts are copied into it. Nothing breaks,
    # but the projects come back dirty.
    collect_destination_ok(context, destination)
    destination.mkdir(parents=True, exist_ok=True)
    projects = files = 0
    for number, song in enumerate(songs, start=1):
        if cancelled is not None and cancelled():
            break
        if progress is not None:
            progress(number, len(songs), song)
        # B470: the titles of THIS project, otherwise the file name is
        # worked out with the title of whatever project happens to be
        # open. B532: and then only the family of the DEFAULT render -
        # without that boundary a project that also has a voice-only
        # variant (``_voc_ori``, B271) hands over that one, because it
        # happens to be the newest file in the folder.
        other = apply_project_titles(context_for_project(context, song))
        videos = existing_videos(other, like=video_target(other))
        if not videos:
            continue
        folder = destination / song if with_sources else destination
        folder.mkdir(parents=True, exist_ok=True)
        wanted = [videos[-1]]
        if with_sources:
            audio = filesystem.find_audio_file(other.paths.input_dir,
                                               TRACK_ORIGINAL)
            if audio is not None:
                wanted.append(audio)
            for name in (song_text_module.LYRICS_FILENAME,
                         karaoke_text.FILENAME):
                path = other.paths.input_dir / name
                if path.exists():
                    wanted.append(path)
        copied = 0
        for path in wanted:
            target = folder / path.name
            # Flat collecting puts every video in one folder, and two
            # projects can carry the same title - ``video_target`` uses
            # the karaoke title and not the folder name. Silently
            # overwriting the first one would lose it AND make the tally
            # a lie, so the second gets the project name with it.
            if not with_sources and target.exists():
                target = folder / f"{path.stem}__{song}{path.suffix}"
                logger.info(t("log_collect_renamed"), path.name, target.name)
            try:
                shutil.copy2(path, target)
            except OSError:
                logger.exception(t("log_collect_failed"), path.name, song)
                continue
            copied += 1
        if copied:
            projects += 1
            files += copied
    logger.info(t("log_collected"), projects, files, destination)
    return projects, files


def next_video_target(target: Path) -> Path:
    """The first free ``<name>_2.mp4``, ``_3``, ... next to ``target``
    (B354). The new render gets the number, so an existing file is never
    touched."""
    stem, parent = target.stem, target.parent
    number = 2
    while True:
        candidate = parent / f"{stem}_{number}{target.suffix}"
        if not candidate.exists():
            return candidate
        number += 1


def run_video(context: AppContext,
              progress=None, text_source: str = "karaoke",
              audio_source: str = "karaoke",
              target: Path | None = None) -> Path:
    """Render the karaoke video; only possible when all input is present.

    ``text_source`` (karaoke/origineel) and ``audio_source``
    (karaoke/origineel/demucs/vocals) choose what goes into the render
    (B226). Default: karaoke music + timed karaoke text - that
    combination yields the bare file name (``<titel>.mp4``); every other
    combination gets a ``_<muziek>_<tekst>`` suffix (B271, see
    ``render_filename_suffix``) so that e.g. a voice-only render with the
    original text (``_voc_ori``) does not overwrite the default render.

    Raises:
        PipelineError: If input is missing or the rendering fails.
    """
    from . import video

    # B470: artist and original title live per project in project.json
    # (B210) and only reached ``config.video`` through the GUI. A render
    # started any other way (batch, a second project) therefore drew the
    # titles of whatever project happened to be open - or nothing at
    # all. Every render route now loads them itself.
    context = apply_project_titles(context)
    sync_input_changes(context)          # B311
    items = video_input_status(context)
    missing = [name for key, name, present, _ in items
               if not present and key not in VIDEO_INPUT_OPTIONAL]
    if missing:
        raise PipelineError(t("err_video_input_incomplete").format(
            missing=", ".join(missing)))

    timed = _render_timed_lines(context, text_source)
    audio = _render_audio(context, audio_source)
    logo = sorted(context.paths.input_dir.glob("logo.*"))[0]
    # File name = the title (spaces allowed; only invalid file name
    # characters replaced) (B87). With a non-default combination (not
    # karaoke music + karaoke text) the file name gets a
    # ``_<muziek>_<tekst>`` suffix (B271), so that several variants can
    # exist next to each other without overwriting each other; the
    # default combination keeps the bare name. ``target`` from the caller
    # wins (B354: "keep side by side" hands in a numbered name).
    if target is None:
        target = video_target(context, text_source, audio_source)
    title = (context.config.video.karaoke_title.strip()
             or context.store.get_meta("display_name")
             or context.config.song.title.replace("_", " ")
             or "Karaoke")
    settings = context.config.video
    # B480: the background belongs to the project - it is the copy in
    # ``input``, nothing else. Falling back on the (global) setting would
    # put the picture of another song in this video, exactly the leak
    # B470 had to fix for the titles.
    background = project_background(context)
    try:
        video.render_video(timed, audio, logo, title, target,
                           width=settings.width, height=settings.height,
                           fps=settings.fps,
                           font_path=fonts.resolve_font(settings.font),
                           progress=progress,
                           colors=video.colors_from_settings(settings),
                           artist=settings.orig_artist,
                           orig_title=settings.orig_title,
                           # B480: only the copy in the project. Taking
                           # the (global) setting as a fallback would put
                           # the picture of another song in this video -
                           # exactly the leak B470 had to fix for the
                           # titles.
                           background_path=str(background or ""),
                           # B456: one level for every video, so the
                           # amplifier does not have to be touched per
                           # song.
                           loudness_lufs=(
                               context.config.advanced.video_loudness_lufs),
                           true_peak_db=(
                               context.config.advanced.video_true_peak_db))
    except video.VideoError as exc:
        raise PipelineError(str(exc)) from exc
    context.store.set_step("video", {"file": str(target),
                                     "audio": str(audio)})
    logger.info(t("log_video_rendered"), audio.name)
    return target


def open_file(path: Path) -> None:
    """Open a file with the default application of the system.

    Is used to show the rendered mp4. Whether the player automatically
    starts playing depends on that player; most Windows players start
    paused or with a single click.
    """
    try:
        import os
        import subprocess
        import sys
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], **proc.no_window_kwargs())
        else:
            subprocess.Popen(["xdg-open", str(path)],
                             **proc.no_window_kwargs())
    except Exception:  # noqa: BLE001 - opening is nice-to-have
        logger.debug(t("log_open_file_failed"), path)


def open_folder(path: Path) -> None:
    """Open the (containing) folder of ``path`` in the system file manager
    (B267).

    Is ``path`` a file (e.g. the rendered mp4), then the folder around
    it is opened, not the file itself. If the folder does not exist
    (anymore), nothing happens (nice-to-have, no hard requirement).
    """
    folder = path if path.is_dir() else path.parent
    if not folder.exists():
        logger.debug(t("log_open_dir_skipped"), folder)
        return
    try:
        import os
        import subprocess
        import sys
        if sys.platform.startswith("win"):
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)], **proc.no_window_kwargs())
        else:
            subprocess.Popen(["xdg-open", str(folder)],
                             **proc.no_window_kwargs())
    except Exception:  # noqa: BLE001 - opening is nice-to-have
        logger.debug(t("log_open_dir_failed"), folder)


def open_in_browser(path: Path) -> None:
    """Try to open a file in the default browser."""
    try:
        import webbrowser
        webbrowser.open(path.resolve().as_uri())
    except Exception:  # noqa: BLE001 - browser is nice-to-have
        logger.debug(t("log_open_browser_failed"), path)
