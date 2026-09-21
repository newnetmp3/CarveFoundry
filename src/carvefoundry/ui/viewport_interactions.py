"""Native-window pointer, keyboard, gizmo drag and wheel-LOD interactions.

The host is still the authoritative QOpenGLWindow. No proxy events, QWidget
event forwarding or extra GL contexts are introduced on Wayland.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QCursor, QMouseEvent, QWheelEvent


class ViewportInteractionMixin:
    def _pan_pixels(self, delta: QPointF) -> None:
        _projection, _view, world_per_pixel = self._camera_geometry()
        right, up, _forward = self._camera_basis()

        # Default pan behaves like grabbing the workpiece: dragging right/down
        # moves the scene right/down.  The navigation inversion options flip
        # the corresponding screen axes for both pan and orbit.
        horizontal = -delta.x() if self.reverse_horizontal_drag else delta.x()
        vertical = -delta.y() if self.invert_vertical_drag else delta.y()
        world_delta = (
            -right * horizontal * world_per_pixel
            + up * vertical * world_per_pixel
        )
        pan = np.asarray(self.camera.pan_world, dtype=float) + world_delta
        self.camera.pan_world = tuple(float(value) for value in pan)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._last_mouse_pos = event.position()
        self._press_pos = event.position()
        self._press_item_index = None
        self._interaction_distance = 0.0
        self._object_drag_started = False
        self._active_gizmo_axis = None
        self._gizmo_drag_origin_translation = None
        self._gizmo_drag_axis_world = None
        self._gizmo_drag_accumulated_delta = 0.0
        self._active_resize_handle = None
        self._transform_interaction_kind = None

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._node_edit_mode
            and not event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            picked = self._pick_vector_node(event.position())
            if picked is not None:
                self._node_drag_index = picked
                self._node_drag_item = self.selected_item_index
                self._node_drag_world = self._editable_node_points()[picked].copy()
                self._interaction_mode = "node-drag"
                self.requestUpdate()
                event.accept()
                return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._camera_control_mode
        ):
            self._interaction_mode = "orbit"
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._camera_control_mode
            and self._shape_draw_mode not in {"measure", "fixture"}
            and not (
                event.modifiers() & Qt.KeyboardModifier.AltModifier
            )
        ):
            resize_handle = self.pick_resize_handle(event.position())
            if (
                resize_handle is not None
                and self.selected_item_index is not None
                and self._begin_resize(
                    self.selected_item_index,
                    resize_handle,
                )
            ):
                self._press_item_index = self.selected_item_index
                self._interaction_mode = "object-resize"
                self.requestUpdate()
                event.accept()
                return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._shape_draw_mode is not None
            and not (
                event.modifiers() & Qt.KeyboardModifier.AltModifier
            )
        ):
            point = self._stock_plane_point(event.position())
            if point is not None:
                self._shape_drag_start_world = point
                self._shape_drag_current_world = point.copy()
                if self._shape_draw_mode == "pen":
                    self._freehand_points_world = [point.copy()]
                self._interaction_mode = "shape-draw"
                self.requestUpdate()
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            modifiers = event.modifiers()
            force_orbit = bool(
                modifiers & Qt.KeyboardModifier.AltModifier
            )
            gizmo_axis = None if force_orbit else self.pick_gizmo_axis(
                event.position()
            )
            if (
                gizmo_axis is not None
                and self.selected_item_index is not None
            ):
                self._press_item_index = self.selected_item_index
                self._active_gizmo_axis = gizmo_axis
                item = self.project.items[self.selected_item_index]
                self._gizmo_drag_origin_translation = np.asarray(
                    item.transform.translation_mm,
                    dtype=float,
                )
                self._gizmo_drag_axis_world = self._gizmo_world_axis(gizmo_axis)
                self._gizmo_drag_accumulated_delta = 0.0
                self._interaction_mode = "gizmo"
                self._transform_interaction_kind = "move"
                self.requestUpdate()
            elif force_orbit:
                self._interaction_mode = "orbit"
            else:
                item_index = self.pick_item(event.position())
                selection_mode = self._selection_mode_for_modifiers(modifiers)
                if item_index is not None:
                    self._press_item_index = item_index
                    self._apply_local_selection(
                        [item_index],
                        selection_mode,
                    )
                    self.selectionRequested.emit(
                        [item_index],
                        selection_mode,
                    )
                    self._interaction_mode = "orbit"
                    self.requestUpdate()
                else:
                    self._selection_drag_start_screen = event.position()
                    self._selection_drag_current_screen = event.position()
                    self._selection_drag_mode = selection_mode
                    self._interaction_mode = "marquee"
                    self.requestUpdate()
        elif event.button() in {
            Qt.MouseButton.RightButton,
            Qt.MouseButton.MiddleButton,
        }:
            self._interaction_mode = "pan"
            self._press_item_index = self.pick_item(event.position())
        else:
            self._interaction_mode = None

        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_mouse_pos is None:
            self._last_mouse_pos = event.position()
            return

        delta = event.position() - self._last_mouse_pos
        self._last_mouse_pos = event.position()
        self._interaction_distance += abs(delta.x()) + abs(delta.y())

        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._interaction_mode == "shape-draw"
            and self._shape_drag_start_world is not None
        ):
            current = self._stock_plane_point(event.position())
            if current is not None:
                if self._shape_draw_mode == "pen":
                    self._shape_drag_current_world = current
                    previous = (
                        self._freehand_points_world[-1]
                        if self._freehand_points_world
                        else self._shape_drag_start_world
                    )
                    distance = float(
                        np.linalg.norm(current[:2] - previous[:2])
                    )
                    if distance >= self._pen_sample_spacing_mm:
                        self._freehand_points_world.append(current.copy())
                else:
                    self._shape_drag_current_world = self._constrained_shape_point(
                        self._shape_drag_start_world,
                        current,
                        event.modifiers(),
                    )
                if (
                    self._shape_draw_mode in {"measure", "fixture"}
                    and self._shape_drag_current_world is not None
                ):
                    start = self._shape_drag_start_world
                    end = self._shape_drag_current_world
                    self.shapeDragUpdated.emit(
                        self._shape_draw_mode,
                        float(start[0]), float(start[1]),
                        float(end[0]), float(end[1]),
                    )
                self.requestUpdate()
            event.accept()
            return

        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._interaction_mode == "node-drag"
            and self._node_drag_world is not None
        ):
            point = self._stock_plane_point(event.position())
            if point is not None:
                self._node_drag_world[:2] = point[:2]
                self.requestUpdate()
            event.accept()
            return

        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._interaction_mode == "marquee"
        ):
            self._selection_drag_current_screen = event.position()
            self.requestUpdate()
            event.accept()
            return

        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._interaction_mode == "object-resize"
            and self._press_item_index is not None
            and self._active_resize_handle is not None
            and self.project is not None
        ):
            factor = self._resize_factor_from_cursor(event.position())
            if factor is not None:
                clamped_factor = max(
                    self.RESIZE_MIN_FACTOR,
                    min(self.RESIZE_MAX_FACTOR, factor),
                )
                if not self._object_drag_started:
                    self._object_drag_started = True
                    self.itemTransformStarted.emit(self._press_item_index)
                if self._apply_resize_factor(
                    self._press_item_index,
                    clamped_factor,
                ):
                    self.itemTransformChanged.emit(self._press_item_index)
                    self.requestUpdate()
                    self.viewChanged.emit()
            event.accept()
            return

        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._interaction_mode == "gizmo"
            and self._press_item_index is not None
            and self._active_gizmo_axis is not None
            and self.project is not None
        ):
            axis_delta = self._gizmo_axis_drag_delta(
                self._press_item_index,
                self._active_gizmo_axis,
                delta,
            )
            if (
                axis_delta is not None
                and abs(axis_delta) > 1e-12
                and self._gizmo_drag_origin_translation is not None
                and self._gizmo_drag_axis_world is not None
            ):
                self._gizmo_drag_accumulated_delta += float(axis_delta)
                distance = self._snap_gizmo_distance(
                    self._gizmo_drag_accumulated_delta,
                    event.modifiers(),
                )

                candidate = (
                    self._gizmo_drag_origin_translation
                    + self._gizmo_drag_axis_world * distance
                )
                item = self.project.items[self._press_item_index]
                current = np.asarray(
                    item.transform.translation_mm,
                    dtype=float,
                )
                if not np.allclose(candidate, current, atol=1e-10):
                    if not self._object_drag_started:
                        self._object_drag_started = True
                        self.itemTransformStarted.emit(self._press_item_index)
                    item.transform.translation_mm = tuple(
                        float(value) for value in candidate
                    )
                    self.itemTransformChanged.emit(self._press_item_index)
                    self.requestUpdate()
                    self.viewChanged.emit()
        elif (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._interaction_mode == "orbit"
        ):
            horizontal = (
                delta.x() if self.reverse_horizontal_drag else -delta.x()
            )
            vertical = (
                -delta.y() if self.invert_vertical_drag else delta.y()
            )
            self.camera.yaw_deg += horizontal * 0.45
            self.camera.elevation_deg = max(
                -89.9,
                min(89.9, self.camera.elevation_deg + vertical * 0.35),
            )
            self.orbitStarted.emit()
            self.requestUpdate()
            self.viewChanged.emit()
        elif (
            event.buttons()
            & (Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton)
            and self._interaction_mode == "pan"
        ):
            self._pan_pixels(delta)
            self.requestUpdate()
            self.viewChanged.emit()

        if event.buttons() == Qt.MouseButton.NoButton:
            handle = self.pick_resize_handle(event.position())
            if handle is not None:
                diagonal = handle in {0, 2}
                cursor = (
                    Qt.CursorShape.SizeFDiagCursor
                    if diagonal
                    else Qt.CursorShape.SizeBDiagCursor
                )
                self.setCursor(QCursor(cursor))
            else:
                self._update_interaction_cursor()

        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._interaction_mode == "node-drag"
        ):
            point = self._stock_plane_point(event.position())
            if point is not None and self._node_drag_index is not None and (
                self._node_drag_item is not None
            ):
                self.nodeMoveRequested.emit(
                    self._node_drag_item, self._node_drag_index,
                    float(point[0]), float(point[1]),
                )
            self._node_drag_index = None
            self._node_drag_item = None
            self._node_drag_world = None
            self._interaction_mode = None
            self.requestUpdate()
            event.accept()
            return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._interaction_mode == "shape-draw"
            and self._shape_draw_mode == "pen"
            and self._shape_drag_start_world is not None
        ):
            current = self._stock_plane_point(event.position())
            if current is not None:
                self._shape_drag_current_world = current
                previous = (
                    self._freehand_points_world[-1]
                    if self._freehand_points_world
                    else self._shape_drag_start_world
                )
                if float(np.linalg.norm(current[:2] - previous[:2])) > 1e-9:
                    self._freehand_points_world.append(current.copy())

            points = [
                (float(point[0]), float(point[1]))
                for point in self._freehand_points_world
            ]
            if len(points) >= 2:
                self.freehandStrokeRequested.emit(points)

            self._shape_drag_start_world = None
            self._shape_drag_current_world = None
            self._freehand_points_world = []
            self._last_mouse_pos = None
            self._press_pos = None
            self._interaction_mode = None
            self._interaction_distance = 0.0
            self.requestUpdate()
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._interaction_mode == "shape-draw"
            and self._shape_draw_mode is not None
            and self._shape_drag_start_world is not None
        ):
            current = self._stock_plane_point(event.position())
            if current is not None:
                self._shape_drag_current_world = self._constrained_shape_point(
                    self._shape_drag_start_world,
                    current,
                    event.modifiers(),
                )
            end = self._shape_drag_current_world
            start = self._shape_drag_start_world
            if end is not None:
                distance = float(np.linalg.norm(end[:2] - start[:2]))
                if distance >= 0.10:
                    self.shapeDrawRequested.emit(
                        self._shape_draw_mode,
                        float(start[0]),
                        float(start[1]),
                        float(end[0]),
                        float(end[1]),
                    )
            self._shape_drag_start_world = None
            self._shape_drag_current_world = None
            self._last_mouse_pos = None
            self._press_pos = None
            self._interaction_mode = None
            self._interaction_distance = 0.0
            self.requestUpdate()
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._interaction_mode in {"gizmo", "object-resize"}
            and self._object_drag_started
            and self._press_item_index is not None
        ):
            self.itemTransformFinished.emit(self._press_item_index)
        elif (
            event.button() == Qt.MouseButton.LeftButton
            and self._interaction_mode == "marquee"
            and self._selection_drag_start_screen is not None
        ):
            self._selection_drag_current_screen = event.position()
            if self._interaction_distance >= 4.0:
                indices = self._selection_indices_in_screen_rect(
                    self._selection_drag_start_screen,
                    self._selection_drag_current_screen,
                )
                self._apply_local_selection(
                    indices,
                    self._selection_drag_mode,
                )
                self.selectionRequested.emit(
                    indices,
                    self._selection_drag_mode,
                )
            elif self._selection_drag_mode == "replace":
                self._apply_local_selection([], "replace")
                self.selectionRequested.emit([], "replace")
            self._selection_drag_start_screen = None
            self._selection_drag_current_screen = None
            self.requestUpdate()
        elif (
            event.button() == Qt.MouseButton.RightButton
            and self._interaction_mode == "pan"
            and self._interaction_distance < 4.0
        ):
            item_index = self.pick_item(event.position())
            if item_index is not None:
                self._apply_local_selection([item_index], "replace")
                self.selectionRequested.emit([item_index], "replace")
                self.itemSelectionRequested.emit(item_index)
                self.itemContextMenuRequested.emit(
                    item_index,
                    event.globalPosition().toPoint(),
                )
                self.requestUpdate()

        self._last_mouse_pos = None
        self._press_pos = None
        self._press_item_index = None
        self._interaction_mode = None
        self._interaction_distance = 0.0
        self._selection_drag_start_screen = None
        self._selection_drag_current_screen = None
        self._object_drag_started = False
        self._active_gizmo_axis = None
        self._gizmo_drag_origin_translation = None
        self._gizmo_drag_axis_world = None
        self._gizmo_drag_accumulated_delta = 0.0
        self._active_resize_handle = None
        self._resize_initial_scale = None
        self._resize_initial_translation = None
        self._resize_active_vector_world = None
        self._resize_active_world = None
        self._resize_opposite_world = None
        self._transform_interaction_kind = None
        self._update_interaction_cursor()
        self.requestUpdate()
        event.accept()

    def keyPressEvent(self, event) -> None:
        """Handle drawing-mode cancellation or nudge the selected object."""
        if event.key() == Qt.Key.Key_Escape and self._node_edit_mode:
            self.set_node_edit_mode(False)
            event.accept()
            return

        if (
            event.key() == Qt.Key.Key_Escape
            and self._shape_draw_mode is not None
        ):
            self.set_shape_draw_mode(None)
            event.accept()
            return

        if (
            self.project is None
            or len(self.selected_item_indices) != 1
            or self.selected_item_index is None
            or self.selected_item_index not in self.selected_item_indices
            or not 0 <= self.selected_item_index < len(self.project.items)
        ):
            super().keyPressEvent(event)
            return

        modifiers = event.modifiers()
        step = 10.0 if modifiers & Qt.KeyboardModifier.ShiftModifier else 1.0
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            step = 0.1

        dx = dy = dz = 0.0
        if event.key() == Qt.Key.Key_Left:
            dx = -step
        elif event.key() == Qt.Key.Key_Right:
            dx = step
        elif event.key() == Qt.Key.Key_Up:
            dy = step
        elif event.key() == Qt.Key.Key_Down:
            dy = -step
        elif event.key() == Qt.Key.Key_PageUp:
            dz = step
        elif event.key() == Qt.Key.Key_PageDown:
            dz = -step
        else:
            super().keyPressEvent(event)
            return

        item = self.project.items[self.selected_item_index]
        tx, ty, tz = item.transform.translation_mm
        self.itemTransformStarted.emit(self.selected_item_index)
        item.transform.translation_mm = (tx + dx, ty + dy, tz + dz)
        self.itemTransformChanged.emit(self.selected_item_index)
        self.itemTransformFinished.emit(self.selected_item_index)
        self.requestUpdate()
        self.viewChanged.emit()
        event.accept()

    def _toolpath_interactive_lod_active(self) -> bool:
        """Return whether the temporary low-detail toolpath should be drawn.

        Mouse orbit/pan is authoritative while the button is held. Wheel zoom
        uses a short restartable idle timer because wheel events have no matching
        release event. No frame-count state is used: that could leave the final
        simplified frame on screen when no later repaint was scheduled.
        """

        return (
            self._interaction_mode in {"orbit", "pan"}
            or self._toolpath_wheel_lod_active
        )

    def _restore_toolpath_full_detail(self) -> None:
        self._toolpath_lod_restore_timer.stop()
        self._toolpath_wheel_lod_active = False
        self.requestUpdate()

    def wheelEvent(self, event: QWheelEvent) -> None:
        self._toolpath_wheel_lod_active = True
        self._toolpath_lod_restore_timer.start()
        angle_steps = event.angleDelta().y() / 120.0
        steps = angle_steps if angle_steps else event.pixelDelta().y() / 120.0
        if steps:
            self.zoom = self.camera.zoom * (1.20**steps)
            self.requestUpdate()
            self.viewChanged.emit()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # Double-click is a convenient Fit View shortcut only on the empty
        # black margin, never on a model or the stock work area. The hit check
        # uses the native viewport's ray, not clamped drawing coordinates.
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._is_empty_viewport_background(event.position())
        ):
            self.fitRequested.emit()
        event.accept()

