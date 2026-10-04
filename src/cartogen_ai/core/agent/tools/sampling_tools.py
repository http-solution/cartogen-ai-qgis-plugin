# -*- coding: utf-8 -*-
"""
Survey sampling frame design for needs assessments (H3, docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md).

Given strata (administrative units, camps vs host communities, ...), works out how many units to survey in each stratum for a
chosen confidence level and margin of error, then draws the sample: from a layer of candidate units (households, buildings,
settlements) if one is supplied, otherwise as random points inside each stratum's polygon.

The statistics are the standard single-proportion formula n0 = z^2 p (1-p) / e^2, multiplied by the design effect, reduced by the
finite-population correction n = n0 / (1 + (n0 - 1) / N) when the stratum size N is known, then inflated for non-response. Every
assumption (confidence, margin of error, expected proportion p, design effect, non-response, seed) is a visible argument and is
echoed in the result. The defaults p = 0.5 (the most conservative value) and design effect = 1.0 are NOT a methodological
recommendation: 1.0 is only right for simple random sampling, and a cluster design needs a design effect the survey designer
supplies. This tool does not choose the survey design for you, and a sample drawn here is only as good as the frame it was drawn from.

The sample-size and draw logic is pure and unit tested offline; the layer work needs QGIS (tests/test_sampling_tools_live.py,
written without a local QGIS).
"""
import math
import random
import statistics

from .registry import register_tool

try:
    from qgis.core import (QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsPointXY,
                           QgsProject, QgsSpatialIndex, QgsVectorLayer)
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

MAX_SAMPLE_PER_STRATUM = 20000
_MAX_DRAW_ATTEMPTS_PER_POINT = 2000


# ---------------------------------------------------------------- pure --

def z_score(confidence):
    """Two-sided normal critical value for a confidence level strictly between 0 and 1. Pure."""
    return statistics.NormalDist().inv_cdf((1.0 + float(confidence)) / 2.0)


def validate_design(confidence, margin_of_error, expected_proportion, design_effect, nonresponse_rate):
    """Error text for an invalid design parameter, else None. Pure."""
    try:
        if not 0.5 <= float(confidence) < 1.0:
            return "confidence must be at least 0.5 and below 1 (e.g. 0.95)."
        if not 0.0 < float(margin_of_error) < 1.0:
            return "margin_of_error must be between 0 and 1 (e.g. 0.05 for plus or minus 5 percentage points)."
        if not 0.0 < float(expected_proportion) < 1.0:
            return "expected_proportion must be between 0 and 1 (0.5 is the most conservative)."
        if float(design_effect) < 1.0:
            return "design_effect must be 1 or more (1 = simple random sampling)."
        if not 0.0 <= float(nonresponse_rate) < 1.0:
            return "nonresponse_rate must be 0 or more and below 1 (e.g. 0.1 for 10%)."
    except (TypeError, ValueError):
        return "confidence, margin_of_error, expected_proportion, design_effect and nonresponse_rate must be numbers."
    return None


def sample_size(population, confidence=0.95, margin_of_error=0.05, expected_proportion=0.5, design_effect=1.0,
                nonresponse_rate=0.0):
    """Units to select in one stratum. Pure.

    population: the stratum size N, or None when unknown (no finite-population correction is applied then). Returns an int,
    never more than N when N is known."""
    z = z_score(confidence)
    p = float(expected_proportion)
    n = (z * z * p * (1.0 - p) / (float(margin_of_error) ** 2)) * float(design_effect)
    if population is not None:
        population = max(0, int(population))
        if population == 0:
            return 0
        n = n / (1.0 + (n - 1.0) / population)
    n = n / (1.0 - float(nonresponse_rate))
    n = int(math.ceil(n - 1e-9))
    if population is not None:
        n = min(n, population)
    return n


def draw_indices(count, n, seed):
    """n distinct indices out of range(count), reproducible for a given seed (all of them when n >= count). Pure."""
    if n >= count:
        return list(range(count))
    return sorted(random.Random(seed).sample(range(count), n))


def stratum_seed(seed, stratum):
    """A per-stratum seed derived from the master seed, so adding a stratum does not reshuffle the others. Pure."""
    return random.Random(f"{seed}|{stratum}").randrange(2 ** 31)


def design_text(confidence, margin_of_error, expected_proportion, design_effect, nonresponse_rate, seed):
    """The assumptions behind a sample size, in one sentence. Pure."""
    return (f"Sample sizes assume a single proportion estimated at {float(confidence) * 100:g}% confidence with a margin of error of "
            f"+/-{float(margin_of_error) * 100:g} percentage points, an expected proportion of {float(expected_proportion):g}, a "
            f"design effect of {float(design_effect):g}, and {float(nonresponse_rate) * 100:g}% non-response; random seed {seed}.")


# ---------------------------------------------------------------- QGIS --

def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _to_crs(geom, src, dst):
    out = QgsGeometry(geom)
    if src != dst:
        out.transform(QgsCoordinateTransform(src, dst, QgsProject.instance()))
    return out


def _random_points_in(geom, count, rng):
    """count random points inside a polygon geometry by rejection sampling inside its bounding box; fewer if it cannot find them."""
    box = geom.boundingBox()
    out, attempts = [], 0
    limit = _MAX_DRAW_ATTEMPTS_PER_POINT * max(1, count)
    while len(out) < count and attempts < limit:
        attempts += 1
        pt = QgsPointXY(rng.uniform(box.xMinimum(), box.xMaximum()), rng.uniform(box.yMinimum(), box.yMaximum()))
        if geom.contains(QgsGeometry.fromPointXY(pt)):
            out.append(pt)
    return out


@register_tool(
    "design_sampling_frame",
    "Design a household/community survey sample (e.g. for a multi-sector needs assessment): works out how many units to survey in "
    "each stratum (admin unit, camp, host community...) for a chosen confidence level and margin of error, and draws the sample as "
    "a point layer with a recorded random seed. Draws from a layer of candidate units (households, buildings, settlements) when "
    "units_layer is given, otherwise as random points inside each stratum polygon (area-based, ignores where people live). "
    "The statistical assumptions are arguments and are echoed back: expected_proportion defaults to 0.5 (most conservative) and "
    "design_effect to 1.0, which is correct ONLY for simple random sampling -- for a cluster design the survey designer must "
    "supply the design effect, so ask rather than guess. It does not choose the survey design, and the result is only as good as "
    "the frame it is drawn from.",
    {
        "type": "object",
        "properties": {
            "strata_layer": {"type": "string", "description": "Polygon layer of strata (admin units, camp / host-community areas)."},
            "stratum_field": {"type": "string", "description": "Field naming each stratum. Omit to treat each polygon as its own stratum, named by feature id."},
            "units_layer": {"type": "string", "description": "Optional layer of candidate units to sample from (points, or polygons such as buildings -- their centroids are used)."},
            "population_attribute": {"type": "string", "description": "Optional numeric field on the strata layer with the number of units (e.g. households) in the stratum. If omitted and units_layer is given, the stratum size is the number of candidate units inside it; otherwise no finite-population correction is applied."},
            "confidence": {"type": "number", "description": "Confidence level, e.g. 0.95 (default)."},
            "margin_of_error": {"type": "number", "description": "Margin of error as a proportion, e.g. 0.05 (default) = +/-5 percentage points."},
            "expected_proportion": {"type": "number", "description": "Expected proportion of the indicator, default 0.5 (most conservative)."},
            "design_effect": {"type": "number", "description": "Design effect, default 1.0 (simple random sampling only). Must be supplied by the survey designer for cluster designs."},
            "nonresponse_rate": {"type": "number", "description": "Expected non-response as a proportion, default 0."},
            "seed": {"type": "integer", "description": "Random seed. Omit to generate one; it is returned either way so the draw can be repeated."},
            "output_layer_name": {"type": "string", "description": "Name of the sample point layer. Default 'survey_sample'."},
            "plan_only": {"type": "boolean", "description": "true: only compute sample sizes per stratum, do not draw or create a layer."},
        },
        "required": ["strata_layer"],
    },
)
def design_sampling_frame(strata_layer, stratum_field=None, units_layer=None, population_attribute=None, confidence=0.95,
                          margin_of_error=0.05, expected_proportion=0.5, design_effect=1.0, nonresponse_rate=0.0, seed=None,
                          output_layer_name="survey_sample", plan_only=False):
    problem = validate_design(confidence, margin_of_error, expected_proportion, design_effect, nonresponse_rate)
    if problem:
        return {"error": problem}
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    strata = _layer(strata_layer)
    if strata is None:
        return {"error": f"Layer '{strata_layer}' not found"}
    from qgis.core import QgsWkbTypes
    if not hasattr(strata, "getFeatures") or "Polygon" not in QgsWkbTypes.displayString(strata.wkbType()):
        return {"error": f"'{strata_layer}' must be a polygon layer."}
    names = [f.name() for f in strata.fields()]
    for label, field in (("stratum_field", stratum_field), ("population_attribute", population_attribute)):
        if field is not None and field not in names:
            return {"error": f"{label} '{field}' not found in '{strata_layer}'. Fields: {names}"}
    units = None
    if units_layer:
        units = _layer(units_layer)
        if units is None or not hasattr(units, "getFeatures"):
            return {"error": f"Layer '{units_layer}' not found"}
    if seed is None:
        seed = random.SystemRandom().randrange(2 ** 31)
    seed = int(seed)

    # one record per stratum (polygons sharing a stratum name are merged)
    groups = {}
    for f in strata.getFeatures():
        g = f.geometry()
        if g is None or g.isEmpty():
            continue
        key = str(f[stratum_field]) if stratum_field else str(f.id())
        entry = groups.setdefault(key, {"geoms": [], "population": 0.0, "has_pop": population_attribute is not None})
        entry["geoms"].append(g)
        if population_attribute is not None:
            try:
                entry["population"] += float(f[population_attribute])
            except (TypeError, ValueError):
                entry["has_pop"] = False
    if not groups:
        return {"error": f"'{strata_layer}' has no usable polygons."}
    for entry in groups.values():
        entry["geom"] = QgsGeometry.unaryUnion(entry["geoms"])

    unit_points = {key: [] for key in groups}
    if units is not None:
        index = QgsSpatialIndex()
        key_by_id = {}
        for i, (key, entry) in enumerate(groups.items()):
            feat = QgsFeature(i)
            feat.setGeometry(entry["geom"])
            index.addFeature(feat)
            key_by_id[i] = key
        for uf in units.getFeatures():
            g = uf.geometry()
            if g is None or g.isEmpty():
                continue
            pt = _to_crs(g.centroid(), units.crs(), strata.crs())
            for i in index.intersects(pt.boundingBox()):
                if groups[key_by_id[i]]["geom"].contains(pt):
                    unit_points[key_by_id[i]].append((uf.id(), pt.asPoint()))
                    break

    rows, warnings = [], []
    for key, entry in groups.items():
        if population_attribute is not None and entry["has_pop"]:
            population, basis = int(round(entry["population"])), f"field '{population_attribute}'"
        elif units is not None:
            population, basis = len(unit_points[key]), f"candidate units in '{units_layer}'"
        else:
            population, basis = None, "unknown (no finite-population correction)"
        needed = sample_size(population, confidence, margin_of_error, expected_proportion, design_effect, nonresponse_rate)
        if needed > MAX_SAMPLE_PER_STRATUM:
            return {"error": f"Stratum '{key}' needs {needed} units, above the limit of {MAX_SAMPLE_PER_STRATUM}. "
                             "Loosen the margin of error or confidence."}
        rows.append({"stratum": key, "population": population, "population_basis": basis, "sample_required": needed,
                     "sample_drawn": 0})

    result = {
        "success": True,
        "seed": seed,
        "strata": rows,
        "total_required": sum(r["sample_required"] for r in rows),
        "assumptions": design_text(confidence, margin_of_error, expected_proportion, design_effect, nonresponse_rate, seed),
        "note": ("Sample sizes are for estimating a single proportion; the default design effect of 1 is only valid for simple "
                 "random sampling. Check them against the survey design before fielding."),
    }
    if plan_only:
        result["plan_only"] = True
        return result

    out = QgsVectorLayer(f"Point?crs={strata.crs().authid()}&field=sample_id:string&field=stratum:string&field=source:string",
                         output_layer_name, "memory")
    feats = []
    for row in rows:
        key, needed = row["stratum"], row["sample_required"]
        rng_seed = stratum_seed(seed, key)
        if units is not None:
            candidates = unit_points[key]
            picks = draw_indices(len(candidates), needed, rng_seed)
            chosen = [(f"unit:{candidates[i][0]}", candidates[i][1]) for i in picks]
            source = "candidate unit"
        else:
            pts = _random_points_in(groups[key]["geom"], needed, random.Random(rng_seed))
            chosen = [("random", p) for p in pts]
            source = "random point"
        for n, (_origin, pt) in enumerate(chosen, 1):
            f = QgsFeature(out.fields())
            f.setGeometry(QgsGeometry.fromPointXY(pt))
            f.setAttributes([f"{key}-{n:04d}", key, source])
            feats.append(f)
        row["sample_drawn"] = len(chosen)
        if len(chosen) < needed:
            warnings.append(f"Stratum '{key}': needed {needed} but only {len(chosen)} could be drawn"
                            + (" (fewer candidate units than the sample size)." if units is not None else "."))
    out.dataProvider().addFeatures(feats)
    out.updateExtents()
    QgsProject.instance().addMapLayer(out)
    result["layer_name"] = output_layer_name
    result["total_drawn"] = len(feats)
    if units is None:
        warnings.append("No units_layer was given, so points are random locations inside each stratum, not households: they ignore "
                        "where people actually live and need a field protocol (nearest dwelling) before use.")
    if warnings:
        result["warnings"] = warnings
    return result
