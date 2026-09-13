"""Tests voor modules.gui (alleen als PySide6 aanwezig is)."""

from __future__ import annotations

import pytest


def test_gui_module_importable() -> None:
    # QtWidgets vereist ook grafische systeembibliotheken; sla over als
    # die ontbreken (bv. op een kale server).
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from modules import gui

    assert hasattr(gui, "run_gui")
    assert hasattr(gui, "MainWindow")
