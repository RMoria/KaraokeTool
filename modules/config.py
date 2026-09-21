"""Configuration management: loading, validating and saving ``config.json``.

The karaoke settings (``search_words``, ``gain_db``, ``fade_in_ms``,
``fade_out_ms``) are at the top level of the JSON file; ``whisper`` and
``align`` are optional sections. All song-specific settings belong in
this file, not in the code.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any
from .translations import t

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Error while loading or validating the configuration."""


@dataclass(frozen=True)
class KaraokeSettings:
    """Settings for the karaoke processing (damping of search words)."""

    search_words: tuple[str, ...] = ("oe", "oeh", "woo", "oh")
    gain_db: float = -25.0
    fade_in_ms: int = 70
    fade_out_ms: int = 60
    margin_ms: int = 0  # extra damping before and after each fragment


@dataclass(frozen=True)
class WhisperSettings:
    """Settings for Faster Whisper (model large-v3, not turbo)."""

    model: str = "large-v3"
    device: str = "auto"
    compute_type: str = "auto"
    language: str = "auto"  # "auto" = Whisper detects the language itself

    #: Decoding temperature (B314). Faster-whisper falls back by default
    #: over ``[0.0, 0.2, ... 1.0]``: as soon as a window fails the
    #: compression or logprob check it decodes again WITH SAMPLING. That
    #: sampling is not seeded, so the same button gives a different
    #: transcription every time - measured on one song, from the same
    #: source file: 36, 28 and 27 segments. A karaoke video you cannot
    #: reproduce is unusable, so the decoding is purely greedy (beam
    #: search). Put the ladder back with ``[0.0, 0.2, 0.4, 0.6, 0.8,
    #: 1.0]`` in ``config.json`` if you do want the fallback.
    temperature: tuple[float, ...] = (0.0,)

    #: Above this probability of "nothing is sung here" faster-whisper
    #: skips a WHOLE window of 30 seconds (B314). Together with
    #: ``log_prob_threshold`` that is the mechanism behind a hole of a
    #: minute in the middle of a song: the model decides for the entire
    #: window at once and jumps to the next. ``null`` switches the skip
    #: off. Because this tool transcribes the separated vocal stem and
    #: not the mix, silence there really is silence and a looser bound is
    #: safer than with an ordinary recording - but that differs per song,
    #: so measure it with ``tools/whisper_probe.py``.
    no_speech_threshold: float | None = 0.6

    #: Rescue for the skip above: if the average logprob of the window is
    #: HIGHER than this, it is not skipped after all (B314). Lower (e.g.
    #: -2.0) therefore means skipping less often. ``null`` switches the
    #: rescue off, so that only the no-speech probability counts.
    log_prob_threshold: float | None = -1.0

    #: Speech detection (Silero) before decoding: cuts the silence out
    #: first. Off by default - on a vocal stem it can just as easily cut
    #: away a softly sung passage.
    vad_filter: bool = False

    #: Skip the silence around a segment that looks like a hallucination
    #: (B314). Only works with word timestamps, which are always on here.
    #: ``null`` = off; a value in seconds (e.g. 2.0) makes faster-whisper
    #: jump over the silence before a suspect segment.
    hallucination_silence_threshold: float | None = None


@dataclass(frozen=True)
class AlignSettings:
    """Settings for the alignment of original and karaoke."""

    max_offsets: int = 12
    window_s: float = 10.0
    step_s: float = 5.0
    search_s: float = 3.0
    tolerance_ms: int = 40
    min_confidence: float = 0.15


@dataclass(frozen=True)
class ClusterSettings:
    """Settings for phonetic clustering of sounds."""

    merge_gap_ms: int = 200
    max_ngram: int = 5
    max_token_duration_s: float = 3.0
    similarity_threshold: float = 0.65


@dataclass(frozen=True)
class AnalysisSettings:
    """Settings for the analysis of the transcription."""

    min_confidence: float = 0.6
    short_word_max_letters: int = 4


@dataclass(frozen=True)
class TrackSettings:
    """To which music tracks transcription and analysis are applied.

    Analysis of the karaoke version itself tracks down residual words
    that have been left in the karaoke - the core of this program.
    """

    original: bool = True
    karaoke: bool = True


@dataclass(frozen=True)
class CacheSettings:
    """Behaviour of the cache."""

    # OFF by default (B236): this way expensive results (Demucs vocal stem,
    # Whisper transcription) are kept between sessions. Emptying manually is
    # possible with the "Nu legen" (empty now) button on Settings.
    clear: bool = False  # clear the cache at start-up and shutdown


@dataclass(frozen=True)
class SongSettings:
    """Active song project (song title determines the subfolders)."""

    title: str = ""


@dataclass(frozen=True)
class VideoSettings:
    """Settings for the karaoke video render."""

    width: int = 1280
    height: int = 720
    #: B448: fifty instead of twenty-five. The line shift lasts 0.35 s
    #: and that was nine frames - just few enough to read as steps. At
    #: fifty it is eighteen. Costs render time and file size.
    fps: int = 50
    font: str = ""  # optional path to a TrueType font
    orig_artist: str = ""             # original artist (credit, B122)
    orig_title: str = ""               # original title (credit, B122)
    karaoke_title: str = ""            # title on the karaoke video (B122)
    background_image: str = ""   # path to background image (B126)
    color_before: str = "#FFFFFF"        # text before the singing (white)
    color_vocal: str = "#3CB043"        # during singing (green)
    color_after: str = "#9E9E9E"          # after the singing (grey)
    color_crowd: str = "#E53935"       # crowd during singing (red)
    color_background: str = "#0A0A0E"  # video background
    #: B477: outline around the letters of the ACTIVE line, so the text
    #: keeps standing out against a background picture. Empty = the
    #: contra colour of that letter colour, worked out per colour; fill
    #: one in and that one wins. The countdown follows the sing colour.
    outline_before: str = ""
    outline_vocal: str = ""
    outline_after: str = ""
    outline_crowd: str = ""


@dataclass(frozen=True)
class InterfaceSettings:
    """Settings for the interface (separate from the audio language)."""

    language: str = "nl"


@dataclass(frozen=True)
class AdvancedSettings:
    """Large models and performance options.

    The large models each fall back if they are not available. The
    rhythm anchor (librosa) is fixed in the core and is always on; it is
    therefore no longer an option.
    """

    demucs: bool = True            # split vocals for residual vocals/karaoke
    forced_alignment: bool = True  # more precise word times (wav2vec2)
    parallel_detection: bool = True  # original+karaoke at once (B90)
    #: Loudness of the karaoke track in the video, in LUFS (B456). Every
    #: video came out at a different level - measured over the finished
    #: files the spread was 11 dB - so at every song the amplifier had to
    #: be touched. -16 is deliberately not the loudest possible: at that
    #: target thirteen of eighteen tracks get a plain straight gain and
    #: nothing is squeezed, while at -11 all eighteen would go through
    #: the limiter. Empty (``None``) switches the normalisation off.
    video_loudness_lufs: float | None = -16.0
    #: True-peak ceiling for that normalisation, in dBTP.
    video_true_peak_db: float = -1.0
    #: Chunked transcription (B442): besides the whole song, transcribe it
    #: once more in pieces cut in the silences the vocal stem shows, and
    #: let those pieces fill ONLY the stretches where the whole run heard
    #: nothing at all. Measured over four songs this takes the unheard
    #: singing from 197.7 s to 71.5 s. Costs a second pass over the audio;
    #: the pieces share the Whisper lanes with the whole run, so it is
    #: not twice the wall clock. Off = the old behaviour, one run.
    chunked_transcription: bool = True
    #: Vocal stem energy analysis: lengthening sustained notes (B194) and
    #: placing 'na-na' filler lines on their energy pulses (B209). Requires
    #: Demucs; falls back neatly if the vocal stem cannot be made.
    vocal_analysis: bool = True
    #: Own output main folder (Windows path or UNC) outside the project root
    #: (B214); empty = the default ``<root>/output``. Global.
    output_dir: str = ""
    #: Phonetic segment timing (B241): within a word distribute the duration
    #: over vowel/consonant segments instead of evenly per syllable.
    phonetic_timing: bool = True
    #: Write local diagnostics files (transcription history, timing
    #: diagnostics) in output/<titel>/diagnostiek/. On by default now; set it
    #: off by default for the GitHub release (B143).
    diagnostics: bool = True
    #: Block anchor barrier (B251): an anchor from an earlier block may not be
    #: displaced by a later block, so that a repeated chorus does not drag
    #: the next verse along and every block anchors on its own onset. Off =
    #: everything in one (virtual) block (old behaviour).
    block_anchor_barrier: bool = True
    #: Tunable base weights for the anchor arbitration (B250/B251); higher =
    #: stronger anchor. Effective weight = base weight × confidence. To be
    #: adjusted via config.json without changing code (like SegmentConfig).
    anchor_weight_syllable: float = 3.0
    anchor_weight_high: float = 2.0
    anchor_weight_word: float = 1.0
    #: Weight of the vocal onset as first anchor (B130/B133); the strongest.
    anchor_weight_onset: float = 10.0


@dataclass(frozen=True)
class ThemeSettings:
    """GUI colours (empty = default of the system)."""

    background: str = ""
    button: str = ""
    #: Colour of a button while its action runs ("busy", B229).
    button_active: str = "#f2c200"


@dataclass(frozen=True)
class AppConfig:
    """Complete application configuration."""

    karaoke: KaraokeSettings = field(default_factory=KaraokeSettings)
    whisper: WhisperSettings = field(default_factory=WhisperSettings)
    align: AlignSettings = field(default_factory=AlignSettings)
    analysis: AnalysisSettings = field(default_factory=AnalysisSettings)
    cluster: ClusterSettings = field(default_factory=ClusterSettings)
    tracks: TrackSettings = field(default_factory=TrackSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    song: SongSettings = field(default_factory=SongSettings)
    video: VideoSettings = field(default_factory=VideoSettings)
    interface: InterfaceSettings = field(default_factory=InterfaceSettings)
    advanced: AdvancedSettings = field(
        default_factory=AdvancedSettings)
    theme: ThemeSettings = field(default_factory=ThemeSettings)
    #: B361: on or off per model (B-number). Whatever is NOT in here
    #: follows the default from ``modules/model_register.py``. A model is
    #: switched OFF, not removed: the idea stays in the code and stays
    #: taking part in the measurements.
    models: dict = field(default_factory=dict)


#: The frame rate that was the default until v0.139.0 (B448).
_OLD_FPS = 25

#: Marker in config.json saying the lift above has been done. Written by
#: :func:`save_config`, so it lands there at the first save.
_FPS_LIFTED = "fps_lifted"

#: The outline colours of the four text colours (B511). Up to v0.145.0
#: they were worked out from perceived brightness, and that gave green a
#: black outline and red a white one - both the wrong way round, and
#: green by less than one brightness point, so it flipped on a hair.
#: ``video.contra_colour`` now decides those four itself, but a value
#: that was filled in by hand wins over that answer, so a stored one
#: would keep the old picture alive. Therefore the four fields are
#: emptied ONCE. The marker is what makes "once" possible: without it
#: the wipe would run at every load and the setting could never be used
#: again. It says only that this one wipe has run - nothing more.
_OUTLINE_RESET = "outline_reset"

#: The outline fields that wipe empties (B511).
_OUTLINE_FIELDS = ("outline_before", "outline_vocal", "outline_after",
                   "outline_crowd")


def default_config() -> AppConfig:
    """Give a configuration with default values."""
    return AppConfig()


def load_config(path: Path) -> AppConfig:
    """Load and validate the configuration from a JSON file.

    Args:
        path: Path to ``config.json``.

    Returns:
        The validated configuration.

    Raises:
        ConfigError: If the file is missing, contains no valid JSON or
            has invalid values.
    """
    if not path.exists():
        raise ConfigError(t("err_config_not_found").format(path=path))
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(
            t("err_config_bad_json").format(path=path, detail=exc)
        ) from exc

    defaults = KaraokeSettings()
    karaoke = KaraokeSettings(
        search_words=_parse_search_words(raw.get("search_words", defaults.search_words)),
        gain_db=float(raw.get("gain_db", defaults.gain_db)),
        fade_in_ms=int(raw.get("fade_in_ms", defaults.fade_in_ms)),
        fade_out_ms=int(raw.get("fade_out_ms", defaults.fade_out_ms)),
        margin_ms=int(raw.get("margin_ms", defaults.margin_ms)),
    )
    whisper = _dataclass_from_mapping(WhisperSettings,
                                     raw.get("whisper", {}))
    # B314: json has no tuple; normalise so that a configuration that
    # has been saved and read back is equal to the original (and the
    # settings signature does not change).
    whisper = replace(whisper,
                      temperature=tuple(float(x) for x in
                                        whisper.temperature))
    align = _dataclass_from_mapping(AlignSettings, raw.get("align", {}))
    analysis = _dataclass_from_mapping(AnalysisSettings,
                                       raw.get("analysis", {}))
    cluster = _dataclass_from_mapping(ClusterSettings, raw.get("cluster", {}))
    tracks = _dataclass_from_mapping(TrackSettings, raw.get("tracks", {}))
    cache = _dataclass_from_mapping(CacheSettings, raw.get("cache", {}))
    song = _dataclass_from_mapping(SongSettings, raw.get("song", {}))
    video = _dataclass_from_mapping(VideoSettings, raw.get("video", {}))
    # B448: an existing config.json holds the old default of 25, and a
    # default that is never read again is no default. So it is lifted -
    # ONCE. The marker is what makes that possible: without it the lift
    # would happen on every load and 25 would be the one value the user
    # could never keep, which is the opposite of a setting.
    if int(raw.get("video", {}).get("fps", 0)) == _OLD_FPS \
            and not raw.get(_FPS_LIFTED):
        logger.info(t("log_fps_lifted"), _OLD_FPS, VideoSettings.fps)
        video = replace(video, fps=VideoSettings.fps)
    # B511: see ``_OUTLINE_RESET``.
    wiped: list[str] = []
    if not raw.get(_OUTLINE_RESET):
        wiped = [name for name in _OUTLINE_FIELDS
                 if str(getattr(video, name, "") or "").strip()]
        if wiped:
            logger.info(t("log_outline_reset"), ", ".join(wiped))
            video = replace(video, **{name: "" for name in wiped})
    interface = _dataclass_from_mapping(InterfaceSettings,
                                        raw.get("interface", {}))
    advanced = _dataclass_from_mapping(AdvancedSettings,
                                          raw.get("advanced", {}))
    theme = _dataclass_from_mapping(ThemeSettings, raw.get("theme", {}))

    models = {str(code): bool(state)
              for code, state in dict(raw.get("models", {})).items()}
    config = AppConfig(karaoke=karaoke, whisper=whisper, align=align,
                       analysis=analysis, cluster=cluster, tracks=tracks,
                       cache=cache, song=song, video=video,
                       interface=interface, advanced=advanced,
                       theme=theme, models=models)
    _validate(config)
    logger.info(t("log_config_loaded"), path)
    if wiped:
        # B511: write the marker down NOW. It only lands in the file
        # through ``save_config``, and there are runs that never save -
        # then the wipe would repeat at every start and the setting
        # could never be used again. That is the one thing "once" may
        # not mean.
        try:
            save_config(config, path)
        except OSError:
            logger.warning(t("log_config_write_failed"), path)
    return config


def save_config(config: AppConfig, path: Path) -> None:
    """Write the configuration to a JSON file.

    The karaoke settings are stored flat, in line with the example
    format from the project description.
    """
    data: dict[str, Any] = {
        "search_words": list(config.karaoke.search_words),
        "gain_db": config.karaoke.gain_db,
        "fade_in_ms": config.karaoke.fade_in_ms,
        "fade_out_ms": config.karaoke.fade_out_ms,
        "margin_ms": config.karaoke.margin_ms,
        # B314: written out via ``asdict`` instead of a hand-written list
        # of keys. That list was the reason the new decoding options
        # (temperature, no-speech threshold) disappeared on saving: they
        # loaded fine but were never written back, so an adjustment in
        # ``config.json`` silently vanished at the next save.
        "whisper": {key: (list(value) if isinstance(value, tuple) else value)
                    for key, value in asdict(config.whisper).items()},
        "align": {
            "max_offsets": config.align.max_offsets,
            "window_s": config.align.window_s,
            "step_s": config.align.step_s,
            "search_s": config.align.search_s,
            "tolerance_ms": config.align.tolerance_ms,
            "min_confidence": config.align.min_confidence,
        },
        "analysis": {
            "min_confidence": config.analysis.min_confidence,
            "short_word_max_letters": config.analysis.short_word_max_letters,
        },
        "cluster": {
            "merge_gap_ms": config.cluster.merge_gap_ms,
            "max_ngram": config.cluster.max_ngram,
            "max_token_duration_s": config.cluster.max_token_duration_s,
            "similarity_threshold": config.cluster.similarity_threshold,
        },
        "tracks": {
            "original": config.tracks.original,
            "karaoke": config.tracks.karaoke,
        },
        "cache": {"clear": config.cache.clear},
        "song": {"title": config.song.title},
        "interface": {"language": config.interface.language},
        _FPS_LIFTED: True,
        _OUTLINE_RESET: True,
        "advanced": {
            "demucs": config.advanced.demucs,
            "forced_alignment": config.advanced.forced_alignment,
            "parallel_detection": config.advanced.parallel_detection,
            "diagnostics": config.advanced.diagnostics,
            "vocal_analysis": config.advanced.vocal_analysis,
            "output_dir": config.advanced.output_dir,
            "phonetic_timing": config.advanced.phonetic_timing,
            "chunked_transcription": config.advanced.chunked_transcription,
            "video_loudness_lufs": config.advanced.video_loudness_lufs,
            "video_true_peak_db": config.advanced.video_true_peak_db,
            "block_anchor_barrier": config.advanced.block_anchor_barrier,
            "anchor_weight_syllable":
                config.advanced.anchor_weight_syllable,
            "anchor_weight_high": config.advanced.anchor_weight_high,
            "anchor_weight_word": config.advanced.anchor_weight_word,
            "anchor_weight_onset": config.advanced.anchor_weight_onset,
        },
        "video": {
            "width": config.video.width,
            "height": config.video.height,
            "fps": config.video.fps,
            "font": config.video.font,
            "orig_artist": config.video.orig_artist,
            "orig_title": config.video.orig_title,
            "karaoke_title": config.video.karaoke_title,
            "background_image": config.video.background_image,
            "color_before": config.video.color_before,
            "color_vocal": config.video.color_vocal,
            "color_after": config.video.color_after,
            "color_crowd": config.video.color_crowd,
            "color_background": config.video.color_background,
            "outline_before": config.video.outline_before,
            "outline_vocal": config.video.outline_vocal,
            "outline_after": config.video.outline_after,
            "outline_crowd": config.video.outline_crowd,
        },
        "theme": {
            "background": config.theme.background,
            "button": config.theme.button,
            "button_active": config.theme.button_active,
        },
        # B361: only the deviations from the default. An empty block
        # means "everything as the register intends"; that reads better
        # than twenty lines all saying true.
        "models": {code: bool(state)
                   for code, state in sorted(dict(config.models).items())},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info(t("log_config_saved"), path)


def _parse_search_words(value: Any) -> tuple[str, ...]:
    """Convert the list of search words into a tuple and validate it."""
    if not isinstance(value, (list, tuple)):
        raise ConfigError(t("err_config_search_words_list"))
    words = tuple(str(word).strip().lower() for word in value)
    if not words or any(not word for word in words):
        raise ConfigError(t("err_config_search_words_empty"))
    return words


def _dataclass_from_mapping(cls: type, mapping: Any) -> Any:
    """Build a dataclass from a dict and ignore unknown keys."""
    if not isinstance(mapping, dict):
        raise ConfigError(
            t("err_config_section_object").format(name=cls.__name__)
        )
    known = {f.name for f in fields(cls)}
    unknown = set(mapping) - known
    if unknown:
        logger.warning(t("log_unknown_keys"), cls.__name__, sorted(unknown))
    return cls(**{key: mapping[key] for key in mapping if key in known})


def _validate(config: AppConfig) -> None:
    """Check value ranges; raise ConfigError on errors."""
    if config.karaoke.gain_db > 0:
        raise ConfigError(t("err_config_gain_db"))
    if config.karaoke.fade_in_ms < 0 or config.karaoke.fade_out_ms < 0:
        raise ConfigError(t("err_config_fade_negative"))
    if config.karaoke.margin_ms < 0:
        raise ConfigError(t("err_config_margin_negative"))
    if config.align.max_offsets < 1:
        raise ConfigError(t("err_config_max_offsets"))
    if config.align.window_s <= 0 or config.align.step_s <= 0:
        raise ConfigError(t("err_config_window_step"))
    if config.align.search_s <= 0 or config.align.tolerance_ms < 0:
        raise ConfigError(t("err_config_search_tolerance"))
    # B301: bound it just like analyse.min_confidence. This was the only
    # threshold that was not checked, while 0.0 breaks the alignment: all
    # windows then keep confidence 0 and the weighted averaging in
    # ``align._build_regions`` divides by a weight sum of zero.
    if not 0.0 < config.align.min_confidence <= 1.0:
        raise ConfigError(t("err_config_align_confidence"))
    if not 0.0 <= config.analysis.min_confidence <= 1.0:
        raise ConfigError(t("err_config_analysis_confidence"))
    if config.analysis.short_word_max_letters < 1:
        raise ConfigError(t("err_config_short_word_letters"))
    if not 0.0 < config.cluster.similarity_threshold <= 1.0:
        raise ConfigError(t("err_config_cluster_similarity"))
    if config.cluster.merge_gap_ms < 0 or config.cluster.max_ngram < 1:
        raise ConfigError(t("err_config_cluster_invalid"))
    if config.cluster.max_token_duration_s <= 0:
        raise ConfigError(t("err_config_token_duration"))
    if config.video.width < 320 or config.video.height < 180 \
            or config.video.fps < 1:
        raise ConfigError(t("err_config_video_invalid"))
    if not (config.tracks.original or config.tracks.karaoke):
        raise ConfigError(t("err_config_no_track"))
