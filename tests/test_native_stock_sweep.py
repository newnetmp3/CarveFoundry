"""Native and Python stock sweeps must remove the same material.

The project is intentionally tiny so both complete code paths run on CI.
Comparisons include actual posted NC, repeated passes and all cutter profiles.
"""
from __future__ import annotations

import numpy as np
import pytest

from carvefoundry.cam.native import native_available
from carvefoundry.cam.stock_simulation import simulate_stock_removal
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.cam.virtual_machining import simulate_posted_stock_removal
from carvefoundry.core.machine_profiles import MachineProfile
from carvefoundry.core.project import Project, Stock
from carvefoundry.core.tools import Cutter, ToolType


@pytest.fixture(autouse=True)
def require_native():
    assert native_available(), "Native stock kernel must ship with the compiled extension"


@pytest.mark.parametrize(
    "cutter",
    (
        Cutter("6.35 mm flat", ToolType.FLAT_END_MILL, 6.35),
        Cutter("3 mm ball", ToolType.BALL_NOSE, 3),
        Cutter("22 deg", ToolType.V_BIT, 6.35, angle_deg=22),
        Cutter("0.2 mm tip", ToolType.ENGRAVING_CONE, 4, angle_deg=60,
               tip_diameter_mm=0.2),
        Cutter("tapered", ToolType.TAPERED_BALL_NOSE, 4,
               ball_radius_mm=1.0, taper_angle_deg=15),
        Cutter("custom", ToolType.CUSTOM, 4,
               profile_points=((0, 0), (0.4, 0.15), (1.0, 0.4), (2, 1.0))),
    ),
)
@pytest.mark.parametrize("verified_nc", (False, True))
def test_swept_stock_equals_reference_for_all_cutters(monkeypatch, cutter, verified_nc):
    path = Toolpath(
        "Diagonal/ramp/plunge", "finish", cutter, 6,
        [
            ToolpathMove(3, 4, 6, MoveKind.RAPID),
            ToolpathMove(3, 4, -1.5, MoveKind.PLUNGE, 150),
            ToolpathMove(23, 22, -2.7, MoveKind.CUT, 640),
            ToolpathMove(23, 22, -2.7, MoveKind.CUT, 640),
            ToolpathMove(10, 22, -2.7, MoveKind.CUT, 640),
            ToolpathMove(10, 22, 6, MoveKind.RAPID),
            ToolpathMove(15, 13, 6, MoveKind.RAPID),
            ToolpathMove(15, 13, -3, MoveKind.PLUNGE, 150),
            ToolpathMove(26, 3, -3, MoveKind.CUT, 640),
            ToolpathMove(26, 3, 6, MoveKind.RAPID),
        ],
    )
    project = Project(
        stock=Stock(30, 26, 12),
        toolpaths=[path],
    )
    machine = MachineProfile(work_x_mm=500, work_y_mm=500, work_z_mm=100)

    def calculate(backend):
        monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", backend)
        if verified_nc:
            return simulate_posted_stock_removal(
                project, machine, spacing_mm=0.75, compare_model=False,
            )
        return simulate_stock_removal(
            project, spacing_mm=0.75, compare_model=False,
        )

    reference = calculate("python")
    native = calculate("rust")
    assert native.cut_sample_count == reference.cut_sample_count
    assert native.grid_spacing_mm == reference.grid_spacing_mm
    assert native.stages[0].changed_cells == reference.stages[0].changed_cells
    assert np.allclose(
        native.remaining_z_mm, reference.remaining_z_mm,
        atol=1e-6, rtol=1e-6,
    )
    assert native.removed_volume_mm3 == pytest.approx(
        reference.removed_volume_mm3, abs=1e-4,
    )


def test_air_cuts_and_stock_bottom_are_identical(monkeypatch):
    cutter = Cutter("flat", ToolType.FLAT_END_MILL, 2.0)
    path = Toolpath(
        "Air and bottom", "finish", cutter, 6,
        [
            ToolpathMove(5, 5, 6, MoveKind.RAPID),
            ToolpathMove(5, 5, 1, MoveKind.PLUNGE, 200),
            ToolpathMove(6, 5, 1, MoveKind.CUT, 200),
            ToolpathMove(6, 5, -3.0, MoveKind.PLUNGE, 200),
            ToolpathMove(15, 5, -3.0, MoveKind.CUT, 200),
            ToolpathMove(15, 5, 6, MoveKind.RAPID),
        ],
    )
    project = Project(stock=Stock(20, 10, 3), toolpaths=[path])
    results = []
    for backend in ("python", "rust"):
        monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", backend)
        results.append(simulate_stock_removal(
            project, spacing_mm=1, compare_model=False,
        ))
    np.testing.assert_allclose(
        results[0].remaining_z_mm, results[1].remaining_z_mm, atol=1e-6,
    )
    assert np.min(results[1].remaining_z_mm) == pytest.approx(-3)
