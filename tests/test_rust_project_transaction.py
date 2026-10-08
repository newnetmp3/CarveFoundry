"""Safe native CF3D placement transactions preserve intent but invalidate motion."""
from __future__ import annotations

import json
from hashlib import sha256

import pytest

from carvefoundry.cam.operation import CamOperation
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.project_file import load_project, save_project
from carvefoundry.core.rust_project_transaction import (
    PROTOCOL_VERSION,
    STALE_REASON,
    ProjectTransactionError,
    apply_transaction,
    inspect_project,
    main,
)
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.core.vector_path import VectorPath


def sample_project(tmp_path):
    path = VectorPath(
        ((0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)),
        closed=True,
    )
    item = ProjectItem(
        "Retained plaque", kind="pen", mesh=path.mesh_asset(),
        vector_path=path,
    )
    other = ProjectItem("locked vector", kind="pen", mesh=path.mesh_asset(),
                        vector_path=path, locked=True)
    cutter = Cutter("Flat", ToolType.FLAT, 3.175)
    operation = CamOperation(
        "profile", cutter, source_item_ids=(item.item_id,),
        parameters={"feed_mm_min": 600.0},
    )
    toolpath = Toolpath(
        name="Unsafe old path", operation="profile", cutter=cutter, safe_z_mm=5.0,
        moves=[ToolpathMove(0.0, 0.0, 5.0, MoveKind.RAPID)],
        source_item_id=item.item_id, cam_operation_id=operation.operation_id,
    )
    fixture = Fixture(
        "left fence", x_min_mm=0, y_min_mm=0,
        x_max_mm=4, y_max_mm=100,
        top_z_mm=23, clearance_mm=2,
    )
    project = Project(
        items=[item, other], toolpaths=[toolpath],
        cam_operations=[operation], fixtures=[fixture],
    )
    file = save_project(project, tmp_path / "existing.cf3d")
    return file, item.item_id, other.item_id, project


def request_for(source, item_id, *, dx=4.0, dy=-3.0):
    return {
        "protocol_version": PROTOCOL_VERSION,
        "source_sha256": sha256(source.read_bytes()).hexdigest(),
        "edits": [{"item_id": item_id, "delta_x_mm": dx, "delta_y_mm": dy}],
    }


def test_transaction_creates_new_file_and_invalidates_all_machine_motion(tmp_path):
    original, item_id, _locked_id, before_project = sample_project(tmp_path)
    original_bytes = original.read_bytes()
    audit = inspect_project(original)
    assert audit["source_sha256"] == sha256(original_bytes).hexdigest()
    assert [item["item_id"] for item in audit["editable_items"]] == [item_id]
    assert audit["toolpaths"] == audit["cam_operations"] == audit["fixtures"] == 1
    destination = tmp_path / "repositioned.cf3d"
    result = apply_transaction(original, destination, request_for(original, item_id))
    assert original.read_bytes() == original_bytes
    assert result["removed_generated_toolpaths"] == 1
    assert result["stale_cam_operations"] == 1
    assert result["requires_cam_regeneration_and_preflight"] is True
    updated = load_project(destination)
    assert updated.items[0].item_id == item_id
    assert updated.items[0].transform.translation_mm == (4.0, -3.0, 0.0)
    assert updated.items[0].vector_path == before_project.items[0].vector_path
    assert updated.items[0].mesh is not None
    assert updated.items[1].locked
    assert updated.items[1].transform.translation_mm == (0.0, 0.0, 0.0)
    assert updated.stock == before_project.stock
    assert updated.fixtures == before_project.fixtures
    assert not updated.toolpaths
    assert len(updated.cam_operations) == 1
    assert updated.cam_operations[0].operation_id == before_project.cam_operations[0].operation_id
    assert updated.cam_operations[0].source_item_ids == (item_id,)
    assert updated.cam_operations[0].parameters == {"feed_mm_min": 600.0}
    assert updated.cam_operations[0].stale_reason == STALE_REASON


def test_transaction_rejects_stale_hash_and_does_not_write(tmp_path):
    source, item_id, _, _ = sample_project(tmp_path)
    request = request_for(source, item_id)
    request["source_sha256"] = "0" * 64
    output = tmp_path / "should-not-exist.cf3d"
    with pytest.raises(ProjectTransactionError, match="changed"):
        apply_transaction(source, output, request)
    assert not output.exists()


def test_reject_existing_destination_and_original_overwrite(tmp_path):
    source, item_id, _, _ = sample_project(tmp_path)
    req = request_for(source, item_id)
    with pytest.raises(ProjectTransactionError, match="original"):
        apply_transaction(source, source, req)
    existing = tmp_path / "existing-output.cf3d"
    existing.write_bytes(b"leave me alone")
    with pytest.raises(ProjectTransactionError, match="exists"):
        apply_transaction(source, existing, req)
    assert existing.read_bytes() == b"leave me alone"


def test_unknown_and_locked_item_reject_entire_batch(tmp_path):
    source, item_id, locked, _ = sample_project(tmp_path)
    output = tmp_path / "rejected.cf3d"
    for bad_id in ("missing-uuid", locked):
        req = request_for(source, item_id)
        req["edits"].append(
            {"item_id": bad_id, "delta_x_mm": 2.0, "delta_y_mm": 0.0}
        )
        with pytest.raises(ProjectTransactionError):
            apply_transaction(source, output, req)
        assert not output.exists()


@pytest.mark.parametrize(
    "dx,dy",
    [(float("nan"), 0), (float("inf"), 0), (True, 1),
     (0, False), (0, 0), (1_000_001, 0)],
)
def test_reject_invalid_offsets_before_any_disk_output(tmp_path, dx, dy):
    source, item_id, _, _ = sample_project(tmp_path)
    output = tmp_path / "invalid.cf3d"
    with pytest.raises(ProjectTransactionError):
        apply_transaction(source, output, request_for(source, item_id, dx=dx, dy=dy))
    assert not output.exists()


def test_unknown_edit_fields_and_duplicate_uuid_are_rejected(tmp_path):
    source, item_id, _, _ = sample_project(tmp_path)
    output = tmp_path / "invalid.cf3d"
    req = request_for(source, item_id)
    req["edits"][0]["z_mm"] = -10.0
    with pytest.raises(ProjectTransactionError, match="fields"):
        apply_transaction(source, output, req)
    req = request_for(source, item_id)
    req["edits"].append(dict(req["edits"][0]))
    with pytest.raises(ProjectTransactionError, match="unique"):
        apply_transaction(source, output, req)


def test_existing_cnc_paths_are_cleared_even_when_no_cam_operation_exists(tmp_path):
    source, item_id, _, project = sample_project(tmp_path)
    project.cam_operations = []
    save_project(project, source)
    output = tmp_path / "no-operation.cf3d"
    result = apply_transaction(source, output, request_for(source, item_id))
    assert result["removed_generated_toolpaths"] == 1
    assert load_project(output).toolpaths == []


def test_cli_inspect_emits_machine_readable_stable_ids(tmp_path, capsys):
    source, item_id, _, _ = sample_project(tmp_path)
    assert main(["inspect", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["protocol_version"] == 1
    assert report["editable_items"][0]["item_id"] == item_id
    assert main(["inspect", str(source), str(tmp_path / "bad.cf3d")]) == 2
