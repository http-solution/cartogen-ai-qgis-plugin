"""analyze_hotspots_gi_star (PLAN-023 R2-2): where are the statistically significant hot spots and cold spots of a numeric field? Getis-Ord Gi* with an optional Benjamini-Hochberg false-discovery correction.

The statistic, the correction and the classes are the pure, hand-checked steps of _spatial_stats.py; the layer reading and the neighbour rules are shared with calculate_spatial_autocorrelation (spatial_stats_tool.py). The result is a NEW layer; the input layer is never changed. Unlike hotspot_analysis (a density surface of where points are
concentrated), this tests whether the VALUES of a field are unusually high or low among neighbours, and says how sure it is.

Written without a QGIS install; tests/test_hotspot_tool_live.py is its first execution in CI."""
from . import _spatial_stats as ss
from . import _spatial_weights as sw
from ._layer_checks import require_valid_layer
from .registry import register_tool
from .spatial_stats_tool import NOTE, WEIGHTS, build_neighbours, read_features

try:
    from qgis.core import QgsFeature, QgsProject, QgsVectorLayer, QgsWkbTypes
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

FDR_NOTE = ("With the false-discovery correction on (the default) the classes use the corrected p-values, which keeps the expected share of false hot and cold spots at or below alpha. Without it, about 1 feature in 20 "
            "would look 'significant at 95%' by chance alone.")
NORMAL_NOTE = "The p-values come from the normal distribution of the Gi* z-score; for strongly skewed values (counts with a few huge ones) they are less reliable, so check a surprising result with Local Moran (permutation)."


def _find_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


@register_tool(
    "analyze_hotspots_gi_star",
    "Find statistically significant HOT SPOTS (clusters of high values) and COLD SPOTS (clusters of low values) of a numeric field with Getis-Ord Gi*: a z-score and p-value per feature, an optional false-discovery "
    "(Benjamini-Hochberg) correction, and a class 'Hot spot 99%' / 'Hot spot 95%' / 'Hot spot 90%' / 'Cold spot ...' / 'Not significant', written to a NEW layer (the input is never changed). This is a significance TEST on "
    "the field's values, not a density map: for a density surface of where points are concentrated use hotspot_analysis. weights: 'queen' or 'rook' (polygon layers), 'knn' (pass k) or 'distance' (a band in layer units, "
    "projected CRS only, pass distance); each feature counts itself as part of its own neighbourhood. Needs a number on every feature (it refuses and says how many are missing); at most 5,000 features. "
    "A hot spot means high values near high values, not a cause: do not describe it as an outbreak or a threat without other evidence.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"},
        "field": {"type": "string", "description": "A numeric field (a count, a rate, an index)."},
        "weights": {"type": "string", "enum": list(WEIGHTS), "description": "queen (default), rook, knn or distance."},
        "k": {"type": "integer", "description": "For weights='knn': how many nearest neighbours each feature counts besides itself."},
        "distance": {"type": "number", "description": "For weights='distance': the band in the layer's units (projected CRS)."},
        "fdr": {"type": "boolean", "description": "Apply the Benjamini-Hochberg false-discovery correction (default true)."},
        "alpha": {"type": "number", "description": "The weakest significance reported: 0.05 (default) reports 99% and 95% spots, 0.10 adds 90%, 0.01 reports only 99%."},
        "output_layer_name": {"type": "string", "description": "Name of the new layer (default '<layer>_gi_star')."},
    }, "required": ["layer_name", "field"]},
    keywords=["hot spot test", "hotspot test", "getis ord", "getis-ord", "gi star", "gi*", "statistically significant hot spots", "significant hot spots", "significant hotspots", "cold spots",
              "where are the significant clusters", "hot and cold spots of"],
)
def analyze_hotspots_gi_star(layer_name, field, weights="queen", k=None, distance=None, fdr=True, alpha=0.05, output_layer_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    weights = str(weights or "queen").strip().lower()
    if weights not in WEIGHTS:
        return {"error": f"Unknown weights '{weights}'. Choose one of: {', '.join(WEIGHTS)}."}
    layer = _find_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not isinstance(layer, QgsVectorLayer):
        return {"error": f"'{layer_name}' is not a vector layer."}
    index = layer.fields().indexOf(field)
    if index < 0:
        return {"error": f"Field '{field}' not found in '{layer_name}'. Fields: {', '.join(f.name() for f in layer.fields())}."}
    if not layer.fields().at(index).isNumeric():
        return {"error": f"Field '{field}' is not numeric."}
    if weights in ("queen", "rook") and QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.GeometryType.PolygonGeometry:
        return {"error": f"'{weights}' neighbours come from shared polygon boundaries, and '{layer_name}' is not a polygon layer. Use weights='knn' or 'distance'."}
    if weights == "knn" and k is None:
        return {"error": "weights='knn' needs k (how many nearest neighbours to count, for example 8)."}
    if weights == "distance" and distance is None:
        return {"error": "weights='distance' needs distance (the band, in the layer's units)."}
    try:
        ids, values, points, rings, problem = read_features(layer, field, weights in ("queen", "rook"))
        if problem:
            return {"error": problem}
        neighbours, problem = build_neighbours(layer, weights, k, distance, points, rings)
        if problem:
            return {"error": problem}
        result = ss.hotspots(values, neighbours, bool(fdr), alpha)
    except ValueError as e:
        return {"error": f"analyze_hotspots_gi_star: {e}"}
    except Exception as e:
        return {"error": f"The hot-spot test could not be computed: {e}"}
    name = (output_layer_name or "").strip() or f"{layer_name}_gi_star"
    written = _write_layer(layer, ids, values, result, name)
    if isinstance(written, str):
        return {"error": written}
    hot = sum(v for c, v in result["counts"].items() if c.startswith("Hot"))
    cold = sum(v for c, v in result["counts"].items() if c.startswith("Cold"))
    out = {"success": True, "layer_name": layer_name, "field": field, "output_layer": written.name(), "weights": weights, "features": len(ids), "fdr": result["fdr"], "alpha": alpha, "classes": result["counts"],
           "hot_spots": hot, "cold_spots": cold, "mean_neighbours": round(sw.mean_neighbours(neighbours), 2), "islands": len(sw.islands(neighbours)),
           "summary": f"{hot} hot spot(s) and {cold} cold spot(s) among {result['tested']} tested features" + (" (false-discovery corrected)" if result["fdr"] else " (NOT corrected for the number of tests)") + ".",
           "notes": [FDR_NOTE if result["fdr"] else "No false-discovery correction was applied: expect some false hot and cold spots by chance.", NORMAL_NOTE, NOTE]}
    if all(r["z"] == 0 for r in result["features"] if r["z"] is not None):
        out["no_variation"] = "Every feature has the same value, so there is nothing to find: no hot or cold spots."
    if out["islands"]:
        out["island_warning"] = (f"{out['islands']} feature(s) have no neighbour under '{weights}' and were not tested. If the polygons should touch, their boundaries do not share exact corner points: check the geometry, or use knn.")
    return out


def _write_layer(layer, ids, values, result, name):
    """A new memory layer with the source geometry and gi_z, gi_p, gi_q, gi_class. Returns the layer, or a refusal string."""
    out = QgsVectorLayer(f"{QgsWkbTypes.displayString(layer.wkbType())}?crs={layer.crs().authid()}&field=src_id:integer&field=value:double&field=gi_z:double&field=gi_p:double&field=gi_q:double"
                         "&field=gi_class:string&field=neighbours:integer", name, "memory")
    try:
        require_valid_layer(out)
    except ValueError as e:
        return str(e)
    by_id = {f.id(): f for f in layer.getFeatures()}

    def rounded(value, places):
        return None if value is None else round(value, places)
    feats = []
    for fid, value, row in zip(ids, values, result["features"], strict=True):
        f = QgsFeature(out.fields())
        f.setGeometry(by_id[fid].geometry())
        f.setAttributes([int(fid), value, rounded(row["z"], 4), rounded(row["p_value"], 6), rounded(row["p_adjusted"], 6), row["class"], row["neighbours"]])
        feats.append(f)
    out.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(out)
    return out
