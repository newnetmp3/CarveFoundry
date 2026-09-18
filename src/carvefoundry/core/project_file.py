from __future__ import annotations

import hashlib
import json
import struct
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

import zstandard as zstd

from .mesh import MeshImportError, load_stl
from .project import Project, ProjectItem, Stock
from .transform import Transform3D
from .units import ModelUnits

PROJECT_FILE_VERSION = 2
LEGACY_PROJECT_FILE_VERSION = 1
PROJECT_SUFFIX = ".cf3d"
PROJECT_FORMAT = "CarveFoundry Project"

PROJECT_FILE_MAGIC = b"CF3D\x1aZST"
CONTAINER_VERSION = 1
_HEADER = struct.Struct("<8sIIQQ")
_HEADER_FLAGS = 0
_MAX_MANIFEST_SIZE = 64 * 1024 * 1024
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


def _stock_to_dict(stock: Stock) -> dict[str, float]:
    return {
        "width_mm": stock.width_mm,
        "height_mm": stock.height_mm,
        "thickness_mm": stock.thickness_mm,
    }


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
            asset_id = hashlib.sha256(data).hexdigest()
            if asset_id not in assets:
                codec, stored = _encode_asset(data)
                assets[asset_id] = {
                    "offset": payload_offset,
                    "stored_size": len(stored),
                    "original_size": len(data),
                    "codec": codec,
                    "sha256": asset_id,
                    "original_name": source_name,
                }
                payloads.append(stored)
                payload_offset += len(stored)

        items.append(
            {
                "name": item.name,
                "kind": item.kind,
                "visible": item.visible,
                "source_units": item.source_units.value,
                "group_id": item.group_id,
                "asset_id": asset_id,
                "source_name": source_name,
                "transform": _transform_to_dict(item.transform),
            }
        )

    manifest: dict[str, Any] = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_FILE_VERSION,
        "container_version": CONTAINER_VERSION,
        "application": "CarveFoundry",
        "coordinate_system": {"linear_units": "mm"},
        "name": project.name,
        "stock": _stock_to_dict(project.stock),
        "items": items,
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


def _load_stock(value: object) -> Stock:
    if not isinstance(value, dict):
        raise ProjectFileError("Project stock section is missing or invalid.")
    try:
        stock = Stock(
            width_mm=float(value["width_mm"]),
            height_mm=float(value["height_mm"]),
            thickness_mm=float(value["thickness_mm"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectFileError("Project stock dimensions are invalid.") from exc
    if min(stock.width_mm, stock.height_mm, stock.thickness_mm) <= 0:
        raise ProjectFileError("Project stock dimensions must be greater than zero.")
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
        mesh=mesh,
        transform=transform,
        source_units=source_units,
        group_id=group_id,
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
    try:
        offset = int(metadata["offset"])
        stored_size = int(metadata["stored_size"])
        original_size = int(metadata["original_size"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectFileError(f"Embedded asset {asset_id} sizes are invalid.") from exc

    if min(offset, stored_size, original_size) < 0:
        raise ProjectFileError(f"Embedded asset {asset_id} sizes are invalid.")
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
    group_value = value.get("group_id")
    group_id = group_value if isinstance(group_value, str) and group_value else None
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

    return ProjectItem(
        name=name,
        source_path=source_path,
        kind=kind,
        visible=visible,
        mesh=mesh,
        transform=transform,
        source_units=source_units,
        group_id=group_id,
    )


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
            stock = _load_stock(manifest.get("stock"))
            items_value = manifest.get("items", [])
            if not isinstance(items_value, list):
                raise ProjectFileError("Project items section is invalid.")

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
    except (OSError, ProjectFileError):
        workspace_owner.cleanup()
        raise

    return Project(
        name=name,
        stock=stock,
        items=items,
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
