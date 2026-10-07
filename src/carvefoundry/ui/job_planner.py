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
        """Compatibility entry point for the persistent operation stack."""

        self._focus_machining_operations_panel()
        if not self.project.cam_operations:
            self.statusBar().showMessage(
                "Generate toolpaths to create the first saved machining operation.",
                5000,
            )
        else:
            self.statusBar().showMessage(
                "Machining Operations opened in the Inspector.",
                3000,
            )
