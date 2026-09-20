# -*- coding: utf-8 -*-
"""
Confidence/uncertainty classification tools for Cartogen AI -- the
agent-facing surface of agent/confidence.py (point 23 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md). See that module's
own docstring for the full design.
"""

from .registry import register_tool
from ...models import confidence as _conf

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


@register_tool(
    "set_layer_confidence",
    "Tags a layer with its epistemic-status/confidence level -- OBSERVED (directly recorded, "
    "e.g. a surveyed facility location), DERIVED (computed from observed data with no modeling "
    "assumptions, e.g. a buffer or spatial join), MODELED (built from a model with real "
    "assumptions, e.g. a service area or population-exposure estimate), INFERRED (a conclusion "
    "drawn beyond what the data directly shows), or UNKNOWN (provenance genuinely unclear). Use "
    "this on any layer whose confidence level matters for how a reader should trust it -- "
    "especially anything that will be exported or printed. No automated classification exists -- "
    "only what's explicitly set here is tracked.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "level": {
                "type": "string",
                "enum": _conf.CONFIDENCE_LEVELS,
                "description": "OBSERVED, DERIVED, MODELED, INFERRED, or UNKNOWN.",
            },
            "reason": {
                "type": "string",
                "description": "Optional short reason, e.g. 'buffer output, no field verification' or 'population estimate, WorldPop 2025 raster'.",
            },
        },
        "required": ["layer_name", "level"],
    },
)
def set_layer_confidence(layer_name, level, reason=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if level not in _conf.CONFIDENCE_LEVELS:
        return {"error": f"level must be one of {_conf.CONFIDENCE_LEVELS}, got {level!r}"}
    if not _conf.set_layer_confidence(layer, level, reason):
        return {"error": "Failed to tag layer confidence."}
    return {"success": True, "layer_name": layer_name, "level": level, "reason": reason}


@register_tool(
    "get_layer_confidence",
    "Reads a layer's current confidence/epistemic-status classification, if any was set via "
    "set_layer_confidence. Returns level=null if never tagged -- not the same as UNKNOWN, just "
    "unclassified.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]},
)
def get_layer_confidence(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    record = _conf.get_layer_confidence(layer)
    return {"success": True, "layer_name": layer_name, **record}
