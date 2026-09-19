"""Layout ergonomics and module-extraction regressions for desktop UI."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")

from PySide6.QtWidgets import QApplication, QPushButton

from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.ui.cam_dialog_help import cam_generation_help
from carvefoundry.ui.inspector_controls import InspectorControlsMixin
from carvefoundry.ui.main_window import MainWindow

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
    window.show()
    _APP.processEvents()
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
