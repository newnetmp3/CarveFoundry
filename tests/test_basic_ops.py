import numpy as np

from carvefoundry.cam.basic_ops import (
    BasicCamSettings,
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
