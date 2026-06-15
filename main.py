"""VisOPU — TL.0009 PAN-TILT Control Application."""

import sys
import traceback
import logging
from datetime import datetime
from PyQt6.QtWidgets import QApplication
from app.mainwindow import MainWindow

# ── Production logging: errors only, to file ──
_LOG_FILE = "visopu.log"
logging.basicConfig(
    filename=_LOG_FILE,
    level=logging.ERROR,
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
