from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import floor, isfinite, sqrt
from typing import Callable

import numpy as np

from .contact import CutterContactMap
from .toolpath import MoveKind, Toolpath, ToolpathMove


class RasterAxis(StrEnum):
    X = "x"
    Y = "y"
    DIAGONAL_45 = "45"
    DIAGONAL_135 = "135"


class RasterLinkMode(StrEnum):
    SMART = "smart"
    LOCAL_LIFT = "local_lift"
    FULL_RETRACT = "full_retract"


@dataclass(frozen=True, slots=True)
class RasterFinishingSettings:
    """Settings for cutter-aware serpentine 3D finishing."""

    stepover_mm: float
    feed_mm_min: float
    plunge_feed_mm_min: float
    safe_z_mm: float
    axis: RasterAxis = RasterAxis.X
    link_mode: RasterLinkMode = RasterLinkMode.SMART
    local_link_clearance_mm: float = 0.5
    direct_link_tolerance_mm: float = 0.02

    def __post_init__(self) -> None:
        positive = (
            self.stepover_mm,
            self.feed_mm_min,
            self.plunge_feed_mm_min,
            self.local_link_clearance_mm,
        )
        if not all(isfinite(value) and value > 0 for value in positive):
            raise ValueError(
                "Stepover, feed, and local-link clearance values must be "
                "finite and greater than zero."
            )
        if not isfinite(self.safe_z_mm):
            raise ValueError("safe_z_mm must be finite.")
        if (
            not isfinite(self.direct_link_tolerance_mm)
            or self.direct_link_tolerance_mm < 0
        ):
            raise ValueError(
                "direct_link_tolerance_mm must be finite and non-negative."
            )


def _sample_indices(
    sample_count: int,
    spacing_mm: float,
    stepover_mm: float,
) -> list[int]:
    if stepover_mm + 1e-9 < spacing_mm:
        raise ValueError(
            "Contact-map resolution is coarser than the requested stepover; "
            "rebuild the surface with finer samples."
        )
    stride = max(1, floor(stepover_mm / spacing_mm + 1e-9))
    indices = list(range(0, sample_count, stride))
    if indices[-1] != sample_count - 1:
        indices.append(sample_count - 1)
    return indices


def _sample_keys(
    first_key: int,
    last_key: int,
    spacing_mm: float,
    stepover_mm: float,
) -> list[int]:
    count = last_key - first_key + 1
    selected = _sample_indices(count, spacing_mm, stepover_mm)
    return [first_key + index for index in selected]


def _grid_lines(
    contact: CutterContactMap,
    settings: RasterFinishingSettings,
) -> list[np.ndarray]:
    surface = contact.surface
    y_count, x_count = contact.tip_z_mm.shape
    lines: list[np.ndarray] = []

    if settings.axis is RasterAxis.X:
        for y_index in _sample_indices(
            y_count,
            surface.spacing_y_mm,
            settings.stepover_mm,
        ):
            lines.append(
                np.asarray(
                    [(y_index, x_index) for x_index in range(x_count)],
                    dtype=np.int64,
                )
            )
        return lines

    if settings.axis is RasterAxis.Y:
        for x_index in _sample_indices(
            x_count,
            surface.spacing_x_mm,
            settings.stepover_mm,
        ):
            lines.append(
                np.asarray(
                    [(y_index, x_index) for y_index in range(y_count)],
                    dtype=np.int64,
                )
            )
        return lines

    perpendicular_spacing = (
        surface.spacing_x_mm
        * surface.spacing_y_mm
        / sqrt(
            surface.spacing_x_mm * surface.spacing_x_mm
            + surface.spacing_y_mm * surface.spacing_y_mm
        )
    )

    if settings.axis is RasterAxis.DIAGONAL_45:
        keys = _sample_keys(
            -(y_count - 1),
            x_count - 1,
            perpendicular_spacing,
            settings.stepover_mm,
        )
        for key in keys:
            points = [
                (y_index, y_index + key)
                for y_index in range(y_count)
                if 0 <= y_index + key < x_count
            ]
            if points:
                lines.append(np.asarray(points, dtype=np.int64))
        return lines

    keys = _sample_keys(
        0,
        x_count + y_count - 2,
        perpendicular_spacing,
        settings.stepover_mm,
    )
    for key in keys:
        points = [
            (y_index, key - y_index)
            for y_index in range(y_count)
            if 0 <= key - y_index < x_count
        ]
        if points:
            points.sort(key=lambda point: point[1])
            lines.append(np.asarray(points, dtype=np.int64))
    return lines


def _split_valid_runs(
    contact: CutterContactMap,
    line: np.ndarray,
) -> list[np.ndarray]:
    runs: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []

    for y_index, x_index in line:
        if np.isfinite(contact.tip_z_mm[int(y_index), int(x_index)]):
            current.append((int(y_index), int(x_index)))
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)

    return [
        np.asarray(run, dtype=np.int64)
        for run in runs
        if run
    ]


def _grid_point(
    contact: CutterContactMap,
    grid_index: tuple[int, int] | np.ndarray,
) -> tuple[float, float, float]:
    y_index = int(grid_index[0])
    x_index = int(grid_index[1])
    return (
        float(contact.surface.x_mm[x_index]),
        float(contact.surface.y_mm[y_index]),
        float(contact.tip_z_mm[y_index, x_index]),
    )


def _link_grid_samples(
    contact: CutterContactMap,
    start_index: np.ndarray,
    end_index: np.ndarray,
) -> list[tuple[float, float]]:
    dy = int(end_index[0] - start_index[0])
    dx = int(end_index[1] - start_index[1])
    step_count = max(abs(dx), abs(dy), 1)
    samples: list[tuple[float, float]] = []

    for step in range(step_count + 1):
        fraction = step / step_count
        y_index = round(int(start_index[0]) + dy * fraction)
        x_index = round(int(start_index[1]) + dx * fraction)
        required_z = float(contact.tip_z_mm[y_index, x_index])
        samples.append((fraction, required_z))
    return samples


def _direct_link_is_safe(
    samples: list[tuple[float, float]],
    start_z: float,
    end_z: float,
    tolerance_mm: float,
) -> bool:
    if not samples or any(not np.isfinite(required_z) for _, required_z in samples):
        return False

    for fraction, required_z in samples:
        interpolated_z = start_z + (end_z - start_z) * fraction
        if interpolated_z + tolerance_mm < required_z:
            return False
    return True


def _append_clearance_link(
    moves: list[ToolpathMove],
    end_point: tuple[float, float, float],
    link_z: float,
    settings: RasterFinishingSettings,
) -> None:
    previous = moves[-1]
    travel_z = max(previous.z_mm, link_z)
    if previous.z_mm < travel_z - 1e-9:
        moves.append(
            ToolpathMove(
                previous.x_mm,
                previous.y_mm,
                travel_z,
                MoveKind.RAPID,
            )
        )
    moves.append(
        ToolpathMove(
            end_point[0],
            end_point[1],
            travel_z,
            MoveKind.RAPID,
        )
    )
    moves.append(
        ToolpathMove(
            *end_point,
            MoveKind.PLUNGE,
            settings.plunge_feed_mm_min,
        )
    )


def _append_safe_link(
    moves: list[ToolpathMove],
    contact: CutterContactMap,
    settings: RasterFinishingSettings,
    *,
    start_index: np.ndarray,
    end_index: np.ndarray,
    end_point: tuple[float, float, float],
) -> None:
    """Connect runs using the least vertical motion allowed by the chosen mode."""

    previous = moves[-1]

    if settings.link_mode is RasterLinkMode.FULL_RETRACT:
        _append_clearance_link(
            moves,
            end_point,
            settings.safe_z_mm,
            settings,
        )
        return

    samples = _link_grid_samples(contact, start_index, end_index)

    if (
        settings.link_mode is RasterLinkMode.SMART
        and _direct_link_is_safe(
            samples,
            previous.z_mm,
            end_point[2],
            settings.direct_link_tolerance_mm,
        )
    ):
        moves.append(
            ToolpathMove(
                *end_point,
                MoveKind.CUT,
                settings.feed_mm_min,
            )
        )
        return

    finite_required = [
        required_z
        for _fraction, required_z in samples
        if np.isfinite(required_z)
    ]
    corridor_is_connected = len(finite_required) == len(samples)
    if corridor_is_connected:
        link_z = min(
            max(finite_required) + settings.local_link_clearance_mm,
            settings.safe_z_mm,
        )
    else:
        link_z = settings.safe_z_mm

    _append_clearance_link(moves, end_point, link_z, settings)


def generate_raster_finishing(
    contact: CutterContactMap,
    settings: RasterFinishingSettings,
    *,
    name: str = "3D Finish",
    progress: Callable[[float], None] | None = None,
) -> Toolpath:
    """Build a fast, cutter-safe serpentine finishing path.

    Flat/continuous areas remain connected as one cutting path whenever the
    cutter-contact map proves the row-to-row transition is safe. If direct
    linking is unsafe, a small local Z clearance is used over connected
    geometry. Full Safe Z is reserved for holes/disconnected corridors or for
    the explicit Full Retract mode.
    """

    finite_tip = contact.tip_z_mm[np.isfinite(contact.tip_z_mm)]
    if finite_tip.size == 0:
        raise ValueError("Cutter-contact map contains no machinable samples.")
    highest_tip = float(np.max(finite_tip))
    if settings.safe_z_mm <= highest_tip:
        raise ValueError(
            f"safe_z_mm must be above the highest cutting Z ({highest_tip:.3f} mm)."
        )

    grid_lines = _grid_lines(contact, settings)
    ordered_runs: list[np.ndarray] = []
    if progress is not None:
        progress(0.0)
    line_count = max(1, len(grid_lines))
    for line_number, line in enumerate(grid_lines):
        runs = _split_valid_runs(contact, line)
        if line_number % 2 == 1:
            runs = [run[::-1] for run in reversed(runs)]
        ordered_runs.extend(runs)
        if progress is not None:
            progress(0.30 * (line_number + 1) / line_count)

    if not ordered_runs:
        raise ValueError("No raster moves could be generated from the contact map.")

    moves: list[ToolpathMove] = []
    previous_index: np.ndarray | None = None

    run_count = len(ordered_runs)
    progress_stride = max(1, run_count // 100)
    for run_index, run in enumerate(ordered_runs):
        first_index = run[0]
        first = _grid_point(contact, first_index)

        if previous_index is None:
            moves.append(
                ToolpathMove(
                    first[0],
                    first[1],
                    settings.safe_z_mm,
                    MoveKind.RAPID,
                )
            )
            moves.append(
                ToolpathMove(
                    *first,
                    MoveKind.PLUNGE,
                    settings.plunge_feed_mm_min,
                )
            )
        else:
            _append_safe_link(
                moves,
                contact,
                settings,
                start_index=previous_index,
                end_index=first_index,
                end_point=first,
            )

        for grid_index in run[1:]:
            point = _grid_point(contact, grid_index)
            moves.append(
                ToolpathMove(
                    *point,
                    MoveKind.CUT,
                    settings.feed_mm_min,
                )
            )

        previous_index = run[-1]
        if (
            progress is not None
            and (
                run_index % progress_stride == 0
                or run_index == run_count - 1
            )
        ):
            progress(0.30 + 0.70 * (run_index + 1) / run_count)

    last = moves[-1]
    if last.z_mm < settings.safe_z_mm - 1e-9:
        moves.append(
            ToolpathMove(
                last.x_mm,
                last.y_mm,
                settings.safe_z_mm,
                MoveKind.RAPID,
            )
        )

    return Toolpath(
        name=name,
        operation="3d_finish_raster",
        cutter=contact.cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )
