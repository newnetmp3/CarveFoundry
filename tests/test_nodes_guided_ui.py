"""Real Direct Selection and the workshop's live guided production checklist."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.core.vector_path import node_world_points
from carvefoundry.ui.project_window import MainWindow

_APP = QApplication.instance() or QApplication([])


def _window():
    window = MainWindow()
    window._set_project(
        Project(
            name="Nodes and workflow",
            stock=Stock(100, 80, 19.4),
        ),
        project_path=None,
    )
    return window


def test_pen_direct_selection_rebuilds_geometry_undoes_and_refreshes_ui(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("CARVEFOUNDRY_RECOVERY_DIR", str(tmp_path / "recover"))
    window = _window()
    try:
        window._freehand_pen_drawn([(10, 10), (15, 15), (20, 10)])
        assert len(window.project.items) == 1
        item = window.project.items[0]
        assert item.vector_path is not None
        assert item.vector_path.points_xy == (
            (10, 10), (15, 15), (20, 10),
        )
        window._select_project_indices([0])
        window._activate_direct_selection()
        assert window._ui_actions["direct_select"].isChecked()
        assert window.viewport._renderer._node_edit_mode
        assert window._vector_nodes_table.rowCount() == 3

        first_bounds = item.transformed_bounds_mm().copy()
        p = node_world_points(item)[1]
        window._node_drag_finished(0, 1, float(p[0] + 5), float(p[1] + 5))
        edited = window.project.items[0]
        assert edited.vector_path != item.vector_path or (
            edited.vector_path.points_xy[1] != (15, 15)
        )
        assert node_world_points(edited)[1][:2] == pytest.approx(
            (p[0] + 5, p[1] + 5), abs=1e-6,
        )
        assert edited.transformed_bounds_mm()[1, 1] > first_bounds[1, 1]
        window._undo()
        assert window.project.items[0].vector_path.points_xy[1] == (15, 15)
        window._redo()
        assert window.project.items[0].vector_path.points_xy[1] != (15, 15)
        window._set_direct_selection(False)
        assert not window.viewport._renderer._node_edit_mode
    finally:
        window.close()


def test_new_line_has_two_editable_endpoints_with_exact_world_positions():
    window = _window()
    try:
        window._shape_drawn("line", 10.0, 15.0, 30.0, 15.0)
        line = window.project.items[-1]
        assert line.kind == "line"
        assert line.vector_path is not None
        assert len(line.vector_path.points_xy) == 2
        assert node_world_points(line)[:, :2] == pytest.approx(
            [[10, 15], [30, 15]]
        )
    finally:
        window.close()


def test_vector_change_clears_obsolete_toolpaths_and_undo_restores_them():
    window = _window()
    try:
        window._freehand_pen_drawn([(10, 10), (15, 15), (20, 10)])
        cutter = Cutter("flat", ToolType.FLAT_END_MILL, 3)
        path = Toolpath(
            "Engrave", "engrave", cutter, 5,
            [
                ToolpathMove(10, 10, 5, MoveKind.RAPID),
                ToolpathMove(15, 15, -1, MoveKind.CUT, 500),
            ],
        )
        window.project.toolpaths = [path]
        window._select_project_indices([0])
        p = node_world_points(window.project.items[0])[1]
        window._node_drag_finished(0, 1, float(p[0] + 2), float(p[1]))
        assert window.project.toolpaths == []
        window._undo()
        assert window.project.toolpaths == [path]
    finally:
        window.close()


def test_guided_workflow_buttons_are_real_and_reflect_live_project_state():
    window = _window()
    try:
        assert window._ui_actions["guided_workflow"].text() == (
            "Guided CNC Workflow…"
        )
        assert window._ui_actions["direct_select"].text() == (
            "Direct Selection — Pen Nodes"
        )
        assert "direct_select" in window.tool_rail.buttons
        steps = window._guided_stage_status()
        assert len(steps) == 8
        assert steps[0][2]
        assert not steps[2][2]  # no recorded fixture yet
        assert not steps[4][2]  # no calculated toolpath
        assert not steps[7][3]  # can't export without preflight
        window._show_guided_workflow()
        assert window._guided_workflow_dialog is not None
        assert len(window._guided_workflow_rows) == 8
        window.project.items.append(ProjectItem(
            "Model", kind="rectangle", mesh=rectangle_mesh(10, 10, 2),
        ))
        cutter = Cutter("flat", ToolType.FLAT_END_MILL, 3)
        path = Toolpath(
            "Finish", "finish", cutter, 5,
            [
                ToolpathMove(10, 10, 5, MoveKind.RAPID),
                ToolpathMove(10, 10, -1, MoveKind.CUT, 500),
            ],
        )
        window.project.toolpaths.append(path)
        assert window._guided_stage_status()[4][2]
        assert not window._guided_stage_status()[7][3]
        window._guided_preflight_pass = window._guided_job_fingerprint()
        assert window._guided_stage_status()[6][2]
        assert window._guided_stage_status()[7][3]
        window.project.stock.width_mm += 1
        assert not window._guided_stage_status()[6][2]
        assert not window._guided_stage_status()[7][3]
        window._guided_workflow_dialog.close()
    finally:
        window.close()
