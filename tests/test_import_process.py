from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import trimesh

from carvefoundry.core.import_process import prepare_stl_import_payload


def test_stl_payload_can_be_prepared_in_spawned_process(tmp_path: Path) -> None:
    path = tmp_path / "part.stl"
    trimesh.creation.box(extents=(10.0, 20.0, 5.0)).export(path)

    with ProcessPoolExecutor(
        max_workers=1,
        mp_context=get_context("spawn"),
    ) as executor:
        info, vertex_bytes, vertex_count = executor.submit(
            prepare_stl_import_payload,
            path,
            "STL",
        ).result(timeout=30)

    assert info.kind == "stl"
    assert info.mesh is not None
    assert info.mesh.face_count == 12
    assert vertex_count == 36

    expanded = np.frombuffer(vertex_bytes, dtype=np.float32).reshape((-1, 3))
    assert expanded.shape == (36, 3)
    assert np.isfinite(expanded).all()
