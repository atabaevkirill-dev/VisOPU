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


# DASHBOARD WIDGET — center panel with gauges and status cards
# ═══════════════════════════════════════════════════════════════════


class ArcGauge(QWidget):
    """Circular arc gauge widget with animated value display."""

    def __init__(self, title="", unit="", min_val=0.0, max_val=100.0,
                 arc_start=225, arc_span=270, color="#0a84ff", parent=None):
        super().__init__(parent)
        self._title = title
        self._unit = unit
        self._min = min_val
        self._max = max_val
        self._value = min_val
        self._arc_start = arc_start   # degrees from top (CW)
        self._arc_span = arc_span      # total arc degrees
        self._color = QColor(color)
        self.setMinimumSize(120, 120)

    def set_value(self, v):
        self._value = max(self._min, min(self._max, v))
        self.update()

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        side = min(w, h)
        p.translate(w // 2, h // 2)
        r = side // 2 - 8

        # ── Background arc (dim track) ──
        bg_pen = QPen(QColor(0x3C, 0x3C, 0x3C), 6)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(bg_pen)
        # Qt angles: 0°=3 o'clock, positive=CCW, multiply by 16 for fixed-point
        start_qt = (90 - self._arc_start) * 16
        span_qt = -self._arc_span * 16
        p.drawArc(QRectF(-r, -r, 2 * r, 2 * r), start_qt, span_qt)

        # ── Value arc ──
        frac = (self._value - self._min) / (self._max - self._min + 1e-9)
        val_span = frac * self._arc_span
        grad = QRadialGradient(0, 0, r)
        c = self._color
        grad.setColorAt(0, QColor(c.red(), c.green(), c.blue(), 220))
        grad.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 160))
        val_pen = QPen(QBrush(grad), 6)
        val_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(val_pen)
        p.drawArc(QRectF(-r, -r, 2 * r, 2 * r),
                  start_qt, -int(val_span * 16))

        # ── Tick marks ──
        tick_pen = QPen(QColor(0x63, 0x63, 0x66, 120), 1)
        p.setPen(tick_pen)
        for i in range(11):
            ang = math.radians(self._arc_start - i * self._arc_span / 10)
            x0 = (r - 4) * math.cos(ang)
            y0 = -(r - 4) * math.sin(ang)
            x1 = (r - 10) * math.cos(ang)
            y1 = -(r - 10) * math.sin(ang)
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

        # ── Glow dot at value position ──
        val_ang = math.radians(self._arc_start - frac * self._arc_span)
        dot_x = r * math.cos(val_ang)
        dot_y = -r * math.sin(val_ang)
        glow = QRadialGradient(dot_x, dot_y, 8)
        glow.setColorAt(0, QColor(c.red(), c.green(), c.blue(), 180))
        glow.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(dot_x, dot_y), 8, 8)

        # ── Value text ──
        p.setPen(QColor(0xF5, 0xF5, 0xF7))
        p.setFont(QFont("SF Pro Display", int(side * 0.12), QFont.Weight.Bold))
        val_str = f"{self._value:.1f}"
        p.drawText(QRectF(-r, -side * 0.12, 2 * r, side * 0.25),
                   Qt.AlignmentFlag.AlignCenter, val_str)

        # ── Unit ──
        p.setPen(QColor(0x63, 0x63, 0x66))
        p.setFont(QFont("SF Pro Display", int(side * 0.07)))
        p.drawText(QRectF(-r, side * 0.08, 2 * r, side * 0.14),
                   Qt.AlignmentFlag.AlignCenter, self._unit)

        # ── Title ──
        p.setPen(QColor(0x98, 0x98, 0x9D))
        p.setFont(QFont("SF Pro Display", int(side * 0.065), QFont.Weight.Bold))
        p.drawText(QRectF(-r, -side * 0.34, 2 * r, side * 0.16),
                   Qt.AlignmentFlag.AlignCenter, self._title.upper())

        p.end()


class DashboardWidget(QWidget):
    """Central dashboard with gauges and live metrics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #1e1e1e;")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)

        # ── HEADER ──
        hdr = QHBoxLayout()
        title = QLabel(tr('dash_title'))
        title.setStyleSheet(
            "color: #f5f5f7; font: 700 18px 'SF Pro Display';")
        hdr.addWidget(title)
        hdr.addStretch()
        self._time_lbl = QLabel("")
        self._time_lbl.setStyleSheet(
            "color: #636366; font: 500 11px 'SF Pro Display';")
        hdr.addWidget(self._time_lbl)
        self._version_lbl = QLabel("v1.0.0")
        self._version_lbl.setStyleSheet(
            "color: #48484a; font: 500 10px 'SF Pro Display';")
        hdr.addWidget(self._version_lbl)
        root.addLayout(hdr)

        # ── GAUGES ROW ──
        gauges_row = QHBoxLayout()
        gauges_row.setSpacing(12)
        gauges_row.addStretch()

        self.gauge_pan = ArcGauge("PAN", "\u00b0", 0.0, 360.0, color="#0a84ff")
        gauges_row.addWidget(self.gauge_pan)

        self.gauge_tilt = ArcGauge("TILT", "\u00b0", -90.0, 45.0, color="#30d158")
        gauges_row.addWidget(self.gauge_tilt)

        self.gauge_laser = ArcGauge("RANGE", "m", 0.0, 5000.0, color="#ff9f0a")
        gauges_row.addWidget(self.gauge_laser)

        self.gauge_temp = ArcGauge("TEMP", "\u00b0C", -40.0, 80.0, color="#bf5af2")
        gauges_row.addWidget(self.gauge_temp)

        gauges_row.addStretch()
        root.addLayout(gauges_row, 1)

        # ── METRICS STRIP ──
        metrics = QFrame()
        metrics.setStyleSheet(
            "QFrame{background:#252526; border-radius:8px; border:1px solid #3c3c3c;}")
        metrics.setFixedHeight(48)
        mh = QHBoxLayout(metrics)
        mh.setContentsMargins(16, 4, 16, 4)
        mh.setSpacing(24)

        self._pan_speed_lbl = QLabel("PAN SPD: 0.0")
        self._tilt_speed_lbl = QLabel("TILT SPD: 0.0")
        self._action_lbl = QLabel(tr('dash_idle'))
        self._target_lbl = QLabel(tr('dash_no_target'))
        _mfont = "font:600 11px 'SF Pro Display'"
        for lbl in (self._pan_speed_lbl, self._tilt_speed_lbl,
                    self._action_lbl, self._target_lbl):
            lbl.setStyleSheet(f"color:#8e8e93; {_mfont};")
            mh.addWidget(lbl)
        mh.addStretch()
        root.addWidget(metrics)

        # Update clock every second
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        from datetime import datetime
        self._time_lbl.setText(datetime.now().strftime("%H:%M:%S"))

    # ── Public API ──

    def set_pan(self, v):
        self.gauge_pan.set_value(v)

    def set_tilt(self, v):
        self.gauge_tilt.set_value(v)

    def set_laser_dist(self, v):
        self.gauge_laser.set_value(v)

    def set_temp(self, v):
        self.gauge_temp.set_value(v)

    def set_pan_speed(self, v):
        self._pan_speed_lbl.setText(f"PAN SPD: {v:.1f}")

    def set_tilt_speed(self, v):
        self._tilt_speed_lbl.setText(f"TILT SPD: {v:.1f}")

    def set_action(self, text, active=False):
        color = "#0a84ff" if active else "#8e8e93"
        self._action_lbl.setText(text)
        self._action_lbl.setStyleSheet(
            f"color:{color}; font:600 11px 'SF Pro Display';")

    def set_target(self, text):
        self._target_lbl.setText(text)

