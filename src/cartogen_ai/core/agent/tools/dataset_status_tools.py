# -*- coding: utf-8 -*-
"""
Dataset Status / QA-Gate tools for Cartogen AI -- the agent-facing surface
of agent/dataset_status.py (point 2 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: a dataset-lifecycle
state machine, INGESTED -> STAGED -> VALIDATED -> ANALYSIS_READY ->
CARTOGRAPHY_READY -> PUBLICATION_READY, tracked per-layer). See that
module's own docstring for the full design; P-code depth (point 6), geometry
QA (point 4), and schema contracts (point 5) are now wired in as automated
checks, and temporal validity / provenance sidecar (points 7, 17) remain
deliberately not built yet.
"""

from .registry import register_tool
from .. import dataset_status as _ds

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
    "get_dataset_status",
    "Read a layer's tracked QA-gate lifecycle status (one of INGESTED, STAGED, VALIDATED, "
    "ANALYSIS_READY, CARTOGRAPHY_READY, PUBLICATION_READY), its full status-change history, and "
    "any automated check results recorded against it. Returns status=null for a layer that has "
    "never been tagged -- call set_dataset_status first to start tracking it.",
    {
        "type": "object",
        "properties": {"layer_name": {"type": "string"}},
        "required": ["layer_name"],
    },
)
def get_dataset_status(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    record = _ds.get_dataset_status(layer)
    return {"success": True, "layer_name": layer_name, **record}


@register_tool(
    "set_dataset_status",
    "Start QA-gate lifecycle tracking on a layer that isn't tracked yet, tagging it with a "
    "starting status (defaults to INGESTED). Refuses to run on a layer that already has a "
    "tracked status -- use advance_dataset_status to move an already-tracked layer forward or "
    "back instead, so this can't accidentally erase real QA history.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "status": {
                "type": "string",
                "description": "Starting status. One of INGESTED, STAGED, VALIDATED, ANALYSIS_READY, CARTOGRAPHY_READY, PUBLICATION_READY. Defaults to INGESTED.",
            },
            "note": {"type": "string", "description": "Optional note explaining why tracking starts at this status."},
        },
        "required": ["layer_name"],
    },
)
def set_dataset_status(layer_name, status="INGESTED", note=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    result = _ds.set_initial_status(layer, status=status, note=note)
    if "error" in result:
        return result
    return {**result, "layer_name": layer_name}


@register_tool(
    "advance_dataset_status",
    "Move a layer's QA-gate lifecycle status forward one step (e.g. STAGED -> VALIDATED), "
    "backward (to mark a regression), or re-state it -- never skipping a state. The "
    "INGESTED -> STAGED step automatically runs a P-code depth check (uniqueness + "
    "parent/child hierarchy prefix-match) when the layer has P-code-shaped fields, and "
    "auto-passes as not-applicable otherwise -- so it never blocks a non-admin-boundary layer. "
    "The STAGED -> VALIDATED step automatically runs the existing geometry-validity check "
    "(diagnose_topology) and refuses to advance if it fails, unless override=True is passed "
    "with a note justifying the bypass. The VALIDATED -> ANALYSIS_READY step runs a "
    "schema-contract check (validate_schema) instead, but ONLY when contract_name is supplied -- "
    "omit it and this transition behaves like any other unchecked one (a note is required). The "
    "CARTOGRAPHY_READY -> PUBLICATION_READY step runs a map-QA check "
    "(generate_map_product_qa_checklist) when layout_name is supplied -- refuses to advance if "
    "the layout is missing a mandatory element (map/title/legend/scale bar/north arrow) or the "
    "layer is tagged RESTRICTED/SENSITIVE, unless override=True is passed with a note justifying "
    "the bypass. Omit layout_name and this transition behaves like any other unchecked one. Every "
    "other transition has no automated check yet and requires a note explaining the manual "
    "advance. Moving backward always requires a note. Call get_dataset_status first if unsure of "
    "the layer's current status, set_dataset_status first if it isn't tracked yet, and "
    "list_schema_contracts to see available contract_name values.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "target_status": {
                "type": "string",
                "description": "One of INGESTED, STAGED, VALIDATED, ANALYSIS_READY, CARTOGRAPHY_READY, PUBLICATION_READY.",
            },
            "note": {"type": "string", "description": "Required for transitions with no automated check, for any backward move, and for an override."},
            "override": {"type": "boolean", "description": "Bypass a failed automated check. Requires note. Defaults to false."},
            "contract_name": {"type": "string", "description": "Only used for VALIDATED -> ANALYSIS_READY, e.g. 'health_facilities' or 'admin2'. See list_schema_contracts."},
            "layout_name": {"type": "string", "description": "Only used for CARTOGRAPHY_READY -> PUBLICATION_READY -- the print layout built for this map product (from create_print_layout)."},
        },
        "required": ["layer_name", "target_status"],
    },
)
def advance_dataset_status(layer_name, target_status, note=None, override=False, contract_name=None, layout_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    result = _ds.advance_dataset_status(
        layer, target_status, note=note, override=override, contract_name=contract_name, layout_name=layout_name,
    )
    if "error" in result:
        return result
    return {**result, "layer_name": layer_name}
