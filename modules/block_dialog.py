"""Link and unlink the blocks of the karaoke text (v1.0.15, B600).

Reached from tab 1, next to the karaoke text. Every block is a row,
with the group it is linked in. The program fills the groups in - the
blocks with the same text - and the owner links or unlinks what he
wants: linked blocks share their timing inside the block in the timing
editor, and what is heard in them is combined.
"""
from __future__ import annotations

import string
from typing import Sequence

from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import song_structure
from .translations import t


class BlockLinksDialog(QDialog):
    """A table of blocks with their groups, and three buttons."""

    def __init__(self, blocks: Sequence[song_structure.Block],
                 groups: Sequence[Sequence[int]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("block_links_title"))
        self.resize(720, 460)
        self._blocks = list(blocks)
        self._groups = song_structure.clean_links(groups, self._blocks)
        layout = QVBoxLayout(self)
        explain = QLabel(t("block_links_explain"))
        explain.setWordWrap(True)
        layout.addWidget(explain)
        self._table = QTableWidget(len(self._blocks), 4)
        self._table.setHorizontalHeaderLabels(
            [t("block_links_col_block"), t("block_links_col_lines"),
             t("block_links_col_text"), t("block_links_col_group")])
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setColumnWidth(2, 420)
        layout.addWidget(self._table, stretch=1)
        self._message = QLabel("")
        self._message.setStyleSheet("color: #a33;")
        layout.addWidget(self._message)
        buttons = QHBoxLayout()
        for key, handler in (("block_links_link", self._link),
                             ("block_links_unlink", self._unlink),
                             ("block_links_auto", self._auto)):
            button = QPushButton(t(key))
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch(1)
        ok = QPushButton(t("block_links_save"))
        cancel = QPushButton(t("block_links_cancel"))
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self._fill()

    def groups(self) -> list[list[int]]:
        return [list(group) for group in self._groups]

    def _letter(self, number: int) -> str:
        for n, group in enumerate(self._groups):
            if number in group:
                letters = string.ascii_uppercase
                return letters[n % 26] + ("" if n < 26 else str(n // 26))
        return "-"

    def _fill(self) -> None:
        for row, block in enumerate(self._blocks):
            for column, value in enumerate(
                    (str(block.number + 1), str(len(block.lines)),
                     block.title, self._letter(block.number))):
                self._table.setItem(row, column, QTableWidgetItem(value))

    def _selected(self) -> list[int]:
        rows = sorted({index.row() for index in
                       self._table.selectionModel().selectedRows()})
        return [self._blocks[row].number for row in rows]

    def _link(self) -> None:
        chosen = self._selected()
        if len(chosen) < 2:
            self._message.setText(t("block_links_pick_two"))
            return
        sizes = {len(block.lines) for block in self._blocks
                 if block.number in chosen}
        if len(sizes) > 1:
            self._message.setText(t("block_links_sizes"))
            return
        rest = [[n for n in group if n not in chosen]
                for group in self._groups]
        self._groups = song_structure.clean_links(
            rest + [sorted(chosen)], self._blocks)
        self._message.setText("")
        self._fill()

    def _unlink(self) -> None:
        chosen = set(self._selected())
        self._groups = song_structure.clean_links(
            [[n for n in group if n not in chosen]
             for group in self._groups], self._blocks)
        self._message.setText("")
        self._fill()

    def _auto(self) -> None:
        self._groups = song_structure.auto_links(self._blocks)
        self._message.setText("")
        self._fill()
