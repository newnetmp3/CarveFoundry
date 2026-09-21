"""Full-resolution image tracing setup with a responsive live mask preview."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.core.image_trace import (
    count_mask_runs,
    trace_dimensions,
    trace_mask,
)

_PREVIEW_LONG_SIDE = 560
_HEAVY_RUN_WARNING = 25_000


def qimage_rgba(image: QImage) -> np.ndarray:
    """Read Qt RGBA8888 scanlines safely, independently of row padding.

    Copy before returning, because the converted QImage owns its original
    pixel buffer and may be released before the NumPy consumer finishes.
    """
    if image.isNull():
        raise ValueError("Could not load image.")
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    height, width = rgba.height(), rgba.width()
    pixels = np.frombuffer(rgba.bits(), dtype=np.uint8)
    rows = pixels.reshape((height, rgba.bytesPerLine()))
    return rows[:, :width * 4].copy().reshape((height, width, 4))


@dataclass(frozen=True, slots=True)
class TraceSettings:
    resolution_percent: int
    threshold: int
    invert: bool
    width_mm: float
    depth_mm: float
    target_width: int
    target_height: int


class ImageTraceDialog(QDialog):
    """Previewed image-to-CNC-relief controls, up to 100% source resolution."""

    def __init__(
        self,
        parent: QWidget,
        image: QImage,
        *,
        source_name: str,
        default_width_mm: float,
    ) -> None:
        super().__init__(parent)
        if image.isNull() or image.width() < 1 or image.height() < 1:
            raise ValueError("Could not load image.")
        self.source_image = QImage(image)
        self.setWindowTitle(f"Trace Image — {Path(source_name).name}")
        self.setObjectName("ImageTraceDialog")
        self.resize(960, 640)
        self.setMinimumWidth(740)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)
        source_size = self.source_image.size()
        self.source_info = QLabel(
            f"Source: {source_size.width():,} × {source_size.height():,} pixels  •  "
            "100% uses every source pixel"
        )
        self.source_info.setObjectName("TraceSourceInfo")
        layout.addWidget(self.source_info)

        previews = QHBoxLayout()
        previews.setSpacing(12)
        original = QVBoxLayout()
        original.addWidget(QLabel("Original image"))
        self.original_preview = QLabel()
        self.original_preview.setObjectName("TraceOriginalPreview")
        self.original_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_preview.setMinimumSize(300, 245)
        self.original_preview.setStyleSheet(
            "background: #111827; border: 1px solid #35415a;"
        )
        original.addWidget(self.original_preview, 1)
        previews.addLayout(original, 1)

        traced = QVBoxLayout()
        traced.addWidget(QLabel("Traced relief (black = material, white = empty)"))
        self.trace_preview = QLabel()
        self.trace_preview.setObjectName("TraceResultPreview")
        self.trace_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.trace_preview.setMinimumSize(300, 245)
        self.trace_preview.setStyleSheet(
            "background: #ffffff; border: 1px solid #35415a;"
        )
        traced.addWidget(self.trace_preview, 1)
        previews.addLayout(traced, 1)
        layout.addLayout(previews, 1)

        controls = QFormLayout()
        controls.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        controls.setHorizontalSpacing(14)
        controls.setVerticalSpacing(9)

        self.resolution_slider = QSlider(Qt.Orientation.Horizontal)
        self.resolution_slider.setObjectName("TraceResolutionSlider")
        self.resolution_slider.setRange(1, 100)
        self.resolution_slider.setSingleStep(1)
        self.resolution_slider.setPageStep(10)
        self.resolution_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.resolution_slider.setTickInterval(10)
        # Default roughly 1024 px longest side; no automatic 96 px truncation.
        suggested = round(1024 * 100 / max(image.width(), image.height()))
        self.resolution_slider.setValue(max(1, min(100, suggested)))
        self.resolution_slider.setToolTip(
            "1–100% of the original pixels; 100% preserves full source detail. "
            "Higher resolutions can generate much larger CNC meshes."
        )
        resolution_row = QHBoxLayout()
        resolution_row.addWidget(self.resolution_slider, 1)
        self.resolution_value = QLabel()
        self.resolution_value.setObjectName("TraceResolutionValue")
        self.resolution_value.setMinimumWidth(52)
        resolution_row.addWidget(self.resolution_value)
        controls.addRow("Detail / resolution", resolution_row)

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setObjectName("TraceThresholdSlider")
        self.threshold_slider.setRange(0, 255)
        self.threshold_slider.setValue(150)
        self.threshold_slider.setToolTip(
            "Raise to include more gray areas; lower to keep only darker marks."
        )
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(self.threshold_slider, 1)
        self.threshold_value = QLabel()
        self.threshold_value.setObjectName("TraceThresholdValue")
        self.threshold_value.setMinimumWidth(48)
        threshold_row.addWidget(self.threshold_value)
        controls.addRow("Darkness cutoff", threshold_row)

        self.invert_check = QCheckBox(
            "Trace the lighter areas instead of dark areas"
        )
        self.invert_check.setObjectName("TraceInvertCheck")
        self.invert_check.setToolTip(
            "Use this when you want light markings on a dark background."
        )
        controls.addRow("Reverse image", self.invert_check)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setObjectName("TraceWidthMm")
        self.width_spin.setRange(1.0, 100_000.0)
        self.width_spin.setDecimals(2)
        self.width_spin.setSuffix(" mm")
        self.width_spin.setValue(max(1.0, default_width_mm))
        controls.addRow("Carved width", self.width_spin)

        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setObjectName("TraceDepthMm")
        self.depth_spin.setRange(0.1, 1000.0)
        self.depth_spin.setDecimals(2)
        self.depth_spin.setSuffix(" mm")
        self.depth_spin.setValue(1.0)
        controls.addRow("Relief depth", self.depth_spin)
        layout.addLayout(controls)

        self.output_info = QLabel()
        self.output_info.setObjectName("TraceOutputInfo")
        self.output_info.setWordWrap(True)
        layout.addWidget(self.output_info)
        self.size_warning = QLabel()
        self.size_warning.setObjectName("TraceSizeWarning")
        self.size_warning.setWordWrap(True)
        layout.addWidget(self.size_warning)
        self.preview_note = QLabel(
            "Preview is screen-sized for responsiveness; the final mesh uses "
            "the output pixel dimensions shown above."
        )
        self.preview_note.setWordWrap(True)
        layout.addWidget(self.preview_note)

        self._estimated_runs = 0
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(90)
        self._preview_timer.timeout.connect(self._update_preview)
        self.resolution_slider.valueChanged.connect(self._schedule_preview)
        self.threshold_slider.valueChanged.connect(self._schedule_preview)
        self.invert_check.toggled.connect(self._schedule_preview)
        self.width_spin.valueChanged.connect(self._schedule_preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_preview()

    def settings(self) -> TraceSettings:
        percent = self.resolution_slider.value()
        width, height = trace_dimensions(
            self.source_image.width(), self.source_image.height(), percent,
        )
        return TraceSettings(
            resolution_percent=percent,
            threshold=self.threshold_slider.value(),
            invert=self.invert_check.isChecked(),
            width_mm=self.width_spin.value(),
            depth_mm=self.depth_spin.value(),
            target_width=width,
            target_height=height,
        )

    def _schedule_preview(self, _value: object = None) -> None:
        settings = self.settings()
        self.resolution_value.setText(f"{settings.resolution_percent}%")
        self.threshold_value.setText(str(settings.threshold))
        self.output_info.setText(
            f"Output: {settings.target_width:,} × {settings.target_height:,} pixels"
            f"  •  {settings.width_mm:.1f} × "
            f"{settings.width_mm * settings.target_height / settings.target_width:.1f}"
            " mm"
        )
        self._preview_timer.start()

    def _update_preview(self) -> None:
        settings = self.settings()
        self.resolution_value.setText(f"{settings.resolution_percent}%")
        self.threshold_value.setText(str(settings.threshold))
        height_mm = (
            settings.width_mm * settings.target_height / settings.target_width
        )
        self.output_info.setText(
            f"Output: {settings.target_width:,} × {settings.target_height:,} pixels"
            f"  •  {settings.width_mm:.1f} × {height_mm:.1f} mm"
            f"  •  {settings.depth_mm:.2f} mm deep"
        )

        # The preview never allocates a full-size final binary or 3D mesh on
        # the Qt GUI thread, so dragging its slider stays responsive.
        preview_factor = min(
            1.0,
            _PREVIEW_LONG_SIDE / max(settings.target_width, settings.target_height),
        )
        preview_width = max(1, round(settings.target_width * preview_factor))
        preview_height = max(1, round(settings.target_height * preview_factor))
        sampled = self.source_image.scaled(
            preview_width,
            preview_height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        mask = trace_mask(
            qimage_rgba(sampled),
            threshold=settings.threshold,
            invert=settings.invert,
        )
        self._estimated_runs = round(
            count_mask_runs(mask)
            * (settings.target_width * settings.target_height)
            / mask.size
        )

        # Black active pixels on opaque white background.
        output_rgb = np.full(
            (preview_height, preview_width, 3), 255, dtype=np.uint8
        )
        output_rgb[mask] = 0
        preview_image = QImage(
            output_rgb.data,
            preview_width,
            preview_height,
            preview_width * 3,
            QImage.Format.Format_RGB888,
        ).copy()
        self._set_preview_image(self.trace_preview, preview_image)
        self._set_preview_image(self.original_preview, sampled)

        if self._estimated_runs >= _HEAVY_RUN_WARNING:
            self.size_warning.setText(
                f"Large trace: roughly {self._estimated_runs:,} mesh blocks "
                "estimated from the preview. Processing and CNC toolpaths "
                "may take substantial time and memory."
            )
            self.size_warning.setStyleSheet("color: #ffbd72;")
        else:
            self.size_warning.setText(
                f"Estimated mesh blocks: ~{self._estimated_runs:,} "
                "(each run of selected pixels becomes one rectangle)."
            )
            self.size_warning.setStyleSheet("")

    @staticmethod
    def _set_preview_image(label: QLabel, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image)
        # Labels have a stable minimum size in a resizable dialog; use maximum
        # sensible screen dimensions rather than ever enlarging bitmap detail.
        label.setPixmap(
            pixmap.scaled(
                440, 330,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def accept(self) -> None:
        self._preview_timer.stop()
        self._update_preview()
        if self._estimated_runs >= _HEAVY_RUN_WARNING:
            answer = QMessageBox.question(
                self,
                "Large CNC trace",
                "This resolution may create a very large mesh and take a long "
                "time to generate or preview. Continue at the selected "
                "resolution?\n\n"
                "You can reduce the Detail / resolution slider if needed.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        super().accept()
