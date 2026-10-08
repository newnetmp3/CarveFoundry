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

    def _stale_cam_operations(self):
        motion_ids = {
            path.cam_operation_id
            for path in self.project.toolpaths
            if path.cam_operation_id is not None
        }
        return [
            operation
            for operation in self.project.cam_operations
            if operation.enabled and (
                operation.needs_recalculation
                or operation.operation_id not in motion_ids
            )
        ]

    def _sync_toolpath_output_state(self) -> None:
        has_toolpaths = bool(self.project.toolpaths)
        stale_operations = self._stale_cam_operations()
        output_ready = has_toolpaths and not stale_operations
        for button in self._toolpath_output_buttons:
            button.setEnabled(output_ready)

        recalculate = getattr(self, "_recalculate_button", None)
        if recalculate is not None:
            recalculate.setEnabled(bool(stale_operations))

        if not output_ready:
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

        if stale_operations:
            reason = stale_operations[0].stale_reason or self._toolpaths_stale_reason
            self._toolpaths_stale_reason = reason
            self._set_cam_status(
                "stale",
                "CAM: RECALCULATE",
                (
                    f"{len(stale_operations)} machining operation"
                    f"{'s' if len(stale_operations) != 1 else ''} need "
                    f"recalculation"
                    + (f" because {reason.lower()} changed." if reason else ".")
                ),
            )
        elif has_toolpaths:
            self._toolpaths_stale_reason = None
            source_names = self._toolpath_source_names(self.project.toolpaths)
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
                    "Calculated motion is stale because "
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
        stale_operations = self._stale_cam_operations()
        if stale_operations:
            reason = stale_operations[0].stale_reason or "CAM inputs"
            self._toolpaths_stale_reason = reason
            self._set_activity_info(
                "Toolpaths need recalculation\n"
                f"{len(stale_operations)} saved machining operation"
                f"{'s' if len(stale_operations) != 1 else ''} are stale.\n\n"
                "Their cutters, source objects and calculation settings were "
                "retained. Recalculate the job before previewing or exporting."
            )
            self.viewport.set_toolpaths_visible(False)
        elif self.project.toolpaths:
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
        if hasattr(self, "_sync_machining_operations_panel"):
            self._sync_machining_operations_panel()
        self.viewport.update()

    def _invalidate_toolpaths(
        self,
        reason: str,
        *,
        source_item_ids: set[str] | None = None,
    ) -> bool:
        """Invalidate dependent motion while retaining persistent machining intent.

        The earliest operation that depends on changed geometry is marked stale
        along with every later stage, because later stock-removal operations may
        depend on the material state left by earlier cutters.
        """

        operations = self.project.cam_operations
        if not operations:
            if not self.project.toolpaths:
                return False
            self.project.toolpaths.clear()
            changed = True
        else:
            earliest: int | None = None
            if source_item_ids is None:
                earliest = 0
            else:
                for index, operation in enumerate(operations):
                    if set(operation.source_item_ids).intersection(source_item_ids):
                        earliest = index
                        break

            if earliest is None:
                legacy_before = len(self.project.toolpaths)
                if source_item_ids is not None:
                    self.project.toolpaths = [
                        path
                        for path in self.project.toolpaths
                        if not (
                            path.cam_operation_id is None
                            and path.source_item_id in source_item_ids
                        )
                    ]
                changed = len(self.project.toolpaths) != legacy_before
                if not changed:
                    return False
            else:
                stale_operations = operations[earliest:]
                stale_ids = {
                    operation.operation_id
                    for operation in stale_operations
                }
                for operation in stale_operations:
                    operation.mark_stale(reason)

                before = len(self.project.toolpaths)
                self.project.toolpaths = [
                    path
                    for path in self.project.toolpaths
                    if (
                        path.cam_operation_id not in stale_ids
                        and not (
                            path.cam_operation_id is None
                            and (
                                source_item_ids is None
                                or path.source_item_id in source_item_ids
                            )
                        )
                    )
                ]
                changed = (
                    len(self.project.toolpaths) != before
                    or bool(stale_operations)
                )

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

        stale_count = len(self._stale_cam_operations())
        self._set_activity_info(
            "Toolpaths need recalculation\n"
            f"{reason} changed after the last calculation.\n\n"
            + (
                f"{stale_count} saved machining operation"
                f"{'s' if stale_count != 1 else ''} retained "
                "their cutters and settings."
                if stale_count
                else "Calculated motion was cleared."
            )
        )
        self._sync_toolpath_output_state()
        if hasattr(self, "_sync_machining_operations_panel"):
            self._sync_machining_operations_panel()
        self.viewport.update()
        return changed
