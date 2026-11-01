"""find_tools additions are capped per lookup and per turn (a real 24-call run kept about 37 extra schemas and hit its 450,000-token budget)."""
import unittest

from cartogen_ai.core.agent.agent_orchestrator import (
    MAX_FOUND_TOOLS_PER_CALL, MAX_FOUND_TOOLS_PER_TURN, CartogenAi)
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA

NAMES = [t["function"]["name"] for t in TOOLS_SCHEMA]


def _schemas(names):
    return [t for t in TOOLS_SCHEMA if t["function"]["name"] in set(names)]


class TestFoundToolsAreCapped(unittest.TestCase):
    def test_one_lookup_keeps_at_most_the_per_call_limit(self):
        base = _schemas(NAMES[:28])
        out = CartogenAi._offer_found_tools(base, {"tool_names": NAMES[40:48]}, {t["function"]["name"] for t in base})
        self.assertEqual(len(out) - len(base), MAX_FOUND_TOOLS_PER_CALL)

    def test_repeated_lookups_stop_at_the_per_turn_limit(self):
        base = _schemas(NAMES[:28])
        base_names = {t["function"]["name"] for t in base}
        tools = base
        for start in range(40, 120, 6):                      # more lookups than the limit allows
            tools = CartogenAi._offer_found_tools(tools, {"tool_names": NAMES[start:start + 6]}, base_names)
        self.assertEqual(len(tools) - len(base), MAX_FOUND_TOOLS_PER_TURN)

    def test_a_tool_already_offered_is_not_added_twice_and_does_not_use_the_budget(self):
        base = _schemas(NAMES[:28])
        base_names = {t["function"]["name"] for t in base}
        out = CartogenAi._offer_found_tools(base, {"tool_names": NAMES[:5] + NAMES[40:44]}, base_names)
        self.assertEqual(len(out) - len(base), 4)
        self.assertEqual(len({t["function"]["name"] for t in out}), len(out))

    def test_without_base_names_the_whole_turn_limit_is_available(self):
        out = CartogenAi._offer_found_tools(_schemas(NAMES[:10]), {"tool_names": NAMES[40:45]})
        self.assertEqual(len(out) - 10, 5)

    def test_limits_are_small_enough_to_matter(self):
        self.assertLessEqual(MAX_FOUND_TOOLS_PER_TURN, 15)
        self.assertLessEqual(MAX_FOUND_TOOLS_PER_CALL, 6)


class TestHospitalTaskFetchesData(unittest.TestCase):
    def test_task_6_02_starts_with_a_data_fetch_tool(self):
        """Owner run 2026-11-01: 'Prefer these tools, in order: add_layer_from_path, apply_categorized_style, zoom_to_layer' for a request
        with no local file steered the model away from downloading the hospitals (1.02 and 1.05 already start with fetch_osm_features)."""
        from cartogen_ai.core.agent import task_register
        task = task_register.by_id("6.02")
        self.assertEqual(task["tools"][0], "fetch_osm_features")


if __name__ == "__main__":
    unittest.main()
