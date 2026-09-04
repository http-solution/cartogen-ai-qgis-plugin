# -*- coding: utf-8 -*-
"""
Schema-contract tools for Cartogen AI -- the agent-facing surface of
agent/schema_contracts.py (point 5 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: machine-readable
YAML/JSON dataset schema contracts, closing the REAL GAP that column
meaning was only ever inferred by the model at call time, never
pre-validated against a contract). See that module's own docstring for the
contract JSON shape and why fields are matched by alias list rather than
one fixed name.
"""

from .registry import register_tool
from .. import schema_contracts as _sc

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
    "list_schema_contracts",
    "List the machine-readable dataset schema contracts available to validate_schema (currently "
    "health_facilities and admin2 -- see agent/contracts/*.json). Each contract declares required "
    "fields (by acceptable name aliases, since real-world admin/pcode field names vary by source), "
    "expected field types, and optional controlled-vocabulary domains.",
    {"type": "object", "properties": {}, "required": []},
)
def list_schema_contracts():
    return {"success": True, "contracts": _sc.list_contracts()}


@register_tool(
    "validate_schema",
    "Check a vector layer's fields -- presence, type, and any controlled-vocabulary values -- "
    "against a named schema contract (see list_schema_contracts for available names). Field "
    "matching is case-insensitive and checks a contract's full alias list, not one fixed name, so "
    "e.g. 'ADM2_PCODE' from a COD-AB download and 'admin2_pcode' from a hand-built layer both "
    "satisfy the same required field. Returns missing_fields/type_mismatches/value_violations and "
    "an overall passed flag -- never blocks anything by itself, but feeds "
    "advance_dataset_status's VALIDATED -> ANALYSIS_READY gate when a contract_name is supplied "
    "there.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "contract_name": {"type": "string", "description": "e.g. 'health_facilities' or 'admin2'. See list_schema_contracts."},
        },
        "required": ["layer_name", "contract_name"],
    },
)
def validate_schema(layer_name, contract_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    result = _sc.validate_layer_schema(layer, contract_name)
    if "error" in result:
        return result
    return {**result, "layer_name": layer_name}
