"""DEF-9 live half: with a real QgsApplication the collector's own connection (tools/collect_evidence.setup) receives a message logged through
QgsMessageLog, in the form snap() writes it. This is the path that delivered nothing on the tester's QGIS 4.2.3."""
import sys
import tempfile
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
class TestCollectorReceivesRealLogMessages(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)

    def test_a_logged_message_reaches_the_collector_with_tag_level_and_text(self):
        from qgis.core import Qgis, QgsMessageLog
        import collect_evidence as ce
        ce._STATE.update({"lines": [], "connected": False, "out": None})
        ce.setup(tempfile.mkdtemp())
        QgsMessageLog.logMessage("collector probe line", "CartogenAI", Qgis.MessageLevel.Info)
        QgsMessageLog.logMessage("collector probe warning", "Agent", Qgis.MessageLevel.Warning)
        got = {(tag, message): level for _t, tag, level, message in ce._STATE["lines"]}
        print(f"COLLECTORLOG {len(ce._STATE['lines'])} lines: {got}")
        self.assertIn(("CartogenAI", "collector probe line"), got, got)
        self.assertEqual(got[("Agent", "collector probe warning")], 1, got)


if __name__ == "__main__":
    unittest.main()
