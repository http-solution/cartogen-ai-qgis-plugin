# -*- coding: utf-8 -*-
"""
Canvas Highlighting for Cartogen AI.
Flashes a layer's extent on the map canvas when the AI's reply mentions it,
bridging the chat text and the map visually. Must only be called from the
main Qt thread.
"""

try:
    from qgis.gui import QgsHighlight
    from qgis.core import QgsGeometry, QgsCoordinateTransform, QgsProject, QgsRectangle
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


def _extent_to_canvas_crs(canvas, extent, source_crs):
    """Transforms extent from source_crs into the canvas's own destination
    CRS -- see the identical helper in agent/tools/vector_tools.py
    (zoom_to_layer) for the full rationale. Duplicated locally rather than
    cross-imported, matching this codebase's existing convention of each
    module keeping its own small CRS-transform helper (vector_tools.py and
    agent/tools/layout_tools.py already each keep their own copy)."""
    canvas_crs = canvas.mapSettings().destinationCrs()
    if not source_crs.isValid() or source_crs == canvas_crs:
        return extent
    try:
        transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
        return transform.transformBoundingBox(extent)
    except Exception:
        return extent


def zoom_to_layers(iface, layers):
    """Moves the map canvas to the combined extent of layers -- real user
    report: after the agent creates/modifies layers, the canvas keeps
    whatever extent it already had, so the result is never actually
    visible without the user manually zooming. Distinct from
    flash_layer_extent above (which highlights without moving the view) --
    this one moves the view. Zooms to the UNION of every given layer's
    extent in one call, not one setExtent() per layer (only the last call
    would visually stick anyway, which would be an arbitrary choice of
    which layer 'wins' when a turn touched more than one). Silently no-ops
    on any layer with a null extent or missing CRS rather than raising,
    since this always runs after a chat turn has already completed -- a
    canvas-move failure must never look like the turn itself failed.

    Only skips on isNull() (a genuinely empty layer, zero features), NOT
    isEmpty() -- live-confirmed against real QGIS 4.2.2 that a single-point
    layer's extent() is a legitimate, real extent with isNull()=False but
    isEmpty()=True (zero width/height, since a point has no area). An
    earlier version of this function also skipped on isEmpty(), which
    silently dropped every single-point layer -- one of the most common
    layer types this plugin creates (facilities, incidents, points of
    interest) -- exactly backwards from the bug being fixed here. Matches
    agent/tools/vector_tools.py's existing single-layer zoom_to_layer tool,
    which never checked either flag and has shipped fine."""
    if not QGIS_AVAILABLE or iface is None or not layers:
        return False
    try:
        canvas = iface.mapCanvas()
        combined = None
        for layer in layers:
            extent = layer.extent()
            if extent.isNull():
                continue
            extent = _extent_to_canvas_crs(canvas, extent, layer.crs())
            if combined is None:
                combined = QgsRectangle(extent)
            else:
                combined.combineExtentWith(extent)
        if combined is None:
            return False
        canvas.setExtent(combined)
        canvas.refresh()
        return True
    except Exception as e:
        print(f"[CanvasHighlight] Failed to zoom to layer(s): {e}")
        return False


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
