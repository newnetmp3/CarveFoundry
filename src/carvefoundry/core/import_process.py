from __future__ import annotations

from pathlib import Path

import numpy as np

from .importer import ImportFileInfo, inspect_import_file


def prepare_stl_import_payload(
    path: str | Path,
    expected_kind: str | None = None,
) -> tuple[ImportFileInfo, bytes, int]:
    """Parse an STL and prepare its non-indexed GPU vertex stream.

    This function is intentionally Qt-free so it can run safely in a spawned
    worker process. Returning the expanded float32 vertex bytes prevents the GUI
    process from doing the expensive indexed-triangle expansion on first paint.
    """

    info = inspect_import_file(path, expected_kind=expected_kind)
    if info.kind != "stl" or info.mesh is None:
        raise ValueError("STL subprocess preparation requires an STL mesh.")

    mesh = info.mesh.mesh
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.int64)

    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) == 0:
        raise ValueError("Mesh must contain XYZ vertices.")
    if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
        raise ValueError("Mesh must contain triangular faces.")
    if np.any(faces < 0) or np.any(faces >= len(vertices)):
        raise ValueError("Mesh contains an out-of-range face index.")

    expanded = np.ascontiguousarray(vertices[faces].reshape((-1, 3)), dtype=np.float32)
    return info, expanded.tobytes(), len(expanded)
