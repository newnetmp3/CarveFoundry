"""Architecture regressions for UI controller boundaries."""
from __future__ import annotations

from carvefoundry.ui.main_window import MainWindow
from carvefoundry.ui.selection_transform_controller import SelectionTransformControllerMixin


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
