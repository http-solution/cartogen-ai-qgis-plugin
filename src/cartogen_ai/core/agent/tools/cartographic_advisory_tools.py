# -*- coding: utf-8 -*-
"""
Visualization-selection advisory tool for Cartogen AI -- v1.8.0 workstream 1,
adapting the external "QGIS Cartographic Intelligence Standard" document's
decision matrix (section 3) to this codebase's own conventions rather than
building a rigid, separate rules engine.

ADVISORY ONLY, by explicit product decision: this module never applies any
styling itself. It gathers a layer/field's real geometry type, field type,
cardinality, and distribution, then returns a recommendation + rationale --
the model still decides and calls the actual apply_*_style tool, the same
way styling_tools.py's own _classify_values() already informs
apply_graduated_style without bypassing the caller. This matches rule 19's
"pick a sensible default, state it, don't stop to ask" convention rather
than adding a second, competing auto-styling path.
"""

from .registry import register_tool
from .styling_tools import _layer_geometry_kind, _classify_values, _find_layer_by_name
from . import styling_tools as _styling_tools

# styling_tools.py's own QGIS_AVAILABLE flag is what actually gates every
# QGIS-touching call in this file (via _find_layer_by_name/_layer_geometry_kind,
# which already degrade to None/"unknown" without QGIS) -- referenced
# directly as _styling_tools.QGIS_AVAILABLE rather than re-derived, so the
# two modules can never disagree about whether QGIS is available.


# Heuristic keyword lists, not a proof -- surfaced as part of a recommendation
# a human/model still reviews, never as a silent auto-decision. Field-name
# hints are checked first (cheapest, most specific to a caller's own naming);
# value-range hints are the fallback for an unfamiliar field name.
_RATE_NAME_HINTS = (
    "rate", "pct", "percent", "ratio", "density", "per_capita", "per_1000",
    "per1000", "prevalence", "index", "score", "_per_", "proportion",
)
_COUNT_NAME_HINTS = (
    "count", "total", "num_", "_num", "n_", "sum_", "population", "cases",
    "incidents", "affected", "beneficiaries",
)


def _looks_like_rate_or_percentage(field_name, values):
    """True when a numeric field's NAME or VALUE RANGE suggests an already-
    normalized measure (rate/percentage/index/score) rather than a raw
    count. Pure Python, no QGIS needed -- unit-testable directly."""
    name_l = (field_name or "").lower()
    if any(hint in name_l for hint in _RATE_NAME_HINTS):
        return True
    if values:
        lo, hi = min(values), max(values)
        if lo >= 0 and hi <= 1.0001:
            return True
        # A 0-100 range with any non-integer value reads as a percentage;
        # a 0-100 range of pure integers is just as likely a small raw
        # count, so that case is left to the count-name-hint check instead
        # of guessed here.
        if lo >= 0 and hi <= 100.0001 and any(float(v) != int(v) for v in values):
            return True
    return False


def _looks_like_raw_count(field_name, values):
    """True when a numeric field's NAME or shape (large whole numbers)
    suggests a raw magnitude/total rather than a normalized rate. Pure
    Python, no QGIS needed."""
    name_l = (field_name or "").lower()
    if any(hint in name_l for hint in _COUNT_NAME_HINTS):
        return True
    if values and all(float(v).is_integer() for v in values) and max(values) > 100:
        return True
    return False


def _recommend_for_geometry(geometry_kind, field_present, field_numeric, cardinality,
                             looks_like_rate, looks_like_count, feature_count,
                             classification=None):
    """Pure decision logic -- no QGIS import, fully unit-testable. Mirrors
    the external standard's visualization decision matrix (section 3),
    adapted to the specific tool names this codebase actually has.
    geometry_kind is 'point'/'line'/'polygon'/'raster'/'unknown', the same
    vocabulary styling_tools._layer_geometry_kind already returns."""
    warnings = []

    if geometry_kind == "raster":
        return {
            "recommended_tool": "apply_raster_stretch",
            "rationale": "Continuous raster surface -- apply_raster_stretch auto-picks a diverging "
                         "index ramp for NDVI/NDWI/NDRE-named layers, or a grayscale contrast "
                         "stretch otherwise.",
            "warnings": warnings,
            "suggested_params": {},
        }

    if not field_present:
        if geometry_kind == "point" and feature_count and feature_count > 200:
            return {
                "recommended_tool": "hotspot_analysis",
                "rationale": "Many point features with no field to style by -- hotspot_analysis "
                             "builds a real kernel-density raster showing concentration; "
                             "apply_heatmap_style is a lighter-weight VISUAL-ONLY alternative when a "
                             "real KDE raster isn't needed. Never present either as a measured risk "
                             "value -- both are exploratory concentration views, not an assessed "
                             "quantity.",
                "warnings": warnings,
                "suggested_params": {},
            }
        return {
            "recommended_tool": None,
            "rationale": "No field given -- this is a reference/location map. Leave unstyled "
                         "(default symbol) unless a real category or measured field exists to "
                         "style by.",
            "warnings": warnings,
            "suggested_params": {},
        }

    if not field_numeric:
        if cardinality is not None and cardinality > 15:
            warnings.append(
                f"{cardinality} distinct category values is a lot for one legend -- consider "
                "whether a coarser grouping, or a different question, would communicate better."
            )
        if geometry_kind == "line" and cardinality is not None and cardinality <= 6:
            return {
                "recommended_tool": "apply_rule_based_style",
                "rationale": "A small fixed vocabulary on a line layer (e.g. route/facility status) "
                             "usually needs a caller-chosen FIXED color per value with an explicit "
                             "'Unknown / No data' class -- apply_rule_based_style, not an "
                             "auto-assigned qualitative palette.",
                "warnings": warnings,
                "suggested_params": {},
            }
        return {
            "recommended_tool": "apply_categorized_style",
            "rationale": "Nominal (unordered) categories -- apply_categorized_style uses a "
                         "qualitative palette designed to maximally distinguish unrelated "
                         "categories, not a sequential/diverging ramp that would falsely imply "
                         "order.",
            "warnings": warnings,
            "suggested_params": {},
        }

    # Numeric field from here on.
    if looks_like_count and geometry_kind == "polygon":
        warnings.append(
            "This field looks like a raw count, not a rate/density -- choropleth-coloring raw "
            "counts on polygons of differing size/population is a common misuse (a large or "
            "populous unit looks more 'severe' purely because it's bigger). Normalize by area, "
            "population, or another meaningful denominator first, or name the denominator "
            "explicitly if the raw count is genuinely the intended message."
        )
        return {
            "recommended_tool": "apply_graduated_style",
            "rationale": "Numeric polygon field, flagged as a likely raw count -- see warnings "
                         "before choropleth-coloring it. If this is genuinely a magnitude/total "
                         "rather than a rate, a proportional symbol at each polygon's centroid "
                         "usually reads more honestly than fill color, but there is no "
                         "polygon-centroid proportional-symbol tool yet -- apply_graduated_symbol_style "
                         "only supports point layers today.",
            "warnings": warnings,
            "suggested_params": {},
        }

    if geometry_kind == "polygon":
        rationale = "Numeric polygon field"
        if looks_like_rate:
            rationale += " that looks like a rate/percentage/index -- a choropleth is the right fit."
        else:
            rationale += " -- apply_graduated_style auto-selects a classification method from the distribution."
        params = {}
        if classification:
            params["expected_classification_method"] = classification["method_label"]
            params["expected_color_ramp"] = classification["ramp"]
        return {
            "recommended_tool": "apply_graduated_style",
            "rationale": rationale,
            "warnings": warnings,
            "suggested_params": params,
        }

    if geometry_kind == "point":
        return {
            "recommended_tool": "apply_graduated_symbol_style",
            "rationale": "Numeric point field -- proportional symbol size encodes absolute "
                         "magnitude more honestly than choropleth color would for point data.",
            "warnings": warnings,
            "suggested_params": {},
        }

    if geometry_kind == "line":
        return {
            "recommended_tool": "apply_graduated_style",
            "rationale": "Numeric line field -- apply_graduated_style's classification/ramp choice "
                         "applies to line symbol color the same way it does to polygon fill.",
            "warnings": warnings,
            "suggested_params": {},
        }

    return {
        "recommended_tool": None,
        "rationale": "Could not determine this layer's geometry type -- inspect it directly "
                     "(get_layers) before styling.",
        "warnings": warnings,
        "suggested_params": {},
    }


@register_tool(
    "recommend_visualization_method",
    "Recommends which styling tool fits a layer/field's actual data semantics -- geometry type, "
    "field type, cardinality, and distribution -- before you style it, instead of guessing the "
    "renderer or defaulting to whichever tool was used last. ADVISORY ONLY: returns a "
    "recommendation and rationale, never applies any styling itself -- you still call the "
    "recommended tool (or a different one, if you have good reason) yourself. Use this before "
    "any apply_*_style call on a field you haven't already styled by in this conversation, "
    "especially before a choropleth on a polygon layer, since the single most common real-world "
    "misuse is coloring raw counts instead of a rate/density.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "field": {
                "type": "string",
                "description": "Optional. Omit for a reference/location-only map with no field to style by.",
            },
            "intended_message": {
                "type": "string",
                "description": "Optional free-text hint, e.g. 'show which districts have the worst "
                "access gap' or 'show route status'. Used only to explain a recommendation more "
                "specifically -- never to override what the data itself actually supports.",
            },
        },
        "required": ["layer_name"],
    },
)
def recommend_visualization_method(layer_name, field=None, intended_message=None):
    if not _styling_tools.QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    geometry_kind = _layer_geometry_kind(layer)

    field_present = bool(field)
    if field_present and field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{field}' not found in '{layer_name}'"}

    field_numeric = False
    numeric_values = []
    cardinality = None
    feature_count = None
    classification = None

    if field_present:
        raw_values = [feat[field] for feat in layer.getFeatures() if feat[field] is not None]
        numeric_values = [v for v in raw_values if isinstance(v, (int, float))]
        field_numeric = bool(raw_values) and len(numeric_values) == len(raw_values)
        if not field_numeric:
            cardinality = len(set(str(v) for v in raw_values))
        elif len(numeric_values) > 5:
            classification = _classify_values(numeric_values)
    else:
        try:
            feature_count = layer.featureCount()
        except Exception:
            feature_count = None

    looks_like_rate = field_numeric and _looks_like_rate_or_percentage(field, numeric_values)
    looks_like_count = field_numeric and _looks_like_raw_count(field, numeric_values)

    result = _recommend_for_geometry(
        geometry_kind, field_present, field_numeric, cardinality,
        looks_like_rate, looks_like_count, feature_count, classification,
    )
    result["layer_name"] = layer_name
    result["field"] = field
    result["geometry_kind"] = geometry_kind
    if intended_message:
        result["intended_message"] = intended_message
    return result
