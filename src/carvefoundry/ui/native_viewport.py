from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import atan, cos, degrees, floor, log10, radians, sin, tan
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QMatrix4x4,
    QMouseEvent,
    QPainter,
    QSurfaceFormat,
    QVector3D,
    QVector4D,
    QWheelEvent,
)
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
    QOpenGLWindow,
)
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from carvefoundry.cam.toolpath import MoveKind

from .gpu_geometry import expand_triangle_positions

if TYPE_CHECKING:
    from carvefoundry.core.project import Project, ProjectItem


GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_DEPTH_TEST = 0x0B71
GL_BLEND = 0x0BE2
GL_CULL_FACE = 0x0B44
GL_BACK = 0x0405
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_LEQUAL = 0x0203
GL_FLOAT = 0x1406
GL_TRIANGLES = 0x0004
GL_LINES = 0x0001

_MESH_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 a_position;

uniform mat4 u_model;
uniform mat4 u_view_projection;

out vec3 v_world_position;

void main()
{
    vec4 world = u_model * vec4(a_position, 1.0);
    v_world_position = world.xyz;
    gl_Position = u_view_projection * world;
}
"""

_MESH_FRAGMENT_SHADER = """
#version 330 core
in vec3 v_world_position;

uniform vec4 u_color;
uniform vec3 u_light_direction;

out vec4 frag_color;

void main()
{
    vec3 dx = dFdx(v_world_position);
    vec3 dy = dFdy(v_world_position);
    vec3 normal = normalize(cross(dx, dy));
    vec3 light_dir = normalize(u_light_direction);
    float diffuse = 0.35 + 0.65 * abs(dot(normal, light_dir));
    frag_color = vec4(u_color.rgb * diffuse, u_color.a);
}
"""

_LINE_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 a_position;

uniform mat4 u_mvp;

void main()
{
    gl_Position = u_mvp * vec4(a_position, 1.0);
}
"""

_LINE_FRAGMENT_SHADER = """
#version 330 core
uniform vec4 u_color;

out vec4 frag_color;

void main()
{
    frag_color = u_color;
}
"""

_STOCK_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 a_position;

uniform mat4 u_mvp;

void main()
{
    gl_Position = u_mvp * vec4(a_position, 1.0);
}
"""

_STOCK_FRAGMENT_SHADER = """
#version 330 core
uniform vec4 u_base_color;

out vec4 frag_color;

void main()
{
    frag_color = u_base_color;
}
"""


@dataclass(slots=True)
class _GpuMesh:
    source_mesh: object
    vao: QOpenGLVertexArrayObject
    vertex_buffer: QOpenGLBuffer
    vertex_count: int

    def destroy(self) -> None:
        if self.vertex_buffer.isCreated():
            self.vertex_buffer.destroy()
        if self.vao.isCreated():
            self.vao.destroy()


@dataclass(slots=True)
class _GpuLineGeometry:
    vao: QOpenGLVertexArrayObject
    vertex_buffer: QOpenGLBuffer
    vertex_count: int = 0

    def destroy(self) -> None:
        if self.vertex_buffer.isCreated():
            self.vertex_buffer.destroy()
        if self.vao.isCreated():
            self.vao.destroy()


@dataclass(slots=True)
class _ToolpathRenderCache:
    key: tuple[tuple[int, int, int], ...]
    cut_vertices: np.ndarray
    rapid_vertices: np.ndarray
    cut_lod_vertices: np.ndarray
    rapid_lod_vertices: np.ndarray
    rapid_prefix: np.ndarray
    points: np.ndarray
    bounds: np.ndarray | None
    segment_count: int
    lod_stride: int

    @classmethod
    def empty(
        cls,
        key: tuple[tuple[int, int, int], ...] = (),
    ) -> "_ToolpathRenderCache":
        vertices = np.empty((0, 3), dtype=np.float32)
        return cls(
            key=key,
            cut_vertices=vertices,
            rapid_vertices=vertices.copy(),
            cut_lod_vertices=vertices.copy(),
            rapid_lod_vertices=vertices.copy(),
            rapid_prefix=np.zeros(1, dtype=np.uint32),
            points=vertices.copy(),
            bounds=None,
            segment_count=0,
            lod_stride=1,
        )


@dataclass(slots=True)
class _CameraState:
    # Default to a CNC-friendly XY plan view: +X right, +Y up, with the
    # stock origin at the lower-left.  Perspective remains the default
    # projection so orbiting immediately behaves like a 3D workspace.
    yaw_deg: float = -90.0
    elevation_deg: float = 90.0
    zoom: float = 1.0
    pan_world: tuple[float, float, float] = (0.0, 0.0, 0.0)
    projection_mode: str = "perspective"


class _NativeOpenGLViewport(QOpenGLWindow):
    """Native OpenGL surface with one authoritative CAD camera state."""

    rendererStatusChanged = Signal(str)
    orbitStarted = Signal()
    fitRequested = Signal()
    viewChanged = Signal()
    itemSelectionRequested = Signal(int)
    selectionRequested = Signal(object, str)
    itemContextMenuRequested = Signal(int, QPoint)
    itemTransformStarted = Signal(int)
    itemTransformChanged = Signal(int)
    itemTransformFinished = Signal(int)
    shapeDrawRequested = Signal(str, float, float, float, float)
    freehandStrokeRequested = Signal(object)
    shapeDrawModeChanged = Signal(str)

    MIN_ZOOM = 0.01
    MAX_ZOOM = 100_000.0
    PERSPECTIVE_FOV_DEG = 45.0
    FIT_MARGIN = 1.10
    ISOMETRIC_ELEVATION_DEG = 35.26438968
    GIZMO_LENGTH_PX = 72.0
    GIZMO_PICK_RADIUS_PX = 10.0
    GIZMO_MIN_PROJECTED_PX = 18.0
    RESIZE_HANDLE_RADIUS_PX = 11.0
    RESIZE_HANDLE_HALF_SIZE_PX = 5.5
    RESIZE_MIN_FACTOR = 0.05
    RESIZE_MAX_FACTOR = 100.0
    TOOLPATH_INTERACTIVE_SEGMENT_BUDGET = 120_000

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self.setFormat(QSurfaceFormat.defaultFormat())

        self.project = project
        self.selected_item_index: int | None = None
        self.selected_item_indices: set[int] = set()
        self.camera = _CameraState()
        self.show_stock = True
        self.show_grid = True
        self.show_toolpaths = True
        self.show_rapids = False
        self.show_toolpath_points = False
        self.simulation_fraction = 1.0
        self.toolpath_marker_xyz: tuple[float, float, float] | None = None
        self.reverse_horizontal_drag = False
        self.invert_vertical_drag = False
        self.transform_orientation = "global"
        self.snap_enabled = False
        self.snap_step_mm = 1.0
        self._isolated_item_indices: set[int] | None = None
        self._camera_control_mode = True

        self._last_mouse_pos: QPointF | None = None
        self._press_pos: QPointF | None = None
        self._press_item_index: int | None = None
        self._interaction_mode: str | None = None
        self._interaction_distance = 0.0
        self._object_drag_started = False
        self._active_gizmo_axis: int | None = None
        self._gizmo_drag_origin_translation: np.ndarray | None = None
        self._gizmo_drag_axis_world: np.ndarray | None = None
        self._gizmo_drag_accumulated_delta = 0.0
        self._active_resize_handle: int | None = None
        self._resize_initial_scale: tuple[float, float, float] | None = None
        self._resize_initial_translation: tuple[float, float, float] | None = None
        self._resize_active_vector_world: np.ndarray | None = None
        self._resize_active_world: np.ndarray | None = None
        self._resize_opposite_world: np.ndarray | None = None
        self._transform_interaction_kind: str | None = None
        self._shape_draw_mode: str | None = None
        self._shape_drag_start_world: np.ndarray | None = None
        self._shape_drag_current_world: np.ndarray | None = None
        self._freehand_points_world: list[np.ndarray] = []
        self._pen_sample_spacing_mm = 0.35
        self._selection_drag_start_screen: QPointF | None = None
        self._selection_drag_current_screen: QPointF | None = None
        self._selection_drag_mode = "replace"
        self._functions = None
        self._mesh_program: QOpenGLShaderProgram | None = None
        self._line_program: QOpenGLShaderProgram | None = None
        self._stock_program: QOpenGLShaderProgram | None = None
        self._line_vao: QOpenGLVertexArrayObject | None = None
        self._line_buffer: QOpenGLBuffer | None = None
        self._toolpath_cut_gpu: _GpuLineGeometry | None = None
        self._toolpath_rapid_gpu: _GpuLineGeometry | None = None
        self._toolpath_cut_lod_gpu: _GpuLineGeometry | None = None
        self._toolpath_rapid_lod_gpu: _GpuLineGeometry | None = None
        self._toolpath_gpu_key: tuple[tuple[int, int, int], ...] | None = None
        self._toolpath_render_cache = _ToolpathRenderCache.empty()
        self._toolpath_interaction_lod_frames = 0
        self._mesh_cache: dict[int, _GpuMesh] = {}
        self._prepared_mesh_uploads: dict[int, tuple[object, bytes, int]] = {}
        self._renderer_description = "Native OpenGL initializing…"
        self._gl_error: str | None = None
        self._update_interaction_cursor()

    @property
    def yaw_deg(self) -> float:
        return self.camera.yaw_deg

    @yaw_deg.setter
    def yaw_deg(self, value: float) -> None:
        self.camera.yaw_deg = float(value)

    @property
    def elevation_deg(self) -> float:
        return self.camera.elevation_deg

    @elevation_deg.setter
    def elevation_deg(self, value: float) -> None:
        self.camera.elevation_deg = float(value)

    @property
    def zoom(self) -> float:
        return self.camera.zoom

    @zoom.setter
    def zoom(self, value: float) -> None:
        self.camera.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(value)))

    @property
    def projection_mode(self) -> str:
        return self.camera.projection_mode

    @projection_mode.setter
    def projection_mode(self, value: str) -> None:
        self.camera.projection_mode = (
            "perspective" if value == "perspective" else "orthographic"
        )

    def set_project(
        self,
        project: Project,
        *,
        fit_view: bool = True,
    ) -> None:
        self.project = project
        self.selected_item_index = None
        self.selected_item_indices.clear()
        self._selection_drag_start_screen = None
        self._selection_drag_current_screen = None
        self._active_resize_handle = None
        self._resize_initial_scale = None
        self._resize_initial_translation = None
        self._resize_active_vector_world = None
        self._resize_active_world = None
        self._resize_opposite_world = None
        self._transform_interaction_kind = None
        self._isolated_item_indices = None
        self._gizmo_drag_origin_translation = None
        self._gizmo_drag_axis_world = None
        self._gizmo_drag_accumulated_delta = 0.0
        self._prepared_mesh_uploads.clear()
        self._invalidate_toolpath_render_cache()
        if fit_view:
            self.fit_view()
        else:
            self.requestUpdate()
            self.viewChanged.emit()

    def set_selected_item(self, index: int | None) -> None:
        self.set_selected_items(
            [] if index is None else [index],
            primary=index,
        )

    def set_selected_items(
        self,
        indices: list[int] | tuple[int, ...] | set[int],
        *,
        primary: int | None = None,
    ) -> None:
        valid = {
            int(index)
            for index in indices
            if self.project is not None
            and 0 <= int(index) < len(self.project.items)
        }
        self.selected_item_indices = valid
        if self._interaction_mode != "object-resize":
            self._active_resize_handle = None
            self._transform_interaction_kind = None
        if primary in valid:
            self.selected_item_index = int(primary)
        elif valid:
            self.selected_item_index = max(valid)
        else:
            self.selected_item_index = None
        self.requestUpdate()
        self.viewChanged.emit()

    @staticmethod
    def _selection_mode_for_modifiers(
        modifiers: Qt.KeyboardModifier,
    ) -> str:
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            return "toggle"
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            return "add"
        return "replace"

    def _apply_local_selection(
        self,
        indices: list[int],
        mode: str,
    ) -> None:
        incoming = {
            int(index)
            for index in indices
            if self.project is not None
            and 0 <= int(index) < len(self.project.items)
        }
        selected = set(self.selected_item_indices)
        if mode == "add":
            selected |= incoming
        elif mode == "toggle":
            selected ^= incoming
        else:
            selected = incoming

        primary = None
        if incoming:
            for index in reversed(indices):
                if int(index) in selected:
                    primary = int(index)
                    break
        if primary is None and self.selected_item_index in selected:
            primary = self.selected_item_index
        self.set_selected_items(selected, primary=primary)

    def prepare_mesh_upload(
        self,
        source_mesh: object,
        vertex_bytes: bytes,
        vertex_count: int,
    ) -> None:
        if vertex_count <= 0 or not vertex_bytes:
            return
        self._prepared_mesh_uploads[id(source_mesh)] = (
            source_mesh,
            vertex_bytes,
            int(vertex_count),
        )
        # The prepared upload can arrive between regular expose/paint events.
        # Request a frame immediately so newly imported geometry does not wait
        # for mouse or keyboard interaction before becoming visible.
        self.requestUpdate()

    def fit_view(self) -> None:
        self.camera.zoom = 1.0
        self.camera.pan_world = (0.0, 0.0, 0.0)
        self.requestUpdate()
        self.viewChanged.emit()

    def _item_viewport_visible(self, index: int, item: ProjectItem) -> bool:
        if not item.visible or item.mesh is None:
            return False
        return (
            self._isolated_item_indices is None
            or index in self._isolated_item_indices
        )

    def _visible_toolpaths(self) -> list:
        if self.project is None:
            return []
        if self._isolated_item_indices is None:
            return list(self.project.toolpaths)
        isolated_ids = {
            self.project.items[index].item_id
            for index in self._isolated_item_indices
            if 0 <= index < len(self.project.items)
        }
        return [
            toolpath
            for toolpath in self.project.toolpaths
            if toolpath.source_item_id in isolated_ids
        ]

    def _toolpath_cache_key(
        self,
        toolpaths: list,
    ) -> tuple[tuple[int, int, int], ...]:
        return tuple(
            (id(toolpath), id(toolpath.moves), len(toolpath.moves))
            for toolpath in toolpaths
        )

    def _invalidate_toolpath_render_cache(self) -> None:
        self._toolpath_render_cache = _ToolpathRenderCache.empty()
        self._toolpath_gpu_key = None

    def _ensure_toolpath_render_cache(self) -> _ToolpathRenderCache:
        toolpaths = self._visible_toolpaths()
        key = self._toolpath_cache_key(toolpaths)
        if self._toolpath_render_cache.key == key:
            return self._toolpath_render_cache

        if not toolpaths:
            self._toolpath_render_cache = _ToolpathRenderCache.empty(key)
            self._toolpath_gpu_key = None
            return self._toolpath_render_cache

        cut_chunks: list[np.ndarray] = []
        rapid_chunks: list[np.ndarray] = []
        point_chunks: list[np.ndarray] = []
        rapid_flag_chunks: list[np.ndarray] = []
        segment_count = 0

        for toolpath in toolpaths:
            moves = toolpath.moves
            move_count = len(moves)
            if move_count == 0:
                continue

            coords = np.fromiter(
                (
                    coordinate
                    for move in moves
                    for coordinate in move.xyz
                ),
                dtype=np.float32,
                count=move_count * 3,
            ).reshape((-1, 3))
            point_chunks.append(coords)
            if move_count < 2:
                continue

            rapid_flags = np.fromiter(
                (
                    move.kind is MoveKind.RAPID
                    for move in moves[1:]
                ),
                dtype=np.bool_,
                count=move_count - 1,
            )
            segments = np.empty(
                (move_count - 1, 2, 3),
                dtype=np.float32,
            )
            segments[:, 0, :] = coords[:-1]
            segments[:, 1, :] = coords[1:]
            if np.any(~rapid_flags):
                cut_chunks.append(
                    segments[~rapid_flags].reshape((-1, 3))
                )
            if np.any(rapid_flags):
                rapid_chunks.append(
                    segments[rapid_flags].reshape((-1, 3))
                )
            rapid_flag_chunks.append(rapid_flags)
            segment_count += move_count - 1

        empty = np.empty((0, 3), dtype=np.float32)
        cut_vertices = (
            np.concatenate(cut_chunks, axis=0)
            if cut_chunks
            else empty.copy()
        )
        rapid_vertices = (
            np.concatenate(rapid_chunks, axis=0)
            if rapid_chunks
            else empty.copy()
        )
        points = (
            np.concatenate(point_chunks, axis=0)
            if point_chunks
            else empty.copy()
        )

        if rapid_flag_chunks:
            rapid_flags = np.concatenate(rapid_flag_chunks)
            rapid_prefix = np.empty(
                len(rapid_flags) + 1,
                dtype=np.uint32,
            )
            rapid_prefix[0] = 0
            np.cumsum(
                rapid_flags,
                dtype=np.uint32,
                out=rapid_prefix[1:],
            )
        else:
            rapid_prefix = np.zeros(1, dtype=np.uint32)

        lod_stride = max(
            1,
            int(
                np.ceil(
                    segment_count
                    / self.TOOLPATH_INTERACTIVE_SEGMENT_BUDGET
                )
            ),
        )

        def decimate(vertices: np.ndarray) -> np.ndarray:
            if lod_stride <= 1 or len(vertices) <= 2:
                return vertices
            segments = vertices.reshape((-1, 2, 3))
            return np.ascontiguousarray(
                segments[::lod_stride].reshape((-1, 3)),
                dtype=np.float32,
            )

        bounds = None
        if len(points):
            bounds = np.vstack(
                (
                    np.min(points, axis=0),
                    np.max(points, axis=0),
                )
            ).astype(float)

        self._toolpath_render_cache = _ToolpathRenderCache(
            key=key,
            cut_vertices=np.ascontiguousarray(
                cut_vertices,
                dtype=np.float32,
            ),
            rapid_vertices=np.ascontiguousarray(
                rapid_vertices,
                dtype=np.float32,
            ),
            cut_lod_vertices=decimate(cut_vertices),
            rapid_lod_vertices=decimate(rapid_vertices),
            rapid_prefix=rapid_prefix,
            points=np.ascontiguousarray(points, dtype=np.float32),
            bounds=bounds,
            segment_count=segment_count,
            lod_stride=lod_stride,
        )
        self._toolpath_gpu_key = None
        return self._toolpath_render_cache

    @property
    def isolated(self) -> bool:
        return self._isolated_item_indices is not None

    def isolate_selected(self) -> bool:
        if self.project is None:
            return False
        isolated = {
            index
            for index in self.selected_item_indices
            if 0 <= index < len(self.project.items)
            and self.project.items[index].visible
            and self.project.items[index].mesh is not None
        }
        if not isolated:
            return False
        self._isolated_item_indices = isolated
        self._invalidate_toolpath_render_cache()
        self.requestUpdate()
        self.viewChanged.emit()
        return True

    def show_all_items(self) -> None:
        if self._isolated_item_indices is None:
            return
        self._isolated_item_indices = None
        self._invalidate_toolpath_render_cache()
        self.requestUpdate()
        self.viewChanged.emit()

    def frame_selected(self) -> bool:
        if self.project is None or not self.selected_item_indices:
            return False
        bounds = [
            self._item_bounds_mm(self.project.items[index])
            for index in sorted(self.selected_item_indices)
            if 0 <= index < len(self.project.items)
            and self.project.items[index].visible
            and self.project.items[index].mesh is not None
        ]
        if not bounds:
            return False

        selected_minimum = np.min(
            np.vstack([item_bounds[0] for item_bounds in bounds]),
            axis=0,
        )
        selected_maximum = np.max(
            np.vstack([item_bounds[1] for item_bounds in bounds]),
            axis=0,
        )
        selected_bounds = np.vstack((selected_minimum, selected_maximum))
        scene_bounds = self._full_scene_bounds()
        scene_center = scene_bounds.mean(axis=0)
        selected_center = selected_bounds.mean(axis=0)
        scene_diagonal = max(
            float(np.linalg.norm(scene_bounds[1] - scene_bounds[0])),
            1e-6,
        )
        selected_diagonal = max(
            float(np.linalg.norm(selected_bounds[1] - selected_bounds[0])),
            1e-6,
        )

        self.camera.pan_world = tuple(
            float(value)
            for value in selected_center - scene_center
        )
        self.camera.zoom = max(
            self.MIN_ZOOM,
            min(
                self.MAX_ZOOM,
                scene_diagonal / selected_diagonal,
            ),
        )
        self.requestUpdate()
        self.viewChanged.emit()
        return True

    def set_transform_orientation(self, orientation: str) -> None:
        normalized = str(orientation).strip().lower()
        if normalized not in {"global", "local"}:
            raise ValueError(
                f"Unsupported transform orientation: {orientation}"
            )
        self.transform_orientation = normalized
        self.requestUpdate()

    def set_transform_snapping(
        self,
        enabled: bool,
        step_mm: float | None = None,
    ) -> None:
        self.snap_enabled = bool(enabled)
        if step_mm is not None:
            self.snap_step_mm = max(0.001, float(step_mm))

    def _snap_gizmo_distance(
        self,
        distance_mm: float,
        modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    ) -> float:
        snap_active = self.snap_enabled or bool(
            modifiers & Qt.KeyboardModifier.ControlModifier
        )
        if not snap_active:
            return float(distance_mm)
        step = max(self.snap_step_mm, 0.001)
        return round(float(distance_mm) / step) * step

    def toggle_stock(self) -> None:
        self.show_stock = not self.show_stock
        self.requestUpdate()

    def toggle_grid(self) -> None:
        self.show_grid = not self.show_grid
        self.requestUpdate()
        self.viewChanged.emit()

    def set_toolpaths_visible(self, visible: bool) -> None:
        self.show_toolpaths = bool(visible)
        self.requestUpdate()
        self.viewChanged.emit()

    def set_rapids_visible(self, visible: bool) -> None:
        self.show_rapids = bool(visible)
        self.requestUpdate()
        self.viewChanged.emit()

    def set_toolpath_points_visible(self, visible: bool) -> None:
        self.show_toolpath_points = bool(visible)
        self.requestUpdate()

    def set_toolpath_marker(
        self,
        xyz: tuple[float, float, float] | None,
    ) -> None:
        self.toolpath_marker_xyz = xyz
        self.requestUpdate()

    def set_simulation_fraction(self, fraction: float) -> None:
        self.simulation_fraction = max(0.0, min(1.0, float(fraction)))
        self.requestUpdate()
        self.viewChanged.emit()

    def set_reverse_horizontal_drag(self, enabled: bool) -> None:
        self.reverse_horizontal_drag = bool(enabled)

    def set_invert_vertical_drag(self, enabled: bool) -> None:
        self.invert_vertical_drag = bool(enabled)

    @property
    def shape_draw_mode(self) -> str | None:
        return self._shape_draw_mode

    def _update_interaction_cursor(self) -> None:
        if self._camera_control_mode:
            shape = Qt.CursorShape.OpenHandCursor
        elif self._shape_draw_mode is not None:
            shape = Qt.CursorShape.CrossCursor
        else:
            shape = Qt.CursorShape.ArrowCursor
        self.setCursor(QCursor(shape))

    @property
    def transform_interaction_kind(self) -> str | None:
        return self._transform_interaction_kind

    @property
    def camera_control_mode(self) -> bool:
        return self._camera_control_mode

    def set_camera_control_mode(self, enabled: bool) -> None:
        self._camera_control_mode = bool(enabled)
        self._interaction_mode = None
        self._selection_drag_start_screen = None
        self._selection_drag_current_screen = None
        self._active_gizmo_axis = None
        self._gizmo_drag_origin_translation = None
        self._gizmo_drag_axis_world = None
        self._gizmo_drag_accumulated_delta = 0.0
        self._active_resize_handle = None
        self._transform_interaction_kind = None
        self._toolpath_interaction_lod_frames = 0
        self._update_interaction_cursor()
        self.requestUpdate()

    def set_pen_sample_spacing(self, spacing_mm: float) -> None:
        self._pen_sample_spacing_mm = max(0.02, float(spacing_mm))

    def set_shape_draw_mode(self, mode: str | None) -> None:
        normalized = mode.lower() if mode else None
        allowed = {"rectangle", "ellipse", "polygon", "line", "text", "pen"}
        if normalized is not None and normalized not in allowed:
            raise ValueError(f"Unsupported shape draw mode: {mode}")

        self._shape_draw_mode = normalized
        self._shape_drag_start_world = None
        self._shape_drag_current_world = None
        self._freehand_points_world = []
        self._interaction_mode = None
        self._active_gizmo_axis = None
        self._gizmo_drag_origin_translation = None
        self._gizmo_drag_axis_world = None
        self._gizmo_drag_accumulated_delta = 0.0
        self._active_resize_handle = None
        self._transform_interaction_kind = None
        self._update_interaction_cursor()
        self.shapeDrawModeChanged.emit(normalized or "")
        self.requestUpdate()

    @staticmethod
    def _compile_program(
        vertex_source: str,
        fragment_source: str,
    ) -> QOpenGLShaderProgram:
        program = QOpenGLShaderProgram()
        if not program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex,
            vertex_source,
        ):
            raise RuntimeError(f"Vertex shader compilation failed: {program.log()}")
        if not program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment,
            fragment_source,
        ):
            raise RuntimeError(f"Fragment shader compilation failed: {program.log()}")
        if not program.link():
            raise RuntimeError(f"Shader link failed: {program.log()}")
        return program

    @staticmethod
    def _qmatrix_from_numpy(matrix: np.ndarray) -> QMatrix4x4:
        values = [float(value) for value in np.asarray(matrix, dtype=float).reshape(16)]
        return QMatrix4x4(*values)

    def initializeGL(self) -> None:
        context = self.context()
        if context is None:
            self._gl_error = "OpenGL context creation failed."
            self.rendererStatusChanged.emit(self._gl_error)
            return

        try:
            self._functions = context.functions()
            self._functions.glEnable(GL_DEPTH_TEST)
            self._functions.glEnable(GL_BLEND)
            self._functions.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            self._functions.glDepthFunc(GL_LEQUAL)
            self._functions.glClearColor(0.067, 0.094, 0.153, 1.0)

            self._mesh_program = self._compile_program(
                _MESH_VERTEX_SHADER,
                _MESH_FRAGMENT_SHADER,
            )
            self._line_program = self._compile_program(
                _LINE_VERTEX_SHADER,
                _LINE_FRAGMENT_SHADER,
            )
            self._stock_program = self._compile_program(
                _STOCK_VERTEX_SHADER,
                _STOCK_FRAGMENT_SHADER,
            )

            self._line_vao = QOpenGLVertexArrayObject()
            if not self._line_vao.create():
                raise RuntimeError("Could not create OpenGL line VAO.")

            self._line_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            if not self._line_buffer.create():
                raise RuntimeError("Could not create OpenGL line vertex buffer.")
            self._line_buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.DynamicDraw)

            self._line_vao.bind()
            self._line_buffer.bind()
            self._line_program.bind()
            self._line_program.enableAttributeArray(0)
            self._line_program.setAttributeBuffer(0, GL_FLOAT, 0, 3, 12)
            self._line_program.release()
            self._line_buffer.release()
            self._line_vao.release()

            self._toolpath_cut_gpu = self._create_gpu_line_geometry()
            self._toolpath_rapid_gpu = self._create_gpu_line_geometry()
            self._toolpath_cut_lod_gpu = self._create_gpu_line_geometry()
            self._toolpath_rapid_lod_gpu = self._create_gpu_line_geometry()

            fmt = context.format()
            profile = fmt.profile().name.replace("Profile", "")
            self._renderer_description = (
                f"Native OpenGL {fmt.majorVersion()}.{fmt.minorVersion()} {profile}"
            ).strip()
            self._gl_error = None
            context.aboutToBeDestroyed.connect(self._cleanup_gl)
        except RuntimeError as exc:
            self._gl_error = str(exc)

        self.rendererStatusChanged.emit(
            self._gl_error or self._renderer_description
        )

    def _cleanup_gl(self) -> None:
        if self.context() is None:
            return

        self.makeCurrent()
        for entry in self._mesh_cache.values():
            entry.destroy()
        self._mesh_cache.clear()

        for geometry in (
            self._toolpath_cut_gpu,
            self._toolpath_rapid_gpu,
            self._toolpath_cut_lod_gpu,
            self._toolpath_rapid_lod_gpu,
        ):
            if geometry is not None:
                geometry.destroy()
        self._toolpath_cut_gpu = None
        self._toolpath_rapid_gpu = None
        self._toolpath_cut_lod_gpu = None
        self._toolpath_rapid_lod_gpu = None
        self._toolpath_gpu_key = None

        if self._line_buffer is not None and self._line_buffer.isCreated():
            self._line_buffer.destroy()
        if self._line_vao is not None and self._line_vao.isCreated():
            self._line_vao.destroy()

        self._mesh_program = None
        self._line_program = None
        self._stock_program = None
        self._line_buffer = None
        self._line_vao = None
        self._functions = None
        self.doneCurrent()

    def resizeGL(self, width: int, height: int) -> None:
        if self._functions is not None:
            self._functions.glViewport(0, 0, max(width, 1), max(height, 1))
        self.viewChanged.emit()

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

    def _camera_basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        azimuth = radians(self.camera.yaw_deg)
        elevation = radians(self.camera.elevation_deg)
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
            right = np.array((1.0, 0.0, 0.0), dtype=float)
        right /= np.linalg.norm(right)

        up = np.cross(view, right)
        up /= np.linalg.norm(up)
        return right, up, view

    def _model_numpy(self, item: ProjectItem) -> np.ndarray:
        assert item.mesh is not None
        units_scale = float(item.source_units.millimeters_per_unit)
        source_bounds = np.asarray(item.mesh.bounds, dtype=float)
        pivot_mm = source_bounds.mean(axis=0) * units_scale

        unit_matrix = np.eye(4, dtype=float)
        unit_matrix[0, 0] = units_scale
        unit_matrix[1, 1] = units_scale
        unit_matrix[2, 2] = units_scale

        return item.transform.matrix(
            tuple(float(value) for value in pivot_mm)
        ) @ unit_matrix

    def _item_bounds_mm(self, item: ProjectItem) -> np.ndarray:
        assert item.mesh is not None
        source_bounds = np.asarray(item.mesh.bounds, dtype=float)
        corners = self._bounds_corners(source_bounds)
        homogeneous = np.column_stack((corners, np.ones(len(corners))))
        transformed = (self._model_numpy(item) @ homogeneous.T).T[:, :3]
        return np.vstack((transformed.min(axis=0), transformed.max(axis=0)))

    def _full_scene_bounds(self) -> np.ndarray:
        if self.project is None:
            return np.array(((0.0, 0.0, -1.0), (100.0, 100.0, 0.0)), dtype=float)

        stock = self.project.stock
        minimum = np.array((0.0, 0.0, -stock.thickness_mm), dtype=float)
        maximum = np.array((stock.width_mm, stock.height_mm, 0.0), dtype=float)

        for index, item in enumerate(self.project.items):
            if not self._item_viewport_visible(index, item):
                continue
            item_bounds = self._item_bounds_mm(item)
            minimum = np.minimum(minimum, item_bounds[0])
            maximum = np.maximum(maximum, item_bounds[1])

        toolpath_bounds = self._ensure_toolpath_render_cache().bounds
        if toolpath_bounds is not None:
            minimum = np.minimum(minimum, toolpath_bounds[0])
            maximum = np.maximum(maximum, toolpath_bounds[1])

        return np.vstack((minimum, maximum))

    def _framing_bounds(self) -> np.ndarray:
        """Return camera framing bounds independent of object selection.

        Selection must never implicitly reframe, zoom, or retarget the camera.
        The selected item only affects overlays such as its bounds and XYZ gizmo.
        Explicit Fit View remains the operation that resets the camera framing.
        """

        return self._full_scene_bounds()

    def _camera_geometry(
        self,
    ) -> tuple[QMatrix4x4, QMatrix4x4, float]:
        frame_bounds = self._framing_bounds()
        clip_bounds = self._full_scene_bounds()
        center = frame_bounds.mean(axis=0)
        _right, up, view = self._camera_basis()

        pan = np.asarray(self.camera.pan_world, dtype=float)
        target = center + pan

        diagonal = max(float(np.linalg.norm(frame_bounds[1] - frame_bounds[0])), 1e-6)
        radius = max(diagonal / 2.0, 1e-6) * self.FIT_MARGIN

        clip_corners = self._bounds_corners(clip_bounds)
        clip_depths = (clip_corners - target) @ view
        nearest_offset = float(np.max(clip_depths))
        farthest_offset = float(np.min(clip_depths))
        clip_diagonal = max(
            float(np.linalg.norm(clip_bounds[1] - clip_bounds[0])),
            1e-6,
        )
        clip_margin = max(clip_diagonal * 0.03, 0.1)

        width = max(self.width(), 1)
        height = max(self.height(), 1)
        aspect = max(width / height, 1e-9)
        zoom = max(self.camera.zoom, 1e-9)

        if self.camera.projection_mode == "perspective":
            # Keep the framing scale independent of camera angle.  The camera may
            # need to move farther away so the complete stock/scene remains inside
            # the near clipping plane, but that safety distance must not change
            # the apparent zoom.  Zoom is therefore expressed through the field
            # of view rather than by moving the camera toward the model.
            base_half_vertical = radians(self.PERSPECTIVE_FOV_DEG) / 2.0
            base_half_horizontal = atan(tan(base_half_vertical) * aspect)
            limiting_angle = max(
                min(base_half_vertical, base_half_horizontal),
                1e-6,
            )
            fit_distance = max(
                radius / sin(limiting_angle),
                radius + 1e-4,
            )
            distance = max(
                fit_distance,
                nearest_offset + clip_margin,
                1e-4,
            )

            desired_half_height = max(
                fit_distance * tan(base_half_vertical) / zoom,
                1e-9,
            )
            effective_half_vertical = atan(desired_half_height / distance)
            effective_fov_deg = max(
                degrees(effective_half_vertical * 2.0),
                1e-5,
            )
            world_per_pixel = (2.0 * desired_half_height) / height

            eye = target + view * distance
            view_matrix = QMatrix4x4()
            view_matrix.lookAt(
                QVector3D(*[float(value) for value in eye]),
                QVector3D(*[float(value) for value in target]),
                QVector3D(*[float(value) for value in up]),
            )

            nearest_depth = distance - nearest_offset
            farthest_depth = distance - farthest_offset
            near_plane = max(nearest_depth * 0.45, 1e-4)
            far_plane = max(farthest_depth + clip_margin, near_plane + 1.0)

            projection = QMatrix4x4()
            projection.perspective(
                effective_fov_deg,
                aspect,
                near_plane,
                far_plane,
            )
            return projection, view_matrix, world_per_pixel

        half_y = radius / zoom
        half_x = half_y * aspect
        if aspect < 1.0:
            half_x = radius / zoom
            half_y = half_x / aspect

        distance = max(
            diagonal * 2.0,
            nearest_offset + clip_margin,
            1.0,
        )
        eye = target + view * distance
        view_matrix = QMatrix4x4()
        view_matrix.lookAt(
            QVector3D(*[float(value) for value in eye]),
            QVector3D(*[float(value) for value in target]),
            QVector3D(*[float(value) for value in up]),
        )

        nearest_depth = distance - nearest_offset
        farthest_depth = distance - farthest_offset
        near_plane = max(nearest_depth * 0.45, 1e-4)
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
        return projection, view_matrix, (2.0 * half_y) / height

    def _upload_mesh(
        self,
        source_mesh: object,
        prepared: tuple[bytes, int] | None = None,
    ) -> _GpuMesh:
        if self._mesh_program is None:
            raise RuntimeError("OpenGL mesh shader is not initialized.")

        if prepared is None:
            triangle_vertices = expand_triangle_positions(source_mesh)
            if len(triangle_vertices) == 0:
                raise RuntimeError("Cannot render an empty mesh.")
            vertex_bytes = triangle_vertices.tobytes()
            vertex_count = len(triangle_vertices)
        else:
            vertex_bytes, vertex_count = prepared
            if vertex_count <= 0 or not vertex_bytes:
                raise RuntimeError("Prepared mesh upload is empty.")

        vao = QOpenGLVertexArrayObject()
        vertex_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        if not vao.create():
            raise RuntimeError("Could not create mesh VAO.")
        if not vertex_buffer.create():
            vao.destroy()
            raise RuntimeError("Could not create mesh vertex buffer.")

        vertex_buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.StaticDraw)
        vao.bind()
        vertex_buffer.bind()
        vertex_buffer.allocate(vertex_bytes, len(vertex_bytes))

        self._mesh_program.bind()
        self._mesh_program.enableAttributeArray(0)
        self._mesh_program.setAttributeBuffer(0, GL_FLOAT, 0, 3, 12)
        self._mesh_program.release()

        vertex_buffer.release()
        vao.release()
        return _GpuMesh(
            source_mesh=source_mesh,
            vao=vao,
            vertex_buffer=vertex_buffer,
            vertex_count=vertex_count,
        )

    def _gpu_mesh_for_item(self, item: ProjectItem) -> _GpuMesh | None:
        if item.mesh is None:
            return None

        source_mesh = item.mesh.mesh
        key = id(source_mesh)
        cached = self._mesh_cache.get(key)
        if cached is not None and cached.source_mesh is source_mesh:
            return cached

        if cached is not None:
            cached.destroy()

        prepared_entry = self._prepared_mesh_uploads.pop(key, None)
        prepared: tuple[bytes, int] | None = None
        if prepared_entry is not None and prepared_entry[0] is source_mesh:
            prepared = (prepared_entry[1], prepared_entry[2])

        try:
            cached = self._upload_mesh(source_mesh, prepared)
        except (RuntimeError, ValueError) as exc:
            self._gl_error = str(exc)
            self.rendererStatusChanged.emit(self._gl_error)
            return None

        self._mesh_cache[key] = cached
        return cached

    def _prune_mesh_cache(self) -> None:
        active_meshes: dict[int, object] = {}
        if self.project is not None:
            for item in self.project.items:
                if item.mesh is not None:
                    source_mesh = item.mesh.mesh
                    active_meshes[id(source_mesh)] = source_mesh

        stale_keys = [
            key
            for key, entry in self._mesh_cache.items()
            if active_meshes.get(key) is not entry.source_mesh
        ]
        for key in stale_keys:
            self._mesh_cache.pop(key).destroy()

        stale_prepared = [
            key
            for key, entry in self._prepared_mesh_uploads.items()
            if active_meshes.get(key) is not entry[0]
        ]
        for key in stale_prepared:
            self._prepared_mesh_uploads.pop(key, None)

    def _create_gpu_line_geometry(self) -> _GpuLineGeometry:
        if self._line_program is None:
            raise RuntimeError("OpenGL line shader is not available.")

        vao = QOpenGLVertexArrayObject()
        if not vao.create():
            raise RuntimeError("Could not create toolpath line VAO.")

        vertex_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        if not vertex_buffer.create():
            vao.destroy()
            raise RuntimeError("Could not create toolpath line vertex buffer.")
        vertex_buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.StaticDraw)

        vao.bind()
        vertex_buffer.bind()
        self._line_program.bind()
        self._line_program.enableAttributeArray(0)
        self._line_program.setAttributeBuffer(0, GL_FLOAT, 0, 3, 12)
        self._line_program.release()
        vertex_buffer.release()
        vao.release()
        return _GpuLineGeometry(vao, vertex_buffer)

    @staticmethod
    def _upload_gpu_line_geometry(
        geometry: _GpuLineGeometry,
        vertices: np.ndarray,
    ) -> None:
        line_vertices = np.ascontiguousarray(
            vertices,
            dtype=np.float32,
        ).reshape((-1, 3))
        geometry.vertex_count = len(line_vertices)
        if geometry.vertex_count == 0:
            return
        line_bytes = line_vertices.tobytes()
        geometry.vertex_buffer.bind()
        geometry.vertex_buffer.allocate(line_bytes, len(line_bytes))
        geometry.vertex_buffer.release()

    def _ensure_toolpath_gpu_cache(
        self,
        cache: _ToolpathRenderCache,
    ) -> bool:
        geometries = (
            self._toolpath_cut_gpu,
            self._toolpath_rapid_gpu,
            self._toolpath_cut_lod_gpu,
            self._toolpath_rapid_lod_gpu,
        )
        if any(geometry is None for geometry in geometries):
            return False
        if self._toolpath_gpu_key == cache.key:
            return True

        assert self._toolpath_cut_gpu is not None
        assert self._toolpath_rapid_gpu is not None
        assert self._toolpath_cut_lod_gpu is not None
        assert self._toolpath_rapid_lod_gpu is not None
        self._upload_gpu_line_geometry(
            self._toolpath_cut_gpu,
            cache.cut_vertices,
        )
        self._upload_gpu_line_geometry(
            self._toolpath_rapid_gpu,
            cache.rapid_vertices,
        )
        self._upload_gpu_line_geometry(
            self._toolpath_cut_lod_gpu,
            cache.cut_lod_vertices,
        )
        self._upload_gpu_line_geometry(
            self._toolpath_rapid_lod_gpu,
            cache.rapid_lod_vertices,
        )
        self._toolpath_gpu_key = cache.key
        return True

    def _draw_gpu_lines(
        self,
        geometry: _GpuLineGeometry | None,
        vertex_count: int,
        *,
        view_projection: QMatrix4x4,
        color: QVector4D,
        line_width: float = 1.0,
    ) -> None:
        if (
            self._functions is None
            or self._line_program is None
            or geometry is None
            or vertex_count <= 0
            or geometry.vertex_count <= 0
        ):
            return

        count = min(int(vertex_count), geometry.vertex_count)
        self._line_program.bind()
        self._line_program.setUniformValue("u_mvp", view_projection)
        self._line_program.setUniformValue("u_color", color)
        geometry.vao.bind()
        self._functions.glLineWidth(max(1.0, float(line_width)))
        try:
            self._functions.glDrawArrays(GL_LINES, 0, count)
        finally:
            self._functions.glLineWidth(1.0)
        geometry.vao.release()
        self._line_program.release()

    def _draw_lines(
        self,
        vertices: np.ndarray,
        *,
        view_projection: QMatrix4x4,
        color: QVector4D,
        line_width: float = 1.0,
    ) -> None:
        if (
            self._functions is None
            or self._line_program is None
            or self._line_buffer is None
            or self._line_vao is None
            or len(vertices) == 0
        ):
            return

        line_vertices = np.asarray(vertices, dtype=np.float32).reshape((-1, 3))
        line_bytes = line_vertices.tobytes()
        self._line_buffer.bind()
        self._line_buffer.allocate(line_bytes, len(line_bytes))
        self._line_buffer.release()

        self._line_program.bind()
        self._line_program.setUniformValue("u_mvp", view_projection)
        self._line_program.setUniformValue("u_color", color)
        self._line_vao.bind()
        self._functions.glLineWidth(max(1.0, float(line_width)))
        try:
            self._functions.glDrawArrays(GL_LINES, 0, len(line_vertices))
        finally:
            self._functions.glLineWidth(1.0)
        self._line_vao.release()
        self._line_program.release()

    @staticmethod
    def _nice_grid_step(target: float) -> float:
        target = max(float(target), 1e-9)
        exponent = floor(log10(target))
        scale = 10.0**exponent
        fraction = target / scale
        if fraction <= 1.0:
            nice = 1.0
        elif fraction <= 2.0:
            nice = 2.0
        elif fraction <= 5.0:
            nice = 5.0
        else:
            nice = 10.0
        return nice * scale

    def _grid_step(self, world_per_pixel: float, width_mm: float, height_mm: float) -> float:
        """Return the exact adaptive spacing shared by grid lines and rulers."""

        step = self._nice_grid_step(max(world_per_pixel * 55.0, 1e-6))
        stock_floor = self._nice_grid_step(max(width_mm, height_mm) / 200.0)
        return max(step, stock_floor)

    def _project_world_point(
        self,
        point: tuple[float, float, float],
        view_projection: QMatrix4x4,
    ) -> QPointF | None:
        # QMatrix4x4.map(QVector3D) applies the full point transform,
        # including perspective division.  Use the explicit API rather than
        # PySide's overloaded QMatrix4x4 * QVector4D operator: that operator
        # currently raises a SyntaxError under Python 3.14 / PySide 6.11.
        mapped = view_projection.map(
            QVector3D(
                float(point[0]),
                float(point[1]),
                float(point[2]),
            )
        )
        ndc_x = float(mapped.x())
        ndc_y = float(mapped.y())
        if not np.isfinite(ndc_x) or not np.isfinite(ndc_y):
            return None
        return QPointF(
            (ndc_x + 1.0) * 0.5 * max(self.width(), 1),
            (1.0 - ndc_y) * 0.5 * max(self.height(), 1),
        )

    @staticmethod
    def _segment_intersects_viewport(
        first: QPointF,
        second: QPointF,
        width: float,
        height: float,
    ) -> bool:
        """Liang-Barsky clip test for a projected finite stock grid line."""

        x0, y0 = first.x(), first.y()
        dx = second.x() - x0
        dy = second.y() - y0
        t_min, t_max = 0.0, 1.0
        for p, q in (
            (-dx, x0),
            (dx, width - x0),
            (-dy, y0),
            (dy, height - y0),
        ):
            if abs(p) < 1e-12:
                if q < 0.0:
                    return False
                continue
            ratio = q / p
            if p < 0.0:
                t_min = max(t_min, ratio)
            else:
                t_max = min(t_max, ratio)
            if t_min > t_max:
                return False
        return True

    @staticmethod
    def _line_edge_intersections(
        first: QPointF,
        second: QPointF,
        width: float,
        height: float,
    ) -> dict[str, float]:
        """Intersect the infinite projected grid line with viewport edges."""

        x0, y0 = first.x(), first.y()
        dx = second.x() - x0
        dy = second.y() - y0
        intersections: dict[str, float] = {}
        epsilon = 1e-9

        if abs(dx) > epsilon:
            for side, x_edge in (("left", 0.0), ("right", width)):
                t = (x_edge - x0) / dx
                y = y0 + t * dy
                if -0.5 <= y <= height + 0.5:
                    intersections[side] = max(0.0, min(height, y))

        if abs(dy) > epsilon:
            for side, y_edge in (("top", 0.0), ("bottom", height)):
                t = (y_edge - y0) / dy
                x = x0 + t * dx
                if -0.5 <= x <= width + 0.5:
                    intersections[side] = max(0.0, min(width, x))

        return intersections

    @staticmethod
    def _format_ruler_coordinate(value: float, step: float) -> str:
        if step >= 10.0:
            return f"{value:.0f}"
        if step >= 1.0:
            decimals = 1
        elif step >= 0.1:
            decimals = 2
        else:
            decimals = 3
        return f"{value:.{decimals}f}".rstrip("0").rstrip(".")

    def ruler_ticks(self) -> dict[str, list[tuple[float, str]]]:
        """Return screen-edge ticks tied to visible stock-plane grid lines.

        Stock coordinates are always expressed in millimeters with the lower-left
        stock corner defined as X=0, Y=0.  Each visible projected grid line gets
        one edge label so the coordinates remain readable when the stock edges
        themselves are outside the zoomed viewport.
        """

        ticks: dict[str, list[tuple[float, str]]] = {
            "top": [],
            "bottom": [],
            "left": [],
            "right": [],
        }
        if self.project is None:
            return ticks

        projection, view_matrix, world_per_pixel = self._camera_geometry()
        view_projection = projection * view_matrix
        viewport_width = float(max(self.width(), 1))
        viewport_height = float(max(self.height(), 1))
        stock_width = float(self.project.stock.width_mm)
        stock_height = float(self.project.stock.height_mm)
        step = self._grid_step(world_per_pixel, stock_width, stock_height)

        def values(limit: float) -> list[float]:
            count = max(0, floor(limit / step + 1e-9))
            result = [index * step for index in range(count + 1)]
            if not result or abs(result[-1] - limit) > max(step * 1e-6, 1e-7):
                result.append(limit)
            return result

        def point_is_visible(point: QPointF) -> bool:
            return (
                -0.5 <= point.x() <= viewport_width + 0.5
                and -0.5 <= point.y() <= viewport_height + 0.5
            )

        def add_line(
            axis: str,
            value: float,
            start: tuple[float, float, float],
            end: tuple[float, float, float],
            axis_side: str,
            priority: tuple[str, ...],
        ) -> None:
            first = self._project_world_point(start, view_projection)
            second = self._project_world_point(end, view_projection)
            if first is None or second is None:
                return

            label = f"{axis} {self._format_ruler_coordinate(value, step)}"

            # When the stock's coordinate axis is visible, anchor the ruler
            # directly to it.  X values come from Y=0 and Y values come from
            # X=0, so the projected stock origin is always labeled 0,0.
            if point_is_visible(first):
                position = (
                    first.x()
                    if axis_side in {"top", "bottom"}
                    else first.y()
                )
                ticks[axis_side].append((position, label))
                return

            # Once the coordinate axis moves off-screen during a zoom or pan,
            # keep the scale useful by attaching each visible grid line to the
            # viewport edge that it actually crosses.
            if not self._segment_intersects_viewport(
                first,
                second,
                viewport_width,
                viewport_height,
            ):
                return
            intersections = self._line_edge_intersections(
                first,
                second,
                viewport_width,
                viewport_height,
            )
            if not intersections:
                return
            for side in priority:
                if side in intersections:
                    ticks[side].append((intersections[side], label))
                    return

        z = 0.002
        for x in values(stock_width):
            add_line(
                "X",
                x,
                (x, 0.0, z),
                (x, stock_height, z),
                "bottom",
                ("bottom", "top", "right", "left"),
            )

        for y in values(stock_height):
            add_line(
                "Y",
                y,
                (0.0, y, z),
                (stock_width, y, z),
                "left",
                ("left", "right", "bottom", "top"),
            )

        return ticks

    def _stock_geometry(
        self,
        world_per_pixel: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        empty = np.empty((0, 3), dtype=np.float32)
        if self.project is None:
            return empty, empty, empty, empty

        stock = self.project.stock
        w = float(stock.width_mm)
        h = float(stock.height_mm)
        t = float(stock.thickness_mm)
        corners = np.array(
            (
                (0.0, 0.0, 0.0),
                (w, 0.0, 0.0),
                (w, h, 0.0),
                (0.0, h, 0.0),
                (0.0, 0.0, -t),
                (w, 0.0, -t),
                (w, h, -t),
                (0.0, h, -t),
            ),
            dtype=np.float32,
        )

        surfaces = empty
        edges = empty
        if self.show_stock:
            triangles = (
                (0, 1, 2), (0, 2, 3),
                (4, 6, 5), (4, 7, 6),
                (0, 4, 5), (0, 5, 1),
                (1, 5, 6), (1, 6, 2),
                (2, 6, 7), (2, 7, 3),
                (3, 7, 4), (3, 4, 0),
            )
            surfaces = np.asarray(
                [corners[index] for tri in triangles for index in tri],
                dtype=np.float32,
            )
            perimeter = ((0, 1), (1, 2), (2, 3), (3, 0))
            edges = np.asarray(
                [corners[index] for pair in perimeter for index in pair],
                dtype=np.float32,
            )

        if not self.show_grid:
            return surfaces, edges, empty, empty

        step = self._grid_step(world_per_pixel, w, h)

        minor: list[tuple[float, float, float]] = []
        major: list[tuple[float, float, float]] = []
        for index in range(1, min(int(w / step) + 1, 220)):
            x = index * step
            if x >= w:
                break
            target = major if index % 5 == 0 else minor
            target.extend(((x, 0.0, 0.002), (x, h, 0.002)))

        for index in range(1, min(int(h / step) + 1, 220)):
            y = index * step
            if y >= h:
                break
            target = major if index % 5 == 0 else minor
            target.extend(((0.0, y, 0.002), (w, y, 0.002)))

        minor_grid = np.asarray(minor, dtype=np.float32).reshape((-1, 3))
        major_grid = np.asarray(major, dtype=np.float32).reshape((-1, 3))
        return surfaces, edges, minor_grid, major_grid

    def _draw_stock_surface(
        self,
        vertices: np.ndarray,
        *,
        view_projection: QMatrix4x4,
    ) -> None:
        if (
            self._functions is None
            or self._stock_program is None
            or self._line_buffer is None
            or self._line_vao is None
            or len(vertices) == 0
        ):
            return

        stock_vertices = np.asarray(vertices, dtype=np.float32).reshape((-1, 3))
        stock_bytes = stock_vertices.tobytes()
        self._line_buffer.bind()
        self._line_buffer.allocate(stock_bytes, len(stock_bytes))
        self._line_buffer.release()

        self._stock_program.bind()
        self._stock_program.setUniformValue("u_mvp", view_projection)
        self._stock_program.setUniformValue(
            "u_base_color",
            QVector4D(0.72, 0.74, 0.78, 0.23),
        )

        self._functions.glEnable(GL_CULL_FACE)
        self._functions.glCullFace(GL_BACK)
        self._functions.glDepthMask(False)
        self._line_vao.bind()
        self._functions.glDrawArrays(GL_TRIANGLES, 0, len(stock_vertices))
        self._line_vao.release()
        self._functions.glDepthMask(True)
        self._functions.glDisable(GL_CULL_FACE)
        self._stock_program.release()

    def _draw_stock(
        self,
        view_projection: QMatrix4x4,
        world_per_pixel: float,
    ) -> None:
        surfaces, edges, minor_grid, major_grid = self._stock_geometry(
            world_per_pixel
        )
        self._draw_stock_surface(surfaces, view_projection=view_projection)
        self._draw_lines(
            minor_grid,
            view_projection=view_projection,
            color=QVector4D(0.40, 0.44, 0.52, 0.48),
        )
        self._draw_lines(
            major_grid,
            view_projection=view_projection,
            color=QVector4D(0.58, 0.62, 0.70, 0.78),
        )
        self._draw_lines(
            edges,
            view_projection=view_projection,
            color=QVector4D(0.62, 0.66, 0.74, 0.88),
        )

    def _draw_meshes(self, view_projection: QMatrix4x4) -> None:
        if (
            self.project is None
            or self._functions is None
            or self._mesh_program is None
        ):
            return

        # Resolve/upload meshes before binding the draw shader.  _upload_mesh()
        # briefly binds and releases this same program while configuring a new
        # VAO.  Doing that in the middle of a draw pass used to leave the shader
        # unbound for the first frame after import, so the selection bounds were
        # visible but the newly imported mesh was not.  Once cached, a later
        # viewport interaction skipped the upload path and the model appeared.
        render_items: list[tuple[int, ProjectItem, _GpuMesh]] = []
        for item_index, item in enumerate(self.project.items):
            if not self._item_viewport_visible(item_index, item):
                continue
            gpu_mesh = self._gpu_mesh_for_item(item)
            if gpu_mesh is not None:
                render_items.append((item_index, item, gpu_mesh))

        if not render_items:
            return

        self._mesh_program.bind()
        try:
            self._mesh_program.setUniformValue(
                "u_view_projection",
                view_projection,
            )
            self._mesh_program.setUniformValue(
                "u_light_direction",
                QVector3D(0.35, -0.45, 0.82),
            )

            for item_index, item, gpu_mesh in render_items:
                self._mesh_program.setUniformValue(
                    "u_model",
                    self._qmatrix_from_numpy(self._model_numpy(item)),
                )
                color = (
                    QVector4D(0.784, 1.0, 0.239, 1.0)
                    if item_index in self.selected_item_indices
                    else QVector4D(0.357, 0.557, 0.839, 1.0)
                )
                self._mesh_program.setUniformValue("u_color", color)

                gpu_mesh.vao.bind()
                self._functions.glDrawArrays(
                    GL_TRIANGLES,
                    0,
                    gpu_mesh.vertex_count,
                )
                gpu_mesh.vao.release()
        finally:
            self._mesh_program.release()

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
        elif self._shape_draw_mode == "line":
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

        if mode in {"rectangle", "text"}:
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

        if mode == "line":
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
        if not self._item_viewport_visible(self.selected_item_index, item):
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

        if self.selected_item_index is None:
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
        if not self._item_viewport_visible(self.selected_item_index, item):
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
        if item.mesh is None or not item.visible:
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

    def _toolpath_visible_vertex_counts(
        self,
        cache: _ToolpathRenderCache,
    ) -> tuple[int, int]:
        if cache.segment_count <= 0 or self.simulation_fraction <= 0.0:
            return 0, 0

        visible_segments = round(
            cache.segment_count * self.simulation_fraction
        )
        visible_segments = max(
            1,
            min(cache.segment_count, visible_segments),
        )
        rapid_segments = int(cache.rapid_prefix[visible_segments])
        cut_segments = visible_segments - rapid_segments
        return cut_segments * 2, rapid_segments * 2

    def _toolpath_line_geometry(
        self,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return cached exact line vertices for the visible simulation prefix."""

        cache = self._ensure_toolpath_render_cache()
        cut_count, rapid_count = self._toolpath_visible_vertex_counts(cache)
        return (
            cache.cut_vertices[:cut_count],
            cache.rapid_vertices[:rapid_count],
        )

    def _toolpath_point_geometry(
        self,
        world_per_pixel: float,
    ) -> np.ndarray:
        if (
            self.project is None
            or not self.show_toolpath_points
            or not self.project.toolpaths
        ):
            return np.empty((0, 3), dtype=np.float32)

        points = self._ensure_toolpath_render_cache().points
        if not len(points):
            return np.empty((0, 3), dtype=np.float32)

        # Keep the overlay responsive on very dense 3D finishing paths.
        stride = max(1, len(points) // 1800)
        size = max(float(world_per_pixel) * 2.5, 0.03)
        vertices: list[tuple[float, float, float]] = []
        for x, y, z in points[::stride]:
            vertices.extend(
                (
                    (x - size, y, z),
                    (x + size, y, z),
                    (x, y - size, z),
                    (x, y + size, z),
                )
            )
        return np.asarray(vertices, dtype=np.float32).reshape((-1, 3))

    def _toolpath_marker_geometry(
        self,
        world_per_pixel: float,
    ) -> np.ndarray:
        if self.toolpath_marker_xyz is None:
            return np.empty((0, 3), dtype=np.float32)
        x, y, z = self.toolpath_marker_xyz
        size = max(float(world_per_pixel) * 8.0, 0.25)
        return np.asarray(
            (
                (x - size, y, z),
                (x + size, y, z),
                (x, y - size, z),
                (x, y + size, z),
                (x, y, z - size),
                (x, y, z + size),
            ),
            dtype=np.float32,
        )

    def _draw_toolpath_preview(
        self,
        view_projection: QMatrix4x4,
        world_per_pixel: float,
    ) -> None:
        if (
            self._functions is None
            or not self.show_toolpaths
            or self.project is None
            or not self.project.toolpaths
        ):
            return

        cache = self._ensure_toolpath_render_cache()
        if not self._ensure_toolpath_gpu_cache(cache):
            return

        cut_count, rapid_count = self._toolpath_visible_vertex_counts(cache)
        use_lod = (
            cache.lod_stride > 1
            and (
                self._interaction_mode in {"orbit", "pan"}
                or self._toolpath_interaction_lod_frames > 0
            )
        )
        if use_lod:
            full_cut_segments = max(len(cache.cut_vertices) // 2, 1)
            full_rapid_segments = max(len(cache.rapid_vertices) // 2, 1)
            cut_fraction = (cut_count // 2) / full_cut_segments
            rapid_fraction = (rapid_count // 2) / full_rapid_segments
            cut_count = round(
                len(cache.cut_lod_vertices) * cut_fraction / 2.0
            ) * 2
            rapid_count = round(
                len(cache.rapid_lod_vertices) * rapid_fraction / 2.0
            ) * 2
            cut_geometry = self._toolpath_cut_lod_gpu
            rapid_geometry = self._toolpath_rapid_lod_gpu
        else:
            cut_geometry = self._toolpath_cut_gpu
            rapid_geometry = self._toolpath_rapid_gpu

        self._functions.glDisable(GL_DEPTH_TEST)
        try:
            self._draw_gpu_lines(
                cut_geometry,
                cut_count,
                view_projection=view_projection,
                color=QVector4D(0.78, 1.0, 0.24, 0.98),
                line_width=2.5,
            )
            if self.show_rapids:
                self._draw_gpu_lines(
                    rapid_geometry,
                    rapid_count,
                    view_projection=view_projection,
                    color=QVector4D(1.0, 0.62, 0.20, 0.90),
                    line_width=1.5,
                )
            if self.show_toolpath_points:
                self._draw_lines(
                    self._toolpath_point_geometry(world_per_pixel),
                    view_projection=view_projection,
                    color=QVector4D(0.70, 0.82, 1.0, 0.72),
                    line_width=1.0,
                )
            self._draw_lines(
                self._toolpath_marker_geometry(world_per_pixel),
                view_projection=view_projection,
                color=QVector4D(1.0, 0.86, 0.20, 1.0),
                line_width=3.5,
            )
        finally:
            self._functions.glEnable(GL_DEPTH_TEST)

    def paintGL(self) -> None:
        if self._functions is None:
            return

        self._functions.glDepthMask(True)
        self._functions.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._prune_mesh_cache()

        if self._gl_error is not None:
            return

        projection, view_matrix, world_per_pixel = self._camera_geometry()
        view_projection = projection * view_matrix
        self._draw_stock(view_projection, world_per_pixel)
        self._draw_meshes(view_projection)
        self._draw_lines(
            self._selected_bounds_geometry(),
            view_projection=view_projection,
            color=QVector4D(0.784, 1.0, 0.239, 0.95),
        )
        self._draw_toolpath_preview(view_projection, world_per_pixel)
        self._draw_shape_preview(view_projection)
        self._draw_selection_marquee()
        self._draw_resize_handles(
            view_projection,
            world_per_pixel,
        )
        self._draw_translation_gizmo(
            view_projection,
            world_per_pixel,
        )

        if self._toolpath_interaction_lod_frames > 0:
            self._toolpath_interaction_lod_frames -= 1

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
            and self._camera_control_mode
        ):
            self._interaction_mode = "orbit"
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._camera_control_mode
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
        if self._interaction_mode in {"orbit", "pan"}:
            self._toolpath_interaction_lod_frames = 1

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

    def _restore_toolpath_full_detail(self) -> None:
        self._toolpath_interaction_lod_frames = 0
        self.requestUpdate()

    def wheelEvent(self, event: QWheelEvent) -> None:
        self._toolpath_interaction_lod_frames = 1
        QTimer.singleShot(60, self._restore_toolpath_full_detail)
        angle_steps = event.angleDelta().y() / 120.0
        steps = angle_steps if angle_steps else event.pixelDelta().y() / 120.0
        if steps:
            self.zoom = self.camera.zoom * (1.20**steps)
            self.requestUpdate()
            self.viewChanged.emit()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.fitRequested.emit()
        event.accept()


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
    freehandStrokeRequested = Signal(object)
    shapeDrawModeChanged = Signal(str)

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
        self._renderer.freehandStrokeRequested.connect(
            self.freehandStrokeRequested.emit
        )
        self._renderer.shapeDrawModeChanged.connect(
            self.shapeDrawModeChanged.emit
        )

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

    def set_pen_sample_spacing(self, spacing_mm: float) -> None:
        self._renderer.set_pen_sample_spacing(spacing_mm)

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
