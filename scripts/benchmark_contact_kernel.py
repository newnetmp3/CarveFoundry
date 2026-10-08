"""Parity-first Python/Rust cutter-contact benchmark using synthetic height fields.

This is an opt-in numerical diagnostic, not a CNC cutting validation.
Run with: python scripts/benchmark_contact_kernel.py --json contact.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
from math import sqrt
from pathlib import Path
from time import perf_counter

import numpy as np

from carvefoundry.cam.contact import _compensate_height_field_python
from carvefoundry.cam.native import compensate_height_field, native_available


def contact_fixture(
    size: int, scene: str = "smooth", profile: str = "flat",
) -> tuple[np.ndarray, list[tuple[int, int, float]]]:
    """Return a reproducible height field and radial cutter footprint."""
    if size < 4:
        raise ValueError("Contact grid size must be at least four.")
    if scene not in {"smooth", "holes", "ridge"}:
        raise ValueError("Unknown contact benchmark scene.")
    if profile not in {"flat", "ball"}:
        raise ValueError("Unknown contact benchmark cutter profile.")

    coordinate = np.linspace(-1.0, 1.0, size, dtype=np.float64)
    x, y = np.meshgrid(coordinate, coordinate)
    surface = (2.0 + 0.5 * x + 0.25 * y).astype(np.float64)
    if scene == "holes":
        surface[(x**2 + y**2) < 0.15] = np.nan
        surface[0, :] = -np.inf
    elif scene == "ridge":
        surface += 2.5 * np.exp(-40.0 * (x - y) ** 2)

    footprint = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            distance_squared = float(dx * dx + dy * dy)
            if distance_squared > 9.0:
                continue
            rise = (
                0.0 if profile == "flat"
                else 3.0 - sqrt(9.0 - distance_squared)
            )
            footprint.append((dy, dx, rise))
    return surface, footprint


def median_wall_ms(callback, iterations: int) -> float:
    callback()  # warmup outside measured samples
    measurements = []
    for _ in range(iterations):
        start = perf_counter()
        callback()
        measurements.append((perf_counter() - start) * 1000.0)
    return float(statistics.median(measurements))


def benchmark(
    size: int, iterations: int, *, scene: str, profile: str, rust: bool,
) -> dict:
    if iterations < 1:
        raise ValueError("Iterations must be positive.")
    source_z, footprint = contact_fixture(size, scene, profile)

    def python_reference():
        return _compensate_height_field_python(source_z, footprint)

    reference = python_reference()
    result = {
        "size": size,
        "scene": scene,
        "profile": profile,
        "samples": len(footprint),
        "python_median_ms": median_wall_ms(python_reference, iterations),
        "rust_median_ms": None,
        "speedup": None,
        "max_abs_error_mm": None,
        "parity": None,
    }
    if rust:
        def native_kernel():
            return compensate_height_field(source_z, footprint)

        actual = native_kernel()
        if actual is None:
            raise RuntimeError("Rust cutter-contact kernel returned no result.")
        np.testing.assert_allclose(
            actual, reference, rtol=1e-8, atol=1e-9, equal_nan=True,
        )
        finite = np.isfinite(actual) & np.isfinite(reference)
        largest_error = (
            float(np.max(np.abs(actual[finite] - reference[finite])))
            if finite.any() else 0.0
        )
        native_ms = median_wall_ms(native_kernel, iterations)
        result.update({
            "rust_median_ms": native_ms,
            "speedup": result["python_median_ms"] / native_ms if native_ms else None,
            "max_abs_error_mm": largest_error,
            "parity": "pass",
        })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[64, 128])
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument(
        "--scenes", choices=["smooth", "holes", "ridge"],
        nargs="+", default=["smooth", "holes", "ridge"],
    )
    parser.add_argument(
        "--profiles", choices=["flat", "ball"],
        nargs="+", default=["flat", "ball"],
    )
    parser.add_argument("--require-rust", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if any(size < 4 for size in args.sizes) or args.iterations < 1:
        parser.error("Grid sizes must be >= 4; iterations must be positive.")
    available = native_available()
    if args.require_rust and not available:
        parser.error("Rust extension is unavailable; build with maturin first.")
    previous = os.environ.get("CARVEFOUNDRY_CAM_BACKEND")
    os.environ["CARVEFOUNDRY_CAM_BACKEND"] = "rust" if available else "python"
    try:
        results = [
            benchmark(
                size, args.iterations, scene=scene,
                profile=profile, rust=available,
            )
            for scene in args.scenes
            for profile in args.profiles
            for size in args.sizes
        ]
    finally:
        if previous is None:
            os.environ.pop("CARVEFOUNDRY_CAM_BACKEND", None)
        else:
            os.environ["CARVEFOUNDRY_CAM_BACKEND"] = previous
    report = {
        "kernel": "compensate_height_field",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "rust_available": available,
        "iterations": args.iterations,
        "results": results,
        "note": "Synthetic grids; timings include allocation and Python/Rust boundary overhead.",
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
