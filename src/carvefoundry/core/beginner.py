"""Beginner-facing starter projects and advisory setup checks.

Advisories are not CNC preflight and never authorize export. Motion, fixture and
posted-code checks remain the responsibility of the established CAM pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .primitives import ellipse_mesh, text_mesh
from .project import Project, ProjectItem, Stock, TextProperties
from .tools import Cutter, ToolType

STOCK_PRESET_MM = (203.2, 101.6, 19.05)


@dataclass(frozen=True, slots=True)
class MaterialStarter:
    name: str
    description: str
    feed_mm_min: float
    plunge_mm_min: float
    stepdown_factor: float


MATERIAL_STARTERS: tuple[MaterialStarter, ...] = (
    MaterialStarter(
        "Softwood", "Pine and similar easy-cutting woods", 700.0, 200.0, 0.35
    ),
    MaterialStarter(
        "Hardwood", "Maple, walnut and similar solid hardwoods", 550.0, 160.0, 0.25
    ),
    MaterialStarter(
        "Plywood", "Layered sheet goods; watch chip-out and glue", 600.0, 170.0, 0.25
    ),
    MaterialStarter(
        "MDF", "Dust-producing engineered board; extraction is essential",
        650.0, 180.0, 0.30,
    ),
)


def starter_project(
    kind: str = "nameplate", *,
    text: str = "MY FIRST CARVE",
) -> Project:
    """Create a genuine editable CNC example in millimeters.

    A template does not generate or claim to verify any toolpaths.
    """
    stock = Stock(*STOCK_PRESET_MM)
    if kind == "nameplate":
        content = text.strip()
        if not content:
            raise ValueError("Nameplate text cannot be empty.")
        props = TextProperties(
            content=content,
            size_pt=36.0,
            depth_mm=1.2,
            alignment="center",
        )
        mesh = text_mesh(properties=props)
        item = ProjectItem(
            name=content, kind="text", mesh=mesh, text_properties=props,
        )
        name = "First Nameplate"
    elif kind == "coaster":
        mesh = ellipse_mesh(80.0, 80.0, 2.0)
        item = ProjectItem(name="Coaster Shape", kind="ellipse", mesh=mesh)
        name = "First Coaster"
    else:
        raise ValueError(f"Unknown starter template: {kind}")
    project = Project(name=name, stock=stock)
    item.transform = project.default_transform_for_mesh(mesh)
    project.items.append(item)
    return project


def cutter_description(cutter: Cutter) -> str:
    """Explain what this physical tool is normally used for."""
    usage = {
        ToolType.FLAT_END_MILL: (
            "Flat bottom. Common for clearing pockets, facing and rough cutting."
        ),
        ToolType.BALL_NOSE: (
            "Rounded bottom. Common for smoothly finishing 3D relief surfaces."
        ),
        ToolType.V_BIT: (
            "V-shaped point. Common for carved lettering and variable-width details."
        ),
        ToolType.ENGRAVING_CONE: (
            "Fine cone. Common for shallow engraving and delicate outlines."
        ),
        ToolType.TAPERED_BALL_NOSE: (
            "Small round tip and tapered body. Common for detailed 3D relief."
        ),
        ToolType.CUSTOM: (
            "User-defined profile. Confirm its measured dimensions before machining."
        ),
    }[cutter.tool_type]
    return (
        f"{usage}\nDiameter: {cutter.diameter_mm:g} mm"
        + (f" · included angle {cutter.angle_deg:g}°" if cutter.angle_deg else "")
    )


def material_starting_values(
    material: MaterialStarter, cutter: Cutter,
) -> tuple[float, float, float]:
    """Return deliberately modest suggestions, not guaranteed cut parameters."""
    return (
        material.feed_mm_min,
        material.plunge_mm_min,
        max(0.1, min(cutter.diameter_mm * material.stepdown_factor, 3.0)),
    )


def design_advisories(
    project: Project, cutter: Cutter | None, *,
    stale_reason: str | None = None,
) -> tuple[tuple[str, str], ...]:
    """Quick geometry/setup feedback without scanning potentially huge motion lists."""
    issues: list[tuple[str, str]] = []
    stock = project.stock
    if not all(
        isfinite(v) and v > 0
        for v in (stock.width_mm, stock.height_mm, stock.thickness_mm)
    ):
        issues.append(("ERROR", "Stock dimensions must be positive and finite."))
        return tuple(issues)
    if stock.xy_zero != "bottom_left":
        issues.append((
            "ERROR", "This setup expects XY0 at the stock bottom-left corner."
        ))
    visible = [
        item for item in project.items
        if item.visible and item.mesh is not None
    ]
    if not visible:
        issues.append((
            "NEXT STEP", "Add text, a shape, an image trace or an STL model."
        ))
    for item in visible:
        bounds = item.transformed_bounds_mm()
        if bounds is None:
            continue
        low, high = bounds
        if (
            low[0] < -0.001 or low[1] < -0.001
            or high[0] > stock.width_mm + 0.001
            or high[1] > stock.height_mm + 0.001
        ):
            issues.append((
                "CHECK", f"{item.name}: design extends beyond the wood in XY."
            ))
        if high[2] > 0.001 or low[2] < -stock.thickness_mm - 0.001:
            issues.append((
                "CHECK",
                f"{item.name}: geometry is above stock-top Z0 or below the wood.",
            ))
        if cutter is not None and item.kind == "text":
            issues.append((
                "INSPECT",
                f"{item.name}: inspect small letter strokes in the stock-removal "
                f"preview; a {cutter.diameter_mm:g} mm cutter cannot reproduce "
                "arbitrarily narrow detail.",
            ))
    if cutter is None:
        issues.append(("NEXT STEP", "Choose a cutter from the tool library."))
    if not project.fixtures:
        issues.append((
            "CHECK",
            "No clamps/fences are recorded. Add keep-outs before motion preflight.",
        ))
    if stale_reason:
        issues.append((
            "ERROR",
            "Toolpaths are stale after design or setup changes; regenerate them.",
        ))
    elif not project.toolpaths:
        issues.append((
            "NEXT STEP", "Generate a cutter operation before preflight or export."
        ))
    cutters = list(dict.fromkeys(
        path.cutter.name for path in project.toolpaths
    ))
    if len(cutters) > 1:
        issues.append((
            "CHECK",
            f"{len(cutters)} different cutters: stop, change, and reprobe Z0 "
            "before each subsequent program.",
        ))
    if not issues:
        issues.append((
            "INFO", "No obvious design/setup issues found. Run the independent "
            "CNC preflight and check the real machine before cutting.",
        ))
    return tuple(issues)
