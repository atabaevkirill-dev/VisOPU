"""Remove extracted methods from mainwindow.py; preserve exact source lines."""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "app", "mainwindow.py")
BAK = SRC + ".bak"

GROUP_METHODS = {
    "_setup_shortcuts", "keyPressEvent", "keyReleaseEvent",
    "_apply_keyboard_movement", "_get_tilt_sign", "_stop_all", "_go_home",
    "_pan_diag", "_tilt_diag", "_sim_diag_done", "_goto_position",
    "_on_real_pan", "_on_real_tilt", "_on_real_pan_spd", "_on_real_tilt_spd",
    "_on_real_temp", "_on_connection", "_on_dpad_pressed", "_on_dpad_released",
    "_simulate",
    "_on_laser_distance", "_laser_single", "_do_laser_single",
    "_laser_continuous", "_laser_stop", "_laser_selfcheck", "_do_laser_selfcheck",
    "_on_laser_connection", "_on_video_laser",
    "_toggle_detection", "_init_detector_bg", "_on_detector_ready",
    "_start_detection_on_cam", "_toggle_tracking", "_on_filter_changed",
    "_apply_filter", "_auto_lock_target", "_cycle_target", "_select_track_id",
    "_stop_tracking", "_on_detection_target", "_on_detections_updated",
    "_on_detection_fps", "_track_control_tick", "_on_video_detect",
    "_on_video_track",
    "_ensure_onvif_connected", "_zoom_tele", "_zoom_wide", "_zoom_stop",
    "_focus_near", "_focus_far", "_focus_stop", "_focus_auto",
    "_on_zoom_scroll", "_on_onvif_connection", "_on_pelco_connection",
    "_on_video_filter", "_set_reticle",
    "_load_settings", "_save_settings",
}

REMOVE_CLASSES = {"ConnectionDialog", "_HideOnCloseFilter", "_StatusLink"}

HEADER = '''"""Main application window for VisOPU."""

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

'''


def segment(source, node):
    lines = source.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1 : node.end_lineno])


def main():
    source = open(BAK, encoding="utf-8").read()
    tree = ast.parse(source)
    parts = [HEADER]

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in REMOVE_CLASSES:
            continue
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name in GROUP_METHODS:
                    continue
                if isinstance(sub, ast.Assign):
                    names = [t.id for t in sub.targets if isinstance(t, ast.Name)]
                    if names == ["_MOVE_KEYS"] or names == ["_LBL_FONT"]:
                        continue
                parts.append(segment(source, sub))
            continue
        if isinstance(node, ast.Expr) and isinstance(getattr(node.value, "value", None), str):
            if "CONNECTION DIALOG" in node.value.value:
                continue
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            continue
        # skip module docstring duplicate and old imports block — keep only from first MainWindow
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(getattr(node.value, "value", None), str):
            if "Main application window" in node.value.value:
                continue

    open(SRC, "w", encoding="utf-8").write("".join(parts))
    print("ok", len(parts) - 1, "chunks")


if __name__ == "__main__":
    main()
