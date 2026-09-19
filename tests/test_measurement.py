"""Planar measurement geometry for the Measure viewport tool."""
import pytest

from carvefoundry.core.measurement import measure_xy


def test_xy_distance_and_signed_angle() -> None:
    measure = measure_xy((10.0, 20.0), (40.0, 60.0))
    assert measure.distance_mm == pytest.approx(50.0)
    assert measure.delta_x_mm == pytest.approx(30.0)
    assert measure.delta_y_mm == pytest.approx(40.0)
    assert measure.angle_deg == pytest.approx(53.130102354)
    assert "Length 50.000 mm" in measure.label


def test_vertical_negative_angle_and_zero_length() -> None:
    down = measure_xy((4.0, 12.0), (4.0, 2.0))
    assert down.distance_mm == pytest.approx(10.0)
    assert down.angle_deg == pytest.approx(-90.0)
    zero = measure_xy((1.0, 1.0), (1.0, 1.0))
    assert zero.distance_mm == 0.0
    assert zero.angle_deg == 0.0


def test_nonfinite_measurement_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        measure_xy((0.0, 0.0), (float("nan"), 1.0))
