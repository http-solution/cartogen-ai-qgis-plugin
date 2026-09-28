"""MANUAL, live-QGIS-only. Confirms a hung script hits the timeout and the
worker is killed and successfully respawned for the next call, rather than
leaving the isolation path permanently wedged."""
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

from qgis.core import QgsApplication, QgsProject  # noqa: E402

app = QgsApplication([], False)
app.initQgis()

from cartogen_ai.core.agent.services import script_isolation as si  # noqa: E402

si._JOB_TIMEOUT_SECONDS = 2  # module-level constant used as submit()'s default
QgsProject.instance().clear()

hung_script = """
def run():
    while True:
        pass
"""

t0 = time.perf_counter()
result = si.run_isolated_script(hung_script)
elapsed = time.perf_counter() - t0
print("hung script result:", result, f"{elapsed:.1f}s")
assert "error" in result and "timeout" in result["error"].lower(), "expected a timeout error"
assert elapsed < 5, "should have been killed at ~2s, not run to completion"

# The worker should have been killed; the next call must respawn cleanly.
ok_script = "def run():\n    return 42\n"
result2 = si.run_isolated_script(ok_script)
print("post-timeout recovery call:", result2)
assert result2.get("success") is True and result2.get("result") == 42, "worker did not recover after a timeout kill"

print("PASS: timeout + recovery")

si._worker.shutdown()
app.exitQgis()
