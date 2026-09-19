"""Cutter-margin-aware batch grids without mutating the source design objects."""
from __future__ import annotations

from dataclasses import replace
from math import ceil, isfinite
from uuid import uuid4

import numpy as np

from .project import Project, ProjectItem

MAX_BATCH_COPIES = 256


def batch_grid(
    project: Project,
    sources: tuple[ProjectItem, ...],
    *,
    copies: int,
    columns: int,
    gap_mm: float,
    margin_mm: float,
    cutter_radius_mm: float,
) -> list[ProjectItem]:
    """Duplicate a multi-item design into a validated stock-relative grid.

    Every returned item retains editable source geometry and its independent
    transform. The caller hides templates and commits all copies with Undo.
    Layout rejects physical fixture rectangles expanded by selected cutter
    radius + fixture clearance; final per-cutter G-code preflight is required.
    """
    if not sources:
        raise ValueError("Select at least one visible mesh as the batch template.")
    if not isinstance(copies, int) or not 1 <= copies <= MAX_BATCH_COPIES:
        raise ValueError(f"Batch count must be 1–{MAX_BATCH_COPIES}.")
    if not isinstance(columns, int) or not 1 <= columns <= copies:
        raise ValueError("Columns must be between 1 and the copy count.")
    if any(
        not isfinite(x) or x < 0
        for x in (gap_mm, margin_mm, cutter_radius_mm)
    ):
        raise ValueError("Gap, stock margin and cutter radius must be nonnegative/finite.")
    if margin_mm < cutter_radius_mm:
        raise ValueError("Stock margin must be at least the selected cutter radius.")

    stock = project.stock
    if any(not isfinite(value) or value <= 0 for value in (
        stock.width_mm, stock.height_mm, stock.thickness_mm,
    )):
        raise ValueError("Stock dimensions must be finite and positive.")
    if stock.xy_zero != "bottom_left":
        raise ValueError("Batch layout requires stock-bottom-left XY0.")
    identifiers = [source.item_id for source in sources]
    active = {item.item_id for item in project.items if item.visible and item.mesh is not None}
    if len(identifiers) != len(set(identifiers)) or any(
        item_id not in active for item_id in identifiers
    ):
        raise ValueError("Batch templates must be unique visible project objects.")
    if any(
        "position_x" in source.smart_bindings
        or "position_y" in source.smart_bindings
        for source in sources
    ):
        raise ValueError(
            "Unbind X/Y position Smart Values before batching; otherwise "
            "automatic binding updates would overwrite each copy's position."
        )

    bounds = []
    for source in sources:
        box = source.transformed_bounds_mm()
        if box is None or not np.isfinite(box).all():
            raise ValueError(f"{source.name}: invalid mesh bounds.")
        if box[0, 2] < -stock.thickness_mm - 1e-6 or box[1, 2] > 1e-6:
            raise ValueError(f"{source.name}: geometry extends outside stock Z.")
        bounds.append(box)
    minimum = np.min(np.asarray([box[0] for box in bounds]), axis=0)
    maximum = np.max(np.asarray([box[1] for box in bounds]), axis=0)
    size = maximum[:2] - minimum[:2]
    rows = ceil(copies / columns)
    occupied_w = columns * size[0] + (columns - 1) * gap_mm + 2 * margin_mm
    occupied_h = rows * size[1] + (rows - 1) * gap_mm + 2 * margin_mm
    if (
        occupied_w > stock.width_mm + 1e-6
        or occupied_h > stock.height_mm + 1e-6
    ):
        raise ValueError(
            f"Batch needs {occupied_w:g} × {occupied_h:g} mm, but "
            f"stock is {stock.width_mm:g} × {stock.height_mm:g} mm."
        )
    for fixture in project.fixtures:
        fixture.validate()

    output = []
    for copy_index in range(copies):
        col = copy_index % columns
        row = copy_index // columns
        dx = margin_mm + col * (size[0] + gap_mm) - minimum[0]
        dy = margin_mm + row * (size[1] + gap_mm) - minimum[1]
        for source, box in zip(sources, bounds, strict=True):
            left, bottom = box[0, :2] + (dx, dy)
            right, top = box[1, :2] + (dx, dy)
            for fixture in project.fixtures:
                clearance = fixture.clearance_mm + cutter_radius_mm
                if (
                    right > fixture.x_min_mm - clearance
                    and left < fixture.x_max_mm + clearance
                    and top > fixture.y_min_mm - clearance
                    and bottom < fixture.y_max_mm + clearance
                ):
                    raise ValueError(
                        f"Copy {copy_index + 1} of {source.name} overlaps "
                        f"fixture {fixture.name!r} with tool clearance."
                    )

        group_id = uuid4().hex if len(sources) > 1 else None
        for source in sources:
            tx, ty, tz = source.transform.translation_mm
            new_transform = replace(source.transform)
            new_transform.translation_mm = (
                float(tx + dx), float(ty + dy), float(tz),
            )
            output.append(ProjectItem(
                name=f"{source.name} #{copy_index + 1:02d}",
                source_path=source.source_path,
                kind=source.kind,
                visible=True,
                mesh=source.mesh,
                transform=new_transform,
                source_units=source.source_units,
                group_id=group_id,
                text_properties=source.text_properties,
                smart_bindings=dict(source.smart_bindings),
            ))
    return output
