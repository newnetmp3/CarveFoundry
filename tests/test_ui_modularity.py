"""Architecture regressions for UI controller boundaries."""
from __future__ import annotations

from carvefoundry.ui.import_controller import ImportControllerMixin
from carvefoundry.ui.main_window import MainWindow
from carvefoundry.ui.project_file_controller import ProjectFileControllerMixin
from carvefoundry.ui.project_inspector_controller import ProjectInspectorControllerMixin
from carvefoundry.ui.selection_transform_controller import SelectionTransformControllerMixin
from carvefoundry.ui.toolpath_state_controller import ToolpathStateControllerMixin
from carvefoundry.ui.workspace_action_registry import WorkspaceActionRegistryMixin
from carvefoundry.ui.workspace_commands import WorkspaceCommandsMixin
from carvefoundry.ui.workspace_menu_builder import WorkspaceMenuBuilderMixin
from carvefoundry.ui.workspace_surface_builder import WorkspaceSurfaceBuilderMixin


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


def test_workspace_command_facade_stays_split_by_surface() -> None:
    assert "_build_command_actions" in WorkspaceActionRegistryMixin.__dict__
    assert "_build_main_menu_bar" in WorkspaceMenuBuilderMixin.__dict__
    assert "_build_tool_rail" in WorkspaceSurfaceBuilderMixin.__dict__
    assert "_populate_ribbon" in WorkspaceSurfaceBuilderMixin.__dict__
    assert "_build_command_actions" not in WorkspaceCommandsMixin.__dict__
    assert "_build_main_menu_bar" not in WorkspaceCommandsMixin.__dict__
    assert "_build_tool_rail" not in WorkspaceCommandsMixin.__dict__


def test_project_file_lifecycle_stays_out_of_main_window() -> None:
    owned = {
        "_set_project",
        "_new_project",
        "_open_project",
        "_save_project",
        "_save_project_as",
        "_save_project_to",
        "_export_gcode",
    }
    assert owned <= ProjectFileControllerMixin.__dict__.keys()
    assert owned.isdisjoint(MainWindow.__dict__.keys())
    assert ProjectFileControllerMixin in MainWindow.__mro__
