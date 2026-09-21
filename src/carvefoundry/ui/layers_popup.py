"""Compact, permanently embedded Inspector Layers section.

Keeps QListWidget's existing selection, rename, ordering, undo and project
synchronization while giving each design row an independent Eye and Lock hit
target. The stock row cannot be hidden or locked.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

LAYER_LOCK_ROLE = Qt.ItemDataRole.UserRole + 1


class LayerRowDelegate(QStyledItemDelegate):
    """Draw two accessible icon hit targets without replacing editable rows."""

    ICON_WIDTH = 26

    @classmethod
    def icon_rects(cls, row_rect: QRect) -> tuple[QRect, QRect]:
        right = row_rect.right() + 1
        return (
            QRect(right - 2 * cls.ICON_WIDTH, row_rect.top(),
                  cls.ICON_WIDTH, row_rect.height()),
            QRect(right - cls.ICON_WIDTH, row_rect.top(),
                  cls.ICON_WIDTH, row_rect.height()),
        )

    def initStyleOption(self, option: QStyleOptionViewItem, index) -> None:
        super().initStyleOption(option, index)
        if index.row() > 0:
            option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        if index.row() == 0:
            super().paint(painter, option, index)
            return

        # Default QListWidgetItem check indicators and our Eye must never
        # appear together. Preserve the Qt selection, focus, editing and
        # keyboard machinery; reserve a separate icon column on the right.
        adjusted = QStyleOptionViewItem(option)
        self.initStyleOption(adjusted, index)
        adjusted.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        eye, lock = self.icon_rects(option.rect)
        adjusted.rect = QRect(option.rect)
        adjusted.rect.setRight(eye.left() - 1)
        super().paint(painter, adjusted, index)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(eye, option.palette.highlight())
            painter.fillRect(lock, option.palette.highlight())
        self._draw_eye(
            painter, eye,
            Qt.CheckState(index.data(Qt.ItemDataRole.CheckStateRole))
            == Qt.CheckState.Checked,
        )
        self._draw_lock(painter, lock, bool(index.data(LAYER_LOCK_ROLE)))
        painter.restore()

    @staticmethod
    def _draw_eye(painter: QPainter, area: QRect, visible: bool) -> None:
        center = area.center()
        x, y = float(center.x()), float(center.y())
        color = "#c8ff3d" if visible else "#7c8497"
        painter.setPen(QPen(QColor(color), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        eye = QPainterPath(QPointF(x - 8, y))
        eye.cubicTo(x - 4, y - 6, x + 4, y - 6, x + 8, y)
        eye.cubicTo(x + 4, y + 6, x - 4, y + 6, x - 8, y)
        painter.drawPath(eye)
        if visible:
            painter.setBrush(QColor(color))
            painter.drawEllipse(QRectF(x - 2, y - 2, 4, 4))
        else:
            painter.drawLine(QPointF(x - 9, y + 7), QPointF(x + 9, y - 7))

    @staticmethod
    def _draw_lock(painter: QPainter, area: QRect, locked: bool) -> None:
        center = area.center()
        x, y = float(center.x()), float(center.y())
        color = "#c8ff3d" if locked else "#7c8497"
        painter.setPen(QPen(QColor(color), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        shackle = QPainterPath(QPointF(x - 4, y + 1))
        shackle.lineTo(x - 4, y - 4)
        shackle.cubicTo(x - 4, y - 10, x + 4, y - 10, x + 4, y - 4)
        if locked:
            shackle.lineTo(x + 4, y + 1)
        else:
            shackle.lineTo(x + 7, y - 1)
        painter.drawPath(shackle)
        painter.drawRoundedRect(QRectF(x - 7, y, 14, 9), 1.5, 1.5)

    def editorEvent(self, event, model, option, index) -> bool:
        if index.row() > 0 and hasattr(event, "position"):
            eye, lock = self.icon_rects(option.rect)
            pos = event.position().toPoint()
            over_eye = eye.contains(pos)
            over_lock = lock.contains(pos)
            if over_eye or over_lock:
                if (
                    event.type() == QEvent.Type.MouseButtonRelease
                    and event.button() == Qt.MouseButton.LeftButton
                ):
                    if over_eye:
                        old = index.data(Qt.ItemDataRole.CheckStateRole)
                        state = (
                            Qt.CheckState.Unchecked
                            if Qt.CheckState(old) == Qt.CheckState.Checked
                            else Qt.CheckState.Checked
                        )
                        model.setData(index, state, Qt.ItemDataRole.CheckStateRole)
                    else:
                        model.setData(
                            index, not bool(index.data(LAYER_LOCK_ROLE)),
                            LAYER_LOCK_ROLE,
                        )
                return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index) -> bool:
        if index.row() > 0:
            eye, lock = self.icon_rects(option.rect)
            if eye.contains(event.pos()):
                message = (
                    "Hide layer" if index.data(Qt.ItemDataRole.CheckStateRole)
                    == Qt.CheckState.Checked else "Show layer"
                )
            elif lock.contains(event.pos()):
                message = (
                    "Unlock layer" if bool(index.data(LAYER_LOCK_ROLE))
                    else "Lock layer (prevent editing)"
                )
            else:
                return super().helpEvent(event, view, option, index)
            QToolTip.showText(event.globalPos(), message, view)
            return True
        return super().helpEvent(event, view, option, index)


class LayersPanel(QFrame):
    """Inspector-top Layers section, always synchronized with the viewport."""

    def __init__(
        self,
        parent: QWidget,
        *,
        move_up: Callable[[], None],
        move_down: Callable[[], None],
        duplicate: Callable[[], None],
        delete: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("LayersPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 9)
        layout.setSpacing(5)

        heading_row = QHBoxLayout()
        heading = QLabel("Layers")
        heading.setObjectName("SectionHeading")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        self.count_label = QLabel("0 objects")
        self.count_label.setObjectName("Muted")
        heading_row.addWidget(self.count_label)
        layout.addLayout(heading_row)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("LayersList")
        self.list_widget.setItemDelegate(LayerRowDelegate(self.list_widget))
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.list_widget.setMinimumHeight(118)
        self.list_widget.setMaximumHeight(270)
        self.list_widget.setToolTip(
            "Click to select • Ctrl/Shift to select multiple • "
            "eye to show/hide • lock to protect a layer from editing"
        )
        layout.addWidget(self.list_widget)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        self.action_buttons: dict[str, QPushButton] = {}
        for key, title, callback in (
            ("move_up", "↑", move_up),
            ("move_down", "↓", move_down),
            ("duplicate", "Duplicate", duplicate),
            ("delete", "Delete", delete),
        ):
            button = QPushButton(title)
            button.setToolTip({
                "move_up": "Move selected layer up",
                "move_down": "Move selected layer down",
                "duplicate": "Duplicate selected layer",
                "delete": "Delete selected layer",
            }[key])
            button.clicked.connect(lambda _checked=False, fn=callback: fn())
            self.action_buttons[key] = button
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def set_object_count(self, count: int) -> None:
        label = "object" if count == 1 else "objects"
        self.count_label.setText(f"{count} {label}")


# Compatibility for existing imports and extensions.
LayersPopup = LayersPanel
