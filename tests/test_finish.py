import numpy as np
import pytest
import trimesh

from carvefoundry.cam.finish import Finish3DSettings, calculate_3d_finish
from carvefoundry.cam.raster import RasterFinishingSettings
from carvefoundry.cam.toolpath import MoveKind
from carvefoundry.core.tools import Cutter, ToolType


def _settings(*, spacing: float = 1.0, max_samples: int = 2_000_000) -> Finish3DSettings:
    return Finish3DSettings(
        surface_spacing_mm=spacing,
        raster=RasterFinishingSettings(
            stepover_mm=1.0,
            feed_mm_min=1200.0,
            plunge_feed_mm_min=300.0,
            safe_z_mm=5.0,
        ),
        max_surface_samples=max_samples,
    )


def test_finish_pipeline_keeps_flat_box_top_at_zero() -> None:
    mesh = trimesh.creation.box(extents=(4.0, 4.0, 2.0))
    mesh.apply_translation((0.0, 0.0, -1.0))
    cutter = Cutter("2 mm flat", ToolType.FLAT_END_MILL, 2.0)

    result = calculate_3d_finish(mesh, cutter, _settings())

    cut_z = [
        move.z_mm
        for move in result.toolpath.moves
        if move.kind in {MoveKind.PLUNGE, MoveKind.CUT}
    ]
    assert cut_z
    assert np.allclose(cut_z, 0.0)
    assert result.surface.z_mm.max() == pytest.approx(0.0)


def test_finish_pipeline_uses_selected_v_bit_geometry() -> None:
    vertices = np.array(
        [
            (-2.0, -2.0, 0.0),
            (2.0, -2.0, 0.0),
            (2.0, 2.0, 0.0),
            (-2.0, 2.0, 0.0),
            (0.0, 0.0, 2.0),
        ]
    )
    faces = np.array(
        [
            (0, 1, 4),
            (1, 2, 4),
            (2, 3, 4),
            (3, 0, 4),
            (0, 3, 2),
            (0, 2, 1),
        ]
    )
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    cutter = Cutter("90 V", ToolType.V_BIT, 4.0, angle_deg=90.0)

    result = calculate_3d_finish(mesh, cutter, _settings())

    center_y = int(np.argmin(np.abs(result.surface.y_mm)))
    center_x = int(np.argmin(np.abs(result.surface.x_mm)))
    assert result.contact.tip_z_mm[center_y, center_x] == pytest.approx(2.0)
    assert result.contact.tip_z_mm[center_y, center_x - 1] == pytest.approx(1.0)


def test_finish_pipeline_blocks_excessive_surface_grid() -> None:
    mesh = trimesh.creation.box(extents=(100.0, 100.0, 10.0))
    cutter = Cutter("flat", ToolType.FLAT_END_MILL, 2.0)

    with pytest.raises(ValueError, match="Increase surface spacing"):
        calculate_3d_finish(mesh, cutter, _settings(spacing=0.1, max_samples=10_000))
