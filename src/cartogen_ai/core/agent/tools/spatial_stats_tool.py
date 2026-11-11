"""calculate_spatial_autocorrelation (PLAN-023 R2-1): is a map more clustered, or more alternating, than a random arrangement of the same values?

The statistics are the pure, hand-checked steps of _spatial_stats.py (global Moran's I and Local Moran's I with permutation tests) over the neighbour lists of _spatial_weights.py; this module reads the layer, builds the
neighbours (queen or rook from polygon outlines, k nearest or a distance band from centroids), runs the statistic and, when asked, writes a NEW layer with the local result. It never edits the input layer.

Written without a QGIS install; tests/test_spatial_stats_tool_live.py is its first execution in CI."""
from . import _spatial_stats as ss
from . import _spatial_weights as sw
from ._layer_checks import require_valid_layer
from .registry import register_tool

try:
    from qgis.core import QgsFeature, QgsProject, QgsVectorLayer, QgsWkbTypes
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

MAX_FEATURES = 5000
WEIGHTS = ("queen", "rook", "knn", "distance")
NOTE = ("A spatial statistic shows that values are arranged in a pattern, not why. A significant result calls for a look at the data and the place; it is not a finding about cause, and a result for areas "
        "says nothing about the individuals living in them.")


def _find_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _rings(geometry):
    parts = geometry.asMultiPolygon() if geometry.isMultipart() else [geometry.asPolygon()]
    return [[(p.x(), p.y()) for p in ring] for part in parts for ring in part]


def read_features(layer, field, need_rings):
    """(feature ids, values, centroids, rings or None, problem) from a vector layer. Reads every feature once; a missing geometry or value is a refusal that says how many."""
    ids, values, points, rings = [], [], [], []
    no_geometry = no_value = 0
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        value = feature[field]
        if geometry is None or geometry.isNull() or geometry.isEmpty():
            no_geometry += 1
            continue
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
            no_value += 1
            continue
        if len(ids) >= MAX_FEATURES:
            return None, None, None, None, f"The layer has more than {MAX_FEATURES:,} features; this tool stops there so QGIS stays responsive. Clip or aggregate it first."
        ids.append(feature.id())
        values.append(float(value))
        centre = geometry.centroid().asPoint()
        points.append((centre.x(), centre.y()))
        if need_rings:
            rings.append(_rings(geometry))
    if no_geometry or no_value:
        parts = []
        if no_geometry:
            parts.append(f"{no_geometry} feature(s) have no geometry")
        if no_value:
            parts.append(f"{no_value} feature(s) have no number in '{field}'")
        return None, None, None, None, "; ".join(parts) + ". Remove or fill them first: dropping them would change who is next to whom, so this tool does not guess."
    return ids, values, points, (rings if need_rings else None), None


def build_neighbours(layer, weights, k, distance, points, rings):
    """(neighbour lists, problem)."""
    try:
        if weights in ("queen", "rook"):
            return sw.contiguity(rings, weights), None
        if weights == "knn":
            return sw.knn(points, k), None
        if layer.crs().isGeographic():
            return None, "A distance band needs a projected CRS (its distance is in the layer's units, which would be degrees here). Reproject the layer first, or use k nearest neighbours."
        return sw.distance_band(points, distance), None
    except ValueError as e:
        return None, str(e)


@register_tool(
    "calculate_spatial_autocorrelation",
    "Test whether a numeric field is spatially clustered (similar values near each other), alternating (high next to low) or no different from a random arrangement: global Moran's I with a permutation p-value, "
    "and with write_local=true the Local Moran's I (LISA) per feature as a NEW layer with lisa_i, lisa_p and lisa_class (HH high among high, LL low among low, HL a high outlier among low, LH a low outlier "
    "among high, or 'not significant'). weights: 'queen' or 'rook' (polygon layers, from shared boundaries), 'knn' (k nearest, pass k) or 'distance' (a distance band in layer units, projected CRS only, pass distance). "
    "Needs a number on every feature (it refuses and says how many are missing). At most 5,000 features. The input layer is never changed. Evidence of a pattern, not of its cause; the local p-values are not "
    "corrected for testing every feature.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"},
        "field": {"type": "string", "description": "A numeric field."},
        "weights": {"type": "string", "enum": list(WEIGHTS), "description": "queen (default), rook, knn or distance."},
        "k": {"type": "integer", "description": "For weights='knn': how many nearest neighbours each feature counts (for example 5)."},
        "distance": {"type": "number", "description": "For weights='distance': the band in the layer's units (projected CRS)."},
        "permutations": {"type": "integer", "description": "Shuffles for the p-value, 99 to 9999 (default 999)."},
        "seed": {"type": "integer", "description": "Random seed (default 1); the same seed gives the same numbers."},
        "write_local": {"type": "boolean", "description": "Also add a new layer with the Local Moran result per feature (default false)."},
        "alpha": {"type": "number", "description": "Significance level for the local classes (default 0.05)."},
        "output_name": {"type": "string", "description": "Name of the local-result layer (default '<layer>_lisa')."},
    }, "required": ["layer_name", "field"]},
    keywords=["spatial autocorrelation", "morans i", "moran's i", "moran i", "local moran", "lisa", "is this a real cluster", "clustered or random", "is there a spatial pattern", "spatial dependence",
              "high next to high", "spatial clustering test"],
)
def calculate_spatial_autocorrelation(layer_name, field, weights="queen", k=None, distance=None, permutations=999, seed=1, write_local=False, alpha=0.05, output_name=None):
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
        return {"error": "weights='knn' needs k (how many nearest neighbours to count, for example 5)."}
    if weights == "distance" and distance is None:
        return {"error": "weights='distance' needs distance (the band, in the layer's units)."}
    try:
        ids, values, points, rings, problem = read_features(layer, field, weights in ("queen", "rook"))
        if problem:
            return {"error": problem}
        neighbours, problem = build_neighbours(layer, weights, k, distance, points, rings)
        if problem:
            return {"error": problem}
        result = ss.morans_i(values, neighbours, "row", permutations, seed)
    except ValueError as e:
        return {"error": f"calculate_spatial_autocorrelation: {e}"}
    except Exception as e:
        return {"error": f"The statistic could not be computed: {e}"}
    out = {"success": True, "layer_name": layer_name, "field": field, "weights": weights, "features": result["n"], "moran_i": round(result["I"], 4), "expected_i": round(result["expected_I"], 4),
           "z_permutation": None if result["z_sim"] is None else round(result["z_sim"], 3), "p_value": round(result["p_value"], 4), "permutations": result["permutations"], "seed": result["seed"],
           "mean_neighbours": round(sw.mean_neighbours(neighbours), 2), "separate_groups": sw.components(neighbours), "islands": len(result["islands"]),
           "interpretation": ss.interpret_global(result), "note": NOTE}
    if result["islands"]:
        out["island_warning"] = (f"{len(result['islands'])} feature(s) have no neighbour under '{weights}' and take no part in the statistic. If the polygons should touch, their boundaries do not share corner points "
                                 "exactly (this tool matches corners, not crossings): check the geometry, or use knn.")
    if write_local:
        try:
            local = ss.local_morans(values, neighbours, "row", permutations, seed, alpha)
        except ValueError as e:
            return {"error": f"calculate_spatial_autocorrelation: {e}"}
        layer_out = _write_local_layer(layer, field, ids, values, local, (output_name or "").strip() or f"{layer_name}_lisa")
        if isinstance(layer_out, str):
            return {"error": layer_out}
        out.update({"local_layer": layer_out.name(), "local_counts": local["counts"], "local_note": local["note"], "alpha": alpha})
    return out


def _write_local_layer(layer, field, ids, values, local, name):
    """A new memory layer with the source geometry and lisa_i, lisa_p, lisa_class. Returns the layer, or a refusal string."""
    geometry_name = QgsWkbTypes.displayString(layer.wkbType())
    out = QgsVectorLayer(f"{geometry_name}?crs={layer.crs().authid()}&field=src_id:integer&field=value:double&field=lisa_i:double&field=lisa_p:double&field=lisa_class:string", name, "memory")
    try:
        require_valid_layer(out)
    except ValueError as e:
        return str(e)
    by_id = {f.id(): f for f in layer.getFeatures()}
    feats = []
    for fid, value, row in zip(ids, values, local["features"], strict=True):
        f = QgsFeature(out.fields())
        f.setGeometry(by_id[fid].geometry())
        f.setAttributes([int(fid), value, None if row["local_i"] is None else round(row["local_i"], 6), None if row["p_value"] is None else round(row["p_value"], 4), row["class"]])
        feats.append(f)
    out.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(out)
    return out
