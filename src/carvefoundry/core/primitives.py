from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise
from math import atan2

import numpy as np
import trimesh
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QGuiApplication,
    QPainterPath,
    QPainterPathStroker,
)
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.ops import unary_union

from .mesh import MeshAsset, mesh_asset_from_geometry
from .project import TextProperties


def _top_at_zero(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    result = mesh.copy()
    bounds = np.asarray(result.bounds, dtype=float)
    result.apply_translation((0.0, 0.0, -float(bounds[1, 2])))
    return result


def rectangle_mesh(
    width_mm: float = 50.0,
    height_mm: float = 30.0,
    depth_mm: float = 1.0,
) -> MeshAsset:
    if min(width_mm, height_mm, depth_mm) <= 0:
        raise ValueError("Rectangle dimensions must be greater than zero.")
    mesh = trimesh.creation.box(extents=(width_mm, height_mm, depth_mm))
    return mesh_asset_from_geometry(_top_at_zero(mesh))


def ellipse_mesh(
    width_mm: float = 50.0,
    height_mm: float = 30.0,
    depth_mm: float = 1.0,
    *,
    sections: int = 96,
) -> MeshAsset:
    if min(width_mm, height_mm, depth_mm) <= 0:
        raise ValueError("Ellipse dimensions must be greater than zero.")
    if sections < 12:
        raise ValueError("Ellipse sections must be at least 12.")
    mesh = trimesh.creation.cylinder(radius=1.0, height=depth_mm, sections=sections)
    mesh.apply_scale((width_mm / 2.0, height_mm / 2.0, 1.0))
    return mesh_asset_from_geometry(_top_at_zero(mesh))


def polygon_mesh(
    sides: int = 6,
    diameter_mm: float = 50.0,
    depth_mm: float = 1.0,
) -> MeshAsset:
    if sides < 3:
        raise ValueError("Polygon must have at least three sides.")
    if min(diameter_mm, depth_mm) <= 0:
        raise ValueError("Polygon dimensions must be greater than zero.")
    mesh = trimesh.creation.cylinder(
        radius=diameter_mm / 2.0,
        height=depth_mm,
        sections=sides,
    )
    return mesh_asset_from_geometry(_top_at_zero(mesh))


def line_mesh(
    length_mm: float = 50.0,
    width_mm: float = 2.0,
    depth_mm: float = 1.0,
) -> MeshAsset:
    if min(length_mm, width_mm, depth_mm) <= 0:
        raise ValueError("Line dimensions must be greater than zero.")
    mesh = trimesh.creation.box(extents=(length_mm, width_mm, depth_mm))
    return mesh_asset_from_geometry(_top_at_zero(mesh))


def polyline_mesh(
    points_xy: Iterable[tuple[float, float]],
    *,
    width_mm: float = 2.0,
    depth_mm: float = 1.0,
) -> MeshAsset:
    points = np.asarray(list(points_xy), dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 2:
        raise ValueError("Polyline requires at least two XY points.")
    if not np.isfinite(points).all():
        raise ValueError("Polyline points must be finite.")
    if min(width_mm, depth_mm) <= 0:
        raise ValueError("Polyline width/depth must be greater than zero.")

    parts: list[trimesh.Trimesh] = []
    for start, end in pairwise(points):
        delta = end - start
        length = float(np.linalg.norm(delta))
        if length <= 1e-9:
            continue
        segment = trimesh.creation.box(extents=(length, width_mm, depth_mm))
        angle = atan2(float(delta[1]), float(delta[0]))
        transform = trimesh.transformations.rotation_matrix(angle, (0.0, 0.0, 1.0))
        segment.apply_transform(transform)
        midpoint = (start + end) / 2.0
        segment.apply_translation(
            (float(midpoint[0]), float(midpoint[1]), -depth_mm / 2.0)
        )
        parts.append(segment)

    for point in points:
        join = trimesh.creation.cylinder(
            radius=width_mm / 2.0,
            height=depth_mm,
            sections=24,
        )
        join.apply_translation(
            (float(point[0]), float(point[1]), -depth_mm / 2.0)
        )
        parts.append(join)

    if not parts:
        raise ValueError("Polyline contains no usable segments.")
    mesh = trimesh.util.concatenate(parts)
    return mesh_asset_from_geometry(mesh)


_FONT_5X7: dict[str, tuple[str, ...]] = {
    "A": ("01110","10001","10001","11111","10001","10001","10001"),
    "B": ("11110","10001","10001","11110","10001","10001","11110"),
    "C": ("01111","10000","10000","10000","10000","10000","01111"),
    "D": ("11110","10001","10001","10001","10001","10001","11110"),
    "E": ("11111","10000","10000","11110","10000","10000","11111"),
    "F": ("11111","10000","10000","11110","10000","10000","10000"),
    "G": ("01111","10000","10000","10111","10001","10001","01111"),
    "H": ("10001","10001","10001","11111","10001","10001","10001"),
    "I": ("11111","00100","00100","00100","00100","00100","11111"),
    "J": ("00111","00010","00010","00010","10010","10010","01100"),
    "K": ("10001","10010","10100","11000","10100","10010","10001"),
    "L": ("10000","10000","10000","10000","10000","10000","11111"),
    "M": ("10001","11011","10101","10101","10001","10001","10001"),
    "N": ("10001","11001","10101","10011","10001","10001","10001"),
    "O": ("01110","10001","10001","10001","10001","10001","01110"),
    "P": ("11110","10001","10001","11110","10000","10000","10000"),
    "Q": ("01110","10001","10001","10001","10101","10010","01101"),
    "R": ("11110","10001","10001","11110","10100","10010","10001"),
    "S": ("01111","10000","10000","01110","00001","00001","11110"),
    "T": ("11111","00100","00100","00100","00100","00100","00100"),
    "U": ("10001","10001","10001","10001","10001","10001","01110"),
    "V": ("10001","10001","10001","10001","10001","01010","00100"),
    "W": ("10001","10001","10001","10101","10101","10101","01010"),
    "X": ("10001","10001","01010","00100","01010","10001","10001"),
    "Y": ("10001","10001","01010","00100","00100","00100","00100"),
    "Z": ("11111","00001","00010","00100","01000","10000","11111"),
    "0": ("01110","10001","10011","10101","11001","10001","01110"),
    "1": ("00100","01100","00100","00100","00100","00100","01110"),
    "2": ("01110","10001","00001","00010","00100","01000","11111"),
    "3": ("11110","00001","00001","01110","00001","00001","11110"),
    "4": ("00010","00110","01010","10010","11111","00010","00010"),
    "5": ("11111","10000","10000","11110","00001","00001","11110"),
    "6": ("01110","10000","10000","11110","10001","10001","01110"),
    "7": ("11111","00001","00010","00100","01000","01000","01000"),
    "8": ("01110","10001","10001","01110","10001","10001","01110"),
    "9": ("01110","10001","10001","01111","00001","00001","01110"),
    "-": ("00000","00000","00000","11111","00000","00000","00000"),
    ".": ("00000","00000","00000","00000","00000","00110","00110"),
    "/": ("00001","00010","00010","00100","01000","01000","10000"),
    " ": ("00000","00000","00000","00000","00000","00000","00000"),
}


def text_mesh(
    text: str,
    *,
    height_mm: float = 20.0,
    depth_mm: float = 1.0,
) -> MeshAsset:
    clean = text.upper()
    if not clean.strip():
        raise ValueError("Text cannot be empty.")
    if min(height_mm, depth_mm) <= 0:
        raise ValueError("Text height/depth must be greater than zero.")

    cell = height_mm / 7.0
    stroke = cell * 0.82
    advance = cell * 6.0
    parts: list[trimesh.Trimesh] = []

    for char_index, char in enumerate(clean):
        pattern = _FONT_5X7.get(char)
        if pattern is None:
            pattern = ("11111","10001","00010","00100","00100","00000","00100")
        x_offset = char_index * advance
        for row, row_bits in enumerate(pattern):
            for column, bit in enumerate(row_bits):
                if bit != "1":
                    continue
                block = trimesh.creation.box(
                    extents=(stroke, stroke, depth_mm),
                )
                x = x_offset + (column + 0.5) * cell
                y = (6 - row + 0.5) * cell
                block.apply_translation((x, y, -depth_mm / 2.0))
                parts.append(block)

    if not parts:
        raise ValueError("Text produced no geometry.")
    mesh = trimesh.util.concatenate(parts)
    bounds = np.asarray(mesh.bounds, dtype=float)
    mesh.apply_translation((-bounds[0, 0], -bounds[0, 1], 0.0))
    return mesh_asset_from_geometry(mesh)


def bitmap_runs_mesh(
    mask: np.ndarray,
    *,
    width_mm: float,
    depth_mm: float = 1.0,
) -> MeshAsset:
    """Create a compact relief mesh from a boolean image mask.

    Consecutive active pixels in each row are merged into one rectangle.  This
    keeps trace meshes manageable without requiring an external contour library.
    """

    bitmap = np.asarray(mask, dtype=bool)
    if bitmap.ndim != 2 or bitmap.size == 0:
        raise ValueError("Trace mask must be a non-empty 2D array.")
    if not bitmap.any():
        raise ValueError("Trace mask contains no active pixels.")
    if min(width_mm, depth_mm) <= 0:
        raise ValueError("Trace dimensions must be greater than zero.")

    rows, columns = bitmap.shape
    pixel = width_mm / max(columns, 1)
    parts: list[trimesh.Trimesh] = []

    for row_index, row in enumerate(bitmap):
        padded = np.concatenate(([False], row, [False]))
        changes = np.flatnonzero(padded[1:] != padded[:-1])
        for start, end in changes.reshape((-1, 2)):
            run_width = (end - start) * pixel
            if run_width <= 0:
                continue
            block = trimesh.creation.box(
                extents=(run_width, pixel, depth_mm),
            )
            x = (start + end) * 0.5 * pixel
            y = (rows - row_index - 0.5) * pixel
            block.apply_translation((x, y, -depth_mm / 2.0))
            parts.append(block)

    if not parts:
        raise ValueError("Trace mask produced no geometry.")
    mesh = trimesh.util.concatenate(parts)
    bounds = np.asarray(mesh.bounds, dtype=float)
    mesh.apply_translation((-bounds[0, 0], -bounds[0, 1], 0.0))
    return mesh_asset_from_geometry(mesh)
