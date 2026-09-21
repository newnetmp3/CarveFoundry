"""Design-object selection synchronization and Inspector selection state."""
from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel

from ..core.planar_operations import PLANAR_KINDS
from ..core.project import ProjectItem


class SelectionControllerMixin:
    """Own multi-selection state shared by Layers, Inspector, and viewport."""

    def _selection_is_editable(self, indices: list[int] | None = None) -> bool:
        """A lock protects edits without preventing selection or visibility toggles."""
        if indices is None:
            indices = self._selected_design_indices(expand_groups=True)
        protected = [
            self.project.items[index].name for index in indices
            if 0 <= index < len(self.project.items)
            and self.project.items[index].locked
        ]
        if not protected:
            return True
        self.statusBar().showMessage(
            "Unlock layer(s) before editing: " + ", ".join(protected[:3]),
            4000,
        )
        return False

    def _sync_selection_action_state(self) -> None:
        if not hasattr(self, "project_list"):
            return

        item = self._selected_item()
        indices = self._selected_design_indices()
        expanded_indices = self._selected_design_indices(expand_groups=True)
        has_selection = bool(indices)
        editable_selection = bool(indices) and not any(
            self.project.items[index].locked
            for index in expanded_indices
        )
        selection_count = len(indices)
        has_mesh = bool(
            selection_count == 1
            and item is not None
            and item.mesh is not None
            and not item.locked
        )
        has_grouped = any(
            self.project.items[index].group_id is not None
            for index in indices
            if 0 <= index < len(self.project.items)
        )
        current_index = self._selected_item_index()

        if self._calculate_button is not None:
            self._calculate_button.setEnabled(True)
            self._calculate_button.setToolTip(
                "Review requirements and generate toolpaths. Surface / Face "
                "can run from stock alone; other operations require geometry."
            )
        if self.generate_toolpaths_button is not None:
            self.generate_toolpaths_button.setEnabled(True)
            self.generate_toolpaths_button.setToolTip(
                "Review all requirements and options, then generate toolpaths. "
                "Surface / Face can run from stock alone."
            )

        for button in self._model_selection_buttons:
            button.setEnabled(has_mesh)

        has_bakeable_mesh = any(
            0 <= index < len(self.project.items)
            and self.project.items[index].mesh is not None
            and self.project.items[index].kind.lower() != "text"
            for index in indices
        )
        for key, enabled in (
            ("frame_selected", has_selection),
            ("isolate_selected", has_selection),
            ("exit_isolate", self.viewport.isolated),
            ("apply_scale", has_bakeable_mesh and editable_selection),
            ("apply_rotation_scale", has_bakeable_mesh and editable_selection),
        ):
            action = self._ui_actions.get(key)
            if action is not None:
                action.setEnabled(enabled)

        enabled_by_action = {
            "cut": editable_selection,
            "copy": has_selection,
            "paste": bool(self._clipboard_items),
            "delete": editable_selection,
            "align": editable_selection,
            "center": editable_selection,
            "group": editable_selection and selection_count >= 2,
            "ungroup": editable_selection and has_grouped,
            "duplicate": editable_selection,
            "move_up": editable_selection and current_index is not None and current_index > 0,
            "move_down": (
                editable_selection
                and current_index is not None
                and current_index < len(self.project.items) - 1
            ),
        }
        for name, enabled in enabled_by_action.items():
            button = self._selection_action_buttons.get(name)
            if button is not None:
                button.setEnabled(enabled)
            if hasattr(self, "layers_popup"):
                popup_button = self.layers_popup.action_buttons.get(name)
                if popup_button is not None:
                    popup_button.setEnabled(enabled)

        planar_selection = bool(indices) and all(
            self.project.items[index].mesh is not None
            and self.project.items[index].kind.lower() in PLANAR_KINDS
            for index in indices
        )
        for key, enabled in (
            ("vector_union", planar_selection and selection_count >= 2),
            ("vector_subtract", planar_selection and selection_count >= 2),
            ("vector_intersect", planar_selection and selection_count >= 2),
            ("vector_offset", planar_selection and selection_count == 1),
        ):
            self._ui_actions[key].setEnabled(enabled)

        if hasattr(self, "tool_rail"):
            self.tool_rail.set_tool_enabled("arrange", has_selection)
            self.tool_rail.set_tool_enabled("cam", True)

    def _select_project_indices(
        self,
        indices: list[int] | tuple[int, ...] | set[int],
        *,
        primary: int | None = None,
    ) -> None:
        """Synchronize a design-object selection across Layers and viewport."""

        valid = sorted(
            {
                int(index)
                for index in indices
                if 0 <= int(index) < len(self.project.items)
            }
        )
        self.project_list.blockSignals(True)
        try:
            self.project_list.clearSelection()
            for index in valid:
                item = self.project_list.item(index + 1)
                if item is not None:
                    item.setSelected(True)

            if primary not in valid:
                primary = valid[-1] if valid else None
            row = primary + 1 if primary is not None else 0
            self.project_list.setCurrentRow(
                row,
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )
        finally:
            self.project_list.blockSignals(False)

        self._project_selection_changed()

    def _viewport_selection_requested(
        self,
        indices: object,
        mode: str,
    ) -> None:
        """Apply replace/add/toggle selection requests from the viewport."""

        requested = [
            int(index)
            for index in (indices if isinstance(indices, (list, tuple, set)) else [])
            if 0 <= int(index) < len(self.project.items)
        ]
        selected = set(self._selected_design_indices())
        incoming = set(requested)
        if mode == "add":
            selected |= incoming
        elif mode == "toggle":
            selected ^= incoming
        else:
            selected = incoming

        primary = None
        for index in reversed(requested):
            if index in selected:
                primary = index
                break
        if primary is None:
            current = self._selected_item_index()
            if current in selected:
                primary = current
        self._select_project_indices(selected, primary=primary)

    def _select_all_design_items(self) -> None:
        """Select every design object in the project."""

        if not self.project.items:
            self._select_project_indices([])
            self.statusBar().showMessage("No design objects to select", 2000)
            return
        indices = list(range(len(self.project.items)))
        self._select_project_indices(indices, primary=indices[-1])
        self.statusBar().showMessage(
            f"Selected all {len(indices)} design objects",
            2000,
        )

    def _viewport_select_item(self, index: int) -> None:
        """Compatibility adapter for single-object viewport selection."""

        if 0 <= index < len(self.project.items):
            self._select_project_indices([index], primary=index)
        else:
            self._select_project_indices([])

    def _project_selection_changed(self) -> None:
        """Keep Inspector, viewport highlights, and action state synchronized."""

        if self._updating_project_list:
            return
        indices = self._selected_design_indices()
        if indices:
            current = self._selected_item_index()
            primary = current if current in indices else indices[-1]
            row = primary + 1
        else:
            primary = None
            row = 0
        self._update_properties(row)

    def _selected_item(self) -> ProjectItem | None:
        row = self.project_list.currentRow()
        if row <= 0:
            return None
        index = row - 1
        if index >= len(self.project.items):
            return None
        return self.project.items[index]

    def _selected_item_index(self) -> int | None:
        row = self.project_list.currentRow()
        if row <= 0:
            return None
        index = row - 1
        if index >= len(self.project.items):
            return None
        return index

    def _refresh_inspector_context(self) -> None:
        """Refresh contextual UI exactly once after a selection change."""
        self._refresh_cam_detail_readouts()
        self._sync_selection_action_state()
        self._sync_toolpath_output_state()

    def _update_properties(self, row: int) -> None:
        if hasattr(self, "object_selector"):
            desired = max(
                0,
                min(int(row), self.object_selector.count() - 1),
            )
            if self.object_selector.currentIndex() != desired:
                self._updating_object_selector = True
                self.object_selector.blockSignals(True)
                try:
                    self.object_selector.setCurrentIndex(desired)
                finally:
                    self.object_selector.blockSignals(False)
                    self._updating_object_selector = False

        selected_indices = self._selected_design_indices()
        if len(selected_indices) > 1:
            primary = (
                row - 1
                if row > 0 and row - 1 in selected_indices
                else selected_indices[-1]
            )
            selected_names = [
                self.project.items[index].name
                for index in selected_indices
            ]
            preview = ", ".join(selected_names[:5])
            if len(selected_names) > 5:
                preview += f", +{len(selected_names) - 5} more"
            self.selection_info.setText(
                f"{len(selected_indices)} objects selected\n{preview}\n\n"
                "Use Align, Group, Duplicate, Delete, or the Layers panel "
                "to operate on the complete selection."
            )
            self._set_inspector_context_sections()
            self.viewport.set_selected_items(
                selected_indices,
                primary=primary,
            )
            self._refresh_inspector_context()
            return

        if row <= 0:
            stock = self.project.stock
            self.selection_info.setText(
                "Stock\n"
                f"{self._number(stock.width_mm)} × {self._number(stock.height_mm)} × "
                f"{self._number(stock.thickness_mm)} mm"
            )
            self._sync_stock_controls()
            self._set_inspector_context_sections(stock=True)
            self.viewport.set_selected_item(None)
            self._refresh_inspector_context()
            return

        item_index = row - 1
        if item_index >= len(self.project.items):
            self.selection_info.setText("No design selected")
            self.stock_widget.setVisible(False)
            self.text_widget.setVisible(False)
            self.transform_widget.setVisible(False)
            self.viewport.set_selected_item(None)
            self._refresh_inspector_context()
            return

        item = self.project.items[item_index]
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.set_selected_item(item_index)
        has_mesh = item.mesh is not None
        is_text = item.kind.lower() == "text" and has_mesh
        self._set_inspector_context_sections(
            text=is_text, transform=has_mesh,
        )
        self.text_widget.setEnabled(not item.locked)
        self.transform_widget.setEnabled(not item.locked)
        if is_text:
            self._sync_text_controls(item)
        if has_mesh:
            self._sync_transform_controls(item)
        self._refresh_inspector_context()

