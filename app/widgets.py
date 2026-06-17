"""Custom PyQt6 widgets for VisOPU application."""
from __future__ import annotations

import math
import threading
import time
from PyQt6 import sip
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
                              QSizePolicy, QFrame, QPlainTextEdit)
from PyQt6.QtCore import (Qt, QTimer, QPointF, QRectF, pyqtSignal,
                           QPropertyAnimation, QEasingCurve, QUrl)
from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush, QFontMetrics,
                          QRadialGradient, QPolygonF, QFont, QPainterPath,
                          QImage, QPixmap)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

from app.offline_map import MBTilesServer

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
            except Exception:
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
        p.drawText(frect, Qt.AlignmentFlag.AlignCenter, f"\u2699 {fname}")




class YandexMapWidget(QWidget):
    """Map widget (Leaflet + local MBTiles or OSM fallback) with beam visualization."""

    # Class-level server: shared across all instances, started once.
    _server: MBTilesServer | None = None
    _server_started = False

    @classmethod
    def _ensure_server(cls):
        """Start the local tile server once (idempotent)."""
        if not cls._server_started:
            import os
            mbtiles_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
            )
            cls._server = MBTilesServer(mbtiles_dir=mbtiles_dir)
            cls._server.start()
            cls._server_started = True
        return cls._server

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background:#1c1c1e;")
        self._last_pan = None
        self._last_pan_time = 0
        self._config_pending = None  # (lat, lng, offset, length) waiting for page load
        self._js_ready = False       # True once Leaflet + JS bridge are loaded
        self._js_queue: list[str] = []  # JS calls queued while page loads

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if HAS_WEBENGINE:
            srv = self._ensure_server()
            self._web = QWebEngineView(self)
            self._web.setStyleSheet("background:#1c1c1e;")
            self._web.loadFinished.connect(self._on_page_loaded)
            self._web.setUrl(QUrl(f"http://127.0.0.1:{srv.port}/"))
            layout.addWidget(self._web, 1)
        else:
            self._fallback = QLabel(self)
            self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._fallback.setText("Map requires PyQt6-WebEngine\npip install PyQt6-WebEngine")
            self._fallback.setStyleSheet(
                "color:#636366; font:600 14px 'SF Pro Display'; background:#1c1c1e;")
            layout.addWidget(self._fallback, 1)

    # ── Internal ──

    def _run_js(self, code: str):
        """Run JS immediately if page is ready, otherwise queue it."""
        if not HAS_WEBENGINE or not hasattr(self, '_web'):
            return
        if sip.isdeleted(self._web):
            return
        if self._js_ready:
            self._web.page().runJavaScript(code)
        else:
            self._js_queue.append(code)

    def _on_page_loaded(self, ok):
        """Page finished loading — flush JS queue."""
        if ok:
            self._js_ready = True
            # Flush queued JS calls in order
            for code in self._js_queue:
                self._web.page().runJavaScript(code)
            self._js_queue.clear()
            # Push saved config if pending
            if self._config_pending:
                lat, lng, offset, length, pan = self._config_pending
                self._web.page().runJavaScript(
                    f"pyApplyConfig({lat},{lng},{offset},{length},{pan})")
                self._config_pending = None

    # ── Public API (called from MainWindow) ──

    def set_pan_angle(self, degrees):
        """Update beam direction from PAN-TILT angle (throttled)."""
        if not HAS_WEBENGINE or not hasattr(self, '_web'):
            return
        now = time.monotonic()
        if self._last_pan is not None:
            if abs(degrees - self._last_pan) < 0.05 and (now - self._last_pan_time) < 0.05:
                return
        self._last_pan = degrees
        self._last_pan_time = now
        self._run_js(f"pySetPan({degrees})")

    def set_device_position(self, lat, lng):
        """Set device location on the map (lat/lng)."""
        self._run_js(f"pySetDevicePos({lat},{lng})")

    def set_beam_offset(self, degrees):
        """Set bearing offset added to PAN angle."""
        self._run_js(f"pySetBeamOffset({degrees})")

    def set_beam_length(self, meters):
        """Set beam ray length in meters."""
        self._run_js(f"pySetBeamLength({meters})")

    def apply_saved_config(self, lat, lng, offset, length, pan=0):
        """Apply saved config — queues it if page hasn't loaded yet."""
        self._config_pending = (lat, lng, offset, length, pan)
        # If page already loaded, push immediately
        self._run_js(f"pyApplyConfig({lat},{lng},{offset},{length},{pan})")

