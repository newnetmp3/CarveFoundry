import numpy as np
import pytest
import trimesh

from carvefoundry.cam.heightfield import HeightField


def test_box_rasterizes_to_its_top_surface() -> None:
    mesh = trimesh.creation.box(extents=(10.0, 8.0, 4.0))

    field = HeightField.from_mesh_top_surface(mesh, spacing_mm=2.0)

    assert field.z_mm.shape == (5, 6)
    assert np.isfinite(field.z_mm).all()
    assert np.allclose(field.z_mm, 2.0)
    assert field.spacing_x_mm == pytest.approx(2.0)
    assert field.spacing_y_mm == pytest.approx(2.0)


def test_rasterizer_uses_highest_surface_when_xy_overlaps() -> None:
    lower = trimesh.creation.box(extents=(4.0, 4.0, 1.0))
    upper = trimesh.creation.box(extents=(2.0, 2.0, 1.0))
    upper.apply_translation((0.0, 0.0, 2.0))
    mesh = trimesh.util.concatenate((lower, upper))

    field = HeightField.from_mesh_top_surface(mesh, spacing_mm=1.0)

    center_x = int(np.argmin(np.abs(field.x_mm)))
    center_y = int(np.argmin(np.abs(field.y_mm)))
    assert field.z_mm[center_y, center_x] == pytest.approx(2.5)
    assert field.z_mm[0, 0] == pytest.approx(0.5)


def test_height_field_rejects_nonuniform_axes() -> None:
    with pytest.raises(ValueError, match="evenly spaced"):
        HeightField(
            np.array([0.0, 1.0, 3.0]),
            np.array([0.0, 1.0]),
            np.zeros((2, 3)),
        )
