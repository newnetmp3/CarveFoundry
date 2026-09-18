"""CarveFoundry native CAD viewport.

The active viewport is implemented with an embedded QOpenGLWindow rather than
QOpenGLWidget. This avoids the extra QWidget/FBO composition path that produced
zoom-only frame ghosting under KDE Plasma/Wayland.
"""

from .native_viewport import MeshViewport

__all__ = ["MeshViewport"]
