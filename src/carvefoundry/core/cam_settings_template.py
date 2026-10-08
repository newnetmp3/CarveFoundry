"""Versioned CAM settings templates, applied only through the trusted CF3D engine.

Templates transfer *parameters* to an existing matching machining operation,
not generated toolpaths or new cutter selection. Exact strategy, cutter
geometry and parameter schema must match. Application produces a NEW .cf3d
project, marks ALL machining stages stale and removes ALL saved cutter motion.
The original project remains unchanged and requires fresh CNC preflight.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from math import isfinite
from pathlib import Path
from uuid import uuid4

from carvefoundry.cam.operation import CamOperation

from .project_file import load_project, save_project
from .rust_project_transaction import _file_sha256

TEMPLATE_VERSION = 1
MAX_TEMPLATE_BYTES = 65_536
STALE_REASON = (
    "Machining settings template applied externally: regenerate all stages "
    "and repeat fixture-aware CNC preflight."
)


class TemplateError(ValueError):
    """The reusable machining settings cannot be safely exported or applied."""


def _sha_guard(source: Path, expected: str) -> None:
    if (not isinstance(expected, str) or len(expected) != 64
            or any(ch not in "0123456789abcdef" for ch in expected)):
        raise TemplateError("Expected source SHA-256 must be lowercase hexadecimal.")
    if _file_sha256(source) != expected:
        raise TemplateError("Original CF3D changed; inspect it again before continuing.")


def _op(project, operation_id: str) -> CamOperation:
    matches = [
        op for op in project.cam_operations if op.operation_id == operation_id
    ]
    if len(matches) != 1:
        raise TemplateError("Target machining operation UUID was not found or is duplicated.")
    return matches[0]


def _cutter_dict(operation: CamOperation) -> dict:
    # ToolType is a StrEnum; JSON serialization converts tuples to arrays.
    return json.loads(json.dumps(asdict(operation.cutter), allow_nan=False))


def _validate_parameters(parameters: object) -> dict:
    if not isinstance(parameters, dict) or len(parameters) > 256:
        raise TemplateError("Template needs a bounded parameter object.")
    validated = {}
    for name, value in parameters.items():
        if not isinstance(name, str) or not name or len(name) > 128:
            raise TemplateError("Template parameter keys must be short nonempty strings.")
        if value is not None and type(value) not in {bool, int, float, str}:
            raise TemplateError(f"Unsupported parameter type: {name}")
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            if abs(value) > 100_000 or not isfinite(value):
                raise TemplateError(f"Parameter {name} is nonfinite or exceeds bounds.")
        if isinstance(value, str) and len(value) > 2048:
            raise TemplateError(f"Text parameter {name} is too long.")
        validated[name] = value
    return validated


def _load_template(path: Path) -> dict:
    if path.suffix.lower() != ".json":
        raise TemplateError("Template source must be a JSON file.")
    if path.stat().st_size > MAX_TEMPLATE_BYTES:
        raise TemplateError("Template exceeds the 64 KiB size limit.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {
        "template_format_version", "name", "strategy", "cutter", "parameters",
    }:
        raise TemplateError("Unsupported CAM template format or extra fields.")
    if type(data["template_format_version"]) is not int or data["template_format_version"] != TEMPLATE_VERSION:
        raise TemplateError("Unsupported CAM template version.")
    if not isinstance(data["name"], str) or not 1 <= len(data["name"]) <= 128:
        raise TemplateError("Template name must have 1–128 characters.")
    if not isinstance(data["strategy"], str) or not data["strategy"]:
        raise TemplateError("Template strategy must be nonempty.")
    if not isinstance(data["cutter"], dict):
        raise TemplateError("Template cutter signature must be an object.")
    data["parameters"] = _validate_parameters(data["parameters"])
    return data


def export_template(
    source: Path, operation_id: str, template_file: Path, expected_sha256: str,
) -> dict:
    if source.suffix.lower() != ".cf3d" or template_file.suffix.lower() != ".json":
        raise TemplateError("Requires a CF3D source and a new JSON template filename.")
    _sha_guard(source, expected_sha256)
    operation = _op(load_project(source), operation_id)
    template = {
        "template_format_version": TEMPLATE_VERSION,
        "name": f"{operation.operation} · {operation.cutter.name}"[:128],
        "strategy": operation.operation,
        "cutter": _cutter_dict(operation),
        "parameters": _validate_parameters(operation.parameters),
    }
    rendered = json.dumps(template, indent=2, allow_nan=False) + "\n"
    if len(rendered.encode("utf-8")) > MAX_TEMPLATE_BYTES:
        raise TemplateError("Export template exceeds size limit.")
    _sha_guard(source, expected_sha256)
    try:
        with template_file.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    except FileExistsError as exc:
        raise TemplateError("Template output exists; refusing to overwrite.") from exc
    return {"template_file": str(template_file), "strategy": operation.operation,
            "parameters": len(template["parameters"]), "is_gcode": False}


def apply_template(
    source: Path, operation_id: str, template_file: Path,
    output: Path, expected_sha256: str,
) -> dict:
    if source.suffix.lower() != ".cf3d" or output.suffix.lower() != ".cf3d":
        raise TemplateError("Template application requires native CF3D source/output.")
    source = source.expanduser().resolve(strict=True)
    output = output.expanduser().absolute()
    if output.resolve() == source or output.exists() or output.is_symlink():
        raise TemplateError("Output must be a different, nonexistent CF3D file.")
    if not output.parent.is_dir():
        raise TemplateError("Output directory must already exist.")
    _sha_guard(source, expected_sha256)
    template = _load_template(template_file)
    project = load_project(source)
    operation = _op(project, operation_id)
    if not operation.enabled:
        raise TemplateError("Enable the target operation in verified CAM before applying a template.")
    if operation.operation != template["strategy"]:
        raise TemplateError("Operation strategy does not match the template.")
    if _cutter_dict(operation) != template["cutter"]:
        raise TemplateError("Cutter geometry differs; select a compatible tool in verified CAM.")
    current = _validate_parameters(operation.parameters)
    proposed = template["parameters"]
    if current.keys() != proposed.keys() or any(
        type(current[key]) is not type(proposed[key]) for key in current
    ):
        raise TemplateError("Parameter keys/types differ; choose an operation with the same settings schema.")

    # Existing CAM generation code remains the authority for all parameter
    # semantics; validate dataclass syntax before accepting changes.
    CamOperation(
        operation=operation.operation, cutter=operation.cutter,
        source_item_ids=operation.source_item_ids,
        parameters=proposed, operation_id=operation.operation_id,
        enabled=operation.enabled, stale_reason=STALE_REASON,
    )
    operation.parameters = dict(proposed)
    old_motion = len(project.toolpaths)
    project.toolpaths.clear()
    for stage in project.cam_operations:
        stage.mark_stale(STALE_REASON)
    _sha_guard(source, expected_sha256)

    staging = output.parent / f".{output.stem}-{uuid4().hex}.cf3d"
    try:
        save_project(project, staging)
        _sha_guard(source, expected_sha256)
        os.link(staging, output)  # atomic same-filesystem exclusive publication
    except FileExistsError as exc:
        raise TemplateError("Output was created by another process; refusing overwrite.") from exc
    finally:
        staging.unlink(missing_ok=True)
    return {
        "template_applied": True, "new_project": str(output),
        "modified_operation_id": operation_id,
        "invalidated_generated_toolpaths": old_motion,
        "stale_cam_operations": len(project.cam_operations),
        "requires_regeneration_and_preflight": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "apply"))
    parser.add_argument("source", type=Path)
    parser.add_argument("operation_id")
    parser.add_argument("template_file", type=Path)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "export":
            if args.output is not None:
                raise TemplateError("Export does not accept a CF3D output path.")
            result = export_template(
                args.source, args.operation_id, args.template_file, args.expected_sha
            )
        else:
            if args.output is None:
                raise TemplateError("Applying a template requires --output NEW.cf3d.")
            result = apply_template(
                args.source, args.operation_id, args.template_file,
                args.output, args.expected_sha,
            )
    except (OSError, ValueError, TypeError) as exc:
        print(f"CAM settings template rejected: {exc}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
