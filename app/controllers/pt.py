"""Auto-extracted controller mixin — expects MainWindow host attributes."""
import threading
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut

from app.detector import YoloDetector, FILTER_ALL, FILTER_AIR, FILTER_DRONE_VEHICLE
from app.i18n import tr
from app.styles import (
    STYLE_GO_BUTTON, COLOR_CONNECTED, COLOR_DISCONNECTED, COLOR_ERROR, COLOR_ACTIVE,
)


class PTControllerMixin:
    _MOVE_KEYS = {
            Qt.Key.Key_Left, Qt.Key.Key_Right,
            Qt.Key.Key_Up, Qt.Key.Key_Down,
            Qt.Key.Key_Q, Qt.Key.Key_E,
        }

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
                pass

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

    def _on_real_pan(self, v):
            self.real_pan = v
            self.pan_pos_lbl.setText(f"PAN: {v:.2f}\u00b0")
            if hasattr(self, 'pan_pos_spin') and not self.pan_pos_spin.hasFocus():
                self.pan_pos_spin.blockSignals(True)
                self.pan_pos_spin.setValue(v)
                self.pan_pos_spin.blockSignals(False)
            if hasattr(self, 'dashboard'):
                self.dashboard.set_pan(v)
            if hasattr(self, 'map_widget'):
                self.map_widget.set_pan_angle(v)

    def _on_real_tilt(self, v):
            self.real_tilt = v
            self.tilt_pos_lbl.setText(f"TILT: {v:.2f}\u00b0")
            if hasattr(self, 'tilt_pos_spin') and not self.tilt_pos_spin.hasFocus():
                self.tilt_pos_spin.blockSignals(True)
                self.tilt_pos_spin.setValue(v)
                self.tilt_pos_spin.blockSignals(False)
            if hasattr(self, 'dashboard'):
                self.dashboard.set_tilt(v)

    def _on_real_pan_spd(self, v):
            self.real_pan_spd = v
            self.pan_spd_lbl.setText(f"P-SPD: {v:.1f}")
            moving = abs(v) > 0.1
            self.action_lbl.setText(tr('state_moving') if moving else tr('state_idle'))
            self.action_lbl.setStyleSheet(
                f"color:{COLOR_ACTIVE};font:600 10px 'SF Pro Display';" if moving
                else "color:#8e8e93;font:600 10px 'SF Pro Display';")
            if hasattr(self, 'dashboard'):
                self.dashboard.set_pan_speed(v)
                self.dashboard.set_action(tr('dash_moving') if moving else tr('dash_idle'), moving)

    def _on_real_tilt_spd(self, v):
            self.real_tilt_spd = v
            self.tilt_spd_lbl.setText(f"T-SPD: {v:.1f}")
            if hasattr(self, 'dashboard'):
                self.dashboard.set_tilt_speed(v)

    def _on_real_temp(self, v):
            self.real_temp = v
            self.temp_lbl.setText(f"TEMP: {v:.1f}")
            if hasattr(self, 'dashboard'):
                self.dashboard.set_temp(v)

    def _on_connection(self, connected):
            self.is_connected = connected
            c = COLOR_CONNECTED if connected else COLOR_DISCONNECTED
            s = tr('status_on') if connected else tr('status_off')
            self.pt_status_lbl.setText(f"\u25cf PAN-TILT: {s}")
            self.pt_status_lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")
            self._log(f"[PAN-TILT] {'Connected' if connected else 'Disconnected'}")

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
            if hasattr(self, 'pan_pos_spin') and not self.pan_pos_spin.hasFocus():
                self.pan_pos_spin.blockSignals(True)
                self.pan_pos_spin.setValue(self.sim_pan)
                self.pan_pos_spin.blockSignals(False)
            if hasattr(self, 'tilt_pos_spin') and not self.tilt_pos_spin.hasFocus():
                self.tilt_pos_spin.blockSignals(True)
                self.tilt_pos_spin.setValue(self.sim_tilt)
                self.tilt_pos_spin.blockSignals(False)
            # Push sim PAN to map beam
            if hasattr(self, 'map_widget'):
                self.map_widget.set_pan_angle(self.sim_pan)
            self.pan_spd_lbl.setText(f"P-SPD: {self.sim_pan_spd:.1f}")
            self.tilt_spd_lbl.setText(f"T-SPD: {self.sim_tilt_spd:.1f}")
            self.temp_lbl.setText("TEMP: 25.0")
            moving = abs(self.sim_pan_spd) > 0.1 or abs(self.sim_tilt_spd) > 0.1
            self.action_lbl.setText(tr('state_moving') if moving else tr('state_idle'))
            self.action_lbl.setStyleSheet(
                f"color:{COLOR_ACTIVE};font:600 10px 'SF Pro Display';" if moving
                else "color:#8e8e93;font:600 10px 'SF Pro Display';")
            # Push to dashboard
            if hasattr(self, 'dashboard'):
                self.dashboard.set_pan(self.sim_pan)
                self.dashboard.set_tilt(self.sim_tilt)
                self.dashboard.set_pan_speed(self.sim_pan_spd)
                self.dashboard.set_tilt_speed(self.sim_tilt_spd)
                self.dashboard.set_temp(25.0)
                self.dashboard.set_action(tr('dash_moving') if moving else tr('dash_idle'), moving)

