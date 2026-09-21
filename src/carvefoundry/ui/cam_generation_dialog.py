from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.core.beginner import MATERIAL_STARTERS, material_starting_values
from carvefoundry.core.tools import Cutter, ToolType

from .cam_dialog_help import cam_generation_help
from .layout_widgets import CamSectionNavigator


class CamGenerationDialogMixin:
    """Construct and validate the complete CAM job requirements form."""

    @staticmethod
    def _generation_double_spin(
        value: float,
        *,
        minimum: float,
        maximum: float,
        suffix: str = "",
        decimals: int = 3,
        step: float = 0.1,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(float(value))
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        return spin

    def _build_toolpath_generation_dialog(self) -> QDialog:
        """Build the all-in-one CAM generation dialog.

        The dialog is intentionally complete enough to generate the chosen
        operation for every design object without visiting other panels.
        """

        dialog = QDialog(self)
        dialog.setObjectName("ToolpathGenerationDialog")
        dialog.setWindowTitle("Generate Toolpaths")
        dialog.resize(1090, 760)
        dialog.setMinimumSize(820, 600)
        dialog.setModal(True)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        title = QLabel("Generate Toolpaths")
        title.setObjectName("DialogTitle")
        title_font = title.font()
        title_font.setPointSize(max(12, title_font.pointSize() + 3))
        title_font.setBold(True)
        title.setFont(title_font)
        title_row = QHBoxLayout()
        title_row.addWidget(title, 1)
        steps_toggle = QPushButton("Hide steps", dialog)
        steps_toggle.setObjectName("CamStepsToggle")
        steps_toggle.setCheckable(True)
        steps_toggle.setChecked(
            bool(self._settings.value(
                "cam/show_step_navigation", True, type=bool,
            ))
        )
        steps_toggle.setAccessibleName("Show CAM step navigation")
        steps_toggle.setToolTip(
            "Show/hide the form's section shortcuts to reclaim canvas "
            "space on smaller screens."
        )
        title_row.addWidget(steps_toggle)
        mode_combo = QComboBox(dialog)
        mode_combo.setObjectName("CamExperienceMode")
        mode_combo.addItems(("Simple", "Advanced"))
        selected_mode = bool(
            self._settings.value("cam/simple_mode", True, type=bool)
        ) and self._active_cam_operation in {
            "profile", "pocket", "vcarve", "engrave", "rough", "finish",
        }
        mode_combo.setCurrentIndex(0 if selected_mode else 1)
        mode_combo.setToolTip(
            "Simple asks only what to carve, which bit, depth and detail. "
            "Advanced keeps every original CAM parameter available."
        )
        title_row.addWidget(mode_combo)
        outer.addLayout(title_row)

        intro = QLabel(
            "Complete the required sections below. Options that do not apply "
            "to the selected operation are disabled automatically. Hover over "
            "any setting for a detailed tooltip, or use its ? button for a "
            "full explanation of the setting and its choices."
        )
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        outer.addWidget(intro)
        cam_brief = QLabel(dialog)
        cam_brief.setObjectName("CamContextSummary")
        cam_brief.setWordWrap(True)
        cam_brief.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        outer.addWidget(cam_brief)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        scroll.setWidget(body)
        workspace = QWidget(dialog)
        workspace_layout = QHBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(8)
        navigator = CamSectionNavigator(scroll, workspace)
        workspace_layout.addWidget(navigator)
        workspace_layout.addWidget(scroll, 1)
        outer.addWidget(workspace, 1)

        def show_step_navigation(visible: bool) -> None:
            navigator.setVisible(visible)
            steps_toggle.setText("Hide steps" if visible else "Show steps")
            self._settings.setValue("cam/show_step_navigation", visible)

        steps_toggle.toggled.connect(show_step_navigation)
        show_step_navigation(steps_toggle.isChecked())

        fields: dict[str, QWidget] = {}
        help_buttons: dict[str, QPushButton] = {}

        generation_help = cam_generation_help()

        def show_generation_help(help_key: str) -> None:
            title_text, help_text = generation_help[help_key]
            help_dialog = QDialog(dialog)
            help_dialog.setObjectName("GenerationOptionHelpDialog")
            help_dialog.setWindowTitle(f"{title_text} — Toolpath Help")
            help_dialog.resize(640, 500)
            help_dialog.setMinimumSize(480, 320)
            help_dialog.setModal(True)

            help_layout = QVBoxLayout(help_dialog)
            help_layout.setContentsMargins(14, 14, 14, 12)
            help_layout.setSpacing(10)

            help_title = QLabel(title_text)
            help_title.setObjectName("DialogTitle")
            title_font = help_title.font()
            title_font.setBold(True)
            title_font.setPointSize(max(11, title_font.pointSize() + 2))
            help_title.setFont(title_font)
            help_layout.addWidget(help_title)

            help_scroll = QScrollArea()
            help_scroll.setFrameShape(QFrame.Shape.NoFrame)
            help_scroll.setWidgetResizable(True)
            help_body = QLabel(help_text)
            help_body.setObjectName("GenerationOptionHelpText")
            help_body.setWordWrap(True)
            help_body.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            help_body.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            help_scroll.setWidget(help_body)
            help_layout.addWidget(help_scroll, 1)

            help_buttons_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Close
            )
            help_buttons_box.rejected.connect(help_dialog.reject)
            help_buttons_box.clicked.connect(
                lambda _button: help_dialog.accept()
            )
            help_layout.addWidget(help_buttons_box)
            help_dialog.exec()

        def help_row(help_key: str, widget: QWidget) -> QWidget:
            title_text, help_text = generation_help[help_key]
            widget.setToolTip(help_text)

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(widget, 1)

            help_button = QPushButton("?")
            help_button.setObjectName(f"GenerationHelp_{help_key}")
            help_button.setFixedSize(24, 24)
            help_button.setToolTip(
                f"Explain {title_text} and all available choices."
            )
            help_button.setAccessibleName(f"Help for {title_text}")
            help_button.clicked.connect(
                lambda _checked=False, key=help_key: show_generation_help(key)
            )
            row_layout.addWidget(
                help_button,
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )
            help_buttons[help_key] = help_button
            return row

        def add_help_row(
            form: QFormLayout,
            label_text: str | None,
            help_key: str,
            widget: QWidget,
        ) -> None:
            row = help_row(help_key, widget)
            if label_text is None:
                form.addRow(row)
            else:
                form.addRow(label_text, row)

        def set_choice_tooltips(
            combo: QComboBox,
            descriptions: dict[str, str],
        ) -> None:
            for index in range(combo.count()):
                item_text = combo.itemText(index)
                description = descriptions.get(item_text)
                if description:
                    combo.setItemData(
                        index,
                        description,
                        Qt.ItemDataRole.ToolTipRole,
                    )

        def group(title_text: str) -> tuple[QGroupBox, QFormLayout]:
            box = QGroupBox(title_text)
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setHorizontalSpacing(10)
            form.setVerticalSpacing(7)
            return box, form

        source_box, source_form = group("1. Source & Operation")
        source_items = [
            project_item
            for project_item in self.project.items
            if project_item.mesh is not None and project_item.visible
        ]
        source_summary = QLabel()
        source_summary.setWordWrap(True)
        if source_items:
            names = ", ".join(item.name for item in source_items[:8])
            if len(source_items) > 8:
                names += f", +{len(source_items) - 8} more"
            source_summary.setText(
                f"All {len(source_items)} design object"
                f"{'s' if len(source_items) != 1 else ''}\n{names}"
            )
        else:
            source_summary.setText(
                "No design geometry in this project\n"
                "Surface / Face can still machine the stock."
            )
        source_summary.setToolTip(
            "Generate Toolpaths always processes every design object that "
            "contains mesh geometry. The current selection is ignored."
        )
        fields["source_summary"] = source_summary
        add_help_row(source_form, "Objects", "source_summary", source_summary)

        operation_combo = QComboBox()
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
        ):
            operation_combo.addItem(
                self._cam_operation_title(operation),
                operation,
            )
        op_index = operation_combo.findData(self._active_cam_operation)
        operation_combo.setCurrentIndex(max(0, op_index))
        set_choice_tooltips(
            operation_combo,
            {
                "Profile": (
                    "Trace projected boundaries with configurable on/inside/"
                    "outside/pocket behavior."
                ),
                "Silhouette": (
                    "Cut the combined outside envelope of all project geometry; "
                    "internal holes are ignored."
                ),
                "Pocket": "Clear the interior of projected closed regions.",
                "Surface / Face": (
                    "Face the stock top. This operation can run with no design "
                    "objects."
                ),
                "V-Carve": (
                    "Use a V-bit/cone profile to carve vector/detail geometry."
                ),
                "Engrave": "Trace projected contours/linework with the cutter.",
                "Drill Features": (
                    "Detect drill-like circular projected features and drill "
                    "their centers."
                ),
                "Center Drill": (
                    "Drill the centroid of every disconnected projected region."
                ),
                "3D Rough": "Remove bulk material from the 3D model.",
                "3D Finish": (
                    "Generate cutter-compensated surface finishing passes."
                ),
                "Height Map": (
                    "Run high-detail 3D surface finishing on model geometry."
                ),
                "3D Rest": "Requires existing cutter stages; cuts only sampled leftover stock.",
                "3D Waterline": (
                    "Generate constant-Z contours at successive model levels."
                ),
            },
        )
        fields["operation"] = operation_combo
        add_help_row(source_form, "Toolpath", "operation", operation_combo)

        stock = self.project.stock
        stock_label = QLabel(
            f"{stock.width_mm:g} × {stock.height_mm:g} × "
            f"{stock.thickness_mm:g} mm"
        )
        fields["stock"] = stock_label
        add_help_row(source_form, "Stock", "stock", stock_label)
        grid.addWidget(source_box, 0, 0)

        cutter_box, cutter_form = group("2. Cutter")
        cutter_combo = QComboBox()
        current_cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        for index in range(self.tool_combo.count()):
            cutter = self.tool_combo.itemData(index)
            if not isinstance(cutter, Cutter):
                continue
            cutter_combo.addItem(cutter.name, cutter)
            cutter_combo.setItemData(
                cutter_combo.count() - 1,
                (
                    f"{cutter.tool_type.value.replace('_', ' ').title()} · "
                    f"diameter {cutter.diameter_mm:g} mm"
                    + (
                        f" · angle {cutter.angle_deg:g}°"
                        if cutter.angle_deg is not None
                        else ""
                    )
                    + (
                        f" · tip diameter {cutter.tip_diameter_mm:g} mm"
                        if cutter.tip_diameter_mm
                        else ""
                    )
                ),
                Qt.ItemDataRole.ToolTipRole,
            )
            if (
                isinstance(current_cutter, Cutter)
                and cutter.name == current_cutter.name
            ):
                cutter_combo.setCurrentIndex(cutter_combo.count() - 1)
        fields["cutter"] = cutter_combo
        add_help_row(cutter_form, "Selected cutter", "cutter", cutter_combo)
        cutter_details = QLabel()
        cutter_details.setWordWrap(True)
        cutter_details.setObjectName("Muted")
        fields["cutter_details"] = cutter_details
        add_help_row(
            cutter_form,
            "Geometry",
            "cutter_details",
            cutter_details,
        )
        grid.addWidget(cutter_box, 0, 1)

        strategy_box, strategy_form = group("3. Geometry & Strategy")
        cut_type = QComboBox()
        cut_type.addItems(("Auto", "Pocket", "On Path", "Outside", "Inside"))
        cut_type.setCurrentText(self._cam_cut_type)
        set_choice_tooltips(
            cut_type,
            {
                "Auto": "Use the selected operation's normal/default behavior.",
                "Pocket": "Clear the projected interior instead of only tracing it.",
                "On Path": "Place the cutter centerline on the projected contour.",
                "Outside": "Offset outward by cutter radius.",
                "Inside": "Offset inward by cutter radius.",
            },
        )
        fields["cut_type"] = cut_type
        add_help_row(strategy_form, "2D cut type", "cut_type", cut_type)

        style_3d = QComboBox()
        style_3d.addItems(
            (
                "Model Boundary Relief",
                "Rectangle Relief",
                "Full Depth Cutout",
            )
        )
        style_3d.setCurrentText(self._cam_3d_cut_style)
        set_choice_tooltips(
            style_3d,
            {
                "Model Boundary Relief": (
                    "Constrain 3D machining to the projected model boundary."
                ),
                "Rectangle Relief": (
                    "Machine the rectangular model/work envelope."
                ),
                "Full Depth Cutout": (
                    "Finish the relief and add an outside through-cut profile."
                ),
            },
        )
        fields["3d_style"] = style_3d
        add_help_row(strategy_form, "3D style", "3d_style", style_3d)

        direction = QComboBox()
        direction.addItems(
            (
                "Smart Serpentine",
                "Offset",
                "Raster X",
                "Raster Y",
                "Raster 45°",
                "Raster 135°",
            )
        )
        direction.setCurrentText(self._cam_direction)
        set_choice_tooltips(
            direction,
            {
                "Smart Serpentine": (
                    "Continuous back-and-forth cutting optimized to reduce air "
                    "moves and Z lifts."
                ),
                "Offset": "Use nested/offset contour-style passes.",
                "Raster X": "Run primary raster cuts parallel to X.",
                "Raster Y": "Run primary raster cuts parallel to Y.",
                "Raster 45°": "Run diagonal raster passes at 45 degrees.",
                "Raster 135°": "Run diagonal raster passes at 135 degrees.",
            },
        )
        fields["direction"] = direction
        add_help_row(strategy_form, "Direction", "direction", direction)

        detail = QSpinBox()
        detail.setRange(0, 100)
        detail.setSuffix(" %")
        detail.setValue(self._cam_detail)
        fields["detail"] = detail
        add_help_row(
            strategy_form,
            "3D / V-Carve detail",
            "detail",
            detail,
        )

        pocket_stepover = self._generation_double_spin(
            float(self._settings.value("cam/stepover_percent", 45.0)),
            minimum=1.0,
            maximum=100.0,
            suffix=" %",
            decimals=1,
            step=1.0,
        )
        fields["pocket_stepover"] = pocket_stepover
        add_help_row(
            strategy_form,
            "2D pocket stepover",
            "pocket_stepover",
            pocket_stepover,
        )

        padding = self._generation_double_spin(
            float(self._settings.value("cam/padding_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            suffix=" mm",
            step=0.25,
        )
        fields["padding"] = padding
        add_help_row(
            strategy_form,
            "Path / relief padding",
            "padding",
            padding,
        )
        grid.addWidget(strategy_box, 1, 0)

        depth_box, depth_form = group("4. Depth Requirements")
        cut_depth = self._generation_double_spin(
            float(self._settings.value("cam/overall_depth_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            suffix=" mm",
            step=0.25,
        )
        fields["cut_depth"] = cut_depth
        add_help_row(depth_form, "Overall cut depth", "cut_depth", cut_depth)

        stepdown = self._generation_double_spin(
            float(self._settings.value("cam/stepdown_mm", 2.0)),
            minimum=0.05,
            maximum=1000.0,
            suffix=" mm",
            step=0.25,
        )
        fields["stepdown"] = stepdown
        add_help_row(depth_form, "Depth per pass", "stepdown", stepdown)

        bit_length = self._generation_double_spin(
            float(self._settings.value("cam/usable_bit_length_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            suffix=" mm",
            step=0.5,
        )
        fields["bit_length"] = bit_length
        add_help_row(
            depth_form,
            "Usable bit length",
            "bit_length",
            bit_length,
        )
        grid.addWidget(depth_box, 1, 1)

        motion_box, motion_form = group("5. Motion & Safety")
        safe_z = self._generation_double_spin(
            float(self._settings.value("cam/safe_z_mm", 1.5)),
            minimum=0.05,
            maximum=100.0,
            suffix=" mm",
            step=0.1,
        )
        fields["safe_z"] = safe_z
        add_help_row(motion_form, "Safe Z", "safe_z", safe_z)

        feed = self._generation_double_spin(
            float(self._settings.value("cam/feed_mm_min", 1000.0)),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm/min",
            decimals=0,
            step=50.0,
        )
        fields["feed"] = feed
        add_help_row(motion_form, "Cut feed", "feed", feed)

        plunge = self._generation_double_spin(
            float(self._settings.value("cam/plunge_mm_min", 300.0)),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm/min",
            decimals=0,
            step=25.0,
        )
        fields["plunge"] = plunge
        add_help_row(motion_form, "Plunge feed", "plunge", plunge)

        entry = QComboBox()
        entry.addItems(("Plunge", "Ramp 5°", "Ramp 20°", "Custom Ramp"))
        entry.setCurrentText(self._cam_entry)
        set_choice_tooltips(
            entry,
            {
                "Plunge": "Enter vertically at the configured Plunge Feed.",
                "Ramp 5°": "Use a long, shallow 5-degree ramp entry.",
                "Ramp 20°": "Use a shorter, steeper 20-degree ramp entry.",
                "Custom Ramp": "Use the angle entered in Custom Ramp.",
            },
        )
        fields["entry"] = entry
        add_help_row(motion_form, "Entry", "entry", entry)

        ramp_angle = self._generation_double_spin(
            float(self._settings.value("cam/custom_ramp_angle_deg", 10.0)),
            minimum=0.5,
            maximum=89.0,
            suffix="°",
            decimals=1,
            step=0.5,
        )
        fields["ramp_angle"] = ramp_angle
        add_help_row(
            motion_form,
            "Custom ramp",
            "ramp_angle",
            ramp_angle,
        )

        milling = QComboBox()
        milling.addItems(("Default", "Climb (CCW)", "Conventional (CW)"))
        milling.setCurrentText(self._cam_milling)
        set_choice_tooltips(
            milling,
            {
                "Default": "Use the operation's normal contour direction.",
                "Climb (CCW)": "Request CarveFoundry's climb-milling direction.",
                "Conventional (CW)": (
                    "Request CarveFoundry's conventional-milling direction."
                ),
            },
        )
        fields["milling"] = milling
        add_help_row(
            motion_form,
            "Milling direction",
            "milling",
            milling,
        )

        linking = QComboBox()
        linking.addItems(("Smart Min-Lift", "Local Lift", "Full Retract"))
        linking.setCurrentText(self._cam_linking)
        set_choice_tooltips(
            linking,
            {
                "Smart Min-Lift": (
                    "Stay down when safe, otherwise use local clearance and "
                    "reserve Safe Z for unsafe/disconnected travel."
                ),
                "Local Lift": (
                    "Use local-clearance lifts between separate path segments."
                ),
                "Full Retract": (
                    "Retract to full Safe Z between separate path segments."
                ),
            },
        )
        fields["linking"] = linking
        add_help_row(motion_form, "Path linking", "linking", linking)

        local_clearance = self._generation_double_spin(
            float(self._settings.value("cam/local_link_clearance_mm", 0.5)),
            minimum=0.05,
            maximum=25.0,
            suffix=" mm",
            step=0.1,
        )
        fields["local_clearance"] = local_clearance
        add_help_row(
            motion_form,
            "Local lift clearance",
            "local_clearance",
            local_clearance,
        )

        link_tolerance = self._generation_double_spin(
            float(self._settings.value("cam/direct_link_tolerance_mm", 0.02)),
            minimum=0.0,
            maximum=5.0,
            suffix=" mm",
            step=0.01,
        )
        fields["link_tolerance"] = link_tolerance
        add_help_row(
            motion_form,
            "Direct-link tolerance",
            "link_tolerance",
            link_tolerance,
        )
        grid.addWidget(motion_box, 2, 0)

        tabs_box, tabs_form = group("6. Tabs / Cutout Holding")
        tabs_enabled = QCheckBox("Use holding tabs")
        tabs_enabled.setChecked(self._tabs_enabled)
        fields["tabs_enabled"] = tabs_enabled
        add_help_row(tabs_form, None, "tabs_enabled", tabs_enabled)

        tab_height = self._generation_double_spin(
            float(self._settings.value("cam/tab_height_mm", 2.0)),
            minimum=0.1,
            maximum=100.0,
            suffix=" mm",
            step=0.25,
        )
        fields["tab_height"] = tab_height
        add_help_row(tabs_form, "Tab height", "tab_height", tab_height)

        tab_width = self._generation_double_spin(
            float(self._settings.value("cam/tab_width_mm", 6.0)),
            minimum=0.5,
            maximum=100.0,
            suffix=" mm",
            step=0.5,
        )
        fields["tab_width"] = tab_width
        add_help_row(tabs_form, "Tab width", "tab_width", tab_width)

        tab_count = QSpinBox()
        tab_count.setRange(1, 32)
        tab_count.setValue(int(self._settings.value("cam/tab_count", 4)))
        fields["tab_count"] = tab_count
        add_help_row(tabs_form, "Tab count", "tab_count", tab_count)
        grid.addWidget(tabs_box, 2, 1)

        rest_box, rest_form = group("Stock-Aware Rest Cleanup")
        rest_intro = QLabel(
            "Generate roughing/finishing first. This operation simulates the "
            "existing job on stock, then appends cleanup ONLY where the "
            "selected cutter can remove leftover material. A smaller cutter "
            "can reach detail the previous tool missed. It cannot infer "
            "actual cuts performed outside CarveFoundry."
        )
        rest_intro.setWordWrap(True)
        rest_form.addRow(rest_intro)
        rest_allowance = self._generation_double_spin(
            float(self._settings.value("cam/rest_min_remaining_mm", 0.15)),
            minimum=0.01,
            maximum=5.0,
            suffix=" mm",
            step=0.05,
        )
        rest_allowance.setToolTip(
            "Minimum residual material to justify a rest cut (above the "
            "contact-safe cutter surface). Larger values skip shallow "
            "leftovers; smaller values add more paths."
        )
        fields["rest_allowance"] = rest_allowance
        rest_form.addRow("Minimum leftover height", rest_allowance)
        rest_resolution = self._generation_double_spin(
            float(self._settings.value("cam/rest_grid_spacing_mm", 0.75)),
            minimum=0.1,
            maximum=10.0,
            suffix=" mm",
            step=0.25,
        )
        rest_resolution.setToolTip(
            "XY sampling of previously removed stock, not final finishing "
            "stepover. Smaller samples cost more memory/time; no grid above "
            "600,000 stock cells is permitted. Use resolution smaller than "
            "the detail you need to detect."
        )
        fields["rest_resolution"] = rest_resolution
        rest_form.addRow("Stock simulation spacing", rest_resolution)
        grid.addWidget(rest_box, 3, 0, 1, 2)

        ready_box = QGroupBox("7. Generation Readiness")
        ready_layout = QVBoxLayout(ready_box)
        readiness = QLabel()
        readiness.setWordWrap(True)
        readiness.setTextFormat(Qt.TextFormat.RichText)
        fields["readiness"] = readiness
        ready_layout.addWidget(help_row("readiness", readiness))
        grid.addWidget(ready_box, 4, 0, 1, 2)

        for key, heading, section in (
            ("source", "1  Source / Operation", source_box),
            ("cutter", "2  Cutter", cutter_box),
            ("strategy", "3  Strategy", strategy_box),
            ("depth", "4  Depth", depth_box),
            ("motion", "5  Motion / Safety", motion_box),
            ("tabs", "6  Holding tabs", tabs_box),
            ("rest", "   Rest cleanup", rest_box),
            ("readiness", "7  Readiness", ready_box),
        ):
            navigator.add_section(key, heading, section)


        append_job = QCheckBox(
            f"Append to existing machining job ({len(self.project.toolpaths)} "
            "operations) instead of replacing it"
        )
        append_job.setObjectName("AppendCamJobCheck")
        append_job.setEnabled(bool(self.project.toolpaths))
        append_job.setToolTip(
            "Build all old and new toolpaths into one ordered job, including "
            "preview and per-cutter GRBL exports. Paths remain session-owned; "
            "regenerate after reopening a .cf3d project."
        )
        fields["append_job"] = append_job
        outer.addWidget(append_job)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        generate_button = buttons.addButton(
            "Generate Toolpaths",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        generate_button.setObjectName("PrimaryButton")
        generate_button.setDefault(True)
        fields["generate"] = generate_button
        buttons.rejected.connect(dialog.reject)
        outer.addWidget(buttons)

        # Simple Mode is a VIEW over the same real CAM fields, never a second
        # settings store or alternate generation engine. All values go through
        # accept_and_generate and its independent readiness checks.
        simple_panel = QGroupBox("Your first toolpath · four choices", dialog)
        simple_panel.setObjectName("SimpleCamPanel")
        simple_form = QFormLayout(simple_panel)
        simple_intro = QLabel(
            "Choose what you want the cutter to do. The Advanced view contains "
            "all safety heights, linking and pass settings. They still apply "
            "in Simple Mode; review them before running the physical machine."
        )
        simple_intro.setWordWrap(True)
        simple_form.addRow(simple_intro)
        simple_operation = QComboBox(simple_panel)
        simple_operation.setObjectName("SimpleCamOperation")
        for op in ("profile", "pocket", "vcarve", "engrave", "rough", "finish"):
            simple_operation.addItem(self._cam_operation_title(op), op)
        op_idx = simple_operation.findData(operation_combo.currentData())
        simple_operation.setCurrentIndex(max(op_idx, 0))
        simple_form.addRow("What should the bit do?", simple_operation)
        simple_cutter = QComboBox(simple_panel)
        simple_cutter.setObjectName("SimpleCamCutter")
        for i in range(cutter_combo.count()):
            simple_cutter.addItem(
                cutter_combo.itemText(i), cutter_combo.itemData(i)
            )
        simple_cutter.setCurrentIndex(cutter_combo.currentIndex())
        simple_form.addRow("Which cutter?", simple_cutter)
        simple_depth = self._generation_double_spin(
            cut_depth.value(), minimum=cut_depth.minimum(),
            maximum=cut_depth.maximum(), suffix=" mm", step=0.25,
        )
        simple_depth.setObjectName("SimpleCamDepth")
        simple_form.addRow("How deep?", simple_depth)
        simple_detail = QSpinBox(simple_panel)
        simple_detail.setRange(0, 100)
        simple_detail.setValue(detail.value())
        simple_detail.setSuffix(" %")
        simple_detail.setObjectName("SimpleCamDetail")
        simple_detail.setToolTip(
            "Higher detail produces closer passes when the operation uses "
            "surface-detail settings. For Profile/Engrave, detail may not "
            "change toolpath geometry."
        )
        simple_form.addRow("How detailed?", simple_detail)
        simple_material = QComboBox(simple_panel)
        simple_material.setObjectName("SimpleCamMaterial")
        for starter in MATERIAL_STARTERS:
            simple_material.addItem(starter.name, starter)
        simple_form.addRow("Example material", simple_material)
        material_note = QLabel(
            "Starting values only. Confirm bit maker, RPM, machine travel "
            "and workholding. Material selection alone changes NOTHING."
        )
        material_note.setWordWrap(True)
        simple_form.addRow(material_note)
        use_material = QPushButton("Apply example feed / plunge / stepdown")
        use_material.setObjectName("SimpleCamApplyMaterial")
        simple_form.addRow(use_material)
        simple_readiness = QLabel(simple_panel)
        simple_readiness.setObjectName("SimpleCamReadiness")
        simple_readiness.setTextFormat(Qt.TextFormat.RichText)
        simple_readiness.setWordWrap(True)
        simple_form.addRow(simple_readiness)
        outer.insertWidget(3, simple_panel)

        def sync_simple_operation(_index: int) -> None:
            desired = operation_combo.findData(simple_operation.currentData())
            if desired >= 0 and desired != operation_combo.currentIndex():
                operation_combo.setCurrentIndex(desired)

        def sync_advanced_operation(_index: int) -> None:
            desired = simple_operation.findData(operation_combo.currentData())
            if desired >= 0 and desired != simple_operation.currentIndex():
                simple_operation.setCurrentIndex(desired)

        def sync_simple_cutter(index: int) -> None:
            if index != cutter_combo.currentIndex():
                cutter_combo.setCurrentIndex(index)

        def sync_advanced_cutter(index: int) -> None:
            if index != simple_cutter.currentIndex():
                simple_cutter.setCurrentIndex(index)

        simple_operation.currentIndexChanged.connect(sync_simple_operation)
        operation_combo.currentIndexChanged.connect(sync_advanced_operation)
        simple_cutter.currentIndexChanged.connect(sync_simple_cutter)
        cutter_combo.currentIndexChanged.connect(sync_advanced_cutter)
        simple_depth.valueChanged.connect(cut_depth.setValue)
        cut_depth.valueChanged.connect(simple_depth.setValue)
        simple_detail.valueChanged.connect(detail.setValue)
        detail.valueChanged.connect(simple_detail.setValue)

        def apply_material() -> None:
            bit = simple_cutter.currentData()
            if not isinstance(bit, Cutter):
                return
            starter = simple_material.currentData()
            example_feed, example_plunge, example_stepdown = (
                material_starting_values(starter, bit)
            )
            feed.setValue(example_feed)
            plunge.setValue(example_plunge)
            stepdown.setValue(example_stepdown)
        use_material.clicked.connect(apply_material)

        def set_cam_mode(_index: int) -> None:
            simple = mode_combo.currentIndex() == 0
            simple_panel.setVisible(simple)
            workspace.setVisible(not simple)
            steps_toggle.setVisible(not simple)
            self._settings.setValue("cam/simple_mode", simple)

        mode_combo.currentIndexChanged.connect(set_cam_mode)
        fields["mode"] = mode_combo
        fields["simple_operation"] = simple_operation
        fields["simple_cutter"] = simple_cutter
        fields["simple_depth"] = simple_depth
        fields["simple_detail"] = simple_detail
        fields["simple_material"] = simple_material
        fields["simple_apply_material"] = use_material
        fields["simple_readiness"] = simple_readiness

        def update_relevance_and_readiness() -> None:
            operation = str(operation_combo.currentData() or "")
            is_3d = operation in {
                "rough",
                "finish",
                "height_map",
                "rest",
                "waterline",
            }
            rest_active = operation == "rest"
            rest_box.setVisible(rest_active)
            if rest_active:
                append_job.setChecked(bool(self.project.toolpaths))
                append_job.setEnabled(False)
            else:
                append_job.setEnabled(bool(self.project.toolpaths))
            uses_cut_type = operation in {"profile", "pocket", "engrave"}
            uses_detail = is_3d or operation == "vcarve"
            uses_entry = operation not in {
                "rough",
                "finish",
                "height_map",
                "rest",
                "waterline",
                "drill",
                "center_drill",
            }
            uses_milling = operation in {
                "profile",
                "silhouette",
                "pocket",
                "surface",
                "engrave",
            }
            uses_linking = True
            uses_tabs = operation in {"profile", "silhouette"} or (
                operation == "finish"
                and style_3d.currentText() == "Full Depth Cutout"
            )

            cut_type.setEnabled(uses_cut_type)
            style_3d.setEnabled(is_3d)
            direction.setEnabled(
                is_3d or operation in {"pocket", "surface"}
            )
            detail.setEnabled(uses_detail)
            pocket_stepover.setEnabled(operation in {"pocket", "surface"})
            entry.setEnabled(uses_entry)
            ramp_angle.setEnabled(
                uses_entry and entry.currentText() == "Custom Ramp"
            )
            milling.setEnabled(uses_milling)
            linking.setEnabled(uses_linking)
            local_clearance.setEnabled(uses_linking)
            link_tolerance.setEnabled(is_3d)
            tabs_box.setEnabled(True)
            tabs_enabled.setEnabled(uses_tabs)
            tabs_active = uses_tabs and tabs_enabled.isChecked()
            tab_height.setEnabled(tabs_active)
            tab_width.setEnabled(tabs_active)
            tab_count.setEnabled(tabs_active)

            cutter = cutter_combo.currentData()
            if isinstance(cutter, Cutter):
                detail_text = (
                    f"{cutter.tool_type.value.replace('_', ' ').title()} · "
                    f"Ø {cutter.diameter_mm:g} mm"
                )
                if cutter.angle_deg is not None:
                    detail_text += f" · {cutter.angle_deg:g}°"
                if cutter.tip_diameter_mm:
                    detail_text += f" · tip Ø {cutter.tip_diameter_mm:g} mm"
                cutter_details.setText(detail_text)
            else:
                cutter_details.setText("No valid cutter selected")

            checks: list[tuple[bool, str]] = []
            requires_geometry = operation != "surface"
            checks.append(
                (
                    bool(source_items) or not requires_geometry,
                    (
                        "Stock surface will be generated"
                        if operation == "surface"
                        else (
                            f"All {len(source_items)} design object"
                            f"{'s' if len(source_items) != 1 else ''} will be generated"
                            if source_items
                            else "Project contains design geometry"
                        )
                    ),
                )
            )
            checks.append(
                (
                    isinstance(cutter, Cutter),
                    "Valid cutter selected",
                )
            )
            if rest_active:
                previous = self.project.toolpaths
                relevant = {
                    path.source_item_id
                    for path in previous
                    if "full depth cutout" not in path.name.casefold()
                }
                checks.append((
                    bool(previous),
                    "Existing cutter stages are present and will be appended",
                ))
                checks.append((
                    bool(previous) and all(
                        item.item_id in relevant
                        for item in source_items
                    ),
                    "Each visible model has a preceding machining operation",
                ))
                checks.append((
                    not any(
                        "full depth cutout" in path.name.casefold()
                        for path in previous
                        if any(
                            path.source_item_id == item.item_id
                            for item in source_items
                        )
                    ),
                    "No selected model has already been freed by a cutout",
                ))
            if operation == "vcarve":
                checks.append(
                    (
                        isinstance(cutter, Cutter)
                        and cutter.tool_type
                        in {ToolType.V_BIT, ToolType.ENGRAVING_CONE}
                        and cutter.angle_deg is not None,
                        "V-Carve cutter has a V/cone profile and included angle",
                    )
                )
            checks.append(
                (
                    stock.width_mm > 0
                    and stock.height_mm > 0
                    and stock.thickness_mm > 0,
                    "Stock dimensions are valid",
                )
            )
            checks.append((safe_z.value() > 0, "Safe Z is positive"))
            checks.append(
                (
                    feed.value() > 0
                    and plunge.value() > 0
                    and stepdown.value() > 0,
                    "Feed, plunge, and depth-per-pass are valid",
                )
            )
            requested_depth = cut_depth.value()
            usable_length = bit_length.value()
            checks.append(
                (
                    usable_length <= 0
                    or requested_depth <= 0
                    or requested_depth <= usable_length + 1e-9,
                    "Requested depth fits the enforced usable bit length",
                )
            )
            if uses_tabs and tabs_enabled.isChecked():
                checks.append(
                    (
                        tab_height.value() > 0
                        and tab_width.value() > 0
                        and tab_count.value() > 0,
                        "Holding-tab dimensions are valid",
                    )
                )

            all_ready = all(ok for ok, _message in checks)
            readiness.setText(
                "<br>".join(
                    (
                        "<span style='color:#62d26f'>✓</span> "
                        if ok
                        else "<span style='color:#ff6b6b'>●</span> "
                    )
                    + message
                    for ok, message in checks
                )
                + (
                    "<br><br><b>Ready to generate.</b>"
                    if all_ready
                    else "<br><br><b>Resolve the red requirements to continue.</b>"
                )
            )
            generate_button.setEnabled(all_ready)
            simple_readiness.setText(readiness.text())
            cam_brief.setText(
                f"{operation_combo.currentText()}   •   "
                f"{cutter.name if isinstance(cutter, Cutter) else 'No cutter'}"
                f"   •   {len(source_items)} visible model(s)   •   "
                f"{stock.width_mm:g} × {stock.height_mm:g} × "
                f"{stock.thickness_mm:g} mm stock"
                + (
                    f"   •   {len(self.project.toolpaths)} earlier operation(s)"
                    if self.project.toolpaths else ""
                )
            )
            navigator.set_available("rest", rest_active)
            navigator.set_available("tabs", uses_tabs)
            navigator.set_ready("readiness", all_ready)
            navigator.set_ready("source", bool(source_items) or operation == "surface")
            navigator.set_ready("cutter", isinstance(cutter, Cutter))
            navigator.set_ready("depth", (
                safe_z.value() > 0 and stepdown.value() > 0
            ))

        def accept_and_generate() -> None:
            update_relevance_and_readiness()
            if not generate_button.isEnabled():
                return

            operation = str(operation_combo.currentData() or "finish")
            self._select_cam_operation(operation)

            cutter = cutter_combo.currentData()
            if isinstance(cutter, Cutter):
                for index in range(self.tool_combo.count()):
                    candidate = self.tool_combo.itemData(index)
                    if (
                        isinstance(candidate, Cutter)
                        and candidate.name == cutter.name
                    ):
                        self.tool_combo.setCurrentIndex(index)
                        break

            for key, combo in (
                ("cut_type", cut_type),
                ("3d_cut_style", style_3d),
                ("direction", direction),
                ("entry", entry),
                ("milling", milling),
                ("linking", linking),
            ):
                self._set_cam_design_option(key, combo.currentText())
            self._set_cam_detail(detail.value(), mark_custom=True)

            values = {
                "cam/safe_z_mm": safe_z.value(),
                "cam/overall_depth_mm": cut_depth.value(),
                "cam/feed_mm_min": feed.value(),
                "cam/plunge_mm_min": plunge.value(),
                "cam/stepdown_mm": stepdown.value(),
                "cam/stepover_percent": pocket_stepover.value(),
                "cam/padding_mm": padding.value(),
                "cam/usable_bit_length_mm": bit_length.value(),
                "cam/tab_height_mm": tab_height.value(),
                "cam/tab_width_mm": tab_width.value(),
                "cam/tab_count": tab_count.value(),
                "cam/local_link_clearance_mm": local_clearance.value(),
                "cam/direct_link_tolerance_mm": link_tolerance.value(),
                "cam/custom_ramp_angle_deg": ramp_angle.value(),
                "cam/rest_min_remaining_mm": rest_allowance.value(),
                "cam/rest_grid_spacing_mm": rest_resolution.value(),
            }
            for setting_key, setting_value in values.items():
                self._settings.setValue(setting_key, setting_value)

            self._tabs_enabled = (
                tabs_enabled.isChecked() if uses_tabs_for_current() else False
            )
            self._settings.setValue("cam/tabs_enabled", self._tabs_enabled)
            if self._tabs_button is not None:
                self._tabs_button.setChecked(self._tabs_enabled)
            self._settings.sync()

            # The worker process combines old/new paths and preview geometry.
            # Do not clear the previous job if generation/validation fails.
            self._cam_append_to_job = append_job.isChecked()
            # Close the modal configuration dialog as soon as the worker is
            # submitted; progress/cancellation are in the status bar, and
            # viewport navigation stays accessible throughout calculation.
            if self._calculate_toolpath_now():
                dialog.accept()
            else:
                update_relevance_and_readiness()

        def uses_tabs_for_current() -> bool:
            operation = str(operation_combo.currentData() or "")
            return operation in {"profile", "silhouette"} or (
                operation == "finish"
                and style_3d.currentText() == "Full Depth Cutout"
            )

        generate_button.clicked.connect(accept_and_generate)

        watched_widgets = (
            operation_combo,
            cutter_combo,
            cut_type,
            style_3d,
            direction,
            detail,
            pocket_stepover,
            padding,
            cut_depth,
            stepdown,
            bit_length,
            safe_z,
            feed,
            plunge,
            entry,
            ramp_angle,
            milling,
            linking,
            local_clearance,
            link_tolerance,
            tabs_enabled,
            tab_height,
            tab_width,
            tab_count,
            rest_allowance,
            rest_resolution,
        )
        for widget in watched_widgets:
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(
                    update_relevance_and_readiness
                )
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(update_relevance_and_readiness)
            else:
                widget.valueChanged.connect(update_relevance_and_readiness)

        fields["section_nav"] = navigator
        fields["context_summary"] = cam_brief
        dialog.section_navigator = navigator
        dialog.generation_fields = fields
        dialog.generation_help_buttons = help_buttons
        dialog.generation_help_text = generation_help
        dialog.refresh_generation_readiness = update_relevance_and_readiness
        update_relevance_and_readiness()
        set_cam_mode(mode_combo.currentIndex())
        return dialog
