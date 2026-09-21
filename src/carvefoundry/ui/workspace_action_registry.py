"""Shared QAction registry for menus, ribbon compatibility, and tool rail."""
from __future__ import annotations

from PySide6.QtGui import QAction

from .ribbon import _ribbon_icon


class WorkspaceActionRegistryMixin:
    """Create the canonical QAction objects reused by every command surface."""

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
            ("recover", "Recover Autosave…", self._show_recovery_dialog),
            ("recovery_snapshot", "Save Recovery Checkpoint", self._manual_recovery_checkpoint),
            ("import", "Import…", self._import_file),
            ("import_stl", "STL", lambda: self._import_file("STL")),
            ("import_svg", "SVG", lambda: self._import_file("SVG")),
            ("import_dxf", "DXF", lambda: self._import_file("DXF")),
            ("import_image", "Image", lambda: self._import_file("Image")),
            ("import_gcode", "G-code", lambda: self._import_file("G-code")),
            ("export_gcode", "Export G-code", self._export_gcode),
            ("export_resume", "Export Resume G-code…", self._export_resume_gcode),
            ("export_tiled", "Export Tiled G-code…", self._export_tiled_gcode),
            ("fixtures", "Clamps and Fences…", self._fixture_editor),
            ("two_sided", "Double-Sided Stock Setup…", self._double_sided_setup),
            ("batch_layout", "Batch Production Grid…", self._batch_layout),
            ("preflight", "CNC Preflight…", self._preflight_toolpaths),
            ("guided_workflow", "Guided CNC Workflow…", self._show_guided_workflow),
            ("undo", "Undo", self._undo),
            ("redo", "Redo", self._redo),
            ("cut", "Cut", self._cut_selected_items),
            ("copy", "Copy", self._copy_selected_items),
            ("paste", "Paste", self._paste_items),
            ("delete", "Delete", self._delete_selected_item),
            ("duplicate", "Duplicate", self._duplicate_selected_item),
            ("select_all", "Select All", self._select_all_design_items),
            ("camera", "Camera Orbit", self._activate_camera_tool),
            ("direct_select", "Direct Selection — Pen Nodes", self._activate_direct_selection),
            ("select", "Select / Marquee", self._activate_navigation_tool),
            ("rectangle", "Rectangle", self._create_rectangle),
            ("ellipse", "Ellipse", self._create_ellipse),
            ("polygon", "Polygon", self._create_polygon),
            ("line", "Line", self._create_line),
            ("text", "Text", self._create_text),
            ("pen", "Pen", self._create_pen_path),
            ("measure", "Measure XY", self._activate_measure_tool),
            ("fixture_draw", "Draw Fixture", self._activate_fixture_tool),
            ("trace_image", "Trace Image", self._trace_image),
            ("ai_relief", "Generate AI Bas-Relief…", self._generate_ai_relief),
            ("vector_union", "Union Silhouettes", lambda: self._run_planar_operation("union")),
            ("vector_subtract", "Subtract Silhouettes",
             lambda: self._run_planar_operation("subtract")),
            ("vector_intersect", "Intersect Silhouettes",
             lambda: self._run_planar_operation("intersect")),
            ("vector_offset", "Offset Silhouette…", lambda: self._run_planar_operation("offset")),
            ("align", "Align", self._align_selected_items),
            ("center", "Center", self._center_selected_items),
            ("group", "Group", self._group_selected_items),
            ("ungroup", "Ungroup", self._ungroup_selected_items),
            ("layers", "Layers", self._show_layers_popup),
            ("move_up", "Move Up", lambda: self._move_selected_item(-1)),
            ("move_down", "Move Down", lambda: self._move_selected_item(1)),
            ("stock_setup", "Stock Setup", self._focus_stock_section),
            ("work_zero", "XY Work Zero…", self._work_zero_mode),
            ("smart_values", "Smart Values…", self._smart_values_dialog),
            (
                "smart_bindings",
                "Bind Smart Values…",
                self._smart_bindings_dialog,
            ),
            ("fit_view", "Fit View", self._fit_view),
            ("position", "Position", lambda: self._focus_transform_section("position")),
            ("rotate", "Rotate", lambda: self._focus_transform_section("rotation")),
            ("size", "Size", lambda: self._focus_transform_section("size")),
            ("scale", "Scale", lambda: self._focus_transform_section("scale")),
            ("apply_scale", "Apply Scale", self._apply_selected_scale),
            (
                "apply_rotation_scale",
                "Apply Rotation && Scale",
                self._apply_selected_rotation_scale,
            ),
            ("frame_selected", "Frame Selected", self._frame_selected),
            ("isolate_selected", "Isolate Selected", self._isolate_selected),
            ("exit_isolate", "Exit Isolate", self._exit_isolate),
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
            ("job_planner", "Machining Job Planner…", self._show_job_planner),
            ("preview", "Preview", self._preview_toolpaths),
            ("stock_simulation", "Simulate Material Removal…", self._simulate_stock_removal),
            ("export_toolpath", "Export G-code", self._export_gcode),
            ("machine_profile", "Edit Machine Profile…", self._machine_profile),
            (
                "select_machine_profile",
                "Select Machine Profile…",
                self._select_machine_profile,
            ),
            (
                "delete_machine_profile",
                "Delete Machine Profile…",
                self._delete_machine_profile,
            ),
            ("work_area", "Work Area", self._machine_work_area),
            ("origin", "Set Work Origin", self._machine_origin),
            ("home_machine", "Home Machine", self._home_machine),
            ("go_work_zero", "Go to Work Zero", self._go_to_work_zero),
            ("park_machine", "Park Machine", self._park_machine),
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
        self._ui_actions["direct_select"].setCheckable(True)

        self._new_ui_action(
            "recovery_enabled",
            "Automatic Recovery Checkpoints",
            lambda: self._set_recovery_enabled(not self._recovery_enabled()),
            checkable=True,
            checked=self._recovery_enabled(),
            tooltip="Save a separate complete CF3D checkpoint after one minute of idle edits.",
        )

        self._new_ui_action(
            "transform_global",
            "Global Orientation",
            lambda: self._set_transform_orientation("global"),
            checkable=True,
            checked=True,
            tooltip="Move gizmo axes follow the stock/world XYZ axes.",
        )
        self._new_ui_action(
            "transform_local",
            "Local Orientation",
            lambda: self._set_transform_orientation("local"),
            checkable=True,
            tooltip="Move gizmo axes follow the selected object's rotation.",
        )
        self._new_ui_action(
            "snap_transform",
            "Snap Translation",
            self._toggle_transform_snap,
            checkable=True,
            tooltip=(
                "Snap gizmo movement to the configured millimeter increment. "
                "Hold Ctrl during a gizmo drag for temporary snapping."
            ),
        )

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
                "measure",
            )
        }
        self._shape_tool_buttons["fixture"] = self._ui_actions["fixture_draw"]
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
                "stock_simulation",
                "preflight",
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

