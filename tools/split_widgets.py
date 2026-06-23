"""One-off script: split app/widgets.py into app/widgets/ package."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "app", "widgets.py")
OUT = os.path.join(ROOT, "app", "widgets")

COMMON_IMPORTS = '''"""VisOPU widget components."""
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
'''

SECTIONS = {
    "collapsible.py": (r"# COLLAPSIBLE PANEL", r"# SLIDING PANEL"),
    "sliding_panel.py": (r"# SLIDING PANEL", r"# DIRECTION PAD"),
    "direction_pad.py": (r"# DIRECTION PAD", r"# SPEED CONTROL"),
    "speed_control.py": (r"# SPEED CONTROL", r"# CAMERA WIDGET"),
    "camera_widget.py": (r"# CAMERA WIDGET", r"class _MapPage"),
    "map_widget.py": (r"class _MapPage", r"# DASHBOARD WIDGET"),
    "dashboard.py": (r"# DASHBOARD WIDGET", None),
}

def main():
    text = open(SRC, encoding="utf-8").read()
    os.makedirs(OUT, exist_ok=True)
    for fname, (start_pat, end_pat) in SECTIONS.items():
        si = re.search(start_pat, text)
        if not si:
            raise SystemExit(f"start not found: {start_pat}")
        start = si.start()
        if end_pat:
            ei = re.search(end_pat, text[start + 1 :])
            if not ei:
                raise SystemExit(f"end not found: {end_pat} in {fname}")
            chunk = text[start : start + 1 + ei.start()]
        else:
            chunk = text[start:]
        if fname != "collapsible.py":
            chunk = re.sub(r"^# =+\n# .+\n# =+\n\n", "", chunk, count=1, flags=re.M)
        path = os.path.join(OUT, fname)
        open(path, "w", encoding="utf-8").write(COMMON_IMPORTS + "\n\n" + chunk)
        print("wrote", path)

    init = '''"""Custom PyQt6 widgets for VisOPU."""
from app.widgets.collapsible import CollapsiblePanel
from app.widgets.sliding_panel import SlidingPanel
from app.widgets.direction_pad import DirectionPad
from app.widgets.speed_control import SpeedControl
from app.widgets.camera_widget import CameraWidget, HAS_CV2
from app.widgets.map_widget import YandexMapWidget
from app.widgets.dashboard import ArcGauge, DashboardWidget

__all__ = [
    "CollapsiblePanel", "SlidingPanel", "DirectionPad", "SpeedControl",
    "CameraWidget", "HAS_CV2", "YandexMapWidget", "ArcGauge", "DashboardWidget",
]
'''
    open(os.path.join(OUT, "__init__.py"), "w", encoding="utf-8").write(init)
    print("done")

if __name__ == "__main__":
    main()
