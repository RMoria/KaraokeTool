"""Export of the final result.

If the input was mp3, then ``karaoke_edit.mp3`` is written with - where
possible - the same sample rate, the same number of channels and the
same bitrate mode as the source: for VBR the LAME quality is chosen
that comes closest to the average source bitrate, for CBR the nearest
valid mp3 bitrate. If the input was wav, then ``karaoke_edit.wav`` is
written. If the input was m4a/flac/ogg/aac (B280, e.g. a track merged
via Clipchamp or a lossless rip), then ``karaoke_edit.mp3`` is written
as well - there is no separate source-format file for those containers
to save into, and mp3 is the universally shareable format that is
already supported here.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from . import ffmpeg
from .ffmpeg import AudioProperties
from .translations import t

logger = logging.getLogger(__name__)

OUTPUT_STEM = "karaoke_edit"

#: Valid CBR bitrates for mp3 (MPEG-1 layer III), in bit/s.
_CBR_BITRATES: tuple[int, ...] = tuple(
    kbps * 1000 for kbps in (32, 40, 48, 56, 64, 80, 96, 112, 128,
                             160, 192, 224, 256, 320))

#: Average bitrate (kbps) per LAME VBR quality (-q:a 0..9).
_VBR_AVERAGES: tuple[tuple[int, int], ...] = (
    (245, 0), (225, 1), (190, 2), (175, 3), (165, 4),
    (130, 5), (115, 6), (100, 7), (85, 8), (65, 9))


class ExportError(Exception):
    """Error during exporting."""


def export_result(
    processed_wav: Path,
    source_properties: AudioProperties,
    source_suffix: str,
    output_dir: Path,
) -> Path:
    """Export the processed file in the format of the source.

    Args:
        processed_wav: The processed wav file from the karaoke step.
        source_properties: Source properties (from ffprobe, step 1).
        source_suffix: Extension of the source - every extension from
            ``filesystem.SUPPORTED_EXTENSIONS`` (B280: ``.mp3``/``.wav``
            were the original two, ``.m4a``/``.flac``/``.ogg``/
            ``.aac`` are later input extensions).
        output_dir: Target folder (``output``).

    Returns:
        The path of ``karaoke_edit.mp3`` or ``karaoke_edit.wav`` - the
        output always remains one of those two (mp3 for every source
        that is not wav), regardless of which extra input format has
        been added.

    Raises:
        ExportError: On an unknown source format or missing input.
    """
    if not processed_wav.exists():
        raise ExportError(
            t("err_export_processed_missing").format(path=processed_wav))
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_suffix.lower()

    if suffix == ".wav":
        target = output_dir / f"{OUTPUT_STEM}.wav"
        shutil.copyfile(processed_wav, target)
        logger.info(t("log_export_wav"), target)
        return target

    if suffix in (".mp3", ".m4a", ".flac", ".ogg", ".aac"):
        target = output_dir / f"{OUTPUT_STEM}.mp3"
        if source_properties.is_vbr:
            quality = vbr_quality_for(source_properties.bit_rate)
            logger.info(t("log_export_mp3_vbr"),
                        source_properties.bit_rate, quality)
            ffmpeg.encode_mp3(processed_wav, target,
                              sample_rate=source_properties.sample_rate,
                              channels=source_properties.channels,
                              vbr_quality=quality)
        else:
            bitrate = nearest_cbr_bitrate(source_properties.bit_rate)
            logger.info(t("log_export_mp3_cbr"), bitrate)
            ffmpeg.encode_mp3(processed_wav, target,
                              sample_rate=source_properties.sample_rate,
                              channels=source_properties.channels,
                              bitrate=bitrate)
        return target

    raise ExportError(
        t("err_export_unknown_format").format(suffix=source_suffix))


def nearest_cbr_bitrate(bit_rate: int | None) -> int:
    """Choose the valid mp3 CBR bitrate that comes closest to the source.

    Without a known source bitrate, 192 kbps is used.
    """
    if bit_rate is None or bit_rate <= 0:
        return 192_000
    return min(_CBR_BITRATES, key=lambda candidate: abs(candidate - bit_rate))


def vbr_quality_for(bit_rate: int | None) -> int:
    """Choose the LAME VBR quality that approaches the average bitrate.

    Without a known source bitrate, quality 2 (~190 kbps) is used.
    """
    if bit_rate is None or bit_rate <= 0:
        return 2
    kbps = bit_rate / 1000.0
    return min(_VBR_AVERAGES,
               key=lambda entry: abs(entry[0] - kbps))[1]
