"""Wrapper around ffmpeg and ffprobe.

Responsible for reading out source properties (bitrate, sample rate,
channels, VBR/CBR) and converting mp3 to wav. The properties are used
later by ``export.py`` to keep the output as close to the source as
possible.

ffmpeg/ffprobe are looked for in the PATH and in addition in the folder
``bin`` of the project, so that installation without a PATH adjustment
also works (simply put the exe's in ``KaraokeTool/bin``).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

from . import proc
from .translations import t

logger = logging.getLogger(__name__)

#: Project-local folder in which ffmpeg.exe/ffprobe.exe may be placed.
_BIN_DIR = Path(__file__).resolve().parents[1] / "bin"


class FfmpegError(Exception):
    """Error while running ffmpeg or ffprobe."""


@dataclass(frozen=True)
class AudioProperties:
    """Properties of an audio file, read out with ffprobe."""

    codec: str
    sample_rate: int
    channels: int
    bit_rate: int | None
    duration: float
    container: str
    is_vbr: bool | None


def find_executable(name: str) -> str | None:
    """Look for a program in the PATH or in the project folder ``bin``.

    Args:
        name: Program name without extension, e.g. ``"ffmpeg"``.

    Returns:
        The full path to the program, or ``None``.
    """
    found = shutil.which(name)
    if found:
        return found
    for candidate in (_BIN_DIR / f"{name}.exe", _BIN_DIR / name):
        if candidate.is_file():
            return str(candidate)
    return None


def is_available() -> bool:
    """Check whether both ffmpeg and ffprobe can be found."""
    return find_executable("ffmpeg") is not None and find_executable("ffprobe") is not None


def probe(path: Path) -> AudioProperties:
    """Read out the audio properties of a file with ffprobe.

    Args:
        path: Path to the audio file.

    Returns:
        The properties read out. For mp3 an additional VBR/CBR detection
        on packet sizes is performed.

    Raises:
        FfmpegError: If ffprobe is missing, fails or finds no audio stream.
    """
    result = _run([
        _tool("ffprobe"), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FfmpegError(
            t("err_ffprobe_unreadable").format(path=path)) from exc

    properties = _parse_probe_output(data)
    if path.suffix.lower() == ".mp3":
        properties = replace(properties, is_vbr=_probe_vbr(path))
    logger.info(t("log_properties"), path.name, properties)
    return properties


def convert_to_wav(source: Path, target: Path) -> Path:
    """Convert an audio file to 16-bit PCM wav.

    Sample rate and channels stay the same as the source.

    Args:
        source: Source file (e.g. mp3).
        target: Target path for the wav file.

    Returns:
        The path to the written wav file.

    Raises:
        FfmpegError: If ffmpeg is missing or the conversion fails.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    _run([_tool("ffmpeg"), "-y", "-v", "error", "-i", str(source),
          "-acodec", "pcm_s16le", str(target)])
    logger.info(t("log_converted_wav"), source.name, target.name)
    return target


def resample_to_match(
    source: Path,
    target: Path,
    sample_rate: int,
    channels: int,
) -> Path:
    """Convert to wav with a SPECIFIED sample rate/channel count (B282).

    In contrast to :func:`convert_to_wav` (source properties stay the
    same) the conversion here is explicitly to ``sample_rate``/
    ``channels`` - needed to mix the original into a karaoke track with
    a different sample rate (e.g. "back from original" in the damping
    editor, where original and karaoke can be separately supplied files
    each with their own properties).

    Raises:
        FfmpegError: If ffmpeg is missing or the conversion fails.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    _run([_tool("ffmpeg"), "-y", "-v", "error", "-i", str(source),
          "-acodec", "pcm_s16le", "-ar", str(sample_rate),
          "-ac", str(channels), str(target)])
    logger.info(t("log_resampled"),
               source.name, target.name, sample_rate, channels)
    return target


def encode_mp3(
    source: Path,
    target: Path,
    sample_rate: int,
    channels: int,
    bitrate: int | None = None,
    vbr_quality: int | None = None,
) -> Path:
    """Encode a wav file to mp3 (LAME) with the specified properties.

    Args:
        source: Source wav.
        target: Target mp3.
        sample_rate: Sample rate in Hz.
        channels: Number of channels.
        bitrate: CBR bitrate in bit/s (excludes ``vbr_quality``).
        vbr_quality: LAME VBR quality 0-9 (takes precedence over
            ``bitrate``).

    Raises:
        FfmpegError: If ffmpeg is missing or the encoding fails.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    args = [_tool("ffmpeg"), "-y", "-v", "error", "-i", str(source),
            "-codec:a", "libmp3lame",
            "-ar", str(sample_rate), "-ac", str(channels)]
    if vbr_quality is not None:
        args += ["-q:a", str(vbr_quality)]
    elif bitrate is not None:
        args += ["-b:a", str(bitrate)]
    args.append(str(target))
    _run(args)
    logger.info(t("log_mp3_written"), target.name)
    return target


def _tool(name: str) -> str:
    """Give the path to a required program or raise a clear error."""
    path = find_executable(name)
    if path is None:
        raise FfmpegError(t("err_ffmpeg_tool_missing").format(
            name=name, folder=_BIN_DIR))
    return path


def _run(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run an ffmpeg/ffprobe command with error handling."""
    logger.debug(t("log_command"), " ".join(args))
    try:
        # B356: through proc.run, so that Stop can really kill it.
        return proc.run(list(args), check=True)
    except FileNotFoundError as exc:
        raise FfmpegError(
            t("err_program_missing").format(name=args[0])) from exc
    except subprocess.CalledProcessError as exc:
        raise FfmpegError(t("err_program_failed").format(
            name=args[0], code=exc.returncode,
            detail=exc.stderr.strip())) from exc


def _parse_probe_output(data: dict[str, Any]) -> AudioProperties:
    """Convert the JSON output of ffprobe to :class:`AudioProperties`."""
    streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise FfmpegError(t("err_ffmpeg_no_audio_stream"))
    stream = streams[0]
    fmt = data.get("format", {})

    bit_rate_raw = stream.get("bit_rate") or fmt.get("bit_rate")
    bit_rate = int(bit_rate_raw) if bit_rate_raw is not None else None
    duration_raw = fmt.get("duration") or stream.get("duration") or 0.0

    return AudioProperties(
        codec=str(stream.get("codec_name", t("value_unknown"))),
        sample_rate=int(stream.get("sample_rate", 0)),
        channels=int(stream.get("channels", 0)),
        bit_rate=bit_rate,
        duration=float(duration_raw),
        container=str(fmt.get("format_name", t("value_unknown"))),
        is_vbr=None,
    )


def _probe_vbr(path: Path) -> bool | None:
    """Detect VBR by comparing packet sizes of the first frames."""
    try:
        result = _run([
            _tool("ffprobe"), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "packet=size", "-read_intervals", "%+#120",
            "-print_format", "json", str(path),
        ])
        packets = json.loads(result.stdout).get("packets", [])
        sizes = [int(p["size"]) for p in packets if "size" in p]
    except (FfmpegError, json.JSONDecodeError, ValueError):
        logger.warning(t("log_vbr_failed"), path.name)
        return None
    return _detect_vbr(sizes)


def _detect_vbr(sizes: Sequence[int]) -> bool | None:
    """Determine VBR/CBR from a series of packet sizes.

    The first and last frames are skipped (headers such as Xing/Info
    and padding deviate). More than two different sizes in the core
    points to VBR.

    Returns:
        ``True`` (VBR), ``False`` (CBR) or ``None`` (too little data).
    """
    if len(sizes) < 10:
        return None
    core = sizes[3:-3]
    return len(set(core)) > 2


#: Sample rate of the audio in the video. loudnorm works internally at
#: 192 kHz and would otherwise pass that straight on.
OUTPUT_RATE = 48000

#: The ranges loudnorm accepts for its own measured values (B459). Each
#: has its own: a loudness is negative, a range is positive, and a true
#: peak can perfectly well sit just above zero - measured on the user's
#: own material, "Lied M" peaks at +0.12 dBTP.
_I_RANGE = (-99.0, 0.0)
_TP_RANGE = (-99.0, 99.0)
_LRA_RANGE = (0.0, 99.0)


@dataclass(frozen=True)
class Loudness:
    """What the first loudnorm pass measured (B456)."""

    #: Integrated loudness in LUFS.
    integrated: float
    #: True peak in dBTP.
    true_peak: float
    #: Loudness range in LU.
    lra: float
    #: Threshold, needed by the second pass.
    threshold: float


def measure_loudness(path: Path, target: float = -16.0,
                     peak: float = -1.0) -> Loudness | None:
    """The first loudnorm pass: what is this track (B456)?

    Two passes and not one, because a single pass has to guess as it
    goes and gets the beginning of a song wrong. Measuring first costs a
    few seconds on an audio file and gives a result that is exactly
    reproducible.

    ``None`` when the measurement fails - a level is a nicety, not a
    reason to drop a render.
    """
    import json as _json

    try:
        done = proc.run([
            _tool("ffmpeg"), "-nostdin", "-hide_banner", "-i", str(path),
            "-af", (f"loudnorm=I={target}:TP={peak}:LRA=11"
                    ":print_format=json"),
            "-f", "null", "-"], check=False)
    except (OSError, subprocess.SubprocessError):
        logger.exception(t("log_loudness_failed"))
        return None
    text = (done.stderr or "") + (done.stdout or "")
    start = text.rfind("{")
    if start < 0:
        return None
    try:
        data = _json.loads(text[start:text.rindex("}") + 1])
        values = [float(data[key]) for key in
                  ("input_i", "input_tp", "input_lra", "input_thresh")]
    except (ValueError, KeyError):
        logger.exception(t("log_loudness_failed"))
        return None
    # A silent (or good as silent) file measures -inf, and loudnorm
    # refuses its own measurement back: "value out of range", after which
    # the render dies on a filter string. Nothing to normalise there
    # anyway, so: no measurement.
    #
    # B459: with the ranges loudnorm ITSELF accepts, and not one range
    # for all four. The first version demanded -99..0 for the loudness
    # range as well, and that one is POSITIVE by definition - it is a
    # range in LU, not a level. So every piece of music with any dynamic
    # at all was rejected, which silently switched off both the
    # normalisation in the video and the whole of 1.5.11e. The test that
    # should have caught it used a pure sine, and that is the one signal
    # with a range of exactly 0.0.
    if not all(value == value and abs(value) != float("inf")
               for value in values):
        logger.info(t("log_loudness_silent"))
        return None
    integrated, true_peak, lra, threshold = values
    if not (_I_RANGE[0] <= integrated <= _I_RANGE[1]
            and _TP_RANGE[0] <= true_peak <= _TP_RANGE[1]
            and _LRA_RANGE[0] <= lra <= _LRA_RANGE[1]
            and _I_RANGE[0] <= threshold <= _I_RANGE[1]):
        logger.info(t("log_loudness_silent"))
        return None
    return Loudness(integrated=integrated, true_peak=true_peak,
                    lra=lra, threshold=threshold)


def leading_silence(path: Path, look: float = 30.0) -> float | None:
    """How many seconds of silence a file starts with (B530).

    Used to check a finished render against itself: the intro shifts the
    picture forward and exactly the same amount of silence has to stand
    in front of the sound, or the whole video runs out of step. ``None``
    when it cannot be measured - that is not a reason to drop a render,
    but the caller then knows it has checked nothing.
    """
    try:
        done = proc.run([
            _tool("ffmpeg"), "-nostdin", "-hide_banner",
            "-t", f"{look:.3f}", "-i", str(path),
            "-af", "silencedetect=noise=-60dB:duration=0.10",
            "-f", "null", "-"], check=False)
    except (OSError, subprocess.SubprocessError, FfmpegError):
        logger.exception(t("log_silence_measure_failed"), path.name)
        return None
    if done.returncode != 0:
        # An unreadable or missing file measures nothing. Saying "zero
        # seconds of silence" here would be a claim, and the caller acts
        # on that claim by refusing a render.
        logger.warning(t("log_silence_measure_failed"), path.name)
        return None
    text = (done.stderr or "") + (done.stdout or "")
    # Only the FIRST reported silence can be the one at the beginning.
    # A later one says nothing about the start - and reading on would
    # turn "the sound starts straight away" into "cannot measure",
    # exactly in the case this check exists for.
    first = None
    for line in text.splitlines():
        if "silence_start:" in line:
            try:
                first = float(line.rsplit("silence_start:", 1)[1].split()[0])
            except (ValueError, IndexError):
                return None
            break
    if first is None or first > 0.05:
        # No silence at all, or the first one begins later: the sound
        # starts straight away. That is a measurement (zero).
        return 0.0
    for line in text.splitlines():
        if "silence_end:" in line:
            try:
                return float(line.rsplit("silence_end:", 1)[1].split()[0])
            except (ValueError, IndexError):
                return None
    # It starts silent and never ends within the window we looked at.
    return None


def delay_filter(seconds: float, channels: int = 2) -> str:
    """Silence in front of the sound, in a way that cannot be dropped
    (B530).

    Two things went wrong with the old ``adelay=<ms>:all=1`` at the END
    of the chain, and both are avoided here.

    The layout: the user's karaoke.wav files carry ``channel_layout=
    unknown`` (measured on his whole collection). ``all=1`` has to bind
    to the channels of a known layout, and without one ffmpeg either
    refuses the link outright - "Cannot select channel layout for the
    link between filters" - or, worse, delays nothing at all and says
    nothing about it. So the layout is named first.

    The place: the delay goes at the FRONT of the chain, before
    loudnorm. loudnorm reconfigures its filter graph part-way through a
    track (it decides between a straight gain and dynamic compression
    after its look-ahead), and anything downstream of it is rebuilt at
    that moment. Silence that is already in the stream by then cannot be
    lost. Deliberately not after: that is exactly the construction that
    produced three videos in which the picture ran up to eight seconds
    ahead of the sound.
    """
    milliseconds = int(round(seconds * 1000))
    # One delay per channel instead of ``all=1``: that way the filter
    # never has to work out how many channels "all" means, whatever the
    # layout says.
    delay = "adelay=" + "|".join([str(milliseconds)] * max(1, channels))
    layout = {1: "mono", 2: "stereo"}.get(channels)
    if layout is None:
        return delay
    return f"aformat=channel_layouts={layout},{delay}"


def loudnorm_filter(measured: Loudness, target: float = -16.0,
                    peak: float = -1.0) -> str:
    """The second-pass filter string, with the measurement filled in.

    ``linear=true`` is the whole point for this project: the user sings
    over source material that is not of the best quality, so the aim is
    the LEAST damage. With ``linear`` ffmpeg applies one straight gain
    as long as it stays under the peak ceiling, and only falls back to
    dynamic compression for a track that cannot reach the target
    otherwise. Measured over eighteen karaoke tracks: at -16 LUFS
    thirteen of them get a plain gain and the other five need at most
    2.1 dB of help; at -11 all eighteen would go through the limiter,
    with a heaviest intervention of 7.1 dB.
    """
    # ``aresample`` is not decoration. loudnorm works internally at
    # 192 kHz and passes that on, so without this every video would be
    # encoded at 96 kHz - twice the file size for audio nobody can hear
    # the difference of.
    return (f"loudnorm=I={target}:TP={peak}:LRA=11"
            f":measured_I={measured.integrated}"
            f":measured_TP={measured.true_peak}"
            f":measured_LRA={measured.lra}"
            f":measured_thresh={measured.threshold}"
            ":linear=true:print_format=summary"
            f",aresample={OUTPUT_RATE}")


def reachable_loudness(measured: Loudness, peak: float = -1.0) -> float:
    """The loudest this track gets on a straight gain alone (B456).

    Above this the limiter has to step in. Reported next to the target
    so it is visible WHICH song had to give something up, instead of
    quietly sounding flatter than the rest.
    """
    return round(measured.integrated + (peak - measured.true_peak), 2)
