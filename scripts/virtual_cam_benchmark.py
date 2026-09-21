"""Reproducible synthetic, no-machine CNC verification benchmark.

These are *surrogate* test geometries. Real CPO anchor/coin/plaque stock projects
can be added as versioned fixtures when their original source files exist.
Run: python scripts/virtual_cam_benchmark.py [--spacing-mm 1.0]
"""
from __future__ import annotations

import argparse
import json
from itertools import pairwise
from math import dist, isfinite
from time import perf_counter

from carvefoundry.cam.gcode import GrblPostSettings, render_grbl_program
from carvefoundry.cam.gcode_verify import verify_grbl_export
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.cam.virtual_machining import simulate_posted_stock_removal
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.machine_profiles import MachineProfile
from carvefoundry.core.project import Project, Stock
from carvefoundry.core.tools import Cutter, ToolType


def _serpentine(cutter: Cutter, depth: float, *, name: str) -> Toolpath:
    """Four alternating X strokes, safe Z between rows, no spurious XY reversals."""
    safe = 6.0
    moves = [ToolpathMove(10, 10, safe, MoveKind.RAPID)]
    for row, y in enumerate((10, 16, 22, 28)):
        start_x, end_x = (10, 50) if row % 2 == 0 else (50, 10)
        if row:
            moves.append(ToolpathMove(start_x, y, safe, MoveKind.RAPID))
        moves.extend((
            ToolpathMove(start_x, y, depth, MoveKind.PLUNGE, 160),
            ToolpathMove(end_x, y, depth, MoveKind.CUT, 650),
            ToolpathMove(end_x, y, safe, MoveKind.RAPID),
        ))
    return Toolpath(name, "finish", cutter, safe, moves)


def sample_project() -> Project:
    """Small fixture-aware stock and rough/fine/detail sequence, stock-top Z0."""
    project = Project(
        name="Synthetic CAM verification benchmark",
        stock=Stock(60, 40, 19.4),
    )
    project.fixtures = [Fixture("Outside left fence", -8, 0, -3, 40, 3, 1)]
    project.toolpaths = [
        _serpentine(
            Cutter("6.35 mm flat", ToolType.FLAT_END_MILL, 6.35),
            -1.0, name="Rough",
        ),
        _serpentine(
            Cutter("3 mm ball", ToolType.BALL_NOSE, 3.0),
            -2.0, name="Finish",
        ),
        _serpentine(
            Cutter("22 deg V-bit", ToolType.V_BIT, 6.35, angle_deg=22),
            -2.7, name="Detail",
        ),
    ]
    return project


def run_benchmark(*, spacing_mm: float = 1.0) -> dict[str, object]:
    """Return serializable actual posted-NC performance and geometric metrics."""
    if not isfinite(spacing_mm) or spacing_mm <= 0:
        raise ValueError("spacing_mm must be finite and positive")
    project = sample_project()
    machine = MachineProfile(work_x_mm=800, work_y_mm=800, work_z_mm=120)
    options = GrblPostSettings()
    stage_metrics = []
    for path in project.toolpaths:
        code = render_grbl_program([path], options)
        verification = verify_grbl_export(
            code, [path], project.stock, machine, tuple(project.fixtures), options,
        )
        if not verification.safe_to_export:
            raise ValueError(verification.format_report())
        moves = verification.decoded.moves
        stage_metrics.append({
            "name": path.name,
            "tool": path.cutter.name,
            "nc_lines": len(code.splitlines()),
            "decoded_motion_count": len(moves),
            "cut_distance_mm": round(sum(
                dist(a.xyz, b.xyz) for a, b in pairwise(moves)
                if b.kind is not MoveKind.RAPID
            ), 5),
            "rapid_distance_mm": round(sum(
                dist(a.xyz, b.xyz) for a, b in pairwise(moves)
                if b.kind is MoveKind.RAPID
            ), 5),
            "lateral_rapids": sum(
                b.kind is MoveKind.RAPID
                and abs(b.x_mm - a.x_mm) + abs(b.y_mm - a.y_mm) > 1e-8
                for a, b in pairwise(moves)
            ),
            "verified": verification.safe_to_export,
        })
    start = perf_counter()
    result = simulate_posted_stock_removal(
        project, machine, options, spacing_mm=spacing_mm, compare_model=False,
    )
    elapsed = perf_counter() - start
    return {
        "case": "synthetic_three_cutter_serpentine",
        "scope": "offline sampled 2.5D / not physically validated",
        "grid_spacing_mm": result.grid_spacing_mm,
        "stock_mm": [60, 40, 19.4],
        "fixture_count": len(project.fixtures),
        "stages": stage_metrics,
        "removed_volume_mm3": round(result.removed_volume_mm3, 5),
        "cut_samples": result.cut_sample_count,
        "simulation_seconds": round(elapsed, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spacing-mm", type=float, default=1.0)
    args = parser.parse_args()
    print(json.dumps(run_benchmark(spacing_mm=args.spacing_mm), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
