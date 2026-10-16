"""Runs ONE GRASS-family algorithm in its own process (python -m tests._grass_probe <alg_id>) and prints a single line `RESULT <json>`.
Same idea as tests/_geometry_probe.py (a hang or a crash is reported by algorithm name instead of taking the live job down), but only
REQUIRED parameters are filled: a GRASS algorithm has dozens of optional ones whose "1" would not be a sensible value. Raster and imagery
algorithms get the two test rasters, vector ones get polygons, then lines, then points. Written without a QGIS install: CI's first run
is its first execution."""
import json
import sys

from tests._geometry_probe import LAYERS, _is_optional, _make_rasters


def grass_params(algorithm, vector_layer):
    params = {}
    for p in algorithm.parameterDefinitions():
        if p.isDestination() or _is_optional(p):
            continue
        kind, name = p.type(), p.name()
        if kind in ("source", "vector", "layer"):
            params[name] = vector_layer
        elif kind == "raster":
            params[name] = "dem2" if "dem" in params.values() else "dem"
        elif kind == "multilayer":
            params[name] = ["dem", "dem2"] if algorithm.id().startswith(("grass:r.", "grass:i.")) else [vector_layer, vector_layer]
        elif kind == "field":
            params[name] = "val"
        elif kind == "number":
            default = p.defaultValue()
            params[name] = default if isinstance(default, (int, float)) and default > 0 else 1
        elif kind == "enum":
            params[name] = p.defaultValue() if p.defaultValue() is not None else 0
        elif kind == "boolean":
            params[name] = bool(p.defaultValue())
        elif kind == "string":
            default = p.defaultValue()
            params[name] = default if isinstance(default, str) and default else ("val" if "col" in name else "1")
        elif kind == "crs":
            params[name] = "EPSG:4326"
        elif kind == "extent":
            params[name] = "0.5,3.5,0.2,1.8 [EPSG:4326]"
        elif kind == "point":
            params[name] = "1,1 [EPSG:4326]"
        else:
            params[name] = p.defaultValue()
    return params


def main(alg_id):
    from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
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
    import tempfile
    for name, path in _make_rasters(tempfile.mkdtemp()).items():
        raster = QgsRasterLayer(path, name)
        if raster.isValid():
            QgsProject.instance().addMapLayer(raster)
    from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
    algorithm = QgsApplication.processingRegistry().algorithmById(alg_id)
    if algorithm is None:
        print("RESULT " + json.dumps({"ok": False, "error": "not in the QGIS registry"}), flush=True)
        return
    errors = []
    for layer_name in ("polys", "lines", "pts"):
        print(f"TRY {layer_name}", flush=True)
        result = run_allowlisted_processing_algorithm(alg_id, grass_params(algorithm, layer_name), new_layer_name="out")
        if result.get("success"):
            print("RESULT " + json.dumps({"ok": True, "layer": layer_name, "message": str(result.get("message", ""))[:120]}), flush=True)
            return
        errors.append(f"{layer_name}: {str(result.get('error'))[:200]}")
        if not algorithm.id().startswith("grass:v."):
            break   # raster and imagery algorithms do not take the vector test layers: one attempt is the whole story
    print("RESULT " + json.dumps({"ok": False, "error": " | ".join(errors)}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
