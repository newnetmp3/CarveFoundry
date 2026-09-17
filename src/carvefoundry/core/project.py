from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .mesh import MeshAsset


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


@dataclass(slots=True)
class Project:
    name: str = "Untitled"
    stock: Stock = field(default_factory=Stock)
    items: list[ProjectItem] = field(default_factory=list)
