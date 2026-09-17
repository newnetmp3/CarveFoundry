"""Core CAM geometry and toolpath primitives for CarveFoundry."""

from .contact import CutterContactMap, compensate_height_field
from .finish import Finish3DResult, Finish3DSettings, calculate_3d_finish
from .heightfield import HeightField
from .raster import RasterAxis, RasterFinishingSettings, generate_raster_finishing
from .toolpath import MoveKind, Toolpath, ToolpathMove

__all__ = [
    "CutterContactMap",
    "Finish3DResult",
    "Finish3DSettings",
    "HeightField",
    "MoveKind",
    "RasterAxis",
    "RasterFinishingSettings",
    "Toolpath",
    "ToolpathMove",
    "calculate_3d_finish",
    "compensate_height_field",
    "generate_raster_finishing",
]
