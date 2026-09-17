import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from carvefoundry.core.mesh import load_stl
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.project_file import (
    LEGACY_PROJECT_FILE_VERSION,
    PROJECT_FILE_MAGIC,
    PROJECT_FILE_VERSION,
    ProjectFileError,
    load_project,
    project_to_dict,
    save_project,
)
from carvefoundry.core.transform import Transform3D


def test_project_round_trip_embeds_stl_and_transform(tmp_path: Path) -> None:
    mesh_path = tmp_path / "part.stl"
    trimesh.creation.box(extents=(10.0, 20.0, 5.0)).export(mesh_path)
    asset = load_stl(mesh_path)
    transform = Transform3D(
        translation_mm=(50.0, 40.0, -2.5),
        rotation_deg=(0.0, 0.0, 90.0),
        scale_xyz=(1.25, 1.25, 1.25),
    )
    project = Project(
        name="Fixture",
        stock=Stock(width_mm=150.0, height_mm=100.0, thickness_mm=18.0),
        items=[
            ProjectItem(
                "part.stl",
                mesh_path,
                "stl",
                mesh=asset,
                transform=transform,
            )
        ],
    )
    project_path = tmp_path / "fixture.cf3d"

    saved_path = save_project(project, project_path)
    mesh_path.unlink()
    loaded = load_project(saved_path)

    assert loaded.name == "Fixture"
    assert loaded.stock == project.stock
    assert len(loaded.items) == 1
    loaded_item = loaded.items[0]
    assert loaded_item.source_path is not None
    assert loaded_item.source_path.is_file()
    assert loaded_item.source_path.name == "part.stl"
    assert loaded_item.source_path != mesh_path.resolve()
    assert loaded_item.mesh is not None
    assert np.allclose(loaded_item.mesh.dimensions, (10.0, 20.0, 5.0))
    assert loaded_item.transform.translation_mm == transform.translation_mm
    assert loaded_item.transform.rotation_deg == transform.rotation_deg
    assert loaded_item.transform.scale_xyz == transform.scale_xyz


def test_saved_project_is_native_container_with_current_manifest(tmp_path: Path) -> None:
    mesh_path = tmp_path / "part.stl"
    trimesh.creation.box().export(mesh_path)
    project = Project(
        items=[ProjectItem("part.stl", mesh_path, "stl", mesh=load_stl(mesh_path))]
    )
    project_path = tmp_path / "job.cf3d"

    save_project(project, project_path)
    manifest = project_to_dict(project, project_path)

    assert project_path.read_bytes().startswith(PROJECT_FILE_MAGIC)
    assert manifest["version"] == PROJECT_FILE_VERSION
    assert manifest["format"] == "CarveFoundry Project"
    assert len(manifest["assets"]) == 1
    assert manifest["items"][0]["asset_id"] in manifest["assets"]


def test_duplicate_source_assets_are_stored_once(tmp_path: Path) -> None:
    mesh_path = tmp_path / "shared.stl"
    trimesh.creation.box(extents=(4.0, 5.0, 6.0)).export(mesh_path)
    mesh = load_stl(mesh_path)
    project = Project(
        items=[
            ProjectItem("first.stl", mesh_path, "stl", mesh=mesh),
            ProjectItem("second.stl", mesh_path, "stl", mesh=mesh),
        ]
    )

    manifest = project_to_dict(project, tmp_path / "dedup.cf3d")

    assert len(manifest["assets"]) == 1
    assert manifest["items"][0]["asset_id"] == manifest["items"][1]["asset_id"]


def test_repetitive_asset_is_compressed_and_portable(tmp_path: Path) -> None:
    svg_path = tmp_path / "large.svg"
    source_bytes = (
        b"<svg xmlns='http://www.w3.org/2000/svg'>"
        + b"<path d='M0 0 L10 10 L20 0 Z'/>" * 30000
        + b"</svg>"
    )
    svg_path.write_bytes(source_bytes)
    project = Project(items=[ProjectItem("large.svg", svg_path, "svg")])
    project_path = tmp_path / "compressed.cf3d"

    save_project(project, project_path)

    assert project_path.stat().st_size < len(source_bytes) // 10

    svg_path.unlink()
    loaded = load_project(project_path)
    loaded_path = loaded.items[0].source_path

    assert loaded_path is not None
    assert loaded_path.read_bytes() == source_bytes


def test_save_adds_project_suffix(tmp_path: Path) -> None:
    saved = save_project(Project(), tmp_path / "untitled")

    assert saved.name == "untitled.cf3d"
    assert saved.is_file()
    assert saved.read_bytes().startswith(PROJECT_FILE_MAGIC)


def test_legacy_missing_stl_is_reported_when_loading(tmp_path: Path) -> None:
    payload = {
        "version": LEGACY_PROJECT_FILE_VERSION,
        "name": "Missing",
        "stock": {"width_mm": 100, "height_mm": 80, "thickness_mm": 18},
        "items": [
            {
                "name": "gone.stl",
                "source_path": "gone.stl",
                "kind": "stl",
                "visible": True,
                "transform": {
                    "translation_mm": [0, 0, 0],
                    "rotation_deg": [0, 0, 0],
                    "scale_xyz": [1, 1, 1],
                },
            }
        ],
    }
    path = tmp_path / "missing.cf3d"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectFileError, match="missing"):
        load_project(path)


def test_invalid_legacy_project_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future.cf3d"
    path.write_text(
        json.dumps({"version": 999, "name": "Future", "stock": {}, "items": []}),
        encoding="utf-8",
    )

    with pytest.raises(ProjectFileError, match="Unsupported project version"):
        load_project(path)
