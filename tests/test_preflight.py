"""Physical safety and export integration regression tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from carvefoundry.cam.gcode import GrblPostSettings
from carvefoundry.cam.job_process import GcodeRequest, run_gcode
from carvefoundry.cam.job_workflows import TilingSettings
from carvefoundry.cam.preflight import check_preflight
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.machine_profiles import MachineProfile
from carvefoundry.core.project import Stock
from carvefoundry.core.tools import Cutter, ToolType


def _path(*, rapid_z: float = 5.0, cut_z: float = -1.0) -> Toolpath:
    return Toolpath(
        "Detail", "engrave",
        Cutter("3 mm flat", ToolType.FLAT_END_MILL, 3.0),
        rapid_z,
        [
            ToolpathMove(10, 10, rapid_z, MoveKind.RAPID),
            ToolpathMove(10, 10, cut_z, MoveKind.PLUNGE, 120),
            ToolpathMove(60, 10, cut_z, MoveKind.CUT, 500),
            ToolpathMove(60, 10, rapid_z, MoveKind.RAPID),
        ],
    )


def _profile(*, x: float = 100, y: float = 80) -> MachineProfile:
    return MachineProfile(work_x_mm=x, work_y_mm=y, work_z_mm=80)


def _fence() -> Fixture:
    return Fixture("Crossbar clamp", 30, 8, 35, 12, 4, 1)


def test_fixture_cut_crossing_is_a_hard_error() -> None:
    result = check_preflight(
        [_path()], Stock(80, 40, 18), _profile(),
        [_fence()],
    )
    assert not result.safe_to_export
    assert any(f.code == "FIXTURE_COLLISION" for f in result.findings)
    assert "Crossbar clamp" in result.format_report()


def test_fixture_collision_considers_cutter_radius_and_clearance() -> None:
    adjacent = Fixture("Nearby fence", 30, 12.6, 35, 15, 4, 1)
    result = check_preflight(
        [_path()], Stock(80, 40, 18), _profile(),
        [adjacent],
    )
    assert not result.safe_to_export


def test_raised_rapid_crossing_can_clear_fixture() -> None:
    path = Toolpath(
        "Raised travel", "engrave",
        Cutter("3 mm flat", ToolType.FLAT_END_MILL, 3.0), 10,
        [
            ToolpathMove(10, 10, 10, MoveKind.RAPID),
            ToolpathMove(60, 10, 10, MoveKind.RAPID),
            ToolpathMove(60, 10, -1, MoveKind.PLUNGE, 100),
            ToolpathMove(60, 10, 10, MoveKind.RAPID),
        ],
    )
    result = check_preflight(
        [path], Stock(80, 40, 18), _profile(), [_fence()]
    )
    assert result.safe_to_export
    assert result.checked_moves == 4


def test_rapid_crossing_too_low_is_blocked() -> None:
    path = Toolpath(
        "Low travel", "engrave",
        Cutter("3 mm flat", ToolType.FLAT_END_MILL, 3.0), 5,
        [
            ToolpathMove(10, 10, 5, MoveKind.RAPID),
            ToolpathMove(60, 10, 5, MoveKind.RAPID),
        ],
    )
    result = check_preflight(
        [path], Stock(80, 40, 18), _profile(), [_fence()]
    )
    assert not result.safe_to_export


def test_stock_depth_and_machine_travel_are_checked() -> None:
    result = check_preflight(
        [_path(cut_z=-20)], Stock(80, 40, 18),
        _profile(x=70), [],
    )
    codes = {f.code for f in result.findings}
    assert "THROUGH_STOCK" in codes
    assert "STOCK_TRAVEL_X" in codes


def test_valid_export_writes_nc_only_after_preflight(tmp_path: Path) -> None:
    output = tmp_path / "good.nc"
    result = run_gcode(GcodeRequest(
        toolpaths=[_path()], path=str(output),
        settings=GrblPostSettings(),
        stock=Stock(80, 40, 18),
        machine_profile=_profile(),
        fixtures=(),
    ))
    assert result["files"] == [str(output)]
    assert output.read_text(encoding="ascii").endswith("M2\n")


def test_blocked_export_does_not_create_any_nc(tmp_path: Path) -> None:
    output = tmp_path / "unsafe.nc"
    with pytest.raises(ValueError, match="Preflight BLOCKED"):
        run_gcode(GcodeRequest(
            toolpaths=[_path()], path=str(output),
            settings=GrblPostSettings(),
            stock=Stock(80, 40, 18),
            machine_profile=_profile(),
            fixtures=(_fence(),),
        ))
    assert not output.exists()


def test_report_only_does_not_write_a_file(tmp_path: Path) -> None:
    output = tmp_path / "never.nc"
    result = run_gcode(GcodeRequest(
        toolpaths=[_path()], path=str(output),
        settings=GrblPostSettings(),
        mode="preflight",
        stock=Stock(80, 40, 18),
        machine_profile=_profile(),
        fixtures=(_fence(),),
    ))
    assert not result["safe_to_export"]
    assert "Crossbar clamp" in result["report"]
    assert not output.exists()


def test_tiled_preflight_allows_stock_larger_than_machine(tmp_path: Path) -> None:
    output = tmp_path / "tiles.nc"
    result = run_gcode(GcodeRequest(
        toolpaths=[_path()], path=str(output),
        settings=GrblPostSettings(),
        mode="tiles",
        tile_settings=TilingSettings(45, 40, 3, True),
        stock_width_mm=80,
        stock_height_mm=40,
        stock=Stock(80, 40, 18),
        machine_profile=_profile(x=50, y=45),
    ))
    assert len(result["files"]) >= 2
    assert all(Path(file).is_file() for file in result["files"])


def test_tiled_preflight_checks_all_tiles_before_writing(tmp_path: Path) -> None:
    output = tmp_path / "tiles.nc"
    with pytest.raises(ValueError, match="Tile row"):
        run_gcode(GcodeRequest(
            toolpaths=[_path()], path=str(output),
            settings=GrblPostSettings(),
            mode="tiles",
            tile_settings=TilingSettings(45, 40, 3, True),
            stock_width_mm=80,
            stock_height_mm=40,
            stock=Stock(80, 40, 18),
            machine_profile=_profile(x=50, y=45),
            fixtures=(_fence(),),
        ))
    assert not list(tmp_path.glob("tiles_r*_c*.nc"))


def test_fixture_validation_rejects_invalid_rectangles() -> None:
    with pytest.raises(ValueError, match="positive XY"):
        Fixture("Clamp", 5, 0, 5, 10, 3).validate()
