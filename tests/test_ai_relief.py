from __future__ import annotations

import numpy as np
import pytest
import trimesh

from carvefoundry.core.ai_relief import ReliefRequest, generate_relief, mesh_from_depth


def _test_depth(rows=13, cols=17):
    yy, xx = np.mgrid[:rows, :cols]
    return (xx * 0.12 + yy * 0.21 + np.sin(xx * 0.4)).astype(np.float32)


@pytest.mark.parametrize("invert", [False, True])
@pytest.mark.parametrize("smoothing", [0.0, 0.6])
def test_depth_map_produces_watertight_positive_volume_stl(invert, smoothing):
    depth = _test_depth()
    mesh = mesh_from_depth(
        depth, width_mm=110, height_mm=90, relief_depth_mm=4,
        backing_thickness_mm=1.5, invert_depth=invert,
        smoothing_px=smoothing,
    )
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.volume > 0
    assert np.allclose(mesh.bounds[0], [0, 0, 0])
    assert np.allclose(mesh.bounds[1], [110, 90, mesh.bounds[1, 2]])
    assert 1.5 < mesh.bounds[1, 2] <= 5.5 + 1e-4
    assert mesh.metadata["units"] == "mm"
    # The solid's visible upper face is above the backing.
    assert np.all(mesh.vertices[:depth.size, 2] >= 1.5 - 1e-4)
    assert np.all(mesh.vertices[depth.size:, 2] == 0)


def test_depth_is_relative_and_inversion_changes_front_back():
    depth = np.arange(36, dtype=np.float32).reshape(6, 6)
    normal = mesh_from_depth(
        depth, width_mm=30, height_mm=30, relief_depth_mm=3,
        backing_thickness_mm=1,
    )
    inverted = mesh_from_depth(
        depth, width_mm=30, height_mm=30, relief_depth_mm=3,
        backing_thickness_mm=1, invert_depth=True,
    )
    assert normal.vertices[0, 2] < normal.vertices[35, 2]
    assert inverted.vertices[0, 2] > inverted.vertices[35, 2]


@pytest.mark.parametrize(
    "depth",
    [
        np.ones((10, 10), dtype=np.float32),
        np.array([[1, np.nan], [2, 3]], dtype=np.float32),
        np.zeros((1, 10), dtype=np.float32),
    ],
)
def test_bad_depth_is_rejected(depth):
    with pytest.raises(ValueError):
        mesh_from_depth(
            depth, width_mm=20, height_mm=20,
            relief_depth_mm=2, backing_thickness_mm=1,
        )


def test_request_requires_exclusive_source_and_safe_stl_destination(tmp_path):
    base = dict(
        output_path=str(tmp_path / "relief.stl"), width_mm=80, height_mm=50
    )
    with pytest.raises(ValueError, match="exactly one"):
        ReliefRequest(**base).validate()
    with pytest.raises(ValueError, match="exactly one"):
        ReliefRequest(**base, prompt="A goat", image_path="missing.png").validate()
    ReliefRequest(**base, prompt="A goat").validate()
    with pytest.raises(ValueError, match="Grid samples"):
        ReliefRequest(**base, prompt="A goat", grid_samples=4000).validate()
    with pytest.raises(ValueError, match="Output"):
        ReliefRequest(**(base | {"output_path": str(tmp_path / "relief.nc")}),
                      prompt="A goat").validate()


def test_local_generation_writes_real_importable_stl_without_model_download(
    tmp_path, monkeypatch,
):
    pil = pytest.importorskip("PIL.Image")
    from carvefoundry.core import ai_relief

    image_path = tmp_path / "reference.png"
    pil.new("RGB", (32, 24), (128, 128, 128)).save(image_path)
    monkeypatch.setattr(ai_relief, "_estimate_depth", lambda image, report: _test_depth())
    destination = tmp_path / "carve.stl"
    updates = []
    result = generate_relief(
        ReliefRequest(
            output_path=str(destination), image_path=str(image_path),
            width_mm=70, height_mm=50, relief_depth_mm=4,
            backing_thickness_mm=1, grid_samples=32,
        ),
        lambda fraction, message: updates.append((fraction, message)),
    )
    assert result["path"] == str(destination)
    assert result["faces"] > 0
    assert destination.stat().st_size > 84  # binary STL header and triangles
    mesh = trimesh.load(destination, process=False)
    assert isinstance(mesh, trimesh.Trimesh)
    assert mesh.is_watertight
    assert np.allclose(mesh.extents[:2], (70, 50))
    assert updates[-1][0] == pytest.approx(0.96)
    assert not list(tmp_path.glob("*.tmp"))


def test_failed_depth_generation_never_creates_stl(tmp_path, monkeypatch):
    pil = pytest.importorskip("PIL.Image")
    from carvefoundry.core import ai_relief

    image_path = tmp_path / "reference.png"
    pil.new("RGB", (16, 16)).save(image_path)
    monkeypatch.setattr(
        ai_relief, "_estimate_depth",
        lambda image, report: np.ones((16, 16), dtype=np.float32),
    )
    output = tmp_path / "never.stl"
    with pytest.raises(ValueError, match="flat"):
        generate_relief(
            ReliefRequest(
                output_path=str(output), image_path=str(image_path),
                width_mm=30, height_mm=30,
            ),
            lambda fraction, message: None,
        )
    assert not output.exists()


def test_ai_relief_dialog_and_shared_model_action_do_not_load_models():
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication
    from carvefoundry.ui.ai_relief import build_ai_relief_dialog
    from carvefoundry.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        action = window._ui_actions["ai_relief"]
        assert "AI Bas-Relief" in action.text()
        assert action in window.main_menu_bar.actions()[4].menu().actions()
        dialog, fields = build_ai_relief_dialog(
            window, width_mm=300, height_mm=200, thickness_mm=19.4,
        )
        assert fields["width"].value() == 280
        assert fields["height"].value() == 180
        assert fields["source"].currentData() == "image"
        fields["source"].setCurrentIndex(1)
        assert fields["source"].currentData() == "prompt"
        dialog.close()
    finally:
        window.close()
