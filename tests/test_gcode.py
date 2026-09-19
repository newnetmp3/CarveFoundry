from pathlib import Path

from carvefoundry.cam.gcode import (
    GrblPostSettings,
    normalize_gcode_path,
    render_grbl,
    render_grbl_program,
    write_grbl,
    write_grbl_program,
)
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


def test_gcode_path_defaults_to_nc_for_missing_or_unknown_suffix(tmp_path: Path) -> None:
    assert normalize_gcode_path(tmp_path / "finish").name == "finish.nc"
    assert normalize_gcode_path(tmp_path / "finish.txt").name == "finish.nc"
    assert normalize_gcode_path(tmp_path / "finish.gcode").name == "finish.gcode"


def test_write_grbl_replaces_unknown_suffix_with_nc(tmp_path: Path) -> None:
    path = write_grbl(_toolpath(), tmp_path / "finish.txt")

    assert path.name == "finish.nc"
    assert path.is_file()
    assert not (tmp_path / "finish.txt").exists()
    assert not (tmp_path / "finish.nc.tmp").exists()


def test_multi_operation_program_has_one_header_and_one_end() -> None:
    first = _toolpath()
    second = _toolpath()
    second.name = "Cutout"

    program = render_grbl_program([first, second])
    lines = program.splitlines()

    assert lines.count("G90") == 1
    assert lines.count("G21") == 1
    assert lines.count("M2") == 1
    assert "(Operation 1: Finish)" in lines
    assert "(Operation 2: Cutout)" in lines


def test_write_multi_operation_grbl(tmp_path: Path) -> None:
    path = write_grbl_program(
        [_toolpath(), _toolpath()],
        tmp_path / "combined.nc",
    )

    text = path.read_text(encoding="ascii")
    assert text.count("(Operation ") == 2
    assert text.endswith("M2\n")


def test_center_work_zero_offsets_output_coordinates() -> None:
    program = render_grbl(
        _toolpath(),
        GrblPostSettings(x_offset_mm=-50.0, y_offset_mm=-25.0),
    )
    lines = program.splitlines()

    assert "G0 X-49 Y-23 Z5" in lines
    assert "G1 X-48 Y-23 Z-1.25 F1200" in lines


def test_parking_is_emitted_once_after_final_retract() -> None:
    options = GrblPostSettings(
        park_enabled=True,
        park_x_mm=10.0,
        park_y_mm=20.0,
        park_z_mm=12.0,
    )
    program = render_grbl_program([_toolpath(), _toolpath()], options)
    lines = program.splitlines()

    assert lines.count("(Park)") == 1
    park_index = lines.index("(Park)")
    assert lines[park_index + 1] == "G0 Z12"
    assert lines[park_index + 2] == "G0 X10 Y20"
    assert lines[-1] == "M2"
