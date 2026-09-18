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
    "invert vertical": ("object-flip-vertical", "transform-flip-vertical"),
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
        callback=None,
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


class RibbonSelector(QtWidgets.QWidget):
    """Compact labeled selector designed to fit inside the Office-style ribbon."""

    def __init__(
        self,
        title: str,
        values: tuple[str, ...] | list[str],
        current: str,
        callback=None,
        *,
        tooltip: str = "",
        minimum_width: int = 108,
    ):
        super().__init__()
        self.setObjectName("RibbonSelector")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 5, 2, 4)
        layout.setSpacing(3)

        label = QtWidgets.QLabel(title)
        label.setObjectName("RibbonSelectorTitle")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(label)

        self.combo = QtWidgets.QComboBox()
        self.combo.setObjectName("RibbonCombo")
        self.combo.addItems(values)
        self.combo.setMinimumWidth(minimum_width)
        self.combo.setMaximumWidth(max(minimum_width + 34, 150))
        if tooltip:
            self.setToolTip(tooltip)
            label.setToolTip(tooltip)
            self.combo.setToolTip(tooltip)

        index = self.combo.findText(current)
        if index >= 0:
            self.combo.setCurrentIndex(index)
        if callback is not None:
            self.combo.currentTextChanged.connect(callback)
        layout.addWidget(self.combo)

        self.setMinimumHeight(68)


class RibbonSlider(QtWidgets.QWidget):
    """Compact labeled slider with a live CAM readout."""

    def __init__(
        self,
        title: str,
        minimum: int,
        maximum: int,
        value: int,
        callback=None,
        *,
        tooltip: str = "",
        minimum_width: int = 190,
        low_label: str = "Faster",
        high_label: str = "More",
    ):
        super().__init__()
        self.setObjectName("RibbonSlider")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 2)
        layout.setSpacing(1)

        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("RibbonSelectorTitle")
        title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title_label)

        slider_row = QtWidgets.QHBoxLayout()
        slider_row.setContentsMargins(0, 0, 0, 0)
        slider_row.setSpacing(4)

        low = QtWidgets.QLabel(low_label)
        low.setObjectName("RibbonSliderEnd")
        slider_row.addWidget(low)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setObjectName("RibbonDetailSlider")
        self.slider.setRange(int(minimum), int(maximum))
        self.slider.setValue(int(value))
        self.slider.setSingleStep(1)
        self.slider.setPageStep(10)
        self.slider.setMinimumWidth(max(90, minimum_width - 82))
        slider_row.addWidget(self.slider, 1)

        high = QtWidgets.QLabel(high_label)
        high.setObjectName("RibbonSliderEnd")
        slider_row.addWidget(high)
        layout.addLayout(slider_row)

        self.readout = QtWidgets.QLabel("")
        self.readout.setObjectName("RibbonSliderReadout")
        self.readout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.readout)

        if tooltip:
            self.setToolTip(tooltip)
            title_label.setToolTip(tooltip)
            self.slider.setToolTip(tooltip)
            self.readout.setToolTip(tooltip)

        if callback is not None:
            self.slider.valueChanged.connect(callback)

        self.setMinimumWidth(minimum_width)
        self.setMinimumHeight(68)

    def set_readout(self, text: str) -> None:
        self.readout.setText(text)


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
        callback=None,
        *,
        primary: bool = False,
    ) -> RibbonButton:
        button = RibbonButton(text, callback, primary=primary)
        self.buttons.addWidget(button)
        return button

    def add_selector(
        self,
        title: str,
        values: tuple[str, ...] | list[str],
        current: str,
        callback=None,
        *,
        tooltip: str = "",
        minimum_width: int = 108,
    ) -> QtWidgets.QComboBox:
        selector = RibbonSelector(
            title,
            values,
            current,
            callback,
            tooltip=tooltip,
            minimum_width=minimum_width,
        )
        self.buttons.addWidget(selector)
        return selector.combo

    def add_slider(
        self,
        title: str,
        minimum: int,
        maximum: int,
        value: int,
        callback=None,
        *,
        tooltip: str = "",
        minimum_width: int = 190,
        low_label: str = "Faster",
        high_label: str = "More",
    ) -> RibbonSlider:
        slider = RibbonSlider(
            title,
            minimum,
            maximum,
            value,
            callback,
            tooltip=tooltip,
            minimum_width=minimum_width,
            low_label=low_label,
            high_label=high_label,
        )
        self.buttons.addWidget(slider)
        return slider


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
