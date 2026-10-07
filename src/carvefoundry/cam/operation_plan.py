from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from carvefoundry.core.project import Project

from .operation import CamOperation


def operation_index(project: Project, operation_id: str) -> int:
    for index, operation in enumerate(project.cam_operations):
        if operation.operation_id == operation_id:
            return index
    raise ValueError("CAM operation no longer exists.")


def invalidate_from(
    project: Project,
    start_index: int,
    reason: str,
    *,
    include_start: bool = True,
) -> set[str]:
    """Mark enabled operations stale from a job position and drop their motion."""

    if not project.cam_operations:
        return set()
    first = start_index if include_start else start_index + 1
    first = max(0, first)
    if first >= len(project.cam_operations):
        return set()

    stale_ids: set[str] = set()
    for operation in project.cam_operations[first:]:
        if not operation.enabled:
            continue
        operation.mark_stale(reason)
        stale_ids.add(operation.operation_id)

    if stale_ids:
        project.toolpaths = [
            path
            for path in project.toolpaths
            if path.cam_operation_id not in stale_ids
        ]
    return stale_ids


def set_operation_enabled(
    project: Project,
    operation_id: str,
    enabled: bool,
) -> bool:
    index = operation_index(project, operation_id)
    operation = project.cam_operations[index]
    enabled = bool(enabled)
    if operation.enabled == enabled:
        return False

    operation.enabled = enabled
    if enabled:
        operation.mark_stale("Operation re-enabled")
        affected_ids = {operation.operation_id}
        affected_ids.update(
            invalidate_from(
                project,
                index,
                "Earlier machining stage changed",
                include_start=False,
            )
        )
        project.toolpaths = [
            path
            for path in project.toolpaths
            if path.cam_operation_id not in affected_ids
        ]
    else:
        project.toolpaths = [
            path
            for path in project.toolpaths
            if path.cam_operation_id != operation.operation_id
        ]
        invalidate_from(
            project,
            index,
            "Earlier machining stage disabled",
            include_start=False,
        )
    return True


def reorder_operation(
    project: Project,
    operation_id: str,
    target_index: int,
) -> bool:
    old_index = operation_index(project, operation_id)
    target_index = max(0, min(int(target_index), len(project.cam_operations) - 1))
    if target_index == old_index:
        return False

    operation = project.cam_operations.pop(old_index)
    project.cam_operations.insert(target_index, operation)
    invalidate_from(
        project,
        min(old_index, target_index),
        "Machining order changed",
    )
    return True


def duplicate_operation(project: Project, operation_id: str) -> CamOperation:
    index = operation_index(project, operation_id)
    source = project.cam_operations[index]
    duplicate = replace(
        source,
        operation_id=uuid4().hex,
        parameters=dict(source.parameters),
        enabled=True,
        stale_reason="Duplicated operation",
    )
    project.cam_operations.insert(index + 1, duplicate)
    invalidate_from(
        project,
        index + 1,
        "Machining operation duplicated",
    )
    return duplicate


def delete_operation(project: Project, operation_id: str) -> CamOperation:
    index = operation_index(project, operation_id)
    removed = project.cam_operations.pop(index)
    project.toolpaths = [
        path
        for path in project.toolpaths
        if path.cam_operation_id != operation_id
    ]
    if index < len(project.cam_operations):
        invalidate_from(
            project,
            index,
            "Earlier machining operation removed",
        )
    return removed


def update_operation(
    project: Project,
    operation_id: str,
    *,
    operation_type: str,
    cutter,
    parameters: dict[str, str | int | float | bool | None],
) -> CamOperation:
    index = operation_index(project, operation_id)
    operation = project.cam_operations[index]
    operation.operation = operation_type
    operation.cutter = cutter
    operation.parameters = dict(parameters)
    invalidate_from(
        project,
        index,
        "Machining settings changed",
    )
    return operation
