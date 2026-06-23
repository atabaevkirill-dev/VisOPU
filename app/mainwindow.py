"""Main application window for VisOPU."""

from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QFrame, QGridLayout,
                              QDoubleSpinBox, QCheckBox,
                              QPlainTextEdit, QComboBox, QSplitter,
                              QMenuBar, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction

from app.communicators import DeviceCommunicator, LaserCommunicator, PelcoDCommunicator, ONVIFCommunicator
from app.widgets import (CollapsiblePanel, DirectionPad,
                          SpeedControl, CameraWidget, SlidingPanel,
                          YandexMapWidget, DashboardWidget, HAS_CV2)
from app.detector import YoloDetector
from app.i18n import tr, set_language, get_language
from app.styles import (apply_apple_dark_style, STYLE_GO_BUTTON, STYLE_STOP_ALL,
                         STYLE_HOME_BUTTON, STYLE_DIAG_BUTTON, STYLE_LOG_TEXT,
                         COLOR_CONNECTED, COLOR_DISCONNECTED, COLOR_ERROR,
                         COLOR_ACTIVE)
from app.dialogs import ConnectionDialog, HideOnCloseFilter, StatusLink
from app.settings import AppSettings
from app.controllers import (
    PTControllerMixin, LaserControllerMixin,
    DetectionControllerMixin, ZoomControllerMixin,
)


class MainWindow(QMainWindow, PTControllerMixin, LaserControllerMixin,
                 DetectionControllerMixin, ZoomControllerMixin):
    _LBL_FONT = StatusLink._LBL_FONT

    def __init__(self):
        super().__init__()
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
        self.cfg = AppSettings()
        set_language(self.cfg.value("language", "ru"))
        self._load_settings()

        # Apply translated window title
        self.setWindowTitle(tr('window_title'))

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
                    tr('map_device_pos').format(lat=self._beam_lat, lng=self._beam_lng))

        # Status bar
        self.statusBar().showMessage(tr('status_ready'))

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

    def _load_settings(self):
        """Load saved connection parameters from AppSettings."""
        self.cfg.load()
        c = self.cfg
        self._pan_tilt_ip = c.pan_tilt_ip
        self._pan_tilt_port = c.pan_tilt_port
        self._laser_ip = c.laser_ip
        self._laser_port = c.laser_port
        self._cam1_ip = c.cam1_ip
        self._cam1_user = c.cam1_user
        self._cam1_pass = c.cam1_pass
        self._cam2_ip = c.cam2_ip
        self._cam2_user = c.cam2_user
        self._cam2_pass = c.cam2_pass
        self._pelco_ip = c.pelco_ip
        self._pelco_port = c.pelco_port
        self._pelco_addr = c.pelco_addr
        self._onvif_ip = c.onvif_ip
        self._onvif_port = c.onvif_port
        self._onvif_user = c.onvif_user
        self._onvif_pass = c.onvif_pass
        self._beam_lat = c.beam_lat
        self._beam_lng = c.beam_lng
        self._beam_offset = c.beam_offset
        self._beam_length = c.beam_length
        if hasattr(self, 'tilt_invert_cb'):
            self.tilt_invert_cb.setChecked(c.tilt_invert)

    def _save_settings(self):
        """Save connection parameters to persistent storage."""
        c = self.cfg
        c.pan_tilt_ip = self._pan_tilt_ip
        c.pan_tilt_port = self._pan_tilt_port
        c.laser_ip = self._laser_ip
        c.laser_port = self._laser_port
        c.cam1_ip = self._cam1_ip
        c.cam1_user = self._cam1_user
        c.cam1_pass = self._cam1_pass
        c.cam2_ip = self._cam2_ip
        c.cam2_user = self._cam2_user
        c.cam2_pass = self._cam2_pass
        c.pelco_ip = self._pelco_ip
        c.pelco_port = self._pelco_port
        c.pelco_addr = self._pelco_addr
        c.onvif_ip = self._onvif_ip
        c.onvif_port = self._onvif_port
        c.onvif_user = self._onvif_user
        c.onvif_pass = self._onvif_pass
        c.tilt_invert = (
            self.tilt_invert_cb.isChecked() if hasattr(self, 'tilt_invert_cb') else True)
        c.beam_lat = self._beam_lat
        c.beam_lng = self._beam_lng
        c.beam_offset = self._beam_offset
        c.beam_length = self._beam_length
        extra = {}
        if hasattr(self, '_cameras_win'):
            extra['cam_win_geometry'] = self._cameras_win.geometry()
        if hasattr(self, '_map_win'):
            extra['map_win_geometry'] = self._map_win.geometry()
        c.save(extra)

    def _build_menu(self):
        menubar = self.menuBar()
        dev_menu = menubar.addMenu(tr('menu_devices'))

        act_pt = QAction(tr('menu_pt_conn'), self)
        act_pt.triggered.connect(self._connect_pan_tilt_dialog)
        dev_menu.addAction(act_pt)

        act_las = QAction(tr('menu_laser_conn'), self)
        act_las.triggered.connect(self._connect_laser_dialog)
        dev_menu.addAction(act_las)

        # View menu
        view_menu = menubar.addMenu(tr('menu_view'))
        self._view_menu = view_menu

        # Language menu
        lang_menu = menubar.addMenu(tr('menu_language'))
        act_ru = QAction(tr('lang_russian'), self)
        act_ru.setCheckable(True)
        act_ru.setChecked(get_language() == 'ru')
        act_ru.triggered.connect(lambda: self._switch_language('ru'))
        lang_menu.addAction(act_ru)
        self._act_lang_ru = act_ru

        act_en = QAction(tr('lang_english'), self)
        act_en.setCheckable(True)
        act_en.setChecked(get_language() == 'en')
        act_en.triggered.connect(lambda: self._switch_language('en'))
        lang_menu.addAction(act_en)
        self._act_lang_en = act_en
    def _switch_language(self, lang):
        """Switch UI language and rebuild the interface."""
        if get_language() == lang:
            return
        set_language(lang)
        self.cfg.set_value("language", lang)
        self._retranslate_ui()
    def _retranslate_ui(self):
        """Update all UI strings after language change."""
        # Window title
        self.setWindowTitle(tr('window_title'))

        # Menu bar (rebuild)
        self.menuBar().clear()
        self._build_menu()
        # Re-add view menu items
        if hasattr(self, '_act_cams'):
            self._act_cams.setText(tr('menu_cameras_win'))
            self._view_menu.addAction(self._act_cams)
        if hasattr(self, '_act_map'):
            self._act_map.setText(tr('menu_map_win'))
            self._view_menu.addAction(self._act_map)
        if hasattr(self, '_log_action'):
            self._log_action.setText(tr('menu_log_win'))

        # Left panel sections & controls
        if hasattr(self, '_panel_status'):
            self._panel_status.setTitle(tr('sec_device_status'))
        if hasattr(self, '_panel_speed'):
            self._panel_speed.setTitle(tr('sec_speed_setting'))
        if hasattr(self, '_panel_goto'):
            self._panel_goto.setTitle(tr('sec_goto_position'))
        if hasattr(self, '_panel_diag'):
            self._panel_diag.setTitle(tr('sec_tilt_diag'))
        if hasattr(self, 'pan_speed_ctrl'):
            self.pan_speed_ctrl.setTitle(tr('pan_speed'))
        if hasattr(self, 'tilt_speed_ctrl'):
            self.tilt_speed_ctrl.setTitle(tr('tilt_speed'))
        if hasattr(self, 'tilt_invert_cb'):
            self.tilt_invert_cb.setText(tr('invert_tilt'))

        # Right panel sections
        if hasattr(self, '_panel_dpad'):
            self._panel_dpad.setTitle(tr('sec_control_pad'))
        if hasattr(self, '_panel_laser'):
            self._panel_laser.setTitle(tr('sec_laser_rangefinder'))
        if hasattr(self, '_panel_det'):
            self._panel_det.setTitle(tr('sec_detection'))

        # Right panel — detection filter combo
        if hasattr(self, 'det_filter_combo'):
            old_idx = self.det_filter_combo.currentIndex()
            self.det_filter_combo.clear()
            self.det_filter_combo.addItems([tr('filter_all'), tr('filter_air'), tr('filter_drone_vehicle')])
            self.det_filter_combo.setCurrentIndex(old_idx)

        # Dynamic state labels
        if hasattr(self, 'action_lbl'):
            moving = abs(self.real_pan_spd) > 0.1
            self.action_lbl.setText(tr('dash_moving') if moving else tr('dash_idle'))

        # Floating window titles
        if hasattr(self, '_cameras_win'):
            self._cameras_win.setWindowTitle(tr('win_cameras'))
        if hasattr(self, '_map_win'):
            self._map_win.setWindowTitle(tr('win_map'))
        if hasattr(self, '_log_win'):
            self._log_win.setWindowTitle(tr('win_log'))

        # Cameras menu (rebuild)
        if hasattr(self, '_cameras_win') and hasattr(self, '_cam_menubar'):
            self._build_cameras_menu()

        # Log message
        self._log(f"[UI] Language: {'Русский' if get_language() == 'ru' else 'English'}")
    def _connect_pan_tilt_dialog(self):
        dlg = ConnectionDialog(tr('dlg_pt_conn'), [
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
        dlg = ConnectionDialog(tr('dlg_laser_conn'), [
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
        dlg = ConnectionDialog(tr('dlg_cam1'), [
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
        dlg = ConnectionDialog(tr('dlg_cam2'), [
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
        dlg = ConnectionDialog(tr('dlg_zoom_onvif'), [
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
            s = tr('status_off')
        else:
            ok = widget.connect_stream(url, is_thermal)
            if ok:
                self._log(f"[CAM] CAM{cam_idx} connected: {url}"
                          + (f" [THERMAL MODE]" if is_thermal else ""))
                # Show and raise cameras window
                self._cameras_win.show()
                self._cameras_win.raise_()
                c = COLOR_CONNECTED
                s = tr('status_on')
            else:
                self._log(f"[CAM] CAM{cam_idx} connection failed")
                c = COLOR_ERROR
                s = tr('status_err')
        # Update status indicator
        lbl = self.cam1_status_lbl if cam_idx == 1 else self.cam2_status_lbl
        lbl.setText(f"● CAM{cam_idx}: {s}")
        lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")
        if cam_idx == 1:
            self.cam1_connected = widget.streaming
        else:
            self.cam2_connected = widget.streaming
    def _build_cameras_menu(self):
        """Build menu bar inside the cameras floating window."""
        if hasattr(self, '_cam_menubar'):
            menubar = self._cam_menubar
            menubar.clear()
        else:
            menubar = QMenuBar(self._cameras_win)
            self._cam_menubar = menubar
        menubar.setStyleSheet(
            "QMenuBar{background:#2d2d2d;border-bottom:1px solid #3c3c3c;}"
            "QMenuBar::item{color:#98989d;padding:4px 10px;font:600 10px 'SF Pro Display';}"
            "QMenuBar::item:selected{background:#3a3a3c;color:#f5f5f7;}"
            "QMenu{background:#2d2d2d;border:1px solid #3c3c3c;}"
            "QMenu::item{color:#f5f5f7;padding:5px 24px;font:500 11px 'SF Pro Display';}"
            "QMenu::item:selected{background:#0a84ff;}")

        # ── Connection menu ──
        conn_menu = menubar.addMenu(tr('cam_menu_connection'))
        act_cam1 = QAction(tr('cam_menu_cam1'), self._cameras_win)
        act_cam1.triggered.connect(self._connect_cam1_dialog)
        conn_menu.addAction(act_cam1)

        act_cam2 = QAction(tr('cam_menu_cam2'), self._cameras_win)
        act_cam2.triggered.connect(self._connect_cam2_dialog)
        conn_menu.addAction(act_cam2)

        conn_menu.addSeparator()

        act_zoom = QAction(tr('cam_menu_zoom'), self._cameras_win)
        act_zoom.triggered.connect(self._connect_zoom_dialog)
        conn_menu.addAction(act_zoom)

        # ── Settings menu ──
        settings_menu = menubar.addMenu(tr('cam_menu_settings'))

        # Reticle submenu
        ret_menu = settings_menu.addMenu(tr('cam_menu_reticle'))
        for name, idx in [(tr('reticle_crosshair'), 0), (tr('reticle_mildot'), 1), (tr('reticle_combat'), 2)]:
            a = QAction(name, self._cameras_win)
            a.triggered.connect(lambda checked, i=idx: self._set_reticle(i))
            ret_menu.addAction(a)

        # Detection filter submenu
        filt_menu = settings_menu.addMenu(tr('cam_menu_det_filter'))
        for name, idx in [(tr('filter_all'), 0), (tr('filter_air'), 1), (tr('filter_drone_vehicle'), 2)]:
            a = QAction(name, self._cameras_win)
            a.triggered.connect(lambda checked, i=idx: self._menu_set_filter(i))
            filt_menu.addAction(a)

        settings_menu.addSeparator()

        # Zoom speed
        act_zoom_spd = QAction(tr('cam_menu_zoom_speed'), self._cameras_win)
        act_zoom_spd.triggered.connect(self._menu_set_zoom_speed)
        settings_menu.addAction(act_zoom_spd)

        # Tracking gain
        act_gain = QAction(tr('cam_menu_track_gain'), self._cameras_win)
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
        val, ok = QInputDialog.getInt(self, tr('dlg_zoom_speed'), tr('dlg_zoom_speed_prompt'),
                                       cur, 10, 100, 5)
        if ok:
            self._zoom_speed = val
    def _menu_set_track_gain(self):
        """Dialog to set tracking gain."""
        from PyQt6.QtWidgets import QInputDialog
        val, ok = QInputDialog.getDouble(self, tr('dlg_track_gain'), tr('dlg_track_gain_prompt'),
                                          self._track_gain, 0.1, 10.0, 2, 0.1)
        if ok:
            self._track_gain = val
    def _menu_beam_config(self):
        """Dialog to set map beam position (called from map window toolbar)."""
        from PyQt6.QtWidgets import QInputDialog
        lat, ok = QInputDialog.getDouble(self, tr('dlg_beam_lat'), tr('dlg_latitude'),
                                          getattr(self, '_beam_lat', 55.751574), -90, 90, 6, step=0.001)
        if not ok:
            return
        lng, ok = QInputDialog.getDouble(self, tr('dlg_beam_lng'), tr('dlg_longitude'),
                                          getattr(self, '_beam_lng', 37.573856), -180, 180, 6, step=0.001)
        if not ok:
            return
        off, ok = QInputDialog.getDouble(self, tr('dlg_beam_offset'), tr('dlg_beam_offset'),
                                          getattr(self, '_beam_offset', 0.0), -180, 180, 1, step=0.5)
        if not ok:
            return
        length, ok = QInputDialog.getInt(self, tr('dlg_beam_length'), tr('dlg_beam_length'),
                                          getattr(self, '_beam_length', 3000), 100, 50000, 100)
        if not ok:
            return
        self._beam_lat = lat
        self._beam_lng = lng
        self._beam_offset = off
        self._beam_length = length
        self._apply_beam_config()
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
        status_panel = CollapsiblePanel(tr('sec_device_status'))
        self._panel_status = status_panel
        sl = QGridLayout()
        sl.setSpacing(4)
        _lbl_font = self._LBL_FONT
        _off = tr('status_off')
        self.pt_status_lbl = StatusLink(f"\u25cf PAN-TILT: {_off}")
        self.pt_status_lbl.set_status_style(f"color:{COLOR_DISCONNECTED}; {_lbl_font}")
        self.pt_status_lbl.set_callback(self._connect_pan_tilt_dialog)
        self.laser_status_lbl = StatusLink(f"\u25cf LASER: {_off}")
        self.laser_status_lbl.set_status_style(f"color:{COLOR_DISCONNECTED}; {_lbl_font}")
        self.laser_status_lbl.set_callback(self._connect_laser_dialog)
        self.cam1_status_lbl = StatusLink(f"\u25cf CAM1: {_off}")
        self.cam1_status_lbl.set_status_style(f"color:{COLOR_DISCONNECTED}; {_lbl_font}")
        self.cam1_status_lbl.set_callback(self._connect_cam1_dialog)
        self.cam2_status_lbl = StatusLink(f"\u25cf CAM2: {_off}")
        self.cam2_status_lbl.set_status_style(f"color:{COLOR_DISCONNECTED}; {_lbl_font}")
        self.cam2_status_lbl.set_callback(self._connect_cam2_dialog)
        self.zoom_status_lbl = StatusLink(f"\u25cf ZOOM: {_off}")
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
        spd = CollapsiblePanel(tr('sec_speed_setting'))
        self._panel_speed = spd
        spdl = QVBoxLayout()
        self.pan_speed_ctrl = SpeedControl(tr('pan_speed'), 0, 50)
        spdl.addWidget(self.pan_speed_ctrl)
        self.tilt_speed_ctrl = SpeedControl(tr('tilt_speed'), 0, 20)
        spdl.addWidget(self.tilt_speed_ctrl)
        spd.content_layout().addLayout(spdl)
        left.addWidget(spd)

        # Go-to position
        pos = CollapsiblePanel(tr('sec_goto_position'))
        self._panel_goto = pos
        pl = QGridLayout()
        pl.addWidget(QLabel(tr('pan_deg')), 0, 0)
        self.pan_pos_spin = QDoubleSpinBox()
        self.pan_pos_spin.setRange(0, 359.99)
        self.pan_pos_spin.setDecimals(2)
        pl.addWidget(self.pan_pos_spin, 0, 1)
        pl.addWidget(QLabel(tr('tilt_deg')), 1, 0)
        self.tilt_pos_spin = QDoubleSpinBox()
        self.tilt_pos_spin.setRange(-90, 45)
        self.tilt_pos_spin.setDecimals(2)
        pl.addWidget(self.tilt_pos_spin, 1, 1)
        go_btn = QPushButton(tr('btn_go'))
        go_btn.setStyleSheet(STYLE_GO_BUTTON)
        go_btn.clicked.connect(self._goto_position)
        pl.addWidget(go_btn, 2, 0, 1, 2)
        pos.content_layout().addLayout(pl)
        left.addWidget(pos)

        # STOP ALL
        stop_btn = QPushButton(tr('btn_stop_all'))
        stop_btn.setStyleSheet(STYLE_STOP_ALL)
        stop_btn.clicked.connect(self._stop_all)
        left.addWidget(stop_btn)

        # HOME button
        home_btn = QPushButton(tr('btn_home'))
        home_btn.setStyleSheet(STYLE_HOME_BUTTON)
        home_btn.clicked.connect(self._go_home)
        left.addWidget(home_btn)

        # TILT invert + Diagnostics
        diag = CollapsiblePanel(tr('sec_tilt_diag'))
        self._panel_diag = diag
        dl = QVBoxLayout()
        self.tilt_invert_cb = QCheckBox(tr('invert_tilt'))
        self.tilt_invert_cb.setChecked(True)  # default ON
        # Load saved preference (override default if previously saved)
        saved_invert = self.cfg.tilt_invert
        if saved_invert is not None:
            self.tilt_invert_cb.setChecked(str(saved_invert).lower() in ("true", "1", "yes"))
        self.tilt_invert_cb.setStyleSheet("color:#98989d; font:600 11px 'SF Pro Display';")
        dl.addWidget(self.tilt_invert_cb)
        diag_row = QHBoxLayout()
        pan_diag_btn = QPushButton(tr('btn_pan_diag'))
        pan_diag_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        pan_diag_btn.clicked.connect(self._pan_diag)
        diag_row.addWidget(pan_diag_btn)
        tilt_diag_btn = QPushButton(tr('btn_tilt_diag'))
        tilt_diag_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        tilt_diag_btn.clicked.connect(self._tilt_diag)
        diag_row.addWidget(tilt_diag_btn)
        dl.addLayout(diag_row)
        diag.content_layout().addLayout(dl)
        left.addWidget(diag)

        left.addStretch()
        self.left_panel.set_content_layout(left)
        root.addWidget(self.left_panel)

        # ─── CENTER — Dashboard ───
        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)

        self.dashboard = DashboardWidget()
        center.addWidget(self.dashboard, 1)

        # Create camera widgets for the floating cameras window
        self.cam1_widget = CameraWidget("CAM1 — IP")
        self.cam2_widget = CameraWidget("CAM2 — THERMAL")
        self.cam2_widget.is_thermal = True

        # ─── FLOATING CAMERAS WINDOW (draggable, resizable) ───
        self._cameras_win = QWidget(self, Qt.WindowType.Window)
        self._cameras_win.setWindowTitle(tr('win_cameras'))
        self._cameras_win.resize(900, 400)
        self._cameras_win.setMinimumSize(300, 200)
        self._cameras_win.setStyleSheet("background:#1e1e1e;")

        # Hide on close instead of destroy
        self._cam_close_filter = HideOnCloseFilter(self._cameras_win)
        self._cameras_win.installEventFilter(self._cam_close_filter)

        cam_layout = QVBoxLayout(self._cameras_win)
        cam_layout.setContentsMargins(0, 0, 0, 0)
        cam_layout.setSpacing(0)

        # Title bar
        cam_hdr = QLabel(f"  {tr('win_cameras')}")
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
        saved_geom = self.cfg.value("cam_win_geometry")
        if saved_geom and hasattr(saved_geom, 'isValid') and saved_geom.isValid():
            self._cameras_win.setGeometry(saved_geom)
        else:
            self._cameras_win.move(
                self.pos().x() + self.width() + 20,
                self.pos().y())
        self._cameras_win.show()

        # View menu action for cameras window
        self._act_cams = QAction(tr('menu_cameras_win'), self)
        self._act_cams.triggered.connect(self._toggle_cameras_view)
        self._view_menu.addAction(self._act_cams)

        # ─── FLOATING MAP WINDOW (draggable, resizable) ───
        self.map_widget = YandexMapWidget()
        # Wire up beam drag signal (mouse control in map)
        self.map_widget.beam_changed.connect(self._on_map_beam_changed)

        self._map_win = QWidget(self, Qt.WindowType.Window)
        self._map_win.setWindowTitle(tr('win_map'))
        self._map_win.resize(700, 500)
        self._map_win.setMinimumSize(300, 200)
        self._map_win.setStyleSheet("background:#1e1e1e;")

        # Hide on close instead of destroy
        self._map_close_filter = HideOnCloseFilter(self._map_win)
        self._map_win.installEventFilter(self._map_close_filter)

        map_layout = QVBoxLayout(self._map_win)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)

        # Title bar
        map_hdr = QLabel(f"  {tr('win_map')}")
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
        beam_btn = QPushButton(tr('btn_beam_config'))
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
        saved_map_geom = self.cfg.value("map_win_geometry")
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
        self._act_map = QAction(tr('menu_map_win'), self)
        self._act_map.triggered.connect(self._toggle_map_view)
        self._view_menu.addAction(self._act_map)

        root.addLayout(center, 1)

        # ─── RIGHT SLIDING PANEL ───
        self.right_panel = SlidingPanel(220, side='right')
        right_content = QWidget()
        right = QVBoxLayout(right_content)
        right.setContentsMargins(8, 8, 8, 8)
        right.setSpacing(2)

        # D-Pad (primary control — always visible at top)
        dpad_panel = CollapsiblePanel(tr('sec_control_pad'))
        self._panel_dpad = dpad_panel
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
        laser = CollapsiblePanel(tr('sec_laser_rangefinder'))
        self._panel_laser = laser
        las = QVBoxLayout()
        self.laser_dist_lbl = QLabel("---.- m")
        self.laser_dist_lbl.setStyleSheet("color:#0a84ff; font:600 20px 'SF Pro Display';")
        self.laser_dist_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        las.addWidget(self.laser_dist_lbl)
        self.laser_target_lbl = QLabel(tr('lbl_no_target'))
        self.laser_target_lbl.setStyleSheet("color:#636366; font:600 10px 'SF Pro Display';")
        self.laser_target_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        las.addWidget(self.laser_target_lbl)
        las_btns = QHBoxLayout()
        single_btn = QPushButton(tr('btn_single'))
        single_btn.clicked.connect(self._laser_single)
        las_btns.addWidget(single_btn)
        self.laser_cont_btn = QPushButton(tr('btn_cont'))
        self.laser_cont_btn.clicked.connect(self._laser_continuous)
        las_btns.addWidget(self.laser_cont_btn)
        las.addLayout(las_btns)
        las_stop_btn = QPushButton(tr('btn_stop'))
        las_stop_btn.clicked.connect(self._laser_stop)
        las.addWidget(las_stop_btn)
        las_diag_btn = QPushButton(tr('btn_selfcheck'))
        las_diag_btn.clicked.connect(self._laser_selfcheck)
        las.addWidget(las_diag_btn)
        las_connect_btn = QPushButton(tr('btn_connect'))
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
        det_panel = CollapsiblePanel(tr('sec_detection'))
        self._panel_det = det_panel
        dt = QVBoxLayout()
        dt.setSpacing(4)
        self.det_model_lbl = QLabel(tr('lbl_model_not_loaded'))
        self.det_model_lbl.setStyleSheet(
            "color:#636366; font:600 10px 'SF Pro Display';")
        dt.addWidget(self.det_model_lbl)
        det_btn_row = QHBoxLayout()
        self.detect_btn = QPushButton(tr('btn_detect'))
        self.detect_btn.setCheckable(True)
        self.detect_btn.clicked.connect(self._toggle_detection)
        det_btn_row.addWidget(self.detect_btn)
        self.track_btn = QPushButton(tr('btn_track'))
        self.track_btn.setCheckable(True)
        self.track_btn.setEnabled(False)
        self.track_btn.clicked.connect(self._toggle_tracking)
        det_btn_row.addWidget(self.track_btn)
        dt.addLayout(det_btn_row)
        # Class filter
        flt_row = QHBoxLayout()
        flt_row.addWidget(QLabel(tr('lbl_filter')))
        self.det_filter_combo = QComboBox()
        self.det_filter_combo.addItems([tr('filter_all'), tr('filter_air'), tr('filter_drone_vehicle')])
        self.det_filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        flt_row.addWidget(self.det_filter_combo, 1)
        dt.addLayout(flt_row)
        # Target info
        self.det_target_lbl = QLabel(tr('lbl_no_target'))
        self.det_target_lbl.setStyleSheet(
            "color:#636366; font:600 11px 'SF Pro Display';")
        self.det_target_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dt.addWidget(self.det_target_lbl)
        # Lock / cycle target buttons
        tgt_row = QHBoxLayout()
        self.det_lock_btn = QPushButton(tr('btn_auto_lock'))
        self.det_lock_btn.setEnabled(False)
        self.det_lock_btn.clicked.connect(self._auto_lock_target)
        tgt_row.addWidget(self.det_lock_btn)
        self.det_cycle_btn = QPushButton(tr('btn_next'))
        self.det_cycle_btn.setEnabled(False)
        self.det_cycle_btn.clicked.connect(self._cycle_target)
        tgt_row.addWidget(self.det_cycle_btn)
        dt.addLayout(tgt_row)
        # Stop tracking
        self.det_stop_btn = QPushButton(tr('btn_stop_tracking'))
        self.det_stop_btn.setEnabled(False)
        self.det_stop_btn.clicked.connect(self._stop_tracking)
        dt.addWidget(self.det_stop_btn)
        # FPS
        self.det_fps_lbl = QLabel(tr('lbl_fps'))
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
        self.action_lbl = QLabel(tr('state_idle'))
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
        self._log_win.setWindowTitle(tr('win_log'))
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
        self._log_close_filter = HideOnCloseFilter(self._log_win)
        self._log_win.installEventFilter(self._log_close_filter)
        # Add to View menu
        self._log_action = QAction(tr('menu_log_win'), self)
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
        lbl = QLabel(tr('zoom_label'))
        lbl.setStyleSheet("color:#8e8e93; font:600 10px 'SF Pro Display';")
        h.addWidget(lbl)
        self.zoom_tele_btn = QPushButton(tr('zoom_tele'))
        self.zoom_tele_btn.setStyleSheet(STYLE_GO_BUTTON)
        self.zoom_tele_btn.pressed.connect(self._zoom_tele)
        self.zoom_tele_btn.released.connect(self._zoom_stop)
        h.addWidget(self.zoom_tele_btn)
        self.zoom_wide_btn = QPushButton(tr('zoom_wide'))
        self.zoom_wide_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.zoom_wide_btn.pressed.connect(self._zoom_wide)
        self.zoom_wide_btn.released.connect(self._zoom_stop)
        h.addWidget(self.zoom_wide_btn)
        # Focus
        self.focus_near_btn = QPushButton(tr('focus_near'))
        self.focus_near_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.focus_near_btn.pressed.connect(self._focus_near)
        self.focus_near_btn.released.connect(self._focus_stop)
        h.addWidget(self.focus_near_btn)
        self.focus_far_btn = QPushButton(tr('focus_far'))
        self.focus_far_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.focus_far_btn.pressed.connect(self._focus_far)
        self.focus_far_btn.released.connect(self._focus_stop)
        h.addWidget(self.focus_far_btn)
        self.focus_auto_btn = QPushButton(tr('focus_auto'))
        self.focus_auto_btn.setStyleSheet(STYLE_DIAG_BUTTON)
        self.focus_auto_btn.clicked.connect(self._focus_auto)
        h.addWidget(self.focus_auto_btn)
        # Insert into cameras window layout (after the splitter, before buttons)
        cam_layout = self._cameras_win.layout()
        if cam_layout is not None:
            cam_layout.addWidget(tb)
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
    def _on_map_beam_changed(self, offset: float, length: float):
        """Handle beam offset/length changed via mouse drag in map."""
        self._beam_offset = offset
        self._beam_length = int(length)
        self.cfg.set_value("beam_offset", offset)
        self.cfg.set_value("beam_length", int(length))
        self._log(f"[MAP] Beam drag: offset={offset:.1f}\u00b0 len={length:.0f}m")
    def _apply_beam_config(self):
        """Apply MAP BEAM settings to the map widget."""
        if not hasattr(self, 'map_widget'):
            return
        lat = self._beam_lat
        lng = self._beam_lng
        offset = self._beam_offset
        length = self._beam_length
        # Use apply_saved_config which handles page-not-loaded case
        pan = self.real_pan if self.is_connected else self.sim_pan
        self.map_widget.apply_saved_config(lat, lng, offset, length, pan)
        if hasattr(self, '_map_pos_lbl'):
            self._map_pos_lbl.setText(tr('map_device_pos').format(lat=lat, lng=lng))
        self._log(f"[MAP] Beam: {lat:.6f},{lng:.6f} offset={offset:.1f}\u00b0 len={length}m")
    def _on_thermal_temp(self, spot, max_t, min_t):
        """Update thermal temperature display in status bar."""
        self.temp_lbl.setText(f"SPOT: {spot:.1f}\u00b0C  MAX: {max_t:.1f}\u00b0C")
        if hasattr(self, 'dashboard'):
            self.dashboard.set_temp(spot)
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{ts}] {msg}")
