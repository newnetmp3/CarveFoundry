"""Main-window background-job orchestration and shared status-bar progress UI.

Worker execution primitives live in background_jobs.py. This module owns only
the GUI lifecycle around one active job: disabling mutating controls, showing
the single status-bar progress indicator, cancellation, and restoring the UI
when the worker thread exits.

Keeping this out of main_window.py makes the application shell easier to
maintain and prevents feature-specific progress widgets from competing with the
global background-job indicator.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QProgressBar, QPushButton, QStatusBar

from .background_jobs import BackgroundWorker, JobCallbacks, JobState

_SAFE_JOB_ACTIONS = {
    "camera",
    "view_fit",
    "frame_selected",
    "view_2d",
    "perspective",
    "orthographic",
    "isometric",
    "view_top",
    "view_bottom",
    "view_front",
    "view_back",
    "view_left",
    "view_right",
    "stock",
    "grid",
    "rulers",
    "toolpaths",
    "rapids",
    "layers",
    "inspector",
    "status_bar",
    "view_controls",
    "reverse_horizontal",
    "invert_vertical",
}


class BackgroundJobControllerMixin:
    """Own one long-running main-window job and its shared progress widgets."""

    def _init_background_job_controller(self) -> None:
        self._background_job: JobState | None = None
        self._job_bridge: JobCallbacks | None = None
        self._job_target_project = None
        self._job_action_states: dict[str, bool] = {}
        self._job_rail_states: dict[str, bool] = {}
        self._job_camera_was_active = True
        self._job_draw_mode: str | None = None
        self._job_sequence = 0

    def _build_status_bar(self) -> QStatusBar:
        """Create the application status bar with one generic job indicator."""

        status = QStatusBar()

        self.job_progress = QProgressBar()
        self.job_progress.setObjectName("BackgroundJobProgress")
        self.job_progress.setFixedWidth(320)
        self.job_progress.setTextVisible(True)
        self.job_progress.hide()
        status.addPermanentWidget(self.job_progress)

        self.cancel_job_button = QPushButton("Cancel")
        self.cancel_job_button.setObjectName("CancelBackgroundJob")
        self.cancel_job_button.clicked.connect(self._cancel_background_job)
        self.cancel_job_button.hide()
        status.addPermanentWidget(self.cancel_job_button)

        status.showMessage("Ready — no machine connected")
        return status

    def _start_background_job(
        self,
        title: str,
        *,
        task=None,
        request=None,
        on_done=None,
        on_failed=None,
        indeterminate: bool = False,
        cancelable: bool = False,
    ) -> bool:
        """Run one costly operation without blocking the GUI thread."""

        if self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        ):
            self.statusBar().showMessage("Another operation is already running", 4000)
            return False

        worker = BackgroundWorker(task, process_request=request)
        thread = QThread(self)
        worker.moveToThread(thread)
        self._background_job = JobState(worker, thread)
        self._job_target_project = self.project
        self._job_sequence += 1
        job_id = self._job_sequence

        # Buttons made with setDefaultAction share QAction state. Snapshot
        # everything before disabling controls so restoration is exact.
        self._job_action_states = {
            key: action.isEnabled()
            for key, action in self._ui_actions.items()
        }
        self._job_rail_states = {
            key: button.isEnabled()
            for key, button in self.tool_rail.buttons.items()
        }

        for key, action in self._ui_actions.items():
            if key not in _SAFE_JOB_ACTIONS:
                action.setEnabled(False)
        if self.generate_toolpaths_button is not None:
            self.generate_toolpaths_button.setEnabled(False)

        # Freeze editing while leaving navigation/repaint controls usable.
        self._job_camera_was_active = self.viewport.camera_control_mode
        self._job_draw_mode = self.viewport.shape_draw_mode
        self.viewport.set_node_edit_mode(False)
        self.viewport.set_shape_draw_mode(None)
        self.viewport.set_camera_control_mode(True)
        self.tool_rail.set_active_tool("camera")
        for key, button in self.tool_rail.buttons.items():
            if key not in {"camera", "view"}:
                button.setEnabled(False)
        self.properties_panel.setEnabled(False)
        self.tool_combo.setEnabled(False)

        self.job_progress.setRange(0, 0 if indeterminate else 100)
        self.job_progress.setValue(0)
        self.job_progress.setFormat(
            title if indeterminate else f"{title} · %p%"
        )
        self.job_progress.show()
        self.cancel_job_button.setEnabled(True)
        self.cancel_job_button.setVisible(request is not None or cancelable)
        self.statusBar().showMessage(f"{title}…")

        def progress(fraction: float, status: str) -> None:
            if job_id != self._job_sequence:
                return
            value = max(0, min(100, round(fraction * 100)))
            if not indeterminate:
                self.job_progress.setValue(value)
            self.job_progress.setFormat(
                status if indeterminate else f"{status} · %p%"
            )
            self.statusBar().showMessage(
                f"{title}: {status}"
                if indeterminate
                else f"{title}: {status} — {value}%"
            )

        def completed(result: object) -> None:
            if self.project is not self._job_target_project:
                self.statusBar().showMessage(
                    f"{title}: project changed; result discarded", 7000
                )
                return
            try:
                if on_done is not None:
                    on_done(result)
                self.job_progress.setRange(0, 100)
                self.job_progress.setValue(100)
                self.job_progress.setFormat(f"{title} complete · %p%")
            except Exception as exc:  # noqa: BLE001 - always clean worker state
                failed(f"{type(exc).__name__}: {exc}")

        def failed(message: str) -> None:
            if on_failed is not None:
                on_failed(message)
            else:
                self._set_activity_info(f"{title} failed\n{message}")
                self.statusBar().showMessage(
                    f"{title} failed: {message}", 9000
                )
            self.job_progress.setFormat(f"{title} failed")

        def cancelled() -> None:
            self.job_progress.setFormat(f"{title} canceled")
            self.statusBar().showMessage(f"{title} canceled", 5000)

        def cleaned_up() -> None:
            if job_id != self._job_sequence:
                return
            self._background_job = None
            self._job_bridge = None
            self._job_target_project = None
            self.cancel_job_button.hide()

            for key, was_enabled in self._job_action_states.items():
                action = self._ui_actions.get(key)
                if action is not None:
                    action.setEnabled(was_enabled)
            self._job_action_states = {}

            for key, was_enabled in self._job_rail_states.items():
                button = self.tool_rail.buttons.get(key)
                if button is not None:
                    button.setEnabled(was_enabled)
            self._job_rail_states = {}

            self.properties_panel.setEnabled(True)
            self.tool_combo.setEnabled(True)
            self.viewport.set_camera_control_mode(self._job_camera_was_active)
            if not self._job_camera_was_active:
                self.viewport.set_shape_draw_mode(self._job_draw_mode)
                self.tool_rail.set_active_tool(
                    self._job_draw_mode or "select"
                )
            else:
                self.tool_rail.set_active_tool("camera")

            self._sync_toolpath_output_state()
            self._sync_selection_action_state()
            if hasattr(self, "_sync_history_action_state"):
                self._sync_history_action_state()
            if self.generate_toolpaths_button is not None:
                self.generate_toolpaths_button.setEnabled(True)

            QTimer.singleShot(
                1800,
                lambda bar=self.job_progress: (
                    bar.hide() if self._background_job is None else None
                ),
            )

        bridge = JobCallbacks(
            self,
            progress=progress,
            completed=completed,
            failed=failed,
            cancelled=cancelled,
            cleaned_up=cleaned_up,
        )
        self._job_bridge = bridge
        thread.started.connect(worker.run)
        worker.progress.connect(bridge.on_progress)
        worker.completed.connect(bridge.on_completed)
        worker.failed.connect(bridge.on_failed)
        worker.cancelled.connect(bridge.on_cancelled)
        for signal in (worker.completed, worker.failed, worker.cancelled):
            signal.connect(thread.quit)
            signal.connect(worker.deleteLater)
        thread.finished.connect(bridge.on_cleaned_up)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        return True

    def _cancel_background_job(self) -> None:
        state = self._background_job
        if state is None:
            return
        self.cancel_job_button.setEnabled(False)
        self.statusBar().showMessage("Cancelling operation…")
        state.worker.cancel()
