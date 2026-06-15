"""Custom PyQt6 widgets for VisOPU application."""

import math
import threading
import time
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
                              QSizePolicy, QFrame, QPlainTextEdit)
from PyQt6.QtCore import (Qt, QTimer, QPointF, QRectF, pyqtSignal,
                           QPropertyAnimation, QEasingCurve)
from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush, QFontMetrics,
                          QRadialGradient, QPolygonF, QFont, QPainterPath,
                          QImage, QPixmap)

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from app.detector import YoloDetector, Detection, AIR_CLASSES


# ═══════════════════════════════════════════════════════════════════
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
# COMPASS / PAN-TILT VISUALIZATION
# ═══════════════════════════════════════════════════════════════════

class DeviceVisualization(QWidget):
    """Minimalist PAN-TILT compass with Apple Dark styling."""

    C_RING  = QColor(0x48, 0x48, 0x4A, 160)
    C_TICK  = QColor(0x8E, 0x8E, 0x93, 200)
    C_LABEL = QColor(0xF5, 0xF5, 0xF7, 230)
    C_ARROW = QColor(0x0A, 0x84, 0xFF)
    C_GLOW  = QColor(0x0A, 0x84, 0xFF, 35)
    C_CENTER= QColor(0x63, 0x63, 0x66, 160)
    C_DIM   = QColor(0x63, 0x63, 0x66)
    C_BG    = QColor(0x1C, 0x1C, 0x1E)

    def __init__(self):
        super().__init__()
        self.pan_angle = 0.0
        self.tilt_angle = 0.0
        self.target_pan = 0.0
        self.target_tilt = 0.0
        self.tilt_inverted = False
        self.display_tilt = 0.0
        self.setMinimumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(20)

    def set_angles(self, pan, tilt):
        self.target_pan = pan
        self.target_tilt = tilt

    def set_tilt_inverted(self, inv):
        self.tilt_inverted = inv
        self.update()

    def set_speeds(self, pan_spd, tilt_spd):
        pass

    def _tick(self):
        pan_diff = ((self.target_pan - self.pan_angle + 180) % 360) - 180
        self.pan_angle = (self.pan_angle + pan_diff * 0.12) % 360
        self.tilt_angle += (self.target_tilt - self.tilt_angle) * 0.12
        self.display_tilt += (self.tilt_angle - self.display_tilt) * 0.12
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.C_BG)

        w, h = self.width(), self.height()
        cx, cy = w // 2 - 20, h // 2
        R = min(w * 0.38, h * 0.34)

        self._draw_compass(p, cx, cy, R)
        bar_x = cx + R + 45
        bar_h = R * 2
        self._draw_tilt_bar(p, bar_x, cy - bar_h / 2, bar_h)
        self._draw_values(p, w)
        p.end()

    def _draw_compass(self, p, cx, cy, R):
        p.setPen(QPen(self.C_RING, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R + 4, R + 4)

        for deg in range(0, 360, 30):
            rad = math.radians(deg - 90)
            r1 = R - 6
            r2 = R + 4
            x1 = cx + r1 * math.cos(rad)
            y1 = cy + r1 * math.sin(rad)
            x2 = cx + r2 * math.cos(rad)
            y2 = cy + r2 * math.sin(rad)
            p.setPen(QPen(self.C_TICK, 1.5 if deg % 90 == 0 else 1))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        for deg, label in {0: "N", 90: "E", 180: "S", 270: "W"}.items():
            rad = math.radians(deg - 90)
            tx = cx + (R + 18) * math.cos(rad)
            ty = cy + (R + 18) * math.sin(rad)
            p.setFont(QFont("SF Pro Display", 10, QFont.Weight.Bold))
            p.setPen(self.C_LABEL)
            p.drawText(QRectF(tx - 10, ty - 8, 20, 16),
                       Qt.AlignmentFlag.AlignCenter, label)

        for deg in (60, 120, 240, 300):
            rad = math.radians(deg - 90)
            tx = cx + (R + 16) * math.cos(rad)
            ty = cy + (R + 16) * math.sin(rad)
            p.setFont(QFont("SF Pro Display", 7))
            p.setPen(self.C_DIM)
            p.drawText(QRectF(tx - 12, ty - 6, 24, 12),
                       Qt.AlignmentFlag.AlignCenter, str(deg))

        p.save()
        p.translate(cx, cy)
        p.rotate(self.pan_angle)

        p.setPen(QPen(self.C_RING, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(0, 0), R * 0.25, R * 0.25)

        p.setPen(QPen(self.C_ARROW, 2))
        p.drawLine(QPointF(0, -R * 0.25), QPointF(0, -R * 0.88))

        tri = QPolygonF([
            QPointF(0, -R * 0.95),
            QPointF(-6, -R * 0.80),
            QPointF(6, -R * 0.80),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.C_ARROW)
        p.drawPolygon(tri)

        p.drawEllipse(QPointF(0, 0), 3, 3)
        p.restore()

    def _draw_tilt_bar(self, p, bar_x, bar_y1, bar_h):
        bar_y2 = bar_y1 + bar_h
        p.setPen(QPen(self.C_DIM, 2))
        p.drawLine(QPointF(bar_x, bar_y1), QPointF(bar_x, bar_y2))

        for deg in (45, 0, -45, -90):
            norm = (45 - deg) / 135.0
            ty = bar_y1 + norm * bar_h
            p.setPen(QPen(self.C_RING, 1))
            p.drawLine(QPointF(bar_x - 6, ty), QPointF(bar_x + 6, ty))
            p.setFont(QFont("SF Pro Display", 7))
            p.setPen(self.C_DIM)
            label = f"+{deg}°" if deg > 0 else f"{deg}°"
            p.drawText(QRectF(bar_x + 10, ty - 5, 36, 10),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       label)

        zero_norm = 45.0 / 135.0
        zero_y = bar_y1 + zero_norm * bar_h
        p.setPen(QPen(self.C_LABEL, 1.5))
        p.drawLine(QPointF(bar_x - 8, zero_y), QPointF(bar_x + 8, zero_y))

        clamped = max(-90.0, min(45.0, self.display_tilt))
        tilt_norm = (45 - clamped) / 135.0
        my = bar_y1 + tilt_norm * bar_h
        my = max(bar_y1, min(bar_y2, my))

        diamond = QPolygonF([
            QPointF(bar_x, my - 6),
            QPointF(bar_x + 5, my),
            QPointF(bar_x, my + 6),
            QPointF(bar_x - 5, my),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.C_ARROW)
        p.drawPolygon(diamond)

    def _draw_values(self, p, w):
        p.setFont(QFont("SF Pro Display", 10, QFont.Weight.Bold))
        p.setPen(self.C_LABEL)
        p.drawText(10, 16, f"PAN {self.pan_angle:7.2f}°  TILT {self.tilt_angle:7.2f}°")


# ═══════════════════════════════════════════════════════════════════
# DIRECTION PAD (8 directions)
# ═══════════════════════════════════════════════════════════════════

class DirectionPad(QWidget):
    """8-direction D-Pad control widget with diagonals."""
    direction_pressed = pyqtSignal(str)
    direction_released = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setFixedSize(240, 240)
        self.pressed_dir = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = 120, 120

        bg = QRadialGradient(cx, cy, 120)
        bg.setColorAt(0, QColor(0x2D, 0x2D, 0x2D))
        bg.setColorAt(1, QColor(0x1C, 0x1C, 0x1E))
        p.setBrush(bg)
        p.setPen(QPen(QColor(0x48, 0x48, 0x4A), 1.5))
        p.drawEllipse(QPointF(cx, cy), 115, 115)

        cardinals = {
            'UP':    (cx, cy - 58, 0),
            'DOWN':  (cx, cy + 58, 180),
            'LEFT':  (cx - 58, cy, 270),
            'RIGHT': (cx + 58, cy, 90),
        }
        for d, (ax, ay, rot) in cardinals.items():
            pressed = self.pressed_dir == d
            color = QColor(0x0A, 0x84, 0xFF) if pressed else QColor(0x8E, 0x8E, 0x93, 200)
            p.save()
            p.translate(ax, ay)
            p.rotate(rot)
            tri = QPolygonF([
                QPointF(0, -14), QPointF(11, 7), QPointF(4, 4),
                QPointF(4, 14), QPointF(-4, 14), QPointF(-4, 4), QPointF(-11, 7),
            ])
            if pressed:
                g = QRadialGradient(0, 0, 18)
                g.setColorAt(0, QColor(0x0A, 0x84, 0xFF, 70))
                g.setColorAt(1, QColor(0x0A, 0x84, 0xFF, 0))
                p.setBrush(g)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(0, 0), 18, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPolygon(tri)
            p.restore()

        diag_dist = 44
        diag_dirs = {
            'UP_RIGHT':   (cx + diag_dist, cy - diag_dist, 45),
            'UP_LEFT':    (cx - diag_dist, cy - diag_dist, 315),
            'DOWN_RIGHT': (cx + diag_dist, cy + diag_dist, 135),
            'DOWN_LEFT':  (cx - diag_dist, cy + diag_dist, 225),
        }
        for d, (ax, ay, rot) in diag_dirs.items():
            pressed = self.pressed_dir == d
            color = QColor(0x40, 0x9C, 0xFF) if pressed else QColor(0x63, 0x63, 0x66, 160)
            p.save()
            p.translate(ax, ay)
            p.rotate(rot)
            tri = QPolygonF([
                QPointF(0, -10), QPointF(7, 4), QPointF(3, 2),
                QPointF(3, 10), QPointF(-3, 10), QPointF(-3, 2), QPointF(-7, 4),
            ])
            if pressed:
                g = QRadialGradient(0, 0, 14)
                g.setColorAt(0, QColor(0x0A, 0x84, 0xFF, 50))
                g.setColorAt(1, QColor(0x0A, 0x84, 0xFF, 0))
                p.setBrush(g)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(0, 0), 14, 14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPolygon(tri)
            p.restore()

        pressed_stop = self.pressed_dir == 'STOP'
        p.setPen(QPen(QColor(0x48, 0x48, 0x4A), 2))
        p.setBrush(QColor(0x0A, 0x84, 0xFF, 50) if pressed_stop else QColor(0x2D, 0x2D, 0x2D))
        p.drawEllipse(QPointF(cx, cy), 18, 18)
        p.setFont(QFont("SF Pro Display", 8, QFont.Weight.Bold))
        p.setPen(QColor(0x8E, 0x8E, 0x93))
        p.drawText(QRectF(cx - 18, cy - 7, 36, 14),
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
        cx, cy = 120, 120
        dx, dy = pos.x() - cx, pos.y() - cy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 20:
            return 'STOP'
        if dist > 115:
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
# SPEED CONTROL (Slider)
# ═══════════════════════════════════════════════════════════════════

class SpeedControl(QWidget):
    """Speed setting widget — stores value only, no movement triggered."""

    def __init__(self, label, min_val, max_val, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
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
        self.slider.setMinimum(int(min_val * 10))
        self.slider.setMaximum(int(max_val * 10))
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
        self.value_label.setText(f"{speed:>+.1f} °/s")

    def get_speed(self):
        return self.slider.value() / 10.0

    def reset(self):
        self.slider.blockSignals(True)
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.value_label.setText("0.0 °/s")


# ═══════════════════════════════════════════════════════════════════
# CAMERA WIDGET (RTSP stream + military reticles)
# ═══════════════════════════════════════════════════════════════════

class CameraWidget(QWidget):
    """IP camera stream viewer with military-style reticle overlays."""

    RETICLE_CROSSHAIR = 0
    RETICLE_MILDOT = 1
    RETICLE_COMBAT = 2

    _frame_ready = pyqtSignal()
    # Video overlay D-Pad signals
    video_dpad_pressed = pyqtSignal(str)
    video_dpad_released = pyqtSignal(str)
    # Zoom scroll: +1 = zoom in (tele), -1 = zoom out (wide)
    zoom_scroll = pyqtSignal(int)
    # Detection target: (dx_norm, dy_norm, class_name) — offset from center -1..1
    detection_target = pyqtSignal(float, float, str)
    # Detection list updated — emits list of Detection objects
    detections_updated = pyqtSignal(list)
    # FPS counter
    detection_fps = pyqtSignal(float)
    # Video overlay button signals
    video_laser_toggled = pyqtSignal(bool)
    video_detect_toggled = pyqtSignal(bool)
    video_track_toggled = pyqtSignal(bool)
    video_filter_changed = pyqtSignal(str)

    # D-Pad overlay constants
    _DPAD_R = 50           # D-Pad radius in pixels
    _DPAD_MARGIN = 16      # margin from corner
    _DPAD_STOP_R = 14      # center stop button radius
    # Detection frame-skip: run inference every N-th frame to keep video smooth
    _DET_SKIP_FRAMES = 4
    # Overlay action buttons (top-left)
    _OBTN_X = 12; _OBTN_Y = 12; _OBTN_W = 56; _OBTN_H = 24; _OBTN_GAP = 4
    # Video filter modes
    FILTER_NORMAL = 0; FILTER_NVG = 1; FILTER_EDGE = 2; FILTER_BW = 3
    _FILTER_NAMES = ('NORMAL', 'NVG', 'EDGE', 'BW')

    def __init__(self, name="CAM"):
        super().__init__()
        self.name = name
        self.cap = None
        self.streaming = False
        self._frame_lock = threading.Lock()
        self._pixmap = None
        self._thread = None
        self._running = False
        self.reticle_type = self.RETICLE_CROSSHAIR
        self.is_thermal = False
        # Laser rangefinder overlay
        self._laser_dist = None      # float meters or None
        self._laser_status = 0       # status byte
        self._laser_label = ""       # e.g. "TARGET", "NEAR", "OUT OF RANGE"
        self._laser_timestamp = 0.0  # last update time
        # Video overlay D-Pad state
        self._dpad_dir = None        # currently pressed direction or None
        self._dpad_hover = None      # currently hovered direction or None
        # YOLO detection state
        self._detector: YoloDetector = None
        self._detections: list = []     # latest Detection objects
        self._det_lock = threading.Lock()
        self._tracking_target_id = None  # track_id to follow, None = no target
        self._detect_active = False
        self._det_frame_count = 0
        self._det_fps_timer = time.time()
        self._det_fps = 0.0
        self._det_loop_count = 0        # frame counter for skip logic
        # Video overlay button state
        self._obtn_laser_on = False
        self._obtn_detect_on = False
        self._obtn_track_on = False
        self._obtn_hover = None   # 'LASER', 'DETECT', 'TRACK', 'FILTER' or None
        # Video filter mode
        self._video_filter = self.FILTER_NORMAL
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background:#1c1c1e;")
        self.setMouseTracking(True)  # Enable hover detection for D-Pad overlay

        # Thread-safe signal: background thread emits → main thread repaint
        self._frame_ready.connect(self.update)

        # Fallback repaint timer (ensures paint even when tab is hidden)
        self._repaint_timer = QTimer(self)
        self._repaint_timer.timeout.connect(self.update)
        self._repaint_timer.start(100)

    def connect_stream(self, rtsp_url, is_thermal=False):
        if not HAS_CV2:
            return False
        self.is_thermal = is_thermal
        self.disconnect_stream()
        try:
            self.cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not self.cap.isOpened():
                self.cap = None
                return False
            self._running = True
            self.streaming = True
            self._repaint_timer.setInterval(33)  # ~30fps repaint
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            return True
        except Exception:
            self.cap = None
            return False

    def disconnect_stream(self):
        self._running = False
        self.streaming = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None
        with self._frame_lock:
            self._pixmap = None
        self._repaint_timer.setInterval(100)
        self.update()

    def _read_loop(self):
        while self._running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # Run detection/tracking on every N-th frame to keep video smooth
                if self._detect_active and self._detector and self._detector.is_available:
                    self._det_loop_count += 1
                    if self._det_loop_count % self._DET_SKIP_FRAMES == 0:
                        try:
                            dets = self._detector.track(frame)
                            with self._det_lock:
                                self._detections = dets
                            # Emit target offset for auto-follow
                            self._emit_tracking_target(dets, frame.shape)
                            # FPS counter
                            self._det_frame_count += 1
                            now = time.time()
                            elapsed = now - self._det_fps_timer
                            if elapsed >= 1.0:
                                self._det_fps = self._det_frame_count / elapsed
                                self._det_frame_count = 0
                                self._det_fps_timer = now
                                self.detection_fps.emit(self._det_fps)
                            self.detections_updated.emit(dets)
                        except Exception:
                            pass
                # Always update video frame (never blocked by detection)
                filtered = self._apply_video_filter(frame)
                rgb = cv2.cvtColor(filtered, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, w * ch, QImage.Format.Format_RGB888)
                with self._frame_lock:
                    self._pixmap = QPixmap.fromImage(qimg.copy())
                # Signal emits on main thread → triggers update()
                self._frame_ready.emit()
            else:
                time.sleep(0.01)

    def _emit_tracking_target(self, dets: list, frame_shape):
        """Emit normalized offset of tracked target from frame center."""
        if self._tracking_target_id is None:
            return
        h, w = frame_shape[:2]
        cx, cy = w / 2.0, h / 2.0
        for d in dets:
            if d.track_id == self._tracking_target_id:
                tx, ty = d.center
                dx = (tx - cx) / cx  # -1..1
                dy = (ty - cy) / cy  # -1..1
                self.detection_target.emit(dx, dy, d.class_name)
                return
        # Target lost
        self.detection_target.emit(0.0, 0.0, "")

    def _apply_video_filter(self, frame):
        """Apply selected military video filter to frame. Returns filtered BGR frame.
        Optimized for real-time: in-place channel ops, no addWeighted, no full allocations."""
        mode = self._video_filter
        if mode == self.FILTER_NORMAL or not HAS_CV2:
            return frame
        try:
            if mode == self.FILTER_NVG:
                # Night vision: luminance → green channel, dim the rest
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frame[:, :, 1] = gray          # green = full luminance
                frame[:, :, 0] //= 4           # dim blue
                frame[:, :, 2] //= 4           # dim red
                return frame
            elif mode == self.FILTER_EDGE:
                # Tactical edge: Sobel gradient overlay (faster than Canny)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gx = cv2.Sobel(gray, cv2.CV_8U, 1, 0, ksize=3)
                gy = cv2.Sobel(gray, cv2.CV_8U, 0, 1, ksize=3)
                edges = cv2.add(gx, gy)
                # Blend edges into green channel for tactical look
                frame[:, :, 1] = cv2.add(frame[:, :, 1], edges // 2)
                return frame
            elif mode == self.FILTER_BW:
                # High-contrast B&W with histogram equalization
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                eq = cv2.equalizeHist(gray)
                frame[:, :, 0] = eq
                frame[:, :, 1] = eq
                frame[:, :, 2] = eq
                return frame
        except Exception:
            pass
        return frame


    # ── Detection control API ──

    def enable_detection(self, detector: YoloDetector):
        """Enable YOLO detection on this camera widget."""
        self._detector = detector
        self._detect_active = True
        self._det_frame_count = 0
        self._det_fps_timer = time.time()
        self._det_fps = 0.0

    def disable_detection(self):
        """Disable YOLO detection."""
        self._detect_active = False
        with self._det_lock:
            self._detections = []
        self._tracking_target_id = None
        self.update()

    def select_track_target(self, track_id):
        """Select a tracked object to follow. None to deselect."""
        self._tracking_target_id = track_id

    def get_tracked_targets(self) -> list:
        """Return current detections with track IDs."""
        with self._det_lock:
            return [d for d in self._detections if d.track_id is not None]

    def get_all_detections(self) -> list:
        """Return all current detections."""
        with self._det_lock:
            return list(self._detections)

    def is_detection_active(self) -> bool:
        return self._detect_active and self._detector is not None

    def get_detection_fps(self) -> float:
        return self._det_fps

    # ── Public sync API (called from MainWindow to keep overlay in sync) ──

    def set_detect_state(self, on: bool):
        """Sync DETECT overlay button state from external source."""
        self._obtn_detect_on = on
        self.update()

    def set_track_state(self, on: bool):
        """Sync TRACK overlay button state from external source."""
        self._obtn_track_on = on
        self.update()

    def set_laser_state(self, on: bool):
        """Sync LSR overlay button state from external source."""
        self._obtn_laser_on = on
        self.update()

    def set_video_filter(self, mode: int):
        """Set video filter mode (0=NORMAL, 1=NVG, 2=EDGE, 3=BW)."""
        self._video_filter = mode
        self.update()

    def set_reticle(self, rtype):
        self.reticle_type = rtype
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(0x1C, 0x1C, 0x1E))

        with self._frame_lock:
            pix = self._pixmap

        if pix and not pix.isNull():
            scaled = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        else:
            p.setPen(QColor(0x63, 0x63, 0x66))
            p.setFont(QFont("SF Pro Display", 14))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       f"{self.name}\nNo Stream")

        if self.streaming or pix:
            self._draw_reticle(p, w, h)
            self._draw_detections(p, w, h)
            self._draw_laser_hud(p, w, h)
            self._draw_video_dpad(p, w, h)
            self._draw_overlay_buttons(p, w, h)

        p.end()

    def _draw_reticle(self, p, w, h):
        cx, cy = w // 2, h // 2
        if self.reticle_type == self.RETICLE_CROSSHAIR:
            self._reticle_crosshair(p, cx, cy, w, h)
        elif self.reticle_type == self.RETICLE_MILDOT:
            self._reticle_mildot(p, cx, cy, w, h)
        elif self.reticle_type == self.RETICLE_COMBAT:
            self._reticle_combat(p, cx, cy, w, h)

    def _reticle_crosshair(self, p, cx, cy, w, h):
        pen = QPen(QColor(0x30, 0xD1, 0x58, 200), 1.5)
        p.setPen(pen)
        gap = 8
        p.drawLine(0, cy, cx - gap, cy)
        p.drawLine(cx + gap, cy, w, cy)
        p.drawLine(cx, 0, cx, cy - gap)
        p.drawLine(cx, cy + gap, cx, h)
        for dx in (60, 120, 180):
            p.drawLine(cx + dx, cy - 4, cx + dx, cy + 4)
            p.drawLine(cx - dx, cy - 4, cx - dx, cy + 4)
        for dy in (60, 120):
            p.drawLine(cx - 4, cy + dy, cx + 4, cy + dy)
            p.drawLine(cx - 4, cy - dy, cx + 4, cy - dy)

    def _reticle_mildot(self, p, cx, cy, w, h):
        pen = QPen(QColor(0xFF, 0xD6, 0x0A, 220), 1.2)
        p.setPen(pen)
        p.setBrush(QColor(0xFF, 0xD6, 0x0A, 220))
        p.drawEllipse(QPointF(cx, cy), 3, 3)
        for i in range(1, 11):
            dx = i * 28
            if cx + dx < w:
                p.drawEllipse(QPointF(cx + dx, cy), 2.5, 2.5)
            if cx - dx > 0:
                p.drawEllipse(QPointF(cx - dx, cy), 2.5, 2.5)
        for i in range(1, 8):
            dy = i * 28
            if cy + dy < h:
                p.drawEllipse(QPointF(cx, cy + dy), 2.5, 2.5)
            if cy - dy > 0:
                p.drawEllipse(QPointF(cx, cy - dy), 2.5, 2.5)
        p.setPen(QPen(QColor(0xFF, 0xD6, 0x0A, 80), 0.5))
        p.drawLine(0, cy, w, cy)
        p.drawLine(cx, 0, cx, h)

    def set_laser_distance(self, dist, status, label="TARGET"):
        """Update laser rangefinder overlay data."""
        self._laser_dist = dist
        self._laser_status = status
        self._laser_label = label
        self._laser_timestamp = time.time()
        self.update()

    def clear_laser_overlay(self):
        """Clear laser rangefinder overlay."""
        self._laser_dist = None
        self._laser_status = 0
        self._laser_label = ""
        self._laser_timestamp = 0.0
        self.update()

    def _draw_laser_hud(self, p, w, h):
        """Draw military-style laser distance HUD overlay near center."""
        if self._laser_dist is None:
            return

        cx, cy = w // 2, h // 2
        # Scale-aware sizing
        scale = min(w, h) / 600.0
        scale = max(0.6, min(scale, 1.8))

        # Colors
        green = QColor(0x30, 0xD1, 0x58, 220)
        green_dim = QColor(0x30, 0xD1, 0x58, 100)
        red = QColor(0xFF, 0x45, 0x3A, 220)
        white = QColor(0xF5, 0xF5, 0xF7, 230)
        bg = QColor(0x00, 0x00, 0x00, 120)

        is_error = (self._laser_status & 0x0F) == 0x04
        accent = red if is_error else green

        # Position: below and right of center crosshair
        off_x = int(55 * scale)
        off_y = int(28 * scale)

        # Distance text
        dist_text = f"{self._laser_dist:.1f}"
        unit_text = "m"
        label_text = self._laser_label

        font_dist = QFont("SF Pro Display", max(8, int(16 * scale)), QFont.Weight.Bold)
        font_unit = QFont("SF Pro Display", max(7, int(10 * scale)), QFont.Weight.Bold)
        font_label = QFont("SF Pro Display", max(6, int(8 * scale)), QFont.Weight.Bold)

        fm_dist = QFontMetrics(font_dist)
        fm_unit = QFontMetrics(font_unit)
        fm_label = QFontMetrics(font_label)

        dist_w = fm_dist.horizontalAdvance(dist_text)
        unit_w = fm_unit.horizontalAdvance(unit_text)
        label_w = fm_label.horizontalAdvance(label_text)

        total_w = dist_w + unit_w + int(8 * scale)
        block_w = max(total_w, label_w) + int(16 * scale)
        block_h = int(42 * scale)

        bx = cx + off_x
        by = cy + off_y

        # Semi-transparent background
        p.setBrush(bg)
        p.setPen(QPen(QColor(0x30, 0xD1, 0x58, 60 if not is_error else 0), 1))
        p.drawRoundedRect(bx - int(4 * scale), by, block_w, block_h, 3, 3)

        # Corner brackets (military HUD style)
        bracket_len = int(8 * scale)
        bracket_pen = QPen(accent, 1.5)
        p.setPen(bracket_pen)
        # Top-left
        p.drawLine(bx - int(4*scale), by, bx - int(4*scale) + bracket_len, by)
        p.drawLine(bx - int(4*scale), by, bx - int(4*scale), by + bracket_len)
        # Top-right
        tr_x = bx - int(4*scale) + block_w
        p.drawLine(tr_x, by, tr_x - bracket_len, by)
        p.drawLine(tr_x, by, tr_x, by + bracket_len)
        # Bottom-left
        bl_y = by + block_h
        p.drawLine(bx - int(4*scale), bl_y, bx - int(4*scale) + bracket_len, bl_y)
        p.drawLine(bx - int(4*scale), bl_y, bx - int(4*scale), bl_y - bracket_len)
        # Bottom-right
        p.drawLine(tr_x, bl_y, tr_x - bracket_len, bl_y)
        p.drawLine(tr_x, bl_y, tr_x, bl_y - bracket_len)

        # Connector line from crosshair to HUD block
        p.setPen(QPen(accent, 1))
        conn_start_x = cx + int(12 * scale)
        conn_end_x = bx - int(4 * scale)
        conn_y = cy + off_y + block_h // 2
        p.drawLine(conn_start_x, conn_y, conn_end_x, conn_y)

        # Small tick at connector start
        p.drawLine(conn_start_x, conn_y - int(4*scale), conn_start_x, conn_y + int(4*scale))

        # Distance value
        text_x = bx + int(4 * scale)
        p.setFont(font_dist)
        p.setPen(white)
        p.drawText(text_x, by + int(22 * scale), dist_text)

        # Unit
        p.setFont(font_unit)
        p.setPen(green_dim if not is_error else QColor(0xFF, 0x45, 0x3A, 140))
        p.drawText(text_x + dist_w + int(3 * scale), by + int(22 * scale), unit_text)

        # Label (TARGET, NEAR, OUT OF RANGE, etc.)
        p.setFont(font_label)
        p.setPen(accent)
        p.drawText(text_x, by + int(36 * scale), label_text)

    def _reticle_combat(self, p, cx, cy, w, h):
        col = QColor(0xFF, 0x45, 0x3A, 220)
        p.setPen(QPen(col, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 40, 40)
        p.drawEllipse(QPointF(cx, cy), 8, 8)
        bw, bh = 60, 40
        p.drawLine(cx - bw, cy - bh, cx - bw + 20, cy - bh)
        p.drawLine(cx - bw, cy - bh, cx - bw, cy - bh + 15)
        p.drawLine(cx + bw, cy - bh, cx + bw - 20, cy - bh)
        p.drawLine(cx + bw, cy - bh, cx + bw, cy - bh + 15)
        p.drawLine(cx - bw, cy + bh, cx - bw + 20, cy + bh)
        p.drawLine(cx - bw, cy + bh, cx - bw, cy + bh - 15)
        p.drawLine(cx + bw, cy + bh, cx + bw - 20, cy + bh)
        p.drawLine(cx + bw, cy + bh, cx + bw, cy + bh - 15)
        p.setPen(QPen(col, 1))
        gap = 12
        p.drawLine(0, cy, cx - gap, cy)
        p.drawLine(cx + gap, cy, w, cy)
        p.drawLine(cx, 0, cx, cy - gap)
        p.drawLine(cx, cy + gap, cx, h)
        for i, dy in enumerate((60, 80, 100)):
            spread = 12 + i * 4
            path = QPainterPath()
            path.moveTo(cx - spread, cy + dy)
            path.lineTo(cx, cy + dy + 6)
            path.lineTo(cx + spread, cy + dy)
            p.drawPath(path)

    # ════════════ DETECTION OVERLAY ════════════

    def _draw_detections(self, p, w, h):
        """Military-grade HUD: corner brackets, velocity vectors, threat rings."""
        with self._det_lock:
            dets = list(self._detections)
        if not dets:
            return

        # Video-to-widget coordinate transform
        with self._frame_lock:
            pix = self._pixmap
        if not pix or pix.isNull():
            return
        vid_w, vid_h = pix.width(), pix.height()
        scaled = min(w / vid_w, h / vid_h)
        off_x = (w - vid_w * scaled) / 2.0
        off_y = (h - vid_h * scaled) / 2.0

        # Reticle center for threat assessment
        rc_x, rc_y = w / 2.0, h / 2.0

        # Sort: tracked target drawn last (on top)
        dets_sorted = sorted(dets, key=lambda d: (d.track_id == self._tracking_target_id))

        for det in dets_sorted:
            x1, y1, x2, y2 = det.bbox
            wx1 = off_x + x1 * scaled
            wy1 = off_y + y1 * scaled
            wx2 = off_x + x2 * scaled
            wy2 = off_y + y2 * scaled
            bw, bh = wx2 - wx1, wy2 - wy1
            cx_d, cy_d = (wx1 + wx2) / 2, (wy1 + wy2) / 2

            is_tracked = (det.track_id == self._tracking_target_id)
            is_air = det.class_id in AIR_CLASSES

            # ── Threat assessment: distance from reticle center ──
            dist_center = ((cx_d - rc_x) ** 2 + (cy_d - rc_y) ** 2) ** 0.5
            max_dist = ((w / 2) ** 2 + (h / 2) ** 2) ** 0.5
            threat = 1.0 - min(dist_center / max_dist, 1.0)  # 0=far, 1=center

            # ── Color by priority ──
            if is_tracked:
                color = QColor(0x00, 0xFF, 0x88, 230)     # bright green — locked
            elif is_air:
                color = QColor(0xFF, 0x6B, 0x00, 220)     # red-orange — air threat
            elif threat > 0.7:
                color = QColor(0xFF, 0x44, 0x44, 200)     # red — near reticle center
            else:
                color = QColor(0xF5, 0xF5, 0xF7, 130)     # white — standard

            pen_w = 2.0 if is_tracked else 1.2

            # ── Military corner brackets (no full rectangle) ──
            b_len = max(6, min(18, min(bw, bh) * 0.18))
            pen = QPen(color, pen_w)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            # Top-left
            p.drawLine(QPointF(wx1, wy1), QPointF(wx1 + b_len, wy1))
            p.drawLine(QPointF(wx1, wy1), QPointF(wx1, wy1 + b_len))
            # Top-right
            p.drawLine(QPointF(wx2, wy1), QPointF(wx2 - b_len, wy1))
            p.drawLine(QPointF(wx2, wy1), QPointF(wx2, wy1 + b_len))
            # Bottom-left
            p.drawLine(QPointF(wx1, wy2), QPointF(wx1 + b_len, wy2))
            p.drawLine(QPointF(wx1, wy2), QPointF(wx1, wy2 - b_len))
            # Bottom-right
            p.drawLine(QPointF(wx2, wy2), QPointF(wx2 - b_len, wy2))
            p.drawLine(QPointF(wx2, wy2), QPointF(wx2, wy2 - b_len))

            # ── Tracked target enhancements ──
            if is_tracked:
                # Tracking ring (dashed circle around target)
                ring_r = max(bw, bh) * 0.65
                p.setPen(QPen(QColor(0x00, 0xFF, 0x88, 100), 1.0, Qt.PenStyle.DashLine))
                p.drawEllipse(QPointF(cx_d, cy_d), ring_r, ring_r)

                # Velocity vector (arrow showing movement direction)
                speed = det.speed
                if speed > 1.5:  # only draw if meaningful movement
                    v_scale = min(40, speed * 5)  # cap arrow length
                    vx_n = det.vx / speed * v_scale
                    vy_n = det.vy / speed * v_scale
                    ax, ay = cx_d + vx_n, cy_d + vy_n
                    p.setPen(QPen(QColor(0x00, 0xFF, 0x88, 180), 2.0))
                    p.drawLine(QPointF(cx_d, cy_d), QPointF(ax, ay))
                    # Arrow head
                    angle = math.atan2(vy_n, vx_n)
                    ah = 6  # arrow head length
                    p.drawLine(QPointF(ax, ay),
                              QPointF(ax - ah * math.cos(angle - 0.4),
                                      ay - ah * math.sin(angle - 0.4)))
                    p.drawLine(QPointF(ax, ay),
                              QPointF(ax - ah * math.cos(angle + 0.4),
                                      ay - ah * math.sin(angle + 0.4)))

                # Center diamond marker
                d_size = 3
                p.setPen(QPen(QColor(0x00, 0xFF, 0x88, 255), 1.5))
                diamond = QPolygonF([
                    QPointF(cx_d, cy_d - d_size),
                    QPointF(cx_d + d_size, cy_d),
                    QPointF(cx_d, cy_d + d_size),
                    QPointF(cx_d - d_size, cy_d),
                    QPointF(cx_d, cy_d - d_size),
                ])
                p.drawPolyline(diamond)

            # ── Air target designator (pulsing ring) ──
            elif is_air and det.confidence >= 0.5:
                pulse = 0.7 + 0.3 * math.sin(time.monotonic() * 4)
                ring_r = max(bw, bh) * 0.55
                p.setPen(QPen(QColor(0xFF, 0x6B, 0x00, int(120 * pulse)), 1.5))
                p.drawEllipse(QPointF(cx_d, cy_d), ring_r, ring_r)

            # ── Label ──
            parts = []
            if det.track_id is not None:
                parts.append(f"T{det.track_id}")
            parts.append(det.class_name.upper())
            parts.append(f"{det.confidence:.0%}")
            if is_tracked and det.speed > 1.5:
                parts.append(f"{det.speed:.0f}px/f")
            label = " ".join(parts)

            font_size = max(7, int(8 * min(w, h) / 600))
            font = QFont("SF Pro Display", font_size, QFont.Weight.Bold)
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(label) + 8
            th = fm.height() + 3

            lx = wx1
            ly = max(0, wy1 - th - 2)
            p.setBrush(QColor(0x00, 0x00, 0x00, 170))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(lx, ly, tw, th))

            p.setFont(font)
            p.setPen(color)
            p.drawText(QRectF(lx + 4, ly, tw - 4, th),
                       Qt.AlignmentFlag.AlignVCenter, label)

    # ════════════ VIDEO OVERLAY D-PAD ════════════

    def _dpad_center(self):
        """Return (cx, cy) center of the D-Pad overlay in widget coords."""
        w, h = self.width(), self.height()
        cx = w - self._DPAD_R - self._DPAD_MARGIN
        cy = h - self._DPAD_R - self._DPAD_MARGIN
        return cx, cy

    def _dpad_hit_test(self, pos):
        """Return direction string for position, or None if outside D-Pad."""
        cx, cy = self._dpad_center()
        dx, dy = pos.x() - cx, pos.y() - cy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > self._DPAD_R:
            return None
        if dist <= self._DPAD_STOP_R:
            return 'STOP'
        # Angle from center (0 = right, 90 = down in screen coords)
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

    def mousePressEvent(self, event):
        if not self.streaming:
            return super().mousePressEvent(event)
        pos = event.position()
        w = self.width()
        # Priority 1: overlay buttons (top-left)
        btn = self._obtn_hit_test(pos, w)
        if btn == 'LSR':
            self._obtn_laser_on = not self._obtn_laser_on
            self.video_laser_toggled.emit(self._obtn_laser_on)
            self.update()
            return
        elif btn == 'DET':
            self._obtn_detect_on = not self._obtn_detect_on
            self.video_detect_toggled.emit(self._obtn_detect_on)
            self.update()
            return
        elif btn == 'TRACK':
            self._obtn_track_on = not self._obtn_track_on
            self.video_track_toggled.emit(self._obtn_track_on)
            self.update()
            return
        elif btn == 'FILTER':
            # Cycle filter: NORMAL -> NVG -> EDGE -> BW -> NORMAL
            self._video_filter = (self._video_filter + 1) % len(self._FILTER_NAMES)
            self.video_filter_changed.emit(self._FILTER_NAMES[self._video_filter])
            self.update()
            return
        # Priority 2: D-Pad (bottom-right)
        d = self._dpad_hit_test(pos)
        if d:
            self._dpad_dir = d
            self.video_dpad_pressed.emit(d)
            self.update()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dpad_dir:
            released = self._dpad_dir
            self._dpad_dir = None
            self.video_dpad_released.emit(released)
            self.update()
        else:
            super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        old_hover = self._dpad_hover
        self._dpad_hover = self._dpad_hit_test(event.position())
        if self._dpad_hover != old_hover:
            self.update()
        # Overlay button hover
        w = self.width()
        old_obtn = self._obtn_hover
        self._obtn_hover = self._obtn_hit_test(event.position(), w)
        if self._obtn_hover != old_obtn:
            self.update()
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_scroll.emit(1)   # scroll up → zoom in (tele)
        elif delta < 0:
            self.zoom_scroll.emit(-1)  # scroll down → zoom out (wide)

    def _draw_video_dpad(self, p, w, h):
        """Draw semi-transparent D-Pad overlay in bottom-right corner of video."""
        cx, cy = self._dpad_center()
        R = self._DPAD_R
        sr = self._DPAD_STOP_R

        # ── Base circle (semi-transparent background) ──
        bg = QRadialGradient(cx, cy, R)
        bg.setColorAt(0, QColor(0x1C, 0x1C, 0x1E, 140))
        bg.setColorAt(1, QColor(0x00, 0x00, 0x00, 100))
        p.setBrush(bg)
        p.setPen(QPen(QColor(0x48, 0x48, 0x4A, 120), 1.5))
        p.drawEllipse(QPointF(cx, cy), R, R)

        # ── Direction arrows ──
        arrow_defs = {
            'UP':    (cx, cy - 28, 0),
            'DOWN':  (cx, cy + 28, 180),
            'LEFT':  (cx - 28, cy, 270),
            'RIGHT': (cx + 28, cy, 90),
        }
        for d, (ax, ay, rot) in arrow_defs.items():
            active = (self._dpad_dir == d)
            hover = (self._dpad_hover == d)
            if active:
                col = QColor(0x0A, 0x84, 0xFF, 200)
            elif hover:
                col = QColor(0xF5, 0xF5, 0xF7, 180)
            else:
                col = QColor(0x8E, 0x8E, 0x93, 160)
            p.save()
            p.translate(ax, ay)
            p.rotate(rot)
            tri = QPolygonF([
                QPointF(0, -8), QPointF(7, 4), QPointF(2, 2),
                QPointF(2, 8), QPointF(-2, 8), QPointF(-2, 2), QPointF(-7, 4),
            ])
            if active:
                g = QRadialGradient(0, 0, 12)
                g.setColorAt(0, QColor(0x0A, 0x84, 0xFF, 50))
                g.setColorAt(1, QColor(0x0A, 0x84, 0xFF, 0))
                p.setBrush(g)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(0, 0), 12, 12)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawPolygon(tri)
            p.restore()

        # ── Diagonal arrows (smaller, dimmer) ──
        diag_dist = 22
        diag_defs = {
            'UP_RIGHT':   (cx + diag_dist, cy - diag_dist, 45),
            'UP_LEFT':    (cx - diag_dist, cy - diag_dist, 315),
            'DOWN_RIGHT': (cx + diag_dist, cy + diag_dist, 135),
            'DOWN_LEFT':  (cx - diag_dist, cy + diag_dist, 225),
        }
        for d, (ax, ay, rot) in diag_defs.items():
            active = (self._dpad_dir == d)
            hover = (self._dpad_hover == d)
            if active:
                col = QColor(0x40, 0x9C, 0xFF, 180)
            elif hover:
                col = QColor(0xF5, 0xF5, 0xF7, 140)
            else:
                col = QColor(0x63, 0x63, 0x66, 120)
            p.save()
            p.translate(ax, ay)
            p.rotate(rot)
            tri = QPolygonF([
                QPointF(0, -6), QPointF(5, 3), QPointF(2, 1),
                QPointF(2, 6), QPointF(-2, 6), QPointF(-2, 1), QPointF(-5, 3),
            ])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawPolygon(tri)
            p.restore()

        # ── Center STOP button ──
        stop_active = (self._dpad_dir == 'STOP')
        stop_hover = (self._dpad_hover == 'STOP')
        if stop_active:
            stop_bg = QColor(0xFF, 0x45, 0x3A, 60)
        elif stop_hover:
            stop_bg = QColor(0x2D, 0x2D, 0x2D, 140)
        else:
            stop_bg = QColor(0x2D, 0x2D, 0x2D, 100)
        p.setBrush(stop_bg)
        p.setPen(QPen(QColor(0x48, 0x48, 0x4A, 120), 1))
        p.drawEllipse(QPointF(cx, cy), sr, sr)
        p.setFont(QFont("SF Pro Display", 7, QFont.Weight.Bold))
        p.setPen(QColor(0x8E, 0x8E, 0x93, 180))
        p.drawText(QRectF(cx - sr, cy - 5, sr * 2, 10),
                   Qt.AlignmentFlag.AlignCenter, "STOP")

    # ════════════ OVERLAY ACTION BUTTONS ════════════

    def _obtn_rects(self):
        """Return list of (label, QRectF, is_on) for overlay buttons."""
        x, y, bw, bh, gap = self._OBTN_X, self._OBTN_Y, self._OBTN_W, self._OBTN_H, self._OBTN_GAP
        return [
            ('LSR',    QRectF(x, y, bw, bh),             self._obtn_laser_on),
            ('DET',    QRectF(x, y + bh + gap, bw, bh),  self._obtn_detect_on),
            ('TRACK',  QRectF(x, y + 2*(bh+gap), bw, bh), self._obtn_track_on),
        ]

    def _filter_label_rect(self, w):
        """Return QRectF for filter label in top-right corner."""
        name = self._FILTER_NAMES[self._video_filter]
        fw = max(60, len(name) * 9 + 16)
        return QRectF(w - fw - self._OBTN_X, self._OBTN_Y, fw, self._OBTN_H)

    def _obtn_hit_test(self, pos, w):
        """Return button key or 'FILTER' or None for given position."""
        for label, rect, _ in self._obtn_rects():
            if rect.contains(pos):
                return label
        if self._filter_label_rect(w).contains(pos):
            return 'FILTER'
        return None

    def _draw_overlay_buttons(self, p, w, h):
        """Draw semi-transparent overlay buttons (LSR, DET, TRACK) top-left and filter label top-right."""
        # Button definitions: (label, rect, is_on, active_color)
        btn_defs = [
            ('LSR',   None, self._obtn_laser_on,  QColor(0xFF, 0x45, 0x3A)),
            ('DET',   None, self._obtn_detect_on, QColor(0x30, 0xD1, 0x58)),
            ('TRACK', None, self._obtn_track_on,  QColor(0xFF, 0x9F, 0x0A)),
        ]
        font = QFont("SF Pro Display", 8, QFont.Weight.Bold)
        p.setFont(font)
        fm = QFontMetrics(font)

        x, y, bw, bh, gap = self._OBTN_X, self._OBTN_Y, self._OBTN_W, self._OBTN_H, self._OBTN_GAP
        for i, (label, _, is_on, accent) in enumerate(btn_defs):
            rect = QRectF(x, y + i * (bh + gap), bw, bh)
            hovered = (self._obtn_hover == label)

            # Background
            if is_on:
                bg = QColor(accent.red(), accent.green(), accent.blue(), 60)
                border = QColor(accent.red(), accent.green(), accent.blue(), 180)
            elif hovered:
                bg = QColor(0x2D, 0x2D, 0x2D, 180)
                border = QColor(0x8E, 0x8E, 0x93, 160)
            else:
                bg = QColor(0x1C, 0x1C, 0x1E, 160)
                border = QColor(0x48, 0x48, 0x4A, 120)

            p.setBrush(bg)
            p.setPen(QPen(border, 1))
            p.drawRoundedRect(rect, 4, 4)

            # Label
            if is_on:
                p.setPen(accent)
            elif hovered:
                p.setPen(QColor(0xF5, 0xF5, 0xF7, 220))
            else:
                p.setPen(QColor(0x8E, 0x8E, 0x93, 180))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

        # Filter label (top-right)
        fname = self._FILTER_NAMES[self._video_filter]
        frect = self._filter_label_rect(w)
        f_hovered = (self._obtn_hover == 'FILTER')
        f_bg = QColor(0x2D, 0x2D, 0x2D, 180) if f_hovered else QColor(0x1C, 0x1C, 0x1E, 160)
        f_border = QColor(0x8E, 0x8E, 0x93, 160) if f_hovered else QColor(0x48, 0x48, 0x4A, 120)
        p.setBrush(f_bg)
        p.setPen(QPen(f_border, 1))
        p.drawRoundedRect(frect, 4, 4)
        f_pen = QColor(0xF5, 0xF5, 0xF7, 220) if f_hovered else QColor(0x8E, 0x8E, 0x93, 180)
        p.setPen(f_pen)
        p.drawText(frect, Qt.AlignmentFlag.AlignCenter, f"⚙ {fname}")

