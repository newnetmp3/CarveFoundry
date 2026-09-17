from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import trimesh

from .mesh import MeshAsset
from .transform import Transform3D, placement_on_stock


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

    def transformed_mesh(self) -> trimesh.Trimesh | None:
        """Return geometry exactly as the viewport/CAM should see it."""

        if self.mesh is None:
            return None
        return self.transform.apply_to_mesh(self.mesh.mesh)


@dataclass(slots=True)
class Project:
    name: str = "Untitled"
    stock: Stock = field(default_factory=Stock)
    items: list[ProjectItem] = field(default_factory=list)

    def default_transform_for_mesh(self, mesh: MeshAsset) -> Transform3D:
        """Place newly imported geometry in a useful stock-relative starting position."""

        return placement_on_stock(
            mesh.mesh,
            stock_width_mm=self.stock.width_mm,
            stock_height_mm=self.stock.height_mm,
        )
