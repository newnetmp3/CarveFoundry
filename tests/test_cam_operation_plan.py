from carvefoundry.cam.operation import CamOperation
from carvefoundry.cam.operation_plan import (
    delete_operation,
    duplicate_operation,
    reorder_operation,
    set_operation_enabled,
    update_operation,
)
from carvefoundry.cam.toolpath import Toolpath
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.tools import Cutter, ToolType


def _cutter(name: str = "6 mm flat") -> Cutter:
    return Cutter(name, ToolType.FLAT_END_MILL, 6.0)


def _operation(item: ProjectItem, name: str) -> CamOperation:
    return CamOperation(
        operation="profile",
        cutter=_cutter(name),
        source_item_ids=(item.item_id,),
        parameters={"feed_mm_min": 1000.0},
    )


def _path(operation: CamOperation, item: ProjectItem) -> Toolpath:
    return Toolpath(
        name=operation.cutter.name,
        operation=operation.operation,
        cutter=operation.cutter,
        safe_z_mm=1.5,
        source_item_id=item.item_id,
        source_item_name=item.name,
        cam_operation_id=operation.operation_id,
    )


def _three_stage_project() -> tuple[Project, list[CamOperation]]:
    items = [ProjectItem("A"), ProjectItem("B"), ProjectItem("C")]
    operations = [
        _operation(items[0], "A cutter"),
        _operation(items[1], "B cutter"),
        _operation(items[2], "C cutter"),
    ]
    return (
        Project(
            items=items,
            cam_operations=operations,
            toolpaths=[
                _path(operation, item)
                for operation, item in zip(operations, items, strict=True)
            ],
        ),
        operations,
    )


def test_disable_removes_stage_and_invalidates_downstream_only() -> None:
    project, operations = _three_stage_project()

    assert set_operation_enabled(
        project,
        operations[1].operation_id,
        False,
    )

    assert operations[0].enabled
    assert not operations[0].needs_recalculation
    assert not operations[1].enabled
    assert operations[2].needs_recalculation
    assert [
        path.cam_operation_id for path in project.toolpaths
    ] == [operations[0].operation_id]


def test_reenable_requires_fresh_motion_for_stage_and_downstream() -> None:
    project, operations = _three_stage_project()
    set_operation_enabled(project, operations[1].operation_id, False)

    assert set_operation_enabled(
        project,
        operations[1].operation_id,
        True,
    )

    assert operations[1].enabled
    assert operations[1].needs_recalculation
    assert operations[2].needs_recalculation
    assert [
        path.cam_operation_id for path in project.toolpaths
    ] == [operations[0].operation_id]


def test_reorder_invalidates_from_earliest_changed_position() -> None:
    project, operations = _three_stage_project()

    assert reorder_operation(
        project,
        operations[2].operation_id,
        1,
    )

    assert [op.operation_id for op in project.cam_operations] == [
        operations[0].operation_id,
        operations[2].operation_id,
        operations[1].operation_id,
    ]
    assert not operations[0].needs_recalculation
    assert operations[1].needs_recalculation
    assert operations[2].needs_recalculation
    assert [
        path.cam_operation_id for path in project.toolpaths
    ] == [operations[0].operation_id]


def test_duplicate_gets_new_id_and_invalidates_following_job() -> None:
    project, operations = _three_stage_project()

    duplicate = duplicate_operation(project, operations[0].operation_id)

    assert duplicate.operation_id != operations[0].operation_id
    assert duplicate.parameters == operations[0].parameters
    assert duplicate.parameters is not operations[0].parameters
    assert duplicate.needs_recalculation
    assert operations[1].needs_recalculation
    assert operations[2].needs_recalculation
    assert [
        path.cam_operation_id for path in project.toolpaths
    ] == [operations[0].operation_id]


def test_delete_removes_owned_motion_and_invalidates_following_job() -> None:
    project, operations = _three_stage_project()

    removed = delete_operation(project, operations[1].operation_id)

    assert removed is operations[1]
    assert [op.operation_id for op in project.cam_operations] == [
        operations[0].operation_id,
        operations[2].operation_id,
    ]
    assert operations[2].needs_recalculation
    assert [
        path.cam_operation_id for path in project.toolpaths
    ] == [operations[0].operation_id]


def test_edit_updates_saved_intent_and_invalidates_from_that_stage() -> None:
    project, operations = _three_stage_project()
    replacement = Cutter("3 mm flat", ToolType.FLAT_END_MILL, 3.0)

    updated = update_operation(
        project,
        operations[1].operation_id,
        operation_type="pocket",
        cutter=replacement,
        parameters={"feed_mm_min": 700.0, "stepdown_mm": 1.0},
    )

    assert updated.operation == "pocket"
    assert updated.cutter == replacement
    assert updated.parameters["feed_mm_min"] == 700.0
    assert not operations[0].needs_recalculation
    assert operations[1].needs_recalculation
    assert operations[2].needs_recalculation
