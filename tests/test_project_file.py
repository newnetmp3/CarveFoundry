import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from carvefoundry.core.mesh import load_stl
from carvefoundry.core.primitives import rectangle_mesh
from carvefoundry.core.project import Project, ProjectItem, Stock, TextProperties
from carvefoundry.core.project_file import (
    LEGACY_PROJECT_FILE_VERSION,
    PROJECT_FILE_MAGIC,
    PROJECT_FILE_VERSION,
    ProjectFileError,
    load_project,
    project_to_dict,
    save_project,
)
from carvefoundry.core.smart_values import SmartValues
from carvefoundry.core.transform import Transform3D


def test_project_round_trip_embeds_stl_and_transform(tmp_path: Path) -> None:
    mesh_path = tmp_path / "part.stl"
    trimesh.creation.box(extents=(10.0, 20.0, 5.0)).export(mesh_path)
    asset = load_stl(mesh_path)
    transform = Transform3D(
        translation_mm=(50.0, 40.0, -2.5),
        rotation_deg=(0.0, 0.0, 90.0),
        scale_xyz=(1.25, 1.25, 1.25),
    )
    project = Project(
        name="Fixture",
        stock=Stock(width_mm=150.0, height_mm=100.0, thickness_mm=18.0),
        items=[
            ProjectItem(
                "part.stl",
                mesh_path,
                "stl",
                mesh=asset,
                transform=transform,
            )
        ],
    )
    project_path = tmp_path / "fixture.cf3d"

    saved_path = save_project(project, project_path)
    mesh_path.unlink()
    loaded = load_project(saved_path)

    assert loaded.name == "Fixture"
    assert loaded.stock == project.stock
    assert len(loaded.items) == 1
    loaded_item = loaded.items[0]
    assert loaded_item.source_path is not None
    assert loaded_item.source_path.is_file()
    assert loaded_item.source_path.name == "part.stl"
    assert loaded_item.source_path != mesh_path.resolve()
    assert loaded_item.mesh is not None
    assert np.allclose(loaded_item.mesh.dimensions, (10.0, 20.0, 5.0))
    assert loaded_item.transform.translation_mm == transform.translation_mm
    assert loaded_item.transform.rotation_deg == transform.rotation_deg
    assert loaded_item.transform.scale_xyz == transform.scale_xyz
    assert loaded_item.item_id == project.items[0].item_id


def test_saved_project_is_native_container_with_current_manifest(tmp_path: Path) -> None:
    mesh_path = tmp_path / "part.stl"
    trimesh.creation.box().export(mesh_path)
    project = Project(
        items=[ProjectItem("part.stl", mesh_path, "stl", mesh=load_stl(mesh_path))]
    )
    project_path = tmp_path / "job.cf3d"

    save_project(project, project_path)
    manifest = project_to_dict(project, project_path)

    assert project_path.read_bytes().startswith(PROJECT_FILE_MAGIC)
    assert manifest["version"] == PROJECT_FILE_VERSION
    assert manifest["format"] == "CarveFoundry Project"
    assert len(manifest["assets"]) == 1
    assert manifest["items"][0]["asset_id"] in manifest["assets"]


def test_duplicate_source_assets_are_stored_once(tmp_path: Path) -> None:
    mesh_path = tmp_path / "shared.stl"
    trimesh.creation.box(extents=(4.0, 5.0, 6.0)).export(mesh_path)
    mesh = load_stl(mesh_path)
    project = Project(
        items=[
            ProjectItem("first.stl", mesh_path, "stl", mesh=mesh),
            ProjectItem("second.stl", mesh_path, "stl", mesh=mesh),
        ]
    )

    manifest = project_to_dict(project, tmp_path / "dedup.cf3d")

    assert len(manifest["assets"]) == 1
    assert manifest["items"][0]["asset_id"] == manifest["items"][1]["asset_id"]


def test_repetitive_asset_is_compressed_and_portable(tmp_path: Path) -> None:
    svg_path = tmp_path / "large.svg"
    source_bytes = (
        b"<svg xmlns='http://www.w3.org/2000/svg'>"
        + b"<path d='M0 0 L10 10 L20 0 Z'/>" * 30000
        + b"</svg>"
    )
    svg_path.write_bytes(source_bytes)
    project = Project(items=[ProjectItem("large.svg", svg_path, "svg")])
    project_path = tmp_path / "compressed.cf3d"

    save_project(project, project_path)

    assert project_path.stat().st_size < len(source_bytes) // 10

    svg_path.unlink()
    loaded = load_project(project_path)
    loaded_path = loaded.items[0].source_path

    assert loaded_path is not None
    assert loaded_path.read_bytes() == source_bytes


def test_save_adds_project_suffix(tmp_path: Path) -> None:
    saved = save_project(Project(), tmp_path / "untitled")

    assert saved.name == "untitled.cf3d"
    assert saved.is_file()
    assert saved.read_bytes().startswith(PROJECT_FILE_MAGIC)


def test_legacy_missing_stl_is_reported_when_loading(tmp_path: Path) -> None:
    payload = {
        "version": LEGACY_PROJECT_FILE_VERSION,
        "name": "Missing",
        "stock": {"width_mm": 100, "height_mm": 80, "thickness_mm": 18},
        "items": [
            {
                "name": "gone.stl",
                "source_path": "gone.stl",
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
    path = tmp_path / "missing.cf3d"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectFileError, match="missing"):
        load_project(path)


def test_invalid_legacy_project_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future.cf3d"
    path.write_text(
        json.dumps({"version": 999, "name": "Future", "stock": {}, "items": []}),
        encoding="utf-8",
    )

    with pytest.raises(ProjectFileError, match="Unsupported project version"):
        load_project(path)


def test_generated_mesh_and_group_round_trip(tmp_path: Path) -> None:
    generated = rectangle_mesh(25.0, 15.0, 2.0)
    project = Project(
        items=[
            ProjectItem(
                "Rectangle",
                kind="rectangle",
                mesh=generated,
                group_id="group-1",
            )
        ]
    )

    path = save_project(project, tmp_path / "generated.cf3d")
    loaded = load_project(path)

    assert len(loaded.items) == 1
    item = loaded.items[0]
    assert item.kind == "rectangle"
    assert item.group_id == "group-1"
    assert item.mesh is not None
    assert np.allclose(item.mesh.dimensions, (25.0, 15.0, 2.0))



def test_editable_text_properties_round_trip(tmp_path: Path) -> None:
    properties = TextProperties(
        content="Chief\nPetty Officer",
        font_family="DejaVu Sans",
        font_style="Bold",
        size_pt=42.5,
        bold=True,
        italic=True,
        underline=True,
        strikeout=True,
        alignment="center",
        character_spacing_mm=0.35,
        word_spacing_mm=0.6,
        kerning=False,
        line_spacing_percent=125.0,
        horizontal_scale_percent=90.0,
        wrap_to_width=True,
        box_width_mm=88.0,
        depth_mm=2.5,
        geometry_mode="outline",
        outline_width_mm=0.7,
        case_mode="uppercase",
    )
    project = Project(
        items=[
            ProjectItem(
                "Title",
                kind="text",
                mesh=rectangle_mesh(20.0, 10.0, 1.0),
                text_properties=properties,
            )
        ]
    )

    path = save_project(project, tmp_path / "text.cf3d")
    loaded = load_project(path)

    assert loaded.items[0].text_properties == properties


def test_smart_values_bindings_and_center_work_zero_round_trip(tmp_path: Path) -> None:
    project = Project(
        stock=Stock(
            width_mm=220.0,
            height_mm=140.0,
            thickness_mm=19.0,
            xy_zero="center",
        ),
        items=[
            ProjectItem(
                "Parametric rectangle",
                kind="rectangle",
                mesh=rectangle_mesh(30.0, 20.0, 2.0),
                smart_bindings={
                    "size_x": "width",
                    "position_x": "stock_width / 2",
                },
            )
        ],
        smart_values=SmartValues.from_lines(
            "width = 75\nmargin = 8\ninside = width - 2 * margin"
        ),
    )

    path = save_project(project, tmp_path / "smart.cf3d")
    loaded = load_project(path)

    assert loaded.stock.xy_zero == "center"
    assert loaded.smart_values.resolve("inside") == pytest.approx(59.0)
    assert loaded.items[0].smart_bindings == project.items[0].smart_bindings
