"""Fixture editing, preflight, resume, and tiled G-code utilities."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from carvefoundry.cam.job_process import GcodeRequest
from carvefoundry.cam.job_workflows import TilingSettings, find_safe_resume_index, plan_tiles
from carvefoundry.core.fixtures import Fixture

from .ribbon_forms import _ActionForm


class JobUtilityActionsMixin:
    """CNC safety/setup utilities and alternate export workflows."""

    def _fixture_editor(self) -> None:
        """Edit persistent keep-out volumes, including off-stock fences."""

        dialog = QDialog(self)
        dialog.setWindowTitle("Clamps and Fences — Fixture Keep-Outs")
        dialog.resize(630, 435)
        layout = QVBoxLayout(dialog)
        explanation = QLabel(
            "Fixture XY is measured from the stock bottom-left corner. "
            "Top Z is relative to the stock top (Z0); a 23 mm fence "
            "measured from the bed has Top Z = 23 - stock thickness. "
            "Keep-out clearance applies beyond the cutter radius."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        listing = QListWidget()
        listing.setObjectName("FixtureKeepOutList")
        layout.addWidget(listing, 1)
        controls = QHBoxLayout()
        add_button = QPushButton("Add")
        edit_button = QPushButton("Edit")
        remove_button = QPushButton("Remove")
        for button in (add_button, edit_button, remove_button):
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        entries = list(self.project.fixtures)

        def refresh() -> None:
            selected = listing.currentRow()
            listing.clear()
            for fixture in entries:
                listing.addItem(
                    f"{fixture.name}  ·  X {fixture.x_min_mm:g}…"
                    f"{fixture.x_max_mm:g}, Y {fixture.y_min_mm:g}…"
                    f"{fixture.y_max_mm:g}, top Z {fixture.top_z_mm:g}, "
                    f"margin {fixture.clearance_mm:g} mm"
                )
            if entries:
                listing.setCurrentRow(max(0, min(selected, len(entries) - 1)))

        def edit_fixture(current: Fixture | None) -> Fixture | None:
            defaults = current or Fixture(
                "Left fence", -23.0, 0.0, -1.0,
                self.project.stock.height_mm,
                23.0 - self.project.stock.thickness_mm, 2.0,
            )
            while True:
                form = _ActionForm(dialog, "Add Fixture" if current is None else "Edit Fixture")
                form.add_line("name", "Name", defaults.name)
                for key, title, value in (
                    ("x0", "Minimum X", defaults.x_min_mm),
                    ("y0", "Minimum Y", defaults.y_min_mm),
                    ("x1", "Maximum X", defaults.x_max_mm),
                    ("y1", "Maximum Y", defaults.y_max_mm),
                    ("top", "Top Z", defaults.top_z_mm),
                    ("margin", "Additional clearance", defaults.clearance_mm),
                ):
                    form.add_double(
                        key, title, value, suffix=" mm",
                        minimum=0.0 if key == "margin" else -100000.0,
                    )
                if form.exec() != QDialog.DialogCode.Accepted:
                    return None
                candidate = Fixture(
                    str(form.value("name")).strip(),
                    float(form.value("x0")),
                    float(form.value("y0")),
                    float(form.value("x1")),
                    float(form.value("y1")),
                    float(form.value("top")),
                    float(form.value("margin")),
                )
                try:
                    candidate.validate()
                except ValueError as exc:
                    QMessageBox.warning(form, "Invalid fixture", str(exc))
                    defaults = candidate
                    continue
                return candidate

        def add() -> None:
            fixture = edit_fixture(None)
            if fixture is not None:
                entries.append(fixture)
                refresh()
                listing.setCurrentRow(len(entries) - 1)

        def edit() -> None:
            index = listing.currentRow()
            if 0 <= index < len(entries):
                fixture = edit_fixture(entries[index])
                if fixture is not None:
                    entries[index] = fixture
                    refresh()

        def remove() -> None:
            index = listing.currentRow()
            if 0 <= index < len(entries):
                entries.pop(index)
                refresh()

        add_button.clicked.connect(add)
        edit_button.clicked.connect(edit)
        remove_button.clicked.connect(remove)
        listing.itemDoubleClicked.connect(lambda _item: edit())
        refresh()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if entries != self.project.fixtures:
            self._before_ribbon_mutation("edit fixtures")
            self.project.fixtures = entries
            self.viewport.update()
            self._after_ribbon_mutation("edit fixtures", True)
            self.statusBar().showMessage(
                f"Saved {len(entries)} fixture keep-out(s)", 4500
            )

    def _preflight_toolpaths(self) -> None:
        paths = list(self.project.toolpaths)
        guided_fingerprint = self._guided_job_fingerprint()
        self._guided_preflight_pass = None
        if not paths:
            self.statusBar().showMessage(
                "Generate toolpaths before running preflight", 4000
            )
            return
        request = GcodeRequest(
            toolpaths=paths,
            path="",
            settings=self._grbl_post_settings(),
            mode="preflight",
            stock=self.project.stock,
            machine_profile=self._active_machine_profile(),
            fixtures=tuple(self.project.fixtures),
        )

        def done(payload: object) -> None:
            self._guided_preflight_pass = (
                guided_fingerprint if payload["safe_to_export"]
                and self._guided_job_fingerprint() == guided_fingerprint
                else None
            )
            self._refresh_guided_workflow()
            report = str(payload["report"])
            self._set_activity_info(report)
            display = QMessageBox(self)
            display.setWindowTitle("CNC Preflight")
            display.setIcon(
                QMessageBox.Icon.Information
                if payload["safe_to_export"] else QMessageBox.Icon.Warning
            )
            display.setText(
                "Preflight passed (with noted warnings)."
                if payload["safe_to_export"] else
                "Preflight blocked export until errors are corrected."
            )
            display.setDetailedText(report)
            display.setStandardButtons(QMessageBox.StandardButton.Ok)
            display.exec()

        self._start_background_job(
            "CNC preflight", request=request, on_done=done
        )

    def _export_resume_gcode(self) -> None:
        toolpaths = list(self.project.toolpaths)
        if not toolpaths:
            self.statusBar().showMessage(
                "Calculate toolpaths before creating a resume file",
                5000,
            )
            return

        counts = [len(toolpath.moves) for toolpath in toolpaths]
        total_moves = sum(counts)
        if total_moves <= 0:
            self.statusBar().showMessage("Toolpaths contain no moves", 4000)
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Resume Carve")
        dialog.resize(620, 320)
        layout = QVBoxLayout(dialog)
        warning = QLabel(
            "Choose approximately where the interruption occurred. "
            "Safe restart rewinds to the beginning of that uninterrupted cutting "
            "section and is recommended because it avoids a blind vertical entry "
            "in the middle of a 3D pass."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, total_moves - 1)
        spin = QSpinBox()
        spin.setRange(0, total_moves - 1)
        spin.setPrefix("Move ")
        row = QHBoxLayout()
        row.addWidget(slider, 1)
        row.addWidget(spin)
        layout.addLayout(row)

        safe_rewind = QCheckBox("Rewind to safe section start")
        safe_rewind.setChecked(True)
        layout.addWidget(safe_rewind)

        detail = QLabel()
        detail.setObjectName("InspectorInfo")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        def locate(global_index: int) -> tuple[int, int]:
            remaining = int(global_index)
            for path_index, count in enumerate(counts):
                if remaining < count:
                    return path_index, remaining
                remaining -= count
            return len(counts) - 1, max(0, counts[-1] - 1)

        def update_detail(value: int) -> None:
            if spin.value() != value:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
            if slider.value() != value:
                slider.blockSignals(True)
                slider.setValue(value)
                slider.blockSignals(False)
            path_index, move_index = locate(value)
            toolpath = toolpaths[path_index]
            move = toolpath.moves[move_index]
            safe_index = move_index
            if safe_rewind.isChecked():
                try:
                    safe_index = find_safe_resume_index(toolpath, move_index)
                except (IndexError, ValueError):
                    safe_index = move_index
            detail.setText(
                f"Operation: {toolpath.name}\n"
                f"Selected point: {move_index:,} / {len(toolpath.moves) - 1:,}\n"
                f"XYZ: {move.x_mm:.3f}, {move.y_mm:.3f}, {move.z_mm:.3f} mm\n"
                f"Move type: {move.kind.value}\n"
                f"Actual restart point: {safe_index:,}"
            )

        slider.valueChanged.connect(update_detail)
        spin.valueChanged.connect(update_detail)
        safe_rewind.toggled.connect(
            lambda _checked: update_detail(slider.value())
        )
        update_detail(0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        path_index, move_index = locate(slider.value())
        rewind = safe_rewind.isChecked()

        base_directory = (
            self.project_path.parent if self.project_path else Path.home()
        )
        name = (
            self.project.name
            if self.project.name != "Untitled"
            else "carve"
        )
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Export Resume G-code",
            str(base_directory / f"{name}_resume.nc"),
            "G-code (*.nc *.gcode *.tap *.cnc);;All files (*)",
        )
        if not output:
            return
        request = GcodeRequest(
            toolpaths=toolpaths,
            path=output,
            settings=self._grbl_post_settings(),
            stock=self.project.stock,
            machine_profile=self._active_machine_profile(),
            fixtures=tuple(self.project.fixtures),
            mode="resume",
            resume_path_index=path_index,
            resume_move_index=move_index,
            resume_rewind=rewind,
        )

        def done(result):
            written = Path(result["files"][0])
            self.statusBar().showMessage(
                f"Resume G-code exported: {written.name}", 5000
            )

        self._start_background_job(
            "Export resume G-code", request=request, on_done=done
        )

    def _export_tiled_gcode(self) -> None:
        toolpaths = list(self.project.toolpaths)
        if not toolpaths:
            self.statusBar().showMessage(
                "Calculate toolpaths before exporting tiles",
                5000,
            )
            return

        profile = self._active_machine_profile()
        stock = self.project.stock
        form = _ActionForm(self, "Large Material Tiling")
        form.add_double(
            "width",
            "Tile width",
            min(stock.width_mm, profile.work_x_mm),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm",
        )
        form.add_double(
            "height",
            "Tile height",
            min(stock.height_mm, profile.work_y_mm),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm",
        )
        form.add_double(
            "overlap",
            "Tile overlap",
            3.0,
            minimum=0.0,
            maximum=10000.0,
            suffix=" mm",
        )
        form.add_check(
            "rebase",
            "Re-zero each shifted tile",
            True,
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        settings = TilingSettings(
            tile_width_mm=float(form.value("width")),
            tile_height_mm=float(form.value("height")),
            overlap_mm=float(form.value("overlap")),
            rebase_each_tile=bool(form.value("rebase")),
        )
        try:
            plan_tiles(
                stock.width_mm,
                stock.height_mm,
                settings,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Large Material Tiling", str(exc))
            return

        base_directory = (
            self.project_path.parent if self.project_path else Path.home()
        )
        name = (
            self.project.name
            if self.project.name != "Untitled"
            else "carve"
        )
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Choose Tiled G-code Base Name",
            str(base_directory / f"{name}_tiles.nc"),
            "G-code (*.nc *.gcode *.tap *.cnc);;All files (*)",
        )
        if not output:
            return

        request = GcodeRequest(
            toolpaths=toolpaths,
            path=output,
            settings=self._grbl_post_settings(),
            stock=self.project.stock,
            machine_profile=self._active_machine_profile(),
            fixtures=tuple(self.project.fixtures),
            mode="tiles",
            tile_settings=settings,
            stock_width_mm=stock.width_mm,
            stock_height_mm=stock.height_mm,
            xy_zero=stock.xy_zero,
        )

        def done(result):
            written = [Path(path) for path in result["files"]]
            self._set_activity_info(
                "Tiled G-code exported\n"
                f"Files: {len(written)}\n"
                f"Tile size: {settings.tile_width_mm:g} × "
                f"{settings.tile_height_mm:g} mm\n"
                f"Overlap: {settings.overlap_mm:g} mm\n"
                + "\n".join(path.name for path in written[:12])
            )
            self.statusBar().showMessage(
                f"Exported {len(written)} tiled G-code files", 5000
            )

        self._start_background_job(
            "Export tiled G-code", request=request, on_done=done
        )
