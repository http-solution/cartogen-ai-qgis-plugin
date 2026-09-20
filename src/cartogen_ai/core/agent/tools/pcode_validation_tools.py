# -*- coding: utf-8 -*-
"""
P-code depth tools for Cartogen AI -- the agent-facing surface of
validators/pcode_validation.py (point 6 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: P-code uniqueness
and parent/child hierarchy validation, extending
HUMANITARIAN_CARTOGRAPHY_STANDARDS.md Section I's already-logged basic
P-code usage check). See that module's own docstring for exact scope and
what's deliberately not addressed (temporal validity, retired-P-code
reuse).
"""

from .registry import register_tool
from ...validators import pcode_validation as _pv

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
    "check_pcode_uniqueness",
    "Check that every P-code value in a layer is unique across its features -- flags duplicate "
    "admin-unit codes that would silently corrupt a P-code join in calculate_severity_index or "
    "calculate_presence_gap. Tries the admin2 P-code field aliases (admin2_pcode/adm2_pcode/"
    "ADM2_PCODE) automatically if pcode_field isn't given.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "pcode_field": {"type": "string", "description": "Optional. Field to check; auto-detected from common P-code field names if omitted."},
        },
        "required": ["layer_name"],
    },
)
def check_pcode_uniqueness(layer_name, pcode_field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    result = _pv.check_pcode_uniqueness(layer, pcode_field=pcode_field)
    if "error" in result:
        return result
    return {**result, "layer_name": layer_name}


@register_tool(
    "check_pcode_hierarchy",
    "Check that each feature's child P-code (e.g. admin2_pcode) is prefixed by its own parent "
    "P-code (e.g. admin1_pcode) on the same row -- the real OCHA/HDX COD-AB convention (admin2 "
    "'YE1201' under admin1 'YE12'). This is a string-prefix check on two sibling attributes, NOT "
    "a spatial containment check -- it does not verify the admin2 polygon actually sits inside "
    "the admin1 polygon's geometry, only that the codes are structurally consistent. Auto-detects "
    "both fields from common P-code field names if not given.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "child_pcode_field": {"type": "string", "description": "Optional. Defaults to an admin2 P-code alias."},
            "parent_pcode_field": {"type": "string", "description": "Optional. Defaults to an admin1 P-code alias."},
        },
        "required": ["layer_name"],
    },
)
def check_pcode_hierarchy(layer_name, child_pcode_field=None, parent_pcode_field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    result = _pv.check_pcode_hierarchy(
        layer, child_pcode_field=child_pcode_field, parent_pcode_field=parent_pcode_field,
    )
    if "error" in result:
        return result
    return {**result, "layer_name": layer_name}
