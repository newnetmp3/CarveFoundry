from itertools import pairwise

import numpy as np
import pytest

from carvefoundry.cam.contact import CutterContactMap
from carvefoundry.cam.heightfield import HeightField
from carvefoundry.cam.raster import (
    RasterAxis,
    RasterFinishingSettings,
    RasterLinkMode,
    generate_raster_finishing,
)
from carvefoundry.cam.toolpath import MoveKind
from carvefoundry.core.tools import Cutter, ToolType


def _contact(z: np.ndarray) -> CutterContactMap:
    y_count, x_count = z.shape
    surface = HeightField(
        np.arange(x_count, dtype=float),
        np.arange(y_count, dtype=float),
        z.copy(),
    )
    cutter = Cutter("1 mm flat", ToolType.FLAT_END_MILL, 1.0)
    return CutterContactMap(surface, cutter, z.copy())


def _settings(
    axis: RasterAxis = RasterAxis.X,
    *,
    stepover: float = 1.0,
    link_mode: RasterLinkMode = RasterLinkMode.SMART,
) -> RasterFinishingSettings:
    return RasterFinishingSettings(
        stepover_mm=stepover,
        feed_mm_min=1200.0,
        plunge_feed_mm_min=300.0,
        safe_z_mm=5.0,
        axis=axis,
        link_mode=link_mode,
        local_link_clearance_mm=0.5,
        direct_link_tolerance_mm=0.02,
    )


def test_flat_x_raster_stays_contiguous_between_rows() -> None:
    path = generate_raster_finishing(_contact(np.zeros((3, 3))), _settings())

    assert path.moves[0].kind is MoveKind.RAPID
    assert path.moves[1].kind is MoveKind.PLUNGE
    assert path.moves[-1].kind is MoveKind.RAPID

    rapids = [move for move in path.moves if move.kind is MoveKind.RAPID]
    plunges = [move for move in path.moves if move.kind is MoveKind.PLUNGE]

    # Initial positioning and final retract only: no per-row retracts.
    assert len(rapids) == 2
    assert len(plunges) == 1

    cut_xy = [
        (move.x_mm, move.y_mm)
        for move in path.moves
        if move.kind is MoveKind.CUT
    ]
    assert (2.0, 1.0) in cut_xy
    assert (0.0, 2.0) in cut_xy


def test_y_raster_runs_along_y() -> None:
    path = generate_raster_finishing(
        _contact(np.zeros((3, 4))),
        _settings(RasterAxis.Y),
    )

    first_points = [
        (move.x_mm, move.y_mm)
        for move in path.moves
        if move.kind in {MoveKind.PLUNGE, MoveKind.CUT}
    ][:3]
    assert first_points == [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]


def test_disconnected_hole_forces_full_safe_z() -> None:
    z = np.zeros((2, 5), dtype=float)
    z[0, 2] = np.nan

    path = generate_raster_finishing(_contact(z), _settings())

    safe_rapids = [
        move
        for move in path.moves
        if move.kind is MoveKind.RAPID and move.z_mm == pytest.approx(5.0)
    ]
    # Initial position, disconnected transfer, and final retract.
    assert len(safe_rapids) >= 4


def test_connected_obstacle_uses_small_local_lift() -> None:
    z = np.zeros((3, 3), dtype=float)
    z[1, 2] = 1.0

    path = generate_raster_finishing(
        _contact(z),
        _settings(stepover=2.0),
    )

    local_rapids = [
        move
        for move in path.moves
        if move.kind is MoveKind.RAPID and move.z_mm == pytest.approx(1.5)
    ]
    assert len(local_rapids) >= 2


def test_full_retract_mode_retracts_between_flat_rows() -> None:
    path = generate_raster_finishing(
        _contact(np.zeros((3, 3))),
        _settings(link_mode=RasterLinkMode.FULL_RETRACT),
    )

    plunges = [move for move in path.moves if move.kind is MoveKind.PLUNGE]
    assert len(plunges) == 3
    assert all(
        move.z_mm == pytest.approx(5.0)
        for move in path.moves
        if move.kind is MoveKind.RAPID
    )


@pytest.mark.parametrize(
    "axis",
    (RasterAxis.DIAGONAL_45, RasterAxis.DIAGONAL_135),
)
def test_diagonal_rasters_move_in_both_xy_axes(axis: RasterAxis) -> None:
    path = generate_raster_finishing(
        _contact(np.zeros((5, 5))),
        _settings(axis, stepover=1.0),
    )

    cut_moves = [move for move in path.moves if move.kind is MoveKind.CUT]
    deltas = [
        (
            current.x_mm - previous.x_mm,
            current.y_mm - previous.y_mm,
        )
        for previous, current in pairwise(cut_moves)
    ]
    assert any(abs(dx) > 0.0 and abs(dy) > 0.0 for dx, dy in deltas)


def test_safe_z_must_clear_cutting_surface() -> None:
    settings = RasterFinishingSettings(1.0, 1000.0, 250.0, 0.5)

    with pytest.raises(ValueError, match="highest cutting Z"):
        generate_raster_finishing(_contact(np.ones((2, 2))), settings)


def test_stepover_cannot_be_finer_than_contact_map_resolution() -> None:
    settings = RasterFinishingSettings(0.5, 1000.0, 250.0, 5.0)

    with pytest.raises(ValueError, match="resolution is coarser"):
        generate_raster_finishing(_contact(np.zeros((2, 2))), settings)
