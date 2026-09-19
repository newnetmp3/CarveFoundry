from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .ribbon import _ribbon_icon


class ToolRail(QFrame):
    """Compact Photoshop-style vertical tool rail with flyout groups."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ToolRail")
        self.setFixedWidth(46)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )

        # Keep the rail compact on laptop-sized windows. All real tools
        # remain reachable by scrolling, with no vertical scrollbar covering
        # the 38-pixel icons.
        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(0)
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("ToolRailScroll")
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._content = QWidget()
        self._content.setObjectName("ToolRailContent")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(3, 5, 3, 5)
        self._layout.setSpacing(2)
        self._scroll.setWidget(self._content)
        wrapper.addWidget(self._scroll)
        self.buttons: dict[str, QToolButton] = {}
        self.actions: dict[str, QAction] = {}
        self._flyout_callbacks: dict[str, Callable[[], None]] = {}
        self._action_callbacks: dict[str, Callable[[], None]] = {}
        self._draw_button_keys = {
            "rectangle": "shapes",
            "ellipse": "shapes",
            "polygon": "shapes",
            "line": "line",
            "text": "text",
            "pen": "vector",
            "measure": "measure",
            "fixture": "fixture",
        }

    @staticmethod
    def _button(
        label: str,
        *,
        tooltip: str,
        checkable: bool = False,
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName("ToolRailButton")
        button.setIcon(_ribbon_icon(label))
        button.setIconSize(QSize(20, 20))
        button.setFixedSize(38, 38)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setAutoRaise(False)
        button.setCheckable(checkable)
        button.setToolTip(tooltip)
        button.setAccessibleName(label)
        return button

    def add_tool(
        self,
        key: str,
        label: str,
        callback: Callable[[], None],
        *,
        tooltip: str,
        checkable: bool = False,
    ) -> QToolButton:
        button = self._button(
            label,
            tooltip=tooltip,
            checkable=checkable,
        )
        button.clicked.connect(
            lambda _checked=False, fn=callback: fn()
        )
        self.buttons[key] = button
        self._layout.addWidget(button)
        return button

    def add_flyout(
        self,
        key: str,
        label: str,
        options: tuple[
            tuple[str, str, Callable[[], None], str],
            ...,
        ],
        *,
        tooltip: str,
        checkable: bool = False,
    ) -> QToolButton:
        button = self._button(
            label,
            tooltip=tooltip,
            checkable=checkable,
        )
        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        menu = QMenu(button)
        menu.setObjectName("ToolRailMenu")
        first_key: str | None = None
        for action_key, action_label, callback, action_tooltip in options:
            action = QAction(
                _ribbon_icon(action_label),
                action_label,
                menu,
            )
            action.setToolTip(action_tooltip)
            action.setStatusTip(action_tooltip)
            self.actions[action_key] = action
            self._action_callbacks[action_key] = callback
            menu.addAction(action)
            if first_key is None:
                first_key = action_key

            def choose(
                _checked: bool = False,
                *,
                selected_key: str = action_key,
                selected_action: QAction = action,
                fn: Callable[[], None] = callback,
            ) -> None:
                self._set_flyout_choice(
                    key,
                    selected_key,
                    selected_action,
                    fn,
                )
                fn()

            action.triggered.connect(choose)

        button.setMenu(menu)
        self.buttons[key] = button
        self._layout.addWidget(button)

        if first_key is not None:
            first_action = self.actions[first_key]
            first_callback = next(
                callback
                for action_key, _label, callback, _tip in options
                if action_key == first_key
            )
            self._set_flyout_choice(
                key,
                first_key,
                first_action,
                first_callback,
            )

        button.clicked.connect(
            lambda _checked=False, flyout_key=key: self._trigger_flyout(
                flyout_key
            )
        )
        return button

    def _set_flyout_choice(
        self,
        key: str,
        action_key: str,
        action: QAction,
        callback: Callable[[], None],
    ) -> None:
        button = self.buttons.get(key)
        if button is None:
            return
        button.setIcon(action.icon())
        button.setToolTip(
            f"{action.toolTip()}\n"
            "Click the small arrow for related tools."
        )
        button.setProperty("currentAction", action_key)
        self._flyout_callbacks[key] = callback

    def _trigger_flyout(self, key: str) -> None:
        callback = self._flyout_callbacks.get(key)
        if callback is not None:
            callback()

    def add_menu(
        self,
        key: str,
        label: str,
        menu: QMenu,
        *,
        tooltip: str,
        primary_callback: Callable[[], None] | None = None,
        checkable: bool = False,
    ) -> QToolButton:
        """Add an icon button backed by a full command menu/flyout."""

        button = self._button(
            label,
            tooltip=tooltip,
            checkable=checkable,
        )
        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        button.setMenu(menu)
        if primary_callback is not None:
            button.clicked.connect(
                lambda _checked=False, fn=primary_callback: fn()
            )
        else:
            button.setPopupMode(
                QToolButton.ToolButtonPopupMode.InstantPopup
            )
        self.buttons[key] = button
        self._layout.addWidget(button)
        return button

    def add_action_tool(
        self,
        key: str,
        action: QAction,
        *,
        tooltip: str | None = None,
    ) -> QToolButton:
        """Add a compact rail button driven by a shared QAction."""

        button = self._button(
            action.text(),
            tooltip=tooltip or action.toolTip() or action.text(),
            checkable=action.isCheckable(),
        )
        button.setDefaultAction(action)
        button.setObjectName("ToolRailButton")
        button.setIconSize(QSize(20, 20))
        button.setFixedSize(38, 38)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.buttons[key] = button
        self._layout.addWidget(button)
        return button

    def add_separator(self) -> None:
        separator = QFrame()
        separator.setObjectName("ToolRailSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFixedHeight(7)
        self._layout.addWidget(separator)

    def add_stretch(self) -> None:
        self._layout.addStretch(1)

    def set_active_tool(self, tool: str) -> None:
        """Reflect the active camera/select/draw mode without changing it."""

        camera = self.buttons.get("camera")
        if camera is not None:
            camera.setChecked(tool == "camera")

        select = self.buttons.get("select")
        if select is not None:
            select.setChecked(tool == "select")

        active_key = self._draw_button_keys.get(tool)
        for key in ("shapes", "line", "text", "vector", "measure", "fixture"):
            button = self.buttons.get(key)
            if button is not None:
                button.setChecked(key == active_key)

        if tool in self.actions and active_key == "shapes":
            action = self.actions[tool]
            callback = self._action_callbacks.get(tool)
            if callback is not None:
                self._set_flyout_choice(
                    "shapes",
                    tool,
                    action,
                    callback,
                )

    def set_active_draw_tool(self, tool: str | None) -> None:
        """Compatibility wrapper for older draw-mode synchronization."""

        self.set_active_tool(tool or "select")

    def set_tool_enabled(self, key: str, enabled: bool) -> None:
        button = self.buttons.get(key)
        if button is not None:
            button.setEnabled(bool(enabled))
