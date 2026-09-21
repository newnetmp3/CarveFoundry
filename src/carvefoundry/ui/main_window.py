from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..cam.job_process import GcodeRequest
from ..core.project import Project, ProjectItem
from ..core.project_file import (
    PROJECT_SUFFIX,
    load_project,
    save_project,
)
from .ai_relief import AiReliefMixin
from .background_job_controller import BackgroundJobControllerMixin
from .batch_layout import BatchLayoutMixin
from .direct_selection import DirectSelectionMixin
from .guided_workflow import GuidedWorkflowMixin
from .import_controller import ImportControllerMixin
from .inspector_controls import InspectorControlsMixin
from .interface_settings import InterfaceSettingsMixin
from .job_planner import JobPlannerMixin
from .layers_popup import LAYER_LOCK_ROLE, LayersPanel
from .planar_operations_actions import PlanarOperationsMixin
from .project_recovery import ProjectRecoveryMixin
from .ribbon import Ribbon
from .ribbon_actions import RibbonActionsMixin
from .selection_transform_controller import SelectionTransformControllerMixin
from .stock_simulation import StockSimulationMixin
from .text_editor import TextEditorMixin
from .two_sided_setup import TwoSidedSetupMixin
from .viewport import MeshViewport
from .workspace_commands import WorkspaceCommandsMixin


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


class MainWindow(
    AiReliefMixin,
    BackgroundJobControllerMixin,
    WorkspaceCommandsMixin,
    DirectSelectionMixin,
    SelectionTransformControllerMixin,
    GuidedWorkflowMixin,
    ImportControllerMixin,
    InspectorControlsMixin,
    BatchLayoutMixin,
    StockSimulationMixin,
    ProjectRecoveryMixin,
    TextEditorMixin,
    TwoSidedSetupMixin,
    JobPlannerMixin,
    InterfaceSettingsMixin,
    PlanarOperationsMixin,
    RibbonActionsMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.project_path: Path | None = None
        self._updating_transform_controls = False
        self._updating_text_controls = False
        self._updating_stock_controls = False
        self._updating_project_list = False
        self._updating_object_selector = False
        self._init_import_controller()
        self._init_background_job_controller()
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
        self._prepared_toolpath_geometry: dict[str, object] | None = None
        self._prepared_toolpath_stats: dict[str, object] | None = None
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

        status = self._build_status_bar()
        self._install_import_status_widget(status)
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
        self.viewport.shapeDragUpdated.connect(self._shape_drag_updated)
        self.viewport.freehandStrokeRequested.connect(
            self._freehand_pen_drawn
        )
        self.viewport.nodeMoveRequested.connect(self._node_drag_finished)
        self.viewport.nodeEditModeChanged.connect(self._node_edit_mode_changed)
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

        guide_button = QPushButton("Guided CNC Job")
        guide_button.setObjectName("TitleQuickButton")
        guide_button.setToolTip(
            "Step-by-step stock, machine, fixtures, toolpaths, "
            "simulation, CNC preflight and export."
        )
        guide_button.clicked.connect(self._show_guided_workflow)
        line.addWidget(guide_button)

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

        # One selection model for Layers, the viewport, and the Inspector.
        # The Layers section is permanently embedded at the Inspector's top.
        self.layers_popup = LayersPanel(
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
        self._viewport_action_bar = canvas_bar
        canvas_bar.installEventFilter(self)
        canvas_bar_layout = QHBoxLayout(canvas_bar)
        canvas_bar_layout.setContentsMargins(7, 4, 7, 4)
        canvas_bar_layout.setSpacing(5)

        canvas_bar_layout.addWidget(QLabel("Object"))
        self.object_selector = QComboBox()
        self.object_selector.setObjectName("ObjectSelector")
        self.object_selector.setMinimumWidth(130)
        self.object_selector.setMaximumWidth(275)
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
            "Focus the Layers section at the top of the Inspector."
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
        self._viewport_fit_button = fit_button
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
        self._viewport_import_button = import_button
        canvas_bar_layout.addWidget(import_button)

        overflow = QToolButton(canvas_bar)
        overflow.setObjectName("ViewportOverflowButton")
        overflow.setText("⋯")
        overflow.setToolTip(
            "Workspace actions: Import, Fit, Inspector, Layers and CNC guide"
        )
        overflow.setAccessibleName("More viewport actions")
        overflow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(overflow)
        menu.addAction(self._ui_actions["import"])
        menu.addAction(self._ui_actions["fit_view"])
        menu.addAction(self._ui_actions["layers"])
        menu.addSeparator()
        toggle_inspector = menu.addAction("Show / Hide Inspector")
        toggle_inspector.triggered.connect(
            self._toggle_properties_panel_option
        )
        menu.addAction(self._ui_actions["guided_workflow"])
        overflow.setMenu(menu)
        self._viewport_overflow_button = overflow
        canvas_bar_layout.addWidget(overflow)
        self._viewport_quick_controls = (
            import_button, fit_button, self.inspector_button,
        )
        canvas_layout.addWidget(canvas_bar)

        self.tool_options_bar = QWidget()
        self.tool_options_bar.setObjectName("ToolOptionsBar")
        tool_options_layout = QHBoxLayout(self.tool_options_bar)
        tool_options_layout.setContentsMargins(7, 4, 7, 4)
        tool_options_layout.setSpacing(5)

        self.tool_options_title = QLabel("Tool")
        self.tool_options_title.setObjectName("ToolOptionsTitle")
        tool_options_layout.addWidget(self.tool_options_title)

        self.tool_options_depth_label = QLabel("Depth")
        tool_options_layout.addWidget(self.tool_options_depth_label)
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

        self.tool_options_fixture_top_label = QLabel("Top Z")
        tool_options_layout.addWidget(self.tool_options_fixture_top_label)
        self.tool_options_fixture_top_spin = QDoubleSpinBox()
        self.tool_options_fixture_top_spin.setObjectName("FixtureTopZ")
        self.tool_options_fixture_top_spin.setRange(-100000, 100000)
        self.tool_options_fixture_top_spin.setDecimals(3)
        self.tool_options_fixture_top_spin.setValue(self._fixture_top_z_mm)
        self.tool_options_fixture_top_spin.setSuffix(" mm")
        self.tool_options_fixture_top_spin.setToolTip(
            "Fixture top relative to stock-top Z0. For a fence measured "
            "from the bed, subtract stock thickness from fence height."
        )
        self.tool_options_fixture_top_spin.setMaximumWidth(120)
        self.tool_options_fixture_top_spin.valueChanged.connect(
            self._fixture_top_changed
        )
        tool_options_layout.addWidget(self.tool_options_fixture_top_spin)

        self.tool_options_fixture_clearance_label = QLabel("Margin")
        tool_options_layout.addWidget(self.tool_options_fixture_clearance_label)
        self.tool_options_fixture_clearance_spin = QDoubleSpinBox()
        self.tool_options_fixture_clearance_spin.setObjectName("FixtureMargin")
        self.tool_options_fixture_clearance_spin.setRange(0, 100000)
        self.tool_options_fixture_clearance_spin.setDecimals(3)
        self.tool_options_fixture_clearance_spin.setValue(
            self._fixture_clearance_mm
        )
        self.tool_options_fixture_clearance_spin.setSuffix(" mm")
        self.tool_options_fixture_clearance_spin.setToolTip(
            "Extra XY/Z safety margin beyond the cutter radius."
        )
        self.tool_options_fixture_clearance_spin.setMaximumWidth(120)
        self.tool_options_fixture_clearance_spin.valueChanged.connect(
            self._fixture_clearance_changed
        )
        tool_options_layout.addWidget(
            self.tool_options_fixture_clearance_spin
        )

        self.tool_options_fixture_size_label = QLabel(
            "Drag a rectangle on the stock to place a fixture"
        )
        self.tool_options_fixture_size_label.setObjectName(
            "ToolFixtureSize"
        )
        tool_options_layout.addWidget(self.tool_options_fixture_size_label)

        self.tool_options_measure_label = QLabel(
            "Drag two points on stock top (XY · Z0)"
        )
        self.tool_options_measure_label.setObjectName("ToolMeasureResult")
        self.tool_options_measure_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        tool_options_layout.addWidget(self.tool_options_measure_label)
        self.tool_options_measure_clear = QPushButton("Clear")
        self.tool_options_measure_clear.setObjectName("ToolMeasureClear")
        self.tool_options_measure_clear.clicked.connect(
            self._clear_measurement
        )
        tool_options_layout.addWidget(self.tool_options_measure_clear)

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
        self.tool_options_fixture_top_label.hide()
        self.tool_options_fixture_top_spin.hide()
        self.tool_options_fixture_clearance_label.hide()
        self.tool_options_fixture_clearance_spin.hide()
        self.tool_options_fixture_size_label.hide()
        self.tool_options_measure_label.hide()
        self.tool_options_measure_clear.hide()
        canvas_layout.addWidget(self.tool_options_bar)

        self.viewport = MeshViewport(self.project)
        canvas_layout.addWidget(self.viewport, 1)

        self.properties_panel = Panel("Inspector")
        self.properties_panel.setObjectName("InspectorPanel")
        # Keep the inspector useful at a compact canvas-friendly width while
        # preventing users from collapsing it until controls become unusable.
        self.properties_panel.setMinimumWidth(260)
        self.properties_panel.body_layout.addWidget(self.layers_popup)

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

    def _update_viewport_action_density(self, available_width: int) -> None:
        """Keep essential object/CAM controls visible without clipping.

        Less frequent actions remain accessible through the always-visible
        overflow menu, even on narrower splitters or a 1050px app window.
        """
        if not hasattr(self, "_viewport_quick_controls"):
            return
        import_button, fit_button, inspector_button = (
            self._viewport_quick_controls
        )
        import_button.setVisible(available_width >= 1030)
        fit_button.setVisible(available_width >= 900)
        inspector_button.setVisible(available_width >= 790)
        self.generate_toolpaths_button.setText(
            "Toolpaths…" if available_width < 770
            else "Generate Toolpaths"
        )

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is getattr(self, "_viewport_action_bar", None)
            and event.type() == QEvent.Type.Resize
        ):
            self._update_viewport_action_density(event.size().width())
        return super().eventFilter(watched, event)

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
        self._prepared_toolpath_geometry = None
        self._prepared_toolpath_stats = None
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
                list_item = QListWidgetItem(project_item.name)
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
                    + "\nEye: show/hide • Lock: protect from edits"
                    + "\nDouble-click name or press F2 to rename."
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
                list_item.setData(LAYER_LOCK_ROLE, project_item.locked)
                if project_item.locked:
                    list_item.setFlags(
                        list_item.flags() & ~Qt.ItemFlag.ItemIsEditable
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
        """Reveal and focus the permanently embedded Inspector Layers list."""
        if not hasattr(self, "layers_popup"):
            return
        self._ensure_inspector_visible()
        self.properties_panel.scroll_area.ensureWidgetVisible(self.layers_popup)
        self.project_list.setFocus(Qt.FocusReason.OtherFocusReason)

    def _active_cutter_changed(self, _index: int) -> None:
        cutter = self.tool_combo.currentData()
        if hasattr(self, "_cutter_menu_actions"):
            current = self.tool_combo.currentIndex()
            for index, action in enumerate(self._cutter_menu_actions):
                action.setChecked(index == current)
        if cutter is not None and hasattr(cutter, "name"):
            self._settings.setValue("tools/selected_name", cutter.name)
            self._settings.sync()
            # Generated toolpaths carry their own cutter geometry; changing
            # the UI's *next* cutter must never erase earlier cutter stages.
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
        locked = bool(list_item.data(LAYER_LOCK_ROLE))
        lock_changed = locked != project_item.locked
        project_item.locked = locked

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
        if renamed and project_item.locked:
            self._updating_project_list = True
            try:
                list_item.setText(project_item.name)
            finally:
                self._updating_project_list = False
            renamed = False
        if lock_changed:
            flags = list_item.flags()
            list_item.setFlags(
                flags & ~Qt.ItemFlag.ItemIsEditable
                if locked else flags | Qt.ItemFlag.ItemIsEditable
            )
            if locked:
                self.viewport.set_node_edit_mode(False)
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
        elif lock_changed:
            state = "locked" if locked else "unlocked"
            self.statusBar().showMessage(
                f"{project_item.name} {state}", 2500,
            )
        elif visibility_changed:
            state = "visible" if visible else "hidden"
            self.statusBar().showMessage(
                f"{project_item.name} {state}",
                2000,
            )

        if lock_changed:
            self._update_properties(self.project_list.currentRow())
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
            ("Frame Selected", "Shift+F", self._frame_selected),
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

    def _set_project(
        self,
        project: Project,
        *,
        project_path: Path | None,
        selected_row: int = 0,
    ) -> None:
        self.viewport.set_node_edit_mode(False)
        self.project = project
        self.project_path = project_path
        self._toolpaths_stale_reason = None
        self._prepared_toolpath_geometry = None
        self._prepared_toolpath_stats = None
        self.project_title_label.setText(f"  •  {project.name} Project")
        self.viewport.set_project(project)
        self._measurement = None
        if hasattr(self, "tool_options_measure_label"):
            self.tool_options_measure_label.setText(
                "Drag two points on stock top (XY · Z0)"
            )
        self._refresh_project_list(selected_row)
        self._sync_toolpath_state_from_project()

    def _undo(self) -> None:
        self.statusBar().showMessage("Nothing to undo", 3000)

    def _new_project(self) -> None:
        self._set_project(Project(), project_path=None)
        self.statusBar().showMessage("New project created", 3000)

    def _open_project(self) -> None:
        if self._background_job is not None:
            self.statusBar().showMessage("Another operation is running", 4000)
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open CarveFoundry Project",
            str(self.project_path.parent if self.project_path else Path.home()),
            f"CarveFoundry Projects (*{PROJECT_SUFFIX});;All files (*)",
        )
        if not path:
            return
        project_path = Path(path)

        def load(progress):
            progress(0.05, "Reading project and embedded assets")
            project = load_project(project_path)
            progress(0.95, "Project loaded")
            return project

        def done(result):
            self._set_project(result, project_path=project_path)
            self.statusBar().showMessage(f"Opened {project_path.name}", 5000)

        self._start_background_job(
            "Open project", task=load, on_done=done,
            indeterminate=True,
        )

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
        if self._background_job is not None:
            self.statusBar().showMessage("Another operation is running", 4000)
            return
        project = self.project
        if project.name == "Untitled":
            project.name = path.stem

        def save(progress):
            progress(0.05, "Compressing project and embedded assets")
            saved = save_project(project, path)
            progress(0.95, "Project written")
            return saved

        def done(saved_path):
            self.project_path = saved_path
            self.project_title_label.setText(f"  •  {project.name} Project")
            self.statusBar().showMessage(f"Saved {saved_path.name}", 5000)

        self._start_background_job(
            "Save project", task=save, on_done=done,
            indeterminate=True,
        )

    def _export_gcode(self) -> None:
        toolpaths = self.project.toolpaths
        if not toolpaths:
            self.statusBar().showMessage(
                "No calculated toolpaths to export", 5000
            )
            return
        base_directory = self.project_path.parent if self.project_path else Path.home()
        toolpath = toolpaths[0]
        project_name = (
            self.project.name if self.project.name != "Untitled"
            else toolpath.name
        )
        suggested = base_directory / f"{project_name}.nc"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export G-code", str(suggested),
            "G-code (*.nc *.gcode *.tap *.cnc);;All files (*)",
        )
        if not path:
            self.statusBar().showMessage("G-code export canceled", 3000)
            return
        request = GcodeRequest(
            toolpaths=list(toolpaths),
            path=path,
            settings=self._grbl_post_settings(),
            stock=self.project.stock,
            machine_profile=self._active_machine_profile(),
            fixtures=tuple(self.project.fixtures),
        )

        def done(result):
            output_files = [Path(name) for name in result["files"]]
            self._set_activity_info(
                f"G-code exported\nFiles: {len(output_files)}\n"
                + "\n".join(str(file) for file in output_files)
                + f"\n\nOperations: {result['summary']}\n"
                + f"Moves: {result['moves']:,}\n"
                + f"Estimated cutting: {result['minutes']:.1f} min "
                "(rapids excluded)\n"
                + (
                    "One program per cutter stage. Stop, change and "
                    "re-probe the cutter before running the next file."
                    if len(output_files) > 1 else ""
                )
            )
            self.statusBar().showMessage(
                f"Exported {len(output_files)} G-code file(s)", 5000
            )

        def failed(message: str) -> None:
            self._set_activity_info(f"G-code export blocked/failed\n{message}")
            QMessageBox.warning(
                self, "G-code export blocked by preflight", message
            )
            self.statusBar().showMessage("G-code export blocked", 8000)

        self._start_background_job(
            "Export G-code", request=request, on_done=done,
            on_failed=failed,
        )

    def closeEvent(self, event) -> None:
        if (
            self._background_job is not None
            or (self._import_thread is not None and self._import_thread.isRunning())
        ):
            self.statusBar().showMessage(
                "Finish or cancel the current operation before closing",
                5000,
            )
            event.ignore()
            return
        self._simulation_timer.stop()
        if self.machine_controller.connected:
            self.machine_controller.disconnect()
        self._save_interface_options()
        super().closeEvent(event)

