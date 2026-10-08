"""Fail-closed CF3D placement transactions for the experimental Rust interface.

No mutation is performed on the source CF3D. Transactions require a SHA-256
precondition, stable persisted item UUIDs, fully validated XY deltas, and a
different previously nonexistent output path. After any edit, *all* generated
toolpaths are discarded and *all* saved CAM intents are marked stale.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from hashlib import sha256
from math import isfinite
from pathlib import Path
from uuid import uuid4

from .project_file import load_project, save_project
from .units import ModelUnits

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1_048_576
MAX_EDITS = 512
STALE_REASON = (
    "External Rust vector placement edit: regenerate every toolpath "
    "and repeat fixture-aware preflight."
)


class ProjectTransactionError(ValueError):
    """The request cannot be safely applied to a native CNC project."""


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_project(path: Path) -> dict:
    """Publish only the supported editable surface and a source precondition."""
    if path.suffix.lower() != ".cf3d":
        raise ProjectTransactionError("Only .cf3d project files are supported.")
    source_hash = _file_sha256(path)
    project = load_project(path)
    editable = [
        {
            "item_id": item.item_id,
            "name": item.name,
            "translation_mm": list(item.transform.translation_mm),
        }
        for item in project.items
        if item.vector_path is not None
        and item.mesh is not None
        and item.visible and not item.locked
        and item.source_units == ModelUnits.MILLIMETERS
        and not item.smart_bindings
    ]
    if _file_sha256(path) != source_hash:
        raise ProjectTransactionError("Project changed during inspection.")
    return {
        "protocol_version": PROTOCOL_VERSION,
        "source_sha256": source_hash,
        "editable_items": editable,
        "cam_operations": len(project.cam_operations),
        "toolpaths": len(project.toolpaths),
        "fixtures": len(project.fixtures),
        "commit_policy": "new-file-only; all generated toolpaths invalidated",
    }


def _parse_edits(request: object) -> tuple[str, list[tuple[str, float, float]]]:
    if not isinstance(request, dict) or set(request) != {
        "protocol_version", "source_sha256", "edits",
    }:
        raise ProjectTransactionError("Invalid placement transaction envelope.")
    if request["protocol_version"] != PROTOCOL_VERSION or isinstance(
        request["protocol_version"], bool
    ):
        raise ProjectTransactionError("Unsupported placement protocol version.")
    expected = request["source_sha256"]
    if not isinstance(expected, str) or len(expected) != 64 or any(
        character not in "0123456789abcdef" for character in expected
    ):
        raise ProjectTransactionError("Expected project SHA-256 is invalid.")
    raw_edits = request["edits"]
    if not isinstance(raw_edits, list) or not 1 <= len(raw_edits) <= MAX_EDITS:
        raise ProjectTransactionError("A transaction requires 1–512 item edits.")
    edits: list[tuple[str, float, float]] = []
    seen: set[str] = set()
    for raw in raw_edits:
        if not isinstance(raw, dict) or set(raw) != {
            "item_id", "delta_x_mm", "delta_y_mm",
        }:
            raise ProjectTransactionError("Unknown or missing placement edit fields.")
        item_id = raw["item_id"]
        if not isinstance(item_id, str) or not item_id or item_id in seen:
            raise ProjectTransactionError("Item IDs must be unique and nonempty.")
        seen.add(item_id)
        values = (raw["delta_x_mm"], raw["delta_y_mm"])
        if any(
            isinstance(value, bool) or not isinstance(value, (float, int))
            or not isfinite(value) or abs(value) > 100_000
            for value in values
        ):
            raise ProjectTransactionError(
                "Placement offsets must be finite numbers within ±100,000 mm."
            )
        dx, dy = (float(value) for value in values)
        if dx == 0.0 and dy == 0.0:
            raise ProjectTransactionError("No-op item placements are not transactions.")
        edits.append((item_id, dx, dy))
    return expected, edits


def apply_transaction(
    source: Path, output: Path, request: object,
) -> dict:
    """Apply a checked edit to a new native project, or leave both untouched."""
    source = source.expanduser().resolve(strict=True)
    output = output.expanduser().absolute()
    if source.suffix.lower() != ".cf3d" or output.suffix.lower() != ".cf3d":
        raise ProjectTransactionError("Input and output must be .cf3d paths.")
    if source == output.resolve():
        raise ProjectTransactionError("Cannot replace the original CNC project.")
    if output.exists() or output.is_symlink():
        raise ProjectTransactionError("Output exists; refusing to overwrite it.")
    expected, edits = _parse_edits(request)
    if _file_sha256(source) != expected:
        raise ProjectTransactionError(
            "Source project changed since Rust inspection; reload before editing."
        )
    project = load_project(source)
    by_id = {item.item_id: item for item in project.items}
    if len(by_id) != len(project.items):
        raise ProjectTransactionError("Source project contains duplicated item UUIDs.")
    for item_id, dx, dy in edits:
        item = by_id.get(item_id)
        if item is None:
            raise ProjectTransactionError(f"Unknown project item UUID: {item_id}")
        if (
            item.locked or not item.visible
            or item.vector_path is None or item.mesh is None
            or item.source_units != ModelUnits.MILLIMETERS
            or item.smart_bindings
        ):
            raise ProjectTransactionError(
                f"Item {item.name!r} is not an editable retained vector."
            )
        tx, ty, tz = item.transform.translation_mm
        next_translation = (tx + dx, ty + dy, tz)
        if not all(isfinite(value) for value in next_translation):
            raise ProjectTransactionError("Resulting placement is not finite.")
        item.transform.translation_mm = next_translation
        item.transform.validate()

    # The engine's own typed operation objects retain their cutter, UUID,
    # source associations and parameters, but are NEVER left ready.
    old_motion_count = len(project.toolpaths)
    project.toolpaths.clear()
    for operation in project.cam_operations:
        operation.mark_stale(STALE_REASON)

    # Recheck the source just before publishing. A race at the final instant
    # is still possible; callers must avoid concurrent editing of this file.
    if _file_sha256(source) != expected:
        raise ProjectTransactionError("Source project changed during the transaction.")
    if not output.parent.is_dir():
        raise ProjectTransactionError("Output directory must already exist.")
    staging = output.parent / f".{output.stem}-{uuid4().hex}.cf3d"
    try:
        save_project(project, staging)
        # Hardlink publishing is atomic, same filesystem and fails exclusively
        # if an unrelated output file appears before completion.
        os.link(staging, output)
    except FileExistsError as exc:
        raise ProjectTransactionError(
            "Output file already exists; refusing to overwrite it."
        ) from exc
    finally:
        staging.unlink(missing_ok=True)

    return {
        "protocol_version": PROTOCOL_VERSION,
        "source_sha256": expected,
        "output_cf3d": str(output),
        "output_sha256": _file_sha256(output),
        "edited_item_ids": [entry[0] for entry in edits],
        "removed_generated_toolpaths": old_motion_count,
        "stale_cam_operations": len(project.cam_operations),
        "requires_cam_regeneration_and_preflight": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "apply"))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.action == "inspect":
            if args.output is not None:
                raise ProjectTransactionError("Inspect takes only one project file.")
            report = inspect_project(args.source)
        else:
            if args.output is None:
                raise ProjectTransactionError("Apply requires a new output CF3D path.")
            payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
            if len(payload) > MAX_REQUEST_BYTES:
                raise ProjectTransactionError("Transaction request is too large.")
            request = json.loads(payload)
            report = apply_transaction(args.source, args.output, request)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"CF3D transaction rejected: {exc}", file=sys.stderr)
        return 2
    json.dump(report, sys.stdout, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
