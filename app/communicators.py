"""Device communication classes for TL.0009 PAN-TILT and Laser rangefinder."""

import socket
import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal


class DeviceCommunicator(QObject):
    """Handles TCP communication with the TL.0009 PAN-TILT device."""
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
            except Exception:
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


class LaserCommunicator(QObject):
    """Handles TCP communication with the 3Km laser rangefinder module."""
    distance_updated = pyqtSignal(float, int)   # (distance_m, status)
    connection_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)
    log_message = pyqtSignal(str)

    FRAME_HEAD = bytes([0xEE, 0x16])
    DEV_CODE = 0x03

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
        except Exception as e:
            self.error_occurred.emit(str(e))
            self.connected = False
            self.connection_changed.emit(False)

    def disconnect_device(self):
        self.polling = False
        if self.poll_thread:
            self.poll_thread.join(timeout=2)
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.connected = False
        self.connection_changed.emit(False)

    def _build_cmd(self, cmd_code, params=None):
        """Build binary command frame: HEAD + LEN + DEV + CMD + PARAMS + CHK."""
        params = params or []
        payload = bytes([self.DEV_CODE, cmd_code] + params)
        data_len = len(payload)
        checksum = sum(payload) & 0xFF
        return self.FRAME_HEAD + bytes([data_len]) + payload + bytes([checksum])

    def send_command(self, cmd_code, params=None):
        """Send command and read response. Returns raw bytes or None."""
        with self._lock:
            if not self.connected or not self.socket:
                return None
            try:
                cmd = self._build_cmd(cmd_code, params)
                self.socket.sendall(cmd)
                time.sleep(0.15)
                data = self.socket.recv(256)
                if len(data) >= 10 and data[0] == 0xEE and data[1] == 0x16:
                    return data
                return None
            except Exception as e:
                self.error_occurred.emit(str(e))
                self.connected = False
                self.connection_changed.emit(False)
                return None

    def single_range(self):
        """Single ranging (cmd 0x02). Returns (distance_m, status) or None."""
        resp = self.send_command(0x02)
        if resp and len(resp) >= 10 and resp[4] == 0x02:
            status = resp[5]
            dist = resp[6] * 256 + resp[7] + resp[8] * 0.1
            self.distance_updated.emit(dist, status)
            return (dist, status)
        return None

    def start_continuous(self):
        """Start continuous ranging (cmd 0x04) and polling thread."""
        self.send_command(0x04)
        self.polling = True
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def stop_continuous(self):
        """Stop continuous ranging (cmd 0x05) and polling thread."""
        self.polling = False
        if self.poll_thread:
            self.poll_thread.join(timeout=2)
        self.send_command(0x05)

    def _poll_loop(self):
        while self.polling and self.connected:
            try:
                with self._lock:
                    cmd = self._build_cmd(0x04)
                    self.socket.sendall(cmd)
                    time.sleep(0.15)
                    data = self.socket.recv(256)
                if (len(data) >= 10 and data[0] == 0xEE
                        and data[1] == 0x16 and data[4] == 0x04):
                    status = data[5]
                    dist = data[6] * 256 + data[7] + data[8] * 0.1
                    self.distance_updated.emit(dist, status)
            except Exception:
                pass
            time.sleep(0.3)

    def self_check(self):
        """Equipment self-check (cmd 0x01). Returns status bytes or None."""
        return self.send_command(0x01)


# ═══════════════════════════════════════════════════════════════════
# PELCO-D PTZ CAMERA COMMUNICATOR
# ═══════════════════════════════════════════════════════════════════

class PelcoDCommunicator(QObject):
    """Handles Pelco-D protocol over TCP (RS-485 bridge or direct IP)."""
    connection_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)
    log_message = pyqtSignal(str)

    SYNC = 0xFF

    def __init__(self, address=0x01):
        super().__init__()
        self.socket = None
        self.connected = False
        self._address = address
        self._lock = threading.Lock()

    def connect_device(self, ip, port):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(3)
            self.socket.connect((ip, port))
            self.connected = True
            self.connection_changed.emit(True)
        except Exception as e:
            self.error_occurred.emit(str(e))
            self.connected = False
            self.connection_changed.emit(False)

    def disconnect_device(self):
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.connected = False
        self.connection_changed.emit(False)

    def _build_frame(self, byte2, byte3, byte4, byte5):
        """Build 7-byte Pelco-D frame: FF addr b2 b3 b4 b5 chk."""
        frame = bytes([
            self.SYNC,
            self._address,
            byte2,
            byte3,
            byte4,
            byte5,
        ])
        checksum = sum(frame[1:]) & 0xFF
        return frame + bytes([checksum])

    def send_command(self, byte2, byte3, byte4=0x00, byte5=0x00):
        """Send Pelco-D command frame."""
        with self._lock:
            if not self.connected or not self.socket:
                return False
            try:
                frame = self._build_frame(byte2, byte3, byte4, byte5)
                self.socket.sendall(frame)
                return True
            except Exception as e:
                self.error_occurred.emit(str(e))
                self.connected = False
                self.connection_changed.emit(False)
                return False

    def stop_all(self):
        """Stop all pan/tilt/zoom motion (byte2=0x00, byte3=0x00)."""
        return self.send_command(0x00, 0x00, 0x00, 0x00)

    # ── Zoom commands ──
    def zoom_tele(self, speed=0x15):
        """Zoom Tele (in). speed: 0x00-0x27 (0=stop)."""
        speed = max(0, min(0x27, speed))
        return self.send_command(0x00, 0x20, speed, 0x00)

    def zoom_wide(self, speed=0x15):
        """Zoom Wide (out). speed: 0x00-0x27 (0=stop)."""
        speed = max(0, min(0x27, speed))
        return self.send_command(0x00, 0x40, speed, 0x00)

    def zoom_stop(self):
        """Stop zoom."""
        return self.send_command(0x00, 0x00, 0x00, 0x00)

    # ── Focus commands ──
    def focus_near(self, speed=0x15):
        """Focus Near. speed: 0x00-0x27."""
        speed = max(0, min(0x27, speed))
        return self.send_command(0x01, 0x00, speed, 0x00)

    def focus_far(self, speed=0x15):
        """Focus Far. speed: 0x00-0x27."""
        speed = max(0, min(0x27, speed))
        return self.send_command(0x01, 0x80, speed, 0x00)

    def focus_stop(self):
        """Stop focus."""
        return self.send_command(0x01, 0x00, 0x00, 0x00)

    def focus_auto(self):
        """Auto-focus on."""
        return self.send_command(0x01, 0x2B, 0x00, 0x00)

    # ── Iris commands ──
    def iris_open(self):
        """Iris open (brighter)."""
        return self.send_command(0x02, 0x00, 0x00, 0x00)

    def iris_close(self):
        """Iris close (darker)."""
        return self.send_command(0x04, 0x00, 0x00, 0x00)

    def iris_stop(self):
        """Iris stop."""
        return self.send_command(0x00, 0x00, 0x00, 0x00)


# ═══════════════════════════════════════════════════════════════════
# ONVIF CAMERA COMMUNICATOR (PTZ / Zoom / Focus)
# ═══════════════════════════════════════════════════════════════════

try:
    from onvif import ONVIFCamera
    HAS_ONVIF = True
except ImportError:
    HAS_ONVIF = False


class ONVIFCommunicator(QObject):
    """Handles ONVIF PTZ control for IP cameras (zoom, focus, iris)."""
    connection_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._cam = None
        self._ptz = None
        self._ptz_config = None
        self._profile_token = None
        self.connected = False

    def connect_device(self, ip, user="admin", password="admin", port=80):
        """Connect to ONVIF camera and initialize PTZ service."""
        if not HAS_ONVIF:
            self.error_occurred.emit("onvif-zeep not installed — pip install onvif-zeep")
            return
        try:
            self._cam = ONVIFCamera(ip, port, user, password)
            # Get media service to find profile token
            media = self._cam.create_media_service()
            profiles = media.GetProfiles()
            if not profiles:
                self.error_occurred.emit("No ONVIF profiles found on camera")
                return
            self._profile_token = profiles[0].token


            # Get PTZ service
            self._ptz = self._cam.create_ptz_service()

            # Get PTZ configuration to know speed limits
            configs = self._ptz.GetConfigurations()
            if configs:
                self._ptz_config = configs[0]

            self.connected = True
            self.connection_changed.emit(True)
        except Exception as e:
            self.error_occurred.emit(f"ONVIF connect failed: {e}")
            self.connected = False
            self.connection_changed.emit(False)

    def disconnect_device(self):
        self._cam = None
        self._ptz = None
        self._ptz_config = None
        self._profile_token = None
        self.connected = False
        self.connection_changed.emit(False)

    def _make_velocity(self, pan=0.0, tilt=0.0, zoom=0.0):
        """Create PTZSpeed velocity structure."""
        request = self._ptz.create_type('ContinuousMove')
        request.ProfileToken = self._profile_token
        request.Velocity = {
            'PanTilt': {'x': pan, 'y': tilt},
            'Zoom': {'x': zoom}
        }
        return request

    def zoom_in(self, speed=0.5):
        """Zoom Tele (in). speed: 0.0-1.0."""
        if not self.connected or not self._ptz:
            return
        try:
            speed = max(0.0, min(1.0, speed))
            request = self._ptz.create_type('ContinuousMove')
            request.ProfileToken = self._profile_token
            request.Velocity = {'PanTilt': {'x': 0, 'y': 0}, 'Zoom': {'x': speed}}
            self._ptz.ContinuousMove(request)
        except Exception as e:
            self.error_occurred.emit(f"ZoomTele: {e}")

    def zoom_out(self, speed=0.5):
        """Zoom Wide (out). speed: 0.0-1.0."""
        if not self.connected or not self._ptz:
            return
        try:
            speed = max(0.0, min(1.0, speed))
            request = self._ptz.create_type('ContinuousMove')
            request.ProfileToken = self._profile_token
            request.Velocity = {'PanTilt': {'x': 0, 'y': 0}, 'Zoom': {'x': -speed}}
            self._ptz.ContinuousMove(request)
        except Exception as e:
            self.error_occurred.emit(f"ZoomWide: {e}")

    def zoom_stop(self):
        """Stop zoom (and all PTZ motion)."""
        if not self.connected or not self._ptz:
            return
        try:
            request = self._ptz.create_type('Stop')
            request.ProfileToken = self._profile_token
            request.PanTilt = True
            request.Zoom = True
            self._ptz.Stop(request)
        except Exception as e:
            self.error_occurred.emit(f"Stop: {e}")

    def focus_near(self, speed=0.5):
        """Focus near. speed: 0.0-1.0."""
        if not self.connected or not self._ptz:
            return
        try:
            speed = max(0.0, min(1.0, speed))
            request = self._ptz.create_type('ContinuousMove')
            request.ProfileToken = self._profile_token

        except Exception as e:
            self.error_occurred.emit(f"FocusNear: {e}")

    def focus_far(self, speed=0.5):
        """Focus far. speed: 0.0-1.0."""
        if not self.connected or not self._ptz:
            return
        try:
            speed = max(0.0, min(1.0, speed))
        except Exception as e:
            self.error_occurred.emit(f"FocusFar: {e}")

    def focus_auto(self):
        """Enable auto-focus via ONVIF Imaging service."""
        if not self.connected or not self._cam:
            return
        try:
            imaging = self._cam.create_imaging_service()
            # Get video source config token
            configs = imaging.GetMoveOptions(0)  # source token 0
        except Exception as e:
            self.error_occurred.emit(f"AutoFocus: {e}")

    def get_ptz_status(self):
        """Get current PTZ position and status."""
        if not self.connected or not self._ptz:
            return None
        try:
            request = self._ptz.create_type('GetStatus')
            request.ProfileToken = self._profile_token
            status = self._ptz.GetStatus(request)
            return status
        except Exception as e:
            self.error_occurred.emit(f"GetStatus: {e}")
            return None
