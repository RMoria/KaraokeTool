"""Reading the available fonts from ``assets/fonts`` (B102).

The .ttf/.otf files are shipped along (or fetched once by
``install.bat``). The settings tab reads this folder when it is opened,
so that new fonts appear in the choice menu by themselves without a
code change.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Folder with the bundled fonts (next to this module: ../assets/fonts).
FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"

_FONT_EXTENSIONS = (".ttf", ".otf")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def display_name(filename: str) -> str:
    """Make a readable name out of a font file name.

    ``BebasNeue-Regular.ttf`` -> ``Bebas Neue``; ``Baloo2[wght].ttf`` ->
    ``Baloo 2``. Suffixes such as ``-Regular`` and variable-axis markers
    (``[wght]``) are removed.
    """
    stem = Path(filename).stem
    stem = re.sub(r"\[[^\]]*\]", "", stem)          # remove [wght] etc.
    for suffix in ("-Regular", "-Bold", "-VariableFont", "-wght"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    stem = stem.replace("_", " ").replace("-", " ").strip()
    stem = _CAMEL.sub(" ", stem)                    # BebasNeue -> Bebas Neue
    stem = re.sub(r"(?<=[A-Za-z])(?=[0-9])", " ", stem)  # Baloo2 -> Baloo 2
    return re.sub(r"\s+", " ", stem).strip() or filename


def store_key(path: str, fonts_dir: Path | None = None) -> str:
    """Convert a font path into a *portable* storage value (B245).

    A font from ``assets/fonts`` is stored as a **file name** (e.g.
    ``Anton-Regular.ttf``) instead of as an absolute path. This way the
    choice stays valid after moving the app or on another computer, where
    the absolute path is different (the old storage broke on that and fell
    back to the default font). A manually chosen file outside that folder
    remains an absolute path. Empty stays empty.
    """
    if not path:
        return ""
    directory = (fonts_dir or FONTS_DIR).resolve()
    try:
        p = Path(path).resolve()
    except OSError:
        return path
    if p.parent == directory:
        return p.name
    # Already a bare file name that exists in assets/fonts? Leave as is.
    if Path(path).name == path and (directory / path).is_file():
        return path
    return path


def resolve_font(field_value: str, fonts_dir: Path | None = None) -> str:
    """Convert a stored font value into a usable path.

    The reverse of :func:`store_key`: a bare file name is looked up in
    ``assets/fonts``; an absolute path is returned unchanged. If the named
    file name does not (no longer) exist there, the value is returned
    unchanged so that the existing fallback in the rendering can do its
    work.
    """
    if not field_value:
        return ""
    if Path(field_value).name == field_value:            # bare file name
        candidate = (fonts_dir or FONTS_DIR) / field_value
        if candidate.is_file():
            return str(candidate)
    return field_value


def available_fonts(fonts_dir: Path | None = None
                    ) -> list[tuple[str, str]]:
    """Give ``(display name, path)`` for each font in ``assets/fonts``.

    Sorted by display name. If the folder is missing, the list is empty.
    """
    directory = fonts_dir or FONTS_DIR
    if not directory.exists():
        return []
    items: list[tuple[str, str]] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.suffix.lower() in _FONT_EXTENSIONS:
            items.append((display_name(entry.name), str(entry)))
    items.sort(key=lambda pair: pair[0].lower())
    return items
