"""Runs ONE geometry-family algorithm in its own process (python -m tests._geometry_probe <alg_id>) and prints a single line
`RESULT <json>`. tests/test_processing_geometry_family_live.py starts one of these per algorithm, with a timeout, because the first CI
run of the 78 in a single process hung for 40 minutes on one algorithm and gave no hint which: a hang or a crash in one algorithm is
now reported by name instead of taking the whole live job with it."""
import json
import sys

LAYERS = {
    "polys": ("Polygon", ["POLYGON((0 0,2 0,2 2,0 2,0 0),(0.5 0.5,1 0.5,1 1,0.5 1,0.5 0.5))", "POLYGON((2 0,4 0,4 2,2 2,2 0))"]),
    "lines": ("LineString", ["LINESTRING(0 0,1 1,2 0,3 1)", "LINESTRING(0 1,3 0)"]),
    # CI run 38684090553: native:climbalongline refuses a layer without Z values, so one 3D line layer is tried last.
    "linesz": ("LineStringZ", ["LINESTRING Z(0 0 0,1 1 5,2 0 10)", "LINESTRING Z(0 1 2,3 0 8)"]),
    "pts": ("Point", ["POINT(0.2 0.2)", "POINT(1.5 0.4)", "POINT(0.9 1.7)", "POINT(2.5 1.5)", "POINT(3.1 0.2)"]),
}


def _is_optional(parameter):
    from qgis.core import Qgis
    flag = getattr(getattr(Qgis, "ProcessingParameterFlag", None), "Optional", None)
    if flag is None:
        flag = parameter.FlagOptional
    return bool(parameter.flags() & flag)


def params_for(algorithm, layer_name, distinct=False):
    params = {}
    for p in algorithm.parameterDefinitions():
        if p.isDestination():
            continue
        kind = p.type()
        if kind in ("source", "vector"):
            # CI run 38684090553: the hub algorithms (hublines, distance to nearest hub) refuse the same layer as hubs and spokes, so a
            # second source parameter gets a different layer, but only on a retry so algorithms that passed with one layer are unchanged.
            if distinct and any(v in ("polys", "lines", "linesz", "pts") for v in params.values()):
                params[p.name()] = "polys" if layer_name == "pts" else "pts"
            else:
                params[p.name()] = layer_name
        elif kind in ("number", "distance", "area", "angle"):
            default = p.defaultValue()
            # CI run 38683312012: native:randomextract(+withinsubsets) default NUMBER=10 exceeds the 2-5 test features and QGIS refuses
            # "Selected number is greater than feature count"; that is the probe's fault, not the algorithm's, so ask for one.
            if p.name() == "NUMBER":
                default = 1
            params[p.name()] = default if isinstance(default, (int, float)) and default > 0 else 1
        elif kind == "enum":
            params[p.name()] = p.defaultValue() if p.defaultValue() is not None else 0
        elif kind == "boolean":
            params[p.name()] = bool(p.defaultValue())
        elif kind == "field":
            numeric = "numeric" in str(p.dataType()).lower()
            params[p.name()] = "val" if numeric else "name"
        elif kind == "extent":
            params[p.name()] = "0.5,3.5,0.2,1.8 [EPSG:4326]"
        elif kind == "point":
            params[p.name()] = "1,1 [EPSG:4326]"
        elif not _is_optional(p):
            params[p.name()] = p.defaultValue()
    return params


def main(alg_id):
    from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    from tests.test_network_units_live import _boot
    why = _boot()
    if why:
        print("RESULT " + json.dumps({"ok": False, "error": "boot: " + why}), flush=True)
        return
    for name, (kind, wkts) in LAYERS.items():
        layer = QgsVectorLayer(f"{kind}?crs=EPSG:4326&field=name:string&field=val:double", name, "memory")
        feats = []
        for i, wkt in enumerate(wkts):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([f"{name}{i}", float(i + 1)])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
    from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
    algorithm = QgsApplication.processingRegistry().algorithmById(alg_id)
    if algorithm is None:
        print("RESULT " + json.dumps({"ok": False, "error": "not in the QGIS registry"}), flush=True)
        return
    errors = []
    for layer_name in ("polys", "lines", "pts", "linesz"):
        print(f"TRY {layer_name}", flush=True)
        result = run_allowlisted_processing_algorithm(alg_id, params_for(algorithm, layer_name), new_layer_name="out")
        if not result.get("success"):
            retry = run_allowlisted_processing_algorithm(alg_id, params_for(algorithm, layer_name, distinct=True), new_layer_name="out")
            if retry.get("success"):
                result = retry
        if result.get("success"):
            print("RESULT " + json.dumps({"ok": True, "layer": layer_name}), flush=True)
            return
        errors.append(f"{layer_name}: {str(result.get('error'))[:160]}")
    print("RESULT " + json.dumps({"ok": False, "error": " | ".join(errors)}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
