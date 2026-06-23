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


class DetectionControllerMixin:
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
                self.detect_btn.setText(tr('btn_detect'))
                self.detect_btn.setStyleSheet("")
                self.track_btn.setEnabled(False)
                self.track_btn.setChecked(False)
                self.track_btn.setText(tr('btn_track'))
                self.track_btn.setStyleSheet("")
                self.det_lock_btn.setEnabled(False)
                self.det_cycle_btn.setEnabled(False)
                self.det_stop_btn.setEnabled(False)
                self.det_target_lbl.setText(tr('lbl_no_target'))
                self.det_target_lbl.setStyleSheet(
                    "color:#636366; font:600 11px 'SF Pro Display';")
                self.det_fps_lbl.setText(tr('lbl_fps'))
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
                self.det_model_lbl.setText(tr('lbl_loading'))
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
                self.det_model_lbl.setText(f"{tr('lbl_model_prefix')}{name} ({backend})")
                self.det_model_lbl.setStyleSheet(
                    "color:#30d158; font:600 10px 'SF Pro Display';")
                self._log(f"[DETECT] Loaded {name} ({backend})")
                self._apply_filter()
                self._start_detection_on_cam()
            else:
                reason = self._detector.backend if self._detector else "unknown"
                self.det_model_lbl.setText(f"{tr('lbl_model_prefix')}{reason}")
                self.det_model_lbl.setStyleSheet(
                    "color:#ff453a; font:600 10px 'SF Pro Display';")
                self._log(f"[DETECT] Failed: {reason}")
                self._detecting = False
                self.detect_btn.setChecked(False)

    def _start_detection_on_cam(self):
            """Enable detection on CAM1 widget."""
            self._detecting = True
            self.detect_btn.setText(tr('btn_stop_det'))
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
                self.track_btn.setText(tr('btn_track'))
                self.track_btn.setStyleSheet("")
                self.det_lock_btn.setEnabled(False)
                self.det_cycle_btn.setEnabled(False)
                self.det_target_lbl.setText(tr('lbl_no_target'))
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
            self.track_btn.setText(tr('btn_stop_trk'))
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
            self.det_target_lbl.setText(
                tr('det_locked_fmt').format(
                    locked=tr('lbl_locked'), id=track_id, cls=class_name.upper()))
            self.det_target_lbl.setStyleSheet(
                "color:#30d158; font:600 11px 'SF Pro Display';")
            if hasattr(self, 'dashboard'):
                self.dashboard.set_target(f"#{track_id} {class_name.upper()}")
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
            self.track_btn.setText(tr('btn_track'))
            self.track_btn.setStyleSheet("")
            self.det_target_lbl.setText(tr('lbl_no_target'))
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
                        tr('det_tracking_fmt').format(
                            locked=tr('lbl_locked'),
                            id=d.track_id,
                            cls=d.class_name.upper(),
                            conf=f"{d.confidence:.0%}"))
                    break
            if not found:
                self.det_target_lbl.setText(
                    tr('det_lost_fmt').format(id=self._track_target_id))
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

