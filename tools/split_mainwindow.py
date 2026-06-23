"""Extract MainWindow controller mixins from mainwindow.py."""
import ast
import os
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "app", "mainwindow.py")
OUT = os.path.join(ROOT, "app", "controllers")

GROUPS = {
    "pt.py": {
        "class": "PTControllerMixin",
        "methods": [
            "_setup_shortcuts", "keyPressEvent", "keyReleaseEvent",
            "_apply_keyboard_movement", "_get_tilt_sign", "_stop_all", "_go_home",
            "_pan_diag", "_tilt_diag", "_sim_diag_done", "_goto_position",
            "_on_real_pan", "_on_real_tilt", "_on_real_pan_spd", "_on_real_tilt_spd",
            "_on_real_temp", "_on_connection", "_on_dpad_pressed", "_on_dpad_released",
            "_simulate",
        ],
        "attrs": ["_MOVE_KEYS"],
    },
    "laser.py": {
        "class": "LaserControllerMixin",
        "methods": [
            "_on_laser_distance", "_laser_single", "_do_laser_single",
            "_laser_continuous", "_laser_stop", "_laser_selfcheck", "_do_laser_selfcheck",
            "_on_laser_connection", "_on_video_laser",
        ],
    },
    "detection.py": {
        "class": "DetectionControllerMixin",
        "methods": [
            "_toggle_detection", "_init_detector_bg", "_on_detector_ready",
            "_start_detection_on_cam", "_toggle_tracking", "_on_filter_changed",
            "_apply_filter", "_auto_lock_target", "_cycle_target", "_select_track_id",
            "_stop_tracking", "_on_detection_target", "_on_detections_updated",
            "_on_detection_fps", "_track_control_tick", "_on_video_detect",
            "_on_video_track",
        ],
    },
    "zoom.py": {
        "class": "ZoomControllerMixin",
        "methods": [
            "_ensure_onvif_connected", "_zoom_tele", "_zoom_wide", "_zoom_stop",
            "_focus_near", "_focus_far", "_focus_stop", "_focus_auto",
            "_on_zoom_scroll", "_on_onvif_connection", "_on_pelco_connection",
            "_on_video_filter", "_set_reticle",
        ],
    },
}


def extract_class_methods(source: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            methods = {}
            attrs = {}
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    seg = ast.get_source_segment(source, item)
                    if seg:
                        methods[item.name] = seg
                elif isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name) and t.id.startswith("_") and t.id.isupper() or (
                            isinstance(t, ast.Name) and t.id == "_MOVE_KEYS"
                        ):
                            seg = ast.get_source_segment(source, item)
                            if seg:
                                attrs[t.id] = seg
            return methods, attrs
    raise SystemExit("MainWindow not found")


def main():
    source = open(SRC, encoding="utf-8").read()
    methods, class_attrs = extract_class_methods(source)
    os.makedirs(OUT, exist_ok=True)

    header = '''"""Auto-extracted controller mixin — expects MainWindow host attributes."""
import threading
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut

from app.detector import YoloDetector, FILTER_ALL, FILTER_AIR, FILTER_DRONE_VEHICLE
from app.i18n import tr
from app.styles import (
    STYLE_GO_BUTTON, COLOR_CONNECTED, COLOR_DISCONNECTED, COLOR_ERROR, COLOR_ACTIVE,
)

'''

    for fname, spec in GROUPS.items():
        lines = [header]
        lines.append(f"\nclass {spec['class']}:\n")
        for attr in spec.get("attrs", []):
            if attr in class_attrs:
                lines.append("    " + class_attrs[attr].replace("\n", "\n    ") + "\n\n")
        for mname in spec["methods"]:
            if mname not in methods:
                raise SystemExit(f"missing method {mname} in {fname}")
            body = methods[mname]
            indented = textwrap.indent(body, "    ")
            lines.append(indented + "\n\n")
        path = os.path.join(OUT, fname)
        open(path, "w", encoding="utf-8").write("".join(lines))
        print("wrote", path)

    init = '''"""MainWindow controller mixins."""
from app.controllers.pt import PTControllerMixin
from app.controllers.laser import LaserControllerMixin
from app.controllers.detection import DetectionControllerMixin
from app.controllers.zoom import ZoomControllerMixin

__all__ = [
    "PTControllerMixin",
    "LaserControllerMixin",
    "DetectionControllerMixin",
    "ZoomControllerMixin",
]
'''
    open(os.path.join(OUT, "__init__.py"), "w", encoding="utf-8").write(init)
    print("done")


if __name__ == "__main__":
    main()
