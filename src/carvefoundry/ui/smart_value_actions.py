"""Smart Value editing and object-binding actions."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from carvefoundry.core.project import ProjectItem
from carvefoundry.core.smart_values import SmartValueError, SmartValues

from .ribbon_forms import _ActionForm


class SmartValueActionsMixin:
    """Edit reusable project expressions and bind them to object transforms."""

    # ------------------------------------------------------------------
    # Project automation / Easel-style workflows
    # ------------------------------------------------------------------
    def _smart_value_context(self) -> dict[str, float]:
        stock = self.project.stock
        return {
            "stock_width": float(stock.width_mm),
            "stock_height": float(stock.height_mm),
            "stock_thickness": float(stock.thickness_mm),
            "stock_center_x": float(stock.width_mm) / 2.0,
            "stock_center_y": float(stock.height_mm) / 2.0,
        }

    def _resolve_item_smart_bindings(
        self,
        item: ProjectItem,
        *,
        values: SmartValues | None = None,
    ) -> dict[str, float]:
        table = values or self.project.smart_values
        context = self._smart_value_context()
        resolved = {
            key: table.evaluate(expression, extra_values=context)
            for key, expression in item.smart_bindings.items()
            if expression.strip()
        }
        for key in ("size_x", "size_y", "size_z"):
            if key in resolved and resolved[key] <= 0:
                raise SmartValueError(
                    f"{item.name}: {key.replace('_', ' ')} must be greater than zero."
                )
        return resolved

    @staticmethod
    def _apply_resolved_smart_bindings(
        item: ProjectItem,
        resolved: dict[str, float],
    ) -> None:
        if item.locked:
            return
        tx, ty, tz = item.transform.translation_mm
        item.transform.translation_mm = (
            resolved.get("position_x", tx),
            resolved.get("position_y", ty),
            resolved.get("position_z", tz),
        )

        size = item.local_size_mm()
        if size is None:
            return
        scale = list(item.transform.scale_xyz)
        for axis, key in enumerate(("size_x", "size_y", "size_z")):
            target = resolved.get(key)
            if target is None:
                continue
            current = float(size[axis])
            if current <= 1.0e-12:
                raise SmartValueError(
                    f"{item.name}: cannot bind {key.replace('_', ' ')} "
                    "because the current model dimension is zero."
                )
            scale[axis] *= target / current
        item.transform.scale_xyz = tuple(float(value) for value in scale)

    def _smart_values_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Smart Values")
        dialog.resize(620, 460)
        layout = QVBoxLayout(dialog)

        intro = QLabel(
            "Define one reusable value per line as name = expression. "
            "Values may reference each other, for example:\n"
            "width = 120\nborder = 6\ninside = width - 2 * border"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        editor = QPlainTextEdit()
        editor.setPlainText(self.project.smart_values.to_lines())
        editor.setPlaceholderText("width = 120\nheight = width / 2\nborder = 6")
        layout.addWidget(editor, 1)

        note = QLabel(
            "Object bindings may also use stock_width, stock_height, "
            "stock_thickness, stock_center_x, and stock_center_y."
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                table = SmartValues.from_lines(editor.toPlainText())
                resolved = [
                    (item, self._resolve_item_smart_bindings(item, values=table))
                    for item in self.project.items
                    if item.smart_bindings and not item.locked
                ]
            except (SmartValueError, ZeroDivisionError) as exc:
                QMessageBox.warning(self, "Smart Values", str(exc))
                continue

            self._before_ribbon_mutation("edit Smart Values")
            self.project.smart_values = table
            for item, item_values in resolved:
                self._apply_resolved_smart_bindings(item, item_values)
            if resolved:
                self._refresh_project_list(self.project_list.currentRow())
                self.viewport.update()
                self._invalidate_toolpaths("Smart Values")
            self._after_ribbon_mutation("edit Smart Values", True)
            self.statusBar().showMessage(
                f"Saved {len(table.expressions)} Smart Value"
                f"{'s' if len(table.expressions) != 1 else ''}",
                3500,
            )
            return

    def _smart_bindings_dialog(self) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if indices and not self._selection_is_editable(indices):
            return
        if not indices:
            self.statusBar().showMessage(
                "Select one or more design objects to bind",
                4000,
            )
            return

        items = [self.project.items[index] for index in indices]
        keys = (
            ("position_x", "Position X"),
            ("position_y", "Position Y"),
            ("position_z", "Position Z"),
            ("size_x", "Size X"),
            ("size_y", "Size Y"),
            ("size_z", "Size Z"),
        )
        form = _ActionForm(self, "Smart Value Bindings")
        for key, label in keys:
            expressions = {
                item.smart_bindings.get(key, "")
                for item in items
            }
            initial = expressions.pop() if len(expressions) == 1 else ""
            field = form.add_line(key, label, initial)
            field.setPlaceholderText(
                "Smart Value or expression; blank leaves this property unbound"
            )

        if form.exec() != QDialog.DialogCode.Accepted:
            return

        bindings = {
            key: str(form.value(key)).strip()
            for key, _label in keys
            if str(form.value(key)).strip()
        }
        try:
            context = self._smart_value_context()
            resolved_template = {
                key: self.project.smart_values.evaluate(
                    expression,
                    extra_values=context,
                )
                for key, expression in bindings.items()
            }
            for key in ("size_x", "size_y", "size_z"):
                if key in resolved_template and resolved_template[key] <= 0:
                    raise SmartValueError(
                        f"{key.replace('_', ' ')} must be greater than zero."
                    )
            for item in items:
                size = item.local_size_mm()
                if size is None:
                    continue
                for axis, key in enumerate(("size_x", "size_y", "size_z")):
                    if (
                        key in resolved_template
                        and float(size[axis]) <= 1.0e-12
                    ):
                        raise SmartValueError(
                            f"{item.name}: cannot bind "
                            f"{key.replace('_', ' ')} because the current "
                            "model dimension is zero."
                        )
        except (SmartValueError, ZeroDivisionError) as exc:
            QMessageBox.warning(self, "Smart Value Bindings", str(exc))
            return

        self._before_ribbon_mutation("bind Smart Values")
        for item in items:
            item.smart_bindings = dict(bindings)
            resolved = self._resolve_item_smart_bindings(item)
            self._apply_resolved_smart_bindings(item, resolved)

        self._refresh_project_list(indices[-1] + 1)
        self._select_project_indices(indices, primary=indices[-1])
        self.viewport.update()
        self._invalidate_toolpaths("Smart Value bindings")
        self._after_ribbon_mutation("bind Smart Values", True)
        self.statusBar().showMessage(
            f"Updated Smart Value bindings for {len(items)} object"
            f"{'s' if len(items) != 1 else ''}",
            3500,
        )

