"""Compatibility entry point for the persistent machining-operation stack."""
from __future__ import annotations


class JobPlannerMixin:
    """Open the persistent Machining Operations panel."""

    def _show_job_planner(self) -> None:
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
