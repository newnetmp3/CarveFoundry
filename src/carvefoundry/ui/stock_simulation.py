"""Independent sampled remaining-stock viewer, not G-code path playback."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
)

from carvefoundry.cam.stock_simulation import StockRemovalResult, simulate_stock_removal
from carvefoundry.cam.virtual_machining import simulate_posted_stock_removal


def stock_image(result: StockRemovalResult, *, deviations: bool = False) -> QImage:
    """Detach a top-down RGB raster from its transient NumPy buffer."""
    z = result.remaining_z_mm.astype(float)
    depth = np.maximum(0.0, -z)
    fraction = np.clip(depth / max(float(depth.max()), 0.001), 0, 1)
    rgb = np.empty((*z.shape, 3), dtype=np.uint8)
    rgb[:, :, 0] = (216 - 137 * fraction).astype(np.uint8)
    rgb[:, :, 1] = (171 - 113 * fraction).astype(np.uint8)
    rgb[:, :, 2] = (108 - 68 * fraction).astype(np.uint8)
    if deviations and result.target_z_mm is not None:
        valid = np.isfinite(result.target_z_mm)
        rgb[valid & (z > result.target_z_mm + 0.15)] = (60, 160, 241)
        rgb[valid & (z < result.target_z_mm - 0.15)] = (244, 69, 79)
    rgb = np.ascontiguousarray(rgb[::-1])
    height, width, _ = rgb.shape
    return QImage(
        rgb.data, width, height, rgb.strides[0],
        QImage.Format.Format_RGB888,
    ).copy()


class StockSimulationMixin:
    """Calculate material removal off-thread and visualize the sampled stock."""

    def _show_stock_removal_result(
        self, result: StockRemovalResult, *, posted_nc: bool = False,
    ) -> None:
        old = getattr(self, "_stock_removal_dialog", None)
        if old is not None:
            old.close()
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setWindowTitle(
            "CarveFoundry — Verified NC Stock Removal" if posted_nc
            else "CarveFoundry — Sampled Stock Removal"
        )
        dialog.resize(1030, 830)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel(
            ("Verified posted NC · " if posted_nc else "Planned paths · ")
            + f"Remaining stock · {result.grid_spacing_mm:.3f} mm samples · "
            f"{result.removed_volume_cm3:.2f} cm³ estimated removed",
        ))
        stage_label = QLabel(
            f"{result.cut_sample_count:,} cutter samples; G0 excluded.\n"
            + "\n".join(
                f"{i + 1:02d}. {stage.name} · {stage.cutter_name} · "
                f"{stage.removed_volume_mm3 / 1000:.2f} cm³"
                for i, stage in enumerate(result.stages)
            )
        )
        stage_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        stage_label.setWordWrap(True)
        layout.addWidget(stage_label)

        uncut, gouged, compared = result.deviation_counts()
        summary = (
            f"Top model surface ({compared:,} sample points): "
            f"{uncut:,} have >0.15 mm uncut material (blue); "
            f"{gouged:,} are >0.15 mm below model (red)."
            if compared else
            "No valid top-model comparison; colours show remaining stock depth."
        )
        info = QLabel(summary)
        info.setWordWrap(True)
        layout.addWidget(info)

        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        image_label = QLabel(scroll)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setMinimumSize(360, 280)
        scroll.setWidget(image_label)
        layout.addWidget(scroll, 1)

        toggle = QCheckBox(
            "Highlight model-surface deviations (±0.15 mm)", dialog
        )
        toggle.setEnabled(compared > 0)
        toggle.setChecked(compared > 0)
        layout.addWidget(toggle)

        def redraw() -> None:
            image = stock_image(result, deviations=toggle.isChecked())
            image_label.setPixmap(QPixmap.fromImage(image).scaled(
                980, 610,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

        toggle.toggled.connect(redraw)
        redraw()

        caveat = QLabel(
            "Sampled 2.5D stock, not exact volumetric CSG. Cannot represent "
            "undercuts, cutter holder, runout or machine/work-offset state. "
            "Intentional pockets and cutouts can fall below the model's top "
            "surface. This does NOT replace mandatory CNC preflight."
        )
        caveat.setWordWrap(True)
        layout.addWidget(caveat)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, parent=dialog
        )
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        self._stock_removal_dialog = dialog
        dialog.destroyed.connect(
            lambda _object=None: self._on_stock_dialog_destroyed(dialog)
        )
        dialog.show()

    def _on_stock_dialog_destroyed(self, dialog) -> None:
        if getattr(self, "_stock_removal_dialog", None) is dialog:
            self._stock_removal_dialog = None

    def _run_stock_removal(
        self, *, spacing_mm: float = 0.75, posted_nc: bool = True,
    ) -> bool:
        if self._background_job is not None:
            self.statusBar().showMessage("Finish the current job first", 5000)
            return False
        if not self.project.toolpaths:
            self.statusBar().showMessage(
                "Generate toolpaths before simulating stock.", 5000
            )
            return False
        project = self.project
        profile = self._active_machine_profile() if posted_nc else None
        settings = self._grbl_post_settings() if posted_nc else None
        compare_model = any(
            path.operation in {
                "rough", "finish", "rest", "height_map", "waterline",
            }
            for path in project.toolpaths
        )

        def calculate(progress):
            if posted_nc and profile is not None:
                return simulate_posted_stock_removal(
                    project, profile, settings, spacing_mm=spacing_mm,
                    progress=progress, compare_model=compare_model,
                )
            return simulate_stock_removal(
                project, spacing_mm=spacing_mm,
                progress=progress, compare_model=compare_model,
            )

        def completed(result):
            self._show_stock_removal_result(result, posted_nc=posted_nc)
            self.statusBar().showMessage(
                f"Estimated material removed: {result.removed_volume_cm3:.2f} cm³",
                8000,
            )

        def failed(message: str):
            self._set_activity_info(f"Stock simulation failed\n{message}")
            self.statusBar().showMessage(
                f"Stock simulation failed: {message}", 9000
            )

        return self._start_background_job(
            "Simulate stock removal",
            task=calculate,
            on_done=completed,
            on_failed=failed,
            cancelable=True,
        )

    def _simulate_stock_removal(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Simulate Material Removal")
        layout = QFormLayout(dialog)
        explanation = QLabel(
            "Simulates the stock remaining after all generated cutting moves, "
            "using each selected cutter's actual radial profile. "
            "Separate from backplot path animation."
        )
        explanation.setWordWrap(True)
        layout.addRow(explanation)
        spacing = QDoubleSpinBox(dialog)
        spacing.setRange(0.1, 10.0)
        spacing.setDecimals(2)
        spacing.setValue(0.75)
        spacing.setSingleStep(0.25)
        spacing.setSuffix(" mm")
        spacing.setToolTip(
            "Smaller XY samples increase detail and calculation cost. "
            "Oversized grids are refused."
        )
        layout.addRow("XY sample spacing", spacing)
        posted = QCheckBox("Verify and simulate posted G-code (recommended)", dialog)
        posted.setChecked(True)
        posted.setToolTip(
            "Render one GRBL program per cutter, decode the actual NC, check "
            "feed/position and fixture clearance, then simulate those commands."
        )
        layout.addRow(posted)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run_stock_removal(
                spacing_mm=spacing.value(), posted_nc=posted.isChecked(),
            )
