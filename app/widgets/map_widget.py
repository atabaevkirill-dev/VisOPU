"""VisOPU widget components."""
from __future__ import annotations

import math
import threading
import time

from PyQt6 import sip
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QSizePolicy, QFrame, QPlainTextEdit,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPointF, QRectF, pyqtSignal,
    QPropertyAnimation, QEasingCurve, QUrl,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFontMetrics,
    QRadialGradient, QLinearGradient, QPolygonF, QFont,
    QPainterPath, QImage, QPixmap,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEnginePage
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

import logging
_logger = logging.getLogger(__name__)

from app.offline_map import MBTilesServer

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from app.detector import YoloDetector, Detection, AIR_CLASSES
from app.i18n import tr


class _MapPage(QWebEnginePage):
    """Custom web page that forwards console messages to Python."""
    console_signal = pyqtSignal(str)

    def javaScriptConsoleMessage(self, level, message, line, source):
        # Only forward messages starting with BRIDGE: prefix
        if message.startswith("BRIDGE:"):
            self.console_signal.emit(message[7:])


class YandexMapWidget(QWidget):
    """Map widget (MapLibre GL JS + local MBTiles or OSM fallback) with beam visualization."""

    # Signals for beam changes from mouse drag in the map
    beam_changed = pyqtSignal(float, float)  # (offset_deg, length_m)

    # Class-level server: shared across all instances, started once.
    _server: MBTilesServer | None = None
    _server_started = False

    @classmethod
    def _ensure_server(cls):
        """Start the local tile server once (idempotent)."""
        if not cls._server_started:
            import os
            mbtiles_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
            )
            cls._server = MBTilesServer(mbtiles_dir=mbtiles_dir)
            cls._server.start()
            cls._server_started = True
        return cls._server

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background:#0a0a0a;")
        self._last_pan = None
        self._last_pan_time = 0
        self._config_pending = None  # (lat, lng, offset, length, pan) waiting for page load
        self._js_ready = False
        self._js_queue: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if HAS_WEBENGINE:
            srv = self._ensure_server()
            self._web = QWebEngineView(self)
            self._web.setStyleSheet("background:#0a0a0a;")

            # Custom page to intercept console messages (JS→Python bridge)
            page = _MapPage(self._web)
            page.console_signal.connect(self._on_js_message)
            self._web.setPage(page)

            settings = self._web.settings()
            settings.setAttribute(
                settings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(
                settings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(
                settings.WebAttribute.ScrollAnimatorEnabled, True)

            self._web.loadFinished.connect(self._on_page_loaded)
            self._web.setUrl(QUrl(f"http://127.0.0.1:{srv.port}/"))
            layout.addWidget(self._web, 1)
        else:
            self._fallback = QLabel(self)
            self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._fallback.setText("Map requires PyQt6-WebEngine\npip install PyQt6-WebEngine")
            self._fallback.setStyleSheet(
                "color:#636366; font:600 14px 'SF Pro Display'; background:#0a0a0a;")
            layout.addWidget(self._fallback, 1)

    # ── Internal ──

    def _run_js(self, code: str):
        """Run JS immediately if page is ready, otherwise queue it."""
        if not HAS_WEBENGINE or not hasattr(self, '_web'):
            return
        if sip.isdeleted(self._web):
            return
        if self._js_ready:
            self._web.page().runJavaScript(code)
        else:
            self._js_queue.append(code)

    def _on_js_message(self, msg: str):
        """Handle console bridge messages from JS."""
        # Format: BEAM_CHANGED:offset,length
        if msg.startswith("BEAM_CHANGED:"):
            try:
                parts = msg[13:].split(",")
                offset = float(parts[0])
                length = float(parts[1])
                self.beam_changed.emit(offset, length)
            except (IndexError, ValueError):
                pass

    def _on_page_loaded(self, ok):
        """Page finished loading — flush JS queue."""
        if ok:
            self._js_ready = True
            # Inject JS bridge callback
            self._web.page().runJavaScript(
                "window.pyBeamChanged=function(off,len){"
                "console.log('BRIDGE:BEAM_CHANGED:'+off.toFixed(2)+','+len.toFixed(0));}"
            )
            # Flush queued JS calls in order
            for code in self._js_queue:
                self._web.page().runJavaScript(code)
            self._js_queue.clear()
            # Push saved config if pending
            if self._config_pending:
                lat, lng, offset, length, pan = self._config_pending
                self._web.page().runJavaScript(
                    f"pyApplyConfig({lat},{lng},{offset},{length},{pan})")
                self._config_pending = None

    # ── Public API (called from MainWindow) ──

    def set_pan_angle(self, degrees):
        """Update beam direction from PAN-TILT angle (throttled)."""
        if not HAS_WEBENGINE or not hasattr(self, '_web'):
            return
        now = time.monotonic()
        if self._last_pan is not None:
            if abs(degrees - self._last_pan) < 0.05 and (now - self._last_pan_time) < 0.05:
                return
        self._last_pan = degrees
        self._last_pan_time = now
        self._run_js(f"pySetPan({degrees})")

    def set_device_position(self, lat, lng):
        """Set device location on the map (lat/lng)."""
        self._run_js(f"pySetDevicePos({lat},{lng})")

    def set_beam_offset(self, degrees):
        """Set bearing offset added to PAN angle."""
        self._run_js(f"pySetBeamOffset({degrees})")

    def set_beam_length(self, meters):
        """Set beam ray length in meters."""
        self._run_js(f"pySetBeamLength({meters})")

    def apply_saved_config(self, lat, lng, offset, length, pan=0):
        """Apply saved config — queues it if page hasn't loaded yet."""
        self._config_pending = (lat, lng, offset, length, pan)
        # If page already loaded, push immediately
        self._run_js(f"pyApplyConfig({lat},{lng},{offset},{length},{pan})")


# ═══════════════════════════════════════════════════════════════════
