from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import numpy as np
import trimesh

from .fixtures import Fixture
from .mesh import MeshAsset
from .smart_values import SmartValues
from .transform import Transform3D
from .units import ModelUnits

if TYPE_CHECKING:
    from carvefoundry.cam.toolpath import Toolpath


MIN_IMPORTED_STOCK_COVERAGE = 0.5


@dataclass(slots=True)
class Stock:
    width_mm: float = 300.0
    height_mm: float = 200.0
    thickness_mm: float = 19.0
    xy_zero: str = "bottom_left"


@dataclass(frozen=True, slots=True)
class TextProperties:
    """Editable CNC text settings stored independently from generated mesh data."""

    content: str = "Text"
    font_family: str = ""
    font_style: str = "Regular"
    size_pt: float = 36.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikeout: bool = False
    alignment: str = "left"
    character_spacing_mm: float = 0.0
    word_spacing_mm: float = 0.0
    kerning: bool = True
    line_spacing_percent: float = 100.0
    horizontal_scale_percent: float = 100.0
    wrap_to_width: bool = False
    box_width_mm: float = 0.0
    depth_mm: float = 1.0
    geometry_mode: str = "filled"
    outline_width_mm: float = 0.8
    case_mode: str = "normal"

    def validate(self) -> None:
        if not self.content:
            raise ValueError("Text content cannot be empty.")
        if not np.isfinite(
            (
                self.size_pt,
                self.character_spacing_mm,
                self.word_spacing_mm,
                self.line_spacing_percent,
                self.horizontal_scale_percent,
                self.box_width_mm,
                self.depth_mm,
                self.outline_width_mm,
            )
        ).all():
            raise ValueError("Text properties must be finite.")
        if self.size_pt <= 0:
            raise ValueError("Font size must be greater than zero.")
        if self.line_spacing_percent <= 0:
            raise ValueError("Line spacing must be greater than zero.")
        if self.horizontal_scale_percent <= 0:
            raise ValueError("Horizontal font scale must be greater than zero.")
        if self.box_width_mm < 0:
            raise ValueError("Text box width cannot be negative.")
        if self.depth_mm <= 0:
            raise ValueError("Text depth must be greater than zero.")
        if self.outline_width_mm <= 0:
            raise ValueError("Outline width must be greater than zero.")
        if self.alignment not in {"left", "center", "right", "justify"}:
            raise ValueError(f"Unsupported text alignment: {self.alignment}")
        if self.geometry_mode not in {"filled", "outline"}:
            raise ValueError(f"Unsupported text geometry mode: {self.geometry_mode}")
        if self.case_mode not in {"normal", "uppercase", "lowercase", "title"}:
            raise ValueError(f"Unsupported text case mode: {self.case_mode}")


@dataclass(slots=True)
class ProjectItem:
    name: str
    source_path: Path | None = None
    kind: str = "shape"
    visible: bool = True
    mesh: MeshAsset | None = None
    transform: Transform3D = field(default_factory=Transform3D)
    source_units: ModelUnits = ModelUnits.MILLIMETERS
    group_id: str | None = None
    item_id: str = field(default_factory=lambda: uuid4().hex)
    text_properties: TextProperties | None = None
    smart_bindings: dict[str, str] = field(default_factory=dict)

    def source_mesh_mm(self) -> trimesh.Trimesh | None:
        """Return source geometry converted to CarveFoundry's millimeter coordinate space."""

        if self.mesh is None:
            return None
        mesh = self.mesh.mesh.copy()
        mesh.apply_scale(self.source_units.millimeters_per_unit)
        return mesh

    def local_size_mm(self) -> np.ndarray | None:
        """Return XYZ model size after units/scale but before rotation.

        Keeping Size independent of rotation gives the transform editor stable
        CAD-style dimensions: rotating a model does not make its Size fields
        change just because its world-axis bounding box changed.
        """

        if self.mesh is None:
            return None
        source_dimensions = np.asarray(self.mesh.dimensions, dtype=float)
        source_dimensions *= float(self.source_units.millimeters_per_unit)
        scale = np.asarray(self.transform.scale_xyz, dtype=float)
        return source_dimensions * scale

    def transformed_bounds_mm(self) -> np.ndarray | None:
        """Return fast conservative placed bounds without copying the full mesh."""

        if self.mesh is None:
            return None
        bounds = np.asarray(self.mesh.bounds, dtype=float)
        bounds *= float(self.source_units.millimeters_per_unit)
        minimum, maximum = bounds
        corners = np.array(
            [
                (x, y, z)
                for x in (minimum[0], maximum[0])
                for y in (minimum[1], maximum[1])
                for z in (minimum[2], maximum[2])
            ],
            dtype=float,
        )
        pivot = tuple(float(value) for value in bounds.mean(axis=0))
        transformed = self.transform.apply_points(corners, pivot=pivot)
        return np.vstack((transformed.min(axis=0), transformed.max(axis=0)))

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
    smart_values: SmartValues = field(default_factory=SmartValues)
    fixtures: list[Fixture] = field(default_factory=list)
    toolpaths: list[Toolpath] = field(
        default_factory=list,
        repr=False,
        compare=False,
    )
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
        bounds = np.asarray(mesh.bounds, dtype=float)
        bounds *= float(units.millimeters_per_unit)
        center = bounds.mean(axis=0)
        dimensions = bounds[1] - bounds[0]

        stock_width = max(float(self.stock.width_mm), 1e-9)
        stock_height = max(float(self.stock.height_mm), 1e-9)
        coverage = max(
            float(dimensions[0]) / stock_width,
            float(dimensions[1]) / stock_height,
        )
        uniform_scale = (
            max(1.0, MIN_IMPORTED_STOCK_COVERAGE / coverage)
            if coverage > 1e-12
            else 1.0
        )

        scaled_top = center[2] + uniform_scale * (bounds[1, 2] - center[2])
        return Transform3D(
            translation_mm=(
                float(self.stock.width_mm / 2.0 - center[0]),
                float(self.stock.height_mm / 2.0 - center[1]),
                float(-scaled_top),
            ),
            scale_xyz=(uniform_scale, uniform_scale, uniform_scale),
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
            group_id=None,
            text_properties=source.text_properties,
            smart_bindings=dict(source.smart_bindings),
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
