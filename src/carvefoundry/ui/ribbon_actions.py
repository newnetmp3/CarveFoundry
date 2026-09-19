from __future__ import annotations

import json
from dataclasses import replace
from math import atan2, ceil, degrees, hypot, pi, sqrt
from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontInfo, QImage
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.cam.basic_ops import (
    BasicCamSettings,
    MillingDirection,
    PocketStrategy,
    ReliefStyle,
    detail_for_stepover_fraction,
    detail_stepover_fraction,
)
from carvefoundry.cam.gcode import GrblPostSettings
from carvefoundry.cam.job_process import CamRequest, GcodeRequest
from carvefoundry.cam.job_workflows import (
    TilingSettings,
    find_safe_resume_index,
    plan_tiles,
)
from carvefoundry.cam.raster import RasterAxis, RasterLinkMode
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.machine_profiles import (
    MachineProfile,
    profiles_from_json,
    profiles_to_json,
)
from carvefoundry.core.measurement import measure_xy
from carvefoundry.core.primitives import (
    bitmap_runs_mesh,
    ellipse_mesh,
    line_mesh,
    polygon_mesh,
    rectangle_mesh,
    text_mesh,
)
from carvefoundry.core.project import ProjectItem, TextProperties
from carvefoundry.core.smart_values import SmartValueError, SmartValues
from carvefoundry.core.tools import DEFAULT_TOOLS, Cutter, ToolType
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.units import ModelUnits
from carvefoundry.core.vector_path import VectorPath

from .cam_generation_dialog import CamGenerationDialogMixin
from .machine_control import MachineController
from .toolpath_preview import ToolpathPreviewWindow


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


class RibbonActionsMixin(CamGenerationDialogMixin):
    """Functional implementations for CarveFoundry ribbon actions."""

    def _init_ribbon_action_state(self) -> None:
        self._clipboard_items: list[ProjectItem] = []
        self._active_cam_operation = "finish"
        self._cam_append_to_job = False
        self._tabs_enabled = False
        self._active_shape_tool: str | None = None
        self._camera_tool_active = True
        self._shape_tool_buttons: dict[str, object] = {}
        self._navigation_tool_button = None
        self._camera_tool_button = None
        self._tool_option_depth_mm = 1.0
        self._tool_option_line_width_mm = 2.0
        self._tool_option_pen_width_mm = 2.0
        self._tool_option_pen_smoothing = 35
        self._tool_option_pen_spacing_mm = 0.35
        self._tool_option_pen_close_path = False
        self._tool_option_polygon_sides = 6
        self._tool_option_text = "Text"
        self._fixture_top_z_mm = 5.0
        self._fixture_clearance_mm = 2.0
        self._measurement = None
        self._cam_selector_widgets: dict[str, list[QComboBox]] = {}
        self._cam_detail_widgets: list[object] = []
        self._toolpath_dialog_progress = None
        self._toolpath_progress_last_value = -1
        self._toolpath_progress_last_text = ""

        def saved_choice(
            key: str,
            default: str,
            allowed: tuple[str, ...],
        ) -> str:
            value = str(self._settings.value(key, default))
            return value if value in allowed else default

        self._cam_cut_type = saved_choice(
            "cam/design/cut_type",
            "Auto",
            ("Auto", "Pocket", "On Path", "Outside", "Inside"),
        )
        self._cam_direction = saved_choice(
            "cam/design/direction",
            "Smart Serpentine",
            (
                "Smart Serpentine",
                "Offset",
                "Raster X",
                "Raster Y",
                "Raster 45°",
                "Raster 135°",
            ),
        )
        self._cam_quality = saved_choice(
            "cam/design/quality",
            "Balanced 10%",
            (
                "Fast 15%",
                "Balanced 10%",
                "Detail 8%",
                "Fine 6%",
                "Custom",
            ),
        )
        preset_fraction = {
            "Fast 15%": 0.15,
            "Balanced 10%": 0.10,
            "Detail 8%": 0.08,
            "Fine 6%": 0.06,
        }.get(self._cam_quality, 0.10)
        default_detail = detail_for_stepover_fraction(preset_fraction)
        try:
            saved_detail = int(
                self._settings.value("cam/design/detail", default_detail)
            )
        except (TypeError, ValueError):
            saved_detail = default_detail
        self._cam_detail = max(0, min(100, saved_detail))
        self._cam_entry = saved_choice(
            "cam/design/entry",
            "Plunge",
            ("Plunge", "Ramp 5°", "Ramp 20°", "Custom Ramp"),
        )
        self._cam_linking = saved_choice(
            "cam/design/linking",
            "Smart Min-Lift",
            ("Smart Min-Lift", "Local Lift", "Full Retract"),
        )
        self._cam_milling = saved_choice(
            "cam/design/milling",
            "Default",
            ("Default", "Climb (CCW)", "Conventional (CW)"),
        )
        self._cam_3d_cut_style = saved_choice(
            "cam/design/3d_cut_style",
            "Model Boundary Relief",
            (
                "Model Boundary Relief",
                "Rectangle Relief",
                "Full Depth Cutout",
            ),
        )
        self._tabs_enabled = bool(
            self._settings.value("cam/tabs_enabled", False, type=bool)
        )
        if self._cam_3d_cut_style == "Full Depth Cutout" and not self._tabs_enabled:
            self._tabs_enabled = True
            self._settings.setValue("cam/tabs_enabled", True)
        self._custom_tools = self._load_custom_tools()

        self._simulation_timer = QTimer(self)
        self._simulation_timer.setInterval(40)
        self._simulation_timer.timeout.connect(self._advance_simulation)
        self._simulation_button = None
        self._toolpaths_view_button = None
        self._rapids_view_button = None
        self._tabs_button = None
        self._jog_dialog: QDialog | None = None
        self._toolpath_preview_window: ToolpathPreviewWindow | None = None
        self._machine_connect_button = None

        self.machine_controller = MachineController(self)
        self.machine_controller.connectionChanged.connect(
            self._machine_connection_changed
        )
        self.machine_controller.lineReceived.connect(self._machine_line_received)
        self.machine_controller.errorOccurred.connect(self._machine_error)

    # ------------------------------------------------------------------
    # Generic project/ribbon helpers
    # ------------------------------------------------------------------
    def _before_ribbon_mutation(self, _label: str) -> None:
        """History hook supplied by project_window.MainWindow."""

    def _after_ribbon_mutation(self, label: str, changed: bool) -> None:
        """History hook supplied by project_window.MainWindow."""

        if not changed:
            return
        normalized = label.strip().lower()
        if normalized in {"group", "ungroup"}:
            return
        if normalized.startswith("calculate ") or normalized == "reorder machining job":
            return
        self._invalidate_toolpaths("Project geometry")

    def _selected_design_indices(self, *, expand_groups: bool = False) -> list[int]:
        rows = sorted(
            {
                index.row()
                for index in self.project_list.selectedIndexes()
                if index.row() > 0
            }
        )
        if not rows and self.project_list.currentRow() > 0:
            rows = [self.project_list.currentRow()]

        indices = [
            row - 1
            for row in rows
            if 0 <= row - 1 < len(self.project.items)
        ]
        if not expand_groups:
            return indices

        group_ids = {
            self.project.items[index].group_id
            for index in indices
            if self.project.items[index].group_id
        }
        if group_ids:
            indices = sorted(
                set(indices)
                | {
                    index
                    for index, item in enumerate(self.project.items)
                    if item.group_id in group_ids
                }
            )
        return indices

    @staticmethod
    def _clone_item(
        item: ProjectItem,
        *,
        name: str | None = None,
        group_id: str | None = None,
        offset_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> ProjectItem:
        tx, ty, tz = item.transform.translation_mm
        return ProjectItem(
            name=name or item.name,
            source_path=item.source_path,
            kind=item.kind,
            visible=item.visible,
            mesh=item.mesh,
            transform=Transform3D(
                translation_mm=(
                    tx + offset_mm[0],
                    ty + offset_mm[1],
                    tz + offset_mm[2],
                ),
                rotation_deg=tuple(item.transform.rotation_deg),
                scale_xyz=tuple(item.transform.scale_xyz),
            ),
            source_units=item.source_units,
            group_id=group_id,
            text_properties=item.text_properties,
            smart_bindings=dict(item.smart_bindings),
            vector_path=item.vector_path,
        )

    def _unique_item_name(self, stem: str) -> str:
        existing = {item.name for item in self.project.items}
        if stem not in existing:
            return stem
        number = 2
        while f"{stem} {number}" in existing:
            number += 1
        return f"{stem} {number}"

    # ------------------------------------------------------------------
    # Design / clipboard / arrange
    # ------------------------------------------------------------------
    def _redo(self) -> None:
        self.statusBar().showMessage("Nothing to redo", 3000)

    def _copy_selected_items(self) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if not indices:
            self.statusBar().showMessage("Select a design item to copy", 3000)
            return
        self._clipboard_items = [
            self._clone_item(self.project.items[index])
            for index in indices
        ]
        self._sync_selection_action_state()
        self.statusBar().showMessage(
            f"Copied {len(self._clipboard_items)} item(s)",
            2500,
        )

    def _cut_selected_items(self) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if not indices:
            self.statusBar().showMessage("Select a design item to cut", 3000)
            return

        self._before_ribbon_mutation("cut")
        self._clipboard_items = [
            self._clone_item(self.project.items[index])
            for index in indices
        ]
        for index in reversed(indices):
            self.project.items.pop(index)
        self._refresh_project_list(
            min(indices[0] + 1, len(self.project.items))
        )
        self.viewport.update()
        self._after_ribbon_mutation("cut", True)
        self.statusBar().showMessage(f"Cut {len(indices)} item(s)", 2500)

    def _paste_items(self) -> None:
        if not self._clipboard_items:
            self.statusBar().showMessage("Clipboard is empty", 3000)
            return

        self._before_ribbon_mutation("paste")
        group_map: dict[str, str] = {}
        pasted: list[ProjectItem] = []
        for source in self._clipboard_items:
            group_id = None
            if source.group_id:
                group_id = group_map.setdefault(source.group_id, uuid4().hex)
            pasted.append(
                self._clone_item(
                    source,
                    name=self._unique_item_name(f"{Path(source.name).stem} copy"),
                    group_id=group_id,
                    offset_mm=(5.0, 5.0, 0.0),
                )
            )
        self.project.items.extend(pasted)
        self._refresh_project_list(len(self.project.items))
        self.viewport.update()
        self._after_ribbon_mutation("paste", True)
        self.statusBar().showMessage(f"Pasted {len(pasted)} item(s)", 2500)

    def _align_selected_items(self) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if not indices:
            self.statusBar().showMessage("Select one or more design items", 3000)
            return
        options = [
            "Left",
            "Center X",
            "Right",
            "Bottom",
            "Center Y",
            "Top",
            "Top Z0",
            "Bottom Z0",
        ]
        choice, accepted = QInputDialog.getItem(
            self,
            "Align",
            "Alignment",
            options,
            1,
            False,
        )
        if not accepted:
            return

        bounds = {
            index: self.project.items[index].transformed_bounds_mm()
            for index in indices
        }
        valid = {
            index: value
            for index, value in bounds.items()
            if value is not None
        }
        if not valid:
            self.statusBar().showMessage("Selected items have no geometry", 3000)
            return

        collective_min = np.min([value[0] for value in valid.values()], axis=0)
        collective_max = np.max([value[1] for value in valid.values()], axis=0)
        collective_center = (collective_min + collective_max) / 2.0

        self._before_ribbon_mutation(f"align {choice}")
        for index, item_bounds in valid.items():
            item = self.project.items[index]
            item_center = item_bounds.mean(axis=0)
            tx, ty, tz = item.transform.translation_mm
            dx = dy = dz = 0.0
            if choice == "Left":
                target = 0.0 if len(valid) == 1 else float(collective_min[0])
                dx = target - float(item_bounds[0, 0])
            elif choice == "Center X":
                target = (
                    self.project.stock.width_mm / 2.0
                    if len(valid) == 1
                    else float(collective_center[0])
                )
                dx = target - float(item_center[0])
            elif choice == "Right":
                target = (
                    self.project.stock.width_mm
                    if len(valid) == 1
                    else float(collective_max[0])
                )
                dx = target - float(item_bounds[1, 0])
            elif choice == "Bottom":
                target = 0.0 if len(valid) == 1 else float(collective_min[1])
                dy = target - float(item_bounds[0, 1])
            elif choice == "Center Y":
                target = (
                    self.project.stock.height_mm / 2.0
                    if len(valid) == 1
                    else float(collective_center[1])
                )
                dy = target - float(item_center[1])
            elif choice == "Top":
                target = (
                    self.project.stock.height_mm
                    if len(valid) == 1
                    else float(collective_max[1])
                )
                dy = target - float(item_bounds[1, 1])
            elif choice == "Top Z0":
                dz = -float(item_bounds[1, 2])
            elif choice == "Bottom Z0":
                dz = -float(item_bounds[0, 2])
            item.transform.translation_mm = (tx + dx, ty + dy, tz + dz)

        self._refresh_project_list(indices[-1] + 1)
        self._select_project_indices(indices, primary=indices[-1])
        self.viewport.update()
        self._after_ribbon_mutation(f"align {choice}", True)
        self.statusBar().showMessage(f"Aligned {len(valid)} item(s): {choice}", 3000)

    def _center_selected_items(self) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if not indices:
            self.statusBar().showMessage("Select one or more design items", 3000)
            return
        bounds = [
            self.project.items[index].transformed_bounds_mm()
            for index in indices
        ]
        valid = [value for value in bounds if value is not None]
        if not valid:
            return
        minimum = np.min([value[0] for value in valid], axis=0)
        maximum = np.max([value[1] for value in valid], axis=0)
        center = (minimum + maximum) / 2.0
        dx = self.project.stock.width_mm / 2.0 - float(center[0])
        dy = self.project.stock.height_mm / 2.0 - float(center[1])

        self._before_ribbon_mutation("center selection")
        for index in indices:
            item = self.project.items[index]
            tx, ty, tz = item.transform.translation_mm
            item.transform.translation_mm = (tx + dx, ty + dy, tz)
        self._refresh_project_list(indices[-1] + 1)
        self._select_project_indices(indices, primary=indices[-1])
        self.viewport.update()
        self._after_ribbon_mutation("center selection", True)
        self.statusBar().showMessage("Centered selection on stock", 3000)

    def _group_selected_items(self) -> None:
        indices = self._selected_design_indices()
        if len(indices) < 2:
            self.statusBar().showMessage("Select at least two items to group", 3000)
            return
        self._before_ribbon_mutation("group")
        group_id = uuid4().hex
        for index in indices:
            self.project.items[index].group_id = group_id
        self._refresh_project_list(indices[-1] + 1)
        self._select_project_indices(indices, primary=indices[-1])
        self._after_ribbon_mutation("group", True)
        self.statusBar().showMessage(f"Grouped {len(indices)} items", 3000)

    def _ungroup_selected_items(self) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        grouped = [
            index
            for index in indices
            if self.project.items[index].group_id is not None
        ]
        if not grouped:
            self.statusBar().showMessage("Selected items are not grouped", 3000)
            return
        self._before_ribbon_mutation("ungroup")
        for index in grouped:
            self.project.items[index].group_id = None
        self._refresh_project_list(grouped[-1] + 1)
        self._select_project_indices(grouped, primary=grouped[-1])
        self._after_ribbon_mutation("ungroup", True)
        self.statusBar().showMessage(f"Ungrouped {len(grouped)} items", 3000)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def _add_generated_item(self, name: str, kind: str, mesh) -> None:
        bounds = np.asarray(mesh.bounds, dtype=float)
        center = bounds.mean(axis=0)
        transform = Transform3D(
            translation_mm=(
                self.project.stock.width_mm / 2.0 - float(center[0]),
                self.project.stock.height_mm / 2.0 - float(center[1]),
                -float(bounds[1, 2]),
            )
        )
        item = ProjectItem(
            name=self._unique_item_name(name),
            kind=kind,
            mesh=mesh,
            transform=transform,
            source_units=ModelUnits.MILLIMETERS,
        )
        self._before_ribbon_mutation(f"create {kind}")
        self.project.items.append(item)
        self._refresh_project_list(len(self.project.items))
        self.viewport.update()
        self._after_ribbon_mutation(f"create {kind}", True)
        self.statusBar().showMessage(f"Created {item.name}", 3000)

    def _activate_camera_tool(self) -> None:
        """Activate dedicated arcball-style viewport camera control."""

        self._camera_tool_active = True
        self.viewport.set_node_edit_mode(False)
        self.viewport.set_shape_draw_mode(None)
        self.viewport.set_camera_control_mode(True)
        if self._camera_tool_button is not None:
            self._camera_tool_button.blockSignals(True)
            try:
                self._camera_tool_button.setChecked(True)
            finally:
                self._camera_tool_button.blockSignals(False)
        if self._navigation_tool_button is not None:
            self._navigation_tool_button.blockSignals(True)
            try:
                self._navigation_tool_button.setChecked(False)
            finally:
                self._navigation_tool_button.blockSignals(False)
        if hasattr(self, "tool_rail"):
            self.tool_rail.set_active_tool("camera")
        self.statusBar().showMessage(
            "Camera / Arcball — left-drag orbits • middle/right-drag pans • "
            "wheel zooms",
            3500,
        )

    def _activate_navigation_tool(self) -> None:
        """Return the viewport to object selection / marquee mode."""

        self._camera_tool_active = False
        self.viewport.set_node_edit_mode(False)
        self.viewport.set_camera_control_mode(False)
        self.viewport.set_shape_draw_mode(None)
        if self._camera_tool_button is not None:
            self._camera_tool_button.blockSignals(True)
            try:
                self._camera_tool_button.setChecked(False)
            finally:
                self._camera_tool_button.blockSignals(False)
        self.statusBar().showMessage(
            "Select tool — click objects to select • drag empty space for marquee • "
            "Alt+drag orbits",
            3500,
        )

    def _apply_active_tool(self) -> None:
        """Finish the current draw tool and keep completed geometry."""

        if self._active_shape_tool is None:
            return
        label = self._active_shape_tool.title()
        self.viewport.set_shape_draw_mode(None)
        self.statusBar().showMessage(
            f"{label} tool applied — returned to Select",
            2500,
        )

    def _cancel_active_tool(self) -> None:
        """Cancel the current draw tool/preview without deleting finished items."""

        if self._active_shape_tool is None:
            return
        label = self._active_shape_tool.title()
        self.viewport.set_shape_draw_mode(None)
        self.statusBar().showMessage(
            f"{label} tool canceled — returned to Select",
            2500,
        )

    def _sync_tool_options_bar(self, mode: str | None) -> None:
        """Show only options relevant to the active paint-style tool."""

        bar = getattr(self, "tool_options_bar", None)
        if bar is None:
            return
        active = bool(mode)
        bar.setVisible(active)
        if not active:
            return

        self.tool_options_title.setText(f"{mode.title()} Tool")
        self.tool_options_depth_spin.blockSignals(True)
        self.tool_options_depth_spin.setValue(self._tool_option_depth_mm)
        self.tool_options_depth_spin.blockSignals(False)
        has_depth = mode not in {"measure", "fixture"}
        self.tool_options_depth_label.setVisible(has_depth)
        self.tool_options_depth_spin.setVisible(has_depth)
        is_fixture = mode == "fixture"
        for element in (
            self.tool_options_fixture_top_label,
            self.tool_options_fixture_top_spin,
            self.tool_options_fixture_clearance_label,
            self.tool_options_fixture_clearance_spin,
        ):
            element.setVisible(is_fixture)
        if is_fixture:
            self.tool_options_fixture_top_spin.blockSignals(True)
            self.tool_options_fixture_top_spin.setValue(self._fixture_top_z_mm)
            self.tool_options_fixture_top_spin.blockSignals(False)
            self.tool_options_fixture_clearance_spin.blockSignals(True)
            self.tool_options_fixture_clearance_spin.setValue(
                self._fixture_clearance_mm
            )
            self.tool_options_fixture_clearance_spin.blockSignals(False)
        self.tool_options_fixture_size_label.setVisible(is_fixture)
        if is_fixture:
            self.tool_options_fixture_size_label.setText(
                "Drag a rectangle on the stock to place a fixture"
            )
        self.tool_options_measure_label.setVisible(mode == "measure")
        self.tool_options_measure_clear.setVisible(mode == "measure")
        if mode == "measure":
            self.tool_options_measure_label.setText(
                self._measurement.label if self._measurement is not None
                else "Drag two points on stock top (XY · Z0)"
            )

        is_polygon = mode == "polygon"
        self.tool_options_polygon_label.setVisible(is_polygon)
        self.tool_options_polygon_sides.setVisible(is_polygon)
        if is_polygon:
            self.tool_options_polygon_sides.blockSignals(True)
            self.tool_options_polygon_sides.setValue(
                self._tool_option_polygon_sides
            )
            self.tool_options_polygon_sides.blockSignals(False)

        is_line = mode == "line"
        self.tool_options_line_width_label.setVisible(is_line)
        self.tool_options_line_width_spin.setVisible(is_line)
        if is_line:
            self.tool_options_line_width_spin.blockSignals(True)
            self.tool_options_line_width_spin.setValue(
                self._tool_option_line_width_mm
            )
            self.tool_options_line_width_spin.blockSignals(False)

        is_pen = mode == "pen"
        self.tool_options_pen_width_label.setVisible(is_pen)
        self.tool_options_pen_width_spin.setVisible(is_pen)
        self.tool_options_pen_smoothing_label.setVisible(is_pen)
        self.tool_options_pen_smoothing_spin.setVisible(is_pen)
        self.tool_options_pen_spacing_label.setVisible(is_pen)
        self.tool_options_pen_spacing_spin.setVisible(is_pen)
        self.tool_options_pen_close_check.setVisible(is_pen)
        if is_pen:
            self.tool_options_pen_width_spin.blockSignals(True)
            self.tool_options_pen_width_spin.setValue(
                self._tool_option_pen_width_mm
            )
            self.tool_options_pen_width_spin.blockSignals(False)
            self.tool_options_pen_smoothing_spin.blockSignals(True)
            self.tool_options_pen_smoothing_spin.setValue(
                self._tool_option_pen_smoothing
            )
            self.tool_options_pen_smoothing_spin.blockSignals(False)
            self.tool_options_pen_spacing_spin.blockSignals(True)
            self.tool_options_pen_spacing_spin.setValue(
                self._tool_option_pen_spacing_mm
            )
            self.tool_options_pen_spacing_spin.blockSignals(False)
            self.tool_options_pen_close_check.blockSignals(True)
            self.tool_options_pen_close_check.setChecked(
                self._tool_option_pen_close_path
            )
            self.tool_options_pen_close_check.blockSignals(False)
            self.viewport.set_pen_sample_spacing(
                self._tool_option_pen_spacing_mm
            )

        is_text = mode == "text"
        self.tool_options_text_label.setVisible(is_text)
        self.tool_options_text_edit.setVisible(is_text)
        self.tool_options_font_label.setVisible(is_text)
        self.tool_options_font_value.setVisible(is_text)
        if is_text:
            self.tool_options_text_edit.blockSignals(True)
            self.tool_options_text_edit.setText(self._tool_option_text)
            self.tool_options_text_edit.blockSignals(False)
            family = (
                self._selected_text_font_family()
                if hasattr(self, "_selected_text_font_family")
                else QFontInfo(QFont()).family()
            )
            self.tool_options_font_value.setText(family)

    def _fixture_top_changed(self, value: float) -> None:
        self._fixture_top_z_mm = float(value)

    def _fixture_clearance_changed(self, value: float) -> None:
        self._fixture_clearance_mm = float(value)

    def _clear_measurement(self) -> None:
        self._measurement = None
        self.viewport.set_measurement(None)
        if hasattr(self, "tool_options_measure_label"):
            self.tool_options_measure_label.setText(
                "Drag two points on stock top (XY · Z0)"
            )
        self.statusBar().showMessage("Measurement cleared", 2500)

    def _tool_option_depth_changed(self, value: float) -> None:
        self._tool_option_depth_mm = float(value)

    def _tool_option_line_width_changed(self, value: float) -> None:
        self._tool_option_line_width_mm = float(value)

    def _tool_option_pen_width_changed(self, value: float) -> None:
        self._tool_option_pen_width_mm = float(value)

    def _tool_option_pen_smoothing_changed(self, value: int) -> None:
        self._tool_option_pen_smoothing = max(0, min(100, int(value)))

    def _tool_option_pen_spacing_changed(self, value: float) -> None:
        self._tool_option_pen_spacing_mm = max(0.02, float(value))
        if hasattr(self, "viewport"):
            self.viewport.set_pen_sample_spacing(
                self._tool_option_pen_spacing_mm
            )

    def _tool_option_pen_close_changed(self, checked: bool) -> None:
        self._tool_option_pen_close_path = bool(checked)

    def _tool_option_polygon_sides_changed(self, value: int) -> None:
        self._tool_option_polygon_sides = int(value)

    def _tool_option_text_changed(self, text: str) -> None:
        self._tool_option_text = text or "Text"

    def _set_shape_tool(self, tool: str) -> None:
        """Activate one paint-style shape tool in the viewport."""

        self._camera_tool_active = False
        self.viewport.set_node_edit_mode(False)
        self.viewport.set_camera_control_mode(False)
        if self._camera_tool_button is not None:
            self._camera_tool_button.blockSignals(True)
            try:
                self._camera_tool_button.setChecked(False)
            finally:
                self._camera_tool_button.blockSignals(False)

        button = self._shape_tool_buttons.get(tool)
        wants_active = bool(button is None or button.isChecked())
        if tool == "fixture" and hasattr(self, "tool_rail"):
            rail_button = self.tool_rail.buttons.get("fixture")
            if rail_button is not None:
                wants_active = rail_button.isChecked()
        if self._active_shape_tool == tool and not wants_active:
            self._activate_navigation_tool()
            return

        self._active_shape_tool = tool
        for name, shape_button in self._shape_tool_buttons.items():
            shape_button.blockSignals(True)
            try:
                shape_button.setChecked(name == tool)
            finally:
                shape_button.blockSignals(False)

        if self._navigation_tool_button is not None:
            self._navigation_tool_button.blockSignals(True)
            try:
                self._navigation_tool_button.setChecked(False)
            finally:
                self._navigation_tool_button.blockSignals(False)

        if tool == "pen":
            self.viewport.set_pen_sample_spacing(
                self._tool_option_pen_spacing_mm
            )
        self.viewport.set_shape_draw_mode(tool)
        label = tool.title()
        if tool == "pen":
            message = (
                "Pen tool — draw freehand directly on the stock • "
                "Alt+drag orbits • Esc returns to Select"
            )
        else:
            message = (
                f"{label} tool — drag on the stock to draw • Shift constrains • "
                "Alt+drag orbits • Esc returns to Select"
            )
        self.statusBar().showMessage(message)

    def _shape_draw_mode_changed(self, mode: str) -> None:
        self._active_shape_tool = mode or None
        for name, button in self._shape_tool_buttons.items():
            button.blockSignals(True)
            try:
                button.setChecked(name == mode)
            finally:
                button.blockSignals(False)
        if self._navigation_tool_button is not None:
            self._navigation_tool_button.blockSignals(True)
            try:
                self._navigation_tool_button.setChecked(
                    not bool(mode) and not self._camera_tool_active
                )
            finally:
                self._navigation_tool_button.blockSignals(False)
        if self._camera_tool_button is not None:
            self._camera_tool_button.blockSignals(True)
            try:
                self._camera_tool_button.setChecked(
                    not bool(mode) and self._camera_tool_active
                )
            finally:
                self._camera_tool_button.blockSignals(False)
        if hasattr(self, "tool_rail"):
            active = (
                "camera"
                if not mode and self._camera_tool_active
                else (mode or "select")
            )
            self.tool_rail.set_active_tool(active)
        self._sync_tool_options_bar(mode or None)

    def _add_drawn_item(
        self,
        name: str,
        kind: str,
        mesh,
        transform: Transform3D,
        *,
        text_properties: TextProperties | None = None,
        vector_path: VectorPath | None = None,
    ) -> ProjectItem:
        item = ProjectItem(
            name=self._unique_item_name(name),
            kind=kind,
            mesh=mesh,
            transform=transform,
            source_units=ModelUnits.MILLIMETERS,
            text_properties=text_properties,
            vector_path=vector_path,
        )
        self._before_ribbon_mutation(f"draw {kind}")
        self.project.items.append(item)
        self._refresh_project_list(len(self.project.items))
        self.viewport.update()
        self._after_ribbon_mutation(f"draw {kind}", True)
        self.statusBar().showMessage(f"Drew {item.name}", 2500)
        return item

    def _shape_drag_updated(
        self, tool: str, x0: float, y0: float, x1: float, y1: float,
    ) -> None:
        """Show accurate dimensions while dragging; commit only on release."""

        if tool == "measure":
            self.tool_options_measure_label.setText(
                measure_xy((x0, y0), (x1, y1)).label
            )
        elif tool == "fixture":
            self.tool_options_fixture_size_label.setText(
                f"XY {abs(x1 - x0):.3f} × {abs(y1 - y0):.3f} mm"
            )

    def _shape_drawn(
        self,
        tool: str,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
    ) -> None:
        """Create geometry from a click-drag gesture on the stock."""

        min_x, max_x = sorted((float(x0), float(x1)))
        min_y, max_y = sorted((float(y0), float(y1)))
        width = max_x - min_x
        height = max_y - min_y
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        depth = self._tool_option_depth_mm

        if tool == "measure":
            reading = measure_xy((x0, y0), (x1, y1))
            self._measurement = reading
            self.viewport.set_measurement(
                reading.start_xy, reading.end_xy
            )
            self.tool_options_measure_label.setText(reading.label)
            self.statusBar().showMessage(reading.label, 12000)
            return

        if tool == "fixture":
            if width < 0.1 or height < 0.1:
                self.statusBar().showMessage(
                    "Draw a fixture with positive X and Y dimensions", 4000
                )
                return
            fixture = Fixture(
                name=f"Fixture {len(self.project.fixtures) + 1}",
                x_min_mm=min_x,
                y_min_mm=min_y,
                x_max_mm=max_x,
                y_max_mm=max_y,
                top_z_mm=self._fixture_top_z_mm,
                clearance_mm=self._fixture_clearance_mm,
            )
            fixture.validate()
            self._before_ribbon_mutation("draw fixture")
            self.project.fixtures.append(fixture)
            self.viewport.update()
            self._after_ribbon_mutation("draw fixture", True)
            self.statusBar().showMessage(
                f"Added {fixture.name} — top Z{fixture.top_z_mm:g} mm, "
                f"clearance {fixture.clearance_mm:g} mm", 6000
            )
            return

        if tool in {"rectangle", "ellipse", "polygon", "text"} and (
            width < 0.10 or height < 0.10
        ):
            self.statusBar().showMessage("Drag farther to create the shape", 2500)
            return

        if tool == "rectangle":
            mesh = rectangle_mesh(width, height, depth)
            transform = Transform3D(
                translation_mm=(center_x, center_y, 0.0)
            )
            self._add_drawn_item("Rectangle", "rectangle", mesh, transform)
            return

        if tool == "ellipse":
            mesh = ellipse_mesh(width, height, depth)
            transform = Transform3D(
                translation_mm=(center_x, center_y, 0.0)
            )
            self._add_drawn_item("Ellipse", "ellipse", mesh, transform)
            return

        if tool == "polygon":
            # Start from a unit regular hexagon and stretch it to the drag box.
            mesh = polygon_mesh(
                self._tool_option_polygon_sides,
                1.0,
                depth,
            )
            transform = Transform3D(
                translation_mm=(center_x, center_y, 0.0),
                scale_xyz=(width, height, 1.0),
            )
            self._add_drawn_item("Polygon", "polygon", mesh, transform)
            return

        if tool == "line":
            dx = float(x1 - x0)
            dy = float(y1 - y0)
            length = hypot(dx, dy)
            if length < 0.10:
                self.statusBar().showMessage("Drag farther to create the line", 2500)
                return
            mesh = line_mesh(
                length,
                self._tool_option_line_width_mm,
                depth,
            )
            transform = Transform3D(
                translation_mm=(
                    (float(x0) + float(x1)) / 2.0,
                    (float(y0) + float(y1)) / 2.0,
                    0.0,
                ),
                rotation_deg=(0.0, 0.0, degrees(atan2(dy, dx))),
            )
            self._add_drawn_item(
                "Line", "line", mesh, transform,
                vector_path=VectorPath(
                    points_xy=((-length / 2.0, 0.0), (length / 2.0, 0.0)),
                    width_mm=self._tool_option_line_width_mm,
                    depth_mm=depth,
                ),
            )
            return

        if tool == "text":
            size_pt = max(6.0, height * 72.0 / 25.4)
            properties = TextProperties(
                content=self._tool_option_text or "Text",
                font_family=(
                    self._selected_text_font_family()
                    if hasattr(self, "_selected_text_font_family")
                    else QFontInfo(QFont()).family()
                ),
                font_style="Regular",
                size_pt=size_pt,
                box_width_mm=max(width, 0.1),
                depth_mm=depth,
            )
            try:
                mesh = text_mesh(properties=properties)
                source_width = float(mesh.dimensions[0])
                if source_width > width and source_width > 1e-9:
                    properties = replace(
                        properties,
                        size_pt=max(
                            4.0,
                            properties.size_pt * width / source_width,
                        ),
                    )
                    mesh = text_mesh(properties=properties)
            except (RuntimeError, ValueError) as exc:
                self.statusBar().showMessage(str(exc), 5000)
                return

            bounds = np.asarray(mesh.bounds, dtype=float)
            transform = Transform3D(
                translation_mm=(
                    min_x - float(bounds[0, 0]),
                    min_y - float(bounds[0, 1]),
                    -float(bounds[1, 2]),
                )
            )
            self._add_drawn_item(
                "Text",
                "text",
                mesh,
                transform,
                text_properties=properties,
            )
            self._focus_text_editor()
            return

    def _activate_measure_tool(self) -> None:
        self._set_shape_tool("measure")

    def _activate_fixture_tool(self) -> None:
        self._set_shape_tool("fixture")

    def _create_rectangle(self) -> None:
        self._set_shape_tool("rectangle")

    def _create_ellipse(self) -> None:
        self._set_shape_tool("ellipse")

    def _create_polygon(self) -> None:
        self._set_shape_tool("polygon")

    def _create_line(self) -> None:
        self._set_shape_tool("line")

    def _create_text(self) -> None:
        self._set_shape_tool("text")

    def _create_pen_path(self) -> None:
        self._set_shape_tool("pen")

    def _smooth_pen_points(
        self,
        points_xy: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        """Apply adjustable freehand smoothing while preserving endpoints."""

        points = np.asarray(points_xy, dtype=float)
        if len(points) < 3 or self._tool_option_pen_smoothing <= 0:
            return [tuple(map(float, point)) for point in points]

        blend = self._tool_option_pen_smoothing / 100.0
        passes = 1 + self._tool_option_pen_smoothing // 34
        smoothed = points.copy()
        for _ in range(passes):
            averaged = smoothed.copy()
            averaged[1:-1] = (
                smoothed[:-2] + 2.0 * smoothed[1:-1] + smoothed[2:]
            ) / 4.0
            smoothed[1:-1] = (
                (1.0 - blend) * smoothed[1:-1]
                + blend * averaged[1:-1]
            )
        return [tuple(map(float, point)) for point in smoothed]

    def _freehand_pen_drawn(self, points: object) -> None:
        """Create one persistent pen object from a viewport freehand stroke."""

        try:
            captured = [
                (float(point[0]), float(point[1]))
                for point in points
            ]
        except (TypeError, ValueError, IndexError):
            self.statusBar().showMessage("Invalid freehand pen stroke", 3000)
            return

        if len(captured) < 2:
            return

        captured = self._smooth_pen_points(captured)
        if (
            self._tool_option_pen_close_path
            and len(captured) >= 3
            and hypot(
                captured[-1][0] - captured[0][0],
                captured[-1][1] - captured[0][1],
            )
            > 1e-9
        ):
            captured.append(captured[0])

        path = VectorPath(
            points_xy=tuple(
                captured[:-1] if (
                    len(captured) >= 3 and captured[0] == captured[-1]
                ) else captured
            ),
            width_mm=self._tool_option_pen_width_mm,
            depth_mm=self._tool_option_depth_mm,
            closed=bool(
                len(captured) >= 3 and captured[0] == captured[-1]
            ),
        )
        try:
            mesh = path.mesh_asset()
        except ValueError as exc:
            self.statusBar().showMessage(f"Pen stroke failed: {exc}", 5000)
            return

        self._add_drawn_item(
            "Pen Stroke",
            "pen",
            mesh,
            Transform3D(),
            vector_path=path,
        )

    def _trace_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Trace Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)",
        )
        if not path:
            return

        form = _ActionForm(self, "Trace Image")
        form.add_int(
            "threshold", "Dark threshold (0-255)", 150,
            minimum=0, maximum=255,
        )
        form.add_double(
            "width",
            "Output width",
            min(120.0, self.project.stock.width_mm * 0.7),
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double("depth", "Depth", 1.0, minimum=0.1, suffix=" mm")
        form.add_check("invert", "Trace light pixels instead", False)
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        # Capture every setting on the GUI thread. Image decoding, pixel
        # conversion and mesh construction happen in the background worker.
        threshold = int(form.value("threshold"))
        invert = bool(form.value("invert"))
        width_mm = float(form.value("width"))
        depth_mm = float(form.value("depth"))
        name = Path(path).stem + " trace"

        def trace(progress):
            progress(0.03, "Loading image")
            image = QImage(path)
            if image.isNull():
                raise ValueError("Could not load image.")
            max_dimension = 96
            if max(image.width(), image.height()) > max_dimension:
                image = image.scaled(
                    max_dimension,
                    max_dimension,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            mask = np.zeros((image.height(), image.width()), dtype=bool)
            for y in range(image.height()):
                for x in range(image.width()):
                    color = QColor(image.pixel(x, y))
                    luminance = (
                        0.2126 * color.red()
                        + 0.7152 * color.green()
                        + 0.0722 * color.blue()
                    )
                    active = color.alpha() > 16 and luminance <= threshold
                    mask[y, x] = (
                        not active if invert and color.alpha() > 16 else active
                    )
                if y % 4 == 0:
                    progress(
                        0.15 + 0.60 * (y + 1) / max(1, image.height()),
                        f"Tracing row {y + 1} / {image.height()}",
                    )
            progress(0.78, "Building relief mesh")
            mesh = bitmap_runs_mesh(
                mask, width_mm=width_mm, depth_mm=depth_mm
            )
            progress(0.98, "Trace ready")
            return mesh

        self._start_background_job(
            "Trace image",
            task=trace,
            on_done=lambda mesh: self._add_generated_item(name, "trace", mesh),
        )

    # ------------------------------------------------------------------
    # Toolpaths / CAM
    # ------------------------------------------------------------------
    def _register_cam_selector(self, key: str, combo: QComboBox) -> None:
        self._cam_selector_widgets.setdefault(key, []).append(combo)

    def _register_cam_detail_slider(self, widget) -> None:
        self._cam_detail_widgets.append(widget)
        self._refresh_cam_detail_readouts()

    def _set_cam_detail(
        self,
        value: int,
        *,
        mark_custom: bool = True,
    ) -> None:
        detail = max(0, min(100, int(value)))
        self._cam_detail = detail
        self._settings.setValue("cam/design/detail", detail)

        if mark_custom and self._cam_quality != "Custom":
            self._cam_quality = "Custom"
            self._settings.setValue("cam/design/quality", "Custom")
            for combo in self._cam_selector_widgets.get("quality", []):
                combo.blockSignals(True)
                try:
                    index = combo.findText("Custom")
                    if index >= 0:
                        combo.setCurrentIndex(index)
                finally:
                    combo.blockSignals(False)

        for widget in self._cam_detail_widgets:
            slider = widget.slider
            if slider.value() == detail:
                continue
            slider.blockSignals(True)
            try:
                slider.setValue(detail)
            finally:
                slider.blockSignals(False)

        self._settings.sync()
        self._refresh_cam_detail_readouts()

        fraction = detail_stepover_fraction(detail)
        cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        if isinstance(cutter, Cutter):
            stepover = cutter.diameter_mm * fraction
            message = (
                f"Detail {detail}% — {fraction * 100:.1f}% stepover "
                f"({stepover:.3f} mm with {cutter.name})"
            )
        else:
            message = (
                f"Detail {detail}% — {fraction * 100:.1f}% cutter stepover"
            )
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(message, 2500)

    def _estimated_detail_raster_lines(self, stepover_mm: float) -> int | None:
        if stepover_mm <= 0.0:
            return None
        if not hasattr(self, "project_list"):
            return None
        item = self._selected_item()
        if item is None:
            return None
        bounds = item.transformed_bounds_mm()
        if bounds is None:
            return None

        span = np.maximum(
            np.asarray(bounds[1, :2], dtype=float)
            - np.asarray(bounds[0, :2], dtype=float),
            0.0,
        )
        span_x = float(span[0])
        span_y = float(span[1])

        direction = self._cam_direction
        if direction == "Offset":
            return None
        if direction == "Raster X":
            cross_span = span_y
        elif direction == "Raster Y":
            cross_span = span_x
        elif direction in {"Raster 45°", "Raster 135°"}:
            cross_span = (span_x + span_y) / sqrt(2.0)
        else:
            # Smart Serpentine runs along the longer dimension, leaving fewer
            # raster rows across the shorter dimension.
            cross_span = min(span_x, span_y)

        if cross_span <= 1e-9:
            return None
        return max(2, ceil(cross_span / stepover_mm) + 1)

    def _refresh_cam_detail_readouts(self) -> None:
        if not self._cam_detail_widgets:
            return

        fraction = detail_stepover_fraction(self._cam_detail)
        cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        if isinstance(cutter, Cutter):
            stepover = cutter.diameter_mm * fraction
            line_count = self._estimated_detail_raster_lines(stepover)
            text = f"{fraction * 100:.1f}% • {stepover:.3f} mm"
            if line_count is not None:
                text += f" • ~{line_count:,} lines"
        else:
            text = f"{fraction * 100:.1f}% of cutter"

        for widget in self._cam_detail_widgets:
            widget.set_readout(text)

    def _set_cam_design_option(self, key: str, value: str) -> None:
        attributes = {
            "cut_type": "_cam_cut_type",
            "direction": "_cam_direction",
            "quality": "_cam_quality",
            "entry": "_cam_entry",
            "linking": "_cam_linking",
            "milling": "_cam_milling",
            "3d_cut_style": "_cam_3d_cut_style",
        }
        attribute = attributes[key]
        setattr(self, attribute, value)
        self._settings.setValue(f"cam/design/{key}", value)

        if key == "quality" and value != "Custom":
            fraction = {
                "Fast 15%": 0.15,
                "Balanced 10%": 0.10,
                "Detail 8%": 0.08,
                "Fine 6%": 0.06,
            }[value]
            self._set_cam_detail(
                detail_for_stepover_fraction(fraction),
                mark_custom=False,
            )
        if (
            key == "3d_cut_style"
            and value == "Full Depth Cutout"
            and not self._tabs_enabled
        ):
            self._tabs_enabled = True
            self._settings.setValue("cam/tabs_enabled", True)
            if self._tabs_button is not None:
                self._tabs_button.setChecked(True)
        self._settings.sync()

        for combo in self._cam_selector_widgets.get(key, []):
            if combo.currentText() == value:
                continue
            combo.blockSignals(True)
            try:
                index = combo.findText(value)
                if index >= 0:
                    combo.setCurrentIndex(index)
            finally:
                combo.blockSignals(False)

        for action in getattr(self, "_cam_menu_choice_actions", {}).get(key, []):
            action.setChecked(action.text() == value)

        if key == "direction":
            self._refresh_cam_detail_readouts()


        self.statusBar().showMessage(
            f"Toolpath {key.replace('_', ' ')}: {value}",
            2500,
        )

    def _toolpath_design_advanced(self) -> None:
        form = _ActionForm(self, "Advanced Toolpath Design")
        form.add_double(
            "safe_z",
            "Global Safe Z",
            float(self._settings.value("cam/safe_z_mm", 1.5)),
            minimum=0.05,
            maximum=100.0,
            decimals=3,
            step=0.1,
            suffix=" mm",
        )
        form.add_double(
            "cut_depth",
            "Overall cut depth (0 = design/model)",
            float(self._settings.value("cam/overall_depth_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            decimals=3,
            step=0.25,
            suffix=" mm",
        )
        form.add_double(
            "feed",
            "Cut feed",
            float(self._settings.value("cam/feed_mm_min", 1000.0)),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm/min",
        )
        form.add_double(
            "plunge",
            "Plunge feed",
            float(self._settings.value("cam/plunge_mm_min", 300.0)),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm/min",
        )
        form.add_double(
            "stepdown",
            "Depth per pass",
            float(self._settings.value("cam/stepdown_mm", 2.0)),
            minimum=0.05,
            maximum=1000.0,
            suffix=" mm",
        )
        form.add_double(
            "pocket_stepover",
            "2D pocket stepover",
            float(self._settings.value("cam/stepover_percent", 45.0)),
            minimum=1.0,
            maximum=100.0,
            decimals=1,
            step=1.0,
            suffix=" %",
        )
        form.add_double(
            "finish_stepover",
            "3D detail stepover",
            detail_stepover_fraction(self._cam_detail) * 100.0,
            minimum=4.0,
            maximum=20.0,
            decimals=1,
            step=0.5,
            suffix=" % of cutter",
        )
        form.add_double(
            "padding",
            "Relief / path padding",
            float(self._settings.value("cam/padding_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            decimals=3,
            step=0.5,
            suffix=" mm",
        )
        form.add_double(
            "bit_length",
            "Usable bit length (0 = not enforced)",
            float(self._settings.value("cam/usable_bit_length_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            decimals=3,
            step=0.5,
            suffix=" mm",
        )
        form.add_double(
            "tab_height",
            "Tab height",
            float(self._settings.value("cam/tab_height_mm", 2.0)),
            minimum=0.1,
            maximum=100.0,
            decimals=3,
            step=0.25,
            suffix=" mm",
        )
        form.add_double(
            "tab_width",
            "Tab width",
            float(self._settings.value("cam/tab_width_mm", 6.0)),
            minimum=0.5,
            maximum=100.0,
            decimals=3,
            step=0.5,
            suffix=" mm",
        )
        form.add_int(
            "tab_count",
            "Tab count",
            int(self._settings.value("cam/tab_count", 4)),
            minimum=1,
            maximum=32,
        )
        form.add_double(
            "local_clearance",
            "Smart-link local clearance",
            float(self._settings.value("cam/local_link_clearance_mm", 0.5)),
            minimum=0.05,
            maximum=25.0,
            decimals=3,
            step=0.1,
            suffix=" mm",
        )
        form.add_double(
            "link_tolerance",
            "Direct-link surface tolerance",
            float(self._settings.value("cam/direct_link_tolerance_mm", 0.02)),
            minimum=0.0,
            maximum=5.0,
            decimals=3,
            step=0.01,
            suffix=" mm",
        )
        form.add_double(
            "ramp_angle",
            "Custom ramp angle",
            float(self._settings.value("cam/custom_ramp_angle_deg", 10.0)),
            minimum=0.5,
            maximum=89.0,
            decimals=1,
            step=0.5,
            suffix="°",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        values = {
            "cam/safe_z_mm": form.value("safe_z"),
            "cam/overall_depth_mm": form.value("cut_depth"),
            "cam/feed_mm_min": form.value("feed"),
            "cam/plunge_mm_min": form.value("plunge"),
            "cam/stepdown_mm": form.value("stepdown"),
            "cam/stepover_percent": form.value("pocket_stepover"),
            "cam/padding_mm": form.value("padding"),
            "cam/usable_bit_length_mm": form.value("bit_length"),
            "cam/tab_height_mm": form.value("tab_height"),
            "cam/tab_width_mm": form.value("tab_width"),
            "cam/tab_count": form.value("tab_count"),
            "cam/local_link_clearance_mm": form.value("local_clearance"),
            "cam/direct_link_tolerance_mm": form.value("link_tolerance"),
            "cam/custom_ramp_angle_deg": form.value("ramp_angle"),
        }
        for setting_key, setting_value in values.items():
            self._settings.setValue(setting_key, setting_value)

        requested_fraction = float(form.value("finish_stepover")) / 100.0
        self._set_cam_detail(
            detail_for_stepover_fraction(requested_fraction),
            mark_custom=True,
        )
        self._settings.sync()
        self.statusBar().showMessage("Advanced toolpath settings saved", 3000)

    def _quality_stepover_fraction(self) -> float:
        return detail_stepover_fraction(self._cam_detail)

    def _ramp_angle(self) -> float | None:
        if self._cam_entry == "Ramp 5°":
            return 5.0
        if self._cam_entry == "Ramp 20°":
            return 20.0
        if self._cam_entry == "Custom Ramp":
            return float(
                self._settings.value("cam/custom_ramp_angle_deg", 10.0)
            )
        return None

    def _milling_direction(self) -> MillingDirection:
        return {
            "Climb (CCW)": MillingDirection.CLIMB,
            "Conventional (CW)": MillingDirection.CONVENTIONAL,
        }.get(self._cam_milling, MillingDirection.DEFAULT)

    def _relief_style(self) -> ReliefStyle:
        return {
            "Rectangle Relief": ReliefStyle.RECTANGLE,
            "Full Depth Cutout": ReliefStyle.FULL_DEPTH,
        }.get(self._cam_3d_cut_style, ReliefStyle.MODEL_BOUNDARY)

    def _link_mode(self) -> RasterLinkMode:
        return {
            "Local Lift": RasterLinkMode.LOCAL_LIFT,
            "Full Retract": RasterLinkMode.FULL_RETRACT,
        }.get(self._cam_linking, RasterLinkMode.SMART)

    def _raster_axis_for_mesh(self, mesh) -> RasterAxis:
        direction = self._cam_direction
        if direction == "Raster Y":
            return RasterAxis.Y
        if direction == "Raster 45°":
            return RasterAxis.DIAGONAL_45
        if direction == "Raster 135°":
            return RasterAxis.DIAGONAL_135
        if direction == "Raster X":
            return RasterAxis.X

        bounds = np.asarray(mesh.bounds, dtype=float)
        span = bounds[1, :2] - bounds[0, :2]
        return RasterAxis.X if span[0] >= span[1] else RasterAxis.Y

    def _pocket_strategy_for_bounds(self, bounds: np.ndarray) -> PocketStrategy:
        if self._cam_direction == "Offset":
            return PocketStrategy.OFFSET
        if self._cam_direction == "Raster Y":
            return PocketStrategy.RASTER_Y
        if self._cam_direction == "Raster X":
            return PocketStrategy.RASTER_X

        span = np.asarray(bounds, dtype=float)[1, :2] - np.asarray(
            bounds,
            dtype=float,
        )[0, :2]
        return (
            PocketStrategy.RASTER_X
            if span[0] >= span[1]
            else PocketStrategy.RASTER_Y
        )

    def _select_cam_operation(self, operation: str) -> None:
        self._active_cam_operation = operation
        labels = {
            "profile": "Profile",
            "silhouette": "Silhouette",
            "pocket": "Pocket",
            "surface": "Surface / Face",
            "vcarve": "V-Carve",
            "engrave": "Engrave",
            "drill": "Drill Features",
            "center_drill": "Center Drill",
            "rough": "3D Rough",
            "finish": "3D Finish",
            "height_map": "Height Map",
            "rest": "3D Rest",
            "waterline": "3D Waterline",
        }

        for name, button in getattr(
            self,
            "_cam_operation_buttons",
            {},
        ).items():
            button.blockSignals(True)
            try:
                button.setChecked(name == operation)
            finally:
                button.blockSignals(False)

        cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        cutter_name = cutter.name if isinstance(cutter, Cutter) else "selected cutter"
        self._set_activity_info(
            f"Toolpath operation\n{labels.get(operation, operation)}\n\n"
            f"Cutter: {cutter_name}\n"
            "Review all generation requirements, then press Generate Toolpaths."
        )
        self._sync_cam_control_relevance()
        self.statusBar().showMessage(
            f"Toolpath operation: {labels.get(operation, operation)}",
            3000,
        )

    def _sync_cam_control_relevance(self) -> None:
        operation = self._active_cam_operation
        is_3d = operation in {
            "rough",
            "finish",
            "height_map",
            "rest",
            "waterline",
        }
        uses_cut_type = operation in {"profile", "pocket", "engrave"}
        uses_entry = operation not in {
            "rough",
            "finish",
            "height_map",
            "rest",
            "waterline",
            "drill",
            "center_drill",
        }
        uses_milling = operation in {
            "profile",
            "silhouette",
            "pocket",
            "surface",
            "engrave",
        }
        uses_direction = is_3d or operation in {"pocket", "surface"}
        uses_detail = is_3d or operation == "vcarve"

        for combo in self._cam_selector_widgets.get("cut_type", []):
            combo.setEnabled(uses_cut_type)
        for combo in self._cam_selector_widgets.get("3d_cut_style", []):
            combo.setEnabled(is_3d)
        for combo in self._cam_selector_widgets.get("direction", []):
            combo.setEnabled(uses_direction)
        for combo in self._cam_selector_widgets.get("entry", []):
            combo.setEnabled(uses_entry)
        for combo in self._cam_selector_widgets.get("milling", []):
            combo.setEnabled(uses_milling)
        for combo in self._cam_selector_widgets.get("linking", []):
            combo.setEnabled(True)

        for widget in self._cam_detail_widgets:
            widget.setEnabled(uses_detail)

        if self._tabs_button is not None:
            self._tabs_button.setEnabled(operation in {"profile", "silhouette"})

    def _toggle_tabs_operation(self) -> None:
        self._tabs_enabled = not self._tabs_enabled
        self._settings.setValue("cam/tabs_enabled", self._tabs_enabled)
        self._settings.sync()
        if self._tabs_button is not None:
            self._tabs_button.setChecked(self._tabs_enabled)
        self.statusBar().showMessage(
            f"Profile tabs {'enabled' if self._tabs_enabled else 'disabled'}",
            2500,
        )

    def _cam_settings(
        self,
        bounds: np.ndarray,
        mesh,
    ) -> BasicCamSettings:
        cut_depth = float(self._settings.value("cam/overall_depth_mm", 0.0))
        return BasicCamSettings(
            safe_z_mm=float(self._settings.value("cam/safe_z_mm", 1.5)),
            feed_mm_min=float(self._settings.value("cam/feed_mm_min", 1000.0)),
            plunge_feed_mm_min=float(
                self._settings.value("cam/plunge_mm_min", 300.0)
            ),
            max_stepdown_mm=float(
                self._settings.value("cam/stepdown_mm", 2.0)
            ),
            stepover_fraction=max(
                0.01,
                min(
                    1.0,
                    float(self._settings.value("cam/stepover_percent", 45.0))
                    / 100.0,
                ),
            ),
            finish_stepover_fraction=self._quality_stepover_fraction(),
            overall_depth_mm=cut_depth if cut_depth > 0.0 else None,
            padding_mm=float(self._settings.value("cam/padding_mm", 0.0)),
            usable_bit_length_mm=(
                float(self._settings.value("cam/usable_bit_length_mm", 0.0))
                or None
            ),
            tab_height_mm=float(
                self._settings.value("cam/tab_height_mm", 2.0)
            ),
            tab_width_mm=float(
                self._settings.value("cam/tab_width_mm", 6.0)
            ),
            tab_count=int(self._settings.value("cam/tab_count", 4)),
            tabs_enabled=self._tabs_enabled,
            milling_direction=self._milling_direction(),
            pocket_strategy=self._pocket_strategy_for_bounds(bounds),
            relief_style=self._relief_style(),
            raster_axis=self._raster_axis_for_mesh(mesh),
            raster_link_mode=self._link_mode(),
            local_link_clearance_mm=float(
                self._settings.value("cam/local_link_clearance_mm", 0.5)
            ),
            direct_link_tolerance_mm=float(
                self._settings.value("cam/direct_link_tolerance_mm", 0.02)
            ),
            ramp_angle_deg=self._ramp_angle(),
        )

    @staticmethod
    def _cam_operation_title(operation: str) -> str:
        return {
            "profile": "Profile",
            "silhouette": "Silhouette",
            "pocket": "Pocket",
            "surface": "Surface / Face",
            "vcarve": "V-Carve",
            "engrave": "Engrave",
            "drill": "Drill Features",
            "center_drill": "Center Drill",
            "rough": "3D Rough",
            "finish": "3D Finish",
            "height_map": "Height Map",
            "rest": "3D Rest",
            "waterline": "3D Waterline",
        }.get(operation, operation.replace("_", " ").title())

    def _update_toolpath_progress(
        self,
        fraction: float,
        status_text: str,
    ) -> None:
        """Update determinate CAM progress and keep the UI repainting."""

        fraction = max(0.0, min(1.0, float(fraction)))
        percent = round(fraction * 100.0)
        text = str(status_text).strip() or "Generating toolpaths"

        bars = [
            getattr(self, "toolpath_progress", None),
            self._toolpath_dialog_progress,
        ]
        changed = (
            percent != self._toolpath_progress_last_value
            or text != self._toolpath_progress_last_text
        )
        for bar in bars:
            if bar is None:
                continue
            bar.setRange(0, 100)
            bar.setValue(percent)
            bar.setFormat(f"{text} · %p%")
            bar.show()

        self._toolpath_progress_last_value = percent
        self._toolpath_progress_last_text = text
        if changed:
            self.statusBar().showMessage(f"{text} — {percent}%")

    def _finish_toolpath_progress(
        self,
        *,
        success: bool,
        message: str,
    ) -> None:
        bars = [
            getattr(self, "toolpath_progress", None),
            self._toolpath_dialog_progress,
        ]
        value = 100 if success else self._toolpath_progress_last_value
        value = max(0, value)
        for bar in bars:
            if bar is None:
                continue
            bar.setRange(0, 100)
            bar.setValue(value)
            bar.setFormat(f"{message} · %p%")
            bar.show()

        status_bar = getattr(self, "toolpath_progress", None)
        if status_bar is not None and success:
            QTimer.singleShot(
                1800,
                lambda bar=status_bar: (
                    bar.hide()
                    if bar.value() == 100
                    else None
                ),
            )

    def _show_toolpath_generation_dialog(self) -> None:
        dialog = self._build_toolpath_generation_dialog()
        dialog.exec()

    def _calculate_toolpath(self) -> None:
        """Compatibility entry point: calculation now begins with review."""

        self._show_toolpath_generation_dialog()

    def _calculate_toolpath_now(self) -> bool:
        """Submit CAM to a separate Python process; never block the Qt loop."""

        if self._background_job is not None:
            self.statusBar().showMessage("Another operation is running", 4000)
            return False
        # Hidden source shapes must never contribute duplicate/obsolete CNC cuts.
        items = [item for item in self.project.items if item.visible and item.mesh is not None]
        cutter = self.tool_combo.currentData()
        if not isinstance(cutter, Cutter):
            self.statusBar().showMessage("Select a valid cutter", 4000)
            return False

        operation = self._active_cam_operation
        if not items and operation != "surface":
            self.statusBar().showMessage(
                "Add geometry before generating this operation", 4000
            )
            return False

        # Only small bounds and QSettings are read on the GUI thread. Mesh
        # transforms, geometry, CAM and path ordering happen in the process.
        specs = []
        for item in items:
            bounds = item.transformed_bounds_mm()
            if bounds is None:
                continue
            settings = self._cam_settings(
                bounds,
                type("_Bounds", (), {"bounds": bounds})(),
            )
            specs.append((item, settings))

        stock = self.project.stock
        stock_bounds = np.array(
            ((0.0, 0.0, -stock.thickness_mm),
             (stock.width_mm, stock.height_mm, 0.0)),
            dtype=float,
        )
        stock_settings = None
        silhouette_settings = None
        if operation == "surface":
            stock_settings = self._cam_settings(
                stock_bounds,
                type("_Bounds", (), {"bounds": stock_bounds})(),
            )
        if operation == "silhouette" and specs:
            bounds = np.vstack(
                (
                    np.vstack([item.transformed_bounds_mm()[0] for item, _ in specs]).min(axis=0),
                    np.vstack([item.transformed_bounds_mm()[1] for item, _ in specs]).max(axis=0),
                )
            )
            silhouette_settings = self._cam_settings(
                bounds,
                type("_Bounds", (), {"bounds": bounds})(),
            )

        if operation == "rest" and not self.project.toolpaths:
            self.statusBar().showMessage(
                "Generate and append roughing/finishing before 3D Rest.", 7000
            )
            return False
        append_to_job = bool(
            self.project.toolpaths and (
                operation == "rest" or self._cam_append_to_job
            )
        )
        self._cam_append_to_job = False
        request = CamRequest(
            operation=operation,
            cutter=cutter,
            cut_type=self._cam_cut_type,
            thickness_mm=stock.thickness_mm,
            stock_width_mm=stock.width_mm,
            stock_height_mm=stock.height_mm,
            settings_by_item=specs,
            stock_settings=stock_settings,
            silhouette_settings=silhouette_settings,
            previous_toolpaths=(
                list(self.project.toolpaths) if append_to_job else None
            ),
            rest_min_remaining_mm=float(
                self._settings.value("cam/rest_min_remaining_mm", 0.15)
            ),
            rest_grid_spacing_mm=float(
                self._settings.value("cam/rest_grid_spacing_mm", 0.75)
            ),
        )
        self._toolpath_progress_last_value = -1
        self._toolpath_progress_last_text = ""
        self._update_toolpath_progress(
            0, f"Preparing {self._cam_operation_title(operation)}"
        )

        def finished(payload: object) -> None:
            if not isinstance(payload, dict):
                raise TypeError("Invalid CAM worker result.")
            paths = payload["toolpaths"]
            if self._simulation_timer.isActive():
                self._simulation_timer.stop()
            if self._simulation_button is not None:
                self._simulation_button.setChecked(False)
            preview = self._toolpath_preview_window
            if preview is not None:
                preview.close()
                self._toolpath_preview_window = None

            self._before_ribbon_mutation(f"calculate {operation}")
            self.project.toolpaths = paths
            self._toolpaths_stale_reason = None
            self._prepared_toolpath_geometry = payload["render_geometry"]
            self._prepared_toolpath_stats = payload
            self.viewport.prepare_toolpath_render_cache(
                paths, self._prepared_toolpath_geometry
            )
            self.viewport.set_toolpaths_visible(True)
            self.viewport.set_simulation_fraction(1.0)
            self.viewport.update()
            self._after_ribbon_mutation(f"calculate {operation}", True)

            count = int(payload["object_count"])
            self._set_activity_info(
                f"Toolpaths ready\n{payload['summary']}\n\n"
                f"Objects: {count}\n"
                f"Cutter: {cutter.name}\n"
                f"Paths: {len(paths):,}\n"
                f"Moves: {int(payload['moves']):,}\n"
                f"Cut distance: {float(payload['cut_mm']):.1f} mm\n"
                f"Rapid distance: {float(payload['rapid_mm']):.1f} mm\n"
                f"Estimated cutting: {float(payload['minutes']):.1f} min"
            )
            self._sync_toolpath_output_state()
            self._finish_toolpath_progress(
                success=True, message="Toolpaths ready"
            )
            self.statusBar().showMessage(
                f"Generated {len(paths)} toolpaths", 6000
            )

        def failed(message: str) -> None:
            self._set_activity_info(f"Toolpath calculation failed\n{message}")
            self._finish_toolpath_progress(
                success=False, message="Generation failed"
            )
            self.statusBar().showMessage(f"Toolpath failed: {message}", 9000)

        return self._start_background_job(
            f"{self._cam_operation_title(operation)} toolpaths",
            request=request,
            on_done=finished,
            on_failed=failed,
            cam_progress=True,
        )

    def _preview_toolpaths(self) -> None:
        if not self.project.toolpaths:
            self.statusBar().showMessage("No calculated toolpaths to preview", 4000)
            return

        existing = self._toolpath_preview_window
        if existing is not None and existing.isVisible():
            existing.showNormal()
            existing.raise_()
            existing.activateWindow()
            return

        window = ToolpathPreviewWindow(
            toolpaths=list(self.project.toolpaths),
            stock=self.project.stock,
            post_settings=self._grbl_post_settings(),
            source_names=self._toolpath_source_names(self.project.toolpaths),
            render_geometry_data=self._prepared_toolpath_geometry,
            estimated_minutes=(
                float(self._prepared_toolpath_stats["minutes"])
                if self._prepared_toolpath_stats is not None
                else None
            ),
            parent=self,
        )
        window.destroyed.connect(
            lambda _obj=None: setattr(
                self,
                "_toolpath_preview_window",
                None,
            )
        )
        self._toolpath_preview_window = window
        window.show()
        window.raise_()
        window.activateWindow()
        self.statusBar().showMessage("Opened toolpath backplot preview", 3000)

    # ------------------------------------------------------------------
    # Cutter tools / feeds and speeds
    # ------------------------------------------------------------------
    def _tool_to_dict(self, tool: Cutter) -> dict[str, object]:
        return {
            "name": tool.name,
            "tool_type": tool.tool_type.value,
            "diameter_mm": tool.diameter_mm,
            "angle_deg": tool.angle_deg,
            "tip_diameter_mm": tool.tip_diameter_mm,
            "taper_angle_deg": tool.taper_angle_deg,
            "ball_radius_mm": tool.ball_radius_mm,
            "profile_points": tool.profile_points,
        }

    def _tool_from_dict(self, value: object) -> Cutter | None:
        if not isinstance(value, dict):
            return None
        try:
            profile_raw = value.get("profile_points")
            profile = None
            if isinstance(profile_raw, list):
                profile = tuple(
                    (float(point[0]), float(point[1]))
                    for point in profile_raw
                )
            return Cutter(
                name=str(value["name"]),
                tool_type=ToolType(str(value["tool_type"])),
                diameter_mm=float(value["diameter_mm"]),
                angle_deg=(
                    None
                    if value.get("angle_deg") is None
                    else float(value["angle_deg"])
                ),
                tip_diameter_mm=float(value.get("tip_diameter_mm", 0.0)),
                taper_angle_deg=(
                    None
                    if value.get("taper_angle_deg") is None
                    else float(value["taper_angle_deg"])
                ),
                ball_radius_mm=(
                    None
                    if value.get("ball_radius_mm") is None
                    else float(value["ball_radius_mm"])
                ),
                profile_points=profile,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _load_custom_tools(self) -> list[Cutter]:
        raw = self._settings.value("tools/custom_json", "[]")
        try:
            payload = json.loads(str(raw))
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        result: list[Cutter] = []
        for value in payload:
            tool = self._tool_from_dict(value)
            if tool is not None:
                result.append(tool)
        return result

    def _save_custom_tools(self) -> None:
        self._settings.setValue(
            "tools/custom_json",
            json.dumps([self._tool_to_dict(tool) for tool in self._custom_tools]),
        )
        self._settings.sync()

    def _all_tools(self) -> list[Cutter]:
        return [*DEFAULT_TOOLS, *self._custom_tools]

    def _reload_tool_combo(self, preferred_name: str | None = None) -> None:
        if not hasattr(self, "tool_combo"):
            return
        current = preferred_name
        if current is None:
            selected = self.tool_combo.currentData()
            current = selected.name if isinstance(selected, Cutter) else None
        self.tool_combo.clear()
        for tool in self._all_tools():
            self.tool_combo.addItem(tool.name, tool)
        if current:
            for index in range(self.tool_combo.count()):
                tool = self.tool_combo.itemData(index)
                if isinstance(tool, Cutter) and tool.name == current:
                    self.tool_combo.setCurrentIndex(index)
                    break

    def _show_tool_library(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Tool Library")
        dialog.resize(620, 380)
        layout = QHBoxLayout(dialog)
        tool_list = QListWidget()
        details = QLabel()
        details.setWordWrap(True)
        details.setMinimumWidth(300)
        layout.addWidget(tool_list, 1)
        layout.addWidget(details, 1)

        tools = self._all_tools()
        for tool in tools:
            tool_list.addItem(tool.name)

        def update_details(row: int) -> None:
            if not 0 <= row < len(tools):
                details.clear()
                return
            tool = tools[row]
            text = (
                f"{tool.name}\n\n"
                f"Type: {tool.tool_type.value.replace('_', ' ').title()}\n"
                f"Diameter: {tool.diameter_mm:g} mm"
            )
            if tool.angle_deg is not None:
                text += f"\nIncluded angle: {tool.angle_deg:g}°"
            if tool.tip_diameter_mm:
                text += f"\nTip diameter: {tool.tip_diameter_mm:g} mm"
            if tool.profile_points:
                text += "\n\nCustom profile:\n" + "\n".join(
                    f"r {radius:g} → h {height:g} mm"
                    for radius, height in tool.profile_points
                )
            details.setText(text)

        tool_list.currentRowChanged.connect(update_details)
        tool_list.setCurrentRow(0)
        dialog.exec()

    def _new_tool(self) -> None:
        form = _ActionForm(self, "New Tool")
        form.add_line("name", "Name", "Custom End Mill")
        type_names = [
            "Flat End Mill",
            "Ball Nose",
            "V-Bit",
            "Engraving Cone",
            "Tapered Ball Nose",
        ]
        form.add_combo("type", "Type", type_names, type_names[0])
        form.add_double("diameter", "Diameter", 3.175, minimum=0.01, suffix=" mm")
        form.add_double("angle", "Included angle", 60.0, minimum=1.0, maximum=179.0, suffix="°")
        form.add_double("tip", "Tip diameter", 0.0, minimum=0.0, suffix=" mm")
        form.add_double("taper", "Taper angle", 5.0, minimum=0.1, maximum=89.0, suffix="°")
        form.add_double("ball", "Ball radius", 1.0, minimum=0.01, suffix=" mm")
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        type_map = {
            "Flat End Mill": ToolType.FLAT_END_MILL,
            "Ball Nose": ToolType.BALL_NOSE,
            "V-Bit": ToolType.V_BIT,
            "Engraving Cone": ToolType.ENGRAVING_CONE,
            "Tapered Ball Nose": ToolType.TAPERED_BALL_NOSE,
        }
        tool_type = type_map[str(form.value("type"))]
        diameter = float(form.value("diameter"))
        kwargs: dict[str, object] = {}
        if tool_type in {ToolType.V_BIT, ToolType.ENGRAVING_CONE}:
            kwargs["angle_deg"] = float(form.value("angle"))
            kwargs["tip_diameter_mm"] = float(form.value("tip"))
        elif tool_type is ToolType.TAPERED_BALL_NOSE:
            kwargs["ball_radius_mm"] = float(form.value("ball"))
            kwargs["taper_angle_deg"] = float(form.value("taper"))

        try:
            tool = Cutter(
                str(form.value("name")).strip() or "Custom Tool",
                tool_type,
                diameter,
                **kwargs,
            )
        except ValueError as exc:
            self.statusBar().showMessage(f"Tool invalid: {exc}", 5000)
            return
        self._custom_tools.append(tool)
        self._save_custom_tools()
        self._reload_tool_combo(tool.name)
        self.statusBar().showMessage(f"Added tool: {tool.name}", 3000)

    def _new_custom_profile_tool(self) -> None:
        form = _ActionForm(self, "Custom Cutter Profile")
        form.add_line("name", "Name", "Custom Profile")
        form.add_double("diameter", "Diameter", 6.0, minimum=0.01, suffix=" mm")
        form.add_line(
            "points",
            "Radius:height points",
            "0:0, 1:0.15, 3:1.5",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            points = tuple(
                (
                    float(pair.split(":", 1)[0].strip()),
                    float(pair.split(":", 1)[1].strip()),
                )
                for pair in str(form.value("points")).split(",")
            )
            tool = Cutter(
                str(form.value("name")).strip() or "Custom Profile",
                ToolType.CUSTOM,
                float(form.value("diameter")),
                profile_points=points,
            )
        except (IndexError, ValueError) as exc:
            self.statusBar().showMessage(f"Custom profile invalid: {exc}", 6000)
            return
        self._custom_tools.append(tool)
        self._save_custom_tools()
        self._reload_tool_combo(tool.name)
        self.statusBar().showMessage(f"Added custom profile: {tool.name}", 3000)

    def _feeds_speeds_calculator(self) -> None:
        cutter = self.tool_combo.currentData()
        if not isinstance(cutter, Cutter):
            return
        form = _ActionForm(self, "Feeds & Speeds Calculator")
        form.add_int("rpm", "Spindle RPM", 18000, minimum=100, maximum=100000)
        form.add_int("flutes", "Flutes", 2, minimum=1, maximum=12)
        form.add_double(
            "chipload",
            "Chip load / tooth",
            0.03,
            minimum=0.001,
            maximum=2.0,
            decimals=4,
            step=0.005,
            suffix=" mm",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        rpm = int(form.value("rpm"))
        flutes = int(form.value("flutes"))
        chipload = float(form.value("chipload"))
        feed = rpm * flutes * chipload
        surface_speed = pi * cutter.diameter_mm * rpm / 1000.0
        self._set_activity_info(
            f"Feeds & speeds estimate\n{cutter.name}\n\n"
            f"Feed: {feed:.0f} mm/min\n"
            f"Spindle: {rpm:,} RPM\n"
            f"Chip load: {chipload:g} mm/tooth\n"
            f"Surface speed: {surface_speed:.1f} m/min\n\n"
            "Verify against the cutter and material manufacturer's limits."
        )
        self.statusBar().showMessage(f"Calculated feed: {feed:.0f} mm/min", 5000)

    # ------------------------------------------------------------------
    # Machine
    # ------------------------------------------------------------------
    def _machine_profiles(self) -> tuple[list[MachineProfile], str]:
        raw = str(self._settings.value("machine/profiles_v1", ""))
        try:
            profiles, active_name = profiles_from_json(raw)
        except (TypeError, ValueError):
            profiles, active_name = [], None

        if not profiles:
            legacy = MachineProfile(
                name=str(
                    self._settings.value(
                        "machine/name",
                        "Onefinity / GRBL",
                    )
                ),
                port=str(self._settings.value("machine/port", "")),
                baud_rate=int(self._settings.value("machine/baud", 115200)),
                work_x_mm=float(
                    self._settings.value("machine/work_x_mm", 816.0)
                ),
                work_y_mm=float(
                    self._settings.value("machine/work_y_mm", 816.0)
                ),
                work_z_mm=float(
                    self._settings.value("machine/work_z_mm", 133.0)
                ),
            )
            profiles = [legacy]
            active_name = legacy.name

        names = {profile.name for profile in profiles}
        if active_name not in names:
            active_name = profiles[0].name
        return profiles, active_name

    def _save_machine_profiles(
        self,
        profiles: list[MachineProfile],
        active_name: str,
    ) -> None:
        if not profiles:
            raise ValueError("At least one machine profile is required.")
        names = {profile.name for profile in profiles}
        if active_name not in names:
            raise ValueError("Active machine profile is missing.")

        self._settings.setValue(
            "machine/profiles_v1",
            profiles_to_json(profiles, active_name=active_name),
        )
        active = next(
            profile for profile in profiles if profile.name == active_name
        )
        # Mirror the active profile into the older keys for compatibility with
        # existing installs and any external scripts reading these settings.
        self._settings.setValue("machine/name", active.name)
        self._settings.setValue("machine/port", active.port)
        self._settings.setValue("machine/baud", active.baud_rate)
        self._settings.setValue("machine/work_x_mm", active.work_x_mm)
        self._settings.setValue("machine/work_y_mm", active.work_y_mm)
        self._settings.setValue("machine/work_z_mm", active.work_z_mm)
        self._settings.sync()

    def _active_machine_profile(self) -> MachineProfile:
        profiles, active_name = self._machine_profiles()
        return next(
            profile for profile in profiles if profile.name == active_name
        )

    def _select_machine_profile(self) -> None:
        profiles, active_name = self._machine_profiles()
        names = [profile.name for profile in profiles]
        selected, accepted = QInputDialog.getItem(
            self,
            "Machine Profile",
            "Active machine",
            names,
            names.index(active_name),
            False,
        )
        if not accepted or not selected:
            return
        self._save_machine_profiles(profiles, str(selected))
        self.statusBar().showMessage(
            f"Active machine: {selected}",
            3000,
        )

    def _delete_machine_profile(self) -> None:
        profiles, active_name = self._machine_profiles()
        if len(profiles) <= 1:
            self.statusBar().showMessage(
                "Keep at least one machine profile",
                4000,
            )
            return
        names = [profile.name for profile in profiles]
        selected, accepted = QInputDialog.getItem(
            self,
            "Delete Machine Profile",
            "Profile",
            names,
            names.index(active_name),
            False,
        )
        if not accepted or not selected:
            return
        answer = QMessageBox.question(
            self,
            "Delete Machine Profile",
            f"Delete machine profile {selected!r}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        remaining = [
            profile for profile in profiles if profile.name != selected
        ]
        new_active = (
            active_name
            if active_name != selected
            else remaining[0].name
        )
        self._save_machine_profiles(remaining, new_active)
        self.statusBar().showMessage(
            f"Deleted machine profile: {selected}",
            3000,
        )

    def _machine_profile(self) -> None:
        profiles, active_name = self._machine_profiles()
        active = next(
            profile for profile in profiles if profile.name == active_name
        )
        ports = MachineController.available_ports()
        port_names = [name for name, _label in ports]
        choices = port_names or ([active.port] if active.port else [""])
        if active.port and active.port not in choices:
            choices.insert(0, active.port)

        form = _ActionForm(self, "Machine Profile")
        form.add_line("name", "Profile name", active.name)
        form.add_combo(
            "port",
            "Serial port",
            choices,
            active.port,
            editable=True,
        )
        form.add_int(
            "baud",
            "Baud rate",
            active.baud_rate,
            minimum=1200,
            maximum=2_000_000,
        )
        form.add_double(
            "work_x",
            "X travel",
            active.work_x_mm,
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double(
            "work_y",
            "Y travel",
            active.work_y_mm,
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double(
            "work_z",
            "Z travel",
            active.work_z_mm,
            minimum=1.0,
            suffix=" mm",
        )
        form.add_check(
            "parking",
            "Park after G-code",
            active.parking_enabled,
        )
        form.add_double(
            "park_x",
            "Park X",
            active.park_x_mm,
            minimum=-100000.0,
            maximum=100000.0,
            suffix=" mm",
        )
        form.add_double(
            "park_y",
            "Park Y",
            active.park_y_mm,
            minimum=-100000.0,
            maximum=100000.0,
            suffix=" mm",
        )
        form.add_double(
            "park_z",
            "Park Z clearance",
            active.park_z_mm,
            minimum=0.0,
            maximum=100000.0,
            suffix=" mm",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        edited = MachineProfile(
            name=str(form.value("name")).strip() or active.name,
            port=str(form.value("port")).strip(),
            baud_rate=int(form.value("baud")),
            work_x_mm=float(form.value("work_x")),
            work_y_mm=float(form.value("work_y")),
            work_z_mm=float(form.value("work_z")),
            parking_enabled=bool(form.value("parking")),
            park_x_mm=float(form.value("park_x")),
            park_y_mm=float(form.value("park_y")),
            park_z_mm=float(form.value("park_z")),
        )
        try:
            edited.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Machine Profile", str(exc))
            return

        # Renaming creates/replaces a named profile without losing the others.
        remaining = [
            profile
            for profile in profiles
            if profile.name not in {active.name, edited.name}
        ]
        remaining.append(edited)
        remaining.sort(key=lambda profile: profile.name.casefold())
        self._save_machine_profiles(remaining, edited.name)
        self.statusBar().showMessage(
            f"Machine profile saved: {edited.name}",
            3000,
        )

    def _machine_work_area(self) -> None:
        profile = self._active_machine_profile()
        form = _ActionForm(self, "Machine Work Area")
        form.add_double(
            "x",
            "X travel",
            profile.work_x_mm,
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double(
            "y",
            "Y travel",
            profile.work_y_mm,
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double(
            "z",
            "Z travel",
            profile.work_z_mm,
            minimum=1.0,
            suffix=" mm",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        profiles, active_name = self._machine_profiles()
        updated = MachineProfile(
            name=profile.name,
            port=profile.port,
            baud_rate=profile.baud_rate,
            work_x_mm=float(form.value("x")),
            work_y_mm=float(form.value("y")),
            work_z_mm=float(form.value("z")),
            parking_enabled=profile.parking_enabled,
            park_x_mm=profile.park_x_mm,
            park_y_mm=profile.park_y_mm,
            park_z_mm=profile.park_z_mm,
        )
        profiles = [
            updated if candidate.name == active_name else candidate
            for candidate in profiles
        ]
        self._save_machine_profiles(profiles, active_name)
        self.statusBar().showMessage("Machine work area saved", 3000)

    def _work_zero_mode(self) -> None:
        form = _ActionForm(self, "XY Work Zero")
        labels = ["Front Left Corner", "Center of Stock"]
        current = (
            "Center of Stock"
            if self.project.stock.xy_zero == "center"
            else "Front Left Corner"
        )
        form.add_combo("mode", "XY zero", labels, current)
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        mode = (
            "center"
            if form.value("mode") == "Center of Stock"
            else "bottom_left"
        )
        if mode == self.project.stock.xy_zero:
            return
        self._before_ribbon_mutation("change work zero")
        self.project.stock.xy_zero = mode
        self._after_ribbon_mutation("change work zero", True)
        self.viewport.update()
        self.statusBar().showMessage(
            "XY work zero set to "
            + ("stock center" if mode == "center" else "front-left corner"),
            3500,
        )

    def _machine_origin(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage(
                "Connect to the machine before setting origin",
                5000,
            )
            return
        form = _ActionForm(self, "Set Work Origin")
        form.add_check("x", "Set X = 0", True)
        form.add_check("y", "Set Y = 0", True)
        form.add_check("z", "Set Z = 0", False)
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        axes = [
            axis
            for axis in ("X", "Y", "Z")
            if bool(form.value(axis.lower()))
        ]
        if not axes:
            return
        command = "G10 L20 P1 " + " ".join(f"{axis}0" for axis in axes)
        if self.machine_controller.send_line(command):
            self.statusBar().showMessage(
                f"Set work origin: {', '.join(axes)}",
                4000,
            )

    def _home_machine(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage(
                "Connect to the machine before homing",
                4000,
            )
            return
        if self.machine_controller.send_line("$H"):
            self.statusBar().showMessage("Machine homing started", 4000)

    def _go_to_work_zero(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage(
                "Connect to the machine before moving to work zero",
                4000,
            )
            return
        safe_z = float(self._settings.value("cam/safe_z_mm", 1.5))
        self.machine_controller.send_line("G90")
        self.machine_controller.send_line(f"G0 Z{safe_z:g}")
        self.machine_controller.send_line("G0 X0 Y0")
        self.statusBar().showMessage("Moving to XY work zero", 4000)

    def _park_machine(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage(
                "Connect to the machine before parking",
                4000,
            )
            return
        profile = self._active_machine_profile()
        clearance = max(
            profile.park_z_mm,
            float(self._settings.value("cam/safe_z_mm", 1.5)),
        )
        self.machine_controller.send_line("G90")
        self.machine_controller.send_line(f"G0 Z{clearance:g}")
        self.machine_controller.send_line(
            f"G0 X{profile.park_x_mm:g} Y{profile.park_y_mm:g}"
        )
        self.statusBar().showMessage(
            f"Parking {profile.name}",
            4000,
        )

    def _postprocessor_settings_dialog(self) -> None:
        form = _ActionForm(self, "Postprocessor")
        form.add_combo(
            "post",
            "Postprocessor",
            ["GRBL / Onefinity"],
            str(self._settings.value("post/name", "GRBL / Onefinity")),
        )
        form.add_int(
            "decimals",
            "Coordinate decimals",
            int(self._settings.value("post/decimals", 3)),
            minimum=0,
            maximum=6,
        )
        form.add_check(
            "comments",
            "Include comments",
            bool(self._settings.value("post/comments", True, type=bool)),
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        self._settings.setValue("post/name", form.value("post"))
        self._settings.setValue("post/decimals", int(form.value("decimals")))
        self._settings.setValue("post/comments", bool(form.value("comments")))
        self._settings.sync()
        self.statusBar().showMessage("Postprocessor settings saved", 3000)

    def _grbl_post_settings(self) -> GrblPostSettings:
        profile = self._active_machine_profile()
        center_zero = self.project.stock.xy_zero == "center"
        return GrblPostSettings(
            decimals=int(self._settings.value("post/decimals", 3)),
            include_comments=bool(
                self._settings.value("post/comments", True, type=bool)
            ),
            x_offset_mm=(
                -self.project.stock.width_mm / 2.0
                if center_zero
                else 0.0
            ),
            y_offset_mm=(
                -self.project.stock.height_mm / 2.0
                if center_zero
                else 0.0
            ),
            park_enabled=profile.parking_enabled,
            park_x_mm=profile.park_x_mm,
            park_y_mm=profile.park_y_mm,
            park_z_mm=profile.park_z_mm,
        )

    def _connect_machine(self) -> None:
        if self.machine_controller.connected:
            self.machine_controller.disconnect()
            return

        if self._machine_connect_button is not None:
            self._machine_connect_button.setChecked(False)

        profile = self._active_machine_profile()
        if not profile.port:
            self._machine_profile()
            profile = self._active_machine_profile()
        if not profile.port:
            self.statusBar().showMessage(
                "No serial port configured for the active machine",
                5000,
            )
            return
        self.statusBar().showMessage(
            f"Connecting {profile.name} on {profile.port}…"
        )
        if self.machine_controller.connect_serial(
            profile.port,
            profile.baud_rate,
        ):
            self.machine_controller.send_line("?")

    def _machine_connection_changed(self, connected: bool, port: str) -> None:
        if self._machine_connect_button is not None:
            self._machine_connect_button.setText(
                "Disconnect" if connected else "Connect"
            )
            self._machine_connect_button.setChecked(connected)

        if hasattr(self, "machine_status_label"):
            self.machine_status_label.setText(
                f"CONNECTED • {port}" if connected else "OFFLINE"
            )
            self.machine_status_label.setProperty(
                "connected",
                connected,
            )
            self.machine_status_label.style().unpolish(
                self.machine_status_label
            )
            self.machine_status_label.style().polish(
                self.machine_status_label
            )

        self.statusBar().showMessage(
            f"{'Connected to' if connected else 'Disconnected from'} {port}",
            4000,
        )

    def _machine_line_received(self, line: str) -> None:
        self.statusBar().showMessage(f"Machine: {line}", 3500)

    def _machine_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Machine: {message}", 6000)

    def _probe_machine(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage("Connect to the machine before probing", 5000)
            return
        form = _ActionForm(self, "Z Probe")
        form.add_double("distance", "Maximum downward travel", 15.0, minimum=0.1, suffix=" mm")
        form.add_double(
            "feed",
            "Probe feed",
            100.0,
            minimum=1.0,
            maximum=5000.0,
            suffix=" mm/min",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        answer = QMessageBox.question(
            self,
            "Start Z Probe",
            "The machine will move Z downward until the probe triggers.\n\n"
            "Confirm the probe is connected and positioned correctly.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        distance = float(form.value("distance"))
        feed = float(form.value("feed"))
        self.machine_controller.send_line(f"G38.2 Z-{distance:g} F{feed:g}")

    def _show_jog_controls(self) -> None:
        if self._jog_dialog is not None:
            self._jog_dialog.show()
            self._jog_dialog.raise_()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Jog")
        dialog.setModal(False)
        layout = QVBoxLayout(dialog)

        controls = QWidget()
        grid = QGridLayout(controls)
        step = QDoubleSpinBox()
        step.setRange(0.01, 100.0)
        step.setValue(1.0)
        step.setSuffix(" mm")
        feed = QDoubleSpinBox()
        feed.setRange(1.0, 10000.0)
        feed.setValue(1000.0)
        feed.setSuffix(" mm/min")
        grid.addWidget(QLabel("Step"), 0, 0)
        grid.addWidget(step, 0, 1)
        grid.addWidget(QLabel("Feed"), 1, 0)
        grid.addWidget(feed, 1, 1)

        def send(axis: str, sign: float) -> None:
            if not self.machine_controller.connected:
                self.statusBar().showMessage("Machine is not connected", 4000)
                return
            amount = step.value() * sign
            self.machine_controller.send_line(
                f"$J=G91 G21 {axis}{amount:g} F{feed.value():g}"
            )

        buttons = [
            ("Y+", "Y", 1.0, 2, 1),
            ("X-", "X", -1.0, 3, 0),
            ("X+", "X", 1.0, 3, 2),
            ("Y-", "Y", -1.0, 4, 1),
            ("Z+", "Z", 1.0, 2, 3),
            ("Z-", "Z", -1.0, 4, 3),
        ]
        for label, axis, sign, row, column in buttons:
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, a=axis, s=sign: send(a, s)
            )
            grid.addWidget(button, row, column)

        layout.addWidget(controls)
        dialog.finished.connect(lambda _result: setattr(self, "_jog_dialog", None))
        self._jog_dialog = dialog
        dialog.show()

    # ------------------------------------------------------------------
    # View / toolpath simulation
    # ------------------------------------------------------------------
    def _set_2d_view(self) -> None:
        self.viewport.set_standard_view("Top", projection_mode="orthographic")
        self.statusBar().showMessage("2D top view", 2500)

    def _toggle_toolpaths_view(self) -> None:
        visible = not self.viewport.toolpaths_visible
        self.viewport.set_toolpaths_visible(visible)
        if self._toolpaths_view_button is not None:
            self._toolpaths_view_button.setChecked(visible)
        self.statusBar().showMessage(
            f"Toolpaths {'shown' if visible else 'hidden'}",
            2500,
        )

    def _toggle_rapids_view(self) -> None:
        visible = not self.viewport.rapids_visible
        self.viewport.set_rapids_visible(visible)
        if self._rapids_view_button is not None:
            self._rapids_view_button.setChecked(visible)
        self.statusBar().showMessage(
            f"Rapids {'shown' if visible else 'hidden'}",
            2500,
        )

    def _simulate_toolpaths(self) -> None:
        if not self.project.toolpaths:
            self.statusBar().showMessage("No calculated toolpaths to simulate", 4000)
            if self._simulation_button is not None:
                self._simulation_button.setChecked(False)
            return

        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
            self.viewport.set_simulation_fraction(1.0)
            if self._simulation_button is not None:
                self._simulation_button.setChecked(False)
            self.statusBar().showMessage("Simulation stopped", 2500)
            return

        self.viewport.set_toolpaths_visible(True)
        self.viewport.set_simulation_fraction(0.0)
        if self._toolpaths_view_button is not None:
            self._toolpaths_view_button.setChecked(True)
        if self._simulation_button is not None:
            self._simulation_button.setChecked(True)
        self._simulation_timer.start()
        self.statusBar().showMessage("Toolpath simulation running…")

    def _advance_simulation(self) -> None:
        total_segments = sum(
            max(0, len(toolpath.moves) - 1)
            for toolpath in self.project.toolpaths
        )
        increment = max(0.005, 1.0 / max(total_segments, 1))
        fraction = self.viewport.simulation_fraction + increment
        if fraction >= 1.0:
            self._simulation_timer.stop()
            self.viewport.set_simulation_fraction(1.0)
            if self._simulation_button is not None:
                self._simulation_button.setChecked(False)
            self.statusBar().showMessage("Simulation complete", 3000)
            return
        self.viewport.set_simulation_fraction(fraction)
        self.statusBar().showMessage(
            f"Simulating toolpath… {fraction * 100:.0f}%"
        )


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
                    if item.smart_bindings
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

    def _fixture_editor(self) -> None:
        """Edit persistent keep-out volumes, including off-stock fences."""

        dialog = QDialog(self)
        dialog.setWindowTitle("Clamps and Fences — Fixture Keep-Outs")
        dialog.resize(630, 435)
        layout = QVBoxLayout(dialog)
        explanation = QLabel(
            "Fixture XY is measured from the stock bottom-left corner. "
            "Top Z is relative to the stock top (Z0); a 23 mm fence "
            "measured from the bed has Top Z = 23 - stock thickness. "
            "Keep-out clearance applies beyond the cutter radius."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        listing = QListWidget()
        listing.setObjectName("FixtureKeepOutList")
        layout.addWidget(listing, 1)
        controls = QHBoxLayout()
        add_button = QPushButton("Add")
        edit_button = QPushButton("Edit")
        remove_button = QPushButton("Remove")
        for button in (add_button, edit_button, remove_button):
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        entries = list(self.project.fixtures)

        def refresh() -> None:
            selected = listing.currentRow()
            listing.clear()
            for fixture in entries:
                listing.addItem(
                    f"{fixture.name}  ·  X {fixture.x_min_mm:g}…"
                    f"{fixture.x_max_mm:g}, Y {fixture.y_min_mm:g}…"
                    f"{fixture.y_max_mm:g}, top Z {fixture.top_z_mm:g}, "
                    f"margin {fixture.clearance_mm:g} mm"
                )
            if entries:
                listing.setCurrentRow(max(0, min(selected, len(entries) - 1)))

        def edit_fixture(current: Fixture | None) -> Fixture | None:
            defaults = current or Fixture(
                "Left fence", -23.0, 0.0, -1.0,
                self.project.stock.height_mm,
                23.0 - self.project.stock.thickness_mm, 2.0,
            )
            while True:
                form = _ActionForm(dialog, "Add Fixture" if current is None else "Edit Fixture")
                form.add_line("name", "Name", defaults.name)
                for key, title, value in (
                    ("x0", "Minimum X", defaults.x_min_mm),
                    ("y0", "Minimum Y", defaults.y_min_mm),
                    ("x1", "Maximum X", defaults.x_max_mm),
                    ("y1", "Maximum Y", defaults.y_max_mm),
                    ("top", "Top Z", defaults.top_z_mm),
                    ("margin", "Additional clearance", defaults.clearance_mm),
                ):
                    form.add_double(
                        key, title, value, suffix=" mm",
                        minimum=0.0 if key == "margin" else -100000.0,
                    )
                if form.exec() != QDialog.DialogCode.Accepted:
                    return None
                candidate = Fixture(
                    str(form.value("name")).strip(),
                    float(form.value("x0")),
                    float(form.value("y0")),
                    float(form.value("x1")),
                    float(form.value("y1")),
                    float(form.value("top")),
                    float(form.value("margin")),
                )
                try:
                    candidate.validate()
                except ValueError as exc:
                    QMessageBox.warning(form, "Invalid fixture", str(exc))
                    defaults = candidate
                    continue
                return candidate

        def add() -> None:
            fixture = edit_fixture(None)
            if fixture is not None:
                entries.append(fixture)
                refresh()
                listing.setCurrentRow(len(entries) - 1)

        def edit() -> None:
            index = listing.currentRow()
            if 0 <= index < len(entries):
                fixture = edit_fixture(entries[index])
                if fixture is not None:
                    entries[index] = fixture
                    refresh()

        def remove() -> None:
            index = listing.currentRow()
            if 0 <= index < len(entries):
                entries.pop(index)
                refresh()

        add_button.clicked.connect(add)
        edit_button.clicked.connect(edit)
        remove_button.clicked.connect(remove)
        listing.itemDoubleClicked.connect(lambda _item: edit())
        refresh()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if entries != self.project.fixtures:
            self._before_ribbon_mutation("edit fixtures")
            self.project.fixtures = entries
            self.viewport.update()
            self._after_ribbon_mutation("edit fixtures", True)
            self.statusBar().showMessage(
                f"Saved {len(entries)} fixture keep-out(s)", 4500
            )

    def _preflight_toolpaths(self) -> None:
        paths = list(self.project.toolpaths)
        guided_fingerprint = self._guided_job_fingerprint()
        self._guided_preflight_pass = None
        if not paths:
            self.statusBar().showMessage(
                "Generate toolpaths before running preflight", 4000
            )
            return
        request = GcodeRequest(
            toolpaths=paths,
            path="",
            settings=self._grbl_post_settings(),
            mode="preflight",
            stock=self.project.stock,
            machine_profile=self._active_machine_profile(),
            fixtures=tuple(self.project.fixtures),
        )

        def done(payload: object) -> None:
            self._guided_preflight_pass = (
                guided_fingerprint if payload["safe_to_export"]
                and self._guided_job_fingerprint() == guided_fingerprint
                else None
            )
            self._refresh_guided_workflow()
            report = str(payload["report"])
            self._set_activity_info(report)
            display = QMessageBox(self)
            display.setWindowTitle("CNC Preflight")
            display.setIcon(
                QMessageBox.Icon.Information
                if payload["safe_to_export"] else QMessageBox.Icon.Warning
            )
            display.setText(
                "Preflight passed (with noted warnings)."
                if payload["safe_to_export"] else
                "Preflight blocked export until errors are corrected."
            )
            display.setDetailedText(report)
            display.setStandardButtons(QMessageBox.StandardButton.Ok)
            display.exec()

        self._start_background_job(
            "CNC preflight", request=request, on_done=done
        )

    def _export_resume_gcode(self) -> None:
        toolpaths = list(self.project.toolpaths)
        if not toolpaths:
            self.statusBar().showMessage(
                "Calculate toolpaths before creating a resume file",
                5000,
            )
            return

        counts = [len(toolpath.moves) for toolpath in toolpaths]
        total_moves = sum(counts)
        if total_moves <= 0:
            self.statusBar().showMessage("Toolpaths contain no moves", 4000)
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Resume Carve")
        dialog.resize(620, 320)
        layout = QVBoxLayout(dialog)
        warning = QLabel(
            "Choose approximately where the interruption occurred. "
            "Safe restart rewinds to the beginning of that uninterrupted cutting "
            "section and is recommended because it avoids a blind vertical entry "
            "in the middle of a 3D pass."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, total_moves - 1)
        spin = QSpinBox()
        spin.setRange(0, total_moves - 1)
        spin.setPrefix("Move ")
        row = QHBoxLayout()
        row.addWidget(slider, 1)
        row.addWidget(spin)
        layout.addLayout(row)

        safe_rewind = QCheckBox("Rewind to safe section start")
        safe_rewind.setChecked(True)
        layout.addWidget(safe_rewind)

        detail = QLabel()
        detail.setObjectName("InspectorInfo")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        def locate(global_index: int) -> tuple[int, int]:
            remaining = int(global_index)
            for path_index, count in enumerate(counts):
                if remaining < count:
                    return path_index, remaining
                remaining -= count
            return len(counts) - 1, max(0, counts[-1] - 1)

        def update_detail(value: int) -> None:
            if spin.value() != value:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
            if slider.value() != value:
                slider.blockSignals(True)
                slider.setValue(value)
                slider.blockSignals(False)
            path_index, move_index = locate(value)
            toolpath = toolpaths[path_index]
            move = toolpath.moves[move_index]
            safe_index = move_index
            if safe_rewind.isChecked():
                try:
                    safe_index = find_safe_resume_index(toolpath, move_index)
                except (IndexError, ValueError):
                    safe_index = move_index
            detail.setText(
                f"Operation: {toolpath.name}\n"
                f"Selected point: {move_index:,} / {len(toolpath.moves) - 1:,}\n"
                f"XYZ: {move.x_mm:.3f}, {move.y_mm:.3f}, {move.z_mm:.3f} mm\n"
                f"Move type: {move.kind.value}\n"
                f"Actual restart point: {safe_index:,}"
            )

        slider.valueChanged.connect(update_detail)
        spin.valueChanged.connect(update_detail)
        safe_rewind.toggled.connect(
            lambda _checked: update_detail(slider.value())
        )
        update_detail(0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        path_index, move_index = locate(slider.value())
        rewind = safe_rewind.isChecked()

        base_directory = (
            self.project_path.parent if self.project_path else Path.home()
        )
        name = (
            self.project.name
            if self.project.name != "Untitled"
            else "carve"
        )
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Export Resume G-code",
            str(base_directory / f"{name}_resume.nc"),
            "G-code (*.nc *.gcode *.tap *.cnc);;All files (*)",
        )
        if not output:
            return
        request = GcodeRequest(
            toolpaths=toolpaths,
            path=output,
            settings=self._grbl_post_settings(),
            stock=self.project.stock,
            machine_profile=self._active_machine_profile(),
            fixtures=tuple(self.project.fixtures),
            mode="resume",
            resume_path_index=path_index,
            resume_move_index=move_index,
            resume_rewind=rewind,
        )

        def done(result):
            written = Path(result["files"][0])
            self.statusBar().showMessage(
                f"Resume G-code exported: {written.name}", 5000
            )

        self._start_background_job(
            "Export resume G-code", request=request, on_done=done
        )

    def _export_tiled_gcode(self) -> None:
        toolpaths = list(self.project.toolpaths)
        if not toolpaths:
            self.statusBar().showMessage(
                "Calculate toolpaths before exporting tiles",
                5000,
            )
            return

        profile = self._active_machine_profile()
        stock = self.project.stock
        form = _ActionForm(self, "Large Material Tiling")
        form.add_double(
            "width",
            "Tile width",
            min(stock.width_mm, profile.work_x_mm),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm",
        )
        form.add_double(
            "height",
            "Tile height",
            min(stock.height_mm, profile.work_y_mm),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm",
        )
        form.add_double(
            "overlap",
            "Tile overlap",
            3.0,
            minimum=0.0,
            maximum=10000.0,
            suffix=" mm",
        )
        form.add_check(
            "rebase",
            "Re-zero each shifted tile",
            True,
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        settings = TilingSettings(
            tile_width_mm=float(form.value("width")),
            tile_height_mm=float(form.value("height")),
            overlap_mm=float(form.value("overlap")),
            rebase_each_tile=bool(form.value("rebase")),
        )
        try:
            plan_tiles(
                stock.width_mm,
                stock.height_mm,
                settings,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Large Material Tiling", str(exc))
            return

        base_directory = (
            self.project_path.parent if self.project_path else Path.home()
        )
        name = (
            self.project.name
            if self.project.name != "Untitled"
            else "carve"
        )
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Choose Tiled G-code Base Name",
            str(base_directory / f"{name}_tiles.nc"),
            "G-code (*.nc *.gcode *.tap *.cnc);;All files (*)",
        )
        if not output:
            return

        request = GcodeRequest(
            toolpaths=toolpaths,
            path=output,
            settings=self._grbl_post_settings(),
            stock=self.project.stock,
            machine_profile=self._active_machine_profile(),
            fixtures=tuple(self.project.fixtures),
            mode="tiles",
            tile_settings=settings,
            stock_width_mm=stock.width_mm,
            stock_height_mm=stock.height_mm,
            xy_zero=stock.xy_zero,
        )

        def done(result):
            written = [Path(path) for path in result["files"]]
            self._set_activity_info(
                "Tiled G-code exported\n"
                f"Files: {len(written)}\n"
                f"Tile size: {settings.tile_width_mm:g} × "
                f"{settings.tile_height_mm:g} mm\n"
                f"Overlap: {settings.overlap_mm:g} mm\n"
                + "\n".join(path.name for path in written[:12])
            )
            self.statusBar().showMessage(
                f"Exported {len(written)} tiled G-code files", 5000
            )

        self._start_background_job(
            "Export tiled G-code", request=request, on_done=done
        )
