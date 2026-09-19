"""Physical cutter sweep removes sampled stock instead of merely animating G-code."""
from __future__ import annotations

import numpy as np
import pytest

from carvefoundry.cam.stock_simulation import simulate_stock_removal
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.tools import Cutter, ToolType
from carvefoundry.core.transform import Transform3D


def path(name, cutter, *, depth=-2, x=10, y=10, operation="finish"):
    return Toolpath(
        name=name, operation=operation, cutter=cutter,
        source_item_name="Part", source_item_id="part",
        safe_z_mm=5,
        moves=[
            ToolpathMove(x, y, 5, MoveKind.RAPID),
            ToolpathMove(x, y, depth, MoveKind.PLUNGE, 100),
            ToolpathMove(x + 2, y, depth, MoveKind.CUT, 250),
        ],
    )


def project(paths):
    return Project(
        stock=Stock(24, 24, 9), toolpaths=list(paths),
    )


def test_flat_cutter_removes_real_stock_and_rapids_never_remove_it():
    flat = Cutter("flat", ToolType.FLAT_END_MILL, 4)
    result = simulate_stock_removal(
        project([path("Pocket", flat, operation="pocket")]),
        spacing_mm=1.0, compare_model=False,
    )
    assert result.remaining_z_mm[10, 10] == pytest.approx(-2)
    assert result.remaining_z_mm[10, 12] == pytest.approx(-2)
    assert result.remaining_z_mm[20, 20] == pytest.approx(0)
    assert result.removed_volume_cm3 > 0.01
    assert result.stages[0].removed_volume_mm3 == pytest.approx(
        result.removed_volume_mm3, abs=0.00001,
    )
    assert result.cut_sample_count > 1

    rapid_only = Toolpath(
        "Travel", "finish", flat, 5,
        [ToolpathMove(10, 10, 5, MoveKind.RAPID),
         ToolpathMove(12, 10, -2, MoveKind.RAPID)],
    )
    empty_result = simulate_stock_removal(
        project([rapid_only]), spacing_mm=1, compare_model=False,
    )
    assert not np.any(empty_result.remaining_z_mm)
    assert empty_result.removed_volume_mm3 == 0


def test_ball_cutter_preserves_material_near_outer_radius():
    ball = Cutter("ball", ToolType.BALL_NOSE, 4)
    result = simulate_stock_removal(
        project([path("Finish", ball)]),
        spacing_mm=1, compare_model=False,
    )
    assert result.remaining_z_mm[10, 10] == pytest.approx(-2)
    assert result.remaining_z_mm[12, 10] == pytest.approx(0)
    assert -2 < result.remaining_z_mm[11, 10] < 0


def test_conical_cutter_removes_only_tip_at_outer_radius():
    cutter = Cutter("v", ToolType.V_BIT, 4, angle_deg=90)
    result = simulate_stock_removal(
        project([path("Engrave", cutter, depth=-1, operation="engrave")]),
        spacing_mm=1, compare_model=False,
    )
    assert result.remaining_z_mm[10, 10] == pytest.approx(-1)
    assert result.remaining_z_mm[11, 10] == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize(
    "cutter",
    [
        Cutter(
            "tapered ball", ToolType.TAPERED_BALL_NOSE, 4,
            taper_angle_deg=15, ball_radius_mm=0.5,
        ),
        Cutter(
            "custom", ToolType.CUSTOM, 4,
            profile_points=((0, 0), (0.5, 0.2), (2, 1.0)),
        ),
    ],
)
def test_tapered_and_custom_simulation_uses_authoritative_profile(cutter):
    result = simulate_stock_removal(
        project([path("Details", cutter, depth=-3)]),
        spacing_mm=1, compare_model=False,
    )
    assert result.remaining_z_mm[10, 10] == pytest.approx(-3)
    assert result.remaining_z_mm[11, 10] == pytest.approx(
        min(0, -3 + cutter.profile_height_mm(1)), abs=1e-6,
    )


def test_multiple_stages_reduce_same_stock_not_reset_per_cutter():
    flat = Cutter("flat", ToolType.FLAT_END_MILL, 4)
    first = path("Rough", flat, depth=-1, operation="rough")
    second = path("Finish", flat, depth=-2)
    result = simulate_stock_removal(
        project([first, second]), spacing_mm=1, compare_model=False,
    )
    assert len(result.stages) == 2
    assert result.stages[0].removed_volume_mm3 > 0
    assert result.stages[1].removed_volume_mm3 > 0
    assert sum(s.removed_volume_mm3 for s in result.stages) == pytest.approx(
        result.removed_volume_mm3, abs=1e-5,
    )


def test_mesh_surface_comparison_tracks_undercut_and_gouges():
    cutter = Cutter("flat", ToolType.FLAT_END_MILL, 2)
    part = ProjectItem(
        name="Part", kind="stl", mesh=rectangle_mesh(10, 10, 2),
        transform=Transform3D(translation_mm=(7, 7, 0)),
    )
    scene = project([path("Finish", cutter)])
    scene.items.append(part)
    result = simulate_stock_removal(scene, spacing_mm=1)
    remaining, gouged, tested = result.deviation_counts()
    assert tested > 0
    assert remaining == 0
    assert gouged > 0
    assert result.target_z_mm is not None


@pytest.mark.parametrize("invalid", ["empty", "no_initial_rapid", "too_deep", "dense"])
def test_refuses_invalid_stock_simulation(invalid):
    flat = Cutter("flat", ToolType.FLAT_END_MILL, 4)
    scene = project([path("Cut", flat)])
    spacing = 1
    if invalid == "empty":
        scene.toolpaths = []
    elif invalid == "no_initial_rapid":
        scene.toolpaths[0].moves.pop(0)
    elif invalid == "too_deep":
        scene.toolpaths[0].moves[1] = ToolpathMove(
            10, 10, -10, MoveKind.PLUNGE, 100,
        )
    elif invalid == "dense":
        spacing = 0.001
    with pytest.raises(ValueError):
        simulate_stock_removal(scene, spacing_mm=spacing, compare_model=False)
