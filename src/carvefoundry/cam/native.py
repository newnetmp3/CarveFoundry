from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Final

import numpy as np

from carvefoundry.core.tools import Cutter

try:
    from carvefoundry import _native as _rust
except ImportError as exc:  # pragma: no cover - source-only fallback.
    _rust = None
    _IMPORT_ERROR: ImportError | None = exc
else:
    _IMPORT_ERROR = None

_BACKEND_ENV: Final = "CARVEFOUNDRY_CAM_BACKEND"
_AUTO_VALUES: Final = {"", "auto"}
_RUST_VALUES: Final = {"rust", "native"}
_PYTHON_VALUES: Final = {"python", "py"}


def native_available() -> bool:
    """Return whether the compiled PyO3 CAM extension imported successfully."""

    return _rust is not None


def backend_name() -> str:
    """Return the CAM kernel backend selected for this process.

    The default is auto: prefer Rust when the extension is installed and fall
    back to the readable Python reference implementation otherwise. The
    CARVEFOUNDRY_CAM_BACKEND environment variable can force rust or python.
    """

    requested = os.environ.get(_BACKEND_ENV, "auto").strip().lower()
    if requested in _PYTHON_VALUES:
        return "python"
    if requested in _AUTO_VALUES:
        return "rust" if native_available() else "python"
    if requested in _RUST_VALUES:
        if not native_available():
            detail = f": {_IMPORT_ERROR}" if _IMPORT_ERROR is not None else ""
            raise RuntimeError(f"Rust CAM backend was requested but is unavailable{detail}")
        return "rust"
    raise ValueError(
        f"Unsupported {_BACKEND_ENV} value {requested!r}; use auto, rust, or python."
    )


def rasterize_top_surface(
    vertices: np.ndarray,
    faces: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
) -> np.ndarray | None:
    """Run the native mesh-to-height-field kernel when Rust is selected."""

    if backend_name() != "rust":
        return None
    assert _rust is not None
    return np.asarray(
        _rust.rasterize_top_surface(vertices, faces, x_axis, y_axis),
        dtype=float,
    )


def compensate_height_field(
    source_z: np.ndarray,
    footprint: Sequence[tuple[int, int, float]],
) -> np.ndarray | None:
    """Run the native cutter-contact kernel when Rust is selected."""

    if backend_name() != "rust":
        return None
    assert _rust is not None
    return np.asarray(
        _rust.compensate_height_field(source_z, list(footprint)),
        dtype=float,
    )



def sweep_stock_segment(
    surface: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    cutter: Cutter,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    samples: int,
    stock_bottom: float,
) -> int | None:
    """Update sampled stock in place using the native cutter-sweep kernel.

    Returns None for the Python reference backend, otherwise the number
    of cell updates (counting repeated cuts of the same cell).
    """
    if backend_name() != "rust":
        return None
    assert _rust is not None
    return int(_rust.sweep_stock_segment(
        surface, x_axis, y_axis, start, end, samples, stock_bottom,
        cutter.tool_type.value, cutter.diameter_mm,
        float(cutter.angle_deg or 0), cutter.tip_diameter_mm,
        float(cutter.taper_angle_deg or 0), float(cutter.ball_radius_mm or 0),
        list(cutter.profile_points or ()),
    ))
