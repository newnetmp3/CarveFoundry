from __future__ import annotations

import math

import pytest

from carvefoundry.core.tools import Cutter, ToolType


def test_flat_end_profile_is_flat() -> None:
    tool = Cutter("flat", ToolType.FLAT_END_MILL, 6.0)
    assert tool.profile_height_mm(0.0) == 0.0
    assert tool.profile_height_mm(3.0) == 0.0


def test_ball_nose_profile_reaches_radius_at_edge() -> None:
    tool = Cutter("ball", ToolType.BALL_NOSE, 6.0)
    assert tool.profile_height_mm(0.0) == pytest.approx(0.0)
    assert tool.profile_height_mm(3.0) == pytest.approx(3.0)


def test_v_bit_profile_uses_included_angle() -> None:
    tool = Cutter("v", ToolType.V_BIT, 10.0, angle_deg=90.0)
    assert tool.profile_height_mm(2.0) == pytest.approx(2.0)


def test_conical_tool_respects_flat_tip() -> None:
    tool = Cutter(
        "engraver",
        ToolType.ENGRAVING_CONE,
        6.0,
        angle_deg=60.0,
        tip_diameter_mm=0.4,
    )
    assert tool.profile_height_mm(0.19) == 0.0
    expected = (1.0 - 0.2) / math.tan(math.radians(30.0))
    assert tool.profile_height_mm(1.0) == pytest.approx(expected)


def test_invalid_radius_rejected() -> None:
    tool = Cutter("flat", ToolType.FLAT_END_MILL, 6.0)
    with pytest.raises(ValueError):
        tool.profile_height_mm(3.1)
