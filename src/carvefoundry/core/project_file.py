from __future__ import annotations

import hashlib
import json
import struct
import tempfile
from dataclasses import asdict
from math import isfinite, isnan
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

import zstandard as zstd

from carvefoundry.cam.operation import CamOperation
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove

from .fixtures import Fixture
from .mesh import MeshImportError, load_stl
from .project import Project, ProjectItem, Stock, TextProperties
from .smart_values import SmartValueError, SmartValues
from .tools import Cutter, ToolType
from .transform import Transform3D
from .units import ModelUnits
from .vector_path import VectorPath, VectorSegment

PROJECT_FILE_VERSION = 2
LEGACY_PROJECT_FILE_VERSION = 1
PROJECT_SUFFIX = ".cf3d"
PROJECT_FORMAT = "CarveFoundry Project"

PROJECT_FILE_MAGIC = b"CF3D\x1aZST"
CONTAINER_VERSION = 1
_HEADER = struct.Struct("<8sIIQQ")
_HEADER_FLAGS = 0
_MAX_MANIFEST_SIZE = 64 * 1024 * 1024
_MAX_TOOLPATHS = 10_000
_MAX_CAM_OPERATIONS = 10_000
_MAX_TOOLPATH_MOVES = 1_000_000
_TOOLPATH_MOVES_ENCODING = "cfmoves-f64-v1"
_TOOLPATH_MOVE_STRUCT = struct.Struct("<dddBd")
_MOVE_KIND_TO_CODE = {
    MoveKind.RAPID: 0,
    MoveKind.PLUNGE: 1,
    MoveKind.CUT: 2,
}
_MOVE_CODE_TO_KIND = {code: kind for kind, code in _MOVE_KIND_TO_CODE.items()}
_ASSET_ZSTD_LEVEL = 19
_MANIFEST_ZSTD_LEVEL = 12


class ProjectFileError(ValueError):
    """Raised when a CarveFoundry project file cannot be read or reconstructed."""


def _triple(value: object, *, field_name: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ProjectFileError(f"{field_name} must contain exactly three numbers.")
    try:
        result = tuple(float(component) for component in value)
    except (TypeError, ValueError) as exc:
        raise ProjectFileError(f"{field_name} must contain exactly three numbers.") from exc
    return result


def _transform_to_dict(transform: Transform3D) -> dict[str, list[float]]:
    return {
        "translation_mm": list(transform.translation_mm),
        "rotation_deg": list(transform.rotation_deg),
        "scale_xyz": list(transform.scale_xyz),
    }


def _stock_to_dict(stock: Stock) -> dict[str, object]:
    return {
        "width_mm": stock.width_mm,
        "height_mm": stock.height_mm,
        "thickness_mm": stock.thickness_mm,
        "xy_zero": stock.xy_zero,
    }


def _finite_float(value: object, *, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ProjectFileError(f"{field_name} must be a finite number.") from exc
    if not isfinite(result):
        raise ProjectFileError(f"{field_name} must be a finite number.")
    return result


def _optional_finite_float(
    value: object,
    *,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    return _finite_float(value, field_name=field_name)


def _cutter_to_dict(cutter: Cutter) -> dict[str, object]:
    return {
        "name": cutter.name,
        "tool_type": cutter.tool_type.value,
        "diameter_mm": cutter.diameter_mm,
        "angle_deg": cutter.angle_deg,
        "tip_diameter_mm": cutter.tip_diameter_mm,
        "taper_angle_deg": cutter.taper_angle_deg,
        "ball_radius_mm": cutter.ball_radius_mm,
        "profile_points": (
            [list(point) for point in cutter.profile_points]
            if cutter.profile_points is not None
            else None
        ),
    }


def _load_cutter(value: object, *, path_index: int) -> Cutter:
    if not isinstance(value, dict):
        raise ProjectFileError(
            f"Toolpath {path_index + 1} cutter must be an object."
        )
    name = value.get("name")
    if not isinstance(name, str) or not name:
        raise ProjectFileError(
            f"Toolpath {path_index + 1} cutter name is invalid."
        )
    try:
        tool_type = ToolType(value.get("tool_type"))
    except (TypeError, ValueError) as exc:
        raise ProjectFileError(
            f"Toolpath {path_index + 1} cutter type is invalid."
        ) from exc

    profile_value = value.get("profile_points")
    profile_points: tuple[tuple[float, float], ...] | None = None
    if profile_value is not None:
        if not isinstance(profile_value, list):
            raise ProjectFileError(
                f"Toolpath {path_index + 1} custom cutter profile is invalid."
            )
        parsed_points: list[tuple[float, float]] = []
        for point_index, point in enumerate(profile_value):
            if not isinstance(point, list) or len(point) != 2:
                raise ProjectFileError(
                    f"Toolpath {path_index + 1} cutter profile point "
                    f"{point_index + 1} is invalid."
                )
            parsed_points.append(
                (
                    _finite_float(
                        point[0],
                        field_name=(
                            f"Toolpath {path_index + 1} cutter profile radius"
                        ),
                    ),
                    _finite_float(
                        point[1],
                        field_name=(
                            f"Toolpath {path_index + 1} cutter profile height"
                        ),
                    ),
                )
            )
        profile_points = tuple(parsed_points)

    try:
        return Cutter(
            name=name,
            tool_type=tool_type,
            diameter_mm=_finite_float(
                value.get("diameter_mm"),
                field_name=f"Toolpath {path_index + 1} cutter diameter",
            ),
            angle_deg=_optional_finite_float(
                value.get("angle_deg"),
                field_name=f"Toolpath {path_index + 1} cutter angle",
            ),
            tip_diameter_mm=_finite_float(
                value.get("tip_diameter_mm", 0.0),
                field_name=f"Toolpath {path_index + 1} cutter tip diameter",
            ),
            taper_angle_deg=_optional_finite_float(
                value.get("taper_angle_deg"),
                field_name=f"Toolpath {path_index + 1} cutter taper angle",
            ),
            ball_radius_mm=_optional_finite_float(
                value.get("ball_radius_mm"),
                field_name=f"Toolpath {path_index + 1} cutter ball radius",
            ),
            profile_points=profile_points,
        )
    except ValueError as exc:
        raise ProjectFileError(
            f"Toolpath {path_index + 1} cutter is invalid: {exc}"
        ) from exc


def _encode_toolpath_moves(toolpath: Toolpath) -> bytes:
    data = bytearray(len(toolpath.moves) * _TOOLPATH_MOVE_STRUCT.size)
    for index, move in enumerate(toolpath.moves):
        feed = float("nan") if move.feed_mm_min is None else move.feed_mm_min
        _TOOLPATH_MOVE_STRUCT.pack_into(
            data,
            index * _TOOLPATH_MOVE_STRUCT.size,
            move.x_mm,
            move.y_mm,
            move.z_mm,
            _MOVE_KIND_TO_CODE[move.kind],
            feed,
        )
    return bytes(data)


def _decode_toolpath_moves(
    data: bytes,
    *,
    path_index: int,
    move_count: int,
) -> list[ToolpathMove]:
    expected_size = move_count * _TOOLPATH_MOVE_STRUCT.size
    if len(data) != expected_size:
        raise ProjectFileError(
            f"Toolpath {path_index + 1} motion payload size is invalid."
        )

    moves: list[ToolpathMove] = []
    for move_index in range(move_count):
        offset = move_index * _TOOLPATH_MOVE_STRUCT.size
        x_mm, y_mm, z_mm, kind_code, feed_value = _TOOLPATH_MOVE_STRUCT.unpack_from(
            data,
            offset,
        )
        kind = _MOVE_CODE_TO_KIND.get(kind_code)
        if kind is None:
            raise ProjectFileError(
                f"Toolpath {path_index + 1} move {move_index + 1} "
                "has an invalid move kind."
            )
        if isnan(feed_value):
            feed_mm_min = None
        elif not isfinite(feed_value):
            raise ProjectFileError(
                f"Toolpath {path_index + 1} move {move_index + 1} "
                "has an invalid feed."
            )
        else:
            feed_mm_min = feed_value
        try:
            moves.append(
                ToolpathMove(
                    x_mm=x_mm,
                    y_mm=y_mm,
                    z_mm=z_mm,
                    kind=kind,
                    feed_mm_min=feed_mm_min,
                )
            )
        except ValueError as exc:
            raise ProjectFileError(
                f"Toolpath {path_index + 1} move {move_index + 1} "
                f"is invalid: {exc}"
            ) from exc
    return moves


def _toolpath_to_dict(
    toolpath: Toolpath,
    *,
    moves_asset_id: str | None,
) -> dict[str, object]:
    return {
        "name": toolpath.name,
        "operation": toolpath.operation,
        "cutter": _cutter_to_dict(toolpath.cutter),
        "safe_z_mm": toolpath.safe_z_mm,
        "source_item_id": toolpath.source_item_id,
        "source_item_name": toolpath.source_item_name,
        "cam_operation_id": toolpath.cam_operation_id,
        "move_count": len(toolpath.moves),
        "moves_encoding": _TOOLPATH_MOVES_ENCODING,
        "moves_asset_id": moves_asset_id,
    }


def _cam_operation_to_dict(operation: CamOperation) -> dict[str, object]:
    return {
        "operation_id": operation.operation_id,
        "operation": operation.operation,
        "cutter": _cutter_to_dict(operation.cutter),
        "source_item_ids": list(operation.source_item_ids),
        "parameters": dict(operation.parameters),
        "enabled": operation.enabled,
        "stale_reason": operation.stale_reason,
    }


def _load_cam_operations(value: object) -> list[CamOperation]:
    if not isinstance(value, list):
        raise ProjectFileError("Project CAM operations section is invalid.")
    if len(value) > _MAX_CAM_OPERATIONS:
        raise ProjectFileError("Project contains too many CAM operations.")

    result: list[CamOperation] = []
    seen_ids: set[str] = set()
    for operation_index, raw_operation in enumerate(value):
        label = f"CAM operation {operation_index + 1}"
        if not isinstance(raw_operation, dict):
            raise ProjectFileError(f"{label} must be an object.")

        operation_id = raw_operation.get("operation_id")
        operation = raw_operation.get("operation")
        if not isinstance(operation_id, str) or not operation_id:
            raise ProjectFileError(f"{label} ID is invalid.")
        if operation_id in seen_ids:
            raise ProjectFileError(f"{label} ID is duplicated.")
        seen_ids.add(operation_id)
        if not isinstance(operation, str) or not operation:
            raise ProjectFileError(f"{label} type is invalid.")

        source_item_ids = raw_operation.get("source_item_ids", [])
        if not isinstance(source_item_ids, list) or not all(
            isinstance(item_id, str) and item_id
            for item_id in source_item_ids
        ):
            raise ProjectFileError(f"{label} source item IDs are invalid.")

        parameters = raw_operation.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ProjectFileError(f"{label} parameters are invalid.")
        parsed_parameters: dict[str, str | int | float | bool | None] = {}
        for key, parameter_value in parameters.items():
            if not isinstance(key, str) or not key:
                raise ProjectFileError(f"{label} parameter name is invalid.")
            if parameter_value is not None and not isinstance(
                parameter_value,
                (str, int, float, bool),
            ):
                raise ProjectFileError(
                    f"{label} parameter {key} has an unsupported value."
                )
            if isinstance(parameter_value, float) and not isfinite(parameter_value):
                raise ProjectFileError(
                    f"{label} parameter {key} must be finite."
                )
            parsed_parameters[key] = parameter_value

        enabled = raw_operation.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ProjectFileError(f"{label} enabled state is invalid.")

        stale_reason = raw_operation.get("stale_reason")
        if stale_reason is not None and (
            not isinstance(stale_reason, str) or not stale_reason.strip()
        ):
            raise ProjectFileError(f"{label} stale reason is invalid.")

        try:
            cutter = _load_cutter(
                raw_operation.get("cutter"),
                path_index=operation_index,
            )
            result.append(
                CamOperation(
                    operation=operation,
                    cutter=cutter,
                    source_item_ids=tuple(source_item_ids),
                    parameters=parsed_parameters,
                    operation_id=operation_id,
                    enabled=enabled,
                    stale_reason=stale_reason,
                )
            )
        except (ProjectFileError, ValueError) as exc:
            raise ProjectFileError(f"{label} is invalid: {exc}") from exc
    return result


def _optional_text(
    value: object,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProjectFileError(f"{field_name} must be a string or null.")
    return value


def _load_toolpaths(
    value: object,
    *,
    handle: BinaryIO,
    payload_start: int,
    container_size: int,
    assets: object,
) -> list[Toolpath]:
    if not isinstance(value, list):
        raise ProjectFileError("Project toolpaths section is invalid.")
    if len(value) > _MAX_TOOLPATHS:
        raise ProjectFileError("Project contains too many toolpaths.")

    result: list[Toolpath] = []
    total_moves = 0
    for path_index, raw_path in enumerate(value):
        if not isinstance(raw_path, dict):
            raise ProjectFileError(
                f"Toolpath {path_index + 1} must be an object."
            )
        name = raw_path.get("name")
        operation = raw_path.get("operation")
        if not isinstance(name, str) or not name:
            raise ProjectFileError(
                f"Toolpath {path_index + 1} name is invalid."
            )
        if not isinstance(operation, str) or not operation:
            raise ProjectFileError(
                f"Toolpath {path_index + 1} operation is invalid."
            )

        raw_move_count = raw_path.get("move_count", 0)
        if isinstance(raw_move_count, bool) or not isinstance(raw_move_count, int):
            raise ProjectFileError(
                f"Toolpath {path_index + 1} move count is invalid."
            )
        move_count = raw_move_count
        if move_count < 0:
            raise ProjectFileError(
                f"Toolpath {path_index + 1} move count is invalid."
            )
        total_moves += move_count
        if total_moves > _MAX_TOOLPATH_MOVES:
            raise ProjectFileError("Project contains too many toolpath moves.")

        encoding = raw_path.get("moves_encoding")
        if encoding != _TOOLPATH_MOVES_ENCODING:
            raise ProjectFileError(
                f"Toolpath {path_index + 1} motion encoding is unsupported."
            )
        asset_id = raw_path.get("moves_asset_id")
        if move_count == 0:
            if asset_id is not None:
                raise ProjectFileError(
                    f"Toolpath {path_index + 1} has an unexpected motion payload."
                )
            moves: list[ToolpathMove] = []
        else:
            if not isinstance(asset_id, str) or len(asset_id) != 64:
                raise ProjectFileError(
                    f"Toolpath {path_index + 1} motion payload id is invalid."
                )
            metadata = _asset_metadata(assets, asset_id)
            expected_size = move_count * _TOOLPATH_MOVE_STRUCT.size
            data = _read_asset_data(
                handle,
                payload_start=payload_start,
                container_size=container_size,
                asset_id=asset_id,
                metadata=metadata,
                expected_original_size=expected_size,
            )
            moves = _decode_toolpath_moves(
                data,
                path_index=path_index,
                move_count=move_count,
            )

        try:
            path = Toolpath(
                name=name,
                operation=operation,
                cutter=_load_cutter(raw_path.get("cutter"), path_index=path_index),
                safe_z_mm=_finite_float(
                    raw_path.get("safe_z_mm"),
                    field_name=f"Toolpath {path_index + 1} safe Z",
                ),
                moves=moves,
                source_item_id=_optional_text(
                    raw_path.get("source_item_id"),
                    field_name=f"Toolpath {path_index + 1} source item ID",
                ),
                source_item_name=_optional_text(
                    raw_path.get("source_item_name"),
                    field_name=f"Toolpath {path_index + 1} source item name",
                ),
                cam_operation_id=_optional_text(
                    raw_path.get("cam_operation_id"),
                    field_name=f"Toolpath {path_index + 1} CAM operation ID",
                ),
            )
        except ValueError as exc:
            raise ProjectFileError(
                f"Toolpath {path_index + 1} is invalid: {exc}"
            ) from exc
        result.append(path)
    return result


def _text_properties_to_dict(
    properties: TextProperties | None,
) -> dict[str, object] | None:
    if properties is None:
        return None
    return {
        "content": properties.content,
        "font_family": properties.font_family,
        "font_style": properties.font_style,
        "size_pt": properties.size_pt,
        "bold": properties.bold,
        "italic": properties.italic,
        "underline": properties.underline,
        "strikeout": properties.strikeout,
        "alignment": properties.alignment,
        "character_spacing_mm": properties.character_spacing_mm,
        "word_spacing_mm": properties.word_spacing_mm,
        "kerning": properties.kerning,
        "line_spacing_percent": properties.line_spacing_percent,
        "horizontal_scale_percent": properties.horizontal_scale_percent,
        "wrap_to_width": properties.wrap_to_width,
        "box_width_mm": properties.box_width_mm,
        "depth_mm": properties.depth_mm,
        "geometry_mode": properties.geometry_mode,
        "outline_width_mm": properties.outline_width_mm,
        "case_mode": properties.case_mode,
    }


def _load_text_properties(
    value: object,
    *,
    item_name: str,
) -> TextProperties | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProjectFileError(
            f"Project item {item_name!r} has invalid text properties."
        )
    try:
        properties = TextProperties(
            content=str(value.get("content", "Text")),
            font_family=str(value.get("font_family", "")),
            font_style=str(value.get("font_style", "Regular")),
            size_pt=float(value.get("size_pt", 36.0)),
            bold=bool(value.get("bold", False)),
            italic=bool(value.get("italic", False)),
            underline=bool(value.get("underline", False)),
            strikeout=bool(value.get("strikeout", False)),
            alignment=str(value.get("alignment", "left")),
            character_spacing_mm=float(
                value.get("character_spacing_mm", 0.0)
            ),
            word_spacing_mm=float(value.get("word_spacing_mm", 0.0)),
            kerning=bool(value.get("kerning", True)),
            line_spacing_percent=float(
                value.get("line_spacing_percent", 100.0)
            ),
            horizontal_scale_percent=float(
                value.get("horizontal_scale_percent", 100.0)
            ),
            wrap_to_width=bool(value.get("wrap_to_width", False)),
            box_width_mm=float(value.get("box_width_mm", 0.0)),
            depth_mm=float(value.get("depth_mm", 1.0)),
            geometry_mode=str(value.get("geometry_mode", "filled")),
            outline_width_mm=float(
                value.get("outline_width_mm", 0.8)
            ),
            case_mode=str(value.get("case_mode", "normal")),
        )
        properties.validate()
    except (TypeError, ValueError) as exc:
        raise ProjectFileError(
            f"Project item {item_name!r} has invalid text properties: {exc}"
        ) from exc
    return properties


def _safe_source_name(name: str, *, fallback: str) -> str:
    normalized = name.replace("\\", "/")
    basename = PurePosixPath(normalized).name.strip()
    if not basename or basename in {".", ".."}:
        return fallback
    return basename


def _mesh_bytes(item: ProjectItem) -> bytes:
    if item.mesh is None:
        raise ProjectFileError(f"Project item {item.name!r} has no mesh data to embed.")
    try:
        exported = item.mesh.mesh.export(file_type="stl")
    except Exception as exc:
        raise ProjectFileError(f"Could not serialize mesh {item.name!r}: {exc}") from exc
    if isinstance(exported, str):
        return exported.encode("utf-8")
    return bytes(exported)


def _asset_bytes_for_item(item: ProjectItem) -> tuple[bytes, str] | None:
    source_path = item.source_path
    if source_path is not None and source_path.is_file():
        try:
            return source_path.read_bytes(), source_path.name
        except OSError as exc:
            raise ProjectFileError(
                f"Could not read source asset for {item.name!r}: {exc}"
            ) from exc

    if item.mesh is not None:
        source_name = item.name
        if Path(source_name).suffix.lower() != ".stl":
            source_name = f"{Path(source_name).stem or 'mesh'}.stl"
        return _mesh_bytes(item), source_name

    if source_path is not None:
        raise ProjectFileError(
            f"Source asset for {item.name!r} is missing and cannot be embedded: "
            f"{source_path}"
        )

    return None


def _compress_zstd(data: bytes, *, level: int) -> bytes:
    compressor = zstd.ZstdCompressor(
        level=level,
        threads=-1,
        write_checksum=True,
        write_content_size=True,
    )
    return compressor.compress(data)


def _encode_asset(data: bytes) -> tuple[str, bytes]:
    compressed = _compress_zstd(data, level=_ASSET_ZSTD_LEVEL)
    if len(compressed) < len(data):
        return "zstd", compressed
    return "raw", data


def _store_payload_asset(
    assets: dict[str, dict[str, Any]],
    payloads: list[bytes],
    data: bytes,
    *,
    payload_offset: int,
    original_name: str,
) -> tuple[str, int]:
    asset_id = hashlib.sha256(data).hexdigest()
    if asset_id in assets:
        return asset_id, payload_offset

    codec, stored = _encode_asset(data)
    assets[asset_id] = {
        "offset": payload_offset,
        "stored_size": len(stored),
        "original_size": len(data),
        "codec": codec,
        "sha256": asset_id,
        "original_name": original_name,
    }
    payloads.append(stored)
    return asset_id, payload_offset + len(stored)


def _build_container(
    project: Project,
) -> tuple[dict[str, Any], list[bytes]]:
    assets: dict[str, dict[str, Any]] = {}
    payloads: list[bytes] = []
    items: list[dict[str, Any]] = []
    payload_offset = 0

    for item in project.items:
        asset = _asset_bytes_for_item(item)
        asset_id: str | None = None
        source_name: str | None = None

        if asset is not None:
            data, source_name = asset
            asset_id, payload_offset = _store_payload_asset(
                assets,
                payloads,
                data,
                payload_offset=payload_offset,
                original_name=source_name,
            )

        items.append(
            {
                "name": item.name,
                "item_id": item.item_id,
                "kind": item.kind,
                "visible": item.visible,
                "locked": item.locked,
                "source_units": item.source_units.value,
                "group_id": item.group_id,
                "text_properties": _text_properties_to_dict(
                    item.text_properties
                ),
                "smart_bindings": dict(item.smart_bindings),
                "vector_path": (
                    {
                        "points_xy": [list(point) for point in item.vector_path.points_xy],
                        "width_mm": item.vector_path.width_mm,
                        "depth_mm": item.vector_path.depth_mm,
                        "closed": item.vector_path.closed,
                        "segments": (
                            [
                                {
                                    "kind": segment.kind,
                                    "control1_xy": (
                                        list(segment.control1_xy)
                                        if segment.control1_xy is not None else None
                                    ),
                                    "control2_xy": (
                                        list(segment.control2_xy)
                                        if segment.control2_xy is not None else None
                                    ),
                                    "bulge": segment.bulge,
                                }
                                for segment in item.vector_path.segments
                            ]
                            if item.vector_path.segments is not None else None
                        ),
                    }
                    if item.vector_path is not None else None
                ),
                "asset_id": asset_id,
                "source_name": source_name,
                "transform": _transform_to_dict(item.transform),
            }
        )

    if len(project.toolpaths) > _MAX_TOOLPATHS:
        raise ProjectFileError("Project contains too many toolpaths.")
    total_toolpath_moves = sum(len(toolpath.moves) for toolpath in project.toolpaths)
    if total_toolpath_moves > _MAX_TOOLPATH_MOVES:
        raise ProjectFileError("Project contains too many toolpath moves.")

    toolpaths: list[dict[str, object]] = []
    for path_index, toolpath in enumerate(project.toolpaths):
        move_data = _encode_toolpath_moves(toolpath)
        moves_asset_id: str | None = None
        if move_data:
            moves_asset_id, payload_offset = _store_payload_asset(
                assets,
                payloads,
                move_data,
                payload_offset=payload_offset,
                original_name=f"toolpath-{path_index + 1}.cfmoves",
            )
        toolpaths.append(
            _toolpath_to_dict(
                toolpath,
                moves_asset_id=moves_asset_id,
            )
        )

    manifest: dict[str, Any] = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_FILE_VERSION,
        "container_version": CONTAINER_VERSION,
        "application": "CarveFoundry",
        "coordinate_system": {"linear_units": "mm"},
        "name": project.name,
        "material_name": project.material_name,
        "notes": project.notes,
        "stock": _stock_to_dict(project.stock),
        "fixtures": [asdict(fixture) for fixture in project.fixtures],
        "smart_values": dict(project.smart_values.expressions),
        "items": items,
        "cam_operations": [
            _cam_operation_to_dict(operation)
            for operation in project.cam_operations
        ],
        "toolpaths": toolpaths,
        "assets": assets,
    }
    return manifest, payloads


def project_to_dict(project: Project, project_path: Path) -> dict[str, Any]:
    """Return the current versioned project manifest as a dictionary."""

    del project_path
    manifest, _ = _build_container(project)
    return manifest


def save_project(project: Project, path: str | Path) -> Path:
    """Write a self-contained native CarveFoundry project container.

    The native CF3D container stores a Zstandard-compressed manifest followed by
    independently compressed, SHA-256-addressed asset payloads. Duplicate source
    assets are stored only once. Assets that are already compressed efficiently
    are stored raw when Zstandard would make them larger.
    """

    project_path = Path(path).expanduser()
    if project_path.suffix.lower() != PROJECT_SUFFIX:
        project_path = project_path.with_suffix(PROJECT_SUFFIX)
    project_path.parent.mkdir(parents=True, exist_ok=True)

    manifest, payloads = _build_container(project)
    manifest_raw = json.dumps(
        manifest,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(manifest_raw) > _MAX_MANIFEST_SIZE:
        raise ProjectFileError("Project manifest is too large to save safely.")
    manifest_stored = _compress_zstd(manifest_raw, level=_MANIFEST_ZSTD_LEVEL)
    header = _HEADER.pack(
        PROJECT_FILE_MAGIC,
        CONTAINER_VERSION,
        _HEADER_FLAGS,
        len(manifest_stored),
        len(manifest_raw),
    )

    temporary = project_path.with_suffix(project_path.suffix + ".tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(header)
            handle.write(manifest_stored)
            for payload in payloads:
                handle.write(payload)
            handle.flush()
        temporary.replace(project_path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProjectFileError(f"Could not save project: {exc}") from exc

    return project_path


def _load_fixtures(value: object) -> list[Fixture]:
    if not isinstance(value, list):
        raise ProjectFileError("Project fixtures must be a list.")
    fixtures: list[Fixture] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ProjectFileError(f"Fixture {index + 1} must be an object.")
        try:
            fixture = Fixture(
                name=str(raw["name"]),
                x_min_mm=float(raw["x_min_mm"]),
                y_min_mm=float(raw["y_min_mm"]),
                x_max_mm=float(raw["x_max_mm"]),
                y_max_mm=float(raw["y_max_mm"]),
                top_z_mm=float(raw["top_z_mm"]),
                clearance_mm=float(raw.get("clearance_mm", 2.0)),
            )
            fixture.validate()
        except (KeyError, ValueError, TypeError) as exc:
            raise ProjectFileError(
                f"Fixture {index + 1} is invalid: {exc}"
            ) from exc
        fixtures.append(fixture)
    return fixtures


def _load_stock(value: object) -> Stock:
    if not isinstance(value, dict):
        raise ProjectFileError("Project stock section is missing or invalid.")
    try:
        stock = Stock(
            width_mm=float(value["width_mm"]),
            height_mm=float(value["height_mm"]),
            thickness_mm=float(value["thickness_mm"]),
            xy_zero=str(value.get("xy_zero", "bottom_left")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectFileError("Project stock dimensions are invalid.") from exc
    if min(stock.width_mm, stock.height_mm, stock.thickness_mm) <= 0:
        raise ProjectFileError("Project stock dimensions must be greater than zero.")
    if stock.xy_zero not in {"bottom_left", "center"}:
        raise ProjectFileError("Project XY work zero must be bottom_left or center.")
    return stock


def _load_transform(value: object) -> Transform3D:
    if value is None:
        return Transform3D()
    if not isinstance(value, dict):
        raise ProjectFileError("Project item transform is invalid.")
    transform = Transform3D(
        translation_mm=_triple(value.get("translation_mm"), field_name="translation_mm"),
        rotation_deg=_triple(value.get("rotation_deg"), field_name="rotation_deg"),
        scale_xyz=_triple(value.get("scale_xyz"), field_name="scale_xyz"),
    )
    try:
        transform.validate()
    except ValueError as exc:
        raise ProjectFileError(str(exc)) from exc
    return transform


def _load_source_units(value: object, *, item_name: str) -> ModelUnits:
    if value is None:
        return ModelUnits.MILLIMETERS
    if not isinstance(value, str):
        raise ProjectFileError(f"Project item {item_name!r} has invalid source units.")
    try:
        return ModelUnits(value)
    except ValueError as exc:
        raise ProjectFileError(
            f"Project item {item_name!r} uses unsupported source units {value!r}."
        ) from exc


def _validate_item_header(value: object) -> tuple[str, str, bool]:
    if not isinstance(value, dict):
        raise ProjectFileError("Project item is invalid.")

    name = value.get("name")
    kind = value.get("kind", "shape")
    visible = value.get("visible", True)
    if not isinstance(name, str) or not name:
        raise ProjectFileError("Project item name is missing or invalid.")
    if not isinstance(kind, str) or not kind:
        raise ProjectFileError(f"Project item {name!r} has an invalid kind.")
    if not isinstance(visible, bool):
        raise ProjectFileError(f"Project item {name!r} has an invalid visibility value.")
    locked = value.get("locked", False)
    if not isinstance(locked, bool):
        raise ProjectFileError(f"Project item {name!r} has an invalid lock value.")
    return name, kind, visible


def _legacy_source_path(value: object, project_path: Path) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ProjectFileError("Project item source_path must be a string or null.")
    source = Path(value).expanduser()
    if not source.is_absolute():
        source = project_path.parent / source
    return source.resolve()


def _load_legacy_item(value: object, project_path: Path) -> ProjectItem:
    name, kind, visible = _validate_item_header(value)
    assert isinstance(value, dict)

    source_path = _legacy_source_path(value.get("source_path"), project_path)
    transform = _load_transform(value.get("transform"))
    source_units = _load_source_units(value.get("source_units"), item_name=name)
    text_properties = _load_text_properties(
        value.get("text_properties"),
        item_name=name,
    )
    group_value = value.get("group_id")
    group_id = group_value if isinstance(group_value, str) and group_value else None
    mesh = None
    if kind.lower() == "stl":
        if source_path is None or not source_path.is_file():
            raise ProjectFileError(f"Source STL for {name!r} is missing: {source_path}")
        try:
            mesh = load_stl(source_path)
        except MeshImportError as exc:
            raise ProjectFileError(f"Could not reload {name!r}: {exc}") from exc

    return ProjectItem(
        name=name,
        source_path=source_path,
        kind=kind,
        visible=visible,
        locked=value.get("locked", False),
        mesh=mesh,
        transform=transform,
        source_units=source_units,
        group_id=group_id,
        text_properties=text_properties,
    )


def _load_legacy_project(project_path: Path) -> Project:
    try:
        payload = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectFileError(f"Could not read project: {exc}") from exc

    if not isinstance(payload, dict):
        raise ProjectFileError("Project file root must be an object.")
    version = payload.get("version")
    if version != LEGACY_PROJECT_FILE_VERSION:
        raise ProjectFileError(
            f"Unsupported project version {version!r}; expected legacy version "
            f"{LEGACY_PROJECT_FILE_VERSION} or native version {PROJECT_FILE_VERSION}."
        )

    name = payload.get("name", "Untitled")
    if not isinstance(name, str) or not name:
        raise ProjectFileError("Project name is invalid.")
    stock = _load_stock(payload.get("stock"))
    items_value = payload.get("items", [])
    if not isinstance(items_value, list):
        raise ProjectFileError("Project items section is invalid.")
    items = [_load_legacy_item(item, project_path) for item in items_value]
    return Project(name=name, stock=stock, items=items)


def _read_exact(handle: BinaryIO, size: int, *, label: str) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise ProjectFileError(f"Project file ended while reading {label}.")
    return data


def _decode_zstd(data: bytes, *, expected_size: int, label: str) -> bytes:
    try:
        result = zstd.ZstdDecompressor().decompress(
            data,
            max_output_size=expected_size,
        )
    except zstd.ZstdError as exc:
        raise ProjectFileError(f"Could not decompress {label}: {exc}") from exc
    if len(result) != expected_size:
        raise ProjectFileError(
            f"{label} size is invalid after decompression."
        )
    return result


def _read_native_manifest(
    handle: BinaryIO,
) -> tuple[dict[str, Any], int]:
    header = _read_exact(handle, _HEADER.size, label="CF3D header")
    magic, container_version, flags, stored_size, original_size = _HEADER.unpack(header)

    if magic != PROJECT_FILE_MAGIC:
        raise ProjectFileError("File is not a native CarveFoundry project.")
    if container_version != CONTAINER_VERSION:
        raise ProjectFileError(
            f"Unsupported CF3D container version {container_version!r}."
        )
    if flags != _HEADER_FLAGS:
        raise ProjectFileError(f"Unsupported CF3D container flags {flags!r}.")
    if original_size <= 0 or original_size > _MAX_MANIFEST_SIZE:
        raise ProjectFileError("Project manifest size is invalid.")
    if stored_size <= 0:
        raise ProjectFileError("Stored project manifest size is invalid.")

    manifest_stored = _read_exact(
        handle,
        stored_size,
        label="compressed project manifest",
    )
    manifest_raw = _decode_zstd(
        manifest_stored,
        expected_size=original_size,
        label="project manifest",
    )
    try:
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectFileError(f"Project manifest is invalid: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ProjectFileError("Project manifest root must be an object.")
    if manifest.get("format") != PROJECT_FORMAT:
        raise ProjectFileError("File is not a recognized CarveFoundry project.")
    if manifest.get("version") != PROJECT_FILE_VERSION:
        raise ProjectFileError(
            f"Unsupported project version {manifest.get('version')!r}; "
            f"expected {PROJECT_FILE_VERSION}."
        )
    return manifest, _HEADER.size + stored_size


def _asset_metadata(
    assets: object,
    asset_id: str,
) -> dict[str, Any]:
    if not isinstance(assets, dict):
        raise ProjectFileError("Project assets section is invalid.")
    metadata = assets.get(asset_id)
    if not isinstance(metadata, dict):
        raise ProjectFileError(f"Embedded asset {asset_id} metadata is missing.")
    if metadata.get("sha256") != asset_id:
        raise ProjectFileError(f"Embedded asset {asset_id} hash metadata is invalid.")
    return metadata


def _read_asset_data(
    handle: BinaryIO,
    *,
    payload_start: int,
    container_size: int,
    asset_id: str,
    metadata: dict[str, Any],
    expected_original_size: int | None = None,
) -> bytes:
    try:
        offset = int(metadata["offset"])
        stored_size = int(metadata["stored_size"])
        original_size = int(metadata["original_size"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectFileError(f"Embedded asset {asset_id} sizes are invalid.") from exc

    if min(offset, stored_size, original_size) < 0:
        raise ProjectFileError(f"Embedded asset {asset_id} sizes are invalid.")
    if expected_original_size is not None and original_size != expected_original_size:
        raise ProjectFileError(
            f"Embedded asset {asset_id} original size is invalid."
        )

    absolute_start = payload_start + offset
    absolute_end = absolute_start + stored_size
    if absolute_start < payload_start or absolute_end > container_size:
        raise ProjectFileError(f"Embedded asset {asset_id} extends outside the project file.")

    handle.seek(absolute_start)
    stored = _read_exact(handle, stored_size, label=f"embedded asset {asset_id}")
    codec = metadata.get("codec")
    if codec == "zstd":
        data = _decode_zstd(
            stored,
            expected_size=original_size,
            label=f"embedded asset {asset_id}",
        )
    elif codec == "raw":
        data = stored
        if len(data) != original_size:
            raise ProjectFileError(f"Embedded asset {asset_id} size verification failed.")
    else:
        raise ProjectFileError(
            f"Embedded asset {asset_id} uses unsupported codec {codec!r}."
        )

    digest = hashlib.sha256(data).hexdigest()
    if digest != asset_id:
        raise ProjectFileError(
            f"Embedded asset {asset_id} failed SHA-256 verification."
        )
    return data


def _materialize_asset(
    handle: BinaryIO,
    *,
    payload_start: int,
    container_size: int,
    asset_id: str,
    metadata: dict[str, Any],
    source_name: str | None,
    workspace: Path,
) -> Path:
    data = _read_asset_data(
        handle,
        payload_start=payload_start,
        container_size=container_size,
        asset_id=asset_id,
        metadata=metadata,
    )

    metadata_name = metadata.get("original_name")
    preferred = source_name if isinstance(source_name, str) and source_name else metadata_name
    if not isinstance(preferred, str) or not preferred:
        preferred = f"{asset_id}.bin"
    filename = _safe_source_name(preferred, fallback=f"{asset_id}.bin")

    target_directory = workspace / asset_id
    target_directory.mkdir(parents=True, exist_ok=True)
    target = target_directory / filename
    try:
        target.write_bytes(data)
    except OSError as exc:
        raise ProjectFileError(f"Could not materialize embedded asset: {exc}") from exc
    return target


def _load_native_item(
    value: object,
    *,
    handle: BinaryIO,
    payload_start: int,
    container_size: int,
    assets: object,
    workspace: Path,
    materialized: dict[tuple[str, str], Path],
) -> ProjectItem:
    name, kind, visible = _validate_item_header(value)
    assert isinstance(value, dict)

    transform = _load_transform(value.get("transform"))
    source_units = _load_source_units(value.get("source_units"), item_name=name)
    text_properties = _load_text_properties(
        value.get("text_properties"),
        item_name=name,
    )
    group_value = value.get("group_id")
    group_id = group_value if isinstance(group_value, str) and group_value else None
    bindings_value = value.get("smart_bindings", {})
    if not isinstance(bindings_value, dict) or not all(
        isinstance(key, str) and isinstance(expression, str)
        for key, expression in bindings_value.items()
    ):
        raise ProjectFileError(f"Project item {name!r} has invalid Smart Value bindings.")
    smart_bindings = dict(bindings_value)
    vector_value = value.get("vector_path")
    vector_path = None
    if vector_value is not None:
        if not isinstance(vector_value, dict):
            raise ProjectFileError(f"Project item {name!r}: invalid vector path.")
        raw_points = vector_value.get("points_xy")
        if not isinstance(raw_points, list) or not all(
            isinstance(pair, list) and len(pair) == 2
            for pair in raw_points
        ):
            raise ProjectFileError(
                f"Project item {name!r}: vector path needs XY point pairs."
            )
        try:
            if any(
                isinstance(component, bool) or not isinstance(component, (int, float))
                for pair in raw_points for component in pair
            ):
                raise ValueError("Vector points must be numbers.")
            closed = vector_value.get("closed", False)
            if not isinstance(closed, bool):
                raise TypeError("Closed state must be boolean.")
            width = vector_value["width_mm"]
            depth = vector_value["depth_mm"]
            if (
                isinstance(width, bool) or not isinstance(width, (int, float))
                or isinstance(depth, bool) or not isinstance(depth, (int, float))
            ):
                raise TypeError("Width/depth must be numbers.")
            raw_segments = vector_value.get("segments")
            segments = None
            if raw_segments is not None:
                if not isinstance(raw_segments, list):
                    raise TypeError("Vector segments must be a list.")
                parsed_segments: list[VectorSegment] = []
                for raw_segment in raw_segments:
                    if not isinstance(raw_segment, dict):
                        raise TypeError("Vector segment must be an object.")
                    kind = raw_segment.get("kind", "line")
                    if not isinstance(kind, str):
                        raise TypeError("Vector segment kind must be text.")

                    def control(name: str, segment_data=raw_segment):
                        raw_control = segment_data.get(name)
                        if raw_control is None:
                            return None
                        if (
                            not isinstance(raw_control, list)
                            or len(raw_control) != 2
                            or any(
                                isinstance(value, bool)
                                or not isinstance(value, (int, float))
                                for value in raw_control
                            )
                        ):
                            raise TypeError(
                                f"Vector segment {name} must be an XY pair."
                            )
                        return tuple(float(value) for value in raw_control)

                    raw_bulge = raw_segment.get("bulge", 0.0)
                    if (
                        isinstance(raw_bulge, bool)
                        or not isinstance(raw_bulge, (int, float))
                    ):
                        raise TypeError("Vector arc bulge must be numeric.")
                    parsed_segments.append(
                        VectorSegment(
                            kind=kind,
                            control1_xy=control("control1_xy"),
                            control2_xy=control("control2_xy"),
                            bulge=float(raw_bulge),
                        )
                    )
                segments = tuple(parsed_segments)

            vector_path = VectorPath(
                points_xy=tuple(tuple(float(v) for v in pair) for pair in raw_points),
                width_mm=float(width),
                depth_mm=float(depth),
                closed=closed,
                segments=segments,
            )
            vector_path.validate()
        except (ValueError, TypeError, KeyError) as exc:
            raise ProjectFileError(
                f"Project item {name!r}: invalid editable path: {exc}"
            ) from exc
    item_id_value = value.get("item_id")
    item_id = (
        item_id_value
        if isinstance(item_id_value, str) and item_id_value.strip()
        else None
    )
    asset_id = value.get("asset_id")
    source_name_value = value.get("source_name")
    source_name = source_name_value if isinstance(source_name_value, str) else None

    source_path: Path | None = None
    mesh = None

    if asset_id is not None:
        if not isinstance(asset_id, str) or len(asset_id) != 64:
            raise ProjectFileError(f"Project item {name!r} has an invalid asset id.")
        metadata = _asset_metadata(assets, asset_id)
        materialize_name = source_name or str(metadata.get("original_name") or "")
        cache_key = (asset_id, materialize_name)
        source_path = materialized.get(cache_key)
        if source_path is None:
            source_path = _materialize_asset(
                handle,
                payload_start=payload_start,
                container_size=container_size,
                asset_id=asset_id,
                metadata=metadata,
                source_name=source_name,
                workspace=workspace,
            )
            materialized[cache_key] = source_path

    if source_path is not None and source_path.suffix.lower() == ".stl":
        try:
            mesh = load_stl(source_path)
        except MeshImportError as exc:
            raise ProjectFileError(f"Could not reload embedded {name!r}: {exc}") from exc
    elif kind.lower() == "stl":
        raise ProjectFileError(f"Embedded STL asset for {name!r} is missing.")

    item_kwargs: dict[str, object] = {
        "name": name,
        "source_path": source_path,
        "kind": kind,
        "visible": visible,
        "locked": value.get("locked", False),
        "mesh": mesh,
        "transform": transform,
        "source_units": source_units,
        "group_id": group_id,
        "text_properties": text_properties,
        "smart_bindings": smart_bindings,
        "vector_path": vector_path,
    }
    if item_id is not None:
        item_kwargs["item_id"] = item_id
    return ProjectItem(**item_kwargs)


def _load_native_project(project_path: Path) -> Project:
    try:
        container_size = project_path.stat().st_size
    except OSError as exc:
        raise ProjectFileError(f"Could not inspect project: {exc}") from exc

    workspace_owner = tempfile.TemporaryDirectory(prefix="carvefoundry-assets-")
    workspace = Path(workspace_owner.name)
    try:
        with project_path.open("rb") as handle:
            manifest, payload_start = _read_native_manifest(handle)

            name = manifest.get("name", "Untitled")
            if not isinstance(name, str) or not name:
                raise ProjectFileError("Project name is invalid.")
            material_name = manifest.get("material_name", "Not specified")
            notes = manifest.get("notes", "")
            if not isinstance(material_name, str) or not isinstance(notes, str):
                raise ProjectFileError("Material or project notes have invalid text.")
            stock = _load_stock(manifest.get("stock"))
            fixtures = _load_fixtures(manifest.get("fixtures", []))
            items_value = manifest.get("items", [])
            if not isinstance(items_value, list):
                raise ProjectFileError("Project items section is invalid.")

            smart_values_raw = manifest.get("smart_values", {})
            if not isinstance(smart_values_raw, dict) or not all(
                isinstance(key, str) and isinstance(expression, str)
                for key, expression in smart_values_raw.items()
            ):
                raise ProjectFileError("Project Smart Values section is invalid.")
            smart_values = SmartValues(dict(smart_values_raw))
            try:
                smart_values.resolve_all()
            except SmartValueError as exc:
                raise ProjectFileError(f"Project Smart Values are invalid: {exc}") from exc

            assets = manifest.get("assets", {})
            materialized: dict[tuple[str, str], Path] = {}
            items = [
                _load_native_item(
                    item,
                    handle=handle,
                    payload_start=payload_start,
                    container_size=container_size,
                    assets=assets,
                    workspace=workspace,
                    materialized=materialized,
                )
                for item in items_value
            ]
            cam_operations = _load_cam_operations(
                manifest.get("cam_operations", [])
            )
            toolpaths = _load_toolpaths(
                manifest.get("toolpaths", []),
                handle=handle,
                payload_start=payload_start,
                container_size=container_size,
                assets=assets,
            )
    except (OSError, ProjectFileError):
        workspace_owner.cleanup()
        raise

    return Project(
        name=name,
        stock=stock,
        items=items,
        smart_values=smart_values,
        fixtures=fixtures,
        toolpaths=toolpaths,
        cam_operations=cam_operations,
        material_name=material_name,
        notes=notes,
        _asset_workspace_owner=workspace_owner,
    )


def load_project(path: str | Path) -> Project:
    """Load a native CF3D package or a legacy version-1 JSON project."""

    project_path = Path(path).expanduser()
    if not project_path.is_file():
        raise ProjectFileError(f"Project file does not exist: {project_path}")

    try:
        with project_path.open("rb") as handle:
            magic = handle.read(len(PROJECT_FILE_MAGIC))
    except OSError as exc:
        raise ProjectFileError(f"Could not read project: {exc}") from exc

    if magic == PROJECT_FILE_MAGIC:
        return _load_native_project(project_path)
    return _load_legacy_project(project_path)
