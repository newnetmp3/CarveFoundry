import pytest
from PySide6.QtWidgets import QApplication

from carvefoundry.cam.toolpath import Toolpath
from carvefoundry.core.primitives import text_mesh
from carvefoundry.core.project import Project, ProjectItem, TextProperties
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.core.transform import Transform3D
from carvefoundry.ui.main_window import MainWindow
from carvefoundry.ui.project_window import MainWindow as ProjectMainWindow

_APP = QApplication.instance() or QApplication([])


def test_main_window_builds_text_inspector_offscreen() -> None:
    window = MainWindow()
    try:
        assert window.text_font_combo.count() > 0
        assert window.text_font_style_combo.count() > 0
        assert window.text_geometry_combo.count() == 2
        assert window.text_widget.isHidden()
    finally:
        window.close()


def test_text_edit_updates_geometry_preserves_placement_and_invalidates_cam() -> None:
    window = ProjectMainWindow()
    try:
        family = window.text_font_combo.currentFont().family()
        original = TextProperties(
            content="CARVE",
            font_family=family,
            size_pt=24.0,
            depth_mm=1.0,
        )
        item = ProjectItem(
            "Title",
            kind="text",
            mesh=text_mesh(properties=original),
            transform=Transform3D(
                translation_mm=(25.0, 35.0, -1.0),
            ),
            text_properties=original,
        )
        cutter = Cutter("3 mm flat", ToolType.FLAT_END_MILL, 3.0)
        path = Toolpath(
            "Title finish",
            "finish",
            cutter,
            2.0,
            source_item_id=item.item_id,
            source_item_name=item.name,
        )
        project = Project(items=[item], toolpaths=[path])
        window._set_project(
            project,
            project_path=None,
            selected_row=1,
        )

        before_translation = item.transform.translation_mm
        before_size = item.local_size_mm()
        assert before_size is not None

        window.text_size_spin.setValue(48.0)
        window.text_underline_button.setChecked(True)
        window._text_update_timer.stop()
        window._apply_text_properties_from_controls()

        edited = window.project.items[0]
        edited_properties = edited.text_properties
        edited_size = edited.local_size_mm()
        assert edited_properties is not None
        assert edited_size is not None
        assert edited_properties.size_pt == pytest.approx(48.0)
        assert edited_properties.underline is True
        assert edited.transform.translation_mm == before_translation
        assert edited_size[0] > before_size[0]
        assert window.size_spins[0].value() == pytest.approx(
            edited_size[0],
            abs=0.01,
        )
        assert window.project.toolpaths == []
        assert window._toolpaths_stale_reason == "Text geometry"
        assert len(window._undo_stack) == 1

        window._undo()
        restored = window.project.items[0]
        assert restored.text_properties == original
        assert restored.transform.translation_mm == before_translation
        assert len(window.project.toolpaths) == 1

        window._redo()
        redone = window.project.items[0]
        assert redone.text_properties == edited_properties
        assert redone.transform.translation_mm == before_translation
        assert window.project.toolpaths == []
    finally:
        window.close()
