from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from math import radians, sqrt, tan


class ToolType(StrEnum):
    FLAT_END_MILL = "flat_end_mill"
    BALL_NOSE = "ball_nose"
    V_BIT = "v_bit"
    ENGRAVING_CONE = "engraving_cone"
    TAPERED_BALL_NOSE = "tapered_ball_nose"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class Cutter:
    """Physical cutter geometry used by CAM compensation.

    ``profile_height_mm(radius)`` returns the height of the cutter surface above
    the tool tip at a radial distance from the tool axis. CAM strategies can use
    this profile rather than assuming every finishing cutter is a ball nose.
    """

    name: str
    tool_type: ToolType
    diameter_mm: float
    angle_deg: float | None = None
    tip_diameter_mm: float = 0.0
    taper_angle_deg: float | None = None
    ball_radius_mm: float | None = None
    profile_points: tuple[tuple[float, float], ...] | None = None

    def __post_init__(self) -> None:
        if self.diameter_mm <= 0:
            raise ValueError("diameter_mm must be greater than zero")
        if self.tip_diameter_mm < 0 or self.tip_diameter_mm > self.diameter_mm:
            raise ValueError("tip_diameter_mm must be between zero and tool diameter")
        if (
            self.tool_type in {ToolType.V_BIT, ToolType.ENGRAVING_CONE}
            and (self.angle_deg is None or not 0 < self.angle_deg < 180)
        ):
            raise ValueError(
                "conical cutters require an included angle between 0 and 180 degrees"
            )
        if self.tool_type is ToolType.TAPERED_BALL_NOSE:
            if self.ball_radius_mm is None or self.ball_radius_mm <= 0:
                raise ValueError("tapered ball nose requires ball_radius_mm")
            if self.taper_angle_deg is None or not 0 < self.taper_angle_deg < 90:
                raise ValueError(
                    "tapered ball nose requires a taper angle between 0 and 90 degrees"
                )

        if self.tool_type is ToolType.CUSTOM and self.profile_points is not None:
            points = self.profile_points
            if len(points) < 2:
                raise ValueError("custom cutters require at least two profile points")
            radii = [float(point[0]) for point in points]
            heights = [float(point[1]) for point in points]
            if radii[0] != 0.0:
                raise ValueError("custom cutter profile must start at radius 0")
            if any(radius < 0 for radius in radii):
                raise ValueError("custom cutter profile radii cannot be negative")
            if any(height < 0 for height in heights):
                raise ValueError("custom cutter profile heights cannot be negative")
            if any(next_radius <= radius for radius, next_radius in pairwise(radii)):
                raise ValueError("custom cutter profile radii must increase strictly")
            if radii[-1] > self.radius_mm + 1e-9:
                raise ValueError("custom cutter profile exceeds the cutter radius")

    @property
    def radius_mm(self) -> float:
        return self.diameter_mm / 2.0

    def profile_height_mm(self, radial_distance_mm: float) -> float:
        """Return cutter surface height above the tool tip at ``radial_distance_mm``.

        This rotational profile is the basis for cutter-contact offsetting. The
        returned profile is valid within the cutter's nominal radius.
        """
        r = abs(float(radial_distance_mm))
        if r > self.radius_mm + 1e-9:
            raise ValueError("radial distance lies outside the cutter diameter")

        if self.tool_type is ToolType.FLAT_END_MILL:
            return 0.0

        if self.tool_type is ToolType.BALL_NOSE:
            radius = self.radius_mm
            return radius - sqrt(max(0.0, radius * radius - r * r))

        if self.tool_type in {ToolType.V_BIT, ToolType.ENGRAVING_CONE}:
            tip_radius = self.tip_diameter_mm / 2.0
            if r <= tip_radius:
                return 0.0
            half_angle = radians(self.angle_deg / 2.0)  # type: ignore[operator]
            return (r - tip_radius) / tan(half_angle)

        if self.tool_type is ToolType.TAPERED_BALL_NOSE:
            ball_radius = float(self.ball_radius_mm)
            if r <= ball_radius:
                return ball_radius - sqrt(max(0.0, ball_radius * ball_radius - r * r))
            ball_equator_height = ball_radius
            taper = radians(float(self.taper_angle_deg))
            return ball_equator_height + (r - ball_radius) / tan(taper)

        if self.tool_type is ToolType.CUSTOM:
            if self.profile_points is None:
                raise NotImplementedError(
                    "custom cutter requires a defined radial profile curve"
                )
            radii = [float(point[0]) for point in self.profile_points]
            heights = [float(point[1]) for point in self.profile_points]
            if r >= radii[-1]:
                return heights[-1]
            right_index = bisect_right(radii, r)
            left_index = max(0, right_index - 1)
            right_index = min(right_index, len(radii) - 1)
            left_radius = radii[left_index]
            right_radius = radii[right_index]
            left_height = heights[left_index]
            right_height = heights[right_index]
            if right_radius <= left_radius:
                return left_height
            fraction = (r - left_radius) / (right_radius - left_radius)
            return left_height + fraction * (right_height - left_height)

        raise NotImplementedError(f"Unsupported cutter type: {self.tool_type}")


DEFAULT_TOOLS: tuple[Cutter, ...] = (
    Cutter("1/4 in Flat End Mill", ToolType.FLAT_END_MILL, 6.35),
    Cutter("1/8 in Ball Nose", ToolType.BALL_NOSE, 3.175),
    Cutter("22° V-Bit", ToolType.V_BIT, 6.35, angle_deg=22.0),
    Cutter(
        "60° Engraving Bit",
        ToolType.ENGRAVING_CONE,
        6.0,
        angle_deg=60.0,
        tip_diameter_mm=0.2,
    ),
)
