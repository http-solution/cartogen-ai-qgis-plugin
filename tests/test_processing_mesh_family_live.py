"""Live run of every mesh-family algorithm on the allow-list (gap-closing package), each in its own process via tests/_mesh_probe.py with a
timeout. Prints one MESHRESULT line per algorithm. A failing algorithm leaves the allow-list and goes into MESH_REJECTED with its error.
Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    import qgis.core  # noqa: F401
    LIVE = True
except ImportError:
    LIVE = False

from cartogen_ai.core.agent.tools._processing_allowlist import MESH_FAMILY

TIMEOUT_SECONDS = 90


def _run_one(alg_id):
    import json
    import os
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        done = subprocess.run([sys.executable, "-m", "tests._mesh_probe", alg_id], cwd=root, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return False, f"HUNG for more than {TIMEOUT_SECONDS}s"
    for line in reversed(done.stdout.splitlines()):
        if line.startswith("RESULT "):
            result = json.loads(line[7:])
            return bool(result.get("ok")), str(result.get("error", ""))
    return False, f"no result (exit code {done.returncode}); stderr tail: {done.stderr[-300:]!r}"


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestMeshFamilyRuns(unittest.TestCase):
    def test_every_algorithm_runs(self):
        from concurrent.futures import ThreadPoolExecutor
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        ids = sorted(MESH_FAMILY)
        with ThreadPoolExecutor(max_workers=3) as pool:
            outcomes = dict(zip(ids, pool.map(_run_one, ids), strict=True))
        for alg_id, (ok, detail) in sorted(outcomes.items()):
            print(f"MESHRESULT {alg_id} {'ok' if ok else 'FAILED'} {detail[:300]}")
        failures = {k: v[1] for k, v in outcomes.items() if not v[0]}
        self.assertEqual(failures, {}, "\n" + "\n".join(f"{k}: {v}" for k, v in sorted(failures.items())))


if __name__ == "__main__":
    unittest.main()
