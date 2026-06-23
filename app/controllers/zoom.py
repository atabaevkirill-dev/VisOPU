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


class ZoomControllerMixin:
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
            self.onvif_comm.focus_stop()
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

    def _on_onvif_connection(self, connected):
            self.onvif_connected = connected
            # Only update ZOOM label if Pelco is not connected (Pelco takes priority)
            if not self.pelco_connected:
                c = COLOR_CONNECTED if connected else COLOR_DISCONNECTED
                s = tr('status_on') if connected else tr('status_off')
                self.zoom_status_lbl.setText(f"\u25cf ZOOM: {s}")
                self.zoom_status_lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")
            self._log(f"[ONVIF] {'Connected' if connected else 'Disconnected'}")

    def _on_pelco_connection(self, connected):
            self.pelco_connected = connected
            c = COLOR_CONNECTED if connected else COLOR_DISCONNECTED
            s = tr('status_on') if connected else tr('status_off')
            self.zoom_status_lbl.setText(f"\u25cf ZOOM: {s}")
            self.zoom_status_lbl.set_status_style(f"color:{c}; {self._LBL_FONT}")
            self._log(f"[PELCO] {'Connected' if connected else 'Disconnected'}")

    def _on_video_filter(self, name):
            """Video filter changed on overlay."""
            # Sync filter to both cameras
            filter_map = {'NORMAL': 0, 'NVG': 1, 'EDGE': 2, 'BW': 3}
            mode = filter_map.get(name, 0)
            for cam in (self.cam1_widget, self.cam2_widget):
                cam.set_video_filter(mode)
            self._log(f"[VIDEO] Filter: {name}")

    def _set_reticle(self, idx):
            if self.cam1_widget:
                self.cam1_widget.set_reticle(idx)
            if self.cam2_widget:
                self.cam2_widget.set_reticle(idx)
            names = [tr('reticle_crosshair_log'), tr('reticle_mildot_log'), tr('reticle_combat_log')]
            self._log(f"[CAM] Reticle: {names[idx]}")

