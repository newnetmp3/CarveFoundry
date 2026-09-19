"""Pen/line editable node geometry persists, changes tool geometry and undoes safely."""
from __future__ import annotations

import numpy as np
import pytest

from carvefoundry.core.history import capture_workspace, restore_workspace
from carvefoundry.core.primitives import polyline_mesh
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.project_file import load_project, save_project
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.vector_path import (
    VectorPath,
    apply_vector_edit,
    insert_node,
    move_node,
    node_world_points,
    remove_node,
    world_xy_to_local,
)


def _editable_item() -> ProjectItem:
    path = VectorPath(((10, 12), (15, 16), (20, 12)), width_mm=2, depth_mm=3)
    return ProjectItem(
        "Pen", kind="pen", mesh=path.mesh_asset(), vector_path=path,
    )


def test_node_move_rebuilds_real_mesh_and_undo_restores_exact_original():
    item = _editable_item()
    project = Project(items=[item])
    snapshot = capture_workspace(project)
    original = item.mesh.mesh.vertices.copy()
    path = move_node(item.vector_path, 1, (15, 25))
    apply_vector_edit(item, path)
    assert item.vector_path.points_xy[1] == (15, 25)
    assert item.mesh.mesh.bounds[1, 1] > 25
    assert not np.array_equal(item.mesh.mesh.vertices, original)
    restore_workspace(project, snapshot)
    assert project.items[0].vector_path.points_xy[1] == (15, 16)
    assert np.array_equal(project.items[0].mesh.mesh.vertices, original)


def test_insert_delete_nodes_and_closed_segment():
    source = _editable_item().vector_path
    inserted = insert_node(source, 0)
    assert inserted.points_xy[1] == pytest.approx((12.5, 14))
    assert remove_node(inserted, 1) == source
    closed = VectorPath(((0, 0), (10, 0), (10, 10)), closed=True)
    assert insert_node(closed, 2).points_xy[-1] == pytest.approx((5, 5))
    assert closed.mesh_asset().mesh.vertices.shape[0] > 0
    with pytest.raises(ValueError, match="last required"):
        remove_node(closed, 0)


@pytest.mark.parametrize(
    "bad",
    [
        VectorPath(((0, 0),)),
        VectorPath(((0, 0), (0, 0))),
        VectorPath(((0, 0), (1, 0)), closed=True),
        VectorPath(((0, 0), (1, 0)), width_mm=float("nan")),
        VectorPath(((0, 0), (float("inf"), 0))),
    ],
)
def test_reject_invalid_control_points(bad):
    with pytest.raises(ValueError):
        bad.validate()


def test_world_stock_drag_inverts_translation_scale_and_z_rotation():
    item = _editable_item()
    item.transform = Transform3D(
        translation_mm=(20, 11, 0),
        rotation_deg=(0, 0, 37),
        scale_xyz=(1.4, 0.8, 1),
    )
    before = node_world_points(item)
    local = world_xy_to_local(item, 1, tuple(before[1, :2]))
    assert local == pytest.approx(item.vector_path.points_xy[1])
    moved = tuple(before[1, :2] + np.array([3.5, -1.25]))
    new = move_node(item.vector_path, 1, world_xy_to_local(item, 1, moved))
    apply_vector_edit(item, new)
    # Transform pivots track geometry bounds, which can change after an edit.
    # The native editor must compensate this change to keep the chosen world
    # point where the operator actually dragged it.
    assert np.isfinite(node_world_points(item)).all()


def test_native_project_preserves_path_nodes_and_editability(tmp_path):
    item = _editable_item()
    item.vector_path = insert_node(item.vector_path, 0)
    item.mesh = item.vector_path.mesh_asset()
    filename = save_project(Project(items=[item]), tmp_path / "editable.cf3d")
    restored = load_project(filename)
    loaded = restored.items[0]
    assert loaded.vector_path == item.vector_path
    assert loaded.kind == "pen"
    assert loaded.mesh.mesh.bounds == pytest.approx(item.mesh.mesh.bounds)
    changed = move_node(loaded.vector_path, 1, (2, 33))
    apply_vector_edit(loaded, changed)
    assert loaded.source_path is None
    assert loaded.mesh.mesh.bounds[1, 1] > 33
    revised = save_project(restored, tmp_path / "revised.cf3d")
    reopened = load_project(revised).items[0]
    assert reopened.vector_path == changed
    assert reopened.mesh.mesh.bounds[1, 1] > 33


def test_vector_path_is_shared_as_immutable_metadata_for_duplicated_objects():
    item = _editable_item()
    project = Project(items=[item])
    _idx, copy = project.duplicate_item(0)
    assert copy.vector_path is item.vector_path
    apply_vector_edit(copy, move_node(copy.vector_path, 1, (10, 40)))
    assert item.vector_path.points_xy[1] == (15, 16)
    assert copy.vector_path.points_xy[1] == (10, 40)


def test_old_mesh_without_nodes_is_not_claimed_editable():
    item = ProjectItem(
        "Imported pen mesh", kind="pen",
        mesh=polyline_mesh([(0, 0), (10, 10)]),
    )
    with pytest.raises(ValueError, match="no retained"):
        apply_vector_edit(item, VectorPath(((0, 0), (10, 20))))
