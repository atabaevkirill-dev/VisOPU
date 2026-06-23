"""VisOPU widget components."""
from __future__ import annotations

import math
import threading
import time

from PyQt6 import sip
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QSizePolicy, QFrame, QPlainTextEdit,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPointF, QRectF, pyqtSignal,
    QPropertyAnimation, QEasingCurve, QUrl,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFontMetrics,
    QRadialGradient, QLinearGradient, QPolygonF, QFont,
    QPainterPath, QImage, QPixmap,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEnginePage
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

import logging
_logger = logging.getLogger(__name__)

from app.offline_map import MBTilesServer

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from app.detector import YoloDetector, Detection, AIR_CLASSES
from app.i18n import tr


# DIRECTION PAD (8 directions)
# ═══════════════════════════════════════════════════════════════════

class DirectionPad(QWidget):
    """8-direction D-Pad control widget with diagonals (compact 160px)."""
    direction_pressed = pyqtSignal(str)
    direction_released = pyqtSignal(str)

    _SZ = 160      # widget size
    _CX = 80       # center x/y
    _OR = 76       # outer radius
    _CD = 38       # cardinal arrow distance from center
    _DD = 30       # diagonal arrow distance
    _SR = 12       # stop button radius

    def __init__(self):
        super().__init__()
        self.setFixedSize(self._SZ, self._SZ)
        self.pressed_dir = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self._CX, self._CX

        bg = QRadialGradient(cx, cy, self._OR)
        bg.setColorAt(0, QColor(0x2D, 0x2D, 0x2D))
        bg.setColorAt(1, QColor(0x1C, 0x1C, 0x1E))
        p.setBrush(bg)
        p.setPen(QPen(QColor(0x48, 0x48, 0x4A), 1.5))
        p.drawEllipse(QPointF(cx, cy), self._OR, self._OR)

        cardinals = {
            'UP':    (cx, cy - self._CD, 0),
            'DOWN':  (cx, cy + self._CD, 180),
            'LEFT':  (cx - self._CD, cy, 270),
            'RIGHT': (cx + self._CD, cy, 90),
        }
        for d, (ax, ay, rot) in cardinals.items():
            pressed = self.pressed_dir == d
            color = QColor(0x0A, 0x84, 0xFF) if pressed else QColor(0x8E, 0x8E, 0x93, 200)
            p.save()
            p.translate(ax, ay)
            p.rotate(rot)
            tri = QPolygonF([
                QPointF(0, -10), QPointF(8, 5), QPointF(3, 3),
                QPointF(3, 10), QPointF(-3, 10), QPointF(-3, 3), QPointF(-8, 5),
            ])
            if pressed:
                g = QRadialGradient(0, 0, 13)
                g.setColorAt(0, QColor(0x0A, 0x84, 0xFF, 70))
                g.setColorAt(1, QColor(0x0A, 0x84, 0xFF, 0))
                p.setBrush(g)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(0, 0), 13, 13)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPolygon(tri)
            p.restore()

        diag_dirs = {
            'UP_RIGHT':   (cx + self._DD, cy - self._DD, 45),
            'UP_LEFT':    (cx - self._DD, cy - self._DD, 315),
            'DOWN_RIGHT': (cx + self._DD, cy + self._DD, 135),
            'DOWN_LEFT':  (cx - self._DD, cy + self._DD, 225),
        }
        for d, (ax, ay, rot) in diag_dirs.items():
            pressed = self.pressed_dir == d
            color = QColor(0x40, 0x9C, 0xFF) if pressed else QColor(0x63, 0x63, 0x66, 160)
            p.save()
            p.translate(ax, ay)
            p.rotate(rot)
            tri = QPolygonF([
                QPointF(0, -7), QPointF(5, 3), QPointF(2, 2),
                QPointF(2, 7), QPointF(-2, 7), QPointF(-2, 3), QPointF(-5, 3),
            ])
            if pressed:
                g = QRadialGradient(0, 0, 10)
                g.setColorAt(0, QColor(0x0A, 0x84, 0xFF, 50))
                g.setColorAt(1, QColor(0x0A, 0x84, 0xFF, 0))
                p.setBrush(g)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(0, 0), 10, 10)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPolygon(tri)
            p.restore()

        pressed_stop = self.pressed_dir == 'STOP'
        p.setPen(QPen(QColor(0x48, 0x48, 0x4A), 1.5))
        p.setBrush(QColor(0x0A, 0x84, 0xFF, 50) if pressed_stop else QColor(0x2D, 0x2D, 0x2D))
        p.drawEllipse(QPointF(cx, cy), self._SR, self._SR)
        p.setFont(QFont("SF Pro Display", 7, QFont.Weight.Bold))
        p.setPen(QColor(0x8E, 0x8E, 0x93))
        p.drawText(QRectF(cx - self._SR, cy - 5, self._SR * 2, 10),
                   Qt.AlignmentFlag.AlignCenter, "STOP")

        p.end()

    def mousePressEvent(self, event):
        d = self._get_dir(event.pos())
        if d:
            self.pressed_dir = d
            self.direction_pressed.emit(d)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.pressed_dir:
            self.direction_released.emit(self.pressed_dir)
            self.pressed_dir = None
            self.update()

    def _get_dir(self, pos):
        cx, cy = self._CX, self._CX
        dx, dy = pos.x() - cx, pos.y() - cy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 14:
            return 'STOP'
        if dist > self._OR:
            return None
        angle = math.degrees(math.atan2(-dy, dx))
        if angle < 0:
            angle += 360
        if angle >= 337.5 or angle < 22.5:
            return 'RIGHT'
        elif angle < 67.5:
            return 'UP_RIGHT'
        elif angle < 112.5:
            return 'UP'
        elif angle < 157.5:
            return 'UP_LEFT'
        elif angle < 202.5:
            return 'LEFT'
        elif angle < 247.5:
            return 'DOWN_LEFT'
        elif angle < 292.5:
            return 'DOWN'
        else:
            return 'DOWN_RIGHT'


# ═══════════════════════════════════════════════════════════════════
