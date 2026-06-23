"""Persistent application settings (QSettings wrapper)."""

from PyQt6.QtCore import QSettings

ORG = "VisOPU"
APP = "TL0009"

DEFAULTS = {
    "pan_tilt_ip": "192.168.1.115",
    "pan_tilt_port": 9760,
    "laser_ip": "192.168.1.7",
    "laser_port": 20108,
    "cam1_ip": "192.168.1.10",
    "cam1_user": "admin",
    "cam1_pass": "admin",
    "cam2_ip": "192.168.1.11",
    "cam2_user": "admin",
    "cam2_pass": "admin",
    "pelco_ip": "192.168.1.10",
    "pelco_port": 5000,
    "pelco_addr": 1,
    "onvif_ip": "192.168.1.68",
    "onvif_port": 80,
    "onvif_user": "admin",
    "onvif_pass": "12qwaszx",
    "tilt_invert": True,
    "beam_lat": 55.751574,
    "beam_lng": 37.573856,
    "beam_offset": 0.0,
    "beam_length": 3000,
    "language": "ru",
}


class AppSettings:
    """Load/save connection and beam configuration."""

    def __init__(self):
        self._s = QSettings(ORG, APP)
        for key, val in DEFAULTS.items():
            setattr(self, key, val)

    def load(self):
        s = self._s
        for key, default in DEFAULTS.items():
            val = s.value(key, default)
            if key.endswith("_port") or key in ("pelco_addr", "beam_length"):
                val = int(val)
            elif key in ("beam_lat", "beam_lng", "beam_offset"):
                val = float(val)
            elif key == "tilt_invert":
                val = str(val).lower() in ("true", "1", "yes") if val is not None else default
            setattr(self, key, val)

    def save(self, extra=None):
        """Persist settings. Pass extra dict for runtime-only keys (geometries)."""
        s = self._s
        for key in DEFAULTS:
            if hasattr(self, key):
                s.setValue(key, getattr(self, key))
        if extra:
            for key, val in extra.items():
                s.setValue(key, val)

    def value(self, key, default=None):
        return self._s.value(key, default)

    def set_value(self, key, val):
        self._s.setValue(key, val)
        if hasattr(self, key):
            setattr(self, key, val)

    @property
    def store(self):
        return self._s
