import numpy as np
import pytest
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from carvefoundry.core.font_handler import describe_qt_font_face
from carvefoundry.core.primitives import text_mesh
from carvefoundry.core.project import TextProperties

_APP = QApplication.instance() or QApplication([])


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

def test_text_box_alignment_preserves_layout_origin() -> None:
    family = _test_font_family()
    common = {
        "content": "CARVE",
        "font_family": family,
        "size_pt": 36.0,
        "box_width_mm": 100.0,
        "depth_mm": 1.0,
    }

    left = text_mesh(
        properties=TextProperties(**common, alignment="left")
    ).mesh
    center = text_mesh(
        properties=TextProperties(**common, alignment="center")
    ).mesh
    right = text_mesh(
        properties=TextProperties(**common, alignment="right")
    ).mesh

    assert np.isclose(left.extents[0], center.extents[0], rtol=1e-4)
    assert np.isclose(center.extents[0], right.extents[0], rtol=1e-4)
    assert left.bounds[0, 0] < center.bounds[0, 0] < right.bounds[0, 0]


def test_character_and_line_spacing_change_text_dimensions() -> None:
    family = _test_font_family()
    tight = text_mesh(
        properties=TextProperties(
            content="CARVE",
            font_family=family,
            size_pt=36.0,
            depth_mm=1.0,
        )
    ).mesh
    spaced = text_mesh(
        properties=TextProperties(
            content="CARVE",
            font_family=family,
            size_pt=36.0,
            character_spacing_mm=1.0,
            depth_mm=1.0,
        )
    ).mesh
    normal_lines = text_mesh(
        properties=TextProperties(
            content="CARVE\nFOUNDRY",
            font_family=family,
            size_pt=36.0,
            line_spacing_percent=100.0,
            depth_mm=1.0,
        )
    ).mesh
    loose_lines = text_mesh(
        properties=TextProperties(
            content="CARVE\nFOUNDRY",
            font_family=family,
            size_pt=36.0,
            line_spacing_percent=180.0,
            depth_mm=1.0,
        )
    ).mesh

    assert spaced.extents[0] > tight.extents[0]
    assert loose_lines.extents[1] > normal_lines.extents[1]


def test_text_effects_are_part_of_cnc_geometry() -> None:
    family = _test_font_family()
    plain = text_mesh(
        properties=TextProperties(
            content="CARVE",
            font_family=family,
            size_pt=36.0,
            depth_mm=1.0,
        )
    ).mesh
    decorated = text_mesh(
        properties=TextProperties(
            content="CARVE",
            font_family=family,
            size_pt=36.0,
            underline=True,
            strikeout=True,
            depth_mm=1.0,
        )
    ).mesh

    assert decorated.is_watertight
    assert decorated.volume > plain.volume


def test_font_handler_verifies_exact_installed_face() -> None:
    family = _test_font_family()
    styles = list(QFontDatabase.styles(family))
    assert styles
    style = (
        "Regular"
        if "Regular" in styles
        else "Book"
        if "Book" in styles
        else styles[0]
    )

    face = describe_qt_font_face(family, style)

    assert face.exact
    assert face.family.casefold() == family.casefold()
    assert face.display_name


def test_font_handler_rejects_missing_family_instead_of_substituting() -> None:
    with pytest.raises(ValueError, match="not installed"):
        describe_qt_font_face(
            "CarveFoundry Definitely Missing Font 12345",
            "Regular",
        )


def test_text_mesh_refuses_silent_missing_font_substitution() -> None:
    properties = TextProperties(
        content="NAVY",
        font_family="CarveFoundry Definitely Missing Font 12345",
        font_style="Regular",
        size_pt=36.0,
        depth_mm=1.0,
    )

    with pytest.raises(ValueError, match="not installed"):
        text_mesh(properties=properties)
