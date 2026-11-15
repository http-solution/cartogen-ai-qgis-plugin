"""DEF-20 (PLAN-033 item 1): add_layer_from_path offers `sublayer` and the tool honours it, but the orchestrator's own branch for the tool
never forwarded it, so asking for one named layer of a GeoPackage always opened the first. The tool-level behaviour is covered live in
tests/test_data_source_tools_live.py; this drives the orchestrator branch itself (the tool function is replaced, no QGIS needed)."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.agent_orchestrator import CartogenAi


def _agent():
    a = CartogenAi.__new__(CartogenAi)
    a._run_current_turn_on_main_thread = lambda fn, arg: fn(arg)
    a._log_tool_success = MagicMock()
    return a


class TestSublayerReachesTheTool(unittest.TestCase):
    def _call(self, arguments):
        tool = MagicMock(return_value={"success": True})
        with patch("cartogen_ai.core.agent.tools.vector_tools.add_layer_from_path", tool), \
             patch("cartogen_ai.core.agent.tools.vector_tools._prefetch_url_to_temp", lambda p: (p, False)):
            _agent()._execute_two_phase_tool("add_layer_from_path", arguments)
        return tool

    def test_sublayer_is_forwarded(self):
        tool = self._call({"file_path": "/data/places.gpkg", "sublayer": "roads", "layer_name": "My roads"})
        tool.assert_called_once_with("/data/places.gpkg", "My roads", None, "roads")

    def test_no_sublayer_still_means_none(self):
        tool = self._call({"file_path": "/data/places.gpkg"})
        tool.assert_called_once_with("/data/places.gpkg", None, None, None)


if __name__ == "__main__":
    unittest.main()
