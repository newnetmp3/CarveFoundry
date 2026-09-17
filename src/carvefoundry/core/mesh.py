from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import numpy as np
import trimesh

MeshGeometry: TypeAlias = trimesh.Trimesh | trimesh.Scene


class MeshImportError(ValueError):
    """Raised when imported mesh data cannot be used by CarveFoundry."""


@dataclass(slots=True)
class MeshAsset:
    """Normalized mesh data retained by a project item for viewport and CAM use."""

    mesh: trimesh.Trimesh
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]]
    dimensions: tuple[float, float, float]
    vertex_count: int
    face_count: int
    units: str | None = None
    source_path: Path | None = None
    source_was_scene: bool = False


def _units_from_geometry(geometry: MeshGeometry) -> str | None:
    try:
        units = getattr(geometry, "units", None)
    except (TypeError, ValueError):
        units = None
    if units:
        return str(units)

    metadata = getattr(geometry, "metadata", None)
    if isinstance(metadata, dict):
        units = metadata.get("units") or metadata.get("unit")
        if units:
            return str(units)
    return None


def _scene_to_mesh(scene: trimesh.Scene) -> trimesh.Trimesh:
    meshes: list[trimesh.Trimesh] = []
    for node_name in scene.graph.nodes_geometry:
        transform, geometry_name = scene.graph[node_name]
        geometry = scene.geometry.get(geometry_name)
        if not isinstance(geometry, trimesh.Trimesh):
            continue
        transformed = geometry.copy()
        transformed.apply_transform(transform)
        meshes.append(transformed)

    if not meshes:
        raise MeshImportError("The mesh scene does not contain any usable triangle geometry.")
    if len(meshes) == 1:
        return meshes[0]
    return trimesh.util.concatenate(meshes)


def normalize_mesh_geometry(geometry: object) -> tuple[trimesh.Trimesh, bool]:
    """Return one transformed Trimesh and whether the source was a Scene."""

    if isinstance(geometry, trimesh.Trimesh):
        return geometry.copy(), False
    if isinstance(geometry, trimesh.Scene):
        return _scene_to_mesh(geometry), True
    raise MeshImportError(
        f"Unsupported mesh object {type(geometry).__name__}; expected Trimesh or Scene."
    )


def mesh_asset_from_geometry(
    geometry: object,
    *,
    source_path: Path | None = None,
) -> MeshAsset:
    """Validate and describe Trimesh/Scene geometry without discarding the mesh."""

    units = (
        _units_from_geometry(geometry)
        if isinstance(geometry, (trimesh.Trimesh, trimesh.Scene))
        else None
    )
    mesh, source_was_scene = normalize_mesh_geometry(geometry)
    if units is None:
        units = _units_from_geometry(mesh)

    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise MeshImportError("The mesh is empty; at least one triangle is required.")
    if not np.isfinite(mesh.vertices).all():
        raise MeshImportError("The mesh contains non-finite vertex coordinates.")

    bounds_array = np.asarray(mesh.bounds, dtype=float)
    dimensions_array = np.asarray(mesh.extents, dtype=float)
    if bounds_array.shape != (2, 3) or dimensions_array.shape != (3,):
        raise MeshImportError("The mesh does not have valid three-dimensional bounds.")
    if not np.isfinite(bounds_array).all() or not np.isfinite(dimensions_array).all():
        raise MeshImportError("The mesh bounds contain non-finite values.")
    if not np.isfinite(mesh.area) or mesh.area <= 0:
        raise MeshImportError("The mesh has no usable triangle surface area.")

    bounds = (
        tuple(float(value) for value in bounds_array[0]),
        tuple(float(value) for value in bounds_array[1]),
    )
    dimensions = tuple(float(value) for value in dimensions_array)

    return MeshAsset(
        mesh=mesh,
        bounds=bounds,
        dimensions=dimensions,
        vertex_count=len(mesh.vertices),
        face_count=len(mesh.faces),
        units=units,
        source_path=source_path,
        source_was_scene=source_was_scene,
    )


def load_stl(path: str | Path) -> MeshAsset:
    """Load an STL file and retain normalized geometry plus import metadata."""

    source_path = Path(path)
    if source_path.suffix.lower() != ".stl":
        raise MeshImportError(f"Expected an STL file, got {source_path.name!r}.")
    if not source_path.is_file():
        raise MeshImportError(f"STL file does not exist: {source_path}")

    try:
        loaded = trimesh.load(source_path, process=False)
    except Exception as exc:  # trimesh loaders expose several parser-specific exceptions
        raise MeshImportError(f"Could not read {source_path.name}: {exc}") from exc

    return mesh_asset_from_geometry(loaded, source_path=source_path)
