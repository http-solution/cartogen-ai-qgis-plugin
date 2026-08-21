# -*- coding: utf-8 -*-
"""
Proactive Map Context Summary for Cartogen AI.
Builds a lightweight snapshot of the current project/canvas so the agent has
baseline spatial awareness without needing a get_layers() tool round-trip on
every request. Must only be called from the main Qt thread -- QgsProject and
iface are not thread-safe.
"""

MAX_LAYERS = 15
MAX_FIELDS_PER_LAYER = 8

try:
    from qgis.core import QgsProject
    from qgis.utils import iface
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    iface = None


def get_map_context_summary() -> dict:
    """Returns a capped, lightweight summary of loaded layers, CRS, and the
    active layer. Returns {} if QGIS isn't available or nothing is loaded."""
    if not QGIS_AVAILABLE:
        return {}

    try:
        project = QgsProject.instance()
        all_layers = list(project.mapLayers().values())
        if not all_layers:
            return {}

        layers = []
        for layer in all_layers[:MAX_LAYERS]:
            if not layer.isValid():
                continue
            fields = []
            if hasattr(layer, "fields"):
                try:
                    fields = [f.name() for f in layer.fields()][:MAX_FIELDS_PER_LAYER]
                except Exception:
                    fields = []
            feature_count = None
            if hasattr(layer, "featureCount"):
                try:
                    feature_count = layer.featureCount()
                except Exception:
                    feature_count = None
            layer_type = layer.type()
            layers.append({
                "name": layer.name(),
                "type": layer_type.name if hasattr(layer_type, "name") else str(layer_type),
                "crs": layer.crs().authid() if layer.crs() else "",
                "feature_count": feature_count,
                "fields": fields,
            })

        active_layer = iface.activeLayer() if iface else None
        canvas = iface.mapCanvas() if iface else None

        return {
            "project_title": project.title() or "Untitled Project",
            "canvas_crs": canvas.mapSettings().destinationCrs().authid() if canvas else "",
            "active_layer": active_layer.name() if active_layer else "None",
            "layer_count": len(all_layers),
            "layers": layers,
            "truncated": len(all_layers) > MAX_LAYERS,
        }
    except Exception as e:
        print(f"[MapContext] Failed to build map context summary: {e}")
        return {}
