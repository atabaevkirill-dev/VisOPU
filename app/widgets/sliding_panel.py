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


# SLIDING PANEL — side panel that slides in/out
# ═══════════════════════════════════════════════════════════════════

class SlidingPanel(QWidget):
    """Side panel that can slide in/out with animation."""

    def __init__(self, width, side='left', parent=None):
        super().__init__(parent)
        self._width = width
        self._side = side
        self._collapsed = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Content area
        self._content = QWidget()
        self._content.setFixedWidth(width)
        self._content.setStyleSheet("background:#252526;")

        # Toggle strip
        self._strip = _ToggleStrip(side)
        self._strip.clicked.connect(self.toggle)

        if side == 'left':
            layout.addWidget(self._content)
            layout.addWidget(self._strip)
        else:
            layout.addWidget(self._strip)
            layout.addWidget(self._content)

        # Animation
        self._anim = QPropertyAnimation(self._content, b'maximumWidth')
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def content_layout(self):
        return self._content.layout()

    def set_content_layout(self, layout):
        self._content.setLayout(layout)

    def toggle(self):
        if self._collapsed:
            self._show()
        else:
            self._hide()

    def _hide(self):
        self._collapsed = True
        self._strip.set_expanded(False)
        self._content.setMinimumWidth(0)  # Allow shrinking
        self._anim.setStartValue(self._width)
        self._anim.setEndValue(0)
        self._anim.finished.connect(self._on_hidden)
        self._anim.start()

    def _on_hidden(self):
        try:
            self._anim.finished.disconnect(self._on_hidden)
        except TypeError:
            pass

    def _show(self):
        self._collapsed = False
        self._strip.set_expanded(True)
        self._anim.setStartValue(0)
        self._anim.setEndValue(self._width)
        self._anim.finished.connect(self._on_shown)
        self._anim.start()

    def _on_shown(self):
        try:
            self._anim.finished.disconnect(self._on_shown)
        except TypeError:
            pass


class _ToggleStrip(QWidget):
    """Thin clickable strip on the edge of a sliding panel."""
    clicked = pyqtSignal()

    def __init__(self, side='left', parent=None):
        super().__init__(parent)
        self.setFixedWidth(16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._side = side
        self._expanded = True
        self._hover = False
        self.setStyleSheet("background:transparent;")

    def set_expanded(self, expanded):
        self._expanded = expanded
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        bg = QColor(0x2D, 0x2D, 0x2D, 180) if self._hover else QColor(0x25, 0x25, 0x26, 100)
        p.fillRect(0, 0, w, h, bg)

        # Thin edge line
        line_x = w - 1 if self._side == 'left' else 0
        p.setPen(QPen(QColor(0x3C, 0x3C, 0x3C), 1))
        p.drawLine(line_x, 0, line_x, h)

        # Arrow indicator
        cy = h // 2
        if self._side == 'left':
            arrow = "\u25C2" if self._expanded else "\u25B8"
        else:
            arrow = "\u25B8" if self._expanded else "\u25C2"

        col = QColor(0x0A, 0x84, 0xFF) if self._hover else QColor(0x63, 0x63, 0x66)
        p.setPen(col)
        p.setFont(QFont("SF Pro Display", 8, QFont.Weight.Bold))
        p.drawText(QRectF(0, cy - 10, w, 20),
                   Qt.AlignmentFlag.AlignCenter, arrow)
        p.end()


# ═══════════════════════════════════════════════════════════════════
