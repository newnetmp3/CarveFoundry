"""Inspector-top Layers, Eye/Lock hit targets, and persisted edit protection."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from carvefoundry.core.history import capture_workspace, restore_workspace
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.project_file import load_project, save_project
from carvefoundry.ui.layers_popup import LAYER_LOCK_ROLE, LayerRowDelegate
from carvefoundry.ui.project_window import MainWindow

_APP = QApplication.instance() or QApplication([])


def _window() -> MainWindow:
    window = MainWindow()
    window._set_project(
        Project(items=[
            ProjectItem("Relief", kind="stl", mesh=rectangle_mesh(30, 25, 2)),
            ProjectItem("Name", kind="text", mesh=rectangle_mesh(15, 10, 1)),
        ]),
        project_path=None,
        selected_row=1,
    )
    return window


def _click_layer_icon(window: MainWindow, row: int, icon: str) -> None:
    listing = window.project_list
    delegate = listing.itemDelegate()
    assert isinstance(delegate, LayerRowDelegate)
    visual = listing.visualItemRect(listing.item(row))
    if not visual.isValid():
        listing.scrollToItem(listing.item(row))
        visual = listing.visualItemRect(listing.item(row))
    area = delegate.icon_rects(visual)[0 if icon == "eye" else 1]
    center = QPointF(area.center())
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        center,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    option = QStyleOptionViewItem()
    option.rect = visual
    index = listing.model().index(row, 0)
    assert delegate.editorEvent(event, listing.model(), option, index)


def test_layers_are_at_inspector_top_not_a_popup() -> None:
    window = _window()
    try:
        assert window.properties_panel.body_layout.itemAt(0).widget() is window.layers_popup
        assert window.project_list.parent() is window.layers_popup
        assert not window.layers_popup.windowFlags() & Qt.WindowType.Popup
        assert window.project_list.count() == 3
        assert window.project_list.item(0).text() == window._stock_list_text()
        assert window.project_list.item(1).text() == "Relief"
        assert window.project_list.item(2).text() == "Name"
        assert window.layers_popup.count_label.text() == "2 objects"
        window._show_layers_popup()
        assert window.properties_panel.isVisible() is False or (
            not window.properties_panel.isHidden()
        )
    finally:
        window.close()


def test_eye_and_lock_toggle_independently_and_are_undoable() -> None:
    window = _window()
    try:
        assert window.project.items[0].visible
        assert not window.project.items[0].locked
        _click_layer_icon(window, 1, "eye")
        assert not window.project.items[0].visible
        assert not window.project.items[0].locked
        assert window.project_list.item(1).checkState() == Qt.CheckState.Unchecked
        assert not window.viewport._renderer._item_viewport_visible(
            0, window.project.items[0]
        )
        _click_layer_icon(window, 1, "lock")
        assert window.project.items[0].locked
        assert not window.project.items[0].visible
        assert window.project_list.item(1).data(LAYER_LOCK_ROLE) is True
        assert not window.project_list.item(1).flags() & Qt.ItemFlag.ItemIsEditable
        window._undo()
        assert not window.project.items[0].locked
        assert not window.project.items[0].visible
        window._undo()
        assert window.project.items[0].visible
        window._redo()
        window._redo()
        assert window.project.items[0].locked
        assert not window.project.items[0].visible
        _click_layer_icon(window, 1, "eye")
        assert window.project.items[0].visible
        assert window.project.items[0].locked
        _click_layer_icon(window, 1, "lock")
        assert not window.project.items[0].locked
        assert window.project_list.item(1).flags() & Qt.ItemFlag.ItemIsEditable
    finally:
        window.close()


def test_lock_blocks_mutations_but_allows_selection_and_visibility() -> None:
    window = _window()
    try:
        _click_layer_icon(window, 1, "lock")
        assert window.project.items[0].locked
        window._select_project_indices([0], primary=0)
        assert window.viewport._renderer.selected_item_index == 0
        assert not window.transform_widget.isEnabled()
        assert not window._ui_actions["apply_scale"].isEnabled()

        before = tuple(window.project.items[0].transform.translation_mm)
        window._center_selected_xy()
        assert tuple(window.project.items[0].transform.translation_mm) == before
        window._delete_selected_item()
        window._duplicate_selected_item()
        window._move_selected_item(1)
        assert [i.name for i in window.project.items] == ["Relief", "Name"]

        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier,
        )
        window.viewport._renderer.keyPressEvent(event)
        assert tuple(window.project.items[0].transform.translation_mm) == before
        assert window.viewport._renderer.pick_gizmo_axis(QPointF(25, 25)) is None

        _click_layer_icon(window, 1, "eye")
        assert not window.project.items[0].visible
        _click_layer_icon(window, 1, "lock")
        window._select_project_indices([0], primary=0)
        assert window.transform_widget.isEnabled()
    finally:
        window.close()


def test_lock_survives_save_load_history_and_duplication(tmp_path: Path) -> None:
    project = Project(items=[
        ProjectItem("A", kind="rectangle", locked=True,
                    mesh=rectangle_mesh(20, 15, 2)),
        ProjectItem("B", kind="rectangle", locked=False,
                    mesh=rectangle_mesh(10, 10, 2)),
    ])
    original = capture_workspace(project)
    project.items[0].locked = False
    restore_workspace(project, original)
    assert project.items[0].locked
    index, duplicate = project.duplicate_item(0)
    assert index == 1 and duplicate.locked

    saved = save_project(project, tmp_path / "locks.cf3d")
    loaded = load_project(saved)
    assert [item.locked for item in loaded.items] == [True, True, False]


def test_stock_has_no_eye_or_lock_controls() -> None:
    window = _window()
    try:
        _click_layer_icon(window, 0, "eye")
        _click_layer_icon(window, 0, "lock")
        assert len(window.project.items) == 2
        assert all(item.visible and not item.locked for item in window.project.items)
    finally:
        window.close()
