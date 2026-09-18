from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from math import ceil, isfinite

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
    tab_height_mm: float = 2.0
    tabs_enabled: bool = False
    milling_direction: MillingDirection = MillingDirection.DEFAULT
    pocket_strategy: PocketStrategy = PocketStrategy.RASTER_X
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
        return -abs(float(settings.overall_depth_mm))
    minimum_z = float(bounds[0, 2])
    if minimum_z < -1e-6:
        return minimum_z
    return float(fallback_mm)


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
        _rapid(moves, corners[0][0], corners[0][1], settings.safe_z_mm)
        _plunge(moves, corners[0][0], corners[0][1], depth, settings)

        if settings.tabs_enabled and depth <= target_z + 1e-9:
            tab_z = min(0.0, depth + settings.tab_height_mm)
            for start, end in pairwise(corners):
                x0, y0 = start
                x1, y1 = end
                first = (x0 + (x1 - x0) * 0.40, y0 + (y1 - y0) * 0.40)
                second = (x0 + (x1 - x0) * 0.60, y0 + (y1 - y0) * 0.60)
                _cut(moves, first[0], first[1], depth, settings)
                _cut(moves, first[0], first[1], tab_z, settings)
                _cut(moves, second[0], second[1], tab_z, settings)
                _cut(moves, second[0], second[1], depth, settings)
                _cut(moves, x1, y1, depth, settings)
        else:
            for x, y in corners[1:]:
                _cut(moves, x, y, depth, settings)

        last = moves[-1]
        _rapid(moves, last.x_mm, last.y_mm, settings.safe_z_mm)

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
                    _rapid(moves, loop[0][0], loop[0][1], settings.safe_z_mm)
                    _plunge(moves, loop[0][0], loop[0][1], depth, settings)
                    first_loop = False
                else:
                    _cut(moves, loop[0][0], loop[0][1], depth, settings)
                for x, y in loop[1:]:
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
                    _rapid(moves, start[0], start[1], settings.safe_z_mm)
                    _plunge(moves, start[0], start[1], depth, settings)
                    first_line = False
                else:
                    _cut(moves, start[0], start[1], depth, settings)
                _cut(moves, end[0], end[1], depth, settings)
                reverse = not reverse

        if moves:
            last = moves[-1]
            _rapid(moves, last.x_mm, last.y_mm, settings.safe_z_mm)

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
    _rapid(moves, points[0][0], points[0][1], settings.safe_z_mm)
    _plunge(moves, points[0][0], points[0][1], z, settings)
    for x, y in points[1:]:
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
    if quality == "rough":
        stepover = max(cutter.diameter_mm * 0.48, 0.05)
        spacing = min(
            stepover,
            max(cutter.diameter_mm * 0.24, float(np.max(xy_span)) / 300.0),
        )
    else:
        fraction = settings.finish_stepover_fraction
        if quality == "rest":
            fraction = min(fraction, 0.08)
        stepover = max(cutter.diameter_mm * fraction, 0.03)
        spacing = min(
            stepover,
            max(stepover * 0.65, float(np.max(xy_span)) / 700.0),
        )

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
    for z in levels:
        section = mesh.section(
            plane_origin=(0.0, 0.0, z),
            plane_normal=(0.0, 0.0, 1.0),
        )
        if section is None:
            continue
        for path in section.discrete:
            points = np.asarray(path, dtype=float)
            if len(points) < 2:
                continue
            first = points[0]
            _rapid(moves, float(first[0]), float(first[1]), settings.safe_z_mm)
            _plunge(moves, float(first[0]), float(first[1]), float(z), settings)
            for point in points[1:]:
                _cut(
                    moves,
                    float(point[0]),
                    float(point[1]),
                    float(z),
                    settings,
                )
            last = moves[-1]
            _rapid(moves, last.x_mm, last.y_mm, settings.safe_z_mm)

    if not moves:
        raise ValueError("Waterline slicing produced no machinable contours.")
    return Toolpath(
        name=name,
        operation="3d_waterline",
        cutter=cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )
