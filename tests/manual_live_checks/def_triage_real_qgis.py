"""Developer checks of four P0/P1 defect rows (DEF-10, DEF-11, DEF-12, DEF-14 of the master task list) in a real QGIS, with no model (written 2026-11-27). Needs internet for DEF-10.
Run it inside the QGIS 4.2.2 image CI uses, with the repository mounted, for example:
docker run --rm --network host -e QT_QPA_PLATFORM=offscreen -v "$PWD":/repo:ro qgis/qgis@<digest from .github/workflows/tests.yml> python3 /repo/tests/manual_live_checks/def_triage_real_qgis.py
It prints what each tool answers; it asserts nothing, so a person reads the output. Results of 2026-11-27 are in the notes of those rows. Not a unit test."""
# ruff: noqa: E402, S112
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)
from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

app = QgsApplication([b"triage"], False)
QgsApplication.setPrefixPath("/usr", True)
app.initQgis()
sys.path.insert(0, os.path.join(QgsApplication.pkgDataPath(), "python", "plugins"))
import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from processing.core.Processing import Processing

Processing.initialize()
QgsProject.instance().clear()
agent = agent_mod.CartogenAi()


def call(name, args):
    r = agent._execute_tool(name, json.dumps(args))
    return r if isinstance(r, dict) else {"raw": str(r)}


def layout_texts():
    out = {}
    for lay in QgsProject.instance().layoutManager().layouts():
        parts = []
        for it in lay.items():
            for attr in ("text", "html"):
                if hasattr(it, attr):
                    try:
                        v = getattr(it, attr)()
                    except Exception:
                        continue
                    if v and isinstance(v, str):
                        parts.append(v.replace("\n", " / "))
        out[lay.name()] = " || ".join(parts)
    return out


def asc(path, base):
    with open(path, "w") as f:
        f.write("ncols 4\nnrows 4\nxllcorner 44.0\nyllcorner 12.0\ncellsize 0.01\nNODATA_value -9999\n")
        for row in range(4):
            f.write(" ".join(str(base + row + col) for col in range(4)) + "\n")


print("== DEF-14: typed figures versus figures from the layer")
lyr = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer", "districts", "memory")
feats = []
for i, (n, v) in enumerate([("Taiz", 94000), ("Aden", 76000), ("Sanaa", 52000)]):
    f = QgsFeature(lyr.fields())
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(44 + i, 13 + i)))
    f.setAttributes([n, v])
    feats.append(f)
lyr.dataProvider().addFeatures(feats)
QgsProject.instance().addMapLayer(lyr)
typed = [{"label": "Taiz", "value": "120,000"}, {"label": "Aden", "value": "85,000"}, {"label": "Sanaa", "value": "45,000"}]
r = call("create_print_layout", {"title": "typed", "template": "sitrep", "body_text": "Situation.", "output_path": "/tmp/typed.pdf", "key_figures": typed})
print("  warning:", str(r.get("sitrep_warning"))[:300])
call("create_print_layout", {"title": "fromlayer", "template": "sitrep", "body_text": "Situation.", "output_path": "/tmp/fromlayer.pdf",
                             "key_figures_from": {"layer_name": "districts", "label_field": "name", "value_field": "pop"}})
for name, txt in layout_texts().items():
    print(f"  layout {name!r}: 120,000={'120,000' in txt} 94,000={'94,000' in txt} marker={'not found in the project data' in txt}")

print("== DEF-12: execute_pyqgis_script")
print("  no script:", str(call("execute_pyqgis_script", {}).get("error"))[:160])
print("  prints and returns a dict:", call("execute_pyqgis_script", {"script": "def run():\n    print('hi')\n    return {'n': 3}\n"}))
print("  returns a set:", call("execute_pyqgis_script", {"script": "def run():\n    return {1, 2, 3}\n"}))

print("== DEF-11: change detection on files that are not loaded")
asc("/tmp/before.asc", 10)
asc("/tmp/after.asc", 12)
print("  two paths:", str(call("calculate_raster_change_detection", {"raster_before": "/tmp/before.asc", "raster_after": "/tmp/after.asc"}))[:300])
print("  a missing path:", str(call("calculate_raster_change_detection", {"raster_before": "/tmp/nothere.asc", "raster_after": "/tmp/after.asc"}))[:200])

print("== DEF-10: Sentinel-2 STAC search")
print("  ", str(call("search_stac_satellite_imagery", {"bbox": [43.8, 13.4, 44.2, 13.7], "start_date": "2025-01-01", "end_date": "2025-02-15", "limit": 3, "max_cloud_cover": 40}))[:300])
app.exitQgis()
