"""Retained editable CNC pen paths, independent of their cutter-facing mesh.

Source knots are in the item's local/model XY millimeter space. Every edit
generates a new MeshAsset; snapshots share immutable old assets, so Undo/Redo
and CAM invalidation are reliable. STL, traced/image and Boolean meshes are
not automatically claimed to be editable vector curves.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import hypot, isfinite

import numpy as np

from .primitives import polyline_mesh
from .project import ProjectItem

MAX_VECTOR_NODES = 12_000


@dataclass(frozen=True, slots=True)
class VectorPath:
    points_xy: tuple[tuple[float, float], ...]
    width_mm: float = 2.0
    depth_mm: float = 1.0
    closed: bool = False

    def validate(self) -> None:
        points = self.points_xy
        if not 2 <= len(points) <= MAX_VECTOR_NODES:
            raise ValueError("An editable path needs 2–12,000 nodes.")
        if self.closed and len(points) < 3:
            raise ValueError("A closed editable path needs at least three nodes.")
        if not isfinite(self.width_mm) or self.width_mm <= 0:
            raise ValueError("Vector stroke width must be positive and finite.")
        if not isfinite(self.depth_mm) or self.depth_mm <= 0:
            raise ValueError("Vector stroke depth must be positive and finite.")
        if not all(isfinite(v) for pair in points for v in pair):
            raise ValueError("Vector node coordinates must be finite.")
        segments = list(zip(points, points[1:], strict=False))
        if self.closed:
            segments.append((points[-1], points[0]))
        if not any(hypot(a[0] - b[0], a[1] - b[1]) > 1e-9
                   for a, b in segments):
            raise ValueError("Editable path has no usable segments.")

    def mesh_asset(self):
        self.validate()
        vertices = list(self.points_xy)
        if self.closed:
            vertices.append(vertices[0])
        return polyline_mesh(
            vertices, width_mm=self.width_mm, depth_mm=self.depth_mm,
        )


def move_node(path: VectorPath, index: int, xy: tuple[float, float]) -> VectorPath:
    if not 0 <= index < len(path.points_xy):
        raise IndexError("Vector node index out of range.")
    points = list(path.points_xy)
    points[index] = (float(xy[0]), float(xy[1]))
    edited = replace(path, points_xy=tuple(points))
    edited.validate()
    return edited


def insert_node(path: VectorPath, segment: int) -> VectorPath:
    """Insert midpoint after segment start; final segment exists if closed."""
    limit = len(path.points_xy) if path.closed else len(path.points_xy) - 1
    if not 0 <= segment < limit:
        raise IndexError("Vector segment index out of range.")
    if len(path.points_xy) >= MAX_VECTOR_NODES:
        raise ValueError("Vector node limit reached.")
    a = path.points_xy[segment]
    b = path.points_xy[(segment + 1) % len(path.points_xy)]
    points = list(path.points_xy)
    points.insert(segment + 1, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    edited = replace(path, points_xy=tuple(points))
    edited.validate()
    return edited


def remove_node(path: VectorPath, index: int) -> VectorPath:
    if not 0 <= index < len(path.points_xy):
        raise IndexError("Vector node index out of range.")
    if len(path.points_xy) <= (3 if path.closed else 2):
        raise ValueError("Cannot remove the last required nodes.")
    points = list(path.points_xy)
    points.pop(index)
    edited = replace(path, points_xy=tuple(points))
    edited.validate()
    return edited


def apply_vector_edit(item: ProjectItem, path: VectorPath) -> None:
    """Commit a validated fresh mesh, preserving the item's actual transform."""
    if item.vector_path is None:
        raise ValueError("Selected model has no retained editable path nodes.")
    if item.source_units.value != "mm":
        raise ValueError("Editable pen source units must remain millimeters.")
    mesh = path.mesh_asset()
    item.mesh = mesh
    item.vector_path = path


def node_world_points(item: ProjectItem) -> np.ndarray:
    if item.vector_path is None or item.mesh is None:
        raise ValueError("Selected object has no editable vector mesh.")
    points = np.asarray(item.vector_path.points_xy, dtype=float)
    local = np.column_stack((points, np.zeros(len(points))))
    bounds = np.asarray(item.mesh.mesh.bounds, dtype=float)
    pivot = tuple(float(value) for value in bounds.mean(axis=0))
    return item.transform.apply_points(local, pivot=pivot)


def world_xy_to_local(
    item: ProjectItem, index: int, xy: tuple[float, float],
) -> tuple[float, float]:
    """Invert the exact current local XY transform and preserve node height.

    Reject X/Y tilt: dragging on the stock-top plane would be ambiguous for
    nonplanar transformed paths. Z rotation and positive XY scale are fine.
    """
    if item.vector_path is None or item.mesh is None:
        raise ValueError("Object has no editable vector nodes.")
    if any(abs(float(v)) > 1e-7 for v in item.transform.rotation_deg[:2]):
        raise ValueError("Use zero X/Y tilt before editing XY path nodes.")
    world = node_world_points(item)
    matrix = item.transform.matrix(
        tuple(float(v) for v in np.asarray(item.mesh.mesh.bounds).mean(axis=0))
    )
    inverse = np.linalg.inv(matrix)
    current = world[index]
    # Preserve transformed node Z; only drag the XY plane.
    local = inverse @ np.array((xy[0], xy[1], current[2], 1), dtype=float)
    if not np.isfinite(local).all():
        raise ValueError("Vector node move must remain finite.")
    return (float(local[0]), float(local[1]))
