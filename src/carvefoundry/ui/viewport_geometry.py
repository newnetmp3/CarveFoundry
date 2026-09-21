"""World-space picking, 2.5D outlines, selection and transform gizmo geometry.

Pure Python mixin: the native QOpenGLWindow owns the GL context and GPU caches.
These methods operate on that same renderer instance, without duplicate cameras
or any extra GL allocation per interaction.
"""
from __future__ import annotations

from itertools import pairwise

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMatrix4x4, QVector3D, QVector4D

from carvefoundry.core.project import ProjectItem

GL_DEPTH_TEST = 0x0B71


class ViewportGeometryMixin:
    def _screen_ray(
        self,
        position: QPointF,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """Return a world-space ray for a viewport pixel."""

        projection, view_matrix, _world_per_pixel = self._camera_geometry()
        view_projection = projection * view_matrix
        inverse, invertible = view_projection.inverted()
        if not invertible:
            return None

        width = float(max(self.width(), 1))
        height = float(max(self.height(), 1))
        ndc_x = 2.0 * float(position.x()) / width - 1.0
        ndc_y = 1.0 - 2.0 * float(position.y()) / height

        near_point = inverse.map(QVector3D(ndc_x, ndc_y, -1.0))
        far_point = inverse.map(QVector3D(ndc_x, ndc_y, 1.0))
        origin = np.array(
            (near_point.x(), near_point.y(), near_point.z()),
            dtype=float,
        )
        far = np.array(
            (far_point.x(), far_point.y(), far_point.z()),
            dtype=float,
        )
        direction = far - origin
        length = float(np.linalg.norm(direction))
        if not np.isfinite(length) or length <= 1e-12:
            return None
        return origin, direction / length

    @staticmethod
    def _ray_bounds_distance(
        origin: np.ndarray,
        direction: np.ndarray,
        bounds: np.ndarray,
    ) -> float | None:
        """Return the nearest ray/AABB hit distance, or None."""

        t_min = 0.0
        t_max = float("inf")
        for axis in range(3):
            component = float(direction[axis])
            low = float(bounds[0, axis])
            high = float(bounds[1, axis])
            coordinate = float(origin[axis])
            if abs(component) <= 1e-12:
                if coordinate < low or coordinate > high:
                    return None
                continue
            first = (low - coordinate) / component
            second = (high - coordinate) / component
            if first > second:
                first, second = second, first
            t_min = max(t_min, first)
            t_max = min(t_max, second)
            if t_max < t_min:
                return None
        return t_min if t_max >= 0.0 else None

    def pick_item(self, position: QPointF) -> int | None:
        """Pick the nearest visible mesh using transformed 3D bounds."""

        if self.project is None:
            return None
        ray = self._screen_ray(position)
        if ray is None:
            return None
        origin, direction = ray
        _projection, _view, world_per_pixel = self._camera_geometry()
        padding = max(float(world_per_pixel) * 4.0, 0.05)

        best_index: int | None = None
        best_distance = float("inf")
        for index, item in enumerate(self.project.items):
            if not self._item_viewport_visible(index, item):
                continue
            bounds = self._item_bounds_mm(item).copy()
            bounds[0] -= padding
            bounds[1] += padding
            distance = self._ray_bounds_distance(origin, direction, bounds)
            if distance is not None and distance < best_distance:
                best_index = index
                best_distance = distance
        return best_index

    def _is_empty_viewport_background(self, position: QPointF) -> bool:
        """Only allow double-click Fit View outside visible stock and meshes.

        The stock-plane mapping used by drawing tools clamps XY to the board
        even when the pointer is over the black margin, so it cannot determine
        whether the pointer is on the background. Use the unclamped world ray
        against the actual stock volume instead. Respect hidden stock/grid and
        mesh visibility; use the existing model picker for object hits.
        """
        if self.project is None:
            return True
        ray = self._screen_ray(position)
        if ray is None:
            return False
        if self.pick_item(position) is not None:
            return False
        if self.show_stock or self.show_grid:
            stock = self.project.stock
            bounds = np.array(
                (
                    (0.0, 0.0, -float(stock.thickness_mm)),
                    (float(stock.width_mm), float(stock.height_mm), 0.0),
                ),
                dtype=float,
            )
            origin, direction = ray
            if self._ray_bounds_distance(origin, direction, bounds) is not None:
                return False
        return True

    def _stock_plane_point(self, position: QPointF) -> np.ndarray | None:
        """Map a screen position onto the top of the stock and clamp to its XY area."""

        if self.project is None:
            return None
        ray = self._screen_ray(position)
        if ray is None:
            return None
        origin, direction = ray
        if abs(float(direction[2])) <= 1e-10:
            return None
        distance = -float(origin[2]) / float(direction[2])
        if distance < 0.0:
            return None

        point = origin + direction * distance
        if not np.isfinite(point).all():
            return None
        point[0] = max(0.0, min(float(self.project.stock.width_mm), float(point[0])))
        point[1] = max(0.0, min(float(self.project.stock.height_mm), float(point[1])))
        point[2] = 0.0
        return point

    def _constrained_shape_point(
        self,
        start: np.ndarray,
        current: np.ndarray,
        modifiers: Qt.KeyboardModifier,
    ) -> np.ndarray:
        if not modifiers & Qt.KeyboardModifier.ShiftModifier:
            return current

        result = current.copy()
        dx = float(current[0] - start[0])
        dy = float(current[1] - start[1])
        if self._shape_draw_mode in {"rectangle", "ellipse", "polygon", "text"}:
            size = max(abs(dx), abs(dy))
            result[0] = start[0] + (size if dx >= 0.0 else -size)
            result[1] = start[1] + (size if dy >= 0.0 else -size)
        elif self._shape_draw_mode in {"line", "measure"}:
            length = float(np.hypot(dx, dy))
            if length > 1e-9:
                angle = np.arctan2(dy, dx)
                snapped = round(angle / (np.pi / 4.0)) * (np.pi / 4.0)
                result[0] = start[0] + np.cos(snapped) * length
                result[1] = start[1] + np.sin(snapped) * length

        if self.project is not None:
            result[0] = max(
                0.0,
                min(float(self.project.stock.width_mm), float(result[0])),
            )
            result[1] = max(
                0.0,
                min(float(self.project.stock.height_mm), float(result[1])),
            )
        return result

    def _shape_preview_vertices(self) -> np.ndarray:
        start = self._shape_drag_start_world
        end = self._shape_drag_current_world
        mode = self._shape_draw_mode
        if mode == "pen":
            if len(self._freehand_points_world) < 2:
                return np.empty((0, 3), dtype=np.float32)
            z = 0.035
            vertices: list[tuple[float, float, float]] = []
            for first, second in pairwise(self._freehand_points_world):
                vertices.extend(
                    (
                        (float(first[0]), float(first[1]), z),
                        (float(second[0]), float(second[1]), z),
                    )
                )
            return np.asarray(vertices, dtype=np.float32).reshape((-1, 3))

        if start is None or end is None or mode is None:
            return np.empty((0, 3), dtype=np.float32)

        x0, y0 = float(start[0]), float(start[1])
        x1, y1 = float(end[0]), float(end[1])
        z = 0.035

        def segments(points: list[tuple[float, float, float]]) -> np.ndarray:
            vertices: list[tuple[float, float, float]] = []
            for first, second in pairwise(points):
                vertices.extend((first, second))
            return np.asarray(vertices, dtype=np.float32).reshape((-1, 3))

        if mode in {"rectangle", "text", "fixture"}:
            points = [
                (x0, y0, z),
                (x1, y0, z),
                (x1, y1, z),
                (x0, y1, z),
                (x0, y0, z),
            ]
            if mode == "text":
                # A diagonal makes the drag box read as a text frame rather
                # than another rectangle while the user is drawing it.
                base = list(segments(points))
                return np.vstack(
                    (
                        np.asarray(base, dtype=np.float32).reshape((-1, 3)),
                        np.asarray(((x0, y0, z), (x1, y1, z)), dtype=np.float32),
                    )
                )
            return segments(points)

        if mode in {"line", "measure"}:
            return np.asarray(
                ((x0, y0, z), (x1, y1, z)),
                dtype=np.float32,
            )

        center_x = (x0 + x1) / 2.0
        center_y = (y0 + y1) / 2.0
        radius_x = abs(x1 - x0) / 2.0
        radius_y = abs(y1 - y0) / 2.0
        section_count = 6 if mode == "polygon" else 48
        points = []
        for index in range(section_count + 1):
            angle = 2.0 * np.pi * index / section_count
            points.append(
                (
                    center_x + np.cos(angle) * radius_x,
                    center_y + np.sin(angle) * radius_y,
                    z,
                )
            )
        return segments(points)

    def _draw_shape_preview(self, view_projection: QMatrix4x4) -> None:
        if self._functions is None or self._shape_draw_mode is None:
            return
        vertices = self._shape_preview_vertices()
        if len(vertices) == 0:
            return
        self._functions.glDisable(GL_DEPTH_TEST)
        try:
            self._draw_lines(
                vertices,
                view_projection=view_projection,
                color=QVector4D(0.30, 0.95, 0.55, 0.98),
                line_width=2.5,
            )
        finally:
            self._functions.glEnable(GL_DEPTH_TEST)

    def _selected_gizmo_pivot(self) -> np.ndarray | None:
        if (
            self.project is None
            or len(self.selected_item_indices) != 1
            or self.selected_item_index is None
            or self.selected_item_index not in self.selected_item_indices
            or not 0 <= self.selected_item_index < len(self.project.items)
        ):
            return None
        item = self.project.items[self.selected_item_index]
        if item.locked or not self._item_viewport_visible(self.selected_item_index, item):
            return None
        return self._item_bounds_mm(item).mean(axis=0)

    def _gizmo_world_axis(self, axis: int) -> np.ndarray:
        world_axis = np.eye(3, dtype=float)[axis]
        if (
            self.transform_orientation != "local"
            or self.project is None
            or self.selected_item_index is None
            or not 0 <= self.selected_item_index < len(self.project.items)
        ):
            return world_axis

        item = self.project.items[self.selected_item_index]
        matrix = np.asarray(item.transform.matrix(), dtype=float)
        local_axis = matrix[:3, axis]
        length = float(np.linalg.norm(local_axis))
        if length <= 1e-12:
            return world_axis
        return local_axis / length

    def _gizmo_visual_direction(
        self,
        axis: int,
        pivot: np.ndarray,
        length_mm: float,
        view_projection: QMatrix4x4,
    ) -> np.ndarray:
        """Return a visible direction for one translation handle.

        Normally the handle follows the true world axis.  If that axis points
        almost straight into the camera, its screen projection collapses.  In
        that case use a small billboard-style direction while the drag still
        changes only the requested world coordinate.
        """

        world_axis = self._gizmo_world_axis(axis)
        start = self._project_world_point(
            tuple(float(value) for value in pivot),
            view_projection,
        )
        actual_end = self._project_world_point(
            tuple(float(value) for value in pivot + world_axis * length_mm),
            view_projection,
        )
        if start is not None and actual_end is not None:
            projected = np.hypot(
                actual_end.x() - start.x(),
                actual_end.y() - start.y(),
            )
            if projected >= self.GIZMO_MIN_PROJECTED_PX:
                return world_axis

        right, up, _view = self._camera_basis()
        if axis == 0:
            fallback = right + up * 0.55
        elif axis == 1:
            fallback = -right + up * 0.55
        else:
            fallback = right + up
        length = float(np.linalg.norm(fallback))
        if length <= 1e-12:
            return world_axis
        return fallback / length

    def _gizmo_axis_data(
        self,
        axis: int,
        *,
        view_projection: QMatrix4x4,
        world_per_pixel: float,
    ) -> tuple[np.ndarray, np.ndarray, QPointF, QPointF] | None:
        pivot = self._selected_gizmo_pivot()
        if pivot is None:
            return None

        length_mm = max(
            float(world_per_pixel) * self.GIZMO_LENGTH_PX,
            0.5,
        )
        visual_direction = self._gizmo_visual_direction(
            axis,
            pivot,
            length_mm,
            view_projection,
        )
        endpoint = pivot + visual_direction * length_mm

        start_screen = self._project_world_point(
            tuple(float(value) for value in pivot),
            view_projection,
        )
        end_screen = self._project_world_point(
            tuple(float(value) for value in endpoint),
            view_projection,
        )
        if start_screen is None or end_screen is None:
            return None
        return pivot, endpoint, start_screen, end_screen

    @staticmethod
    def _point_segment_distance(
        point: QPointF,
        start: QPointF,
        end: QPointF,
    ) -> float:
        px = float(point.x())
        py = float(point.y())
        sx = float(start.x())
        sy = float(start.y())
        ex = float(end.x())
        ey = float(end.y())
        dx = ex - sx
        dy = ey - sy
        length_sq = dx * dx + dy * dy
        if length_sq <= 1e-12:
            return float(np.hypot(px - sx, py - sy))
        t = ((px - sx) * dx + (py - sy) * dy) / length_sq
        t = max(0.0, min(1.0, t))
        closest_x = sx + t * dx
        closest_y = sy + t * dy
        return float(np.hypot(px - closest_x, py - closest_y))

    def pick_gizmo_axis(self, position: QPointF) -> int | None:
        """Return the selected translation axis when a gizmo handle is hit."""

        if self.selected_item_index is None or self.project is None:
            return None
        if self.project.items[self.selected_item_index].locked:
            return None
        projection, view_matrix, world_per_pixel = self._camera_geometry()
        view_projection = projection * view_matrix

        best_axis: int | None = None
        best_distance = float("inf")
        for axis in range(3):
            data = self._gizmo_axis_data(
                axis,
                view_projection=view_projection,
                world_per_pixel=world_per_pixel,
            )
            if data is None:
                continue
            _pivot, _endpoint, start, end = data

            # Do not let the shared center point make all three axes ambiguous.
            # Only the outer 80% of each shaft is an active handle.
            handle_start = QPointF(
                start.x() + (end.x() - start.x()) * 0.20,
                start.y() + (end.y() - start.y()) * 0.20,
            )
            distance = self._point_segment_distance(
                position,
                handle_start,
                end,
            )
            if (
                distance <= self.GIZMO_PICK_RADIUS_PX
                and distance < best_distance
            ):
                best_axis = axis
                best_distance = distance
        return best_axis

    def _gizmo_axis_drag_delta(
        self,
        item_index: int,
        axis: int,
        delta: QPointF,
    ) -> float | None:
        """Convert mouse movement along a visible handle to one-axis motion."""

        if (
            self.project is None
            or not 0 <= item_index < len(self.project.items)
            or not 0 <= axis <= 2
        ):
            return None

        projection, view_matrix, world_per_pixel = self._camera_geometry()
        view_projection = projection * view_matrix
        data = self._gizmo_axis_data(
            axis,
            view_projection=view_projection,
            world_per_pixel=world_per_pixel,
        )
        if data is None:
            return None
        pivot, endpoint, start, end = data

        screen_axis = np.array(
            (float(end.x() - start.x()), float(end.y() - start.y())),
            dtype=float,
        )
        screen_length = float(np.linalg.norm(screen_axis))
        world_length = float(np.linalg.norm(endpoint - pivot))
        if screen_length <= 1e-9 or world_length <= 1e-12:
            return None

        screen_unit = screen_axis / screen_length
        mouse_delta = np.array(
            (float(delta.x()), float(delta.y())),
            dtype=float,
        )
        along_pixels = float(mouse_delta @ screen_unit)
        millimeters_per_pixel = world_length / screen_length
        axis_delta = along_pixels * millimeters_per_pixel

        # Prevent a low-angle/perspective edge case from turning a tiny cursor
        # movement into a large model jump.
        pixel_distance = float(np.linalg.norm(mouse_delta))
        max_delta = max(
            float(world_per_pixel) * pixel_distance * 1.35,
            0.02,
        )
        return max(-max_delta, min(max_delta, axis_delta))

    def _gizmo_axis_vertices(
        self,
        axis: int,
        *,
        view_projection: QMatrix4x4,
        world_per_pixel: float,
    ) -> np.ndarray:
        data = self._gizmo_axis_data(
            axis,
            view_projection=view_projection,
            world_per_pixel=world_per_pixel,
        )
        if data is None:
            return np.empty((0, 3), dtype=np.float32)

        pivot, endpoint, _start, _end = data
        direction = endpoint - pivot
        length = float(np.linalg.norm(direction))
        if length <= 1e-12:
            return np.empty((0, 3), dtype=np.float32)
        direction /= length

        _right, _up, view = self._camera_basis()
        side = np.cross(direction, view)
        side_length = float(np.linalg.norm(side))
        if side_length <= 1e-9:
            side = np.cross(direction, np.array((0.0, 0.0, 1.0)))
            side_length = float(np.linalg.norm(side))
        if side_length <= 1e-9:
            side = np.array((1.0, 0.0, 0.0), dtype=float)
        else:
            side /= side_length

        head_length = length * 0.20
        wing = head_length * 0.48
        head_base = endpoint - direction * head_length
        first_wing = head_base + side * wing
        second_wing = head_base - side * wing

        return np.asarray(
            (
                pivot,
                endpoint,
                endpoint,
                first_wing,
                endpoint,
                second_wing,
            ),
            dtype=np.float32,
        )

    def _draw_translation_gizmo(
        self,
        view_projection: QMatrix4x4,
        world_per_pixel: float,
    ) -> None:
        if self._selected_gizmo_pivot() is None or self._functions is None:
            return

        colors = (
            QVector4D(0.96, 0.30, 0.28, 1.0),
            QVector4D(0.30, 0.90, 0.38, 1.0),
            QVector4D(0.30, 0.55, 1.00, 1.0),
        )
        active_color = QVector4D(1.0, 0.86, 0.25, 1.0)

        # Translation handles are controls, not scene geometry.  Render them on
        # top so a handle cannot disappear inside the selected mesh.
        self._functions.glDisable(GL_DEPTH_TEST)
        try:
            for axis, color in enumerate(colors):
                active = axis == self._active_gizmo_axis
                self._draw_lines(
                    self._gizmo_axis_vertices(
                        axis,
                        view_projection=view_projection,
                        world_per_pixel=world_per_pixel,
                    ),
                    view_projection=view_projection,
                    color=active_color if active else color,
                    line_width=4.0 if active else 3.0,
                )
        finally:
            self._functions.glEnable(GL_DEPTH_TEST)

    def _selected_resize_item(self) -> tuple[int, ProjectItem] | None:
        if (
            self.project is None
            or self._camera_control_mode
            or len(self.selected_item_indices) != 1
            or self.selected_item_index is None
            or self.selected_item_index not in self.selected_item_indices
            or not 0 <= self.selected_item_index < len(self.project.items)
        ):
            return None
        item = self.project.items[self.selected_item_index]
        if item.locked or not self._item_viewport_visible(self.selected_item_index, item):
            return None
        return self.selected_item_index, item

    @staticmethod
    def _resize_opposite_handle(handle: int) -> int:
        return (int(handle) + 2) % 4

    def _resize_world_corners(self, item: ProjectItem) -> np.ndarray:
        """Return the four transformed top-face corners used as XY resize handles."""

        if item.mesh is None:
            return np.empty((0, 3), dtype=float)
        bounds = np.asarray(item.mesh.bounds, dtype=float)
        bounds *= float(item.source_units.millimeters_per_unit)
        minimum, maximum = bounds
        z = float(maximum[2])
        local = np.asarray(
            (
                (minimum[0], minimum[1], z),
                (maximum[0], minimum[1], z),
                (maximum[0], maximum[1], z),
                (minimum[0], maximum[1], z),
            ),
            dtype=float,
        )
        pivot = tuple(float(value) for value in bounds.mean(axis=0))
        return item.transform.apply_points(local, pivot=pivot)

    def _resize_handle_screen_points(
        self,
        view_projection: QMatrix4x4,
    ) -> list[QPointF | None]:
        selected = self._selected_resize_item()
        if selected is None:
            return []
        _index, item = selected
        corners = self._resize_world_corners(item)
        return [
            self._project_world_point(
                tuple(float(value) for value in corner),
                view_projection,
            )
            for corner in corners
        ]

    def pick_resize_handle(self, position: QPointF) -> int | None:
        selected = self._selected_resize_item()
        if selected is None:
            return None
        projection, view_matrix, _world_per_pixel = self._camera_geometry()
        view_projection = projection * view_matrix
        points = self._resize_handle_screen_points(view_projection)
        best_handle: int | None = None
        best_distance = float("inf")
        for handle, point in enumerate(points):
            if point is None:
                continue
            distance = float(
                np.hypot(
                    position.x() - point.x(),
                    position.y() - point.y(),
                )
            )
            if (
                distance <= self.RESIZE_HANDLE_RADIUS_PX
                and distance < best_distance
            ):
                best_handle = handle
                best_distance = distance
        return best_handle

    def _begin_resize(self, item_index: int, handle: int) -> bool:
        if (
            self.project is None
            or not 0 <= item_index < len(self.project.items)
            or handle not in {0, 1, 2, 3}
        ):
            return False
        item = self.project.items[item_index]
        if item.mesh is None or not item.visible or item.locked:
            return False
        corners = self._resize_world_corners(item)
        if len(corners) != 4:
            return False
        opposite = self._resize_opposite_handle(handle)
        center = corners.mean(axis=0)
        self._resize_initial_scale = tuple(item.transform.scale_xyz)
        self._resize_initial_translation = tuple(
            item.transform.translation_mm
        )
        self._resize_active_world = corners[handle].copy()
        self._resize_opposite_world = corners[opposite].copy()
        self._resize_active_vector_world = corners[handle] - center
        self._active_resize_handle = handle
        self._interaction_mode = "object-resize"
        self._transform_interaction_kind = "resize-object"
        return True

    def _apply_resize_factor(
        self,
        item_index: int,
        factor: float,
    ) -> bool:
        if (
            self.project is None
            or not 0 <= item_index < len(self.project.items)
            or self._resize_initial_scale is None
            or self._resize_initial_translation is None
            or self._resize_active_vector_world is None
        ):
            return False
        item = self.project.items[item_index]
        if item.mesh is None or not item.visible:
            return False

        factor = max(
            self.RESIZE_MIN_FACTOR,
            min(self.RESIZE_MAX_FACTOR, float(factor)),
        )
        sx, sy, sz = self._resize_initial_scale
        # Viewport corner handles are intentionally planar. They resize the
        # model footprint uniformly in XY while preserving its CNC Z/depth.
        item.transform.scale_xyz = (
            max(1e-6, sx * factor),
            max(1e-6, sy * factor),
            sz,
        )
        initial_translation = np.asarray(
            self._resize_initial_translation,
            dtype=float,
        )
        translation = (
            initial_translation
            + self._resize_active_vector_world * (factor - 1.0)
        )
        item.transform.translation_mm = tuple(
            float(value) for value in translation
        )
        item.transform.validate()
        return True

    def _resize_factor_from_cursor(self, position: QPointF) -> float | None:
        if (
            self._resize_active_world is None
            or self._resize_opposite_world is None
        ):
            return None
        projection, view_matrix, _world_per_pixel = self._camera_geometry()
        view_projection = projection * view_matrix
        active = self._project_world_point(
            tuple(float(value) for value in self._resize_active_world),
            view_projection,
        )
        opposite = self._project_world_point(
            tuple(float(value) for value in self._resize_opposite_world),
            view_projection,
        )
        if active is None or opposite is None:
            return None
        diagonal = np.asarray(
            (active.x() - opposite.x(), active.y() - opposite.y()),
            dtype=float,
        )
        length_sq = float(diagonal @ diagonal)
        if length_sq <= 1e-9:
            return None
        cursor = np.asarray(
            (position.x() - opposite.x(), position.y() - opposite.y()),
            dtype=float,
        )
        return float(cursor @ diagonal / length_sq)

    def _resize_frame_vertices(self, world_per_pixel: float) -> np.ndarray:
        selected = self._selected_resize_item()
        if selected is None:
            return np.empty((0, 3), dtype=np.float32)
        _index, item = selected
        corners = self._resize_world_corners(item)
        if len(corners) != 4:
            return np.empty((0, 3), dtype=np.float32)

        vertices: list[np.ndarray] = []
        for first, second in (
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 0),
        ):
            vertices.extend((corners[first], corners[second]))

        right, up, _view = self._camera_basis()
        half = max(
            float(world_per_pixel) * self.RESIZE_HANDLE_HALF_SIZE_PX,
            0.05,
        )
        for corner in corners:
            square = (
                corner - right * half - up * half,
                corner + right * half - up * half,
                corner + right * half + up * half,
                corner - right * half + up * half,
            )
            vertices.extend(
                (
                    square[0],
                    square[1],
                    square[1],
                    square[2],
                    square[2],
                    square[3],
                    square[3],
                    square[0],
                )
            )
        return np.asarray(vertices, dtype=np.float32).reshape((-1, 3))

    def _draw_resize_handles(
        self,
        view_projection: QMatrix4x4,
        world_per_pixel: float,
    ) -> None:
        if self._functions is None or self._selected_resize_item() is None:
            return
        vertices = self._resize_frame_vertices(world_per_pixel)
        if len(vertices) == 0:
            return
        color = (
            QVector4D(1.0, 0.86, 0.25, 1.0)
            if self._active_resize_handle is not None
            else QVector4D(0.92, 1.0, 0.82, 1.0)
        )
        self._functions.glDisable(GL_DEPTH_TEST)
        try:
            self._draw_lines(
                vertices,
                view_projection=view_projection,
                color=color,
                line_width=2.2,
            )
        finally:
            self._functions.glEnable(GL_DEPTH_TEST)

    def _selected_bounds_geometry(self) -> np.ndarray:
        """Return world-space AABB line vertices for every selected item."""

        if self.project is None or not self.selected_item_indices:
            return np.empty((0, 3), dtype=np.float32)

        edges = (
            (0, 1),
            (0, 2),
            (0, 4),
            (1, 3),
            (1, 5),
            (2, 3),
            (2, 6),
            (3, 7),
            (4, 5),
            (4, 6),
            (5, 7),
            (6, 7),
        )
        vertices: list[np.ndarray] = []
        for item_index in sorted(self.selected_item_indices):
            if not 0 <= item_index < len(self.project.items):
                continue
            item = self.project.items[item_index]
            if not self._item_viewport_visible(item_index, item):
                continue
            minimum, maximum = self._item_bounds_mm(item)
            corners = np.array(
                [
                    (x, y, z)
                    for x in (minimum[0], maximum[0])
                    for y in (minimum[1], maximum[1])
                    for z in (minimum[2], maximum[2])
                ],
                dtype=np.float32,
            )
            vertices.extend(
                corners[index]
                for edge in edges
                for index in edge
            )
        if not vertices:
            return np.empty((0, 3), dtype=np.float32)
        return np.asarray(vertices, dtype=np.float32).reshape((-1, 3))

    def _selection_indices_in_screen_rect(
        self,
        first: QPointF,
        second: QPointF,
    ) -> list[int]:
        """Return visible objects whose projected bounds intersect a marquee."""

        if self.project is None:
            return []

        left = min(first.x(), second.x())
        right = max(first.x(), second.x())
        top = min(first.y(), second.y())
        bottom = max(first.y(), second.y())

        projection, view_matrix, _world_per_pixel = self._camera_geometry()
        view_projection = projection * view_matrix
        selected: list[int] = []
        for index, item in enumerate(self.project.items):
            if not self._item_viewport_visible(index, item):
                continue
            corners = self._bounds_corners(self._item_bounds_mm(item))
            projected = [
                self._project_world_point(
                    tuple(float(value) for value in corner),
                    view_projection,
                )
                for corner in corners
            ]
            visible = [point for point in projected if point is not None]
            if not visible:
                continue
            item_left = min(point.x() for point in visible)
            item_right = max(point.x() for point in visible)
            item_top = min(point.y() for point in visible)
            item_bottom = max(point.y() for point in visible)
            if not (
                item_right < left
                or item_left > right
                or item_bottom < top
                or item_top > bottom
            ):
                selected.append(index)
        return selected

    def _selection_marquee_vertices(self) -> np.ndarray:
        start = self._selection_drag_start_screen
        current = self._selection_drag_current_screen
        if start is None or current is None:
            return np.empty((0, 3), dtype=np.float32)

        width = float(max(self.width(), 1))
        height = float(max(self.height(), 1))

        def ndc(point: QPointF) -> tuple[float, float, float]:
            return (
                2.0 * float(point.x()) / width - 1.0,
                1.0 - 2.0 * float(point.y()) / height,
                0.0,
            )

        a = ndc(start)
        c = ndc(current)
        b = (c[0], a[1], 0.0)
        d = (a[0], c[1], 0.0)
        return np.asarray(
            (a, b, b, c, c, d, d, a),
            dtype=np.float32,
        )

    def _draw_selection_marquee(self) -> None:
        if (
            self._functions is None
            or self._selection_drag_start_screen is None
            or self._selection_drag_current_screen is None
        ):
            return
        self._functions.glDisable(GL_DEPTH_TEST)
        try:
            self._draw_lines(
                self._selection_marquee_vertices(),
                view_projection=QMatrix4x4(),
                color=QVector4D(0.784, 1.0, 0.239, 0.98),
                line_width=1.5,
            )
        finally:
            self._functions.glEnable(GL_DEPTH_TEST)

