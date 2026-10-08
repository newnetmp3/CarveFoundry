"""Direct-selection inspector for retained pen knots, with real CAM geometry edits."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from carvefoundry.core.vector_path import (
    VectorSegment,
    arc_sweep_degrees,
    insert_node,
    move_node,
    node_world_points,
    remove_node,
    segment_world_controls,
    segment_world_point,
    set_segment,
    world_xy_to_local,
    world_xy_to_local_point,
)
from carvefoundry.core.vector_snapping import nearest_vector_snap


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
        return (
            item if item.visible and not item.locked
            and item.vector_path is not None else None
        )

    def _set_direct_selection(self, enabled: bool) -> None:
        if enabled and self._editable_vector_item() is None:
            action = self._ui_actions.get("direct_select")
            if action is not None:
                action.setChecked(False)
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

    def _node_edit_mode_changed(self, enabled: bool) -> None:
        action = self._ui_actions.get("direct_select")
        if action is not None:
            action.setChecked(enabled)
        if not enabled:
            dialog = getattr(self, "_vector_node_dialog", None)
            if dialog is not None:
                self._vector_node_dialog = None
                self._vector_nodes_table = None
                dialog.close()


    def _commit_vector_path(
        self, item_id: str, path, *, label: str,
        target_node: int | None = None,
        target_world_xy: tuple[float, float] | None = None,
    ) -> bool:
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
        if item.locked:
            self.statusBar().showMessage("Unlock the layer before editing nodes", 3500)
            return False
        try:
            mesh = path.mesh_asset()
        except (ValueError, IndexError) as exc:
            self.statusBar().showMessage(f"Invalid vector edit: {exc}", 8000)
            return False
        self._before_ribbon_mutation(label)
        item.mesh = mesh
        item.source_path = None
        item.vector_path = path
        # Transform3D pivots about the *mesh bounds centre*. Editing a node
        # may change that centre, so preserve the cursor's exact world XY.
        if target_world_xy is not None and target_node is not None:
            actual = node_world_points(item)[target_node]
            tx, ty, tz = item.transform.translation_mm
            item.transform.translation_mm = (
                tx + target_world_xy[0] - float(actual[0]),
                ty + target_world_xy[1] - float(actual[1]),
                tz,
            )
        self._after_ribbon_mutation(label, True)
        self.viewport.update()
        self._refresh_vector_node_inspector()
        self.statusBar().showMessage(
            f"{item.name}: updated {len(path.points_xy)} vector nodes. "
            "Toolpaths must be regenerated.",
            6000,
        )
        return True

    def _snap_vector_world_xy(
        self,
        item_id: str,
        node_index: int,
        xy: tuple[float, float],
    ) -> tuple[tuple[float, float], str | None]:
        enabled = self._settings.value("vector/snap_enabled", True, type=bool)
        if not enabled:
            return xy, None
        tolerance = float(self._settings.value("vector/snap_tolerance_mm", 1.0))
        candidate = nearest_vector_snap(
            self.project.items,
            xy,
            tolerance,
            exclude_item_id=item_id,
            exclude_node_index=node_index,
        )
        if candidate is None:
            return xy, None
        return candidate.point_xy, candidate.kind

    def _node_drag_finished(
        self, item_index: int, node_index: int, x_mm: float, y_mm: float,
    ) -> None:
        if not 0 <= item_index < len(self.project.items):
            return
        item = self.project.items[item_index]
        if item.vector_path is None:
            return
        snapped_xy, snap_kind = self._snap_vector_world_xy(
            item.item_id,
            node_index,
            (x_mm, y_mm),
        )
        x_mm, y_mm = snapped_xy
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
        changed = self._commit_vector_path(
            item.item_id, new, label="drag vector node",
            target_node=node_index, target_world_xy=(x_mm, y_mm),
        )
        if changed and snap_kind is not None:
            self.statusBar().showMessage(
                f"Vector node snapped to {snap_kind}. Toolpaths must be regenerated.",
                5000,
            )

    def _refresh_vector_node_inspector(self) -> None:
        dialog = getattr(self, "_vector_node_dialog", None)
        table = getattr(self, "_vector_nodes_table", None)
        item = self._editable_vector_item()
        if dialog is None or table is None or item is None:
            return
        selected_row = table.currentRow()
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
        if table.rowCount():
            table.setCurrentCell(
                min(max(selected_row, 0), table.rowCount() - 1),
                0,
            )

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

        snap_row = QHBoxLayout()
        snap_enabled = QCheckBox("Snap to vector geometry", dialog)
        snap_enabled.setObjectName("VectorSnapEnabled")
        snap_enabled.setChecked(
            self._settings.value("vector/snap_enabled", True, type=bool)
        )
        snap_tolerance = QDoubleSpinBox(dialog)
        snap_tolerance.setObjectName("VectorSnapTolerance")
        snap_tolerance.setRange(0.01, 50.0)
        snap_tolerance.setDecimals(2)
        snap_tolerance.setSuffix(" mm")
        snap_tolerance.setValue(
            float(self._settings.value("vector/snap_tolerance_mm", 1.0))
        )
        snap_tolerance.setToolTip(
            "Maximum distance for node, midpoint, arc-center and intersection snaps."
        )
        snap_row.addWidget(snap_enabled)
        snap_row.addWidget(QLabel("Tolerance:", dialog))
        snap_row.addWidget(snap_tolerance)
        layout.addLayout(snap_row)

        segment_heading = QLabel("Segment after selected node", dialog)
        segment_heading.setObjectName("SectionHeading")
        layout.addWidget(segment_heading)
        segment_form = QFormLayout()
        segment_kind = QComboBox(dialog)
        segment_kind.setObjectName("VectorSegmentKind")
        segment_kind.addItem("Line", "line")
        segment_kind.addItem("Circular Arc", "arc")
        segment_kind.addItem("Cubic Bezier", "cubic")
        segment_form.addRow("Type", segment_kind)

        arc_sweep = QDoubleSpinBox(dialog)
        arc_sweep.setObjectName("VectorArcSweep")
        arc_sweep.setRange(-359.0, 359.0)
        arc_sweep.setDecimals(1)
        arc_sweep.setSingleStep(5.0)
        arc_sweep.setSuffix(" deg")
        arc_sweep.setValue(90.0)
        segment_form.addRow("Arc sweep", arc_sweep)

        control_spins = tuple(QDoubleSpinBox(dialog) for _ in range(4))
        for spin in control_spins:
            spin.setRange(-1_000_000, 1_000_000)
            spin.setDecimals(3)
            spin.setSuffix(" mm")
        segment_form.addRow("Control 1 X", control_spins[0])
        segment_form.addRow("Control 1 Y", control_spins[1])
        segment_form.addRow("Control 2 X", control_spins[2])
        segment_form.addRow("Control 2 Y", control_spins[3])
        layout.addLayout(segment_form)
        apply_segment = QPushButton("Apply Segment", dialog)
        apply_segment.setObjectName("VectorApplySegment")
        layout.addWidget(apply_segment)

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

        def refresh_segment_fields():
            selected, index = current()
            path = selected.vector_path if selected is not None else None
            has_segment = bool(path is not None and index < path.segment_count)
            segment_kind.setEnabled(has_segment)
            apply_segment.setEnabled(has_segment)
            if not has_segment:
                arc_sweep.setEnabled(False)
                for spin in control_spins:
                    spin.setEnabled(False)
                return

            segment = path.resolved_segments()[index]
            segment_kind.setCurrentIndex(
                max(0, segment_kind.findData(segment.kind))
            )
            sweep = arc_sweep_degrees(path, index)
            if sweep is not None:
                arc_sweep.setValue(sweep)

            controls = segment_world_controls(selected, index)
            if controls is None:
                start = segment_world_point(selected, index, 0.0)
                end = segment_world_point(selected, index, 1.0)
                controls = (
                    (
                        start[0] + (end[0] - start[0]) / 3.0,
                        start[1] + (end[1] - start[1]) / 3.0,
                    ),
                    (
                        start[0] + 2.0 * (end[0] - start[0]) / 3.0,
                        start[1] + 2.0 * (end[1] - start[1]) / 3.0,
                    ),
                )
            values = (
                controls[0][0], controls[0][1],
                controls[1][0], controls[1][1],
            )
            for spin, value in zip(control_spins, values, strict=True):
                spin.setValue(float(value))

            kind = str(segment_kind.currentData())
            arc_sweep.setEnabled(kind == "arc")
            for spin in control_spins:
                spin.setEnabled(kind == "cubic")

        def row_changed():
            selected, index = current()
            if selected is None:
                return
            point = node_world_points(selected)[index]
            x.setValue(float(point[0]))
            y.setValue(float(point[1]))
            refresh_segment_fields()

        def segment_kind_changed():
            kind = str(segment_kind.currentData())
            arc_sweep.setEnabled(kind == "arc" and apply_segment.isEnabled())
            for spin in control_spins:
                spin.setEnabled(kind == "cubic" and apply_segment.isEnabled())

        def apply_selected_segment():
            selected, index = current()
            if selected is None or selected.vector_path is None:
                return
            if index >= selected.vector_path.segment_count:
                return
            try:
                kind = str(segment_kind.currentData())
                if kind == "line":
                    segment = VectorSegment.line()
                elif kind == "arc":
                    segment = VectorSegment.arc(arc_sweep.value())
                else:
                    c1 = world_xy_to_local_point(
                        selected,
                        (control_spins[0].value(), control_spins[1].value()),
                    )
                    c2 = world_xy_to_local_point(
                        selected,
                        (control_spins[2].value(), control_spins[3].value()),
                    )
                    segment = VectorSegment.cubic(c1, c2)
                changed = set_segment(selected.vector_path, index, segment)
                anchor = segment_world_point(selected, index, 0.0)
            except (ValueError, IndexError) as exc:
                QMessageBox.warning(dialog, "Invalid vector segment", str(exc))
                return
            self._commit_vector_path(
                selected.item_id,
                changed,
                label="edit vector segment",
                target_node=index,
                target_world_xy=anchor,
            )
            refresh_segment_fields()

        def edit(kind: str):
            selected, index = current()
            if selected is None:
                return
            try:
                path = selected.vector_path
                if kind == "move":
                    target_xy, _snap_kind = self._snap_vector_world_xy(
                        selected.item_id,
                        index,
                        (x.value(), y.value()),
                    )
                    x.setValue(target_xy[0])
                    y.setValue(target_xy[1])
                    local = world_xy_to_local(
                        selected, index, target_xy,
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
                target_node=index if kind == "move" else None,
                target_world_xy=(
                    (x.value(), y.value()) if kind == "move" else None
                ),
            )
            table.setCurrentCell(
                min(index, table.rowCount() - 1), 0,
            )

        table.currentCellChanged.connect(
            lambda *_args: row_changed(),
        )
        snap_enabled.toggled.connect(
            lambda enabled: self._settings.setValue("vector/snap_enabled", enabled)
        )
        snap_tolerance.valueChanged.connect(
            lambda value: self._settings.setValue("vector/snap_tolerance_mm", value)
        )
        segment_kind.currentIndexChanged.connect(
            lambda _index: segment_kind_changed()
        )
        apply_segment.clicked.connect(apply_selected_segment)
        move.clicked.connect(lambda: edit("move"))
        add.clicked.connect(lambda: edit("insert"))
        delete.clicked.connect(lambda: edit("delete"))

        footer = QLabel(
            "Retained paths support line, circular-arc and cubic Bezier segments. "
            "Imported and Boolean-result meshes are not silently converted. "
            "On a 3D-tilted path, reset X/Y tilt before editing XY geometry."
        )
        footer.setWordWrap(True)
        layout.addWidget(footer)

        def closed():
            if getattr(self, "_vector_node_dialog", None) is dialog:
                self._vector_node_dialog = None
                self._vector_nodes_table = None
                # Qt can destroy the native QOpenGLWindow before emitting
                # WA_DeleteOnClose for this modeless dialog during app exit.
                # Do not call into already-destroyed C++ widgets.
                try:
                    self.viewport.set_node_edit_mode(False)
                    action = self._ui_actions.get("direct_select")
                    if action is not None:
                        action.setChecked(False)
                except RuntimeError:
                    pass

        dialog.destroyed.connect(closed)
        self._vector_node_dialog = dialog
        self._vector_nodes_table = table
        self._refresh_vector_node_inspector()
        table.setCurrentCell(0, 0)
        dialog.show()
