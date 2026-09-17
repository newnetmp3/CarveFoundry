"""Core CAM geometry and toolpath primitives for CarveFoundry."""

from .contact import CutterContactMap, compensate_height_field
from .heightfield import HeightField
from .raster import RasterAxis, RasterFinishingSettings, generate_raster_finishing
from .toolpath import MoveKind, Toolpath, ToolpathMove

__all__ = [
    "CutterContactMap",
    "HeightField",
    "MoveKind",
    "RasterAxis",
    "RasterFinishingSettings",
    "Toolpath",
    "ToolpathMove",
    "compensate_height_field",
    "generate_raster_finishing",
]
