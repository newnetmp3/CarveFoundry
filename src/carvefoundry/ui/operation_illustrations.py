"""Small illustrative CAM-operation animation for first-time CNC users.

This graphic explains intent only; the actual cutter-compensated toolpaths and
stock-removal simulation are authoritative.
"""
from __future__ import annotations

from itertools import pairwise

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

_OPERATION_EXPLANATIONS = {
    "profile": (
        "Profile follows the outline of a shape. Choose Inside/Outside "
        "in Advanced when cutter radius matters; a cutout needs secure holding."
    ),
    "pocket": (
        "Pocket removes wood INSIDE a closed region, leaving a recessed area."
    ),
    "vcarve": (
        "V-Carve varies cutting depth across lettering or shapes with a V-bit."
    ),
    "engrave": (
        "Engrave traces outlines or linework at the configured depth."
    ),
    "rough": (
        "3D Rough removes the bulk of the wood before a smaller or round "
        "finishing cutter refines the surface."
    ),
    "finish": (
        "3D Finish follows the modeled top surface. A finer stepover can "
        "improve visible detail but takes more passes."
    ),
}


def operation_explanation(operation: str) -> str:
    return _OPERATION_EXPLANATIONS.get(
        operation, "Choose Advanced to configure this specialized operation."
    )


class CamOperationIllustration(QWidget):
    """Animated cartoon of the material-removal idea, never a CAM preview."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CamOperationIllustration")
        self.setMinimumHeight(112)
        self._operation = "finish"
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._advance)
        self.setToolTip(
            "Concept illustration only; use actual material-removal simulation "
            "to review generated toolpaths and cutter contact."
        )

    def set_operation(self, operation: str) -> None:
        if self._operation != operation:
            self._operation = operation
            self._frame = 0
            self.update()

    def set_running(self, running: bool) -> None:
        if running:
            self._timer.start()
        else:
            self._timer.stop()

    def _advance(self) -> None:
        self._frame = (self._frame + 1) % 32
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#182436"))
        w = max(self.width() - 30, 80)
        x0 = 14.0
        y0 = 27.0
        wood = QRectF(x0, y0 + 22, w, 45)
        painter.setPen(QPen(QColor("#e2b98a"), 1))
        painter.setBrush(QColor("#9a6e47"))
        painter.drawRoundedRect(wood, 3, 3)

        x = x0 + 8 + (w - 16) * self._frame / 31
        active = self._operation
        painter.setPen(QPen(QColor("#223b45"), 2))
        if active == "pocket":
            painter.setBrush(QColor("#263b4d"))
            painter.drawRect(QRectF(x0 + w * 0.2, y0 + 22, w * 0.6, 16))
        elif active in {"vcarve", "engrave"}:
            painter.setPen(QPen(QColor("#283b49"), 4 if active == "engrave" else 9))
            painter.drawLine(
                int(x0 + w * 0.22), int(y0 + 23),
                int(x0 + w * 0.78), int(y0 + 23),
            )
        elif active == "rough":
            painter.setBrush(QColor("#263b4d"))
            painter.drawRect(QRectF(x0 + w * 0.2, y0 + 22, w * 0.6, 10))
        elif active == "finish":
            painter.setPen(QPen(QColor("#273e4c"), 3))
            path = [
                (x0 + w * (0.15 + i * 0.7 / 24), y0 + 28 - (
                    8 if i in range(8, 17) else 0
                ))
                for i in range(25)
            ]
            for a, b in pairwise(path):
                painter.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
        else:
            painter.setPen(QPen(QColor("#263b4d"), 4))
            painter.drawLine(
                int(x0 + w * 0.15), int(y0 + 23),
                int(x0 + w * 0.85), int(y0 + 23),
            )

        painter.setPen(QPen(QColor("#83d7b0"), 2))
        painter.setBrush(QColor("#7dc3a5"))
        painter.drawRect(QRectF(x - 4, y0 - 7, 8, 28))
        painter.drawLine(int(x), int(y0 + 21), int(x), int(y0 + 30))
        painter.setPen(QColor("#d1deeb"))
        painter.drawText(
            self.rect().adjusted(12, 1, -8, -1),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            "Illustration only — not generated cutter motion",
        )
        painter.end()
