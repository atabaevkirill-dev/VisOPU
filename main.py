import sys
import math
import socket
import threading
import time
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                              QHBoxLayout, QPushButton, QLabel, QFrame,
                              QGridLayout, QSpinBox, QDoubleSpinBox,
                              QLineEdit, QSlider, QSizePolicy, QCheckBox,
                              QPlainTextEdit)
from PyQt6.QtCore import (Qt, QTimer, QPointF, QRectF, pyqtSignal, QObject,
                           QPropertyAnimation, QEasingCurve)
from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush,
                          QLinearGradient, QRadialGradient, QConicalGradient,
                          QPolygonF, QFont, QPainterPath)


class DeviceCommunicator(QObject):
    """Handles TCP communication with the TL.0009 device."""
    pan_position_updated = pyqtSignal(float)
    tilt_position_updated = pyqtSignal(float)
    pan_speed_updated = pyqtSignal(float)
    tilt_speed_updated = pyqtSignal(float)
    temperature_updated = pyqtSignal(float)
    connection_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.socket = None
        self.connected = False
        self.polling = False
        self.poll_thread = None
        self._lock = threading.Lock()

    def connect_device(self, ip, port):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(3)
            self.socket.connect((ip, port))
            self.connected = True
            self.connection_changed.emit(True)
            self.start_polling()
        except Exception as e:
            self.error_occurred.emit(str(e))
            self.connected = False
            self.connection_changed.emit(False)

    def disconnect_device(self):
        self.stop_polling()
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.connected = False
        self.connection_changed.emit(False)

    def send_command(self, cmd):
        with self._lock:
            if not self.connected or not self.socket:
                return None
            try:
                self.socket.sendall((cmd + "\n").encode())
                data = self.socket.recv(1024).decode().strip()
                self.log_message.emit(f">> {cmd}  << {data}")
                return data
            except Exception as e:
                self.error_occurred.emit(str(e))
                self.connected = False
                self.connection_changed.emit(False)
                return None

    def start_polling(self):
        self.polling = True
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def stop_polling(self):
        self.polling = False
        if self.poll_thread:
            self.poll_thread.join(timeout=2)

    def _poll_loop(self):
        while self.polling and self.connected:
            try:
                resp = self.send_command("$o#")
                if resp and resp.startswith("$o,"):
                    val = float(resp.split(",")[1].rstrip("#"))
                    self.pan_position_updated.emit(val)

                resp = self.send_command("$O#")
                if resp and resp.startswith("$O,"):
                    val = float(resp.split(",")[1].rstrip("#"))
                    self.tilt_position_updated.emit(val)

                resp = self.send_command("$p#")
                if resp and resp.startswith("$p,"):
                    val = float(resp.split(",")[1].rstrip("#"))
                    self.pan_speed_updated.emit(val)

                resp = self.send_command("$P#")
                if resp and resp.startswith("$P,"):
                    val = float(resp.split(",")[1].rstrip("#"))
                    self.tilt_speed_updated.emit(val)

                resp = self.send_command("$t#")
                if resp and resp.startswith("$t,"):
                    val = float(resp.split(",")[1].rstrip("#"))
                    self.temperature_updated.emit(val)
            except:
                pass
            time.sleep(0.25)

    def pan_set_speed(self, speed):
        self.send_command(f"$w,{speed:.2f}#")

    def tilt_set_speed(self, speed):
        self.send_command(f"$W,{speed:.2f}#")

    def pan_goto(self, pos, speed=None):
        if speed:
            self.send_command(f"$x,{pos:.2f},{speed:.2f}#")
        else:
            self.send_command(f"$x,{pos:.2f}#")

    def tilt_goto(self, pos, speed=None):
        if speed:
            self.send_command(f"$X,{pos:.2f},{speed:.2f}#")
        else:
            self.send_command(f"$X,{pos:.2f}#")

    def pan_stop(self):
        self.send_command("$u#")

    def tilt_stop(self):
        self.send_command("$U#")

    def pan_diag(self):
        """Start PAN axis self-diagnostics."""
        self.send_command("$m,1#")

    def tilt_diag(self):
        """Start TILT axis self-diagnostics."""
        self.send_command("$M,1#")

    def stop_all(self):
        self.pan_stop()
        self.tilt_stop()


class CollapsiblePanel(QFrame):
    """Panel with clickable header that collapses/expands content like a shutter."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.collapsed = False
        self.setStyleSheet("""
            CollapsiblePanel{background:rgba(10,10,10,230);
                border:1px solid #333333;border-radius:8px;}
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
        self._cl.setContentsMargins(8, 4, 8, 8)
        self._cl.setSpacing(4)
        main.addWidget(self._content)

        # Animation
        self._anim = QPropertyAnimation(self._content, b'maximumHeight')
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

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
    """Clickable header for CollapsiblePanel."""
    clicked = pyqtSignal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title = title
        self._arrow = True  # True = pointing down (expanded)

    def set_arrow(self, expanded):
        self._arrow = expanded
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Hover background
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Arrow
        arrow = "▾" if self._arrow else "▸"
        p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        p.setPen(QColor(200, 200, 200, 200))
        p.drawText(10, 18, arrow)
        # Title
        p.setPen(QColor(180, 180, 180, 180))
        p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        p.drawText(26, 18, self._title)
        # Bottom line
        p.setPen(QPen(QColor(60, 60, 60), 1))
        p.drawLine(0, 27, self.width(), 27)
        p.end()


class DeviceVisualization(QWidget):
    """Minimalist monochrome PAN-TILT compass."""

    # Color palette — pure black & white
    C_RING  = QColor(80, 80, 80, 100)
    C_TICK  = QColor(160, 160, 160, 160)
    C_LABEL = QColor(200, 200, 200, 200)
    C_ARROW = QColor(255, 255, 255)
    C_GLOW  = QColor(255, 255, 255, 40)
    C_CENTER= QColor(200, 200, 200, 120)
    C_DIM   = QColor(80, 80, 80)
    C_BG    = QColor(0, 0, 0)

    def __init__(self):
        super().__init__()
        self.pan_angle = 0.0
        self.tilt_angle = 0.0
        self.target_pan = 0.0
        self.target_tilt = 0.0
        self.tilt_inverted = False
        self.display_tilt = 0.0  # smoothed display value (handles inversion seamlessly)
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
        # Shortest angular path for PAN (handles 360°/0° wrapping)
        pan_diff = ((self.target_pan - self.pan_angle + 180) % 360) - 180
        self.pan_angle = (self.pan_angle + pan_diff * 0.12) % 360
        # TILT: smooth raw value
        self.tilt_angle += (self.target_tilt - self.tilt_angle) * 0.12
        # Display tilt tracks raw value directly (D-Pad is already intuitive)
        # Smooth display value for seamless transitions
        self.display_tilt += (self.tilt_angle - self.display_tilt) * 0.12
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.C_BG)

        w, h = self.width(), self.height()
        # Shift compass left to make room for vertical TILT bar
        cx, cy = w // 2 - 20, h // 2
        R = min(w * 0.38, h * 0.34)

        self._draw_compass(p, cx, cy, R)
        # Vertical TILT bar to the right of compass
        bar_x = cx + R + 45
        bar_h = R * 2
        self._draw_tilt_bar(p, bar_x, cy - bar_h / 2, bar_h)
        self._draw_values(p, w)
        p.end()

    def _draw_compass(self, p, cx, cy, R):
        # Thin outer ring
        p.setPen(QPen(self.C_RING, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R + 4, R + 4)

        # Tick marks every 30°
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

        # Cardinal labels — all same cyan color
        for deg, label in {0: "N", 90: "E", 180: "S", 270: "W"}.items():
            rad = math.radians(deg - 90)
            tx = cx + (R + 18) * math.cos(rad)
            ty = cy + (R + 18) * math.sin(rad)
            p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            p.setPen(self.C_LABEL)
            p.drawText(QRectF(tx - 10, ty - 8, 20, 16),
                       Qt.AlignmentFlag.AlignCenter, label)

        # Degree numbers every 60° (skip cardinals)
        for deg in (60, 120, 240, 300):
            rad = math.radians(deg - 90)
            tx = cx + (R + 16) * math.cos(rad)
            ty = cy + (R + 16) * math.sin(rad)
            p.setFont(QFont("Consolas", 7))
            p.setPen(self.C_DIM)
            p.drawText(QRectF(tx - 12, ty - 6, 24, 12),
                       Qt.AlignmentFlag.AlignCenter, str(deg))

        # Rotating arrow (simple line + triangle)
        p.save()
        p.translate(cx, cy)
        p.rotate(self.pan_angle)

        # Inner circle
        p.setPen(QPen(self.C_RING, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(0, 0), R * 0.25, R * 0.25)

        # Arrow line from center to edge
        p.setPen(QPen(self.C_ARROW, 2))
        p.drawLine(QPointF(0, -R * 0.25), QPointF(0, -R * 0.88))

        # Arrowhead
        tri = QPolygonF([
            QPointF(0, -R * 0.95),
            QPointF(-6, -R * 0.80),
            QPointF(6, -R * 0.80),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.C_ARROW)
        p.drawPolygon(tri)

        # Small dot at center
        p.drawEllipse(QPointF(0, 0), 3, 3)
        p.restore()

    def _draw_tilt_bar(self, p, bar_x, bar_y1, bar_h):
        """Vertical TILT bar: top = +45°, bottom = -90°, 0° marked."""
        bar_y2 = bar_y1 + bar_h

        # Track line
        p.setPen(QPen(self.C_DIM, 2))
        p.drawLine(QPointF(bar_x, bar_y1), QPointF(bar_x, bar_y2))

        # Tick marks at key angles
        for deg in (45, 0, -45, -90):
            norm = (45 - deg) / 135.0
            ty = bar_y1 + norm * bar_h
            p.setPen(QPen(self.C_RING, 1))
            p.drawLine(QPointF(bar_x - 6, ty), QPointF(bar_x + 6, ty))
            p.setFont(QFont("Consolas", 7))
            p.setPen(self.C_DIM)
            label = f"+{deg}°" if deg > 0 else f"{deg}°"
            p.drawText(QRectF(bar_x + 10, ty - 5, 36, 10),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       label)

        # 0° reference mark (more prominent)
        zero_norm = 45.0 / 135.0
        zero_y = bar_y1 + zero_norm * bar_h
        p.setPen(QPen(self.C_LABEL, 1.5))
        p.drawLine(QPointF(bar_x - 8, zero_y), QPointF(bar_x + 8, zero_y))

        # TILT marker: use smoothed display_tilt mapped to bar range
        clamped = max(-90.0, min(45.0, self.display_tilt))
        tilt_norm = (45 - clamped) / 135.0
        my = bar_y1 + tilt_norm * bar_h
        my = max(bar_y1, min(bar_y2, my))

        # Marker diamond
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
        # Compact value readout at top
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        p.setPen(self.C_LABEL)
        p.drawText(10, 16, f"PAN {self.pan_angle:7.2f}°  TILT {self.tilt_angle:7.2f}°")


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

        # Background
        bg = QRadialGradient(cx, cy, 120)
        bg.setColorAt(0, QColor(20, 20, 20))
        bg.setColorAt(1, QColor(5, 5, 5))
        p.setBrush(bg)
        p.setPen(QPen(QColor(60, 60, 60), 2))
        p.drawEllipse(QPointF(cx, cy), 115, 115)

        # Cardinal arrows (4 main directions)
        cardinals = {
            'UP':    (cx, cy - 58, 0),
            'DOWN':  (cx, cy + 58, 180),
            'LEFT':  (cx - 58, cy, 270),
            'RIGHT': (cx + 58, cy, 90),
        }
        for d, (ax, ay, rot) in cardinals.items():
            pressed = self.pressed_dir == d
            color = QColor(255, 255, 255) if pressed else QColor(180, 180, 180, 180)
            p.save()
            p.translate(ax, ay)
            p.rotate(rot)
            tri = QPolygonF([
                QPointF(0, -14), QPointF(11, 7), QPointF(4, 4),
                QPointF(4, 14), QPointF(-4, 14), QPointF(-4, 4), QPointF(-11, 7),
            ])
            if pressed:
                g = QRadialGradient(0, 0, 18)
                g.setColorAt(0, QColor(255, 255, 255, 60))
                g.setColorAt(1, QColor(255, 255, 255, 0))
                p.setBrush(g)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(0, 0), 18, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPolygon(tri)
            p.restore()

        # Diagonal arrows (4 corners) — smaller
        diag_dist = 44
        diag_dirs = {
            'UP_RIGHT':   (cx + diag_dist, cy - diag_dist, 45),
            'UP_LEFT':    (cx - diag_dist, cy - diag_dist, 315),
            'DOWN_RIGHT': (cx + diag_dist, cy + diag_dist, 135),
            'DOWN_LEFT':  (cx - diag_dist, cy + diag_dist, 225),
        }
        for d, (ax, ay, rot) in diag_dirs.items():
            pressed = self.pressed_dir == d
            color = QColor(220, 220, 220) if pressed else QColor(120, 120, 120, 140)
            p.save()
            p.translate(ax, ay)
            p.rotate(rot)
            tri = QPolygonF([
                QPointF(0, -10), QPointF(7, 4), QPointF(3, 2),
                QPointF(3, 10), QPointF(-3, 10), QPointF(-3, 2), QPointF(-7, 4),
            ])
            if pressed:
                g = QRadialGradient(0, 0, 14)
                g.setColorAt(0, QColor(255, 255, 255, 50))
                g.setColorAt(1, QColor(255, 255, 255, 0))
                p.setBrush(g)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(0, 0), 14, 14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPolygon(tri)
            p.restore()

        # Center STOP
        pressed_stop = self.pressed_dir == 'STOP'
        p.setPen(QPen(QColor(160, 160, 160, 220 if pressed_stop else 140), 2))
        p.setBrush(QColor(40, 40, 40) if pressed_stop else QColor(20, 20, 20))
        p.drawEllipse(QPointF(cx, cy), 18, 18)
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.setPen(QColor(180, 180, 180))
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
        # Angle in degrees, 0=right, positive=up (screen y is inverted)
        angle = math.degrees(math.atan2(-dy, dx))  # -180..180
        # Normalize to 0..360
        if angle < 0:
            angle += 360
        # 8 sectors of 45° each, centered on their direction
        # RIGHT: 337.5..22.5, UP_RIGHT: 22.5..67.5, UP: 67.5..112.5, etc.
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


class SpeedControl(QWidget):
    """Speed setting widget — stores value only, no movement triggered."""

    def __init__(self, label, min_val, max_val, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        layout = QVBoxLayout()
        layout.setSpacing(2)

        self.title = QLabel(label)
        self.title.setStyleSheet("color: #aaaaaa; font: bold 10px Consolas;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_label = QLabel("0.0 °/s")
        self.value_label.setStyleSheet("color: #ffffff; font: bold 12px Consolas;")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(int(min_val * 10))
        self.slider.setMaximum(int(max_val * 10))
        self.slider.setValue(0)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #222222, stop:0.5 #111111, stop:1 #222222);
                height: 5px; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff; width: 12px; height: 12px;
                margin: -4px 0; border-radius: 6px;
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TL.0009 ОПУ — ТехЛазер")
        self.setMinimumSize(400, 300)
        self.resize(1150, 700)

        self.comm = DeviceCommunicator()
        self.is_connected = False

        # Real device state (from polling)
        self.real_pan = 0.0
        self.real_tilt = 0.0
        self.real_pan_spd = 0.0
        self.real_tilt_spd = 0.0
        self.real_temp = 0.0

        # Simulation state (when not connected)
        self.sim_pan = 0.0
        self.sim_tilt = 0.0
        self.sim_pan_spd = 0.0
        self.sim_tilt_spd = 0.0

        self._build_ui()
        self._apply_style()
        self._connect_signals()

        # Simulation timer
        self.sim_timer = QTimer()
        self.sim_timer.timeout.connect(self._simulate)
        self.sim_timer.start(30)

    def resizeEvent(self, event):
        """Hide side panels when window is too narrow; hide compass when too short."""
        super().resizeEvent(event)
        w = event.size().width()
        h = event.size().height()
        # Width: side panels
        # < 700px: hide both side panels, only controls visible
        # < 950px: hide right panel only
        # >= 950px: show all
        if w < 700:
            self.left_container.setVisible(False)
            self.right_container.setVisible(False)
        elif w < 950:
            self.left_container.setVisible(True)
            self.right_container.setVisible(False)
        else:
            self.left_container.setVisible(True)
            self.right_container.setVisible(True)
        # Height: hide compass when window is short, keep only D-Pad
        self.compass_panel.setVisible(h >= 500)

    # ════════════════ UI BUILD ════════════════
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ─── LEFT PANEL (in a QWidget container for show/hide) ───
        self.left_container = QWidget()
        self.left_container.setFixedWidth(260)
        left = QVBoxLayout(self.left_container)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)

        # Connection
        conn = CollapsiblePanel("CONNECTION")
        cl = QVBoxLayout()
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("IP:"))
        self.ip_input = QLineEdit("192.168.1.115")
        self.ip_input.setFixedWidth(120)
        r1.addWidget(self.ip_input)
        cl.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Port:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(9760)
        self.port_input.setFixedWidth(120)
        r2.addWidget(self.port_input)
        cl.addLayout(r2)
        self.connect_btn = QPushButton("CONNECT")
        self.connect_btn.clicked.connect(self._toggle_connection)
        cl.addWidget(self.connect_btn)
        self.status_label = QLabel("● DISCONNECTED")
        self.status_label.setStyleSheet("color:#888888; font:bold 11px Consolas;")
        cl.addWidget(self.status_label)
        conn.content_layout().addLayout(cl)
        left.addWidget(conn)

        # Speed setting (sliders — only set value, no movement)
        spd = CollapsiblePanel("SPEED SETTING")
        sl = QVBoxLayout()
        self.pan_speed_ctrl = SpeedControl("PAN SPEED °/s", -50, 50)
        sl.addWidget(self.pan_speed_ctrl)
        self.tilt_speed_ctrl = SpeedControl("TILT SPEED °/s", -20, 20)
        sl.addWidget(self.tilt_speed_ctrl)
        spd.content_layout().addLayout(sl)
        left.addWidget(spd)

        # Go-to position
        pos = CollapsiblePanel("GO TO POSITION")
        pl = QGridLayout()
        pl.addWidget(QLabel("PAN °:"), 0, 0)
        self.pan_pos_spin = QDoubleSpinBox()
        self.pan_pos_spin.setRange(0, 359.99)
        self.pan_pos_spin.setDecimals(2)
        pl.addWidget(self.pan_pos_spin, 0, 1)
        pl.addWidget(QLabel("TILT °:"), 1, 0)
        self.tilt_pos_spin = QDoubleSpinBox()
        self.tilt_pos_spin.setRange(-90, 45)
        self.tilt_pos_spin.setDecimals(2)
        pl.addWidget(self.tilt_pos_spin, 1, 1)
        go_btn = QPushButton("GO")
        go_btn.setStyleSheet("""
            QPushButton{background:#111111;color:#ffffff;border:1px solid #ffffff;
                        font:bold 12px Consolas;padding:8px;border-radius:4px;}
            QPushButton:hover{background:#222222;}
            QPushButton:pressed{background:#ffffff;color:#000000;}
        """)
        go_btn.clicked.connect(self._goto_position)
        pl.addWidget(go_btn, 2, 0, 1, 2)
        pos.content_layout().addLayout(pl)
        left.addWidget(pos)

        # STOP ALL
        stop_btn = QPushButton("⬛  STOP ALL")
        stop_btn.setStyleSheet("""
            QPushButton{background:#111111;color:#aaaaaa;border:1px solid #666666;
                        font:bold 14px Consolas;padding:12px;border-radius:6px;}
            QPushButton:hover{background:#222222;}
            QPushButton:pressed{background:#666666;color:#000000;}
        """)
        stop_btn.clicked.connect(self._stop_all)
        left.addWidget(stop_btn)

        # HOME button
        home_btn = QPushButton("⌂  HOME (0° / 0°)")
        home_btn.setStyleSheet("""
            QPushButton{background:#111111;color:#cccccc;border:1px solid #555555;
                        font:bold 13px Consolas;padding:10px;border-radius:6px;}
            QPushButton:hover{background:#222222;}
            QPushButton:pressed{background:#555555;color:#000000;}
        """)
        home_btn.clicked.connect(self._go_home)
        left.addWidget(home_btn)

        # TILT invert + Diagnostics
        diag = CollapsiblePanel("TILT & DIAGNOSTICS")
        dl = QVBoxLayout()
        self.tilt_invert_cb = QCheckBox("Invert TILT axis")
        self.tilt_invert_cb.setStyleSheet("color:#aaaaaa; font:bold 10px Consolas;")
        dl.addWidget(self.tilt_invert_cb)
        diag_row = QHBoxLayout()
        pan_diag_btn = QPushButton("PAN DIAG")
        pan_diag_btn.setStyleSheet("""
            QPushButton{background:#111111;color:#aaaaaa;border:1px solid #555555;
                        font:bold 10px Consolas;padding:6px;border-radius:4px;}
            QPushButton:hover{background:#222222;}
            QPushButton:pressed{background:#555555;color:#000000;}
        """)
        pan_diag_btn.clicked.connect(self._pan_diag)
        diag_row.addWidget(pan_diag_btn)
        tilt_diag_btn = QPushButton("TILT DIAG")
        tilt_diag_btn.setStyleSheet("""
            QPushButton{background:#111111;color:#aaaaaa;border:1px solid #555555;
                        font:bold 10px Consolas;padding:6px;border-radius:4px;}
            QPushButton:hover{background:#222222;}
            QPushButton:pressed{background:#555555;color:#000000;}
        """)
        tilt_diag_btn.clicked.connect(self._tilt_diag)
        diag_row.addWidget(tilt_diag_btn)
        dl.addLayout(diag_row)
        diag.content_layout().addLayout(dl)
        left.addWidget(diag)

        left.addStretch()
        root.addWidget(self.left_container)

        # ─── CENTER ───
        center = QVBoxLayout()

        # Compass in a collapsible framed window
        self.compass_panel = CollapsiblePanel("COMPASS")
        compass_inner = QVBoxLayout()
        self.viz = DeviceVisualization()
        compass_inner.addWidget(self.viz)
        self.compass_panel.content_layout().addLayout(compass_inner)
        center.addWidget(self.compass_panel, 1)

        # D-Pad in a collapsible framed window
        dpad_panel = CollapsiblePanel("CONTROL PAD")
        dpad_inner = QHBoxLayout()
        dpad_inner.addStretch()
        self.dpad = DirectionPad()
        self.dpad.direction_pressed.connect(self._on_dpad_pressed)
        self.dpad.direction_released.connect(self._on_dpad_released)
        dpad_inner.addWidget(self.dpad)
        dpad_inner.addStretch()
        dpad_panel.content_layout().addLayout(dpad_inner)
        center.addWidget(dpad_panel, 0)

        root.addLayout(center, 1)

        # ─── RIGHT PANEL (in a QWidget container for show/hide) ───
        self.right_container = QWidget()
        self.right_container.setFixedWidth(240)
        right = QVBoxLayout(self.right_container)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)

        # Device state
        st = CollapsiblePanel("DEVICE STATE")
        sg = QGridLayout()
        sg.setSpacing(4)
        self.pan_pos_lbl = QLabel("0.00°")
        self.tilt_pos_lbl = QLabel("0.00°")
        self.pan_spd_lbl = QLabel("0.0 °/s")
        self.tilt_spd_lbl = QLabel("0.0 °/s")
        self.temp_lbl = QLabel("-- °C")
        self.action_lbl = QLabel("IDLE")
        for i, (name, val) in enumerate([
            ("PAN:", self.pan_pos_lbl), ("TILT:", self.tilt_pos_lbl),
            ("PAN SPD:", self.pan_spd_lbl), ("TILT SPD:", self.tilt_spd_lbl),
            ("TEMP:", self.temp_lbl), ("STATUS:", self.action_lbl),
        ]):
            nl = QLabel(name)
            nl.setStyleSheet("color:#888888; font:10px Consolas;")
            val.setStyleSheet("color:#ffffff; font:bold 11px Consolas;")
            sg.addWidget(nl, i, 0)
            sg.addWidget(val, i, 1)
        st.content_layout().addLayout(sg)
        right.addWidget(st)

        # Log — QPlainTextEdit for stable layout
        lg = CollapsiblePanel("PROTOCOL LOG")
        ll = QVBoxLayout()
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(25)
        self.log_text.setStyleSheet("""
            QPlainTextEdit{color:#999999; font:9px Consolas;
                           background:#0a0a0a; border:1px solid #333333;
                           border-radius:4px;}
        """)
        self.log_text.setFixedHeight(200)
        ll.addWidget(self.log_text)
        lg.content_layout().addLayout(ll)
        right.addWidget(lg)

        right.addStretch()
        root.addWidget(self.right_container)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow{background:#000000;}
            QLabel{color:#aaaaaa; font:10px Consolas;}
            QLineEdit,QSpinBox,QDoubleSpinBox{
                background:#111111;color:#ffffff;border:1px solid #444444;
                padding:4px;border-radius:4px;font:11px Consolas;}
            QPushButton{
                background:#111111;color:#cccccc;border:1px solid #cccccc;
                padding:7px;border-radius:4px;font:bold 10px Consolas;}
            QPushButton:hover{background:#222222;}
            QPushButton:pressed{background:#cccccc;color:#000000;}
            QCheckBox{color:#aaaaaa; font:10px Consolas; spacing:6px;}
            QCheckBox::indicator{width:14px;height:14px;border:1px solid #888888;
                                 border-radius:3px;background:#111111;}
            QCheckBox::indicator:checked{background:#ffffff;border-color:#ffffff;}
        """)

    def _connect_signals(self):
        self.comm.pan_position_updated.connect(self._on_real_pan)
        self.comm.tilt_position_updated.connect(self._on_real_tilt)
        self.comm.pan_speed_updated.connect(self._on_real_pan_spd)
        self.comm.tilt_speed_updated.connect(self._on_real_tilt_spd)
        self.comm.temperature_updated.connect(self._on_real_temp)
        self.comm.connection_changed.connect(self._on_connection)
        self.comm.error_occurred.connect(lambda e: self._log(f"[ERR] {e}"))
        self.comm.log_message.connect(self._log)
        # TILT invert checkbox syncs with visualization
        self.tilt_invert_cb.toggled.connect(
            lambda checked: self.viz.set_tilt_inverted(checked))

    # ════════════════ REAL DEVICE CALLBACKS ════════════════
    def _on_real_pan(self, v):
        self.real_pan = v
        self.viz.set_angles(v, self.real_tilt)
        self.pan_pos_lbl.setText(f"{v:.2f}°")

    def _on_real_tilt(self, v):
        self.real_tilt = v
        self.viz.set_angles(self.real_pan, v)
        self.tilt_pos_lbl.setText(f"{v:.2f}°")

    def _on_real_pan_spd(self, v):
        self.real_pan_spd = v
        self.pan_spd_lbl.setText(f"{v:.1f} °/s")
        self.action_lbl.setText("MOVING" if abs(v) > 0.1 else "IDLE")
        self.action_lbl.setStyleSheet(
            "color:#bbbbbb;font:bold 11px Consolas;" if abs(v) > 0.1
            else "color:#ffffff;font:bold 11px Consolas;")

    def _on_real_tilt_spd(self, v):
        self.real_tilt_spd = v
        self.tilt_spd_lbl.setText(f"{v:.1f} °/s")

    def _on_real_temp(self, v):
        self.real_temp = v
        self.temp_lbl.setText(f"{v:.1f} °C")

    def _on_connection(self, connected):
        self.is_connected = connected
        s = "CONNECTED" if connected else "DISCONNECTED"
        c = "#ffffff" if connected else "#888888"
        self.status_label.setText(f"● {s}")
        self.status_label.setStyleSheet(f"color:{c}; font:bold 11px Consolas;")
        self.connect_btn.setText("DISCONNECT" if connected else "CONNECT")

    # ════════════════ ACTIONS ════════════════
    def _toggle_connection(self):
        if self.is_connected:
            self.comm.disconnect_device()
        else:
            self.comm.connect_device(self.ip_input.text(), self.port_input.value())

    def _get_tilt_sign(self):
        """Returns -1 if TILT is inverted, 1 otherwise."""
        return -1 if self.tilt_invert_cb.isChecked() else 1

    def _apply_speed(self):
        """No-op — sliders only store values for D-Pad."""
        pass

    def _stop_all(self):
        if self.is_connected:
            self.comm.stop_all()
        self.sim_pan_spd = 0.0
        self.sim_tilt_spd = 0.0
        self.pan_speed_ctrl.reset()
        self.tilt_speed_ctrl.reset()
        self._log("STOP ALL: $u# + $U#")

    def _go_home(self):
        """Return both axes to 0°."""
        if self.is_connected:
            self.comm.pan_goto(0.0)
            self.comm.tilt_goto(0.0)
        else:
            self.sim_pan_spd = 0
            self.sim_tilt_spd = 0
            self.sim_pan = 0.0
            self.sim_tilt = 0.0
        self._log("HOME: PAN→0° TILT→0°")

    def _pan_diag(self):
        """Start PAN axis self-diagnostics."""
        if self.is_connected:
            self.comm.pan_diag()
            self._log("DIAG: PAN self-diagnostics started ($m,1#)")
        else:
            # Simulate: rotate PAN 360° then back to 0
            self.sim_pan_spd = 30.0
            self._log("[SIM] DIAG: PAN self-diagnostics (rotating 360°)")
            QTimer.singleShot(12000, lambda: self._sim_diag_done('pan'))

    def _tilt_diag(self):
        """Start TILT axis self-diagnostics."""
        if self.is_connected:
            self.comm.tilt_diag()
            self._log("DIAG: TILT self-diagnostics started ($M,1#)")
        else:
            self.sim_tilt_spd = 10.0
            self._log("[SIM] DIAG: TILT self-diagnostics (cycling)")
            QTimer.singleShot(5000, lambda: self._sim_diag_done('tilt_neg'))
            QTimer.singleShot(10000, lambda: self._sim_diag_done('tilt_zero'))

    def _sim_diag_done(self, axis):
        if axis == 'pan':
            self.sim_pan_spd = 0
            self.sim_pan = 0.0
            self._log("[SIM] DIAG: PAN done → 0°")
        elif axis == 'tilt_neg':
            self.sim_tilt_spd = -10.0
        elif axis == 'tilt_zero':
            self.sim_tilt_spd = 0
            self.sim_tilt = 0.0
            self._log("[SIM] DIAG: TILT done → 0°")

    def _goto_position(self):
        pan = self.pan_pos_spin.value()
        tilt = self.tilt_pos_spin.value()
        if self.is_connected:
            self.comm.pan_goto(pan)
            self.comm.tilt_goto(tilt)
        else:
            # In sim: jump smoothly
            self.sim_pan_spd = 0
            self.sim_tilt_spd = 0
            self.sim_pan = pan
            self.sim_tilt = tilt
        self._log(f"GOTO: PAN={pan:.2f}° TILT={tilt:.2f}°")

    # ════════════════ D-PAD (8 directions) ════════════════
    def _on_dpad_pressed(self, d):
        if d == 'STOP':
            self._stop_all()
            return
        # Read speed values from sliders (absolute)
        pan_spd = self.pan_speed_ctrl.get_speed()
        tilt_spd = self.tilt_speed_ctrl.get_speed()
        # If slider is at 0, use defaults
        if abs(pan_spd) < 0.1:
            pan_spd = 20.0
        if abs(tilt_spd) < 0.1:
            tilt_spd = 10.0
    
        # Map direction to (pan_speed, tilt_speed) — always intuitive
        dir_map = {
            'UP':         (0.0,           tilt_spd),
            'DOWN':       (0.0,          -tilt_spd),
            'LEFT':       (-abs(pan_spd),  0.0),
            'RIGHT':      (abs(pan_spd),   0.0),
            'UP_RIGHT':   (abs(pan_spd),   tilt_spd),
            'UP_LEFT':    (-abs(pan_spd),  tilt_spd),
            'DOWN_RIGHT': (abs(pan_spd),  -tilt_spd),
            'DOWN_LEFT':  (-abs(pan_spd), -tilt_spd),
        }
        p_spd, t_spd = dir_map.get(d, (0, 0))
    
        if self.is_connected:
            # Apply inversion only for real device commands
            tilt_sign = self._get_tilt_sign()
            if p_spd != 0:
                self.comm.pan_set_speed(p_spd)
            if t_spd != 0:
                self.comm.tilt_set_speed(t_spd * tilt_sign)
        # Sim: always intuitive — inversion doesn't affect visual direction
        self.sim_pan_spd = p_spd
        self.sim_tilt_spd = t_spd
        self._log(f"[DPAD] {d} \u2192 PAN={p_spd:.0f} TILT={t_spd:.0f} °/s")

    def _on_dpad_released(self, d):
        if d == 'STOP':
            return
        # Diagonals affect both axes
        if d in ('UP_RIGHT', 'UP_LEFT', 'DOWN_RIGHT', 'DOWN_LEFT'):
            if self.is_connected:
                self.comm.pan_stop()
                self.comm.tilt_stop()
            self.sim_pan_spd = 0
            self.sim_tilt_spd = 0
            self._log(f"[DPAD] {d} → ALL STOP")
        elif d in ('LEFT', 'RIGHT'):
            if self.is_connected:
                self.comm.pan_stop()
            self.sim_pan_spd = 0
            self._log("[DPAD] PAN STOP")
        elif d in ('UP', 'DOWN'):
            if self.is_connected:
                self.comm.tilt_stop()
            self.sim_tilt_spd = 0
            self._log("[DPAD] TILT STOP")

    # ════════════════ SIMULATION ════════════════
    def _simulate(self):
        """Runs when not connected — updates positions from sim speeds."""
        if self.is_connected:
            return

        dt = 0.03
        if abs(self.sim_pan_spd) > 0.01:
            self.sim_pan = (self.sim_pan + self.sim_pan_spd * dt) % 360
        if abs(self.sim_tilt_spd) > 0.01:
            self.sim_tilt = max(-90, min(45, self.sim_tilt + self.sim_tilt_spd * dt))

        # Feed real values to visualization and labels
        self.viz.set_angles(self.sim_pan, self.sim_tilt)
        self.viz.set_speeds(self.sim_pan_spd, self.sim_tilt_spd)

        self.pan_pos_lbl.setText(f"{self.sim_pan:.2f}°")
        self.tilt_pos_lbl.setText(f"{self.sim_tilt:.2f}°")
        self.pan_spd_lbl.setText(f"{self.sim_pan_spd:.1f} °/s")
        self.tilt_spd_lbl.setText(f"{self.sim_tilt_spd:.1f} °/s")
        self.temp_lbl.setText("25.0 °C")

        moving = abs(self.sim_pan_spd) > 0.1 or abs(self.sim_tilt_spd) > 0.1
        self.action_lbl.setText("MOVING" if moving else "IDLE")
        self.action_lbl.setStyleSheet(
            "color:#bbbbbb;font:bold 11px Consolas;" if moving
            else "color:#ffffff;font:bold 11px Consolas;")

    # ════════════════ LOG ════════════════
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{ts}] {msg}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
