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
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.core.tools import Cutter, ToolType


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
        dialog.resize(860, 760)
        dialog.setMinimumSize(720, 600)
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
        outer.addWidget(title)

        intro = QLabel(
            "Complete the required sections below. Options that do not apply "
            "to the selected operation are disabled automatically. Hover over "
            "any setting for a detailed tooltip, or use its ? button for a "
            "full explanation of the setting and its choices."
        )
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        outer.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        fields: dict[str, QWidget] = {}
        help_buttons: dict[str, QPushButton] = {}

        generation_help: dict[str, tuple[str, str]] = {
            "source_summary": (
                "Objects",
                (
                    "Generate Toolpaths works from the project, not the current "
                    "viewport selection. Every design object containing mesh "
                    "geometry is included. Surface / Face is the exception: it can "
                    "run from the stock even when the project contains no design "
                    "geometry. Hiding, selecting, or isolating an object in the "
                    "viewport does not remove it from generation."
                ),
            ),
            "operation": (
                "Toolpath",
                (
                    "Choose the machining operation to generate.\n\n"
                    "Profile — follows projected model boundaries at one or more "
                    "depths. The 2D Cut Type controls whether the cutter runs on, "
                    "inside, outside, or clears the region.\n\n"
                    "Silhouette — builds one project-wide outside envelope from "
                    "all design geometry. Internal holes are intentionally ignored.\n\n"
                    "Pocket — clears the interior of projected closed regions.\n\n"
                    "Surface / Face — faces the stock top and can run without any "
                    "design objects.\n\n"
                    "V-Carve — follows vector/detail geometry with a V-bit or "
                    "engraving cone. A valid included cutter angle is required.\n\n"
                    "Engrave — traces projected linework/contours with the selected "
                    "cutter and supports the 2D Cut Type choices.\n\n"
                    "Drill Features — finds drill-like circular projected features "
                    "and drills their centers.\n\n"
                    "Center Drill — drills the centroid of each disconnected "
                    "projected region, whether or not that region is circular.\n\n"
                    "3D Rough — removes bulk material from the 3D model using the "
                    "selected cutter geometry and roughing strategy.\n\n"
                    "3D Finish — cutter-compensated finishing over the model "
                    "surface; Detail and Direction control raster density/layout.\n\n"
                    "Height Map — uses CarveFoundry's high-detail 3D surface "
                    "finishing engine on model geometry. It is not a separate "
                    "bitmap height-map importer.\n\n"
                    "3D Rest — runs the 3D rest/cleanup strategy for model detail.\n\n"
                    "3D Waterline — creates constant-Z contour passes around the "
                    "3D model at successive levels."
                ),
            ),
            "stock": (
                "Stock",
                (
                    "Shows the active stock width × height × thickness in "
                    "millimeters. Toolpaths, Safe Z, cut depth, cutouts, and stock "
                    "surfacing are evaluated against this stock definition. Change "
                    "the stock from Stock Setup before opening this dialog if these "
                    "dimensions are wrong."
                ),
            ),
            "cutter": (
                "Selected cutter",
                (
                    "Select the physical cutter that will run this operation. "
                    "CarveFoundry compensates generated geometry for the selected "
                    "tool profile rather than assuming every tool is a ball nose. "
                    "Diameter, tool type, included angle, and tip diameter can all "
                    "change the resulting path. V-Carve requires a V-bit or "
                    "engraving cone with a valid included angle. The tool must "
                    "match the cutter actually installed in the machine."
                ),
            ),
            "cutter_details": (
                "Cutter geometry",
                (
                    "Read-only summary of the selected cutter definition: tool "
                    "type, diameter, and angle/tip diameter when applicable. Use "
                    "this line as a final sanity check before generating. Incorrect "
                    "cutter geometry produces incorrect cutter compensation even "
                    "when every other CAM setting is correct."
                ),
            ),
            "cut_type": (
                "2D cut type",
                (
                    "Controls how 2D Profile, Pocket, and Engrave operations relate "
                    "the cutter centerline to projected geometry.\n\n"
                    "Auto — use the operation's normal/default behavior.\n"
                    "Pocket — clear the interior region instead of tracing only a "
                    "boundary.\n"
                    "On Path — place the cutter centerline directly on the "
                    "projected contour.\n"
                    "Outside — offset the cutter centerline outward by its radius "
                    "so the model boundary is preserved on the inside.\n"
                    "Inside — offset inward by the cutter radius so the outside "
                    "boundary is preserved."
                ),
            ),
            "3d_style": (
                "3D style",
                (
                    "Chooses the area and finishing behavior for 3D operations.\n\n"
                    "Model Boundary Relief — constrain the relief to the projected "
                    "model boundary.\n"
                    "Rectangle Relief — machine the rectangular model/work "
                    "envelope rather than only the projected silhouette.\n"
                    "Full Depth Cutout — finish the 3D model and also generate an "
                    "outside profile through the stock so the part can be freed. "
                    "Holding tabs become available for this mode."
                ),
            ),
            "direction": (
                "Direction",
                (
                    "Controls the pattern/orientation used where an operation "
                    "supports directional passes.\n\n"
                    "Smart Serpentine — prioritizes a continuous back-and-forth "
                    "path with minimal air cutting and minimal Z lifts.\n"
                    "Offset — uses nested/offset contours where supported.\n"
                    "Raster X — long cutting runs parallel to X.\n"
                    "Raster Y — long cutting runs parallel to Y.\n"
                    "Raster 45° — diagonal raster at 45 degrees.\n"
                    "Raster 135° — opposite diagonal raster at 135 degrees.\n\n"
                    "The most efficient direction depends on model shape, grain, "
                    "clamping, cutter, and the surface detail you are trying to "
                    "preserve."
                ),
            ),
            "detail": (
                "3D / V-Carve detail",
                (
                    "Controls path density for 3D finishing and the supported "
                    "V-Carve detail behavior. Higher values create denser sampling "
                    "and smaller finishing stepover, improving fine detail and "
                    "surface smoothness at the cost of more G-code and longer run "
                    "time. Lower values generate fewer passes and run faster. "
                    "Changing Detail does not make a cutter physically capable of "
                    "reaching features smaller than its geometry."
                ),
            ),
            "pocket_stepover": (
                "2D pocket stepover",
                (
                    "Sets lateral spacing between adjacent pocket/surface passes as "
                    "a percentage of cutter diameter. For example, 40% means the "
                    "next pass center is approximately 0.40 cutter diameters away. "
                    "Lower percentages overlap more, usually leaving a smoother "
                    "surface but increasing run time. Higher percentages remove "
                    "material faster but can leave larger scallops or uncut areas "
                    "with unsuitable tool/geometry combinations."
                ),
            ),
            "padding": (
                "Path / relief padding",
                (
                    "Adds lateral margin around path or relief boundaries where the "
                    "chosen operation supports padding. 0 mm uses the calculated "
                    "boundary directly. Positive padding expands the machining "
                    "envelope, which can be useful for clearing beyond an edge or "
                    "giving a finishing cutter room to reach the model boundary. "
                    "Verify clamp and stock-edge clearance before increasing it."
                ),
            ),
            "cut_depth": (
                "Overall cut depth",
                (
                    "Maximum requested machining depth below stock Z0. A value of "
                    "0 tells CarveFoundry to derive depth from the model/operation "
                    "instead of forcing an override. A positive value overrides the "
                    "normal model depth for operations that use this setting. The "
                    "requested depth is also checked against Usable Bit Length when "
                    "that limit is enabled."
                ),
            ),
            "stepdown": (
                "Depth per pass",
                (
                    "Maximum axial depth removed in one Z level/pass. Smaller "
                    "stepdowns reduce cutter load and are safer for small tools, "
                    "hard material, or less rigid machines, but create more passes. "
                    "Larger values reduce pass count but increase cutting load. "
                    "CarveFoundry divides the requested total depth into passes that "
                    "do not exceed this value."
                ),
            ),
            "bit_length": (
                "Usable bit length",
                (
                    "Optional depth-safety limit for the cutter. 0 disables this "
                    "check. A positive value represents the cutting length you are "
                    "willing to use below the tool/holder and blocks a requested "
                    "overall depth that exceeds it. This is a validation aid, not a "
                    "complete holder/clamp collision simulation."
                ),
            ),
            "safe_z": (
                "Safe Z",
                (
                    "Full-retract clearance above stock Z0, in millimeters. "
                    "CarveFoundry uses this for initial positioning, final retracts, "
                    "Full Retract linking, and transitions that cannot be proven "
                    "safe at a lower height. Keep it high enough to clear the stock, "
                    "fixtures, fences, and clamps that the tool may cross. A larger "
                    "value is safer but increases non-cutting travel time."
                ),
            ),
            "feed": (
                "Cut feed",
                (
                    "XY/3D cutting feed rate in millimeters per minute for normal "
                    "cutting moves. It must be appropriate for cutter diameter, "
                    "flute geometry, spindle/router speed, material, depth per pass, "
                    "and machine rigidity. This field does not automatically "
                    "guarantee a safe chip load."
                ),
            ),
            "plunge": (
                "Plunge feed",
                (
                    "Feed rate used when moving downward into material. Plunge "
                    "moves usually need to be slower than lateral cutting because "
                    "many cutters evacuate chips less effectively at the center. "
                    "Ramp entries can reduce the amount of straight-down plunging "
                    "for operations that support them."
                ),
            ),
            "entry": (
                "Entry",
                (
                    "Controls how supported 2D/2.5D operations enter each cutting "
                    "depth.\n\n"
                    "Plunge — descend vertically at the Plunge Feed.\n"
                    "Ramp 5° — enter gradually along a shallow 5-degree ramp.\n"
                    "Ramp 20° — use a steeper 20-degree ramp requiring less XY "
                    "distance.\n"
                    "Custom Ramp — use the angle entered in Custom Ramp.\n\n"
                    "Shallower ramps generally reduce axial shock but require more "
                    "room. The control is disabled for operations whose current "
                    "generator does not use entry ramps."
                ),
            ),
            "ramp_angle": (
                "Custom ramp",
                (
                    "Ramp angle used only when Entry is Custom Ramp. Small angles "
                    "produce a long, gentle entry; large angles are shorter and "
                    "closer to a plunge. The valid range stays below 90 degrees. "
                    "Make sure the model/pocket has enough travel length for the "
                    "chosen angle and depth."
                ),
            ),
            "milling": (
                "Milling direction",
                (
                    "Controls contour direction for operations that support climb "
                    "or conventional milling.\n\n"
                    "Default — let the operation choose its normal direction.\n"
                    "Climb (CCW) — request CarveFoundry's climb-milling contour "
                    "direction.\n"
                    "Conventional (CW) — request the opposite conventional "
                    "direction.\n\n"
                    "Actual cutting forces also depend on whether a contour is "
                    "inside or outside. Use the direction appropriate for your "
                    "machine, workholding, cutter, and material."
                ),
            ),
            "linking": (
                "Path linking",
                (
                    "Controls how CarveFoundry moves between separate cutting "
                    "segments.\n\n"
                    "Smart Min-Lift — preferred fast mode. Keep the cutter at "
                    "cutting depth when a transition is verified safe; otherwise "
                    "use a small local clearance, reserving full Safe Z for "
                    "disconnected/unsafe travel and initial/final moves.\n"
                    "Local Lift — use short local-clearance transitions instead of "
                    "direct cutting-depth links where possible.\n"
                    "Full Retract — retract to Safe Z between separate path "
                    "segments. This is slowest but most conservative."
                ),
            ),
            "local_clearance": (
                "Local lift clearance",
                (
                    "Extra Z clearance used by Local Lift and by Smart Min-Lift "
                    "when a direct cutting-depth connection is not safe. "
                    "CarveFoundry raises the cutter above the highest required "
                    "surface along a connected transition corridor by this amount, "
                    "without exceeding full Safe Z. Increase it for more margin; "
                    "decrease it to reduce air time only when setup accuracy allows."
                ),
            ),
            "link_tolerance": (
                "Direct-link tolerance",
                (
                    "3D-only tolerance used by Smart Min-Lift when deciding whether "
                    "two raster runs may be connected directly at cutting depth. "
                    "The contact-map samples along the corridor must stay within "
                    "this allowed surface/clearance difference. A smaller value is "
                    "more conservative and causes more local lifts; a larger value "
                    "permits more direct links. 0 requires the strictest match."
                ),
            ),
            "tabs_enabled": (
                "Use holding tabs",
                (
                    "Keep small bridges of material during through-cut profiles so "
                    "the part remains attached to the surrounding stock. Tabs are "
                    "available for Profile, Silhouette, and 3D Finish when Full "
                    "Depth Cutout is selected. Turn them off only when another "
                    "workholding method safely prevents the finished part from "
                    "moving into the cutter."
                ),
            ),
            "tab_height": (
                "Tab height",
                (
                    "Amount of material left vertically in each holding tab. More "
                    "height makes tabs stronger but requires more cleanup after the "
                    "cut. Too little height can allow the part to break free before "
                    "the profile completes. This value is only used when holding "
                    "tabs are enabled."
                ),
            ),
            "tab_width": (
                "Tab width",
                (
                    "Length of each holding bridge measured along the cut path. "
                    "Wider tabs hold more strongly but take more effort to remove "
                    "and clean up. This value is only used when holding tabs are "
                    "enabled."
                ),
            ),
            "tab_count": (
                "Tab count",
                (
                    "Number of holding tabs distributed around the cutout/profile. "
                    "More tabs improve restraint on large or flexible parts but add "
                    "cleanup. Use enough tabs to resist cutting forces without "
                    "placing them where they interfere with important finished "
                    "details."
                ),
            ),
            "readiness": (
                "Generation readiness",
                (
                    "Live preflight checklist for the current dialog settings. "
                    "Green checks are requirements that currently pass. Red items "
                    "must be corrected before Generate Toolpaths is enabled. The "
                    "checklist verifies basic geometry, cutter compatibility, stock "
                    "dimensions, feeds/depth settings, usable bit length, and tabs "
                    "when applicable; it does not replace a physical setup and "
                    "collision check at the machine."
                ),
            ),
        }

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
            if project_item.mesh is not None
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
                "3D Rest": "Run the 3D rest/cleanup strategy.",
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

        ready_box = QGroupBox("7. Generation Readiness")
        ready_layout = QVBoxLayout(ready_box)
        readiness = QLabel()
        readiness.setWordWrap(True)
        readiness.setTextFormat(Qt.TextFormat.RichText)
        fields["readiness"] = readiness
        ready_layout.addWidget(help_row("readiness", readiness))
        grid.addWidget(ready_box, 3, 0, 1, 2)

        generation_progress = QProgressBar()
        generation_progress.setObjectName("ToolpathGenerationProgress")
        generation_progress.setRange(0, 100)
        generation_progress.setValue(0)
        generation_progress.setTextVisible(True)
        generation_progress.setFormat("Ready to generate · %p%")
        generation_progress.hide()
        outer.addWidget(generation_progress)

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

        def update_relevance_and_readiness() -> None:
            operation = str(operation_combo.currentData() or "")
            is_3d = operation in {
                "rough",
                "finish",
                "height_map",
                "rest",
                "waterline",
            }
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

        dialog.generation_fields = fields
        dialog.generation_help_buttons = help_buttons
        dialog.generation_help_text = generation_help
        dialog.generation_progress = generation_progress
        dialog.refresh_generation_readiness = update_relevance_and_readiness
        update_relevance_and_readiness()
        return dialog
