"""Non-modal notices inside a dialog, the way the PyQGIS cookbook shows it.

The cookbook (Communicating with the user) says a QMessageBox is usually a poor way to show a notice and that a QgsMessageBar can
sit inside your own dialog ("so you don't have to show a message box"). Confirmations that need an answer stay QMessageBox.question;
this is only for notices that report an outcome (exported, deleted, failed) and need no reply. Needs a real Qt/QGIS process, so it is
exercised by tests/test_chat_widget_live.py in the QGIS CI job, not by the offline suite."""

from qgis.core import Qgis
from qgis.gui import QgsMessageBar

_LEVELS = {
    "info": Qgis.MessageLevel.Info,
    "success": Qgis.MessageLevel.Success,
    "warning": Qgis.MessageLevel.Warning,
    "critical": Qgis.MessageLevel.Critical,
}
_BAR_ATTR = "_cartogen_message_bar"
_AUTO_HIDE_SECONDS = 10


def push_dialog_message(dialog, title, text, level="info"):
    """Show `text` in a message bar at the top of `dialog`'s layout, creating the bar on first use. Warnings and errors stay until
    dismissed; info and success clear themselves after a few seconds. Returns the bar."""
    bar = getattr(dialog, _BAR_ATTR, None)
    if bar is None:
        bar = QgsMessageBar(dialog)
        layout = dialog.layout()
        if layout is not None:
            layout.insertWidget(0, bar)
        setattr(dialog, _BAR_ATTR, bar)
    bar.clearWidgets()
    stays = level in ("warning", "critical")
    bar.pushMessage(title, text, level=_LEVELS.get(level, Qgis.MessageLevel.Info), duration=0 if stays else _AUTO_HIDE_SECONDS)
    return bar
