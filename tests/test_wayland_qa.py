"""Check the real Wayland QA script's signal wiring in headless CI.

This covers startup wiring only. Real compositor, GPU, mouse and keyboard
acceptance still requires the physical KDE Plasma session checklist.
"""
from __future__ import annotations

from pathlib import Path
from runpy import run_path

from PySide6.QtWidgets import QApplication

from carvefoundry import app as carve_app
from carvefoundry.ui.project_window import MainWindow

# The QA script is a repo-only executable, not part of the installed src
# package. pytest's console entry point does not put the repo root on sys.path.
_script_path = Path(__file__).resolve().parents[1] / "scripts" / "wayland_qa.py"
qa = run_path(str(_script_path), run_name="carvefoundry_wayland_qa")
NativeInputRecorder = qa["NativeInputRecorder"]
attach_native_input_telemetry = qa["attach_native_input_telemetry"]

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


def test_wayland_qa_uses_exact_production_qt_bootstrap() -> None:
    # The separate QA launcher previously created a bare QApplication and
    # skipped the depth buffer + multisampling requested by normal launch.
    assert qa["create_application"] is carve_app.create_application


def test_production_bootstrap_configures_gl_before_qapplication(monkeypatch) -> None:
    events = []

    class FakeApplication:
        def __init__(self, argv):
            events.append(("QApplication", list(argv)))

        def setApplicationDisplayName(self, name):
            events.append(("display", name))

        def setWindowIcon(self, icon):
            events.append(("icon", not icon.isNull()))

        def setStyleSheet(self, stylesheet):
            events.append(("stylesheet", stylesheet))

    monkeypatch.setattr(
        carve_app, "_configure_opengl",
        lambda: events.append(("configure_gl", None)),
    )
    monkeypatch.setattr(carve_app, "QApplication", FakeApplication)

    result = carve_app.create_application(["carvefoundry"])
    assert isinstance(result, FakeApplication)
    assert events[0] == ("configure_gl", None)
    assert events[1] == ("QApplication", ["carvefoundry"])
    assert events[2] == ("display", "CarveFoundry")
    assert events[3] == ("icon", True)
    assert events[4] == ("stylesheet", carve_app.APP_STYLESHEET)
