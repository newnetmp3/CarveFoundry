"""Viewport transform lifecycle, transform Inspector, and view framing."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from ..core.mesh import mesh_asset_from_geometry
from ..core.project import ProjectItem
from ..core.transform import Transform3D
from ..core.units import ModelUnits


class TransformInteractionControllerMixin:
    """Own object transforms, context actions, snapping, and viewport framing."""

    def _viewport_transform_started(self, _index: int) -> None:
        """Lifecycle hook overridden by the project-history window."""

    def _viewport_transform_changed(self, index: int) -> None:
        if not 0 <= index < len(self.project.items):
            return
        row = index + 1
        if self.project_list.currentRow() != row:
            self.project_list.setCurrentRow(row)
            return
        item = self.project.items[index]
        self._sync_transform_controls(item)
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.set_selected_item(index)

    def _viewport_transform_finished(self, index: int) -> None:
        self._viewport_transform_changed(index)
        if not 0 <= index < len(self.project.items):
            return

        item = self.project.items[index]
        if self.viewport.transform_interaction_kind == "resize-object":
            reason = (
                "Text size"
                if item.kind.lower() == "text"
                else "Model size"
            )
            self._invalidate_toolpaths(reason)
            local_size = item.local_size_mm()
            if local_size is not None:
                self.statusBar().showMessage(
                    f"Resized {item.name} — "
                    f"W {local_size[0]:.2f}  H {local_size[1]:.2f} mm",
                    3000,
                )
            else:
                self.statusBar().showMessage(
                    f"Resized {item.name}",
                    3000,
                )
            return

        self._invalidate_toolpaths("Model position")
        x, y, z = item.transform.translation_mm
        self.statusBar().showMessage(
            f"Moved {item.name} — X {x:.2f}  Y {y:.2f}  Z {z:.2f} mm",
            3000,
        )

    def _before_context_transform(self, _index: int, _label: str) -> None:
        """History hook for a discrete viewport/context-menu transform."""

    def _after_context_transform(self, _index: int, _label: str) -> None:
        """History hook for a discrete viewport/context-menu transform."""

    def _apply_context_transform(
        self,
        label: str,
        transform_action,
    ) -> None:
        index = self._selected_item_index()
        item = self._selected_item()
        if index is None or item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return
        if not self._selection_is_editable([index]):
            return

        self._before_context_transform(index, label)
        transform_action(item)
        item.transform.validate()
        self._sync_transform_controls(item)
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.set_selected_item(index)
        self._invalidate_toolpaths("Model transform")
        self.viewport.update()
        self._after_context_transform(index, label)
        self.statusBar().showMessage(f"{label}: {item.name}", 3000)

    def _focus_transform_section(self, section: str) -> None:
        item = self._selected_item()
        if item is not None and item.locked:
            self._selection_is_editable()
            return
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return

        self._ensure_inspector_visible()

        controls = {
            "position": self.position_spins,
            "rotation": self.rotation_spins,
            "size": self.size_spins,
            "scale": self.scale_spins,
        }
        labels = {
            "position": "Position",
            "rotation": "Rotation",
            "size": "Size",
            "scale": "Scale",
        }
        target = controls.get(section, self.position_spins)
        accordion = getattr(self, "_transform_sections", {}).get(section)
        if accordion is not None:
            accordion.setExpanded(True)
        self.properties_panel.scroll_area.ensureWidgetVisible(
            target[0], 12, 45,
        )
        target[0].setFocus(Qt.FocusReason.OtherFocusReason)
        target[0].selectAll()
        self.statusBar().showMessage(
            f"{labels.get(section, 'Position')} editor ready for {item.name}",
            4000,
        )

    def _move_selected_to_stock_origin(self) -> None:
        def apply(item: ProjectItem) -> None:
            bounds = item.transformed_bounds_mm()
            if bounds is None:
                return
            tx, ty, tz = item.transform.translation_mm
            item.transform.translation_mm = (
                tx - float(bounds[0, 0]),
                ty - float(bounds[0, 1]),
                tz,
            )

        self._apply_context_transform("Move to stock origin", apply)

    def _bottom_selected_to_surface(self) -> None:
        def apply(item: ProjectItem) -> None:
            bounds = item.transformed_bounds_mm()
            if bounds is None:
                return
            tx, ty, tz = item.transform.translation_mm
            item.transform.translation_mm = (
                tx,
                ty,
                tz - float(bounds[0, 2]),
            )

        self._apply_context_transform("Bottom to Z0", apply)

    def _place_selected_at_stock_origin(self) -> None:
        def apply(item: ProjectItem) -> None:
            bounds = item.transformed_bounds_mm()
            if bounds is None:
                return
            tx, ty, tz = item.transform.translation_mm
            item.transform.translation_mm = (
                tx - float(bounds[0, 0]),
                ty - float(bounds[0, 1]),
                tz - float(bounds[1, 2]),
            )

        self._apply_context_transform("Place at stock origin", apply)

    def _rotate_selected_axis(self, axis: int, degrees_delta: float) -> None:
        axis_name = "XYZ"[axis]
        plane_name = ("YZ", "XZ", "XY")[axis]

        def apply(item: ProjectItem) -> None:
            rotation = list(item.transform.rotation_deg)
            rotation[axis] += degrees_delta
            item.transform.rotation_deg = tuple(rotation)

        sign = "+" if degrees_delta >= 0 else ""
        self._apply_context_transform(
            (
                f"Rotate around {axis_name} {sign}{degrees_delta:g}° "
                f"({plane_name} plane)"
            ),
            apply,
        )

    def _reset_selected_rotation(self) -> None:
        self._apply_context_transform(
            "Reset rotation",
            lambda item: setattr(
                item.transform,
                "rotation_deg",
                (0.0, 0.0, 0.0),
            ),
        )

    def _scale_selected_uniform(self, factor: float) -> None:
        def apply(item: ProjectItem) -> None:
            item.transform.scale_xyz = tuple(
                float(value) * factor for value in item.transform.scale_xyz
            )

        self._apply_context_transform(f"Scale {factor:g}×", apply)

    def _reset_selected_scale(self) -> None:
        self._apply_context_transform(
            "Reset scale",
            lambda item: setattr(
                item.transform,
                "scale_xyz",
                (1.0, 1.0, 1.0),
            ),
        )

    def _fit_selected_inside_stock(self) -> None:
        def apply(item: ProjectItem) -> None:
            bounds = item.transformed_bounds_mm()
            if bounds is None:
                return
            dimensions = bounds[1] - bounds[0]
            width = max(float(dimensions[0]), 1e-9)
            height = max(float(dimensions[1]), 1e-9)
            factor = 0.95 * min(
                float(self.project.stock.width_mm) / width,
                float(self.project.stock.height_mm) / height,
            )
            item.transform.scale_xyz = tuple(
                float(value) * factor for value in item.transform.scale_xyz
            )

            fitted_bounds = item.transformed_bounds_mm()
            if fitted_bounds is None:
                return
            center = fitted_bounds.mean(axis=0)
            tx, ty, tz = item.transform.translation_mm
            item.transform.translation_mm = (
                tx + float(self.project.stock.width_mm) / 2.0 - float(center[0]),
                ty + float(self.project.stock.height_mm) / 2.0 - float(center[1]),
                tz,
            )

        self._apply_context_transform("Fit inside stock", apply)

    @staticmethod
    def _add_context_action(menu: QMenu, text: str, callback):
        """Add an action with a PySide-safe triggered(bool) adapter."""

        action = menu.addAction(text)
        action.triggered.connect(
            lambda _checked=False, function=callback: function()
        )
        return action

    def _show_viewport_item_context_menu(self, index: int, global_pos) -> None:
        if not 0 <= index < len(self.project.items):
            return
        self._viewport_select_item(index)
        item = self.project.items[index]

        menu = QMenu(self)
        menu.addSection(item.name)

        if item.kind.lower() == "text":
            self._add_context_action(
                menu,
                "Edit Text…",
                self._focus_text_editor,
            )
            menu.addSeparator()

        edit_menu = menu.addMenu("Edit Transform")
        self._add_context_action(
            edit_menu,
            "Move / Position…",
            lambda: self._focus_transform_section("position"),
        )
        self._add_context_action(
            edit_menu,
            "Rotate…",
            lambda: self._focus_transform_section("rotation"),
        )
        self._add_context_action(
            edit_menu,
            "Size…",
            lambda: self._focus_transform_section("size"),
        )
        self._add_context_action(
            edit_menu,
            "Scale…",
            lambda: self._focus_transform_section("scale"),
        )

        move_menu = menu.addMenu("Move / Place")
        self._add_context_action(
            move_menu,
            "Center in Stock (XY)",
            self._center_selected_xy,
        )
        self._add_context_action(
            move_menu,
            "Move to Stock Origin (XY)",
            self._move_selected_to_stock_origin,
        )
        self._add_context_action(
            move_menu,
            "Place at Stock Origin + Top Z0",
            self._place_selected_at_stock_origin,
        )
        move_menu.addSeparator()
        self._add_context_action(
            move_menu,
            "Top to Stock Surface (Z0)",
            self._top_selected_to_surface,
        )
        self._add_context_action(
            move_menu,
            "Bottom to Stock Surface (Z0)",
            self._bottom_selected_to_surface,
        )

        rotate_menu = menu.addMenu("Rotate 90°")
        for axis in range(3):
            axis_name = "XYZ"[axis]
            plane_name = ("YZ", "XZ", "XY")[axis]
            self._add_context_action(
                rotate_menu,
                f"Around {axis_name} / {plane_name} plane +90°",
                lambda a=axis: self._rotate_selected_axis(a, 90.0),
            )
            self._add_context_action(
                rotate_menu,
                f"Around {axis_name} / {plane_name} plane -90°",
                lambda a=axis: self._rotate_selected_axis(a, -90.0),
            )
        rotate_menu.addSeparator()
        self._add_context_action(
            rotate_menu,
            "Reset Rotation",
            self._reset_selected_rotation,
        )

        scale_menu = menu.addMenu("Scale")
        self._add_context_action(
            scale_menu,
            "50%",
            lambda: self._scale_selected_uniform(0.5),
        )
        self._add_context_action(
            scale_menu,
            "200%",
            lambda: self._scale_selected_uniform(2.0),
        )
        self._add_context_action(
            scale_menu,
            "Fit Inside Stock",
            self._fit_selected_inside_stock,
        )
        scale_menu.addSeparator()
        self._add_context_action(
            scale_menu,
            "Reset Scale",
            self._reset_selected_scale,
        )

        menu.addSeparator()
        self._add_context_action(
            menu,
            "Reset Full Transform",
            self._reset_selected_transform,
        )
        menu.addSeparator()
        self._add_context_action(
            menu,
            "Duplicate",
            self._duplicate_selected_item,
        )
        self._add_context_action(
            menu,
            "Delete",
            self._delete_selected_item,
        )
        menu.exec(global_pos)

    def _sync_transform_controls(self, item: ProjectItem) -> None:
        self._updating_transform_controls = True
        try:
            unit_index = self.source_units_combo.findData(item.source_units)
            if unit_index >= 0:
                self.source_units_combo.setCurrentIndex(unit_index)
            for spin, value in zip(
                self.position_spins,
                item.transform.translation_mm,
                strict=True,
            ):
                spin.setValue(value)
            for spin, value in zip(
                self.rotation_spins,
                item.transform.rotation_deg,
                strict=True,
            ):
                spin.setValue(value)
            local_size = item.local_size_mm()
            if local_size is not None:
                for spin, value in zip(
                    self.size_spins,
                    local_size,
                    strict=True,
                ):
                    spin.setValue(float(value))
            for spin, value in zip(
                self.scale_spins,
                item.transform.scale_xyz,
                strict=True,
            ):
                spin.setValue(value)
        finally:
            self._updating_transform_controls = False

    def _source_units_changed(self, _index: int) -> None:
        if self._updating_transform_controls:
            return
        item = self._selected_item()
        if item is not None and item.locked:
            self._selection_is_editable()
            return
        if item is None or item.mesh is None:
            return
        units = self.source_units_combo.currentData()
        if not isinstance(units, ModelUnits) or units is item.source_units:
            return
        item.source_units = units
        item.transform = self.project.default_transform_for_mesh(item.mesh, units)
        self._invalidate_toolpaths("Model units")
        self._refresh_project_list(self.project_list.currentRow())
        self.viewport.fit_view()
        self.statusBar().showMessage(
            f"Interpreting {item.name} as {units.display_name}; placement reset",
            5000,
        )

    def _locked_transform_axes(self) -> tuple[bool, bool, bool]:
        return tuple(
            checkbox.isChecked()
            for checkbox in self.lock_axis_checks
        )

    def _transform_control_changed(self, value: float) -> None:
        if self._updating_transform_controls:
            return

        item = self._selected_item()
        if item is not None and item.locked:
            self._selection_is_editable()
            return
        if item is None or item.mesh is None:
            return

        sender = self.sender()
        current_scale = np.asarray(item.transform.scale_xyz, dtype=float)
        new_scale = current_scale.copy()
        locked_axes = self._locked_transform_axes()

        if sender in self.size_spins:
            axis = self.size_spins.index(sender)
            current_size = item.local_size_mm()
            if current_size is None:
                return
            axis_size = float(current_size[axis])
            if axis_size <= 1e-12:
                self.statusBar().showMessage(
                    f"Cannot resize zero-length {'XYZ'[axis]} dimension",
                    3500,
                )
                self._sync_transform_controls(item)
                return

            factor = float(value) / axis_size
            affected = (
                [
                    index
                    for index, locked in enumerate(locked_axes)
                    if locked
                ]
                if locked_axes[axis]
                else [axis]
            )
            if axis not in affected:
                affected.append(axis)
            for index in affected:
                new_scale[index] = current_scale[index] * factor

        elif sender in self.scale_spins:
            axis = self.scale_spins.index(sender)
            requested_scale = float(value)
            current_axis_scale = float(current_scale[axis])
            if current_axis_scale <= 1e-12:
                return

            factor = requested_scale / current_axis_scale
            affected = (
                [
                    index
                    for index, locked in enumerate(locked_axes)
                    if locked
                ]
                if locked_axes[axis]
                else [axis]
            )
            if axis not in affected:
                affected.append(axis)
            for index in affected:
                new_scale[index] = current_scale[index] * factor

        item.transform.translation_mm = tuple(
            spin.value() for spin in self.position_spins
        )
        item.transform.rotation_deg = tuple(
            spin.value() for spin in self.rotation_spins
        )
        item.transform.scale_xyz = tuple(float(value) for value in new_scale)
        item.transform.validate()
        self._invalidate_toolpaths("Model transform")

        self._sync_transform_controls(item)
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.update()

    def _center_selected_xy(self) -> None:
        item = self._selected_item()
        if item is not None and item.locked:
            self._selection_is_editable()
            return
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return

        transformed = item.transformed_mesh()
        assert transformed is not None
        bounds = np.asarray(transformed.bounds, dtype=float)
        center = bounds.mean(axis=0)
        tx, ty, tz = item.transform.translation_mm
        item.transform.translation_mm = (
            tx + self.project.stock.width_mm / 2.0 - center[0],
            ty + self.project.stock.height_mm / 2.0 - center[1],
            tz,
        )
        self._sync_transform_controls(item)
        self._invalidate_toolpaths("Model position")
        self._update_properties(self.project_list.currentRow())
        self.viewport.update()
        self.statusBar().showMessage("Centered selected mesh on stock", 3000)

    def _top_selected_to_surface(self) -> None:
        item = self._selected_item()
        if item is not None and item.locked:
            self._selection_is_editable()
            return
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return

        transformed = item.transformed_mesh()
        assert transformed is not None
        bounds = np.asarray(transformed.bounds, dtype=float)
        tx, ty, tz = item.transform.translation_mm
        item.transform.translation_mm = (tx, ty, tz - bounds[1, 2])
        self._sync_transform_controls(item)
        self._invalidate_toolpaths("Model position")
        self._update_properties(self.project_list.currentRow())
        self.viewport.update()
        self.statusBar().showMessage("Placed selected mesh top at stock Z0", 3000)

    def _reset_selected_transform(self) -> None:
        item = self._selected_item()
        if item is not None and item.locked:
            self._selection_is_editable()
            return
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return

        item.transform = self.project.default_transform_for_mesh(
            item.mesh,
            item.source_units,
        )
        self._sync_transform_controls(item)
        self._invalidate_toolpaths("Model transform")
        self._update_properties(self.project_list.currentRow())
        self.viewport.update()
        self.statusBar().showMessage("Reset selected mesh transform", 3000)

    def _focus_transform_controls(self) -> None:
        item = self._selected_item()
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return
        self.position_spins[0].setFocus()

    def _fit_view(self) -> None:
        self.viewport.fit_view()

    def _frame_selected(self) -> None:
        if not self.viewport.frame_selected():
            self.statusBar().showMessage(
                "Select one or more visible design objects to frame",
                3000,
            )
            return
        self.statusBar().showMessage("Framed selected object(s)", 2000)

    def _isolate_selected(self) -> None:
        if not self.viewport.isolate_selected():
            self.statusBar().showMessage(
                "Select one or more visible design objects to isolate",
                3000,
            )
            return
        self._sync_selection_action_state()
        self.statusBar().showMessage(
            "Isolate view enabled • CAM still uses the full project",
            3500,
        )

    def _exit_isolate(self) -> None:
        if not self.viewport.isolated:
            self.statusBar().showMessage("Isolate view is not active", 2000)
            return
        self.viewport.show_all_items()
        self._sync_selection_action_state()
        self.statusBar().showMessage("Returned to full project view", 2000)

    def _set_transform_orientation(self, orientation: str) -> None:
        normalized = str(orientation).strip().lower()
        self.viewport.set_transform_orientation(normalized)
        if hasattr(self, "transform_orientation_combo"):
            index = self.transform_orientation_combo.findData(normalized)
            if index >= 0:
                self.transform_orientation_combo.blockSignals(True)
                try:
                    self.transform_orientation_combo.setCurrentIndex(index)
                finally:
                    self.transform_orientation_combo.blockSignals(False)
        for key, target in (
            ("transform_global", "global"),
            ("transform_local", "local"),
        ):
            action = self._ui_actions.get(key)
            if action is not None:
                action.setChecked(normalized == target)
        self._settings.setValue("viewport/transform_orientation", normalized)
        self.statusBar().showMessage(
            f"Transform orientation: {normalized.title()}",
            2000,
        )

    def _transform_orientation_changed(self, _index: int) -> None:
        orientation = self.transform_orientation_combo.currentData()
        if orientation in {"global", "local"}:
            self._set_transform_orientation(str(orientation))

    def _transform_snap_changed(self, _value=None) -> None:
        enabled = self.transform_snap_check.isChecked()
        step = float(self.transform_snap_step_spin.value())
        self.transform_snap_step_spin.setEnabled(enabled)
        self.viewport.set_transform_snapping(enabled, step)
        action = self._ui_actions.get("snap_transform")
        if action is not None:
            action.setChecked(enabled)
        self._settings.setValue("viewport/transform_snap_enabled", enabled)
        self._settings.setValue("viewport/transform_snap_step_mm", step)

    def _toggle_transform_snap(self) -> None:
        self.transform_snap_check.setChecked(
            not self.transform_snap_check.isChecked()
        )

    def _apply_selected_transform_components(
        self,
        *,
        apply_rotation: bool,
        apply_scale: bool,
        label: str,
    ) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if indices and not self._selection_is_editable(indices):
            return
        if not indices:
            self.statusBar().showMessage(
                "Select one or more mesh objects first",
                3000,
            )
            return

        self._before_ribbon_mutation(label)
        changed = 0
        skipped_text = 0
        selected_after = list(indices)

        for index in indices:
            if not 0 <= index < len(self.project.items):
                continue
            item = self.project.items[index]
            if item.mesh is None:
                continue
            if item.kind.lower() == "text":
                skipped_text += 1
                continue

            rotation = (
                item.transform.rotation_deg
                if apply_rotation
                else (0.0, 0.0, 0.0)
            )
            scale = (
                item.transform.scale_xyz
                if apply_scale
                else (1.0, 1.0, 1.0)
            )
            rotation_changed = any(abs(value) > 1e-9 for value in rotation)
            scale_changed = any(abs(value - 1.0) > 1e-9 for value in scale)
            if not rotation_changed and not scale_changed:
                continue

            source_mesh_mm = item.source_mesh_mm()
            if source_mesh_mm is None:
                continue
            baked = Transform3D(
                rotation_deg=rotation,
                scale_xyz=scale,
            ).apply_to_mesh(source_mesh_mm)

            translation = item.transform.translation_mm
            remaining_rotation = (
                (0.0, 0.0, 0.0)
                if apply_rotation
                else item.transform.rotation_deg
            )
            remaining_scale = (
                (1.0, 1.0, 1.0)
                if apply_scale
                else item.transform.scale_xyz
            )
            item.mesh = mesh_asset_from_geometry(baked)
            item.source_units = ModelUnits.MILLIMETERS
            item.source_path = None
            item.transform = Transform3D(
                translation_mm=translation,
                rotation_deg=remaining_rotation,
                scale_xyz=remaining_scale,
            )
            changed += 1

        if changed:
            self._invalidate_toolpaths("Applied model transform")
            self._refresh_project_list(self.project_list.currentRow())
            valid_selection = [
                index
                for index in selected_after
                if 0 <= index < len(self.project.items)
            ]
            if valid_selection:
                self._select_project_indices(
                    valid_selection,
                    primary=valid_selection[-1],
                )
            self.viewport.update()

        self._after_ribbon_mutation(label, bool(changed))
        if changed:
            suffix = (
                f" • skipped {skipped_text} editable text object"
                f"{'s' if skipped_text != 1 else ''}"
                if skipped_text
                else ""
            )
            self.statusBar().showMessage(
                f"{label.title()} on {changed} object"
                f"{'s' if changed != 1 else ''}{suffix}",
                4500,
            )
        elif skipped_text:
            self.statusBar().showMessage(
                "Editable text keeps its live font transform; "
                "Apply Transform is for mesh-based objects",
                4500,
            )
        else:
            self.statusBar().showMessage(
                "Selected object transform is already applied",
                3000,
            )

    def _apply_selected_scale(self) -> None:
        self._apply_selected_transform_components(
            apply_rotation=False,
            apply_scale=True,
            label="apply scale",
        )

    def _apply_selected_rotation_scale(self) -> None:
        self._apply_selected_transform_components(
            apply_rotation=True,
            apply_scale=True,
            label="apply rotation and scale",
        )

