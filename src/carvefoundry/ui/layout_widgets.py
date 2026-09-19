"""Reusable compact, accessible workspace section controls."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class InspectorSection(QFrame):
    """A persistent one-click accordion with an actual, focusable header.

    Collapsing only hides the panel's content, not the whole Inspector or
    its model state. Layout and controls stay alive across object selection,
    tool changes and reopening the app.
    """

    def __init__(
        self,
        title: str,
        *,
        key: str,
        settings,
        expanded: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("InspectorSection")
        self._settings = settings
        self._key = f"interface/inspector_sections/{key}"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(3)
        header = QToolButton(self)
        header.setObjectName("InspectorSectionToggle")
        header.setText(title)
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        header.setCheckable(True)
        header.setAutoRaise(True)
        header.setAccessibleName(f"Expand or collapse {title}")
        header.setToolTip(f"Expand or collapse {title}")
        layout.addWidget(header)
        body = QWidget(self)
        body.setObjectName("InspectorSectionBody")
        content = QVBoxLayout(body)
        content.setContentsMargins(4, 1, 0, 5)
        content.setSpacing(6)
        layout.addWidget(body)
        self.header = header
        self.body = body
        self.content_layout = content

        def on_toggled(value: bool) -> None:
            body.setVisible(value)
            header.setArrowType(
                Qt.ArrowType.DownArrow if value else Qt.ArrowType.RightArrow
            )
            self._settings.setValue(self._key, value)

        header.toggled.connect(on_toggled)
        self.setExpanded(
            bool(settings.value(self._key, expanded, type=bool))
        )

    def setExpanded(self, expanded: bool) -> None:
        self.header.setChecked(bool(expanded))
        # setChecked() does not emit toggled when state was unchanged.
        self.body.setVisible(bool(expanded))
        self.header.setArrowType(
            Qt.ArrowType.DownArrow
            if expanded else Qt.ArrowType.RightArrow
        )

    def isExpanded(self) -> bool:
        return self.header.isChecked()
