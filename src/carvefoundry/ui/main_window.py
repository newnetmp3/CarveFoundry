from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6.QtCore import QSettings, Qt, QThread
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..cam.gcode import write_grbl, write_grbl_program
from ..core.project import Project, ProjectItem
from ..core.project_file import (
    PROJECT_SUFFIX,
    ProjectFileError,
    load_project,
    save_project,
)
from ..core.units import ModelUnits
from .import_worker import ImportWorker
from .layers_popup import LayersPopup
from .ribbon import Ribbon
from .ribbon_actions import RibbonActionsMixin
from .viewport import MeshViewport


class Panel(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("WorkspacePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QLabel(title)
        self.header.setObjectName("PanelHeader")
        self.header.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(self.header)

        self.body = QWidget()
        self.body.setObjectName("InspectorBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 8, 8, 8)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("InspectorScrollArea")
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setWidget(self.body)
        layout.addWidget(self.scroll_area, 1)


class MainWindow(RibbonActionsMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.project_path: Path | None = None
        self._updating_transform_controls = False
        self._updating_stock_controls = False
        self._updating_project_list = False
        self._updating_object_selector = False
        self._import_thread: QThread | None = None
        self._import_worker: ImportWorker | None = None
        self._import_target_project: Project | None = None
        self._settings = QSettings()
        self._option_buttons: dict[str, object] = {}
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
        self.ribbon = Ribbon()
        self._populate_ribbon()
        self.ribbon.currentChanged.connect(self._ribbon_tab_changed)
        layout.addWidget(self.ribbon)
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
        self.viewport.itemSelectionRequested.connect(self._viewport_select_item)
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
        self.viewport.shapeDrawModeChanged.connect(
            self._shape_draw_mode_changed
        )
        self._restore_options()

    def _build_brand_row(self) -> QWidget:
        row = QWidget()
        row.setObjectName("TitleBar")
        row.setFixedHeight(42)
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
        output.add_button("Export G-code", self._export_gcode)

        # DESIGN: geometry creation, editing, arrangement, and object management.
        design = self.ribbon.add_page("Design")
        edit = design.add_group("Edit")
        edit.add_button("Undo", self._undo)
        edit.add_button("Redo", self._redo)
        edit.add_button("Cut", self._cut_selected_items)
        edit.add_button("Copy", self._copy_selected_items)
        edit.add_button("Paste", self._paste_items)
        edit.add_button("Delete", self._delete_selected_item)

        shapes = design.add_group("Draw")
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
                "Hold Shift to constrain. Press Esc to exit the tool."
            )
            self._shape_tool_buttons[tool] = button

        vectors = design.add_group("Vector")
        vectors.add_button("Pen", self._create_pen_path)
        vectors.add_button("Trace Image", self._trace_image)

        arrange = design.add_group("Arrange")
        arrange.add_button("Align", self._align_selected_items)
        arrange.add_button("Center", self._center_selected_items)
        arrange.add_button("Group", self._group_selected_items)
        arrange.add_button("Ungroup", self._ungroup_selected_items)
        arrange.add_button("Duplicate", self._duplicate_selected_item)

        objects = design.add_group("Objects")
        objects.add_button("Layers", self._show_layers_popup, primary=True)
        objects.add_button("Move Up", lambda: self._move_selected_item(-1))
        objects.add_button("Move Down", lambda: self._move_selected_item(1))

        # MODEL: stock-relative placement and object transforms.
        model = self.ribbon.add_page("Model")
        stock = model.add_group("Stock")
        stock.add_button("Stock Setup", self._focus_stock_section, primary=True)
        stock.add_button("Fit View", self._fit_view)

        transform = model.add_group("Transform")
        transform.add_button(
            "Position",
            lambda: self._focus_transform_section("position"),
        )
        transform.add_button(
            "Rotate",
            lambda: self._focus_transform_section("rotation"),
        )
        transform.add_button(
            "Size",
            lambda: self._focus_transform_section("size"),
            primary=True,
        )
        transform.add_button(
            "Scale",
            lambda: self._focus_transform_section("scale"),
        )

        placement = model.add_group("Placement")
        placement.add_button("Center XY", self._center_selected_xy)
        placement.add_button("Top to Z0", self._top_selected_to_surface)
        placement.add_button("Fit Stock", self._fit_selected_inside_stock)
        placement.add_button("Reset", self._reset_selected_transform)

        # TOOLPATHS: all CAM work lives in one workflow tab.
        toolpaths = self.ribbon.add_page("Toolpaths")
        operations_2d = toolpaths.add_group("2D / 2.5D")
        self._cam_operation_buttons: dict[str, object] = {}
        for operation, title in (
            ("profile", "Profile"),
            ("pocket", "Pocket"),
            ("vcarve", "V-Carve"),
            ("engrave", "Engrave"),
            ("drill", "Drill"),
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
        generate.add_button("Calculate", self._calculate_toolpath, primary=True)
        generate.add_button("Preview", self._preview_toolpaths)
        self._simulation_button = generate.add_button(
            "Simulate",
            self._simulate_toolpaths,
        )
        self._simulation_button.setCheckable(True)
        generate.add_button("Export G-code", self._export_gcode)

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
        self._rapids_view_button = display.add_button(
            "Rapids",
            self._toggle_rapids_view,
        )
        self._rapids_view_button.setCheckable(True)

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

    def _build_workspace(self) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(8, 8, 8, 8)

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
        canvas_bar_layout.setContentsMargins(10, 6, 10, 6)
        canvas_bar_layout.setSpacing(7)

        canvas_bar_layout.addWidget(QLabel("Object"))
        self.object_selector = QComboBox()
        self.object_selector.setObjectName("ObjectSelector")
        self.object_selector.setMinimumWidth(230)
        self.object_selector.setMaximumWidth(420)
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

        self.viewport = MeshViewport(self.project)
        canvas_layout.addWidget(self.viewport, 1)

        self.properties_panel = Panel("Inspector")
        self.properties_panel.setObjectName("InspectorPanel")
        self.selection_info = QLabel()
        self.selection_info.setWordWrap(True)
        self.selection_info.setObjectName("InspectorSummary")
        self.properties_panel.body_layout.addWidget(self.selection_info)

        self.stock_widget = self._build_stock_controls()
        self.properties_panel.body_layout.addWidget(self.stock_widget)

        self.transform_widget = self._build_transform_controls()
        self.properties_panel.body_layout.addWidget(self.transform_widget)

        inspector_hint = QLabel(
            "Cutter selection and CAM settings are grouped on the Toolpaths ribbon."
        )
        inspector_hint.setWordWrap(True)
        inspector_hint.setObjectName("Muted")
        self.properties_panel.body_layout.addWidget(inspector_hint)
        self.properties_panel.body_layout.addStretch(1)

        self.project_list.currentRowChanged.connect(self._update_properties)
        self.project_list.itemChanged.connect(self._project_item_changed)
        self._refresh_project_list(0)

        splitter.addWidget(canvas)
        splitter.addWidget(self.properties_panel)
        splitter.setSizes(self._default_workspace_splitter_sizes(1500))
        splitter.setStretchFactor(0, 1)
        layout.addWidget(splitter)
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
            self.transform_widget.sizeHint().width(),
        )
        return max(330, min(430, content_width + outer_padding))

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
        return spin

    def _build_stock_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("StockControls")
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 6, 0, 10)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)

        heading = QLabel("Stock dimensions")
        heading.setObjectName("SectionHeading")
        grid.addWidget(heading, 0, 0, 1, 2)

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
        for row, (title, spin) in enumerate(
            zip(("Width", "Height", "Thickness"), self.stock_spins, strict=True),
            start=1,
        ):
            grid.addWidget(QLabel(title), row, 0)
            grid.addWidget(spin, row, 1)
            spin.valueChanged.connect(self._stock_control_changed)

        return widget

    def _build_transform_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("TransformControls")
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 6, 0, 10)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)

        heading = QLabel("Model transform")
        heading.setObjectName("SectionHeading")
        grid.addWidget(heading, 0, 0, 1, 4)

        grid.addWidget(QLabel("Model units"), 1, 0)
        self.source_units_combo = QComboBox()
        for units in ModelUnits:
            self.source_units_combo.addItem(units.display_name, units)
        self.source_units_combo.currentIndexChanged.connect(self._source_units_changed)
        grid.addWidget(self.source_units_combo, 1, 1, 1, 3)

        grid.addWidget(QLabel(""), 2, 0)
        for column, axis in enumerate(("X", "Y", "Z"), start=1):
            label = QLabel(axis)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setObjectName("Muted")
            grid.addWidget(label, 2, column)

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

        for row, (title, spins) in enumerate(
            (
                ("Position", self.position_spins),
                ("Rotate about", self.rotation_spins),
                ("Size", self.size_spins),
                ("Scale", self.scale_spins),
            ),
            start=3,
        ):
            grid.addWidget(QLabel(title), row, 0)
            for column, spin in enumerate(spins, start=1):
                grid.addWidget(spin, row, column)
                spin.valueChanged.connect(self._transform_control_changed)

        rotation_note = QLabel(
            "Rotation axes: X → YZ plane   Y → XZ plane   Z → XY plane"
        )
        rotation_note.setObjectName("Muted")
        rotation_note.setWordWrap(True)
        rotation_note.setToolTip(
            "X/Y/Z name the axis being rotated around, not the plane being rotated."
        )
        grid.addWidget(rotation_note, 7, 0, 1, 4)

        grid.addWidget(QLabel("Lock axes"), 8, 0)
        self.lock_axis_checks = tuple(
            QCheckBox(axis)
            for axis in ("X", "Y", "Z")
        )
        for column, checkbox in enumerate(self.lock_axis_checks, start=1):
            checkbox.setChecked(True)
            checkbox.setToolTip(
                "Locked axes resize proportionally together when Size or Scale changes."
            )
            grid.addWidget(checkbox, 8, column)

        center_button = QPushButton("Center XY")
        center_button.clicked.connect(self._center_selected_xy)
        grid.addWidget(center_button, 9, 0, 1, 2)

        top_button = QPushButton("Top to Z0")
        top_button.clicked.connect(self._top_selected_to_surface)
        grid.addWidget(top_button, 9, 2, 1, 2)

        reset_button = QPushButton("Reset Transform")
        reset_button.clicked.connect(self._reset_selected_transform)
        grid.addWidget(reset_button, 10, 0, 1, 4)

        widget.setVisible(False)
        return widget

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

        return (
            f"{item.name}\n"
            f"{kind} • {mesh.face_count:,} faces{group}\n\n"
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
        group = "  • grouped" if item.group_id else ""
        kind = "STL" if item.kind.lower() == "stl" else item.kind.upper()
        return f"{kind}  {item.name}{group}"

    @staticmethod
    def _object_selector_text(item: ProjectItem) -> str:
        group = " • Grouped" if item.group_id else ""
        kind = "STL" if item.kind.lower() == "stl" else item.kind.upper()
        return f"{item.name}  [{kind}]{group}"

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
                list_item.setToolTip(
                    f"{project_item.name}\n"
                    f"Source size: {self._source_dimensions_text(project_item)}"
                )
                list_item.setFlags(
                    list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable
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
        row_changed = self.project_list.currentRow() != row
        self.project_list.clearSelection()
        self.project_list.setCurrentRow(row)
        item = self.project_list.item(row)
        if item is not None:
            item.setSelected(True)
        if not row_changed:
            self._update_properties(row)

    def _show_layers_popup(self) -> None:
        if not hasattr(self, "layers_popup"):
            return
        self.layers_popup.show_below(self.layers_button)

    def _active_cutter_changed(self, _index: int) -> None:
        cutter = self.tool_combo.currentData()
        if cutter is not None and hasattr(cutter, "name"):
            self._settings.setValue("tools/selected_name", cutter.name)
            self._settings.sync()
        self._refresh_cam_detail_readouts()

    def _ensure_inspector_visible(self) -> None:
        self.properties_panel.show()
        self.inspector_button.setChecked(True)
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
        visible = list_item.checkState() == Qt.CheckState.Checked
        self.project.items[index].visible = visible
        self.viewport.update()
        state = "visible" if visible else "hidden"
        self.statusBar().showMessage(f"{self.project.items[index].name} {state}", 2000)

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
        if self.project_list.count():
            self.project_list.item(0).setText(self._stock_list_text())
        self.selection_info.setText(
            "Stock\n"
            f"{self._number(width)} × {self._number(height)} × "
            f"{self._number(thickness)} mm"
        )
        self.viewport.update()

    def _viewport_select_item(self, index: int) -> None:
        """Synchronize a viewport click with the Project/Layers selection."""

        row = index + 1 if 0 <= index < len(self.project.items) else 0
        row_changed = self.project_list.currentRow() != row
        self.project_list.clearSelection()
        self.project_list.setCurrentRow(row)
        item = self.project_list.item(row)
        if item is not None:
            item.setSelected(True)
        if not row_changed:
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
        if 0 <= index < len(self.project.items):
            item = self.project.items[index]
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

        if row <= 0:
            stock = self.project.stock
            self.selection_info.setText(
                "Stock\n"
                f"{self._number(stock.width_mm)} × {self._number(stock.height_mm)} × "
                f"{self._number(stock.thickness_mm)} mm"
            )
            self._sync_stock_controls()
            self.stock_widget.setVisible(True)
            self.transform_widget.setVisible(False)
            self.viewport.set_selected_item(None)
            self._refresh_cam_detail_readouts()
            return

        item_index = row - 1
        if item_index >= len(self.project.items):
            self.selection_info.setText("No design selected")
            self.stock_widget.setVisible(False)
            self.transform_widget.setVisible(False)
            self.viewport.set_selected_item(None)
            self._refresh_cam_detail_readouts()
            return

        item = self.project.items[item_index]
        self.selection_info.setText(self._mesh_properties_text(item))
        self.viewport.set_selected_item(item_index)
        self.stock_widget.setVisible(False)
        has_mesh = item.mesh is not None
        self.transform_widget.setVisible(has_mesh)
        if has_mesh:
            self._sync_transform_controls(item)
        self._refresh_cam_detail_readouts()

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

        self.project.items.extend(duplicates)
        self._refresh_project_list(len(self.project.items))
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
            ("Delete", QKeySequence(Qt.Key.Key_Delete), self._delete_selected_item),
            ("Duplicate", "Ctrl+D", self._duplicate_selected_item),
            ("Layers", "Ctrl+Shift+L", self._show_layers_popup),
            ("Inspector", "Ctrl+Shift+I", self._toggle_properties_panel_option),
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
        self.project_title_label.setText(f"  •  {project.name} Project")
        self.viewport.set_project(project)
        self._refresh_project_list(selected_row)

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
            self.selection_info.setText(f"Project open failed\n{exc}")
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
            self.selection_info.setText(f"Project save failed\n{exc}")
            self.statusBar().showMessage(f"Could not save project: {exc}", 8000)
            return
        self.project_path = saved_path
        self.project_title_label.setText(f"  •  {self.project.name} Project")
        self.statusBar().showMessage(f"Saved {saved_path.name}", 5000)

    def _export_gcode(self) -> None:
        toolpaths = self.project.toolpaths
        if not toolpaths:
            self.selection_info.setText(
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
            self.selection_info.setText(f"G-code export failed\n{exc}")
            self.statusBar().showMessage(f"Could not export G-code: {exc}", 8000)
            return

        total_moves = sum(len(path.moves) for path in toolpaths)
        total_minutes = sum(
            path.estimated_cutting_minutes for path in toolpaths
        )
        operation_names = " + ".join(path.name for path in toolpaths)
        self.selection_info.setText(
            f"G-code exported\n{output_path}\n\n"
            f"Operations: {operation_names}\n"
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
            self.selection_info.setText(
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
            self._refresh_project_list(len(self.project.items))
            if any(item.mesh is not None for item in imported):
                self.viewport.fit_view()
            self._on_import_items_added(len(imported))

        if failure_list:
            failure_text = "\n".join(failure_list[:8])
            if len(failure_list) > 8:
                failure_text += f"\n… and {len(failure_list) - 8} more"
            self.selection_info.setText(
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
        self.selection_info.setText(f"Import failed\n{message}")
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

