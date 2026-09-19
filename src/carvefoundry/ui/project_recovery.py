"""Qt lifecycle for opt-in recovery of full, checksum-verified native projects."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from carvefoundry.core.recovery import (
    RecoveryEntry,
    discard_key,
    discard_recovery,
    list_recoveries,
    load_recovery,
    prune_recoveries,
    save_recovery,
)

RECOVERY_IDLE_MS = 60_000


def recovery_directory() -> Path:
    override = os.environ.get("CARVEFOUNDRY_RECOVERY_DIR")
    if override:
        return Path(override).expanduser()
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation,
    )
    if not location:
        raise RuntimeError("No writable application data directory for recovery.")
    return Path(location) / "recovery"


class ProjectRecoveryMixin:
    """Autosave edits without overriding the user's deliberate project file."""

    def _init_project_recovery(self) -> None:
        self._recovery_dir = recovery_directory()
        self._recovery_key = uuid4().hex
        self._recovery_timer = QTimer(self)
        self._recovery_timer.setSingleShot(True)
        self._recovery_timer.setInterval(RECOVERY_IDLE_MS)
        self._recovery_timer.timeout.connect(self._autosave_recovery)
        # App startup returns to its event loop before any recovery dialog.
        QTimer.singleShot(500, self._offer_startup_recovery)

    def _recovery_enabled(self) -> bool:
        return str(self._settings.value(
            "recovery/enabled", "true",
        )).casefold() not in {"false", "0", "no"}

    def _set_recovery_enabled(self, enabled: bool) -> None:
        self._settings.setValue("recovery/enabled", bool(enabled))
        self._settings.sync()
        if not enabled:
            self._recovery_timer.stop()
        elif self._project_dirty:
            self._queue_autosave_recovery()
        self.statusBar().showMessage(
            "Automatic project recovery enabled" if enabled
            else "Automatic project recovery disabled",
            5000,
        )

    def _queue_autosave_recovery(self) -> None:
        if self._project_dirty and self._recovery_enabled():
            self._recovery_timer.start(RECOVERY_IDLE_MS)
        else:
            self._recovery_timer.stop()

    def _clear_recovery_checkpoint(self, *, key: str | None = None) -> None:
        self._recovery_timer.stop()
        discard_key(
            self._recovery_dir, key if key is not None else self._recovery_key,
        )

    def _autosave_recovery(self, *, force: bool = False) -> bool:
        if not self._project_dirty:
            return False
        if not force and not self._recovery_enabled():
            return False
        if self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        ):
            self._recovery_timer.start(10_000)
            return False

        project = self.project
        state_id = self._history_state_id
        key = self._recovery_key
        original_path = self.project_path
        directory = self._recovery_dir

        def write(progress):
            progress(0.02, "Writing complete recovery checkpoint")
            entry = save_recovery(
                project, directory, key=key, state_id=state_id,
                original_path=original_path,
            )
            prune_recoveries(directory)
            progress(0.98, "Recovery checkpoint verified and recorded")
            return entry

        def complete(entry: RecoveryEntry) -> None:
            self.statusBar().showMessage(
                f"Recovery checkpoint saved: {entry.name}. "
                "Normal Save is still required.",
                7000,
            )
            if self._history_state_id != state_id and self._project_dirty:
                self._queue_autosave_recovery()

        def failed(message: str) -> None:
            self.statusBar().showMessage(
                f"Automatic recovery failed: {message}", 9000,
            )
            self._set_activity_info(
                f"Automatic recovery failed\n{message}\n"
                "Your last manually saved project was not changed."
            )

        return self._start_background_job(
            "Save recovery checkpoint",
            task=write,
            on_done=complete,
            on_failed=failed,
            indeterminate=True,
        )

    def _manual_recovery_checkpoint(self) -> bool:
        return self._autosave_recovery(force=True)

    def _offer_startup_recovery(self) -> None:
        # Offscreen/headless windows used by tests must not create dialogs.
        if self.isVisible() and list_recoveries(self._recovery_dir):
            self._show_recovery_dialog()

    def _show_recovery_dialog(self) -> None:
        entries = list_recoveries(self._recovery_dir)
        if not entries:
            self.statusBar().showMessage("No recovery checkpoints found", 4500)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Restore a CarveFoundry Recovery Checkpoint")
        dialog.resize(710, 450)
        layout = QVBoxLayout(dialog)
        intro = QLabel(
            "These are complete, separately saved CF3D checkpoints. "
            "Restoring never overwrites the original project automatically. "
            "Choose a checkpoint, then use normal Save after reviewing it."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        entries_list = QListWidget(dialog)
        for entry in entries:
            source = str(entry.original_path) if entry.original_path else "Unsaved project"
            changed = " · ORIGINAL FILE CHANGED" if entry.original_changed() else ""
            entries_list.addItem(
                f"{entry.name} · {entry.timestamp}\n{source}{changed}"
            )
        entries_list.setCurrentRow(0)
        layout.addWidget(entries_list, 1)
        controls = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        restore = QPushButton("Restore Selected", dialog)
        discard = QPushButton("Discard Selected", dialog)
        controls.addButton(
            discard, QDialogButtonBox.ButtonRole.DestructiveRole,
        )
        controls.addButton(
            restore, QDialogButtonBox.ButtonRole.AcceptRole,
        )
        controls.rejected.connect(dialog.reject)

        def chosen() -> RecoveryEntry | None:
            index = entries_list.currentRow()
            return entries[index] if 0 <= index < len(entries) else None

        def accept_recovery() -> None:
            entry = chosen()
            if entry is None:
                return
            if entry.original_changed():
                warning = QMessageBox.warning(
                    dialog,
                    "Original project changed",
                    "The original project has changed since this checkpoint "
                    "was taken. Restoring does not overwrite it, but a future "
                    "normal Save to that path would. Continue?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if warning != QMessageBox.StandardButton.Yes:
                    return
            dialog.accept()
            self._restore_checkpoint(entry)

        def discard_selected() -> None:
            entry = chosen()
            if entry is None:
                return
            answer = QMessageBox.question(
                dialog,
                "Discard recovery?",
                f"Permanently discard the separate recovery copy for {entry.name}?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            discard_recovery(entry)
            index = entries_list.currentRow()
            entries_list.takeItem(index)
            entries.pop(index)
            if entries:
                entries_list.setCurrentRow(min(index, len(entries) - 1))
            else:
                dialog.reject()

        restore.clicked.connect(accept_recovery)
        discard.clicked.connect(discard_selected)
        layout.addWidget(controls)
        dialog.exec()

    def _restore_checkpoint(self, entry: RecoveryEntry) -> bool:
        if self._background_job is not None:
            self.statusBar().showMessage("Finish the current operation first", 5000)
            return False
        if self._project_dirty:
            # Reuse the established Save/Discard/Cancel guard. On Save,
            # defer actual loading until writing the current project succeeds.
            self._pending_open_target = entry.project_file
            if not self._confirm_open_project(entry.name):
                if self._after_save_action is not None:
                    self._after_save_action = (
                        lambda: self._restore_checkpoint(entry)
                    )
                return False

        old_key = self._recovery_key
        old_dirty = self._project_dirty

        def read(progress):
            progress(0.05, "Checking recovery file checksum")
            loaded = load_recovery(entry)
            progress(0.97, "Recovery checkpoint loaded")
            return loaded

        def done(project):
            if old_dirty and old_key != entry.key:
                discard_key(self._recovery_dir, old_key)
            source = (
                entry.original_path
                if entry.original_path is not None and entry.original_path.is_file()
                else None
            )
            self._set_project(project, project_path=source)
            self._recovery_key = entry.key
            self._mark_project_dirty()
            self._queue_autosave_recovery()
            self.statusBar().showMessage(
                "Recovery restored as unsaved changes. Review and Save.",
                11000,
            )

        def failed(message):
            self._set_activity_info(f"Recovery failed\n{message}")
            self.statusBar().showMessage(
                f"Could not restore recovery: {message}", 9000,
            )

        return self._start_background_job(
            "Restore recovery",
            task=read,
            on_done=done,
            on_failed=failed,
            indeterminate=True,
        )
