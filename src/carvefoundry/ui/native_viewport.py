from __future__ import annotations

from dataclasses import dataclass
from math import atan, cos, degrees, floor, log10, radians, sin, tan
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor,
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
class _CameraState:
    yaw_deg: float = 45.0
    elevation_deg: float = 35.0
    zoom: float = 1.0
    pan_world: tuple[float, float, float] = (0.0, 0.0, 0.0)
    projection_mode: str = "orthographic"


class _NativeOpenGLViewport(QOpenGLWindow):
    """Native OpenGL surface with one authoritative CAD camera state."""

    rendererStatusChanged = Signal(str)
    orbitStarted = Signal()
    fitRequested = Signal()
    viewChanged = Signal()

    MIN_ZOOM = 0.01
    MAX_ZOOM = 100_000.0
    PERSPECTIVE_FOV_DEG = 45.0
    FIT_MARGIN = 1.10
    ISOMETRIC_ELEVATION_DEG = 35.26438968

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self.setFormat(QSurfaceFormat.defaultFormat())

        self.project = project
        self.selected_item_index: int | None = None
        self.camera = _CameraState()
        self.show_stock = True
        self.show_grid = True
        self.reverse_horizontal_drag = True

        self._last_mouse_pos: QPointF | None = None
        self._functions = None
        self._mesh_program: QOpenGLShaderProgram | None = None
        self._line_program: QOpenGLShaderProgram | None = None
        self._stock_program: QOpenGLShaderProgram | None = None
        self._line_vao: QOpenGLVertexArrayObject | None = None
        self._line_buffer: QOpenGLBuffer | None = None
        self._mesh_cache: dict[int, _GpuMesh] = {}
        self._prepared_mesh_uploads: dict[int, tuple[object, bytes, int]] = {}
        self._renderer_description = "Native OpenGL initializing…"
        self._gl_error: str | None = None

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

    def set_project(self, project: Project) -> None:
        self.project = project
        self.selected_item_index = None
        self._prepared_mesh_uploads.clear()
        self.fit_view()

    def set_selected_item(self, index: int | None) -> None:
        self.selected_item_index = index
        self.requestUpdate()
        self.viewChanged.emit()

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

    def fit_view(self) -> None:
        self.camera.zoom = 1.0
        self.camera.pan_world = (0.0, 0.0, 0.0)
        self.requestUpdate()
        self.viewChanged.emit()

    def toggle_stock(self) -> None:
        self.show_stock = not self.show_stock
        self.requestUpdate()

    def toggle_grid(self) -> None:
        self.show_grid = not self.show_grid
        self.requestUpdate()
        self.viewChanged.emit()

    def set_reverse_horizontal_drag(self, enabled: bool) -> None:
        self.reverse_horizontal_drag = bool(enabled)

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

        for item in self.project.items:
            if not item.visible or item.mesh is None:
                continue
            item_bounds = self._item_bounds_mm(item)
            minimum = np.minimum(minimum, item_bounds[0])
            maximum = np.maximum(maximum, item_bounds[1])

        return np.vstack((minimum, maximum))

    def _framing_bounds(self) -> np.ndarray:
        if self.project is not None and self.selected_item_index is not None:
            index = self.selected_item_index
            if 0 <= index < len(self.project.items):
                item = self.project.items[index]
                if item.visible and item.mesh is not None:
                    return self._item_bounds_mm(item)
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

    def _draw_lines(
        self,
        vertices: np.ndarray,
        *,
        view_projection: QMatrix4x4,
        color: QVector4D,
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
        self._functions.glDrawArrays(GL_LINES, 0, len(line_vertices))
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
            decimals = 0
        elif step >= 1.0:
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

        def add_line(
            axis: str,
            value: float,
            start: tuple[float, float, float],
            end: tuple[float, float, float],
            priority: tuple[str, ...],
        ) -> None:
            first = self._project_world_point(start, view_projection)
            second = self._project_world_point(end, view_projection)
            if first is None or second is None:
                return
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
            label = (
                f"{axis} "
                f"{self._format_ruler_coordinate(value, step)}"
            )
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
                ("bottom", "top", "right", "left"),
            )

        for y in values(stock_height):
            add_line(
                "Y",
                y,
                (0.0, y, z),
                (stock_width, y, z),
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

        self._mesh_program.bind()
        self._mesh_program.setUniformValue("u_view_projection", view_projection)
        self._mesh_program.setUniformValue(
            "u_light_direction",
            QVector3D(0.35, -0.45, 0.82),
        )

        for item_index, item in enumerate(self.project.items):
            if not item.visible or item.mesh is None:
                continue

            gpu_mesh = self._gpu_mesh_for_item(item)
            if gpu_mesh is None:
                continue

            self._mesh_program.setUniformValue(
                "u_model",
                self._qmatrix_from_numpy(self._model_numpy(item)),
            )
            color = (
                QVector4D(0.784, 1.0, 0.239, 1.0)
                if item_index == self.selected_item_index
                else QVector4D(0.357, 0.557, 0.839, 1.0)
            )
            self._mesh_program.setUniformValue("u_color", color)

            gpu_mesh.vao.bind()
            self._functions.glDrawArrays(GL_TRIANGLES, 0, gpu_mesh.vertex_count)
            gpu_mesh.vao.release()

        self._mesh_program.release()

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

    def _pan_pixels(self, delta: QPointF) -> None:
        _projection, _view, world_per_pixel = self._camera_geometry()
        right, up, _forward = self._camera_basis()

        horizontal = -delta.x() if self.reverse_horizontal_drag else delta.x()
        world_delta = (
            -right * horizontal * world_per_pixel
            + up * delta.y() * world_per_pixel
        )
        pan = np.asarray(self.camera.pan_world, dtype=float) + world_delta
        self.camera.pan_world = tuple(float(value) for value in pan)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._last_mouse_pos = event.position()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_mouse_pos is None:
            self._last_mouse_pos = event.position()
            return

        delta = event.position() - self._last_mouse_pos
        self._last_mouse_pos = event.position()

        if event.buttons() & Qt.MouseButton.LeftButton:
            horizontal = -delta.x() if self.reverse_horizontal_drag else delta.x()
            self.camera.yaw_deg += horizontal * 0.45
            self.camera.elevation_deg = max(
                -85.0,
                min(85.0, self.camera.elevation_deg + delta.y() * 0.35),
            )
            self.orbitStarted.emit()
            self.requestUpdate()
            self.viewChanged.emit()
        elif event.buttons() & (
            Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton
        ):
            self._pan_pixels(delta)
            self.requestUpdate()
            self.viewChanged.emit()

        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._last_mouse_pos = None
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
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
        self._ticks = sorted(ticks, key=lambda item: item[0])
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
        last_end = -10_000.0
        for position, label in self._ticks:
            if horizontal:
                text_width = metrics.horizontalAdvance(label)
                start = max(2.0, min(self.width() - text_width - 2.0, position - text_width / 2.0))
                if start < last_end + 7.0:
                    continue
                if self.side == "top":
                    painter.drawLine(int(position), self.height() - 1, int(position), self.height() - 6)
                    text_y = 2
                else:
                    painter.drawLine(int(position), 0, int(position), 5)
                    text_y = 8
                painter.drawText(int(start), text_y + metrics.ascent(), label)
                last_end = start + text_width
            else:
                text_height = metrics.height()
                start_y = max(1.0, min(self.height() - text_height - 1.0, position - text_height / 2.0))
                if start_y < last_end + 5.0:
                    continue
                if self.side == "left":
                    painter.drawLine(self.width() - 1, int(position), self.width() - 6, int(position))
                    rect_x = 2
                    align = Qt.AlignmentFlag.AlignRight
                else:
                    painter.drawLine(0, int(position), 5, int(position))
                    rect_x = 6
                    align = Qt.AlignmentFlag.AlignLeft
                painter.drawText(
                    rect_x,
                    int(start_y),
                    self.width() - rect_x - 3,
                    text_height,
                    int(align | Qt.AlignmentFlag.AlignVCenter),
                    label,
                )
                last_end = start_y + text_height


class MeshViewport(QWidget):
    """Widget wrapper around a native QOpenGLWindow CAD viewport."""

    viewSettingsChanged = Signal()

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
        self._projection_combo.currentTextChanged.connect(self._projection_changed)

        self._view_combo = QComboBox()
        self._view_combo.addItems(
            ("Free", "Isometric", "Top", "Bottom", "Front", "Back", "Left", "Right")
        )
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
    def reverse_horizontal_drag(self) -> bool:
        return self._renderer.reverse_horizontal_drag

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

    def set_project(self, project: Project) -> None:
        self._renderer.set_project(project)
        self._update_empty_status()

    def set_selected_item(self, index: int | None) -> None:
        self._renderer.set_selected_item(index)
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

    def set_reverse_horizontal_drag(self, enabled: bool) -> None:
        self._renderer.set_reverse_horizontal_drag(enabled)

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

    def set_standard_view(self, name: str) -> None:
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

        self._renderer.projection_mode = "orthographic"
        self._renderer.yaw_deg, self._renderer.elevation_deg = orientations[name]
        self._set_projection_combo("Orthographic")
        self._set_view_combo(name)
        self.fit_view()
        self.viewSettingsChanged.emit()

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
