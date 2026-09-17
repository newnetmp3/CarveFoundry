import numpy as np
import pytest
import trimesh

from carvefoundry.ui.gpu_geometry import expand_triangle_positions


def test_expand_triangle_positions_matches_face_order() -> None:
    mesh = trimesh.Trimesh(
        vertices=np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
        ),
        faces=np.array([[0, 1, 2], [0, 2, 3]]),
        process=False,
    )

    expanded = expand_triangle_positions(mesh)

    assert expanded.dtype == np.float32
    assert expanded.flags.c_contiguous
    assert expanded.shape == (6, 3)
    assert np.allclose(
        expanded,
        np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        ),
    )


def test_expand_triangle_positions_rejects_empty_mesh() -> None:
    mesh = trimesh.Trimesh(
        vertices=np.empty((0, 3)),
        faces=np.empty((0, 3), dtype=np.int64),
        process=False,
    )

    with pytest.raises(ValueError, match="vertices"):
        expand_triangle_positions(mesh)
