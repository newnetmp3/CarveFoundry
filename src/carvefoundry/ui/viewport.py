from __future__ import annotations

from math import cos, radians, sin
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from carvefoundry.core.project import Project, ProjectItem


class MeshViewport(QWidget):
    """Interactive stock and mesh preview using a lightweight orthographic renderer."""

    MAX_RENDER_FACES = 6000

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self.project = project
        self.selected_item_index: int | None = None
        self.yaw_deg = 45.0
        self.elevation_deg = 35.0
        self.zoom = 1.0
        self.pan_px = QPointF(0.0, 0.0)
        self.show_stock = True
        self.show_grid = True
        self._last_mouse_pos: QPointF | None = None
        self.setObjectName("MeshViewport")
        self.setMinimumSize(360, 260)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_project(self, project: Project) -> None:
        self.project = project
        self.selected_item_index = None
        self.fit_view()

    def set_selected_item(self, index: int | None) -> None:
        self.selected_item_index = index
        self.update()

    def fit_view(self) -> None:
        self.yaw_deg = 45.0
        self.elevation_deg = 35.0
        self.zoom = 1.0
        self.pan_px = QPointF(0.0, 0.0)
        self.update()

    def toggle_stock(self) -> None:
        self.show_stock = not self.show_stock
        self.update()

    def toggle_grid(self) -> None:
        self.show_grid = not self.show_grid
        self.update()

    def _camera_basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        azimuth = radians(self.yaw_deg)
        elevation = radians(self.elevation_deg)
        view = np.array(
            (
                cos(elevation) * cos(azimuth),
                cos(elevation) * sin(azimuth),
                sin(elevation),
            ),
            dtype=float,
        )
        view /= np.linalg.norm(view)
        right = np.cross(np.array((0.0, 0.0, 1.0)), view)
        if np.linalg.norm(right) < 1e-9:
            right = np.array((1.0, 0.0, 0.0))
        right /= np.linalg.norm(right)
        up = np.cross(view, right)
        up /= np.linalg.norm(up)
        return right, up, view

    def _scene_bounds(self) -> np.ndarray:
        if self.project is None:
            return np.array(((0.0, 0.0, -1.0), (100.0, 100.0, 0.0)), dtype=float)

        stock = self.project.stock
        minimum = np.array((0.0, 0.0, -stock.thickness_mm), dtype=float)
        maximum = np.array((stock.width_mm, stock.height_mm, 0.0), dtype=float)

        for item in self.project.items:
            if not item.visible or item.mesh is None:
                continue
            transformed = item.transformed_mesh()
            if transformed is None:
                continue
            item_bounds = np.asarray(transformed.bounds, dtype=float)
            minimum = np.minimum(minimum, item_bounds[0])
            maximum = np.maximum(maximum, item_bounds[1])

        return np.vstack((minimum, maximum))

    @staticmethod
    def _bounds_corners(bounds: np.ndarray) -> np.ndarray:
        minimum, maximum = bounds
        return np.array(
            [
                (x, y, z)
                for x in (minimum[0], maximum[0])
                for y in (minimum[1], maximum[1])
                for z in (minimum[2], maximum[2])
            ],
            dtype=float,
        )

    def _view_parameters(
        self,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
        bounds = self._scene_bounds()
        target = bounds.mean(axis=0)
        right, up, view = self._camera_basis()
        corners = self._bounds_corners(bounds) - target
        horizontal = corners @ right
        vertical = corners @ up
        span_x = max(float(np.ptp(horizontal)), 1.0)
        span_y = max(float(np.ptp(vertical)), 1.0)
        available_width = max(self.width() - 72, 100)
        available_height = max(self.height() - 72, 100)
        base_scale = min(available_width / span_x, available_height / span_y)
        return target, right, up, view, base_scale * self.zoom

    def _project(
        self,
        points: np.ndarray,
        *,
        target: np.ndarray,
        right: np.ndarray,
        up: np.ndarray,
        view: np.ndarray,
        scale: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        relative = np.asarray(points, dtype=float) - target
        screen = np.empty((len(relative), 2), dtype=float)
        screen[:, 0] = relative @ right * scale + self.width() / 2.0 + self.pan_px.x()
        screen[:, 1] = -(relative @ up) * scale + self.height() / 2.0 + self.pan_px.y()
        depth = relative @ view
        return screen, depth

    def _draw_stock(
        self,
        painter: QPainter,
        target: np.ndarray,
        right: np.ndarray,
        up: np.ndarray,
        view: np.ndarray,
        scale: float,
    ) -> None:
        if self.project is None or not self.show_stock:
            return

        stock = self.project.stock
        corners = np.array(
            (
                (0.0, 0.0, 0.0),
                (stock.width_mm, 0.0, 0.0),
                (stock.width_mm, stock.height_mm, 0.0),
                (0.0, stock.height_mm, 0.0),
                (0.0, 0.0, -stock.thickness_mm),
                (stock.width_mm, 0.0, -stock.thickness_mm),
                (stock.width_mm, stock.height_mm, -stock.thickness_mm),
                (0.0, stock.height_mm, -stock.thickness_mm),
            ),
            dtype=float,
        )
        projected, _ = self._project(
            corners,
            target=target,
            right=right,
            up=up,
            view=view,
            scale=scale,
        )

        top_polygon = QPolygonF([QPointF(float(x), float(y)) for x, y in projected[:4]])
        painter.setPen(QPen(QColor("#58647a"), 1.0))
        painter.setBrush(QColor(77, 91, 115, 30))
        painter.drawPolygon(top_polygon)

        if self.show_grid:
            self._draw_grid(painter, target, right, up, view, scale)

        edges = (
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 0),
            (4, 5),
            (5, 6),
            (6, 7),
            (7, 4),
            (0, 4),
            (1, 5),
            (2, 6),
            (3, 7),
        )
        painter.setPen(QPen(QColor("#65728a"), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for start, end in edges:
            painter.drawLine(QPointF(*projected[start]), QPointF(*projected[end]))

    def _draw_grid(
        self,
        painter: QPainter,
        target: np.ndarray,
        right: np.ndarray,
        up: np.ndarray,
        view: np.ndarray,
        scale: float,
    ) -> None:
        if self.project is None:
            return

        stock = self.project.stock
        largest = max(stock.width_mm, stock.height_mm)
        if largest <= 150:
            step = 10.0
        elif largest <= 400:
            step = 25.0
        elif largest <= 1000:
            step = 50.0
        else:
            step = 100.0

        painter.setPen(QPen(QColor(91, 106, 130, 75), 1.0))
        for x in np.arange(step, stock.width_mm, step):
            points = np.array(((x, 0.0, 0.0), (x, stock.height_mm, 0.0)))
            projected, _ = self._project(
                points,
                target=target,
                right=right,
                up=up,
                view=view,
                scale=scale,
            )
            painter.drawLine(QPointF(*projected[0]), QPointF(*projected[1]))

        for y in np.arange(step, stock.height_mm, step):
            points = np.array(((0.0, y, 0.0), (stock.width_mm, y, 0.0)))
            projected, _ = self._project(
                points,
                target=target,
                right=right,
                up=up,
                view=view,
                scale=scale,
            )
            painter.drawLine(QPointF(*projected[0]), QPointF(*projected[1]))

    def _sample_faces(self, item: ProjectItem) -> np.ndarray:
        assert item.mesh is not None
        faces = np.asarray(item.mesh.mesh.faces, dtype=np.int64)
        if len(faces) <= self.MAX_RENDER_FACES:
            return faces
        indices = np.linspace(0, len(faces) - 1, self.MAX_RENDER_FACES, dtype=np.int64)
        return faces[indices]

    def _draw_mesh(
        self,
        painter: QPainter,
        item: ProjectItem,
        item_index: int,
        target: np.ndarray,
        right: np.ndarray,
        up: np.ndarray,
        view: np.ndarray,
        scale: float,
    ) -> None:
        if item.mesh is None or not item.visible:
            return

        render_mesh = item.transformed_mesh()
        if render_mesh is None:
            return
        faces = self._sample_faces(item)
        unique_vertices, inverse = np.unique(faces.reshape(-1), return_inverse=True)
        transformed_vertices = np.asarray(render_mesh.vertices, dtype=float)[unique_vertices]
        triangles = transformed_vertices[inverse].reshape((-1, 3, 3))
        flat_points = triangles.reshape((-1, 3))
        projected, depths = self._project(
            flat_points,
            target=target,
            right=right,
            up=up,
            view=view,
            scale=scale,
        )
        projected = projected.reshape((-1, 3, 2))
        depths = depths.reshape((-1, 3)).mean(axis=1)

        normals = np.cross(
            triangles[:, 1] - triangles[:, 0],
            triangles[:, 2] - triangles[:, 0],
        )
        normal_lengths = np.linalg.norm(normals, axis=1)
        valid = normal_lengths > 1e-12
        normals[valid] /= normal_lengths[valid, None]
        light = np.array((0.35, -0.45, 0.82), dtype=float)
        light /= np.linalg.norm(light)
        shading = 0.35 + 0.65 * np.abs(normals @ light)

        selected = item_index == self.selected_item_index
        base = np.array((200, 255, 61) if selected else (91, 142, 214), dtype=float)
        order = np.argsort(depths)
        edge = QColor(20, 27, 43, 190 if selected else 130)

        for triangle_index in order:
            polygon_points = projected[triangle_index]
            polygon = QPolygonF([QPointF(float(x), float(y)) for x, y in polygon_points])
            shade = float(shading[triangle_index])
            color_values = np.clip(base * shade, 0, 255).astype(int)
            painter.setBrush(
                QColor(
                    int(color_values[0]),
                    int(color_values[1]),
                    int(color_values[2]),
                    215 if selected else 185,
                )
            )
            painter.setPen(QPen(edge, 0.65 if selected else 0.45))
            painter.drawPolygon(polygon)

    def _draw_overlay(self, painter: QPainter) -> None:
        painter.setPen(QColor("#9aa4b8"))
        painter.drawText(
            14,
            22,
            "LMB orbit  •  RMB/MMB pan  •  Wheel zoom  •  Double-click fit",
        )
        if self.project is None or not any(
            item.mesh is not None and item.visible for item in self.project.items
        ):
            painter.setPen(QColor("#edf1f7"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Import an STL to preview it in the stock.",
            )

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111827"))

        target, right, up, view, scale = self._view_parameters()
        self._draw_stock(painter, target, right, up, view, scale)

        if self.project is not None:
            for index, item in enumerate(self.project.items):
                self._draw_mesh(painter, item, index, target, right, up, view, scale)

        self._draw_overlay(painter)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._last_mouse_pos = event.position()
        self.setFocus()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_mouse_pos is None:
            self._last_mouse_pos = event.position()
            return

        delta = event.position() - self._last_mouse_pos
        self._last_mouse_pos = event.position()

        if event.buttons() & Qt.MouseButton.LeftButton:
            self.yaw_deg += delta.x() * 0.45
            self.elevation_deg = max(
                -85.0,
                min(85.0, self.elevation_deg + delta.y() * 0.35),
            )
            self.update()
        elif event.buttons() & (Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton):
            self.pan_px += delta
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        del event
        self._last_mouse_pos = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() / 120.0
        self.zoom *= 1.15**steps
        self.zoom = max(0.08, min(25.0, self.zoom))
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        del event
        self.fit_view()
