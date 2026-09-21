"""Check the real Wayland QA script's signal wiring in headless CI.

This covers startup wiring only. Real compositor, GPU, mouse and keyboard
acceptance still requires the physical KDE Plasma session checklist.
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from carvefoundry.ui.project_window import MainWindow
from scripts.wayland_qa import NativeInputRecorder, attach_native_input_telemetry

_APP = QApplication.instance() or QApplication([])


def test_wayland_qa_records_renderer_orbit_and_wrapper_selection(capsys) -> None:
    window = MainWindow()
    recorder = NativeInputRecorder()
    try:
        renderer = attach_native_input_telemetry(window, recorder)
        assert renderer is window.viewport._renderer
        assert not hasattr(window.viewport, "orbitStarted")
        assert hasattr(renderer, "orbitStarted")

        # Simulate only the signal connections, not a real Wayland event.
        renderer.orbitStarted.emit()
        window.viewport.selectionRequested.emit([0], "replace")
        window.viewport.itemTransformChanged.emit(0)
        recorded = capsys.readouterr().out
        assert "[camera] orbit started" in recorded
        assert "[selection] mode=replace, indices=[0]" in recorded
        assert "[gizmo/keyboard transform] object=0" in recorded
    finally:
        renderer = window.viewport._renderer
        renderer.removeEventFilter(recorder)
        window.close()
