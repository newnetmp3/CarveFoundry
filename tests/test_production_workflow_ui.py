"""UI wiring and real asynchronous two-sided/CAM job operation tests."""
from __future__ import annotations

from time import monotonic, sleep

from PySide6.QtWidgets import QApplication

from carvefoundry.cam.operation import CamOperation
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.core.transform import Transform3D
from carvefoundry.ui.project_window import MainWindow

_APP = QApplication.instance() or QApplication([])


def _finish(window, timeout: float = 40.0) -> None:
    deadline = monotonic() + timeout
    while window._background_job is not None and monotonic() < deadline:
        _APP.processEvents()
        sleep(0.01)
    _APP.processEvents()
    assert window._background_job is None, "Background task did not finish"


def _models():
    return [
        ProjectItem(
            "front",
            kind="rectangle",
            mesh=rectangle_mesh(10, 10, 2),
            transform=Transform3D(translation_mm=(20, 20, 0)),
        ),
        ProjectItem(
            "back",
            kind="rectangle",
            mesh=rectangle_mesh(10, 10, 2),
            transform=Transform3D(translation_mm=(45, 20, 0)),
        ),
    ]


def _path(name, operation, tool):
    return Toolpath(
        name=name, operation=operation, cutter=tool,
        source_item_id="model", source_item_name="Model",
        safe_z_mm=5.0,
        moves=[
            ToolpathMove(5, 5, 5, MoveKind.RAPID),
            ToolpathMove(5, 5, -1, MoveKind.PLUNGE, 120),
            ToolpathMove(10, 5, -1, MoveKind.CUT, 500),
        ],
    )


def test_two_sided_setup_is_a_real_menu_command_and_background_export(tmp_path):
    window = MainWindow()
    try:
        assert window._ui_actions["two_sided"].text() == "Double-Sided Stock Setup…"
        project_menu = window.main_menu_bar.actions()[1].menu()
        assert window._ui_actions["two_sided"] in project_menu.actions()
        items = _models()
        window._set_project(
            Project(name="Two Faces", stock=Stock(100, 100, 19.4), items=items),
            project_path=None,
        )
        target = tmp_path / "two_sided"
        assert window._run_two_sided_setup(
            back_item_ids=frozenset({items[1].item_id}),
            axis="x",
            destination=target,
        )
        _finish(window)
        assert (target / "front.cf3d").is_file()
        assert (target / "back.cf3d").is_file()
        assert (target / "SETUP_INSTRUCTIONS.txt").is_file()
        assert len(window.project.items) == 2
        assert not window._background_job
    finally:
        window.close()


def test_job_planner_entry_opens_persistent_machining_operations_panel():
    window = MainWindow()
    flat = Cutter("Flat", ToolType.FLAT_END_MILL, 6)
    model = _models()[0]
    operation = CamOperation(
        operation="rough",
        cutter=flat,
        source_item_ids=(model.item_id,),
        parameters={"feed_mm_min": 1000.0},
    )
    rough = _path("Rough", "rough", flat)
    rough.source_item_id = model.item_id
    rough.source_item_name = model.name
    rough.cam_operation_id = operation.operation_id
    try:
        window._set_project(
            Project(
                items=[model],
                toolpaths=[rough],
                cam_operations=[operation],
            ),
            project_path=None,
        )
        assert window._ui_actions["job_planner"].text() == "Machining Operations"
        window._show_job_planner()
        assert window.machining_operations_panel is not None
        assert window.machining_operations_list.count() == 1
        assert "Rough" in window.machining_operations_list.item(0).text()

        dialog = window._build_toolpath_generation_dialog()
        try:
            assert dialog.generation_fields["append_job"].isEnabled()
        finally:
            dialog.close()
    finally:
        window.close()


def test_batch_grid_ui_commits_all_copies_and_undo_restores_templates():
    window = MainWindow()
    try:
        items = _models()
        window._set_project(
            Project(name="Batch", stock=Stock(100, 100, 19.4), items=items),
            project_path=None,
        )
        window._select_project_indices([0, 1])
        assert window._ui_actions["batch_layout"].text() == "Batch Production Grid…"
        assert window._run_batch_layout(
            copies=4, columns=2, gap_mm=5, margin_mm=8
        )
        _finish(window)
        assert len(window.project.items) == 10
        assert not window.project.items[0].visible
        assert not window.project.items[1].visible
        assert all(item.visible for item in window.project.items[2:])
        assert len({item.item_id for item in window.project.items}) == 10
        window._undo()
        assert len(window.project.items) == 2
        assert all(item.visible for item in window.project.items)
    finally:
        window.close()
