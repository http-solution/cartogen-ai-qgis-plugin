"""PLAN-023 R10-2: the registration contract of set_conditional_formatting, set_map_tip and add_feature_action (offline: no QGIS needed). The checks are in test_display_rules.py and the
real-layer behaviour in test_layer_display_tools_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA

NAMES = ("set_conditional_formatting", "set_map_tip", "add_feature_action")


def schema(name):
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == name)


class TestRegistration(unittest.TestCase):
    def test_all_three_are_registered_with_their_required_arguments(self):
        required = {"set_conditional_formatting": ["layer_name"], "set_map_tip": ["layer_name", "template"], "add_feature_action": ["layer_name", "name", "action_type"]}
        for name in NAMES:
            self.assertIn(name, TOOL_REGISTRY)
            self.assertEqual(schema(name)["parameters"]["required"], required[name], name)
            self.assertTrue(TOOL_KEYWORDS[name], name)
            self.assertEqual(tool_operations.TOOL_OPERATION_TYPES[name], tool_operations.MODIFY, name)
            self.assertIn("project", schema(name)["description"], name)

    def test_the_layer_action_description_states_the_no_command_policy(self):
        text = schema("add_feature_action")["description"]
        self.assertIn("REFUSED by policy", text)
        self.assertIn("OPENS A WEB ADDRESS", text)

    def test_a_command_action_is_refused_before_qgis_is_needed_for_anything_else(self):
        # without QGIS the tool answers 'QGIS not available'; the refusal itself is pure and tested in test_display_rules
        self.assertEqual(TOOL_REGISTRY["add_feature_action"]("a", "Run", "python"), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["set_map_tip"]("a", "x"), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["set_conditional_formatting"]("a"), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()


class TestNameAvoidsTheLayerWord(unittest.TestCase):
    def test_no_new_tool_name_has_the_word_layer_because_the_router_scores_name_words(self):
        """The router gives +10 for a tool-name word found in the request; 'layer' is in almost every request, so a name with it pushed get_layer_extent out of the offered tools
        for 'zoom to the layer smoke_zones' (tests.test_tool_router_basics golden requests)."""
        for name in NAMES:
            self.assertNotIn("layer", name.split("_"), name)
        self.assertIn("add_feature_action", TOOL_REGISTRY)
