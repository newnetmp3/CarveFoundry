"""Reusable nonmodal-safe action forms shared by command mixins."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

class _ActionForm(QDialog):
    """Compact reusable form dialog for ribbon actions."""

    def __init__(self, parent, title: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(430)
        self.setSizeGripEnabled(True)

        self._form = QFormLayout()
        self._form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self._form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.DontWrapRows
        )
        self._form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._form.setHorizontalSpacing(14)
        self._form.setVerticalSpacing(8)
        self._fields: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(12)
        layout.addLayout(self._form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_line(self, key: str, label: str, value: str = "") -> QLineEdit:
        widget = QLineEdit(value)
        self._fields[key] = widget
        self._form.addRow(label, widget)
        return widget

    def add_double(
        self,
        key: str,
        label: str,
        value: float,
        *,
        minimum: float = -100000.0,
        maximum: float = 100000.0,
        decimals: int = 3,
        step: float = 1.0,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setSingleStep(step)
        widget.setValue(float(value))
        widget.setSuffix(suffix)
        self._fields[key] = widget
        self._form.addRow(label, widget)
        return widget

    def add_int(
        self,
        key: str,
        label: str,
        value: int,
        *,
        minimum: int = 0,
        maximum: int = 1_000_000,
    ) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(int(value))
        self._fields[key] = widget
        self._form.addRow(label, widget)
        return widget

    def add_check(
        self,
        key: str,
        label: str,
        checked: bool,
    ) -> QCheckBox:
        widget = QCheckBox()
        widget.setChecked(bool(checked))
        self._fields[key] = widget
        self._form.addRow(label, widget)
        return widget

    def add_combo(
        self,
        key: str,
        label: str,
        values: list[str],
        current: str,
        *,
        editable: bool = False,
    ) -> QComboBox:
        widget = QComboBox()
        widget.addItems(values)
        widget.setEditable(editable)
        index = widget.findText(current)
        if index >= 0:
            widget.setCurrentIndex(index)
        elif editable:
            widget.setEditText(current)
        self._fields[key] = widget
        self._form.addRow(label, widget)
        return widget

    def value(self, key: str):
        widget = self._fields[key]
        if isinstance(widget, QLineEdit):
            return widget.text()
        if isinstance(widget, QDoubleSpinBox):
            return widget.value()
        if isinstance(widget, QSpinBox):
            return widget.value()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        raise TypeError(f"Unsupported form widget: {type(widget).__name__}")

