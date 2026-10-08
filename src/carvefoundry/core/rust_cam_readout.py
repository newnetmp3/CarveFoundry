"""Read-only typed CAM inventory for the experimental Rust desktop.

This is *not* a CNC preflight certificate. Even apparently complete stored
toolpath motion must be regenerated/checked by the authoritative application.
No project edits, sender actions, or G-code are available through this adapter.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .project_file import load_project
from .rust_project_transaction import _file_sha256

PROTOCOL_VERSION = 1
MAX_OPERATIONS = 10_000


def cam_readout(path: Path) -> dict:
    if path.suffix.lower() != ".cf3d":
        raise ValueError("CAM inspector accepts native .cf3d projects only.")
    source_hash = _file_sha256(path)
    project = load_project(path)
    if len(project.cam_operations) > MAX_OPERATIONS:
        raise ValueError("CAM operation count exceeds inspection limit.")
    paths_by_operation: dict[str, int] = {}
    motion_by_operation: dict[str, int] = {}
    for toolpath in project.toolpaths:
        identifier = toolpath.cam_operation_id
        if identifier:
            paths_by_operation[identifier] = paths_by_operation.get(identifier, 0) + 1
            motion_by_operation[identifier] = (
                motion_by_operation.get(identifier, 0) + len(toolpath.moves)
            )

    summaries = []
    counts = {"disabled": 0, "stale": 0, "missing_motion": 0,
              "motion_present_unverified": 0}
    for operation in project.cam_operations:
        if not operation.enabled:
            state = "disabled"
        elif operation.needs_recalculation:
            state = "stale"
        elif motion_by_operation.get(operation.operation_id, 0) == 0:
            state = "missing_motion"
        else:
            state = "motion_present_unverified"
        counts[state] += 1
        summaries.append({
            "operation_id": operation.operation_id,
            "strategy": operation.operation,
            "cutter_name": operation.cutter.name,
            "cutter_type": operation.cutter.tool_type.value,
            "cutter_diameter_mm": operation.cutter.diameter_mm,
            "source_item_count": len(operation.source_item_ids),
            "generated_toolpath_count": paths_by_operation.get(operation.operation_id, 0),
            "motion_move_count": motion_by_operation.get(operation.operation_id, 0),
            "state": state,
            "stale_reason": operation.stale_reason,
        })
    if _file_sha256(path) != source_hash:
        raise ValueError("CF3D project changed during CAM readout; inspect again.")
    return {
        "protocol_version": PROTOCOL_VERSION,
        "source_sha256": source_hash,
        "project_name": project.name,
        "operation_count": len(summaries),
        "generated_toolpath_count": len(project.toolpaths),
        "fixture_count": len(project.fixtures),
        "counts": counts,
        "operations": summaries,
        "export_allowed_from_rust": False,
        "preflight_verified": False,
        "notice": "Read-only inspection. Existing CNC CAM must regenerate, preflight and export.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args(argv)
    try:
        report = cam_readout(args.source)
    except (OSError, ValueError, TypeError) as exc:
        print(f"CF3D CAM readout rejected: {exc}", file=sys.stderr)
        return 2
    json.dump(report, sys.stdout, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
