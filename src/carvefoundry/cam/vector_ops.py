from __future__ import annotations

from itertools import pairwise
from math import ceil, hypot, isfinite, pi, radians, tan
from typing import Protocol

import numpy as np
import trimesh
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Polygon,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, unary_union

from carvefoundry.core.tools import Cutter, ToolType

from .toolpath import MoveKind, Toolpath, ToolpathMove


class CamSettingsLike(Protocol):
    safe_z_mm: float
    feed_mm_min: float
    plunge_feed_mm_min: float
    max_stepdown_mm: float
    stepover_fraction: float
    finish_stepover_fraction: float
    overall_depth_mm: float | None
    padding_mm: float
    usable_bit_length_mm: float | None
    tab_height_mm: float
    tab_width_mm: float
    tab_count: int
    tabs_enabled: bool
    milling_direction: object
    pocket_strategy: object
    ramp_angle_deg: float | None


_EPS = 1e-8
_PROJECT_BATCH = 1500
_FEATURE_ANGLE_DEG = 30.0
_SIMPLIFY_MM = 0.01


def _polygon_parts(geometry: BaseGeometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return [polygon for polygon in geometry.geoms if not polygon.is_empty]
    if isinstance(geometry, GeometryCollection):
        result: list[Polygon] = []
        for item in geometry.geoms:
            result.extend(_polygon_parts(item))
        return result
    return []


def _line_parts(geometry: BaseGeometry) -> list[LineString]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return [line for line in geometry.geoms if line.length > _EPS]
    if isinstance(geometry, GeometryCollection):
        result: list[LineString] = []
        for item in geometry.geoms:
            result.extend(_line_parts(item))
        return result
    return []


def projected_regions(mesh: trimesh.Trimesh) -> BaseGeometry:
    """Project machinable model faces to XY while preserving holes and islands."""

    triangles = np.asarray(mesh.triangles, dtype=float)
    normals = np.asarray(mesh.face_normals, dtype=float)
    if len(triangles) == 0:
        raise ValueError("Selected model has no triangles.")

    positive = np.flatnonzero(normals[:, 2] > 1e-7)
    negative = np.flatnonzero(normals[:, 2] < -1e-7)
    face_areas = np.asarray(mesh.area_faces, dtype=float)
    positive_weight = float(
        np.sum(face_areas[positive] * np.abs(normals[positive, 2]))
    )
    negative_weight = float(
        np.sum(face_areas[negative] * np.abs(normals[negative, 2]))
    )
    face_indices = positive if positive_weight >= negative_weight else negative
    if not len(face_indices):
        raise ValueError("Selected model has no XY-projectable faces.")

    unions: list[BaseGeometry] = []
    batch: list[Polygon] = []
    for face_index in face_indices:
        xy = triangles[int(face_index), :, :2]
        signed_twice_area = (
            xy[0, 0] * (xy[1, 1] - xy[2, 1])
            + xy[1, 0] * (xy[2, 1] - xy[0, 1])
            + xy[2, 0] * (xy[0, 1] - xy[1, 1])
        )
        if abs(float(signed_twice_area)) <= _EPS:
            continue
        polygon = Polygon(xy)
        if polygon.area <= _EPS:
            continue
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty:
            continue
        batch.extend(_polygon_parts(polygon))
        if len(batch) >= _PROJECT_BATCH:
            unions.append(unary_union(batch))
            batch.clear()

    if batch:
        unions.append(unary_union(batch))
    if not unions:
        raise ValueError("Selected model produced no usable projected regions.")

    geometry = unary_union(unions)
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    polygons = _polygon_parts(geometry)
    if not polygons:
        raise ValueError("Selected model produced no closed XY regions.")
    return unary_union(polygons)


def _feature_linework(
    mesh: trimesh.Trimesh,
    regions: BaseGeometry,
) -> BaseGeometry:
    lines: list[BaseGeometry] = [regions.boundary]
    vertices = np.asarray(mesh.vertices, dtype=float)

    adjacency_edges = np.asarray(mesh.face_adjacency_edges, dtype=np.int64)
    adjacency_angles = np.asarray(mesh.face_adjacency_angles, dtype=float)
    if len(adjacency_edges) and len(adjacency_angles):
        threshold = radians(_FEATURE_ANGLE_DEG)
        for edge in adjacency_edges[adjacency_angles >= threshold]:
            a = vertices[int(edge[0]), :2]
            b = vertices[int(edge[1]), :2]
            if float(np.linalg.norm(b - a)) <= _EPS:
                continue
            lines.append(LineString((a, b)))

    unique_edges = np.asarray(mesh.edges_unique, dtype=np.int64)
    inverse = np.asarray(mesh.edges_unique_inverse, dtype=np.int64)
    if len(unique_edges) and len(inverse):
        counts = np.bincount(inverse, minlength=len(unique_edges))
        for edge in unique_edges[counts == 1]:
            a = vertices[int(edge[0]), :2]
            b = vertices[int(edge[1]), :2]
            if float(np.linalg.norm(b - a)) > _EPS:
                lines.append(LineString((a, b)))

    merged: BaseGeometry = unary_union(lines)
    try:
        merged = linemerge(merged)
    except ValueError:
        pass
    return merged


def engraving_paths(mesh: trimesh.Trimesh) -> list[np.ndarray]:
    """Return projected outlines plus real sharp internal model features."""

    regions = projected_regions(mesh)
    geometry = _feature_linework(mesh, regions)
    paths: list[np.ndarray] = []
    for line in _line_parts(geometry):
        simplified = line.simplify(_SIMPLIFY_MM, preserve_topology=True)
        for part in _line_parts(simplified):
            points = np.asarray(part.coords, dtype=float)
            if len(points) >= 2:
                paths.append(points)
    if not paths:
        raise ValueError("Selected model produced no engravable contours.")
    return paths


def _settings_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _target_depth(
    mesh: trimesh.Trimesh,
    settings: CamSettingsLike,
    *,
    fallback_mm: float = -1.0,
) -> float:
    if settings.overall_depth_mm is not None:
        target = -abs(float(settings.overall_depth_mm))
    else:
        minimum_z = float(np.asarray(mesh.bounds, dtype=float)[0, 2])
        target = minimum_z if minimum_z < -1e-6 else float(fallback_mm)

    if (
        settings.usable_bit_length_mm is not None
        and abs(target) > settings.usable_bit_length_mm + 1e-9
    ):
        raise ValueError(
            f"Requested cut depth {abs(target):.3f} mm exceeds the usable "
            f"bit length {settings.usable_bit_length_mm:.3f} mm."
        )
    return target


def _depth_passes(target_z: float, max_stepdown_mm: float) -> list[float]:
    if target_z >= 0.0:
        return [target_z]
    depth = abs(target_z)
    count = max(1, ceil(depth / max_stepdown_mm))
    return [-min(depth, (index + 1) * depth / count) for index in range(count)]


def _rapid(moves: list[ToolpathMove], x: float, y: float, z: float) -> None:
    moves.append(ToolpathMove(float(x), float(y), float(z), MoveKind.RAPID))


def _plunge(
    moves: list[ToolpathMove],
    x: float,
    y: float,
    z: float,
    settings: CamSettingsLike,
) -> None:
    moves.append(
        ToolpathMove(
            float(x),
            float(y),
            float(z),
            MoveKind.PLUNGE,
            float(settings.plunge_feed_mm_min),
        )
    )


def _cut(
    moves: list[ToolpathMove],
    x: float,
    y: float,
    z: float,
    settings: CamSettingsLike,
) -> None:
    moves.append(
        ToolpathMove(
            float(x),
            float(y),
            float(z),
            MoveKind.CUT,
            float(settings.feed_mm_min),
        )
    )


def _enter_depth(
    moves: list[ToolpathMove],
    points: np.ndarray,
    target_z: float,
    previous_depth_z: float,
    settings: CamSettingsLike,
) -> int:
    start = points[0]
    _rapid(moves, start[0], start[1], settings.safe_z_mm)
    if settings.ramp_angle_deg is None or len(points) < 2:
        _plunge(moves, start[0], start[1], target_z, settings)
        return 1

    entry_z = min(0.0, previous_depth_z)
    _plunge(moves, start[0], start[1], entry_z, settings)
    end = points[1]
    dx = float(end[0] - start[0])
    dy = float(end[1] - start[1])
    segment_length = hypot(dx, dy)
    if segment_length <= _EPS:
        _plunge(moves, start[0], start[1], target_z, settings)
        return 1

    required = abs(target_z - entry_z) / tan(radians(settings.ramp_angle_deg))
    fraction = min(1.0, required / segment_length)
    ramp_end = (
        float(start[0] + dx * fraction),
        float(start[1] + dy * fraction),
    )
    _cut(moves, ramp_end[0], ramp_end[1], target_z, settings)
    if fraction < 1.0 - 1e-9:
        _cut(moves, end[0], end[1], target_z, settings)
    return 2


def _closed(points: np.ndarray) -> bool:
    return len(points) >= 3 and bool(np.linalg.norm(points[0] - points[-1]) <= 1e-7)


def _rotate_closed_path(points: np.ndarray, target: np.ndarray) -> np.ndarray:
    ring = points[:-1]
    distances = np.linalg.norm(ring - target, axis=1)
    index = int(np.argmin(distances))
    rotated = np.vstack((ring[index:], ring[:index]))
    return np.vstack((rotated, rotated[0]))


def _order_paths(paths: list[np.ndarray]) -> list[np.ndarray]:
    remaining = [np.asarray(path, dtype=float) for path in paths if len(path) >= 2]
    if not remaining:
        return []

    ordered: list[np.ndarray] = [remaining.pop(0)]
    while remaining:
        target = ordered[-1][-1]
        best_index = 0
        best_path = remaining[0]
        best_distance = float("inf")
        for index, path in enumerate(remaining):
            candidate = path
            if _closed(path):
                candidate = _rotate_closed_path(path, target)
                distance = float(np.linalg.norm(candidate[0] - target))
            else:
                start_distance = float(np.linalg.norm(path[0] - target))
                end_distance = float(np.linalg.norm(path[-1] - target))
                if end_distance < start_distance:
                    candidate = path[::-1].copy()
                    distance = end_distance
                else:
                    distance = start_distance
            if distance < best_distance:
                best_distance = distance
                best_index = index
                best_path = candidate
        remaining.pop(best_index)
        ordered.append(best_path)
    return ordered


def _order_tagged_paths(
    paths: list[tuple[np.ndarray, bool]],
) -> list[tuple[np.ndarray, bool]]:
    remaining = [
        (np.asarray(points, dtype=float), bool(tag))
        for points, tag in paths
        if len(points) >= 2
    ]
    if not remaining:
        return []

    ordered: list[tuple[np.ndarray, bool]] = [remaining.pop(0)]
    while remaining:
        target = ordered[-1][0][-1]
        best_index = 0
        best_points = remaining[0][0]
        best_tag = remaining[0][1]
        best_distance = float("inf")
        for index, (points, tag) in enumerate(remaining):
            candidate = points
            if _closed(points):
                candidate = _rotate_closed_path(points, target)
                distance = float(np.linalg.norm(candidate[0] - target))
            else:
                start_distance = float(np.linalg.norm(points[0] - target))
                end_distance = float(np.linalg.norm(points[-1] - target))
                if end_distance < start_distance:
                    candidate = points[::-1].copy()
                    distance = end_distance
                else:
                    distance = start_distance
            if distance < best_distance:
                best_distance = distance
                best_index = index
                best_points = candidate
                best_tag = tag
        remaining.pop(best_index)
        ordered.append((best_points, best_tag))
    return ordered


def _signed_area(points: np.ndarray) -> float:
    ring = points[:-1] if _closed(points) else points
    if len(ring) < 3:
        return 0.0
    shifted = np.roll(ring, -1, axis=0)
    return float(
        0.5
        * np.sum(
            ring[:, 0] * shifted[:, 1]
            - shifted[:, 0] * ring[:, 1]
        )
    )


def _oriented_ring(
    coordinates: object,
    *,
    exterior: bool,
    settings: CamSettingsLike,
) -> np.ndarray:
    points = np.asarray(coordinates, dtype=float)
    if not _closed(points):
        points = np.vstack((points, points[0]))

    conventional = _settings_value(settings.milling_direction) == "conventional"
    # Clockwise outer / counterclockwise inner is climb for a conventional
    # clockwise router spindle. Conventional milling reverses both.
    want_clockwise = exterior != conventional
    is_clockwise = _signed_area(points) < 0.0
    if is_clockwise != want_clockwise:
        points = points[::-1].copy()
    return points


def _ring_paths(
    geometry: BaseGeometry,
    settings: CamSettingsLike,
) -> list[tuple[np.ndarray, bool]]:
    result: list[tuple[np.ndarray, bool]] = []
    for polygon in _polygon_parts(geometry):
        result.append(
            (
                _oriented_ring(
                    polygon.exterior.coords,
                    exterior=True,
                    settings=settings,
                ),
                True,
            )
        )
        for interior in polygon.interiors:
            result.append(
                (
                    _oriented_ring(
                        interior.coords,
                        exterior=False,
                        settings=settings,
                    ),
                    False,
                )
            )
    return result


def _cut_tabbed_ring(
    moves: list[ToolpathMove],
    points: np.ndarray,
    depth: float,
    settings: CamSettingsLike,
) -> None:
    lengths = [
        hypot(float(b[0] - a[0]), float(b[1] - a[1]))
        for a, b in pairwise(points)
    ]
    perimeter = sum(lengths)
    if perimeter <= _EPS:
        return

    half_width = settings.tab_width_mm / 2.0
    centers = [
        perimeter * (index + 0.5) / settings.tab_count
        for index in range(settings.tab_count)
    ]
    intervals = [
        (max(0.0, center - half_width), min(perimeter, center + half_width))
        for center in centers
    ]
    tab_z = min(0.0, depth + settings.tab_height_mm)

    cumulative = 0.0
    for (start, end), segment_length in zip(pairwise(points), lengths, strict=True):
        if segment_length <= _EPS:
            continue
        segment_start = cumulative
        segment_end = cumulative + segment_length
        breaks = {segment_start, segment_end}
        for tab_start, tab_end in intervals:
            if segment_start < tab_start < segment_end:
                breaks.add(tab_start)
            if segment_start < tab_end < segment_end:
                breaks.add(tab_end)
        ordered = sorted(breaks)
        for range_start, range_end in pairwise(ordered):
            midpoint = (range_start + range_end) / 2.0
            z = (
                tab_z
                if any(a <= midpoint <= b for a, b in intervals)
                else depth
            )
            local_start = (range_start - segment_start) / segment_length
            local_end = (range_end - segment_start) / segment_length
            p0 = start + (end - start) * local_start
            p1 = start + (end - start) * local_end
            if abs(moves[-1].z_mm - z) > 1e-9:
                _cut(moves, p0[0], p0[1], z, settings)
            _cut(moves, p1[0], p1[1], z, settings)
        cumulative = segment_end


def geometry_profile(
    mesh: trimesh.Trimesh,
    cutter: Cutter,
    settings: CamSettingsLike,
    *,
    name: str = "Profile",
    offset_mode: str = "outside",
) -> Toolpath:
    regions = projected_regions(mesh)
    distance = cutter.radius_mm + settings.padding_mm
    if offset_mode == "outside":
        path_regions = regions.buffer(distance, join_style=2)
    elif offset_mode == "inside":
        path_regions = regions.buffer(-distance, join_style=2)
    elif offset_mode == "on":
        path_regions = (
            regions.buffer(settings.padding_mm, join_style=2)
            if settings.padding_mm > 0
            else regions
        )
    else:
        raise ValueError(f"Unsupported profile offset mode: {offset_mode}")
    if path_regions.is_empty:
        raise ValueError("Selected geometry is too small for this profile offset.")

    rings = _ring_paths(path_regions, settings)
    if not rings:
        raise ValueError("Selected geometry produced no profile contours.")
    target_z = _target_depth(mesh, settings)
    moves: list[ToolpathMove] = []
    previous_depth = 0.0

    for depth in _depth_passes(target_z, settings.max_stepdown_mm):
        for points, exterior in _order_tagged_paths(rings):
            start_index = _enter_depth(
                moves,
                points,
                depth,
                previous_depth,
                settings,
            )
            final_tab_pass = (
                settings.tabs_enabled
                and exterior
                and depth <= target_z + 1e-9
            )
            if final_tab_pass:
                _cut_tabbed_ring(moves, points, depth, settings)
            else:
                for point in points[start_index:]:
                    _cut(moves, point[0], point[1], depth, settings)
            last = moves[-1]
            _rapid(moves, last.x_mm, last.y_mm, settings.safe_z_mm)
        previous_depth = depth

    return Toolpath(
        name=name,
        operation="profile",
        cutter=cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )


def _link_is_safe(
    region: BaseGeometry,
    start: np.ndarray,
    end: np.ndarray,
) -> bool:
    link = LineString((start, end))
    return bool(region.buffer(1e-7).covers(link))


def _cut_path_with_smart_link(
    moves: list[ToolpathMove],
    points: np.ndarray,
    depth: float,
    region: BaseGeometry,
    settings: CamSettingsLike,
    current: np.ndarray | None,
) -> np.ndarray:
    start = points[0]
    if (
        current is not None
        and abs(moves[-1].z_mm - depth) <= 1e-9
        and _link_is_safe(region, current, start)
    ):
        if float(np.linalg.norm(start - current)) > _EPS:
            _cut(moves, start[0], start[1], depth, settings)
    else:
        _rapid(moves, start[0], start[1], settings.safe_z_mm)
        _plunge(moves, start[0], start[1], depth, settings)

    for point in points[1:]:
        _cut(moves, point[0], point[1], depth, settings)
    return points[-1]


def _scanline_segments(
    region: BaseGeometry,
    *,
    axis_y: bool,
    step: float,
) -> list[np.ndarray]:
    min_x, min_y, max_x, max_y = region.bounds
    low = min_x if axis_y else min_y
    high = max_x if axis_y else max_y
    values = list(np.arange(low, high + step * 0.5, step))
    if not values or values[-1] < high - 1e-9:
        values.append(high)

    paths: list[np.ndarray] = []
    reverse = False
    for value in values:
        if axis_y:
            scan = LineString(((value, min_y), (value, max_y)))
        else:
            scan = LineString(((min_x, value), (max_x, value)))
        clipped = region.intersection(scan)
        parts = _line_parts(clipped)
        parts.sort(
            key=lambda line: line.bounds[1 if axis_y else 0],
            reverse=reverse,
        )
        row: list[np.ndarray] = []
        for line in parts:
            points = np.asarray(line.coords, dtype=float)
            if len(points) < 2 or line.length <= _EPS:
                continue
            if reverse:
                points = points[::-1].copy()
            row.append(points)
        paths.extend(row)
        reverse = not reverse
    return paths


def geometry_pocket(
    mesh: trimesh.Trimesh,
    cutter: Cutter,
    settings: CamSettingsLike,
    *,
    name: str = "Pocket",
) -> Toolpath:
    regions = projected_regions(mesh)
    expanded = (
        regions.buffer(settings.padding_mm, join_style=2)
        if settings.padding_mm > 0
        else regions
    )
    work = expanded.buffer(-cutter.radius_mm, join_style=2)
    if work.is_empty:
        raise ValueError("Selected geometry is too small for the selected cutter.")

    target_z = _target_depth(mesh, settings)
    stepover = max(cutter.diameter_mm * settings.stepover_fraction, 0.05)
    strategy = _settings_value(settings.pocket_strategy)
    moves: list[ToolpathMove] = []

    for depth in _depth_passes(target_z, settings.max_stepdown_mm):
        current_point: np.ndarray | None = None
        if strategy == "offset":
            current_region = work
            iteration = 0
            while not current_region.is_empty:
                rings = [
                    points
                    for points, _exterior in _ring_paths(
                        current_region,
                        settings,
                    )
                ]
                for points in _order_paths(rings):
                    current_point = _cut_path_with_smart_link(
                        moves,
                        points,
                        depth,
                        work,
                        settings,
                        current_point,
                    )
                current_region = current_region.buffer(-stepover, join_style=2)
                iteration += 1
                if iteration > 10000:
                    raise RuntimeError("Pocket offset generation did not converge.")
        else:
            axis_y = strategy == "raster_y"
            paths = _scanline_segments(work, axis_y=axis_y, step=stepover)
            for points in paths:
                current_point = _cut_path_with_smart_link(
                    moves,
                    points,
                    depth,
                    work,
                    settings,
                    current_point,
                )

        if moves:
            last = moves[-1]
            _rapid(moves, last.x_mm, last.y_mm, settings.safe_z_mm)

    if not moves:
        raise ValueError("Selected geometry produced no pocket toolpath.")
    return Toolpath(
        name=name,
        operation="pocket",
        cutter=cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )


def geometry_engrave(
    mesh: trimesh.Trimesh,
    cutter: Cutter,
    settings: CamSettingsLike,
    *,
    depth_mm: float = -0.5,
    name: str = "Engrave",
) -> Toolpath:
    paths = _order_paths(engraving_paths(mesh))
    target_z = (
        _target_depth(mesh, settings, fallback_mm=depth_mm)
        if settings.overall_depth_mm is not None
        else min(-1e-4, float(depth_mm))
    )
    if (
        settings.usable_bit_length_mm is not None
        and abs(target_z) > settings.usable_bit_length_mm + 1e-9
    ):
        raise ValueError(
            f"Requested engraving depth {abs(target_z):.3f} mm exceeds the "
            f"usable bit length {settings.usable_bit_length_mm:.3f} mm."
        )

    moves: list[ToolpathMove] = []
    previous_depth = 0.0
    for depth in _depth_passes(target_z, settings.max_stepdown_mm):
        for points in paths:
            start_index = _enter_depth(
                moves,
                points,
                depth,
                previous_depth,
                settings,
            )
            for point in points[start_index:]:
                _cut(moves, point[0], point[1], depth, settings)
            last = moves[-1]
            _rapid(moves, last.x_mm, last.y_mm, settings.safe_z_mm)
        previous_depth = depth

    return Toolpath(
        name=name,
        operation="engrave",
        cutter=cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )


def _deepest_inset_radius(polygon: Polygon, upper: float) -> float:
    low = 0.0
    high = max(0.0, float(upper))
    for _iteration in range(28):
        middle = (low + high) / 2.0
        if middle <= _EPS:
            low = middle
            continue
        if polygon.buffer(-middle, join_style=2).is_empty:
            high = middle
        else:
            low = middle
    return low


def geometry_vcarve(
    mesh: trimesh.Trimesh,
    cutter: Cutter,
    settings: CamSettingsLike,
    *,
    name: str = "V-Carve",
) -> Toolpath:
    if cutter.tool_type not in {ToolType.V_BIT, ToolType.ENGRAVING_CONE}:
        raise ValueError("V-Carve requires a V-bit or engraving-cone cutter.")
    if cutter.angle_deg is None:
        raise ValueError("Selected V-carving cutter has no included angle.")

    regions = projected_regions(mesh)
    if settings.padding_mm > 0:
        regions = regions.buffer(settings.padding_mm, join_style=2)

    half_angle = radians(cutter.angle_deg / 2.0)
    slope = tan(half_angle)
    if slope <= _EPS or not isfinite(slope):
        raise ValueError("Selected V-bit angle cannot produce a valid V-carve.")

    tip_radius = cutter.tip_diameter_mm / 2.0
    cutter_depth = cutter.profile_height_mm(cutter.radius_mm)
    bounds = np.asarray(mesh.bounds, dtype=float)
    model_depth = max(0.0, float(bounds[1, 2] - bounds[0, 2]))
    if settings.overall_depth_mm is not None:
        max_depth = abs(float(settings.overall_depth_mm))
    elif model_depth > _EPS:
        max_depth = min(cutter_depth, model_depth)
    else:
        max_depth = cutter_depth
    if settings.usable_bit_length_mm is not None:
        max_depth = min(max_depth, float(settings.usable_bit_length_mm))
    max_depth = min(max_depth, cutter_depth)
    if max_depth <= _EPS:
        raise ValueError("No usable V-carve depth is available for this model/tool.")

    max_radius = min(
        cutter.radius_mm,
        tip_radius + max_depth * slope,
    )
    radial_step = max(
        0.05,
        cutter.diameter_mm
        * max(0.015, min(float(settings.finish_stepover_fraction), 0.04)),
    )
    start_radius = tip_radius + min(0.025, radial_step * 0.25)

    levels: set[float] = set()
    radius = start_radius
    while radius <= max_radius + 1e-9:
        levels.add(float(radius))
        radius += radial_step

    for polygon in _polygon_parts(regions):
        width = min(
            polygon.bounds[2] - polygon.bounds[0],
            polygon.bounds[3] - polygon.bounds[1],
        )
        deepest = _deepest_inset_radius(
            polygon,
            min(max_radius, max(0.0, width / 2.0)),
        )
        if deepest > tip_radius + _EPS:
            levels.add(float(deepest * 0.995))

    moves: list[ToolpathMove] = []
    for radius in sorted(levels):
        inset = regions.buffer(-radius, join_style=2)
        if inset.is_empty:
            continue
        depth = min(max_depth, max(0.0, (radius - tip_radius) / slope))
        if depth <= 1e-4:
            continue
        paths = [
            points
            for points, _exterior in _ring_paths(inset, settings)
        ]
        for points in _order_paths(paths):
            _rapid(moves, points[0, 0], points[0, 1], settings.safe_z_mm)
            _plunge(moves, points[0, 0], points[0, 1], -depth, settings)
            for point in points[1:]:
                _cut(moves, point[0], point[1], -depth, settings)
            last = moves[-1]
            _rapid(moves, last.x_mm, last.y_mm, settings.safe_z_mm)

    if not moves:
        raise ValueError(
            "Selected regions are too narrow for the selected V-bit tip/angle."
        )
    return Toolpath(
        name=name,
        operation="v_carve",
        cutter=cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )


def _ring_is_circular(points: np.ndarray) -> tuple[bool, tuple[float, float]]:
    polygon = Polygon(points)
    if polygon.is_empty or polygon.area <= _EPS or polygon.length <= _EPS:
        return False, (0.0, 0.0)
    min_x, min_y, max_x, max_y = polygon.bounds
    width = max_x - min_x
    height = max_y - min_y
    if min(width, height) <= _EPS:
        return False, (0.0, 0.0)
    aspect = max(width, height) / min(width, height)
    circularity = 4.0 * pi * polygon.area / (polygon.length * polygon.length)
    center = polygon.centroid
    return (
        aspect <= 1.18 and circularity >= 0.82,
        (float(center.x), float(center.y)),
    )


def _drill_centers(regions: BaseGeometry) -> list[tuple[float, float]]:
    centers: list[tuple[float, float]] = []
    for polygon in _polygon_parts(regions):
        candidates = [np.asarray(polygon.exterior.coords, dtype=float)]
        candidates.extend(
            np.asarray(interior.coords, dtype=float)
            for interior in polygon.interiors
        )
        for points in candidates:
            circular, center = _ring_is_circular(points)
            if not circular:
                continue
            if not any(hypot(center[0] - x, center[1] - y) < 0.01 for x, y in centers):
                centers.append(center)
    return centers


def geometry_drill(
    mesh: trimesh.Trimesh,
    cutter: Cutter,
    settings: CamSettingsLike,
    *,
    name: str = "Drill",
) -> Toolpath:
    centers = _drill_centers(projected_regions(mesh))
    if not centers:
        raise ValueError(
            "Drill found no circular projected features. Select circular "
            "geometry or holes instead of drilling the model bounding-box center."
        )

    target_z = _target_depth(mesh, settings)
    ordered: list[tuple[float, float]] = [centers.pop(0)]
    while centers:
        x, y = ordered[-1]
        index = min(
            range(len(centers)),
            key=lambda i: hypot(centers[i][0] - x, centers[i][1] - y),
        )
        ordered.append(centers.pop(index))

    moves: list[ToolpathMove] = []
    for x, y in ordered:
        _rapid(moves, x, y, settings.safe_z_mm)
        for depth in _depth_passes(target_z, settings.max_stepdown_mm):
            _plunge(moves, x, y, depth, settings)
            _rapid(moves, x, y, settings.safe_z_mm)

    return Toolpath(
        name=name,
        operation="drill",
        cutter=cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )
