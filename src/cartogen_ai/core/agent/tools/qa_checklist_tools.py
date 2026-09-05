# -*- coding: utf-8 -*-
"""Automated per-map-product QA checklist for Cartogen AI -- point 26 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md, confirmed distinct
from this plugin's own docs/RELEASE_SMOKE_TEST.md (that document verifies
the *plugin's tools* work in a real QGIS session before a release; this
tool checks one specific *map product's* readiness, no automated
equivalent of which existed anywhere).

Pure assembly, no new tracked state: reads dataset_status (point 2) for
data readiness, list_layout_items (point 15) for cartographic
completeness, and get_provenance_record (point 17) for export/provenance
-- the same "read from what already exists rather than tracking it a
second time" approach point 17's own provenance sidecar used. Disclosure/
sensitivity has no automated classification to read from yet (point 24 of
the same review is a real gap, not built), so that section is an honest
static reminder, not a guessed pass/fail."""

from .registry import register_tool
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

    # Point 24 (sensitivity/disclosure classification) is a real gap, not
    # built -- this is an honest static reminder, not a guessed pass/fail
    # from a classification scheme that doesn't exist.
    categories["disclosure"] = {
        "note": (
            "No automated sensitivity/disclosure classification exists yet (PUBLIC/INTERNAL/"
            "RESTRICTED/SENSITIVE tagging -- point 24 of the architecture review). Manually "
            "confirm this layer doesn't need obfuscate_sensitive_points or an export review "
            "before sharing."
        ),
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
