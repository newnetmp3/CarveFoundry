from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6.QtCore import QItemSelectionModel, QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QFont, QFontDatabase, QFontInfo, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ..cam.gcode import write_grbl, write_grbl_program
from ..core.font_handler import describe_qt_font_face
from ..core.primitives import text_mesh
from ..core.project import Project, ProjectItem, TextProperties
from ..core.project_file import (
    PROJECT_SUFFIX,
    ProjectFileError,
    load_project,
    save_project,
)
from ..core.units import ModelUnits
from .import_worker import ImportWorker
from .layers_popup import LayersPopup
from .ribbon import Ribbon, _ribbon_icon
from .ribbon_actions import RibbonActionsMixin
from .tool_rail import ToolRail
from .viewport import MeshViewport

_FONT_FAMILY_VARIANT_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("Extra Condensed", "Extra Condensed"),
    ("ExtraCondensed", "Extra Condensed"),
    ("Ultra Condensed", "Ultra Condensed"),
    ("UltraCondensed", "Ultra Condensed"),
    ("Semi Condensed", "Semi Condensed"),
    ("SemiCondensed", "Semi Condensed"),
    ("Semi Expanded", "Semi Expanded"),
    ("SemiExpanded", "Semi Expanded"),
    ("Extra Expanded", "Extra Expanded"),
    ("ExtraExpanded", "Extra Expanded"),
    ("Ultra Expanded", "Ultra Expanded"),
    ("UltraExpanded", "Ultra Expanded"),
    ("Extra Light", "ExtraLight"),
    ("ExtraLight", "ExtraLight"),
    ("Ultra Light", "UltraLight"),
    ("UltraLight", "UltraLight"),
    ("Semi Light", "SemiLight"),
    ("SemiLight", "SemiLight"),
    ("Demi Bold", "DemiBold"),
    ("DemiBold", "DemiBold"),
    ("Semi Bold", "SemiBold"),
    ("SemiBold", "SemiBold"),
    ("Extra Bold", "ExtraBold"),
    ("ExtraBold", "ExtraBold"),
    ("Ultra Bold", "UltraBold"),
    ("UltraBold", "UltraBold"),
    ("SemCond", "Semi Condensed"),
    ("SmCn", "Semi Condensed"),
    ("SemBd", "SemiBold"),
    ("SmBd", "SemiBold"),
    ("ExtCond", "Extra Condensed"),
    ("XCn", "Extra Condensed"),
    ("ExtLt", "ExtraLight"),
    ("XLt", "ExtraLight"),
    ("ExtBd", "ExtraBold"),
    ("XBd", "ExtraBold"),
    ("Med", "Medium"),
    ("Md", "Medium"),
    ("Lt", "Light"),
    ("Th", "Thin"),
    ("Blk", "Black"),
    ("Bk", "Book"),
    ("Ret", "Retina"),
    ("Condensed", "Condensed"),
    ("Cond", "Condensed"),
    ("Cn", "Condensed"),
    ("Mono", "Monospaced"),
    ("Propo", "Proportional"),
    ("NFM", "Nerd Font Mono"),
    ("NFP", "Nerd Font Proportional"),
    ("NF", "Nerd Font"),
    ("Compressed", "Compressed"),
    ("Expanded", "Expanded"),
    ("Extended", "Extended"),
    ("Narrow", "Narrow"),
    ("Display", "Display"),
    ("Headline", "Headline"),
    ("Caption", "Caption"),
    ("Text", "Text"),
    ("Thin", "Thin"),
    ("Light", "Light"),
    ("Book", "Book"),
    ("Medium", "Medium"),
    ("Bold", "Bold"),
    ("Black", "Black"),
    ("Heavy", "Heavy"),
    ("Regular", "Regular"),
)


class Panel(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("WorkspacePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QLabel(title)
        self.header.setObjectName("PanelHeader")
        self.header.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(self.header)

        self.body = QWidget()
        self.body.setObjectName("InspectorBody")
        self.body.setMinimumWidth(0)
        self.body.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 8, 8, 8)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("InspectorScrollArea")
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setWidget(self.body)
        layout.addWidget(self.scroll_area, 1)


class MainWindow(RibbonActionsMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.project_path: Path | None = None
        self._updating_transform_controls = False
        self._updating_text_controls = False
        self._updating_stock_controls = False
        self._updating_project_list = False
        self._updating_object_selector = False
        self._import_thread: QThread | None = None
        self._import_worker: ImportWorker | None = None
        self._import_target_project: Project | None = None
        self._settings = QSettings()
        self._option_buttons: dict[str, object] = {}
        self._history_action_buttons: dict[str, list[object]] = {
            "undo": [],
            "redo": [],
        }
        self._toolpath_output_buttons: list[object] = []
        self._model_selection_buttons: list[object] = []
        self._selection_action_buttons: dict[str, object] = {}
        self._calculate_button = None
        self.generate_toolpaths_button: QPushButton | None = None
        self._toolpaths_stale_reason: str | None = None
        self._text_update_timer = QTimer(self)
        self._text_update_timer.setSingleShot(True)
        self._text_update_timer.setInterval(275)
        self._text_update_timer.timeout.connect(
            self._apply_text_properties_from_controls
        )
        self._init_ribbon_action_state()
        self.setWindowTitle("CarveFoundry")
        self.resize(1500, 900)
        self.setMinimumSize(1050, 650)

        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_brand_row())

        # Keep the former ribbon as a non-visible compatibility host for the
        # existing live CAM widgets while presenting a Photopea-style menu bar
        # and vertical tool rail to the user.
        self.ribbon = Ribbon()
        self._populate_ribbon()
        self.ribbon.hide()

        self._build_command_actions()
        self.main_menu_bar = self._build_main_menu_bar()
        layout.addWidget(self.main_menu_bar)
        layout.addWidget(self._build_workspace(), 1)

        status = QStatusBar()
        self.import_progress = QProgressBar()
        self.import_progress.setObjectName("ImportProgress")
        self.import_progress.setFixedWidth(220)
        self.import_progress.setTextVisible(False)
        self.import_progress.hide()
        status.addPermanentWidget(self.import_progress)
        status.showMessage("Ready — no machine connected")
        self.setStatusBar(status)
        self._install_shortcuts()

        self.viewport.viewSettingsChanged.connect(self._save_viewport_mode)
        self.viewport.selectionRequested.connect(
            self._viewport_selection_requested
        )
        self.viewport.itemContextMenuRequested.connect(
            self._show_viewport_item_context_menu
        )
        self.viewport.itemTransformStarted.connect(
            self._viewport_transform_started
        )
        self.viewport.itemTransformChanged.connect(
            self._viewport_transform_changed
        )
        self.viewport.itemTransformFinished.connect(
            self._viewport_transform_finished
        )
        self.viewport.shapeDrawRequested.connect(self._shape_drawn)
        self.viewport.freehandStrokeRequested.connect(
            self._freehand_pen_drawn
        )
        self.viewport.shapeDrawModeChanged.connect(
            self._shape_draw_mode_changed
        )
        self._restore_options()

    def _build_brand_row(self) -> QWidget:
        row = QWidget()
        row.setObjectName("TitleBar")
        row.setFixedHeight(36)
        line = QHBoxLayout(row)
        line.setContentsMargins(14, 0, 14, 0)
        line.setSpacing(5)
        name = QLabel("Carve")
        name.setObjectName("AppName")
        accent = QLabel("Foundry")
        accent.setObjectName("AppAccent")
        line.addWidget(name)
        line.addWidget(accent)
        self.project_title_label = QLabel("  •  Untitled Project")
        self.project_title_label.setObjectName("Muted")
        line.addWidget(self.project_title_label)
        line.addStretch(1)

        for title, callback, tooltip in (
            ("Save", self._save_project, "Save project • Ctrl+S"),
            ("Undo", self._undo, "Undo • Ctrl+Z"),
            ("Redo", self._redo, "Redo • Ctrl+Y"),
        ):
            button = QPushButton(title)
            button.setObjectName("TitleQuickButton")
            button.setToolTip(tooltip)
            button.clicked.connect(
                lambda _checked=False, fn=callback: fn()
            )
            line.addWidget(button)
            key = title.lower()
            if key in self._history_action_buttons:
                self._history_action_buttons[key].append(button)

        self.machine_status_label = QLabel("OFFLINE")
        self.machine_status_label.setObjectName("MachineStatus")
        self.machine_status_label.setToolTip(
            "Machine connection status"
        )
        line.addWidget(self.machine_status_label)

        mode = QLabel("DESIGN + CAM")
        mode.setObjectName("AccentText")
        line.addWidget(mode)
        return row

    def _new_ui_action(
        self,
        key: str,
        text: str,
        callback,
        *,
        checkable: bool = False,
        checked: bool = False,
        tooltip: str = "",
    ) -> QAction:
        action = QAction(text, self)
        icon_label = text.replace("…", "").split(" / ", 1)[0]
        action.setIcon(_ribbon_icon(icon_label))
        action.setCheckable(checkable)
        action.setChecked(bool(checked))
        if tooltip:
            action.setToolTip(tooltip)
            action.setStatusTip(tooltip)
        action.triggered.connect(
            lambda _checked=False, fn=callback: fn()
        )
        self._ui_actions[key] = action
        return action

    def _build_command_actions(self) -> None:
        """Create one shared QAction set for menus and vertical tool rail."""

        self._ui_actions: dict[str, QAction] = {}

        specs = (
            ("new", "New", self._new_project),
            ("open", "Open", self._open_project),
            ("save", "Save", self._save_project),
            ("save_as", "Save As", self._save_project_as),
            ("import", "Import…", self._import_file),
            ("import_stl", "STL", lambda: self._import_file("STL")),
            ("import_svg", "SVG", lambda: self._import_file("SVG")),
            ("import_dxf", "DXF", lambda: self._import_file("DXF")),
            ("import_image", "Image", lambda: self._import_file("Image")),
            ("import_gcode", "G-code", lambda: self._import_file("G-code")),
            ("export_gcode", "Export G-code", self._export_gcode),
            ("undo", "Undo", self._undo),
            ("redo", "Redo", self._redo),
            ("cut", "Cut", self._cut_selected_items),
            ("copy", "Copy", self._copy_selected_items),
            ("paste", "Paste", self._paste_items),
            ("delete", "Delete", self._delete_selected_item),
            ("duplicate", "Duplicate", self._duplicate_selected_item),
            ("select_all", "Select All", self._select_all_design_items),
            ("camera", "Camera Orbit", self._activate_camera_tool),
            ("select", "Select / Marquee", self._activate_navigation_tool),
            ("rectangle", "Rectangle", self._create_rectangle),
            ("ellipse", "Ellipse", self._create_ellipse),
            ("polygon", "Polygon", self._create_polygon),
            ("line", "Line", self._create_line),
            ("text", "Text", self._create_text),
            ("pen", "Pen", self._create_pen_path),
            ("trace_image", "Trace Image", self._trace_image),
            ("align", "Align", self._align_selected_items),
            ("center", "Center", self._center_selected_items),
            ("group", "Group", self._group_selected_items),
            ("ungroup", "Ungroup", self._ungroup_selected_items),
            ("layers", "Layers", self._show_layers_popup),
            ("move_up", "Move Up", lambda: self._move_selected_item(-1)),
            ("move_down", "Move Down", lambda: self._move_selected_item(1)),
            ("stock_setup", "Stock Setup", self._focus_stock_section),
            ("fit_view", "Fit View", self._fit_view),
            ("position", "Position", lambda: self._focus_transform_section("position")),
            ("rotate", "Rotate", lambda: self._focus_transform_section("rotation")),
            ("size", "Size", lambda: self._focus_transform_section("size")),
            ("scale", "Scale", lambda: self._focus_transform_section("scale")),
            ("center_xy", "Center XY", self._center_selected_xy),
            ("top_z0", "Top to Z0", self._top_selected_to_surface),
            ("fit_stock", "Fit Stock", self._fit_selected_inside_stock),
            ("reset_transform", "Reset Transform", self._reset_selected_transform),
            ("tool_library", "Tool Library", self._show_tool_library),
            ("new_tool", "New Tool", self._new_tool),
            ("custom_profile", "Custom Profile", self._new_custom_profile_tool),
            ("calculator", "Feeds && Speeds Calculator", self._feeds_speeds_calculator),
            ("advanced_cam", "Advanced CAM…", self._toolpath_design_advanced),
            ("calculate", "Generate Toolpaths…", self._calculate_toolpath),
            ("preview", "Preview", self._preview_toolpaths),
            ("export_toolpath", "Export G-code", self._export_gcode),
            ("machine_profile", "Machine Profile", self._machine_profile),
            ("work_area", "Work Area", self._machine_work_area),
            ("origin", "Origin", self._machine_origin),
            ("postprocessor", "Postprocessor", self._postprocessor_settings_dialog),
            ("probe", "Probe", self._probe_machine),
            ("jog", "Jog", self._show_jog_controls),
            ("view_fit", "Fit View", self._fit_view),
            ("view_2d", "2D Top", self._set_2d_view),
            ("perspective", "Perspective", self._set_perspective_option),
            ("orthographic", "Orthographic", self._set_orthographic_option),
            ("isometric", "Isometric", self._set_isometric_option),
            ("view_top", "Top", lambda: self._set_standard_view_option("Top")),
            ("view_bottom", "Bottom", lambda: self._set_standard_view_option("Bottom")),
            ("view_front", "Front", lambda: self._set_standard_view_option("Front")),
            ("view_back", "Back", lambda: self._set_standard_view_option("Back")),
            ("view_left", "Left", lambda: self._set_standard_view_option("Left")),
            ("view_right", "Right", lambda: self._set_standard_view_option("Right")),
            ("reset_ui", "Reset UI", self._reset_interface_options),
        )
        for key, text, callback in specs:
            self._new_ui_action(key, text, callback)

        for operation, title in (
            ("profile", "Profile"),
            ("silhouette", "Silhouette"),
            ("pocket", "Pocket"),
            ("surface", "Surface"),
            ("vcarve", "V-Carve"),
            ("engrave", "Engrave"),
            ("drill", "Drill Features"),
            ("center_drill", "Center Drill"),
            ("rough", "Rough"),
            ("finish", "Finish"),
            ("height_map", "Height Map"),
            ("rest", "Rest"),
            ("waterline", "Waterline"),
        ):
            self._new_ui_action(
                f"cam_{operation}",
                title,
                lambda op=operation: self._select_cam_operation(op),
                checkable=True,
                checked=operation == self._active_cam_operation,
            )

        self._new_ui_action(
            "tabs",
            "Tabs",
            self._toggle_tabs_operation,
            checkable=True,
            checked=self._tabs_enabled,
        )
        self._new_ui_action(
            "simulate",
            "Simulate",
            self._simulate_toolpaths,
            checkable=True,
        )
        self._new_ui_action(
            "machine_connect",
            "Connect",
            self._connect_machine,
            checkable=True,
        )
        for key, text, callback, checked in (
            ("stock", "Stock", self._toggle_stock, True),
            ("grid", "Grid", self._toggle_grid, True),
            ("rulers", "Rulers", self._toggle_rulers, True),
            ("toolpaths", "Toolpaths", self._toggle_toolpaths_view, True),
            ("rapids", "Rapids", self._toggle_rapids_view, False),
            (
                "inspector",
                "Inspector",
                self._toggle_properties_panel_option,
                True,
            ),
            (
                "status_bar",
                "Status Bar",
                self._toggle_status_bar_option,
                True,
            ),
            (
                "view_controls",
                "View Controls",
                self._toggle_view_controls_option,
                True,
            ),
            (
                "reverse_horizontal",
                "Reverse Horizontal",
                self._toggle_reverse_horizontal_option,
                False,
            ),
            (
                "invert_vertical",
                "Invert Vertical",
                self._toggle_invert_vertical_option,
                False,
            ),
        ):
            self._new_ui_action(
                key,
                text,
                callback,
                checkable=True,
                checked=checked,
            )

        # Replace the hidden-ribbon state handles with the user-visible actions.
        self._camera_tool_button = self._ui_actions["camera"]
        self._camera_tool_button.setCheckable(True)
        self._camera_tool_button.setChecked(True)
        self._navigation_tool_button = self._ui_actions["select"]
        self._navigation_tool_button.setCheckable(True)
        self._navigation_tool_button.setChecked(False)
        self._shape_tool_buttons = {
            name: self._ui_actions[name]
            for name in (
                "rectangle",
                "ellipse",
                "polygon",
                "line",
                "text",
                "pen",
            )
        }
        for action in self._shape_tool_buttons.values():
            action.setCheckable(True)

        self._cam_operation_buttons = {
            operation: self._ui_actions[f"cam_{operation}"]
            for operation in (
                "profile",
                "silhouette",
                "pocket",
                "surface",
                "vcarve",
                "engrave",
                "drill",
                "center_drill",
                "rough",
                "finish",
                "height_map",
                "rest",
                "waterline",
            )
        }
        self._tabs_button = self._ui_actions["tabs"]
        self._simulation_button = self._ui_actions["simulate"]
        self._machine_connect_button = self._ui_actions["machine_connect"]
        self._toolpaths_view_button = self._ui_actions["toolpaths"]
        self._rapids_view_button = self._ui_actions["rapids"]
        self._calculate_button = self._ui_actions["calculate"]

        self._history_action_buttons["undo"].append(self._ui_actions["undo"])
        self._history_action_buttons["redo"].append(self._ui_actions["redo"])
        for name in (
            "cut",
            "copy",
            "paste",
            "delete",
            "align",
            "center",
            "group",
            "ungroup",
            "duplicate",
            "move_up",
            "move_down",
        ):
            self._selection_action_buttons[name] = self._ui_actions[name]

        self._model_selection_buttons.extend(
            self._ui_actions[name]
            for name in (
                "position",
                "rotate",
                "size",
                "scale",
                "center_xy",
                "top_z0",
                "fit_stock",
                "reset_transform",
            )
        )
        self._toolpath_output_buttons.extend(
            self._ui_actions[name]
            for name in (
                "preview",
                "simulate",
                "export_toolpath",
                "toolpaths",
                "rapids",
            )
        )
        self._option_buttons.update(
            {
                name: self._ui_actions[name]
                for name in (
                    "stock",
                    "grid",
                    "rulers",
                    "inspector",
                    "status_bar",
                    "view_controls",
                    "reverse_horizontal",
                    "invert_vertical",
                )
            }
        )
        self._option_buttons["properties_panel"] = self._ui_actions["inspector"]

    def _add_menu_actions(
        self,
        menu: QMenu,
        keys: tuple[str, ...],
    ) -> None:
        for key in keys:
            menu.addAction(self._ui_actions[key])

    def _add_cam_choice_menu(
        self,
        parent: QMenu,
        title: str,
        key: str,
        values: tuple[str, ...],
        current: str,
    ) -> QMenu:
        submenu = parent.addMenu(title)
        self._cam_menu_choice_actions.setdefault(key, [])
        for value in values:
            action = QAction(value, submenu)
            action.setCheckable(True)
            action.setChecked(value == current)
            action.triggered.connect(
                lambda _checked=False, setting=key, choice=value: (
                    self._set_cam_design_option(setting, choice)
                )
            )
            submenu.addAction(action)
            self._cam_menu_choice_actions[key].append(action)
        return submenu

    def _build_main_menu_bar(self) -> QMenuBar:
        """Build the normal Photopea-style dropdown command bar."""

        bar = QMenuBar()
        bar.setObjectName("MainMenuBar")
        self._cam_menu_choice_actions: dict[str, list[QAction]] = {}
        self._cutter_menu_actions: list[QAction] = []

        file_menu = bar.addMenu("File")
        self._add_menu_actions(file_menu, ("new", "open", "save", "save_as"))
        file_menu.addSeparator()
        import_menu = file_menu.addMenu("Import")
        self._add_menu_actions(
            import_menu,
            (
                "import",
                "import_stl",
                "import_svg",
                "import_dxf",
                "import_image",
                "import_gcode",
            ),
        )
        file_menu.addSeparator()
        file_menu.addAction(self._ui_actions["export_gcode"])

        edit_menu = bar.addMenu("Edit")
        self._add_menu_actions(edit_menu, ("undo", "redo"))
        edit_menu.addSeparator()
        self._add_menu_actions(
            edit_menu,
            (
                "cut",
                "copy",
                "paste",
                "duplicate",
                "delete",
                "select_all",
            ),
        )

        design_menu = bar.addMenu("Design")
        draw_menu = design_menu.addMenu("Draw")
        self._add_menu_actions(
            draw_menu,
            ("select", "rectangle", "ellipse", "polygon", "line", "text"),
        )
        vector_menu = design_menu.addMenu("Vector")
        self._add_menu_actions(vector_menu, ("pen", "trace_image"))
        arrange_menu = design_menu.addMenu("Arrange")
        self._add_menu_actions(
            arrange_menu,
            ("align", "center", "group", "ungroup", "duplicate"),
        )
        design_menu.addSeparator()
        self._add_menu_actions(design_menu, ("layers", "move_up", "move_down"))

        model_menu = bar.addMenu("Model")
        self._add_menu_actions(model_menu, ("stock_setup", "fit_view"))
        transform_menu = model_menu.addMenu("Transform")
        self._add_menu_actions(
            transform_menu,
            ("position", "rotate", "size", "scale"),
        )
        placement_menu = model_menu.addMenu("Placement")
        self._add_menu_actions(
            placement_menu,
            ("center_xy", "top_z0", "fit_stock", "reset_transform"),
        )

        toolpaths_menu = bar.addMenu("Toolpaths")
        ops_2d = toolpaths_menu.addMenu("2D / 2.5D")
        self._add_menu_actions(
            ops_2d,
            (
                "cam_profile",
                "cam_silhouette",
                "cam_pocket",
                "cam_surface",
                "cam_vcarve",
                "cam_engrave",
                "cam_drill",
                "cam_center_drill",
                "tabs",
            ),
        )
        ops_3d = toolpaths_menu.addMenu("3D")
        self._add_menu_actions(
            ops_3d,
            (
                "cam_rough",
                "cam_finish",
                "cam_height_map",
                "cam_rest",
                "cam_waterline",
            ),
        )

        cutter_menu = toolpaths_menu.addMenu("Cutter")
        for index in range(self.tool_combo.count()):
            cutter = self.tool_combo.itemData(index)
            label = getattr(cutter, "name", self.tool_combo.itemText(index))
            action = QAction(str(label), cutter_menu)
            action.setCheckable(True)
            action.setChecked(index == self.tool_combo.currentIndex())
            action.triggered.connect(
                lambda _checked=False, idx=index: self.tool_combo.setCurrentIndex(idx)
            )
            cutter_menu.addAction(action)
            self._cutter_menu_actions.append(action)
        cutter_menu.addSeparator()
        self._add_menu_actions(
            cutter_menu,
            ("tool_library", "new_tool", "custom_profile", "calculator"),
        )

        path_design = toolpaths_menu.addMenu("Path Design")
        self._add_cam_choice_menu(
            path_design,
            "Cut Type",
            "cut_type",
            ("Auto", "Pocket", "On Path", "Outside", "Inside"),
            self._cam_cut_type,
        )
        self._add_cam_choice_menu(
            path_design,
            "3D Style",
            "3d_cut_style",
            (
                "Model Boundary Relief",
                "Rectangle Relief",
                "Full Depth Cutout",
            ),
            self._cam_3d_cut_style,
        )
        self._add_cam_choice_menu(
            path_design,
            "Direction",
            "direction",
            (
                "Smart Serpentine",
                "Offset",
                "Raster X",
                "Raster Y",
                "Raster 45°",
                "Raster 135°",
            ),
            self._cam_direction,
        )
        detail_menu = path_design.addMenu("Detail")
        for detail in (0, 25, 50, 75, 100):
            action = QAction(f"{detail}%", detail_menu)
            action.triggered.connect(
                lambda _checked=False, value=detail: self._set_cam_detail(value)
            )
            detail_menu.addAction(action)
        path_design.addAction(self._ui_actions["advanced_cam"])

        motion = toolpaths_menu.addMenu("Motion")
        self._add_cam_choice_menu(
            motion,
            "Entry",
            "entry",
            ("Plunge", "Ramp 5°", "Ramp 20°", "Custom Ramp"),
            self._cam_entry,
        )
        self._add_cam_choice_menu(
            motion,
            "Milling",
            "milling",
            ("Default", "Climb (CCW)", "Conventional (CW)"),
            self._cam_milling,
        )
        self._add_cam_choice_menu(
            motion,
            "Linking",
            "linking",
            ("Smart Min-Lift", "Local Lift", "Full Retract"),
            self._cam_linking,
        )

        toolpaths_menu.addSeparator()
        self._add_menu_actions(
            toolpaths_menu,
            ("calculate", "preview", "simulate", "export_toolpath"),
        )

        machine_menu = bar.addMenu("Machine")
        self._add_menu_actions(
            machine_menu,
            ("machine_profile", "work_area", "origin", "postprocessor"),
        )
        machine_menu.addSeparator()
        self._add_menu_actions(
            machine_menu,
            ("machine_connect", "probe", "jog"),
        )

        view_menu = bar.addMenu("View")
        display_menu = view_menu.addMenu("Display")
        self._add_menu_actions(
            display_menu,
            ("stock", "grid", "rulers", "toolpaths", "rapids"),
        )
        camera_menu = view_menu.addMenu("Camera")
        self._add_menu_actions(
            camera_menu,
            (
                "camera",
                "view_fit",
                "view_2d",
                "perspective",
                "orthographic",
                "isometric",
            ),
        )
        fixed_menu = view_menu.addMenu("Fixed View")
        self._add_menu_actions(
            fixed_menu,
            (
                "view_top",
                "view_bottom",
                "view_front",
                "view_back",
                "view_left",
                "view_right",
            ),
        )
        workspace_menu = view_menu.addMenu("Workspace")
        self._add_menu_actions(
            workspace_menu,
            ("layers", "inspector", "status_bar", "view_controls", "reset_ui"),
        )
        navigation_menu = view_menu.addMenu("Navigation")
        self._add_menu_actions(
            navigation_menu,
            ("reverse_horizontal", "invert_vertical"),
        )
        return bar

    def _populate_ribbon(self) -> None:
        def add_cam_selector(
            group,
            key: str,
            title: str,
            values: tuple[str, ...],
            current: str,
            tooltip: str,
            *,
            minimum_width: int = 108,
        ):
            combo = group.add_selector(
                title,
                values,
                current,
                lambda value, setting=key: self._set_cam_design_option(
                    setting,
                    value,
                ),
                tooltip=tooltip,
                minimum_width=minimum_width,
            )
            self._register_cam_selector(key, combo)
            return combo

        # FILE: project lifecycle and bringing source material into the job.
        file_page = self.ribbon.add_page("File")
        project = file_page.add_group("Project")
        project.add_button("New", self._new_project)
        project.add_button("Open", self._open_project)
        project.add_button("Save", self._save_project, primary=True)
        project.add_button("Save As", self._save_project_as)

        import_group = file_page.add_group("Import")
        import_group.add_button("Import", self._import_file, primary=True)
        import_group.add_button("STL", lambda: self._import_file("STL"))
        import_group.add_button("SVG", lambda: self._import_file("SVG"))
        import_group.add_button("DXF", lambda: self._import_file("DXF"))
        import_group.add_button("Image", lambda: self._import_file("Image"))
        import_group.add_button("G-code", lambda: self._import_file("G-code"))

        output = file_page.add_group("Output")
        file_export = output.add_button("Export G-code", self._export_gcode)
        self._toolpath_output_buttons.append(file_export)

        # DESIGN: geometry creation, editing, arrangement, and object management.
        design = self.ribbon.add_page("Design")
        edit = design.add_group("Edit")
        undo_button = edit.add_button("Undo", self._undo)
        redo_button = edit.add_button("Redo", self._redo)
        self._history_action_buttons["undo"].append(undo_button)
        self._history_action_buttons["redo"].append(redo_button)
        self._selection_action_buttons["cut"] = edit.add_button(
            "Cut",
            self._cut_selected_items,
        )
        self._selection_action_buttons["copy"] = edit.add_button(
            "Copy",
            self._copy_selected_items,
        )
        self._selection_action_buttons["paste"] = edit.add_button(
            "Paste",
            self._paste_items,
        )
        self._selection_action_buttons["delete"] = edit.add_button(
            "Delete",
            self._delete_selected_item,
        )

        shapes = design.add_group("Draw")
        self._navigation_tool_button = shapes.add_button(
            "Select",
            self._activate_navigation_tool,
            primary=True,
        )
        self._navigation_tool_button.setCheckable(True)
        self._navigation_tool_button.setChecked(True)
        self._navigation_tool_button.setToolTip(
            "Select / Navigate: return to normal object selection and viewport "
            "navigation. Esc also exits an active drawing tool."
        )
        shape_actions = (
            ("rectangle", "Rectangle", self._create_rectangle),
            ("ellipse", "Ellipse", self._create_ellipse),
            ("polygon", "Polygon", self._create_polygon),
            ("line", "Line", self._create_line),
            ("text", "Text", self._create_text),
        )
        for tool, title, callback in shape_actions:
            button = shapes.add_button(title, callback)
            button.setCheckable(True)
            button.setToolTip(
                f"{title}: drag directly on the stock to draw. "
                "Hold Shift to constrain. Alt+drag temporarily orbits. "
                "Press Esc or Select to exit the tool."
            )
            self._shape_tool_buttons[tool] = button

        vectors = design.add_group("Vector")
        vectors.add_button("Pen", self._create_pen_path)
        vectors.add_button("Trace Image", self._trace_image)

        arrange = design.add_group("Arrange")
        self._selection_action_buttons["align"] = arrange.add_button(
            "Align",
            self._align_selected_items,
        )
        self._selection_action_buttons["center"] = arrange.add_button(
            "Center",
            self._center_selected_items,
        )
        self._selection_action_buttons["group"] = arrange.add_button(
            "Group",
            self._group_selected_items,
        )
        self._selection_action_buttons["ungroup"] = arrange.add_button(
            "Ungroup",
            self._ungroup_selected_items,
        )
        self._selection_action_buttons["duplicate"] = arrange.add_button(
            "Duplicate",
            self._duplicate_selected_item,
        )

        objects = design.add_group("Objects")
        objects.add_button("Layers", self._show_layers_popup, primary=True)
        self._selection_action_buttons["move_up"] = objects.add_button(
            "Move Up",
            lambda: self._move_selected_item(-1),
        )
        self._selection_action_buttons["move_down"] = objects.add_button(
            "Move Down",
            lambda: self._move_selected_item(1),
        )

        # MODEL: stock-relative placement and object transforms.
        model = self.ribbon.add_page("Model")
        stock = model.add_group("Stock")
        stock.add_button("Stock Setup", self._focus_stock_section, primary=True)
        stock.add_button("Fit View", self._fit_view)

        transform = model.add_group("Transform")
        for title, section, primary in (
            ("Position", "position", False),
            ("Rotate", "rotation", False),
            ("Size", "size", True),
            ("Scale", "scale", False),
        ):
            button = transform.add_button(
                title,
                lambda name=section: self._focus_transform_section(name),
                primary=primary,
            )
            self._model_selection_buttons.append(button)

        placement = model.add_group("Placement")
        for title, callback in (
            ("Center XY", self._center_selected_xy),
            ("Top to Z0", self._top_selected_to_surface),
            ("Fit Stock", self._fit_selected_inside_stock),
            ("Reset", self._reset_selected_transform),
        ):
            button = placement.add_button(title, callback)
            self._model_selection_buttons.append(button)

        # TOOLPATHS: all CAM work lives in one workflow tab.
        toolpaths = self.ribbon.add_page("Toolpaths")
        operations_2d = toolpaths.add_group("2D / 2.5D")
        self._cam_operation_buttons: dict[str, object] = {}
        for operation, title in (
            ("profile", "Profile"),
            ("silhouette", "Silhouette"),
            ("pocket", "Pocket"),
            ("surface", "Surface"),
            ("vcarve", "V-Carve"),
            ("engrave", "Engrave"),
            ("drill", "Drill Features"),
            ("center_drill", "Center Drill"),
        ):
            button = operations_2d.add_button(
                title,
                lambda op=operation: self._select_cam_operation(op),
            )
            button.setCheckable(True)
            self._cam_operation_buttons[operation] = button
        self._tabs_button = operations_2d.add_button(
            "Tabs",
            self._toggle_tabs_operation,
        )
        self._tabs_button.setCheckable(True)
        self._tabs_button.setChecked(self._tabs_enabled)

        operations_3d = toolpaths.add_group("3D")
        for operation, title in (
            ("rough", "Rough"),
            ("finish", "Finish"),
            ("height_map", "Height Map"),
            ("rest", "Rest"),
            ("waterline", "Waterline"),
        ):
            button = operations_3d.add_button(
                title,
                lambda op=operation: self._select_cam_operation(op),
                primary=operation == "finish",
            )
            button.setCheckable(True)
            self._cam_operation_buttons[operation] = button

        active_button = self._cam_operation_buttons.get(
            self._active_cam_operation
        )
        if active_button is not None:
            active_button.setChecked(True)

        cutters = toolpaths.add_group("Cutter")
        all_cutters = self._all_tools()
        cutter_names = [cutter.name for cutter in all_cutters]
        preferred_cutter = str(
            self._settings.value(
                "tools/selected_name",
                cutter_names[0] if cutter_names else "",
            )
        )
        self.tool_combo = cutters.add_selector(
            "Selected Cutter",
            cutter_names,
            preferred_cutter,
            tooltip=(
                "The active cutter is used for toolpath generation and "
                "cutter-profile compensation."
            ),
            minimum_width=150,
        )
        for index, cutter in enumerate(all_cutters):
            self.tool_combo.setItemData(index, cutter)
        self.tool_combo.currentIndexChanged.connect(
            self._active_cutter_changed
        )
        cutters.add_button("Library", self._show_tool_library)
        cutters.add_button("New Tool", self._new_tool)
        cutters.add_button("Custom Profile", self._new_custom_profile_tool)
        cutters.add_button("Calculator", self._feeds_speeds_calculator)

        path_design = toolpaths.add_group("Path Design")
        add_cam_selector(
            path_design,
            "cut_type",
            "Cut Type",
            ("Auto", "Pocket", "On Path", "Outside", "Inside"),
            self._cam_cut_type,
            (
                "Choose where the cutter runs relative to 2D geometry. "
                "Auto follows the selected operation."
            ),
            minimum_width=98,
        )
        add_cam_selector(
            path_design,
            "3d_cut_style",
            "3D Style",
            (
                "Model Boundary Relief",
                "Rectangle Relief",
                "Full Depth Cutout",
            ),
            self._cam_3d_cut_style,
            (
                "Controls the area surrounding a 3D model and whether a "
                "final outside cutout operation is added."
            ),
            minimum_width=140,
        )
        add_cam_selector(
            path_design,
            "direction",
            "Direction",
            (
                "Smart Serpentine",
                "Offset",
                "Raster X",
                "Raster Y",
                "Raster 45°",
                "Raster 135°",
            ),
            self._cam_direction,
            (
                "Smart Serpentine minimizes row count. Explicit raster "
                "directions can be aligned to grain or surface features."
            ),
            minimum_width=126,
        )
        detail_slider = path_design.add_slider(
            "Detail",
            0,
            100,
            self._cam_detail,
            self._set_cam_detail,
            tooltip=(
                "Raster-line density for the selected cutter. More Detail "
                "reduces stepover and increases raster lines."
            ),
            minimum_width=215,
            low_label="Faster",
            high_label="Detail",
        )
        self._register_cam_detail_slider(detail_slider)

        motion = toolpaths.add_group("Motion")
        add_cam_selector(
            motion,
            "entry",
            "Entry",
            ("Plunge", "Ramp 5°", "Ramp 20°", "Custom Ramp"),
            self._cam_entry,
            "Choose vertical plunge or a ramped entry into material.",
            minimum_width=98,
        )
        add_cam_selector(
            motion,
            "milling",
            "Milling",
            ("Default", "Climb (CCW)", "Conventional (CW)"),
            self._cam_milling,
            "Controls milling direction for outlines and offset fills.",
            minimum_width=116,
        )
        add_cam_selector(
            motion,
            "linking",
            "Linking",
            ("Smart Min-Lift", "Local Lift", "Full Retract"),
            self._cam_linking,
            (
                "Smart Min-Lift keeps safe serpentine links cutting, uses "
                "small local lifts where needed, and retracts fully only "
                "across disconnected areas."
            ),
            minimum_width=112,
        )
        motion.add_button("Advanced", self._toolpath_design_advanced)

        generate = toolpaths.add_group("Generate")
        self._calculate_button = generate.add_button(
            "Generate Toolpaths…",
            self._calculate_toolpath,
            primary=True,
        )
        preview_button = generate.add_button(
            "Preview",
            self._preview_toolpaths,
        )
        self._toolpath_output_buttons.append(preview_button)
        self._simulation_button = generate.add_button(
            "Simulate",
            self._simulate_toolpaths,
        )
        self._simulation_button.setCheckable(True)
        self._toolpath_output_buttons.append(self._simulation_button)
        toolpath_export = generate.add_button(
            "Export G-code",
            self._export_gcode,
        )
        self._toolpath_output_buttons.append(toolpath_export)

        # MACHINE: physical machine configuration and control only.
        machine = self.ribbon.add_page("Machine")
        setup = machine.add_group("Setup")
        setup.add_button("Machine Profile", self._machine_profile)
        setup.add_button("Work Area", self._machine_work_area)
        setup.add_button("Origin", self._machine_origin)
        setup.add_button("Postprocessor", self._postprocessor_settings_dialog)
        control = machine.add_group("Control")
        self._machine_connect_button = control.add_button(
            "Connect",
            self._connect_machine,
            primary=True,
        )
        self._machine_connect_button.setCheckable(True)
        control.add_button("Probe", self._probe_machine)
        control.add_button("Jog", self._show_jog_controls)

        # VIEW: canvas appearance, camera, and workspace chrome.
        view = self.ribbon.add_page("View")
        display = view.add_group("Display")
        stock_view = display.add_button("Stock", self._toggle_stock)
        stock_view.setCheckable(True)
        self._option_buttons["stock"] = stock_view
        grid_view = display.add_button("Grid", self._toggle_grid)
        grid_view.setCheckable(True)
        self._option_buttons["grid"] = grid_view
        rulers_view = display.add_button("Rulers", self._toggle_rulers)
        rulers_view.setCheckable(True)
        self._option_buttons["rulers"] = rulers_view
        self._toolpaths_view_button = display.add_button(
            "Toolpaths",
            self._toggle_toolpaths_view,
        )
        self._toolpaths_view_button.setCheckable(True)
        self._toolpaths_view_button.setChecked(True)
        self._toolpath_output_buttons.append(self._toolpaths_view_button)
        self._rapids_view_button = display.add_button(
            "Rapids",
            self._toggle_rapids_view,
        )
        self._rapids_view_button.setCheckable(True)
        self._toolpath_output_buttons.append(self._rapids_view_button)

        camera = view.add_group("Camera")
        camera.add_button("Fit View", self._fit_view, primary=True)
        camera.add_button("2D Top", self._set_2d_view)
        camera.add_button("Perspective", self._set_perspective_option)
        camera.add_button("Orthographic", self._set_orthographic_option)
        camera.add_button("Isometric", self._set_isometric_option)

        fixed_views = view.add_group("Fixed View")
        for title in ("Top", "Bottom", "Front", "Back", "Left", "Right"):
            fixed_views.add_button(
                title,
                lambda name=title: self._set_standard_view_option(name),
            )

        workspace = view.add_group("Workspace")
        workspace.add_button("Layers", self._show_layers_popup)
        inspector = workspace.add_button(
            "Inspector",
            self._toggle_properties_panel_option,
        )
        inspector.setCheckable(True)
        self._option_buttons["properties_panel"] = inspector
        status = workspace.add_button(
            "Status Bar",
            self._toggle_status_bar_option,
        )
        status.setCheckable(True)
        self._option_buttons["status_bar"] = status
        controls = workspace.add_button(
            "View Controls",
            self._toggle_view_controls_option,
        )
        controls.setCheckable(True)
        self._option_buttons["view_controls"] = controls
        workspace.add_button("Reset UI", self._reset_interface_options)

        navigation = view.add_group("Navigation")
        reverse_horizontal = navigation.add_button(
            "Reverse\nHorizontal",
            self._toggle_reverse_horizontal_option,
        )
        reverse_horizontal.setCheckable(True)
        self._option_buttons["reverse_horizontal"] = reverse_horizontal
        invert_vertical = navigation.add_button(
            "Invert\nVertical",
            self._toggle_invert_vertical_option,
        )
        invert_vertical.setCheckable(True)
        self._option_buttons["invert_vertical"] = invert_vertical

        self._sync_cam_control_relevance()

        preferred_tab = str(
            self._settings.value("interface/ribbon_tab", "Design")
        )
        selected_index = self.ribbon.indexOf(design)
        for index in range(self.ribbon.count()):
            if self.ribbon.tabText(index) == preferred_tab:
                selected_index = index
                break
        self.ribbon.setCurrentIndex(selected_index)

    def _ribbon_tab_changed(self, index: int) -> None:
        if not 0 <= index < self.ribbon.count():
            return
        self._settings.setValue(
            "interface/ribbon_tab",
            self.ribbon.tabText(index),
        )
        self._settings.sync()

    def _add_menu_widget(
        self,
        menu: QMenu,
        title: str,
        widget: QWidget,
    ) -> QWidgetAction:
        container = QWidget()
        container.setObjectName("ToolRailMenuWidget")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        label = QLabel(title)
        label.setObjectName("ToolRailMenuLabel")
        layout.addWidget(label)
        widget.setMinimumWidth(max(170, widget.minimumWidth()))
        layout.addWidget(widget)

        action = QWidgetAction(menu)
        action.setDefaultWidget(container)
        menu.addAction(action)
        return action

    def _build_tool_rail(self) -> ToolRail:
        """Build the complete Photopea-style vertical command/tool rail."""

        rail = ToolRail(self)

        rail.add_action_tool(
            "camera",
            self._ui_actions["camera"],
            tooltip=(
                "Camera / Arcball\n"
                "Left-drag rotates the view. Middle/right-drag pans. "
                "Mouse wheel zooms. This is the default viewport tool."
            ),
        )
        rail.add_action_tool(
            "select",
            self._ui_actions["select"],
            tooltip=(
                "Select / Marquee (V)\n"
                "Click selects one object. Ctrl-click toggles, Shift-click adds, "
                "drag empty space box-selects, Ctrl+A selects all, Alt-drag orbits."
            ),
        )

        rail.add_flyout(
            "shapes",
            "Rectangle",
            (
                (
                    "rectangle",
                    "Rectangle",
                    self._create_rectangle,
                    "Rectangle tool — drag on the stock to draw.",
                ),
                (
                    "ellipse",
                    "Ellipse",
                    self._create_ellipse,
                    "Ellipse tool — drag on the stock to draw.",
                ),
                (
                    "polygon",
                    "Polygon",
                    self._create_polygon,
                    "Polygon tool — sides are set in the tool options bar.",
                ),
            ),
            tooltip="Shape tools — click arrow to choose Rectangle, Ellipse, or Polygon.",
            checkable=True,
        )
        rail.add_action_tool(
            "line",
            self._ui_actions["line"],
            tooltip="Line tool — drag to draw. Shift constrains to 45° increments.",
        )
        rail.add_action_tool(
            "text",
            self._ui_actions["text"],
            tooltip="Text tool — drag a text box; typography appears in Inspector.",
        )

        vector_menu = QMenu(rail)
        self._add_menu_actions(vector_menu, ("pen", "trace_image"))
        rail.add_menu(
            "vector",
            "Pen",
            vector_menu,
            tooltip=(
                "Vector tools — Pen draws freehand directly in the viewport; "
                "Trace Image converts artwork to vector-like geometry."
            ),
            primary_callback=self._create_pen_path,
            checkable=True,
        )

        rail.add_separator()

        file_menu = QMenu(rail)
        self._add_menu_actions(file_menu, ("new", "open", "save", "save_as"))
        file_menu.addSeparator()
        import_menu = file_menu.addMenu("Import")
        self._add_menu_actions(
            import_menu,
            (
                "import",
                "import_stl",
                "import_svg",
                "import_dxf",
                "import_image",
                "import_gcode",
            ),
        )
        file_menu.addSeparator()
        file_menu.addAction(self._ui_actions["export_gcode"])
        rail.add_menu(
            "file",
            "Open",
            file_menu,
            tooltip="Project, import, save, and G-code output commands.",
            primary_callback=self._open_project,
        )

        edit_menu = QMenu(rail)
        self._add_menu_actions(
            edit_menu,
            (
                "undo",
                "redo",
                "cut",
                "copy",
                "paste",
                "duplicate",
                "delete",
                "select_all",
            ),
        )
        rail.add_menu(
            "edit",
            "Cut",
            edit_menu,
            tooltip="Edit commands — undo/redo, clipboard, duplicate, delete, select all.",
        )

        arrange_menu = QMenu(rail)
        self._add_menu_actions(
            arrange_menu,
            (
                "align",
                "center",
                "group",
                "ungroup",
                "duplicate",
                "move_up",
                "move_down",
                "layers",
            ),
        )
        rail.add_menu(
            "arrange",
            "Align",
            arrange_menu,
            tooltip="Arrange, group, order, and Layers commands.",
        )

        model_menu = QMenu(rail)
        self._add_menu_actions(model_menu, ("stock_setup", "fit_view"))
        transform_menu = model_menu.addMenu("Transform")
        self._add_menu_actions(
            transform_menu,
            ("position", "rotate", "size", "scale"),
        )
        placement_menu = model_menu.addMenu("Placement")
        self._add_menu_actions(
            placement_menu,
            ("center_xy", "top_z0", "fit_stock", "reset_transform"),
        )
        rail.add_menu(
            "model",
            "Position",
            model_menu,
            tooltip="Stock, transform, size, placement, and reset commands.",
        )

        cam_menu = QMenu(rail)
        ops_2d = cam_menu.addMenu("2D / 2.5D")
        self._add_menu_actions(
            ops_2d,
            (
                "cam_profile",
                "cam_silhouette",
                "cam_pocket",
                "cam_surface",
                "cam_vcarve",
                "cam_engrave",
                "cam_drill",
                "cam_center_drill",
                "tabs",
            ),
        )
        ops_3d = cam_menu.addMenu("3D")
        self._add_menu_actions(
            ops_3d,
            (
                "cam_rough",
                "cam_finish",
                "cam_height_map",
                "cam_rest",
                "cam_waterline",
            ),
        )
        cam_menu.addSeparator()

        for title, key in (
            ("Cut Type", "cut_type"),
            ("3D Style", "3d_cut_style"),
            ("Direction", "direction"),
        ):
            widgets = self._cam_selector_widgets.get(key, [])
            if widgets:
                self._add_menu_widget(cam_menu, title, widgets[0])

        if self._cam_detail_widgets:
            self._add_menu_widget(
                cam_menu,
                "Detail",
                self._cam_detail_widgets[0],
            )

        motion_menu = cam_menu.addMenu("Motion")
        for title, key in (
            ("Entry", "entry"),
            ("Milling", "milling"),
            ("Linking", "linking"),
        ):
            widgets = self._cam_selector_widgets.get(key, [])
            if widgets:
                self._add_menu_widget(motion_menu, title, widgets[0])

        cam_menu.addSeparator()
        self._add_menu_actions(
            cam_menu,
            ("advanced_cam", "calculate", "preview", "simulate", "export_toolpath"),
        )
        rail.add_menu(
            "cam",
            "V-Carve",
            cam_menu,
            tooltip="All CAM operations, path design, motion, Detail, and generation.",
            primary_callback=lambda: self._select_cam_operation(
                self._active_cam_operation
            ),
        )

        cutter_menu = QMenu(rail)
        self._add_menu_widget(
            cutter_menu,
            "Selected Cutter",
            self.tool_combo,
        )
        cutter_menu.addSeparator()
        self._add_menu_actions(
            cutter_menu,
            ("tool_library", "new_tool", "custom_profile", "calculator"),
        )
        rail.add_menu(
            "cutter",
            "Library",
            cutter_menu,
            tooltip="Cutter selector, tool library, custom tools, and feeds/speeds.",
        )

        machine_menu = QMenu(rail)
        self._add_menu_actions(
            machine_menu,
            ("machine_profile", "work_area", "origin", "postprocessor"),
        )
        machine_menu.addSeparator()
        self._add_menu_actions(
            machine_menu,
            ("machine_connect", "probe", "jog"),
        )
        rail.add_menu(
            "machine",
            "Machine Profile",
            machine_menu,
            tooltip="Machine setup, connection, probe, and jog controls.",
        )

        view_menu = QMenu(rail)
        display_menu = view_menu.addMenu("Display")
        self._add_menu_actions(
            display_menu,
            ("stock", "grid", "rulers", "toolpaths", "rapids"),
        )
        camera_menu = view_menu.addMenu("Camera")
        self._add_menu_actions(
            camera_menu,
            ("view_fit", "view_2d", "perspective", "orthographic", "isometric"),
        )
        fixed_menu = view_menu.addMenu("Fixed View")
        self._add_menu_actions(
            fixed_menu,
            (
                "view_top",
                "view_bottom",
                "view_front",
                "view_back",
                "view_left",
                "view_right",
            ),
        )
        workspace_menu = view_menu.addMenu("Workspace")
        self._add_menu_actions(
            workspace_menu,
            ("layers", "inspector", "status_bar", "view_controls", "reset_ui"),
        )
        navigation_menu = view_menu.addMenu("Navigation")
        self._add_menu_actions(
            navigation_menu,
            ("reverse_horizontal", "invert_vertical"),
        )
        rail.add_menu(
            "view",
            "Perspective",
            view_menu,
            tooltip="Display, camera, fixed views, workspace, and navigation options.",
        )

        rail.add_stretch()
        rail.set_active_tool("camera")
        return rail

    def _build_workspace(self) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.tool_rail = self._build_tool_rail()
        layout.addWidget(self.tool_rail)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.workspace_splitter = splitter

        # Keep the existing QListWidget-based project selection model, but move
        # it out of the permanent layout.  It now lives in an on-demand popup.
        self.layers_popup = LayersPopup(
            self,
            move_up=lambda: self._move_selected_item(-1),
            move_down=lambda: self._move_selected_item(1),
            duplicate=self._duplicate_selected_item,
            delete=self._delete_selected_item,
        )
        self.project_list = self.layers_popup.list_widget

        canvas = QFrame()
        canvas.setObjectName("CanvasFrame")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)

        canvas_bar = QWidget()
        canvas_bar.setObjectName("ViewportBar")
        canvas_bar_layout = QHBoxLayout(canvas_bar)
        canvas_bar_layout.setContentsMargins(7, 4, 7, 4)
        canvas_bar_layout.setSpacing(5)

        canvas_bar_layout.addWidget(QLabel("Object"))
        self.object_selector = QComboBox()
        self.object_selector.setObjectName("ObjectSelector")
        self.object_selector.setMinimumWidth(190)
        self.object_selector.setMaximumWidth(360)
        self.object_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.object_selector.setMinimumContentsLength(22)
        self.object_selector.setToolTip(
            "Select Stock or a design object without opening the Layers manager."
        )
        self.object_selector.currentIndexChanged.connect(
            self._object_selector_changed
        )
        canvas_bar_layout.addWidget(self.object_selector)

        self.layers_button = QPushButton("Layers")
        self.layers_button.setToolTip(
            "Open the object/layer manager for visibility, multi-select, and ordering."
        )
        self.layers_button.clicked.connect(self._show_layers_popup)
        canvas_bar_layout.addWidget(self.layers_button)
        canvas_bar_layout.addStretch(1)

        self.cam_status_label = QLabel("CAM: NONE")
        self.cam_status_label.setObjectName("CamStatus")
        self.cam_status_label.setProperty("state", "none")
        self.cam_status_label.setToolTip(
            "No calculated toolpath for the current job."
        )
        canvas_bar_layout.addWidget(self.cam_status_label)

        self.generate_toolpaths_button = QPushButton("Generate Toolpaths")
        self.generate_toolpaths_button.setObjectName("PrimaryButton")
        self.generate_toolpaths_button.setToolTip(
            "Review all requirements and options, then generate the selected "
            "toolpath."
        )
        self.generate_toolpaths_button.clicked.connect(
            self._show_toolpath_generation_dialog
        )
        canvas_bar_layout.addWidget(self.generate_toolpaths_button)

        fit_button = QPushButton("Fit")
        fit_button.setToolTip("Fit the entire job to the viewport")
        fit_button.clicked.connect(self._fit_view)
        canvas_bar_layout.addWidget(fit_button)

        self.inspector_button = QPushButton("Inspector")
        self.inspector_button.setCheckable(True)
        self.inspector_button.setChecked(True)
        self.inspector_button.setToolTip(
            "Show or hide the contextual stock/object inspector"
        )
        self.inspector_button.clicked.connect(
            self._toggle_properties_panel_option
        )
        canvas_bar_layout.addWidget(self.inspector_button)

        import_button = QPushButton("Import")
        import_button.setObjectName("PrimaryButton")
        import_button.setToolTip("Import a design file into this project")
        import_button.clicked.connect(
            lambda _checked=False: self._import_file()
        )
        canvas_bar_layout.addWidget(import_button)
        canvas_layout.addWidget(canvas_bar)

        self.tool_options_bar = QWidget()
        self.tool_options_bar.setObjectName("ToolOptionsBar")
        tool_options_layout = QHBoxLayout(self.tool_options_bar)
        tool_options_layout.setContentsMargins(7, 4, 7, 4)
        tool_options_layout.setSpacing(5)

        self.tool_options_title = QLabel("Tool")
        self.tool_options_title.setObjectName("ToolOptionsTitle")
        tool_options_layout.addWidget(self.tool_options_title)

        tool_options_layout.addWidget(QLabel("Depth"))
        self.tool_options_depth_spin = QDoubleSpinBox()
        self.tool_options_depth_spin.setRange(0.05, 1000.0)
        self.tool_options_depth_spin.setDecimals(3)
        self.tool_options_depth_spin.setSingleStep(0.25)
        self.tool_options_depth_spin.setSuffix(" mm")
        self.tool_options_depth_spin.setValue(self._tool_option_depth_mm)
        self.tool_options_depth_spin.setMaximumWidth(110)
        self.tool_options_depth_spin.valueChanged.connect(
            self._tool_option_depth_changed
        )
        tool_options_layout.addWidget(self.tool_options_depth_spin)

        self.tool_options_polygon_label = QLabel("Sides")
        tool_options_layout.addWidget(self.tool_options_polygon_label)
        self.tool_options_polygon_sides = QSpinBox()
        self.tool_options_polygon_sides.setRange(3, 64)
        self.tool_options_polygon_sides.setValue(
            self._tool_option_polygon_sides
        )
        self.tool_options_polygon_sides.setMaximumWidth(78)
        self.tool_options_polygon_sides.valueChanged.connect(
            self._tool_option_polygon_sides_changed
        )
        tool_options_layout.addWidget(self.tool_options_polygon_sides)

        self.tool_options_line_width_label = QLabel("Width")
        tool_options_layout.addWidget(self.tool_options_line_width_label)
        self.tool_options_line_width_spin = QDoubleSpinBox()
        self.tool_options_line_width_spin.setRange(0.05, 1000.0)
        self.tool_options_line_width_spin.setDecimals(3)
        self.tool_options_line_width_spin.setSingleStep(0.25)
        self.tool_options_line_width_spin.setSuffix(" mm")
        self.tool_options_line_width_spin.setValue(
            self._tool_option_line_width_mm
        )
        self.tool_options_line_width_spin.setMaximumWidth(110)
        self.tool_options_line_width_spin.valueChanged.connect(
            self._tool_option_line_width_changed
        )
        tool_options_layout.addWidget(self.tool_options_line_width_spin)

        self.tool_options_pen_width_label = QLabel("Width")
        tool_options_layout.addWidget(self.tool_options_pen_width_label)
        self.tool_options_pen_width_spin = QDoubleSpinBox()
        self.tool_options_pen_width_spin.setRange(0.05, 1000.0)
        self.tool_options_pen_width_spin.setDecimals(3)
        self.tool_options_pen_width_spin.setSingleStep(0.25)
        self.tool_options_pen_width_spin.setSuffix(" mm")
        self.tool_options_pen_width_spin.setValue(
            self._tool_option_pen_width_mm
        )
        self.tool_options_pen_width_spin.setMaximumWidth(110)
        self.tool_options_pen_width_spin.valueChanged.connect(
            self._tool_option_pen_width_changed
        )
        tool_options_layout.addWidget(self.tool_options_pen_width_spin)

        self.tool_options_pen_smoothing_label = QLabel("Smooth")
        tool_options_layout.addWidget(self.tool_options_pen_smoothing_label)
        self.tool_options_pen_smoothing_spin = QSpinBox()
        self.tool_options_pen_smoothing_spin.setRange(0, 100)
        self.tool_options_pen_smoothing_spin.setSuffix("%")
        self.tool_options_pen_smoothing_spin.setValue(
            self._tool_option_pen_smoothing
        )
        self.tool_options_pen_smoothing_spin.setMaximumWidth(82)
        self.tool_options_pen_smoothing_spin.setToolTip(
            "Smooth the captured freehand path after mouse-up."
        )
        self.tool_options_pen_smoothing_spin.valueChanged.connect(
            self._tool_option_pen_smoothing_changed
        )
        tool_options_layout.addWidget(self.tool_options_pen_smoothing_spin)

        self.tool_options_pen_spacing_label = QLabel("Spacing")
        tool_options_layout.addWidget(self.tool_options_pen_spacing_label)
        self.tool_options_pen_spacing_spin = QDoubleSpinBox()
        self.tool_options_pen_spacing_spin.setRange(0.02, 25.0)
        self.tool_options_pen_spacing_spin.setDecimals(2)
        self.tool_options_pen_spacing_spin.setSingleStep(0.05)
        self.tool_options_pen_spacing_spin.setSuffix(" mm")
        self.tool_options_pen_spacing_spin.setValue(
            self._tool_option_pen_spacing_mm
        )
        self.tool_options_pen_spacing_spin.setMaximumWidth(105)
        self.tool_options_pen_spacing_spin.setToolTip(
            "Minimum distance between captured freehand points."
        )
        self.tool_options_pen_spacing_spin.valueChanged.connect(
            self._tool_option_pen_spacing_changed
        )
        tool_options_layout.addWidget(self.tool_options_pen_spacing_spin)

        self.tool_options_pen_close_check = QCheckBox("Close path")
        self.tool_options_pen_close_check.setChecked(
            self._tool_option_pen_close_path
        )
        self.tool_options_pen_close_check.setToolTip(
            "Connect the end of each stroke back to its starting point."
        )
        self.tool_options_pen_close_check.toggled.connect(
            self._tool_option_pen_close_changed
        )
        tool_options_layout.addWidget(self.tool_options_pen_close_check)

        self.tool_options_text_label = QLabel("Text")
        tool_options_layout.addWidget(self.tool_options_text_label)
        self.tool_options_text_edit = QLineEdit(self._tool_option_text)
        self.tool_options_text_edit.setMinimumWidth(120)
        self.tool_options_text_edit.setMaximumWidth(260)
        self.tool_options_text_edit.textChanged.connect(
            self._tool_option_text_changed
        )
        tool_options_layout.addWidget(self.tool_options_text_edit)

        self.tool_options_font_label = QLabel("Font")
        tool_options_layout.addWidget(self.tool_options_font_label)
        self.tool_options_font_value = QLabel("")
        self.tool_options_font_value.setObjectName("ToolOptionsValue")
        self.tool_options_font_value.setMaximumWidth(220)
        self.tool_options_font_value.setToolTip(
            "Uses the current font selected in the Text Inspector."
        )
        tool_options_layout.addWidget(self.tool_options_font_value)

        tool_options_layout.addStretch(1)

        self.tool_options_apply_button = QPushButton("✓")
        self.tool_options_apply_button.setObjectName("ToolApplyButton")
        self.tool_options_apply_button.setFixedWidth(32)
        self.tool_options_apply_button.setToolTip(
            "Apply / finish this tool and return to Select"
        )
        self.tool_options_apply_button.clicked.connect(
            self._apply_active_tool
        )
        tool_options_layout.addWidget(self.tool_options_apply_button)

        self.tool_options_cancel_button = QPushButton("✕")
        self.tool_options_cancel_button.setObjectName("ToolCancelButton")
        self.tool_options_cancel_button.setFixedWidth(32)
        self.tool_options_cancel_button.setToolTip(
            "Cancel this tool/current preview and return to Select"
        )
        self.tool_options_cancel_button.clicked.connect(
            self._cancel_active_tool
        )
        tool_options_layout.addWidget(self.tool_options_cancel_button)

        self.tool_options_bar.hide()
        self.tool_options_polygon_label.hide()
        self.tool_options_polygon_sides.hide()
        self.tool_options_line_width_label.hide()
        self.tool_options_line_width_spin.hide()
        self.tool_options_pen_width_label.hide()
        self.tool_options_pen_width_spin.hide()
        self.tool_options_pen_smoothing_label.hide()
        self.tool_options_pen_smoothing_spin.hide()
        self.tool_options_pen_spacing_label.hide()
        self.tool_options_pen_spacing_spin.hide()
        self.tool_options_pen_close_check.hide()
        self.tool_options_text_label.hide()
        self.tool_options_text_edit.hide()
        self.tool_options_font_label.hide()
        self.tool_options_font_value.hide()
        canvas_layout.addWidget(self.tool_options_bar)

        self.viewport = MeshViewport(self.project)
        canvas_layout.addWidget(self.viewport, 1)

        self.properties_panel = Panel("Inspector")
        self.properties_panel.setObjectName("InspectorPanel")
        # Keep the inspector useful at a compact canvas-friendly width while
        # preventing users from collapsing it until controls become unusable.
        self.properties_panel.setMinimumWidth(260)

        selection_heading = QLabel("Selection")
        selection_heading.setObjectName("SectionHeading")
        self.properties_panel.body_layout.addWidget(selection_heading)

        self.selection_info = QLabel()
        self.selection_info.setWordWrap(True)
        self.selection_info.setObjectName("InspectorSummary")
        self.properties_panel.body_layout.addWidget(self.selection_info)

        self.stock_widget = self._build_stock_controls()
        self.properties_panel.body_layout.addWidget(self.stock_widget)

        self.text_widget = self._build_text_controls()
        self.properties_panel.body_layout.addWidget(self.text_widget)

        self.transform_widget = self._build_transform_controls()
        self.properties_panel.body_layout.addWidget(self.transform_widget)

        activity_heading = QLabel("Job / CAM")
        activity_heading.setObjectName("SectionHeading")
        self.properties_panel.body_layout.addWidget(activity_heading)

        self.activity_info = QLabel(
            "No calculated toolpath. Choose an operation on Toolpaths when ready."
        )
        self.activity_info.setWordWrap(True)
        self.activity_info.setObjectName("ActivitySummary")
        self.properties_panel.body_layout.addWidget(self.activity_info)

        inspector_hint = QLabel(
            "Cutter selection and CAM settings are grouped on the Toolpaths ribbon."
        )
        inspector_hint.setWordWrap(True)
        inspector_hint.setObjectName("Muted")
        self.properties_panel.body_layout.addWidget(inspector_hint)
        self.properties_panel.body_layout.addStretch(1)

        self.project_list.currentRowChanged.connect(self._update_properties)
        self.project_list.itemSelectionChanged.connect(
            self._project_selection_changed
        )
        self.project_list.itemChanged.connect(self._project_item_changed)
        self._refresh_project_list(0)

        splitter.addWidget(canvas)
        splitter.addWidget(self.properties_panel)
        splitter.setSizes(self._default_workspace_splitter_sizes(1500))
        splitter.setStretchFactor(0, 1)
        layout.addWidget(splitter, 1)
        return wrapper

    def _properties_panel_default_width(self) -> int:
        """Return a useful contextual-inspector width without stealing canvas."""

        self.properties_panel.ensurePolished()
        self.stock_widget.ensurePolished()
        self.transform_widget.ensurePolished()

        body_margins = self.properties_panel.body_layout.contentsMargins()
        frame_padding = self.properties_panel.frameWidth() * 2
        outer_padding = (
            body_margins.left()
            + body_margins.right()
            + frame_padding
        )
        content_width = max(
            self.properties_panel.header.sizeHint().width(),
            self.stock_widget.sizeHint().width(),
            self.text_widget.sizeHint().width(),
            self.transform_widget.sizeHint().width(),
        )
        return max(300, min(370, content_width + outer_padding))

    def _default_workspace_splitter_sizes(
        self,
        total_width: int | None = None,
    ) -> list[int]:
        if total_width is None:
            total_width = sum(self.workspace_splitter.sizes())
        if total_width <= 0:
            total_width = 1500

        inspector_width = self._properties_panel_default_width()
        canvas_width = max(520, total_width - inspector_width)
        return [canvas_width, inspector_width]

    @staticmethod
    def _configured_spin(
        *,
        minimum: float,
        maximum: float,
        decimals: int,
        step: float,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        spin.setMinimumWidth(0)
        spin.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        return spin

    @staticmethod
    def _configure_inspector_form(form: QFormLayout) -> None:
        """Make a form reflow instead of clipping in a narrow inspector."""

        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

    @staticmethod
    def _configure_inspector_field(widget: QWidget) -> None:
        widget.setMinimumWidth(0)
        policy = widget.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        widget.setSizePolicy(policy)

    @staticmethod
    def _installed_text_font_families() -> list[str]:
        """Return installed font families suitable for editable CNC text."""

        symbol = QFontDatabase.WritingSystem.Symbol
        families: list[str] = []
        for family in QFontDatabase.families():
            writing_systems = QFontDatabase.writingSystems(family)
            if writing_systems and all(
                system == symbol for system in writing_systems
            ):
                continue
            families.append(family)

        # A pathological/minimal font setup should still leave the editor
        # usable rather than producing an empty selector.
        if not families:
            families = list(QFontDatabase.families())
        return families

    @staticmethod
    def _parse_fontconfig_text_font_aliases(
        output: str,
        families: list[str],
    ) -> dict[str, tuple[str, str]]:
        """Map full-name aliases back to their real family and style."""

        available = {family.casefold(): family for family in families}
        candidates: dict[str, set[tuple[str, str]]] = {}
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) < 3:
                continue
            family_name, style_name, full_name = (
                field.strip() for field in fields[:3]
            )
            canonical = available.get(family_name.casefold())
            alias = available.get(full_name.casefold())
            if (
                canonical is None
                or alias is None
                or canonical.casefold() == alias.casefold()
            ):
                continue
            candidates.setdefault(alias.casefold(), set()).add(
                (canonical, style_name or "Regular")
            )

        # If Fontconfig reports one full name ambiguously for more than one
        # family/style, leave it visible instead of guessing.
        return {
            alias: next(iter(options))
            for alias, options in candidates.items()
            if len(options) == 1
        }

    @classmethod
    def _fontconfig_text_font_aliases(
        cls,
        families: list[str],
    ) -> dict[str, tuple[str, str]]:
        """Return Linux Fontconfig aliases when available.

        Qt sometimes exposes a font's full face name as another family.
        Fontconfig keeps the canonical family/style relationship, so use it
        to hide duplicates such as "... Med" or "... SemBd".  Non-Linux
        systems simply fall back to the suffix grouping below.
        """

        try:
            result = subprocess.run(
                (
                    "fc-list",
                    "-f",
                    "%{family[0]}\\t%{style[0]}\\t%{fullname[0]}\\n",
                ),
                check=False,
                capture_output=True,
                text=True,
                timeout=3.0,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            return {}
        if result.returncode != 0:
            return {}
        return cls._parse_fontconfig_text_font_aliases(
            result.stdout,
            families,
        )

    def _canonical_text_font_family(
        self,
        family: str,
    ) -> tuple[str, str | None]:
        alias = getattr(self, "_text_font_aliases", {}).get(
            family.casefold()
        )
        if alias is None:
            return family, None
        return alias

    @staticmethod
    def _font_family_variant_candidate(family: str) -> tuple[str, str]:
        """Split common family-level alternatives from a font family name."""

        remaining = family.strip()
        qualifier = ""
        if remaining.endswith("]"):
            qualifier_start = remaining.rfind(" [")
            if qualifier_start > 0:
                qualifier = remaining[qualifier_start:]
                remaining = remaining[:qualifier_start].rstrip()

        parts: list[str] = []
        while remaining:
            matched = False
            folded = remaining.casefold()
            for suffix, label in _FONT_FAMILY_VARIANT_SUFFIXES:
                needle = f" {suffix}".casefold()
                if not folded.endswith(needle):
                    continue
                base = remaining[: -len(suffix)].rstrip()
                if not base:
                    continue
                remaining = base
                parts.insert(0, label)
                matched = True
                break
            if not matched:
                break
        base = remaining or family
        if qualifier and remaining:
            base = f"{remaining}{qualifier}"
        return base, " ".join(parts) or "Regular"

    @classmethod
    def _group_text_font_families(
        cls,
        families: list[str],
    ) -> dict[str, list[tuple[str, str]]]:
        """Group concrete installed families under uncluttered base names."""

        candidates = {
            family: cls._font_family_variant_candidate(family)
            for family in families
        }
        family_names = {family.casefold() for family in families}
        candidate_counts: dict[str, int] = {}
        for base, variant in candidates.values():
            if variant == "Regular":
                continue
            key = base.casefold()
            candidate_counts[key] = candidate_counts.get(key, 0) + 1

        grouped: dict[str, list[tuple[str, str]]] = {}
        for family in families:
            base, variant = candidates[family]
            can_group = variant != "Regular" and (
                base.casefold() in family_names
                or candidate_counts.get(base.casefold(), 0) >= 2
            )
            if not can_group:
                base, variant = family, "Regular"
            grouped.setdefault(base, []).append((variant, family))

        result: dict[str, list[tuple[str, str]]] = {}
        for base in sorted(grouped, key=str.casefold):
            variants = grouped[base]
            variants.sort(
                key=lambda item: (
                    item[0] != "Regular",
                    item[0].casefold(),
                    item[1].casefold(),
                )
            )
            result[base] = variants
        return result

    def _font_group_for_family(self, family: str) -> tuple[str, str]:
        family, _alias_style = self._canonical_text_font_family(family)
        for base, variants in self._text_font_groups.items():
            for variant, concrete_family in variants:
                if concrete_family == family:
                    return base, variant
        first_base = next(iter(self._text_font_groups), "")
        return first_base, "Regular"

    def _selected_text_font_family(self) -> str:
        if hasattr(self, "text_font_variant_combo"):
            family = self.text_font_variant_combo.currentData()
            if isinstance(family, str) and family:
                return family
        base = self.text_font_combo.currentText()
        variants = self._text_font_groups.get(base, [])
        if variants:
            return variants[0][1]
        return QFontInfo(QFont()).family()

    def _refresh_text_font_variants(
        self,
        base_family: str,
        preferred_family: str | None = None,
    ) -> None:
        variants = self._text_font_groups.get(base_family, [])
        if preferred_family:
            preferred_family, _alias_style = (
                self._canonical_text_font_family(preferred_family)
            )
        self.text_font_variant_combo.blockSignals(True)
        try:
            self.text_font_variant_combo.clear()
            for label, concrete_family in variants:
                self.text_font_variant_combo.addItem(label, concrete_family)
                index = self.text_font_variant_combo.count() - 1
                self.text_font_variant_combo.setItemData(
                    index,
                    QFont(concrete_family),
                    Qt.ItemDataRole.FontRole,
                )
            index = -1
            if preferred_family:
                index = self.text_font_variant_combo.findData(
                    preferred_family
                )
            if index < 0:
                index = self.text_font_variant_combo.findText("Regular")
            self.text_font_variant_combo.setCurrentIndex(max(0, index))
            self.text_font_variant_combo.setEnabled(
                self.text_font_variant_combo.count() > 1
            )
        finally:
            self.text_font_variant_combo.blockSignals(False)

    def _build_stock_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("StockControls")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 6, 0, 10)
        layout.setSpacing(6)

        heading = QLabel("Stock dimensions")
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)

        form = QFormLayout()
        self._configure_inspector_form(form)
        layout.addLayout(form)

        self.stock_spins = tuple(
            self._configured_spin(
                minimum=0.1,
                maximum=100000.0,
                decimals=3,
                step=1.0,
                suffix=" mm",
            )
            for _ in range(3)
        )
        for title, spin in zip(
            ("Width", "Height", "Thickness"),
            self.stock_spins,
            strict=True,
        ):
            form.addRow(title, spin)
            spin.valueChanged.connect(self._stock_control_changed)

        return widget

    def _build_text_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("TextControls")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 6, 0, 10)
        layout.setSpacing(6)

        heading = QLabel("Text")
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)

        self.text_editor = QPlainTextEdit()
        self.text_editor.setPlaceholderText("Enter text…")
        self.text_editor.setMinimumHeight(72)
        self.text_editor.setMaximumHeight(120)
        self.text_editor.setMinimumWidth(0)
        self.text_editor.setTabChangesFocus(True)
        self.text_editor.textChanged.connect(self._text_control_changed)
        layout.addWidget(self.text_editor)

        typography_heading = QLabel("Typography")
        typography_heading.setObjectName("TextSubheading")
        layout.addWidget(typography_heading)

        typography_form = QFormLayout()
        self._configure_inspector_form(typography_form)
        layout.addLayout(typography_form)

        installed_families = self._installed_text_font_families()
        self._text_font_aliases = self._fontconfig_text_font_aliases(
            installed_families
        )
        selectable_families = [
            family
            for family in installed_families
            if family.casefold() not in self._text_font_aliases
        ]
        self._text_font_groups = self._group_text_font_families(
            selectable_families
        )

        self.text_font_combo = QComboBox()
        for base_family, variants in self._text_font_groups.items():
            preview_family = variants[0][1]
            self.text_font_combo.addItem(base_family, preview_family)
            item_index = self.text_font_combo.count() - 1
            self.text_font_combo.setItemData(
                item_index,
                QFont(preview_family),
                Qt.ItemDataRole.FontRole,
            )
        self.text_font_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.text_font_combo.setMinimumContentsLength(10)
        self._configure_inspector_field(self.text_font_combo)
        self.text_font_combo.setToolTip(
            "Base font families, previewed in their own typeface. Family-level "
            "alternatives such as Condensed or SemiBold are in Variant."
        )
        typography_form.addRow("Font", self.text_font_combo)

        self.text_font_variant_combo = QComboBox()
        self.text_font_variant_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.text_font_variant_combo.setMinimumContentsLength(8)
        self._configure_inspector_field(self.text_font_variant_combo)
        self.text_font_variant_combo.setToolTip(
            "Installed alternatives belonging to the selected base family."
        )
        typography_form.addRow("Variant", self.text_font_variant_combo)

        default_family = QFontInfo(QFont()).family()
        default_base, _default_variant = self._font_group_for_family(
            default_family
        )
        default_index = self.text_font_combo.findText(default_base)
        self.text_font_combo.setCurrentIndex(max(0, default_index))
        self._refresh_text_font_variants(
            self.text_font_combo.currentText(),
            default_family,
        )
        self.text_font_combo.currentTextChanged.connect(
            self._text_font_group_changed
        )
        self.text_font_variant_combo.currentIndexChanged.connect(
            self._text_font_variant_changed
        )

        self.text_font_style_combo = QComboBox()
        self.text_font_style_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.text_font_style_combo.setMinimumContentsLength(8)
        self._configure_inspector_field(self.text_font_style_combo)
        self.text_font_style_combo.currentTextChanged.connect(
            self._text_style_changed
        )
        typography_form.addRow("Style", self.text_font_style_combo)

        self.text_size_spin = self._configured_spin(
            minimum=1.0,
            maximum=1000.0,
            decimals=1,
            step=1.0,
            suffix=" pt",
        )
        self.text_size_spin.setToolTip(
            "Font point size, matching conventional word-processor sizing."
        )
        self.text_size_spin.valueChanged.connect(self._text_control_changed)
        typography_form.addRow("Size", self.text_size_spin)

        format_bar = QWidget()
        format_bar.setMinimumWidth(0)
        format_layout = QHBoxLayout(format_bar)
        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(4)
        self.text_bold_button = QPushButton("B")
        self.text_italic_button = QPushButton("I")
        self.text_underline_button = QPushButton("U")
        self.text_strike_button = QPushButton("S")
        for button, tooltip in (
            (self.text_bold_button, "Bold"),
            (self.text_italic_button, "Italic"),
            (self.text_underline_button, "Underline"),
            (self.text_strike_button, "Strikethrough"),
        ):
            button.setCheckable(True)
            button.setFixedWidth(34)
            button.setToolTip(tooltip)
            if button in (
                self.text_bold_button,
                self.text_italic_button,
            ):
                button.toggled.connect(self._text_emphasis_changed)
            else:
                button.toggled.connect(self._text_control_changed)
            format_layout.addWidget(button)
        format_layout.addStretch(1)
        typography_form.addRow("Effects", format_bar)

        self.text_alignment_combo = QComboBox()
        for title, value in (
            ("Left", "left"),
            ("Center", "center"),
            ("Right", "right"),
            ("Justified", "justify"),
        ):
            self.text_alignment_combo.addItem(title, value)
        self._configure_inspector_field(self.text_alignment_combo)
        self.text_alignment_combo.currentIndexChanged.connect(
            self._text_control_changed
        )
        typography_form.addRow("Align", self.text_alignment_combo)

        self.text_case_combo = QComboBox()
        for title, value in (
            ("Normal", "normal"),
            ("UPPERCASE", "uppercase"),
            ("lowercase", "lowercase"),
            ("Title Case", "title"),
        ):
            self.text_case_combo.addItem(title, value)
        self._configure_inspector_field(self.text_case_combo)
        self.text_case_combo.currentIndexChanged.connect(
            self._text_control_changed
        )
        typography_form.addRow("Case", self.text_case_combo)

        spacing_heading = QLabel("Spacing & layout")
        spacing_heading.setObjectName("TextSubheading")
        layout.addWidget(spacing_heading)

        spacing_form = QFormLayout()
        self._configure_inspector_form(spacing_form)
        layout.addLayout(spacing_form)

        self.text_kerning_check = QCheckBox("Pair kerning")
        self.text_kerning_check.setChecked(True)
        self.text_kerning_check.setToolTip(
            "Use the selected font's kerning pairs when positioning glyphs."
        )
        self.text_kerning_check.toggled.connect(self._text_control_changed)
        spacing_form.addRow(self.text_kerning_check)

        self.text_wrap_check = QCheckBox("Wrap to text box width")
        self.text_wrap_check.toggled.connect(self._text_layout_control_changed)
        spacing_form.addRow(self.text_wrap_check)

        self.text_character_spacing_spin = self._configured_spin(
            minimum=-25.0,
            maximum=100.0,
            decimals=3,
            step=0.1,
            suffix=" mm",
        )
        self.text_character_spacing_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow(
            "Character spacing",
            self.text_character_spacing_spin,
        )

        self.text_word_spacing_spin = self._configured_spin(
            minimum=-25.0,
            maximum=100.0,
            decimals=3,
            step=0.25,
            suffix=" mm",
        )
        self.text_word_spacing_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow("Word spacing", self.text_word_spacing_spin)

        self.text_line_spacing_spin = self._configured_spin(
            minimum=25.0,
            maximum=500.0,
            decimals=1,
            step=5.0,
            suffix=" %",
        )
        self.text_line_spacing_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow("Line spacing", self.text_line_spacing_spin)

        self.text_horizontal_scale_spin = self._configured_spin(
            minimum=10.0,
            maximum=400.0,
            decimals=1,
            step=5.0,
            suffix=" %",
        )
        self.text_horizontal_scale_spin.setToolTip(
            "Horizontally stretch or condense character width."
        )
        self.text_horizontal_scale_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow(
            "Character width",
            self.text_horizontal_scale_spin,
        )

        self.text_box_width_spin = self._configured_spin(
            minimum=0.1,
            maximum=100000.0,
            decimals=3,
            step=1.0,
            suffix=" mm",
        )
        self.text_box_width_spin.valueChanged.connect(
            self._text_control_changed
        )
        spacing_form.addRow("Text box width", self.text_box_width_spin)

        geometry_heading = QLabel("CNC geometry")
        geometry_heading.setObjectName("TextSubheading")
        layout.addWidget(geometry_heading)

        geometry_form = QFormLayout()
        self._configure_inspector_form(geometry_form)
        layout.addLayout(geometry_form)

        self.text_geometry_combo = QComboBox()
        self.text_geometry_combo.addItem("Filled", "filled")
        self.text_geometry_combo.addItem("Outline", "outline")
        self._configure_inspector_field(self.text_geometry_combo)
        self.text_geometry_combo.currentIndexChanged.connect(
            self._text_geometry_control_changed
        )
        geometry_form.addRow("Geometry", self.text_geometry_combo)

        self.text_outline_width_spin = self._configured_spin(
            minimum=0.05,
            maximum=50.0,
            decimals=3,
            step=0.1,
            suffix=" mm",
        )
        self.text_outline_width_spin.valueChanged.connect(
            self._text_control_changed
        )
        self.text_outline_label = QLabel("Outline width")
        geometry_form.addRow(
            self.text_outline_label,
            self.text_outline_width_spin,
        )

        self.text_depth_spin = self._configured_spin(
            minimum=0.05,
            maximum=1000.0,
            decimals=3,
            step=0.25,
            suffix=" mm",
        )
        self.text_depth_spin.setToolTip(
            "Extruded text thickness. Text top remains at the object's Z level."
        )
        self.text_depth_spin.valueChanged.connect(self._text_control_changed)
        geometry_form.addRow("Depth", self.text_depth_spin)

        self._text_shortcuts: list[QShortcut] = []
        for sequence, callback in (
            ("Ctrl+B", self.text_bold_button.toggle),
            ("Ctrl+I", self.text_italic_button.toggle),
            ("Ctrl+U", self.text_underline_button.toggle),
            ("Ctrl+Shift+X", self.text_strike_button.toggle),
            (
                "Ctrl+L",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("left")
                ),
            ),
            (
                "Ctrl+E",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("center")
                ),
            ),
            (
                "Ctrl+R",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("right")
                ),
            ),
            (
                "Ctrl+J",
                lambda: self.text_alignment_combo.setCurrentIndex(
                    self.text_alignment_combo.findData("justify")
                ),
            ),
        ):
            shortcut = QShortcut(QKeySequence(sequence), widget)
            shortcut.setContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            shortcut.activated.connect(callback)
            self._text_shortcuts.append(shortcut)

        note = QLabel(
            "Font geometry comes from the exact installed system font face. "
            "CarveFoundry refuses silent Qt font substitution when regenerating "
            "text so CNC geometry cannot quietly change typefaces."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.text_font_face_status = QLabel()
        self.text_font_face_status.setObjectName("TextFontFaceStatus")
        self.text_font_face_status.setWordWrap(True)
        layout.addWidget(self.text_font_face_status)

        self.text_font_verify_button = QPushButton("Verify Font Face")
        self.text_font_verify_button.setToolTip(
            "Verify that Qt resolves the selected family and style to the exact "
            "installed face used to generate CNC outlines."
        )
        self.text_font_verify_button.clicked.connect(
            self._verify_selected_text_font_face
        )
        layout.addWidget(self.text_font_verify_button)

        self.text_font_warning = QLabel()
        self.text_font_warning.setObjectName("TextFontWarning")
        self.text_font_warning.setWordWrap(True)
        self.text_font_warning.hide()
        layout.addWidget(self.text_font_warning)

        self.text_cnc_hint = QLabel()
        self.text_cnc_hint.setObjectName("TextCncHint")
        self.text_cnc_hint.setWordWrap(True)
        layout.addWidget(self.text_cnc_hint)

        initial_family = self._selected_text_font_family()
        self._refresh_text_font_styles(initial_family, "Regular")
        self._update_text_editor_preview(initial_family)

        widget.setVisible(False)
        return widget

    def _build_transform_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("TransformControls")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 6, 0, 10)
        layout.setSpacing(6)

        heading = QLabel("Model transform")
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)

        units_form = QFormLayout()
        self._configure_inspector_form(units_form)
        layout.addLayout(units_form)

        self.source_units_combo = QComboBox()
        for units in ModelUnits:
            self.source_units_combo.addItem(units.display_name, units)
        self._configure_inspector_field(self.source_units_combo)
        self.source_units_combo.currentIndexChanged.connect(
            self._source_units_changed
        )
        units_form.addRow("Model units", self.source_units_combo)

        self.position_spins = tuple(
            self._configured_spin(
                minimum=-100000.0,
                maximum=100000.0,
                decimals=3,
                step=1.0,
                suffix=" mm",
            )
            for _ in range(3)
        )
        self.rotation_spins = tuple(
            self._configured_spin(
                minimum=-3600.0,
                maximum=3600.0,
                decimals=1,
                step=5.0,
                suffix="°",
            )
            for _ in range(3)
        )
        rotation_planes = (
            ("X", "YZ"),
            ("Y", "XZ"),
            ("Z", "XY"),
        )
        for spin, (axis, plane) in zip(
            self.rotation_spins,
            rotation_planes,
            strict=True,
        ):
            spin.setToolTip(
                f"Rotate around the {axis} axis; motion occurs in the {plane} plane."
            )
            spin.setAccessibleName(f"Rotation around {axis} axis")

        self.size_spins = tuple(
            self._configured_spin(
                minimum=0.001,
                maximum=100000.0,
                decimals=3,
                step=1.0,
                suffix=" mm",
            )
            for _ in range(3)
        )
        for spin, axis in zip(
            self.size_spins,
            ("X", "Y", "Z"),
            strict=True,
        ):
            spin.setToolTip(
                f"Set model Size {axis} directly in millimeters. "
                "Size is measured before rotation."
            )

        self.scale_spins = tuple(
            self._configured_spin(
                minimum=0.001,
                maximum=1000.0,
                decimals=4,
                step=0.05,
            )
            for _ in range(3)
        )

        def add_axis_group(
            title: str,
            spins: tuple[QDoubleSpinBox, ...],
        ) -> None:
            title_label = QLabel(title)
            title_label.setObjectName("InspectorFieldHeading")
            layout.addWidget(title_label)

            axis_form = QFormLayout()
            self._configure_inspector_form(axis_form)
            for axis, spin in zip(("X", "Y", "Z"), spins, strict=True):
                axis_form.addRow(axis, spin)
                spin.valueChanged.connect(self._transform_control_changed)
            layout.addLayout(axis_form)

        add_axis_group("Position", self.position_spins)
        add_axis_group("Rotate about", self.rotation_spins)

        rotation_note = QLabel(
            "Rotation axes: X → YZ plane   Y → XZ plane   Z → XY plane"
        )
        rotation_note.setObjectName("Muted")
        rotation_note.setWordWrap(True)
        rotation_note.setToolTip(
            "X/Y/Z name the axis being rotated around, not the plane being rotated."
        )
        layout.addWidget(rotation_note)

        add_axis_group("Size", self.size_spins)
        add_axis_group("Scale", self.scale_spins)

        lock_bar = QWidget()
        lock_bar.setMinimumWidth(0)
        lock_layout = QHBoxLayout(lock_bar)
        lock_layout.setContentsMargins(0, 0, 0, 0)
        lock_layout.setSpacing(8)
        lock_layout.addWidget(QLabel("Lock axes"))
        self.lock_axis_checks = tuple(
            QCheckBox(axis)
            for axis in ("X", "Y", "Z")
        )
        for checkbox in self.lock_axis_checks:
            checkbox.setChecked(True)
            checkbox.setToolTip(
                "Locked axes resize proportionally together when Size or Scale changes."
            )
            lock_layout.addWidget(checkbox)
        lock_layout.addStretch(1)
        layout.addWidget(lock_bar)

        action_bar = QWidget()
        action_bar.setMinimumWidth(0)
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)

        center_button = QPushButton("Center XY")
        center_button.setMinimumWidth(0)
        center_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        center_button.clicked.connect(self._center_selected_xy)
        action_layout.addWidget(center_button)

        top_button = QPushButton("Top to Z0")
        top_button.setMinimumWidth(0)
        top_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        top_button.clicked.connect(self._top_selected_to_surface)
        action_layout.addWidget(top_button)
        layout.addWidget(action_bar)

        reset_button = QPushButton("Reset Transform")
        reset_button.setMinimumWidth(0)
        reset_button.clicked.connect(self._reset_selected_transform)
        layout.addWidget(reset_button)

        widget.setVisible(False)
        return widget

    def _set_activity_info(self, text: str) -> None:
        if hasattr(self, "activity_info"):
            self.activity_info.setText(text)

    def _set_cam_status(self, state: str, text: str, tooltip: str) -> None:
        if not hasattr(self, "cam_status_label"):
            return
        self.cam_status_label.setText(text)
        self.cam_status_label.setToolTip(tooltip)
        self.cam_status_label.setProperty("state", state)
        self.cam_status_label.style().unpolish(self.cam_status_label)
        self.cam_status_label.style().polish(self.cam_status_label)

    def _sync_selection_action_state(self) -> None:
        if not hasattr(self, "project_list"):
            return

        item = self._selected_item()
        indices = self._selected_design_indices()
        has_selection = bool(indices)
        selection_count = len(indices)
        has_mesh = bool(
            selection_count == 1
            and item is not None
            and item.mesh is not None
        )
        has_grouped = any(
            self.project.items[index].group_id is not None
            for index in indices
            if 0 <= index < len(self.project.items)
        )
        current_index = self._selected_item_index()

        if self._calculate_button is not None:
            self._calculate_button.setEnabled(True)
            self._calculate_button.setToolTip(
                "Review requirements and generate toolpaths. Surface / Face "
                "can run from stock alone; other operations require geometry."
            )
        if self.generate_toolpaths_button is not None:
            self.generate_toolpaths_button.setEnabled(True)
            self.generate_toolpaths_button.setToolTip(
                "Review all requirements and options, then generate toolpaths. "
                "Surface / Face can run from stock alone."
            )

        for button in self._model_selection_buttons:
            button.setEnabled(has_mesh)

        enabled_by_action = {
            "cut": has_selection,
            "copy": has_selection,
            "paste": bool(self._clipboard_items),
            "delete": has_selection,
            "align": has_selection,
            "center": has_selection,
            "group": selection_count >= 2,
            "ungroup": has_grouped,
            "duplicate": has_selection,
            "move_up": current_index is not None and current_index > 0,
            "move_down": (
                current_index is not None
                and current_index < len(self.project.items) - 1
            ),
        }
        for name, enabled in enabled_by_action.items():
            button = self._selection_action_buttons.get(name)
            if button is not None:
                button.setEnabled(enabled)
            if hasattr(self, "layers_popup"):
                popup_button = self.layers_popup.action_buttons.get(name)
                if popup_button is not None:
                    popup_button.setEnabled(enabled)

        if hasattr(self, "tool_rail"):
            self.tool_rail.set_tool_enabled("arrange", has_selection)
            self.tool_rail.set_tool_enabled("cam", True)

    def _set_history_action_state(
        self,
        *,
        can_undo: bool,
        can_redo: bool,
        undo_label: str | None = None,
        redo_label: str | None = None,
    ) -> None:
        for button in self._history_action_buttons["undo"]:
            button.setEnabled(can_undo)
            button.setToolTip(
                f"Undo: {undo_label} • Ctrl+Z"
                if can_undo and undo_label
                else "Nothing to undo"
            )
        for button in self._history_action_buttons["redo"]:
            button.setEnabled(can_redo)
            button.setToolTip(
                f"Redo: {redo_label} • Ctrl+Y"
                if can_redo and redo_label
                else "Nothing to redo"
            )

    def _sync_toolpath_output_state(self) -> None:
        has_toolpaths = bool(self.project.toolpaths)
        for button in self._toolpath_output_buttons:
            button.setEnabled(has_toolpaths)

        if not has_toolpaths:
            if self._toolpaths_view_button is not None:
                self._toolpaths_view_button.setChecked(False)
            if self._rapids_view_button is not None:
                self._rapids_view_button.setChecked(False)
            if self._simulation_button is not None:
                self._simulation_button.setChecked(False)
        else:
            if self._toolpaths_view_button is not None:
                self._toolpaths_view_button.setChecked(
                    self.viewport.toolpaths_visible
                )
            if self._rapids_view_button is not None:
                self._rapids_view_button.setChecked(
                    self.viewport.rapids_visible
                )

        if has_toolpaths:
            self._toolpaths_stale_reason = None
            source_names = self._toolpath_source_names(
                self.project.toolpaths
            )
            operation_names = " + ".join(
                path.name for path in self.project.toolpaths
            )
            source_text = ", ".join(source_names) if source_names else "Unknown source"
            self._set_cam_status(
                "ready",
                "CAM: READY",
                (
                    f"{operation_names} for {source_text}. "
                    "Current and available to preview or export."
                ),
            )
        elif self._toolpaths_stale_reason:
            self._set_cam_status(
                "stale",
                "CAM: RECALCULATE",
                (
                    "The previous toolpath was cleared because "
                    f"{self._toolpaths_stale_reason.lower()} changed."
                ),
            )
        else:
            self._set_cam_status(
                "none",
                "CAM: NONE",
                "No calculated toolpath for the current job.",
            )

    def _toolpath_source_names(self, toolpaths) -> list[str]:
        names_by_id = {
            item.item_id: item.name
            for item in self.project.items
        }
        names: list[str] = []
        for path in toolpaths:
            name = (
                names_by_id.get(path.source_item_id)
                if path.source_item_id
                else None
            ) or path.source_item_name
            if name and name not in names:
                names.append(name)
        return names

    def _sync_toolpath_state_from_project(self) -> None:
        if self.project.toolpaths:
            self._toolpaths_stale_reason = None
            operation_names = " + ".join(
                path.name for path in self.project.toolpaths
            )
            source_names = self._toolpath_source_names(
                self.project.toolpaths
            )
            source_text = ", ".join(source_names) if source_names else "Unknown"
            total_moves = sum(
                len(path.moves) for path in self.project.toolpaths
            )
            total_minutes = sum(
                path.estimated_cutting_minutes
                for path in self.project.toolpaths
            )
            self._set_activity_info(
                "Toolpath available\n"
                f"{operation_names}\n\n"
                f"Source: {source_text}\n"
                f"Moves: {total_moves:,}\n"
                f"Estimated cutting: {total_minutes:.1f} min"
            )
            self.viewport.set_toolpaths_visible(True)
        else:
            self._set_activity_info(
                "No calculated toolpath. Choose an operation on Toolpaths when ready."
            )
            self.viewport.set_toolpaths_visible(False)

        self._sync_toolpath_output_state()
        self.viewport.update()

    def _invalidate_toolpaths(self, reason: str) -> bool:
        """Clear calculated motion when geometry or CAM inputs become stale."""

        if not self.project.toolpaths:
            return False

        self.project.toolpaths.clear()
        self._toolpaths_stale_reason = reason

        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
        self.viewport.set_simulation_fraction(1.0)
        self.viewport.set_toolpaths_visible(False)

        preview = self._toolpath_preview_window
        if preview is not None:
            preview.close()
            self._toolpath_preview_window = None

        self._set_activity_info(
            "Toolpath needs recalculation\n"
            f"{reason} changed after the last calculation.\n\n"
            "Review the current setup and press Calculate again before previewing "
            "or exporting G-code."
        )
        self._sync_toolpath_output_state()
        self.viewport.update()
        return True

    @staticmethod
    def _number(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    @classmethod
    def _source_dimensions_text(cls, item: ProjectItem) -> str:
        if item.mesh is None:
            return ""
        dimensions = " × ".join(cls._number(value) for value in item.mesh.dimensions)
        return f"{dimensions} {item.source_units.value}"

    @classmethod
    def _mesh_properties_text(cls, item: ProjectItem) -> str:
        mesh = item.mesh
        if mesh is None:
            return f"{item.name}\n{item.kind.upper()} source"

        local_size = item.local_size_mm()
        bounds = item.transformed_bounds_mm()
        assert local_size is not None and bounds is not None

        size_text = " × ".join(
            cls._number(float(value))
            for value in local_size
        )
        world_size = bounds[1] - bounds[0]
        world_size_text = " × ".join(
            cls._number(float(value))
            for value in world_size
        )
        position = " / ".join(
            cls._number(float(value))
            for value in item.transform.translation_mm
        )
        rotation = " / ".join(
            f"{cls._number(float(value))}°"
            for value in item.transform.rotation_deg
        )
        scale = " / ".join(
            cls._number(float(value))
            for value in item.transform.scale_xyz
        )
        kind = "STL" if item.kind.lower() == "stl" else item.kind.upper()
        group = "\nGrouped object" if item.group_id else ""
        text_details = ""
        if item.kind.lower() == "text" and item.text_properties is not None:
            properties = item.text_properties
            style_parts = [
                properties.font_style or "Regular",
                f"{cls._number(properties.size_pt)} pt",
            ]
            if properties.bold:
                style_parts.append("Bold")
            if properties.italic:
                style_parts.append("Italic")
            text_details = (
                "\nText: "
                + " • ".join(style_parts)
                + f"\nFont: {properties.font_family or 'System default'}"
                + f"\nGeometry: {properties.geometry_mode.title()}"
            )

        return (
            f"{item.name}\n"
            f"{kind} • {mesh.face_count:,} faces{group}{text_details}\n\n"
            f"Size XYZ: {size_text} mm\n"
            f"World bounds: {world_size_text} mm\n"
            f"Position XYZ: {position} mm\n"
            f"Rotation XYZ: {rotation}\n"
            f"Scale XYZ: {scale}\n\n"
            f"Source: {cls._source_dimensions_text(item)}"
        )

    def _stock_list_text(self) -> str:
        stock = self.project.stock
        return (
            f"Stock  {self._number(stock.width_mm)} × "
            f"{self._number(stock.height_mm)} × "
            f"{self._number(stock.thickness_mm)} mm"
        )

    def _item_list_text(self, item: ProjectItem) -> str:
        return item.name

    @staticmethod
    def _object_selector_text(item: ProjectItem) -> str:
        group = " • Grouped" if item.group_id else ""
        kind = "STL" if item.kind.lower() == "stl" else item.kind.upper()
        preview = ""
        if item.kind.lower() == "text" and item.text_properties is not None:
            first_line = " ".join(
                item.text_properties.content.splitlines()
            ).strip()
            if first_line:
                if len(first_line) > 34:
                    first_line = first_line[:31].rstrip() + "…"
                preview = f' • “{first_line}”'
        return f"{item.name}  [{kind}]{group}{preview}"

    def _refresh_project_list(self, selected_row: int = 0) -> None:
        self._updating_project_list = True
        self._updating_object_selector = True
        self.project_list.blockSignals(True)
        self.object_selector.blockSignals(True)
        try:
            self.project_list.clear()
            self.object_selector.clear()

            self.project_list.addItem(self._stock_list_text())
            self.object_selector.addItem("Stock")

            for project_item in self.project.items:
                list_item = QListWidgetItem(self._item_list_text(project_item))
                kind = (
                    "STL"
                    if project_item.kind.lower() == "stl"
                    else project_item.kind.upper()
                )
                group_text = "\nGrouped object" if project_item.group_id else ""
                source_size = self._source_dimensions_text(project_item)
                text_preview = ""
                if (
                    project_item.kind.lower() == "text"
                    and project_item.text_properties is not None
                ):
                    content_preview = " ".join(
                        project_item.text_properties.content.splitlines()
                    ).strip()
                    if len(content_preview) > 90:
                        content_preview = content_preview[:87].rstrip() + "…"
                    if content_preview:
                        text_preview = f"\nContent: {content_preview}"
                list_item.setToolTip(
                    f"{kind} • {project_item.name}{group_text}"
                    + text_preview
                    + (
                        f"\nSource size: {source_size}"
                        if source_size
                        else ""
                    )
                    + "\nDouble-click or press F2 to rename."
                )
                list_item.setFlags(
                    list_item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEditable
                )
                list_item.setCheckState(
                    Qt.CheckState.Checked
                    if project_item.visible
                    else Qt.CheckState.Unchecked
                )
                self.project_list.addItem(list_item)
                self.object_selector.addItem(
                    self._object_selector_text(project_item)
                )

            selected_row = max(
                0,
                min(selected_row, self.project_list.count() - 1),
            )
            self.project_list.setCurrentRow(selected_row)
            self.object_selector.setCurrentIndex(selected_row)
            self.layers_popup.set_object_count(len(self.project.items))
        finally:
            self.project_list.blockSignals(False)
            self.object_selector.blockSignals(False)
            self._updating_project_list = False
            self._updating_object_selector = False
        self._update_properties(selected_row)

    def _object_selector_changed(self, row: int) -> None:
        if self._updating_object_selector:
            return
        row = max(0, min(int(row), self.project_list.count() - 1))
        if row <= 0:
            self._select_project_indices([])
        else:
            self._select_project_indices([row - 1], primary=row - 1)

    def _show_layers_popup(self) -> None:
        if not hasattr(self, "layers_popup"):
            return
        self.layers_popup.show_below(self.layers_button)

    def _active_cutter_changed(self, _index: int) -> None:
        cutter = self.tool_combo.currentData()
        if hasattr(self, "_cutter_menu_actions"):
            current = self.tool_combo.currentIndex()
            for index, action in enumerate(self._cutter_menu_actions):
                action.setChecked(index == current)
        if cutter is not None and hasattr(cutter, "name"):
            self._settings.setValue("tools/selected_name", cutter.name)
            self._settings.sync()
            self._invalidate_toolpaths("Selected cutter")
        self._refresh_cam_detail_readouts()
        if hasattr(self, "text_cnc_hint"):
            self._update_text_cnc_hint()

    def _ensure_inspector_visible(self) -> None:
        self.properties_panel.show()
        self.inspector_button.setChecked(True)
        if hasattr(self, "tool_rail"):
            rail_button = self.tool_rail.buttons.get("inspector")
            if rail_button is not None:
                rail_button.setChecked(True)
        self._set_option_checked("properties_panel", True)

        sizes = self.workspace_splitter.sizes()
        if len(sizes) == 2 and sizes[1] < 40:
            preferred = self._properties_panel_default_width()
            total = max(sum(sizes), preferred + 520)
            self.workspace_splitter.setSizes(
                [max(520, total - preferred), preferred]
            )
        self._save_interface_options()

    def _focus_stock_section(self) -> None:
        self._ensure_inspector_visible()
        if self.project_list.currentRow() != 0:
            self.project_list.setCurrentRow(0)
        self.stock_spins[0].setFocus(Qt.FocusReason.OtherFocusReason)
        self.stock_spins[0].selectAll()
        self.statusBar().showMessage("Stock setup ready", 2500)

    def _project_item_changed(self, list_item: QListWidgetItem) -> None:
        if self._updating_project_list:
            return
        row = self.project_list.row(list_item)
        if row <= 0:
            return
        index = row - 1
        if index >= len(self.project.items):
            return

        project_item = self.project.items[index]
        visible = list_item.checkState() == Qt.CheckState.Checked
        visibility_changed = visible != project_item.visible
        project_item.visible = visible

        requested_name = list_item.text().strip()
        if not requested_name:
            requested_name = project_item.name

        other_names = {
            item.name
            for other_index, item in enumerate(self.project.items)
            if other_index != index
        }
        unique_name = requested_name
        if unique_name in other_names:
            base = requested_name
            number = 2
            while f"{base} {number}" in other_names:
                number += 1
            unique_name = f"{base} {number}"

        renamed = unique_name != project_item.name
        if renamed:
            old_name = project_item.name
            project_item.name = unique_name
            self._updating_project_list = True
            list_item.blockSignals(True)
            try:
                list_item.setText(unique_name)
            finally:
                list_item.blockSignals(False)
                self._updating_project_list = False

            self.object_selector.blockSignals(True)
            try:
                self.object_selector.setItemText(
                    row,
                    self._object_selector_text(project_item),
                )
            finally:
                self.object_selector.blockSignals(False)

            kind = (
                "STL"
                if project_item.kind.lower() == "stl"
                else project_item.kind.upper()
            )
            group_text = "\nGrouped object" if project_item.group_id else ""
            source_size = self._source_dimensions_text(project_item)
            list_item.setToolTip(
                f"{kind} • {project_item.name}{group_text}"
                + (
                    f"\nSource size: {source_size}"
                    if source_size
                    else ""
                )
                + "\nDouble-click or press F2 to rename."
            )
            self.selection_info.setText(
                self._mesh_properties_text(project_item)
            )
            if any(
                path.source_item_id == project_item.item_id
                for path in self.project.toolpaths
            ):
                self._sync_toolpath_state_from_project()
            self.statusBar().showMessage(
                f"Renamed {old_name} → {unique_name}",
                2500,
            )
        elif visibility_changed:
            state = "visible" if visible else "hidden"
            self.statusBar().showMessage(
                f"{project_item.name} {state}",
                2000,
            )

        self.viewport.update()

    def _sync_stock_controls(self) -> None:
        self._updating_stock_controls = True
        try:
            for spin, value in zip(
                self.stock_spins,
                (
                    self.project.stock.width_mm,
                    self.project.stock.height_mm,
                    self.project.stock.thickness_mm,
                ),
                strict=True,
            ):
                spin.setValue(value)
        finally:
            self._updating_stock_controls = False

    def _stock_control_changed(self, _value: float) -> None:
        if self._updating_stock_controls:
            return
        width, height, thickness = (spin.value() for spin in self.stock_spins)
        self.project.stock.width_mm = width
        self.project.stock.height_mm = height
        self.project.stock.thickness_mm = thickness
        self._invalidate_toolpaths("Stock dimensions")
        if self.project_list.count():
            self.project_list.item(0).setText(self._stock_list_text())
        self.selection_info.setText(
            "Stock\n"
            f"{self._number(width)} × {self._number(height)} × "
            f"{self._number(thickness)} mm"
        )
        self.viewport.update()

    def _select_project_indices(
        self,
        indices: list[int] | tuple[int, ...] | set[int],
        *,
        primary: int | None = None,
    ) -> None:
        """Synchronize a design-object selection across Layers and viewport."""

        valid = sorted(
            {
                int(index)
                for index in indices
                if 0 <= int(index) < len(self.project.items)
            }
        )
        self.project_list.blockSignals(True)
        try:
            self.project_list.clearSelection()
            for index in valid:
                item = self.project_list.item(index + 1)
                if item is not None:
                    item.setSelected(True)

            if primary not in valid:
                primary = valid[-1] if valid else None
            row = primary + 1 if primary is not None else 0
            self.project_list.setCurrentRow(
                row,
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )
        finally:
            self.project_list.blockSignals(False)

        self._project_selection_changed()

    def _viewport_selection_requested(
        self,
        indices: object,
        mode: str,
    ) -> None:
        """Apply replace/add/toggle selection requests from the viewport."""

        requested = [
            int(index)
            for index in (indices if isinstance(indices, (list, tuple, set)) else [])
            if 0 <= int(index) < len(self.project.items)
        ]
        selected = set(self._selected_design_indices())
        incoming = set(requested)
        if mode == "add":
            selected |= incoming
        elif mode == "toggle":
            selected ^= incoming
        else:
            selected = incoming

        primary = None
        for index in reversed(requested):
            if index in selected:
                primary = index
                break
        if primary is None:
            current = self._selected_item_index()
            if current in selected:
                primary = current
        self._select_project_indices(selected, primary=primary)

    def _select_all_design_items(self) -> None:
        """Select every design object in the project."""

        if not self.project.items:
            self._select_project_indices([])
            self.statusBar().showMessage("No design objects to select", 2000)
            return
        indices = list(range(len(self.project.items)))
        self._select_project_indices(indices, primary=indices[-1])
        self.statusBar().showMessage(
            f"Selected all {len(indices)} design objects",
            2000,
        )

    def _viewport_select_item(self, index: int) -> None:
        """Compatibility adapter for single-object viewport selection."""

        if 0 <= index < len(self.project.items):
            self._select_project_indices([index], primary=index)
        else:
            self._select_project_indices([])

    def _project_selection_changed(self) -> None:
        """Keep Inspector, viewport highlights, and action state synchronized."""

        if self._updating_project_list:
            return
        indices = self._selected_design_indices()
        if indices:
            current = self._selected_item_index()
            primary = current if current in indices else indices[-1]
            row = primary + 1
        else:
            primary = None
            row = 0
        self._update_properties(row)

    def _viewport_transform_started(self, _index: int) -> None:
        """Lifecycle hook overridden by the project-history window."""

    def _viewport_transform_changed(self, index: int) -> None:
        if not 0 <= index < len(self.project.items):
            return
        row = index + 1
        if self.project_list.currentRow() != row:
            self.project_list.setCurrentRow(row)
            return
        item = self.project.items[index]
        self._sync_transform_controls(item)
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.set_selected_item(index)

    def _viewport_transform_finished(self, index: int) -> None:
        self._viewport_transform_changed(index)
        if not 0 <= index < len(self.project.items):
            return

        item = self.project.items[index]
        if self.viewport.transform_interaction_kind == "resize-text":
            self._invalidate_toolpaths("Text size")
            local_size = item.local_size_mm()
            if local_size is not None:
                self.statusBar().showMessage(
                    f"Resized {item.name} — "
                    f"W {local_size[0]:.2f}  H {local_size[1]:.2f} mm",
                    3000,
                )
            else:
                self.statusBar().showMessage(
                    f"Resized {item.name}",
                    3000,
                )
            return

        self._invalidate_toolpaths("Model position")
        x, y, z = item.transform.translation_mm
        self.statusBar().showMessage(
            f"Moved {item.name} — X {x:.2f}  Y {y:.2f}  Z {z:.2f} mm",
            3000,
        )

    def _before_context_transform(self, _index: int, _label: str) -> None:
        """History hook for a discrete viewport/context-menu transform."""

    def _after_context_transform(self, _index: int, _label: str) -> None:
        """History hook for a discrete viewport/context-menu transform."""

    def _apply_context_transform(
        self,
        label: str,
        transform_action,
    ) -> None:
        index = self._selected_item_index()
        item = self._selected_item()
        if index is None or item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return

        self._before_context_transform(index, label)
        transform_action(item)
        item.transform.validate()
        self._sync_transform_controls(item)
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.set_selected_item(index)
        self._invalidate_toolpaths("Model transform")
        self.viewport.update()
        self._after_context_transform(index, label)
        self.statusBar().showMessage(f"{label}: {item.name}", 3000)

    def _focus_transform_section(self, section: str) -> None:
        item = self._selected_item()
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return

        self._ensure_inspector_visible()

        controls = {
            "position": self.position_spins,
            "rotation": self.rotation_spins,
            "size": self.size_spins,
            "scale": self.scale_spins,
        }
        labels = {
            "position": "Position",
            "rotation": "Rotation",
            "size": "Size",
            "scale": "Scale",
        }
        target = controls.get(section, self.position_spins)
        target[0].setFocus(Qt.FocusReason.OtherFocusReason)
        target[0].selectAll()
        self.statusBar().showMessage(
            f"{labels.get(section, 'Position')} editor ready for {item.name}",
            4000,
        )

    def _move_selected_to_stock_origin(self) -> None:
        def apply(item: ProjectItem) -> None:
            bounds = item.transformed_bounds_mm()
            if bounds is None:
                return
            tx, ty, tz = item.transform.translation_mm
            item.transform.translation_mm = (
                tx - float(bounds[0, 0]),
                ty - float(bounds[0, 1]),
                tz,
            )

        self._apply_context_transform("Move to stock origin", apply)

    def _bottom_selected_to_surface(self) -> None:
        def apply(item: ProjectItem) -> None:
            bounds = item.transformed_bounds_mm()
            if bounds is None:
                return
            tx, ty, tz = item.transform.translation_mm
            item.transform.translation_mm = (
                tx,
                ty,
                tz - float(bounds[0, 2]),
            )

        self._apply_context_transform("Bottom to Z0", apply)

    def _place_selected_at_stock_origin(self) -> None:
        def apply(item: ProjectItem) -> None:
            bounds = item.transformed_bounds_mm()
            if bounds is None:
                return
            tx, ty, tz = item.transform.translation_mm
            item.transform.translation_mm = (
                tx - float(bounds[0, 0]),
                ty - float(bounds[0, 1]),
                tz - float(bounds[1, 2]),
            )

        self._apply_context_transform("Place at stock origin", apply)

    def _rotate_selected_axis(self, axis: int, degrees_delta: float) -> None:
        axis_name = "XYZ"[axis]
        plane_name = ("YZ", "XZ", "XY")[axis]

        def apply(item: ProjectItem) -> None:
            rotation = list(item.transform.rotation_deg)
            rotation[axis] += degrees_delta
            item.transform.rotation_deg = tuple(rotation)

        sign = "+" if degrees_delta >= 0 else ""
        self._apply_context_transform(
            (
                f"Rotate around {axis_name} {sign}{degrees_delta:g}° "
                f"({plane_name} plane)"
            ),
            apply,
        )

    def _reset_selected_rotation(self) -> None:
        self._apply_context_transform(
            "Reset rotation",
            lambda item: setattr(
                item.transform,
                "rotation_deg",
                (0.0, 0.0, 0.0),
            ),
        )

    def _scale_selected_uniform(self, factor: float) -> None:
        def apply(item: ProjectItem) -> None:
            item.transform.scale_xyz = tuple(
                float(value) * factor for value in item.transform.scale_xyz
            )

        self._apply_context_transform(f"Scale {factor:g}×", apply)

    def _reset_selected_scale(self) -> None:
        self._apply_context_transform(
            "Reset scale",
            lambda item: setattr(
                item.transform,
                "scale_xyz",
                (1.0, 1.0, 1.0),
            ),
        )

    def _fit_selected_inside_stock(self) -> None:
        def apply(item: ProjectItem) -> None:
            bounds = item.transformed_bounds_mm()
            if bounds is None:
                return
            dimensions = bounds[1] - bounds[0]
            width = max(float(dimensions[0]), 1e-9)
            height = max(float(dimensions[1]), 1e-9)
            factor = 0.95 * min(
                float(self.project.stock.width_mm) / width,
                float(self.project.stock.height_mm) / height,
            )
            item.transform.scale_xyz = tuple(
                float(value) * factor for value in item.transform.scale_xyz
            )

            fitted_bounds = item.transformed_bounds_mm()
            if fitted_bounds is None:
                return
            center = fitted_bounds.mean(axis=0)
            tx, ty, tz = item.transform.translation_mm
            item.transform.translation_mm = (
                tx + float(self.project.stock.width_mm) / 2.0 - float(center[0]),
                ty + float(self.project.stock.height_mm) / 2.0 - float(center[1]),
                tz,
            )

        self._apply_context_transform("Fit inside stock", apply)

    @staticmethod
    def _add_context_action(menu: QMenu, text: str, callback):
        """Add an action with a PySide-safe triggered(bool) adapter."""

        action = menu.addAction(text)
        action.triggered.connect(
            lambda _checked=False, function=callback: function()
        )
        return action

    def _show_viewport_item_context_menu(self, index: int, global_pos) -> None:
        if not 0 <= index < len(self.project.items):
            return
        self._viewport_select_item(index)
        item = self.project.items[index]

        menu = QMenu(self)
        menu.addSection(item.name)

        if item.kind.lower() == "text":
            self._add_context_action(
                menu,
                "Edit Text…",
                self._focus_text_editor,
            )
            menu.addSeparator()

        edit_menu = menu.addMenu("Edit Transform")
        self._add_context_action(
            edit_menu,
            "Move / Position…",
            lambda: self._focus_transform_section("position"),
        )
        self._add_context_action(
            edit_menu,
            "Rotate…",
            lambda: self._focus_transform_section("rotation"),
        )
        self._add_context_action(
            edit_menu,
            "Size…",
            lambda: self._focus_transform_section("size"),
        )
        self._add_context_action(
            edit_menu,
            "Scale…",
            lambda: self._focus_transform_section("scale"),
        )

        move_menu = menu.addMenu("Move / Place")
        self._add_context_action(
            move_menu,
            "Center in Stock (XY)",
            self._center_selected_xy,
        )
        self._add_context_action(
            move_menu,
            "Move to Stock Origin (XY)",
            self._move_selected_to_stock_origin,
        )
        self._add_context_action(
            move_menu,
            "Place at Stock Origin + Top Z0",
            self._place_selected_at_stock_origin,
        )
        move_menu.addSeparator()
        self._add_context_action(
            move_menu,
            "Top to Stock Surface (Z0)",
            self._top_selected_to_surface,
        )
        self._add_context_action(
            move_menu,
            "Bottom to Stock Surface (Z0)",
            self._bottom_selected_to_surface,
        )

        rotate_menu = menu.addMenu("Rotate 90°")
        for axis in range(3):
            axis_name = "XYZ"[axis]
            plane_name = ("YZ", "XZ", "XY")[axis]
            self._add_context_action(
                rotate_menu,
                f"Around {axis_name} / {plane_name} plane +90°",
                lambda a=axis: self._rotate_selected_axis(a, 90.0),
            )
            self._add_context_action(
                rotate_menu,
                f"Around {axis_name} / {plane_name} plane -90°",
                lambda a=axis: self._rotate_selected_axis(a, -90.0),
            )
        rotate_menu.addSeparator()
        self._add_context_action(
            rotate_menu,
            "Reset Rotation",
            self._reset_selected_rotation,
        )

        scale_menu = menu.addMenu("Scale")
        self._add_context_action(
            scale_menu,
            "50%",
            lambda: self._scale_selected_uniform(0.5),
        )
        self._add_context_action(
            scale_menu,
            "200%",
            lambda: self._scale_selected_uniform(2.0),
        )
        self._add_context_action(
            scale_menu,
            "Fit Inside Stock",
            self._fit_selected_inside_stock,
        )
        scale_menu.addSeparator()
        self._add_context_action(
            scale_menu,
            "Reset Scale",
            self._reset_selected_scale,
        )

        menu.addSeparator()
        self._add_context_action(
            menu,
            "Reset Full Transform",
            self._reset_selected_transform,
        )
        menu.addSeparator()
        self._add_context_action(
            menu,
            "Duplicate",
            self._duplicate_selected_item,
        )
        self._add_context_action(
            menu,
            "Delete",
            self._delete_selected_item,
        )
        menu.exec(global_pos)

    def _selected_item(self) -> ProjectItem | None:
        row = self.project_list.currentRow()
        if row <= 0:
            return None
        index = row - 1
        if index >= len(self.project.items):
            return None
        return self.project.items[index]

    def _selected_item_index(self) -> int | None:
        row = self.project_list.currentRow()
        if row <= 0:
            return None
        index = row - 1
        if index >= len(self.project.items):
            return None
        return index

    def _update_properties(self, row: int) -> None:
        if hasattr(self, "object_selector"):
            desired = max(
                0,
                min(int(row), self.object_selector.count() - 1),
            )
            if self.object_selector.currentIndex() != desired:
                self._updating_object_selector = True
                self.object_selector.blockSignals(True)
                try:
                    self.object_selector.setCurrentIndex(desired)
                finally:
                    self.object_selector.blockSignals(False)
                    self._updating_object_selector = False

        selected_indices = self._selected_design_indices()
        if len(selected_indices) > 1:
            primary = (
                row - 1
                if row > 0 and row - 1 in selected_indices
                else selected_indices[-1]
            )
            selected_names = [
                self.project.items[index].name
                for index in selected_indices
            ]
            preview = ", ".join(selected_names[:5])
            if len(selected_names) > 5:
                preview += f", +{len(selected_names) - 5} more"
            self.selection_info.setText(
                f"{len(selected_indices)} objects selected\n{preview}\n\n"
                "Use Align, Group, Duplicate, Delete, or the Layers panel "
                "to operate on the complete selection."
            )
            self.stock_widget.setVisible(False)
            self.text_widget.setVisible(False)
            self.transform_widget.setVisible(False)
            self.viewport.set_selected_items(
                selected_indices,
                primary=primary,
            )
            self._refresh_cam_detail_readouts()
            self._sync_selection_action_state()
            self._sync_toolpath_output_state()
            return

        if row <= 0:
            stock = self.project.stock
            self.selection_info.setText(
                "Stock\n"
                f"{self._number(stock.width_mm)} × {self._number(stock.height_mm)} × "
                f"{self._number(stock.thickness_mm)} mm"
            )
            self._sync_stock_controls()
            self.stock_widget.setVisible(True)
            self.text_widget.setVisible(False)
            self.transform_widget.setVisible(False)
            self.viewport.set_selected_item(None)
            self._refresh_cam_detail_readouts()
            self._sync_selection_action_state()
            self._sync_toolpath_output_state()
            return

        item_index = row - 1
        if item_index >= len(self.project.items):
            self.selection_info.setText("No design selected")
            self.stock_widget.setVisible(False)
            self.text_widget.setVisible(False)
            self.transform_widget.setVisible(False)
            self.viewport.set_selected_item(None)
            self._refresh_cam_detail_readouts()
            self._sync_selection_action_state()
            self._sync_toolpath_output_state()
            return

        item = self.project.items[item_index]
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.set_selected_item(item_index)
        self.stock_widget.setVisible(False)
        has_mesh = item.mesh is not None
        is_text = item.kind.lower() == "text" and has_mesh
        self.text_widget.setVisible(is_text)
        self.transform_widget.setVisible(has_mesh)
        if is_text:
            self._sync_text_controls(item)
        if has_mesh:
            self._sync_transform_controls(item)
        self._refresh_cam_detail_readouts()
        self._sync_selection_action_state()
        self._sync_toolpath_output_state()

    def _legacy_text_properties(self, item: ProjectItem) -> TextProperties:
        dimensions = (
            np.asarray(item.mesh.dimensions, dtype=float)
            * float(item.source_units.millimeters_per_unit)
            if item.mesh is not None
            else np.array((40.0, 12.0, 1.0), dtype=float)
        )
        content = item.name.strip() or "Text"
        return TextProperties(
            content=content,
            font_family=QFontInfo(QFont()).family(),
            size_pt=max(6.0, float(dimensions[1]) * 72.0 / 25.4),
            box_width_mm=max(0.1, float(dimensions[0])),
            depth_mm=max(0.05, float(dimensions[2])),
        )

    def _refresh_text_font_styles(
        self,
        family: str,
        preferred: str | None = None,
    ) -> None:
        styles = list(QFontDatabase.styles(family))
        if not styles:
            styles = ["Regular"]

        current = preferred or self.text_font_style_combo.currentText()
        self.text_font_style_combo.blockSignals(True)
        try:
            self.text_font_style_combo.clear()
            self.text_font_style_combo.addItems(styles)
            index = self.text_font_style_combo.findText(current)
            if index < 0:
                index = self.text_font_style_combo.findText("Regular")
            self.text_font_style_combo.setCurrentIndex(max(0, index))
        finally:
            self.text_font_style_combo.blockSignals(False)

    def _update_text_editor_preview(
        self,
        requested_family: str | None = None,
    ) -> None:
        family = (
            requested_family
            or self._selected_text_font_family()
            or QFont().family()
        )
        preview_font = QFont(family)
        style = self.text_font_style_combo.currentText()
        if style:
            preview_font.setStyleName(style)
        if self.text_bold_button.isChecked():
            preview_font.setBold(True)
        if self.text_italic_button.isChecked():
            preview_font.setItalic(True)
        preview_font.setUnderline(self.text_underline_button.isChecked())
        preview_font.setStrikeOut(self.text_strike_button.isChecked())
        preview_font.setPointSizeF(
            max(10.0, min(22.0, float(self.text_size_spin.value())))
        )
        self.text_editor.setFont(preview_font)

    def _update_text_font_availability(self, requested_family: str) -> None:
        installed = set(QFontDatabase.families())
        if requested_family and requested_family not in installed:
            fallback = self._selected_text_font_family()
            self.text_font_face_status.setText("Font face: unresolved")
            self.text_font_warning.setText(
                f"Font “{requested_family}” is not installed. "
                f"Showing {fallback or 'the system fallback'} for editing only; "
                "CarveFoundry will not regenerate CNC text with a substituted font."
            )
            self.text_font_warning.show()
            return

        family = self._selected_text_font_family() or requested_family
        style = self.text_font_style_combo.currentText() or "Regular"
        try:
            face = describe_qt_font_face(family, style)
        except ValueError as exc:
            self.text_font_face_status.setText("Font face: unresolved")
            self.text_font_warning.setText(str(exc))
            self.text_font_warning.show()
            return

        self.text_font_face_status.setText(
            f"Font face: {face.display_name}  •  exact"
        )
        self.text_font_warning.clear()
        self.text_font_warning.hide()

    def _verify_selected_text_font_face(self) -> None:
        family = self._selected_text_font_family()
        style = self.text_font_style_combo.currentText() or "Regular"
        try:
            face = describe_qt_font_face(family, style)
        except ValueError as exc:
            self._update_text_font_availability(family)
            self.statusBar().showMessage(
                f"Font verification failed: {exc}",
                7000,
            )
            return
        self._update_text_font_availability(family)
        self.statusBar().showMessage(
            f"Exact font verified: {face.display_name}",
            4000,
        )

    def _sync_text_controls(self, item: ProjectItem) -> None:
        properties = item.text_properties or self._legacy_text_properties(item)
        family = properties.font_family or QFont().family()
        canonical_family, alias_style = self._canonical_text_font_family(
            family
        )
        installed_families = set(QFontDatabase.families())
        display_family = (
            canonical_family
            if canonical_family in installed_families
            else QFont().family()
        )

        self._updating_text_controls = True
        try:
            self.text_editor.setPlainText(properties.content)
            base_family, _variant = self._font_group_for_family(
                display_family
            )
            font_index = self.text_font_combo.findText(base_family)
            self.text_font_combo.setCurrentIndex(max(0, font_index))
            self._refresh_text_font_variants(
                self.text_font_combo.currentText(),
                display_family,
            )
            display_family = self._selected_text_font_family()
            self._refresh_text_font_styles(
                display_family,
                alias_style or properties.font_style,
            )
            self.text_size_spin.setValue(properties.size_pt)
            style_bold, style_italic = self._text_style_traits(
                display_family,
                self.text_font_style_combo.currentText(),
            )
            self.text_bold_button.setChecked(
                properties.bold or style_bold
            )
            self.text_italic_button.setChecked(
                properties.italic or style_italic
            )
            self.text_underline_button.setChecked(properties.underline)
            self.text_strike_button.setChecked(properties.strikeout)

            alignment_index = self.text_alignment_combo.findData(
                properties.alignment
            )
            self.text_alignment_combo.setCurrentIndex(
                max(0, alignment_index)
            )
            case_index = self.text_case_combo.findData(properties.case_mode)
            self.text_case_combo.setCurrentIndex(max(0, case_index))

            self.text_kerning_check.setChecked(properties.kerning)
            self.text_wrap_check.setChecked(properties.wrap_to_width)
            self.text_character_spacing_spin.setValue(
                properties.character_spacing_mm
            )
            self.text_word_spacing_spin.setValue(
                properties.word_spacing_mm
            )
            self.text_line_spacing_spin.setValue(
                properties.line_spacing_percent
            )
            self.text_horizontal_scale_spin.setValue(
                properties.horizontal_scale_percent
            )
            self.text_box_width_spin.setValue(
                max(0.1, properties.box_width_mm or 0.1)
            )

            geometry_index = self.text_geometry_combo.findData(
                properties.geometry_mode
            )
            self.text_geometry_combo.setCurrentIndex(
                max(0, geometry_index)
            )
            self.text_outline_width_spin.setValue(
                properties.outline_width_mm
            )
            self.text_depth_spin.setValue(properties.depth_mm)
        finally:
            self._updating_text_controls = False

        self._update_text_font_availability(family)
        self._update_text_editor_preview(display_family)
        self._update_text_control_enablement()

    @staticmethod
    def _text_style_traits(
        family: str,
        style: str,
    ) -> tuple[bool, bool]:
        font = QFontDatabase.font(family, style, 12)
        return font.bold(), font.italic()

    def _set_text_emphasis_buttons_from_style(self) -> None:
        family = self._selected_text_font_family()
        style = self.text_font_style_combo.currentText()
        style_bold, style_italic = self._text_style_traits(
            family,
            style,
        )
        self.text_bold_button.blockSignals(True)
        self.text_italic_button.blockSignals(True)
        try:
            self.text_bold_button.setChecked(style_bold)
            self.text_italic_button.setChecked(style_italic)
        finally:
            self.text_bold_button.blockSignals(False)
            self.text_italic_button.blockSignals(False)

    def _choose_text_style_for_emphasis(
        self,
        *,
        bold: bool,
        italic: bool,
    ) -> None:
        family = self._selected_text_font_family()
        styles = list(QFontDatabase.styles(family))
        if not styles:
            return

        current = self.text_font_style_combo.currentText()
        candidates = [
            style
            for style in styles
            if self._text_style_traits(family, style) == (bold, italic)
        ]
        if not candidates:
            return

        preferred = current if current in candidates else candidates[0]
        index = self.text_font_style_combo.findText(preferred)
        if index >= 0 and index != self.text_font_style_combo.currentIndex():
            self.text_font_style_combo.blockSignals(True)
            try:
                self.text_font_style_combo.setCurrentIndex(index)
            finally:
                self.text_font_style_combo.blockSignals(False)

    def _text_emphasis_changed(self, _checked: bool) -> None:
        if self._updating_text_controls:
            return
        self._choose_text_style_for_emphasis(
            bold=self.text_bold_button.isChecked(),
            italic=self.text_italic_button.isChecked(),
        )
        self._text_control_changed()

    def _text_style_changed(self, _style: str) -> None:
        if self._updating_text_controls:
            return
        self._set_text_emphasis_buttons_from_style()
        self._update_text_font_availability(
            self._selected_text_font_family()
        )
        self._text_control_changed()

    def _text_font_group_changed(self, base_family: str) -> None:
        if self._updating_text_controls:
            return
        self._refresh_text_font_variants(base_family)
        self._apply_text_font_selection_change()

    def _text_font_variant_changed(self, _index: int) -> None:
        if self._updating_text_controls:
            return
        self._apply_text_font_selection_change()

    def _apply_text_font_selection_change(self) -> None:
        family = self._selected_text_font_family()
        preferred_style = self.text_font_style_combo.currentText() or "Regular"
        self._refresh_text_font_styles(family, preferred_style)
        self._set_text_emphasis_buttons_from_style()
        self._update_text_font_availability(family)
        self._update_text_editor_preview(family)
        self._text_control_changed()

    def _text_layout_control_changed(self, _checked: bool) -> None:
        self._update_text_control_enablement()
        self._text_control_changed()

    def _text_geometry_control_changed(self, _index: int) -> None:
        self._update_text_control_enablement()
        self._text_control_changed()

    def _update_text_control_enablement(self) -> None:
        if not hasattr(self, "text_wrap_check"):
            return
        # Width also defines the alignment frame when wrapping is off, so it
        # remains editable at all times. Wrap only controls line breaking.
        self.text_box_width_spin.setEnabled(True)
        outline_enabled = (
            self.text_geometry_combo.currentData() == "outline"
        )
        self.text_outline_width_spin.setVisible(outline_enabled)
        self.text_outline_label.setVisible(outline_enabled)
        self.text_outline_width_spin.setEnabled(outline_enabled)
        self._update_text_cnc_hint()

    def _update_text_cnc_hint(self) -> None:
        if not hasattr(self, "text_cnc_hint"):
            return
        cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        diameter = getattr(cutter, "diameter_mm", None)
        if diameter is None:
            self.text_cnc_hint.setText(
                "Choose a cutter on Toolpaths to compare it with text geometry."
            )
            return

        diameter = float(diameter)
        if (
            self.text_geometry_combo.currentData() == "outline"
            and self.text_outline_width_spin.value() < diameter
        ):
            self.text_cnc_hint.setText(
                f"Machining warning: {self.text_outline_width_spin.value():.3f} mm "
                f"outline is narrower than the {diameter:.3f} mm active cutter. "
                "Use a smaller cutter, widen the outline, or use a V-carve strategy."
            )
            return

        self.text_cnc_hint.setText(
            f"Active cutter: {diameter:.3f} mm. Fine glyph details may require "
            "a smaller cutter or V-carve; Preview the calculated toolpath before cutting."
        )

    def _text_control_changed(self, *_args) -> None:
        if self._updating_text_controls:
            return
        self._update_text_control_enablement()
        self._update_text_editor_preview()
        self._text_update_timer.start()

    def _text_properties_from_controls(self) -> TextProperties:
        return TextProperties(
            content=self.text_editor.toPlainText(),
            font_family=self._selected_text_font_family(),
            font_style=self.text_font_style_combo.currentText() or "Regular",
            size_pt=float(self.text_size_spin.value()),
            bold=self.text_bold_button.isChecked(),
            italic=self.text_italic_button.isChecked(),
            underline=self.text_underline_button.isChecked(),
            strikeout=self.text_strike_button.isChecked(),
            alignment=str(
                self.text_alignment_combo.currentData() or "left"
            ),
            character_spacing_mm=float(
                self.text_character_spacing_spin.value()
            ),
            word_spacing_mm=float(self.text_word_spacing_spin.value()),
            kerning=self.text_kerning_check.isChecked(),
            line_spacing_percent=float(self.text_line_spacing_spin.value()),
            horizontal_scale_percent=float(
                self.text_horizontal_scale_spin.value()
            ),
            wrap_to_width=self.text_wrap_check.isChecked(),
            box_width_mm=float(self.text_box_width_spin.value()),
            depth_mm=float(self.text_depth_spin.value()),
            geometry_mode=str(
                self.text_geometry_combo.currentData() or "filled"
            ),
            outline_width_mm=float(
                self.text_outline_width_spin.value()
            ),
            case_mode=str(self.text_case_combo.currentData() or "normal"),
        )

    def _before_text_properties_change(self, _index: int) -> None:
        """History hook supplied by project_window.MainWindow."""

    def _after_text_properties_change(self, _index: int) -> None:
        """History hook supplied by project_window.MainWindow."""

    def _apply_text_properties_from_controls(self) -> None:
        if self._updating_text_controls:
            return
        index = self._selected_item_index()
        item = self._selected_item()
        if (
            index is None
            or item is None
            or item.kind.lower() != "text"
            or item.mesh is None
        ):
            return

        properties = self._text_properties_from_controls()
        if not properties.content.strip():
            self.statusBar().showMessage(
                "Text object cannot be blank",
                3500,
            )
            return
        if item.text_properties == properties:
            return

        try:
            properties.validate()
            generated_mesh = text_mesh(properties=properties)
        except (RuntimeError, ValueError) as exc:
            self._set_activity_info(f"Text update failed\n{exc}")
            self.statusBar().showMessage(
                f"Could not update text: {exc}",
                6000,
            )
            return

        self._before_text_properties_change(index)
        item.mesh = generated_mesh
        item.text_properties = properties
        # Loaded generated objects can point at a materialized embedded STL.
        # Once edited, saving must embed the newly generated mesh instead.
        item.source_path = None
        self._invalidate_toolpaths("Text geometry")
        self._sync_transform_controls(item)
        self.selection_info.setText(self._mesh_properties_text(item))
        row = index + 1
        self.object_selector.blockSignals(True)
        try:
            self.object_selector.setItemText(
                row,
                self._object_selector_text(item),
            )
        finally:
            self.object_selector.blockSignals(False)
        list_item = self.project_list.item(row)
        if list_item is not None:
            kind = item.kind.upper()
            content_preview = " ".join(
                properties.content.splitlines()
            ).strip()
            if len(content_preview) > 90:
                content_preview = content_preview[:87].rstrip() + "…"
            list_item.setToolTip(
                f"{kind} • {item.name}"
                + (
                    f"\nContent: {content_preview}"
                    if content_preview
                    else ""
                )
                + "\nDouble-click or press F2 to rename."
            )
        self.viewport.set_selected_item(index)
        self.viewport.update()
        self._after_text_properties_change(index)
        self.statusBar().showMessage(
            f"Updated text: {item.name}",
            2500,
        )

    def _focus_text_editor(self) -> None:
        item = self._selected_item()
        if item is None or item.kind.lower() != "text":
            return
        self._ensure_inspector_visible()
        self.text_editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self.text_editor.selectAll()

    def _sync_transform_controls(self, item: ProjectItem) -> None:
        self._updating_transform_controls = True
        try:
            unit_index = self.source_units_combo.findData(item.source_units)
            if unit_index >= 0:
                self.source_units_combo.setCurrentIndex(unit_index)
            for spin, value in zip(
                self.position_spins,
                item.transform.translation_mm,
                strict=True,
            ):
                spin.setValue(value)
            for spin, value in zip(
                self.rotation_spins,
                item.transform.rotation_deg,
                strict=True,
            ):
                spin.setValue(value)
            local_size = item.local_size_mm()
            if local_size is not None:
                for spin, value in zip(
                    self.size_spins,
                    local_size,
                    strict=True,
                ):
                    spin.setValue(float(value))
            for spin, value in zip(
                self.scale_spins,
                item.transform.scale_xyz,
                strict=True,
            ):
                spin.setValue(value)
        finally:
            self._updating_transform_controls = False

    def _source_units_changed(self, _index: int) -> None:
        if self._updating_transform_controls:
            return
        item = self._selected_item()
        if item is None or item.mesh is None:
            return
        units = self.source_units_combo.currentData()
        if not isinstance(units, ModelUnits) or units is item.source_units:
            return
        item.source_units = units
        item.transform = self.project.default_transform_for_mesh(item.mesh, units)
        self._invalidate_toolpaths("Model units")
        self._refresh_project_list(self.project_list.currentRow())
        self.viewport.fit_view()
        self.statusBar().showMessage(
            f"Interpreting {item.name} as {units.display_name}; placement reset",
            5000,
        )

    def _locked_transform_axes(self) -> tuple[bool, bool, bool]:
        return tuple(
            checkbox.isChecked()
            for checkbox in self.lock_axis_checks
        )

    def _transform_control_changed(self, value: float) -> None:
        if self._updating_transform_controls:
            return

        item = self._selected_item()
        if item is None or item.mesh is None:
            return

        sender = self.sender()
        current_scale = np.asarray(item.transform.scale_xyz, dtype=float)
        new_scale = current_scale.copy()
        locked_axes = self._locked_transform_axes()

        if sender in self.size_spins:
            axis = self.size_spins.index(sender)
            current_size = item.local_size_mm()
            if current_size is None:
                return
            axis_size = float(current_size[axis])
            if axis_size <= 1e-12:
                self.statusBar().showMessage(
                    f"Cannot resize zero-length {'XYZ'[axis]} dimension",
                    3500,
                )
                self._sync_transform_controls(item)
                return

            factor = float(value) / axis_size
            affected = (
                [
                    index
                    for index, locked in enumerate(locked_axes)
                    if locked
                ]
                if locked_axes[axis]
                else [axis]
            )
            if axis not in affected:
                affected.append(axis)
            for index in affected:
                new_scale[index] = current_scale[index] * factor

        elif sender in self.scale_spins:
            axis = self.scale_spins.index(sender)
            requested_scale = float(value)
            current_axis_scale = float(current_scale[axis])
            if current_axis_scale <= 1e-12:
                return

            factor = requested_scale / current_axis_scale
            affected = (
                [
                    index
                    for index, locked in enumerate(locked_axes)
                    if locked
                ]
                if locked_axes[axis]
                else [axis]
            )
            if axis not in affected:
                affected.append(axis)
            for index in affected:
                new_scale[index] = current_scale[index] * factor

        item.transform.translation_mm = tuple(
            spin.value() for spin in self.position_spins
        )
        item.transform.rotation_deg = tuple(
            spin.value() for spin in self.rotation_spins
        )
        item.transform.scale_xyz = tuple(float(value) for value in new_scale)
        item.transform.validate()
        self._invalidate_toolpaths("Model transform")

        self._sync_transform_controls(item)
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.update()

    def _center_selected_xy(self) -> None:
        item = self._selected_item()
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return

        transformed = item.transformed_mesh()
        assert transformed is not None
        bounds = np.asarray(transformed.bounds, dtype=float)
        center = bounds.mean(axis=0)
        tx, ty, tz = item.transform.translation_mm
        item.transform.translation_mm = (
            tx + self.project.stock.width_mm / 2.0 - center[0],
            ty + self.project.stock.height_mm / 2.0 - center[1],
            tz,
        )
        self._sync_transform_controls(item)
        self._invalidate_toolpaths("Model position")
        self._update_properties(self.project_list.currentRow())
        self.viewport.update()
        self.statusBar().showMessage("Centered selected mesh on stock", 3000)

    def _top_selected_to_surface(self) -> None:
        item = self._selected_item()
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return

        transformed = item.transformed_mesh()
        assert transformed is not None
        bounds = np.asarray(transformed.bounds, dtype=float)
        tx, ty, tz = item.transform.translation_mm
        item.transform.translation_mm = (tx, ty, tz - bounds[1, 2])
        self._sync_transform_controls(item)
        self._invalidate_toolpaths("Model position")
        self._update_properties(self.project_list.currentRow())
        self.viewport.update()
        self.statusBar().showMessage("Placed selected mesh top at stock Z0", 3000)

    def _reset_selected_transform(self) -> None:
        item = self._selected_item()
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return

        item.transform = self.project.default_transform_for_mesh(
            item.mesh,
            item.source_units,
        )
        self._sync_transform_controls(item)
        self._invalidate_toolpaths("Model transform")
        self._update_properties(self.project_list.currentRow())
        self.viewport.update()
        self.statusBar().showMessage("Reset selected mesh transform", 3000)

    def _duplicate_selected_item(self) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if not indices:
            self.statusBar().showMessage("Select one or more design objects", 3000)
            return

        group_map: dict[str, str] = {}
        duplicates: list[ProjectItem] = []
        for index in indices:
            source = self.project.items[index]
            source_path = Path(source.name)
            duplicate_name = self._unique_item_name(
                f"{source_path.stem} copy{source_path.suffix}"
            )
            group_id = None
            if source.group_id:
                group_id = group_map.setdefault(
                    source.group_id,
                    uuid4().hex,
                )
            duplicates.append(
                self._clone_item(
                    source,
                    name=duplicate_name,
                    group_id=group_id,
                    offset_mm=(5.0, 5.0, 0.0),
                )
            )

        first_new_index = len(self.project.items)
        self.project.items.extend(duplicates)
        self._invalidate_toolpaths("Project geometry")
        duplicate_indices = list(
            range(first_new_index, first_new_index + len(duplicates))
        )
        self._refresh_project_list(len(self.project.items))
        self._select_project_indices(
            duplicate_indices,
            primary=duplicate_indices[-1],
        )
        self.viewport.update()

        if len(duplicates) == 1:
            message = f"Duplicated {duplicates[0].name} • offset 5 mm"
        else:
            message = f"Duplicated {len(duplicates)} objects • offset 5 mm"
        self.statusBar().showMessage(message, 3000)

    def _delete_selected_item(self) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if not indices:
            self.statusBar().showMessage("Select one or more design objects", 3000)
            return

        removed_names = [
            self.project.items[index].name
            for index in indices
        ]
        for index in reversed(indices):
            self.project.remove_item(index)

        self._invalidate_toolpaths("Project geometry")
        next_row = min(indices[0] + 1, len(self.project.items))
        self._refresh_project_list(next_row)
        self.viewport.update()

        if len(removed_names) == 1:
            message = f"Deleted {removed_names[0]}"
        else:
            message = f"Deleted {len(removed_names)} objects"
        self.statusBar().showMessage(message, 3000)

    def _move_selected_item(self, offset: int) -> None:
        index = self._selected_item_index()
        if index is None:
            self.statusBar().showMessage("Select a design item to reorder", 3000)
            return
        new_index = self.project.move_item(index, offset)
        self._refresh_project_list(new_index + 1)
        self.viewport.update()

    def _focus_transform_controls(self) -> None:
        item = self._selected_item()
        if item is None or item.mesh is None:
            self.statusBar().showMessage("Select a model or shape first", 3000)
            return
        self.position_spins[0].setFocus()

    def _fit_view(self) -> None:
        self.viewport.fit_view()

    def _install_shortcuts(self) -> None:
        """Install predictable desktop shortcuts for frequent workspace actions."""

        bindings = (
            ("New Project", QKeySequence.StandardKey.New, self._new_project),
            ("Open Project", QKeySequence.StandardKey.Open, self._open_project),
            ("Save Project", QKeySequence.StandardKey.Save, self._save_project),
            ("Save Project As", "Ctrl+Shift+S", self._save_project_as),
            ("Undo", QKeySequence.StandardKey.Undo, self._undo),
            ("Redo", QKeySequence.StandardKey.Redo, self._redo),
            ("Cut", QKeySequence.StandardKey.Cut, self._cut_selected_items),
            ("Copy", QKeySequence.StandardKey.Copy, self._copy_selected_items),
            ("Paste", QKeySequence.StandardKey.Paste, self._paste_items),
            ("Select All", QKeySequence.StandardKey.SelectAll, self._select_all_design_items),
            ("Delete", QKeySequence(Qt.Key.Key_Delete), self._delete_selected_item),
            ("Duplicate", "Ctrl+D", self._duplicate_selected_item),
            ("Layers", "Ctrl+Shift+L", self._show_layers_popup),
            ("Inspector", "Ctrl+Shift+I", self._toggle_properties_panel_option),
            ("Select Tool", "V", self._activate_navigation_tool),
            ("Select / Cancel Tool", "Escape", self._cancel_active_tool),
            ("Fit View", "Ctrl+0", self._fit_view),
        )

        self._shortcut_actions: list[QAction] = []
        for title, shortcut, callback in bindings:
            action = QAction(title, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(
                lambda _checked=False, fn=callback: fn()
            )
            self.addAction(action)
            self._shortcut_actions.append(action)

    def _set_option_checked(self, key: str, checked: bool) -> None:
        button = self._option_buttons.get(key)
        if button is not None:
            button.setChecked(bool(checked))

    def _settings_bool(self, key: str, default: bool) -> bool:
        return bool(self._settings.value(key, default, type=bool))

    def _restore_options(self) -> None:
        if self._settings.contains("interface/inspector_visible"):
            inspector_visible = self._settings_bool(
                "interface/inspector_visible",
                True,
            )
        else:
            inspector_visible = self._settings_bool(
                "interface/properties_panel_visible",
                True,
            )

        status_bar_visible = self._settings_bool(
            "interface/status_bar_visible",
            True,
        )
        view_controls_visible = self._settings_bool(
            "interface/view_controls_visible",
            True,
        )
        stock_visible = self._settings_bool("viewport/show_stock", True)
        grid_visible = self._settings_bool("viewport/show_grid", True)
        rulers_visible = self._settings_bool("viewport/show_rulers", True)
        reverse_horizontal = self._settings_bool(
            "viewport/reverse_horizontal_navigation",
            False,
        )
        invert_vertical = self._settings_bool(
            "viewport/invert_vertical_navigation",
            False,
        )

        self.properties_panel.setVisible(inspector_visible)
        self.inspector_button.setChecked(inspector_visible)
        if hasattr(self, "tool_rail"):
            rail_button = self.tool_rail.buttons.get("inspector")
            if rail_button is not None:
                rail_button.setChecked(inspector_visible)
        self.statusBar().setVisible(status_bar_visible)
        self.viewport.set_view_controls_visible(view_controls_visible)
        self.viewport.show_stock = stock_visible
        self.viewport.show_grid = grid_visible
        self.viewport.set_rulers_visible(rulers_visible)
        self.viewport.set_reverse_horizontal_drag(reverse_horizontal)
        self.viewport.set_invert_vertical_drag(invert_vertical)

        stored_sizes = self._settings.value("interface/splitter_sizes")
        restored_splitter = False
        if isinstance(stored_sizes, list):
            try:
                sizes = [max(0, int(value)) for value in stored_sizes]
            except (TypeError, ValueError):
                sizes = []

            if len(sizes) == 2 and sum(sizes) > 0:
                self.workspace_splitter.setSizes(sizes)
                restored_splitter = True
            elif len(sizes) == 3 and sum(sizes) > 0:
                # Migrate the old Project | Canvas | Properties splitter.
                self.workspace_splitter.setSizes(
                    [sizes[0] + sizes[1], sizes[2]]
                )
                restored_splitter = True

        if not restored_splitter:
            self.workspace_splitter.setSizes(
                self._default_workspace_splitter_sizes()
            )

        projection = str(
            self._settings.value("viewport/projection_mode", "perspective")
        ).lower()
        view_name = str(self._settings.value("viewport/view_name", "Top"))
        standard_views = {"Top", "Bottom", "Front", "Back", "Left", "Right"}
        if view_name == "Isometric":
            self.viewport.set_isometric_view()
        elif view_name in standard_views:
            self.viewport.set_standard_view(
                view_name,
                projection_mode=(
                    "perspective"
                    if projection == "perspective"
                    else "orthographic"
                ),
            )
        elif projection == "perspective":
            self.viewport.set_perspective_view()
        else:
            self.viewport.set_orthographic_view()

        self._set_option_checked("properties_panel", inspector_visible)
        self._set_option_checked("status_bar", status_bar_visible)
        self._set_option_checked("view_controls", view_controls_visible)
        self._set_option_checked("stock", stock_visible)
        self._set_option_checked("grid", grid_visible)
        self._set_option_checked("rulers", rulers_visible)
        self._set_option_checked("reverse_horizontal", reverse_horizontal)
        self._set_option_checked("invert_vertical", invert_vertical)
        self.viewport.update()

    def _save_viewport_mode(self) -> None:
        self._settings.setValue(
            "viewport/projection_mode",
            self.viewport.projection_mode,
        )
        self._settings.setValue("viewport/view_name", self.viewport.view_name)

    def _save_interface_options(self) -> None:
        self._settings.setValue(
            "interface/inspector_visible",
            self.properties_panel.isVisible(),
        )
        self._settings.setValue(
            "interface/status_bar_visible",
            self.statusBar().isVisible(),
        )
        self._settings.setValue(
            "interface/view_controls_visible",
            self.viewport.view_controls_visible,
        )
        self._settings.setValue(
            "interface/splitter_sizes",
            self.workspace_splitter.sizes(),
        )
        self._settings.setValue("viewport/show_stock", self.viewport.show_stock)
        self._settings.setValue("viewport/show_grid", self.viewport.show_grid)
        self._settings.setValue("viewport/show_rulers", self.viewport.rulers_visible)
        self._settings.setValue(
            "viewport/reverse_horizontal_navigation",
            self.viewport.reverse_horizontal_drag,
        )
        self._settings.setValue(
            "viewport/invert_vertical_navigation",
            self.viewport.invert_vertical_drag,
        )
        self._settings.remove("interface/project_panel_visible")
        self._settings.remove("interface/properties_panel_visible")
        self._settings.remove("viewport/reverse_horizontal_drag")
        self._save_viewport_mode()
        self._settings.sync()

    def _toggle_project_panel_option(self) -> None:
        """Compatibility alias: the former project pane is now the Layers popup."""

        self._show_layers_popup()

    def _toggle_properties_panel_option(self) -> None:
        visible = not self.properties_panel.isVisible()
        self.properties_panel.setVisible(visible)
        self.inspector_button.setChecked(visible)
        if hasattr(self, "tool_rail"):
            rail_button = self.tool_rail.buttons.get("inspector")
            if rail_button is not None:
                rail_button.setChecked(visible)
        self._set_option_checked("properties_panel", visible)

        if visible:
            sizes = self.workspace_splitter.sizes()
            if len(sizes) == 2 and sizes[1] < 40:
                preferred = self._properties_panel_default_width()
                total = max(sum(sizes), preferred + 520)
                self.workspace_splitter.setSizes(
                    [max(520, total - preferred), preferred]
                )

        self._save_interface_options()

    def _toggle_status_bar_option(self) -> None:
        visible = not self.statusBar().isVisible()
        self.statusBar().setVisible(visible)
        self._set_option_checked("status_bar", visible)
        self._save_interface_options()

    def _toggle_view_controls_option(self) -> None:
        visible = not self.viewport.view_controls_visible
        self.viewport.set_view_controls_visible(visible)
        self._set_option_checked("view_controls", visible)
        self._save_interface_options()
        self.statusBar().showMessage(
            f"Viewport controls {'shown' if visible else 'hidden'}",
            2000,
        )

    def _toggle_reverse_horizontal_option(self) -> None:
        enabled = not self.viewport.reverse_horizontal_drag
        self.viewport.set_reverse_horizontal_drag(enabled)
        self._set_option_checked("reverse_horizontal", enabled)
        self._save_interface_options()
        state = "reversed" if enabled else "standard"
        self.statusBar().showMessage(
            f"Horizontal pan + orbit: {state}",
            2500,
        )

    def _toggle_invert_vertical_option(self) -> None:
        enabled = not self.viewport.invert_vertical_drag
        self.viewport.set_invert_vertical_drag(enabled)
        self._set_option_checked("invert_vertical", enabled)
        self._save_interface_options()
        state = "inverted" if enabled else "standard"
        self.statusBar().showMessage(
            f"Vertical pan + orbit: {state}",
            2500,
        )

    def _toggle_stock(self) -> None:
        self.viewport.toggle_stock()
        self._set_option_checked("stock", self.viewport.show_stock)
        self._save_interface_options()
        state = "shown" if self.viewport.show_stock else "hidden"
        self.statusBar().showMessage(f"Stock {state}", 2000)

    def _toggle_grid(self) -> None:
        self.viewport.toggle_grid()
        self._set_option_checked("grid", self.viewport.show_grid)
        self._save_interface_options()
        state = "shown" if self.viewport.show_grid else "hidden"
        self.statusBar().showMessage(f"Grid {state}", 2000)

    def _toggle_rulers(self) -> None:
        visible = not self.viewport.rulers_visible
        self.viewport.set_rulers_visible(visible)
        self._set_option_checked("rulers", visible)
        self._save_interface_options()
        state = "shown" if visible else "hidden"
        self.statusBar().showMessage(f"Viewport rulers {state}", 2000)

    def _set_perspective_option(self) -> None:
        self.viewport.set_perspective_view()
        self.statusBar().showMessage("Perspective projection", 2000)

    def _set_orthographic_option(self) -> None:
        self.viewport.set_orthographic_view()
        self.statusBar().showMessage("Orthographic projection", 2000)

    def _set_isometric_option(self) -> None:
        self.viewport.set_isometric_view()
        self.statusBar().showMessage("Isometric view", 2000)

    def _set_standard_view_option(self, name: str) -> None:
        self.viewport.set_standard_view(name)
        self.statusBar().showMessage(f"{name} view", 2000)

    def _reset_interface_options(self) -> None:
        self._settings.remove("interface")
        self._settings.remove("viewport")

        self.layers_popup.hide()
        self.properties_panel.show()
        self.inspector_button.setChecked(True)
        self.statusBar().show()
        self.workspace_splitter.setSizes(
            self._default_workspace_splitter_sizes()
        )

        self.viewport.set_view_controls_visible(True)
        self.viewport.show_stock = True
        self.viewport.show_grid = True
        self.viewport.set_rulers_visible(True)
        self.viewport.set_reverse_horizontal_drag(False)
        self.viewport.set_invert_vertical_drag(False)
        self.viewport.set_default_view()

        for key in (
            "properties_panel",
            "status_bar",
            "view_controls",
            "stock",
            "grid",
            "rulers",
        ):
            self._set_option_checked(key, True)
        self._set_option_checked("reverse_horizontal", False)
        self._set_option_checked("invert_vertical", False)

        self.viewport.update()
        self._save_interface_options()
        self.statusBar().showMessage("Workspace layout reset", 3000)

    def _set_project(
        self,
        project: Project,
        *,
        project_path: Path | None,
        selected_row: int = 0,
    ) -> None:
        self.project = project
        self.project_path = project_path
        self._toolpaths_stale_reason = None
        self.project_title_label.setText(f"  •  {project.name} Project")
        self.viewport.set_project(project)
        self._refresh_project_list(selected_row)
        self._sync_toolpath_state_from_project()

    def _undo(self) -> None:
        self.statusBar().showMessage("Nothing to undo", 3000)

    def _new_project(self) -> None:
        self._set_project(Project(), project_path=None)
        self.statusBar().showMessage("New project created", 3000)

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open CarveFoundry Project",
            str(self.project_path.parent if self.project_path else Path.home()),
            f"CarveFoundry Projects (*{PROJECT_SUFFIX});;All files (*)",
        )
        if not path:
            return
        project_path = Path(path)
        try:
            project = load_project(project_path)
        except ProjectFileError as exc:
            self._set_activity_info(f"Project open failed\n{exc}")
            self.statusBar().showMessage(f"Could not open project: {exc}", 8000)
            return
        self._set_project(project, project_path=project_path)
        self.statusBar().showMessage(f"Opened {project_path.name}", 5000)

    def _save_project(self) -> None:
        if self.project_path is None:
            self._save_project_as()
            return
        self._save_project_to(self.project_path)

    def _save_project_as(self) -> None:
        suggested = (
            self.project_path
            if self.project_path is not None
            else Path.home() / f"{self.project.name}{PROJECT_SUFFIX}"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CarveFoundry Project",
            str(suggested),
            f"CarveFoundry Projects (*{PROJECT_SUFFIX})",
        )
        if not path:
            return
        self._save_project_to(Path(path))

    def _save_project_to(self, path: Path) -> None:
        if self.project.name == "Untitled":
            self.project.name = path.stem
        try:
            saved_path = save_project(self.project, path)
        except ProjectFileError as exc:
            self._set_activity_info(f"Project save failed\n{exc}")
            self.statusBar().showMessage(f"Could not save project: {exc}", 8000)
            return
        self.project_path = saved_path
        self.project_title_label.setText(f"  •  {self.project.name} Project")
        self.statusBar().showMessage(f"Saved {saved_path.name}", 5000)

    def _export_gcode(self) -> None:
        toolpaths = self.project.toolpaths
        if not toolpaths:
            self._set_activity_info(
                "No calculated toolpaths to export.\n\n"
                "Calculate a toolpath first, then return to Export G-code."
            )
            self.statusBar().showMessage("No calculated toolpaths to export", 5000)
            return

        toolpath = toolpaths[0]
        base_directory = self.project_path.parent if self.project_path else Path.home()
        project_name = self.project.name if self.project.name != "Untitled" else toolpath.name
        suggested = base_directory / f"{project_name}.nc"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export G-code",
            str(suggested),
            "G-code (*.nc *.gcode *.tap *.cnc);;All files (*)",
        )
        if not path:
            self.statusBar().showMessage("G-code export canceled", 3000)
            return

        try:
            if len(toolpaths) == 1:
                output_path = write_grbl(
                    toolpath,
                    Path(path),
                    self._grbl_post_settings(),
                )
            else:
                output_path = write_grbl_program(
                    toolpaths,
                    Path(path),
                    self._grbl_post_settings(),
                )
        except (OSError, ValueError) as exc:
            self._set_activity_info(f"G-code export failed\n{exc}")
            self.statusBar().showMessage(f"Could not export G-code: {exc}", 8000)
            return

        total_moves = sum(len(path.moves) for path in toolpaths)
        total_minutes = sum(
            path.estimated_cutting_minutes for path in toolpaths
        )
        operation_names = " + ".join(path.name for path in toolpaths)
        source_names = self._toolpath_source_names(toolpaths)
        source_text = ", ".join(source_names) if source_names else "Unknown"
        self._set_activity_info(
            f"G-code exported\n{output_path}\n\n"
            f"Operations: {operation_names}\n"
            f"Source: {source_text}\n"
            f"Cutter: {toolpath.cutter.name}\n"
            f"Moves: {total_moves:,}\n"
            f"Estimated cutting time: {total_minutes:.1f} min "
            "(rapids excluded)"
        )
        self.statusBar().showMessage(f"Exported {output_path.name}", 5000)

    def _import_file(self, kind: str | None = None) -> None:
        if self._import_thread is not None and self._import_thread.isRunning():
            self.statusBar().showMessage("An import is already in progress", 3000)
            return

        filters = {
            "SVG": "SVG files (*.svg)",
            "DXF": "DXF files (*.dxf)",
            "STL": "STL files (*.stl)",
            "Image": "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
            "G-code": "G-code (*.nc *.gcode *.tap *.cnc)",
        }
        selected_filter = filters.get(
            kind,
            "Supported designs (*.stl *.svg *.dxf *.png *.jpg *.jpeg *.bmp *.webp "
            "*.nc *.gcode *.tap *.cnc);;All files (*)",
        )

        if kind is None:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                "Import Design Files",
                str(Path.home()),
                selected_filter,
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                f"Import {kind}",
                str(Path.home()),
                selected_filter,
            )
            paths = [path] if path else []

        if not paths:
            self.statusBar().showMessage("Import canceled", 3000)
            return

        self._start_import(paths, kind)

    def _start_import(self, paths: list[str], kind: str | None) -> None:
        thread = QThread(self)
        worker = ImportWorker(paths, kind)
        worker.moveToThread(thread)

        self._import_thread = thread
        self._import_worker = worker
        self._import_target_project = self.project

        thread.started.connect(worker.run)
        worker.progress.connect(self._import_progress_changed)
        worker.finished.connect(self._import_completed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(self._import_failed)
        worker.failed.connect(thread.quit)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._import_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self.import_progress.setRange(0, 0)
        self.import_progress.show()
        self.statusBar().showMessage("Loading design…")
        thread.start()

    def _import_progress_changed(self, index: int, total: int, name: str) -> None:
        if total <= 1:
            self.import_progress.setRange(0, 0)
        else:
            self.import_progress.setRange(0, total)
            self.import_progress.setValue(max(0, index - 1))
        self.statusBar().showMessage(f"Loading {name} ({index}/{total})…")

    def _import_completed(self, infos: object, failures: object) -> None:
        if self.project is not self._import_target_project:
            self._set_activity_info(
                "Import finished, but the active project changed while it was loading.\n\n"
                "The loaded data was not added to the new project."
            )
            self.statusBar().showMessage("Import result discarded — project changed", 6000)
            return

        prepared_list = list(infos)
        failure_list = list(failures)
        if prepared_list:
            self._before_import_items_added(len(prepared_list))

        imported: list[ProjectItem] = []
        source_only_count = 0

        for prepared in prepared_list:
            info = prepared.info
            mesh = info.mesh
            if mesh is None:
                item = ProjectItem(info.path.name, info.path, info.kind)
                source_only_count += 1
            else:
                source_units = ModelUnits.from_metadata(mesh.units)
                transform = self.project.default_transform_for_mesh(mesh, source_units)
                item = ProjectItem(
                    info.path.name,
                    info.path,
                    info.kind,
                    mesh=mesh,
                    transform=transform,
                    source_units=source_units,
                )
                if prepared.gpu_vertex_bytes is not None:
                    self.viewport.prepare_mesh_upload(
                        mesh.mesh,
                        prepared.gpu_vertex_bytes,
                        prepared.gpu_vertex_count,
                    )
            self.project.items.append(item)
            imported.append(item)

        if imported:
            self._invalidate_toolpaths("Project geometry")
            self._refresh_project_list(len(self.project.items))
            if any(item.mesh is not None for item in imported):
                self.viewport.fit_view()
            self._on_import_items_added(len(imported))

        if failure_list:
            failure_text = "\n".join(failure_list[:8])
            if len(failure_list) > 8:
                failure_text += f"\n… and {len(failure_list) - 8} more"
            self._set_activity_info(
                f"Import completed with {len(failure_list)} failure(s)\n\n{failure_text}"
            )

        if imported and failure_list:
            self.statusBar().showMessage(
                f"Imported {len(imported)} file(s); {len(failure_list)} failed",
                8000,
            )
        elif imported:
            message = f"Imported {len(imported)} file(s)"
            if source_only_count:
                message += (
                    f" — {source_only_count} stored as project source asset(s) "
                    "pending dedicated editor support"
                )
            self.statusBar().showMessage(message, 6000)
        else:
            self.statusBar().showMessage(
                f"Import failed for {len(failure_list)} file(s)",
                8000,
            )

    def _before_import_items_added(self, count: int) -> None:
        del count

    def _on_import_items_added(self, count: int) -> None:
        del count

    def _import_failed(self, message: str) -> None:
        self._set_activity_info(f"Import failed\n{message}")
        self.statusBar().showMessage(f"Import failed: {message}", 8000)

    def _import_thread_finished(self) -> None:
        self.import_progress.hide()
        self._import_worker = None
        self._import_thread = None
        self._import_target_project = None

    def closeEvent(self, event) -> None:
        if self._import_thread is not None and self._import_thread.isRunning():
            self.statusBar().showMessage(
                "Please wait for the current import to finish before closing",
                5000,
            )
            event.ignore()
            return
        self._simulation_timer.stop()
        if self.machine_controller.connected:
            self.machine_controller.disconnect()
        self._save_interface_options()
        super().closeEvent(event)

