"""Helper layer for the optional, large models (Demucs, wav2vec2).

Every large feature only works if the accompanying library is present.
This module provides a simple availability check and some information
(download size, computational cost) for the GUI. If a library is
missing or a download fails, the pipeline falls back to the existing
method and it is retried the next time.

The rhythm anchor (librosa) no longer belongs to these large models: it
is fixed in the core and is always on.
"""

from __future__ import annotations

import importlib.util
import logging

logger = logging.getLogger(__name__)

#: Per feature the required import name and info for the user.
MODEL_INFO: dict[str, dict[str, str]] = {
    "demucs": {
        "module": "demucs",
        "omschrijving": "Zang scheiden (restzang / karaoke maken)",
        "download": "~250 MB (eenmalig)",
        "kosten": "traag op CPU (enkele minuten per nummer), snel op GPU",
    },
    "forced_alignment": {
        "module": "whisperx",
        "omschrijving": "Preciezere woordtijden (wav2vec2)",
        "download": "~360 MB per taal (eenmalig)",
        "kosten": "matig; sneller op GPU",
    },
}


def is_available(feature: str) -> bool:
    """Is the library for this feature installed?"""
    info = MODEL_INFO.get(feature)
    if info is None:
        return False
    return importlib.util.find_spec(info["module"]) is not None


def info_text(feature: str) -> str:
    """Short info (download + compute cost) for the option in the GUI."""
    info = MODEL_INFO.get(feature, {})
    return f"{info.get('download', '')} — {info.get('kosten', '')}"
