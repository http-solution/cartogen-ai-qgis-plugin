"""MANUAL, live-QGIS-only (not collected by unittest). Verifies Phase 1's actual
subprocess-isolation round-trip against a real QgsApplication -- not the Phase 0
timing-only benchmark in this same directory. Run inside the qgis/qgis Docker
image this repo's CI pins:

    docker run --rm -v <repo>:/repo qgis/qgis@sha256:... \\
        python3 /repo/tests/manual_isolation_bench/phase1_live_check.py

IMPLEMENTATION_TRACKER.md §1.11, Phase 1 go-ahead 2026-09-28.
"""
import os
import sys
import traceback

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

from qgis.core import (  # noqa: E402
    QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
)

app = QgsApplication([], False)
app.initQgis()

from cartogen_ai.core.agent.services import script_isolation as si  # noqa: E402

passed = []
failed = []


def check(name, condition, detail=""):
    if condition:
        passed.append(name)
        print(f"PASS: {name}")
    else:
        failed.append(name)
        print(f"FAIL: {name} {detail}")


def fresh_project():
    QgsProject.instance().clear()


# --- Test 1: a script that creates and adds a brand-new memory layer ---
fresh_project()
script_new_layer = """
def run():
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "isolated_new_layer", "memory")
    provider = layer.dataProvider()
    feat = QgsFeature()
    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1.0, 2.0)))
    provider.addFeatures([feat])
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return "created"
"""
try:
    result = si.run_isolated_script(script_new_layer)
    check("new-layer script reports success", result.get("success") is True, result)
    new_layer_matches = QgsProject.instance().mapLayersByName("isolated_new_layer")
    check("new layer reconciled into live project", len(new_layer_matches) == 1, new_layer_matches)
    if new_layer_matches:
        check("new layer has its one feature", new_layer_matches[0].featureCount() == 1,
              new_layer_matches[0].featureCount())
except Exception:
    failed.append("new-layer script (exception)")
    print("FAIL: new-layer script raised:\n" + traceback.format_exc())

# --- Test 2: a script that reads an existing memory layer's pre-existing feature and adds another ---
fresh_project()
existing = QgsVectorLayer("Point?crs=EPSG:4326", "existing_memory_layer", "memory")
existing_provider = existing.dataProvider()
seed_feat = QgsFeature()
seed_feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(10.0, 20.0)))
existing_provider.addFeatures([seed_feat])
existing.updateExtents()
QgsProject.instance().addMapLayer(existing)
pre_count = existing.featureCount()

script_add_feature = """
def run():
    layer = QgsProject.instance().mapLayersByName("existing_memory_layer")[0]
    seen = layer.featureCount()
    provider = layer.dataProvider()
    feat = QgsFeature()
    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(30.0, 40.0)))
    provider.addFeatures([feat])
    layer.updateExtents()
    return {"saw_before": seen}
"""
try:
    result = si.run_isolated_script(script_add_feature)
    check("existing-layer script reports success", result.get("success") is True, result)
    check("script saw the pre-existing feature (memory-layer export worked)",
          result.get("result", {}).get("saw_before") == pre_count, result)
    live_existing = QgsProject.instance().mapLayersByName("existing_memory_layer")[0]
    check("live memory layer synced to 2 features after the isolated add",
          live_existing.featureCount() == 2, live_existing.featureCount())
except Exception:
    failed.append("existing-layer script (exception)")
    print("FAIL: existing-layer script raised:\n" + traceback.format_exc())

# --- Test 3: the uncommitted-edits guard actually blocks ---
fresh_project()
edit_layer = QgsVectorLayer("Point?crs=EPSG:4326", "editable_layer", "memory")
QgsProject.instance().addMapLayer(edit_layer)
edit_layer.startEditing()
try:
    editable = si.has_uncommitted_edits()
    check("uncommitted-edits guard detects the editable layer", "editable_layer" in editable, editable)
finally:
    edit_layer.rollBack()

# --- Test 4: a blocked-module script still gets rejected before ever reaching the worker ---
fresh_project()
script_blocked = """
import os
def run():
    return os.getcwd()
"""
try:
    result = si.run_isolated_script(script_blocked)
    check("blocked import still rejected inside isolation", "error" in result and "Blocked import" in result["error"], result)
except Exception:
    failed.append("blocked-import script (exception)")
    print("FAIL: blocked-import script raised:\n" + traceback.format_exc())

# --- Test 5: interpreter lookup is sane on this platform (Linux) ---
check("find_python_interpreter returns sys.executable on Linux", si.find_python_interpreter() == sys.executable)

si._worker.shutdown()
app.exitQgis()

print(f"\n{len(passed)} passed, {len(failed)} failed")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
sys.exit(0)
