import numpy as np
import pytest
import trimesh
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from carvefoundry.cam.basic_ops import (
    BasicCamSettings,
    PocketStrategy,
)
from carvefoundry.cam.toolpath import MoveKind
from carvefoundry.cam.vector_ops import (
    geometry_drill,
    geometry_engrave,
    geometry_pocket,
    geometry_profile,
    geometry_vcarve,
    projected_regions,
)
from carvefoundry.core.tools import Cutter, ToolType


def _extrude(geometry, depth: float = 3.0) -> trimesh.Trimesh:
    mesh = trimesh.creation.extrude_polygon(
        geometry,
        height=depth,
        engine="earcut",
    )
    mesh.apply_translation((0.0, 0.0, -depth))
    return mesh


def _settings(**kwargs) -> BasicCamSettings:
    values = {
        "safe_z_mm": 1.5,
        "feed_mm_min": 1000.0,
        "plunge_feed_mm_min": 300.0,
        "max_stepdown_mm": 1.0,
        "stepover_fraction": 0.4,
        "finish_stepover_fraction": 0.08,
        "overall_depth_mm": 1.0,
        "pocket_strategy": PocketStrategy.RASTER_X,
    }
    values.update(kwargs)
    return BasicCamSettings(**values)


def _donut_mesh() -> trimesh.Trimesh:
    polygon = Polygon(
        [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)],
        holes=[[(7.0, 7.0), (13.0, 7.0), (13.0, 13.0), (7.0, 13.0)]],
    )
    return _extrude(polygon)


def _cut_xy(toolpath) -> np.ndarray:
    return np.asarray(
        [
            (move.x_mm, move.y_mm)
            for move in toolpath.moves
            if move.kind is MoveKind.CUT
        ],
        dtype=float,
    )


def test_projected_regions_preserve_holes_and_disconnected_islands() -> None:
    geometry = unary_union(
        [
            Polygon(
                [(0, 0), (10, 0), (10, 10), (0, 10)],
                holes=[[(3, 3), (7, 3), (7, 7), (3, 7)]],
            ),
            box(15, 2, 19, 6),
        ]
    )
    projected = projected_regions(_extrude(geometry))

    assert projected.area == pytest.approx(100.0 - 16.0 + 16.0, abs=0.05)
    assert len(getattr(projected, "geoms", [projected])) == 2


def test_profile_and_engrave_follow_internal_model_contours() -> None:
    mesh = _donut_mesh()
    cutter = Cutter("2 mm flat", ToolType.FLAT_END_MILL, 2.0)
    settings = _settings()

    profile = geometry_profile(
        mesh,
        cutter,
        settings,
        offset_mode="on",
    )
    engrave = geometry_engrave(mesh, cutter, settings)

    for toolpath in (profile, engrave):
        points = _cut_xy(toolpath)
        assert len(points) > 8
        inner = (
            np.isclose(points[:, 0], 7.0, atol=0.05)
            | np.isclose(points[:, 0], 13.0, atol=0.05)
            | np.isclose(points[:, 1], 7.0, atol=0.05)
            | np.isclose(points[:, 1], 13.0, atol=0.05)
        )
        assert np.any(inner), "internal hole contour was omitted"


def test_polygon_pocket_never_links_across_hole() -> None:
    mesh = _donut_mesh()
    cutter = Cutter("2 mm flat", ToolType.FLAT_END_MILL, 2.0)
    settings = _settings(
        overall_depth_mm=0.8,
        max_stepdown_mm=1.0,
        pocket_strategy=PocketStrategy.RASTER_X,
    )
    toolpath = geometry_pocket(mesh, cutter, settings)
    work = projected_regions(mesh).buffer(-cutter.radius_mm, join_style=2)
    buffered_work = work.buffer(1e-6)

    previous = None
    for move in toolpath.moves:
        if move.kind is MoveKind.RAPID:
            previous = move
            continue
        if move.kind is MoveKind.CUT and previous is not None:
            segment = LineString(
                (
                    (previous.x_mm, previous.y_mm),
                    (move.x_mm, move.y_mm),
                )
            )
            assert buffered_work.covers(segment)
        previous = move


def test_vcarve_uses_tool_angle_and_region_width_for_depth() -> None:
    cutter = Cutter(
        "60 degree V",
        ToolType.V_BIT,
        6.0,
        angle_deg=60.0,
    )
    settings = _settings(
        overall_depth_mm=None,
        max_stepdown_mm=2.0,
        finish_stepover_fraction=0.04,
    )

    narrow = geometry_vcarve(
        _extrude(box(0, 0, 3, 15), depth=8.0),
        cutter,
        settings,
    )
    wide = geometry_vcarve(
        _extrude(box(0, 0, 8, 15), depth=8.0),
        cutter,
        settings,
    )

    narrow_depths = {
        round(move.z_mm, 4)
        for move in narrow.moves
        if move.kind is MoveKind.CUT
    }
    wide_depths = {
        round(move.z_mm, 4)
        for move in wide.moves
        if move.kind is MoveKind.CUT
    }

    assert len(narrow_depths) > 2
    assert len(wide_depths) > 2
    assert min(wide_depths) < min(narrow_depths)

    wide_xy = _cut_xy(wide)
    assert np.any(
        (wide_xy[:, 0] > 0.1)
        & (wide_xy[:, 0] < 7.9)
        & (wide_xy[:, 1] > 0.1)
        & (wide_xy[:, 1] < 14.9)
    )


def test_vcarve_rejects_non_conical_cutters() -> None:
    mesh = _extrude(box(0, 0, 10, 10))
    cutter = Cutter("flat", ToolType.FLAT_END_MILL, 3.0)

    with pytest.raises(ValueError, match="V-bit or engraving-cone"):
        geometry_vcarve(mesh, cutter, _settings())


def test_drill_uses_real_circular_features_not_bounds_center() -> None:
    plate = box(0, 0, 20, 12)
    holes = unary_union(
        [
            Point(5, 6).buffer(1.5, resolution=32),
            Point(15, 6).buffer(2.0, resolution=32),
        ]
    )
    mesh = _extrude(plate.difference(holes), depth=4.0)
    cutter = Cutter("drill", ToolType.FLAT_END_MILL, 2.0)
    toolpath = geometry_drill(
        mesh,
        cutter,
        _settings(overall_depth_mm=2.0),
    )

    rapid_xy = {
        (round(move.x_mm, 2), round(move.y_mm, 2))
        for move in toolpath.moves
        if move.kind is MoveKind.RAPID
    }
    assert (5.0, 6.0) in rapid_xy
    assert (15.0, 6.0) in rapid_xy
    assert (10.0, 6.0) not in rapid_xy


def test_drill_refuses_non_circular_placeholder_center() -> None:
    mesh = _extrude(box(0, 0, 20, 10))
    cutter = Cutter("drill", ToolType.FLAT_END_MILL, 2.0)

    with pytest.raises(ValueError, match="no circular projected features"):
        geometry_drill(mesh, cutter, _settings())
