"""Regression tests for the shared progress/work isolation contract."""
from __future__ import annotations

from threading import Event
from time import monotonic, sleep

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication

from carvefoundry.ui.main_window import MainWindow

_APP = QApplication.instance() or QApplication([])


def _wait(window: MainWindow, timeout: float = 25.0) -> None:
    deadline = monotonic() + timeout
    while window._background_job is not None and monotonic() < deadline:
        _APP.processEvents()
        sleep(0.01)
    _APP.processEvents()
    assert window._background_job is None


def test_gui_keeps_processing_events_during_worker_and_recovers_controls() -> None:
    window = MainWindow()
    gate = Event()
    completed: list[tuple[bool, object]] = []
    heartbeat: list[bool] = []
    before_camera = window.viewport.camera_control_mode
    # Tool rail buttons using setDefaultAction() share QAction enabled state.
    # Capture before the job so a post-disable snapshot regression is visible.
    before_actions = {
        key: window._ui_actions[key].isEnabled()
        for key in ("select", "direct_select", "text", "import")
    }
    before_buttons = {
        key: window.tool_rail.buttons[key].isEnabled()
        for key in ("select", "direct_select", "text", "model")
    }
    assert all(before_actions.values())
    assert all(before_buttons.values())

    def task(progress):
        progress(0.2, "Preparing")
        if not gate.wait(5):
            raise RuntimeError("Test worker gate timed out")
        progress(0.8, "Finishing")
        return "ok"

    try:
        assert window._start_background_job(
            "Worker test",
            task=task,
            on_done=lambda result: completed.append(
                (QThread.currentThread() == window.thread(), result)
            ),
        )
        assert window._background_job is not None
        assert window.viewport.camera_control_mode
        assert not window.properties_panel.isEnabled()
        assert not window._ui_actions["select"].isEnabled()
        assert not window.tool_rail.buttons["select"].isEnabled()

        QTimer.singleShot(0, lambda: heartbeat.append(window._background_job is not None))
        _APP.processEvents()
        assert heartbeat == [True], "Qt timer did not fire while the job ran"
        gate.set()
        _wait(window)

        assert completed == [(True, "ok")], "Completion touched GUI off-thread"
        assert window.properties_panel.isEnabled()
        assert window.viewport.camera_control_mode == before_camera
        assert window.job_progress.value() == 100
        assert window._job_bridge is None
        assert before_actions == {
            key: window._ui_actions[key].isEnabled() for key in before_actions
        }
        assert before_buttons == {
            key: window.tool_rail.buttons[key].isEnabled() for key in before_buttons
        }
        window.tool_rail.buttons["select"].click()
        assert not window.viewport.camera_control_mode
        assert window.tool_rail.buttons["select"].isChecked()
    finally:
        gate.set()
        _wait(window)
        window.close()


def test_failed_job_restores_controls_without_overwriting_project() -> None:
    window = MainWindow()
    original = window.project

    def task(progress):
        progress(0.3, "Working")
        raise ValueError("sample failure")

    try:
        assert window._start_background_job("Failing job", task=task)
        _wait(window)

        assert window.project is original
        assert window._background_job is None
        assert "sample failure" in window.activity_info.text()
        assert window.properties_panel.isEnabled()
        assert window._ui_actions["select"].isEnabled()
        assert window.tool_rail.buttons["select"].isEnabled()
        window.tool_rail.buttons["select"].click()
        assert not window.viewport.camera_control_mode
    finally:
        _wait(window)
        window.close()
