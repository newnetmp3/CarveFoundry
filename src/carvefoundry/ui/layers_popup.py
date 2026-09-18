from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LayersPopup(QFrame):
    """Compact on-demand object/layer manager anchored to the canvas toolbar."""

    def __init__(
        self,
        parent: QWidget,
        *,
        move_up: Callable[[], None],
        move_down: Callable[[], None],
        duplicate: Callable[[], None],
        delete: Callable[[], None],
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self.setObjectName("LayersPopup")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        heading_row = QHBoxLayout()
        heading = QLabel("Objects & Layers")
        heading.setObjectName("LayersPopupTitle")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        self.count_label = QLabel("0 objects")
        self.count_label.setObjectName("Muted")
        heading_row.addWidget(self.count_label)
        layout.addLayout(heading_row)

        hint = QLabel(
            "Click to select • Ctrl/Shift for multiple • checkbox controls visibility"
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("LayersList")
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.list_widget.setMinimumHeight(180)
        layout.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(5)
        self.action_buttons: dict[str, QPushButton] = {}
        for key, title, callback in (
            ("move_up", "Up", move_up),
            ("move_down", "Down", move_down),
            ("duplicate", "Duplicate", duplicate),
            ("delete", "Delete", delete),
        ):
            button = QPushButton(title)
            button.clicked.connect(lambda _checked=False, fn=callback: fn())
            self.action_buttons[key] = button
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def set_object_count(self, count: int) -> None:
        label = "object" if count == 1 else "objects"
        self.count_label.setText(f"{count} {label}")

    def show_below(self, anchor: QWidget) -> None:
        """Show below an anchor while keeping the popup inside the screen."""

        rows = max(1, self.list_widget.count())
        width = max(360, anchor.width() * 3)
        height = min(520, max(250, 150 + rows * 30))
        self.resize(width, height)

        position = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        screen = anchor.screen()
        if screen is not None:
            available = screen.availableGeometry()
            x = min(
                max(position.x(), available.left()),
                max(available.left(), available.right() - width + 1),
            )
            y = position.y()
            if y + height > available.bottom() + 1:
                y = anchor.mapToGlobal(QPoint(0, -height - 4)).y()
            y = max(available.top(), y)
            position = QPoint(x, y)

        self.move(position)
        self.show()
        self.raise_()
        self.list_widget.setFocus(Qt.FocusReason.PopupFocusReason)
