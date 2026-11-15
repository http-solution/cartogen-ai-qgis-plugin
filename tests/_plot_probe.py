"""Runs ONE plot or information algorithm in its own process (python -m tests._plot_probe <alg_id>) and prints one line `PLOTPROBE <json>` (PLAN-023 R11-5, PLAN-006 E2b/E2a).

A probe, not a feature test: it records whether the algorithm runs in the QGIS image CI uses, with the plot module present or absent, what file it writes and how big, and the algorithm's
own parameter names (so the tool that follows is built from what QGIS reports, not from memory). A hang or crash is reported by name by the caller, as for the geometry sweep.
Written without a QGIS install: CI's first run is where the answers come from."""
import json
import os
import sys
import tempfile


def _outputs(algorithm, folder):
    """{destination name: path} for every output destination the algorithm has. Needs QGIS."""
    out = {}
    for p in algorithm.parameterDefinitions():
        if p.isDestination():
            ext = "png" if "image" in algorithm.id() else ("json" if algorithm.id().endswith("json") else ("html" if "html" in str(p.type()).lower() or p.name() == "OUTPUT" else "txt"))
            out[p.name()] = os.path.join(folder, f"{p.name()}.{ext}")
    return out


def main(alg_id):
    from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    from tests._geometry_probe import _make_rasters, params_for
    from tests.test_network_units_live import _boot
    why = _boot()
    if why:
        print("PLOTPROBE " + json.dumps({"id": alg_id, "ok": False, "error": "boot: " + why}), flush=True)
        return
    folder = tempfile.mkdtemp(prefix="cartogen_plotprobe_")
    result = {"id": alg_id}
    try:
        import plotly
        result["plotly"] = getattr(plotly, "__version__", "present")
    except ImportError as e:
        result["plotly"] = f"absent: {str(e)[:80]}"
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=val:double&field=val2:double", "pts", "memory")
    feats = []
    for i, (x, y) in enumerate(((0.2, 0.2), (1.5, 0.4), (0.9, 1.7), (2.5, 1.5), (3.1, 0.2))):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} {y})"))
        f.setAttributes([f"p{i % 3}", float(i + 1), float((i + 1) ** 2)])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    rasters = _make_rasters(folder)
    for name, path in rasters.items():
        QgsProject.instance().addMapLayer(QgsRasterLayer(path, name))
    algorithm = QgsApplication.processingRegistry().algorithmById(alg_id)
    if algorithm is None:
        result.update(ok=False, error="not in the QGIS registry")
        print("PLOTPROBE " + json.dumps(result), flush=True)
        return
    result["parameters"] = {p.name(): f"{p.type()}{' (destination)' if p.isDestination() else ''}" for p in algorithm.parameterDefinitions()}
    import processing
    params = params_for(algorithm, "pts")
    for key, value in list(params.items()):
        if value == "val" and key.upper().startswith(("Y", "VALUE")):
            params[key] = "val2" if key.upper().startswith("Y") else value
    if alg_id.startswith("gdal:ogrinfo") or alg_id == "gdal:dataset_identify":
        gpkg = os.path.join(folder, "pts.gpkg")
        processing.run("native:savefeatures", {"INPUT": layer, "OUTPUT": gpkg})
        params["INPUT"] = gpkg
    params.update(_outputs(algorithm, folder))
    result["params_used"] = {k: (v if isinstance(v, (int, float, bool, str)) else str(v)[:60]) for k, v in params.items()}
    try:
        outcome = processing.run(alg_id, params)
        files = {}
        for key, path in (outcome.items() if isinstance(outcome, dict) else []):
            if isinstance(path, str) and os.path.isfile(path):
                with open(path, "rb") as fh:
                    head = fh.read(160)
                files[key] = {"bytes": os.path.getsize(path), "head": head.decode("utf-8", "replace")[:120]}
        result.update(ok=bool(files), files=files)
        if not files:
            result["error"] = "ran but wrote no file; result keys: " + ", ".join(map(str, outcome))[:160]
    except Exception as e:
        result.update(ok=False, error=f"{type(e).__name__}: {str(e)[:300]}")
    print("PLOTPROBE " + json.dumps(result, default=str), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
