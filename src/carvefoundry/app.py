from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from .ui.project_window import MainWindow
from .ui.theme import APP_STYLESHEET


def _configure_opengl() -> None:
    """Request a modern desktop OpenGL context before QApplication is created."""

    surface_format = QSurfaceFormat()
    surface_format.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    surface_format.setVersion(3, 3)
    surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface_format.setDepthBufferSize(24)
    surface_format.setStencilBufferSize(8)
    surface_format.setSamples(4)
    QSurfaceFormat.setDefaultFormat(surface_format)


def main() -> int:
    # Qt 6 handles Wayland and high-DPI scaling natively. Do not force XCB.
    QCoreApplication.setOrganizationName("CarveFoundry")
    QCoreApplication.setApplicationName("CarveFoundry")
    _configure_opengl()

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("CarveFoundry")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
