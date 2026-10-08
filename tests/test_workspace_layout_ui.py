"""Layout ergonomics and module-extraction regressions for desktop UI."""
from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
    QTableWidget,
)

from carvefoundry.cam.operation import CamOperation
from carvefoundry.cam.toolpath import Toolpath
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.core.vector_path import (
    VectorPath,
    VectorSegment,
    node_world_points,
    segment_world_controls,
    segment_world_point,
)
from carvefoundry.ui.cam_dialog_help import cam_generation_help
from carvefoundry.ui.inspector_controls import InspectorControlsMixin
from carvefoundry.ui.main_window import MainWindow
from carvefoundry.ui.project_window import MainWindow as ProjectMainWindow

_APP = QApplication.instance() or QApplication([])


def _model_window():
    window = MainWindow()
    window._set_project(
        Project(items=[ProjectItem(
            "Relief", kind="rectangle", mesh=rectangle_mesh(30, 20, 2),
        )]),
        project_path=None,
        selected_row=1,
    )
    return window


def test_accordion_is_compact_persistent_and_menu_focus_opens_collapsed_section():
    window = _model_window()
    # Native QOpenGLWindow must remain unshown in offscreen software CI.
    # Verify the accordion and spin's text-selection state without mapping it.
    original = {
        key: window._settings.value(f"interface/inspector_sections/{key}")
        for key in ("setup", "position", "rotation", "size", "scale")
    }
    try:
        assert isinstance(window, InspectorControlsMixin)
        sections = window._transform_sections
        assert set(sections) == {
            "setup", "position", "rotation", "size", "scale",
        }
        sections["rotation"].setExpanded(False)
        assert sections["rotation"].body.isHidden()
        window._focus_transform_section("rotation")
        assert sections["rotation"].isExpanded()
        # Offscreen Qt may focus the spin's embedded line edit, not the
        # outer QDoubleSpinBox itself; Select All proves menu focus worked.
        assert window.rotation_spins[0].lineEdit().selectedText()
        sections["scale"].setExpanded(False)
        assert sections["scale"].body.isHidden()

        window._settings.sync()
        # New window: the same section choice is restored from QSettings.
        second = _model_window()
        try:
            assert not second._transform_sections["scale"].isExpanded()
            assert second._transform_sections["rotation"].isExpanded()
        finally:
            second.close()
    finally:
        for key, value in original.items():
            storage = f"interface/inspector_sections/{key}"
            if value is None:
                window._settings.remove(storage)
            else:
                window._settings.setValue(storage, value)
        window._settings.sync()
        window.close()


def test_cam_help_is_pure_complete_and_all_fields_have_explanations():
    help_text = cam_generation_help()
    assert "source_summary" in help_text
    assert "operation" in help_text
    assert "readiness" in help_text
    assert len(help_text) >= 20
    assert all(name and description for name, description in help_text.values())


def test_cam_form_section_navigation_reuses_original_live_controls():
    window = _model_window()
    setting = window._settings.value("cam/show_step_navigation")
    try:
        window._settings.setValue("cam/show_step_navigation", True)
        dialog = window._build_toolpath_generation_dialog()
        nav = dialog.section_navigator
        assert dialog.generation_fields["section_nav"] is nav
        assert set(nav.buttons) == {
            "source", "cutter", "strategy", "depth", "motion",
            "tabs", "rest", "readiness",
        }
        assert all(
            key in dialog.generation_fields
            for key in ("operation", "cutter", "readiness")
        )
        assert not nav.buttons["rest"].isEnabled()
        assert "visible model" in (
            dialog.generation_fields["context_summary"].text()
        )
        dialog.show()
        _APP.processEvents()
        nav.navigate("motion")
        _APP.processEvents()
        assert nav.buttons["motion"].isChecked()
        assert (
            dialog.findChild(QPushButton, "CamStepsToggle")
            is not None
        )
        toggle = dialog.findChild(QPushButton, "CamStepsToggle")
        toggle.setChecked(False)
        assert nav.isHidden()
        toggle.setChecked(True)
        assert not nav.isHidden()

        operations = dialog.generation_fields["operation"]
        operations.setCurrentIndex(operations.findData("rest"))
        assert nav.buttons["rest"].isEnabled()
        assert nav.buttons["tabs"].isEnabled() is False
        assert not dialog.generation_fields["generate"].isEnabled()
        assert "3D Rest" in dialog.generation_fields["context_summary"].text()
        dialog.close()
    finally:
        if setting is None:
            window._settings.remove("cam/show_step_navigation")
        else:
            window._settings.setValue("cam/show_step_navigation", setting)
        window._settings.sync()
        window.close()


def test_viewport_toolbar_keeps_essential_cam_buttons_and_overflow_access():
    window = _model_window()
    try:
        menu_names = {
            action.text()
            for action in window._viewport_overflow_button.menu().actions()
            if not action.isSeparator()
        }
        assert {"Import…", "Fit View", "Layers", "Guided CNC Workflow…"}.issubset(
            menu_names
        )
        assert "Show / Hide Inspector" in menu_names
        window._update_viewport_action_density(680)
        assert window._viewport_import_button.isHidden()
        assert window._viewport_fit_button.isHidden()
        assert window.inspector_button.isHidden()
        assert window.generate_toolpaths_button.text() == "Toolpaths…"
        assert window.generate_toolpaths_button.isEnabled()
        window._update_viewport_action_density(1200)
        assert not window._viewport_import_button.isHidden()
        assert not window._viewport_fit_button.isHidden()
        assert not window.inspector_button.isHidden()
        assert window.generate_toolpaths_button.text() == "Generate Toolpaths"
    finally:
        window.close()


def test_guided_workflow_progress_and_snapshot_does_not_repaint_when_unchanged():
    window = _model_window()
    try:
        window._show_guided_workflow()
        first = window._guided_workflow_cache
        progress = window._guided_workflow_progress.value()
        assert first
        assert "Next:" in window._guided_workflow_next_hint.text()
        assert window._guided_workflow_next_button.isEnabled()
        window._refresh_guided_workflow()
        assert window._guided_workflow_cache == first
        assert window._guided_workflow_progress.value() == progress
        window.project.items.clear()
        window._refresh_guided_workflow()
        assert window._guided_workflow_cache != first
        assert window._guided_workflow_progress.value() < progress
        window._guided_workflow_dialog.close()
    finally:
        window.close()



def test_machining_operations_panel_reflects_persistent_job_and_disable_state():
    window = _model_window()
    try:
        item = window.project.items[0]
        cutter = Cutter("6 mm flat", ToolType.FLAT_END_MILL, 6.0)
        operation = CamOperation(
            operation="profile",
            cutter=cutter,
            source_item_ids=(item.item_id,),
            parameters={"feed_mm_min": 1000.0},
        )
        path = Toolpath(
            name="Profile",
            operation="profile",
            cutter=cutter,
            safe_z_mm=1.5,
            source_item_id=item.item_id,
            source_item_name=item.name,
            cam_operation_id=operation.operation_id,
        )
        window.project.cam_operations = [operation]
        window.project.toolpaths = [path]
        window._sync_toolpath_state_from_project()

        rows = window.machining_operations_list
        assert rows.count() == 1
        assert "Profile" in rows.item(0).text()
        assert "READY" in rows.item(0).text()
        assert "6 mm flat" in rows.item(0).text()
        assert rows.item(0).checkState() == Qt.CheckState.Checked

        rows.item(0).setCheckState(Qt.CheckState.Unchecked)
        _APP.processEvents()

        assert not operation.enabled
        assert window.project.toolpaths == []
        assert "DISABLED" in rows.item(0).text()
    finally:
        window.close()


def test_direct_selection_can_create_arc_and_bezier_segments_with_snap_controls():
    window = MainWindow()
    path = VectorPath(((0.0, 0.0), (20.0, 0.0)), width_mm=1.0, depth_mm=1.0)
    item = ProjectItem(
        "Editable curve",
        kind="pen",
        mesh=path.mesh_asset(),
        vector_path=path,
    )
    try:
        window._set_project(
            Project(items=[item]),
            project_path=None,
            selected_row=1,
        )
        window._activate_direct_selection()
        dialog = window._vector_node_dialog
        assert dialog is not None

        segment_kind = dialog.findChild(QComboBox, "VectorSegmentKind")
        arc_sweep = dialog.findChild(QDoubleSpinBox, "VectorArcSweep")
        apply_segment = dialog.findChild(QPushButton, "VectorApplySegment")
        snap_enabled = dialog.findChild(QCheckBox, "VectorSnapEnabled")
        snap_tolerance = dialog.findChild(QDoubleSpinBox, "VectorSnapTolerance")

        assert segment_kind is not None
        assert arc_sweep is not None
        assert apply_segment is not None
        assert snap_enabled is not None
        assert snap_tolerance is not None
        assert snap_enabled.isChecked()

        segment_kind.setCurrentIndex(segment_kind.findData("arc"))
        arc_sweep.setValue(120.0)
        apply_segment.click()
        _APP.processEvents()
        edited = window.project.items[0].vector_path
        assert edited is not None
        assert edited.resolved_segments()[0].kind == "arc"

        segment_kind.setCurrentIndex(segment_kind.findData("cubic"))
        apply_segment.click()
        _APP.processEvents()
        edited = window.project.items[0].vector_path
        assert edited is not None
        assert edited.resolved_segments()[0].kind == "cubic"

        snap_enabled.setChecked(False)
        snap_tolerance.setValue(2.5)
        assert not window._settings.value("vector/snap_enabled", True, type=bool)
        assert float(window._settings.value("vector/snap_tolerance_mm")) == 2.5
    finally:
        dialog = getattr(window, "_vector_node_dialog", None)
        if dialog is not None:
            dialog.close()
        window._settings.remove("vector/snap_enabled")
        window._settings.remove("vector/snap_tolerance_mm")
        window.close()



def test_direct_selection_split_updates_cam_sources_and_undo_restores_job():
    window = ProjectMainWindow()
    path = VectorPath(((0.0, 0.0), (10.0, 0.0), (20.0, 0.0)))
    item = ProjectItem(
        "Split me",
        kind="pen",
        mesh=path.mesh_asset(),
        vector_path=path,
    )
    cutter = Cutter("3 mm flat", ToolType.FLAT_END_MILL, 3.0)
    operation = CamOperation(
        operation="profile",
        cutter=cutter,
        source_item_ids=(item.item_id,),
    )
    try:
        window._set_project(
            Project(items=[item], cam_operations=[operation]),
            project_path=None,
            selected_row=1,
        )
        window._activate_direct_selection()
        dialog = window._vector_node_dialog
        table = window._vector_nodes_table
        split_button = dialog.findChild(QPushButton, "VectorSplitPath")
        assert split_button is not None

        table.setCurrentCell(1, 0)
        _APP.processEvents()
        assert split_button.isEnabled()
        split_button.click()
        _APP.processEvents()

        assert len(window.project.items) == 2
        first, second = window.project.items
        assert first.vector_path.points_xy == ((0.0, 0.0), (10.0, 0.0))
        assert second.vector_path.points_xy == ((10.0, 0.0), (20.0, 0.0))
        assert window.project.cam_operations[0].source_item_ids == (
            first.item_id,
            second.item_id,
        )
        assert window.project.cam_operations[0].needs_recalculation

        window._undo()
        assert len(window.project.items) == 1
        assert window.project.items[0].item_id == item.item_id
        assert window.project.cam_operations[0].source_item_ids == (item.item_id,)
    finally:
        dialog = getattr(window, "_vector_node_dialog", None)
        if dialog is not None:
            dialog.close()
        window.close()


def test_direct_selection_join_two_paths_retargets_cam_and_undo_restores_both():
    window = ProjectMainWindow()
    first_path = VectorPath(((0.0, 0.0), (10.0, 0.0)))
    second_path = VectorPath(((10.5, 0.0), (20.0, 0.0)))
    first = ProjectItem(
        "First",
        kind="pen",
        mesh=first_path.mesh_asset(),
        vector_path=first_path,
    )
    second = ProjectItem(
        "Second",
        kind="pen",
        mesh=second_path.mesh_asset(),
        vector_path=second_path,
    )
    cutter = Cutter("3 mm flat", ToolType.FLAT_END_MILL, 3.0)
    operation = CamOperation(
        operation="engrave",
        cutter=cutter,
        source_item_ids=(first.item_id, second.item_id),
    )
    try:
        window._set_project(
            Project(items=[first, second], cam_operations=[operation]),
            project_path=None,
            selected_row=1,
        )
        window._settings.setValue("vector/snap_tolerance_mm", 1.0)
        window._select_project_indices([0, 1], primary=0)
        window._activate_direct_selection()
        dialog = window._vector_node_dialog
        join_button = dialog.findChild(QPushButton, "VectorJoinPaths")
        assert join_button is not None
        assert join_button.isEnabled()

        join_button.click()
        _APP.processEvents()

        assert len(window.project.items) == 1
        joined_item = window.project.items[0]
        assert joined_item.item_id == first.item_id
        assert joined_item.vector_path is not None
        assert not joined_item.vector_path.closed
        assert joined_item.vector_path.points_xy == (
            (0.0, 0.0),
            (10.0, 0.0),
            (10.5, 0.0),
            (20.0, 0.0),
        )
        assert window.project.cam_operations[0].source_item_ids == (
            first.item_id,
        )
        assert window.project.cam_operations[0].needs_recalculation

        window._undo()
        assert [item.item_id for item in window.project.items] == [
            first.item_id,
            second.item_id,
        ]
        assert window.project.cam_operations[0].source_item_ids == (
            first.item_id,
            second.item_id,
        )
    finally:
        dialog = getattr(window, "_vector_node_dialog", None)
        if dialog is not None:
            dialog.close()
        window._settings.remove("vector/snap_tolerance_mm")
        window.close()


def test_native_bezier_handles_retain_selection_and_commit_undoable_curve():
    path = VectorPath(
        ((10, 10), (40, 10)),
        segments=(VectorSegment.cubic((17, 23), (33, 23)),),
    )
    item = ProjectItem("Curve", kind="pen", mesh=path.mesh_asset(), vector_path=path)
    window = MainWindow()
    try:
        window._set_project(Project(items=[item]), project_path=None, selected_row=1)
        window.viewport.set_node_edit_mode(True)
        native = window.viewport._renderer
        controls = native._editable_cubic_controls()
        assert len(controls) == 2
        assert [(segment, handle) for segment, handle, _, _ in controls] == [
            (0, 1), (0, 2),
        ]
        initial = segment_world_controls(item, 0)[0]
        window._control_drag_finished(0, 0, 1, initial[0] + 1.5, initial[1] + 2.0)
        assert item.vector_path.resolved_segments()[0].control1_xy != (17, 23)
        assert item.vector_path.resolved_segments()[0].control2_xy == (33, 23)
        moved = segment_world_controls(item, 0)[0]
        assert moved == pytest.approx((initial[0] + 1.5, initial[1] + 2.0))
    finally:
        window.close()


def test_bezier_handle_drag_uses_stock_grid_when_geometry_snapping_disabled():
    path = VectorPath(
        ((10, 10), (40, 10)),
        segments=(VectorSegment.cubic((17, 23), (33, 23)),),
    )
    item = ProjectItem("Curve", kind="pen", mesh=path.mesh_asset(), vector_path=path)
    window = MainWindow()
    keys = ("vector/snap_enabled", "vector/grid_snap_enabled",
            "vector/snap_tolerance_mm", "vector/grid_spacing_mm")
    original = {key: window._settings.value(key) for key in keys}
    try:
        window._set_project(Project(items=[item]), project_path=None, selected_row=1)
        window._settings.setValue("vector/snap_enabled", False)
        window._settings.setValue("vector/grid_snap_enabled", True)
        window._settings.setValue("vector/snap_tolerance_mm", 1.0)
        window._settings.setValue("vector/grid_spacing_mm", 5.0)
        window._control_drag_finished(0, 0, 1, 20.3, 24.7)
        world = segment_world_controls(item, 0)
        assert world is not None
        assert world[0] == pytest.approx((20.0, 25.0))
        assert item.vector_path.resolved_segments()[0].control2_xy == (33, 23)
    finally:
        for key, value in original.items():
            if value is None:
                window._settings.remove(key)
            else:
                window._settings.setValue(key, value)
        window.close()


def test_vector_angle_step_is_persisted_and_forwarded_to_native_viewport():
    path = VectorPath(
        ((10, 10), (40, 10)),
        segments=(VectorSegment.cubic((17, 23), (33, 23)),),
    )
    item = ProjectItem("Curve", kind="pen", mesh=path.mesh_asset(), vector_path=path)
    window = MainWindow()
    key = "vector/angle_step_degrees"
    original = window._settings.value(key)
    try:
        window._settings.setValue(key, 45.0)
        window._set_project(Project(items=[item]), project_path=None, selected_row=1)
        window._show_vector_node_inspector()
        dialog = window._vector_node_dialog
        assert dialog is not None
        step = dialog.findChild(QDoubleSpinBox, "VectorAngleStep")
        assert step is not None
        assert step.value() == pytest.approx(45.0)
        step.setValue(30.0)
        assert window.viewport._renderer._vector_angle_step_degrees == pytest.approx(30.0)
        assert float(window._settings.value(key)) == pytest.approx(30.0)
        dialog.close()
    finally:
        if original is None:
            window._settings.remove(key)
        else:
            window._settings.setValue(key, original)
        window.close()


def test_ctrl_cubic_handle_drag_previews_and_commits_neighbor_tangent():
    path = VectorPath(
        ((0, 0), (10, 0), (20, 5)),
        segments=(
            VectorSegment.line(),
            VectorSegment.cubic((13, 7), (18, 8)),
        ),
    )
    item = ProjectItem("Curve", kind="pen", mesh=path.mesh_asset(), vector_path=path)
    window = MainWindow()
    try:
        window._set_project(Project(items=[item]), project_path=None, selected_row=1)
        window.viewport.set_node_edit_mode(True)
        native = window.viewport._renderer
        native._control_drag_key = (1, 1)
        native._node_drag_item = 0
        origin = segment_world_point(item, 1, 0.0)
        target = np.array((origin[0] + 4, origin[1] + 6, 0.0))
        kind = native._constrain_cubic_drag(target, Qt.KeyboardModifier.ControlModifier)
        assert kind == "tangent"
        assert target[1] == pytest.approx(origin[1])
        assert native._control_angle_constrained
        assert native._control_constraint_kind == "tangent"
        window._control_drag_finished(0, 1, 1, target[0], target[1], kind)
        world = segment_world_controls(item, 1)
        assert world is not None
        assert world[0] == pytest.approx(target[:2])
        assert item.vector_path.resolved_segments()[1].control2_xy == (18, 8)
        updated_origin = segment_world_point(item, 1, 0.0)
        normal = np.array((updated_origin[0] + 4, updated_origin[1] + 6, 0.0))
        kind = native._constrain_cubic_drag(
            normal,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        assert kind == "perpendicular"
        assert native._control_constraint_kind == "perpendicular"
        assert normal[0] == pytest.approx(updated_origin[0])
    finally:
        window.close()


def test_direct_selection_endpoint_trim_updates_retained_curve_and_ui():
    path = VectorPath(
        ((0, 0), (20, 0)),
        segments=(VectorSegment.cubic((4, 7), (16, 7)),),
    )
    item = ProjectItem("Curve", kind="pen", mesh=path.mesh_asset(), vector_path=path)
    window = MainWindow()
    try:
        window._set_project(Project(items=[item]), project_path=None, selected_row=1)
        window._show_vector_node_inspector()
        dialog = window._vector_node_dialog
        assert dialog is not None
        trim = dialog.findChild(QPushButton, "VectorTrimEndpoint")
        fraction = dialog.findChild(QDoubleSpinBox, "VectorEndpointTrimPercent")
        assert trim is not None and fraction is not None
        table = dialog.findChild(QTableWidget, "EditableVectorNodeTable")
        assert table is not None
        table.setCurrentCell(0, 0)
        fraction.setValue(30.0)
        assert trim.isEnabled()
        opposite_before = tuple(node_world_points(item)[-1, :2])
        trim.click()
        assert item.vector_path.points_xy[0] != (0, 0)
        assert item.vector_path.resolved_segments()[0].kind == "cubic"
        assert tuple(node_world_points(item)[-1, :2]) == pytest.approx(opposite_before)
        assert not item.vector_path.closed
    finally:
        window.close()


def test_direct_selection_line_extension_preserves_opposite_world_endpoint():
    path = VectorPath(((0, 0), (20, 0)), segments=(VectorSegment.line(),))
    item = ProjectItem("Line", kind="pen", mesh=path.mesh_asset(), vector_path=path)
    window = MainWindow()
    try:
        window._set_project(Project(items=[item]), project_path=None, selected_row=1)
        window._show_vector_node_inspector()
        dialog = window._vector_node_dialog
        assert dialog is not None
        extend = dialog.findChild(QPushButton, "VectorExtendEndpoint")
        amount = dialog.findChild(QDoubleSpinBox, "VectorEndpointExtendDistance")
        table = dialog.findChild(QTableWidget, "EditableVectorNodeTable")
        assert extend is not None and amount is not None and table is not None
        table.setCurrentCell(0, 0)
        opposite_before = tuple(node_world_points(item)[-1, :2])
        amount.setValue(6.0)
        assert extend.isEnabled()
        extend.click()
        assert item.vector_path.points_xy[0] == pytest.approx((-6.0, 0.0))
        assert tuple(node_world_points(item)[-1, :2]) == pytest.approx(opposite_before)
    finally:
        window.close()


def test_direct_selection_fit_to_second_selected_line_preserves_world_anchor():
    source_path = VectorPath(((0, 0), (10, 0)))
    target_path = VectorPath(((5, -4), (5, 4)))
    source = ProjectItem(
        "Source", kind="pen", mesh=source_path.mesh_asset(), vector_path=source_path,
    )
    reference = ProjectItem(
        "Reference", kind="pen", mesh=target_path.mesh_asset(),
        vector_path=target_path,
    )
    window = MainWindow()
    try:
        window._set_project(
            Project(items=[source, reference]), project_path=None, selected_row=1,
        )
        window._selected_design_indices = lambda: [0, 1]
        window.viewport._renderer.selected_item_index = 0
        window._show_vector_node_inspector()
        dialog = window._vector_node_dialog
        assert dialog is not None
        table = dialog.findChild(QTableWidget, "EditableVectorNodeTable")
        button = dialog.findChild(QPushButton, "VectorFitIntersection")
        mode = dialog.findChild(QComboBox, "VectorFitMode")
        assert table is not None and button is not None and mode is not None
        table.setCurrentCell(0, 0)
        assert button.isEnabled()
        before = tuple(node_world_points(source)[-1, :2])
        button.click()
        assert source.vector_path.points_xy[0] == pytest.approx((5, 0))
        assert tuple(node_world_points(source)[-1, :2]) == pytest.approx(before)
        assert reference.vector_path == target_path
    finally:
        window.close()
