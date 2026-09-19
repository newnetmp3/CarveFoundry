"""Safe ordering and readable statistics for session-owned multi-cutter CAM jobs."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from carvefoundry.cam.toolpath import Toolpath


@dataclass(frozen=True, slots=True)
class CutterStage:
    index: int
    cutter_name: str
    operations: tuple[str, ...]
    moves: int
    estimated_cutting_minutes: float


def validate_job_order(paths: Sequence[Toolpath]) -> None:
    """Refuse to machine a detached model or finish before its roughing path.

    This is an ordering check, not stock-removal simulation. Final export still
    runs fixture-aware preflight and separates consecutive tool changes.
    """
    if not paths or any(not path.moves for path in paths):
        raise ValueError("A machining job needs nonempty generated operations.")
    by_source: dict[str, list[Toolpath]] = {}
    for index, path in enumerate(paths):
        source = path.source_item_id or f"__unknown_{index}"
        by_source.setdefault(source, []).append(path)
    for operations in by_source.values():
        detached = False
        finished = False
        for path in operations:
            label = path.name.casefold()
            full_cutout = "full depth cutout" in label
            if detached and not full_cutout:
                raise ValueError(
                    f"{path.source_item_name or path.name}: no operations may follow "
                    "the final full-depth cutout of the same item."
                )
            if path.operation == "rough" and finished:
                raise ValueError(
                    f"{path.source_item_name or path.name}: roughing must precede "
                    "the finishing/detail operations of that item."
                )
            if path.operation in {"finish", "height_map", "waterline", "vcarve", "engrave"}:
                finished = True
            detached = detached or full_cutout


def cutter_stages(paths: Sequence[Toolpath]) -> tuple[CutterStage, ...]:
    """Report cutter changes using the same consecutive grouping as GRBL export."""
    stages: list[CutterStage] = []
    current: list[Toolpath] = []
    for path in paths:
        if current and path.cutter != current[-1].cutter:
            stages.append(_stage(len(stages) + 1, current))
            current = []
        current.append(path)
    if current:
        stages.append(_stage(len(stages) + 1, current))
    return tuple(stages)


def _stage(index: int, paths: list[Toolpath]) -> CutterStage:
    return CutterStage(
        index=index,
        cutter_name=paths[0].cutter.name,
        operations=tuple(path.name for path in paths),
        moves=sum(len(path.moves) for path in paths),
        estimated_cutting_minutes=sum(
            path.estimated_cutting_minutes for path in paths
        ),
    )


def job_report(paths: Sequence[Toolpath]) -> str:
    validate_job_order(paths)
    stages = cutter_stages(paths)
    rows = [
        (
            f"{len(paths)} operation(s), {len(stages)} cutter stage(s), "
            f"{sum(len(path.moves) for path in paths):,} moves"
        ),
        (
            f"Feed-based cutting time (excludes rapids/tool changes): "
            f"{sum(path.estimated_cutting_minutes for path in paths):.1f} min"
        ),
    ]
    for stage in stages:
        rows.append(
            f"{stage.index}. {stage.cutter_name} — "
            f"{' + '.join(stage.operations)} "
            f"({stage.estimated_cutting_minutes:.1f} min)"
        )
    return "\n".join(rows)
