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
    adjacent = Fixture("Nearby fence", 30, 12.4, 35, 15, 4, 1)
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
        Cutter("3 mm flat", ToolType.FLAT_END_MILL, 3.0), 4,
        [
            ToolpathMove(10, 10, 4, MoveKind.RAPID),
            ToolpathMove(60, 10, 4, MoveKind.RAPID),
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


def test_multi_cutter_export_creates_separate_ordered_programs(tmp_path: Path) -> None:
    flat = _path()
    vbit = _path()
    vbit.name = "V detail"
    vbit.cutter = Cutter("22 degree V-bit", ToolType.V_BIT, 6.35, angle_deg=22)
    flat_again = _path()
    flat_again.name = "Final cleanup"
    result = run_gcode(GcodeRequest(
        toolpaths=[flat, vbit, flat_again],
        path=str(tmp_path / "multi.nc"),
        settings=GrblPostSettings(),
        stock=Stock(80, 40, 18),
        machine_profile=_profile(),
    ))
    files = [Path(file) for file in result["files"]]
    assert len(files) == 3
    assert len({f.name for f in files}) == 3
    assert "tool01" in files[0].name
    assert "tool02" in files[1].name
    assert "tool03" in files[2].name
    for output in files:
        gcode = output.read_text(encoding="ascii")
        assert gcode.count("M2") == 1
        assert gcode.count("(Cutter:") == 1
    assert not (tmp_path / "multi.nc").exists()


def test_adjacent_operations_with_same_cutter_share_one_file(tmp_path: Path) -> None:
    first = _path()
    next_one = _path()
    next_one.name = "Finish detail"
    result = run_gcode(GcodeRequest(
        toolpaths=[first, next_one],
        path=str(tmp_path / "same-cutter.nc"),
        settings=GrblPostSettings(),
        stock=Stock(80, 40, 18),
        machine_profile=_profile(),
    ))
    assert result["files"] == [str(tmp_path / "same-cutter.nc")]
    assert "(Operation 1: Detail)" in (tmp_path / "same-cutter.nc").read_text()
    assert "(Operation 2: Finish detail)" in (tmp_path / "same-cutter.nc").read_text()


def test_park_collision_uses_postprocessor_work_zero_offsets() -> None:
    # G-code park X-40 with X offset -40 corresponds to stock X0,
    # so a fixture entirely at negative stock X is not crossed.
    fixture = Fixture("Outside fence", -15, 8, -10, 12, 5, 1)
    options = GrblPostSettings(
        x_offset_mm=-40,
        park_enabled=True,
        park_x_mm=-40,
        park_y_mm=10,
        park_z_mm=3,
    )
    result = check_preflight(
        [_path()], Stock(80, 40, 18), _profile(),
        [fixture], options,
    )
    assert result.safe_to_export
