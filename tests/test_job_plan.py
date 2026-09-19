"""Validated operation order and accurate consecutive cutter stage reporting."""
from __future__ import annotations

import pytest

from carvefoundry.cam.job_plan import (
    cutter_stages,
    job_report,
    validate_job_order,
)
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.tools import Cutter, ToolType

FLAT = Cutter("1/4 flat", ToolType.FLAT_END_MILL, 6.35)
BALL = Cutter("3 mm ball", ToolType.BALL_NOSE, 3.0)


def _path(
    name: str,
    operation: str,
    cutter: Cutter,
    source: str = "piece1",
) -> Toolpath:
    return Toolpath(
        name=name,
        operation=operation,
        cutter=cutter,
        source_item_id=source,
        source_item_name="Plaque",
        safe_z_mm=5.0,
        moves=[
            ToolpathMove(10, 10, 5, MoveKind.RAPID),
            ToolpathMove(10, 10, -1, MoveKind.PLUNGE, 120),
            ToolpathMove(20, 10, -1, MoveKind.CUT, 600),
        ],
    )


def test_multitool_operations_group_consecutive_cutter_only() -> None:
    paths = [
        _path("Rough", "rough", FLAT),
        _path("Finish", "finish", BALL),
        _path("Detail", "engrave", BALL),
        _path("Full Depth Cutout", "profile", FLAT),
    ]
    validate_job_order(paths)
    stages = cutter_stages(paths)
    assert len(stages) == 3
    assert [stage.cutter_name for stage in stages] == [
        "1/4 flat", "3 mm ball", "1/4 flat"
    ]
    assert [len(stage.operations) for stage in stages] == [1, 2, 1]
    assert sum(stage.moves for stage in stages) == 12
    assert "3 cutter stage(s)" in job_report(paths)
    assert "excludes rapids/tool changes" in job_report(paths)


@pytest.mark.parametrize(
    ("operations", "reason"),
    [
        ([("Finish", "finish"), ("Rough", "rough")], "roughing"),
        ([("Full Depth Cutout", "profile"), ("Finish", "finish")], "final full-depth"),
    ],
)
def test_invalid_sequence_rejected(operations, reason) -> None:
    paths = [_path(name, op, FLAT) for name, op in operations]
    with pytest.raises(ValueError, match=reason):
        validate_job_order(paths)


def test_different_model_cutout_does_not_block_other_models() -> None:
    validate_job_order([
        _path("Full Depth Cutout", "profile", FLAT, "part-a"),
        _path("Rough", "rough", FLAT, "part-b"),
    ])


def test_empty_toolpath_is_not_a_usable_stage() -> None:
    with pytest.raises(ValueError, match="nonempty"):
        validate_job_order([])
    path = _path("Finish", "finish", BALL)
    path.moves.clear()
    with pytest.raises(ValueError, match="nonempty"):
        validate_job_order([path])
