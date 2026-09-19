from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from collections.abc import Callable

import numpy as np
import trimesh


@dataclass(frozen=True, slots=True)
class HeightField:
    """Regular XY samples of the top-most machinable surface, expressed in millimeters."""

    x_mm: np.ndarray
    y_mm: np.ndarray
    z_mm: np.ndarray

    def __post_init__(self) -> None:
        x = np.asarray(self.x_mm, dtype=float)
        y = np.asarray(self.y_mm, dtype=float)
        z = np.asarray(self.z_mm, dtype=float)
        if x.ndim != 1 or y.ndim != 1:
            raise ValueError("Height-field axes must be one-dimensional.")
        if len(x) < 2 or len(y) < 2:
            raise ValueError("Height fields require at least two samples on each axis.")
        if z.shape != (len(y), len(x)):
            raise ValueError("Height-field Z shape must be (len(y), len(x)).")
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError("Height-field axes must be finite.")
        if np.any(np.diff(x) <= 0) or np.any(np.diff(y) <= 0):
            raise ValueError("Height-field axes must increase strictly.")
        if not np.allclose(np.diff(x), np.diff(x)[0], rtol=1e-7, atol=1e-9):
            raise ValueError("Height-field X samples must be evenly spaced.")
        if not np.allclose(np.diff(y), np.diff(y)[0], rtol=1e-7, atol=1e-9):
            raise ValueError("Height-field Y samples must be evenly spaced.")
        object.__setattr__(self, "x_mm", x)
        object.__setattr__(self, "y_mm", y)
        object.__setattr__(self, "z_mm", z)

    @property
    def spacing_x_mm(self) -> float:
        return float(self.x_mm[1] - self.x_mm[0])

    @property
    def spacing_y_mm(self) -> float:
        return float(self.y_mm[1] - self.y_mm[0])

    @property
    def valid_mask(self) -> np.ndarray:
        return np.isfinite(self.z_mm)

    @property
    def bounds_xy_mm(self) -> tuple[float, float, float, float]:
        return (
            float(self.x_mm[0]),
            float(self.y_mm[0]),
            float(self.x_mm[-1]),
            float(self.y_mm[-1]),
        )

    @classmethod
    def from_mesh_top_surface(
        cls,
        mesh: trimesh.Trimesh,
        *,
        spacing_mm: float,
        padding_mm: float = 0.0,
        fill_missing_z_mm: float | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> HeightField:
        """Rasterize the top-most Z surface of *mesh* onto a regular XY grid.

        This is a top-down 3-axis representation: for overlapping/overhanging
        triangles, the highest Z at an XY sample wins. Nearly vertical triangles
        have no XY area and therefore do not directly contribute samples.
        """

        if spacing_mm <= 0 or not np.isfinite(spacing_mm):
            raise ValueError("spacing_mm must be a finite value greater than zero.")
        if padding_mm < 0 or not np.isfinite(padding_mm):
            raise ValueError("padding_mm must be finite and non-negative.")
        if fill_missing_z_mm is not None and not np.isfinite(fill_missing_z_mm):
            raise ValueError("fill_missing_z_mm must be finite when supplied.")
        vertices = np.asarray(mesh.vertices, dtype=float)
        faces = np.asarray(mesh.faces, dtype=np.int64)
        if len(vertices) == 0 or len(faces) == 0:
            raise ValueError("Cannot rasterize an empty mesh.")
        if not np.isfinite(vertices).all():
            raise ValueError("Cannot rasterize a mesh with non-finite vertices.")

        bounds = np.asarray(mesh.bounds, dtype=float)
        min_x, min_y = bounds[0, :2] - padding_mm
        max_x, max_y = bounds[1, :2] + padding_mm
        span_x = float(max_x - min_x)
        span_y = float(max_y - min_y)
        if span_x <= 0 or span_y <= 0:
            raise ValueError("Mesh must have non-zero XY dimensions for 3-axis CAM.")

        x_count = max(2, ceil(span_x / spacing_mm) + 1)
        y_count = max(2, ceil(span_y / spacing_mm) + 1)
        x_axis = np.linspace(min_x, max_x, x_count, dtype=float)
        y_axis = np.linspace(min_y, max_y, y_count, dtype=float)
        z_field = np.full((y_count, x_count), -np.inf, dtype=float)

        tolerance = 1e-10
        face_count = len(faces)
        progress_stride = max(1, face_count // 100)
        if progress is not None:
            progress(0.0)
        for face_index, face in enumerate(faces):
            triangle = vertices[face]
            x0, y0, z0 = triangle[0]
            x1, y1, z1 = triangle[1]
            x2, y2, z2 = triangle[2]
            denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(denominator) <= tolerance:
                continue

            ix0 = max(0, int(np.searchsorted(x_axis, min(x0, x1, x2), side="left")))
            ix1 = min(
                x_count - 1,
                int(np.searchsorted(x_axis, max(x0, x1, x2), side="right") - 1),
            )
            iy0 = max(0, int(np.searchsorted(y_axis, min(y0, y1, y2), side="left")))
            iy1 = min(
                y_count - 1,
                int(np.searchsorted(y_axis, max(y0, y1, y2), side="right") - 1),
            )
            if ix1 < ix0 or iy1 < iy0:
                continue

            grid_x, grid_y = np.meshgrid(
                x_axis[ix0 : ix1 + 1],
                y_axis[iy0 : iy1 + 1],
            )
            weight0 = (
                (y1 - y2) * (grid_x - x2) + (x2 - x1) * (grid_y - y2)
            ) / denominator
            weight1 = (
                (y2 - y0) * (grid_x - x2) + (x0 - x2) * (grid_y - y2)
            ) / denominator
            weight2 = 1.0 - weight0 - weight1
            inside = (
                (weight0 >= -tolerance)
                & (weight1 >= -tolerance)
                & (weight2 >= -tolerance)
            )
            interpolated_z = weight0 * z0 + weight1 * z1 + weight2 * z2
            target = z_field[iy0 : iy1 + 1, ix0 : ix1 + 1]
            np.maximum(target, np.where(inside, interpolated_z, -np.inf), out=target)
            if (
                progress is not None
                and (
                    face_index % progress_stride == 0
                    or face_index == face_count - 1
                )
            ):
                progress((face_index + 1) / face_count)

        missing = ~np.isfinite(z_field)
        if fill_missing_z_mm is None:
            z_field[missing] = np.nan
            if not np.isfinite(z_field).any():
                raise ValueError("Mesh produced no top-surface samples.")
        else:
            z_field[missing] = float(fill_missing_z_mm)
        return cls(x_axis, y_axis, z_field)
