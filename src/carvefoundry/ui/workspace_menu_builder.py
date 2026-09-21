"""Top-level dropdown menu construction for the CarveFoundry workspace."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMenuBar


class WorkspaceMenuBuilderMixin:
    """Build normal desktop menus from the shared action registry."""

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
        self._add_menu_actions(
            file_menu, ("recover", "recovery_snapshot", "recovery_enabled"),
        )
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

        project_menu = bar.addMenu("Project")
        self._add_menu_actions(
            project_menu,
            ("stock_setup", "work_zero", "fixtures", "two_sided", "guided_workflow",
             "smart_values", "smart_bindings"),
        )

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
            ("select", "direct_select", "rectangle", "ellipse", "polygon", "line", "text"),
        )
        vector_menu = design_menu.addMenu("Vector")
        self._add_menu_actions(vector_menu, ("direct_select", "pen", "trace_image"))
        vector_menu.addSeparator()
        self._add_menu_actions(
            vector_menu,
            ("vector_union", "vector_subtract", "vector_intersect", "vector_offset"),
        )
        workshop_menu = design_menu.addMenu("Workshop")
        self._add_menu_actions(
            workshop_menu, ("measure", "fixture_draw", "fixtures")
        )
        arrange_menu = design_menu.addMenu("Arrange")
        self._add_menu_actions(
            arrange_menu,
            ("align", "center", "group", "ungroup", "duplicate", "batch_layout"),
        )
        design_menu.addSeparator()
        self._add_menu_actions(design_menu, ("layers", "move_up", "move_down"))

        model_menu = bar.addMenu("Model")
        self._add_menu_actions(model_menu, ("stock_setup", "fit_view", "ai_relief"))
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
            (
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

        machine_menu = bar.addMenu("Machine")
        self._add_menu_actions(
            machine_menu,
            (
                "select_machine_profile",
                "machine_profile",
                "delete_machine_profile",
                "work_area",
                "fixtures",
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
                "frame_selected",
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
            (
                "layers",
                "inspector",
                "isolate_selected",
                "exit_isolate",
                "status_bar",
                "view_controls",
                "reset_ui",
            ),
        )
        navigation_menu = view_menu.addMenu("Navigation")
        self._add_menu_actions(
            navigation_menu,
            ("reverse_horizontal", "invert_vertical"),
        )
        return bar

