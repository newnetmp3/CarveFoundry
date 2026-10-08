"""Deterministic tests for the opt-in native raster benchmarking harness."""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pytest

_SPEC = spec_from_file_location(
    "carvefoundry_native_benchmark",
    Path(__file__).resolve().parents[1] / "scripts" / "benchmark_native_kernels.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_benchmark = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_benchmark)
_fixture = _benchmark._fixture
benchmark = _benchmark.benchmark
main = _benchmark.main


def test_raster_benchmark_fixture_is_stable_and_well_formed():
    vertices, faces, x_axis, y_axis = _fixture(16)
    assert vertices.shape == (4, 3)
    assert faces.shape == (2, 3)
    assert x_axis.shape == (16,)
    assert y_axis.shape == (16,)
    assert np.all(np.diff(x_axis) > 0)


def test_benchmark_python_reference_has_explicit_missing_rust_results():
    result = benchmark(12, 1, rust=False)
    assert result["cells"] == 144
    assert result["python_median_ms"] >= 0.0
    assert result["rust_median_ms"] is None
    assert result["speedup"] is None
    assert result["parity"] is None


@pytest.mark.parametrize("size", [0, 1])
def test_raster_benchmark_rejects_invalid_grid_size(size):
    with pytest.raises(ValueError):
        _fixture(size)


def test_raster_benchmark_cli_can_write_machine_readable_report(tmp_path, monkeypatch):
    monkeypatch.setattr(_benchmark, "native_available", lambda: False)
    path = tmp_path / "baseline.json"
    assert main(["--sizes", "8", "--iterations", "1", "--json", str(path)]) == 0
    content = path.read_text(encoding="utf-8")
    assert '"kernel": "rasterize_top_surface"' in content
    assert '"rust_available": false' in content


def test_raster_benchmark_checks_compiled_kernel_parity_when_available(monkeypatch):
    from carvefoundry.cam.native import native_available

    if not native_available():
        pytest.skip("Compiled native kernel is unavailable")
    monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", "rust")
    result = benchmark(16, 1, rust=True)
    assert result["parity"] == "pass"
    assert result["max_abs_error_mm"] is not None
    assert result["max_abs_error_mm"] < 1e-8
    assert result["rust_median_ms"] >= 0.0
