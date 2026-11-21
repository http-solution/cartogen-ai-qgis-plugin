"""LR-21 follow-up: generate_situation_dashboard runs its three HTTP fetches off the GUI thread (TWO_PHASE_TOOLS), then adds layers and writes the HTML
on the GUI thread. It used to call the three fetch tools whole, so all three fetches blocked QGIS's GUI thread."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent import agent_orchestrator
from cartogen_ai.core.agent.tools import export_tools, hazard_monitoring_tools as hz

BBOX = [34.9, 30.9, 35.2, 31.3]
OK = {"layer_name": "L", "detection_count": 1, "event_count": 1, "alert_count": 1}


class TestRouting(unittest.TestCase):
    def test_the_dashboard_is_a_two_phase_tool(self):
        self.assertIn("generate_situation_dashboard", agent_orchestrator.TWO_PHASE_TOOLS)

    def test_the_network_phase_never_touches_the_layer_steps(self):
        calls = []
        with patch.object(hz, "fetch_nasa_active_fires_network_phase", side_effect=lambda *a: calls.append("fires") or {"success": True}), \
                patch.object(hz, "fetch_nasa_eonet_events_network_phase", side_effect=lambda *a: calls.append("eonet") or {"success": True}), \
                patch.object(hz, "fetch_gdacs_disaster_alerts_network_phase", side_effect=lambda *a: calls.append("gdacs") or {"success": True}), \
                patch.object(hz, "add_nasa_active_fires_layer_main_thread_phase", side_effect=AssertionError("layer step on the network thread")), \
                patch.object(hz, "resolve_output_path", side_effect=AssertionError("project read on the network thread")):
            out = hz.generate_situation_dashboard_network_phase(BBOX, include_eonet=False)
        self.assertEqual(calls, ["fires", "gdacs"])
        self.assertEqual(set(out["fetched"]), {"fires", "disasters"})

    def test_a_bad_bbox_is_refused_before_any_fetch(self):
        with patch.object(hz, "fetch_nasa_active_fires_network_phase", side_effect=AssertionError("fetched")):
            self.assertIn("error", hz.generate_situation_dashboard_network_phase([1, 2, 3]))
            self.assertIn("error", hz.generate_situation_dashboard_network_phase(None))


class TestMainThreadPhase(unittest.TestCase):
    def test_result_shape_and_source_warnings(self):
        captured = {}

        def fake_dashboard(layers_config, **kwargs):
            captured["layers"], captured["kwargs"] = layers_config, kwargs
            return {"success": True}
        fetched = {"fetched": {"fires": {"error": "no key"}, "eonet": {"success": True}, "disasters": {"success": True}}}
        with patch.object(hz, "add_nasa_active_fires_layer_main_thread_phase", return_value={"error": "no key"}), \
                patch.object(hz, "add_nasa_eonet_events_layer_main_thread_phase", return_value=dict(OK)), \
                patch.object(hz, "add_gdacs_disaster_alerts_layer_main_thread_phase", return_value={"layer_name": "G", "alert_count": 0}), \
                patch.object(export_tools, "generate_html_dashboard", fake_dashboard):
            out = hz.build_situation_dashboard_main_thread_phase(fetched, None, "T")
        self.assertEqual(out, {"success": True, "source_warnings": ["Active fires: no key"]})
        self.assertEqual([c["layer_name"] for c in captured["layers"]], ["L"])
        self.assertEqual(captured["kwargs"]["title"], "T")

    def test_no_data_error_lists_the_source_errors(self):
        with patch.object(hz, "add_nasa_active_fires_layer_main_thread_phase", return_value={"error": "boom"}):
            out = hz.build_situation_dashboard_main_thread_phase({"fetched": {"fires": {}}})
        self.assertEqual(out, {"error": "No hazard data available to build a dashboard -- Active fires: boom"})

    def test_a_network_phase_error_passes_through(self):
        self.assertEqual(hz.build_situation_dashboard_main_thread_phase({"error": "x"}), {"error": "x"})


class TestAuditFollowsHelpers(unittest.TestCase):
    def test_the_audit_sees_the_network_through_two_helper_levels(self):
        import importlib.util
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location("audit_processing_cost", os.path.join(root, "tools", "audit_processing_cost.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        row = next(r for r in mod.audit() if r["tool"] == "generate_situation_dashboard")
        self.assertTrue(row["network"])


if __name__ == "__main__":
    unittest.main()
