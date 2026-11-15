"""PLAN-023 R9-4: the registration contract of copy_features_between_layers (offline: no QGIS needed). The mapping is in test_copy_ops.py and the real-layer behaviour in
test_copy_features_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "copy_features_between_layers")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_required_layers_and_a_mapping_argument(self):
        self.assertIn("copy_features_between_layers", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["source_layer", "target_layer"])
        for key in ("only_selected", "filter_expression", "field_mapping"):
            self.assertIn(key, params["properties"], key)

    def test_it_changes_the_target_so_it_is_a_modify_tool_with_a_preview_and_a_same_type_rule(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["copy_features_between_layers"], tool_operations.MODIFY)
        text = schema()["description"]
        for word in ("SAME geometry type", "preview", "undo_manual_edit", "never changed"):
            self.assertIn(word, text)
        self.assertIn("copy features", TOOL_KEYWORDS["copy_features_between_layers"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["copy_features_between_layers"]("a", "b"), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
