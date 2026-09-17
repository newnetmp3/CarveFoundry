from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.theme import APP_STYLESHEET


def main() -> int:
    # Qt 6 handles Wayland and high-DPI scaling natively. Do not force XCB.
    QCoreApplication.setOrganizationName("CarveFoundry")
    QCoreApplication.setApplicationName("CarveFoundry")

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("CarveFoundry")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
