"""Project/Inspector list presentation and stock-edit synchronization.

This domain owns the Layers/Object selector representation, Inspector visibility,
item rename/visibility/lock updates, and stock dimension controls. Selection and
transform behavior live in selection_transform_controller.py.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from ..core.project import ProjectItem
from .layers_popup import LAYER_LOCK_ROLE


class ProjectInspectorControllerMixin:
    """Synchronize project metadata with Layers/Object selector and stock UI."""

    @staticmethod
    def _number(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    @classmethod
    def _source_dimensions_text(cls, item: ProjectItem) -> str:
        if item.mesh is None:
            return ""
        dimensions = " × ".join(cls._number(value) for value in item.mesh.dimensions)
        return f"{dimensions} {item.source_units.value}"

    @classmethod
    def _mesh_properties_text(cls, item: ProjectItem) -> str:
        mesh = item.mesh
        if mesh is None:
            return f"{item.name}\n{item.kind.upper()} source"

        local_size = item.local_size_mm()
        bounds = item.transformed_bounds_mm()
        assert local_size is not None and bounds is not None

        size_text = " × ".join(
            cls._number(float(value))
            for value in local_size
        )
        world_size = bounds[1] - bounds[0]
        world_size_text = " × ".join(
            cls._number(float(value))
            for value in world_size
        )
        position = " / ".join(
            cls._number(float(value))
            for value in item.transform.translation_mm
        )
        rotation = " / ".join(
            f"{cls._number(float(value))}°"
            for value in item.transform.rotation_deg
        )
        scale = " / ".join(
            cls._number(float(value))
            for value in item.transform.scale_xyz
        )
        kind = "STL" if item.kind.lower() == "stl" else item.kind.upper()
        group = "\nGrouped object" if item.group_id else ""
        text_details = ""
        if item.kind.lower() == "text" and item.text_properties is not None:
            properties = item.text_properties
            style_parts = [
                properties.font_style or "Regular",
                f"{cls._number(properties.size_pt)} pt",
            ]
            if properties.bold:
                style_parts.append("Bold")
            if properties.italic:
                style_parts.append("Italic")
            text_details = (
                "\nText: "
                + " • ".join(style_parts)
                + f"\nFont: {properties.font_family or 'System default'}"
                + f"\nGeometry: {properties.geometry_mode.title()}"
            )

        return (
            f"{item.name}\n"
            f"{kind} • {mesh.face_count:,} faces{group}{text_details}\n\n"
            f"Size XYZ: {size_text} mm\n"
            f"World bounds: {world_size_text} mm\n"
            f"Position XYZ: {position} mm\n"
            f"Rotation XYZ: {rotation}\n"
            f"Scale XYZ: {scale}\n\n"
            f"Source: {cls._source_dimensions_text(item)}"
        )

    def _stock_list_text(self) -> str:
        stock = self.project.stock
        return (
            f"Stock  {self._number(stock.width_mm)} × "
            f"{self._number(stock.height_mm)} × "
            f"{self._number(stock.thickness_mm)} mm"
        )

    def _item_list_text(self, item: ProjectItem) -> str:
        return item.name

    @staticmethod
    def _object_selector_text(item: ProjectItem) -> str:
        group = " • Grouped" if item.group_id else ""
        kind = "STL" if item.kind.lower() == "stl" else item.kind.upper()
        preview = ""
        if item.kind.lower() == "text" and item.text_properties is not None:
            first_line = " ".join(
                item.text_properties.content.splitlines()
            ).strip()
            if first_line:
                if len(first_line) > 34:
                    first_line = first_line[:31].rstrip() + "…"
                preview = f' • “{first_line}”'
        return f"{item.name}  [{kind}]{group}{preview}"

    @classmethod
    def _item_tooltip(cls, item: ProjectItem) -> str:
        kind = "STL" if item.kind.lower() == "stl" else item.kind.upper()
        group_text = "\nGrouped object" if item.group_id else ""
        source_size = cls._source_dimensions_text(item)
        text_preview = ""
        if item.kind.lower() == "text" and item.text_properties is not None:
            content_preview = " ".join(
                item.text_properties.content.splitlines()
            ).strip()
            if len(content_preview) > 90:
                content_preview = content_preview[:87].rstrip() + "…"
            if content_preview:
                text_preview = f"\nContent: {content_preview}"
        return (
            f"{kind} • {item.name}{group_text}"
            + text_preview
            + (f"\nSource size: {source_size}" if source_size else "")
            + "\nEye: show/hide • Lock: protect from edits"
            + "\nDouble-click name or press F2 to rename."
        )

    def _refresh_project_list(self, selected_row: int = 0) -> None:
        self._updating_project_list = True
        self._updating_object_selector = True
        self.project_list.blockSignals(True)
        self.object_selector.blockSignals(True)
        try:
            self.project_list.clear()
            self.object_selector.clear()

            self.project_list.addItem(self._stock_list_text())
            self.object_selector.addItem("Stock")

            for project_item in self.project.items:
                list_item = QListWidgetItem(project_item.name)
                list_item.setToolTip(self._item_tooltip(project_item))
                list_item.setFlags(
                    list_item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEditable
                )
                list_item.setCheckState(
                    Qt.CheckState.Checked
                    if project_item.visible
                    else Qt.CheckState.Unchecked
                )
                list_item.setData(LAYER_LOCK_ROLE, project_item.locked)
                if project_item.locked:
                    list_item.setFlags(
                        list_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                    )
                self.project_list.addItem(list_item)
                self.object_selector.addItem(
                    self._object_selector_text(project_item)
                )

            selected_row = max(
                0,
                min(selected_row, self.project_list.count() - 1),
            )
            self.project_list.setCurrentRow(selected_row)
            self.object_selector.setCurrentIndex(selected_row)
            self.layers_popup.set_object_count(len(self.project.items))
        finally:
            self.project_list.blockSignals(False)
            self.object_selector.blockSignals(False)
            self._updating_project_list = False
            self._updating_object_selector = False
        self._update_properties(selected_row)

    def _object_selector_changed(self, row: int) -> None:
        if self._updating_object_selector:
            return
        row = max(0, min(int(row), self.project_list.count() - 1))
        if row <= 0:
            self._select_project_indices([])
        else:
            self._select_project_indices([row - 1], primary=row - 1)

    def _show_layers_popup(self) -> None:
        """Reveal and focus the permanently embedded Inspector Layers list."""
        if not hasattr(self, "layers_popup"):
            return
        self._ensure_inspector_visible()
        self.properties_panel.scroll_area.ensureWidgetVisible(self.layers_popup)
        self.project_list.setFocus(Qt.FocusReason.OtherFocusReason)

    def _active_cutter_changed(self, _index: int) -> None:
        cutter = self.tool_combo.currentData()
        if hasattr(self, "_cutter_menu_actions"):
            current = self.tool_combo.currentIndex()
            for index, action in enumerate(self._cutter_menu_actions):
                action.setChecked(index == current)
        if cutter is not None and hasattr(cutter, "name"):
            self._settings.setValue("tools/selected_name", cutter.name)
            self._settings.sync()
            # Generated toolpaths carry their own cutter geometry; changing
            # the UI's *next* cutter must never erase earlier cutter stages.
        self._refresh_cam_detail_readouts()
        if hasattr(self, "text_cnc_hint"):
            self._update_text_cnc_hint()

    def _ensure_inspector_visible(self) -> None:
        self.properties_panel.show()
        self.inspector_button.setChecked(True)
        if hasattr(self, "tool_rail"):
            rail_button = self.tool_rail.buttons.get("inspector")
            if rail_button is not None:
                rail_button.setChecked(True)
        self._set_option_checked("properties_panel", True)

        sizes = self.workspace_splitter.sizes()
        if len(sizes) == 2 and sizes[1] < 40:
            preferred = self._properties_panel_default_width()
            total = max(sum(sizes), preferred + 520)
            self.workspace_splitter.setSizes(
                [max(520, total - preferred), preferred]
            )
        self._save_interface_options()

    def _focus_stock_section(self) -> None:
        self._ensure_inspector_visible()
        if self.project_list.currentRow() != 0:
            self.project_list.setCurrentRow(0)
        self.stock_spins[0].setFocus(Qt.FocusReason.OtherFocusReason)
        self.stock_spins[0].selectAll()
        self.statusBar().showMessage("Stock setup ready", 2500)

    def _project_item_changed(self, list_item: QListWidgetItem) -> None:
        if self._updating_project_list:
            return
        row = self.project_list.row(list_item)
        if row <= 0:
            return
        index = row - 1
        if index >= len(self.project.items):
            return

        project_item = self.project.items[index]
        visible = list_item.checkState() == Qt.CheckState.Checked
        visibility_changed = visible != project_item.visible
        project_item.visible = visible
        locked = bool(list_item.data(LAYER_LOCK_ROLE))
        lock_changed = locked != project_item.locked
        project_item.locked = locked

        requested_name = list_item.text().strip()
        if not requested_name:
            requested_name = project_item.name

        other_names = {
            item.name
            for other_index, item in enumerate(self.project.items)
            if other_index != index
        }
        unique_name = requested_name
        if unique_name in other_names:
            base = requested_name
            number = 2
            while f"{base} {number}" in other_names:
                number += 1
            unique_name = f"{base} {number}"

        renamed = unique_name != project_item.name
        if renamed and project_item.locked:
            self._updating_project_list = True
            try:
                list_item.setText(project_item.name)
            finally:
                self._updating_project_list = False
            renamed = False
        if lock_changed:
            flags = list_item.flags()
            list_item.setFlags(
                flags & ~Qt.ItemFlag.ItemIsEditable
                if locked else flags | Qt.ItemFlag.ItemIsEditable
            )
            if locked:
                self.viewport.set_node_edit_mode(False)
        if renamed:
            old_name = project_item.name
            project_item.name = unique_name
            self._updating_project_list = True
            list_item.blockSignals(True)
            try:
                list_item.setText(unique_name)
            finally:
                list_item.blockSignals(False)
                self._updating_project_list = False

            self.object_selector.blockSignals(True)
            try:
                self.object_selector.setItemText(
                    row,
                    self._object_selector_text(project_item),
                )
            finally:
                self.object_selector.blockSignals(False)

            list_item.setToolTip(self._item_tooltip(project_item))
            self.selection_info.setText(
                self._mesh_properties_text(project_item)
            )
            if any(
                path.source_item_id == project_item.item_id
                for path in self.project.toolpaths
            ):
                self._sync_toolpath_state_from_project()
            self.statusBar().showMessage(
                f"Renamed {old_name} → {unique_name}",
                2500,
            )
        elif lock_changed:
            state = "locked" if locked else "unlocked"
            self.statusBar().showMessage(
                f"{project_item.name} {state}", 2500,
            )
        elif visibility_changed:
            state = "visible" if visible else "hidden"
            self.statusBar().showMessage(
                f"{project_item.name} {state}",
                2000,
            )

        if lock_changed:
            self._update_properties(self.project_list.currentRow())
        self.viewport.update()

    def _sync_stock_controls(self) -> None:
        self._updating_stock_controls = True
        try:
            for spin, value in zip(
                self.stock_spins,
                (
                    self.project.stock.width_mm,
                    self.project.stock.height_mm,
                    self.project.stock.thickness_mm,
                ),
                strict=True,
            ):
                spin.setValue(value)
        finally:
            self._updating_stock_controls = False

    def _stock_control_changed(self, _value: float) -> None:
        if self._updating_stock_controls:
            return
        width, height, thickness = (spin.value() for spin in self.stock_spins)
        self.project.stock.width_mm = width
        self.project.stock.height_mm = height
        self.project.stock.thickness_mm = thickness
        self._invalidate_toolpaths("Stock dimensions")
        if self.project_list.count():
            self.project_list.item(0).setText(self._stock_list_text())
        self.selection_info.setText(
            "Stock\n"
            f"{self._number(width)} × {self._number(height)} × "
            f"{self._number(thickness)} mm"
        )
        self.viewport.update()

