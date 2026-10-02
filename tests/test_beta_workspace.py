"""Beta2 surfaces drive the shared project, CAM state and guarded commands."""
from time import monotonic, sleep

import numpy as np
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from carvefoundry.cam.stock_simulation import RemovalStage, StockRemovalResult
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.ui import main_window
from carvefoundry.ui.workspace_palette import PaletteCommand, WorkspaceCommandPalette

_APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "beta.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(main_window, "QSettings", lambda: settings)
    instance = main_window.MainWindow()
    yield instance
    instance.close()


def paths():
    cutter = Cutter("Flat 3 mm", ToolType.FLAT_END_MILL, 3)
    return [Toolpath(
        name, operation, cutter, 5,
        [ToolpathMove(10, 10, 5, MoveKind.RAPID),
         ToolpathMove(10, 10, -1, MoveKind.CUT, 500)],
        source_item_id="part", source_item_name="Part",
    ) for name, operation in (("Rough", "rough"), ("Finish", "finish"))]


def test_workspace_preserves_project_selection_and_restores_preferences(window):
    project = window.project
    window.workspace_mode.setCurrentText("Machine")
    assert not window.machining_dock.isHidden()
    assert window.properties_panel.isHidden()
    assert window.project is project
    window.experience_mode.setCurrentText("Advanced")
    assert not window.machining_edit_bar.isHidden()
    assert not window._settings.value("cam/simple_mode", type=bool)
    second = main_window.MainWindow()
    try:
        assert second.workspace_mode.currentText() == "Machine"
        assert second.experience_mode.currentText() == "Advanced"
        second._focus_stock_section()
        assert second.workspace_mode.currentText() == "Design"
        assert not second.properties_panel.isHidden()
    finally:
        second.close()


def test_cam_mode_and_machine_append_default_share_real_form(window):
    window.project.toolpaths = paths()
    window.workspace_mode.setCurrentText("Machine")
    window.experience_mode.setCurrentText("Advanced")
    dialog = window._build_toolpath_generation_dialog()
    assert dialog.generation_fields["mode"].currentText() == "Advanced"
    assert dialog.generation_fields["append_job"].isChecked()
    dialog.close()
    window.experience_mode.setCurrentText("Beginner")
    dialog = window._build_toolpath_generation_dialog()
    assert dialog.generation_fields["mode"].currentText() == "Simple"
    assert window.machining_edit_bar.isHidden()
    dialog.close()


def test_preflight_export_is_invalidated_and_rechecked_at_click(window):
    window.project.toolpaths = paths()
    window._refresh_machining_panel()
    assert window.machining_operations.count() == 2
    assert not window.machining_steps[7].isEnabled()
    window._guided_preflight_pass = window._guided_job_fingerprint()
    window._refresh_machining_panel()
    assert window.machining_steps[7].isEnabled()
    called = []
    window.project.stock.thickness_mm += 1
    window._run_machining_step(7, lambda: called.append(True))
    assert not called
    assert not window.machining_steps[7].isEnabled()
    window._invalidate_toolpaths("Geometry")
    assert window.machining_operations.count() == 0
    assert "Recalculate" in window.machining_status.text()


def test_panel_reorder_rejects_invalid_order_and_remove_updates_project(window, monkeypatch):
    window.project.toolpaths = paths()
    window._refresh_machining_panel()
    window.machining_operations.setCurrentRow(1)
    warnings = []
    monkeypatch.setattr(
        "carvefoundry.ui.beta_workspace.QMessageBox.warning",
        lambda *args: warnings.append(args[-1]),
    )
    window._edit_machining_operation(-1)
    assert warnings and "roughing must precede" in warnings[0]
    assert window.project.toolpaths[0].name == "Rough"
    window._edit_machining_operation(0)
    deadline = monotonic() + 10
    while window._background_job is not None and monotonic() < deadline:
        _APP.processEvents()
        sleep(0.01)
    assert window._background_job is None
    assert [path.name for path in window.project.toolpaths] == ["Rough"]
    assert window.machining_operations.count() == 1


def test_busy_panel_cannot_invoke_commands(window):
    window.project.toolpaths = paths()
    window._background_job = object()
    try:
        called = []
        window._run_machining_step(4, lambda: called.append(True))
        assert not called
        assert all(not button.isEnabled() for button in window.machining_steps)
    finally:
        window._background_job = None


def test_tabbed_machine_workspace_shares_the_real_cam_form(window):
    window.workspace_mode.setCurrentText("Machine")
    assert [window.machining_tabs.tabText(i) for i in range(4)] == [
        "1 · Setup", "2 · Operations", "3 · Review", "4 · Export",
    ]
    assert window.machining_dock.features() & (
        window.machining_dock.DockWidgetFeature.DockWidgetMovable
    )
    window._open_inline_cam_form()
    form = window._machining_embedded_dialog
    assert form is not None
    assert window.machining_tabs.currentIndex() == 1
    assert not form.isWindow()
    assert not form.isModal()
    assert "generate" in form.generation_fields
    assert form.generation_fields["mode"].currentText() == "Simple"

    window.experience_mode.setCurrentText("Advanced")
    assert form.generation_fields["mode"].currentText() == "Advanced"
    assert not window.machining_edit_bar.isHidden()
    form.close()


def test_docked_cam_form_rejects_design_changes_before_submission(window):
    window.workspace_mode.setCurrentText("Machine")
    window._open_inline_cam_form()
    form = window._machining_embedded_dialog
    initial_context = window._machining_form_snapshot
    assert initial_context == window._cam_form_context_key()
    window.project.stock.thickness_mm += 2
    assert initial_context != window._cam_form_context_key()
    window._refresh_machining_panel()
    assert not form.generation_fields["generate"].isEnabled()
    assert "out of date" in window.machining_status.text().lower()
    window._open_inline_cam_form()
    assert window._machining_form_snapshot == window._cam_form_context_key()
    assert window._machining_embedded_dialog is not form


def test_preflight_report_is_inline_and_stales_on_setup_changes(window):
    window.workspace_mode.setCurrentText("Machine")
    window.project.toolpaths = paths()
    window._guided_preflight_pass = window._guided_job_fingerprint()
    should_suppress_popup = window._handle_beta_preflight_result({
        "safe_to_export": True, "report": "Decoded NC preflight report\\nNO BLOCKING ISSUES",
    })
    assert should_suppress_popup
    assert window.machining_tabs.currentIndex() == 2
    assert "Decoded NC preflight" in window.machining_preflight_report.toPlainText()
    assert "PASS" in window.machining_preflight_state.text()
    window.project.fixtures.append(
        Fixture(
            "Fence", -20, 0, -1, 50, 4, 2,
        )
    )
    window._refresh_machining_panel()
    assert "NOT CLEARED" in window.machining_preflight_state.text()
    assert not window.machining_steps[7].isEnabled()


def test_operation_picker_opens_specialized_advanced_cam_inline(window):
    window.workspace_mode.setCurrentText("Machine")
    assert window.experience_mode.currentText() == "Beginner"
    picker = window.machining_operation_picker
    row = picker.findData("rest")
    assert row >= 0
    window._select_machine_operation(row)
    assert window._active_cam_operation == "rest"
    assert window.experience_mode.currentText() == "Advanced"
    form = window._machining_embedded_dialog
    assert form is not None
    assert form.generation_fields["operation"].currentData() == "rest"
    assert form.generation_fields["mode"].currentText() == "Advanced"
    assert picker.currentData() == "rest"


def test_embedded_cam_experience_stays_in_sync_and_outside_changes_stale(window):
    window.workspace_mode.setCurrentText("Machine")
    window._open_inline_cam_form()
    form = window._machining_embedded_dialog
    form.generation_fields["mode"].setCurrentText("Advanced")
    assert window.experience_mode.currentText() == "Advanced"
    window.experience_mode.setCurrentText("Beginner")
    assert form.generation_fields["mode"].currentText() == "Simple"

    window._select_cam_operation("pocket")
    assert window._machining_form_snapshot != window._cam_form_context_key()
    window._refresh_machining_panel()
    assert not form.generation_fields["generate"].isEnabled()


def test_review_path_overlays_and_per_cutter_summary(window):
    window.workspace_mode.setCurrentText("Machine")
    window.project.toolpaths = paths()
    window._refresh_machining_panel()
    assert "2 operations" in window.machining_job_summary.text()
    assert "1 cutter stage" in window.machining_job_summary.text()
    before = window.viewport.toolpaths_visible
    window.machining_paths_toggle.click()
    assert window.viewport.toolpaths_visible != before
    assert window.machining_paths_toggle.isChecked() == window.viewport.toolpaths_visible
    window.machining_rapids_toggle.click()
    assert window.machining_rapids_toggle.isChecked() == window.viewport.rapids_visible


def test_stock_simulation_runs_original_background_path_without_modal(window, monkeypatch):
    window.workspace_mode.setCurrentText("Machine")
    window.project.toolpaths = paths()
    window._refresh_machining_panel()
    requested = []
    monkeypatch.setattr(
        window, "_run_stock_removal",
        lambda **kw: requested.append(kw) or True,
    )
    window._simulate_stock_in_workspace()
    assert requested == [{"spacing_mm": 0.75, "posted_nc": True}]
    assert window.machining_tabs.currentIndex() == 2
    assert "background" in window.machining_stock_summary.text()
    window.experience_mode.setCurrentText("Advanced")
    window.machining_verify_posted_nc.setChecked(False)
    window.machining_sample_spacing.setValue(1.5)
    window._simulate_stock_in_workspace()
    assert requested[-1] == {"spacing_mm": 1.5, "posted_nc": False}


def test_simulation_result_is_embedded_not_reused_after_stock_change(window):
    window.workspace_mode.setCurrentText("Machine")
    window.project.toolpaths = paths()
    zeros = np.zeros((3, 3), dtype=np.float32)
    result = StockRemovalResult(
        x_mm=np.array([0, 1, 2], dtype=float),
        y_mm=np.array([0, 1, 2], dtype=float),
        remaining_z_mm=zeros,
        target_z_mm=None,
        removed_volume_mm3=20.0,
        cut_sample_count=3,
        grid_spacing_mm=1.0,
        stages=(RemovalStage("Rough", "Flat 3 mm", 20.0, 3),),
    )
    window._show_stock_removal_result(result, posted_nc=True)
    assert window._beta_stock_result is result
    assert "Verified posted NC" in window.machining_stock_summary.text()
    assert window.machining_stock_image.pixmap() is not None
    assert window.machining_stock_details.isEnabled()
    assert getattr(window, "_stock_removal_dialog", None) is None
    window.project.stock.thickness_mm += 1
    window._refresh_machining_panel()
    assert window._beta_stock_result is None
    assert not window.machining_stock_details.isEnabled()
    assert "out of date" in window.machining_stock_image.text()


def test_machine_beginner_always_uses_verified_nc_simulation(window):
    window.workspace_mode.setCurrentText("Machine")
    window.experience_mode.setCurrentText("Advanced")
    window.machining_verify_posted_nc.setChecked(False)
    window.experience_mode.setCurrentText("Beginner")
    assert window.machining_verify_posted_nc.isChecked()
    assert window.machining_verify_posted_nc.isHidden()


def test_quick_command_palette_search_and_guarded_execution():
    called = []
    dialog = WorkspaceCommandPalette([
        PaletteCommand("Edit stock", lambda: called.append("stock")),
        PaletteCommand(
            "Export NC", lambda: called.append("unsafe"), enabled=False,
            keywords="machine",
        ),
        PaletteCommand("Open toolpaths", lambda: called.append("paths")),
    ])
    dialog.search.setText("export")
    assert dialog.results.count() == 1
    assert not dialog.results.item(0).isSelected()
    dialog.run_selected()
    _APP.processEvents()
    assert called == []

    dialog.search.setText("stock")
    assert dialog.results.count() == 1
    dialog.run_selected()
    _APP.processEvents()
    assert called == ["stock"]
    dialog.close()


def test_quick_commands_and_restore_closed_machine_dock(window):
    assert window._beta_command_shortcut.key().toString() == "Ctrl+K"
    window.workspace_mode.setCurrentText("Machine")
    window.machining_dock.hide()
    assert window.machining_dock.isHidden()
    window._restore_beta_panels()
    assert not window.machining_dock.isHidden()
    window._show_command_palette()
    popup = window._beta_palette
    assert popup is not None
    popup.search.setText("Switch to Design")
    assert popup.results.count() >= 1
    popup.run_selected()
    _APP.processEvents()
    assert window.workspace_mode.currentText() == "Design"


def test_beginner_reviews_job_order_inline_with_advanced_fallback(window):
    window.workspace_mode.setCurrentText("Machine")
    window.project.toolpaths = paths()
    window._refresh_machining_panel()
    window.machining_tabs.setCurrentIndex(0)
    assert window.machining_advanced_planner.isHidden()
    window.machining_steps[5].click()
    assert window.machining_tabs.currentIndex() == 1
    assert window.machining_operations.count() == 2
    window.experience_mode.setCurrentText("Advanced")
    assert not window.machining_advanced_planner.isHidden()
    assert window.machining_advanced_planner.isEnabled()
