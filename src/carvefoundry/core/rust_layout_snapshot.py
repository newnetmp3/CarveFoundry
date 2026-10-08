"""Read-only, loss-aware CF3D -> Rust Studio 2D layout JSON adapter.

This module intentionally exports ONLY planarly placed, closed retained
vectors. It never modifies CF3D, CAM operations, fixtures, or NC programs.
The resulting layout is a new document; editing it cannot mutate the source.
"""
from __future__ import annotations

import argparse
import json
import sys
from math import isfinite
from pathlib import Path

import numpy as np

from .project import Project
from .project_file import load_project
from .vector_path import sampled_world_points

MAX_PARTS = 512
MAX_SAMPLED_POINTS = 1024


def project_to_layout_snapshot(project: Project) -> dict:
    """Create a lossy, read-only planar-vector design snapshot for Rust Studio."""
    if project.stock.xy_zero != "bottom_left":
        raise ValueError("Rust Studio requires stock-bottom-left XY0.")
    if not all(
        isfinite(value) and value > 0 and value <= 100_000
        for value in (project.stock.width_mm, project.stock.height_mm)
    ):
        raise ValueError("Project stock dimensions must be finite and positive.")
    items: list[dict] = []
    skipped = 0
    for index, item in enumerate(project.items):
        if not item.visible or item.vector_path is None or item.mesh is None:
            skipped += 1
            continue
        if not item.vector_path.closed or item.source_units.value != "mm":
            skipped += 1
            continue
        if any(abs(float(value)) > 1e-7 for value in item.transform.rotation_deg[:2]):
            skipped += 1
            continue
        try:
            sampled = np.asarray(
                sampled_world_points(item, tolerance_mm=0.25),
                dtype=np.float64,
            )
        except (ValueError, IndexError, TypeError):
            skipped += 1
            continue
        if sampled.ndim != 2 or sampled.shape[1] < 2:
            skipped += 1
            continue
        points = sampled[:, :2]
        if len(points) > 3 and np.allclose(points[0], points[-1], atol=1e-8):
            points = points[:-1]
        if (
            not 3 <= len(points) <= MAX_SAMPLED_POINTS
            or not np.isfinite(points).all()
        ):
            skipped += 1
            continue
        origin = points.min(axis=0)
        local = points - origin
        area_twice = float(
            np.dot(local[:, 0], np.roll(local[:, 1], -1))
            - np.dot(local[:, 1], np.roll(local[:, 0], -1))
        )
        if abs(area_twice) <= 1e-8:
            skipped += 1
            continue
        if len(items) >= MAX_PARTS:
            raise ValueError("Rust Studio snapshot exceeds the 512-part limit.")
        items.append({
            "id": index + 1,
            "name": item.name[:256],
            "outline": local.tolist(),
            "x": float(origin[0]),
            "y": float(origin[1]),
            "quarter_turns": 0,
        })
    return {
        "format_version": 1,
        "name": f"{project.name} (read-only vector snapshot)",
        "width_mm": float(project.stock.width_mm),
        "height_mm": float(project.stock.height_mm),
        "parts": items,
        "skipped_items": skipped,
        "source_was_read_only": True,
        "excluded_cam_and_fixtures": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cf3d", type=Path, help="Existing CF3D project to inspect only")
    args = parser.parse_args(argv)
    try:
        if args.cf3d.suffix.lower() != ".cf3d":
            raise ValueError("Input must be a CF3D project.")
        source = load_project(args.cf3d)
        snapshot = project_to_layout_snapshot(source)
    except (ValueError, OSError, TypeError) as exc:
        print(f"CF3D snapshot rejected: {exc}", file=sys.stderr)
        return 2
    json.dump(snapshot, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
