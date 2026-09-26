"""Small, animated explanations of CAM operation intent."""
from __future__ import annotations

import math
from itertools import pairwise

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

_OPERATION_EXPLANATIONS = {
    "profile": "Profile follows the outline of a shape. Choose Inside/Outside in Advanced when cutter radius matters; a cutout needs secure holding.",
    "pocket": "Pocket removes wood INSIDE a closed region, leaving a recessed area.",
    "vcarve": "V-Carve varies cutting depth across lettering or shapes with a V-bit.",
    "engrave": "Engrave traces outlines or linework at the configured depth.",
    "rough": "3D Rough removes bulk material before a smaller or round finishing cutter refines the surface.",
    "finish": "3D Finish follows the modeled top surface. A finer stepover can improve visible detail but takes more passes.",
    "silhouette": "Silhouette traces the outside boundary of the selected shapes.",
    "surface": "Surface / Face skims the stock top with parallel leveling passes.",
    "drill": "Drill Features plunges at each hole location, then retracts safely.",
    "center_drill": "Center Drill spots each hole before a larger drill follows.",
    "height_map": "Height Map scans a relief in close parallel passes.",
    "rest": "3D Rest clears material left behind by the previous, larger cutter.",
    "waterline": "3D Waterline follows constant-height contours around steep walls.",
}


def operation_explanation(operation: str) -> str:
    return _OPERATION_EXPLANATIONS.get(operation, "Choose Advanced to configure this specialized operation.")


class CamOperationIllustration(QWidget):
    """Animated concept view with operation-specific cutter motion."""

    _WIDTH, _HEIGHT, _FRAMES = 250, 170, 56

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CamOperationIllustration")
        self.setMinimumSize(self._WIDTH, self._HEIGHT)
        self.setMaximumSize(self._WIDTH, self._HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._operation = "finish"
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._advance)
        self.setToolTip("Concept illustration only; use material-removal simulation to review generated toolpaths.")

    def sizeHint(self) -> QSize:
        return QSize(self._WIDTH, self._HEIGHT)

    def set_operation(self, operation: str) -> None:
        operation = str(operation or "finish")
        if self._operation != operation:
            self._operation, self._frame = operation, 0
            self.update()

    def set_running(self, running: bool) -> None:
        (self._timer.start if running else self._timer.stop)()

    def _advance(self) -> None:
        self._frame = (self._frame + 1) % self._FRAMES
        self.update()

    @property
    def _progress(self) -> float:
        return self._frame / (self._FRAMES - 1)

    def _cutter(self, p: QPainter, x: float, y: float, *, v_bit: bool = False) -> None:
        p.save()
        p.setPen(QPen(QColor("#8fe3c2"), 1.5))
        p.setBrush(QColor("#77bfaa"))
        if v_bit:
            p.drawPolygon(QPolygonF((QPointF(x - 8, y - 16), QPointF(x + 8, y - 16), QPointF(x, y + 7))))
        else:
            p.drawRoundedRect(QRectF(x - 5, y - 17, 10, 23), 2, 2)
            p.drawLine(QPointF(x, y + 6), QPointF(x, y + 13))
        p.restore()

    def _path(self, p: QPainter, points: list[QPointF], upto: float) -> None:
        if len(points) < 2:
            return
        count = max(1, min(len(points) - 1, math.ceil((len(points) - 1) * upto)))
        p.save()
        p.setPen(QPen(QColor("#f4c86a"), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for a, b in pairwise(points[: count + 1]):
            p.drawLine(a, b)
        p.restore()

    def _profile(self, p: QPainter, box: QRectF) -> None:
        cx, cy, rx, ry = box.center().x(), box.center().y() + 2, box.width() * .31, box.height() * .26
        pts = [QPointF(cx-rx, cy-ry), QPointF(cx+rx, cy-ry), QPointF(cx+rx, cy+ry), QPointF(cx-rx, cy+ry), QPointF(cx-rx, cy-ry)]
        self._path(p, pts, self._progress)
        i = min(4, int(self._progress * 4))
        self._cutter(p, pts[i].x(), pts[i].y())
        p.setPen(QPen(QColor("#7b9eae"), 1))
        p.drawRect(QRectF(cx-rx-7, cy-ry-7, 2*rx+14, 2*ry+14))

    def _pocket(self, p: QPainter, box: QRectF) -> None:
        left, right, top, bottom = box.left()+25, box.right()-25, box.top()+34, box.bottom()-25
        p.setPen(QPen(QColor("#426276"), 1)); p.setBrush(QColor("#263e4e")); p.drawRoundedRect(QRectF(left, top, right-left, bottom-top), 7, 7)
        pts = []
        for row in range(6):
            y = top + 12 + row * (bottom-top-24) / 5
            pts.extend((QPointF(left+7, y), QPointF(right-7, y)) if row % 2 == 0 else (QPointF(right-7, y), QPointF(left+7, y)))
        self._path(p, pts, self._progress); i = min(len(pts)-1, int(self._progress*(len(pts)-1))); self._cutter(p, pts[i].x(), pts[i].y())

    def _linework(self, p: QPainter, box: QRectF, *, v_bit: bool) -> None:
        cx, cy = box.center().x(), box.center().y()+4
        pts = [QPointF(cx-40,cy-18), QPointF(cx-15,cy+20), QPointF(cx,cy-2), QPointF(cx+15,cy+20), QPointF(cx+40,cy-18)]
        p.setPen(QPen(QColor("#55798c"), 1)); p.drawLine(QPointF(cx-48,cy+25), QPointF(cx+48,cy+25)); self._path(p, pts, self._progress)
        i = min(4, int(self._progress*4)); self._cutter(p, pts[i].x(), pts[i].y(), v_bit=v_bit)

    def _raster(self, p: QPainter, box: QRectF, *, rough: bool) -> None:
        left, right, top, bottom = box.left()+17, box.right()-17, box.top()+33, box.bottom()-22
        rows = 6 if rough else 10; pts = []
        for row in range(rows):
            y = top + row*(bottom-top)/(rows-1); pts.extend((QPointF(left,y), QPointF(right,y)) if row % 2 == 0 else (QPointF(right,y), QPointF(left,y)))
        p.setPen(QPen(QColor("#39596a"), 1)); p.setBrush(QColor("#284657" if rough else "#31576b")); p.drawEllipse(QRectF(left+13,top+4,right-left-26,bottom-top-8)); self._path(p, pts, self._progress)
        i = min(len(pts)-1, int(self._progress*(len(pts)-1))); self._cutter(p, pts[i].x(), pts[i].y())

    def _drill(self, p: QPainter, box: QRectF) -> None:
        centers = [QPointF(box.center().x()+dx, box.center().y()+dy) for dx,dy in ((-32,-24),(32,-24),(-32,25),(32,25))]
        index = min(3, int(self._progress*4))
        for i, point in enumerate(centers):
            p.setPen(QPen(QColor("#f4c86a" if i < index else "#55798c"), 2)); p.drawEllipse(point, 8 if i < index else 6, 8 if i < index else 6)
        self._cutter(p, centers[index].x(), centers[index].y())

    def _waterline(self, p: QPainter, box: QRectF) -> None:
        cx, cy, pts = box.center().x(), box.center().y()+3, []
        for ring in range(4):
            rx, ry = 14+ring*11, 10+ring*8
            for step in range(17):
                angle = 2*math.pi*step/16; pts.append(QPointF(cx+rx*math.cos(angle), cy+ry*math.sin(angle)))
        self._path(p, pts, self._progress); i = min(len(pts)-1, int(self._progress*(len(pts)-1))); self._cutter(p, pts[i].x(), pts[i].y())

    def paintEvent(self, _event) -> None:
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.fillRect(self.rect(), QColor("#152535")); p.setPen(QPen(QColor("#355163"), 1)); p.drawRoundedRect(self.rect().adjusted(1,1,-2,-2), 9, 9)
        p.setPen(QColor("#d1deeb")); p.drawText(QRectF(12,9,self.width()-24,17), "WHAT THE CUTTER DOES")
        box = QRectF(15,30,self.width()-30,self.height()-47); p.setPen(QPen(QColor("#527286"),1)); p.setBrush(QColor("#9a6e47")); p.drawRoundedRect(box,6,6)
        op = self._operation
        if op in {"profile", "silhouette"}: self._profile(p, box)
        elif op == "pocket": self._pocket(p, box)
        elif op == "vcarve": self._linework(p, box, v_bit=True)
        elif op == "engrave": self._linework(p, box, v_bit=False)
        elif op in {"rough", "surface", "height_map", "rest", "finish"}: self._raster(p, box, rough=op in {"rough", "rest"})
        elif op in {"drill", "center_drill"}: self._drill(p, box)
        elif op == "waterline": self._waterline(p, box)
        else: self._raster(p, box, rough=False)
        p.setPen(QColor("#8da5b4")); p.drawText(QRectF(12,self.height()-15,self.width()-24,12), "concept view · not machine motion"); p.end()
