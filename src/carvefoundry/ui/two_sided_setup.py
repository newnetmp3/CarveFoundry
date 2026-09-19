"""User-facing two-sided setup: partition faces and bake the physical flip."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from carvefoundry.core.two_sided import save_two_sided_setup


class TwoSidedSetupMixin:
    """Non-destructively create two verified native projects in the background."""

    def _two_sided_dialog(self) -> tuple[frozenset[str], str, str] | None:
        models = [
            item for item in self.project.items
            if item.visible and item.mesh is not None
        ]
        if len(models) < 2:
            self.statusBar().showMessage(
                "Two-sided setup needs at least two visible design items.", 6000
            )
            return None

        dialog = QDialog(self)
        dialog.setWindowTitle("Double-Sided Stock Setup")
        dialog.setMinimumWidth(570)
        layout = QVBoxLayout(dialog)
        explanation = QLabel(
            "Assign each visible model to the front or back of the SAME stock. "
            "Selected back models are reflected into the machine's XY coordinates "
            "after the physical stock turnover. Neither the source project nor "
            "your current design objects are changed."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        axis = QComboBox(dialog)
        axis.addItem(
            "Left/right turnover (X reverses; left and bottom stops)",
            "x",
        )
        axis.addItem("Top/bottom turnover (Y reverses)", "y")
        axis.setToolTip(
            "Choose the axis that reverses when the STOCK is actually turned over."
        )
        form.addRow("Physical stock flip", axis)
        layout.addLayout(form)

        layout.addWidget(QLabel("Check the models that belong on the BACK:"))
        faces = QListWidget(dialog)
        initial = set(self.project.items[index].item_id for index in
                      self._selected_design_indices())
        if not initial or initial == {item.item_id for item in models}:
            initial = {models[-1].item_id}
        for model in models:
            entry = QListWidgetItem(model.name)
            entry.setData(Qt.ItemDataRole.UserRole, model.item_id)
            entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            entry.setCheckState(
                Qt.CheckState.Checked if model.item_id in initial
                else Qt.CheckState.Unchecked
            )
            faces.addItem(entry)
        faces.setMinimumHeight(140)
        layout.addWidget(faces)

        location = QFormLayout()
        folder = QLineEdit(dialog)
        folder.setText(
            (self.project_path.stem if self.project_path is not None
             else self.project.name).replace(" ", "_") + "_two_sided"
        )
        folder.setToolTip("A NEW folder will hold front.cf3d, back.cf3d and setup notes.")
        location.addRow("New setup folder name", folder)
        layout.addLayout(location)

        note = QLabel(
            "Front and back become separate, normal CarveFoundry projects. "
            "For each face: generate toolpaths, preview, preflight, and export "
            "separate cutter-stage G-code. Flip, re-register and re-probe Z0 "
            "between faces. Fixed machine fences/fixtures are NOT mirrored."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )

        def checked_back_ids() -> frozenset[str]:
            return frozenset(
                str(faces.item(i).data(Qt.ItemDataRole.UserRole))
                for i in range(faces.count())
                if faces.item(i).checkState() == Qt.CheckState.Checked
            )

        def accept() -> None:
            selected = checked_back_ids()
            name = folder.text().strip()
            if not 0 < len(selected) < faces.count():
                QMessageBox.warning(
                    dialog, "Assign both faces",
                    "At least one visible model must belong to each face.",
                )
                return
            if name in {"", ".", ".."} or "/" in name or "\\" in name:
                QMessageBox.warning(
                    dialog, "Invalid setup folder",
                    "Use a simple folder name without slashes or '..'.",
                )
                return
            dialog.accept()

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return checked_back_ids(), str(axis.currentData()), folder.text().strip()

    def _run_two_sided_setup(
        self,
        *,
        back_item_ids: frozenset[str],
        axis: str,
        destination: Path,
    ) -> bool:
        if self._background_job is not None:
            self.statusBar().showMessage("Finish the current background job first", 5000)
            return False
        source_project = self.project

        def task(progress):
            return save_two_sided_setup(
                source_project,
                back_item_ids=back_item_ids,
                axis=axis,
                destination=destination,
                progress=progress,
            )

        def finished(folder):
            self._set_activity_info(
                "TWO-SIDED SETUP READY\n"
                f"{folder}\n\n"
                "Open front.cf3d and back.cf3d separately. Generate and "
                "preflight their toolpaths, export separate per-cutter G-code, "
                "and read SETUP_INSTRUCTIONS.txt before cutting. "
                "Re-probe Z0 on the exposed back face after flipping."
            )
            self.statusBar().showMessage(
                f"Two-sided stock setup saved: {folder}", 12000
            )

        def failed(message: str):
            self.statusBar().showMessage(
                f"Two-sided setup failed: {message}", 10000
            )
            self._set_activity_info(f"Two-sided setup failed\n{message}")

        return self._start_background_job(
            "Double-sided stock setup",
            task=task,
            on_done=finished,
            on_failed=failed,
            indeterminate=True,
        )

    def _double_sided_setup(self) -> bool:
        if self._background_job is not None:
            self.statusBar().showMessage("Finish the current background job first", 5000)
            return False
        chosen = self._two_sided_dialog()
        if chosen is None:
            return False
        back_ids, axis, folder_name = chosen
        root = QFileDialog.getExistingDirectory(
            self,
            "Choose Parent Folder for Two-Sided Setup",
            str(self.project_path.parent if self.project_path else Path.home()),
        )
        if not root:
            return False
        return self._run_two_sided_setup(
            back_item_ids=back_ids,
            axis=axis,
            destination=Path(root) / folder_name,
        )
