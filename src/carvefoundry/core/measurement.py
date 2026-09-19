"""Planar stock-top measurements from two picked viewport coordinates."""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot, isfinite


@dataclass(frozen=True, slots=True)
class Measurement:
    start_xy: tuple[float, float]
    end_xy: tuple[float, float]
    delta_x_mm: float
    delta_y_mm: float
    distance_mm: float
    angle_deg: float

    @property
    def label(self) -> str:
        return (
            f"Length {self.distance_mm:.3f} mm · "
            f"ΔX {self.delta_x_mm:+.3f} mm · "
            f"ΔY {self.delta_y_mm:+.3f} mm · "
            f"Angle {self.angle_deg:+.2f}°"
        )


def measure_xy(
    start_xy: tuple[float, float], end_xy: tuple[float, float],
) -> Measurement:
    """Measure an XY segment at stock-top Z0; angle is CCW from +X."""
    values = (*start_xy, *end_xy)
    if not all(isfinite(value) for value in values):
        raise ValueError("Measurement endpoints must be finite.")
    dx = float(end_xy[0] - start_xy[0])
    dy = float(end_xy[1] - start_xy[1])
    return Measurement(
        start_xy=(float(start_xy[0]), float(start_xy[1])),
        end_xy=(float(end_xy[0]), float(end_xy[1])),
        delta_x_mm=dx,
        delta_y_mm=dy,
        distance_mm=hypot(dx, dy),
        angle_deg=degrees(atan2(dy, dx)),
    )
