"""Main application window for VisOPU."""

import threading
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QFrame, QGridLayout,
                              QSpinBox, QDoubleSpinBox, QLineEdit, QCheckBox,
                              QPlainTextEdit, QComboBox, QSplitter,
                              QDialog, QFormLayout, QDialogButtonBox, QMenu,
                              QMenuBar, QSizePolicy, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QPoint, QSettings, QObject
from PyQt6.QtGui import QAction, QFont, QColor, QShortcut, QKeySequence

from app.communicators import DeviceCommunicator, LaserCommunicator, PelcoDCommunicator, ONVIFCommunicator
from app.widgets import (CollapsiblePanel, DirectionPad,
                          SpeedControl, CameraWidget, SlidingPanel,
                          YandexMapWidget, HAS_CV2)
from app.detector import YoloDetector, FILTER_ALL, FILTER_AIR, FILTER_DRONE_VEHICLE
from app.styles import (apply_apple_dark_style, STYLE_GO_BUTTON, STYLE_STOP_ALL,
                         STYLE_HOME_BUTTON, STYLE_DIAG_BUTTON, STYLE_LOG_TEXT,
                         COLOR_CONNECTED, COLOR_DISCONNECTED, COLOR_ERROR,
                         COLOR_ACTIVE)


# ═══════════════════════════════════════════════════════════════════
# CONNECTION DIALOG
# ═══════════════════════════════════════════════════════════════════

class ConnectionDialog(QDialog):
    """Generic connection dialog for devices with input validation."""

    def __init__(self, title, fields, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.inputs = {}
        for label, default, echo in fields:
            inp = QLineEdit(str(default))
            if echo == "password":
                inp.setEchoMode(QLineEdit.EchoMode.Password)
            self.inputs[label] = inp
            form.addRow(label, inp)
        layout.addLayout(form)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _validate_and_accept(self):
        """Validate inputs before accepting."""
        for label, inp in self.inputs.items():
            val = inp.text().strip()
            if not val:
                QMessageBox.warning(self, "Validation", f"{label} cannot be empty")
                inp.setFocus()
                return
            # Port validation
            if label.lower().startswith("port"):
                try:
                    port = int(val)
                    if not (1 <= port <= 65535):
                        raise ValueError
                except ValueError:
                    QMessageBox.warning(self, "Validation", f"{label} must be 1-65535")
                    inp.setFocus()
                    return
        self.accept()

    def get_values(self):
        return {k: v.text().strip() for k, v in self.inputs.items()}


class _HideOnCloseFilter(QObject):
    """Event filter that hides a window on close instead of destroying it."""
    def eventFilter(self, obj, event):
        if event.type() == event.Type.Close:
            event.ignore()
            obj.hide()
            return True
        return False


class _StatusLink(QLabel):
    """Clickable status label that opens a connection dialog on click."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self._callback = None
        self._base_style = ""

    def set_callback(self, fn):
        self._callback = fn

    def _apply_style(self):
        color = self._base_style
        if self._hover:
            # Brighten on hover
            color = color.replace('#636366', '#98989d')
            color = color.replace('#30d158', '#5ae07a')
            color = color.replace('#ff453a', '#ff6b63')
        self.setStyleSheet(color)

    def set_status_style(self, style):
        self._base_style = style
        self._apply_style()

    def enterEvent(self, event):
        self._hover = True
        self._apply_style()

    def leaveEvent(self, event):
        self._hover = False
        self._apply_style()

    def mousePressEvent(self, event):
        if self._callback:
            self._callback()


# ═══════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    _LBL_FONT = "font:600 11px 'SF Pro Display';"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TL.0009 ОПУ — ТехЛазер")
        self.setMinimumSize(400, 300)
        self.resize(1150, 700)

        self.comm = DeviceCommunicator()
        self.is_connected = False

        self.laser_comm = LaserCommunicator()
        self.laser_connected = False

        self.pelco_comm = PelcoDCommunicator()
        self.pelco_connected = False

        self.onvif_comm = ONVIFCommunicator()
        self.onvif_connected = False

        # Camera state
        self.cam1_widget = None
        self.cam2_widget = None
        self.cam1_connected = False
        self.cam2_connected = False

        # Connection settings storage (defaults)
        self._pan_tilt_ip = "192.168.1.115"
        self._pan_tilt_port = 9760
        self._laser_ip = "192.168.1.7"
        self._laser_port = 20108
        self._cam1_ip = "192.168.1.10"
        self._cam1_user = "admin"
        self._cam1_pass = "admin"
        self._cam2_ip = "192.168.1.11"
        self._cam2_user = "admin"
        self._cam2_pass = "admin"

        # Pelco-D (zoom camera) settings
        self._pelco_ip = "192.168.1.10"
        self._pelco_port = 5000
        self._pelco_addr = 1

        # ONVIF camera settings
        self._onvif_ip = "192.168.1.68"
        self._onvif_port = 80
        self._onvif_user = "admin"
        self._onvif_pass = "12qwaszx"

        # Persistent settings
        self._settings = QSettings("VisOPU", "TL0009")
        self._load_settings()

        # Real device state
        self.real_pan = 0.0
        self.real_tilt = 0.0
        self.real_pan_spd = 0.0
        self.real_tilt_spd = 0.0
        self.real_temp = 0.0

        # Simulation state
        self.sim_pan = 0.0
        self.sim_tilt = 0.0
        self.sim_pan_spd = 0.0
        self.sim_tilt_spd = 0.0

        # Keyboard movement state (arrow keys + Q/E zoom)
        self._held_keys = set()  # currently held movement keys
        self._kb_zoom_timer = QTimer()
        self._kb_zoom_timer.setSingleShot(True)
        self._kb_zoom_timer.timeout.connect(self._zoom_stop)

        self._build_menu()
        self._build_ui()
        apply_apple_dark_style(self)
        self._connect_signals()

        # Push saved beam config to map on startup
        if hasattr(self, 'map_widget'):
            self.map_widget.apply_saved_config(
                self._beam_lat,
                self._beam_lng,
                self._beam_offset,
                self._beam_length,
                0)
            # Update map toolbar device position label
            if hasattr(self, '_map_pos_lbl'):
                self._map_pos_lbl.setText(
                    f"Device: {self._beam_lat:.4f}, {self._beam_lng:.4f}")

        # Status bar
        self.statusBar().showMessage("Ready")

        # Simulation timer
        self.sim_timer = QTimer()
        self.sim_timer.timeout.connect(self._simulate)
        self.sim_timer.start(30)

        # Zoom wheel stop timer (stops ONVIF zoom after scroll pulse)
        self._zoom_wheel_timer = QTimer()
        self._zoom_wheel_timer.setSingleShot(True)
        self._zoom_wheel_timer.timeout.connect(self._zoom_stop)

        # YOLO detection state
        self._detector = None          # YoloDetector instance
        self._detecting = False        # detection active
        self._tracking = False         # auto-follow active
        self._track_target_id = None   # currently followed track_id
        self._track_gain = 1.5         # proportional gain for auto-follow
        self._track_deadzone = 0.05    # 5% of frame = centered
        self._last_det_dx = 0.0
        self._last_det_dy = 0.0
        self._last_det_cls = ""

        # Track controller timer (20 Hz proportional control loop)
        self._track_timer = QTimer()
        self._track_timer.setInterval(50)
        self._track_timer.timeout.connect(self._track_control_tick)

        # Keyboard shortcuts
        self._setup_shortcuts()

    # ════════════════ MENU BAR ════════════════
    def _build_menu(self):
        menubar = self.menuBar()
        dev_menu = menubar.addMenu("&Devices")

        act_pt = QAction("PAN-TILT Connection...", self)
        act_pt.triggered.connect(self._connect_pan_tilt_dialog)
        dev_menu.addAction(act_pt)

        act_las = QAction("LASER Connection...", self)
        act_las.triggered.connect(self._connect_laser_dialog)
        dev_menu.addAction(act_las)

        # View menu
        view_menu = menubar.addMenu("&View")
        self._view_menu = view_menu

    def _set_reticle(self, idx):
        if self.cam1_widget:
            self.cam1_widget.set_reticle(idx)
        if self.cam2_widget:
            self.cam2_widget.set_reticle(idx)
        names = ["Crosshair", "Mil-Dot", "Combat"]
        self._log(f"[CAM] Reticle: {names[idx]}")

    # ════════════════ KEYBOARD SHORTCUTS ════════════════
    def _setup_shortcuts(self):
        """Global keyboard shortcuts for quick access."""
        shortcuts = [
            ("Space", self._stop_all),
            ("H", self._go_home),
            ("Escape", self._stop_tracking),
            ("F1", self._toggle_cameras_view),
            ("F2", self._toggle_map_view),
            ("F3", self._toggle_log_window),
        ]
        for key, fn in shortcuts:
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(fn)

    # ════════════════ KEYBOARD PAN/TILT/ZOOM ════════════════
    _MOVE_KEYS = {
        Qt.Key.Key_Left, Qt.Key.Key_Right,
        Qt.Key.Key_Up, Qt.Key.Key_Down,
        Qt.Key.Key_Q, Qt.Key.Key_E,
    }

    def keyPressEvent(self, event):
        """Arrow keys = pan/tilt, Q/E = zoom. Hold to move, release to stop."""
        key = event.key()
        if key in self._MOVE_KEYS:
            if event.isAutoRepeat():
                return  # ignore OS auto-repeat
            self._held_keys.add(key)
            self._apply_keyboard_movement()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Stop axis when its keys are released."""
        key = event.key()
        if key in self._MOVE_KEYS:
            if event.isAutoRepeat():
                return
            self._held_keys.discard(key)
            self._apply_keyboard_movement()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _apply_keyboard_movement(self):
        """Read _held_keys and send pan/tilt/zoom commands."""
        h = self._held_keys

        # ── PAN (Left / Right arrows) ──
        pan_left = Qt.Key.Key_Left in h
        pan_right = Qt.Key.Key_Right in h
        pan_spd = self.pan_speed_ctrl.get_speed()
        if pan_spd < 0.1:
            pan_spd = 20.0

        if pan_left and not pan_right:
            if self.is_connected:
                self.comm.pan_set_speed(-pan_spd)
            self.sim_pan_spd = -pan_spd
        elif pan_right and not pan_left:
            if self.is_connected:
                self.comm.pan_set_speed(pan_spd)
            self.sim_pan_spd = pan_spd
        else:
            # neither or both → stop pan
            if self.is_connected and not (pan_left and pan_right):
                self.comm.pan_stop()
            if not (pan_left or pan_right):
                self.sim_pan_spd = 0.0

        # ── TILT (Up / Down arrows) ──
        tilt_up = Qt.Key.Key_Up in h
        tilt_down = Qt.Key.Key_Down in h
        tilt_spd = self.tilt_speed_ctrl.get_speed()
        if tilt_spd < 0.1:
            tilt_spd = 10.0
        tilt_sign = self._get_tilt_sign()

        if tilt_up and not tilt_down:
            if self.is_connected:
                self.comm.tilt_set_speed(tilt_spd * tilt_sign)
            self.sim_tilt_spd = tilt_spd
        elif tilt_down and not tilt_up:
            if self.is_connected:
                self.comm.tilt_set_speed(-tilt_spd * tilt_sign)
            self.sim_tilt_spd = -tilt_spd
        else:
            if self.is_connected and not (tilt_up and tilt_down):
                self.comm.tilt_stop()
            if not (tilt_up or tilt_down):
                self.sim_tilt_spd = 0.0

        # ── ZOOM (Q = wide/out, E = tele/in) ──
        zoom_in = Qt.Key.Key_E in h
        zoom_out = Qt.Key.Key_Q in h
        if zoom_in and not zoom_out:
            if self._ensure_onvif_connected():
                spd = self._zoom_speed / 100.0
                self.onvif_comm.zoom_in(spd)
                self._kb_zoom_timer.start(300)
        elif zoom_out and not zoom_in:
            if self._ensure_onvif_connected():
                spd = self._zoom_speed / 100.0
                self.onvif_comm.zoom_out(spd)
                self._kb_zoom_timer.start(300)
        elif not zoom_in and not zoom_out:
            pass  # zoom stop handled by _kb_zoom_timer timeout

    # ════════════════ SETTINGS PERSISTENCE ════════════════
    def _load_settings(self):
        """Load saved connection parameters."""
        s = self._settings
        self._pan_tilt_ip = s.value("pan_tilt_ip", self._pan_tilt_ip)
        self._pan_tilt_port = int(s.value("pan_tilt_port", self._pan_tilt_port))
        self._laser_ip = s.value("laser_ip", self._laser_ip)
        self._laser_port = int(s.value("laser_port", self._laser_port))
        self._cam1_ip = s.value("cam1_ip", self._cam1_ip)
        self._cam1_user = s.value("cam1_user", self._cam1_user)
        self._cam1_pass = s.value("cam1_pass", self._cam1_pass)
        self._cam2_ip = s.value("cam2_ip", self._cam2_ip)
        self._cam2_user = s.value("cam2_user", self._cam2_user)
        self._cam2_pass = s.value("cam2_pass", self._cam2_pass)
        self._pelco_ip = s.value("pelco_ip", self._pelco_ip)
        self._pelco_port = int(s.value("pelco_port", self._pelco_port))
        self._pelco_addr = int(s.value("pelco_addr", self._pelco_addr))
        self._onvif_ip = s.value("onvif_ip", self._onvif_ip)
        self._onvif_port = int(s.value("onvif_port", self._onvif_port))
        self._onvif_user = s.value("onvif_user", self._onvif_user)
        self._onvif_pass = s.value("onvif_pass", self._onvif_pass)
        # TILT invert
        if hasattr(self, 'tilt_invert_cb'):
            invert = s.value("tilt_invert", "true")
            self.tilt_invert_cb.setChecked(str(invert).lower() in ("true", "1", "yes"))
        # Beam config — store as vars for later spinbox init
        self._beam_lat = float(s.value("beam_lat", 55.751574))
        self._beam_lng = float(s.value("beam_lng", 37.573856))
        self._beam_offset = float(s.value("beam_offset", 0.0))
        self._beam_length = int(s.value("beam_length", 3000))

    def _save_settings(self):
        """Save connection parameters to persistent storage."""
        s = self._settings
        s.setValue("pan_tilt_ip", self._pan_tilt_ip)
        s.setValue("pan_tilt_port", self._pan_tilt_port)
        s.setValue("laser_ip", self._laser_ip)
        s.setValue("laser_port", self._laser_port)
        s.setValue("cam1_ip", self._cam1_ip)
        s.setValue("cam1_user", self._cam1_user)
        s.setValue("cam1_pass", self._cam1_pass)
        s.setValue("cam2_ip", self._cam2_ip)
        s.setValue("cam2_user", self._cam2_user)
        s.setValue("cam2_pass", self._cam2_pass)
        s.setValue("pelco_ip", self._pelco_ip)
        s.setValue("pelco_port", self._pelco_port)
        s.setValue("pelco_addr", self._pelco_addr)
        s.setValue("onvif_ip", self._onvif_ip)
        s.setValue("onvif_port", self._onvif_port)
        s.setValue("onvif_user", self._onvif_user)
        s.setValue("onvif_pass", self._onvif_pass)
        s.setValue("tilt_invert", self.tilt_invert_cb.isChecked() if hasattr(self, 'tilt_invert_cb') else True)
        # Beam config
        s.setValue("beam_lat", self._beam_lat)
        s.setValue("beam_lng", self._beam_lng)
        s.setValue("beam_offset", self._beam_offset)
        s.setValue("beam_length", self._beam_length)
        # Save cameras window geometry
        if hasattr(self, '_cameras_win'):
            s.setValue("cam_win_geometry", self._cameras_win.geometry())
        # Save map window geometry
        if hasattr(self, '_map_win'):
            s.setValue("map_win_geometry", self._map_win.geometry())

    # ════════════════ CONNECTION DIALOGS ════════════════
    def _connect_pan_tilt_dialog(self):
        dlg = ConnectionDialog("PAN-TILT Connection", [
            ("IP:", self._pan_tilt_ip, "text"),
            ("Port:", self._pan_tilt_port, "text"),
        ], self)
        if dlg.exec():
            vals = dlg.get_values()
            self._pan_tilt_ip = vals["IP:"]
            self._pan_tilt_port = int(vals["Port:"])
            self._save_settings()
            if self.is_connected:
                self.comm.disconnect_device()
            self.comm.connect_device(self._pan_tilt_ip, self._pan_tilt_port)
            self._log(f"[PAN-TILT] Connecting {self._pan_tilt_ip}:{self._pan_tilt_port}")

    def _connect_laser_dialog(self):
        dlg = ConnectionDialog("LASER Connection", [
            ("IP:", self._laser_ip, "text"),
            ("Port:", self._laser_port, "text"),
        ], self)
        if dlg.exec():
            vals = dlg.get_values()
            self._laser_ip = vals["IP:"]
            self._laser_port = int(vals["Port:"])
            self._save_settings()
            if self.laser_connected:
                self.laser_comm.disconnect_device()
            self.laser_comm.connect_device(self._laser_ip, self._laser_port)
            self._log(f"[LASER] Connecting {self._laser_ip}:{self._laser_port}")

    def _connect_cam1_dialog(self):
        dlg = ConnectionDialog("CAM1 — IP Camera", [
            ("IP:", self._cam1_ip, "text"),
            ("User:", self._cam1_user, "text"),
            ("Pass:", self._cam1_pass, "password"),
            ("RTSP:", "rtsp://{user}:{pass}@{ip}:554/stream1", "text"),
        ], self)
        if dlg.exec():
            vals = dlg.get_values()
            self._cam1_ip = vals["IP:"]
            self._cam1_user = vals["User:"]
            self._cam1_pass = vals["Pass:"]
            self._save_settings()
            url = vals["RTSP:"].replace("{ip}", self._cam1_ip)
            url = url.replace("{user}", self._cam1_user).replace("{pass}", self._cam1_pass)
            self._connect_cam_stream(1, url, is_thermal=False)

    def _connect_cam2_dialog(self):
        dlg = ConnectionDialog("CAM2 — Thermal Camera", [
            ("IP:", self._cam2_ip, "text"),
            ("User:", self._cam2_user, "text"),
            ("Pass:", self._cam2_pass, "password"),
            ("RTSP:", "rtsp://{user}:{pass}@{ip}:554/stream1", "text"),
        ], self)
        if dlg.exec():
            vals = dlg.get_values()
            self._cam2_ip = vals["IP:"]
            self._cam2_user = vals["User:"]
            self._cam2_pass = vals["Pass:"]
            self._save_settings()
            url = vals["RTSP:"].replace("{ip}", self._cam2_ip)
            url = url.replace("{user}", self._cam2_user).replace("{pass}", self._cam2_pass)
            self._connect_cam_stream(2, url, is_thermal=True)

    def _connect_zoom_dialog(self):
        dlg = ConnectionDialog("ZOOM Camera — ONVIF", [
            ("IP:", self._onvif_ip, "text"),
            ("Port:", self._onvif_port, "text"),
            ("User:", self._onvif_user, "text"),
            ("Pass:", self._onvif_pass, "password"),
        ], self)
        if dlg.exec():
            vals = dlg.get_values()
            self._onvif_ip = vals["IP:"]
            self._onvif_port = int(vals["Port:"])
            self._onvif_user = vals["User:"]
            self._onvif_pass = vals["Pass:"]
            self._save_settings()
            if self.onvif_connected:
                self.onvif_comm.disconnect_device()
            self.onvif_comm.connect_device(
                self._onvif_ip, self._onvif_user, self._onvif_pass, self._onvif_port)
            self._log(f"[ZOOM] Connecting ONVIF {self._onvif_ip}:{self._onvif_port}")

    def _connect_cam_stream(self, cam_idx, url, is_thermal):
        widget = self.cam1_widget if cam_idx == 1 else self.cam2_widget
        if not HAS_CV2:
            self._log("[CAM] OpenCV not installed — pip install opencv-python")
            return
        if widget.streaming:
            widget.disconnect_stream()
            self._log(f"[CAM] CAM{cam_idx} disconnected")
            c = COLOR_DISCONNECTED
            s = "OFF"
        else:
            ok = widget.connect_stream(url, is_thermal)
            if ok:
                self._log(f"[CAM] CAM{cam_idx} connected: {url}"
                          + (f" [THERMAL MODE]" if is_thermal else ""))
                # Show and raise cameras window
                self._cameras_win.show()
                self._cameras_win.raise_()
                c = COLOR_CONNECTED
                s = "ON"
            else:
                self._log(f"[CAM] CAM{cam_idx} connection failed")
                c = COLOR_ERROR
                s = "ERR"
        # Update status indicator
        lbl = self.cam1_status_lbl if cam_idx == 1 else self.cam2_status_lbl
        lbl.setText(f"● CAM{cam_idx}: {s}")
        lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")

    def _set_reticle(self, idx):
        if self.cam1_widget:
            self.cam1_widget.set_reticle(idx)
        if self.cam2_widget:
            self.cam2_widget.set_reticle(idx)
        names = ["Crosshair", "Mil-Dot", "Combat"]
        self._log(f"[CAM] Reticle: {names[idx]}")

    # ════════════════ CAMERAS WINDOW MENU ════════════════
    def _build_cameras_menu(self):
        """Build menu bar inside the cameras floating window."""
        menubar = QMenuBar(self._cameras_win)
        menubar.setStyleSheet(
            "QMenuBar{background:#2d2d2d;border-bottom:1px solid #3c3c3c;}"
            "QMenuBar::item{color:#98989d;padding:4px 10px;font:600 10px 'SF Pro Display';}"
            "QMenuBar::item:selected{background:#3a3a3c;color:#f5f5f7;}"
            "QMenu{background:#2d2d2d;border:1px solid #3c3c3c;}"
            "QMenu::item{color:#f5f5f7;padding:5px 24px;font:500 11px 'SF Pro Display';}"
            "QMenu::item:selected{background:#0a84ff;}")

        # ── Connection menu ──
        conn_menu = menubar.addMenu("Connection")
        act_cam1 = QAction("CAM1 (IP Camera)...", self._cameras_win)
        act_cam1.triggered.connect(self._connect_cam1_dialog)
        conn_menu.addAction(act_cam1)

        act_cam2 = QAction("CAM2 (Thermal)...", self._cameras_win)
        act_cam2.triggered.connect(self._connect_cam2_dialog)
        conn_menu.addAction(act_cam2)

        conn_menu.addSeparator()

        act_zoom = QAction("ZOOM Camera (ONVIF)...", self._cameras_win)
        act_zoom.triggered.connect(self._connect_zoom_dialog)
        conn_menu.addAction(act_zoom)

        # ── Settings menu ──
        settings_menu = menubar.addMenu("Settings")

        # Reticle submenu
        ret_menu = settings_menu.addMenu("Reticle")
        for name, idx in [("Crosshair", 0), ("Mil-Dot", 1), ("Combat", 2)]:
            a = QAction(name, self._cameras_win)
            a.triggered.connect(lambda checked, i=idx: self._set_reticle(i))
            ret_menu.addAction(a)

        # Detection filter submenu
        filt_menu = settings_menu.addMenu("Detection Filter")
        for name, idx in [("All Classes", 0), ("Air Targets", 1), ("Drones + Vehicles", 2)]:
            a = QAction(name, self._cameras_win)
            a.triggered.connect(lambda checked, i=idx: self._menu_set_filter(i))
            filt_menu.addAction(a)

        settings_menu.addSeparator()

        # Zoom speed
        act_zoom_spd = QAction("Zoom Speed...", self._cameras_win)
        act_zoom_spd.triggered.connect(self._menu_set_zoom_speed)
        settings_menu.addAction(act_zoom_spd)

        # Tracking gain
        act_gain = QAction("Tracking Gain...", self._cameras_win)
        act_gain.triggered.connect(self._menu_set_track_gain)
        settings_menu.addAction(act_gain)

        return menubar

    def _menu_set_filter(self, idx):
        """Set detection filter from cameras menu."""
        if hasattr(self, 'det_filter_combo'):
            self.det_filter_combo.setCurrentIndex(idx)

    def _menu_set_zoom_speed(self):
        """Dialog to set zoom speed percentage."""
        from PyQt6.QtWidgets import QInputDialog
        cur = getattr(self, '_zoom_speed', 50)
        val, ok = QInputDialog.getInt(self, "Zoom Speed", "Zoom speed (%):",
                                       cur, 10, 100, 5)
        if ok:
            self._zoom_speed = val

    def _menu_set_track_gain(self):
        """Dialog to set tracking gain."""
        from PyQt6.QtWidgets import QInputDialog
        val, ok = QInputDialog.getDouble(self, "Tracking Gain", "Proportional gain:",
                                          self._track_gain, 0.1, 10.0, 2, 0.1)
        if ok:
            self._track_gain = val

    def _menu_beam_config(self):
        """Dialog to set map beam position (called from map window toolbar)."""
        from PyQt6.QtWidgets import QInputDialog
        lat, ok = QInputDialog.getDouble(self, "Beam Latitude", "Latitude:",
                                          getattr(self, '_beam_lat', 55.751574), -90, 90, 6, 0.001)
        if not ok:
            return
        lng, ok = QInputDialog.getDouble(self, "Beam Longitude", "Longitude:",
                                          getattr(self, '_beam_lng', 37.573856), -180, 180, 6, 0.001)
        if not ok:
            return
        off, ok = QInputDialog.getDouble(self, "Beam Offset", "Offset (deg):",
                                          getattr(self, '_beam_offset', 0.0), -180, 180, 1, 0.5)
        if not ok:
            return
        length, ok = QInputDialog.getInt(self, "Beam Length", "Length (m):",
                                          getattr(self, '_beam_length', 3000), 100, 50000, 100)
        if not ok:
            return
        self._beam_lat = lat
        self._beam_lng = lng
        self._beam_offset = off
        self._beam_length = length
        self._apply_beam_config()

    # ════════════════ VIEW TOGGLES ════════════════
    def _toggle_cameras_view(self):
        if self._cameras_win.isVisible():
            self._cameras_win.hide()
        else:
            self._cameras_win.show()
            self._cameras_win.raise_()

    def _toggle_map_view(self):
        if self._map_win.isVisible():
            self._map_win.hide()
        else:
            self._map_win.show()
            self._map_win.raise_()

    # ════════════════ RESIZE — responsive auto-collapse ════════════════
    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        # Determine desired panel states based on window width
        if w < 700:
            left_show, right_show = False, False
        elif w < 950:
            left_show, right_show = True, False
        else:
            left_show, right_show = True, True

        # Only trigger animation when state actually changes
        if hasattr(self, 'left_panel'):
            if left_show and self.left_panel._collapsed:
                self.left_panel._show()
            elif not left_show and not self.left_panel._collapsed:
                self.left_panel._hide()
        if hasattr(self, 'right_panel'):
            if right_show and self.right_panel._collapsed:
                self.right_panel._show()
            elif not right_show and not self.right_panel._collapsed:
                self.right_panel._hide()

    def closeEvent(self, event):
        self._save_settings()
        # Stop tracking
        if hasattr(self, '_track_timer') and self._track_timer.isActive():
            self._track_timer.stop()
        # Stop camera streams
        for cam in (self.cam1_widget, self.cam2_widget):
            if cam:
                cam.disconnect_stream()
        # Stop laser polling
        if hasattr(self, 'laser_comm') and self.laser_comm.polling:
            self.laser_comm.stop_continuous()
        # Stop PAN-TILT polling
        if hasattr(self, 'comm') and self.comm.polling:
            self.comm.stop_polling()
        # Destroy YOLO detector
        if hasattr(self, '_detector') and self._detector:
            self._detector.destroy()
        # Clean up floating windows
        if hasattr(self, '_cameras_win'):
            self._cameras_win.deleteLater()
        if hasattr(self, '_map_win'):
            self._map_win.deleteLater()
        if hasattr(self, '_log_win'):
            self._log_win.deleteLater()
        super().closeEvent(event)

    # ════════════════ UI BUILD ════════════════
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── LEFT SLIDING PANEL ───
        self.left_panel = SlidingPanel(240, side='left')
        left_content = QWidget()
        left = QVBoxLayout(left_content)
        left.setContentsMargins(8, 8, 8, 8)
        left.setSpacing(2)

        # Status indicators (compact, clickable)
        status_panel = CollapsiblePanel("DEVICE STATUS")
        sl = QGridLayout()
        sl.setSpacing(4)
        _lbl_font = self._LBL_FONT
        self.pt_status_lbl = _StatusLink("● PAN-TILT: OFF")
        self.pt_status_lbl.set_status_style(f"color:{COLOR_DISCONNECTED}; {_lbl_font}")
        self.pt_status_lbl.set_callback(self._connect_pan_tilt_dialog)
        self.laser_status_lbl = _StatusLink("● LASER: OFF")
        self.laser_status_lbl.set_status_style(f"color:{COLOR_DISCONNECTED}; {_lbl_font}")
        self.laser_status_lbl.set_callback(self._connect_laser_dialog)
        self.cam1_status_lbl = _StatusLink("● CAM1: OFF")
        self.cam1_status_lbl.set_status_style(f"color:{COLOR_DISCONNECTED}; {_lbl_font}")
        self.cam1_status_lbl.set_callback(self._connect_cam1_dialog)
        self.cam2_status_lbl = _StatusLink("● CAM2: OFF")
        self.cam2_status_lbl.set_status_style(f"color:{COLOR_DISCONNECTED}; {_lbl_font}")
        self.cam2_status_lbl.set_callback(self._connect_cam2_dialog)
        self.zoom_status_lbl = _StatusLink("● ZOOM: OFF")
        self.zoom_status_lbl.set_status_style(f"color:{COLOR_DISCONNECTED}; {_lbl_font}")
        self.zoom_status_lbl.set_callback(self._connect_zoom_dialog)
        sl.addWidget(self.pt_status_lbl, 0, 0)
        sl.addWidget(self.laser_status_lbl, 1, 0)
        sl.addWidget(self.cam1_status_lbl, 2, 0)
        sl.addWidget(self.cam2_status_lbl, 3, 0)
        sl.addWidget(self.zoom_status_lbl, 4, 0)
        status_panel.content_layout().addLayout(sl)
        left.addWidget(status_panel)

        # Speed setting
        spd = CollapsiblePanel("SPEED SETTING")
        spdl = QVBoxLayout()
        self.pan_speed_ctrl = SpeedControl("PAN SPEED °/s", 0, 50)
        spdl.addWidget(self.pan_speed_ctrl)
        self.tilt_speed_ctrl = SpeedControl("TILT SPEED °/s", 0, 20)
        spdl.addWidget(self.tilt_speed_ctrl)
        spd.content_layout().addLayout(spdl)
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
        go_btn.setStyleSheet(STYLE_GO_BUTTON)
        go_btn.clicked.connect(self._goto_position)
        pl.addWidget(go_btn, 2, 0, 1, 2)
        pos.content_layout().addLayout(pl)
        left.addWidget(pos)

        # STOP ALL
        stop_btn = QPushButton("⬛  STOP ALL")
        stop_btn.setStyleSheet(STYLE_STOP_ALL)
        stop_btn.clicked.connect(self._stop_all)
        left.addWidget(stop_btn)

        # HOME button
        home_btn = QPushButton("⌂  HOME (0° / 0°)")
        home_btn.setStyleSheet(STYLE_HOME_BUTTON)
        home_btn.clicked.connect(self._go_home)
        left.addWidget(home_btn)

        # TILT invert + Diagnostics
        diag = CollapsiblePanel("TILT & DIAGNOSTICS")
        dl = QVBoxLayout()
        self.tilt_invert_cb = QCheckBox("Invert TILT axis")
        self.tilt_invert_cb.setChecked(True)  # default ON
        # Load saved preference (override default if previously saved)
        saved_invert = self._settings.value("tilt_invert")
        if saved_invert is not None:
            self.tilt_invert_cb.setChecked(str(saved_invert).lower() in ("true", "1", "yes"))
        self.tilt_invert_cb.setStyleSheet("color:#98989d; font:600 11px 'SF Pro Display';")
        dl.addWidget(self.tilt_invert_cb)
        diag_row = QHBoxLayout()
        pan_diag_btn = QPushButton("PAN DIAG")
        pan_diag_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        pan_diag_btn.clicked.connect(self._pan_diag)
        diag_row.addWidget(pan_diag_btn)
        tilt_diag_btn = QPushButton("TILT DIAG")
        tilt_diag_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        tilt_diag_btn.clicked.connect(self._tilt_diag)
        diag_row.addWidget(tilt_diag_btn)
        dl.addLayout(diag_row)
        diag.content_layout().addLayout(dl)
        left.addWidget(diag)

        left.addStretch()
        self.left_panel.set_content_layout(left)
        root.addWidget(self.left_panel)

        # ─── CENTER — Yandex Map ───
        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)

        # Create camera widgets for the floating cameras window
        self.cam1_widget = CameraWidget("CAM1 — IP")
        self.cam2_widget = CameraWidget("CAM2 — THERMAL")
        self.cam2_widget.is_thermal = True

        # ─── FLOATING CAMERAS WINDOW (draggable, resizable) ───
        self._cameras_win = QWidget(self, Qt.WindowType.Window)
        self._cameras_win.setWindowTitle("CAMERAS")
        self._cameras_win.resize(900, 400)
        self._cameras_win.setMinimumSize(300, 200)
        self._cameras_win.setStyleSheet("background:#1e1e1e;")

        # Hide on close instead of destroy
        self._cam_close_filter = _HideOnCloseFilter(self._cameras_win)
        self._cameras_win.installEventFilter(self._cam_close_filter)

        cam_layout = QVBoxLayout(self._cameras_win)
        cam_layout.setContentsMargins(0, 0, 0, 0)
        cam_layout.setSpacing(0)

        # Title bar
        cam_hdr = QLabel("  CAMERAS")
        cam_hdr.setFixedHeight(28)
        cam_hdr.setStyleSheet(
            "color:#98989d; font:600 10px 'SF Pro Display'; "
            "background:#2d2d2d; border-bottom:1px solid #3c3c3c;")
        cam_layout.addWidget(cam_hdr)

        # Cameras window menu bar
        cam_menubar = self._build_cameras_menu()
        cam_layout.addWidget(cam_menubar)

        # Splitter for side-by-side cameras
        cam_splitter = QSplitter(Qt.Orientation.Horizontal)
        cam_splitter.setHandleWidth(3)
        cam_splitter.setStyleSheet("""
            QSplitter::handle {
                background: #3c3c3c;
            }
            QSplitter::handle:hover {
                background: #0a84ff;
            }
        """)
        cam_splitter.addWidget(self.cam1_widget)
        cam_splitter.addWidget(self.cam2_widget)
        cam_splitter.setStretchFactor(0, 1)
        cam_splitter.setStretchFactor(1, 1)
        cam_layout.addWidget(cam_splitter, 1)

        # Position the cameras window next to the main window
        saved_geom = self._settings.value("cam_win_geometry")
        if saved_geom and hasattr(saved_geom, 'isValid') and saved_geom.isValid():
            self._cameras_win.setGeometry(saved_geom)
        else:
            self._cameras_win.move(
                self.pos().x() + self.width() + 20,
                self.pos().y())
        self._cameras_win.show()

        # View menu action for cameras window
        act_cams = QAction("Cameras Window", self)
        act_cams.triggered.connect(self._toggle_cameras_view)
        self._view_menu.addAction(act_cams)

        # ─── FLOATING MAP WINDOW (draggable, resizable) ───
        self.map_widget = YandexMapWidget()

        self._map_win = QWidget(self, Qt.WindowType.Window)
        self._map_win.setWindowTitle("MAP")
        self._map_win.resize(700, 500)
        self._map_win.setMinimumSize(300, 200)
        self._map_win.setStyleSheet("background:#1e1e1e;")

        # Hide on close instead of destroy
        self._map_close_filter = _HideOnCloseFilter(self._map_win)
        self._map_win.installEventFilter(self._map_close_filter)

        map_layout = QVBoxLayout(self._map_win)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)

        # Title bar
        map_hdr = QLabel("  MAP")
        map_hdr.setFixedHeight(28)
        map_hdr.setStyleSheet(
            "color:#98989d; font:600 10px 'SF Pro Display'; "
            "background:#2d2d2d; border-bottom:1px solid #3c3c3c;")
        map_layout.addWidget(map_hdr)

        # Map toolbar (beam config + device position)
        map_tb = QWidget()
        map_tb.setStyleSheet("QWidget{background:#1c1c1e; border-bottom:1px solid #38383a;}")
        map_tb_h = QHBoxLayout(map_tb)
        map_tb_h.setContentsMargins(8, 4, 8, 4)
        map_tb_h.setSpacing(8)
        beam_btn = QPushButton("BEAM CONFIG")
        beam_btn.setStyleSheet(
            "QPushButton{background:#2d2d2d;color:#98989d;border:1px solid #48484a;"
            "border-radius:4px;padding:3px 12px;font:600 10px 'SF Pro Display';}"
            "QPushButton:hover{background:#3a3a3c;color:#f5f5f7;border-color:#0a84ff;}")
        beam_btn.clicked.connect(self._menu_beam_config)
        map_tb_h.addWidget(beam_btn)
        self._map_pos_lbl = QLabel("Device: --")
        self._map_pos_lbl.setStyleSheet("color:#636366; font:500 10px 'SF Pro Display';")
        map_tb_h.addWidget(self._map_pos_lbl)
        map_tb_h.addStretch()
        map_layout.addWidget(map_tb)

        map_layout.addWidget(self.map_widget, 1)

        # Position the map window — avoid overlap with cameras window
        saved_map_geom = self._settings.value("map_win_geometry")
        if saved_map_geom and hasattr(saved_map_geom, 'isValid') and saved_map_geom.isValid():
            self._map_win.setGeometry(saved_map_geom)
        else:
            # Place below cameras window if it exists, otherwise next to main
            if hasattr(self, '_cameras_win'):
                cam_geo = self._cameras_win.geometry()
                # Check if cameras window bottom would go off screen
                cam_bottom = cam_geo.y() + cam_geo.height() + 10
                screen_h = self.screen().availableGeometry().height() if self.screen() else 900
                if cam_bottom + 500 > screen_h:
                    # Place map to the right of cameras window instead
                    self._map_win.move(cam_geo.x() + cam_geo.width() + 10, cam_geo.y())
                else:
                    self._map_win.move(cam_geo.x(), cam_bottom)
            else:
                self._map_win.move(
                    self.pos().x() + self.width() + 20,
                    self.pos().y() + 420)
        self._map_win.show()

        # View menu action for map window
        act_map = QAction("Map Window", self)
        act_map.triggered.connect(self._toggle_map_view)
        self._view_menu.addAction(act_map)

        # Add a placeholder to center so it's not empty
        center.addStretch()

        root.addLayout(center, 1)

        # ─── RIGHT SLIDING PANEL ───
        self.right_panel = SlidingPanel(220, side='right')
        right_content = QWidget()
        right = QVBoxLayout(right_content)
        right.setContentsMargins(8, 8, 8, 8)
        right.setSpacing(2)

        # D-Pad (primary control — always visible at top)
        dpad_panel = CollapsiblePanel("CONTROL PAD")
        dpad_inner = QHBoxLayout()
        dpad_inner.addStretch()
        self.dpad = DirectionPad()
        self.dpad.direction_pressed.connect(self._on_dpad_pressed)
        self.dpad.direction_released.connect(self._on_dpad_released)
        dpad_inner.addWidget(self.dpad)
        dpad_inner.addStretch()
        dpad_panel.content_layout().addLayout(dpad_inner)
        right.addWidget(dpad_panel)

        # Laser rangefinder controls (compact)
        laser = CollapsiblePanel("LASER RANGEFINDER")
        las = QVBoxLayout()
        self.laser_dist_lbl = QLabel("---.- m")
        self.laser_dist_lbl.setStyleSheet("color:#0a84ff; font:600 20px 'SF Pro Display';")
        self.laser_dist_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        las.addWidget(self.laser_dist_lbl)
        self.laser_target_lbl = QLabel("NO TARGET")
        self.laser_target_lbl.setStyleSheet("color:#636366; font:600 10px 'SF Pro Display';")
        self.laser_target_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        las.addWidget(self.laser_target_lbl)
        las_btns = QHBoxLayout()
        single_btn = QPushButton("SINGLE")
        single_btn.clicked.connect(self._laser_single)
        las_btns.addWidget(single_btn)
        self.laser_cont_btn = QPushButton("CONT")
        self.laser_cont_btn.clicked.connect(self._laser_continuous)
        las_btns.addWidget(self.laser_cont_btn)
        las.addLayout(las_btns)
        las_stop_btn = QPushButton("STOP")
        las_stop_btn.clicked.connect(self._laser_stop)
        las.addWidget(las_stop_btn)
        las_diag_btn = QPushButton("SELF-CHECK")
        las_diag_btn.clicked.connect(self._laser_selfcheck)
        las.addWidget(las_diag_btn)
        las_connect_btn = QPushButton("CONNECT")
        las_connect_btn.setStyleSheet(
            "QPushButton{background:#2d2d2d;color:#98989d;border:1px solid #48484a;"
            "border-radius:4px;padding:3px 8px;font:600 10px 'SF Pro Display';}"
            "QPushButton:hover{background:#3a3a3c;color:#f5f5f7;border-color:#30d158;}")
        las_connect_btn.clicked.connect(self._connect_laser_dialog)
        las.addWidget(las_connect_btn)
        laser.content_layout().addLayout(las)
        right.addWidget(laser)

        # (ZOOM CAMERA moved to Cameras window toolbar — see _build_zoom_toolbar)

        # ── DETECTION ──
        det_panel = CollapsiblePanel("DETECTION")
        dt = QVBoxLayout()
        dt.setSpacing(4)
        self.det_model_lbl = QLabel("Model: Not Loaded")
        self.det_model_lbl.setStyleSheet(
            "color:#636366; font:600 10px 'SF Pro Display';")
        dt.addWidget(self.det_model_lbl)
        det_btn_row = QHBoxLayout()
        self.detect_btn = QPushButton("DETECT")
        self.detect_btn.setCheckable(True)
        self.detect_btn.clicked.connect(self._toggle_detection)
        det_btn_row.addWidget(self.detect_btn)
        self.track_btn = QPushButton("TRACK")
        self.track_btn.setCheckable(True)
        self.track_btn.setEnabled(False)
        self.track_btn.clicked.connect(self._toggle_tracking)
        det_btn_row.addWidget(self.track_btn)
        dt.addLayout(det_btn_row)
        # Class filter
        flt_row = QHBoxLayout()
        flt_row.addWidget(QLabel("Filter:"))
        self.det_filter_combo = QComboBox()
        self.det_filter_combo.addItems(["All Classes", "Air Targets", "Drones + Vehicles"])
        self.det_filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        flt_row.addWidget(self.det_filter_combo, 1)
        dt.addLayout(flt_row)
        # Target info
        self.det_target_lbl = QLabel("NO TARGET")
        self.det_target_lbl.setStyleSheet(
            "color:#636366; font:600 11px 'SF Pro Display';")
        self.det_target_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dt.addWidget(self.det_target_lbl)
        # Lock / cycle target buttons
        tgt_row = QHBoxLayout()
        self.det_lock_btn = QPushButton("AUTO-LOCK")
        self.det_lock_btn.setEnabled(False)
        self.det_lock_btn.clicked.connect(self._auto_lock_target)
        tgt_row.addWidget(self.det_lock_btn)
        self.det_cycle_btn = QPushButton("NEXT")
        self.det_cycle_btn.setEnabled(False)
        self.det_cycle_btn.clicked.connect(self._cycle_target)
        tgt_row.addWidget(self.det_cycle_btn)
        dt.addLayout(tgt_row)
        # Stop tracking
        self.det_stop_btn = QPushButton("STOP TRACKING")
        self.det_stop_btn.setEnabled(False)
        self.det_stop_btn.clicked.connect(self._stop_tracking)
        dt.addWidget(self.det_stop_btn)
        # FPS
        self.det_fps_lbl = QLabel("FPS: --")
        self.det_fps_lbl.setStyleSheet(
            "color:#636366; font:10px 'SF Pro Display';")
        dt.addWidget(self.det_fps_lbl)
        det_panel.content_layout().addLayout(dt)
        right.addWidget(det_panel)

        # (MAP BEAM, DEVICE STATE, PROTOCOL LOG moved out of right panel)

        right.addStretch()
        self.right_panel.set_content_layout(right)
        root.addWidget(self.right_panel)

        # ─── DEVICE STATE — compact inline bar at bottom ───
        self._build_device_state_bar()

        # ─── FLOATING LOG WINDOW ───
        self._build_log_window()

        # ─── ZOOM CONTROLS — in cameras window toolbar ───
        self._build_zoom_toolbar()

    # ════════════════ BUILDER HELPERS ════════════════

    def _build_device_state_bar(self):
        """Compact inline device state bar at bottom of main window."""
        bar = QFrame()
        bar.setStyleSheet("QFrame{background:#1c1c1e; border-top:1px solid #38383a;}")
        bar.setFixedHeight(28)
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 2, 12, 2)
        h.setSpacing(16)
        _lbl_font = "font:600 10px 'SF Pro Display'"
        self.pan_pos_lbl = QLabel("PAN: 0.00\u00b0")
        self.tilt_pos_lbl = QLabel("TILT: 0.00\u00b0")
        self.pan_spd_lbl = QLabel("P-SPD: 0.0")
        self.tilt_spd_lbl = QLabel("T-SPD: 0.0")
        self.temp_lbl = QLabel("TEMP: --")
        self.action_lbl = QLabel("IDLE")
        for lbl in (self.pan_pos_lbl, self.tilt_pos_lbl, self.pan_spd_lbl,
                    self.tilt_spd_lbl, self.temp_lbl, self.action_lbl):
            lbl.setStyleSheet(f"color:#8e8e93; {_lbl_font};")
            h.addWidget(lbl)
        h.addStretch()
        self.statusBar().addPermanentWidget(bar)

    def _build_log_window(self):
        """Floating protocol log window (toggle from View menu)."""
        self._log_win = QFrame(self)
        self._log_win.setWindowFlags(Qt.WindowType.Window)
        self._log_win.setWindowTitle("Protocol Log")
        self._log_win.setStyleSheet(
            "QFrame{background:#1c1c1e;}"
            "QFrame#logFrame{background:#0a0a0a; border:1px solid #38383a; border-radius:6px;}")
        self._log_win.setFixedSize(420, 300)
        vl = QVBoxLayout(self._log_win)
        vl.setContentsMargins(8, 8, 8, 8)
        inner = QFrame()
        inner.setObjectName("logFrame")
        il = QVBoxLayout(inner)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(50)
        self.log_text.setStyleSheet(STYLE_LOG_TEXT)
        il.addWidget(self.log_text)
        vl.addWidget(inner)
        self._log_close_filter = _HideOnCloseFilter(self._log_win)
        self._log_win.installEventFilter(self._log_close_filter)
        # Add to View menu
        self._log_action = QAction("Protocol Log", self)
        self._log_action.setCheckable(True)
        self._log_action.triggered.connect(self._toggle_log_window)
        if hasattr(self, '_view_menu'):
            self._view_menu.addAction(self._log_action)

    def _toggle_log_window(self):
        if self._log_win.isVisible():
            self._log_win.hide()
            self._log_action.setChecked(False)
        else:
            self._log_win.move(self.x() + 200, self.y() + 200)
            self._log_win.show()
            self._log_win.raise_()
            self._log_action.setChecked(True)

    def _build_zoom_toolbar(self):
        """Zoom controls placed as toolbar inside the cameras floating window."""
        self._zoom_speed = 50  # default zoom speed %
        if not hasattr(self, '_cameras_win'):
            return
        tb = QWidget()
        tb.setStyleSheet("QWidget{background:#1c1c1e; border:1px solid #38383a; border-radius:6px;}")
        h = QHBoxLayout(tb)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(6)
        lbl = QLabel("ZOOM")
        lbl.setStyleSheet("color:#8e8e93; font:600 10px 'SF Pro Display';")
        h.addWidget(lbl)
        self.zoom_tele_btn = QPushButton("TELE +")
        self.zoom_tele_btn.setStyleSheet(STYLE_GO_BUTTON)
        self.zoom_tele_btn.pressed.connect(self._zoom_tele)
        self.zoom_tele_btn.released.connect(self._zoom_stop)
        h.addWidget(self.zoom_tele_btn)
        self.zoom_wide_btn = QPushButton("WIDE \u2212")
        self.zoom_wide_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.zoom_wide_btn.pressed.connect(self._zoom_wide)
        self.zoom_wide_btn.released.connect(self._zoom_stop)
        h.addWidget(self.zoom_wide_btn)
        # Focus
        self.focus_near_btn = QPushButton("NEAR")
        self.focus_near_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.focus_near_btn.pressed.connect(self._focus_near)
        self.focus_near_btn.released.connect(self._focus_stop)
        h.addWidget(self.focus_near_btn)
        self.focus_far_btn = QPushButton("FAR")
        self.focus_far_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.focus_far_btn.pressed.connect(self._focus_far)
        self.focus_far_btn.released.connect(self._focus_stop)
        h.addWidget(self.focus_far_btn)
        self.focus_auto_btn = QPushButton("AUTO FOCUS")
        self.focus_auto_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.focus_auto_btn.clicked.connect(self._focus_auto)
        h.addWidget(self.focus_auto_btn)
        # Insert into cameras window layout (after the splitter, before buttons)
        cam_layout = self._cameras_win.layout()
        if cam_layout is not None:
            cam_layout.addWidget(tb)

    # ════════════════ SIGNALS ════════════════
    def _connect_signals(self):
        self.comm.pan_position_updated.connect(self._on_real_pan)
        self.comm.tilt_position_updated.connect(self._on_real_tilt)
        self.comm.pan_speed_updated.connect(self._on_real_pan_spd)
        self.comm.tilt_speed_updated.connect(self._on_real_tilt_spd)
        self.comm.temperature_updated.connect(self._on_real_temp)
        self.comm.connection_changed.connect(self._on_connection)
        self.comm.error_occurred.connect(lambda e: self._log(f"[PAN-TILT ERR] {e}"))
        self.laser_comm.distance_updated.connect(self._on_laser_distance)
        self.laser_comm.connection_changed.connect(self._on_laser_connection)
        self.laser_comm.error_occurred.connect(lambda e: self._log(f"[LASER ERR] {e}"))
        self.pelco_comm.connection_changed.connect(self._on_pelco_connection)
        self.pelco_comm.error_occurred.connect(lambda e: self._log(f"[PELCO ERR] {e}"))
        self.onvif_comm.connection_changed.connect(self._on_onvif_connection)
        self.onvif_comm.error_occurred.connect(lambda e: self._log(f"[ONVIF ERR] {e}"))
        # Video overlay D-Pad + zoom scroll from camera widgets
        for cam in (self.cam1_widget, self.cam2_widget):
            cam.video_dpad_pressed.connect(self._on_dpad_pressed)
            cam.video_dpad_released.connect(self._on_dpad_released)
            cam.zoom_scroll.connect(self._on_zoom_scroll)
        # Detection signals from CAM1
        self.cam1_widget.detection_target.connect(self._on_detection_target)
        self.cam1_widget.detections_updated.connect(self._on_detections_updated)
        self.cam1_widget.detection_fps.connect(self._on_detection_fps)
        # Video overlay buttons (LSR, DET, TRK, FILTER) from both cameras
        for cam in (self.cam1_widget, self.cam2_widget):
            cam.video_laser_toggled.connect(self._on_video_laser)
            cam.video_detect_toggled.connect(self._on_video_detect)
            cam.video_track_toggled.connect(self._on_video_track)
            cam.video_filter_changed.connect(self._on_video_filter)
        # Thermal camera signals (CAM2)
        self.cam2_widget.thermal_palette_changed.connect(
            lambda name: self._log(f"[THERMAL] Palette: {name}"))
        self.cam2_widget.thermal_temp_updated.connect(self._on_thermal_temp)

    # ════════════════ CALLBACKS ════════════════
    def _on_real_pan(self, v):
        self.real_pan = v
        self.pan_pos_lbl.setText(f"PAN: {v:.2f}\u00b0")
        if hasattr(self, 'map_widget'):
            self.map_widget.set_pan_angle(v)

    def _on_real_tilt(self, v):
        self.real_tilt = v
        self.tilt_pos_lbl.setText(f"TILT: {v:.2f}\u00b0")

    def _on_real_pan_spd(self, v):
        self.real_pan_spd = v
        self.pan_spd_lbl.setText(f"P-SPD: {v:.1f}")
        self.action_lbl.setText("MOVING" if abs(v) > 0.1 else "IDLE")
        self.action_lbl.setStyleSheet(
            f"color:{COLOR_ACTIVE};font:600 10px 'SF Pro Display';" if abs(v) > 0.1
            else "color:#8e8e93;font:600 10px 'SF Pro Display';")

    def _on_real_tilt_spd(self, v):
        self.real_tilt_spd = v
        self.tilt_spd_lbl.setText(f"T-SPD: {v:.1f}")

    def _on_real_temp(self, v):
        self.real_temp = v
        self.temp_lbl.setText(f"TEMP: {v:.1f}")

    def _on_connection(self, connected):
        self.is_connected = connected
        c = COLOR_CONNECTED if connected else COLOR_DISCONNECTED
        s = "ON" if connected else "OFF"
        self.pt_status_lbl.setText(f"● PAN-TILT: {s}")
        self.pt_status_lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")
        self._log(f"[PAN-TILT] {'Connected' if connected else 'Disconnected'}")

    def _on_laser_connection(self, connected):
        self.laser_connected = connected
        c = COLOR_CONNECTED if connected else COLOR_DISCONNECTED
        s = "ON" if connected else "OFF"
        self.laser_status_lbl.setText(f"● LASER: {s}")
        self.laser_status_lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")
        self._log(f"[LASER] {'Connected' if connected else 'Disconnected'}")

    def _on_pelco_connection(self, connected):
        self.pelco_connected = connected
        c = COLOR_CONNECTED if connected else COLOR_DISCONNECTED
        s = "ON" if connected else "OFF"
        self.zoom_status_lbl.setText(f"● ZOOM: {s}")
        self.zoom_status_lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")
        self._log(f"[PELCO] {'Connected' if connected else 'Disconnected'}")

    def _on_onvif_connection(self, connected):
        self.onvif_connected = connected
        # Only update ZOOM label if Pelco is not connected (Pelco takes priority)
        if not self.pelco_connected:
            c = COLOR_CONNECTED if connected else COLOR_DISCONNECTED
            s = "ON" if connected else "OFF"
            self.zoom_status_lbl.setText(f"● ZOOM: {s}")
            self.zoom_status_lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")
        self._log(f"[ONVIF] {'Connected' if connected else 'Disconnected'}")

    # ════════════════ ACTIONS ════════════════
    def _get_tilt_sign(self):
        return -1 if self.tilt_invert_cb.isChecked() else 1

    def _stop_all(self):
        if self.is_connected:
            self.comm.stop_all()
        self.sim_pan_spd = 0.0
        self.sim_tilt_spd = 0.0
        self.pan_speed_ctrl.reset()
        self.tilt_speed_ctrl.reset()
        self._log("STOP ALL: $u# + $U#")

    def _go_home(self):
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
        if self.is_connected:
            self.comm.pan_diag()
            self._log("DIAG: PAN self-diagnostics started ($m,1#)")
        else:
            self.sim_pan_spd = 30.0
            self._log("[SIM] DIAG: PAN self-diagnostics (rotating 360°)")
            QTimer.singleShot(12000, lambda: self._sim_diag_done('pan'))

    def _tilt_diag(self):
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
            self.sim_pan_spd = 0
            self.sim_tilt_spd = 0
            self.sim_pan = pan
            self.sim_tilt = tilt
        self._log(f"GOTO: PAN={pan:.2f}° TILT={tilt:.2f}°")

    # ════════════════ LASER ════════════════
    def _on_laser_distance(self, dist, status):
        self.laser_dist_lbl.setText(f"{dist:.1f} m")
        if status & 0x0F == 0x04:
            label = "OUT OF RANGE"
            self.laser_target_lbl.setText(label)
            self.laser_target_lbl.setStyleSheet(
                f"color:{COLOR_ERROR}; font:600 10px 'SF Pro Display';")
        else:
            flags = []
            if status & 0x01: flags.append("NEAR")
            if status & 0x02: flags.append("FAR")
            multi = (status >> 4) & 0x0F
            label = "TARGET"
            if flags: label = " + ".join(flags)
            if multi > 0: label += f" (#{multi + 1})"
            self.laser_target_lbl.setText(label)
            self.laser_target_lbl.setStyleSheet(
                "color:#f5f5f7; font:600 10px 'SF Pro Display';")
        # Push distance overlay to camera widgets
        for cam in (self.cam1_widget, self.cam2_widget):
            if cam:
                cam.set_laser_distance(dist, status, label)

    def _laser_single(self):
        if not self.laser_connected:
            self._log("[LASER] Not connected")
            return
        threading.Thread(target=self._do_laser_single, daemon=True).start()

    def _do_laser_single(self):
        result = self.laser_comm.single_range()
        if result:
            dist, status = result
            self._log(f"[LASER] Range: {dist:.1f} m  status=0x{status:02X}")
        else:
            self._log("[LASER] Single range: no response")
            # Clear overlay on no response
            for cam in (self.cam1_widget, self.cam2_widget):
                if cam:
                    cam.clear_laser_overlay()

    def _laser_continuous(self):
        if not self.laser_connected:
            self._log("[LASER] Not connected")
            return
        if self.laser_comm.polling:
            self.laser_comm.stop_continuous()
            self.laser_cont_btn.setText("CONT")
            # Clear panel display
            self.laser_dist_lbl.setText("---.- m")
            self.laser_target_lbl.setText("NO TARGET")
            self.laser_target_lbl.setStyleSheet(
                "color:#636366; font:600 10px 'SF Pro Display';")
            # Clear overlay on camera widgets
            for cam in (self.cam1_widget, self.cam2_widget):
                if cam:
                    cam.clear_laser_overlay()
            self._log("[LASER] Continuous ranging stopped")
            # Sync overlay button state
            for cam in (self.cam1_widget, self.cam2_widget):
                cam.set_laser_state(False)
        else:
            self.laser_comm.start_continuous()
            self.laser_cont_btn.setText("STOP CONT")
            self._log("[LASER] Continuous ranging started")

    def _laser_stop(self):
        if self.laser_comm.polling:
            self.laser_comm.stop_continuous()
            self.laser_cont_btn.setText("CONT")
        self.laser_dist_lbl.setText("---.- m")
        self.laser_target_lbl.setText("NO TARGET")
        self.laser_target_lbl.setStyleSheet(
            "color:#636366; font:600 10px 'SF Pro Display';")
        # Clear overlay on camera widgets
        for cam in (self.cam1_widget, self.cam2_widget):
            if cam:
                cam.clear_laser_overlay()
        self._log("[LASER] Ranging stopped, display cleared")
        # Sync overlay button state
        for cam in (self.cam1_widget, self.cam2_widget):
            cam.set_laser_state(False)

    def _laser_selfcheck(self):
        if not self.laser_connected:
            self._log("[LASER] Not connected")
            return
        threading.Thread(target=self._do_laser_selfcheck, daemon=True).start()

    def _do_laser_selfcheck(self):
        resp = self.laser_comm.self_check()
        if resp and len(resp) >= 10:
            s = resp[5:9]
            self._log(f"[LASER] Self-check: status bytes {s.hex()}")
            s1 = s[2]
            s0 = s[3]
            checks = []
            checks.append("FPGA:" + ("OK" if s1 & 0x01 else "ERR"))
            checks.append("Temp:" + ("OK" if s1 & 0x40 else "ERR"))
            checks.append("Bias:" + ("OK" if s1 & 0x20 else "ERR"))
            checks.append("5V6:" + ("OK" if s0 & 0x01 else "ERR"))
            self._log(f"[LASER] Health: {' | '.join(checks)}")
        else:
            self._log("[LASER] Self-check: no response")

    # ════════════════ MAP BEAM CONFIG ════════════════
    def _apply_beam_config(self):
        """Apply MAP BEAM settings to the map widget."""
        if not hasattr(self, 'map_widget'):
            return
        lat = self._beam_lat
        lng = self._beam_lng
        offset = self._beam_offset
        length = self._beam_length
        self.map_widget.set_device_position(lat, lng)
        self.map_widget.set_beam_offset(offset)
        self.map_widget.set_beam_length(length)
        if hasattr(self, '_map_pos_lbl'):
            self._map_pos_lbl.setText(f"Device: {lat:.4f}, {lng:.4f}")
        self._log(f"[MAP] Beam: {lat:.6f},{lng:.6f} offset={offset:.1f}\u00b0 len={length}m")

    # ════════════════ ZOOM (ONVIF) ════════════════
    def _ensure_onvif_connected(self):
        """Auto-connect ONVIF if not connected, then return status."""
        if not self.onvif_connected:
            self._log(f"[ZOOM] Connecting ONVIF {self._onvif_ip}...")
            self.onvif_comm.connect_device(
                self._onvif_ip, self._onvif_user, self._onvif_pass, self._onvif_port)
        return self.onvif_connected

    def _zoom_tele(self):
        if not self._ensure_onvif_connected():
            return
        spd = self._zoom_speed / 100.0
        self.onvif_comm.zoom_in(spd)
        self._log(f"[ZOOM] Tele (in) speed={spd:.2f}")

    def _zoom_wide(self):
        if not self._ensure_onvif_connected():
            return
        spd = self._zoom_speed / 100.0
        self.onvif_comm.zoom_out(spd)
        self._log(f"[ZOOM] Wide (out) speed={spd:.2f}")

    def _zoom_stop(self):
        if not self.onvif_connected:
            return
        self.onvif_comm.zoom_stop()
        self._log("[ZOOM] Stop")

    def _focus_near(self):
        if not self._ensure_onvif_connected():
            return
        spd = self._zoom_speed / 100.0
        self.onvif_comm.focus_near(spd)
        self._log(f"[ZOOM] Focus Near speed={spd:.2f}")

    def _focus_far(self):
        if not self._ensure_onvif_connected():
            return
        spd = self._zoom_speed / 100.0
        self.onvif_comm.focus_far(spd)
        self._log(f"[ZOOM] Focus Far speed={spd:.2f}")

    def _focus_stop(self):
        if not self.onvif_connected:
            return
        self.onvif_comm.zoom_stop()
        self._log("[ZOOM] Focus Stop")

    def _focus_auto(self):
        if not self._ensure_onvif_connected():
            return
        self.onvif_comm.focus_auto()
        self._log("[ZOOM] Auto Focus")

    def _on_zoom_scroll(self, direction):
        """Handle mouse wheel zoom on camera video: +1=tele, -1=wide."""
        if not self._ensure_onvif_connected():
            return
        spd = self._zoom_speed / 100.0
        if direction > 0:
            self.onvif_comm.zoom_in(spd)
            self._log(f"[ZOOM] Scroll→Tele speed={spd:.2f}")
        else:
            self.onvif_comm.zoom_out(spd)
            self._log(f"[ZOOM] Scroll→Wide speed={spd:.2f}")
        # Restart stop timer — zoom stops 300ms after last scroll notch
        self._zoom_wheel_timer.start(300)

    # ════════════════ DETECTION & TRACKING ════════════════
    def _toggle_detection(self):
        """Start or stop YOLO detection on CAM1."""
        if self._detecting:
            # Stop detection
            self._detecting = False
            self._tracking = False
            self._track_timer.stop()
            if self.cam1_widget:
                self.cam1_widget.disable_detection()
            if self._detector:
                self._detector.reset_tracker()
            self.detect_btn.setChecked(False)
            self.detect_btn.setText("DETECT")
            self.detect_btn.setStyleSheet("")
            self.track_btn.setEnabled(False)
            self.track_btn.setChecked(False)
            self.track_btn.setText("TRACK")
            self.track_btn.setStyleSheet("")
            self.det_lock_btn.setEnabled(False)
            self.det_cycle_btn.setEnabled(False)
            self.det_stop_btn.setEnabled(False)
            self.det_target_lbl.setText("NO TARGET")
            self.det_target_lbl.setStyleSheet(
                "color:#636366; font:600 11px 'SF Pro Display';")
            self.det_fps_lbl.setText("FPS: --")
            self._track_target_id = None
            # Sync overlay button states
            for cam in (self.cam1_widget, self.cam2_widget):
                cam.set_detect_state(False)
                cam.set_track_state(False)
            self._log("[DETECT] Detection stopped")
            return

        # Start detection — initialize model if needed
        if self._detector is None:
            self._detector = YoloDetector()
            self._log("[DETECT] Initializing model...")
            self.det_model_lbl.setText("Loading...")
            # Run initialization in background thread to avoid blocking UI
            threading.Thread(target=self._init_detector_bg, daemon=True).start()
        else:
            self._start_detection_on_cam()

    def _init_detector_bg(self):
        """Initialize YOLO model in background thread."""
        ok = self._detector.initialize()
        # Use QTimer.singleShot(0, ...) to call on main thread
        QTimer.singleShot(0, lambda: self._on_detector_ready(ok))

    def _on_detector_ready(self, ok):
        """Called on main thread after detector initialization."""
        if ok:
            name = self._detector.model_name
            backend = self._detector.backend
            self.det_model_lbl.setText(f"Model: {name} ({backend})")
            self.det_model_lbl.setStyleSheet(
                "color:#30d158; font:600 10px 'SF Pro Display';")
            self._log(f"[DETECT] Loaded {name} ({backend})")
            self._apply_filter()
            self._start_detection_on_cam()
        else:
            reason = self._detector.backend if self._detector else "unknown"
            self.det_model_lbl.setText(f"Model: {reason}")
            self.det_model_lbl.setStyleSheet(
                "color:#ff453a; font:600 10px 'SF Pro Display';")
            self._log(f"[DETECT] Failed: {reason}")
            self._detecting = False
            self.detect_btn.setChecked(False)

    def _start_detection_on_cam(self):
        """Enable detection on CAM1 widget."""
        self._detecting = True
        self.detect_btn.setText("STOP DET")
        self.detect_btn.setStyleSheet(
            "background:#ff453a; color:white; font:600 11px 'SF Pro Display';")
        self.track_btn.setEnabled(True)
        self.det_stop_btn.setEnabled(True)
        if self.cam1_widget and self._detector:
            self.cam1_widget.enable_detection(self._detector)
        # Sync overlay button states
        for cam in (self.cam1_widget, self.cam2_widget):
            cam.set_detect_state(True)
        self._log("[DETECT] Detection started on CAM1")

    def _toggle_tracking(self):
        """Enable or disable auto-follow tracking."""
        if self._tracking:
            self._tracking = False
            self._track_timer.stop()
            self.track_btn.setChecked(False)
            self.track_btn.setText("TRACK")
            self.track_btn.setStyleSheet("")
            self.det_lock_btn.setEnabled(False)
            self.det_cycle_btn.setEnabled(False)
            self.det_target_lbl.setText("NO TARGET")
            self.det_target_lbl.setStyleSheet(
                "color:#636366; font:600 11px 'SF Pro Display';")
            self._track_target_id = None
            if self.cam1_widget:
                self.cam1_widget.select_track_target(None)
            # Sync overlay button states
            for cam in (self.cam1_widget, self.cam2_widget):
                cam.set_track_state(False)
            self._log("[TRACK] Auto-follow disabled")
            return

        self._tracking = True
        self.track_btn.setText("STOP TRK")
        self.track_btn.setStyleSheet(
            "background:#ff9f0a; color:white; font:600 11px 'SF Pro Display';")
        self.det_lock_btn.setEnabled(True)
        self.det_cycle_btn.setEnabled(True)
        self.det_stop_btn.setEnabled(True)
        self._track_timer.start()
        # Sync overlay button states
        for cam in (self.cam1_widget, self.cam2_widget):
            cam.set_track_state(True)
        self._log("[TRACK] Auto-follow enabled — select a target")

    def _on_filter_changed(self, idx):
        """Update class filter on the detector."""
        self._apply_filter()

    def _apply_filter(self):
        """Apply current filter selection to detector."""
        if not self._detector:
            return
        idx = self.det_filter_combo.currentIndex()
        if idx == 0:
            self._detector.set_classes(None)  # all
        elif idx == 1:
            self._detector.set_classes(FILTER_AIR)
        elif idx == 2:
            self._detector.set_classes(FILTER_DRONE_VEHICLE)
        self._log(f"[DETECT] Filter: {['All Classes','Air Targets','Drones+Vehicles'][idx]}")

    def _auto_lock_target(self):
        """Auto-select the best tracked target (largest air target, or largest any)."""
        if not self.cam1_widget:
            return
        targets = self.cam1_widget.get_tracked_targets()
        if not targets:
            self._log("[TRACK] No tracked targets available")
            return
        # Prefer air targets, then largest area
        air = [t for t in targets if t.is_air_target]
        best = max(air, key=lambda t: t.area) if air else max(targets, key=lambda t: t.area)
        self._select_track_id(best.track_id, best.class_name)

    def _cycle_target(self):
        """Cycle to the next tracked target."""
        if not self.cam1_widget:
            return
        targets = self.cam1_widget.get_tracked_targets()
        if not targets:
            return
        ids = [t.track_id for t in targets]
        if self._track_target_id in ids:
            idx = (ids.index(self._track_target_id) + 1) % len(ids)
        else:
            idx = 0
        t = targets[idx] if idx < len(targets) else targets[0]
        self._select_track_id(t.track_id, t.class_name)

    def _select_track_id(self, track_id, class_name=""):
        """Set a specific track ID as the follow target."""
        self._track_target_id = track_id
        if self.cam1_widget:
            self.cam1_widget.select_track_target(track_id)
        self.det_target_lbl.setText(f"LOCKED: #{track_id} {class_name.upper()}")
        self.det_target_lbl.setStyleSheet(
            "color:#30d158; font:600 11px 'SF Pro Display';")
        self._log(f"[TRACK] Locked target #{track_id} ({class_name})")

    def _stop_tracking(self):
        """Stop tracking and auto-follow."""
        self._tracking = False
        self._track_timer.stop()
        self._track_target_id = None
        if self.cam1_widget:
            self.cam1_widget.select_track_target(None)
        # Sync overlay button states
        for cam in (self.cam1_widget, self.cam2_widget):
            cam.set_track_state(False)
        self.track_btn.setChecked(False)
        self.track_btn.setText("TRACK")
        self.track_btn.setStyleSheet("")
        self.det_target_lbl.setText("NO TARGET")
        self.det_target_lbl.setStyleSheet(
            "color:#636366; font:600 11px 'SF Pro Display';")
        self.det_lock_btn.setEnabled(False)
        self.det_cycle_btn.setEnabled(False)
        if self.is_connected:
            self.comm.stop_all()
        self._log("[TRACK] Tracking stopped, all movement halted")

    def _on_detection_target(self, dx, dy, cls_name):
        """Store latest target offset from CAM1 detection thread."""
        self._last_det_dx = dx
        self._last_det_dy = dy
        self._last_det_cls = cls_name

    def _on_detections_updated(self, dets):
        """Update target info when detection list changes."""
        if not self._tracking or not self._track_target_id:
            return
        # Check if our target is still present
        found = False
        for d in dets:
            if d.track_id == self._track_target_id:
                found = True
                self.det_target_lbl.setText(
                    f"LOCKED: #{d.track_id} {d.class_name.upper()} {d.confidence:.0%}")
                break
        if not found:
            self.det_target_lbl.setText(f"TARGET #{self._track_target_id} LOST")
            self.det_target_lbl.setStyleSheet(
                "color:#ff9f0a; font:600 11px 'SF Pro Display';")

    def _on_detection_fps(self, fps):
        """Update FPS display."""
        self.det_fps_lbl.setText(f"FPS: {fps:.1f}")

    def _track_control_tick(self):
        """20 Hz proportional auto-follow controller."""
        if not self._tracking or self._track_target_id is None:
            return
        dx, dy = self._last_det_dx, self._last_det_dy
        cls = self._last_det_cls

        # Empty class name + zero offset = target lost
        if cls == "" and abs(dx) < 0.001 and abs(dy) < 0.001:
            # Target lost — stop movement
            if self.is_connected:
                self.comm.pan_stop()
                self.comm.tilt_stop()
            return

        # Dead zone — target is centered enough
        if abs(dx) < self._track_deadzone and abs(dy) < self._track_deadzone:
            if self.is_connected:
                self.comm.pan_stop()
                self.comm.tilt_stop()
            return

        # Calculate proportional speeds
        base_pan = self.pan_speed_ctrl.get_speed()
        base_tilt = self.tilt_speed_ctrl.get_speed()
        if base_pan < 0.1:
            base_pan = 20.0
        if base_tilt < 0.1:
            base_tilt = 10.0

        pan_spd = dx * self._track_gain * base_pan
        tilt_spd = -dy * self._track_gain * base_tilt

        # Clamp
        pan_spd = max(-base_pan, min(base_pan, pan_spd))
        tilt_spd = max(-base_tilt, min(base_tilt, tilt_spd))

        if self.is_connected:
            tilt_sign = self._get_tilt_sign()
            self.comm.pan_set_speed(pan_spd)
            self.comm.tilt_set_speed(tilt_spd * tilt_sign)

    # ════════════════ VIDEO OVERLAY BUTTONS ════════════════
    def _on_video_laser(self, on):
        """Video overlay LSR button: start/stop laser ranging."""
        if on:
            if not self.laser_connected:
                self._log("[LASER] Not connected")
                for cam in (self.cam1_widget, self.cam2_widget):
                    cam.set_laser_state(False)
                return
            self.laser_comm.start_continuous()
            self.laser_cont_btn.setText("STOP CONT")
            self._log("[LASER] Continuous ranging started")
        else:
            self._laser_stop()

    def _on_video_detect(self, on):
        """Video overlay DET button: start/stop detection."""
        # Sync state: if already in desired state, skip
        if self._detecting == on:
            return
        self._toggle_detection()

    def _on_video_track(self, on):
        """Video overlay TRK button: start/stop auto-follow."""
        if self._tracking == on:
            return
        # Tracking requires detection active
        if on and not self._detecting:
            self._log("[TRACK] Enable detection first")
            for cam in (self.cam1_widget, self.cam2_widget):
                cam.set_track_state(False)
            return
        if on and not self._track_target_id:
            # Auto-lock to best target if none selected
            self._auto_lock_target()
        self._toggle_tracking()

    def _on_video_filter(self, name):
        """Video filter changed on overlay."""
        # Sync filter to both cameras
        filter_map = {'NORMAL': 0, 'NVG': 1, 'EDGE': 2, 'BW': 3}
        mode = filter_map.get(name, 0)
        for cam in (self.cam1_widget, self.cam2_widget):
            cam.set_video_filter(mode)
        self._log(f"[VIDEO] Filter: {name}")

    def _on_thermal_temp(self, spot, max_t, min_t):
        """Update thermal temperature display in status bar."""
        self.temp_lbl.setText(f"SPOT: {spot:.1f}\u00b0C  MAX: {max_t:.1f}\u00b0C")

    # ════════════════ D-PAD ════════════════
    def _on_dpad_pressed(self, d):
        if d == 'STOP':
            self._stop_all()
            return
        pan_spd = self.pan_speed_ctrl.get_speed()
        tilt_spd = self.tilt_speed_ctrl.get_speed()
        if pan_spd < 0.1:
            pan_spd = 20.0
        if tilt_spd < 0.1:
            tilt_spd = 10.0
        dir_map = {
            'UP':         (0.0,      tilt_spd),
            'DOWN':       (0.0,     -tilt_spd),
            'LEFT':       (-pan_spd,  0.0),
            'RIGHT':      (pan_spd,   0.0),
            'UP_RIGHT':   (pan_spd,   tilt_spd),
            'UP_LEFT':    (-pan_spd,  tilt_spd),
            'DOWN_RIGHT': (pan_spd,  -tilt_spd),
            'DOWN_LEFT':  (-pan_spd, -tilt_spd),
        }
        p_spd, t_spd = dir_map.get(d, (0, 0))
        if self.is_connected:
            tilt_sign = self._get_tilt_sign()
            if p_spd != 0:
                self.comm.pan_set_speed(p_spd)
            if t_spd != 0:
                self.comm.tilt_set_speed(t_spd * tilt_sign)
        self.sim_pan_spd = p_spd
        self.sim_tilt_spd = t_spd
        self._log(f"[DPAD] {d} → PAN={p_spd:.0f} TILT={t_spd:.0f} °/s")

    def _on_dpad_released(self, d):
        if d == 'STOP':
            return
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
        if self.is_connected:
            return
        dt = 0.03
        if abs(self.sim_pan_spd) > 0.01:
            self.sim_pan = (self.sim_pan + self.sim_pan_spd * dt) % 360
        if abs(self.sim_tilt_spd) > 0.01:
            self.sim_tilt = max(-90, min(45, self.sim_tilt + self.sim_tilt_spd * dt))
        self.pan_pos_lbl.setText(f"PAN: {self.sim_pan:.2f}\u00b0")
        self.tilt_pos_lbl.setText(f"TILT: {self.sim_tilt:.2f}\u00b0")
        # Push sim PAN to map beam
        if hasattr(self, 'map_widget'):
            self.map_widget.set_pan_angle(self.sim_pan)
        self.pan_spd_lbl.setText(f"P-SPD: {self.sim_pan_spd:.1f}")
        self.tilt_spd_lbl.setText(f"T-SPD: {self.sim_tilt_spd:.1f}")
        self.temp_lbl.setText("TEMP: 25.0")
        moving = abs(self.sim_pan_spd) > 0.1 or abs(self.sim_tilt_spd) > 0.1
        self.action_lbl.setText("MOVING" if moving else "IDLE")
        self.action_lbl.setStyleSheet(
            f"color:{COLOR_ACTIVE};font:600 10px 'SF Pro Display';" if moving
            else "color:#8e8e93;font:600 10px 'SF Pro Display';")

    # ════════════════ LOG ════════════════
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{ts}] {msg}")
