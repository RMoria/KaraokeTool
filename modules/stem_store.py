"""Stems of a test kept for later, small enough to keep (v1.0.22, B632).

A blend of separations (:mod:`modules.stem_blend`) needs the stems of
its parts, and a round of 1.5.14 throws its stems away once it has
measured them. Separating again for every blend is cheap for Demucs and
costs an hour a song for a Roformer model on a processor - so the rounds
of the ways a blend is made of keep their stems here, beside the test,
and a blend round takes them from here where they are.

A float stem of four minutes is 85 MB; kept as 24-bit FLAC it is about
half. FLAC holds no numbers above full scale, and the stems keep the
level of the original (B597), so a stem that peaks above it is kept
turned down with its factor beside it, and given back at its own level:
24 bits leave its noise 140 dB under the music, far below anything a
test measures.

One folder per way (its tag, made safe), each written beside itself and
put in place in one move, so a blend never reads half a stem.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import numpy as np

from .translations import t

logger = logging.getLogger(__name__)

#: Beside the stems: per stem the factor it was turned down by.
GAIN_FILE = "gain.json"
#: A stem above this peak is turned down to it before it is kept.
_CEILING = 0.999


def _safe(tag: str) -> str:
    """A folder name for a tag: readable, short, and never the same for
    two tags (a long tag is cut, with a hash of the whole behind it)."""
    import hashlib

    safe = "".join(ch if ch.isalnum() else "_" for ch in tag)
    if len(safe) <= 60:
        return safe
    digest = hashlib.sha1(tag.encode("utf-8")).hexdigest()[:12]
    return f"{safe[:60]}_{digest}"


class StemStore:
    """The kept stems of one song (one folder)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def folder(self, tag: str) -> Path:
        return self.root / _safe(tag)

    def has(self, tag: str) -> bool:
        folder = self.folder(tag)
        return (folder / GAIN_FILE).is_file() and \
            (folder / "vocals.flac").is_file() and \
            (folder / "instrumental.flac").is_file()

    def get(self, tag: str, into: Path) -> dict[str, Path] | None:
        """The stems of ``tag`` as float wav files in ``into``, at their
        own level; ``None`` when they are not (all) there."""
        import soundfile

        if not self.has(tag):
            return None
        folder = self.folder(tag)
        try:
            gains = json.loads((folder / GAIN_FILE).read_text(
                encoding="utf-8"))
            into.mkdir(parents=True, exist_ok=True)
            stems = {}
            for path in sorted(folder.glob("*.flac")):
                data, rate = soundfile.read(str(path), dtype="float32",
                                            always_2d=True)
                factor = float(gains.get(path.stem, 1.0) or 1.0)
                if factor != 1.0:
                    data = data * np.float32(factor)
                target = into / f"{path.stem}.wav"
                soundfile.write(str(target), data, rate, subtype="FLOAT")
                stems[path.stem] = target
        except (OSError, ValueError, RuntimeError):
            logger.warning(t("log_stem_store_unreadable"), folder)
            return None
        return stems

    def put(self, tag: str, stems: dict) -> bool:
        """Keep ``stems`` (``{name: wav path}``) under ``tag``. Already
        kept, or the share away: nothing happens. Returns whether they are
        kept now."""
        import soundfile

        if self.has(tag):
            return True
        import uuid

        folder = self.folder(tag)
        spare = folder.with_name(folder.name + f".part{uuid.uuid4().hex}")
        try:
            shutil.rmtree(spare, ignore_errors=True)
            spare.mkdir(parents=True, exist_ok=True)
            gains = {}
            for name, path in stems.items():
                if not isinstance(path, (str, Path)) or \
                        not Path(path).is_file():
                    continue
                data, rate = soundfile.read(str(path), dtype="float32",
                                            always_2d=True)
                peak = float(np.max(np.abs(data))) if data.size else 0.0
                factor = peak / _CEILING if peak > _CEILING else 1.0
                if factor != 1.0:
                    data = data / np.float32(factor)
                soundfile.write(str(spare / f"{name}.flac"), data, rate,
                                format="FLAC", subtype="PCM_24")
                gains[name] = round(factor, 6)
            (spare / GAIN_FILE).write_text(json.dumps(gains),
                                           encoding="utf-8")
            if folder.exists():             # a twin was quicker
                shutil.rmtree(spare, ignore_errors=True)
                return self.has(tag)
            spare.rename(folder)
            return True
        except (OSError, RuntimeError):
            shutil.rmtree(spare, ignore_errors=True)
            logger.warning(t("log_stem_store_not_kept"), folder)
            return False
