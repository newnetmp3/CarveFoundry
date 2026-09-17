import pytest

from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.tools import Cutter, ToolType


def test_cut_move_requires_positive_feed() -> None:
    with pytest.raises(ValueError, match="positive finite feed"):
        ToolpathMove(0.0, 0.0, 0.0, MoveKind.CUT)


def test_toolpath_reports_cut_and_rapid_distances() -> None:
    cutter = Cutter("flat", ToolType.FLAT_END_MILL, 2.0)
    path = Toolpath(
        "Example",
        "test",
        cutter,
        5.0,
        [
            ToolpathMove(0.0, 0.0, 5.0, MoveKind.RAPID),
            ToolpathMove(0.0, 0.0, 0.0, MoveKind.PLUNGE, 100.0),
            ToolpathMove(3.0, 4.0, 0.0, MoveKind.CUT, 200.0),
            ToolpathMove(3.0, 4.0, 5.0, MoveKind.RAPID),
        ],
    )

    assert path.cutting_distance_mm == pytest.approx(10.0)
    assert path.rapid_distance_mm == pytest.approx(5.0)
    assert path.estimated_cutting_minutes == pytest.approx(5.0 / 100.0 + 5.0 / 200.0)
