from __future__ import annotations

from enum import StrEnum


class ModelUnits(StrEnum):
    """Interpretation of otherwise unitless imported model coordinates."""

    MILLIMETERS = "mm"
    CENTIMETERS = "cm"
    METERS = "m"
    INCHES = "in"

    @property
    def millimeters_per_unit(self) -> float:
        return {
            ModelUnits.MILLIMETERS: 1.0,
            ModelUnits.CENTIMETERS: 10.0,
            ModelUnits.METERS: 1000.0,
            ModelUnits.INCHES: 25.4,
        }[self]

    @property
    def display_name(self) -> str:
        return {
            ModelUnits.MILLIMETERS: "Millimeters (mm)",
            ModelUnits.CENTIMETERS: "Centimeters (cm)",
            ModelUnits.METERS: "Meters (m)",
            ModelUnits.INCHES: "Inches (in)",
        }[self]

    @classmethod
    def from_metadata(cls, value: str | None) -> ModelUnits:
        """Map common mesh-unit spellings to a model-unit assumption.

        STL itself has no unit field, so unknown or missing metadata deliberately
        defaults to millimeters, matching CarveFoundry's internal/CNC units.
        """

        if not value:
            return cls.MILLIMETERS
        normalized = value.strip().lower().replace("_", " ")
        aliases = {
            "mm": cls.MILLIMETERS,
            "millimeter": cls.MILLIMETERS,
            "millimeters": cls.MILLIMETERS,
            "millimetre": cls.MILLIMETERS,
            "millimetres": cls.MILLIMETERS,
            "cm": cls.CENTIMETERS,
            "centimeter": cls.CENTIMETERS,
            "centimeters": cls.CENTIMETERS,
            "centimetre": cls.CENTIMETERS,
            "centimetres": cls.CENTIMETERS,
            "m": cls.METERS,
            "meter": cls.METERS,
            "meters": cls.METERS,
            "metre": cls.METERS,
            "metres": cls.METERS,
            "in": cls.INCHES,
            "inch": cls.INCHES,
            "inches": cls.INCHES,
        }
        return aliases.get(normalized, cls.MILLIMETERS)
