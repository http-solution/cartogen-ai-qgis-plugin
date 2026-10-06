# -*- coding: utf-8 -*-
"""apply_humanitarian_look: give a result field written by an analysis tool its humanitarian map look (HX1).

calculate_severity_index, calculate_population_in_need, calculate_presence_gap, calculate_damage_exposure_severity and calculate_mcda_ranking
write their result into a field of the user's own layer. Those tools never restyle a layer they did not create, so the result used to
arrive in QGIS's single default colour. This tool is what they point to (their `map_look` hint): one explicit call that changes only
the layer's renderer, with the class limits and palettes defined in humanitarian_style (severity classes that match the tool's own
1-5 classes, count classes, presence-gap categories, rank bands). Written without a local QGIS for the QGIS half; the pure rules are
unit tested offline and the renderer is covered by tests/test_humanitarian_look_live.py in CI.
"""
from .registry import register_tool

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

LOOK_DESCRIPTIONS = {
    "severity": "a 0-1 composite severity score (calculate_severity_index, calculate_damage_exposure_severity): five equal-interval classes, "
                "yellow to dark red, the same classes the tools report",
    "people_in_need": "a people / population count (calculate_population_in_need): quantile classes in purple",
    "exposure": "an exposed-population count: quantile classes in orange-brown",
    "allocation": "an allocation amount (calculate_allocation_envelope): quantile classes in green",
    "presence_gap": "the gap / covered / unmatched status from calculate_presence_gap",
    "jiaf_severity": "a JIAF 2 severity PHASE 1-5 (jf_pre_sev, jf_fin_sev): phase colours 1 none/minimal to 5 catastrophic; a unit with no phase is drawn grey as not assessed",
    "jiaf_review_pin": "JIAF 2 PiN review status (jf_pin_st): which units have no flag, were closed in bulk, were decided, or still wait for the group",
    "jiaf_review_severity": "JIAF 2 severity review status (jf_sev_st): preliminary accepted, decided, pending the group, or incomplete sector coverage",
    "jiaf_count": "a small JIAF 2 count per unit (jf_npinfl, jf_nsevfl, jf_nsec40, jf_nsev45): how many flags or sectors; zero its own class",
    "rank": "a rank field (calculate_mcda_ranking, <prefix>_rank): the top_k units dark, the next top_k mid, the rest pale",
}


@register_tool(
    "apply_humanitarian_look",
    "Style a layer's analysis-result field the way humanitarian maps expect, after calculate_severity_index, calculate_population_in_need, "
    "calculate_presence_gap, calculate_damage_exposure_severity, calculate_mcda_ranking or calculate_allocation_envelope wrote it (their results carry a `map_look` hint "
    "with the exact arguments). look='severity': a 0-1 score in five equal classes yellow to dark red that match the tool's own 1-5 classes; "
    "'people_in_need', 'exposure' or 'allocation': a count or amount in quantile classes; 'presence_gap': gap / covered / unmatched; 'rank': the top_k ranked units "
    "dark. Changes only the layer's renderer (nothing is written to the data); units with no value in the field are not drawn. Only call it "
    "when the user wants the result shown on the map or accepts the offer.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "The layer that holds the result field."},
            "look": {"type": "string", "enum": list(LOOK_DESCRIPTIONS), "description": "; ".join(f"{k}: {v}" for k, v in LOOK_DESCRIPTIONS.items())},
            "field": {"type": "string", "description": "The result field to style."},
            "top_k": {"type": "integer", "description": "For look='rank': how many top-ranked units to emphasise. Defaults to 10."},
        },
        "required": ["layer_name", "look", "field"],
    },
)
def apply_humanitarian_look(layer_name, look, field, top_k=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from .humanitarian_style import LOOKS, style_result_field
    if look not in LOOKS:
        return {"error": f"look must be one of {list(LOOKS)}."}
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        return {"error": f"Layer '{layer_name}' not found"}
    if len(layers) > 1:
        return {"error": f"'{layer_name}' matches {len(layers)} layers; rename the duplicates first so the look goes on the right one."}
    layer = layers[0]
    if not hasattr(layer, "fields"):
        return {"error": f"'{layer_name}' is not a vector layer."}
    result = style_result_field(layer, look, field, top_k)
    if "error" in result:
        return result
    return {"success": True, "layer_name": layer_name, "look": look, "field": field, "classes": result["classes"], "notes": result["notes"]}
