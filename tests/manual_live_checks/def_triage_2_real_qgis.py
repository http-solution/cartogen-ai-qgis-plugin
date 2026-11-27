"""Developer checks of defect and roadmap rows DEF-13, DEF-20, DEF-22, DEF-34 and LR-3 of the master task list in a real QGIS, with no model (written 2026-11-27).
Run it inside the QGIS 4.2.2 image CI uses, with the repository mounted, for example:
docker run --rm --network host -e QT_QPA_PLATFORM=offscreen -v "$PWD":/repo:ro qgis/qgis@<digest from .github/workflows/tests.yml> python3 /repo/tests/manual_live_checks/def_triage_2_real_qgis.py
It prints what each tool answers and asserts nothing, so a person reads the output. Results of 2026-11-27 are in the notes of those rows. Not a unit test."""
# ruff: noqa: E402, E702, E701, UP031, SIM105, S110
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsVectorFileWriter, QgsCoordinateTransformContext
app = QgsApplication([b"triage4"], False); QgsApplication.setPrefixPath("/usr", True); app.initQgis()
sys.path.insert(0, os.path.join(QgsApplication.pkgDataPath(), "python", "plugins"))
import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from processing.core.Processing import Processing
Processing.initialize()
QgsProject.instance().clear()
agent = agent_mod.CartogenAi()
def call(name, args):
    r = agent._execute_tool(name, json.dumps(args))
    return r if isinstance(r, dict) else {"raw": str(r)}
def show(label, d, keys=None, n=330):
    keys = keys or ("success", "error", "message", "layer_name", "why_empty", "note", "exported", "reason")
    print(" ", label, "->", {k: str(v)[:n] for k, v in d.items() if k in keys} or str(d)[:n])
def pts(name, rows, extra="field=name:string&field=cases:integer&field=district:string"):
    lyr = QgsVectorLayer("Point?crs=EPSG:4326&" + extra, name, "memory")
    fs = []
    for i, row in enumerate(rows):
        f = QgsFeature(lyr.fields()); f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(44 + i * .1, 13 + i * .1))); f.setAttributes(list(row)); fs.append(f)
    lyr.dataProvider().addFeatures(fs); return lyr

print("######## DEF-20: add_layer_from_path forwards 'sublayer' for a named layer of a GeoPackage")
a = pts("alpha", [("A", 1, "X"), ("B", 2, "Y")]); b = pts("beta", [("C", 3, "Z")])
gp = "/tmp/two.gpkg"
o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = "alpha"
QgsVectorFileWriter.writeAsVectorFormatV3(a, gp, QgsCoordinateTransformContext(), o)
o2 = QgsVectorFileWriter.SaveVectorOptions(); o2.driverName = "GPKG"; o2.layerName = "beta"; o2.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
QgsVectorFileWriter.writeAsVectorFormatV3(b, gp, QgsCoordinateTransformContext(), o2)
r = call("add_layer_from_path", {"file_path": gp, "layer_name": "only_beta", "sublayer": "beta"})
show("sublayer=beta", r)
lyrs = QgsProject.instance().mapLayersByName("only_beta")
print("  layer 'only_beta' exists:", bool(lyrs), "| features:", lyrs[0].featureCount() if lyrs else None, "(beta has 1 feature, alpha has 2)")

print("######## DEF-22: an extract that matches nothing says why")
QgsProject.instance().addMapLayer(pts("districts", [("Taiz", 10, "Al-Mudhaffar"), ("Aden", 20, "Crater"), ("Sanaa", 30, "Old City")]))
r = call("run_allowlisted_processing_algorithm", {"alg_id": "native:extractbyexpression", "params": {"INPUT": "districts", "EXPRESSION": "\"name\" = 'Nowhere'"}, "new_layer_name": "none_found"})
show("expression matching nothing", r, n=700)

print("######## DEF-34: the native heatmap guard (1-degree radius on a point layer; any radius on polygons)")
r = call("run_allowlisted_processing_algorithm", {"alg_id": "native:heatmapkerneldensityestimation", "params": {"INPUT": "districts", "RADIUS": 1, "PIXEL_SIZE": 0.01}, "new_layer_name": "heat_deg"})
show("radius 1 in a degree CRS", r, n=500)
poly = QgsVectorLayer("Polygon?crs=EPSG:32638&field=name:string", "polys", "memory")
f = QgsFeature(poly.fields()); f.setGeometry(QgsGeometry.fromWkt("POLYGON((500000 1500000,501000 1500000,501000 1501000,500000 1501000,500000 1500000))")); f.setAttributes(["p"]); poly.dataProvider().addFeatures([f]); QgsProject.instance().addMapLayer(poly)
r = call("run_allowlisted_processing_algorithm", {"alg_id": "native:heatmapkerneldensityestimation", "params": {"INPUT": "polys", "RADIUS": 500, "PIXEL_SIZE": 50}, "new_layer_name": "heat_poly"})
show("a polygon layer", r, n=500)

print("######## LR-3: epidemic bulletin")
QgsProject.instance().addMapLayer(pts("cases", [("Taiz", 15, "Al-Mudhaffar"), ("Aden", 12, "Crater"), ("Sanaa", 9, "Old City"), ("Ibb", 5, "Ibb City")], "field=name:string&field=cases:integer&field=district:string"))
r = call("create_print_layout", {"title": "Weekly bulletin, Surveillance District", "template": "epi_bulletin", "body_text": "Cases rose in Surveillance District.", "output_path": "/tmp/epi_bad.pdf",
        "key_figures_from": {"layer_name": "cases", "label_field": "name", "value_field": "cases", "top_n": 3}})
show("a place name no layer holds (title and summary)", r, n=420)
print("  PDF written for the refused one:", os.path.exists("/tmp/epi_bad.pdf"))
r = call("create_print_layout", {"title": "Weekly bulletin, Taiz and Aden", "template": "epi_bulletin", "body_text": "Cases rose in Taiz and Aden.", "output_path": "/tmp/epi_ok.pdf",
        "key_figures_from": {"layer_name": "cases", "label_field": "name", "value_field": "cases", "top_n": 3}})
show("place names that the layer holds", r, keys=("success", "error", "exported", "output_path", "sitrep_warning", "export_error"), n=420)
print("  PDF exists and size:", os.path.exists("/tmp/epi_ok.pdf"), os.path.getsize("/tmp/epi_ok.pdf") if os.path.exists("/tmp/epi_ok.pdf") else None)
texts = []
for lay in QgsProject.instance().layoutManager().layouts():
    for it in lay.items():
        if hasattr(it, "text"):
            try: texts.append(it.text())
            except Exception: pass
blob = " ".join(texts)
print("  top-3 figures from the data on the layout: 15=%s 12=%s 9=%s | the 4th (5) left out of the top 3: %s | invented 20/18 present: %s/%s" % ("15" in blob, "12" in blob, "9" in blob, "Ibb" not in blob, "20" in blob.split("KEY")[-1][:80], "18" in blob.split("KEY")[-1][:80]))

print("######## DEF-13: update_task with no id, null status, or no tasks")
for args in ({}, {"task_id": None, "status": None}, {"task_id": "99", "status": "DONE"}):
    show("update_task %s" % json.dumps(args), call("update_task", args), n=240)
app.exitQgis()
