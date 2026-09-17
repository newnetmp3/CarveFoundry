from carvefoundry.core.units import ModelUnits


def test_unit_scales_to_millimeters() -> None:
    assert ModelUnits.MILLIMETERS.millimeters_per_unit == 1.0
    assert ModelUnits.CENTIMETERS.millimeters_per_unit == 10.0
    assert ModelUnits.METERS.millimeters_per_unit == 1000.0
    assert ModelUnits.INCHES.millimeters_per_unit == 25.4


def test_common_metadata_spellings_are_recognized() -> None:
    assert ModelUnits.from_metadata("millimeters") is ModelUnits.MILLIMETERS
    assert ModelUnits.from_metadata("CM") is ModelUnits.CENTIMETERS
    assert ModelUnits.from_metadata("metres") is ModelUnits.METERS
    assert ModelUnits.from_metadata("inches") is ModelUnits.INCHES


def test_unknown_or_missing_mesh_units_default_to_mm() -> None:
    assert ModelUnits.from_metadata(None) is ModelUnits.MILLIMETERS
    assert ModelUnits.from_metadata("parsecs") is ModelUnits.MILLIMETERS
