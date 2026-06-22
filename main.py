"""VisOPU — TL.0009 PAN-TILT Control Application."""

import os
import sys
import traceback
import logging
from datetime import datetime

# ── Fix QtWebEngine zoom/scroll in PyInstaller exe ──
# GPU compositing breaks inside packaged builds; force software rendering.
# MUST be set before QApplication is created.
if getattr(sys, 'frozen', False):
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = (
        '--disable-gpu --disable-gpu-compositing '
        '--disable-software-rasterizer --no-sandbox '
        '--ignore-gpu-blacklist --disable-features=GPU'
    )
    # Force Qt to use software OpenGL before any Qt import initialises the GL context
    os.environ['QT_OPENGL'] = 'software'

from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import QApplication
from app.mainwindow import MainWindow

# Must be called BEFORE QApplication() — tells Qt to skip hardware GL for WebEngine
if getattr(sys, 'frozen', False):
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)

# ── Production logging: info+errors to file ──
_LOG_FILE = "visopu.log"
logging.basicConfig(
    filename=_LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _unhandled_exception(exc_type, exc_value, exc_tb):
    """Catch all unhandled exceptions — log to file instead of crashing silently."""
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.error(f"Unhandled exception:\n{tb_text}")
    # Also print to stderr for dev debugging
    print(f"[FATAL] {exc_type.__name__}: {exc_value}\n{tb_text}", file=sys.stderr)


sys.excepthook = _unhandled_exception


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("VisOPU")
    app.setApplicationVersion("1.0.0")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
