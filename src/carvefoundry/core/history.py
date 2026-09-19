from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from carvefoundry.cam.toolpath import Toolpath

from .fixtures import Fixture
from .mesh import MeshAsset
from .project import Project, ProjectItem, Stock, TextProperties
from .smart_values import SmartValues
from .transform import Transform3D
from .units import ModelUnits


@dataclass(frozen=True, slots=True)
class ProjectItemSnapshot:
    name: str
    source_path: Path | None
    kind: str
    visible: bool
    mesh: MeshAsset | None
    translation_mm: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]
    scale_xyz: tuple[float, float, float]
    source_units: ModelUnits
    group_id: str | None
    item_id: str
    text_properties: TextProperties | None
    smart_bindings: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """Undoable project state without copying heavy source mesh geometry."""

    stock: tuple[float, float, float, str]
    fixtures: tuple[Fixture, ...]
    smart_values: tuple[tuple[str, str], ...]
    items: tuple[ProjectItemSnapshot, ...]
    toolpaths: tuple[Toolpath, ...]


def _snapshot_item(item: ProjectItem) -> ProjectItemSnapshot:
    return ProjectItemSnapshot(
        name=item.name,
        source_path=item.source_path,
        kind=item.kind,
        visible=item.visible,
        mesh=item.mesh,
        translation_mm=tuple(item.transform.translation_mm),
        rotation_deg=tuple(item.transform.rotation_deg),
        scale_xyz=tuple(item.transform.scale_xyz),
        source_units=item.source_units,
        group_id=item.group_id,
        item_id=item.item_id,
        text_properties=item.text_properties,
        smart_bindings=tuple(item.smart_bindings.items()),
    )


def capture_workspace(project: Project) -> WorkspaceSnapshot:
    """Capture mutable workspace state while sharing immutable/heavy assets."""

    return WorkspaceSnapshot(
        stock=(
            project.stock.width_mm,
            project.stock.height_mm,
            project.stock.thickness_mm,
            project.stock.xy_zero,
        ),
        fixtures=tuple(project.fixtures),
        smart_values=tuple(project.smart_values.expressions.items()),
        items=tuple(_snapshot_item(item) for item in project.items),
        toolpaths=tuple(project.toolpaths),
    )


def _restore_item(snapshot: ProjectItemSnapshot) -> ProjectItem:
    return ProjectItem(
        name=snapshot.name,
        source_path=snapshot.source_path,
        kind=snapshot.kind,
        visible=snapshot.visible,
        mesh=snapshot.mesh,
        transform=Transform3D(
            translation_mm=snapshot.translation_mm,
            rotation_deg=snapshot.rotation_deg,
            scale_xyz=snapshot.scale_xyz,
        ),
        source_units=snapshot.source_units,
        group_id=snapshot.group_id,
        item_id=snapshot.item_id,
        text_properties=snapshot.text_properties,
        smart_bindings=dict(snapshot.smart_bindings),
    )


def restore_workspace(project: Project, snapshot: WorkspaceSnapshot) -> None:
    """Restore an undo snapshot into the existing project identity."""

    project.stock = Stock(
        width_mm=snapshot.stock[0],
        height_mm=snapshot.stock[1],
        thickness_mm=snapshot.stock[2],
        xy_zero=snapshot.stock[3],
    )
    project.fixtures = list(snapshot.fixtures)
    project.smart_values = SmartValues(dict(snapshot.smart_values))
    project.items = [_restore_item(item) for item in snapshot.items]
    project.toolpaths = list(snapshot.toolpaths)
