import numpy as np
import pytest

from carvefoundry.cam.contact import CutterContactMap
from carvefoundry.cam.heightfield import HeightField
from carvefoundry.cam.raster import (
    RasterAxis,
    RasterFinishingSettings,
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


def _settings(axis: RasterAxis = RasterAxis.X) -> RasterFinishingSettings:
    return RasterFinishingSettings(
        stepover_mm=1.0,
        feed_mm_min=1200.0,
        plunge_feed_mm_min=300.0,
        safe_z_mm=5.0,
        axis=axis,
    )


def test_x_raster_alternates_direction_and_retracts_each_row() -> None:
    path = generate_raster_finishing(_contact(np.zeros((3, 3))), _settings())

    assert path.moves[0].kind is MoveKind.RAPID
    assert path.moves[1].kind is MoveKind.PLUNGE
    first_row_cuts = [move for move in path.moves[:5] if move.kind is MoveKind.CUT]
    assert [move.x_mm for move in first_row_cuts] == [1.0, 2.0]
    second_row = path.moves[5:10]
    assert second_row[0].x_mm == pytest.approx(2.0)
    assert [move.x_mm for move in second_row if move.kind is MoveKind.CUT] == [1.0, 0.0]
    assert all(
        move.z_mm == pytest.approx(5.0)
        for move in path.moves
        if move.kind is MoveKind.RAPID
    )


def test_y_raster_runs_along_y() -> None:
    path = generate_raster_finishing(
        _contact(np.zeros((3, 4))),
        _settings(RasterAxis.Y),
    )

    first_cut_points = [
        (move.x_mm, move.y_mm)
        for move in path.moves[:5]
        if move.kind in {MoveKind.PLUNGE, MoveKind.CUT}
    ]
    assert first_cut_points == [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]


def test_invalid_holes_create_separate_safe_runs() -> None:
    z = np.zeros((2, 5), dtype=float)
    z[0, 2] = np.nan

    path = generate_raster_finishing(_contact(z), _settings())

    first_line_rapids = [move for move in path.moves[:8] if move.kind is MoveKind.RAPID]
    assert len(first_line_rapids) == 4


def test_safe_z_must_clear_cutting_surface() -> None:
    settings = RasterFinishingSettings(1.0, 1000.0, 250.0, 0.5)

    with pytest.raises(ValueError, match="highest cutting Z"):
        generate_raster_finishing(_contact(np.ones((2, 2))), settings)


def test_stepover_cannot_be_finer_than_contact_map_resolution() -> None:
    settings = RasterFinishingSettings(0.5, 1000.0, 250.0, 5.0)

    with pytest.raises(ValueError, match="resolution is coarser"):
        generate_raster_finishing(_contact(np.zeros((2, 2))), settings)
