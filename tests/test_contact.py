import numpy as np
import pytest

from carvefoundry.cam.contact import compensate_height_field
from carvefoundry.cam.heightfield import HeightField
from carvefoundry.core.tools import Cutter, ToolType


def _field(z: np.ndarray) -> HeightField:
    size_y, size_x = z.shape
    return HeightField(
        np.arange(size_x, dtype=float),
        np.arange(size_y, dtype=float),
        z.astype(float),
    )


def test_flat_end_mill_requires_local_maximum_under_footprint() -> None:
    z = np.zeros((5, 5), dtype=float)
    z[2, 2] = 1.0
    cutter = Cutter("2 mm flat", ToolType.FLAT_END_MILL, 2.0)

    contact = compensate_height_field(_field(z), cutter)

    assert contact.tip_z_mm[2, 2] == pytest.approx(1.0)
    assert contact.tip_z_mm[2, 1] == pytest.approx(1.0)
    assert contact.tip_z_mm[1, 2] == pytest.approx(1.0)
    assert contact.tip_z_mm[1, 1] == pytest.approx(0.0)


def test_ball_nose_uses_curved_profile_instead_of_flat_assumption() -> None:
    z = np.zeros((5, 5), dtype=float)
    z[2, 2] = 1.0
    cutter = Cutter("2 mm ball", ToolType.BALL_NOSE, 2.0)

    contact = compensate_height_field(_field(z), cutter)

    assert contact.tip_z_mm[2, 2] == pytest.approx(1.0)
    assert contact.tip_z_mm[2, 1] == pytest.approx(0.0)
    assert contact.tip_z_mm[1, 2] == pytest.approx(0.0)


def test_v_bit_contact_map_uses_conical_profile() -> None:
    z = np.zeros((7, 7), dtype=float)
    z[3, 3] = 2.0
    cutter = Cutter("90 degree V", ToolType.V_BIT, 4.0, angle_deg=90.0)

    contact = compensate_height_field(_field(z), cutter)

    assert contact.tip_z_mm[3, 3] == pytest.approx(2.0)
    assert contact.tip_z_mm[3, 2] == pytest.approx(1.0)
    assert contact.tip_z_mm[3, 1] == pytest.approx(0.0)


def test_invalid_custom_profile_is_not_silently_treated_as_ball_nose() -> None:
    z = np.zeros((3, 3), dtype=float)
    cutter = Cutter("Custom", ToolType.CUSTOM, 2.0)

    with pytest.raises(NotImplementedError, match="custom cutter"):
        compensate_height_field(_field(z), cutter)
