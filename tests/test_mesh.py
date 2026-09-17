from pathlib import Path

import numpy as np
import pytest
import trimesh

from carvefoundry.core.mesh import (
    MeshImportError,
    load_stl,
    mesh_asset_from_geometry,
)


def test_load_generated_stl_preserves_mesh_and_metadata(tmp_path: Path) -> None:
    generated = trimesh.creation.box(extents=(10.0, 20.0, 5.0))
    path = tmp_path / "box.stl"
    generated.export(path)

    asset = load_stl(path)

    assert asset.source_path == path
    assert asset.source_was_scene is False
    assert np.allclose(asset.dimensions, (10.0, 20.0, 5.0))
    assert np.allclose(asset.bounds[0], (-5.0, -10.0, -2.5))
    assert np.allclose(asset.bounds[1], (5.0, 10.0, 2.5))
    assert asset.vertex_count == len(asset.mesh.vertices)
    assert asset.face_count == len(asset.mesh.faces)
    assert asset.vertex_count > 0
    assert asset.face_count > 0


def test_scene_import_applies_node_transforms_and_combines_geometry() -> None:
    scene = trimesh.Scene()
    first = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    second = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    transform = np.eye(4)
    transform[0, 3] = 4.0
    scene.add_geometry(first, node_name="left", geom_name="left-box")
    scene.add_geometry(second, node_name="right", geom_name="right-box", transform=transform)

    asset = mesh_asset_from_geometry(scene)

    assert asset.source_was_scene is True
    assert np.allclose(asset.bounds[0], (-1.0, -1.0, -1.0))
    assert np.allclose(asset.bounds[1], (5.0, 1.0, 1.0))
    assert np.allclose(asset.dimensions, (6.0, 2.0, 2.0))
    assert asset.face_count == 24


def test_geometry_units_are_preserved_when_available() -> None:
    mesh = trimesh.creation.box(extents=(1.0, 2.0, 3.0))
    mesh.units = "mm"

    asset = mesh_asset_from_geometry(mesh)

    assert asset.units == "mm"
    assert np.allclose(asset.dimensions, (1.0, 2.0, 3.0))


def test_empty_mesh_is_rejected() -> None:
    empty = trimesh.Trimesh(
        vertices=np.empty((0, 3)),
        faces=np.empty((0, 3), dtype=np.int64),
        process=False,
    )

    with pytest.raises(MeshImportError, match="empty"):
        mesh_asset_from_geometry(empty)


def test_non_mesh_geometry_is_rejected() -> None:
    with pytest.raises(MeshImportError, match="expected Trimesh or Scene"):
        mesh_asset_from_geometry(object())
