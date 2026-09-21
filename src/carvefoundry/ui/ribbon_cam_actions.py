"""Toolpath design options, CAM requests and preview actions."""
from __future__ import annotations

from math import ceil, sqrt

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QDialog

from carvefoundry.cam.basic_ops import (
    BasicCamSettings,
    MillingDirection,
    PocketStrategy,
    ReliefStyle,
    detail_for_stepover_fraction,
    detail_stepover_fraction,
)
from carvefoundry.cam.job_process import CamRequest
from carvefoundry.cam.raster import RasterAxis, RasterLinkMode
from carvefoundry.core.tools import Cutter

from .ribbon_forms import _ActionForm
from .toolpath_preview import ToolpathPreviewWindow


class RibbonCamActionsMixin:
    def _register_cam_selector(self, key: str, combo: QComboBox) -> None:
        self._cam_selector_widgets.setdefault(key, []).append(combo)

    def _register_cam_detail_slider(self, widget) -> None:
        self._cam_detail_widgets.append(widget)
        self._refresh_cam_detail_readouts()

    def _set_cam_detail(
        self,
        value: int,
        *,
        mark_custom: bool = True,
    ) -> None:
        detail = max(0, min(100, int(value)))
        self._cam_detail = detail
        self._settings.setValue("cam/design/detail", detail)

        if mark_custom and self._cam_quality != "Custom":
            self._cam_quality = "Custom"
            self._settings.setValue("cam/design/quality", "Custom")
            for combo in self._cam_selector_widgets.get("quality", []):
                combo.blockSignals(True)
                try:
                    index = combo.findText("Custom")
                    if index >= 0:
                        combo.setCurrentIndex(index)
                finally:
                    combo.blockSignals(False)

        for widget in self._cam_detail_widgets:
            slider = widget.slider
            if slider.value() == detail:
                continue
            slider.blockSignals(True)
            try:
                slider.setValue(detail)
            finally:
                slider.blockSignals(False)

        self._settings.sync()
        self._refresh_cam_detail_readouts()

        fraction = detail_stepover_fraction(detail)
        cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        if isinstance(cutter, Cutter):
            stepover = cutter.diameter_mm * fraction
            message = (
                f"Detail {detail}% — {fraction * 100:.1f}% stepover "
                f"({stepover:.3f} mm with {cutter.name})"
            )
        else:
            message = (
                f"Detail {detail}% — {fraction * 100:.1f}% cutter stepover"
            )
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(message, 2500)

    def _estimated_detail_raster_lines(self, stepover_mm: float) -> int | None:
        if stepover_mm <= 0.0:
            return None
        if not hasattr(self, "project_list"):
            return None
        item = self._selected_item()
        if item is None:
            return None
        bounds = item.transformed_bounds_mm()
        if bounds is None:
            return None

        span = np.maximum(
            np.asarray(bounds[1, :2], dtype=float)
            - np.asarray(bounds[0, :2], dtype=float),
            0.0,
        )
        span_x = float(span[0])
        span_y = float(span[1])

        direction = self._cam_direction
        if direction == "Offset":
            return None
        if direction == "Raster X":
            cross_span = span_y
        elif direction == "Raster Y":
            cross_span = span_x
        elif direction in {"Raster 45°", "Raster 135°"}:
            cross_span = (span_x + span_y) / sqrt(2.0)
        else:
            # Smart Serpentine runs along the longer dimension, leaving fewer
            # raster rows across the shorter dimension.
            cross_span = min(span_x, span_y)

        if cross_span <= 1e-9:
            return None
        return max(2, ceil(cross_span / stepover_mm) + 1)

    def _refresh_cam_detail_readouts(self) -> None:
        if not self._cam_detail_widgets:
            return

        fraction = detail_stepover_fraction(self._cam_detail)
        cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        if isinstance(cutter, Cutter):
            stepover = cutter.diameter_mm * fraction
            line_count = self._estimated_detail_raster_lines(stepover)
            text = f"{fraction * 100:.1f}% • {stepover:.3f} mm"
            if line_count is not None:
                text += f" • ~{line_count:,} lines"
        else:
            text = f"{fraction * 100:.1f}% of cutter"

        for widget in self._cam_detail_widgets:
            widget.set_readout(text)

    def _set_cam_design_option(self, key: str, value: str) -> None:
        attributes = {
            "cut_type": "_cam_cut_type",
            "direction": "_cam_direction",
            "quality": "_cam_quality",
            "entry": "_cam_entry",
            "linking": "_cam_linking",
            "milling": "_cam_milling",
            "3d_cut_style": "_cam_3d_cut_style",
        }
        attribute = attributes[key]
        setattr(self, attribute, value)
        self._settings.setValue(f"cam/design/{key}", value)

        if key == "quality" and value != "Custom":
            fraction = {
                "Fast 15%": 0.15,
                "Balanced 10%": 0.10,
                "Detail 8%": 0.08,
                "Fine 6%": 0.06,
            }[value]
            self._set_cam_detail(
                detail_for_stepover_fraction(fraction),
                mark_custom=False,
            )
        if (
            key == "3d_cut_style"
            and value == "Full Depth Cutout"
            and not self._tabs_enabled
        ):
            self._tabs_enabled = True
            self._settings.setValue("cam/tabs_enabled", True)
            if self._tabs_button is not None:
                self._tabs_button.setChecked(True)
        self._settings.sync()

        for combo in self._cam_selector_widgets.get(key, []):
            if combo.currentText() == value:
                continue
            combo.blockSignals(True)
            try:
                index = combo.findText(value)
                if index >= 0:
                    combo.setCurrentIndex(index)
            finally:
                combo.blockSignals(False)

        for action in getattr(self, "_cam_menu_choice_actions", {}).get(key, []):
            action.setChecked(action.text() == value)

        if key == "direction":
            self._refresh_cam_detail_readouts()


        self.statusBar().showMessage(
            f"Toolpath {key.replace('_', ' ')}: {value}",
            2500,
        )

    def _toolpath_design_advanced(self) -> None:
        form = _ActionForm(self, "Advanced Toolpath Design")
        form.add_double(
            "safe_z",
            "Global Safe Z",
            float(self._settings.value("cam/safe_z_mm", 1.5)),
            minimum=0.05,
            maximum=100.0,
            decimals=3,
            step=0.1,
            suffix=" mm",
        )
        form.add_double(
            "cut_depth",
            "Overall cut depth (0 = design/model)",
            float(self._settings.value("cam/overall_depth_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            decimals=3,
            step=0.25,
            suffix=" mm",
        )
        form.add_double(
            "feed",
            "Cut feed",
            float(self._settings.value("cam/feed_mm_min", 1000.0)),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm/min",
        )
        form.add_double(
            "plunge",
            "Plunge feed",
            float(self._settings.value("cam/plunge_mm_min", 300.0)),
            minimum=1.0,
            maximum=100000.0,
            suffix=" mm/min",
        )
        form.add_double(
            "stepdown",
            "Depth per pass",
            float(self._settings.value("cam/stepdown_mm", 2.0)),
            minimum=0.05,
            maximum=1000.0,
            suffix=" mm",
        )
        form.add_double(
            "pocket_stepover",
            "2D pocket stepover",
            float(self._settings.value("cam/stepover_percent", 45.0)),
            minimum=1.0,
            maximum=100.0,
            decimals=1,
            step=1.0,
            suffix=" %",
        )
        form.add_double(
            "finish_stepover",
            "3D detail stepover",
            detail_stepover_fraction(self._cam_detail) * 100.0,
            minimum=4.0,
            maximum=20.0,
            decimals=1,
            step=0.5,
            suffix=" % of cutter",
        )
        form.add_double(
            "padding",
            "Relief / path padding",
            float(self._settings.value("cam/padding_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            decimals=3,
            step=0.5,
            suffix=" mm",
        )
        form.add_double(
            "bit_length",
            "Usable bit length (0 = not enforced)",
            float(self._settings.value("cam/usable_bit_length_mm", 0.0)),
            minimum=0.0,
            maximum=1000.0,
            decimals=3,
            step=0.5,
            suffix=" mm",
        )
        form.add_double(
            "tab_height",
            "Tab height",
            float(self._settings.value("cam/tab_height_mm", 2.0)),
            minimum=0.1,
            maximum=100.0,
            decimals=3,
            step=0.25,
            suffix=" mm",
        )
        form.add_double(
            "tab_width",
            "Tab width",
            float(self._settings.value("cam/tab_width_mm", 6.0)),
            minimum=0.5,
            maximum=100.0,
            decimals=3,
            step=0.5,
            suffix=" mm",
        )
        form.add_int(
            "tab_count",
            "Tab count",
            int(self._settings.value("cam/tab_count", 4)),
            minimum=1,
            maximum=32,
        )
        form.add_double(
            "local_clearance",
            "Smart-link local clearance",
            float(self._settings.value("cam/local_link_clearance_mm", 0.5)),
            minimum=0.05,
            maximum=25.0,
            decimals=3,
            step=0.1,
            suffix=" mm",
        )
        form.add_double(
            "link_tolerance",
            "Direct-link surface tolerance",
            float(self._settings.value("cam/direct_link_tolerance_mm", 0.02)),
            minimum=0.0,
            maximum=5.0,
            decimals=3,
            step=0.01,
            suffix=" mm",
        )
        form.add_double(
            "ramp_angle",
            "Custom ramp angle",
            float(self._settings.value("cam/custom_ramp_angle_deg", 10.0)),
            minimum=0.5,
            maximum=89.0,
            decimals=1,
            step=0.5,
            suffix="°",
        )
        if form.exec() != QDialog.DialogCode.Accepted:
            return

        values = {
            "cam/safe_z_mm": form.value("safe_z"),
            "cam/overall_depth_mm": form.value("cut_depth"),
            "cam/feed_mm_min": form.value("feed"),
            "cam/plunge_mm_min": form.value("plunge"),
            "cam/stepdown_mm": form.value("stepdown"),
            "cam/stepover_percent": form.value("pocket_stepover"),
            "cam/padding_mm": form.value("padding"),
            "cam/usable_bit_length_mm": form.value("bit_length"),
            "cam/tab_height_mm": form.value("tab_height"),
            "cam/tab_width_mm": form.value("tab_width"),
            "cam/tab_count": form.value("tab_count"),
            "cam/local_link_clearance_mm": form.value("local_clearance"),
            "cam/direct_link_tolerance_mm": form.value("link_tolerance"),
            "cam/custom_ramp_angle_deg": form.value("ramp_angle"),
        }
        for setting_key, setting_value in values.items():
            self._settings.setValue(setting_key, setting_value)

        requested_fraction = float(form.value("finish_stepover")) / 100.0
        self._set_cam_detail(
            detail_for_stepover_fraction(requested_fraction),
            mark_custom=True,
        )
        self._settings.sync()
        self.statusBar().showMessage("Advanced toolpath settings saved", 3000)

    def _quality_stepover_fraction(self) -> float:
        return detail_stepover_fraction(self._cam_detail)

    def _ramp_angle(self) -> float | None:
        if self._cam_entry == "Ramp 5°":
            return 5.0
        if self._cam_entry == "Ramp 20°":
            return 20.0
        if self._cam_entry == "Custom Ramp":
            return float(
                self._settings.value("cam/custom_ramp_angle_deg", 10.0)
            )
        return None

    def _milling_direction(self) -> MillingDirection:
        return {
            "Climb (CCW)": MillingDirection.CLIMB,
            "Conventional (CW)": MillingDirection.CONVENTIONAL,
        }.get(self._cam_milling, MillingDirection.DEFAULT)

    def _relief_style(self) -> ReliefStyle:
        return {
            "Rectangle Relief": ReliefStyle.RECTANGLE,
            "Full Depth Cutout": ReliefStyle.FULL_DEPTH,
        }.get(self._cam_3d_cut_style, ReliefStyle.MODEL_BOUNDARY)

    def _link_mode(self) -> RasterLinkMode:
        return {
            "Local Lift": RasterLinkMode.LOCAL_LIFT,
            "Full Retract": RasterLinkMode.FULL_RETRACT,
        }.get(self._cam_linking, RasterLinkMode.SMART)

    def _raster_axis_for_mesh(self, mesh) -> RasterAxis:
        direction = self._cam_direction
        if direction == "Raster Y":
            return RasterAxis.Y
        if direction == "Raster 45°":
            return RasterAxis.DIAGONAL_45
        if direction == "Raster 135°":
            return RasterAxis.DIAGONAL_135
        if direction == "Raster X":
            return RasterAxis.X

        bounds = np.asarray(mesh.bounds, dtype=float)
        span = bounds[1, :2] - bounds[0, :2]
        return RasterAxis.X if span[0] >= span[1] else RasterAxis.Y

    def _pocket_strategy_for_bounds(self, bounds: np.ndarray) -> PocketStrategy:
        if self._cam_direction == "Offset":
            return PocketStrategy.OFFSET
        if self._cam_direction == "Raster Y":
            return PocketStrategy.RASTER_Y
        if self._cam_direction == "Raster X":
            return PocketStrategy.RASTER_X

        span = np.asarray(bounds, dtype=float)[1, :2] - np.asarray(
            bounds,
            dtype=float,
        )[0, :2]
        return (
            PocketStrategy.RASTER_X
            if span[0] >= span[1]
            else PocketStrategy.RASTER_Y
        )

    def _select_cam_operation(self, operation: str) -> None:
        self._active_cam_operation = operation
        if hasattr(self, "tool_rail"):
            action = self._ui_actions.get(f"cam_{operation}")
            if action is not None:
                self.tool_rail.set_menu_active_action("cam", action)
        labels = {
            "profile": "Profile",
            "silhouette": "Silhouette",
            "pocket": "Pocket",
            "surface": "Surface / Face",
            "vcarve": "V-Carve",
            "engrave": "Engrave",
            "drill": "Drill Features",
            "center_drill": "Center Drill",
            "rough": "3D Rough",
            "finish": "3D Finish",
            "height_map": "Height Map",
            "rest": "3D Rest",
            "waterline": "3D Waterline",
        }

        for name, button in getattr(
            self,
            "_cam_operation_buttons",
            {},
        ).items():
            button.blockSignals(True)
            try:
                button.setChecked(name == operation)
            finally:
                button.blockSignals(False)

        cutter = (
            self.tool_combo.currentData()
            if hasattr(self, "tool_combo")
            else None
        )
        cutter_name = cutter.name if isinstance(cutter, Cutter) else "selected cutter"
        self._set_activity_info(
            f"Toolpath operation\n{labels.get(operation, operation)}\n\n"
            f"Cutter: {cutter_name}\n"
            "Review all generation requirements, then press Generate Toolpaths."
        )
        self._sync_cam_control_relevance()
        self.statusBar().showMessage(
            f"Toolpath operation: {labels.get(operation, operation)}",
            3000,
        )

    def _sync_cam_control_relevance(self) -> None:
        operation = self._active_cam_operation
        is_3d = operation in {
            "rough",
            "finish",
            "height_map",
            "rest",
            "waterline",
        }
        uses_cut_type = operation in {"profile", "pocket", "engrave"}
        uses_entry = operation not in {
            "rough",
            "finish",
            "height_map",
            "rest",
            "waterline",
            "drill",
            "center_drill",
        }
        uses_milling = operation in {
            "profile",
            "silhouette",
            "pocket",
            "surface",
            "engrave",
        }
        uses_direction = is_3d or operation in {"pocket", "surface"}
        uses_detail = is_3d or operation == "vcarve"

        for combo in self._cam_selector_widgets.get("cut_type", []):
            combo.setEnabled(uses_cut_type)
        for combo in self._cam_selector_widgets.get("3d_cut_style", []):
            combo.setEnabled(is_3d)
        for combo in self._cam_selector_widgets.get("direction", []):
            combo.setEnabled(uses_direction)
        for combo in self._cam_selector_widgets.get("entry", []):
            combo.setEnabled(uses_entry)
        for combo in self._cam_selector_widgets.get("milling", []):
            combo.setEnabled(uses_milling)
        for combo in self._cam_selector_widgets.get("linking", []):
            combo.setEnabled(True)

        for widget in self._cam_detail_widgets:
            widget.setEnabled(uses_detail)

        if self._tabs_button is not None:
            self._tabs_button.setEnabled(operation in {"profile", "silhouette"})

    def _toggle_tabs_operation(self) -> None:
        self._tabs_enabled = not self._tabs_enabled
        self._settings.setValue("cam/tabs_enabled", self._tabs_enabled)
        self._settings.sync()
        if self._tabs_button is not None:
            self._tabs_button.setChecked(self._tabs_enabled)
        self.statusBar().showMessage(
            f"Profile tabs {'enabled' if self._tabs_enabled else 'disabled'}",
            2500,
        )

    def _cam_settings(
        self,
        bounds: np.ndarray,
        mesh,
    ) -> BasicCamSettings:
        cut_depth = float(self._settings.value("cam/overall_depth_mm", 0.0))
        return BasicCamSettings(
            safe_z_mm=float(self._settings.value("cam/safe_z_mm", 1.5)),
            feed_mm_min=float(self._settings.value("cam/feed_mm_min", 1000.0)),
            plunge_feed_mm_min=float(
                self._settings.value("cam/plunge_mm_min", 300.0)
            ),
            max_stepdown_mm=float(
                self._settings.value("cam/stepdown_mm", 2.0)
            ),
            stepover_fraction=max(
                0.01,
                min(
                    1.0,
                    float(self._settings.value("cam/stepover_percent", 45.0))
                    / 100.0,
                ),
            ),
            finish_stepover_fraction=self._quality_stepover_fraction(),
            overall_depth_mm=cut_depth if cut_depth > 0.0 else None,
            padding_mm=float(self._settings.value("cam/padding_mm", 0.0)),
            usable_bit_length_mm=(
                float(self._settings.value("cam/usable_bit_length_mm", 0.0))
                or None
            ),
            tab_height_mm=float(
                self._settings.value("cam/tab_height_mm", 2.0)
            ),
            tab_width_mm=float(
                self._settings.value("cam/tab_width_mm", 6.0)
            ),
            tab_count=int(self._settings.value("cam/tab_count", 4)),
            tabs_enabled=self._tabs_enabled,
            milling_direction=self._milling_direction(),
            pocket_strategy=self._pocket_strategy_for_bounds(bounds),
            relief_style=self._relief_style(),
            raster_axis=self._raster_axis_for_mesh(mesh),
            raster_link_mode=self._link_mode(),
            local_link_clearance_mm=float(
                self._settings.value("cam/local_link_clearance_mm", 0.5)
            ),
            direct_link_tolerance_mm=float(
                self._settings.value("cam/direct_link_tolerance_mm", 0.02)
            ),
            ramp_angle_deg=self._ramp_angle(),
        )

    @staticmethod
    def _cam_operation_title(operation: str) -> str:
        return {
            "profile": "Profile",
            "silhouette": "Silhouette",
            "pocket": "Pocket",
            "surface": "Surface / Face",
            "vcarve": "V-Carve",
            "engrave": "Engrave",
            "drill": "Drill Features",
            "center_drill": "Center Drill",
            "rough": "3D Rough",
            "finish": "3D Finish",
            "height_map": "Height Map",
            "rest": "3D Rest",
            "waterline": "3D Waterline",
        }.get(operation, operation.replace("_", " ").title())

    def _update_toolpath_progress(
        self,
        fraction: float,
        status_text: str,
    ) -> None:
        """Update determinate CAM progress and keep the UI repainting."""

        fraction = max(0.0, min(1.0, float(fraction)))
        percent = round(fraction * 100.0)
        text = str(status_text).strip() or "Generating toolpaths"

        bars = [
            getattr(self, "toolpath_progress", None),
            self._toolpath_dialog_progress,
        ]
        changed = (
            percent != self._toolpath_progress_last_value
            or text != self._toolpath_progress_last_text
        )
        for bar in bars:
            if bar is None:
                continue
            bar.setRange(0, 100)
            bar.setValue(percent)
            bar.setFormat(f"{text} · %p%")
            bar.show()

        self._toolpath_progress_last_value = percent
        self._toolpath_progress_last_text = text
        if changed:
            self.statusBar().showMessage(f"{text} — {percent}%")

    def _finish_toolpath_progress(
        self,
        *,
        success: bool,
        message: str,
    ) -> None:
        bars = [
            getattr(self, "toolpath_progress", None),
            self._toolpath_dialog_progress,
        ]
        value = 100 if success else self._toolpath_progress_last_value
        value = max(0, value)
        for bar in bars:
            if bar is None:
                continue
            bar.setRange(0, 100)
            bar.setValue(value)
            bar.setFormat(f"{message} · %p%")
            bar.show()

        status_bar = getattr(self, "toolpath_progress", None)
        if status_bar is not None and success:
            QTimer.singleShot(
                1800,
                lambda bar=status_bar: (
                    bar.hide()
                    if bar.value() == 100
                    else None
                ),
            )

    def _show_toolpath_generation_dialog(self) -> None:
        dialog = self._build_toolpath_generation_dialog()
        dialog.exec()

    def _calculate_toolpath(self) -> None:
        """Compatibility entry point: calculation now begins with review."""

        self._show_toolpath_generation_dialog()

    def _calculate_toolpath_now(self) -> bool:
        """Submit CAM to a separate Python process; never block the Qt loop."""

        if self._background_job is not None:
            self.statusBar().showMessage("Another operation is running", 4000)
            return False
        # Hidden source shapes must never contribute duplicate/obsolete CNC cuts.
        items = [item for item in self.project.items if item.visible and item.mesh is not None]
        cutter = self.tool_combo.currentData()
        if not isinstance(cutter, Cutter):
            self.statusBar().showMessage("Select a valid cutter", 4000)
            return False

        operation = self._active_cam_operation
        if not items and operation != "surface":
            self.statusBar().showMessage(
                "Add geometry before generating this operation", 4000
            )
            return False

        # Only small bounds and QSettings are read on the GUI thread. Mesh
        # transforms, geometry, CAM and path ordering happen in the process.
        specs = []
        for item in items:
            bounds = item.transformed_bounds_mm()
            if bounds is None:
                continue
            settings = self._cam_settings(
                bounds,
                type("_Bounds", (), {"bounds": bounds})(),
            )
            specs.append((item, settings))

        stock = self.project.stock
        stock_bounds = np.array(
            ((0.0, 0.0, -stock.thickness_mm),
             (stock.width_mm, stock.height_mm, 0.0)),
            dtype=float,
        )
        stock_settings = None
        silhouette_settings = None
        if operation == "surface":
            stock_settings = self._cam_settings(
                stock_bounds,
                type("_Bounds", (), {"bounds": stock_bounds})(),
            )
        if operation == "silhouette" and specs:
            bounds = np.vstack(
                (
                    np.vstack([item.transformed_bounds_mm()[0] for item, _ in specs]).min(axis=0),
                    np.vstack([item.transformed_bounds_mm()[1] for item, _ in specs]).max(axis=0),
                )
            )
            silhouette_settings = self._cam_settings(
                bounds,
                type("_Bounds", (), {"bounds": bounds})(),
            )

        if operation == "rest" and not self.project.toolpaths:
            self.statusBar().showMessage(
                "Generate and append roughing/finishing before 3D Rest.", 7000
            )
            return False
        append_to_job = bool(
            self.project.toolpaths and (
                operation == "rest" or self._cam_append_to_job
            )
        )
        self._cam_append_to_job = False
        request = CamRequest(
            operation=operation,
            cutter=cutter,
            cut_type=self._cam_cut_type,
            thickness_mm=stock.thickness_mm,
            stock_width_mm=stock.width_mm,
            stock_height_mm=stock.height_mm,
            settings_by_item=specs,
            stock_settings=stock_settings,
            silhouette_settings=silhouette_settings,
            previous_toolpaths=(
                list(self.project.toolpaths) if append_to_job else None
            ),
            rest_min_remaining_mm=float(
                self._settings.value("cam/rest_min_remaining_mm", 0.15)
            ),
            rest_grid_spacing_mm=float(
                self._settings.value("cam/rest_grid_spacing_mm", 0.75)
            ),
        )
        self._toolpath_progress_last_value = -1
        self._toolpath_progress_last_text = ""
        self._update_toolpath_progress(
            0, f"Preparing {self._cam_operation_title(operation)}"
        )

        def finished(payload: object) -> None:
            if not isinstance(payload, dict):
                raise TypeError("Invalid CAM worker result.")
            paths = payload["toolpaths"]
            if self._simulation_timer.isActive():
                self._simulation_timer.stop()
            if self._simulation_button is not None:
                self._simulation_button.setChecked(False)
            preview = self._toolpath_preview_window
            if preview is not None:
                preview.close()
                self._toolpath_preview_window = None

            self._before_ribbon_mutation(f"calculate {operation}")
            self.project.toolpaths = paths
            self._toolpaths_stale_reason = None
            self._prepared_toolpath_geometry = payload["render_geometry"]
            self._prepared_toolpath_stats = payload
            self.viewport.prepare_toolpath_render_cache(
                paths, self._prepared_toolpath_geometry
            )
            self.viewport.set_toolpaths_visible(True)
            self.viewport.set_simulation_fraction(1.0)
            self.viewport.update()
            self._after_ribbon_mutation(f"calculate {operation}", True)

            count = int(payload["object_count"])
            self._set_activity_info(
                f"Toolpaths ready\n{payload['summary']}\n\n"
                f"Objects: {count}\n"
                f"Cutter: {cutter.name}\n"
                f"Paths: {len(paths):,}\n"
                f"Moves: {int(payload['moves']):,}\n"
                f"Cut distance: {float(payload['cut_mm']):.1f} mm\n"
                f"Rapid distance: {float(payload['rapid_mm']):.1f} mm\n"
                f"Estimated cutting: {float(payload['minutes']):.1f} min"
            )
            self._sync_toolpath_output_state()
            self._finish_toolpath_progress(
                success=True, message="Toolpaths ready"
            )
            self.statusBar().showMessage(
                f"Generated {len(paths)} toolpaths", 6000
            )

        def failed(message: str) -> None:
            self._set_activity_info(f"Toolpath calculation failed\n{message}")
            self._finish_toolpath_progress(
                success=False, message="Generation failed"
            )
            self.statusBar().showMessage(f"Toolpath failed: {message}", 9000)

        return self._start_background_job(
            f"{self._cam_operation_title(operation)} toolpaths",
            request=request,
            on_done=finished,
            on_failed=failed,
            cam_progress=True,
        )

    def _preview_toolpaths(self) -> None:
        if not self.project.toolpaths:
            self.statusBar().showMessage("No calculated toolpaths to preview", 4000)
            return

        existing = self._toolpath_preview_window
        if existing is not None and existing.isVisible():
            existing.showNormal()
            existing.raise_()
            existing.activateWindow()
            return

        window = ToolpathPreviewWindow(
            toolpaths=list(self.project.toolpaths),
            stock=self.project.stock,
            post_settings=self._grbl_post_settings(),
            source_names=self._toolpath_source_names(self.project.toolpaths),
            render_geometry_data=self._prepared_toolpath_geometry,
            estimated_minutes=(
                float(self._prepared_toolpath_stats["minutes"])
                if self._prepared_toolpath_stats is not None
                else None
            ),
            parent=self,
        )
        window.destroyed.connect(
            lambda _obj=None: setattr(
                self,
                "_toolpath_preview_window",
                None,
            )
        )
        self._toolpath_preview_window = window
        window.show()
        window.raise_()
        window.activateWindow()
        self.statusBar().showMessage("Opened toolpath backplot preview", 3000)

    # ------------------------------------------------------------------
    # Cutter tools / feeds and speeds
    # ------------------------------------------------------------------
