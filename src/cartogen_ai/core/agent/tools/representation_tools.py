# -*- coding: utf-8 -*-
"""
High-Level Representation & Cartographic Planning Tools for Cartogen AI.

Exposes:
- analyze_layer_for_visualization
- recommend_map_representation
- apply_recommended_representation
- explain_current_representation
"""

from typing import Any, Dict, Optional
from .registry import register_tool
from ..map_intelligence import ChatActionRegistry
from ...representation.models import RepresentationCandidate
from ...representation.profiler import profile_layer
from ...representation.planner import plan_representations
from ...representation.applier import apply_representation

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _get_layer(name: str):
    if not QGIS_AVAILABLE or not QgsProject.instance():
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


@register_tool(
    "analyze_layer_for_visualization",
    "Analyze a layer's geometry, feature count, spatial density, overlap ratio, and attribute semantics (rates vs raw counts, nominals, temporal) to inform cartographic representation decisions.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Name of the layer in the QGIS project to analyze."},
        },
        "required": ["layer_name"],
    },
)
def analyze_layer_for_visualization(layer_name: str) -> Dict[str, Any]:
    layer = _get_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found."}

    prof = profile_layer(layer)
    fields_summary = {}
    for fn, fp in prof.fields.items():
        fields_summary[fn] = {
            "semantic_type": fp.semantic_type,
            "is_numeric": fp.is_numeric,
            "distinct_count": fp.distinct_count,
            "distribution": fp.distribution,
            "skewness": round(fp.skewness, 2) if fp.skewness is not None else None,
        }

    return {
        "success": True,
        "layer_name": prof.layer_name,
        "layer_type": prof.layer_type,
        "geometry": prof.geometry,
        "feature_count": prof.feature_count,
        "spatial_density": prof.spatial_density,
        "overlap_ratio": prof.overlap_ratio,
        "crs": prof.crs_authid,
        "fields": fields_summary,
    }


@register_tool(
    "recommend_map_representation",
    "Evaluate candidate map representations for a layer based on spatial density, geometry, and analytical question (e.g. 'Where are they concentrated', 'Which are largest', 'What category'). Returns scored candidates and interactive action options.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Name of the layer to evaluate."},
            "user_intent": {"type": "string", "description": "The analytical question or intent, e.g. 'show density', 'compare size', 'show status category'."},
            "target_field": {"type": "string", "description": "Optional attribute field to style or symbolize by."},
        },
        "required": ["layer_name"],
    },
)
def recommend_map_representation(layer_name: str, user_intent: Optional[str] = None, target_field: Optional[str] = None) -> Dict[str, Any]:
    layer = _get_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found."}

    prof = profile_layer(layer)
    candidates = plan_representations(prof, user_intent=user_intent, target_field=target_field)
    if not candidates:
        return {"error": f"No suitable representation candidates found for layer '{layer_name}'."}

    best = candidates[0]
    alternatives = []
    action_chips = []

    for c in candidates:
        act_id = ChatActionRegistry.register(
            kind="apply_style",
            label=f"Apply {c.label}",
            payload={"layer_name": layer_name, "representation_id": c.id, "target_field": c.target_field},
            safety="immediate",
        )
        action_chips.append({
            "id": act_id,
            "label": f"🎨 {c.label}",
            "url": f"cartogen://action/{act_id}",
        })
        if c != best:
            alternatives.append({
                "id": c.id,
                "label": c.label,
                "score": c.score.total_score if c.score else 0.0,
                "rationale": c.rationale,
            })

    return {
        "success": True,
        "layer_name": layer_name,
        "recommended": {
            "id": best.id,
            "label": best.label,
            "score": best.score.total_score if best.score else 0.0,
            "rationale": best.rationale,
            "warnings": best.warnings,
            "target_field": best.target_field,
        },
        "alternatives": alternatives[:3],
        "action_chips": action_chips[:3],
    }


@register_tool(
    "apply_recommended_representation",
    "Apply a recommended representation candidate (e.g. 'point_cluster', 'point_displacement', 'point_heatmap', 'polygon_choropleth_rate', 'polygon_proportional_centroid') to a layer.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "representation_id": {"type": "string", "description": "Candidate representation id to apply, e.g. 'point_cluster', 'point_heatmap', 'polygon_choropleth_rate'."},
            "target_field": {"type": "string", "description": "Optional attribute field if the representation requires one."},
        },
        "required": ["layer_name", "representation_id"],
    },
)
def apply_recommended_representation(layer_name: str, representation_id: str, target_field: Optional[str] = None) -> Dict[str, Any]:
    layer = _get_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found."}

    candidate = RepresentationCandidate(
        id=representation_id,
        label=representation_id,
        renderer_type="",
        target_field=target_field,
    )
    return apply_representation(layer, candidate)


@register_tool(
    "explain_current_representation",
    "Inspect a layer's active renderer and explain whether it fits the data distribution and geometry, flagging potential cartographic issues (such as raw count choropleth distortion or dense point crowding).",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
        },
        "required": ["layer_name"],
    },
)
def explain_current_representation(layer_name: str) -> Dict[str, Any]:
    layer = _get_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found."}

    prof = profile_layer(layer)
    renderer_name = type(layer.renderer()).__name__ if hasattr(layer, "renderer") and layer.renderer() else "Unknown"

    issues = []
    if prof.geometry == "polygon" and "Graduated" in renderer_name:
        for fn, fp in prof.fields.items():
            if fp.semantic_type == "positive_quantity":
                issues.append(
                    f"Warning: Layer may be displaying raw count total '{fn}' as a choropleth. "
                    "Different polygon areas mislead visual perception of total quantity. "
                    "Consider proportional symbols over centroids or normalizing by area/population."
                )
                break

    if prof.geometry == "point" and prof.spatial_density in ("high", "extreme") and "Single" in renderer_name:
        issues.append(
            f"Point layer has {prof.feature_count} features with high spatial overlap ({prof.overlap_ratio * 100:.0f}%). "
            "Individual markers obscure each other. Recommend 'point_cluster' or 'point_heatmap'."
        )

    return {
        "success": True,
        "layer_name": layer_name,
        "current_renderer": renderer_name,
        "feature_count": prof.feature_count,
        "spatial_density": prof.spatial_density,
        "cartographic_evaluation": "Suboptimal" if issues else "Satisfactory",
        "issues_and_recommendations": issues,
    }
