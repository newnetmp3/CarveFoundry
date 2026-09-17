from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .mesh import MeshImportError, load_stl
from .project import Project, ProjectItem, Stock
from .transform import Transform3D
from .units import ModelUnits

PROJECT_FILE_VERSION = 1
PROJECT_SUFFIX = ".carvefoundry"


class ProjectFileError(ValueError):
    """Raised when a CarveFoundry project file cannot be read or reconstructed."""


def _source_path_for_save(source_path: Path | None, project_path: Path) -> str | None:
    if source_path is None:
        return None
    try:
        return os.path.relpath(source_path.resolve(), project_path.parent.resolve())
    except (OSError, ValueError):
        return str(source_path)


def _source_path_for_load(value: object, project_path: Path) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ProjectFileError("Project item source_path must be a string or null.")
    source = Path(value).expanduser()
    if not source.is_absolute():
        source = project_path.parent / source
    return source.resolve()


def _triple(value: object, *, field_name: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ProjectFileError(f"{field_name} must contain exactly three numbers.")
    try:
        result = tuple(float(component) for component in value)
    except (TypeError, ValueError) as exc:
        raise ProjectFileError(f"{field_name} must contain exactly three numbers.") from exc
    return result


def project_to_dict(project: Project, project_path: Path) -> dict[str, Any]:
    """Return the portable, versioned representation stored on disk."""

    return {
        "version": PROJECT_FILE_VERSION,
        "name": project.name,
        "stock": {
            "width_mm": project.stock.width_mm,
            "height_mm": project.stock.height_mm,
            "thickness_mm": project.stock.thickness_mm,
        },
        "items": [
            {
                "name": item.name,
                "source_path": _source_path_for_save(item.source_path, project_path),
                "kind": item.kind,
                "visible": item.visible,
                "source_units": item.source_units.value,
                "transform": {
                    "translation_mm": list(item.transform.translation_mm),
                    "rotation_deg": list(item.transform.rotation_deg),
                    "scale_xyz": list(item.transform.scale_xyz),
                },
            }
            for item in project.items
        ],
    }


def save_project(project: Project, path: str | Path) -> Path:
    """Write a project atomically enough for ordinary desktop use."""

    project_path = Path(path).expanduser()
    if project_path.suffix.lower() != PROJECT_SUFFIX:
        project_path = project_path.with_suffix(PROJECT_SUFFIX)
    project_path.parent.mkdir(parents=True, exist_ok=True)

    payload = project_to_dict(project, project_path)
    temporary = project_path.with_suffix(project_path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(project_path)
    except OSError as exc:
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


def _load_item(value: object, project_path: Path) -> ProjectItem:
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

    source_path = _source_path_for_load(value.get("source_path"), project_path)
    transform = _load_transform(value.get("transform"))
    source_units = _load_source_units(value.get("source_units"), item_name=name)
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
    )


def load_project(path: str | Path) -> Project:
    """Load a CarveFoundry project and rehydrate referenced STL geometry."""

    project_path = Path(path).expanduser()
    if not project_path.is_file():
        raise ProjectFileError(f"Project file does not exist: {project_path}")
    try:
        payload = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectFileError(f"Could not read project: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProjectFileError("Project file root must be an object.")
    if payload.get("version") != PROJECT_FILE_VERSION:
        raise ProjectFileError(
            f"Unsupported project version {payload.get('version')!r}; "
            f"expected {PROJECT_FILE_VERSION}."
        )

    name = payload.get("name", "Untitled")
    if not isinstance(name, str) or not name:
        raise ProjectFileError("Project name is invalid.")
    stock = _load_stock(payload.get("stock"))
    items_value = payload.get("items", [])
    if not isinstance(items_value, list):
        raise ProjectFileError("Project items section is invalid.")
    items = [_load_item(item, project_path) for item in items_value]
    return Project(name=name, stock=stock, items=items)
