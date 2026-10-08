"""Reproducible Python/Rust raster-kernel parity and wall-time baseline.

Run after installing CarveFoundry with its Maturin native extension. This
compares one deterministic mesh on increasing XY sample grids. No machine
code is emitted; results are advisory, not CNC validation.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

from carvefoundry.cam.heightfield import _rasterize_top_surface_python
from carvefoundry.cam.native import native_available, rasterize_top_surface


def _fixture(size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if size < 2:
        raise ValueError("Grid size must be at least two.")
    vertices = np.array([
        [0.0, 0.0, 0.0], [10.0, 0.0, 1.0],
        [10.0, 10.0, 4.0], [0.0, 10.0, 2.0],
    ], dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    axis = np.linspace(0.0, 10.0, size, dtype=np.float64)
    return vertices, faces, axis, axis.copy()


def _sample(fn, iterations: int) -> float:
    fn()  # warm up allocations, imports and dispatch outside measurement
    durations = []
    for _ in range(iterations):
        start = perf_counter()
        fn()
        durations.append((perf_counter() - start) * 1000.0)
    return statistics.median(durations)


def benchmark(size: int, iterations: int, *, rust: bool) -> dict:
    vertices, faces, x_axis, y_axis = _fixture(size)
    def python_fn():
        return _rasterize_top_surface_python(vertices, faces, x_axis, y_axis)
    py_result = python_fn()
    output = {
        "grid": size,
        "cells": size * size,
        "python_median_ms": _sample(python_fn, iterations),
        "rust_median_ms": None,
        "speedup": None,
        "max_abs_error_mm": None,
        "parity": None,
    }
    if rust:
        def rust_fn():
            return rasterize_top_surface(vertices, faces, x_axis, y_axis)
        native_result = rust_fn()
        if native_result is None:
            raise RuntimeError("Native kernel returned no result.")
        # Compare *all* cells, including missing values and exposed edges.
        np.testing.assert_allclose(
            native_result, py_result, rtol=1e-8, atol=1e-9,
            equal_nan=True,
        )
        finite = np.isfinite(py_result) & np.isfinite(native_result)
        max_error = (
            float(np.max(np.abs(native_result[finite] - py_result[finite])))
            if finite.any() else 0.0
        )
        rust_ms = _sample(rust_fn, iterations)
        output.update({
            "rust_median_ms": rust_ms,
            "speedup": output["python_median_ms"] / rust_ms if rust_ms else None,
            "max_abs_error_mm": max_error,
            "parity": "pass",
        })
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[64, 128, 256])
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--require-rust", action="store_true")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.iterations < 1 or any(size < 2 for size in args.sizes):
        parser.error("Iterations must be positive and grid sizes at least two.")
    available = native_available()
    if args.require_rust and not available:
        parser.error("Compiled Rust extension is unavailable; install with maturin first.")
    # Bypass an arbitrary user backend override so these runs explicitly
    # compare the selected implementations.
    original = os.environ.get("CARVEFOUNDRY_CAM_BACKEND")
    os.environ["CARVEFOUNDRY_CAM_BACKEND"] = "rust" if available else "python"
    try:
        results = [
            benchmark(size, args.iterations, rust=available)
            for size in args.sizes
        ]
    finally:
        if original is None:
            os.environ.pop("CARVEFOUNDRY_CAM_BACKEND", None)
        else:
            os.environ["CARVEFOUNDRY_CAM_BACKEND"] = original
    report = {
        "kernel": "rasterize_top_surface",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "rust_available": available,
        "iterations": args.iterations,
        "results": results,
        "note": "Measured wall times include Python/Rust boundary overhead; machine-dependent.",
    }
    formatted = json.dumps(report, indent=2)
    print(formatted)
    if args.json:
        args.json.write_text(formatted + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
