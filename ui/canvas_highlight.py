# -*- coding: utf-8 -*-
"""
Canvas Highlighting for Cartogen AI.
Flashes a layer's extent on the map canvas when the AI's reply mentions it,
bridging the chat text and the map visually. Must only be called from the
main Qt thread.
"""

try:
    from qgis.gui import QgsHighlight
    from qgis.core import QgsGeometry
    from qgis.PyQt.QtCore import QTimer
    from qgis.PyQt.QtGui import QColor
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

HIGHLIGHT_DURATION_MS = 2500
HIGHLIGHT_COLOR = (255, 140, 0, 160)  # orange, semi-transparent


def flash_layer_extent(iface, layer, on_expired=None, duration_ms=HIGHLIGHT_DURATION_MS):
    """Creates a temporary QgsHighlight over layer's extent and removes it
    after duration_ms. Returns the QgsHighlight so the caller can keep a
    reference alive until on_expired fires (Python GC would otherwise collect
    it before the timer runs)."""
    if not QGIS_AVAILABLE or iface is None or layer is None:
        return None

    try:
        canvas = iface.mapCanvas()
        extent = layer.extent()
        if extent.isNull() or extent.isEmpty():
            return None

        # QgsHighlight has no overload that accepts a raw QgsRectangle -- only
        # QgsGeometry or QgsFeature. Passing the rectangle directly raised
        # "arguments did not match any overloaded call" on every single highlight
        # attempt (confirmed live). Wrap it as a geometry instead.
        highlight = QgsHighlight(canvas, QgsGeometry.fromRect(extent), layer)
        highlight.setColor(QColor(*HIGHLIGHT_COLOR))
        highlight.setFillColor(QColor(*HIGHLIGHT_COLOR))
        highlight.setWidth(4)
        highlight.show()

        def _expire():
            try:
                highlight.hide()
            except Exception:
                pass
            if on_expired:
                on_expired(highlight)

        QTimer.singleShot(duration_ms, _expire)
        return highlight
    except Exception as e:
        print(f"[CanvasHighlight] Failed to highlight layer: {e}")
        return None


def find_mentioned_layers(text, project_layers, max_matches=2):
    """Case-insensitive substring match of loaded layer names against reply
    text. Returns at most max_matches QgsMapLayer objects, longest names
    matched first so a specific layer name isn't shadowed by a shorter
    unrelated substring match."""
    if not text or not project_layers:
        return []

    lowered = text.lower()
    candidates = sorted(project_layers, key=lambda l: len(l.name()), reverse=True)
    matches = []
    for layer in candidates:
        name = layer.name()
        if name and len(name) >= 3 and name.lower() in lowered:
            matches.append(layer)
        if len(matches) >= max_matches:
            break
    return matches
