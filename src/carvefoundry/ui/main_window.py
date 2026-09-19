from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6.QtCore import QItemSelectionModel, QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QKeySequence
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
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..cam.job_process import GcodeRequest
from ..core.mesh import mesh_asset_from_geometry
from ..core.planar_operations import PLANAR_KINDS
from ..core.project import Project, ProjectItem
from ..core.project_file import (
    PROJECT_SUFFIX,
    load_project,
    save_project,
)
from ..core.transform import Transform3D
from ..core.units import ModelUnits
from .background_jobs import BackgroundWorker, JobCallbacks, JobState
from .import_worker import ImportWorker
from .interface_settings import InterfaceSettingsMixin
from .layers_popup import LayersPopup
from .planar_operations_actions import PlanarOperationsMixin
from .ribbon import Ribbon
from .ribbon_actions import RibbonActionsMixin
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
    WorkspaceCommandsMixin,
    TextEditorMixin,
    TwoSidedSetupMixin,
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
        self._import_thread: QThread | None = None
        self._import_worker: ImportWorker | None = None
        self._import_target_project: Project | None = None
        self._background_job: JobState | None = None
        self._job_bridge: JobCallbacks | None = None
        self._job_target_project: Project | None = None
        self._job_action_states: dict[str, bool] = {}
        self._job_rail_states: dict[str, bool] = {}
        self._job_camera_was_active = True
        self._job_draw_mode: str | None = None
        self._job_sequence = 0
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

        status = QStatusBar()
        self.import_progress = QProgressBar()
        self.import_progress.setObjectName("ImportProgress")
        self.import_progress.setFixedWidth(300)
        self.import_progress.setTextVisible(True)
        self.import_progress.setFormat("Import · %p%")
        self.import_progress.hide()
        status.addPermanentWidget(self.import_progress)

        self.toolpath_progress = QProgressBar()
        self.toolpath_progress.setObjectName("ToolpathProgress")
        self.toolpath_progress.setRange(0, 100)
        self.toolpath_progress.setValue(0)
        self.toolpath_progress.setFixedWidth(320)
        self.toolpath_progress.setTextVisible(True)
        self.toolpath_progress.setFormat("Toolpath generation · %p%")
        self.toolpath_progress.hide()
        status.addPermanentWidget(self.toolpath_progress)

        self.job_progress = QProgressBar()
        self.job_progress.setObjectName("BackgroundJobProgress")
        self.job_progress.setFixedWidth(320)
        self.job_progress.setTextVisible(True)
        self.job_progress.hide()
        status.addPermanentWidget(self.job_progress)

        self.cancel_job_button = QPushButton("Cancel")
        self.cancel_job_button.setObjectName("CancelBackgroundJob")
        self.cancel_job_button.clicked.connect(self._cancel_background_job)
        self.cancel_job_button.hide()
        status.addPermanentWidget(self.cancel_job_button)

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
        self.viewport.shapeDragUpdated.connect(self._shape_drag_updated)
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

    def _build_transform_controls(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("TransformControls")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 6, 0, 10)
        layout.setSpacing(6)

        heading = QLabel("Model transform")
        heading.setObjectName("SectionHeading")
        layout.addWidget(heading)

        resize_hint = QLabel(
            "Drag a corner handle around the selected object in the viewport "
            "to resize its XY footprint live. Z/depth stays unchanged."
        )
        resize_hint.setObjectName("Muted")
        resize_hint.setWordWrap(True)
        layout.addWidget(resize_hint)

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

        self.transform_orientation_combo = QComboBox()
        self.transform_orientation_combo.addItem("Global", "global")
        self.transform_orientation_combo.addItem("Local", "local")
        self.transform_orientation_combo.setToolTip(
            "Global uses stock/world XYZ axes. Local rotates the move gizmo "
            "with the selected object."
        )
        self._configure_inspector_field(self.transform_orientation_combo)
        self.transform_orientation_combo.currentIndexChanged.connect(
            self._transform_orientation_changed
        )
        units_form.addRow("Gizmo orientation", self.transform_orientation_combo)

        self.transform_snap_check = QCheckBox("Snap translation")
        self.transform_snap_check.setToolTip(
            "Snap gizmo moves to a fixed increment. Ctrl temporarily enables "
            "snapping during a drag."
        )
        self.transform_snap_check.toggled.connect(
            self._transform_snap_changed
        )
        units_form.addRow("Precision", self.transform_snap_check)

        self.transform_snap_step_spin = QDoubleSpinBox()
        self.transform_snap_step_spin.setRange(0.001, 1000.0)
        self.transform_snap_step_spin.setDecimals(3)
        self.transform_snap_step_spin.setSingleStep(0.5)
        self.transform_snap_step_spin.setSuffix(" mm")
        self.transform_snap_step_spin.setValue(1.0)
        self.transform_snap_step_spin.setToolTip(
            "Translation snapping increment in millimeters."
        )
        self._configure_inspector_field(self.transform_snap_step_spin)
        self.transform_snap_step_spin.valueChanged.connect(
            self._transform_snap_changed
        )
        units_form.addRow("Snap step", self.transform_snap_step_spin)

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

        apply_bar = QWidget()
        apply_bar.setMinimumWidth(0)
        apply_layout = QHBoxLayout(apply_bar)
        apply_layout.setContentsMargins(0, 0, 0, 0)
        apply_layout.setSpacing(6)

        apply_scale_button = QPushButton("Apply Scale")
        apply_scale_button.setMinimumWidth(0)
        apply_scale_button.setToolTip(
            "Bake the selected object's current scale into its mesh and reset "
            "Scale to 1,1,1. Useful before CAM/export."
        )
        apply_scale_button.clicked.connect(self._apply_selected_scale)
        apply_layout.addWidget(apply_scale_button)

        apply_rotation_scale_button = QPushButton("Apply R+S")
        apply_rotation_scale_button.setMinimumWidth(0)
        apply_rotation_scale_button.setToolTip(
            "Bake rotation and scale into the selected mesh while preserving "
            "its placed position."
        )
        apply_rotation_scale_button.clicked.connect(
            self._apply_selected_rotation_scale
        )
        apply_layout.addWidget(apply_rotation_scale_button)
        layout.addWidget(apply_bar)

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

        has_bakeable_mesh = any(
            0 <= index < len(self.project.items)
            and self.project.items[index].mesh is not None
            and self.project.items[index].kind.lower() != "text"
            for index in indices
        )
        for key, enabled in (
            ("frame_selected", has_selection),
            ("isolate_selected", has_selection),
            ("exit_isolate", self.viewport.isolated),
            ("apply_scale", has_bakeable_mesh),
            ("apply_rotation_scale", has_bakeable_mesh),
        ):
            action = self._ui_actions.get(key)
            if action is not None:
                action.setEnabled(enabled)

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

        planar_selection = bool(indices) and all(
            self.project.items[index].mesh is not None
            and self.project.items[index].kind.lower() in PLANAR_KINDS
            for index in indices
        )
        for key, enabled in (
            ("vector_union", planar_selection and selection_count >= 2),
            ("vector_subtract", planar_selection and selection_count >= 2),
            ("vector_intersect", planar_selection and selection_count >= 2),
            ("vector_offset", planar_selection and selection_count == 1),
        ):
            self._ui_actions[key].setEnabled(enabled)

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
        if self.viewport.transform_interaction_kind == "resize-object":
            reason = (
                "Text size"
                if item.kind.lower() == "text"
                else "Model size"
            )
            self._invalidate_toolpaths(reason)
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

    def _frame_selected(self) -> None:
        if not self.viewport.frame_selected():
            self.statusBar().showMessage(
                "Select one or more visible design objects to frame",
                3000,
            )
            return
        self.statusBar().showMessage("Framed selected object(s)", 2000)

    def _isolate_selected(self) -> None:
        if not self.viewport.isolate_selected():
            self.statusBar().showMessage(
                "Select one or more visible design objects to isolate",
                3000,
            )
            return
        self._sync_selection_action_state()
        self.statusBar().showMessage(
            "Isolate view enabled • CAM still uses the full project",
            3500,
        )

    def _exit_isolate(self) -> None:
        if not self.viewport.isolated:
            self.statusBar().showMessage("Isolate view is not active", 2000)
            return
        self.viewport.show_all_items()
        self._sync_selection_action_state()
        self.statusBar().showMessage("Returned to full project view", 2000)

    def _set_transform_orientation(self, orientation: str) -> None:
        normalized = str(orientation).strip().lower()
        self.viewport.set_transform_orientation(normalized)
        if hasattr(self, "transform_orientation_combo"):
            index = self.transform_orientation_combo.findData(normalized)
            if index >= 0:
                self.transform_orientation_combo.blockSignals(True)
                try:
                    self.transform_orientation_combo.setCurrentIndex(index)
                finally:
                    self.transform_orientation_combo.blockSignals(False)
        for key, target in (
            ("transform_global", "global"),
            ("transform_local", "local"),
        ):
            action = self._ui_actions.get(key)
            if action is not None:
                action.setChecked(normalized == target)
        self._settings.setValue("viewport/transform_orientation", normalized)
        self.statusBar().showMessage(
            f"Transform orientation: {normalized.title()}",
            2000,
        )

    def _transform_orientation_changed(self, _index: int) -> None:
        orientation = self.transform_orientation_combo.currentData()
        if orientation in {"global", "local"}:
            self._set_transform_orientation(str(orientation))

    def _transform_snap_changed(self, _value=None) -> None:
        enabled = self.transform_snap_check.isChecked()
        step = float(self.transform_snap_step_spin.value())
        self.transform_snap_step_spin.setEnabled(enabled)
        self.viewport.set_transform_snapping(enabled, step)
        action = self._ui_actions.get("snap_transform")
        if action is not None:
            action.setChecked(enabled)
        self._settings.setValue("viewport/transform_snap_enabled", enabled)
        self._settings.setValue("viewport/transform_snap_step_mm", step)

    def _toggle_transform_snap(self) -> None:
        self.transform_snap_check.setChecked(
            not self.transform_snap_check.isChecked()
        )

    def _apply_selected_transform_components(
        self,
        *,
        apply_rotation: bool,
        apply_scale: bool,
        label: str,
    ) -> None:
        indices = self._selected_design_indices(expand_groups=True)
        if not indices:
            self.statusBar().showMessage(
                "Select one or more mesh objects first",
                3000,
            )
            return

        self._before_ribbon_mutation(label)
        changed = 0
        skipped_text = 0
        selected_after = list(indices)

        for index in indices:
            if not 0 <= index < len(self.project.items):
                continue
            item = self.project.items[index]
            if item.mesh is None:
                continue
            if item.kind.lower() == "text":
                skipped_text += 1
                continue

            rotation = (
                item.transform.rotation_deg
                if apply_rotation
                else (0.0, 0.0, 0.0)
            )
            scale = (
                item.transform.scale_xyz
                if apply_scale
                else (1.0, 1.0, 1.0)
            )
            rotation_changed = any(abs(value) > 1e-9 for value in rotation)
            scale_changed = any(abs(value - 1.0) > 1e-9 for value in scale)
            if not rotation_changed and not scale_changed:
                continue

            source_mesh_mm = item.source_mesh_mm()
            if source_mesh_mm is None:
                continue
            baked = Transform3D(
                rotation_deg=rotation,
                scale_xyz=scale,
            ).apply_to_mesh(source_mesh_mm)

            translation = item.transform.translation_mm
            remaining_rotation = (
                (0.0, 0.0, 0.0)
                if apply_rotation
                else item.transform.rotation_deg
            )
            remaining_scale = (
                (1.0, 1.0, 1.0)
                if apply_scale
                else item.transform.scale_xyz
            )
            item.mesh = mesh_asset_from_geometry(baked)
            item.source_units = ModelUnits.MILLIMETERS
            item.source_path = None
            item.transform = Transform3D(
                translation_mm=translation,
                rotation_deg=remaining_rotation,
                scale_xyz=remaining_scale,
            )
            changed += 1

        if changed:
            self._invalidate_toolpaths("Applied model transform")
            self._refresh_project_list(self.project_list.currentRow())
            valid_selection = [
                index
                for index in selected_after
                if 0 <= index < len(self.project.items)
            ]
            if valid_selection:
                self._select_project_indices(
                    valid_selection,
                    primary=valid_selection[-1],
                )
            self.viewport.update()

        self._after_ribbon_mutation(label, bool(changed))
        if changed:
            suffix = (
                f" • skipped {skipped_text} editable text object"
                f"{'s' if skipped_text != 1 else ''}"
                if skipped_text
                else ""
            )
            self.statusBar().showMessage(
                f"{label.title()} on {changed} object"
                f"{'s' if changed != 1 else ''}{suffix}",
                4500,
            )
        elif skipped_text:
            self.statusBar().showMessage(
                "Editable text keeps its live font transform; "
                "Apply Transform is for mesh-based objects",
                4500,
            )
        else:
            self.statusBar().showMessage(
                "Selected object transform is already applied",
                3000,
            )

    def _apply_selected_scale(self) -> None:
        self._apply_selected_transform_components(
            apply_rotation=False,
            apply_scale=True,
            label="apply scale",
        )

    def _apply_selected_rotation_scale(self) -> None:
        self._apply_selected_transform_components(
            apply_rotation=True,
            apply_scale=True,
            label="apply rotation and scale",
        )

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

    def _start_background_job(
        self,
        title: str,
        *,
        task=None,
        request=None,
        on_done=None,
        on_failed=None,
        cam_progress: bool = False,
        indeterminate: bool = False,
    ) -> bool:
        """Run one costly operation off the GUI thread with reusable progress UI."""

        if self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        ):
            self.statusBar().showMessage("Another operation is already running", 4000)
            return False
        worker = BackgroundWorker(task, process_request=request)
        thread = QThread(self)
        worker.moveToThread(thread)
        state = JobState(worker, thread)
        self._background_job = state
        self._job_target_project = self.project
        self._job_sequence += 1
        job_id = self._job_sequence
        self._job_action_states = {
            key: action.isEnabled()
            for key, action in self._ui_actions.items()
        }
        # Camera, view and selection remain usable. Design and machine commands
        # are disabled to keep the snapshot stable until the worker completes.
        safe_actions = {
            "camera", "view_fit", "frame_selected", "view_2d",
            "perspective", "orthographic", "isometric", "view_top",
            "view_bottom", "view_front", "view_back", "view_left",
            "view_right", "stock", "grid", "rulers", "toolpaths",
            "rapids", "layers", "inspector", "status_bar",
            "view_controls", "reverse_horizontal", "invert_vertical",
        }
        for key, action in self._ui_actions.items():
            if key not in safe_actions:
                action.setEnabled(False)
        if self.generate_toolpaths_button is not None:
            self.generate_toolpaths_button.setEnabled(False)
        # Protect the job snapshot without blocking navigation or repaints.
        self._job_camera_was_active = self.viewport.camera_control_mode
        self._job_draw_mode = self.viewport.shape_draw_mode
        self.viewport.set_shape_draw_mode(None)
        self.viewport.set_camera_control_mode(True)
        self.tool_rail.set_active_tool("camera")
        self._job_rail_states = {
            key: button.isEnabled()
            for key, button in self.tool_rail.buttons.items()
        }
        for key, button in self.tool_rail.buttons.items():
            if key not in {"camera", "view"}:
                button.setEnabled(False)
        self.properties_panel.setEnabled(False)
        self.tool_combo.setEnabled(False)
        self.job_progress.setRange(0, 0 if indeterminate else 100)
        self.job_progress.setValue(0)
        self.job_progress.setFormat(title if indeterminate else f"{title} · %p%")
        self.job_progress.show()
        self.cancel_job_button.setEnabled(True)
        self.cancel_job_button.setVisible(request is not None)
        self.statusBar().showMessage(f"{title}…")

        def progress(fraction: float, status: str) -> None:
            if job_id != self._job_sequence:
                return
            value = max(0, min(100, round(fraction * 100)))
            if not indeterminate:
                self.job_progress.setValue(value)
            self.job_progress.setFormat(
                status if indeterminate else f"{status} · %p%"
            )
            self.statusBar().showMessage(
                f"{title}: {status}" if indeterminate
                else f"{title}: {status} — {value}%"
            )
            if cam_progress:
                self._update_toolpath_progress(fraction, status)

        def completed(result: object) -> None:
            if self.project is not self._job_target_project:
                self.statusBar().showMessage(
                    f"{title}: project changed; result discarded", 7000
                )
                return
            try:
                if on_done is not None:
                    on_done(result)
                self.job_progress.setRange(0, 100)
                self.job_progress.setValue(100)
                self.job_progress.setFormat(f"{title} complete · %p%")
            except Exception as exc:  # noqa: BLE001 - always clean up the worker
                failed(f"{type(exc).__name__}: {exc}")

        def failed(message: str) -> None:
            if on_failed is not None:
                on_failed(message)
            else:
                self._set_activity_info(f"{title} failed\n{message}")
                self.statusBar().showMessage(f"{title} failed: {message}", 9000)
            self.job_progress.setFormat(f"{title} failed")

        def cancelled() -> None:
            self.job_progress.setFormat(f"{title} canceled")
            self.statusBar().showMessage(f"{title} canceled", 5000)
            if cam_progress:
                self._finish_toolpath_progress(
                    success=False, message="Generation canceled"
                )

        def cleaned_up() -> None:
            if job_id != self._job_sequence:
                return
            self._background_job = None
            self._job_bridge = None
            self._job_target_project = None
            self.cancel_job_button.hide()
            for key, was_enabled in self._job_action_states.items():
                action = self._ui_actions.get(key)
                if action is not None:
                    action.setEnabled(was_enabled)
            self._job_action_states = {}
            for key, was_enabled in self._job_rail_states.items():
                button = self.tool_rail.buttons.get(key)
                if button is not None:
                    button.setEnabled(was_enabled)
            self._job_rail_states = {}
            self.properties_panel.setEnabled(True)
            self.tool_combo.setEnabled(True)
            self.viewport.set_camera_control_mode(self._job_camera_was_active)
            if not self._job_camera_was_active:
                self.viewport.set_shape_draw_mode(self._job_draw_mode)
                self.tool_rail.set_active_tool(
                    self._job_draw_mode or "select"
                )
            else:
                self.tool_rail.set_active_tool("camera")
            self._sync_toolpath_output_state()
            self._sync_selection_action_state()
            if hasattr(self, "_sync_history_action_state"):
                self._sync_history_action_state()
            if self.generate_toolpaths_button is not None:
                self.generate_toolpaths_button.setEnabled(True)
            QTimer.singleShot(
                1800,
                lambda bar=self.job_progress: (
                    bar.hide() if self._background_job is None else None
                ),
            )

        bridge = JobCallbacks(
            self,
            progress=progress,
            completed=completed,
            failed=failed,
            cancelled=cancelled,
            cleaned_up=cleaned_up,
        )
        self._job_bridge = bridge
        thread.started.connect(worker.run)
        worker.progress.connect(bridge.on_progress)
        worker.completed.connect(bridge.on_completed)
        worker.failed.connect(bridge.on_failed)
        worker.cancelled.connect(bridge.on_cancelled)
        for signal in (worker.completed, worker.failed, worker.cancelled):
            signal.connect(thread.quit)
            signal.connect(worker.deleteLater)
        thread.finished.connect(bridge.on_cleaned_up)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        return True

    def _cancel_background_job(self) -> None:
        state = self._background_job
        if state is None:
            return
        self.cancel_job_button.setEnabled(False)
        self.statusBar().showMessage("Cancelling operation…")
        state.worker.cancel()

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

    def _import_file(self, kind: str | None = None) -> None:
        if self._background_job is not None or (
            self._import_thread is not None and self._import_thread.isRunning()
        ):
            self.statusBar().showMessage("Another operation is running", 3000)
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
        if index > total:
            self.import_progress.setRange(0, max(1, total))
            self.import_progress.setValue(max(1, total))
            self.import_progress.setFormat("Import ready · %p%")
            self.statusBar().showMessage("Finalizing imported items…")
        elif total <= 1:
            self.import_progress.setRange(0, 0)
            self.import_progress.setFormat(f"Loading {name}…")
            self.statusBar().showMessage(f"Loading {name}…")
        else:
            self.import_progress.setRange(0, total)
            self.import_progress.setValue(max(0, index - 1))
            self.import_progress.setFormat(f"{name} · %p%")
            self.statusBar().showMessage(
                f"Loading {name} ({index}/{total})…"
            )

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

