"""End-to-end vector menu/rail -> worker -> project/undo/CF3D behavior."""
from __future__ import annotations

import os
from pathlib import Path
from time import monotonic, sleep

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")

import pytest
from PySide6.QtWidgets import QApplication

from carvefoundry.cam.vector_ops import projected_regions
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.project_file import load_project, save_project
from carvefoundry.core.transform import Transform3D
from carvefoundry.ui.project_window import MainWindow

_APP = QApplication.instance() or QApplication([])


def _pump_job(window: MainWindow, seconds: float = 30.0) -> None:
    deadline = monotonic() + seconds
    while window._background_job is not None and monotonic() < deadline:
        _APP.processEvents()
        sleep(0.01)
    _APP.processEvents()
    assert window._background_job is None, "Planar calculation failed to finish"


def _shape(name: str, x: float) -> ProjectItem:
    return ProjectItem(
        name=name,
        kind="rectangle",
        mesh=rectangle_mesh(10, 10, 1.0),
        transform=Transform3D(translation_mm=(x, 20.0, 0.0)),
    )


def test_vector_commands_are_only_enabled_for_valid_selection() -> None:
    window = MainWindow()
    try:
        window._set_project(
            Project(items=[_shape("A", 10), _shape("B", 15)]),
            project_path=None,
        )
        flyout_labels = [action.text() for action in
                         window.tool_rail.buttons["vector"].menu().actions()]
        assert "Union Silhouettes" in flyout_labels
        assert "Offset Silhouette…" in flyout_labels

        window._select_project_indices([0])
        assert window._ui_actions["vector_offset"].isEnabled()
        assert not window._ui_actions["vector_union"].isEnabled()
        window._select_project_indices([0, 1])
        assert window._ui_actions["vector_union"].isEnabled()
        assert window._ui_actions["vector_subtract"].isEnabled()
        assert window._ui_actions["vector_intersect"].isEnabled()
        assert not window._ui_actions["vector_offset"].isEnabled()
    finally:
        window.close()


def test_union_via_worker_is_undoable_persisted_and_hides_inputs(tmp_path: Path) -> None:
    window = MainWindow()
    try:
        window._set_project(
            Project(items=[_shape("A", 10), _shape("B", 15)]),
            project_path=None,
        )
        window._select_project_indices([0, 1])
        assert window._run_planar_operation("union", depth_mm=2.0)
        assert window._background_job is not None
        _pump_job(window)

        assert len(window.project.items) == 3
        a, b, result = window.project.items
        assert not a.visible and not b.visible
        assert result.visible and result.kind == "boolean"
        assert result.transform == Transform3D()
        assert result.mesh.mesh.is_watertight
        assert projected_regions(result.mesh.mesh).area == pytest.approx(150)
        assert result.mesh.bounds[1][2] == pytest.approx(0)
        assert result.mesh.bounds[0][2] == pytest.approx(-2)
        assert window._selected_design_indices() == [2]
        assert window._undo_stack[-1].label == "vector union"
        assert window.project.toolpaths == []

        saved = save_project(window.project, tmp_path / "boolean.cf3d")
        loaded = load_project(saved)
        assert [x.visible for x in loaded.items] == [False, False, True]
        assert loaded.items[-1].kind == "boolean"
        assert projected_regions(loaded.items[-1].mesh.mesh).area == pytest.approx(150)

        window._undo()
        assert len(window.project.items) == 2
        assert all(x.visible for x in window.project.items)
        window._redo()
        assert len(window.project.items) == 3
        assert [x.visible for x in window.project.items] == [False, False, True]

        # The composite replaces its hidden inputs for actual CNC generation,
        # not just for drawing or the Layers panel.
        window._select_cam_operation("profile")
        assert window._calculate_toolpath_now()
        _pump_job(window)
        assert {path.source_item_name for path in window.project.toolpaths} == {
            window.project.items[-1].name
        }
    finally:
        if window._background_job is not None:
            _pump_job(window)
        window.close()


def test_failed_intersection_does_not_change_project_or_history() -> None:
    window = MainWindow()
    try:
        window._set_project(
            Project(items=[_shape("A", 10), _shape("B", 80)]),
            project_path=None,
        )
        window._select_project_indices([0, 1])
        before_undo = len(window._undo_stack)
        assert window._run_planar_operation("intersect", depth_mm=1.0)
        _pump_job(window)
        assert len(window.project.items) == 2
        assert all(item.visible for item in window.project.items)
        assert len(window._undo_stack) == before_undo
    finally:
        if window._background_job is not None:
            _pump_job(window)
        window.close()


def test_offset_creates_stock_top_result_and_supports_undo() -> None:
    window = MainWindow()
    try:
        window._set_project(Project(items=[_shape("A", 10)]), project_path=None)
        window._select_project_indices([0])
        assert window._run_planar_operation(
            "offset", depth_mm=1.0, offset_mm=-2.0,
        )
        _pump_job(window)
        assert len(window.project.items) == 2
        assert window.project.items[0].visible is False
        assert window.project.items[1].kind == "offset"
        assert projected_regions(
            window.project.items[1].mesh.mesh
        ).area == pytest.approx(36)
        window._undo()
        assert len(window.project.items) == 1
        assert window.project.items[0].visible
    finally:
        if window._background_job is not None:
            _pump_job(window)
        window.close()
