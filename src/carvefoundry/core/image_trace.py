"""Image-to-mask helpers shared by full-resolution tracing and thumbnail preview.

The trace resolution is a percentage of the ORIGINAL image, not an arbitrary
hard-coded maximum. Pixel thresholding is vectorized to avoid a Python loop
per pixel on photographic inputs.
"""
from __future__ import annotations

import numpy as np


def trace_dimensions(width: int, height: int, percent: int) -> tuple[int, int]:
    """Preserve source aspect ratio and never upsample beyond its dimensions."""
    if width < 1 or height < 1:
        raise ValueError("The source image has no pixels.")
    if not 1 <= percent <= 100:
        raise ValueError("Trace resolution must be 1–100% of the source image.")
    return (
        max(1, min(width, round(width * percent / 100))),
        max(1, min(height, round(height * percent / 100))),
    )


def trace_mask(
    rgba: np.ndarray,
    *,
    threshold: int = 150,
    invert: bool = False,
) -> np.ndarray:
    """Return True for pixels to be carved; fully transparent pixels stay empty.

    RGBA is kept in channel order by QImage.Format_RGBA8888 on every supported
    host endianness; no QColor/Python nested pixel loops are needed.
    """
    image = np.asarray(rgba, dtype=np.uint8)
    if image.ndim != 3 or image.shape[2] != 4 or not image.size:
        raise ValueError("Trace pixels must be a nonempty H×W×4 RGBA array.")
    if not 0 <= threshold <= 255:
        raise ValueError("Darkness threshold must be between 0 and 255.")
    opaque = image[:, :, 3] > 16
    # Match the previous QColor trace's weighted luminance and threshold
    # behavior, including inversion only among nontransparent pixels.
    luminance = (
        0.2126 * image[:, :, 0].astype(np.float32)
        + 0.7152 * image[:, :, 1].astype(np.float32)
        + 0.0722 * image[:, :, 2].astype(np.float32)
    )
    dark = luminance <= threshold
    return opaque & (~dark if invert else dark)


def count_mask_runs(mask: np.ndarray) -> int:
    """Count compact scanline rectangles needed by bitmap_runs_mesh."""
    image = np.asarray(mask, dtype=bool)
    if image.ndim != 2 or not image.size:
        return 0
    # One rectangle begins at each active pixel whose left neighbor is empty.
    return int(np.count_nonzero(image[:, :1])) + int(
        np.count_nonzero(image[:, 1:] & ~image[:, :-1])
    )
