"""Retained editable CNC vector paths independent of cutter-facing meshes.

Anchors and curve controls are stored in each item's local/model XY millimeter
space. A path can contain line, circular-arc (CAD bulge) and cubic Bezier
segments. Curves are deterministically flattened only at rendering/CAM
boundaries; the editable source remains analytic.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import acos, atan, atan2, ceil, cos, degrees, hypot, isfinite, pi, sin, tan

import numpy as np

from .primitives import polyline_mesh
from .project import ProjectItem

MAX_VECTOR_NODES = 12_000
MAX_CURVE_SAMPLES = 200_000
DEFAULT_CURVE_TOLERANCE_MM = 0.02
_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class VectorSegment:
    """One segment from anchor i to anchor i+1.

    Arc uses the common CAD bulge definition tan(sweep / 4). Positive bulge is
    counter-clockwise. Cubic controls are absolute local XY points.
    """

    kind: str = "line"
    control1_xy: tuple[float, float] | None = None
    control2_xy: tuple[float, float] | None = None
    bulge: float = 0.0

    def validate(self) -> None:
        if self.kind not in {"line", "arc", "cubic"}:
            raise ValueError(f"Unsupported vector segment kind: {self.kind}")
        values = []
        for point in (self.control1_xy, self.control2_xy):
            if point is not None:
                if len(point) != 2:
                    raise ValueError("Vector controls must be XY pairs.")
                values.extend(point)
        if not all(isfinite(float(value)) for value in values):
            raise ValueError("Vector control coordinates must be finite.")
        if not isfinite(self.bulge):
            raise ValueError("Arc bulge must be finite.")
        if self.kind == "cubic":
            if self.control1_xy is None or self.control2_xy is None:
                raise ValueError("Cubic Bezier segments need two control points.")
        elif self.control1_xy is not None or self.control2_xy is not None:
            raise ValueError("Only cubic Bezier segments use control points.")
        if self.kind == "arc":
            if abs(self.bulge) <= _EPS:
                raise ValueError("Circular arc sweep cannot be zero.")
            sweep = abs(4.0 * atan(self.bulge))
            if sweep >= 2.0 * pi - 1e-7:
                raise ValueError("A single circular arc must be less than 360 degrees.")
        elif abs(self.bulge) > _EPS:
            raise ValueError("Only circular arc segments use bulge.")

    @classmethod
    def line(cls) -> VectorSegment:
        return cls("line")

    @classmethod
    def arc(cls, sweep_degrees: float) -> VectorSegment:
        if not isfinite(sweep_degrees) or abs(sweep_degrees) < 0.01:
            raise ValueError("Arc sweep must be a non-zero finite angle.")
        if abs(sweep_degrees) >= 360.0:
            raise ValueError("A single circular arc must be less than 360 degrees.")
        segment = cls("arc", bulge=tan(np.deg2rad(sweep_degrees) / 4.0))
        segment.validate()
        return segment

    @classmethod
    def cubic(
        cls,
        control1_xy: tuple[float, float],
        control2_xy: tuple[float, float],
    ) -> VectorSegment:
        segment = cls(
            "cubic",
            (float(control1_xy[0]), float(control1_xy[1])),
            (float(control2_xy[0]), float(control2_xy[1])),
        )
        segment.validate()
        return segment


@dataclass(frozen=True, slots=True)
class VectorPath:
    points_xy: tuple[tuple[float, float], ...]
    width_mm: float = 2.0
    depth_mm: float = 1.0
    closed: bool = False
    segments: tuple[VectorSegment, ...] | None = None

    @property
    def segment_count(self) -> int:
        return len(self.points_xy) if self.closed else max(0, len(self.points_xy) - 1)

    def resolved_segments(self) -> tuple[VectorSegment, ...]:
        if self.segments is None:
            return tuple(VectorSegment.line() for _ in range(self.segment_count))
        return self.segments

    def validate(self) -> None:
        points = self.points_xy
        if not 2 <= len(points) <= MAX_VECTOR_NODES:
            raise ValueError("An editable path needs 2-12,000 nodes.")
        if self.closed and len(points) < 3:
            raise ValueError("A closed editable path needs at least three nodes.")
        if not isfinite(self.width_mm) or self.width_mm <= 0:
            raise ValueError("Vector stroke width must be positive and finite.")
        if not isfinite(self.depth_mm) or self.depth_mm <= 0:
            raise ValueError("Vector stroke depth must be positive and finite.")
        if not all(isfinite(v) for pair in points for v in pair):
            raise ValueError("Vector node coordinates must be finite.")
        segments = self.resolved_segments()
        if len(segments) != self.segment_count:
            raise ValueError(
                f"Editable path needs exactly {self.segment_count} segment definitions."
            )
        for segment in segments:
            segment.validate()
        if not any(
            hypot(
                points[index][0] - points[(index + 1) % len(points)][0],
                points[index][1] - points[(index + 1) % len(points)][1],
            ) > _EPS
            for index in range(self.segment_count)
        ):
            raise ValueError("Editable path has no usable segments.")

    def mesh_asset(self):
        self.validate()
        vertices = list(sampled_points_xy(self))
        if self.closed and vertices[-1] != vertices[0]:
            vertices.append(vertices[0])
        return polyline_mesh(
            vertices,
            width_mm=self.width_mm,
            depth_mm=self.depth_mm,
        )


def _xy(value) -> np.ndarray:
    return np.asarray(value, dtype=float)


def _arc_geometry(
    start: tuple[float, float],
    end: tuple[float, float],
    bulge: float,
) -> tuple[np.ndarray, float, float, float]:
    p0 = _xy(start)
    p1 = _xy(end)
    chord = p1 - p0
    length = float(np.linalg.norm(chord))
    if length <= _EPS:
        raise ValueError("Arc endpoints must not coincide.")
    sweep = 4.0 * atan(float(bulge))
    normal = np.array((-chord[1], chord[0]), dtype=float) / length
    center_offset = length * (1.0 - bulge * bulge) / (4.0 * bulge)
    center = (p0 + p1) / 2.0 + normal * center_offset
    radius = float(np.linalg.norm(p0 - center))
    start_angle = atan2(p0[1] - center[1], p0[0] - center[0])
    return center, radius, start_angle, sweep


def segment_point(
    path: VectorPath,
    segment_index: int,
    fraction: float,
) -> tuple[float, float]:
    path.validate()
    if not 0 <= segment_index < path.segment_count:
        raise IndexError("Vector segment index out of range.")
    t = max(0.0, min(1.0, float(fraction)))
    p0 = _xy(path.points_xy[segment_index])
    p3 = _xy(path.points_xy[(segment_index + 1) % len(path.points_xy)])
    segment = path.resolved_segments()[segment_index]
    if segment.kind == "line":
        point = p0 + (p3 - p0) * t
    elif segment.kind == "arc":
        center, radius, start_angle, sweep = _arc_geometry(
            tuple(p0), tuple(p3), segment.bulge,
        )
        angle = start_angle + sweep * t
        point = center + radius * np.array((cos(angle), sin(angle)))
    else:
        p1 = _xy(segment.control1_xy)
        p2 = _xy(segment.control2_xy)
        u = 1.0 - t
        point = (
            u**3 * p0
            + 3.0 * u * u * t * p1
            + 3.0 * u * t * t * p2
            + t**3 * p3
        )
    return (float(point[0]), float(point[1]))


def arc_center(path: VectorPath, segment_index: int) -> tuple[float, float] | None:
    segment = path.resolved_segments()[segment_index]
    if segment.kind != "arc":
        return None
    center, _radius, _start, _sweep = _arc_geometry(
        path.points_xy[segment_index],
        path.points_xy[(segment_index + 1) % len(path.points_xy)],
        segment.bulge,
    )
    return (float(center[0]), float(center[1]))


def arc_sweep_degrees(path: VectorPath, segment_index: int) -> float | None:
    segment = path.resolved_segments()[segment_index]
    if segment.kind != "arc":
        return None
    return degrees(4.0 * atan(segment.bulge))


def _distance_to_chord(point: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    chord = b - a
    length = float(np.linalg.norm(chord))
    if length <= _EPS:
        return float(np.linalg.norm(point - a))
    delta = point - a
    cross_z = chord[0] * delta[1] - chord[1] * delta[0]
    return abs(float(cross_z)) / length


def _flatten_cubic(
    p0: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    p3: np.ndarray,
    tolerance_mm: float,
    *,
    depth: int = 0,
) -> list[np.ndarray]:
    flatness = max(
        _distance_to_chord(p1, p0, p3),
        _distance_to_chord(p2, p0, p3),
    )
    if flatness <= tolerance_mm or depth >= 18:
        return [p3]
    p01 = (p0 + p1) / 2.0
    p12 = (p1 + p2) / 2.0
    p23 = (p2 + p3) / 2.0
    p012 = (p01 + p12) / 2.0
    p123 = (p12 + p23) / 2.0
    middle = (p012 + p123) / 2.0
    return (
        _flatten_cubic(p0, p01, p012, middle, tolerance_mm, depth=depth + 1)
        + _flatten_cubic(middle, p123, p23, p3, tolerance_mm, depth=depth + 1)
    )


def _sample_segment(
    path: VectorPath,
    index: int,
    tolerance_mm: float,
) -> list[tuple[float, float]]:
    segment = path.resolved_segments()[index]
    p0 = _xy(path.points_xy[index])
    p3 = _xy(path.points_xy[(index + 1) % len(path.points_xy)])
    if segment.kind == "line":
        return [(float(p3[0]), float(p3[1]))]
    if segment.kind == "cubic":
        result = _flatten_cubic(
            p0,
            _xy(segment.control1_xy),
            _xy(segment.control2_xy),
            p3,
            tolerance_mm,
        )
        return [(float(point[0]), float(point[1])) for point in result]

    center, radius, start_angle, sweep = _arc_geometry(
        tuple(p0), tuple(p3), segment.bulge,
    )
    if radius <= tolerance_mm:
        steps = max(2, ceil(abs(sweep) / (pi / 8.0)))
    else:
        ratio = max(-1.0, min(1.0, 1.0 - tolerance_mm / radius))
        max_step = max(1e-4, 2.0 * acos(ratio))
        steps = max(2, ceil(abs(sweep) / max_step))
    steps = min(steps, 8192)
    result = []
    for sample in range(1, steps + 1):
        angle = start_angle + sweep * sample / steps
        point = center + radius * np.array((cos(angle), sin(angle)))
        result.append((float(point[0]), float(point[1])))
    result[-1] = (float(p3[0]), float(p3[1]))
    return result


def sampled_points_xy(
    path: VectorPath,
    *,
    tolerance_mm: float = DEFAULT_CURVE_TOLERANCE_MM,
) -> tuple[tuple[float, float], ...]:
    path.validate()
    if not isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError("Curve tolerance must be positive and finite.")
    result = [tuple(float(v) for v in path.points_xy[0])]
    for index in range(path.segment_count):
        result.extend(_sample_segment(path, index, tolerance_mm))
        if len(result) > MAX_CURVE_SAMPLES:
            raise ValueError("Editable path exceeds the curve sampling limit.")
    if path.closed and result[-1] == result[0]:
        result.pop()
    return tuple(result)


def _canonical_segments(
    segments: list[VectorSegment] | tuple[VectorSegment, ...],
) -> tuple[VectorSegment, ...] | None:
    resolved = tuple(segments)
    if all(segment == VectorSegment.line() for segment in resolved):
        return None
    return resolved


def move_node(path: VectorPath, index: int, xy: tuple[float, float]) -> VectorPath:
    if not 0 <= index < len(path.points_xy):
        raise IndexError("Vector node index out of range.")
    points = list(path.points_xy)
    points[index] = (float(xy[0]), float(xy[1]))
    edited = replace(path, points_xy=tuple(points))
    edited.validate()
    return edited


def set_segment(
    path: VectorPath,
    index: int,
    segment: VectorSegment,
) -> VectorPath:
    if not 0 <= index < path.segment_count:
        raise IndexError("Vector segment index out of range.")
    segment.validate()
    segments = list(path.resolved_segments())
    segments[index] = segment
    edited = replace(path, segments=_canonical_segments(segments))
    edited.validate()
    return edited


def _split_cubic(
    p0: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
    p3: np.ndarray,
) -> tuple[np.ndarray, VectorSegment, VectorSegment]:
    p01 = (p0 + p1) / 2.0
    p12 = (p1 + p2) / 2.0
    p23 = (p2 + p3) / 2.0
    p012 = (p01 + p12) / 2.0
    p123 = (p12 + p23) / 2.0
    middle = (p012 + p123) / 2.0
    left = VectorSegment.cubic(tuple(p01), tuple(p012))
    right = VectorSegment.cubic(tuple(p123), tuple(p23))
    return middle, left, right


def insert_node(path: VectorPath, segment: int) -> VectorPath:
    """Split a segment exactly at its parametric midpoint."""
    if not 0 <= segment < path.segment_count:
        raise IndexError("Vector segment index out of range.")
    if len(path.points_xy) >= MAX_VECTOR_NODES:
        raise ValueError("Vector node limit reached.")
    current = path.resolved_segments()[segment]
    p0 = _xy(path.points_xy[segment])
    p3 = _xy(path.points_xy[(segment + 1) % len(path.points_xy)])
    if current.kind == "cubic":
        middle, left, right = _split_cubic(
            p0,
            _xy(current.control1_xy),
            _xy(current.control2_xy),
            p3,
        )
    else:
        middle = _xy(segment_point(path, segment, 0.5))
        if current.kind == "arc":
            half_sweep = 2.0 * atan(current.bulge)
            half = VectorSegment("arc", bulge=tan(half_sweep / 4.0))
            left = half
            right = half
        else:
            left = VectorSegment.line()
            right = VectorSegment.line()

    points = list(path.points_xy)
    points.insert(segment + 1, (float(middle[0]), float(middle[1])))
    segments = list(path.resolved_segments())
    segments[segment:segment + 1] = [left, right]
    edited = replace(
        path,
        points_xy=tuple(points),
        segments=_canonical_segments(segments),
    )
    edited.validate()
    return edited


def remove_node(path: VectorPath, index: int) -> VectorPath:
    if not 0 <= index < len(path.points_xy):
        raise IndexError("Vector node index out of range.")
    if len(path.points_xy) <= (3 if path.closed else 2):
        raise ValueError("Cannot remove the last required nodes.")

    old_points = list(path.points_xy)
    old_segments = list(path.resolved_segments())
    last_index = len(old_points) - 1
    if path.closed or index not in {0, last_index}:
        incoming = (index - 1) % len(old_segments)
        outgoing = index % len(old_segments)
        if (
            old_segments[incoming].kind != "line"
            or old_segments[outgoing].kind != "line"
        ):
            raise ValueError(
                "Convert adjacent curve segments to lines before deleting this node."
            )

    remaining_old_indices = [
        old_index
        for old_index in range(len(old_points))
        if old_index != index
    ]
    points = [old_points[old_index] for old_index in remaining_old_indices]
    segment_count = len(points) if path.closed else len(points) - 1
    segments: list[VectorSegment] = []
    for new_index in range(segment_count):
        start_old = remaining_old_indices[new_index]
        end_old = remaining_old_indices[
            (new_index + 1) % len(remaining_old_indices)
        ]
        expected_end = (start_old + 1) % len(old_points)
        if end_old == expected_end:
            segments.append(old_segments[start_old])
        else:
            segments.append(VectorSegment.line())

    edited = replace(
        path,
        points_xy=tuple(points),
        segments=_canonical_segments(segments),
    )
    edited.validate()
    return edited

def _reverse_segment(segment: VectorSegment) -> VectorSegment:
    if segment.kind == "line":
        return VectorSegment.line()
    if segment.kind == "arc":
        return VectorSegment("arc", bulge=-segment.bulge)
    return VectorSegment.cubic(
        segment.control2_xy,
        segment.control1_xy,
    )


def reverse_path(path: VectorPath) -> VectorPath:
    """Reverse anchor order while preserving exact analytic segment geometry."""

    path.validate()
    points = tuple(reversed(path.points_xy))
    segments = path.resolved_segments()
    if path.closed:
        count = len(segments)
        reversed_segments = tuple(
            _reverse_segment(segments[(count - 2 - index) % count])
            for index in range(count)
        )
    else:
        reversed_segments = tuple(
            _reverse_segment(segment)
            for segment in reversed(segments)
        )
    result = replace(
        path,
        points_xy=points,
        segments=_canonical_segments(reversed_segments),
    )
    result.validate()
    return result


def close_path(path: VectorPath) -> VectorPath:
    """Close an open contour with one explicit straight segment."""

    path.validate()
    if path.closed:
        raise ValueError("Vector path is already closed.")
    if len(path.points_xy) < 3:
        raise ValueError("Closing a vector path requires at least three anchors.")
    segments = list(path.resolved_segments())
    segments.append(VectorSegment.line())
    result = replace(
        path,
        closed=True,
        segments=_canonical_segments(segments),
    )
    result.validate()
    return result


def open_path_at_node(path: VectorPath, node_index: int) -> VectorPath:
    """Open a closed contour at *node_index*, preserving all other segments."""

    path.validate()
    if not path.closed:
        raise ValueError("Vector path is already open.")
    count = len(path.points_xy)
    if not 0 <= node_index < count:
        raise IndexError("Vector node index out of range.")

    points = tuple(
        path.points_xy[(node_index + offset) % count]
        for offset in range(count)
    )
    segments = tuple(
        path.resolved_segments()[(node_index + offset) % count]
        for offset in range(count - 1)
    )
    result = replace(
        path,
        points_xy=points,
        closed=False,
        segments=_canonical_segments(segments),
    )
    result.validate()
    return result


def split_path_at_node(
    path: VectorPath,
    node_index: int,
) -> tuple[VectorPath, VectorPath]:
    """Split one open path at an interior anchor into two independent paths."""

    path.validate()
    if path.closed:
        raise ValueError("Open a closed contour before splitting it.")
    if not 0 < node_index < len(path.points_xy) - 1:
        raise ValueError("Split requires an interior vector node.")

    segments = path.resolved_segments()
    left = replace(
        path,
        points_xy=tuple(path.points_xy[:node_index + 1]),
        segments=_canonical_segments(segments[:node_index]),
    )
    right = replace(
        path,
        points_xy=tuple(path.points_xy[node_index:]),
        segments=_canonical_segments(segments[node_index:]),
    )
    left.validate()
    right.validate()
    return left, right


def join_paths(
    first: VectorPath,
    second: VectorPath,
    *,
    first_endpoint: str = "end",
    second_endpoint: str = "start",
    max_gap_mm: float = 1.0,
) -> VectorPath:
    """Join two compatible open paths at selected endpoints.

    Geometry is never silently flattened. If endpoint coordinates differ, a
    straight connector is inserted, provided the gap is within *max_gap_mm*.
    """

    first.validate()
    second.validate()
    if first.closed or second.closed:
        raise ValueError("Only open vector paths can be joined.")
    if first_endpoint not in {"start", "end"}:
        raise ValueError("First endpoint must be 'start' or 'end'.")
    if second_endpoint not in {"start", "end"}:
        raise ValueError("Second endpoint must be 'start' or 'end'.")
    if (
        abs(first.width_mm - second.width_mm) > 1e-7
        or abs(first.depth_mm - second.depth_mm) > 1e-7
    ):
        raise ValueError("Joined paths must use the same stroke width and depth.")
    if not isfinite(max_gap_mm) or max_gap_mm < 0:
        raise ValueError("Join tolerance must be finite and non-negative.")

    left = reverse_path(first) if first_endpoint == "start" else first
    right = reverse_path(second) if second_endpoint == "end" else second
    left_end = left.points_xy[-1]
    right_start = right.points_xy[0]
    gap = hypot(
        left_end[0] - right_start[0],
        left_end[1] - right_start[1],
    )
    if gap > max_gap_mm + _EPS:
        raise ValueError(
            f"Nearest vector endpoints are {gap:.3f} mm apart, beyond the "
            f"{max_gap_mm:.3f} mm join tolerance."
        )

    points = list(left.points_xy)
    segments = list(left.resolved_segments())
    if gap <= _EPS:
        points.extend(right.points_xy[1:])
    else:
        segments.append(VectorSegment.line())
        points.extend(right.points_xy)
    segments.extend(right.resolved_segments())

    result = VectorPath(
        points_xy=tuple(points),
        width_mm=left.width_mm,
        depth_mm=left.depth_mm,
        closed=False,
        segments=_canonical_segments(segments),
    )
    result.validate()
    return result


def apply_vector_edit(item: ProjectItem, path: VectorPath) -> None:
    """Commit a validated fresh mesh, preserving the item's actual transform."""
    if item.vector_path is None:
        raise ValueError("Selected model has no retained editable path nodes.")
    if item.source_units.value != "mm":
        raise ValueError("Editable pen source units must remain millimeters.")
    mesh = path.mesh_asset()
    item.mesh = mesh
    item.source_path = None
    item.vector_path = path


def _local_points_to_world(
    item: ProjectItem,
    points_xy: tuple[tuple[float, float], ...] | list[tuple[float, float]],
) -> np.ndarray:
    if item.vector_path is None or item.mesh is None:
        raise ValueError("Selected object has no editable vector mesh.")
    points = np.asarray(points_xy, dtype=float)
    local = np.column_stack((points, np.zeros(len(points))))
    bounds = np.asarray(item.mesh.mesh.bounds, dtype=float)
    pivot = tuple(float(value) for value in bounds.mean(axis=0))
    return item.transform.apply_points(local, pivot=pivot)


def vector_path_in_world_xy(item: ProjectItem) -> VectorPath:
    """Bake a planar retained path into world XY without flattening curves.

    Circular arcs remain analytic only under uniform positive XY scale. X/Y
    tilt and non-uniform XY scale would turn circles into non-planar/elliptic
    geometry, so callers must resolve those transforms before topology joins.
    """

    path = item.vector_path
    if path is None or item.mesh is None:
        raise ValueError("Object has no editable vector path.")
    if item.source_units.value != "mm":
        raise ValueError("Editable vector joins require millimeter source units.")
    if any(abs(float(value)) > 1e-7 for value in item.transform.rotation_deg[:2]):
        raise ValueError("Apply or reset X/Y tilt before joining vector paths.")
    sx, sy, sz = (float(value) for value in item.transform.scale_xyz)
    if abs(sx - sy) > 1e-7:
        raise ValueError("Apply non-uniform XY scale before joining vector paths.")
    if abs(sz - 1.0) > 1e-7:
        raise ValueError("Apply Z scale before joining vector paths.")

    anchors = _local_points_to_world(item, list(path.points_xy))
    segments: list[VectorSegment] = []
    for segment in path.resolved_segments():
        if segment.kind == "line":
            segments.append(VectorSegment.line())
        elif segment.kind == "arc":
            segments.append(segment)
        else:
            controls = _local_points_to_world(
                item,
                [segment.control1_xy, segment.control2_xy],
            )
            segments.append(
                VectorSegment.cubic(
                    (float(controls[0, 0]), float(controls[0, 1])),
                    (float(controls[1, 0]), float(controls[1, 1])),
                )
            )

    result = VectorPath(
        points_xy=tuple(
            (float(point[0]), float(point[1]))
            for point in anchors
        ),
        width_mm=path.width_mm * sx,
        depth_mm=path.depth_mm,
        closed=path.closed,
        segments=_canonical_segments(segments),
    )
    result.validate()
    return result


def node_world_points(item: ProjectItem) -> np.ndarray:
    if item.vector_path is None:
        raise ValueError("Selected object has no editable vector mesh.")
    return _local_points_to_world(item, list(item.vector_path.points_xy))


def sampled_world_points(
    item: ProjectItem,
    *,
    tolerance_mm: float = DEFAULT_CURVE_TOLERANCE_MM,
) -> np.ndarray:
    if item.vector_path is None:
        raise ValueError("Selected object has no editable vector path.")
    return _local_points_to_world(
        item,
        list(sampled_points_xy(item.vector_path, tolerance_mm=tolerance_mm)),
    )


def segment_world_point(
    item: ProjectItem,
    segment_index: int,
    fraction: float,
) -> tuple[float, float]:
    if item.vector_path is None:
        raise ValueError("Selected object has no editable vector path.")
    point = segment_point(item.vector_path, segment_index, fraction)
    world = _local_points_to_world(item, [point])[0]
    return (float(world[0]), float(world[1]))


def segment_world_controls(
    item: ProjectItem,
    segment_index: int,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    if item.vector_path is None:
        raise ValueError("Selected object has no editable vector path.")
    segment = item.vector_path.resolved_segments()[segment_index]
    if segment.kind != "cubic":
        return None
    world = _local_points_to_world(
        item,
        [segment.control1_xy, segment.control2_xy],
    )
    return (
        (float(world[0, 0]), float(world[0, 1])),
        (float(world[1, 0]), float(world[1, 1])),
    )


def segment_world_arc_center(
    item: ProjectItem,
    segment_index: int,
) -> tuple[float, float] | None:
    if item.vector_path is None:
        raise ValueError("Selected object has no editable vector path.")
    center = arc_center(item.vector_path, segment_index)
    if center is None:
        return None
    world = _local_points_to_world(item, [center])[0]
    return (float(world[0]), float(world[1]))


def world_xy_to_local_point(
    item: ProjectItem,
    xy: tuple[float, float],
) -> tuple[float, float]:
    if item.vector_path is None or item.mesh is None:
        raise ValueError("Object has no editable vector nodes.")
    if any(abs(float(v)) > 1e-7 for v in item.transform.rotation_deg[:2]):
        raise ValueError("Use zero X/Y tilt before editing XY path nodes.")
    world = node_world_points(item)
    matrix = item.transform.matrix(
        tuple(float(v) for v in np.asarray(item.mesh.mesh.bounds).mean(axis=0))
    )
    inverse = np.linalg.inv(matrix)
    z_world = float(world[0, 2])
    local = inverse @ np.array((xy[0], xy[1], z_world, 1), dtype=float)
    if not np.isfinite(local).all():
        raise ValueError("Vector edit must remain finite.")
    return (float(local[0]), float(local[1]))


def world_xy_to_local(
    item: ProjectItem,
    index: int,
    xy: tuple[float, float],
) -> tuple[float, float]:
    if item.vector_path is None:
        raise ValueError("Object has no editable vector nodes.")
    if not 0 <= index < len(item.vector_path.points_xy):
        raise IndexError("Vector node index out of range.")
    return world_xy_to_local_point(item, xy)
