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
    VectorSegment,
    apply_vector_edit,
    arc_center,
    arc_sweep_degrees,
    close_path,
    extend_open_line_endpoint,
    insert_node,
    join_paths,
    move_cubic_control,
    move_node,
    node_world_points,
    open_path_at_node,
    remove_node,
    sampled_points_xy,
    segment_point,
    set_segment,
    split_path_at_node,
    trim_open_endpoint,
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


def test_arc_segment_is_analytic_and_splits_without_changing_shape():
    source = VectorPath(
        ((0, 0), (10, 0)),
        segments=(VectorSegment.arc(180.0),),
    )
    source.validate()
    assert arc_center(source, 0) == pytest.approx((5.0, 0.0))
    assert arc_sweep_degrees(source, 0) == pytest.approx(180.0)
    midpoint = segment_point(source, 0, 0.5)
    assert midpoint == pytest.approx((5.0, -5.0))
    samples = sampled_points_xy(source, tolerance_mm=0.01)
    assert samples[0] == pytest.approx((0.0, 0.0))
    assert samples[-1] == pytest.approx((10.0, 0.0))
    assert min(point[1] for point in samples) == pytest.approx(-5.0, abs=0.01)

    split = insert_node(source, 0)
    assert len(split.points_xy) == 3
    assert split.points_xy[1] == pytest.approx(midpoint)
    assert split.segment_count == 2
    assert all(segment.kind == "arc" for segment in split.resolved_segments())
    assert sum(
        arc_sweep_degrees(split, index)
        for index in range(split.segment_count)
    ) == pytest.approx(180.0)


def test_cubic_bezier_sampling_and_exact_midpoint_split():
    source = VectorPath(
        ((0, 0), (12, 0)),
        segments=(VectorSegment.cubic((2, 8), (10, 8)),),
    )
    midpoint = segment_point(source, 0, 0.5)
    assert midpoint == pytest.approx((6.0, 6.0))
    samples = sampled_points_xy(source, tolerance_mm=0.01)
    assert max(point[1] for point in samples) == pytest.approx(6.0, abs=0.02)

    split = insert_node(source, 0)
    assert split.points_xy[1] == pytest.approx(midpoint)
    assert [segment.kind for segment in split.resolved_segments()] == [
        "cubic",
        "cubic",
    ]
    with pytest.raises(ValueError, match="Convert adjacent curve"):
        remove_node(split, 1)


def test_all_line_paths_remain_legacy_canonical_after_insert_delete():
    source = VectorPath(((0, 0), (10, 0), (20, 0)))
    inserted = insert_node(source, 0)
    assert inserted.segments is None
    restored = remove_node(inserted, 1)
    assert restored == source
    assert restored.segments is None


def test_set_segment_back_to_lines_recovers_compact_legacy_form():
    source = VectorPath(
        ((0, 0), (10, 0)),
        segments=(VectorSegment.arc(90.0),),
    )
    changed = set_segment(source, 0, VectorSegment.line())
    assert changed.segments is None
    assert changed == VectorPath(((0, 0), (10, 0)))


def test_native_project_preserves_arc_and_bezier_segments(tmp_path):
    path = VectorPath(
        ((0, 0), (10, 0), (20, 0)),
        width_mm=1.25,
        depth_mm=2.5,
        segments=(
            VectorSegment.arc(-90.0),
            VectorSegment.cubic((12, 5), (18, 5)),
        ),
    )
    item = ProjectItem("Curves", kind="pen", mesh=path.mesh_asset(), vector_path=path)
    filename = save_project(Project(items=[item]), tmp_path / "curves.cf3d")
    loaded = load_project(filename).items[0].vector_path
    assert loaded == path
    assert loaded.resolved_segments()[0].kind == "arc"
    assert loaded.resolved_segments()[1].kind == "cubic"



def test_close_and_open_contour_preserve_analytic_segments():
    source = VectorPath(
        ((0, 0), (10, 0), (10, 10)),
        segments=(
            VectorSegment.arc(90.0),
            VectorSegment.cubic((12, 3), (12, 7)),
        ),
    )
    closed = close_path(source)
    assert closed.closed
    assert closed.segment_count == 3
    assert [segment.kind for segment in closed.resolved_segments()] == [
        "arc", "cubic", "line",
    ]

    opened = open_path_at_node(closed, 1)
    assert not opened.closed
    assert opened.points_xy == ((10, 0), (10, 10), (0, 0))
    assert [segment.kind for segment in opened.resolved_segments()] == [
        "cubic", "line",
    ]


def test_split_open_path_preserves_curve_geometry_on_both_sides():
    source = VectorPath(
        ((0, 0), (10, 0), (20, 0), (30, 0)),
        segments=(
            VectorSegment.arc(90.0),
            VectorSegment.cubic((12, 5), (18, 5)),
            VectorSegment.line(),
        ),
    )
    left, right = split_path_at_node(source, 2)

    assert left.points_xy == ((0, 0), (10, 0), (20, 0))
    assert right.points_xy == ((20, 0), (30, 0))
    assert [segment.kind for segment in left.resolved_segments()] == [
        "arc", "cubic",
    ]
    assert [segment.kind for segment in right.resolved_segments()] == ["line"]


def test_join_paths_orients_endpoints_and_keeps_curves_analytic():
    first = VectorPath(
        ((0, 0), (10, 0)),
        width_mm=1.5,
        depth_mm=2.0,
        segments=(VectorSegment.arc(90.0),),
    )
    second = VectorPath(
        ((20, 0), (10, 0)),
        width_mm=1.5,
        depth_mm=2.0,
        segments=(VectorSegment.cubic((18, 4), (12, 4)),),
    )

    joined = join_paths(
        first,
        second,
        first_endpoint="end",
        second_endpoint="end",
        max_gap_mm=0.01,
    )

    assert joined.points_xy == ((0, 0), (10, 0), (20, 0))
    segments = joined.resolved_segments()
    assert [segment.kind for segment in segments] == ["arc", "cubic"]
    assert segments[1].control1_xy == pytest.approx((12, 4))
    assert segments[1].control2_xy == pytest.approx((18, 4))


def test_join_paths_rejects_far_or_incompatible_geometry():
    first = VectorPath(((0, 0), (10, 0)), width_mm=1.0, depth_mm=1.0)
    far = VectorPath(((20, 0), (30, 0)), width_mm=1.0, depth_mm=1.0)
    with pytest.raises(ValueError, match="beyond"):
        join_paths(first, far, max_gap_mm=2.0)

    different = VectorPath(((10, 0), (20, 0)), width_mm=2.0, depth_mm=1.0)
    with pytest.raises(ValueError, match="same stroke width"):
        join_paths(first, different)


def test_move_cubic_handle_preserves_other_control_and_anchors():
    source = VectorPath(
        ((0, 0), (12, 0)),
        segments=(VectorSegment.cubic((2, 8), (10, 8)),),
    )
    changed = move_cubic_control(source, 0, 1, (3, 12))
    assert source.resolved_segments()[0].control1_xy == (2, 8)
    assert changed.points_xy == source.points_xy
    assert changed.resolved_segments()[0].control1_xy == (3, 12)
    assert changed.resolved_segments()[0].control2_xy == (10, 8)
    assert segment_point(changed, 0, 0.5) != segment_point(source, 0, 0.5)

    second = move_cubic_control(changed, 0, 2, (9, -4))
    assert second.resolved_segments()[0].control1_xy == (3, 12)
    assert second.resolved_segments()[0].control2_xy == (9, -4)


def test_move_cubic_handle_rejects_invalid_indices_and_coordinates():
    source = VectorPath(
        ((0, 0), (10, 0)),
        segments=(VectorSegment.cubic((2, 3), (8, 3)),),
    )
    with pytest.raises(IndexError):
        move_cubic_control(source, 1, 1, (4, 4))
    with pytest.raises(ValueError, match="index"):
        move_cubic_control(source, 0, 0, (4, 4))
    with pytest.raises(ValueError, match="finite"):
        move_cubic_control(source, 0, 2, (float("nan"), 4))
    with pytest.raises(ValueError, match="Only cubic"):
        move_cubic_control(VectorPath(((0, 0), (10, 0))), 0, 1, (4, 4))


def test_move_cubic_handle_roundtrips_project_and_history(tmp_path):
    source = VectorPath(
        ((0, 0), (12, 0)),
        segments=(VectorSegment.cubic((2, 8), (10, 8)),),
    )
    item = ProjectItem("Curve", kind="pen", mesh=source.mesh_asset(), vector_path=source)
    project = Project(items=[item])
    snapshot = capture_workspace(project)
    edited = move_cubic_control(source, 0, 2, (10, 12))
    apply_vector_edit(item, edited)
    assert load_project(save_project(project, tmp_path / "handles.cf3d")).items[0].vector_path == edited
    restore_workspace(project, snapshot)
    assert project.items[0].vector_path == source


@pytest.mark.parametrize("kind", ["line", "arc", "cubic"])
@pytest.mark.parametrize("at_start", [True, False])
def test_endpoint_trim_preserves_analytic_segment_and_original_subcurve(
    kind: str, at_start: bool,
) -> None:
    segment = {
        "line": VectorSegment.line(),
        "arc": VectorSegment.arc(120.0),
        "cubic": VectorSegment.cubic((3, 8), (7, -3)),
    }[kind]
    original = VectorPath(((0, 0), (10, 0)), segments=(segment,))
    fraction = 0.35
    trimmed = trim_open_endpoint(
        original, at_start=at_start, fraction=fraction,
    )
    assert trimmed.resolved_segments()[0].kind == kind
    assert trimmed.points_xy[0 if at_start else 1] == pytest.approx(
        segment_point(original, 0, fraction)
    )
    assert trimmed.points_xy[1 if at_start else 0] == original.points_xy[
        1 if at_start else 0
    ]
    for index in range(11):
        t = index / 10.0
        source_t = fraction + (1 - fraction) * t if at_start else fraction * t
        assert segment_point(trimmed, 0, t) == pytest.approx(
            segment_point(original, 0, source_t), abs=1e-7,
        )


def test_endpoint_trim_keeps_unedited_segments_and_refuses_closed_path() -> None:
    original = VectorPath(
        ((0, 0), (10, 0), (20, 5)),
        segments=(VectorSegment.line(), VectorSegment.cubic((12, 4), (18, 8))),
    )
    edited = trim_open_endpoint(original, at_start=True, fraction=0.4)
    assert edited.resolved_segments()[1] == original.resolved_segments()[1]
    assert edited.points_xy[-1] == original.points_xy[-1]
    closed = VectorPath(
        ((0, 0), (10, 0), (10, 10)), closed=True,
    )
    with pytest.raises(ValueError):
        trim_open_endpoint(closed, at_start=True, fraction=0.5)


@pytest.mark.parametrize("fraction", [0, 1, -0.1, 1.1, float("nan"), float("inf")])
def test_endpoint_trim_rejects_invalid_fraction(fraction: float) -> None:
    with pytest.raises(ValueError):
        trim_open_endpoint(
            VectorPath(((0, 0), (10, 0))),
            at_start=True, fraction=fraction,
        )


def test_trimmed_analytic_curve_roundtrips_and_history_restores(tmp_path) -> None:
    original = VectorPath(
        ((0, 0), (10, 0)),
        segments=(VectorSegment.cubic((2, 8), (8, -5)),),
    )
    item = ProjectItem("Trim", kind="pen", mesh=original.mesh_asset(), vector_path=original)
    project = Project(items=[item])
    snapshot = capture_workspace(project)
    changed = trim_open_endpoint(original, at_start=True, fraction=0.4)
    apply_vector_edit(item, changed)
    saved = save_project(project, tmp_path / "trimmed-curve.cf3d")
    assert load_project(saved).items[0].vector_path == changed
    restore_workspace(project, snapshot)
    assert project.items[0].vector_path == original


@pytest.mark.parametrize("at_start", [True, False])
def test_extend_line_endpoint_preserves_other_segments(at_start: bool) -> None:
    path = VectorPath(
        ((0, 0), (10, 0), (20, 10)),
        segments=(VectorSegment.line(), VectorSegment.line()),
    )
    extended = extend_open_line_endpoint(path, at_start=at_start, distance_mm=5)
    assert extended.segment_count == path.segment_count
    assert extended.resolved_segments() == path.resolved_segments()
    if at_start:
        assert extended.points_xy[0] == pytest.approx((-5, 0))
        assert extended.points_xy[1:] == path.points_xy[1:]
    else:
        diagonal = 5 / np.sqrt(2)
        assert extended.points_xy[-1] == pytest.approx(
            (20 + diagonal, 10 + diagonal)
        )
        assert extended.points_xy[:-1] == path.points_xy[:-1]


@pytest.mark.parametrize("amount", [0.0, -1.0, float("inf"), float("nan")])
def test_extend_line_endpoint_rejects_invalid_distance(amount: float) -> None:
    path = VectorPath(((0, 0), (10, 0)))
    with pytest.raises(ValueError):
        extend_open_line_endpoint(path, at_start=True, distance_mm=amount)


def test_extend_line_endpoint_rejects_closed_and_curved_ends() -> None:
    closed = VectorPath(((0, 0), (10, 0), (10, 10)), closed=True)
    with pytest.raises(ValueError, match="Open"):
        extend_open_line_endpoint(closed, at_start=True, distance_mm=1)
    cubic = VectorPath(
        ((0, 0), (10, 0)), segments=(VectorSegment.cubic((2, 4), (8, 4)),),
    )
    with pytest.raises(ValueError, match="straight"):
        extend_open_line_endpoint(cubic, at_start=False, distance_mm=1)
