"""Double-click Fit View is restricted to the empty black viewport margin."""
from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from carvefoundry.core.project import Project
from carvefoundry.ui.native_viewport import _NativeOpenGLViewport

_APP = QApplication.instance() or QApplication([])


def _double_click(
    renderer: _NativeOpenGLViewport,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        QPointF(20.0, 20.0),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )
    renderer.mouseDoubleClickEvent(event)
    assert event.isAccepted()


@pytest.mark.parametrize(
    ("on_stock", "on_model", "stock_visible", "grid_visible", "button", "fits"),
    [
        (True, False, True, True, Qt.MouseButton.LeftButton, False),
        (True, False, False, True, Qt.MouseButton.LeftButton, False),
        (True, False, True, False, Qt.MouseButton.LeftButton, False),
        (True, False, False, False, Qt.MouseButton.LeftButton, True),
        (False, True, True, True, Qt.MouseButton.LeftButton, False),
        (False, False, True, True, Qt.MouseButton.LeftButton, True),
        (False, False, True, True, Qt.MouseButton.RightButton, False),
    ],
)
def test_fit_view_only_on_empty_black_background(
    monkeypatch,
    on_stock,
    on_model,
    stock_visible,
    grid_visible,
    button,
    fits,
) -> None:
    renderer = _NativeOpenGLViewport(Project())
    try:
        stock = renderer.project.stock
        x = float(stock.width_mm) / 2 if on_stock else -30.0
        y = float(stock.height_mm) / 2
        origin = np.array((x, y, 100.0))
        direction = np.array((0.0, 0.0, -1.0))
        monkeypatch.setattr(renderer, "_screen_ray", lambda _pos: (origin, direction))
        monkeypatch.setattr(
            renderer, "pick_item", lambda _pos: 0 if on_model else None,
        )
        renderer.show_stock = stock_visible
        renderer.show_grid = grid_visible
        emitted = []
        renderer.fitRequested.connect(lambda: emitted.append(True))

        before = renderer.camera.zoom
        _double_click(renderer, button)
        assert bool(emitted) is fits
        assert renderer.camera.zoom == before
    finally:
        renderer.close()


def test_fit_view_ignores_unprojectable_pointer(monkeypatch) -> None:
    renderer = _NativeOpenGLViewport(Project())
    try:
        monkeypatch.setattr(renderer, "_screen_ray", lambda _pos: None)
        emitted = []
        renderer.fitRequested.connect(lambda: emitted.append(True))
        _double_click(renderer)
        assert not emitted
    finally:
        renderer.close()


def test_empty_project_background_may_fit(monkeypatch) -> None:
    renderer = _NativeOpenGLViewport(None)
    try:
        emitted = []
        renderer.fitRequested.connect(lambda: emitted.append(True))
        _double_click(renderer)
        assert emitted == [True]
    finally:
        renderer.close()
