"""Direct-selection inspector for retained pen knots, with real CAM geometry edits."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from carvefoundry.core.vector_path import (
    insert_node,
    move_node,
    node_world_points,
    remove_node,
    world_xy_to_local,
)


class DirectSelectionMixin:
    """Select and drag actual pen knots or edit exact coordinates in the table."""

    def _editable_vector_item(self):
        index = self.viewport._renderer.selected_item_index
        if (
            index is None
            or not 0 <= index < len(self.project.items)
        ):
            return None
        item = self.project.items[index]
        return item if item.visible and item.vector_path is not None else None

    def _set_direct_selection(self, enabled: bool) -> None:
        if enabled and self._editable_vector_item() is None:
            self.statusBar().showMessage(
                "Select an editable Pen Stroke or Line to use Direct Selection. "
                "Imported STL and baked Boolean meshes have no retained knots.",
                8500,
            )
            return
        self._camera_tool_active = False
        if enabled:
            self.viewport.set_shape_draw_mode(None)
            self.viewport.set_camera_control_mode(False)
        self.viewport.set_node_edit_mode(enabled)
        action = self._ui_actions.get("direct_select")
        if action is not None:
            action.setChecked(enabled)
        if hasattr(self, "tool_rail"):
            self.tool_rail.set_active_tool("direct_select" if enabled else "select")
        if enabled:
            self._show_vector_node_inspector()
        else:
            dialog = getattr(self, "_vector_node_dialog", None)
            if dialog is not None:
                self._vector_node_dialog = None
                dialog.close()
        self.statusBar().showMessage(
            "Direct Selection: drag green nodes; edit exact XY in the inspector. "
            "Alt-drag orbits; Esc returns to Select."
            if enabled else "Returned to Select tool",
            6000,
        )

    def _activate_direct_selection(self) -> None:
        self._set_direct_selection(True)

    def _commit_vector_path(self, item_id: str, path, *, label: str) -> bool:
        indices = [
            index for index, item in enumerate(self.project.items)
            if item.item_id == item_id
        ]
        if len(indices) != 1:
            self.statusBar().showMessage(
                "Vector edit discarded: selected object changed.", 6000,
            )
            return False
        item = self.project.items[indices[0]]
        try:
            mesh = path.mesh_asset()
        except (ValueError, IndexError) as exc:
            self.statusBar().showMessage(f"Invalid vector edit: {exc}", 8000)
            return False
        self._before_ribbon_mutation(label)
        item.mesh = mesh
        item.vector_path = path
        self._after_ribbon_mutation(label, True)
        self.viewport.update()
        self._refresh_vector_node_inspector()
        self.statusBar().showMessage(
            f"{item.name}: updated {len(path.points_xy)} vector nodes. "
            "Toolpaths must be regenerated.",
            6000,
        )
        return True

    def _node_drag_finished(
        self, item_index: int, node_index: int, x_mm: float, y_mm: float,
    ) -> None:
        if not 0 <= item_index < len(self.project.items):
            return
        item = self.project.items[item_index]
        if item.vector_path is None:
            return
        try:
            local_xy = world_xy_to_local(
                item, node_index, (x_mm, y_mm),
            )
            new = move_node(item.vector_path, node_index, local_xy)
            if new == item.vector_path:
                return
        except (ValueError, IndexError) as exc:
            self.statusBar().showMessage(f"Vector drag rejected: {exc}", 7500)
            return
        self._commit_vector_path(item.item_id, new, label="drag vector node")

    def _refresh_vector_node_inspector(self) -> None:
        dialog = getattr(self, "_vector_node_dialog", None)
        table = getattr(self, "_vector_nodes_table", None)
        item = self._editable_vector_item()
        if dialog is None or table is None or item is None:
            return
        table.setRowCount(len(item.vector_path.points_xy))
        for index, point in enumerate(node_world_points(item)):
            values = (f"{index + 1}", f"{point[0]:.3f}", f"{point[1]:.3f}")
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                table.setItem(index, column, cell)

    def _show_vector_node_inspector(self) -> None:
        item = self._editable_vector_item()
        if item is None:
            return
        old = getattr(self, "_vector_node_dialog", None)
        if old is not None:
            self._refresh_vector_node_inspector()
            old.show()
            old.raise_()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Direct Selection — Editable Vector Nodes")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setMinimumSize(465, 390)
        layout = QVBoxLayout(dialog)
        instructions = QLabel(
            "Select and drag green knots in the viewport (top view makes "
            "placement easier), or select a row to edit exact stock XY. "
            "Inserted nodes split the chosen segment at its midpoint. "
            "This edits the actual CNC mesh and is Undo/Redo-able."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        table = QTableWidget(dialog)
        table.setObjectName("EditableVectorNodeTable")
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(("Node", "World X (mm)", "World Y (mm)"))
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows,
        )
        table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        layout.addWidget(table, 1)
        row = QHBoxLayout()
        x = QDoubleSpinBox(dialog)
        y = QDoubleSpinBox(dialog)
        for widget in (x, y):
            widget.setRange(-1_000_000, 1_000_000)
            widget.setDecimals(3)
            widget.setSuffix(" mm")
        row.addWidget(QLabel("X:", dialog))
        row.addWidget(x)
        row.addWidget(QLabel("Y:", dialog))
        row.addWidget(y)
        layout.addLayout(row)
        actions = QHBoxLayout()
        move = QPushButton("Move Node", dialog)
        add = QPushButton("Insert Midpoint After", dialog)
        delete = QPushButton("Delete Node", dialog)
        actions.addWidget(move)
        actions.addWidget(add)
        actions.addWidget(delete)
        layout.addLayout(actions)

        def current():
            selected = self._editable_vector_item()
            index = table.currentRow()
            if selected is None or selected.vector_path is None:
                return None, -1
            if not 0 <= index < len(selected.vector_path.points_xy):
                return None, -1
            return selected, index

        def row_changed():
            selected, index = current()
            if selected is None:
                return
            point = node_world_points(selected)[index]
            x.setValue(float(point[0]))
            y.setValue(float(point[1]))

        def edit(kind: str):
            selected, index = current()
            if selected is None:
                return
            try:
                path = selected.vector_path
                if kind == "move":
                    local = world_xy_to_local(
                        selected, index, (x.value(), y.value()),
                    )
                    changed = move_node(path, index, local)
                elif kind == "insert":
                    changed = insert_node(path, index)
                else:
                    changed = remove_node(path, index)
            except (ValueError, IndexError) as exc:
                QMessageBox.warning(dialog, "Invalid vector edit", str(exc))
                return
            self._commit_vector_path(
                selected.item_id, changed, label=f"{kind} vector node",
            )
            table.setCurrentCell(
                min(index, table.rowCount() - 1), 0,
            )

        table.currentCellChanged.connect(
            lambda *_args: row_changed(),
        )
        move.clicked.connect(lambda: edit("move"))
        add.clicked.connect(lambda: edit("insert"))
        delete.clicked.connect(lambda: edit("delete"))

        footer = QLabel(
            "Only newly drawn Pen Strokes and Lines retain nodes. Imported and "
            "Boolean-result meshes are not silently converted. "
            "On a 3D-tilted path, reset X/Y tilt before moving XY knots."
        )
        footer.setWordWrap(True)
        layout.addWidget(footer)

        def closed():
            if getattr(self, "_vector_node_dialog", None) is dialog:
                self._vector_node_dialog = None
                self._vector_nodes_table = None
                self.viewport.set_node_edit_mode(False)
                action = self._ui_actions.get("direct_select")
                if action is not None:
                    action.setChecked(False)

        dialog.destroyed.connect(closed)
        self._vector_node_dialog = dialog
        self._vector_nodes_table = table
        self._refresh_vector_node_inspector()
        table.setCurrentCell(0, 0)
        dialog.show()
