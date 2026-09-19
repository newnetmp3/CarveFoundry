"""Maintenance regressions for modularized UI and shared design-item cloning."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")

from PySide6.QtWidgets import QApplication

from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.project_file import load_project, save_project
from carvefoundry.ui.project_window import MainWindow

_APP = QApplication.instance() or QApplication([])


def test_copy_and_paste_preserve_independent_smart_value_bindings(
    tmp_path: Path,
) -> None:
    original = ProjectItem(
        name="Parametric rectangle",
        kind="rectangle",
        mesh=rectangle_mesh(12, 8, 1),
        smart_bindings={"position_x": "width / 2", "size_y": "height"},
    )
    window = MainWindow()
    try:
        window._set_project(Project(items=[original]), project_path=None)
        window._select_project_indices([0])
        window._copy_selected_items()

        assert window._clipboard_items[0].smart_bindings == original.smart_bindings
        assert window._clipboard_items[0].smart_bindings is not original.smart_bindings

        window._paste_items()
        assert len(window.project.items) == 2
        pasted = window.project.items[-1]
        assert pasted.smart_bindings == original.smart_bindings
        assert pasted.smart_bindings is not original.smart_bindings
        assert pasted.item_id != original.item_id

        saved = save_project(window.project, tmp_path / "binding-clones.cf3d")
        loaded = load_project(saved)
        assert loaded.items[-1].smart_bindings == original.smart_bindings

        pasted.smart_bindings["position_x"] = "123"
        assert original.smart_bindings["position_x"] == "width / 2"

        window._undo()
        assert len(window.project.items) == 1
        assert window.project.items[0].smart_bindings == original.smart_bindings
    finally:
        window.close()
