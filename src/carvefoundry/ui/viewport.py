from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent

from .viewport_gpu import MeshViewport as _GpuMeshViewport


class MeshViewport(_GpuMeshViewport):
    """GPU viewport with selection-aware framing and deep inspection zoom."""

    MIN_ZOOM = 0.01
    MAX_ZOOM = 100_000.0

    def _scene_bounds(self):
        """Frame the selected mesh instead of letting stock dominate the view.

        Selecting the Stock row clears ``selected_item_index`` and therefore
        intentionally falls back to the complete stock/project bounds.
        """

        if self.project is not None and self.selected_item_index is not None:
            index = self.selected_item_index
            if 0 <= index < len(self.project.items):
                item = self.project.items[index]
                if item.visible and item.mesh is not None:
                    return self._item_bounds_mm(item)
        return super()._scene_bounds()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom over a much wider range than the original 25x limit."""

        angle_steps = event.angleDelta().y() / 120.0
        if angle_steps:
            steps = angle_steps
        else:
            # Some Wayland touchpads report smooth scrolling through pixelDelta.
            steps = event.pixelDelta().y() / 120.0

        if steps:
            self.zoom *= 1.20**steps
            self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.zoom))
            self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-click fits the selected model; Stock selection fits the scene."""

        self.fit_view()
        event.accept()


__all__ = ["MeshViewport"]
