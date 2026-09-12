# -*- coding: utf-8 -*-
"""Live-QGIS-palette theme extraction, used by both dock_widget.py (the container
stylesheet) and chat_tab_widget.py (per-message bubble colors). Pulled out of
dock_widget.py during the tab-widget split (docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md)
specifically so chat_tab_widget.py doesn't have to import it back from dock_widget.py,
which would be circular now that dock_widget.py imports ChatTabWidget."""

from qgis.PyQt.QtWidgets import QApplication

from .chat_formatting import derive_bubble_colors

# Luminance below this (0-255 scale, simple RGB average) reads as a dark background --
# same threshold convention QFieldSync's real theme-detection helper uses
# (qfieldsync/gui/utils.py's extract_theme_from_qgis_settings).
_DARK_LUMINANCE_THRESHOLD = 128


def _detect_theme_mode():
    """Two-tier light/dark detection, matching QFieldSync's real, shipping pattern
    (qfieldsync/gui/utils.py) rather than trusting palette luminance alone: QGIS ships named
    themes ("Night Mapping", "Blend of Gray") that don't always show up as a clean luminance
    difference across every QPalette role, so check the active theme's NAME first and only
    fall back to a palette-luminance read for anything else (a custom theme, an OS-driven
    scheme, or a QGIS version/config where themeName() isn't meaningful). Returns "light" or
    "dark"; never raises -- an unexpected theme name or no live QApplication both fall through
    to the palette-luminance path, and that path itself defaults to "light" if there's truly
    no QApplication to read (matches extract_theme_palette()'s own None-on-no-QApplication
    behavior elsewhere in this file)."""
    try:
        from qgis.core import QgsApplication
        qgis_app = QgsApplication.instance()
        if qgis_app is not None:
            theme_name = qgis_app.themeName()
            if theme_name == "Night Mapping":
                return "dark"
            if theme_name == "Blend of Gray":
                return "light"
    except ImportError:
        pass

    app = QApplication.instance()
    if app is None:
        return "light"
    from qgis.PyQt.QtGui import QPalette
    window_color = app.palette().color(QPalette.ColorRole.Window)
    luminance = (window_color.red() + window_color.green() + window_color.blue()) / 3
    return "dark" if luminance < _DARK_LUMINANCE_THRESHOLD else "light"


def extract_theme_palette():
    """Reads the live QGIS application's actual palette so chat bubble colors
    follow whatever theme QGIS is really running (OS dark mode, a QGIS theme,
    a custom stylesheet) instead of a guessed static light/dark split. Thin
    and QGIS-dependent on purpose -- see chat_formatting.derive_bubble_colors
    for the pure-Python color logic this feeds, which is what's unit tested
    (this function can't be, since it isn't importable outside a real QGIS
    process at all -- see the qgis.PyQt import at the top of this file, which
    has no QGIS_AVAILABLE-style fallback)."""
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


def theme_colors():
    return derive_bubble_colors(extract_theme_palette())
