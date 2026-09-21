"""Real beginner project, simple CAM and operator-document regressions."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QPlainTextEdit

from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.beginner import (
    MATERIAL_STARTERS,
    design_advisories,
    explain_motion_preflight,
    material_starting_values,
    starter_project,
)
from carvefoundry.core.history import capture_workspace, restore_workspace
from carvefoundry.core.job_sheet import job_sheet_html
from carvefoundry.core.machine_profiles import MachineProfile
from carvefoundry.core.project_file import load_project, save_project
from carvefoundry.core.tools import DEFAULT_TOOLS
from carvefoundry.ui.main_window import MainWindow

_APP = QApplication.instance() or QApplication([])


def test_first_nameplate_is_editable_cnc_geometry_with_stock_top_z0() -> None:
    project = starter_project()
    assert project.name == "First Nameplate"
    assert project.stock.width_mm == pytest.approx(203.2)
    assert project.stock.height_mm == pytest.approx(101.6)
    assert project.stock.thickness_mm == pytest.approx(19.05)
    assert len(project.items) == 1
    item = project.items[0]
    assert item.text_properties is not None
    assert item.text_properties.content == "MY FIRST CARVE"
    assert item.mesh is not None and item.mesh.mesh.is_watertight
    bounds = item.transformed_bounds_mm()
    assert bounds is not None
    assert bounds[1, 2] == pytest.approx(0.0)
    assert 0 < bounds[0, 0] < bounds[1, 0] < project.stock.width_mm
    assert 0 < bounds[0, 1] < bounds[1, 1] < project.stock.height_mm
    assert not project.toolpaths


def test_other_starter_and_bad_name_or_type() -> None:
    coaster = starter_project("coaster")
    assert coaster.items[0].kind == "ellipse"
    assert coaster.items[0].mesh is not None
    with pytest.raises(ValueError, match="cannot be empty"):
        starter_project(text="  ")
    with pytest.raises(ValueError, match="Unknown"):
        starter_project("unknown")


def test_material_values_are_examples_and_never_change_cutter_geometry() -> None:
    cutter = DEFAULT_TOOLS[0]
    values = material_starting_values(MATERIAL_STARTERS[1], cutter)
    assert values == (550.0, 160.0, pytest.approx(1.5875))
    assert cutter.diameter_mm == 6.35


def test_quality_advisories_cannot_claim_preflight_pass() -> None:
    project = starter_project()
    findings = design_advisories(project, DEFAULT_TOOLS[0])
    messages = "\n".join(message for _kind, message in findings)
    assert "clamps/fences" in messages
    assert "Generate" in messages
    assert "letter strokes" in messages
    stale = design_advisories(
        project, DEFAULT_TOOLS[0], stale_reason="Geometry changed",
    )
    assert any("regenerate" in message for _kind, message in stale)


def test_job_sheet_includes_real_cutter_order_and_only_real_export_names() -> None:
    project = starter_project()
    bit1, bit2 = DEFAULT_TOOLS[:2]
    for bit in (bit1, bit2):
        project.toolpaths.append(Toolpath(
            name="Example", operation="finish", cutter=bit, safe_z_mm=5.0,
            moves=[
                ToolpathMove(30, 30, 5, MoveKind.RAPID),
                ToolpathMove(30, 30, -1, MoveKind.PLUNGE, 150),
                ToolpathMove(50, 30, -1, MoveKind.CUT, 500),
            ],
        ))
    machine = MachineProfile()
    pending = job_sheet_html(project, machine)
    assert "Not exported yet" in pending
    assert "stock TOP" in pending
    assert "re-probe" in pending
    assert "☐" in pending
    complete = job_sheet_html(
        project, machine,
        output_files=("/tmp/rough.nc", "/tmp/finish.nc"),
    )
    assert "rough.nc" in complete
    assert "finish.nc" in complete
    assert "/tmp/rough.nc" not in complete
    incomplete = job_sheet_html(project, machine, output_files=("rough.nc",))
    assert "Not exported yet" in incomplete
    assert "rough.nc" not in incomplete
    with pytest.raises(ValueError, match="Generate toolpaths"):
        job_sheet_html(starter_project(), machine)


def test_welcome_and_simple_cam_use_existing_project_and_cam_widgets() -> None:
    window = MainWindow()
    old_mode = window._settings.value("cam/simple_mode", None)
    try:
        window._settings.setValue("cam/simple_mode", True)
        window._show_welcome()
        assert window._beginner_welcome_dialog.objectName() == "BeginnerWelcome"
        window._beginner_welcome_dialog.close()

        # Avoid opening the companion guide in this ownership test.
        window._show_guided_workflow = lambda: None
        window._create_starter_project("nameplate")
        assert window.project.items[0].kind == "text"
        assert window.project_path is None

        dialog = window._build_toolpath_generation_dialog()
        fields = dialog.generation_fields
        assert fields["mode"].currentText() == "Simple"
        assert fields["simple_operation"].objectName() == "SimpleCamOperation"
        assert (
            fields["simple_operation_preview"].objectName()
            == "CamOperationIllustration"
        )
        assert "surface" in fields["simple_operation_help"].text().lower()
        assert not fields["simple_depth"].isHidden()
        fields["simple_depth"].setValue(2.5)
        assert fields["cut_depth"].value() == pytest.approx(2.5)
        fields["simple_detail"].setValue(80)
        assert fields["detail"].value() == 80
        fields["simple_operation"].setCurrentIndex(
            fields["simple_operation"].findData("pocket")
        )
        assert fields["operation"].currentData() == "pocket"
        assert "inside" in fields["simple_operation_help"].text().lower()
        old_feed = fields["feed"].value()
        fields["simple_material"].setCurrentIndex(1)
        assert fields["feed"].value() == old_feed
        fields["simple_apply_material"].click()
        assert fields["feed"].value() == pytest.approx(550.0)
        fields["mode"].setCurrentText("Advanced")
        assert fields["mode"].currentText() == "Advanced"
        assert fields["simple_depth"].value() == pytest.approx(2.5)
        fields["operation"].setCurrentIndex(
            fields["operation"].findData("waterline")
        )
        fields["mode"].setCurrentText("Simple")
        assert fields["mode"].currentText() == "Advanced"
        dialog.close()
    finally:
        if old_mode is None:
            window._settings.remove("cam/simple_mode")
        else:
            window._settings.setValue("cam/simple_mode", old_mode)
        window.close()


def test_job_setup_sheet_saves_real_pdf(tmp_path: Path, monkeypatch) -> None:
    window = MainWindow()
    try:
        project = starter_project()
        cutter = DEFAULT_TOOLS[0]
        project.toolpaths.append(Toolpath(
            name="First pass", operation="engrave",
            cutter=cutter, safe_z_mm=4.0,
            moves=[
                ToolpathMove(30, 30, 4, MoveKind.RAPID),
                ToolpathMove(30, 30, -1, MoveKind.PLUNGE, 120),
                ToolpathMove(55, 30, -1, MoveKind.CUT, 600),
            ],
        ))
        window._set_project(project, project_path=None, selected_row=1)
        target = tmp_path / "first_setup.pdf"
        monkeypatch.setattr(
            QFileDialog, "getSaveFileName",
            lambda *_args, **_kwargs: (str(target), "PDF document (*.pdf)"),
        )
        window._export_setup_sheet()
        assert target.is_file()
        data = target.read_bytes()
        assert data.startswith(b"%PDF-")
        assert len(data) > 1000
    finally:
        window.close()


def test_project_material_and_notes_survive_cf3d_and_undo(tmp_path: Path) -> None:
    project = starter_project("coaster")
    project.material_name = "Hardwood"
    project.notes = "Maple: inspect cut quality & use a test scrap. <no auto-RPM>"
    before = capture_workspace(project)
    project.notes = "Changed"
    project.material_name = "Plywood"
    restore_workspace(project, before)
    assert project.material_name == "Hardwood"
    assert "Maple:" in project.notes
    target = tmp_path / "coaster.cf3d"
    save_project(project, target)
    restored = load_project(target)
    assert restored.material_name == project.material_name
    assert restored.notes == project.notes
    sheet = job_sheet_html(
        project_with_demo_path(project), MachineProfile()
    )
    assert "Hardwood" in sheet
    assert "&lt;no auto-RPM&gt;" in sheet


def project_with_demo_path(project):
    cutter = DEFAULT_TOOLS[0]
    project.toolpaths.append(Toolpath(
        name="Demo", operation="engrave", cutter=cutter, safe_z_mm=5,
        moves=[
            ToolpathMove(30, 30, 5, MoveKind.RAPID),
            ToolpathMove(30, 30, -1, MoveKind.PLUNGE, 100),
        ],
    ))
    return project


def test_notes_edit_does_not_invalidate_existing_cam(monkeypatch) -> None:
    window = MainWindow()
    try:
        window._set_project(
            project_with_demo_path(starter_project("coaster")),
            project_path=None,
        )
        initial_paths = list(window.project.toolpaths)

        def edit_and_accept(dialog):
            entry = dialog.findChild(QPlainTextEdit, "ProjectNotesText")
            assert entry is not None
            entry.setPlainText("Test notes for maple")
            return QDialog.DialogCode.Accepted

        monkeypatch.setattr(QDialog, "exec", edit_and_accept)
        window._show_project_notes()
        assert window.project.notes == "Test notes for maple"
        assert window.project.toolpaths == initial_paths
    finally:
        window.close()


def test_plain_english_preflight_distinguishes_posted_nc_and_physical_checks() -> None:
    report = (
        "Cutter stage 1:\nPreflight BLOCKED — 12 moves\n"
        "ERROR: Stock width exceeds machine travel.\n"
        "WARNING: No fixtures recorded.\n"
    )
    text = explain_motion_preflight(report, False)
    assert "1 error(s), 1 warning(s)" in text
    assert "Stock width exceeds" in text
    assert "posted G-code" in text
    assert "physical clamps" in text
