"""Regression coverage for split interaction/CAM modules and shared UI context."""
from __future__ import annotations

import trimesh
from PySide6.QtWidgets import QApplication

from carvefoundry.core.mesh import mesh_asset_from_geometry
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.ui.contextual_tool_state import ToolOptionsState
from carvefoundry.ui.main_window import MainWindow
from carvefoundry.ui.native_viewport import _NativeOpenGLViewport
from carvefoundry.ui.job_utility_actions import JobUtilityActionsMixin
from carvefoundry.ui.project_edit_actions import ProjectEditActionsMixin
from carvefoundry.ui.ribbon_action_state import RibbonActionStateMixin
from carvefoundry.ui.ribbon_actions import RibbonActionsMixin
from carvefoundry.ui.ribbon_cam_actions import RibbonCamActionsMixin
from carvefoundry.ui.ribbon_design_tools import RibbonDesignToolsMixin
from carvefoundry.ui.ribbon_machine_actions import RibbonMachineActionsMixin
from carvefoundry.ui.smart_value_actions import SmartValueActionsMixin
from carvefoundry.ui.view_simulation_actions import ViewSimulationActionsMixin
from carvefoundry.ui.viewport_geometry import ViewportGeometryMixin
from carvefoundry.ui.viewport_interactions import ViewportInteractionMixin

_APP = QApplication.instance() or QApplication([])


def test_split_modules_still_compose_one_authoritative_window_and_renderer() -> None:
    assert issubclass(RibbonActionsMixin, RibbonActionStateMixin)
    assert issubclass(RibbonActionsMixin, ProjectEditActionsMixin)
    assert issubclass(RibbonActionsMixin, ViewSimulationActionsMixin)
    assert issubclass(RibbonActionsMixin, SmartValueActionsMixin)
    assert issubclass(RibbonActionsMixin, JobUtilityActionsMixin)
    assert issubclass(RibbonActionsMixin, RibbonDesignToolsMixin)
    assert issubclass(RibbonActionsMixin, RibbonCamActionsMixin)
    assert issubclass(RibbonActionsMixin, RibbonMachineActionsMixin)
    assert "_copy_selected_items" not in RibbonActionsMixin.__dict__
    assert "_smart_values_dialog" not in RibbonActionsMixin.__dict__
    assert "_export_tiled_gcode" not in RibbonActionsMixin.__dict__
    assert issubclass(_NativeOpenGLViewport, ViewportGeometryMixin)
    assert issubclass(_NativeOpenGLViewport, ViewportInteractionMixin)

    window = MainWindow()
    try:
        renderer = window.viewport._renderer
        assert renderer.project is window.project
        assert renderer.camera is window.viewport._renderer.camera
        assert renderer.camera_control_mode
        assert renderer._mesh_cache == {}  # No eager GL uploads during refactor.
        assert callable(renderer.pick_item)
        assert callable(renderer.mousePressEvent)
    finally:
        window.close()


def test_contextual_tool_modes_are_disjoint_except_common_depth() -> None:
    assert ToolOptionsState.for_mode(None) == ToolOptionsState()
    assert ToolOptionsState.for_mode("camera") == ToolOptionsState()
    for mode in ("rectangle", "ellipse", "polygon", "line", "pen", "text"):
        assert ToolOptionsState.for_mode(mode).depth
    for mode in ("measure", "fixture"):
        assert not ToolOptionsState.for_mode(mode).depth
    for mode in ("measure", "fixture", "polygon", "line", "pen", "text"):
        plan = ToolOptionsState.for_mode(mode)
        enabled = tuple(
            getattr(plan, group)
            for group in ("measure", "fixture", "polygon", "line", "pen", "text")
        )
        assert enabled.count(True) == 1


def test_paint_tool_visibility_and_inspector_context_recover_after_selection() -> None:
    window = MainWindow()
    try:
        window._activate_camera_tool()
        assert window.tool_options_bar.isHidden()
        window._activate_navigation_tool()
        assert window.tool_options_bar.isHidden()

        window._set_shape_tool("line")
        assert not window.tool_options_bar.isHidden()
        assert not window.tool_options_line_width_spin.isHidden()
        assert window.tool_options_pen_width_spin.isHidden()
        assert not window.tool_options_depth_spin.isHidden()

        window._set_shape_tool("pen")
        assert not window.tool_options_pen_width_spin.isHidden()
        assert window.tool_options_line_width_spin.isHidden()

        window._set_shape_tool("measure")
        assert not window.tool_options_measure_clear.isHidden()
        assert window.tool_options_depth_spin.isHidden()

        window._activate_navigation_tool()
        assert window.tool_options_bar.isHidden()

        mesh = mesh_asset_from_geometry(
            trimesh.creation.box(extents=(25, 20, 3))
        )
        one = ProjectItem("One", kind="stl", mesh=mesh)
        two = ProjectItem("Two", kind="stl", mesh=mesh)
        window._set_project(Project(items=[one, two]), project_path=None)
        assert not window.stock_widget.isHidden()
        assert window.transform_widget.isHidden()

        window._select_project_indices([0], primary=0)
        assert window.stock_widget.isHidden()
        assert not window.transform_widget.isHidden()
        assert window.text_widget.isHidden()

        window._select_project_indices([0, 1], primary=1)
        assert window.stock_widget.isHidden()
        assert window.transform_widget.isHidden()
        assert window.text_widget.isHidden()
        assert "2 objects selected" in window.selection_info.text()

        window._select_project_indices([])
        assert not window.stock_widget.isHidden()
        assert window.transform_widget.isHidden()
        assert window.viewport.camera_control_mode is False
    finally:
        window.close()
