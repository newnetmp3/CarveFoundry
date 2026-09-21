"""Project editing, clipboard, grouping, alignment, and generated items."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6.QtWidgets import QInputDialog

from carvefoundry.core.project import ProjectItem
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.units import ModelUnits


class ProjectEditActionsMixin:
    """Project mutation helpers shared by design tools and command surfaces."""

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
        if normalized in {"group", "ungroup", "edit project notes"}:
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

