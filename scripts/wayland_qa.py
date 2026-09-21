"""Real Qt/Wayland input event recorder for CarveFoundry's native GL viewport.

Run from an actual KDE Plasma Wayland graphical session (not XWayland,
QT_QPA_PLATFORM=offscreen, Xvfb or CI). The operator performs the checklist in
docs/WAYLAND_QA.md; QTest-injected events do NOT count as compositor testing.
"""
from __future__ import annotations

import os
import sys
from time import monotonic

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QGuiApplication

from carvefoundry.app import create_application
from carvefoundry.ui.project_window import MainWindow


class NativeInputRecorder(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._last_motion = 0.0
        self.counts = {
            "press": 0, "move": 0, "release": 0, "wheel": 0, "key": 0,
        }

    def eventFilter(self, _obj: QObject, event: QEvent) -> bool:
        kind = {
            QEvent.Type.MouseButtonPress: "press",
            QEvent.Type.MouseMove: "move",
            QEvent.Type.MouseButtonRelease: "release",
            QEvent.Type.Wheel: "wheel",
            QEvent.Type.KeyPress: "key",
        }.get(event.type())
        if kind is None:
            return False
        self.counts[kind] += 1
        now = monotonic()
        if kind == "move":
            if now - self._last_motion < 0.25:
                return False
            self._last_motion = now
        print(f"[native Wayland input] {kind}: {self.counts[kind]}", flush=True)
        return False  # Never consume a real user event.


def attach_native_input_telemetry(
    window: MainWindow, recorder: NativeInputRecorder,
):
    """Record real renderer events; MeshViewport does not forward orbitStarted.

    Selection and item transform events are public MeshViewport signals, but
    orbitStarted belongs to its native QOpenGLWindow child. Keep the same event
    filter and diagnostics for the actual window receiving Wayland input.
    """
    renderer = window.viewport._renderer
    renderer.installEventFilter(recorder)
    window.viewport.selectionRequested.connect(
        lambda indices, mode: print(
            f"[selection] mode={mode}, indices={indices}", flush=True
        )
    )
    window.viewport.itemTransformChanged.connect(
        lambda index: print(
            f"[gizmo/keyboard transform] object={index}", flush=True
        )
    )
    renderer.orbitStarted.connect(
        lambda: print("[camera] orbit started", flush=True)
    )
    return renderer


def main() -> int:
    # Use the same pre-QApplication surface format as the normal entry point.
    # Without its depth buffer the QA view can show torn/overlapping mesh faces.
    app = create_application(sys.argv)
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    platform = QGuiApplication.platformName().lower()
    if session != "wayland" or platform != "wayland":
        print(
            "STOP: requires a real KDE Wayland session. "
            f"XDG_SESSION_TYPE={session!r}; Qt platform={platform!r}. "
            "Run with QT_QPA_PLATFORM=wayland in KDE Plasma Wayland.",
            file=sys.stderr,
        )
        return 2

    window = MainWindow()
    recorder = NativeInputRecorder()
    renderer = attach_native_input_telemetry(window, recorder)
    window.show()

    def report_context() -> None:
        context = renderer.context()
        print(
            "CarveFoundry REAL compositor QA: "
            f"session={session}, Qt={platform}, "
            f"native window exposed={renderer.isExposed()}, "
            f"OpenGL context={bool(context and context.isValid())}, "
            f"depth={context.format().depthBufferSize() if context else 'none'}, "
            f"samples={context.format().samples() if context else 'none'}",
            flush=True,
        )
        print(
            "Perform every step in docs/WAYLAND_QA.md using physical input. "
            "Input, selection, orbit and transforms will be logged here.",
            flush=True,
        )

    QTimer.singleShot(900, report_context)
    result = app.exec()
    print(f"Native input totals: {recorder.counts}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
