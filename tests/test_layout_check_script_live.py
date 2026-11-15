"""PLAN-021 WP-G, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): tools/layout_check_script.py,
the model-free check the owner runs on a real machine, runs here first. Every check must pass on CI's fonts; what CI cannot prove is the owner's
fonts, which is why the script exists."""
import importlib.util
import json
import os
import tempfile
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "layout_check_script.py")


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestLayoutCheckScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def test_every_check_runs_and_passes_and_the_files_are_written(self):
        spec = importlib.util.spec_from_file_location("layout_check_script", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            summary = module.run(folder, quiet=True)
            self.assertEqual(summary["failed"], [], json.dumps([c for c in summary["checks"] if not c["ok"]], indent=1, default=str))
            self.assertGreaterEqual(len(summary["checks"]), 11)
            for name in ("layout_check.json", "layout_check.txt"):
                self.assertTrue(os.path.isfile(os.path.join(folder, name)), name)
            written = {f for f in os.listdir(folder) if f.endswith((".pdf", ".png"))}
            self.assertTrue({"footer_default.pdf", "big_map_A3.pdf", "profile_test.pdf", "disclaimer_test.pdf"} <= written, sorted(written))
            with open(os.path.join(folder, "layout_check.json"), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["passed"], len(summary["checks"]))


if __name__ == "__main__":
    unittest.main()
