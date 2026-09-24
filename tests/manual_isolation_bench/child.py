"""Phase 0 benchmark child: what an isolated execute_pyqgis_script subprocess would do.
Headless (GUI=False), fresh QgsApplication, loads a serialized project copy, runs a trivial
'script', writes a result summary. Reports its own internal phase timings to a JSON file."""
import json
import sys
import time

t0 = time.perf_counter()
from qgis.core import QgsApplication, QgsProject  # noqa: E402
t_import = time.perf_counter()

app = QgsApplication([], False)
app.initQgis()
t_init = time.perf_counter()

proj_path, out_path = sys.argv[1], sys.argv[2]
proj = QgsProject.instance()
ok = proj.read(proj_path)
t_read = time.perf_counter()

counts = {}
for lyr in proj.mapLayers().values():
    try:
        counts[lyr.name()] = {"valid": lyr.isValid(),
                              "features": lyr.featureCount() if hasattr(lyr, "featureCount") else None}
    except Exception as e:
        counts[lyr.name()] = {"error": str(e)}
t_script = time.perf_counter()

with open(out_path, "w") as fh:
    json.dump({
        "read_ok": ok,
        "counts": counts,
        "t_import": t_import - t0,
        "t_initQgis": t_init - t_import,
        "t_project_read": t_read - t_init,
        "t_script": t_script - t_read,
        "t_child_total": t_script - t0,
    }, fh)
app.exitQgis()
