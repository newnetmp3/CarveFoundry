"""Planar geometry regressions: closed contour math, holes, Z0 and errors."""
from __future__ import annotations

from math import pi

import numpy as np
import pytest

from carvefoundry.cam.vector_ops import projected_regions
from carvefoundry.core.planar_operations import build_planar_result
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import ProjectItem
from carvefoundry.core.transform import Transform3D


def rectangle(
    name: str,
    width: float = 10.0,
    height: float = 10.0,
    *,
    x: float = 0.0,
    y: float = 0.0,
) -> ProjectItem:
    return ProjectItem(
        name,
        kind="rectangle",
        mesh=rectangle_mesh(width, height, 2.0),
        transform=Transform3D(translation_mm=(x, y, 0.0)),
    )


@pytest.mark.parametrize(
    ("operation", "expected_area"),
    [("union", 150.0), ("intersect", 50.0), ("subtract", 50.0)],
)
def test_boolean_two_overlapping_shapes(operation: str, expected_area: float) -> None:
    a = rectangle("base")
    b = rectangle("other", x=5)
    before_a = a.mesh.mesh.vertices.copy()
    before_b = b.mesh.mesh.vertices.copy()
    result = build_planar_result([a, b], operation=operation, depth_mm=2.5)

    assert result.mesh.is_watertight
    assert projected_regions(result.mesh).area == pytest.approx(expected_area)
    assert np.allclose(result.bounds[0][2], -2.5)
    assert np.allclose(result.bounds[1][2], 0.0)
    assert np.array_equal(before_a, a.mesh.mesh.vertices)
    assert np.array_equal(before_b, b.mesh.mesh.vertices)


def test_subtract_preserves_hole_and_reversing_order_changes_result() -> None:
    outer = rectangle("outer", 20, 20)
    inner = rectangle("inner", 8, 8, x=2, y=1)
    cut = build_planar_result([outer, inner], operation="subtract", depth_mm=3.0)
    geometry = projected_regions(cut.mesh)

    assert geometry.area == pytest.approx(336.0)
    assert len(geometry.interiors) == 1
    assert cut.mesh.is_watertight
    with pytest.raises(ValueError, match="no machinable area"):
        build_planar_result([inner, outer], operation="subtract", depth_mm=3.0)


def test_union_preserves_islands() -> None:
    result = build_planar_result(
        [rectangle("a"), rectangle("b", x=35)],
        operation="union",
        depth_mm=1.0,
    )
    assert result.mesh.is_watertight
    assert len(result.mesh.split(only_watertight=True)) == 2
    assert projected_regions(result.mesh).area == pytest.approx(200.0)


@pytest.mark.parametrize(
    ("distance", "corners", "expected_area"),
    [(2.0, "mitre", 196.0), (-2.0, "round", 36.0)],
)
def test_signed_offset(distance: float, corners: str, expected_area: float) -> None:
    result = build_planar_result(
        [rectangle("square")],
        operation="offset",
        depth_mm=1.5,
        offset_mm=distance,
        join_style=corners,
    )
    assert result.mesh.is_watertight
    assert projected_regions(result.mesh).area == pytest.approx(expected_area)


def test_round_offset_uses_actual_rounded_corners() -> None:
    result = build_planar_result(
        [rectangle("square")],
        operation="offset",
        depth_mm=1.0,
        offset_mm=2.0,
    )
    assert projected_regions(result.mesh).area == pytest.approx(
        100.0 + 80.0 + 4.0 * pi, abs=0.03,
    )


def test_invalid_operations_do_not_modify_sources() -> None:
    a = rectangle("a")
    first = a.mesh.mesh.vertices.copy()
    with pytest.raises(ValueError, match="exactly one"):
        build_planar_result([a, a], operation="offset", depth_mm=1, offset_mm=1)
    with pytest.raises(ValueError, match="non-zero"):
        build_planar_result([a], operation="offset", depth_mm=1, offset_mm=0)
    with pytest.raises(ValueError, match="no machinable area"):
        build_planar_result(
            [a, rectangle("far", x=50)],
            operation="intersect",
            depth_mm=1,
        )
    with pytest.raises(ValueError, match="at least two"):
        build_planar_result([a], operation="union", depth_mm=1)
    with pytest.raises(ValueError, match="finite positive"):
        build_planar_result([a, a], operation="union", depth_mm=float("nan"))
    with pytest.raises(ValueError, match="no X/Y tilt"):
        build_planar_result(
            [a, ProjectItem(
                "tilted",
                kind="rectangle",
                mesh=rectangle_mesh(),
                transform=Transform3D(rotation_deg=(15, 0, 0)),
            )],
            operation="union",
            depth_mm=1,
        )
    with pytest.raises(ValueError, match="planar design shape"):
        build_planar_result(
            [a, ProjectItem("not a vector", kind="stl", mesh=rectangle_mesh())],
            operation="union",
            depth_mm=1,
        )
    assert np.array_equal(a.mesh.mesh.vertices, first)
