"""Vocal separation with Demucs (optional).

Is used to:

* isolate the **vocal stem** of the karaoke, so that residual vocals
  are much more reliably detectable than on the mixed karaoke;
* make a **karaoke version out of the original** (vocals removed -> the
  instrumental stem), so that a separate karaoke is not needed.

Demucs runs via a subprocess (``python -m demucs``), so that we do not
depend on a specific Python API version. If Demucs is missing or it
does not succeed, this module raises a :class:`SeparationError` and the
pipeline falls back to the ordinary method (and tries again the next
time).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from . import models, proc
from .translations import t

logger = logging.getLogger(__name__)


class SeparationError(Exception):
    """Error while separating the stems."""


def is_available() -> bool:
    """Is Demucs installed?"""
    return models.is_available("demucs")


def separate(audio_path: Path, work_dir: Path,
             model: str = "htdemucs") -> dict[str, Path]:
    """Separate a file into a vocal and an instrumental stem.

    Args:
        audio_path: The audio file to be separated.
        work_dir: Folder in which Demucs writes its result.
        model: Demucs model (``htdemucs`` by default).

    Returns:
        ``{"vocals": path, "instrumental": path}`` (wav files).

    Raises:
        SeparationError: If Demucs is missing or the separation fails.
    """
    if not is_available():
        raise SeparationError("Demucs is niet geïnstalleerd.")
    # Empty the work folder first so that old stems are never reused
    # (B135).
    if work_dir.exists():
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    # Windowless interpreter: on Windows Demucs (via torch/
    # multiprocessing) otherwise starts its own cmd windows (B89).
    command = [proc.windowless_python(), "-m", "demucs", "--two-stems",
               "vocals", "-n", model, "-o", str(work_dir), str(audio_path)]
    logger.info(t("log_demucs_separating"), audio_path.name)
    try:
        # B356: via proc.run, zodat een afbreken Demucs echt stopt in
        # plaats van drie minuten uit te zitten.
        proc.run(command, check=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise SeparationError(f"Demucs faalde: {detail}") from exc

    vocals = _find_stem(work_dir, "vocals")
    instrumental = _find_stem(work_dir, "no_vocals")
    if vocals is None or instrumental is None:
        raise SeparationError("Demucs leverde geen stemmen op.")
    return {"vocals": vocals, "instrumental": instrumental}


def _find_stem(work_dir: Path, name: str) -> Path | None:
    """Find a separated stem (``<model>/<name>/<stem>.wav``)."""
    matches = sorted(work_dir.glob(f"**/{name}.wav"))
    return matches[-1] if matches else None


def separate_cached(audio_path: Path, cache_root: Path, key: str,
                    model: str = "htdemucs") -> dict[str, Path]:
    """Separate a source, but at most once per source (B135/B248).

    The stems are stored in a fixed folder per source
    (``<cache_root>/demucs_stems_<key>/``). If a ``vocals.wav`` and a
    ``no_vocals.wav`` are already there, then those are reused and Demucs
    does not run again. This way the same source (e.g. the original) is not
    separated several times for the different purposes (vocal stem analysis,
    karaoke-from-original, transcription). If the cache is emptied, then the
    folder disappears and the next run separates again by itself.

    Args:
        audio_path: The audio file to be separated.
        cache_root: The cache folder of the project (``paths.cache_dir``).
        key: Stable name for the source, e.g. ``"original"`` or
            ``"karaoke"``.
        model: Demucs model.

    Returns:
        ``{"vocals": path, "instrumental": path}``.

    Raises:
        SeparationError: If Demucs is missing or the separation fails.
    """
    store = cache_root / f"demucs_stems_{key}"
    vocals = store / "vocals.wav"
    instrumental = store / "no_vocals.wav"
    marker = store / "source.sha1"
    checksum = _source_checksum(audio_path)
    if vocals.exists() and instrumental.exists():
        if _marker_matches(marker, checksum, model):
            _write_marker(marker, checksum, model)   # upgrade, B548
            logger.info(t("log_demucs_reused"),
                        key, store)
            return {"vocals": vocals, "instrumental": instrumental}
        # B311: the stems belong to OTHER audio. Reusing them anyway is
        # exactly how v0.96 went wrong: Whisper transcribes the vocal
        # stem, so a stale stem silently gives a stale transcription of a
        # song that is no longer there. Separate again.
        logger.info(t("log_demucs_stale"), key)

    # Not yet (completely) in the cache: separate once and put the stems in
    # the fixed place. We separate into a temporary work folder and copy the
    # two stems out of it, so that the fixed place is predictable and does
    # not depend on the internal folder structure of Demucs (<model>/<name>/).
    import shutil
    fresh = separate(audio_path, cache_root / f"demucs_work_{key}", model)
    store.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(fresh["vocals"], vocals)
        shutil.copyfile(fresh["instrumental"], instrumental)
    except OSError as exc:
        # Copying failed: return the fresh stems so that the run can go on.
        logger.warning(t("log_demucs_copy_failed"), exc)
        return fresh
    # Clean up the (large) work folder; the stems are now in the fixed place.
    shutil.rmtree(cache_root / f"demucs_work_{key}", ignore_errors=True)
    _write_marker(marker, checksum, model)
    logger.info(t("log_demucs_cached"), key, store)
    return {"vocals": vocals, "instrumental": instrumental}


def _source_checksum(audio_path: Path) -> str:
    """Fingerprint of the audio that the stems belong to (B311)."""
    from .filesystem import file_sha1
    try:
        return file_sha1(audio_path)
    except OSError:
        return ""


def _demucs_version() -> str:
    """The installed Demucs version, or empty when it cannot be read."""
    from importlib.metadata import version

    try:
        return str(version("demucs"))
    except Exception:  # noqa: BLE001 - a marker may never break a run
        return ""


def _stamp(checksum: str, model: str) -> str:
    """What the stems were made from: audio, model, Demucs (B548)."""
    return "\n".join([checksum, model, _demucs_version()])


def _write_marker(marker: Path, checksum: str, model: str) -> None:
    """Note beside the stems what they were made from.

    Also upgrades a marker from before B548, which held the checksum
    alone: writing the full stamp costs nothing and the next run then
    has the whole answer.
    """
    if not checksum:
        return
    try:
        marker.write_text(_stamp(checksum, model), encoding="utf-8")
    except OSError as exc:          # marker is a bonus, not a condition
        logger.warning(t("log_demucs_marker_failed"), exc)


def _marker_matches(marker: Path, checksum: str, model: str) -> bool:
    """Do the cached stems belong to this audio, model and Demucs?

    B311 asked the first of those three. B548 added the other two: the
    ``model`` argument of :func:`separate_cached` was accepted, passed
    on and never written down, so ``htdemucs_ft`` silently got
    ``htdemucs`` stems back. And a Demucs upgrade - which
    ``install.bat`` invites - leaves stems whose marker still matches,
    so the old model's separation would be reused for ever and Whisper
    would keep transcribing it. That is the B311 failure through
    another door.

    Stems without a marker at all come from before B311. Those are
    still accepted: throwing away a separation that is probably fine
    costs minutes per song, and from the next run onwards there IS a
    marker.

    A marker of ONE line is from before B548 and is not accepted. The
    first thought was to let it pass on its checksum, since the stems
    under it were probably made by the Demucs that is installed now -
    but "probably" is exactly wrong here: a marker from before this
    check is precisely the one that may predate an upgrade, and
    passing it would then also stamp those stems as belonging to the
    new version, so the mistake would never be findable again. It
    costs one separation per project, once.

    A torn write lands in the same branch, which is the second reason:
    half a marker says nothing, and this way it says nothing loudly.
    """
    if not checksum:
        return True
    if not marker.exists():
        return True
    try:
        written = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return True
    if "\n" not in written:     # from before B548, or half written
        return False
    return written == _stamp(checksum, model).strip()


def warmup(model: str = "htdemucs") -> None:
    """Load the Demucs model once (forces the download)."""
    if not is_available():
        raise SeparationError("Demucs is niet geïnstalleerd.")
    try:
        from demucs.pretrained import get_model  # type: ignore
        get_model(model)
    except Exception as exc:  # noqa: BLE001
        raise SeparationError(f"Demucs-model laden mislukt: {exc}") from exc
