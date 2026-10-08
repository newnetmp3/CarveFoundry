"""Atomic, read-only CF3D inventory adapter for replacing the Python UI."""
from __future__ import annotations

import json
from hashlib import sha256

import pytest

from carvefoundry.cam.operation import CamOperation
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.project_file import save_project
from carvefoundry.core.rust_cam_readout import cam_readout
from carvefoundry.core import rust_project_session as session
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.core.vector_path import VectorPath


def project_file(tmp_path):
    contour = VectorPath(
        ((0.0, 0.0), (20.0, 0.0), (20.0, 12.0), (0.0, 12.0)),
        closed=True,
    )
    vector = ProjectItem("Vector", kind="pen", vector_path=contour,
                         mesh=contour.mesh_asset())
    locked = ProjectItem("Locked vector", kind="pen", vector_path=contour,
                        mesh=contour.mesh_asset(), locked=True)
    mesh = ProjectItem("3D object", kind="mesh", mesh=contour.mesh_asset())
    cutter = Cutter("Test flat", ToolType.FLAT_END_MILL, 3.175)
    stage = CamOperation(
        "profile", cutter, source_item_ids=(vector.item_id,),
        parameters={"feed_mm_min": 600.0},
    )
    motion = Toolpath(
        name="Old generated path", operation="profile", cutter=cutter,
        safe_z_mm=5.0,
        moves=[ToolpathMove(0.0, 0.0, 5.0, MoveKind.RAPID)],
        source_item_id=vector.item_id, cam_operation_id=stage.operation_id,
    )
    fixture = Fixture("Fence", -4, 0, 0, 80, 4.0, clearance_mm=2.0)
    original = Project(items=[vector, locked, mesh],
                       cam_operations=[stage], toolpaths=[motion],
                       fixtures=[fixture], material_name="Maple")
    file = save_project(original, tmp_path / "job.cf3d")
    return file, original


def test_atomic_session_includes_same_digest_stock_fixture_and_cam(tmp_path):
    path, original = project_file(tmp_path)
    before = path.read_bytes()
    report = session.read_project_session(path)
    digest = sha256(before).hexdigest()
    assert path.read_bytes() == before
    assert report["source_sha256"] == digest
    assert report["layout"]["source_sha256"] == digest
    assert report["cam"]["source_sha256"] == digest
    assert report["layout"]["source_was_read_only"] is True
    assert report["layout"]["excluded_cam_and_fixtures"] is True
    assert report["preflight_verified"] is False
    assert report["export_allowed_from_rust"] is False
    assert report["stock"]["xy_zero"] == "bottom_left"
    assert report["stock"]["thickness_mm"] == original.stock.thickness_mm
    assert report["fixtures"][0]["top_z_mm"] == 4.0
    assert report["fixtures"][0]["clearance_mm"] == 2.0
    assert report["cam"]["operation_count"] == 1
    assert report["cam"]["generated_toolpath_count"] == 1
    assert report["cam"] == cam_readout(path)
    assert len(report["items"]) == 3
    assert {item["item_id"] for item in report["items"]} == {
        item.item_id for item in original.items
    }
    assert len(report["layout"]["parts"]) >= 1
    assert report["layout"]["skipped_items"] >= 1
    assert len(report["layout"]["parts"]) + report["layout"]["skipped_items"] == 3


def test_session_rejects_other_extensions_and_modified_source(tmp_path, monkeypatch):
    path, _ = project_file(tmp_path)
    with pytest.raises(ValueError, match="cf3d"):
        session.read_project_session(tmp_path / "job.txt")
    calls = 0
    real_sha = session._file_sha256

    def changing_sha(candidate):
        nonlocal calls
        calls += 1
        if calls >= 2:
            return "a" * 64
        return real_sha(candidate)

    monkeypatch.setattr(session, "_file_sha256", changing_sha)
    with pytest.raises(ValueError, match="changed"):
        session.read_project_session(path)
    assert path.is_file()


def test_session_cli_emits_coherent_inspection_without_motion(tmp_path, capsys):
    path, _ = project_file(tmp_path)
    assert session.main([str(path)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["session_version"] == 1
    assert data["cam"]["operations"][0]["motion_move_count"] == 1
    assert all("moves" not in op for op in data["cam"]["operations"])
    assert all("mesh_data" not in item for item in data["items"])
    assert session.main([str(tmp_path / "missing.cf3d")]) == 2
    assert "rejected" in capsys.readouterr().err


def test_session_rejects_duplicate_persistent_item_identity(tmp_path):
    path, original = project_file(tmp_path)
    original.items[1].item_id = original.items[0].item_id
    save_project(original, path)
    with pytest.raises(ValueError, match="UUID"):
        session.read_project_session(path)


def test_session_rejects_excessive_fixture_and_item_inventory(tmp_path, monkeypatch):
    path, _ = project_file(tmp_path)
    monkeypatch.setattr(session, "MAX_FIXTURES", 0)
    with pytest.raises(ValueError, match="inventory limits"):
        session.read_project_session(path)
