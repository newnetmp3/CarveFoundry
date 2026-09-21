"""Camera, drawing, contextual tool options and tracing actions."""
from __future__ import annotations

from dataclasses import replace
from math import atan2, degrees, hypot
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontInfo, QImage
from PySide6.QtWidgets import QDialog, QFileDialog

from carvefoundry.core.fixtures import Fixture
from carvefoundry.core.image_trace import trace_mask
from carvefoundry.core.measurement import measure_xy
from carvefoundry.core.primitives import (
    bitmap_runs_mesh,
    ellipse_mesh,
    line_mesh,
    polygon_mesh,
    rectangle_mesh,
    text_mesh,
)
from carvefoundry.core.project import ProjectItem, TextProperties
from carvefoundry.core.transform import Transform3D
from carvefoundry.core.units import ModelUnits
from carvefoundry.core.vector_path import VectorPath

from .contextual_tool_state import ToolOptionsState
from .image_trace_dialog import ImageTraceDialog, qimage_rgba


class RibbonDesignToolsMixin:
    def _activate_camera_tool(self) -> None:
        """Activate dedicated arcball-style viewport camera control."""

        self._camera_tool_active = True
        self.viewport.set_node_edit_mode(False)
        self.viewport.set_shape_draw_mode(None)
        self.viewport.set_camera_control_mode(True)
        if self._camera_tool_button is not None:
            self._camera_tool_button.blockSignals(True)
            try:
                self._camera_tool_button.setChecked(True)
            finally:
                self._camera_tool_button.blockSignals(False)
        if self._navigation_tool_button is not None:
            self._navigation_tool_button.blockSignals(True)
            try:
                self._navigation_tool_button.setChecked(False)
            finally:
                self._navigation_tool_button.blockSignals(False)
        if hasattr(self, "tool_rail"):
            self.tool_rail.set_active_tool("camera")
        self.statusBar().showMessage(
            "Camera / Arcball — left-drag orbits • middle/right-drag pans • "
            "wheel zooms",
            3500,
        )

    def _activate_navigation_tool(self) -> None:
        """Return the viewport to object selection / marquee mode."""

        self._camera_tool_active = False
        self.viewport.set_node_edit_mode(False)
        self.viewport.set_camera_control_mode(False)
        self.viewport.set_shape_draw_mode(None)
        if self._camera_tool_button is not None:
            self._camera_tool_button.blockSignals(True)
            try:
                self._camera_tool_button.setChecked(False)
            finally:
                self._camera_tool_button.blockSignals(False)
        self.statusBar().showMessage(
            "Select tool — click objects to select • drag empty space for marquee • "
            "Alt+drag orbits",
            3500,
        )

    def _apply_active_tool(self) -> None:
        """Finish the current draw tool and keep completed geometry."""

        if self._active_shape_tool is None:
            return
        label = self._active_shape_tool.title()
        self.viewport.set_shape_draw_mode(None)
        self.statusBar().showMessage(
            f"{label} tool applied — returned to Select",
            2500,
        )

    def _cancel_active_tool(self) -> None:
        """Cancel the current draw tool/preview without deleting finished items."""

        if self._active_shape_tool is None:
            return
        label = self._active_shape_tool.title()
        self.viewport.set_shape_draw_mode(None)
        self.statusBar().showMessage(
            f"{label} tool canceled — returned to Select",
            2500,
        )

    def _sync_tool_options_bar(self, mode: str | None) -> None:
        """Show only options relevant to the active paint-style tool."""

        bar = getattr(self, "tool_options_bar", None)
        if bar is None:
            return
        active = bool(mode)
        bar.setVisible(active)
        if not active:
            return

        options = ToolOptionsState.for_mode(mode)
        self.tool_options_title.setText(f"{mode.title()} Tool")
        self.tool_options_depth_spin.blockSignals(True)
        self.tool_options_depth_spin.setValue(self._tool_option_depth_mm)
        self.tool_options_depth_spin.blockSignals(False)
        self.tool_options_depth_label.setVisible(options.depth)
        self.tool_options_depth_spin.setVisible(options.depth)
        is_fixture = options.fixture
        for element in (
            self.tool_options_fixture_top_label,
            self.tool_options_fixture_top_spin,
            self.tool_options_fixture_clearance_label,
            self.tool_options_fixture_clearance_spin,
        ):
            element.setVisible(is_fixture)
        if is_fixture:
            self.tool_options_fixture_top_spin.blockSignals(True)
            self.tool_options_fixture_top_spin.setValue(self._fixture_top_z_mm)
            self.tool_options_fixture_top_spin.blockSignals(False)
            self.tool_options_fixture_clearance_spin.blockSignals(True)
            self.tool_options_fixture_clearance_spin.setValue(
                self._fixture_clearance_mm
            )
            self.tool_options_fixture_clearance_spin.blockSignals(False)
        self.tool_options_fixture_size_label.setVisible(is_fixture)
        if is_fixture:
            self.tool_options_fixture_size_label.setText(
                "Drag a rectangle on the stock to place a fixture"
            )
        self.tool_options_measure_label.setVisible(options.measure)
        self.tool_options_measure_clear.setVisible(options.measure)
        if options.measure:
            self.tool_options_measure_label.setText(
                self._measurement.label if self._measurement is not None
                else "Drag two points on stock top (XY · Z0)"
            )

        is_polygon = options.polygon
        self.tool_options_polygon_label.setVisible(is_polygon)
        self.tool_options_polygon_sides.setVisible(is_polygon)
        if is_polygon:
            self.tool_options_polygon_sides.blockSignals(True)
            self.tool_options_polygon_sides.setValue(
                self._tool_option_polygon_sides
            )
            self.tool_options_polygon_sides.blockSignals(False)

        is_line = options.line
        self.tool_options_line_width_label.setVisible(is_line)
        self.tool_options_line_width_spin.setVisible(is_line)
        if is_line:
            self.tool_options_line_width_spin.blockSignals(True)
            self.tool_options_line_width_spin.setValue(
                self._tool_option_line_width_mm
            )
            self.tool_options_line_width_spin.blockSignals(False)

        is_pen = options.pen
        self.tool_options_pen_width_label.setVisible(is_pen)
        self.tool_options_pen_width_spin.setVisible(is_pen)
        self.tool_options_pen_smoothing_label.setVisible(is_pen)
        self.tool_options_pen_smoothing_spin.setVisible(is_pen)
        self.tool_options_pen_spacing_label.setVisible(is_pen)
        self.tool_options_pen_spacing_spin.setVisible(is_pen)
        self.tool_options_pen_close_check.setVisible(is_pen)
        if is_pen:
            self.tool_options_pen_width_spin.blockSignals(True)
            self.tool_options_pen_width_spin.setValue(
                self._tool_option_pen_width_mm
            )
            self.tool_options_pen_width_spin.blockSignals(False)
            self.tool_options_pen_smoothing_spin.blockSignals(True)
            self.tool_options_pen_smoothing_spin.setValue(
                self._tool_option_pen_smoothing
            )
            self.tool_options_pen_smoothing_spin.blockSignals(False)
            self.tool_options_pen_spacing_spin.blockSignals(True)
            self.tool_options_pen_spacing_spin.setValue(
                self._tool_option_pen_spacing_mm
            )
            self.tool_options_pen_spacing_spin.blockSignals(False)
            self.tool_options_pen_close_check.blockSignals(True)
            self.tool_options_pen_close_check.setChecked(
                self._tool_option_pen_close_path
            )
            self.tool_options_pen_close_check.blockSignals(False)
            self.viewport.set_pen_sample_spacing(
                self._tool_option_pen_spacing_mm
            )

        is_text = options.text
        self.tool_options_text_label.setVisible(is_text)
        self.tool_options_text_edit.setVisible(is_text)
        self.tool_options_font_label.setVisible(is_text)
        self.tool_options_font_value.setVisible(is_text)
        if is_text:
            self.tool_options_text_edit.blockSignals(True)
            self.tool_options_text_edit.setText(self._tool_option_text)
            self.tool_options_text_edit.blockSignals(False)
            family = (
                self._selected_text_font_family()
                if hasattr(self, "_selected_text_font_family")
                else QFontInfo(QFont()).family()
            )
            self.tool_options_font_value.setText(family)

    def _fixture_top_changed(self, value: float) -> None:
        self._fixture_top_z_mm = float(value)

    def _fixture_clearance_changed(self, value: float) -> None:
        self._fixture_clearance_mm = float(value)

    def _clear_measurement(self) -> None:
        self._measurement = None
        self.viewport.set_measurement(None)
        if hasattr(self, "tool_options_measure_label"):
            self.tool_options_measure_label.setText(
                "Drag two points on stock top (XY · Z0)"
            )
        self.statusBar().showMessage("Measurement cleared", 2500)

    def _tool_option_depth_changed(self, value: float) -> None:
        self._tool_option_depth_mm = float(value)

    def _tool_option_line_width_changed(self, value: float) -> None:
        self._tool_option_line_width_mm = float(value)

    def _tool_option_pen_width_changed(self, value: float) -> None:
        self._tool_option_pen_width_mm = float(value)

    def _tool_option_pen_smoothing_changed(self, value: int) -> None:
        self._tool_option_pen_smoothing = max(0, min(100, int(value)))

    def _tool_option_pen_spacing_changed(self, value: float) -> None:
        self._tool_option_pen_spacing_mm = max(0.02, float(value))
        if hasattr(self, "viewport"):
            self.viewport.set_pen_sample_spacing(
                self._tool_option_pen_spacing_mm
            )

    def _tool_option_pen_close_changed(self, checked: bool) -> None:
        self._tool_option_pen_close_path = bool(checked)

    def _tool_option_polygon_sides_changed(self, value: int) -> None:
        self._tool_option_polygon_sides = int(value)

    def _tool_option_text_changed(self, text: str) -> None:
        self._tool_option_text = text or "Text"

    def _set_shape_tool(self, tool: str) -> None:
        """Activate one paint-style shape tool in the viewport."""

        self._camera_tool_active = False
        self.viewport.set_node_edit_mode(False)
        self.viewport.set_camera_control_mode(False)
        if self._camera_tool_button is not None:
            self._camera_tool_button.blockSignals(True)
            try:
                self._camera_tool_button.setChecked(False)
            finally:
                self._camera_tool_button.blockSignals(False)

        button = self._shape_tool_buttons.get(tool)
        wants_active = bool(button is None or button.isChecked())
        if tool == "fixture" and hasattr(self, "tool_rail"):
            rail_button = self.tool_rail.buttons.get("fixture")
            if rail_button is not None:
                wants_active = rail_button.isChecked()
        if self._active_shape_tool == tool and not wants_active:
            self._activate_navigation_tool()
            return

        self._active_shape_tool = tool
        for name, shape_button in self._shape_tool_buttons.items():
            shape_button.blockSignals(True)
            try:
                shape_button.setChecked(name == tool)
            finally:
                shape_button.blockSignals(False)

        if self._navigation_tool_button is not None:
            self._navigation_tool_button.blockSignals(True)
            try:
                self._navigation_tool_button.setChecked(False)
            finally:
                self._navigation_tool_button.blockSignals(False)

        if tool == "pen":
            self.viewport.set_pen_sample_spacing(
                self._tool_option_pen_spacing_mm
            )
        self.viewport.set_shape_draw_mode(tool)
        label = tool.title()
        if tool == "pen":
            message = (
                "Pen tool — draw freehand directly on the stock • "
                "Alt+drag orbits • Esc returns to Select"
            )
        else:
            message = (
                f"{label} tool — drag on the stock to draw • Shift constrains • "
                "Alt+drag orbits • Esc returns to Select"
            )
        self.statusBar().showMessage(message)

    def _shape_draw_mode_changed(self, mode: str) -> None:
        self._active_shape_tool = mode or None
        for name, button in self._shape_tool_buttons.items():
            button.blockSignals(True)
            try:
                button.setChecked(name == mode)
            finally:
                button.blockSignals(False)
        if self._navigation_tool_button is not None:
            self._navigation_tool_button.blockSignals(True)
            try:
                self._navigation_tool_button.setChecked(
                    not bool(mode) and not self._camera_tool_active
                )
            finally:
                self._navigation_tool_button.blockSignals(False)
        if self._camera_tool_button is not None:
            self._camera_tool_button.blockSignals(True)
            try:
                self._camera_tool_button.setChecked(
                    not bool(mode) and self._camera_tool_active
                )
            finally:
                self._camera_tool_button.blockSignals(False)
        if hasattr(self, "tool_rail"):
            active = (
                "camera"
                if not mode and self._camera_tool_active
                else (mode or "select")
            )
            self.tool_rail.set_active_tool(active)
        self._sync_tool_options_bar(mode or None)

    def _add_drawn_item(
        self,
        name: str,
        kind: str,
        mesh,
        transform: Transform3D,
        *,
        text_properties: TextProperties | None = None,
        vector_path: VectorPath | None = None,
    ) -> ProjectItem:
        item = ProjectItem(
            name=self._unique_item_name(name),
            kind=kind,
            mesh=mesh,
            transform=transform,
            source_units=ModelUnits.MILLIMETERS,
            text_properties=text_properties,
            vector_path=vector_path,
        )
        self._before_ribbon_mutation(f"draw {kind}")
        self.project.items.append(item)
        self._refresh_project_list(len(self.project.items))
        self.viewport.update()
        self._after_ribbon_mutation(f"draw {kind}", True)
        self.statusBar().showMessage(f"Drew {item.name}", 2500)
        return item

    def _shape_drag_updated(
        self, tool: str, x0: float, y0: float, x1: float, y1: float,
    ) -> None:
        """Show accurate dimensions while dragging; commit only on release."""

        if tool == "measure":
            self.tool_options_measure_label.setText(
                measure_xy((x0, y0), (x1, y1)).label
            )
        elif tool == "fixture":
            self.tool_options_fixture_size_label.setText(
                f"XY {abs(x1 - x0):.3f} × {abs(y1 - y0):.3f} mm"
            )

    def _shape_drawn(
        self,
        tool: str,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
    ) -> None:
        """Create geometry from a click-drag gesture on the stock."""

        min_x, max_x = sorted((float(x0), float(x1)))
        min_y, max_y = sorted((float(y0), float(y1)))
        width = max_x - min_x
        height = max_y - min_y
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        depth = self._tool_option_depth_mm

        if tool == "measure":
            reading = measure_xy((x0, y0), (x1, y1))
            self._measurement = reading
            self.viewport.set_measurement(
                reading.start_xy, reading.end_xy
            )
            self.tool_options_measure_label.setText(reading.label)
            self.statusBar().showMessage(reading.label, 12000)
            return

        if tool == "fixture":
            if width < 0.1 or height < 0.1:
                self.statusBar().showMessage(
                    "Draw a fixture with positive X and Y dimensions", 4000
                )
                return
            fixture = Fixture(
                name=f"Fixture {len(self.project.fixtures) + 1}",
                x_min_mm=min_x,
                y_min_mm=min_y,
                x_max_mm=max_x,
                y_max_mm=max_y,
                top_z_mm=self._fixture_top_z_mm,
                clearance_mm=self._fixture_clearance_mm,
            )
            fixture.validate()
            self._before_ribbon_mutation("draw fixture")
            self.project.fixtures.append(fixture)
            self.viewport.update()
            self._after_ribbon_mutation("draw fixture", True)
            self.statusBar().showMessage(
                f"Added {fixture.name} — top Z{fixture.top_z_mm:g} mm, "
                f"clearance {fixture.clearance_mm:g} mm", 6000
            )
            return

        if tool in {"rectangle", "ellipse", "polygon", "text"} and (
            width < 0.10 or height < 0.10
        ):
            self.statusBar().showMessage("Drag farther to create the shape", 2500)
            return

        if tool == "rectangle":
            mesh = rectangle_mesh(width, height, depth)
            transform = Transform3D(
                translation_mm=(center_x, center_y, 0.0)
            )
            self._add_drawn_item("Rectangle", "rectangle", mesh, transform)
            return

        if tool == "ellipse":
            mesh = ellipse_mesh(width, height, depth)
            transform = Transform3D(
                translation_mm=(center_x, center_y, 0.0)
            )
            self._add_drawn_item("Ellipse", "ellipse", mesh, transform)
            return

        if tool == "polygon":
            # Start from a unit regular hexagon and stretch it to the drag box.
            mesh = polygon_mesh(
                self._tool_option_polygon_sides,
                1.0,
                depth,
            )
            transform = Transform3D(
                translation_mm=(center_x, center_y, 0.0),
                scale_xyz=(width, height, 1.0),
            )
            self._add_drawn_item("Polygon", "polygon", mesh, transform)
            return

        if tool == "line":
            dx = float(x1 - x0)
            dy = float(y1 - y0)
            length = hypot(dx, dy)
            if length < 0.10:
                self.statusBar().showMessage("Drag farther to create the line", 2500)
                return
            mesh = line_mesh(
                length,
                self._tool_option_line_width_mm,
                depth,
            )
            transform = Transform3D(
                translation_mm=(
                    (float(x0) + float(x1)) / 2.0,
                    (float(y0) + float(y1)) / 2.0,
                    0.0,
                ),
                rotation_deg=(0.0, 0.0, degrees(atan2(dy, dx))),
            )
            self._add_drawn_item(
                "Line", "line", mesh, transform,
                vector_path=VectorPath(
                    points_xy=((-length / 2.0, 0.0), (length / 2.0, 0.0)),
                    width_mm=self._tool_option_line_width_mm,
                    depth_mm=depth,
                ),
            )
            return

        if tool == "text":
            size_pt = max(6.0, height * 72.0 / 25.4)
            properties = TextProperties(
                content=self._tool_option_text or "Text",
                font_family=(
                    self._selected_text_font_family()
                    if hasattr(self, "_selected_text_font_family")
                    else QFontInfo(QFont()).family()
                ),
                font_style="Regular",
                size_pt=size_pt,
                box_width_mm=max(width, 0.1),
                depth_mm=depth,
            )
            try:
                mesh = text_mesh(properties=properties)
                source_width = float(mesh.dimensions[0])
                if source_width > width and source_width > 1e-9:
                    properties = replace(
                        properties,
                        size_pt=max(
                            4.0,
                            properties.size_pt * width / source_width,
                        ),
                    )
                    mesh = text_mesh(properties=properties)
            except (RuntimeError, ValueError) as exc:
                self.statusBar().showMessage(str(exc), 5000)
                return

            bounds = np.asarray(mesh.bounds, dtype=float)
            transform = Transform3D(
                translation_mm=(
                    min_x - float(bounds[0, 0]),
                    min_y - float(bounds[0, 1]),
                    -float(bounds[1, 2]),
                )
            )
            self._add_drawn_item(
                "Text",
                "text",
                mesh,
                transform,
                text_properties=properties,
            )
            self._focus_text_editor()
            return

    def _activate_measure_tool(self) -> None:
        self._set_shape_tool("measure")

    def _activate_fixture_tool(self) -> None:
        self._set_shape_tool("fixture")

    def _create_rectangle(self) -> None:
        self._set_shape_tool("rectangle")

    def _create_ellipse(self) -> None:
        self._set_shape_tool("ellipse")

    def _create_polygon(self) -> None:
        self._set_shape_tool("polygon")

    def _create_line(self) -> None:
        self._set_shape_tool("line")

    def _create_text(self) -> None:
        self._set_shape_tool("text")

    def _create_pen_path(self) -> None:
        self._set_shape_tool("pen")

    def _smooth_pen_points(
        self,
        points_xy: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        """Apply adjustable freehand smoothing while preserving endpoints."""

        points = np.asarray(points_xy, dtype=float)
        if len(points) < 3 or self._tool_option_pen_smoothing <= 0:
            return [tuple(map(float, point)) for point in points]

        blend = self._tool_option_pen_smoothing / 100.0
        passes = 1 + self._tool_option_pen_smoothing // 34
        smoothed = points.copy()
        for _ in range(passes):
            averaged = smoothed.copy()
            averaged[1:-1] = (
                smoothed[:-2] + 2.0 * smoothed[1:-1] + smoothed[2:]
            ) / 4.0
            smoothed[1:-1] = (
                (1.0 - blend) * smoothed[1:-1]
                + blend * averaged[1:-1]
            )
        return [tuple(map(float, point)) for point in smoothed]

    def _freehand_pen_drawn(self, points: object) -> None:
        """Create one persistent pen object from a viewport freehand stroke."""

        try:
            captured = [
                (float(point[0]), float(point[1]))
                for point in points
            ]
        except (TypeError, ValueError, IndexError):
            self.statusBar().showMessage("Invalid freehand pen stroke", 3000)
            return

        if len(captured) < 2:
            return

        captured = self._smooth_pen_points(captured)
        if (
            self._tool_option_pen_close_path
            and len(captured) >= 3
            and hypot(
                captured[-1][0] - captured[0][0],
                captured[-1][1] - captured[0][1],
            )
            > 1e-9
        ):
            captured.append(captured[0])

        path = VectorPath(
            points_xy=tuple(
                captured[:-1] if (
                    len(captured) >= 3 and captured[0] == captured[-1]
                ) else captured
            ),
            width_mm=self._tool_option_pen_width_mm,
            depth_mm=self._tool_option_depth_mm,
            closed=bool(
                len(captured) >= 3 and captured[0] == captured[-1]
            ),
        )
        try:
            mesh = path.mesh_asset()
        except ValueError as exc:
            self.statusBar().showMessage(f"Pen stroke failed: {exc}", 5000)
            return

        self._add_drawn_item(
            "Pen Stroke",
            "pen",
            mesh,
            Transform3D(),
            vector_path=path,
        )

    def _trace_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Trace Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)",
        )
        if not path:
            return

        source = QImage(path)
        if source.isNull():
            self.statusBar().showMessage(
                "Could not load the selected image for tracing.", 6000,
            )
            return
        dialog = ImageTraceDialog(
            self,
            source,
            source_name=path,
            default_width_mm=min(120.0, self.project.stock.width_mm * 0.7),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # The dialog has already computed the original pixel dimensions and
        # captured every setting. No hard-coded trace resolution ceiling.
        settings = dialog.settings()
        name = Path(path).stem + " trace"
        source = QImage(source)  # Hold a reference for the background job.

        def trace(progress):
            progress(0.03, "Preparing source image")
            if (
                source.width() == settings.target_width
                and source.height() == settings.target_height
            ):
                image = source
            else:
                image = source.scaled(
                    settings.target_width,
                    settings.target_height,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            progress(
                0.20,
                f"Tracing {image.width():,} × {image.height():,} pixels",
            )
            mask = trace_mask(
                qimage_rgba(image),
                threshold=settings.threshold,
                invert=settings.invert,
            )
            progress(0.65, "Building relief mesh from selected pixels")
            mesh = bitmap_runs_mesh(
                mask,
                width_mm=settings.width_mm,
                depth_mm=settings.depth_mm,
            )
            progress(0.98, "Trace ready")
            return mesh

        self._start_background_job(
            "Trace image",
            task=trace,
            on_done=lambda mesh: self._add_generated_item(name, "trace", mesh),
        )

    # ------------------------------------------------------------------
    # Toolpaths / CAM
    # ------------------------------------------------------------------
