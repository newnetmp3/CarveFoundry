"""Toolpath visibility, stale-state, and CAM status coordination.

This controller contains UI state derived from the current project's calculated
toolpaths. It deliberately does not generate CAM or write G-code; those jobs
remain in their dedicated CAM/export modules.
"""
from __future__ import annotations


class ToolpathStateControllerMixin:
    """Synchronize calculated toolpaths with viewport, status, and output actions."""

    def _set_cam_status(self, state: str, text: str, tooltip: str) -> None:
        if not hasattr(self, "cam_status_label"):
            return
        self.cam_status_label.setText(text)
        self.cam_status_label.setToolTip(tooltip)
        self.cam_status_label.setProperty("state", state)
        self.cam_status_label.style().unpolish(self.cam_status_label)
        self.cam_status_label.style().polish(self.cam_status_label)

    def _sync_toolpath_output_state(self) -> None:
        has_toolpaths = bool(self.project.toolpaths)
        for button in self._toolpath_output_buttons:
            button.setEnabled(has_toolpaths)

        if not has_toolpaths:
            if self._toolpaths_view_button is not None:
                self._toolpaths_view_button.setChecked(False)
            if self._rapids_view_button is not None:
                self._rapids_view_button.setChecked(False)
            if self._simulation_button is not None:
                self._simulation_button.setChecked(False)
        else:
            if self._toolpaths_view_button is not None:
                self._toolpaths_view_button.setChecked(
                    self.viewport.toolpaths_visible
                )
            if self._rapids_view_button is not None:
                self._rapids_view_button.setChecked(
                    self.viewport.rapids_visible
                )

        if has_toolpaths:
            self._toolpaths_stale_reason = None
            source_names = self._toolpath_source_names(
                self.project.toolpaths
            )
            operation_names = " + ".join(
                path.name for path in self.project.toolpaths
            )
            source_text = ", ".join(source_names) if source_names else "Unknown source"
            self._set_cam_status(
                "ready",
                "CAM: READY",
                (
                    f"{operation_names} for {source_text}. "
                    "Current and available to preview or export."
                ),
            )
        elif self._toolpaths_stale_reason:
            self._set_cam_status(
                "stale",
                "CAM: RECALCULATE",
                (
                    "The previous toolpath was cleared because "
                    f"{self._toolpaths_stale_reason.lower()} changed."
                ),
            )
        else:
            self._set_cam_status(
                "none",
                "CAM: NONE",
                "No calculated toolpath for the current job.",
            )

    def _toolpath_source_names(self, toolpaths) -> list[str]:
        names_by_id = {
            item.item_id: item.name
            for item in self.project.items
        }
        names: list[str] = []
        for path in toolpaths:
            name = (
                names_by_id.get(path.source_item_id)
                if path.source_item_id
                else None
            ) or path.source_item_name
            if name and name not in names:
                names.append(name)
        return names

    def _sync_toolpath_state_from_project(self) -> None:
        if self.project.toolpaths:
            self._toolpaths_stale_reason = None
            operation_names = " + ".join(
                path.name for path in self.project.toolpaths
            )
            source_names = self._toolpath_source_names(
                self.project.toolpaths
            )
            source_text = ", ".join(source_names) if source_names else "Unknown"
            total_moves = sum(
                len(path.moves) for path in self.project.toolpaths
            )
            total_minutes = sum(
                path.estimated_cutting_minutes
                for path in self.project.toolpaths
            )
            self._set_activity_info(
                "Toolpath available\n"
                f"{operation_names}\n\n"
                f"Source: {source_text}\n"
                f"Moves: {total_moves:,}\n"
                f"Estimated cutting: {total_minutes:.1f} min"
            )
            self.viewport.set_toolpaths_visible(True)
        else:
            self._set_activity_info(
                "No calculated toolpath. Choose an operation on Toolpaths when ready."
            )
            self.viewport.set_toolpaths_visible(False)

        self._sync_toolpath_output_state()
        self.viewport.update()

    def _invalidate_toolpaths(self, reason: str) -> bool:
        """Clear calculated motion when geometry or CAM inputs become stale."""

        if not self.project.toolpaths:
            return False

        self.project.toolpaths.clear()
        self._prepared_toolpath_geometry = None
        self._prepared_toolpath_stats = None
        self._toolpaths_stale_reason = reason

        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
        self.viewport.set_simulation_fraction(1.0)
        self.viewport.set_toolpaths_visible(False)

        preview = self._toolpath_preview_window
        if preview is not None:
            preview.close()
            self._toolpath_preview_window = None

        self._set_activity_info(
            "Toolpath needs recalculation\n"
            f"{reason} changed after the last calculation.\n\n"
            "Review the current setup and press Calculate again before previewing "
            "or exporting G-code."
        )
        self._sync_toolpath_output_state()
        self.viewport.update()
        return True

