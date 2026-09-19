"""Sampled cutter-swept stock simulation for 3-axis top-down machining.

Unlike a G-code backplot, this updates *remaining material* at every XY stock
sample using the actual cutter radial profile, per-toolpath order and motion
Z. The representation is a 2.5D height-field (no undercuts, holder or machine
kinematics); it is deliberately not a claim of exact continuous CSG.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import ceil, hypot, isfinite, radians, tan

import numpy as np

from carvefoundry.cam.heightfield import _rasterize_top_surface_python
from carvefoundry.cam.native import rasterize_top_surface as _native_rasterize_top_surface
from carvefoundry.cam.toolpath import MoveKind, Toolpath
from carvefoundry.core.project import Project, Stock
from carvefoundry.core.tools import Cutter, ToolType

MAX_GRID_CELLS = 600_000
MAX_PATH_SAMPLES = 2_000_000


@dataclass(frozen=True, slots=True)
class RemovalStage:
    name: str
    cutter_name: str
    removed_volume_mm3: float
    changed_cells: int


@dataclass(frozen=True, slots=True)
class StockRemovalResult:
    x_mm: np.ndarray
    y_mm: np.ndarray
    remaining_z_mm: np.ndarray
    target_z_mm: np.ndarray | None
    removed_volume_mm3: float
    cut_sample_count: int
    grid_spacing_mm: float
    stages: tuple[RemovalStage, ...]

    @property
    def removed_volume_cm3(self) -> float:
        return self.removed_volume_mm3 / 1000.0

    @property
    def target_valid(self) -> np.ndarray | None:
        if self.target_z_mm is None:
            return None
        return np.isfinite(self.target_z_mm)

    def deviation_counts(self, tolerance_mm: float = 0.15) -> tuple[int, int, int]:
        """(uncut/remaining above target, gouged below target, compared cells)."""
        if tolerance_mm < 0 or not isfinite(tolerance_mm):
            raise ValueError("Comparison tolerance must be finite and nonnegative.")
        mask = self.target_valid
        if mask is None or not mask.any():
            return 0, 0, 0
        delta = self.remaining_z_mm[mask] - self.target_z_mm[mask]
        return (
            int(np.count_nonzero(delta > tolerance_mm)),
            int(np.count_nonzero(delta < -tolerance_mm)),
            int(np.count_nonzero(mask)),
        )


def _axes(stock: Stock, spacing_mm: float) -> tuple[np.ndarray, np.ndarray, float]:
    dims = (stock.width_mm, stock.height_mm, stock.thickness_mm)
    if not all(isfinite(v) and v > 0 for v in dims):
        raise ValueError("Stock must have positive finite XYZ dimensions.")
    if not isfinite(spacing_mm) or spacing_mm <= 0:
        raise ValueError("Simulation spacing must be positive and finite.")
    if stock.xy_zero != "bottom_left":
        raise ValueError("Simulation currently requires stock-bottom-left XY0.")
    nx = max(2, ceil(stock.width_mm / spacing_mm) + 1)
    ny = max(2, ceil(stock.height_mm / spacing_mm) + 1)
    if nx * ny > MAX_GRID_CELLS:
        raise ValueError(
            f"Simulation needs {nx * ny:,} cells; increase the spacing "
            f"(maximum {MAX_GRID_CELLS:,} cells)."
        )
    x = np.linspace(0.0, stock.width_mm, nx)
    y = np.linspace(0.0, stock.height_mm, ny)
    return x, y, float(max(x[1] - x[0], y[1] - y[0]))


def _target_surface(
    project: Project,
    x: np.ndarray,
    y: np.ndarray,
    progress: Callable[[float, str], None] | None,
) -> np.ndarray | None:
    """Merge visible design meshes without blank outside-region comparison."""
    meshes = [
        item.transformed_mesh()
        for item in project.items if item.visible and item.mesh is not None
    ]
    if not meshes:
        return None
    result = np.full((len(y), len(x)), -np.inf)
    for index, mesh in enumerate(meshes):
        if mesh is None:
            continue
        vertices = np.asarray(mesh.vertices, dtype=float)
        faces = np.asarray(mesh.faces, dtype=np.int64)
        z = _native_rasterize_top_surface(vertices, faces, x, y)
        if z is None:
            z = _rasterize_top_surface_python(vertices, faces, x, y)
        np.maximum(result, z, out=result)
        if progress is not None:
            progress(
                0.77 + 0.20 * (index + 1) / len(meshes),
                "Comparing finished stock against model surface",
            )
    result[~np.isfinite(result)] = np.nan
    return result if np.isfinite(result).any() else None


def _tool_sample(
    surface: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    cutter: Cutter,
    center_x: float,
    center_y: float,
    tip_z: float,
    stock_bottom: float,
) -> int:
    """Cut local raster cells, honoring radial cutter height above its tip."""
    radius = cutter.radius_mm
    if tip_z > 0 or (
        center_x + radius < x[0] or center_x - radius > x[-1]
        or center_y + radius < y[0] or center_y - radius > y[-1]
    ):
        return 0
    ix0 = max(0, int(np.searchsorted(x, center_x - radius, side="left")))
    ix1 = min(len(x), int(np.searchsorted(x, center_x + radius, side="right")))
    iy0 = max(0, int(np.searchsorted(y, center_y - radius, side="left")))
    iy1 = min(len(y), int(np.searchsorted(y, center_y + radius, side="right")))
    if ix0 >= ix1 or iy0 >= iy1:
        return 0
    xx, yy = np.meshgrid(x[ix0:ix1], y[iy0:iy1])
    distances = np.hypot(xx - center_x, yy - center_y)
    inside = distances <= radius + 1e-9
    if not inside.any():
        return 0
    # The cutter may be tapered, conical, spherical, flat, or a custom
    # rotational profile. Only distances within the cutter's stated radius
    # are passed to the authoritative cutter geometry function.
    radial = np.minimum(distances, radius)
    kind = cutter.tool_type
    if kind is ToolType.FLAT_END_MILL:
        profiles = np.zeros_like(radial)
    elif kind is ToolType.BALL_NOSE:
        profiles = radius - np.sqrt(
            np.maximum(0.0, radius * radius - radial * radial)
        )
    elif kind in (ToolType.V_BIT, ToolType.ENGRAVING_CONE):
        tip = cutter.tip_diameter_mm / 2.0
        profiles = np.maximum(0.0, radial - tip) / tan(
            radians(float(cutter.angle_deg) / 2.0)
        )
    elif kind is ToolType.TAPERED_BALL_NOSE:
        ball = float(cutter.ball_radius_mm)
        curve = ball - np.sqrt(np.maximum(0.0, ball * ball - radial * radial))
        taper = ball + (radial - ball) / tan(radians(float(cutter.taper_angle_deg)))
        profiles = np.where(radial <= ball, curve, taper)
    elif kind is ToolType.CUSTOM and cutter.profile_points is not None:
        radii, heights = zip(*cutter.profile_points, strict=True)
        profiles = np.interp(radial, radii, heights)
    else:
        raise ValueError(f"{cutter.name}: simulation needs a defined cutter profile.")
    target = surface[iy0:iy1, ix0:ix1]
    new_z = np.maximum(tip_z + profiles, stock_bottom)
    updated = inside & (new_z < target - 1e-9)
    np.minimum(target, np.where(updated, new_z, target), out=target)
    return int(np.count_nonzero(updated))


def simulate_stock_removal(
    project: Project,
    *,
    spacing_mm: float = 0.5,
    progress: Callable[[float, str], None] | None = None,
    compare_model: bool = True,
) -> StockRemovalResult:
    """Simulate all project toolpaths on a bounded height-field of raw stock.

    Rapid traversals never remove material. Cutting/plunge moves are sampled
    at most half a pixel apart, including Z ramps, and cut only where the
    selected cutter's surface lies below the previous stock. Real material
    removal is approximated at grid centers; volume is an estimate. Neither
    air cuts nor retracts are interpreted as machining.
    """
    x, y, spacing = _axes(project.stock, spacing_mm)
    paths: Sequence[Toolpath] = project.toolpaths
    if not paths or any(not path.moves for path in paths):
        raise ValueError("Calculate nonempty toolpaths before simulating material removal.")
    for path in paths:
        if path.moves[0].kind is not MoveKind.RAPID:
            raise ValueError(f"{path.name}: first move must establish safe XY as rapid.")
        if path.safe_z_mm < 0:
            raise ValueError(f"{path.name}: safe Z cannot lie inside the stock.")
        for move in path.moves:
            if move.kind is not MoveKind.RAPID and move.z_mm < -project.stock.thickness_mm - 1e-6:
                raise ValueError(f"{path.name}: cutting move extends through stock bottom.")

    height = np.zeros((len(y), len(x)), dtype=np.float32)
    pixel_area = float((x[1] - x[0]) * (y[1] - y[0]))
    stages: list[RemovalStage] = []
    count = 0
    total_moves = max(1, sum(len(path.moves) - 1 for path in paths))
    seen = 0

    for path in paths:
        before_sum = float(height.sum(dtype=np.float64))
        changed_cells = 0
        previous = path.moves[0]
        for move in path.moves[1:]:
            if move.kind is not MoveKind.RAPID:
                distance = hypot(
                    move.x_mm - previous.x_mm,
                    move.y_mm - previous.y_mm,
                )
                samples = max(1, ceil(distance / (0.5 * spacing)))
                if count + samples + 1 > MAX_PATH_SAMPLES:
                    raise ValueError(
                        "Simulation path sampling limit exceeded; increase "
                        "grid spacing or simulate a smaller machining job."
                    )
                for step in range(samples + 1):
                    t = step / samples
                    changed_cells += _tool_sample(
                        height, x, y, path.cutter,
                        previous.x_mm + t * (move.x_mm - previous.x_mm),
                        previous.y_mm + t * (move.y_mm - previous.y_mm),
                        previous.z_mm + t * (move.z_mm - previous.z_mm),
                        -project.stock.thickness_mm,
                    )
                count += samples + 1
            previous = move
            seen += 1
            if progress is not None and seen % 256 == 0:
                progress(
                    0.75 * seen / total_moves,
                    f"Simulating swept cutter volume: {path.name}",
                )
        after_sum = float(height.sum(dtype=np.float64))
        stages.append(RemovalStage(
            path.name,
            path.cutter.name,
            max(0.0, (before_sum - after_sum) * pixel_area),
            changed_cells,
        ))
    removed = -float(height.sum(dtype=np.float64)) * pixel_area
    if progress is not None:
        progress(0.76, "Calculating remaining stock and cut volume")
    target = _target_surface(project, x, y, progress) if compare_model else None
    if progress is not None:
        progress(1.0, "Material removal simulation complete")
    return StockRemovalResult(
        x_mm=x,
        y_mm=y,
        remaining_z_mm=height,
        target_z_mm=target,
        removed_volume_mm3=max(0.0, removed),
        cut_sample_count=count,
        grid_spacing_mm=spacing,
        stages=tuple(stages),
    )
