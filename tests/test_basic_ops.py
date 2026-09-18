import numpy as np
import pytest

from carvefoundry.cam.basic_ops import (
    BasicCamSettings,
    MillingDirection,
    PocketStrategy,
    center_drill,
    rectangular_pocket,
    rectangular_profile,
)
from carvefoundry.cam.toolpath import MoveKind
from carvefoundry.core.tools import Cutter, ToolType


def _bounds() -> np.ndarray:
    return np.array(((10.0, 20.0, -4.0), (60.0, 50.0, 0.0)), dtype=float)


def _tool() -> Cutter:
    return Cutter("flat", ToolType.FLAT_END_MILL, 6.0)


def test_profile_generates_closed_cutting_path_and_retracts() -> None:
    toolpath = rectangular_profile(
        _bounds(),
        _tool(),
        BasicCamSettings(max_stepdown_mm=2.0),
    )

    assert toolpath.operation == "profile"
    assert toolpath.moves
    assert toolpath.moves[0].kind is MoveKind.RAPID
    assert toolpath.moves[-1].kind is MoveKind.RAPID
    assert min(move.z_mm for move in toolpath.moves) == -4.0


def test_profile_tabs_raise_final_depth_mid_side() -> None:
    toolpath = rectangular_profile(
        _bounds(),
        _tool(),
        BasicCamSettings(
            max_stepdown_mm=10.0,
            tabs_enabled=True,
            tab_height_mm=1.5,
        ),
    )

    cutting_z = [
        move.z_mm
        for move in toolpath.moves
        if move.kind is MoveKind.CUT
    ]
    assert -4.0 in cutting_z
    assert -2.5 in cutting_z


def test_pocket_serpentine_fills_bounds() -> None:
    toolpath = rectangular_pocket(
        _bounds(),
        _tool(),
        BasicCamSettings(max_stepdown_mm=4.0, stepover_fraction=0.5),
    )

    cuts = [move for move in toolpath.moves if move.kind is MoveKind.CUT]
    assert len(cuts) >= 2
    assert min(move.z_mm for move in cuts) == -4.0


def test_center_drill_reaches_target_depth() -> None:
    toolpath = center_drill(
        _bounds(),
        _tool(),
        BasicCamSettings(max_stepdown_mm=2.0),
    )

    plunges = [move for move in toolpath.moves if move.kind is MoveKind.PLUNGE]
    assert plunges
    assert plunges[-1].z_mm == -4.0


def test_profile_inside_offset_uses_cutter_radius() -> None:
    toolpath = rectangular_profile(
        _bounds(),
        _tool(),
        BasicCamSettings(max_stepdown_mm=10.0),
        offset_mode="inside",
    )

    cut_xy = [
        (move.x_mm, move.y_mm)
        for move in toolpath.moves
        if move.kind is MoveKind.CUT
    ]
    assert (57.0, 23.0) in cut_xy
    assert (13.0, 47.0) in cut_xy


def test_overall_depth_overrides_geometry_depth() -> None:
    toolpath = rectangular_profile(
        _bounds(),
        _tool(),
        BasicCamSettings(
            overall_depth_mm=2.5,
            max_stepdown_mm=10.0,
        ),
    )

    assert min(move.z_mm for move in toolpath.moves) == -2.5


def test_raster_y_pocket_runs_along_y_axis() -> None:
    toolpath = rectangular_pocket(
        _bounds(),
        _tool(),
        BasicCamSettings(
            max_stepdown_mm=10.0,
            stepover_fraction=0.5,
            pocket_strategy=PocketStrategy.RASTER_Y,
        ),
    )

    cutting = [
        move
        for move in toolpath.moves
        if move.kind in {MoveKind.PLUNGE, MoveKind.CUT}
    ]
    assert cutting[0].x_mm == cutting[1].x_mm
    assert cutting[0].y_mm != cutting[1].y_mm


def test_offset_pocket_generates_nested_loops() -> None:
    toolpath = rectangular_pocket(
        _bounds(),
        _tool(),
        BasicCamSettings(
            max_stepdown_mm=10.0,
            stepover_fraction=0.5,
            pocket_strategy=PocketStrategy.OFFSET,
        ),
    )

    cuts = [move for move in toolpath.moves if move.kind is MoveKind.CUT]
    assert len(cuts) > 4


def test_ramp_entry_reaches_depth_while_advancing_xy() -> None:
    toolpath = rectangular_profile(
        _bounds(),
        _tool(),
        BasicCamSettings(
            max_stepdown_mm=10.0,
            ramp_angle_deg=20.0,
        ),
    )

    plunge = next(move for move in toolpath.moves if move.kind is MoveKind.PLUNGE)
    first_cut = next(move for move in toolpath.moves if move.kind is MoveKind.CUT)
    assert plunge.z_mm == 0.0
    assert first_cut.z_mm == -4.0
    assert (first_cut.x_mm, first_cut.y_mm) != (
        plunge.x_mm,
        plunge.y_mm,
    )


def test_conventional_profile_reverses_outline_direction() -> None:
    toolpath = rectangular_profile(
        _bounds(),
        _tool(),
        BasicCamSettings(
            max_stepdown_mm=10.0,
            milling_direction=MillingDirection.CONVENTIONAL,
        ),
    )

    cuts = [move for move in toolpath.moves if move.kind is MoveKind.CUT]
    assert cuts[0].x_mm == pytest.approx(7.0)
    assert cuts[0].y_mm == pytest.approx(53.0)


def test_usable_bit_length_blocks_overdeep_profile() -> None:
    with pytest.raises(ValueError, match="usable bit length"):
        rectangular_profile(
            _bounds(),
            _tool(),
            BasicCamSettings(
                overall_depth_mm=4.0,
                usable_bit_length_mm=2.0,
                max_stepdown_mm=10.0,
            ),
        )


def test_configurable_tab_count_creates_requested_tab_zones() -> None:
    toolpath = rectangular_profile(
        _bounds(),
        _tool(),
        BasicCamSettings(
            max_stepdown_mm=10.0,
            tabs_enabled=True,
            tab_height_mm=1.5,
            tab_width_mm=4.0,
            tab_count=6,
        ),
    )

    tab_moves = [
        move
        for move in toolpath.moves
        if move.kind is MoveKind.CUT and move.z_mm == pytest.approx(-2.5)
    ]
    assert len(tab_moves) >= 6
