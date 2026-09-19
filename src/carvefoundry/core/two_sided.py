"""Stock-registered, non-destructive front/back CNC project preparation.

Each output file is a normal CF3D project. Back-face geometry is reflected in
the stock XY plane, not merely translated or mirrored in postprocessed G-code.
The operator physically flips the stock, re-registers against fixed stops and
probes the newly exposed face as Z0 before machining the back project.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import replace
from math import isfinite
from pathlib import Path
from uuid import uuid4

import numpy as np

from .mesh import mesh_asset_from_geometry
from .project import Project, ProjectItem, Stock
from .project_file import load_project, save_project
from .smart_values import SmartValues
from .transform import Transform3D
from .units import ModelUnits

_AXES = {"x", "y"}
_EPS = 1e-5


def _validated_stock(project: Project) -> Stock:
    stock = project.stock
    dims = (stock.width_mm, stock.height_mm, stock.thickness_mm)
    if not all(isfinite(value) and value > 0 for value in dims):
        raise ValueError("Stock width, height and thickness must be positive and finite.")
    if stock.xy_zero != "bottom_left":
        raise ValueError(
            "Two-sided setup requires stock-bottom-left XY0 for both registered setups."
        )
    for fixture in project.fixtures:
        fixture.validate()
    return replace(stock)


def _validated_bounds(item: ProjectItem, stock: Stock) -> None:
    bounds = item.transformed_bounds_mm()
    if bounds is None or not np.isfinite(bounds).all():
        raise ValueError(f"{item.name}: no valid placed mesh.")
    low, high = bounds
    if (
        low[0] < -_EPS or low[1] < -_EPS
        or high[0] > stock.width_mm + _EPS
        or high[1] > stock.height_mm + _EPS
    ):
        raise ValueError(
            f"{item.name}: geometry lies outside the registered stock XY rectangle."
        )
    if low[2] < -stock.thickness_mm - _EPS or high[2] > _EPS:
        raise ValueError(
            f"{item.name}: geometry must be within stock-top Z0 and stock bottom "
            f"Z{-stock.thickness_mm:g} mm."
        )


def reflect_back_face(
    item: ProjectItem,
    stock: Stock,
    *,
    axis: str,
) -> ProjectItem:
    """Bake a reflected face mesh while leaving its relief Z depth unchanged.

    'x' is a physical left/right turnover (the work X axis reverses);
    'y' is a top/bottom turnover. The reflection has negative determinant;
    trimesh.apply_transform corrects triangle winding and normals.
    """
    if axis not in _AXES:
        raise ValueError("Flip axis must be x or y.")
    _validated_bounds(item, stock)
    mesh = item.transformed_mesh()
    if mesh is None:
        raise ValueError(f"{item.name}: no usable geometry.")
    matrix = np.eye(4, dtype=float)
    if axis == "x":
        matrix[0, 0] = -1.0
        matrix[0, 3] = stock.width_mm
    else:
        matrix[1, 1] = -1.0
        matrix[1, 3] = stock.height_mm
    mesh.apply_transform(matrix)
    mesh.metadata["units"] = "mm"
    # Baked geometry is intentional: editable text and placement Smart Values
    # would otherwise regenerate the *unreflected* design on the reverse side.
    return ProjectItem(
        name=item.name,
        kind="stl",
        visible=True,
        mesh=mesh_asset_from_geometry(mesh),
        transform=Transform3D(),
        source_units=ModelUnits.MILLIMETERS,
        group_id=item.group_id,
        item_id=uuid4().hex,
    )


def prepare_two_sided(
    project: Project,
    *,
    back_item_ids: frozenset[str] | set[str],
    axis: str,
) -> tuple[Project, Project]:
    """Partition active design into front and flipped back project identities.

    Hidden meshes never enter either face; fixtures are MACHINE-FIXED keepouts
    and must NOT be mirrored with the stock. No source item is changed.
    """
    if axis not in _AXES:
        raise ValueError("Flip axis must be x or y.")
    stock = _validated_stock(project)
    active = [item for item in project.items if item.visible and item.mesh is not None]
    ids = {item.item_id for item in active}
    back_ids = set(back_item_ids)
    if len(ids) != len(active):
        raise ValueError("Duplicate item IDs prevent unambiguous face assignment.")
    if back_ids - ids:
        raise ValueError("Back face selection includes hidden or missing geometry.")
    if not back_ids or not ids - back_ids:
        raise ValueError("Assign at least one visible model to each face.")

    for item in active:
        _validated_bounds(item, stock)

    front_items = [
        replace(
            item,
            transform=replace(item.transform),
            smart_bindings=dict(item.smart_bindings),
        )
        for item in active if item.item_id not in back_ids
    ]
    back_items = [
        reflect_back_face(item, stock, axis=axis)
        for item in active if item.item_id in back_ids
    ]
    front = Project(
        name=f"{project.name} - front",
        stock=replace(stock),
        items=front_items,
        fixtures=list(project.fixtures),
        smart_values=SmartValues(dict(project.smart_values.expressions)),
    )
    back = Project(
        name=f"{project.name} - back (flip {axis.upper()})",
        stock=replace(stock),
        items=back_items,
        fixtures=list(project.fixtures),
    )
    return front, back


def setup_instructions(
    *,
    original: Project,
    front: Project,
    back: Project,
    axis: str,
) -> str:
    stock = original.stock
    axis_text = (
        "LEFT/RIGHT turnover: X_back = stock_width - X_front, Y_back = Y_front"
        if axis == "x"
        else "TOP/BOTTOM turnover: X_back = X_front, Y_back = stock_height - Y_front"
    )
    fixtures = (
        ", ".join(fixture.name for fixture in original.fixtures)
        if original.fixtures else "NONE RECORDED — add clamps/fences before export"
    )
    return (
        "CARVEFOUNDRY TWO-SIDED SETUP — READ BEFORE CUTTING\n"
        "================================================\n"
        f"Original project: {original.name}\n"
        f"Stock: {stock.width_mm:g} X {stock.height_mm:g} X "
        f"{stock.thickness_mm:g} mm\n"
        "Both projects: stock-bottom-left XY0, exposed-face stock-top Z0.\n"
        f"Physical flip: {axis_text}.\n"
        f"Recorded machine-fixed fixtures (copied to both setups): {fixtures}\n\n"
        "1. Check that fixed registration fences/hold-downs match both physical "
        "setups; their positions are NOT mirrored by software.\n"
        "2. Open front.cf3d. Generate toolpaths for FRONT items only. Preview, "
        "run CNC preflight, export G-code, and machine the front. Use separate "
        "numbered files per cutter and re-probe Z after every tool change.\n"
        "3. Stop spindle and motion. Turn the STOCK over about the selected "
        "physical axis, register it against the stops, secure it again. "
        "Check fence height/clearance against the changed stock thickness.\n"
        "4. Open back.cf3d. Verify the reflected layout, actual work offset, "
        "fixtures and holder clearance. Re-establish XY registration and "
        "RE-PROBE THE NEWLY EXPOSED FACE as Z0. Generate paths for BACK items, "
        "preview, preflight and export the separate back program(s).\n"
        "5. Confirm the back operation will not break through the remaining "
        "stock or compromise holding. Consider a small alignment trial.\n\n"
        f"Front models: {', '.join(item.name for item in front.items)}\n"
        f"Back models: {', '.join(item.name for item in back.items)}\n\n"
        "The back geometry has its placement, vector/text edits and Smart "
        "Values baked into reflected mesh data. Edit originals in the source "
        "project and rerun setup if either side needs design changes. "
        "This is NOT direct G-code mirroring, automatic Z-probing or a "
        "physical flip/alignment guarantee.\n"
    )


def save_two_sided_setup(
    project: Project,
    *,
    back_item_ids: frozenset[str] | set[str],
    axis: str,
    destination: Path,
    progress=None,
) -> Path:
    """Build and save both faces in a NEW directory without overwriting files.

    A private sibling folder is fully populated and load-validated before it
    is renamed to the requested final directory.
    """
    folder = Path(destination).expanduser()
    if folder.exists():
        raise FileExistsError(f"Setup folder already exists: {folder}")
    if not folder.parent.is_dir():
        raise FileNotFoundError(f"Parent folder does not exist: {folder.parent}")

    def report(fraction: float, message: str) -> None:
        if progress is not None:
            progress(fraction, message)

    report(0.03, "Validating both face layouts and stock registration")
    front, back = prepare_two_sided(
        project, back_item_ids=back_item_ids, axis=axis,
    )
    report(0.6, "Writing independent front and back projects")
    temporary = Path(tempfile.mkdtemp(
        prefix=".carvefoundry-two-sided-", dir=folder.parent,
    ))
    try:
        save_project(front, temporary / "front.cf3d")
        report(0.77, "Saving reflected back mesh assets")
        save_project(back, temporary / "back.cf3d")
        (temporary / "SETUP_INSTRUCTIONS.txt").write_text(
            setup_instructions(
                original=project, front=front, back=back, axis=axis,
            ),
            encoding="utf-8",
        )
        report(0.9, "Checking both exported projects")
        check_front = load_project(temporary / "front.cf3d")
        check_back = load_project(temporary / "back.cf3d")
        if len(check_front.items) != len(front.items) or len(check_back.items) != len(back.items):
            raise ValueError("Saved face validation failed.")
        if folder.exists():
            raise FileExistsError(f"Setup folder already exists: {folder}")
        temporary.rename(folder)
        report(1.0, "Both face setups saved and verified")
        return folder
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
