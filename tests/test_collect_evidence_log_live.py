"""DEF-9 live half. On the tester's QGIS 4.2.3 the collector's log files were empty although its signal was connected. A first live run (CI 42639289496, QGIS
4.2.2) with the collector's own connection received NO line at all after a real QgsMessageLog.logMessage, so a bad `int(level)` was not the only fault.

This test tries every plausible way to connect to QgsApplication.messageLog().messageReceived, logs one message, and prints which forms received it (the
COLLECTORFORMS line in the CI output). It fails only when NO form receives anything; the collector then has to use one that does."""
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

    def test_which_connection_forms_receive_a_real_log_message(self):
        from qgis.core import Qgis, QgsApplication, QgsMessageLog
        log = QgsApplication.messageLog()
        print(f"COLLECTORFORMS messageLog object: {log!r}, signal: {log.messageReceived!r}")
        seen = {}

        def make(name):
            def handler(*args):
                seen.setdefault(name, []).append(tuple(str(a) for a in args))
            return handler

        results = {}
        signal = log.messageReceived
        forms = {
            "explicit_enum": lambda: signal[str, str, Qgis.MessageLevel],
            "default": lambda: signal,
            "explicit_int": lambda: signal[str, str, int],
            "signature_text": lambda: signal["QString", "QString", "Qgis::MessageLevel"],
            "explicit_bool": lambda: signal[bool],
        }
        for name, pick in forms.items():
            try:
                pick().connect(make(name))
                results[name] = "connected"
            except Exception as e:                      # which forms refuse to connect is part of the answer
                results[name] = f"connect raised {type(e).__name__}: {str(e)[:80]}"
        QgsMessageLog.logMessage("collector probe line", "CartogenAI", Qgis.MessageLevel.Info)
        QgsMessageLog.logMessage("collector probe warning", "Agent", Qgis.MessageLevel.Warning, True)
        for name in forms:
            print(f"COLLECTORFORMS {name}: {results[name]}; received {len(seen.get(name, []))}: {seen.get(name, [])[:2]}")
        self.assertTrue(seen, f"no connection form received any message: {results}")

    def test_the_collector_records_a_real_log_message_with_tag_level_and_text(self):
        from qgis.core import Qgis, QgsMessageLog
        import collect_evidence as ce
        ce._STATE.update({"lines": [], "connected": False, "out": None})
        ce.setup(tempfile.mkdtemp())
        QgsMessageLog.logMessage("collector real line", "CartogenAI", Qgis.MessageLevel.Info)
        QgsMessageLog.logMessage("collector real warning", "Agent", Qgis.MessageLevel.Warning)
        got = {(tag, message): level for _t, tag, level, message in ce._STATE["lines"]}
        print(f"COLLECTORLOG {len(ce._STATE['lines'])} lines: {got}")
        self.assertIn(("CartogenAI", "collector real line"), got, got)
        self.assertEqual(got[("Agent", "collector real warning")], 1, got)


if __name__ == "__main__":
    unittest.main()
