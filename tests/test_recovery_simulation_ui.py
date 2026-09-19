"""Live project recovery and sampled stock preview UI regressions."""
from __future__ import annotations

from time import monotonic, sleep
from uuid import uuid4

import pytest
from PySide6.QtWidgets import QApplication

from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.project_file import load_project, save_project
from carvefoundry.core.recovery import list_recoveries, save_recovery
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.ui.project_window import MainWindow

_APP = QApplication.instance() or QApplication([])


def _finish(window, timeout=45.0):
    deadline = monotonic() + timeout
    while window._background_job is not None and monotonic() < deadline:
        _APP.processEvents()
        sleep(0.01)
    _APP.processEvents()
    assert window._background_job is None


def _scene():
    flat = Cutter("flat", ToolType.FLAT_END_MILL, 4)
    return Project(
        name="Demo",
        stock=Stock(24, 24, 9),
        items=[ProjectItem(
            "Relief", kind="rectangle", mesh=rectangle_mesh(9, 9, 2),
        )],
        toolpaths=[Toolpath(
            "Pocket", "pocket", flat, 5.0,
            [
                ToolpathMove(10, 10, 5, MoveKind.RAPID),
                ToolpathMove(10, 10, -1, MoveKind.PLUNGE, 100),
                ToolpathMove(15, 10, -1, MoveKind.CUT, 300),
            ],
        )],
    )


def test_stock_simulation_menu_and_background_image(tmp_path, monkeypatch):
    monkeypatch.setenv("CARVEFOUNDRY_RECOVERY_DIR", str(tmp_path / "recovery"))
    window = MainWindow()
    try:
        window._set_project(_scene(), project_path=None)
        assert window._ui_actions["stock_simulation"].text() == (
            "Simulate Material Removal…"
        )
        assert window._run_stock_removal(spacing_mm=1.0)
        _finish(window)
        assert window._stock_removal_dialog.isVisible()
        window._stock_removal_dialog.close()
    finally:
        window.close()


def test_recovery_menu_manual_checkpoint_and_clean_save(tmp_path, monkeypatch):
    monkeypatch.setenv("CARVEFOUNDRY_RECOVERY_DIR", str(tmp_path / "recover"))
    window = MainWindow()
    try:
        window._set_project(_scene(), project_path=None)
        assert window._ui_actions["recover"].text() == "Recover Autosave…"
        window._mark_project_dirty()
        assert window._project_dirty
        assert window._manual_recovery_checkpoint()
        _finish(window)
        entries = list_recoveries(tmp_path / "recover")
        assert len(entries) == 1
        assert entries[0].name == "Demo"
        assert entries[0].original_path is None
        assert window._project_dirty
        target = tmp_path / "saved.cf3d"
        assert window._save_project_to(target)
        _finish(window)
        assert load_project(target).name == "Demo"
        assert not list_recoveries(tmp_path / "recover")
        assert not window._project_dirty
    finally:
        window.close()


def test_restore_checkpoint_marks_unsaved_without_overwriting_original(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("CARVEFOUNDRY_RECOVERY_DIR", str(tmp_path / "recover"))
    original = save_project(Project(name="Saved"), tmp_path / "original.cf3d")
    baseline = original.read_bytes()
    checkpoint = save_recovery(
        _scene(), tmp_path / "recover", key=uuid4().hex,
        state_id=7, original_path=original,
    )
    window = MainWindow()
    try:
        assert window._restore_checkpoint(checkpoint)
        _finish(window)
        assert window.project.name == "Demo"
        assert window.project_path == original
        assert window._project_dirty
        assert window._recovery_key == checkpoint.key
        assert original.read_bytes() == baseline
        assert list_recoveries(tmp_path / "recover")
        # Explicit normal Save is the only operation overwriting original.
        assert window._save_project()
        _finish(window)
        assert load_project(original).name == "Demo"
        assert not list_recoveries(tmp_path / "recover")
    finally:
        window.close()


def test_recovery_toggle_stops_auto_timer_but_allows_manual_snapshot(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("CARVEFOUNDRY_RECOVERY_DIR", str(tmp_path / "recover"))
    window = MainWindow()
    original = window._settings.value("recovery/enabled", "true")
    try:
        window._set_project(_scene(), project_path=None)
        window._mark_project_dirty()
        window._set_recovery_enabled(False)
        assert not window._recovery_timer.isActive()
        assert window._manual_recovery_checkpoint()
        _finish(window)
        assert len(list_recoveries(tmp_path / "recover")) == 1
    finally:
        window._settings.setValue("recovery/enabled", original)
        window._settings.sync()
        window.close()
