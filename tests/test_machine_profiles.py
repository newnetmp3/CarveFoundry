import pytest

from carvefoundry.core.machine_profiles import (
    MachineProfile,
    profiles_from_json,
    profiles_to_json,
)


def test_machine_profiles_round_trip() -> None:
    profile = MachineProfile(
        name="Woodworker",
        port="/dev/ttyUSB0",
        work_x_mm=816.0,
        work_y_mm=816.0,
        work_z_mm=133.0,
        parking_enabled=True,
        park_x_mm=10.0,
        park_y_mm=800.0,
        park_z_mm=15.0,
    )

    text = profiles_to_json([profile], active_name=profile.name)
    loaded, active = profiles_from_json(text)

    assert loaded == [profile]
    assert active == "Woodworker"


def test_negative_parking_z_is_rejected() -> None:
    with pytest.raises(ValueError, match="Parking Z"):
        MachineProfile(park_z_mm=-1.0).validate()
