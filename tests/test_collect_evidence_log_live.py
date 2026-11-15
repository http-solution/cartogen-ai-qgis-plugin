"""DEF-9 live half. On the tester's QGIS 4.2.3 the evidence collector's log files were empty although its signal was connected. A first live run (CI
42639289496, QGIS 4.2.2) saw no line reach the collector's messageReceived connection, and a second showed that a probe passing on the bool form proves nothing
(the CI log hides prints of passing tests). So:

the assertion is on the path that does not depend on the signal: a line logged through the plugin's own logger comes back from the collector's `_plugin_lines`.
A third probe that connected every messageReceived signal form and wrote collector_signal_forms.txt segfaulted QGIS 4.2.2 in CI (run 42643147052, exit 139), so it was removed."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

try:
    import qgis.core  # noqa: F401
    LIVE = True
except ImportError:
    LIVE = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestCollectorSeesTheLogInRealQgis(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)

    def test_a_plugin_log_line_reaches_the_collector_and_the_log_file_is_never_silent(self):
        import collect_evidence as ce
        from cartogen_ai.core import logger
        ce._STATE.update({"lines": [], "connected": False, "out": None})
        ce.setup(tempfile.mkdtemp())
        since = time.time() - 0.01
        logger.log_info("collector probe line", tag="CartogenAI")
        logger.log_warning("collector probe warning", tag="Agent")
        lines = ce._plugin_lines(since)
        self.assertTrue(any("collector probe line" in line for line in lines), lines)
        self.assertTrue(any("[Agent] WARNING collector probe warning" in line for line in lines), lines)
        text = ce._log_file_text(lines, ce._STATE.get("forms_connected", 0))
        self.assertIn("collector probe line", text)


if __name__ == "__main__":
    unittest.main()
