from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import floor, isfinite

import numpy as np

from .contact import CutterContactMap
from .toolpath import MoveKind, Toolpath, ToolpathMove


class RasterAxis(StrEnum):
    X = "x"
    Y = "y"


@dataclass(frozen=True, slots=True)
class RasterFinishingSettings:
    """Safe baseline settings for a serpentine 3D finishing operation."""

    stepover_mm: float
    feed_mm_min: float
    plunge_feed_mm_min: float
    safe_z_mm: float
    axis: RasterAxis = RasterAxis.X

    def __post_init__(self) -> None:
        positive = (self.stepover_mm, self.feed_mm_min, self.plunge_feed_mm_min)
        if not all(isfinite(value) and value > 0 for value in positive):
            raise ValueError("Stepover and feed values must be finite and greater than zero.")
        if not isfinite(self.safe_z_mm):
            raise ValueError("safe_z_mm must be finite.")


def _line_indices(sample_count: int, spacing_mm: float, stepover_mm: float) -> list[int]:
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


def _contiguous_runs(mask: np.ndarray) -> list[np.ndarray]:
    padded = np.concatenate(([False], np.asarray(mask, dtype=bool), [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    return [np.arange(start, end, dtype=np.int64) for start, end in changes.reshape(-1, 2)]


def _sample_point(
    contact: CutterContactMap,
    axis: RasterAxis,
    line_index: int,
    sample_index: int,
) -> tuple[float, float, float]:
    surface = contact.surface
    if axis is RasterAxis.X:
        return (
            float(surface.x_mm[sample_index]),
            float(surface.y_mm[line_index]),
            float(contact.tip_z_mm[line_index, sample_index]),
        )
    return (
        float(surface.x_mm[line_index]),
        float(surface.y_mm[sample_index]),
        float(contact.tip_z_mm[sample_index, line_index]),
    )


def generate_raster_finishing(
    contact: CutterContactMap,
    settings: RasterFinishingSettings,
    *,
    name: str = "3D Finish",
) -> Toolpath:
    """Build a conservative serpentine finish path from a cutter-contact map.

    Every disconnected valid run retracts vertically to ``safe_z_mm`` before the
    next XY rapid. Adjacent rows alternate direction to avoid needless return
    traverses while keeping linking behavior unambiguously safe.
    """

    finite_tip = contact.tip_z_mm[np.isfinite(contact.tip_z_mm)]
    if finite_tip.size == 0:
        raise ValueError("Cutter-contact map contains no machinable samples.")
    highest_tip = float(np.max(finite_tip))
    if settings.safe_z_mm <= highest_tip:
        raise ValueError(
            f"safe_z_mm must be above the highest cutting Z ({highest_tip:.3f} mm)."
        )

    surface = contact.surface
    if settings.axis is RasterAxis.X:
        line_count = len(surface.y_mm)
        line_spacing = surface.spacing_y_mm
    else:
        line_count = len(surface.x_mm)
        line_spacing = surface.spacing_x_mm
    line_indices = _line_indices(line_count, line_spacing, settings.stepover_mm)

    moves: list[ToolpathMove] = []
    for line_number, line_index in enumerate(line_indices):
        if settings.axis is RasterAxis.X:
            valid = np.isfinite(contact.tip_z_mm[line_index, :])
        else:
            valid = np.isfinite(contact.tip_z_mm[:, line_index])
        runs = _contiguous_runs(valid)
        reverse = line_number % 2 == 1
        if reverse:
            runs = [run[::-1] for run in reversed(runs)]

        for run in runs:
            if run.size == 0:
                continue
            first = _sample_point(contact, settings.axis, line_index, int(run[0]))
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
            for sample_index in run[1:]:
                point = _sample_point(
                    contact,
                    settings.axis,
                    line_index,
                    int(sample_index),
                )
                moves.append(
                    ToolpathMove(
                        *point,
                        MoveKind.CUT,
                        settings.feed_mm_min,
                    )
                )
            last = moves[-1]
            moves.append(
                ToolpathMove(
                    last.x_mm,
                    last.y_mm,
                    settings.safe_z_mm,
                    MoveKind.RAPID,
                )
            )

    if not moves:
        raise ValueError("No raster moves could be generated from the contact map.")
    return Toolpath(
        name=name,
        operation="3d_finish_raster",
        cutter=contact.cutter,
        safe_z_mm=settings.safe_z_mm,
        moves=moves,
    )
