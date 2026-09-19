"""End-to-end two-sided stock registration, serialization and safety checks."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.project_file import load_project
from carvefoundry.core.smart_values import SmartValues
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.two_sided import (
    prepare_two_sided,
    reflect_back_face,
    save_two_sided_setup,
    setup_instructions,
)


def _item(
    name: str,
    *,
    x: float,
    y: float,
    depth: float = 2.0,
) -> ProjectItem:
    return ProjectItem(
        name=name,
        kind="rectangle",
        mesh=rectangle_mesh(10.0, 6.0, depth),
        transform=Transform3D(translation_mm=(x, y, 0.0)),
    )


def _project() -> Project:
    return Project(
        name="Coin",
        stock=Stock(width_mm=100.0, height_mm=80.0, thickness_mm=19.4),
        items=[_item("Heads", x=22, y=20), _item("Tails", x=67, y=43)],
        fixtures=[Fixture("Left fence", -3, 0, -0.1, 80, 3.6)],
        smart_values=SmartValues({"depth": "2"}),
    )


@pytest.mark.parametrize("axis", ["x", "y"])
def test_reflection_preserves_depth_winding_source_and_axis(axis: str) -> None:
    project = _project()
    source = project.items[-1]
    original_vertices = source.mesh.mesh.vertices.copy()
    before = source.transformed_bounds_mm()
    before_volume = source.transformed_mesh().volume
    back = reflect_back_face(source, project.stock, axis=axis)
    after = back.transformed_bounds_mm()
    if axis == "x":
        assert after[:, 0] == pytest.approx(
            [100 - before[1, 0], 100 - before[0, 0]]
        )
        assert after[:, 1] == pytest.approx(before[:, 1])
    else:
        assert after[:, 1] == pytest.approx(
            [80 - before[1, 1], 80 - before[0, 1]]
        )
        assert after[:, 0] == pytest.approx(before[:, 0])
    assert after[:, 2] == pytest.approx(before[:, 2])
    assert back.mesh.mesh.is_watertight
    assert back.mesh.mesh.is_winding_consistent
    assert back.mesh.mesh.volume == pytest.approx(before_volume)
    assert np.array_equal(source.mesh.mesh.vertices, original_vertices)
    assert back.kind == "stl"
    assert back.source_path is None
    assert back.smart_bindings == {}


def test_both_face_projects_include_only_assigned_meshes_and_fixed_fixtures() -> None:
    project = _project()
    project.items.append(_item("Hidden prototype", x=40, y=25))
    project.items[-1].visible = False
    back_id = project.items[1].item_id
    front, back = prepare_two_sided(
        project, back_item_ids={back_id}, axis="x",
    )
    assert [i.name for i in front.items] == ["Heads"]
    assert [i.name for i in back.items] == ["Tails"]
    assert front.fixtures == back.fixtures == project.fixtures
    assert front.stock == back.stock == project.stock
    assert front.fixtures[0].x_min_mm == -3
    assert front.smart_values.expressions == {"depth": "2"}
    assert back.smart_values.expressions == {}
    assert not project.toolpaths
    assert project.items[1].kind == "rectangle"
    assert "X_back = stock_width - X_front" in setup_instructions(
        original=project, front=front, back=back, axis="x",
    )


@pytest.mark.parametrize(
    ("variant", "reason"),
    [
        ("missing_face", "at least one"),
        ("hidden", "hidden or missing"),
        ("outside_xy", "outside"),
        ("above_z0", "within stock-top"),
        ("below_stock", "within stock-top"),
        ("invalid_axis", "axis"),
        ("wrong_origin", "bottom-left"),
        ("duplicate_id", "Duplicate"),
    ],
)
def test_reject_unsafe_or_ambiguous_setups(variant: str, reason: str) -> None:
    project = _project()
    back = project.items[1]
    axis = "x"
    ids = {back.item_id}
    if variant == "missing_face":
        ids = {item.item_id for item in project.items}
    elif variant == "hidden":
        back.visible = False
    elif variant == "outside_xy":
        back.transform.translation_mm = (101, 10, 0)
    elif variant == "above_z0":
        back.transform.translation_mm = (45, 30, 1)
    elif variant == "below_stock":
        back.transform.translation_mm = (45, 30, -19)
    elif variant == "invalid_axis":
        axis = "z"
    elif variant == "wrong_origin":
        project.stock.xy_zero = "center"
    elif variant == "duplicate_id":
        project.items[0].item_id = back.item_id
    with pytest.raises(ValueError, match=reason):
        prepare_two_sided(project, back_item_ids=ids, axis=axis)


def test_create_load_two_files_and_never_overwrite_existing_setup(tmp_path) -> None:
    project = _project()
    destination = tmp_path / "Coin_two_sided"
    progress = []
    folder = save_two_sided_setup(
        project,
        back_item_ids={project.items[1].item_id},
        axis="x",
        destination=destination,
        progress=lambda f, s: progress.append((f, s)),
    )
    assert folder == destination
    assert sorted(p.name for p in folder.iterdir()) == [
        "SETUP_INSTRUCTIONS.txt", "back.cf3d", "front.cf3d",
    ]
    front = load_project(folder / "front.cf3d")
    back = load_project(folder / "back.cf3d")
    assert len(front.items) == len(back.items) == 1
    assert front.fixtures == back.fixtures == project.fixtures
    assert back.items[0].transformed_bounds_mm()[:, 0] == pytest.approx(
        [100 - project.items[1].transformed_bounds_mm()[1, 0],
         100 - project.items[1].transformed_bounds_mm()[0, 0]],
    )
    instructions = (folder / "SETUP_INSTRUCTIONS.txt").read_text()
    assert "RE-PROBE THE NEWLY EXPOSED FACE" in instructions
    assert "generate toolpaths" in instructions.lower()
    assert progress[-1][0] == 1.0
    with pytest.raises(FileExistsError):
        save_two_sided_setup(
            project, back_item_ids={project.items[1].item_id},
            axis="x", destination=destination,
        )
    assert len(list(tmp_path.iterdir())) == 1


def test_saved_back_face_does_not_regenerate_unmirrored_text_or_bindings(tmp_path) -> None:
    project = _project()
    back = project.items[1]
    back.kind = "text"
    back.smart_bindings = {"position_x": "depth * 10"}
    save_two_sided_setup(
        project, back_item_ids={back.item_id}, axis="y",
        destination=tmp_path / "turnover",
    )
    restored = load_project(tmp_path / "turnover" / "back.cf3d").items[0]
    assert restored.kind == "stl"
    assert restored.smart_bindings == {}
    assert restored.text_properties is None
    assert restored.transformed_bounds_mm()[0, 1] == pytest.approx(
        80 - back.transformed_bounds_mm()[1, 1]
    )


def test_invalid_stock_dimensions_are_rejected() -> None:
    project = _project()
    project.stock = replace(project.stock, thickness_mm=float("nan"))
    with pytest.raises(ValueError, match="positive and finite"):
        prepare_two_sided(
            project, back_item_ids={project.items[1].item_id}, axis="x",
        )
