"""Real Qt mouse input for Photopea-style rail click vs press-and-hold."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QToolButton

from carvefoundry.ui.main_window import MainWindow
from carvefoundry.ui.tool_rail import ToolRail

_APP = QApplication.instance() or QApplication([])


def _rail_with_shapes() -> tuple[ToolRail, list[str]]:
    events: list[str] = []
    rail = ToolRail()
    rail.add_flyout(
        "shapes", "Rectangle",
        (
            ("rectangle", "Rectangle", lambda: events.append("rectangle"), "Draw rectangle"),
            ("ellipse", "Ellipse", lambda: events.append("ellipse"), "Draw ellipse"),
        ),
        tooltip="Choose shape",
        checkable=True,
    )
    rail.show()
    _APP.processEvents()
    return rail, events


def test_short_click_uses_current_tool_then_choice_updates_icon_and_callback() -> None:
    rail, events = _rail_with_shapes()
    try:
        button = rail.buttons["shapes"]
        assert button.popupMode() == QToolButton.ToolButtonPopupMode.DelayedPopup
        assert button.property("holdForOptions") is True
        assert button.iconSize().width() == 25
        menu = button.menu()
        assert menu is not None

        original_icon_key = button.icon().cacheKey()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert events == ["rectangle"]
        assert not menu.isVisible()

        menu.actions()[1].trigger()  # User chooses another tool in the flyout.
        assert events == ["rectangle", "ellipse"]
        assert button.property("currentAction") == "ellipse"
        assert button.icon().cacheKey() != original_icon_key
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert events == ["rectangle", "ellipse", "ellipse"]
        assert not menu.isVisible()
    finally:
        rail.close()


def test_press_and_hold_opens_flyout_without_running_active_tool() -> None:
    rail, events = _rail_with_shapes()
    try:
        button = rail.buttons["shapes"]
        menu = button.menu()
        assert menu is not None
        opened: list[bool] = []
        menu.aboutToShow.connect(lambda: opened.append(True))
        # Native QToolButton DelayedPopup may enter QMenu.exec() in its
        # hold timer; close it from Qt's event loop so qWait can return.
        QTimer.singleShot(1200, menu.close)
        QTest.mousePress(button, Qt.MouseButton.LeftButton)
        QTest.qWait(1450)  # Longer than Qt's platform tool-button hold delay.
        assert opened == [True]
        assert events == []
        QTest.mouseRelease(button, Qt.MouseButton.LeftButton)
        _APP.processEvents()
        assert events == [], "Releasing after a held click must not draw anything."
        menu.close()
    finally:
        rail.close()


def test_menu_only_button_does_not_run_an_arbitrary_action_on_short_click() -> None:
    events: list[str] = []
    rail = ToolRail()
    menu = QMenu(rail)
    action = menu.addAction("Dangerous machine command")
    action.triggered.connect(lambda: events.append("machine"))
    button = rail.add_menu(
        "machine", "Machine Profile", menu, tooltip="Machine controls",
    )
    rail.show()
    _APP.processEvents()
    try:
        assert button.popupMode() == QToolButton.ToolButtonPopupMode.DelayedPopup
        shows: list[bool] = []
        menu.aboutToShow.connect(lambda: shows.append(True))
        # QToolButton.showMenu may use a nested menu event loop.
        QTimer.singleShot(100, menu.close)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert shows == [True]
        assert events == []
    finally:
        rail.close()


def test_corner_marker_is_part_of_active_tool_icon() -> None:
    pixmap = QPixmap(22, 22)
    pixmap.fill(QColor("#526375"))
    icon = ToolRail._flyout_icon(QIcon(pixmap))
    result = icon.pixmap(28, 28).toImage()
    assert result.width() == 28
    assert result.height() == 28
    # Original tool icon is visible; the south-east marker occupies its corner.
    assert result.pixelColor(8, 8) == QColor("#526375")
    marker = result.pixelColor(24, 25)
    assert marker.alpha() >= 245  # Qt antialiasing varies slightly by build.
    assert abs(marker.red() - 200) <= 2
    assert marker.green() == 255
    assert abs(marker.blue() - 61) <= 2


def test_main_window_cam_icon_tracks_chosen_active_operation() -> None:
    window = MainWindow()
    try:
        button = window.tool_rail.buttons["cam"]
        assert button.popupMode() == QToolButton.ToolButtonPopupMode.DelayedPopup
        window._select_cam_operation("pocket")
        pocket_icon = button.icon().cacheKey()
        assert button.property("currentAction") == window._ui_actions["cam_pocket"].text()
        window._select_cam_operation("finish")
        assert button.property("currentAction") == window._ui_actions["cam_finish"].text()
        assert button.icon().cacheKey() != pocket_icon
    finally:
        window.close()
