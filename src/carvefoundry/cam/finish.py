from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from collections.abc import Callable

import numpy as np
import trimesh

from carvefoundry.core.tools import Cutter

from .contact import CutterContactMap, compensate_height_field
from .heightfield import HeightField
from .raster import RasterFinishingSettings, generate_raster_finishing
from .toolpath import Toolpath


@dataclass(frozen=True, slots=True)
class Finish3DSettings:
    """Parameters shared by surface sampling and the raster finishing strategy."""

    surface_spacing_mm: float
    raster: RasterFinishingSettings
    max_surface_samples: int = 2_000_000
    surface_padding_mm: float = 0.0
    background_z_mm: float | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.surface_spacing_mm) or self.surface_spacing_mm <= 0:
            raise ValueError("surface_spacing_mm must be finite and greater than zero.")
        if self.max_surface_samples < 4:
            raise ValueError("max_surface_samples must be at least four.")
        if not isfinite(self.surface_padding_mm) or self.surface_padding_mm < 0:
            raise ValueError("surface_padding_mm must be finite and non-negative.")
        if self.background_z_mm is not None and not isfinite(self.background_z_mm):
            raise ValueError("background_z_mm must be finite when supplied.")


@dataclass(frozen=True, slots=True)
class Finish3DResult:
    surface: HeightField
    contact: CutterContactMap
    toolpath: Toolpath


def _estimated_sample_count(
    mesh: trimesh.Trimesh,
    spacing_mm: float,
    padding_mm: float = 0.0,
) -> int:
    bounds = np.asarray(mesh.bounds, dtype=float)
    span = bounds[1, :2] - bounds[0, :2] + 2.0 * padding_mm
    if np.any(span <= 0):
        raise ValueError("Mesh must have non-zero XY dimensions for 3-axis finishing.")
    x_count = max(2, ceil(float(span[0]) / spacing_mm) + 1)
    y_count = max(2, ceil(float(span[1]) / spacing_mm) + 1)
    return x_count * y_count


def calculate_3d_finish(
    mesh_mm: trimesh.Trimesh,
    cutter: Cutter,
    settings: Finish3DSettings,
    *,
    name: str = "3D Finish",
    progress: Callable[[float, str], None] | None = None,
) -> Finish3DResult:
    """Run the geometry-safe baseline 3D finishing pipeline.

    ``mesh_mm`` must already be transformed into project/machine millimeter
    coordinates. Cutter compensation is performed from the selected cutter's
    radial profile; no cutter family is substituted or approximated as a ball.
    """

    sample_count = _estimated_sample_count(
        mesh_mm,
        settings.surface_spacing_mm,
        settings.surface_padding_mm,
    )
    if sample_count > settings.max_surface_samples:
        raise ValueError(
            f"Requested surface grid would contain {sample_count:,} samples; "
            f"limit is {settings.max_surface_samples:,}. Increase surface spacing."
        )

    if progress is not None:
        progress(0.0, "Sampling 3D surface")
    surface = HeightField.from_mesh_top_surface(
        mesh_mm,
        spacing_mm=settings.surface_spacing_mm,
        padding_mm=settings.surface_padding_mm,
        fill_missing_z_mm=settings.background_z_mm,
        progress=(
            (lambda value: progress(0.45 * value, "Sampling 3D surface"))
            if progress is not None
            else None
        ),
    )
    if progress is not None:
        progress(0.45, "Compensating for cutter geometry")
    contact = compensate_height_field(
        surface,
        cutter,
        progress=(
            (
                lambda value: progress(
                    0.45 + 0.30 * value,
                    "Compensating for cutter geometry",
                )
            )
            if progress is not None
            else None
        ),
    )
    if progress is not None:
        progress(0.75, "Building optimized raster path")
    toolpath = generate_raster_finishing(
        contact,
        settings.raster,
        name=name,
        progress=(
            (
                lambda value: progress(
                    0.75 + 0.25 * value,
                    "Building optimized raster path",
                )
            )
            if progress is not None
            else None
        ),
    )
    if progress is not None:
        progress(1.0, "3D path ready")
    return Finish3DResult(surface=surface, contact=contact, toolpath=toolpath)
