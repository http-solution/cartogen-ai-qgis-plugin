"""Smoke row C28 driven in a real QGIS (offscreen; written 2026-11-26 to find why a 5 MB boundary download added no layer): the large-download card, Cancel, a second card, Apply,
a second Apply of the same boundary, and what is in the project afterwards. Needs internet. Run it inside the QGIS 4.2.2 image CI uses, with the repository mounted, for example:
docker run --rm --network host -e QT_QPA_PLATFORM=offscreen -v "$PWD":/repo:ro qgis/qgis@<digest from .github/workflows/tests.yml> python3 /repo/tests/manual_live_checks/c28_apply_flow.py
Not a unit test (it uses the network); the behaviour it exercised is pinned by tests/test_net_live.py and tests/test_boundary_no_layer.py. Findings: docs/BUG_TRACKER.md BUG-2026-11-26-3 and -5."""
# ruff: noqa: E402
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)
from qgis.core import QgsApplication, QgsProject, QgsSettings

app = QgsApplication([b"c28"], False)
QgsApplication.setPrefixPath("/usr", True)
app.initQgis()
plugins = os.path.join(QgsApplication.pkgDataPath(), "python", "plugins")
sys.path.insert(0, plugins)
from cartogen_ai.infrastructure.settings_keys import SETTINGS_LOCAL_DATA_ASK_ABOVE_MB

QgsSettings().setValue(SETTINGS_LOCAL_DATA_ASK_ABOVE_MB, 1)      # the card's step: ask above 1 MB
import cartogen_ai.core.agent.agent_orchestrator as agent_mod

lines = []
orig = agent_mod.log_event
def spy(event, *a, **k):
    if event == "tool_call" and k.get("via") == "apply":
        lines.append(dict(k, event=event))
    return orig(event, *a, **k)
agent_mod.log_event = spy

QgsProject.instance().clear()
agent = agent_mod.CartogenAi()
args = json.dumps({"iso3": "YEM", "admin_level": "ADM2"})

def layers(): return [layer.name() for layer in QgsProject.instance().mapLayers().values()]

print("STEP 1 request -> card")
r = agent._execute_tool("fetch_geoboundaries", args)
print("  RAW:", str(r)[:600])
print("  status:", r.get("status"), "size_mb:", r.get("size_mb"))
print("  layers after card:", layers())
pend = [t for t in agent.task_manager.tasks if t.get("status") == "PREVIEW_READY" and t.get("pending_tool")]
print("  pending Apply tasks:", [(t["id"], t["pending_tool"]) for t in pend])

print("STEP 2 Cancel (what the card's Cancel link does)")
t = pend[0]
agent.task_manager.update_task(t["id"], "FAILED", "Cancelled by User")
print("  layers after cancel:", layers())

print("STEP 3 same request again -> card -> Apply")
r = agent._execute_tool("fetch_geoboundaries", args)
print("  second card status:", r.get("status"))
pend = [t for t in agent.task_manager.tasks if t.get("status") == "PREVIEW_READY" and t.get("pending_tool")]
t = max(pend, key=lambda x: x.get("updated_at", ""))
t0 = time.time()
res = agent.execute_confirmed(t["pending_tool"], t.get("pending_args", {}))
print("  Apply took %.1f s" % (time.time() - t0))
print("  Apply result keys:", {k: (str(v)[:120]) for k, v in res.items() if k in ("success", "error", "layer_name", "boundary")})
print("  layers after Apply:", layers())
for layer in QgsProject.instance().mapLayers().values():
    print("  layer:", layer.name(), "valid:", layer.isValid(), "features:", layer.featureCount(), "crs:", layer.crs().authid())
print("  apply log lines:", lines)

print("STEP 4 Apply a SECOND time on the same boundary (the repeat-fetch shape, W2/W3)")
t0 = time.time()
res2 = agent.execute_confirmed("fetch_geoboundaries", {"iso3": "YEM", "admin_level": "ADM2"})
print("  second Apply took %.1f s" % (time.time() - t0))
print("  second Apply result:", {k: str(v)[:200] for k, v in res2.items() if k in ("success", "error", "layer_name")})
print("  layers now:", layers())
for layer in QgsProject.instance().mapLayers().values():
    print("  layer:", layer.name(), "valid:", layer.isValid(), "features:", layer.featureCount())
app.exitQgis()
