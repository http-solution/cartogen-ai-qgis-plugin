"""PLAN-055 gap A, the owner's choice (2026-11-03): a confirmed fetch still downloads on the UI thread, so QGIS can pause until it finishes. Instead of
moving the Apply path to a worker, the confirmation card for a download tool says so before the person presses Apply. Offline; nothing is fetched."""
import unittest
from unittest.mock import MagicMock

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent.task_manager import AgentTaskManager
from cartogen_ai.core.models import egress_gate

DECISION = {"action": "block", "layers": {"smoke_zones": "tagged RESTRICTED"}, "result": {"error": "blocked"}, "warning": "w"}
PAUSE = "QGIS may pause"


def make_agent():
    agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
    agent.task_manager = AgentTaskManager()
    agent.memory_manager = MagicMock()
    agent._last_tool_call = None
    agent._egress_gate_decision = lambda name, args: DECISION
    return agent


class TestPreviewRequiredWording(unittest.TestCase):
    def test_a_download_card_says_qgis_may_pause_until_it_finishes(self):
        card = egress_gate.preview_required("fetch_worldpop_population", {"iso3": "YEM"}, DECISION, downloads=True)
        self.assertIn(PAUSE, card["rationale"])
        self.assertIn("download", card["rationale"])

    def test_the_default_card_is_unchanged(self):
        self.assertNotIn(PAUSE, egress_gate.preview_required("buffer_analysis", {}, DECISION)["rationale"])
        self.assertEqual(egress_gate.preview_required("buffer_analysis", {}, DECISION),
                         egress_gate.preview_required("buffer_analysis", {}, DECISION, downloads=False))

    def test_the_rest_of_the_card_is_kept(self):
        card = egress_gate.preview_required("fetch_worldpop_population", {"iso3": "YEM"}, DECISION, downloads=True)
        self.assertTrue(card["egress_override"])
        self.assertEqual(card["arguments"], {"iso3": "YEM"})
        self.assertIn("smoke_zones", card["rationale"])
        self.assertIn("Confirming overrides that block for this one call only", card["rationale"])


class TestTheCardTheAgentRegisters(unittest.TestCase):
    def test_every_download_tool_gets_the_warning_on_its_card(self):
        for name in sorted(agent_mod.TWO_PHASE_TOOLS):
            agent = make_agent()
            blocked, _egress, _applied = agent._egress_precheck(name, {"x": 1}, {"x": 1}, False)
            self.assertIn(PAUSE, blocked["rationale"], name)

    def test_an_ordinary_tool_gets_no_download_warning(self):
        agent = make_agent()
        blocked, _egress, _applied = agent._egress_precheck("buffer_analysis", {"layer_name": "smoke_zones"}, {"layer_name": "smoke_zones"}, False)
        self.assertNotIn(PAUSE, blocked["rationale"])


if __name__ == "__main__":
    unittest.main()
