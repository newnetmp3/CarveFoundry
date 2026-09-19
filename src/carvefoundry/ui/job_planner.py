"""Session CAM job planner: review, reorder, remove and preview real toolpaths."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from carvefoundry.cam.job_plan import job_report, validate_job_order
from carvefoundry.cam.render_geometry import build_render_geometry


class JobPlannerMixin:
    """Edit the actual generated operation sequence (not a separate fake plan)."""

    def _apply_job_plan(self, paths: list) -> bool:
        if self._background_job is not None:
            self.statusBar().showMessage("Finish the current operation first", 5000)
            return False
        if paths:
            validate_job_order(paths)
        source_project = self.project

        def calculate(progress):
            progress(0.15, "Preparing complete CAM job preview")
            geometry = build_render_geometry(paths) if paths else None
            progress(0.95, "CAM job order ready")
            return geometry

        def finished(geometry):
            if self.project is not source_project:
                return
            self._before_ribbon_mutation("reorder machining job")
            self.project.toolpaths = list(paths)
            self._prepared_toolpath_geometry = geometry
            self._prepared_toolpath_stats = None
            if self._simulation_timer.isActive():
                self._simulation_timer.stop()
            if self._toolpath_preview_window is not None:
                self._toolpath_preview_window.close()
                self._toolpath_preview_window = None
            if paths:
                self.viewport.prepare_toolpath_render_cache(paths, geometry)
                self.viewport.set_simulation_fraction(1.0)
                self._toolpaths_stale_reason = None
            else:
                self._toolpaths_stale_reason = None
                self.viewport.set_toolpaths_visible(False)
            self._sync_toolpath_state_from_project()
            if paths:
                self._set_activity_info("Machining job\n" + job_report(paths))
            self._after_ribbon_mutation("reorder machining job", True)
            self.statusBar().showMessage(
                f"Job updated: {len(paths)} operations in export order.", 6000
            )

        return self._start_background_job(
            "Rebuild machining job",
            task=calculate,
            on_done=finished,
            indeterminate=True,
        )

    def _show_job_planner(self) -> None:
        if self._background_job is not None:
            self.statusBar().showMessage("Finish the current operation first", 5000)
            return
        if not self.project.toolpaths:
            self.statusBar().showMessage(
                "Generate toolpaths before opening the machining job planner.", 6000
            )
            return

        planned = list(self.project.toolpaths)
        dialog = QDialog(self)
        dialog.setWindowTitle("Machining Job Planner")
        dialog.resize(770, 560)
        layout = QVBoxLayout(dialog)
        hint = QLabel(
            "Operations run in this exact order. Consecutive operations using "
            "the same cutter are exported together; each cutter change gets "
            "a separate numbered G-code file with manual re-probing. "
            "Append new operations from Generate Toolpaths."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        rows = QListWidget(dialog)
        rows.setObjectName("JobPlanOperationList")
        rows.setMinimumHeight(220)
        layout.addWidget(rows)

        report = QLabel()
        report.setWordWrap(True)
        layout.addWidget(report)

        def refresh(selected: int = 0) -> None:
            rows.clear()
            for index, path in enumerate(planned, start=1):
                line = (
                    f"{index:02d}  {path.name}  ·  {path.cutter.name}  ·  "
                    f"{path.source_item_name or 'Stock'}  ·  "
                    f"{path.estimated_cutting_minutes:.1f} min"
                )
                entry = QListWidgetItem(line)
                entry.setToolTip(
                    f"{len(path.moves):,} moves; "
                    f"{path.cutting_distance_mm:.1f} mm cutting, "
                    f"{path.rapid_distance_mm:.1f} mm rapid."
                )
                rows.addItem(entry)
            if planned:
                rows.setCurrentRow(min(selected, len(planned) - 1))
            if planned:
                try:
                    report.setText(job_report(planned))
                except ValueError as exc:
                    report.setText(f"Fix operation order before applying: {exc}")
            else:
                report.setText("Empty job: this will clear the calculated toolpaths.")

        actions = QHBoxLayout()
        for caption, direction in (("Move Up", -1), ("Move Down", 1)):
            button = QPushButton(caption, dialog)
            def move(_checked=False, delta=direction):
                index = rows.currentRow()
                next_index = index + delta
                if index < 0 or not 0 <= next_index < len(planned):
                    return
                planned[index], planned[next_index] = (
                    planned[next_index], planned[index]
                )
                refresh(next_index)
            button.clicked.connect(move)
            actions.addWidget(button)
        remove = QPushButton("Remove Selected", dialog)
        def remove_selected():
            index = rows.currentRow()
            if index < 0:
                return
            planned.pop(index)
            refresh(max(0, index - 1))
        remove.clicked.connect(remove_selected)
        actions.addWidget(remove)
        layout.addLayout(actions)

        warning = QLabel(
            "Cutouts must follow all other passes on their part; roughing must "
            "precede finishing. The job and its toolpaths are session-owned: "
            "regenerate them after reopening the CF3D project. Export still "
            "runs mandatory CNC preflight."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )

        def apply():
            if planned:
                try:
                    validate_job_order(planned)
                except ValueError as exc:
                    QMessageBox.warning(dialog, "Invalid machining order", str(exc))
                    return
            dialog.accept()

        buttons.accepted.connect(apply)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        refresh()
        if dialog.exec() == QDialog.DialogCode.Accepted and (
            len(planned) != len(self.project.toolpaths)
            or any(a is not b for a, b in zip(planned, self.project.toolpaths))
        ):
            self._apply_job_plan(planned)
