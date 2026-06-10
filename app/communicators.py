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
                hex_str = data.hex()
                self.log_message.emit(f">> {cmd.hex()}  << {hex_str}")
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
            except:
                pass
            time.sleep(0.3)

    def self_check(self):
        """Equipment self-check (cmd 0x01). Returns status bytes or None."""
        return self.send_command(0x01)
