"""Production grid bounds, fixture avoidance, editable assets and validation."""
from __future__ import annotations

import numpy as np
import pytest

from carvefoundry.core.batch_layout import batch_grid
from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.transform import Transform3D


def _project():
    a = ProjectItem(
        "Anchor", kind="rectangle", mesh=rectangle_mesh(10, 8, 2),
        transform=Transform3D(translation_mm=(24, 18, 0)),
    )
    b = ProjectItem(
        "Chain", kind="rectangle", mesh=rectangle_mesh(4, 4, 1),
        transform=Transform3D(translation_mm=(32, 23, 0)),
    )
    return Project(name="Coin batch", stock=Stock(100, 80, 19.4), items=[a, b])


def test_produces_grid_in_stock_and_preserves_templates_and_editability():
    project = _project()
    original = [item.mesh.mesh.vertices.copy() for item in project.items]
    clones = batch_grid(
        project, tuple(project.items), copies=6, columns=3,
        gap_mm=5, margin_mm=8, cutter_radius_mm=3.175,
    )
    assert len(clones) == 12
    assert len({item.item_id for item in clones}) == 12
    assert clones[0].group_id == clones[1].group_id
    assert clones[0].group_id != clones[2].group_id
    assert clones[0].mesh is project.items[0].mesh
    assert clones[0].kind == "rectangle"
    assert clones[0].text_properties is None
    for item in clones:
        low, high = item.transformed_bounds_mm()
        assert low[0] >= 3.175
        assert low[1] >= 3.175
        assert high[0] <= 100 - 3.175
        assert high[1] <= 80 - 3.175
        assert high[2] <= 0
    assert np.array_equal(original[0], project.items[0].mesh.mesh.vertices)
    assert np.array_equal(original[1], project.items[1].mesh.mesh.vertices)
    assert all(item.visible for item in project.items)


@pytest.mark.parametrize(
    ("options", "reason"),
    [
        ({"copies": 0}, "Batch count"),
        ({"copies": 257}, "Batch count"),
        ({"columns": 5}, "Columns"),
        ({"gap_mm": -1}, "nonnegative"),
        ({"margin_mm": 1}, "cutter radius"),
        ({"margin_mm": 30}, "Batch needs"),
    ],
)
def test_grid_rejects_invalid_settings(options, reason):
    project = _project()
    settings = {
        "copies": 4, "columns": 2, "gap_mm": 5,
        "margin_mm": 8, "cutter_radius_mm": 3.175,
    }
    settings.update(options)
    with pytest.raises(ValueError, match=reason):
        batch_grid(project, (project.items[0],), **settings)


def test_fixture_clearance_prevents_unsafe_grid_without_partial_outputs():
    project = _project()
    project.fixtures = [Fixture("Middle clamp", 11, 10, 16, 18, 2, 2)]
    with pytest.raises(ValueError, match="fixture"):
        batch_grid(
            project, (project.items[0],),
            copies=4, columns=2, gap_mm=5, margin_mm=8,
            cutter_radius_mm=3.175,
        )
    assert len(project.items) == 2


def test_position_bound_smart_values_must_not_override_batch_offsets():
    project = _project()
    project.items[0].smart_bindings["position_x"] = "10"
    with pytest.raises(ValueError, match="Unbind X/Y"):
        batch_grid(
            project, (project.items[0],),
            copies=2, columns=1, gap_mm=5, margin_mm=8,
            cutter_radius_mm=3.175,
        )
