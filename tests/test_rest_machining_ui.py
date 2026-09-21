"""Workshop UI blocks pretend rest passes and preserves preceding cutter stages."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.core.transform import Transform3D
from carvefoundry.ui.project_window import MainWindow

_APP = QApplication.instance() or QApplication([])


def _window():
    window = MainWindow()
    item = ProjectItem(
        "Relief", kind="rectangle", mesh=rectangle_mesh(12, 12, 2),
        transform=Transform3D(translation_mm=(15, 15, -1)),
    )
    window._set_project(
        Project(
            name="Workshop Rest", stock=Stock(30, 30, 8),
            items=[item],
        ),
        project_path=None,
        selected_row=1,
    )
    return window


def _prior(item):
    return Toolpath(
        "3D Rough", "3d_rough_raster",
        Cutter("6 mm flat", ToolType.FLAT_END_MILL, 6),
        3.0,
        [
            ToolpathMove(14, 15, 3, MoveKind.RAPID),
            ToolpathMove(14, 15, -0.5, MoveKind.PLUNGE, 150),
            ToolpathMove(16, 15, -0.5, MoveKind.CUT, 500),
            ToolpathMove(16, 15, 3, MoveKind.RAPID),
        ],
        source_item_name=item.name,
        source_item_id=item.item_id,
    )


def test_rest_dialog_blocks_missing_previous_stages_and_exposes_real_parameters():
    window = _window()
    try:
        window._select_cam_operation("rest")
        dialog = window._build_toolpath_generation_dialog()
        fields = dialog.generation_fields
        assert fields["operation"].currentData() == "rest"
        assert fields["rest_allowance"].value() == pytest.approx(0.15)
        assert fields["rest_resolution"].value() == pytest.approx(0.75)
        assert fields["rest_allowance"].isVisibleTo(dialog)
        assert not fields["generate"].isEnabled()
        assert not fields["append_job"].isEnabled()
        dialog.close()
    finally:
        window.close()


def test_rest_dialog_forces_append_and_warns_after_part_cutout():
    window = _window()
    try:
        item = window.project.items[0]
        window.project.toolpaths = [_prior(item)]
        window._select_cam_operation("rest")
        dialog = window._build_toolpath_generation_dialog()
        fields = dialog.generation_fields
        assert fields["append_job"].isChecked()
        assert not fields["append_job"].isEnabled()
        assert fields["generate"].isEnabled()
        assert "preceding" in fields["readiness"].text().lower()
        dialog.close()

        window.project.toolpaths.append(
            _prior(item)
        )
        window.project.toolpaths[-1].name = "Full Depth Cutout"
        blocked = window._build_toolpath_generation_dialog()
        assert not blocked.generation_fields["generate"].isEnabled()
        blocked.close()
    finally:
        window.close()


def test_workshop_guide_has_real_rest_launcher_that_checks_prior_stages():
    window = _window()
    try:
        window._show_guided_workflow()
        labels = {
            button.text() for button in window._guided_workflow_extras
        }
        assert len(labels) == 8
        assert {
            "Rest Cleanup", "Check Carve Quality", "Job Setup Sheet",
            "Carving Notes",
        } <= labels
        rest_button = next(
            button for button in window._guided_workflow_extras
            if button.text() == "Rest Cleanup"
        )
        assert not rest_button.isEnabled()
        window.project.toolpaths.append(_prior(window.project.items[0]))
        window._refresh_guided_workflow()
        assert rest_button.isEnabled()
        # Action selects existing CAM Rest operation rather than a placeholder.
        window._select_cam_operation("finish")
        assert callable(window._start_guided_rest_cleanup)
        window._guided_workflow_dialog.close()
    finally:
        window.close()


def test_next_cutter_and_cam_choices_never_delete_previously_planned_job():
    window = _window()
    try:
        first = _prior(window.project.items[0])
        window.project.toolpaths = [first]
        window._select_cam_operation("rough")
        assert window.project.toolpaths == [first]
        window._select_cam_operation("rest")
        assert window.project.toolpaths == [first]
        window._set_cam_detail(90)
        assert window.project.toolpaths == [first]
        window._set_cam_design_option("direction", "Raster Y")
        assert window.project.toolpaths == [first]
        window._toggle_tabs_operation()
        assert window.project.toolpaths == [first]
        if window.tool_combo.count() > 1:
            window.tool_combo.setCurrentIndex(
                (window.tool_combo.currentIndex() + 1)
                % window.tool_combo.count()
            )
            assert window.project.toolpaths == [first]
            assert window.project.toolpaths[0].cutter == first.cutter
        rest = window._build_toolpath_generation_dialog()
        assert rest.generation_fields["operation"].currentData() == "rest"
        assert rest.generation_fields["append_job"].isChecked()
        assert rest.generation_fields["generate"].isEnabled()
        rest.close()
    finally:
        window.close()
