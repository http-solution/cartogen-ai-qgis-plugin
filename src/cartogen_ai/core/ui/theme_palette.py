"""The live QGIS application's palette as a plain dict, for the dialogs' stylesheets. Shared by the Settings and Connections windows."""
from qgis.PyQt.QtWidgets import QApplication


def extract_theme_palette():
    """Reads the live QGIS application's palette so a dialog's QSS follows whatever theme QGIS is actually running, matching
    dock_widget.py's own palette extraction. Returns None when there is no application yet."""
    from qgis.PyQt.QtGui import QPalette
    app = QApplication.instance()
    if app is None:
        return None
    p = app.palette()
    return {
        "window": p.color(QPalette.ColorRole.Window).name(),
        "alt_base": p.color(QPalette.ColorRole.AlternateBase).name(),
        "base": p.color(QPalette.ColorRole.Base).name(),
        "text": p.color(QPalette.ColorRole.WindowText).name(),
        "highlight": p.color(QPalette.ColorRole.Highlight).name(),
        "highlighted_text": p.color(QPalette.ColorRole.HighlightedText).name(),
        "muted_text": p.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText).name(),
        "mid": p.color(QPalette.ColorRole.Mid).name(),
    }
