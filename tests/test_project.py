from pathlib import Path

import numpy as np
import trimesh

from carvefoundry.core.mesh import mesh_asset_from_geometry
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.units import ModelUnits


def test_inch_source_units_are_converted_to_millimeters_before_transform() -> None:
    asset = mesh_asset_from_geometry(trimesh.creation.box(extents=(1.0, 2.0, 0.5)))
    item = ProjectItem(
        "inch-part.stl",
        kind="stl",
        mesh=asset,
        source_units=ModelUnits.INCHES,
    )

    transformed = item.transformed_mesh()

    assert transformed is not None
    assert np.allclose(transformed.extents, (25.4, 50.8, 12.7))


def test_default_placement_respects_source_units() -> None:
    asset = mesh_asset_from_geometry(trimesh.creation.box(extents=(1.0, 2.0, 0.5)))
    project = Project()
    transform = project.default_transform_for_mesh(asset, ModelUnits.INCHES)
    item = ProjectItem(
        "inch-part.stl",
        kind="stl",
        mesh=asset,
        transform=transform,
        source_units=ModelUnits.INCHES,
    )

    transformed = item.transformed_mesh()

    assert transformed is not None
    assert np.allclose(transformed.bounds.mean(axis=0)[:2], (150.0, 100.0))
    assert transformed.bounds[1, 2] == 0.0


def test_duplicate_item_copies_transform_but_not_transform_object() -> None:
    asset = mesh_asset_from_geometry(trimesh.creation.box())
    original = ProjectItem(
        "part.stl",
        Path("part.stl"),
        "stl",
        mesh=asset,
        transform=Transform3D(translation_mm=(5.0, 6.0, 7.0)),
        source_units=ModelUnits.INCHES,
    )
    project = Project(items=[original])

    new_index, duplicate = project.duplicate_item(0)
    duplicate.transform.translation_mm = (9.0, 9.0, 9.0)

    assert new_index == 1
    assert duplicate.name == "part copy.stl"
    assert duplicate.mesh is original.mesh
    assert duplicate.source_units is ModelUnits.INCHES
    assert original.transform.translation_mm == (5.0, 6.0, 7.0)


def test_remove_and_move_items() -> None:
    project = Project(
        items=[
            ProjectItem("a"),
            ProjectItem("b"),
            ProjectItem("c"),
        ]
    )

    assert project.move_item(2, -1) == 1
    assert [item.name for item in project.items] == ["a", "c", "b"]
    removed = project.remove_item(1)

    assert removed.name == "c"
    assert [item.name for item in project.items] == ["a", "b"]


def test_fast_transformed_bounds_match_unrotated_mesh_bounds() -> None:
    asset = mesh_asset_from_geometry(trimesh.creation.box(extents=(2.0, 4.0, 6.0)))
    item = ProjectItem(
        "part.stl",
        kind="stl",
        mesh=asset,
        transform=Transform3D(
            translation_mm=(10.0, 20.0, -3.0),
            scale_xyz=(2.0, 0.5, 1.5),
        ),
    )

    fast_bounds = item.transformed_bounds_mm()
    transformed = item.transformed_mesh()

    assert fast_bounds is not None
    assert transformed is not None
    assert np.allclose(fast_bounds, transformed.bounds)
