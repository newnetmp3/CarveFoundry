"""Verify actual GRBL output independently of the planned toolpath."""
from __future__ import annotations

from pathlib import Path

import pytest

from carvefoundry.cam.gcode import GrblPostSettings, render_grbl_program
from carvefoundry.cam.gcode_verify import decode_grbl, verify_grbl_export
from carvefoundry.cam.job_process import GcodeRequest, run_gcode
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.machine_profiles import MachineProfile
from carvefoundry.core.project import Stock
from carvefoundry.core.tools import Cutter, ToolType


def stage(*, cutter=None) -> Toolpath:
    return Toolpath(
        "Detail", "engrave",
        cutter or Cutter("flat", ToolType.FLAT_END_MILL, 3.0),
        6,
        [
            ToolpathMove(8, 8, 6, MoveKind.RAPID),
            ToolpathMove(8, 8, -2, MoveKind.PLUNGE, 120),
            ToolpathMove(28, 8, -2, MoveKind.CUT, 400),
            ToolpathMove(28, 8, 6, MoveKind.RAPID),
        ],
    )


def context():
    return Stock(40, 30, 15), MachineProfile(
        work_x_mm=300, work_y_mm=300, work_z_mm=100,
    )


def verify(program: str, toolpaths=None, fixtures=(), options=None):
    stock, machine = context()
    paths = [stage()] if toolpaths is None else toolpaths
    return verify_grbl_export(
        program, paths, stock, machine, fixtures,
        options or GrblPostSettings(),
    )


def test_independent_parser_recovers_written_moves_and_retracts():
    path = stage()
    code = render_grbl_program([path])
    decoded = decode_grbl(code)
    assert decoded.initial_safe_z_mm == 6
    assert len(decoded.moves) == len(path.moves) + 1
    assert decoded.moves[1].xyz == (8, 8, -2)
    assert decoded.moves[1].feed_mm_min == 120
    assert decoded.moves[-1].kind is MoveKind.RAPID
    assert verify(code).safe_to_export


def test_modal_incremental_inches_and_feed_conversion():
    code = (
        "G20 G90 G17 G94\n"
        "G0 Z0.25\n"
        "G0 X0.5 Y0.5\n"
        "G91\n"
        "F10 G1 Z-0.1\n"
        "G1 X0.25\n"
        "G0 Z0.1\n"
        "M2\n"
    )
    result = decode_grbl(code)
    assert result.moves[0].xyz == pytest.approx((12.7, 12.7, 6.35))
    assert result.moves[1].xyz == pytest.approx((12.7, 12.7, 3.81))
    assert result.moves[1].feed_mm_min == pytest.approx(254)
    assert result.moves[2].xyz == pytest.approx((19.05, 12.7, 3.81))


@pytest.mark.parametrize(
    "bad,match",
    [
        ("G90 G21\nG0 X0 Y0 Z5\nG2 X1 Y1 I0 J1\nM2\n", "unsupported G2"),
        ("G90 G21\nG53 G0 X0 Y0 Z5\nM2\n", "unsupported G53"),
        ("G90 G21\nG0 X0 Y0 Z5\nG1 X1 Z-1\nM2\n", "no feed"),
        ("G90 G21\nG0 X0 Y0 Z5\nG0 X1 Y1\n", "no M2"),
        ("G90 G21\nG0 X0 Y0 Z5\nM2\nG1 X1\n", "after program end"),
        ("G90 G21\nG0 X0 Y0 Z5\nG1 X1 Y1 Z-1 F-10\nM2\n", "feed must"),
        ("G90 G21\nG0 X0 Y0 Z5\nG92 X10\nM2\n", "unsupported G92"),
    ],
)
def test_unsupported_and_malformed_programs_fail_closed(bad, match):
    with pytest.raises(ValueError, match=match):
        decode_grbl(bad)


def test_posted_cut_xyz_and_feed_are_compared_to_source():
    original = render_grbl_program([stage()])
    with pytest.raises(ValueError, match="posted cut"):
        verify(original.replace("X28 Y8 Z-2", "X27 Y8 Z-2"))
    with pytest.raises(ValueError, match="posted feed"):
        verify(original.replace(" F400", " F401"))


def test_verified_posted_fixture_collision_detected_on_rapid():
    fixture = Fixture("Fence", 17, 7, 19, 9, 4, 0.5)
    path = stage()
    # The planned cutting pass would itself cross this fixture, so demonstrate
    # the independent NC check with a safe planned path and injected G0 sweep.
    path.moves[2] = ToolpathMove(9, 8, -2, MoveKind.CUT, 400)
    path.moves[3] = ToolpathMove(9, 8, 6, MoveKind.RAPID)
    output = render_grbl_program([path])
    malicious = output.replace("M2\n", "G0 X30 Y8 Z1\nM2\n")
    outcome = verify(malicious, [path], (fixture,))
    assert not outcome.safe_to_export
    assert any(f.code == "FIXTURE_COLLISION" for f in outcome.preflight.findings)
    assert verify(output, [path], (fixture,)).safe_to_export


def test_detects_lateral_rapid_through_stock_not_vertical_retract():
    path = stage()
    output = render_grbl_program([path])
    unsafe = output.replace("M2\n", "G0 Z-1\nG0 X35 Y12 Z-1\nM2\n")
    result = verify(unsafe)
    assert not result.safe_to_export
    assert any(f.code == "RAPID_IN_STOCK" for f in result.preflight.findings)
    assert verify(output).safe_to_export


def test_reconstructs_post_offsets_and_checks_park_rapid():
    options = GrblPostSettings(
        x_offset_mm=-30, y_offset_mm=12,
        park_enabled=True, park_x_mm=5, park_y_mm=20,
        park_z_mm=8,
    )
    path = stage()
    code = render_grbl_program([path], options)
    stock, machine = context()
    outcome = verify_grbl_export(code, [path], stock, machine, (), options)
    assert outcome.safe_to_export
    assert outcome.decoded.moves[0].xyz == (8, 8, 6)
    assert outcome.decoded.moves[-1].xyz == (35, 8, 8)


def test_export_verifies_before_replacing_file_and_blocks_tampered_nc(
    tmp_path: Path, monkeypatch,
):
    import carvefoundry.cam.job_process as jobs

    stock, machine = context()
    dest = tmp_path / "keep.nc"
    dest.write_text("previous valid NC", encoding="ascii")
    actual_render = jobs.render_grbl_program

    def broken_render(paths, options, *, progress=None):
        program = actual_render(paths, options, progress=progress)
        return program.replace(" F400", " F401")

    monkeypatch.setattr(jobs, "render_grbl_program", broken_render)
    with pytest.raises(ValueError, match="posted feed"):
        run_gcode(GcodeRequest(
            toolpaths=[stage()], path=str(dest),
            settings=GrblPostSettings(), stock=stock,
            machine_profile=machine,
        ))
    assert dest.read_text() == "previous valid NC"
    assert not list(tmp_path.glob("*.verify.tmp"))


def test_exported_nc_verifies_and_can_be_redecoded(tmp_path: Path):
    stock, machine = context()
    dest = tmp_path / "verified.nc"
    result = run_gcode(GcodeRequest(
        toolpaths=[stage()], path=str(dest),
        settings=GrblPostSettings(), stock=stock,
        machine_profile=machine,
    ))
    assert result["files"] == [str(dest)]
    assert verify(dest.read_text()).safe_to_export


def test_virtual_machining_uses_decoded_nc_and_preserves_model():
    from carvefoundry.cam.stock_simulation import simulate_stock_removal
    from carvefoundry.cam.virtual_machining import simulate_posted_stock_removal
    from carvefoundry.core.project import Project

    stock, machine = context()
    scene = Project(name="Synthetic engraving", stock=stock, toolpaths=[stage()])
    raw = simulate_stock_removal(scene, spacing_mm=1, compare_model=False)
    actual = simulate_posted_stock_removal(
        scene, machine, spacing_mm=1, compare_model=False,
    )
    assert actual.removed_volume_mm3 == pytest.approx(
        raw.removed_volume_mm3, abs=1e-4,
    )
    assert len(actual.stages) == 1
    assert "NC stage" in actual.stages[0].name
    assert scene.toolpaths[0].name == "Detail"


def test_virtual_machining_rejects_fixtures_before_simulating():
    from carvefoundry.cam.virtual_machining import simulate_posted_stock_removal
    from carvefoundry.core.project import Project

    stock, machine = context()
    fixture = Fixture("Blocking fence", 17, 7, 19, 9, 4, 0)
    scene = Project(
        name="Fixture test", stock=stock, toolpaths=[stage()],
        fixtures=[fixture],
    )
    with pytest.raises(ValueError, match="Posted NC stage"):
        simulate_posted_stock_removal(
            scene, machine, spacing_mm=1, compare_model=False,
        )


def test_multiple_cutter_stages_are_verified_separately():
    from carvefoundry.cam.virtual_machining import simulate_posted_stock_removal
    from carvefoundry.core.project import Project

    stock, machine = context()
    rough = stage()
    ball = stage(cutter=Cutter("ball", ToolType.BALL_NOSE, 2))
    ball.name = "Finish"
    ball.moves = [
        ToolpathMove(12, 12, 6, MoveKind.RAPID),
        ToolpathMove(12, 12, -1, MoveKind.PLUNGE, 120),
        ToolpathMove(20, 12, -1, MoveKind.CUT, 400),
    ]
    scene = Project(stock=stock, toolpaths=[rough, ball])
    result = simulate_posted_stock_removal(
        scene, machine, spacing_mm=1, compare_model=False,
    )
    assert len(result.stages) == 2
    assert result.stages[0].removed_volume_mm3 > 0
    assert result.cut_sample_count > 0


def test_zero_decimal_output_does_not_truncate_100_to_1():
    cutter = Cutter("flat", ToolType.FLAT_END_MILL, 3)
    path = Toolpath(
        "Integer posts", "engrave", cutter, 5,
        [
            ToolpathMove(100, 8, 5, MoveKind.RAPID),
            ToolpathMove(100, 8, -2, MoveKind.PLUNGE, 100),
            ToolpathMove(120, 8, -2, MoveKind.CUT, 500),
        ],
    )
    stock = Stock(150, 30, 15)
    machine = MachineProfile(work_x_mm=300, work_y_mm=300, work_z_mm=100)
    settings = GrblPostSettings(decimals=0)
    program = render_grbl_program([path], settings)
    assert "X100 " in program
    assert " F100" in program
    assert " F500" in program
    assert verify_grbl_export(program, [path], stock, machine, (), settings).safe_to_export
