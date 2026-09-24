"""MANUAL, live-QGIS-only (not collected by unittest). Run: python-qgis.bat tests/manual_isolation_bench/bench.py

Phase 0 benchmark parent -- IMPLEMENTATION_TRACKER.md SS1.11 / docs/EXECUTE_PYQGIS_SCRIPT_
ISOLATION_SCOPE_2026-09-24.md. Measures Path A's real overhead, and verifies the memory-layer
fidelity question empirically instead of assuming it."""
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
from qgis.core import (  # noqa: E402
    QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext,
)

app = QgsApplication([], True)
app.initQgis()

HERE = os.path.dirname(os.path.abspath(__file__))
CHILD = os.path.join(HERE, "child.py")
FIXTURE_SRC = os.path.join(REPO, "docs", "release_smoke_assets", "inputs")
work = tempfile.mkdtemp(prefix="p0_bench_")
# Copy the fixture bundle so QGIS opening/writing the gpkg never touches the repo's copy.
fixtures = os.path.join(work, "inputs")
shutil.copytree(FIXTURE_SRC, fixtures)

print("sys.executable:", sys.executable)
print("python:", sys.version.split()[0])


def stats(xs):
    return {"n": len(xs), "min": round(min(xs), 3), "median": round(statistics.median(xs), 3),
            "max": round(max(xs), 3)}


def load_fixture():
    proj = QgsProject.instance()
    proj.clear()
    assert proj.read(os.path.join(fixtures, "smoke_start.qgz")), "fixture failed to load"
    return proj


def spawn_child(proj_path):
    out = os.path.join(work, "child_out.json")
    t = time.perf_counter()
    r = subprocess.run([sys.executable, CHILD, proj_path, out], capture_output=True, text=True)
    wall = time.perf_counter() - t
    if r.returncode != 0:
        print("CHILD FAILED:", r.returncode, r.stderr[-800:])
    data = {}
    if os.path.exists(out):
        with open(out) as fh:
            data = json.load(fh)
    return wall, data


# ---- Scenario 1: fixture project as-is (all file-backed layers) ----------------------
proj = load_fixture()
n_layers = len(proj.mapLayers())
print(f"\nScenario 1: fixture project, {n_layers} layers, all file-backed")

ser, spawn, reload_ = [], [], []
child_phases = {"t_import": [], "t_initQgis": [], "t_project_read": [], "t_script": []}
ITER = 8
for i in range(ITER):
    tmp_qgz = os.path.join(work, f"snap_{i}.qgz")
    orig_name = proj.fileName()
    t = time.perf_counter()
    assert proj.write(tmp_qgz)
    ser.append(time.perf_counter() - t)
    proj.setFileName(orig_name)

    wall, data = spawn_child(tmp_qgz)
    spawn.append(wall)
    for k in child_phases:
        child_phases[k].append(data.get(k, 0))

    # "reload results": load a result layer back from disk into the live project
    t = time.perf_counter()
    lyr = QgsVectorLayer(os.path.join(fixtures, "smoke_data.gpkg") + "|layername=smoke_points",
                         "result_reload", "ogr")
    assert lyr.isValid()
    proj.addMapLayer(lyr)
    reload_.append(time.perf_counter() - t)
    proj.removeMapLayer(lyr.id())

print("  serialize live project -> .qgz (s):", stats(ser))
print("  child spawn, wall clock end-to-end (s):", stats(spawn))
for k, v in child_phases.items():
    print(f"     child internal {k} (s):", stats(v))
print("  reload one result layer into live project (s):", stats(reload_))
total = [a + b + c for a, b, c in zip(ser, spawn, reload_)]
print("  TOTAL added overhead per call (s):", stats(total))

# ---- In-process baseline: the real execute_pyqgis_script, trivial script -------------------
from cartogen_ai.core.agent.tools.system_tools import execute_pyqgis_script  # noqa: E402
trivial = "def run():\n    return len(QgsProject.instance().mapLayers())\n"
base = []
for _ in range(50):
    t = time.perf_counter()
    r = execute_pyqgis_script(trivial)
    base.append(time.perf_counter() - t)
assert r.get("success"), r
print("\nIn-process baseline (real execute_pyqgis_script, trivial script, 50 runs) (s):", stats(base))

# ---- Scenario 2: the memory-layer fidelity question --------------------------------------
print("\nScenario 2: memory (scratch) layers -- this plugin's tools output these constantly")
for n_feat in (1_000, 50_000):
    proj = load_fixture()
    mem = QgsVectorLayer("Point?crs=EPSG:32636&field=id:int", f"scratch_{n_feat}", "memory")
    feats = []
    for i in range(n_feat):
        f = QgsFeature(mem.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(700000 + i % 500, 1700000 + i // 500)))
        f.setAttributes([i])
        feats.append(f)
    mem.dataProvider().addFeatures(feats)
    mem.updateExtents()
    proj.addMapLayer(mem)

    tmp_qgz = os.path.join(work, f"mem_{n_feat}.qgz")
    orig_name = proj.fileName()
    t = time.perf_counter()
    proj.write(tmp_qgz)
    t_ser = time.perf_counter() - t
    proj.setFileName(orig_name)
    _, data = spawn_child(tmp_qgz)
    seen = data.get("counts", {}).get(f"scratch_{n_feat}")
    print(f"  {n_feat} features in memory layer: qgz write {t_ser:.3f}s; "
          f"child sees -> {seen}   (live parent has {mem.featureCount()})")

    # Workaround cost: export the memory layer to a GPKG so its data actually reaches the child
    gpkg = os.path.join(work, f"mem_export_{n_feat}.gpkg")
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    t = time.perf_counter()
    err = QgsVectorFileWriter.writeAsVectorFormatV3(mem, gpkg, QgsCoordinateTransformContext(), opts)
    t_exp = time.perf_counter() - t
    print(f"     workaround: export to GPKG {t_exp:.3f}s (writer status {err[0]})")

shutil.rmtree(work, ignore_errors=True)
print("\nDONE")
