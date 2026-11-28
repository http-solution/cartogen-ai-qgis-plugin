"""Developer checks of DEF-30, DEF-38 and DEF-19 of the master task list in a real QGIS, with no model (written 2026-11-28). Needs internet for DEF-19.
Run it inside the QGIS 4.2.2 image CI uses, with the repository mounted, for example:
docker run --rm --network host -e QT_QPA_PLATFORM=offscreen -v "$PWD":/repo:ro qgis/qgis@<digest from .github/workflows/tests.yml> python3 /repo/tests/manual_live_checks/def_triage_3_real_qgis.py
It prints what each tool answers and asserts nothing, so a person reads the output. Results of 2026-11-28 are in the notes of those rows. Not a unit test."""
# ruff: noqa: E402, E702, E701
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsMeshLayer, QgsRasterLayer
app = QgsApplication([b"triage5"], False); QgsApplication.setPrefixPath("/usr", True); app.initQgis()
sys.path.insert(0, os.path.join(QgsApplication.pkgDataPath(), "python", "plugins"))
from processing.core.Processing import Processing
Processing.initialize()
import cartogen_ai.core.agent.agent_orchestrator as agent_mod
import make_full_smoke_fixtures as fx
fx.write_all("/tmp/fx5")
QgsProject.instance().clear()
agent = agent_mod.CartogenAi()
def call(n, a):
    r = agent._execute_tool(n, json.dumps(a)); return r if isinstance(r, dict) else {"raw": str(r)}
def show(label, d, n=420):
    print(" ", label, "->", json.dumps(d, default=str)[:n])

print("######## DEF-30: a mesh rasterised with a cell size far larger than the data")
mesh = QgsMeshLayer("/tmp/fx5/smoke_mesh.2dm", "smoke_mesh", "mdal")
print("  mesh valid:", mesh.isValid(), "| extent:", mesh.extent().toString(3) if mesh.isValid() else None, "| crs:", mesh.crs().authid() if mesh.isValid() else None)
QgsProject.instance().addMapLayer(mesh)
r = call("run_allowlisted_processing_algorithm", {"alg_id": "native:meshrasterize", "params": {"INPUT": "smoke_mesh", "DATASET_GROUPS": [0], "PIXEL_SIZE": 5, "CRS_OUTPUT": "EPSG:4326"}, "new_layer_name": "mesh_big_cells"})
show("PIXEL_SIZE 5", r, 700)
print("  says no layer was made:", ("NO layer" in json.dumps(r)) or r.get("layer_created") is False, "| names the cell size:", "cell" in json.dumps(r).lower())

r = call("run_allowlisted_processing_algorithm", {"alg_id": "native:meshrasterize", "params": {"INPUT": "smoke_mesh", "DATASET_GROUPS": [0], "PIXEL_SIZE": 0.0005, "CRS_OUTPUT": "EPSG:4326"}, "new_layer_name": "mesh_ok_cells"})
show("PIXEL_SIZE 0.0005 (sensible)", r, 500)

print("######## DEF-38: render_check on a bar chart, a line chart and an elevation profile")
lyr = QgsVectorLayer("Point?crs=EPSG:32638&field=name:string&field=pop:integer", "towns", "memory")
fs = []
for i, (n, v) in enumerate([("A", 50), ("B", 120), ("C", 300), ("D", 500)]):
    f = QgsFeature(lyr.fields()); f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(500000 + i * 1000, 1500000 + i * 500))); f.setAttributes([n, v]); fs.append(f)
lyr.dataProvider().addFeatures(fs); QgsProject.instance().addMapLayer(lyr)
with open("/tmp/dem5.asc", "w") as f:
    f.write("ncols 30\nnrows 30\nxllcorner 499000\nyllcorner 1499000\ncellsize 100\nNODATA_value -9999\n")
    for r_ in range(30): f.write(" ".join(str(100 + r_ * 5 + c * 3) for c in range(30)) + "\n")
dem = QgsRasterLayer("/tmp/dem5.asc", "dem5"); dem.setCrs(lyr.crs()); QgsProject.instance().addMapLayer(dem)
print("  dem valid:", dem.isValid())
r = call("create_print_layout", {"title": "Chart check", "output_path": "/tmp/chartcheck.pdf"})
print("  layout:", {k: str(v)[:80] for k, v in r.items() if k in ("success", "layout_name", "error")})
ln = r.get("layout_name", "Chart check")
for kind in ("bar", "line"):
    rr = call("add_layout_chart", {"layout_name": ln, "layer_name": "towns", "x_field": "name", "y_field": "pop", "chart_type": kind})
    show(f"{kind} chart", {k: v for k, v in rr.items() if k in ("success", "error", "render_check", "placement_note")}, 520)
rr = call("add_layout_elevation_profile", {"layout_name": ln, "layer_names": ["dem5"], "start_x": 499500, "start_y": 1499500, "end_x": 501500, "end_y": 1501500})
show("elevation profile", {k: v for k, v in rr.items() if k in ("success", "error", "render_check", "placement_note")}, 620)

print("######## DEF-19: a UCDP fetch that matches nothing must not add an empty layer")
before = len(QgsProject.instance().mapLayers())
r = call("fetch_ucdp_conflict_events", {"country": "Yemen", "start_date": "2035-01-01", "end_date": "2035-01-31"})
show("UCDP, a month in the future", r, 600)
print("  layers added:", len(QgsProject.instance().mapLayers()) - before)
app.exitQgis()
