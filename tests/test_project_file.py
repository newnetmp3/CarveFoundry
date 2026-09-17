import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from carvefoundry.core.mesh import load_stl
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.project_file import (
    PROJECT_FILE_VERSION,
    ProjectFileError,
    load_project,
    save_project,
)
from carvefoundry.core.transform import Transform3D


def test_project_round_trip_reloads_stl_and_transform(tmp_path: Path) -> None:
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
    project_path = tmp_path / "fixture.carvefoundry"

    saved_path = save_project(project, project_path)
    loaded = load_project(saved_path)

    assert loaded.name == "Fixture"
    assert loaded.stock == project.stock
    assert len(loaded.items) == 1
    loaded_item = loaded.items[0]
    assert loaded_item.source_path == mesh_path.resolve()
    assert loaded_item.mesh is not None
    assert np.allclose(loaded_item.mesh.dimensions, (10.0, 20.0, 5.0))
    assert loaded_item.transform.translation_mm == transform.translation_mm
    assert loaded_item.transform.rotation_deg == transform.rotation_deg
    assert loaded_item.transform.scale_xyz == transform.scale_xyz


def test_saved_project_uses_current_version_and_relative_source_path(tmp_path: Path) -> None:
    mesh_path = tmp_path / "assets" / "part.stl"
    mesh_path.parent.mkdir()
    trimesh.creation.box().export(mesh_path)
    project = Project(
        items=[ProjectItem("part.stl", mesh_path, "stl", mesh=load_stl(mesh_path))]
    )
    project_path = tmp_path / "job.carvefoundry"

    save_project(project, project_path)
    payload = json.loads(project_path.read_text(encoding="utf-8"))

    assert payload["version"] == PROJECT_FILE_VERSION
    assert payload["items"][0]["source_path"] == "assets/part.stl"


def test_save_adds_project_suffix(tmp_path: Path) -> None:
    saved = save_project(Project(), tmp_path / "untitled")

    assert saved.name == "untitled.carvefoundry"
    assert saved.is_file()


def test_missing_stl_is_reported_when_loading(tmp_path: Path) -> None:
    payload = {
        "version": PROJECT_FILE_VERSION,
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
    path = tmp_path / "missing.carvefoundry"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectFileError, match="missing"):
        load_project(path)


def test_invalid_project_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future.carvefoundry"
    path.write_text(
        json.dumps({"version": 999, "name": "Future", "stock": {}, "items": []}),
        encoding="utf-8",
    )

    with pytest.raises(ProjectFileError, match="Unsupported project version"):
        load_project(path)
