"""2D silhouette Boolean and signed-offset operations for machinable design shapes.

These are *planar* operations. The result is an independent, watertight
stock-top extrusion; they are not volumetric Boolean operations on reliefs.
"""
from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from carvefoundry.cam.vector_ops import projected_regions

from .mesh import MeshAsset, mesh_asset_from_geometry
from .project import ProjectItem

PLANAR_KINDS = frozenset({
    "rectangle", "ellipse", "polygon", "line", "pen", "text",
    "trace", "boolean", "offset",
})
BOOLEAN_OPERATIONS = frozenset({"union", "subtract", "intersect"})
JOIN_STYLES = frozenset({"round", "mitre", "bevel"})
_EPS = 1e-8


def _parts(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry] if geometry.area > _EPS else []
    if isinstance(geometry, MultiPolygon):
        return [part for part in geometry.geoms if part.area > _EPS]
    return []


def _project_item(item: ProjectItem) -> BaseGeometry:
    if item.kind.lower() not in PLANAR_KINDS or item.mesh is None:
        raise ValueError(f"{item.name}: select a renderable planar design shape.")
    rx, ry, _rz = item.transform.rotation_deg
    if any(abs((float(angle) + 180.0) % 360.0 - 180.0) > 1e-6 for angle in (rx, ry)):
        raise ValueError(f"{item.name}: apply only XY-plane shapes (no X/Y tilt).")
    mesh = item.transformed_mesh()
    if mesh is None:
        raise ValueError(f"{item.name}: no machinable geometry.")
    regions = projected_regions(mesh)
    if regions.is_empty or regions.area <= _EPS:
        raise ValueError(f"{item.name}: no closed machinable XY area.")
    return regions


def build_planar_result(
    items: Sequence[ProjectItem],
    *,
    operation: str,
    depth_mm: float,
    offset_mm: float = 0.0,
    join_style: str = "round",
) -> MeshAsset:
    """Build an independent Z0-topped extrusion from selected shape silhouettes.

    Item order matters for subtraction: item 0 MINUS the union of items 1+.
    Positive offset expands material; negative offset shrinks material.
    Holes and disjoint islands are preserved in the final mesh.
    """
    if operation not in BOOLEAN_OPERATIONS | {"offset"}:
        raise ValueError(f"Unsupported planar operation: {operation}")
    if not isfinite(depth_mm) or depth_mm <= 0:
        raise ValueError("Depth must be a finite positive number of millimeters.")
    if operation == "offset":
        if len(items) != 1:
            raise ValueError("Offset requires exactly one selected planar shape.")
        if not isfinite(offset_mm) or abs(offset_mm) <= _EPS:
            raise ValueError("Offset distance must be a finite, non-zero value.")
        if join_style not in JOIN_STYLES:
            raise ValueError(f"Unsupported offset corner style: {join_style}")
    elif len(items) < 2:
        raise ValueError("Boolean operations require at least two selected planar shapes.")

    regions = [_project_item(item) for item in items]
    if operation == "offset":
        geometry = regions[0].buffer(offset_mm, join_style=join_style, quad_segs=16)
    elif operation == "union":
        geometry = unary_union(regions)
    elif operation == "intersect":
        geometry = regions[0]
        for region in regions[1:]:
            geometry = geometry.intersection(region)
            if geometry.is_empty:
                break
    else:
        geometry = regions[0].difference(unary_union(regions[1:]))

    if geometry.is_empty or geometry.area <= _EPS:
        raise ValueError("Operation produced no machinable area; source shapes were unchanged.")
    if not geometry.is_valid:
        raise ValueError("Operation produced invalid contours; source shapes were unchanged.")

    meshes: list[trimesh.Trimesh] = []
    for polygon in _parts(geometry):
        mesh = trimesh.creation.extrude_polygon(
            polygon, height=float(depth_mm), engine="earcut",
        )
        mesh.apply_translation((0.0, 0.0, -float(depth_mm)))
        if not mesh.is_watertight:
            raise ValueError("Operation produced a non-watertight region; no shape was changed.")
        meshes.append(mesh)
    if not meshes:
        raise ValueError("Operation produced no extrudable polygon; source shapes were unchanged.")

    result = trimesh.util.concatenate(meshes)
    bounds = np.asarray(result.bounds, dtype=float)
    if not np.isclose(bounds[1, 2], 0.0) or not np.isclose(bounds[0, 2], -depth_mm):
        raise ValueError("Planar extrusion did not fit the requested Z depth.")
    return mesh_asset_from_geometry(result)
