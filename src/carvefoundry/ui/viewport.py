from __future__ import annotations

from math import atan, degrees, radians, sin, tan

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMatrix4x4, QMouseEvent, QVector3D, QWheelEvent
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from .viewport_gpu import MeshViewport as _GpuMeshViewport


class MeshViewport(_GpuMeshViewport):
    """GPU viewport with CAD projection modes and selection-aware framing."""

    MIN_ZOOM = 0.01
    MAX_ZOOM = 100_000.0
    PERSPECTIVE_FOV_DEG = 45.0
    ISOMETRIC_ELEVATION_DEG = 35.26438968
    FIT_MARGIN = 1.10

    def __init__(self, project=None) -> None:
        super().__init__(project)
        self.projection_mode = "orthographic"
        self.view_name = "Free"
        self._build_view_controls()

    def _build_view_controls(self) -> None:
        self._view_controls = QWidget(self)
        self._view_controls.setObjectName("ViewportViewControls")
        layout = QHBoxLayout(self._view_controls)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(5)

        projection_label = QLabel("Projection")
        projection_label.setObjectName("Muted")
        layout.addWidget(projection_label)

        self._projection_combo = QComboBox()
        self._projection_combo.addItems(("Orthographic", "Perspective"))
        self._projection_combo.currentTextChanged.connect(self._projection_changed)
        layout.addWidget(self._projection_combo)

        view_label = QLabel("View")
        view_label.setObjectName("Muted")
        layout.addWidget(view_label)

        self._view_combo = QComboBox()
        self._view_combo.addItems(
            ("Free", "Isometric", "Top", "Bottom", "Front", "Back", "Left", "Right")
        )
        self._view_combo.currentTextChanged.connect(self._view_changed)
        layout.addWidget(self._view_combo)

        self._view_controls.adjustSize()
        self._position_view_controls()
        self._view_controls.raise_()

    def _position_view_controls(self) -> None:
        if not hasattr(self, "_view_controls"):
            return
        self._view_controls.adjustSize()
        x = max(9, self.width() - self._view_controls.width() - 9)
        self._view_controls.move(x, 7)
        self._view_controls.raise_()

    def set_view_controls_visible(self, visible: bool) -> None:
        self._view_controls.setVisible(bool(visible))
        if visible:
            self._position_view_controls()

    @property
    def view_controls_visible(self) -> bool:
        return self._view_controls.isVisible()

    def resizeGL(self, width: int, height: int) -> None:
        super().resizeGL(width, height)
        self._position_view_controls()

    def _scene_bounds(self) -> np.ndarray:
        """Return bounds used to frame the current view.

        The selected mesh controls framing so a small model can fill the
        viewport. Selecting the Stock row clears ``selected_item_index`` and
        therefore intentionally falls back to the complete stock/project bounds.
        """

        if self.project is not None and self.selected_item_index is not None:
            index = self.selected_item_index
            if 0 <= index < len(self.project.items):
                item = self.project.items[index]
                if item.visible and item.mesh is not None:
                    return self._item_bounds_mm(item)
        return super()._scene_bounds()

    def _clip_bounds(self) -> np.ndarray:
        """Return full-scene bounds used only for near/far clipping.

        Framing and clipping must be separate. A selected STL can be tiny
        compared with the stock, but the stock/grid still needs to remain inside
        the depth range while the camera orbits.
        """

        return super()._scene_bounds()

    def fit_view(self) -> None:
        """Fit the current target while preserving orientation/projection."""

        self.zoom = 1.0
        self.pan_px = QPointF(0.0, 0.0)
        self.update()

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
        self.projection_mode = "perspective" if text == "Perspective" else "orthographic"
        if self.projection_mode == "perspective" and self.view_name != "Free":
            self.view_name = "Free"
            self._set_view_combo("Free")
        self.fit_view()

    def _view_changed(self, text: str) -> None:
        if text == "Free":
            self.view_name = "Free"
            self.update()
            return
        if text == "Isometric":
            self.set_isometric_view()
            return
        self.set_standard_view(text)

    def set_perspective_view(self) -> None:
        """Use a human-eye-like perspective projection at the current angle."""

        self.projection_mode = "perspective"
        self.view_name = "Free"
        self._set_projection_combo("Perspective")
        self._set_view_combo("Free")
        self.fit_view()

    def set_orthographic_view(self) -> None:
        """Use a parallel projection at the current camera angle."""

        self.projection_mode = "orthographic"
        self.view_name = "Free"
        self._set_projection_combo("Orthographic")
        self._set_view_combo("Free")
        self.fit_view()

    def set_isometric_view(self) -> None:
        """Show three axes equally using an orthographic isometric view."""

        self.projection_mode = "orthographic"
        self.view_name = "Isometric"
        self.yaw_deg = 45.0
        self.elevation_deg = self.ISOMETRIC_ELEVATION_DEG
        self._set_projection_combo("Orthographic")
        self._set_view_combo("Isometric")
        self.fit_view()

    def set_standard_view(self, name: str) -> None:
        """Switch to a fixed orthographic Top/Bottom/Front/Back/Left/Right view."""

        orientations = {
            "Top": (0.0, 90.0),
            "Bottom": (0.0, -90.0),
            "Front": (-90.0, 0.0),
            "Back": (90.0, 0.0),
            "Left": (180.0, 0.0),
            "Right": (0.0, 0.0),
        }
        if name not in orientations:
            raise ValueError(f"Unknown standard view: {name}")

        self.projection_mode = "orthographic"
        self.view_name = name
        self.yaw_deg, self.elevation_deg = orientations[name]
        self._set_projection_combo("Orthographic")
        self._set_view_combo(name)
        self.fit_view()

    def _camera_matrices(self) -> tuple[QMatrix4x4, QMatrix4x4]:
        """Build stable camera matrices while keeping the full scene unclipped.

        ``_scene_bounds`` controls framing and may intentionally contain only a
        selected model. ``_clip_bounds`` always contains the stock and visible
        scene so grid/stock geometry cannot disappear merely because a small STL
        is selected. Framing uses a rotation-invariant sphere so orbiting never
        changes zoom.
        """

        bounds = self._scene_bounds()
        clip_bounds = self._clip_bounds()
        target = bounds.mean(axis=0)
        right, up, view = self._camera_basis()

        diagonal = max(float(np.linalg.norm(bounds[1] - bounds[0])), 1e-6)
        radius = max(diagonal / 2.0, 1e-6)
        framed_radius = radius * self.FIT_MARGIN

        clip_corners = self._bounds_corners(clip_bounds)
        relative_clip_depths = (clip_corners - target) @ view
        nearest_scene_offset = float(np.max(relative_clip_depths))
        farthest_scene_offset = float(np.min(relative_clip_depths))
        clip_diagonal = max(
            float(np.linalg.norm(clip_bounds[1] - clip_bounds[0])),
            1e-6,
        )
        clip_margin = max(clip_diagonal * 0.02, 0.1)

        width = max(self.width(), 1)
        height = max(self.height(), 1)
        aspect = max(width / height, 1e-9)
        zoom = max(self.zoom, 1e-9)

        if self.projection_mode == "perspective":
            base_half_vertical = radians(self.PERSPECTIVE_FOV_DEG) / 2.0
            base_half_horizontal = atan(tan(base_half_vertical) * aspect)
            limiting_half_angle = max(
                min(base_half_vertical, base_half_horizontal),
                1e-6,
            )

            fit_distance = max(
                framed_radius / sin(limiting_half_angle),
                framed_radius + 1e-5,
            )
            distance = max(
                fit_distance,
                nearest_scene_offset + clip_margin,
                1e-5,
            )

            desired_half_height = max(
                fit_distance * tan(base_half_vertical) / zoom,
                1e-9,
            )
            effective_half_vertical = atan(desired_half_height / distance)
            effective_fov_deg = max(degrees(effective_half_vertical * 2.0), 1e-5)
            world_height = 2.0 * desired_half_height
            world_width = world_height * aspect
            target = (
                target
                - right * self.pan_px.x() * (world_width / width)
                + up * self.pan_px.y() * (world_height / height)
            )

            eye = target + view * distance
            view_matrix = QMatrix4x4()
            view_matrix.lookAt(
                QVector3D(*[float(value) for value in eye]),
                QVector3D(*[float(value) for value in target]),
                QVector3D(*[float(value) for value in up]),
            )

            nearest_depth = distance - nearest_scene_offset
            farthest_depth = distance - farthest_scene_offset
            near_plane = max(nearest_depth * 0.5, 1e-4)
            far_plane = max(farthest_depth + clip_margin, near_plane + 1.0)
            projection = QMatrix4x4()
            projection.perspective(
                effective_fov_deg,
                aspect,
                near_plane,
                far_plane,
            )
            return projection, view_matrix

        half_extent = framed_radius / zoom
        if aspect >= 1.0:
            half_y = half_extent
            half_x = half_extent * aspect
        else:
            half_x = half_extent
            half_y = half_extent / aspect

        target = (
            target
            - right * self.pan_px.x() * ((2.0 * half_x) / width)
            + up * self.pan_px.y() * ((2.0 * half_y) / height)
        )

        distance = max(
            diagonal * 2.0,
            nearest_scene_offset + clip_margin,
            1.0,
        )
        eye = target + view * distance
        view_matrix = QMatrix4x4()
        view_matrix.lookAt(
            QVector3D(*[float(value) for value in eye]),
            QVector3D(*[float(value) for value in target]),
            QVector3D(*[float(value) for value in up]),
        )

        nearest_depth = distance - nearest_scene_offset
        farthest_depth = distance - farthest_scene_offset
        near_plane = max(nearest_depth * 0.5, 1e-4)
        far_plane = max(farthest_depth + clip_margin, near_plane + 1.0)

        projection = QMatrix4x4()
        projection.ortho(
            -half_x,
            half_x,
            -half_y,
            half_y,
            near_plane,
            far_plane,
        )
        return projection, view_matrix

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        before = (self.yaw_deg, self.elevation_deg)
        super().mouseMoveEvent(event)
        after = (self.yaw_deg, self.elevation_deg)
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and before != after
            and self.view_name != "Free"
        ):
            self.view_name = "Free"
            self._set_view_combo("Free")

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom over a wide range, including smooth Wayland touchpad deltas."""

        angle_steps = event.angleDelta().y() / 120.0
        if angle_steps:
            steps = angle_steps
        else:
            steps = event.pixelDelta().y() / 120.0

        if steps:
            self.zoom *= 1.20**steps
            self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.zoom))
            self.update()
        event.accept()


__all__ = ["MeshViewport"]
