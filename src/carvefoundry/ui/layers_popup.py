"""Persistent, collapsible Layers section above the contextual Inspector.

The existing QListWidget remains the authoritative selection/rename model.
A compact delegate paints eye and padlock controls at the end of every row,
without per-row QWidget allocations or mouse-event interception on Wayland.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .layout_widgets import InspectorSection


class LayerControlsDelegate(QStyledItemDelegate):
    """Draw actual clickable eye and lock controls after the editable name."""

    def __init__(
        self, parent: QListWidget,
        *,
        visible_at: Callable[[int], bool],
        locked_at: Callable[[int], bool],
        toggle_visibility: Callable[[int], None],
        toggle_lock: Callable[[int], None],
    ) -> None:
        super().__init__(parent)
        self._visible_at = visible_at
        self._locked_at = locked_at
        self._toggle_visibility = toggle_visibility
        self._toggle_lock = toggle_lock

    @staticmethod
    def _hit(rect, x: int) -> str | None:
        if rect.right() - 61 <= x <= rect.right() - 34:
            return "eye"
        if rect.right() - 30 <= x <= rect.right() - 3:
            return "lock"
        return None

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        row = index.row() - 1  # Stock has no eye/lock controls.
        if row < 0:
            super().paint(painter, option, index)
            return

        text_option = QStyleOptionViewItem(option)
        text_option.rect = option.rect.adjusted(0, 0, -65, 0)
        super().paint(painter, text_option, index)
        selected = bool(option.state & option.state.State_Selected)
        if selected:
            painter.fillRect(
                option.rect.adjusted(option.rect.width() - 65, 0, 0, 0),
                option.palette.highlight(),
            )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ink = (
            option.palette.highlightedText().color()
            if selected else option.palette.text().color()
        )
        muted = QColor(ink)
        muted.setAlpha(95)
        center_y = option.rect.center().y()
        eye_x = option.rect.right() - 48
        lock_x = option.rect.right() - 16
        painter.setPen(QPen(ink if self._visible_at(row) else muted, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPoint(eye_x, center_y), 8, 5)
        if self._visible_at(row):
            painter.setBrush(ink)
            painter.drawEllipse(QPoint(eye_x, center_y), 2, 2)
        else:
            painter.drawLine(eye_x - 10, center_y + 7, eye_x + 10, center_y - 7)

        painter.setPen(QPen(ink if self._locked_at(row) else muted, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(lock_x - 6, center_y - 1, 12, 9, 1.5, 1.5)
        shackle_x = lock_x if self._locked_at(row) else lock_x + 4
        painter.drawArc(shackle_x - 4, center_y - 9, 8, 12, 0, 180 * 16)
        painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:
        if index.row() > 0 and event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                target = self._hit(option.rect, int(event.position().x()))
                if target == "eye":
                    self._toggle_visibility(index.row() - 1)
                    return True
                if target == "lock":
                    self._toggle_lock(index.row() - 1)
                    return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index) -> bool:
        if index.row() > 0:
            target = self._hit(option.rect, int(event.pos().x()))
            if target:
                row = index.row() - 1
                message = (
                    "Hide layer" if self._visible_at(row) else "Show layer"
                ) if target == "eye" else (
                    "Unlock layer for editing" if self._locked_at(row)
                    else "Lock layer against editing"
                )
                QToolTip.showText(event.globalPos(), message, view)
                return True
        return super().helpEvent(event, view, option, index)


class LayersPopup(QFrame):
    """Docked Layers section (legacy name retained for command compatibility)."""

    def __init__(
        self,
        parent: QWidget,
        *,
        move_up: Callable[[], None],
        move_down: Callable[[], None],
        duplicate: Callable[[], None],
        delete: Callable[[], None],
        visible_at: Callable[[int], bool],
        locked_at: Callable[[int], bool],
        toggle_visibility: Callable[[int], None],
        toggle_lock: Callable[[int], None],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("LayersPanel")
        self.setMinimumWidth(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.section = InspectorSection(
            "Layers", key="layers", settings=parent._settings,
            expanded=True, parent=self,
        )
        layout.addWidget(self.section)
        heading = QHBoxLayout()
        self.count_label = QLabel("0 objects")
        self.count_label.setObjectName("Muted")
        heading.addWidget(self.count_label)
        heading.addStretch(1)
        self.section.content_layout.addLayout(heading)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("LayersList")
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.list_widget.setMinimumHeight(85)
        self.list_widget.setMaximumHeight(280)
        self.list_widget.setItemDelegate(
            LayerControlsDelegate(
                self.list_widget, visible_at=visible_at, locked_at=locked_at,
                toggle_visibility=toggle_visibility, toggle_lock=toggle_lock,
            )
        )
        self.section.content_layout.addWidget(self.list_widget)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        self.action_buttons: dict[str, QPushButton] = {}
        for key, title, callback in (
            ("move_up", "Up", move_up),
            ("move_down", "Down", move_down),
            ("duplicate", "Copy", duplicate),
            ("delete", "Delete", delete),
        ):
            button = QPushButton(title)
            button.setMinimumWidth(0)
            button.clicked.connect(lambda _checked=False, fn=callback: fn())
            self.action_buttons[key] = button
            buttons.addWidget(button)
        self.section.content_layout.addLayout(buttons)

    def set_object_count(self, count: int) -> None:
        self.count_label.setText(f"{count} {'object' if count == 1 else 'objects'}")

    def show_below(self, _anchor: QWidget | None = None) -> None:
        """Old menu/toolbar Layers commands now focus the docked section."""
        self.section.setExpanded(True)
        self.show()
        self.list_widget.setFocus(Qt.FocusReason.OtherFocusReason)
