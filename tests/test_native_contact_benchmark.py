"""Tests for the opt-in Python/Rust cutter-contact numerical benchmark."""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pytest

_SPEC = spec_from_file_location(
    "carvefoundry_contact_benchmark",
    Path(__file__).resolve().parents[1] / "scripts" / "benchmark_contact_kernel.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_benchmark = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_benchmark)

contact_fixture = _benchmark.contact_fixture
benchmark = _benchmark.benchmark
main = _benchmark.main


@pytest.mark.parametrize("scene", ["smooth", "holes", "ridge"])
@pytest.mark.parametrize("profile", ["flat", "ball"])
def test_contact_fixtures_are_reproducible(scene: str, profile: str) -> None:
    first, footprint = contact_fixture(16, scene, profile)
    second, footprint_again = contact_fixture(16, scene, profile)
    np.testing.assert_array_equal(first, second)
    assert footprint == footprint_again
    assert first.shape == (16, 16)
    assert len(footprint) > 1


def test_missing_height_samples_are_preserved_in_fixture() -> None:
    source, _samples = contact_fixture(16, "holes", "flat")
    assert np.isnan(source).any()
    assert np.isneginf(source).any()
    assert np.isfinite(source).any()


@pytest.mark.parametrize("scene", ["smooth", "holes", "ridge"])
def test_contact_benchmark_python_reference(scene: str) -> None:
    value = benchmark(12, 1, scene=scene, profile="ball", rust=False)
    assert value["python_median_ms"] >= 0
    assert value["rust_median_ms"] is None
    assert value["parity"] is None


@pytest.mark.parametrize("scene", ["smooth", "holes", "ridge"])
@pytest.mark.parametrize("profile", ["flat", "ball"])
def test_contact_benchmark_native_parity_when_available(
    scene: str, profile: str, monkeypatch,
) -> None:
    from carvefoundry.cam.native import native_available

    if not native_available():
        pytest.skip("Compiled native extension unavailable.")
    monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", "rust")
    value = benchmark(16, 1, scene=scene, profile=profile, rust=True)
    assert value["parity"] == "pass"
    assert value["max_abs_error_mm"] <= 1e-8


@pytest.mark.parametrize(
    "size,scene,profile",
    [(1, "smooth", "flat"), (8, "bad", "flat"), (8, "smooth", "bad")],
)
def test_invalid_contact_fixture_is_rejected(size, scene, profile) -> None:
    with pytest.raises(ValueError):
        contact_fixture(size, scene, profile)


def test_contact_cli_writes_python_only_json_when_rust_absent(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setattr(_benchmark, "native_available", lambda: False)
    path = tmp_path / "contact.json"
    assert main([
        "--sizes", "8", "--iterations", "1", "--scenes", "holes",
        "--profiles", "flat", "--json", str(path),
    ]) == 0
    contents = path.read_text(encoding="utf-8")
    assert '"kernel": "compensate_height_field"' in contents
    assert '"rust_available": false' in contents
