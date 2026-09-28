"""MANUAL, live-QGIS-only. Confirms the worker is persistent (not respawned per
call) and measures real per-call latency after warm-up, to check against the
scoping doc's derived (not separately measured) ~0.6s/call estimate."""
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

from qgis.core import QgsApplication, QgsProject  # noqa: E402

app = QgsApplication([], False)
app.initQgis()

from cartogen_ai.core.agent.services import script_isolation as si  # noqa: E402

QgsProject.instance().clear()

script = """
def run():
    return 1 + 1
"""

t0 = time.perf_counter()
result = si.run_isolated_script(script)
t_cold = time.perf_counter() - t0
print("cold call:", result, f"{t_cold:.3f}s")
pid_after_first = si._worker._proc.pid

times = []
for _ in range(5):
    t0 = time.perf_counter()
    result = si.run_isolated_script(script)
    times.append(time.perf_counter() - t0)
pid_after_warm = si._worker._proc.pid

print("warm calls:", [f"{t:.3f}s" for t in times])
print("worker pid stayed the same across calls:", pid_after_first == pid_after_warm, pid_after_first, pid_after_warm)

si._worker.shutdown()
app.exitQgis()
