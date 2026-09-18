import numpy as np

from carvefoundry.core.primitives import (
    bitmap_runs_mesh,
    rectangle_mesh,
    text_mesh,
)


def test_rectangle_primitive_has_requested_size_and_top_at_zero() -> None:
    asset = rectangle_mesh(50.0, 30.0, 2.0)

    assert np.allclose(asset.dimensions, (50.0, 30.0, 2.0))
    assert np.isclose(asset.bounds[1][2], 0.0)


def test_text_primitive_produces_visible_geometry() -> None:
    asset = text_mesh("CNC", height_mm=14.0, depth_mm=1.5)

    assert asset.vertex_count > 0
    assert asset.face_count > 0
    assert asset.dimensions[0] > 0
    assert asset.dimensions[1] > 0
    assert np.isclose(asset.bounds[1][2], 0.0)


def test_bitmap_trace_compacts_active_runs_into_mesh() -> None:
    mask = np.array(
        [
            [False, True, True, False],
            [True, True, False, False],
        ],
        dtype=bool,
    )

    asset = bitmap_runs_mesh(mask, width_mm=40.0, depth_mm=1.0)

    assert asset.vertex_count > 0
    assert asset.dimensions[0] <= 40.0 + 1e-9
    assert np.isclose(asset.bounds[1][2], 0.0)
