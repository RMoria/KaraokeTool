"""Speech recognition with Faster Whisper (model ``large-v3``, not turbo).

Transcribes the original with word timestamps and confidence and writes
the results to ``transcript.txt``, ``woorden.csv``, ``words.json``,
``segments.json`` and ``run_info.json``. The segments can be kept in
the cache via :func:`save_segments`/:func:`load_segments`, so that
Whisper does not have to run again.

CSV files use ``;`` as separator (Excel-friendly for Dutch settings).
"""

from __future__ import annotations

import csv
import json
import logging
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import WhisperSettings
from .translations import t

ProgressCallback = Callable[[float, float], None]

#: Whisper models loaded once per (model, device, compute), shared across
#: tracks. This way the model does not load twice with parallel detection
#: (halves the memory and speeds up a second run); ctranslate2 models are
#: safe for simultaneous transcribe calls (B114).
_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}
_MODEL_LOCK = threading.Lock()
"""Callback (verwerkte seconden, totale seconden) voor voortgang."""

logger = logging.getLogger(__name__)

CSV_DELIMITER = ";"


class WhisperError(Exception):
    """Error while loading the model or transcribing."""


class CancelledError(Exception):
    """The transcription was aborted by the user (Stop button)."""


@dataclass(frozen=True)
class Word:
    """One recognised word with timestamps and confidence."""

    text: str
    start: float
    end: float
    confidence: float


@dataclass(frozen=True)
class Segment:
    """One recognised segment (sentence/line) with its words."""

    index: int
    text: str
    start: float
    end: float
    words: tuple[Word, ...]


def decode_options(settings: WhisperSettings) -> dict[str, Any]:
    """The decoding options from the configuration (B314).

    Kept apart from :func:`transcribe` so that
    ``tools/whisper_probe.py`` can measure exactly the same call with
    other values, and so that a test can see what goes to faster-whisper
    without a model being needed.

    Four choices steer how much of a song is heard at all:

    ``temperature``
        Faster-whisper falls back over a ladder of temperatures as soon
        as a window fails its quality checks, and decodes again WITH
        SAMPLING. Not seeded, so the outcome differs per run. Greedy
        (``0.0``) makes it reproducible.
    ``no_speech_threshold`` and ``log_prob_threshold``
        Together they decide whether a window of thirty seconds is
        skipped WHOLE ("no voice activity"). That is the mechanism
        behind a hole of a minute in the middle of a song.
    ``vad_filter``
        Cuts silence out beforehand.
    ``hallucination_silence_threshold``
        Jumps over the silence around a segment that looks like a
        hallucination.
    """
    temperature = list(settings.temperature) or [0.0]
    return {
        "temperature": temperature,
        "no_speech_threshold": settings.no_speech_threshold,
        "log_prob_threshold": settings.log_prob_threshold,
        "vad_filter": settings.vad_filter,
        "hallucination_silence_threshold":
            settings.hallucination_silence_threshold,
    }


def transcribe(
    audio_path: Path,
    settings: WhisperSettings,
    output_dir: Path,
    progress: ProgressCallback | None = None,
    language_override: str | None = None,
    cancelled: Callable[[], bool] | None = None,
    initial_prompt: str | None = None,
) -> tuple[Segment, ...]:
    """Transcribe an audio file and write all output files.

    Args:
        audio_path: Path to the wav file of the original.
        settings: Whisper settings from the configuration.
        output_dir: Folder in which the output files are placed.
        initial_prompt: Optional context text (e.g. the lyrics words,
            B263) that Whisper is given as expected vocabulary. Helps
            against consistently misrecognised words that produce the
            same mistake at every repetition.

    Returns:
        The recognised segments including words.

    Raises:
        WhisperError: If faster-whisper is missing or the model fails.
    """
    model = _load_model(settings)
    logger.info(t("log_transcription_started"), audio_path.name)
    started = time.perf_counter()
    try:
        chosen = language_override or settings.language
        language = None if chosen == "auto" else chosen
        raw_segments, info = model.transcribe(
            str(audio_path),
            language=language,  # None => Whisper detects the language itself
            word_timestamps=True,
            beam_size=5,
            condition_on_previous_text=False,  # fewer hallucination loops
            initial_prompt=initial_prompt or None,  # B263
            **decode_options(settings),  # B314
        )
        segments = _collect_segments(raw_segments, float(info.duration),
                                     progress, cancelled)
    except (WhisperError, CancelledError):
        raise
    except Exception as exc:  # noqa: BLE001 - model library has many errors
        raise WhisperError(
            t("err_transcription_failed").format(detail=exc)) from exc
    elapsed = time.perf_counter() - started

    word_count = sum(len(segment.words) for segment in segments)
    run_info: dict[str, Any] = {
        "file": str(audio_path),
        "model": settings.model,
        "language": info.language,
        "taal_kans": round(float(info.language_probability), 4),
        "audio_duur_s": round(float(info.duration), 2),
        "segments": len(segments),
        "words": word_count,
        "rekentijd_s": round(elapsed, 1),
        "tijdstip": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "faster_whisper": _package_version("faster-whisper"),
        "initial_prompt_woorden": (len(initial_prompt.split())
                                   if initial_prompt else 0),  # B263
    }
    write_outputs(segments, run_info, output_dir)
    logger.info(t("log_transcription_done"),
                len(segments), word_count, elapsed)
    return segments


#: The last decoded audio, so that cutting a song into pieces decodes it
#: once instead of once per piece (B442). One entry is enough: a chunked
#: run works through one file and then moves on, and a whole song at
#: 16 kHz mono float32 is some fifteen megabytes - worth keeping for the
#: length of a run, not worth collecting.
_DECODED: dict = {}
_DECODED_LOCK = threading.Lock()

#: The sample rate Whisper wants. Anything else is resampled.
SLICE_RATE = 16000


def _decoded(audio_path: Path):
    """The whole file as samples, decoded at most once.

    Keyed on path plus size and modification time, so an audio file that
    is replaced under our feet is decoded again instead of quietly
    serving the previous song.
    """
    import librosa

    stat = Path(audio_path).stat()
    key = (str(audio_path), stat.st_size, stat.st_mtime_ns)
    with _DECODED_LOCK:
        if _DECODED.get("key") == key:
            return _DECODED["samples"]
    samples, _rate = librosa.load(str(audio_path), sr=SLICE_RATE, mono=True)
    with _DECODED_LOCK:
        _DECODED.clear()
        _DECODED.update({"key": key, "samples": samples})
    return samples


def audio_slice(audio_path: Path, start: float = 0.0,
                end: float | None = None):
    """The audio as 16 kHz mono samples, optionally one slice (B442).

    Faster-whisper takes a numpy array as happily as a path, and that is
    what makes a chunked run possible at all: cut the audio, transcribe,
    add the offset back to every time. No dependency on
    ``clip_timestamps``, so it works with any version.

    This lived in ``tools/whisper_probe.py``, where it was fine as long
    as only the trial cut anything: a trial cuts one song and takes as
    long as it takes. In production it is called once per piece, ten to
    fifteen times per song, and decoding plus resampling the WHOLE song
    every time is tens of seconds of pure waste per run - so the decoded
    audio is kept for as long as it is being cut.
    """
    samples = _decoded(audio_path)
    first = max(0, int(round(start * SLICE_RATE)))
    last = len(samples) if end is None else min(
        len(samples), int(round(end * SLICE_RATE)))
    return samples[first:last]


def transcribe_slice(audio_path: Path, settings: WhisperSettings,
                     start: float = 0.0, end: float | None = None,
                     initial_prompt: str = "",
                     language_override: str | None = None,
                     cancelled: Callable[[], bool] | None = None,
                     ) -> tuple[Segment, ...]:
    """Transcribe one slice and put the times back on the song (B442).

    The small brother of :func:`transcribe`: no output files, no run
    info, no progress - a piece is not a run the user is watching. What
    it does share is the model cache and :func:`decode_options`, so a
    piece is decoded with exactly the settings the whole song would get.

    ``index`` on the segments is local to the piece; the caller renumbers
    once everything has been put together.
    """
    model = _load_model(settings)
    chosen = language_override or settings.language
    language = None if chosen == "auto" else chosen
    audio = (str(audio_path) if (start <= 0.0 and end is None)
             else audio_slice(audio_path, start, end))
    try:
        raw_segments, _info = model.transcribe(
            audio, language=language, word_timestamps=True, beam_size=5,
            condition_on_previous_text=False,
            initial_prompt=initial_prompt or None,
            **decode_options(settings))
        segments = _collect_segments(raw_segments, 0.0, None, cancelled)
    except (WhisperError, CancelledError):
        raise
    except Exception as exc:  # noqa: BLE001 - model library has many errors
        raise WhisperError(
            t("err_transcription_failed").format(detail=exc)) from exc
    shift = float(start)
    if not shift:
        return segments
    return tuple(
        Segment(index=segment.index, text=segment.text,
                start=segment.start + shift, end=segment.end + shift,
                words=tuple(replace(word, start=word.start + shift,
                                    end=word.end + shift)
                            for word in segment.words))
        for segment in segments)


def write_outputs(
    segments: tuple[Segment, ...],
    run_info: dict[str, Any],
    output_dir: Path,
) -> None:
    """Write all Whisper output files to the output folder."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_transcript(segments, output_dir / "transcript.txt")
    _write_words_csv(segments, output_dir / "words.csv")
    # B558: ``woorden.json``/``segmenten.json`` until v1.0.5. These are
    # written into ``output/<song>/<track>/``, which is made anew on
    # every run, so unlike the input files of B555 there is nothing to
    # migrate - the old two simply stop being written. A stale pair from
    # before this version stays behind until the folder is cleared, and
    # is read by nothing.
    _write_words_json(segments, output_dir / "words.json")
    _write_json(segments_to_dicts(segments), output_dir / "segments.json")
    _write_json(run_info, output_dir / "run_info.json")
    logger.info(t("log_whisper_output"), output_dir)


def save_segments(segments: tuple[Segment, ...], path: Path) -> None:
    """Keep segments in the cache (JSON)."""
    _write_json(segments_to_dicts(segments), path)
    logger.debug(t("log_segments_cached"), path)


def load_segments(path: Path) -> tuple[Segment, ...]:
    """Load previously cached segments.

    Raises:
        WhisperError: If the cache file is unreadable.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return segments_from_dicts(data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise WhisperError(
            t("err_cache_unreadable").format(path=path)) from exc


def segments_to_dicts(segments: tuple[Segment, ...]) -> list[dict[str, Any]]:
    """Convert segments into JSON-serialisable dicts."""
    return [
        {
            "index": segment.index,
            "text": segment.text,
            "start": segment.start,
            "end": segment.end,
            "words": [
                {"text": word.text, "start": word.start,
                 "end": word.end, "confidence": word.confidence}
                for word in segment.words
            ],
        }
        for segment in segments
    ]


def segments_from_dicts(data: list[dict[str, Any]]) -> tuple[Segment, ...]:
    """Rebuild segments from dicts (the reverse of serialisation)."""
    return tuple(
        Segment(
            index=int(item["index"]),
            text=str(item["text"]),
            start=float(item["start"]),
            end=float(item["end"]),
            words=tuple(
                Word(text=str(word["text"]), start=float(word["start"]),
                     end=float(word["end"]),
                     confidence=float(word["confidence"]))
                for word in item["words"]
            ),
        )
        for item in data
    )


def _collect_segments(
    raw_segments: Any,
    total_duration_s: float = 0.0,
    progress: ProgressCallback | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[Segment, ...]:
    """Convert the streaming output of faster-whisper into dataclasses.

    The output of faster-whisper is a generator; while running through
    it the progress (on the basis of the processed audio position) is
    reported to the callback. If ``cancelled()`` is true, then the run
    stops with a :class:`CancelledError` (Stop button).
    """
    segments: list[Segment] = []
    for index, raw in enumerate(raw_segments):
        if cancelled is not None and cancelled():
            raise CancelledError()
        if progress is not None and total_duration_s > 0:
            progress(min(float(raw.end), total_duration_s), total_duration_s)
        words = tuple(
            Word(
                text=str(word.word).strip(),
                start=float(word.start),
                end=float(word.end),
                confidence=float(word.probability),
            )
            for word in (raw.words or ())
        )
        segments.append(Segment(
            index=index,
            text=str(raw.text).strip(),
            start=float(raw.start),
            end=float(raw.end),
            words=words,
        ))
    return tuple(segments)


def hub_cache_dir() -> Path:
    """The folder huggingface_hub will really download into (B545).

    Copied from ``huggingface_hub.constants``, which resolves
    ``HF_HUB_CACHE``, then the legacy ``HUGGINGFACE_HUB_CACHE``, then
    ``HF_HOME/hub``, and only without any of those
    ``XDG_CACHE_HOME/huggingface/hub`` or ``~/.cache/huggingface/hub``.
    A ``~`` and an environment variable are expanded on the way, as it
    expands them.

    A variable that is SET BUT EMPTY counts as set, exactly as it does
    there - ``os.getenv`` does not care that the value is empty, and a
    `.bat` that does ``set HF_HUB_CACHE=%MODELDIR%`` with an undefined
    ``MODELDIR`` leaves precisely that. Treating it as unset would send
    this answer to another folder than the download.

    Read out rather than imported so that this answer does not depend
    on huggingface_hub being importable; ``test_whisper.py`` compares
    the two on a machine where it is, so a change in the library shows
    up as a red test instead of as a silent wrong answer.
    """
    import os

    def _expand(value: str) -> Path:
        return Path(os.path.expandvars(os.path.expanduser(value)))

    hub = os.environ.get("HF_HUB_CACHE")
    if hub is not None:
        return _expand(hub)
    legacy = os.environ.get("HUGGINGFACE_HUB_CACHE")
    if legacy is not None:
        return _expand(legacy)
    home = os.environ.get("HF_HOME")
    if home is not None:
        return _expand(home) / "hub"
    base = os.environ.get("XDG_CACHE_HOME")
    if base is None:
        base = str(Path.home() / ".cache")
    return _expand(base) / "huggingface" / "hub"


def _name_parts(name: str) -> list[str]:
    """A cache folder name or a model name, cut into its pieces."""
    return [part for part in name.lower().replace("/", "-").split("-")
            if part]


def _folder_is_the_model(folder: list[str], wanted: list[str]) -> bool:
    """Does this hub folder hold the model that was asked for? (B547)

    The old rule was "the folder name contains the model name", and
    that answers yes to the wrong question twice over: with only
    ``models--Systran--faster-whisper-large-v3-turbo`` in the cache the
    question about ``large-v3`` came back yes, and three gigabytes came
    down without a word.

    The rule now is: the pieces of the model appear in the folder in
    this order, and the folder ENDS on the last of them. That last
    condition is what keeps ``-turbo`` and ``tiny.en`` out, and the
    order without adjacency is what lets ``distil-large-v3`` find
    ``models--Systran--faster-distil-whisper-large-v3``, where the
    maker put ``whisper`` in the middle of the name.

    It is an estimate and it says so: the folder for a model is not
    derivable from the name faster-whisper accepts, only guessable.
    ``large``, which faster-whisper reads as an alias, is not found
    this way - the app does not offer it, and the cost of a miss is a
    message too many, not a wrong transcription.
    """
    if not wanted or not folder:
        return False
    if folder[-1] != wanted[-1]:
        return False
    at = 0
    for part in wanted:
        while at < len(folder) and folder[at] != part:
            at += 1
        if at == len(folder):
            return False
        at += 1
    return True


def model_cached(settings: WhisperSettings) -> bool:
    """Estimate whether the Whisper model has already been downloaded.

    Looks in the Hugging Face cache for a folder that belongs to the
    model. Is used to show the "model is being downloaded" message only
    when that really happens.

    B545: which cache that is now comes from ``hub_cache_dir``. The old
    code built the folder out of ``HF_HOME`` and fell back to
    ``~/.cache/huggingface/hub`` as soon as it did not exist yet -
    which is exactly the situation the message is for: a fresh
    ``HF_HOME`` has no ``hub`` precisely because nothing has been
    downloaded into it. It then answered about a cache that was not
    going to be used, found the model there, and kept the message away
    before a multi-gigabyte download.
    """
    import os

    model = settings.model
    if os.path.isdir(model):  # explicit path to a model
        return True
    hub = hub_cache_dir()
    if not hub.exists():
        return False
    wanted = _name_parts(model)
    for entry in hub.iterdir():
        if not entry.is_dir():
            continue
        if not _folder_is_the_model(_name_parts(entry.name), wanted):
            continue
        # B547: and a download that was broken off is not a model. The
        # pieces land as blobs/<sha>.incomplete, so a folder holding
        # one of those is exactly the case the message is for.
        if any(entry.glob("blobs/*.incomplete")):
            logger.info(t("log_model_half_downloaded"), entry.name)
            continue
        return True
    return False


def _load_model(settings: WhisperSettings) -> Any:
    """Load (or reuse) the Whisper model with automatic device choice.

    Models that have been loaded once are cached module-wide and shared
    across tracks, so that parallel detection does not load the same model
    twice (B114).

    B422: that sharing needs ``num_workers``, and without it it costs more
    than it saves. One model handles one transcription at a time, so as
    soon as two work slots use the same model they stand in line instead
    of running side by side. Measured on a full night job: the same trial
    went from 3902 s to 5522 s after the model was shared, with per
    thirty-second window 44-52 s instead of 20-27 s - exactly twice as
    slow, which is what taking turns looks like. And in the task manager
    it showed as four busy cores while there were two runs.

    ``cpu_threads`` is set explicitly for the same reason. The library
    silently defaults to four, ``measure_pool`` counts its work slots on
    the assumption of four, and those two numbers agreeing was luck
    rather than design. Now the sum is written down in one place.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise WhisperError(t("err_faster_whisper_missing")) from exc

    from . import measure_pool

    device, compute_type = _resolve_device(settings)
    workers = max(1, measure_pool.whisper_lanes())
    threads = max(1, measure_pool.threads_per_lane())
    key = (settings.model, device, compute_type, workers, threads)
    with _MODEL_LOCK:
        cached = _MODEL_CACHE.get(key)
        if cached is not None:
            logger.info(t("log_whisper_model_reused"),
                        settings.model, device, compute_type)
            return cached
        logger.info(t("log_whisper_model_load"),
                    settings.model, device, compute_type)
        try:
            model = WhisperModel(settings.model, device=device,
                                 compute_type=compute_type,
                                 cpu_threads=threads,
                                 num_workers=workers)
        except Exception as exc:  # noqa: BLE001
            raise WhisperError(
                t("err_whisper_model_failed").format(detail=exc)) from exc
        _MODEL_CACHE[key] = model
        logger.info(t("log_whisper_model_lanes"), workers, threads)
        return model


def _resolve_device(settings: WhisperSettings) -> tuple[str, str]:
    """Determine device and compute type; 'auto' picks GPU if present."""
    device = settings.device
    if device == "auto":
        device = "cuda" if _cuda_available() else "cpu"
    compute_type = settings.compute_type
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


def _cuda_available() -> bool:
    """Check whether a CUDA GPU is available for ctranslate2."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001 - missing library or driver
        return False


def _package_version(name: str) -> str:
    """Give the installed version of a package (or 'onbekend')."""
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:  # noqa: BLE001
        return "onbekend"


def _write_transcript(segments: tuple[Segment, ...], path: Path) -> None:
    """Write the text of all segments, one line per segment."""
    lines = [segment.text for segment in segments]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_words_csv(segments: tuple[Segment, ...], path: Path) -> None:
    """Write all words with times and confidence to csv."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=CSV_DELIMITER)
        writer.writerow(["word", "start", "end", "confidence", "segment"])
        for segment in segments:
            for word in segment.words:
                writer.writerow([
                    word.text,
                    f"{word.start:.3f}",
                    f"{word.end:.3f}",
                    f"{word.confidence:.4f}",
                    segment.index,
                ])


def _write_words_json(segments: tuple[Segment, ...], path: Path) -> None:
    """Write all words as a flat JSON list."""
    words = [
        {"text": word.text, "start": word.start, "end": word.end,
         "confidence": word.confidence, "segment": segment.index}
        for segment in segments
        for word in segment.words
    ]
    _write_json(words, path)


def _write_json(data: Any, path: Path) -> None:
    """Write data as readable JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
