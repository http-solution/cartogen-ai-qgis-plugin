# -*- coding: utf-8 -*-
"""Automated per-map-product QA checklist for Cartogen AI -- point 26 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md, confirmed distinct
from this plugin's own docs/RELEASE_SMOKE_TEST.md (that document verifies
the *plugin's tools* work in a real QGIS session before a release; this
tool checks one specific *map product's* readiness, no automated
equivalent of which existed anywhere).

Pure assembly, no new tracked state: reads dataset_status (point 2) for
data readiness, list_layout_items (point 15) for cartographic
completeness, sensitivity.py (point 24) for disclosure classification,
and get_provenance_record (point 17) for export/provenance -- the same
"read from what already exists rather than tracking it a second time"
approach point 17's own provenance sidecar used.

v1.8.0 workstream 2: the disclosure section used to be a static reminder
("no automated classification exists yet") even though point 24's real
classification (agent/sensitivity.py, set_layer_sensitivity/
get_layer_sensitivity) already existed -- this checklist simply never
read it. Fixed by reading the layer's real sensitivity tag directly."""

from .registry import register_tool
from .. import sensitivity as _sens
from .dataset_status_tools import get_dataset_status
from .provenance_tools import get_provenance_record
from .layout_tools import list_layout_items

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


_MANDATORY_LAYOUT_ELEMENTS = {
    "MAP_MAIN": "map",
    "TITLE": "title",
    "LEGEND": "legend",
    "SCALEBAR": "scale bar",
    "NORTH_ARROW": "north arrow",
}


@register_tool(
    "generate_map_product_qa_checklist",
    "Assembles a QA checklist for one map product -- a layer, optionally paired with a print "
    "layout -- covering data readiness, cartographic completeness, disclosure/sensitivity, and "
    "export/provenance. Reads from what's already tracked (dataset_status, layout item ids, "
    "provenance) rather than re-deriving or guessing any of it. Point 26 of "
    "docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md -- distinct from this plugin's own "
    "docs/RELEASE_SMOKE_TEST.md, which verifies the plugin's tools work in a live QGIS session, "
    "not an individual map product's readiness.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "layout_name": {
                "type": "string",
                "description": "Optional print layout built for this product (from create_print_layout) -- checked for the mandatory MAP_MAIN/TITLE/LEGEND/SCALEBAR/NORTH_ARROW elements. Omit to skip the cartography section.",
            },
        },
        "required": ["layer_name"],
    },
)
def generate_map_product_qa_checklist(layer_name, layout_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    categories = {}

    status_res = get_dataset_status(layer_name)
    if status_res.get("status") is None:
        categories["data"] = {
            "tracked": False,
            "note": "No QA-gate status tracked for this layer -- see set_dataset_status/advance_dataset_status.",
        }
    else:
        categories["data"] = {
            "tracked": True,
            "status": status_res["status"],
            "checks": status_res.get("checks", {}),
        }

    if layout_name:
        items_res = list_layout_items(layout_name)
        if not items_res.get("success"):
            categories["cartography"] = {"error": items_res.get("error")}
        else:
            ids_present = {item["id"] for item in items_res["items"]}
            categories["cartography"] = {
                "layout_name": layout_name,
                "mandatory_elements_present": [
                    label for item_id, label in _MANDATORY_LAYOUT_ELEMENTS.items() if item_id in ids_present
                ],
                "mandatory_elements_missing": [
                    label for item_id, label in _MANDATORY_LAYOUT_ELEMENTS.items() if item_id not in ids_present
                ],
            }
    else:
        categories["cartography"] = {
            "note": "No layout_name given -- skipped. Pass the print layout built for this product to check mandatory elements.",
        }

    # v1.8.0 workstream 2: reads the layer's real sensitivity tag (point 24,
    # agent/sensitivity.py) instead of a static "no classification exists"
    # reminder -- that classification has existed since point 24 shipped,
    # this checklist just never read it until now.
    sensitivity_record = _sens.get_layer_sensitivity(layer)
    level = sensitivity_record.get("level")
    if level is None:
        categories["disclosure"] = {
            "tracked": False,
            "level": None,
            "note": (
                "This layer has no sensitivity classification set (set_layer_sensitivity). "
                "Not the same as PUBLIC -- unclassified. Confirm this layer doesn't need "
                "obfuscate_sensitive_points or a sensitivity tag before sharing."
            ),
        }
    else:
        categories["disclosure"] = {
            "tracked": True,
            "level": level,
            "reason": sensitivity_record.get("reason"),
            "warning": _sens.export_warning_for(layer) or None,
        }

    prov_res = get_provenance_record(layer_name)
    if prov_res.get("success"):
        categories["export_provenance"] = {
            "tracked": True,
            "tool_execution_count": len(prov_res.get("lineage", [])),
            "qgis_version": prov_res.get("qgis_version"),
        }
    else:
        categories["export_provenance"] = {"tracked": False, "note": prov_res.get("error", "Provenance unavailable.")}

    return {"success": True, "layer_name": layer_name, "categories": categories}
