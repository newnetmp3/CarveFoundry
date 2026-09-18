import numpy as np
import pytest
import trimesh

from carvefoundry.core.mesh import mesh_asset_from_geometry
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.transform import Transform3D, placement_on_stock


def test_translation_moves_mesh_without_changing_dimensions() -> None:
    mesh = trimesh.creation.box(extents=(10.0, 20.0, 5.0))
    transform = Transform3D(translation_mm=(15.0, -3.0, 2.0))

    moved = transform.apply_to_mesh(mesh)

    assert np.allclose(moved.extents, mesh.extents)
    assert np.allclose(moved.bounds.mean(axis=0), (15.0, -3.0, 2.0))


def test_x_rotation_acts_in_yz_plane() -> None:
    mesh = trimesh.creation.box(extents=(10.0, 20.0, 5.0))
    transform = Transform3D(rotation_deg=(90.0, 0.0, 0.0))

    rotated = transform.apply_to_mesh(mesh)

    assert np.allclose(rotated.extents, (10.0, 5.0, 20.0), atol=1e-9)


def test_y_rotation_acts_in_xz_plane() -> None:
    mesh = trimesh.creation.box(extents=(10.0, 20.0, 5.0))
    transform = Transform3D(rotation_deg=(0.0, 90.0, 0.0))

    rotated = transform.apply_to_mesh(mesh)

    assert np.allclose(rotated.extents, (5.0, 20.0, 10.0), atol=1e-9)


def test_z_rotation_swaps_rectangular_xy_extents() -> None:
    mesh = trimesh.creation.box(extents=(10.0, 20.0, 5.0))
    transform = Transform3D(rotation_deg=(0.0, 0.0, 90.0))

    rotated = transform.apply_to_mesh(mesh)

    assert np.allclose(rotated.extents, (20.0, 10.0, 5.0), atol=1e-9)


def test_positive_axis_rotations_follow_right_hand_rule() -> None:
    x_rotated = Transform3D(rotation_deg=(90.0, 0.0, 0.0)).apply_points(
        np.array(((0.0, 1.0, 0.0),))
    )
    y_rotated = Transform3D(rotation_deg=(0.0, 90.0, 0.0)).apply_points(
        np.array(((0.0, 0.0, 1.0),))
    )
    z_rotated = Transform3D(rotation_deg=(0.0, 0.0, 90.0)).apply_points(
        np.array(((1.0, 0.0, 0.0),))
    )

    assert np.allclose(x_rotated[0], (0.0, 0.0, 1.0), atol=1e-9)
    assert np.allclose(y_rotated[0], (1.0, 0.0, 0.0), atol=1e-9)
    assert np.allclose(z_rotated[0], (0.0, 1.0, 0.0), atol=1e-9)


def test_non_uniform_scale_changes_extents() -> None:
    mesh = trimesh.creation.box(extents=(10.0, 20.0, 5.0))
    transform = Transform3D(scale_xyz=(2.0, 0.5, 3.0))

    scaled = transform.apply_to_mesh(mesh)

    assert np.allclose(scaled.extents, (20.0, 10.0, 15.0))


def test_invalid_scale_is_rejected() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        Transform3D(scale_xyz=(1.0, 0.0, 1.0)).matrix()


def test_default_stock_placement_centers_xy_and_sets_top_to_z_zero() -> None:
    mesh = trimesh.creation.box(extents=(20.0, 40.0, 10.0))

    transform = placement_on_stock(mesh, stock_width_mm=100.0, stock_height_mm=80.0)
    placed = transform.apply_to_mesh(mesh)

    assert np.allclose(placed.bounds.mean(axis=0)[:2], (50.0, 40.0))
    assert placed.bounds[1, 2] == pytest.approx(0.0)


def test_project_item_returns_transformed_mesh() -> None:
    asset = mesh_asset_from_geometry(trimesh.creation.box(extents=(4.0, 6.0, 2.0)))
    project = Project(stock=Stock(width_mm=100.0, height_mm=80.0, thickness_mm=18.0))
    transform = project.default_transform_for_mesh(asset)
    item = ProjectItem("box.stl", kind="stl", mesh=asset, transform=transform)

    transformed = item.transformed_mesh()

    assert transformed is not None
    assert np.allclose(transformed.bounds.mean(axis=0)[:2], (50.0, 40.0))
    assert transformed.bounds[1, 2] == pytest.approx(0.0)
