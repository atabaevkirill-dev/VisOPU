"""Custom PyQt6 widgets for VisOPU application."""

import math
import threading
import time
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
                              QSizePolicy, QFrame, QPlainTextEdit)
from PyQt6.QtCore import (Qt, QTimer, QPointF, QRectF, pyqtSignal,
                           QPropertyAnimation, QEasingCurve)
from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush,
                          QRadialGradient, QPolygonF, QFont, QPainterPath,
                          QImage, QPixmap)

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


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
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background:#1c1c1e;")

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
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, w * ch, QImage.Format.Format_RGB888)
                with self._frame_lock:
                    self._pixmap = QPixmap.fromImage(qimg.copy())
                # Signal emits on main thread → triggers update()
                self._frame_ready.emit()
            else:
                time.sleep(0.01)

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
