"""PLAN-023 R11-5 (PLAN-006 E2b probe and E2a): do the 9 plot algorithms and the 4 file-information algorithms run in the QGIS image CI uses, and what do they write? A probe, not a feature
test: it always passes and records one line per id starting 'PLOTPROBE' in the live job's log (and in $CARTOGEN_LIVE_ARTIFACTS/plot_info_probe.txt when that folder is set), because the answer
decides which tools get built next and which ids are declined with the reason. Each id runs in its own process with a timeout so a hang or a crash is reported by name.
Written without a QGIS install: CI's first run is where the answers come from."""
import os
import unittest

try:
    import qgis.core  # noqa: F401
    LIVE = True
except ImportError:
    LIVE = False

IDS = ("qgis:barplot", "qgis:boxplot", "qgis:meanandstandarddeviationplot", "qgis:polarplot", "qgis:rasterlayerhistogram", "qgis:scatter3dplot", "qgis:vectorlayerhistogram",
       "qgis:vectorlayerscatterplot", "native:generateelevationprofileimage", "gdal:gdalinfo", "gdal:ogrinfo", "gdal:ogrinfojson", "gdal:dataset_identify")
TIMEOUT_SECONDS = 90


def _run_one(alg_id):
    """The probe line for one id, or a line saying it hung or crashed. Pure subprocess plumbing."""
    import json
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        done = subprocess.run([sys.executable, "-m", "tests._plot_probe", alg_id], cwd=root, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return "PLOTPROBE " + json.dumps({"id": alg_id, "ok": False, "error": f"HUNG for more than {TIMEOUT_SECONDS}s"})
    for line in reversed(done.stdout.splitlines()):
        if line.startswith("PLOTPROBE "):
            return line
    return "PLOTPROBE " + json.dumps({"id": alg_id, "ok": False, "error": f"no result (exit code {done.returncode}); stderr tail: {done.stderr[-300:]!r}"})


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestPlotAndInfoProbe(unittest.TestCase):
    def test_record_what_each_plot_and_info_algorithm_does(self):
        lines = [_run_one(alg_id) for alg_id in IDS]
        for line in lines:
            print(line)
        folder = os.environ.get("CARTOGEN_LIVE_ARTIFACTS")
        if folder:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "plot_info_probe.txt"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        self.assertEqual(len(lines), len(IDS))


if __name__ == "__main__":
    unittest.main()
