"""Reusable compact, accessible workspace section controls."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
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


class CamSectionNavigator(QFrame):
    """Fixed step rail for the long CAM form; retains the full editable form.

    This only changes UI navigation. No CAM controls are moved, cloned or
    replaced, and the existing readiness and G-code checks remain authoritative.
    """

    def __init__(self, scroll: QScrollArea, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CamSectionNavigator")
        self._scroll = scroll
        self._sections: dict[str, tuple[QPushButton, QWidget]] = {}
        self._active: str | None = None
        self.setFixedWidth(166)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(5)
        heading = QLabel("JOB STEPS", self)
        heading.setObjectName("CamStepHeading")
        layout.addWidget(heading)
        self._layout = layout
        layout.addStretch(1)

    def add_section(self, key: str, title: str, widget: QWidget) -> None:
        if key in self._sections:
            raise ValueError(f"Duplicate CAM section: {key}")
        button = QPushButton(title, self)
        button.setObjectName("CamStepButton")
        button.setCheckable(True)
        button.setToolTip(f"Jump to {title}")
        button.setAccessibleName(f"Jump to CAM section {title}")
        button.setProperty("state", "pending")
        button.clicked.connect(
            lambda _checked=False, name=key: self.navigate(name)
        )
        self._layout.insertWidget(self._layout.count() - 1, button)
        self._sections[key] = (button, widget)
        if self._active is None:
            self._active = key
            button.setChecked(True)

    def navigate(self, key: str) -> None:
        if key not in self._sections:
            raise KeyError(key)
        button, widget = self._sections[key]
        if not button.isEnabled() or widget.isHidden():
            return
        self._active = key
        for name, (candidate, _widget) in self._sections.items():
            candidate.setChecked(name == key)

        def scroll_to() -> None:
            if not widget.isVisibleTo(self._scroll):
                return
            y = widget.mapTo(self._scroll.widget(), QPoint(0, 0)).y()
            self._scroll.verticalScrollBar().setValue(max(0, y - 6))

        QTimer.singleShot(0, scroll_to)

    def set_available(self, key: str, enabled: bool) -> None:
        button, _widget = self._sections[key]
        button.setEnabled(enabled)
        if not enabled and self._active == key:
            self.navigate("source")

    def set_ready(self, key: str, ready: bool) -> None:
        button, _widget = self._sections[key]
        state = "ready" if ready else "pending"
        if button.property("state") == state:
            return
        button.setProperty("state", state)
        button.style().unpolish(button)
        button.style().polish(button)

    @property
    def buttons(self) -> dict[str, QPushButton]:
        return {key: value[0] for key, value in self._sections.items()}
