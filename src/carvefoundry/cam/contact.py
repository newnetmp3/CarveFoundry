from __future__ import annotations

from dataclasses import dataclass
from math import ceil, hypot

import numpy as np

from carvefoundry.core.tools import Cutter

from .heightfield import HeightField


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


def compensate_height_field(surface: HeightField, cutter: Cutter) -> CutterContactMap:
    """Compute a collision-safe tool-tip height map from the cutter's actual profile.

    For every tool center, the cutter surface must remain at or above every
    sampled model point inside its radius. With ``profile_height_mm(r)`` defined
    as cutter height above the tip, the required tip Z is therefore the maximum
    of ``surface_z - profile_height`` over the cutter footprint.

    Samples outside the supplied height field are intentionally unknown rather
    than assumed clear; machining boundaries are handled by higher CAM layers.
    """

    source_z = surface.z_mm
    result = np.full(source_z.shape, -np.inf, dtype=float)
    touched = np.zeros(source_z.shape, dtype=bool)
    radius = cutter.radius_mm
    max_dx = int(ceil(radius / surface.spacing_x_mm))
    max_dy = int(ceil(radius / surface.spacing_y_mm))

    for offset_y in range(-max_dy, max_dy + 1):
        dy = offset_y * surface.spacing_y_mm
        destination_y, source_y = _aligned_slices(len(surface.y_mm), offset_y)
        for offset_x in range(-max_dx, max_dx + 1):
            dx = offset_x * surface.spacing_x_mm
            distance = hypot(dx, dy)
            if distance > radius + 1e-9:
                continue
            profile_height = cutter.profile_height_mm(distance)
            destination_x, source_x = _aligned_slices(len(surface.x_mm), offset_x)
            source_view = source_z[source_y, source_x]
            valid = np.isfinite(source_view)
            if not valid.any():
                continue
            result_view = result[destination_y, destination_x]
            candidate = source_view - profile_height
            np.maximum(result_view, np.where(valid, candidate, -np.inf), out=result_view)
            touched[destination_y, destination_x] |= valid

    result[~touched] = np.nan
    return CutterContactMap(surface=surface, cutter=cutter, tip_z_mm=result)
