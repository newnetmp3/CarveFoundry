import numpy as np

from carvefoundry.cam.render_geometry import build_render_geometry
from carvefoundry.cam.toolpath import MoveKind, Toolpath, ToolpathMove
from carvefoundry.core.tools import Cutter, ToolType


def test_build_preview_geometry_preserves_full_path_and_rapid_partition() -> None:
    cutter = Cutter("Flat", ToolType.FLAT_END_MILL, 3.0)
    toolpath = Toolpath(
        "Test",
        "profile",
        cutter,
        2.0,
        [
            ToolpathMove(0, 0, 2, MoveKind.RAPID),
            ToolpathMove(0, 0, -1, MoveKind.PLUNGE, 100),
            ToolpathMove(10, 0, -1, MoveKind.CUT, 500),
            ToolpathMove(10, 0, 2, MoveKind.RAPID),
            ToolpathMove(20, 0, 2, MoveKind.RAPID),
        ],
    )

    result = build_render_geometry([toolpath], segment_budget=2)

    assert result["segment_count"] == 4
    assert len(result["cut_vertices"]) == 4
    assert len(result["rapid_vertices"]) == 4
    assert len(result["points"]) == 5
    assert result["lod_stride"] == 2
    assert len(result["cut_lod_vertices"]) == 2
    assert len(result["rapid_lod_vertices"]) == 2
    assert np.allclose(result["bounds"], [[0, 0, -1], [20, 0, 2]])
    assert result["rapid_prefix"].tolist() == [0, 0, 0, 1, 2]
