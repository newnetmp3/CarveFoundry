"""Regression coverage for cutter-contact-safe, genuinely stock-aware 3D rest."""
from __future__ import annotations

import numpy as np
import pytest

from carvefoundry.cam.basic_ops import BasicCamSettings
from carvefoundry.cam.job_plan import validate_job_order
from carvefoundry.cam.job_process import CamRequest, run_cam
from carvefoundry.cam.rest_machining import stock_aware_rest_3d
from carvefoundry.cam.stock_simulation import StockRemovalResult
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import ProjectItem
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.core.transform import Transform3D


def _mesh():
    asset = rectangle_mesh(12, 12, 2)
    mesh = asset.mesh.copy()
    mesh.apply_translation((15, 15, -1))
    return mesh


def _stock(*, clear_left: bool = False, fully_cleared: bool = False):
    axes = np.linspace(0, 30, 61)
    height = np.zeros((len(axes), len(axes)), dtype=np.float32)
    if clear_left:
        height[:, axes < 14] = -3.0
    if fully_cleared:
        height[:] = -3.0
    return StockRemovalResult(
        x_mm=axes, y_mm=axes, remaining_z_mm=height,
        target_z_mm=None, removed_volume_mm3=0.0,
        cut_sample_count=0, grid_spacing_mm=0.5, stages=(),
    )


def _settings():
    return BasicCamSettings(
        safe_z_mm=3,
        feed_mm_min=1000,
        plunge_feed_mm_min=200,
        finish_stepover_fraction=0.3,
    )


def _tool():
    return Cutter("1.5 mm flat", ToolType.FLAT_END_MILL, 1.5)


def test_rest_requires_material_above_actual_cutter_contact():
    tool = _tool()
    rest = stock_aware_rest_3d(
        _mesh(), tool, _settings(), _stock(),
        minimum_remaining_mm=0.15,
    )
    assert rest.operation == "3d_rest_raster"
    assert rest.name == "3D Stock-Aware Rest"
    assert rest.cutter == tool
    assert rest.moves[0].kind is MoveKind.RAPID
    assert rest.moves[0].z_mm == pytest.approx(3)
    assert rest.moves[-1].z_mm == pytest.approx(3)
    assert min(
        move.z_mm for move in rest.moves if move.kind is not MoveKind.RAPID
    ) <= -0.99


def test_rest_only_targets_remaining_stock_not_previously_cleared_side():
    rest = stock_aware_rest_3d(
        _mesh(), _tool(), _settings(), _stock(clear_left=True),
    )
    cutting = [
        move for move in rest.moves
        if move.kind in {MoveKind.CUT, MoveKind.PLUNGE}
    ]
    assert cutting
    assert min(move.x_mm for move in cutting) > 12
    assert max(move.x_mm for move in cutting) > 19


def test_rest_fails_closed_when_previous_stage_cleared_entire_target():
    with pytest.raises(ValueError, match="No stock-aware rest cuts"):
        stock_aware_rest_3d(
            _mesh(), _tool(), _settings(), _stock(fully_cleared=True),
        )


@pytest.mark.parametrize("allowance", [0.0, -0.2, 6.0, float("nan")])
def test_invalid_rest_allowance_is_refused(allowance):
    with pytest.raises(ValueError, match="Rest allowance"):
        stock_aware_rest_3d(
            _mesh(), _tool(), _settings(), _stock(),
            minimum_remaining_mm=allowance,
        )


def test_rest_refuses_model_outside_stock():
    model = _mesh()
    model.apply_translation((-16, 0, 0))
    with pytest.raises(ValueError, match="fully inside XY stock"):
        stock_aware_rest_3d(model, _tool(), _settings(), _stock())


def _previous(item_id, *, depth=-0.5, name="3D Rough"):
    return Toolpath(
        name=name,
        operation="3d_rough_raster",
        cutter=Cutter("6 mm flat", ToolType.FLAT_END_MILL, 6),
        safe_z_mm=3,
        moves=[
            ToolpathMove(14, 15, 3, MoveKind.RAPID),
            ToolpathMove(14, 15, depth, MoveKind.PLUNGE, 200),
            ToolpathMove(16, 15, depth, MoveKind.CUT, 1000),
            ToolpathMove(16, 15, 3, MoveKind.RAPID),
        ],
        source_item_id=item_id,
        source_item_name="Part",
    )


def test_rest_worker_simulates_old_stages_then_appends_real_cleanup():
    item = ProjectItem(
        "Part", kind="rectangle", mesh=rectangle_mesh(12, 12, 2),
        transform=Transform3D(translation_mm=(15, 15, -1)),
    )
    previous = _previous(item.item_id)
    result = run_cam(CamRequest(
        operation="rest", cutter=_tool(), cut_type="Auto",
        thickness_mm=8, stock_width_mm=30, stock_height_mm=30,
        settings_by_item=[(item, _settings())],
        previous_toolpaths=[previous],
        rest_grid_spacing_mm=0.5,
        rest_min_remaining_mm=0.15,
    ))
    paths = result["toolpaths"]
    assert paths[0] == previous
    assert len(paths) == 2
    assert paths[1].operation == "3d_rest_raster"
    assert paths[1].source_item_id == item.item_id
    assert paths[1].cutter == _tool()
    validate_job_order(paths)
    assert result["moves"] > len(previous.moves)


def test_rest_worker_refuses_prior_stages_for_different_object():
    item = ProjectItem("Part", kind="rectangle", mesh=rectangle_mesh(12, 12, 2),
                       transform=Transform3D(translation_mm=(15, 15, -1)))
    with pytest.raises(ValueError, match="before stock-aware rest"):
        run_cam(CamRequest(
            operation="rest", cutter=_tool(), cut_type="Auto",
            thickness_mm=8, stock_width_mm=30, stock_height_mm=30,
            settings_by_item=[(item, _settings())],
            previous_toolpaths=[_previous("different-item")],
            rest_grid_spacing_mm=0.5,
        ))


def test_rest_worker_rejects_detached_part_before_generating_rest():
    item = ProjectItem("Part", kind="rectangle", mesh=rectangle_mesh(12, 12, 2),
                       transform=Transform3D(translation_mm=(15, 15, -1)))
    prior = _previous(item.item_id, name="Full Depth Cutout")
    with pytest.raises(ValueError, match="full-depth cutout"):
        run_cam(CamRequest(
            operation="rest", cutter=_tool(), cut_type="Auto",
            thickness_mm=8, stock_width_mm=30, stock_height_mm=30,
            settings_by_item=[(item, _settings())],
            previous_toolpaths=[prior],
            rest_grid_spacing_mm=0.5,
        ))
