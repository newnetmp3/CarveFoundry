from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class RibbonButton(QToolButton):
    def __init__(self, text: str, callback: Callable[[], None] | None = None, *, primary: bool = False):
        super().__init__()
        self.setText(text)
        self.setObjectName("RibbonPrimary" if primary else "RibbonButton")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(22, 22))
        self.setMinimumHeight(52)
        if callback is not None:
            self.clicked.connect(callback)


class RibbonGroup(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("RibbonGroup")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 4)
        outer.setSpacing(3)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(3)
        outer.addLayout(self.buttons, 1)
        label = QLabel(title)
        label.setObjectName("RibbonGroupTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(label)

    def add_button(self, text: str, callback: Callable[[], None] | None = None, *, primary: bool = False) -> RibbonButton:
        button = RibbonButton(text, callback, primary=primary)
        self.buttons.addWidget(button)
        return button


class RibbonPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("RibbonPage")
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(8, 6, 8, 6)
        self.layout_.setSpacing(6)
        self.layout_.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def add_group(self, title: str) -> RibbonGroup:
        group = RibbonGroup(title)
        self.layout_.addWidget(group)
        return group


class Ribbon(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Ribbon")
        self.setDocumentMode(True)
        self.setMovable(False)
        self.setTabsClosable(False)
        self.setFixedHeight(122)

    def add_page(self, title: str) -> RibbonPage:
        page = RibbonPage()
        self.addTab(page, title)
        return page
