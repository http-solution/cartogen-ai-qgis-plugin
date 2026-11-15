"""Guards from the 2026-10-12 processing-cost audit (docs/PROCESSING_COST_AUDIT_2026-10-12.md): a tool that waits on the network must not run on
the GUI thread, a batch tool must honour Stop, and the audit script itself keeps working."""
import importlib.util
import os
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _audit_module():
    spec = importlib.util.spec_from_file_location("audit_processing_cost", os.path.join(ROOT, "tools", "audit_processing_cost.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestNetworkToolsStayOffTheGuiThread(unittest.TestCase):
    def test_every_tool_that_calls_the_network_is_routed_off_the_gui_thread(self):
        from cartogen_ai.core.agent.agent_orchestrator import NETWORK_ONLY_TOOLS, TWO_PHASE_TOOLS
        rows = _audit_module().audit()
        on_gui_thread = sorted(r["tool"] for r in rows if r["network"] and r["tool"] not in NETWORK_ONLY_TOOLS | TWO_PHASE_TOOLS)
        self.assertEqual(on_gui_thread, [], "these tools wait on the network on QGIS's GUI thread; add them to NETWORK_ONLY_TOOLS "
                                            "(no QGIS objects) or TWO_PHASE_TOOLS (fetch off-thread, layer on the GUI thread)")


class TestGeocodeBatch(unittest.TestCase):
    def test_stop_ends_the_batch_between_lookups_and_returns_what_was_done(self):
        from cartogen_ai.core.agent.tools import system_tools as st
        calls = []

        def fake_one(name):
            calls.append(name)
            return {"cached": True, "lat": 1.0, "lon": 2.0}
        stops = iter([False, False, True])
        with patch.object(st, "_geocode_one", fake_one), patch("cartogen_ai.core.agent.cancel_signal.is_cancelled", lambda: next(stops)):
            out = st.geocode_batch(["a", "b", "c", "d"])
        self.assertFalse(out["success"])
        self.assertEqual(calls, ["a", "b"])
        self.assertEqual(len(out["results"]), 2)
        self.assertIn("Stopped by the user after 2 of 4", out["error"])


class TestAuditScript(unittest.TestCase):
    def test_it_finds_the_registered_tools_and_ranks_them(self):
        rows = _audit_module().audit()
        self.assertGreater(len(rows), 150)
        self.assertEqual([r["score"] for r in rows], sorted((r["score"] for r in rows), reverse=True))
        by_name = {r["tool"]: r for r in rows}
        self.assertTrue(by_name["travel_time_matrix"]["background"])          # runs its algorithm through the background runner

    def test_scoring_rewards_guards(self):
        m = _audit_module()
        base = {"loops": 2, "get_features": 2, "processing_run": 1, "sleep": 0, "raster_reads": 0, "network": False, "spatial_index": False,
                "background": False, "cancel": False, "caps": False}
        self.assertLess(m.score({**base, "background": True, "cancel": True, "caps": True}), m.score(base))


if __name__ == "__main__":
    unittest.main()
