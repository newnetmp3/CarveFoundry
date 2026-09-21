"""Initialize cross-cutting UI state used by ribbon action modules."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QDialog

from carvefoundry.cam.basic_ops import detail_for_stepover_fraction
from carvefoundry.core.project import ProjectItem

from .machine_control import MachineController
from .toolpath_preview import ToolpathPreviewWindow


class RibbonActionStateMixin:
    """Initialize shared state without owning command implementations."""

    def _init_ribbon_action_state(self) -> None:
        self._clipboard_items: list[ProjectItem] = []
        self._active_cam_operation = "finish"
        self._cam_append_to_job = False
        self._tabs_enabled = False
        self._active_shape_tool: str | None = None
        self._camera_tool_active = True
        self._shape_tool_buttons: dict[str, object] = {}
        self._navigation_tool_button = None
        self._camera_tool_button = None
        self._tool_option_depth_mm = 1.0
        self._tool_option_line_width_mm = 2.0
        self._tool_option_pen_width_mm = 2.0
        self._tool_option_pen_smoothing = 35
        self._tool_option_pen_spacing_mm = 0.35
        self._tool_option_pen_close_path = False
        self._tool_option_polygon_sides = 6
        self._tool_option_text = "Text"
        self._fixture_top_z_mm = 5.0
        self._fixture_clearance_mm = 2.0
        self._measurement = None
        self._cam_selector_widgets: dict[str, list[QComboBox]] = {}
        self._cam_detail_widgets: list[object] = []

        def saved_choice(
            key: str,
            default: str,
            allowed: tuple[str, ...],
        ) -> str:
            value = str(self._settings.value(key, default))
            return value if value in allowed else default

        self._cam_cut_type = saved_choice(
            "cam/design/cut_type",
            "Auto",
            ("Auto", "Pocket", "On Path", "Outside", "Inside"),
        )
        self._cam_direction = saved_choice(
            "cam/design/direction",
            "Smart Serpentine",
            (
                "Smart Serpentine",
                "Offset",
                "Raster X",
                "Raster Y",
                "Raster 45°",
                "Raster 135°",
            ),
        )
        self._cam_quality = saved_choice(
            "cam/design/quality",
            "Balanced 10%",
            (
                "Fast 15%",
                "Balanced 10%",
                "Detail 8%",
                "Fine 6%",
                "Custom",
            ),
        )
        preset_fraction = {
            "Fast 15%": 0.15,
            "Balanced 10%": 0.10,
            "Detail 8%": 0.08,
            "Fine 6%": 0.06,
        }.get(self._cam_quality, 0.10)
        default_detail = detail_for_stepover_fraction(preset_fraction)
        try:
            saved_detail = int(
                self._settings.value("cam/design/detail", default_detail)
            )
        except (TypeError, ValueError):
            saved_detail = default_detail
        self._cam_detail = max(0, min(100, saved_detail))
        self._cam_entry = saved_choice(
            "cam/design/entry",
            "Plunge",
            ("Plunge", "Ramp 5°", "Ramp 20°", "Custom Ramp"),
        )
        self._cam_linking = saved_choice(
            "cam/design/linking",
            "Smart Min-Lift",
            ("Smart Min-Lift", "Local Lift", "Full Retract"),
        )
        self._cam_milling = saved_choice(
            "cam/design/milling",
            "Default",
            ("Default", "Climb (CCW)", "Conventional (CW)"),
        )
        self._cam_3d_cut_style = saved_choice(
            "cam/design/3d_cut_style",
            "Model Boundary Relief",
            (
                "Model Boundary Relief",
                "Rectangle Relief",
                "Full Depth Cutout",
            ),
        )
        self._tabs_enabled = bool(
            self._settings.value("cam/tabs_enabled", False, type=bool)
        )
        if self._cam_3d_cut_style == "Full Depth Cutout" and not self._tabs_enabled:
            self._tabs_enabled = True
            self._settings.setValue("cam/tabs_enabled", True)
        self._custom_tools = self._load_custom_tools()

        self._simulation_timer = QTimer(self)
        self._simulation_timer.setInterval(40)
        self._simulation_timer.timeout.connect(self._advance_simulation)
        self._simulation_total_segments = 0
        self._simulation_button = None
        self._toolpaths_view_button = None
        self._rapids_view_button = None
        self._tabs_button = None
        self._jog_dialog: QDialog | None = None
        self._toolpath_preview_window: ToolpathPreviewWindow | None = None
        self._machine_connect_button = None

        self.machine_controller = MachineController(self)
        self.machine_controller.connectionChanged.connect(
            self._machine_connection_changed
        )
        self.machine_controller.lineReceived.connect(self._machine_line_received)
        self.machine_controller.errorOccurred.connect(self._machine_error)

