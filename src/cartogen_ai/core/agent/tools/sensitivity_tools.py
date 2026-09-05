# -*- coding: utf-8 -*-
"""
Sensitivity / disclosure classification tools for Cartogen AI -- the
agent-facing surface of agent/sensitivity.py (point 24 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md). See that module's
own docstring for the full design and why this is advisory, not a hard
export-blocking gate.
"""

from .registry import register_tool
from .. import sensitivity as _sens

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
    "set_layer_sensitivity",
    "Tags a layer with a sensitivity/disclosure classification -- PUBLIC, INTERNAL, RESTRICTED, "
    "or SENSITIVE. Use for a layer containing individual beneficiary locations, protection "
    "incident details, or anything else that shouldn't be shared broadly. export_layer/"
    "export_to_csv check this and add an advisory warning (not a block -- the export still "
    "completes) when exporting a RESTRICTED/SENSITIVE layer. No automated classification exists "
    "-- only what's explicitly set here is tracked.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "level": {
                "type": "string",
                "enum": _sens.SENSITIVITY_LEVELS,
                "description": "PUBLIC, INTERNAL, RESTRICTED, or SENSITIVE.",
            },
            "reason": {
                "type": "string",
                "description": "Optional short reason shown in the export warning, e.g. 'contains individual beneficiary GPS coordinates'.",
            },
        },
        "required": ["layer_name", "level"],
    },
)
def set_layer_sensitivity(layer_name, level, reason=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if level not in _sens.SENSITIVITY_LEVELS:
        return {"error": f"level must be one of {_sens.SENSITIVITY_LEVELS}, got {level!r}"}
    if not _sens.set_layer_sensitivity(layer, level, reason):
        return {"error": "Failed to tag layer sensitivity."}
    return {"success": True, "layer_name": layer_name, "level": level, "reason": reason}


@register_tool(
    "get_layer_sensitivity",
    "Reads a layer's current sensitivity/disclosure classification, if any was set via "
    "set_layer_sensitivity. Returns level=null if never tagged -- not the same as PUBLIC, just "
    "unclassified.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]},
)
def get_layer_sensitivity(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    record = _sens.get_layer_sensitivity(layer)
    return {"success": True, "layer_name": layer_name, **record}
