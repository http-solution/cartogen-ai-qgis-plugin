"""Live run of every GRASS-family algorithm on the allow-list (M9), each in its own process via tests/_grass_probe.py with a timeout.
Needs the GRASS provider (present in CI's QGIS image, absent on most desktops): without it the test is skipped. A failure names the
algorithm and the error; the algorithm then leaves the allow-list and goes into GRASS_REJECTED with that error. Prints one `GRASSRESULT`
line per algorithm so the log shows which ran. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    import qgis.core  # noqa: F401
    LIVE = True
except ImportError:
    LIVE = False

from cartogen_ai.core.agent.tools._processing_allowlist import GRASS_FAMILY
from tests._processing_live_rows import GRASS_REJECTED  # noqa: F401

TIMEOUT_SECONDS = 120


def _run_one(alg_id):
    """(ok, detail) for one algorithm run in its own process; a hang, a crash or a missing result line is a failure with its reason."""
    import json
    import os
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        done = subprocess.run([sys.executable, "-m", "tests._grass_probe", alg_id], cwd=root, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as e:
        return False, f"HUNG for more than {TIMEOUT_SECONDS}s (last output: {str(e.stdout or '')[-200:]!r})"
    for line in reversed(done.stdout.splitlines()):
        if line.startswith("RESULT "):
            result = json.loads(line[7:])
            return bool(result.get("ok")), str(result.get("error", ""))
    return False, f"no result (exit code {done.returncode}); stderr tail: {done.stderr[-300:]!r}"


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestGrassFamilyRuns(unittest.TestCase):
    def test_every_algorithm_runs(self):
        from concurrent.futures import ThreadPoolExecutor
        from qgis.core import QgsApplication
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        if QgsApplication.processingRegistry().providerById("grass") is None:
            self.skipTest("this QGIS has no GRASS provider")
        ids = sorted(GRASS_FAMILY)
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = dict(zip(ids, pool.map(_run_one, ids), strict=True))
        for alg_id, (ok, detail) in sorted(outcomes.items()):
            print(f"GRASSRESULT {alg_id} {'ok' if ok else 'FAILED'} {detail[:300]}")
        failures = {k: v[1] for k, v in outcomes.items() if not v[0]}
        self.assertEqual(failures, {}, "\n" + "\n".join(f"{k}: {v}" for k, v in sorted(failures.items())))


if __name__ == "__main__":
    unittest.main()
