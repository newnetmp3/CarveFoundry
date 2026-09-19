import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import QApplication, QComboBox, QSizePolicy

from carvefoundry.cam.toolpath import Toolpath
from carvefoundry.core.primitives import rectangle_mesh, text_mesh
from carvefoundry.core.project import Project, ProjectItem, TextProperties
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.core.transform import Transform3D
from carvefoundry.ui.main_window import MainWindow
from carvefoundry.ui.project_window import MainWindow as ProjectMainWindow

_APP = QApplication.instance() or QApplication([])


def test_photopea_menu_bar_replaces_visible_ribbon_and_full_rail() -> None:
    window = MainWindow()
    try:
        assert window.tool_rail.width() == 46
        assert window.ribbon.isHidden()
        assert window.main_menu_bar.isVisible() is False
        assert [
            action.text()
            for action in window.main_menu_bar.actions()
        ] == [
            "File",
            "Edit",
            "Design",
            "Model",
            "Toolpaths",
            "Machine",
            "View",
        ]
        assert {
            "camera",
            "select",
            "shapes",
            "line",
            "text",
            "vector",
            "file",
            "edit",
            "arrange",
            "model",
            "cam",
            "cutter",
            "machine",
            "view",
        }.issubset(window.tool_rail.buttons)
        assert (
            window.tool_rail._layout.itemAt(0).widget()
            is window.tool_rail.buttons["camera"]
        )
        assert window.tool_rail.buttons["camera"].isChecked()
        assert not window.tool_rail.buttons["camera"].icon().isNull()
        assert not window.tool_rail.buttons["select"].isChecked()
        assert window.viewport.camera_control_mode
        assert len(window.tool_rail.buttons["shapes"].menu().actions()) == 3

        window._activate_navigation_tool()
        assert not window.viewport.camera_control_mode
        assert window.tool_rail.buttons["select"].isChecked()
        assert not window.tool_rail.buttons["camera"].isChecked()

        window._set_shape_tool("ellipse")
        assert not window.viewport.camera_control_mode
        assert window.viewport.shape_draw_mode == "ellipse"
        assert window.tool_rail.buttons["shapes"].isChecked()
        assert (
            window.tool_rail.buttons["shapes"].property("currentAction")
            == "ellipse"
        )

        window._activate_camera_tool()
        assert window.viewport.shape_draw_mode is None
        assert window.viewport.camera_control_mode
        assert window.tool_rail.buttons["camera"].isChecked()
        assert not window.tool_rail.buttons["select"].isChecked()
    finally:
        window.close()


def test_viewport_multi_selection_syncs_layers_and_actions() -> None:
    window = MainWindow()
    try:
        project = Project(
            items=[
                ProjectItem(
                    "Left",
                    kind="rectangle",
                    mesh=rectangle_mesh(10.0, 10.0, 1.0),
                    transform=Transform3D(
                        translation_mm=(25.0, 25.0, 0.0),
                    ),
                ),
                ProjectItem(
                    "Right",
                    kind="rectangle",
                    mesh=rectangle_mesh(10.0, 10.0, 1.0),
                    transform=Transform3D(
                        translation_mm=(75.0, 25.0, 0.0),
                    ),
                ),
            ]
        )
        window._set_project(
            project,
            project_path=None,
            selected_row=1,
        )

        window._viewport_selection_requested([0], "replace")
        window._viewport_selection_requested([1], "add")

        assert window._selected_design_indices() == [0, 1]
        assert window.viewport._renderer.selected_item_indices == {0, 1}
        assert "2 objects selected" in window.selection_info.text()
        assert window._selection_action_buttons["group"].isEnabled()
        assert window._selection_action_buttons["align"].isEnabled()

        window._viewport_selection_requested([0], "toggle")
        assert window._selected_design_indices() == [1]
        assert window.viewport._renderer.selected_item_indices == {1}

        window._viewport_selection_requested([], "replace")
        assert window._selected_design_indices() == []
        assert window.viewport._renderer.selected_item_indices == set()
    finally:
        window.close()


def test_viewport_marquee_detects_multiple_visible_objects() -> None:
    window = MainWindow()
    try:
        project = Project(
            items=[
                ProjectItem(
                    "One",
                    kind="rectangle",
                    mesh=rectangle_mesh(12.0, 12.0, 1.0),
                    transform=Transform3D(
                        translation_mm=(30.0, 30.0, 0.0),
                    ),
                ),
                ProjectItem(
                    "Two",
                    kind="rectangle",
                    mesh=rectangle_mesh(12.0, 12.0, 1.0),
                    transform=Transform3D(
                        translation_mm=(90.0, 60.0, 0.0),
                    ),
                ),
            ]
        )
        window._set_project(
            project,
            project_path=None,
            selected_row=1,
        )
        renderer = window.viewport._renderer
        renderer.resize(800, 600)

        selected = renderer._selection_indices_in_screen_rect(
            QPointF(0.0, 0.0),
            QPointF(800.0, 600.0),
        )
        assert selected == [0, 1]

        assert renderer._selection_mode_for_modifiers(
            Qt.KeyboardModifier.NoModifier
        ) == "replace"
        assert renderer._selection_mode_for_modifiers(
            Qt.KeyboardModifier.ShiftModifier
        ) == "add"
        assert renderer._selection_mode_for_modifiers(
            Qt.KeyboardModifier.ControlModifier
        ) == "toggle"
    finally:
        window.close()


def test_main_window_builds_text_inspector_offscreen() -> None:
    window = MainWindow()
    try:
        assert window.text_font_combo.count() > 0
        assert window.text_font_style_combo.count() > 0
        assert window.text_geometry_combo.count() == 2
        assert window.text_widget.isHidden()
    finally:
        window.close()


def test_inspector_stays_compact_without_clipping_field_minimums() -> None:
    window = MainWindow()
    try:
        assert window.properties_panel.minimumWidth() == 260
        assert (
            window.properties_panel.body.sizePolicy().horizontalPolicy()
            == QSizePolicy.Policy.Ignored
        )
        assert window.text_widget.minimumSizeHint().width() <= 260
        assert window.transform_widget.minimumSizeHint().width() <= 260

        responsive_fields = (
            window.text_font_combo,
            window.text_font_variant_combo,
            window.text_font_style_combo,
            window.text_size_spin,
            window.text_alignment_combo,
            window.text_case_combo,
            window.text_character_spacing_spin,
            window.text_word_spacing_spin,
            window.text_line_spacing_spin,
            window.text_horizontal_scale_spin,
            window.text_box_width_spin,
            window.text_geometry_combo,
            window.text_outline_width_spin,
            window.text_depth_spin,
            window.source_units_combo,
            *window.position_spins,
            *window.rotation_spins,
            *window.size_spins,
            *window.scale_spins,
        )
        assert all(field.minimumWidth() == 0 for field in responsive_fields)
    finally:
        window.close()


def test_inspector_scrollbar_matches_ribbon_scroll_policy() -> None:
    window = MainWindow()
    try:
        scroll_area = window.properties_panel.scroll_area
        assert (
            scroll_area.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        assert (
            scroll_area.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
    finally:
        window.close()


def test_font_family_grouping_separates_common_variants() -> None:
    groups = MainWindow._group_text_font_families(
        [
            "Noto Sans",
            "Noto Sans Condensed",
            "Noto Sans SemiCondensed",
            "Noto Sans SemiBold",
            "Liberation Serif",
            "Franklin Gothic Medium",
        ]
    )

    assert groups["Noto Sans"] == [
        ("Regular", "Noto Sans"),
        ("Condensed", "Noto Sans Condensed"),
        ("Semi Condensed", "Noto Sans SemiCondensed"),
        ("SemiBold", "Noto Sans SemiBold"),
    ]
    assert groups["Liberation Serif"] == [
        ("Regular", "Liberation Serif")
    ]
    # A lone suffix-like family stays intact instead of inventing a base
    # family that is not actually present.
    assert groups["Franklin Gothic Medium"] == [
        ("Regular", "Franklin Gothic Medium")
    ]


def test_text_font_selector_previews_grouped_families_and_variants() -> None:
    window = MainWindow()
    try:
        assert isinstance(window.text_font_combo, QComboBox)
        assert isinstance(window.text_font_variant_combo, QComboBox)
        assert window.text_font_combo.count() > 0
        assert window.text_font_combo.currentText()
        assert window.text_font_variant_combo.count() > 0
        for index in range(min(5, window.text_font_combo.count())):
            item_font = window.text_font_combo.itemData(
                index,
                Qt.ItemDataRole.FontRole,
            )
            concrete_family = window.text_font_combo.itemData(index)
            assert isinstance(item_font, QFont)
            assert isinstance(concrete_family, str)
            assert item_font.family() == concrete_family

        for index in range(window.text_font_variant_combo.count()):
            item_font = window.text_font_variant_combo.itemData(
                index,
                Qt.ItemDataRole.FontRole,
            )
            concrete_family = window.text_font_variant_combo.itemData(index)
            assert isinstance(item_font, QFont)
            assert item_font.family() == concrete_family
    finally:
        window.close()


def test_select_tool_and_escape_cancel_active_drawing_mode() -> None:
    window = MainWindow()
    try:
        select_button = window._navigation_tool_button
        rectangle_button = window._shape_tool_buttons["rectangle"]

        assert select_button is not None
        assert select_button.isChecked()
        assert window.viewport.shape_draw_mode is None

        rectangle_button.setChecked(True)
        window._set_shape_tool("rectangle")
        assert window._active_shape_tool == "rectangle"
        assert window.viewport.shape_draw_mode == "rectangle"
        assert rectangle_button.isChecked()
        assert not select_button.isChecked()

        window._activate_navigation_tool()
        assert window._active_shape_tool is None
        assert window.viewport.shape_draw_mode is None
        assert select_button.isChecked()
        assert not rectangle_button.isChecked()

        rectangle_button.setChecked(True)
        window._set_shape_tool("rectangle")
        escape_action = next(
            action
            for action in window._shortcut_actions
            if action.text() == "Select / Cancel Tool"
        )
        assert escape_action.shortcut() == QKeySequence("Escape")
        escape_action.trigger()

        assert window._active_shape_tool is None
        assert window.viewport.shape_draw_mode is None
        assert select_button.isChecked()
        assert not rectangle_button.isChecked()
    finally:
        window.close()


def test_contextual_tool_options_bar_tracks_active_draw_tool() -> None:
    window = MainWindow()
    try:
        assert window.tool_options_bar.isHidden()

        window._set_shape_tool("rectangle")
        assert not window.tool_options_bar.isHidden()
        assert window.tool_options_title.text() == "Rectangle Tool"
        assert window.tool_options_polygon_sides.isHidden()
        assert window.tool_options_line_width_spin.isHidden()
        assert window.tool_options_text_edit.isHidden()

        window.tool_options_depth_spin.setValue(2.75)
        window._shape_drawn("rectangle", 10.0, 20.0, 30.0, 35.0)
        rectangle = window.project.items[-1]
        assert rectangle.kind == "rectangle"
        assert rectangle.local_size_mm() == pytest.approx(
            (20.0, 15.0, 2.75),
            abs=0.01,
        )

        window._set_shape_tool("polygon")
        assert not window.tool_options_polygon_sides.isHidden()
        window.tool_options_polygon_sides.setValue(9)
        assert window._tool_option_polygon_sides == 9

        window._set_shape_tool("line")
        assert not window.tool_options_line_width_spin.isHidden()
        window.tool_options_line_width_spin.setValue(4.5)
        window._shape_drawn("line", 0.0, 0.0, 20.0, 0.0)
        line = window.project.items[-1]
        assert line.kind == "line"
        assert line.local_size_mm() == pytest.approx(
            (20.0, 4.5, 2.75),
            abs=0.01,
        )

        window._set_shape_tool("text")
        assert not window.tool_options_text_edit.isHidden()
        assert not window.tool_options_font_value.isHidden()
        window.tool_options_text_edit.setText("NAVY")
        window._shape_drawn("text", 5.0, 5.0, 45.0, 20.0)
        text_item = window.project.items[-1]
        assert text_item.text_properties is not None
        assert text_item.text_properties.content == "NAVY"
        assert text_item.text_properties.depth_mm == pytest.approx(2.75)

        window._apply_active_tool()
        assert window._active_shape_tool is None
        assert window.viewport.shape_draw_mode is None
        assert window.tool_options_bar.isHidden()

        window._set_shape_tool("ellipse")
        assert not window.tool_options_bar.isHidden()
        window._cancel_active_tool()
        assert window._active_shape_tool is None
        assert window.viewport.shape_draw_mode is None
        assert window.tool_options_bar.isHidden()
    finally:
        window.close()


def test_text_edit_updates_geometry_preserves_placement_and_invalidates_cam() -> None:
    window = ProjectMainWindow()
    try:
        family = window._selected_text_font_family()
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
