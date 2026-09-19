from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import ceil, hypot

import numpy as np

from carvefoundry.core.tools import Cutter

from .heightfield import HeightField
from .native import compensate_height_field as _native_compensate_height_field

FootprintSample = tuple[int, int, float]


@dataclass(frozen=True, slots=True)
class CutterContactMap:
    """Required tool-tip Z at each XY center position for one cutter geometry."""

    surface: HeightField
    cutter: Cutter
    tip_z_mm: np.ndarray

    def __post_init__(self) -> None:
        tip = np.asarray(self.tip_z_mm, dtype=float)
        if tip.shape != self.surface.z_mm.shape:
            raise ValueError("Cutter contact map must match the source height-field shape.")
        object.__setattr__(self, "tip_z_mm", tip)

    @property
    def valid_mask(self) -> np.ndarray:
        return np.isfinite(self.tip_z_mm)


def _aligned_slices(length: int, offset: int) -> tuple[slice, slice]:
    """Return destination/source slices where source index equals destination + offset."""

    if offset >= 0:
        return slice(0, length - offset), slice(offset, length)
    return slice(-offset, length), slice(0, length + offset)


def _cutter_footprint(surface: HeightField, cutter: Cutter) -> list[FootprintSample]:
    """Precompute the small radial cutter profile shared by both CAM backends."""

    radius = cutter.radius_mm
    max_dx = ceil(radius / surface.spacing_x_mm)
    max_dy = ceil(radius / surface.spacing_y_mm)
    footprint: list[FootprintSample] = []

    for offset_y in range(-max_dy, max_dy + 1):
        dy = offset_y * surface.spacing_y_mm
        for offset_x in range(-max_dx, max_dx + 1):
            dx = offset_x * surface.spacing_x_mm
            distance = hypot(dx, dy)
            if distance > radius + 1e-9:
                continue
            footprint.append(
                (offset_y, offset_x, float(cutter.profile_height_mm(distance)))
            )

    return footprint


def _compensate_height_field_python(
    source_z: np.ndarray,
    footprint: Sequence[FootprintSample],
    *,
    progress: Callable[[float], None] | None = None,
) -> np.ndarray:
    """Readable reference implementation for cutter-profile compensation."""

    result = np.full(source_z.shape, -np.inf, dtype=float)
    touched = np.zeros(source_z.shape, dtype=bool)
    height, width = source_z.shape
    footprint_count = max(1, len(footprint))

    for sample_index, (offset_y, offset_x, profile_height) in enumerate(footprint):
        destination_y, source_y = _aligned_slices(height, offset_y)
        destination_x, source_x = _aligned_slices(width, offset_x)
        source_view = source_z[source_y, source_x]
        valid = np.isfinite(source_view)
        if valid.any():
            result_view = result[destination_y, destination_x]
            candidate = source_view - profile_height
            np.maximum(
                result_view,
                np.where(valid, candidate, -np.inf),
                out=result_view,
            )
            touched[destination_y, destination_x] |= valid

        if progress is not None:
            progress((sample_index + 1) / footprint_count)

    result[~touched] = np.nan
    return result


def compensate_height_field(
    surface: HeightField,
    cutter: Cutter,
    *,
    progress: Callable[[float], None] | None = None,
) -> CutterContactMap:
    """Compute a collision-safe tool-tip height map from the cutter's actual profile.

    For every tool center, the cutter surface must remain at or above every
    sampled model point inside its radius. With profile_height_mm(r) defined as
    cutter height above the tip, the required tip Z is therefore the maximum
    of surface_z - profile_height over the cutter footprint.

    The cutter profile itself stays in Python so there is one authoritative
    definition for every tool type. Rust receives only the precomputed radial
    footprint and performs the large grid calculation. This keeps the native
    boundary small and makes backend parity straightforward to debug.
    """

    source_z = surface.z_mm
    footprint = _cutter_footprint(surface, cutter)

    if progress is not None:
        progress(0.0)
    result = _native_compensate_height_field(source_z, footprint)
    if result is None:
        result = _compensate_height_field_python(
            source_z,
            footprint,
            progress=progress,
        )
    elif progress is not None:
        progress(1.0)

    return CutterContactMap(surface=surface, cutter=cutter, tip_z_mm=result)
