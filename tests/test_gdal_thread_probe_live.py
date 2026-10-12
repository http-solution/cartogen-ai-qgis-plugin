"""INVESTIGATION, not a regression test (2026-10-12): runs tests/manual_live_checks/gdal_thread_probe.py in fresh processes and PRINTS what happened,
so the QGIS 4.2.2 CI log shows whether and where a Python-implemented Processing algorithm (gdal:slope) crashes on a worker thread. It never fails
on a crash; it fails only if the probe cannot be run at all. Remove (or move to EXCLUDED) once the cause is recorded."""
import os
import subprocess
import sys
import unittest

try:
    import qgis.core  # noqa: F401
    LIVE = True
except ImportError:
    LIVE = False

PROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual_live_checks", "gdal_thread_probe.py")
ATTEMPTS = 4
RUNS = [("flags", "nogui", 1), ("sync", "nogui", 2), ("bg_current", "nogui", 3), ("bg_current", "gui", 3), ("bg_cpp_feedback", "nogui", 3),
        ("bg_cpp_feedback", "gui", 3), ("bg_poll", "nogui", 3), ("bg_keepalive", "nogui", 3)]


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestGdalThreadProbe(unittest.TestCase):
    def test_print_the_evidence(self):
        lines = ["", "=" * 78, "GDAL THREAD PROBE (gdal:slope on a worker thread), fresh process per attempt"]
        summary = []
        for variant, gui, repeats in RUNS:
            crashes = 0
            for attempt in range(ATTEMPTS if variant != "flags" else 1):
                try:
                    p = subprocess.run([sys.executable, PROBE, variant, gui, str(repeats)], capture_output=True, text=True, timeout=240, check=False)
                    code, out, err = p.returncode, p.stdout, p.stderr
                except subprocess.TimeoutExpired as e:
                    code, out, err = "TIMEOUT", (e.stdout or ""), (e.stderr or "")
                    out = out if isinstance(out, str) else out.decode("utf-8", "replace")
                    err = err if isinstance(err, str) else err.decode("utf-8", "replace")
                probe_lines = [ln for ln in out.splitlines() if ln.startswith("PROBE")]
                bad = code not in (0,)
                crashes += bool(bad)
                lines.append(f"--- {variant} {gui} attempt {attempt}: exit {code}")
                lines.extend("    " + ln for ln in probe_lines)
                if bad:
                    lines.append("    stderr tail (faulthandler prints the Python stack of the crashing thread):")
                    lines.extend("      " + ln for ln in err.strip().splitlines()[-45:])
            summary.append(f"{variant:16s} {gui:6s} crashed in {crashes} of {ATTEMPTS if variant != 'flags' else 1} attempts")
        lines.append("SUMMARY")
        lines.extend("  " + s for s in summary)
        lines.append("=" * 78)
        print("\n".join(lines), flush=True)


if __name__ == "__main__":
    unittest.main()
