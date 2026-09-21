"""Architecture regressions for UI controller boundaries."""
from __future__ import annotations

from carvefoundry.ui.import_controller import ImportControllerMixin
from carvefoundry.ui.main_window import MainWindow
from carvefoundry.ui.project_inspector_controller import ProjectInspectorControllerMixin
from carvefoundry.ui.selection_transform_controller import SelectionTransformControllerMixin
from carvefoundry.ui.toolpath_state_controller import ToolpathStateControllerMixin


def test_selection_and_transform_domain_stays_out_of_main_window() -> None:
    owned = {
        "_sync_selection_action_state",
        "_select_project_indices",
        "_viewport_transform_changed",
        "_show_viewport_item_context_menu",
        "_transform_control_changed",
        "_duplicate_selected_item",
        "_apply_selected_transform_components",
    }
    assert owned <= SelectionTransformControllerMixin.__dict__.keys()
    assert owned.isdisjoint(MainWindow.__dict__.keys())
    assert SelectionTransformControllerMixin in MainWindow.__mro__


def test_import_lifecycle_stays_out_of_main_window() -> None:
    owned = {
        "_import_file",
        "_start_import",
        "_import_progress_changed",
        "_import_completed",
        "_import_failed",
        "_import_thread_finished",
    }
    assert owned <= ImportControllerMixin.__dict__.keys()
    assert owned.isdisjoint(MainWindow.__dict__.keys())
    assert ImportControllerMixin in MainWindow.__mro__


def test_toolpath_state_domain_stays_out_of_main_window() -> None:
    owned = {
        "_set_cam_status",
        "_sync_toolpath_output_state",
        "_toolpath_source_names",
        "_sync_toolpath_state_from_project",
        "_invalidate_toolpaths",
    }
    assert owned <= ToolpathStateControllerMixin.__dict__.keys()
    assert owned.isdisjoint(MainWindow.__dict__.keys())
    assert ToolpathStateControllerMixin in MainWindow.__mro__


def test_project_inspector_domain_stays_out_of_main_window() -> None:
    owned = {
        "_refresh_project_list",
        "_project_item_changed",
        "_sync_stock_controls",
        "_stock_control_changed",
        "_ensure_inspector_visible",
    }
    assert owned <= ProjectInspectorControllerMixin.__dict__.keys()
    assert owned.isdisjoint(MainWindow.__dict__.keys())
    assert ProjectInspectorControllerMixin in MainWindow.__mro__
