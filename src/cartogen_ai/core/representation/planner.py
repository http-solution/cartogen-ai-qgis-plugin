# -*- coding: utf-8 -*-
"""
Representation Planner Engine for Cartogen AI.

Generates and scores candidate map representations based on layer semantics,
spatial density, statistical honesty, and user analytical intent.
"""

from typing import Any, Dict, List, Optional
from .models import (
    LayerSemanticProfile,
    FieldSemanticProfile,
    RepresentationCandidate,
    CandidateScore,
)


def _infer_intent_keywords(user_intent: Optional[str]) -> str:
    """Classifies user intent into a core cartographic question."""
    if not user_intent:
        return "general"
    intent = user_intent.lower()
    if any(k in intent for k in ("concentrat", "density", "cluster", "hotspot", "crowd", "heat")):
        return "density"
    if any(k in intent for k in ("type", "categor", "class", "status", "which kind")):
        return "category"
    if any(k in intent for k in ("largest", "size", "capacity", "magnitude", "highest volume", "scale")):
        return "magnitude"
    if any(k in intent for k in ("rate", "percent", "ratio", "proportion", "prevalence")):
        return "rate"
    if any(k in intent for k in ("where are", "location", "distribution", "overview")):
        return "location"
    if any(k in intent for k in ("flow", "movement", "direction", "traffic")):
        return "flow"
    if any(k in intent for k in ("terrain", "elevation", "relief", "topograph")):
        return "terrain"
    return "general"


def plan_representations(
    profile: LayerSemanticProfile,
    user_intent: Optional[str] = None,
    target_field: Optional[str] = None,
) -> List[RepresentationCandidate]:
    """Evaluates the LayerSemanticProfile and returns a sorted list of scored candidates."""
    intent_type = _infer_intent_keywords(user_intent)
    candidates: List[RepresentationCandidate] = []

    # -----------------------------------------------------------------------
    # 1. Point Geometries
    # -----------------------------------------------------------------------
    if profile.geometry == "point":
        # Candidate A: Point Cluster Renderer
        cluster_score = CandidateScore(
            total_score=0.0,
            semantic_fit=0.85 if intent_type in ("density", "location", "general") else 0.60,
            geometry_fit=1.0,
            scale_fit=0.90,
            density_fit=0.95 if profile.spatial_density in ("high", "extreme") else 0.40,
            statistical_honesty=0.90,
            readability=0.95,
            accessibility=0.90,
            clutter_risk=0.05,
            misleading_risk=0.05,
        )
        total_a = (
            cluster_score.semantic_fit * 0.25
            + cluster_score.geometry_fit * 0.15
            + cluster_score.density_fit * 0.25
            + cluster_score.readability * 0.20
            + cluster_score.statistical_honesty * 0.15
            - cluster_score.clutter_risk
        )
        cluster_score.total_score = round(max(0.0, min(1.0, total_a)), 3)
        candidates.append(
            RepresentationCandidate(
                id="point_cluster",
                label="Point Clusters (Scale-Aware)",
                renderer_type="cluster",
                rationale="Aggregates co-located points into cluster symbols with dynamic counts, eliminating screen clutter.",
                score=cluster_score,
            )
        )

        # Candidate B: Visual Heatmap / KDE
        heatmap_score = CandidateScore(
            total_score=0.0,
            semantic_fit=0.98 if intent_type == "density" else 0.65,
            geometry_fit=0.95,
            scale_fit=0.85,
            density_fit=0.95 if profile.spatial_density in ("high", "extreme") else 0.30,
            statistical_honesty=0.85,
            readability=0.85,
            accessibility=0.80,
            clutter_risk=0.0,
            misleading_risk=0.10,
        )
        total_b = (
            heatmap_score.semantic_fit * 0.30
            + heatmap_score.geometry_fit * 0.15
            + heatmap_score.density_fit * 0.25
            + heatmap_score.readability * 0.15
            + heatmap_score.statistical_honesty * 0.15
        )
        heatmap_score.total_score = round(max(0.0, min(1.0, total_b)), 3)
        candidates.append(
            RepresentationCandidate(
                id="point_heatmap",
                label="Continuous Density Heatmap",
                renderer_type="heatmap",
                rationale="Renders a smooth perceptual gradient (Viridis) highlighting hotspots of feature concentration.",
                score=heatmap_score,
            )
        )

        # Candidate C: Proportional Symbols (if numeric field present)
        qty_field = target_field
        if not qty_field:
            for fn, fp in profile.fields.items():
                if fp.semantic_type in ("positive_quantity", "rate_percentage") and fp.is_numeric:
                    qty_field = fn
                    break

        if qty_field and qty_field in profile.fields:
            field_prof = profile.fields[qty_field]
            prop_score = CandidateScore(
                total_score=0.0,
                semantic_fit=0.95 if intent_type == "magnitude" else 0.70,
                geometry_fit=0.95,
                scale_fit=0.80,
                density_fit=0.60 if profile.spatial_density in ("high", "extreme") else 0.90,
                statistical_honesty=0.95,
                readability=0.70 if profile.spatial_density == "extreme" else 0.90,
                accessibility=0.90,
                clutter_risk=0.25 if profile.spatial_density in ("high", "extreme") else 0.05,
                misleading_risk=0.0,
            )
            total_c = (
                prop_score.semantic_fit * 0.30
                + prop_score.geometry_fit * 0.15
                + prop_score.statistical_honesty * 0.25
                + prop_score.readability * 0.15
                + prop_score.density_fit * 0.15
                - prop_score.clutter_risk
            )
            prop_score.total_score = round(max(0.0, min(1.0, total_c)), 3)
            candidates.append(
                RepresentationCandidate(
                    id="point_proportional",
                    label=f"Proportional Circles by '{qty_field}'",
                    renderer_type="proportional",
                    target_field=qty_field,
                    rationale=f"Scales symbol radius proportional to '{qty_field}' using Flannery perceptual compensation.",
                    score=prop_score,
                )
            )

        # Candidate D: Categorized Nominal Icons
        cat_field = target_field
        if not cat_field:
            for fn, fp in profile.fields.items():
                if fp.semantic_type in ("nominal", "ordered_status") and 2 <= fp.distinct_count <= 12:
                    cat_field = fn
                    break

        if cat_field and cat_field in profile.fields:
            cat_prof = profile.fields[cat_field]
            cat_score = CandidateScore(
                total_score=0.0,
                semantic_fit=0.98 if intent_type == "category" else 0.75,
                geometry_fit=0.95,
                scale_fit=0.85,
                density_fit=0.55 if profile.spatial_density == "extreme" else 0.85,
                statistical_honesty=0.95,
                readability=0.85,
                accessibility=0.85,
                clutter_risk=0.15 if profile.spatial_density == "extreme" else 0.05,
                misleading_risk=0.0,
            )
            total_d = (
                cat_score.semantic_fit * 0.35
                + cat_score.geometry_fit * 0.15
                + cat_score.statistical_honesty * 0.20
                + cat_score.readability * 0.15
                + cat_score.density_fit * 0.15
                - cat_score.clutter_risk
            )
            cat_score.total_score = round(max(0.0, min(1.0, total_d)), 3)
            candidates.append(
                RepresentationCandidate(
                    id="point_categorized",
                    label=f"Categorized Symbols by '{cat_field}'",
                    renderer_type="categorized",
                    target_field=cat_field,
                    rationale=f"Applies discrete color/icon styling distinguishing {cat_prof.distinct_count} categories of '{cat_field}'.",
                    score=cat_score,
                )
            )

    # -----------------------------------------------------------------------
    # 2. Polygon Geometries
    # -----------------------------------------------------------------------
    elif profile.geometry == "polygon":
        # Candidate A: Normalized Choropleth (Rate/Percentage)
        rate_field = target_field
        if not rate_field:
            for fn, fp in profile.fields.items():
                if fp.semantic_type == "rate_percentage" and fp.is_numeric:
                    rate_field = fn
                    break

        if rate_field and rate_field in profile.fields:
            field_profile = profile.fields[rate_field]
            is_raw_count = field_profile.semantic_type == "positive_quantity"
            stat_honesty = 0.40 if is_raw_count else 0.98
            misleading_risk = 0.45 if is_raw_count else 0.0
            sem_fit = 0.50 if is_raw_count else (0.98 if intent_type == "rate" else 0.80)

            rate_score = CandidateScore(
                total_score=0.0,
                semantic_fit=sem_fit,
                geometry_fit=0.95,
                scale_fit=0.90,
                density_fit=0.90,
                statistical_honesty=stat_honesty,
                readability=0.90,
                accessibility=0.90,
                clutter_risk=0.05,
                misleading_risk=misleading_risk,
            )
            total_poly_a = (
                rate_score.semantic_fit * 0.30
                + rate_score.statistical_honesty * 0.30
                + rate_score.geometry_fit * 0.15
                + rate_score.readability * 0.15
                + rate_score.density_fit * 0.10
                - rate_score.misleading_risk
            )
            rate_score.total_score = round(max(0.0, min(1.0, total_poly_a)), 3)

            warnings = []
            if is_raw_count:
                rationale = f"Warning: '{rate_field}' is a raw count total. Using choropleth coloring on varying polygon areas misrepresents true concentration."
                warnings.append("Misleading choropleth: raw counts mapped directly to varying polygon areas distort spatial density. Consider normalizing by area/population or using proportional symbols.")
            else:
                rationale = f"'{rate_field}' is a normalized rate/index; graduated sequential choropleth is statistically sound and honest."

            candidates.append(
                RepresentationCandidate(
                    id="polygon_choropleth_rate",
                    label=f"Graduated Choropleth by '{rate_field}'",
                    renderer_type="graduated",
                    target_field=rate_field,
                    rationale=rationale,
                    warnings=warnings,
                    score=rate_score,
                )
            )

        # Candidate B: Raw Count on Unequal Areas -> Proportional Circles over Centroids!
        count_field = None
        if target_field and target_field in profile.fields:
            if profile.fields[target_field].semantic_type == "positive_quantity":
                count_field = target_field
        if not count_field:
            for fn, fp in profile.fields.items():
                if fp.semantic_type == "positive_quantity" and fp.is_numeric:
                    count_field = fn
                    break

        if count_field and count_field in profile.fields:
            prop_poly_score = CandidateScore(
                total_score=0.0,
                semantic_fit=0.95 if intent_type == "magnitude" else 0.85,
                geometry_fit=0.90,
                scale_fit=0.90,
                density_fit=0.85,
                statistical_honesty=0.98,  # Does NOT distort by polygon area!
                readability=0.90,
                accessibility=0.90,
                clutter_risk=0.05,
                misleading_risk=0.0,
            )
            total_poly_b = (
                prop_poly_score.semantic_fit * 0.25
                + prop_poly_score.statistical_honesty * 0.35
                + prop_poly_score.geometry_fit * 0.15
                + prop_poly_score.readability * 0.15
                + prop_poly_score.density_fit * 0.10
            )
            prop_poly_score.total_score = round(max(0.0, min(1.0, total_poly_b)), 3)
            candidates.append(
                RepresentationCandidate(
                    id="polygon_proportional_centroid",
                    label=f"Proportional Circles by '{count_field}' (Statistically Honest)",
                    renderer_type="proportional",
                    target_field=count_field,
                    rationale=f"'{count_field}' is a raw count total. Using proportional symbols over polygon centroids avoids deceptive area-bias distortion.",
                    warnings=[f"Avoid coloring raw counts directly on polygons of varying size."],
                    score=prop_poly_score,
                )
            )

        # Candidate C: Semi-Transparent Operational Overlay (for buffers/hazards)
        overlay_score = CandidateScore(
            total_score=0.75,
            semantic_fit=0.80,
            geometry_fit=0.95,
            scale_fit=0.90,
            density_fit=0.90,
            statistical_honesty=0.90,
            readability=0.95,
            accessibility=0.90,
            clutter_risk=0.05,
            misleading_risk=0.0,
        )
        candidates.append(
            RepresentationCandidate(
                id="polygon_translucent_overlay",
                label="Semi-Transparent Overlay (20% fill, 100% stroke)",
                renderer_type="single",
                rationale="Applies a faint 20% interior tint with a crisp boundary outline, keeping basemap and features beneath 100% visible.",
                score=overlay_score,
            )
        )

        # Candidate D: Hollow Boundary Outline
        hollow_score = CandidateScore(
            total_score=0.70,
            semantic_fit=0.75,
            geometry_fit=0.95,
            scale_fit=0.90,
            density_fit=0.90,
            statistical_honesty=0.95,
            readability=0.95,
            accessibility=0.90,
            clutter_risk=0.0,
            misleading_risk=0.0,
        )
        candidates.append(
            RepresentationCandidate(
                id="polygon_hollow_boundary",
                label="Hollow Boundary Outline (No interior fill)",
                renderer_type="single",
                rationale="Renders a crisp administrative border with no fill, completely avoiding occlusion of underlying data.",
                score=hollow_score,
            )
        )

    # -----------------------------------------------------------------------
    # 3. Continuous Raster Surfaces
    # -----------------------------------------------------------------------
    elif profile.geometry == "raster":
        if profile.raster_data_type == "elevation_dem":
            relief_score = CandidateScore(
                total_score=0.95,
                semantic_fit=0.98,
                geometry_fit=1.0,
                scale_fit=0.95,
                density_fit=1.0,
                statistical_honesty=0.95,
                readability=0.95,
                accessibility=0.90,
                clutter_risk=0.0,
                misleading_risk=0.0,
            )
            candidates.append(
                RepresentationCandidate(
                    id="raster_shaded_relief",
                    label="Shaded Relief Composite (Multiply Blend)",
                    renderer_type="relief",
                    rationale="Combines hypsometric elevation color tints with grayscale hillshade using Multiply blending for clear 3D terrain perception.",
                    score=relief_score,
                )
            )
        else:
            pseudo_score = CandidateScore(
                total_score=0.88,
                semantic_fit=0.90,
                geometry_fit=1.0,
                scale_fit=0.90,
                density_fit=1.0,
                statistical_honesty=0.90,
                readability=0.90,
                accessibility=0.85,
                clutter_risk=0.0,
                misleading_risk=0.05,
            )
            candidates.append(
                RepresentationCandidate(
                    id="raster_pseudocolor",
                    label="Singleband Pseudocolor (Perceptually Uniform)",
                    renderer_type="graduated",
                    rationale="Applies a perceptually uniform color ramp (Viridis/Batlow) avoiding false visual boundaries.",
                    score=pseudo_score,
                )
            )

    # Sort descending by total score
    candidates.sort(key=lambda c: c.score.total_score if c.score else 0.0, reverse=True)
    return candidates
