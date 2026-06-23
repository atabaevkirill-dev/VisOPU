"""Connection and UI helper dialogs for VisOPU."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QLineEdit, QMessageBox, QLabel,
)
from PyQt6.QtCore import Qt, QObject, QEvent
from PyQt6.QtGui import QFont

from app.i18n import tr


class ConnectionDialog(QDialog):
    """Generic connection dialog for devices with input validation."""

    def __init__(self, title, fields, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.inputs = {}
        for label, default, echo in fields:
            inp = QLineEdit(str(default))
            if echo == "password":
                inp.setEchoMode(QLineEdit.EchoMode.Password)
            self.inputs[label] = inp
            form.addRow(label, inp)
        layout.addLayout(form)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _validate_and_accept(self):
        for label, inp in self.inputs.items():
            val = inp.text().strip()
            if not val:
                QMessageBox.warning(
                    self, tr('dlg_validation'), f"{label} {tr('dlg_empty_field')}")
                inp.setFocus()
                return
            if label.lower().startswith("port"):
                try:
                    port = int(val)
                    if not (1 <= port <= 65535):
                        raise ValueError
                except ValueError:
                    QMessageBox.warning(
                        self, tr('dlg_validation'), f"{label} {tr('dlg_invalid_port')}")
                    inp.setFocus()
                    return
        self.accept()

    def get_values(self):
        return {k: v.text().strip() for k, v in self.inputs.items()}


class HideOnCloseFilter(QObject):
    """Event filter that hides a window on close instead of destroying it."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Close:
            event.ignore()
            obj.hide()
            return True
        return False


class StatusLink(QLabel):
    """Clickable status label that opens a connection dialog on click."""

    _LBL_FONT = "font:600 11px 'SF Pro Display';"

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self._callback = None
        self._base_style = ""

    def set_callback(self, fn):
        self._callback = fn

    def _apply_style(self):
        color = self._base_style
        if self._hover:
            color = color.replace('#636366', '#98989d')
            color = color.replace('#30d158', '#5ae07a')
            color = color.replace('#ff453a', '#ff6b63')
        self.setStyleSheet(color)

    def set_status_style(self, style):
        self._base_style = style
        self._apply_style()

    def enterEvent(self, event):
        self._hover = True
        self._apply_style()

    def leaveEvent(self, event):
        self._hover = False
        self._apply_style()

    def mousePressEvent(self, event):
        if self._callback:
            self._callback()
