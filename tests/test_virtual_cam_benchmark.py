"""Pin virtual CAM benchmark geometry and NC metrics without machine access."""
from __future__ import annotations

from pathlib import Path
from runpy import run_path

import pytest

_script = run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "virtual_cam_benchmark.py"),
    run_name="carvefoundry_virtual_cam_benchmark",
)
run_benchmark = _script["run_benchmark"]
sample_project = _script["sample_project"]


def test_benchmark_has_real_distinct_cutter_stages_and_stock_fence():
    project = sample_project()
    assert len(project.toolpaths) == 3
    assert len({p.cutter.tool_type for p in project.toolpaths}) == 3
    assert project.stock.thickness_mm == pytest.approx(19.4)
    assert len(project.fixtures) == 1


def test_reproducible_nc_benchmark_enforces_path_quality_and_stock_removal():
    result = run_benchmark(spacing_mm=2.0)
    assert result["case"] == "synthetic_three_cutter_serpentine"
    assert result["fixture_count"] == 1
    assert result["removed_volume_mm3"] > 0
    assert result["cut_samples"] > 0
    assert len(result["stages"]) == 3
    assert all(stage["verified"] for stage in result["stages"])
    assert all(stage["lateral_rapids"] == 3 for stage in result["stages"])
    assert all(stage["cut_distance_mm"] >= 160 for stage in result["stages"])


@pytest.mark.parametrize("spacing", [0, -1, float("nan"), float("inf")])
def test_benchmark_rejects_unbounded_grid_spacing(spacing):
    with pytest.raises(ValueError, match="spacing_mm"):
        run_benchmark(spacing_mm=spacing)
