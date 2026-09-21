"""Qt widget shell around the native OpenGL CAD renderer.

The OpenGL renderer owns rendering and interaction math. This module owns only
the QWidget composition around that native window: rulers, projection/view
controls, and signal forwarding.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .native_viewport import _NativeOpenGLViewport

if TYPE_CHECKING:
    from carvefoundry.core.project import Project


class _RulerBand(QWidget):
    """Thin screen-space ruler drawn outside the native OpenGL child window."""

    def __init__(self, side: str) -> None:
        super().__init__()
        self.side = side
        self._ticks: list[tuple[float, str]] = []
        self.setObjectName("ViewportRuler")
        if side in {"top", "bottom"}:
            self.setFixedHeight(26)
        else:
            self.setFixedWidth(58)

    def set_ticks(self, ticks: list[tuple[float, str]]) -> None:
        # Give the coordinate origin first claim on ruler space.  Remaining
        # labels are then laid out spatially and skipped only when necessary.
        self._ticks = sorted(
            ticks,
            key=lambda item: (
                not item[1].endswith(" 0"),
                item[0],
            ),
        )
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(self.rect(), QColor(14, 20, 37))
        painter.setPen(QColor(105, 117, 139))

        horizontal = self.side in {"top", "bottom"}
        if horizontal:
            edge_y = self.height() - 1 if self.side == "top" else 0
            painter.drawLine(0, edge_y, self.width(), edge_y)
        else:
            edge_x = self.width() - 1 if self.side == "left" else 0
            painter.drawLine(edge_x, 0, edge_x, self.height())

        painter.setPen(QColor(199, 208, 224))
        metrics = painter.fontMetrics()
        occupied: list[tuple[float, float]] = []

        def overlaps(start: float, end: float, gap: float) -> bool:
            return any(
                start < used_end + gap and end > used_start - gap
                for used_start, used_end in occupied
            )

        for position, label in self._ticks:
            if horizontal:
                text_width = metrics.horizontalAdvance(label)
                start = max(
                    2.0,
                    min(
                        self.width() - text_width - 2.0,
                        position - text_width / 2.0,
                    ),
                )
                end = start + text_width
                if overlaps(start, end, 7.0):
                    continue
                if self.side == "top":
                    painter.drawLine(
                        int(position),
                        self.height() - 1,
                        int(position),
                        self.height() - 6,
                    )
                    text_y = 2
                else:
                    painter.drawLine(int(position), 0, int(position), 5)
                    text_y = 8
                painter.drawText(int(start), text_y + metrics.ascent(), label)
                occupied.append((start, end))
            else:
                text_height = metrics.height()
                start_y = max(
                    1.0,
                    min(
                        self.height() - text_height - 1.0,
                        position - text_height / 2.0,
                    ),
                )
                end_y = start_y + text_height
                if overlaps(start_y, end_y, 5.0):
                    continue
                if self.side == "left":
                    painter.drawLine(
                        self.width() - 1,
                        int(position),
                        self.width() - 6,
                        int(position),
                    )
                    rect_x = 2
                    text_width = self.width() - rect_x - 10
                    align = Qt.AlignmentFlag.AlignRight
                else:
                    painter.drawLine(0, int(position), 5, int(position))
                    rect_x = 10
                    text_width = self.width() - rect_x - 3
                    align = Qt.AlignmentFlag.AlignLeft
                painter.drawText(
                    rect_x,
                    int(start_y),
                    text_width,
                    text_height,
                    int(align | Qt.AlignmentFlag.AlignVCenter),
                    label,
                )
                occupied.append((start_y, end_y))


class MeshViewport(QWidget):
    """Widget wrapper around a native QOpenGLWindow CAD viewport."""

    viewSettingsChanged = Signal()
    itemSelectionRequested = Signal(int)
    selectionRequested = Signal(object, str)
    itemContextMenuRequested = Signal(int, QPoint)
    itemTransformStarted = Signal(int)
    itemTransformChanged = Signal(int)
    itemTransformFinished = Signal(int)
    shapeDrawRequested = Signal(str, float, float, float, float)
    shapeDragUpdated = Signal(str, float, float, float, float)
    freehandStrokeRequested = Signal(object)
    shapeDrawModeChanged = Signal(str)
    nodeMoveRequested = Signal(int, int, float, float)
    nodeEditModeChanged = Signal(bool)

    ISOMETRIC_ELEVATION_DEG = 35.26438968

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self.setObjectName("MeshViewport")
        self.setMinimumSize(360, 260)

        self._renderer = _NativeOpenGLViewport(project)
        self._renderer.rendererStatusChanged.connect(self._renderer_status_changed)
        self._renderer.orbitStarted.connect(self._orbit_started)
        self._renderer.fitRequested.connect(self.fit_view)
        self._renderer.viewChanged.connect(self._update_rulers)
        self._renderer.itemSelectionRequested.connect(
            self.itemSelectionRequested.emit
        )
        self._renderer.selectionRequested.connect(
            self.selectionRequested.emit
        )
        self._renderer.itemContextMenuRequested.connect(
            self.itemContextMenuRequested.emit
        )
        self._renderer.itemTransformStarted.connect(
            self.itemTransformStarted.emit
        )
        self._renderer.itemTransformChanged.connect(
            self.itemTransformChanged.emit
        )
        self._renderer.itemTransformFinished.connect(
            self.itemTransformFinished.emit
        )
        self._renderer.shapeDrawRequested.connect(
            self.shapeDrawRequested.emit
        )
        self._renderer.shapeDragUpdated.connect(
            self.shapeDragUpdated.emit
        )
        self._renderer.freehandStrokeRequested.connect(
            self.freehandStrokeRequested.emit
        )
        self._renderer.shapeDrawModeChanged.connect(
            self.shapeDrawModeChanged.emit
        )
        self._renderer.nodeMoveRequested.connect(self.nodeMoveRequested.emit)
        self._renderer.nodeEditModeChanged.connect(self.nodeEditModeChanged.emit)

        self._container = QWidget.createWindowContainer(self._renderer, self)
        self._container.setObjectName("NativeViewportContainer")
        self._container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._container.setMinimumSize(360, 220)

        self._rulers_visible = True
        self._top_ruler = _RulerBand("top")
        self._bottom_ruler = _RulerBand("bottom")
        self._left_ruler = _RulerBand("left")
        self._right_ruler = _RulerBand("right")
        self._ruler_bands = (
            self._top_ruler,
            self._bottom_ruler,
            self._left_ruler,
            self._right_ruler,
        )

        self._viewport_shell = QWidget()
        self._viewport_shell.setObjectName("ViewportShell")
        shell_layout = QGridLayout(self._viewport_shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self._top_ruler, 0, 1)
        shell_layout.addWidget(self._left_ruler, 1, 0)
        shell_layout.addWidget(self._container, 1, 1)
        shell_layout.addWidget(self._right_ruler, 1, 2)
        shell_layout.addWidget(self._bottom_ruler, 2, 1)
        shell_layout.setRowStretch(1, 1)
        shell_layout.setColumnStretch(1, 1)

        self._status_label = QLabel("Native OpenGL initializing…")
        self._status_label.setObjectName("Muted")

        self._projection_combo = QComboBox()
        self._projection_combo.addItems(("Orthographic", "Perspective"))
        self._projection_combo.setCurrentText("Perspective")
        self._projection_combo.currentTextChanged.connect(self._projection_changed)

        self._view_combo = QComboBox()
        self._view_combo.addItems(
            ("Free", "Isometric", "Top", "Bottom", "Front", "Back", "Left", "Right")
        )
        self._view_combo.setCurrentText("Top")
        self._view_combo.currentTextChanged.connect(self._view_changed)

        self._controls = QWidget()
        self._controls.setObjectName("ViewportViewControls")
        controls_layout = QHBoxLayout(self._controls)
        controls_layout.setContentsMargins(7, 4, 7, 4)
        controls_layout.setSpacing(6)
        controls_layout.addWidget(self._status_label)
        controls_layout.addStretch(1)
        controls_layout.addWidget(QLabel("Projection"))
        controls_layout.addWidget(self._projection_combo)
        controls_layout.addWidget(QLabel("View"))
        controls_layout.addWidget(self._view_combo)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._controls)
        layout.addWidget(self._viewport_shell, 1)
        self._update_rulers()

    @property
    def project(self) -> Project | None:
        return self._renderer.project

    @property
    def selected_item_index(self) -> int | None:
        return self._renderer.selected_item_index

    @property
    def yaw_deg(self) -> float:
        return self._renderer.yaw_deg

    @yaw_deg.setter
    def yaw_deg(self, value: float) -> None:
        self._renderer.yaw_deg = value

    @property
    def elevation_deg(self) -> float:
        return self._renderer.elevation_deg

    @elevation_deg.setter
    def elevation_deg(self, value: float) -> None:
        self._renderer.elevation_deg = value

    @property
    def zoom(self) -> float:
        return self._renderer.zoom

    @property
    def projection_mode(self) -> str:
        return self._renderer.projection_mode

    @property
    def view_name(self) -> str:
        return self._view_combo.currentText()

    @view_name.setter
    def view_name(self, value: str) -> None:
        self._set_view_combo(value)

    @property
    def show_stock(self) -> bool:
        return self._renderer.show_stock

    @show_stock.setter
    def show_stock(self, value: bool) -> None:
        self._renderer.show_stock = bool(value)

    @property
    def show_grid(self) -> bool:
        return self._renderer.show_grid

    @show_grid.setter
    def show_grid(self, value: bool) -> None:
        self._renderer.show_grid = bool(value)
        self._update_rulers()

    @property
    def toolpaths_visible(self) -> bool:
        return self._renderer.show_toolpaths

    @property
    def rapids_visible(self) -> bool:
        return self._renderer.show_rapids

    @property
    def simulation_fraction(self) -> float:
        return self._renderer.simulation_fraction

    @property
    def toolpath_points_visible(self) -> bool:
        return self._renderer.show_toolpath_points

    @property
    def shape_draw_mode(self) -> str | None:
        return self._renderer.shape_draw_mode

    @property
    def transform_interaction_kind(self) -> str | None:
        return self._renderer.transform_interaction_kind

    @property
    def camera_control_mode(self) -> bool:
        return self._renderer.camera_control_mode

    @property
    def transform_orientation(self) -> str:
        return self._renderer.transform_orientation

    @property
    def snap_enabled(self) -> bool:
        return self._renderer.snap_enabled

    @property
    def snap_step_mm(self) -> float:
        return self._renderer.snap_step_mm

    @property
    def isolated(self) -> bool:
        return self._renderer.isolated

    def set_camera_control_mode(self, enabled: bool) -> None:
        self._renderer.set_camera_control_mode(enabled)

    def set_shape_draw_mode(self, mode: str | None) -> None:
        self._renderer.set_shape_draw_mode(mode)

    def set_node_edit_mode(self, enabled: bool) -> None:
        self._renderer.set_node_edit_mode(enabled)

    def set_pen_sample_spacing(self, spacing_mm: float) -> None:
        self._renderer.set_pen_sample_spacing(spacing_mm)

    def set_measurement(
        self, start_xy: tuple[float, float] | None,
        end_xy: tuple[float, float] | None = None,
    ) -> None:
        self._renderer.set_measurement(start_xy, end_xy)

    @property
    def reverse_horizontal_drag(self) -> bool:
        return self._renderer.reverse_horizontal_drag

    @property
    def invert_vertical_drag(self) -> bool:
        return self._renderer.invert_vertical_drag

    @property
    def rulers_visible(self) -> bool:
        return self._rulers_visible

    @property
    def view_controls_visible(self) -> bool:
        return self._controls.isVisible()

    def set_view_controls_visible(self, visible: bool) -> None:
        self._controls.setVisible(bool(visible))

    def set_rulers_visible(self, visible: bool) -> None:
        self._rulers_visible = bool(visible)
        for band in self._ruler_bands:
            band.setVisible(self._rulers_visible)
        self._update_rulers()

    def _update_rulers(self) -> None:
        if not hasattr(self, "_ruler_bands") or not self._rulers_visible:
            return
        ticks = self._renderer.ruler_ticks()
        self._top_ruler.set_ticks(ticks["top"])
        self._bottom_ruler.set_ticks(ticks["bottom"])
        self._left_ruler.set_ticks(ticks["left"])
        self._right_ruler.set_ticks(ticks["right"])

    def set_project(
        self,
        project: Project,
        *,
        fit_view: bool = True,
    ) -> None:
        self._renderer.set_project(project, fit_view=fit_view)
        self._update_empty_status()

    def set_selected_item(self, index: int | None) -> None:
        self._renderer.set_selected_item(index)
        self._update_empty_status()

    def set_selected_items(
        self,
        indices: list[int] | tuple[int, ...] | set[int],
        *,
        primary: int | None = None,
    ) -> None:
        self._renderer.set_selected_items(indices, primary=primary)
        self._update_empty_status()

    def prepare_mesh_upload(
        self,
        source_mesh: object,
        vertex_bytes: bytes,
        vertex_count: int,
    ) -> None:
        self._renderer.prepare_mesh_upload(
            source_mesh,
            vertex_bytes,
            vertex_count,
        )

    def prepare_toolpath_render_cache(
        self,
        toolpaths: list,
        prepared: dict[str, object],
    ) -> bool:
        return self._renderer.prepare_toolpath_render_cache(toolpaths, prepared)

    def set_toolpaths_visible(self, visible: bool) -> None:
        self._renderer.set_toolpaths_visible(visible)

    def set_rapids_visible(self, visible: bool) -> None:
        self._renderer.set_rapids_visible(visible)

    def set_toolpath_points_visible(self, visible: bool) -> None:
        self._renderer.set_toolpath_points_visible(visible)

    def set_toolpath_marker(
        self,
        xyz: tuple[float, float, float] | None,
    ) -> None:
        self._renderer.set_toolpath_marker(xyz)

    def set_simulation_fraction(self, fraction: float) -> None:
        self._renderer.set_simulation_fraction(fraction)

    def set_reverse_horizontal_drag(self, enabled: bool) -> None:
        self._renderer.set_reverse_horizontal_drag(enabled)

    def set_invert_vertical_drag(self, enabled: bool) -> None:
        self._renderer.set_invert_vertical_drag(enabled)

    def set_transform_orientation(self, orientation: str) -> None:
        self._renderer.set_transform_orientation(orientation)

    def set_transform_snapping(
        self,
        enabled: bool,
        step_mm: float | None = None,
    ) -> None:
        self._renderer.set_transform_snapping(enabled, step_mm)

    def isolate_selected(self) -> bool:
        return self._renderer.isolate_selected()

    def show_all_items(self) -> None:
        self._renderer.show_all_items()

    def frame_selected(self) -> bool:
        return self._renderer.frame_selected()

    def fit_view(self) -> None:
        self._renderer.fit_view()

    def toggle_stock(self) -> None:
        self._renderer.toggle_stock()

    def toggle_grid(self) -> None:
        self._renderer.toggle_grid()
        self._update_rulers()

    def update(self, *args) -> None:
        self._renderer.requestUpdate()
        self._update_rulers()
        super().update(*args)

    def _set_projection_combo(self, text: str) -> None:
        self._projection_combo.blockSignals(True)
        try:
            self._projection_combo.setCurrentText(text)
        finally:
            self._projection_combo.blockSignals(False)

    def _set_view_combo(self, text: str) -> None:
        self._view_combo.blockSignals(True)
        try:
            self._view_combo.setCurrentText(text)
        finally:
            self._view_combo.blockSignals(False)

    def _projection_changed(self, text: str) -> None:
        if text == "Perspective":
            self.set_perspective_view()
        else:
            self.set_orthographic_view()

    def _view_changed(self, text: str) -> None:
        if text == "Free":
            self._renderer.requestUpdate()
            self.viewSettingsChanged.emit()
        elif text == "Isometric":
            self.set_isometric_view()
        else:
            self.set_standard_view(text)

    def set_perspective_view(self) -> None:
        self._renderer.projection_mode = "perspective"
        self._set_projection_combo("Perspective")
        self._set_view_combo("Free")
        self.fit_view()
        self.viewSettingsChanged.emit()

    def set_orthographic_view(self) -> None:
        self._renderer.projection_mode = "orthographic"
        self._set_projection_combo("Orthographic")
        self._set_view_combo("Free")
        self.fit_view()
        self.viewSettingsChanged.emit()

    def set_isometric_view(self) -> None:
        self._renderer.projection_mode = "orthographic"
        self._renderer.yaw_deg = 45.0
        self._renderer.elevation_deg = self.ISOMETRIC_ELEVATION_DEG
        self._set_projection_combo("Orthographic")
        self._set_view_combo("Isometric")
        self.fit_view()
        self.viewSettingsChanged.emit()

    def set_standard_view(
        self,
        name: str,
        *,
        projection_mode: str = "orthographic",
    ) -> None:
        orientations = {
            "Top": (-90.0, 90.0),
            "Bottom": (0.0, -90.0),
            "Front": (-90.0, 0.0),
            "Back": (90.0, 0.0),
            "Left": (180.0, 0.0),
            "Right": (0.0, 0.0),
        }
        if name not in orientations:
            raise ValueError(f"Unknown standard view: {name}")
        if projection_mode not in {"orthographic", "perspective"}:
            raise ValueError(f"Unknown projection mode: {projection_mode}")

        self._renderer.projection_mode = projection_mode
        self._renderer.yaw_deg, self._renderer.elevation_deg = orientations[name]
        self._set_projection_combo(
            "Perspective" if projection_mode == "perspective" else "Orthographic"
        )
        self._set_view_combo(name)
        self.fit_view()
        self.viewSettingsChanged.emit()

    def set_default_view(self) -> None:
        """Restore the default top-down XY view using perspective projection."""

        self.set_standard_view("Top", projection_mode="perspective")

    def _orbit_started(self) -> None:
        if self.view_name != "Free":
            self._set_view_combo("Free")
            self.viewSettingsChanged.emit()

    def _renderer_status_changed(self, text: str) -> None:
        self._status_label.setText(text)

    def _update_empty_status(self) -> None:
        project = self.project
        has_mesh = bool(
            project
            and any(
                item.visible and item.mesh is not None
                for item in project.items
            )
        )
        if not has_mesh:
            self._status_label.setText(
                "Native OpenGL • Import an STL to preview it in the stock."
            )


__all__ = ["MeshViewport"]
