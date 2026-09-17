from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import dist, isfinite

from carvefoundry.core.tools import Cutter


class MoveKind(StrEnum):
    RAPID = "rapid"
    PLUNGE = "plunge"
    CUT = "cut"


@dataclass(frozen=True, slots=True)
class ToolpathMove:
    """One machine-space destination; ``kind`` describes the move to this point."""

    x_mm: float
    y_mm: float
    z_mm: float
    kind: MoveKind
    feed_mm_min: float | None = None

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.x_mm, self.y_mm, self.z_mm)):
            raise ValueError("Toolpath coordinates must be finite.")
        if self.kind is MoveKind.RAPID:
            if self.feed_mm_min is not None and self.feed_mm_min <= 0:
                raise ValueError("Rapid feed, when supplied, must be greater than zero.")
            return
        if self.feed_mm_min is None or not isfinite(self.feed_mm_min) or self.feed_mm_min <= 0:
            raise ValueError("Cutting and plunge moves require a positive finite feed.")

    @property
    def xyz(self) -> tuple[float, float, float]:
        return (self.x_mm, self.y_mm, self.z_mm)


@dataclass(slots=True)
class Toolpath:
    """Ordered machine moves for one CAM operation."""

    name: str
    operation: str
    cutter: Cutter
    safe_z_mm: float
    moves: list[ToolpathMove] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Toolpath name cannot be empty.")
        if not self.operation:
            raise ValueError("Toolpath operation cannot be empty.")
        if not isfinite(self.safe_z_mm):
            raise ValueError("safe_z_mm must be finite.")

    @property
    def bounds_xyz_mm(
        self,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        if not self.moves:
            return None
        x_values = [move.x_mm for move in self.moves]
        y_values = [move.y_mm for move in self.moves]
        z_values = [move.z_mm for move in self.moves]
        return (
            (min(x_values), min(y_values), min(z_values)),
            (max(x_values), max(y_values), max(z_values)),
        )

    @property
    def cutting_distance_mm(self) -> float:
        total = 0.0
        for previous, current in zip(self.moves, self.moves[1:]):
            if current.kind is not MoveKind.RAPID:
                total += dist(previous.xyz, current.xyz)
        return total

    @property
    def rapid_distance_mm(self) -> float:
        total = 0.0
        for previous, current in zip(self.moves, self.moves[1:]):
            if current.kind is MoveKind.RAPID:
                total += dist(previous.xyz, current.xyz)
        return total

    @property
    def estimated_cutting_minutes(self) -> float:
        """Feed-based cut/plunge time, excluding controller-specific rapid time."""

        total_minutes = 0.0
        for previous, current in zip(self.moves, self.moves[1:]):
            if current.kind is MoveKind.RAPID:
                continue
            assert current.feed_mm_min is not None
            total_minutes += dist(previous.xyz, current.xyz) / current.feed_mm_min
        return total_minutes
