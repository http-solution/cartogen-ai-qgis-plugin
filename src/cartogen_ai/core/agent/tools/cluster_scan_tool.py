"""detect_spatial_clusters (PLAN-023 R2-3): is there a group of nearby areas with more cases than their population explains? Kulldorff's circular scan statistic (Poisson model) with a Monte Carlo p-value.

The scan, its hand-checked log likelihood ratio and the Monte Carlo are the pure steps of _kulldorff.py; this module reads the layer (each area is its centroid with a case count and a population), refuses what the
method cannot handle, and writes the circles to a NEW layer. It never edits the input layer. Areas are treated as points at their centroids, so a cluster's circle is where the centroids are, not a boundary.

Written without a QGIS install; tests/test_cluster_scan_tool_live.py is its first execution in CI."""
import math

from . import _kulldorff as kd
from ._layer_checks import require_valid_layer
from .registry import register_tool

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

NOTE = ("A scan finds where cases exceed what population alone would give, and how often chance alone would do as well. It does not say why, it does not say anyone caused or was exposed to anything, and it says nothing "
        "about individuals living in the circle. Areas are treated as points at their centres, so the circle shows where the centres are, not a boundary. Cases must be counts of the same period and definition in every area.")
LIMIT_NOTE = "Large circles are reported as found; a cluster is never allowed to hold more than max_pop_fraction of the whole population, so an area that is itself half of the population cannot be a cluster."


def _find_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _read(layer, case_field, population_field):
    """(ids, cases, populations, points, problem). Refuses, with the counts, any feature that lacks a geometry, a whole-number case count or a positive population."""
    ids, cases, pops, points = [], [], [], []
    bad_geometry = bad_cases = bad_pop = 0
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        c, p = feature[case_field], feature[population_field]
        if geometry is None or geometry.isNull() or geometry.isEmpty():
            bad_geometry += 1
            continue
        if c is None or isinstance(c, bool) or not isinstance(c, (int, float)) or c != c or c < 0 or c != int(c):
            bad_cases += 1
            continue
        if p is None or isinstance(p, bool) or not isinstance(p, (int, float)) or p != p or p <= 0:
            bad_pop += 1
            continue
        if len(ids) >= kd.MAX_AREAS:
            return None, None, None, None, f"The layer has more than {kd.MAX_AREAS:,} areas; the scan compares every area with every other, so it stops there. Aggregate to fewer, larger areas first."
        centre = geometry.centroid().asPoint()
        ids.append(feature.id())
        cases.append(int(c))
        pops.append(float(p))
        points.append((centre.x(), centre.y()))
    problems = []
    if bad_geometry:
        problems.append(f"{bad_geometry} feature(s) have no geometry")
    if bad_cases:
        problems.append(f"{bad_cases} feature(s) have no whole-number case count in '{case_field}'")
    if bad_pop:
        problems.append(f"{bad_pop} feature(s) have no population above zero in '{population_field}'")
    if problems:
        return None, None, None, None, "; ".join(problems) + ". Fix or remove them first: leaving areas out would change who is near whom, so this tool does not guess."
    return ids, cases, pops, points, None


@register_tool(
    "detect_spatial_clusters",
    "Find the most likely CLUSTER of excess cases with Kulldorff's circular spatial scan statistic (Poisson model): it tries circles of every size around every area, scores each by how many more cases it holds than "
    "its population would give, and reports the best circle with its centre, radius, cases, expected cases, relative risk and a Monte Carlo p-value (how often chance alone does as well), plus further non-overlapping "
    "circles that are also significant. Writes the circles to a NEW layer (the input is never changed). Needs a whole-number case field and a population field on every area, a projected CRS, and numpy (ships with QGIS). "
    "Use it for 'is this a real cluster', 'where is the most likely cluster', outbreak or incident clustering; it shows where cases exceed population, never why. max_pop_fraction (default 0.5, the largest allowed) "
    "caps a cluster's share of the population. At most 1,500 areas.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"},
        "case_field": {"type": "string", "description": "Whole-number case counts per area."},
        "population_field": {"type": "string", "description": "Population at risk per area (above zero)."},
        "model": {"type": "string", "enum": ["poisson"], "description": "Only 'poisson' is built."},
        "max_pop_fraction": {"type": "number", "description": "Largest share of the population a cluster may hold, 0.01 to 0.5 (default 0.5)."},
        "max_radius": {"type": "number", "description": "Largest cluster radius in layer units (default: no limit besides the population cap)."},
        "monte_carlo": {"type": "integer", "description": "Random re-draws for the p-value, 99 to 9999 (default 999)."},
        "seed": {"type": "integer", "description": "Random seed (default 1); the same seed gives the same numbers on the same numpy version."},
        "max_clusters": {"type": "integer", "description": "Most clusters to report, 1 to 20 (default 5)."},
        "alpha": {"type": "number", "description": "Significance level for secondary clusters (default 0.05)."},
        "output_layer_name": {"type": "string", "description": "Name of the new layer (default '<layer>_scan_clusters')."},
    }, "required": ["layer_name", "case_field", "population_field"]},
    keywords=["spatial scan", "scan statistic", "kulldorff", "satscan", "most likely cluster", "is this a real cluster", "cluster of cases", "disease cluster", "outbreak cluster", "cluster detection",
              "clustering of incidents", "excess cases", "circular scan"],
)
def detect_spatial_clusters(layer_name, case_field, population_field, model="poisson", max_pop_fraction=0.5, max_radius=None, monte_carlo=999, seed=1, max_clusters=5, alpha=0.05, output_layer_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if str(model or "poisson").strip().lower() != "poisson":
        return {"error": f"Model '{model}' is not built; only 'poisson' (cases against population) is."}
    if not kd.HAVE_NUMPY:
        return {"error": "The cluster scan needs numpy, which ships with QGIS but was not found in this QGIS Python."}
    layer = _find_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not isinstance(layer, QgsVectorLayer):
        return {"error": f"'{layer_name}' is not a vector layer."}
    for label, name in (("case", case_field), ("population", population_field)):
        index = layer.fields().indexOf(name)
        if index < 0:
            return {"error": f"The {label} field '{name}' was not found in '{layer_name}'. Fields: {', '.join(f.name() for f in layer.fields())}."}
        if not layer.fields().at(index).isNumeric():
            return {"error": f"The {label} field '{name}' is not numeric."}
    if layer.crs().isGeographic():
        return {"error": "The scan measures distances between centres, which would be in degrees on this layer's CRS. Reproject the layer to a projected CRS first."}
    ids, cases, pops, points, problem = _read(layer, case_field, population_field)
    if problem:
        return {"error": problem}
    try:
        result = kd.scan(cases, pops, points, max_pop_fraction, max_radius, monte_carlo, seed, max_clusters, alpha)
    except ValueError as e:
        return {"error": f"detect_spatial_clusters: {e}"}
    except Exception as e:
        return {"error": f"The cluster scan could not be computed: {e}"}
    name = (output_layer_name or "").strip() or f"{layer_name}_scan_clusters"
    written = _write_layer(layer, ids, points, result, name) if result["clusters"] else None      # no circle, no empty layer cluttering the project
    if isinstance(written, str):
        return {"error": written}
    clusters = [_describe(c, ids, alpha) for c in result["clusters"]]
    best = clusters[0] if clusters else None
    if best is None:                                    # every circle holds at most what its population explains: nothing to rank
        summary = "No cluster: no circle holds more cases than its population explains."
    elif best["significant"]:
        summary = (f"Most likely cluster: {best['areas']} area(s) around feature {best['centre_id']}, {best['cases']} cases against {best['expected']} expected "
                   f"(relative risk {best['relative_risk']}), p = {best['p_value']}.")
    else:
        summary = (f"No cluster stands out: the best circle ({best['areas']} area(s) around feature {best['centre_id']}, {best['cases']} cases against {best['expected']} expected) "
                   f"has p = {best['p_value']}, which chance alone often matches.")
    return {"success": True, "layer_name": layer_name, "output_layer": written.name() if written is not None else None, "areas": len(ids), "total_cases": result["total_cases"], "monte_carlo": monte_carlo, "seed": seed,
            "alpha": alpha, "max_pop_fraction": max_pop_fraction, "clusters": clusters, "significant_clusters": sum(1 for c in clusters if c["significant"]), "summary": summary,
            "notes": [NOTE, LIMIT_NOTE]}


def _describe(cluster, ids, alpha):
    rr = cluster["relative_risk"]
    return {"centre_id": ids[cluster["centre"]], "areas": len(cluster["members"]), "member_ids": [ids[m] for m in cluster["members"][:50]], "members_truncated": len(cluster["members"]) > 50,
            "radius": round(cluster["radius"], 3), "cases": cluster["cases"], "expected": round(cluster["expected"], 2), "relative_risk": None if rr is None else round(rr, 3),
            "llr": round(cluster["llr"], 3), "p_value": round(cluster["p_value"], 4), "significant": cluster["p_value"] <= alpha}


def _write_layer(layer, ids, points, result, name):
    """A new memory polygon layer with one circle per reported cluster. Returns the layer, or a refusal string."""
    out = QgsVectorLayer(f"Polygon?crs={layer.crs().authid()}&field=cluster:integer&field=centre_id:integer&field=areas:integer&field=radius:double&field=cases:integer&field=expected:double"
                         "&field=rel_risk:double&field=llr:double&field=p_value:double&field=significant:string", name, "memory")
    try:
        require_valid_layer(out)
    except ValueError as e:
        return str(e)
    feats = []
    for rank, c in enumerate(result["clusters"], start=1):
        x, y = points[c["centre"]]
        draw = c["radius"]
        if draw <= 0:                                   # a one-area cluster has radius 0; draw half the distance to the nearest other centre so it is visible
            others = [math.hypot(x - px, y - py) for j, (px, py) in enumerate(points) if j != c["centre"]]
            draw = (min(others) / 2) if others and min(others) > 0 else 1.0
        f = QgsFeature(out.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)).buffer(draw, 48))
        rr = c["relative_risk"]
        f.setAttributes([rank, int(ids[c["centre"]]), len(c["members"]), round(c["radius"], 3), c["cases"], round(c["expected"], 3), None if rr is None else round(rr, 4),
                         round(c["llr"], 4), round(c["p_value"], 5), "yes" if c["p_value"] <= result["alpha"] else "no"])
        feats.append(f)
    out.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(out)
    return out
