"""Tiny Qt-painted line icons for Beta2; independent of Linux icon themes."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def workspace_icon(name: str) -> QIcon:
    """Return a consistent 24 px symbol without SVG assets or system themes."""

    image = QPixmap(24, 24)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#dcebe0"))
    pen.setWidthF(1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if name in {"setup", "stock"}:
        painter.drawRect(QRectF(3, 5, 18, 14))
        painter.drawLine(QPointF(3, 10), QPointF(21, 10))
        painter.drawLine(QPointF(8, 5), QPointF(8, 19))
    elif name in {"operations", "cam"}:
        path = QPainterPath(QPointF(4, 7))
        path.lineTo(19, 7)
        path.lineTo(19, 11)
        path.lineTo(6, 11)
        path.lineTo(6, 15)
        path.lineTo(19, 15)
        path.lineTo(19, 19)
        path.lineTo(4, 19)
        painter.drawPath(path)
    elif name in {"review", "preflight"}:
        path = QPainterPath(QPointF(12, 3))
        path.lineTo(20, 7)
        path.lineTo(19, 15)
        path.quadTo(17, 20, 12, 22)
        path.quadTo(7, 20, 5, 15)
        path.lineTo(4, 7)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(8, 12), QPointF(11, 15))
        painter.drawLine(QPointF(11, 15), QPointF(16, 10))
    elif name in {"export", "download"}:
        painter.drawLine(QPointF(12, 3), QPointF(12, 16))
        painter.drawLine(QPointF(7, 11), QPointF(12, 16))
        painter.drawLine(QPointF(17, 11), QPointF(12, 16))
        painter.drawLine(QPointF(5, 20), QPointF(19, 20))
    elif name == "machine":
        painter.drawRect(QRectF(4, 5, 16, 16))
        painter.drawLine(QPointF(8, 9), QPointF(16, 9))
        painter.drawLine(QPointF(12, 9), QPointF(12, 16))
        painter.drawLine(QPointF(9, 20), QPointF(15, 20))
    elif name == "fixtures":
        painter.drawLine(QPointF(5, 3), QPointF(5, 19))
        painter.drawLine(QPointF(5, 19), QPointF(21, 19))
        painter.drawRect(QRectF(9, 9, 9, 7))
    elif name == "layers":
        for y in (5, 10, 15):
            painter.drawRect(QRectF(5, y, 14, 4))
    elif name == "simulate":
        painter.drawEllipse(QRectF(5, 5, 14, 14))
        painter.drawEllipse(QRectF(9, 9, 6, 6))
        painter.drawLine(QPointF(12, 2), QPointF(12, 22))
    elif name == "job_sheet":
        painter.drawRect(QRectF(6, 3, 12, 18))
        for y in (8, 12, 16):
            painter.drawLine(QPointF(9, y), QPointF(16, y))
    else:
        painter.drawEllipse(QRectF(4, 4, 16, 16))
    painter.end()
    return QIcon(image)
