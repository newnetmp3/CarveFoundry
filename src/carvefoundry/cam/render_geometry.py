"""Pure NumPy toolpath preview geometry, safe to compute in a worker process."""
from __future__ import annotations

from collections.abc import Callable

import numpy as np

from carvefoundry.cam.toolpath import MoveKind, Toolpath


def build_render_geometry(
    toolpaths: list[Toolpath],
    *,
    segment_budget: int = 120_000,
    progress: Callable[[float, str], None] | None = None,
) -> dict[str, object]:
    """Build full/L0D line buffers without invoking Qt or OpenGL.

    The returned arrays can be transported to the GUI and directly installed
    into the viewport cache; only the GPU upload remains on the GUI thread.
    """

    cut_chunks: list[np.ndarray] = []
    rapid_chunks: list[np.ndarray] = []
    point_chunks: list[np.ndarray] = []
    rapid_flag_chunks: list[np.ndarray] = []
    segment_count = 0
    count = len(toolpaths)

    for index, toolpath in enumerate(toolpaths):
        moves = toolpath.moves
        move_count = len(moves)
        if move_count:
            coords = np.fromiter(
                (coordinate for move in moves for coordinate in move.xyz),
                dtype=np.float32,
                count=move_count * 3,
            ).reshape((-1, 3))
            point_chunks.append(coords)
            if move_count >= 2:
                flags = np.fromiter(
                    (move.kind is MoveKind.RAPID for move in moves[1:]),
                    dtype=np.bool_,
                    count=move_count - 1,
                )
                segments = np.empty((move_count - 1, 2, 3), dtype=np.float32)
                segments[:, 0, :] = coords[:-1]
                segments[:, 1, :] = coords[1:]
                if np.any(~flags):
                    cut_chunks.append(segments[~flags].reshape((-1, 3)))
                if np.any(flags):
                    rapid_chunks.append(segments[flags].reshape((-1, 3)))
                rapid_flag_chunks.append(flags)
                segment_count += move_count - 1
        if progress is not None:
            progress((index + 1) / max(1, count), "Preparing toolpath preview")

    empty = np.empty((0, 3), dtype=np.float32)
    cut_vertices = (
        np.concatenate(cut_chunks, axis=0) if cut_chunks else empty.copy()
    )
    rapid_vertices = (
        np.concatenate(rapid_chunks, axis=0) if rapid_chunks else empty.copy()
    )
    points = np.concatenate(point_chunks, axis=0) if point_chunks else empty.copy()

    if rapid_flag_chunks:
        flags = np.concatenate(rapid_flag_chunks)
        prefix = np.empty(len(flags) + 1, dtype=np.uint32)
        prefix[0] = 0
        np.cumsum(flags, dtype=np.uint32, out=prefix[1:])
    else:
        prefix = np.zeros(1, dtype=np.uint32)

    stride = max(1, int(np.ceil(segment_count / max(1, segment_budget))))

    def decimate(vertices: np.ndarray) -> np.ndarray:
        if stride <= 1 or len(vertices) <= 2:
            return vertices
        segments = vertices.reshape((-1, 2, 3))
        return np.ascontiguousarray(
            segments[::stride].reshape((-1, 3)),
            dtype=np.float32,
        )

    bounds = None
    if len(points):
        bounds = np.vstack(
            (np.min(points, axis=0), np.max(points, axis=0))
        ).astype(float)

    return {
        "cut_vertices": np.ascontiguousarray(cut_vertices, dtype=np.float32),
        "rapid_vertices": np.ascontiguousarray(rapid_vertices, dtype=np.float32),
        "cut_lod_vertices": decimate(cut_vertices),
        "rapid_lod_vertices": decimate(rapid_vertices),
        "rapid_prefix": prefix,
        "points": np.ascontiguousarray(points, dtype=np.float32),
        "bounds": bounds,
        "segment_count": segment_count,
        "lod_stride": stride,
    }
