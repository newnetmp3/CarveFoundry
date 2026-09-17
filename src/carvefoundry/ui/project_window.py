from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.project_file import (
    PROJECT_SUFFIX,
    ProjectFileError,
    load_project,
    save_project,
)

from .main_window import MainWindow as _BaseMainWindow


class MainWindow(_BaseMainWindow):
    """Main window with project lifecycle and unsaved-change protection.

    This layer keeps project lifecycle concerns separate from the workspace while
    the ribbon is implemented button-by-button. The File > Project actions can
    therefore be hardened without mixing persistence state into rendering/CAM UI.
    """

    def __init__(self) -> None:
        self._project_dirty = False
        super().__init__()
        self._update_project_title()

    @staticmethod
    def _transform_signature(item: ProjectItem) -> tuple[object, ...]:
        transform = item.transform
        return (
            item.source_units,
            tuple(transform.translation_mm),
            tuple(transform.rotation_deg),
            tuple(transform.scale_xyz),
        )

    def _update_project_title(self) -> None:
        marker = " *" if self._project_dirty else ""
        self.project_title_label.setText(f"  •  {self.project.name} Project{marker}")
        self.setWindowTitle(f"CarveFoundry — {self.project.name}{marker}")

    def _mark_project_dirty(self) -> None:
        if self._project_dirty:
            return
        self._project_dirty = True
        self._update_project_title()

    def _mark_project_clean(self) -> None:
        self._project_dirty = False
        self._update_project_title()

    def _set_project(
        self,
        project: Project,
        *,
        project_path: Path | None,
        selected_row: int = 0,
    ) -> None:
        super()._set_project(
            project,
            project_path=project_path,
            selected_row=selected_row,
        )
        self._mark_project_clean()

    def _save_project(self) -> bool:
        if self.project_path is None:
            return self._save_project_as()

        # A clean project that still exists on disk needs no rewrite. If the
        # backing file was removed externally, Save recreates it from the
        # in-memory project even though the project itself is unchanged.
        if not self._project_dirty and self.project_path.is_file():
            self.statusBar().showMessage(
                f"No changes to save — {self.project_path.name} is up to date",
                3000,
            )
            return True

        return self._save_project_to(self.project_path)

    def _save_project_as(self) -> bool:
        suggested = (
            self.project_path
            if self.project_path is not None
            else Path.home() / f"{self.project.name}{PROJECT_SUFFIX}"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CarveFoundry Project As",
            str(suggested),
            f"CarveFoundry Projects (*{PROJECT_SUFFIX})",
        )
        if not path:
            self.statusBar().showMessage("Save As canceled", 3000)
            return False

        target = Path(path)
        # Save As establishes a new project identity. Keep the display/project
        # name synchronized with the new file name, while _save_project_to()
        # restores the old name if the write fails.
        return self._save_project_to(target, project_name=target.stem)

    def _save_project_to(
        self,
        path: Path,
        *,
        project_name: str | None = None,
    ) -> bool:
        original_name = self.project.name
        if project_name is not None:
            self.project.name = project_name
        elif self.project.name == "Untitled":
            self.project.name = path.stem

        try:
            saved_path = save_project(self.project, path)
        except ProjectFileError as exc:
            self.project.name = original_name
            self.selection_info.setText(f"Project save failed\n{exc}")
            self.statusBar().showMessage(f"Could not save project: {exc}", 8000)
            self._update_project_title()
            return False

        self.project_path = saved_path
        self._mark_project_clean()
        self.statusBar().showMessage(f"Saved {saved_path.name}", 5000)
        return True

    def _confirm_new_project(self) -> bool:
        if not self._project_dirty:
            return True

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Unsaved Changes")
        dialog.setText(
            f'Save changes to "{self.project.name}" before creating a new project?'
        )
        dialog.setInformativeText(
            "Creating a new project will replace the current workspace."
        )
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Save)
        result = dialog.exec()

        if result == QMessageBox.StandardButton.Save:
            return self._save_project()
        return result == QMessageBox.StandardButton.Discard

    def _new_project(self) -> None:
        if not self._confirm_new_project():
            self.statusBar().showMessage("New project canceled", 3000)
            return
        self._set_project(Project(), project_path=None)
        self.statusBar().showMessage("New project created", 3000)

    def _confirm_open_project(self, target_name: str) -> bool:
        if not self._project_dirty:
            return True

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Unsaved Changes")
        dialog.setText(
            f'Save changes to "{self.project.name}" before opening "{target_name}"?'
        )
        dialog.setInformativeText(
            "Opening another project will replace the current workspace."
        )
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Save)
        result = dialog.exec()

        if result == QMessageBox.StandardButton.Save:
            return self._save_project()
        return result == QMessageBox.StandardButton.Discard

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open CarveFoundry Project",
            str(self.project_path.parent if self.project_path else Path.home()),
            f"CarveFoundry Projects (*{PROJECT_SUFFIX});;All files (*)",
        )
        if not path:
            self.statusBar().showMessage("Open project canceled", 3000)
            return

        target = Path(path)
        if not self._confirm_open_project(target.name):
            self.statusBar().showMessage("Open project canceled", 3000)
            return

        # Load completely before replacing the current project. If the file is
        # invalid or references missing assets, the current workspace remains
        # intact.
        try:
            project = load_project(target)
        except ProjectFileError as exc:
            self.selection_info.setText(f"Project open failed\n{exc}")
            self.statusBar().showMessage(f"Could not open project: {exc}", 8000)
            return

        self._set_project(project, project_path=target)
        self.statusBar().showMessage(f"Opened {target.name}", 5000)

    # Mutating workspace actions mark the project as modified. Keeping this in
    # one lifecycle layer makes the dirty state reliable for New/Open/Close.
    def _project_item_changed(self, list_item) -> None:
        before = tuple(item.visible for item in self.project.items)
        super()._project_item_changed(list_item)
        after = tuple(item.visible for item in self.project.items)
        if after != before:
            self._mark_project_dirty()

    def _stock_control_changed(self, value: float) -> None:
        before = (
            self.project.stock.width_mm,
            self.project.stock.height_mm,
            self.project.stock.thickness_mm,
        )
        super()._stock_control_changed(value)
        after = (
            self.project.stock.width_mm,
            self.project.stock.height_mm,
            self.project.stock.thickness_mm,
        )
        if after != before:
            self._mark_project_dirty()

    def _source_units_changed(self, index: int) -> None:
        item = self._selected_item()
        before = self._transform_signature(item) if item is not None else None
        super()._source_units_changed(index)
        item = self._selected_item()
        after = self._transform_signature(item) if item is not None else None
        if after != before:
            self._mark_project_dirty()

    def _transform_control_changed(self, value: float) -> None:
        item = self._selected_item()
        before = self._transform_signature(item) if item is not None else None
        super()._transform_control_changed(value)
        item = self._selected_item()
        after = self._transform_signature(item) if item is not None else None
        if after != before:
            self._mark_project_dirty()

    def _center_selected_xy(self) -> None:
        item = self._selected_item()
        before = self._transform_signature(item) if item is not None else None
        super()._center_selected_xy()
        item = self._selected_item()
        after = self._transform_signature(item) if item is not None else None
        if after != before:
            self._mark_project_dirty()

    def _top_selected_to_surface(self) -> None:
        item = self._selected_item()
        before = self._transform_signature(item) if item is not None else None
        super()._top_selected_to_surface()
        item = self._selected_item()
        after = self._transform_signature(item) if item is not None else None
        if after != before:
            self._mark_project_dirty()

    def _reset_selected_transform(self) -> None:
        item = self._selected_item()
        before = self._transform_signature(item) if item is not None else None
        super()._reset_selected_transform()
        item = self._selected_item()
        after = self._transform_signature(item) if item is not None else None
        if after != before:
            self._mark_project_dirty()

    def _duplicate_selected_item(self) -> None:
        before = len(self.project.items)
        super()._duplicate_selected_item()
        if len(self.project.items) != before:
            self._mark_project_dirty()

    def _delete_selected_item(self) -> None:
        before = len(self.project.items)
        super()._delete_selected_item()
        if len(self.project.items) != before:
            self._mark_project_dirty()

    def _move_selected_item(self, offset: int) -> None:
        before = tuple(id(item) for item in self.project.items)
        super()._move_selected_item(offset)
        after = tuple(id(item) for item in self.project.items)
        if after != before:
            self._mark_project_dirty()

    def _import_file(self, kind: str | None = None) -> None:
        before = len(self.project.items)
        super()._import_file(kind)
        if len(self.project.items) != before:
            self._mark_project_dirty()
