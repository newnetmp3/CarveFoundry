"""Hidden ribbon compatibility host and compact vertical tool rail."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from .tool_rail import ToolRail


class WorkspaceSurfaceBuilderMixin:
    """Build legacy compatibility controls and the visible tool rail."""

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

        rail.add_action_tool(
            "direct_select",
            self._ui_actions["direct_select"],
            tooltip=(
                "Direct Selection / Nodes — select a Pen Stroke, drag green "
                "viewport knots or edit exact XY; real CNC geometry changes "
                "support Undo/Redo and invalidate stale paths."
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
            tooltip="Shape tools — click to draw; press and hold for Rectangle, Ellipse, or Polygon.",
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
        self._add_menu_actions(vector_menu, ("direct_select", "pen", "trace_image"))
        vector_menu.addSeparator()
        self._add_menu_actions(
            vector_menu,
            ("vector_union", "vector_subtract", "vector_intersect", "vector_offset"),
        )
        rail.add_menu(
            "vector",
            "Pen",
            vector_menu,
            tooltip=(
                "Vector tools — click for Pen; press and hold to choose "
                "Direct Selection, Trace Image, Boolean, or Offset."
            ),
            primary_callback=self._create_pen_path,
            checkable=True,
        )

        rail.add_action_tool(
            "measure",
            self._ui_actions["measure"],
            tooltip=(
                "Measure XY — drag two stock-top points to read the exact "
                "planar length, ΔX, ΔY, and angle."
            ),
        )
        fixture_menu = QMenu(rail)
        self._add_menu_actions(fixture_menu, ("fixtures",))
        rail.add_menu(
            "fixture",
            "Draw Fixture",
            fixture_menu,
            tooltip=(
                "Click to draw a clamp/fence keep-out; press and hold "
                "for fixture setup, including off-stock fences."
            ),
            primary_callback=self._activate_fixture_tool,
            checkable=True,
        )

        rail.add_separator()

        model_menu = QMenu(rail)
        self._add_menu_actions(
            model_menu,
            ("stock_setup", "work_zero", "fixtures", "two_sided", "ai_relief", "guided_workflow", "batch_layout",
             "smart_values", "smart_bindings", "fit_view"),
        )
        transform_menu = model_menu.addMenu("Transform")
        self._add_menu_actions(
            transform_menu,
            ("position", "rotate", "size", "scale"),
        )
        orientation_menu = transform_menu.addMenu("Orientation")
        self._add_menu_actions(
            orientation_menu,
            ("transform_global", "transform_local"),
        )
        transform_menu.addSeparator()
        self._add_menu_actions(
            transform_menu,
            ("snap_transform", "apply_scale", "apply_rotation_scale"),
        )
        placement_menu = model_menu.addMenu("Placement")
        self._add_menu_actions(
            placement_menu,
            ("center_xy", "top_z0", "fit_stock", "reset_transform"),
        )
        model_menu.addSeparator()
        self._add_menu_actions(
            model_menu,
            ("frame_selected", "isolate_selected", "exit_isolate"),
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
            (
                "advanced_cam",
                "guided_workflow",
                "calculate",
                "job_planner",
                "preview",
                "simulate",
                "stock_simulation",
                "preflight",
                "export_toolpath",
                "export_resume",
                "export_tiled",
            ),
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
            (
                "select_machine_profile",
                "machine_profile",
                "delete_machine_profile",
                "work_area",
                "postprocessor",
            ),
        )
        machine_menu.addSeparator()
        self._add_menu_actions(
            machine_menu,
            (
                "machine_connect",
                "home_machine",
                "origin",
                "go_work_zero",
                "park_machine",
                "probe",
                "jog",
            ),
        )
        rail.add_menu(
            "machine",
            "Machine Profile",
            machine_menu,
            tooltip="Machine setup, connection, probe, and jog controls.",
        )

        rail.add_separator()
        # Frequent actions stay one click away; general File/Edit/View
        # commands remain in the permanent top menu rather than crowding rail.
        rail.add_action_tool(
            "generate",
            self._ui_actions["calculate"],
            tooltip="Generate current CAM operation with its configured cutter.",
        )
        rail.add_action_tool(
            "preview",
            self._ui_actions["preview"],
            tooltip="Inspect calculated G-code in the toolpath backplotter.",
        )
        rail.add_action_tool(
            "preflight",
            self._ui_actions["preflight"],
            tooltip="Check machine travel, stock depth and fixture clearance.",
        )
        rail.add_action_tool(
            "export",
            self._ui_actions["export_toolpath"],
            tooltip="Export preflight-checked G-code by cutter stage.",
        )

        rail.add_stretch()
        rail.set_active_tool("camera")
        return rail
