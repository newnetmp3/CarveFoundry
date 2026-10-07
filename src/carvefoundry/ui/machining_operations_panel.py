"""Persistent machining-operation stack UI and edit actions."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.cam.operation import CamOperation
from carvefoundry.cam import operation_plan
from carvefoundry.core.tools import Cutter

from .layout_widgets import InspectorSection


_OPERATION_ID_ROLE = Qt.ItemDataRole.UserRole + 27


class MachiningOperationsPanelMixin:
    """Expose the persistent CAM operation stack in the Inspector."""

    def _build_machining_operations_panel(self) -> QWidget:
        section = InspectorSection(
            "Machining Operations",
            key="machining_operations",
            settings=self._settings,
            expanded=True,
        )
        section.setObjectName("MachiningOperationsSection")

        intro = QLabel(
            "Saved machining intent. Reordering or editing an operation "
            "invalidates only the affected stage and the stages after it."
        )
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        section.content_layout.addWidget(intro)

        self.machining_operations_list = QListWidget(section)
        self.machining_operations_list.setObjectName("MachiningOperationsList")
        self.machining_operations_list.setMinimumHeight(150)
        self.machining_operations_list.setSelectionMode(
            QListWidget.SelectionMode.SingleSelection
        )
        self.machining_operations_list.currentRowChanged.connect(
            self._machining_operation_selection_changed
        )
        self.machining_operations_list.itemChanged.connect(
            self._machining_operation_item_changed
        )
        section.content_layout.addWidget(self.machining_operations_list)

        first_row = QHBoxLayout()
        first_row.setContentsMargins(0, 0, 0, 0)
        first_row.setSpacing(5)
        self.machining_operation_edit_button = QPushButton("Edit")
        self.machining_operation_edit_button.setObjectName(
            "MachiningOperationEdit"
        )
        self.machining_operation_edit_button.clicked.connect(
            self._edit_selected_machining_operation
        )
        first_row.addWidget(self.machining_operation_edit_button)

        self.machining_operation_recalculate_button = QPushButton("Recalculate")
        self.machining_operation_recalculate_button.setObjectName(
            "MachiningOperationRecalculate"
        )
        self.machining_operation_recalculate_button.clicked.connect(
            self._recalculate_selected_machining_operation
        )
        first_row.addWidget(self.machining_operation_recalculate_button)
        section.content_layout.addLayout(first_row)

        second_row = QHBoxLayout()
        second_row.setContentsMargins(0, 0, 0, 0)
        second_row.setSpacing(5)
        self.machining_operation_up_button = QPushButton("↑")
        self.machining_operation_up_button.setToolTip(
            "Move the selected operation earlier in the machining order."
        )
        self.machining_operation_up_button.clicked.connect(
            lambda: self._move_selected_machining_operation(-1)
        )
        second_row.addWidget(self.machining_operation_up_button)

        self.machining_operation_down_button = QPushButton("↓")
        self.machining_operation_down_button.setToolTip(
            "Move the selected operation later in the machining order."
        )
        self.machining_operation_down_button.clicked.connect(
            lambda: self._move_selected_machining_operation(1)
        )
        second_row.addWidget(self.machining_operation_down_button)

        self.machining_operation_duplicate_button = QPushButton("Duplicate")
        self.machining_operation_duplicate_button.clicked.connect(
            self._duplicate_selected_machining_operation
        )
        second_row.addWidget(self.machining_operation_duplicate_button)

        self.machining_operation_delete_button = QPushButton("Delete")
        self.machining_operation_delete_button.clicked.connect(
            self._delete_selected_machining_operation
        )
        second_row.addWidget(self.machining_operation_delete_button)
        section.content_layout.addLayout(second_row)

        self.machining_operation_hint = QLabel(
            "No saved machining operations yet."
        )
        self.machining_operation_hint.setObjectName("Muted")
        self.machining_operation_hint.setWordWrap(True)
        section.content_layout.addWidget(self.machining_operation_hint)

        self._updating_machining_operations_panel = False
        self._sync_machining_operations_panel()
        return section

    def _operation_source_summary(self, operation: CamOperation) -> str:
        if operation.operation == "surface":
            return "Stock"
        names_by_id = {
            item.item_id: item.name
            for item in self.project.items
        }
        names = [
            names_by_id.get(item_id, "Missing object")
            for item_id in operation.source_item_ids
        ]
        if operation.operation == "silhouette":
            return (
                f"All design objects ({len(names)})"
                if names else "All design objects"
            )
        if not names:
            return "No source objects"
        if len(names) <= 2:
            return ", ".join(names)
        return f"{names[0]}, {names[1]} +{len(names) - 2}"

    def _operation_has_motion(self, operation_id: str) -> bool:
        return any(
            path.cam_operation_id == operation_id
            for path in self.project.toolpaths
        )

    def _operation_display_status(self, operation: CamOperation) -> str:
        if not operation.enabled:
            return "DISABLED"
        if operation.needs_recalculation:
            return "RECALCULATE"
        if not self._operation_has_motion(operation.operation_id):
            return "RECALCULATE"
        return "READY"

    def _sync_machining_operations_panel(
        self,
        selected_operation_id: str | None = None,
    ) -> None:
        rows = getattr(self, "machining_operations_list", None)
        if rows is None:
            return

        if selected_operation_id is None:
            current = rows.currentItem()
            if current is not None:
                selected_operation_id = current.data(_OPERATION_ID_ROLE)

        self._updating_machining_operations_panel = True
        rows.blockSignals(True)
        try:
            rows.clear()
            selected_row = -1
            for index, operation in enumerate(self.project.cam_operations):
                status = self._operation_display_status(operation)
                source = self._operation_source_summary(operation)
                title = self._cam_operation_title(operation.operation)
                text = (
                    f"{index + 1:02d}  {title}  ·  {status}\n"
                    f"{operation.cutter.name}  ·  {source}"
                )
                item = QListWidgetItem(text)
                item.setData(_OPERATION_ID_ROLE, operation.operation_id)
                item.setFlags(
                    item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEnabled
                )
                item.setCheckState(
                    Qt.CheckState.Checked
                    if operation.enabled
                    else Qt.CheckState.Unchecked
                )
                stale = (
                    f"\nNeeds recalculation: {operation.stale_reason}"
                    if operation.needs_recalculation
                    else ""
                )
                item.setToolTip(
                    f"{title}\nCutter: {operation.cutter.name}\n"
                    f"Source: {source}\nState: {status}{stale}"
                )
                rows.addItem(item)
                if operation.operation_id == selected_operation_id:
                    selected_row = index

            if rows.count():
                rows.setCurrentRow(
                    selected_row if selected_row >= 0 else min(
                        max(rows.currentRow(), 0),
                        rows.count() - 1,
                    )
                )
            else:
                rows.setCurrentRow(-1)
        finally:
            rows.blockSignals(False)
            self._updating_machining_operations_panel = False

        enabled = sum(
            1 for operation in self.project.cam_operations if operation.enabled
        )
        stale = sum(
            1
            for operation in self.project.cam_operations
            if operation.enabled and (
                operation.needs_recalculation
                or not self._operation_has_motion(operation.operation_id)
            )
        )
        if not self.project.cam_operations:
            self.machining_operation_hint.setText(
                "No saved machining operations yet. Generate a toolpath to add one."
            )
        else:
            self.machining_operation_hint.setText(
                f"{len(self.project.cam_operations)} saved · {enabled} enabled"
                + (f" · {stale} need recalculation" if stale else " · job current")
            )
        self._sync_machining_operation_action_state()

    def _selected_machining_operation(self) -> CamOperation | None:
        rows = getattr(self, "machining_operations_list", None)
        if rows is None:
            return None
        item = rows.currentItem()
        if item is None:
            return None
        operation_id = item.data(_OPERATION_ID_ROLE)
        return next(
            (
                operation
                for operation in self.project.cam_operations
                if operation.operation_id == operation_id
            ),
            None,
        )

    def _sync_machining_operation_action_state(self) -> None:
        operation = self._selected_machining_operation()
        has_selection = operation is not None
        row = (
            self.machining_operations_list.currentRow()
            if has_selection else -1
        )
        count = len(self.project.cam_operations)
        self.machining_operation_edit_button.setEnabled(has_selection)
        self.machining_operation_recalculate_button.setEnabled(
            bool(operation and operation.enabled)
        )
        self.machining_operation_up_button.setEnabled(
            has_selection and row > 0
        )
        self.machining_operation_down_button.setEnabled(
            has_selection and 0 <= row < count - 1
        )
        self.machining_operation_duplicate_button.setEnabled(has_selection)
        self.machining_operation_delete_button.setEnabled(has_selection)

    def _machining_operation_selection_changed(self, _row: int) -> None:
        self._sync_machining_operation_action_state()
        operation = self._selected_machining_operation()
        if operation is None:
            return
        status = self._operation_display_status(operation)
        self._set_activity_info(
            "Machining operation\n"
            f"{self._cam_operation_title(operation.operation)} · {status}\n\n"
            f"Cutter: {operation.cutter.name}\n"
            f"Source: {self._operation_source_summary(operation)}"
        )

    def _machining_operation_item_changed(self, item: QListWidgetItem) -> None:
        if getattr(self, "_updating_machining_operations_panel", False):
            return
        operation_id = item.data(_OPERATION_ID_ROLE)
        if not isinstance(operation_id, str):
            return
        enabled = item.checkState() == Qt.CheckState.Checked

        self._before_ribbon_mutation("machining operation enabled state")
        changed = operation_plan.set_operation_enabled(self.project, operation_id, enabled)
        self._finish_machining_plan_mutation(
            changed,
            selected_operation_id=operation_id,
            message=(
                "Machining operation enabled"
                if enabled else "Machining operation disabled"
            ),
        )
        self._after_ribbon_mutation(
            "machining operation enabled state",
            changed,
        )

    def _finish_machining_plan_mutation(
        self,
        changed: bool,
        *,
        selected_operation_id: str | None,
        message: str,
    ) -> None:
        if not changed:
            self._sync_machining_operations_panel(selected_operation_id)
            return

        self._prepared_toolpath_geometry = None
        self._prepared_toolpath_stats = None
        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
        self.viewport.set_simulation_fraction(1.0)
        if self._toolpath_preview_window is not None:
            self._toolpath_preview_window.close()
            self._toolpath_preview_window = None

        self._sync_toolpath_state_from_project()
        self._sync_machining_operations_panel(selected_operation_id)
        self.statusBar().showMessage(message, 5000)

    def _move_selected_machining_operation(self, delta: int) -> None:
        if self._background_job is not None:
            self.statusBar().showMessage("Finish the current operation first", 4000)
            return
        operation = self._selected_machining_operation()
        if operation is None:
            return
        old_index = operation_plan.operation_index(self.project, operation.operation_id)
        target = old_index + int(delta)

        self._before_ribbon_mutation("machining operation reorder")
        changed = operation_plan.reorder_operation(
            self.project,
            operation.operation_id,
            target,
        )
        self._finish_machining_plan_mutation(
            changed,
            selected_operation_id=operation.operation_id,
            message="Machining order updated; affected stages need recalculation",
        )
        self._after_ribbon_mutation("machining operation reorder", changed)

    def _duplicate_selected_machining_operation(self) -> None:
        operation = self._selected_machining_operation()
        if operation is None:
            return
        self._before_ribbon_mutation("machining operation duplicate")
        duplicate = operation_plan.duplicate_operation(self.project, operation.operation_id)
        self._finish_machining_plan_mutation(
            True,
            selected_operation_id=duplicate.operation_id,
            message="Machining operation duplicated; affected stages need recalculation",
        )
        self._after_ribbon_mutation("machining operation duplicate", True)

    def _delete_selected_machining_operation(self) -> None:
        operation = self._selected_machining_operation()
        if operation is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete Machining Operation",
            (
                f"Delete {self._cam_operation_title(operation.operation)} using "
                f"{operation.cutter.name}?\n\n"
                "Later machining stages may need recalculation."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._before_ribbon_mutation("machining operation delete")
        operation_plan.delete_operation(self.project, operation.operation_id)
        next_id = (
            self.project.cam_operations[
                min(
                    self.machining_operations_list.currentRow(),
                    len(self.project.cam_operations) - 1,
                )
            ].operation_id
            if self.project.cam_operations
            else None
        )
        self._finish_machining_plan_mutation(
            True,
            selected_operation_id=next_id,
            message="Machining operation deleted",
        )
        self._after_ribbon_mutation("machining operation delete", True)

    def _recalculate_selected_machining_operation(self) -> None:
        operation = self._selected_machining_operation()
        if operation is None or not operation.enabled:
            return
        index = operation_plan.operation_index(self.project, operation.operation_id)

        self._before_ribbon_mutation("machining operation recalculate")
        stale_ids = operation_plan.invalidate_from(
            self.project,
            index,
            "Manual recalculation requested",
        )
        changed = bool(stale_ids)
        self._finish_machining_plan_mutation(
            changed,
            selected_operation_id=operation.operation_id,
            message="Selected operation and dependent stages queued for recalculation",
        )
        self._after_ribbon_mutation(
            "machining operation recalculate",
            changed,
        )
        if changed:
            self._recalculate_stale_cam_operations()

    @staticmethod
    def _operation_editor_double(
        value: float,
        *,
        minimum: float,
        maximum: float,
        suffix: str = "",
        decimals: int = 3,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setValue(float(value))
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        return spin

    def _edit_selected_machining_operation(self) -> None:
        operation = self._selected_machining_operation()
        if operation is None:
            return
        if self._background_job is not None:
            self.statusBar().showMessage("Finish the current operation first", 4000)
            return

        parameters = operation.parameters
        dialog = QDialog(self)
        dialog.setObjectName("MachiningOperationEditor")
        dialog.setWindowTitle("Edit Machining Operation")
        dialog.resize(560, 700)
        layout = QVBoxLayout(dialog)

        summary = QLabel(
            f"Source: {self._operation_source_summary(operation)}\n"
            "Changing machining settings preserves the saved operation but "
            "invalidates this stage and dependent stages."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(form)

        operation_combo = QComboBox(dialog)
        for operation_type in (
            "profile", "silhouette", "pocket", "surface", "v_carving",
            "engrave", "drill", "center_drill", "rough", "finish",
            "height_map", "rest", "waterline",
        ):
            operation_combo.addItem(
                self._cam_operation_title(operation_type),
                operation_type,
            )
        operation_combo.setCurrentIndex(
            max(0, operation_combo.findData(operation.operation))
        )
        form.addRow("Operation", operation_combo)

        cutter_combo = QComboBox(dialog)
        for index in range(self.tool_combo.count()):
            cutter = self.tool_combo.itemData(index)
            if isinstance(cutter, Cutter):
                cutter_combo.addItem(cutter.name, cutter)
        cutter_index = next(
            (
                index
                for index in range(cutter_combo.count())
                if cutter_combo.itemData(index) == operation.cutter
            ),
            -1,
        )
        if cutter_index < 0:
            cutter_combo.addItem(operation.cutter.name, operation.cutter)
            cutter_index = cutter_combo.count() - 1
        cutter_combo.setCurrentIndex(cutter_index)
        form.addRow("Cutter", cutter_combo)

        def choice(
            title: str,
            key: str,
            options: tuple[str, ...],
            default: str,
        ) -> QComboBox:
            combo = QComboBox(dialog)
            combo.addItems(options)
            combo.setCurrentText(str(parameters.get(key, default)))
            form.addRow(title, combo)
            return combo

        cut_type = choice(
            "2D cut type",
            "cut_type",
            ("Auto", "Pocket", "On Path", "Outside", "Inside"),
            "Auto",
        )
        direction = choice(
            "Direction",
            "direction",
            (
                "Smart Serpentine", "Offset", "Raster X", "Raster Y",
                "Raster 45°", "Raster 135°",
            ),
            "Smart Serpentine",
        )
        style_3d = choice(
            "3D style",
            "3d_cut_style",
            ("Model Boundary Relief", "Rectangle Relief", "Full Depth Cutout"),
            "Model Boundary Relief",
        )
        entry = choice(
            "Entry",
            "entry",
            ("Plunge", "Ramp 5°", "Ramp 20°", "Custom Ramp"),
            "Plunge",
        )
        milling = choice(
            "Milling",
            "milling",
            ("Default", "Climb (CCW)", "Conventional (CW)"),
            "Default",
        )
        linking = choice(
            "Linking",
            "linking",
            ("Smart Min-Lift", "Local Lift", "Full Retract"),
            "Smart Min-Lift",
        )

        detail = QSpinBox(dialog)
        detail.setRange(0, 100)
        detail.setValue(int(parameters.get("detail", 50)))
        detail.setSuffix("%")
        form.addRow("Detail", detail)

        numeric_specs = (
            ("safe_z_mm", "Safe Z", 0.05, 1000.0, " mm", 1.5),
            ("overall_depth_mm", "Overall depth", 0.0, 10000.0, " mm", 0.0),
            ("feed_mm_min", "Cut feed", 1.0, 100000.0, " mm/min", 1000.0),
            ("plunge_mm_min", "Plunge feed", 1.0, 100000.0, " mm/min", 300.0),
            ("stepdown_mm", "Depth per pass", 0.01, 10000.0, " mm", 2.0),
            ("stepover_percent", "2D stepover", 1.0, 100.0, "%", 45.0),
            ("padding_mm", "Padding", 0.0, 10000.0, " mm", 0.0),
            ("usable_bit_length_mm", "Usable bit length", 0.0, 10000.0, " mm", 0.0),
            ("local_link_clearance_mm", "Local link clearance", 0.0, 1000.0, " mm", 0.5),
            ("direct_link_tolerance_mm", "Direct-link tolerance", 0.0, 100.0, " mm", 0.02),
            ("custom_ramp_angle_deg", "Custom ramp angle", 0.1, 89.0, "°", 10.0),
            ("rest_min_remaining_mm", "Rest minimum remaining", 0.0, 100.0, " mm", 0.15),
            ("rest_grid_spacing_mm", "Rest grid spacing", 0.01, 100.0, " mm", 0.75),
            ("tab_height_mm", "Tab height", 0.1, 1000.0, " mm", 2.0),
            ("tab_width_mm", "Tab width", 0.1, 1000.0, " mm", 6.0),
        )
        numeric: dict[str, QDoubleSpinBox] = {}
        for key, title, minimum, maximum, suffix, default in numeric_specs:
            spin = self._operation_editor_double(
                float(parameters.get(key, default)),
                minimum=minimum,
                maximum=maximum,
                suffix=suffix,
            )
            numeric[key] = spin
            form.addRow(title, spin)

        tabs_enabled = QCheckBox("Use holding tabs", dialog)
        tabs_enabled.setChecked(bool(parameters.get("tabs_enabled", False)))
        form.addRow("Tabs", tabs_enabled)

        tab_count = QSpinBox(dialog)
        tab_count.setRange(1, 128)
        tab_count.setValue(int(parameters.get("tab_count", 4)))
        form.addRow("Tab count", tab_count)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_parameters = dict(parameters)
        new_parameters.update(
            {
                "cut_type": cut_type.currentText(),
                "direction": direction.currentText(),
                "3d_cut_style": style_3d.currentText(),
                "entry": entry.currentText(),
                "milling": milling.currentText(),
                "linking": linking.currentText(),
                "detail": detail.value(),
                "tabs_enabled": tabs_enabled.isChecked(),
                "tab_count": tab_count.value(),
            }
        )
        for key, spin in numeric.items():
            new_parameters[key] = spin.value()

        cutter = cutter_combo.currentData()
        if not isinstance(cutter, Cutter):
            QMessageBox.warning(
                dialog,
                "Invalid Cutter",
                "Choose a valid cutter before saving this machining operation.",
            )
            return

        operation_type = str(operation_combo.currentData())
        changed = (
            operation_type != operation.operation
            or cutter != operation.cutter
            or new_parameters != operation.parameters
        )
        if not changed:
            return

        self._before_ribbon_mutation("machining operation edit")
        operation_plan.update_operation(
            self.project,
            operation.operation_id,
            operation_type=operation_type,
            cutter=cutter,
            parameters=new_parameters,
        )
        self._finish_machining_plan_mutation(
            True,
            selected_operation_id=operation.operation_id,
            message="Machining settings updated; affected stages need recalculation",
        )
        self._after_ribbon_mutation("machining operation edit", True)

    def _focus_machining_operations_panel(self) -> None:
        self._ensure_inspector_visible()
        panel = getattr(self, "machining_operations_panel", None)
        if panel is not None:
            self.properties_panel.scroll_area.ensureWidgetVisible(panel)
        self.machining_operations_list.setFocus(Qt.FocusReason.OtherFocusReason)
