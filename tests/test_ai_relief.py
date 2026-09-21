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
    base = {
        "output_path": str(tmp_path / "relief.stl"), "width_mm": 80, "height_mm": 50,
    }
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
    # STL stores expanded triangle corners rather than shared vertex indices.
    # Weld duplicates to verify the actual exported solid topology.
    mesh = trimesh.load(destination, process=True)
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
    assert app is not None
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


def test_prompt_mode_saves_stl_and_auto_imports_through_existing_path(tmp_path, monkeypatch):
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialogButtonBox

    from carvefoundry.ui import ai_relief
    from carvefoundry.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    assert app is not None
    window = MainWindow()
    try:
        generated_stl = tmp_path / "my-ai-relief.stl"
        original = ai_relief.build_ai_relief_dialog

        def make_dialog(*args, **kwargs):
            dialog, fields = original(*args, **kwargs)
            fields["source"].setCurrentIndex(1)
            fields["prompt"].setPlainText("An anchor with a heavy chain")
            QTimer.singleShot(
                0,
                fields["buttons"].button(
                    QDialogButtonBox.StandardButton.Ok
                ).click,
            )
            return dialog, fields

        monkeypatch.setattr(ai_relief, "build_ai_relief_dialog", make_dialog)
        monkeypatch.setattr(
            ai_relief.QFileDialog, "getSaveFileName",
            lambda *args: (str(generated_stl), "STL mesh (*.stl)"),
        )
        jobs = []
        imported = []
        monkeypatch.setattr(
            window, "_start_background_job",
            lambda title, **kwargs: jobs.append((title, kwargs)) or True,
        )
        monkeypatch.setattr(
            window, "_start_import",
            lambda paths, kind: imported.append((paths, kind)),
        )
        window._generate_ai_relief()
        assert len(jobs) == 1
        title, callbacks = jobs[0]
        assert title == "Local AI bas-relief"
        assert callbacks["request"].prompt == "An anchor with a heavy chain"
        assert callbacks["request"].output_path == str(generated_stl)
        assert callbacks["request"].image_path == ""
        assert callbacks["cancelable"]
        callbacks["on_done"]({"path": str(generated_stl)})
        assert imported == [([str(generated_stl)], "STL")]
    finally:
        window.close()



def test_optional_ai_package_declares_torchvision():
    from pathlib import Path
    from tomllib import loads

    project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
    packages = loads(project_file.read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]["ai"]
    assert any(requirement.startswith("torchvision>=") for requirement in packages)


def test_missing_torchvision_has_actionable_local_install_message(monkeypatch):
    from carvefoundry.core import ai_relief

    def missing(name):
        assert name == "torchvision"
        raise ModuleNotFoundError("No module named 'torchvision'", name="torchvision")

    monkeypatch.setattr(ai_relief, "import_module", missing)
    with pytest.raises(RuntimeError, match="pip install -e") as error:
        ai_relief._require_torchvision()
    assert "CarveFoundry venv" in str(error.value)
    assert "Restart CarveFoundry" in str(error.value)


def test_incompatible_torchvision_reports_matching_pytorch_builds(monkeypatch):
    from carvefoundry.core import ai_relief

    def incompatible(name):
        assert name == "torchvision"
        raise RuntimeError("operator torchvision::nms does not exist")

    monkeypatch.setattr(ai_relief, "import_module", incompatible)
    with pytest.raises(RuntimeError, match="compatible torch and torchvision") as error:
        ai_relief._require_torchvision()
    assert "CUDA" in str(error.value)
    assert "ROCm" in str(error.value)
    assert "torchvision::nms" in str(error.value)



def test_ai_stl_background_job_import_restores_select_and_object_workflow(tmp_path):
    """Exercise BOTH async phases: generation completion hands off to STL import."""
    from time import monotonic, sleep

    from PySide6.QtWidgets import QApplication

    from carvefoundry.ui.project_window import MainWindow

    app = QApplication.instance() or QApplication([])
    assert app is not None
    stl_path = tmp_path / "ai_generated.stl"
    trimesh.creation.box(extents=(24, 20, 3)).export(stl_path)
    window = MainWindow()
    imported = []
    try:
        assert window._ui_actions["select"].isEnabled()
        assert window.tool_rail.buttons["select"].isEnabled()
        assert window._start_background_job(
            "Local AI bas-relief",
            task=lambda progress: {"path": str(stl_path)},
            on_done=lambda result: (
                imported.append(result["path"]),
                window._start_import([result["path"]], "STL"),
            ),
        )

        deadline = monotonic() + 45.0
        while (window._background_job is not None
               or window._import_thread is not None) and monotonic() < deadline:
            app.processEvents()
            sleep(0.01)
        app.processEvents()
        assert window._background_job is None
        assert window._import_thread is None
        assert imported == [str(stl_path)]
        assert len(window.project.items) == 1
        assert window.project.items[0].mesh is not None
        assert window.project_list.currentRow() == 1
        assert window._ui_actions["select"].isEnabled()
        assert window.tool_rail.buttons["select"].isEnabled()
        assert window.tool_rail.buttons["direct_select"].isEnabled()
        assert window.tool_rail.buttons["model"].isEnabled()
        assert window.properties_panel.isEnabled()

        # The generated mesh is actually selectable after import, not just
        # highlighted in a disabled tool rail.
        window.tool_rail.buttons["select"].click()
        assert window.tool_rail.buttons["select"].isChecked()
        assert not window.viewport.camera_control_mode
        window._select_project_indices([0], primary=0)
        assert window._selected_design_indices() == [0]
    finally:
        deadline = monotonic() + 45.0
        while (window._background_job is not None
               or window._import_thread is not None) and monotonic() < deadline:
            app.processEvents()
            sleep(0.01)
        window.close()
