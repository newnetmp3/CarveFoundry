"""Geometric snapping for retained editable vector paths."""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, floor, hypot, isfinite, pi, sin

from shapely.geometry import GeometryCollection, LineString, MultiPoint, Point

from carvefoundry.core.project import ProjectItem
from carvefoundry.core.vector_path import (
    sampled_world_points,
    segment_world_arc_center,
    segment_world_point,
)

_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class VectorSnapCandidate:
    kind: str
    point_xy: tuple[float, float]
    item_id: str | None = None
    node_index: int | None = None
    segment_index: int | None = None

    def distance_to(self, xy: tuple[float, float]) -> float:
        return hypot(self.point_xy[0] - xy[0], self.point_xy[1] - xy[1])


def _intersection_points(geometry) -> list[tuple[float, float]]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Point):
        return [(float(geometry.x), float(geometry.y))]
    if isinstance(geometry, MultiPoint):
        return [(float(point.x), float(point.y)) for point in geometry.geoms]
    if isinstance(geometry, GeometryCollection):
        result: list[tuple[float, float]] = []
        for part in geometry.geoms:
            result.extend(_intersection_points(part))
        return result
    return []


def grid_snap_candidate(
    query_xy: tuple[float, float],
    spacing_mm: float,
    tolerance_mm: float,
    *,
    origin_xy: tuple[float, float] = (0.0, 0.0),
) -> VectorSnapCandidate | None:
    """Find the closest stock-relative grid intersection within tolerance."""
    if (
        not isfinite(spacing_mm) or spacing_mm <= 0
        or not isfinite(tolerance_mm) or tolerance_mm <= 0
        or not all(isfinite(float(v)) for v in (*query_xy, *origin_xy))
    ):
        raise ValueError("Grid spacing, tolerance and coordinates must be finite.")
    snapped = tuple(
        origin + floor((coordinate - origin) / spacing_mm + 0.5) * spacing_mm
        for coordinate, origin in zip(query_xy, origin_xy, strict=True)
    )
    candidate = VectorSnapCandidate("grid", snapped)
    return candidate if candidate.distance_to(query_xy) <= tolerance_mm else None


def constrain_angle(
    query_xy: tuple[float, float],
    anchor_xy: tuple[float, float],
    increment_degrees: float = 45.0,
) -> tuple[float, float]:
    """Constrain handle direction about its anchor to nearest angular step."""
    if (
        not isfinite(increment_degrees) or not 0 < increment_degrees <= 180
        or not all(isfinite(float(v)) for v in (*query_xy, *anchor_xy))
    ):
        raise ValueError("Angle constraint requires finite coordinates and a valid step.")
    dx = query_xy[0] - anchor_xy[0]
    dy = query_xy[1] - anchor_xy[1]
    radius = hypot(dx, dy)
    if radius <= _EPS:
        return (float(anchor_xy[0]), float(anchor_xy[1]))
    step = increment_degrees * pi / 180.0
    angle = floor(atan2(dy, dx) / step + 0.5) * step
    return (
        anchor_xy[0] + radius * cos(angle),
        anchor_xy[1] + radius * sin(angle),
    )


def adjacent_control_reference(
    item: ProjectItem,
    segment_index: int,
    control_index: int,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """World-space reference tangent from the segment adjoining a cubic handle.

    Control 1 uses the preceding segment's ending tangent; control 2 uses
    the following segment's starting tangent. No reference exists at an open
    path boundary. Derivative direction is sampled close to the endpoint,
    preserving transforms and analytic curve shape.
    """
    path = item.vector_path
    if (
        path is None or control_index not in (1, 2)
        or not 0 <= segment_index < path.segment_count
        or path.resolved_segments()[segment_index].kind != "cubic"
    ):
        return None
    count = path.segment_count
    if control_index == 1:
        neighbor = segment_index - 1
        if neighbor < 0:
            if not path.closed:
                return None
            neighbor = count - 1
        if neighbor == segment_index:
            return None
        anchor = segment_world_point(item, segment_index, 0.0)
        near = segment_world_point(item, neighbor, 1.0 - 1e-4)
        end = segment_world_point(item, neighbor, 1.0)
        direction = (end[0] - near[0], end[1] - near[1])
    else:
        neighbor = segment_index + 1
        if neighbor >= count:
            if not path.closed:
                return None
            neighbor = 0
        if neighbor == segment_index:
            return None
        anchor = segment_world_point(item, segment_index, 1.0)
        start = segment_world_point(item, neighbor, 0.0)
        near = segment_world_point(item, neighbor, 1e-4)
        direction = (near[0] - start[0], near[1] - start[1])
    if hypot(*direction) <= _EPS:
        return None
    return anchor, direction


def directional_snap_candidate(
    query_xy: tuple[float, float],
    origin_xy: tuple[float, float],
    direction_xy: tuple[float, float],
    tolerance_mm: float,
    *,
    perpendicular: bool = False,
) -> VectorSnapCandidate | None:
    """Project onto an infinite tangent or normal line through an anchor.

    This primitive takes an explicit reference direction. Callers must select
    a meaningful anchor and segment tangent; it does not infer curve tangents.
    """
    values = (*query_xy, *origin_xy, *direction_xy, tolerance_mm)
    if not all(isfinite(float(value)) for value in values) or tolerance_mm <= 0:
        raise ValueError("Directional snap coordinates and tolerance must be finite.")
    dx, dy = (float(value) for value in direction_xy)
    magnitude = hypot(dx, dy)
    if magnitude <= _EPS:
        raise ValueError("Directional snap requires a nonzero reference direction.")
    dx, dy = dx / magnitude, dy / magnitude
    if perpendicular:
        dx, dy = -dy, dx
    displacement_x = query_xy[0] - origin_xy[0]
    displacement_y = query_xy[1] - origin_xy[1]
    distance_along = displacement_x * dx + displacement_y * dy
    point = (
        origin_xy[0] + distance_along * dx,
        origin_xy[1] + distance_along * dy,
    )
    candidate = VectorSnapCandidate(
        "perpendicular" if perpendicular else "tangent", point,
    )
    return candidate if candidate.distance_to(query_xy) <= tolerance_mm else None


def vector_snap_candidates(
    items: list[ProjectItem],
    query_xy: tuple[float, float],
    tolerance_mm: float,
    *,
    exclude_item_id: str | None = None,
    exclude_node_index: int | None = None,
) -> list[VectorSnapCandidate]:
    """Return nearby node, midpoint, arc-center and path-intersection snaps."""

    if (
        not isfinite(tolerance_mm)
        or tolerance_mm <= 0
        or not all(isfinite(value) for value in query_xy)
    ):
        raise ValueError("Snap query and tolerance must be finite and positive.")

    candidates: list[VectorSnapCandidate] = []
    linework: list[tuple[ProjectItem, LineString]] = []

    for item in items:
        path = item.vector_path
        if not item.visible or path is None or item.mesh is None:
            continue

        world_nodes = sampled_world_points(item)
        sampled_xy = [(float(point[0]), float(point[1])) for point in world_nodes]
        if path.closed and sampled_xy:
            sampled_xy.append(sampled_xy[0])
        if len(sampled_xy) >= 2:
            linework.append((item, LineString(sampled_xy)))

        anchor_world = [
            segment_world_point(item, index, 0.0)
            for index in range(path.segment_count)
        ]
        if not path.closed:
            anchor_world.append(segment_world_point(item, path.segment_count - 1, 1.0))

        for index, point in enumerate(anchor_world):
            if (
                item.item_id == exclude_item_id
                and index == exclude_node_index
            ):
                continue
            candidate = VectorSnapCandidate(
                "node",
                point,
                item_id=item.item_id,
                node_index=index,
            )
            if candidate.distance_to(query_xy) <= tolerance_mm + _EPS:
                candidates.append(candidate)

        for index in range(path.segment_count):
            midpoint = VectorSnapCandidate(
                "midpoint",
                segment_world_point(item, index, 0.5),
                item_id=item.item_id,
                segment_index=index,
            )
            if midpoint.distance_to(query_xy) <= tolerance_mm + _EPS:
                candidates.append(midpoint)
            center = segment_world_arc_center(item, index)
            if center is not None:
                center_candidate = VectorSnapCandidate(
                    "center",
                    center,
                    item_id=item.item_id,
                    segment_index=index,
                )
                if center_candidate.distance_to(query_xy) <= tolerance_mm + _EPS:
                    candidates.append(center_candidate)

    for left_index, (left_item, left_line) in enumerate(linework):
        for right_item, right_line in linework[left_index + 1:]:
            intersection = left_line.intersection(right_line)
            for point in _intersection_points(intersection):
                candidate = VectorSnapCandidate(
                    "intersection",
                    point,
                    item_id=left_item.item_id,
                )
                if candidate.distance_to(query_xy) <= tolerance_mm + _EPS:
                    candidates.append(candidate)

    priority = {
        "node": 0,
        "intersection": 1,
        "center": 2,
        "midpoint": 3,
    }
    candidates.sort(
        key=lambda candidate: (
            candidate.distance_to(query_xy),
            priority.get(candidate.kind, 99),
        )
    )
    return candidates


def nearest_vector_snap(
    items: list[ProjectItem],
    query_xy: tuple[float, float],
    tolerance_mm: float,
    *,
    exclude_item_id: str | None = None,
    exclude_node_index: int | None = None,
) -> VectorSnapCandidate | None:
    candidates = vector_snap_candidates(
        items,
        query_xy,
        tolerance_mm,
        exclude_item_id=exclude_item_id,
        exclude_node_index=exclude_node_index,
    )
    return candidates[0] if candidates else None
