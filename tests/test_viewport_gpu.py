from PySide6.QtOpenGLWidgets import QOpenGLWidget

from carvefoundry.ui.viewport import MeshViewport


def test_mesh_viewport_uses_qopenglwidget() -> None:
    assert issubclass(MeshViewport, QOpenGLWidget)
