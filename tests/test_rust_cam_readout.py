"""Regression coverage for the read-only native CAM status adapter."""
from __future__ import annotations

from pathlib import Path

from carvefoundry.cam.operation import CamOperation
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.project import Project
from carvefoundry.core.project_file import save_project
from carvefoundry.core.rust_cam_readout import cam_readout, main
from carvefoundry.core.tools import DEFAULT_TOOLS


def test_cam_readout_includes_stale_missing_disabled_and_nonverified_motion(
    tmp_path: Path,
) -> None:
    cutter = DEFAULT_TOOLS[0]
    stale = CamOperation("Profile", cutter, stale_reason="Source geometry changed")
    disabled = CamOperation("Pocket", cutter, enabled=False)
    missing = CamOperation("Engrave", cutter)
    present = CamOperation("Profile", cutter)
    move = ToolpathMove(1.0, 1.0, 5.0, MoveKind.RAPID)
    toolpath = Toolpath(
        "Retained motion", "Profile", cutter, safe_z_mm=5.0,
        cam_operation_id=present.operation_id, moves=[move],
    )
    project = Project(
        name="CAM-readout", cam_operations=[stale, missing, disabled, present],
        toolpaths=[toolpath],
    )
    source = tmp_path / "job.cf3d"
    save_project(project, source)
    original_bytes = source.read_bytes()
    data = cam_readout(source)
    assert data["operation_count"] == 4
    assert data["counts"] == {
        "disabled": 1, "stale": 1, "missing_motion": 1,
        "motion_present_unverified": 1,
    }
    assert [op["state"] for op in data["operations"]] == [
        "stale", "missing_motion", "disabled", "motion_present_unverified",
    ]
    assert data["operations"][0]["stale_reason"] == "Source geometry changed"
    assert data["operations"][3]["motion_move_count"] == 1
    assert data["operations"][3]["cutter_type"] == "flat_end_mill"
    assert data["export_allowed_from_rust"] is False
    assert data["preflight_verified"] is False
    assert source.read_bytes() == original_bytes


def test_new_cf3d_placement_invalidates_readout_motion(tmp_path: Path):
    operation = CamOperation("Pocket", DEFAULT_TOOLS[0], stale_reason="External placement edit")
    source = tmp_path / "changed.cf3d"
    save_project(Project(cam_operations=[operation]), source)
    data = cam_readout(source)
    assert data["counts"]["stale"] == 1
    assert data["generated_toolpath_count"] == 0
    assert data["operations"][0]["source_item_count"] == 0


def test_readout_cli_refuses_non_cf3d(tmp_path: Path, capsys):
    bad = tmp_path / "wrong.json"
    bad.write_text("{}")
    assert main([str(bad)]) == 2
    assert "native .cf3d" in capsys.readouterr().err


def test_empty_project_is_not_a_preflight_certificate(tmp_path: Path):
    source = tmp_path / "empty.cf3d"
    save_project(Project(), source)
    data = cam_readout(source)
    assert data["operation_count"] == 0
    assert not data["export_allowed_from_rust"]
    assert not data["preflight_verified"]
