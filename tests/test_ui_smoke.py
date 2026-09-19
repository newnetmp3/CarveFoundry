import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import QApplication, QComboBox, QGroupBox, QSizePolicy

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


def test_generate_toolpaths_button_opens_complete_requirement_dialog() -> None:
    window = MainWindow()
    try:
        item = ProjectItem(
            "Panel",
            kind="rectangle",
            mesh=rectangle_mesh(40.0, 30.0, 2.0),
        )
        window._set_project(
            Project(items=[item]),
            project_path=None,
            selected_row=1,
        )

        assert window.generate_toolpaths_button is not None
        assert window.generate_toolpaths_button.text() == "Generate Toolpaths"
        assert window.generate_toolpaths_button.isEnabled()
        assert window._ui_actions["calculate"].text() == "Generate Toolpaths…"

        dialog = window._build_toolpath_generation_dialog()
        fields = dialog.generation_fields

        section_titles = {
            box.title()
            for box in dialog.findChildren(QGroupBox)
        }
        assert {
            "1. Source & Operation",
            "2. Cutter",
            "3. Geometry & Strategy",
            "4. Depth Requirements",
            "5. Motion & Safety",
            "6. Tabs / Cutout Holding",
            "7. Generation Readiness",
        }.issubset(section_titles)

        assert "All 1 design object" in fields["source_summary"].text()
        assert "Panel" in fields["source_summary"].text()
        assert fields["operation"].currentData() == "finish"
        assert fields["generate"].isEnabled()
        assert not fields["cut_type"].isEnabled()
        assert fields["3d_style"].isEnabled()
        assert fields["linking"].isEnabled()

        fields["operation"].setCurrentIndex(
            fields["operation"].findData("profile")
        )
        assert fields["cut_type"].isEnabled()
        assert not fields["3d_style"].isEnabled()
        assert fields["linking"].isEnabled()
        assert fields["local_clearance"].isEnabled()
        assert not fields["link_tolerance"].isEnabled()
        assert fields["tabs_enabled"].isEnabled()
        dialog.close()
    finally:
        window.close()


def test_generate_toolpaths_uses_all_objects_regardless_of_selection() -> None:
    window = MainWindow()
    try:
        project = Project(
            items=[
                ProjectItem(
                    "Left",
                    kind="rectangle",
                    mesh=rectangle_mesh(20.0, 15.0, 2.0),
                    transform=Transform3D(
                        translation_mm=(10.0, 10.0, 0.0),
                    ),
                ),
                ProjectItem(
                    "Right",
                    kind="rectangle",
                    mesh=rectangle_mesh(18.0, 12.0, 2.0),
                    transform=Transform3D(
                        translation_mm=(50.0, 10.0, 0.0),
                    ),
                ),
            ]
        )
        window._set_project(
            project,
            project_path=None,
            selected_row=0,
        )
        assert window._selected_item() is None

        window._select_cam_operation("profile")
        window._calculate_toolpath_now()

        assert len(window.project.toolpaths) == 2
        assert {
            path.source_item_name
            for path in window.project.toolpaths
        } == {"Left", "Right"}
        assert {
            path.source_item_id
            for path in window.project.toolpaths
        } == {
            project.items[0].item_id,
            project.items[1].item_id,
        }
    finally:
        window.close()


def test_waterline_generation_has_required_trimesh_graph_dependency() -> None:
    window = MainWindow()
    try:
        project = Project(
            items=[
                ProjectItem(
                    "Relief",
                    kind="rectangle",
                    mesh=rectangle_mesh(20.0, 15.0, 3.0),
                )
            ]
        )
        window._set_project(
            project,
            project_path=None,
            selected_row=0,
        )

        window._select_cam_operation("waterline")
        window._calculate_toolpath_now()

        assert window.project.toolpaths
        assert window.project.toolpaths[0].operation == "3d_waterline"
        assert window.project.toolpaths[0].source_item_name == "Relief"
    finally:
        window.close()


def test_generation_dialog_exposes_extended_milling_methods() -> None:
    window = MainWindow()
    try:
        dialog = window._build_toolpath_generation_dialog()
        fields = dialog.generation_fields

        operations = {
            fields["operation"].itemData(index)
            for index in range(fields["operation"].count())
        }
        assert {
            "profile",
            "silhouette",
            "pocket",
            "surface",
            "vcarve",
            "engrave",
            "drill",
            "center_drill",
            "rough",
            "finish",
            "height_map",
            "rest",
            "waterline",
        }.issubset(operations)

        fields["operation"].setCurrentIndex(
            fields["operation"].findData("surface")
        )
        assert fields["generate"].isEnabled()
        assert fields["direction"].isEnabled()
        assert fields["pocket_stepover"].isEnabled()
        assert not fields["3d_style"].isEnabled()
        dialog.close()

        for key in (
            "cam_silhouette",
            "cam_surface",
            "cam_center_drill",
            "cam_height_map",
        ):
            assert key in window._ui_actions
    finally:
        window.close()


def test_surface_can_generate_from_stock_without_design_geometry() -> None:
    window = MainWindow()
    try:
        window._set_project(
            Project(),
            project_path=None,
            selected_row=0,
        )
        assert window.generate_toolpaths_button is not None
        assert window.generate_toolpaths_button.isEnabled()

        window._select_cam_operation("surface")
        window._settings.setValue("cam/overall_depth_mm", 0.5)
        window._settings.setValue("cam/stepdown_mm", 1.0)
        window._calculate_toolpath_now()

        assert len(window.project.toolpaths) == 1
        path = window.project.toolpaths[0]
        assert path.operation == "surface"
        assert path.source_item_name == "Stock"
    finally:
        window.close()


def test_text_inspector_exposes_exact_font_verification() -> None:
    window = MainWindow()
    try:
        family = window._selected_text_font_family()
        window._update_text_font_availability(family)

        assert window.text_font_verify_button.text() == "Verify Font Face"
        assert "Font face:" in window.text_font_face_status.text()
        assert "exact" in window.text_font_face_status.text().lower()
        assert window.text_font_warning.isHidden()
    finally:
        window.close()


def test_generation_dialog_blocks_incompatible_vcarve_cutter() -> None:
    window = MainWindow()
    try:
        item = ProjectItem(
            "Badge",
            kind="rectangle",
            mesh=rectangle_mesh(30.0, 20.0, 2.0),
        )
        window._set_project(
            Project(items=[item]),
            project_path=None,
            selected_row=1,
        )
        dialog = window._build_toolpath_generation_dialog()
        fields = dialog.generation_fields

        fields["operation"].setCurrentIndex(
            fields["operation"].findData("vcarve")
        )

        flat_index = next(
            index
            for index in range(fields["cutter"].count())
            if fields["cutter"].itemData(index).tool_type
            == ToolType.FLAT_END_MILL
        )
        fields["cutter"].setCurrentIndex(flat_index)
        assert not fields["generate"].isEnabled()
        assert "V-Carve cutter" in fields["readiness"].text()

        v_index = next(
            index
            for index in range(fields["cutter"].count())
            if fields["cutter"].itemData(index).tool_type
            in {ToolType.V_BIT, ToolType.ENGRAVING_CONE}
        )
        fields["cutter"].setCurrentIndex(v_index)
        assert fields["generate"].isEnabled()
        dialog.close()
    finally:
        window.close()


def test_pen_tool_draws_freehand_without_dialog_and_exposes_options() -> None:
    window = MainWindow()
    try:
        window._create_pen_path()

        assert window.viewport.shape_draw_mode == "pen"
        assert not window.viewport.camera_control_mode
        assert window._ui_actions["pen"].isChecked()
        assert window.tool_rail.buttons["vector"].isChecked()
        assert not window.tool_options_bar.isHidden()
        assert not window.tool_options_pen_width_spin.isHidden()
        assert not window.tool_options_pen_smoothing_spin.isHidden()
        assert not window.tool_options_pen_spacing_spin.isHidden()
        assert not window.tool_options_pen_close_check.isHidden()
        assert window.tool_options_text_edit.isHidden()

        window.tool_options_pen_width_spin.setValue(3.25)
        window.tool_options_pen_smoothing_spin.setValue(60)
        window.tool_options_pen_spacing_spin.setValue(0.2)
        window.tool_options_pen_close_check.setChecked(True)

        before = len(window.project.items)
        window._freehand_pen_drawn(
            [(10.0, 10.0), (15.0, 12.0), (20.0, 9.0), (25.0, 14.0)]
        )

        assert len(window.project.items) == before + 1
        assert window.project.items[-1].kind == "pen"
        assert window.project.items[-1].name.startswith("Pen Stroke")
        assert window.viewport.shape_draw_mode == "pen"
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


def test_fontconfig_aliases_collapse_full_face_names_into_styles() -> None:
    families = [
        "FiraCode Nerd Font",
        "FiraCode Nerd Font Med",
        "FiraCode Nerd Font Mono",
        "FiraCode Nerd Font Mono SemBd",
        "FiraCode Nerd Font Propo",
    ]
    aliases = MainWindow._parse_fontconfig_text_font_aliases(
        (
            "FiraCode Nerd Font\tMedium\tFiraCode Nerd Font Med\n"
            "FiraCode Nerd Font Mono\tSemiBold\t"
            "FiraCode Nerd Font Mono SemBd"
        ),
        families,
    )

    assert aliases["firacode nerd font med"] == (
        "FiraCode Nerd Font",
        "Medium",
    )
    assert aliases["firacode nerd font mono sembd"] == (
        "FiraCode Nerd Font Mono",
        "SemiBold",
    )

    selectable = [
        family
        for family in families
        if family.casefold() not in aliases
    ]
    groups = MainWindow._group_text_font_families(selectable)
    assert groups["FiraCode Nerd Font"] == [
        ("Regular", "FiraCode Nerd Font"),
        ("Monospaced", "FiraCode Nerd Font Mono"),
        ("Proportional", "FiraCode Nerd Font Propo"),
    ]


def test_font_variant_fallback_understands_common_abbreviations() -> None:
    assert MainWindow._font_family_variant_candidate(
        "3270 Nerd Font Mono SemCond"
    ) == ("3270 Nerd Font", "Monospaced Semi Condensed")
    assert MainWindow._font_family_variant_candidate(
        "FiraCode Nerd Font Propo Med"
    ) == ("FiraCode Nerd Font", "Proportional Medium")
    assert MainWindow._font_family_variant_candidate(
        "RobotoMono Nerd Font Mono SmBd"
    ) == ("RobotoMono Nerd Font", "Monospaced SemiBold")
    assert MainWindow._font_family_variant_candidate(
        "RobotoMono Nerd Font Mono SmBd [GOOG]"
    ) == (
        "RobotoMono Nerd Font [GOOG]",
        "Monospaced SemiBold",
    )


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
        camera_button = window._camera_tool_button
        select_button = window._navigation_tool_button
        rectangle_button = window._shape_tool_buttons["rectangle"]

        assert camera_button is not None
        assert camera_button.isChecked()
        assert select_button is not None
        assert not select_button.isChecked()
        assert window.viewport.camera_control_mode
        assert window.viewport.shape_draw_mode is None

        window._activate_navigation_tool()
        assert select_button.isChecked()
        assert not camera_button.isChecked()
        assert not window.viewport.camera_control_mode

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


def test_text_viewport_resize_handles_scale_live_and_anchor_opposite_corner() -> None:
    window = MainWindow()
    try:
        family = window._selected_text_font_family()
        properties = TextProperties(
            content="HANDLE",
            font_family=family,
            size_pt=36.0,
            depth_mm=1.5,
        )
        item = ProjectItem(
            "Resizable Text",
            kind="text",
            mesh=text_mesh(properties=properties),
            transform=Transform3D(
                translation_mm=(55.0, 45.0, -1.5),
            ),
            text_properties=properties,
        )
        window._set_project(
            Project(items=[item]),
            project_path=None,
            selected_row=1,
        )
        window._activate_navigation_tool()

        renderer = window.viewport._renderer
        before = renderer._text_resize_world_corners(item).copy()
        before_size = item.local_size_mm()
        assert before_size is not None
        assert renderer._selected_text_resize_item() is not None
        assert len(renderer._text_resize_frame_vertices(0.2)) == 40

        assert renderer._begin_text_resize(0, 2)
        assert renderer.transform_interaction_kind == "resize-text"
        assert renderer._apply_text_resize_factor(0, 1.5)

        after = renderer._text_resize_world_corners(item)
        after_size = item.local_size_mm()
        assert after_size is not None

        # Handle 0 is opposite handle 2 and therefore remains fixed in world
        # space while the dragged corner moves outward.
        assert np.allclose(after[0], before[0], atol=1e-6)
        before_diagonal = np.linalg.norm(before[2] - before[0])
        after_diagonal = np.linalg.norm(after[2] - after[0])
        assert after_diagonal == pytest.approx(before_diagonal * 1.5)
        assert after_size[0] == pytest.approx(before_size[0] * 1.5)
        assert after_size[1] == pytest.approx(before_size[1] * 1.5)
        assert after_size[2] == pytest.approx(before_size[2])
        assert item.transform.scale_xyz[2] == pytest.approx(1.0)
    finally:
        window.close()


def test_text_resize_handles_remain_available_while_text_tool_is_active() -> None:
    window = MainWindow()
    try:
        family = window._selected_text_font_family()
        properties = TextProperties(
            content="EDIT",
            font_family=family,
            size_pt=32.0,
            depth_mm=1.0,
        )
        item = ProjectItem(
            "Editable Text",
            kind="text",
            mesh=text_mesh(properties=properties),
            text_properties=properties,
        )
        window._set_project(
            Project(items=[item]),
            project_path=None,
            selected_row=1,
        )

        window._set_shape_tool("text")
        renderer = window.viewport._renderer

        assert renderer.shape_draw_mode == "text"
        assert not renderer.camera_control_mode
        assert renderer._selected_text_resize_item() is not None
        assert renderer._begin_text_resize(0, 1)
    finally:
        window.close()


def test_text_resize_finish_invalidates_cam_as_text_size_change() -> None:
    window = MainWindow()
    try:
        family = window._selected_text_font_family()
        properties = TextProperties(
            content="CAM",
            font_family=family,
            size_pt=30.0,
            depth_mm=1.0,
        )
        item = ProjectItem(
            "CAM Text",
            kind="text",
            mesh=text_mesh(properties=properties),
            text_properties=properties,
        )
        cutter = Cutter("3 mm flat", ToolType.FLAT_END_MILL, 3.0)
        path = Toolpath(
            "Text profile",
            "profile",
            cutter,
            1.5,
            source_item_id=item.item_id,
            source_item_name=item.name,
        )
        window._set_project(
            Project(items=[item], toolpaths=[path]),
            project_path=None,
            selected_row=1,
        )
        window._activate_navigation_tool()

        renderer = window.viewport._renderer
        assert renderer._begin_text_resize(0, 2)
        assert renderer._apply_text_resize_factor(0, 1.25)
        window._viewport_transform_finished(0)

        assert window.project.toolpaths == []
        assert window._toolpaths_stale_reason == "Text size"
        assert "Resized CAM Text" in window.statusBar().currentMessage()
    finally:
        window.close()


def test_project_history_labels_viewport_text_resize() -> None:
    window = ProjectMainWindow()
    try:
        family = window._selected_text_font_family()
        properties = TextProperties(
            content="UNDO",
            font_family=family,
            size_pt=30.0,
            depth_mm=1.0,
        )
        item = ProjectItem(
            "Undo Text",
            kind="text",
            mesh=text_mesh(properties=properties),
            text_properties=properties,
        )
        window._set_project(
            Project(items=[item]),
            project_path=None,
            selected_row=1,
        )
        window._activate_navigation_tool()

        renderer = window.viewport._renderer
        assert renderer._begin_text_resize(0, 2)
        window._viewport_transform_started(0)
        assert renderer._apply_text_resize_factor(0, 1.2)
        window._viewport_transform_finished(0)

        assert window._undo_stack
        assert window._undo_stack[-1].label == "resize text"
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
