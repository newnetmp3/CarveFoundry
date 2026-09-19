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
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
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
    finish_3d,
    waterline_3d,
)
from carvefoundry.cam.gcode import GrblPostSettings
from carvefoundry.cam.raster import RasterAxis, RasterLinkMode
from carvefoundry.cam.vector_ops import (
    geometry_drill,
    geometry_engrave,
    geometry_pocket,
    geometry_profile,
    geometry_vcarve,
)
from carvefoundry.core.primitives import (
    bitmap_runs_mesh,
    ellipse_mesh,
    line_mesh,
    polygon_mesh,
    polyline_mesh,
    rectangle_mesh,
    text_mesh,
)
from carvefoundry.core.project import ProjectItem, TextProperties
from carvefoundry.core.tools import DEFAULT_TOOLS, Cutter, ToolType
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.units import ModelUnits

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


class RibbonActionsMixin:
    """Functional implementations for CarveFoundry ribbon actions."""

    def _init_ribbon_action_state(self) -> None:
        self._clipboard_items: list[ProjectItem] = []
        self._active_cam_operation = "finish"
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
        self._cam_selector_widgets: dict[str, list[QComboBox]] = {}
        self._cam_detail_widgets: list[object] = []

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
        if normalized.startswith("calculate "):
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
        self.viewport.set_camera_control_mode(False)
        if self._camera_tool_button is not None:
            self._camera_tool_button.blockSignals(True)
            try:
                self._camera_tool_button.setChecked(False)
            finally:
                self._camera_tool_button.blockSignals(False)

        button = self._shape_tool_buttons.get(tool)
        wants_active = bool(button is None or button.isChecked())
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
    ) -> ProjectItem:
        item = ProjectItem(
            name=self._unique_item_name(name),
            kind=kind,
            mesh=mesh,
            transform=transform,
            source_units=ModelUnits.MILLIMETERS,
            text_properties=text_properties,
        )
        self._before_ribbon_mutation(f"draw {kind}")
        self.project.items.append(item)
        self._refresh_project_list(len(self.project.items))
        self.viewport.update()
        self._after_ribbon_mutation(f"draw {kind}", True)
        self.statusBar().showMessage(f"Drew {item.name}", 2500)
        return item

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
            self._add_drawn_item("Line", "line", mesh, transform)
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

        try:
            mesh = polyline_mesh(
                captured,
                width_mm=self._tool_option_pen_width_mm,
                depth_mm=self._tool_option_depth_mm,
            )
        except ValueError as exc:
            self.statusBar().showMessage(f"Pen stroke failed: {exc}", 5000)
            return

        self._add_drawn_item(
            "Pen Stroke",
            "pen",
            mesh,
            Transform3D(),
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
        image = QImage(path)
        if image.isNull():
            self.statusBar().showMessage("Could not load image", 5000)
            return

        form = _ActionForm(self, "Trace Image")
        form.add_int("threshold", "Dark threshold (0-255)", 150, minimum=0, maximum=255)
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

        max_dimension = 96
        if max(image.width(), image.height()) > max_dimension:
            image = image.scaled(
                max_dimension,
                max_dimension,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        mask = np.zeros((image.height(), image.width()), dtype=bool)
        threshold = int(form.value("threshold"))
        invert = bool(form.value("invert"))
        for y in range(image.height()):
            for x in range(image.width()):
                color = QColor(image.pixel(x, y))
                luminance = (
                    0.2126 * color.red()
                    + 0.7152 * color.green()
                    + 0.0722 * color.blue()
                )
                active = color.alpha() > 16 and luminance <= threshold
                mask[y, x] = not active if invert and color.alpha() > 16 else active

        try:
            mesh = bitmap_runs_mesh(
                mask,
                width_mm=form.value("width"),
                depth_mm=form.value("depth"),
            )
        except ValueError as exc:
            self.statusBar().showMessage(f"Trace failed: {exc}", 5000)
            return
        self._add_generated_item(Path(path).stem + " trace", "trace", mesh)

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
        previous_detail = self._cam_detail
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
        if detail != previous_detail:
            self._invalidate_toolpaths("Toolpath detail")

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
        previous_value = getattr(self, attribute)
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

        if value != previous_value:
            self._invalidate_toolpaths("Toolpath settings")

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
        self._invalidate_toolpaths("Advanced toolpath settings")
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
        previous_operation = self._active_cam_operation
        self._active_cam_operation = operation
        if operation != previous_operation:
            self._invalidate_toolpaths("Toolpath operation")
        labels = {
            "profile": "Profile",
            "pocket": "Pocket",
            "vcarve": "V-Carve",
            "engrave": "Engrave",
            "drill": "Drill",
            "rough": "3D Rough",
            "finish": "3D Finish",
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
        is_3d = operation in {"rough", "finish", "rest", "waterline"}
        uses_cut_type = operation in {"profile", "pocket", "engrave"}

        for combo in self._cam_selector_widgets.get("cut_type", []):
            combo.setEnabled(uses_cut_type)
        for combo in self._cam_selector_widgets.get("3d_cut_style", []):
            combo.setEnabled(is_3d)
        for combo in self._cam_selector_widgets.get("entry", []):
            combo.setEnabled(not is_3d)
        for combo in self._cam_selector_widgets.get("milling", []):
            combo.setEnabled(not is_3d)
        for combo in self._cam_selector_widgets.get("linking", []):
            combo.setEnabled(is_3d)

        for widget in self._cam_detail_widgets:
            widget.setEnabled(is_3d)

        if self._tabs_button is not None:
            self._tabs_button.setEnabled(operation == "profile")

    def _toggle_tabs_operation(self) -> None:
        self._tabs_enabled = not self._tabs_enabled
        self._settings.setValue("cam/tabs_enabled", self._tabs_enabled)
        self._invalidate_toolpaths("Tab settings")
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
            "pocket": "Pocket",
            "vcarve": "V-Carve",
            "engrave": "Engrave",
            "drill": "Drill",
            "rough": "3D Rough",
            "finish": "3D Finish",
            "rest": "3D Rest",
            "waterline": "3D Waterline",
        }.get(operation, operation.replace("_", " ").title())

    @staticmethod
    def _generation_double_spin(
        value: float,
        *,
        minimum: float,
        maximum: float,
        suffix: str = "",
        decimals: int = 3,
        step: float = 0.1,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(float(value))
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        return spin

    def _build_toolpath_generation_dialog(self) -> QDialog:
        """Build the all-in-one CAM generation dialog.

        The dialog is intentionally complete enough to generate the chosen
        operation for every design object without visiting other panels.
        """

        dialog = QDialog(self)
        dialog.setObjectName("ToolpathGenerationDialog")
        dialog.setWindowTitle("Generate Toolpaths")
        dialog.resize(860, 760)
        dialog.setMinimumSize(720, 600)
        dialog.setModal(True)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        title = QLabel("Generate Toolpaths")
        title.setObjectName("DialogTitle")
        title_font = title.font()
        title_font.setPointSize(max(12, title_font.pointSize() + 3))
        title_font.setBold(True)
        title.setFont(title_font)
        outer.addWidget(title)

        intro = QLabel(
            "Complete the required sections below. Options that do not apply "
            "to the selected operation are disabled automatically."
        )
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        outer.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        fields: dict[str, QWidget] = {}

        def group(title_text: str) -> tuple[QGroupBox, QFormLayout]:
            box = QGroupBox(title_text)
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setHorizontalSpacing(10)
            form.setVerticalSpacing(7)
            return box, form

        source_box, source_form = group("1. Source & Operation")
        source_items = [
            project_item
            for project_item in self.project.items
            if project_item.mesh is not None
        ]
        source_summary = QLabel()
        source_summary.setWordWrap(True)
        if source_items:
            names = ", ".join(item.name for item in source_items[:8])
            if len(source_items) > 8:
                names += f", +{len(source_items) - 8} more"
            source_summary.setText(
                f"All {len(source_items)} design object"
                f"{'s' if len(source_items) != 1 else ''}\n{names}"
            )
        else:
            source_summary.setText("No design geometry in this project")
        source_summary.setToolTip(
            "Generate Toolpaths always processes every design object that "
            "contains mesh geometry. The current selection is ignored."
        )
        fields["source_summary"] = source_summary
        source_form.addRow("Objects", source_summary)

        operation_combo = QComboBox()
        for operation in (
            "profile",
            "pocket",
            "vcarve",
            "engrave",
            "drill",
            "rough",
            "finish",
            "rest",
            "waterline",
        ):
            operation_combo.addItem(
                self._cam_operation_title(operation),
                operation,
            )
        op_index = operation_combo.findData(self._active_cam_operation)
        operation_combo.setCurrentIndex(max(0, op_index))
        fields["operation"] = operation_combo
        source_form.addRow("Toolpath", operation_combo)

        stock = self.project.stock
        stock_label = QLabel(
            f"{stock.width_mm:g} × {stock.height_mm:g} × "
            f"{stock.thickness_mm:g} mm"
        )
        fields["stock"] = stock_label
        source_form.addRow("Stock", stock_label)
        grid.addWidget(source_box, 0, 0)

        cutter_box, cutter_form = group("2. Cutter")
        cutter_combo = QComboBox()
        current_cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        for index in range(self.tool_combo.count()):
            cutter = self.tool_combo.itemData(index)
            if not isinstance(cutter, Cutter):
                continue
            cutter_combo.addItem(cutter.name, cutter)
            if (
                isinstance(current_cutter, Cutter)
                and cutter.name == current_cutter.name
            ):
                cutter_combo.setCurrentIndex(cutter_combo.count() - 1)
        fields["cutter"] = cutter_combo
        cutter_form.addRow("Selected cutter", cutter_combo)
        cutter_details = QLabel()
        cutter_details.setWordWrap(True)
        cutter_details.setObjectName("Muted")
        fields["cutter_details"] = cutter_details
        cutter_form.addRow("Geometry", cutter_details)
        grid.addWidget(cutter_box, 0, 1)

        strategy_box, strategy_form = group("3. Geometry & Strategy")
        cut_type = QComboBox()
        cut_type.addItems(("Auto", "Pocket", "On Path", "Outside", "Inside"))
        cut_type.setCurrentText(self._cam_cut_type)
        fields["cut_type"] = cut_type
        strategy_form.addRow("2D cut type", cut_type)

        style_3d = QComboBox()
        style_3d.addItems(
            (
                "Model Boundary Relief",
                "Rectangle Relief",
                "Full Depth Cutout",
            )
        )
        style_3d.setCurrentText(self._cam_3d_cut_style)
        fields["3d_style"] = style_3d
        strategy_form.addRow("3D style", style_3d)

        direction = QComboBox()
        direction.addItems(
            (
                "Smart Serpentine",
                "Offset",
                "Raster X",
                "Raster Y",
                "Raster 45°",
                "Raster 135°",
            )
        )
        direction.setCurrentText(self._cam_direction)
        fields["direction"] = direction
        strategy_form.addRow("Direction", direction)

        detail = QSpinBox()
        detail.setRange(0, 100)
        detail.setSuffix(" %")
        detail.setValue(self._cam_detail)
        fields["detail"] = detail
        strategy_form.addRow("3D / V-Carve detail", detail)

        pocket_stepover = self._generation_double_spin(
            float(self._settings.value("cam/stepover_percent", 45.0)),
            minimum=1.0,
            maximum=100.0,
            suffix=" %",
            decimals=1,
            step=1.0,
        )
        fields["pocket_stepover"] = pocket_stepover
        strategy_form.addRow("2D pocket stepover", pocket_stepover)

        padding = self._generation_double_spin(
            float(self._settings.value("cam/padding_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            suffix=" mm",
            step=0.25,
        )
        fields["padding"] = padding
        strategy_form.addRow("Path / relief padding", padding)
        grid.addWidget(strategy_box, 1, 0)

        depth_box, depth_form = group("4. Depth Requirements")
        cut_depth = self._generation_double_spin(
            float(self._settings.value("cam/overall_depth_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            suffix=" mm",
            step=0.25,
        )
        cut_depth.setToolTip(
            "0 uses the design/model depth. A positive value overrides it."
        )
        fields["cut_depth"] = cut_depth
        depth_form.addRow("Overall cut depth", cut_depth)

        stepdown = self._generation_double_spin(
            float(self._settings.value("cam/stepdown_mm", 2.0)),
            minimum=0.05,
            maximum=1000.0,
            suffix=" mm",
            step=0.25,
        )
        fields["stepdown"] = stepdown
        depth_form.addRow("Depth per pass", stepdown)

        bit_length = self._generation_double_spin(
            float(self._settings.value("cam/usable_bit_length_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            suffix=" mm",
            step=0.5,
        )
        bit_length.setToolTip("0 disables usable-length enforcement.")
        fields["bit_length"] = bit_length
        depth_form.addRow("Usable bit length", bit_length)
        grid.addWidget(depth_box, 1, 1)

        motion_box, motion_form = group("5. Motion & Safety")
        safe_z = self._generation_double_spin(
            float(self._settings.value("cam/safe_z_mm", 1.5)),
            minimum=0.05,
            maximum=100.0,
            suffix=" mm",
            step=0.1,
        )
        fields["safe_z"] = safe_z
        motion_form.addRow("Safe Z", safe_z)

        feed = self._generation_double_spin(
            float(self._settings.value("cam/feed_mm_min", 1000.0)),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm/min",
            decimals=0,
            step=50.0,
        )
        fields["feed"] = feed
        motion_form.addRow("Cut feed", feed)

        plunge = self._generation_double_spin(
            float(self._settings.value("cam/plunge_mm_min", 300.0)),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm/min",
            decimals=0,
            step=25.0,
        )
        fields["plunge"] = plunge
        motion_form.addRow("Plunge feed", plunge)

        entry = QComboBox()
        entry.addItems(("Plunge", "Ramp 5°", "Ramp 20°", "Custom Ramp"))
        entry.setCurrentText(self._cam_entry)
        fields["entry"] = entry
        motion_form.addRow("Entry", entry)

        ramp_angle = self._generation_double_spin(
            float(self._settings.value("cam/custom_ramp_angle_deg", 10.0)),
            minimum=0.5,
            maximum=89.0,
            suffix="°",
            decimals=1,
            step=0.5,
        )
        fields["ramp_angle"] = ramp_angle
        motion_form.addRow("Custom ramp", ramp_angle)

        milling = QComboBox()
        milling.addItems(("Default", "Climb (CCW)", "Conventional (CW)"))
        milling.setCurrentText(self._cam_milling)
        fields["milling"] = milling
        motion_form.addRow("Milling direction", milling)

        linking = QComboBox()
        linking.addItems(("Smart Min-Lift", "Local Lift", "Full Retract"))
        linking.setCurrentText(self._cam_linking)
        fields["linking"] = linking
        motion_form.addRow("3D linking", linking)

        local_clearance = self._generation_double_spin(
            float(self._settings.value("cam/local_link_clearance_mm", 0.5)),
            minimum=0.05,
            maximum=25.0,
            suffix=" mm",
            step=0.1,
        )
        fields["local_clearance"] = local_clearance
        motion_form.addRow("Local lift clearance", local_clearance)

        link_tolerance = self._generation_double_spin(
            float(self._settings.value("cam/direct_link_tolerance_mm", 0.02)),
            minimum=0.0,
            maximum=5.0,
            suffix=" mm",
            step=0.01,
        )
        fields["link_tolerance"] = link_tolerance
        motion_form.addRow("Direct-link tolerance", link_tolerance)
        grid.addWidget(motion_box, 2, 0)

        tabs_box, tabs_form = group("6. Tabs / Cutout Holding")
        tabs_enabled = QCheckBox("Use holding tabs")
        tabs_enabled.setChecked(self._tabs_enabled)
        fields["tabs_enabled"] = tabs_enabled
        tabs_form.addRow(tabs_enabled)

        tab_height = self._generation_double_spin(
            float(self._settings.value("cam/tab_height_mm", 2.0)),
            minimum=0.1,
            maximum=100.0,
            suffix=" mm",
            step=0.25,
        )
        fields["tab_height"] = tab_height
        tabs_form.addRow("Tab height", tab_height)

        tab_width = self._generation_double_spin(
            float(self._settings.value("cam/tab_width_mm", 6.0)),
            minimum=0.5,
            maximum=100.0,
            suffix=" mm",
            step=0.5,
        )
        fields["tab_width"] = tab_width
        tabs_form.addRow("Tab width", tab_width)

        tab_count = QSpinBox()
        tab_count.setRange(1, 32)
        tab_count.setValue(int(self._settings.value("cam/tab_count", 4)))
        fields["tab_count"] = tab_count
        tabs_form.addRow("Tab count", tab_count)
        grid.addWidget(tabs_box, 2, 1)

        ready_box = QGroupBox("7. Generation Readiness")
        ready_layout = QVBoxLayout(ready_box)
        readiness = QLabel()
        readiness.setWordWrap(True)
        readiness.setTextFormat(Qt.TextFormat.RichText)
        fields["readiness"] = readiness
        ready_layout.addWidget(readiness)
        grid.addWidget(ready_box, 3, 0, 1, 2)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        generate_button = buttons.addButton(
            "Generate Toolpaths",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        generate_button.setObjectName("PrimaryButton")
        generate_button.setDefault(True)
        fields["generate"] = generate_button
        buttons.rejected.connect(dialog.reject)
        outer.addWidget(buttons)

        def update_relevance_and_readiness() -> None:
            operation = str(operation_combo.currentData() or "")
            is_3d = operation in {"rough", "finish", "rest", "waterline"}
            uses_cut_type = operation in {"profile", "pocket", "engrave"}
            uses_detail = is_3d or operation == "vcarve"
            uses_entry = not is_3d and operation != "drill"
            uses_milling = operation in {"profile", "pocket", "engrave"}
            uses_linking = is_3d
            uses_tabs = operation == "profile" or (
                operation == "finish"
                and style_3d.currentText() == "Full Depth Cutout"
            )

            cut_type.setEnabled(uses_cut_type)
            style_3d.setEnabled(is_3d)
            direction.setEnabled(is_3d or operation == "pocket")
            detail.setEnabled(uses_detail)
            pocket_stepover.setEnabled(operation == "pocket")
            entry.setEnabled(uses_entry)
            ramp_angle.setEnabled(
                uses_entry and entry.currentText() == "Custom Ramp"
            )
            milling.setEnabled(uses_milling)
            linking.setEnabled(uses_linking)
            local_clearance.setEnabled(uses_linking)
            link_tolerance.setEnabled(uses_linking)
            tabs_box.setEnabled(uses_tabs)

            cutter = cutter_combo.currentData()
            if isinstance(cutter, Cutter):
                detail_text = (
                    f"{cutter.tool_type.value.replace('_', ' ').title()} · "
                    f"Ø {cutter.diameter_mm:g} mm"
                )
                if cutter.angle_deg is not None:
                    detail_text += f" · {cutter.angle_deg:g}°"
                if cutter.tip_diameter_mm:
                    detail_text += f" · tip Ø {cutter.tip_diameter_mm:g} mm"
                cutter_details.setText(detail_text)
            else:
                cutter_details.setText("No valid cutter selected")

            checks: list[tuple[bool, str]] = []
            checks.append(
                (
                    bool(source_items),
                    (
                        f"All {len(source_items)} design object"
                        f"{'s' if len(source_items) != 1 else ''} will be generated"
                        if source_items
                        else "Project contains design geometry"
                    ),
                )
            )
            checks.append(
                (
                    isinstance(cutter, Cutter),
                    "Valid cutter selected",
                )
            )
            if operation == "vcarve":
                checks.append(
                    (
                        isinstance(cutter, Cutter)
                        and cutter.tool_type
                        in {ToolType.V_BIT, ToolType.ENGRAVING_CONE}
                        and cutter.angle_deg is not None,
                        "V-Carve cutter has a V/cone profile and included angle",
                    )
                )
            checks.append(
                (
                    stock.width_mm > 0
                    and stock.height_mm > 0
                    and stock.thickness_mm > 0,
                    "Stock dimensions are valid",
                )
            )
            checks.append((safe_z.value() > 0, "Safe Z is positive"))
            checks.append(
                (
                    feed.value() > 0
                    and plunge.value() > 0
                    and stepdown.value() > 0,
                    "Feed, plunge, and depth-per-pass are valid",
                )
            )
            requested_depth = cut_depth.value()
            usable_length = bit_length.value()
            checks.append(
                (
                    usable_length <= 0
                    or requested_depth <= 0
                    or requested_depth <= usable_length + 1e-9,
                    "Requested depth fits the enforced usable bit length",
                )
            )
            if uses_tabs and tabs_enabled.isChecked():
                checks.append(
                    (
                        tab_height.value() > 0
                        and tab_width.value() > 0
                        and tab_count.value() > 0,
                        "Holding-tab dimensions are valid",
                    )
                )

            all_ready = all(ok for ok, _message in checks)
            readiness.setText(
                "<br>".join(
                    (
                        "<span style='color:#62d26f'>✓</span> "
                        if ok
                        else "<span style='color:#ff6b6b'>●</span> "
                    )
                    + message
                    for ok, message in checks
                )
                + (
                    "<br><br><b>Ready to generate.</b>"
                    if all_ready
                    else "<br><br><b>Resolve the red requirements to continue.</b>"
                )
            )
            generate_button.setEnabled(all_ready)

        def accept_and_generate() -> None:
            update_relevance_and_readiness()
            if not generate_button.isEnabled():
                return

            operation = str(operation_combo.currentData() or "finish")
            self._select_cam_operation(operation)

            cutter = cutter_combo.currentData()
            if isinstance(cutter, Cutter):
                for index in range(self.tool_combo.count()):
                    candidate = self.tool_combo.itemData(index)
                    if (
                        isinstance(candidate, Cutter)
                        and candidate.name == cutter.name
                    ):
                        self.tool_combo.setCurrentIndex(index)
                        break

            for key, combo in (
                ("cut_type", cut_type),
                ("3d_cut_style", style_3d),
                ("direction", direction),
                ("entry", entry),
                ("milling", milling),
                ("linking", linking),
            ):
                self._set_cam_design_option(key, combo.currentText())
            self._set_cam_detail(detail.value(), mark_custom=True)

            values = {
                "cam/safe_z_mm": safe_z.value(),
                "cam/overall_depth_mm": cut_depth.value(),
                "cam/feed_mm_min": feed.value(),
                "cam/plunge_mm_min": plunge.value(),
                "cam/stepdown_mm": stepdown.value(),
                "cam/stepover_percent": pocket_stepover.value(),
                "cam/padding_mm": padding.value(),
                "cam/usable_bit_length_mm": bit_length.value(),
                "cam/tab_height_mm": tab_height.value(),
                "cam/tab_width_mm": tab_width.value(),
                "cam/tab_count": tab_count.value(),
                "cam/local_link_clearance_mm": local_clearance.value(),
                "cam/direct_link_tolerance_mm": link_tolerance.value(),
                "cam/custom_ramp_angle_deg": ramp_angle.value(),
            }
            for setting_key, setting_value in values.items():
                self._settings.setValue(setting_key, setting_value)

            self._tabs_enabled = (
                tabs_enabled.isChecked() if uses_tabs_for_current() else False
            )
            self._settings.setValue("cam/tabs_enabled", self._tabs_enabled)
            if self._tabs_button is not None:
                self._tabs_button.setChecked(self._tabs_enabled)
            self._settings.sync()

            dialog.accept()
            self._calculate_toolpath_now()

        def uses_tabs_for_current() -> bool:
            operation = str(operation_combo.currentData() or "")
            return operation == "profile" or (
                operation == "finish"
                and style_3d.currentText() == "Full Depth Cutout"
            )

        generate_button.clicked.connect(accept_and_generate)

        watched_widgets = (
            operation_combo,
            cutter_combo,
            cut_type,
            style_3d,
            direction,
            detail,
            pocket_stepover,
            padding,
            cut_depth,
            stepdown,
            bit_length,
            safe_z,
            feed,
            plunge,
            entry,
            ramp_angle,
            milling,
            linking,
            local_clearance,
            link_tolerance,
            tabs_enabled,
            tab_height,
            tab_width,
            tab_count,
        )
        for widget in watched_widgets:
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(
                    update_relevance_and_readiness
                )
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(update_relevance_and_readiness)
            else:
                widget.valueChanged.connect(update_relevance_and_readiness)

        dialog.generation_fields = fields
        dialog.refresh_generation_readiness = update_relevance_and_readiness
        update_relevance_and_readiness()
        return dialog

    def _show_toolpath_generation_dialog(self) -> None:
        dialog = self._build_toolpath_generation_dialog()
        dialog.exec()

    def _calculate_toolpath(self) -> None:
        """Compatibility entry point: calculation now begins with review."""

        self._show_toolpath_generation_dialog()

    def _generate_toolpaths_for_item(
        self,
        item: ProjectItem,
        cutter: Cutter,
        operation: str,
    ) -> list:
        """Generate the selected CAM operation for one project object."""

        bounds = item.transformed_bounds_mm()
        mesh = item.transformed_mesh()
        if bounds is None or mesh is None:
            return []

        settings = self._cam_settings(bounds, mesh)
        cut_type = self._cam_cut_type
        if operation == "vcarve":
            toolpath = geometry_vcarve(mesh, cutter, settings)
        elif operation == "drill":
            toolpath = geometry_drill(mesh, cutter, settings)
        elif (
            cut_type == "Pocket"
            and operation in {"profile", "pocket", "engrave"}
        ):
            toolpath = geometry_pocket(mesh, cutter, settings)
        elif (
            cut_type in {"On Path", "Outside", "Inside"}
            and operation in {"profile", "pocket", "engrave"}
        ):
            if operation == "engrave" and cut_type == "On Path":
                toolpath = geometry_engrave(mesh, cutter, settings)
            else:
                offset_mode = {
                    "On Path": "on",
                    "Outside": "outside",
                    "Inside": "inside",
                }[cut_type]
                toolpath = geometry_profile(
                    mesh,
                    cutter,
                    settings,
                    offset_mode=offset_mode,
                )
                if operation == "engrave":
                    toolpath.name = "Engrave"
                    toolpath.operation = "engrave"
        elif operation == "profile":
            toolpath = geometry_profile(mesh, cutter, settings)
        elif operation == "pocket":
            toolpath = geometry_pocket(mesh, cutter, settings)
        elif operation == "engrave":
            toolpath = geometry_engrave(mesh, cutter, settings)
        elif operation in {"rough", "finish", "rest"}:
            toolpath = finish_3d(
                mesh,
                cutter,
                settings,
                strategy=operation,
            )
        elif operation == "waterline":
            toolpath = waterline_3d(mesh, cutter, settings)
        else:
            raise ValueError(f"Unknown CAM operation: {operation}")

        generated_toolpaths = [toolpath]
        if (
            operation == "finish"
            and self._relief_style() is ReliefStyle.FULL_DEPTH
        ):
            cutout_settings = BasicCamSettings(
                safe_z_mm=settings.safe_z_mm,
                feed_mm_min=settings.feed_mm_min,
                plunge_feed_mm_min=settings.plunge_feed_mm_min,
                max_stepdown_mm=settings.max_stepdown_mm,
                stepover_fraction=settings.stepover_fraction,
                finish_stepover_fraction=settings.finish_stepover_fraction,
                overall_depth_mm=self.project.stock.thickness_mm,
                padding_mm=settings.padding_mm,
                usable_bit_length_mm=settings.usable_bit_length_mm,
                tab_height_mm=settings.tab_height_mm,
                tab_width_mm=settings.tab_width_mm,
                tab_count=settings.tab_count,
                tabs_enabled=self._tabs_enabled,
                milling_direction=settings.milling_direction,
                pocket_strategy=settings.pocket_strategy,
                relief_style=ReliefStyle.FULL_DEPTH,
                raster_axis=settings.raster_axis,
                raster_link_mode=settings.raster_link_mode,
                local_link_clearance_mm=settings.local_link_clearance_mm,
                direct_link_tolerance_mm=settings.direct_link_tolerance_mm,
                ramp_angle_deg=settings.ramp_angle_deg,
            )
            generated_toolpaths.append(
                geometry_profile(
                    mesh,
                    cutter,
                    cutout_settings,
                    name="Full Depth Cutout",
                    offset_mode="outside",
                )
            )

        for generated in generated_toolpaths:
            generated.source_item_id = item.item_id
            generated.source_item_name = item.name
        return generated_toolpaths

    def _calculate_toolpath_now(self) -> None:
        items = [
            item
            for item in self.project.items
            if item.mesh is not None
        ]
        if not items:
            self.statusBar().showMessage(
                "Add a mesh or created shape before generating toolpaths",
                4000,
            )
            return

        cutter = self.tool_combo.currentData()
        if not isinstance(cutter, Cutter):
            self.statusBar().showMessage("Select a valid cutter", 4000)
            return

        operation = self._active_cam_operation
        self.statusBar().showMessage(
            f"Calculating {operation} toolpaths for {len(items)} object"
            f"{'s' if len(items) != 1 else ''}…"
        )

        generated_toolpaths = []
        try:
            for item in items:
                generated_toolpaths.extend(
                    self._generate_toolpaths_for_item(
                        item,
                        cutter,
                        operation,
                    )
                )
        except ModuleNotFoundError as exc:
            missing = exc.name or "required Python package"
            message = (
                f"Toolpath generation requires the missing dependency "
                f"'{missing}'. Reinstall CarveFoundry dependencies."
            )
            self._set_activity_info(
                f"Toolpath calculation failed\n{message}"
            )
            self.statusBar().showMessage(message, 10000)
            return
        except (RuntimeError, ValueError) as exc:
            failed_item = item.name
            message = f"{failed_item}: {exc}"
            self._set_activity_info(
                f"Toolpath calculation failed\n{message}"
            )
            self.statusBar().showMessage(
                f"Toolpath failed: {message}",
                10000,
            )
            return

        if not generated_toolpaths:
            self.statusBar().showMessage(
                "The project geometry produced no toolpaths",
                5000,
            )
            return

        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
        if self._simulation_button is not None:
            self._simulation_button.setChecked(False)
        preview = self._toolpath_preview_window
        if preview is not None:
            preview.close()
            self._toolpath_preview_window = None

        self._before_ribbon_mutation(f"calculate {operation}")
        self.project.toolpaths = generated_toolpaths
        self._toolpaths_stale_reason = None
        self.viewport.set_toolpaths_visible(True)
        self.viewport.set_simulation_fraction(1.0)
        self.viewport.update()
        self._after_ribbon_mutation(f"calculate {operation}", True)

        total_moves = sum(len(path.moves) for path in generated_toolpaths)
        total_cut = sum(path.cutting_distance_mm for path in generated_toolpaths)
        total_rapid = sum(path.rapid_distance_mm for path in generated_toolpaths)
        total_minutes = sum(
            path.estimated_cutting_minutes for path in generated_toolpaths
        )
        object_count = len(
            {
                path.source_item_id
                for path in generated_toolpaths
                if path.source_item_id
            }
        )
        operation_names = sorted({path.name for path in generated_toolpaths})
        operation_summary = " + ".join(operation_names)
        self._set_activity_info(
            f"Toolpaths ready\n{operation_summary}\n\n"
            f"Objects: {object_count}\n"
            f"Cutter: {cutter.name}\n"
            f"Paths: {len(generated_toolpaths):,}\n"
            f"Moves: {total_moves:,}\n"
            f"Cut distance: {total_cut:.1f} mm\n"
            f"Rapid distance: {total_rapid:.1f} mm\n"
            f"Estimated cutting: {total_minutes:.1f} min"
        )
        self._sync_toolpath_output_state()
        self.statusBar().showMessage(
            f"Generated {len(generated_toolpaths)} toolpath"
            f"{'s' if len(generated_toolpaths) != 1 else ''} for "
            f"{object_count} object{'s' if object_count != 1 else ''}",
            6000,
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
    def _machine_profile(self) -> None:
        ports = MachineController.available_ports()
        port_names = [name for name, _label in ports]
        saved_port = str(self._settings.value("machine/port", ""))
        choices = port_names or ([saved_port] if saved_port else [""])
        if saved_port and saved_port not in choices:
            choices.insert(0, saved_port)

        form = _ActionForm(self, "Machine Profile")
        form.add_line(
            "name",
            "Machine name",
            str(self._settings.value("machine/name", "Onefinity / GRBL")),
        )
        form.add_combo(
            "port",
            "Serial port",
            choices,
            saved_port,
            editable=True,
        )
        form.add_int(
            "baud",
            "Baud rate",
            int(self._settings.value("machine/baud", 115200)),
            minimum=1200,
            maximum=2_000_000,
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        self._settings.setValue("machine/name", str(form.value("name")))
        self._settings.setValue("machine/port", str(form.value("port")).strip())
        self._settings.setValue("machine/baud", int(form.value("baud")))
        self._settings.sync()
        self.statusBar().showMessage("Machine profile saved", 3000)

    def _machine_work_area(self) -> None:
        form = _ActionForm(self, "Machine Work Area")
        form.add_double(
            "x",
            "X travel",
            float(self._settings.value("machine/work_x_mm", 816.0)),
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double(
            "y",
            "Y travel",
            float(self._settings.value("machine/work_y_mm", 816.0)),
            minimum=1.0,
            suffix=" mm",
        )
        form.add_double(
            "z",
            "Z travel",
            float(self._settings.value("machine/work_z_mm", 133.0)),
            minimum=1.0,
            suffix=" mm",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        for key in ("x", "y", "z"):
            self._settings.setValue(
                f"machine/work_{key}_mm",
                float(form.value(key)),
            )
        self._settings.sync()
        self.statusBar().showMessage("Machine work area saved", 3000)

    def _machine_origin(self) -> None:
        if not self.machine_controller.connected:
            self.statusBar().showMessage("Connect to the machine before setting origin", 5000)
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
        return GrblPostSettings(
            decimals=int(self._settings.value("post/decimals", 3)),
            include_comments=bool(
                self._settings.value("post/comments", True, type=bool)
            ),
        )

    def _connect_machine(self) -> None:
        if self.machine_controller.connected:
            self.machine_controller.disconnect()
            return

        # A checkable ribbon button toggles before this callback runs.  Treat
        # controller state as authoritative so canceled/failed attempts never
        # leave the UI looking connected.
        if self._machine_connect_button is not None:
            self._machine_connect_button.setChecked(False)

        port = str(self._settings.value("machine/port", "")).strip()
        baud = int(self._settings.value("machine/baud", 115200))
        if not port:
            self._machine_profile()
            port = str(self._settings.value("machine/port", "")).strip()
        if not port:
            self.statusBar().showMessage("No machine serial port configured", 5000)
            return
        self.statusBar().showMessage(f"Connecting to {port}…")
        if self.machine_controller.connect_serial(port, baud):
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
