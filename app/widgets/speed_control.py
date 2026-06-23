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


# SPEED CONTROL (Slider)
# ═══════════════════════════════════════════════════════════════════

class SpeedControl(QWidget):
    """Speed setting widget — stores magnitude value, emits signal on change."""
    speed_changed = pyqtSignal(float)  # emits new speed in °/s

    def __init__(self, label, min_val, max_val, parent=None):
        super().__init__(parent)
        self.min_val = min(0, min_val)  # speed can't be negative
        self.max_val = max(1, max_val)
        layout = QVBoxLayout()
        layout.setSpacing(4)

        self.title = QLabel(label)
        self.title.setStyleSheet(
            "color: #636366; font: 700 8px 'SF Pro Display'; letter-spacing: 1px;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_label = QLabel("0.0 °/s")
        self.value_label.setStyleSheet(
            "color: #f5f5f7; font: 600 13px 'SF Pro Display';")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)                     # always 0
        self.slider.setMaximum(int(self.max_val * 10))  # e.g. 500 for max=50
        self.slider.setValue(0)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #3a3a3c;
                height: 3px; border-radius: 1.5px;
            }
            QSlider::sub-page:horizontal {
                background: #0a84ff;
                border-radius: 1.5px;
            }
            QSlider::handle:horizontal {
                background: #f5f5f7;
                width: 14px; height: 14px;
                margin: -5.5px 0; border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
            }
            QSlider::handle:horizontal:pressed {
                background: #0a84ff;
            }
        """)
        self.slider.valueChanged.connect(self._on_change)

        layout.addWidget(self.title)
        layout.addWidget(self.slider)
        layout.addWidget(self.value_label)
        self.setLayout(layout)

    def _on_change(self, val):
        speed = val / 10.0
        self.value_label.setText(f"{speed:.1f} °/s")
        self.speed_changed.emit(speed)

    def get_speed(self):
        return self.slider.value() / 10.0

    def set_speed(self, speed):
        """Programmatically set slider value."""
        self.slider.setValue(int(max(0, min(self.max_val, speed)) * 10))

    def reset(self):
        self.slider.blockSignals(True)
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.value_label.setText("0.0 \u00b0/s")

    def setTitle(self, title):
        self.title.setText(title)


# ═══════════════════════════════════════════════════════════════════
