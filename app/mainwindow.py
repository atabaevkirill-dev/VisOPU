"""Main application window for VisOPU."""

import threading
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QFrame, QGridLayout,
                              QSpinBox, QDoubleSpinBox, QLineEdit, QCheckBox,
                              QPlainTextEdit, QComboBox, QSplitter,
                              QDialog, QFormLayout, QDialogButtonBox, QMenu,
                              QSizePolicy)
from PyQt6.QtCore import Qt, QTimer, QPoint, QSettings, QObject
from PyQt6.QtGui import QAction, QFont, QColor

from app.communicators import DeviceCommunicator, LaserCommunicator, PelcoDCommunicator, ONVIFCommunicator
from app.widgets import (CollapsiblePanel, DirectionPad,
                          SpeedControl, CameraWidget, SlidingPanel, HAS_CV2)
from app.detector import YoloDetector, FILTER_ALL, FILTER_AIR, FILTER_DRONE_VEHICLE
from app.styles import (apply_apple_dark_style, STYLE_GO_BUTTON, STYLE_STOP_ALL,
                         STYLE_HOME_BUTTON, STYLE_DIAG_BUTTON, STYLE_LOG_TEXT,
                         COLOR_CONNECTED, COLOR_DISCONNECTED, COLOR_ERROR,
                         COLOR_ACTIVE)


# ═══════════════════════════════════════════════════════════════════
# CONNECTION DIALOG
# ═══════════════════════════════════════════════════════════════════

class ConnectionDialog(QDialog):
    """Generic connection dialog for devices."""

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
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_values(self):
        return {k: v.text() for k, v in self.inputs.items()}


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

        self._build_menu()
        self._build_ui()
        apply_apple_dark_style(self)
        self._connect_signals()

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

        dev_menu.addSeparator()

        act_cam1 = QAction("CAM1 (IP Camera)...", self)
        act_cam1.triggered.connect(self._connect_cam1_dialog)
        dev_menu.addAction(act_cam1)

        act_cam2 = QAction("CAM2 (Thermal)...", self)
        act_cam2.triggered.connect(self._connect_cam2_dialog)
        dev_menu.addAction(act_cam2)

        dev_menu.addSeparator()

        act_zoom = QAction("ZOOM Camera (ONVIF)...", self)
        act_zoom.triggered.connect(self._connect_zoom_dialog)
        dev_menu.addAction(act_zoom)

        dev_menu.addSeparator()

        act_ret = QAction("Reticle: Crosshair", self)
        self._reticle_action = act_ret
        ret_menu = dev_menu.addMenu("Reticle")
        for name, idx in [("Crosshair", 0), ("Mil-Dot", 1), ("Combat", 2)]:
            a = QAction(name, self)
            a.triggered.connect(lambda checked, i=idx: self._set_reticle(i))
            ret_menu.addAction(a)

        # View menu
        view_menu = menubar.addMenu("&View")
        self._view_menu = view_menu

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
        # Save cameras window geometry
        if hasattr(self, '_cameras_win'):
            s.setValue("cam_win_geometry", self._cameras_win.geometry())

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
                self._log(f"[CAM] CAM{cam_idx} connected: {url}")
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
        self._reticle_action.setText(f"Reticle: {names[idx]}")
        self._log(f"[CAM] Reticle: {names[idx]}")

    # ════════════════ VIEW TOGGLES ════════════════
    def _toggle_cameras_view(self):
        if self._cameras_win.isVisible():
            self._cameras_win.hide()
        else:
            self._cameras_win.show()
            self._cameras_win.raise_()

    # ════════════════ RESIZE ════════════════
    def resizeEvent(self, event):
        super().resizeEvent(event)

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
        # Clean up floating cameras window
        if hasattr(self, '_cameras_win'):
            self._cameras_win.deleteLater()
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
        self.pan_speed_ctrl = SpeedControl("PAN SPEED °/s", -50, 50)
        spdl.addWidget(self.pan_speed_ctrl)
        self.tilt_speed_ctrl = SpeedControl("TILT SPEED °/s", -20, 20)
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

        # ─── CENTER — D-Pad only ───
        center = QVBoxLayout()
        center.setContentsMargins(4, 0, 4, 0)
        center.setSpacing(8)

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

        # D-Pad
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

        # ─── RIGHT SLIDING PANEL ───
        self.right_panel = SlidingPanel(220, side='right')
        right_content = QWidget()
        right = QVBoxLayout(right_content)
        right.setContentsMargins(8, 8, 8, 8)
        right.setSpacing(2)

        # Laser rangefinder controls
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
        laser.content_layout().addLayout(las)
        right.addWidget(laser)

        # Zoom camera (Pelco-D)
        zoom = CollapsiblePanel("ZOOM CAMERA")
        zl = QVBoxLayout()
        zoom_row = QHBoxLayout()
        self.zoom_tele_btn = QPushButton("TELE +")
        self.zoom_tele_btn.setStyleSheet(STYLE_GO_BUTTON)
        self.zoom_tele_btn.pressed.connect(self._zoom_tele)
        self.zoom_tele_btn.released.connect(self._zoom_stop)
        zoom_row.addWidget(self.zoom_tele_btn)
        self.zoom_wide_btn = QPushButton("WIDE −")
        self.zoom_wide_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.zoom_wide_btn.pressed.connect(self._zoom_wide)
        self.zoom_wide_btn.released.connect(self._zoom_stop)
        zoom_row.addWidget(self.zoom_wide_btn)
        zl.addLayout(zoom_row)
        self.zoom_speed_spin = QSpinBox()
        self.zoom_speed_spin.setRange(10, 100)
        self.zoom_speed_spin.setValue(50)
        self.zoom_speed_spin.setSuffix(" %")
        self.zoom_speed_spin.setToolTip("Zoom speed: 10-100%")
        zl.addWidget(self.zoom_speed_spin)
        zoom_stop_btn = QPushButton("ZOOM STOP")
        zoom_stop_btn.setStyleSheet(STYLE_STOP_ALL)
        zoom_stop_btn.clicked.connect(self._zoom_stop)
        zl.addWidget(zoom_stop_btn)
        focus_row = QHBoxLayout()
        self.focus_near_btn = QPushButton("NEAR")
        self.focus_near_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.focus_near_btn.pressed.connect(self._focus_near)
        self.focus_near_btn.released.connect(self._focus_stop)
        focus_row.addWidget(self.focus_near_btn)
        self.focus_far_btn = QPushButton("FAR")
        self.focus_far_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.focus_far_btn.pressed.connect(self._focus_far)
        self.focus_far_btn.released.connect(self._focus_stop)
        focus_row.addWidget(self.focus_far_btn)
        zl.addLayout(focus_row)
        self.focus_auto_btn = QPushButton("AUTO FOCUS")
        self.focus_auto_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.focus_auto_btn.clicked.connect(self._focus_auto)
        zl.addWidget(self.focus_auto_btn)
        zoom.content_layout().addLayout(zl)
        right.addWidget(zoom)

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
            nl.setStyleSheet("color:#636366; font:10px 'SF Pro Display';")
            val.setStyleSheet("color:#f5f5f7; font:600 11px 'SF Pro Display';")
            sg.addWidget(nl, i, 0)
            sg.addWidget(val, i, 1)
        st.content_layout().addLayout(sg)
        right.addWidget(st)

        # Log
        lg = CollapsiblePanel("PROTOCOL LOG")
        ll = QVBoxLayout()
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(50)
        self.log_text.setStyleSheet(STYLE_LOG_TEXT)
        self.log_text.setFixedHeight(200)
        ll.addWidget(self.log_text)
        lg.content_layout().addLayout(ll)
        right.addWidget(lg)

        right.addStretch()
        self.right_panel.set_content_layout(right)
        root.addWidget(self.right_panel)

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

    # ════════════════ CALLBACKS ════════════════
    def _on_real_pan(self, v):
        self.real_pan = v
        self.pan_pos_lbl.setText(f"{v:.2f}°")

    def _on_real_tilt(self, v):
        self.real_tilt = v
        self.tilt_pos_lbl.setText(f"{v:.2f}°")

    def _on_real_pan_spd(self, v):
        self.real_pan_spd = v
        self.pan_spd_lbl.setText(f"{v:.1f} °/s")
        self.action_lbl.setText("MOVING" if abs(v) > 0.1 else "IDLE")
        self.action_lbl.setStyleSheet(
            f"color:{COLOR_ACTIVE};font:600 11px 'SF Pro Display';" if abs(v) > 0.1
            else "color:#f5f5f7;font:600 11px 'SF Pro Display';")

    def _on_real_tilt_spd(self, v):
        self.real_tilt_spd = v
        self.tilt_spd_lbl.setText(f"{v:.1f} °/s")

    def _on_real_temp(self, v):
        self.real_temp = v
        self.temp_lbl.setText(f"{v:.1f} °C")

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
        self._log(f"[ZOOM] {'Connected' if connected else 'Disconnected'}")

    def _on_onvif_connection(self, connected):
        self.onvif_connected = connected
        c = COLOR_CONNECTED if connected else COLOR_DISCONNECTED
        s = "ON" if connected else "OFF"
        self.zoom_status_lbl.setText(f"● ZOOM: {s}")
        self.zoom_status_lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")
        self._log(f"[ZOOM] ONVIF {'Connected' if connected else 'Disconnected'}")

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
        spd = self.zoom_speed_spin.value() / 100.0
        self.onvif_comm.zoom_in(spd)
        self._log(f"[ZOOM] Tele (in) speed={spd:.2f}")

    def _zoom_wide(self):
        if not self._ensure_onvif_connected():
            return
        spd = self.zoom_speed_spin.value() / 100.0
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
        spd = self.zoom_speed_spin.value() / 100.0
        self.onvif_comm.focus_near(spd)
        self._log(f"[ZOOM] Focus Near speed={spd:.2f}")

    def _focus_far(self):
        if not self._ensure_onvif_connected():
            return
        spd = self.zoom_speed_spin.value() / 100.0
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
        spd = self.zoom_speed_spin.value() / 100.0
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
        if abs(base_pan) < 0.1:
            base_pan = 20.0
        if abs(base_tilt) < 0.1:
            base_tilt = 10.0

        pan_spd = dx * self._track_gain * abs(base_pan)
        tilt_spd = -dy * self._track_gain * abs(base_tilt)

        # Clamp
        pan_spd = max(-abs(base_pan), min(abs(base_pan), pan_spd))
        tilt_spd = max(-abs(base_tilt), min(abs(base_tilt), tilt_spd))

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

    # ════════════════ D-PAD ════════════════
    def _on_dpad_pressed(self, d):
        if d == 'STOP':
            self._stop_all()
            return
        pan_spd = self.pan_speed_ctrl.get_speed()
        tilt_spd = self.tilt_speed_ctrl.get_speed()
        if abs(pan_spd) < 0.1:
            pan_spd = 20.0
        if abs(tilt_spd) < 0.1:
            tilt_spd = 10.0
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
        self.pan_pos_lbl.setText(f"{self.sim_pan:.2f}°")
        self.tilt_pos_lbl.setText(f"{self.sim_tilt:.2f}°")
        self.pan_spd_lbl.setText(f"{self.sim_pan_spd:.1f} °/s")
        self.tilt_spd_lbl.setText(f"{self.sim_tilt_spd:.1f} °/s")
        self.temp_lbl.setText("25.0 °C")
        moving = abs(self.sim_pan_spd) > 0.1 or abs(self.sim_tilt_spd) > 0.1
        self.action_lbl.setText("MOVING" if moving else "IDLE")
        self.action_lbl.setStyleSheet(
            f"color:{COLOR_ACTIVE};font:600 11px 'SF Pro Display';" if moving
            else "color:#f5f5f7;font:600 11px 'SF Pro Display';")

    # ════════════════ LOG ════════════════
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{ts}] {msg}")
