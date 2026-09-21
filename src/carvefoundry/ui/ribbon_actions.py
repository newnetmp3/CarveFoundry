from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from carvefoundry.cam.basic_ops import detail_for_stepover_fraction
from carvefoundry.cam.job_process import GcodeRequest
from carvefoundry.cam.job_workflows import TilingSettings, find_safe_resume_index, plan_tiles
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.project import ProjectItem
from carvefoundry.core.smart_values import SmartValueError, SmartValues
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.units import ModelUnits

from .cam_generation_dialog import CamGenerationDialogMixin
from .machine_control import MachineController
from .ribbon_cam_actions import RibbonCamActionsMixin
from .ribbon_design_tools import RibbonDesignToolsMixin
from .ribbon_forms import _ActionForm
from .ribbon_machine_actions import RibbonMachineActionsMixin
from .toolpath_preview import ToolpathPreviewWindow


class RibbonActionsMixin(RibbonDesignToolsMixin, RibbonCamActionsMixin, RibbonMachineActionsMixin, CamGenerationDialogMixin):
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
            locked=item.locked,
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
        if indices and not self._selection_is_editable(indices):
            return
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
        if indices and not self._selection_is_editable(indices):
            return
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
        if indices and not self._selection_is_editable(indices):
            return
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
        if indices and not self._selection_is_editable(indices):
            return
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
        if indices and not self._selection_is_editable(indices):
            return
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
