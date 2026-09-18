import numpy as np
from PySide6.QtGui import QFontDatabase, QGuiApplication

from carvefoundry.core.primitives import text_mesh
from carvefoundry.core.project import TextProperties

_APP = QGuiApplication.instance() or QGuiApplication([])


def _test_font_family() -> str:
    families = list(QFontDatabase.families())
    assert families
    if "DejaVu Sans" in families:
        return "DejaVu Sans"
    return families[0]


def test_system_font_text_uses_real_glyph_outlines() -> None:
    properties = TextProperties(
        content="O",
        font_family=_test_font_family(),
        size_pt=48.0,
        depth_mm=2.0,
    )

    asset = text_mesh(properties=properties)
    mesh = asset.mesh
    extents = np.asarray(mesh.extents, dtype=float)

    assert mesh.is_watertight
    assert np.isclose(mesh.bounds[1, 2], 0.0)
    assert np.isclose(mesh.bounds[0, 2], -2.0)
    assert extents[0] > 0.0
    assert extents[1] > 0.0
    # Curved system-font outlines produce many distinct X positions, unlike
    # the legacy 5x7 rectangular-cell fallback.
    assert np.unique(np.round(mesh.vertices[:, 0], 3)).size > 12
    # The counter in "O" means the solid volume is materially below its
    # bounding-box volume.
    assert mesh.volume < float(np.prod(extents)) * 0.9


def test_outline_text_geometry_is_distinct_from_filled_text() -> None:
    family = _test_font_family()
    filled = text_mesh(
        properties=TextProperties(
            content="CARVE",
            font_family=family,
            size_pt=36.0,
            depth_mm=1.5,
        )
    )
    outlined = text_mesh(
        properties=TextProperties(
            content="CARVE",
            font_family=family,
            size_pt=36.0,
            depth_mm=1.5,
            geometry_mode="outline",
            outline_width_mm=0.45,
        )
    )

    assert filled.mesh.is_watertight
    assert outlined.mesh.is_watertight
    assert not np.isclose(filled.mesh.volume, outlined.mesh.volume)
