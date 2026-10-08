"""Single-load, read-only CF3D project session for the Rust desktop.

The authoritative Python engine reads a native project only once. The UI
receives a consistent, fingerprinted and loss-aware preview of its layout,
CAM readiness, stock, fixtures and object inventory. It receives NO cutter
motion, controller connection, G-code or preflight authorization.
"""
from __future__ import annotations

import argparse
import json
import sys
from math import isfinite
from pathlib import Path

from .project_file import load_project
from .rust_cam_readout import cam_readout_from_project
from .rust_layout_snapshot import project_to_layout_snapshot
from .rust_project_transaction import _file_sha256

SESSION_VERSION = 1
MAX_ITEMS = 10_000
MAX_FIXTURES = 2_048
MAX_OUTPUT_BYTES = 8_000_000


def read_project_session(path: Path) -> dict:
    """Inspect one consistent version of an existing CF3D without modifying it."""
    if path.suffix.lower() != ".cf3d":
        raise ValueError("Native project session accepts .cf3d files only.")
    source_hash = _file_sha256(path)
    project = load_project(path)
    if len(project.items) > MAX_ITEMS or len(project.fixtures) > MAX_FIXTURES:
        raise ValueError("Project exceeds native UI inventory limits.")
    stock = project.stock
    if stock.xy_zero != "bottom_left":
        raise ValueError("Rust workspace requires stock bottom-left XY0.")
    if not all(
        isfinite(v) and v > 0 and v <= 100_000
        for v in (stock.width_mm, stock.height_mm, stock.thickness_mm)
    ):
        raise ValueError("Stock dimensions/thickness are invalid for native inspection.")

    snapshot = project_to_layout_snapshot(project)
    snapshot["source_sha256"] = source_hash
    cam = cam_readout_from_project(project, source_hash)
    fixtures = []
    for fixture in project.fixtures:
        fixture.validate()
        fixtures.append({
            "name": fixture.name,
            "x_min_mm": fixture.x_min_mm,
            "y_min_mm": fixture.y_min_mm,
            "x_max_mm": fixture.x_max_mm,
            "y_max_mm": fixture.y_max_mm,
            "top_z_mm": fixture.top_z_mm,
            "clearance_mm": fixture.clearance_mm,
        })
    items = []
    for item in project.items:
        if not isinstance(item.item_id, str) or not item.item_id:
            raise ValueError("Project contains an invalid persistent item UUID.")
        items.append({
            "item_id": item.item_id,
            "name": item.name[:256],
            "kind": item.kind[:128],
            "visible": item.visible,
            "locked": item.locked,
            "has_mesh": item.mesh is not None,
            "has_vector": item.vector_path is not None,
        })
    if len({item["item_id"] for item in items}) != len(items):
        raise ValueError("Project item UUIDs are not unique.")
    session = {
        "session_version": SESSION_VERSION,
        "source_sha256": source_hash,
        "source_was_read_only": True,
        "export_allowed_from_rust": False,
        "preflight_verified": False,
        "stock": {
            "width_mm": stock.width_mm,
            "height_mm": stock.height_mm,
            "thickness_mm": stock.thickness_mm,
            "xy_zero": stock.xy_zero,
        },
        "layout": snapshot,
        "cam": cam,
        "fixtures": fixtures,
        "items": items,
        "material_name": project.material_name[:256],
    }
    if _file_sha256(path) != source_hash:
        raise ValueError("Source CF3D changed during project inspection; reload.")
    rendered = json.dumps(session, allow_nan=False, ensure_ascii=False)
    if len(rendered.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError("CF3D session exceeds the 8 MB inspection output limit.")
    return session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args(argv)
    try:
        report = read_project_session(args.source)
    except (OSError, ValueError, TypeError) as exc:
        print(f"CF3D native session rejected: {exc}", file=sys.stderr)
        return 2
    json.dump(report, sys.stdout, ensure_ascii=False, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
