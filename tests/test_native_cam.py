import numpy as np
import trimesh

from carvefoundry.cam.contact import compensate_height_field
from carvefoundry.cam.heightfield import HeightField
from carvefoundry.cam.native import backend_name, native_available
from carvefoundry.core.tools import Cutter, ToolType


def test_native_extension_is_packaged() -> None:
    assert native_available()


def test_backend_can_be_forced_for_debugging(monkeypatch) -> None:
    monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", "python")
    assert backend_name() == "python"

    monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", "rust")
    assert backend_name() == "rust"


def test_rust_heightfield_matches_python_reference(monkeypatch) -> None:
    lower = trimesh.creation.box(extents=(8.0, 6.0, 1.5))
    upper = trimesh.creation.icosphere(subdivisions=2, radius=2.0)
    upper.apply_translation((0.5, -0.25, 1.5))
    mesh = trimesh.util.concatenate((lower, upper))

    monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", "python")
    python_field = HeightField.from_mesh_top_surface(
        mesh,
        spacing_mm=0.5,
        padding_mm=0.5,
    )

    monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", "rust")
    rust_field = HeightField.from_mesh_top_surface(
        mesh,
        spacing_mm=0.5,
        padding_mm=0.5,
    )

    assert np.array_equal(rust_field.x_mm, python_field.x_mm)
    assert np.array_equal(rust_field.y_mm, python_field.y_mm)
    assert np.allclose(
        rust_field.z_mm,
        python_field.z_mm,
        rtol=1e-12,
        atol=1e-12,
        equal_nan=True,
    )


def test_rust_contact_map_matches_python_reference(monkeypatch) -> None:
    x = np.linspace(-3.0, 3.0, 25)
    y = np.linspace(-2.0, 2.0, 17)
    grid_x, grid_y = np.meshgrid(x, y)
    z = 1.5 * np.exp(-0.45 * (grid_x * grid_x + grid_y * grid_y))
    z[2:4, 6:8] = np.nan
    surface = HeightField(x, y, z)
    cutter = Cutter("3 mm ball", ToolType.BALL_NOSE, 3.0)

    monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", "python")
    python_contact = compensate_height_field(surface, cutter)

    monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", "rust")
    rust_contact = compensate_height_field(surface, cutter)

    assert np.allclose(
        rust_contact.tip_z_mm,
        python_contact.tip_z_mm,
        rtol=1e-12,
        atol=1e-12,
        equal_nan=True,
    )


def test_rust_contact_map_matches_v_bit_reference(monkeypatch) -> None:
    z = np.zeros((15, 15), dtype=float)
    z[7, 7] = 4.0
    surface = HeightField(
        np.arange(15, dtype=float) * 0.5,
        np.arange(15, dtype=float) * 0.5,
        z,
    )
    cutter = Cutter(
        "60 degree V",
        ToolType.V_BIT,
        6.0,
        angle_deg=60.0,
        tip_diameter_mm=0.2,
    )

    monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", "python")
    python_contact = compensate_height_field(surface, cutter)

    monkeypatch.setenv("CARVEFOUNDRY_CAM_BACKEND", "rust")
    rust_contact = compensate_height_field(surface, cutter)

    assert np.allclose(
        rust_contact.tip_z_mm,
        python_contact.tip_z_mm,
        rtol=1e-12,
        atol=1e-12,
        equal_nan=True,
    )
