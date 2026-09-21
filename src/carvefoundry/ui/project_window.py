from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox

from carvefoundry.core.history import WorkspaceSnapshot, capture_workspace, restore_workspace
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.project_file import (
    PROJECT_SUFFIX,
    load_project,
    save_project,
)

from .main_window import MainWindow as _BaseMainWindow


@dataclass(slots=True)
class _UndoEntry:
    snapshot: WorkspaceSnapshot
    selected_row: int
    state_id: int
    label: str


class MainWindow(_BaseMainWindow):
    """Main window with project lifecycle and unsaved-change protection.

    This layer keeps project lifecycle concerns separate from the workspace while
    the ribbon is implemented button-by-button. The File > Project actions can
    therefore be hardened without mixing persistence state into rendering/CAM UI.
    """

    def __init__(self) -> None:
        self._project_dirty = False
        self._after_save_action = None
        self._undo_stack: list[_UndoEntry] = []
        self._redo_stack: list[_UndoEntry] = []
        self._history_state_id = 0
        self._history_next_id = 1
        self._saved_state_id = 0
        self._pending_import_undo: tuple[WorkspaceSnapshot, int] | None = None
        self._pending_viewport_transform_undo: tuple[
            WorkspaceSnapshot,
            int,
            tuple[object, ...],
        ] | None = None
        self._pending_context_transform_undo: tuple[
            WorkspaceSnapshot,
            int,
            tuple[object, ...],
            str,
        ] | None = None
        self._pending_text_properties_undo: tuple[
            WorkspaceSnapshot,
            int,
        ] | None = None
        self._pending_ribbon_undo: tuple[
            WorkspaceSnapshot,
            int,
            str,
        ] | None = None
        super().__init__()
        self._init_project_recovery()
        self._update_project_title()
        self._sync_history_action_state()

    @staticmethod
    def _transform_signature(item: ProjectItem) -> tuple[object, ...]:
        transform = item.transform
        return (
            item.source_units,
            tuple(transform.translation_mm),
            tuple(transform.rotation_deg),
            tuple(transform.scale_xyz),
        )

    def _sync_history_action_state(self) -> None:
        self._set_history_action_state(
            can_undo=bool(self._undo_stack),
            can_redo=bool(self._redo_stack),
            undo_label=(
                self._undo_stack[-1].label
                if self._undo_stack
                else None
            ),
            redo_label=(
                self._redo_stack[-1].label
                if self._redo_stack
                else None
            ),
        )

    def _update_project_title(self) -> None:
        marker = " *" if self._project_dirty else ""
        self.project_title_label.setText(f"  •  {self.project.name} Project{marker}")
        self.setWindowTitle(f"CarveFoundry — {self.project.name}{marker}")

    def _mark_project_dirty(self) -> None:
        if not self._project_dirty:
            self._history_state_id = self._history_next_id
            self._history_next_id += 1
        self._project_dirty = True
        self._update_project_title()
        if hasattr(self, "_recovery_timer"):
            self._queue_autosave_recovery()

    def _mark_project_clean(self) -> None:
        self._saved_state_id = self._history_state_id
        self._project_dirty = False
        self._update_project_title()

    def _reset_undo_history(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._history_state_id = 0
        self._history_next_id = 1
        self._saved_state_id = 0
        self._pending_import_undo = None
        self._pending_viewport_transform_undo = None
        self._pending_context_transform_undo = None
        self._pending_text_properties_undo = None
        self._pending_ribbon_undo = None
        if hasattr(self, "_history_action_buttons"):
            self._sync_history_action_state()

    def _record_undo(
        self,
        snapshot: WorkspaceSnapshot,
        selected_row: int,
        label: str,
    ) -> None:
        self._undo_stack.append(
            _UndoEntry(
                snapshot=snapshot,
                selected_row=selected_row,
                state_id=self._history_state_id,
                label=label,
            )
        )
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

        self._history_state_id = self._history_next_id
        self._history_next_id += 1
        self._project_dirty = self._history_state_id != self._saved_state_id
        self._update_project_title()
        self._sync_history_action_state()
        if hasattr(self, "_recovery_timer"):
            self._queue_autosave_recovery()

    def _undo(self) -> None:
        if not self._undo_stack:
            self.statusBar().showMessage("Nothing to undo", 3000)
            return

        entry = self._undo_stack.pop()
        self._redo_stack.append(
            _UndoEntry(
                snapshot=capture_workspace(self.project),
                selected_row=self.project_list.currentRow(),
                state_id=self._history_state_id,
                label=entry.label,
            )
        )
        if len(self._redo_stack) > 100:
            self._redo_stack.pop(0)

        restore_workspace(self.project, entry.snapshot)
        self._history_state_id = entry.state_id
        self._project_dirty = self._history_state_id != self._saved_state_id
        self._update_project_title()

        self.viewport.set_project(self.project, fit_view=False)
        self._refresh_project_list(entry.selected_row)
        self._sync_toolpath_state_from_project()
        self._sync_history_action_state()
        self.statusBar().showMessage(f"Undo: {entry.label}", 3000)
        self._queue_autosave_recovery()
        if not self._project_dirty:
            self._clear_recovery_checkpoint()

    def _redo(self) -> None:
        if not self._redo_stack:
            self.statusBar().showMessage("Nothing to redo", 3000)
            return

        entry = self._redo_stack.pop()
        self._undo_stack.append(
            _UndoEntry(
                snapshot=capture_workspace(self.project),
                selected_row=self.project_list.currentRow(),
                state_id=self._history_state_id,
                label=entry.label,
            )
        )
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)

        restore_workspace(self.project, entry.snapshot)
        self._history_state_id = entry.state_id
        self._project_dirty = self._history_state_id != self._saved_state_id
        self._update_project_title()

        self.viewport.set_project(self.project, fit_view=False)
        self._refresh_project_list(entry.selected_row)
        self._sync_toolpath_state_from_project()
        self._sync_history_action_state()
        self.statusBar().showMessage(f"Redo: {entry.label}", 3000)
        self._queue_autosave_recovery()
        if not self._project_dirty:
            self._clear_recovery_checkpoint()

    def _set_project(
        self,
        project: Project,
        *,
        project_path: Path | None,
        selected_row: int = 0,
    ) -> None:
        if hasattr(self, "_recovery_timer"):
            self._recovery_timer.stop()
        super()._set_project(
            project,
            project_path=project_path,
            selected_row=selected_row,
        )
        if hasattr(self, "_recovery_key"):
            from uuid import uuid4
            self._recovery_key = uuid4().hex
        self._reset_undo_history()
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
        """Save asynchronously without marking unsaved edits as committed early."""

        if self._background_job is not None:
            self.statusBar().showMessage("Another operation is running", 4000)
            return False
        project = self.project
        original_name = project.name
        old_path = self.project_path
        saved_state = self._history_state_id
        if project_name is not None:
            project.name = project_name
        elif project.name == "Untitled":
            project.name = path.stem
        self._update_project_title()

        def save(progress):
            progress(0.03, "Compressing project and embedded assets")
            saved = save_project(project, path)
            progress(0.96, "Project written")
            return saved

        def after_cleanup(action) -> None:
            if self._background_job is not None:
                QTimer.singleShot(20, lambda: after_cleanup(action))
            else:
                action()

        def done(saved_path):
            self.project_path = saved_path
            if self._history_state_id == saved_state:
                self._mark_project_clean()
                self._clear_recovery_checkpoint()
            else:
                self._update_project_title()
            self.statusBar().showMessage(f"Saved {saved_path.name}", 5000)
            action = self._after_save_action
            self._after_save_action = None
            if action is not None:
                after_cleanup(action)

        def failed(message: str) -> None:
            if self.project is project:
                project.name = original_name
                self.project_path = old_path
                self._update_project_title()
            self._after_save_action = None
            self._set_activity_info(f"Project save failed\n{message}")
            self.statusBar().showMessage(
                f"Could not save project: {message}", 8000
            )

        started = self._start_background_job(
            "Save project", task=save, on_done=done,
            on_failed=failed, indeterminate=True,
        )
        if not started:
            project.name = original_name
            self._update_project_title()
        return started

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
            self._after_save_action = self._new_project
            if not self._save_project():
                self._after_save_action = None
            return False
        return result == QMessageBox.StandardButton.Discard

    def _new_project(self) -> None:
        if not self._confirm_new_project():
            if self._after_save_action is None:
                self.statusBar().showMessage("New project canceled", 3000)
            return
        if self._project_dirty:
            self._clear_recovery_checkpoint()
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
            self._after_save_action = lambda: self._open_project_path(
                self._pending_open_target
            )
            if not self._save_project():
                self._after_save_action = None
            return False
        return result == QMessageBox.StandardButton.Discard

    def _open_project(self) -> None:
        if self._background_job is not None:
            self.statusBar().showMessage("Another operation is running", 4000)
            return
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
        self._pending_open_target = target
        if not self._confirm_open_project(target.name):
            if self._after_save_action is None:
                self.statusBar().showMessage("Open project canceled", 3000)
            return
        self._open_project_path(target)

    def _open_project_path(self, target: Path) -> None:
        old_key = self._recovery_key
        old_dirty = self._project_dirty

        def load(progress):
            progress(0.03, "Reading project and embedded assets")
            loaded = load_project(target)
            progress(0.96, "Project loaded")
            return loaded

        def done(loaded):
            if old_dirty:
                self._clear_recovery_checkpoint(key=old_key)
            self._set_project(loaded, project_path=target)
            self.statusBar().showMessage(f"Opened {target.name}", 5000)

        def failed(message: str) -> None:
            self._set_activity_info(f"Project open failed\n{message}")
            self.statusBar().showMessage(
                f"Could not open project: {message}", 8000
            )

        self._start_background_job(
            "Open project", task=load, on_done=done,
            on_failed=failed, indeterminate=True,
        )

    # Mutating workspace actions mark the project as modified. Keeping this in
    # one lifecycle layer makes the dirty state reliable for New/Open/Close.
    def _project_item_changed(self, list_item) -> None:
        snapshot = capture_workspace(self.project)
        selected_row = self.project_list.currentRow()
        before = tuple(
            (item.name, item.visible, item.locked)
            for item in self.project.items
        )
        super()._project_item_changed(list_item)
        after = tuple(
            (item.name, item.visible, item.locked)
            for item in self.project.items
        )
        if after == before:
            return

        renamed = any(
            old_name != new_name
            for (old_name, _old_visible, _old_lock), (new_name, _new_visible, _new_lock)
            in zip(before, after, strict=True)
        )
        locked_changed = any(
            old_lock != new_lock
            for (_old_name, _old_visible, old_lock), (_new_name, _new_visible, new_lock)
            in zip(before, after, strict=True)
        )
        label = "rename object" if renamed else "layer lock" if locked_changed else "visibility"
        self._record_undo(snapshot, selected_row, label)

    def _stock_control_changed(self, value: float) -> None:
        snapshot = capture_workspace(self.project)
        selected_row = self.project_list.currentRow()
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
            self._record_undo(snapshot, selected_row, "stock dimensions")

    def _source_units_changed(self, index: int) -> None:
        snapshot = capture_workspace(self.project)
        selected_row = self.project_list.currentRow()
        item = self._selected_item()
        before = self._transform_signature(item) if item is not None else None
        super()._source_units_changed(index)
        item = self._selected_item()
        after = self._transform_signature(item) if item is not None else None
        if after != before:
            self._record_undo(snapshot, selected_row, "model units")

    def _transform_control_changed(self, value: float) -> None:
        snapshot = capture_workspace(self.project)
        selected_row = self.project_list.currentRow()
        item = self._selected_item()
        before = self._transform_signature(item) if item is not None else None
        super()._transform_control_changed(value)
        item = self._selected_item()
        after = self._transform_signature(item) if item is not None else None
        if after != before:
            self._record_undo(snapshot, selected_row, "model transform")

    def _center_selected_xy(self) -> None:
        snapshot = capture_workspace(self.project)
        selected_row = self.project_list.currentRow()
        item = self._selected_item()
        before = self._transform_signature(item) if item is not None else None
        super()._center_selected_xy()
        item = self._selected_item()
        after = self._transform_signature(item) if item is not None else None
        if after != before:
            self._record_undo(snapshot, selected_row, "center XY")

    def _top_selected_to_surface(self) -> None:
        snapshot = capture_workspace(self.project)
        selected_row = self.project_list.currentRow()
        item = self._selected_item()
        before = self._transform_signature(item) if item is not None else None
        super()._top_selected_to_surface()
        item = self._selected_item()
        after = self._transform_signature(item) if item is not None else None
        if after != before:
            self._record_undo(snapshot, selected_row, "top to Z0")

    def _reset_selected_transform(self) -> None:
        snapshot = capture_workspace(self.project)
        selected_row = self.project_list.currentRow()
        item = self._selected_item()
        before = self._transform_signature(item) if item is not None else None
        super()._reset_selected_transform()
        item = self._selected_item()
        after = self._transform_signature(item) if item is not None else None
        if after != before:
            self._record_undo(snapshot, selected_row, "reset transform")

    def _duplicate_selected_item(self) -> None:
        snapshot = capture_workspace(self.project)
        selected_row = self.project_list.currentRow()
        before = len(self.project.items)
        super()._duplicate_selected_item()
        if len(self.project.items) != before:
            self._record_undo(snapshot, selected_row, "duplicate")

    def _delete_selected_item(self) -> None:
        snapshot = capture_workspace(self.project)
        selected_row = self.project_list.currentRow()
        before = len(self.project.items)
        removed_name = self._selected_item().name if self._selected_item() is not None else "item"
        super()._delete_selected_item()
        if len(self.project.items) != before:
            self._record_undo(snapshot, selected_row, f"delete {removed_name}")

    def _move_selected_item(self, offset: int) -> None:
        snapshot = capture_workspace(self.project)
        selected_row = self.project_list.currentRow()
        before = tuple(id(item) for item in self.project.items)
        super()._move_selected_item(offset)
        after = tuple(id(item) for item in self.project.items)
        if after != before:
            self._record_undo(snapshot, selected_row, "reorder layer")

    def _viewport_transform_started(self, index: int) -> None:
        super()._viewport_transform_started(index)
        if not 0 <= index < len(self.project.items):
            self._pending_viewport_transform_undo = None
            return
        item = self.project.items[index]
        self._pending_viewport_transform_undo = (
            capture_workspace(self.project),
            index + 1,
            self._transform_signature(item),
        )

    def _viewport_transform_finished(self, index: int) -> None:
        super()._viewport_transform_finished(index)
        pending = self._pending_viewport_transform_undo
        self._pending_viewport_transform_undo = None
        if pending is None or not 0 <= index < len(self.project.items):
            return
        snapshot, selected_row, before = pending
        after = self._transform_signature(self.project.items[index])
        if after != before:
            if self.viewport.transform_interaction_kind == "resize-object":
                label = (
                    "resize text"
                    if self.project.items[index].kind.lower() == "text"
                    else "resize object"
                )
            else:
                label = "move object"
            self._record_undo(snapshot, selected_row, label)

    def _before_context_transform(self, index: int, label: str) -> None:
        super()._before_context_transform(index, label)
        if not 0 <= index < len(self.project.items):
            self._pending_context_transform_undo = None
            return
        item = self.project.items[index]
        self._pending_context_transform_undo = (
            capture_workspace(self.project),
            index + 1,
            self._transform_signature(item),
            label,
        )

    def _after_context_transform(self, index: int, label: str) -> None:
        super()._after_context_transform(index, label)
        pending = self._pending_context_transform_undo
        self._pending_context_transform_undo = None
        if pending is None or not 0 <= index < len(self.project.items):
            return
        snapshot, selected_row, before, pending_label = pending
        after = self._transform_signature(self.project.items[index])
        if after != before:
            self._record_undo(
                snapshot,
                selected_row,
                pending_label or label,
            )

    def _before_text_properties_change(self, index: int) -> None:
        super()._before_text_properties_change(index)
        if not 0 <= index < len(self.project.items):
            self._pending_text_properties_undo = None
            return
        self._pending_text_properties_undo = (
            capture_workspace(self.project),
            self.project_list.currentRow(),
        )

    def _after_text_properties_change(self, index: int) -> None:
        super()._after_text_properties_change(index)
        pending = self._pending_text_properties_undo
        self._pending_text_properties_undo = None
        if pending is None:
            return
        snapshot, selected_row = pending
        self._record_undo(snapshot, selected_row, "edit text")

    def _before_ribbon_mutation(self, label: str) -> None:
        super()._before_ribbon_mutation(label)
        self._pending_ribbon_undo = (
            capture_workspace(self.project),
            self.project_list.currentRow(),
            label,
        )

    def _after_ribbon_mutation(self, label: str, changed: bool) -> None:
        super()._after_ribbon_mutation(label, changed)
        pending = self._pending_ribbon_undo
        self._pending_ribbon_undo = None
        if not changed or pending is None:
            return
        snapshot, selected_row, pending_label = pending
        self._record_undo(
            snapshot,
            selected_row,
            pending_label or label,
        )

    def _before_import_items_added(self, count: int) -> None:
        if count <= 0:
            self._pending_import_undo = None
            return
        self._pending_import_undo = (
            capture_workspace(self.project),
            self.project_list.currentRow(),
        )

    def _on_import_items_added(self, count: int) -> None:
        pending = self._pending_import_undo
        self._pending_import_undo = None
        if count > 0 and pending is not None:
            snapshot, selected_row = pending
            label = "import file" if count == 1 else f"import {count} files"
            self._record_undo(snapshot, selected_row, label)

    def _import_thread_finished(self) -> None:
        super()._import_thread_finished()
        self._pending_import_undo = None

    def closeEvent(self, event) -> None:
        # Hidden windows are closed programmatically (including headless
        # tests); only prompt when a user can see and interact with the dialog.
        if not self.isVisible():
            super().closeEvent(event)
            return
        if self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        ):
            super().closeEvent(event)
            return
        if not self._project_dirty:
            super().closeEvent(event)
            return
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Unsaved Changes")
        dialog.setText(f'Save changes to "{self.project.name}" before closing?')
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Save)
        answer = dialog.exec()
        if answer == QMessageBox.StandardButton.Discard:
            self._clear_recovery_checkpoint()
            super().closeEvent(event)
        elif answer == QMessageBox.StandardButton.Save:
            self._after_save_action = self.close
            if not self._save_project():
                self._after_save_action = None
            event.ignore()
        else:
            event.ignore()
