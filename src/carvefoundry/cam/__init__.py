"""Core CAM geometry and toolpath primitives for CarveFoundry."""

from .contact import CutterContactMap, compensate_height_field
from .heightfield import HeightField

__all__ = ["CutterContactMap", "HeightField", "compensate_height_field"]
