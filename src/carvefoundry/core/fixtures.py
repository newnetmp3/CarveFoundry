"""Physical keep-out zones expressed in the project stock coordinate system."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class Fixture:
    """Rectangle in stock-bottom-left XY; top Z relative to stock top (Z0).

    An external fence may have negative XY. Clearance includes an additional
    physical margin beyond cutter radius, not just the tool centre.
    """

    name: str
    x_min_mm: float
    y_min_mm: float
    x_max_mm: float
    y_max_mm: float
    top_z_mm: float
    clearance_mm: float = 2.0

    def validate(self) -> None:
        values = (
            self.x_min_mm, self.y_min_mm, self.x_max_mm, self.y_max_mm,
            self.top_z_mm, self.clearance_mm,
        )
        if not self.name.strip():
            raise ValueError("Fixture name is required.")
        if not all(isfinite(value) for value in values):
            raise ValueError("Fixture values must be finite.")
        if self.x_max_mm <= self.x_min_mm or self.y_max_mm <= self.y_min_mm:
            raise ValueError("Fixture must have positive XY width and height.")
        if self.clearance_mm < 0:
            raise ValueError("Fixture clearance must be nonnegative.")
