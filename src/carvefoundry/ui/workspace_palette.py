"""Searchable keyboard command palette for Beta2.

This UI only invokes existing guarded application commands; there is no new
machining or CNC-controller implementation.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


@dataclass(frozen=True)
class PaletteCommand:
    title: str
    invoke: Callable[[], None]
    enabled: bool = True
    keywords: str = ""


class WorkspaceCommandPalette(QDialog):
    """Small command search with keyboard-first, enabled-action semantics."""

    def __init__(self, commands: list[PaletteCommand], parent=None):
        super().__init__(parent)
        self.setObjectName("BetaCommandPalette")
        self.setWindowTitle("Quick Commands")
        self.setMinimumSize(420, 365)
        self.resize(520, 480)
        self.commands = commands
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        caption = QLabel("Quick Commands  ·  Ctrl+K")
        caption.setObjectName("BetaPaletteTitle")
        root.addWidget(caption)
        self.search = QLineEdit(self)
        self.search.setObjectName("BetaPaletteSearch")
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText(
            "Find a tool, open a workspace, or run a command…"
        )
        root.addWidget(self.search)
        self.results = QListWidget(self)
        self.results.setObjectName("BetaPaletteResults")
        self.results.setAccessibleName("Matching workspace commands")
        root.addWidget(self.results, 1)
        foot = QHBoxLayout()
        note = QLabel("Enter: run  ·  Esc: close")
        note.setObjectName("Muted")
        foot.addWidget(note, 1)
        cancel = QPushButton("Close")
        cancel.clicked.connect(self.reject)
        foot.addWidget(cancel)
        root.addLayout(foot)

        self.search.textChanged.connect(self._refresh)
        self.search.returnPressed.connect(self.run_selected)
        self.results.itemActivated.connect(lambda _item: self.run_selected())
        self._refresh("")
        self.search.setFocus()

    def _refresh(self, query: str) -> None:
        self.results.clear()
        words = query.casefold().split()
        for index, command in enumerate(self.commands):
            searchable = (command.title + " " + command.keywords).casefold()
            if not all(word in searchable for word in words):
                continue
            item = QListWidgetItem(command.title)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsEnabled
                if command.enabled
                else item.flags() & ~Qt.ItemFlag.ItemIsEnabled
            )
            if not command.enabled:
                item.setToolTip("Unavailable for the current job or background process")
            self.results.addItem(item)
        for row in range(self.results.count()):
            item = self.results.item(row)
            if item.flags() & Qt.ItemFlag.ItemIsEnabled:
                self.results.setCurrentRow(row)
                break

    def run_selected(self) -> None:
        item = self.results.currentItem()
        if item is None or not item.flags() & Qt.ItemFlag.ItemIsEnabled:
            return
        command = self.commands[int(item.data(Qt.ItemDataRole.UserRole))]
        if not command.enabled:
            return
        self.accept()
        # Execute after closing to avoid a new modal CAM dialog beneath this one.
        QTimer.singleShot(0, command.invoke)
