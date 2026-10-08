from __future__ import annotations

import pytest

from carvefoundry.core.project import ProjectItem
from carvefoundry.core.vector_path import VectorPath, VectorSegment
from carvefoundry.core.vector_snapping import nearest_vector_snap, vector_snap_candidates


def _item(name: str, path: VectorPath) -> ProjectItem:
    return ProjectItem(name, kind="pen", mesh=path.mesh_asset(), vector_path=path)


def test_snap_prefers_intersection_over_midpoints_at_same_location() -> None:
    horizontal = _item("H", VectorPath(((0, 5), (10, 5))))
    vertical = _item("V", VectorPath(((5, 0), (5, 10))))

    result = nearest_vector_snap(
        [horizontal, vertical],
        (5.1, 5.1),
        0.5,
    )

    assert result is not None
    assert result.kind == "intersection"
    assert result.point_xy == pytest.approx((5.0, 5.0))


def test_snap_finds_arc_center_and_endpoint() -> None:
    arc = _item(
        "Arc",
        VectorPath(
            ((0, 0), (10, 0)),
            segments=(VectorSegment.arc(180.0),),
        ),
    )

    center = nearest_vector_snap([arc], (5.05, 0.02), 0.2)
    assert center is not None
    assert center.kind == "center"
    assert center.point_xy == pytest.approx((5.0, 0.0))

    endpoint = nearest_vector_snap([arc], (9.95, 0.02), 0.2)
    assert endpoint is not None
    assert endpoint.kind == "node"
    assert endpoint.node_index == 1


def test_snap_excludes_actively_dragged_node_but_keeps_other_nodes() -> None:
    path = _item("Line", VectorPath(((0, 0), (10, 0), (20, 0))))

    near_first = vector_snap_candidates(
        [path],
        (0.05, 0.0),
        0.2,
        exclude_item_id=path.item_id,
        exclude_node_index=0,
    )
    assert not any(
        candidate.kind == "node" and candidate.node_index == 0
        for candidate in near_first
    )

    near_second = nearest_vector_snap(
        [path],
        (10.05, 0.0),
        0.2,
        exclude_item_id=path.item_id,
        exclude_node_index=0,
    )
    assert near_second is not None
    assert near_second.kind == "node"
    assert near_second.node_index == 1


@pytest.mark.parametrize("tolerance", [0.0, -1.0, float("inf")])
def test_snap_rejects_invalid_tolerance(tolerance: float) -> None:
    path = _item("Line", VectorPath(((0, 0), (10, 0))))
    with pytest.raises(ValueError):
        vector_snap_candidates([path], (0.0, 0.0), tolerance)
