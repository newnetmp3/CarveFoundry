from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise
from math import atan2

import numpy as np
import trimesh
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


def _block_text_mesh(
    text: str,
    *,
    height_mm: float,
    depth_mm: float,
) -> MeshAsset:
    """Legacy/headless text fallback used when no Qt GUI font engine exists."""

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
                cell_mesh = trimesh.creation.box(
                    extents=(stroke, stroke, depth_mm),
                )
                x = x_offset + (column + 0.5) * cell
                y = (6 - row + 0.5) * cell
                cell_mesh.apply_translation((x, y, -depth_mm / 2.0))
                parts.append(cell_mesh)

    if not parts:
        raise ValueError("Text produced no geometry.")
    mesh = trimesh.util.concatenate(parts)
    bounds = np.asarray(mesh.bounds, dtype=float)
    mesh.apply_translation((-bounds[0, 0], -bounds[0, 1], 0.0))
    return mesh_asset_from_geometry(mesh)


_FONT_EM_UNITS = 1000
_POINTS_TO_MM = 25.4 / 72.0


def _text_case(content: str, mode: str) -> str:
    if mode == "uppercase":
        return content.upper()
    if mode == "lowercase":
        return content.lower()
    if mode == "title":
        return content.title()
    return content


def _font_for_text(properties: TextProperties):
    """Resolve the exact installed Qt face used for CNC glyph outlines."""

    from PySide6.QtGui import QFont

    from .font_handler import resolve_qt_font_face

    millimeters_per_unit = (
        float(properties.size_pt) * _POINTS_TO_MM / _FONT_EM_UNITS
    )
    font, _resolved = resolve_qt_font_face(
        properties.font_family,
        properties.font_style,
        pixel_size=_FONT_EM_UNITS,
        strict=True,
    )
    if properties.bold:
        font.setBold(True)
    if properties.italic:
        font.setItalic(True)
    font.setKerning(bool(properties.kerning))
    font.setStretch(
        max(1, min(4000, round(float(properties.horizontal_scale_percent))))
    )
    font.setLetterSpacing(
        QFont.SpacingType.AbsoluteSpacing,
        float(properties.character_spacing_mm) / millimeters_per_unit,
    )
    font.setWordSpacing(
        float(properties.word_spacing_mm) / millimeters_per_unit
    )
    return font, millimeters_per_unit


def _wrap_text_lines(
    content: str,
    metrics,
    *,
    width_units: float | None,
    wrap: bool,
) -> list[tuple[str, bool]]:
    """Return line/final-in-paragraph pairs for CNC text layout."""

    paragraphs = content.split("\n")
    result: list[tuple[str, bool]] = []

    for paragraph in paragraphs:
        if not wrap or width_units is None or width_units <= 0:
            result.append((paragraph, True))
            continue
        if not paragraph:
            result.append(("", True))
            continue

        words = paragraph.split(" ")
        current = ""
        lines: list[str] = []
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if current and metrics.horizontalAdvance(candidate) > width_units:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)

        for index, line in enumerate(lines):
            result.append((line, index == len(lines) - 1))

    return result


def _build_text_path(properties: TextProperties):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QFont, QFontMetricsF, QPainterPath

    font, millimeters_per_unit = _font_for_text(properties)
    metrics = QFontMetricsF(font)
    content = _text_case(properties.content, properties.case_mode)

    width_units = (
        float(properties.box_width_mm) / millimeters_per_unit
        if properties.box_width_mm > 0
        else None
    )
    lines = _wrap_text_lines(
        content,
        metrics,
        width_units=width_units,
        wrap=bool(properties.wrap_to_width),
    )
    natural_widths = [
        float(metrics.horizontalAdvance(line))
        for line, _final in lines
    ]
    layout_width = (
        width_units
        if width_units is not None and width_units > 0
        else max(natural_widths, default=0.0)
    )

    glyph_path = QPainterPath()
    decoration_path = QPainterPath()
    baseline = float(metrics.ascent())
    line_advance = max(
        1.0,
        float(metrics.lineSpacing())
        * float(properties.line_spacing_percent)
        / 100.0,
    )

    for (line, final_in_paragraph), natural_width in zip(
        lines,
        natural_widths,
        strict=True,
    ):
        line_font = QFont(font)
        line_metrics = metrics

        if (
            properties.alignment == "justify"
            and not final_in_paragraph
            and layout_width > natural_width
            and line.count(" ") > 0
        ):
            extra_per_space = (
                layout_width - natural_width
            ) / line.count(" ")
            line_font.setWordSpacing(
                font.wordSpacing() + extra_per_space
            )
            line_metrics = QFontMetricsF(line_font)

        line_width = float(line_metrics.horizontalAdvance(line))
        if properties.alignment == "center":
            x = max(0.0, (layout_width - line_width) / 2.0)
        elif properties.alignment == "right":
            x = max(0.0, layout_width - line_width)
        else:
            x = 0.0

        if line:
            glyph_path.addText(
                QPointF(x, baseline),
                line_font,
                line,
            )

            decoration_thickness = max(
                1.0,
                float(line_metrics.lineWidth()),
            )
            if properties.underline:
                underline_y = baseline + float(line_metrics.underlinePos())
                decoration_path.addRect(
                    x,
                    underline_y,
                    line_width,
                    decoration_thickness,
                )
            if properties.strikeout:
                strike_y = baseline - float(line_metrics.strikeOutPos())
                decoration_path.addRect(
                    x,
                    strike_y,
                    line_width,
                    decoration_thickness,
                )

        baseline += line_advance

    return glyph_path, decoration_path, millimeters_per_unit


def _flatten_polygon_geometry(value) -> list[Polygon]:
    if value.is_empty:
        return []
    if isinstance(value, Polygon):
        return [value]
    if isinstance(value, MultiPolygon):
        return [polygon for polygon in value.geoms if not polygon.is_empty]
    if hasattr(value, "geoms"):
        result: list[Polygon] = []
        for geometry in value.geoms:
            result.extend(_flatten_polygon_geometry(geometry))
        return result
    return []


def _text_path_geometry(
    path,
    millimeters_per_unit: float,
):
    """Convert Qt glyph contours into a hole-aware Shapely geometry."""

    contours: list[Polygon] = []
    for polygon in path.toSubpathPolygons():
        coordinates = [
            (
                float(point.x()) * millimeters_per_unit,
                -float(point.y()) * millimeters_per_unit,
            )
            for point in polygon
        ]
        if len(coordinates) < 3:
            continue
        candidate = Polygon(coordinates)
        if not candidate.is_valid:
            candidate = candidate.buffer(0)
        for part in _flatten_polygon_geometry(candidate):
            if part.area > 1e-8:
                contours.append(part)

    if not contours:
        raise ValueError("The selected font produced no usable text outlines.")

    depths: list[int] = []
    for index, contour in enumerate(contours):
        depth = sum(
            1
            for other_index, other in enumerate(contours)
            if other_index != index
            and other.area > contour.area
            and other.contains(contour)
        )
        depths.append(depth)

    geometry = GeometryCollection()
    for depth in sorted(set(depths)):
        level = unary_union(
            [
                contour
                for contour, contour_depth in zip(
                    contours,
                    depths,
                    strict=True,
                )
                if contour_depth == depth
            ]
        )
        if depth % 2 == 0:
            geometry = geometry.union(level)
        else:
            geometry = geometry.difference(level)

    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty:
        raise ValueError("The selected font produced empty text geometry.")
    return geometry


def _extrude_text_geometry(
    geometry,
    depth_mm: float,
    *,
    preserve_x_origin: bool = False,
) -> MeshAsset:
    parts: list[trimesh.Trimesh] = []
    for polygon in _flatten_polygon_geometry(geometry):
        if polygon.area <= 1e-8:
            continue
        mesh = trimesh.creation.extrude_polygon(
            polygon,
            height=float(depth_mm),
            engine="earcut",
        )
        mesh.apply_translation((0.0, 0.0, -float(depth_mm)))
        parts.append(mesh)

    if not parts:
        raise ValueError("Text produced no machinable geometry.")

    mesh = trimesh.util.concatenate(parts)
    bounds = np.asarray(mesh.bounds, dtype=float)
    x_shift = 0.0 if preserve_x_origin else -bounds[0, 0]
    mesh.apply_translation((x_shift, -bounds[0, 1], 0.0))
    return mesh_asset_from_geometry(mesh)


def text_mesh(
    text: str | None = None,
    *,
    height_mm: float = 20.0,
    depth_mm: float = 1.0,
    properties: TextProperties | None = None,
) -> MeshAsset:
    """Build editable CNC text from actual Qt/system font outlines."""

    if properties is None:
        content = text or ""
        properties = TextProperties(
            content=content,
            size_pt=max(
                1.0,
                float(height_mm) / _POINTS_TO_MM,
            ),
            depth_mm=float(depth_mm),
        )
    properties.validate()

    if not properties.content.strip():
        raise ValueError("Text cannot be blank.")

    try:
        from PySide6.QtGui import QGuiApplication
    except ImportError:
        return _block_text_mesh(
            properties.content,
            height_mm=max(
                0.5,
                float(properties.size_pt) * _POINTS_TO_MM,
            ),
            depth_mm=float(properties.depth_mm),
        )

    if QGuiApplication.instance() is None:
        return _block_text_mesh(
            properties.content,
            height_mm=max(
                0.5,
                float(properties.size_pt) * _POINTS_TO_MM,
            ),
            depth_mm=float(properties.depth_mm),
        )

    glyph_path, decoration_path, millimeters_per_unit = _build_text_path(
        properties
    )
    geometry = _text_path_geometry(glyph_path, millimeters_per_unit)

    if properties.geometry_mode == "outline":
        # Build the CNC outline from the already hole-aware glyph polygons
        # instead of QPainterPathStroker output.  Qt's stroker can emit
        # touching/self-overlapping subpaths differently across fontconfig
        # versions, which in turn can create non-watertight extrusion seams.
        geometry = geometry.boundary.buffer(
            float(properties.outline_width_mm) / 2.0,
            quad_segs=12,
            cap_style="round",
            join_style="round",
        )

    if not decoration_path.isEmpty():
        decoration_geometry = _text_path_geometry(
            decoration_path,
            millimeters_per_unit,
        )
        geometry = geometry.union(decoration_geometry)

    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty:
        raise ValueError("The selected font produced empty text geometry.")

    return _extrude_text_geometry(
        geometry,
        properties.depth_mm,
        preserve_x_origin=properties.box_width_mm > 0,
    )


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
