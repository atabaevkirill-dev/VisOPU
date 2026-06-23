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


# COLLAPSIBLE PANEL
# ═══════════════════════════════════════════════════════════════════

class CollapsiblePanel(QFrame):
    """Panel with clickable header that collapses/expands content."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.collapsed = False
        self.setStyleSheet("""
            CollapsiblePanel {
                background: transparent;
                border: none;
            }
        """)
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Clickable header
        self._header = _PanelHeader(title)
        self._header.clicked.connect(self.toggle)
        main.addWidget(self._header)

        # Content container
        self._content = QWidget()
        self._cl = QVBoxLayout(self._content)
        self._cl.setContentsMargins(4, 6, 4, 8)
        self._cl.setSpacing(6)
        main.addWidget(self._content)

        # Animation
        self._anim = QPropertyAnimation(self._content, b'maximumHeight')
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def content_layout(self):
        return self._cl

    def setTitle(self, title):
        self._header.setTitle(title)

    def toggle(self):
        if self.collapsed:
            self._expand()
        else:
            self._collapse()

    def _collapse(self):
        self.collapsed = True
        self._header.set_arrow(False)
        self._anim.setStartValue(self._content.sizeHint().height())
        self._anim.setEndValue(0)
        self._anim.finished.connect(self._on_collapsed)
        self._anim.start()

    def _on_collapsed(self):
        self._content.setVisible(False)
        try:
            self._anim.finished.disconnect(self._on_collapsed)
        except TypeError:
            pass

    def _expand(self):
        self.collapsed = False
        self._content.setVisible(True)
        self._header.set_arrow(True)
        h = self._content.sizeHint().height()
        self._anim.setStartValue(0)
        self._anim.setEndValue(max(h, 500))
        self._anim.finished.connect(self._on_expanded)
        self._anim.start()

    def _on_expanded(self):
        self._content.setMaximumHeight(16777215)
        try:
            self._anim.finished.disconnect(self._on_expanded)
        except TypeError:
            pass


class _PanelHeader(QWidget):
    """Clean minimal header for CollapsiblePanel."""
    clicked = pyqtSignal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title = title
        self._arrow = True  # True = expanded
        self._hover = False

    def set_arrow(self, expanded):
        self._arrow = expanded
        self.update()

    def setTitle(self, title):
        self._title = title
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

        # Subtle hover highlight
        if self._hover:
            p.fillRect(self.rect(), QColor(0x2D, 0x2D, 0x2D, 80))

        # Chevron
        arrow_color = QColor(0x0A, 0x84, 0xFF) if self._arrow else QColor(0x63, 0x63, 0x66)
        arrow = "▾" if self._arrow else "▸"
        p.setFont(QFont("SF Pro Display", 9, QFont.Weight.Bold))
        p.setPen(arrow_color)
        p.drawText(6, 16, arrow)

        # Title
        p.setPen(QColor(0x98, 0x98, 0x9D))
        p.setFont(QFont("SF Pro Display", 9, QFont.Weight.Bold))
        p.drawText(22, 16, self._title.upper())

        # Thin bottom divider
        p.setPen(QPen(QColor(0x3C, 0x3C, 0x3C, 120), 1))
        p.drawLine(0, 23, self.width(), 23)
        p.end()


# ═══════════════════════════════════════════════════════════════════
