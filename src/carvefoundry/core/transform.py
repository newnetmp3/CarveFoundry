from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin

import numpy as np
import trimesh


@dataclass(slots=True)
class Transform3D:
    """Mutable model transform used by both the viewport and future CAM calculations."""

    translation_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale_xyz: tuple[float, float, float] = (1.0, 1.0, 1.0)

    def validate(self) -> None:
        values = (*self.translation_mm, *self.rotation_deg, *self.scale_xyz)
        if not np.isfinite(values).all():
            raise ValueError("Transform values must all be finite.")
        if any(value <= 0 for value in self.scale_xyz):
            raise ValueError("Transform scale values must be greater than zero.")

    def matrix(self, pivot: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> np.ndarray:
        """Build a 4x4 transform matrix around *pivot* in model coordinates."""

        self.validate()
        tx, ty, tz = self.translation_mm
        rx, ry, rz = (radians(value) for value in self.rotation_deg)
        sx, sy, sz = self.scale_xyz
        px, py, pz = pivot

        translate = np.eye(4, dtype=float)
        translate[:3, 3] = (tx, ty, tz)

        to_pivot = np.eye(4, dtype=float)
        to_pivot[:3, 3] = (px, py, pz)
        from_pivot = np.eye(4, dtype=float)
        from_pivot[:3, 3] = (-px, -py, -pz)

        scale = np.diag((sx, sy, sz, 1.0))

        rotate_x = np.array(
            (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, cos(rx), -sin(rx), 0.0),
                (0.0, sin(rx), cos(rx), 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
            dtype=float,
        )
        rotate_y = np.array(
            (
                (cos(ry), 0.0, sin(ry), 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (-sin(ry), 0.0, cos(ry), 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
            dtype=float,
        )
        rotate_z = np.array(
            (
                (cos(rz), -sin(rz), 0.0, 0.0),
                (sin(rz), cos(rz), 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
            dtype=float,
        )

        return translate @ to_pivot @ rotate_z @ rotate_y @ rotate_x @ scale @ from_pivot

    def apply_points(
        self,
        points: np.ndarray,
        *,
        pivot: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> np.ndarray:
        """Return transformed XYZ points without mutating the source array."""

        points_array = np.asarray(points, dtype=float)
        if points_array.ndim != 2 or points_array.shape[1] != 3:
            raise ValueError("Points must have shape (N, 3).")
        homogeneous = np.column_stack((points_array, np.ones(len(points_array))))
        return (self.matrix(pivot) @ homogeneous.T).T[:, :3]

    def apply_to_mesh(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Return a transformed copy of *mesh*, rotating/scaling around its bounds center."""

        transformed = mesh.copy()
        pivot = tuple(float(value) for value in np.asarray(mesh.bounds, dtype=float).mean(axis=0))
        transformed.apply_transform(self.matrix(pivot))
        return transformed

    def transformed_bounds(
        self, mesh: trimesh.Trimesh
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        transformed = self.apply_to_mesh(mesh)
        bounds = np.asarray(transformed.bounds, dtype=float)
        return (
            tuple(float(value) for value in bounds[0]),
            tuple(float(value) for value in bounds[1]),
        )


def placement_on_stock(
    mesh: trimesh.Trimesh,
    *,
    stock_width_mm: float,
    stock_height_mm: float,
) -> Transform3D:
    """Center a mesh over the stock in XY and place its highest point at stock Z0."""

    bounds = np.asarray(mesh.bounds, dtype=float)
    center = bounds.mean(axis=0)
    translation = (
        float(stock_width_mm / 2.0 - center[0]),
        float(stock_height_mm / 2.0 - center[1]),
        float(-bounds[1, 2]),
    )
    return Transform3D(translation_mm=translation)
