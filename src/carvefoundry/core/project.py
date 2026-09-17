from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import trimesh

from .mesh import MeshAsset
from .transform import Transform3D, placement_on_stock
from .units import ModelUnits


@dataclass(slots=True)
class Stock:
    width_mm: float = 300.0
    height_mm: float = 200.0
    thickness_mm: float = 19.0


@dataclass(slots=True)
class ProjectItem:
    name: str
    source_path: Path | None = None
    kind: str = "shape"
    visible: bool = True
    mesh: MeshAsset | None = None
    transform: Transform3D = field(default_factory=Transform3D)
    source_units: ModelUnits = ModelUnits.MILLIMETERS

    def source_mesh_mm(self) -> trimesh.Trimesh | None:
        """Return source geometry converted to CarveFoundry's millimeter coordinate space."""

        if self.mesh is None:
            return None
        mesh = self.mesh.mesh.copy()
        mesh.apply_scale(self.source_units.millimeters_per_unit)
        return mesh

    def transformed_mesh(self) -> trimesh.Trimesh | None:
        """Return geometry exactly as the viewport/CAM should see it, in millimeters."""

        mesh_mm = self.source_mesh_mm()
        if mesh_mm is None:
            return None
        return self.transform.apply_to_mesh(mesh_mm)


@dataclass(slots=True)
class Project:
    name: str = "Untitled"
    stock: Stock = field(default_factory=Stock)
    items: list[ProjectItem] = field(default_factory=list)
    _asset_workspace_owner: object | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def default_transform_for_mesh(
        self,
        mesh: MeshAsset,
        source_units: ModelUnits | None = None,
    ) -> Transform3D:
        """Place newly imported geometry in a useful stock-relative starting position."""

        units = source_units or ModelUnits.from_metadata(mesh.units)
        mesh_mm = mesh.mesh.copy()
        mesh_mm.apply_scale(units.millimeters_per_unit)
        return placement_on_stock(
            mesh_mm,
            stock_width_mm=self.stock.width_mm,
            stock_height_mm=self.stock.height_mm,
        )

    def remove_item(self, index: int) -> ProjectItem:
        """Remove and return a design item by zero-based project-item index."""

        if not 0 <= index < len(self.items):
            raise IndexError("Project item index out of range")
        return self.items.pop(index)

    def duplicate_item(self, index: int) -> tuple[int, ProjectItem]:
        """Duplicate an item while sharing immutable source geometry and copying placement."""

        if not 0 <= index < len(self.items):
            raise IndexError("Project item index out of range")
        source = self.items[index]
        source_name = Path(source.name)
        duplicate_name = f"{source_name.stem} copy{source_name.suffix}"
        duplicate = ProjectItem(
            name=duplicate_name,
            source_path=source.source_path,
            kind=source.kind,
            visible=source.visible,
            mesh=source.mesh,
            transform=Transform3D(
                translation_mm=tuple(source.transform.translation_mm),
                rotation_deg=tuple(source.transform.rotation_deg),
                scale_xyz=tuple(source.transform.scale_xyz),
            ),
            source_units=source.source_units,
        )
        new_index = index + 1
        self.items.insert(new_index, duplicate)
        return new_index, duplicate

    def move_item(self, index: int, offset: int) -> int:
        """Move an item by *offset* slots and return its resulting index."""

        if not 0 <= index < len(self.items):
            raise IndexError("Project item index out of range")
        if not self.items:
            return index
        target = max(0, min(len(self.items) - 1, index + offset))
        if target == index:
            return index
        item = self.items.pop(index)
        self.items.insert(target, item)
        return target
