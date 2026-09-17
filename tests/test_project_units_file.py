import json
from pathlib import Path

import numpy as np
import trimesh

from carvefoundry.core.mesh import load_stl
from carvefoundry.core.project import Project, ProjectItem
from carvefoundry.core.project_file import load_project, project_to_dict, save_project
from carvefoundry.core.units import ModelUnits


def test_project_file_preserves_source_unit_assumption(tmp_path: Path) -> None:
    mesh_path = tmp_path / "inch-part.stl"
    trimesh.creation.box(extents=(1.0, 2.0, 0.5)).export(mesh_path)
    item = ProjectItem(
        "inch-part.stl",
        mesh_path,
        "stl",
        mesh=load_stl(mesh_path),
        source_units=ModelUnits.INCHES,
    )
    project = Project(items=[item])
    project_path = tmp_path / "inch-job.cf3d"

    save_project(project, project_path)
    manifest = project_to_dict(project, project_path)
    mesh_path.unlink()
    loaded = load_project(project_path)

    assert manifest["items"][0]["source_units"] == "in"
    assert loaded.items[0].source_units is ModelUnits.INCHES
    transformed = loaded.items[0].transformed_mesh()
    assert transformed is not None
    assert np.allclose(transformed.extents, (25.4, 50.8, 12.7))


def test_legacy_project_without_source_units_defaults_to_mm(tmp_path: Path) -> None:
    mesh_path = tmp_path / "part.stl"
    trimesh.creation.box(extents=(10.0, 20.0, 5.0)).export(mesh_path)
    project_path = tmp_path / "legacy.carvefoundry"
    project_path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "Legacy",
                "stock": {"width_mm": 100, "height_mm": 80, "thickness_mm": 18},
                "items": [
                    {
                        "name": "part.stl",
                        "source_path": "part.stl",
                        "kind": "stl",
                        "visible": True,
                        "transform": {
                            "translation_mm": [0, 0, 0],
                            "rotation_deg": [0, 0, 0],
                            "scale_xyz": [1, 1, 1],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_project(project_path)

    assert loaded.items[0].source_units is ModelUnits.MILLIMETERS
