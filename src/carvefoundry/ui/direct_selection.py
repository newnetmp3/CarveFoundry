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

from carvefoundry.core.project import ProjectItem
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.vector_path import (
    VectorSegment,
    arc_sweep_degrees,
    close_path,
    insert_node,
    join_paths,
    move_cubic_control,
    move_node,
    node_world_points,
    open_path_at_node,
    remove_node,
    segment_world_controls,
    segment_world_point,
    set_segment,
    split_path_at_node,
    vector_path_in_world_xy,
    world_xy_to_local,
    world_xy_to_local_point,
)
from carvefoundry.core.vector_snapping import grid_snap_candidate, nearest_vector_snap


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
        target_control: tuple[int, int] | None = None,
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
        if target_world_xy is not None and target_control is not None:
            segment_index, handle = target_control
            controls = segment_world_controls(item, segment_index)
            if controls is not None:
                actual = controls[handle - 1]
                tx, ty, tz = item.transform.translation_mm
                item.transform.translation_mm = (
                    tx + target_world_xy[0] - actual[0],
                    ty + target_world_xy[1] - actual[1],
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
        if self._settings.value("vector/grid_snap_enabled", False, type=bool):
            spacing = float(self._settings.value("vector/grid_spacing_mm", 5.0))
            grid = grid_snap_candidate(xy, spacing, tolerance)
            if grid is not None and (
                candidate is None or grid.distance_to(xy) < candidate.distance_to(xy)
            ):
                candidate = grid
        if candidate is None:
            return xy, None
        return candidate.point_xy, candidate.kind

    def _control_drag_finished(
        self, item_index: int, segment_index: int, handle: int,
        x_mm: float, y_mm: float,
    ) -> None:
        if not 0 <= item_index < len(self.project.items):
            return
        item = self.project.items[item_index]
        if item.locked or item.vector_path is None:
            return
        try:
            local = world_xy_to_local_point(item, (x_mm, y_mm))
            edited = move_cubic_control(
                item.vector_path, segment_index, handle, local,
            )
            if edited == item.vector_path:
                return
        except (ValueError, IndexError) as exc:
            self.statusBar().showMessage(f"Bezier handle drag rejected: {exc}", 7500)
            return
        self._commit_vector_path(
            item.item_id, edited, label="drag Bezier handle",
            target_world_xy=(x_mm, y_mm),
            target_control=(segment_index, handle),
        )

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

    @staticmethod
    def _copy_transform(transform) -> Transform3D:
        return Transform3D(
            translation_mm=tuple(transform.translation_mm),
            rotation_deg=tuple(transform.rotation_deg),
            scale_xyz=tuple(transform.scale_xyz),
        )

    @staticmethod
    def _preserve_anchor_world(
        item: ProjectItem,
        node_index: int,
        target_xy: tuple[float, float],
    ) -> None:
        actual = node_world_points(item)[node_index]
        tx, ty, tz = item.transform.translation_mm
        item.transform.translation_mm = (
            tx + target_xy[0] - float(actual[0]),
            ty + target_xy[1] - float(actual[1]),
            tz,
        )

    def _retarget_cam_sources_after_split(
        self,
        original_item_id: str,
        new_item_id: str,
    ) -> None:
        for operation in self.project.cam_operations:
            if original_item_id not in operation.source_item_ids:
                continue
            updated: list[str] = []
            for source_id in operation.source_item_ids:
                updated.append(source_id)
                if source_id == original_item_id:
                    updated.append(new_item_id)
            operation.source_item_ids = tuple(dict.fromkeys(updated))

    def _retarget_cam_sources_after_join(
        self,
        retained_item_id: str,
        removed_item_id: str,
    ) -> None:
        for operation in self.project.cam_operations:
            if removed_item_id not in operation.source_item_ids:
                continue
            updated = [
                retained_item_id if source_id == removed_item_id else source_id
                for source_id in operation.source_item_ids
            ]
            operation.source_item_ids = tuple(dict.fromkeys(updated))

    def _split_selected_vector_path(self, node_index: int) -> bool:
        item = self._editable_vector_item()
        if item is None or item.vector_path is None:
            return False
        try:
            left, right = split_path_at_node(item.vector_path, node_index)
        except (ValueError, IndexError) as exc:
            self.statusBar().showMessage(f"Vector split rejected: {exc}", 6500)
            return False

        item_index = next(
            (
                index
                for index, candidate in enumerate(self.project.items)
                if candidate.item_id == item.item_id
            ),
            None,
        )
        if item_index is None:
            return False
        target = node_world_points(item)[node_index]
        target_xy = (float(target[0]), float(target[1]))
        original_transform = self._copy_transform(item.transform)

        self._before_ribbon_mutation("split vector path")
        item.vector_path = left
        item.mesh = left.mesh_asset()
        item.source_path = None
        self._preserve_anchor_world(
            item,
            len(left.points_xy) - 1,
            target_xy,
        )

        new_item = ProjectItem(
            name=self._unique_item_name(f"{item.name} split"),
            source_path=None,
            kind=item.kind,
            visible=item.visible,
            locked=False,
            mesh=right.mesh_asset(),
            transform=original_transform,
            source_units=item.source_units,
            group_id=item.group_id,
            vector_path=right,
        )
        self._preserve_anchor_world(new_item, 0, target_xy)
        self.project.items.insert(item_index + 1, new_item)
        self._retarget_cam_sources_after_split(item.item_id, new_item.item_id)

        self._refresh_project_list(item_index + 1)
        self._after_ribbon_mutation("split vector path", True)
        self.viewport.update()
        self._refresh_vector_node_inspector()
        self.statusBar().showMessage(
            f"Split {item.name} into two editable vector paths.", 5000
        )
        return True

    def _join_selected_vector_paths(self) -> bool:
        indices = self._selected_design_indices()
        if len(indices) != 2:
            self.statusBar().showMessage(
                "Select exactly two open editable vector paths to join.", 5000
            )
            return False
        items = [self.project.items[index] for index in indices]
        if any(
            item.locked or item.vector_path is None or item.mesh is None
            for item in items
        ):
            self.statusBar().showMessage(
                "Both selected paths must be unlocked editable vectors.", 5500
            )
            return False
        if any(item.vector_path.closed for item in items):
            self.statusBar().showMessage(
                "Open closed contours before joining them.", 5000
            )
            return False
        if abs(
            float(items[0].transform.translation_mm[2])
            - float(items[1].transform.translation_mm[2])
        ) > 1e-7:
            self.statusBar().showMessage(
                "Joined vector paths must share the same Z position.", 5500
            )
            return False

        try:
            world_paths = [
                vector_path_in_world_xy(item)
                for item in items
            ]
        except ValueError as exc:
            self.statusBar().showMessage(f"Vector join rejected: {exc}", 7000)
            return False

        endpoints = []
        for endpoint_a, point_a in (
            ("start", world_paths[0].points_xy[0]),
            ("end", world_paths[0].points_xy[-1]),
        ):
            for endpoint_b, point_b in (
                ("start", world_paths[1].points_xy[0]),
                ("end", world_paths[1].points_xy[-1]),
            ):
                distance = (
                    (point_a[0] - point_b[0]) ** 2
                    + (point_a[1] - point_b[1]) ** 2
                ) ** 0.5
                endpoints.append((distance, endpoint_a, endpoint_b))
        distance, endpoint_a, endpoint_b = min(endpoints)
        tolerance = float(
            self._settings.value("vector/snap_tolerance_mm", 1.0)
        )
        try:
            joined = join_paths(
                world_paths[0],
                world_paths[1],
                first_endpoint=endpoint_a,
                second_endpoint=endpoint_b,
                max_gap_mm=tolerance,
            )
        except ValueError as exc:
            self.statusBar().showMessage(f"Vector join rejected: {exc}", 7000)
            return False

        primary = self._selected_item()
        retained_index = (
            indices[0]
            if primary is None
            else next(
                (
                    index
                    for index in indices
                    if self.project.items[index].item_id == primary.item_id
                ),
                indices[0],
            )
        )
        removed_index = indices[1] if retained_index == indices[0] else indices[0]
        retained = self.project.items[retained_index]
        removed = self.project.items[removed_index]
        retained_id = retained.item_id
        removed_id = removed.item_id
        retained_z = float(retained.transform.translation_mm[2])

        self._before_ribbon_mutation("join vector paths")
        retained.vector_path = joined
        retained.mesh = joined.mesh_asset()
        retained.source_path = None
        retained.kind = (
            retained.kind if retained.kind == removed.kind else "pen"
        )
        retained.transform = Transform3D(
            translation_mm=(0.0, 0.0, retained_z)
        )
        retained.group_id = (
            retained.group_id
            if retained.group_id == removed.group_id
            else None
        )
        self._retarget_cam_sources_after_join(retained_id, removed_id)
        self.project.items.pop(removed_index)

        final_index = retained_index - (1 if removed_index < retained_index else 0)
        self._refresh_project_list(final_index + 1)
        self._after_ribbon_mutation("join vector paths", True)
        self.viewport.update()
        self._refresh_vector_node_inspector()
        self.statusBar().showMessage(
            f"Joined vector paths ({distance:.3f} mm endpoint gap).", 5000
        )
        return True

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

        topology_heading = QLabel("Path topology", dialog)
        topology_heading.setObjectName("SectionHeading")
        layout.addWidget(topology_heading)
        topology_actions = QHBoxLayout()
        open_close = QPushButton("Close Path", dialog)
        open_close.setObjectName("VectorOpenClosePath")
        split_path = QPushButton("Split at Node", dialog)
        split_path.setObjectName("VectorSplitPath")
        join_paths_button = QPushButton("Join 2 Selected", dialog)
        join_paths_button.setObjectName("VectorJoinPaths")
        topology_actions.addWidget(open_close)
        topology_actions.addWidget(split_path)
        topology_actions.addWidget(join_paths_button)
        layout.addLayout(topology_actions)

        def current():
            selected = self._editable_vector_item()
            index = table.currentRow()
            if selected is None or selected.vector_path is None:
                return None, -1
            if not 0 <= index < len(selected.vector_path.points_xy):
                return None, -1
            return selected, index

        def refresh_topology_actions():
            selected, index = current()
            path = selected.vector_path if selected is not None else None
            if path is None:
                open_close.setEnabled(False)
                split_path.setEnabled(False)
            else:
                open_close.setText(
                    "Open at Node" if path.closed else "Close Path"
                )
                open_close.setEnabled(path.closed or len(path.points_xy) >= 3)
                split_path.setEnabled(
                    not path.closed
                    and 0 < index < len(path.points_xy) - 1
                )
            selected_indices = self._selected_design_indices()
            join_paths_button.setEnabled(
                len(selected_indices) == 2
                and all(
                    0 <= item_index < len(self.project.items)
                    and not self.project.items[item_index].locked
                    and self.project.items[item_index].vector_path is not None
                    and not self.project.items[item_index].vector_path.closed
                    for item_index in selected_indices
                )
            )

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
            refresh_topology_actions()

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

        def toggle_open_closed():
            selected, index = current()
            if selected is None or selected.vector_path is None:
                return
            anchor = node_world_points(selected)[index]
            target_xy = (float(anchor[0]), float(anchor[1]))
            try:
                if selected.vector_path.closed:
                    changed = open_path_at_node(selected.vector_path, index)
                    target_node = 0
                    label = "open vector path"
                else:
                    changed = close_path(selected.vector_path)
                    target_node = index
                    label = "close vector path"
            except (ValueError, IndexError) as exc:
                QMessageBox.warning(dialog, "Invalid vector topology", str(exc))
                return
            if self._commit_vector_path(
                selected.item_id,
                changed,
                label=label,
                target_node=target_node,
                target_world_xy=target_xy,
            ):
                table.setCurrentCell(target_node, 0)
                refresh_topology_actions()

        def split_selected():
            _selected, index = current()
            if self._split_selected_vector_path(index):
                self._refresh_vector_node_inspector()
                refresh_topology_actions()

        def join_selected():
            if self._join_selected_vector_paths():
                self._refresh_vector_node_inspector()
                table.setCurrentCell(0, 0)
                refresh_topology_actions()

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
        open_close.clicked.connect(toggle_open_closed)
        split_path.clicked.connect(split_selected)
        join_paths_button.clicked.connect(join_selected)
        move.clicked.connect(lambda: edit("move"))
        add.clicked.connect(lambda: edit("insert"))
        delete.clicked.connect(lambda: edit("delete"))

        footer = QLabel(
            "Retained paths support line, circular-arc and cubic Bezier segments. "
            "Open/close/split preserve analytic segments; Join uses the snap tolerance "
            "and requires planar paths with compatible stroke geometry. Imported and "
            "Boolean-result meshes are not silently converted."
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
