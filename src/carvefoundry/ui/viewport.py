from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QMatrix4x4,
    QMouseEvent,
    QVector3D,
    QVector4D,
    QWheelEvent,
)
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QLabel

if TYPE_CHECKING:
    import trimesh

    from carvefoundry.core.project import Project, ProjectItem


GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_DEPTH_TEST = 0x0B71
GL_LEQUAL = 0x0203
GL_FLOAT = 0x1406
GL_UNSIGNED_INT = 0x1405
GL_TRIANGLES = 0x0004
GL_LINES = 0x0001

_MESH_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;

uniform mat4 u_mvp;
uniform mat3 u_normal_matrix;

out vec3 v_normal;

void main()
{
    gl_Position = u_mvp * vec4(a_position, 1.0);
    v_normal = normalize(u_normal_matrix * a_normal);
}
"""

_MESH_FRAGMENT_SHADER = """
#version 330 core
in vec3 v_normal;

uniform vec4 u_color;
uniform vec3 u_light_direction;

out vec4 frag_color;

void main()
{
    vec3 normal = normalize(v_normal);
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


@dataclass(slots=True)
class _GpuMesh:
    source_mesh: object
    vao: QOpenGLVertexArrayObject
    vertex_buffer: QOpenGLBuffer
    index_buffer: QOpenGLBuffer
    index_count: int

    def destroy(self) -> None:
        if self.index_buffer.isCreated():
            self.index_buffer.destroy()
        if self.vertex_buffer.isCreated():
            self.vertex_buffer.destroy()
        if self.vao.isCreated():
            self.vao.destroy()


class MeshViewport(QOpenGLWidget):
    """GPU-backed interactive 3D viewport for stock and imported meshes."""

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
        self._functions = None
        self._mesh_program: QOpenGLShaderProgram | None = None
        self._line_program: QOpenGLShaderProgram | None = None
        self._line_vao: QOpenGLVertexArrayObject | None = None
        self._line_buffer: QOpenGLBuffer | None = None
        self._mesh_cache: dict[int, _GpuMesh] = {}
        self._renderer_description = "GPU OpenGL initializing…"
        self._gl_error: str | None = None

        self.setObjectName("MeshViewport")
        self.setMinimumSize(360, 260)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)

        self._overlay_label = QLabel(self)
        self._overlay_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._overlay_label.setStyleSheet(
            "background: transparent; color: #9aa4b8; padding: 3px 5px;"
        )

        self._empty_label = QLabel(self)
        self._empty_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            "background: transparent; color: #edf1f7; font-size: 15px;"
        )
        self._update_overlay()

    def set_project(self, project: Project) -> None:
        self.project = project
        self.selected_item_index = None
        self.fit_view()
        self._update_overlay()

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

    @staticmethod
    def _qmatrix_from_numpy(matrix: np.ndarray) -> QMatrix4x4:
        values = [float(value) for value in np.asarray(matrix, dtype=float).reshape(16)]
        return QMatrix4x4(*values)

    @staticmethod
    def _compile_program(vertex_source: str, fragment_source: str) -> QOpenGLShaderProgram:
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

    def initializeGL(self) -> None:
        context = self.context()
        if context is None:
            self._gl_error = "OpenGL context creation failed."
            self._update_overlay()
            return

        try:
            self._functions = context.functions()
            self._functions.glEnable(GL_DEPTH_TEST)
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
            self._line_vao.release()
            self._line_buffer.release()

            fmt = context.format()
            profile = (
                "Core"
                if fmt.profile().name == "CoreProfile"
                else fmt.profile().name.replace("Profile", "")
            )
            self._renderer_description = (
                f"GPU OpenGL {fmt.majorVersion()}.{fmt.minorVersion()} {profile}"
            ).strip()
            self._gl_error = None
            context.aboutToBeDestroyed.connect(self._cleanup_gl)
        except RuntimeError as exc:
            self._gl_error = str(exc)

        self._update_overlay()

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
        self._line_buffer = None
        self._line_vao = None
        self._functions = None
        self.doneCurrent()

    def resizeGL(self, width: int, height: int) -> None:
        if self._functions is not None:
            self._functions.glViewport(0, 0, max(width, 1), max(height, 1))
        self._empty_label.setGeometry(0, 0, max(width, 1), max(height, 1))
        self._overlay_label.adjustSize()
        self._overlay_label.move(9, 7)
        self._overlay_label.raise_()
        self._empty_label.raise_()

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

    def _model_numpy(self, item: ProjectItem) -> np.ndarray:
        assert item.mesh is not None
        source_mesh = item.mesh.mesh
        units_scale = float(item.source_units.millimeters_per_unit)
        source_bounds = np.asarray(source_mesh.bounds, dtype=float)
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
        source_bounds = np.asarray(item.mesh.mesh.bounds, dtype=float)
        corners = self._bounds_corners(source_bounds)
        homogeneous = np.column_stack((corners, np.ones(len(corners))))
        transformed = (self._model_numpy(item) @ homogeneous.T).T[:, :3]
        return np.vstack((transformed.min(axis=0), transformed.max(axis=0)))

    def _scene_bounds(self) -> np.ndarray:
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

    def _camera_matrices(self) -> tuple[QMatrix4x4, QMatrix4x4]:
        bounds = self._scene_bounds()
        target = bounds.mean(axis=0)
        right, up, view = self._camera_basis()

        corners = self._bounds_corners(bounds) - target
        span_x = max(float(np.ptp(corners @ right)), 1.0)
        span_y = max(float(np.ptp(corners @ up)), 1.0)

        width = max(self.width(), 1)
        height = max(self.height(), 1)
        aspect = width / height

        half_x = max(span_x * 0.55 / self.zoom, 0.01)
        half_y = max(span_y * 0.55 / self.zoom, 0.01)
        if half_x / half_y < aspect:
            half_x = half_y * aspect
        else:
            half_y = half_x / aspect

        world_per_pixel_x = (2.0 * half_x) / width
        world_per_pixel_y = (2.0 * half_y) / height
        target = (
            target
            - right * self.pan_px.x() * world_per_pixel_x
            + up * self.pan_px.y() * world_per_pixel_y
        )

        diagonal = max(float(np.linalg.norm(bounds[1] - bounds[0])), 1.0)
        distance = max(diagonal * 2.0, 10.0)
        eye = target + view * distance

        view_matrix = QMatrix4x4()
        view_matrix.lookAt(
            QVector3D(*[float(value) for value in eye]),
            QVector3D(*[float(value) for value in target]),
            QVector3D(*[float(value) for value in up]),
        )

        projection = QMatrix4x4()
        projection.ortho(
            -half_x,
            half_x,
            -half_y,
            half_y,
            0.1,
            distance * 4.0 + diagonal * 2.0 + 100.0,
        )
        return projection, view_matrix

    def _upload_mesh(self, source_mesh: trimesh.Trimesh) -> _GpuMesh:
        if self._mesh_program is None:
            raise RuntimeError("OpenGL mesh shader is not initialized.")

        vertices = np.asarray(source_mesh.vertices, dtype=np.float32)
        normals = np.asarray(source_mesh.vertex_normals, dtype=np.float32)
        faces = np.asarray(source_mesh.faces, dtype=np.uint32).reshape(-1)

        if len(vertices) == 0 or len(faces) == 0:
            raise RuntimeError("Cannot render an empty mesh.")
        if normals.shape != vertices.shape:
            raise RuntimeError("Mesh normals do not match mesh vertices.")

        interleaved = np.empty((len(vertices), 6), dtype=np.float32)
        interleaved[:, :3] = vertices
        interleaved[:, 3:] = normals

        vao = QOpenGLVertexArrayObject()
        vertex_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        index_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)

        if not vao.create():
            raise RuntimeError("Could not create mesh VAO.")
        if not vertex_buffer.create():
            vao.destroy()
            raise RuntimeError("Could not create mesh vertex buffer.")
        if not index_buffer.create():
            vertex_buffer.destroy()
            vao.destroy()
            raise RuntimeError("Could not create mesh index buffer.")

        vertex_buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.StaticDraw)
        index_buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.StaticDraw)

        vao.bind()
        vertex_buffer.bind()
        vertex_bytes = interleaved.tobytes()
        vertex_buffer.allocate(vertex_bytes, len(vertex_bytes))

        index_buffer.bind()
        index_bytes = faces.tobytes()
        index_buffer.allocate(index_bytes, len(index_bytes))

        self._mesh_program.bind()
        self._mesh_program.enableAttributeArray(0)
        self._mesh_program.setAttributeBuffer(0, GL_FLOAT, 0, 3, 24)
        self._mesh_program.enableAttributeArray(1)
        self._mesh_program.setAttributeBuffer(1, GL_FLOAT, 12, 3, 24)
        self._mesh_program.release()

        vao.release()
        vertex_buffer.release()
        index_buffer.release()

        return _GpuMesh(
            source_mesh=source_mesh,
            vao=vao,
            vertex_buffer=vertex_buffer,
            index_buffer=index_buffer,
            index_count=len(faces),
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

        try:
            cached = self._upload_mesh(source_mesh)
        except RuntimeError as exc:
            self._gl_error = str(exc)
            self._update_overlay()
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

    def _stock_lines(self) -> tuple[np.ndarray, np.ndarray]:
        if self.project is None or not self.show_stock:
            empty = np.empty((0, 3), dtype=np.float32)
            return empty, empty

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
        edge_indices = (
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
        edges = np.asarray(
            [corners[index] for pair in edge_indices for index in pair],
            dtype=np.float32,
        )

        if not self.show_grid:
            return edges, np.empty((0, 3), dtype=np.float32)

        largest = max(w, h)
        if largest <= 150.0:
            step = 10.0
        elif largest <= 400.0:
            step = 25.0
        elif largest <= 1000.0:
            step = 50.0
        else:
            step = 100.0

        grid_points: list[tuple[float, float, float]] = []
        for x in np.arange(step, w, step):
            grid_points.extend(((float(x), 0.0, 0.0), (float(x), h, 0.0)))
        for y in np.arange(step, h, step):
            grid_points.extend(((0.0, float(y), 0.0), (w, float(y), 0.0)))

        grid = np.asarray(grid_points, dtype=np.float32).reshape((-1, 3))
        return edges, grid

    def _draw_stock(self, view_projection: QMatrix4x4) -> None:
        edges, grid = self._stock_lines()
        self._draw_lines(
            grid,
            view_projection=view_projection,
            color=QVector4D(0.30, 0.36, 0.47, 1.0),
        )
        self._draw_lines(
            edges,
            view_projection=view_projection,
            color=QVector4D(0.43, 0.50, 0.62, 1.0),
        )

    def _draw_meshes(self, view_projection: QMatrix4x4) -> None:
        if (
            self.project is None
            or self._functions is None
            or self._mesh_program is None
        ):
            return

        self._mesh_program.bind()
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

            model = self._qmatrix_from_numpy(self._model_numpy(item))
            mvp = view_projection * model
            self._mesh_program.setUniformValue("u_mvp", mvp)
            self._mesh_program.setUniformValue(
                "u_normal_matrix",
                model.normalMatrix(),
            )

            if item_index == self.selected_item_index:
                color = QVector4D(0.784, 1.0, 0.239, 1.0)
            else:
                color = QVector4D(0.357, 0.557, 0.839, 1.0)
            self._mesh_program.setUniformValue("u_color", color)

            gpu_mesh.vao.bind()
            self._functions.glDrawElements(
                GL_TRIANGLES,
                gpu_mesh.index_count,
                GL_UNSIGNED_INT,
                None,
            )
            gpu_mesh.vao.release()

        self._mesh_program.release()

    def paintGL(self) -> None:
        if self._functions is None:
            return

        self._functions.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._prune_mesh_cache()

        if self._gl_error is None:
            projection, view_matrix = self._camera_matrices()
            view_projection = projection * view_matrix
            self._draw_stock(view_projection)
            self._draw_meshes(view_projection)

        self._update_overlay()

    def _update_overlay(self) -> None:
        if self._gl_error:
            self._overlay_label.setText(f"OpenGL error: {self._gl_error}")
        else:
            self._overlay_label.setText(
                f"{self._renderer_description}  •  "
                "LMB orbit  •  RMB/MMB pan  •  Wheel zoom  •  Double-click fit"
            )
        self._overlay_label.adjustSize()
        self._overlay_label.move(9, 7)

        has_visible_mesh = bool(
            self.project
            and any(
                item.mesh is not None and item.visible
                for item in self.project.items
            )
        )
        self._empty_label.setText(
            "" if has_visible_mesh else "Import an STL to preview it in the stock."
        )
        self._empty_label.setGeometry(0, 0, max(self.width(), 1), max(self.height(), 1))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._last_mouse_pos = event.position()
        self.setFocus()
        event.accept()

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
        elif event.buttons() & (
            Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton
        ):
            self.pan_px += delta
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._last_mouse_pos = None
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() / 120.0
        self.zoom *= 1.15**steps
        self.zoom = max(0.08, min(25.0, self.zoom))
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.fit_view()
        event.accept()
