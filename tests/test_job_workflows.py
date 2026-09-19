import pytest

from carvefoundry.cam.job_workflows import (
    Tile,
    TilingSettings,
    find_safe_resume_index,
    plan_tiles,
    resume_toolpath,
    tile_toolpath,
)
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.tools import Cutter, ToolType


def _path() -> Toolpath:
    cutter = Cutter("3 mm flat", ToolType.FLAT_END_MILL, 3.0)
    return Toolpath(
        "Profile",
        "profile",
        cutter,
        5.0,
        [
            ToolpathMove(0.0, 5.0, 5.0, MoveKind.RAPID),
            ToolpathMove(0.0, 5.0, -1.0, MoveKind.PLUNGE, 200.0),
            ToolpathMove(20.0, 5.0, -1.0, MoveKind.CUT, 800.0),
            ToolpathMove(20.0, 15.0, -1.0, MoveKind.CUT, 800.0),
            ToolpathMove(20.0, 15.0, 5.0, MoveKind.RAPID),
            ToolpathMove(2.0, 18.0, 5.0, MoveKind.RAPID),
            ToolpathMove(2.0, 18.0, -0.5, MoveKind.PLUNGE, 200.0),
            ToolpathMove(8.0, 18.0, -0.5, MoveKind.CUT, 800.0),
            ToolpathMove(8.0, 18.0, 5.0, MoveKind.RAPID),
        ],
    )


def test_tile_plan_covers_stock_with_overlap() -> None:
    tiles = plan_tiles(
        250.0,
        100.0,
        TilingSettings(100.0, 100.0, overlap_mm=10.0),
    )

    assert len(tiles) == 3
    assert tiles[0] == Tile(0, 0, 0.0, 0.0, 100.0, 100.0)
    assert tiles[1].x0_mm == pytest.approx(90.0)
    assert tiles[-1].x1_mm == pytest.approx(250.0)


def test_tiling_clips_and_rebases_cut_geometry() -> None:
    tiled = tile_toolpath(
        _path(),
        Tile(0, 0, 10.0, 0.0, 20.0, 20.0),
        rebase=True,
    )

    assert tiled is not None
    cutting = [move for move in tiled.moves if move.kind is not MoveKind.RAPID]
    assert cutting
    assert all(-1e-9 <= move.x_mm <= 10.0 + 1e-9 for move in cutting)
    assert all(-1e-9 <= move.y_mm <= 20.0 + 1e-9 for move in cutting)
    assert any(move.x_mm == pytest.approx(0.0) for move in cutting)
    assert any(move.x_mm == pytest.approx(10.0) for move in cutting)
    assert tiled.moves[-1].z_mm == pytest.approx(tiled.safe_z_mm)


def test_safe_resume_rewinds_to_current_cut_section() -> None:
    path = _path()

    assert find_safe_resume_index(path, 3) == 1
    assert find_safe_resume_index(path, 7) == 6

    resumed = resume_toolpath(path, 3)

    assert resumed.moves[0].kind is MoveKind.RAPID
    assert resumed.moves[0].z_mm == pytest.approx(path.safe_z_mm)
    assert resumed.moves[1].kind is MoveKind.PLUNGE
    assert resumed.moves[1].xyz == path.moves[1].xyz
    assert resumed.moves[-1].z_mm == pytest.approx(path.safe_z_mm)
