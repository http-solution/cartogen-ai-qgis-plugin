"""Live run of every geometry-family algorithm on the allow-list (M6a), built from each algorithm's OWN parameter definitions: a source
parameter gets a suitable test layer, numbers / enums / booleans their default, fields a matching field, extents and points a fixed
value. The call goes through run_allowlisted_processing_algorithm, so the wrapper (unknown-parameter check, memory-only sinks, layer
resolution) is exercised too. A failure names the algorithm and the error; fix the call here only if the call is wrong, otherwise the
algorithm leaves the allow-list and goes into GEOMETRY_NOT_YET with the reason. Written without a QGIS install: CI's first run is
its first execution."""
import unittest

try:
    import qgis.core  # noqa: F401
    LIVE = True
except ImportError:
    LIVE = False

from cartogen_ai.core.agent.tools._processing_allowlist import GEOMETRY_FAMILY
from tests._processing_live_rows import GEOMETRY_NOT_YET

TIMEOUT_SECONDS = 60


def _run_one(alg_id):
    """(ok, detail) for one algorithm run in its own process; a hang, a crash or a missing result line is a failure with its reason."""
    import json
    import os
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        done = subprocess.run([sys.executable, "-m", "tests._geometry_probe", alg_id], cwd=root, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as e:
        return False, f"HUNG for more than {TIMEOUT_SECONDS}s (last output: {str(e.stdout or '')[-200:]!r})"
    for line in reversed(done.stdout.splitlines()):
        if line.startswith("RESULT "):
            result = json.loads(line[7:])
            return bool(result.get("ok")), str(result.get("error", ""))
    return False, f"no result (exit code {done.returncode}); stderr tail: {done.stderr[-300:]!r}"


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestGeometryFamilyRuns(unittest.TestCase):
    def test_every_algorithm_runs_on_at_least_one_geometry_type(self):
        from concurrent.futures import ThreadPoolExecutor
        ids = sorted(set(GEOMETRY_FAMILY) - set(GEOMETRY_NOT_YET))
        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = dict(zip(ids, pool.map(_run_one, ids), strict=True))
        failures = {k: v[1] for k, v in outcomes.items() if not v[0]}
        self.assertEqual(failures, {}, "\n" + "\n".join(f"{k}: {v}" for k, v in sorted(failures.items())))


if __name__ == "__main__":
    unittest.main()
