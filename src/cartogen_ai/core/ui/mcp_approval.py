"""The approval dialog for a change asked for over MCP (PLAN-034). One call, one question: Allow once, or Deny.

Deliberately plain, and strict where it matters: the default button and Escape are Deny, there is no "always allow", no "don't ask again", and a dialog
nobody answers closes itself as a refusal after `timeout_s`. The text shown is built by mcp_policy.approval_text from the arguments exactly as the
client sent them. MAIN THREAD ONLY (it runs a modal dialog). Real-QGIS behaviour is covered by tests/test_mcp_server_live.py."""
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QMessageBox

DEFAULT_TIMEOUT_S = 120


def ask(parent, name, text, timeout_s=DEFAULT_TIMEOUT_S):
    """True only when the person pressed "Allow once". Everything else -- Deny, Escape, closing the window, the timeout -- is False."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Cartogen AI: allow this change?")
    box.setText(text)
    allow = box.addButton("Allow once", QMessageBox.ButtonRole.AcceptRole)
    deny = box.addButton("Deny", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(deny)
    box.setEscapeButton(deny)
    timer = QTimer(box)
    timer.setSingleShot(True)
    timer.timeout.connect(box.reject)
    timer.start(int(timeout_s * 1000))
    box.raise_()
    box.activateWindow()
    box.exec()
    return box.clickedButton() is allow
