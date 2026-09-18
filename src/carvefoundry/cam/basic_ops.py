from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite

import numpy as np
import trimesh

from carvefoundry.core.tools import Cutter

from .finish import Finish3DSettings, calculate_3d_finish
from .raster import RasterAxis, RasterFinishingSettings
from .toolpath import MoveKind, Toolpath, ToolpathMove


@dataclass(frozen=True, slots=True)
class BasicCamSettings:
    safe_z_mm: float = 5.0
    feed_mm_min: float = 1000.0
    plunge_feed_mm_min: float = 300.0
    max_stepdown_mm: float = 2.0
    stepover_fraction: float = 0.45
    tab_height_mm: float = 2.0
    tabs_enabled: bool = False

    def __post_init__(self) -> None:
        positive = (
            self.feed_mm_min,
            self.plunge_feed_mm_min,
            self.max_stepdown_mm,
            self.stepover_fraction,
            self.tab_height_mm,
        )
        if not all(isfinite(value) and value > 0 for value in positive):
            raise ValueError("CAM feed/step values must be finite and greater than zero.")
        if not isfinite(self.safe_z_mm):
            raise ValueError("safe_z_mm must be finite.")


def _target_depth(bounds: np.ndarray, *, fallback_mm: float = -1.0) -> float:
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


def rectangular_profile(
    bounds: np.ndarray,
    cutter: Cutter,
    settings: BasicCamSettings,
    *,
    name: str = "Profile",
) -> Toolpath:
    data = np.asarray(bounds, dtype=float)
    min_x, min_y = data[0, :2]
    max_x, max_y = data[1, :2]
    radius = cutter.radius_mm
    min_x -= radius
    min_y -= radius
    max_x += radius
    max_y += radius
    target_z = _target_depth(data)
    moves: list[ToolpathMove] = []

    for depth in _depth_passes(target_z, settings.max_stepdown_mm):
        corners = [
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
            (min_x, min_y),
        ]
        _rapid(moves, corners[0][0], corners[0][1], settings.safe_z_mm)
        _plunge(moves, corners[0][0], corners[0][1], depth, settings)

        if settings.tabs_enabled and depth <= target_z + 1e-9:
            tab_z = min(0.0, depth + settings.tab_height_mm)
            for start, end in zip(corners, corners[1:]):
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
    min_x, min_y = data[0, :2] + cutter.radius_mm
    max_x, max_y = data[1, :2] - cutter.radius_mm
    if max_x <= min_x or max_y <= min_y:
        raise ValueError("Selected geometry is too small for the selected cutter.")
    target_z = _target_depth(data)
    stepover = max(cutter.diameter_mm * settings.stepover_fraction, 0.05)
    y_values = list(np.arange(min_y, max_y + stepover * 0.5, stepover))
    if not y_values or y_values[-1] < max_y:
        y_values.append(max_y)

    moves: list[ToolpathMove] = []
    for depth in _depth_passes(target_z, settings.max_stepdown_mm):
        reverse = False
        first_xy: tuple[float, float] | None = None
        for y in y_values:
            start_x, end_x = (max_x, min_x) if reverse else (min_x, max_x)
            if first_xy is None:
                first_xy = (start_x, float(y))
                _rapid(moves, start_x, float(y), settings.safe_z_mm)
                _plunge(moves, start_x, float(y), depth, settings)
            else:
                _cut(moves, start_x, float(y), depth, settings)
            _cut(moves, end_x, float(y), depth, settings)
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
    z = min(-1e-4, float(depth_mm))
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
    target_z = _target_depth(data)
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
        spacing = max(cutter.diameter_mm * 0.28, float(np.max(xy_span)) / 260.0)
        stepover = max(cutter.diameter_mm * 0.48, spacing)
    elif quality == "rest":
        spacing = max(cutter.diameter_mm * 0.08, float(np.max(xy_span)) / 650.0)
        stepover = max(cutter.diameter_mm * 0.10, spacing)
    else:
        spacing = max(cutter.diameter_mm * 0.12, float(np.max(xy_span)) / 500.0)
        stepover = max(cutter.diameter_mm * 0.14, spacing)

    return Finish3DSettings(
        surface_spacing_mm=spacing,
        raster=RasterFinishingSettings(
            stepover_mm=stepover,
            feed_mm_min=settings.feed_mm_min,
            plunge_feed_mm_min=settings.plunge_feed_mm_min,
            safe_z_mm=settings.safe_z_mm,
            axis=RasterAxis.X,
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
