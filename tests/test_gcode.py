from pathlib import Path

from carvefoundry.cam.gcode import render_grbl, write_grbl
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.tools import Cutter, ToolType


def _toolpath() -> Toolpath:
    cutter = Cutter("3 mm ball", ToolType.BALL_NOSE, 3.0)
    return Toolpath(
        "Finish",
        "3d_finish_raster",
        cutter,
        5.0,
        [
            ToolpathMove(1.0, 2.0, 5.0, MoveKind.RAPID),
            ToolpathMove(1.0, 2.0, -1.0, MoveKind.PLUNGE, 300.0),
            ToolpathMove(2.0, 2.0, -1.25, MoveKind.CUT, 1200.0),
            ToolpathMove(2.0, 2.0, 5.0, MoveKind.RAPID),
        ],
    )


def test_grbl_output_is_metric_absolute_and_retracts_first() -> None:
    program = render_grbl(_toolpath())
    lines = program.splitlines()

    assert "G90" in lines
    assert "G21" in lines
    assert lines.index("G0 Z5") < lines.index("G0 X1 Y2 Z5")
    assert "G1 X1 Y2 Z-1 F300" in lines
    assert "G1 X2 Y2 Z-1.25 F1200" in lines
    assert lines[-1] == "M2"


def test_write_grbl_creates_plain_nc_file(tmp_path: Path) -> None:
    path = write_grbl(_toolpath(), tmp_path / "finish.nc")

    assert path.name == "finish.nc"
    assert path.read_text(encoding="ascii").endswith("M2\n")
