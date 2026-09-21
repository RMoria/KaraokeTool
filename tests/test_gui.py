"""Tests for modules.gui (only when PySide6 is present)."""

from __future__ import annotations

import pytest


def test_gui_module_importable() -> None:
    # QtWidgets needs graphical system libraries as well; skip when
    # those are missing (on a bare server, for instance).
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from modules import gui

    assert hasattr(gui, "run_gui")
    assert hasattr(gui, "MainWindow")
