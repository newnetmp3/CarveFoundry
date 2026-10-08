"""Loss-aware, non-mutating CF3D-to-Rust layout snapshot tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.project_file import load_project, save_project
from carvefoundry.core.rust_layout_snapshot import main, project_to_layout_snapshot
from carvefoundry.core.vector_path import VectorPath, VectorSegment


def _vector_item(name: str, *, closed: bool = True) -> ProjectItem:
    path = VectorPath(
        ((0, 0), (20, 0), (20, 10), (0, 10)), closed=closed,
    )
    return ProjectItem(name, kind="pen", mesh=path.mesh_asset(), vector_path=path)


def test_snapshot_keeps_stock_and_contour_but_does_not_modify_source():
    kept = _vector_item("Panel")
    skipped = _vector_item("Open line", closed=False)
    project = Project(name="Shop", stock=Stock(120, 80, 18), items=[kept, skipped])
    before = kept.vector_path
    output = project_to_layout_snapshot(project)
    assert output["format_version"] == 1
    assert output["width_mm"] == pytest.approx(120)
    assert output["height_mm"] == pytest.approx(80)
    assert output["source_was_read_only"]
    assert output["excluded_cam_and_fixtures"]
    assert output["skipped_items"] == 1
    assert len(output["parts"]) == 1
    item = output["parts"][0]
    assert item["name"] == "Panel"
    assert item["source_item_id"] == kept.item_id
    assert item["x"] == pytest.approx(0)
    assert item["y"] == pytest.approx(0)
    assert len(item["outline"]) >= 4
    assert kept.vector_path is before
    assert len(project.items) == 2


def test_snapshot_handles_arc_sampling_without_mutating_analytic_curve():
    path = VectorPath(
        ((0, 0), (10, 0), (10, 10)),
        closed=True,
        segments=(VectorSegment.arc(45), VectorSegment.line(), VectorSegment.line()),
    )
    item = ProjectItem("Arc", kind="pen", mesh=path.mesh_asset(), vector_path=path)
    data = project_to_layout_snapshot(Project(items=[item]))
    assert len(data["parts"]) == 1
    assert len(data["parts"][0]["outline"]) > 3
    assert item.vector_path == path


def test_cf3d_source_roundtrip_remains_identical_when_snapshot_used(tmp_path: Path, capsys):
    original = Project(items=[_vector_item("Original")])
    path = tmp_path / "source.cf3d"
    save_project(original, path)
    prior = path.read_bytes()
    assert main([str(path)]) == 0
    from hashlib import sha256

    payload = json.loads(capsys.readouterr().out)
    assert payload["source_sha256"] == sha256(prior).hexdigest()
    assert payload["parts"][0]["source_item_id"] == original.items[0].item_id
    assert path.read_bytes() == prior
    assert load_project(path).items[0].name == "Original"


def test_snapshot_cli_rejects_unknown_extension(tmp_path: Path, capsys):
    wrong = tmp_path / "fake.json"
    wrong.write_text(json.dumps({}), encoding="utf-8")
    assert main([str(wrong)]) == 2
    assert "CF3D" in capsys.readouterr().err


def test_non_bottom_left_origin_is_rejected():
    project = Project(items=[_vector_item("Part")])
    project.stock.xy_zero = "center"
    with pytest.raises(ValueError, match="bottom-left"):
        project_to_layout_snapshot(project)
