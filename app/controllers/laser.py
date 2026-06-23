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


class LaserControllerMixin:
    def _on_laser_distance(self, dist, status):
            self.laser_dist_lbl.setText(f"{dist:.1f} m")
            if hasattr(self, 'dashboard'):
                self.dashboard.set_laser_dist(dist)
            if status & 0x0F == 0x04:
                label = tr('laser_out_of_range')
                self.laser_target_lbl.setText(label)
                self.laser_target_lbl.setStyleSheet(
                    f"color:{COLOR_ERROR}; font:600 10px 'SF Pro Display';")
            else:
                flags = []
                if status & 0x01: flags.append(tr('laser_near'))
                if status & 0x02: flags.append(tr('laser_far'))
                multi = (status >> 4) & 0x0F
                label = tr('laser_target')
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
                self.laser_cont_btn.setText(tr('btn_cont'))
                # Clear panel display
                self.laser_dist_lbl.setText("---.- m")
                self.laser_target_lbl.setText(tr('lbl_no_target'))
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
                self.laser_cont_btn.setText(tr('laser_stop_cont'))
                self._log("[LASER] Continuous ranging started")

    def _laser_stop(self):
            if self.laser_comm.polling:
                self.laser_comm.stop_continuous()
                self.laser_cont_btn.setText(tr('btn_cont'))
            self.laser_dist_lbl.setText("---.- m")
            self.laser_target_lbl.setText(tr('lbl_no_target'))
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

    def _on_laser_connection(self, connected):
            self.laser_connected = connected
            c = COLOR_CONNECTED if connected else COLOR_DISCONNECTED
            s = tr('status_on') if connected else tr('status_off')
            self.laser_status_lbl.setText(f"\u25cf LASER: {s}")
            self.laser_status_lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")
            self._log(f"[LASER] {'Connected' if connected else 'Disconnected'}")

    def _on_video_laser(self, on):
            """Video overlay LSR button: start/stop laser ranging."""
            if on:
                if not self.laser_connected:
                    self._log("[LASER] Not connected")
                    for cam in (self.cam1_widget, self.cam2_widget):
                        cam.set_laser_state(False)
                    return
                self.laser_comm.start_continuous()
                self.laser_cont_btn.setText(tr('laser_stop_cont'))
                self._log("[LASER] Continuous ranging started")
            else:
                self._laser_stop()

