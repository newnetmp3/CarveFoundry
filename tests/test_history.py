from pathlib import Path

import trimesh

from carvefoundry.core.history import capture_workspace, restore_workspace
from carvefoundry.core.mesh import load_stl
from carvefoundry.core.project import Project, ProjectItem, Stock
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.units import ModelUnits


def test_workspace_snapshot_restores_mutable_state_without_copying_mesh(tmp_path: Path) -> None:
    mesh_path = tmp_path / "part.stl"
    trimesh.creation.box(extents=(10.0, 20.0, 5.0)).export(mesh_path)
    mesh = load_stl(mesh_path)

    project = Project(
        stock=Stock(100.0, 80.0, 18.0),
        items=[
            ProjectItem(
                "part.stl",
                mesh_path,
                "stl",
                mesh=mesh,
                transform=Transform3D(
                    translation_mm=(1.0, 2.0, 3.0),
                    rotation_deg=(4.0, 5.0, 6.0),
                    scale_xyz=(1.2, 1.2, 1.2),
                ),
                source_units=ModelUnits.MILLIMETERS,
            )
        ],
    )

    snapshot = capture_workspace(project)
    original_mesh_asset = project.items[0].mesh

    project.stock.width_mm = 999.0
    project.items[0].visible = False
    project.items[0].transform.translation_mm = (50.0, 60.0, 70.0)
    project.items.clear()

    restore_workspace(project, snapshot)

    assert project.stock == Stock(100.0, 80.0, 18.0)
    assert len(project.items) == 1
    restored = project.items[0]
    assert restored.visible is True
    assert restored.transform.translation_mm == (1.0, 2.0, 3.0)
    assert restored.transform.rotation_deg == (4.0, 5.0, 6.0)
    assert restored.transform.scale_xyz == (1.2, 1.2, 1.2)
    assert restored.mesh is original_mesh_asset


def test_snapshot_does_not_capture_project_identity(tmp_path: Path) -> None:
    project = Project(name="Before")
    snapshot = capture_workspace(project)

    project.name = "Saved As"
    restore_workspace(project, snapshot)

    assert project.name == "Saved As"
