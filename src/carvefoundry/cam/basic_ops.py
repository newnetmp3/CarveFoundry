from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from math import ceil, hypot, isfinite, radians, tan

import numpy as np
import trimesh

from carvefoundry.core.tools import Cutter

from .finish import Finish3DSettings, calculate_3d_finish
from .raster import (
    RasterAxis,
    RasterFinishingSettings,
    RasterLinkMode,
)
from .toolpath import MoveKind, Toolpath, ToolpathMove


class MillingDirection(StrEnum):
    DEFAULT = "default"
    CLIMB = "climb"
    CONVENTIONAL = "conventional"


class PocketStrategy(StrEnum):
    OFFSET = "offset"
    RASTER_X = "raster_x"
    RASTER_Y = "raster_y"


class ReliefStyle(StrEnum):
    MODEL_BOUNDARY = "model_boundary"
    RECTANGLE = "rectangle"
    FULL_DEPTH = "full_depth"


DETAIL_FAST_STEPOVER_FRACTION = 0.20
DETAIL_FINE_STEPOVER_FRACTION = 0.04


def detail_stepover_fraction(detail: float) -> float:
    """Map a 0-100 detail control to cutter-relative raster stepover.

    Zero favors speed at 20% of cutter diameter. One hundred favors detail at
    4%. Increasing Detail therefore always adds raster lines for a fixed tool
    and work area.
    """

    value = float(detail)
    if not isfinite(value) or not 0.0 <= value <= 100.0:
        raise ValueError("detail must be between 0 and 100.")
    span = DETAIL_FAST_STEPOVER_FRACTION - DETAIL_FINE_STEPOVER_FRACTION
    return DETAIL_FAST_STEPOVER_FRACTION - span * (value / 100.0)


def detail_for_stepover_fraction(fraction: float) -> int:
    """Return the nearest slider value for a supported stepover fraction."""

    value = float(fraction)
    if not isfinite(value):
        raise ValueError("stepover fraction must be finite.")
    value = max(
        DETAIL_FINE_STEPOVER_FRACTION,
        min(DETAIL_FAST_STEPOVER_FRACTION, value),
    )
    span = DETAIL_FAST_STEPOVER_FRACTION - DETAIL_FINE_STEPOVER_FRACTION
    return round(
        100.0 * (DETAIL_FAST_STEPOVER_FRACTION - value) / span
    )


@dataclass(frozen=True, slots=True)
class BasicCamSettings:
    safe_z_mm: float = 1.5
    feed_mm_min: float = 1000.0
    plunge_feed_mm_min: float = 300.0
    max_stepdown_mm: float = 2.0
    stepover_fraction: float = 0.45
    finish_stepover_fraction: float = 0.10
    overall_depth_mm: float | None = None
    padding_mm: float = 0.0
    usable_bit_length_mm: float | None = None
    tab_height_mm: float = 2.0
    tab_width_mm: float = 6.0
    tab_count: int = 4
    tabs_enabled: bool = False
    milling_direction: MillingDirection = MillingDirection.DEFAULT
    pocket_strategy: PocketStrategy = PocketStrategy.RASTER_X
    relief_style: ReliefStyle = ReliefStyle.MODEL_BOUNDARY
    raster_axis: RasterAxis = RasterAxis.X
    raster_link_mode: RasterLinkMode = RasterLinkMode.SMART
    local_link_clearance_mm: float = 0.5
    direct_link_tolerance_mm: float = 0.02
    ramp_angle_deg: float | None = None

    def __post_init__(self) -> None:
        positive = (
            self.feed_mm_min,
            self.plunge_feed_mm_min,
            self.max_stepdown_mm,
            self.stepover_fraction,
            self.finish_stepover_fraction,
            self.tab_height_mm,
            self.tab_width_mm,
            self.local_link_clearance_mm,
        )
        if not all(isfinite(value) and value > 0 for value in positive):
            raise ValueError("CAM feed/step values must be finite and greater than zero.")
        if not isfinite(self.safe_z_mm):
            raise ValueError("safe_z_mm must be finite.")
        if self.overall_depth_mm is not None and (
            not isfinite(self.overall_depth_mm) or self.overall_depth_mm <= 0
        ):
            raise ValueError("overall_depth_mm must be greater than zero when set.")
        if not isfinite(self.padding_mm) or self.padding_mm < 0:
            raise ValueError("padding_mm must be finite and non-negative.")
        if self.usable_bit_length_mm is not None and (
            not isfinite(self.usable_bit_length_mm)
            or self.usable_bit_length_mm <= 0
        ):
            raise ValueError(
                "usable_bit_length_mm must be greater than zero when set."
            )
        if not 1 <= self.tab_count <= 32:
            raise ValueError("tab_count must be between 1 and 32.")
        if self.stepover_fraction > 1.0 or self.finish_stepover_fraction > 1.0:
            raise ValueError("Stepover fractions cannot exceed 1.0.")
        if (
            not isfinite(self.direct_link_tolerance_mm)
            or self.direct_link_tolerance_mm < 0
        ):
            raise ValueError(
                "direct_link_tolerance_mm must be finite and non-negative."
            )
        if self.ramp_angle_deg is not None and (
            not isfinite(self.ramp_angle_deg)
            or not 0 < self.ramp_angle_deg < 90
        ):
            raise ValueError("ramp_angle_deg must be between 0 and 90 degrees.")


def _target_depth(
    bounds: np.ndarray,
    settings: BasicCamSettings,
    *,
    fallback_mm: float = -1.0,
) -> float:
    if settings.overall_depth_mm is not None:
        target = -abs(float(settings.overall_depth_mm))
    else:
        minimum_z = float(bounds[0, 2])
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
    moves.append(ToolpathMove(x, y, z, MoveKind.RAPID))


def _plunge(
    moves: list[ToolpathMove],
    x: float,
    y: float,
    z: float,
    settings: BasicCamSettings,
) -> None:
    moves.append(
        ToolpathMove(
            x,
            y,
            z,
            MoveKind.PLUNGE,
            settings.plunge_feed_mm_min,
        )
    )


def _cut(
    moves: list[ToolpathMove],
    x: float,
    y: float,
    z: float,
    settings: BasicCamSettings,
) -> None:
    moves.append(
        ToolpathMove(
            x,
            y,
            z,
            MoveKind.CUT,
            settings.feed_mm_min,
        )
    )


def _transition_clearance_z(settings: BasicCamSettings) -> float:
    if settings.raster_link_mode is RasterLinkMode.FULL_RETRACT:
        return settings.safe_z_mm
    return min(
        settings.safe_z_mm,
        max(0.0, settings.local_link_clearance_mm),
    )


def _position_for_transition(
    moves: list[ToolpathMove],
    x: float,
    y: float,
    settings: BasicCamSettings,
) -> None:
    if not moves:
        _rapid(moves, x, y, settings.safe_z_mm)
        return
    previous = moves[-1]
    travel_z = max(previous.z_mm, _transition_clearance_z(settings))
    if previous.z_mm < travel_z - 1e-9:
        _rapid(moves, previous.x_mm, previous.y_mm, travel_z)
    if hypot(previous.x_mm - x, previous.y_mm - y) > 1e-9:
        _rapid(moves, x, y, travel_z)


def _final_retract(
    moves: list[ToolpathMove],
    settings: BasicCamSettings,
) -> None:
    if not moves:
        return
    last = moves[-1]
    if last.z_mm < settings.safe_z_mm - 1e-9:
        _rapid(moves, last.x_mm, last.y_mm, settings.safe_z_mm)


def _enter_depth(
    moves: list[ToolpathMove],
    start: tuple[float, float],
    next_point: tuple[float, float],
    target_z: float,
    previous_depth_z: float,
    settings: BasicCamSettings,
) -> tuple[float, float]:
    """Enter material vertically or by ramping along the first toolpath segment."""

    _rapid(moves, start[0], start[1], settings.safe_z_mm)
    if settings.ramp_angle_deg is None:
        _plunge(moves, start[0], start[1], target_z, settings)
        return start

    # Move through already-cleared air/material to the previous pass level, then
    # descend while advancing along the actual toolpath.
    entry_z = min(0.0, previous_depth_z)
    _plunge(moves, start[0], start[1], entry_z, settings)

    dx = next_point[0] - start[0]
    dy = next_point[1] - start[1]
    segment_length = hypot(dx, dy)
    if segment_length <= 1e-9:
        _plunge(moves, start[0], start[1], target_z, settings)
        return start

    depth_delta = abs(target_z - entry_z)
    required_length = depth_delta / tan(radians(settings.ramp_angle_deg))
    fraction = min(1.0, required_length / segment_length)
    ramp_end = (
        start[0] + dx * fraction,
        start[1] + dy * fraction,
    )
    _cut(moves, ramp_end[0], ramp_end[1], target_z, settings)
    return ramp_end


def _padded_xy_bounds(
    bounds: np.ndarray,
    padding_mm: float,
) -> tuple[float, float, float, float]:
    data = np.asarray(bounds, dtype=float)
    return (
        float(data[0, 0] - padding_mm),
        float(data[0, 1] - padding_mm),
        float(data[1, 0] + padding_mm),
        float(data[1, 1] + padding_mm),
    )


def _profile_with_tabs(
    moves: list[ToolpathMove],
    corners: list[tuple[float, float]],
    depth: float,
    tab_z: float,
    settings: BasicCamSettings,
) -> None:
    segment_lengths = [
        hypot(end[0] - start[0], end[1] - start[1])
        for start, end in pairwise(corners)
    ]
    perimeter = sum(segment_lengths)
    if perimeter <= 1e-9:
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

    cumulative = 0.0
    for (start, end), segment_length in zip(
        pairwise(corners),
        segment_lengths,
        strict=True,
    ):
        segment_start = cumulative
        segment_end = cumulative + segment_length
        breakpoints = {segment_start, segment_end}
        for interval_start, interval_end in intervals:
            if segment_start < interval_start < segment_end:
                breakpoints.add(interval_start)
            if segment_start < interval_end < segment_end:
                breakpoints.add(interval_end)
        ordered = sorted(breakpoints)

        for range_start, range_end in pairwise(ordered):
            midpoint = (range_start + range_end) / 2.0
            desired_z = (
                tab_z
                if any(
                    interval_start <= midpoint <= interval_end
                    for interval_start, interval_end in intervals
                )
                else depth
            )
            local_start = (
                (range_start - segment_start) / segment_length
                if segment_length > 1e-12
                else 0.0
            )
            local_end = (
                (range_end - segment_start) / segment_length
                if segment_length > 1e-12
                else 1.0
            )
            start_point = (
                start[0] + (end[0] - start[0]) * local_start,
                start[1] + (end[1] - start[1]) * local_start,
            )
            end_point = (
                start[0] + (end[0] - start[0]) * local_end,
                start[1] + (end[1] - start[1]) * local_end,
            )
            if abs(moves[-1].z_mm - desired_z) > 1e-9:
                _cut(
                    moves,
                    start_point[0],
                    start_point[1],
                    desired_z,
                    settings,
                )
            _cut(
                moves,
                end_point[0],
                end_point[1],
                desired_z,
                settings,
            )
        cumulative = segment_end


def rectangular_profile(
    bounds: np.ndarray,
    cutter: Cutter,
    settings: BasicCamSettings,
    *,
    name: str = "Profile",
    offset_mode: str = "outside",
) -> Toolpath:
    data = np.asarray(bounds, dtype=float)
    min_x, min_y, max_x, max_y = _padded_xy_bounds(
        data,
        settings.padding_mm,
    )
    radius = cutter.radius_mm
    if offset_mode == "outside":
        min_x -= radius
        min_y -= radius
        max_x += radius
        max_y += radius
    elif offset_mode == "inside":
        min_x += radius
        min_y += radius
        max_x -= radius
        max_y -= radius
    elif offset_mode != "on":
        raise ValueError(f"Unsupported profile offset mode: {offset_mode}")
    if max_x <= min_x or max_y <= min_y:
        raise ValueError("Selected geometry is too small for this profile offset.")
    target_z = _target_depth(data, settings)
    moves: list[ToolpathMove] = []
    previous_depth = 0.0

    for depth in _depth_passes(target_z, settings.max_stepdown_mm):
        corners = [
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
            (min_x, min_y),
        ]
        if settings.milling_direction is MillingDirection.CONVENTIONAL:
            corners = [
                (min_x, min_y),
                (min_x, max_y),
                (max_x, max_y),
                (max_x, min_y),
                (min_x, min_y),
            ]
        final_tab_pass = settings.tabs_enabled and depth <= target_z + 1e-9
        if final_tab_pass:
            _rapid(moves, corners[0][0], corners[0][1], settings.safe_z_mm)
            _plunge(moves, corners[0][0], corners[0][1], depth, settings)
        else:
            ramp_end = _enter_depth(
                moves,
                corners[0],
                corners[1],
                depth,
                previous_depth,
                settings,
            )
            if ramp_end != corners[0] and ramp_end != corners[1]:
                _cut(moves, corners[1][0], corners[1][1], depth, settings)

        if final_tab_pass:
            tab_z = min(0.0, depth + settings.tab_height_mm)
            _profile_with_tabs(
                moves,
                corners,
                depth,
                tab_z,
                settings,
            )
        else:
            start_index = 1
            if settings.ramp_angle_deg is not None:
                start_index = 2
            for x, y in corners[start_index:]:
                _cut(moves, x, y, depth, settings)

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


def rectangular_pocket(
    bounds: np.ndarray,
    cutter: Cutter,
    settings: BasicCamSettings,
    *,
    name: str = "Pocket",
) -> Toolpath:
    data = np.asarray(bounds, dtype=float)
    raw_min_x, raw_min_y, raw_max_x, raw_max_y = _padded_xy_bounds(
        data,
        settings.padding_mm,
    )
    min_x = raw_min_x + cutter.radius_mm
    min_y = raw_min_y + cutter.radius_mm
    max_x = raw_max_x - cutter.radius_mm
    max_y = raw_max_y - cutter.radius_mm
    if max_x <= min_x or max_y <= min_y:
        raise ValueError("Selected geometry is too small for the selected cutter.")
    target_z = _target_depth(data, settings)
    stepover = max(cutter.diameter_mm * settings.stepover_fraction, 0.05)

    moves: list[ToolpathMove] = []
    previous_depth = 0.0
    for depth in _depth_passes(target_z, settings.max_stepdown_mm):
        if settings.pocket_strategy is PocketStrategy.OFFSET:
            inset = 0.0
            first_loop = True
            while (
                min_x + inset <= max_x - inset
                and min_y + inset <= max_y - inset
            ):
                left = min_x + inset
                right = max_x - inset
                bottom = min_y + inset
                top = max_y - inset
                loop = [
                    (left, bottom),
                    (right, bottom),
                    (right, top),
                    (left, top),
                    (left, bottom),
                ]
                if settings.milling_direction is MillingDirection.CONVENTIONAL:
                    loop = [
                        (left, bottom),
                        (left, top),
                        (right, top),
                        (right, bottom),
                        (left, bottom),
                    ]
                if first_loop:
                    ramp_end = _enter_depth(
                        moves,
                        loop[0],
                        loop[1],
                        depth,
                        previous_depth,
                        settings,
                    )
                    first_loop = False
                    start_index = 1
                    if settings.ramp_angle_deg is not None:
                        if ramp_end != loop[1]:
                            _cut(moves, loop[1][0], loop[1][1], depth, settings)
                        start_index = 2
                else:
                    _cut(moves, loop[0][0], loop[0][1], depth, settings)
                    start_index = 1
                for x, y in loop[start_index:]:
                    _cut(moves, x, y, depth, settings)
                inset += stepover
        else:
            raster_y = settings.pocket_strategy is PocketStrategy.RASTER_Y
            line_min = min_x if raster_y else min_y
            line_max = max_x if raster_y else max_y
            line_values = list(
                np.arange(line_min, line_max + stepover * 0.5, stepover)
            )
            if not line_values or line_values[-1] < line_max:
                line_values.append(line_max)

            reverse = False
            first_line = True
            for line_value in line_values:
                if raster_y:
                    start = (
                        float(line_value),
                        max_y if reverse else min_y,
                    )
                    end = (
                        float(line_value),
                        min_y if reverse else max_y,
                    )
                else:
                    start = (
                        max_x if reverse else min_x,
                        float(line_value),
                    )
                    end = (
                        min_x if reverse else max_x,
                        float(line_value),
                    )
                if first_line:
                    ramp_end = _enter_depth(
                        moves,
                        start,
                        end,
                        depth,
                        previous_depth,
                        settings,
                    )
                    first_line = False
                    if ramp_end != end:
                        _cut(moves, end[0], end[1], depth, settings)
                else:
                    _cut(moves, start[0], start[1], depth, settings)
                    _cut(moves, end[0], end[1], depth, settings)
                reverse = not reverse

        if moves:
            last = moves[-1]
            _rapid(moves, last.x_mm, last.y_mm, settings.safe_z_mm)
        previous_depth = depth

    return Toolpath(
        name=name,
        operation="pocket",
        cutter=cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )


def rectangular_engrave(
    bounds: np.ndarray,
    cutter: Cutter,
    settings: BasicCamSettings,
    *,
    depth_mm: float = -0.5,
    name: str = "Engrave",
    operation: str = "engrave",
) -> Toolpath:
    data = np.asarray(bounds, dtype=float)
    min_x, min_y = data[0, :2]
    max_x, max_y = data[1, :2]
    z = (
        _target_depth(data, settings, fallback_mm=depth_mm)
        if settings.overall_depth_mm is not None
        else min(-1e-4, float(depth_mm))
    )
    points = [
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
        (min_x, min_y),
    ]
    moves: list[ToolpathMove] = []
    ramp_end = _enter_depth(
        moves,
        points[0],
        points[1],
        z,
        0.0,
        settings,
    )
    start_index = 1
    if settings.ramp_angle_deg is not None:
        if ramp_end != points[1]:
            _cut(moves, points[1][0], points[1][1], z, settings)
        start_index = 2
    for x, y in points[start_index:]:
        _cut(moves, x, y, z, settings)
    _rapid(moves, points[-1][0], points[-1][1], settings.safe_z_mm)
    return Toolpath(
        name=name,
        operation=operation,
        cutter=cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )


def center_drill(
    bounds: np.ndarray,
    cutter: Cutter,
    settings: BasicCamSettings,
    *,
    name: str = "Drill",
) -> Toolpath:
    data = np.asarray(bounds, dtype=float)
    center = data.mean(axis=0)
    target_z = _target_depth(data, settings)
    moves: list[ToolpathMove] = []
    _rapid(moves, float(center[0]), float(center[1]), settings.safe_z_mm)
    for depth in _depth_passes(target_z, settings.max_stepdown_mm):
        _plunge(
            moves,
            float(center[0]),
            float(center[1]),
            depth,
            settings,
        )
        _rapid(
            moves,
            float(center[0]),
            float(center[1]),
            settings.safe_z_mm,
        )
    return Toolpath(
        name=name,
        operation="drill",
        cutter=cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )


def _finish_settings(
    mesh: trimesh.Trimesh,
    cutter: Cutter,
    settings: BasicCamSettings,
    *,
    quality: str,
) -> Finish3DSettings:
    bounds = np.asarray(mesh.bounds, dtype=float)
    xy_span = np.maximum(bounds[1, :2] - bounds[0, :2], 1e-6)
    detail_fraction = settings.finish_stepover_fraction
    if quality == "rough":
        # Roughing stays substantially coarser than finishing, but the same
        # Detail control still raises/lowers row density predictably.
        rough_fraction = min(0.65, max(0.18, detail_fraction * 4.0))
        stepover = max(cutter.diameter_mm * rough_fraction, 0.05)
        spacing = min(
            stepover,
            max(stepover * 0.55, float(np.max(xy_span)) / 300.0),
        )
    else:
        fraction = (
            max(0.03, detail_fraction * 0.8)
            if quality == "rest"
            else detail_fraction
        )
        stepover = max(cutter.diameter_mm * fraction, 0.03)
        spacing = min(
            stepover,
            max(stepover * 0.65, float(np.max(xy_span)) / 700.0),
        )

    surface_padding = 0.0
    background_z: float | None = None
    if settings.relief_style is ReliefStyle.RECTANGLE:
        surface_padding = settings.padding_mm
        if settings.overall_depth_mm is not None:
            background_z = -abs(settings.overall_depth_mm)
        else:
            background_z = float(bounds[0, 2])

    return Finish3DSettings(
        surface_spacing_mm=spacing,
        raster=RasterFinishingSettings(
            stepover_mm=stepover,
            feed_mm_min=settings.feed_mm_min,
            plunge_feed_mm_min=settings.plunge_feed_mm_min,
            safe_z_mm=settings.safe_z_mm,
            axis=settings.raster_axis,
            link_mode=settings.raster_link_mode,
            local_link_clearance_mm=settings.local_link_clearance_mm,
            direct_link_tolerance_mm=settings.direct_link_tolerance_mm,
        ),
        max_surface_samples=2_000_000,
        surface_padding_mm=surface_padding,
        background_z_mm=background_z,
    )


def finish_3d(
    mesh: trimesh.Trimesh,
    cutter: Cutter,
    settings: BasicCamSettings,
    *,
    strategy: str = "finish",
) -> Toolpath:
    if strategy not in {"rough", "finish", "rest"}:
        raise ValueError(f"Unsupported raster 3D strategy: {strategy}")
    bounds = np.asarray(mesh.bounds, dtype=float)
    required_depth = max(0.0, float(bounds[1, 2] - bounds[0, 2]))
    if (
        settings.usable_bit_length_mm is not None
        and required_depth > settings.usable_bit_length_mm + 1e-9
    ):
        raise ValueError(
            f"Model depth {required_depth:.3f} mm exceeds the usable bit "
            f"length {settings.usable_bit_length_mm:.3f} mm."
        )

    result = calculate_3d_finish(
        mesh,
        cutter,
        _finish_settings(mesh, cutter, settings, quality=strategy),
        name={
            "rough": "3D Rough",
            "finish": "3D Finish",
            "rest": "3D Rest",
        }[strategy],
    )
    toolpath = result.toolpath

    if strategy == "rough":
        allowance = min(max(cutter.diameter_mm * 0.08, 0.2), 1.0)
        adjusted: list[ToolpathMove] = []
        for move in toolpath.moves:
            if move.kind is MoveKind.RAPID:
                adjusted.append(move)
            else:
                adjusted.append(
                    ToolpathMove(
                        move.x_mm,
                        move.y_mm,
                        min(settings.safe_z_mm - 1e-4, move.z_mm + allowance),
                        move.kind,
                        move.feed_mm_min,
                    )
                )
        toolpath.moves = adjusted
        toolpath.operation = "3d_rough_raster"
    elif strategy == "rest":
        toolpath.operation = "3d_rest_raster"

    return toolpath


def waterline_3d(
    mesh: trimesh.Trimesh,
    cutter: Cutter,
    settings: BasicCamSettings,
    *,
    level_step_mm: float | None = None,
    name: str = "3D Waterline",
) -> Toolpath:
    bounds = np.asarray(mesh.bounds, dtype=float)
    min_z = float(bounds[0, 2])
    max_z = float(bounds[1, 2])
    depth = max_z - min_z
    if depth <= 1e-9:
        raise ValueError("Mesh has no Z depth for waterline machining.")
    step = level_step_mm or max(cutter.diameter_mm * 0.5, 0.5)
    level_count = max(1, ceil(depth / step))
    levels = [
        max_z - (index + 1) * depth / level_count
        for index in range(level_count)
    ]

    moves: list[ToolpathMove] = []
    previous_xy: np.ndarray | None = None
    for z in levels:
        section = mesh.section(
            plane_origin=(0.0, 0.0, z),
            plane_normal=(0.0, 0.0, 1.0),
        )
        if section is None:
            continue

        remaining = [
            np.asarray(path, dtype=float)
            for path in section.discrete
            if len(path) >= 2
        ]
        ordered: list[np.ndarray] = []
        while remaining:
            if previous_xy is None:
                points = remaining.pop(0)
            else:
                best_index = 0
                best_points = remaining[0]
                best_distance = float("inf")
                for index, candidate in enumerate(remaining):
                    trial = candidate
                    closed = (
                        len(candidate) >= 3
                        and np.linalg.norm(candidate[0, :2] - candidate[-1, :2])
                        <= 1e-7
                    )
                    if closed:
                        ring = candidate[:-1]
                        distances = np.linalg.norm(
                            ring[:, :2] - previous_xy[:2],
                            axis=1,
                        )
                        start_index = int(np.argmin(distances))
                        rotated = np.vstack(
                            (ring[start_index:], ring[:start_index])
                        )
                        trial = np.vstack((rotated, rotated[0]))
                        distance = float(np.min(distances))
                    else:
                        start_distance = float(
                            np.linalg.norm(candidate[0, :2] - previous_xy[:2])
                        )
                        end_distance = float(
                            np.linalg.norm(candidate[-1, :2] - previous_xy[:2])
                        )
                        if end_distance < start_distance:
                            trial = candidate[::-1].copy()
                            distance = end_distance
                        else:
                            distance = start_distance
                    if distance < best_distance:
                        best_index = index
                        best_points = trial
                        best_distance = distance
                remaining.pop(best_index)
                points = best_points
            ordered.append(points)
            previous_xy = points[-1]

        for points in ordered:
            first = points[0]
            _position_for_transition(
                moves,
                float(first[0]),
                float(first[1]),
                settings,
            )
            _plunge(moves, float(first[0]), float(first[1]), float(z), settings)
            for point in points[1:]:
                _cut(
                    moves,
                    float(point[0]),
                    float(point[1]),
                    float(z),
                    settings,
                )
            previous_xy = points[-1]

    _final_retract(moves, settings)
    if not moves:
        raise ValueError("Waterline slicing produced no machinable contours.")
    return Toolpath(
        name=name,
        operation="3d_waterline",
        cutter=cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )
