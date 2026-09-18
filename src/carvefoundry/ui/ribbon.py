from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore, QtGui, QtWidgets


_ICON_CANDIDATES: dict[str, tuple[str, ...]] = {
    "new": ("document-new",),
    "open": ("document-open",),
    "save": ("document-save",),
    "save as": ("document-save-as", "document-save"),
    "import": ("document-import", "document-open"),
    "export g-code": ("document-export", "document-save"),
    "undo": ("edit-undo",),
    "redo": ("edit-redo",),
    "cut": ("edit-cut",),
    "copy": ("edit-copy",),
    "paste": ("edit-paste",),
    "delete": ("edit-delete", "user-trash"),
    "align": ("align-horizontal-center", "transform-move"),
    "center": ("align-horizontal-center", "transform-move"),
    "group": ("object-group", "selection-group"),
    "ungroup": ("object-ungroup", "selection-group"),
    "duplicate": ("edit-copy",),
    "move up": ("go-up",),
    "move down": ("go-down",),
    "rectangle": ("draw-rectangle",),
    "ellipse": ("draw-ellipse",),
    "polygon": ("draw-polygon",),
    "line": ("draw-line",),
    "text": ("draw-text",),
    "pen": ("draw-freehand", "document-edit"),
    "trace image": ("image-x-generic", "document-preview"),
    "svg": ("image-svg+xml", "image-x-generic"),
    "dxf": ("application-vnd.dxf", "applications-engineering"),
    "stl": ("model-stl", "applications-engineering", "draw-cuboid"),
    "image": ("image-x-generic",),
    "g-code": ("text-x-script", "text-x-generic"),
    "profile": ("draw-bezier-curves", "draw-line"),
    "pocket": ("draw-rectangle", "applications-engineering"),
    "v-carve": ("draw-triangle", "applications-engineering"),
    "engrave": ("draw-freehand", "document-edit"),
    "drill": ("tools", "applications-engineering"),
    "tabs": ("view-list-tree", "applications-engineering"),
    "calculate": ("accessories-calculator",),
    "preview": ("document-preview", "view-preview"),
    "orient": ("transform-rotate",),
    "scale": ("transform-scale",),
    "position": ("transform-move",),
    "center xy": ("align-horizontal-center", "transform-move"),
    "top to z0": ("go-top", "go-up"),
    "rough": ("applications-engineering", "tools"),
    "finish": ("emblem-default", "applications-engineering"),
    "rest": ("media-playback-pause", "applications-engineering"),
    "waterline": ("draw-line", "applications-engineering"),
    "library": ("folder", "view-list-icons"),
    "new tool": ("list-add", "tools"),
    "custom profile": ("document-edit", "tools"),
    "calculator": ("accessories-calculator",),
    "machine profile": ("computer", "preferences-system"),
    "work area": ("view-grid", "draw-rectangle"),
    "origin": ("crosshairs", "mark-location"),
    "postprocessor": ("preferences-system", "system-run"),
    "connect": ("network-connect", "network-wired"),
    "probe": ("crosshairs", "mark-location"),
    "jog": ("input-gaming", "transform-move"),
    "fit 3d": ("zoom-fit-best",),
    "fit view": ("zoom-fit-best",),
    "stock": ("draw-cuboid", "applications-engineering"),
    "grid": ("view-grid",),
    "rulers": ("measure", "kruler", "view-grid"),
    "2d": ("draw-rectangle",),
    "toolpaths": ("draw-bezier-curves", "applications-engineering"),
    "rapids": ("go-next", "media-seek-forward"),
    "simulate": ("media-playback-start",),
    "reset ui": ("edit-clear-history", "view-refresh"),
    "project panel": ("view-list-tree", "sidebar-show"),
    "properties": ("document-properties",),
    "status bar": ("view-status-bar", "dialog-information"),
    "view controls": ("configure-toolbars", "preferences-system"),
    "reverse horizontal": ("object-flip-horizontal", "transform-flip-horizontal"),
    "perspective": ("camera-photo", "view-preview"),
    "orthographic": ("draw-cuboid", "view-grid"),
    "isometric": ("draw-cuboid", "applications-engineering"),
    "top": ("go-top", "go-up"),
    "bottom": ("go-bottom", "go-down"),
    "front": ("go-home", "draw-cuboid"),
    "back": ("go-previous", "draw-cuboid"),
    "left": ("go-previous",),
    "right": ("go-next",),
}

_STANDARD_FALLBACKS: dict[str, QtWidgets.QStyle.StandardPixmap] = {
    "new": QtWidgets.QStyle.StandardPixmap.SP_FileIcon,
    "open": QtWidgets.QStyle.StandardPixmap.SP_DialogOpenButton,
    "save": QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton,
    "save as": QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton,
    "undo": QtWidgets.QStyle.StandardPixmap.SP_ArrowBack,
    "redo": QtWidgets.QStyle.StandardPixmap.SP_ArrowForward,
    "delete": QtWidgets.QStyle.StandardPixmap.SP_TrashIcon,
    "move up": QtWidgets.QStyle.StandardPixmap.SP_ArrowUp,
    "move down": QtWidgets.QStyle.StandardPixmap.SP_ArrowDown,
    "top": QtWidgets.QStyle.StandardPixmap.SP_ArrowUp,
    "bottom": QtWidgets.QStyle.StandardPixmap.SP_ArrowDown,
    "left": QtWidgets.QStyle.StandardPixmap.SP_ArrowLeft,
    "right": QtWidgets.QStyle.StandardPixmap.SP_ArrowRight,
}


def _ribbon_icon(text: str) -> QtGui.QIcon:
    label = text.replace("\n", " ").strip().lower()
    candidates = _ICON_CANDIDATES.get(label, ())
    for candidate in candidates:
        icon = QtGui.QIcon.fromTheme(candidate)
        if not icon.isNull():
            return icon

    fallback = _STANDARD_FALLBACKS.get(
        label,
        QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView,
    )
    app = QtWidgets.QApplication.instance()
    if app is not None:
        return app.style().standardIcon(fallback)
    return QtGui.QIcon()


class RibbonButton(QtWidgets.QToolButton):
    def __init__(
        self,
        text: str,
        callback: Callable[[], None] | None = None,
        *,
        primary: bool = False,
    ):
        super().__init__()
        self.setText(text)
        self.setIcon(_ribbon_icon(text))
        self.setObjectName("RibbonPrimary" if primary else "RibbonButton")
        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QtCore.QSize(28, 28))
        self.setMinimumHeight(68)
        self.setToolTip(text.replace("\n", " "))

        # Size to the visible label instead of Qt eliding it with "...".
        # Multiline labels keep dense ribbon groups readable without forcing
        # every button to the width of its full phrase.
        longest_line = max(text.splitlines(), key=len, default=text)
        label_width = self.fontMetrics().horizontalAdvance(longest_line)
        self.setMinimumWidth(max(58, label_width + 24))
        if callback is not None:
            self.clicked.connect(lambda _checked=False: callback())


class RibbonGroup(QtWidgets.QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("RibbonGroup")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 4)
        outer.setSpacing(3)
        self.buttons = QtWidgets.QHBoxLayout()
        self.buttons.setSpacing(3)
        outer.addLayout(self.buttons, 1)
        label = QtWidgets.QLabel(title)
        label.setObjectName("RibbonGroupTitle")
        label.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(label)

    def add_button(
        self,
        text: str,
        callback: Callable[[], None] | None = None,
        *,
        primary: bool = False,
    ) -> RibbonButton:
        button = RibbonButton(text, callback, primary=primary)
        self.buttons.addWidget(button)
        return button


class RibbonPage(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("RibbonPage")
        self.layout_ = QtWidgets.QHBoxLayout(self)
        self.layout_.setContentsMargins(8, 6, 8, 6)
        self.layout_.setSpacing(6)
        self.layout_.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

    def add_group(self, title: str) -> RibbonGroup:
        group = RibbonGroup(title)
        self.layout_.addWidget(group)
        return group


class Ribbon(QtWidgets.QTabWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Ribbon")
        self.setDocumentMode(True)
        self.setMovable(False)
        self.setTabsClosable(False)
        self.setFixedHeight(140)

    def add_page(self, title: str) -> RibbonPage:
        page = RibbonPage()
        self.addTab(page, title)
        return page
