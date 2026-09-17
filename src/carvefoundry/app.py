from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.theme import APP_STYLESHEET


def main() -> int:
    # Qt 6 handles Wayland natively. Do not force XCB; respect the active KDE session.
    QCoreApplication.setOrganizationName("CarveFoundry")
    QCoreApplication.setApplicationName("CarveFoundry")
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("CarveFoundry")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
