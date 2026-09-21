"""Full source-resolution trace calculations and interactive preview acceptance."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QWidget

from carvefoundry.core.image_trace import count_mask_runs, trace_dimensions, trace_mask
from carvefoundry.ui.image_trace_dialog import ImageTraceDialog, qimage_rgba
from carvefoundry.ui.main_window import MainWindow

_APP = QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    ("width", "height", "percent", "expected"),
    [
        (4000, 3000, 100, (4000, 3000)),
        (4000, 3000, 50, (2000, 1500)),
        (4000, 3000, 1, (40, 30)),
        (257, 83, 100, (257, 83)),
        (257, 83, 25, (64, 21)),
        (1, 20, 1, (1, 1)),
        (2, 2, 100, (2, 2)),
    ],
)
def test_trace_resolution_is_percentage_of_original_pixels(
    width: int, height: int, percent: int, expected: tuple[int, int],
) -> None:
    assert trace_dimensions(width, height, percent) == expected


@pytest.mark.parametrize("percent", [0, -5, 101, 500])
def test_trace_rejects_out_of_range_resolution(percent: int) -> None:
    with pytest.raises(ValueError, match="resolution"):
        trace_dimensions(4000, 3000, percent)


def test_mask_matches_previous_threshold_and_alpha_logic() -> None:
    image = np.array(
        [
            [[0, 0, 0, 255], [255, 255, 255, 255], [50, 50, 50, 0]],
            [[151, 151, 151, 255], [150, 150, 150, 255], [100, 150, 200, 16]],
        ],
        dtype=np.uint8,
    )
    expected_dark = np.array(
        [[True, False, False], [False, True, False]]
    )
    expected_light = np.array(
        [[False, True, False], [True, False, False]]
    )
    assert np.array_equal(trace_mask(image), expected_dark)
    assert np.array_equal(trace_mask(image, invert=True), expected_light)
    assert count_mask_runs(expected_dark) == 2


def test_qimage_rgba_keeps_channel_order_and_owns_storage() -> None:
    image = QImage(3, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor("transparent"))
    image.setPixelColor(0, 0, QColor(20, 100, 240, 255))
    image.setPixelColor(2, 1, QColor(244, 70, 9, 128))
    data = qimage_rgba(image)
    assert data.shape == (2, 3, 4)
    assert tuple(data[0, 0]) == (20, 100, 240, 255)
    assert tuple(data[1, 2]) == (244, 70, 9, 128)
    image.fill(QColor("red"))
    assert tuple(data[0, 0]) == (20, 100, 240, 255)


def test_trace_dialog_shows_original_and_previews_up_to_100_percent() -> None:
    source = QImage(1290, 900, QImage.Format.Format_ARGB32)
    source.fill(QColor("white"))
    source.setPixelColor(10, 10, QColor("black"))
    parent = QWidget()
    dialog = ImageTraceDialog(
        parent, source, source_name="source.png", default_width_mm=95.0,
    )
    try:
        assert "1,290 × 900" in dialog.source_info.text()
        assert dialog.resolution_slider.minimum() == 1
        assert dialog.resolution_slider.maximum() == 100
        assert dialog.resolution_slider.value() > 0
        assert dialog.original_preview.pixmap() is not None
        assert dialog.trace_preview.pixmap() is not None
        dialog.resolution_slider.setValue(100)
        dialog._update_preview()
        settings = dialog.settings()
        assert settings.target_width == 1290
        assert settings.target_height == 900
        assert "1,290 × 900" in dialog.output_info.text()
        assert "100%" == dialog.resolution_value.text()
        assert dialog.size_warning.text()
        dialog.resolution_slider.setValue(50)
        dialog.threshold_slider.setValue(42)
        dialog.invert_check.setChecked(True)
        dialog.width_spin.setValue(150.0)
        dialog.depth_spin.setValue(3.2)
        dialog._update_preview()
        settings = dialog.settings()
        assert (settings.target_width, settings.target_height) == (645, 450)
        assert settings.threshold == 42
        assert settings.invert
        assert settings.width_mm == 150
        assert settings.depth_mm == 3.2
        assert "645 × 450" in dialog.output_info.text()
        assert "3.20 mm deep" in dialog.output_info.text()
    finally:
        dialog.close()
        parent.close()


def test_trace_dialog_warns_before_exceptionally_heavy_mesh(monkeypatch) -> None:
    image = QImage(200, 100, QImage.Format.Format_ARGB32)
    image.fill(QColor("black"))
    dialog = ImageTraceDialog(
        QWidget(), image, source_name="dense.png", default_width_mm=100.0,
    )
    try:
        dialog._estimated_runs = 30_000
        # Force the estimate independently of the thumbnail for this dialog
        # branch; a black solid mask normally has few compact scanline runs.
        monkeypatch.setattr(dialog, "_update_preview", lambda: None)
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
        )
        dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
        )
        dialog.accept()
        assert dialog.result() == QDialog.DialogCode.Accepted
    finally:
        dialog.close()


def test_trace_action_does_not_downscale_when_slider_at_100_percent(
    tmp_path: Path, monkeypatch,
) -> None:
    source = QImage(260, 130, QImage.Format.Format_ARGB32)
    source.fill(QColor("black"))
    path = tmp_path / "relief.png"
    assert source.save(str(path))
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *_args, **_kwargs: (str(path), ""),
    )

    def select_native_resolution(dialog: ImageTraceDialog):
        dialog.resolution_slider.setValue(100)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ImageTraceDialog, "exec", select_native_resolution)
    captured = {}

    def capture_job(_self, _label, *, task, on_done, **_kwargs):
        captured["task"] = task
        captured["on_done"] = on_done

    window = MainWindow()
    try:
        monkeypatch.setattr(
            window, "_start_background_job",
            lambda label, *, task, on_done, **kwargs: capture_job(
                window, label, task=task, on_done=on_done, **kwargs,
            ),
        )
        window._trace_image()
        assert "task" in captured
        updates = []
        mesh = captured["task"](
            lambda fraction, label: updates.append((fraction, label))
        )
        assert any("260 × 130" in label for _, label in updates)
        assert np.isclose(mesh.mesh.bounds[1, 0] - mesh.mesh.bounds[0, 0], 120.0)
        assert np.isclose(mesh.mesh.bounds[1, 1] - mesh.mesh.bounds[0, 1], 60.0)
        assert len(mesh.mesh.faces) == 130 * 12  # Not downscaled to 96 px!
    finally:
        window.close()
