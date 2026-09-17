from __future__ import annotations

import numpy as np
import trimesh


def expand_triangle_positions(mesh: trimesh.Trimesh) -> np.ndarray:
    """Return contiguous float32 triangle vertices for non-indexed GPU drawing.

    PySide6's QOpenGLFunctions binding is inconsistent across versions for the
    pointer/offset argument accepted by ``glDrawElements``. Expanding indexed
    triangles once at upload time lets the viewport use ``glDrawArrays`` while
    still keeping all per-frame transforms and rasterization on the GPU.
    """

    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.int64)

    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) == 0:
        raise ValueError("Mesh must contain XYZ vertices.")
    if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
        raise ValueError("Mesh must contain triangular faces.")
    if np.any(faces < 0) or np.any(faces >= len(vertices)):
        raise ValueError("Mesh contains an out-of-range face index.")

    expanded = vertices[faces].reshape((-1, 3))
    return np.ascontiguousarray(expanded, dtype=np.float32)
