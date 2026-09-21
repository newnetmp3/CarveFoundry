"""Duplicate, delete, and reorder design objects."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..core.project import ProjectItem


class ObjectLifecycleActionsMixin:
    """Own selected-object duplication, deletion, and stacking order."""

    def _duplicate_selected_item(self) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if indices and not self._selection_is_editable(indices):
            return
        if not indices:
            self.statusBar().showMessage("Select one or more design objects", 3000)
            return

        group_map: dict[str, str] = {}
        duplicates: list[ProjectItem] = []
        for index in indices:
            source = self.project.items[index]
            source_path = Path(source.name)
            duplicate_name = self._unique_item_name(
                f"{source_path.stem} copy{source_path.suffix}"
            )
            group_id = None
            if source.group_id:
                group_id = group_map.setdefault(
                    source.group_id,
                    uuid4().hex,
                )
            duplicates.append(
                self._clone_item(
                    source,
                    name=duplicate_name,
                    group_id=group_id,
                    offset_mm=(5.0, 5.0, 0.0),
                )
            )

        first_new_index = len(self.project.items)
        self.project.items.extend(duplicates)
        self._invalidate_toolpaths("Project geometry")
        duplicate_indices = list(
            range(first_new_index, first_new_index + len(duplicates))
        )
        self._refresh_project_list(len(self.project.items))
        self._select_project_indices(
            duplicate_indices,
            primary=duplicate_indices[-1],
        )
        self.viewport.update()

        if len(duplicates) == 1:
            message = f"Duplicated {duplicates[0].name} • offset 5 mm"
        else:
            message = f"Duplicated {len(duplicates)} objects • offset 5 mm"
        self.statusBar().showMessage(message, 3000)

    def _delete_selected_item(self) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if indices and not self._selection_is_editable(indices):
            return
        if not indices:
            self.statusBar().showMessage("Select one or more design objects", 3000)
            return

        removed_names = [
            self.project.items[index].name
            for index in indices
        ]
        for index in reversed(indices):
            self.project.remove_item(index)

        self._invalidate_toolpaths("Project geometry")
        next_row = min(indices[0] + 1, len(self.project.items))
        self._refresh_project_list(next_row)
        self.viewport.update()

        if len(removed_names) == 1:
            message = f"Deleted {removed_names[0]}"
        else:
            message = f"Deleted {len(removed_names)} objects"
        self.statusBar().showMessage(message, 3000)

    def _move_selected_item(self, offset: int) -> None:
        index = self._selected_item_index()
        if index is not None and not self._selection_is_editable([index]):
            return
        if index is None:
            self.statusBar().showMessage("Select a design item to reorder", 3000)
            return
        new_index = self.project.move_item(index, offset)
        self._refresh_project_list(new_index + 1)
        self.viewport.update()

